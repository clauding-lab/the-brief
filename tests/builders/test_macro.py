"""Tests for the macro builder — v1.4.0 rewrite.

v1.4.0 replaces the Phase C macro builder (6 metrics from metric_history using
old macro_* IDs) with an 8-metric builder reading from metric_history_monthly
using the _monthly-suffixed canonical IDs (AGENTS.md landmine #1 + #6).

Old metric IDs (macro_cpi_headline, macro_cpi_food, point_to_point_inflation,
macro_gdp_growth, macro_credit_growth) are superseded by the new canonical IDs.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from brief.builders import BuilderContext
from brief.builders.macro import build, _MACRO_METRICS
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow


def _snap() -> EconDeltaSnapshot:
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 5, 27, tzinfo=timezone.utc),
        sources_status={},
        data={},
    )


class _FakeHistoryMonthly:
    """Minimal MetricHistoryClient stub returning HistoryRows from metric_history_monthly."""

    def __init__(self, latest_by_id: dict[str, HistoryRow]) -> None:
        self._latest = latest_by_id

    def get_latest(self, metric_id: str, *, table: str = "metric_history_monthly") -> HistoryRow | None:
        return self._latest.get(metric_id)

    def get_history_window(
        self,
        metric_ids: list[str],
        *,
        limit: int | None = None,
        days: int | None = None,
        today: date | None = None,
        table: str = "metric_history",
    ) -> dict:
        # Return empty history (no facts) by default
        return {mid: [] for mid in metric_ids}


def test_macro_section_identity() -> None:
    """Section keeps id='macro' and title='Macro & Inflation' after rewrite."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 5, 27))
    s = build(ctx)
    assert s.id == "macro"
    assert s.title == "Macro & Inflation"


def test_macro_has_eight_metrics() -> None:
    """v1.4.0 macro section has exactly 8 monthly metrics."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 5, 27))
    s = build(ctx)
    assert len(s.metrics) == 8


@pytest.mark.parametrize(
    "metric_id",
    [mid for mid, *_ in _MACRO_METRICS],
)
def test_macro_metric_ids_present(metric_id: str) -> None:
    """All 8 expected metric IDs land in the section after rewrite."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 5, 27))
    s = build(ctx)
    ids = {m.id for m in s.metrics}
    assert metric_id in ids


def test_macro_metrics_in_documented_order() -> None:
    """Metrics appear in the order defined in _MACRO_METRICS."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 5, 27))
    s = build(ctx)
    ordered_ids = [m.id for m in s.metrics]
    expected = [mid for mid, *_ in _MACRO_METRICS]
    assert ordered_ids == expected


def test_macro_cpi_value_flows_from_history_monthly() -> None:
    """When history_monthly returns a row for cpi_12m_avg_monthly, the Metric carries that value."""
    today = date(2026, 5, 27)
    history = _FakeHistoryMonthly({
        "cpi_12m_avg_monthly": HistoryRow(
            metric_id="cpi_12m_avg_monthly",
            as_of=date(2026, 4, 1),
            value=5.24,
            source="BBS",
        ),
    })
    ctx = BuilderContext(snapshot=_snap(), history=None, today=today, history_monthly=history)
    s = build(ctx)
    cpi = next(m for m in s.metrics if m.id == "cpi_12m_avg_monthly")
    assert cpi.value == 5.24
    assert cpi.as_of == date(2026, 4, 1)
    assert cpi.unit == "%"
    assert cpi.source == "BBS"


def test_macro_metric_value_falls_through_to_none_when_history_monthly_none() -> None:
    """No history_monthly client → every metric value is None and as_of falls back to ctx.today."""
    today = date(2026, 5, 27)
    ctx = BuilderContext(snapshot=_snap(), history=None, today=today, history_monthly=None)
    s = build(ctx)
    for m in s.metrics:
        assert m.value is None, f"{m.id} should be None when history_monthly is unavailable"
        assert m.as_of == today, f"{m.id} should fall back to ctx.today when history_monthly is unavailable"


def test_macro_history_facts_empty_when_history_monthly_none() -> None:
    """When history_monthly is None, history_facts must be empty (no HistoryFact generation)."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 5, 27), history_monthly=None)
    s = build(ctx)
    assert s.history_facts == []


def test_macro_all_metrics_are_monthly_cadence() -> None:
    """All 8 macro metrics use monthly cadence (v1.4.0 reads metric_history_monthly)."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 5, 27))
    s = build(ctx)
    for m in s.metrics:
        assert m.cadence == "monthly", f"{m.id} should have cadence='monthly'"


def test_macro_builder_uses_metric_history_monthly_table() -> None:
    """Builder passes table='metric_history_monthly' to get_latest — AGENTS.md landmine #1."""
    from unittest.mock import MagicMock, call
    mock = MagicMock()
    mock.get_latest.return_value = None
    mock.get_history_window.return_value = {}

    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 5, 27), history_monthly=mock)
    build(ctx)

    for c in mock.get_latest.call_args_list:
        _, kwargs = c
        assert kwargs.get("table") == "metric_history_monthly", (
            f"get_latest called without table='metric_history_monthly': {c}"
        )
