"""Cadence + freshness computation for The Brief.

BD trading week is Sun–Thu. `fresh` thresholds are cadence-specific;
trading-day awareness applies only to `daily`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable, cast

from brief.schema import CadenceKind, FreshnessKind, Metric, SectionData

_BDT = timezone(timedelta(hours=6))

# Sun=6, Mon=0, Tue=1, Wed=2, Thu=3 → BD trading days
_BD_TRADING_WEEKDAYS = {6, 0, 1, 2, 3}

# ---------------------------------------------------------------------------
# Sections that have NO legacy backfill source.
# When all their metrics have value=None (empty history), they emit
# "warming_up" instead of "unavailable" — signalling intentional accumulation,
# not a data error. Expected to resolve after ~7 V4 pipeline runs.
# ---------------------------------------------------------------------------
SECTIONS_WITHOUT_LEGACY_BACKFILL: frozenset[str] = frozenset({
    "banking", "macro", "dam", "remit", "fiscal"
})


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


def metric_aging(metric: Metric, *, today: date | None = None) -> bool:
    """True when the metric is past its fresh threshold but not yet stale.

    Surfaces in the render layer as an "AGING" chip — signal that the
    reading is older than ideal but still usable. False for fresh, stale,
    unavailable, and pending states (and for value=None metrics).
    """
    return metric_freshness(metric, today=today) == "warning"


def section_freshness(
    metrics: Iterable[Metric],
    *,
    today: date | None = None,
    section_id: str | None = None,
) -> FreshnessKind:
    """Section freshness = worst metric freshness (spec §4).

    section_id — when provided and the section belongs to
    SECTIONS_WITHOUT_LEGACY_BACKFILL, "unavailable" is promoted to
    "warming_up".  This signals intentional history accumulation rather than
    a data error.  All other rankings (stale, warning, …) are unchanged.
    """
    states = [metric_freshness(m, today=today) for m in metrics]
    # "pending" is reserved for externally-set overrides (e.g. a metric whose
    # next-release window has not passed yet); metric_freshness does not emit
    # it today but the priority tuple retains the slot for future/upstream use.
    for worst in ("unavailable", "stale", "pending", "warning"):
        if worst in states:
            if worst == "unavailable" and section_id in SECTIONS_WITHOUT_LEGACY_BACKFILL:
                return "warming_up"
            return cast(FreshnessKind, worst)
    return "fresh"


# ---------------------------------------------------------------------------
# Systemic-risk rules — deterministic predicates that fire `risk_active=True`
# on a section when satisfied. The Call 5 (systemic_risk_callout) prompt only
# runs for sections where one rule fires.
# ---------------------------------------------------------------------------
from typing import Callable

RiskRule = Callable[[SectionData], tuple[bool, str, str]]


def _by_id(metrics: list[Metric], metric_id: str) -> Metric | None:
    return next((m for m in metrics if m.id == metric_id), None)


def banking_npl_rule(section: SectionData) -> tuple[bool, str, str]:
    npl = _by_id(section.metrics, "banking_npl_pct")
    if npl is None or not isinstance(npl.value, (int, float)):
        return (False, "warning", "banking_npl")
    if npl.value >= 30.0:
        return (True, "critical", "banking_npl_above_30")
    if npl.value >= 20.0:
        return (True, "warning", "banking_npl_above_20")
    return (False, "warning", "banking_npl")


def fx_reserves_rule(section: SectionData) -> tuple[bool, str, str]:
    res = _by_id(section.metrics, "bb_gross_reserves")
    if res is None or not isinstance(res.value, (int, float)):
        return (False, "warning", "fx_reserves")
    if res.value < 32.0:
        return (True, "critical", "fx_reserves_below_32bn")
    if res.value < 34.0:
        return (True, "warning", "fx_reserves_below_34bn")
    return (False, "warning", "fx_reserves")


def fx_usd_bdt_rule(section: SectionData) -> tuple[bool, str, str]:
    fx = _by_id(section.metrics, "fx_usd_bdt")
    if fx is None or not isinstance(fx.value, (int, float)):
        return (False, "warning", "fx_usd_bdt")
    if fx.value > 124.0:
        return (True, "critical", "fx_usd_bdt_above_124")
    return (False, "warning", "fx_usd_bdt")


SECTION_RULES: dict[str, list[RiskRule]] = {
    "banking": [banking_npl_rule],
    "bb":      [fx_reserves_rule],
    "fx":      [fx_usd_bdt_rule, fx_reserves_rule],
}


def evaluate_risk_rules(section: SectionData) -> tuple[bool, str | None, str | None]:
    """Return (risk_active, level, rule_id). First-fired rule wins (in declared order)."""
    for rule in SECTION_RULES.get(section.id, []):
        fired, level, rid = rule(section)
        if fired:
            return (True, level, rid)
    return (False, None, None)
