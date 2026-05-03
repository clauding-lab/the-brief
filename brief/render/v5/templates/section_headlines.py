"""V5 §09 — Headlines.

Two render paths:
- **Newspaper layout** (Phase 2.1): when `section.extras["layout"]` carries a
  validated `{lead, right_rail, secondary}` payload from the Claude
  `headlines_layout_v5` call, the section renders LEAD + KEY POINTS box +
  4 right-rail items + 3 secondary items in a 2×2 newspaper grid.
- **Simple grid** (fallback): the original 1-lead + 6-bullet layout used
  when no layout payload is present (V4 path or when the layout call
  failed validation).
"""
from __future__ import annotations

from typing import Optional

from brief.render.v5._jsx import _attr_esc, _esc, news_bullet, source_badge
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import NewsItem, SectionData


def _first_n_words(text: str, n: int = 30) -> str:
    if not text:
        return ""
    parts = text.split()
    return " ".join(parts[:n])


def _escape_keep_b(s: str) -> str:
    """Escape user-facing HTML but preserve <b>...</b> emphasis from Claude."""
    return (
        _esc(s)
        .replace("&lt;b&gt;", "<b>")
        .replace("&lt;/b&gt;", "</b>")
    )


def _by_url(news: list[NewsItem]) -> dict[str, NewsItem]:
    return {n.url: n for n in news}


def _validate_layout_against_news(layout: dict, by_url: dict[str, NewsItem]) -> bool:
    """Defensive: if any URL in the layout is not in the news list, fall back."""
    try:
        urls = [layout["lead"]["url"], *layout["right_rail"], *layout["secondary"]]
    except (KeyError, TypeError):
        return False
    return all(u in by_url for u in urls)


def _hl_time_label(item: NewsItem) -> str:
    """Compact time label for hl-time footer ('05:40 BDT' or 'Apr 20')."""
    return item.published.strftime("%H:%M UTC")


def _render_lead(lead_item: NewsItem, key_points: list[str]) -> str:
    summary = getattr(lead_item, "summary", "") or ""
    dek = _first_n_words(summary, n=40) if summary else _first_n_words(lead_item.title, n=40)

    bullets_html = "".join(
        f'<li><span>{_escape_keep_b(kp)}</span></li>' for kp in key_points
    )
    keypts_html = (
        '<div class="keypts">'
        '<h4>Key points · for the book</h4>'
        f'<ul>{bullets_html}</ul>'
        '</div>'
    )

    return (
        '<article class="hl lead">'
        f'<div class="hl-tag">{source_badge(lead_item.source)}'
        f'<span class="hl-tag-name">{_esc(lead_item.source)}</span>'
        '<span class="hl-tag-role">Lead</span>'
        '</div>'
        f'<h3 class="hl-head"><a href="{_attr_esc(lead_item.url)}">{_esc(lead_item.title)}</a></h3>'
        f'<p class="hl-dek">{_esc(dek)}</p>'
        f'{keypts_html}'
        f'<div class="hl-time">{_esc(_hl_time_label(lead_item))}</div>'
        '</article>'
    )


def _render_rail_item(item: NewsItem) -> str:
    return (
        '<article class="hl hl-rail">'
        f'<div class="hl-tag">{source_badge(item.source)}'
        f'<span class="hl-tag-name">{_esc(item.source)}</span>'
        '</div>'
        f'<h4 class="hl-head"><a href="{_attr_esc(item.url)}">{_esc(item.title)}</a></h4>'
        f'<div class="hl-time">{_esc(_hl_time_label(item))}</div>'
        '</article>'
    )


def _render_secondary_item(item: NewsItem) -> str:
    summary = getattr(item, "summary", "") or ""
    dek = _first_n_words(summary, n=24) if summary else ""
    dek_html = f'<p class="hl-dek">{_esc(dek)}</p>' if dek else ""
    return (
        '<article class="hl hl-secondary">'
        f'<div class="hl-tag">{source_badge(item.source)}'
        f'<span class="hl-tag-name">{_esc(item.source)}</span>'
        '</div>'
        f'<h4 class="hl-head"><a href="{_attr_esc(item.url)}">{_esc(item.title)}</a></h4>'
        f'{dek_html}'
        f'<div class="hl-time">{_esc(_hl_time_label(item))}</div>'
        '</article>'
    )


def _render_newspaper_layout(layout: dict, news: list[NewsItem]) -> Optional[str]:
    """Build the 2-column lead+rail block plus the 3-up secondary row.

    Returns the assembled HTML, or None if the layout references unknown URLs.
    """
    by_url = _by_url(news)
    if not _validate_layout_against_news(layout, by_url):
        return None

    lead_item = by_url[layout["lead"]["url"]]
    rail_items = [by_url[u] for u in layout["right_rail"]]
    secondary_items = [by_url[u] for u in layout["secondary"]]

    lead_html = _render_lead(lead_item, layout["lead"].get("key_points", []))
    rail_html = "".join(_render_rail_item(n) for n in rail_items)
    secondary_html = "".join(_render_secondary_item(n) for n in secondary_items)

    return (
        '<div class="hl-newspaper">'
        '<div class="hl-newspaper-top">'
        f'{lead_html}'
        f'<div class="hl-rail">{rail_html}</div>'
        '</div>'
        f'<div class="hl-newspaper-secondary">{secondary_html}</div>'
        '</div>'
    )


def _render_simple_grid(section: SectionData) -> str:
    """Original layout: lead article + 6 bullets. Falls back when no V5 layout."""
    if not section.news:
        return ""
    lead = section.news[0]
    rest = section.news[1:7]
    dek_source = getattr(lead, "summary", "") or lead.title
    dek = _first_n_words(dek_source, n=30)
    lead_html = (
        f'<article class="hl-lead">'
        f'<div class="hl-lead-source">{source_badge(lead.source)}</div>'
        f'<h3 class="hl-lead-title"><a href="{_attr_esc(lead.url)}">{_esc(lead.title)}</a></h3>'
        f'<p class="hl-lead-dek">{_esc(dek)}</p>'
        f'</article>'
    )
    bullets_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in rest)
    return f'<div class="hl-grid">{lead_html}<ul class="sec-news">{bullets_html}</ul></div>'


def render_section_headlines(section: SectionData) -> str:
    if section.id != "headlines":
        raise ValueError(f"render_section_headlines received id={section.id!r}; expected 'headlines'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "headlines_count" in metrics_by_id:
        m = metrics_by_id["headlines_count"]
        try:
            count_val = int(m.value) if m.value is not None else 0
        except (TypeError, ValueError):
            count_val = 0
        pills.append(f'<span class="sum-pill"><span class="sum-key">HEADLINES</span> <strong>{count_val}</strong></span>')

    metric_cards_html = ""

    layout = section.extras.get("layout") if section.extras else None
    news_html = ""
    if layout and section.news:
        news_html = _render_newspaper_layout(layout, list(section.news)) or ""
    if not news_html:
        news_html = _render_simple_grid(section)

    return render_section_base(
        section,
        section_n="01",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=False,
    )
