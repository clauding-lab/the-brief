"""V5 §01 — Headlines."""
from __future__ import annotations

from brief.render.v5._jsx import _attr_esc, _esc, news_bullet, source_badge
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def _first_n_words(text: str, n: int = 30) -> str:
    """Return the first n whitespace-separated words of text, joined by space."""
    if not text:
        return ""
    parts = text.split()
    return " ".join(parts[:n])


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

    news_html = ""
    if section.news:
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
        news_html = f'<div class="hl-grid">{lead_html}<ul class="sec-news">{bullets_html}</ul></div>'

    return render_section_base(
        section,
        section_n="01",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=False,
    )
