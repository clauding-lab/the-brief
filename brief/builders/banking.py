"""Builder: Banking — quarterly NPL / CAR from history."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.press_override import press_override
from brief.schema import Metric, SectionData
from . import BuilderContext


def _quarterly_ratio(ctx: BuilderContext, metric_id: str, label: str) -> Metric:
    """BB FSR ratio, or an owner-approved press figure named by its outlet (decision (c))."""
    last = ctx.history.get_latest(metric_id) if ctx.history is not None else None
    press = press_override(last)
    return Metric(id=metric_id, label=label,
                  value=(last.value if last else None), unit="%",
                  as_of=(last.as_of if last else ctx.today),
                  source=(press.card_source if press else "BB"), cadence="quarterly",
                  press_override=press)


def build(ctx: BuilderContext) -> SectionData:
    metrics = [
        _quarterly_ratio(ctx, "banking_npl_pct", "NPL Ratio"),
        _quarterly_ratio(ctx, "banking_car_pct", "CAR"),
    ]
    return SectionData(
        id="banking", title="Banking", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today, section_id="banking"),
    )
