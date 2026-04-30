from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_headlines import render_section_headlines
from brief.schema import Metric, NewsItem, SectionData


def _headlines_section(*, with_metrics: bool = True, with_news: bool = True,
                       news_count: int = 8) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="headlines_count", label="Headlines count", value=news_count,
                   unit="items", as_of=date(2026, 4, 28), source="scraper", cadence="daily"),
        ]
    news: list[NewsItem] = []
    if with_news and news_count > 0:
        # Lead has a longer summary so the dek extraction is exercised.
        news.append(NewsItem(
            title="Bangladesh Bank holds policy rate at 10% for fourth consecutive meeting",
            url="https://example.com/lead",
            source="The Daily Star",
            published=datetime(2026, 4, 28, 9, 0, tzinfo=timezone.utc),
        ))
        for i in range(2, news_count + 1):
            news.append(NewsItem(
                title=f"Headline number {i}",
                url=f"https://example.com/h{i}",
                source="Reuters",
                published=datetime(2026, 4, 28, tzinfo=timezone.utc),
            ))
    return SectionData(
        id="headlines", title="Headlines",
        kicker="HEADLINES", tldr=f"{news_count} curated stories",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[],
    )


def test_section_headlines_renders_with_full_data():
    html = render_section_headlines(_headlines_section())
    assert 'id="section-headlines"' in html
    assert "§01" in html
    assert "HEADLINES" in html
    # Pill with the count
    assert "<strong>8</strong>" in html
    # Lead article block
    assert "hl-lead" in html
    assert "Bangladesh Bank holds policy rate" in html
    # Standard bullets follow (rest items 2..7 should appear; item 8 should be capped)
    assert "Headline number 2" in html
    assert "Headline number 7" in html
    assert "Headline number 8" not in html  # only 6 bullets after the lead
    # No metric_hero_card output
    assert "metric-card" not in html


def test_section_headlines_renders_with_no_metrics():
    html = render_section_headlines(_headlines_section(with_metrics=False))
    assert 'id="section-headlines"' in html
    # No metric pill when no metric (sum-pill is the pill class)
    assert '<span class="sum-pill">' not in html


def test_section_headlines_renders_with_no_news():
    html = render_section_headlines(_headlines_section(with_news=False))
    assert 'id="section-headlines"' in html
    assert "hl-lead" not in html
    assert "hl-grid" not in html


def test_section_headlines_no_threshold_badge_in_render():
    """Headlines has no hero metric; badge must never appear."""
    html_low  = render_section_headlines(_headlines_section(news_count=1))
    html_high = render_section_headlines(_headlines_section(news_count=99))
    assert "CRITICAL" not in html_low and "CRITICAL" not in html_high
    assert "WATCH" not in html_low and "WATCH" not in html_high


def test_section_headlines_rejects_wrong_id():
    section = _headlines_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_headlines(section)
