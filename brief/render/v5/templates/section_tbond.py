"""V5 §07 — Treasury (T-Bonds & T-Bills)."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_tbond(section: SectionData) -> str:
    if section.id != "tbond":
        raise ValueError(f"render_section_tbond received id={section.id!r}; expected 'tbond'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "tbond_bond_10y" in metrics_by_id:
        m = metrics_by_id["tbond_bond_10y"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">10Y</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "tbond_bond_5y" in metrics_by_id:
        m = metrics_by_id["tbond_bond_5y"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">5Y</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "tbond_tbill_91d" in metrics_by_id:
        m = metrics_by_id["tbond_tbill_91d"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">91D</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "tbond_bond_10y" in metrics_by_id:
        hero = metrics_by_id["tbond_bond_10y"]
        badge = None
        if isinstance(hero.value, (int, float)) and hero.value > 12.0:
            badge = "WATCH"
        hero_html = metric_hero_card(hero, badge=badge, supporting="BB weekly auction")

    supporting_cards = []
    for mid in ("tbond_bond_5y", "tbond_tbill_364d", "tbond_tbill_91d"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="07",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
