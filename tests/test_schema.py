from datetime import date
import pytest
from pydantic import ValidationError

from brief.schema import Delta, Metric


def test_metric_minimal_valid():
    m = Metric(
        id="bb_policy_rate",
        label="Policy Rate",
        value=10.0,
        unit="%",
        as_of=date(2026, 4, 18),
        source="BB",
        cadence="event",
    )
    assert m.id == "bb_policy_rate"
    assert m.delta is None
    assert m.source_url is None


def test_metric_accepts_str_value():
    m = Metric(
        id="fx_usd_bdt_mid",
        label="USD/BDT mid",
        value="122.70",
        unit="BDT",
        as_of=date(2026, 4, 20),
        source="BB",
        cadence="daily",
    )
    assert m.value == "122.70"


def test_metric_rejects_unknown_cadence():
    with pytest.raises(ValidationError):
        Metric(
            id="x",
            label="x",
            value=1,
            unit="%",
            as_of=date(2026, 1, 1),
            source="x",
            cadence="yearly",  # not in CadenceKind
        )


def test_delta_requires_direction_literal():
    d = Delta(value=0.3, direction="up", window="wow")
    assert d.direction == "up"
    with pytest.raises(ValidationError):
        Delta(value=0.3, direction="north", window="wow")
