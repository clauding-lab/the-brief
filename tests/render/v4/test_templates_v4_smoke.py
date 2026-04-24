"""Parametrized smoke tests for all V4 generic section renderers (bb + 8 binders).

Each test checks:
  - The dom_id is present in output
  - The numeral is present
  - The kicker text is present (HTML-escaped where needed)
  - A metric-grid is present
  - BankerRead aside is present when bankerread is provided

This matrix catches import errors, wiring mistakes, and wrong meta assignments.
"""
from __future__ import annotations

import importlib
from datetime import date

import pytest

from brief.schema import BankerReadStructured, Delta, Metric, SectionData


# ---------------------------------------------------------------------------
# Fixture helper
# ---------------------------------------------------------------------------

def _make_minimal_section(sid: str) -> SectionData:
    """Create a minimal SectionData with one metric and one structured BankerRead."""
    return SectionData(
        id=sid,
        title=f"Smoke test section {sid}",
        freshness="fresh",
        metrics=[
            Metric(
                id=f"{sid}_metric",
                label="Key Metric",
                value=42.0,
                unit="%",
                as_of=date(2026, 4, 22),
                source="Test Source",
                cadence="monthly",
                delta=Delta(value=1.0, direction="up", window="mom"),
            ),
        ],
        bankerread=BankerReadStructured(
            meaning="Conditions are stable.",
            action="No action required.",
            trigger="Watch for deviation above threshold.",
            focus="Core metric remains the anchor.",
            pull="Stable.",
        ),
    )


# ---------------------------------------------------------------------------
# Parametrize matrix
# kicker strings that contain "&" are HTML-escaped in output — check both
# ---------------------------------------------------------------------------

_CASES = [
    (
        "bb",
        "brief.render.v4.templates.section_bb.render_section_bb",
        "02",
        "POLICY",          # partial match avoids &amp; escaping complexity
    ),
    (
        "banking",
        "brief.render.v4.templates.section_banking.render_section_banking",
        "03",
        "BANKING SECTOR",
    ),
    (
        "fx",
        "brief.render.v4.templates.section_fx.render_section_fx",
        "06",
        "FX",
    ),
    (
        "macro",
        "brief.render.v4.templates.section_macro.render_section_macro",
        "07",
        "MACRO INDICATORS",
    ),
    (
        "dam",
        "brief.render.v4.templates.section_dam.render_section_dam",
        "08",
        "FOOD PRICES",
    ),
    (
        "comm",
        "brief.render.v4.templates.section_comm.render_section_comm",
        "09",
        "GLOBAL COMMODITIES",
    ),
    (
        "remit",
        "brief.render.v4.templates.section_remit.render_section_remit",
        "10",
        "REMITTANCES",
    ),
    (
        "fiscal",
        "brief.render.v4.templates.section_fiscal.render_section_fiscal",
        "15",
        "FISCAL",
    ),
    (
        "nbr",
        "brief.render.v4.templates.section_nbr.render_section_nbr",
        "16",
        "TAX REVENUE",
    ),
]


@pytest.mark.parametrize(
    "sid,renderer_path,expected_numeral,expected_kicker_fragment",
    _CASES,
    ids=[c[0] for c in _CASES],
)
def test_section_smoke(
    sid: str,
    renderer_path: str,
    expected_numeral: str,
    expected_kicker_fragment: str,
) -> None:
    """Generic smoke test: dom_id, numeral, kicker, metric-grid, bankerread."""
    section = _make_minimal_section(sid)
    module_path, func_name = renderer_path.rsplit(".", 1)
    fn = getattr(importlib.import_module(module_path), func_name)
    html = fn(section)

    # dom_id
    assert f'id="section-{sid}"' in html, f"Missing id=section-{sid}"

    # numeral
    assert expected_numeral in html, f"Missing numeral {expected_numeral}"

    # kicker fragment (partial match — avoids &amp; ambiguity)
    assert expected_kicker_fragment in html, (
        f"Missing kicker fragment {expected_kicker_fragment!r}"
    )

    # metric grid present
    assert 'class="metric-grid"' in html or "metric-card" in html, (
        "No metric-grid or metric-card found"
    )

    # bankerread present (section has a BankerRead in fixture)
    assert "bankerread" in html, "Missing bankerread aside"


@pytest.mark.parametrize(
    "sid,renderer_path,_numeral,_kicker",
    _CASES,
    ids=[f"{c[0]}-unavailable" for c in _CASES],
)
def test_section_smoke_unavailable(
    sid: str,
    renderer_path: str,
    _numeral: str,
    _kicker: str,
) -> None:
    """When freshness=unavailable only the unavailable shell renders."""
    section = _make_minimal_section(sid)
    # Override freshness to unavailable (must rebuild because Pydantic model)
    section = SectionData(
        **{**section.model_dump(), "freshness": "unavailable"}
    )
    module_path, func_name = renderer_path.rsplit(".", 1)
    fn = getattr(importlib.import_module(module_path), func_name)
    html = fn(section)

    assert "Section Unavailable" in html
    assert "section-unavailable" in html
    assert "Key Metric" not in html
    assert "bankerread" not in html
