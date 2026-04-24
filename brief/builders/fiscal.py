"""Builder: Fiscal — monthly NBR / ADP / borrow from history."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_SPEC = (
    ("fiscal_nbr_collected_trn", "NBR collected YTD", "BDT trn", "NBR"),
    ("fiscal_nbr_target_trn",    "NBR full-year target", "BDT trn", "NBR"),
    ("fiscal_adp_pct",           "ADP utilisation", "%",  "IMED"),
    ("fiscal_govt_borrow_trn",   "Govt bank borrow YTD", "BDT trn", "BB"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    for mid, label, unit, source in _SPEC:
        last = ctx.history.get_latest(mid) if ctx.history else None
        metrics.append(Metric(
            id=mid, label=label,
            value=(last.value if last else None), unit=unit,
            as_of=(last.as_of if last else ctx.today),
            source=source, cadence="monthly",
        ))
    return SectionData(
        id="fiscal", title="Fiscal", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
