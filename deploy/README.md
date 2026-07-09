# The Brief — VPS operator runbook

## One-time install

1. Complete `docs/ops/part2-preflight.md`.
2. `ssh adnan@135.181.43.68`
3. `cd ~/the-brief && git checkout main && git pull`
4. `sudo cp deploy/brief.env.example /etc/brief.env`
5. Edit `/etc/brief.env` — fill every `REDACTED`. `sudo chmod 640 /etc/brief.env && sudo chown root:adnan /etc/brief.env`
6. `sudo deploy/install.sh`
7. `sudo systemctl start brief.service` (first manual run).
8. `journalctl -u brief.service -f` — watch to completion.
9. Confirm a new row in Supabase `briefs` (latest `issue_no`, today's `brief_date`).
10. Confirm SPA at https://thebrief.clauding-lab.com/ flips to the new issue.

## Daily operation (after install)

Nothing to do. Timer fires every day at 06:30 BDT (Mon–Sun since PR #116). Discord pings on every run.

Each fire self-deploys first: a fail-closed guard (`deploy/brief_guard.sh`)
refuses to publish unless the checkout is on `main` (a held publish + Discord
alert beats silently publishing feature-branch code; readers keep yesterday's
complete brief), then `ExecStartPre` runs `git pull --ff-only origin main`
(best-effort, 120s cap) so a merged PR reaches the next scheduled brief without
a manual pull (AGENTS.md landmine 21), then the guard runs again to log the
post-pull branch + commit that actually runs. If GitHub is unreachable the
publish still runs on the current checkout. A non-fast-forwardable checkout
(local divergence) is skipped silently — if `git rev-parse --short HEAD` lags
origin/main, resolve the divergence manually.

**Self-deploy caveat:** a merged PR is pulled and run UNATTENDED at the next
fire. Any PR needing manual steps — Supabase DDL (landmine 18), new deps in
`requirements.txt` (`pip install` into the venv), new `/etc/brief.env` vars —
must have those steps applied BEFORE merge, not after.

## Failure alerts (OnFailure → Discord)

`brief.service` carries `OnFailure=brief-alert@%n.service`. Any hard failure — non-zero
exit (including the sub-editor's exit 4), a `TimeoutStartSec` SIGTERM, an OOM-kill —
fires `deploy/brief_alert.sh`, which posts the failed unit name, host, BDT timestamp,
and a journal tail to Discord.

- Webhook: set `DISCORD_ALERT_WEBHOOK_URL` in `/etc/brief.env` (falls back to
  `DISCORD_PREVIEW_WEBHOOK_URL`; if neither is set the alert logs to stderr and no-ops).
- Journal tail in the alert needs `adnan` in the `systemd-journal` group:
  `sudo usermod -aG systemd-journal adnan` (optional — without it the alert still
  fires, minus the log excerpt).
- Test end-to-end without touching a real publish:
  `sudo systemctl start brief-alert@brief.service.service` → a ping should land.

## Weekly export (brief-export.timer)

Supabase is the ONLY copy of every issue and the LLM prose is unreproducible.
`brief-export.timer` fires Saturdays 09:30 BDT (03:30 UTC — clear of the publish
window, which can stretch to ~08:00 BDT under 529 retries) and dumps `briefs` +
all child tables (`sections`, `metrics`, `news`, `chart_series`, `chart_notes`)
as dated JSON to `/home/adnan/brief-exports/<YYYY-MM-DD>/` with a `manifest.json`
of row counts. Retention: newest 12 runs (~3 months); older dirs pruned.

- Failures alert via `OnFailure=brief-alert@%n.service` (same Discord path).
- No self-deploy `ExecStartPre` of its own — intentional: `brief.service`'s daily
  pull keeps the shared checkout fresh, and one self-deploying unit per checkout
  avoids two units racing a git pull.
- Manual run: `sudo systemctl start brief-export.service`, then check
  `cat /home/adnan/brief-exports/$(date +%F)/manifest.json`.
- The export dir lives OUTSIDE the repo checkout so a repo wipe can't take the
  archive with it. For true off-box durability, periodically copy it down from
  the Mac: `rsync -a adnan@135.181.43.68:/home/adnan/brief-exports/ ~/Backups/brief-exports/`.

## Off-box heartbeat (ExonVPS, 07:30 BDT cron)

`deploy/heartbeat.py` runs on **ExonVPS** (`adnan-local@103.187.23.22`) — deliberately
off the Hetzner box that publishes, so a dead box can't kill its own watchdog. One
cron, two checks, one Discord alert on breach:

1. **The Brief published today** — today's `brief_date` (computed in **Asia/Dhaka**,
   not UTC: before 06:00 BDT the UTC date is still yesterday) is the latest
   `status=published` row in `briefs`. 7 days/week (PR #116) — no Saturday exclusion.
2. **EconDelta sentinel alive** — an `ok` `run_logs` row with
   `source=freshness_sentinel` finished within 26 h (its timer fires 13:30 BDT).

Reads Supabase with the **anon key only** (both tables anon-readable, verified
2026-07-09 — never put the service key on this box). Exit codes: `0` healthy ·
`1` breach (alert delivered) · `2` heartbeat failure (Supabase unreachable, or
alert undeliverable).

### ExonVPS install (manual, as adnan-local)

```bash
# 1. This repo is not cloned on ExonVPS — copy the one file:
scp deploy/heartbeat.py adnan-local@103.187.23.22:/home/adnan-local/brief-heartbeat.py

# 2. Env file (template: deploy/brief-heartbeat.env.example; ANON key only):
sudo tee /etc/brief-heartbeat.env >/dev/null <<'ENV'
SUPABASE_URL=https://ssbliukchgibjcjohibi.supabase.co
SUPABASE_ANON_KEY=<anon key>
DISCORD_ALERT_WEBHOOK_URL=<same webhook as the Hetzner alert kit>
ENV
sudo chmod 640 /etc/brief-heartbeat.env && sudo chown root:adnan-local /etc/brief-heartbeat.env

# 3. Manual test (expect exit 0 + an "ok" line; exit 1 + a Discord ping on breach):
python3 /home/adnan-local/brief-heartbeat.py --env-file /etc/brief-heartbeat.env; echo "exit=$?"

# 4. Cron at 07:30 BDT daily. Crontab runs in the SYSTEM timezone — check
#    `timedatectl` first. System TZ = UTC → 01:30; system TZ = Asia/Dhaka → 07:30.
crontab -e
30 1 * * * python3 /home/adnan-local/brief-heartbeat.py >> /home/adnan-local/brief-heartbeat.log 2>&1
```

**Install-order caveat:** EconDelta's `freshness_sentinel` (econdelta PR #80) must
have written its FIRST ok `run_logs` row before this cron goes live (its timer
fires 13:30 BDT), or the first heartbeat will — correctly — alert
"no ok freshness_sentinel row". Install after 13:30 BDT, or expect one advisory alert.

**Last-turtle limitation, honestly:** nothing watches this watchdog. If the
heartbeat itself breaks (box down, cron removed, env deleted) the only signals are
`brief-heartbeat.log` going quiet and cron's discarded mail. It exits non-zero and
logs loudly on its own failures — but something has to be the last turtle.

## Common failures

| Symptom | Fix |
|---|---|
| `journalctl`: `Claude CLI binary not found: claude` | `/etc/brief.env` missing `CLAUDE_BINARY` or path wrong. Re-point at `/home/adnan/.npm-global/bin/claude`. |
| `journalctl`: `Claude CLI exited 1: Session not found` | Max OAuth expired. On the host: `claude` interactively, re-authenticate. |
| `journalctl`: `V6 publish failed: subeditor verdict=fail` | Editor output failed sub-editor self-review. Check the most recent log for the failure reason; usually fixed by retry on next timer fire. |
| `journalctl`: Supabase 4xx/5xx in `run_publish` | Check `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` in `/etc/brief.env`; verify the `briefs`/`sections` schema is up to date. |
| Discord webhook silent | `DISCORD_WEBHOOK_URL` unset or wrong. `curl -X POST -H 'Content-Type: application/json' -d '{"content":"test"}' "$DISCORD_WEBHOOK_URL"` should return 204. |

## Rollback

See `docs/ops/part2-rollback-runbook.md`. TL;DR: `BRIEF_DRY_RUN=1` in `/etc/brief.env`, `sudo systemctl restart brief.timer`, re-enable GHA schedule in `.github/workflows/daily-update.yml`.

## Uninstall

`sudo deploy/uninstall.sh` — leaves env + logs + artifacts intact.
