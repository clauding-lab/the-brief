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
