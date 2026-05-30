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


def _extract_json_object(text: str) -> str | None:
    """Best-effort extraction of a single top-level JSON object from text.

    Sometimes the model returns prose preamble before the JSON body
    (e.g., "I'll audit the editor's output now.\\n\\n{...}"). This finds the
    first '{' and walks bracket depth to find its matching '}', returning
    that substring. Returns None if no balanced object is found.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


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
    model: str = "claude-opus-4-8",
    timeout_s: int = 1800,
    claude_binary: str | None = None,
    effort: str = "xhigh",
    via_stdin: bool | None = None,
) -> MaxCallResult:
    """Invoke the Claude Max CLI, return parsed result.

    Binary resolution (highest precedence first):
      1. explicit `claude_binary=` argument
      2. `CLAUDE_BINARY` env var — lets VPS deploys point at an absolute
         path (e.g. /home/adnan/.npm-global/bin/claude) regardless of
         the PATH that cron/systemd inherits.
      3. `"claude"` — resolves via $PATH at subprocess launch.

    When the prompt is large enough to risk Linux's ARG_MAX cap (~128KB),
    pass it via stdin instead of argv. Auto-detected when prompt > 64KB,
    or override with via_stdin=True/False.
    """
    if claude_binary is None:
        claude_binary = os.environ.get("CLAUDE_BINARY", "claude")
    if via_stdin is None:
        via_stdin = len(prompt) > 64_000

    argv = [claude_binary, "-p"]
    if not via_stdin:
        argv.append(prompt)
    argv += [
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
        # On Opus 4.7+ (we pin 4.8) effort drives *adaptive thinking*: at
        # high/xhigh/max the model almost always thinks deeply. There is NO
        # separate thinking flag/env in headless mode — MAX_THINKING_TOKENS is
        # ignored by Opus 4.7+. So --effort xhigh == "xhigh + thinking on".
        "--effort", effort,
    ]
    if via_stdin:
        argv += ["--input-format", "text"]

    _t0 = time.monotonic()
    try:
        cp = subprocess.run(
            argv,
            input=prompt if via_stdin else None,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise MaxCallError(f"Claude CLI timed out after {timeout_s}s") from e
    except FileNotFoundError as e:
        raise MaxCallError(f"Claude CLI binary not found: {claude_binary}") from e

    if cp.returncode != 0:
        # In --output-format json mode the CLI writes its error payload to
        # STDOUT (stderr is frequently empty) and exits non-zero. Surface BOTH
        # so a failure is diagnosable instead of an opaque "exited 1".
        raise MaxCallError(
            f"Claude CLI exited {cp.returncode}: "
            f"stderr={cp.stderr.strip()[:500]!r} stdout={cp.stdout.strip()[:1200]!r}"
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
        # Fallback for prose-then-JSON outputs (the subeditor occasionally
        # writes a preamble like "I'll audit the editor's output now.\n\n{...}").
        embedded = _extract_json_object(raw_text)
        if embedded is not None:
            try:
                parsed = json.loads(embedded)
            except json.JSONDecodeError:
                parsed = None
        else:
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
