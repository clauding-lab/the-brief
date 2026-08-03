"""Builder: Remittance — monthly cadence; last-known from history.

`remit_yoy_pct` ("YoY %") was removed in v1.6.6: the id has never had a row, and
unlike most gaps this one cannot be closed by pointing at a different series.
Year-on-year needs the same month a year earlier, and `remit_monthly_mn` only
begins 2026-05-02 — there is no August 2025 to compare August 2026 against. It
becomes computable once history reaches thirteen months; until then a derived
column would be arithmetic on data that does not exist.

Same reasoning as `fiscal`: a permanently None metric scored "unavailable",
which for a `SECTIONS_WITHOUT_LEGACY_BACKFILL` section is promoted to
"warming_up", so the badge advertised incoming data that was never coming.
"""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


def build(ctx: BuilderContext) -> SectionData:
    last_mn = ctx.history.get_latest("remit_monthly_mn") if ctx.history is not None else None

    metrics = [
        Metric(
            id="remit_monthly_mn", label="Monthly Remittance",
            value=(last_mn.value if last_mn else None), unit="mn USD",
            as_of=(last_mn.as_of if last_mn else ctx.today),
            source="BB (publictn/5/27)", cadence="monthly",
        ),
    ]
    return SectionData(
        id="remit", title="Remittance", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today, section_id="remit"),
    )
