"""Render function body for SectionBB."""
from __future__ import annotations

from brief.render._jsx import bankerread_tag, fmt_num, freshness_pill
from brief.schema import SectionData


def render(section: SectionData) -> str:
    cards = []
    for m in section.metrics:
        cards.append(
            f'        <MetricCard label="{m.label}" '
            f'value="{fmt_num(m.value)}{m.unit}" />'
        )
    pill = freshness_pill(section.freshness)
    br_tag = bankerread_tag(section.bankerread)
    cards_src = "\n".join(cards)
    return (
        "function SectionBB() {\n"
        "  return (\n"
        f'    <section id="section-bb">\n'
        f"      <h2>{section.title}{pill}</h2>\n"
        f"{cards_src}\n"
        f"      {br_tag}\n"
        f"    </section>\n"
        "  );\n"
        "}"
    )
