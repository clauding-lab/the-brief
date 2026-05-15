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
