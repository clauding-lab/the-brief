"""A healthy quiet day reads "ready" once every monthly leg says why it wrote nothing (R2 fix H4).

EconDelta's yield ladder, EPB exports and reserves writers used to publish a zero-row run as
"no rows written (reason not itemised by this writer)". Unknown is never healthy, so every
quiet day read degraded. They now itemise it. The three leg receipts below are the shared
contract's `monthly_contract.quiet_day_legs`: EconDelta tests/test_quiet_day_leg_receipts.py
regenerates them byte-for-byte from its real writers, so this is the producer's exact shape,
not a hand-written "healthy". They sit in the producer's real nesting (main():
monthly -> chart_appenders -> macro/yield/exports, plus reserves) beside the macro legs of a
caught-up day and CPI/M2 upstream polls that are live (R2 fix H3).
"""
import json
from datetime import timedelta
from pathlib import Path

from tests.test_readiness import NOW
from tests.test_readiness_monthly_lag import DAILY_OK, caught_up, judge, leg_reasons, parent
from tests.upstream_liveness import LIVE_UPSTREAM

QUIET = json.loads((Path(__file__).parent / "fixtures/contracts/brief-observations-v1.json")
                   .read_text())["monthly_contract"]["quiet_day_legs"]
UNITEMISED = "no rows written (reason not itemised by this writer)"  # EconDelta's pre-H4 zero-row reason


def quiet_day(**legs: dict) -> dict:
    """The whole write_status of the quiet day, nested exactly as EconDelta's main() nests it."""
    macro = caught_up()["monthly"]["legs"]["chart_appenders"]["legs"]["macro"]
    own = {**QUIET["legs"], **legs}
    appenders = parent({"macro": macro, "yield": own["yield"], "exports": own["exports"]})
    return {"daily": DAILY_OK, "monthly": parent({"chart_appenders": appenders, "reserves": own["reserves"]})}


def unitemised(name: str) -> dict:
    """The same leg as the pre-H4 writer published it: nothing written, and no reason."""
    return {**QUIET["legs"][name], "reason": UNITEMISED, "skips": []}


def test_a_quiet_day_with_every_monthly_leg_itemised_reads_ready():
    assert QUIET["attempted_at"] == DAILY_OK["attempted_at"]  # so judge() stamps it before NOW
    result = judge(quiet_day(), sources=LIVE_UPSTREAM)

    assert (result.state, result.reasons) == ("ready", ())
    for leg, month in (("yield", "2026-09"), ("exports", "2026-08")):
        assert (f"monthly {leg} leg: official publication lag (BB lists nothing after {month}; "
                "inside its accepted 45-day lag window)") in result.notes


def test_the_same_quiet_day_as_the_pre_h4_writers_published_it_is_degraded_on_those_legs_only():
    result = judge(quiet_day(**{name: unitemised(name) for name in ("yield", "exports")}), sources=LIVE_UPSTREAM)

    assert result.state == "degraded"
    assert leg_reasons(result) == ["monthly yield leg skipped: reason not itemised",
                                   "monthly exports leg skipped: reason not itemised"]


def test_the_quiet_day_lag_is_healthy_only_inside_each_legs_accepted_window():
    later = NOW + timedelta(days=61)  # 25 Nov: past 45 days from both 30 Sep and 31 Aug
    result = judge(quiet_day(), sources=LIVE_UPSTREAM, now=later)

    assert result.state == "degraded"
    for leg, month in (("yield", "2026-09-01"), ("exports", "2026-08-01")):
        assert (f"monthly {leg} leg: no new official period, but its newest recorded month {month} is "
                "past its accepted 45-day lag window (stale since BB published nothing newer)") \
            in leg_reasons(result)
