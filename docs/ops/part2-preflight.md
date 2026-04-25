# Brief Part 2 — VPS Preflight Checklist

Run each command on the VPS (`ssh adnan@135.181.43.68` — or local if you're already there).
Tick the checkbox once the expected output is confirmed. Do not start `install.sh` until every item is green.

## 1. Binary resolution

- [ ] `/home/adnan/.npm-global/bin/claude --version` → prints `2.1.119` or newer.
- [ ] `echo $PATH | tr ':' '\n' | grep npm-global` → the `.npm-global/bin` path appears (interactive shell only; systemd won't see this — we pin via `CLAUDE_BINARY` in the service file).
- [ ] `/home/adnan/.npm-global/bin/claude -p "Reply only with the word ECHO" --model claude-opus-4-7 --output-format json --no-session-persistence --tools "" --permission-mode bypassPermissions` → returns JSON with `"result":"ECHO"` within 3 seconds.
- [ ] `/usr/bin/claude --version` either doesn't exist OR prints an older version — leave it; we will not use it.

## 2. EconDelta data source

- [ ] `ls -la /home/adnan/econdelta/data/latest.json` → file exists, mtime is within the last 24h.
- [ ] `jq '.generated_at' /home/adnan/econdelta/data/latest.json` → prints an ISO-8601 timestamp from today (or yesterday on weekends).
- [ ] `sudo -u adnan cat /home/adnan/econdelta/data/latest.json | head -c 200` → JSON is readable by the `adnan` user (the service runs as `adnan`).

## 3. Credentials

- [ ] `test -f /etc/brief.env || echo MISSING` → prints `MISSING` (we will create it in 5.9; abort install if this file already exists with other contents).
- [ ] `test -f /home/adnan/.claude/.credentials.json && stat -c '%a' /home/adnan/.claude/.credentials.json` → prints `600` or `640`. Max OAuth session must be live.

## 4. Supabase connectivity

- [ ] From VPS: `curl -sS -o /dev/null -w '%{http_code}\n' "$SUPABASE_URL/rest/v1/metric_history?select=metric_id&limit=1" -H "apikey: $SUPABASE_SERVICE_ROLE_KEY"` → prints `200`. (Use the values that will go into `/etc/brief.env`.)

## 5. Headlines scrape

- [ ] From VPS: `curl -sS -o /dev/null -w '%{http_code}\n' https://www.thedailystar.net/business` → prints `200`. Repeat for `prothomalo.com`, `tbsnews.net`, `dhakatribune.com`, `businessstandardbd.com`. Any `403` / `429` is an ASN block — flag it; we'll note in `docs/ops/part2-shadow-observations.md` and rely on the per-source degraded path.

## 6. Systemd readiness

- [ ] `systemctl --version` → 249 or newer.
- [ ] `test -d /etc/systemd/system && echo OK` → prints `OK`.
- [ ] `systemctl list-timers --all | grep econdelta` → existing econdelta timers appear (confirms the systemd-timer pattern is already proven on this host).

## 7. Disk

- [ ] `df -h /home/adnan` → at least 2 GB free.
- [ ] `df -h /` → at least 500 MB free (for `/var/log` journal).

## 8. GitHub push-back (SSH deploy key)

The pipeline pushes artifacts to `clauding-lab/the-brief` from the VPS via SSH. A deploy key with `contents: write` must already be installed on the repo and the matching private key must be on the VPS.

- [ ] `test -f /home/adnan/.ssh/the-brief && stat -c '%a' /home/adnan/.ssh/the-brief` → prints `600`. (Private key path used by `brief.gitops`; if the path differs, update `GIT_SSH_COMMAND` in `/etc/brief.env`.)
- [ ] `ssh-keygen -y -f /home/adnan/.ssh/the-brief | awk '{print $2}'` → prints the public key. Compare against **GitHub → repo `clauding-lab/the-brief` → Settings → Deploy keys** — the same key must be listed with **Allow write access** ticked. If absent, add it before continuing.
- [ ] `GIT_SSH_COMMAND='ssh -i /home/adnan/.ssh/the-brief -o IdentitiesOnly=yes' ssh -T git@github.com 2>&1 | grep -E "successfully authenticated|Permission denied"` → prints a line containing `successfully authenticated` (GitHub's banner; the SSH session itself exits non-zero, that's normal).
- [ ] From a temp clone: `GIT_SSH_COMMAND='ssh -i /home/adnan/.ssh/the-brief -o IdentitiesOnly=yes' git ls-remote git@github.com:clauding-lab/the-brief.git refs/heads/main` → prints the current `main` HEAD SHA (proves read access).

If any of the above fail, generate a fresh keypair (`ssh-keygen -t ed25519 -f /home/adnan/.ssh/the-brief -N ''`), add the `.pub` to the repo's deploy keys with write access, and re-run this section. Do **not** continue to `install.sh` until all four boxes are green — `brief.gitops.push_artifacts` will fail at first run otherwise.

When every item is ticked, proceed to `deploy/install.sh`.
