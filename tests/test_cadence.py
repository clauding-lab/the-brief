from datetime import date, datetime, timezone, timedelta

from brief.cadence import (
    is_bd_trading_day,
    metric_aging,
    metric_freshness,
    section_freshness,
    trading_days_between,
)
from brief.schema import CadenceKind, Metric


def test_is_bd_trading_day_sunday_true():
    # 2026-04-19 is Sunday (BD trading day)
    assert is_bd_trading_day(date(2026, 4, 19)) is True


def test_is_bd_trading_day_friday_false():
    # 2026-04-17 is Friday (weekend in BD)
    assert is_bd_trading_day(date(2026, 4, 17)) is False


def test_is_bd_trading_day_saturday_false():
    assert is_bd_trading_day(date(2026, 4, 18)) is False


def test_trading_days_between_skips_weekend():
    # Thu 2026-04-16 to Sun 2026-04-19: Thu, Sun = 1 trading day gap
    assert trading_days_between(date(2026, 4, 16), date(2026, 4, 19)) == 1


def test_trading_days_between_same_day_zero():
    assert trading_days_between(date(2026, 4, 20), date(2026, 4, 20)) == 0


def test_trading_days_between_across_week():
    # Sun 2026-04-12 → Sun 2026-04-19 = 5 trading days gap (Mon,Tue,Wed,Thu,Sun)
    assert trading_days_between(date(2026, 4, 12), date(2026, 4, 19)) == 5


def _m(mid: str, as_of: date, cadence: CadenceKind = "daily", value=1.0) -> Metric:
    return Metric(id=mid, label=mid, value=value, unit="x", as_of=as_of,
                  source="t", cadence=cadence)


def test_daily_fresh_within_one_trading_day():
    today = date(2026, 4, 21)  # Tuesday
    m = _m("x", date(2026, 4, 20), "daily")  # Monday
    assert metric_freshness(m, today=today) == "fresh"


def test_daily_warning_at_two_trading_days():
    today = date(2026, 4, 22)  # Wednesday
    m = _m("x", date(2026, 4, 20), "daily")  # Monday
    # Trading days between Mon 04-20 and Wed 04-22 = Tue,Wed = 2 → warning
    assert metric_freshness(m, today=today) == "warning"


def test_daily_stale_at_three_trading_days():
    today = date(2026, 4, 22)  # Wednesday
    m = _m("x", date(2026, 4, 19), "daily")  # Sunday
    # Trading days between Sun 04-19 and Wed 04-22 = Mon,Tue,Wed = 3 → stale (>2 trading days)
    assert metric_freshness(m, today=today) == "stale"


def test_daily_thursday_close_still_fresh_on_saturday():
    # DSE closes Thu; Sat run should see Thursday's value as fresh (0 trading days passed)
    today = date(2026, 4, 18)  # Saturday
    m = _m("dse", date(2026, 4, 16), "daily")  # Thursday
    assert metric_freshness(m, today=today) == "fresh"


def test_weekly_fresh_under_7_days():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 4, 17), "weekly")
    assert metric_freshness(m, today=today) == "fresh"


def test_weekly_stale_over_10_days():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 4, 10), "weekly")
    assert metric_freshness(m, today=today) == "stale"


def test_weekly_warning_at_9_days():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 4, 12), "weekly")  # 9 days → warning (weekly: ≤7 fresh, ≤10 warning, >10 stale)
    assert metric_freshness(m, today=today) == "warning"


def test_monthly_fresh_under_35_days():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 3, 20), "monthly")
    assert metric_freshness(m, today=today) == "fresh"


def test_monthly_stale_over_45_days():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 2, 20), "monthly")
    assert metric_freshness(m, today=today) == "stale"


def test_monthly_warning_at_40_days():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 3, 12), "monthly")  # 40 days → warning (monthly: ≤35 fresh, ≤45 warning, >45 stale)
    assert metric_freshness(m, today=today) == "warning"


# ── event cadence: a writer-liveness check, NOT a value-age check ────────────
# Regression guard for the 2026-08-03 incident: the BB policy rate sat at the
# pre-cut 10.00% for four days after BB cut to 9.50%, and §02's badge read
# "fresh" the whole time — event metrics could not report staleness under any
# circumstance. The fix bounds them on the RESTAMP date (EconDelta re-upserts
# them daily), so a dead writer surfaces while a genuinely-unchanged standing
# rate still reads fresh.

def test_event_fresh_while_the_writer_keeps_restamping():
    """A standing rate that has not MOVED in a year is still fresh, as long as
    EconDelta restamped it recently. Ageing it off the decision date would flag
    a six-year-old policy rate as stale when it is the rate in force."""
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 4, 20), "event")   # restamped yesterday
    assert metric_freshness(m, today=today) == "fresh"


def test_event_warning_when_restamp_lapses_past_a_week():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 4, 12), "event")   # 9 days since restamp
    assert metric_freshness(m, today=today) == "warning"


def test_event_stale_when_the_writer_stops():
    """The bug this closes: with no restamp bound, THIS returned "fresh"."""
    today = date(2026, 4, 21)
    m = _m("x", date(2025, 1, 1), "event")    # writer dead for over a year
    assert metric_freshness(m, today=today) == "stale"


def test_event_fallback_constant_is_stale_even_when_stamped_today():
    """bb.py's corridor fallback marks stale=True. Without honouring that flag
    the restamp check cannot see it — a fallback carries a recent as_of, so it
    would read "fresh" while printing a last-known constant."""
    today = date(2026, 4, 21)
    m = _m("x", today, "event")
    m.stale = True
    assert metric_freshness(m, today=today) == "stale"


def test_event_none_value_still_unavailable_not_stale():
    """The value=None check must keep running BEFORE the event branch."""
    today = date(2026, 4, 21)
    m = _m("x", date(2025, 1, 1), "event", value=None)
    assert metric_freshness(m, today=today) == "unavailable"


def test_metric_with_none_value_is_unavailable():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 4, 20), "daily", value=None)
    assert metric_freshness(m, today=today) == "unavailable"


def test_section_freshness_empty_is_fresh():
    assert section_freshness([]) == "fresh"


def test_section_freshness_worst_unavailable_wins():
    today = date(2026, 4, 21)
    metrics = [
        _m("a", date(2026, 4, 20), "daily"),                      # fresh
        _m("b", date(2026, 4, 20), "daily", value=None),          # unavailable
        _m("c", date(2026, 3, 1), "monthly"),                     # warning/stale
    ]
    assert section_freshness(metrics, today=today) == "unavailable"


def test_section_freshness_stale_beats_warning():
    today = date(2026, 4, 21)
    metrics = [
        _m("a", date(2026, 2, 20), "monthly"),  # stale
        _m("b", date(2026, 3, 20), "monthly"),  # fresh
    ]
    assert section_freshness(metrics, today=today) == "stale"


def test_section_freshness_all_fresh():
    today = date(2026, 4, 21)
    metrics = [
        _m("a", date(2026, 4, 20), "daily"),
        _m("b", date(2026, 4, 15), "weekly"),
    ]
    assert section_freshness(metrics, today=today) == "fresh"


def test_section_freshness_warning_only():
    today = date(2026, 4, 21)
    metrics = [
        _m("a", date(2026, 4, 20), "daily"),     # fresh (1 trading day)
        _m("b", date(2026, 3, 12), "monthly"),   # warning (40 days; monthly: ≤35 fresh, ≤45 warning)
    ]
    assert section_freshness(metrics, today=today) == "warning"


# ── metric_aging ─────────────────────────────────────────────────────────────

def test_metric_aging_false_when_fresh():
    today = date(2026, 4, 21)
    metric = _m("cpi", date(2026, 4, 1), "monthly")  # 20 days < 35 fresh
    assert metric_aging(metric, today=today) is False


def test_metric_aging_true_when_warning_band():
    today = date(2026, 4, 21)
    metric = _m("cpi", date(2026, 3, 12), "monthly")  # 40 days → warning
    assert metric_aging(metric, today=today) is True


def test_metric_aging_false_when_stale():
    today = date(2026, 4, 21)
    metric = _m("cpi", date(2026, 2, 1), "monthly")  # 79 days → stale
    assert metric_aging(metric, today=today) is False


def test_metric_aging_false_when_value_none():
    today = date(2026, 4, 21)
    metric = _m("cpi", date(2026, 3, 12), "monthly", value=None)
    assert metric_aging(metric, today=today) is False


def test_metric_aging_quarterly_warning_band():
    today = date(2026, 4, 21)
    metric = _m("npl", date(2026, 1, 1), "quarterly")  # 110 days → warning (≤120)
    assert metric_aging(metric, today=today) is True
