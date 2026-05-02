"""V5 risk map — SVG bubble plot of today's top-7 sections.

Coordinate system: x ∈ [0, 10] = movement today; y ∈ [0, 10] = significance.
Faithful port of the V4 Map-Front mockup's RiskMap component:
  - viewBox 760×420 with padL/R/T/B insets
  - 4-color quadrant fills (slow / event / anchor / noise)
  - dotted grid at every integer 1..9
  - solid axes + ticks at 0, 2.5, 5, 7.5, 10
  - quadrant captions positioned at TOP of each quadrant (y=8.8 in data space)
  - dotted oxblood diagonal (read-first guide) from (4,10) → (10,4)
  - filled bubbles with §N inside, kicker label ABOVE the bubble
"""
from __future__ import annotations

from typing import Any

from brief.render.v5._jsx import _attr_esc, _esc
from brief.schema import TopPicks

# SVG viewBox + plot insets (matches mockup pixel-for-pixel)
W, H = 760, 420
PAD_L, PAD_R, PAD_T, PAD_B = 64, 30, 36, 56

# Bubble fill colors keyed on kind
_KIND_FILL = {
    "event":   "#6b1f27",  # oxblood
    "anchor":  "#171310",  # ink
    "slow":    "#b57a15",  # mustard
    "fresh":   "#2f6b3a",  # green
}
# Bubble label color — slow uses ink (mustard bg too light for cream text)
_KIND_LABEL_FILL = {"slow": "#171310"}


def _x(v: float) -> float:
    return PAD_L + (v / 10.0) * (W - PAD_L - PAD_R)


def _y(v: float) -> float:
    return H - PAD_B - (v / 10.0) * (H - PAD_T - PAD_B)


def _grid_lines() -> str:
    """Dotted grid at every integer 1..9 in data space."""
    parts = []
    for v in range(1, 10):
        gx, gy = _x(v), _y(v)
        parts.append(
            f'<line x1="{gx:.1f}" x2="{gx:.1f}" y1="{PAD_T}" y2="{H - PAD_B}" '
            f'stroke="#cfc4a4" stroke-width=".5" stroke-dasharray="2 3"/>'
            f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{gy:.1f}" y2="{gy:.1f}" '
            f'stroke="#cfc4a4" stroke-width=".5" stroke-dasharray="2 3"/>'
        )
    return "".join(parts)


def _axes_and_ticks() -> str:
    """Solid x/y axes + tick marks + numeric labels at 0, 2.5, 5, 7.5, 10."""
    parts = [
        # solid axes
        f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{H - PAD_B}" y2="{H - PAD_B}" stroke="#171310" stroke-width="1.2"/>',
        f'<line x1="{PAD_L}" x2="{PAD_L}" y1="{PAD_T}" y2="{H - PAD_B}" stroke="#171310" stroke-width="1.2"/>',
    ]
    for v in (0, 2.5, 5, 7.5, 10):
        tx, ty = _x(v), _y(v)
        # x-axis tick + label
        parts.append(
            f'<line x1="{tx:.1f}" x2="{tx:.1f}" y1="{H - PAD_B}" y2="{H - PAD_B + 4}" stroke="#171310" stroke-width="1"/>'
            f'<text x="{tx:.1f}" y="{H - PAD_B + 16}" text-anchor="middle" font-size="9" '
            f'font-family="JetBrains Mono,monospace" fill="#6c6358">{int(v) if v.is_integer() else v}</text>'
        )
        # y-axis tick + label
        parts.append(
            f'<line x1="{PAD_L - 4}" x2="{PAD_L}" y1="{ty:.1f}" y2="{ty:.1f}" stroke="#171310" stroke-width="1"/>'
            f'<text x="{PAD_L - 8}" y="{ty + 3:.1f}" text-anchor="end" font-size="9" '
            f'font-family="JetBrains Mono,monospace" fill="#6c6358">{int(v) if v.is_integer() else v}</text>'
        )
    return "".join(parts)


def _quadrant_fills_and_captions() -> str:
    """4-color quadrant rectangles + caption labels at top of each quadrant."""
    midX = _x(5)
    midY = _y(5)
    parts = [
        # quadrant fills
        f'<rect x="{PAD_L}" y="{PAD_T}" width="{midX - PAD_L:.1f}" height="{midY - PAD_T:.1f}" fill="#f3ede0"/>',
        f'<rect x="{midX:.1f}" y="{PAD_T}" width="{W - PAD_R - midX:.1f}" height="{midY - PAD_T:.1f}" fill="#f0e3df"/>',
        f'<rect x="{PAD_L}" y="{midY:.1f}" width="{midX - PAD_L:.1f}" height="{H - PAD_B - midY:.1f}" fill="#f5f0e4"/>',
        f'<rect x="{midX:.1f}" y="{midY:.1f}" width="{W - PAD_R - midX:.1f}" height="{H - PAD_B - midY:.1f}" fill="#efe8d8"/>',
    ]
    # quadrant captions — at top of each quadrant
    for vx, vy, label in (
        (2.5, 8.8, "SLOW · STRUCTURAL"),
        (7.5, 8.8, "ACTIVE · MATERIAL"),
        (2.5, 1.4, "DORMANT"),
        (7.5, 1.4, "NOISE"),
    ):
        parts.append(
            f'<text x="{_x(vx):.1f}" y="{_y(vy):.1f}" text-anchor="middle" font-size="9.5" '
            f'letter-spacing="3" font-family="JetBrains Mono,monospace" fill="#a29785">{label}</text>'
        )
    return "".join(parts)


def _axis_labels() -> str:
    """Mono-cap axis labels."""
    return (
        f'<text x="{W - PAD_R}" y="{H - PAD_B + 32}" text-anchor="end" font-size="10" '
        f'letter-spacing="2" font-family="JetBrains Mono,monospace" fill="#171310" font-weight="600">'
        f'MOVEMENT TODAY →</text>'
        f'<g transform="translate({PAD_L - 44},{(PAD_T + H - PAD_B) / 2:.1f}) rotate(-90)">'
        f'<text font-size="10" letter-spacing="2" text-anchor="middle" '
        f'font-family="JetBrains Mono,monospace" fill="#171310" font-weight="600">'
        f'SIGNIFICANCE FOR THE BOOK →</text></g>'
    )


def _read_first_diagonal() -> str:
    """Dotted oxblood diagonal from (4,10) to (10,4) + 'read first ↗' label."""
    return (
        f'<line x1="{_x(4):.1f}" y1="{_y(10):.1f}" x2="{_x(10):.1f}" y2="{_y(4):.1f}" '
        f'stroke="#6b1f27" stroke-width=".8" stroke-dasharray="1 4" opacity=".6"/>'
        f'<text x="{_x(9.3):.1f}" y="{_y(5.2):.1f}" font-size="9" font-style="italic" '
        f'font-family="Source Serif 4,serif" fill="#6b1f27">read first ↗</text>'
    )


def _bubbles(picks: TopPicks, sections: dict[str, dict[str, Any]]) -> str:
    """Bubbles with section number INSIDE and kicker label ABOVE."""
    parts = []
    for p in picks.plotted:
        cx, cy = _x(p.x), _y(p.y)
        r = p.r / 2  # mockup uses p.r/2 — visual radius is half the data-space r
        meta = sections.get(p.id, {"kicker": p.id, "n": ""})
        kicker_short = str(meta["kicker"]).split(" · ")[0]
        fill = _KIND_FILL.get(p.kind, "#171310")
        num_fill = _KIND_LABEL_FILL.get(p.kind, "#f7f3e9")
        parts.append(
            f'<g class="rm-bubble rm-{_attr_esc(p.kind)}" data-id="{_attr_esc(p.id)}">'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" opacity="0.88"/>'
            f'<text x="{cx:.1f}" y="{cy + 3.5:.1f}" text-anchor="middle" '
            f'font-family="JetBrains Mono,monospace" font-weight="700" font-size="10" '
            f'fill="{num_fill}">§{_esc(meta["n"])}</text>'
            f'<text x="{cx:.1f}" y="{cy - r - 8:.1f}" text-anchor="middle" '
            f'font-family="Source Serif 4,serif" font-weight="600" font-size="12" fill="#171310">'
            f'{_esc(kicker_short)}</text>'
            f'</g>'
        )
    return "".join(parts)


def _legend() -> str:
    return (
        '<div class="rm-legend">'
        '<span class="rm-leg-item"><span class="dot dot-event"></span> EVENT</span>'
        '<span class="rm-leg-item"><span class="dot dot-fresh"></span> FRESH PRINT</span>'
        '<span class="rm-leg-item"><span class="dot dot-slow"></span> SLOW · STRUCTURAL</span>'
        '<span class="rm-leg-item"><span class="dot dot-anchor"></span> ANCHOR</span>'
        '</div>'
    )


def render_risk_map(*, picks: TopPicks, sections: dict[str, dict[str, Any]], today_label: str) -> str:
    # Defensive filter: headlines is a meta-aggregator and must never appear on
    # the risk map — even if Claude's top_picks call placed it there. The prompt
    # also disallows this; this is the belt-and-braces fallback.
    plotted = [p for p in picks.plotted if p.id != "headlines"]
    if len(plotted) < 1:
        raise ValueError("render_risk_map: nothing to plot after filtering headlines")
    picks = picks.model_copy(update={"plotted": plotted})

    return (
        '<section class="risk-map" aria-label="Risk map">'
        '<header class="rm-header">'
        f'<span class="rm-eyebrow">§ RISK MAP · {_esc(today_label)}</span>'
        '<span class="rm-eyebrow-right">AREA ∝ READ-WEIGHT · COLOR = KIND</span>'
        '</header>'
        '<div class="rm-svg-wrap">'
        f'<svg class="rm-svg" viewBox="0 0 {W} {H}" role="img" aria-label="Risk map plotting today\'s seven sections">'
        f'{_quadrant_fills_and_captions()}'
        f'{_grid_lines()}'
        f'{_axes_and_ticks()}'
        f'{_axis_labels()}'
        f'{_read_first_diagonal()}'
        f'{_bubbles(picks, sections)}'
        '</svg>'
        '</div>'
        f'{_legend()}'
        '</section>'
    )
