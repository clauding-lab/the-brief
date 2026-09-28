"""A snapshot the five-minute ExonVPS -> Hetzner pull delivers half-copied, or OLDER than one a
live run already read past readiness, never reads as a current capture (R2 task G3).

The installed pull (read-only check, 28 Sep 2026 00:43 BDT) is a Hetzner cron running
`rsync -t` every five minutes: temp file + rename, so a reader never sees a half-written file
from THAT transfer, but there is no JSON validation and no capture-time check. It copies
whatever latest.json ExonVPS holds, so a restored or rolled-back older snapshot arrives as
faithfully as a new one. The Brief's reader is the only guard, and it must also stay safe if
the transfer is ever changed to a non-atomic copy (scp, rsync --inplace, a manual cp).

Owner decision (e): a snapshot problem publishes degraded plus ONE alert; it never holds.
All data here is synthetic: the repo fixture with its capture time changed. Nothing is sent.
"""
from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from brief.econdelta import EconDeltaSnapshot, EconDeltaUnavailable, load_snapshot
from brief.readiness import assess
from tests.test_snapshot_recovery import (  # noqa: F401 - the three autouse fixtures apply here too
    FIXTURE,
    RUN_AT,
    _config,
    _no_live_alert_channel,
    _no_live_dse_scrape,
    _publish,
    _readiness_line,
    _refuse_network,
)

# Synthetic capture times on the same Bangladesh day as RUN_AT (08:00 BDT 25 Sep 2026).
OLDEST = "2026-09-24T20:30:00Z"   # 02:30 BDT
OLDER = "2026-09-24T20:56:00Z"    # 02:56 BDT: the aggregate's first fire
NEWER = "2026-09-24T21:15:17Z"    # 03:15 BDT: the aggregate's retry fire
NEWEST = "2026-09-24T21:40:00Z"   # 03:40 BDT
AFTER_THE_RUN = "2026-09-25T03:00:00Z"  # 09:00 BDT: later than RUN_AT, a contradiction (hold)
BACKWARDS = "cause: capture went backwards."
BACKWARDS_STORY = ("from an EconDelta snapshot older than the one an earlier run already read past "
                   "readiness (degraded)")
# The mark is recorded after the readiness hold check and BEFORE run_publish, so the alert may only
# claim an earlier run READ that capture past readiness, never that it published or used it (C2).
BACKWARDS_DETAIL = "Figures taken from it are older than ones an earlier run already read past readiness."


def _at(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _snapshot_bytes(captured: str) -> bytes:
    return json.dumps({**json.loads(FIXTURE.read_text()), "updated_at": captured}).encode("utf-8")


def _deliver(path: Path, captured: str) -> Path:
    """What the pull leaves on Hetzner: ExonVPS's latest.json with this capture time."""
    path.write_bytes(_snapshot_bytes(captured))
    return path


def _mark_path() -> Path:
    # Resolved at call time: the module is the unit under test, and conftest points it at a
    # per-test directory (never the real ~/.local/state/the-brief).
    return importlib.import_module("brief.capture_mark").mark_path()


def _alerts(send) -> list[str]:
    return [call.args[0] for call in send.call_args_list]


# ── A non-atomic copy: every partial file is refused as broken, never read as a snapshot ──
def test_every_partial_copy_is_refused_as_broken_never_read_as_a_smaller_snapshot(tmp_path):
    payload = {**json.loads(FIXTURE.read_text()), "updated_at": NEWER,
               "synthetic_note": "synthetic: Tk ৳ 123.45 − multi-byte UTF-8 characters"}
    whole = json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")
    path = tmp_path / "latest.json"
    path.write_bytes(whole)
    assert load_snapshot(path).updated_at == _at(NEWER)  # control: the complete copy loads
    for cut in range(len(whole)):
        path.write_bytes(whole[:cut])
        with pytest.raises(EconDeltaUnavailable) as caught:
            load_snapshot(path)
        assert caught.value.cause in ("truncated", "unparseable"), (cut, caught.value.cause)
    # A copy cut inside a multi-byte character is named for what it is: it ends early.
    inside_taka_sign = whole.index("৳".encode()) + 1
    path.write_bytes(whole[:inside_taka_sign])
    with pytest.raises(EconDeltaUnavailable) as caught:
        load_snapshot(path)
    assert caught.value.cause == "truncated"


def test_a_copy_caught_half_written_degrades_with_one_alert_then_the_completed_copy_reads_clean(
        tmp_path, caplog):
    whole = _snapshot_bytes(NEWER)
    path = tmp_path / "latest.json"
    path.write_bytes(whole[: len(whole) // 3])  # the reader opens the file mid-copy
    seen: list = []
    rc, run, send = _publish(_config(path), caplog, seen=seen)
    assert rc == 0 and run.call_count == 1  # published from saved history, not held
    assert len(_alerts(send)) == 1 and "cause: truncated." in _alerts(send)[0]

    path.write_bytes(whole)  # the copy completes; the next run reads it
    caplog.clear()
    rc, run, send = _publish(_config(path), caplog, seen=seen)
    assert rc == 0 and run.call_count == 1 and not send.called
    assert "unavailable (" not in _readiness_line(caplog)
    half, complete = seen
    assert half.updated_at is None and half.data == {}
    assert complete.updated_at == _at(NEWER)
    assert complete.data == json.loads(whole)["data"]


# ── A capture going BACKWARDS: an older capture replacing a newer one is never current ──
def test_an_older_capture_replacing_one_a_live_run_already_used_degrades_with_one_alert(tmp_path, caplog):
    path = _deliver(tmp_path / "latest.json", NEWER)
    rc, _run, send = _publish(_config(path), caplog)
    assert rc == 0 and not send.called

    _deliver(path, OLDER)  # e.g. a restore on ExonVPS, copied faithfully by the pull
    caplog.clear()
    seen: list = []
    rc, run, send = _publish(_config(path), caplog, seen=seen)
    line = _readiness_line(caplog)
    assert line.startswith("Publication readiness: degraded; ")
    assert ("snapshot capture went backwards (2026-09-25 02:56:00 BDT is older than "
            "2026-09-25 03:15:17 BDT, already read by a live run that passed readiness)") in line
    (message,) = _alerts(send)
    assert message.startswith(f"ALERT: The Brief is publishing {BACKWARDS_STORY} — {BACKWARDS} "
                              f"{BACKWARDS_DETAIL} ")
    assert "already used" not in message
    assert "saved history" not in message and "could not be used" not in message
    # Degraded, never held (decision (e)): the older capture's own dated figures build the edition.
    assert rc == 0 and run.call_count == 1
    assert seen[0].updated_at == _at(OLDER) and seen[0].data


def test_rerunning_on_the_same_capture_is_not_a_regression(tmp_path, caplog):
    path = _deliver(tmp_path / "latest.json", NEWER)
    for _ in range(2):
        rc, run, send = _publish(_config(path), caplog)
        assert rc == 0 and run.call_count == 1 and not send.called


def test_the_mark_is_never_lowered_so_an_older_capture_alerts_until_a_newer_one_arrives(tmp_path, caplog):
    path = tmp_path / "latest.json"
    sent: list[list[str]] = []
    for captured in (NEWER, OLDER, OLDEST, OLDER, NEWEST, NEWER):
        _deliver(path, captured)
        rc, run, send = _publish(_config(path), caplog)
        assert rc == 0 and run.call_count == 1
        sent.append(_alerts(send))
    assert [len(messages) for messages in sent] == [0, 1, 1, 1, 0, 1]
    assert all(BACKWARDS in messages[0] for messages in sent if messages)


def test_a_dry_run_reports_a_backwards_capture_without_claiming_a_publish(tmp_path, caplog):
    path = _deliver(tmp_path / "latest.json", NEWER)
    _publish(_config(path), caplog)
    _deliver(path, OLDER)
    rc, run, send = _publish(_config(path), caplog, dry_run=True)
    (message,) = _alerts(send)
    assert rc == 3 and run.call_count == 1
    assert message.startswith("ALERT: The Brief dry run (nothing will be published) is building "
                              f"{BACKWARDS_STORY} — {BACKWARDS}")


def test_a_dry_run_never_moves_the_mark(tmp_path, caplog):
    # Dry runs replay other days and fixtures (--today, ECONDELTA_DATA); only a live run's
    # capture may become the one later runs are measured against.
    path = _deliver(tmp_path / "latest.json", OLDER)
    assert _publish(_config(path), caplog)[0] == 0
    _deliver(path, NEWEST)
    assert _publish(_config(path), caplog, dry_run=True)[0] == 3
    _deliver(path, OLDER)
    rc, run, send = _publish(_config(path), caplog)
    assert rc == 0 and run.call_count == 1 and not send.called


def _held_malformed_receipts(path: Path) -> Path:
    # A normal, past capture that holds for another reason: a receipt block that is not an object.
    payload = {**json.loads(FIXTURE.read_text()), "updated_at": NEWEST, "write_status": ["ok"]}
    path.write_text(json.dumps(payload))
    return path


@pytest.mark.parametrize("held", [
    lambda path: _deliver(path, AFTER_THE_RUN),  # capture later than the run: a contradiction
    _held_malformed_receipts,
], ids=["future-capture", "malformed-receipts"])
def test_a_held_run_never_moves_the_mark(tmp_path, caplog, held):
    path = held(tmp_path / "latest.json")
    rc, run, send = _publish(_config(path), caplog)
    assert rc == 4 and not run.called and not send.called
    _deliver(path, NEWER)
    rc, run, send = _publish(_config(path), caplog)
    assert rc == 0 and run.call_count == 1 and not send.called


# SYNTHETIC: a hand-crafted mark nested deeper than the JSON decoder can recurse (R2 G3 review
# probe: ~400 KB of brackets made json.loads raise RecursionError, which crashed the run).
DEEPLY_NESTED_MARK = b'{"captured_at": ' + b"[" * 200_000 + b"]" * 200_000 + b"}"


@pytest.mark.parametrize("content", [
    b"", b'{"captured_at": "2026-09-25T03:15', b'["2026-09-24T21:15:17+00:00"]',
    b'{"captured_at": "2026-09-24T21:15:17"}', b'{"captured_at": 5}', b'{"other": "field"}',
    b'{"captured_at": "2026-09-26T00:00:00+00:00"}',  # later than the run: cannot be a used capture
    DEEPLY_NESTED_MARK,
], ids=["empty", "truncated", "list", "naive", "number", "no-field", "future", "deeply-nested"])
def test_an_unusable_mark_is_logged_never_blocks_and_is_replaced_by_the_next_live_capture(
        tmp_path, caplog, content):
    mark = _mark_path()
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_bytes(content)
    path = _deliver(tmp_path / "latest.json", OLDER)
    rc, run, send = _publish(_config(path), caplog)
    assert rc == 0 and run.call_count == 1 and not send.called  # unknown is not proof of regression
    assert "capture mark unusable" in caplog.text
    # The live run's capture became the mark: an even older capture now alerts.
    _deliver(path, OLDEST)
    rc, run, send = _publish(_config(path), caplog)
    assert rc == 0 and len(_alerts(send)) == 1 and BACKWARDS in _alerts(send)[0]


def test_a_mark_that_cannot_be_saved_never_blocks_the_publish(tmp_path, caplog):
    mark = _mark_path()
    mark.parent.parent.mkdir(parents=True, exist_ok=True)
    mark.parent.write_text("a file where the state directory should be")
    rc, run, send = _publish(_config(_deliver(tmp_path / "latest.json", NEWER)), caplog)
    assert rc == 0 and run.call_count == 1 and not send.called
    assert "capture mark not saved" in caplog.text


# ── The rule itself, at readiness's own seam ──
def _loaded(captured: str) -> EconDeltaSnapshot:
    return EconDeltaSnapshot(updated_at=_at(captured), sources_status={}, data={})


def test_readiness_calls_an_older_capture_than_the_last_used_one_backwards_even_when_it_is_also_old():
    now = RUN_AT
    result = assess(_loaded("2026-09-22T20:56:00Z"), persisted_rows=[], now=now, last_capture=_at(NEWER))
    assert result.state == "degraded" and result.snapshot_problem == "capture went backwards"
    assert ("snapshot capture went backwards (2026-09-23 02:56:00 BDT is older than "
            "2026-09-25 03:15:17 BDT, already read by a live run that passed readiness)") in result.reasons
    assert "snapshot capture is more than one day old" in result.reasons  # the age is still stated


@pytest.mark.parametrize("last_capture", [None, NEWER, OLDER], ids=["no-mark", "same-capture", "older-mark"])
def test_readiness_sees_no_regression_unless_the_capture_is_older_than_the_last_used_one(last_capture):
    mark = _at(last_capture) if last_capture is not None else None
    result = assess(_loaded(NEWER), persisted_rows=[], now=RUN_AT, last_capture=mark)
    assert result.snapshot_problem is None
    assert not [reason for reason in result.reasons if "went backwards" in reason]


def test_the_last_used_capture_is_compared_as_an_instant_not_as_wall_clock_text():
    # 03:15:17 BDT and 21:15:17 UTC the day before are the same instant: not a regression.
    same_instant = datetime(2026, 9, 25, 3, 15, 17, tzinfo=timezone(timedelta(hours=6)))
    result = assess(_loaded(NEWER), persisted_rows=[], now=RUN_AT, last_capture=same_instant)
    assert result.snapshot_problem is None
