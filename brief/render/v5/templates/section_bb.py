"""V5 §02 — Bangladesh Bank (Policy & Rates)."""
from __future__ import annotations

from brief.render.v5._jsx import _esc, fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import Metric, SectionData


def render_section_bb(section: SectionData) -> str:
    if section.id != "bb":
        raise ValueError(f"render_section_bb received id={section.id!r}; expected 'bb'")

    metrics_by_id = {m.id: m for m in section.metrics}
    pills = []
    if "bb_policy_rate" in metrics_by_id:
        m = metrics_by_id["bb_policy_rate"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">POLICY RATE</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "bb_gross_reserves" in metrics_by_id:
        m = metrics_by_id["bb_gross_reserves"]
        delta_label = ""
        if m.delta:
            sign = "+" if m.delta.value > 0 else ""
            delta_label = f" {sign}{m.delta.value:.2f} {m.delta.window}"
        pills.append(f'<span class="sum-pill"><span class="sum-key">RESERVES</span> <strong>${fmt_num(m.value)}BN</strong>{_esc(delta_label)}</span>')

    hero_html = ""
    if "bb_gross_reserves" in metrics_by_id:
        reserves = metrics_by_id["bb_gross_reserves"]
        badge = None
        supporting_text = "BB H2 target: $36bn"
        if isinstance(reserves.value, (int, float)):
            if reserves.value < 32.0:
                badge = "CRITICAL"
            elif reserves.value < 34.0:
                badge = "WATCH"
        hero_html = metric_hero_card(reserves, badge=badge, supporting=supporting_text)

    supporting_cards = []
    for mid in ("bb_policy_rate", "bb_sdf", "bb_slf"):
        if mid in metrics_by_id:
            m = metrics_by_id[mid]
            supporting_cards.append(metric_hero_card(m))

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
