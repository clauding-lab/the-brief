"""Regression tests for the issue-181 truncation failure (2026-07-31).

The Friday weekly wrap outgrew the CLI's default per-response output ceiling.
The editor was cut off mid-JSON, continued in a SECOND assistant message, and
`--output-format json` surfaces only the FINAL message in `result` — so the
pipeline received the tail of the brief and rejected it as a schema violation,
three publishes in a row.

These tests pin the two guards that came out of it:
  1. run_max always hands the CLI an explicit CLAUDE_CODE_MAX_OUTPUT_TOKENS.
  2. run_max reports num_turns, so a multi-turn (= cut off) response is visible.
"""
import json
from unittest.mock import MagicMock, patch

from brief.claude.max_client import DEFAULT_MAX_OUTPUT_TOKENS, run_max


def _fake_completed(stdout: str, returncode: int = 0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    m.stderr = ""
    return m


def _outer(result_str: str = "{}", **extra) -> str:
    payload = {
        "result": result_str,
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "total_cost_usd": 0.0,
    }
    payload.update(extra)
    return json.dumps(payload)


class TestMaxOutputTokensEnv:
    def test_default_ceiling_is_passed_to_the_cli(self, monkeypatch):
        # Arrange
        monkeypatch.delenv("BRIEF_MAX_OUTPUT_TOKENS", raising=False)
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(_outer())) as sp:
            run_max(prompt="hi")
        # Assert
        env = sp.call_args.kwargs["env"]
        assert env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == str(DEFAULT_MAX_OUTPUT_TOKENS)

    def test_default_ceiling_is_large_enough_for_a_full_brief(self):
        # The observed issue-181 run burned 72k output tokens across turns; the
        # ceiling must be well above a single brief's payload, not a token gesture.
        assert DEFAULT_MAX_OUTPUT_TOKENS >= 32_000

    def test_explicit_kwarg_overrides_the_default(self, monkeypatch):
        # Arrange
        monkeypatch.delenv("BRIEF_MAX_OUTPUT_TOKENS", raising=False)
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(_outer())) as sp:
            run_max(prompt="hi", max_output_tokens=12_345)
        # Assert
        assert sp.call_args.kwargs["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "12345"

    def test_env_var_overrides_the_default(self, monkeypatch):
        # Arrange
        monkeypatch.setenv("BRIEF_MAX_OUTPUT_TOKENS", "48000")
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(_outer())) as sp:
            run_max(prompt="hi")
        # Assert
        assert sp.call_args.kwargs["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "48000"

    def test_garbage_env_var_falls_back_instead_of_crashing(self, monkeypatch):
        # Arrange — a typo in /etc/brief.env must not take the 06:30 publish down
        monkeypatch.setenv("BRIEF_MAX_OUTPUT_TOKENS", "sixty-four thousand")
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(_outer())) as sp:
            run_max(prompt="hi")
        # Assert
        env = sp.call_args.kwargs["env"]
        assert env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == str(DEFAULT_MAX_OUTPUT_TOKENS)

    def test_existing_environment_is_preserved(self, monkeypatch):
        # Arrange — the CLI still needs PATH, HOME, credentials, etc.
        monkeypatch.setenv("BRIEF_CANARY_VAR", "still-here")
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(_outer())) as sp:
            run_max(prompt="hi")
        # Assert
        assert sp.call_args.kwargs["env"]["BRIEF_CANARY_VAR"] == "still-here"


class TestNumTurnsVisibility:
    def test_num_turns_is_surfaced(self):
        # Arrange — a cut-off-then-continued response reports >1 turn
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(_outer(num_turns=3))):
            r = run_max(prompt="hi")
        # Assert
        assert r.num_turns == 3

    def test_num_turns_defaults_to_zero_when_absent(self):
        # Arrange — older CLI payloads may omit the field entirely
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(_outer())):
            r = run_max(prompt="hi")
        # Assert
        assert r.num_turns == 0

    def test_multi_turn_unparseable_response_is_logged_as_truncation(self, caplog):
        # Arrange — this is the exact issue-181 signature: tail-only JSON that
        # parses to something, or not at all, after a multi-turn generation.
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(
                       _outer("no json here at all", num_turns=2))):
            with caplog.at_level("ERROR"):
                r = run_max(prompt="hi")
        # Assert
        assert r.parsed is None
        assert "CUT OFF" in caplog.text
