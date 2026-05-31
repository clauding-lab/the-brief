# F3 — FX Flows → "External Flow Balance" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the §fx chart (FIG.01) from a stacked bar reading the buggy daily store into a diverging-area + net-balance line ("External Flow Balance") reading the clean monthly archive.

**Architecture:** Near-exact clone of the F5 yield-ladder change (PR #106, commit `e60c273`). Add a new `metric_history_monthly` fetcher + an explicit `fx` branch in the pipeline's chart-series stamper (removing `fx` from the HTTP dispatch map) + a new Chart.js config that replaces the slug's config. The old daily fetcher/config are retained (still unit-tested) but no longer dispatched. Read `git show e60c273` before starting — every task mirrors it.

**Tech Stack:** Python 3.12 + pytest (pipeline), TypeScript + Next.js 16 + Chart.js 4 (SPA), Supabase REST (`metric_history_monthly`), git + gh + Vercel + Hetzner systemd (deploy).

Spec: [`../specs/2026-05-31-f3-fx-flows-redesign-design.md`](../specs/2026-05-31-f3-fx-flows-redesign-design.md).

---

## Conventions (every task)

- Branch `feat/brief-f3-fx-balance` (already checked out; spec @ `dea9998`, this plan @ HEAD).
- After Python edits: `.venv/bin/pytest` stays green. After TS edits: `npx tsc --noEmit --pretty false` (exit 0) + `npx eslint <file>` (exit 0).
- Conventional Commits. No force-push, no `--no-verify`, no destructive ops.
- Verified metric_ids (must match EXACTLY): `exports_usd_mn_monthly`, `imports_usd_mn_monthly`, `remittance_usd_mn_monthly` — table `metric_history_monthly`, cols `(metric_id, as_of, value)`, USD mn, 171 months each.

---

## Task 1: New monthly fetcher `fetch_fx_balance_monthly` (TDD)

**Files:**
- Create: `tests/test_fetch_fx_balance_monthly.py`
- Modify: `brief/chart_series_fetcher.py`

- [ ] **Step 1: Write the failing test** (clone of `tests/test_fetch_yield_ladder_monthly.py`)

```python
"""Unit test for fetch_fx_balance_monthly (F3 — §fx External Flow Balance)."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from brief.chart_series_fetcher import (
    _FX_BALANCE_MONTHLY_METRIC_IDS,
    fetch_fx_balance_monthly,
)
from brief.history import HistoryRow
from brief.v6_schema import SeriesPointV6


def _row(metric_id: str, as_of: str, value: float) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=date.fromisoformat(as_of), value=value, source="t")


def test_fetch_fx_balance_monthly_returns_three_series_chronological():
    mock = MagicMock()
    # 24 valid month-ends, most-recent-first (PostgREST anchor order).
    months = [f"2025-{m:02d}-01" for m in range(12, 0, -1)] + [f"2024-{m:02d}-01" for m in range(12, 0, -1)]

    def _gw(metric_ids, *, limit=None, days=None, today=None, table="metric_history"):
        return {m: [_row(m, d, 100.0 + i) for i, d in enumerate(months)] for m in metric_ids}

    mock.get_history_window.side_effect = _gw
    result = fetch_fx_balance_monthly(mock, months=24)

    assert set(result.keys()) == set(_FX_BALANCE_MONTHLY_METRIC_IDS)
    assert len(_FX_BALANCE_MONTHLY_METRIC_IDS) == 3
    for mid in _FX_BALANCE_MONTHLY_METRIC_IDS:
        pts = result[mid]
        assert len(pts) == 24
        assert all(isinstance(p, SeriesPointV6) and p.key == mid for p in pts)
        assert pts[0].ts < pts[-1].ts  # chronological oldest-first

    _, kwargs = mock.get_history_window.call_args
    assert kwargs.get("table") == "metric_history_monthly"
    assert kwargs.get("limit") == 24 * 3  # months * 3 ids (landmine #14)
```

- [ ] **Step 2: Run it, confirm it fails**

Run: `.venv/bin/pytest tests/test_fetch_fx_balance_monthly.py`
Expected: FAIL (ImportError: `_FX_BALANCE_MONTHLY_METRIC_IDS` / `fetch_fx_balance_monthly`).

- [ ] **Step 3: Add the constant** (in `brief/chart_series_fetcher.py`, right after `_REMIT_MONTHLY_METRIC_IDS`)

```python
# F3 — §fx external flow balance (metric_history_monthly, USD mn → bn in SPA).
_FX_BALANCE_MONTHLY_METRIC_IDS: tuple[str, ...] = (
    "exports_usd_mn_monthly",
    "imports_usd_mn_monthly",
    "remittance_usd_mn_monthly",
)
```

- [ ] **Step 4: Add the fetcher** (after `fetch_remit_monthly`, before `fetch_yield_curve` — clone of `fetch_remit_monthly`)

```python
def fetch_fx_balance_monthly(
    history_monthly: MetricHistoryClient,
    *,
    months: int = 24,
) -> dict[str, list[SeriesPointV6]]:
    """Pull `months` of exports / imports / remittance from `metric_history_monthly`
    for the F3 §fx External Flow Balance chart (USD mn; SPA converts to bn).

    Multi-series sibling of `fetch_macro_cpi_series`; dict keyed by metric_id,
    chronological (oldest-first). The net basic balance is computed in the SPA
    config, not here.

    AGENTS.md landmine #1: reads metric_history_monthly, NOT tb_* tables.
    AGENTS.md landmine #6: uses the _monthly-suffixed metric IDs.
    AGENTS.md landmine #14: limit is months * len(ids) (per-id, not global).
    """
    grouped = history_monthly.get_history_window(
        _FX_BALANCE_MONTHLY_METRIC_IDS,
        limit=months * len(_FX_BALANCE_MONTHLY_METRIC_IDS),
        table="metric_history_monthly",
    )
    out: dict[str, list[SeriesPointV6]] = {}
    for mid in _FX_BALANCE_MONTHLY_METRIC_IDS:
        rows = grouped.get(mid, [])
        out[mid] = [
            SeriesPointV6(key=mid, ts=r.as_of.isoformat(), value=r.value)
            for r in reversed(rows)
        ]
    return out
```

Do NOT touch the existing `fetch_fx_flows` (daily, unit-tested).

- [ ] **Step 5: Run the test, confirm it passes**

Run: `.venv/bin/pytest tests/test_fetch_fx_balance_monthly.py`
Expected: `1 passed`.

---

## Task 2: Pipeline dispatch — explicit `fx` branch + remove from HTTP map

**Files:**
- Modify: `brief/pipeline_v6.py`
- Modify: `tests/test_pipeline_v6_chart_series_propagation.py`

- [ ] **Step 1: Add the explicit `fx` branch** in `_stamp_chart_series` (place beside the `remit` / `bb` / `tbond` branches, before the `_CHART_FETCHERS_BY_SLUG` lookup)

```python
        # F3 — §fx External Flow Balance, last 24 months (metric_history_monthly).
        # Replaces the daily fetch_fx_flows path (fx removed from the HTTP map below).
        if section.slug == "fx":
            try:
                series_by_id = chart_series_fetcher.fetch_fx_balance_monthly(history_monthly_client)
                section.series = [pt for pts in series_by_id.values() for pt in pts]
            except Exception:  # noqa: BLE001 — graceful degradation
                logger.warning(
                    "v6: fx-balance series fetch failed for slug=fx",
                    exc_info=True,
                )
            continue
```

- [ ] **Step 2: Remove `fx` from the HTTP dispatch map**

In `_CHART_FETCHERS_BY_SLUG`, delete the `"fx": "fx_flows",` line so only `dse` + `iran` remain. Add a one-line comment mirroring the `tbond` note:
```python
    # fx moved to the metric_history_monthly External Flow Balance branch (F3);
    # fetch_fx_flows is retained (unit-tested) but no longer slug-dispatched.
```

- [ ] **Step 3: Run the dispatch tests, see the expected failures**

Run: `.venv/bin/pytest tests/test_pipeline_v6_chart_series_propagation.py`
Expected: failures in the dispatch-map test, `populates_chartable_sections`, `threads_http_and_today`, and the run_publish integration test (all assumed fx was HTTP-dispatched). Fix them in Steps 4–9.

- [ ] **Step 4: Fix the dispatch-map membership test**

In `test_chart_fetchers_by_slug_only_includes_http_dispatched_sections`: change the expected set to `{"dse", "iran"}` and update the docstring to note fx joined the monthly branches.

- [ ] **Step 5: Fix `test_stamp_chart_series_populates_chartable_sections`**

Add an fx point + monkeypatch, mirroring the bb/tbond ones already there:
```python
    fx_pt = SeriesPointV6(key="exports_usd_mn_monthly", ts="2026-03-01", value=3489.8)
    monkeypatch.setattr(
        chart_series_fetcher, "fetch_fx_balance_monthly", lambda *_a, **_k: {fx_pt.key: [fx_pt]}
    )
```
Remove the old `fetch_fx_flows` fx mock and the `by_slug["fx"].series == fx_series` (HTTP) assertion; assert instead `by_slug["fx"].series == [fx_pt]`. Drop `fx` from any "chartless" loop.

- [ ] **Step 6: Fix `test_stamp_chart_series_handles_fetcher_exception_gracefully`**

Add fx to the monthly-branch isolation no-op patches:
```python
    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_balance_monthly", _empty_dict)
```
(The dsex-raises scenario is unchanged.)

- [ ] **Step 7: Extend `test_stamp_chart_series_handles_monthly_branch_exception_gracefully`**

Add fx to the raise+warn coverage: patch `fetch_fx_balance_monthly` to `_raise`; assert `by_slug["fx"].series == []` and that a warning message contains `fx`.

- [ ] **Step 8: Fix `test_stamp_chart_series_threads_http_and_today_to_fetchers`**

fx is no longer HTTP-dispatched. Remove the fx `_record` expectation: there are now **2** HTTP fetchers → `assert len(captured) == 2`. Add `fetch_fx_balance_monthly` to the monthly no-op patches (`_empty_dict`). Update the docstring (HTTP-dispatched = dse/iran). Remove the `fetch_fx_flows` `_record` mock line.

- [ ] **Step 9: Fix `test_run_publish_stamps_chart_series_on_final_brief`** (fx is the subject here)

The brief in this test has an `fx` section. Replace the `fetch_fx_flows` monkeypatch with:
```python
    fx_pt = SeriesPointV6(key="exports_usd_mn_monthly", ts="2026-04-30", value=3489.8)
    monkeypatch.setattr(
        chart_series_fetcher, "fetch_fx_balance_monthly", lambda *_a, **_k: {fx_pt.key: [fx_pt]}
    )
```
Update the assertion that reads the fx section's series to expect `[fx_pt]` (the flattened dict). Read the current test body first and adapt the surrounding setup. **Verify this one carefully.**

- [ ] **Step 10: Update the module docstring** (top of file) so the "fx/dse/iran HTTP-dispatched" line reads "dse/iran HTTP-dispatched; fx joins bb/tbond/macro/remit on the monthly branches."

- [ ] **Step 11: Run the suite, confirm green**

Run: `.venv/bin/pytest tests/test_pipeline_v6_chart_series_propagation.py tests/test_fetch_fx_balance_monthly.py`
Expected: all pass. (The existing `fetch_fx_flows` unit tests stay untouched and green.)

---

## Task 3: SPA chart config `fxBalanceConfig` + wiring

**Files:**
- Modify: `lib/chartConfigs.ts`

- [ ] **Step 1: Add `fxBalanceConfig`** after `fxFlowsConfig`. Reuse the palette keys `fxFlowsConfig` uses (`palette.bull` exports, `palette.ink2` remittance, `palette.bear` imports, `palette.ink` net). Manual cumulative stacking (spec §6 landmine).

```ts
/**
 * fxBalance — F3. External Flow Balance for §fx (FIG.01). Diverging area +
 * bold net-balance line, 24-month, USD bn, read from metric_history_monthly.
 * Inflows (exports + remittance) stack UP via manual cumulative values
 * (remittance dataset = exports+remittance, fill:"-1"); imports drawn as a
 * negative area; net = exports+remittance-imports is the hero line.
 *
 * AGENTS.md landmine: do NOT use scales.y.stacked here — it folds the negative
 * imports area + the overlay net line into the stack and renders wrong. Stack
 * inflows manually (caught in the F3 brainstorm mockup). TimeScale already
 * registered in BriefChart.tsx (landmine #2).
 */
function fxBalanceConfig(ctx: BuildContext): ChartConfiguration<"line"> {
  const EXP = "exports_usd_mn_monthly";
  const IMP = "imports_usd_mn_monthly";
  const REM = "remittance_usd_mn_monthly";
  if (!hasAnyData(ctx.series, [EXP, IMP, REM])) return emptyLineConfig();

  const palette = buildPalette();
  // mn → bn, aligned by ts.
  const toBn = (key: string): XYPoint[] =>
    toPoints(ctx.series[key]).map((p) => ({ x: p.x, y: p.y == null ? null : p.y / 1000 }));
  const exp = toBn(EXP);
  const imp = toBn(IMP);
  const rem = toBn(REM);
  const remByTs = new Map(rem.map((p) => [p.x, p.y ?? 0]));
  const impByTs = new Map(imp.map((p) => [p.x, p.y ?? 0]));
  const inflowTop: XYPoint[] = exp.map((p) => ({ x: p.x, y: (p.y ?? 0) + (remByTs.get(p.x) ?? 0) }));
  const net: XYPoint[] = exp.map((p) => ({ x: p.x, y: (p.y ?? 0) + (remByTs.get(p.x) ?? 0) - (impByTs.get(p.x) ?? 0) }));
  const impNeg: XYPoint[] = imp.map((p) => ({ x: p.x, y: p.y == null ? null : -Math.abs(p.y) }));

  const datasets: ChartDataset<"line", XYPoint[]>[] = [
    { label: "Exports", data: exp, backgroundColor: palette.bull, borderColor: palette.bull, borderWidth: 0.8, fill: "origin", pointRadius: 0, tension: 0.3 },
    { label: "Remittance", data: inflowTop, backgroundColor: palette.ink2, borderColor: palette.ink2, borderWidth: 0.8, fill: "-1", pointRadius: 0, tension: 0.3 },
    { label: "Imports", data: impNeg, backgroundColor: palette.bear, borderColor: palette.bear, borderWidth: 0.8, fill: "origin", pointRadius: 0, tension: 0.3 },
    { label: "Net basic balance", data: net, borderColor: palette.ink, borderWidth: 2.6, fill: false, pointRadius: 0, tension: 0.25, order: 0 },
  ];

  const baseOpts = baseLineOptions({
    legend: true,
    yTicks: { callback: (v: number) => (v < 0 ? "-$" : "$") + Math.abs(v) },
  });

  return {
    type: "line",
    data: { datasets },
    options: {
      ...baseOpts,
      scales: {
        ...baseOpts.scales,
        x: {
          ...baseOpts.scales.x,
          time: { unit: "month" as const, tooltipFormat: "MMM yyyy" },
          ticks: { ...baseOpts.scales.x.ticks, maxTicksLimit: 9 },
        },
      },
    },
  } as unknown as ChartConfiguration<"line">;
}
```

> Note on the backgroundColor fills: `palette.bull/.ink2/.bear` are solid inks. If the areas read too heavy, wrap them in a low-alpha variant the way `fxFlowsConfig`/`brentConfig` already do (check those for the project's alpha helper, e.g. an `rgba`/`withAlpha` util) and match that convention rather than inventing a new one. The zero line is conveyed by the y-axis crossing 0; only add a custom `afterDraw` zero-rule plugin if `BriefChart` passes `config.plugins` through (it constructs `new Chart(canvas, config)`, so an inline `plugins: [...]` on the returned object works) — otherwise rely on the gridline at 0.

- [ ] **Step 2: Register in the `chartConfigs` registry**

Add `fxBalance: fxBalanceConfig,` to the `chartConfigs` object.

- [ ] **Step 3: Repoint the section → chart map**

In `SECTION_TO_CHART`, change `fx: "fxFlows"` → `fx: "fxBalance"`.

- [ ] **Step 4: Update the card head** (keep FIG.01)

```ts
  fx: {
    fig: "01",
    title: "External Flow Balance",
    subtitle: "24-month · inflows vs imports · net basic balance · USD bn",
  },
```

- [ ] **Step 5: Leave `fxFlowsConfig` in place** (retained, unused — F5 precedent). Do not delete it.

- [ ] **Step 6: Typecheck + lint**

Run: `npx tsc --noEmit --pretty false` → exit 0; `npx eslint lib/chartConfigs.ts` → exit 0.
If `XYPoint` null-handling trips `tsc`/eslint, mirror exactly how `fxFlowsConfig` types its `imp` map (it already maps to `{x, y: -Math.abs(v)}`).

---

## Task 4: AGENTS.md landmine

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Add a numbered landmine**

> "Diverging area charts with an overlay line (e.g. `fxBalanceConfig`) must stack inflows via **manual cumulative dataset values + `fill:'-1'`**, NOT Chart.js `scales.y.stacked` — `y.stacked` folds negative areas and overlay lines into the stack and renders wrong (caught in the F3 brainstorm mockup: inflows showed ~$4bn instead of ~$7bn)."

- [ ] **Step 2: Stage AGENTS.md** (it will be committed with the feature commit in Task 5, per the AGENTS.md auto-commit convention).

---

## Task 5: Full verification gate + feature commit

**Files:** all of the above.

- [ ] **Step 1: Typecheck + lint**

Run: `npx tsc --noEmit --pretty false` (exit 0); `npx eslint lib/chartConfigs.ts` (exit 0).

- [ ] **Step 2: Full Python suite**

Run: `.venv/bin/pytest` → confirm exit 0 (no failures; count = prior + 1 new fetcher test).

- [ ] **Step 3: Commit code + tests + landmine as one feature commit**

```bash
git add brief/chart_series_fetcher.py brief/pipeline_v6.py lib/chartConfigs.ts AGENTS.md \
        tests/test_fetch_fx_balance_monthly.py tests/test_pipeline_v6_chart_series_propagation.py
git commit -m "feat(spa+pipeline): F3 §fx External Flow Balance (diverging area + net line) + monthly re-point"
```

---

## Task 6: Preview-before-prod (MANUAL CHECKPOINT — Adnan signs off)

**Files:**
- Create: `public/fixtures/f3-preview-2026-05-31.json` (droppable)

- [ ] **Step 1: Build the fixture** — clone a recent `public/fixtures/*dryrun*.json`; set the `fx` section's `series` to the 24-month exports/imports/remittance points as `{key, ts, value}` in **raw USD mn** (the config divides by 1000). Pull values from Supabase with the same one-liner pattern used for F6/F2/F5 fixtures (anon creds in `.env.local`). `jq empty` it to validate.

- [ ] **Step 2: Commit the fixture as a SEPARATE droppable commit + push + open PR**

```bash
git add public/fixtures/f3-preview-2026-05-31.json
git commit -m "chore(preview): add F3 fixture for §fx External Flow Balance preview"
git push -u origin feat/brief-f3-fx-balance
gh pr create --base main --head feat/brief-f3-fx-balance --title "feat: F3 §fx External Flow Balance (Phase C #4)" --body "<summary + preview path + the FIG.01 before/after + droppable-fixture note>"
```

- [ ] **Step 3: Verify on local dev + the live Vercel branch preview**

Local: ensure the tmux dev server is up; `/preview?fixture=f3-preview-2026-05-31.json`. Vercel: poll the branch-alias URL's fixture path until HTTP 200. With Playwright at **1440** and **390**: confirm the §fx canvas draws, the diverging areas + bold net line render, the net line crosses zero, and **0 console errors**.

- [ ] **Step 4: STOP — present the preview URL + a before/after (old stacked bar vs new balance) and WAIT for Adnan's explicit approval.**

---

## Task 7: Merge (after approval)

- [ ] **Step 1: Drop the preview fixture (no force-push)**

```bash
git revert --no-edit <fixture-commit-sha>
git diff main...HEAD --name-only | grep -i fixture && echo "STILL PRESENT" || echo "clean"
git push
```

- [ ] **Step 2: Squash-merge + delete branch**

```bash
gh pr merge <#> --squash --delete-branch \
  --subject "feat(spa+pipeline): F3 §fx External Flow Balance + monthly re-point (#NN)" \
  --body "Diverging area + net-balance line; re-points §fx to metric_history_monthly. Preview fixture reverted before merge."
```

- [ ] **Step 3: Verify on `origin/main`** — `fxBalanceConfig` present, no `f3-preview` fixture, branch deleted.

---

## Task 8: Deploy (MANUAL CHECKPOINT)

- [ ] **Step 1: Check Hetzner state (read-only)**

```bash
ssh adnan@135.181.43.68 'cd ~/the-brief && git fetch -q origin && echo "behind: $(git rev-list --count HEAD..origin/main)" && git status -s'
```
Confirm the merge won't collide with the local `package-lock.json` edit (F3 doesn't touch it: `git diff <hetzner-HEAD>..main --name-only` excludes it).

- [ ] **Step 2: Pull main on Hetzner (no sudo)**

```bash
ssh adnan@135.181.43.68 'cd ~/the-brief && git pull --ff-only origin main && git log --oneline -1'
```

- [ ] **Step 3: Smoke-test the prod venv import**

```bash
ssh adnan@135.181.43.68 'cd ~/the-brief && .venv/bin/python -c "from brief.chart_series_fetcher import fetch_fx_balance_monthly; from brief import pipeline_v6; print(\"fx in HTTP map:\", \"fx\" in pipeline_v6._CHART_FETCHERS_BY_SLUG)"'
```
Expected: imports OK; `fx in HTTP map: False`. No restart — `brief.timer` fires fresh at 06:30 BDT.

---

## Self-Review

- **Spec coverage:** §3 chart → Task 3; §4 data → Tasks 1+3; §5 implementation → Tasks 1–3; §6 landmine → Tasks 3+4; §7 tests → Tasks 1–2; §8 verify/rollout → Tasks 5–8; §9 decisions → reflected throughout. No gaps.
- **Placeholders:** the PR body text and `<fixture-commit-sha>`/`<#>`/`<#NN>` are runtime values, not design placeholders. All code steps contain complete code.
- **Type consistency:** `fetch_fx_balance_monthly` signature + `_FX_BALANCE_MONTHLY_METRIC_IDS` match across Tasks 1–2 and the test; `fxBalanceConfig` key names match the verified metric_ids and the registry/SECTION_TO_CHART entries.

## Rollback Plan

Pre-merge: drop the branch. Post-merge/pre-deploy: revert the squash commit on `main` (SPA reverts on next Vercel build). Post-deploy: revert on `main` + re-pull Hetzner. The retained `fetch_fx_flows`/`fxFlowsConfig` are NOT a usable fallback (they read the buggy daily source) — rollback = revert, not re-point.
