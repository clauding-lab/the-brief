"""Phase A — wire fiscal/remit builders into the V6 pipeline.

The builders already exist in brief/builders/ and produce valid
SectionData. Phase A:
  1. Register them in SPINE_BUILDER_IDS so gather() invokes them.
  2. Add them to V5_TO_V6 so _to_v6_raw forwards them to the editor.

Slots:
  - fiscal → ord 8, group "policy" (deliberately reserved between tbond/macro/iran)
  - remit  → ord 11, group "markets" (after iran=10)

Phase A also shipped `comm` at ord 12. v1.6.7 retired it — Gold moved into
`fx`, LNG went away with the section — so ord 12 is now a hole, and the
last test below pins the consequence: a section id the map does not know is
silently dropped by _to_v6_raw.

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
        ("fiscal", "fiscal", 8, "policy"),
        ("remit", "remit", 11, "markets"),
    ],
)
def test_v5_to_v6_contains_phase_a_section(
    v5_id: str, expected_slug: str, expected_ord: int, expected_group: str
) -> None:
    assert v5_id in pipeline_v6.V5_TO_V6, (
        f"V5_TO_V6 must contain {v5_id!r} — Phase A wires fiscal/remit into V6"
    )
    slug, ord_v6, group = pipeline_v6.V5_TO_V6[v5_id]
    assert slug == expected_slug, f"{v5_id}: slug should be {expected_slug!r}, got {slug!r}"
    assert ord_v6 == expected_ord, f"{v5_id}: ord should be {expected_ord}, got {ord_v6}"
    assert group == expected_group, f"{v5_id}: group should be {expected_group!r}, got {group!r}"


def test_v5_to_v6_ords_are_unique():
    """No two sections share an ord — section ordering in the SPA depends on it."""
    ords = [tup[1] for tup in pipeline_v6.V5_TO_V6.values()]
    assert len(ords) == len(set(ords)), f"V5_TO_V6 has duplicate ords: {sorted(ords)}"


# ──────────────────────────────────────────────────────────────────────
# SPINE_BUILDER_IDS registry
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("builder_id", ["fiscal", "remit"])
def test_spine_builder_ids_contains_phase_a(builder_id):
    assert builder_id in SPINE_BUILDER_IDS, (
        f"{builder_id!r} must be in SPINE_BUILDER_IDS — Phase A promotes it from "
        f"unregistered to spine (stable historical data, must ship daily)"
    )


# ──────────────────────────────────────────────────────────────────────
# _to_v6_raw integration — map flows through correctly
# ──────────────────────────────────────────────────────────────────────


def _section(section_id: str) -> SectionData:
    # Cadence is hardcoded "monthly" because _to_v6_raw is a pure
    # slug/ord/group/freshness/metrics passthrough — it does not branch on cadence.
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


def test_to_v6_raw_includes_fiscal_remit_alongside_existing_sections():
    """Build a list with banking + fiscal + remit + iranwar; assert all 4
    appear in _to_v6_raw output, sorted by ord ascending."""
    sections = [
        _section("banking"),  # ord 4
        _section("fiscal"),   # ord 8
        _section("iranwar"),  # ord 10 (mapped to slug "iran")
        _section("remit"),    # ord 11
    ]

    out = pipeline_v6._to_v6_raw(sections)

    slugs = [s["slug"] for s in out]
    assert slugs == ["banking", "fiscal", "iran", "remit"], (
        f"Output must include all 4 sections sorted by ord ascending; got {slugs}"
    )


def test_to_v6_raw_carries_fiscal_remit_slug_ord_group():
    """Each Phase A section retains the right slug/ord/group_key after transform."""
    sections = [_section("fiscal"), _section("remit")]
    out = pipeline_v6._to_v6_raw(sections)

    by_slug = {s["slug"]: s for s in out}

    assert by_slug["fiscal"]["ord"] == 8
    assert by_slug["fiscal"]["group_key"] == "policy"

    assert by_slug["remit"]["ord"] == 11
    assert by_slug["remit"]["group_key"] == "markets"


def test_to_v6_raw_output_sorted_by_ord_ascending():
    """Even with input order shuffled, output is ord-sorted (banking=4 first,
    remit=11 last)."""
    sections = [
        _section("remit"),    # ord 11
        _section("banking"),  # ord 4
        _section("fiscal"),   # ord 8
    ]
    out = pipeline_v6._to_v6_raw(sections)
    ords = [s["ord"] for s in out]
    assert ords == sorted(ords), f"_to_v6_raw output must be ord-sorted; got {ords}"
    assert ords == [4, 8, 11]


def test_to_v6_raw_drops_a_section_the_map_does_not_know():
    """`comm` was ord 12 until v1.6.7. The map is the gate: a SectionData whose
    id is absent from V5_TO_V6 does not reach the editor at all — it is not
    passed through with a default ord. This is why retiring a section means
    removing the map entry, not just the builder."""
    out = pipeline_v6._to_v6_raw([_section("fiscal"), _section("comm")])
    assert [s["slug"] for s in out] == ["fiscal"]
