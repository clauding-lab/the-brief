"""V5 §14 — Executive Signals."""
from __future__ import annotations

from brief.render.v5._jsx import _attr_esc, _esc
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


_EXEC_DIRECTION_ARROW = {
    "bull": "▲",
    "bear": "▼",
    "warn": "⚠",
    "watch": "◐",
}

_EXEC_ANCHOR_TO_N = {
    "headlines": "01", "bb": "02", "macro": "03", "fx": "04",
    "remit": "05", "dse": "06", "tbond": "07", "iranwar": "08",
    "banking": "09", "comm": "10", "fiscal": "11", "nbr": "12",
    "dam": "13", "exec": "14",
}


def render_section_exec(section: SectionData) -> str:
    if section.id != "exec":
        raise ValueError(f"render_section_exec received id={section.id!r}; expected 'exec'")

    pills: list[str] = []
    metric_cards_html = ""

    signals = section.exec_signals or []
    signals_html = ""
    if signals:
        items = []
        for sig in signals:
            arrow = _EXEC_DIRECTION_ARROW.get(sig.direction, "◐")
            anchor_n = _EXEC_ANCHOR_TO_N.get(sig.section_anchor, "??")
            items.append(
                f'<li class="exec-signal exec-signal-{_attr_esc(sig.direction)}">'
                f'<span class="exec-arrow">{_esc(arrow)}</span>'
                f'<span class="exec-text">{_esc(sig.text)}</span>'
                f'<a class="exec-anchor" href="#section-{_attr_esc(sig.section_anchor)}">→ §{_esc(anchor_n)}</a>'
                f'</li>'
            )
        signals_html = f'<ul class="exec-signals">{"".join(items)}</ul>'

    return render_section_base(
        section,
        section_n="14",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=signals_html,
        show_sparkline=False,
    )
