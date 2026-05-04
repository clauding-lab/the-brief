"""Thin CLI entrypoint for the Brief pipeline.

Usage (V6 publish — writes to Supabase):
  python -m brief.cli run --publish [--dry-run] [--today=YYYY-MM-DD]

Exit codes:
  0 ok                    — editor + subeditor passed, brief published to Supabase
  1 error                 — pipeline raised; stack to stderr
  3 dry-run-ok            — --dry-run requested, no Supabase write
  4 publish-failed        — V6 subeditor verdict=fail or Supabase write failed
"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback
from datetime import date

from brief.pipeline import PipelineConfig, gather


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="brief", description="The Brief pipeline CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Run the pipeline and publish to Supabase")
    r.add_argument("--publish", action="store_true",
                   help="(V6) Publish to Supabase via 2-call editor+subeditor flow.")
    r.add_argument("--dry-run", action="store_true",
                   help="Run the pipeline but do not write to Supabase")
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

    print("--publish is required (V5 HTML path has been removed)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
