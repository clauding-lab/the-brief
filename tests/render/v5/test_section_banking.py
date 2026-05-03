from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_banking import render_section_banking
from brief.schema import Metric, NewsItem, SectionData


def _banking_section(*, with_metrics: bool = True, with_news: bool = True,
                     npl: float = 11.5) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="banking_npl_pct", label="NPL Ratio", value=npl, unit="%",
                   as_of=date(2026, 3, 31), source="BB", cadence="quarterly"),
            Metric(id="banking_car_pct", label="CAR", value=11.8, unit="%",
                   as_of=date(2026, 3, 31), source="BB", cadence="quarterly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="Q1 NPL ratio holds steady", url="https://example.com/banking1",
                     source="The Daily Star", published=datetime(2026, 4, 5, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="banking", title="Banking",
        kicker="BANKING", tldr=f"NPL: {npl}%; CAR: 11.8%",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[10.5, 10.8, 11.0, 11.2, 11.3, 11.4, npl],
    )


def test_section_banking_renders_with_full_metrics():
    html = render_section_banking(_banking_section())
    assert 'id="section-banking"' in html
    assert "§10" in html
    assert "BANKING" in html
    assert "Banking" in html
    assert "11.50" in html
    assert "NPL" in html
    assert "CAR" in html


def test_section_banking_renders_with_no_metrics():
    html = render_section_banking(_banking_section(with_metrics=False))
    assert 'id="section-banking"' in html
    assert "metric-card" not in html


def test_section_banking_renders_with_no_news():
    html = render_section_banking(_banking_section(with_news=False))
    assert 'id="section-banking"' in html
    assert '<ul class="sec-news">' not in html


def test_section_banking_threshold_badge_npl_above_30():
    # npl = 32 → CRITICAL
    html_crit = render_section_banking(_banking_section(npl=32.0))
    assert "CRITICAL" in html_crit
    # npl = 22 → WATCH (above 20 but below 30)
    html_watch = render_section_banking(_banking_section(npl=22.0))
    assert "WATCH" in html_watch
    assert "CRITICAL" not in html_watch


def test_section_banking_rejects_wrong_id():
    section = _banking_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_banking(section)
