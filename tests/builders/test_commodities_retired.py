"""Tests for v1.6.7: Commodities retired, Gold rehomed into FX & External.

The `comm` section carried exactly two tiles. LNG's only live source is a
monthly World Bank Pink Sheet print whose download URL is edition-pinned and has
frozen silently before; v1.6.6 had just repointed it off a series that died
2026-04-20 after 105 days of printing the same 15.00. Gold is a genuine daily
reading and the only thing keeping the section alive.

Removing a section is easy to get half-right. The three ways it goes wrong:

  1. The builder stops running but the slug stays in the V5→V6 map, so the
     pipeline keeps a slot for a section that no longer exists.
  2. Gold is "moved" but the id changes and nothing checks the value survived
     the move, so the number quietly becomes something else.
  3. Gold's disappearance stops being visible. `comm`'s badge used to report
     "unavailable" when the snapshot lost `gold_usd_oz`. If Gold lands in FX as
     pure context — as reserves and trade flows already are — that signal is
     gone and nobody notices gold went missing.

Each has a test below.
"""
from __future__ import annotations

import importlib
from datetime import date, datetime, timezone

import pytest

from brief.builders import ALL_BUILDER_IDS, BuilderContext
from brief.builders.fx import build as build_fx
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow
from brief.pipeline_v6 import V5_TO_V6

AUG4 = date(2026, 8, 4)
JUN30 = date(2026, 6, 30)

# The values production actually held on 2026-08-04.
GOLD_USD_OZ = 4121.10009765625
USD_BDT_MID = 123.8197


def _row(metric_id: str, value: float, as_of: date) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=as_of, value=value, source="test")


class _FakeHistory:
    def __init__(self, latest_by_id: dict[str, HistoryRow]) -> None:
        self._latest = latest_by_id

    def get_latest(self, metric_id: str, *, table: str | None = None) -> HistoryRow | None:
        return self._latest.get(metric_id)

    def get_history_window(self, metric_ids: list[str], **kwargs) -> dict:
        return {mid: [] for mid in metric_ids}


LIVE = {
    "gross_reserves_usd_bn": _row("gross_reserves_usd_bn", 37.578, JUN30),
    # P0 honesty fix (2026-08-22 audit #204): fx.py no longer reads the daily
    # `monthly_export`/`monthly_import` flash — exports/trade-gap now read the
    # official `*_usd_mn_monthly` archive (mn USD; fx.py converts to bn). Both
    # dated the SAME month (June) here so the trade gap actually computes —
    # 4030.0mn/5800.0mn -> 4.03bn/5.80bn, reproducing this fixture's original
    # figures on an honest (same-month) footing.
    "exports_usd_mn_monthly": _row("exports_usd_mn_monthly", 4030.0, JUN30),
    "imports_usd_mn_monthly": _row("imports_usd_mn_monthly", 5800.0, JUN30),
}


def _ctx(*, data: dict | None = None, today: date = AUG4) -> BuilderContext:
    history = _FakeHistory(LIVE)
    return BuilderContext(
        snapshot=EconDeltaSnapshot(
            updated_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
            sources_status={},
            data={"usd_bdt_mid": USD_BDT_MID, "gold_usd_oz": GOLD_USD_OZ}
            if data is None
            else data,
        ),
        history=history,
        today=today,
        history_monthly=history,
    )


# ── 1. the section is gone from every place that could resurrect it ──────────

def test_the_comm_builder_module_no_longer_exists() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("brief.builders.comm")


def test_comm_is_not_in_the_builder_registry() -> None:
    assert "comm" not in ALL_BUILDER_IDS


def test_comm_is_not_in_the_v5_to_v6_map() -> None:
    """A slug left in this map reserves an ord and a group for a section the
    pipeline can no longer produce."""
    assert "comm" not in V5_TO_V6


def test_no_surviving_section_took_over_comms_ord() -> None:
    """Ord 12 is deliberately retired rather than reused: renumbering would
    silently re-home whichever section inherited the slot."""
    assert 12 not in {ord_ for _slug, ord_, _group in V5_TO_V6.values()}


# ── 2. Gold moved, and it is still the same number ───────────────────────────

def test_gold_now_ships_inside_fx() -> None:
    ids = {m.id for m in build_fx(_ctx()).metrics}
    assert "fx_gold_usd_oz" in ids


def test_gold_reads_the_same_snapshot_key_and_value_as_before() -> None:
    """`comm` read `gold_usd_oz` off the EconDelta snapshot. The move must not
    change the printed number — only where it sits on the page."""
    gold = next(m for m in build_fx(_ctx()).metrics if m.id == "fx_gold_usd_oz")
    assert gold.value == GOLD_USD_OZ
    assert gold.label == "Gold"
    assert gold.unit == "USD/oz"
    assert gold.cadence == "daily"
    assert gold.source == "EconDelta"


def test_fx_fits_the_editors_five_metric_cap_so_gold_actually_renders() -> None:
    """Moving Gold into a section that is already full does not move Gold — the
    editor prompt says "drop low-signal metrics (max 5 per section)" and picks
    which. FX carried 6 before this change and the editor was discarding EUR/BDT
    on its own. Two went, so all five that remain are published.

    If this ever fails because a metric was added, the fix is to decide what
    leaves — not to raise the number. The cap lives in the editor prompt, and
    the prompt is a sign-off-gated contract file."""
    metrics = build_fx(_ctx()).metrics
    assert len(metrics) == 5
    ids = {m.id for m in metrics}
    assert "fx_eur_bdt" not in ids
    assert "fx_gold_usd_oz" in ids


def test_fx_no_longer_duplicates_the_remittance_tile() -> None:
    """§05 printed `monthly_remittance` (2.82 bn USD) while §11 printed
    `remit_monthly_mn` (2820.0 mn USD) — the same BB figure, twice, under the
    same label. The copy went; §11 is the section that exists to report it."""
    ids = {m.id for m in build_fx(_ctx()).metrics}
    assert "fx_monthly_remittance" not in ids


# ── 3. losing Gold is still visible ──────────────────────────────────────────

def test_a_snapshot_without_gold_degrades_the_fx_badge() -> None:
    """This is the signal `comm`'s badge used to carry. Gold's as_of is stamped
    with today every run, so it can never age into "stale" — but a snapshot that
    stops carrying `gold_usd_oz` gives value=None, which scores "unavailable".
    Without this, Gold could vanish for months under a green badge, which is
    exactly how LNG survived 105 days."""
    s = build_fx(_ctx(data={"usd_bdt_mid": USD_BDT_MID}))
    gold = next(m for m in s.metrics if m.id == "fx_gold_usd_oz")
    assert gold.value is None
    assert s.freshness != "fresh"


def test_a_stale_reserves_row_now_correctly_drags_the_fx_badge() -> None:
    """SUPERSEDED (P2 fact-checker, 2026-08-22 audit #204, round-2 item 4):
    this test used to assert the opposite — that reserves and trade flows
    were supporting context excluded from the freshness badge, so FX stayed
    "fresh" even while reserves sat 35 days stale. That was audit finding (e):
    "the fx badge reads ONLY spot+gold." fx.py now scores freshness worst-of
    ALL its metrics, same as every other builder.

    Reserves are month-END stamped and declared monthly since the landmine-24
    correction (fresh <=35d, warning <=45d), so the 35-day-old June print this
    test originally used is now — correctly — still fresh. The stale case is a
    print older than 45 days. To prove RESERVES is the driver (and not the
    exports/trade-gap tiles, which stay inside their 35-day window here), the
    same context is run twice: reserves at 30 Jun reads fresh, at 31 May reads
    stale, and only the second drags the section."""
    def _ctx_with_reserves(as_of: date) -> BuilderContext:
        history = _FakeHistory({**LIVE, "gross_reserves_usd_bn": _row("gross_reserves_usd_bn", 37.578, as_of)})
        return BuilderContext(
            snapshot=EconDeltaSnapshot(
                updated_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
                sources_status={},
                data={"usd_bdt_mid": USD_BDT_MID, "gold_usd_oz": GOLD_USD_OZ},
            ),
            history=history, today=AUG4, history_monthly=history,
        )

    current = build_fx(_ctx_with_reserves(JUN30))
    assert (AUG4 - JUN30).days == 35
    assert current.freshness == "fresh"                    # exports (35d) and reserves (35d) both fresh

    late = build_fx(_ctx_with_reserves(date(2026, 5, 31)))
    reserves = next(m for m in late.metrics if m.id == "fx_gross_reserves")
    assert (AUG4 - reserves.as_of).days == 65
    assert late.freshness == "stale"                       # reserves alone drags the section
