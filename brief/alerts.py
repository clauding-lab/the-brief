"""Best-effort Discord ops alerts.

One tiny surface: `send_discord_alert(message)` POSTs to the webhook in
DISCORD_ALERT_WEBHOOK_URL (falling back to DISCORD_PREVIEW_WEBHOOK_URL, so alerts
land in the preview channel when no dedicated alerts channel is configured yet).

Contract: NEVER raises. A broken alert path must not compound the failure it is
reporting. Returns True only when Discord accepted the POST (2xx).

The systemd-level counterpart is deploy/brief_alert.sh (OnFailure= hard-failure
pings); this module covers in-process conditions where the unit still exits 0 —
e.g. a successful publish whose subscriber email delivered to nobody (item 5d).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_TIMEOUT_S = 10
# Discord caps message content at 2000 chars; stay under with margin.
_MAX_CONTENT = 1990
# Discord's edge returns 403 Forbidden to urllib's default "Python-urllib/3.x"
# User-Agent. Observed in production 2026-08-23, when the prose-number gate's
# grouped alert became the first real call this module ever made and 403'd —
# the fail-loud path had been dead since it shipped. The same bug bit the
# econdelta OnFailure alerts on exonhost in Aug 2026 (their notifier.py avoids
# it only because `requests` sets a UA for you). Any non-urllib UA satisfies it.
_USER_AGENT = "the-brief-alerts/1.0 (+https://thebrief.clauding-lab.com)"


def send_discord_alert(message: str) -> bool:
    """POST `message` to the ops Discord webhook. Best-effort, never raises."""
    url = (
        os.environ.get("DISCORD_ALERT_WEBHOOK_URL", "").strip()
        or os.environ.get("DISCORD_PREVIEW_WEBHOOK_URL", "").strip()
    )
    if not url:
        logger.warning(
            "alerts: no DISCORD_ALERT_WEBHOOK_URL / DISCORD_PREVIEW_WEBHOOK_URL set — "
            "alert not sent: %s",
            message[:200],
        )
        return False

    payload = json.dumps({"content": message[:_MAX_CONTENT]}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            ok = 200 <= resp.status < 300
            if not ok:
                logger.warning("alerts: Discord webhook returned HTTP %s", resp.status)
            return ok
    except Exception as exc:  # noqa: BLE001 — alert path must never raise
        logger.warning("alerts: Discord alert failed: %s", exc)
        return False
