"""Tests for V4 section_headlines 3-tier template.

TDD: tests written before implementation (RED phase), implementation written
to make them pass (GREEN phase).

Layout verified:
  - 1 lead article (class "hl lead")
  - 4 compact right column items (inside <aside class="hl-right-column">)
  - 3 bottom row items (inside <div class="hl-bottom-row">)
  - KeyPoints card with ox-glyph § bullets
  - Italic-oxblood emphasis (<em class="italic-ox">) on lead title
  - BankerRead freeform aside (class "br-freeform")
  - Graceful degradation with fewer than 8 items
  - HTML escaping of malicious titles
"""
from __future__ import annotations

import html
from datetime import datetime, timezone

import pytest

from brief.schema import BankerReadFreeform, NewsItem, SectionData
from brief.render.v4.templates.section_headlines import render_section_headlines


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

def _make_news(n: int = 8) -> list[NewsItem]:
    sources = ["Daily Star", "bdnews24", "Prothom Alo", "Business Standard"]
    return [
        NewsItem(
            title=f"Test headline {i} with full phrase here",
            url=f"https://example.com/{i}",
            source=sources[i % 4],
            published=datetime(2026, 4, 24, 10 + i, 0, 0, tzinfo=timezone.utc),
        )
        for i in range(n)
    ]


def _headlines_section(n: int = 8, with_freeform_br: bool = True) -> SectionData:
    news = _make_news(n)
    br = (
        BankerReadFreeform(
            text="Reserves steady; policy on hold; expect CPI to print soft.",
            pull="Reserves steady; policy on hold.",
        )
        if with_freeform_br
        else None
    )
    return SectionData(
        id="headlines",
        title="Headlines",
        freshness="fresh",
        metrics=[],
        news=news,
        bankerread=br,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHeadlines8Items:
    """Happy path: 8 headlines → full 3-tier layout."""

    def test_lead_article_present(self) -> None:
        out = render_section_headlines(_headlines_section())
        assert 'class="hl lead"' in out

    def test_exactly_one_lead(self) -> None:
        out = render_section_headlines(_headlines_section())
        assert out.count('class="hl lead"') == 1

    def test_right_column_present(self) -> None:
        out = render_section_headlines(_headlines_section())
        assert 'class="hl-right-column"' in out

    def test_right_column_has_4_items(self) -> None:
        out = render_section_headlines(_headlines_section())
        # Each compact item has class "hl-compact"
        assert out.count('class="hl-compact"') == 4

    def test_bottom_row_present(self) -> None:
        out = render_section_headlines(_headlines_section())
        assert 'class="hl-bottom-row"' in out

    def test_bottom_row_has_3_items(self) -> None:
        out = render_section_headlines(_headlines_section())
        assert out.count('class="hl-bottom-item"') == 3

    def test_section_id_present(self) -> None:
        out = render_section_headlines(_headlines_section())
        assert 'id="section-headlines"' in out

    def test_numeral_01_in_head(self) -> None:
        out = render_section_headlines(_headlines_section())
        assert "01" in out


class TestKeyPoints:
    def test_key_points_block_present(self) -> None:
        out = render_section_headlines(_headlines_section())
        assert "Key points" in out

    def test_ox_glyph_present(self) -> None:
        out = render_section_headlines(_headlines_section())
        assert 'class="ox-glyph"' in out

    def test_ox_glyph_character(self) -> None:
        out = render_section_headlines(_headlines_section())
        assert "<span class=\"ox-glyph\">§</span>" in out

    def test_three_bullets(self) -> None:
        out = render_section_headlines(_headlines_section())
        # Each bullet contains the ox-glyph
        assert out.count('class="ox-glyph"') == 3


class TestItalicOxEmphasis:
    def test_italic_ox_em_present(self) -> None:
        out = render_section_headlines(_headlines_section())
        assert '<em class="italic-ox">' in out

    def test_italic_ox_is_inside_lead_title(self) -> None:
        out = render_section_headlines(_headlines_section())
        # Lead article must contain the em tag
        lead_start = out.index('class="hl lead"')
        em_pos = out.index('<em class="italic-ox">', lead_start)
        # Find lead article end (</article>)
        lead_end = out.index("</article>", lead_start)
        assert em_pos < lead_end

    def test_italic_ox_wraps_last_word(self) -> None:
        out = render_section_headlines(_headlines_section())
        # First headline title is "Test headline 0 with full phrase here"
        # Last word is "here" → should be in em tag
        assert '<em class="italic-ox">here</em>' in out


class TestBankerReadFreeform:
    def test_bankerread_aside_present(self) -> None:
        out = render_section_headlines(_headlines_section(with_freeform_br=True))
        assert "<aside" in out
        assert "bankerread" in out

    def test_bankerread_is_freeform(self) -> None:
        out = render_section_headlines(_headlines_section(with_freeform_br=True))
        assert "br-freeform" in out

    def test_bankerread_not_structured(self) -> None:
        out = render_section_headlines(_headlines_section(with_freeform_br=True))
        assert "br-structured" not in out

    def test_bankerread_content_present(self) -> None:
        out = render_section_headlines(_headlines_section(with_freeform_br=True))
        assert "Reserves steady" in out


class TestBankerReadNone:
    def test_no_bankerread_no_aside(self) -> None:
        out = render_section_headlines(_headlines_section(with_freeform_br=False))
        # Section should render but no bankerread aside
        assert "bankerread" not in out

    def test_section_still_renders(self) -> None:
        out = render_section_headlines(_headlines_section(with_freeform_br=False))
        assert 'id="section-headlines"' in out


class TestFewHeadlines:
    def test_5_items_lead_and_4_right_no_bottom(self) -> None:
        out = render_section_headlines(_headlines_section(n=5))
        assert out.count('class="hl lead"') == 1
        assert out.count('class="hl-compact"') == 4
        assert 'class="hl-bottom-row"' not in out

    def test_1_item_lead_only(self) -> None:
        out = render_section_headlines(_headlines_section(n=1))
        assert out.count('class="hl lead"') == 1
        assert out.count('class="hl-compact"') == 0
        assert 'class="hl-bottom-row"' not in out

    def test_0_items_no_crash(self) -> None:
        out = render_section_headlines(_headlines_section(n=0))
        # Should render the section shell without crashing
        assert 'id="section-headlines"' in out
        assert 'class="hl lead"' not in out

    def test_3_items_lead_and_2_right(self) -> None:
        out = render_section_headlines(_headlines_section(n=3))
        assert out.count('class="hl lead"') == 1
        assert out.count('class="hl-compact"') == 2


class TestHTMLEscaping:
    def test_malicious_title_escaped(self) -> None:
        news = [
            NewsItem(
                title='<script>alert("xss")</script> headline',
                url="https://example.com/0",
                source="Test",
                published=datetime(2026, 4, 24, 10, 0, tzinfo=timezone.utc),
            )
        ]
        section = SectionData(
            id="headlines",
            title="Headlines",
            freshness="fresh",
            metrics=[],
            news=news,
        )
        out = render_section_headlines(section)
        assert "<script>" not in out
        assert "&lt;script&gt;" in out or "alert" not in out

    def test_malicious_source_escaped(self) -> None:
        news = [
            NewsItem(
                title="Normal headline",
                url="https://example.com/0",
                source='<img src=x onerror=alert(1)>',
                published=datetime(2026, 4, 24, 10, 0, tzinfo=timezone.utc),
            )
        ]
        section = SectionData(
            id="headlines",
            title="Headlines",
            freshness="fresh",
            metrics=[],
            news=news,
        )
        out = render_section_headlines(section)
        assert "<img" not in out
