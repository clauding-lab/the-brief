from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from brief.builders import BuilderContext
from brief.builders.bb import build
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow

# ── Verified-live ground truth (probed 2026-07-09, Supabase metric_history) ──
# These are the values the builder MUST resolve to from live data.
_LIVE_REPO = 10.0
_LIVE_SDF = 7.5     # BB cut twice; 8.5 is the RETIRED hardcode — must never resurface
_LIVE_SLF = 11.5
_LIVE_RESERVES = 34.5478

TODAY = date(2026, 7, 9)


def _snap(**overrides):
    data = {
        "gross_reserves_usd_bn": _LIVE_RESERVES,
        "reserves_date": "2026-07-09",
    }
    data.update(overrides)
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
        sources_status={"bb_forex": {"status": "ok", "age_hours": 0.1}},
        data=data,
    )


class _FakeHistory:
    """Controllable metric_history double keyed by metric_id.

    `latest` maps metric_id -> HistoryRow | None (what get_latest returns).
    Unlike a bare MagicMock this distinguishes the live reserves id from the
    dead one, so tests can prove the builder reads the right id. It also has
    NO get_history_window method on purpose: if build() ever calls it, tests
    crash loudly (that call would break the pipeline's single-batched-call
    invariant — see test_build_issues_no_get_history_window_call).
    """

    def __init__(self, latest: dict | None = None):
        self._latest = latest or {}
        self.upsert_many = MagicMock()

    def get_latest(self, metric_id, *, table="metric_history"):
        return self._latest.get(metric_id)


def _live_rate_rows(as_of=date(2026, 7, 9)):
    return {
        "policy_rate_repo": HistoryRow("policy_rate_repo", as_of, _LIVE_REPO, "BB"),
        "policy_rate_sdf": HistoryRow("policy_rate_sdf", as_of, _LIVE_SDF, "BB"),
        "policy_rate_slf": HistoryRow("policy_rate_slf", as_of, _LIVE_SLF, "BB"),
    }


def _live_money_market_rows(as_of=date(2026, 7, 9)):
    """Fresh money-market rows (probed 2026-07-10, Supabase metric_history)."""
    return {
        "call_money_rate": HistoryRow("call_money_rate", as_of, 9.56, "BB"),
        "call_money_rate_7d": HistoryRow("call_money_rate_7d", as_of, 9.41, "BB"),
        "call_money_rate_14d": HistoryRow("call_money_rate_14d", as_of, 11.19, "BB"),
    }


def _m(section, mid):
    return next(m for m in section.metrics if m.id == mid)


# ── Corridor: live reads ─────────────────────────────────────────────────────

def test_corridor_reads_live_rates_not_hardcoded():
    """Repo/SDF/SLF come from metric_history; SDF resolves to the live 7.5, not
    the retired 8.5 hardcode. FAILS if anyone re-hardcodes SDF=8.5 or stops
    reading policy_rate_sdf — the mock feeds 7.5, so a hardcode returns 8.5."""
    hist = _FakeHistory(latest=_live_rate_rows())
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    s = build(ctx)

    assert _m(s, "bb_policy_rate").value == 10.0
    assert _m(s, "bb_sdf").value == 7.5            # regression guard: NOT 8.5
    assert _m(s, "bb_slf").value == 11.5
    for mid in ("bb_policy_rate", "bb_sdf", "bb_slf"):
        m = _m(s, mid)
        assert m.stale is False                    # sourced live → not stale
        assert m.cadence == "event"
        assert m.source == "BB"
    # the retired 8.5 value must not appear anywhere in the corridor
    assert all(m.value != 8.5 for m in s.metrics)
    # event-cadence rates keep the section fresh
    assert s.freshness == "fresh"


# ── Corridor: honest degradation ─────────────────────────────────────────────

def test_single_missing_rate_falls_back_and_marks_stale():
    """A per-rate metric_history gap must not blank the corridor: the missing
    rate falls back to the last-known constant AND is marked stale=True, while
    the rates that DID resolve stay live and non-stale."""
    rows = _live_rate_rows()
    rows["policy_rate_sdf"] = None   # SDF row missing from history
    hist = _FakeHistory(latest=rows)
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    s = build(ctx)

    sdf = _m(s, "bb_sdf")
    assert sdf.value == 7.5            # fallback constant == live-correct value
    assert sdf.stale is True           # honest degradation flag
    assert _m(s, "bb_policy_rate").stale is False   # others resolved live
    assert _m(s, "bb_slf").stale is False


def test_corridor_degrades_when_history_unavailable():
    """metric_history outage (history=None) must never blank the corridor: all
    three rates fall back to last-known constants and are marked stale=True.
    The SDF fallback constant is the live-correct 7.5 — never the retired 8.5."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=TODAY)
    s = build(ctx)

    assert _m(s, "bb_policy_rate").value == 9.50
    assert _m(s, "bb_sdf").value == 7.5     # fallback must NOT be 8.5
    assert _m(s, "bb_slf").value == 11.00
    for mid in ("bb_policy_rate", "bb_sdf", "bb_slf"):
        assert _m(s, mid).stale is True
        assert _m(s, mid).cadence == "event"
    assert all(m.value != 8.5 for m in s.metrics)


def test_fallback_constants_match_the_latest_mpc_decision():
    """Regression guard for 2026-08-03: BB cut the repo 10.00 -> 9.50 and the
    SLF 11.50 -> 11.00 on 2026-07-30, and these constants still held the PRE-CUT
    corridor four days later. A history outage would have printed a corridor
    that no longer existed. Bump these WITH the decision, not after it."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=TODAY)
    s = build(ctx)

    # The retired pre-cut corridor must not resurface, the way 8.5 SDF once did.
    assert _m(s, "bb_policy_rate").value != 10.0
    assert _m(s, "bb_slf").value != 11.5
    # A fallback dates from the decision that set it, never from today.
    assert _m(s, "bb_policy_rate").as_of == date(2026, 7, 30)


def test_corridor_fallback_forces_the_section_stale():
    """The fallback is honest ONLY if the badge says so. Before this, stale=True
    was decorative: metric_freshness returned "fresh" for every event metric, so
    a full metric_history outage rendered §02 as fresh while printing three
    last-known constants."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=TODAY)
    s = build(ctx)

    assert s.freshness == "stale"


def test_corridor_goes_stale_when_econdelta_stops_restamping():
    """EconDelta re-upserts the corridor daily. If that writer dies the rows
    stop moving, and The Brief has no evidence the printed rate is still in
    force — §02 must stop claiming it is fresh. This is the hole the 2026-08-03
    incident sat in: event cadence returned "fresh" unconditionally."""
    stale_rows = _live_rate_rows(as_of=date(2026, 5, 1))   # 69 days before TODAY
    hist = _FakeHistory(latest={**stale_rows, **_live_money_market_rows()})
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    s = build(ctx)

    # values still render (never blanked) — only the freshness claim changes
    assert _m(s, "bb_policy_rate").value == _LIVE_REPO
    assert _m(s, "bb_policy_rate").stale is False   # it IS a live read, just old
    assert s.freshness == "stale"


# ── Reserves ─────────────────────────────────────────────────────────────────

def test_reserves_uses_snapshot_value_and_never_fakes_delta():
    """Reserves reads the live snapshot value and emits NO WoW delta — the
    daily-restamped id would only yield a fabricated ~0 delta, so the builder
    drops it rather than lie. FAILS if a fake/zero delta is reintroduced."""
    hist = _FakeHistory(latest=_live_rate_rows())
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    s = build(ctx)

    res = _m(s, "bb_gross_reserves")
    assert res.value == _LIVE_RESERVES
    assert res.stale is False
    assert res.delta is None                 # no fabricated delta
    assert res.cadence == "weekly"


def test_reserves_fallback_reads_live_id_not_dead_id():
    """When the snapshot lacks reserves, the builder backfills from the LIVE
    metric_history id `gross_reserves_usd_bn` and marks it stale — it must NOT
    read the dead `bb_gross_reserves` id (no writer since 2026-03-01). The dead
    id is wired to return a distinct value; if the builder read it, the metric
    value would be that value instead of the live 34.20."""
    hist = _FakeHistory(latest={
        **_live_rate_rows(),
        "gross_reserves_usd_bn": HistoryRow(
            "gross_reserves_usd_bn", date(2026, 7, 8), 34.20, "BB"
        ),
        "bb_gross_reserves": HistoryRow(
            "bb_gross_reserves", date(2026, 3, 1), 34.1166, "BB"
        ),
    })
    ctx = BuilderContext(snapshot=_snap(gross_reserves_usd_bn=None), history=hist, today=TODAY)
    s = build(ctx)

    res = _m(s, "bb_gross_reserves")
    assert res.value == 34.20            # live id, NOT the dead-id 34.1166
    assert res.value != 34.1166          # regression guard: dead id must not be read
    assert res.stale is True             # sourced from history → stale
    assert res.as_of == date(2026, 7, 8)
    assert res.delta is None             # stale fallback → no delta


def test_reserves_missing_everywhere_is_unavailable_not_crash():
    """No snapshot reserves and no history → reserves value is None and the
    section degrades gracefully (never crashes, never fabricates)."""
    ctx = BuilderContext(snapshot=_snap(gross_reserves_usd_bn=None), history=None, today=TODAY)
    s = build(ctx)
    res = next((m for m in s.metrics if m.id == "bb_gross_reserves"), None)
    assert res is not None
    assert res.value is None
    assert res.delta is None
    assert s.freshness in ("unavailable", "warning", "stale")


def test_reserves_malformed_date_falls_back_to_today():
    ctx = BuilderContext(snapshot=_snap(reserves_date="2026-07-XX"), history=None, today=TODAY)
    s = build(ctx)
    res = _m(s, "bb_gross_reserves")
    assert res.as_of == TODAY


# ── Structural invariants ────────────────────────────────────────────────────

def test_section_emits_expected_metric_ids():
    """The four canonical BB metric ids must stay stable — cadence.py's
    fx_reserves_rule keys on `bb_gross_reserves`, and the corridor ids feed the
    SPA and risk rules. Renaming any of them breaks systemic-risk wiring."""
    hist = _FakeHistory(latest=_live_rate_rows())
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    s = build(ctx)
    ids = {m.id for m in s.metrics}
    assert {"bb_policy_rate", "bb_sdf", "bb_slf", "bb_gross_reserves"}.issubset(ids)
    assert s.id == "bb"


def test_bb_does_not_write_to_history():
    """Historical persistence moved upstream to EconDelta — the bb builder must
    never call upsert_many (see econdelta/docs/data-contract.md)."""
    hist = _FakeHistory(latest=_live_rate_rows())
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    build(ctx)
    hist.upsert_many.assert_not_called()


def test_build_issues_no_get_history_window_call():
    """The builder must NOT call get_history_window during build. The pipeline
    issues exactly ONE batched window call in _enrich_metric_history; a second
    call here breaks test_gather_enriches_metric_history_values' assert_called_once.
    This invariant is WHY the reserves WoW delta is dropped, not computed."""
    from brief.history import MetricHistoryClient
    hist = MagicMock(spec=MetricHistoryClient)
    hist.get_latest.return_value = None
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    build(ctx)
    hist.get_history_window.assert_not_called()


def test_overnight_call_money_tile_present_and_live():
    """§02 surfaces the overnight call-money rate, read live from metric_history,
    in the builder's own metric list. FAILS if bb_call_money is dropped or
    hardcoded.

    NOTE (sdf-diagnosis-2026-08-05.md): this only asserts the BUILDER's list.
    It does NOT prove bb_call_money renders as a tile — the editor_v6 prompt
    reorders and drops metrics before anything reaches storage (AGENTS.md
    landmine 25), so builder-list index carries no downstream meaning. This
    test used to assert `ids.index("bb_call_money") < 5` as a stand-in for
    "tile-eligible"; that assertion encoded a false premise and was removed.
    The real post-editor survival guarantee (for the protected corridor
    metrics) is tested in tests/test_pipeline_v6_metric_reconciliation.py.
    """
    hist = _FakeHistory(latest={**_live_rate_rows(), **_live_money_market_rows()})
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    s = build(ctx)

    cm = _m(s, "bb_call_money")
    assert cm.value == 9.56
    assert cm.label == "Overnight Call Money"
    assert cm.unit == "%"
    assert cm.source == "BB"
    assert cm.cadence == "daily"
    assert cm.stale is False
    ids = [m.id for m in s.metrics]
    # grouped with the corridor, ahead of reserves — builder's own ordering,
    # not a claim about what the editor does with it downstream.
    assert ids.index("bb_call_money") < ids.index("bb_gross_reserves")


def test_call_money_omitted_when_missing_no_fallback():
    """Missing call_money_rate → NO bb_call_money metric (no fake fallback for a
    fast daily rate); §02 keeps exactly its 4 canonical metrics; no crash."""
    hist = _FakeHistory(latest=_live_rate_rows())  # no call-money rows
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    s = build(ctx)

    assert all(m.id != "bb_call_money" for m in s.metrics)
    assert {m.id for m in s.metrics} == {
        "bb_policy_rate", "bb_sdf", "bb_slf", "bb_gross_reserves",
    }


def test_tenor_points_present_but_never_tiles():
    """7d/14d call-money tenor feed the editor as prose context, appended after
    the corridor/overnight/reserves group. The full builder order is asserted
    to document the atomic tenor feed.

    NOTE (sdf-diagnosis-2026-08-05.md): "never tiles" in this test's name
    describes the BUILDER's stated intent (bb.py:187-201's own comment), not
    a guarantee this test can prove. The editor_v6 prompt reorders every
    section's metrics before storage, so a builder-list position >= 5 does
    NOT mean a metric never becomes a tile (AGENTS.md landmine 25 corrected
    this) — in production these two tenor points have occupied tile slots and
    evicted SDF/Reserves on every recent issue. This test previously asserted
    `ids.index(...) >= 5` as a stand-in for "safe from tiling"; that assertion
    encoded the same false premise and was removed. What protects the
    corridor now is `_reconcile_metrics` in brief/pipeline_v6.py, tested in
    tests/test_pipeline_v6_metric_reconciliation.py — not builder order.
    """
    hist = _FakeHistory(latest={**_live_rate_rows(), **_live_money_market_rows()})
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    s = build(ctx)

    assert _m(s, "bb_call_money_7d").value == 9.41
    assert _m(s, "bb_call_money_7d").label == "Call Money · 7-day"
    assert _m(s, "bb_call_money_14d").value == 11.19
    ids = [m.id for m in s.metrics]
    assert ids == [
        "bb_policy_rate", "bb_sdf", "bb_slf", "bb_call_money",
        "bb_gross_reserves", "bb_call_money_7d", "bb_call_money_14d",
    ]


def test_tenor_omitted_when_overnight_missing():
    """The money-market feed is atomic: no overnight row → NO tenor metrics
    either, even when 7d/14d rows exist. Guarantees a tenor point can never land
    in the 5-tile slice."""
    rows = {**_live_rate_rows(), **_live_money_market_rows()}
    del rows["call_money_rate"]           # overnight gone; 7d/14d still present
    hist = _FakeHistory(latest=rows)
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    s = build(ctx)

    ids = {m.id for m in s.metrics}
    assert "bb_call_money" not in ids
    assert "bb_call_money_7d" not in ids
    assert "bb_call_money_14d" not in ids
    assert ids == {"bb_policy_rate", "bb_sdf", "bb_slf", "bb_gross_reserves"}


def test_stale_tenor_point_omitted_only_fresh_kept():
    """A present-but-stale tenor is omitted so an invisible context metric can
    never drag §02's visible freshness badge (and stale term-structure never
    reaches the editor). The overnight tile and a fresh tenor stay; the section
    badge stays fresh. TODAY is 2026-07-09; as_of 2026-07-01 is >2 trading days
    stale under the daily rule."""
    rows = {
        **_live_rate_rows(),
        "call_money_rate": HistoryRow("call_money_rate", TODAY, 9.56, "BB"),
        "call_money_rate_7d": HistoryRow("call_money_rate_7d", TODAY, 9.41, "BB"),
        "call_money_rate_14d": HistoryRow(
            "call_money_rate_14d", date(2026, 7, 1), 11.19, "BB"
        ),  # stale
    }
    ctx = BuilderContext(snapshot=_snap(), history=_FakeHistory(latest=rows), today=TODAY)
    s = build(ctx)

    ids = {m.id for m in s.metrics}
    assert "bb_call_money" in ids           # overnight tile kept
    assert "bb_call_money_7d" in ids        # fresh tenor kept
    assert "bb_call_money_14d" not in ids   # stale tenor omitted
    assert s.freshness == "fresh"           # no invisible metric drags the badge


def test_call_money_omitted_when_value_non_numeric():
    """Omit-on-missing also fires on a present-but-non-numeric row (EconDelta may
    write a null): no bb_call_money metric, no fabrication, no crash. Covers the
    isinstance branch the missing-row test short-circuits past."""
    rows = {
        **_live_rate_rows(),
        "call_money_rate": HistoryRow("call_money_rate", TODAY, None, "BB"),
    }
    ctx = BuilderContext(snapshot=_snap(), history=_FakeHistory(latest=rows), today=TODAY)
    s = build(ctx)
    assert all(m.id != "bb_call_money" for m in s.metrics)


def test_warning_level_tenor_also_omitted():
    """The tenor guard is `== "fresh"`, so a WARNING-level tenor (aging but not
    yet stale) is ALSO omitted — locking the intent against a future loosening to
    `!= "stale"`. TODAY is Thu 2026-07-09; as_of Tue 2026-07-07 is 2 BD trading
    days back → `metric_freshness` returns "warning" (verified in brief.cadence).
    A `!= "stale"` guard would KEEP this tenor and fail this test."""
    rows = {
        **_live_rate_rows(),
        "call_money_rate": HistoryRow("call_money_rate", TODAY, 9.56, "BB"),
        "call_money_rate_7d": HistoryRow("call_money_rate_7d", TODAY, 9.41, "BB"),
        "call_money_rate_14d": HistoryRow(
            "call_money_rate_14d", date(2026, 7, 7), 11.19, "BB"
        ),  # 2 trading days back → warning
    }
    ctx = BuilderContext(snapshot=_snap(), history=_FakeHistory(latest=rows), today=TODAY)
    s = build(ctx)

    ids = {m.id for m in s.metrics}
    assert "bb_call_money" in ids           # overnight tile kept
    assert "bb_call_money_7d" in ids        # fresh tenor kept
    assert "bb_call_money_14d" not in ids   # warning-level tenor omitted (guard is == "fresh")
