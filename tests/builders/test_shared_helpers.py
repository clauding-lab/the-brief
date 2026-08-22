"""Tests for shared builder helpers in `brief/builders/__init__.py`.

`official_monthly_bn` is the P0 honesty fix (2026-08-22 audit #204) shared
between fx.py (exports/imports, trade gap) and macro.py (import cover): read
the latest official "*_usd_mn_monthly" archive row, convert mn USD -> bn USD,
and normalize `as_of` to that month's last day.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from brief.builders import BuilderContext, official_monthly_bn
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow


def _snap() -> EconDeltaSnapshot:
    return EconDeltaSnapshot(updated_at=datetime(2026, 8, 22, tzinfo=timezone.utc), sources_status={}, data={})


class _FakeHistory:
    def __init__(self, latest_by_id: dict[str, HistoryRow]) -> None:
        self._latest = latest_by_id

    def get_latest(self, metric_id: str, *, table: str | None = None) -> HistoryRow | None:
        return self._latest.get(metric_id)


class _Boom:
    def get_latest(self, *a, **k):
        raise RuntimeError("supabase down")


def _ctx(history_monthly) -> BuilderContext:
    return BuilderContext(snapshot=_snap(), history=None, today=date(2026, 8, 22),
                         history_monthly=history_monthly)


def test_converts_mn_to_bn_and_normalizes_as_of_to_month_end():
    row = HistoryRow(metric_id="exports_usd_mn_monthly", as_of=date(2026, 6, 1),
                     value=4202.69, source="EPB")
    result = official_monthly_bn(_ctx(_FakeHistory({"exports_usd_mn_monthly": row})),
                                 "exports_usd_mn_monthly")
    assert result is not None
    assert result.value == 4.2
    assert result.as_of == date(2026, 6, 30)


def test_returns_none_when_history_monthly_client_is_absent():
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 8, 22))
    assert official_monthly_bn(ctx, "exports_usd_mn_monthly") is None


def test_returns_none_when_the_row_is_missing():
    assert official_monthly_bn(_ctx(_FakeHistory({})), "exports_usd_mn_monthly") is None


def test_returns_none_when_the_value_is_not_numeric():
    row = HistoryRow(metric_id="x", as_of=date(2026, 6, 1), value="n/a", source="EPB")
    assert official_monthly_bn(_ctx(_FakeHistory({"x": row})), "x") is None


def test_returns_none_when_the_read_raises():
    """A dark archive read must not take the builder (or the issue) down."""
    assert official_monthly_bn(_ctx(_Boom()), "exports_usd_mn_monthly") is None
