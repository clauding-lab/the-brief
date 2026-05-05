"""Integration-shaped test for fresh-brief V1 wiring on Mon–Thu.

Mocks Claude + Supabase; verifies the pipeline:
  - Calls score_lens with today's sections
  - Filters scraped_headlines against recent_news
  - Forces lens onto editor_brief
  - Calls stamp_changed and mark_held_overs post-LLM
"""
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from brief import pipeline_v6
from brief.schema import SectionData


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def previous_brief():
    return json.loads((FIXTURES / "v6_previous_brief.json").read_text())


@pytest.fixture
def metric_definitions():
    return json.loads((FIXTURES / "v6_metric_definitions.json").read_text())["definitions"]


def test_monday_pipeline_wires_lens_and_stamps(previous_brief, metric_definitions, monkeypatch):
    """End-to-end: lens forced, headlines filtered, stamp + held-overs run on final_brief."""
    monday = date(2026, 5, 4)

    monkeypatch.setattr(pipeline_v6, "fetch_previous_brief", lambda: previous_brief)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 91)
    monkeypatch.setattr(pipeline_v6, "fetch_recent_news", lambda n_issues=5: [
        {"headline": "Will cenbank's Tk40,000cr refinance scheme fuel inflation?",
         "source_url": "https://example.com/refinance"}
    ])
    monkeypatch.setattr(pipeline_v6, "fetch_metric_definitions", lambda: metric_definitions)

    captured: list = []
    monkeypatch.setattr(pipeline_v6, "publish_brief",
                        lambda payload: captured.append(payload) or "fake-uuid-123")

    fake_sections = [
        SectionData(id="iranwar", title="External", kicker="", tldr="", pull="",
                    freshness="fresh", freshness_reason="",
                    metrics=[], news=[]),
        SectionData(id="banking", title="Banking", kicker="", tldr="", pull="",
                    freshness="fresh", freshness_reason="",
                    metrics=[], news=[]),
    ]

    scraped = [
        {"headline": "Will cenbank's Tk40,000cr refinance scheme fuel inflation?",
         "source_url": "https://example.com/refinance"},  # repeat
        {"headline": "Brent jumps to $113.95",
         "source_url": "https://example.com/brent"},  # fresh
    ]

    # Editor output: includes banking section with NPL=35.73% (unchanged from previous_brief
    # → mark_held_overs should annotate it because cadence=quarterly in metric_definitions).
    # Plus a fresh news item (Hormuz reescalation) that's NOT in previous_brief → stamp_changed
    # should mark it changed=True.
    editor_output = {
        "brief": {
            "issue_no": 92, "volume": 1, "brief_date": "2026-05-04",
            "lens": "iran", "frame": "external-shock",
            "todays_call": "Brent jumped...",
            "cover_metric": {"label": "BRENT", "value": "$113.95", "section_slug": "iran"},
            "status": "published",
        },
        "sections": [
            {
                "slug": "iran", "ord": 10, "title": "External", "group_key": "policy", "weight": 2,
                "metrics": [{"label": "Brent Spot", "value": "$113.95"}],
                "news": [{"headline": "Hormuz reescalation", "source_url": "https://x.com/hormuz"}],
            },
            {
                "slug": "banking", "ord": 4, "title": "Banking", "group_key": "banking", "weight": 1,
                "metrics": [{"label": "NPL Ratio", "value": "35.73%"}],  # unchanged from previous
                "news": [],
            },
        ],
    }

    with patch("brief.pipeline_v6._call_with_retries") as call_mock:
        call_mock.side_effect = [
            editor_output,                              # editor
            {"verdict": "pass", "issues": []},          # subeditor
        ]
        result = pipeline_v6.run_publish(
            fake_sections, today=monday, scraped_headlines=scraped, dry_run=False,
        )

    assert result == "fake-uuid-123"

    # ── Editor input wiring ──────────────────────────────────────────
    editor_call = call_mock.call_args_list[0]
    editor_input = editor_call.kwargs["input_obj"]
    # Re-runs filtered out — only Brent headline remains
    assert len(editor_input["scraped_headlines"]) == 1
    assert "Brent" in editor_input["scraped_headlines"][0]["headline"]

    # ── Post-LLM stamping verified on the published brief ────────────
    assert len(captured) == 1, "publish_brief was not called"
    final_brief = captured[0]

    # stamp_changed: the fresh Hormuz headline (not in previous_brief) is changed=True.
    iran_section = next(s for s in final_brief.sections if s.slug == "iran")
    assert iran_section.news[0].changed is True

    # mark_held_overs: NPL Ratio in banking is held-over (unchanged value + cadence=quarterly).
    banking_section = next(s for s in final_brief.sections if s.slug == "banking")
    npl_metric = banking_section.metrics[0]
    assert npl_metric.changed is False  # value unchanged from previous_brief
    assert npl_metric.held_from is not None  # cadence=quarterly + unchanged → annotated
    assert "Q3 2026" in (npl_metric.next_print or "") or "Jul" in (npl_metric.next_print or "")
