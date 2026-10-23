"""R3 design test 4: only a fresh, validated publication receipt that says this
run CREATED today's identity may start the subscriber email — and a restart
after any crash never replays audience sends.

Everything below the CLI is real (identity read, publish_brief, the notifier's
subscriber pagination and per-recipient Brevo loop). Fakes sit only at the HTTP
boundary: one in-memory "world" answers Supabase REST, the publish_brief_atomic
RPC (with the database's committed-identity semantics) and Brevo. The model
stage is replaced by a stand-in that hands a SYNTHETIC payload to the real
publisher. `_Killed` is a BaseException, so no `except Exception` handler can
run after it — the in-process equivalent of SIGKILL. No network, no email.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from brief import cli
from brief.cadence import now_bdt

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"
_SUBSCRIBERS = [  # SYNTHETIC recipients, ascending UUID cursor order
    {"id": "00000000-0000-4000-8000-000000000001", "name": "A", "email": "a@example.test",
     "organisation": None},
    {"id": "00000000-0000-4000-8000-000000000002", "name": "B", "email": "b@example.test",
     "organisation": None},
    {"id": "00000000-0000-4000-8000-000000000003", "name": "C", "email": "c@example.test",
     "organisation": None},
]


class _Killed(BaseException):
    """Simulated process death: nothing after this point runs in that process."""


class _Body:
    def __init__(self, raw: bytes | BaseException) -> None:
        self._raw = raw

    def __enter__(self) -> "_Body":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        if isinstance(self._raw, BaseException):
            raise self._raw
        return self._raw


class _World:
    """In-memory Supabase + Brevo. `briefs` survives a 'restart' (a new CLI run)."""

    def __init__(self, today: date) -> None:
        self.today = today
        self.briefs: list[dict[str, Any]] = [{
            "id": str(uuid.uuid4()), "issue_no": 235, "volume": 1,
            "brief_date": "2026-09-25", "status": "published",
        }]
        self.accepted: list[str] = []  # recipients Brevo accepted (HTTP 2xx)
        self.rpc_calls = 0
        self.unexpected: list[str] = []
        self.rpc_fault: str | None = None  # one-shot: applies to the next RPC only
        self.kill_after_brevo: int | None = None
        self.kill_before_notifier = False

    # ── database semantics of publish_brief_atomic (migration 0006) ──────
    def _commit(self, issue_no: int, brief_date: str) -> tuple[dict[str, Any], bool]:
        existing = [b for b in self.briefs if b["brief_date"] == brief_date]
        if existing:
            row = existing[0]
            assert row["issue_no"] == issue_no, "fake DB: identity_conflict"
            row["status"] = "published"
            return row, False
        assert issue_no == max(b["issue_no"] for b in self.briefs) + 1
        row = {"id": str(uuid.uuid4()), "issue_no": issue_no, "volume": 1,
               "brief_date": brief_date, "status": "published"}
        self.briefs.append(row)
        return row, True

    def _rpc(self, body: dict[str, Any]) -> _Body:
        self.rpc_calls += 1
        fault, self.rpc_fault = self.rpc_fault, None
        if fault == "competitor_committed_first":
            self._commit(body["p_expected_issue_no"], body["p_expected_brief_date"])
        row, created = self._commit(body["p_expected_issue_no"], body["p_expected_brief_date"])
        if fault == "claims_new":  # a receipt that (wrongly) says new; same-day guard must hold
            created = True
        receipt = json.dumps({
            "brief_id": row["id"], "issue_no": row["issue_no"],
            "brief_date": row["brief_date"],
            "published_at": datetime.now(timezone.utc).isoformat(),
            "created_new_identity": created,
        }).encode()
        # The transaction is COMMITTED above; each fault loses only the answer.
        if fault == "response_dropped":
            return _Body(TimeoutError("timed out"))
        if fault == "connection_reset":
            return _Body(ConnectionResetError("reset by peer"))
        if fault == "malformed":
            return _Body(receipt[: len(receipt) // 2])
        if fault == "empty":
            return _Body(b"")
        if fault == "gateway_502":
            import io
            import urllib.error
            raise urllib.error.HTTPError(
                "https://fake.supabase.test/rest/v1/rpc/publish_brief_atomic", 502,
                "Bad Gateway", None, io.BytesIO(b"<html>502</html>"),  # type: ignore[arg-type]
            )
        return _Body(receipt)

    def _rest_get(self, table: str, query: dict[str, list[str]]) -> Any:
        if table == "briefs" and "brief_date" in query:
            day = query["brief_date"][0].removeprefix("eq.")
            return [{"issue_no": b["issue_no"], "brief_date": b["brief_date"],
                     "status": b["status"]} for b in self.briefs if b["brief_date"] == day]
        if table == "briefs" and query.get("order") == ["issue_no.desc"]:
            return [{"issue_no": max(b["issue_no"] for b in self.briefs)}]
        if table == "briefs" and "id" in query:
            wanted = query["id"][0].removeprefix("eq.")
            return [{**b, "published_at": "2026-09-29T02:00:00+00:00",
                     "todays_call": "SYNTHETIC call.", "lens": None}
                    for b in self.briefs if b["id"] == wanted]
        if table == "sections":
            return []  # no headlines section: the email has no lead story
        if table == "subscribers":
            return [] if "id" in query else _SUBSCRIBERS
        self.unexpected.append(f"GET {table} {query}")
        return []

    def urlopen(self, req: Any, *args: Any, **kwargs: Any) -> _Body:
        parts = urlsplit(req.full_url)
        method = req.get_method()
        body = json.loads(req.data.decode()) if req.data else None
        if req.full_url == _BREVO_URL and method == "POST":
            self.accepted.append(body["to"][0]["email"])
            if self.kill_after_brevo == len(self.accepted):
                raise _Killed(f"killed after Brevo POST {len(self.accepted)}")
            return _Body(json.dumps({"messageId": f"m-{len(self.accepted)}"}).encode())
        if parts.path == "/rest/v1/rpc/publish_brief_atomic" and method == "POST":
            return self._rpc(body)
        if parts.path.startswith("/rest/v1/") and method == "GET":
            table = parts.path.removeprefix("/rest/v1/")
            return _Body(json.dumps(self._rest_get(table, parse_qs(parts.query))).encode())
        self.unexpected.append(f"{method} {req.full_url}")
        raise AssertionError(f"unexpected request {method} {parts.path}")

    def rows_on(self, day: date) -> list[dict[str, Any]]:
        return [b for b in self.briefs if b["brief_date"] == day.isoformat()]


def _model_stage(sections: Any, today: date, *, expected_identity: Any,
                 **_: Any) -> Any:
    """Stand-in for the LLM stages: a SYNTHETIC payload handed to the REAL publisher."""
    from brief.pipeline_v6 import V6PublishError
    from brief.v6_publisher import PublishError, publish_brief
    from brief.v6_schema import BriefPayloadV6

    payload = BriefPayloadV6.model_validate({
        "brief": {"issue_no": expected_identity.issue_no, "volume": 1,
                  "brief_date": expected_identity.brief_date.isoformat(),
                  "todays_call": "SYNTHETIC test edition.", "status": "published"},
        "sections": [{"slug": "bb", "ord": 3, "title": "Bangladesh Bank",
                      "group_key": "banking", "weight": 1}],
    })
    try:
        return publish_brief(payload, expected_identity=expected_identity)
    except PublishError as exc:  # same translation as the real run_publish
        raise V6PublishError(f"Supabase publish failed: {exc}") from exc


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> _World:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("BRIEF_DRY_RUN", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-service-key")
    monkeypatch.setenv("BREVO_API_KEY", "synthetic-brevo-key")
    monkeypatch.setenv("FROM_EMAIL", "sender@example.test")
    monkeypatch.setenv("UNSUBSCRIBE_EMAIL", "unsubscribe@example.test")
    return _World(now_bdt().date())


def _run_cli(world: _World) -> int:
    """One live `brief.cli run --publish` process lifetime against the world."""
    import brief.notifier as notifier

    real_notify = notifier.notify

    def notify(brief_id: str) -> Any:
        if world.kill_before_notifier:
            world.kill_before_notifier = False
            raise _Killed("killed after the publish response, before the notifier")
        return real_notify(brief_id)

    with patch("urllib.request.urlopen", side_effect=world.urlopen), \
         patch("brief.notifier.urlopen", side_effect=world.urlopen), \
         patch("brief.cli.gather", return_value=[]), \
         patch("brief.headlines.scrape_all", return_value=[]), \
         patch("brief.pipeline_v6.run_publish", side_effect=_model_stage), \
         patch("brief.notifier.notify", side_effect=notify), \
         patch("brief.alerts.send_discord_alert"):
        return cli.main(["run", "--publish"])


def test_fresh_first_publication_notifies_every_subscriber_exactly_once(world: _World) -> None:
    """Control: the harness CAN send, so every zero-send assertion below is meaningful."""
    assert _run_cli(world) == 0
    assert world.accepted == [s["email"] for s in _SUBSCRIBERS]
    assert [r["issue_no"] for r in world.rows_on(world.today)] == [236]
    assert world.rpc_calls == 1
    assert world.unexpected == []


@pytest.mark.parametrize("fault", [
    "response_dropped", "connection_reset", "malformed", "empty", "gateway_502",
])
def test_commit_succeeded_but_answer_lost_never_notifies_even_after_restart(
    world: _World, fault: str,
) -> None:
    world.rpc_fault = fault
    assert _run_cli(world) == 4  # held: commit outcome unknown to this process
    assert world.accepted == []
    assert world.rpc_calls == 1, "no automatic replay of the RPC"
    committed = world.rows_on(world.today)
    assert [(r["issue_no"], r["status"]) for r in committed] == [(236, "published")]

    assert _run_cli(world) == 0  # restart: same identity, suppressed
    assert world.accepted == []
    assert world.rows_on(world.today) == committed  # same UUID and issue, no new number
    assert world.unexpected == []


def test_killed_after_success_before_notifier_restart_does_not_send(world: _World) -> None:
    world.kill_before_notifier = True
    with pytest.raises(_Killed):
        _run_cli(world)
    assert world.accepted == []
    assert _run_cli(world) == 0
    assert world.accepted == []
    assert [r["issue_no"] for r in world.rows_on(world.today)] == [236]


@pytest.mark.parametrize("killed_after", [1, 2, 3], ids=["first", "middle", "last"])
def test_killed_after_a_brevo_post_restart_never_replays_audience_sends(
    world: _World, killed_after: int,
) -> None:
    world.kill_after_brevo = killed_after
    with pytest.raises(_Killed):
        _run_cli(world)
    already = [s["email"] for s in _SUBSCRIBERS[:killed_after]]
    assert world.accepted == already
    world.kill_after_brevo = None

    assert _run_cli(world) == 0
    assert world.accepted == already, "restart must not email anyone again or catch up"
    assert [r["issue_no"] for r in world.rows_on(world.today)] == [236]


def test_receipt_saying_existing_identity_suppresses_a_fresh_looking_run(world: _World) -> None:
    """The same-day read saw nothing, but a competing writer committed first:
    created_new_identity=false must never authorise a send."""
    world.rpc_fault = "competitor_committed_first"
    assert _run_cli(world) == 0
    assert world.accepted == []
    assert [r["issue_no"] for r in world.rows_on(world.today)] == [236]


def test_same_day_suppression_still_applies_to_a_receipt_claiming_new(world: _World) -> None:
    """Both guards are required: a receipt claiming a new identity does not
    override the same-day read that already saw today's edition."""
    assert _run_cli(world) == 0  # today's edition, emailed once
    sent = list(world.accepted)
    world.rpc_fault = "claims_new"
    assert _run_cli(world) == 0
    assert world.accepted == sent
