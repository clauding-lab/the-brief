from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from brief.builders import BuilderContext
from brief.builders.dse import build
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow


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
