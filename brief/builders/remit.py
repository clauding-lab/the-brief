"""Builder: Remittance — monthly cadence; last-known from history."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


def build(ctx: BuilderContext) -> SectionData:
    last_mn = ctx.history.get_latest("remit_monthly_mn") if ctx.history else None
    last_yoy = ctx.history.get_latest("remit_yoy_pct") if ctx.history else None

    metrics = [
        Metric(
            id="remit_monthly_mn", label="Monthly Remittance",
            value=(last_mn.value if last_mn else None), unit="mn USD",
            as_of=(last_mn.as_of if last_mn else ctx.today),
            source="BB (publictn/5/27)", cadence="monthly",
        ),
        Metric(
            id="remit_yoy_pct", label="YoY %", value=(last_yoy.value if last_yoy else None),
            unit="%", as_of=(last_yoy.as_of if last_yoy else ctx.today),
            source="BB", cadence="monthly",
        ),
    ]
    return SectionData(
        id="remit", title="Remittance", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
