"""V5 assemble — splice chrome + section fragments into shell_v5.html."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from brief.render.v5.chrome.colophon import render_colophon
from brief.render.v5.chrome.front_of_book import render_front_of_book
from brief.render.v5.chrome.live_banner import render_live_banner
from brief.render.v5.chrome.masthead import render_masthead
from brief.render.v5.chrome.risk_map import render_risk_map
from brief.render.v5.chrome.secondary_grid import render_secondary_grid
from brief.schema import SectionData, TodaysCall, TopPicks

V5_DIR = Path(__file__).parent
SHELL = V5_DIR / "shell_v5.html"
TOKENS = V5_DIR / "tokens.css"
STYLES = V5_DIR / "styles.css"


def assemble_v5(
    *,
    sections: list[SectionData],
    section_renderers: dict[str, Callable[[SectionData], str]],
    v4_renderer_fallback: Callable[[SectionData], str],
    top_picks: TopPicks,
    todays_call: TodaysCall,
    live: dict[str, Any],
    run_meta: dict[str, Any],
    today_label: str,
) -> str:
    section_by_id = {s.id: s for s in sections}
    sections_lookup = {s.id: {"kicker": s.kicker, "n": _section_n(s.id)} for s in sections}

    body_parts = []
    body_parts.append(render_live_banner(live))
    body_parts.append(render_masthead(
        vol=str(run_meta.get("vol", "II")),
        issue=int(run_meta.get("issue", 1)),
        today_label=today_label,
        todays_call=todays_call,
    ))

    risk_map_html = render_risk_map(picks=top_picks, sections=sections_lookup, today_label=today_label)
    fob_section = section_by_id.get(top_picks.front_of_book_id)
    fob_html = ""
    if fob_section is not None:
        fob_html = render_front_of_book(fob_section, section_n=_section_n(fob_section.id))
    body_parts.append(f'<div class="map-row">{risk_map_html}{fob_html}</div>')

    body_parts.append(render_secondary_grid(picks=top_picks, sections=section_by_id))

    plotted_ids_in_order = [top_picks.front_of_book_id] + [
        p.id for p in top_picks.plotted if p.id != top_picks.front_of_book_id
    ]
    grid_ids = [g.id for g in top_picks.grid]
    full_order = plotted_ids_in_order + grid_ids

    for sid in full_order:
        section = section_by_id.get(sid)
        if section is None:
            continue
        renderer = section_renderers.get(sid, v4_renderer_fallback)
        body_parts.append(renderer(section))

    body_parts.append(render_colophon({
        **run_meta,
        "today_label": today_label,
    }))

    body = "\n".join(body_parts)

    shell = SHELL.read_text()
    return (shell
        .replace("{{title}}", "The Brief")
        .replace("{{tokens_css}}", TOKENS.read_text())
        .replace("{{styles_css}}", STYLES.read_text())
        .replace("{{body}}", body)
    )


def _section_n(section_id: str) -> str:
    mapping = {"headlines": "01", "bb": "02", "macro": "03", "fx": "04",
               "remit": "05", "dse": "06", "tbond": "07", "iranwar": "08",
               "banking": "09", "comm": "10", "fiscal": "11", "nbr": "12",
               "dam": "13", "exec": "14"}
    return mapping.get(section_id, "??")
