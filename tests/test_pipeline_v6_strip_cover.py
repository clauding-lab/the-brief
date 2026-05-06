"""Auto-suppress cover_metric when every hero-section metric is unchanged.

Bug context: even with Patches 1+2+3 shipped, on quiet days where every
banking metric is held (NPL=35.73% repeated across 5 issues, CAR=1.56%
likewise), the editor is still forced to pick one of them as cover_metric
because banking is the lens. The user-visible result is the same NPL repeat.

Fix: after stamp_changed runs, if every metric in the hero section
(weight=2) is changed=False (i.e., value identical to previous brief),
strip cover_metric to None. The SPA's Cover component already null-handles
this; hides the big-number block. Brief opens with masthead → headlines.

`stamp_changed` runs on `(slug, label)` keys — same logic the editor sees
via is_held_over from Patch 2. Cold starts (previous_brief=None) are
unaffected: stamp_changed marks everything changed=True for cold start,
so this strip never fires.
"""
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from brief import pipeline_v6
from brief.schema import Metric, SectionData

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def metric_definitions():
    return json.loads((FIXTURES / "v6_metric_definitions.json").read_text())["definitions"]


def _make_previous_brief() -> dict:
    return {
        "brief": {
            "issue_no": 92,
            "volume": 1,
            "brief_date": "2026-05-05",
            "lens": "banking",
            "frame": "credit-cycle",
            "status": "published",
        },
        "sections": [
            {
                "slug": "banking",
                "metrics": [
                    {"label": "NPL Ratio", "value": "35.73%"},
                    {"label": "CAR", "value": "1.56%"},
                ],
                "news": [],
            }
        ],
    }


def _editor_output_with_banking_hero(npl_value: str, car_value: str, cover_value: str) -> dict:
    """Mock editor brief: banking hero with NPL+CAR, cover_metric on banking."""
    return {
        "brief": {
            "issue_no": 93, "volume": 1, "brief_date": "2026-05-06",
            "lens": "banking", "frame": "credit-cycle",
            "todays_call": "Banking distress remains the dominant risk.",
            "cover_metric": {
                "label": "NPL RATIO · Q4 2025",
                "value": cover_value,
                "section_slug": "banking",
                "tone": "bear",
                "as_of": "Q4 2025 · BB",
            },
            "status": "published",
        },
        "sections": [
            {
                "slug": "banking", "ord": 4, "title": "Banking",
                "group_key": "banking", "weight": 2,
                "metrics": [
                    {"label": "NPL Ratio", "value": npl_value},
                    {"label": "CAR", "value": car_value},
                ],
                "news": [],
            },
        ],
    }


def _run_with_mocked_llms(monkeypatch, previous, editor_output, metric_defs,
                          v5_npl_value="35.73%", v5_car_value="1.56%"):
    """Drive run_publish through to publish, capturing the final brief.

    `v5_npl_value` and `v5_car_value` set what the V5 builder emits to the
    pipeline (matters for stamp_changed's prev-vs-current diff). Defaults
    are the stuck values; tests override them when simulating movement.
    """
    monday = date(2026, 5, 6)

    monkeypatch.setattr(pipeline_v6, "fetch_previous_brief", lambda: previous)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 92)
    monkeypatch.setattr(pipeline_v6, "fetch_recent_news", lambda n_issues=5: [])
    monkeypatch.setattr(pipeline_v6, "fetch_metric_definitions", lambda: metric_defs)

    captured: list = []
    monkeypatch.setattr(
        pipeline_v6, "publish_brief",
        lambda payload: captured.append(payload) or "fake-uuid",
    )

    fake_sections = [
        SectionData(
            id="banking", title="Banking", kicker="", tldr="", pull="",
            freshness="fresh", freshness_reason="",
            metrics=[
                Metric(id="banking_npl_pct", label="NPL Ratio",
                       value=v5_npl_value,
                       unit="pct", as_of=date(2026, 1, 1), source="BB", cadence="quarterly"),
                Metric(id="banking_car_pct", label="CAR",
                       value=v5_car_value,
                       unit="pct", as_of=date(2026, 1, 1), source="BB", cadence="quarterly"),
            ],
            news=[],
        ),
    ]

    with patch("brief.pipeline_v6._call_with_retries") as call_mock:
        call_mock.side_effect = [editor_output, {"verdict": "pass", "issues": []}]
        pipeline_v6.run_publish(
            fake_sections, today=monday, scraped_headlines=[], dry_run=False,
        )

    assert len(captured) == 1, "publish_brief was not called"
    return captured[0]


def test_cover_metric_stripped_when_all_hero_metrics_unchanged(monkeypatch, metric_definitions):
    """The user-visible regression: NPL=35.73% and CAR=1.56% unchanged from
    Issue 92 → both metrics get changed=False → strip cover_metric to None.
    """
    previous = _make_previous_brief()
    editor_output = _editor_output_with_banking_hero(
        npl_value="35.73%", car_value="1.56%", cover_value="35.73%",
    )
    final_brief = _run_with_mocked_llms(monkeypatch, previous, editor_output, metric_definitions)

    assert final_brief.brief.cover_metric is None, \
        f"cover_metric should be stripped when every hero metric is unchanged; got {final_brief.brief.cover_metric}"


def test_cover_metric_preserved_when_one_hero_metric_changed(monkeypatch, metric_definitions):
    """Symmetry: NPL stuck but CAR moved → cover_metric preserved.
    The editor can pick the moved metric (CAR) as cover, or even keep NPL
    if narrative-driven; we just don't auto-strip."""
    previous = _make_previous_brief()
    editor_output = _editor_output_with_banking_hero(
        npl_value="35.73%", car_value="2.10%", cover_value="2.10%",  # CAR moved
    )
    final_brief = _run_with_mocked_llms(
        monkeypatch, previous, editor_output, metric_definitions,
        v5_npl_value="35.73%", v5_car_value="2.10%",  # V5 emits the moved values too
    )

    assert final_brief.brief.cover_metric is not None, \
        "cover_metric should be preserved when at least one hero metric changed"


def test_cover_metric_preserved_when_all_hero_metrics_changed(monkeypatch, metric_definitions):
    """Both NPL and CAR moved → no auto-strip."""
    previous = _make_previous_brief()
    editor_output = _editor_output_with_banking_hero(
        npl_value="33.0%", car_value="2.10%", cover_value="33.0%",
    )
    final_brief = _run_with_mocked_llms(
        monkeypatch, previous, editor_output, metric_definitions,
        v5_npl_value="33.0%", v5_car_value="2.10%",
    )

    assert final_brief.brief.cover_metric is not None
    assert final_brief.brief.cover_metric.value == "33.0%"


def test_cover_metric_preserved_on_cold_start(monkeypatch, metric_definitions):
    """previous_brief=None means stamp_changed marks every metric as
    changed=True (cold start) → strip never fires → cover_metric preserved."""
    editor_output = _editor_output_with_banking_hero(
        npl_value="35.73%", car_value="1.56%", cover_value="35.73%",
    )
    final_brief = _run_with_mocked_llms(monkeypatch, None, editor_output, metric_definitions)

    assert final_brief.brief.cover_metric is not None, \
        "cold start: nothing is held → cover preserved"


def test_cover_metric_preserved_when_hero_section_has_no_metrics(monkeypatch, metric_definitions):
    """Defensive: if the hero section has zero metrics (unusual), don't strip."""
    previous = _make_previous_brief()
    editor_output = _editor_output_with_banking_hero(
        npl_value="35.73%", car_value="1.56%", cover_value="35.73%",
    )
    # Strip metrics from the editor's brief
    editor_output["sections"][0]["metrics"] = []
    final_brief = _run_with_mocked_llms(monkeypatch, previous, editor_output, metric_definitions)

    assert final_brief.brief.cover_metric is not None, \
        "empty hero metrics → no strip (no signal of all-held)"
