"""Tests for brief/alerts.py — best-effort Discord ops alerts (item 5d)."""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from brief.alerts import send_discord_alert


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("DISCORD_PREVIEW_WEBHOOK_URL", raising=False)


def _resp(status: int = 204):
    class _Resp:
        def __enter__(self):
            self.status = status
            return self

        def __exit__(self, *a):
            return False

    return _Resp()


def test_no_webhook_env_returns_false_without_network() -> None:
    with patch("urllib.request.urlopen") as mock_open:
        assert send_discord_alert("hello") is False
    mock_open.assert_not_called()


def test_posts_to_alert_webhook_with_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_ALERT_WEBHOOK_URL", "https://discord.test/hook-alerts")
    captured = {}

    def _capture(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _resp(204)

    with patch("urllib.request.urlopen", side_effect=_capture):
        assert send_discord_alert("publish failed: sent=0") is True

    assert captured["url"] == "https://discord.test/hook-alerts"
    assert captured["body"]["content"] == "publish failed: sent=0"


def test_falls_back_to_preview_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_PREVIEW_WEBHOOK_URL", "https://discord.test/hook-preview")
    captured = {}

    def _capture(req, timeout=None):
        captured["url"] = req.full_url
        return _resp(204)

    with patch("urllib.request.urlopen", side_effect=_capture):
        assert send_discord_alert("x") is True
    assert captured["url"] == "https://discord.test/hook-preview"


def test_truncates_to_discord_content_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_ALERT_WEBHOOK_URL", "https://discord.test/hook")
    captured = {}

    def _capture(req, timeout=None):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _resp(204)

    with patch("urllib.request.urlopen", side_effect=_capture):
        send_discord_alert("y" * 5000)
    assert len(captured["body"]["content"]) == 1990


def test_network_error_returns_false_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_ALERT_WEBHOOK_URL", "https://discord.test/hook")
    err = urllib.error.HTTPError(
        url="https://discord.test/hook", code=500, msg="boom",
        hdrs=None, fp=io.BytesIO(b"{}"),  # type: ignore[arg-type]
    )
    with patch("urllib.request.urlopen", side_effect=err):
        assert send_discord_alert("z") is False  # swallowed, reported as False
