from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_macro import render_section_macro
from brief.schema import Metric, NewsItem, SectionData


def _macro_section(*, with_metrics: bool = True, with_news: bool = True, cpi_value: float = 9.4) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="macro_cpi_headline",  label="CPI Headline",  value=cpi_value, unit="%",
                   as_of=date(2026, 3, 31), source="BBS", cadence="monthly"),
            Metric(id="macro_cpi_food",      label="CPI Food",      value=10.8, unit="%",
                   as_of=date(2026, 3, 31), source="BBS", cadence="monthly"),
            Metric(id="macro_gdp_growth",    label="GDP Growth",    value=5.8, unit="%",
                   as_of=date(2026, 3, 31), source="BBS", cadence="quarterly"),
            Metric(id="macro_credit_growth", label="Credit Growth", value=8.5, unit="% YoY",
                   as_of=date(2026, 3, 31), source="BB", cadence="monthly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="Headline CPI eases to 9.4%", url="https://example.com/macro1",
                     source="The Daily Star", published=datetime(2026, 4, 28, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="macro", title="Macro & Inflation",
        kicker="MACRO", tldr=f"CPI Headline: {cpi_value}%",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[9.8, 9.7, 9.6, 9.5, 9.5, 9.4, cpi_value],
    )


def test_section_macro_renders_with_full_metrics():
    html = render_section_macro(_macro_section())
    assert 'id="section-macro"' in html
    assert "§03" in html
    assert "MACRO" in html
    assert "Macro &amp; Inflation" in html
    assert "9.40" in html
    assert "CPI" in html
    assert "FOOD" in html
    assert "GDP" in html


def test_section_macro_renders_with_no_metrics():
    html = render_section_macro(_macro_section(with_metrics=False))
    assert 'id="section-macro"' in html
    assert "metric-card" not in html


def test_section_macro_renders_with_no_news():
    html = render_section_macro(_macro_section(with_news=False))
    assert 'id="section-macro"' in html
    assert '<ul class="sec-news">' not in html


def test_section_macro_threshold_badge_above_10():
    html = render_section_macro(_macro_section(cpi_value=10.5))
    assert "CRITICAL" in html


def test_section_macro_rejects_wrong_id():
    section = _macro_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_macro(section)
