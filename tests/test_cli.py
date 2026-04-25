# tests/test_cli.py
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from brief import cli
from brief.pipeline import PipelineConfig, RunResult


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


def test_cli_shadow_flag_threads_through(tmp_path: Path, monkeypatch, fake_run_result):
    captured = {}
    def spy(cfg, **kw):
        captured["shadow"] = kw.get("shadow", False)
        return fake_run_result
    monkeypatch.setattr(cli, "run_with_mode", spy)
    monkeypatch.setattr(cli, "push_artifacts",
                        lambda *, repo_dir, branch, artifacts_dir, message, dry_run=False:
                        {"branch": branch, "sha": "abc1234", "pushed": True})
    cli.main(["run", f"--artifacts-dir={tmp_path}", "--shadow"])
    assert captured["shadow"] is True


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


def test_shadow_calls_push_artifacts(tmp_path: Path, monkeypatch, fake_run_result):
    """--shadow flag triggers push_artifacts and folds result into run_report.json."""
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    push_calls = []
    def fake_push_artifacts(*, repo_dir, branch, artifacts_dir, message, dry_run=False):
        # Invariant: run_report.json must exist at push time, because
        # gitops.push_artifacts copies it onto the shadow branch via `git add`.
        # If we write it AFTER push_artifacts, the real (non-mocked) gitops
        # fails with `git add: pathspec 'run_report.json' did not match any files`.
        assert (artifacts_dir / "run_report.json").exists(), (
            "run_report.json must be written before push_artifacts is called"
        )
        push_calls.append({"branch": branch, "message": message})
        return {"branch": branch, "sha": "abc1234", "pushed": True}
    monkeypatch.setattr(cli, "push_artifacts", fake_push_artifacts)
    rc = cli.main(["run", f"--artifacts-dir={tmp_path}", "--shadow"])
    assert rc == 0
    assert len(push_calls) == 1
    assert push_calls[0]["branch"].startswith("shadow/")
    report = json.loads((tmp_path / "run_report.json").read_text())
    assert report["git_push"]["pushed"] is True
    assert report["git_push"]["sha"] == "abc1234"


def test_non_shadow_does_not_call_push_artifacts(tmp_path: Path, monkeypatch, fake_run_result):
    """Without --shadow, push_artifacts is never called."""
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    push_calls = []
    def fake_push_artifacts(*, repo_dir, branch, artifacts_dir, message, dry_run=False):
        push_calls.append(branch)
        return {"branch": branch, "sha": "abc1234", "pushed": True}
    monkeypatch.setattr(cli, "push_artifacts", fake_push_artifacts)
    rc = cli.main(["run", f"--artifacts-dir={tmp_path}"])
    assert rc == 0
    assert len(push_calls) == 0


def test_post_discord_not_called_when_env_unset(tmp_path, monkeypatch, fake_run_result):
    """post_discord is never invoked when DISCORD_WEBHOOK_URL is absent from the environment."""
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    calls = []
    monkeypatch.setattr(cli, "post_discord", lambda url, *, payload: calls.append(url) or 0)
    cli.main(["run", f"--artifacts-dir={tmp_path}"])
    assert len(calls) == 0


def test_shadow_and_push_main_are_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["run", f"--artifacts-dir={tmp_path}", "--shadow", "--push-main"])


def test_push_main_calls_gitops_with_main_branch(tmp_path, monkeypatch, fake_run_result):
    captured = {}
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    monkeypatch.setattr("brief.cli.push_artifacts",
                        lambda **kw: captured.update(kw) or
                                      {"branch": "main", "sha": "abc1234",
                                       "pushed": True})
    cli.main(["run", f"--artifacts-dir={tmp_path}", "--push-main"])
    assert captured["branch"] == "main"


def test_email_flag_invokes_send_email(tmp_path, monkeypatch, fake_run_result):
    sent = []
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    monkeypatch.setattr("brief.cli.push_artifacts",
                        lambda **kw: {"branch": "main", "sha": "abc1234", "pushed": True})
    monkeypatch.setattr("brief.cli.send_email",
                        lambda **kw: sent.append(kw))
    monkeypatch.setenv("BREVO_API_KEY", "x")
    monkeypatch.setenv("FROM_EMAIL", "adnan@example.com")
    cli.main(["run", f"--artifacts-dir={tmp_path}", "--push-main", "--email"])
    assert len(sent) == 1
    assert sent[0]["from_email"] == "adnan@example.com"


def test_email_without_api_key_is_skipped(tmp_path, monkeypatch, fake_run_result, capsys):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    monkeypatch.setattr("brief.cli.push_artifacts",
                        lambda **kw: {"branch": "main", "sha": "x", "pushed": True})
    sent = []
    monkeypatch.setattr("brief.cli.send_email", lambda **kw: sent.append(kw))
    cli.main(["run", f"--artifacts-dir={tmp_path}", "--push-main", "--email"])
    assert sent == []  # gracefully skipped


def test_run_report_top_level_duration_s_is_populated(tmp_path, monkeypatch, fake_run_result):
    """Top-level duration_s must reflect run_with_mode wallclock, not stay at 0.0."""
    import time as _time

    def slow_run(cfg, **kw):
        _time.sleep(0.05)
        return fake_run_result
    monkeypatch.setattr(cli, "run", slow_run)
    cli.main(["run", f"--artifacts-dir={tmp_path}"])
    report = json.loads((tmp_path / "run_report.json").read_text())
    assert report["duration_s"] >= 0.04, f"expected wallclock-derived duration_s, got {report['duration_s']}"
    assert report["duration_s"] < 5.0  # sanity bound
