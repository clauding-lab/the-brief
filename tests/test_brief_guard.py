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
    # _base_path() includes /usr/bin for df/stat/readlink; on the real box
    # AGENTS.md landmine 39 records a real (stale) /usr/bin/claude there, which
    # would make this case exercise test_stale_prefix_binary_refuses's path
    # instead of the true PATH-miss path this test is named for (review LOW,
    # 2026-09-16). Skip rather than false-fail in the one place this would be
    # run under pressure — the true PATH-miss behaviour is still exercised on
    # every host that has no /usr/bin/claude (CI, this Mac).
    if shutil.which("claude", path="/usr/bin"):
        pytest.skip("a real /usr/bin/claude exists on this host (landmine 39)")
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


# --- Review hardening pass, 2026-09-16 (findings below regression-locked) ---


# (i) BRIEF_MIN_FREE_MB set to something that isn't a plain integer must
# REFUSE, not silently disable the disk floor (a bash `((...))` comparison
# against "2G" is a no-op false, which fail-opens past the check) and not
# crash with an unbound-variable error and no refusal message either.
def test_min_free_mb_non_numeric_refuses(repo: Path, executable_claude: Path) -> None:
    result = run_guard(
        repo,
        {"CLAUDE_BINARY": str(executable_claude), "BRIEF_MIN_FREE_MB": "2G"},
    )
    assert result.returncode == 1
    assert "BRIEF_MIN_FREE_MB" in result.stderr
    assert "not a plain integer" in result.stderr


@pytest.fixture
def stub_dash_df(tmp_path: Path) -> Path:
    """A fake `df` that reports Available as `-` (as GNU df does for a
    filesystem that doesn't report block counts) instead of a number."""
    bin_dir = tmp_path / "dash-df-bin"
    bin_dir.mkdir()
    path = bin_dir / "df"
    path.write_text(
        "#!/bin/sh\n"
        "echo 'Filesystem 1024-blocks Used Available Capacity Mounted'\n"
        "echo 'fake 100 100 - 100% /'\n"
    )
    path.chmod(0o755)
    return bin_dir


# (j) a `df` that reports a non-numeric Available column must REFUSE
# (fail-closed), not silently pass the disk check (bash's `((...))` treats a
# bad operand as a syntax error, not a comparison — the old code let that
# error fall through to the binary check and a normal exit 0).
def test_disk_free_non_numeric_refuses(
    repo: Path, executable_claude: Path, stub_dash_df: Path
) -> None:
    result = run_guard(
        repo,
        {"CLAUDE_BINARY": str(executable_claude)},
        path_extra=str(stub_dash_df),
    )
    assert result.returncode == 1
    assert "could not read free disk" in result.stderr


# (k) branch=/head= must be logged even when the fire is held at the disk or
# binary check — not only on the happy path — so an operator triaging a held
# fire can still tell which commit was checked out (brief.service's own
# comment on the second guard call promises this for every fire).
def test_branch_head_logged_on_disk_refusal(
    repo: Path, executable_claude: Path
) -> None:
    result = run_guard(
        repo,
        {
            "CLAUDE_BINARY": str(executable_claude),
            "BRIEF_MIN_FREE_MB": "999999999",
        },
    )
    assert result.returncode == 1
    assert "branch=main head=" in result.stdout


# (l) an unset CLAUDE_BINARY that resolves via PATH to something under the
# configured stale-binary prefix (production default: /usr/bin, where
# AGENTS.md landmine 39 records a separate, stale, root-owned `claude`) must
# be refused, not silently accepted as if it were the real npm-global build.
def test_stale_prefix_binary_refuses(repo: Path, executable_claude: Path) -> None:
    result = run_guard(
        repo,
        {"BRIEF_STALE_BINARY_PREFIX": str(executable_claude.parent)},
        path_extra=str(executable_claude.parent),
    )
    assert result.returncode == 1
    assert "landmine 39" in result.stderr
    assert "stale binary" in result.stderr


# (m) journald visibility: every refusal must also go through `logger`, since
# brief.service's StandardOutput/StandardError append this unit's own
# stdout/stderr straight to logs/brief-systemd.log — NOT the journal
# brief_alert.sh's Discord alert reads via `journalctl -u brief.service`.
# Without this, the alert never names the cause (review HIGH, 2026-09-16).
@pytest.fixture
def stub_logger(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "logger-bin"
    bin_dir.mkdir()
    capture = tmp_path / "logger-calls.log"
    path = bin_dir / "logger"
    path.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {capture}\n")
    path.chmod(0o755)
    return bin_dir, capture


def test_refusal_also_goes_through_logger(
    repo: Path, tmp_path: Path, stub_logger: tuple[Path, Path]
) -> None:
    logger_dir, capture = stub_logger
    missing = tmp_path / "nowhere" / "claude"
    result = run_guard(
        repo, {"CLAUDE_BINARY": str(missing)}, path_extra=str(logger_dir)
    )
    assert result.returncode == 1
    assert capture.exists(), "logger stub was never invoked"
    logged = capture.read_text()
    assert "brief_guard" in logged
    assert "not an executable file" in logged


# (n) the stub-binary refusal message must carry the REAL stat() values, not
# just the right words — a later edit to the stat format string (`-c '%s %A'`
# instead of `%s %a'`, or a dropped `-c`) would otherwise stay green on every
# platform this suite runs on.
def test_stub_binary_message_has_real_size_and_mode(
    repo: Path, stub_claude: Path
) -> None:
    result = run_guard(repo, {"CLAUDE_BINARY": str(stub_claude)})
    assert result.returncode == 1
    assert "size=500" in result.stderr
    assert "mode=644" in result.stderr


# (o) a dangling CLAUDE_BINARY symlink must produce a single-line refusal.
# BSD `readlink -f` prints a partial (non-empty) path for a dangling symlink
# AND exits non-zero; the old `$(readlink -f ... || printf ...)` ran the
# `printf` fallback anyway and concatenated both outputs into one variable,
# splitting the one-line refusal across two lines (GNU readlink -f on the
# real box returns 0 here, so production was never affected).
def test_dangling_symlink_binary_message_is_one_line(
    repo: Path, tmp_path: Path
) -> None:
    dangling = tmp_path / "dangling-claude"
    dangling.symlink_to(tmp_path / "does-not-exist")
    result = run_guard(repo, {"CLAUDE_BINARY": str(dangling)})
    assert result.returncode == 1
    lines_with_msg = [
        line for line in result.stderr.splitlines() if "not an executable file" in line
    ]
    assert len(lines_with_msg) == 1
    assert "->" in lines_with_msg[0]
