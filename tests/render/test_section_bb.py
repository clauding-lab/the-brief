from datetime import date, datetime, timezone

from brief.render.templates.section_bb import render
from brief.schema import BankerReadInsight, Delta, Metric, SectionData


def _section(freshness="fresh", with_bankerread=True):
    br = BankerReadInsight(
        sentences=["one.", "two.", "three.", "four."],
        generated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
    ) if with_bankerread else None
    return SectionData(
        id="bb", title="Policy & Rates",
        metrics=[
            Metric(id="bb_policy_rate", label="Policy Rate", value=10.0, unit="%",
                   as_of=date(2026, 4, 18), source="BB", cadence="event"),
            Metric(id="bb_gross_reserves", label="Reserves", value=34.12, unit="bn USD",
                   as_of=date(2026, 4, 20), source="BB", cadence="weekly",
                   delta=Delta(value=0.3, direction="up", window="wow")),
        ],
        freshness=freshness,
        bankerread=br,
    )


def test_renders_valid_jsx_function():
    out = render(_section())
    assert out.startswith("function SectionBB()")
    assert out.rstrip().endswith("}")
    assert "<section" in out
    assert "Policy Rate" in out
    assert "10.00" in out
    assert "<BankerRead" in out


def test_renders_pill_when_stale():
    out = render(_section(freshness="stale"))
    assert "Stale" in out


def test_renders_without_bankerread_when_missing():
    out = render(_section(with_bankerread=False))
    assert "<BankerRead" not in out
    assert "Policy Rate" in out
