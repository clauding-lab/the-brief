"""Subprocess wrapper around the `claude -p` Max CLI.

No Anthropic API calls. Auth is via the OS user's ~/.claude/.credentials.json
(Max OAuth), injected by the CLI itself — we pass no tokens.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

# Matches an opening fence (```json, ```JSON, ```, etc.) and a closing ```.
# The language tag is optional and case-insensitive.  re.DOTALL lets '.' match
# newlines so multi-line JSON bodies are captured in group(1).
_FENCE_RE = re.compile(
    r"^```[a-zA-Z]*\n(.*?)\n```$",
    re.DOTALL,
)


def _strip_markdown_fences(text: str) -> str:
    """Return *text* with surrounding markdown code fences removed.

    Claude occasionally wraps its JSON output in triple-backtick fences even
    when asked for bare JSON.  This helper strips them so json.loads() can
    succeed.  If no fence is detected the text is returned unchanged.

    Only the outermost fence pair is removed; ``MaxCallResult.raw_text`` is
    intentionally left as-returned so future debugging retains the original
    Claude output.
    """
    stripped = text.strip()
    m = _FENCE_RE.match(stripped)
    if m:
        return m.group(1)
    # Return the stripped version only if text had leading/trailing whitespace;
    # otherwise preserve the original so callers that check identity still work.
    return stripped if stripped != text else text


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
    model: str = "claude-opus-4-6",
    timeout_s: int = 1800,
    claude_binary: str | None = None,
    effort: str = "high",
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
        # Without --strict-mcp-config the CLI loads any user-installed MCP
        # plugins (e.g. the Discord-bot plugin on Hetzner) and the agent
        # treats prompts as conversational — routing the response to the
        # Discord channel instead of stdout. This flag tells Claude to
        # use ONLY MCP servers passed via --mcp-config; we pass none, so
        # zero MCP tools load. Pure stdout JSON, no side channels.
        "--strict-mcp-config",
        "--permission-mode", "bypassPermissions",
        "--effort", effort,
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
        parsed = json.loads(_strip_markdown_fences(raw_text))
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
