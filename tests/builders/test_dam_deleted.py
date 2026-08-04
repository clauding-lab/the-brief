"""Tests for v1.6.8: the DAM Food Prices builder is deleted.

`brief/builders/dam.py` shipped in the original 9-builder batch and was never
registered. `gather()` iterates `ALL_BUILDER_IDS`, `dam` was in neither
`SPINE_BUILDER_IDS` nor `KEEP_BUILDER_IDS`, so the module was never imported and
its nine food-price metrics were never built — not built-and-dropped, never
built at all. It sat there for months looking like a shipping section.

Deleting it is the easy half. The half worth testing is that nothing else still
believes in it, because the leftovers are all *silent*:

  - `SECTIONS_WITHOUT_LEGACY_BACKFILL` held "dam". That set turns an
    "unavailable" badge into "warming_up" — a promise that data is on the way.
    A promise made on behalf of a section that cannot exist is a promise that
    can never be kept, and nothing would ever have reported it.
  - A registry entry added later would silently resurrect an import of a file
    that is gone, and fail at collection rather than at review.

The upstream scrapers are untouched. EconDelta still collects these prices; The
Brief has simply stopped carrying a reader for them. If Food Prices is ever
wanted as a section, it comes back as a new builder against live data — not by
reviving this file, whose nine ids had been frozen at identical values for 92
days when it was removed.
"""
from __future__ import annotations

import importlib

import pytest

from brief.builders import ALL_BUILDER_IDS
from brief.cadence import SECTIONS_WITHOUT_LEGACY_BACKFILL
from brief.pipeline_v6 import V5_TO_V6


def test_the_dam_builder_module_no_longer_exists() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("brief.builders.dam")


def test_dam_is_not_in_the_builder_registry() -> None:
    """It never was — this pins that a future edit does not add it back and
    wire `gather()` to an import that cannot resolve."""
    assert "dam" not in ALL_BUILDER_IDS


def test_dam_is_not_in_the_v5_to_v6_map() -> None:
    assert "dam" not in V5_TO_V6


def test_dam_no_longer_claims_a_warming_up_badge() -> None:
    """Membership here promotes "unavailable" to "warming_up" — "history is
    accumulating, expect this shortly". For a section with no builder that
    sentence can never come true."""
    assert "dam" not in SECTIONS_WITHOUT_LEGACY_BACKFILL


def test_the_sections_that_do_get_the_warming_up_promotion_are_all_real() -> None:
    """The general form of the bug above: every id in this set must be a
    section something can actually build, or the badge is writing a cheque for
    a section that will never arrive."""
    assert set(SECTIONS_WITHOUT_LEGACY_BACKFILL) <= set(ALL_BUILDER_IDS)
