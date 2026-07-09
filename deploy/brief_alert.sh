#!/usr/bin/env bash
# Post a Discord alert when a brief-* systemd unit hard-fails.
#
# Invoked by brief-alert@.service with the FAILED unit's name as $1
# (OnFailure=brief-alert@%n.service on the publisher units).
#
# Env (from /etc/brief.env via the alert unit's EnvironmentFile):
#   DISCORD_ALERT_WEBHOOK_URL    — preferred alert channel webhook
#   DISCORD_PREVIEW_WEBHOOK_URL  — fallback (the preview channel) if no alert URL
#
# Design notes:
#   - Best-effort everywhere: a broken alert path must never mask or compound the
#     original failure. Missing webhook → log to stderr, exit 0.
#   - JSON built with python3 (guaranteed on the box — the pipeline runs on it;
#     jq is NOT installed on Hetzner clauding-lab).
#   - journalctl excerpt is best-effort: reading a system unit's journal needs
#     systemd-journal group membership (see deploy/README.md); without it the
#     alert still fires, just without the log tail.

set -u

FAILED_UNIT="${1:-unknown-unit}"
WEBHOOK="${DISCORD_ALERT_WEBHOOK_URL:-${DISCORD_PREVIEW_WEBHOOK_URL:-}}"

if [[ -z "$WEBHOOK" ]]; then
  echo "brief_alert: no DISCORD_ALERT_WEBHOOK_URL / DISCORD_PREVIEW_WEBHOOK_URL set — cannot alert" >&2
  exit 0
fi

HOST="$(hostname 2>/dev/null || echo unknown-host)"
# BDT (UTC+6) timestamp — house convention: times for humans are BDT-labelled.
WHEN="$(TZ=Asia/Dhaka date '+%Y-%m-%d %H:%M BDT' 2>/dev/null || date -u '+%Y-%m-%d %H:%MZ')"

# Last journal lines of the failed unit (best-effort; may be empty without perms).
LOG_TAIL="$(journalctl -u "$FAILED_UNIT" -n 15 --no-pager -o cat 2>/dev/null | tail -c 1200 || true)"

# Build the JSON payload safely (Discord caps content at 2000 chars).
PAYLOAD="$(FAILED_UNIT="$FAILED_UNIT" HOST="$HOST" WHEN="$WHEN" LOG_TAIL="$LOG_TAIL" python3 - <<'PY'
import json, os

unit = os.environ.get("FAILED_UNIT", "unknown-unit")
host = os.environ.get("HOST", "unknown-host")
when = os.environ.get("WHEN", "")
tail = (os.environ.get("LOG_TAIL") or "").strip()

lines = [
    f"ALERT: `{unit}` FAILED on {host} at {when}.",
    f"Inspect: `journalctl -u {unit} -n 100 --no-pager`",
]
if tail:
    lines.append("```\n" + tail + "\n```")

content = "\n".join(lines)
print(json.dumps({"content": content[:1990]}))
PY
)" || {
  echo "brief_alert: payload build failed" >&2
  exit 0
}

HTTP_CODE="$(curl -sS -o /dev/null -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -X POST --data "$PAYLOAD" \
  --max-time 15 \
  "$WEBHOOK" 2>/dev/null || echo 000)"

if [[ "$HTTP_CODE" =~ ^2 ]]; then
  echo "brief_alert: Discord alert sent for $FAILED_UNIT (HTTP $HTTP_CODE)"
else
  echo "brief_alert: Discord webhook returned HTTP $HTTP_CODE for $FAILED_UNIT" >&2
fi

# Never propagate failure — the alert is best-effort by design.
exit 0
