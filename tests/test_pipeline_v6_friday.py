"""Friday branch test — verifies pipeline_v6 routes to editor_v6_friday on Fri."""
from datetime import date
from unittest.mock import patch

import pytest

from brief import pipeline_v6
from brief.schema import SectionData


def test_friday_uses_friday_prompt(monkeypatch):
    friday = date(2026, 5, 8)  # Friday

    monkeypatch.setattr(pipeline_v6, "fetch_previous_brief", lambda: None)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 95)
    monkeypatch.setattr(pipeline_v6, "fetch_recent_news", lambda n_issues=5: [])
    monkeypatch.setattr(pipeline_v6, "fetch_metric_definitions", lambda: [])
    monkeypatch.setattr(pipeline_v6, "publish_brief", lambda payload: "fake-uuid-friday")

    fake_sections = [SectionData(
        id="iranwar", title="External", kicker="", tldr="", pull="",
        freshness="fresh", freshness_reason="", metrics=[], news=[],
    )]

    fake_editor_out = {
        "brief": {"issue_no": 96, "volume": 1, "brief_date": "2026-05-08",
                  "lens": "weekly_wrap", "frame": "weekly-wrap",
                  "todays_call": "Wrap...", "status": "published",
                  "cover_metric": {"label": "X", "value": "y", "section_slug": "iran"}},
        "sections": [{"slug": "iran", "ord": 10, "title": "External", "group_key": "policy", "weight": 2}],
    }

    with patch("brief.pipeline_v6._call_with_retries") as call_mock, \
         patch("brief.pipeline_v6._pipeline._load_prompt") as load_prompt:
        call_mock.side_effect = [fake_editor_out, {"verdict": "pass", "issues": []}]
        load_prompt.return_value = "FAKE_PROMPT_BODY"
        result = pipeline_v6.run_publish(fake_sections, today=friday, dry_run=False)

    assert result == "fake-uuid-friday"
    # Verify Friday prompt was loaded
    prompt_files_loaded = [c.args[0] for c in load_prompt.call_args_list]
    assert "editor_v6_friday.txt" in prompt_files_loaded
    # Verify weekly_diffs block was added
    editor_call_input = call_mock.call_args_list[0].kwargs["input_obj"]
    assert "weekly_diffs" in editor_call_input
    assert editor_call_input["today_lens"] == "weekly_wrap"
