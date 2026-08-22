"""Pipeline_v6 orchestrator tests — mocked Claude + mocked publisher."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from brief.claude.max_client import MaxCallResult
from brief.pipeline_v6 import V6PublishError, _to_v6_raw, run_publish
from brief.schema import SectionData
from brief.v6_schema import BriefPayloadV6, SubeditorReview


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


def test_subeditor_revise_without_brief_holds_never_ships_unrevised(
    _stub_supabase_reads: object,
) -> None:
    """verdict=revise with revised_brief=None is now schema-invalid (never fail
    OPEN). If the sub-editor persists in returning it after the one retry,
    run_publish HOLDS — it must never ship the unrevised editor brief while
    logging the edition as reviewed."""
    revise_no_brief = {"verdict": "revise", "issues": [
        {
            "section": None,
            "field": "todays_call",
            "severity": "error",
            "problem": "Missing posture line at end.",
        }
    ], "revised_brief": None}

    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief") as mock_pub:
        mock_run.side_effect = [
            _max_result(_editor_output()),   # editor
            _max_result(revise_no_brief),    # sub-editor attempt 1 (invalid — no brief)
            _max_result(revise_no_brief),    # sub-editor attempt 2 (the one retry, still invalid)
        ]
        with pytest.raises(V6PublishError, match="malformed review twice"):
            run_publish([], today=date(2026, 5, 5))

    mock_pub.assert_not_called()
    assert mock_run.call_count == 3  # editor + exactly two sub-editor attempts


def test_subeditor_revise_without_brief_holds_even_for_warn_only_issues(
    _stub_supabase_reads: object,
) -> None:
    """Same as above but with a warn-only issue list. The prompt permits fixing
    warn-only issues via revise (subeditor_v6.txt:116), and the schema rule is
    severity-blind — a future narrowing to error-severity-only would leave a
    warn-only revise+None fail-open again, so this case pins the broader rule."""
    revise_no_brief_warn = {"verdict": "revise", "issues": [
        {
            "section": None,
            "field": "todays_call",
            "severity": "warn",
            "problem": "Minor phrasing nit.",
        }
    ], "revised_brief": None}

    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief") as mock_pub:
        mock_run.side_effect = [
            _max_result(_editor_output()),        # editor
            _max_result(revise_no_brief_warn),    # sub-editor attempt 1 (invalid — no brief)
            _max_result(revise_no_brief_warn),    # sub-editor attempt 2 (the one retry, still invalid)
        ]
        with pytest.raises(V6PublishError, match="malformed review twice"):
            run_publish([], today=date(2026, 5, 5))

    mock_pub.assert_not_called()
    assert mock_run.call_count == 3  # editor + exactly two sub-editor attempts


def test_publish_gate_holds_on_non_pass_verdict_even_if_validator_bypassed(
    _stub_supabase_reads: object,
) -> None:
    """The publish gate must enforce "never ship without a revised_brief" as its
    OWN invariant, not rely solely on SubeditorReview's model_validator. A
    validator only guards `model_validate` — `model_construct()` and plain
    attribute assignment both skip it (no `validate_assignment` on the model),
    so a bypassed revise+None must still be caught and held at the gate."""
    bypassed = SubeditorReview.model_construct(verdict="revise", issues=[], revised_brief=None)

    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6._run_subeditor", return_value=bypassed), \
         patch("brief.pipeline_v6.publish_brief") as mock_pub:
        mock_run.side_effect = [_max_result(_editor_output())]
        with pytest.raises(V6PublishError, match="never fail OPEN"):
            run_publish([], today=date(2026, 5, 5))

    mock_pub.assert_not_called()


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


def test_deterministic_gate_crash_never_blocks_publish(
    _stub_supabase_reads: object, caplog: pytest.LogCaptureFixture
) -> None:
    """Log-only is STRUCTURAL: even if a validator regresses its never-raise
    contract and the gate itself crashes, the publish must proceed (fresh-context
    review MEDIUM). The crash is logged at WARNING with the traceback."""
    review = {"verdict": "pass", "issues": [], "revised_brief": None}

    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief", return_value="brief-id-89") as mock_pub, \
         patch(
             "brief.pipeline_v6._validators.validate_no_banal_language",
             side_effect=RuntimeError("validator regressed its never-raise contract"),
         ):
        mock_run.side_effect = [_max_result(_editor_output()), _max_result(review)]
        with caplog.at_level("WARNING", logger="brief.pipeline_v6"):
            brief_id = run_publish([], today=date(2026, 5, 5), scraped_headlines=[])

    assert brief_id == "brief-id-89"          # publish went through
    mock_pub.assert_called_once()             # despite the gate crashing
    assert any(
        "deterministic gate crashed" in r.message for r in caplog.records
    ), "gate crash must be logged, not silently swallowed"


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


# ── hard denylist (P0 honesty fix, 2026-08-22 audit #204) ───────────────────
# The editor invented a "$80 FY27 [crude]" budget-assumption motif, repeated
# with "$14.09" — neither has any basis in Bangladesh's actual FY27 budget.
# Unlike the log-only checks above, a match here must HOLD the publish.


def _brief_with_todays_call(text: str) -> BriefPayloadV6:
    return BriefPayloadV6.model_validate({
        "brief": {
            "issue_no": 89, "volume": 1, "brief_date": "2026-05-05",
            "todays_call": text,
        },
        "sections": [{
            "slug": "dse", "ord": 6, "title": "DSE", "group_key": "markets",
            "weight": 1,
        }],
    })


def test_deterministic_gate_passes_clean_text_through_the_denylist() -> None:
    from brief.pipeline_v6 import _run_deterministic_gate

    clean = _brief_with_todays_call(
        "Reserves firmed to $35.11B; the book stays defensive on import cover."
    )
    assert _run_deterministic_gate(clean) == 0


def test_deterministic_gate_hard_fails_on_80_dollar_fy27_forward_order() -> None:
    from brief.pipeline_v6 import DenylistViolationError, _run_deterministic_gate

    brief = _brief_with_todays_call("The FY27 budget assumes crude at $80 a barrel.")
    with pytest.raises(DenylistViolationError):
        _run_deterministic_gate(brief)


def test_deterministic_gate_hard_fails_on_80_dollar_fy27_reverse_order() -> None:
    from brief.pipeline_v6 import DenylistViolationError, _run_deterministic_gate

    brief = _brief_with_todays_call("Crude at $80 underpins the FY27 budget math.")
    with pytest.raises(DenylistViolationError):
        _run_deterministic_gate(brief)


def test_deterministic_gate_hard_fails_on_1409() -> None:
    from brief.pipeline_v6 import DenylistViolationError, _run_deterministic_gate

    brief = _brief_with_todays_call("Brent settled at $14.09 on thin volume.")
    with pytest.raises(DenylistViolationError):
        _run_deterministic_gate(brief)


def test_deterministic_gate_denylist_is_case_insensitive() -> None:
    from brief.pipeline_v6 import DenylistViolationError, _run_deterministic_gate

    brief = _brief_with_todays_call("the fy27 budget assumes crude at $80 a barrel.")
    with pytest.raises(DenylistViolationError):
        _run_deterministic_gate(brief)


def test_run_publish_holds_when_editor_output_hits_the_hard_denylist(
    _stub_supabase_reads: object,
) -> None:
    """Unlike a log-only gate crash, a denylist hit must propagate all the way
    through run_publish and abort BEFORE publish_brief is ever called."""
    from brief.pipeline_v6 import DenylistViolationError

    tainted = _editor_output()
    tainted["brief"]["todays_call"] = "The FY27 budget assumes crude at $80 a barrel."
    review = {"verdict": "pass", "issues": [], "revised_brief": None}

    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief") as mock_pub:
        mock_run.side_effect = [_max_result(tainted), _max_result(review)]
        with pytest.raises(DenylistViolationError):
            run_publish([], today=date(2026, 5, 5), scraped_headlines=[])

    mock_pub.assert_not_called()


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
