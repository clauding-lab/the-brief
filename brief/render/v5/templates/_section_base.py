"""Shared per-section render shape — every V5 section template uses this scaffold.

Sections compose: header (numeral + kicker + title + tldr) → 3-pill summary →
optional systemic-risk callout → metric cards → optional sparkline → optional news → banker's read.
"""
from __future__ import annotations

from typing import Sequence

from brief.render.v5._jsx import (
    _attr_esc,
    _esc,
    bankerread_panel_v5,
    cadence_pill_v5,
    freshness_pill,
    sparkline_svg,
    systemic_risk_callout,
)
from brief.schema import SectionData


def _all_metrics_empty(section: SectionData) -> bool:
    """True when every metric in the section is null — i.e. there is
    nothing real to render. Used to swap the metric grid for a graceful
    "Section unavailable" placeholder instead of a wall of "None".
    """
    if not section.metrics:
        return True
    return all(m.value is None for m in section.metrics)


def _render_unavailable_placeholder(section: SectionData) -> str:
    """The graceful 'no data' card. Modelled on the V1 mockup's diagonal-stripe
    "§ SECTION UNAVAILABLE" treatment — explicit about what's missing and why,
    with a hint about when it'll refresh."""
    reason = section.freshness_reason or _default_unavailable_reason(section)
    return (
        '<div class="sec-unavailable">'
        '<div class="sec-unavailable-stripes" aria-hidden="true"></div>'
        '<div class="sec-unavailable-body">'
        '<span class="sec-unavailable-eyebrow">§ Section unavailable</span>'
        f'<p class="sec-unavailable-title">{_esc(section.title)} — no fresh data this cycle.</p>'
        f'<p class="sec-unavailable-reason">{_esc(reason)}</p>'
        '</div>'
        '</div>'
    )


def _default_unavailable_reason(section: SectionData) -> str:
    cadence = section.metrics[0].cadence if section.metrics else "event"
    if cadence == "daily":
        return "Pipeline still warming up — values populate on the next aggregate cycle."
    if cadence == "weekly":
        return "Weekly publication pending; section refreshes when the next bulletin lands."
    if cadence == "monthly":
        return "Monthly release not yet published; values refresh once the official series updates."
    if cadence == "quarterly":
        return "Quarterly release pending; section refreshes after the next BB / BBS publication."
    return "No fresh reading available; check back when the next cycle completes."


def render_section_base(
    section: SectionData,
    *,
    section_n: str,
    summary_pills: Sequence[str],
    metric_cards_html: str = "",
    news_block_html: str = "",
    show_sparkline: bool = True,
) -> str:
    """Return the full <section> HTML for a V5 section."""
    cadence = section.metrics[0].cadence if section.metrics else "event"
    pill = freshness_pill(section.freshness)
    cadence_p = cadence_pill_v5(cadence)

    # When every metric is null, swap the metric-card grid (which would
    # otherwise render a wall of "None") for a single graceful placeholder.
    if _all_metrics_empty(section):
        metric_cards_html = _render_unavailable_placeholder(section)

    risk_callout_html = ""
    if section.systemic_risk is not None:
        risk_callout_html = systemic_risk_callout(section.systemic_risk)

    sparkline_html = ""
    if show_sparkline and section.history_values and len(section.history_values) >= 7:
        sparkline_html = (
            '<div class="section-sparkline">'
            + sparkline_svg(section.history_values, w=240, h=48)
            + '</div>'
        )

    bankerread_html = ""
    if section.bankerread is not None and section.bankerread.variant != "v4_legacy":
        bankerread_html = bankerread_panel_v5(section.bankerread, anchor=section.id)

    summary_pills_html = "".join(summary_pills)

    return (
        f'<section class="section section-v5 section-{_attr_esc(section.id)}" id="section-{_attr_esc(section.id)}">'
        '<header class="sec-header">'
        f'<span class="sec-numeral">§{_esc(section_n)}</span>'
        f'<span class="sec-kicker">{_esc(section.kicker.upper())}</span>'
        f'<span class="sec-meta">{cadence_p}{pill}</span>'
        '</header>'
        f'<h2 class="sec-title"><em>{_esc(section.title)}</em></h2>'
        f'<p class="sec-tldr">{_esc(section.tldr)}</p>'
        '<div class="sec-summary-pills">'
        f'{summary_pills_html}'
        '</div>'
        f'{risk_callout_html}'
        '<div class="sec-metric-grid">'
        f'{metric_cards_html}'
        '</div>'
        f'{sparkline_html}'
        f'{news_block_html}'
        f'{bankerread_html}'
        '</section>'
    )
