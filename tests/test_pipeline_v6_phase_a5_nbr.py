"""Phase A.5 — wire the nbr builder into the V6 pipeline.

The nbr builder already exists in brief/builders/nbr.py and produces a valid
SectionData (3 monthly metrics: VAT, Income Tax, Customs — all NBR-sourced).
Phase A.5 wires it in alongside the Phase A trio (fiscal/remit/comm):

  1. Register "nbr" in SPINE_BUILDER_IDS so gather() invokes it.
  2. Add it to V5_TO_V6 so _to_v6_raw forwards it to the editor.

Slot:
  - nbr → ord 13, group "policy" (same group as fiscal — both are
    NBR/govt-revenue concerns)

These tests assert the registry + map shape (RED-phase contract) and the
end-to-end transformation through _to_v6_raw (GREEN-phase verification).
"""
from __future__ import annotations

from datetime import date

import pytest

from brief import pipeline_v6
from brief.builders import SPINE_BUILDER_IDS
from brief.schema import Metric, SectionData


# ──────────────────────────────────────────────────────────────────────
# V5_TO_V6 map — the slug/ord/group_key contract
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "v5_id, expected_slug, expected_ord, expected_group",
    [
        ("nbr", "nbr", 13, "policy"),
    ],
)
def test_v5_to_v6_contains_nbr_section(
    v5_id: str, expected_slug: str, expected_ord: int, expected_group: str
) -> None:
    assert v5_id in pipeline_v6.V5_TO_V6, (
        f"V5_TO_V6 must contain {v5_id!r} — Phase A.5 wires nbr into V6"
    )
    slug, ord_v6, group = pipeline_v6.V5_TO_V6[v5_id]
    assert slug == expected_slug, f"{v5_id}: slug should be {expected_slug!r}, got {slug!r}"
    assert ord_v6 == expected_ord, f"{v5_id}: ord should be {expected_ord}, got {ord_v6}"
    assert group == expected_group, f"{v5_id}: group should be {expected_group!r}, got {group!r}"


def test_v5_to_v6_ords_are_unique() -> None:
    """No two sections share an ord — section ordering in the SPA depends on it.

    Re-asserted here since Phase A.5 adds ord=13 — must remain unique.
    """
    ords = [tup[1] for tup in pipeline_v6.V5_TO_V6.values()]
    assert len(ords) == len(set(ords)), f"V5_TO_V6 has duplicate ords: {sorted(ords)}"


# ──────────────────────────────────────────────────────────────────────
# SPINE_BUILDER_IDS registry
# ──────────────────────────────────────────────────────────────────────


def test_nbr_in_spine_builder_ids() -> None:
    """nbr must be in SPINE_BUILDER_IDS — Phase A.5 promotes it from
    unregistered to spine (NBR posts monthly revenue collection numbers,
    must ship daily as last-known)."""
    assert "nbr" in SPINE_BUILDER_IDS, (
        "'nbr' must be in SPINE_BUILDER_IDS — Phase A.5 promotes it to spine"
    )


# ──────────────────────────────────────────────────────────────────────
# _to_v6_raw integration — map flows through correctly
# ──────────────────────────────────────────────────────────────────────


def _section(section_id: str) -> SectionData:
    """Build a minimal SectionData fixture; cadence is hardcoded "monthly"
    because _to_v6_raw is a pure slug/ord/group/freshness/metrics passthrough."""
    return SectionData(
        id=section_id,
        title=section_id.title(),
        kicker="",
        tldr="",
        pull="",
        freshness="fresh",
        freshness_reason="",
        metrics=[
            Metric(
                id=f"{section_id}_test",
                label="Test Metric",
                value="100",
                unit="pct",
                as_of=date(2026, 5, 8),
                source="EconDelta",
                cadence="monthly",
            ),
        ],
        news=[],
    )


def test_to_v6_raw_includes_nbr_alongside_phase_a_sections() -> None:
    """Build a list with banking + fiscal + remit + comm + nbr; assert all 5
    appear in _to_v6_raw output, sorted by ord ascending (nbr=13 last)."""
    sections = [
        _section("banking"),  # ord 4
        _section("fiscal"),   # ord 8
        _section("remit"),    # ord 11
        _section("comm"),     # ord 12
        _section("nbr"),      # ord 13
    ]

    out = pipeline_v6._to_v6_raw(sections)

    slugs = [s["slug"] for s in out]
    assert slugs == ["banking", "fiscal", "remit", "comm", "nbr"], (
        f"Output must include all 5 sections sorted by ord ascending; got {slugs}"
    )


def test_to_v6_raw_carries_nbr_slug_ord_group() -> None:
    """nbr retains the right slug/ord/group_key after transform."""
    sections = [_section("nbr")]
    out = pipeline_v6._to_v6_raw(sections)

    assert len(out) == 1
    nbr = out[0]
    assert nbr["slug"] == "nbr"
    assert nbr["ord"] == 13
    assert nbr["group_key"] == "policy"


def test_to_v6_raw_nbr_appears_after_comm() -> None:
    """Even with input order shuffled, nbr (ord=13) lands last among Phase A/A.5
    sections (comm=12)."""
    sections = [
        _section("nbr"),      # ord 13
        _section("fiscal"),   # ord 8
        _section("comm"),     # ord 12
        _section("remit"),    # ord 11
    ]
    out = pipeline_v6._to_v6_raw(sections)
    ords = [s["ord"] for s in out]
    assert ords == sorted(ords), f"_to_v6_raw output must be ord-sorted; got {ords}"
    assert ords == [8, 11, 12, 13]
    assert out[-1]["slug"] == "nbr"
