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
