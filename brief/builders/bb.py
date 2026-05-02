"""Builder: Policy & Rates (Bangladesh Bank).

Policy/SDF/SLF are event-cadence rates; reserves is weekly from EconDelta.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from brief.cadence import section_freshness
from brief.schema import Delta, Metric, SectionData
from . import BuilderContext

# Event-cadence rates — source of truth is BB MPC. Updated via migration when MPC moves.
_POLICY_RATE_PCT = 10.0
_SDF_PCT = 8.5
_SLF_PCT = 11.5
_RATES_AS_OF = date(2026, 4, 18)   # latest MPC decision date; event-cadence


def _reserves_delta(current: float, history_row: HistoryRow | None) -> Delta | None:
    if history_row is None:
        return None
    try:
        prev = float(history_row.value)
    except (TypeError, ValueError):
        return None
    diff = round(current - prev, 4)
    return Delta(
        value=diff,
        direction="up" if diff > 0 else "down" if diff < 0 else "flat",
        window="wow",
    )


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = [
        Metric(id="bb_policy_rate", label="Policy Rate", value=_POLICY_RATE_PCT,
               unit="%", as_of=_RATES_AS_OF, source="BB",
               source_url="https://www.bb.org.bd/", cadence="event"),
        Metric(id="bb_sdf", label="SDF", value=_SDF_PCT,
               unit="%", as_of=_RATES_AS_OF, source="BB",
               source_url="https://www.bb.org.bd/", cadence="event"),
        Metric(id="bb_slf", label="SLF", value=_SLF_PCT,
               unit="%", as_of=_RATES_AS_OF, source="BB",
               source_url="https://www.bb.org.bd/", cadence="event"),
    ]

    reserves_val = ctx.snapshot.get("gross_reserves_usd_bn")
    reserves_as_of_str = ctx.snapshot.get("reserves_date")
    try:
        reserves_as_of = (
            date.fromisoformat(reserves_as_of_str) if reserves_as_of_str else ctx.today
        )
    except ValueError:
        reserves_as_of = ctx.today

    prev = (
        ctx.history.get_latest("bb_gross_reserves")
        if (ctx.history is not None and reserves_val is not None)
        else None
    )

    reserves_metric = Metric(
        id="bb_gross_reserves",
        label="Gross Reserves",
        value=reserves_val,
        unit="bn USD",
        as_of=reserves_as_of,
        source="BB",
        source_url="https://www.bb.org.bd/",
        cadence="weekly",
        delta=_reserves_delta(reserves_val, prev) if reserves_val is not None else None,
    )
    metrics.append(reserves_metric)

    # NOTE: Historical persistence of bb_gross_reserves moved upstream to
    # EconDelta's aggregate_latest.py (utils/supabase_writer) — every numeric
    # snapshot value is now upserted to metric_history at 06:10 BDT daily.
    # See econdelta/docs/data-contract.md.

    freshness = section_freshness(metrics, today=ctx.today)
    return SectionData(
        id="bb",
        title="Policy & Rates (Bangladesh Bank)",
        metrics=metrics,
        freshness=freshness,
    )
