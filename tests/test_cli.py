# tests/test_cli.py
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from brief import cli
from brief.pipeline import RunResult


@pytest.fixture
def fake_run_result() -> RunResult:
    return RunResult(
        sections=[],
        html="<html>ok</html>",
        claude_outputs={},
        call_reports=[
            {"name": "headlines_curation", "status": "ok", "reason": None,
             "cost_usd": 0.12, "duration_s": 2.1},
        ],
        map_coords=[],
        todays_call=None,
        read_order=[],
        email_text="email digest text",
    )


def test_cli_run_writes_all_artifacts(tmp_path: Path, monkeypatch, fake_run_result):
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    rc = cli.main(["run", f"--artifacts-dir={tmp_path}"])
    assert rc == 0
    assert (tmp_path / "index.html").read_text() == "<html>ok</html>"
    assert (tmp_path / "email.txt").read_text() == "email digest text"
    report = json.loads((tmp_path / "run_report.json").read_text())
    assert report["status"] == "ok"
    assert report["total_cost_usd"] == pytest.approx(0.12)


def test_cli_dry_run_does_not_write(tmp_path: Path, monkeypatch, fake_run_result):
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    rc = cli.main(["run", f"--artifacts-dir={tmp_path}", "--dry-run"])
    assert rc == 3
    assert not (tmp_path / "index.html").exists()


def test_cli_degraded_exit_code(tmp_path: Path, monkeypatch):
    degraded = RunResult(
        sections=[], html="x", claude_outputs={},
        call_reports=[{"name": "headlines_curation", "status": "error",
                       "reason": "timeout", "cost_usd": 0.0, "duration_s": 30.0}],
        email_text="x",
    )
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: degraded)
    rc = cli.main(["run", f"--artifacts-dir={tmp_path}"])
    assert rc == 2


def test_cli_pipeline_exception_returns_1(tmp_path: Path, monkeypatch):
    def boom(cfg, **kw):
        raise RuntimeError("econdelta missing")
    monkeypatch.setattr(cli, "run", boom)
    rc = cli.main(["run", f"--artifacts-dir={tmp_path}"])
    assert rc == 1


def test_cli_rejects_unknown_subcommand():
    with pytest.raises(SystemExit) as ei:
        cli.main(["sneeze"])
    assert ei.value.code != 0


def test_post_discord_called_once_when_env_set(tmp_path, monkeypatch, fake_run_result):
    """post_discord fires exactly once when DISCORD_WEBHOOK_URL is in the environment."""
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook/test")
    calls = []
    monkeypatch.setattr(cli, "post_discord", lambda url, *, payload: calls.append(url) or 0)
    cli.main(["run", f"--artifacts-dir={tmp_path}"])
    assert len(calls) == 1


def test_post_discord_not_called_when_env_unset(tmp_path, monkeypatch, fake_run_result):
    """post_discord is never invoked when DISCORD_WEBHOOK_URL is absent from the environment."""
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    calls = []
    monkeypatch.setattr(cli, "post_discord", lambda url, *, payload: calls.append(url) or 0)
    cli.main(["run", f"--artifacts-dir={tmp_path}"])
    assert len(calls) == 0


def test_email_flag_invokes_send_email(tmp_path, monkeypatch, fake_run_result):
    sent = []
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    monkeypatch.setattr("brief.cli.send_email",
                        lambda **kw: sent.append(kw))
    monkeypatch.setenv("BREVO_API_KEY", "x")
    monkeypatch.setenv("FROM_EMAIL", "adnan@example.com")
    cli.main(["run", f"--artifacts-dir={tmp_path}", "--email"])
    assert len(sent) == 1
    assert sent[0]["from_email"] == "adnan@example.com"


def test_email_without_api_key_is_skipped(tmp_path, monkeypatch, fake_run_result):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    sent = []
    monkeypatch.setattr("brief.cli.send_email", lambda **kw: sent.append(kw))
    cli.main(["run", f"--artifacts-dir={tmp_path}", "--email"])
    assert sent == []  # gracefully skipped


def test_run_report_top_level_duration_s_is_populated(tmp_path, monkeypatch, fake_run_result):
    """Top-level duration_s must reflect run() wallclock, not stay at 0.0."""
    import time as _time

    def slow_run(cfg, **kw):
        _time.sleep(0.05)
        return fake_run_result
    monkeypatch.setattr(cli, "run", slow_run)
    cli.main(["run", f"--artifacts-dir={tmp_path}"])
    report = json.loads((tmp_path / "run_report.json").read_text())
    assert report["duration_s"] >= 0.04, f"expected wallclock-derived duration_s, got {report['duration_s']}"
    assert report["duration_s"] < 5.0  # sanity bound
