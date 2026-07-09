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

REPO=/home/adnan/the-brief

branch="$(git -C "$REPO" symbolic-ref --short -q HEAD || echo DETACHED)"
head="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"

echo "brief_guard: branch=$branch head=$head"

if [[ "$branch" != "main" ]]; then
  echo "brief_guard: REFUSING to publish from '$branch' (only main) — holding this run;" \
       "fix with: git -C $REPO checkout main" >&2
  exit 1
fi

exit 0
