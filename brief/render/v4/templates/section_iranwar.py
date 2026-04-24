"""V4 US-Iran War Impact section renderer (§14 GEOPOLITICS).

Extends the generic skeleton with an Oil Chart SVG injected as post_grid_html.

SVG layout (480 x 220):
  - 12-session Brent crude price line from ``section.extras["brent_12_sessions"]``
    (list of 12 floats).  Line: stroke="var(--ink-2)", stroke-width 1.8.
  - Event pins from ``section.extras["oil_events"]`` (list of dicts or OilEvent
    objects).  Each pin:
      date   — ISO date string "YYYY-MM-DD" or datetime.date object.
      label  — short text description.
      hotness — "hot" | "cold" (or .hot bool attribute on OilEvent dataclass).
      y_offset — optional int pixel offset for the label (default 0).
    Hot events: vertical line stroke="var(--ox)", label class "pin-hot".
    Cold events: vertical line stroke="var(--ink-3)", label class "pin-cold".
  - Events are positioned by matching their date to the 12-session window.
    Sessions are spaced evenly across the chart width.  Events outside the
    window are pinned at the left/right edge with a ``<`` or ``>`` prefix.
  - If ``brent_12_sessions`` is absent or empty, post_grid_html is "".

Session window dates: this module does NOT know the actual trading calendar; it
assigns sessions sequentially (session 0 at left, session 11 at right).
Events are matched by date string to the ``session_dates`` list if it is
present in ``section.extras["session_dates"]``; otherwise the 12 sessions are
assumed to run on consecutive calendar days ending at the briefing date.

Oil event dict shape (builder-serialised):
    {"date": "2026-04-21", "label": "Hormuz tanker", "hotness": "hot"}

OilEvent dataclass shape (builder object):
    OilEvent(date=date(2026,4,21), label="Hormuz tanker", hot=True)
"""
from __future__ import annotations

from datetime import date as _date, timedelta

from brief.render.v4.templates._generic import _SECTION_META, render_generic_section
from brief.schema import SectionData

_SVG_W = 480
_SVG_H = 220
_PAD_LEFT = 40
_PAD_RIGHT = 20
_PAD_TOP = 28
_PAD_BOTTOM = 32


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------

def _event_date(ev: object) -> str:
    """Return ISO date string from a dict or OilEvent-like object."""
    if isinstance(ev, dict):
        d = ev.get("date", "")
        return str(d)[:10] if d else ""
    d = getattr(ev, "date", None)
    if d is None:
        return ""
    if isinstance(d, str):
        return d[:10]
    return d.isoformat()[:10]


def _event_label(ev: object) -> str:
    if isinstance(ev, dict):
        return str(ev.get("label", ""))
    return str(getattr(ev, "label", ""))


def _event_is_hot(ev: object) -> bool:
    """Return True for hot events."""
    if isinstance(ev, dict):
        hotness = ev.get("hotness", "")
        return str(hotness).lower() == "hot"
    # OilEvent dataclass uses .hot bool
    hot_attr = getattr(ev, "hot", None)
    if hot_attr is not None:
        return bool(hot_attr)
    hotness = getattr(ev, "hotness", "")
    return str(hotness).lower() == "hot"


def _event_y_offset(ev: object) -> int:
    if isinstance(ev, dict):
        return int(ev.get("y_offset", 0))
    return int(getattr(ev, "y_offset", 0))


# ---------------------------------------------------------------------------
# SVG builder
# ---------------------------------------------------------------------------

def _build_oil_chart_svg(
    sessions: list[float],
    events: list,
    briefing_date: str | None = None,
) -> str:
    """Build oil chart SVG. Returns '' if sessions is empty."""
    if not sessions:
        return ""

    n = len(sessions)
    chart_w = _SVG_W - _PAD_LEFT - _PAD_RIGHT
    chart_h = _SVG_H - _PAD_TOP - _PAD_BOTTOM

    y_min = min(sessions)
    y_max = max(sessions)
    y_rng = y_max - y_min if y_max > y_min else 1.0

    def x_for(idx: int) -> float:
        return round(_PAD_LEFT + (idx / max(n - 1, 1)) * chart_w, 2)

    def y_for(val: float) -> float:
        frac = (val - y_min) / y_rng
        return round(_PAD_TOP + chart_h * (1.0 - frac), 2)

    # Main price line
    pts = " ".join(f"{x_for(i)},{y_for(v)}" for i, v in enumerate(sessions))
    line_svg = (
        f'<polyline points="{pts}" '
        f'stroke="var(--ink-2)" stroke-width="1.8" fill="none" '
        f'stroke-linejoin="round"/>'
    )

    # Session dates: infer from briefing_date (last session = today)
    session_dates: list[str] = []
    if briefing_date:
        try:
            end = _date.fromisoformat(briefing_date)
            session_dates = [(end - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]
        except ValueError:
            pass

    # Event pins
    pins_svg = ""
    for ev in events:
        ev_date = _event_date(ev)
        label = _event_label(ev)
        is_hot = _event_is_hot(ev)
        y_offset = _event_y_offset(ev)

        # Find session index for this event date
        pin_idx: int | None = None
        prefix = ""
        if ev_date and session_dates:
            if ev_date in session_dates:
                pin_idx = session_dates.index(ev_date)
            elif ev_date < session_dates[0]:
                pin_idx = 0
                prefix = "< "
            else:
                pin_idx = n - 1
                prefix = "> "
        elif ev_date and not session_dates:
            # No date info — skip pin positioning, skip this pin
            continue
        else:
            continue

        px = x_for(pin_idx)
        stroke = "var(--ox)" if is_hot else "var(--ink-3)"
        lbl_class = "pin-hot" if is_hot else "pin-cold"
        label_y = _PAD_TOP - 8 + y_offset
        import html as _html_mod
        esc_label = _html_mod.escape(prefix + label, quote=False)

        pins_svg += (
            f'<line x1="{px}" y1="{_PAD_TOP}" x2="{px}" y2="{_PAD_TOP + chart_h}" '
            f'stroke="{stroke}" stroke-width="1.2" stroke-dasharray="3 2"/>'
            f'<text x="{px}" y="{label_y}" text-anchor="middle" '
            f'class="oil-pin-label {lbl_class}">{esc_label}</text>'
        )

    return (
        f'<svg class="oil-chart-svg" width="{_SVG_W}" height="{_SVG_H}" '
        f'viewBox="0 0 {_SVG_W} {_SVG_H}" xmlns="http://www.w3.org/2000/svg">'
        f"{line_svg}"
        f"{pins_svg}"
        f"</svg>"
    )


# ---------------------------------------------------------------------------
# Public renderer
# ---------------------------------------------------------------------------

def render_section_iranwar(section: "SectionData") -> str:
    """IranWar (§14): generic skeleton + oil chart with event pins."""
    post_grid_html = ""

    if section.freshness != "unavailable":
        sessions = section.extras.get("brent_12_sessions") or []
        events = section.extras.get("oil_events") or []
        # Briefing date: use latest metric as_of date if available
        briefing_date: str | None = None
        if section.metrics:
            briefing_date = section.metrics[0].as_of.isoformat()
        svg = _build_oil_chart_svg(sessions, events, briefing_date)
        if svg:
            post_grid_html = f'<div class="iranwar-oil-chart">{svg}</div>'

    meta = _SECTION_META["iranwar"]
    return render_generic_section(
        section,
        dom_id="section-iranwar",
        numeral=meta[0],
        kicker=meta[1],
        title=meta[2],
        bankerread_label=f"§{meta[0]} {meta[2]}",
        post_grid_html=post_grid_html,
    )
