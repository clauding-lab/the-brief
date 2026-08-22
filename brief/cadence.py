"""Cadence + freshness computation for The Brief.

BD trading week is Sun–Thu. `fresh` thresholds are cadence-specific;
trading-day awareness applies only to `daily`.
"""
from __future__ import annotations

import calendar
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
# "dam" was removed in v1.6.8 along with the builder — see landmine #31.
SECTIONS_WITHOUT_LEGACY_BACKFILL: frozenset[str] = frozenset({
    "banking", "macro", "remit", "fiscal"
})


def now_bdt() -> datetime:
    """Clock seam for tests — replace via monkeypatch."""
    return datetime.now(_BDT)


def is_bd_trading_day(d: date) -> bool:
    return d.weekday() in _BD_TRADING_WEEKDAYS


def month_end(d: date) -> date:
    """Normalize `d` to the last calendar day of its month.

    P0 honesty fix (2026-08-22 audit #204): `metric_history_monthly` rows are
    sometimes stamped at the START of their month (e.g. 2026-07-01 for July's
    official final) rather than its end. Read literally, that ages a fresh
    official read by up to ~30 days under `metric_freshness`'s monthly
    threshold before it should — a same-day publish of July's final would
    already read 43 days old. Callers that read a monthly archive value should
    normalize its `as_of` through this before comparing it to today.
    """
    last_day = calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last_day)


def months_apart(a: date, b: date) -> int:
    """Absolute distance between two dates in whole calendar months.

    Same-month dates (any day) are 0 apart; adjacent months are 1 apart,
    regardless of day-of-month. Used to gate derived metrics (trade gap,
    import cover) that must not silently pair figures from different
    reporting periods.
    """
    return abs((a.year - b.year) * 12 + (a.month - b.month))


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

# `event` cadence covers STANDING values (the BB policy corridor) that hold
# between decisions, so their as_of is a daily RESTAMP date, not a decision date
# (AGENTS.md landmine 24). Ageing them like a periodic series would flag a
# six-year-old policy rate as stale when it is genuinely the rate in force.
#
# But "the as_of means nothing" was read as "never check the as_of", which left
# event metrics unable to report staleness under ANY circumstance. That is the
# wrong invariant: a standing value is only trustworthy while its writer keeps
# CONFIRMING it. If EconDelta stops restamping the corridor, The Brief has no
# evidence the printed rate is still in force — and used to keep printing it as
# "fresh" indefinitely. These bounds are a writer-liveness check, not a
# value-age check: same numbers as `weekly`, because a restamped-daily row that
# has not moved in over a week means the writer is down.
_EVENT_RESTAMP_THRESHOLDS = (7, 10)  # (fresh_max, warning_max) days since restamp


def metric_freshness(metric: Metric, *, today: date | None = None) -> FreshnessKind:
    """Freshness per spec §6. Trading-day-aware for daily cadence only."""
    if today is None:
        today = now_bdt().date()

    # None check runs before event: an unset event metric is "unavailable", not "fresh"
    if metric.value is None:
        return "unavailable"

    if metric.cadence == "event":
        # Fallback-sourced (history unreachable / row missing): the builder
        # already knows this value is last-known rather than confirmed, and
        # stamps as_of=today, so the restamp check below cannot see it. This
        # is STRONGER than the floor below (outright "stale", not merely
        # "warning"), so it stays its own early return.
        if metric.stale:
            return "stale"
        days = (today - metric.as_of).days
        fresh_max, warn_max = _EVENT_RESTAMP_THRESHOLDS
        if days <= fresh_max:
            result: FreshnessKind = "fresh"
        elif days <= warn_max:
            result = "warning"
        else:
            result = "stale"
        return result

    if metric.cadence == "daily":
        gap = trading_days_between(metric.as_of, today)
        if gap <= 1:
            result = "fresh"
        elif gap <= 2:
            result = "warning"
        else:
            result = "stale"
    elif metric.cadence in _THRESHOLDS:
        days = (today - metric.as_of).days
        fresh_max, warn_max = _THRESHOLDS[metric.cadence]
        if days <= fresh_max:
            result = "fresh"
        elif days <= warn_max:
            result = "warning"
        else:
            result = "stale"
    else:
        # Unknown cadence — conservative
        return "unavailable"

    # M-B, review round 2 (2026-08-22 audit #204): `Metric.stale` means "this
    # value came from a fallback, not a confirmed current read" — per its own
    # docstring, for EVERY cadence, not just `event`. Before this fix the flag
    # was inert for daily/weekly/monthly/quarterly: a monthly-cadence fallback
    # (e.g. remit.py's flash-fallback branch, forced to a recent as_of so it
    # never claims "today" — see H5 review round 1) could still land inside
    # the fresh window and ship under a plain "fresh" badge, silently
    # contradicting its own `source` text. Floor at "warning" so a
    # stale-flagged value can never read as unqualified fresh — this also
    # makes `metric_vintage` fire, since it only skips metrics that are
    # genuinely fresh. Never DOWNGRADES an already-worse computed signal.
    if metric.stale and result == "fresh":
        return "warning"
    return result


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
    "warming_up" — but ONLY when EVERY metric in the section is
    "unavailable" (H-B, review round 2, 2026-08-22 audit #204). The
    implementation used to promote whenever "unavailable" was present at
    ALL, contradicting its own docstring above ("when ALL their metrics have
    value=None"): a section with, say, three genuinely stale archive metrics
    and ONE suppressed derived metric (e.g. macro's import cover, gated in
    fx.py/macro.py on data-vintage checks) reported the cheerful
    "history is accumulating" badge instead of the honest "stale" one — at
    ANY size of the underlying data gap, not just the specific one that was
    first caught. When NOT every metric is unavailable, a single "nothing to
    show today" metric must not mask a worse REAL signal from a metric that
    IS reporting — the worst-of ranking runs over the metrics that DO have
    an answer.
    """
    states = [metric_freshness(m, today=today) for m in metrics]
    if not states:
        return "fresh"

    eligible = section_id in SECTIONS_WITHOUT_LEGACY_BACKFILL
    if eligible and all(s == "unavailable" for s in states):
        return "warming_up"
    if eligible:
        # Some metrics DO have an answer — don't let "unavailable" (a
        # single metric with nothing to show) outrank a worse REAL signal
        # from a metric that reported something (e.g. "stale").
        reporting = [s for s in states if s != "unavailable"]
        states = reporting or states

    # "pending" is reserved for externally-set overrides (e.g. a metric whose
    # next-release window has not passed yet); metric_freshness does not emit
    # it today but the priority tuple retains the slot for future/upstream use.
    for worst in ("unavailable", "stale", "pending", "warning"):
        if worst in states:
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
