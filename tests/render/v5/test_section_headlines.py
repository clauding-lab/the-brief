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


# ── newspaper layout (Phase 2.1) ────────────────────────────────────────────

def _layout_payload(news_count: int = 8) -> dict:
    return {
        "lead": {
            "url": "https://example.com/lead",
            "key_points": [
                "Insurer <b>war-risk premia up 18%</b> — review aviation lines.",
                "<b>Brent $95.10</b>; CPI food feed-through ~6 weeks.",
                "<b>BSEC</b> policy pricing review at 10:00 BDT.",
            ],
        },
        "right_rail": [f"https://example.com/h{i}" for i in range(2, 6)],
        "secondary": [f"https://example.com/h{i}" for i in range(6, 9)],
    }


def _section_with_layout() -> SectionData:
    s = _headlines_section()
    # Make news urls predictable so the layout can reference them
    new_news = []
    for i, n in enumerate(s.news, start=1):
        url = "https://example.com/lead" if i == 1 else f"https://example.com/h{i}"
        new_news.append(n.model_copy(update={"url": url}))
    s = s.model_copy(update={"news": new_news})
    s.extras["layout"] = _layout_payload(len(new_news))
    return s


def test_newspaper_layout_renders_lead_with_key_points_box():
    html = render_section_headlines(_section_with_layout())
    # New 2x2 grid container present
    assert "hl-newspaper" in html
    # LEAD article element present
    assert 'class="hl lead"' in html
    # KEY POINTS dark box renders with all 3 bullets
    assert "keypts" in html
    assert "war-risk premia up 18%" in html
    assert "Brent $95.10" in html
    assert "BSEC" in html


def test_newspaper_layout_renders_right_rail_4_items():
    html = render_section_headlines(_section_with_layout())
    # 4 right-rail mini-headlines
    rail_count = html.count('class="hl hl-rail"')
    assert rail_count == 4


def test_newspaper_layout_renders_secondary_3_items():
    html = render_section_headlines(_section_with_layout())
    secondary_count = html.count('class="hl hl-secondary"')
    assert secondary_count == 3


def test_newspaper_layout_keypoints_keep_bold_html():
    html = render_section_headlines(_section_with_layout())
    # <b>...</b> tags from the prompt make it through to render
    assert "<b>war-risk premia up 18%</b>" in html
    assert "<b>Brent $95.10</b>" in html


def test_falls_back_to_simple_grid_when_no_layout():
    # No layout in extras → existing hl-grid path (lead + bullets)
    html = render_section_headlines(_headlines_section())
    assert "hl-newspaper" not in html
    assert "hl-grid" in html


def test_layout_with_unknown_lead_url_falls_back():
    """Renderer is defensive: if the layout references a url not in news,
    skip the layout and use the simple grid."""
    s = _headlines_section()
    s.extras["layout"] = {
        "lead": {"url": "https://gone.example/x", "key_points": ["a", "b", "c"]},
        "right_rail": ["x", "y", "z", "w"],
        "secondary": ["a", "b", "c"],
    }
    html = render_section_headlines(s)
    assert "hl-newspaper" not in html
    assert "hl-grid" in html
