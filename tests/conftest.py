"""Shared fixtures — use across builder/render tests."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from brief.econdelta import EconDeltaSnapshot
from brief.builders import BuilderContext


FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def fixture_snapshot() -> EconDeltaSnapshot:
    payload = json.loads((FIXTURES / "econdelta_latest.json").read_text())
    return EconDeltaSnapshot(
        updated_at=datetime.fromisoformat(payload["updated_at"].replace("Z", "+00:00")),
        sources_status=payload["sources_status"],
        data=payload["data"],
    )


@pytest.fixture
def today() -> date:
    return date(2026, 4, 21)


@pytest.fixture
def ctx(fixture_snapshot, today) -> BuilderContext:
    return BuilderContext(
        snapshot=fixture_snapshot,
        history=None,
        today=today,
    )
