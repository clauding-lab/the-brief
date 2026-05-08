"""Lens scorer regression — sections marked 'unavailable' must not win lens.

Background:
  brief/builders/lens.py:score_lens() picks today's editorial lens by
  multiplying freshness × magnitude × signal per section. brief/pipeline_v6.py
  maps freshness="unavailable" → days_since_refresh=30, and
  _freshness_score(30) = 0.0 (linear decay, ≥14d → 0.0). So any section
  upstream-flagged unavailable scores 0 — guaranteed below the 0.05
  quiet-day threshold.

These tests pin that contract:

  a. Mid-week (Mon–Thu): a single FRESH section beats a pile of UNAVAILABLE
     sections, even when the unavailable sections carry high σ-mag (because
     freshness=0.0 zeroes out the product).
  b. All sections unavailable + previous_lens set → fall back to previous_lens
     with breakdown["fallback"]=="quiet_day".
  c. All sections unavailable + previous_lens=None → fall back to
     alphabetically first slug with breakdown["fallback"]=="quiet_day_alpha".

This is the deferred MEDIUM finding from the python-reviewer pass on PR #48.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from brief.builders.lens import score_lens


# ──────────────────────────────────────────────────────────────────────
# Fixture helpers
# ──────────────────────────────────────────────────────────────────────


def _unavailable_section(slug: str, *, mag: float = 2.0) -> dict[str, Any]:
    """Build a section dict shaped like _build_editor_input produces:
    days_since_refresh=30 (the upstream mapping for freshness='unavailable'),
    all metrics held_over=True, and high σ-mag to prove that magnitude alone
    does not rescue an unavailable section."""
    return {
        "slug": slug,
        "freshness_days_since_refresh": 30,
        "metrics": [
            {
                "label": f"{slug}_metric",
                "value": "100",
                "delta_sigma": mag,
                "is_held_over": True,
            },
        ],
    }


def _fresh_section(slug: str, *, mag: float = 1.0) -> dict[str, Any]:
    """Build a fresh section: days_since_refresh=0, no metrics held."""
    return {
        "slug": slug,
        "freshness_days_since_refresh": 0,
        "metrics": [
            {
                "label": f"{slug}_metric",
                "value": "100",
                "delta_sigma": mag,
                "is_held_over": False,
            },
        ],
    }


# ──────────────────────────────────────────────────────────────────────
# (a) Unavailable sections must NOT win lens against a fresh section
# ──────────────────────────────────────────────────────────────────────


def test_unavailable_sections_lose_to_fresh_section_midweek() -> None:
    """Mon–Thu: even with 4 unavailable sections at high σ-mag, the single
    fresh section wins because freshness=0.0 zeroes their product score.

    Mirrors the realistic Phase A.5 layout: fiscal/remit/comm/nbr unavailable,
    bb (banking) the only fresh signal."""
    today = date(2026, 5, 11)  # Monday
    sections = [
        _unavailable_section("fiscal", mag=2.0),
        _unavailable_section("remit", mag=2.0),
        _unavailable_section("comm", mag=2.0),
        _unavailable_section("nbr", mag=2.0),
        _fresh_section("bb", mag=1.0),
    ]

    lens, breakdown = score_lens(sections, today=today, previous_lens="banking")

    assert lens == "bb", (
        f"Fresh 'bb' must beat unavailable sections regardless of their σ-mag; "
        f"got lens={lens!r}, breakdown={breakdown}"
    )
    assert lens not in {"fiscal", "remit", "comm", "nbr"}
    # All unavailable sections score 0.0; bb scores > 0.
    for unavail_slug in ("fiscal", "remit", "comm", "nbr"):
        assert breakdown[unavail_slug]["score"] == 0.0, (
            f"{unavail_slug} should score 0.0 (freshness=0); breakdown={breakdown}"
        )
    assert breakdown["bb"]["score"] > 0.0


# ──────────────────────────────────────────────────────────────────────
# (b) All unavailable + previous_lens set → previous_lens fallback
# ──────────────────────────────────────────────────────────────────────


def test_all_unavailable_falls_back_to_previous_lens() -> None:
    """If every section is unavailable and held-over (mag=0), score_lens
    must fall back to previous_lens and tag breakdown.fallback='quiet_day'."""
    today = date(2026, 5, 11)  # Monday
    sections = [
        _unavailable_section("fiscal", mag=0.0),
        _unavailable_section("remit", mag=0.0),
        _unavailable_section("comm", mag=0.0),
        _unavailable_section("nbr", mag=0.0),
    ]

    lens, breakdown = score_lens(sections, today=today, previous_lens="iran")

    assert lens == "iran", f"Expected previous_lens fallback 'iran', got {lens!r}"
    assert breakdown.get("fallback") == "quiet_day", (
        f"breakdown.fallback should be 'quiet_day'; got {breakdown.get('fallback')!r}"
    )


# ──────────────────────────────────────────────────────────────────────
# (c) All unavailable + previous_lens=None → alphabetical first slug
# ──────────────────────────────────────────────────────────────────────


def test_all_unavailable_no_previous_lens_falls_back_to_alpha() -> None:
    """No previous lens to anchor to → alphabetically first slug wins,
    breakdown.fallback='quiet_day_alpha'."""
    today = date(2026, 5, 11)  # Monday
    sections = [
        _unavailable_section("remit", mag=0.0),
        _unavailable_section("comm", mag=0.0),
        _unavailable_section("nbr", mag=0.0),
        _unavailable_section("fiscal", mag=0.0),
    ]

    lens, breakdown = score_lens(sections, today=today, previous_lens=None)

    # Alphabetically first among {comm, fiscal, nbr, remit} is "comm".
    assert lens == "comm", (
        f"Expected alphabetically first slug 'comm', got {lens!r}; "
        f"breakdown={breakdown}"
    )
    assert breakdown.get("fallback") == "quiet_day_alpha", (
        f"breakdown.fallback should be 'quiet_day_alpha'; got {breakdown.get('fallback')!r}"
    )
