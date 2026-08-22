"""Tests for v1.6.6: the three never-written metrics.

Three ids were wired into shipping sections and had never had a single row in
`metric_history` or `metric_history_monthly` — `fiscal_nbr_target_trn`,
`fiscal_adp_pct`, `remit_yoy_pct`.

A fourth, `comm_lng_jkm`, had 12 rows and then died on 2026-04-20, and kept
printing 15.00 USD/MMBtu for 105 days. v1.6.6 repointed it to the live Pink
Sheet series; v1.6.7 retired the whole Commodities section, so the LNG cases
that used to live here now have nothing to assert against. What replaced them
is in test_commodities_retired.py.

The property worth protecting is not "these labels are gone". It is that a
section's freshness badge means what it says. A None-valued metric scores
"unavailable", which for a SECTIONS_WITHOUT_LEGACY_BACKFILL section is promoted
to "warming_up" — a badge that promises data is on its way. For an id nobody
writes, that promise is never kept, and a badge that always claims to be warming
up is indistinguishable from one that is broken.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from brief.builders import BuilderContext
from brief.builders.fiscal import build as build_fiscal
from brief.builders.remit import build as build_remit
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow

AUG3 = date(2026, 8, 3)
JUN30 = date(2026, 6, 30)


def _row(metric_id: str, value: float, as_of: date) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=as_of, value=value, source="test")


class _FakeHistory:
    """Returns only what it was given — asking for a dead id yields None, which
    is exactly what production does for these four."""

    def __init__(self, latest_by_id: dict[str, HistoryRow]) -> None:
        self._latest = latest_by_id
        self.ids_seen: list[str] = []

    def get_latest(self, metric_id: str, *, table: str | None = None) -> HistoryRow | None:
        self.ids_seen.append(metric_id)
        return self._latest.get(metric_id)

    def get_history_window(self, metric_ids: list[str], **kwargs) -> dict:
        return {mid: [] for mid in metric_ids}


# The live rows, at the values production actually held on 2026-08-03.
# `remittance_usd_mn_monthly` is the OFFICIAL final remit.py now reads first
# (P0 honesty fix, 2026-08-22 audit #204) — with a July row present, remit
# takes that path rather than the unconfirmed daily flash, so its freshness
# genuinely reflects a confirmed current read (not floored to "warning" by
# the flash-fallback's stale=True, M-B review round 2).
LIVE = {
    "fiscal_nbr_collected_trn": _row("fiscal_nbr_collected_trn", 3.61, AUG3),
    "fiscal_govt_borrow_trn": _row("fiscal_govt_borrow_trn", 0.94, JUN30),
    "remit_monthly_mn": _row("remit_monthly_mn", 2820.0, AUG3),
    "remittance_usd_mn_monthly": _row("remittance_usd_mn_monthly", 2858.68, date(2026, 7, 31)),
}


def _ctx(*, live: dict | None = None, today: date = AUG3) -> BuilderContext:
    history = _FakeHistory(LIVE if live is None else live)
    return BuilderContext(
        snapshot=EconDeltaSnapshot(
            updated_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
            sources_status={},
            data={"gold_usd_oz": 3400.0},
        ),
        history=history,
        today=today,
        history_monthly=history,
    )


# ── the ids are gone, and nothing asks the database for them ─────────────────

def test_fiscal_no_longer_carries_the_never_written_ids() -> None:
    ids = {m.id for m in build_fiscal(_ctx()).metrics}
    assert "fiscal_nbr_target_trn" not in ids
    assert "fiscal_adp_pct" not in ids


def test_remit_no_longer_carries_the_never_written_id() -> None:
    assert "remit_yoy_pct" not in {m.id for m in build_remit(_ctx()).metrics}


def test_the_dead_ids_are_not_even_queried() -> None:
    """A removed metric that still costs a round-trip is half-removed. This also
    pins the intent: these are not "temporarily hidden", they are unwired."""
    ctx = _ctx()
    build_fiscal(ctx)
    build_remit(ctx)
    seen = ctx.history.ids_seen  # type: ignore[union-attr]
    assert "fiscal_nbr_target_trn" not in seen
    assert "fiscal_adp_pct" not in seen
    assert "remit_yoy_pct" not in seen


# ── what the removal was actually for: an honest badge ───────────────────────

def test_fiscal_reads_fresh_when_its_live_metrics_are_fresh() -> None:
    """Before v1.6.6 this section said "warming_up" no matter how current its
    real numbers were, because two permanently-None tiles outvoted them."""
    assert build_fiscal(_ctx()).freshness == "fresh"


def test_remit_reads_fresh_when_its_live_metric_is_fresh() -> None:
    assert build_remit(_ctx()).freshness == "fresh"


def test_a_genuinely_missing_row_still_degrades_the_section() -> None:
    """The removal must not have bought a green badge by disabling the signal.
    Drop the live row and the section must go back to reporting trouble."""
    s = build_remit(_ctx(live={}))
    assert s.metrics[0].value is None
    assert s.freshness == "warming_up"
