# Brief Part 2 — First Run (VPS)

Perform after `deploy/install.sh` completes without error. Tick each item.

- [ ] `sudo systemctl status brief.timer` → `active (waiting)`, `Trigger:` shows the next 00:30 UTC firing.
- [ ] `sudo systemctl start brief.service` — trigger a manual run NOW (do not wait for timer).
- [ ] `journalctl -u brief.service -f` — watch until `Main PID ... (code=exited, status=0/SUCCESS)` or `status=2/DEGRADED`. Any other exit is a failure — read the stack, file an issue, do NOT proceed.
- [ ] `cat ~/the-brief/artifacts/run_report.json | jq '.status, .total_cost_usd, .degraded_sections, .git_push'` — expect:
  - `status` ∈ {`ok`, `degraded`}
  - `total_cost_usd` ≤ 5.00
  - `degraded_sections` — empty or a short list
  - `git_push.pushed` = `true`, branch = `shadow/<today>`
- [ ] GitHub: visit `https://github.com/clauding-lab/the-brief/tree/shadow/<today>` — commit present, `index.html` size 80–200 KB.
- [ ] Discord: ping received in the configured channel, contains today's date and a green/yellow status icon.
- [ ] Tail `~/the-brief/logs/brief-systemd.log` — no stack traces, no `claude-opus-4-7: unknown model` type errors.

If every item is green: Phase 5 exit gate passed. Proceed to Phase 6 (shadow soak).
