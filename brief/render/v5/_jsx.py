"""V5 JSX helpers — pure functions returning HTML fragment strings.

Reuses V4 helpers (`brief.render.v4._jsx.fmt_num`, `attr`, `_esc`, `_attr_esc`,
`sparkline_svg`) where applicable. New V5 helpers below.
"""
from __future__ import annotations

from datetime import date

from brief.cadence import metric_aging, now_bdt
from brief.render.v4._jsx import _esc, _attr_esc, attr, fmt_num, sparkline_svg
from brief.schema import (
    BankerReadInsight,
    Metric,
    NewsItem,
    SystemicRisk,
)
from brief.sources import SOURCE_BADGES, resolve_source_code

__all__ = [
    "_esc",
    "_attr_esc",
    "attr",
    "fmt_num",
    "sparkline_svg",
    "kind_dot",
    "freshness_pill",
    "cadence_pill_v5",
    "pull_quote_card",
    "metric_hero_card",
    "news_bullet",
    "source_badge",
    "line_chart_svg",
    "heatmap_svg",
    "bankerread_panel_v5",
    "systemic_risk_callout",
]

_VALID_KINDS = frozenset({"event", "fresh", "slow", "anchor"})
_VALID_FRESHNESS = frozenset({"fresh", "warming_up", "stale", "warning", "pending", "unavailable"})


def kind_dot(kind: str) -> str:
    """Colored dot for risk-map / legend by kind."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"kind_dot: unknown kind {kind!r}; valid={sorted(_VALID_KINDS)}")
    return f'<span class="dot dot-{kind}"></span>'


def freshness_pill(freshness: str) -> str:
    """Freshness badge. Fresh is implied (no visible pill); others render label."""
    if freshness not in _VALID_FRESHNESS:
        raise ValueError(f"freshness_pill: unknown freshness {freshness!r}")
    if freshness == "fresh":
        return ""  # implied; no visible pill
    label_map = {
        "warming_up": "WARMING UP",
        "stale": "STALE",
        "warning": "WARN",
        "pending": "PENDING",
        "unavailable": "UNAVAILABLE",
    }
    css_state = freshness.replace("_", "-")
    label = label_map[freshness]
    return f'<span class="freshness-pill freshness-{css_state}">{label}</span>'


def cadence_pill_v5(cadence: str) -> str:
    return f'<span class="cadence-pill cadence-{_esc(cadence)}">{_esc(cadence.upper())}</span>'


def pull_quote_card(text: str) -> str:
    """Highlighted single-line editorial quote — used in front-of-book preview."""
    return f'<div class="pull-quote-card"><em>{_esc(text)}</em></div>'


def _relative_date_label(as_of: date, today: date) -> str:
    """Render a metric's age as a short human label for the meta footer."""
    delta = (today - as_of).days
    if delta <= 0:
        return "today"
    if delta == 1:
        return "yesterday"
    if delta < 14:
        return f"{delta}d ago"
    return as_of.strftime("%-d %b")


def metric_hero_card(
    metric: Metric,
    *,
    badge: str | None = None,
    supporting: str | None = None,
    today: date | None = None,
    is_hero: bool = True,
) -> str:
    """Metric card with status badge, supporting text, and meta footer.

    is_hero=True (default) — big-display variant that spans 2 grid columns
    with 56px value type. Use for the headline metric of a section, OR when
    the section's content is the metric grid itself.

    is_hero=False — compact variant: 1 grid column, 32px value. Use when
    another element (e.g. heatmap, chart) is the section hero and the
    numeric metrics demote to supporting roles.

    The meta footer (source · date · optional AGING chip) only renders when
    the metric has a value — placeholders/null metrics keep the bare card shape.
    """
    if today is None:
        today = now_bdt().date()

    badge_html = ""
    if badge:
        badge_html = f'<span class="metric-badge">{_esc(badge)}</span>'
    supporting_html = ""
    if supporting:
        supporting_html = f'<p class="metric-supporting">{_esc(supporting)}</p>'
    value_html = (
        fmt_num(metric.value, unit=metric.unit, tabular=True)
        if isinstance(metric.value, (int, float))
        else _esc(str(metric.value))
    )

    meta_html = ""
    if metric.value is not None:
        rel = _relative_date_label(metric.as_of, today)
        aging_chip = ""
        if metric_aging(metric, today=today):
            aging_chip = '<span class="metric-aging-chip">AGING</span>'
        meta_html = (
            '<div class="metric-meta">'
            f'<span class="metric-source">{_esc(metric.source)}</span>'
            f' · <span class="metric-asof">{_esc(rel)}</span>'
            f'{aging_chip}'
            '</div>'
        )

    sparkline_html = ""
    if metric.history_values and len(metric.history_values) >= 7:
        # hero metrics get the brand oxblood stroke; supporting cards get a softer ink
        stroke = "#6b1f27" if metric.hero else "#444"
        variant_cls = "metric-sparkline-hero" if metric.hero else "metric-sparkline-supporting"
        sparkline_html = (
            f'<div class="metric-sparkline {variant_cls}">'
            + sparkline_svg(metric.history_values, color=stroke, w=140, h=28)
            + '</div>'
        )

    card_class = "metric-card metric-card-hero" if is_hero else "metric-card metric-card-compact"
    return (
        f'<div class="{card_class}">'
        f'<div class="metric-label">{_esc(metric.label)}</div>'
        f'<div class="metric-value">{value_html}</div>'
        f'{sparkline_html}'
        f'{badge_html}'
        f'{supporting_html}'
        f'{meta_html}'
        '</div>'
    )


def source_badge(source: str) -> str:
    """Render a source as a small colored lozenge.

    Known sources (REU/DS/TBS/FE/BBC/AJZ/FT/BBN) get their brand-tinted
    badge; anything else falls back to a neutral lozenge with the raw
    source string. Display label is always the short code when known so
    the layout stays compact in dense headline rails.
    """
    code = resolve_source_code(source)
    if code is None:
        return f'<span class="source-badge source-badge-default">{_esc(source)}</span>'
    badge = SOURCE_BADGES[code]
    return (
        f'<span class="source-badge source-badge-{badge["css"]}" '
        f'title="{_attr_esc(badge["name"])}">{_esc(code)}</span>'
    )


def news_bullet(item: NewsItem, *, summary: str = "") -> str:
    """News bullet with title, summary lede, source/date attribution."""
    pub_label = item.published.strftime("%-d %b %Y")
    return (
        '<li class="news-bullet">'
        f'<a class="news-title" href="{_attr_esc(item.url)}">{_esc(item.title)}</a>'
        f'<p class="news-summary">{_esc(summary)}</p>'
        '<div class="news-attr">'
        f'{source_badge(item.source)}'
        f' <span class="news-date">{_esc(pub_label)}</span>'
        '</div>'
        '</li>'
    )


def line_chart_svg(
    series: list[float | None],
    *,
    x_labels: list[str],
    y_min: float | None = None,
    y_max: float | None = None,
    w: int = 520,
    h: int = 220,
    pad: int = 36,
    comparison_series: list[float | None] | None = None,
    color: str = "#6b1f27",
    comparison_color: str = "#999",
) -> str:
    """Multi-point line chart with axis ticks and dot markers.

    Skips None values when drawing the path (gap rendering, not interpolated).
    Returns "" when fewer than 2 non-None points are available.

    Useful for the yield curve hero (§07 T-Bond) — and any future series
    where today's reading is plotted against a comparison.
    """
    # Need at least 2 valid (i, value) pairs to draw a line
    valid = [(i, v) for i, v in enumerate(series) if isinstance(v, (int, float))]
    if len(valid) < 2:
        return ""

    # Auto-derive bounds when not specified
    all_known = [v for v in series if isinstance(v, (int, float))]
    if comparison_series:
        all_known += [v for v in comparison_series if isinstance(v, (int, float))]
    if y_min is None:
        y_min = min(all_known)
    if y_max is None:
        y_max = max(all_known)
    if y_max == y_min:
        y_max = y_min + 1.0  # avoid div-by-zero on flat data

    inner_w = w - 2 * pad
    inner_h = h - 2 * pad
    n = len(series)

    def _x(i: int) -> float:
        return pad + (i / max(n - 1, 1)) * inner_w

    def _y(v: float) -> float:
        return pad + (1 - (v - y_min) / (y_max - y_min)) * inner_h

    def _path(values: list[float | None]) -> str:
        d_parts: list[str] = []
        first = True
        for i, v in enumerate(values):
            if not isinstance(v, (int, float)):
                first = True  # break the path at the gap
                continue
            cmd = "M" if first else " L"
            d_parts.append(f"{cmd}{_x(i):.1f},{_y(v):.1f}")
            first = False
        return "".join(d_parts)

    # 4 horizontal gridlines evenly spaced between y_min and y_max
    gridline_html: list[str] = []
    grid_steps = 4
    for k in range(grid_steps + 1):
        gv = y_min + (y_max - y_min) * k / grid_steps
        gy = _y(gv)
        gridline_html.append(
            f'<line x1="{pad}" y1="{gy:.1f}" x2="{w - pad}" y2="{gy:.1f}" '
            f'stroke="#ddd" stroke-width="0.5"/>'
        )
        gridline_html.append(
            f'<text x="{pad - 6}" y="{gy + 3:.1f}" text-anchor="end" '
            f'font-family="monospace" font-size="10" fill="#888">'
            f'{gv:.2f}</text>'
        )

    # x-axis labels
    label_html: list[str] = []
    for i, lab in enumerate(x_labels[:n]):
        label_html.append(
            f'<text x="{_x(i):.1f}" y="{h - pad + 18}" text-anchor="middle" '
            f'font-family="monospace" font-size="10" fill="#888">{_attr_esc(lab)}</text>'
        )

    # Optional comparison line (rendered first so it sits behind the main line)
    cmp_path_html = ""
    if comparison_series:
        cmp_d = _path(list(comparison_series))
        if cmp_d:
            cmp_path_html = (
                f'<path d="{cmp_d}" fill="none" stroke="{comparison_color}" '
                f'stroke-width="1.5" stroke-dasharray="3 4"/>'
            )

    main_d = _path(series)
    main_path_html = (
        f'<path d="{main_d}" fill="none" stroke="{color}" stroke-width="2.5"/>'
    )

    # Dot markers on the main series
    dots_html: list[str] = []
    for i, v in enumerate(series):
        if isinstance(v, (int, float)):
            dots_html.append(
                f'<circle cx="{_x(i):.1f}" cy="{_y(v):.1f}" r="3.5" fill="{color}"/>'
            )

    return (
        f'<svg width="100%" viewBox="0 0 {w} {h}" '
        f'xmlns="http://www.w3.org/2000/svg" class="line-chart">'
        + "".join(gridline_html)
        + "".join(label_html)
        + cmp_path_html
        + main_path_html
        + "".join(dots_html)
        + '</svg>'
    )


def heatmap_svg(sectors) -> str:
    """4×2 sector heatmap tile grid for §06 DSE.

    `sectors` is a list of dicts: ``[{"sector": "Banks", "pct": -1.4}, ...]``
    Returns "" on empty/None input. Each tile gets a CSS custom property
    ``--heatmap-intensity`` (0.0–1.0, scaled to the largest abs % across
    the set) so stylesheet rules can paint background opacity.

    Sign is encoded via ``heatmap-tile-pos`` / ``heatmap-tile-neg`` classes
    so up/down coloring is theme-able from CSS.
    """
    if not sectors:
        return ""

    # Normalize intensity against the largest absolute pct in the set,
    # capped so a single outlier doesn't wash the others out.
    max_abs = max((abs(s["pct"]) for s in sectors if isinstance(s.get("pct"), (int, float))), default=0.0)
    cap = max(max_abs, 1.0)  # at least ±1% range so small swings are visible

    tiles_html: list[str] = []
    for s in sectors:
        sector = str(s.get("sector", ""))
        pct = s.get("pct")
        if not isinstance(pct, (int, float)):
            continue
        sign_cls = "heatmap-tile-pos" if pct >= 0 else "heatmap-tile-neg"
        intensity = min(abs(pct) / cap, 1.0)
        sign = "+" if pct > 0 else ("" if pct < 0 else "+")
        # NB: ``+`` for zero per V1 mockup convention (flat reads as small-positive)
        if pct == 0:
            sign = ""
        tiles_html.append(
            f'<div class="heatmap-tile {sign_cls}" '
            f'style="--heatmap-intensity: {intensity:.2f}">'
            f'<div class="heatmap-tile-label">{_esc(sector)}</div>'
            f'<div class="heatmap-tile-pct">{sign}{pct:.1f}%</div>'
            '</div>'
        )

    return f'<div class="sector-heatmap">{"".join(tiles_html)}</div>'


def bankerread_panel_v5(br: BankerReadInsight, *, anchor: str) -> str:
    """V5 banker's read panel — V1-mockup style.

    Compact inline §A/§B/§C/§D label prefixes (no MEANING/ACTION/TRIGGER/FOCUS
    spelled out per-line), with a single legend footer. Matches the V1 Map
    Front mockup BankerRead component.

    variant=full: render all four lines.
    variant=stale_micro: render only §A meaning + pull_quote.
    variant=v4_legacy: not supported here — caller must use V4 panel.
    """
    if br.variant == "v4_legacy":
        raise ValueError("bankerread_panel_v5 received v4_legacy variant; use V4 renderer")

    def _line(label: str, body: str | None) -> str:
        if not body:
            return ""
        return (
            '<div class="br-line">'
            f'<span class="br-lbl">{label}</span>'
            f'<span class="br-text">{_esc(body)}</span>'
            '</div>'
        )

    body_html = _line("§A", br.meaning)
    if br.variant == "full":
        body_html += _line("§B", br.action)
        body_html += _line("§C", br.trigger)
        body_html += _line("§D", br.focus)

    pull_html = ""
    if br.pull_quote:
        pull_html = f'<div class="br-pull-quote"><em>{_esc(br.pull_quote)}</em></div>'

    header_html = (
        '<div class="br-header">'
        '<span class="bankerread-label">BankerRead</span>'
        '<span class="br-sub">4 sentences · today</span>'
        '</div>'
    ) if br.variant == "full" else (
        '<div class="br-header">'
        '<span class="bankerread-label">BankerRead</span>'
        '<span class="br-sub">stale</span>'
        '</div>'
    )

    legend_html = (
        '<div class="br-foot">'
        '<span class="br-legend">A · Meaning &nbsp; B · Action &nbsp; C · Trigger &nbsp; D · Focus</span>'
        f'<a class="bankerread-jump" href="#{_attr_esc(anchor)}">← back to map</a>'
        '</div>'
    ) if br.variant == "full" else (
        f'<a class="bankerread-jump" href="#{_attr_esc(anchor)}">← back to map</a>'
    )

    return (
        f'<aside class="bankerread bankerread-v5 br-{br.variant}" id="br-{_attr_esc(anchor)}">'
        f'{header_html}'
        f'{pull_html}'
        f'<div class="br-body">{body_html}</div>'
        f'{legend_html}'
        '</aside>'
    )


def systemic_risk_callout(risk: SystemicRisk) -> str:
    """Red/amber bordered callout — only rendered when builder fires the rule."""
    return (
        f'<aside class="systemic-risk systemic-risk-{risk.level}" data-rule="{_attr_esc(risk.rule_id)}">'
        f'<div class="systemic-risk-icon" aria-hidden="true">⚠</div>'
        f'<h3 class="systemic-risk-headline">{_esc(risk.headline)}</h3>'
        f'<p class="systemic-risk-body">{_esc(risk.body)}</p>'
        '</aside>'
    )
