"""SectionDSE — DSEX close + breadth strip."""
from __future__ import annotations

from brief.render._jsx import bankerread_tag, fmt_num, freshness_pill
from brief.schema import SectionData


def render(section: SectionData) -> str:
    def find(mid: str):
        return next((m for m in section.metrics if m.id == mid), None)

    dsex = find("dse_dsex_close")
    change = find("dse_dsex_change_pct")
    advancing = find("dse_advancing")
    declining = find("dse_declining")

    dsex_line = (
        f'<MetricCard label="DSEX" '
        f'value="{fmt_num(dsex.value if dsex else None)}" '
        f'change="{fmt_num(change.value if change else None, 2)}%" />'
    )
    breadth_line = (
        f'<div className="breadth">Advancing {int(advancing.value) if advancing and advancing.value is not None else "—"} · '
        f'Declining {int(declining.value) if declining and declining.value is not None else "—"}</div>'
    )
    pill = freshness_pill(section.freshness)
    br = bankerread_tag(section.bankerread)
    return (
        "function SectionDSE() {\n"
        "  return (\n"
        '    <section id="section-dse">\n'
        f"      <h2>{section.title}{pill}</h2>\n"
        f"      {dsex_line}\n"
        f"      {breadth_line}\n"
        f"      {br}\n"
        "    </section>\n"
        "  );\n"
        "}"
    )
