from __future__ import annotations

import json
from pathlib import Path

import pytest

from brief.pipeline import RunResult
from brief.report import build_run_report, write_run_report


def _rr(call_reports: list[dict], sections=None) -> RunResult:
    return RunResult(
        sections=sections or [],
        html="", claude_outputs={},
        call_reports=call_reports, email_text="",
    )


def test_ok_when_all_calls_ok():
    rr = _rr([
        {"name": "headlines_curation", "status": "ok", "reason": None,
         "cost_usd": 0.12, "duration_s": 2.0},
        {"name": "exec_signals", "status": "ok", "reason": None,
         "cost_usd": 0.40, "duration_s": 6.0},
    ])
    r = build_run_report(rr, shadow=False)
    assert r["status"] == "ok"
    assert r["total_cost_usd"] == pytest.approx(0.52)
    assert r["degraded_sections"] == []


def test_degraded_when_one_call_invalid():
    rr = _rr([
        {"name": "headlines_curation", "status": "invalid", "reason": "missing key",
         "cost_usd": 0.10, "duration_s": 1.0},
        {"name": "exec_signals", "status": "ok", "reason": None,
         "cost_usd": 0.40, "duration_s": 6.0},
    ])
    r = build_run_report(rr, shadow=False)
    assert r["status"] == "degraded"


def test_degraded_when_call_error():
    rr = _rr([
        {"name": "headlines_curation", "status": "error", "reason": "timeout",
         "cost_usd": 0.0, "duration_s": 30.0},
    ])
    r = build_run_report(rr, shadow=False)
    assert r["status"] == "degraded"


def test_total_cost_handles_missing_cost_usd():
    rr = _rr([
        {"name": "headlines_curation", "status": "ok", "reason": None},  # no cost_usd
    ])
    r = build_run_report(rr, shadow=False)
    assert r["total_cost_usd"] == 0.0


def test_degraded_sections_collected_from_section_freshness():
    class FakeSection:
        def __init__(self, sid, freshness):
            self.id = sid
            self.freshness = freshness

    rr = _rr(
        [{"name": "x", "status": "ok", "cost_usd": 0.1, "duration_s": 1.0}],
        sections=[FakeSection("bb", "fresh"),
                  FakeSection("dse", "unavailable"),
                  FakeSection("fx", "stale")],
    )
    r = build_run_report(rr, shadow=False)
    assert r["degraded_sections"] == ["dse", "fx"]
    assert r["status"] == "degraded"  # unavailable/stale count as degraded


def test_shadow_flag_is_threaded():
    rr = _rr([{"name": "x", "status": "ok", "cost_usd": 0.0, "duration_s": 0.0}])
    r = build_run_report(rr, shadow=True)
    assert r["shadow"] is True


def test_write_run_report_roundtrips(tmp_path: Path):
    rr = _rr([{"name": "x", "status": "ok", "cost_usd": 1.5, "duration_s": 1.0}])
    report = build_run_report(rr, shadow=False)
    write_run_report(tmp_path / "run_report.json", report)
    loaded = json.loads((tmp_path / "run_report.json").read_text())
    assert loaded["total_cost_usd"] == 1.5
    assert loaded["schema_version"] == 1


def test_schema_version_is_pinned():
    rr = _rr([{"name": "x", "status": "ok", "cost_usd": 0.0, "duration_s": 0.0}])
    r = build_run_report(rr, shadow=False)
    assert r["schema_version"] == 1
