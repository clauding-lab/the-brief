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
