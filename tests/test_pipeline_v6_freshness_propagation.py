"""Phase D.2 — verify per-section freshness propagates from V5 SectionData
through the V6 publish pipeline so the SPA can collapse dead sections.

Coverage:
  1. SectionV6 schema accepts the new `freshness` field (Literal),
     remains optional for backward-compat with pre-D.2 issues, and
     rejects bad values.
  2. _stamp_freshness helper enriches `final_brief.sections[i].freshness`
     in-place by slug lookup against the V6-shape raw_sections list
     emitted by `_to_v6_raw`.
  3. Round-trip: _to_v6_raw → _stamp_freshness preserves V5 freshness
     values onto the schema-validated final brief.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from brief import pipeline_v6
from brief.schema import Metric, SectionData
from brief.v6_schema import BriefPayloadV6, BriefV6, SectionV6


# ─── Fixtures ──────────────────────────────────────────────────────────


def _make_section_v6(slug: str, freshness: str | None = None) -> SectionV6:
    """Build a minimal valid SectionV6 for tests; freshness defaults to None."""
    kwargs: dict[str, Any] = {
        "slug": slug,
        "ord": 2,
        "title": f"Section {slug.upper()}",
        "group_key": "overview",
        "weight": 1,
    }
    if freshness is not None:
        kwargs["freshness"] = freshness
    return SectionV6(**kwargs)


def _make_brief_payload(sections: list[SectionV6]) -> BriefPayloadV6:
    """Wrap sections in a minimal valid BriefPayloadV6."""
    return BriefPayloadV6(
        brief=BriefV6(issue_no=1, volume=1, brief_date=date(2026, 5, 8)),
        sections=sections,
    )


# ─── Schema-level tests ────────────────────────────────────────────────


def test_section_v6_accepts_freshness_field() -> None:
    """SectionV6(freshness='fresh') round-trips through dump/validate cleanly."""
    section: SectionV6 = SectionV6(
        slug="bb",
        ord=3,
        title="Bangladesh Bank",
        group_key="banking",
        freshness="fresh",
    )
    assert section.freshness == "fresh"

    dumped: dict[str, Any] = section.model_dump(mode="json")
    assert dumped["freshness"] == "fresh"

    revalidated: SectionV6 = SectionV6.model_validate(dumped)
    assert revalidated.freshness == "fresh"


def test_section_v6_accepts_none_freshness() -> None:
    """Backward-compat — pre-D.2 issues without freshness still validate."""
    # Constructed via kwargs that omit freshness entirely
    section: SectionV6 = SectionV6(
        slug="bb",
        ord=3,
        title="Bangladesh Bank",
        group_key="banking",
    )
    assert section.freshness is None

    # And from a dict missing the key
    dict_input: dict[str, Any] = {
        "slug": "bb",
        "ord": 3,
        "title": "Bangladesh Bank",
        "group_key": "banking",
    }
    revalidated: SectionV6 = SectionV6.model_validate(dict_input)
    assert revalidated.freshness is None


def test_section_v6_rejects_invalid_freshness() -> None:
    """Bogus freshness values raise ValidationError (catches prompt drift / data bugs)."""
    with pytest.raises(ValidationError):
        SectionV6(
            slug="bb",
            ord=3,
            title="Bangladesh Bank",
            group_key="banking",
            freshness="bogus",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "freshness_value",
    ["fresh", "warning", "stale", "unavailable", "warming_up"],
)
def test_section_v6_accepts_all_freshness_kinds(freshness_value: str) -> None:
    """Every Literal value in FreshnessKind validates."""
    section: SectionV6 = SectionV6(
        slug="bb",
        ord=3,
        title="Bangladesh Bank",
        group_key="banking",
        freshness=freshness_value,  # type: ignore[arg-type]
    )
    assert section.freshness == freshness_value


# ─── _stamp_freshness helper tests ─────────────────────────────────────


def test_stamp_freshness_enriches_by_slug() -> None:
    """Each section's freshness is filled in from raw_sections by slug lookup."""
    sections: list[SectionV6] = [
        _make_section_v6("bb"),
        _make_section_v6("fx"),
        _make_section_v6("dse"),
    ]
    final_brief: BriefPayloadV6 = _make_brief_payload(sections)
    raw_sections: list[dict[str, Any]] = [
        {"slug": "bb", "freshness": "fresh"},
        {"slug": "fx", "freshness": "warning"},
        {"slug": "dse", "freshness": "stale"},
    ]

    pipeline_v6._stamp_freshness(final_brief, raw_sections)

    by_slug: dict[str, SectionV6] = {s.slug: s for s in final_brief.sections}
    assert by_slug["bb"].freshness == "fresh"
    assert by_slug["fx"].freshness == "warning"
    assert by_slug["dse"].freshness == "stale"


def test_stamp_freshness_handles_missing_slug() -> None:
    """A final_brief slug not present in raw_sections leaves freshness as None
    (defensive — should never happen given _to_v6_raw is the only producer).
    """
    sections: list[SectionV6] = [
        _make_section_v6("bb"),
        _make_section_v6("ghost"),  # not in raw_sections
    ]
    final_brief: BriefPayloadV6 = _make_brief_payload(sections)
    raw_sections: list[dict[str, Any]] = [
        {"slug": "bb", "freshness": "fresh"},
    ]

    pipeline_v6._stamp_freshness(final_brief, raw_sections)

    by_slug: dict[str, SectionV6] = {s.slug: s for s in final_brief.sections}
    assert by_slug["bb"].freshness == "fresh"
    assert by_slug["ghost"].freshness is None


def test_stamp_freshness_does_not_mutate_other_fields() -> None:
    """Stamping freshness leaves title, weight, ord, group_key, etc. untouched."""
    section: SectionV6 = SectionV6(
        slug="bb",
        ord=3,
        title="Bangladesh Bank",
        group_key="banking",
        weight=2,
        verdict="Reserves stable",
        verdict_tone="neu",
        tldr="BDT pegged at 110.5",
    )
    final_brief: BriefPayloadV6 = _make_brief_payload([section])
    raw_sections: list[dict[str, Any]] = [
        {"slug": "bb", "freshness": "fresh"},
    ]

    pipeline_v6._stamp_freshness(final_brief, raw_sections)

    bb: SectionV6 = final_brief.sections[0]
    assert bb.freshness == "fresh"
    # All other fields preserved
    assert bb.slug == "bb"
    assert bb.ord == 3
    assert bb.title == "Bangladesh Bank"
    assert bb.group_key == "banking"
    assert bb.weight == 2
    assert bb.verdict == "Reserves stable"
    assert bb.verdict_tone == "neu"
    assert bb.tldr == "BDT pegged at 110.5"


def test_stamp_freshness_handles_missing_freshness_key_in_raw() -> None:
    """If a raw_section dict omits the freshness key, target stays None
    (mirrors V5's None-friendly schema; keeps helper defensive).
    """
    sections: list[SectionV6] = [_make_section_v6("bb")]
    final_brief: BriefPayloadV6 = _make_brief_payload(sections)
    raw_sections: list[dict[str, Any]] = [
        {"slug": "bb"},  # no freshness key at all
    ]

    pipeline_v6._stamp_freshness(final_brief, raw_sections)

    assert final_brief.sections[0].freshness is None


def test_stamp_freshness_preserves_existing_when_raw_provides_none() -> None:
    """If raw_sections has freshness=None or missing, preserve the section's
    existing freshness rather than clobbering it with None. Defensive against
    partial raw_section dicts (M1 review finding)."""
    section: SectionV6 = SectionV6(
        slug="bb",
        ord=3,
        title="Bangladesh Bank",
        group_key="banking",
        freshness="warning",  # already set
    )
    final_brief: BriefPayloadV6 = _make_brief_payload([section])
    # Two cases that both must preserve the existing "warning" value
    raw_with_explicit_none: list[dict[str, Any]] = [
        {"slug": "bb", "freshness": None},
    ]
    pipeline_v6._stamp_freshness(final_brief, raw_with_explicit_none)
    assert final_brief.sections[0].freshness == "warning", (
        "raw freshness=None must NOT clobber existing value"
    )

    raw_with_missing_key: list[dict[str, Any]] = [
        {"slug": "bb"},
    ]
    pipeline_v6._stamp_freshness(final_brief, raw_with_missing_key)
    assert final_brief.sections[0].freshness == "warning", (
        "missing freshness key must NOT clobber existing value"
    )


def test_stamp_freshness_overrides_existing_value() -> None:
    """If the editor somehow returned freshness already, the deterministic
    V5-derived value still wins (post-LLM enrichment is the source of truth).
    """
    section: SectionV6 = SectionV6(
        slug="bb",
        ord=3,
        title="Bangladesh Bank",
        group_key="banking",
        freshness="warning",  # editor's guess
    )
    final_brief: BriefPayloadV6 = _make_brief_payload([section])
    raw_sections: list[dict[str, Any]] = [
        {"slug": "bb", "freshness": "fresh"},  # V5 truth
    ]

    pipeline_v6._stamp_freshness(final_brief, raw_sections)

    assert final_brief.sections[0].freshness == "fresh"


# ─── Round-trip integration test ───────────────────────────────────────


def test_to_v6_raw_then_stamp_freshness_round_trip() -> None:
    """End-to-end: V5 SectionData → _to_v6_raw → _stamp_freshness lands V5's
    freshness on the SectionV6 model.
    """
    metric_a: Metric = Metric(
        id="bb_reserves",
        label="FX Reserves",
        value=20.5,
        unit="USD bn",
        as_of=date(2026, 5, 1),
        source="Bangladesh Bank",
        cadence="monthly",
    )
    metric_b: Metric = Metric(
        id="fx_bdt",
        label="BDT/USD",
        value=110.5,
        unit="BDT",
        as_of=date(2026, 5, 7),
        source="BB",
        cadence="daily",
    )
    v5_sections: list[SectionData] = [
        SectionData(
            id="bb",
            title="Bangladesh Bank",
            metrics=[metric_a],
            freshness="fresh",
            freshness_reason="published today",
        ),
        SectionData(
            id="fx",
            title="FX Markets",
            metrics=[metric_b],
            freshness="warning",
            freshness_reason="2 days stale",
        ),
    ]

    raw_sections: list[dict[str, Any]] = pipeline_v6._to_v6_raw(v5_sections)

    # Build a final_brief that mirrors the editor's output for these slugs
    sections_v6: list[SectionV6] = [
        SectionV6(slug=r["slug"], ord=r["ord"], title=r["title"], group_key=r["group_key"])
        for r in raw_sections
    ]
    final_brief: BriefPayloadV6 = _make_brief_payload(sections_v6)

    pipeline_v6._stamp_freshness(final_brief, raw_sections)

    by_slug: dict[str, SectionV6] = {s.slug: s for s in final_brief.sections}
    assert by_slug["bb"].freshness == "fresh"
    assert by_slug["fx"].freshness == "warning"


# ─── Pipeline-level: stamp_freshness is invoked in run_publish ─────────


def test_run_publish_stamps_freshness_on_final_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pipeline calls _stamp_freshness so freshness lands on the
    payload that publish_brief receives.
    """
    monday: date = date(2026, 5, 4)

    # No previous brief
    monkeypatch.setattr(pipeline_v6, "fetch_previous_brief", lambda: None)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 0)
    monkeypatch.setattr(pipeline_v6, "fetch_recent_news", lambda n_issues=5: [])
    monkeypatch.setattr(pipeline_v6, "fetch_metric_definitions", lambda: [])

    # V5 input — single section with explicit freshness
    v5_sections: list[SectionData] = [
        SectionData(
            id="bb",
            title="Bangladesh Bank",
            metrics=[],
            freshness="stale",
            freshness_reason="not refreshed in 14 days",
        ),
    ]

    # Editor returns a brief with that section but NO freshness — _stamp_freshness must add it.
    editor_output: dict[str, Any] = {
        "brief": {
            "issue_no": 1,
            "volume": 1,
            "brief_date": monday.isoformat(),
            "status": "published",
        },
        "sections": [
            {
                "slug": "bb",
                "ord": 3,
                "title": "Bangladesh Bank",
                "group_key": "banking",
                "weight": 2,
                "verdict": "Reserves below floor",
                "verdict_tone": "warn",
                "tldr": "BB hasn't published reserves in 14 days.",
            },
        ],
    }
    subeditor_output: dict[str, Any] = {"verdict": "pass", "issues": []}

    call_log: list[str] = []

    def fake_call(*, label: str, **_: Any) -> dict[str, Any]:
        call_log.append(label)
        if label == "editor_v6":
            return editor_output
        if label == "subeditor_v6":
            return subeditor_output
        raise AssertionError(f"unexpected label: {label}")

    monkeypatch.setattr(pipeline_v6, "_call_with_retries", fake_call)

    captured: list[BriefPayloadV6] = []
    monkeypatch.setattr(
        pipeline_v6,
        "publish_brief",
        lambda payload: captured.append(payload) or "fake-uuid",
    )

    result: str | None = pipeline_v6.run_publish(v5_sections, monday)

    assert result == "fake-uuid"
    assert len(captured) == 1
    published: BriefPayloadV6 = captured[0]
    assert published.sections[0].slug == "bb"
    assert published.sections[0].freshness == "stale"
