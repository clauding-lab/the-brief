"""Unit tests for build_weekly_input — Friday weekly wrap."""
from datetime import date

from brief.builders.weekly import build_weekly_input


def test_adds_weekly_diffs_block():
    base = {
        "today": "2026-05-08",
        "today_lens": "weekly_wrap",
        "previous_brief": None,
        "sections_raw": [{"slug": "iran", "metrics": [{"label": "Brent", "value": "$113.95"}]}],
        "scraped_headlines": [],
        "meta": {"issue_no": 95, "volume": 1, "brief_date": "2026-05-08"},
    }
    out = build_weekly_input(base, today=date(2026, 5, 8))
    assert "weekly_diffs" in out
    assert out["today_lens"] == "weekly_wrap"
    # All other keys preserved
    assert out["meta"] == base["meta"]


def test_today_must_be_friday():
    """build_weekly_input on non-Friday is a programmer error — raise."""
    import pytest
    with pytest.raises(ValueError, match="Friday"):
        build_weekly_input({}, today=date(2026, 5, 4))  # Monday
