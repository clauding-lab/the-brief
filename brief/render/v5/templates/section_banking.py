"""V5 §09 — Banking."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_banking(section: SectionData) -> str:
    if section.id != "banking":
        raise ValueError(f"render_section_banking received id={section.id!r}; expected 'banking'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "banking_npl_pct" in metrics_by_id:
        m = metrics_by_id["banking_npl_pct"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">NPL</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "banking_car_pct" in metrics_by_id:
        m = metrics_by_id["banking_car_pct"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">CAR</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "banking_npl_pct" in metrics_by_id:
        hero = metrics_by_id["banking_npl_pct"]
        badge = None
        if isinstance(hero.value, (int, float)):
            if hero.value > 30.0:
                badge = "CRITICAL"
            elif hero.value > 20.0:
                badge = "WATCH"
        hero_html = metric_hero_card(hero, badge=badge, supporting="BB quarterly release")

    supporting_cards = []
    if "banking_car_pct" in metrics_by_id:
        supporting_cards.append(metric_hero_card(metrics_by_id["banking_car_pct"]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="10",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
