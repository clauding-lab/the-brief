"""Tests for the macro builder (CPI + GDP + credit growth).

Phase C enrichment: adds macro_cpi_nonfood and point_to_point_inflation
alongside the existing macro_cpi_headline / macro_cpi_food / macro_gdp_growth
/ macro_credit_growth tuple. No new section is created.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from brief.builders import BuilderContext
from brief.builders.macro import build
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow


def _snap() -> EconDeltaSnapshot:
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
        sources_status={},
        data={},
    )


class _FakeHistory:
    """Minimal MetricHistoryClient stub returning known last-knowns by id."""

    def __init__(self, latest_by_id: dict[str, HistoryRow]) -> None:
        self._latest = latest_by_id

    def get_latest(self, metric_id: str) -> HistoryRow | None:
        return self._latest.get(metric_id)


def test_macro_section_identity() -> None:
    """Section keeps id='macro' and title='Macro & Inflation' after enrichment."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 5, 8))
    s = build(ctx)
    assert s.id == "macro"
    assert s.title == "Macro & Inflation"


def test_macro_has_six_metrics_after_phase_c() -> None:
    """Phase C lifts macro from 4 metrics to 6 (adds non-food + point-to-point)."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 5, 8))
    s = build(ctx)
    assert len(s.metrics) == 6


@pytest.mark.parametrize(
    "metric_id",
    [
        "macro_cpi_headline",
        "macro_cpi_food",
        "macro_cpi_nonfood",
        "point_to_point_inflation",
        "macro_gdp_growth",
        "macro_credit_growth",
    ],
)
def test_macro_metric_ids_present(metric_id: str) -> None:
    """All 6 expected metric IDs land in the section after enrichment."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 5, 8))
    s = build(ctx)
    ids = {m.id for m in s.metrics}
    assert metric_id in ids


def test_macro_metrics_in_documented_order() -> None:
    """CPI metrics group first (headline → food → non-food → p2p), then GDP, then credit growth."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 5, 8))
    s = build(ctx)
    ordered_ids = [m.id for m in s.metrics]
    assert ordered_ids == [
        "macro_cpi_headline",
        "macro_cpi_food",
        "macro_cpi_nonfood",
        "point_to_point_inflation",
        "macro_gdp_growth",
        "macro_credit_growth",
    ]


def test_macro_cpi_nonfood_value_flows_from_history() -> None:
    """When history returns a row for macro_cpi_nonfood the Metric carries that value."""
    history = _FakeHistory({
        "macro_cpi_nonfood": HistoryRow(
            metric_id="macro_cpi_nonfood",
            as_of=date(2026, 4, 30),
            value=8.42,
            source="BBS",
        ),
    })
    ctx = BuilderContext(snapshot=_snap(), history=history, today=date(2026, 5, 8))
    s = build(ctx)
    nonfood = next(m for m in s.metrics if m.id == "macro_cpi_nonfood")
    assert nonfood.value == 8.42
    assert nonfood.as_of == date(2026, 4, 30)
    assert nonfood.unit == "%"
    assert nonfood.source == "BBS"


def test_macro_point_to_point_inflation_queried_by_econdelta_canonical_id() -> None:
    """point_to_point_inflation has no macro_* alias — builder must query EconDelta-canonical id directly."""
    history = _FakeHistory({
        "point_to_point_inflation": HistoryRow(
            metric_id="point_to_point_inflation",
            as_of=date(2026, 4, 30),
            value=9.17,
            source="BBS",
        ),
    })
    ctx = BuilderContext(snapshot=_snap(), history=history, today=date(2026, 5, 8))
    s = build(ctx)
    p2p = next(m for m in s.metrics if m.id == "point_to_point_inflation")
    assert p2p.value == 9.17
    assert p2p.as_of == date(2026, 4, 30)


def test_macro_metric_value_falls_through_to_none_when_history_empty() -> None:
    """No history client → every metric value is None and as_of falls back to ctx.today."""
    today = date(2026, 5, 8)
    ctx = BuilderContext(snapshot=_snap(), history=None, today=today)
    s = build(ctx)
    for m in s.metrics:
        assert m.value is None, f"{m.id} should be None when history is unavailable"
        assert m.as_of == today, f"{m.id} should fall back to ctx.today when history is unavailable"


def test_macro_metric_as_of_is_today_when_history_returns_none() -> None:
    """History client present but missing this id → fall back to ctx.today."""
    today = date(2026, 5, 8)
    history = _FakeHistory({})  # empty store; every get_latest() returns None
    ctx = BuilderContext(snapshot=_snap(), history=history, today=today)
    s = build(ctx)
    for m in s.metrics:
        assert m.value is None
        assert m.as_of == today


def test_macro_section_marks_warming_up_when_only_p2p_missing() -> None:
    """5 fresh CPI/GDP/credit metrics + p2p None → section freshness is 'warming_up'.

    macro is in SECTIONS_WITHOUT_LEGACY_BACKFILL (brief/cadence.py), so a single
    None-valued metric promotes the section's freshness from 'unavailable' to
    'warming_up' rather than poisoning the whole section into 'stale'.

    This locks an operational contract that matters at cold-start: until
    point_to_point_inflation rows land in Supabase, the macro section must
    NOT be silently degraded — it should signal 'warming up' so the editor
    knows the data is intentionally accumulating, not broken.
    """
    today = date(2026, 5, 8)
    history = _FakeHistory({
        "macro_cpi_headline":  HistoryRow(metric_id="macro_cpi_headline",  as_of=today, value=8.0,  source="BBS"),
        "macro_cpi_food":      HistoryRow(metric_id="macro_cpi_food",      as_of=today, value=9.0,  source="BBS"),
        "macro_cpi_nonfood":   HistoryRow(metric_id="macro_cpi_nonfood",   as_of=today, value=7.5,  source="BBS"),
        # point_to_point_inflation deliberately absent → value=None
        "macro_gdp_growth":    HistoryRow(metric_id="macro_gdp_growth",    as_of=today, value=6.5,  source="BBS"),
        "macro_credit_growth": HistoryRow(metric_id="macro_credit_growth", as_of=today, value=10.0, source="BB"),
    })
    ctx = BuilderContext(snapshot=_snap(), history=history, today=today)
    s = build(ctx)
    assert s.freshness == "warming_up", (
        f"macro section should signal 'warming_up' when only p2p is missing; got {s.freshness!r}"
    )


@pytest.mark.parametrize(
    "metric_id, expected_cadence",
    [
        ("macro_cpi_headline", "monthly"),
        ("macro_cpi_food", "monthly"),
        ("macro_cpi_nonfood", "monthly"),
        ("point_to_point_inflation", "monthly"),
        ("macro_gdp_growth", "quarterly"),
        ("macro_credit_growth", "monthly"),
    ],
)
def test_macro_cadence_per_spec(metric_id: str, expected_cadence: str) -> None:
    """Cadence is preserved per the spec tuple — CPI all monthly, GDP quarterly, credit growth monthly."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 5, 8))
    s = build(ctx)
    m = next(metric for metric in s.metrics if metric.id == metric_id)
    assert m.cadence == expected_cadence


@pytest.mark.parametrize(
    "metric_id, expected_source",
    [
        ("macro_cpi_headline", "BBS"),
        ("macro_cpi_food", "BBS"),
        ("macro_cpi_nonfood", "BBS"),
        ("point_to_point_inflation", "BBS"),
        ("macro_gdp_growth", "BBS"),
        ("macro_credit_growth", "BB"),
    ],
)
def test_macro_source_per_spec(metric_id: str, expected_source: str) -> None:
    """Source attribution is preserved per the spec tuple."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 5, 8))
    s = build(ctx)
    m = next(metric for metric in s.metrics if metric.id == metric_id)
    assert m.source == expected_source
