"""V4 Risk Map template — SVG scatter with 4 quadrants, dots, and detail pane."""
from __future__ import annotations

import html

from brief.schema import MapCoord, SectionData
from brief.render.v4._jsx import attr, fmt_num

# ---------------------------------------------------------------------------
# Plot area constants
# ---------------------------------------------------------------------------

_VB_W = 640
_VB_H = 480

# Margins for axis labels
_PLOT_LEFT = 80
_PLOT_RIGHT = 600
_PLOT_TOP = 40
_PLOT_BOTTOM = 440

_PLOT_W = _PLOT_RIGHT - _PLOT_LEFT   # 520
_PLOT_H = _PLOT_BOTTOM - _PLOT_TOP   # 400

_MID_X = (_PLOT_LEFT + _PLOT_RIGHT) // 2   # 340
_MID_Y = (_PLOT_TOP + _PLOT_BOTTOM) // 2   # 240

# Colour constants referenced by type
_DOT_FILL = {
    "event": "var(--ox)",
    "fresh": "var(--up)",
    "slow": "var(--warn)",
    "anchor": "var(--ink-2)",
}

_DOT_CLASS = {
    "event": "rm-dot-event",
    "fresh": "rm-dot-fresh",
    "slow": "rm-dot-slow",
    "anchor": "rm-dot-anchor",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def _attr_esc(s: str) -> str:
    return html.escape(s, quote=True)


def _coord_to_svg(mc: MapCoord) -> tuple[float, float]:
    """Map (mc.x, mc.y) [0-10] to SVG (cx, cy) within the plot area."""
    cx = _PLOT_LEFT + mc.x * (_PLOT_W / 10.0)
    cy = _PLOT_BOTTOM - mc.y * (_PLOT_H / 10.0)  # y is inverted
    return round(cx, 1), round(cy, 1)


# ---------------------------------------------------------------------------
# SVG sub-renderers
# ---------------------------------------------------------------------------

def _render_quadrant_fills() -> str:
    """4 <rect> covering the 4 quadrants of the plot area."""
    # top-left: high Y, low X  → anchor
    # top-right: high Y, high X → event
    # bottom-left: low Y, low X → slow
    # bottom-right: low Y, high X → fresh
    quads = [
        # (x, y, w, h, css_class, fill)
        (_PLOT_LEFT, _PLOT_TOP, _MID_X - _PLOT_LEFT, _MID_Y - _PLOT_TOP,
         "q-anchor", "var(--ox-wash, rgba(107,31,39,0.06))"),
        (_MID_X, _PLOT_TOP, _PLOT_RIGHT - _MID_X, _MID_Y - _PLOT_TOP,
         "q-event", "var(--warn-bg, rgba(107,31,39,0.08))"),
        (_PLOT_LEFT, _MID_Y, _MID_X - _PLOT_LEFT, _PLOT_BOTTOM - _MID_Y,
         "q-slow", "var(--paper-2, rgba(164,152,130,0.07))"),
        (_MID_X, _MID_Y, _PLOT_RIGHT - _MID_X, _PLOT_BOTTOM - _MID_Y,
         "q-fresh", "var(--paper-3, rgba(164,152,130,0.04))"),
    ]
    parts: list[str] = []
    for x, y, w, h, cls, fill in quads:
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}"'
            f' class="{cls}" fill="{fill}" fill-opacity="0.5"/>'
        )
    return "".join(parts)


def _render_grid_lines() -> str:
    """9 vertical + 9 horizontal dotted grid lines."""
    parts: list[str] = []
    stroke_attrs = 'stroke="var(--ink-4)" stroke-width="0.4" stroke-dasharray="1 2"'
    # 9 vertical lines (x = 1..9 in data space)
    for i in range(1, 10):
        vx = round(_PLOT_LEFT + i * (_PLOT_W / 10.0), 1)
        parts.append(
            f'<line x1="{vx}" y1="{_PLOT_TOP}" x2="{vx}" y2="{_PLOT_BOTTOM}" {stroke_attrs}/>'
        )
    # 9 horizontal lines (y = 1..9 in data space)
    for i in range(1, 10):
        vy = round(_PLOT_BOTTOM - i * (_PLOT_H / 10.0), 1)
        parts.append(
            f'<line x1="{_PLOT_LEFT}" y1="{vy}" x2="{_PLOT_RIGHT}" y2="{vy}" {stroke_attrs}/>'
        )
    return "".join(parts)


def _render_axes() -> str:
    """X and Y axes."""
    axis_attrs = 'stroke="var(--ink-2)" stroke-width="1"'
    x_axis = f'<line x1="{_PLOT_LEFT}" y1="{_PLOT_BOTTOM}" x2="{_PLOT_RIGHT}" y2="{_PLOT_BOTTOM}" {axis_attrs}/>'
    y_axis = f'<line x1="{_PLOT_LEFT}" y1="{_PLOT_TOP}" x2="{_PLOT_LEFT}" y2="{_PLOT_BOTTOM}" {axis_attrs}/>'
    return x_axis + y_axis


def _render_axis_labels() -> str:
    """Axis title and tick labels."""
    parts: list[str] = []
    text_attrs = 'class="risk-map-axis-label" font-family="var(--font-mono)" font-size="11"'

    # X axis label — bottom center
    mid_x = (_PLOT_LEFT + _PLOT_RIGHT) / 2
    parts.append(
        f'<text x="{mid_x}" y="{_VB_H - 8}" {text_attrs}'
        f' text-anchor="middle" fill="var(--ink-4)">Movement today →</text>'
    )

    # Y axis label — rotated, left center
    mid_y = (_PLOT_TOP + _PLOT_BOTTOM) / 2
    parts.append(
        f'<text x="14" y="{mid_y}" {text_attrs}'
        f' text-anchor="middle" transform="rotate(-90, 14, {mid_y})"'
        f' fill="var(--ink-4)">Significance for the book ↑</text>'
    )

    # Tick labels 0, 5, 10 on X axis
    for val, label in [(0, "0"), (5, "5"), (10, "10")]:
        tx = round(_PLOT_LEFT + val * (_PLOT_W / 10.0), 1)
        parts.append(
            f'<text x="{tx}" y="{_PLOT_BOTTOM + 14}" {text_attrs}'
            f' text-anchor="middle" fill="var(--ink-4)">{label}</text>'
        )

    # Tick labels 0, 5, 10 on Y axis
    for val, label in [(0, "0"), (5, "5"), (10, "10")]:
        ty = round(_PLOT_BOTTOM - val * (_PLOT_H / 10.0), 1)
        parts.append(
            f'<text x="{_PLOT_LEFT - 8}" y="{ty + 4}" {text_attrs}'
            f' text-anchor="end" fill="var(--ink-4)">{label}</text>'
        )

    return "".join(parts)


def _render_diagonal_hint() -> str:
    """Subtle read-order diagonal hint from bottom-left to top-right."""
    line = (
        f'<line x1="{_PLOT_LEFT}" y1="{_PLOT_BOTTOM}"'
        f' x2="{_PLOT_RIGHT}" y2="{_PLOT_TOP}"'
        f' stroke="var(--ox)" stroke-opacity="0.15"'
        f' stroke-width="1" stroke-dasharray="2 4"/>'
    )
    # Label near mid-diagonal
    lx = (_PLOT_LEFT + _PLOT_RIGHT) / 2 + 10
    ly = (_PLOT_TOP + _PLOT_BOTTOM) / 2 - 8
    label = (
        f'<text x="{lx}" y="{ly}"'
        f' font-family="var(--font-mono)" font-size="9"'
        f' fill="var(--ox)" opacity="0.3"'
        f' transform="rotate(-37, {lx}, {ly})">read order →</text>'
    )
    return line + label


def _render_dots(coords: list[MapCoord], sections: dict[str, SectionData]) -> str:
    """Render one circle + label per coord."""
    parts: list[str] = []
    for mc in coords:
        cx, cy = _coord_to_svg(mc)
        r = mc.r / 2  # halve for viewBox
        dot_type = mc.type
        fill = _DOT_FILL.get(dot_type, "var(--ink-3)")
        css_class = f"map-dot {_DOT_CLASS.get(dot_type, 'map-dot-unknown')}"

        # Circle
        parts.append(
            f'<circle'
            f' cx="{cx}" cy="{cy}" r="{r}"'
            f' fill="{fill}"'
            f' class="{_attr_esc(css_class)}"'
            f' data-section="{_attr_esc(mc.section_id)}"'
            f'/>'
        )

        # Section ID label above dot
        label_y = round(cy - r / 2 - 4, 1)
        sid_upper = _esc(mc.section_id.upper())
        parts.append(
            f'<text x="{cx}" y="{label_y}"'
            f' class="map-label"'
            f' font-family="var(--font-mono)" font-size="9"'
            f' fill="var(--ink-2)" text-anchor="middle"'
            f' font-weight="600">{sid_upper}</text>'
        )

        # Optional kicker below dot — first 20 chars of section title
        section = sections.get(mc.section_id)
        if section and section.title:
            kicker_raw = section.title[:20]
            kicker_text = _esc(kicker_raw)
            kicker_y = round(cy + r / 2 + 11, 1)
            parts.append(
                f'<text x="{cx}" y="{kicker_y}"'
                f' font-family="var(--font-mono)" font-size="9"'
                f' fill="var(--ink-3)" text-anchor="middle"'
                f' opacity="0.7">{kicker_text}</text>'
            )

    return "".join(parts)


def _render_detail_pane(
    read_order: list[str] | None,
    sections: dict[str, SectionData],
) -> str:
    """Detail pane: lead section or fallback message."""
    if not read_order:
        return '<p class="map-fallback">Click a dot for details.</p>'

    lead_id = read_order[0]
    section = sections.get(lead_id)
    if section is None:
        return '<p class="map-fallback">Click a dot for details.</p>'

    kicker = _esc(lead_id.upper())
    title = _esc(section.title)

    metrics_html = ""
    top_metrics = section.metrics[:3]
    for m in top_metrics:
        label = _esc(m.label)
        val_html = fmt_num(m.value, m.unit)
        metrics_html += (
            f'<div class="map-detail-metric">'
            f'<span class="map-detail-metric-label">{label}</span>'
            f'<span class="map-detail-metric-value">{val_html}</span>'
            f'</div>'
        )

    return (
        f'<p class="map-detail-kicker">{kicker}</p>'
        f'<p class="map-detail-title">{title}</p>'
        f'<div class="map-detail-metrics">{metrics_html}</div>'
    )


# ---------------------------------------------------------------------------
# Public render function
# ---------------------------------------------------------------------------

def render_risk_map(
    coords: list[MapCoord],
    sections: dict[str, SectionData],
    read_order: list[str] | None = None,
) -> str:
    """SVG scatter: 4 quadrants + grid + axes + dots + detail pane."""
    n = len(coords)
    aria_label = _attr_esc(
        f"Risk Map: {n} sections plotted by today's movement and significance"
    )

    svg_inner = (
        _render_quadrant_fills()
        + _render_grid_lines()
        + _render_axes()
        + _render_axis_labels()
        + _render_diagonal_hint()
        + _render_dots(coords, sections)
    )

    svg = (
        f'<svg class="risk-map-svg map-svg"'
        f' viewBox="0 0 {_VB_W} {_VB_H}"'
        f' role="img"'
        f' aria-label="{aria_label}">'
        + svg_inner
        + "</svg>"
    )

    quadrant_captions = (
        '<div class="quadrant-captions">'
        '<span class="qc qc-anchor">ANCHOR</span>'
        '<span class="qc qc-event">EVENT</span>'
        '<span class="qc qc-slow">SLOW</span>'
        '<span class="qc qc-fresh">FRESH</span>'
        "</div>"
    )

    map_left = (
        '<div class="map-left">'
        + svg
        + quadrant_captions
        + "</div>"
    )

    detail_html = _render_detail_pane(read_order, sections)
    detail_aside = f'<aside class="map-detail">{detail_html}</aside>'

    return (
        '<section class="risk-map risk-map-wrap" aria-label="Risk Map">'
        + map_left
        + detail_aside
        + "</section>"
    )
