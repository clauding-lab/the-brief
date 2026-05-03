"""V5 §05 — Remittances."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_remit(section: SectionData) -> str:
    if section.id != "remit":
        raise ValueError(f"render_section_remit received id={section.id!r}; expected 'remit'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "remit_monthly_mn" in metrics_by_id:
        m = metrics_by_id["remit_monthly_mn"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">MONTHLY</span> <strong>${fmt_num(m.value)}MN</strong></span>')
    if "remit_yoy_pct" in metrics_by_id:
        m = metrics_by_id["remit_yoy_pct"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">YoY%</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "remit_monthly_mn" in metrics_by_id:
        hero = metrics_by_id["remit_monthly_mn"]
        badge = None
        yoy_metric = metrics_by_id.get("remit_yoy_pct")
        if yoy_metric is not None and isinstance(yoy_metric.value, (int, float)) and yoy_metric.value < -5.0:
            badge = "WATCH"
        hero_html = metric_hero_card(hero, badge=badge, supporting="BB monthly release")

    supporting_cards = []
    if "remit_yoy_pct" in metrics_by_id:
        supporting_cards.append(metric_hero_card(metrics_by_id["remit_yoy_pct"]))

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
