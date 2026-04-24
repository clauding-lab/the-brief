"""V4 Headlines section renderer (§01 MAJOR NEWS HEADLINES).

Implements a 3-tier editorial layout:
  - Lead article (first headline) with source badge, italic-oxblood emphasis on
    the last word of the title, a derived dek, KeyPoints card, and timestamp.
  - Right column (next 4 headlines) — compact items with source + title + time.
  - Bottom row (next 3 headlines) — items with a short dek.
  - Optional BankerRead aside (freeform variant) rendered at the end.

Layout structure:
    <section id="section-headlines">
      <header class="section-head">...</header>
      <div class="hl-grid">
        <article class="hl lead">...</article>
        <aside class="hl-right-column">...</aside>
        <div class="hl-bottom-row">...</div>
      </div>
      [bankerread_aside if section.bankerread]
    </section>

Italic-oxblood emphasis heuristic:
    The last word (split on whitespace) of the lead title is wrapped in
    <em class="italic-ox">...</em>.  This is a deliberate editorial heuristic
    — not semantic — and is documented as such.

BankerRead:
    If section.bankerread is set it is rendered via _jsx.bankerread_aside with
    anchor="01" and anchor_label="§01 Headlines".  Both freeform (expected) and
    structured (defensive fallback) kinds are handled by bankerread_aside.

All user-supplied text is HTML-escaped before insertion.
"""
from __future__ import annotations

import html as _html
from datetime import datetime, timezone

from brief.render.v4._jsx import bankerread_aside, section_head, staleness_dot
from brief.render.v4.templates._generic import (
    _SECTION_META,
    _freshness_pill_html,
    _freshness_to_dot_state,
)
from brief.schema import NewsItem, SectionData

_NUMERAL = "01"
_KICKER = "MAJOR NEWS HEADLINES"
_TITLE = "Headlines"
_ANCHOR = "section-headlines"
_BR_ANCHOR = "01"
_BR_LABEL = "§01 Headlines"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    return _html.escape(s, quote=False)


def _attr_esc(s: str) -> str:
    return _html.escape(s, quote=True)


def _fmt_time(dt: datetime) -> str:
    """Return human-readable publish time: 'Apr 24 · 10:15'."""
    return dt.strftime("%b %-d · %H:%M")


def _iso_time(dt: datetime) -> str:
    return dt.isoformat()


def _italic_ox_last_word(title: str) -> str:
    """Wrap the last whitespace-delimited word in <em class="italic-ox">.</em>.

    If the title has only one word, the whole title is wrapped.
    This is a deliberate editorial heuristic — not semantic markup.
    """
    words = title.split(" ")
    if len(words) == 1:
        return f'<em class="italic-ox">{_esc(title)}</em>'
    first_part = " ".join(words[:-1])
    last_word = words[-1]
    return f"{_esc(first_part)} <em class=\"italic-ox\">{_esc(last_word)}</em>"


def _dek(title: str, max_chars: int = 160) -> str:
    """Derive a short dek from the title — first max_chars chars."""
    return title[:max_chars]


def _source_badge(source: str) -> str:
    return f'<span class="source-badge">{_esc(source)}</span>'


def _time_element(dt: datetime) -> str:
    return (
        f'<time datetime="{_attr_esc(_iso_time(dt))}">'
        f"{_esc(_fmt_time(dt))}"
        f"</time>"
    )


# ---------------------------------------------------------------------------
# Lead article
# ---------------------------------------------------------------------------

def _render_lead(item: NewsItem, key_point_items: list[NewsItem]) -> str:
    """Render the lead article card."""
    title_html = _italic_ox_last_word(item.title)
    dek_text = _dek(item.title)

    # KeyPoints bullets — derived from the next items (or stubbed if <3 available)
    bullets: list[str] = []
    for kp in key_point_items[:3]:
        bullets.append(
            f'<li><span class="ox-glyph">§</span> {_esc(kp.title)}</li>'
        )
    # Pad to at least 1 bullet if none available
    if not bullets:
        bullets.append('<li><span class="ox-glyph">§</span> See full story.</li>')

    bullets_html = "\n".join(bullets)
    key_points_html = (
        '<div class="hl-key-points">'
        '<div class="kp-head">Key points · for the book</div>'
        f"<ul>{bullets_html}</ul>"
        "</div>"
    )

    return (
        '<article class="hl lead">'
        '<div class="hl-meta">'
        + _source_badge(item.source)
        + '<span class="lead-marker">LEAD</span>'
        "</div>"
        f'<h3 class="hl-title">{title_html}</h3>'
        f'<p class="hl-dek">{_esc(dek_text)}</p>'
        + key_points_html
        + _time_element(item.published)
        + "</article>"
    )


# ---------------------------------------------------------------------------
# Right column (4 compact items)
# ---------------------------------------------------------------------------

def _render_compact_item(item: NewsItem) -> str:
    return (
        '<div class="hl-compact">'
        + _source_badge(item.source)
        + f'<p class="hl-title-sm">{_esc(item.title)}</p>'
        + _time_element(item.published)
        + "</div>"
    )


def _render_right_column(items: list[NewsItem]) -> str:
    if not items:
        return '<aside class="hl-right-column"></aside>'
    inner = "".join(_render_compact_item(i) for i in items)
    return f'<aside class="hl-right-column">{inner}</aside>'


# ---------------------------------------------------------------------------
# Bottom row (3 items with dek)
# ---------------------------------------------------------------------------

def _render_bottom_item(item: NewsItem) -> str:
    return (
        '<div class="hl-bottom-item">'
        + _source_badge(item.source)
        + f'<p class="hl-title-sm">{_esc(item.title)}</p>'
        + f'<p class="hl-dek">{_esc(_dek(item.title))}</p>'
        + _time_element(item.published)
        + "</div>"
    )


def _render_bottom_row(items: list[NewsItem]) -> str:
    if not items:
        return ""
    inner = "".join(_render_bottom_item(i) for i in items)
    return f'<div class="hl-bottom-row">{inner}</div>'


# ---------------------------------------------------------------------------
# Public renderer
# ---------------------------------------------------------------------------

def render_section_headlines(
    section: "SectionData",
    curation: dict | None = None,
) -> str:
    """Headlines (§01): 3-tier layout — lead, right column (4), bottom row (3) + freeform BankerRead.

    Split logic:
      - Lead: section.news[0]
      - Right column: section.news[1:5]
      - Bottom row: section.news[5:8]
      - KeyPoints bullets: derived from the first 3 items of the right column.

    The `curation` argument is accepted for future integration (ignored in MVP).
    """
    news = section.news or []

    # Section head
    meta = _SECTION_META["headlines"]
    numeral = meta[0]
    kicker = meta[1]
    title = meta[2]

    dot_state = _freshness_to_dot_state(section.freshness)
    dot_html = staleness_dot(dot_state)
    fresh_pill = _freshness_pill_html(section.freshness, section.freshness_reason)
    meta_pills = [dot_html]
    if fresh_pill:
        meta_pills.append(fresh_pill)

    head_html = section_head(
        numeral=numeral,
        kicker=kicker,
        title_parts=[(title, "plain")],
        dek=section.freshness_reason or "",
        meta=meta_pills,
    )

    # Grid
    if news:
        lead = news[0]
        right_items = news[1:5]
        bottom_items = news[5:8]
        # KeyPoints source: right_items (first 3) or bottom_items as fallback
        kp_source = (right_items + bottom_items)[:3]
        lead_html = _render_lead(lead, kp_source)
    else:
        lead_html = ""
        right_items = []
        bottom_items = []

    right_html = _render_right_column(right_items)
    bottom_html = _render_bottom_row(bottom_items)

    grid_html = (
        '<div class="hl-grid">'
        + lead_html
        + right_html
        + bottom_html
        + "</div>"
    )

    # BankerRead aside
    br_html = ""
    if section.bankerread:
        br_html = bankerread_aside(
            section.bankerread,
            anchor=_BR_ANCHOR,
            anchor_label=_BR_LABEL,
        )

    return (
        f'<section class="section section-headlines" id="{_ANCHOR}">'
        + head_html
        + grid_html
        + br_html
        + "</section>"
    )
