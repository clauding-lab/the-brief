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


def pct_change_since(
    history: Sequence[HistoryRow],
    *,
    current_value: float,
    reference_as_of: str,
    formatter: Callable[[float], str],
    cadence: str,
) -> HistoryFact | None:
    """Compute the delta from current to a specific reference date.

    `reference_as_of` is an ISO date string. Looks up the exact row; returns None
    if not present (caller's responsibility to pass a date that exists in history).
    """
    target = date.fromisoformat(reference_as_of)
    for row in history:
        if row.as_of == target:
            ref_formatted = formatter(row.value)
            period_label = _format_as_of(row.as_of, cadence)
            return HistoryFact(
                metric_id=row.metric_id,
                kind="vs_period",
                phrase=f"vs {period_label} ({ref_formatted} then)",
                reference_value=row.value,
                reference_value_formatted=ref_formatted,
                reference_as_of=row.as_of.isoformat(),
            )
    return None


def rolling_extremes(
    history: Sequence[HistoryRow],
    *,
    current_value: float,
    window: int,
    formatter: Callable[[float], str],
    cadence: str,
) -> HistoryFact | None:
    """Compute min/max within a window of N data points; return the more notable extreme.

    If current_value is at or near the window max OR min, return a HistoryFact
    naming the relevant extreme. If current_value sits in the middle, return None.
    """
    if len(history) < MIN_DATA_POINTS.get(cadence, 6):
        return None

    window_rows = history[:window]
    if not window_rows:
        return None

    values = [r.value for r in window_rows]
    win_min = min(values)
    win_max = max(values)

    # Compute current_value's rank in window (lower index = higher value)
    sorted_desc = sorted(values, reverse=True)
    try:
        rank_high = sorted_desc.index(current_value) + 1  # 1 = highest
    except ValueError:
        rank_high = None

    # Notable if current is exact max, exact min, or in top/bottom 5 of window
    if current_value == win_max:
        # Find the row that previously held the max (excluding current)
        prior_max = max((r for r in window_rows[1:]), key=lambda r: r.value, default=None)
        if prior_max is None:
            return None
        return HistoryFact(
            metric_id=window_rows[0].metric_id,
            kind="extreme_in_window",
            phrase=f"highest in {window}-period window (prior {formatter(prior_max.value)} on {_format_as_of(prior_max.as_of, cadence)})",
            reference_value=prior_max.value,
            reference_value_formatted=formatter(prior_max.value),
            reference_as_of=prior_max.as_of.isoformat(),
        )
    if current_value == win_min:
        prior_min = min((r for r in window_rows[1:]), key=lambda r: r.value, default=None)
        if prior_min is None:
            return None
        return HistoryFact(
            metric_id=window_rows[0].metric_id,
            kind="extreme_in_window",
            phrase=f"lowest in {window}-period window (prior {formatter(prior_min.value)} on {_format_as_of(prior_min.as_of, cadence)})",
            reference_value=prior_min.value,
            reference_value_formatted=formatter(prior_min.value),
            reference_as_of=prior_min.as_of.isoformat(),
        )
    if rank_high and rank_high <= 5:
        return HistoryFact(
            metric_id=window_rows[0].metric_id,
            kind="extreme_in_window",
            phrase=f"{rank_high}th-highest in {window}-period window",
            reference_value=win_max,
            reference_value_formatted=formatter(win_max),
            reference_as_of=window_rows[0].as_of.isoformat(),
        )
    return None


def first_cross_since(
    history: Sequence[HistoryRow],
    *,
    current_value: float,
    threshold: float,
    direction: Literal["up", "down"],
    formatter: Callable[[float], str],
    cadence: str,
) -> HistoryFact | None:
    """Return a HistoryFact for the most recent time the metric was on the other side of `threshold`.

    direction='up' means current is above threshold; find the last time the metric was above threshold previously.
    direction='down' means current is below threshold; find the last time the metric was below threshold previously.
    """
    if len(history) < MIN_DATA_POINTS.get(cadence, 6):
        return None

    if direction == "up" and current_value <= threshold:
        return None
    if direction == "down" and current_value >= threshold:
        return None

    threshold_formatted = formatter(threshold)
    direction_word = "above" if direction == "up" else "below"

    # Skip the current row (history[0])
    for row in history[1:]:
        if (direction == "up" and row.value > threshold) or (direction == "down" and row.value < threshold):
            period_label = _format_as_of(row.as_of, cadence)
            ref_formatted = formatter(row.value)
            return HistoryFact(
                metric_id=row.metric_id,
                kind="first_cross_since",
                phrase=f"first time {direction_word} {threshold_formatted} since {period_label} ({ref_formatted} last cross)",
                reference_value=row.value,
                reference_value_formatted=ref_formatted,
                reference_as_of=row.as_of.isoformat(),
            )
    return None


def compute_history_facts(
    history: Sequence[HistoryRow],
    *,
    cadence: str,
    current_value: float | None,
    formatter: Callable[[float], str],
    rolling_window: int | None = None,
) -> list[HistoryFact]:
    """Run all primitives over a metric's history and return all non-None facts.

    Returns an empty list when:
      - current_value is None (no live value to anchor against)
      - history is shorter than MIN_DATA_POINTS for the cadence
    """
    if current_value is None:
        return []
    if len(history) < MIN_DATA_POINTS.get(cadence, 6):
        return []

    facts: list[HistoryFact] = []

    # since_lower / since_higher are mutually exclusive on the same current value
    lower = last_lower_than(history, current_value=current_value, cadence=cadence, formatter=formatter)
    if lower:
        facts.append(lower)
    else:
        higher = last_higher_than(history, current_value=current_value, cadence=cadence, formatter=formatter)
        if higher:
            facts.append(higher)

    # rolling_extremes adds a window-rank fact if current is near an extreme
    window = rolling_window or DEFAULT_WINDOW.get(cadence, 30)
    extreme = rolling_extremes(
        history,
        current_value=current_value,
        window=window,
        formatter=formatter,
        cadence=cadence,
    )
    if extreme:
        facts.append(extreme)

    return facts


def fetch_and_compute(
    client: MetricHistoryClient,
    metric_id: str,
    *,
    cadence: str,
    current_value: float | None,
    formatter: Callable[[float], str],
) -> list[HistoryFact]:
    """Pull history for a single metric and compute facts.

    Cadence-aware: chooses the right Supabase table per CADENCE_TABLE.
    """
    table = CADENCE_TABLE.get(cadence, "metric_history")
    window = DEFAULT_WINDOW.get(cadence, 365)
    grouped = client.get_history_window([metric_id], limit=window, table=table)
    history = grouped.get(metric_id, [])
    return compute_history_facts(
        history,
        cadence=cadence,
        current_value=current_value,
        formatter=formatter,
    )
