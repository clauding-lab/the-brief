"""Builder: Policy & Rates (Bangladesh Bank).

Policy/SDF/SLF are event-cadence rates read LIVE from Supabase metric_history
(EconDelta re-stamps them daily, so their as_of is a restamp date, NOT a
decision date — cadence stays "event" and freshness stays "fresh"). Reserves
is weekly from the EconDelta snapshot, with metric_history as the backfill.
"""
from __future__ import annotations

from datetime import date

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext

# Last-known BB policy corridor. Used ONLY when metric_history is unreachable
# (history client absent) or a given rate row is missing/non-numeric. A metric
# sourced from these constants is marked stale=True, so an outage never blanks
# the corridor nor presents a possibly-outdated rate as current. Live values
# come from metric_history ids policy_rate_repo / policy_rate_sdf / policy_rate_slf.
_FALLBACK_POLICY_RATE_PCT = 10.0
_FALLBACK_SDF_PCT = 7.5
_FALLBACK_SLF_PCT = 11.5

_BB_URL = "https://www.bb.org.bd/"


def _rate_metric(
    ctx: BuilderContext,
    *,
    metric_id: str,
    history_id: str,
    label: str,
    fallback: float,
) -> Metric:
    """Build one corridor metric, read live from metric_history.

    Falls back to the module last-known constant AND marks the metric
    stale=True when the history client is absent or the rate row is
    missing/non-numeric — a metric_history outage never blanks the corridor
    nor lies about it. cadence stays "event": these are standing rates whose
    daily-restamped as_of is not a decision date, so freshness reads "fresh".
    """
    row = ctx.history.get_latest(history_id) if ctx.history is not None else None
    if row is not None and isinstance(row.value, (int, float)):
        return Metric(
            id=metric_id,
            label=label,
            value=float(row.value),
            unit="%",
            as_of=row.as_of,  # internal only — Section.tsx does not render per-metric as_of
            source="BB",
            source_url=_BB_URL,
            cadence="event",
        )
    return Metric(
        id=metric_id,
        label=label,
        value=fallback,
        unit="%",
        as_of=ctx.today,
        source="BB",
        source_url=_BB_URL,
        cadence="event",
        stale=True,
    )


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = [
        _rate_metric(ctx, metric_id="bb_policy_rate", history_id="policy_rate_repo",
                     label="Policy Rate", fallback=_FALLBACK_POLICY_RATE_PCT),
        _rate_metric(ctx, metric_id="bb_sdf", history_id="policy_rate_sdf",
                     label="SDF", fallback=_FALLBACK_SDF_PCT),
        _rate_metric(ctx, metric_id="bb_slf", history_id="policy_rate_slf",
                     label="SLF", fallback=_FALLBACK_SLF_PCT),
    ]

    reserves_val = ctx.snapshot.get("gross_reserves_usd_bn")
    reserves_as_of_str = ctx.snapshot.get("reserves_date")
    try:
        reserves_as_of = (
            date.fromisoformat(reserves_as_of_str) if reserves_as_of_str else ctx.today
        )
    except ValueError:
        reserves_as_of = ctx.today

    # Snapshot empty? Fall back to the last LIVE reading from metric_history.
    # The live id is `gross_reserves_usd_bn` (matches fx.py); the legacy
    # `bb_gross_reserves` id has had no writer since 2026-03-01 — do NOT read it.
    # A value sourced from history is marked stale=True.
    is_stale = False
    if reserves_val is None and ctx.history is not None:
        last = ctx.history.get_latest("gross_reserves_usd_bn")
        if last is not None:
            reserves_val = last.value
            reserves_as_of = last.as_of
            is_stale = True

    # No WoW delta: `gross_reserves_usd_bn` is re-stamped, so get_latest() returns
    # TODAY's value (a fabricated ~0 delta). An honest week-ago prior would need a
    # second get_history_window call, which breaks the pipeline's single-batched-
    # call contract (pipeline._enrich_metric_history issues exactly one). We drop
    # the delta rather than fabricate one; sparkline enrichment still attaches
    # Metric.history_values downstream for the trend.
    reserves_metric = Metric(
        id="bb_gross_reserves",  # keep — cadence.fx_reserves_rule keys on this id
        label="Gross Reserves",
        value=reserves_val,
        unit="bn USD",
        as_of=reserves_as_of,
        source="BB",
        source_url=_BB_URL,
        cadence="weekly",
        stale=is_stale,
    )
    metrics.append(reserves_metric)

    # The builder never writes history: EconDelta's aggregate_latest.py upserts
    # every numeric snapshot value (incl. gross_reserves_usd_bn) to metric_history
    # daily at 06:10 BDT. See econdelta/docs/data-contract.md; the no-write
    # invariant is enforced by test_bb.py::test_bb_does_not_write_to_history.
    freshness = section_freshness(metrics, today=ctx.today)
    return SectionData(
        id="bb",
        title="Policy & Rates (Bangladesh Bank)",
        metrics=metrics,
        freshness=freshness,
    )
