"""A missing, truncated, malformed or old EconDelta snapshot never reaches the model as fresh.

The Hetzner copy of latest.json arrives by a five-minute rsync from ExonVPS. When it is
absent or unreadable, gather() still builds from history (existing behaviour), but the
snapshot it hands on must carry no invented capture time, and the pre-model readiness
check must name the unavailable snapshot in its log line.
"""
from __future__ import annotations

import json
import logging
import socket
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from brief import cli
from brief.v6_publisher import PublishReceipt
from brief.pipeline import PipelineConfig, gather

TODAY = date(2026, 9, 25)
RUN_AT = datetime(2026, 9, 25, 8, 0, tzinfo=timezone(timedelta(hours=6)))  # brief.timer, BDT
FIXTURE = Path(__file__).parent.parent / "fixtures" / "econdelta_latest.json"


def _missing(tmp_path: Path) -> Path:
    return tmp_path / "latest.json"


def _truncated(tmp_path: Path) -> Path:
    whole = FIXTURE.read_bytes()
    path = tmp_path / "latest.json"
    path.write_bytes(whole[: len(whole) // 2])
    return path


def _top_level_list(tmp_path: Path) -> Path:
    path = tmp_path / "latest.json"
    path.write_text(json.dumps([json.loads(FIXTURE.read_text())]))
    return path


def _naive_capture(tmp_path: Path) -> Path:
    payload = {**json.loads(FIXTURE.read_text()), "updated_at": "2026-09-24T20:56:00"}
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(payload))
    return path


UNREADABLE = [(_missing, "not found"), (_truncated, "unparseable"),
              (_top_level_list, "not an object"), (_naive_capture, "timezone")]
UNREADABLE_IDS = ["missing", "truncated", "top-level-list", "naive-capture"]


@pytest.fixture(autouse=True)
def _refuse_network(monkeypatch):
    """Recovery runs are hermetic: an empty snapshot must not send builders to live sites."""
    attempts: list[str] = []

    def refuse_connect(self: socket.socket, address: object) -> None:
        attempts.append(f"connect({address!r})")
        raise OSError(f"test refused outbound connect to {address!r}")

    def refuse_lookup(host: object, *args: object, **kwargs: object) -> None:
        attempts.append(f"getaddrinfo({host!r})")
        raise OSError(f"test refused DNS lookup of {host!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse_connect)
    monkeypatch.setattr(socket, "getaddrinfo", refuse_lookup)
    yield
    if attempts:
        pytest.fail("outbound network attempted: " + ", ".join(sorted(set(attempts))))


@pytest.fixture(autouse=True)
def _no_live_alert_channel(monkeypatch):
    # No run in this file may reach a real webhook, and the operator pause is off unless a
    # test sets it. Alert-path tests replace the transport with a fake on top of this.
    for name in ("DISCORD_ALERT_WEBHOOK_URL", "DISCORD_PREVIEW_WEBHOOK_URL", "BRIEF_DRY_RUN"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_live_dse_scrape(monkeypatch):
    # With no snapshot breadth or sector heat, the DSE builder falls back to live dsebd.org
    # scrapes; fake them as "scrape unavailable" (None), the path a failed scrape takes.
    from brief.builders import dse
    monkeypatch.setattr(dse, "scrape_breadth", lambda *a, **k: None)
    monkeypatch.setattr(dse, "scrape_sector_heat", lambda *a, **k: None)


def _config(path: Path) -> PipelineConfig:
    return PipelineConfig(today=TODAY, enable_history=False, enable_headlines=False,
                          econdelta_path=str(path))


@pytest.mark.parametrize("make,cause", UNREADABLE, ids=UNREADABLE_IDS)
def test_gather_never_invents_a_capture_time_for_an_unreadable_snapshot(tmp_path, make, cause):
    sections = gather(_config(make(tmp_path)))
    snapshot = sections.snapshot
    assert snapshot.updated_at is None
    assert snapshot.data == {} and snapshot.sources_status == {} and snapshot.write_status is None
    assert cause in snapshot.load_error


def _publish_dry_run(cfg: PipelineConfig, caplog) -> tuple[int, object]:
    with caplog.at_level(logging.INFO, logger="brief.cli"), \
         patch("brief.cli.now_bdt", return_value=RUN_AT), \
         patch("brief.v6_publisher.fetch_same_day_briefs", return_value=[]), \
         patch("brief.v6_publisher.fetch_max_issue_no", return_value=235), \
         patch("brief.pipeline_v6.run_publish", return_value=None) as run:
        rc = cli._run_v6_publish(cfg, TODAY, dry_run=True, notify_enabled=False)
    return rc, run


def _readiness_line(caplog) -> str:
    (line,) = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Publication readiness:")]
    return line


@pytest.mark.parametrize("make,cause", UNREADABLE, ids=UNREADABLE_IDS)
def test_publication_readiness_names_the_unavailable_snapshot_before_the_model(tmp_path, caplog, make, cause):
    rc, run = _publish_dry_run(_config(make(tmp_path)), caplog)
    line = _readiness_line(caplog)
    assert line.startswith("Publication readiness: degraded; EconDelta snapshot unavailable (")
    assert cause in line
    assert "capture time, source health and accepted observations unknown" in line
    # The model receives the same snapshot readiness judged: still no invented capture time.
    assert run.call_args.args[0].snapshot.updated_at is None
    assert rc == 3


def test_publication_readiness_reports_an_old_snapshot_by_its_age(tmp_path, caplog):
    payload = {**json.loads(FIXTURE.read_text()), "updated_at": "2026-09-22T20:56:00Z"}
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(payload))
    _publish_dry_run(_config(path), caplog)
    line = _readiness_line(caplog)
    assert line.startswith("Publication readiness: degraded; ")
    assert "snapshot capture is more than one day old" in line
    assert "unavailable (" not in line


@pytest.mark.parametrize("write_status", [["ok"], "ok", 1, True], ids=["list", "string", "number", "bool"])
def test_a_present_but_malformed_receipt_block_holds_the_publish_before_the_model(tmp_path, caplog, write_status):
    # Absent receipts are legacy (unconfirmed); a receipt block that is there but is not an
    # object is a contradiction on the real load path too, not an "unavailable" snapshot.
    payload = {**json.loads(FIXTURE.read_text()), "updated_at": "2026-09-24T20:56:00Z",
               "write_status": write_status}
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(payload))
    rc, run = _publish_dry_run(_config(path), caplog)
    line = _readiness_line(caplog)
    assert line.startswith("Publication readiness: hold; persistence receipts malformed")
    assert "unavailable (" not in line
    assert not run.called
    assert rc == 4


# ── Owner decision (e): an unavailable snapshot still publishes from saved history, and the
# operator gets exactly ONE alert per run naming the cause category (never a path or a raw
# exception dump). The transport is always a fake here; nothing is sent. ──
def _empty(tmp_path: Path) -> Path:
    path = tmp_path / "latest.json"
    path.write_bytes(b"")  # an interrupted copy leaves nothing behind
    return path


def _garbage(tmp_path: Path) -> Path:
    path = tmp_path / "latest.json"
    path.write_text("<html>502 Bad Gateway</html>")
    return path


def _corrupt_bytes(tmp_path: Path) -> Path:
    path = tmp_path / "latest.json"
    path.write_bytes(b'{"updated_at": "\xff\xfe\xfd", "sources_status": {}, "data": {}}')
    return path


def _no_data_field(tmp_path: Path) -> Path:
    payload = {k: v for k, v in json.loads(FIXTURE.read_text()).items() if k != "data"}
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(payload))
    return path


def _directory(tmp_path: Path) -> Path:
    path = tmp_path / "latest.json"
    path.mkdir()
    return path


def _stale(tmp_path: Path) -> Path:
    payload = {**json.loads(FIXTURE.read_text()), "updated_at": "2026-09-22T20:56:00Z"}
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(payload))
    return path


def _healthy(tmp_path: Path) -> Path:
    # 02:56 BDT capture, five hours before the 08:00 BDT fire.
    payload = {**json.loads(FIXTURE.read_text()), "updated_at": "2026-09-24T20:56:00Z"}
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(payload))
    return path


ALERT_CASES = [
    (_missing, "missing"), (_truncated, "truncated"), (_empty, "truncated"),
    (_garbage, "unparseable"), (_corrupt_bytes, "unparseable"),
    (_top_level_list, "wrong shape"), (_no_data_field, "wrong shape"), (_naive_capture, "wrong shape"),
    (_directory, "unreadable"), (_stale, "stale capture"),
]
ALERT_CASE_IDS = ["missing", "truncated-half", "truncated-empty", "unparseable-text",
                  "unparseable-bytes", "wrong-shape-list", "wrong-shape-no-data",
                  "wrong-shape-naive-capture", "unreadable-directory", "stale-capture"]
# Raw decoder/OS error text that must stay in the service log, never in the Discord message.
RAW_ERROR_FRAGMENTS = ("Expecting", "Unterminated", "codec", "Errno", "Traceback",
                       "JSONDecodeError", "IsADirectoryError", "not an object", "timezone")


# Where today's numbers came from, as the alert must tell it (fix 14 round 1). A snapshot that
# loaded but is not a current capture is still READ — its figures reach the cards — so its
# alert must never claim a history-only build, and a load failure's alert must never claim a
# snapshot was read.
FROM_SAVED_HISTORY = "from saved history (degraded) because the EconDelta snapshot could not be used"
FROM_OLD_SNAPSHOT = "from an EconDelta snapshot captured more than one day ago (degraded)"
FROM_UNDATED_SNAPSHOT = "from an EconDelta snapshot whose capture time is unknown (degraded)"


def _publish(cfg: PipelineConfig, caplog, *, dry_run: bool = False, alert=None, seen: list | None = None):
    """A live-shaped run (no lock, no database, no model): only the alert transport is observed.

    `seen` (optional) receives the snapshot the run's own gather() handed on.
    """
    alert = alert if alert is not None else patch("brief.alerts.send_discord_alert", return_value=True)

    def _recording_gather(config):
        sections = gather(config)
        if seen is not None:
            seen.append(sections.snapshot)
        return sections

    with caplog.at_level(logging.INFO), alert as send, \
         patch("brief.cli.gather", side_effect=_recording_gather), \
         patch("brief.cli.now_bdt", return_value=RUN_AT), \
         patch("brief.v6_publisher.fetch_same_day_briefs", return_value=[]), \
         patch("brief.v6_publisher.fetch_max_issue_no", return_value=235), \
         patch("brief.pipeline_v6.run_publish", return_value=PublishReceipt(  # SYNTHETIC receipt
             brief_id="3f2b8c1e-4d5a-4e6f-9a7b-8c9d0e1f2a3b", issue_no=236, brief_date=TODAY,
             published_at=RUN_AT, created_new_identity=True)) as run:
        rc = cli._run_v6_publish_unlocked(cfg, TODAY, dry_run=dry_run, notify_enabled=False)
    return rc, run, send


@pytest.mark.parametrize("make,cause", ALERT_CASES, ids=ALERT_CASE_IDS)
def test_an_unavailable_snapshot_sends_one_alert_naming_its_cause_and_still_publishes(tmp_path, caplog,
                                                                                     make, cause):
    path = make(tmp_path)
    seen: list = []
    rc, run, send = _publish(_config(path), caplog, seen=seen)
    assert send.call_count == 1
    (message,) = send.call_args.args
    assert f"cause: {cause}." in message
    # The alert's account must match what this run actually built from.
    (snapshot,) = seen
    snapshot_was_read = bool(snapshot.data)
    assert snapshot_was_read == (cause == "stale capture")
    story = FROM_OLD_SNAPSHOT if snapshot_was_read else FROM_SAVED_HISTORY
    assert message.startswith(f"ALERT: The Brief is publishing {story}")
    if snapshot_was_read:
        assert "saved history" not in message and "could not be used" not in message
    else:
        assert "captured more than one day ago" not in message
    assert str(tmp_path) not in message and str(path) not in message
    assert not [fragment for fragment in RAW_ERROR_FRAGMENTS if fragment in message]
    # The publish is not blocked: the model still runs on the degraded input, exit 0.
    assert run.call_count == 1
    assert rc == 0


def test_a_healthy_snapshot_sends_no_snapshot_alert(tmp_path, caplog):
    rc, run, send = _publish(_config(_healthy(tmp_path)), caplog)
    assert not send.called
    assert run.call_count == 1 and rc == 0


@pytest.mark.parametrize("failure", [RuntimeError("https://discord.com/api/webhooks/1/SECRET-TOKEN"),
                                     ImportError("brief.alerts")], ids=["raises", "import-error"])
def test_a_broken_alert_transport_never_blocks_the_degraded_publish(tmp_path, caplog, failure):
    broken = patch("brief.alerts.send_discord_alert", side_effect=failure)
    rc, run, send = _publish(_config(_missing(tmp_path)), caplog, alert=broken)
    assert send.call_count == 1
    assert run.call_count == 1 and rc == 0
    logged = [r.getMessage() for r in caplog.records if "snapshot alert" in r.getMessage()]
    assert logged == [f"snapshot alert: send failed ({type(failure).__name__}); cause: missing"]
    assert "SECRET-TOKEN" not in caplog.text


def test_an_undelivered_alert_is_logged_and_the_publish_proceeds(tmp_path, caplog):
    undelivered = patch("brief.alerts.send_discord_alert", return_value=False)
    rc, run, send = _publish(_config(_missing(tmp_path)), caplog, alert=undelivered)
    assert send.call_count == 1 and run.call_count == 1 and rc == 0
    assert [r.getMessage() for r in caplog.records if "snapshot alert" in r.getMessage()] == [
        "snapshot alert: not delivered; cause: missing"]


@pytest.mark.parametrize("make,cause,story", [(_missing, "missing", FROM_SAVED_HISTORY),
                                               (_stale, "stale capture", FROM_OLD_SNAPSHOT)],
                         ids=["missing", "stale-capture"])
def test_an_explicit_dry_run_alert_never_claims_a_publish(tmp_path, caplog, make, cause, story):
    rc, _run, send = _publish(_config(make(tmp_path)), caplog, dry_run=True)
    (message,) = send.call_args.args
    assert send.call_count == 1 and rc == 3
    assert message.startswith(f"ALERT: The Brief dry run (nothing will be published) is building {story}")
    assert "publishing" not in message
    assert f"cause: {cause}." in message


def test_a_snapshot_with_no_capture_time_is_not_reported_as_a_history_only_build():
    # "capture time unknown" means the snapshot loaded and its data is read, but nobody knows
    # when it was captured. Only a programmatic snapshot reaches it (load_snapshot rejects a
    # missing or naive updated_at as "wrong shape"), so the alert is checked at its own seam.
    from brief.snapshot_alert import alert_snapshot_problem
    with patch("brief.alerts.send_discord_alert", return_value=True) as send:
        assert alert_snapshot_problem("capture time unknown", dry_run=False) is True
    (message,) = send.call_args.args
    assert message.startswith(f"ALERT: The Brief is publishing {FROM_UNDATED_SNAPSHOT}")
    assert "cause: capture time unknown." in message
    assert "saved history" not in message and "could not be used" not in message


def test_the_operator_pause_suppresses_the_snapshot_alert(tmp_path, caplog, monkeypatch):
    # deploy/README.md: BRIEF_DRY_RUN pauses every in-process pipeline warning send.
    monkeypatch.setenv("BRIEF_DRY_RUN", "1")
    rc, _run, send = _publish(_config(_missing(tmp_path)), caplog, dry_run=True)
    assert not send.called and rc == 3
    assert [r.getMessage() for r in caplog.records if "snapshot alert" in r.getMessage()] == [
        "snapshot alert: suppressed by publication pause; cause: missing"]


def test_a_held_run_leaves_the_alert_to_the_failure_unit(tmp_path, caplog):
    # A hold exits 4, which already fires the OnFailure Discord alert with the log tail;
    # a second in-process message would make two alerts for one run.
    payload = {**json.loads(FIXTURE.read_text()), "updated_at": "2026-09-22T20:56:00Z",
               "write_status": ["ok"]}
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(payload))
    rc, run, send = _publish(_config(path), caplog)
    assert rc == 4 and not run.called and not send.called


def test_healthy_official_lag_is_logged_as_a_note_never_as_a_readiness_reason(tmp_path, caplog):
    """R2 fix 4: BB not having published a newer month is a fact worth logging, not a problem."""
    at = "2026-09-24T21:00:00Z"
    lag = {"status": "skipped", "attempted_at": at, "reason": "no new official period",
           "skips": [{"category": "no new official period", "detail": "BB lists nothing newer",
                      "newest_recorded": "2026-08-01", "lag_window_days": 45}]}
    payload = {**json.loads(FIXTURE.read_text()), "updated_at": "2026-09-24T20:56:00Z",
               "write_status": {"daily": {"status": "ok", "attempted_at": at},
                                "monthly": {"status": "skipped", "attempted_at": at, "legs": {"remittance": lag}}}}
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(payload))
    _publish_dry_run(_config(path), caplog)
    notes = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Readiness notes")]
    assert notes == [("Readiness notes (healthy, not degrading): monthly remittance leg: official publication "
                      "lag (BB lists nothing after 2026-08; inside its accepted 45-day lag window)")]
    assert "remittance" not in _readiness_line(caplog)
