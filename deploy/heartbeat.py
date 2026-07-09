#!/usr/bin/env python3
"""Off-box heartbeat for The Brief fleet (handoff item 5b).

Runs on ExonVPS (adnan-local@103.187.23.22) via cron at ~07:30 BDT daily —
deliberately OFF the Hetzner box that publishes, so a dead box can't kill its
own watchdog. Two checks, one Discord alert on breach:

  1. THE BRIEF PUBLISHED TODAY — today's `brief_date` (Asia/Dhaka calendar day,
     NOT UTC) is the latest `status=published` row in Supabase `briefs`.
     Publishes are 7 days/week since PR #116 — no Saturday exclusion.
  2. ECONDELTA SENTINEL ALIVE — a `run_logs` row with source='freshness_sentinel'
     and status='ok' finished within the last ~26 h (its timer fires 13:30 BDT
     daily; 26 h covers one fire plus slack). One cron, two watchdogs.

Auth: Supabase ANON key — both tables are anon-readable (verified 2026-07-09:
`briefs` exposes brief_date/status to anon; `run_logs` has the "anon read runs"
SELECT policy). No service key ever leaves the Hetzner/env boundary for this.

Config: env vars SUPABASE_URL, SUPABASE_ANON_KEY, DISCORD_ALERT_WEBHOOK_URL —
read from the environment, else loaded from an env file (--env-file, default
/etc/brief-heartbeat.env; see deploy/brief-heartbeat.env.example).

Timezone: "today" is computed at UTC+6 (fixed offset — Bangladesh abolished DST
in 2009, so Asia/Dhaka is permanently +06:00; no tzdata dependency). The classic
trap: any run before 06:00 BDT has a UTC date of YESTERDAY, so a UTC-computed
"today" would demand a brief that doesn't exist yet. Tested explicitly.

Fail-loud + the last-turtle limitation, honestly: this is the TOP of the
watchdog chain — nothing watches the watchdog. If the heartbeat itself cannot
reach Supabase or Discord it prints to stderr and exits non-zero; cron's only
duty is the crontab line's `>> logfile 2>&1` redirect (cron mail is typically
discarded). A silently-broken heartbeat is only caught by a human noticing the
log went quiet. Something has to be allowed to be the last turtle.

Exit codes:
  0  both checks healthy
  1  breach detected, Discord alert delivered
  2  heartbeat failure — Supabase unreachable, or a breach/alert could not be
     delivered to Discord

Stdlib only. No new dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

# Bangladesh Standard Time — fixed UTC+6, no DST since 2009.
BDT = timezone(timedelta(hours=6), name="BDT")

DEFAULT_ENV_FILE = "/etc/brief-heartbeat.env"
DEFAULT_SENTINEL_MAX_AGE_HOURS = 26.0
_HTTP_TIMEOUT_S = 20
_DISCORD_MAX_CONTENT = 1990


class HeartbeatError(RuntimeError):
    """The heartbeat itself failed (Supabase/Discord unreachable) — exit 2."""


def _log(msg: str, *, err: bool = False) -> None:
    stamp = datetime.now(BDT).strftime("%Y-%m-%d %H:%M:%S BDT")
    print(f"{stamp} heartbeat: {msg}", file=sys.stderr if err else sys.stdout)


def load_env_file(path: str, environ: dict | None = None) -> None:
    """Load KEY=VALUE lines into the environment WITHOUT overriding existing vars.

    Missing file is fine (vars may already be exported). Comments/blank lines
    skipped; values may be quoted.
    """
    env = environ if environ is not None else os.environ
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in env:
            env[key] = value


def today_bdt(now_utc: datetime | None = None) -> date:
    """Today's calendar date in Bangladesh (UTC+6).

    THE trap this exists for: before 06:00 BDT the UTC date is still yesterday,
    so `datetime.now(timezone.utc).date()` would look for yesterday's brief.
    """
    now = now_utc if now_utc is not None else datetime.now(timezone.utc)
    return now.astimezone(BDT).date()


def _fetch_json(url: str, headers: dict[str, str]) -> tuple[int, object]:
    """GET url → (status, parsed_json). Raises HeartbeatError on network failure."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        raise HeartbeatError(f"GET {url} → HTTP {e.code}: {body}") from e
    except Exception as e:  # URLError, timeout, bad JSON …
        raise HeartbeatError(f"GET {url} failed: {e}") from e


def _anon_headers(anon_key: str) -> dict[str, str]:
    return {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json",
    }


def check_brief_published_today(
    *,
    supabase_url: str,
    anon_key: str,
    today: date,
    fetch=None,
) -> str | None:
    """Breach message if today's brief_date is NOT the latest published row; else None."""
    fetch = fetch if fetch is not None else _fetch_json  # late-bind so tests can patch
    url = (
        f"{supabase_url.rstrip('/')}/rest/v1/briefs"
        "?select=brief_date&status=eq.published&order=brief_date.desc&limit=1"
    )
    status, body = fetch(url, _anon_headers(anon_key))
    if status != 200 or not isinstance(body, list):
        raise HeartbeatError(f"briefs query → HTTP {status} (body type {type(body).__name__})")
    if not body:
        return "The Brief: NO published briefs found in Supabase at all"
    latest = str(body[0].get("brief_date", ""))
    if latest != today.isoformat():
        return (
            f"The Brief: today's issue ({today.isoformat()} BDT) is NOT published — "
            f"latest published brief_date is {latest or 'unknown'}"
        )
    return None


def check_sentinel_alive(
    *,
    supabase_url: str,
    anon_key: str,
    now_utc: datetime,
    max_age_hours: float = DEFAULT_SENTINEL_MAX_AGE_HOURS,
    fetch=None,
) -> str | None:
    """Breach message unless an ok freshness_sentinel run finished within max_age_hours."""
    fetch = fetch if fetch is not None else _fetch_json  # late-bind so tests can patch
    url = (
        f"{supabase_url.rstrip('/')}/rest/v1/run_logs"
        "?select=finished_at&source=eq.freshness_sentinel&status=eq.ok"
        "&order=finished_at.desc.nullslast&limit=1"
    )
    status, body = fetch(url, _anon_headers(anon_key))
    if status != 200 or not isinstance(body, list):
        raise HeartbeatError(f"run_logs query → HTTP {status} (body type {type(body).__name__})")
    if not body:
        return "EconDelta: no ok freshness_sentinel row in run_logs at all"
    raw = body[0].get("finished_at")
    if not raw:
        return "EconDelta: latest ok freshness_sentinel row has no finished_at"
    try:
        finished = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return f"EconDelta: unparseable freshness_sentinel finished_at: {raw!r}"
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=timezone.utc)
    age_h = (now_utc - finished).total_seconds() / 3600.0
    if age_h > max_age_hours:
        return (
            f"EconDelta: freshness_sentinel last ok {age_h:.1f}h ago "
            f"(limit {max_age_hours:.0f}h) — the scraper watchdog itself is dead"
        )
    return None


def send_discord_alert(webhook_url: str, message: str) -> bool:
    """POST to the Discord webhook. Returns True on 2xx; never raises."""
    payload = json.dumps({"content": message[:_DISCORD_MAX_CONTENT]}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
            return 200 <= resp.status < 300
    except Exception as e:  # noqa: BLE001 — reported via return value
        _log(f"Discord POST failed: {e}", err=True)
        return False


def run_checks(
    *,
    supabase_url: str,
    anon_key: str,
    now_utc: datetime,
    max_age_hours: float,
    fetch=None,
) -> list[str]:
    """Run both fleet checks; return the list of breach messages (empty = healthy)."""
    fetch = fetch if fetch is not None else _fetch_json  # late-bind so tests can patch
    breaches: list[str] = []
    b = check_brief_published_today(
        supabase_url=supabase_url, anon_key=anon_key,
        today=today_bdt(now_utc), fetch=fetch,
    )
    if b:
        breaches.append(b)
    s = check_sentinel_alive(
        supabase_url=supabase_url, anon_key=anon_key,
        now_utc=now_utc, max_age_hours=max_age_hours, fetch=fetch,
    )
    if s:
        breaches.append(s)
    return breaches


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="heartbeat", description="Off-box fleet heartbeat (The Brief + EconDelta sentinel)"
    )
    p.add_argument(
        "--env-file", default=DEFAULT_ENV_FILE,
        help=f"env file with SUPABASE_URL / SUPABASE_ANON_KEY / DISCORD_ALERT_WEBHOOK_URL "
             f"(default {DEFAULT_ENV_FILE}; already-exported vars win)",
    )
    p.add_argument(
        "--max-sentinel-age-hours", type=float, default=DEFAULT_SENTINEL_MAX_AGE_HOURS,
        help=f"freshness_sentinel staleness limit (default {DEFAULT_SENTINEL_MAX_AGE_HOURS:.0f})",
    )
    ns = p.parse_args(argv)

    load_env_file(ns.env_file)
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    webhook = os.environ.get("DISCORD_ALERT_WEBHOOK_URL", "").strip()
    if not supabase_url or not anon_key or not webhook:
        _log(
            "missing config — need SUPABASE_URL, SUPABASE_ANON_KEY, "
            f"DISCORD_ALERT_WEBHOOK_URL (env or {ns.env_file})",
            err=True,
        )
        return 2

    now_utc = datetime.now(timezone.utc)
    try:
        breaches = run_checks(
            supabase_url=supabase_url, anon_key=anon_key,
            now_utc=now_utc, max_age_hours=ns.max_sentinel_age_hours,
        )
    except HeartbeatError as e:
        _log(f"HEARTBEAT FAILURE (cannot check the fleet): {e}", err=True)
        # Best-effort self-report — Discord may still be reachable when Supabase isn't.
        send_discord_alert(
            webhook,
            f"HEARTBEAT FAILURE on ExonVPS: could not check the fleet — {e}",
        )
        return 2

    if not breaches:
        _log(f"ok — brief published for {today_bdt(now_utc).isoformat()} (BDT), sentinel alive")
        return 0

    for b in breaches:
        _log(f"BREACH: {b}", err=True)
    message = "FLEET ALERT (off-box heartbeat, 07:30 BDT):\n" + "\n".join(
        f"- {b}" for b in breaches
    )
    if not send_discord_alert(webhook, message):
        _log("breach detected but the Discord alert could NOT be delivered", err=True)
        return 2
    _log(f"alert delivered ({len(breaches)} breach(es))")
    return 1


if __name__ == "__main__":
    sys.exit(main())
