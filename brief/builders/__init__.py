"""Registry for section builders.

Spine = must ship daily; graceful-stale allowed but never dropped.
Keep  = useful context; may degrade silently to last-known or unavailable.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# v1.6.7 dropped "comm" (Commodities). Its two tiles were Gold and LNG; LNG's
# only live series is a monthly Pink Sheet print that had been dead 105 days
# before v1.6.6 repointed it, and Gold now lives in `fx` as a reserve-asset
# reading. A one-tile section is not a section.
SPINE_BUILDER_IDS: tuple[str, ...] = (
    "bb", "macro", "fx", "dse", "tbond", "iranwar",
    "headlines", "exec",
    "fiscal", "remit",
)

KEEP_BUILDER_IDS: tuple[str, ...] = ("banking",)

ALL_BUILDER_IDS: tuple[str, ...] = SPINE_BUILDER_IDS + KEEP_BUILDER_IDS

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Mapping, Sequence

if TYPE_CHECKING:
    from brief.econdelta import EconDeltaSnapshot
    from brief.history import MetricHistoryClient
    from brief.headlines import Headline


@dataclass(frozen=True)
class BuilderContext:
    snapshot: EconDeltaSnapshot
    history: MetricHistoryClient | None
    today: date
    headlines: Sequence[Headline] = ()
    claude_outputs: Mapping[str, Any] = field(default_factory=dict)
    # v1.4.0 — same client as `history` but callers pass
    # table="metric_history_monthly" per call. Separate field so builders that
    # don't need monthly data don't need to be updated.
    history_monthly: "MetricHistoryClient | None" = None


def official_monthly_bn(ctx: "BuilderContext", metric_id: str, *,
                        table: str = "metric_history_monthly"):
    """Latest official monthly row for `metric_id`, converted mn USD -> bn USD
    (/1000) with `as_of` normalized to month-end.

    Shared by fx.py (exports/imports, trade gap) and macro.py (import cover) —
    both read the same class of BB/EPB "*_usd_mn_monthly" archive series and
    need identical unit + date-stamp handling (P0 honesty fix, 2026-08-22
    audit #204: the pre-fix reads mixed a bn-scale daily flash with these
    mn-scale official finals, and dated an archive row by whichever calendar
    day it happened to be stamped on rather than that month's end).

    Returns None if the client is absent, the row is missing, its value isn't
    numeric, or the read raises — a section going dark must not take the
    builder (or the issue) down; a missing row already renders as
    "unavailable". Every non-success path logs a WARNING naming the metric id
    (M3, review round 1) — a dark archive read must never fail silently.

    Returns FULL float precision (L1, review round 1) — round only when a
    caller assigns a final display value. Rounding here AND again downstream
    (e.g. fx.py's trade-gap subtraction) compounds error twice for no reason.
    """
    from brief.history import HistoryRow, observation_date

    history_monthly = ctx.history_monthly
    if history_monthly is None:
        logger.warning(
            "official_monthly_bn: %s — no history_monthly client available", metric_id,
        )
        return None
    try:
        row = history_monthly.get_latest(metric_id, table=table)
    except Exception:  # noqa: BLE001 — best-effort read, never fatal
        logger.warning(
            "official_monthly_bn: %s — get_latest raised, treating as absent",
            metric_id, exc_info=True,
        )
        return None
    if row is None:
        logger.warning("official_monthly_bn: %s — no row in %s", metric_id, table)
        return None
    if not isinstance(row.value, (int, float)):
        logger.warning(
            "official_monthly_bn: %s — non-numeric value %r, treating as absent",
            metric_id, row.value,
        )
        return None
    observed = observation_date(row, today=ctx.today, monthly=True)
    if row.metric_id != metric_id or observed is None:
        logger.warning("official_monthly_bn: %s — invalid source period", metric_id)
        return None
    return HistoryRow(
        metric_id=row.metric_id,
        as_of=observed,
        value=row.value / 1000,
        source=row.source,
    )


# Producer spells oil USD/barrel; USD/bbl is the same unit, not a scale conversion.
_QUOTE_UNITS = {
    "brent_crude_usd_barrel": ("USD/barrel", "USD/bbl"),
    "wti_crude_usd_barrel": ("USD/barrel", "USD/bbl"),
    "gold_usd_oz": ("USD/oz",),
    "usd_bdt_mid": ("BDT",),
}


def dated_quote(ctx: BuilderContext, metric_id: str) -> tuple[float, date, str, bool] | None:
    """Return a source-bound (value, date, source, held) quote, or None.

    A legacy scalar cannot borrow a date from an equal number. The fallback
    uses the history record's own value and explicit source_as_of together.
    Daily source_as_of is optional; no query requires that column to exist.
    """
    from brief.history import finite_number, observation_date

    item = ctx.snapshot.observation(metric_id, today=ctx.today)
    if item is not None:
        if item.get("unit") not in _QUOTE_UNITS.get(metric_id, ()):
            return None
        return (item["value"], date.fromisoformat(item["as_of"]), item["source"],
                item["quality"] == "held")
    # An explicit rejected/unknown record must not be resurrected from history.
    if metric_id in ctx.snapshot.observations:
        return None
    if ctx.history is None:
        return None
    row = ctx.history.get_latest(metric_id)
    if (row is None or getattr(row, "metric_id", None) != metric_id
            or getattr(row, "source_as_of", None) is None
            or not finite_number(row.value) or not row.source):
        return None
    observed = observation_date(row, today=ctx.today)
    return (row.value, observed, row.source, True) if observed is not None else None
