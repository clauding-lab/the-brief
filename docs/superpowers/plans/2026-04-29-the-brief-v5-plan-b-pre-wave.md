# V5 Plan B — Pre-Wave: Pipeline split (PR #20)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `brief/pipeline.py` (1,244 lines) into `brief/pipeline.py` (V4 logic + V5 dispatcher, ~720 lines) and a new `brief/pipeline_v5.py` (V5 editorial pipeline, ~525 lines), with zero behavior change. Both files end up under the 800-line soft cap.

**Architecture:** Pure module extraction. The V4 entry-point function `render_index_html` (line 636 in current `pipeline.py`) keeps living in `pipeline.py` and continues to dispatch to V5 helpers — those helpers move to `pipeline_v5.py` and get re-imported. No public API changes; no import-path changes for callers outside `brief/`.

**Tech Stack:** Python 3.14, pytest. Only standard refactor tooling — no new dependencies.

**Spec reference:** [docs/superpowers/specs/2026-04-29-the-brief-v5-plan-b-design.md](../specs/2026-04-29-the-brief-v5-plan-b-design.md) §3 (Pre-Wave row), §4 (file layout).

**Branch:** `feat/v5-pilot` (already pushed to origin; PR #19 is open against `feat/v4-retarget`). This pre-wave PR will stack on top of the same branch.

**Estimated session length:** ~1 hour. TDD-friendly (refactor; baseline tests must pass before AND after).

---

## Pre-flight check

Before any task, confirm baseline state:

- [ ] **Confirm working branch is `feat/v5-pilot` and tree is clean.**

Run:
```bash
cd ~/Projects/clauding-lab/the-brief
git status --short --branch
```
Expected:
```
## feat/v5-pilot...origin/feat/v5-pilot
```
(no `M` or `??` lines under tracked files; untracked `.venv`, `artifacts/`, `logs/`, `.superpowers/` are all fine.)

- [ ] **Confirm baseline test count: 612/612 passing.**

Run:
```bash
source .venv/bin/activate
python -m pytest --no-cov -q 2>&1 | tail -3
```
Expected:
```
612 passed in <N>s
```
If the count is anything other than 612 passed, STOP and report — the baseline has drifted since 2026-04-29.

---

## Task 1: Identify the exact V5 boundary

**Files:**
- Read: `brief/pipeline.py`

**Goal:** Confirm the line ranges to move are still what the plan says (file may have grown since this plan was written).

- [ ] **Step 1: Find the V5 section divider.**

Run:
```bash
grep -n "^# V5 Editorial Pipeline" brief/pipeline.py
```
Expected: a single line number (was 719 when this plan was written). Record this as `V5_START`.

- [ ] **Step 2: Get the file line count.**

Run:
```bash
wc -l brief/pipeline.py
```
Expected: a single line count (was 1244). Record this as `FILE_END`.

- [ ] **Step 3: List every top-level definition from V5_START onwards.**

Run:
```bash
awk -v s="$V5_START" 'NR>=s && /^(def |class |[A-Z_]+: |# )/{print NR": "$0}' brief/pipeline.py
```

Expected output should include (functions and constants, exact names from the current file — verify each appears):

```
_record_v5_call_ok
_record_v5_call_error
run_v5_editorial
run_v5_qa_gate
_section_summary_for_top_picks
_section_summary_for_qa
_section_n
_V5_KICKER_BY_ID                      # module-level constant dict
_v5_synthesize_tldr
_v5_apply_section_adapter
_placement_for
_triggering_metric_for
_top_picks_fallback
_todays_call_fallback
_strip_css_and_script                 # borderline — see Task 2
_run_v5_headlines_curation
_v5_metric_value
_run_v5
```

If any function name above is missing from the awk output, STOP and update this plan before proceeding.

- [ ] **Step 4: Check `_strip_css_and_script` usage.**

Run:
```bash
grep -n "_strip_css_and_script" brief/pipeline.py
```
Expected: definition + usage sites. If it's only used by V5 code (e.g., inside `_run_v5`), it moves to `pipeline_v5.py`. If it's used by V4 code too, it stays in `pipeline.py` and gets imported into `pipeline_v5.py`.

Record decision: __MOVE_TO_V5__ or __KEEP_IN_V4__.

- [ ] **Step 5: Find all imports the V5 portion uses.**

Run:
```bash
sed -n '1,134p' brief/pipeline.py | grep -E "^(import|from)"
```
This gives you the existing import block (V5 functions reuse it). Record the list — `pipeline_v5.py` will need a subset of these.

---

## Task 2: Create `brief/pipeline_v5.py` with all V5 code

**Files:**
- Create: `brief/pipeline_v5.py`
- Modify: `brief/pipeline.py` (delete the moved code, add import statement)

**Goal:** Move all V5 functions and constants from `pipeline.py` into `pipeline_v5.py`. Update `pipeline.py` to re-import them so external callers don't break.

- [ ] **Step 1: Create `brief/pipeline_v5.py` with module docstring + imports.**

Write `brief/pipeline_v5.py` with this header (then we'll add the body in step 2):

```python
"""V5 editorial pipeline — Claude-powered banker daily.

Extracted from pipeline.py during V5 Plan B (Pre-Wave) on 2026-04-29.
Pure code-move refactor: no behavior changes from extraction.

Public functions used by pipeline.run / render_index_html:
- run_v5_editorial
- run_v5_qa_gate
- _run_v5_headlines_curation
- _run_v5
- _v5_apply_section_adapter

Private helpers stay private (underscore-prefixed).
"""
from __future__ import annotations

# Imports needed by the V5 body — derived from what pipeline.py imports today.
# Trim later if any are unused after extraction.
import asyncio
import json
import logging
from typing import Any

from brief.cadence.systemic_risk import (
    DEFAULT_SYSTEMIC_RISK_RULES,
    evaluate_systemic_risks,
)
from brief.claude.editorial_qa import (
    EDITORIAL_QA_PROMPT,
    parse_editorial_qa,
)
from brief.claude.max_client import (
    MaxCallError,
    MaxCallResult,
    run_max,
)
from brief.claude.todays_call import TodaysCall, parse_todays_call
from brief.claude.top_picks import TopPicks, parse_top_picks
from brief.claude.bankerread import (
    BankerRead,
    parse_bankerread_full_v5,
    parse_bankerread_stale_v5,
)
from brief.claude.systemic_risks import (
    SystemicRisksResult,
    parse_systemic_risks,
)
from brief.schema import SectionData
```

(Adjust the import list to match what Task 1 Step 5 actually showed. If `pipeline.py` doesn't import `top_picks` or `bankerread` or `editorial_qa` directly — they may live in different modules — derive the right list from the existing file. **Do not invent imports.**)

- [ ] **Step 2: Move all V5 code from `pipeline.py` to `pipeline_v5.py`.**

Run a precise extraction. Easiest approach: use `sed` to extract lines `V5_START` through `FILE_END` of the original `pipeline.py`, then append to `pipeline_v5.py`:

```bash
sed -n "${V5_START},${FILE_END}p" brief/pipeline.py >> brief/pipeline_v5.py
```

Then truncate `pipeline.py` to the V4 portion only:

```bash
# Keep lines 1 through (V5_START - 1)
sed -i '' "$((V5_START))"',$d' brief/pipeline.py
```

(macOS BSD `sed` requires `-i ''`. On Linux it's `sed -i`.)

- [ ] **Step 3: Add re-imports to `pipeline.py`.**

Open `brief/pipeline.py` and add this re-import block at the top of the file — right after the existing imports (find the last `from brief.X import Y` line and add this block after it):

```python
# V5 pipeline lives in brief/pipeline_v5.py — re-imported here so callers that
# do `from brief.pipeline import run_v5_editorial` (etc.) keep working without
# code changes. Do not delete: tests + render_index_html depend on these names
# being available on this module.
from brief.pipeline_v5 import (  # noqa: E402,F401
    _V5_KICKER_BY_ID,
    _placement_for,
    _record_v5_call_error,
    _record_v5_call_ok,
    _run_v5,
    _run_v5_headlines_curation,
    _section_n,
    _section_summary_for_qa,
    _section_summary_for_top_picks,
    _todays_call_fallback,
    _top_picks_fallback,
    _triggering_metric_for,
    _v5_apply_section_adapter,
    _v5_metric_value,
    _v5_synthesize_tldr,
    run_v5_editorial,
    run_v5_qa_gate,
)
```

(If Task 1 Step 4 said `_strip_css_and_script` moves to V5, add it to the re-import list. If it stays in V4, do NOT add it.)

- [ ] **Step 4: Verify both files have valid Python syntax.**

Run:
```bash
python -c "import brief.pipeline; import brief.pipeline_v5; print('imports ok')"
```
Expected: `imports ok`. If you get an `ImportError` or `NameError`, the import block is wrong — fix and retry.

- [ ] **Step 5: Run the full test suite.**

Run:
```bash
python -m pytest --no-cov -q 2>&1 | tail -5
```
Expected:
```
612 passed in <N>s
```

If any test fails, the typical causes are:
1. A function moved to `pipeline_v5.py` but its caller in `pipeline.py` doesn't have access to it (re-import block missing the name) — check Step 3.
2. A circular import (`pipeline_v5.py` imports something from `pipeline.py` that imports from `pipeline_v5.py`) — refactor to break the cycle, never via lazy import inside a function.
3. A V5 function relies on a `pipeline.py` private helper that should also have moved — move it too.

**Do NOT mark this step done until all 612 tests pass.**

- [ ] **Step 6: Verify file sizes are both under 800 lines.**

Run:
```bash
wc -l brief/pipeline.py brief/pipeline_v5.py
```

Expected: each file under 800. Targets:
- `brief/pipeline.py` ≈ 720 lines
- `brief/pipeline_v5.py` ≈ 540 lines

If either exceeds 800, the boundary was wrong. Re-run Task 1 Step 3 and decide what else to move.

---

## Task 3: Trim unused imports in both files

**Files:**
- Modify: `brief/pipeline.py`, `brief/pipeline_v5.py`

**Goal:** Remove imports that are no longer used after the split. Both modules currently inherit the full import block; a chunk of those are only relevant to one module.

- [ ] **Step 1: Find unused imports in `brief/pipeline.py`.**

Run:
```bash
python -c "import ast; src = open('brief/pipeline.py').read(); tree = ast.parse(src); imports = [n.names[0].name if isinstance(n, ast.Import) else f'{n.module}.{n.names[0].name}' for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]; print('\n'.join(imports))"
```

Then for each import name, grep for usage:
```bash
for name in <each_import_alias>; do
  count=$(grep -c "\b${name}\b" brief/pipeline.py)
  if [ "$count" -le 1 ]; then echo "UNUSED: $name"; fi
done
```

(`-le 1` because the import line itself counts as one occurrence.)

Delete each `UNUSED:` import.

- [ ] **Step 2: Same audit for `brief/pipeline_v5.py`.**

Repeat the grep audit on the new file.

- [ ] **Step 3: Run the test suite again.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```
Expected: `612 passed`. If a `NameError` or `ImportError` surfaces, you trimmed an import that's still in use — restore it.

---

## Task 4: Smoke-test the V5 dispatcher works end-to-end (optional but recommended)

**Files:** none (read-only).

**Goal:** Verify `render_index_html` still routes V5 → V5 functions correctly. This catches any subtle import-path issue that the unit tests miss.

- [ ] **Step 1: Run a stub render test.**

Run:
```bash
python -c "
from brief.pipeline import render_index_html, _run_v5, run_v5_editorial, run_v5_qa_gate
print('render_index_html:', render_index_html.__module__)
print('_run_v5:', _run_v5.__module__)
print('run_v5_editorial:', run_v5_editorial.__module__)
print('run_v5_qa_gate:', run_v5_qa_gate.__module__)
"
```

Expected:
```
render_index_html: brief.pipeline
_run_v5: brief.pipeline_v5
run_v5_editorial: brief.pipeline_v5
run_v5_qa_gate: brief.pipeline_v5
```

This confirms the V4 entry-point stays in `pipeline.py` and the V5 helpers it calls live in `pipeline_v5.py`.

---

## Task 5: Commit

**Files:** `brief/pipeline.py`, `brief/pipeline_v5.py`.

- [ ] **Step 1: Stage and commit.**

Run:
```bash
git add brief/pipeline.py brief/pipeline_v5.py
git commit -m "refactor(pipeline): extract V5 editorial pipeline to pipeline_v5.py

Pure code-move refactor — zero behavior change. pipeline.py was at 1244 lines
(over the 800-line soft cap); the V5 portion (~525 lines, starting at
the '# V5 Editorial Pipeline' divider) moves to a new pipeline_v5.py module.

pipeline.py re-imports the moved names so callers that do
'from brief.pipeline import run_v5_editorial' (etc.) keep working without
code changes. render_index_html (the V4 entry-point) stays in pipeline.py
and continues to dispatch to V5 helpers via the re-imported names.

Pre-Wave for Plan B (V5 templates for the 13 non-pilot sections) — splitting
now keeps both files comfortably under the cap before adding 13 more
template registrations.

Tests: 612/612 passing (unchanged baseline).
File sizes:
  brief/pipeline.py    ~720 lines
  brief/pipeline_v5.py ~540 lines"
```

Expected: clean commit with two files modified.

---

## Task 6: Push and open PR (gated on user approval)

**Goal:** Push the branch and open PR #20 against `feat/v4-retarget`.

This task involves shared-state actions (push to origin, GitHub PR creation) that need explicit user approval per the user's standing rule. Do NOT automate.

- [ ] **Step 1: Stop and ask user.**

Tell the user:
> "Pre-Wave refactor done locally. 612/612 tests passing. Both files under the 800-line cap. Branch `feat/v5-pilot` has one new commit. May I push to origin and open PR #20 against `feat/v4-retarget`?"

Wait for action-explicit approval like "yes, push and open the PR" or "yes, push to origin and open PR #20".

- [ ] **Step 2: Push.**

```bash
git push origin feat/v5-pilot
```

- [ ] **Step 3: Open PR.**

```bash
gh pr create --base feat/v4-retarget --head feat/v5-pilot --title "refactor(pipeline): extract V5 editorial pipeline to pipeline_v5.py" --body "$(cat <<'EOF'
## Summary

Pure code-move refactor — zero behavior change. Splits `brief/pipeline.py` (1,244 lines, over the 800-line soft cap) into two focused modules:

- `brief/pipeline.py` — V4 logic + V5 dispatcher (~720 lines)
- `brief/pipeline_v5.py` — V5 editorial pipeline (~540 lines)

`pipeline.py` re-imports the moved names so callers that do `from brief.pipeline import run_v5_editorial` keep working without code changes. `render_index_html` (the V4/V5 dispatcher entry-point) stays in `pipeline.py` and continues to route to V5 helpers via the re-imported names.

### Why now

Pre-Wave for [V5 Plan B](../docs/superpowers/specs/2026-04-29-the-brief-v5-plan-b-design.md), which adds 13 new section templates plus updates to the dispatch table. Splitting now keeps both files comfortably under the cap before adding those changes.

### Test plan

- [x] 612/612 unit tests pass on `feat/v5-pilot` (baseline unchanged)
- [x] Both files under 800-line soft cap
- [x] `render_index_html.__module__` confirmed as `brief.pipeline`
- [x] `_run_v5.__module__`, `run_v5_editorial.__module__`, `run_v5_qa_gate.__module__` confirmed as `brief.pipeline_v5`
- [ ] Manual: confirm V4 production path (`BRIEF_RENDERER` unset) still renders identically
- [ ] Manual: confirm V5 path (`BRIEF_RENDERER=v5`) still dispatches to V5 helpers without regression

### Out of scope

- Wave 1 (FX, Macro, Remit, NBR templates) — separate PR
- Tiered model routing — parked
EOF
)"
```

- [ ] **Step 4: Verify PR state.**

```bash
gh pr view --json number,state,mergeable,baseRefName,headRefName,additions,deletions,changedFiles
```
Expected: `state=OPEN`, `mergeable=MERGEABLE`, `baseRefName=feat/v4-retarget`, `headRefName=feat/v5-pilot`, two files changed.

---

## Acceptance criteria for PR #20

When all six tasks are checked off:

- ✓ `brief/pipeline.py` is under 800 lines (target ~720)
- ✓ `brief/pipeline_v5.py` exists, is under 800 lines (target ~540), and contains all V5 functions
- ✓ All 612 existing tests still pass — zero regression
- ✓ `from brief.pipeline import run_v5_editorial` (and 14 other re-imported names) still works
- ✓ `render_index_html.__module__ == 'brief.pipeline'`
- ✓ `run_v5_editorial.__module__ == 'brief.pipeline_v5'`
- ✓ Single commit on `feat/v5-pilot`, pushed to origin, PR #20 open and `MERGEABLE`

After PR #20 merges (separate user action), Wave 1 plan gets written against the post-split code structure.
