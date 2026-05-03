"""V4 pipeline integration tests -- Phase 4B exit gate (Task 4B.16).

Verifies that run() produces well-formed V4 HTML and a clean plain-text
email digest across three scenarios:
  1. Full happy path with 12 sections on the risk map (exec + headlines excluded).
  2. Risk map fallback (invalid Claude response) -- HTML still well-formed.
  3. todays_call failure -- email has graceful fallback text.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from brief.builders import ALL_BUILDER_IDS
from brief.claude.max_client import MaxCallResult
from brief.pipeline import PipelineConfig, run

# Reuse helpers from the existing integration test suite
from tests.test_pipeline_integration import (
    _fake_curation,
    _fake_insights,
    _fake_insights_stale,
    _fake_signals,
)

# ---------------------------------------------------------------------------
# Extra fakes
# ---------------------------------------------------------------------------

_RISK_MAP_IDS = ["bb", "macro", "fx", "remit", "dse", "tbond", "iranwar", "comm", "banking", "dam", "fiscal", "nbr"]


def _fake_risk_map_full():
    """12 section IDs plotted (exec + headlines excluded); type sampled to cover all enum variants."""
    types_map = {
        "bb": "anchor", "macro": "anchor", "iranwar": "event",
        "dse": "fresh", "fx": "fresh", "banking": "fresh",
        "remit": "slow", "tbond": "slow", "comm": "slow",
        "dam": "slow", "fiscal": "slow", "nbr": "slow",
    }
    sections = [
        {
            "section_id": sid,
            "x": 3.0,
            "y": 5.0,
            "r": 30,
            "type": types_map.get(sid, "slow"),
            "hero_metric_id": None,
        }
        for sid in _RISK_MAP_IDS
    ]
    read_order = list(_RISK_MAP_IDS)
    return MaxCallResult(
        raw_text="{}",
        parsed={"sections": sections, "read_order": read_order},
        usage={}, total_cost_usd=0,
    )


_FAKE_V4_CALL_TEXT = (
    # V5 validator requires 60-100 words.
    "Bangladesh policy rate held steady as gross reserves edged upward for a "
    "second consecutive week narrowing the external financing gap while food CPI "
    "remained elevated above ten percent adding pressure to the import bill and "
    "squeezing NIM on floating-rate books. Hormuz tensions priced into oil not "
    "supply — hedge exposure in the commodity-linked trade finance book before "
    "the next print arrives and do not add duration to fixed-rate portfolios now."
)


def _fake_todays_call_ok():
    return MaxCallResult(
        raw_text="{}",
        parsed={"text": _FAKE_V4_CALL_TEXT, "byline": "Desk Editor · The Brief"},
        usage={}, total_cost_usd=0,
    )


def _fake_risk_map_invalid():
    return MaxCallResult(
        raw_text="{}",
        parsed={"sections": [], "read_order": []},
        usage={}, total_cost_usd=0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_run_produces_v4_html_and_email(fixture_snapshot, today):
    """Happy path: 12 sections on risk map (exec + headlines excluded), valid risk map + todays_call."""
    cfg = PipelineConfig(today=today, enable_history=False, enable_headlines=False)
    with patch("brief.pipeline.run_max") as mx:
        mx.side_effect = [
            _fake_curation([]),
            _fake_signals(),
            _fake_insights(),
            _fake_insights_stale(),
            _fake_risk_map_full(),
            _fake_todays_call_ok(),
        ]
        result = run(cfg, shell_path=None, snapshot_override=fixture_snapshot)

    html = result.html

    # DOCTYPE preserved
    assert html.startswith("<!DOCTYPE html>") or html.startswith("<!doctype html>")

    # Front-door blocks present
    assert 'class="dateline"' in html
    assert 'class="masthead"' in html
    assert 'class="risk-map' in html
    assert 'class="flow-index"' in html
    assert 'class="colophon"' in html

    # Every rendered section appears (13 numbered -- exec is not a standalone section)
    for sid in [
        "headlines", "bb", "banking", "dse", "tbond", "fx",
        "macro", "dam", "comm", "remit", "iranwar", "fiscal", "nbr",
    ]:
        assert f'id="section-{sid}"' in html, f"section-{sid} missing from V4 HTML"

    # No V1 leftover strings
    assert "OLD_BB_BODY" not in html
    assert "SectionRMG" not in html

    # No unreplaced SPLICE placeholders
    assert "<!-- SPLICE:" not in html

    # email_text field is populated
    email = result.email_text
    assert email, "email_text should be non-empty"

    assert "THE BRIEF" in email
    assert "TODAY'S CALL" in email
    assert "Bangladesh policy rate held steady" in email
    assert "TOP 3 SIGNALS" in email
    assert "Full edition" in email

    # No HTML tags in email
    for forbidden in ["<div", "<p>", "<span", "<html"]:
        assert forbidden not in email, f"HTML tag {forbidden!r} found in email digest"


@pytest.mark.integration
def test_run_v4_html_email_with_risk_map_fallback(fixture_snapshot, today):
    """When risk map Claude call fails, deterministic fallback fires and HTML is still well-formed."""
    cfg = PipelineConfig(today=today, enable_history=False, enable_headlines=False)
    with patch("brief.pipeline.run_max") as mx:
        mx.side_effect = [
            _fake_curation([]),
            _fake_signals(),
            _fake_insights(),
            _fake_insights_stale(),
            _fake_risk_map_invalid(),   # invalid -> fallback fires
            _fake_todays_call_ok(),
        ]
        result = run(cfg, shell_path=None, snapshot_override=fixture_snapshot)

    # Fallback produces 12 coords (exec + headlines excluded)
    assert len(result.map_coords) == 12

    # HTML is well-formed (DOCTYPE present, no unreplaced SPLICEs)
    assert result.html.startswith("<!DOCTYPE html>") or result.html.startswith("<!doctype html>")
    assert "<!-- SPLICE:" not in result.html
    assert 'class="risk-map' in result.html

    # email digest still coherent
    assert "THE BRIEF" in result.email_text
    assert "TODAY'S CALL" in result.email_text
    assert "Full edition" in result.email_text


@pytest.mark.integration
def test_v4_email_handles_missing_todays_call(fixture_snapshot, today):
    """When todays_call Claude call fails, deterministic fallback fires and email is still coherent."""
    from brief.claude.max_client import MaxCallError

    cfg = PipelineConfig(today=today, enable_history=False, enable_headlines=False)

    # First 5 calls succeed; the 6th (todays_call) raises MaxCallError
    call_counter = {"n": 0}
    responses = [
        _fake_curation([]),
        _fake_signals(),
        _fake_insights(),
        _fake_insights_stale(),
        _fake_risk_map_full(),
    ]

    def _side_effect(*args, **kwargs):
        idx = call_counter["n"]
        call_counter["n"] += 1
        if idx < len(responses):
            return responses[idx]
        raise MaxCallError("todays_call timed out")

    with patch("brief.pipeline.run_max", side_effect=_side_effect):
        result = run(cfg, shell_path=None, snapshot_override=fixture_snapshot)

    # todays_call should be the deterministic fallback (not None)
    assert result.todays_call is not None

    email = result.email_text
    assert "TODAY'S CALL" in email
    # Fallback text from _fallback_todays_call -- should be non-empty
    assert email.count("TODAY'S CALL") >= 1

    # Email still structurally complete
    assert "THE BRIEF" in email
    assert "Full edition" in email

    # HTML still rendered without crash
    assert "<!-- SPLICE:" not in result.html


@pytest.mark.integration
def test_call_reports_include_cost_and_duration(fixture_snapshot, today):
    """Every call_report entry must carry cost_usd (float), duration_s (float), and tokens (dict)."""
    from brief.claude.max_client import MaxCallResult

    known_cost = 0.0123
    known_duration = 1.5
    known_tokens = {"input": 200, "output": 80}

    def _make_result(parsed):
        return MaxCallResult(
            raw_text="{}",
            parsed=parsed,
            usage={"input_tokens": 200, "output_tokens": 80},
            total_cost_usd=known_cost,
            duration_s=known_duration,
            tokens=known_tokens,
        )

    _RISK_MAP_IDS_LOCAL = ["bb", "macro", "fx", "remit", "dse", "tbond", "iranwar", "comm", "banking", "dam", "fiscal", "nbr"]

    responses = [
        _make_result({"selected": [], "rationale_bullet": "x"}),
        _make_result({"signals": [{"direction": "bull", "text": "ok", "section_anchor": "bb"}], "traffic_status": "neu"}),
        _make_result({"insights": {"fx": ["one", "two", "three", "four"]}}),
        _make_result({"insights": {"bb": ["stale note"]}}),
        _make_result({
            "sections": [
                {"section_id": sid, "x": 3.0, "y": 5.0, "r": 30, "type": "slow", "hero_metric_id": None}
                for sid in _RISK_MAP_IDS_LOCAL
            ],
            "read_order": list(_RISK_MAP_IDS_LOCAL),
        }),
        _make_result({"text": "Test call text."}),
    ]

    cfg = PipelineConfig(today=today, enable_history=False, enable_headlines=False)
    with patch("brief.pipeline.run_max", side_effect=responses):
        result = run(cfg, shell_path=None, snapshot_override=fixture_snapshot)

    assert len(result.call_reports) == 6, f"Expected 6 call_reports, got {len(result.call_reports)}"

    total_cost = 0.0
    for entry in result.call_reports:
        assert "cost_usd" in entry, f"Missing cost_usd in {entry['name']}"
        assert "duration_s" in entry, f"Missing duration_s in {entry['name']}"
        assert "tokens" in entry, f"Missing tokens in {entry['name']}"
        assert isinstance(entry["cost_usd"], float), f"cost_usd not float in {entry['name']}"
        assert isinstance(entry["duration_s"], float), f"duration_s not float in {entry['name']}"
        assert isinstance(entry["tokens"], dict), f"tokens not dict in {entry['name']}"
        assert "input" in entry["tokens"]
        assert "output" in entry["tokens"]
        total_cost += entry["cost_usd"]

    assert total_cost == pytest.approx(known_cost * 6)
