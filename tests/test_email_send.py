# tests/test_email_send.py
from __future__ import annotations

import json

import pytest

import brief.email_send as email_send_mod
from brief.email_send import send_email


def test_send_email_posts_correct_brevo_payload(monkeypatch):
    """Verifies the Request sent to Brevo has the correct URL, api-key header, and JSON body."""
    captured = {}

    class FakeResponse:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data.decode())
        return FakeResponse()

    monkeypatch.setattr(email_send_mod, "urlopen", fake_urlopen)

    result = send_email(
        from_email="adnan@example.com",
        api_key="test-api-key",
        subject="The Brief · 2026-04-25",
        html="<html>content</html>",
        text="plain text content",
    )

    assert result == 201
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert "Api-key" in captured["headers"] or "api-key" in {k.lower(): v for k, v in captured["headers"].items()}
    body = captured["body"]
    assert body["sender"]["email"] == "adnan@example.com"
    assert body["to"][0]["email"] == "adnan@example.com"
    assert body["subject"] == "The Brief · 2026-04-25"
    assert body["htmlContent"] == "<html>content</html>"
    assert body["textContent"] == "plain text content"


def test_send_email_returns_zero_on_network_error(monkeypatch):
    """Verifies fail-open: send_email returns 0 when urlopen raises OSError."""

    def boom(req, timeout=None):
        raise OSError("network unreachable")

    monkeypatch.setattr(email_send_mod, "urlopen", boom)

    result = send_email(
        from_email="adnan@example.com",
        api_key="test-api-key",
        subject="Test",
        html="<html/>",
        text="text",
    )

    assert result == 0
