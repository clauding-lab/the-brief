"""run_report.json writer.

Aggregates per-call status + cost into a single report blob. Consumed by
brief.cli (writes the file) and brief.notify (summarises for Discord).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brief.cadence import now_bdt
from brief.pipeline import RunResult

SCHEMA_VERSION = 1
_DEGRADED_FRESHNESS = {"stale", "unavailable", "pending"}


def build_run_report(rr: RunResult, *, shadow: bool) -> dict[str, Any]:
    call_reports: list[dict[str, Any]] = []
    total_cost = 0.0
    for cr in rr.call_reports:
        entry = dict(cr)
        entry.setdefault("cost_usd", 0.0)
        entry.setdefault("duration_s", 0.0)
        total_cost += float(entry["cost_usd"] or 0.0)
        call_reports.append(entry)

    degraded_sections = [
        getattr(s, "id", "?") for s in rr.sections
        if getattr(s, "freshness", "fresh") in _DEGRADED_FRESHNESS
    ]

    any_call_bad = any(cr["status"] != "ok" for cr in call_reports)
    status = "degraded" if (any_call_bad or degraded_sections) else "ok"

    now = now_bdt()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "today": now.date().isoformat(),
        "shadow": shadow,
        "status": status,
        "duration_s": 0.0,  # filled in by caller if wanted; CLI wraps run() for timing
        "call_reports": call_reports,
        "total_cost_usd": round(total_cost, 4),
        "degraded_sections": degraded_sections,
        "builder_failures": [],  # populated once builders surface structured errors
        "git_push": {"branch": None, "sha": None, "pushed": False},
    }


def write_run_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n",
                    encoding="utf-8")
