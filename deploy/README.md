# The Brief — VPS operator runbook

## One-time install

1. Complete `docs/ops/part2-preflight.md`.
2. `ssh adnan@135.181.43.68`
3. `cd ~/the-brief && git checkout main && git pull`
4. `sudo cp deploy/brief.env.example /etc/brief.env`
5. Edit `/etc/brief.env` — fill every `REDACTED`. `sudo chmod 640 /etc/brief.env && sudo chown root:adnan /etc/brief.env`
6. Provision the stable publication lock directory BEFORE installing the unit:
   `sudo install -d -o adnan -g adnan -m 700 /home/adnan/.local/state/the-brief`
   then `sudo deploy/install.sh`
7. `sudo systemctl start brief.service` (first manual run).
8. `journalctl -u brief.service -f` — watch to completion.
9. Confirm a new row in Supabase `briefs` (latest `issue_no`, today's `brief_date`).
10. Confirm SPA at https://thebrief.clauding-lab.com/ flips to the new issue.

## Daily operation (after install)

Nothing to do. Timer fires every day at 08:00 BDT (Mon–Sun since PR #116; moved from 06:30 in PR #149 so the fire lands after EconDelta's aggregate). Discord pings on every run.

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
exit (except intentional dry-run exit 3; including the sub-editor's exit 4), a `TimeoutStartSec` SIGTERM, an OOM-kill —
fires `deploy/brief_alert.sh`, which posts the failed unit name, host, BDT timestamp,
and a bounded, redacted tail of `/home/adnan/the-brief/logs/brief-systemd.log` to Discord.
That application log contains the actual Python traceback (for example, a
`V6PublishError`); the service journal alone may not contain it.

- Webhook: set `DISCORD_ALERT_WEBHOOK_URL` in `/etc/brief.env` (falls back to
  `DISCORD_PREVIEW_WEBHOOK_URL`; if neither is set the alert logs to stderr and no-ops).
- The shared alert unit uses journal tails for the allowlisted
  `brief-export.service` and `chess-prodigy-prune.service`. These need `adnan`
  in the `systemd-journal` group for the excerpt:
  `sudo usermod -aG systemd-journal adnan`.
- **Approved-channel test after deployment:** run exactly one
  `sudo systemctl start brief-alert@brief.service.service` and confirm one
  message arrives in the intended Discord channel. Check that it names the
  application log and contains no credentials or recipient addresses. This
  test sends a real alert; do it only during the approved release step.
- **Shared with another repo on the same box.** `chess-prodigy-prune.service`
  (clauding-lab/chess-prodigy, `deploy/`) carries the same
  `OnFailure=brief-alert@%n.service` line. Renaming or moving `brief-alert@.service`,
  `deploy/brief_alert.sh`, the `/home/adnan/the-brief` checkout or `/etc/brief.env`
  silently kills that repo's prune-failure alarm — update its unit in the same change.

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

## Off-box heartbeat (ExonVPS, 09:45 BDT cron)

`deploy/heartbeat.py` runs on **ExonVPS** (`adnan-local@103.187.23.22`) — deliberately
off the Hetzner box that publishes, so a dead box can't kill its own watchdog. One
cron, two checks, one Discord alert on breach:

1. **The Brief published today** — today's `brief_date` (computed in **Asia/Dhaka**,
   not UTC: before 06:00 BDT the UTC date is still yesterday) is the latest
   `status=published` row in `briefs`. 7 days/week (PR #116) — no Saturday exclusion.
2. **EconDelta sentinel alive** — an `ok` `run_logs` row with
   `source=freshness_sentinel` finished within 26 h (its actual timer fires
   03:35 BDT). The 26 h liveness limit stays unchanged.

The Brief's timer starts at 08:00 BDT and has a 90-minute runtime limit. The
09:45 check allows another 15 minutes before declaring today's issue missing.
The code also gates the Brief check by this deadline if run manually earlier;
the sentinel check still runs.

Reads Supabase with the **anon key only** (both tables anon-readable, verified
2026-07-09 — never put the service key on this box). Exit codes: `0` healthy ·
`1` breach (alert delivered) · `2` heartbeat failure (Supabase unreachable, or
alert undeliverable).

### ExonVPS install (manual, as adnan-local)

```bash
# 1. This repo is not cloned on ExonVPS — copy the one file:
scp deploy/heartbeat.py adnan-local@103.187.23.22:/home/adnan-local/brief-heartbeat.py

# 2. Preserve the installed env file (template: deploy/brief-heartbeat.env.example).
#    Verify readability without printing its keys or webhook:
test -r /home/adnan-local/.brief-heartbeat.env

# 3. Read-only syntax check before enabling cron:
python3 -m py_compile /home/adnan-local/brief-heartbeat.py

# 4. ExonVPS system TZ is Asia/Dhaka; verify with `timedatectl`. Replace its
#    existing 07:30 BDT entry, which starts `30 7 * * *` and uses the same
#    --env-file path, with this 09:45 BDT line. Do not leave both installed.
crontab -e
45 9 * * * python3 /home/adnan-local/brief-heartbeat.py --env-file /home/adnan-local/.brief-heartbeat.env >> /home/adnan-local/brief-heartbeat.log 2>&1
crontab -l
```

Confirm `crontab -l` shows exactly one `brief-heartbeat.py` line.

**Install-order caveat:** EconDelta's `freshness_sentinel` (econdelta PR #80) must
have written its FIRST ok `run_logs` row before this cron goes live (its timer
fires 03:35 BDT), or the first heartbeat will — correctly — alert
"no ok freshness_sentinel row". Install after its first successful run, or expect
one advisory alert.

**Last-turtle limitation, honestly:** nothing watches this watchdog. If the
heartbeat itself breaks (box down, cron removed, env deleted) the only signals are
`brief-heartbeat.log` going quiet and cron's discarded mail. It exits non-zero and
logs loudly on its own failures — but something has to be the last turtle.

## Common failures

| Symptom | Fix |
|---|---|
| `journalctl`: `Claude CLI binary not found: claude` | `/etc/brief.env` missing `CLAUDE_BINARY` or path wrong. Re-point at `/home/adnan/.npm-global/bin/claude`. |
| `journalctl`: `brief_guard: REFUSING to publish — only NNN MB free ...` | Free disk on the box, or raise the floor for this box only: `BRIEF_MIN_FREE_MB=<new value>` in `/etc/brief.env` (default 2048; see AGENTS.md landmine 39). |
| `journalctl`: `brief_guard: REFUSING to publish — CLAUDE_BINARY ... not found on PATH` / `... resolved to '/usr/bin/...', a stale binary` | `/etc/brief.env`'s `CLAUDE_BINARY` is unset or wrong. Re-point at `/home/adnan/.npm-global/bin/claude`, never `/usr/bin/claude` — that copy is a separate, stale 2.1.104 build the service must not run (AGENTS.md landmine 39). |
| `journalctl`: `Claude CLI exited 1: Session not found` | Max OAuth expired. On the host: `claude` interactively, re-authenticate. |
| `journalctl`: `V6 publish failed: subeditor verdict=fail` | Editor output failed sub-editor self-review. Check the most recent log for the failure reason; usually fixed by retry on next timer fire. |
| `journalctl`: Supabase 4xx/5xx in `run_publish` | Check `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` in `/etc/brief.env`; verify the `briefs`/`sections` schema is up to date. |
| Discord webhook silent | `DISCORD_WEBHOOK_URL` unset or wrong. `curl -X POST -H 'Content-Type: application/json' -d '{"content":"test"}' "$DISCORD_WEBHOOK_URL"` should return 204. |

## Rollback

TL;DR: `BRIEF_DRY_RUN=1` in `/etc/brief.env` to pause sends, `sudo systemctl disable --now brief.timer` (`brief.timer` carries `Persistent=true`; a plain `stop` survives only until the next boot or re-arm and a missed fire gets caught up). To roll back the code, `git revert` the bad commit and push to `main` — `brief.service`'s `ExecStartPre` self-pull (`deploy/brief.service:37-39`, see AGENTS.md landmine #21) picks it up at the next fire, or SSH in and `git -C ~/the-brief pull --ff-only origin main` to apply it sooner. There is no GitHub Actions cron to re-enable — the V1 GHA workflow was retired in PR #57 and deleted 2026-05-01.

## Uninstall

`sudo deploy/uninstall.sh` — leaves env + logs + artifacts intact.

## Publication identity, concurrency and maintenance pause

Code allocates the issue number once from the BDT run date and existing rows.
A unique same-day row (published or draft) keeps its issue number; a new date
uses the maximum issue number plus one. Conflicting same-day rows or either
model changing the allocated number/date hold publication with exit 4.
The publisher checks the target's date again immediately before deletion.
Live `--today` must equal today's BDT date. Historical replay requires
`--dry-run`; historical correction is a separate reviewed operation.

All live runs must use `python -m brief.cli run --publish`, as user `adnan`
with the normal `/home/adnan` home directory. The CLI holds a nonblocking
process lock from before database identity/gather reads through subscriber
delivery. Another invocation exits 4 before reads, models, writes or sends.
The lock lives at `/home/adnan/.local/state/the-brief/publication.lock` for
both systemd and manual runs, independent of checkout/current directory and
`PrivateTmp`. The dedicated directory must be a real directory owned by the
service user with no group/other permissions (provision it as mode 0700).
An unsafe existing directory is refused; the CLI never silently changes its
permissions or ownership. Never delete, replace or symlink the lock file. It remains on
disk after release; the operating system releases ownership when the process
exits. This protects cooperating same-user processes on one host, not
external database writers or a distributed database transaction.

**Install prerequisite for existing hosts:** create the lock directory using
the step above BEFORE copying the revised `brief.service`; its
`ReadWritePaths` requires that directory to exist. Install the unit and run
`sudo systemctl daemon-reload`. The unit now treats successful intentional
exit 3 as success (`SuccessExitStatus=3`); exit 1 and hold exit 4 remain failures.
A git self-pull does not install or reload the systemd unit. Do not rely on
these service settings until the installed unit has been verified.

Set `BRIEF_DRY_RUN=1` in `/etc/brief.env` to pause database writes and all
subscriber, preview and in-process pipeline warning sends. Accepted true
values are `1`, `true`, `yes`, `on`; false values are unset, empty, `0`,
`false`, `no`, `off` (case-insensitive, surrounding whitespace ignored).
Any other value fails before gathering data. The effective dry-run is
resolved before `--write-fixture`/`--preview-notify` validation; the pause
allows fixtures but suppresses preview sends. Explicit `--dry-run` still
wins when the environment says false, and can still request preview sends
when the environment pause is off. Models and reads still run while paused;
stop/disable the timer as well when a maintenance window needs no execution.
The separate systemd hard-failure alert remains active for genuine failures.

Same-day replacement runs automatically suppress subscriber delivery,
including draft retries: without a delivery ledger a draft could be the
remains of a failed replacement of an already emailed issue. There is **no
supported resend command** yet. Missing/partial delivery must wait for the
separate controlled retry workflow with a delivery-ledger check (R3); do not
invoke the notifier directly or add an unchecked resend flag. First-ever
publication for a date retains normal delivery (one Brevo POST per recipient).

**Remaining replacement failure window — release blocker for R3:** the
existing publisher deletes the old row before inserting the replacement
as a draft. If it crashes in that interval, there is no same-day row left
to prove the intended identity or earlier delivery. B1's local lock and
row-based suppression do not close that gap or provide end-to-end duplicate
send protection. The controlled retry/delivery guard must account for it
before live rollout; do not recover that state with an unattended re-fire.
