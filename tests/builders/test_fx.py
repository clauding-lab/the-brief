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
            "eur_bdt": 144.34,
        },
    )


class _FakeHistory:
    """Minimal MetricHistoryClient stub returning known last-knowns."""

    def __init__(self, latest_by_id: dict):
        self._latest = latest_by_id

    def get_latest(self, metric_id: str):
        return self._latest.get(metric_id)


class _Row:
    def __init__(self, value, as_of):
        self.value = value
        self.as_of = as_of


def test_fx_post_2026_05_03_layout():
    """USD/BDT spot + 4 cross-section external-balance metrics."""
    history = _FakeHistory({
        "gross_reserves_usd_bn": _Row(35.04, date(2026, 4, 15)),
        "monthly_export":        _Row(3.48,  date(2026, 3, 31)),
        "monthly_import":        _Row(6.48,  date(2026, 3, 31)),
        "monthly_remittance":    _Row(3.755, date(2026, 3, 31)),
    })
    ctx = BuilderContext(snapshot=_snap(), history=history, today=date(2026, 4, 21))
    s = build(ctx)
    assert s.id == "fx"
    by_id = {m.id: m for m in s.metrics}
    assert {"fx_usd_bdt_mid", "fx_eur_bdt",
            "fx_gross_reserves", "fx_monthly_exports",
            "fx_trade_gap", "fx_monthly_remittance"} <= set(by_id)
    assert by_id["fx_usd_bdt_mid"].value == 122.70
    assert by_id["fx_gross_reserves"].value == 35.04
    assert by_id["fx_monthly_exports"].value == 3.48
    # Trade gap = exports − imports = 3.48 − 6.48 = −3.0
    assert by_id["fx_trade_gap"].value == -3.0
    assert by_id["fx_monthly_remittance"].value == 3.755


def test_fx_trade_gap_null_when_legs_missing():
    """Trade gap requires both export + import; null otherwise."""
    history = _FakeHistory({
        "monthly_export": _Row(3.48, date(2026, 3, 31)),
        # monthly_import absent → no gap
    })
    ctx = BuilderContext(snapshot=_snap(), history=history, today=date(2026, 4, 21))
    s = build(ctx)
    by_id = {m.id: m for m in s.metrics}
    assert by_id["fx_trade_gap"].value is None
    # Exports leg still populated
    assert by_id["fx_monthly_exports"].value == 3.48


def test_fx_external_metrics_null_when_history_unavailable():
    """No history client → cross-section metrics are None placeholders."""
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 4, 21))
    s = build(ctx)
    by_id = {m.id: m for m in s.metrics}
    assert by_id["fx_gross_reserves"].value is None
    assert by_id["fx_monthly_exports"].value is None
    assert by_id["fx_trade_gap"].value is None
    assert by_id["fx_monthly_remittance"].value is None
    # Spot rates still pulled from snapshot
    assert by_id["fx_usd_bdt_mid"].value == 122.70


def test_fx_unavailable_when_all_values_none():
    snap = EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={"bb_forex": {"status": "error", "age_hours": 72.0}},
        data={"usd_bdt_mid": None, "eur_bdt": None},
    )
    ctx = BuilderContext(snapshot=snap, history=None, today=date(2026, 4, 21))
    s = build(ctx)
    assert s.freshness == "unavailable"
