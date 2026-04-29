"""V5 §03 — Macro & Inflation."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_macro(section: SectionData) -> str:
    if section.id != "macro":
        raise ValueError(f"render_section_macro received id={section.id!r}; expected 'macro'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "macro_cpi_headline" in metrics_by_id:
        m = metrics_by_id["macro_cpi_headline"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">CPI</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "macro_cpi_food" in metrics_by_id:
        m = metrics_by_id["macro_cpi_food"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">FOOD</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "macro_gdp_growth" in metrics_by_id:
        m = metrics_by_id["macro_gdp_growth"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">GDP</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "macro_cpi_headline" in metrics_by_id:
        hero = metrics_by_id["macro_cpi_headline"]
        badge = None
        if isinstance(hero.value, (int, float)) and hero.value > 10.0:
            badge = "CRITICAL"
        hero_html = metric_hero_card(hero, badge=badge, supporting="BBS monthly release")

    supporting_cards = []
    for mid in ("macro_cpi_food", "macro_gdp_growth", "macro_credit_growth"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="03",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
