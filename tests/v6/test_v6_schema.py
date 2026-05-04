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
    """Schema doesn't enforce brief presence on revise (intentional — the orchestrator
    falls back to editor output if revised_brief is missing). Just verify both shapes parse."""
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


def test_metric_value_must_be_string() -> None:
    """The schema requires metric.value as string for tabular display in the SPA."""
    with pytest.raises(ValidationError):
        MetricV6(label="NPL", value=35.73)  # type: ignore[arg-type]
