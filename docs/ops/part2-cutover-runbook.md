# Brief Part 2 — Cutover Runbook

**Do not start this until `docs/ops/part2-shadow-observations.md` shows 3 consecutive clean days.**

## Step 1 — Pause the GHA schedule

Edit `.github/workflows/daily-update.yml`:

```yaml
on:
  # schedule:
  #   - cron: '30 0 * * 0-5'     # commented out; kept for quick re-enable
  workflow_dispatch:              # keep for emergencies
```

Commit on `main` directly (small, reversible):
```
git add .github/workflows/daily-update.yml
git commit -m "ci(cutover): pause GHA schedule; VPS is primary"
git push origin main
```

## Step 2 — Flip VPS pipeline to main + email

On the VPS:
```
sudo sed -i 's|--shadow|--push-main --email|' /etc/systemd/system/brief.service
sudo systemctl daemon-reload
```

(Agents: the actual CLI flags — `--push-main --email` — must already be implemented. See Task 6.2 pre-reqs in this plan.)

## Step 3 — Add deprecation header to `update.py`

```
# update.py
# DEPRECATED: superseded by brief.cli (V4 pipeline). This file is kept
# only for emergency rollback via GHA workflow_dispatch. Scheduled removal:
# 2026-05-09 (14 days after cutover).
```

## Step 4 — Verify next scheduled run

- `ssh adnan@135.181.43.68 'systemctl list-timers brief.timer --no-pager'`
- Confirm the next trigger is tomorrow 00:30 UTC.
- Next morning (06:30 BDT): confirm `main` branch got a new commit from `clauding-lab` deploy key, email landed in adnan's inbox, Discord said `✅ ok`, no `shadow/` branch from today (since we're in main mode now).

## Step 5 — Monitor 7 days

- Daily Discord check. Daily `jq '.status' main/run_report.json` on the VPS.
- Any `status == "error"` → execute rollback runbook immediately, do not wait.
- At day 7 (2026-05-03 at the earliest): cutover is ratified. Proceed to Task 6.5 (`update.py` removal).
