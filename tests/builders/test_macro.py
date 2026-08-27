"""Tests for the macro builder.

v1.4.0 built all 8 metrics from `metric_history_monthly`. v1.6.3 repoints the
five that have a live source — three directly, two derived — and leaves the
three that have none reading the archive.

The tests that matter most here are the honesty ones: that a derived figure is
dated by its STALEST input, and that the section does not start calling itself
fresh just because most of its metrics now are. Those are the properties that
were quietly false when the section printed 155-day-old numbers.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from brief.builders import BuilderContext
from brief.builders.macro import _MACRO_METRICS, build
from brief.cadence import section_freshness
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow


def _snap() -> EconDeltaSnapshot:
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 5, 27, tzinfo=timezone.utc),
        sources_status={},
        data={},
    )


def _row(metric_id: str, value: float, as_of: date) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=as_of, value=value, source="test")


class _FakeHistory:
    """Minimal MetricHistoryClient stub. Records the tables it was asked for."""

    def __init__(self, latest_by_id: dict[str, HistoryRow], *,
                 default_table: str = "metric_history",
                 at_or_before_by_id: dict[str, HistoryRow] | None = None) -> None:
        self._latest = latest_by_id
        self.default_table = default_table
        self.tables_seen: list[str] = []
        self._at_or_before = at_or_before_by_id or {}
        self.at_or_before_calls: list[tuple[str, date]] = []
        self.window_calls = 0

    def get_latest(self, metric_id: str, *, table: str | None = None) -> HistoryRow | None:
        self.tables_seen.append(table or self.default_table)
        return self._latest.get(metric_id)

    def get_history_window(self, metric_ids: list[str], **kwargs) -> dict:
        self.window_calls += 1
        return {mid: [] for mid in metric_ids}

    def get_at_or_before(self, metric_id: str, as_of: date, *, table: str | None = None) -> HistoryRow | None:
        self.at_or_before_calls.append((metric_id, as_of))
        return self._at_or_before.get(metric_id)


# Live values good enough to exercise every path, dated 2026-08-03 unless the
# real series is genuinely older (the inflation family publishes at month end).
JUN30 = date(2026, 6, 30)
JUL31 = date(2026, 7, 31)
AUG3 = date(2026, 8, 3)

# `policy_rate_repo`'s LATEST read is post the 30-Jul cut (9.50); the rate IN
# FORCE on the inflation reading's date (Jun 30) was still the pre-cut 10.00 —
# this pair is what makes the period-consistency fix testable at all.
LIVE = {
    "food_inflation": _row("food_inflation", 8.6, JUN30),
    "non_food_inflation": _row("non_food_inflation", 9.61, JUN30),
    "private_sector_credit_yoy_pct": _row("private_sector_credit_yoy_pct", 4.98, AUG3),
    "policy_rate_repo": _row("policy_rate_repo", 9.5, AUG3),
    "general_inflation": _row("general_inflation", 9.16, JUN30),
    "point_to_point_inflation": _row("point_to_point_inflation", 9.16, JUN30),
    "gross_reserves_usd_bn": _row("gross_reserves_usd_bn", 37.578, JUN30),
}

LIVE_AT_OR_BEFORE = {
    "policy_rate_repo": _row("policy_rate_repo", 10.0, JUN30),
}

# Official imports archive (mn USD), same month as reserves (JUN30) so import
# cover computes: 5800.0mn -> 5.8bn, `official_monthly_bn` normalizes as_of to
# JUN30's month-end (JUN30 itself, already month-end).
IMPORTS_ARCHIVE = {
    "imports_usd_mn_monthly": _row("imports_usd_mn_monthly", 5800.0, JUN30),
}


def _ctx(*, live: dict | None = None, archive: dict | None = None,
         at_or_before: dict | None = None, today: date = AUG3) -> BuilderContext:
    return BuilderContext(
        snapshot=_snap(),
        history=(
            _FakeHistory(live, at_or_before_by_id=at_or_before) if live is not None else None
        ),
        today=today,
        history_monthly=(
            _FakeHistory(archive, default_table="metric_history_monthly")
            if archive is not None else None
        ),
    )


# ── section shape (unchanged by the repoint) ─────────────────────────────────

def test_macro_section_identity() -> None:
    s = build(_ctx())
    assert s.id == "macro"
    assert s.title == "Macro & Inflation"


def test_macro_has_eight_metrics() -> None:
    assert len(build(_ctx()).metrics) == 8


@pytest.mark.parametrize("metric_id", [spec.id for spec in _MACRO_METRICS])
def test_macro_metric_ids_present(metric_id: str) -> None:
    """The PUBLISHED ids must survive the repoint — the SPA and the metrics
    table key on them, so moving where a value is read from must not rename it."""
    assert metric_id in {m.id for m in build(_ctx()).metrics}


def test_macro_metrics_in_documented_order() -> None:
    assert [m.id for m in build(_ctx()).metrics] == [spec.id for spec in _MACRO_METRICS]


def test_macro_all_metrics_are_monthly_cadence() -> None:
    for m in build(_ctx()).metrics:
        assert m.cadence == "monthly", f"{m.id} should have cadence='monthly'"


# ── the repoint: live values now come from the daily table ───────────────────

def test_live_metrics_read_from_metric_history() -> None:
    """The three with a direct live equivalent carry that value, not the archive's."""
    s = build(_ctx(live=LIVE))
    by_id = {m.id: m for m in s.metrics}

    assert by_id["cpi_p2p_food_monthly"].value == 8.6
    assert by_id["cpi_p2p_food_monthly"].as_of == JUN30
    assert by_id["cpi_p2p_nonfood_monthly"].value == 9.61
    assert by_id["private_credit_growth_yoy_monthly"].value == 4.98
    assert by_id["private_credit_growth_yoy_monthly"].as_of == AUG3


def test_live_metrics_are_read_from_the_daily_table() -> None:
    """Guards the actual bug: reading the writer-less monthly archive."""
    client = _FakeHistory(LIVE)
    ctx = BuilderContext(snapshot=_snap(), history=client, today=AUG3)
    build(ctx)
    assert client.tables_seen
    assert set(client.tables_seen) == {"metric_history"}


def test_archive_metrics_still_read_the_monthly_table() -> None:
    """AGENTS.md landmine 1 — the three with no live source keep their table."""
    archive = {
        "reer_monthly": _row("reer_monthly", 102.78, date(2026, 3, 1)),
        "cpi_12m_avg_monthly": _row("cpi_12m_avg_monthly", 8.6, date(2026, 3, 1)),
        "m2_growth_yoy_monthly": _row("m2_growth_yoy_monthly", 10.52, date(2026, 2, 1)),
    }
    client = _FakeHistory(archive, default_table="metric_history_monthly")
    ctx = BuilderContext(snapshot=_snap(), history=_FakeHistory(LIVE), today=AUG3,
                         history_monthly=client)
    s = build(ctx)
    by_id = {m.id: m for m in s.metrics}

    assert set(client.tables_seen) == {"metric_history_monthly"}
    assert by_id["reer_monthly"].value == 102.78
    assert by_id["m2_growth_yoy_monthly"].value == 10.52


# ── the derived pair (P0 honesty fix, 2026-08-22 audit #204) ────────────────
# All four take the at_or_before branch, which since the 2026-08-26 restamp-
# lag guard is only reached when the MPC decision is LATER than the inflation
# reading — so they pin the decision date too (review fix 5). Unpinned, an
# MPC move earlier than 30 Jun would silently reroute them through the guard.

def test_real_policy_rate_pairs_the_repo_rate_in_force_on_the_inflation_date(mpc) -> None:
    """The bug this fixes: pairing the LATEST repo rate (9.50, post the 30-Jul
    cut) with June's inflation print (9.16) gives 0.34% — a rate that never
    coexisted with that inflation reading. The June-consistent value is the
    rate in force ON 30 Jun (10.00, pre-cut) minus 9.16 = 0.84%."""
    mpc(JUL30)
    assert _rpr(live=LIVE, at_or_before=LIVE_AT_OR_BEFORE).value == pytest.approx(0.84)


def test_real_policy_rate_as_of_is_the_inflation_date(mpc) -> None:
    mpc(JUL30)
    assert _rpr(live=LIVE, at_or_before=LIVE_AT_OR_BEFORE).as_of == JUN30


def test_real_policy_rate_looks_up_the_repo_rate_at_the_inflation_date(mpc) -> None:
    """Regression guard for the mechanism, not just the number: the repo
    lookup must be anchored on the inflation reading's date, not "today"."""
    mpc(JUL30)
    history = _FakeHistory(LIVE, at_or_before_by_id=LIVE_AT_OR_BEFORE)
    ctx = BuilderContext(snapshot=_snap(), history=history, today=AUG3)
    build(ctx)
    assert ("policy_rate_repo", JUN30) in history.at_or_before_calls


def test_real_policy_rate_is_none_when_no_repo_rate_existed_that_early(mpc) -> None:
    """The corridor's `at_or_before` read finding nothing (e.g. history starts
    after the inflation date) is a missing input, not an invented rate."""
    mpc(JUL30)
    assert _rpr(live=LIVE, at_or_before={}).value is None


# ── the restamp-lag guard (2026-08-26) ─────────────────────────────────────
# Production shipped 1.68% ("BB's real policy rate after the July cut") on
# 2026-08-26. That number is 10.00 − 8.32, and 10.00 is the PRE-cut rate: the
# 30 Jul MPC cut (10.00 → 9.50) was not restamped onto `policy_rate_repo`
# until 03 Aug (landmine 24 — `as_of` is the restamp date, never the decision
# date), so the row `at_or_before` 31 Jul still read 10.00. The rate actually
# in force on 31 Jul was 9.50, and the honest figure is 1.18%.
#
# REVIEW FIX 5 — every test below PINS `bb._LAST_MPC_DECISION` via the `mpc`
# fixture instead of leaning on whatever today's constant happens to be. The
# guard's contract is an ORDERING (did the corridor move on or before this
# CPI print?), not a fact about August 2026. Left unpinned, the next MPC
# bump silently flips these tests to the at_or_before branch, and the
# tempting "fix" is to edit 1.18 → 1.68 — i.e. to re-bless the exact bug
# this module exists to prevent.

JUL30 = date(2026, 7, 30)  # the real 2026 MPC cut date; pinned, not assumed


@pytest.fixture
def mpc(monkeypatch):
    """Pin the MPC decision date the guard keys on.

    `macro._real_policy_rate` imports `_LAST_MPC_DECISION` from `bb` INSIDE
    the function, so it re-reads the module attribute on every call and this
    patch takes effect without reloading anything.
    """
    def _set(decision: date) -> None:
        monkeypatch.setattr("brief.builders.bb._LAST_MPC_DECISION", decision)
    return _set


RESTAMP_LAG_LIVE = {
    **LIVE,
    # July's p2p CPI print, the reading the metric is dated by.
    "point_to_point_inflation": _row("point_to_point_inflation", 8.32, JUL31),
    # The corridor's LATEST restamp — post-cut, and the rate really in force.
    "policy_rate_repo": _row("policy_rate_repo", 9.5, AUG3),
}

# What `get_at_or_before(policy_rate_repo, 31 Jul)` really returns in
# production: the 31 Jul restamp, still carrying the PRE-cut 10.00.
RESTAMP_LAG_AT_OR_BEFORE = {
    "policy_rate_repo": _row("policy_rate_repo", 10.0, JUL31),
}


def _rpr(**kwargs):
    return next(m for m in build(_ctx(**kwargs)).metrics
                if m.id == "real_policy_rate_monthly")


def test_real_policy_rate_uses_the_rate_in_force_not_the_restamp_lag(mpc) -> None:
    """A cut on or before the inflation reading's own date means the
    `at_or_before` row may still carry the pre-decision rate — the corridor
    moved but EconDelta had not restamped it yet. Resolve the repo leg from
    the LATEST row instead: 9.50 − 8.32 = 1.18, not 10.00 − 8.32 = 1.68."""
    mpc(JUL30)
    m = _rpr(live=RESTAMP_LAG_LIVE, at_or_before=RESTAMP_LAG_AT_OR_BEFORE)
    assert m.value == pytest.approx(1.18)
    assert "9.50" in (m.source or "")
    assert "10.00" not in (m.source or "")


def test_real_policy_rate_unchanged_when_no_decision_since_the_inflation_date(mpc) -> None:
    """The guard must be narrow. June's print (30 Jun) is EARLIER than the
    30 Jul decision, so no cut had happened by then and the `at_or_before`
    row (10.00) is genuinely the rate in force: 10.00 − 9.16 = 0.84."""
    mpc(JUL30)
    m = _rpr(live=LIVE, at_or_before=LIVE_AT_OR_BEFORE)
    assert m.value == pytest.approx(0.84)
    assert "10.00" in (m.source or "")


def test_real_policy_rate_guard_still_dates_the_metric_by_the_inflation_reading(mpc) -> None:
    """Landmine 27(b): the repo leg moving to the latest restamp must not drag
    the metric's `as_of` onto that restamp date. It stays July's CPI date."""
    mpc(JUL30)
    assert _rpr(live=RESTAMP_LAG_LIVE, at_or_before=RESTAMP_LAG_AT_OR_BEFORE).as_of == JUL31


def test_real_policy_rate_is_none_when_the_guard_finds_no_latest_repo_row(mpc) -> None:
    """Landmine 27(b): half a derivation is not a number. The guard path has
    the same missing-input discipline as the `at_or_before` path."""
    mpc(JUL30)
    no_repo = {k: v for k, v in RESTAMP_LAG_LIVE.items() if k != "policy_rate_repo"}
    m = _rpr(live=no_repo, at_or_before=RESTAMP_LAG_AT_OR_BEFORE)
    assert m.value is None
    assert m.source == "BB+BBS"


def test_real_policy_rate_source_names_both_legs(mpc) -> None:
    """`MetricV6` has no `source` field, so this note only reaches the reader
    via `pipeline_v6._stamp_real_policy_rate_sub`, which finds it by the
    marker substring. The builder's job is to record BOTH legs — the repo
    rate it actually used and the CPI print it subtracted — plus the
    inflation month, using Master.md's minus GLYPH (−, U+2212).

    REVIEW FIX 4: on the GUARD branch the repo leg is dated by the MPC
    DECISION ("30 Jul cut"), never by `repo.as_of` — that is a restamp date,
    and landmine 24 forbids presenting it as when the rate changed."""
    mpc(JUL30)
    m = _rpr(live=RESTAMP_LAG_LIVE, at_or_before=RESTAMP_LAG_AT_OR_BEFORE)
    assert m.source == "BB+BBS (9.50% repo (30 Jul cut) − 8.32% Jul p2p CPI)"
    assert "-" not in m.source  # the ASCII hyphen must not sneak in
    assert "3 Aug" not in m.source  # never the restamp date


def test_real_policy_rate_note_on_the_at_or_before_branch_carries_no_cut_date(mpc) -> None:
    """REVIEW FIX 4: the else branch's two legs match by construction, so the
    note stays in its plain undated form — no decision parenthetical to add,
    because no decision sits between the two vintages."""
    mpc(JUL30)
    m = _rpr(live=LIVE, at_or_before=LIVE_AT_OR_BEFORE)
    assert m.source == "BB+BBS (10.00% repo − 9.16% Jun p2p CPI)"
    assert "cut)" not in m.source


def test_real_policy_rate_guard_reads_the_latest_repo_row_not_a_second_window(mpc) -> None:
    """Landmine 23: the guard resolves the repo leg with `get_latest`, never
    a second `get_history_window` from inside a builder."""
    mpc(JUL30)
    history = _FakeHistory(RESTAMP_LAG_LIVE,
                           at_or_before_by_id=RESTAMP_LAG_AT_OR_BEFORE)
    ctx = BuilderContext(snapshot=_snap(), history=history, today=AUG3)
    build(ctx)
    assert history.window_calls == 0


# ── REVIEW FIX 3: the guard branch needs a staleness bound ──────────────────
# `get_latest` returns the freshest restamp no matter HOW far it has drifted
# from the inflation reading. Without a bound, a corridor that keeps being
# restamped while the CPI feed dies pairs a 2027 rate with a 2026 print and
# prints the difference as if it described July 2026. Same shape, same
# remedy, same constant as `_import_cover`'s 4-month gate.

def test_real_policy_rate_suppressed_when_the_latest_repo_restamp_is_months_stale(mpc) -> None:
    """Reviewer's row G: CPI stuck at 8.32 @ 31 Jul 2026 while the corridor
    restamps on to 6.00 @ 26 Aug 2027. The old code printed −2.32% dated
    31 Jul 2026 with no warning. Thirteen months apart is not a period-
    consistent pair — suppress (landmine 27(b))."""
    mpc(JUL30)
    stale = {
        **RESTAMP_LAG_LIVE,
        "policy_rate_repo": _row("policy_rate_repo", 6.0, date(2027, 8, 26)),
    }
    assert _rpr(live=stale, at_or_before=RESTAMP_LAG_AT_OR_BEFORE).value is None


def test_real_policy_rate_guard_accepts_the_live_one_month_gap(mpc) -> None:
    """The bound must not suppress production's ordinary shape: the corridor
    restamps daily (late Aug) while July's CPI print is the freshest reading.
    One month apart — well inside the gate — still yields 1.18."""
    mpc(JUL30)
    live_shape = {
        **RESTAMP_LAG_LIVE,
        "policy_rate_repo": _row("policy_rate_repo", 9.5, date(2026, 8, 26)),
    }
    assert _rpr(live=live_shape,
                at_or_before=RESTAMP_LAG_AT_OR_BEFORE).value == pytest.approx(1.18)


# ── REVIEW FIX 5: the guard's known bound, pinned deliberately ──────────────

def test_real_policy_rate_after_a_newer_decision_reverts_to_the_at_or_before_branch(mpc) -> None:
    """DOCUMENTED BEHAVIOUR, not an endorsement (reviewer's row E).

    When a NEWER MPC decision lands (28 Oct) while the CPI feed is still
    stalled on July's print, `_LAST_MPC_DECISION <= inflation.as_of` is False
    again, so the guard stands down and the at_or_before branch re-reads the
    31 Jul restamp — reprinting 10.00 − 8.32 = 1.68, the very number this
    fix removed.

    That is the honest limit of a guard keyed on a SINGLE decision date: it
    can only reason about the most recent move, so it cannot tell that the
    31 Jul row was already stale relative to an EARLIER one. Closing it needs
    a real corridor effective-date series in EconDelta, not more logic here.
    This test exists so that behaviour can never change by accident — if a
    future change alters it, this assertion fails and the change is a
    deliberate one."""
    mpc(date(2026, 10, 28))
    assert _rpr(live=RESTAMP_LAG_LIVE,
                at_or_before=RESTAMP_LAG_AT_OR_BEFORE).value == pytest.approx(1.68)


def test_at_or_before_warns_by_name_when_no_row_found(caplog, mpc) -> None:
    """M3, review round 1: no silent darkness — a missing at_or_before row
    logs a WARNING naming the metric id."""
    mpc(JUL30)
    with caplog.at_level("WARNING", logger="brief.builders.macro"):
        build(_ctx(live=LIVE, at_or_before={}))
    assert any("policy_rate_repo" in r.message for r in caplog.records)


def test_at_or_before_warns_by_name_when_the_client_raises(caplog) -> None:
    class _RaisingAtOrBefore:
        def get_latest(self, metric_id, *, table=None):
            return LIVE.get(metric_id)

        def get_at_or_before(self, metric_id, as_of, *, table=None):
            raise RuntimeError("supabase down")

        def get_history_window(self, metric_ids, **kwargs):
            return {mid: [] for mid in metric_ids}

    ctx = BuilderContext(snapshot=_snap(), history=_RaisingAtOrBefore(), today=AUG3)
    with caplog.at_level("WARNING", logger="brief.builders.macro"):
        build(ctx)
    assert any("policy_rate_repo" in r.message for r in caplog.records)


# ── M-C, review round 2: `_latest`'s swallow path feeds 5 of macro's 8
# published metrics — no silent darkness there either. ──────────────────────

def test_latest_warns_by_name_when_no_row_found(caplog) -> None:
    partial = {k: v for k, v in LIVE.items() if k != "food_inflation"}
    with caplog.at_level("WARNING", logger="brief.builders.macro"):
        build(_ctx(live=partial))
    assert any("food_inflation" in r.message for r in caplog.records)


def test_latest_warns_by_name_when_the_client_raises(caplog) -> None:
    class _RaisingGetLatest:
        def get_latest(self, metric_id, *, table=None):
            raise RuntimeError("supabase down")

        def get_at_or_before(self, metric_id, as_of, *, table=None):
            return None

        def get_history_window(self, metric_ids, **kwargs):
            return {mid: [] for mid in metric_ids}

    ctx = BuilderContext(snapshot=_snap(), history=_RaisingGetLatest(), today=AUG3)
    with caplog.at_level("WARNING", logger="brief.builders.macro"):
        build(ctx)
    assert any("food_inflation" in r.message for r in caplog.records)
    assert any("gross_reserves_usd_bn" in r.message for r in caplog.records)


def test_import_cover_is_reserves_over_one_month_of_official_imports() -> None:
    """37.578bn reserves / 5.8bn (official imports archive, mn->bn) = 6.48 months."""
    m = next(m for m in build(_ctx(live=LIVE, archive=IMPORTS_ARCHIVE)).metrics
             if m.id == "import_cover_months_monthly")
    assert m.value == pytest.approx(6.4790, rel=1e-3)


# ── H1, review round 1: the >1-month gate flipped an honest "stale" section
# into a false "warming_up" one — see _import_cover's docstring. Replaced
# with a 4-month gate, dated by the IMPORTS month, with a dual-period source. ──

def test_import_cover_computes_at_the_real_production_gap_of_four_months() -> None:
    """The exact 2026-08-22 audit #204 production shape: reserves 31 Jul
    (36.4222bn) vs the official imports archive frozen at Mar (5826.2mn ->
    5.8262bn) — 4 months apart. This USED to suppress under the old >1-month
    rule; it must now compute, dated by the (older) imports month, with both
    periods named in `source`."""
    live = dict(LIVE, **{
        "gross_reserves_usd_bn": _row("gross_reserves_usd_bn", 36.4222, date(2026, 7, 31)),
    })
    archive = {"imports_usd_mn_monthly": _row("imports_usd_mn_monthly", 5826.2, date(2026, 3, 31))}
    m = next(m for m in build(_ctx(live=live, archive=archive)).metrics
             if m.id == "import_cover_months_monthly")
    assert m.value == pytest.approx(6.25, abs=0.01)
    assert m.as_of == date(2026, 3, 31)  # dated by the IMPORTS month, not reserves
    assert "31 Jul" in m.source
    assert "Mar" in m.source


def test_import_cover_production_gap_keeps_macro_section_honestly_stale() -> None:
    """The regression the review demanded: with the three still-archived
    metrics (REER/CPI 12m avg/M2 YoY) genuinely 5+ months old, §03 must read
    "stale" — NOT "warming_up". Import cover computing (rather than
    suppressing) is what protects this: a suppressed metric would score
    "unavailable", which macro's SECTIONS_WITHOUT_LEGACY_BACKFILL membership
    promotes to the false "warming_up" badge."""
    live = dict(LIVE, **{
        "gross_reserves_usd_bn": _row("gross_reserves_usd_bn", 36.4222, date(2026, 7, 31)),
    })
    archive = {
        "reer_monthly": _row("reer_monthly", 102.78, date(2026, 3, 1)),
        "cpi_12m_avg_monthly": _row("cpi_12m_avg_monthly", 8.6, date(2026, 3, 1)),
        "m2_growth_yoy_monthly": _row("m2_growth_yoy_monthly", 10.52, date(2026, 2, 1)),
        "imports_usd_mn_monthly": _row("imports_usd_mn_monthly", 5826.2, date(2026, 3, 31)),
    }
    s = build(_ctx(live=live, archive=archive, at_or_before=LIVE_AT_OR_BEFORE))
    assert s.freshness == "stale"
    cover = next(m for m in s.metrics if m.id == "import_cover_months_monthly")
    assert cover.value == pytest.approx(6.25, abs=0.01)


def test_import_cover_suppressed_at_five_months_still_keeps_the_section_stale() -> None:
    """H-B, review round 2 — the regression the review specifically demanded:
    imports 5 months behind reserves (2026-08-31 vs 2026-03-01) is PAST the
    H1 4-month gate, so import cover is genuinely suppressed (value=None,
    "unavailable"). That must NOT flip the section to "warming_up" just
    because one metric has nothing to show — the cadence.py fix (promotion
    only when EVERY metric is unavailable) is what protects this, at any
    gap size, independent of where the H1 threshold happens to sit."""
    today = date(2026, 9, 1)
    live = dict(LIVE, **{
        "gross_reserves_usd_bn": _row("gross_reserves_usd_bn", 36.4222, date(2026, 8, 31)),
    })
    archive = {
        "reer_monthly": _row("reer_monthly", 102.78, date(2026, 3, 1)),
        "cpi_12m_avg_monthly": _row("cpi_12m_avg_monthly", 8.6, date(2026, 3, 1)),
        "m2_growth_yoy_monthly": _row("m2_growth_yoy_monthly", 10.52, date(2026, 2, 1)),
        "imports_usd_mn_monthly": _row("imports_usd_mn_monthly", 5826.2, date(2026, 3, 1)),
    }
    s = build(_ctx(live=live, archive=archive, at_or_before=LIVE_AT_OR_BEFORE, today=today))
    cover = next(m for m in s.metrics if m.id == "import_cover_months_monthly")
    assert cover.value is None  # months_apart(31 Aug, 1 Mar) = 5 > 4 -> suppressed
    assert s.freshness == "stale"
    assert s.freshness != "warming_up"


def test_import_cover_is_suppressed_when_imports_are_more_than_four_months_stale() -> None:
    """Beyond the 4-month gate, suppress rather than guess. Reserves (Jun) vs
    a Jan imports archive are 5 months apart."""
    stale_imports = {"imports_usd_mn_monthly": _row("imports_usd_mn_monthly", 5800.0, date(2026, 1, 31))}
    m = next(m for m in build(_ctx(live=LIVE, archive=stale_imports)).metrics
             if m.id == "import_cover_months_monthly")
    assert m.value is None


def test_import_cover_is_none_when_the_official_imports_archive_has_no_row() -> None:
    m = next(m for m in build(_ctx(live=LIVE, archive={})).metrics
             if m.id == "import_cover_months_monthly")
    assert m.value is None


def test_import_cover_source_defaults_to_bb_when_suppressed() -> None:
    """No dual-period override when the metric can't compute — the spec's
    plain "BB" source stays, rather than a stale/misleading note."""
    m = next(m for m in build(_ctx(live=LIVE, archive={})).metrics
             if m.id == "import_cover_months_monthly")
    assert m.source == "BB"


def test_a_derived_metric_is_dated_by_its_oldest_input(mpc) -> None:
    """The #184 failure was a March REER printed beside that day's spot rate with
    nothing recording the gap. A figure made of a fresh input and a stale one is
    as old as the stale one."""
    mpc(JUL30)
    s = build(_ctx(live=LIVE, archive=IMPORTS_ARCHIVE, at_or_before=LIVE_AT_OR_BEFORE))
    by_id = {m.id: m for m in s.metrics}

    # Real policy rate is dated by the inflation reading it pairs with (Jun 30).
    assert by_id["real_policy_rate_monthly"].as_of == JUN30
    # Import cover: reserves and the official imports archive are both Jun 30 here.
    assert by_id["import_cover_months_monthly"].as_of == JUN30


def test_derived_metric_is_none_when_an_input_is_missing(mpc) -> None:
    """Half a derivation is not a number. Better unavailable than invented."""
    mpc(JUL30)
    partial = {k: v for k, v in LIVE.items() if k != "point_to_point_inflation"}
    assert _rpr(live=partial, at_or_before=LIVE_AT_OR_BEFORE).value is None


def test_derived_metric_survives_a_zero_denominator() -> None:
    """A zero import bill is nonsense data, not a reason to lose the issue."""
    zeroed = {"imports_usd_mn_monthly": _row("imports_usd_mn_monthly", 0.0, JUN30)}
    m = next(m for m in build(_ctx(live=LIVE, archive=zeroed)).metrics
             if m.id == "import_cover_months_monthly")
    assert m.value is None


# ── honesty properties ───────────────────────────────────────────────────────

def test_section_stays_stale_while_the_unsourced_three_are_old() -> None:
    """The repoint must not let the section relabel itself fresh. Five current
    metrics beside three five-month-old ones is a stale section, and
    section_freshness being worst-of is what keeps that true."""
    archive = {
        "reer_monthly": _row("reer_monthly", 102.78, date(2026, 3, 1)),
        "cpi_12m_avg_monthly": _row("cpi_12m_avg_monthly", 8.6, date(2026, 3, 1)),
        "m2_growth_yoy_monthly": _row("m2_growth_yoy_monthly", 10.52, date(2026, 2, 1)),
        **IMPORTS_ARCHIVE,
    }
    s = build(_ctx(live=LIVE, archive=archive, at_or_before=LIVE_AT_OR_BEFORE))
    assert s.freshness == "stale"

    # ...and it is the archive three dragging it down, not the repointed five.
    live_ids = {"cpi_p2p_food_monthly", "cpi_p2p_nonfood_monthly",
                "private_credit_growth_yoy_monthly", "real_policy_rate_monthly",
                "import_cover_months_monthly"}
    repointed = [m for m in s.metrics if m.id in live_ids]
    assert section_freshness(repointed, today=AUG3, section_id="macro") == "fresh"


def test_no_history_clients_yields_all_none_and_no_facts() -> None:
    """Total history outage degrades to an empty section, never an exception."""
    s = build(_ctx(today=AUG3))
    for m in s.metrics:
        assert m.value is None, f"{m.id} should be None with no history client"
        assert m.as_of == AUG3
    assert s.history_facts == []
    # H-B, review round 2: the promotion ITSELF must still fire when EVERY
    # metric is genuinely unavailable — this test's whole point is that
    # scenario. The companion regression above (five-months-behind) proves
    # the promotion is now correctly gated OFF a partial outage.
    assert s.freshness == "warming_up"


def test_a_raising_history_client_does_not_take_the_section_down() -> None:
    """An issue must still ship if Supabase is having a bad morning."""
    class _Boom:
        def get_latest(self, *a, **k):
            raise RuntimeError("supabase down")

        def get_history_window(self, metric_ids, **k):
            return {mid: [] for mid in metric_ids}

    ctx = BuilderContext(snapshot=_snap(), history=_Boom(), today=AUG3,
                         history_monthly=_Boom())
    s = build(ctx)
    assert len(s.metrics) == 8
    assert all(m.value is None for m in s.metrics)


def test_history_facts_are_not_computed_for_live_metrics() -> None:
    """Landmine 23 (no second get_history_window from a builder) and, separately,
    the live series hold ~4 months stamped across many dates — "lowest since"
    over that would be counting restamps as observations."""
    client = _FakeHistory(LIVE)
    ctx = BuilderContext(snapshot=_snap(), history=client, today=AUG3)
    s = build(ctx)
    assert s.history_facts == []
    assert not hasattr(client, "_window_calls")


# ── CPI dual-source official resolver (issue 206, item 4) ───────────────────


def test_dual_source_cpi_cards_stay_on_daily_official_when_archive_july_is_unofficial() -> None:
    """Both p2p CPI specs now carry BOTH `live_id` and `archive_id`, but with
    a July archive point that is NOT official (arithmetic-derived for food,
    owner-pending for non-food — production's real 2026-08-24 shape), the
    resolver must still land on June's daily print. Card values must NOT
    change from before this fix."""
    archive = {
        "cpi_p2p_food_monthly": HistoryRow(
            metric_id="cpi_p2p_food_monthly", as_of=date(2026, 7, 1), value=7.16,
            source="derived_implied_weight_bb_inflation",
        ),
        "cpi_p2p_nonfood_monthly": HistoryRow(
            metric_id="cpi_p2p_nonfood_monthly", as_of=date(2026, 7, 1), value=9.28,
            source="bb_inflation_page",  # LOOKS official but is owner-pending-denylisted
        ),
    }
    ctx = BuilderContext(
        snapshot=_snap(), history=_FakeHistory(LIVE), today=AUG3,
        history_monthly=_FakeHistory(archive, default_table="metric_history_monthly"),
    )
    s = build(ctx)
    by_id = {m.id: m for m in s.metrics}
    assert by_id["cpi_p2p_food_monthly"].value == 8.6
    assert by_id["cpi_p2p_food_monthly"].as_of == JUN30
    assert by_id["cpi_p2p_nonfood_monthly"].value == 9.61
    assert by_id["cpi_p2p_nonfood_monthly"].as_of == JUN30


def test_dual_source_cpi_cards_prefer_a_genuinely_newer_official_archive_row() -> None:
    """If the archive DOES carry a newer OFFICIAL row than the daily table,
    the resolver picks it — proving this is a real newest-official
    comparison, not just 'always prefer the daily leg'."""
    archive = {
        "cpi_p2p_food_monthly": HistoryRow(
            metric_id="cpi_p2p_food_monthly", as_of=date(2026, 7, 1), value=7.5,
            source="bb_inflation_page",
        ),
    }
    ctx = BuilderContext(
        snapshot=_snap(), history=_FakeHistory(LIVE), today=AUG3,
        history_monthly=_FakeHistory(archive, default_table="metric_history_monthly"),
    )
    s = build(ctx)
    by_id = {m.id: m for m in s.metrics}
    assert by_id["cpi_p2p_food_monthly"].value == 7.5
    assert by_id["cpi_p2p_food_monthly"].as_of == date(2026, 7, 1)


def test_private_credit_yoy_is_unaffected_by_the_cpi_dual_source_resolver() -> None:
    """`dual_source_official` is opt-in, per-spec — private credit YoY (a
    plain `live_id` spec with no `archive_id`) must resolve exactly as
    before this fix, even when a `history_monthly` client is present."""
    archive = {
        "reer_monthly": _row("reer_monthly", 102.78, date(2026, 3, 1)),
        "cpi_12m_avg_monthly": _row("cpi_12m_avg_monthly", 8.6, date(2026, 3, 1)),
        "m2_growth_yoy_monthly": _row("m2_growth_yoy_monthly", 10.52, date(2026, 2, 1)),
    }
    ctx = BuilderContext(
        snapshot=_snap(), history=_FakeHistory(LIVE), today=AUG3,
        history_monthly=_FakeHistory(archive, default_table="metric_history_monthly"),
    )
    s = build(ctx)
    by_id = {m.id: m for m in s.metrics}
    assert by_id["private_credit_growth_yoy_monthly"].value == 4.98
    assert by_id["private_credit_growth_yoy_monthly"].as_of == AUG3


def test_dual_source_cpi_specs_get_no_history_facts() -> None:
    """The two CPI dual-source specs must not gain history facts merely
    because they now also carry `archive_id` — that would be new behaviour
    this fix does not intend (see the guard's comment in macro.py)."""
    archive = {
        "cpi_p2p_food_monthly": HistoryRow(
            metric_id="cpi_p2p_food_monthly", as_of=date(2026, 3, 1), value=8.1,
            source="bb_inflation_page",
        ),
    }
    ctx = BuilderContext(
        snapshot=_snap(), history=_FakeHistory(LIVE), today=AUG3,
        history_monthly=_FakeHistory(archive, default_table="metric_history_monthly"),
    )
    s = build(ctx)
    assert s.history_facts == []
