"""Tests for risk_map and flow_index V4 templates."""
from __future__ import annotations

from datetime import date

import pytest

from brief.schema import MapCoord, Metric, SectionData
from brief.render.v4.templates.risk_map import render_risk_map
from brief.render.v4.templates.flow_index import render_flow_index


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_12_coords() -> list[MapCoord]:
    ids = ["bb", "macro", "fx", "remit", "dse", "tbond", "iranwar", "headlines", "comm", "banking", "dam", "fiscal"]
    types = ["anchor", "anchor", "fresh", "slow", "fresh", "slow", "event", "fresh", "slow", "fresh", "slow", "slow"]
    # Use evenly spaced x values 0.0, 0.9, 1.8, ... 9.9 so all stay within [0, 10]
    xs = [round(i * 10 / 11, 2) for i in range(12)]
    return [
        MapCoord(
            section_id=sid,
            x=xs[i],
            y=round(10 - xs[i], 2),
            r=30,
            type=t,
            hero_metric_id=None,
        )
        for i, (sid, t) in enumerate(zip(ids, types))
    ]


def _make_sections() -> dict[str, SectionData]:
    sids = ["bb", "macro", "fx", "remit", "dse", "tbond", "iranwar", "headlines", "comm", "banking", "dam", "fiscal"]
    return {
        sid: SectionData(
            id=sid,
            title=sid.upper(),
            freshness="fresh",
            metrics=[
                Metric(
                    id=f"{sid}_m1",
                    label="Test Metric",
                    value=1.0,
                    unit="pct",
                    as_of=date(2026, 4, 24),
                    source="Test",
                    cadence="daily",
                )
            ],
        )
        for sid in sids
    }


# ---------------------------------------------------------------------------
# render_risk_map tests
# ---------------------------------------------------------------------------

class TestRenderRiskMap:
    def test_twelve_coords_produces_twelve_dots(self) -> None:
        """Happy path: 12 coords → exactly 12 <circle elements with class map-dot."""
        coords = _make_12_coords()
        sections = _make_sections()
        result = render_risk_map(coords, sections, read_order=list(sections.keys()))
        assert result.count('<circle') == 12
        assert result.count('class="map-dot') == 12

    def test_axis_labels_present(self) -> None:
        """SVG contains both axis label texts."""
        coords = _make_12_coords()
        sections = _make_sections()
        result = render_risk_map(coords, sections)
        assert "Movement today" in result
        assert "Significance for the book" in result

    def test_dot_type_class_names_are_distinct(self) -> None:
        """Each type produces a distinct CSS class on the dot element."""
        coords = _make_12_coords()
        sections = _make_sections()
        result = render_risk_map(coords, sections)
        # All four types are present in the fixture
        assert "rm-dot-event" in result
        assert "rm-dot-fresh" in result
        assert "rm-dot-slow" in result
        assert "rm-dot-anchor" in result

    def test_detail_pane_renders_lead_section(self) -> None:
        """Detail pane shows lead section title and at least one metric."""
        coords = _make_12_coords()
        sections = _make_sections()
        read_order = ["iranwar", "bb", "macro"]
        result = render_risk_map(coords, sections, read_order=read_order)
        # Lead is iranwar — its title (IRANWAR) should be in detail pane
        assert "IRANWAR" in result
        # At least one metric label should appear in detail
        assert "Test Metric" in result

    def test_empty_coords_no_dots_fallback_message(self) -> None:
        """Empty coords → SVG container present, 0 circles, fallback message shown."""
        result = render_risk_map([], {})
        assert "risk-map" in result
        assert "<circle" not in result
        assert "Click a dot for details" in result

    def test_svg_structure_present(self) -> None:
        """SVG element with correct class and role is present."""
        coords = _make_12_coords()
        sections = _make_sections()
        result = render_risk_map(coords, sections)
        assert '<svg class="risk-map-svg map-svg"' in result
        assert 'role="img"' in result
        assert 'aria-label="Risk Map"' in result

    def test_section_id_in_data_attribute(self) -> None:
        """Each dot carries its section_id in data-section attribute."""
        coords = _make_12_coords()
        sections = _make_sections()
        result = render_risk_map(coords, sections)
        for mc in coords:
            assert f'data-section="{mc.section_id}"' in result

    def test_empty_read_order_shows_fallback(self) -> None:
        """Empty read_order → fallback message in detail pane."""
        coords = _make_12_coords()
        sections = _make_sections()
        result = render_risk_map(coords, sections, read_order=[])
        assert "Click a dot for details" in result

    def test_fewer_than_twelve_coords(self) -> None:
        """Render whatever length is passed — 5 coords → 5 dots."""
        coords = _make_12_coords()[:5]
        sections = _make_sections()
        result = render_risk_map(coords, sections)
        assert result.count("<circle") == 5


# ---------------------------------------------------------------------------
# render_flow_index tests
# ---------------------------------------------------------------------------

class TestRenderFlowIndex:
    def test_twelve_entries_with_correct_anchors(self) -> None:
        """12 entries → 12 <li class='flow-entry'> elements, all anchors start with #section-."""
        read_order = ["bb", "macro", "fx", "remit", "dse", "tbond", "iranwar", "headlines", "comm", "banking", "dam", "fiscal"]
        sections = _make_sections()
        result = render_flow_index(read_order, sections)
        assert result.count('class="flow-entry"') == 12
        for sid in read_order:
            assert f'href="#section-{sid}"' in result

    def test_rank_numerals_zero_padded(self) -> None:
        """Ranks 01 through 12 are present (zero-padded)."""
        read_order = ["bb", "macro", "fx", "remit", "dse", "tbond", "iranwar", "headlines", "comm", "banking", "dam", "fiscal"]
        sections = _make_sections()
        result = render_flow_index(read_order, sections)
        for i in range(1, 13):
            assert f"{i:02d}" in result

    def test_read_order_respected_first_entry(self) -> None:
        """First entry matches read_order[0]."""
        read_order = ["iranwar", "bb", "macro", "fx", "remit", "dse", "tbond", "headlines", "comm", "banking", "dam", "fiscal"]
        sections = _make_sections()
        result = render_flow_index(read_order, sections)
        # §14 · IRANWAR should appear as first kicker
        assert "§14 · IRANWAR" in result
        # 01 rank should be assigned to iranwar
        first_entry_idx = result.index("flow-entry")
        # The first flow-entry should contain rank 01
        first_chunk = result[first_entry_idx: first_entry_idx + 300]
        assert "01" in first_chunk

    def test_missing_sid_renders_fallback_without_crash(self) -> None:
        """Unknown sid not in sections dict renders without crashing."""
        read_order = ["bb", "unknown_section"]
        sections = _make_sections()  # unknown_section not present
        result = render_flow_index(read_order, sections)
        # Should still have 2 entries
        assert result.count('class="flow-entry"') == 2
        # The unknown section renders with sid-derived fallback
        assert "UNKNOWN_SECTION" in result
        assert 'href="#section-unknown_section"' in result

    def test_section_numerals_correct(self) -> None:
        """Section numeral mapping is correct for bb, dse, iranwar, headlines."""
        read_order = ["bb", "dse", "iranwar", "headlines"]
        sections = _make_sections()
        result = render_flow_index(read_order, sections)
        assert "§02 · BB" in result
        assert "§04 · DSE" in result
        assert "§14 · IRANWAR" in result
        assert "§01 · HEADLINES" in result

    def test_unknown_numeral_fallback(self) -> None:
        """sid not in _SECTION_NUMERAL gets em-dash numeral fallback."""
        read_order = ["novelid"]
        # build a sections dict that has this sid
        sections = {
            "novelid": SectionData(
                id="novelid",
                title="Novel Section",
                freshness="fresh",
                metrics=[],
            )
        }
        result = render_flow_index(read_order, sections)
        # em-dash as numeral: §— · NOVEL SECTION
        assert "§—" in result
        assert "NOVEL SECTION" in result

    def test_section_title_used_when_present(self) -> None:
        """section.title is used for flow-title span."""
        read_order = ["bb"]
        sections = {
            "bb": SectionData(
                id="bb",
                title="Bangladesh Bank",
                freshness="fresh",
                metrics=[],
            )
        }
        result = render_flow_index(read_order, sections)
        assert "Bangladesh Bank" in result
