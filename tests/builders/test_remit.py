"""Remittance retains the latest supported month; it never guesses a period."""
from datetime import date, datetime, timezone

from brief.builders import BuilderContext
from brief.builders.remit import _expected_final_month, build
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow


class History:
    def __init__(self, rows):
        self.rows = {r.metric_id: r for r in rows}
        self.tables = []

    def get_latest(self, mid, *, table="metric_history"):
        self.tables.append(table)
        return self.rows.get(mid)


def context(*, official=None, today=date(2026, 8, 22), flash=None):
    snapshot = EconDeltaSnapshot(datetime(2026, 8, 22, tzinfo=timezone.utc), {}, {})
    return BuilderContext(snapshot, History([flash] if flash else []), today,
                          history_monthly=History([official] if official else []))


def test_completed_official_final_beats_same_month_daily_restamp():
    ctx = context(official=HistoryRow("remittance_usd_mn_monthly", date(2026, 7, 1), 2858.68, "BB"),
                  flash=HistoryRow("remit_monthly_mn", date(2026, 8, 22), 2820, "econdelta"))
    section = build(ctx)
    card = section.metrics[0]
    assert (card.id, card.label, card.value) == ("remit_monthly_mn", "Monthly Remittance", 2858.68)
    assert card.as_of == date(2026, 7, 31)
    assert "Jul 2026, final" in card.source
    assert not card.stale
    assert ctx.history_monthly.tables == ["metric_history_monthly"]


def test_future_official_final_is_rejected():
    ctx = context(official=HistoryRow("remittance_usd_mn_monthly", date(2026, 8, 31), 2900, "BB"))
    assert build(ctx).metrics == []
    assert build(ctx).freshness == "unavailable"


def test_open_month_bucket_does_not_manufacture_a_final_period():
    ctx = context(official=HistoryRow("remittance_usd_mn_monthly", date(2026, 8, 1), 2900, "BB"))
    assert build(ctx).metrics == []


def test_older_official_final_is_held_under_its_real_month():
    ctx = context(official=HistoryRow("remittance_usd_mn_monthly", date(2026, 6, 30), 2700, "BB"),
                  flash=HistoryRow("remit_monthly_mn", date(2026, 8, 22), 2820, "econdelta"))
    card = build(ctx).metrics[0]
    assert (card.value, card.as_of, card.stale) == (2700, date(2026, 6, 30), True)
    assert "Jun 2026, final" in card.source
    assert "newer period unavailable" in card.source


def test_undated_flash_is_unavailable_with_no_official_final():
    ctx = context(flash=HistoryRow("remit_monthly_mn", date(2026, 8, 22), 2820, "econdelta"))
    assert build(ctx).metrics == []
    assert build(ctx).freshness == "unavailable"


def test_missing_clients_are_unavailable():
    ctx = context()
    section = build(BuilderContext(ctx.snapshot, None, ctx.today))
    assert section.id == "remit" and section.title == "Remittance"
    assert section.metrics == [] and section.freshness == "unavailable"


def test_expected_release_clock_wraps_january_but_does_not_date_data():
    assert _expected_final_month(date(2026, 1, 15)) == (2025, 12)
    assert _expected_final_month(date(2026, 8, 22)) == (2026, 7)
    ctx = context(today=date(2026, 1, 15), official=HistoryRow(
        "remittance_usd_mn_monthly", date(2025, 11, 1), 2500, "BB"))
    card = build(ctx).metrics[0]
    assert card.as_of == date(2025, 11, 30)
    assert "Nov 2025" in card.source
