"""Thin CLI entrypoint for the Brief pipeline.

Usage (V6 publish — writes to Supabase):
  python -m brief.cli run --publish [--dry-run] [--today=YYYY-MM-DD] [--no-notify]

Exit codes:
  0 ok                    — editor + subeditor passed, brief published to Supabase
                            (notifier failures are logged but do NOT change exit code:
                            the Supabase brief is the canonical artifact; the email
                            is a best-effort amplifier.)
  1 error                 — pipeline raised; stack to stderr
  3 dry-run-ok            — --dry-run or BRIEF_DRY_RUN pause, no Supabase write
  4 publish-failed        — validation/identity hold, publication busy, or write failed
"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback
from contextlib import nullcontext
from datetime import date

from brief.cadence import now_bdt
from brief.capture_mark import read_capture_mark, record_capture_mark
from brief.pipeline import PipelineConfig, gather
from brief.publication_identity import (
    PublicationBusyError, environment_paused, publication_lock, resolve_identity,
)
from brief.snapshot_alert import alert_snapshot_problem


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="brief", description="The Brief pipeline CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Run the pipeline and publish to Supabase")
    r.add_argument("--publish", action="store_true",
                   help="(V6) Publish to Supabase via 2-call editor+subeditor flow.")
    r.add_argument("--dry-run", action="store_true",
                   help="Run the pipeline but do not write to Supabase")
    r.add_argument("--today", default=None,
                   help="Run date (YYYY-MM-DD); live runs require today in BDT. "
                        "Use --dry-run for historical replay.")
    r.add_argument("--no-notify", action="store_true",
                   help="Skip the subscriber email notifier after a successful publish")
    r.add_argument("--write-fixture", default=None, metavar="PATH",
                   help="When used with --dry-run, write the final brief JSON to PATH "
                        "(for SPA preview at /preview?fixture=<name>)")
    r.add_argument("--preview-notify", action="store_true",
                   help="After --write-fixture writes the JSON, ping Discord webhook "
                        "(DISCORD_PREVIEW_WEBHOOK_URL) and email (PREVIEW_EMAIL_RECIPIENT) "
                        "with the preview URL. Each channel is best-effort; failures "
                        "are logged but do not change exit code.")
    return p.parse_args(argv)


def _run_v6_publish_unlocked(
    cfg: PipelineConfig,
    today: date,
    dry_run: bool,
    notify_enabled: bool,
    write_fixture_path: str | None = None,
    preview_notify_enabled: bool = False,
) -> int:
    """V6 publish path: gather → editor_v6 → subeditor_v6 → Supabase."""
    from brief.headlines import scrape_all
    from brief.pipeline_v6 import V6PublishError, run_publish

    from brief.v6_publisher import PublishError, fetch_max_issue_no, fetch_same_day_briefs

    log = logging.getLogger("brief.cli")

    try:
        same_day_rows = fetch_same_day_briefs(today)
        try:
            identity = resolve_identity(
                today, same_day_rows=same_day_rows,
                max_issue_no=fetch_max_issue_no(),
            )
        except ValueError as exc:
            raise V6PublishError(str(exc)) from exc
        # No delivery ledger exists yet. Even a draft may be a failed replacement
        # of an emailed issue: suppress ALL same-day retries conservatively.
        if same_day_rows:
            notify_enabled = False
            log.info(
                "Same-day replacement: subscriber resend suppressed "
                "(no supported resend workflow)"
            )
        sections = gather(cfg)
        if hasattr(sections, "snapshot"):
            from brief.readiness import assess
            now = now_bdt()
            last_capture = read_capture_mark(now)
            readiness = assess(sections.snapshot,
                persisted_rows=[m for section in sections for m in section.metrics],
                now=now, last_capture=last_capture)
            log.info("Publication readiness: %s; %s", readiness.state, "; ".join(readiness.reasons))
            if readiness.notes:  # healthy official lag (fix 4): informational, never degrading
                log.info("Readiness notes (healthy, not degrading): %s", "; ".join(readiness.notes))
            if readiness.state == "hold":
                raise V6PublishError("readiness hold: " + "; ".join(readiness.reasons))
            if not dry_run:  # only a live, non-held run's capture becomes the one to beat
                record_capture_mark(sections.snapshot.updated_at, previous=last_capture)
            if readiness.snapshot_problem is not None:
                # Owner decision (e): publish degraded AND tell an operator, once per run.
                alert_snapshot_problem(readiness.snapshot_problem, dry_run=dry_run)
        scraped = [
            {"title": h.title, "url": h.url, "source": h.source,
             "published": h.published.isoformat() if h.published else None}
            for h in scrape_all()
        ] if cfg.enable_headlines else []
        brief_id = run_publish(
            sections, today,
            expected_identity=identity,
            scraped_headlines=scraped,
            dry_run=dry_run,
            write_fixture_path=write_fixture_path,
        )
    except (V6PublishError, PublishError) as e:
        log.error("V6 publish failed: %s", e)
        traceback.print_exc(file=sys.stderr)
        return 4
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1

    if dry_run:
        log.info("V6 dry-run: editor + subeditor passed, no Supabase write")
        if preview_notify_enabled and write_fixture_path:
            try:
                from brief.preview_notify import notify_preview
                res = notify_preview(write_fixture_path)
                log.info(
                    "preview_notify: discord_ok=%s email_ok=%s url=%s",
                    res.discord_ok, res.email_ok, res.preview_url,
                )
            except Exception:
                log.exception("preview_notify: unexpected exception (dry-run remains successful)")
        return 3
    log.info("V6 publish ok: brief_id=%s", brief_id)

    if notify_enabled and brief_id:
        try:
            from brief.notifier import notify as _notify
            result = _notify(brief_id)
            log.info(
                "notifier: accepted=%d attempted=%d acceptance unconfirmed=%d skipped=%d message_id=%s error=%s",
                result.sent_count, result.attempted_count,
                result.failed_count, result.skipped_count, result.message_id, result.error,
            )
            # Brevo HTTP acceptance is not inbox delivery. A request timeout can
            # leave acceptance unknown, so these alerts never imply safe resend.
            # Auth/fetch failure is also an incident; an empty audience is not.
            # Keep exit 0 because the canonical edition is already published.
            no_confirmed_acceptance = result.sent_count == 0 and (
                result.attempted_count > 0
                or result.error not in (None, "no_subscribers")
            )
            retry_caution = "Timed-out attempts may already have been accepted; do not resend everyone."
            if no_confirmed_acceptance:
                log.error(
                    "notifier: NO CONFIRMED ACCEPTANCE — accepted=0 attempted=%d "
                    "acceptance unconfirmed=%d error=%s (publish itself succeeded). %s",
                    result.attempted_count, result.failed_count, result.error, retry_caution,
                )
                from brief.alerts import send_discord_alert
                send_discord_alert(
                    f"ALERT: The Brief published (brief_id={brief_id}) but the "
                    f"subscriber email has no confirmed provider acceptance — accepted=0 "
                    f"attempted={result.attempted_count} acceptance unconfirmed={result.failed_count} "
                    f"error={result.error}. {retry_caution} "
                    f"Inspect: journalctl -u brief.service -n 200 --no-pager"
                )
            elif result.failed_count > 0:
                # Keep the published edition and do not retry an already-mailed
                # audience. B5 owns the existing alert transport.
                incident = (
                    f"PARTIAL ACCEPTANCE — accepted={result.sent_count} "
                    f"attempted={result.attempted_count} acceptance unconfirmed={result.failed_count} "
                    f"error={result.error} (publish itself succeeded). {retry_caution}"
                )
                log.error("notifier: %s", incident)
                from brief.alerts import send_discord_alert
                send_discord_alert(
                    f"ALERT: The Brief published (brief_id={brief_id}) but subscriber email had "
                    f"{incident}. Inspect: journalctl -u brief.service -n 200 --no-pager"
                )
        except Exception:
            # Last-resort fail-open: even an import error must not crash a successful
            # publish. A crash may occur after some sends, so acceptance is unknown.
            log.exception("notifier: unexpected exception (publish remains successful)")
            try:
                from brief.alerts import send_discord_alert
                send_discord_alert(
                    f"ALERT: The Brief published (brief_id={brief_id}) but the "
                    f"notifier CRASHED — provider acceptance may be unknown. "
                    f"Do not resend everyone. "
                    f"Inspect: journalctl -u brief.service -n 200 --no-pager"
                )
            except Exception:
                log.exception("alerts: send_discord_alert itself failed")

    return 0


def _run_v6_publish(
    cfg: PipelineConfig,
    today: date,
    dry_run: bool,
    notify_enabled: bool,
    write_fixture_path: str | None = None,
    preview_notify_enabled: bool = False,
) -> int:
    """The only live entry: hold the lock before reads until delivery finishes."""
    try:
        with nullcontext() if dry_run else publication_lock():
            return _run_v6_publish_unlocked(
                cfg, today, dry_run, notify_enabled,
                write_fixture_path, preview_notify_enabled,
            )
    except PublicationBusyError as exc:
        logging.getLogger("brief.cli").error("Publication held: %s", exc)
        return 4
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ns = _parse(argv or sys.argv[1:])

    try:
        paused = environment_paused()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    dry_run = ns.dry_run or paused
    preview_enabled = ns.preview_notify and not paused

    if ns.write_fixture and not dry_run:
        print("--write-fixture requires --dry-run; use both flags together", file=sys.stderr)
        return 1

    if preview_enabled and not ns.write_fixture:
        print("--preview-notify requires --write-fixture (nothing to point at otherwise)", file=sys.stderr)
        return 1

    current_day = now_bdt().date()
    try:
        today = date.fromisoformat(ns.today) if ns.today else current_day
    except ValueError:
        print("--today must be YYYY-MM-DD", file=sys.stderr)
        return 1
    if not dry_run and today != current_day:
        print("Live --today must match today's BDT date; use --dry-run for historical replay", file=sys.stderr)
        return 1
    cfg = PipelineConfig(today=today)

    if ns.publish:
        return _run_v6_publish(
            cfg, today,
            dry_run=dry_run,
            notify_enabled=not ns.no_notify and not dry_run,
            write_fixture_path=ns.write_fixture,
            preview_notify_enabled=preview_enabled,
        )

    print("--publish is required (V5 HTML path has been removed)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
