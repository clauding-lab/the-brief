"""Unit test for fetch_yield_ladder_monthly (F5 — §tbond 8-tenor yield ladder)."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from brief.chart_series_fetcher import (
    _YIELD_LADDER_MONTHLY_METRIC_IDS,
    fetch_yield_ladder_monthly,
)
from brief.history import HistoryRow
from brief.v6_schema import SeriesPointV6


def _row(metric_id: str, as_of: str, value: float) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=date.fromisoformat(as_of), value=value, source="t")


def test_fetch_yield_ladder_monthly_returns_all_tenors_last_two_months():
    mock = MagicMock()

    def _get_history_window(metric_ids, *, limit=None, days=None, today=None, table="metric_history"):
        # PostgREST anchor mode returns most-recent-first; mock 2 month-ends desc.
        return {
            m: [_row(m, "2026-04-01", 10.5), _row(m, "2026-03-01", 9.9)]
            for m in metric_ids
        }

    mock.get_history_window.side_effect = _get_history_window

    result = fetch_yield_ladder_monthly(mock, months=2)

    # All 8 tenors present.
    assert set(result.keys()) == set(_YIELD_LADDER_MONTHLY_METRIC_IDS)
    assert len(_YIELD_LADDER_MONTHLY_METRIC_IDS) == 8
    for mid in _YIELD_LADDER_MONTHLY_METRIC_IDS:
        pts = result[mid]
        assert len(pts) == 2
        assert all(isinstance(p, SeriesPointV6) and p.key == mid for p in pts)
        # Output is chronological (oldest-first): March before April.
        assert pts[0].ts == "2026-03-01"
        assert pts[-1].ts == "2026-04-01"

    # Reads metric_history_monthly with a per-id limit (landmines #1, #14).
    _, kwargs = mock.get_history_window.call_args
    assert kwargs.get("table") == "metric_history_monthly"
    assert kwargs.get("limit") == 16  # months * 8 ids
