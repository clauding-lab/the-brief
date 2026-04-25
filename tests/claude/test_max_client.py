import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from brief.claude.max_client import (
    MaxCallError, MaxCallResult, run_max,
)


def _fake_completed(stdout: str, returncode: int = 0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    m.stderr = ""
    return m


def test_run_max_returns_parsed_json():
    claude_payload = {
        "result": json.dumps({"selected": [], "rationale_bullet": "x"}),
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "total_cost_usd": 0.01,
    }
    with patch("brief.claude.max_client.subprocess.run",
               return_value=_fake_completed(json.dumps(claude_payload))):
        r = run_max(prompt="hi", timeout_s=60)

    assert isinstance(r, MaxCallResult)
    assert r.parsed == {"selected": [], "rationale_bullet": "x"}
    assert r.usage == {"input_tokens": 10, "output_tokens": 5}
    assert r.raw_text == json.dumps({"selected": [], "rationale_bullet": "x"})


def test_run_max_rejects_bad_returncode():
    with patch("brief.claude.max_client.subprocess.run",
               return_value=_fake_completed("", returncode=1)):
        with pytest.raises(MaxCallError):
            run_max(prompt="hi", timeout_s=60)


def test_run_max_rejects_non_json_outer():
    with patch("brief.claude.max_client.subprocess.run",
               return_value=_fake_completed("not json")):
        with pytest.raises(MaxCallError):
            run_max(prompt="hi", timeout_s=60)


def test_run_max_returns_raw_text_when_result_is_not_json():
    with patch("brief.claude.max_client.subprocess.run",
               return_value=_fake_completed(json.dumps({
                   "result": "plain text not json",
                   "usage": {},
               }))):
        r = run_max(prompt="hi", timeout_s=60)
    assert r.parsed is None
    assert r.raw_text == "plain text not json"


def test_run_max_wraps_timeout():
    with patch("brief.claude.max_client.subprocess.run",
               side_effect=subprocess.TimeoutExpired("claude", 60)):
        with pytest.raises(MaxCallError):
            run_max(prompt="hi", timeout_s=60)


def test_run_max_honors_claude_binary_env_var(monkeypatch):
    claude_payload = {"result": "ok", "usage": {}}
    with patch("brief.claude.max_client.subprocess.run",
               return_value=_fake_completed(json.dumps(claude_payload))) as sp:
        monkeypatch.setenv("CLAUDE_BINARY", "/home/adnan/.npm-global/bin/claude")
        run_max(prompt="hi", timeout_s=60)
    argv = sp.call_args.args[0]
    assert argv[0] == "/home/adnan/.npm-global/bin/claude"


def test_run_max_explicit_binary_beats_env_var(monkeypatch):
    claude_payload = {"result": "ok", "usage": {}}
    with patch("brief.claude.max_client.subprocess.run",
               return_value=_fake_completed(json.dumps(claude_payload))) as sp:
        monkeypatch.setenv("CLAUDE_BINARY", "/env/var/claude")
        run_max(prompt="hi", timeout_s=60, claude_binary="/explicit/claude")
    argv = sp.call_args.args[0]
    assert argv[0] == "/explicit/claude"


def test_run_max_defaults_to_plain_claude_when_no_env_var(monkeypatch):
    claude_payload = {"result": "ok", "usage": {}}
    with patch("brief.claude.max_client.subprocess.run",
               return_value=_fake_completed(json.dumps(claude_payload))) as sp:
        monkeypatch.delenv("CLAUDE_BINARY", raising=False)
        run_max(prompt="hi", timeout_s=60)
    argv = sp.call_args.args[0]
    assert argv[0] == "claude"


def test_max_call_result_exposes_duration_and_tokens():
    fake_stdout = json.dumps({
        "result": '{"x":1}',
        "usage": {"input_tokens": 100, "output_tokens": 50},
        "total_cost_usd": 0.0042,
    })
    with patch("brief.claude.max_client.subprocess.run",
               return_value=_fake_completed(fake_stdout)):
        r = run_max(prompt="hi")
    assert r.total_cost_usd == pytest.approx(0.0042)
    assert r.duration_s >= 0
    assert r.tokens == {"input": 100, "output": 50}


# ---------------------------------------------------------------------------
# Fence-stripping tests (RED -> GREEN with _strip_markdown_fences fix)
# ---------------------------------------------------------------------------

class TestStripMarkdownFences:
    """Unit tests for the _strip_markdown_fences helper."""

    def test_import_helper_exists(self):
        # Arrange / Act / Assert
        from brief.claude.max_client import _strip_markdown_fences  # noqa: F401

    def test_bare_json_object_unchanged(self):
        # Arrange
        from brief.claude.max_client import _strip_markdown_fences
        text = '{"a": 1}'
        # Act
        result = _strip_markdown_fences(text)
        # Assert
        assert result == '{"a": 1}'

    def test_strips_json_fenced_block(self):
        # Arrange
        from brief.claude.max_client import _strip_markdown_fences
        text = '```json\n{"a": 1}\n```'
        # Act
        result = _strip_markdown_fences(text)
        # Assert
        assert result == '{"a": 1}'

    def test_strips_plain_fenced_block(self):
        # Arrange
        from brief.claude.max_client import _strip_markdown_fences
        text = '```\n{"a": 1}\n```'
        # Act
        result = _strip_markdown_fences(text)
        # Assert
        assert result == '{"a": 1}'

    def test_strips_fences_with_surrounding_whitespace(self):
        # Arrange
        from brief.claude.max_client import _strip_markdown_fences
        text = '  ```json\n{"a": 1}\n```  '
        # Act
        result = _strip_markdown_fences(text)
        # Assert
        assert result == '{"a": 1}'

    def test_strips_fenced_array(self):
        # Arrange
        from brief.claude.max_client import _strip_markdown_fences
        text = '```json\n[1, 2, 3]\n```'
        # Act
        result = _strip_markdown_fences(text)
        # Assert
        assert result == '[1, 2, 3]'

    def test_strips_uppercase_json_tag(self):
        # Arrange
        from brief.claude.max_client import _strip_markdown_fences
        text = '```JSON\n{"a": 1}\n```'
        # Act
        result = _strip_markdown_fences(text)
        # Assert
        assert result == '{"a": 1}'

    def test_empty_string_unchanged(self):
        # Arrange
        from brief.claude.max_client import _strip_markdown_fences
        text = ''
        # Act
        result = _strip_markdown_fences(text)
        # Assert
        assert result == ''

    def test_plain_text_unchanged(self):
        # Arrange
        from brief.claude.max_client import _strip_markdown_fences
        text = 'plain text not json'
        # Act
        result = _strip_markdown_fences(text)
        # Assert
        assert result == 'plain text not json'

    def test_multiline_inner_json_preserved(self):
        # Arrange
        from brief.claude.max_client import _strip_markdown_fences
        inner = '{\n  "insights": {\n    "fx": ["s1", "s2"]\n  }\n}'
        text = f'```json\n{inner}\n```'
        # Act
        result = _strip_markdown_fences(text)
        # Assert
        assert result == inner


class TestRunMaxFenceStripping:
    """Integration tests: run_max parses JSON even when Claude wraps in fences."""

    def _make_outer(self, result_str: str) -> str:
        return json.dumps({
            "result": result_str,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })

    def test_fenced_json_object_parsed_correctly(self):
        # Arrange
        fenced = '```json\n{"insights": {"fx": ["s1", "s2", "s3", "s4"]}}\n```'
        outer = self._make_outer(fenced)
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(outer)):
            r = run_max(prompt="test", timeout_s=60)
        # Assert -- parsed must be the dict, not None
        assert r.parsed == {"insights": {"fx": ["s1", "s2", "s3", "s4"]}}

    def test_plain_fenced_block_parsed_correctly(self):
        # Arrange
        fenced = '```\n{"a": 1}\n```'
        outer = self._make_outer(fenced)
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(outer)):
            r = run_max(prompt="test", timeout_s=60)
        # Assert
        assert r.parsed == {"a": 1}

    def test_bare_json_still_parsed_correctly(self):
        # Arrange -- regression: bare JSON must still work after the fix
        bare = '{"a": 1}'
        outer = self._make_outer(bare)
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(outer)):
            r = run_max(prompt="test", timeout_s=60)
        # Assert
        assert r.parsed == {"a": 1}

    def test_fenced_array_parsed_correctly(self):
        # Arrange
        fenced = '```json\n[1, 2]\n```'
        outer = self._make_outer(fenced)
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(outer)):
            r = run_max(prompt="test", timeout_s=60)
        # Assert
        assert r.parsed == [1, 2]

    def test_invalid_json_inside_fences_gives_none(self):
        # Arrange -- Claude returns fenced text that is not valid JSON
        fenced = '```json\nnot valid json at all\n```'
        outer = self._make_outer(fenced)
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(outer)):
            r = run_max(prompt="test", timeout_s=60)
        # Assert -- graceful: parsed is None, no exception raised
        assert r.parsed is None

    def test_raw_text_preserved_as_returned_by_claude(self):
        # Arrange -- raw_text must stay as Claude returned it (fences intact)
        fenced = '```json\n{"a": 1}\n```'
        outer = self._make_outer(fenced)
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(outer)):
            r = run_max(prompt="test", timeout_s=60)
        # Assert -- raw_text unchanged; only parsed benefits from stripping
        assert r.raw_text == fenced


# ---------------------------------------------------------------------------
# extended_thinking_budget kwarg tests
# ---------------------------------------------------------------------------

def test_extended_thinking_budget_passes_thinking_flag():
    fake_completed = _fake_completed(json.dumps({
        "result": '{"ok": true}',
        "total_cost_usd": 0.01,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }))
    with patch("brief.claude.max_client.subprocess.run", return_value=fake_completed) as mock_run:
        run_max(prompt="hi", extended_thinking_budget=12000)
    args = mock_run.call_args.args[0]
    assert "--thinking-budget" in args
    idx = args.index("--thinking-budget")
    assert args[idx + 1] == "12000"


def test_extended_thinking_budget_default_omits_flag():
    fake_completed = _fake_completed(json.dumps({
        "result": "{}",
        "total_cost_usd": 0.0,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }))
    with patch("brief.claude.max_client.subprocess.run", return_value=fake_completed) as mock_run:
        run_max(prompt="hi")
    args = mock_run.call_args.args[0]
    assert "--thinking-budget" not in args
