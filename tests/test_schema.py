from datetime import date, datetime, timezone
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


from brief.schema import (
    BankerReadInsight,
    ExecSignal,
    NewsItem,
    SectionData,
)


def test_section_data_defaults():
    s = SectionData(id="bb", title="Policy & Rates", freshness="fresh")
    assert s.metrics == []
    assert s.news == []
    assert s.bankerread is None
    assert s.exec_signals is None


def test_bankerread_full_variant():
    br = BankerReadInsight(
        sentences=["a", "b", "c", "d"],
        generated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
    )
    assert br.variant == "full"


def test_bankerread_stale_variant():
    br = BankerReadInsight(
        sentences=["no fresh data; headlines suggest x"],
        generated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        variant="stale_micro",
    )
    assert br.variant == "stale_micro"
    assert len(br.sentences) == 1


def test_exec_signal_shape():
    e = ExecSignal(direction="bull", text="Reserves up 0.3 bn WoW", section_anchor="bb")
    assert e.direction == "bull"
    assert e.section_anchor == "bb"


def test_news_item_parses_isoformat():
    n = NewsItem(
        title="x",
        url="https://example.com/x",
        source="DS",
        published=datetime(2026, 4, 21, 6, 0, tzinfo=timezone.utc),
    )
    assert n.source == "DS"
