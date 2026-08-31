"""Unit test for fetch_yield_ladder_monthly (F5 — §tbond 8-tenor yield ladder)."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from brief.chart_series_fetcher import (
    _YIELD_LADDER_MONTHLY_METRIC_IDS,
    YIELD_LADDER_AUCTION_NOTE_KEY,
    fetch_yield_ladder_last_auction,
    fetch_yield_ladder_monthly,
)
from brief.history import HistoryRow
from brief.v6_schema import SeriesPointV6


def _row(metric_id: str, as_of: str, value: float) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=date.fromisoformat(as_of), value=value, source="t")


def test_fetch_yield_ladder_monthly_returns_all_tenors_last_two_months():
    mock = MagicMock()

    def _get_history_window(metric_ids, *, limit=None, days=None, today=None, table="metric_history"):
        # PostgREST anchor mode returns most-recent-first; mock 2 month-ends desc.
        return {
            m: [_row(m, "2026-04-01", 10.5), _row(m, "2026-03-01", 9.9)]
            for m in metric_ids
        }

    mock.get_history_window.side_effect = _get_history_window

    result = fetch_yield_ladder_monthly(mock, months=2)

    # All 8 tenors present.
    assert set(result.keys()) == set(_YIELD_LADDER_MONTHLY_METRIC_IDS)
    assert len(_YIELD_LADDER_MONTHLY_METRIC_IDS) == 8
    for mid in _YIELD_LADDER_MONTHLY_METRIC_IDS:
        pts = result[mid]
        assert len(pts) == 2
        assert all(isinstance(p, SeriesPointV6) and p.key == mid for p in pts)
        # Output is chronological (oldest-first): March before April.
        assert pts[0].ts == "2026-03-01"
        assert pts[-1].ts == "2026-04-01"

    # Reads metric_history_monthly with a per-id limit (landmines #1, #14).
    _, kwargs = mock.get_history_window.call_args
    assert kwargs.get("table") == "metric_history_monthly"
    assert kwargs.get("limit") == 16  # months * 8 ids


def test_default_window_is_three_months():
    """Adnan asked for a 3-month curve on 2026-08-31 (was 2). The default is
    what production actually gets — pipeline_v6 calls this with no `months`."""
    mock = MagicMock()

    def _get_history_window(metric_ids, *, limit=None, days=None, today=None, table="metric_history"):
        return {
            m: [
                _row(m, "2026-08-01", 9.2),
                _row(m, "2026-07-01", 10.2),
                _row(m, "2026-06-01", 10.0),
            ]
            for m in metric_ids
        }

    mock.get_history_window.side_effect = _get_history_window

    result = fetch_yield_ladder_monthly(mock)  # no months= -> default

    _, kwargs = mock.get_history_window.call_args
    assert kwargs.get("limit") == 24  # 3 months * 8 ids
    for mid in _YIELD_LADDER_MONTHLY_METRIC_IDS:
        pts = result[mid]
        assert [p.ts for p in pts] == ["2026-06-01", "2026-07-01", "2026-08-01"]


# ---------------------------------------------------------------------------
# fetch_yield_ladder_last_auction — the chart's bottom footnote
# ---------------------------------------------------------------------------


def _row_sa(metric_id: str, as_of: str, value: float, source_as_of: str | None) -> HistoryRow:
    return HistoryRow(
        metric_id=metric_id,
        as_of=date.fromisoformat(as_of),
        value=value,
        source="t",
        source_as_of=date.fromisoformat(source_as_of) if source_as_of else None,
    )


def _client(rows_by_id):
    mock = MagicMock()
    mock.get_history_window.side_effect = (
        lambda metric_ids, **_kw: {m: rows_by_id(m) for m in metric_ids}
    )
    return mock


def test_last_auction_is_the_newest_auction_feeding_the_newest_month():
    """The footnote names the most recent auction behind the ACCENT line.

    Tenors auction on different days, so the August rung is a mix: most tenors
    carried forward from earlier dates, one or two struck late in the month.
    The reader wants the latest of those — that's how current the curve is."""
    def rows(mid):
        # August rung: 20y struck 27 Aug, everything else earlier in August.
        aug_src = "2026-08-27" if mid == "yield_20y_monthly" else "2026-08-05"
        return [
            _row_sa(mid, "2026-08-01", 9.2, aug_src),
            _row_sa(mid, "2026-07-01", 10.2, "2026-07-10"),
        ]

    note = fetch_yield_ladder_last_auction(_client(rows))

    assert note is not None
    assert note.series_key == YIELD_LADDER_AUCTION_NOTE_KEY
    assert note.ts == "2026-08-27"


def test_last_auction_ignores_older_months():
    """Only the newest `as_of` month feeds the footnote.

    A later `source_as_of` sitting on an OLDER rung (a backfill written after
    the fact, say) must not be reported as the cutoff of the line the chart
    draws in accent."""
    def rows(mid):
        return [
            _row_sa(mid, "2026-08-01", 9.2, "2026-08-05"),
            _row_sa(mid, "2026-07-01", 10.2, "2026-12-31"),  # later, but older month
        ]

    note = fetch_yield_ladder_last_auction(_client(rows))
    assert note is not None
    assert note.ts == "2026-08-05"


def test_last_auction_returns_none_when_no_row_carries_a_source_date():
    """Rows written before EconDelta recorded `source_as_of` must degrade to
    no footnote, not to a wrong or invented one."""
    def rows(mid):
        return [_row_sa(mid, "2026-08-01", 9.2, None)]

    assert fetch_yield_ladder_last_auction(_client(rows)) is None


def test_last_auction_returns_none_on_empty_history():
    def rows(_mid):
        return []

    assert fetch_yield_ladder_last_auction(_client(rows)) is None


def test_last_auction_reads_monthly_table_with_per_id_limit():
    """Landmines #1 and #14, same as the series fetcher."""
    def rows(mid):
        return [_row_sa(mid, "2026-08-01", 9.2, "2026-08-05")]

    client = _client(rows)
    fetch_yield_ladder_last_auction(client)
    _, kwargs = client.get_history_window.call_args
    assert kwargs.get("table") == "metric_history_monthly"
    assert kwargs.get("limit") == 24
