# Brief Part 2 — Rollback Runbook

Invoke when V4 produces a bad `index.html`, a hallucinated number, a silently empty section, or any failure that would be visible to subscribers.

**Target:** within 15 minutes, GHA is back in control and today's send is either the legacy output or paused.

## Option A — V4 ran and produced a bad output (most common)

1. `ssh adnan@135.181.43.68`
2. `sudo sed -i 's|BRIEF_DRY_RUN=0|BRIEF_DRY_RUN=1|' /etc/brief.env`
3. `sudo systemctl stop brief.service` (if still running)
4. If a bad commit already landed on `main`: `cd ~/the-brief && git revert HEAD && git push origin main`.
5. Locally, re-enable GHA schedule:
   ```
   git checkout main
   # uncomment the schedule block in .github/workflows/daily-update.yml
   git commit -am "ci(rollback): re-enable GHA schedule"
   git push origin main
   ```
6. Trigger the GHA workflow manually via `workflow_dispatch` if the subscribers need today's send.

## Option B — V4 hasn't run yet, pre-emptive disable

1. `ssh adnan@135.181.43.68`
2. `sudo systemctl disable --now brief.timer`
3. `sudo sed -i 's|BRIEF_DRY_RUN=0|BRIEF_DRY_RUN=1|' /etc/brief.env` (belt-and-braces).
4. Re-enable GHA schedule as in Option A step 5.

## Exit from rollback

Once the root cause is fixed and a fresh shadow-soak of 3 clean days completes: redo Task 6.3 cutover runbook.
