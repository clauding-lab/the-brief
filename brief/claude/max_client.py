"""Subprocess wrapper around the `claude -p` Max CLI.

No Anthropic API calls. Auth is via the OS user's ~/.claude/.credentials.json
(Max OAuth), injected by the CLI itself — we pass no tokens.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any


class MaxCallError(RuntimeError):
    """Raised when the CLI fails, times out, or returns non-JSON."""


@dataclass(frozen=True)
class MaxCallResult:
    raw_text: str        # Claude's `result` field as a string
    parsed: Any | None   # json.loads(raw_text) or None if result wasn't JSON
    usage: dict[str, Any]
    total_cost_usd: float | None
    duration_s: float = 0.0
    tokens: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})


def run_max(
    *,
    prompt: str,
    model: str = "claude-opus-4-7",
    timeout_s: int = 1800,
    claude_binary: str | None = None,
) -> MaxCallResult:
    """Invoke the Claude Max CLI, return parsed result.

    Binary resolution (highest precedence first):
      1. explicit `claude_binary=` argument
      2. `CLAUDE_BINARY` env var — lets VPS deploys point at an absolute
         path (e.g. /home/adnan/.npm-global/bin/claude) regardless of
         the PATH that cron/systemd inherits.
      3. `"claude"` — resolves via $PATH at subprocess launch.
    """
    if claude_binary is None:
        claude_binary = os.environ.get("CLAUDE_BINARY", "claude")
    argv = [
        claude_binary, "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--no-session-persistence",
        "--tools", "",
        "--permission-mode", "bypassPermissions",
    ]
    _t0 = time.monotonic()
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

    _duration = time.monotonic() - _t0
    _usage = outer.get("usage") or {}
    _tokens = {
        "input": int(_usage.get("input_tokens") or 0),
        "output": int(_usage.get("output_tokens") or 0),
    }

    return MaxCallResult(
        raw_text=raw_text,
        parsed=parsed,
        usage=_usage,
        total_cost_usd=outer.get("total_cost_usd"),
        duration_s=_duration,
        tokens=_tokens,
    )
