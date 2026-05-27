# tests/test_history_anchors.py
import pytest
from brief.history_anchors import (
    HistoryFact,
    MIN_DATA_POINTS,
    DEFAULT_WINDOW,
    CADENCE_TABLE,
)


def test_history_fact_is_frozen_dataclass():
    fact = HistoryFact(
        metric_id="cpi_12m_avg_monthly",
        kind="since_lower",
        phrase="lowest 12-month CPI since Sep 2021 (4.8% then)",
        reference_value=4.8,
        reference_value_formatted="4.8%",
        reference_as_of="2021-09-01",
    )
    assert fact.metric_id == "cpi_12m_avg_monthly"
    assert fact.kind == "since_lower"
    with pytest.raises(Exception):  # frozen dataclass raises on setattr
        fact.kind = "vs_period"  # type: ignore[misc]


def test_min_data_points_per_cadence():
    assert MIN_DATA_POINTS["daily"] == 30
    assert MIN_DATA_POINTS["weekly"] == 12
    assert MIN_DATA_POINTS["monthly"] == 6
    assert MIN_DATA_POINTS["quarterly"] == 4
    assert MIN_DATA_POINTS["fiscal_year"] == 3


def test_default_window_per_cadence():
    assert DEFAULT_WINDOW["daily"] == 365
    assert DEFAULT_WINDOW["weekly"] == 52
    assert DEFAULT_WINDOW["monthly"] == 60
    assert DEFAULT_WINDOW["quarterly"] == 16
    assert DEFAULT_WINDOW["fiscal_year"] == 5


def test_cadence_table_routing():
    assert CADENCE_TABLE["daily"] == "metric_history"
    assert CADENCE_TABLE["weekly"] == "metric_history"
    assert CADENCE_TABLE["monthly"] == "metric_history_monthly"
    assert CADENCE_TABLE["quarterly"] == "metric_history"
    assert CADENCE_TABLE["fiscal_year"] == "metric_history"


# ── last_lower_than ──────────────────────────────────────────────────────────

from datetime import date as _date
from brief.history_anchors import last_lower_than
from brief.history import HistoryRow


def _format_pct_1dp(v: float) -> str:
    return f"{v:.1f}%"


def _row(metric_id: str, as_of: str, value: float) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=_date.fromisoformat(as_of), value=value, source="t")


def test_last_lower_than_finds_most_recent_lower():
    # History sorted most-recent-first (as PostgREST order=as_of.desc returns)
    # 6 rows: meets MIN_DATA_POINTS["monthly"]=6
    history = [
        _row("cpi_12m_avg_monthly", "2026-04-01", 5.2),  # current
        _row("cpi_12m_avg_monthly", "2026-03-01", 5.4),
        _row("cpi_12m_avg_monthly", "2026-02-01", 5.6),
        _row("cpi_12m_avg_monthly", "2026-01-01", 5.7),
        _row("cpi_12m_avg_monthly", "2021-09-01", 4.8),  # last lower
        _row("cpi_12m_avg_monthly", "2021-08-01", 5.1),
    ]
    fact = last_lower_than(history, current_value=5.2, cadence="monthly", formatter=_format_pct_1dp)
    assert fact is not None
    assert fact.kind == "since_lower"
    assert fact.reference_value == 4.8
    assert fact.reference_value_formatted == "4.8%"
    assert fact.reference_as_of == "2021-09-01"
    assert "since Sep 2021" in fact.phrase
    assert "(4.8% then)" in fact.phrase


def test_last_lower_than_returns_none_when_no_lower_exists():
    # No row with value < 5.2 in the window
    history_with_higher_only = [_row("x", "2026-04-01", 5.2)] + [
        _row("x", f"2026-{m:02d}-01", 10.0) for m in range(1, 4)
    ]
    # Pad to meet min_data_points threshold
    extended = history_with_higher_only + [
        _row("x", f"2025-{m:02d}-01", 10.0) for m in range(1, 13)
    ]
    fact = last_lower_than(extended, current_value=5.2, cadence="monthly", formatter=_format_pct_1dp)
    assert fact is None


def test_last_lower_than_returns_none_when_history_too_sparse():
    history = [_row("x", "2026-04-01", 5.2), _row("x", "2026-03-01", 4.8)]
    # Only 2 monthly data points — below MIN_DATA_POINTS["monthly"]=6
    fact = last_lower_than(history, current_value=5.2, cadence="monthly", formatter=_format_pct_1dp)
    assert fact is None


# ── last_higher_than ─────────────────────────────────────────────────────────

from brief.history_anchors import last_higher_than


def test_last_higher_than_finds_most_recent_higher():
    history = [
        _row("cpi_12m_avg_monthly", "2026-04-01", 5.2),
        _row("cpi_12m_avg_monthly", "2026-03-01", 5.0),
        _row("cpi_12m_avg_monthly", "2022-03-01", 7.5),  # last higher
        _row("cpi_12m_avg_monthly", "2022-02-01", 6.0),
        # pad to meet min_data_points threshold (need 6 total)
        *[_row("cpi_12m_avg_monthly", f"2021-{m:02d}-01", 4.0) for m in range(1, 3)],
    ]
    fact = last_higher_than(history, current_value=5.2, cadence="monthly", formatter=_format_pct_1dp)
    assert fact is not None
    assert fact.kind == "since_higher"
    assert fact.reference_value == 7.5
    assert "highest since Mar 2022" in fact.phrase
    assert "(7.5% then)" in fact.phrase


# ── pct_change_since ─────────────────────────────────────────────────────────

from brief.history_anchors import pct_change_since


def test_pct_change_since_matches_named_period():
    history = [
        _row("cpi_12m_avg_monthly", "2026-04-01", 5.2),
        _row("cpi_12m_avg_monthly", "2026-03-01", 5.4),
        _row("cpi_12m_avg_monthly", "2026-02-01", 5.5),
        _row("cpi_12m_avg_monthly", "2025-04-01", 9.4),  # YoY anchor
        *[_row("cpi_12m_avg_monthly", f"2025-{m:02d}-01", 8.5) for m in range(1, 13)],
    ]
    fact = pct_change_since(
        history,
        current_value=5.2,
        reference_as_of="2025-04-01",
        formatter=_format_pct_1dp,
        cadence="monthly",
    )
    assert fact is not None
    assert fact.kind == "vs_period"
    assert fact.reference_value == 9.4
    assert "vs Apr 2025" in fact.phrase
    assert "(9.4% then)" in fact.phrase


# ── rolling_extremes ─────────────────────────────────────────────────────────

from brief.history_anchors import rolling_extremes


def test_rolling_extremes_returns_min_max_and_rank():
    # current_value is the max in the 30-period window — returns extreme_in_window fact
    # Need ≥30 rows for cadence="daily" (MIN_DATA_POINTS["daily"]=30)
    # All other values cap at 90.0 so 91.40 is the unambiguous window max
    history = [
        _row("brent_crude_usd_barrel", "2026-04-01", 91.40),  # current — window max
        *[_row("brent_crude_usd_barrel", f"2026-03-{d:02d}", 80.0 + d * 0.2) for d in range(1, 31)],  # 30 rows, all < 91.40
    ]
    fact = rolling_extremes(
        history,
        current_value=91.40,
        window=31,
        formatter=lambda v: f"${v:.2f}",
        cadence="daily",
    )
    assert fact is not None
    assert fact.kind == "extreme_in_window"
    # Either highlights the max or notes current rank in window — implementation choice
    assert "$" in fact.reference_value_formatted


# ── first_cross_since ────────────────────────────────────────────────────────

from brief.history_anchors import first_cross_since


def test_first_cross_since_detects_threshold_cross_up():
    # Need ≥30 rows for cadence="daily" (MIN_DATA_POINTS["daily"]=30)
    history = [
        _row("brent_crude_usd_barrel", "2026-04-01", 91.40),  # current — crossed above 90
        _row("brent_crude_usd_barrel", "2026-03-15", 87.00),
        _row("brent_crude_usd_barrel", "2026-03-01", 86.00),
        _row("brent_crude_usd_barrel", "2026-02-15", 85.00),  # extra row to meet threshold
        _row("brent_crude_usd_barrel", "2023-10-01", 92.10),  # last above threshold
        _row("brent_crude_usd_barrel", "2023-09-01", 88.00),
        *[_row("brent_crude_usd_barrel", f"2024-{m:02d}-01", 80.0) for m in range(1, 13)],
        *[_row("brent_crude_usd_barrel", f"2025-{m:02d}-01", 82.0) for m in range(1, 13)],
    ]
    fact = first_cross_since(
        history,
        current_value=91.40,
        threshold=90.0,
        direction="up",
        formatter=lambda v: f"${v:.2f}",
        cadence="daily",
    )
    assert fact is not None
    assert fact.kind == "first_cross_since"
    assert "above $90" in fact.phrase
    assert "Oct 2023" in fact.phrase
    assert "($92.10" in fact.phrase
