"""Builder: Iran War / Oil — daily commodity prices from EconDelta + BankerRead-worthy."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext, dated_quote


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
    metrics = []
    for mid, label, key in (
        ("iranwar_brent_spot", "Brent spot", "brent_crude_usd_barrel"),
        ("iranwar_wti_spot", "WTI spot", "wti_crude_usd_barrel"),
    ):
        quote = dated_quote(ctx, key)
        if quote is None:
            continue
        value, observed, source, held = quote
        metrics.append(Metric(id=mid, label=label, value=value, unit="USD/bbl",
                              as_of=observed, source=source, cadence="daily", stale=held))
    section = SectionData(
        id="iranwar", title="Iran War & Oil", metrics=metrics,
        freshness="unavailable" if len(metrics) < 2 else section_freshness(metrics, today=ctx.today),
    )
    section.extras["oil_events"] = list(OIL_EVENTS)
    return section
