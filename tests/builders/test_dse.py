from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from brief.builders import BuilderContext
from brief.builders.dse import build
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow
from brief.vintage import period_label


def _snap():
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={"dse_market": {"status": "ok", "age_hours": 6.94}},
        data={
            "dsex": 5232.49, "dsex_change": -15.05, "dsex_change_pct": -0.29,
            "ds30": 1980.01, "dses": 1059.70, "turnover_crore": 824.76,
            "advancing": 120, "declining": 207, "unchanged": 62,
        },
    )


def test_dse_fresh_has_seven_metrics():
    ctx = BuilderContext(snapshot=_snap(), history=MagicMock(),
                         today=date(2026, 4, 21))
    s = build(ctx)
    assert s.id == "dse"
    ids = {m.id for m in s.metrics}
    assert {"dsex", "dse_dsex_change_pct", "dse_ds30",
            "dse_dses", "dse_turnover_crore", "dse_advancing",
            "dse_declining"}.issubset(ids)
    # Historical persistence moved upstream to EconDelta — the dse builder
    # no longer writes to history. See econdelta/docs/data-contract.md.
    ctx.history.upsert_many.assert_not_called()


def test_dse_saturday_run_with_same_day_data_is_fresh():
    # Same-day Saturday data should show fresh under daily cadence.
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 4, 18))
    s = build(ctx)
    dsex = next(m for m in s.metrics if m.id == "dsex")
    assert dsex.value == 5232.49
    assert s.freshness in ("fresh", "warning")


def test_dse_stale_fallback_reads_live_dsex_series_not_legacy():
    """On a non-trading day (no snapshot DSEX), the tile must fall back to the
    LIVE `dsex` metric_history series, never the frozen legacy `dse_dsex_close`.

    Regression for the 2026-07-04 review: the fallback key was `dse_dsex_close`
    (dead at 5,257 / 2026-04-21) while the chart used live `dsex`, so a stale day
    rendered a dead number under a live chart.
    """
    from brief.history import HistoryRow

    snap = EconDeltaSnapshot(
        updated_at=datetime(2026, 6, 11, tzinfo=timezone.utc),
        sources_status={"dse_market": {"status": "ok"}},
        data={"dsex": None, "dsex_change_pct": None, "ds30": None,
              "dses": None, "turnover_crore": None,
              "advancing": None, "declining": None, "unchanged": None},
    )

    requested_ids: list[str] = []

    def _get_latest(metric_id, **kwargs):
        requested_ids.append(metric_id)
        if metric_id == "dsex":
            return HistoryRow(metric_id="dsex", as_of=date(2026, 6, 11),
                              value=5516.82, source="DSE")
        return None

    history = MagicMock()
    history.get_latest.side_effect = _get_latest

    ctx = BuilderContext(snapshot=snap, history=history, today=date(2026, 6, 13))
    s = build(ctx)

    dsex = next(m for m in s.metrics if m.id == "dsex")
    assert dsex.value == 5516.82          # live series value, not the dead 5,257
    assert dsex.stale is True             # marked stale (last trading session)
    assert "dsex" in requested_ids        # fallback queried the LIVE series id
    assert "dse_dsex_close" not in requested_ids  # never the dead legacy series


def test_dse_stale_fallback_reads_live_series_for_other_six_tiles():
    """On a non-trading day, DS30/DSES/Turnover/Advancing/Declining/DSEX-%Δ must
    fall back to the LIVE metric_history ids EconDelta actually writes
    (ds30, dses, turnover_crore, advancing, declining, dsex_change_pct) —
    never the dead dse_-prefixed ids that were never written, which would
    resolve to None and render the wall-of-None the fallback exists to avoid.
    """
    snap = EconDeltaSnapshot(
        updated_at=datetime(2026, 6, 11, tzinfo=timezone.utc),
        sources_status={"dse_market": {"status": "ok"}},
        data={"dsex": None, "dsex_change_pct": None, "ds30": None,
              "dses": None, "turnover_crore": None,
              "advancing": None, "declining": None, "unchanged": None},
    )

    live_values = {
        "dsex_change_pct": -0.29,
        "ds30": 1980.01,
        "dses": 1059.70,
        "turnover_crore": 824.76,
        "advancing": 120,
        "declining": 207,
    }
    requested_ids: list[str] = []

    def _get_latest(metric_id, **kwargs):
        requested_ids.append(metric_id)
        if metric_id in live_values:
            return HistoryRow(metric_id=metric_id, as_of=date(2026, 6, 11),
                              value=live_values[metric_id], source="DSE")
        return None

    history = MagicMock()
    history.get_latest.side_effect = _get_latest

    ctx = BuilderContext(snapshot=snap, history=history, today=date(2026, 6, 13))
    s = build(ctx)

    by_id = {m.id: m for m in s.metrics}
    # Display Metric.id values stay unchanged (prev-brief diff continuity + SPA keys).
    assert by_id["dse_dsex_change_pct"].value == -0.29
    assert by_id["dse_ds30"].value == 1980.01
    assert by_id["dse_dses"].value == 1059.70
    assert by_id["dse_turnover_crore"].value == 824.76
    assert by_id["dse_advancing"].value == 120
    assert by_id["dse_declining"].value == 207
    for mid in ("dse_dsex_change_pct", "dse_ds30", "dse_dses",
                "dse_turnover_crore", "dse_advancing", "dse_declining"):
        assert by_id[mid].stale is True

    # Fallback must query the live ids EconDelta writes...
    for live_id in live_values:
        assert live_id in requested_ids
    # ...and never the dead dse_-prefixed ids.
    for dead_id in ("dse_dsex_change_pct", "dse_ds30", "dse_dses",
                    "dse_turnover_crore", "dse_advancing", "dse_declining"):
        assert dead_id not in requested_ids


def test_fresh_snapshot_dates_metrics_by_session_not_run_date():
    """Issue 206 regression. The 24 Aug 08:16 BDT publish read a snapshot
    holding the 23 AUG session (DSE opens 10:00; there was no 24 Aug
    session yet) and stamped every metric as_of = the RUN date, so
    period_label produced '24 Aug 2026' and editor_v6.txt:290 ordered the
    editor to print it verbatim — while the same section's chart_read,
    driven by series_summary.last_ts, correctly said 23 Aug.
    """
    snap = EconDeltaSnapshot(
        updated_at=datetime(2026, 8, 23, 21, 15, tzinfo=timezone.utc),
        sources_status={"dse_market": {"status": "ok"}},
        data={"dsex": 5722.21464, "dsex_change_pct": -1.10379,
              "ds30": 2145.48199, "dses": None, "turnover_crore": 711.1497,
              "advancing": 32, "declining": 324, "unchanged": 0},
    )
    history = MagicMock()
    history.get_latest.side_effect = lambda k: HistoryRow(
        metric_id=k, as_of=date(2026, 8, 23), value=snap.get(k), source="EconDelta"
    )
    ctx = BuilderContext(snapshot=snap, history=history, today=date(2026, 8, 24))
    dsex = next(m for m in build(ctx).metrics if m.id == "dsex")
    assert dsex.as_of == date(2026, 8, 23)               # FAILS today: 2026-08-24
    assert period_label(dsex.as_of, "daily") == "23 Aug 2026"  # FAILS: '24 Aug 2026'
    assert dsex.as_of < ctx.today, "a session date may never be the run date"


def test_fresh_snapshot_with_history_outage_falls_back_to_prior_trading_day_never_run_date():
    """When history is unreachable (get_latest raises), the fresh branch must
    NOT default to ctx.today — it must fall back to the last BD trading day
    strictly before the run. ctx.today here is a Saturday (non-trading), so
    the correct fallback skips Friday too and lands on Thursday.
    """
    snap = EconDeltaSnapshot(
        updated_at=datetime(2026, 8, 22, 3, 0, tzinfo=timezone.utc),
        sources_status={"dse_market": {"status": "ok"}},
        data={"dsex": 5722.21464, "dsex_change_pct": -1.10379,
              "ds30": 2145.48199, "dses": 1059.70, "turnover_crore": 711.1497,
              "advancing": 32, "declining": 324, "unchanged": 0},
    )
    _spec_keys = {"dsex", "dsex_change_pct", "ds30", "dses", "turnover_crore",
                  "advancing", "declining"}

    def _get_latest(metric_id, **kwargs):
        if metric_id in _spec_keys:
            raise RuntimeError("Supabase unreachable")
        return None  # sector-heat lookups outside this test's scope

    history = MagicMock()
    history.get_latest.side_effect = _get_latest

    ctx = BuilderContext(snapshot=snap, history=history, today=date(2026, 8, 22))
    dsex = next(m for m in build(ctx).metrics if m.id == "dsex")
    assert dsex.as_of == date(2026, 8, 20)  # last BD trading day before Sat 22 Aug
    assert dsex.as_of < ctx.today


def test_dse_unavailable_when_dsex_missing():
    snap = EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={"dse_market": {"status": "error"}},
        data={"dsex": None, "dsex_change": None, "dsex_change_pct": None,
              "ds30": None, "dses": None, "turnover_crore": None,
              "advancing": None, "declining": None, "unchanged": None},
    )
    ctx = BuilderContext(snapshot=snap, history=None, today=date(2026, 4, 21))
    s = build(ctx)
    assert s.freshness == "unavailable"
