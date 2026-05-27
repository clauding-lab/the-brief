"""Integration tests for the macro section builder — v1.4.0 enrichment.

Verifies:
1. Builder reads 8 monthly metrics from metric_history_monthly.
2. Builder attaches history_facts when enough history is available.
3. CPI 24-month series are fetched for the macro section chart.
4. Builder degrades gracefully when history_monthly client is None.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from brief.builders import BuilderContext
from brief.builders.macro import build, _MACRO_METRICS
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow
from brief.chart_series_fetcher import fetch_macro_cpi_series


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot() -> EconDeltaSnapshot:
    from datetime import datetime, timezone
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 5, 27, tzinfo=timezone.utc),
        sources_status={},
        data={},
    )


def _make_row(metric_id: str, as_of: str, value: float) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=date.fromisoformat(as_of), value=value, source="t")


def _history_monthly_with_values(value_map: dict[str, float]) -> MagicMock:
    """Return a mock history_monthly client whose get_latest returns
    a HistoryRow for each metric_id key in value_map."""
    mock = MagicMock()

    def _get_latest(mid: str, *, table: str = "metric_history_monthly") -> HistoryRow | None:
        if mid in value_map:
            return _make_row(mid, "2026-04-01", value_map[mid])
        return None

    mock.get_latest.side_effect = _get_latest

    def _get_history_window(metric_ids, *, limit=None, days=None, today=None, table="metric_history"):
        result = {}
        for mid in metric_ids:
            if mid in value_map:
                # Return enough rows (≥6 for monthly) to satisfy MIN_DATA_POINTS
                rows = [
                    _make_row(mid, f"2026-{m:02d}-01", value_map[mid] + (m * 0.1))
                    for m in range(1, 7)
                ]
                # Prepend current as most-recent-first
                rows = [_make_row(mid, "2026-04-01", value_map[mid])] + rows
                result[mid] = rows
            else:
                result[mid] = []
        return result

    mock.get_history_window.side_effect = _get_history_window
    return mock


# ---------------------------------------------------------------------------
# Test 1 — macro builder reads 8 monthly metrics from metric_history_monthly
# ---------------------------------------------------------------------------

def test_macro_builder_reads_8_monthly_metrics_from_history_monthly():
    value_map = {mid: 5.0 + i * 0.1 for i, (mid, *_) in enumerate(_MACRO_METRICS)}
    history_monthly = _history_monthly_with_values(value_map)

    ctx = BuilderContext(
        snapshot=_make_snapshot(),
        history=None,
        today=date(2026, 5, 27),
        history_monthly=history_monthly,
    )
    section = build(ctx)

    assert section.id == "macro"
    metric_ids = [m.id for m in section.metrics]
    assert len(metric_ids) == 8

    expected_ids = [mid for mid, *_ in _MACRO_METRICS]
    for mid in expected_ids:
        assert mid in metric_ids, f"Expected {mid} in macro section metrics"

    # Verify get_latest was called with correct table kwarg
    for call in history_monthly.get_latest.call_args_list:
        args, kwargs = call
        assert kwargs.get("table") == "metric_history_monthly", (
            f"get_latest must use table='metric_history_monthly', got {kwargs}"
        )


# ---------------------------------------------------------------------------
# Test 2 — macro builder attaches history_facts
# ---------------------------------------------------------------------------

def test_macro_builder_attaches_history_facts():
    """Builder should attach history_facts when enough monthly history exists."""
    # Set current value at a historic low so last_lower_than fires
    value_map = {}
    for mid, *_ in _MACRO_METRICS:
        value_map[mid] = 4.5  # current value = 4.5% (a "new low")

    mock = MagicMock()

    def _get_latest(mid, *, table="metric_history_monthly"):
        return _make_row(mid, "2026-04-01", 4.5)

    def _get_history_window(metric_ids, *, limit=None, days=None, today=None, table="metric_history"):
        result = {}
        for mid in metric_ids:
            # 13 rows, most-recent-first; all older rows at 5.5 (> current 4.5)
            # so last_lower_than finds none, last_higher_than should fire instead
            rows = [_make_row(mid, "2026-04-01", 4.5)]
            rows += [_make_row(mid, f"2025-{m:02d}-01", 5.5) for m in range(1, 13)]
            result[mid] = rows
        return result

    mock.get_latest.side_effect = _get_latest
    mock.get_history_window.side_effect = _get_history_window

    ctx = BuilderContext(
        snapshot=_make_snapshot(),
        history=None,
        today=date(2026, 5, 27),
        history_monthly=mock,
    )
    section = build(ctx)

    # With 13 rows (≥ MIN_DATA_POINTS["monthly"]=6), some facts should fire
    # (either since_higher or since_lower depending on data pattern)
    assert isinstance(section.history_facts, list)
    # Each metric should contribute at least one fact since history is rich enough
    # We have 8 metrics × at least 1 fact each = ≥ 1 total
    assert len(section.history_facts) >= 1


# ---------------------------------------------------------------------------
# Test 3 — macro section series populated with 3 CPI monthly series
# ---------------------------------------------------------------------------

def test_macro_section_series_populated_with_cpi_24_months():
    """fetch_macro_cpi_series returns all 3 CPI metric_ids."""
    from brief.v6_schema import SeriesPointV6

    CPI_IDS = ["cpi_12m_avg_monthly", "cpi_p2p_food_monthly", "cpi_p2p_nonfood_monthly"]

    mock = MagicMock()

    def _get_history_window(metric_ids, *, limit=None, days=None, today=None, table="metric_history"):
        result = {}
        for mid in metric_ids:
            rows = [_make_row(mid, f"2024-{m:02d}-01", 5.0 + m * 0.1) for m in range(1, 13)]
            rows += [_make_row(mid, f"2025-{m:02d}-01", 5.2 + m * 0.05) for m in range(1, 13)]
            result[mid] = rows
        return result

    mock.get_history_window.side_effect = _get_history_window

    result = fetch_macro_cpi_series(mock)

    assert isinstance(result, dict)
    for cid in CPI_IDS:
        assert cid in result, f"Expected CPI series key {cid} in result"
        assert len(result[cid]) > 0, f"Expected non-empty series for {cid}"
        # Each point should be a SeriesPointV6
        for pt in result[cid]:
            assert isinstance(pt, SeriesPointV6)
            assert pt.key == cid

    # Check that get_history_window was called with metric_history_monthly table
    for call in mock.get_history_window.call_args_list:
        _, kwargs = call
        assert kwargs.get("table") == "metric_history_monthly"


# ---------------------------------------------------------------------------
# Test 4 — graceful degradation when history_monthly is None
# ---------------------------------------------------------------------------

def test_macro_builder_handles_missing_history_monthly_client_gracefully():
    """When ctx.history_monthly is None, builder returns section with empty
    history_facts, all metric values None, no exception raised."""
    ctx = BuilderContext(
        snapshot=_make_snapshot(),
        history=None,
        today=date(2026, 5, 27),
        history_monthly=None,
    )
    section = build(ctx)

    assert section.id == "macro"
    assert len(section.metrics) == 8
    assert section.history_facts == []
    # All values should be None since no client was available
    for m in section.metrics:
        assert m.value is None


# ---------------------------------------------------------------------------
# Test 5 — editor input includes history_facts key for macro section
# ---------------------------------------------------------------------------

def test_editor_input_includes_history_facts_for_macro():
    """_to_v6_raw serializes SectionData.history_facts into the editor input."""
    from brief.history_anchors import HistoryFact
    from brief.schema import SectionData
    from brief.pipeline_v6 import _to_v6_raw

    fact = HistoryFact(
        metric_id="cpi_12m_avg_monthly",
        kind="since_lower",
        phrase="lowest 12-month CPI since Sep 2021 (4.8% then)",
        reference_value=4.8,
        reference_value_formatted="4.8%",
        reference_as_of="2021-09-01",
    )
    section = SectionData(
        id="macro",
        title="Macro & Inflation",
        metrics=[],
        freshness="fresh",
        history_facts=[fact],
    )

    raw_sections = _to_v6_raw([section])
    assert len(raw_sections) == 1
    macro_raw = raw_sections[0]

    assert "history_facts" in macro_raw
    hf_list = macro_raw["history_facts"]
    assert len(hf_list) == 1
    hf = hf_list[0]
    assert hf["metric_id"] == "cpi_12m_avg_monthly"
    assert hf["kind"] == "since_lower"
    assert hf["phrase"] == "lowest 12-month CPI since Sep 2021 (4.8% then)"
    assert hf["reference_value_formatted"] == "4.8%"
    assert hf["reference_as_of"] == "2021-09-01"
