from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_tbond import render_section_tbond
from brief.schema import Metric, NewsItem, SectionData


def _tbond_section(*, with_metrics: bool = True, with_news: bool = True,
                   bond_10y: float = 11.42) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="tbond_tbill_91d",  label="91d T-Bill cut-off",  value=9.85, unit="%",
                   as_of=date(2026, 4, 21), source="BB", cadence="event"),
            Metric(id="tbond_tbill_182d", label="182d T-Bill cut-off", value=10.20, unit="%",
                   as_of=date(2026, 4, 21), source="BB", cadence="event"),
            Metric(id="tbond_tbill_364d", label="364d T-Bill cut-off", value=10.55, unit="%",
                   as_of=date(2026, 4, 21), source="BB", cadence="event"),
            Metric(id="tbond_bond_5y",    label="5y Govt Bond",        value=11.10, unit="%",
                   as_of=date(2026, 4, 25), source="BB", cadence="weekly"),
            Metric(id="tbond_bond_10y",   label="10y Govt Bond",       value=bond_10y, unit="%",
                   as_of=date(2026, 4, 25), source="BB", cadence="weekly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="10y bond yield holds above 11%", url="https://example.com/tbond1",
                     source="The Financial Express", published=datetime(2026, 4, 25, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="tbond", title="T-Bonds & T-Bills",
        kicker="TREASURY", tldr=f"10y: {bond_10y}%",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[11.0, 11.1, 11.2, 11.25, 11.3, 11.38, bond_10y],
    )


def test_section_tbond_renders_with_full_metrics():
    html = render_section_tbond(_tbond_section())
    assert 'id="section-tbond"' in html
    assert "§08" in html
    assert "TREASURY" in html
    assert "T-Bonds" in html
    assert "11.42" in html
    assert "10Y" in html
    assert "5Y" in html
    assert "91D" in html


def test_section_tbond_renders_with_no_metrics():
    html = render_section_tbond(_tbond_section(with_metrics=False))
    assert 'id="section-tbond"' in html
    assert "metric-card" not in html


def test_section_tbond_renders_with_no_news():
    html = render_section_tbond(_tbond_section(with_news=False))
    assert 'id="section-tbond"' in html
    assert '<ul class="sec-news">' not in html


def test_section_tbond_threshold_badge_above_12():
    html = render_section_tbond(_tbond_section(bond_10y=12.5))
    assert "WATCH" in html


def test_section_tbond_rejects_wrong_id():
    section = _tbond_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_tbond(section)


# ── yield curve chart (Phase 2.3) ───────────────────────────────────────────

def test_section_tbond_renders_yield_curve_chart_when_enough_tenors():
    """At least 2 tenors with values → curve chart appears."""
    html = render_section_tbond(_tbond_section())
    # Chart container + svg present
    assert "yield-curve-chart" in html
    assert 'class="line-chart"' in html
    # Eyebrow shows the chart title
    assert "Yield Curve" in html


def test_section_tbond_skips_chart_when_only_one_tenor_has_value():
    """Single tenor → not a curve, no chart rendered."""
    metrics = [
        Metric(id="tbond_tbill_91d", label="91d", value=9.85, unit="%",
               as_of=date(2026, 4, 21), source="BB", cadence="event"),
        # All other tenors absent → chart should skip
    ]
    section = SectionData(
        id="tbond", title="T-Bonds & T-Bills",
        kicker="TREASURY", tldr="91d 9.85%",
        metrics=metrics, news=[], freshness="fresh",
    )
    html = render_section_tbond(section)
    assert "yield-curve-chart" not in html


def test_section_tbond_chart_uses_history_for_comparison_when_available():
    """When tenor metrics carry history_values with >=8 points, the chart
    plots last week's curve as a dashed comparison."""
    section = _tbond_section()
    # Attach history to each tenor (last value = today's, [-8] = ~last week)
    for m in section.metrics:
        m.history_values = [m.value - 0.20, m.value - 0.18, m.value - 0.15,
                            m.value - 0.12, m.value - 0.08, m.value - 0.05,
                            m.value - 0.02, m.value]
    html = render_section_tbond(section)
    # Comparison line uses dasharray
    assert "stroke-dasharray" in html


def test_section_tbond_renders_six_tenor_layout():
    """4 T-Bill cards top, 2 BGTB cards beside chart."""
    html = render_section_tbond(_tbond_section())
    assert "tbond-tbills" in html
    assert "tbond-bond-chart" in html


def test_section_tbond_renders_chart_with_partial_data():
    """Some tenors None, some present → chart still renders if ≥2 valid."""
    metrics = [
        Metric(id="tbond_tbill_91d", label="91d", value=9.85, unit="%",
               as_of=date(2026, 4, 21), source="BB", cadence="event"),
        Metric(id="tbond_tbill_182d", label="182d", value=None, unit="%",
               as_of=date(2026, 4, 21), source="BB", cadence="event"),
        Metric(id="tbond_tbill_364d", label="364d", value=10.55, unit="%",
               as_of=date(2026, 4, 21), source="BB", cadence="event"),
        Metric(id="tbond_bond_5y", label="5y", value=None, unit="%",
               as_of=date(2026, 4, 25), source="BB", cadence="weekly"),
        Metric(id="tbond_bond_10y", label="10y", value=11.42, unit="%",
               as_of=date(2026, 4, 25), source="BB", cadence="weekly"),
    ]
    section = SectionData(
        id="tbond", title="T-Bonds & T-Bills",
        kicker="TREASURY", tldr="partial data",
        metrics=metrics, news=[], freshness="warning",
    )
    html = render_section_tbond(section)
    assert "yield-curve-chart" in html
    # 3 valid tenors out of 5 → 3 dots; line breaks at each None gap
    assert html.count("<circle") == 3
