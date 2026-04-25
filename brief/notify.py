"""Discord webhook notifier for the Brief pipeline.

Intentionally swallows all network errors — Discord flakiness must never fail
a pipeline run. Returns the HTTP status code (or 0 on socket error) for logging.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen


def build_payload(
    report: dict[str, Any],
    *,
    lead_headline: str | None,
    repo_slug: str,
) -> dict[str, str]:
    status = report["status"]
    icon = {"ok": "✅", "degraded": "⚠️", "error": "❌"}.get(status, "❔")
    today = report["today"]
    duration = int(round(report.get("duration_s") or 0.0))
    cost = report.get("total_cost_usd") or 0.0
    lines = [f"The Brief · {today} · {icon} {status}",
             f"duration {duration}s · cost ${cost:.2f}"]
    if report.get("degraded_sections"):
        lines.append(f"degraded: {', '.join(report['degraded_sections'])}")
    if lead_headline:
        lines.append(f'Lead: "{lead_headline}"')
    gp = report.get("git_push") or {}
    if gp.get("pushed") and gp.get("branch"):
        lines.append(f"https://github.com/{repo_slug}/tree/{gp['branch']}")
    return {"content": "\n".join(lines)}


def post_discord(webhook_url: str, *, payload: dict[str, Any]) -> int:
    body = json.dumps(payload).encode("utf-8")
    req = Request(webhook_url, data=body,
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            return getattr(resp, "status", 0)
    except Exception:
        return 0
