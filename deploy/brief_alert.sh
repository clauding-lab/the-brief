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
#   - brief.service writes its application traceback to brief-systemd.log;
#     other allowed units use the journal (best-effort without journal access).

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

# Unit names and log sources are fixed; never use arbitrary input as a path or
# journalctl option. Keep the tail bounded before passing it to Python.
case "$FAILED_UNIT" in
  brief.service)
    LOG_SOURCE="application log"
    LOG_TAIL="$(tail -c 1500 /home/adnan/the-brief/logs/brief-systemd.log 2>/dev/null || true)"
    ;;
  brief-export.service)
    LOG_SOURCE="journal"
    LOG_TAIL="$(journalctl --unit=brief-export.service -n 15 --no-pager -o cat 2>/dev/null | tail -c 1500 || true)"
    ;;
  chess-prodigy-prune.service)
    LOG_SOURCE="journal"
    LOG_TAIL="$(journalctl --unit=chess-prodigy-prune.service -n 15 --no-pager -o cat 2>/dev/null | tail -c 1500 || true)"
    ;;
  *)
    FAILED_UNIT="unknown-unit"
    LOG_SOURCE="none"
    LOG_TAIL=""
    ;;
esac

# Build the JSON payload safely (Discord caps content at 2000 chars).
PAYLOAD="$(FAILED_UNIT="$FAILED_UNIT" HOST="$HOST" WHEN="$WHEN" LOG_TAIL="$LOG_TAIL" LOG_SOURCE="$LOG_SOURCE" python3 - <<'PY'
import json, os, re

unit = os.environ.get("FAILED_UNIT", "unknown-unit")
host = os.environ.get("HOST", "unknown-host")
when = os.environ.get("WHEN", "")
tail = (os.environ.get("LOG_TAIL") or "").strip()
source = os.environ.get("LOG_SOURCE", "none")

def redact(value):
    value = re.sub(r"https?://\S*(?:webhooks?|hooks)/\S+", "[webhook redacted]", value, flags=re.I)
    value = re.sub(r"(?im)^.*(?:authorization|api[-_]?key|password|secret|token|webhook_url)\s*[:=].*$", "[credential redacted]", value)
    value = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[email redacted]", value)
    return value

lines = [
    f"ALERT: `{unit}` FAILED on {host} at {when}.",
    ("Inspect: `/home/adnan/the-brief/logs/brief-systemd.log`"
     if source == "application log" else f"Source: {source}"),
]
if tail:
    lines.append("```\n" + redact(tail) + "\n```")

content = "\n".join(lines)
print(json.dumps({"content": content[:1990]}))
PY
)" || {
  echo "brief_alert: payload build failed" >&2
  exit 0
}

HTTP_CODE="$(curl -sS -o /dev/null -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -A 'the-brief-alerts/1.0 (+https://thebrief.clauding-lab.com)' \
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
