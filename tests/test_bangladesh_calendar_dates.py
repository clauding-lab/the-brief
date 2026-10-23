"""The Brief reads a Bangladesh-dated record against the Bangladesh date of its capture.

EconDelta's aggregate captures the day's bb_forex rate before UTC midnight (about 02:56
BDT), dated by the Dhaka calendar. Comparing that date with the capture's UTC date made
the reader reject the day's USD/BDT reading. A genuinely future date is still rejected,
and a family not dated by the Bangladesh calendar keeps the UTC comparison. The cases are
shared, byte for byte, with EconDelta (tests/fixtures/contracts/brief-observations-v1.json).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from brief.econdelta import EconDeltaSnapshot
from tests.upstream_liveness import POLLED_UPSTREAM

CONTRACT = json.loads((Path(__file__).parent / "fixtures/contracts/brief-observations-v1.json").read_text())
BD_CONTRACT = CONTRACT["bangladesh_calendar_contract"]
RUN_0256 = datetime(2026, 9, 24, 20, 56, tzinfo=timezone.utc)  # 02:56 BDT on 25 Sep
TODAY = date(2026, 9, 25)  # The Brief's 08:00 BDT publish day


def snapshot(record: dict) -> EconDeltaSnapshot:
    mid = record["metric_id"]
    return EconDeltaSnapshot(updated_at=RUN_0256, sources_status=POLLED_UPSTREAM, data={mid: record["value"]},
                             observations={mid: record})


def forex(**changes) -> dict:
    return {**BD_CONTRACT["cases"][0]["record"], **changes}  # usd_bdt_mid, captured 01:35 BDT 25 Sep


def test_the_reader_names_the_same_bangladesh_calendar_sources_as_the_producer_contract():
    from brief.econdelta import BANGLADESH_CALENDAR_SOURCES

    assert sorted(BANGLADESH_CALENDAR_SOURCES) == BD_CONTRACT["sources"]


@pytest.mark.parametrize("case", BD_CONTRACT["cases"], ids=lambda c: c["case_id"])
def test_each_shared_boundary_case_gets_the_contract_verdict(case):
    record = case["record"]
    accepted = snapshot(record).observation(record["metric_id"],
                                            today=date.fromisoformat(case["brief_today"]))
    assert (accepted == record) is case["consumer_accepted"]


def test_the_brief_day_still_caps_a_bangladesh_dated_record():
    """A replay for 24 Sep must not accept a reading dated 25 Sep, whatever its capture."""
    assert snapshot(forex()).observation("usd_bdt_mid", today=date(2026, 9, 24)) is None


@pytest.mark.parametrize("as_of,captured_at,accepted", [
    # Yesterday's file (01:35 BDT on 24 Sep) still carries its own Dhaka day: dated evidence.
    ("2026-09-24", "2026-09-23T19:35:00+00:00", True),
    # Captured 16:00 BDT on 23 Sep but dated 24 Sep: after its own capture day.
    ("2026-09-24", "2026-09-23T10:00:00+00:00", False),
], ids=["dated-its-capture-day", "dated-after-its-capture-day"])
def test_an_older_capture_is_bound_by_its_own_dhaka_day(as_of, captured_at, accepted):
    """Mirrors EconDelta's producer rule for a reading captured on an earlier day."""
    record = forex(as_of=as_of, captured_at=captured_at)
    assert (snapshot(record).observation("usd_bdt_mid", today=TODAY) == record) is accepted


@pytest.mark.parametrize("source", ["commodity_prices", "archive", "usd_bdt_mid"])
def test_a_record_not_dated_by_the_bangladesh_calendar_keeps_the_utc_comparison(source):
    """Same date and capture as the day's forex reading, but another producer source."""
    assert snapshot(forex(source=source)).observation("usd_bdt_mid", today=TODAY) is None


def test_a_writer_confirmation_is_still_dated_by_its_captures_own_utc_day():
    """Corridor confirmations carry the UTC date prefix of the parse capture (EconDelta
    from_snapshot), not a Bangladesh calendar day: 24 Sep is accepted for a 01:45 BDT
    25 Sep parse, and a 25 Sep confirmation date is still rejected (fix #1 contract)."""
    record = CONTRACT["writer_confirmation_contract"]["records"][0]["expected"]
    mid = record["metric_id"]
    assert snapshot(record).writer_confirmation(mid, today=TODAY).confirmed_on == date(2026, 9, 24)
    assert snapshot({**record, "as_of": "2026-09-25"}).writer_confirmation(mid, today=TODAY) is None


def test_the_days_usd_bdt_reading_reaches_readiness_as_a_current_reading():
    """Readiness at 08:00 BDT neither lists the day's USD/BDT as unavailable nor as a
    contradiction when the fx card prints that record."""
    from brief.readiness import assess
    from brief.schema import Metric

    record = forex()
    card = Metric(id="fx_usd_bdt_mid", label="USD/BDT", value=record["value"], unit="BDT",
                  as_of=date(2026, 9, 25), source="bb_forex", cadence="daily")
    snap = snapshot(record)
    receipt = {"status": "ok", "attempted_at": RUN_0256.isoformat()}
    snap = EconDeltaSnapshot(updated_at=snap.updated_at, sources_status=POLLED_UPSTREAM, data=snap.data,
                             observations=snap.observations,
                             write_status={"daily": receipt, "monthly": receipt})
    result = assess(snap, persisted_rows=[card], now=datetime(2026, 9, 25, 2, tzinfo=timezone.utc))
    assert (result.state, result.reasons, result.unavailable) == ("ready", (), ())
