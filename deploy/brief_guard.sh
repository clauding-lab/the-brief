#!/usr/bin/env bash
# Fail-closed branch guard for the self-deploying brief.service (PR #130 review HIGH).
#
# `git pull --ff-only origin main` merges into WHATEVER branch is checked out. If the
# box checkout is ever left on a feature branch (or a detached HEAD), the best-effort
# pull silently no-ops under its `-` prefix and ExecStart would publish untested
# feature-branch code to bankers with no trace of what ran.
#
# This guard runs WITHOUT the `-` prefix (a failure holds the publish):
#   - refuses to proceed unless the checkout is exactly `main` (detached HEAD refused);
#   - logs the resolved branch + short HEAD, so every fire records what is checked out.
#
# A held publish is strictly better than silently publishing wrong code: readers keep
# yesterday's COMPLETE brief (PR #125 two-phase semantics), and the failure fires the
# #129 OnFailure Discord alert. It runs twice per fire — before the pull (gate) and
# after it (log the post-pull commit that will actually run).

set -u

REPO="${BRIEF_REPO:-/home/adnan/the-brief}"
BRIEF_MIN_FREE_MB="${BRIEF_MIN_FREE_MB:-2048}"
# PATH-resolved fallback binaries under this prefix are refused (review LOW,
# 2026-09-16): AGENTS.md landmine 39 records a separate root-owned, stale
# `/usr/bin/claude` on the box that "is NOT a fallback the service can use".
# Overridable only so the test suite can exercise the check without touching
# the real /usr/bin.
BRIEF_STALE_BINARY_PREFIX="${BRIEF_STALE_BINARY_PREFIX:-/usr/bin}"

# _refuse: stderr (for a human reading logs/brief-systemd.log) AND the syslog
# socket (for journald), then exit 1.
#
# brief.service redirects THIS unit's own stdout/stderr to
# logs/brief-systemd.log (StandardOutput=append:/StandardError=append:) — that
# is NOT the journal brief_alert.sh reads (`journalctl -u brief.service -n 15`
# on OnFailure). `logger`'s write to /dev/log bypasses that file redirection
# entirely: journald attributes it to this unit by cgroup, so it lands in the
# journal tail the Discord alert is built from. Without this, every alert read
# only systemd's own "exit-code" line — the same opaque alert that went
# unread for four mornings, 13–16 Sep (review HIGH, 2026-09-16).
_refuse() {
  local msg="$1"
  echo "$msg" >&2
  command -v logger >/dev/null 2>&1 && logger -t brief_guard -p user.err -- "$msg" || true
  exit 1
}

# A bare non-negative integer (MB count) — nothing else. An env-supplied
# threshold like "2G"/"4 GB", or a `df` column that comes back blank or "-",
# must REFUSE, not silently skip the check (bash's `((...))` treats a bad
# operand as an error mid-expression, or as 0, depending on the operand —
# review MEDIUM/LOW, 2026-09-16).
_is_plain_int() {
  [[ "$1" =~ ^[0-9]+$ ]]
}

if ! _is_plain_int "$BRIEF_MIN_FREE_MB"; then
  _refuse "brief_guard: REFUSING to publish — BRIEF_MIN_FREE_MB='$BRIEF_MIN_FREE_MB' is not a plain integer number of MB (set it in /etc/brief.env as e.g. BRIEF_MIN_FREE_MB=2048)"
fi

branch="$(git -C "$REPO" symbolic-ref --short -q HEAD || echo DETACHED)"
head="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"

# Unconditional — every fire, success or refusal, records what was checked
# out (brief.service's own comment on the SECOND guard call promises exactly
# this: "re-verifies main and logs the POST-pull branch + short HEAD, so the
# journal records exactly which commit this fire ran" — that was only true on
# the success path before this line existed here — review LOW, 2026-09-16).
echo "brief_guard: branch=$branch head=$head"

if [[ "$branch" != "main" ]]; then
  _refuse "brief_guard: REFUSING to publish from '$branch' (only main) — holding this run; fix with: git -C $REPO checkout main"
fi

# Disk-free check — a full disk is how npm's postinstall was left mid-extraction
# on 12 Sep 2026 (AGENTS.md landmine 39), leaving a non-executable stub behind.
free_mb="$(df -Pm "$REPO" | awk 'NR==2 {print $4}')"

if ! _is_plain_int "$free_mb"; then
  _refuse "brief_guard: REFUSING to publish — could not read free disk for $REPO (df reported '${free_mb}')"
fi

if (( free_mb < BRIEF_MIN_FREE_MB )); then
  _refuse "brief_guard: REFUSING to publish — only ${free_mb} MB free on the filesystem holding $REPO (need >= ${BRIEF_MIN_FREE_MB} MB); free disk, then: sudo systemctl start brief.service (to lower the floor for one box, set BRIEF_MIN_FREE_MB in /etc/brief.env)"
fi

# Binary check — names the cause instead of letting a bad CLAUDE_BINARY surface
# as an opaque PermissionError three layers down in the Python pipeline.
bin="${CLAUDE_BINARY:-claude}"

if [[ "$bin" != */* ]]; then
  resolved="$(command -v -- "$bin" 2>/dev/null || true)"
  if [[ -z "$resolved" ]]; then
    _refuse "brief_guard: REFUSING to publish — CLAUDE_BINARY '$bin' not found on PATH"
  fi
  if [[ "$resolved" == "$BRIEF_STALE_BINARY_PREFIX"/* ]]; then
    _refuse "brief_guard: REFUSING to publish — CLAUDE_BINARY unset and PATH resolved to '$resolved', a stale binary AGENTS.md landmine 39 says is NOT a fallback the service can use; set CLAUDE_BINARY explicitly in /etc/brief.env"
  fi
  bin="$resolved"
fi

# Capture readlink's own resolution first, and only fall back to the raw path
# when that capture is EMPTY. A dangling symlink makes BSD `readlink -f` print
# a partial (non-empty) path AND exit non-zero; the old `$(cmd || fallback)`
# form ran the fallback anyway and concatenated both outputs into one
# variable, corrupting the one-line refusal below into two (review LOW,
# 2026-09-16 — confined to macOS/dev; GNU readlink -f on the box exits 0 here).
real="$(readlink -f -- "$bin" 2>/dev/null)"
[[ -n "$real" ]] || real="$bin"

# GNU stat (`-c`) on the box; fall back to BSD stat (`-f`) so this degrades
# gracefully when the suite runs on the owner's Mac (spec point 5).
size_mode() {
  stat -c '%s %a' -- "$1" 2>/dev/null || stat -f '%z %Lp' -- "$1" 2>/dev/null || echo "0 000"
}

if [[ -f "$real" && -x "$real" ]]; then
  read -r size mode <<<"$(size_mode "$real")"
  echo "brief_guard: branch=$branch head=$head disk_free_mb=$free_mb claude=$real ($size bytes)"
  exit 0
fi

read -r size mode <<<"$(size_mode "$real")"
_refuse "brief_guard: REFUSING to publish — CLAUDE_BINARY '$bin' -> '$real' is not an executable file (size=${size} mode=${mode}). A ~500-byte non-executable file is npm's placeholder from a half-finished Claude Code update — see AGENTS.md landmine 39; rollback: rename the retired .claude-code-* tree back, or free disk and reinstall."
