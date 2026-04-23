from datetime import date, datetime, timezone, timedelta

from brief.cadence import is_bd_trading_day, trading_days_between


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
