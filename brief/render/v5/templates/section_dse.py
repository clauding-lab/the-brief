"""V5 §06 — Equities (DSE) with sector heatmap."""
from __future__ import annotations

from brief.render.v5._jsx import (
    fmt_num,
    heatmap_svg,
    metric_hero_card,
    news_bullet,
)
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def _build_sector_heatmap_block(section: SectionData) -> str:
    """Build the sector heat-map block from extras.sector_heat (Phase 3.1).

    `extras.sector_heat` is a list of {sector, pct, as_of} dicts produced
    upstream by the DSE builder (which reads `dse_sector_heat` from the
    EconDelta snapshot). When the list is missing or empty, render nothing
    — the section gracefully falls back to its non-heatmap shape.
    """
    payload = (section.extras or {}).get("sector_heat") if section.extras else None
    if not isinstance(payload, list) or not payload:
        return ""
    heat_svg = heatmap_svg(payload)
    if not heat_svg:
        return ""
    first_as_of = next((p.get("as_of") for p in payload if p.get("as_of")), None)
    as_of_html = f' · <span class="hm-as-of">{first_as_of}</span>' if first_as_of else ""
    return (
        '<div class="sector-heatmap-card">'
        '<div class="hm-eyebrow">'
        f'<span>Sector heat · 1 day{as_of_html}</span>'
        '</div>'
        f'{heat_svg}'
        '</div>'
    )


def render_section_dse(section: SectionData) -> str:
    if section.id != "dse":
        raise ValueError(f"render_section_dse received id={section.id!r}; expected 'dse'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "dse_dsex_close" in metrics_by_id:
        m = metrics_by_id["dse_dsex_close"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">DSEX</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "dse_ds30" in metrics_by_id:
        m = metrics_by_id["dse_ds30"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">DS30</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "dse_turnover_crore" in metrics_by_id:
        m = metrics_by_id["dse_turnover_crore"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">TURNOVER</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "dse_dsex_close" in metrics_by_id:
        hero = metrics_by_id["dse_dsex_close"]
        badge = None
        adv = metrics_by_id.get("dse_advancing")
        dec = metrics_by_id.get("dse_declining")
        if (adv is not None and dec is not None
                and isinstance(adv.value, (int, float))
                and isinstance(dec.value, (int, float))
                and (adv.value + dec.value) > 0):
            breadth_pct = (adv.value / (adv.value + dec.value)) * 100
            if breadth_pct < 30:
                badge = "WATCH"
        hero_html = metric_hero_card(hero, badge=badge, supporting="DSE daily close")

    supporting_cards = []
    for mid in ("dse_ds30", "dse_dses", "dse_turnover_crore"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    heatmap_html = _build_sector_heatmap_block(section)
    if heatmap_html:
        metric_cards_html += heatmap_html

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="06",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
