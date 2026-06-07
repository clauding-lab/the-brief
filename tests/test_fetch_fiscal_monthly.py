"""Unit test for fetch_fiscal_monthly (F7b — §fiscal NBR monthly chart)."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from brief.chart_series_fetcher import fetch_fiscal_monthly
from brief.history import HistoryRow
from brief.v6_schema import SeriesPointV6


def _row(metric_id: str, as_of: str, value: float) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=date.fromisoformat(as_of), value=value, source="t")


def test_fetch_fiscal_monthly_returns_chronological_series_from_monthly_table():
    mid = "nbr_revenue_monthly_cr"
    mock = MagicMock()

    def _get_history_window(metric_ids, *, limit=None, days=None, today=None, table="metric_history"):
        # PostgREST anchor mode returns most-recent-first; mock 10 months desc.
        return {
            m: [_row(m, f"2025-{x:02d}-01", 22000.0 + x * 100) for x in range(10, 0, -1)]
            for m in metric_ids
        }

    mock.get_history_window.side_effect = _get_history_window

    result = fetch_fiscal_monthly(mock, months=30)

    assert mid in result
    pts = result[mid]
    assert len(pts) == 10
    assert all(isinstance(p, SeriesPointV6) and p.key == mid for p in pts)
    # Output is chronological (oldest-first) regardless of PostgREST desc ordering.
    assert pts[0].ts < pts[-1].ts

    # Reads metric_history_monthly with a per-id limit (landmines #1, #14).
    _, kwargs = mock.get_history_window.call_args
    assert kwargs.get("table") == "metric_history_monthly"
    assert kwargs.get("limit") == 30  # months * 1 id
