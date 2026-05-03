"""Builder: NBR revenue composition — monthly last-known."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_SPEC = (
    ("nbr_vat_bn",     "VAT",     "BDT bn", "NBR"),
    ("nbr_it_bn",      "Income Tax", "BDT bn", "NBR"),
    ("nbr_customs_bn", "Customs", "BDT bn", "NBR"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    for mid, label, unit, source in _SPEC:
        last = ctx.history.get_latest(mid) if ctx.history is not None else None
        metrics.append(Metric(
            id=mid, label=label,
            value=(last.value if last else None), unit=unit,
            as_of=(last.as_of if last else ctx.today),
            source=source, cadence="monthly",
        ))
    return SectionData(
        id="nbr", title="NBR Revenue", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today, section_id="nbr"),
    )
