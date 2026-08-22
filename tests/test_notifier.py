"""Unit tests for brief.notifier — release email notifier."""
from __future__ import annotations

from brief.notifier import Subscriber, NotifyResult

FROM_EMAIL = "notify@thebrief.example"


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
    text = render_text(brief=_fixture_brief(), lead_news=_fixture_lead_news(), from_email=FROM_EMAIL)
    assert "THE BRIEF · Vol. 01 · No. 107" in text
    assert "Fri 15 May 2026" in text
    # 09:33 UTC → 15:33 BDT (UTC+6)
    assert "15:33 BDT" in text
    assert "weekly wrap" in text


def test_render_text_contains_todays_call_paragraphs():
    text = render_text(brief=_fixture_brief(), lead_news=_fixture_lead_news(), from_email=FROM_EMAIL)
    assert "TODAY'S CALL" in text
    assert "Fitch went negative on BD Wednesday" in text
    assert "USD/BDT held 122.75" in text
    assert "Next week: May CPI print." in text


def test_render_text_contains_lead_headline_block():
    text = render_text(brief=_fixture_brief(), lead_news=_fixture_lead_news(), from_email=FROM_EMAIL)
    assert "LEAD HEADLINE" in text
    assert "Fitch revises Bangladesh outlook to negative amid Middle East fallout" in text
    assert "The Daily Star" in text
    # 00:30 UTC May 14 → 06:30 BDT May 14
    assert "06:30 BDT" in text
    assert "https://www.thedailystar.net/business/economy/news/fitch-revises-bangladesh-outlook-negative-amid-middle-east-fallout-4175171" in text


def test_render_text_omits_lead_section_when_lead_news_is_none():
    text = render_text(brief=_fixture_brief(), lead_news=None, from_email=FROM_EMAIL)
    assert "LEAD HEADLINE" not in text
    assert "(no lead headline today)" not in text


def test_render_text_ends_with_full_edition_link_and_unsubscribe():
    text = render_text(brief=_fixture_brief(), lead_news=_fixture_lead_news(), from_email=FROM_EMAIL)
    assert "Full edition → https://thebrief.clauding-lab.com/" in text
    assert "Unsubscribe" in text


def test_render_text_unsubscribe_points_at_from_email():
    """P0 honesty fix (2026-08-22 audit #204): both unsubscribe paths must
    name the SAME mailbox the email was actually sent from."""
    text = render_text(brief=_fixture_brief(), lead_news=None, from_email=FROM_EMAIL)
    assert FROM_EMAIL in text


def test_render_text_carries_issue_number_and_date_near_the_cta():
    """P0 honesty fix (2026-08-22 audit #204): an old email dug up months
    later should identify its issue without scrolling back to the masthead."""
    text = render_text(brief=_fixture_brief(), lead_news=_fixture_lead_news(), from_email=FROM_EMAIL)
    lines = text.split("\n")
    cta_idx = next(i for i, l in enumerate(lines) if l.startswith("Full edition"))
    nearby = "\n".join(lines[max(0, cta_idx - 2): cta_idx + 1])
    assert "Issue No. 107" in nearby
    assert "15 May 2026" in nearby


from brief.notifier import render_html


def test_render_html_has_doctype_and_inline_styled_body():
    html = render_html(brief=_fixture_brief(), lead_news=_fixture_lead_news(), from_email=FROM_EMAIL)
    assert html.startswith("<!DOCTYPE html>")
    assert "background:#f7f2e8" in html  # cream-paper outer bg
    assert "background:#fdfaf4" in html  # card bg
    # Outlook-safe: NO <style> block, only inline styles
    assert "<style" not in html


def test_render_html_renders_masthead_and_dateline():
    html = render_html(brief=_fixture_brief(), lead_news=_fixture_lead_news(), from_email=FROM_EMAIL)
    assert "Vol. 01" in html
    assert "No. 107" in html
    assert "Fri 15 May 2026" in html
    assert "15:33 BDT" in html
    assert "weekly wrap" in html


def test_render_html_renders_todays_call_as_paragraphs():
    html = render_html(brief=_fixture_brief(), lead_news=_fixture_lead_news(), from_email=FROM_EMAIL)
    # Each \n\n becomes a <p>
    assert html.count("<p style=") >= 3  # 3 paragraphs in fixture todays_call
    assert "Fitch went negative on BD Wednesday" in html
    assert "USD/BDT held 122.75" in html


def test_render_html_renders_lead_headline_with_link():
    html = render_html(brief=_fixture_brief(), lead_news=_fixture_lead_news(), from_email=FROM_EMAIL)
    assert 'href="https://www.thedailystar.net/' in html
    assert "Fitch revises Bangladesh outlook to negative" in html
    assert "The Daily Star" in html
    assert "06:30 BDT" in html


def test_render_html_omits_lead_section_when_lead_news_is_none():
    html = render_html(brief=_fixture_brief(), lead_news=None, from_email=FROM_EMAIL)
    assert "Lead Headline" not in html
    # Hairline count is one fewer when no lead section
    assert html.count("border-top:1px solid #e6dfd1") == 2  # date->call, call->cta


def test_render_html_escapes_special_chars_in_todays_call():
    brief = BriefRow(
        id="x", issue_no=1, volume=1, brief_date=date(2026, 1, 1),
        published_at=datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
        todays_call="Risk & rate <test> entities",
        lens=None,
    )
    html = render_html(brief=brief, lead_news=None, from_email=FROM_EMAIL)
    assert "Risk &amp; rate &lt;test&gt; entities" in html
    assert "Risk & rate <test>" not in html  # un-escaped form must NOT appear


def test_render_html_drops_non_http_source_url_to_prevent_xss():
    bad_lead = NewsRow(
        headline="legitimate-looking headline",
        source="Some Source",
        source_url="javascript:alert(1)",
        published_at=None,
    )
    html = render_html(brief=_fixture_brief(), lead_news=bad_lead, from_email=FROM_EMAIL)
    # javascript: scheme must NOT appear as an href value
    assert 'href="javascript:' not in html
    assert "javascript:alert(1)" not in html
    # But the headline text should still render
    assert "legitimate-looking headline" in html


def test_render_html_escapes_special_chars_in_lead_headline():
    bad_lead = NewsRow(
        headline='Analyst says "buy" & hold <urgent>',
        source="Source & Co",
        source_url="https://example.com",
        published_at=None,
    )
    html = render_html(brief=_fixture_brief(), lead_news=bad_lead, from_email=FROM_EMAIL)
    # Headline escaped
    assert "Analyst says &quot;buy&quot; &amp; hold &lt;urgent&gt;" in html
    assert "<urgent>" not in html  # un-escaped form must NOT appear
    # Source escaped
    assert "Source &amp; Co" in html


def test_render_html_unsubscribe_mailto_points_at_from_email():
    """P0 honesty fix (2026-08-22 audit #204): this used to hardcode a
    personal Gmail address, a different mailbox than the one the email was
    actually sent from."""
    html = render_html(brief=_fixture_brief(), lead_news=None, from_email=FROM_EMAIL)
    assert f"mailto:{FROM_EMAIL}?subject=" in html
    assert "adnan.rshd@gmail.com" not in html


def test_render_html_carries_issue_number_and_date_near_the_cta():
    html = render_html(brief=_fixture_brief(), lead_news=_fixture_lead_news(), from_email=FROM_EMAIL)
    cta_pos = html.index("Full edition")
    nearby = html[max(0, cta_pos - 300):cta_pos]
    assert "Issue No. 107" in nearby
    assert "Fri 15 May 2026" in nearby


from brief.notifier import render_email


def test_render_email_returns_three_strings():
    subject, html, text = render_email(brief=_fixture_brief(), lead_news=_fixture_lead_news(), from_email=FROM_EMAIL)
    assert isinstance(subject, str) and subject.startswith("The Brief · No. 107")
    assert html.startswith("<!DOCTYPE html>")
    assert text.startswith("THE BRIEF · Vol. 01 · No. 107")


def test_render_email_handles_no_lead_news():
    subject, html, text = render_email(brief=_fixture_brief(), lead_news=None, from_email=FROM_EMAIL)
    assert "LEAD HEADLINE" not in html
    assert "LEAD HEADLINE" not in text
    assert subject == "The Brief · No. 107 · Fri 15 May 2026 · weekly wrap"


import json as _json
import brief.notifier as notifier_mod
from brief.notifier import fetch_subscribers


class _FakeResp:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self) -> bytes:
        return self._body


def test_fetch_subscribers_returns_list_of_subscriber(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        body = _json.dumps([
            {"name": "Mehrin", "email": "m@brac.com", "organisation": "BRAC"},
            {"name": "Tareq", "email": "t@city.com", "organisation": None},
        ]).encode()
        return _FakeResp(body)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    subs = fetch_subscribers()

    assert len(subs) == 2
    assert subs[0] == Subscriber(name="Mehrin", email="m@brac.com", organisation="BRAC")
    assert subs[1].organisation is None
    assert "/rest/v1/subscribers" in captured["url"]
    assert captured["headers"].get("Apikey") == "test-key" or captured["headers"].get("apikey") == "test-key"


def test_fetch_subscribers_returns_empty_when_table_empty(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")

    def fake_urlopen(req, timeout=None):
        return _FakeResp(b"[]")

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    assert fetch_subscribers() == []


def test_fetch_subscribers_raises_on_missing_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    with __import__("pytest").raises(RuntimeError, match="SUPABASE_URL"):
        fetch_subscribers()


from brief.notifier import fetch_brief_data


def test_fetch_brief_data_returns_brief_and_lead_news(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")

    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        if "/briefs?" in req.full_url:
            body = _json.dumps([{
                "id": "f54ac95d", "issue_no": 107, "volume": 1,
                "brief_date": "2026-05-15", "published_at": "2026-05-15T09:33:12+00:00",
                "todays_call": "Fitch went negative.", "lens": "weekly_wrap",
            }]).encode()
        elif "/sections?" in req.full_url:
            body = _json.dumps([{"id": "sec-uuid"}]).encode()
        elif "/news?" in req.full_url:
            body = _json.dumps([{
                "headline": "Fitch revises Bangladesh outlook to negative",
                "source": "The Daily Star",
                "source_url": "https://example.com/x",
                "published_at": "2026-05-14T00:30:00+00:00",
            }]).encode()
        else:
            raise AssertionError(f"unexpected URL: {req.full_url}")
        return _FakeResp(body)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    brief, lead = fetch_brief_data("f54ac95d")
    assert brief.issue_no == 107
    assert brief.todays_call == "Fitch went negative."
    assert lead is not None
    assert lead.headline.startswith("Fitch revises Bangladesh")
    assert lead.source == "The Daily Star"


def test_fetch_brief_data_returns_none_lead_when_no_headlines_section(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")

    def fake_urlopen(req, timeout=None):
        if "/briefs?" in req.full_url:
            body = _json.dumps([{
                "id": "x", "issue_no": 1, "volume": 1,
                "brief_date": "2026-05-15", "published_at": "2026-05-15T00:30:00+00:00",
                "todays_call": "x", "lens": None,
            }]).encode()
        elif "/sections?" in req.full_url:
            body = b"[]"  # no headlines section
        else:
            raise AssertionError(f"unexpected URL: {req.full_url}")
        return _FakeResp(body)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    brief, lead = fetch_brief_data("x")
    assert lead is None


def test_fetch_brief_data_returns_none_lead_when_section_has_no_news(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")

    def fake_urlopen(req, timeout=None):
        if "/briefs?" in req.full_url:
            body = _json.dumps([{
                "id": "x", "issue_no": 1, "volume": 1,
                "brief_date": "2026-05-15", "published_at": "2026-05-15T00:30:00+00:00",
                "todays_call": "x", "lens": None,
            }]).encode()
        elif "/sections?" in req.full_url:
            body = _json.dumps([{"id": "sec-uuid"}]).encode()
        elif "/news?" in req.full_url:
            body = b"[]"
        else:
            raise AssertionError(f"unexpected URL: {req.full_url}")
        return _FakeResp(body)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    brief, lead = fetch_brief_data("x")
    assert lead is None


from brief.notifier import send_via_brevo


def test_send_via_brevo_posts_one_call_per_subscriber(monkeypatch):
    """Privacy guarantee: each subscriber gets their own Brevo call with
    only their own address in `to`, so recipients never see each other.
    Also asserts shared-fields (sender / subject / bodies) and that the
    returned message_id is the LAST successful messageId."""
    captured: list[dict] = []
    counter = {"n": 0}

    def fake_urlopen(req, timeout=None):
        counter["n"] += 1
        captured.append({
            "url": req.full_url,
            "headers": dict(req.headers),
            "body": _json.loads(req.data.decode()),
        })
        # Each call returns a distinct messageId so we can verify "last wins"
        return _FakeResp(
            f'{{"messageId":"<msg-{counter["n"]}@brevo>"}}'.encode(),
            status=201,
        )

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    result = send_via_brevo(
        api_key="test-key",
        from_email="adnan.rshd@gmail.com",
        from_name="The Brief",
        subscribers=[
            Subscriber(name="A", email="a@x.com", organisation=None),
            Subscriber(name="B", email="b@y.com", organisation="Y"),
        ],
        subject="The Brief · No. 107",
        html_body="<html/>",
        text_body="plain",
    )

    # Privacy assertion: exactly one POST per subscriber, each `to` isolated.
    assert len(captured) == 2
    assert captured[0]["body"]["to"] == [{"email": "a@x.com", "name": "A"}]
    assert captured[1]["body"]["to"] == [{"email": "b@y.com", "name": "B"}]

    # Shared fields are identical across calls.
    for call in captured:
        assert call["url"] == "https://api.brevo.com/v3/smtp/email"
        assert call["body"]["sender"] == {"email": "adnan.rshd@gmail.com", "name": "The Brief"}
        assert call["body"]["subject"] == "The Brief · No. 107"
        assert call["body"]["htmlContent"] == "<html/>"
        assert call["body"]["textContent"] == "plain"

    # Return contract: (sent_count, last_message_id, error)
    assert result == (2, "<msg-2@brevo>", None)


def test_send_via_brevo_includes_list_unsubscribe_header(monkeypatch):
    """P0 honesty fix (2026-08-22 audit #204): no unsubscribe mechanism beyond
    "reply to this email" existed. The header lets mail clients offer a
    one-click unsubscribe against the SAME mailbox the email was sent from."""
    captured: list[dict] = []

    def fake_urlopen(req, timeout=None):
        captured.append(_json.loads(req.data.decode()))
        return _FakeResp(b'{"messageId":"<ok@brevo>"}', status=201)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    send_via_brevo(
        api_key="k", from_email="notify@thebrief.example", from_name="The Brief",
        subscribers=[Subscriber(name="A", email="a@x.com", organisation=None)],
        subject="s", html_body="h", text_body="t",
    )

    assert captured[0]["headers"]["List-Unsubscribe"] == \
        "<mailto:notify@thebrief.example?subject=Unsubscribe>"


def test_send_via_brevo_partial_failure_reports_sent_count_and_first_error(monkeypatch):
    """If subscriber 2 of 3 fails but 1 and 3 succeed, sent_count=2 and the
    error string surfaces the first failure. Caller can decide to retry."""
    counter = {"n": 0}

    def fake_urlopen(req, timeout=None):
        counter["n"] += 1
        if counter["n"] == 2:
            raise OSError("transient network blip")
        return _FakeResp(b'{"messageId":"<ok@brevo>"}', status=201)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    sent, msg_id, err = send_via_brevo(
        api_key="k",
        from_email="from@x.com",
        from_name="The Brief",
        subscribers=[
            Subscriber(name="A", email="a@x.com", organisation=None),
            Subscriber(name="B", email="b@y.com", organisation=None),
            Subscriber(name="C", email="c@z.com", organisation=None),
        ],
        subject="s", html_body="h", text_body="t",
    )
    assert sent == 2
    assert msg_id == "<ok@brevo>"
    assert "transient network blip" in err


def test_send_via_brevo_returns_error_on_network_failure(monkeypatch):
    def boom(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(notifier_mod, "urlopen", boom)

    sent, msg_id, err = send_via_brevo(
        api_key="k", from_email="a@x.com", from_name="The Brief",
        subscribers=[Subscriber(name="A", email="a@x.com", organisation=None)],
        subject="s", html_body="h", text_body="t",
    )
    assert sent == 0
    assert msg_id is None
    assert "connection refused" in err


def test_send_via_brevo_returns_error_on_non_2xx(monkeypatch):
    import urllib.error

    def http_err(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized",
            hdrs=None, fp=__import__("io").BytesIO(b'{"message":"invalid api key"}'),
        )

    monkeypatch.setattr(notifier_mod, "urlopen", http_err)

    sent, msg_id, err = send_via_brevo(
        api_key="bad", from_email="a@x.com", from_name="The Brief",
        subscribers=[Subscriber(name="A", email="a@x.com", organisation=None)],
        subject="s", html_body="h", text_body="t",
    )
    assert sent == 0
    assert msg_id is None
    assert "401" in err


def test_send_via_brevo_masks_email_in_failure_logs(monkeypatch, caplog):
    """P0 honesty fix (2026-08-22 audit #204): the full subscriber address was
    logged on send failure, violating the repo's own no-PII rule
    (app/api/subscribe/route.ts:174-177 — error CODE only, never the email)."""
    def boom(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(notifier_mod, "urlopen", boom)

    with caplog.at_level("WARNING", logger="brief.notifier"):
        send_via_brevo(
            api_key="k", from_email="a@x.com", from_name="The Brief",
            subscribers=[Subscriber(name="A", email="mehrin.rahman@brac.com", organisation=None)],
            subject="s", html_body="h", text_body="t",
        )

    joined = "\n".join(r.message for r in caplog.records)
    assert "mehrin.rahman@brac.com" not in joined
    assert "m***@brac.com" in joined


def test_send_via_brevo_masks_email_on_http_error(monkeypatch, caplog):
    import urllib.error

    def http_err(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized",
            hdrs=None, fp=__import__("io").BytesIO(b'{"message":"invalid api key"}'),
        )

    monkeypatch.setattr(notifier_mod, "urlopen", http_err)

    with caplog.at_level("WARNING", logger="brief.notifier"):
        send_via_brevo(
            api_key="bad", from_email="a@x.com", from_name="The Brief",
            subscribers=[Subscriber(name="A", email="mehrin.rahman@brac.com", organisation=None)],
            subject="s", html_body="h", text_body="t",
        )

    joined = "\n".join(r.message for r in caplog.records)
    assert "mehrin.rahman@brac.com" not in joined
    assert "m***@brac.com" in joined


from brief.notifier import _mask_email


def test_mask_email_keeps_first_char_and_domain():
    assert _mask_email("adnan.rshd@gmail.com") == "a***@gmail.com"


def test_mask_email_handles_single_char_local_part():
    assert _mask_email("m@brac.com") == "m***@brac.com"


def test_mask_email_falls_back_on_malformed_input():
    assert _mask_email("not-an-email") == "***"


from brief.notifier import notify


def test_notify_happy_path(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")
    monkeypatch.setenv("BREVO_API_KEY", "brevo-key")
    monkeypatch.setenv("FROM_EMAIL", "adnan@example.com")

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        if "/briefs?" in url:
            body = _json.dumps([{
                "id": "f54ac95d", "issue_no": 107, "volume": 1,
                "brief_date": "2026-05-15", "published_at": "2026-05-15T09:33:12+00:00",
                "todays_call": "x", "lens": "weekly_wrap",
            }]).encode()
        elif "/sections?" in url:
            body = _json.dumps([{"id": "sec-uuid"}]).encode()
        elif "/news?" in url:
            body = _json.dumps([{
                "headline": "h", "source": "s",
                "source_url": "https://example.com",
                "published_at": "2026-05-14T00:30:00+00:00",
            }]).encode()
        elif "/subscribers?" in url:
            body = _json.dumps([
                {"name": "Mehrin", "email": "m@brac.com", "organisation": "BRAC"},
            ]).encode()
        elif url == "https://api.brevo.com/v3/smtp/email":
            body = b'{"messageId":"<abc@brevo>"}'
        else:
            raise AssertionError(f"unexpected URL: {url}")
        return _FakeResp(body)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    result = notify("f54ac95d")

    assert result.sent_count == 1
    assert result.message_id == "<abc@brevo>"
    assert result.error is None


def test_notify_returns_no_api_key_error_when_brevo_key_missing(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    # urlopen should not be called — so set a tripwire
    def tripwire(*a, **kw):
        raise AssertionError("urlopen called despite missing BREVO_API_KEY")
    monkeypatch.setattr(notifier_mod, "urlopen", tripwire)

    result = notify("f54ac95d")
    assert result.sent_count == 0
    assert result.error == "no_api_key"


def test_notify_returns_no_subscribers_when_table_empty(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")
    monkeypatch.setenv("BREVO_API_KEY", "brevo-key")
    monkeypatch.setenv("FROM_EMAIL", "adnan@example.com")

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        if "/briefs?" in url:
            body = _json.dumps([{
                "id": "x", "issue_no": 1, "volume": 1,
                "brief_date": "2026-05-15", "published_at": "2026-05-15T00:30:00+00:00",
                "todays_call": "x", "lens": None,
            }]).encode()
        elif "/sections?" in url:
            body = b"[]"
        elif "/subscribers?" in url:
            body = b"[]"
        else:
            raise AssertionError(f"unexpected URL: {url}")
        return _FakeResp(body)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    result = notify("x")
    assert result.sent_count == 0
    assert result.error == "no_subscribers"


def test_notify_swallows_unexpected_exception(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")
    monkeypatch.setenv("BREVO_API_KEY", "brevo-key")

    def boom(req, timeout=None):
        raise RuntimeError("unexpected!")

    monkeypatch.setattr(notifier_mod, "urlopen", boom)

    result = notify("x")
    assert result.sent_count == 0
    assert result.error is not None
    assert result.error.startswith("fetch_brief:")
    assert "unexpected" in result.error.lower()


def test_notify_returns_fetch_subs_error_when_subscribers_raises(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")
    monkeypatch.setenv("BREVO_API_KEY", "brevo-key")

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        if "/briefs?" in url:
            body = _json.dumps([{
                "id": "x", "issue_no": 1, "volume": 1,
                "brief_date": "2026-05-15", "published_at": "2026-05-15T00:30:00+00:00",
                "todays_call": "x", "lens": None,
            }]).encode()
            return _FakeResp(body)
        elif "/sections?" in url:
            return _FakeResp(b"[]")  # no headlines → fetch_brief_data returns (brief, None)
        elif "/subscribers?" in url:
            raise OSError("db timeout")
        else:
            raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    result = notify("x")
    assert result.sent_count == 0
    assert result.error is not None
    assert result.error.startswith("fetch_subs:")
    assert "db timeout" in result.error
