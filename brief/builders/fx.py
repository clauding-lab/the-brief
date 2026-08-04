"""Builder: FX & External — USD/BDT spot + reserves + trade flows.

Post-2026-05-03: pivoted from a multi-FX-rate card layout (mid/buy/sell/EUR/GBP)
to the V1 mockup's external-balance layout: 1 USD/BDT spot card + 4 cross-
section metrics (gross reserves, trade gap, monthly exports, monthly remittance).

The 4 cross-section metrics are pulled from `metric_history` (last-known) since
they live in BB / external-balance scraper IDs, not the bb_forex daily snapshot.

v1.6.7: Gold moved here from the retired `comm` section. It is a reserve asset,
so it belongs with reserves rather than in a commodities card of its own. EUR/BDT
was dropped in the same change to make room: the editor prompt caps each section
at 5 metrics and EUR/BDT was the one it discarded anyway, so keeping both would
have meant Gold competing for a slot that had no room in it.
"""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_SPOT_SPEC = (
    ("fx_usd_bdt_mid", "USD/BDT mid", "usd_bdt_mid", "BDT"),
)


def _last_known(ctx: BuilderContext, metric_id: str):
    """Return (value, as_of) from metric_history, or (None, today) if absent."""
    if ctx.history is None:
        return None, ctx.today
    last = ctx.history.get_latest(metric_id)
    if last is None:
        return None, ctx.today
    return last.value, last.as_of


def build(ctx: BuilderContext) -> SectionData:
    # ── USD/BDT spot from EconDelta daily snapshot ─────────────────────────
    metrics: list[Metric] = []
    for mid, label, src_key, unit in _SPOT_SPEC:
        metrics.append(Metric(
            id=mid, label=label, value=ctx.snapshot.get(src_key), unit=unit,
            as_of=ctx.today, source="BB",
            source_url="https://www.bb.org.bd/en/index.php/econdata/exchangerate",
            cadence="daily",
        ))

    # ── Gold, from the EconDelta daily snapshot (ex-`comm`) ────────────────
    # Same snapshot path the retired Commodities section used, so the printed
    # number does not change — only where it sits.
    metrics.append(Metric(
        id="fx_gold_usd_oz", label="Gold", value=ctx.snapshot.get("gold_usd_oz"),
        unit="USD/oz", as_of=ctx.today, source="EconDelta", cadence="daily",
    ))

    # ── Cross-section metrics from metric_history ──────────────────────────
    res_v, res_as_of = _last_known(ctx, "gross_reserves_usd_bn")
    metrics.append(Metric(
        id="fx_gross_reserves", label="Gross Reserves", value=res_v, unit="bn USD",
        as_of=res_as_of, source="BB", cadence="weekly",
    ))

    exp_v, exp_as_of = _last_known(ctx, "monthly_export")
    imp_v, _ = _last_known(ctx, "monthly_import")
    metrics.append(Metric(
        id="fx_monthly_exports", label="Monthly Exports", value=exp_v, unit="bn USD",
        as_of=exp_as_of, source="EPB", cadence="monthly",
    ))

    # Trade gap = exports − imports (negative = deficit). Computed only when
    # both legs are present; otherwise null.
    trade_gap = None
    if isinstance(exp_v, (int, float)) and isinstance(imp_v, (int, float)):
        trade_gap = round(exp_v - imp_v, 2)
    metrics.append(Metric(
        id="fx_trade_gap", label="Trade Gap", value=trade_gap, unit="bn USD",
        as_of=exp_as_of, source="EPB · BB", cadence="monthly",
    ))

    # `fx_monthly_remittance` was dropped in v1.6.7. It printed the same BB
    # figure as §11 Remittance's `remit_monthly_mn` — 2.82 bn USD against 2820.0
    # mn USD on 2026-08-04 — so the brief carried one number twice under one
    # label. Dropping the copy, not the original: §11 is the section that exists
    # to report it. This also brings FX to exactly 5 metrics, which is the cap
    # the editor prompt enforces, so every remaining tile renders instead of
    # competing for a slot.

    # Section freshness is driven by the spot rate (the section's primary
    # identity). Cross-section external-balance metrics are supporting context
    # — their staleness must not push the whole section into "stale".
    #
    # Gold joins the badge set deliberately. Both it and the spot rate are
    # stamped with today's date every run, so neither can ever age into "stale"
    # — but a snapshot that stops carrying `gold_usd_oz` yields value=None,
    # which section_freshness reports as "unavailable". Including it keeps the
    # disappearance visible; the retired `comm` section used to provide that
    # signal, and dropping it silently would have been a regression.
    badge_metrics = [
        m for m in metrics if m.id in ("fx_usd_bdt_mid", "fx_gold_usd_oz")
    ]
    return SectionData(
        id="fx",
        title="FX & External",
        metrics=metrics,
        freshness=section_freshness(badge_metrics, today=ctx.today),
    )
