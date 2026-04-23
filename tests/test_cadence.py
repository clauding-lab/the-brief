from datetime import date, datetime, timezone, timedelta

from brief.cadence import is_bd_trading_day, metric_freshness, trading_days_between
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
    m = _m("x", date(2026, 4, 19), "daily")  # Sunday
    # Trading days between Sun 04-19 and Wed 04-22 = Mon,Tue,Wed = 3 → stale? spec says >2 trading days
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


def test_monthly_fresh_under_35_days():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 3, 20), "monthly")
    assert metric_freshness(m, today=today) == "fresh"


def test_monthly_stale_over_45_days():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 2, 20), "monthly")
    assert metric_freshness(m, today=today) == "stale"


def test_event_always_fresh():
    today = date(2026, 4, 21)
    m = _m("x", date(2025, 1, 1), "event")
    assert metric_freshness(m, today=today) == "fresh"


def test_metric_with_none_value_is_unavailable():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 4, 20), "daily", value=None)
    assert metric_freshness(m, today=today) == "unavailable"
