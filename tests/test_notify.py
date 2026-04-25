# tests/test_notify.py
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from brief.notify import build_payload, post_discord


def _report(**overrides):
    base = {
        "schema_version": 1,
        "generated_at": "2026-04-25T06:30:12+06:00",
        "today": "2026-04-25",
        "shadow": True,
        "status": "ok",
        "duration_s": 184.2,
        "total_cost_usd": 1.23,
        "degraded_sections": [],
        "call_reports": [],
        "git_push": {"branch": "shadow/2026-04-25",
                     "sha": "abc1234", "pushed": True},
    }
    base.update(overrides)
    return base


def test_payload_ok():
    p = build_payload(_report(), lead_headline="Taka slides",
                      repo_slug="clauding-lab/the-brief")
    assert "✅ ok" in p["content"]
    assert "$1.23" in p["content"]
    assert "shadow/2026-04-25" in p["content"]
    assert "Taka slides" in p["content"]


def test_payload_degraded():
    p = build_payload(_report(status="degraded", degraded_sections=["dse"]),
                      lead_headline=None,
                      repo_slug="clauding-lab/the-brief")
    assert "⚠️ degraded" in p["content"]
    assert "dse" in p["content"]


def test_payload_error_has_no_git_link():
    p = build_payload(_report(status="error",
                              git_push={"branch": None, "sha": None, "pushed": False}),
                      lead_headline=None,
                      repo_slug="clauding-lab/the-brief")
    assert "❌ error" in p["content"]
    assert "shadow/" not in p["content"]


def test_post_discord_sends_http_post(monkeypatch):
    captured = {}
    class _Resp:
        status = 204
        def read(self): return b""
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake_urlopen(req, timeout=10):
        captured["url"] = req.full_url
        captured["body"] = req.data.decode()
        return _Resp()
    monkeypatch.setattr("brief.notify.urlopen", fake_urlopen)
    rc = post_discord("https://discord.example/webhook/abc",
                      payload={"content": "hi"})
    assert rc == 204
    assert captured["url"] == "https://discord.example/webhook/abc"
    assert json.loads(captured["body"]) == {"content": "hi"}


def test_post_discord_swallows_non_2xx_and_returns_status(monkeypatch):
    class _Resp:
        status = 429
        def read(self): return b""
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr("brief.notify.urlopen", lambda *a, **k: _Resp())
    rc = post_discord("https://discord.example/webhook/abc", payload={"content": "x"})
    assert rc == 429  # caller logs; Discord flakiness must not fail the pipeline


def test_post_discord_network_failure_returns_zero(monkeypatch):
    def boom(*a, **k):
        raise OSError("dns")
    monkeypatch.setattr("brief.notify.urlopen", boom)
    rc = post_discord("https://discord.example/webhook/abc", payload={"content": "x"})
    assert rc == 0
