"""V5 §07 — Treasury (T-Bonds & T-Bills) with yield curve chart hero.

Layout (Phase 2.3 V1 fidelity):
- Top row: 3 T-Bill tenor cards (91d / 182d / 364d) in a `.tbond-tbills` grid.
- Bottom row: 2 BGTB cards (5Y / 10Y) on the left, large yield curve chart
  on the right in a `.tbond-bond-chart` 1:2 grid.

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
        w=520,
        h=220,
    )
    if not chart:
        return ""

    return (
        '<div class="yield-curve-chart">'
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

    # ── T-Bill row (top: 91D / 182D / 364D) ──────────────────────────────────
    tbill_cards = []
    for mid in ("tbond_tbill_91d", "tbond_tbill_182d", "tbond_tbill_364d"):
        m = metrics_by_id.get(mid)
        if m is not None:
            tbill_cards.append(metric_hero_card(m))

    # ── Bond + chart row (bottom: 5Y / 10Y stacked + curve chart) ────────────
    bond_cards = []
    for mid in ("tbond_bond_5y", "tbond_bond_10y"):
        m = metrics_by_id.get(mid)
        if m is None:
            continue
        badge = None
        if mid == "tbond_bond_10y" and isinstance(m.value, (int, float)) and m.value > 12.0:
            badge = "WATCH"
        supporting = "BB weekly auction" if mid == "tbond_bond_10y" else None
        bond_cards.append(metric_hero_card(m, badge=badge, supporting=supporting))

    chart_html = _build_yield_curve_chart(metrics_by_id)

    metric_cards_html = ""
    if tbill_cards:
        metric_cards_html += f'<div class="tbond-tbills">{"".join(tbill_cards)}</div>'
    if bond_cards or chart_html:
        metric_cards_html += (
            '<div class="tbond-bond-chart">'
            f'<div class="tbond-bonds">{"".join(bond_cards)}</div>'
            f'{chart_html}'
            '</div>'
        )

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    # show_sparkline at section-level is now redundant with the yield curve
    # hero — the section's history_values would otherwise paint a sparkline
    # of one tenor's series, which clashes with the curve. Suppress it.
    return render_section_base(
        section,
        section_n="07",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=False,
    )
