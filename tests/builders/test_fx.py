from datetime import date, datetime, timezone

from brief.builders import BuilderContext
from brief.builders.fx import build
from brief.econdelta import EconDeltaSnapshot


def _snap():
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={"bb_forex": {"status": "ok", "age_hours": 0.08}},
        data={
            "usd_bdt_mid": 122.70,
            "usd_bdt_buy": 122.60,
            "usd_bdt_sell": 122.80,
            "eur_bdt": 144.34,
            "gbp_bdt": 165.85,
        },
    )


def test_fx_fresh_populates_five_metrics():
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 4, 21))
    s = build(ctx)
    assert s.id == "fx"
    ids = {m.id for m in s.metrics}
    assert ids == {"fx_usd_bdt_mid", "fx_usd_bdt_buy", "fx_usd_bdt_sell",
                   "fx_eur_bdt", "fx_gbp_bdt"}
    assert s.freshness == "fresh"
    # Guards against positional swap in _SPEC (template concern)
    by_id = {m.id: m for m in s.metrics}
    assert by_id["fx_usd_bdt_mid"].value == 122.70
    assert by_id["fx_usd_bdt_buy"].value == 122.60
    assert by_id["fx_usd_bdt_sell"].value == 122.80
    assert by_id["fx_eur_bdt"].value == 144.34
    assert by_id["fx_gbp_bdt"].value == 165.85


def test_fx_unavailable_when_all_values_none():
    snap = EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={"bb_forex": {"status": "error", "age_hours": 72.0}},
        data={"usd_bdt_mid": None, "usd_bdt_buy": None, "usd_bdt_sell": None,
              "eur_bdt": None, "gbp_bdt": None},
    )
    ctx = BuilderContext(snapshot=snap, history=None, today=date(2026, 4, 21))
    s = build(ctx)
    assert s.freshness == "unavailable"
