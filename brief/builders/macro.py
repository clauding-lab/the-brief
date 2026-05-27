"""Builder: Macro (CPI + Policy + REER + Credit + External). Monthly cadence.

Reads 8 banker-essential monthly metrics from metric_history_monthly via
the brief.history client (using the `table` kwarg added in Phase 1).
Computes HistoryFacts via brief.history_anchors and attaches them to the
returned SectionData so the editor can weave them into prose.

Per spec §3.6 — this is the macro section's per-section override on the
5-metric cap; the editor prompt explicitly allows 8 metrics here.

AGENTS.md landmine #1: reads from metric_history_monthly, NOT tb_* tables.
"""
from __future__ import annotations

from typing import Callable

from brief.cadence import section_freshness
from brief.history_anchors import HistoryFact, fetch_and_compute
from brief.schema import Metric, SectionData
from . import BuilderContext


# (metric_id, label, unit, source, format_kind)
_MACRO_METRICS: tuple[tuple[str, str, str, str, str], ...] = (
    ("cpi_12m_avg_monthly",              "CPI 12m Avg",           "%",      "BBS",    "percent-1dp"),
    ("cpi_p2p_food_monthly",             "CPI Food (P-to-P)",     "%",      "BBS",    "percent-1dp"),
    ("cpi_p2p_nonfood_monthly",          "CPI Non-Food (P-to-P)", "%",      "BBS",    "percent-1dp"),
    ("real_policy_rate_monthly",         "Real Policy Rate",      "%",      "BB+BBS", "percent-1dp"),
    ("reer_monthly",                     "REER",                  "index",  "BB",     "comma-2dp"),
    ("private_credit_growth_yoy_monthly","Private Credit YoY",    "%",      "BB",     "percent-1dp"),
    ("m2_growth_yoy_monthly",            "M2 YoY",                "%",      "BB",     "percent-1dp"),
    ("import_cover_months_monthly",      "Import Cover",          "months", "BB",     "comma-1dp"),
)


def _formatter_for(format_kind: str) -> Callable[[float], str]:
    if format_kind == "percent-1dp":
        return lambda v: f"{v:.1f}%"
    if format_kind == "comma-2dp":
        return lambda v: f"{v:,.2f}"
    if format_kind == "comma-1dp":
        return lambda v: f"{v:,.1f}"
    return lambda v: str(v)


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    history_facts: list[HistoryFact] = []

    for mid, label, unit, source, format_kind in _MACRO_METRICS:
        last = (
            ctx.history_monthly.get_latest(mid, table="metric_history_monthly")
            if ctx.history_monthly is not None
            else None
        )
        value = last.value if last is not None else None
        as_of = last.as_of if last is not None else ctx.today
        metrics.append(Metric(
            id=mid,
            label=label,
            value=value,
            unit=unit,
            as_of=as_of,
            source=source,
            cadence="monthly",  # type: ignore[arg-type]
        ))

        if ctx.history_monthly is not None and value is not None:
            facts = fetch_and_compute(
                ctx.history_monthly,
                mid,
                cadence="monthly",
                current_value=value,
                formatter=_formatter_for(format_kind),
            )
            history_facts.extend(facts)

    return SectionData(
        id="macro",
        title="Macro & Inflation",
        metrics=metrics,
        history_facts=history_facts,
        freshness=section_freshness(metrics, today=ctx.today, section_id="macro"),
    )
