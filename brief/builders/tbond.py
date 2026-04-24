"""Builder: T-Bill / T-Bond — event-cadence yields, history-driven."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_METRIC_SPEC = (
    ("tbond_tbill_91d",   "91d T-Bill cut-off",  "%",   "BB", "event"),
    ("tbond_tbill_182d",  "182d T-Bill cut-off", "%",   "BB", "event"),
    ("tbond_tbill_364d",  "364d T-Bill cut-off", "%",   "BB", "event"),
    ("tbond_bond_5y",     "5y Govt Bond",        "%",   "BB", "weekly"),
    ("tbond_bond_10y",    "10y Govt Bond",       "%",   "BB", "weekly"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    for mid, label, unit, source, cadence in _METRIC_SPEC:
        last = ctx.history.get_latest(mid) if ctx.history else None
        metrics.append(Metric(
            id=mid, label=label,
            value=(last.value if last else None), unit=unit,
            as_of=(last.as_of if last else ctx.today),
            source=source, cadence=cadence,  # type: ignore[arg-type]
        ))
    return SectionData(
        id="tbond", title="T-Bonds & T-Bills", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
