"""V5 §12 — Tax & Customs (NBR)."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_nbr(section: SectionData) -> str:
    if section.id != "nbr":
        raise ValueError(f"render_section_nbr received id={section.id!r}; expected 'nbr'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "nbr_vat_bn" in metrics_by_id:
        m = metrics_by_id["nbr_vat_bn"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">VAT</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "nbr_it_bn" in metrics_by_id:
        m = metrics_by_id["nbr_it_bn"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">IT</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "nbr_customs_bn" in metrics_by_id:
        m = metrics_by_id["nbr_customs_bn"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">CUSTOMS</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "nbr_vat_bn" in metrics_by_id:
        hero = metrics_by_id["nbr_vat_bn"]
        # No threshold badge — current builder has no FYTD/target metric to threshold against.
        hero_html = metric_hero_card(hero, badge=None, supporting="NBR monthly composition")

    supporting_cards = []
    for mid in ("nbr_it_bn", "nbr_customs_bn"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="12",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
