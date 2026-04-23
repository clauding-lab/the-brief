"""Cadence + freshness computation for The Brief.

BD trading week is Sun–Thu. `fresh` thresholds are cadence-specific;
trading-day awareness applies only to `daily`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from brief.schema import CadenceKind, FreshnessKind, Metric

_BDT = timezone(timedelta(hours=6))

# Sun=6, Mon=0, Tue=1, Wed=2, Thu=3 → BD trading days
_BD_TRADING_WEEKDAYS = {6, 0, 1, 2, 3}


def now_bdt() -> datetime:
    """Clock seam for tests — replace via monkeypatch."""
    return datetime.now(_BDT)


def is_bd_trading_day(d: date) -> bool:
    return d.weekday() in _BD_TRADING_WEEKDAYS


def trading_days_between(start: date, end: date) -> int:
    """Count BD trading days strictly between start and end (inclusive of end, excluding start)."""
    if end <= start:
        return 0
    count = 0
    cur = start + timedelta(days=1)
    while cur <= end:
        if is_bd_trading_day(cur):
            count += 1
        cur += timedelta(days=1)
    return count


# ── cadence thresholds (spec §6) ──────────────────────────────────────────────
_THRESHOLDS = {
    # cadence: (fresh_max, warning_max)   # stale if > warning_max
    "weekly":    (7, 10),
    "monthly":   (35, 45),
    "quarterly": (95, 120),
}


def metric_freshness(metric: Metric, *, today: date | None = None) -> FreshnessKind:
    """Freshness per spec §6. Trading-day-aware for daily cadence only."""
    if today is None:
        today = now_bdt().date()

    # None check runs before event: an unset event metric is "unavailable", not "fresh"
    if metric.value is None:
        return "unavailable"

    if metric.cadence == "event":
        return "fresh"

    if metric.cadence == "daily":
        gap = trading_days_between(metric.as_of, today)
        if gap <= 1:
            return "fresh"
        if gap <= 2:
            return "warning"
        return "stale"

    if metric.cadence in _THRESHOLDS:
        days = (today - metric.as_of).days
        fresh_max, warn_max = _THRESHOLDS[metric.cadence]
        if days <= fresh_max:
            return "fresh"
        if days <= warn_max:
            return "warning"
        return "stale"

    # Unknown cadence — conservative
    return "unavailable"
