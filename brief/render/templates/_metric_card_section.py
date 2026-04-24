"""Generic metric-card section renderer used by most templates."""
from __future__ import annotations

from brief.render._jsx import bankerread_tag, fmt_num, freshness_pill
from brief.schema import SectionData


def render_generic(section: SectionData, *, component_name: str,
                   dom_id: str) -> str:
    cards = [
        f'        <MetricCard label="{m.label}" '
        f'value="{fmt_num(m.value)}{m.unit}" />'
        for m in section.metrics
    ]
    cards_src = "\n".join(cards) if cards else '        <div className="empty">No data</div>'
    pill = freshness_pill(section.freshness)
    br = bankerread_tag(section.bankerread)
    return (
        f"function {component_name}() {{\n"
        "  return (\n"
        f'    <section id="{dom_id}">\n'
        f"      <h2>{section.title}{pill}</h2>\n"
        f"{cards_src}\n"
        f"      {br}\n"
        f"    </section>\n"
        "  );\n"
        "}"
    )
