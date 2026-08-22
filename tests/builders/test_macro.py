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

    def get_latest(self, metric_id: str, *, table: str | None = None) -> HistoryRow | None:
        self.tables_seen.append(table or self.default_table)
        return self._latest.get(metric_id)

    def get_history_window(self, metric_ids: list[str], **kwargs) -> dict:
        return {mid: [] for mid in metric_ids}

    def get_at_or_before(self, metric_id: str, as_of: date, *, table: str | None = None) -> HistoryRow | None:
        self.at_or_before_calls.append((metric_id, as_of))
        return self._at_or_before.get(metric_id)


# Live values good enough to exercise every path, dated 2026-08-03 unless the
# real series is genuinely older (the inflation family publishes at month end).
JUN30 = date(2026, 6, 30)
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

def test_real_policy_rate_pairs_the_repo_rate_in_force_on_the_inflation_date() -> None:
    """The bug this fixes: pairing the LATEST repo rate (9.50, post the 30-Jul
    cut) with June's inflation print (9.16) gives 0.34% — a rate that never
    coexisted with that inflation reading. The June-consistent value is the
    rate in force ON 30 Jun (10.00, pre-cut) minus 9.16 = 0.84%."""
    m = next(m for m in build(_ctx(live=LIVE, at_or_before=LIVE_AT_OR_BEFORE)).metrics
             if m.id == "real_policy_rate_monthly")
    assert m.value == pytest.approx(0.84)


def test_real_policy_rate_as_of_is_the_inflation_date() -> None:
    m = next(m for m in build(_ctx(live=LIVE, at_or_before=LIVE_AT_OR_BEFORE)).metrics
             if m.id == "real_policy_rate_monthly")
    assert m.as_of == JUN30


def test_real_policy_rate_looks_up_the_repo_rate_at_the_inflation_date() -> None:
    """Regression guard for the mechanism, not just the number: the repo
    lookup must be anchored on the inflation reading's date, not "today"."""
    history = _FakeHistory(LIVE, at_or_before_by_id=LIVE_AT_OR_BEFORE)
    ctx = BuilderContext(snapshot=_snap(), history=history, today=AUG3)
    build(ctx)
    assert ("policy_rate_repo", JUN30) in history.at_or_before_calls


def test_real_policy_rate_is_none_when_no_repo_rate_existed_that_early() -> None:
    """The corridor's `at_or_before` read finding nothing (e.g. history starts
    after the inflation date) is a missing input, not an invented rate."""
    m = next(m for m in build(_ctx(live=LIVE, at_or_before={})).metrics
             if m.id == "real_policy_rate_monthly")
    assert m.value is None


def test_import_cover_is_reserves_over_one_month_of_official_imports() -> None:
    """37.578bn reserves / 5.8bn (official imports archive, mn->bn) = 6.48 months."""
    m = next(m for m in build(_ctx(live=LIVE, archive=IMPORTS_ARCHIVE)).metrics
             if m.id == "import_cover_months_monthly")
    assert m.value == pytest.approx(6.4790, rel=1e-3)


def test_import_cover_is_suppressed_when_imports_are_more_than_a_month_stale() -> None:
    """The bug this fixes: a 31-Jul reserves read divided by a ~March import
    bill printed "6.28 months" as if current. Reserves (Jun) vs a Mar imports
    archive are 3 months apart — the honest output is no metric at all, not a
    guessed ratio."""
    stale_imports = {"imports_usd_mn_monthly": _row("imports_usd_mn_monthly", 5800.0, date(2026, 3, 31))}
    m = next(m for m in build(_ctx(live=LIVE, archive=stale_imports)).metrics
             if m.id == "import_cover_months_monthly")
    assert m.value is None


def test_import_cover_is_none_when_the_official_imports_archive_has_no_row() -> None:
    m = next(m for m in build(_ctx(live=LIVE, archive={})).metrics
             if m.id == "import_cover_months_monthly")
    assert m.value is None


def test_a_derived_metric_is_dated_by_its_oldest_input() -> None:
    """The #184 failure was a March REER printed beside that day's spot rate with
    nothing recording the gap. A figure made of a fresh input and a stale one is
    as old as the stale one."""
    s = build(_ctx(live=LIVE, archive=IMPORTS_ARCHIVE, at_or_before=LIVE_AT_OR_BEFORE))
    by_id = {m.id: m for m in s.metrics}

    # Real policy rate is dated by the inflation reading it pairs with (Jun 30).
    assert by_id["real_policy_rate_monthly"].as_of == JUN30
    # Import cover: reserves and the official imports archive are both Jun 30 here.
    assert by_id["import_cover_months_monthly"].as_of == JUN30


def test_derived_metric_is_none_when_an_input_is_missing() -> None:
    """Half a derivation is not a number. Better unavailable than invented."""
    partial = {k: v for k, v in LIVE.items() if k != "general_inflation"}
    m = next(m for m in build(_ctx(live=partial, at_or_before=LIVE_AT_OR_BEFORE)).metrics
             if m.id == "real_policy_rate_monthly")
    assert m.value is None


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
