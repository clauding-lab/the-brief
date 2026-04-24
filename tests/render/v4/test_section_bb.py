"""Tests for V4 section_bb canonical template.

TDD: these tests were written first (RED), then section_bb.py implemented (GREEN).
After the Commit-2 refactor (section_bb delegates to _generic), all 10 tests
must still pass without modification.
"""
from __future__ import annotations

import html
from datetime import date

import pytest

from brief.schema import BankerReadStructured, Delta, Metric, SectionData
from brief.render.v4.templates.section_bb import render_section_bb


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

def _bb_section(**overrides) -> SectionData:
    base: dict = dict(
        id="bb",
        title="Bangladesh Bank",
        freshness="fresh",
        metrics=[
            Metric(
                id="policy_rate",
                label="Policy Rate",
                value=10.00,
                unit="%",
                as_of=date(2026, 4, 22),
                source="Bangladesh Bank",
                cadence="event",
                delta=Delta(value=0.0, direction="flat", window="mom"),
                hero=True,
            ),
            Metric(
                id="reserves_total",
                label="Reserves (Gross)",
                value=20.5,
                unit="bn USD",
                as_of=date(2026, 4, 22),
                source="Bangladesh Bank",
                cadence="daily",
                delta=Delta(value=0.3, direction="up", window="wow"),
            ),
            Metric(
                id="cpi_headline",
                label="CPI (yoy)",
                value=9.1,
                unit="%",
                as_of=date(2026, 3, 31),
                source="BBS",
                cadence="monthly",
                delta=Delta(value=0.2, direction="down", window="mom"),
            ),
        ],
        pull="Policy steady; reserves stable; inflation sticky.",
        bankerread=BankerReadStructured(
            meaning="Policy is on hold; inflation remains above target.",
            action="Hold duration; watch the next CPI print closely.",
            trigger="A CPI surprise >9.5% or USD/BDT > 122 triggers reassessment.",
            focus="Reserves floor at 20bn; policy rate 10% — twin anchors.",
            pull="Policy steady; reserves stable.",
        ),
    )
    base.update(overrides)
    return SectionData(**base)


# ---------------------------------------------------------------------------
# Test 1: structural landmarks
# ---------------------------------------------------------------------------

def test_section_bb_structural_landmarks():
    """Output contains section id, numeral, kicker, and title text."""
    out = render_section_bb(_bb_section())
    assert 'id="section-bb"' in out
    assert "02" in out
    assert "POLICY &amp; RATES" in out or "POLICY & RATES" in out
    assert "Bangladesh Bank" in out


# ---------------------------------------------------------------------------
# Test 2: all three metrics render
# ---------------------------------------------------------------------------

def test_section_bb_all_metrics_render():
    """All three metric labels and values appear in the output."""
    out = render_section_bb(_bb_section())
    # Labels
    assert "Policy Rate" in out
    assert "Reserves (Gross)" in out
    assert "CPI (yoy)" in out
    # Values (fmt_num wraps in span.num — check raw number text too)
    assert "10.00" in out
    assert "20.50" in out
    assert "9.10" in out


# ---------------------------------------------------------------------------
# Test 3: hero metric gets metric-hero class
# ---------------------------------------------------------------------------

def test_section_bb_hero_metric_class():
    """The hero metric (policy_rate) renders with metric-hero class."""
    out = render_section_bb(_bb_section())
    assert "metric-hero" in out


# ---------------------------------------------------------------------------
# Test 4: pull quote rendered
# ---------------------------------------------------------------------------

def test_section_bb_pull_quote():
    """Pull quote text appears inside a pull-quote blockquote."""
    out = render_section_bb(_bb_section())
    assert "pull-quote" in out
    assert "Policy steady; reserves stable; inflation sticky." in out


# ---------------------------------------------------------------------------
# Test 5: BankerRead aside with all four fields
# ---------------------------------------------------------------------------

def test_section_bb_bankerread_fields():
    """BankerRead aside renders all four §A/§B/§C/§D sections."""
    out = render_section_bb(_bb_section())
    assert "§A" in out
    assert "§B" in out
    assert "§C" in out
    assert "§D" in out
    # §A meaning: drop-cap splits first letter so search for the rest of the phrase
    assert "olicy is on hold" in out
    assert "Hold duration" in out
    assert "CPI surprise" in out
    assert "Reserves floor" in out


# ---------------------------------------------------------------------------
# Test 6: cadence pills
# ---------------------------------------------------------------------------

def test_section_bb_cadence_pills():
    """EVENT, DAILY and MONTHLY cadence pills are all present."""
    out = render_section_bb(_bb_section())
    assert "EVENT" in out
    assert "DAILY" in out
    assert "MONTHLY" in out


# ---------------------------------------------------------------------------
# Test 7: delta arrows
# ---------------------------------------------------------------------------

def test_section_bb_delta_arrows():
    """All three delta direction arrows are present."""
    out = render_section_bb(_bb_section())
    assert "▲" in out   # up  (reserves)
    assert "▼" in out   # down (cpi)
    assert "–" in out   # flat (policy rate)


# ---------------------------------------------------------------------------
# Test 8: unavailable freshness
# ---------------------------------------------------------------------------

def test_section_bb_unavailable_freshness():
    """When freshness=unavailable only the unavailable message appears."""
    out = render_section_bb(_bb_section(freshness="unavailable"))
    assert "Section Unavailable" in out
    # No metric data, no bankerread, no pull quote
    assert "Policy Rate" not in out
    assert "bankerread" not in out
    assert "pull-quote" not in out
    assert "section-unavailable" in out


# ---------------------------------------------------------------------------
# Test 9: no bankerread when bankerread=None
# ---------------------------------------------------------------------------

def test_section_bb_no_bankerread():
    """When bankerread=None the section renders without any bankerread aside."""
    out = render_section_bb(_bb_section(bankerread=None, pull=None))
    assert "section-bb" in out
    assert "bankerread" not in out
    # Metrics still appear
    assert "Policy Rate" in out


# ---------------------------------------------------------------------------
# Test 10: HTML escaping of user content
# ---------------------------------------------------------------------------

def test_section_bb_html_escape():
    """User-supplied content is HTML-escaped to prevent XSS."""
    evil = "<script>alert(1)</script>"
    out = render_section_bb(_bb_section(pull=evil))
    assert "&lt;script&gt;" in out
    assert "<script>" not in out
