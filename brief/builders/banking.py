"""Builder: Banking — quarterly NPL / CAR from history."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


def build(ctx: BuilderContext) -> SectionData:
    last_npl = ctx.history.get_latest("banking_npl_pct") if ctx.history else None
    last_car = ctx.history.get_latest("banking_car_pct") if ctx.history else None
    metrics = [
        Metric(id="banking_npl_pct", label="NPL Ratio",
               value=(last_npl.value if last_npl else None), unit="%",
               as_of=(last_npl.as_of if last_npl else ctx.today),
               source="BB", cadence="quarterly"),
        Metric(id="banking_car_pct", label="CAR",
               value=(last_car.value if last_car else None), unit="%",
               as_of=(last_car.as_of if last_car else ctx.today),
               source="BB", cadence="quarterly"),
    ]
    return SectionData(
        id="banking", title="Banking", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
