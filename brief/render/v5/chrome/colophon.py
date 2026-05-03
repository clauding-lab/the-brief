"""V5 colophon — bottom-of-page metadata strip."""
from __future__ import annotations

from typing import Any

from brief.render.v5._jsx import _esc


def render_colophon(meta: dict[str, Any]) -> str:
    duration_s = meta.get("render_duration_s", 0)
    minutes, seconds = divmod(int(duration_s), 60)
    duration_label = f"{minutes:02d}:{seconds:02d}"
    cost = meta.get("total_cost_usd", 0.0)

    sources = " · ".join(_esc(s) for s in meta.get("sources_used", []))

    return (
        '<footer class="colophon" aria-label="Edition metadata">'
        '<div class="col-row">'
        f'<span>VOL. {_esc(str(meta.get("vol", "")))}</span>'
        f'<span>NO. {meta.get("issue", "")}</span>'
        f'<span>{_esc(meta.get("today_label", ""))}</span>'
        '</div>'
        '<div class="col-row col-sources">'
        f'<span class="col-label">SOURCES</span> {sources}'
        '</div>'
        '<div class="col-row col-stats">'
        f'<span>RENDER {duration_label}</span>'
        f'<span>COST ${cost:.2f}</span>'
        '</div>'
        '</footer>'
    )
