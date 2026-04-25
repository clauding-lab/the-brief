"""Thin CLI entrypoint for the Brief V4 pipeline.

Usage:
  python -m brief.cli run --artifacts-dir=PATH [--shadow | --push-main]
                         [--email] [--dry-run] [--today=YYYY-MM-DD]

Exit codes:
  0 ok                    — all Claude calls succeeded, artifacts written
  1 error                 — pipeline raised; stack to stderr
  2 degraded              — pipeline completed but ≥1 Claude call failed
  3 dry-run-ok            — --dry-run requested, no artifacts written
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import date
from pathlib import Path

from brief.email_send import send_email
from brief.gitops import push_artifacts
from brief.notify import build_payload, post_discord
from brief.pipeline import PipelineConfig, RunResult, run
from brief.report import build_run_report, write_run_report


def run_with_mode(cfg: PipelineConfig, *, shadow: bool) -> RunResult:
    """Thin indirection to let tests stub the whole pipeline call."""
    return run(cfg)


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="brief", description="The Brief V4 pipeline CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Run the pipeline and write artifacts")
    r.add_argument("--artifacts-dir", required=True, type=Path)
    group = r.add_mutually_exclusive_group()
    group.add_argument("--shadow", action="store_true",
                       help="Shadow mode: push to shadow branch, do not email")
    group.add_argument("--push-main", action="store_true",
                       help="Post-cutover: push artifacts to main")
    r.add_argument("--email", action="store_true",
                   help="Send the email digest via Brevo (requires BREVO_API_KEY)")
    r.add_argument("--dry-run", action="store_true",
                   help="Run the pipeline but do not write artifacts")
    r.add_argument("--today", default=None,
                   help="Override today's date (YYYY-MM-DD); default: system date")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse(argv or sys.argv[1:])
    today = date.fromisoformat(ns.today) if ns.today else date.today()
    cfg = PipelineConfig(today=today)

    started = time.monotonic()
    try:
        rr = run_with_mode(cfg, shadow=ns.shadow)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1
    elapsed = time.monotonic() - started

    if ns.dry_run:
        return 3

    ns.artifacts_dir.mkdir(parents=True, exist_ok=True)
    (ns.artifacts_dir / "index.html").write_text(rr.html, encoding="utf-8")
    (ns.artifacts_dir / "email.txt").write_text(rr.email_text, encoding="utf-8")

    report = build_run_report(rr, shadow=ns.shadow)
    report["duration_s"] = elapsed

    if ns.push_main or ns.shadow:
        branch = "main" if ns.push_main else f"shadow/{today.isoformat()}"
        gp = push_artifacts(
            repo_dir=Path.cwd(),
            branch=branch,
            artifacts_dir=ns.artifacts_dir,
            message=f"Brief {today.isoformat()} [{'main' if ns.push_main else 'shadow'}]",
        )
        report["git_push"] = gp
        write_run_report(ns.artifacts_dir / "run_report.json", report)
    else:
        write_run_report(ns.artifacts_dir / "run_report.json", report)

    if ns.email and os.environ.get("BREVO_API_KEY") and os.environ.get("FROM_EMAIL"):
        send_email(
            from_email=os.environ["FROM_EMAIL"],
            api_key=os.environ["BREVO_API_KEY"],
            subject=f"The Brief · {today.isoformat()}",
            html=rr.html,
            text=rr.email_text,
        )

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook:
        repo = os.environ.get("BRIEF_REPO_SLUG", "clauding-lab/the-brief")
        lead = rr.todays_call.text if rr.todays_call else None
        post_discord(webhook, payload=build_payload(report, lead_headline=lead,
                                                    repo_slug=repo))

    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
