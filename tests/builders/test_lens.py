"""Unit tests for score_lens — data-driven daily lens picker."""
from datetime import date

import pytest

from brief.builders.lens import score_lens


def _section(slug: str, metrics: list[dict], days_since_refresh: int = 0) -> dict:
    return {
        "slug": slug,
        "metrics": metrics,
        "freshness_days_since_refresh": days_since_refresh,
    }


def test_friday_returns_weekly_wrap_unconditionally():
    """Friday always wins weekly_wrap regardless of data."""
    sections = [_section("banking", [{"label": "NPL", "value": "35.73%", "delta_sigma": 5.0}])]
    lens, _ = score_lens(sections, today=date(2026, 5, 8), previous_lens=None)  # Friday
    assert lens == "weekly_wrap"


def test_highest_movement_wins():
    """Mon: section with the biggest σ-move wins."""
    today = date(2026, 5, 4)  # Monday
    sections = [
        _section("banking", [{"label": "NPL", "value": "35.73%", "delta_sigma": 0.0}], days_since_refresh=20),
        _section("iran",    [{"label": "Brent", "value": "$113.95", "delta_sigma": 3.2}], days_since_refresh=0),
    ]
    lens, breakdown = score_lens(sections, today=today, previous_lens="banking")
    assert lens == "iran"
    assert breakdown["iran"]["score"] > breakdown["banking"]["score"]


def test_held_over_section_loses_signal():
    """A section dominated by held-overs scores low even if data is "fresh"."""
    today = date(2026, 5, 4)
    sections = [
        _section("banking", [
            {"label": "NPL", "value": "35.73%", "delta_sigma": 0.0, "is_held_over": True},
            {"label": "CAR", "value": "1.56%", "delta_sigma": 0.0, "is_held_over": True},
        ], days_since_refresh=0),
        _section("fx", [{"label": "USDBDT", "value": "122.70", "delta_sigma": 1.5}], days_since_refresh=0),
    ]
    lens, _ = score_lens(sections, today=today, previous_lens=None)
    assert lens == "fx"


def test_quiet_day_falls_back_to_previous_lens():
    """All sections score < 0.05 → fall back to previous_lens."""
    today = date(2026, 5, 4)
    sections = [
        _section("banking", [{"label": "X", "value": "1", "delta_sigma": 0.0}], days_since_refresh=20),
    ]
    lens, breakdown = score_lens(sections, today=today, previous_lens="iran")
    assert lens == "iran"
    assert breakdown["fallback"] == "quiet_day"


def test_quiet_day_no_previous_falls_back_to_alpha():
    """Quiet day + no previous lens → alphabetical first slug."""
    today = date(2026, 5, 4)
    sections = [
        _section("zebra", [{"label": "X", "value": "1", "delta_sigma": 0.0}], days_since_refresh=20),
        _section("alpha", [{"label": "Y", "value": "2", "delta_sigma": 0.0}], days_since_refresh=20),
    ]
    lens, _ = score_lens(sections, today=today, previous_lens=None)
    assert lens == "alpha"


def test_freshness_decay_linear_14d():
    """freshness=1.0 today, 0.5 at 7d, 0.0 at >=14d."""
    from brief.builders.lens import _freshness_score
    assert _freshness_score(0) == 1.0
    assert abs(_freshness_score(7) - 0.5) < 0.01
    assert _freshness_score(14) == 0.0
    assert _freshness_score(30) == 0.0
