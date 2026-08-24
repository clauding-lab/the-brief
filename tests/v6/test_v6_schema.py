"""V6 schema validation tests — strict shape enforcement."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from brief.v6_schema import (
    BankerReadV6,
    BriefPayloadV6,
    BriefV6,
    MetricV6,
    SectionV6,
    SubeditorReview,
    SummaryPillV6,
)


def _minimal_section(slug: str = "bb", ord_: int = 3) -> dict:
    return {
        "slug": slug,
        "ord": ord_,
        "title": "Bangladesh Bank",
        "group_key": "banking",
        "weight": 1,
    }


def _minimal_brief(issue_no: int = 89) -> dict:
    return {
        "brief": {
            "issue_no": issue_no,
            "volume": 1,
            "brief_date": "2026-05-05",
            "status": "published",
        },
        "sections": [_minimal_section("headlines", 2)],
    }


def test_minimal_brief_validates() -> None:
    payload = BriefPayloadV6.model_validate(_minimal_brief())
    assert payload.brief.issue_no == 89
    assert len(payload.sections) == 1
    assert payload.sections[0].slug == "headlines"


def test_extra_field_on_brief_rejected() -> None:
    body = _minimal_brief()
    body["brief"]["mystery_field"] = "boo"
    with pytest.raises(ValidationError):
        BriefPayloadV6.model_validate(body)


def test_extra_field_on_section_rejected() -> None:
    body = _minimal_brief()
    body["sections"][0]["mystery_field"] = "boo"
    with pytest.raises(ValidationError):
        BriefPayloadV6.model_validate(body)


def test_invalid_tone_rejected() -> None:
    body = _minimal_brief()
    body["sections"][0]["verdict_tone"] = "hopeful"
    with pytest.raises(ValidationError):
        BriefPayloadV6.model_validate(body)


def test_banker_read_min_verdict_length() -> None:
    with pytest.raises(ValidationError):
        BankerReadV6(verdict="too short", watch=[], risk=[])


def test_a_full_sentence_verdict_fits_the_widened_cap() -> None:
    """The Daily Star voice trades characters for verbs.

    The live issue-206 Policy & Rates verdict was 231 chars in the telegraphic
    register and 355 rewritten as full sentences — a ~50% cost. The old 400-char
    cap left almost no margin, and overrunning it fails validation and holds the
    whole publish rather than degrading gracefully.
    """
    rewritten = (
        "Short-term money remains cheap. Overnight call money is trading at "
        "9.26% and the 7-day at 9.25%, both below the 9.5% policy rate set "
        "after July's cut, though the 14-day has moved up to 9.88%. Reserves "
        "were last published at $36.42bn for 1 Jul 2026 and have not been "
        "updated since, so the cover ratio behind an easing front rests on a "
        "seven-week-old print. Deposit rates have not yet followed the bill "
        "curve down, which leaves bank margins carrying the gap into H2."
    )
    assert len(rewritten) > 400, "sample no longer exercises the widened cap"
    assert BankerReadV6(verdict=rewritten, watch=[], risk=[]).verdict == rewritten


def test_the_cap_is_still_a_cap() -> None:
    """1000 is a safety limit, not an invitation — past it, still a hard stop.

    The SPA renders this field at 22px (30px in the hero) with no line clamp,
    so an unbounded verdict would run as a wall of display type.
    """
    with pytest.raises(ValidationError):
        BankerReadV6(verdict="A. " * 400, watch=[], risk=[])


def test_banker_read_full() -> None:
    br = BankerReadV6(
        verdict="NPLs at 35.73% are not a headline — they are the headline.",
        watch=["item one", "item two"],
        risk=["risk one"],
        runway={"value": "0", "unit": "mo buffer"},
    )
    assert br.runway is not None
    assert br.runway.value == "0"


def test_summary_pill_default_tone() -> None:
    pill = SummaryPillV6(key="POLICY RATE", value="10.00%")
    assert pill.tone == "neu"


def test_section_weight_clamp() -> None:
    body = _minimal_brief()
    body["sections"][0]["weight"] = 5
    with pytest.raises(ValidationError):
        BriefPayloadV6.model_validate(body)


def test_section_ord_clamp() -> None:
    body = _minimal_brief()
    body["sections"][0]["ord"] = 99
    with pytest.raises(ValidationError):
        BriefPayloadV6.model_validate(body)


def test_subeditor_review_pass() -> None:
    review = SubeditorReview.model_validate({"verdict": "pass"})
    assert review.verdict == "pass"
    assert review.issues == []
    assert review.revised_brief is None


def test_subeditor_review_revise_requires_brief() -> None:
    """verdict="revise" without a revised_brief must be REJECTED at the schema
    layer — a review gate must never fail OPEN (AGENT_LEARNINGS.md). Letting a
    well-formed-but-empty revise through shipped the unrevised editor brief
    while journaling it as reviewed."""
    review_with = SubeditorReview.model_validate(
        {
            "verdict": "revise",
            "issues": [
                {
                    "section": "fx",
                    "field": "banker_read.verdict",
                    "severity": "error",
                    "problem": "Verdict claims pin holds but trade analysis says depreciating.",
                }
            ],
            "revised_brief": _minimal_brief(),
        }
    )
    assert review_with.revised_brief is not None
    assert review_with.revised_brief.brief.issue_no == 89

    with pytest.raises(ValidationError, match="revised_brief"):
        SubeditorReview.model_validate(
            {
                "verdict": "revise",
                "issues": [
                    {
                        "section": "fx",
                        "field": "banker_read.verdict",
                        "severity": "error",
                        "problem": "Verdict claims pin holds but trade analysis says depreciating.",
                    }
                ],
                "revised_brief": None,
            }
        )

    # Severity-blind: even a warn-only revise (the prompt permits fixing warn
    # issues via revise, subeditor_v6.txt:116) must still carry a
    # revised_brief. A future narrowing of the validator to error-severity
    # issues only would leave this fail-open again — this case pins that
    # the rule is not severity-scoped.
    with pytest.raises(ValidationError, match="revised_brief"):
        SubeditorReview.model_validate(
            {
                "verdict": "revise",
                "issues": [
                    {
                        "section": "fx",
                        "field": "banker_read.verdict",
                        "severity": "warn",
                        "problem": "Minor phrasing nit.",
                    }
                ],
                "revised_brief": None,
            }
        )


def test_subeditor_review_fail() -> None:
    review = SubeditorReview.model_validate(
        {
            "verdict": "fail",
            "issues": [
                {
                    "section": None,
                    "field": "cover_metric.value",
                    "severity": "error",
                    "problem": "Cover metric value 35.73% does not appear in raw data.",
                }
            ],
        }
    )
    assert review.verdict == "fail"
    assert review.issues[0].severity == "error"


def test_metric_value_string_passes_through_unchanged() -> None:
    """The canonical happy path: a pre-formatted string flows through as-is."""
    m = MetricV6(label="NPL", value="35.73%")
    assert m.value == "35.73%"


def test_metric_value_accepts_float_and_coerces_to_string() -> None:
    """v1.5.1: editor occasionally emits numeric values; schema stringifies
    rather than crashing the publish. Trailing zeros are trimmed via :.10g."""
    m = MetricV6(label="NPL", value=35.73)  # type: ignore[arg-type]
    assert m.value == "35.73"


def test_metric_value_accepts_int_and_coerces_to_string() -> None:
    m = MetricV6(label="Sections", value=8)  # type: ignore[arg-type]
    assert m.value == "8"


def test_metric_value_preserves_full_precision() -> None:
    """A genuinely-precise float (e.g., FX reserves 35.1112) is kept, not rounded."""
    m = MetricV6(label="FX reserves $B", value=35.1112)  # type: ignore[arg-type]
    assert m.value == "35.1112"


def test_metric_delta_dict_stringifies_with_direction_and_window() -> None:
    """v1.5.1: editor sometimes emits delta as {value, direction, window};
    schema renders 'up' as '+', 'down' as '−' (Unicode minus), formats
    magnitude as N.NN%, and pretty-cases the window suffix."""
    m = MetricV6(
        label="BB",
        value="35.11",
        delta={"value": 0.9946, "direction": "up", "window": "wow"},  # type: ignore[arg-type]
    )
    assert m.delta == "+0.99% WoW"


def test_metric_delta_dict_down_direction_uses_unicode_minus() -> None:
    m = MetricV6(
        label="NPL",
        value="11.5",
        delta={"value": 0.42, "direction": "down", "window": "mom"},  # type: ignore[arg-type]
    )
    assert m.delta == "−0.42% MoM"


def test_metric_delta_dict_without_window_still_renders() -> None:
    m = MetricV6(
        label="Call money",
        value="9.5",
        delta={"value": 0.25, "direction": "up"},  # type: ignore[arg-type]
    )
    assert m.delta == "+0.25%"


def test_metric_delta_string_passes_through_unchanged() -> None:
    """Already-formatted delta strings (the editor's primary intent) are not touched."""
    m = MetricV6(label="x", value="1", delta="+1.2% WoW")
    assert m.delta == "+1.2% WoW"


def test_metric_delta_none_passes_through_unchanged() -> None:
    m = MetricV6(label="x", value="1")
    assert m.delta is None


def test_metric_delta_numeric_coerces_via_stringify_numeric() -> None:
    m = MetricV6(label="x", value="1", delta=0.42)  # type: ignore[arg-type]
    assert m.delta == "0.42"
