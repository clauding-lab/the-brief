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
    BankerReadFreeform,
    BankerReadInsight,
    BankerReadStructured,
    ExecSignal,
    MapCoord,
    NewsItem,
    SectionData,
    TodaysCall,
)


def test_section_data_defaults():
    s = SectionData(id="bb", title="Policy & Rates", freshness="fresh")
    assert s.metrics == []
    assert s.news == []
    assert s.bankerread is None
    assert s.exec_signals is None
    assert s.pull is None
    assert s.degraded_breadth is False
    assert s.degraded_sector_heat is False
    assert s.extras == {}


def test_bankerread_structured_validates_when_all_5_fields_present():
    br = BankerReadStructured(
        meaning="Policy rate holds.",
        action="Hold duration short.",
        trigger="Inflation stays above 9%.",
        focus="BB rate decision.",
        pull="Policy rate holds.",
    )
    assert br.kind == "structured"
    assert br.meaning == "Policy rate holds."
    assert br.pull == "Policy rate holds."


def test_bankerread_freeform_validates_with_only_text():
    br = BankerReadFreeform(text="No fresh data; headlines suggest pressure.")
    assert br.kind == "freeform"
    assert br.pull is None


def test_discriminator_routes_correctly_on_kind_field():
    from pydantic import TypeAdapter
    ta = TypeAdapter(BankerReadInsight)
    structured = ta.validate_python({"kind": "structured", "meaning": "a", "action": "b",
                                     "trigger": "c", "focus": "d", "pull": "a"})
    assert isinstance(structured, BankerReadStructured)
    freeform = ta.validate_python({"kind": "freeform", "text": "x"})
    assert isinstance(freeform, BankerReadFreeform)


def test_mapcoord_rejects_x_11():
    with pytest.raises(ValidationError):
        MapCoord(section_id="bb", x=11, y=5, r=30, type="event")


def test_mapcoord_rejects_r_10():
    with pytest.raises(ValidationError):
        MapCoord(section_id="bb", x=5, y=5, r=10, type="event")


def test_mapcoord_rejects_invalid_type():
    with pytest.raises(ValidationError):
        MapCoord(section_id="bb", x=5, y=5, r=30, type="invalid")


def test_todays_call_rejects_text_over_400_chars():
    with pytest.raises(ValidationError):
        TodaysCall(text="x" * 401)


def test_todays_call_accepts_text_at_400_chars():
    tc = TodaysCall(text="x" * 400)
    assert tc.byline == "Desk Editor · The Brief"


def test_mapcoord_valid_with_hero_metric_id():
    mc = MapCoord(section_id="fx", x=3.5, y=7.0, r=25, type="fresh", hero_metric_id="fx_usd_bdt")
    assert mc.hero_metric_id == "fx_usd_bdt"
    assert mc.section_id == "fx"


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
