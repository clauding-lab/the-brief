"""Unit tests for stamp_changed and mark_held_overs."""
import json
from pathlib import Path

import pytest

from brief.builders.diff import stamp_changed
from brief.v6_schema import BriefPayloadV6, NewsItemV6, MetricV6, SectionV6, BriefV6


FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def previous_brief() -> dict:
    return json.loads((FIXTURES / "v6_previous_brief.json").read_text())


def _make_brief(metrics_by_section: dict[str, list[dict]], news_by_section: dict[str, list[dict]]) -> BriefPayloadV6:
    sections = []
    for slug, metrics in metrics_by_section.items():
        sections.append(SectionV6(
            slug=slug,
            ord=1,
            title=slug.title(),
            group_key="banking" if slug in ("banking", "bb") else "markets",
            metrics=[MetricV6(**m) for m in metrics],
            news=[NewsItemV6(**n) for n in news_by_section.get(slug, [])],
        ))
    for slug, news in news_by_section.items():
        if slug not in metrics_by_section:
            sections.append(SectionV6(
                slug=slug,
                ord=1,
                title=slug.title(),
                group_key="banking" if slug in ("banking", "bb") else "markets",
                metrics=[],
                news=[NewsItemV6(**n) for n in news],
            ))
    return BriefPayloadV6(
        brief=BriefV6(issue_no=91, volume=1, brief_date="2026-05-05"),
        sections=sections,
    )


def test_metric_value_unchanged_marked_false(previous_brief):
    """NPL 35.73% in both briefs → changed=False."""
    current = _make_brief({"banking": [{"label": "NPL Ratio", "value": "35.73%"}]}, {})
    stamp_changed(current, previous_brief)
    assert current.sections[0].metrics[0].changed is False


def test_metric_value_moved_marked_true(previous_brief):
    """Brent moved $107.56 → $113.95 → changed=True."""
    current = _make_brief({"iran": [{"label": "Brent Spot", "value": "$113.95"}]}, {})
    stamp_changed(current, previous_brief)
    assert current.sections[0].metrics[0].changed is True


def test_metric_new_marked_true(previous_brief):
    """A metric that didn't exist before → changed=True."""
    current = _make_brief({"banking": [{"label": "Reserve Money", "value": "Tk 4.2tn"}]}, {})
    stamp_changed(current, previous_brief)
    assert current.sections[0].metrics[0].changed is True


def test_news_exact_match_marked_false(previous_brief):
    """Same headline + same URL → changed=False (this is the bug we're fixing)."""
    current = _make_brief({}, {"banking": [
        {"headline": "Will cenbank's Tk40,000cr refinance scheme fuel inflation?",
         "source_url": "https://example.com/refinance"}
    ]})
    stamp_changed(current, previous_brief)
    assert current.sections[0].news[0].changed is False


def test_news_new_url_marked_true(previous_brief):
    """Same headline text, different URL → changed=True (likely a fresh article)."""
    current = _make_brief({}, {"banking": [
        {"headline": "Will cenbank's Tk40,000cr refinance scheme fuel inflation?",
         "source_url": "https://example.com/refinance-update"}
    ]})
    stamp_changed(current, previous_brief)
    assert current.sections[0].news[0].changed is True


def test_news_normalized_match(previous_brief):
    """Same headline with different punctuation/case → changed=False."""
    current = _make_brief({}, {"banking": [
        {"headline": "WILL CENBANK'S TK40,000CR REFINANCE SCHEME FUEL INFLATION??",
         "source_url": "https://example.com/refinance"}
    ]})
    stamp_changed(current, previous_brief)
    assert current.sections[0].news[0].changed is False


def test_no_previous_brief_marks_everything_true():
    """Cold start: previous_brief=None → all changed=True."""
    current = _make_brief(
        {"banking": [{"label": "NPL", "value": "35%"}]},
        {"banking": [{"headline": "Anything", "source_url": "x"}]}
    )
    stamp_changed(current, None)
    assert current.sections[0].metrics[0].changed is True
    assert current.sections[0].news[0].changed is True
