"""V5 §10 — Commodities."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_comm(section: SectionData) -> str:
    if section.id != "comm":
        raise ValueError(f"render_section_comm received id={section.id!r}; expected 'comm'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "comm_gold_usd_oz" in metrics_by_id:
        m = metrics_by_id["comm_gold_usd_oz"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">GOLD</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "comm_gold_22k_bdt" in metrics_by_id:
        m = metrics_by_id["comm_gold_22k_bdt"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">GOLD 22K</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "comm_lng_jkm" in metrics_by_id:
        m = metrics_by_id["comm_lng_jkm"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">LNG</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "comm_gold_usd_oz" in metrics_by_id:
        hero = metrics_by_id["comm_gold_usd_oz"]
        # No threshold badge — spec wanted brent threshold; brent lives in iranwar builder.
        hero_html = metric_hero_card(hero, badge=None, supporting="EconDelta daily spot")

    supporting_cards = []
    for mid in ("comm_gold_22k_bdt", "comm_lng_jkm"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="11",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
