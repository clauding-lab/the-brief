from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_remit import render_section_remit
from brief.schema import Metric, NewsItem, SectionData


def _remit_section(*, with_metrics: bool = True, with_news: bool = True, yoy: float = 8.4) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="remit_monthly_mn", label="Monthly Remittance", value=2347.0, unit="mn USD",
                   as_of=date(2026, 3, 31), source="BB", cadence="monthly"),
            Metric(id="remit_yoy_pct",    label="YoY %",              value=yoy, unit="%",
                   as_of=date(2026, 3, 31), source="BB", cadence="monthly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="March remittances cross $2.3bn", url="https://example.com/remit1",
                     source="Prothom Alo", published=datetime(2026, 4, 1, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="remit", title="Remittance",
        kicker="REMITTANCES", tldr="Monthly: $2,347mn",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[2100, 2150, 2210, 2280, 2300, 2330, 2347],
    )


def test_section_remit_renders_with_full_metrics():
    html = render_section_remit(_remit_section())
    assert 'id="section-remit"' in html
    assert "§05" in html
    assert "REMITTANCES" in html
    assert "Remittance" in html
    assert "2347" in html or "2,347" in html
    assert "MONTHLY" in html
    assert "YoY%" in html


def test_section_remit_renders_with_no_metrics():
    html = render_section_remit(_remit_section(with_metrics=False))
    assert 'id="section-remit"' in html
    assert "metric-card" not in html


def test_section_remit_renders_with_no_news():
    html = render_section_remit(_remit_section(with_news=False))
    assert 'id="section-remit"' in html
    assert '<ul class="sec-news">' not in html


def test_section_remit_threshold_badge_yoy_below_minus_5():
    html = render_section_remit(_remit_section(yoy=-7.2))
    assert "WATCH" in html


def test_section_remit_rejects_wrong_id():
    section = _remit_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_remit(section)
