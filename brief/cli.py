"""Thin CLI entrypoint for the Brief pipeline.

Usage (V5 HTML render — legacy, retiring in PR #29):
  python -m brief.cli run --artifacts-dir=PATH [--shadow | --push-main]
                         [--email] [--dry-run] [--today=YYYY-MM-DD]

Usage (V6 publish — writes to Supabase):
  python -m brief.cli run --publish [--dry-run] [--today=YYYY-MM-DD]

Exit codes:
  0 ok                    — all Claude calls succeeded, artifacts written/published
  1 error                 — pipeline raised; stack to stderr
  2 degraded              — V5 pipeline completed but ≥1 Claude call failed
  3 dry-run-ok            — --dry-run requested, no artifacts written
  4 publish-failed        — V6 subeditor verdict=fail or Supabase write failed
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import traceback
from datetime import date
from pathlib import Path

from brief.email_send import send_email
from brief.gitops import push_artifacts
from brief.notify import build_payload, post_discord
from brief.pipeline import PipelineConfig, RunResult, gather, run
from brief.report import build_run_report, write_run_report


def run_with_mode(cfg: PipelineConfig, *, shadow: bool) -> RunResult:
    """Thin indirection to let tests stub the whole pipeline call."""
    return run(cfg)


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="brief", description="The Brief V4 pipeline CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Run the pipeline and write artifacts or publish")
    r.add_argument("--artifacts-dir", default=None, type=Path,
                   help="(V5) Output directory for HTML/email artifacts. Required unless --publish.")
    group = r.add_mutually_exclusive_group()
    group.add_argument("--shadow", action="store_true",
                       help="(V5) Shadow mode: push HTML to shadow branch, do not email")
    group.add_argument("--push-main", action="store_true",
                       help="(V5) Post-cutover: push artifacts to main")
    group.add_argument("--publish", action="store_true",
                       help="(V6) Publish to Supabase via 2-call editor+subeditor flow. "
                            "Skips HTML render and gitops entirely.")
    r.add_argument("--email", action="store_true",
                   help="Send the email digest via Brevo (requires BREVO_API_KEY)")
    r.add_argument("--dry-run", action="store_true",
                   help="Run the pipeline but do not write artifacts")
    r.add_argument("--today", default=None,
                   help="Override today's date (YYYY-MM-DD); default: system date")
    return p.parse_args(argv)


def _run_v6_publish(cfg: PipelineConfig, today: date, dry_run: bool) -> int:
    """V6 publish path: gather → editor_v6 → subeditor_v6 → Supabase."""
    from brief.headlines import scrape_all
    from brief.pipeline_v6 import V6PublishError, run_publish

    log = logging.getLogger("brief.cli")
    try:
        sections = gather(cfg)
        scraped = [
            {"title": h.title, "url": h.url, "source": h.source,
             "published": h.published.isoformat() if h.published else None}
            for h in scrape_all()
        ] if cfg.enable_headlines else []
        brief_id = run_publish(sections, today, scraped_headlines=scraped, dry_run=dry_run)
    except V6PublishError as e:
        log.error("V6 publish failed: %s", e)
        traceback.print_exc(file=sys.stderr)
        return 4
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1

    if dry_run:
        log.info("V6 dry-run: editor + subeditor passed, no Supabase write")
        return 3
    log.info("V6 publish ok: brief_id=%s", brief_id)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ns = _parse(argv or sys.argv[1:])
    today = date.fromisoformat(ns.today) if ns.today else date.today()
    cfg = PipelineConfig(today=today)

    if ns.publish:
        return _run_v6_publish(cfg, today, dry_run=ns.dry_run)

    if ns.artifacts_dir is None:
        print("--artifacts-dir is required unless --publish is set", file=sys.stderr)
        return 1

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

    # Write run_report.json BEFORE push_artifacts so the file exists when
    # gitops copies/git-adds it onto the shadow (or main) branch. The local
    # artifact is overwritten below with the git_push field once we know it.
    write_run_report(ns.artifacts_dir / "run_report.json", report)

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
