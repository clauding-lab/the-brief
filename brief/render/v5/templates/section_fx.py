"""V5 §05 — FX & External (post-2026-05-03 V1-mockup layout).

USD/BDT mid is the hero. Surrounding compact cards are cross-section external-
balance metrics: gross reserves, trade gap, monthly exports, monthly remittance.
"""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_fx(section: SectionData) -> str:
    if section.id != "fx":
        raise ValueError(f"render_section_fx received id={section.id!r}; expected 'fx'")

    metrics_by_id = {m.id: m for m in section.metrics}

    # 3-pill summary: USD/BDT, Reserves, Remittance
    pills = []
    if "fx_usd_bdt_mid" in metrics_by_id:
        m = metrics_by_id["fx_usd_bdt_mid"]
        pills.append(
            f'<span class="sum-pill"><span class="sum-key">USD/BDT</span> '
            f'<strong>{fmt_num(m.value, unit=m.unit)}</strong></span>'
        )
    if "fx_gross_reserves" in metrics_by_id:
        m = metrics_by_id["fx_gross_reserves"]
        pills.append(
            f'<span class="sum-pill"><span class="sum-key">RESERVES</span> '
            f'<strong>{fmt_num(m.value, unit=m.unit)}</strong></span>'
        )
    if "fx_monthly_remittance" in metrics_by_id:
        m = metrics_by_id["fx_monthly_remittance"]
        pills.append(
            f'<span class="sum-pill"><span class="sum-key">REMIT</span> '
            f'<strong>{fmt_num(m.value, unit=m.unit)}</strong></span>'
        )

    # Hero: USD/BDT mid spot (the most-watched single rate for this market)
    hero_html = ""
    if "fx_usd_bdt_mid" in metrics_by_id:
        hero = metrics_by_id["fx_usd_bdt_mid"]
        badge = None
        if isinstance(hero.value, (int, float)) and hero.value > 124.0:
            badge = "WATCH"
        hero_html = metric_hero_card(hero, badge=badge, supporting="USD/BDT mid spot")

    # Compact supporting cards: external-balance row
    supporting_cards = []
    for mid in ("fx_gross_reserves", "fx_trade_gap",
                "fx_monthly_exports", "fx_monthly_remittance"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid], is_hero=False))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="05",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
