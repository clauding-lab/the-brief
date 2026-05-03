from datetime import date, datetime, timezone

from brief.render.v5.templates.section_bb import render_section_bb
from brief.schema import (
    BankerReadInsight,
    Delta,
    Metric,
    NewsItem,
    SectionData,
    SystemicRisk,
)


def _full_bb_section(systemic: bool = False) -> SectionData:
    metrics = [
        Metric(id="bb_policy_rate", label="Policy Rate", value=10.0, unit="%",
               as_of=date(2026, 4, 18), source="BB", cadence="event"),
        Metric(id="bb_sdf", label="SDF", value=8.5, unit="%",
               as_of=date(2026, 4, 18), source="BB", cadence="event"),
        Metric(id="bb_slf", label="SLF", value=11.5, unit="%",
               as_of=date(2026, 4, 18), source="BB", cadence="event"),
        Metric(id="bb_gross_reserves", label="Gross Reserves", value=34.12, unit="bn USD",
               as_of=date(2026, 4, 20), source="BB", cadence="weekly",
               delta=Delta(value=0.12, direction="up", window="wow")),
    ]
    risk = None
    if systemic:
        risk = SystemicRisk(headline="Reserves below threshold",
                            body=" ".join(["word"] * 80),
                            level="warning",
                            rule_id="fx_reserves_below_34bn")
    br = BankerReadInsight(
        variant="full",
        meaning=" ".join(["m"] * 80),
        action=" ".join(["a"] * 80),
        trigger=" ".join(["t"] * 80),
        focus=" ".join(["f"] * 80),
        pull_quote="Comfort with the real-rate gap, not the prelude to a pivot.",
        generated_at=datetime.now(timezone.utc),
    )
    return SectionData(
        id="bb", title="Governor held. Again.", kicker="Policy & rates",
        tldr="4th consecutive hold; credit growth undershooting.",
        metrics=metrics, news=[], freshness="fresh",
        bankerread=br, systemic_risk=risk, risk_active=systemic,
        history_values=[34.0, 34.05, 34.08, 34.10, 34.11, 34.10, 34.12],
    )


def test_section_bb_renders_full():
    html = render_section_bb(_full_bb_section())
    assert 'id="section-bb"' in html
    assert "§03" in html
    assert "POLICY" in html and "RATES" in html  # kicker — & is HTML-escaped to &amp;
    assert "Governor held" in html
    assert "10.00" in html
    assert "34.12" in html
    assert "POLICY RATE" in html
    assert "RESERVES" in html
    # V1-mockup style: compact §A/§B/§C/§D labels (no MEANING/ACTION/TRIGGER/FOCUS per line)
    assert 'class="br-lbl">§A<' in html
    assert 'class="br-lbl">§D<' in html
    # legend footer spelled out once
    assert "A · Meaning" in html
    assert "D · Focus" in html
    assert '<svg' in html


def test_section_bb_renders_systemic_risk_callout_when_active():
    html = render_section_bb(_full_bb_section(systemic=True))
    assert "systemic-risk" in html
    assert "Reserves below threshold" in html


def test_section_bb_omits_sparkline_when_history_too_short():
    section = _full_bb_section()
    section_short = section.model_copy(update={"history_values": [1.0, 2.0, 3.0]})
    html = render_section_bb(section_short)
    assert '<svg' not in html or 'sparkline' not in html


def test_section_bb_rejects_wrong_id():
    section = _full_bb_section().model_copy(update={"id": "fx"})
    import pytest
    with pytest.raises(ValueError):
        render_section_bb(section)
