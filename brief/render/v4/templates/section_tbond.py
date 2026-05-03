"""V4 T-Bill & T-Bond section renderer (§05 RATES).

Extends the generic skeleton with a Yield Curve SVG injected as post_grid_html.

SVG layout (480 x 240):
  - X axis: 6 tenor labels (3M, 6M, 1Y, 2Y, 5Y, 10Y) evenly spaced.
  - Y axis: auto-scaled to min/max of all yields (current + prev) with 0.5%
    padding each side.  Low / high values labelled via <text> elements.
  - Current week: solid oxblood polyline (stroke="var(--ox)", stroke-width 2.5)
    + 6 circle markers (r=4).
  - Previous week (if section.extras["prev_week_yields"] is present): dashed
    ink-4 polyline (stroke="var(--ink-4)", stroke-dasharray="4 3",
    stroke-width 1.5) + smaller circle markers (r=3).
  - Legend placed top-right: "This week" / "Last week" with matching styles.
  - Missing tenor data: that point is skipped (polyline gaps); if ALL 6 current
    tenors are missing, post_grid_html is returned as "".

Metric ID pattern: ``tbond_{tenor_lower}_yield``
  e.g. ``tbond_3m_yield``, ``tbond_6m_yield``, ``tbond_1y_yield``, etc.
"""
from __future__ import annotations

from brief.render.v4.templates._generic import _SECTION_META, render_generic_section
from brief.schema import SectionData

_TENORS = ["3M", "6M", "1Y", "2Y", "5Y", "10Y"]

_SVG_W = 480
_SVG_H = 240
_PAD_LEFT = 48
_PAD_RIGHT = 24
_PAD_TOP = 32
_PAD_BOTTOM = 36


def _tenor_metric_id(tenor: str) -> str:
    return f"tbond_{tenor.lower()}_yield"


def _extract_current_yields(section: "SectionData") -> dict[str, float | None]:
    """Return {tenor: yield_float | None} for the 6 canonical tenors."""
    by_id = {m.id: m for m in section.metrics}
    result: dict[str, float | None] = {}
    for t in _TENORS:
        mid = _tenor_metric_id(t)
        m = by_id.get(mid)
        if m is not None and m.value is not None:
            try:
                result[t] = float(m.value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                result[t] = None
        else:
            result[t] = None
    return result


def _scale(val: float, y_min: float, y_max: float) -> float:
    """Map a yield value to SVG y-coordinate (top = high yield)."""
    rng = y_max - y_min
    if rng == 0:
        return _PAD_TOP + (_SVG_H - _PAD_TOP - _PAD_BOTTOM) / 2
    frac = (val - y_min) / rng  # 0=low, 1=high
    chart_h = _SVG_H - _PAD_TOP - _PAD_BOTTOM
    return _PAD_TOP + chart_h * (1.0 - frac)  # invert: high -> top


def _x_for(idx: int) -> float:
    """X coordinate for the idx-th tenor (0-based)."""
    chart_w = _SVG_W - _PAD_LEFT - _PAD_RIGHT
    step = chart_w / (len(_TENORS) - 1) if len(_TENORS) > 1 else 0
    return _PAD_LEFT + idx * step


def _build_yield_curve_svg(
    current: dict[str, float | None],
    prev: dict[str, float] | None,
) -> str:
    """Build the SVG string. Returns '' if no current data at all."""
    current_vals = [(t, v) for t, v in current.items() if v is not None]
    if not current_vals:
        return ""

    # Collect all values for scale
    all_vals: list[float] = [v for _, v in current_vals]
    if prev:
        all_vals.extend(prev.values())

    y_min = min(all_vals) - 0.5
    y_max = max(all_vals) + 0.5

    # Build current polyline points
    cur_pts: list[str] = []
    cur_circles: list[str] = []
    for i, t in enumerate(_TENORS):
        v = current.get(t)
        if v is None:
            continue
        x = round(_x_for(i), 2)
        y = round(_scale(v, y_min, y_max), 2)
        cur_pts.append(f"{x},{y}")
        cur_circles.append(
            f'<circle cx="{x}" cy="{y}" r="4" fill="var(--ox)" stroke="none"/>'
        )

    cur_polyline = (
        f'<polyline points="{" ".join(cur_pts)}" '
        f'stroke="var(--ox)" stroke-width="2.5" fill="none" stroke-linejoin="round"/>'
        if len(cur_pts) >= 2 else ""
    )

    # Build prev polyline
    prev_polyline = ""
    prev_circles: list[str] = []
    if prev:
        prev_pts: list[str] = []
        for i, t in enumerate(_TENORS):
            v = prev.get(t)
            if v is None:
                continue
            x = round(_x_for(i), 2)
            y = round(_scale(v, y_min, y_max), 2)
            prev_pts.append(f"{x},{y}")
            prev_circles.append(
                f'<circle cx="{x}" cy="{y}" r="3" fill="var(--ink-4)" stroke="none"/>'
            )
        if len(prev_pts) >= 2:
            prev_polyline = (
                f'<polyline points="{" ".join(prev_pts)}" '
                f'stroke="var(--ink-4)" stroke-width="1.5" fill="none" '
                f'stroke-dasharray="4 3" stroke-linejoin="round"/>'
            )

    # X-axis labels
    x_labels = ""
    for i, t in enumerate(_TENORS):
        x = round(_x_for(i), 2)
        x_labels += (
            f'<text x="{x}" y="{_SVG_H - 6}" '
            f'text-anchor="middle" class="yc-label yc-xlabel">{t}</text>'
        )

    # Y-axis labels (low/high)
    y_low_y = round(_scale(y_min + 0.5, y_min, y_max), 2)  # original min
    y_high_y = round(_scale(y_max - 0.5, y_min, y_max), 2)  # original max
    y_labels = (
        f'<text x="{_PAD_LEFT - 6}" y="{y_low_y + 4}" '
        f'text-anchor="end" class="yc-label yc-ylabel">{y_min + 0.5:.1f}%</text>'
        f'<text x="{_PAD_LEFT - 6}" y="{y_high_y + 4}" '
        f'text-anchor="end" class="yc-label yc-ylabel">{y_max - 0.5:.1f}%</text>'
    )

    # Legend (top-right)
    legend_x = _SVG_W - _PAD_RIGHT - 10
    legend_y_cur = _PAD_TOP - 14
    legend_y_prev = legend_y_cur - 18
    legend = (
        f'<text x="{legend_x}" y="{legend_y_cur}" '
        f'text-anchor="end" class="yc-legend yc-cur">This week</text>'
    )
    if prev:
        legend += (
            f'<text x="{legend_x}" y="{legend_y_prev}" '
            f'text-anchor="end" class="yc-legend yc-prev">Last week</text>'
        )

    inner = (
        y_labels
        + x_labels
        + prev_polyline
        + "".join(prev_circles)
        + cur_polyline
        + "".join(cur_circles)
        + legend
    )

    return (
        f'<svg class="yield-curve-svg" width="{_SVG_W}" height="{_SVG_H}" '
        f'viewBox="0 0 {_SVG_W} {_SVG_H}" xmlns="http://www.w3.org/2000/svg">'
        f"{inner}"
        f"</svg>"
    )


def render_section_tbond(section: "SectionData") -> str:
    """TBond (§05): generic skeleton + yield curve SVG."""
    post_grid_html = ""

    if section.freshness != "unavailable":
        current = _extract_current_yields(section)
        prev: dict[str, float] | None = section.extras.get("prev_week_yields")
        svg = _build_yield_curve_svg(current, prev)
        if svg:
            post_grid_html = f'<div class="tbond-yield-curve">{svg}</div>'

    meta = _SECTION_META["tbond"]
    return render_generic_section(
        section,
        dom_id="section-tbond",
        numeral=meta[0],
        kicker=meta[1],
        title=meta[2],
        bankerread_label=f"§{meta[0]} {meta[2]}",
        post_grid_html=post_grid_html,
    )
