"""Builder: FX — daily rates from EconDelta bb_forex."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_SPEC = (
    ("fx_usd_bdt_mid",  "USD/BDT mid",  "usd_bdt_mid",  "BDT"),
    ("fx_usd_bdt_buy",  "USD/BDT buy",  "usd_bdt_buy",  "BDT"),
    ("fx_usd_bdt_sell", "USD/BDT sell", "usd_bdt_sell", "BDT"),
    ("fx_eur_bdt",      "EUR/BDT",      "eur_bdt",      "BDT"),
    ("fx_gbp_bdt",      "GBP/BDT",      "gbp_bdt",      "BDT"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics = [
        Metric(
            id=mid,
            label=label,
            value=ctx.snapshot.get(src_key),
            unit=unit,
            as_of=ctx.today,
            source="BB",
            source_url="https://www.bb.org.bd/en/index.php/econdata/exchangerate",
            cadence="daily",
        )
        for (mid, label, src_key, unit) in _SPEC
    ]
    return SectionData(
        id="fx",
        title="Foreign Exchange",
        metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
