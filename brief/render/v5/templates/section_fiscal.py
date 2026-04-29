"""V5 §11 — Fiscal."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_fiscal(section: SectionData) -> str:
    if section.id != "fiscal":
        raise ValueError(f"render_section_fiscal received id={section.id!r}; expected 'fiscal'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "fiscal_nbr_collected_trn" in metrics_by_id:
        m = metrics_by_id["fiscal_nbr_collected_trn"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">COLLECTED</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "fiscal_adp_pct" in metrics_by_id:
        m = metrics_by_id["fiscal_adp_pct"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">ADP</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "fiscal_govt_borrow_trn" in metrics_by_id:
        m = metrics_by_id["fiscal_govt_borrow_trn"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">BORROW</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "fiscal_nbr_collected_trn" in metrics_by_id:
        hero = metrics_by_id["fiscal_nbr_collected_trn"]
        # No threshold badge — current builder has no deficit/pace metric.
        hero_html = metric_hero_card(hero, badge=None, supporting="NBR YTD vs annual target")

    supporting_cards = []
    for mid in ("fiscal_nbr_target_trn", "fiscal_adp_pct", "fiscal_govt_borrow_trn"):
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
