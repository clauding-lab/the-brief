"""Pipeline_v6 orchestrator tests — mocked Claude + mocked publisher."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from brief.claude.max_client import MaxCallResult
from brief.pipeline_v6 import V6PublishError, _to_v6_raw, run_publish
from brief.schema import SectionData
from brief.v6_schema import BriefPayloadV6


@pytest.fixture(autouse=True)
def _supabase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")


def _editor_output(issue_no: int = 89) -> dict:
    return {
        "brief": {
            "issue_no": issue_no,
            "volume": 1,
            "brief_date": "2026-05-05",
            "todays_call": "Today's brief is shipping.",
            "status": "published",
        },
        "sections": [
            {
                "slug": "bb",
                "ord": 3,
                "title": "Bangladesh Bank",
                "group_key": "banking",
                "weight": 1,
                "verdict": "Holding; data-dependent",
                "verdict_tone": "neu",
                "tldr": "Holding; data-dependent — tightening optionality intact.",
                "metrics": [{"label": "Repo", "value": "10.00%", "tone": "neu"}],
                "news": [],
                "summary_pills": [
                    {"key": "POLICY RATE", "value": "10.00%", "tone": "neu"},
                ],
            },
            {
                "slug": "banking",
                "ord": 4,
                "title": "Banking",
                "group_key": "banking",
                "weight": 2,
                "verdict_tone": "bear",
                "tldr": "Stress accelerating.",
                "analysis": "NPLs at 35.73%...",
                "metrics": [{"label": "NPL", "value": "35.73%", "tone": "bear"}],
                "news": [],
                "summary_pills": [
                    {"key": "NPL", "value": "35.73%", "tone": "bear"},
                ],
            },
        ],
    }


def _max_result(parsed: dict) -> MaxCallResult:
    return MaxCallResult(
        raw_text="<json>", parsed=parsed, usage={}, total_cost_usd=0.05, duration_s=0.5
    )


@pytest.fixture
def _stub_supabase_reads() -> object:
    """fetch_max_issue_no returns 88 → next is 89; fetch_previous_brief returns None.
    Also stubs the new Phase 2/3 helpers so tests don't hit the network.
    """
    with patch("brief.pipeline_v6.fetch_max_issue_no", return_value=88), \
         patch("brief.pipeline_v6.fetch_previous_brief", return_value=None), \
         patch("brief.pipeline_v6.fetch_recent_news", return_value=[]), \
         patch("brief.pipeline_v6.fetch_metric_definitions", return_value=[]):
        yield


def test_subeditor_pass_publishes_editor_output(_stub_supabase_reads: object) -> None:
    """When subeditor returns verdict=pass, the editor output is published as-is."""
    review = {"verdict": "pass", "issues": [], "revised_brief": None}

    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief", return_value="brief-id-89") as mock_pub:
        mock_run.side_effect = [_max_result(_editor_output()), _max_result(review)]
        brief_id = run_publish([], today=date(2026, 5, 5), scraped_headlines=[])

    assert brief_id == "brief-id-89"
    assert mock_run.call_count == 2  # editor + subeditor
    published = mock_pub.call_args.args[0]
    assert published.brief.issue_no == 89


def test_subeditor_revise_publishes_revised_brief(_stub_supabase_reads: object) -> None:
    """When subeditor returns verdict=revise, the revised_brief is published instead."""
    edited = _editor_output()
    revised = _editor_output()
    revised["brief"]["todays_call"] = "REVISED — issues fixed."
    review = {
        "verdict": "revise",
        "issues": [
            {
                "section": None,
                "field": "todays_call",
                "severity": "warn",
                "problem": "Missing posture line at end.",
            }
        ],
        "revised_brief": revised,
    }

    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief", return_value="brief-id-89") as mock_pub:
        mock_run.side_effect = [_max_result(edited), _max_result(review)]
        run_publish([], today=date(2026, 5, 5))

    published = mock_pub.call_args.args[0]
    assert "REVISED" in (published.brief.todays_call or "")


def test_subeditor_fail_aborts(_stub_supabase_reads: object) -> None:
    """When subeditor returns verdict=fail, run_publish raises and nothing is written."""
    review = {
        "verdict": "fail",
        "issues": [
            {
                "section": None,
                "field": "cover_metric.value",
                "severity": "error",
                "problem": "Cover metric value not in raw data.",
            }
        ],
        "revised_brief": None,
    }

    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief") as mock_pub:
        mock_run.side_effect = [_max_result(_editor_output()), _max_result(review)]
        with pytest.raises(V6PublishError, match="verdict=fail"):
            run_publish([], today=date(2026, 5, 5))

    mock_pub.assert_not_called()


def test_dry_run_skips_publish(_stub_supabase_reads: object) -> None:
    review = {"verdict": "pass", "issues": [], "revised_brief": None}
    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief") as mock_pub:
        mock_run.side_effect = [_max_result(_editor_output()), _max_result(review)]
        result = run_publish([], today=date(2026, 5, 5), dry_run=True)

    assert result is None
    mock_pub.assert_not_called()


def test_subeditor_malformed_twice_holds_never_auto_pass(_stub_supabase_reads: object) -> None:
    """A malformed SubeditorReview must NEVER auto-pass. After one retry it still
    fails → run_publish HOLDS (raises), and nothing is published. (Review item 7.)"""
    malformed = {"verdict": "maybe"}  # not a valid ReviewVerdict → SubeditorReview rejects

    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief") as mock_pub:
        mock_run.side_effect = [
            _max_result(_editor_output()),  # editor
            _max_result(malformed),         # sub-editor attempt 1
            _max_result(malformed),         # sub-editor attempt 2 (the one retry)
        ]
        with pytest.raises(V6PublishError, match="malformed review twice"):
            run_publish([], today=date(2026, 5, 5))

    mock_pub.assert_not_called()
    assert mock_run.call_count == 3  # editor + exactly two sub-editor attempts


def test_subeditor_malformed_once_then_valid_passes(_stub_supabase_reads: object) -> None:
    """A malformed review on the first attempt but a valid one on the retry should
    publish normally (the retry recovers transient LLM formatting glitches)."""
    malformed = {"verdict": "maybe"}
    valid = {"verdict": "pass", "issues": [], "revised_brief": None}

    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief", return_value="brief-id-89") as mock_pub:
        mock_run.side_effect = [
            _max_result(_editor_output()),  # editor
            _max_result(malformed),         # sub-editor attempt 1 (malformed)
            _max_result(valid),             # sub-editor attempt 2 (valid → pass)
        ]
        brief_id = run_publish([], today=date(2026, 5, 5))

    assert brief_id == "brief-id-89"
    assert mock_run.call_count == 3
    mock_pub.assert_called_once()


def test_deterministic_gate_flags_banal_and_bad_chart_read() -> None:
    """The log-only deterministic gate counts banal language + chart_read cap/anchor
    violations over the final brief prose (validators.py wired into the publish path)."""
    from brief.pipeline_v6 import _run_deterministic_gate

    long_signal = " ".join(f"word{i}" for i in range(30))  # 30 words > 25-word cap
    brief = BriefPayloadV6.model_validate({
        "brief": {
            "issue_no": 89, "volume": 1, "brief_date": "2026-05-05",
            "todays_call": "A robust and stunning move amid the data.",  # 3 banal tells
        },
        "sections": [{
            "slug": "dse", "ord": 6, "title": "DSE", "group_key": "markets",
            "weight": 1,
            "chart_read": {
                "signal": long_signal,                                   # over length cap
                "context": "the index moved a lot broadly across names",  # no temporal anchor
                "implication": "things look interesting overall",         # no desk/verb/time
            },
        }],
    })

    n = _run_deterministic_gate(brief)
    # todays_call banal + chart_read length + temporal_anchor + implication_quality
    assert n >= 4


def test_deterministic_gate_clean_brief_zero_violations() -> None:
    from brief.pipeline_v6 import _run_deterministic_gate

    brief = BriefPayloadV6.model_validate({
        "brief": {
            "issue_no": 89, "volume": 1, "brief_date": "2026-05-05",
            "todays_call": "Reserves firmed to $35.11B; the book stays defensive on import cover.",
        },
        "sections": [{
            "slug": "dse", "ord": 6, "title": "DSE", "group_key": "markets",
            "weight": 1,
            "chart_read": {
                "signal": "DSEX closed at 5,516, up 0.4% on the session.",
                "context": "Highest since March 2026 on thin turnover.",
                "implication": "Treasury should watch the index above 5,500 for rotation.",
            },
        }],
    })

    assert _run_deterministic_gate(brief) == 0


def test_section_adapter_renames_iranwar_to_iran() -> None:
    """V5 SectionData id 'iranwar' → V6 slug 'iran' per the V5_TO_V6 map."""
    sections = [
        SectionData(id="iranwar", title="Iran War & Oil", freshness="fresh"),
        SectionData(id="exec", title="Executive Signals", freshness="fresh"),  # dropped
        SectionData(id="bb", title="Bangladesh Bank", freshness="fresh"),
    ]
    raw = _to_v6_raw(sections)
    slugs = [s["slug"] for s in raw]
    assert "iran" in slugs
    assert "iranwar" not in slugs
    assert "exec" not in slugs  # V6 dropped exec
    assert "bb" in slugs
