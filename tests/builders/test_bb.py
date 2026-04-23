from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from brief.builders import BuilderContext
from brief.builders.bb import build
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow


def _snap(**overrides):
    data = {
        "gross_reserves_usd_bn": 34.1166,
        "reserves_date": "2026-04-14",
    }
    data.update(overrides)
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={"bb_forex": {"status": "ok", "age_hours": 0.1}},
        data=data,
    )


def test_bb_fresh_with_reserves_and_event_rates():
    history = MagicMock()
    history.get_latest.return_value = HistoryRow(
        "bb_gross_reserves", date(2026, 4, 13), 33.80, "BB"
    )
    ctx = BuilderContext(
        snapshot=_snap(),
        history=history,
        today=date(2026, 4, 21),
    )
    s = build(ctx)
    assert s.id == "bb"
    assert s.freshness in ("fresh", "warning")
    ids = {m.id for m in s.metrics}
    assert {"bb_policy_rate", "bb_sdf", "bb_gross_reserves"}.issubset(ids)
    reserves = next(m for m in s.metrics if m.id == "bb_gross_reserves")
    assert reserves.value == 34.1166
    assert reserves.delta is not None
    assert reserves.delta.direction == "up"
    assert reserves.delta.window == "wow"


def test_bb_handles_missing_reserves():
    ctx = BuilderContext(
        snapshot=_snap(gross_reserves_usd_bn=None),
        history=None,
        today=date(2026, 4, 21),
    )
    s = build(ctx)
    reserves = next((m for m in s.metrics if m.id == "bb_gross_reserves"), None)
    assert reserves is not None
    assert reserves.value is None
    assert s.freshness in ("unavailable", "warning", "stale")
