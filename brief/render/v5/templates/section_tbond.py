"""V5 §08 — Treasury (T-Bonds & T-Bills) with yield curve chart hero.

Layout (post-2026-05-03 hero swap):
- Top: full-width yield curve chart (HERO).
- Bottom: 5 compact tenor cards in one row (91d / 182d / 364d / 5Y / 10Y).

The chart is a deterministic SVG rendered by `_jsx.line_chart_svg`. Today's
curve is drawn as a solid oxblood line; if every tenor metric carries at
least 8 days of history, last week's curve is drawn as a dashed grey
comparison underneath. With fewer than 2 valid tenors the chart silently
disappears (graceful degradation while EconDelta accumulates multi-tenor
data).
"""
from __future__ import annotations

from brief.render.v5._jsx import (
    fmt_num,
    line_chart_svg,
    metric_hero_card,
    news_bullet,
)
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


_TENOR_ORDER: tuple[tuple[str, str], ...] = (
    ("tbond_tbill_91d",  "3M"),
    ("tbond_tbill_182d", "6M"),
    ("tbond_tbill_364d", "1Y"),
    ("tbond_bond_5y",    "5Y"),
    ("tbond_bond_10y",   "10Y"),
)


def _build_yield_curve_chart(metrics_by_id: dict) -> str:
    """Compose the yield curve chart from any present tenor metrics.

    Returns "" when fewer than 2 tenors carry numeric values.
    """
    series: list[float | None] = []
    prev: list[float | None] = []
    x_labels: list[str] = []
    has_any_history = False

    for mid, lab in _TENOR_ORDER:
        x_labels.append(lab)
        m = metrics_by_id.get(mid)
        v = m.value if m is not None and isinstance(m.value, (int, float)) else None
        series.append(v)

        last_week = None
        if m is not None and m.history_values and len(m.history_values) >= 8:
            last_week = m.history_values[-8]
            has_any_history = True
        prev.append(last_week)

    chart = line_chart_svg(
        series,
        x_labels=x_labels,
        comparison_series=prev if has_any_history else None,
        w=900,
        h=280,
    )
    if not chart:
        return ""

    return (
        '<div class="yield-curve-chart yield-curve-hero">'
        '<div class="yc-eyebrow">'
        '<span>Yield Curve · BDT Govt</span>'
        '<span>Today vs Last Week</span>'
        '</div>'
        f'{chart}'
        '</div>'
    )


def render_section_tbond(section: SectionData) -> str:
    if section.id != "tbond":
        raise ValueError(f"render_section_tbond received id={section.id!r}; expected 'tbond'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    for mid, label in (("tbond_bond_10y", "10Y"),
                       ("tbond_bond_5y",  "5Y"),
                       ("tbond_tbill_91d", "91D")):
        m = metrics_by_id.get(mid)
        if m is not None and m.value is not None:
            pills.append(
                f'<span class="sum-pill"><span class="sum-key">{label}</span> '
                f'<strong>{fmt_num(m.value, unit=m.unit)}</strong></span>'
            )

    # ── Hero: full-width yield curve chart ─────────────────────────────────
    chart_html = _build_yield_curve_chart(metrics_by_id)

    # ── Compact tenor cards (one row of 5: 91d/182d/364d/5Y/10Y) ────────────
    tenor_cards = []
    for mid in ("tbond_tbill_91d", "tbond_tbill_182d", "tbond_tbill_364d",
                "tbond_bond_5y", "tbond_bond_10y"):
        m = metrics_by_id.get(mid)
        if m is None:
            continue
        badge = None
        if mid == "tbond_bond_10y" and isinstance(m.value, (int, float)) and m.value > 12.0:
            badge = "WATCH"
        supporting = "BB weekly auction" if mid == "tbond_bond_10y" else None
        tenor_cards.append(metric_hero_card(m, badge=badge, supporting=supporting, is_hero=False))

    metric_cards_html = ""
    if chart_html:
        metric_cards_html += chart_html
    if tenor_cards:
        metric_cards_html += f'<div class="tbond-tenor-row">{"".join(tenor_cards)}</div>'

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    # show_sparkline at section-level is now redundant with the yield curve
    # hero — the section's history_values would otherwise paint a sparkline
    # of one tenor's series, which clashes with the curve. Suppress it.
    return render_section_base(
        section,
        section_n="08",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=False,
    )
