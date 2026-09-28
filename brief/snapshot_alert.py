"""One operator alert when a run proceeds without a usable EconDelta snapshot.

Owner decision (e), 26 Sep 2026: a missing or broken `latest.json` does not stop the
08:00 BDT publish — the brief is built from saved history and readiness reports it as
degraded — but an operator must hear about it the same morning. The exit code stays 0,
so the systemd OnFailure alert never fires for it; this module is the in-process alert.
A snapshot that loads but is not a current capture (stale, earlier-day, older than the one
an earlier live run read past readiness, or no capture time) is still
read by the builders, so its alert names that snapshot as the source, not saved history.

Contract:
- exactly one call per run, made by `brief.cli` after readiness and only when the run is
  NOT held (a hold exits 4 and the OnFailure unit already alerts with the log tail);
- the message names only a fixed cause category — the file path and the decoder/OS
  error text stay in the service log, never in Discord;
- never raises and never blocks the publish: a transport failure is logged and dropped;
- suppressed by the BRIEF_DRY_RUN operator pause, like every in-process warning send.
"""
from __future__ import annotations

import logging

from brief.publication_identity import environment_paused

logger = logging.getLogger(__name__)

# Keys: brief.econdelta.UNAVAILABLE_CAUSES plus readiness's capture-age problems.
_CAUSE_TEXT: dict[str, str] = {
    "missing": "latest.json is not there",
    "truncated": "latest.json ends before its JSON is complete",
    "unparseable": "latest.json is not valid JSON",
    "unreadable": "latest.json could not be opened",
    "wrong shape": "latest.json is not a complete EconDelta snapshot",
    "stale capture": "figures taken from it are as old as that capture, not today's",
    "earlier-day capture": "figures taken from it are from that earlier capture, not today's",
    "capture time unknown": "figures taken from it may not be current",
    "capture went backwards": ("figures taken from it are older than ones an earlier run already read "
                               "past readiness"),
}
_UNCLASSIFIED = "unavailable"
# Causes where the snapshot loaded and IS read: its figures reach today's cards, so the alert
# names that snapshot as the source instead of claiming a build from saved history.
_READ_BUT_NOT_CURRENT: dict[str, str] = {
    "stale capture": "an EconDelta snapshot captured more than one day ago",
    "earlier-day capture": "an EconDelta snapshot captured on an earlier Bangladesh day",
    "capture time unknown": "an EconDelta snapshot whose capture time is unknown",
    "capture went backwards": ("an EconDelta snapshot older than the one an earlier run already read "
                               "past readiness"),
}
_WHERE_TO_LOOK = ("Check the ExonVPS to Hetzner latest.json sync and EconDelta's aggregate. "
                  "Details: the 'Publication readiness' line in logs/brief-systemd.log.")


def alert_snapshot_problem(problem: str, *, dry_run: bool) -> bool:
    """Send the one snapshot alert for this run. Returns True only if Discord accepted it."""
    cause = problem if problem in _CAUSE_TEXT else _UNCLASSIFIED
    try:
        if environment_paused():
            logger.info("snapshot alert: suppressed by publication pause; cause: %s", cause)
            return False
        from brief.alerts import send_discord_alert
        delivered = send_discord_alert(_message(cause, dry_run=dry_run))
    except Exception as exc:  # noqa: BLE001 — the alert path must never stop the publish
        # Type name only: exception text can carry the webhook URL.
        logger.warning("snapshot alert: send failed (%s); cause: %s", type(exc).__name__, cause)
        return False
    if delivered:
        logger.info("snapshot alert: sent; cause: %s", cause)
    else:
        logger.warning("snapshot alert: not delivered; cause: %s", cause)
    return delivered


def _message(cause: str, *, dry_run: bool) -> str:
    run = ("The Brief dry run (nothing will be published) is building" if dry_run
           else "The Brief is publishing")
    detail = _CAUSE_TEXT.get(cause, "the snapshot could not be used")
    detail = f"{detail[0].upper()}{detail[1:]}."
    old_source = _READ_BUT_NOT_CURRENT.get(cause)
    if old_source is not None:
        return f"ALERT: {run} from {old_source} (degraded) — cause: {cause}. {detail} {_WHERE_TO_LOOK}"
    return (
        f"ALERT: {run} from saved history (degraded) because the EconDelta snapshot "
        f"could not be used — cause: {cause}. {detail} "
        f"Today's edition is built without a current snapshot. {_WHERE_TO_LOOK}"
    )
