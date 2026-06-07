# F7b — NBR Monthly-Trend Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one line chart (NBR single-month tax revenue, ~28 months from `metric_history_monthly`) to The Brief's §Fiscal section via the existing 1:1 `SECTION_TO_CHART` pattern.

**Architecture:** Three layers, mirroring the existing `remit` chart end-to-end: (1) a Python fetcher `fetch_fiscal_monthly` reads `nbr_revenue_monthly_cr` from `metric_history_monthly`; (2) a fiscal branch in `pipeline_v6._stamp_chart_series` stamps the series onto the §fiscal section; (3) a TS `fiscalNbr` builder in `lib/chartConfigs.ts` renders the line, wired via `SECTION_TO_CHART` + `CHART_CARD_HEADS`. No schema change. The §Fiscal headline cards are untouched.

**Tech Stack:** Python 3 (pytest), TypeScript/Next.js 16 (Chart.js, eslint, `next build`). NOTE: this repo has **no TS unit-test runner** (`package.json` scripts = `build: next build`, `lint: eslint`) — the TS builder is verified by typecheck (`next build`) + `eslint`, plus the Python pipeline test proves the data flow. Do NOT add vitest/jest (YAGNI + match conventions).

**Spec:** `docs/superpowers/specs/2026-06-07-f7b-fiscal-nbr-chart-design.md`
**Worktree / branch:** `.worktrees/f7b-fiscal-nbr` on `feat/f7b-fiscal-nbr-chart` (off `origin/main`). Run all commands from the worktree root.

**Verify gates:**
```
python -m pytest tests/test_fetch_fiscal_monthly.py tests/test_pipeline_v6_chart_series_propagation.py -q
npx eslint lib/chartConfigs.ts
npx next build      # typechecks the TS (no separate tsc script)
```

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `brief/chart_series_fetcher.py` | Supabase series fetchers | Add `_FISCAL_MONTHLY_METRIC_IDS` + `fetch_fiscal_monthly` (mirror `fetch_remit_monthly`) |
| `brief/pipeline_v6.py` | Stamp chart series onto sections | Add a `fiscal` branch in `_stamp_chart_series` (mirror the `fx` branch) |
| `lib/chartConfigs.ts` | Chart.js config builders + maps | Add `fiscalNbrConfig` (mirror `remitFlowConfig`); register it; `SECTION_TO_CHART["fiscal"]`; `CHART_CARD_HEADS["fiscal"]` (FIG.09) |
| `tests/test_fetch_fiscal_monthly.py` | Unit test for the fetcher | Create (mirror `test_fetch_remit_monthly.py`) |
| `tests/test_pipeline_v6_chart_series_propagation.py` | Pipeline stamping test | Update: §fiscal moves from chartless→chartable |

---

## Task 1: `fetch_fiscal_monthly` (Python fetcher)

**Files:**
- Modify: `brief/chart_series_fetcher.py` (add tuple after `_REMIT_MONTHLY_METRIC_IDS` line 46; add function after `fetch_remit_monthly` line 442)
- Create: `tests/test_fetch_fiscal_monthly.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_fetch_fiscal_monthly.py`:

```python
"""Unit test for fetch_fiscal_monthly (F7b — §fiscal NBR monthly chart)."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from brief.chart_series_fetcher import fetch_fiscal_monthly
from brief.history import HistoryRow
from brief.v6_schema import SeriesPointV6


def _row(metric_id: str, as_of: str, value: float) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=date.fromisoformat(as_of), value=value, source="t")


def test_fetch_fiscal_monthly_returns_chronological_series_from_monthly_table():
    mid = "nbr_revenue_monthly_cr"
    mock = MagicMock()

    def _get_history_window(metric_ids, *, limit=None, days=None, today=None, table="metric_history"):
        # PostgREST anchor mode returns most-recent-first; mock 10 months desc.
        return {
            m: [_row(m, f"2025-{x:02d}-01", 22000.0 + x * 100) for x in range(10, 0, -1)]
            for m in metric_ids
        }

    mock.get_history_window.side_effect = _get_history_window

    result = fetch_fiscal_monthly(mock, months=30)

    assert mid in result
    pts = result[mid]
    assert len(pts) == 10
    assert all(isinstance(p, SeriesPointV6) and p.key == mid for p in pts)
    # Output is chronological (oldest-first) regardless of PostgREST desc ordering.
    assert pts[0].ts < pts[-1].ts

    # Reads metric_history_monthly with a per-id limit (landmines #1, #14).
    _, kwargs = mock.get_history_window.call_args
    assert kwargs.get("table") == "metric_history_monthly"
    assert kwargs.get("limit") == 30  # months * 1 id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fetch_fiscal_monthly.py -q`
Expected: FAIL — `ImportError: cannot import name 'fetch_fiscal_monthly'`

- [ ] **Step 3: Add the metric-id tuple** — in `brief/chart_series_fetcher.py`, immediately after the line `_REMIT_MONTHLY_METRIC_IDS: tuple[str, ...] = ("remittance_usd_mn_monthly",)`:

```python
_FISCAL_MONTHLY_METRIC_IDS: tuple[str, ...] = ("nbr_revenue_monthly_cr",)
```

- [ ] **Step 4: Add the fetcher** — in `brief/chart_series_fetcher.py`, immediately after `fetch_remit_monthly` (after its closing `return out`):

```python
def fetch_fiscal_monthly(
    history_monthly: MetricHistoryClient,
    *,
    months: int = 30,
) -> dict[str, list[SeriesPointV6]]:
    """Pull `months` rows of monthly NBR tax revenue from `metric_history_monthly`
    for the F7b §fiscal chart (single-month figures, BDT crore).

    Single-series sibling of `fetch_remit_monthly`; returns a dict keyed by
    metric_id with chronological (oldest-first) SeriesPointV6 lists. months=30
    covers the ~28 backfilled months (Jul'23..Oct'25) with headroom.

    AGENTS.md landmine #1: reads metric_history_monthly, NOT tb_* tables.
    AGENTS.md landmine #6: uses the _monthly/_cr-suffixed EconDelta metric ID.
    AGENTS.md landmine #14: limit is months * len(ids) (per-id, not global).
    """
    grouped = history_monthly.get_history_window(
        _FISCAL_MONTHLY_METRIC_IDS,
        limit=months * len(_FISCAL_MONTHLY_METRIC_IDS),
        table="metric_history_monthly",
    )
    out: dict[str, list[SeriesPointV6]] = {}
    for mid in _FISCAL_MONTHLY_METRIC_IDS:
        rows = grouped.get(mid, [])
        out[mid] = [
            SeriesPointV6(key=mid, ts=r.as_of.isoformat(), value=r.value)
            for r in reversed(rows)
        ]
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_fetch_fiscal_monthly.py -q`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add brief/chart_series_fetcher.py tests/test_fetch_fiscal_monthly.py
git commit -m "feat(fiscal): fetch_fiscal_monthly — NBR monthly series from metric_history_monthly"
```

---

## Task 2: Pipeline fiscal branch + propagation test

**Files:**
- Modify: `brief/pipeline_v6.py` (`_stamp_chart_series`, after the `fx` branch — its `continue` at line 429)
- Modify: `tests/test_pipeline_v6_chart_series_propagation.py` (flip §fiscal chartless→chartable in two tests + docstring)

- [ ] **Step 1: Update the failing test first** — in `tests/test_pipeline_v6_chart_series_propagation.py`, make these four edits to `test_stamp_chart_series_populates_chartable_sections`:

(a) Add the fiscal mock point next to the others (after the `remit_pt = ...` line):
```python
    fiscal_pt = SeriesPointV6(key="nbr_revenue_monthly_cr", ts="2025-03-01", value=32245.0)
```
(b) Add the monkeypatch next to the other monthly ones (after the `fetch_remit_monthly` monkeypatch block):
```python
    monkeypatch.setattr(
        chart_series_fetcher, "fetch_fiscal_monthly", lambda *_a, **_k: {fiscal_pt.key: [fiscal_pt]}
    )
```
(c) Add the chartable assertion (after `assert by_slug["remit"].series == [remit_pt]`):
```python
    assert by_slug["fiscal"].series == [fiscal_pt]
```
(d) Remove `"fiscal"` from the chartless loop tuple, so it reads:
```python
    for slug in ("headlines", "banking", "comm"):
```
Also update the docstring's "Chartless:" line (around line 418) to drop `fiscal` and add a "fiscal (F7b NBR)" entry to the monthly-archive list.

- [ ] **Step 2: Isolate fiscal in the exception test** — in `test_stamp_chart_series_handles_fetcher_exception_gracefully`, add to the `_empty_dict` monkeypatch block (next to `fetch_macro_cpi_series`):
```python
    monkeypatch.setattr(chart_series_fetcher, "fetch_fiscal_monthly", _empty_dict)
```

- [ ] **Step 3: Run the tests to verify they FAIL**

Run: `python -m pytest tests/test_pipeline_v6_chart_series_propagation.py::test_stamp_chart_series_populates_chartable_sections -q`
Expected: FAIL — `by_slug["fiscal"].series == [fiscal_pt]` fails because the pipeline doesn't stamp fiscal yet (fiscal series is still `[]`).

- [ ] **Step 4: Add the fiscal branch** — in `brief/pipeline_v6.py` `_stamp_chart_series`, immediately after the `fx` branch's `continue` (line 429), before the `fn_suffix = _CHART_FETCHERS_BY_SLUG.get(...)` line:

```python
        # F7b — §fiscal NBR monthly tax-revenue line (metric_history_monthly).
        if section.slug == "fiscal":
            try:
                series_by_id = chart_series_fetcher.fetch_fiscal_monthly(history_monthly_client)
                section.series = [pt for pts in series_by_id.values() for pt in pts]
            except Exception:  # noqa: BLE001 — graceful degradation
                logger.warning(
                    "v6: fiscal series fetch failed for slug=fiscal",
                    exc_info=True,
                )
            continue
```

- [ ] **Step 5: Run the tests to verify they PASS**

Run: `python -m pytest tests/test_pipeline_v6_chart_series_propagation.py -q`
Expected: PASS (all tests in the file green)

- [ ] **Step 6: Commit**

```bash
git add brief/pipeline_v6.py tests/test_pipeline_v6_chart_series_propagation.py
git commit -m "feat(fiscal): stamp NBR monthly series onto the §fiscal section"
```

---

## Task 3: `fiscalNbr` chart builder + wiring (TypeScript)

**Files:**
- Modify: `lib/chartConfigs.ts` (add `fiscalNbrConfig` after `remitFlowConfig` line 1072; register in `chartConfigs`; add `SECTION_TO_CHART["fiscal"]`; add `CHART_CARD_HEADS["fiscal"]`)

> No TS unit-test runner exists; this task is verified by `eslint` + `next build` (typecheck) and, end-to-end, by the live render after deploy (Task 5).

- [ ] **Step 1: Add the builder** — in `lib/chartConfigs.ts`, immediately after `remitFlowConfig` (after its closing `}` at line 1072):

```typescript
/**
 * fiscalNbr — F7b. ~28-month monthly NBR tax-revenue line (BDT crore) for
 * §fiscal. Reads nbr_revenue_monthly_cr from section.series. Single-series,
 * newspaper-thin (mirrors remitFlow). Y-axis = BDT crore, X-axis = monthly
 * TimeScale (already registered in BriefChart.tsx per AGENTS.md landmine #2).
 *
 * NB: the §fiscal headline cards ("NBR collected YTD") come from a different
 * external pipeline (fiscal_*_trn, YTD); this chart plots EconDelta's
 * single-MONTH figures, so its scale/latest differ by design — the subtitle
 * flags the monthly basis.
 */
function fiscalNbrConfig(ctx: BuildContext): ChartConfiguration<"line"> {
  const KEY = "nbr_revenue_monthly_cr";

  if (!hasAnyData(ctx.series, [KEY])) {
    return emptyLineConfig();
  }

  const palette = buildPalette();

  const datasets: ChartDataset<"line", XYPoint[]>[] = [
    {
      label: "NBR revenue (monthly)",
      data: toPoints(ctx.series[KEY]),
      borderColor: palette.ink,
      borderWidth: 1.8,
      pointRadius: 0,
      tension: 0.25,
      fill: false,
    },
  ];

  const baseOpts = baseLineOptions({
    legend: false,
    yTicks: { callback: (v: number) => Number(v).toLocaleString() },
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
          ticks: { ...baseOpts.scales.x.ticks, maxTicksLimit: 8 },
        },
      },
    },
  } as unknown as ChartConfiguration<"line">;
}
```

- [ ] **Step 2: Register the builder** — in the `chartConfigs` registry object (line 1211-1222), add after `reserves: reservesConfig,`:

```typescript
  fiscalNbr: fiscalNbrConfig,
```

- [ ] **Step 3: Map the section to the chart** — in `SECTION_TO_CHART` (line 1230), add after `remit: "remitFlow",`:

```typescript
  fiscal: "fiscalNbr",
```

- [ ] **Step 4: Add the card-head metadata** — in `CHART_CARD_HEADS` (line 1252), add after the `remit: {...}` entry (FIG.08 `bb` is the current highest, so fiscal = FIG.09):

```typescript
  fiscal: {
    fig: "09",
    title: "NBR Tax Revenue",
    subtitle: "Monthly · BDT crore",
  },
```

- [ ] **Step 5: Verify lint + typecheck pass**

Run: `npx eslint lib/chartConfigs.ts`
Expected: no errors.

Run: `npx next build`
Expected: build succeeds (TS typechecks `fiscalNbrConfig`, the registry key `fiscalNbr`, and `ChartConfigKey` union all resolve). If `toPoints` / `XYPoint` / `buildPalette` are not in scope where you added the function, confirm you placed it within the same module section as `remitFlowConfig` (they share file-scope helpers).

- [ ] **Step 6: Commit**

```bash
git add lib/chartConfigs.ts
git commit -m "feat(fiscal): fiscalNbr chart builder + SECTION_TO_CHART + FIG.09 card head"
```

---

## Task 4: Full verify

**Files:** none (verification only)

- [ ] **Step 1: Python suite (no regressions)**

Run: `python -m pytest -q`
Expected: all pass (the two fiscal-touching files green; nothing else regressed).

- [ ] **Step 2: Lint + build**

Run: `npx eslint . && npx next build`
Expected: clean lint; successful build.

- [ ] **Step 3: Commit any fixups**

```bash
git add -A && git commit -m "chore(fiscal): lint/build fixups for F7b NBR chart" || echo "nothing to commit"
```

---

## Task 5 (OPERATIONAL — PR + deploy + live verify)

> Not a code-subagent task. The Brief deploys on Hetzner; a chart re-point renders **blank on live until the next 06:30 BDT auto-publish** (AGENTS landmine #17) — so deploy pre-window or trigger a manual publish, then confirm the live render.

- [ ] **Step 1: Open the PR** for `feat/f7b-fiscal-nbr-chart` → `main`. Confirm CI/build green.
- [ ] **Step 2: Merge**, deploy to Hetzner (`ssh` + `git pull origin main` per the-brief AGENTS deploy flow), and **trigger a manual publish** (or deploy before 06:30 BDT) so the chart isn't blank until the next auto-publish.
- [ ] **Step 3: Live verify** — load the Brief, confirm the §Fiscal section now shows the NBR monthly line (FIG.09, ~28 points Jul'23→Oct'25, the June year-end spikes visible) AND the existing YTD cards still render.
- [ ] **Step 4: Update auto-memory / AGENT_LEARNINGS** with the F7b outcome + the §Fiscal cards-vs-chart data-lineage distinction (cards = external fiscal_*_trn YTD; chart = EconDelta monthly_cr).

---

## Self-Review

- **Spec coverage:** fetch (T1), pipeline branch (T2), builder + wiring + FIG.09 (T3), cards-untouched (no edit to fiscal.py — verified by scope), graceful degradation (T2 try/except), TDD (T1/T2 tests; TS via build+lint per repo reality — a noted, justified deviation from the spec's "TS builder test" since there's no TS runner), deploy landmine #17 (T5). All spec sections map to a task.
- **Placeholder scan:** none — every code step has complete code; no TBD/TODO.
- **Type consistency:** `_FISCAL_MONTHLY_METRIC_IDS` / `fetch_fiscal_monthly(history_monthly, *, months=30) -> dict[str, list[SeriesPointV6]]`, builder `fiscalNbrConfig(ctx: BuildContext) -> ChartConfiguration<"line">`, registry key `fiscalNbr`, `SECTION_TO_CHART["fiscal"]="fiscalNbr"`, metric id `nbr_revenue_monthly_cr` — used consistently across T1-T3 and both tests.
