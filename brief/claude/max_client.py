"""Subprocess wrapper around the `claude -p` Max CLI.

No Anthropic API calls. Auth is via the OS user's ~/.claude/.credentials.json
(Max OAuth), injected by the CLI itself — we pass no tokens.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Per-response output ceiling handed to the CLI via CLAUDE_CODE_MAX_OUTPUT_TOKENS.
#
# Why this exists (issue 181, 2026-07-31): the Friday weekly wrap outgrew the
# CLI's default ceiling. The editor was cut off mid-JSON and continued the
# payload in a SECOND assistant message, while `--output-format json` reports
# only the FINAL message in `result` — so the pipeline received the tail of the
# brief and rejected it as a schema violation.
#
# NOTE (issue 183, 2026-08-02): 64_000 is the model's HARD per-response cap on
# claude-opus-4-8, not a tunable default — probing with 128_000 comes back 64_000.
# Pinning this value buys no headroom and never did; the actual fix is stitching
# every assistant message back together (see `_collect_stream_messages`). The
# constant stays because it is still the number the CLI is told, and because a
# future model with a larger cap makes it meaningful again.
DEFAULT_MAX_OUTPUT_TOKENS = 64_000

# Matches an opening fence (```json, ```JSON, ```, etc.) and a closing ```.
# The language tag is optional and case-insensitive.  re.DOTALL lets '.' match
# newlines so multi-line JSON bodies are captured in group(1).
_FENCE_RE = re.compile(
    r"^```[a-zA-Z]*\n(.*?)\n```$",
    re.DOTALL,
)


class MaxCallError(RuntimeError):
    """Raised when the CLI fails, times out, or returns non-JSON."""


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


def _collect_stream_messages(stdout: str) -> tuple[list[str], dict[str, Any]] | None:
    """Parse `--output-format stream-json` NDJSON into (assistant_texts, result_event).

    The CLI emits one JSON object per line. Assistant turns arrive as
    ``{"type": "assistant", "message": {"id": ..., "content": [{"type": "text",
    "text": ...}, ...]}}`` and the run ends with a single
    ``{"type": "result", "result": ..., "usage": ..., "num_turns": ...}``.

    When a response hits the per-response token cap the model is cut off and
    CONTINUES in a new assistant message — the text blocks concatenate back into
    the original payload byte-for-byte (verified against a forced-truncation
    probe, 2026-08-02). Returning them in order lets the caller stitch.

    One returned string per text-bearing assistant event, so ``len()`` is the
    assistant-message count the cut-off alarm keys on.

    De-duplication is by ``(message.id, that event's text)``, NOT by
    ``message.id`` alone: with ``--effort xhigh`` the CLI splits ONE assistant
    message into TWO events sharing an id — the ``thinking`` block first, the
    answer text second (live probe, 2026-08-09). Keying on the id alone kept the
    thinking-only event and dropped the event carrying the brief, so nothing was
    collected and the caller silently fell back to the result field: the exact
    ``--output-format json`` data loss this function exists to prevent (issue
    190/192). A genuinely re-emitted event repeats both id and text, so it is
    still de-duplicated; a continuation chunk differs in text and is kept.

    ``thinking`` blocks are skipped — they are not part of the answer, and an
    event with no text at all is not counted as a message. Lines that are not
    JSON are ignored (the CLI occasionally prints non-protocol noise on stdout).

    Returns None only if stdout carries neither an assistant nor a result event —
    i.e. it is not a stream payload at all and the caller should fall back to
    single-object parsing. Assistant text with no result event (a stream cut
    short) still returns what was captured rather than discarding it.
    """
    texts: list[str] = []
    seen: set[tuple[str, str]] = set()
    result_event: dict[str, Any] | None = None

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        etype = event.get("type")
        if etype == "result":
            result_event = event
        elif etype == "assistant":
            message = event.get("message") or {}
            event_text = "".join(
                block.get("text") or ""
                for block in message.get("content") or []
                if isinstance(block, dict) and block.get("type") == "text"
            )
            if not event_text:
                continue
            msg_id = message.get("id")
            if msg_id is not None:
                key = (msg_id, event_text)
                if key in seen:
                    continue
                seen.add(key)
            texts.append(event_text)

    if result_event is None:
        if not texts:
            return None
        logger.warning(
            "run_max: stream ended with %d assistant message(s) but no result "
            "event — usage and cost will be unavailable.", len(texts),
        )
        return texts, {}
    return texts, result_event


def _parse_cli_stdout(stdout: str) -> tuple[str, dict[str, Any], int]:
    """Return (raw_text, result_event, assistant_message_count) from CLI stdout.

    Handles both output shapes:
      * `--output-format stream-json` — NDJSON; assistant messages are stitched
        in arrival order so a cut-off response is reassembled whole.
      * `--output-format json` — a single result object whose `result` field
        holds only the FINAL assistant message. Kept as a fallback so callers
        (and fixtures) built against the older shape still work.
    """
    stream = _collect_stream_messages(stdout)
    if stream is not None:
        texts, result_event = stream
        if texts:
            return "".join(texts), result_event, len(texts)
        # No assistant text captured (e.g. an error result): fall back to the
        # result field so the caller still sees whatever the CLI reported.
        fallback = result_event.get("result", "")
        return (fallback if isinstance(fallback, str) else ""), result_event, 0

    try:
        outer = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise MaxCallError(f"Claude CLI stdout is not JSON: {e}") from e
    if not isinstance(outer, dict):
        raise MaxCallError("Claude CLI stdout is not a JSON object")

    raw_text = outer.get("result", "")
    if not isinstance(raw_text, str):
        raise MaxCallError("Claude CLI returned non-string result field")
    return raw_text, outer, 1 if raw_text else 0


@dataclass(frozen=True)
class MaxCallResult:
    raw_text: str        # Claude's `result` field as a string
    parsed: Any | None   # json.loads(raw_text) or None if result wasn't JSON
    usage: dict[str, Any]
    total_cost_usd: float | None
    duration_s: float = 0.0
    tokens: dict[str, int] = field(
        default_factory=lambda: {"input": 0, "output": 0, "thinking": 0}
    )
    num_turns: int = 0   # CLI-reported turn count; NOT a cut-off signal (see below)
    assistant_messages: int = 0  # >1 means the response was cut off and stitched


def run_max(
    *,
    prompt: str,
    model: str = "claude-opus-4-8",
    timeout_s: int = 1800,
    claude_binary: str | None = None,
    effort: str = "xhigh",
    via_stdin: bool | None = None,
    max_output_tokens: int | None = None,
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
    if max_output_tokens is None:
        try:
            max_output_tokens = int(
                os.environ.get("BRIEF_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS)
            )
        except ValueError:
            logger.warning(
                "BRIEF_MAX_OUTPUT_TOKENS=%r is not an integer — falling back to %d",
                os.environ.get("BRIEF_MAX_OUTPUT_TOKENS"), DEFAULT_MAX_OUTPUT_TOKENS,
            )
            max_output_tokens = DEFAULT_MAX_OUTPUT_TOKENS

    argv = [claude_binary, "-p"]
    if not via_stdin:
        argv.append(prompt)
    argv += [
        "--model", model,
        # stream-json (NDJSON), NOT json: the single-object `json` shape reports
        # only the FINAL assistant message in `result`, so a response cut off at
        # the token cap loses everything written before the cut (issue 181/183).
        # The stream emits every assistant message; `_parse_cli_stdout` stitches
        # them. --verbose is mandatory for stream-json under --print.
        "--output-format", "stream-json",
        "--verbose",
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
            env={
                **os.environ,
                "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(max_output_tokens),
            },
        )
    except subprocess.TimeoutExpired as e:
        raise MaxCallError(f"Claude CLI timed out after {timeout_s}s") from e
    except FileNotFoundError as e:
        raise MaxCallError(f"Claude CLI binary not found: {claude_binary}") from e

    if cp.returncode != 0:
        # The CLI writes its error payload to STDOUT (stderr is frequently
        # empty) and exits non-zero. Surface BOTH so a failure is diagnosable
        # instead of an opaque "exited 1".
        #
        # Show the TAIL, not the head. Under --output-format stream-json the
        # first line is always the `system/init` event — a ~1.2 KB inventory of
        # slash commands and agent names, identical on every run. Slicing the
        # head therefore spent the whole budget on boilerplate and never reached
        # the error: the 2026-08-19 publish failed 3/3 attempts and all three
        # log lines are pure init noise, so that outage cannot be diagnosed
        # today. The real payload is always at the end of the stream.
        raise MaxCallError(
            f"Claude CLI exited {cp.returncode}: "
            f"stderr={cp.stderr.strip()[-500:]!r} "
            f"stdout_tail={cp.stdout.strip()[-1200:]!r}"
        )

    raw_text, outer, _assistant_messages = _parse_cli_stdout(cp.stdout)

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
    _num_turns = int(outer.get("num_turns") or 0)
    _usage = outer.get("usage") or {}
    # `output_tokens` is the WHOLE output budget: thinking blocks count against
    # it even though `_collect_stream_messages` (correctly) drops them from the
    # answer text. The CLI reports the split under
    # `usage.output_tokens_details.thinking_tokens` — verified live 2026-08-23
    # against a trivial one-line prompt, where 167 of 178 output tokens were
    # thinking. Without this field the cut-off alarm is unreadable: it shows a
    # 65k output next to a 33k-char answer and invites the wrong conclusion
    # ("the brief got too long") when the answer is a small minority of the
    # spend. Absent on a model or CLI that doesn't report it — 0, not a crash.
    _details = _usage.get("output_tokens_details") or {}
    _tokens = {
        "input": int(_usage.get("input_tokens") or 0),
        "output": int(_usage.get("output_tokens") or 0),
        "thinking": int((_details or {}).get("thinking_tokens") or 0),
    }
    # The headroom gauge. #172 wired the thinking split into the two FAILURE
    # paths only (cut-off, parse failure), which measures the engine solely once
    # it is already overheating — a clean run recorded nothing. The number that
    # actually decides the effort/split/adaptive-retry question is how close a
    # HEALTHY run gets to the ceiling, so log it unconditionally, at INFO (the
    # service logs at INFO; DEBUG would keep it invisible).
    logger.info(
        "run_max: output_tokens=%s of which thinking=%s (%.1f%% of the "
        "%d ceiling), answer=%d chars, assistant_messages=%d, %.1fs",
        _tokens["output"],
        _tokens["thinking"],
        100.0 * _tokens["output"] / max_output_tokens,
        max_output_tokens,
        len(raw_text),
        _assistant_messages,
        _duration,
    )
    if _assistant_messages > 1:
        # The response hit the per-response cap and continued in a new assistant
        # message. We stitched it — this is recovery, not failure — but it must
        # be visible: it says the payload is at the model's hard ceiling, and the
        # next growth spurt lands somewhere with no stitching to save it.
        #
        # Do NOT gate this on `parsed is None` (the issue-181 alarm did, and the
        # preamble fallback salvaged a fragment so it never fired) and do NOT
        # gate it on `num_turns` — a cut-off-and-continued response is still
        # ONE turn, so num_turns stays 1. Assistant-message count is the signal.
        level = logging.ERROR if parsed is None else logging.WARNING
        logger.log(
            level,
            "run_max: response was CUT OFF and continued across %d assistant "
            "messages — stitched into %d chars (parsed=%s, output_tokens=%s of "
            "which thinking=%s, max_output_tokens=%d). The ceiling is spent on "
            "output_tokens as a WHOLE: thinking counts against it, and on this "
            "workload it is the large majority. Read the thinking share before "
            "concluding the answer is too long.",
            _assistant_messages, len(raw_text), parsed is not None,
            _tokens["output"], _tokens["thinking"], max_output_tokens,
        )
    elif parsed is None:
        logger.error(
            "run_max: response did not parse as JSON (raw_len=%d, "
            "assistant_messages=%d, output_tokens=%s of which thinking=%s).",
            len(raw_text), _assistant_messages,
            _tokens["output"], _tokens["thinking"],
        )
    return MaxCallResult(
        raw_text=raw_text,
        parsed=parsed,
        usage=_usage,
        total_cost_usd=outer.get("total_cost_usd"),
        duration_s=_duration,
        tokens=_tokens,
        num_turns=_num_turns,
        assistant_messages=_assistant_messages,
    )
