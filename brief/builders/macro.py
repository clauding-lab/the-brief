"""Builder: Macro (CPI + MPC). Monthly cadence; no EconDelta source today.

Initial release reads last-known from metric_history only. Values land as None
until an EconDelta or dedicated scraper populates them.
"""
from __future__ import annotations


from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_HIST_SPEC = (
    ("macro_cpi_headline", "CPI Headline", "%",       "BBS", "monthly"),
    ("macro_cpi_food",     "CPI Food",     "%",       "BBS", "monthly"),
    ("macro_gdp_growth",   "GDP Growth",   "%",       "BBS", "quarterly"),
    ("macro_credit_growth","Credit Growth","% YoY",   "BB",  "monthly"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    for mid, label, unit, source, cadence in _HIST_SPEC:
        last = ctx.history.get_latest(mid) if ctx.history is not None else None
        value = last.value if last is not None else None
        as_of = last.as_of if last is not None else ctx.today
        metrics.append(Metric(
            id=mid, label=label, value=value, unit=unit,
            as_of=as_of, source=source, cadence=cadence,  # type: ignore[arg-type]
        ))

    return SectionData(
        id="macro",
        title="Macro & Inflation",
        metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
