"""V5 assemble — splice chrome + section fragments into shell_v5.html."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from brief.render.v5.chrome.colophon import render_colophon
from brief.render.v5.chrome.flow_index import render_flow_index
from brief.render.v5.chrome.front_of_book import render_front_of_book
from brief.render.v5.chrome.live_banner import render_live_banner
from brief.render.v5.chrome.masthead import render_masthead
from brief.render.v5.chrome.risk_map import render_risk_map
from brief.render.v5.chrome.secondary_grid import render_secondary_grid  # retained for back-compat; not rendered in V5 flow
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
    # FOB pinned to iranwar for now (per editorial decision 2026-05-02). Falls
    # back to whatever Claude's top_picks.front_of_book_id selected if iranwar
    # isn't in today's section_by_id.
    fob_section = section_by_id.get("iranwar") or section_by_id.get(top_picks.front_of_book_id)
    fob_html = ""
    if fob_section is not None:
        fob_html = render_front_of_book(fob_section, section_n=_section_n(fob_section.id))
    body_parts.append(f'<div class="map-row">{risk_map_html}{fob_html}</div>')

    # Flow index: 'The flow — as plotted'. Replaces the V4 'ALSO TODAY · 7 sections
    # not on the map' secondary grid (which is now retired from the front-of-book).
    section_titles = {sid: s.title for sid, s in section_by_id.items()}
    body_parts.append(render_flow_index(
        picks=top_picks,
        sections=sections_lookup,
        section_titles=section_titles,
    ))

    # Chapters render in numeric §01 → §14 order — the flow index above already
    # surfaces today's editorial priority. The chapter body is the reference
    # ordering (banker reads left-to-right by section number).
    plotted_ids = {top_picks.front_of_book_id, *(p.id for p in top_picks.plotted)}
    grid_ids = {g.id for g in top_picks.grid}
    all_ids = plotted_ids | grid_ids
    full_order = sorted(all_ids, key=lambda sid: _section_n(sid))

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
    mapping = {"headlines": "01", "exec": "02", "bb": "03", "macro": "04",
               "fx": "05", "remit": "06", "dse": "07", "tbond": "08",
               "iranwar": "09", "banking": "10", "comm": "11", "fiscal": "12",
               "nbr": "13", "dam": "14"}
    return mapping.get(section_id, "??")
