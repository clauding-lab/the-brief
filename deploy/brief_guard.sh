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

branch="$(git -C "$REPO" symbolic-ref --short -q HEAD || echo DETACHED)"
head="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"

if [[ "$branch" != "main" ]]; then
  echo "brief_guard: REFUSING to publish from '$branch' (only main) — holding this run;" \
       "fix with: git -C $REPO checkout main" >&2
  exit 1
fi

# Disk-free check — a full disk is how npm's postinstall was left mid-extraction
# on 12 Sep 2026 (AGENTS.md landmine 39), leaving a non-executable stub behind.
free_mb="$(df -Pm "$REPO" | awk 'NR==2 {print $4}')"

if (( free_mb < BRIEF_MIN_FREE_MB )); then
  echo "brief_guard: REFUSING to publish — only ${free_mb} MB free on the filesystem holding $REPO" \
       "(need >= ${BRIEF_MIN_FREE_MB} MB); free disk, then: sudo systemctl start brief.service" >&2
  exit 1
fi

# Binary check — names the cause instead of letting a bad CLAUDE_BINARY surface
# as an opaque PermissionError three layers down in the Python pipeline.
bin="${CLAUDE_BINARY:-claude}"

if [[ "$bin" != */* ]]; then
  resolved="$(command -v -- "$bin" 2>/dev/null || true)"
  if [[ -z "$resolved" ]]; then
    echo "brief_guard: REFUSING to publish — CLAUDE_BINARY '$bin' not found on PATH" >&2
    exit 1
  fi
  bin="$resolved"
fi

real="$(readlink -f -- "$bin" 2>/dev/null || printf '%s' "$bin")"

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
echo "brief_guard: REFUSING to publish — CLAUDE_BINARY '$bin' -> '$real' is not an executable file" \
     "(size=${size} mode=${mode}). A ~500-byte non-executable file is npm's placeholder from a" \
     "half-finished Claude Code update — see AGENTS.md landmine 39; rollback: rename the retired" \
     ".claude-code-* tree back, or free disk and reinstall." >&2
exit 1
