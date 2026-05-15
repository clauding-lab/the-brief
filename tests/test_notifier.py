"""Unit tests for brief.notifier — release email notifier."""
from __future__ import annotations

from brief.notifier import Subscriber, NotifyResult


def test_subscriber_dataclass_is_frozen_and_has_expected_fields():
    s = Subscriber(name="Mehrin Rahman", email="m@brac.bank.com", organisation="BRAC")
    assert s.name == "Mehrin Rahman"
    assert s.email == "m@brac.bank.com"
    assert s.organisation == "BRAC"
    # frozen → mutation raises
    import dataclasses
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        s.email = "other@example.com"  # type: ignore[misc]


def test_notify_result_has_expected_fields_with_defaults():
    r = NotifyResult(sent_count=5, skipped_count=0, message_id="abc", error=None)
    assert r.sent_count == 5
    assert r.skipped_count == 0
    assert r.message_id == "abc"
    assert r.error is None


from datetime import date
from brief.notifier import render_subject


def test_render_subject_friday_weekly_wrap():
    subj = render_subject(issue_no=107, brief_date=date(2026, 5, 15), lens="weekly_wrap")
    assert subj == "The Brief · No. 107 · Fri 15 May 2026 · weekly wrap"


def test_render_subject_weekday_daily():
    subj = render_subject(issue_no=108, brief_date=date(2026, 5, 18), lens="daily")
    assert subj == "The Brief · No. 108 · Mon 18 May 2026 · daily read"


def test_render_subject_unknown_lens_falls_back_to_daily_read():
    subj = render_subject(issue_no=99, brief_date=date(2026, 4, 15), lens="something_new")
    assert subj == "The Brief · No. 99 · Wed 15 Apr 2026 · daily read"


def test_render_subject_null_lens_falls_back_to_daily_read():
    subj = render_subject(issue_no=99, brief_date=date(2026, 4, 15), lens=None)
    assert subj == "The Brief · No. 99 · Wed 15 Apr 2026 · daily read"


from datetime import datetime, timezone
from brief.notifier import BriefRow, NewsRow, render_text


def _fixture_brief() -> BriefRow:
    """A realistic V6 brief row built from Issue 107 (2026-05-15)."""
    return BriefRow(
        id="f54ac95d-2127-44f4-bb02-9bd0f7fc5de8",
        issue_no=107,
        volume=1,
        brief_date=date(2026, 5, 15),
        published_at=datetime(2026, 5, 15, 9, 33, 12, tzinfo=timezone.utc),
        todays_call=(
            "Fitch went negative on BD Wednesday — first rating action.\n\n"
            "USD/BDT held 122.75 all five sessions.\n\n"
            "Next week: May CPI print."
        ),
        lens="weekly_wrap",
    )


def _fixture_lead_news() -> NewsRow:
    return NewsRow(
        headline="Fitch revises Bangladesh outlook to negative amid Middle East fallout",
        source="The Daily Star",
        source_url="https://www.thedailystar.net/business/economy/news/fitch-revises-bangladesh-outlook-negative-amid-middle-east-fallout-4175171",
        published_at=datetime(2026, 5, 14, 0, 30, 16, tzinfo=timezone.utc),
    )


def test_render_text_contains_masthead_and_dateline():
    text = render_text(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert "THE BRIEF · Vol. 01 · No. 107" in text
    assert "Fri 15 May 2026" in text
    # 09:33 UTC → 15:33 BDT (UTC+6)
    assert "15:33 BDT" in text
    assert "weekly wrap" in text


def test_render_text_contains_todays_call_paragraphs():
    text = render_text(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert "TODAY'S CALL" in text
    assert "Fitch went negative on BD Wednesday" in text
    assert "USD/BDT held 122.75" in text
    assert "Next week: May CPI print." in text


def test_render_text_contains_lead_headline_block():
    text = render_text(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert "LEAD HEADLINE" in text
    assert "Fitch revises Bangladesh outlook to negative amid Middle East fallout" in text
    assert "The Daily Star" in text
    # 00:30 UTC May 14 → 06:30 BDT May 14
    assert "06:30 BDT" in text
    assert "https://www.thedailystar.net/business/economy/news/fitch-revises-bangladesh-outlook-negative-amid-middle-east-fallout-4175171" in text


def test_render_text_omits_lead_section_when_lead_news_is_none():
    text = render_text(brief=_fixture_brief(), lead_news=None)
    assert "LEAD HEADLINE" not in text
    assert "(no lead headline today)" not in text


def test_render_text_ends_with_full_edition_link_and_unsubscribe():
    text = render_text(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert "Full edition → https://thebrief.clauding-lab.com/" in text
    assert "Unsubscribe" in text


from brief.notifier import render_html


def test_render_html_has_doctype_and_inline_styled_body():
    html = render_html(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert html.startswith("<!DOCTYPE html>")
    assert "background:#f7f2e8" in html  # cream-paper outer bg
    assert "background:#fdfaf4" in html  # card bg
    # Outlook-safe: NO <style> block, only inline styles
    assert "<style" not in html


def test_render_html_renders_masthead_and_dateline():
    html = render_html(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert "Vol. 01" in html
    assert "No. 107" in html
    assert "Fri 15 May 2026" in html
    assert "15:33 BDT" in html
    assert "weekly wrap" in html


def test_render_html_renders_todays_call_as_paragraphs():
    html = render_html(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    # Each \n\n becomes a <p>
    assert html.count("<p style=") >= 3  # 3 paragraphs in fixture todays_call
    assert "Fitch went negative on BD Wednesday" in html
    assert "USD/BDT held 122.75" in html


def test_render_html_renders_lead_headline_with_link():
    html = render_html(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert 'href="https://www.thedailystar.net/' in html
    assert "Fitch revises Bangladesh outlook to negative" in html
    assert "The Daily Star" in html
    assert "06:30 BDT" in html


def test_render_html_omits_lead_section_when_lead_news_is_none():
    html = render_html(brief=_fixture_brief(), lead_news=None)
    assert "LEAD HEADLINE" not in html
    # Hairline count is one fewer when no lead section
    assert html.count("border-top:1px solid #e6dfd1") == 2  # date->call, call->cta


def test_render_html_escapes_special_chars_in_todays_call():
    brief = BriefRow(
        id="x", issue_no=1, volume=1, brief_date=date(2026, 1, 1),
        published_at=datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
        todays_call="Risk & rate <test> entities",
        lens=None,
    )
    html = render_html(brief=brief, lead_news=None)
    assert "Risk &amp; rate &lt;test&gt; entities" in html
    assert "Risk & rate <test>" not in html  # un-escaped form must NOT appear
