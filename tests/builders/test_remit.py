"""Tests for the remittance builder.

P0 honesty fix (2026-08-22 audit #204): the card used to read the daily BB
flash (`remit_monthly_mn`, frozen at 2820.0 for July) and print it as the
lede figure, while the official final for the same month
(`remittance_usd_mn_monthly` = 2858.68) sat unread in the monthly archive.
These tests pin the new priority: official final for the expected month,
month-end `as_of`, and a flash fallback that says it is a flash.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from brief.builders import BuilderContext
from brief.builders.remit import build
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow


def _snap() -> EconDeltaSnapshot:
    return EconDeltaSnapshot(updated_at=datetime(2026, 8, 22, tzinfo=timezone.utc), sources_status={}, data={})


def _row(metric_id: str, value: float, as_of: date) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=as_of, value=value, source="test")


class _FakeHistory:
    """Minimal MetricHistoryClient stub. Records the tables it was asked for."""

    def __init__(self, latest_by_id: dict[str, HistoryRow], *, default_table: str = "metric_history") -> None:
        self._latest = latest_by_id
        self.default_table = default_table
        self.tables_seen: list[str] = []

    def get_latest(self, metric_id: str, *, table: str | None = None) -> HistoryRow | None:
        self.tables_seen.append(table or self.default_table)
        return self._latest.get(metric_id)


# Issue date: August 22 → expected official-final month is July.
TODAY = date(2026, 8, 22)


def _ctx(*, flash: dict | None = None, archive: dict | None = None, today: date = TODAY) -> BuilderContext:
    return BuilderContext(
        snapshot=_snap(),
        history=_FakeHistory(flash) if flash is not None else None,
        today=today,
        history_monthly=(
            _FakeHistory(archive, default_table="metric_history_monthly")
            if archive is not None else None
        ),
    )


def test_official_final_is_used_when_it_covers_the_expected_month() -> None:
    """July's official final (2858.68) beats the frozen July flash (2820.0)."""
    archive = {"remittance_usd_mn_monthly": _row("remittance_usd_mn_monthly", 2858.68, date(2026, 7, 31))}
    flash = {"remit_monthly_mn": _row("remit_monthly_mn", 2820.0, TODAY)}
    s = build(_ctx(flash=flash, archive=archive))
    m = s.metrics[0]
    assert m.value == 2858.68
    assert m.label == "Monthly Remittance"
    assert m.source == "BB (publictn/5/27)"
    assert m.cadence == "monthly"


def test_official_final_as_of_is_normalized_to_month_end() -> None:
    """Some archive rows stamp the month START (e.g. 2026-07-01) — landmine:
    a month-start stamp ages a fresh final read ~30 days before it should."""
    archive = {"remittance_usd_mn_monthly": _row("remittance_usd_mn_monthly", 2858.68, date(2026, 7, 1))}
    s = build(_ctx(archive=archive))
    assert s.metrics[0].as_of == date(2026, 7, 31)


def test_falls_back_to_flash_when_archive_has_no_row_for_expected_month() -> None:
    """Archive frozen two months back (exports-style lag) — the July slot is
    empty, so the honest move is the flash, clearly labelled as one."""
    archive = {"remittance_usd_mn_monthly": _row("remittance_usd_mn_monthly", 2700.0, date(2026, 6, 30))}
    flash = {"remit_monthly_mn": _row("remit_monthly_mn", 2820.0, TODAY)}
    s = build(_ctx(flash=flash, archive=archive))
    m = s.metrics[0]
    assert m.value == 2820.0
    assert m.label == "Monthly Remittance (BB flash)"
    assert "flash" in m.source.lower()


def test_falls_back_to_flash_when_archive_is_completely_empty() -> None:
    flash = {"remit_monthly_mn": _row("remit_monthly_mn", 2820.0, TODAY)}
    s = build(_ctx(flash=flash, archive={}))
    assert s.metrics[0].value == 2820.0
    assert s.metrics[0].label == "Monthly Remittance (BB flash)"


def test_falls_back_to_flash_when_no_monthly_client_at_all() -> None:
    flash = {"remit_monthly_mn": _row("remit_monthly_mn", 2820.0, TODAY)}
    s = build(_ctx(flash=flash, archive=None))
    assert s.metrics[0].value == 2820.0
    assert s.metrics[0].label == "Monthly Remittance (BB flash)"


def test_value_is_none_when_both_official_and_flash_are_unavailable() -> None:
    s = build(_ctx(flash=None, archive=None))
    m = s.metrics[0]
    assert m.value is None
    assert m.as_of == TODAY
    assert m.label == "Monthly Remittance (BB flash)"


def test_reads_the_official_metric_id_from_the_monthly_table() -> None:
    archive = {"remittance_usd_mn_monthly": _row("remittance_usd_mn_monthly", 2858.68, date(2026, 7, 31))}
    client = _FakeHistory(archive, default_table="metric_history_monthly")
    ctx = BuilderContext(snapshot=_snap(), history=None, today=TODAY, history_monthly=client)
    build(ctx)
    assert set(client.tables_seen) == {"metric_history_monthly"}


def test_section_identity_and_single_metric() -> None:
    s = build(_ctx())
    assert s.id == "remit"
    assert s.title == "Remittance"
    assert len(s.metrics) == 1
    assert s.metrics[0].id == "remit_monthly_mn"
