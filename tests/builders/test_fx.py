from datetime import date, datetime, timezone

from brief.builders import BuilderContext
from brief.builders.fx import build
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow


def _snap():
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={"bb_forex": {"status": "ok", "age_hours": 0.08}},
        data={
            "usd_bdt_mid": 122.70,
            "gold_usd_oz": 3310.5,
        },
    )


class _FakeHistory:
    """Minimal MetricHistoryClient stub returning known last-knowns."""

    def __init__(self, latest_by_id: dict):
        self._latest = latest_by_id

    def get_latest(self, metric_id: str, *, table: str | None = None):
        return self._latest.get(metric_id)


class _Row:
    def __init__(self, value, as_of):
        self.value = value
        self.as_of = as_of


def _archive_row(metric_id: str, value_mn: float, as_of: date) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=as_of, value=value_mn, source="EPB")


def test_fx_post_2026_05_03_layout():
    """USD/BDT spot + Gold + Gross Reserves + Exports — no trade gap because
    exports and imports cover different months (P0 honesty fix, audit #204)."""
    history = _FakeHistory({
        "gross_reserves_usd_bn": _Row(35.04, date(2026, 4, 15)),
    })
    history_monthly = _FakeHistory({
        "exports_usd_mn_monthly": _archive_row("exports_usd_mn_monthly", 4202.69, date(2026, 6, 1)),
        "imports_usd_mn_monthly": _archive_row("imports_usd_mn_monthly", 5826.2, date(2026, 3, 1)),
    })
    ctx = BuilderContext(snapshot=_snap(), history=history, today=date(2026, 8, 22),
                         history_monthly=history_monthly)
    s = build(ctx)
    assert s.id == "fx"
    by_id = {m.id: m for m in s.metrics}
    assert set(by_id) == {"fx_usd_bdt_mid", "fx_gold_usd_oz",
                          "fx_gross_reserves", "fx_monthly_exports"}
    assert by_id["fx_usd_bdt_mid"].value == 122.70
    assert by_id["fx_gold_usd_oz"].value == 3310.5
    assert by_id["fx_gross_reserves"].value == 35.04
    # 4202.69 mn -> 4.20 bn, as_of normalized to June's month-end
    assert by_id["fx_monthly_exports"].value == 4.2
    assert by_id["fx_monthly_exports"].as_of == date(2026, 6, 30)
    assert by_id["fx_monthly_exports"].source == "EPB"
    # No trade gap tile at all — different months (Jun exports vs Mar imports)
    assert "fx_trade_gap" not in by_id


def test_fx_trade_gap_emitted_when_exports_and_imports_share_a_month():
    history_monthly = _FakeHistory({
        "exports_usd_mn_monthly": _archive_row("exports_usd_mn_monthly", 4202.69, date(2026, 6, 1)),
        "imports_usd_mn_monthly": _archive_row("imports_usd_mn_monthly", 5826.2, date(2026, 6, 30)),
    })
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 8, 22),
                         history_monthly=history_monthly)
    s = build(ctx)
    by_id = {m.id: m for m in s.metrics}
    assert "fx_trade_gap" in by_id
    # L1 (review round 1): mn->bn division stays FULL PRECISION until the
    # final subtraction, rounded once at the end — 4202.69/1000 - 5826.2/1000
    # = -1.62351 -> -1.62 (not -1.63, which is what rounding each leg to 2dp
    # BEFORE subtracting would have given).
    assert by_id["fx_trade_gap"].value == round(4202.69 / 1000 - 5826.2 / 1000, 2)
    assert by_id["fx_trade_gap"].as_of == date(2026, 6, 30)
    assert by_id["fx_trade_gap"].source == "EPB · BB"


def test_fx_trade_gap_omitted_when_imports_leg_missing():
    """Trade gap requires both legs from the SAME month; otherwise no tile at all."""
    history_monthly = _FakeHistory({
        "exports_usd_mn_monthly": _archive_row("exports_usd_mn_monthly", 4202.69, date(2026, 6, 1)),
    })
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 8, 22),
                         history_monthly=history_monthly)
    s = build(ctx)
    by_id = {m.id: m for m in s.metrics}
    assert "fx_trade_gap" not in by_id
    # Exports leg still populated
    assert by_id["fx_monthly_exports"].value == 4.2


def test_fx_exports_omitted_when_archive_has_no_row():
    """No flash fallback for exports — the flash is a different basis."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 8, 22),
                         history_monthly=_FakeHistory({}))
    s = build(ctx)
    by_id = {m.id: m for m in s.metrics}
    assert "fx_monthly_exports" not in by_id
    assert "fx_trade_gap" not in by_id


def test_fx_external_metrics_omitted_when_history_monthly_unavailable():
    """No monthly client → exports/trade-gap tiles are omitted (not None-valued)."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 8, 22))
    s = build(ctx)
    by_id = {m.id: m for m in s.metrics}
    assert "fx_monthly_exports" not in by_id
    assert "fx_trade_gap" not in by_id
    assert by_id["fx_gross_reserves"].value is None
    # Spot rate and Gold still pulled from the snapshot, which needs no history
    assert by_id["fx_usd_bdt_mid"].value == 122.70
    assert by_id["fx_gold_usd_oz"].value == 3310.5


def test_fx_freshness_is_worst_of_all_metrics_not_badge_cherry_picked():
    """P2 fact-checker regression (2026-08-22 audit #204, round-2 item 4):
    the old `badge_metrics` cherry-pick only looked at spot + Gold, both
    stamped with today's date every run, so the section could never read
    anything but "fresh" — even while Exports sat two months stale. With
    today's real production data shape (Exports at Jun, reserves stale since
    mid-April) the section must now honestly read "stale"."""
    history = _FakeHistory({
        "gross_reserves_usd_bn": _Row(35.04, date(2026, 4, 15)),
    })
    history_monthly = _FakeHistory({
        "exports_usd_mn_monthly": _archive_row("exports_usd_mn_monthly", 4202.69, date(2026, 6, 1)),
        "imports_usd_mn_monthly": _archive_row("imports_usd_mn_monthly", 5826.2, date(2026, 3, 1)),
    })
    ctx = BuilderContext(snapshot=_snap(), history=history, today=date(2026, 8, 22),
                         history_monthly=history_monthly)
    s = build(ctx)
    assert s.freshness == "stale"


def test_fx_freshness_is_fresh_when_every_metric_is_genuinely_current():
    """Same worst-of mechanism, opposite direction — spot/Gold/reserves all
    current and no monthly archive tiles present must still read "fresh"."""
    history = _FakeHistory({
        "gross_reserves_usd_bn": _Row(35.04, date(2026, 8, 21)),
    })
    ctx = BuilderContext(snapshot=_snap(), history=history, today=date(2026, 8, 22),
                         history_monthly=_FakeHistory({}))
    s = build(ctx)
    assert s.freshness == "fresh"


def test_fx_unavailable_when_all_values_none():
    snap = EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={"bb_forex": {"status": "error", "age_hours": 72.0}},
        data={"usd_bdt_mid": None, "gold_usd_oz": None},
    )
    ctx = BuilderContext(snapshot=snap, history=None, today=date(2026, 4, 21))
    s = build(ctx)
    assert s.freshness == "unavailable"
