# The Brief — VPS operator runbook

## One-time install

1. Complete `docs/ops/part2-preflight.md`.
2. `ssh adnan@135.181.43.68`
3. `cd ~/the-brief && git checkout main && git pull`
4. `sudo cp deploy/brief.env.example /etc/brief.env`
5. Edit `/etc/brief.env` — fill every `REDACTED`. `sudo chmod 640 /etc/brief.env && sudo chown root:adnan /etc/brief.env`
6. `sudo deploy/install.sh` — it creates the publication lock directory
   `/home/adnan/.local/state/the-brief` (owner `adnan`, mode 700) BEFORE it installs the
   units, because `brief.service`'s `ReadWritePaths` needs it to exist at unit start.
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
  `sudo systemctl start brief-alert@brief-test.service` and confirm one
  message beginning `TEST ALERT:` arrives in the intended Discord channel.
  The test instance uses the installed alert unit's environment and the
  allowlisted `brief.service` application log. Check that it names the
  application log and contains no credentials or recipient addresses. This
  test sends a real alert; do it only during the approved release step.
- **Shared with another repo on the same box.** `chess-prodigy-prune.service`
  (clauding-lab/chess-prodigy, `deploy/`) carries the same
  `OnFailure=brief-alert@%n.service` line. Renaming or moving `brief-alert@.service`,
  `deploy/brief_alert.sh`, the `/home/adnan/the-brief` checkout or `/etc/brief.env`
  silently kills that repo's prune-failure alarm — update its unit in the same change.

## EconDelta snapshot missing, broken or old at the 08:00 BDT fire

**How the file gets here.** EconDelta writes `latest.json` on ExonVPS at 02:55 BDT
(retry 03:15). A Hetzner user-crontab line, `*/5 * * * * /home/adnan/bin/pull-econdelta-latest.sh`,
copies it to `/home/adnan/econdelta/data/latest.json` with `rsync -t` every five minutes.
The copy is atomic (temporary file + rename) but checks nothing: a broken or older file on
ExonVPS arrives as it is. The Brief's own reader is the only check.

**What you see.** One Discord message beginning `ALERT: The Brief is publishing from …`
and naming `cause: <category>`. The run is **not** held (owner decision, 26 Sep 2026): the
issue still publishes at 08:00 BDT, marked degraded, with at most one such alert per run.
- `missing`, `truncated`, `unparseable`, `unreadable`, `wrong shape`: the snapshot could not
  be used; the issue is built from saved history.
- `stale capture` (over 24 h old), `earlier-day capture`, `capture went backwards` (older
  than the newest capture a live run already read and passed readiness with): the snapshot
  is read, and its figures carry their own, older dates.

A **hold** (exit 4, the OnFailure alert with the log tail) is a different path: the
snapshot contradicts itself, for example a capture time later than the run.

**1. Read the cause (on Hetzner; read-only, prints no credentials).**
```bash
grep "Publication readiness" /home/adnan/the-brief/logs/brief-systemd.log | tail -n 1
ls -l --time-style=full-iso /home/adnan/econdelta/data/latest.json
python3 -c "import json;d=json.load(open(\"/home/adnan/econdelta/data/latest.json\"));print(d[\"updated_at\"])"  # UTC; add 6 h for BDT (jq is not installed on Hetzner)
sha256sum /home/adnan/econdelta/data/latest.json | cut -c1-16
crontab -l | grep -n pull-econdelta-latest                      # the */5 line must be there
tail -n 20 /home/adnan/econdelta/logs/pull-cron.log             # silent on success; no timestamps
cat /home/adnan/.local/state/the-brief/econdelta-capture-mark.json  # newest capture a live run read (past readiness)
```

**2. Compare with ExonVPS (needs the owner's SSH approval; read-only).**
```bash
ssh adnan-local@103.187.23.22 'ls -l --time-style=full-iso ~/econdelta/data/latest.json;
  python3 -c "import json;d=json.load(open(\"/home/adnan-local/econdelta/data/latest.json\"));print(d[\"updated_at\"])";
  sha256sum ~/econdelta/data/latest.json | cut -c1-16;
  systemctl list-timers "econdelta-aggregate*" --no-pager'
```
Never print `~/.ssh/*` or the pull key. To see the pull key's restrictions on ExonVPS, cut
the key material:
`grep hetzner-econdelta-pull ~/.ssh/authorized_keys | sed -E 's#ssh-ed25519 [A-Za-z0-9+/=]+#ssh-ed25519 <redacted>#'`.

**3. Decide by cause.**
- **Load failure on Hetzner, ExonVPS file fine** (valid JSON, newer or different hash): the
  pull has not delivered it (look for `Connection timed out` in `pull-cron.log`). It retries
  every five minutes, so tomorrow is safe without action. To refresh the copy now, run the
  pull once as `adnan`: `/home/adnan/bin/pull-econdelta-latest.sh`.
- **ExonVPS's own file is missing or broken:** an EconDelta problem. Follow AGENTS.md
  landmine 38 (Supabase `run_logs`, then the aggregate log on ExonVPS). Never hand-edit or
  hand-copy a `latest.json` into place.
- **`stale capture` / `earlier-day capture`:** no new accepted capture was made (a hard
  review reject keeps the previous file, landmine 38), or the pull is stuck (the two hashes
  differ).
- **`capture went backwards`:** the Hetzner `updated_at` is older than the capture mark.
  Usually an older `latest.json` was restored on ExonVPS. If that was deliberate, do
  nothing: each live run alerts until the next aggregate writes a newer capture, because
  the mark is never lowered. If the mark itself is wrong (for example a manual live run read
  another file through `ECONDELTA_DATA`), move it aside, never delete it:
  `mv ~/.local/state/the-brief/econdelta-capture-mark.json ~/.local/state/the-brief/econdelta-capture-mark.json.bak-$(date +%Y%m%d)`.
  The next live run starts a new mark.

**4. Re-publishing today is optional and the owner's call.** Once the Hetzner copy is right,
`sudo systemctl start brief.service` re-runs today's issue. A same-day run REPLACES the issue
in place (AGENTS.md landmine 33), and subscriber email is not re-sent. The default is to leave
the degraded issue up: the next 02:55 BDT aggregate and 08:00 BDT fire recover on their own.

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
| Discord: `ALERT: The Brief is publishing from … — cause: <category>` | The EconDelta snapshot was missing, broken or old; the issue still published, degraded. See "EconDelta snapshot missing, broken or old at the 08:00 BDT fire" above. |
| Discord webhook silent | `DISCORD_WEBHOOK_URL` unset or wrong. `curl -X POST -H 'Content-Type: application/json' -d '{"content":"test"}' "$DISCORD_WEBHOOK_URL"` should return 204. |

## Rollback

TL;DR: `BRIEF_DRY_RUN=1` in `/etc/brief.env` to pause sends, `sudo systemctl disable --now brief.timer` (`brief.timer` carries `Persistent=true`; a plain `stop` survives only until the next boot or re-arm and a missed fire gets caught up). To roll back the code, `git revert` the bad commit and push to `main` — `brief.service`'s `ExecStartPre` self-pull (`deploy/brief.service:37-39`, see AGENTS.md landmine #21) picks it up at the next fire, or SSH in and `git -C ~/the-brief pull --ff-only origin main` to apply it sooner. There is no GitHub Actions cron to re-enable — the V1 GHA workflow was retired in PR #57 and deleted 2026-05-01.

**Not for a rollback across the R3 merge** (migration 0006, `publish_brief_atomic`,
`the-brief#215`). There a revert brings back the pre-R3 delete-and-insert publisher, and the
self-pull above would run it at the next fire, which the R3 design forbids. Follow the
rollback in [Coordinated release order](#coordinated-release-order-data-reliability-repair-r2--r3)
instead: `disable --now` the timer first and keep it disabled until a corrected atomic
publisher is merged.

## Uninstall

`sudo deploy/uninstall.sh` — leaves env + logs + artifacts intact.

## Publication identity, concurrency and maintenance pause

Code allocates the issue number once from the BDT run date and existing rows.
A unique same-day row (published or draft) keeps its issue number; a new date
uses the maximum issue number plus one. Conflicting same-day rows or either
model changing the allocated number/date hold publication with exit 4.
Publication is ONE database call, `publish_brief_atomic` (migration 0006, R3):
under its own lock the database checks the target date and issue again, then
replaces the edition in one transaction (AGENTS.md landmine 41).
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

**Install prerequisite for existing hosts:** `deploy/install.sh` creates the
lock directory before it copies the revised `brief.service`; its
`ReadWritePaths` requires that directory to exist, or systemd refuses to start
the unit and nothing publishes. Install the unit and run
`sudo systemctl daemon-reload` (install.sh does both). The unit now treats successful intentional
exit 3 as success (`SuccessExitStatus=3`); exit 1 and hold exit 4 remain failures.
A git self-pull does not install or reload the systemd unit. Do not rely on
these service settings until the installed unit has been verified.

**Rolling out a unit change to the box — in one sitting, in this order.** The box
checkout only moves when `brief.service` fires (its self-pull), so right after a merge
`/home/adnan/the-brief/deploy/install.sh` is still the OLD copy: it installs the old
unit and never creates the lock directory. And a fire between the merge and the install
self-pulls the new code but runs it under the OLD unit, whose read-only home has no
writable lock directory, so nothing publishes. So:

1. BEFORE the merge: `sudo systemctl stop brief.timer brief-export.timer` (no fire or
   weekly export can land in the gap; a reboot re-arms them, so do not leave them stopped).
2. Check nothing is running. `systemctl is-active brief.service brief-export.service`
   must print `inactive` or `failed` for both: either means not running (`failed` only
   says the last run held or failed). And `pgrep -af 'brief[.]cli'` must print nothing:
   a hand-started run (see "Manual fire") is outside systemd, so `is-active` cannot see it.
   Stopping the timers does not stop a run that is already going (a fire can run from
   08:00 to about 09:30 BDT), and a pull in the middle of a run makes it publish with old
   code and send with new code. If either unit says `active`, `activating` or
   `deactivating`, or pgrep prints a process, wait and check again; never stop a running
   fire to hurry this.
3. Merge the PR to `main`.
4. `sudo -u adnan git -C /home/adnan/the-brief pull --ff-only origin main` (as adnan, so
   `.git` stays adnan's; a diverged checkout fails here, loudly).
5. `sudo -u adnan git -C /home/adnan/the-brief log -1 --format='%H %s'` must show the
   merge commit. If not, stop and fix; do not run install.sh.
6. `sudo /home/adnan/the-brief/deploy/install.sh` — installs the new unit, creates the
   lock directory and starts `brief.timer` and `brief-export.timer` again.
7. Check: `systemctl cat brief.service | grep ReadWritePaths` lists
   `/home/adnan/.local/state/the-brief`; `stat -c '%U %a' /home/adnan/.local/state/the-brief`
   prints `adnan 700`; `systemctl list-timers brief.timer brief-export.timer` shows the next
   02:00 UTC (08:00 BDT) run and the next Saturday export. If install.sh stopped early, the
   timers are still stopped: fix the cause and re-run install.sh; never start them by hand
   under the old unit.

**Treat running install.sh as a possible publish.** It re-copies `brief.timer`, reloads
systemd and runs `systemctl start brief.timer`. Starting a timer that is already running
does nothing, but `brief.timer` has `Persistent=true`: if systemd counts a missed 08:00
slot it fires `brief.service` at once. If the stop in step 1 spanned an 08:00 BDT slot,
that catch-up is the documented `Persistent=true` behaviour (new code, new unit, the
day's issue). EconDelta's install.sh, which re-installs its
`Persistent=true` timers the same way, fired four services at once on 11 Jul 2026. This
has not been checked for `brief.timer`. Run it at a time when a publish is acceptable, or
set `BRIEF_DRY_RUN=1` first (models still run; no database write, no email) and remove
it before 08:00 BDT. Then `sudo journalctl -u brief.service --since "-10 min"` shows
whether it fired.

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
supported resend command**. R3 did not build one: an unattended retry needs a
separately designed and approved per-recipient delivery ledger. Before any
manual resend, check the Brevo provider records; do not invoke the notifier
directly or add an unchecked resend flag. First-ever publication for a date
retains normal delivery (one Brevo POST per recipient).

**The replacement window is closed (R3, migration 0006).** The old publisher
deleted the day's row before inserting the replacement; a crash in between left
no edition and no identity. `publish_brief_atomic` never deletes the `briefs`
row: it keeps the same id, issue number and date, replaces the children and
flips `status='published'` last, all in one transaction. A failure at any point
leaves the previous complete edition exactly as it was (rehearsed on the R3 test
database: cancel, kill and timeout mid-write; see
`docs/reviews/2026-09-25-repair-release-evidence.md`). Only
a fresh receipt from this run with `created_new_identity=true` may start the
email. An error, a timeout or a lost answer exits 4 and sends nothing; the
edition may still have committed ("published but possibly unemailed"), so check
the issue and Brevo before any manual send, and never re-fire to "retry".
If migration 0006 is missing on the database, the publisher exits 4 and names
it; there is no fallback to the old delete-and-insert path.

## Coordinated release order (data-reliability repair, R2 + R3)

**TLDR.** EconDelta goes first, then the history repair, then the database function, then
this Brief. Roll back in the opposite direction: the Brief first. Measured, not guessed
(controller ruling 28 Sep 2026, step 2 amended 29 Sep 2026; AGENTS.md landmine 44): the
deployed Brief `a810fcb` ignores the new producer's extra snapshot fields and does not break,
though it does not stay identical either (see "Transition window" below), while the new Brief
on the OLD producer drops the USD/BDT, gold, Brent and WTI cards on every fire, and the new
pair on unrepaired NBR history HOLDs every publish. The older "Brief consumer first" order is
superseded.

**Transition window: what the deployed Brief `a810fcb` shows on the new producer** (measured,
`fixG2-compat.md` §8; the controller ruling of 28 Sep 2026 carries these into this plan). They
apply to every `a810fcb` fire after the producer merge (step 1) and before the new Brief
replaces it (step 5): when the steps span more than one night, or when the old Brief is
resumed because a later step slipped (see "If step 3 or 4 slips" below):
- From the first night, the new EPB exports rows move its exports card to August and **hide
  its Trade Gap card** while exports lead imports (BB imports are still at June); the External
  Flow Balance chart shows exports months with no imports. The new Brief does the same, so this
  is the new data, not a reader mismatch.
- On an Opus-quarantine night before the first new-format 02:55 BDT archive exists, the new
  producer drops the rejected family instead of carrying yesterday's number. `a810fcb` then
  shows **no value** on the USD/BDT, gold, Brent and WTI cards; the DSE cards show their last
  history row marked stale under a **false "Non-trading day — last trading session"** reason,
  even on a trading day; the §02 gross-reserves card shows its history row, stale. If
  `advancing` or `declining` is dropped, `a810fcb` also tries a live dsebd.org scrape from
  Hetzner (code reading only, not measured; expect degraded breadth). The window for this
  closes after the first successful new-format 02:55 BDT archive, so the first night after the
  producer merge is the one to watch.
- A reading the new producer marks unavailable is still printed by `a810fcb`, as today.
No number is invented and nothing crashes or holds; record what the first issue shows in the
release evidence.

**Before step 1: pause and check (one agreed window, nothing merged yet).**
- Pick a night that avoids EconDelta's chain (01:00–03:35 BDT) for the checks and the
  Brief's fire plus watchdog (07:50–09:45 BDT) for the Brief steps.
- Read-only checks first: the installed timers on both boxes, the Hetzner five-minute
  snapshot pull (see "EconDelta snapshot missing, broken or old" above), `CLAUDE_BINARY`,
  free disk, and that the Supabase project is `ssbliukchgibjcjohibi`.
- Pause the Brief with a real stop, not only the environment flag: steps 1–2 of
  "Rolling out a unit change" in
  [Publication identity, concurrency and maintenance pause](#publication-identity-concurrency-and-maintenance-pause).
  `BRIEF_DRY_RUN=1` is extra protection only. Also make sure no other copy of the OLD
  publisher can run (a manual checkout, another host with the service key): it would
  still delete and re-insert around the new function's lock.

**The order.**

1. **EconDelta producer first, including the H5 NBR dating fix.** Merge `econdelta#137` so
   the 01:00 BDT `econdelta-gitpull` pulls it (it pulls `main` only; this branch changes no
   EconDelta unit, so no EconDelta `install.sh`). Merge it on the release night before
   01:00 BDT, or earlier.
2. **History repair R1 with exclusions (d) + (l), owner-applied.** After the new producer is
   merged (optional) but BEFORE its first `metric_history` write: the 02:55 BDT aggregate,
   the 03:15 BDT retry, a catch-up fire on an install, or any manual run. H5 writes the NBR
   2026-06-30 period row that the reviewed list would otherwise refuse. If R1 cannot finish
   before 02:55 BDT, keep the EconDelta aggregate timers stopped until it has (starting a
   `Persistent=true` timer after a missed slot fires it at once: EconDelta landmine 5).
3. **Round 4 NBR exclusion, owner-reviewed, before the new Brief's first fire.** Exclude the
   NBR capture-date restamps dated after 2026-09-24: exact keys from a recapture taken with
   the writers paused, each bound to its value, the producer's 2026-06-30 period row kept,
   rehearsed on its own isolated copy. Until round 4 is applied the new Brief must not go
   live. At release prep, compare the 2026-06-30 and 2026-07-31 rows of `tax_revenue`,
   `nbr_fytd_collected_cr` and `fiscal_nbr_collected_trn` with the reviewed before-images.
4. **Migration 0006, owner-applied through the Supabase SQL editor**, before the Brief merge
   (AGENTS.md landmines 18 and 41). Paste `migrations/0006_publish_brief_atomic.sql` as a
   whole; it checks the schema first and changes nothing if anything drifted. Afterwards
   capture the function definition and its grants (EXECUTE for `service_role` only).
5. **The new Brief, before its 08:00 BDT fire.** First confirm the new producer's first daily
   write has landed: after the 02:55 BDT run, the Hetzner `latest.json` must come from the new
   producer (it carries a `write_status` block) with a capture newer than the merge. On bare
   R1 history the new Brief holds until that write exists. Then deploy with steps 1–5 of
   "Rolling out a unit change" in
   [Publication identity, concurrency and maintenance pause](#publication-identity-concurrency-and-maintenance-pause):
   stop both timers, check nothing runs, merge `the-brief#215`, pull as `adnan`, check HEAD.
   **Recipient-contract check (task B4; blocking).** The new notifier refuses to email anyone
   if a single stored subscriber row breaks the signup contract, so check the stored rows
   before it can run. The merge also ships the repaired signup form: first wait until Vercel
   production serves the merge commit, so the old, looser signup cannot add a bad row after
   the check. Then run this read-only check. It calls only the new `fetch_subscribers()` (no
   email, no Brevo) and prints counts and an error category, never names, addresses or ids:

   ```bash
   sudo -u adnan bash -c 'cd /home/adnan/the-brief && set -a && . /etc/brief.env && set +a && .venv/bin/python -c "
   import json, sys
   from brief.notifier import fetch_subscribers, _error_tag
   try:
       count = len(fetch_subscribers())
   except Exception as error:
       print(json.dumps({\"validation_complete\": False, \"unique_recipients\": None, \"error_category\": _error_tag(error)}))
       sys.exit(1)
   print(json.dumps({\"validation_complete\": True, \"unique_recipients\": count, \"error_category\": None}))
   "'
   ```

   Record the commit, the BDT time and the printed line in the release evidence. If it fails
   (exit 1, `"validation_complete": false`), do not run steps 6–7: run
   `sudo systemctl disable --now brief.timer` so nothing fires, and stop. The owner reviews the
   incompatible stored rows; never delete or skip them to get past this check. Only after it
   passes, steps 6–7 of "Rolling out a unit change": run `deploy/install.sh` (the self-pull
   alone never installs the unit or creates `/home/adnan/.local/state/the-brief`; without it
   no fire can publish), then check. Preview with
   `python -m brief.cli run --publish --dry-run --no-notify --write-fixture <path>` before the
   first live fire.
6. **The 09:45 BDT watchdog heartbeat, the same morning, before 09:45 BDT** (task B5). On
   ExonVPS replace the old 07:30 BDT heartbeat line (`30 7 * * *`) with the 09:45 BDT one,
   as "ExonVPS install" in
   [Off-box heartbeat (ExonVPS, 09:45 BDT cron)](#off-box-heartbeat-exonvps-0945-bdt-cron)
   describes: copy the new `deploy/heartbeat.py`, keep the real `--env-file`, and confirm
   `crontab -l` shows exactly one heartbeat line. The 09:45 BDT time is the 08:00 BDT start plus
   the 90-minute run limit plus 15 minutes; B5 found that a 07:30 BDT check demands an issue that
   cannot exist yet. The alert log routing (`deploy/brief_alert.sh` reading the application
   log) arrives with the merge: prove it with the one approved-channel `TEST ALERT` in
   "Failure alerts" above, and record both in the release evidence.

**If step 3 or 4 slips** (round 4 or migration 0006 is not done by 07:50 BDT on the morning
the new Brief was due): do not merge `the-brief#215`. The new Brief must not go live without
both. The deployed Brief `a810fcb` is still paused from "Before step 1". The owner decides
before 07:50 BDT, and the release evidence records which:
- (a) keep it paused: no issue that day; the site keeps the last complete edition and the
  watchdog reports the missing issue. This is what happens when no decision is recorded. If
  the pause may outlast a reboot, use `sudo systemctl disable --now brief.timer brief-export.timer`
  instead of a plain stop (a reboot re-arms a stopped timer).
- (b) resume it for its 08:00 BDT fire with `sudo systemctl start brief.timer brief-export.timer`
  (started after 08:00 BDT, `Persistent=true` is expected to fire it at once; not yet
  checked for `brief.timer`, see above). This is the measured, compatible pair (`a810fcb` on the new producer), with the transition-window effects listed
  above; its behaviour on R1-repaired history before round 4 was not separately measured. It
  still publishes with today's delete-and-insert publisher, as production does now.
Then repeat the pause (steps 1–2 of "Rolling out a unit change") before step 5 on a later night.

**Rollback: roll back the Brief first**, then (only if needed) EconDelta. The new Brief on the
old producer drops four cards, so never leave that pair running. First
`sudo systemctl disable --now brief.timer` (a plain `stop` is not enough: `brief.timer` has
`Persistent=true`, so a reboot re-arms it and the missed fire runs at once), then check that
nothing runs (step 2 of "Rolling out a unit change"), then restore the previous Brief code on
`main` through a reviewed revert PR. A pre-R3 Brief still contains the delete-and-insert
publisher; per the R3 design, do not let it publish again: keep `brief.timer` disabled, and run
no `brief.cli run --publish` from a pre-R3 checkout, until a corrected atomic publisher is
merged. The site keeps serving the last complete edition meanwhile. Leave migration 0006 in
place; it is additive and the old reader code ignores it. Never restore a whole-table backup as
a code rollback.
