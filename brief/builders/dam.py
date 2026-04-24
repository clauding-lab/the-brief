"""Builder: DAM weekly food prices — history-backed; scraper lands in a follow-up PR."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_ITEMS = (
    ("dam_rice_coarse",   "Rice (coarse)", "BDT/kg"),
    ("dam_rice_fine",     "Rice (fine)",   "BDT/kg"),
    ("dam_lentil",        "Red lentil",    "BDT/kg"),
    ("dam_oil",           "Soybean oil",   "BDT/L"),
    ("dam_sugar",         "Sugar",         "BDT/kg"),
    ("dam_onion",         "Onion",         "BDT/kg"),
    ("dam_egg",           "Egg",           "BDT/doz"),
    ("dam_chicken",       "Broiler",       "BDT/kg"),
    ("dam_flour",         "Wheat flour",   "BDT/kg"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    for mid, label, unit in _ITEMS:
        last = ctx.history.get_latest(mid) if ctx.history is not None else None
        metrics.append(Metric(
            id=mid, label=label,
            value=(last.value if last else None), unit=unit,
            as_of=(last.as_of if last else ctx.today),
            source="DAM Bangladesh", cadence="weekly",
        ))
    return SectionData(
        id="dam", title="DAM Food Prices", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
