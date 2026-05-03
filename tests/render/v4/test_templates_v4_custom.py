"""Tests for V4 custom section templates: DSE, TBond, IranWar.

TDD pattern: fixtures first, assertions based on expected HTML structure.
"""
from __future__ import annotations

from datetime import date

import pytest

from brief.schema import Metric, SectionData
from brief.render.v4.templates.section_dse import render_section_dse
from brief.render.v4.templates.section_tbond import render_section_tbond
from brief.render.v4.templates.section_iranwar import render_section_iranwar


# ---------------------------------------------------------------------------
# DSE fixtures
# ---------------------------------------------------------------------------

_DSE_DEFAULT_EXTRAS = {
    "sector_heat": [
        {"name": "Banks", "pct": 0.85},
        {"name": "NBFI", "pct": -0.42},
        {"name": "Textile", "pct": -1.12},
        {"name": "Pharma", "pct": 0.31},
        {"name": "Fuel", "pct": -0.08},
        {"name": "Telecom", "pct": 0.00},
        {"name": "Food", "pct": 0.22},
        {"name": "IT", "pct": 1.45},
    ],
}


def _dse_section(
    degraded_breadth: bool = False,
    degraded_sector_heat: bool = False,
    extras: dict | None = None,
    **kwargs,
) -> SectionData:
    # extras=None → use defaults; extras={...} → use exactly what was passed (no merge)
    resolved_extras = dict(_DSE_DEFAULT_EXTRAS) if extras is None else extras
    return SectionData(
        id="dse",
        title="Dhaka Stock Exchange",
        freshness=kwargs.pop("freshness", "fresh"),
        metrics=[
            Metric(
                id="dse_close",
                label="DSEX",
                value=5420.75,
                unit="pts",
                as_of=date(2026, 4, 24),
                source="DSE",
                cadence="daily",
            ),
            Metric(
                id="dse_advancing",
                label="Advancing",
                value=74,
                unit="",
                as_of=date(2026, 4, 24),
                source="DSE",
                cadence="daily",
            ),
            Metric(
                id="dse_declining",
                label="Declining",
                value=162,
                unit="",
                as_of=date(2026, 4, 24),
                source="DSE",
                cadence="daily",
            ),
            Metric(
                id="dse_unchanged",
                label="Unchanged",
                value=58,
                unit="",
                as_of=date(2026, 4, 24),
                source="DSE",
                cadence="daily",
            ),
        ],
        pull="Breadth skewed to decliners.",
        degraded_breadth=degraded_breadth,
        degraded_sector_heat=degraded_sector_heat,
        extras=resolved_extras,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# TBond fixture
# ---------------------------------------------------------------------------

def _tbond_section(**kwargs) -> SectionData:
    return SectionData(
        id="tbond",
        title="T-Bill & T-Bond",
        freshness=kwargs.pop("freshness", "fresh"),
        metrics=[
            Metric(
                id=f"tbond_{t.lower()}_yield",
                label=f"{t} Yield",
                value=7.5 + i * 0.3,
                unit="%",
                as_of=date(2026, 4, 24),
                source="BB",
                cadence="weekly",
            )
            for i, t in enumerate(["3M", "6M", "1Y", "2Y", "5Y", "10Y"])
        ],
        pull="Curve bear-steepened.",
        extras={
            "prev_week_yields": {
                "3M": 7.4,
                "6M": 7.7,
                "1Y": 8.0,
                "2Y": 8.3,
                "5Y": 8.6,
                "10Y": 8.9,
            }
        },
        **kwargs,
    )


# ---------------------------------------------------------------------------
# IranWar fixture
# ---------------------------------------------------------------------------

def _iranwar_section(**kwargs) -> SectionData:
    return SectionData(
        id="iranwar",
        title="US-Iran War Impact",
        freshness=kwargs.pop("freshness", "fresh"),
        metrics=[
            Metric(
                id="brent_spot",
                label="Brent",
                value=87.40,
                unit="USD/bbl",
                as_of=date(2026, 4, 24),
                source="Oilprice",
                cadence="daily",
            ),
        ],
        pull="Hormuz tension keeps oil watch active.",
        extras={
            "brent_12_sessions": [
                82.1, 83.5, 85.2, 86.0, 85.8, 87.1,
                86.4, 87.0, 88.2, 87.9, 87.6, 87.40,
            ],
            "oil_events": [
                {"date": "2026-04-15", "label": "IAEA report", "hotness": "cold"},
                {"date": "2026-04-19", "label": "OPEC+ hold", "hotness": "cold"},
                {"date": "2026-04-23", "label": "Hormuz tanker", "hotness": "hot"},
            ],
        },
        **kwargs,
    )


# ===========================================================================
# DSE tests
# ===========================================================================

class TestDSEHappyPath:
    def test_breadth_block_rendered(self) -> None:
        html = render_section_dse(_dse_section())
        assert "dse-breadth" in html

    def test_advancing_count_in_breadth(self) -> None:
        html = render_section_dse(_dse_section())
        assert "ADVANCING" in html
        assert "74" in html

    def test_declining_count_in_breadth(self) -> None:
        html = render_section_dse(_dse_section())
        assert "DECLINING" in html
        assert "162" in html

    def test_unchanged_count_in_breadth(self) -> None:
        html = render_section_dse(_dse_section())
        assert "UNCHANGED" in html
        assert "58" in html

    def test_sector_heat_rendered(self) -> None:
        html = render_section_dse(_dse_section())
        assert "dse-sector-heat" in html

    def test_sector_heat_tiles_present(self) -> None:
        html = render_section_dse(_dse_section())
        assert "sector-tile" in html
        assert "Banks" in html

    def test_pos_tile_class(self) -> None:
        html = render_section_dse(_dse_section())
        assert "tile-pos" in html

    def test_neg_tile_class(self) -> None:
        html = render_section_dse(_dse_section())
        assert "tile-neg" in html

    def test_section_id_present(self) -> None:
        html = render_section_dse(_dse_section())
        assert 'id="section-dse"' in html

    def test_numeral_04_in_head(self) -> None:
        html = render_section_dse(_dse_section())
        assert "04" in html


class TestDSEDegraded:
    def test_breadth_degraded_no_breadth_block(self) -> None:
        html = render_section_dse(_dse_section(degraded_breadth=True))
        assert "dse-breadth" not in html

    def test_breadth_degraded_sector_heat_still_renders(self) -> None:
        html = render_section_dse(_dse_section(degraded_breadth=True))
        assert "dse-sector-heat" in html

    def test_sector_heat_degraded_no_heatmap(self) -> None:
        html = render_section_dse(_dse_section(degraded_sector_heat=True))
        assert "dse-sector-heat" not in html

    def test_sector_heat_degraded_breadth_still_renders(self) -> None:
        html = render_section_dse(_dse_section(degraded_sector_heat=True))
        assert "dse-breadth" in html

    def test_both_degraded_no_custom_blocks(self) -> None:
        html = render_section_dse(_dse_section(degraded_breadth=True, degraded_sector_heat=True))
        assert "dse-breadth" not in html
        assert "dse-sector-heat" not in html

    def test_both_degraded_metric_grid_still_renders(self) -> None:
        html = render_section_dse(_dse_section(degraded_breadth=True, degraded_sector_heat=True))
        assert "metric-grid" in html


class TestDSEUnavailable:
    def test_unavailable_returns_minimal_html(self) -> None:
        section = _dse_section(freshness="unavailable")
        html = render_section_dse(section)
        assert "Section Unavailable" in html

    def test_unavailable_no_breadth(self) -> None:
        section = _dse_section(freshness="unavailable")
        html = render_section_dse(section)
        assert "dse-breadth" not in html

    def test_unavailable_no_heatmap(self) -> None:
        section = _dse_section(freshness="unavailable")
        html = render_section_dse(section)
        assert "dse-sector-heat" not in html


class TestDSESectorHeatMissing:
    def test_empty_sector_heat_no_heatmap(self) -> None:
        section = _dse_section(extras={"sector_heat": []})
        html = render_section_dse(section)
        assert "dse-sector-heat" not in html

    def test_sector_heat_absent_in_extras_no_heatmap(self) -> None:
        section = _dse_section(extras={})
        html = render_section_dse(section)
        assert "dse-sector-heat" not in html


# ===========================================================================
# TBond tests
# ===========================================================================

class TestTBondYieldCurve:
    def test_svg_rendered(self) -> None:
        html = render_section_tbond(_tbond_section())
        assert "<svg" in html
        assert "yield-curve-svg" in html

    def test_six_tenor_labels_present(self) -> None:
        html = render_section_tbond(_tbond_section())
        for tenor in ["3M", "6M", "1Y", "2Y", "5Y", "10Y"]:
            assert tenor in html, f"Missing tenor label: {tenor}"

    def test_oxblood_solid_current_curve(self) -> None:
        html = render_section_tbond(_tbond_section())
        assert "var(--ox)" in html

    def test_dashed_prev_week_curve_present(self) -> None:
        html = render_section_tbond(_tbond_section())
        assert "stroke-dasharray" in html

    def test_no_prev_week_no_dashed_curve(self) -> None:
        section = _tbond_section()
        section.extras.pop("prev_week_yields", None)
        html = render_section_tbond(section)
        assert "<svg" in html
        assert "stroke-dasharray" not in html

    def test_ink4_stroke_for_prev_curve(self) -> None:
        html = render_section_tbond(_tbond_section())
        assert "var(--ink-4)" in html

    def test_section_id_present(self) -> None:
        html = render_section_tbond(_tbond_section())
        assert 'id="section-tbond"' in html

    def test_numeral_05_in_head(self) -> None:
        html = render_section_tbond(_tbond_section())
        assert "05" in html

    def test_legend_present(self) -> None:
        html = render_section_tbond(_tbond_section())
        assert "This week" in html

    def test_prev_legend_when_prev_present(self) -> None:
        html = render_section_tbond(_tbond_section())
        assert "Last week" in html

    def test_unavailable_no_svg(self) -> None:
        section = _tbond_section(freshness="unavailable")
        html = render_section_tbond(section)
        assert "Section Unavailable" in html
        assert "yield-curve-svg" not in html


# ===========================================================================
# IranWar tests
# ===========================================================================

class TestIranWarOilChart:
    def test_svg_rendered(self) -> None:
        html = render_section_iranwar(_iranwar_section())
        assert "<svg" in html
        assert "oil-chart-svg" in html

    def test_12_point_line_polyline_present(self) -> None:
        html = render_section_iranwar(_iranwar_section())
        assert "polyline" in html
        assert "var(--ink-2)" in html

    def test_event_pins_count(self) -> None:
        html = render_section_iranwar(_iranwar_section())
        # 3 events → 3 pin labels
        assert html.count("oil-pin-label") == 3

    def test_hot_pin_class(self) -> None:
        html = render_section_iranwar(_iranwar_section())
        assert "pin-hot" in html

    def test_cold_pins_class(self) -> None:
        html = render_section_iranwar(_iranwar_section())
        assert "pin-cold" in html

    def test_hot_pin_uses_ox_stroke(self) -> None:
        html = render_section_iranwar(_iranwar_section())
        assert "var(--ox)" in html

    def test_cold_pin_uses_ink3_stroke(self) -> None:
        html = render_section_iranwar(_iranwar_section())
        assert "var(--ink-3)" in html

    def test_event_labels_present(self) -> None:
        html = render_section_iranwar(_iranwar_section())
        assert "IAEA report" in html
        assert "OPEC+ hold" in html
        assert "Hormuz tanker" in html

    def test_section_id_present(self) -> None:
        html = render_section_iranwar(_iranwar_section())
        assert 'id="section-iranwar"' in html

    def test_numeral_14_in_head(self) -> None:
        html = render_section_iranwar(_iranwar_section())
        assert "14" in html

    def test_no_brent_sessions_no_svg(self) -> None:
        section = _iranwar_section()
        section.extras.pop("brent_12_sessions", None)
        html = render_section_iranwar(section)
        assert "oil-chart-svg" not in html

    def test_unavailable_no_chart(self) -> None:
        section = _iranwar_section(freshness="unavailable")
        html = render_section_iranwar(section)
        assert "Section Unavailable" in html
        assert "oil-chart-svg" not in html
