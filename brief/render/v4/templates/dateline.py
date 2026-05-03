"""V4 dateline template — top oxblood ticker bar.

LIVE pulse + Dhaka time + 4 headline metrics + next-update note.
"""
from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brief.pipeline import RunResult

from brief.cadence import now_bdt
from brief.render.v4._jsx import fmt_num

# ---------------------------------------------------------------------------
# Freshness mapping (SectionData.freshness → staleness_dot states)
# Not used in dateline but kept here for reference consistency.
# ---------------------------------------------------------------------------

_EM_DASH = "—"


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def _find_section(run_result: "RunResult", section_id: str):
    """Return first SectionData with given id, or None."""
    for s in run_result.sections:
        if s.id == section_id:
            return s
    return None


def _find_metric(section, *id_substrings: str):
    """Return first metric whose id contains any of the given substrings (case-insensitive).

    Falls back to the first metric in the section if no match found.
    Returns None if section is None or has no metrics.
    """
    if section is None or not section.metrics:
        return None
    for substring in id_substrings:
        sub_lower = substring.lower()
        for m in section.metrics:
            if sub_lower in m.id.lower() or sub_lower in m.label.lower():
                return m
    # Fallback: first metric
    return section.metrics[0]


def _metric_html(label: str, metric) -> str:
    """Render a single dateline metric chip."""
    if metric is None or metric.value is None:
        value_html = _EM_DASH
    else:
        # Use fmt_num without tabular wrapping for the compact ticker bar
        value_html = fmt_num(metric.value, metric.unit, tabular=False)
    escaped_label = _esc(label)
    return (
        f'<span class="metric">'
        f'<span class="label">{escaped_label}</span> '
        f'<span class="value">{value_html}</span>'
        f"</span>"
    )


def render_dateline(run_result: "RunResult") -> str:
    """Top oxblood ticker: LIVE pulse + time + 4 headline metrics + 'Next update · 18:00 close'."""
    now = now_bdt()
    time_str = now.strftime("%H:%M BDT")

    # --- 4 headline metrics ---
    fx_section = _find_section(run_result, "fx")
    dse_section = _find_section(run_result, "dse")
    iranwar_section = _find_section(run_result, "iranwar")
    bb_section = _find_section(run_result, "bb")

    usd_bdt_metric = _find_metric(fx_section, "usd_bdt", "usd/bdt", "usd", "bdt")
    dsex_metric = _find_metric(dse_section, "dsex", "close", "dse")
    brent_metric = _find_metric(iranwar_section, "brent")
    reserves_metric = _find_metric(bb_section, "reserves")

    metrics_html = (
        _metric_html("USD/BDT", usd_bdt_metric)
        + _metric_html("DSEX", dsex_metric)
        + _metric_html("Brent", brent_metric)
        + _metric_html("Reserves", reserves_metric)
    )

    return (
        '<section class="dateline" role="banner">'
        '<span class="live"><span class="dot"></span>LIVE</span>'
        f'<span class="time">{_esc(time_str)}</span>'
        f'<span class="metrics">{metrics_html}</span>'
        '<span class="next-update">Next update · 18:00 close</span>'
        "</section>"
    )
