import socket
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from brief.builders import BuilderContext
from brief.builders.dse import build
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow
from brief.vintage import period_label


@pytest.fixture(autouse=True)
def _no_outbound_network(monkeypatch):
    """DSE builder tests are offline: they once made live GETs to dsebd.org (sector heat /
    breadth fallbacks). Any DNS lookup or socket connect here is refused and fails the test."""
    attempts: list[str] = []

    def _refuse(kind: str):
        def _blocked(*args, **kwargs):
            attempts.append(kind)
            raise OSError(f"outbound network blocked in tests ({kind})")
        return _blocked

    monkeypatch.setattr(socket, "getaddrinfo", _refuse("getaddrinfo"))
    monkeypatch.setattr(socket, "create_connection", _refuse("create_connection"))
    monkeypatch.setattr(socket.socket, "connect", _refuse("connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse("connect_ex"))
    yield
    assert attempts == [], f"test tried to reach the network: {attempts}"


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


def _held_or_verified_dsex(monkeypatch, quality: str):
    """SYNTHETIC dsex record in the shape EconDelta publishes for dse_market (see the shared
    contract's holiday_closure records): the Monday 20 Apr session, read on Tuesday 21 Apr."""
    from brief.builders import dse

    monkeypatch.setattr(dse, "scrape_breadth", lambda *a, **k: None)
    monkeypatch.setattr(dse, "scrape_sector_heat", lambda *a, **k: None)
    base = _snap()
    record = {"metric_id": "dsex", "value": base.data["dsex"], "as_of": "2026-04-20", "unit": "index",
              "source": "dse_market", "source_url": "https://www.dse.com.bd/api/live/market",
              "captured_at": "2026-04-20T20:56:00+00:00", "quality": quality,
              "date_basis": "observation", "evidence": "dse_market snapshot field dsex",
              "dependencies": [], "release_status": "unknown"}
    snap = EconDeltaSnapshot(updated_at=base.updated_at, sources_status=base.sources_status,
                             data=base.data, observations={"dsex": record})
    return build(BuilderContext(snapshot=snap, history=None, today=date(2026, 4, 21)))


def test_a_reading_the_producer_holds_is_stale_even_when_only_one_session_old(monkeypatch):
    """A one-session-old date alone reads fresh; only EconDelta's 'held' quality (no confirmed
    new session) can tell the card and the section badge that the reading is held over."""
    held = _held_or_verified_dsex(monkeypatch, "held")
    dsex = next(m for m in held.metrics if m.id == "dsex")
    assert (dsex.as_of, dsex.stale) == (date(2026, 4, 20), True)
    assert (held.freshness, held.freshness_reason) == ("stale", None)
    verified = _held_or_verified_dsex(monkeypatch, "verified")
    dsex = next(m for m in verified.metrics if m.id == "dsex")
    assert (dsex.as_of, dsex.stale) == (date(2026, 4, 20), False)
    assert verified.freshness != "stale"


# ── G2b: the fallback reason must not claim a non-trading day on a trading day ──
_NON_TRADING_REASON = "Non-trading day — last trading session"
_MISSING_READING_REASON = "Latest DSE reading not available — last session shown"
_DSE_SNAPSHOT_KEYS = ("dsex", "dsex_change_pct", "ds30", "dses", "turnover_crore",
                      "advancing", "declining")


def _dse_with_readings_missing(monkeypatch, today: date, missing: tuple[str, ...], *,
                               how: str, last_session: date,
                               sessions: dict[str, date] | None = None):
    """SYNTHETIC day: the snapshot lacks `missing` DSE ids (`how` = 'quarantined': the key is
    dropped from data, as the new producer does for a rejected field; 'unavailable': the key is
    present with no value) and history holds each id's reading from `last_session` (or from
    `sessions[id]` for the ids listed there)."""
    from brief.builders import dse

    monkeypatch.setattr(dse, "scrape_breadth", lambda *a, **k: None)
    monkeypatch.setattr(dse, "scrape_sector_heat", lambda *a, **k: None)
    base = _snap().data
    if how == "quarantined":
        data = {k: v for k, v in base.items() if k not in missing}
    else:
        data = {k: (None if k in missing else v) for k, v in base.items()}
    snap = EconDeltaSnapshot(updated_at=datetime(2026, 9, 23, 21, 0, tzinfo=timezone.utc),
                             sources_status={"dse_market": {"status": "ok"}}, data=data)

    def _get_latest(metric_id, **kwargs):
        if metric_id in _DSE_SNAPSHOT_KEYS:
            return HistoryRow(metric_id=metric_id,
                              as_of=(sessions or {}).get(metric_id, last_session),
                              value=base[metric_id], source="EconDelta")
        return None  # sector-heat lookups outside this test's scope

    history = MagicMock()
    history.get_latest.side_effect = _get_latest
    return build(BuilderContext(snapshot=snap, history=history, today=today))


@pytest.mark.parametrize("how", ["quarantined", "unavailable"])
@pytest.mark.parametrize("missing", [("dsex",), _DSE_SNAPSHOT_KEYS], ids=["one-id", "all-ids"])
def test_a_dse_reading_missing_on_a_trading_day_never_calls_it_a_non_trading_day(
        monkeypatch, how, missing):
    """Thursday 24 Sep 2026 is a trading day by the Brief's own rule. A DSE id the snapshot
    lacks falls back to its last history session: the card keeps that session's real date and
    is stale, the section is stale, and the reason says the latest reading is missing, never
    that the market was shut (G2 review: one quarantined id labelled the whole section)."""
    section = _dse_with_readings_missing(monkeypatch, date(2026, 9, 24), missing, how=how,
                                         last_session=date(2026, 9, 23))
    by_id = {m.id: m for m in section.metrics}
    assert (by_id["dsex"].value, by_id["dsex"].as_of, by_id["dsex"].stale) == (
        5232.49, date(2026, 9, 23), True)
    assert (section.freshness, section.freshness_reason) == ("stale", _MISSING_READING_REASON)
    assert "Non-trading" not in section.freshness_reason


@pytest.mark.parametrize("today", [date(2026, 9, 25), date(2026, 9, 26)], ids=["friday", "saturday"])
def test_a_weekend_fallback_keeps_the_non_trading_day_reason(monkeypatch, today):
    """On Friday and Saturday (no BD session) the empty snapshot falls back to Thursday's
    session, and the section still says so: non-trading day, last trading session."""
    section = _dse_with_readings_missing(monkeypatch, today, _DSE_SNAPSHOT_KEYS, how="unavailable",
                                         last_session=date(2026, 9, 24))
    dsex = next(m for m in section.metrics if m.id == "dsex")
    assert (dsex.as_of, dsex.stale) == (date(2026, 9, 24), True)
    assert (section.freshness, section.freshness_reason) == ("stale", _NON_TRADING_REASON)


@pytest.mark.parametrize(("today", "missing"), [
    (date(2026, 9, 25), ("dsex",)),
    (date(2026, 9, 26), _DSE_SNAPSHOT_KEYS),
], ids=["friday-one-id", "saturday-all-ids"])
def test_a_weekend_fallback_older_than_the_last_session_is_not_called_the_last_trading_session(
        monkeypatch, today, missing):
    """Friday 25 / Saturday 26 Sep 2026: the last BD session was Thursday 24 Sep, but history's
    newest row is Wednesday 23 Sep (Thursday's reading never arrived). The card keeps its real
    Wednesday date and is stale, and the section must not claim it shows the last trading
    session; it says the latest reading is missing (G2b review round 0, SYNTHETIC data)."""
    section = _dse_with_readings_missing(monkeypatch, today, missing, how="quarantined",
                                         last_session=date(2026, 9, 23))
    dsex = next(m for m in section.metrics if m.id == "dsex")
    assert (dsex.as_of, dsex.stale) == (date(2026, 9, 23), True)
    assert (section.freshness, section.freshness_reason) == ("stale", _MISSING_READING_REASON)


def test_a_weekend_fallback_is_the_last_trading_session_only_if_every_fallback_card_is(
        monkeypatch):
    """Friday 25 Sep 2026, whole snapshot empty: six ids fall back to Thursday 24 Sep (the last
    session) but DS30's newest history row is Wednesday 23 Sep. One card older than the last
    session is enough to make 'last trading session' false for the section (SYNTHETIC data)."""
    section = _dse_with_readings_missing(monkeypatch, date(2026, 9, 25), _DSE_SNAPSHOT_KEYS,
                                         how="unavailable", last_session=date(2026, 9, 24),
                                         sessions={"ds30": date(2026, 9, 23)})
    ds30 = next(m for m in section.metrics if m.id == "dse_ds30")
    assert (ds30.as_of, ds30.stale) == (date(2026, 9, 23), True)
    assert (section.freshness, section.freshness_reason) == ("stale", _MISSING_READING_REASON)
