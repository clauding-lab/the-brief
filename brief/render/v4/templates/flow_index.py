"""V4 Flow Index template — read-order grid, 2 rows x 6 cols desktop."""
from __future__ import annotations

import html

from brief.schema import SectionData

# ---------------------------------------------------------------------------
# Section numeral mapping
# ---------------------------------------------------------------------------

_SECTION_NUMERAL: dict[str, str] = {
    "headlines": "01",
    "bb": "02",
    "banking": "03",
    "dse": "04",
    "tbond": "05",
    "fx": "06",
    "macro": "07",
    "dam": "08",
    "comm": "09",
    "remit": "10",
    "iranwar": "14",
    "fiscal": "15",
    "nbr": "16",
    "exec": "00",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def _attr_esc(s: str) -> str:
    return html.escape(s, quote=True)


def _section_numeral(sid: str) -> str:
    return _SECTION_NUMERAL.get(sid, "—")  # em-dash fallback


def _section_upper(sid: str, sections: dict[str, SectionData]) -> str:
    section = sections.get(sid)
    if section and section.title:
        return section.title.upper()
    return sid.upper()


def _section_title(sid: str, sections: dict[str, SectionData]) -> str:
    section = sections.get(sid)
    if section and section.title:
        return section.title
    return sid


# ---------------------------------------------------------------------------
# Public render function
# ---------------------------------------------------------------------------

def render_flow_index(
    read_order: list[str],
    sections: dict[str, SectionData],
) -> str:
    """N-entry (plan targets 12) read-order grid, 2 rows x 6 cols desktop (CSS)."""
    items: list[str] = []
    for idx, sid in enumerate(read_order):
        rank = f"{idx + 1:02d}"
        numeral = _esc(_section_numeral(sid))
        section_upper = _esc(_section_upper(sid, sections))
        title = _esc(_section_title(sid, sections))
        anchor = _attr_esc(f"section-{sid.lower()}")

        kicker_text = f"§{numeral} · {section_upper}"  # §NN · SECTION

        item = (
            f'<li class="flow-entry">'
            f'<a href="#{anchor}" class="flow-idx-item">'
            f'<span class="flow-rank flow-idx-rank">{_esc(rank)}</span>'
            f'<span class="flow-kicker flow-idx-kicker">{_esc(kicker_text)}</span>'
            f'<span class="flow-title flow-idx-title">{title}</span>'
            f"</a>"
            f"</li>"
        )
        items.append(item)

    list_html = (
        '<ol class="flow-list flow-index-grid">'
        + "".join(items)
        + "</ol>"
    )

    head = (
        '<h2 class="flow-head flow-index-title">'
        "Flow Index"
        '<span class="flow-sub"> &middot; Today&#39;s read order</span>'
        "</h2>"
    )

    return (
        '<section class="flow-index" aria-label="Flow Index">'
        + head
        + list_html
        + "</section>"
    )
