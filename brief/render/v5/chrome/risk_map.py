"""V5 risk map — SVG bubble plot of today's top-7 sections.

Coordinate system: x ∈ [0, 10] = movement today; y ∈ [0, 10] = significance.
Map drawn at viewBox 0 0 640 480. Sections lookup provides {kicker, n} per id.
"""
from __future__ import annotations

from typing import Any

from brief.render.v5._jsx import _attr_esc, _esc
from brief.render.v5._tokens import KIND_COLOR
from brief.schema import TopPicks

PLOT_X0, PLOT_Y0 = 80, 40
PLOT_W, PLOT_H = 480, 360


def _coord(x: float, y: float) -> tuple[float, float]:
    """Map (x ∈ [0,10], y ∈ [0,10]) → SVG pixel space."""
    px = PLOT_X0 + (x / 10.0) * PLOT_W
    py = PLOT_Y0 + ((10.0 - y) / 10.0) * PLOT_H
    return px, py


def render_risk_map(*, picks: TopPicks, sections: dict[str, dict[str, Any]], today_label: str) -> str:
    if len(picks.plotted) != 7:
        raise ValueError(f"render_risk_map expects exactly 7 plotted; got {len(picks.plotted)}")

    bubbles_html = []
    for point in picks.plotted:
        cx, cy = _coord(point.x, point.y)
        color = KIND_COLOR[point.kind]
        meta = sections.get(point.id, {"kicker": point.id, "n": ""})
        label_x = cx + point.r + 6
        label_y = cy + 4
        bubbles_html.append(
            f'<g class="rm-bubble rm-{point.kind}" data-id="{_attr_esc(point.id)}">'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{point.r}" fill="{color}"/>'
            f'<text class="rm-num" x="{cx:.1f}" y="{cy + 4:.1f}" text-anchor="middle" fill="var(--ink-inverse)">§{_esc(meta["n"])}</text>'
            f'<text class="rm-label" x="{label_x:.1f}" y="{label_y:.1f}">{_esc(meta["kicker"])}</text>'
            f'</g>'
        )

    fob = next((p for p in picks.plotted if p.id == picks.front_of_book_id), picks.plotted[0])
    fx, fy = _coord(fob.x, fob.y)
    arrow_x = fx + fob.r + 80
    arrow_y = fy
    bubbles_html.append(
        f'<g class="rm-readfirst">'
        f'<text x="{arrow_x:.1f}" y="{arrow_y:.1f}">read first ↗</text>'
        f'</g>'
    )

    quads = (
        (PLOT_X0 + 100, PLOT_Y0 + 30, "SLOW · STRUCTURAL"),
        (PLOT_X0 + PLOT_W - 100, PLOT_Y0 + 30, "ACTIVE · MATERIAL"),
        (PLOT_X0 + 100, PLOT_Y0 + PLOT_H - 20, "DORMANT"),
        (PLOT_X0 + PLOT_W - 100, PLOT_Y0 + PLOT_H - 20, "NOISE"),
    )
    quad_html = "".join(
        f'<text class="rm-quad" x="{x}" y="{y}" text-anchor="middle">{_esc(label)}</text>'
        for x, y, label in quads
    )

    axis_html = (
        f'<text class="rm-axis-x" x="{PLOT_X0 + PLOT_W / 2}" y="{PLOT_Y0 + PLOT_H + 32}" text-anchor="middle">MOVEMENT TODAY →</text>'
        f'<text class="rm-axis-y" x="{PLOT_X0 - 28}" y="{PLOT_Y0 + PLOT_H / 2}" transform="rotate(-90 {PLOT_X0 - 28} {PLOT_Y0 + PLOT_H / 2})" text-anchor="middle">SIGNIFICANCE FOR THE BOOK ↑</text>'
    )

    legend_html = (
        '<div class="rm-legend">'
        '<span class="rm-leg-item"><span class="dot dot-event"></span> EVENT</span>'
        '<span class="rm-leg-item"><span class="dot dot-fresh"></span> FRESH PRINT</span>'
        '<span class="rm-leg-item"><span class="dot dot-slow"></span> SLOW · STRUCTURAL</span>'
        '<span class="rm-leg-item"><span class="dot dot-anchor"></span> ANCHOR</span>'
        '</div>'
    )

    return (
        '<section class="risk-map" aria-label="Risk map">'
        '<header class="rm-header">'
        f'<span class="rm-eyebrow">§ RISK MAP · {_esc(today_label)}</span>'
        '<span class="rm-eyebrow-right">AREA ∝ READ-WEIGHT · COLOR = KIND</span>'
        '</header>'
        '<svg class="rm-svg" viewBox="0 0 640 480" role="img" aria-label="Risk map plotting today\'s seven sections">'
        f'<rect class="rm-quad-bg q-slow"   x="{PLOT_X0}" y="{PLOT_Y0}" width="{PLOT_W/2}" height="{PLOT_H/2}"/>'
        f'<rect class="rm-quad-bg q-event"  x="{PLOT_X0+PLOT_W/2}" y="{PLOT_Y0}" width="{PLOT_W/2}" height="{PLOT_H/2}"/>'
        f'<rect class="rm-quad-bg q-anchor" x="{PLOT_X0}" y="{PLOT_Y0+PLOT_H/2}" width="{PLOT_W/2}" height="{PLOT_H/2}"/>'
        f'<rect class="rm-quad-bg q-noise"  x="{PLOT_X0+PLOT_W/2}" y="{PLOT_Y0+PLOT_H/2}" width="{PLOT_W/2}" height="{PLOT_H/2}"/>'
        f'{quad_html}'
        f'{axis_html}'
        + "".join(bubbles_html) +
        '</svg>'
        f'{legend_html}'
        '</section>'
    )
