"""V4 JSX helper library — pure functions returning HTML fragment strings.

All helpers are side-effect-free: they take plain Python values and return
HTML strings. No framework dependency. CSS classes are defined in shell_v4.html.
"""
from __future__ import annotations

import html
from typing import Literal

from brief.schema import BankerReadInsight

# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    """HTML-escape text content (not attributes)."""
    return html.escape(s, quote=False)


def _attr_esc(s: str) -> str:
    """HTML-escape an attribute value."""
    return html.escape(s, quote=True)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def attr(name: str, value: str | None) -> str:
    """Escape an HTML attribute.

    Returns ` name="escaped-value"` (with leading space).
    Returns "" when value is None or empty.
    """
    if value is None or value == "":
        return ""
    return f' {name}="{_attr_esc(str(value))}"'


def fmt_num(
    value: float | int | None,
    unit: str | None = None,
    tabular: bool = True,
) -> str:
    """Format a number with tabular-nums and optional unit suffix.

    - None  → em-dash "—"
    - int   → no decimal places
    - float → 2 decimal places; thousands separator when abs >= 1000
    - tabular=True → wraps numeric part in <span class="num">
    - unit  → appended as <span class="unit">unit</span>
    """
    if value is None:
        return "—"

    if isinstance(value, int):
        formatted = f"{value:,}"
    else:
        f = float(value)
        if abs(f) >= 1000:
            formatted = f"{f:,.2f}"
        else:
            formatted = f"{f:.2f}"

    if tabular:
        inner = f'<span class="num">{formatted}</span>'
    else:
        inner = formatted

    if unit:
        inner += f' <span class="unit">{_esc(unit)}</span>'

    return inner


_VALID_STALENESS_STATES: frozenset[str] = frozenset(
    {"fresh", "warn", "stale", "pending", "warming_up"}
)


def staleness_dot(
    state: Literal["fresh", "warn", "stale", "pending", "warming_up"],
) -> str:
    """Small colored staleness dot.

    Returns <span class="dot dot-{state}"></span>.
    CSS maps the state class to color: fresh=green, warn=amber, stale=grey,
    pending=blue, warming_up=amber (intentional placeholder — no legacy backfill).
    Raises ValueError for unknown state.
    """
    if state not in _VALID_STALENESS_STATES:
        raise ValueError(
            f"staleness_dot: unknown state {state!r}. "
            f"Valid states: {sorted(_VALID_STALENESS_STATES)}"
        )
    # Normalize underscore to hyphen for CSS class convention (dot-warming-up, not dot-warming_up)
    css_state = state.replace("_", "-")
    return f'<span class="dot dot-{css_state}"></span>'


_VALID_CADENCES: frozenset[str] = frozenset(
    {"daily", "weekly", "monthly", "quarterly", "event", "pending"}
)


def cadence_pill(cadence: str) -> str:
    """Pill badge indicating metric cadence.

    Returns <span class="cadence-pill cadence-{cadence}">CADENCE_UPPER</span>.
    """
    label = cadence.upper()
    return f'<span class="cadence-pill cadence-{cadence}">{label}</span>'


def sparkline_svg(
    points: list[float],
    color: str = "#171310",
    w: int = 140,
    h: int = 32,
) -> str:
    """Render a 12-point SVG polyline sparkline.

    - Normalizes points to fit [0, w] x [0, h] (y inverted: max at top).
    - All-equal points: horizontal line at mid-height.
    - Empty or fewer than 2 points: returns "".
    - stroke-width 1.5, fill none.
    """
    if not points or len(points) < 2:
        return ""

    min_v = min(points)
    max_v = max(points)
    value_range = max_v - min_v

    n = len(pairs := list(enumerate(points)))
    _ = n  # suppress unused warning

    coords: list[str] = []
    for i, v in pairs:
        x = round(i / (len(points) - 1) * w, 2)
        if value_range == 0:
            y = h / 2
        else:
            # Invert: max value maps to y=0 (top), min to y=h (bottom)
            y = round(h - (v - min_v) / value_range * h, 2)
        coords.append(f"{x},{y}")

    pts_str = " ".join(coords)
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'xmlns="http://www.w3.org/2000/svg" class="sparkline">'
        f'<polyline points="{pts_str}" '
        f'stroke="{_attr_esc(color)}" stroke-width="1.5" fill="none"/>'
        f"</svg>"
    )


def hero_wrap(metric_html: str) -> str:
    """Wrap metric content in hero chrome.

    paper-2 background, 3px oxblood left border, spans 2 grid columns.
    """
    return f'<div class="metric-card metric-hero">{metric_html}</div>'


def pull_quote(text: str, cite: str) -> str:
    """Section-top pull quote.

    Large italic serif text with oxblood left border and large opening-quote glyph.
    Both text and cite are HTML-escaped.
    """
    escaped_text = _esc(text)
    escaped_cite = _esc(cite)
    return (
        '<blockquote class="pull-quote">'
        '<span class="glyph">&ldquo;</span>'
        f"<p>{escaped_text}</p>"
        f"<cite>{escaped_cite}</cite>"
        "</blockquote>"
    )


def bankerread_aside(
    br: BankerReadInsight,
    anchor: str,
    anchor_label: str,
) -> str:
    """Render a BankerRead insight aside.

    Structured variant: §A (meaning) + §B (action) + §C (trigger) + §D (focus),
    mono gold labels, 52px oxblood drop cap on first letter of §A content.

    Freeform variant: single text block with freeform chrome.

    Both end with a "Jump to §{anchor}" anchor link.
    Wrapping: <aside class="bankerread br-{kind}" id="br-{anchor}">
    """
    jump_link = (
        f'<a class="bankerread-jump" href="#{_attr_esc(anchor)}">'
        f"Jump to §{_esc(anchor_label)}"
        f"</a>"
    )

    if br.kind == "structured":
        # §A gets a drop cap on its first letter
        meaning_text = html.escape(br.meaning, quote=False)
        if meaning_text:
            first = meaning_text[0]
            rest = meaning_text[1:]
            meaning_body = f'<span class="drop-cap">{first}</span>{rest}'
        else:
            meaning_body = meaning_text

        sections_html = (
            '<div class="br-section">'
            '<span class="br-label mono-gold">§A</span>'
            f'<p class="br-content">{meaning_body}</p>'
            "</div>"
            '<div class="br-section">'
            '<span class="br-label mono-gold">§B</span>'
            f'<p class="br-content">{html.escape(br.action, quote=False)}</p>'
            "</div>"
            '<div class="br-section">'
            '<span class="br-label mono-gold">§C</span>'
            f'<p class="br-content">{html.escape(br.trigger, quote=False)}</p>'
            "</div>"
            '<div class="br-section">'
            '<span class="br-label mono-gold">§D</span>'
            f'<p class="br-content">{html.escape(br.focus, quote=False)}</p>'
            "</div>"
        )
        inner = sections_html + jump_link

    else:  # freeform
        text_body = html.escape(br.text, quote=False)
        inner = (
            '<div class="br-freeform-body">'
            f"<p>{text_body}</p>"
            "</div>"
            + jump_link
        )

    return (
        f'<aside class="bankerread br-{br.kind}"'
        f' id="br-{_attr_esc(anchor)}">'
        '<span class="bankerread-label">BankerRead</span>'
        f"{inner}"
        "</aside>"
    )


def section_head(
    numeral: str,
    kicker: str,
    title_parts: list[tuple[str, str]],
    dek: str,
    meta: list[str],
) -> str:
    """Render a section header.

    numeral    — e.g. "02", rendered as big oxblood serif.
    kicker     — e.g. "POLICY & RATES", mono uppercase.
    title_parts — list of (text, style) where style in {"plain", "italic-ox"}.
    dek        — sub-title paragraph, italic serif.
    meta       — list of pre-rendered HTML fragments (e.g. staleness_dot(),
                 _freshness_pill_html()) passed through verbatim as pill content.
                 Items must already be safe HTML — they are NOT escaped here.

    Returns <header class="section-head">...</header>.
    """
    # Numeral
    numeral_html = (
        f'<span class="section-numeral">{_esc(numeral)}</span>'
    )

    # Kicker
    kicker_html = (
        f'<span class="section-kicker">{_esc(kicker)}</span>'
    )

    # Title — assemble styled parts
    title_inner = ""
    for text, style in title_parts:
        if style == "italic-ox":
            title_inner += f'<em class="italic-ox">{_esc(text)}</em>'
        else:
            title_inner += _esc(text)
    title_html = f'<h2 class="section-title">{title_inner}</h2>'

    # Dek
    dek_html = f'<p class="section-dek">{_esc(dek)}</p>'

    # Meta pills — items are pre-rendered HTML fragments; do not escape them.
    meta_html = ""
    if meta:
        pills = "".join(
            f'<span class="meta-pill">{m}</span>' for m in meta
        )
        meta_html = f'<div class="section-meta">{pills}</div>'

    return (
        "<header class=\"section-head\">"
        + numeral_html
        + kicker_html
        + title_html
        + dek_html
        + meta_html
        + "</header>"
    )
