"""Git push-back for Brief artifacts.

Shadow mode: fresh branch from origin/main, overwrite, push.
Main mode: fast-forward only; abort if main has advanced beyond our base.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _git(repo: Path, *args: str, check: bool = True) -> str:
    cp = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=check,
    )
    return cp.stdout.strip()


def push_artifacts(
    *,
    repo_dir: Path,
    branch: str,
    artifacts_dir: Path,
    message: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    _git(repo_dir, "fetch", "origin", "--prune")

    if branch == "main":
        base = _git(repo_dir, "merge-base", "HEAD", "origin/main")
        tip = _git(repo_dir, "rev-parse", "origin/main")
        if base != tip:
            raise RuntimeError(
                "main has diverged; refusing non-fast-forward push. "
                f"base={base[:8]} origin/main={tip[:8]}"
            )
        _git(repo_dir, "checkout", "main")
    else:
        # shadow: fresh branch from origin/main; overwrite local copy if exists
        _git(repo_dir, "checkout", "-B", branch, "origin/main")

    # Copy artifacts into the repo root (index.html, email.txt, run_report.json)
    for name in ("index.html", "email.txt", "run_report.json"):
        src = artifacts_dir / name
        if src.exists():
            (repo_dir / name).write_bytes(src.read_bytes())

    _git(repo_dir, "add", "index.html", "email.txt", "run_report.json")
    _git(repo_dir, "commit", "-m", message, check=False)  # no-op if nothing changed
    sha = _git(repo_dir, "rev-parse", "HEAD")

    pushed = False
    if not dry_run:
        # Shadow branches are throwaway dated scratch branches — re-running a
        # render on the same calendar day rebuilds the branch from origin/main
        # so the local history doesn't match what's on the remote, and a
        # plain push gets rejected as non-fast-forward. Force-with-lease is
        # safe here: the lease check still rejects if someone else has pushed
        # to the same shadow branch concurrently.
        # Main pushes stay fast-forward-only — guarded by the merge-base check
        # earlier in this function.
        if branch == "main":
            _git(repo_dir, "push", "origin", branch)
        else:
            _git(repo_dir, "push", "--force-with-lease", "origin", branch)
        pushed = True
    return {"branch": branch, "sha": sha[:7], "pushed": pushed}
