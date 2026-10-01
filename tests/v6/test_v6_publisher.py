"""V6 publisher tests — mocked urllib, no network calls."""
from __future__ import annotations

from brief.publication_identity import PublishIdentity

import io
import json
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from brief.v6_publisher import (
    PublishError,
    fetch_max_issue_no,
    fetch_previous_brief,
    publish_brief,
)
from brief.v6_schema import BriefPayloadV6


@pytest.fixture(autouse=True)
def _supabase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")


def _fake_response(payload: object) -> io.BytesIO:
    body = json.dumps(payload).encode("utf-8")
    resp = io.BytesIO(body)
    return resp


def _minimal_payload(issue_no: int = 89) -> BriefPayloadV6:
    return BriefPayloadV6.model_validate(
        {
            "brief": {
                "issue_no": issue_no,
                "volume": 1,
                "brief_date": "2026-05-05",
                "todays_call": "Test brief.",
                "status": "published",
            },
            "sections": [
                {
                    "slug": "bb",
                    "ord": 3,
                    "title": "Bangladesh Bank",
                    "group_key": "banking",
                    "weight": 1,
                    "metrics": [
                        {"label": "Repo", "value": "10.00%", "tone": "neu"},
                    ],
                    "news": [
                        {"headline": "BB holds policy rates", "source": "DS"},
                    ],
                }
            ],
        }
    )


def test_missing_env_raises() -> None:
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(PublishError, match="Missing SUPABASE_URL"):
            fetch_max_issue_no()


def test_fetch_max_issue_no_empty_table() -> None:
    """fetch_max_issue_no returns 0 when the table is empty."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = _fake_response([])
        assert fetch_max_issue_no() == 0


def test_fetch_max_issue_no_with_data() -> None:
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = _fake_response(
            [{"issue_no": 88}]
        )
        assert fetch_max_issue_no() == 88


def test_fetch_previous_brief_none() -> None:
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = _fake_response([])
        assert fetch_previous_brief() is None


_RPC_URL = "https://test.supabase.co/rest/v1/rpc/publish_brief_atomic"
_BRIEF_UUID = "3f2b8c1e-4d5a-4e6f-9a7b-8c9d0e1f2a3b"


def _receipt(**changes: object) -> dict[str, object]:
    """A SYNTHETIC receipt shaped like publish_brief_atomic's jsonb return."""
    base: dict[str, object] = {
        "brief_id": _BRIEF_UUID,
        "issue_no": 89,
        "brief_date": "2026-05-05",
        "published_at": "2026-05-05T02:10:11.123456+00:00",
        "created_new_identity": True,
    }
    return {**base, **changes}


class _Reply:
    """urlopen context manager whose read() returns bytes or raises."""

    def __init__(self, raw: bytes | BaseException) -> None:
        self._raw = raw

    def __enter__(self) -> "_Reply":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        if isinstance(self._raw, BaseException):
            raise self._raw
        return self._raw


class _AtRead:
    """A failure that happens while reading the response body (after commit)."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc


def _rpc_http(calls: list[dict[str, object]], reply: object):  # type: ignore[no-untyped-def]
    """Record every request at the urllib boundary; answer with `reply`."""

    def _side(req, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append({
            "method": req.get_method(),
            "url": req.full_url,
            "headers": {k.lower(): v for k, v in req.header_items()},
            "body": json.loads(req.data.decode()) if req.data else None,
            "timeout": kwargs.get("timeout", args[1] if len(args) > 1 else None),
        })
        if isinstance(reply, BaseException):
            raise reply  # failure while connecting / an HTTP error status
        if isinstance(reply, _AtRead):
            return _Reply(reply.exc)  # headers arrived, the body was lost
        return _Reply(reply)

    return _side


def _identity(payload: BriefPayloadV6) -> PublishIdentity:
    return PublishIdentity(payload.brief.issue_no, payload.brief.brief_date)


def _http_error(code: int, body: dict[str, object]) -> Exception:
    import urllib.error

    return urllib.error.HTTPError(
        url=_RPC_URL, code=code, msg="error", hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(json.dumps(body).encode()),
    )


def test_publication_is_one_atomic_database_call_carrying_the_trusted_identity() -> None:
    """R3: the whole edition goes to the database in ONE request; the database
    replaces it in one transaction. No DELETE, sweep, child POST or PATCH."""
    from brief import v6_publisher

    payload = _minimal_payload(issue_no=89)
    calls: list[dict[str, object]] = []
    with patch("urllib.request.urlopen",
               side_effect=_rpc_http(calls, json.dumps(_receipt()).encode())):
        receipt = publish_brief(payload, expected_identity=_identity(payload))

    assert len(calls) == 1
    call = calls[0]
    assert call["method"] == "POST"
    assert call["url"] == _RPC_URL
    assert call["body"] == {
        "p_expected_issue_no": 89,
        "p_expected_brief_date": "2026-05-05",
        "p_payload": payload.model_dump(mode="json"),
    }
    headers = call["headers"]
    assert headers["apikey"] == "test-service-key"  # type: ignore[index]
    assert headers["authorization"] == "Bearer test-service-key"  # type: ignore[index]
    assert headers["content-type"] == "application/json"  # type: ignore[index]
    assert call["timeout"] == 30
    assert receipt == v6_publisher.PublishReceipt(
        brief_id=_BRIEF_UUID, issue_no=89, brief_date=date(2026, 5, 5),
        published_at=datetime(2026, 5, 5, 2, 10, 11, 123456, tzinfo=timezone.utc),
        created_new_identity=True,
    )


def test_existing_identity_receipt_is_carried_as_not_new() -> None:
    payload = _minimal_payload(issue_no=89)
    calls: list[dict[str, object]] = []
    body = json.dumps(_receipt(created_new_identity=False)).encode()
    with patch("urllib.request.urlopen", side_effect=_rpc_http(calls, body)):
        receipt = publish_brief(payload, expected_identity=_identity(payload))
    assert receipt.created_new_identity is False
    assert len(calls) == 1


_BAD_RECEIPTS: list[tuple[str, object]] = [
    ("empty object", {}),
    ("null", None),
    ("array wrapped", [_receipt()]),
    ("string", "ok"),
    ("missing brief_id", {k: v for k, v in _receipt().items() if k != "brief_id"}),
    ("missing created_new_identity",
     {k: v for k, v in _receipt().items() if k != "created_new_identity"}),
    ("unknown extra field", _receipt(notify=True)),
    ("brief_id not a uuid", _receipt(brief_id="brief-uuid-1")),
    ("brief_id number", _receipt(brief_id=7)),
    ("issue_no string", _receipt(issue_no="89")),
    ("issue_no bool", _receipt(issue_no=True)),
    ("issue_no float", _receipt(issue_no=89.0)),
    ("issue_no mismatch", _receipt(issue_no=90)),
    ("brief_date mismatch", _receipt(brief_date="2026-05-04")),
    ("brief_date malformed", _receipt(brief_date="05/05/2026")),
    ("brief_date null", _receipt(brief_date=None)),
    ("published_at missing zone", _receipt(published_at="2026-05-05T02:10:11")),
    ("published_at malformed", _receipt(published_at="yesterday")),
    ("published_at null", _receipt(published_at=None)),
    ("created_new_identity string", _receipt(created_new_identity="true")),
    ("created_new_identity int", _receipt(created_new_identity=1)),
    ("created_new_identity null", _receipt(created_new_identity=None)),
]


@pytest.mark.parametrize("label,raw", _BAD_RECEIPTS, ids=[b[0] for b in _BAD_RECEIPTS])
def test_malformed_or_mismatched_receipt_fails_closed(label: str, raw: object) -> None:
    """Only a receipt whose every field validates, for exactly this identity,
    may leave publish_brief — anything else raises, so nothing can notify."""
    payload = _minimal_payload(issue_no=89)
    calls: list[dict[str, object]] = []
    with patch("urllib.request.urlopen",
               side_effect=_rpc_http(calls, json.dumps(raw).encode())):
        with pytest.raises(PublishError, match="receipt"):
            publish_brief(payload, expected_identity=_identity(payload))
    assert len(calls) == 1, "a bad receipt must never trigger a replay or fallback write"


def _transport_failures() -> list[tuple[str, object]]:
    import http.client
    import urllib.error

    return [
        ("function missing 404 PGRST202", _http_error(404, {
            "code": "PGRST202", "message": "Could not find the function public.publish_brief_atomic",
        })),
        ("database refusal identity_conflict", _http_error(400, {
            "code": "P0001", "hint": "identity_conflict", "message": "refused",
        })),
        ("database refusal wrong_publication_date", _http_error(400, {
            "code": "P0001", "hint": "wrong_publication_date", "message": "refused",
        })),
        ("statement timeout", _http_error(500, {"code": "57014", "message": "canceling statement"})),
        ("gateway 502", _http_error(502, {"message": "bad gateway"})),
        ("network unreachable", urllib.error.URLError("unreachable")),
        ("connect timeout", urllib.error.URLError(TimeoutError("timed out"))),
        ("response lost: read timeout after commit", _AtRead(TimeoutError("timed out"))),
        ("response lost: connection reset", _AtRead(ConnectionResetError("reset"))),
        ("response truncated", _AtRead(http.client.IncompleteRead(b'{"brief_id":'))),
        ("malformed json", b'{"brief_id": '),
        ("empty body", b""),
        ("html error page", b"<html>502</html>"),
    ]


@pytest.mark.parametrize("label,reply", _transport_failures(),
                         ids=[f[0] for f in _transport_failures()])
def test_any_transport_or_database_failure_fails_closed_without_fallback(
    label: str, reply: object,
) -> None:
    """HTTP errors, a missing function, timeouts and lost/malformed responses
    all raise PublishError after exactly ONE request: no legacy DELETE+POST
    fallback and no automatic replay whose success could read as permission."""
    payload = _minimal_payload(issue_no=89)
    calls: list[dict[str, object]] = []
    with patch("urllib.request.urlopen", side_effect=_rpc_http(calls, reply)):
        with pytest.raises(PublishError):
            publish_brief(payload, expected_identity=_identity(payload))
    assert [(c["method"], c["url"]) for c in calls] == [("POST", _RPC_URL)]


def test_missing_function_error_names_the_migration() -> None:
    """An operator reading the log must see why: the R3 migration is absent."""
    payload = _minimal_payload(issue_no=89)
    calls: list[dict[str, object]] = []
    reply = _http_error(404, {"code": "PGRST202", "message": "Could not find the function"})
    with patch("urllib.request.urlopen", side_effect=_rpc_http(calls, reply)):
        with pytest.raises(PublishError, match="0006"):
            publish_brief(payload, expected_identity=_identity(payload))


def test_model_issue_one_april20_cannot_delete_when_max_is_235():
    from datetime import date
    from brief.publication_identity import resolve_identity

    expected = resolve_identity(date(2026, 9, 25), same_day_rows=[], max_issue_no=235)
    payload = _minimal_payload(issue_no=1)
    payload.brief.brief_date = date(2026, 4, 20)
    with patch("brief.v6_publisher._request") as request:
        with pytest.raises(PublishError, match="trusted publication identity"):
            publish_brief(payload, expected_identity=expected)
    request.assert_not_called()  # zero GET/DELETE/POST/PATCH, before config/network


def test_trusted_identity_not_the_model_payload_targets_the_database_write():
    """The database re-checks the target under its lock (identity_conflict);
    Python must send the trusted identity, and a model that changed it is
    refused before any request (no read-then-delete window any more)."""
    payload = _minimal_payload(issue_no=235)
    with patch("brief.v6_publisher._request") as request:
        with pytest.raises(PublishError, match="trusted publication identity"):
            publish_brief(payload, expected_identity=PublishIdentity(235, date(2026, 4, 20)))
    request.assert_not_called()


def test_publisher_requires_trusted_identity():
    with patch("brief.v6_publisher._request") as request:
        with pytest.raises(TypeError, match="expected_identity"):
            publish_brief(_minimal_payload())
    request.assert_not_called()


def test_same_day_read_includes_drafts_and_published_rows():
    from datetime import date
    from brief.v6_publisher import fetch_same_day_briefs

    with patch("brief.v6_publisher._request", return_value=[]) as request:
        assert fetch_same_day_briefs(date(2026, 9, 25)) == []
    assert request.call_args.args == (
        "GET", "/briefs?brief_date=eq.2026-09-25&select=issue_no,brief_date,status",
    )
