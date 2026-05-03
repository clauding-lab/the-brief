"""Tests for OilEvent constant and iranwar builder integration (Task 2C.3)."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from brief.builders import BuilderContext
from brief.builders.iranwar import OIL_EVENTS, OilEvent, build
from brief.econdelta import EconDeltaSnapshot
from datetime import datetime, timezone


def _make_ctx() -> BuilderContext:
    snap = EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={},
        data={"brent_crude_usd_barrel": 88.5, "wti_crude_usd_barrel": 84.2},
    )
    return BuilderContext(snapshot=snap, history=None, today=date(2026, 4, 21))


class TestOilEventsConstant:
    def test_oil_events_count(self):
        assert len(OIL_EVENTS) == 3

    def test_third_event_is_hot(self):
        assert OIL_EVENTS[2].hot is True

    def test_first_two_events_not_hot(self):
        assert OIL_EVENTS[0].hot is False
        assert OIL_EVENTS[1].hot is False

    def test_all_are_oil_event_dataclasses(self):
        for ev in OIL_EVENTS:
            assert isinstance(ev, OilEvent)

    def test_event_dates(self):
        assert OIL_EVENTS[0].date == date(2026, 4, 2)
        assert OIL_EVENTS[1].date == date(2026, 4, 11)
        assert OIL_EVENTS[2].date == date(2026, 4, 21)

    def test_event_labels(self):
        assert OIL_EVENTS[0].label == "IAEA report"
        assert OIL_EVENTS[1].label == "OPEC+ hold"
        assert OIL_EVENTS[2].label == "Hormuz tanker"


class TestBuilderAttachesEvents:
    def test_builder_attaches_events_to_extras(self):
        ctx = _make_ctx()
        s = build(ctx)
        assert "oil_events" in s.extras
        assert s.extras["oil_events"] == list(OIL_EVENTS)

    def test_builder_section_id(self):
        ctx = _make_ctx()
        s = build(ctx)
        assert s.id == "iranwar"

    def test_builder_has_two_metrics(self):
        ctx = _make_ctx()
        s = build(ctx)
        assert len(s.metrics) == 2
        ids = {m.id for m in s.metrics}
        assert "iranwar_brent_spot" in ids
        assert "iranwar_wti_spot" in ids
