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
