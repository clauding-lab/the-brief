"""Tests for brief.sources — source taxonomy + code resolver."""
from __future__ import annotations

from brief.sources import SOURCE_BADGES, resolve_source_code


def test_known_codes_present():
    for code in ("REU", "DS", "TBS", "FE", "BBC", "AJZ", "FT", "BBN"):
        assert code in SOURCE_BADGES
        assert "name" in SOURCE_BADGES[code]
        assert "css" in SOURCE_BADGES[code]


def test_resolve_returns_known_code_unchanged():
    assert resolve_source_code("DS") == "DS"
    assert resolve_source_code("REU") == "REU"


def test_resolve_handles_full_name_case_insensitive():
    assert resolve_source_code("Reuters") == "REU"
    assert resolve_source_code("reuters") == "REU"
    assert resolve_source_code("The Daily Star") == "DS"
    assert resolve_source_code("the business standard") == "TBS"


def test_resolve_handles_common_aliases():
    assert resolve_source_code("Financial Express BD") == "FE"
    assert resolve_source_code("TBS News") == "TBS"


def test_resolve_unknown_returns_none():
    assert resolve_source_code("Some Random Outlet") is None
    assert resolve_source_code("") is None


def test_resolve_strips_whitespace():
    assert resolve_source_code("  Reuters  ") == "REU"
