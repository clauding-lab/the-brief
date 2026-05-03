"""V5 §13 — Food prices (DAM Bangladesh)."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_dam(section: SectionData) -> str:
    if section.id != "dam":
        raise ValueError(f"render_section_dam received id={section.id!r}; expected 'dam'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "dam_rice_coarse" in metrics_by_id:
        m = metrics_by_id["dam_rice_coarse"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">RICE</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "dam_flour" in metrics_by_id:
        m = metrics_by_id["dam_flour"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">FLOUR</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "dam_lentil" in metrics_by_id:
        m = metrics_by_id["dam_lentil"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">LENTIL</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "dam_rice_coarse" in metrics_by_id:
        hero = metrics_by_id["dam_rice_coarse"]
        # No threshold badge — V4 builder doesn't populate delta for mom-change check.
        hero_html = metric_hero_card(hero, badge=None, supporting="DAM weekly retail")

    supporting_cards = []
    for mid in ("dam_flour", "dam_lentil", "dam_oil"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="14",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
