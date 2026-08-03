"""Builder: Policy & Rates (Bangladesh Bank).

Policy/SDF/SLF are event-cadence rates read LIVE from Supabase metric_history.
EconDelta re-stamps them daily, so their as_of is a restamp date, NOT a decision
date — the section must never present it as "the rate changed on this date"
(AGENTS.md landmine 24). Freshness therefore does not age these off the decision
date; it checks that the WRITER is still alive (a restamp inside the last week)
and falls to "stale" when it is not. Reserves is weekly from the EconDelta
snapshot, with metric_history as the backfill.
"""
from __future__ import annotations

from datetime import date

from brief.cadence import metric_freshness, section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext

# Last-known BB policy corridor, as set by the MPC decision of 2026-07-30 (repo
# and SLF each cut 50bp; SDF held). Used ONLY when metric_history is unreachable
# (history client absent) or a given rate row is missing/non-numeric. A metric
# sourced from these constants is marked stale=True, which now forces the
# section's freshness badge to "stale" (brief/cadence.py) — so an outage never
# blanks the corridor NOR presents a last-known rate as current. Live values
# come from metric_history ids policy_rate_repo / policy_rate_sdf / policy_rate_slf.
#
# THESE GO OUT OF DATE AT EVERY MPC DECISION. Until 2026-08-03 they still held
# the pre-cut 10.0/11.5 — four days after BB's first cut in six years. Update
# them in the same PR that reacts to a corridor move.
_LAST_MPC_DECISION = date(2026, 7, 30)
_FALLBACK_POLICY_RATE_PCT = 9.50
_FALLBACK_SDF_PCT = 7.5
_FALLBACK_SLF_PCT = 11.00

_BB_URL = "https://www.bb.org.bd/"

# Call-money tenor points fed to the editor as prose context (never tiles).
# (id, metric_history id, label)
_CALL_MONEY_TENORS = (
    ("bb_call_money_7d", "call_money_rate_7d", "Call Money · 7-day"),
    ("bb_call_money_14d", "call_money_rate_14d", "Call Money · 14-day"),
)


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
    daily-restamped as_of is not a decision date, so freshness reads "fresh"
    while EconDelta keeps confirming them, and "stale" once it stops (or once
    the fallback constant is what got printed).
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
        # The constant dates from the MPC decision that set it, not from today.
        # Freshness does not depend on this (stale=True already forces "stale"),
        # but stamping today's date on a last-known value would be a lie in the
        # raw payload the editor and the debug dump both read.
        as_of=_LAST_MPC_DECISION,
        source="BB",
        source_url=_BB_URL,
        cadence="event",
        stale=True,
    )


def _money_market_metric(
    ctx: BuilderContext,
    *,
    metric_id: str,
    history_id: str,
    label: str,
) -> Metric | None:
    """Read one money-market rate live from metric_history, or return None.

    Money-market rates are fast daily prints with no meaningful "last-known
    standing value", so a missing/non-numeric row OMITS the metric rather than
    falling back to a constant (which would misrepresent where money trades
    today). Contrast _rate_metric, whose standing corridor rates DO fall back.
    Reads only via get_latest — never get_history_window (landmine 23).
    """
    if ctx.history is None:
        return None
    row = ctx.history.get_latest(history_id)
    if row is None or not isinstance(row.value, (int, float)):
        return None
    return Metric(
        id=metric_id,
        label=label,
        value=float(row.value),
        unit="%",
        as_of=row.as_of,
        source="BB",
        source_url=_BB_URL,
        cadence="daily",
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

    # Overnight call money — where banks actually lend each other cash, read
    # live. Tile #4, grouped with the corridor and ahead of Reserves. Omitted
    # (never faked) when the row is missing — a fast daily rate has no standing
    # fallback value.
    call_money = _money_market_metric(
        ctx,
        metric_id="bb_call_money",
        history_id="call_money_rate",
        label="Overnight Call Money",
    )
    if call_money is not None:
        metrics.append(call_money)

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

    # Tenor curve (7d/14d) — prose context for the term premium. Emitted ONLY
    # alongside the overnight tile (atomic feed): with the overnight present the
    # tile-eligible core is 5, so these land at index >= 5 and never render as
    # tiles. Each still requires its own live row (omit-on-missing).
    if call_money is not None:
        for metric_id, history_id, label in _CALL_MONEY_TENORS:
            tenor = _money_market_metric(
                ctx, metric_id=metric_id, history_id=history_id, label=label
            )
            # Emit a tenor only when it is fresh: an invisible context metric must
            # never drag §02's visible freshness badge, and stale term-structure
            # must not reach the editor. (The overnight tile is NOT gated this way
            # — it is visible/material and should render-and-flag if it goes stale.)
            if tenor is not None and metric_freshness(tenor, today=ctx.today) == "fresh":
                metrics.append(tenor)

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
