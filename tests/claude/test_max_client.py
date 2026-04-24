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
