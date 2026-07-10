# B3 Item 11 — §02 Money-Market Line — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the Bangladesh overnight call-money rate as a §02 KPI tile and feed the 7-day/14-day tenor to the editor as prose context — so §02 can say where money trades and how deep liquidity is.

**Architecture:** One builder file (`brief/builders/bb.py`) gains a money-market reader that reads live rows from Supabase `metric_history` and OMITS on missing (no fallback constant — call money is a fast daily rate). The overnight rate slots in as the 4th metric (tile #4, before Reserves); the tenor points append after Reserves and only when the overnight tile is present, so they feed the editor but never render as tiles. No migration, no SPA/CSS, no prompt edit.

**Tech Stack:** Python 3.12, Pydantic (`brief/schema.py`), pytest (`.venv/bin/pytest`). Read-only Supabase `metric_history` via the existing `MetricHistoryClient` (builder never fetches — the pipeline enriches).

## Global Constraints

- **5-KPI-tile cap:** `app/components/Section.tsx:189` renders `metrics.slice(0, 5)`. Only a section's first 5 metrics become tiles. Tile-eligible metrics MUST precede prose-feed/context metrics in the list.
- **Metric-id stability:** `bb_policy_rate` / `bb_sdf` / `bb_slf` / `bb_gross_reserves` must NOT be renamed (`cadence.py` `fx_reserves_rule` keys on `bb_gross_reserves`; risk rules + SPA key on the corridor ids). New ids: `bb_call_money`, `bb_call_money_7d`, `bb_call_money_14d`.
- **Omit-on-missing (no fallback):** a missing/non-numeric money-market row emits NO metric — never a hardcoded constant (that would misrepresent where money trades today). Contrast the corridor's `_rate_metric`, which DOES fall back.
- **Atomic feed:** tenor points (`bb_call_money_7d` / `_14d`) are emitted ONLY when the overnight tile (`bb_call_money`) is present. Structurally guarantees a tenor point never occupies a tile slot.
- **Money-market metric fields:** `unit="%"`, `source="BB"`, `source_url=_BB_URL`, `cadence="daily"`.
- **Builder issues ZERO history-window calls** (landmine 23) — reads only via `ctx.history.get_latest(...)`. The pipeline's single batched `get_history_window` enriches `bb_call_money` with a sparkline for free.
- **Scope fence:** pipeline-only. No `brief/claude/prompts/*` edits, no `app/**`, no SQL/migration, no new deps.
- **Commits:** Conventional Commits; **no `Co-Authored-By: Claude` trailer** (project rule, `the-brief/CLAUDE.md`). Tests behavior-based and RED-proven. Branch is `feat/bb-money-market` (already created; spec committed at `4ce89c5`).

---

### Task 1: Overnight call-money tile (`bb_call_money`)

**Files:**
- Modify: `brief/builders/bb.py` (add `_money_market_metric` helper after `_rate_metric`; insert the call-money metric into `build()` after the corridor list, before the reserves block)
- Test: `tests/builders/test_bb.py` (add `_live_money_market_rows` helper + two tests)

**Interfaces:**
- Consumes: `BuilderContext` (`.history: MetricHistoryClient | None`, `.snapshot`, `.today`); `ctx.history.get_latest(metric_id) -> HistoryRow | None` where `HistoryRow(metric_id, as_of: date, value, source: str)`; `Metric` from `brief.schema`; `_BB_URL` constant already in `bb.py`.
- Produces: `_money_market_metric(ctx, *, metric_id: str, history_id: str, label: str) -> Metric | None` (used again in Task 2). `build()` emits a `bb_call_money` `Metric` at list index 3 (before `bb_gross_reserves`) when its row is present.

- [ ] **Step 1: Write the failing tests**

Add to `tests/builders/test_bb.py` (after the existing `_live_rate_rows` helper, and at the end of the file for the tests):

```python
def _live_money_market_rows(as_of=date(2026, 7, 9)):
    """Fresh money-market rows (probed 2026-07-10, Supabase metric_history)."""
    return {
        "call_money_rate": HistoryRow("call_money_rate", as_of, 9.56, "BB"),
        "call_money_rate_7d": HistoryRow("call_money_rate_7d", as_of, 9.41, "BB"),
        "call_money_rate_14d": HistoryRow("call_money_rate_14d", as_of, 11.19, "BB"),
    }


def test_overnight_call_money_tile_present_and_live():
    """§02 surfaces the overnight call-money rate as a tile-eligible metric read
    live from metric_history. FAILS if bb_call_money is dropped or hardcoded."""
    hist = _FakeHistory(latest={**_live_rate_rows(), **_live_money_market_rows()})
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    s = build(ctx)

    cm = _m(s, "bb_call_money")
    assert cm.value == 9.56
    assert cm.label == "Overnight Call Money"
    assert cm.unit == "%"
    assert cm.source == "BB"
    assert cm.cadence == "daily"
    assert cm.stale is False
    ids = [m.id for m in s.metrics]
    # tile-eligible: within the first 5 metrics (Section.tsx renders slice(0,5))
    assert ids.index("bb_call_money") < 5
    # grouped with the corridor, ahead of reserves
    assert ids.index("bb_call_money") < ids.index("bb_gross_reserves")


def test_call_money_omitted_when_missing_no_fallback():
    """Missing call_money_rate → NO bb_call_money metric (no fake fallback for a
    fast daily rate); §02 keeps exactly its 4 canonical metrics; no crash."""
    hist = _FakeHistory(latest=_live_rate_rows())  # no call-money rows
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    s = build(ctx)

    assert all(m.id != "bb_call_money" for m in s.metrics)
    assert {m.id for m in s.metrics} == {
        "bb_policy_rate", "bb_sdf", "bb_slf", "bb_gross_reserves",
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/builders/test_bb.py::test_overnight_call_money_tile_present_and_live tests/builders/test_bb.py::test_call_money_omitted_when_missing_no_fallback -v`
Expected: FAIL — `test_overnight...` errors with `StopIteration` (`_m` finds no `bb_call_money`); `test_call_money_omitted...` PASSES already (call money not yet emitted) — that's fine, it's the guard that stays green after Step 3.

- [ ] **Step 3: Add the helper and wire the metric**

In `brief/builders/bb.py`, add this helper immediately AFTER the `_rate_metric` function (after its closing `return ... )` around line 66):

```python
def _money_market_metric(
    ctx: BuilderContext,
    *,
    metric_id: str,
    history_id: str,
    label: str,
) -> Metric | None:
    """Read one money-market rate live from metric_history, or return None.

    Money-market rates are fast daily prints with no meaningful "last-known
    standing value", so a missing/non-numeric row OMITS the metric rather than
    falling back to a constant (which would misrepresent where money trades
    today). Contrast _rate_metric, whose standing corridor rates DO fall back.
    Reads only via get_latest — never get_history_window (landmine 23).
    """
    if ctx.history is None:
        return None
    row = ctx.history.get_latest(history_id)
    if row is None or not isinstance(row.value, (int, float)):
        return None
    return Metric(
        id=metric_id,
        label=label,
        value=float(row.value),
        unit="%",
        as_of=row.as_of,
        source="BB",
        source_url=_BB_URL,
        cadence="daily",
    )
```

Then, inside `build()`, immediately AFTER the corridor list literal closes (the `]` after the three `_rate_metric(...)` entries, ~line 77) and BEFORE the `reserves_val = ...` line, insert:

```python
    # Overnight call money — where banks actually lend each other cash, read
    # live. Tile #4, grouped with the corridor and ahead of Reserves. Omitted
    # (never faked) when the row is missing — a fast daily rate has no standing
    # fallback value.
    call_money = _money_market_metric(
        ctx,
        metric_id="bb_call_money",
        history_id="call_money_rate",
        label="Overnight Call Money",
    )
    if call_money is not None:
        metrics.append(call_money)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/builders/test_bb.py::test_overnight_call_money_tile_present_and_live tests/builders/test_bb.py::test_call_money_omitted_when_missing_no_fallback -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full bb suite to confirm no regression**

Run: `.venv/bin/pytest tests/builders/test_bb.py -q`
Expected: PASS — the 10 pre-existing tests + 2 new = 12 passed. (Existing corridor tests use `_live_rate_rows()` with no call-money rows, so `bb_call_money` is omitted and their assertions are unaffected.)

- [ ] **Step 6: Commit**

```bash
git add brief/builders/bb.py tests/builders/test_bb.py
git commit -m "feat(bb): surface overnight call-money rate as §02 tile"
```

---

### Task 2: Call-money tenor context (`bb_call_money_7d` / `_14d`), atomic + non-tile

**Files:**
- Modify: `brief/builders/bb.py` (add `_CALL_MONEY_TENORS` constant; append the tenor block in `build()` after the reserves append, guarded on the overnight tile being present)
- Test: `tests/builders/test_bb.py` (two tests)

**Interfaces:**
- Consumes: `_money_market_metric(...)` and the `call_money` local from Task 1.
- Produces: `build()` appends `bb_call_money_7d` then `bb_call_money_14d` (each present-and-numeric) at list indices ≥ 5, and ONLY when `call_money is not None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/builders/test_bb.py` (end of file):

```python
def test_tenor_points_present_but_never_tiles():
    """7d/14d call-money tenor feed the editor as prose context: present in the
    metric list at index >= 5, so slice(0,5) never renders them as tiles. The
    full order is asserted to lock the tile row (corridor + overnight + reserves)."""
    hist = _FakeHistory(latest={**_live_rate_rows(), **_live_money_market_rows()})
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    s = build(ctx)

    assert _m(s, "bb_call_money_7d").value == 9.41
    assert _m(s, "bb_call_money_7d").label == "Call Money · 7-day"
    assert _m(s, "bb_call_money_14d").value == 11.19
    ids = [m.id for m in s.metrics]
    assert ids.index("bb_call_money_7d") >= 5
    assert ids.index("bb_call_money_14d") >= 5
    assert ids == [
        "bb_policy_rate", "bb_sdf", "bb_slf", "bb_call_money",
        "bb_gross_reserves", "bb_call_money_7d", "bb_call_money_14d",
    ]


def test_tenor_omitted_when_overnight_missing():
    """The money-market feed is atomic: no overnight row → NO tenor metrics
    either, even when 7d/14d rows exist. Guarantees a tenor point can never land
    in the 5-tile slice."""
    rows = {**_live_rate_rows(), **_live_money_market_rows()}
    del rows["call_money_rate"]           # overnight gone; 7d/14d still present
    hist = _FakeHistory(latest=rows)
    ctx = BuilderContext(snapshot=_snap(), history=hist, today=TODAY)
    s = build(ctx)

    ids = {m.id for m in s.metrics}
    assert "bb_call_money" not in ids
    assert "bb_call_money_7d" not in ids
    assert "bb_call_money_14d" not in ids
    assert ids == {"bb_policy_rate", "bb_sdf", "bb_slf", "bb_gross_reserves"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/builders/test_bb.py::test_tenor_points_present_but_never_tiles tests/builders/test_bb.py::test_tenor_omitted_when_overnight_missing -v`
Expected: FAIL — `test_tenor_points...` errors with `StopIteration` (`_m` finds no `bb_call_money_7d`); `test_tenor_omitted...` PASSES already (no tenor emitted yet) — it's the guard that must stay green after Step 3.

- [ ] **Step 3: Add the tenor constant and the guarded append**

In `brief/builders/bb.py`, add this constant near the top (after the `_FALLBACK_*` / `_BB_URL` constants, ~line 25):

```python
# Call-money tenor points fed to the editor as prose context (never tiles).
# (id, metric_history id, label)
_CALL_MONEY_TENORS = (
    ("bb_call_money_7d", "call_money_rate_7d", "Call Money · 7-day"),
    ("bb_call_money_14d", "call_money_rate_14d", "Call Money · 14-day"),
)
```

Then, inside `build()`, immediately AFTER `metrics.append(reserves_metric)` (~line 117) and BEFORE the `freshness = section_freshness(...)` line, insert:

```python
    # Tenor curve (7d/14d) — prose context for the term premium. Emitted ONLY
    # alongside the overnight tile (atomic feed): with the overnight present the
    # tile-eligible core is 5, so these land at index >= 5 and never render as
    # tiles. Each still requires its own live row (omit-on-missing).
    if call_money is not None:
        for metric_id, history_id, label in _CALL_MONEY_TENORS:
            tenor = _money_market_metric(
                ctx, metric_id=metric_id, history_id=history_id, label=label
            )
            if tenor is not None:
                metrics.append(tenor)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/builders/test_bb.py::test_tenor_points_present_but_never_tiles tests/builders/test_bb.py::test_tenor_omitted_when_overnight_missing -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full bb suite**

Run: `.venv/bin/pytest tests/builders/test_bb.py -q`
Expected: PASS — 14 passed (10 pre-existing + 4 new). Note: `test_overnight_call_money_tile_present_and_live` and `test_tenor_points_present_but_never_tiles` use `_FakeHistory`, whose double has NO `get_history_window` method — so if `build()` ever issued a window call on the present-path it would crash here, which is the existing enforcement of landmine 23.

- [ ] **Step 6: Commit**

```bash
git add brief/builders/bb.py tests/builders/test_bb.py
git commit -m "feat(bb): add call-money 7d/14d tenor as §02 prose context"
```

---

### Task 3: Full-suite gate + record the 5-tile-cap landmine

**Files:**
- Modify: `AGENTS.md` (add landmine 25 after landmine 24)

**Interfaces:** none (documentation + verification only).

- [ ] **Step 1: Run the full test suite (the real gate, no filtering)**

Run: `.venv/bin/pytest -q`
Expected: PASS — exit 0, 630 passed (item-12 baseline 626 + 4 new). If anything else fails, STOP and investigate before proceeding — do not pipe through `tail`/`grep` (masks the exit code).

- [ ] **Step 2: Add landmine 25 to `AGENTS.md`**

Append immediately AFTER the landmine-24 block (`## 24. Live corridor/reserves ids: ...`):

```markdown

## 25. §-builder metric order is load-bearing — the 5-tile cap

`app/components/Section.tsx` renders `metrics.slice(0, 5)` — only a section's
FIRST 5 metrics become KPI tiles. When adding a metric to any builder,
tile-eligible metrics MUST precede prose-feed/context metrics in the list, or a
`slice(0,5)` silently DROPS a real tile (e.g. §02 Reserves) and promotes a
context metric into the tile row. In `bb.py` the order is
`[Policy, SDF, SLF, Call Money, Reserves]` (tiles) then the call-money tenor
points (context); the tenor feed is emitted ONLY when the overnight tile is
present, so a tenor point can never occupy a tile slot. (B3 item 11, 2026-07-10.)
```

- [ ] **Step 3: Confirm the landmine count reference stays consistent**

Run: `grep -nE "landmine" the-brief/CLAUDE.md 2>/dev/null; grep -cE "^## [0-9]+\." AGENTS.md`
Expected: the `grep -c` prints `25`. If `CLAUDE.md` cites a landmine COUNT (e.g. "24 numbered landmines"), bump it to 25 in the same commit; if it only references landmines generically, leave it.

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md the-brief/CLAUDE.md 2>/dev/null || git add AGENTS.md
git commit -m "docs(agents): record 5-tile-cap metric-ordering landmine (25)"
```

---

## Post-plan verification (before opening the PR — not a code task)

Per the spec's ship gate (pipeline-only, handoff §B3):

1. **Live-Supabase render proof** (substitutes the absent `/tmp/brief.env`): a scratchpad script builds a real read-only `MetricHistoryClient` (anon key), runs `bb.build`, and asserts §02 emits `bb_call_money == 9.56` at index 3, `bb_gross_reserves` at index 4, tenor at indices 5–6. Mirrors item 12's `verify_corridor_live.py`.
2. **Adversarial review:** fresh-context Opus reviewer runs its OWN RED proof (revert bb.py, overlay the new tests → they fail) and confirms omit-on-missing + atomic-feed + ordering.
3. **Post-06:30 prod verify** (landmine 17): after the next 06:30 BDT publish, `thebrief.clauding-lab.com` §02 shows an **Overnight Call Money** tile at ~9.56% beside the corridor.
4. **No version bump / CHANGELOG** — deferred to batch all of B3 into one release (matches item 12).

---

## Self-Review (checked against the spec)

**Spec coverage:**
- §2 metrics table (call money tile + 7d/14d) → Tasks 1 & 2. ✓
- §2 order (protects Reserves' slot) → Task 2 Step 1 exact-order assertion + landmine 25. ✓
- §3(a) omit-on-missing → Task 1 `test_call_money_omitted_when_missing_no_fallback`. ✓
- §3(a) atomic feed → Task 2 `test_tenor_omitted_when_overnight_missing`. ✓
- §3(b) prompt deferred → Global Constraints scope fence (no prompt edit in any task). ✓
- §4 no second window call → enforced by `_FakeHistory` (method-less double) in Tasks 1/2; noted Task 2 Step 5. ✓
- §4 cadence/units/source → helper in Task 1 Step 3. ✓
- §5 tests (5 cases) → the 4 new tests + the pre-existing `test_section_emits_expected_metric_ids` (regression guard) covered by Task 1 Step 5 / Task 3 Step 1. ✓
- §6 ship gate → Post-plan verification section. ✓
- §8 item-13 cross-ref (no `metric_definitions` rows) → carried in the spec; no code task here (correct — it's item 13's work). ✓

**Placeholder scan:** none — every code step shows complete code; every run step shows the command + expected result.

**Type consistency:** `_money_market_metric(ctx, *, metric_id, history_id, label) -> Metric | None` defined in Task 1, reused verbatim in Task 2. Metric ids (`bb_call_money`, `bb_call_money_7d`, `bb_call_money_14d`) consistent across tasks and the exact-order assertion. `HistoryRow(id, as_of, value, source)` matches the existing test fixture. ✓
