# tests/test_gitops.py
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, call

import pytest

from brief.gitops import push_artifacts


def _ok(stdout="abc1234\n"):
    return subprocess.CompletedProcess([], 0, stdout, "")


def test_shadow_branch_flow(tmp_path: Path, monkeypatch):
    calls = []
    def fake_run(argv, **kw):
        calls.append(argv)
        return _ok("abc1234\n")
    monkeypatch.setattr("brief.gitops.subprocess.run", fake_run)
    r = push_artifacts(repo_dir=tmp_path, branch="shadow/2026-04-25",
                       artifacts_dir=tmp_path / "artifacts",
                       message="shadow run 2026-04-25")
    assert r["pushed"] is True
    assert r["branch"] == "shadow/2026-04-25"
    # Expected git sequence:
    assert calls[0][:4] == ["git", "-C", str(tmp_path), "fetch"]
    assert "checkout" in calls[1]
    assert calls[-1][:4] == ["git", "-C", str(tmp_path), "push"]


def test_dry_run_does_not_push(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr("brief.gitops.subprocess.run",
                        lambda a, **k: (calls.append(a), _ok())[1])
    r = push_artifacts(repo_dir=tmp_path, branch="shadow/x",
                       artifacts_dir=tmp_path / "artifacts",
                       message="m", dry_run=True)
    assert r["pushed"] is False
    assert not any(a[:4] == ["git", "-C", str(tmp_path), "push"] for a in calls)


def test_main_branch_refuses_non_fast_forward(tmp_path: Path, monkeypatch):
    def fake_run(argv, **kw):
        if "merge-base" in argv:
            return _ok("deadbeef\n")
        if "rev-parse" in argv and "origin/main" in argv:
            return _ok("other123\n")  # origin/main advanced beyond merge-base
        return _ok()
    monkeypatch.setattr("brief.gitops.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="diverged|fast-forward"):
        push_artifacts(repo_dir=tmp_path, branch="main",
                       artifacts_dir=tmp_path / "artifacts",
                       message="cutover")
