"""Builder: Remittance — official monthly final, with a dated flash fallback.

`remit_yoy_pct` ("YoY %") was removed in v1.6.6: the id has never had a row, and
unlike most gaps this one cannot be closed by pointing at a different series.
Year-on-year needs the same month a year earlier, and `remit_monthly_mn` only
begins 2026-05-02 — there is no August 2025 to compare August 2026 against. It
becomes computable once history reaches thirteen months; until then a derived
column would be arithmetic on data that does not exist.

Same reasoning as `fiscal`: a permanently None metric scored "unavailable",
which for a `SECTIONS_WITHOUT_LEGACY_BACKFILL` section is promoted to
"warming_up", so the badge advertised incoming data that was never coming.

P0 honesty fix (2026-08-22 audit #204)
---------------------------------------
Until this change, the card read the daily BB flash `remit_monthly_mn`, which
is frozen mid-month at a provisional number (2820.0 for July, stamped as
"today's" figure every day it doesn't move) while `metric_history_monthly`'s
`remittance_usd_mn_monthly` already carried the OFFICIAL final for the prior
month (2858.68 for July — a ~$38.7mn/$0.04bn difference the flash never
closes). The card now reads the official final whenever one exists for the
expected month (the calendar month before the issue month — BB publishes
finals on roughly a one-month lag). If no row exists for that month yet, it
falls back to the flash and says so explicitly in the label/source, rather
than silently presenting a provisional number as a final one.
"""
from __future__ import annotations

from datetime import date

from brief.cadence import month_end, section_freshness
from brief.history import HistoryRow
from brief.schema import Metric, SectionData
from . import BuilderContext

_OFFICIAL_METRIC_ID = "remittance_usd_mn_monthly"
_FLASH_METRIC_ID = "remit_monthly_mn"


def _expected_final_month(today: date) -> tuple[int, int]:
    """The (year, month) an official final published today SHOULD cover.

    BB's monthly final publishes on roughly a one-month lag, so today's issue
    should be able to cite last calendar month's number.
    """
    if today.month == 1:
        return (today.year - 1, 12)
    return (today.year, today.month - 1)


def _official_final(ctx: BuilderContext) -> HistoryRow | None:
    """The official monthly final, but ONLY if it has caught up to the
    expected month.

    L3 (review round 1): compares chronologically, not with `!=`. A row for
    a month OLDER than expected means the archive hasn't caught up yet —
    fall back to the flash. A row for the expected month, OR a NEWER one
    (the archive got ahead of schedule — rare, but not a reason to discard a
    genuine newer final), is used as-is: a newer final must win, not be
    treated the same as a stale one just because it doesn't match exactly.
    """
    if ctx.history_monthly is None:
        return None
    row = ctx.history_monthly.get_latest(_OFFICIAL_METRIC_ID, table="metric_history_monthly")
    if row is None:
        return None
    archive_month = (row.as_of.year, row.as_of.month)
    if archive_month < _expected_final_month(ctx.today):
        return None
    return row


def build(ctx: BuilderContext) -> SectionData:
    official = _official_final(ctx)

    if official is not None:
        metrics = [
            Metric(
                id="remit_monthly_mn", label="Monthly Remittance",
                value=official.value, unit="mn USD",
                as_of=month_end(official.as_of),
                source="BB (publictn/5/27)", cadence="monthly",
            ),
        ]
    else:
        # H5, M1 (review round 1): the label stays "Monthly Remittance" on
        # BOTH paths — provenance goes in `source` only, protecting the
        # (slug, label) keying `_reject_invented_and_dedupe` and
        # `stamp_vintages` both rely on. And this branch must never ship
        # "(BB flash)" dated TODAY with no month named: the flash is a
        # daily-restamped running figure, so its own `as_of` says nothing
        # about which month it's tracking. `as_of` is forced to the month-end
        # of the EXPECTED month, and `source` states that month explicitly
        # and marks the figure provisional. Whether the flash is still
        # actively changing intra-month is unknowable here without a second
        # `get_history_window` call (landmine 23 forbids it from a builder).
        last_mn = ctx.history.get_latest(_FLASH_METRIC_ID) if ctx.history is not None else None
        expected_y, expected_m = _expected_final_month(ctx.today)
        month_label = date(expected_y, expected_m, 1).strftime("%b %Y")
        metrics = [
            Metric(
                id="remit_monthly_mn", label="Monthly Remittance",
                value=(last_mn.value if last_mn else None), unit="mn USD",
                as_of=month_end(date(expected_y, expected_m, 1)),
                source=f"BB flash · {month_label}, provisional",
                cadence="monthly", stale=True,
            ),
        ]
    return SectionData(
        id="remit", title="Remittance", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today, section_id="remit"),
    )
