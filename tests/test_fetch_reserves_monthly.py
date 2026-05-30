"""Unit test for fetch_reserves_monthly (F2 — §02 reserves two-line chart)."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from brief.chart_series_fetcher import (
    _RESERVES_MONTHLY_METRIC_IDS,
    fetch_reserves_monthly,
)
from brief.history import HistoryRow
from brief.v6_schema import SeriesPointV6


def _row(metric_id: str, as_of: str, value: float) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=date.fromisoformat(as_of), value=value, source="t")


def test_fetch_reserves_monthly_returns_both_series_chronological_from_monthly_table():
    gross = "gross_reserves_usd_bn_monthly"
    bpm6 = "net_reserves_bpm6_usd_bn_monthly"
    mock = MagicMock()

    # 13 valid month-ends, most-recent-first (PostgREST anchor order): Mar-2026 → Mar-2025.
    _months = [
        "2026-03-01", "2026-02-01", "2026-01-01", "2025-12-01", "2025-11-01",
        "2025-10-01", "2025-09-01", "2025-08-01", "2025-07-01", "2025-06-01",
        "2025-05-01", "2025-04-01", "2025-03-01",
    ]

    def _get_history_window(metric_ids, *, limit=None, days=None, today=None, table="metric_history"):
        return {
            m: [_row(m, d, 20.0 + i) for i, d in enumerate(_months)]
            for m in metric_ids
        }

    mock.get_history_window.side_effect = _get_history_window

    result = fetch_reserves_monthly(mock, months=13)

    # Both series present, keyed by metric_id (assert against the production
    # constant so a third reserves id added later is caught immediately).
    assert set(result.keys()) == set(_RESERVES_MONTHLY_METRIC_IDS)
    assert len(_RESERVES_MONTHLY_METRIC_IDS) == 2
    assert {gross, bpm6} == set(_RESERVES_MONTHLY_METRIC_IDS)
    for mid in (gross, bpm6):
        pts = result[mid]
        assert len(pts) == 13
        assert all(isinstance(p, SeriesPointV6) and p.key == mid for p in pts)
        # Output is chronological (oldest-first) regardless of PostgREST desc ordering.
        assert pts[0].ts < pts[-1].ts

    # Reads metric_history_monthly with a per-id limit (landmines #1, #14).
    _, kwargs = mock.get_history_window.call_args
    assert kwargs.get("table") == "metric_history_monthly"
    assert kwargs.get("limit") == 26  # months * 2 ids
