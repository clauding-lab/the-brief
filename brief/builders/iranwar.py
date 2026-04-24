"""Builder: Iran War / Oil — daily commodity prices from EconDelta + BankerRead-worthy."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


def build(ctx: BuilderContext) -> SectionData:
    src = "EconDelta commodity_prices"
    metrics = [
        Metric(id="iranwar_brent_spot", label="Brent spot",
               value=ctx.snapshot.get("brent_crude_usd_barrel"),
               unit="USD/bbl", as_of=ctx.today, source=src, cadence="daily"),
        Metric(id="iranwar_wti_spot", label="WTI spot",
               value=ctx.snapshot.get("wti_crude_usd_barrel"),
               unit="USD/bbl", as_of=ctx.today, source=src, cadence="daily"),
    ]
    return SectionData(
        id="iranwar", title="Iran War & Oil", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
