"""Stub for Task 5.2 tests. Full implementation lands in Task 5.3."""
from __future__ import annotations

from pathlib import Path


def build_run_report(rr, *, shadow: bool = False) -> dict:
    total = sum(c.get("cost_usd", 0.0) for c in (rr.call_reports or []))
    has_error = any(c.get("status") == "error" for c in (rr.call_reports or []))
    return {"status": "degraded" if has_error else "ok", "total_cost_usd": total, "shadow": shadow}


def write_run_report(path: Path, report: dict) -> None:
    import json
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
