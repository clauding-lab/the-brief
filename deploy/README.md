# The Brief — VPS operator runbook

## One-time install

1. Complete `docs/ops/part2-preflight.md`.
2. `ssh adnan@135.181.43.68`
3. `cd ~/the-brief && git checkout feat/v4-retarget && git pull`
4. `sudo cp deploy/brief.env.example /etc/brief.env`
5. Edit `/etc/brief.env` — fill every `REDACTED`. `sudo chmod 640 /etc/brief.env && sudo chown root:adnan /etc/brief.env`
6. `sudo deploy/install.sh`
7. `sudo systemctl start brief.service` (first manual run).
8. `journalctl -u brief.service -f` — watch to completion.
9. Inspect `~/the-brief/artifacts/run_report.json` — `status` must be `ok` or `degraded`.
10. Confirm Discord webhook fired. Confirm the `shadow/YYYY-MM-DD` branch exists on GitHub.

## Daily operation (after install)

Nothing to do. Timer fires Sun–Fri at 06:30 BDT automatically. Discord pings on every run.

## Common failures

| Symptom | Fix |
|---|---|
| `journalctl`: `Claude CLI binary not found: claude` | `/etc/brief.env` missing `CLAUDE_BINARY` or path wrong. Re-point at `/home/adnan/.npm-global/bin/claude`. |
| `journalctl`: `Claude CLI exited 1: Session not found` | Max OAuth expired. On the host: `claude` interactively, re-authenticate. |
| `run_report.json`: `status: degraded`, one call `"status": "error"`, `reason: "timed out"` | Expected during Bangladesh bank holidays when sources lag. Check the next-day run before alarming. |
| `git push` fails in logs | Deploy key missing or expired. See `docs/ops/part2-preflight.md` section 4 and re-issue. |
| Discord webhook silent | `DISCORD_WEBHOOK_URL` unset or wrong. `curl -X POST -H 'Content-Type: application/json' -d '{"content":"test"}' "$DISCORD_WEBHOOK_URL"` should return 204. |

## Rollback

See `docs/ops/part2-rollback-runbook.md`. TL;DR: `BRIEF_DRY_RUN=1` in `/etc/brief.env`, `sudo systemctl restart brief.timer`, re-enable GHA schedule in `.github/workflows/daily-update.yml`.

## Uninstall

`sudo deploy/uninstall.sh` — leaves env + logs + artifacts intact.
