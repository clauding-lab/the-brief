"""SectionHeadlines — renders a JS array literal of news items."""
from __future__ import annotations

from brief.render._jsx import bankerread_tag, freshness_pill
from brief.schema import SectionData


def _esc_js(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
         .replace('"', '&quot;')
         .replace("\n", " ")
    )


def render(section: SectionData) -> str:
    items = ",\n".join(
        f'    {{ title: "{_esc_js(n.title)}", url: "{_esc_js(n.url)}", '
        f'source: "{_esc_js(n.source)}", time: "{n.published.date().isoformat()}" }}'
        for n in section.news
    )
    array_literal = "[\n" + items + "\n  ]" if section.news else "[]"
    pill = freshness_pill(section.freshness)
    br = bankerread_tag(section.bankerread)
    return (
        "function SectionHeadlines() {\n"
        f"  const headlines = {array_literal};\n"
        "  return (\n"
        '    <section id="section-headlines">\n'
        f"      <h2>{section.title}{pill}</h2>\n"
        "      {headlines.map(h => (\n"
        '        <a key={h.url} href={h.url}>[{h.source}] {h.title} <time>{h.time}</time></a>\n'
        "      ))}\n"
        f"      {br}\n"
        "    </section>\n"
        "  );\n"
        "}"
    )
