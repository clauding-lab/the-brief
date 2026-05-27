"""History anchors compute layer.

Reads metric_history (daily/weekly/quarterly/fiscal_year) and
metric_history_monthly (monthly long-horizon) and produces HistoryFact
instances for the editor to weave into chart_read.context, banker_read.verdict,
and Section.analysis.

The compute layer is the SOLE place that formats the parenthetical reference
value phrase. The editor inlines `phrase` verbatim and is forbidden from
inventing its own parens phrasing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal, Sequence

from brief.history import HistoryRow, MetricHistoryClient


HistoryKind = Literal[
    "since_lower",
    "since_higher",
    "vs_period",
    "extreme_in_window",
    "first_cross_since",
]


@dataclass(frozen=True)
class HistoryFact:
    """A pre-formatted historical anchor for the editor to inline verbatim.

    `phrase` ALREADY includes the reference value in parens — the editor must
    not append, modify, or replace the parenthetical. The editor MAY paraphrase
    the surrounding sentence.
    """
    metric_id: str
    kind: HistoryKind
    phrase: str                         # e.g. "lowest 12-month CPI since Sep 2021 (4.8% then)"
    reference_value: float              # raw numeric reference point
    reference_value_formatted: str      # e.g. "4.8%" — already embedded in `phrase`
    reference_as_of: str                # ISO date "2021-09-01" or period "Q3 2024"


# Minimum data points for "since X" claims to be statistical, not nominal.
# Below this threshold the compute layer returns no facts of that kind.
MIN_DATA_POINTS: dict[str, int] = {
    "daily":       30,
    "weekly":      12,
    "monthly":     6,
    "quarterly":   4,
    "fiscal_year": 3,
}

# Default look-back window (in data points, not calendar days — robust to gaps).
DEFAULT_WINDOW: dict[str, int] = {
    "daily":       365,
    "weekly":      52,
    "monthly":     60,
    "quarterly":   16,
    "fiscal_year": 5,
}

# Which Supabase table holds the history for each cadence.
CADENCE_TABLE: dict[str, str] = {
    "daily":       "metric_history",
    "weekly":      "metric_history",
    "monthly":     "metric_history_monthly",
    "quarterly":   "metric_history",
    "fiscal_year": "metric_history",
}

_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _format_as_of(d: date, cadence: str) -> str:
    """Format a date as a banker-friendly period label.

    monthly  → 'Sep 2021'
    quarterly → 'Q3 2024'  (computed from month)
    daily/weekly → 'Sep 2021'  (month-level granularity is enough for prose)
    fiscal_year → 'FY24'  (Bangladesh FY runs Jul-Jun)
    """
    if cadence == "quarterly":
        q = (d.month - 1) // 3 + 1
        return f"Q{q} {d.year}"
    if cadence == "fiscal_year":
        # BD FY runs Jul-Jun; FY24 ends Jun 2024
        fy = d.year if d.month >= 7 else d.year - 1
        return f"FY{str(fy)[-2:]}"
    return f"{_MONTH_ABBR[d.month - 1]} {d.year}"


def last_lower_than(
    history: Sequence[HistoryRow],
    *,
    current_value: float,
    cadence: str,
    formatter: Callable[[float], str],
) -> HistoryFact | None:
    """Return a HistoryFact for the most recent row whose value is < current_value.

    `history` MUST be ordered most-recent-first (PostgREST `order=as_of.desc`).
    Returns None when:
      - fewer than MIN_DATA_POINTS[cadence] rows are available
      - no row in `history` is below `current_value`
    """
    min_pts = MIN_DATA_POINTS.get(cadence, 6)
    if len(history) < min_pts:
        return None

    metric_id = history[0].metric_id
    for row in history:
        if row.value < current_value:
            ref_formatted = formatter(row.value)
            period_label = _format_as_of(row.as_of, cadence)
            return HistoryFact(
                metric_id=metric_id,
                kind="since_lower",
                phrase=f"lowest since {period_label} ({ref_formatted} then)",
                reference_value=row.value,
                reference_value_formatted=ref_formatted,
                reference_as_of=row.as_of.isoformat(),
            )
    return None


def last_higher_than(
    history: Sequence[HistoryRow],
    *,
    current_value: float,
    cadence: str,
    formatter: Callable[[float], str],
) -> HistoryFact | None:
    """Mirror of last_lower_than — returns the most recent row above current_value.

    `history` MUST be ordered most-recent-first (PostgREST `order=as_of.desc`).
    Returns None when:
      - fewer than MIN_DATA_POINTS[cadence] rows are available
      - no row in `history` is above `current_value`
    """
    min_pts = MIN_DATA_POINTS.get(cadence, 6)
    if len(history) < min_pts:
        return None

    metric_id = history[0].metric_id
    for row in history:
        if row.value > current_value:
            ref_formatted = formatter(row.value)
            period_label = _format_as_of(row.as_of, cadence)
            return HistoryFact(
                metric_id=metric_id,
                kind="since_higher",
                phrase=f"highest since {period_label} ({ref_formatted} then)",
                reference_value=row.value,
                reference_value_formatted=ref_formatted,
                reference_as_of=row.as_of.isoformat(),
            )
    return None
