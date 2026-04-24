"""Builder: Commodities — gold (from EconDelta), LNG (from history)."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


def build(ctx: BuilderContext) -> SectionData:
    gold_oz = ctx.snapshot.get("gold_usd_oz")

    last_lng = ctx.history.get_latest("comm_lng_jkm") if ctx.history else None
    last_gold_bdt = ctx.history.get_latest("comm_gold_22k_bdt") if ctx.history else None

    metrics = [
        Metric(id="comm_gold_usd_oz", label="Gold", value=gold_oz,
               unit="USD/oz", as_of=ctx.today, source="EconDelta", cadence="daily"),
        Metric(id="comm_gold_22k_bdt", label="Gold 22K",
               value=(last_gold_bdt.value if last_gold_bdt else None),
               unit="BDT/bhori",
               as_of=(last_gold_bdt.as_of if last_gold_bdt else ctx.today),
               source="BAJUS", cadence="daily"),
        Metric(id="comm_lng_jkm", label="LNG JKM",
               value=(last_lng.value if last_lng else None),
               unit="USD/MMBtu",
               as_of=(last_lng.as_of if last_lng else ctx.today),
               source="History", cadence="weekly"),
    ]
    return SectionData(
        id="comm", title="Commodities", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
