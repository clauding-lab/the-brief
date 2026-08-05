# tests/test_history_anchors.py
import pytest
from brief.history_anchors import (
    HistoryFact,
    MIN_DATA_POINTS,
    DEFAULT_WINDOW,
    CADENCE_TABLE,
    _format_as_of,
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
    # Match sits 3 periods back (idx=3) to clear the LOOKBACK_MIN guard.
    history = [
        _row("cpi_12m_avg_monthly", "2026-04-01", 5.2),
        _row("cpi_12m_avg_monthly", "2026-03-01", 5.0),
        _row("cpi_12m_avg_monthly", "2026-02-01", 5.1),  # filler, doesn't match (< current)
        _row("cpi_12m_avg_monthly", "2022-03-01", 7.5),  # last higher, 3 periods back
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


def test_last_higher_than_suppresses_match_within_lookback_min():
    # A match 2 periods back (idx=2) must be skipped in favor of the next
    # valid match at least LOOKBACK_MIN periods back.
    history = [
        _row("x", "2026-04-01", 5.2),  # current
        _row("x", "2026-03-01", 5.0),  # idx=1, no match (< current)
        _row("x", "2026-02-01", 9.0),  # idx=2, WOULD match but too recent — must be skipped
        _row("x", "2026-01-01", 5.1),  # idx=3, no match (< current)
        _row("x", "2025-12-01", 8.0),  # idx=4, valid match
        _row("x", "2025-11-01", 4.0),  # filler
    ]
    fact = last_higher_than(history, current_value=5.2, cadence="monthly", formatter=_format_pct_1dp)
    assert fact is not None
    assert fact.reference_value == 8.0
    assert fact.reference_as_of == "2025-12-01"


def test_last_lower_than_suppresses_match_within_lookback_min():
    # Mirror of the above for last_lower_than.
    history = [
        _row("x", "2026-04-01", 5.2),  # current
        _row("x", "2026-03-01", 5.3),  # idx=1, no match (> current)
        _row("x", "2026-02-01", 3.0),  # idx=2, WOULD match but too recent — must be skipped
        _row("x", "2026-01-01", 5.4),  # idx=3, no match (> current)
        _row("x", "2025-12-01", 4.0),  # idx=4, valid match
        _row("x", "2025-11-01", 6.0),  # filler
    ]
    fact = last_lower_than(history, current_value=5.2, cadence="monthly", formatter=_format_pct_1dp)
    assert fact is not None
    assert fact.reference_value == 4.0
    assert fact.reference_as_of == "2025-12-01"


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


def test_rolling_extremes_interpolates_actual_row_count_not_requested_window():
    # Only 8 monthly rows are available (MIN_DATA_POINTS["monthly"]=6 clears the
    # floor), but the caller requests a 60-period window. The phrase must state
    # the number of rows actually examined (8), not the requested window (60) —
    # otherwise 8 rows of history publishes as a false "60-period" claim.
    history = [
        _row("cpi_12m_avg_monthly", "2026-04-01", 6.0),  # current — window max
        *[_row("cpi_12m_avg_monthly", f"2026-{m:02d}-01", 5.0 + m * 0.1) for m in range(1, 8)],  # 7 rows
    ]
    assert len(history) == 8
    fact = rolling_extremes(
        history,
        current_value=6.0,
        window=60,
        formatter=_format_pct_1dp,
        cadence="monthly",
    )
    assert fact is not None
    assert "8-period window" in fact.phrase
    assert "60-period window" not in fact.phrase


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


# ── compute_history_facts + fetch_and_compute ─────────────────────────────────

from brief.history_anchors import compute_history_facts, fetch_and_compute


def test_compute_history_facts_combines_primitives_for_monthly_metric():
    # Monthly cadence: current_value=5.2 with a history containing a prior low (4.8)
    # → since_lower fact should be produced (last time CPI was below 5.2 was 4.8 in 2021)
    history = [
        _row("cpi_12m_avg_monthly", "2026-04-01", 5.2),  # current
        _row("cpi_12m_avg_monthly", "2026-03-01", 5.4),
        _row("cpi_12m_avg_monthly", "2026-02-01", 5.6),
        _row("cpi_12m_avg_monthly", "2026-01-01", 5.7),
        _row("cpi_12m_avg_monthly", "2021-09-01", 4.8),  # below current → since_lower
        *[_row("cpi_12m_avg_monthly", f"2025-{m:02d}-01", 5.5 + m * 0.1) for m in range(1, 13)],
    ]
    facts = compute_history_facts(
        history,
        cadence="monthly",
        current_value=5.2,
        formatter=_format_pct_1dp,
    )
    assert len(facts) >= 1
    kinds = {f.kind for f in facts}
    assert "since_lower" in kinds


def test_compute_history_facts_returns_empty_for_sparse_history():
    history = [_row("x", "2026-04-01", 5.0), _row("x", "2026-03-01", 4.8)]
    facts = compute_history_facts(history, cadence="monthly", current_value=5.0, formatter=_format_pct_1dp)
    assert facts == []


def test_compute_history_facts_returns_empty_when_current_value_is_none():
    history = [_row("x", "2026-04-01", 5.0)] * 10
    facts = compute_history_facts(history, cadence="monthly", current_value=None, formatter=_format_pct_1dp)
    assert facts == []


def test_compute_history_facts_uptick_does_not_publish_lowest_since():
    # Current value ROSE vs the immediately-preceding period (8.4 -> 8.5).
    # The naive "first row below current" walk would match idx=1 (8.4) trivially
    # and publish a false "lowest since last month" claim. Direction-aware
    # dispatch must suppress since_lower entirely on an uptick and prefer
    # since_higher instead.
    history = [
        _row("cpi_12m_avg_monthly", "2026-04-01", 8.5),  # current — rose from 8.4
        _row("cpi_12m_avg_monthly", "2026-03-01", 8.4),  # prev period, lower
        _row("cpi_12m_avg_monthly", "2026-02-01", 8.6),  # higher, but only 2 back (guarded out)
        _row("cpi_12m_avg_monthly", "2026-01-01", 8.5),  # equal, matches neither
        _row("cpi_12m_avg_monthly", "2025-12-01", 9.0),  # higher, 4 back — valid since_higher
        _row("cpi_12m_avg_monthly", "2025-11-01", 8.0),  # filler
    ]
    facts = compute_history_facts(history, cadence="monthly", current_value=8.5, formatter=_format_pct_1dp)
    kinds = {f.kind for f in facts}
    assert "since_lower" not in kinds
    assert "since_higher" in kinds
    higher = next(f for f in facts if f.kind == "since_higher")
    assert higher.reference_value == 9.0
    assert higher.reference_as_of == "2025-12-01"


def test_compute_history_facts_downtick_still_publishes_lowest_since():
    # Current value FELL vs the immediately-preceding period (5.3 -> 5.0).
    # since_lower must still fire, anchored on a match that clears the
    # minimum-lookback guard.
    history = [
        _row("cpi_12m_avg_monthly", "2026-04-01", 5.0),  # current — fell from 5.3
        _row("cpi_12m_avg_monthly", "2026-03-01", 5.3),  # prev period, higher
        _row("cpi_12m_avg_monthly", "2026-02-01", 4.9),  # lower, but only 2 back (guarded out)
        _row("cpi_12m_avg_monthly", "2026-01-01", 5.1),  # higher, matches neither
        _row("cpi_12m_avg_monthly", "2025-12-01", 4.7),  # lower, 4 back — valid since_lower
        _row("cpi_12m_avg_monthly", "2025-11-01", 5.5),  # filler
    ]
    facts = compute_history_facts(history, cadence="monthly", current_value=5.0, formatter=_format_pct_1dp)
    kinds = {f.kind for f in facts}
    assert "since_lower" in kinds
    lower = next(f for f in facts if f.kind == "since_lower")
    assert lower.reference_value == 4.7
    assert lower.reference_as_of == "2025-12-01"


# ── _format_as_of: quarterly cadence ────────────────────────────────────────

def test_format_as_of_quarterly():
    assert _format_as_of(_date(2026, 1, 1), "quarterly") == "Q1 2026"
    assert _format_as_of(_date(2026, 4, 1), "quarterly") == "Q2 2026"
    assert _format_as_of(_date(2026, 7, 1), "quarterly") == "Q3 2026"
    assert _format_as_of(_date(2026, 10, 1), "quarterly") == "Q4 2026"
    assert _format_as_of(_date(2026, 12, 31), "quarterly") == "Q4 2026"


# ── _format_as_of: fiscal_year cadence (BD FY convention) ───────────────────

def test_format_as_of_fiscal_year_bd_convention():
    # BD FY runs Jul-Jun; labels by END year: Jul 2023–Jun 2024 = FY24.
    assert _format_as_of(_date(2023, 7, 1), "fiscal_year") == "FY24"    # start of FY24
    assert _format_as_of(_date(2024, 5, 1), "fiscal_year") == "FY24"    # mid-FY24
    assert _format_as_of(_date(2024, 6, 30), "fiscal_year") == "FY24"   # last day of FY24
    assert _format_as_of(_date(2024, 7, 1), "fiscal_year") == "FY25"    # start of FY25
    assert _format_as_of(_date(2024, 8, 15), "fiscal_year") == "FY25"   # mid-FY25


# ── first_cross_since: returns None when never crossed in window ─────────────

def test_first_cross_since_returns_none_when_always_same_side():
    # All 30+ rows above 90 — no opposite-side stretch in the window → None
    history = [
        _row("brent_crude_usd_barrel", "2026-04-01", 91.40),
        *[_row("brent_crude_usd_barrel", f"2025-{m:02d}-01", 91.0 + m * 0.1) for m in range(1, 13)],
        *[_row("brent_crude_usd_barrel", f"2024-{m:02d}-01", 90.5) for m in range(1, 13)],
        *[_row("brent_crude_usd_barrel", f"2023-{m:02d}-01", 90.1) for m in range(1, 7)],
    ]
    fact = first_cross_since(
        history,
        current_value=91.40,
        threshold=90.0,
        direction="up",
        formatter=lambda v: f"${v:.2f}",
        cadence="daily",
    )
    assert fact is None
