"""Smoke test: every builder produces a valid SectionData from the fixture."""
from __future__ import annotations

import importlib
import pytest

from brief.builders import ALL_BUILDER_IDS
from brief.schema import SectionData


@pytest.mark.parametrize("bid", ALL_BUILDER_IDS)
def test_builder_smokes(bid, ctx):
    # Builders not yet implemented are skipped automatically; they must pass before merge.
    try:
        mod = importlib.import_module(f"brief.builders.{bid}")
    except ModuleNotFoundError:
        pytest.skip(f"builder {bid} not yet implemented")

    section = mod.build(ctx)
    assert isinstance(section, SectionData)
    assert section.id == {
        "bb": "bb", "macro": "macro", "fx": "fx", "remit": "remit",
        "dse": "dse", "tbond": "tbond", "iranwar": "iranwar",
        "headlines": "headlines", "exec": "exec",
        "banking": "banking", "fiscal": "fiscal",
    }[bid]
    assert section.freshness in (
        "fresh", "warning", "stale", "pending", "unavailable", "warming_up"
    )
