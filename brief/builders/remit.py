"""Remittance: newest evidenced period wins; same-period final beats flash.

An old final remains under its own month. Neither the issue month nor a daily
aggregate restamp can establish the period of a provisional remittance value.
"""
from __future__ import annotations

from datetime import date

from brief.cadence import section_freshness
from brief.history import finite_number, observation_date
from brief.schema import Metric, SectionData
from . import BuilderContext

_OFFICIAL_METRIC_ID = "remittance_usd_mn_monthly"
_FLASH_METRIC_ID = "remit_monthly_mn"


def _expected_final_month(today: date) -> tuple[int, int]:
    """Expected release month, used only to disclose lag, never to date data."""
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def build(ctx: BuilderContext) -> SectionData:
    candidates: list[tuple[date, bool, float, bool]] = []
    if ctx.history_monthly is not None:
        row = ctx.history_monthly.get_latest(_OFFICIAL_METRIC_ID, table="metric_history_monthly")
        if (row is not None and row.metric_id == _OFFICIAL_METRIC_ID
                and finite_number(row.value)):
            observed = observation_date(row, today=ctx.today, monthly=True)
            if observed is not None:
                candidates.append((observed, True, row.value, False))
    flash = ctx.snapshot.observation(_FLASH_METRIC_ID, today=ctx.today)
    if (flash is not None and flash.get("release_status") in ("final", "provisional")
            and flash.get("unit") == "USD million"):
        observed = date.fromisoformat(flash["as_of"])
        candidates.append((observed, flash["release_status"] == "final", flash["value"],
                           flash["quality"] == "held"))

    metrics: list[Metric] = []
    if candidates:
        # Compare source periods first. Final wins within the SAME month even
        # if a provisional source uses an intra-month reporting date.
        observed, final, value, held = max(candidates, key=lambda c: (c[0].year, c[0].month, c[1], c[0]))
        old = (observed.year, observed.month) < _expected_final_month(ctx.today)
        status = "final" if final else "provisional"
        note = f"BB · {observed:%b %Y}, {status}"
        if old or held:
            note += " · last known; newer period unavailable"
        metrics.append(Metric(id=_FLASH_METRIC_ID, label="Monthly Remittance", value=value,
                              unit="mn USD", as_of=observed, source=note, cadence="monthly",
                              stale=old or held or not final))
    return SectionData(id="remit", title="Remittance", metrics=metrics,
                       freshness=section_freshness(metrics, today=ctx.today) if metrics else "unavailable")
