"""V5 §04 — FX & Reserves."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_fx(section: SectionData) -> str:
    if section.id != "fx":
        raise ValueError(f"render_section_fx received id={section.id!r}; expected 'fx'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "fx_usd_bdt_mid" in metrics_by_id:
        m = metrics_by_id["fx_usd_bdt_mid"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">USD/BDT</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "fx_eur_bdt" in metrics_by_id:
        m = metrics_by_id["fx_eur_bdt"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">EUR/BDT</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "fx_gbp_bdt" in metrics_by_id:
        m = metrics_by_id["fx_gbp_bdt"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">GBP/BDT</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "fx_usd_bdt_mid" in metrics_by_id:
        hero = metrics_by_id["fx_usd_bdt_mid"]
        badge = None
        if isinstance(hero.value, (int, float)) and hero.value > 124.0:
            badge = "WATCH"
        hero_html = metric_hero_card(hero, badge=badge, supporting="USD/BDT mid spot")

    supporting_cards = []
    for mid in ("fx_usd_bdt_buy", "fx_usd_bdt_sell", "fx_eur_bdt"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="04",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
