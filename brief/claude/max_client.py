"""Subprocess wrapper around the `claude -p` Max CLI.

No Anthropic API calls. Auth is via the OS user's ~/.claude/.credentials.json
(Max OAuth), injected by the CLI itself — we pass no tokens.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


class MaxCallError(RuntimeError):
    """Raised when the CLI fails, times out, or returns non-JSON."""


@dataclass(frozen=True)
class MaxCallResult:
    raw_text: str        # Claude's `result` field as a string
    parsed: Any | None   # json.loads(raw_text) or None if result wasn't JSON
    usage: dict[str, Any]
    total_cost_usd: float | None


def run_max(
    *,
    prompt: str,
    model: str = "claude-opus-4-7",
    timeout_s: int = 1800,
    claude_binary: str = "claude",
) -> MaxCallResult:
    """Invoke the Claude Max CLI, return parsed result."""
    argv = [
        claude_binary, "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--no-session-persistence",
        "--tools", "",
        "--permission-mode", "bypassPermissions",
    ]
    try:
        cp = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise MaxCallError(f"Claude CLI timed out after {timeout_s}s") from e
    except FileNotFoundError as e:
        raise MaxCallError(f"Claude CLI binary not found: {claude_binary}") from e

    if cp.returncode != 0:
        raise MaxCallError(
            f"Claude CLI exited {cp.returncode}: {cp.stderr.strip()[:500]}"
        )

    try:
        outer = json.loads(cp.stdout)
    except json.JSONDecodeError as e:
        raise MaxCallError(f"Claude CLI stdout is not JSON: {e}") from e

    raw_text = outer.get("result", "")
    if not isinstance(raw_text, str):
        raise MaxCallError("Claude CLI returned non-string result field")

    parsed: Any | None
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = None

    return MaxCallResult(
        raw_text=raw_text,
        parsed=parsed,
        usage=outer.get("usage") or {},
        total_cost_usd=outer.get("total_cost_usd"),
    )
