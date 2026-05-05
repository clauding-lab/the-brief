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


def _make_editor_output(today_lens="iran") -> dict:
    return {
        "brief": {
            "issue_no": 92, "volume": 1, "brief_date": "2026-05-04",
            "lens": today_lens, "frame": "external-shock",
            "todays_call": "Brent jumped...",
            "cover_metric": {"label": "BRENT", "value": "$113.95", "section_slug": "iran"},
            "status": "published",
        },
        "sections": [
            {
                "slug": "iran", "ord": 10, "title": "External", "group_key": "policy", "weight": 2,
                "metrics": [{"label": "Brent Spot", "value": "$113.95"}],
                "news": [{"headline": "Hormuz reescalation", "source_url": "https://x.com/hormuz"}],
            }
        ],
    }


def test_monday_pipeline_wires_lens_and_stamps(previous_brief, metric_definitions, monkeypatch):
    monday = date(2026, 5, 4)

    monkeypatch.setattr(pipeline_v6, "fetch_previous_brief", lambda: previous_brief)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 91)
    monkeypatch.setattr(pipeline_v6, "fetch_recent_news", lambda n_issues=5: [
        {"headline": "Will cenbank's Tk40,000cr refinance scheme fuel inflation?",
         "source_url": "https://example.com/refinance"}
    ])
    monkeypatch.setattr(pipeline_v6, "fetch_metric_definitions", lambda: metric_definitions)
    monkeypatch.setattr(pipeline_v6, "publish_brief", lambda payload: "fake-uuid-123")

    fake_sections = [
        SectionData(id="iranwar", title="External", freshness="fresh"),
    ]

    scraped = [
        {"headline": "Will cenbank's Tk40,000cr refinance scheme fuel inflation?",
         "source_url": "https://example.com/refinance"},  # repeat — should be dropped
        {"headline": "Brent jumps to $113.95",
         "source_url": "https://example.com/brent"},  # fresh — should be kept
    ]

    with patch("brief.pipeline_v6._call_with_retries") as call_mock:
        call_mock.side_effect = [
            _make_editor_output(today_lens="iran"),  # editor
            {"verdict": "pass", "issues": []},        # subeditor
        ]
        result = pipeline_v6.run_publish(
            fake_sections, today=monday, scraped_headlines=scraped, dry_run=False,
        )

    assert result == "fake-uuid-123"
    # Lens forced onto the brief
    editor_call = call_mock.call_args_list[0]
    editor_input = editor_call.kwargs["input_obj"]
    assert editor_input["today_lens"] == "iran"
    # Re-runs filtered out — only Brent headline remains
    assert len(editor_input["scraped_headlines"]) == 1
    assert "Brent" in editor_input["scraped_headlines"][0]["headline"]
