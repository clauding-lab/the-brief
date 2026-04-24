"""Builder: Iran War / Oil — daily commodity prices from EconDelta + BankerRead-worthy."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


@dataclass(frozen=True)
class OilEvent:
    date: date
    label: str
    hot: bool


OIL_EVENTS: tuple[OilEvent, ...] = (
    OilEvent(date(2026, 4, 2), "IAEA report", False),
    OilEvent(date(2026, 4, 11), "OPEC+ hold", False),
    OilEvent(date(2026, 4, 21), "Hormuz tanker", True),
)


def build(ctx: BuilderContext) -> SectionData:
    src = "EconDelta"
    metrics = [
        Metric(id="iranwar_brent_spot", label="Brent spot",
               value=ctx.snapshot.get("brent_crude_usd_barrel"),
               unit="USD/bbl", as_of=ctx.today, source=src, cadence="daily"),
        Metric(id="iranwar_wti_spot", label="WTI spot",
               value=ctx.snapshot.get("wti_crude_usd_barrel"),
               unit="USD/bbl", as_of=ctx.today, source=src, cadence="daily"),
    ]
    section = SectionData(
        id="iranwar", title="Iran War & Oil", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
    section.extras["oil_events"] = list(OIL_EVENTS)
    return section
