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


@pytest.fixture(autouse=True)
def _redirect_raw_dumps(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Test hygiene, not a behavior change: several tests below deliberately
    trigger a malformed-review hold (e.g. `test_subeditor_malformed_twice_
    holds_never_auto_pass`), which calls the REAL `_dump_raw_on_failure` —
    production code that writes into the repo's tracked `logs/` dir by
    design (issue 181, 2026-07-31). Left unpatched, every pytest run leaks a
    handful of 6-byte `raw_text="<json>"` dump files into that real
    directory. `_dump_raw_on_failure` itself is UNCHANGED — this only
    redirects where THIS test file's calls land, to pytest's own per-test
    `tmp_path` (auto-cleaned), preserving the same "stashed text → return a
    path, or None when nothing was stashed" contract the callers depend on.
    """
    import brief.pipeline_v6 as _pv6

    def _redirected(label: str) -> str | None:
        raw = _pv6._LAST_RAW.get(label)
        if not raw:
            return None
        path = tmp_path / f"{label}_raw_test.txt"
        path.write_text(raw)
        return str(path)

    monkeypatch.setattr(_pv6, "_dump_raw_on_failure", _redirected)


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


def test_deterministic_gate_1409_alone_passes() -> None:
    """Review round 1 (C1, BLOCKER): the original bare '$14.09' pattern would
    have blocked this legitimate desk line forever — there is nothing
    hallucinatory about Brent settling at $14.09. It now needs FY27/$80/
    crude/budget CONTEXT in the same field to mean anything."""
    from brief.pipeline_v6 import _run_deterministic_gate

    brief = _brief_with_todays_call("Brent settled at $14.09 on thin volume.")
    assert _run_deterministic_gate(brief) == 0


# H-A, review round 2: the bare (no-lookaround) "$?14\.09" pattern matched
# "14.09" as a SUBSTRING of a larger real number. Each of these four is a
# genuine banker-grade figure with nothing to do with the FY27 hallucination
# and must pass even with no context requirement — the fix is in the regex
# itself (bounded on both sides), not just the co-occurrence gate above.

def test_deterministic_gate_passes_tk_1214_09():
    from brief.pipeline_v6 import _run_deterministic_gate

    brief = _brief_with_todays_call("NBR collections reached Tk1,214.09 crore in July.")
    assert _run_deterministic_gate(brief) == 0


def test_deterministic_gate_passes_314_09bn():
    from brief.pipeline_v6 import _run_deterministic_gate

    brief = _brief_with_todays_call("Gross reserves stand at $314.09bn equivalent.")
    assert _run_deterministic_gate(brief) == 0


def test_deterministic_gate_passes_3914_09():
    from brief.pipeline_v6 import _run_deterministic_gate

    brief = _brief_with_todays_call("The index closed at 3,914.09, up on the session.")
    assert _run_deterministic_gate(brief) == 0


def test_deterministic_gate_passes_4014_09():
    from brief.pipeline_v6 import _run_deterministic_gate

    brief = _brief_with_todays_call("Turnover hit 4,014.09 crore taka on the DSE.")
    assert _run_deterministic_gate(brief) == 0


def test_deterministic_gate_hard_fails_on_1409_with_fy27_context() -> None:
    from brief.pipeline_v6 import DenylistViolationError, _run_deterministic_gate

    brief = _brief_with_todays_call("$14.09 above the $80 FY27 line.")
    with pytest.raises(DenylistViolationError):
        _run_deterministic_gate(brief)


def test_deterministic_gate_hard_fails_on_1409_with_budget_context() -> None:
    from brief.pipeline_v6 import DenylistViolationError, _run_deterministic_gate

    brief = _brief_with_todays_call("The line item sits $14.09 over the budget assumption.")
    with pytest.raises(DenylistViolationError):
        _run_deterministic_gate(brief)


def test_deterministic_gate_scans_prose_only_a_chart_series_value_of_5114_09_passes() -> None:
    """C1 BLOCKER, real reviewer reproduction: scanning the FULL serialized
    brief matched a chart data point whose JSON happens to end in '14.09'
    (e.g. DSEX closing at 5114.09) with zero relation to the FY27
    hallucination — that would have held the publish for as long as the
    point stayed in the trailing window. `series`/`spark`/`movers`/
    `metric.value` are never scanned."""
    from brief.pipeline_v6 import _run_deterministic_gate

    brief = BriefPayloadV6.model_validate({
        "brief": {
            "issue_no": 89, "volume": 1, "brief_date": "2026-05-05",
            "todays_call": "A quiet session across the board.",
        },
        "sections": [{
            "slug": "dse", "ord": 6, "title": "DSE", "group_key": "markets",
            "weight": 1,
            "series": [{"key": "dsex", "ts": "2026-05-05", "value": 5114.09}],
            "metrics": [{"label": "DSEX", "value": "5,114.09"}],
        }],
    })
    assert _run_deterministic_gate(brief) == 0


def test_deterministic_gate_scans_chart_note_detail_which_is_free_prose() -> None:
    """L-C, review round 2: `notes[].detail` is free-text the editor writes
    (a chart annotation's explanation) — the same kind of surface as
    `todays_call`, and was originally lumped in with the numeric exclusions
    by mistake."""
    from brief.pipeline_v6 import DenylistViolationError, _run_deterministic_gate

    brief = BriefPayloadV6.model_validate({
        "brief": {"issue_no": 89, "volume": 1, "brief_date": "2026-05-05"},
        "sections": [{
            "slug": "dse", "ord": 6, "title": "DSE", "group_key": "markets",
            "weight": 1,
            "notes": [{
                "series_key": "dsex", "ts": "2026-05-05", "label": "Peak",
                "detail": "The FY27 budget assumes crude at $80 a barrel.",
            }],
        }],
    })
    with pytest.raises(DenylistViolationError):
        _run_deterministic_gate(brief)


def test_deterministic_gate_does_not_scan_note_label_or_series_key() -> None:
    """The short structural fields on a chart note (`label`, `series_key`,
    `ts`) stay unscanned — only `detail` is prose."""
    from brief.pipeline_v6 import _run_deterministic_gate

    brief = BriefPayloadV6.model_validate({
        "brief": {"issue_no": 89, "volume": 1, "brief_date": "2026-05-05"},
        "sections": [{
            "slug": "dse", "ord": 6, "title": "DSE", "group_key": "markets",
            "weight": 1,
            "notes": [{
                "series_key": "$80 FY27", "ts": "2026-05-05",
                "label": "$80 FY27 crude",
            }],
        }],
    })
    assert _run_deterministic_gate(brief) == 0


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


# ── M-A, review round 2: _stamp_import_cover_sub — MetricV6 has no `source`
# field, so the dual-period note the builder computes must be forced into
# `sub` deterministically, not left to the editor to transcribe. ────────────

def _macro_raw_sections_with_import_cover(source: str | None, value: float | None = 6.25) -> list[dict]:
    return [{
        "slug": "macro",
        "metrics": [{"label": "Import Cover", "value": value, "source": source}],
    }]


def _macro_brief_with_import_cover_sub(sub: str | None) -> BriefPayloadV6:
    return BriefPayloadV6.model_validate({
        "brief": {"issue_no": 89, "volume": 1, "brief_date": "2026-05-05"},
        "sections": [{
            "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
            "weight": 1,
            "metrics": [{"label": "Import Cover", "value": "6.25", "sub": sub}],
        }],
    })


def test_stamp_import_cover_sub_appends_the_note_when_the_editor_dropped_it() -> None:
    from brief.pipeline_v6 import _stamp_import_cover_sub

    raw = _macro_raw_sections_with_import_cover("BB (reserves 31 Jul ÷ Mar import bill)")
    brief = _macro_brief_with_import_cover_sub(None)

    _stamp_import_cover_sub(brief, raw)

    metric = brief.sections[0].metrics[0]
    assert metric.sub == "reserves 31 Jul ÷ Mar import bill"


def test_stamp_import_cover_sub_appends_to_existing_editor_prose_not_replaces_it() -> None:
    from brief.pipeline_v6 import _stamp_import_cover_sub

    raw = _macro_raw_sections_with_import_cover("BB (reserves 31 Jul ÷ Mar import bill)")
    brief = _macro_brief_with_import_cover_sub("Comfortable against short-term needs.")

    _stamp_import_cover_sub(brief, raw)

    metric = brief.sections[0].metrics[0]
    assert metric.sub == "Comfortable against short-term needs. · reserves 31 Jul ÷ Mar import bill"


def test_stamp_import_cover_sub_is_a_noop_when_already_present() -> None:
    """Never double-appends on a re-run."""
    from brief.pipeline_v6 import _stamp_import_cover_sub

    raw = _macro_raw_sections_with_import_cover("BB (reserves 31 Jul ÷ Mar import bill)")
    already = "reserves 31 Jul ÷ Mar import bill"
    brief = _macro_brief_with_import_cover_sub(already)

    _stamp_import_cover_sub(brief, raw)

    assert brief.sections[0].metrics[0].sub == already


def test_stamp_import_cover_sub_still_stamps_when_editor_prose_contains_the_bare_marker() -> None:
    """Idempotence keys on the EXACT note, not the marker substring: an editor
    sub that naturally says "import bill" (the marker phrase) must not be
    mistaken for an already-stamped sub. This is the issue-210 failure shape —
    the Real Policy stamp was skipped because the editor wrote "repo above
    p2p CPI" and the marker-substring check read that as already-stamped."""
    from brief.pipeline_v6 import _stamp_import_cover_sub

    raw = _macro_raw_sections_with_import_cover("BB (reserves 31 Jul ÷ Mar import bill)")
    brief = _macro_brief_with_import_cover_sub("Jun print, import bill rising.")

    _stamp_import_cover_sub(brief, raw)

    assert (
        brief.sections[0].metrics[0].sub
        == "Jun print, import bill rising. · reserves 31 Jul ÷ Mar import bill"
    )


def test_stamp_import_cover_sub_is_a_noop_when_the_metric_is_suppressed() -> None:
    """The raw builder metric has value=None (H1's 4-month gate suppressed
    it) — there is no dual-period fact to stamp."""
    from brief.pipeline_v6 import _stamp_import_cover_sub

    raw = _macro_raw_sections_with_import_cover("BB", value=None)
    brief = _macro_brief_with_import_cover_sub(None)

    _stamp_import_cover_sub(brief, raw)

    assert brief.sections[0].metrics[0].sub is None


def test_stamp_import_cover_sub_is_a_noop_when_no_macro_section_in_raw() -> None:
    from brief.pipeline_v6 import _stamp_import_cover_sub

    brief = _macro_brief_with_import_cover_sub(None)
    _stamp_import_cover_sub(brief, [])
    assert brief.sections[0].metrics[0].sub is None


# ── _stamp_real_policy_rate_sub (2026-08-26) — same mechanism as the import
# cover stamp: the builder records "which repo rate minus which CPI print" on
# the RAW metric's `source`, and this pass is the only thing that carries it
# to the reader, because MetricV6 has no `source` field. ────────────────────

_RPR_NOTE = "BB+BBS (9.50% repo (30 Jul cut) − 8.32% Jul p2p CPI)"
_RPR_SUB = "9.50% repo (30 Jul cut) − 8.32% Jul p2p CPI"


def _macro_raw_sections_with_real_policy_rate(
    source: str | None, value: float | None = 1.18,
) -> list[dict]:
    return [{
        "slug": "macro",
        "metrics": [{"label": "Real Policy Rate", "value": value, "source": source}],
    }]


def _macro_brief_with_real_policy_rate_sub(
    sub: str | None, *, label: str = "Real Policy Rate",
) -> BriefPayloadV6:
    return BriefPayloadV6.model_validate({
        "brief": {"issue_no": 89, "volume": 1, "brief_date": "2026-05-05"},
        "sections": [{
            "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
            "weight": 1,
            "metrics": [{"label": label, "value": "1.2%", "sub": sub}],
        }],
    })


def test_stamp_real_policy_rate_sub_appends_the_note_when_the_editor_dropped_it() -> None:
    from brief.pipeline_v6 import _stamp_real_policy_rate_sub

    raw = _macro_raw_sections_with_real_policy_rate(_RPR_NOTE)
    brief = _macro_brief_with_real_policy_rate_sub(None)

    _stamp_real_policy_rate_sub(brief, raw)

    assert brief.sections[0].metrics[0].sub == _RPR_SUB


def test_stamp_real_policy_rate_sub_appends_to_existing_editor_prose_not_replaces_it() -> None:
    from brief.pipeline_v6 import _stamp_real_policy_rate_sub

    raw = _macro_raw_sections_with_real_policy_rate(_RPR_NOTE)
    brief = _macro_brief_with_real_policy_rate_sub("Positive real rates, barely.")

    _stamp_real_policy_rate_sub(brief, raw)

    assert brief.sections[0].metrics[0].sub == f"Positive real rates, barely. · {_RPR_SUB}"


def test_stamp_real_policy_rate_sub_is_a_noop_when_already_present() -> None:
    """Never double-appends on a re-run."""
    from brief.pipeline_v6 import _stamp_real_policy_rate_sub

    raw = _macro_raw_sections_with_real_policy_rate(_RPR_NOTE)
    brief = _macro_brief_with_real_policy_rate_sub(_RPR_SUB)

    _stamp_real_policy_rate_sub(brief, raw)

    assert brief.sections[0].metrics[0].sub == _RPR_SUB


def test_stamp_real_policy_rate_sub_still_stamps_when_editor_prose_contains_the_bare_marker() -> None:
    """THE ISSUE-210 REGRESSION (2026-08-28): the editor's own sub was
    "Jul 2026, repo above p2p CPI." — it contains the marker phrase
    "p2p CPI", so the marker-substring idempotence check concluded the note
    was already stamped and skipped it. The corrected 1.18 published with no
    provenance. Idempotence must key on the EXACT reconstructed note."""
    from brief.pipeline_v6 import _stamp_real_policy_rate_sub

    raw = _macro_raw_sections_with_real_policy_rate(_RPR_NOTE)
    brief = _macro_brief_with_real_policy_rate_sub("Jul 2026, repo above p2p CPI.")

    _stamp_real_policy_rate_sub(brief, raw)

    assert brief.sections[0].metrics[0].sub == f"Jul 2026, repo above p2p CPI. · {_RPR_SUB}"


def test_stamp_real_policy_rate_sub_is_a_noop_when_the_metric_is_suppressed() -> None:
    """A missing leg suppressed the derivation — the spec's plain default
    source survives and there is no arithmetic to disclose."""
    from brief.pipeline_v6 import _stamp_real_policy_rate_sub

    raw = _macro_raw_sections_with_real_policy_rate("BB+BBS", value=None)
    brief = _macro_brief_with_real_policy_rate_sub(None)

    _stamp_real_policy_rate_sub(brief, raw)

    assert brief.sections[0].metrics[0].sub is None


def test_stamp_real_policy_rate_sub_is_a_noop_when_no_macro_section_in_raw() -> None:
    from brief.pipeline_v6 import _stamp_real_policy_rate_sub

    brief = _macro_brief_with_real_policy_rate_sub(None)
    _stamp_real_policy_rate_sub(brief, [])
    assert brief.sections[0].metrics[0].sub is None


def test_stamp_real_policy_rate_sub_carries_the_repo_leg_the_builder_actually_used() -> None:
    """Never a hardcoded corridor rate: whatever the builder resolved is what
    the reader sees. Pre-cut shape (June, at_or_before branch) stamps 10.00,
    not 9.50, and carries no decision parenthetical."""
    from brief.pipeline_v6 import _stamp_real_policy_rate_sub

    raw = _macro_raw_sections_with_real_policy_rate(
        "BB+BBS (10.00% repo − 9.16% Jun p2p CPI)", value=0.84,
    )
    brief = _macro_brief_with_real_policy_rate_sub(None)

    _stamp_real_policy_rate_sub(brief, raw)

    assert brief.sections[0].metrics[0].sub == "10.00% repo − 9.16% Jun p2p CPI"


# ── REVIEW FIX 2: both stampers must match labels the way every other
# post-editor pass does. `_reject_invented_and_dedupe` keeps the EDITOR'S
# casing, so an editor writing "Real policy rate" (one lowercase letter)
# previously got NO provenance stamp at all — and, worse, still tripped the
# validator's source-marker exemption, leaving its prose unchecked. ────────

def test_stamp_real_policy_rate_sub_matches_a_label_the_editor_recased() -> None:
    from brief.pipeline_v6 import _stamp_real_policy_rate_sub

    raw = _macro_raw_sections_with_real_policy_rate(_RPR_NOTE)
    brief = _macro_brief_with_real_policy_rate_sub(None, label="Real policy rate")

    _stamp_real_policy_rate_sub(brief, raw)

    assert brief.sections[0].metrics[0].sub == _RPR_SUB


def test_stamp_import_cover_sub_matches_a_label_the_editor_recased() -> None:
    from brief.pipeline_v6 import _stamp_import_cover_sub

    raw = _macro_raw_sections_with_import_cover("BB (reserves 31 Jul ÷ Mar import bill)")
    brief = BriefPayloadV6.model_validate({
        "brief": {"issue_no": 89, "volume": 1, "brief_date": "2026-05-05"},
        "sections": [{
            "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
            "weight": 1,
            "metrics": [{"label": "Import cover", "value": "6.25", "sub": None}],
        }],
    })

    _stamp_import_cover_sub(brief, raw)

    assert brief.sections[0].metrics[0].sub == "reserves 31 Jul ÷ Mar import bill"


def test_stamp_real_policy_rate_sub_reads_a_raw_label_the_builder_recased() -> None:
    """Normalization must apply to the RAW side of the lookup too, not only
    the published side."""
    from brief.pipeline_v6 import _stamp_real_policy_rate_sub

    raw = [{
        "slug": "macro",
        "metrics": [{"label": "  REAL POLICY RATE ", "value": 1.18, "source": _RPR_NOTE}],
    }]
    brief = _macro_brief_with_real_policy_rate_sub(None)

    _stamp_real_policy_rate_sub(brief, raw)

    assert brief.sections[0].metrics[0].sub == _RPR_SUB


# ── P2 fact-checker (2026-08-22 audit #204) — prose-number gate wiring ──────


def test_run_publish_warns_but_still_ships_a_stale_flash_figure_by_default(
    _stub_supabase_reads: object, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round-2 review reshape: `check_metric_sub_numbers`/`check_metric_value_vs_raw`
    are WARN-mode by default (25-real-issue corpus replay showed 0.6%
    precision when this held the publish). The audit #204 failure ('$2.82bn'
    quoted on a real 2858.68mn builder value) now surfaces as a Discord
    alert + log line, but the issue STILL ships — unlike the denylist check,
    which still hard-fails."""
    monkeypatch.delenv("BRIEF_PROSE_VALIDATOR_STRICT", raising=False)
    from brief.schema import Metric, SectionData

    sections = [SectionData(
        id="remit", title="Remittance", freshness="fresh",
        metrics=[Metric(
            id="remit_monthly_mn", label="Monthly Remittance", value=2858.68,
            unit="mn USD", as_of=date(2026, 7, 31), source="BB", cadence="monthly",
        )],
    )]
    tainted = {
        "brief": {"issue_no": 89, "volume": 1, "brief_date": "2026-08-22",
                  "todays_call": "Today's brief is shipping.", "status": "published"},
        "sections": [{
            "slug": "remit", "ord": 11, "title": "Remittance", "group_key": "markets",
            "weight": 1,
            "metrics": [{
                "label": "Monthly Remittance", "value": "$2.86bn",
                "sub": "$2.82bn — July final",
            }],
            "news": [], "summary_pills": [],
        }],
    }
    review = {"verdict": "pass", "issues": [], "revised_brief": None}

    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief", return_value="brief-id-89") as mock_pub, \
         patch("brief.pipeline_v6._alert") as mock_alert:
        mock_run.side_effect = [_max_result(tainted), _max_result(review)]
        brief_id = run_publish(sections, today=date(2026, 8, 22), scraped_headlines=[])

    assert brief_id == "brief-id-89"
    mock_pub.assert_called_once()
    # Filtered against `_alert` calls, not asserted as the ONLY calls — this
    # fixture's "bb"-less sections list also triggers the UNRELATED protected-
    # metric degradation alert (3 calls, pre-existing behaviour). ONE grouped
    # prose-number alert (H3), not one per warning, is what this test proves.
    prose_alerts = [c for c in mock_alert.call_args_list if "prose-number gate" in c.args[0]]
    assert len(prose_alerts) == 1
    assert "$2.82bn" in prose_alerts[0].args[0]


def test_run_publish_holds_on_a_sourceless_count_claim(
    _stub_supabase_reads: object,
) -> None:
    """The ONLY BLOCK-mode surface left post-round-2: a sourceless
    "fourteen reads" style count-claim still holds the publish."""
    from brief.pipeline_v6 import ProseNumberGateError
    from brief.schema import SectionData

    sections = [SectionData(id="fiscal", title="Fiscal", freshness="fresh")]
    tainted = {
        "brief": {"issue_no": 89, "volume": 1, "brief_date": "2026-08-22",
                  "todays_call": "Today's brief is shipping.", "status": "published"},
        "sections": [{
            "slug": "fiscal", "ord": 8, "title": "Fiscal", "group_key": "policy",
            "weight": 1,
            "verdict": "Flat across fourteen reads — no new monthly print.",
            "news": [], "summary_pills": [],
        }],
    }
    review = {"verdict": "pass", "issues": [], "revised_brief": None}

    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief") as mock_pub:
        mock_run.side_effect = [_max_result(tainted), _max_result(review)]
        with pytest.raises(ProseNumberGateError):
            run_publish(sections, today=date(2026, 8, 22), scraped_headlines=[])

    mock_pub.assert_not_called()


def _dse_editor_output(verdict: str) -> dict:
    return {
        "brief": {"issue_no": 89, "volume": 1, "brief_date": "2026-08-25",
                  "todays_call": "Today's brief is shipping.", "status": "published"},
        "sections": [{
            "slug": "dse", "ord": 6, "title": "DSE Markets", "group_key": "markets",
            "weight": 1,
            "verdict": verdict,
            "news": [], "summary_pills": [],
        }],
    }


def _session_low_fact(rank: int):
    from brief.history_anchors import HistoryFact

    return HistoryFact(
        metric_id="dsex",
        kind="since_lower",
        phrase=f"a {rank}-session low (5,601.44 on 22 Jun the last lower close)",
        reference_value=5601.44,
        reference_value_formatted="5,601.44",
        reference_as_of="2026-06-22",
    )


def test_run_publish_holds_on_a_fabricated_dse_session_low(
    _stub_supabase_reads: object,
) -> None:
    """The 2026-08-28 owner-approved promotion, proven through the FULL gate
    path rather than the check in isolation: a `dse` hyphenated count claim
    that matches no machine-supplied rank raises the SAME
    `ProseNumberGateError` (a `V6PublishError`, exit code 4 — AGENTS.md
    landmine 34) the sourceless count-claim BLOCK raises, and nothing is
    published. The pipeline hands `dse` a real 42-session fact here; the
    editor prints "ten-session" anyway — issue 205-208's actual defect."""
    from brief.pipeline_v6 import ProseNumberGateError
    from brief.schema import SectionData

    def _fake_fetch(*, today, http, supabase_url, service_key, history_facts_out=None):
        if history_facts_out is not None:
            history_facts_out.setdefault("dse", []).append(_session_low_fact(42))
        return {}

    sections = [SectionData(id="dse", title="DSE Markets", freshness="fresh")]
    review = {"verdict": "pass", "issues": [], "revised_brief": None}

    with patch("brief.pipeline_v6._fetch_series_summaries", side_effect=_fake_fetch), \
         patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief") as mock_pub:
        mock_run.side_effect = [
            _max_result(_dse_editor_output(
                "DSEX grinds to a ten-session low on drained turnover.")),
            _max_result(review),
        ]
        with pytest.raises(ProseNumberGateError, match=r"ten-session low"):
            run_publish(sections, today=date(2026, 8, 25), scraped_headlines=[])

    mock_pub.assert_not_called()
    assert issubclass(ProseNumberGateError, V6PublishError)


def test_run_publish_ships_the_dse_session_low_the_pipeline_actually_supplied(
    _stub_supabase_reads: object,
) -> None:
    """The companion that keeps the BLOCK honest rather than absolute: when
    the editor inlines the rank the pipeline COMPUTED for it, the same gate
    passes and the edition publishes. If this test ever fails, the promotion
    has started holding correct briefs."""
    from brief.schema import SectionData

    def _fake_fetch(*, today, http, supabase_url, service_key, history_facts_out=None):
        if history_facts_out is not None:
            history_facts_out.setdefault("dse", []).append(_session_low_fact(42))
        return {}

    sections = [SectionData(id="dse", title="DSE Markets", freshness="fresh")]
    review = {"verdict": "pass", "issues": [], "revised_brief": None}

    with patch("brief.pipeline_v6._fetch_series_summaries", side_effect=_fake_fetch), \
         patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief", return_value="brief-id-89") as mock_pub:
        mock_run.side_effect = [
            _max_result(_dse_editor_output(
                "DSEX grinds to a 42-session low on drained turnover.")),
            _max_result(review),
        ]
        brief_id = run_publish(sections, today=date(2026, 8, 25), scraped_headlines=[])

    assert brief_id == "brief-id-89"
    mock_pub.assert_called_once()


def test_run_publish_ships_a_sub_that_traces_to_the_real_builder_value(
    _stub_supabase_reads: object,
) -> None:
    """Sanity companion: the honest figure ($2.86bn, matching 2858.68mn)
    produces no warnings at all."""
    from brief.schema import Metric, SectionData

    sections = [SectionData(
        id="remit", title="Remittance", freshness="fresh",
        metrics=[Metric(
            id="remit_monthly_mn", label="Monthly Remittance", value=2858.68,
            unit="mn USD", as_of=date(2026, 7, 31), source="BB", cadence="monthly",
        )],
    )]
    clean = {
        "brief": {"issue_no": 89, "volume": 1, "brief_date": "2026-08-22",
                  "todays_call": "Today's brief is shipping.", "status": "published"},
        "sections": [{
            "slug": "remit", "ord": 11, "title": "Remittance", "group_key": "markets",
            "weight": 1,
            "metrics": [{
                "label": "Monthly Remittance", "value": "$2.86bn",
                "sub": "$2.86bn — Jul final",
            }],
            "news": [], "summary_pills": [],
        }],
    }
    review = {"verdict": "pass", "issues": [], "revised_brief": None}

    with patch("brief.pipeline_v6.run_max") as mock_run, \
         patch("brief.pipeline_v6.publish_brief", return_value="brief-id-89") as mock_pub, \
         patch("brief.pipeline_v6._alert") as mock_alert:
        mock_run.side_effect = [_max_result(clean), _max_result(review)]
        brief_id = run_publish(sections, today=date(2026, 8, 22), scraped_headlines=[])

    assert brief_id == "brief-id-89"
    mock_pub.assert_called_once()
    # Same filtering as above — this fixture also fires the unrelated
    # protected-metric degradation alert; no prose-number alert is the point.
    prose_alerts = [c for c in mock_alert.call_args_list if "prose-number gate" in c.args[0]]
    assert prose_alerts == []


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
