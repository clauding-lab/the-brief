"""V4 generic section renderer — shared skeleton for non-custom sections.

All non-frontmatter sections (bb, banking, fx, macro, dam, comm, remit,
fiscal, nbr, …) follow the same outer shape:
  1. <section> wrapper with a stable dom_id
  2. section_head (numeral, kicker, title, dek, meta pills)
  3. pull_quote (if section.pull is set)
  4. optional pre_grid_html hook (custom sections inject charts etc.)
  5. metric-grid (zero or more metric cards)
  6. optional post_grid_html hook
  7. bankerread aside (if section.bankerread is set)

Hero metric strategy: if a metric has hero=True we add class "metric-hero"
directly to the metric-card div.  We do NOT use hero_wrap() because that
helper also wraps with the same class and would double-nest the div.

_freshness_pill_html and _freshness_to_dot_state are internal helpers
exposed at module level so binders and tests can import them if needed.
"""
from __future__ import annotations

import html as _html

from brief.render.v4._jsx import (
    bankerread_aside,
    cadence_pill,
    fmt_num,
    pull_quote,
    section_head,
    staleness_dot,
)
from brief.schema import SectionData

# ---------------------------------------------------------------------------
# Section metadata registry
# (numeral, kicker, title)
# ---------------------------------------------------------------------------

_SECTION_META: dict[str, tuple[str, str, str]] = {
    "bb":        ("02", "POLICY & RATES",       "Bangladesh Bank"),
    "banking":   ("03", "BANKING SECTOR",        "Banking Sector"),
    "dse":       ("04", "EQUITIES",              "Dhaka Stock Exchange"),
    "tbond":     ("05", "RATES",                 "T-Bill & T-Bond"),
    "fx":        ("06", "FX & RESERVES",         "BDT/USD FX & Reserves"),
    "macro":     ("07", "MACRO INDICATORS",      "Macroeconomic Indicators"),
    "dam":       ("08", "FOOD PRICES",           "Domestic Food Prices"),
    "comm":      ("09", "GLOBAL COMMODITIES",    "Global Commodities"),
    "remit":     ("10", "REMITTANCES",           "Remittances"),
    "iranwar":   ("14", "GEOPOLITICS",           "US-Iran War Impact"),
    "fiscal":    ("15", "FISCAL & BUDGET",       "Fiscal & Budget"),
    "nbr":       ("16", "TAX REVENUE",           "NBR Tax Revenue"),
    "headlines": ("01", "MAJOR NEWS HEADLINES",  "Headlines"),
}

# ---------------------------------------------------------------------------
# Freshness helpers
# ---------------------------------------------------------------------------

_FRESHNESS_DOT_MAP: dict[str, str] = {
    "warning":     "warn",
    "unavailable": "stale",
}

_FRESHNESS_PILL_TEXT: dict[str, str] = {
    "warning":     "WARNING",
    "stale":       "STALE",
    "pending":     "NEXT RELEASE",
    "unavailable": "UNAVAILABLE",
}

_FRESHNESS_PILL_CLASS: dict[str, str] = {
    "warning":     "warn",
    "stale":       "stale",
    "pending":     "pending",
    "unavailable": "stale",
}


def _freshness_to_dot_state(freshness: str) -> str:
    """Map SectionData.freshness values to staleness_dot-accepted states."""
    return _FRESHNESS_DOT_MAP.get(freshness, freshness)


def _freshness_pill_html(freshness: str, reason: str | None = None) -> str:
    """Return a freshness pill span, or '' for 'fresh'.

    State classes: warn (amber), stale (grey), pending (blue).
    If reason is provided it is set as the title attribute on the pill.
    """
    if freshness == "fresh":
        return ""
    text = _FRESHNESS_PILL_TEXT.get(freshness, freshness.upper())
    cls = _FRESHNESS_PILL_CLASS.get(freshness, "stale")
    title_attr = ""
    if reason:
        escaped_reason = _html.escape(reason, quote=True)
        title_attr = f' title="{escaped_reason}"'
    return f'<span class="fresh-pill fresh-pill-{cls}"{title_attr}>{text}</span>'


# ---------------------------------------------------------------------------
# Delta helpers
# ---------------------------------------------------------------------------

_DELTA_ARROW: dict[str, str] = {
    "up":   "▲",  # ▲
    "down": "▼",  # ▼
    "flat": "–",  # –
}

_WINDOW_LABEL: dict[str, str] = {
    "dod": "d/d",
    "wow": "w/w",
    "mom": "m/m",
    "yoy": "y/y",
}


def _render_delta_line(delta) -> str:
    """Render a delta line: arrow + formatted value + window label."""
    arrow = _DELTA_ARROW.get(delta.direction, "–")
    value_html = fmt_num(delta.value, tabular=False)
    window = _WINDOW_LABEL.get(delta.window, delta.window)
    return (
        f'<div class="m-delta m-delta-{delta.direction}">'
        f"{arrow} {value_html} {window}"
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Metric card
# ---------------------------------------------------------------------------

def _render_metric_card(metric) -> str:
    """Render a single metric card div.

    Hero metrics get the 'metric-hero' class added to the card div directly.
    The metric-hero class spans 2 grid columns (defined in shell_v4.html CSS).
    """
    hero_class = " metric-hero" if metric.hero else ""
    top_row = (
        '<div class="m-top">'
        f'<span class="m-label">{_html.escape(metric.label, quote=False)}</span>'
        f"{cadence_pill(metric.cadence)}"
        "</div>"
    )
    value_row = f'<div class="m-value">{fmt_num(metric.value, metric.unit, tabular=True)}</div>'
    delta_row = _render_delta_line(metric.delta) if metric.delta else ""
    return (
        f'<div class="metric-card{hero_class}">'
        f"{top_row}"
        f"{value_row}"
        f"{delta_row}"
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Generic section renderer
# ---------------------------------------------------------------------------

def render_generic_section(
    section: "SectionData",
    dom_id: str,
    numeral: str,
    kicker: str,
    title: str,
    bankerread_label: str,
    pre_grid_html: str = "",
    post_grid_html: str = "",
) -> str:
    """Shared skeleton used by non-custom sections.

    pre_grid_html: injected between pull quote and metric grid (used by custom
        sections for e.g. yield curve, sector heat, oil chart).
    post_grid_html: injected between metric grid and BankerRead aside.
    """
    # Unavailable short-circuit
    if section.freshness == "unavailable":
        return (
            f'<section class="section section-unavailable" id="{dom_id}">'
            '<div class="fresh-tag">Section Unavailable</div>'
            "</section>"
        )

    # Section head — meta pills: dot + freshness pill
    dot_state = _freshness_to_dot_state(section.freshness)
    dot_html = staleness_dot(dot_state)
    fresh_pill = _freshness_pill_html(section.freshness, section.freshness_reason)
    meta_pills = [dot_html]
    if fresh_pill:
        meta_pills.append(fresh_pill)

    head_html = section_head(
        numeral=numeral,
        kicker=kicker,
        title_parts=[(title, "plain")],
        dek=section.freshness_reason or "",
        meta=meta_pills,
    )

    # Pull quote
    pull_html = ""
    if section.pull:
        pull_html = pull_quote(section.pull, f"BankerRead · {bankerread_label}")

    # Metric grid
    cards_html = "".join(_render_metric_card(m) for m in section.metrics)
    grid_html = f'<div class="metric-grid">{cards_html}</div>'

    # BankerRead aside
    br_html = ""
    if section.bankerread:
        br_html = bankerread_aside(
            section.bankerread,
            anchor=numeral,
            anchor_label=bankerread_label,
        )

    return (
        f'<section class="section" id="{dom_id}">'
        f"{head_html}"
        f"{pull_html}"
        f"{pre_grid_html}"
        f"{grid_html}"
        f"{post_grid_html}"
        f"{br_html}"
        f"</section>"
    )
