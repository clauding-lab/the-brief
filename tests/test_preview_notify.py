"""Tests for brief/preview_notify.py — Discord webhook + Brevo email pings."""
import io
import json as _json
import urllib.error
from datetime import date
from pathlib import Path

import pytest

from brief import preview_notify as mod
from brief.preview_notify import (
    PreviewMeta,
    extract_preview_meta,
    notify_preview,
    preview_url,
    send_discord_ping,
    send_email_ping,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


class _FakeResp:
    """Minimal urlopen-context-manager stand-in."""
    def __init__(self, body: bytes = b"", status: int = 200):
        self._body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


def _write_fixture(path: Path, *, brief_date: str = "2026-05-28",
                   issue_no: int | None = 117,
                   todays_call: str | None = "First paragraph.\n\nSecond paragraph.") -> Path:
    payload = {
        "brief": {
            "issue_no": issue_no,
            "brief_date": brief_date,
            "todays_call": todays_call,
        },
        "sections": [],
    }
    path.write_text(_json.dumps(payload), encoding="utf-8")
    return path


# ── preview_url ──────────────────────────────────────────────────────────────


def test_preview_url_builds_production_path():
    assert preview_url("foo.json") == (
        "https://thebrief.clauding-lab.com/preview?fixture=foo.json"
    )


# ── extract_preview_meta ─────────────────────────────────────────────────────


def test_extract_preview_meta_pulls_brief_date_issue_and_todays_call(tmp_path):
    fp = _write_fixture(tmp_path / "preview-2026-05-28.json")

    meta = extract_preview_meta(fp)

    assert meta.fixture_name == "preview-2026-05-28.json"
    assert meta.brief_date == date(2026, 5, 28)
    assert meta.issue_no == 117
    assert meta.todays_call == "First paragraph.\n\nSecond paragraph."


def test_extract_preview_meta_tolerates_missing_fields(tmp_path):
    fp = tmp_path / "bare.json"
    fp.write_text('{"brief": {}, "sections": []}', encoding="utf-8")

    meta = extract_preview_meta(fp)

    assert meta.fixture_name == "bare.json"
    assert meta.issue_no is None
    assert meta.todays_call is None
    # brief_date falls back to today() — just sanity-check the type
    assert isinstance(meta.brief_date, date)


# ── send_discord_ping ────────────────────────────────────────────────────────


def test_send_discord_ping_posts_url_and_todays_call(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = _json.loads(req.data.decode())
        return _FakeResp(b'{"ok":true}', status=204)

    monkeypatch.setattr(mod, "urlopen", fake_urlopen)

    meta = PreviewMeta(
        fixture_name="preview-2026-05-28.json",
        brief_date=date(2026, 5, 28),
        issue_no=117,
        todays_call="The headline today is X. The watch list includes Y and Z.",
    )

    err = send_discord_ping(webhook_url="https://discord.test/webhook/abc", meta=meta)

    assert err is None
    assert captured["url"] == "https://discord.test/webhook/abc"
    content = captured["body"]["content"]
    assert "Preview ready — Thu 28 May 2026" in content
    assert "No. 117" in content
    assert "https://thebrief.clauding-lab.com/preview?fixture=preview-2026-05-28.json" in content
    assert "headline today is X" in content


def test_send_discord_ping_returns_http_error(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized",
            hdrs=None, fp=io.BytesIO(b'{"message":"bad token"}'),
        )

    monkeypatch.setattr(mod, "urlopen", boom)

    meta = PreviewMeta(
        fixture_name="x.json", brief_date=date.today(), issue_no=None, todays_call=None,
    )
    err = send_discord_ping(webhook_url="https://discord.test/webhook/x", meta=meta)

    assert err is not None and "401" in err


# ── send_email_ping ──────────────────────────────────────────────────────────


def test_send_email_ping_posts_correct_brevo_payload(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = _json.loads(req.data.decode())
        return _FakeResp(b'{"messageId":"<msg@brevo>"}', status=201)

    monkeypatch.setattr(mod, "urlopen", fake_urlopen)

    meta = PreviewMeta(
        fixture_name="preview-2026-05-28.json",
        brief_date=date(2026, 5, 28),
        issue_no=117,
        todays_call="Hello world.\n\nSecond paragraph here.",
    )

    err = send_email_ping(
        api_key="brevo-key",
        from_email="adnan@thebrief.clauding-lab.com",
        recipient_email="adnan.rshd@gmail.com",
        meta=meta,
    )

    assert err is None
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    # Privacy: a single recipient, not a list of subscribers
    assert captured["body"]["to"] == [{"email": "adnan.rshd@gmail.com"}]
    assert captured["body"]["sender"] == {
        "email": "adnan@thebrief.clauding-lab.com",
        "name": "The Brief — Preview",
    }
    assert "The Brief preview" in captured["body"]["subject"]
    assert "Thu 28 May 2026" in captured["body"]["subject"]
    assert "No. 117" in captured["body"]["subject"]
    assert "https://thebrief.clauding-lab.com/preview?fixture=preview-2026-05-28.json" in captured["body"]["textContent"]
    assert "https://thebrief.clauding-lab.com/preview?fixture=preview-2026-05-28.json" in captured["body"]["htmlContent"]
    assert "Hello world" in captured["body"]["textContent"]


def test_send_email_ping_escapes_html_in_todays_call(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = _json.loads(req.data.decode())
        return _FakeResp(b'{"messageId":"<m@b>"}', status=201)

    monkeypatch.setattr(mod, "urlopen", fake_urlopen)

    meta = PreviewMeta(
        fixture_name="x.json",
        brief_date=date(2026, 5, 28),
        issue_no=None,
        todays_call='Risk includes <script>alert(1)</script> and a "quote" embedded.',
    )

    send_email_ping(
        api_key="k", from_email="a@x.com", recipient_email="b@y.com", meta=meta,
    )

    html = captured["body"]["htmlContent"]
    # XSS-escaped, never executed
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&quot;quote&quot;" in html


# ── notify_preview orchestration ─────────────────────────────────────────────


def test_notify_preview_fires_both_channels_independently(monkeypatch, tmp_path):
    fp = _write_fixture(tmp_path / "preview-2026-05-28.json")
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        if "discord" in req.full_url:
            return _FakeResp(b'', status=204)
        return _FakeResp(b'{"messageId":"<m@b>"}', status=201)

    monkeypatch.setattr(mod, "urlopen", fake_urlopen)
    monkeypatch.setenv("DISCORD_PREVIEW_WEBHOOK_URL", "https://discord.test/webhook/x")
    monkeypatch.setenv("BREVO_API_KEY", "brevo-key")
    monkeypatch.setenv("FROM_EMAIL", "adnan@thebrief.clauding-lab.com")
    monkeypatch.setenv("PREVIEW_EMAIL_RECIPIENT", "adnan.rshd@gmail.com")

    result = notify_preview(fp)

    assert result.discord_ok is True
    assert result.discord_error is None
    assert result.email_ok is True
    assert result.email_error is None
    assert result.preview_url.endswith("/preview?fixture=preview-2026-05-28.json")
    assert any("discord" in u for u in calls)
    assert any("brevo" in u for u in calls)


def test_notify_preview_one_channel_failure_does_not_block_the_other(monkeypatch, tmp_path):
    fp = _write_fixture(tmp_path / "p.json")

    def fake_urlopen(req, timeout=None):
        if "discord" in req.full_url:
            raise OSError("network blip")
        return _FakeResp(b'{"messageId":"<m@b>"}', status=201)

    monkeypatch.setattr(mod, "urlopen", fake_urlopen)
    monkeypatch.setenv("DISCORD_PREVIEW_WEBHOOK_URL", "https://discord.test/webhook/x")
    monkeypatch.setenv("BREVO_API_KEY", "brevo-key")
    monkeypatch.setenv("FROM_EMAIL", "adnan@thebrief.clauding-lab.com")
    monkeypatch.setenv("PREVIEW_EMAIL_RECIPIENT", "adnan.rshd@gmail.com")

    result = notify_preview(fp)

    assert result.discord_ok is False
    assert "network blip" in (result.discord_error or "")
    assert result.email_ok is True
    assert result.email_error is None


def test_notify_preview_skips_channels_with_missing_env(monkeypatch, tmp_path):
    fp = _write_fixture(tmp_path / "p.json")

    def fake_urlopen(req, timeout=None):
        # Should not be called if both channels are gated off by env
        raise AssertionError("urlopen called despite missing env")

    monkeypatch.setattr(mod, "urlopen", fake_urlopen)
    monkeypatch.delenv("DISCORD_PREVIEW_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("FROM_EMAIL", raising=False)
    monkeypatch.delenv("PREVIEW_EMAIL_RECIPIENT", raising=False)

    result = notify_preview(fp)

    assert result.discord_ok is False
    assert result.discord_error == "no_webhook"
    assert result.email_ok is False
    assert result.email_error is not None
    assert "missing_env" in result.email_error
