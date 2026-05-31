"""Unit test for fetch_fx_balance_monthly (F3 — §fx External Flow Balance)."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from brief.chart_series_fetcher import (
    _FX_BALANCE_MONTHLY_METRIC_IDS,
    fetch_fx_balance_monthly,
)
from brief.history import HistoryRow
from brief.v6_schema import SeriesPointV6


def _row(metric_id: str, as_of: str, value: float) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=date.fromisoformat(as_of), value=value, source="t")


def test_fetch_fx_balance_monthly_returns_three_series_chronological():
    mock = MagicMock()
    # 24 valid month-ends, most-recent-first (PostgREST anchor order).
    months = [f"2025-{m:02d}-01" for m in range(12, 0, -1)] + [f"2024-{m:02d}-01" for m in range(12, 0, -1)]

    def _gw(metric_ids, *, limit=None, days=None, today=None, table="metric_history"):
        return {m: [_row(m, d, 100.0 + i) for i, d in enumerate(months)] for m in metric_ids}

    mock.get_history_window.side_effect = _gw
    result = fetch_fx_balance_monthly(mock, months=24)

    assert set(result.keys()) == set(_FX_BALANCE_MONTHLY_METRIC_IDS)
    assert len(_FX_BALANCE_MONTHLY_METRIC_IDS) == 3
    for mid in _FX_BALANCE_MONTHLY_METRIC_IDS:
        pts = result[mid]
        assert len(pts) == 24
        assert all(isinstance(p, SeriesPointV6) and p.key == mid for p in pts)
        assert pts[0].ts < pts[-1].ts  # chronological oldest-first

    _, kwargs = mock.get_history_window.call_args
    assert kwargs.get("table") == "metric_history_monthly"
    assert kwargs.get("limit") == 24 * 3  # months * 3 ids (landmine #14)
