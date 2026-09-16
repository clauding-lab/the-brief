"""Tests for deploy/brief_guard.sh — branch, disk-free, and binary checks.

The guard runs WITHOUT the `-` ExecStartPre prefix in brief.service, so a
non-zero exit holds the daily publish and fires the OnFailure Discord alert
(see AGENTS.md landmine 39, AGENT_LEARNINGS.md 2026-09-16). These tests run
the script by path against a disposable temp git repo and temp binaries —
never against the real /home/adnan/the-brief checkout.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="brief_guard.sh is a bash script"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD = REPO_ROOT / "deploy" / "brief_guard.sh"

GIT = os.environ.get("BRIEF_TEST_GIT") or shutil.which("git") or "git"
_GIT_DIR = str(Path(GIT).parent)


def _base_path() -> str:
    """PATH for the subprocess: the git this test suite was told to use,
    plus the minimal system dirs the guard's own `command -v` / `df` /
    `stat` / `readlink` calls need. Deliberately excludes any directory
    that might carry a real `claude` binary, so tests control that."""
    parts = [p for p in (_GIT_DIR, "/usr/bin", "/bin") if p and p != "."]
    return os.pathsep.join(parts)


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        [GIT, *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": _base_path(), "HOME": str(cwd)},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A one-commit temp git repo on branch `main`."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _run_git(["init", "-q"], cwd=repo_dir)
    _run_git(["config", "user.email", "brief-guard-test@example.com"], cwd=repo_dir)
    _run_git(["config", "user.name", "brief-guard-test"], cwd=repo_dir)
    (repo_dir / "README.md").write_text("brief_guard test repo\n")
    _run_git(["add", "README.md"], cwd=repo_dir)
    _run_git(["commit", "-q", "-m", "init"], cwd=repo_dir)
    _run_git(["branch", "-M", "main"], cwd=repo_dir)
    return repo_dir


@pytest.fixture
def repo_off_main(repo: Path) -> Path:
    """Same repo, but checked out on a non-main branch."""
    _run_git(["checkout", "-q", "-b", "feature"], cwd=repo)
    return repo


@pytest.fixture
def executable_claude(tmp_path: Path) -> Path:
    """A mode-755 shell script standing in for a real, installed claude."""
    bin_dir = tmp_path / "good-bin"
    bin_dir.mkdir()
    path = bin_dir / "claude"
    path.write_text("#!/bin/sh\necho fake-claude\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def stub_claude(tmp_path: Path) -> Path:
    """A 500-byte mode-644 file standing in for npm's half-installed stub."""
    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir()
    path = stub_dir / "claude"
    path.write_bytes(b"x" * 500)
    path.chmod(0o644)
    return path


def run_guard(
    repo_dir: Path,
    env_overrides: dict[str, str] | None = None,
    path_extra: str | None = None,
) -> subprocess.CompletedProcess[str]:
    path = _base_path()
    if path_extra:
        path = os.pathsep.join([path_extra, path])
    env = {"PATH": path, "BRIEF_REPO": str(repo_dir)}
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["bash", str(GUARD)],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


# (a) happy path
def test_happy_path_exits_zero(repo: Path, executable_claude: Path) -> None:
    result = run_guard(repo, {"CLAUDE_BINARY": str(executable_claude)})
    assert result.returncode == 0, result.stderr
    assert "branch=main" in result.stdout
    assert "disk_free_mb=" in result.stdout
    assert "claude=" in result.stdout


# (b) non-main branch
def test_non_main_branch_refuses(repo_off_main: Path, executable_claude: Path) -> None:
    result = run_guard(repo_off_main, {"CLAUDE_BINARY": str(executable_claude)})
    assert result.returncode == 1
    assert "only main" in result.stderr


# (c) stub binary
def test_stub_binary_refuses(repo: Path, stub_claude: Path) -> None:
    result = run_guard(repo, {"CLAUDE_BINARY": str(stub_claude)})
    assert result.returncode == 1
    assert "not an executable file" in result.stderr
    assert "landmine 39" in result.stderr


# (d) missing path
def test_missing_binary_path_refuses(repo: Path, tmp_path: Path) -> None:
    missing = tmp_path / "nowhere" / "claude"
    result = run_guard(repo, {"CLAUDE_BINARY": str(missing)})
    assert result.returncode == 1


# (e) CLAUDE_BINARY unset, no claude on PATH
def test_unset_binary_not_on_path_refuses(repo: Path) -> None:
    result = run_guard(repo, {})
    assert result.returncode == 1
    assert "not found on PATH" in result.stderr


# (f) CLAUDE_BINARY unset, a claude shim on PATH
def test_unset_binary_found_via_path(repo: Path, executable_claude: Path) -> None:
    result = run_guard(repo, {}, path_extra=str(executable_claude.parent))
    assert result.returncode == 0, result.stderr
    assert "claude=" in result.stdout


# (g) disk-free threshold
def test_disk_below_threshold_refuses(repo: Path, executable_claude: Path) -> None:
    result = run_guard(
        repo,
        {
            "CLAUDE_BINARY": str(executable_claude),
            "BRIEF_MIN_FREE_MB": "999999999",
        },
    )
    assert result.returncode == 1
    assert "MB free" in result.stderr


# (h) ordering: branch check wins over binary check
def test_branch_check_wins_over_binary_check(
    repo_off_main: Path, stub_claude: Path
) -> None:
    result = run_guard(repo_off_main, {"CLAUDE_BINARY": str(stub_claude)})
    assert result.returncode == 1
    assert "only main" in result.stderr
    assert "not an executable file" not in result.stderr
