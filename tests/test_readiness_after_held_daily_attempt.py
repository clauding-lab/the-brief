"""After EconDelta holds a day, readiness reports the retained capture's true age.

On an Opus hard reject EconDelta keeps the previous accepted `latest.json`
byte-for-byte and writes that night's attempt to `latest.attempt.json`, an
operations receipt the Brief does not read (controller ruling, R2 fix 9). The
retained file's own receipts say its writes succeeded - true, for that older
capture - so only its capture time can tell the Brief the day was held. These
tests pin that the next morning's publish sees an old capture, not a fresh one.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from brief.econdelta import load_snapshot
from brief.readiness import assess
from tests.upstream_liveness import POLLED_UPSTREAM

# 02:56 BDT 27 Sep: last accepted capture. 02:56 BDT 28 Sep: that night's attempt is held.
ACCEPTED_AT = "2026-09-26T20:56:00+00:00"
HELD_ATTEMPT_AT = "2026-09-27T20:56:10+00:00"
MORNING_OF_CAPTURE = datetime(2026, 9, 27, 2, 0, tzinfo=timezone.utc)  # 08:00 BDT 27 Sep
MORNING_AFTER_HOLD = datetime(2026, 9, 28, 2, 0, tzinfo=timezone.utc)  # 08:00 BDT 28 Sep

# Shapes as EconDelta writes them (aggregate_latest.main / _write_held_attempt_receipt).
RETAINED = {
    "schema_version": "3.0", "updated_at": ACCEPTED_AT, "sources_status": POLLED_UPSTREAM, "data": {},
    "observations": {},
    "write_status": {
        "daily": {"status": "ok", "attempted_at": "2026-09-26T20:57:30+00:00",
                  "reason": "rows confirmed"},
        "monthly": {"status": "ok", "attempted_at": "2026-09-26T20:58:00+00:00",
                    "reason": "yield: 8 row(s) written and confirmed by exact readback"},
    },
}
HELD_RECEIPT = {
    "daily": {"status": "skipped", "attempted_at": HELD_ATTEMPT_AT,
              "reason": "daily review held; previous accepted snapshot retained"},
    "monthly": {"status": "failed", "attempted_at": HELD_ATTEMPT_AT,
                "reason": "yield: readback failed (write unconfirmed): writer reported 8 row(s)"},
}


def _retained_snapshot(tmp_path: Path, sidecar: str | None) -> Path:
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps(RETAINED))
    if sidecar is not None:
        latest.with_suffix(".attempt.json").write_text(sidecar)
    return latest


def test_the_capture_retained_through_a_held_night_is_reported_by_its_age(tmp_path):
    snapshot = load_snapshot(_retained_snapshot(tmp_path, json.dumps(HELD_RECEIPT)))
    result = assess(snapshot, persisted_rows=[], now=MORNING_AFTER_HOLD)
    assert snapshot.updated_at == datetime.fromisoformat(ACCEPTED_AT)
    assert (result.state, result.reasons, result.snapshot_problem) == (
        "degraded", ("snapshot capture is more than one day old",), "stale capture")


def test_the_same_capture_is_ready_on_the_morning_it_was_taken(tmp_path):
    """Control: nothing but the capture's age separates the two mornings."""
    snapshot = load_snapshot(_retained_snapshot(tmp_path, json.dumps(HELD_RECEIPT)))
    result = assess(snapshot, persisted_rows=[], now=MORNING_OF_CAPTURE)
    assert (result.state, result.reasons, result.snapshot_problem) == ("ready", (), None)


@pytest.mark.parametrize("sidecar", [None, json.dumps(HELD_RECEIPT), '{"daily": {"sta'],
                         ids=["absent", "held-receipt", "truncated"])
def test_the_operations_receipt_never_changes_what_the_brief_reads(tmp_path, sidecar):
    snapshot = load_snapshot(_retained_snapshot(tmp_path, sidecar))
    result = assess(snapshot, persisted_rows=[], now=MORNING_AFTER_HOLD)
    assert (snapshot.updated_at, snapshot.write_status) == (
        datetime.fromisoformat(ACCEPTED_AT), RETAINED["write_status"])
    assert (result.state, result.snapshot_problem) == ("degraded", "stale capture")


# A capture accepted off schedule the previous afternoon (a manual run, or a Persistent=true
# catch-up fire of econdelta-aggregate.timer after downtime), then the scheduled night is held.
# At the 08:00 BDT publish it is under 24 hours old, so its age alone cannot reveal the hold;
# its Bangladesh capture day can: the edition is dated 28 Sep, the capture 27 Sep (R2 fix 9 r1).
AFTERNOON_CAPTURE_AT = "2026-09-27T08:00:00+00:00"  # 14:00 BDT 27 Sep
EARLIER_DAY_REASON = "snapshot capture is from an earlier Bangladesh day (2026-09-27 BDT)"


def _captured_at(tmp_path: Path, updated_at: str) -> Path:
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps({**RETAINED, "updated_at": updated_at}))
    latest.with_suffix(".attempt.json").write_text(json.dumps(HELD_RECEIPT))
    return latest


def test_an_afternoon_capture_retained_through_a_held_night_is_not_todays_capture(tmp_path):
    snapshot = load_snapshot(_captured_at(tmp_path, AFTERNOON_CAPTURE_AT))
    result = assess(snapshot, persisted_rows=[], now=MORNING_AFTER_HOLD)
    assert (MORNING_AFTER_HOLD - snapshot.updated_at).total_seconds() < 86400  # age alone passes
    assert (result.state, result.reasons, result.snapshot_problem) == (
        "degraded", (EARLIER_DAY_REASON,), "earlier-day capture")


@pytest.mark.parametrize("updated_at,now,expected", [
    # 23:59 BDT 27 Sep read at 00:01 BDT 28 Sep: two minutes old, but yesterday's capture.
    ("2026-09-27T17:59:00+00:00", datetime(2026, 9, 27, 18, 1, tzinfo=timezone.utc),
     ("degraded", ("snapshot capture is from an earlier Bangladesh day (2026-09-27 BDT)",),
      "earlier-day capture")),
    # 00:01 BDT 28 Sep read at 08:00 BDT 28 Sep: different UTC dates, same Bangladesh day.
    ("2026-09-27T18:01:00+00:00", MORNING_AFTER_HOLD, ("ready", (), None)),
    # The scheduled 03:15 BDT retry capture on the publish morning is today's capture.
    ("2026-09-27T21:15:30+00:00", MORNING_AFTER_HOLD, ("ready", (), None)),
], ids=["two-minutes-old-across-dhaka-midnight", "same-dhaka-day-across-utc-midnight",
        "scheduled-retry-capture"])
def test_the_capture_day_is_read_on_the_dhaka_calendar(tmp_path, updated_at, now, expected):
    result = assess(load_snapshot(_captured_at(tmp_path, updated_at)), persisted_rows=[], now=now)
    assert (result.state, result.reasons, result.snapshot_problem) == expected


def test_the_earlier_day_alert_says_the_old_snapshot_was_read_not_that_it_is_a_day_old():
    """cli.py alerts on any snapshot_problem; the message must tell this cause truthfully."""
    from brief.snapshot_alert import alert_snapshot_problem
    with patch("brief.alerts.send_discord_alert", return_value=True) as send:
        assert alert_snapshot_problem("earlier-day capture", dry_run=False) is True
    (message,) = send.call_args.args
    assert message.startswith("ALERT: The Brief is publishing from an EconDelta snapshot captured "
                              "on an earlier Bangladesh day (degraded) — cause: earlier-day capture.")
    assert "more than one day ago" not in message
    assert "saved history" not in message and "could not be used" not in message
