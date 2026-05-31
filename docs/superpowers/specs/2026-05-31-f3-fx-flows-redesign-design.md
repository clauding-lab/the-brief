# F3 — FX Flows → "External Flow Balance" redesign + data re-point

**Date:** 2026-05-31
**Status:** Draft (post-brainstorm, awaiting plan)
**Owner:** Adnan
**Phase:** C (SPA charts), chart #4 — after F6 remittance (#105), F2 reserves + F5 yield ladder (#106)
**Section:** `fx` ("FX & External"), FIG.01

---

## 1. Problem & Goal

The §fx chart (FIG.01) has two problems:

**a) Data bug.** `fetch_fx_flows` reads the **daily** `metric_history` table for ids `monthly_export` / `monthly_remittance` / `monthly_import`, filtered to the last ~12×31 days. The daily store is young (≈ since early May 2026) and these "monthly_*" ids carry daily-revised snapshots, so the chart plots **revision noise**, not clean month-end flows. It is sparse and unreliable.

**b) The visual is a generic stacked bar.** `fxFlowsConfig` is a stacked bar (exports + remittance up, imports down). It does not foreground the one number a banker reads off an external-flows chart: the **net basic balance**, and whether it is above or below water.

**Goal:** Re-point the chart to the clean deep monthly archive (`metric_history_monthly`, back to 2012) **and** redesign it into a **diverging area + net-balance line** ("External Flow Balance", Direction A from the brainstorm). One change fixes the data bug and ships the redesign together.

This follows the F5 pattern exactly: a new monthly fetcher + a new chart config replace the slug's current wiring; the old (unit-tested) fetcher and config are retained but no longer dispatched.

## 2. Out of Scope

- **Removing the old `fetch_fx_flows` / `fxFlowsConfig`.** They stay (still unit-tested). They are simply no longer slug-dispatched. Deleting them + their tests is a separate cleanup, not this change.
- **Changing the §fx KPI / "Latest:" line.** `Section.tsx` shows `metrics[0]` as "Latest:"; for fx that is a section metric, which may differ from the chart's net (the same daily-vs-monthly-vintage nuance as F6). Left as-is for now. (Decision below.)
- **A second axis or dual-scale.** The chart stays single-axis (USD bn), zero-centred.
- **Backfilling new data.** All three series already exist in `metric_history_monthly` (171 months each), verified live.
- **import_cover_months_monthly.** Present in the archive but not part of this flows chart.

## 3. The Chart — "External Flow Balance" (Direction A)

Visual contract (approved in brainstorm via the visual companion):

- **Type:** line chart with area fills, **monthly time x-axis (Chart.js TimeScale)** for consistency with cpiTrend / remitFlow, zero-centred y-axis (negative region used).
- **Window:** 24 months (most recent 24 month-ends).
- **Units:** USD **bn** (archive stores USD mn; divide by 1000 in the config presentation layer).
- **Datasets (draw order matters for fills):**
  1. **Exports** — area, `fill: "origin"` (0 → exports), soft green.
  2. **Remittance** — area, data = **cumulative** `exports + remittance`, `fill: "-1"` (fills down to the exports area), soft slate. This manually stacks the inflows. **Do NOT use Chart.js `scales.y.stacked`** (see §6).
  3. **Imports** — area, data = **negative** (`-imports`), `fill: "origin"` (0 → −imports), soft rust.
  4. **Net basic balance** — line, data = `exports + remittance − imports`, **bold ink, the hero**, `fill: false`, drawn last (`order: 0`), no points.
- **Zero rule:** an emphasized horizontal rule at y = 0 via a small inline Chart.js `afterDraw` plugin defined in the config (as prototyped in the brainstorm mockup), so the surplus/deficit split is unmistakable.
- **Card head (`CHART_CARD_HEADS.fx`):** keep `fig: "01"`; title → **"External Flow Balance"**; subtitle → **"24-month · inflows vs imports · net basic balance · USD bn"**.
- **Legend:** Exports · Remittance · Imports (outflow) · Net basic balance.
- **Tooltip:** per-series; imports shown as a negative `-$X.XXbn`; net shown signed.

**Why this design:** inflows (exports + remittance) stack above zero, imports pull below, and the bold net line is the basic balance crossing zero. On real data the net sits in modest surplus most months but **dipped through zero around Feb-2026** — the knife-edge a banker watches: remittance strength is the only thing holding the external account above water against a structural import bill.

## 4. Data

| Series | metric_id (`metric_history_monthly`) | Role |
|---|---|---|
| Exports | `exports_usd_mn_monthly` | inflow (stacked, bottom) |
| Remittance | `remittance_usd_mn_monthly` | inflow (stacked, top) |
| Imports | `imports_usd_mn_monthly` | outflow (negative area) |
| Net basic balance | *(computed)* exp + rem − imp | hero line |

- Schema: `(metric_id, as_of, value)`; values in USD mn. All three have 171 months (Apr-2024 → Mar-2026 covers the 24-month window; archive goes to ~2012).
- The **net** series is **not** fetched — it is computed in the chart config from the three fetched series, so a missing month in any component is handled once.
- USD-bn conversion (÷1000) happens in the **config** (presentation), not the fetcher. The fetcher returns raw archive values (consistent with `fetch_remit_monthly` / `fetch_reserves_monthly` / `fetch_yield_ladder_monthly`).

## 5. Implementation

Mirrors F5 (tbond) exactly.

**`brief/chart_series_fetcher.py`**
- Add `_FX_BALANCE_MONTHLY_METRIC_IDS = ("exports_usd_mn_monthly", "imports_usd_mn_monthly", "remittance_usd_mn_monthly")`.
- Add `fetch_fx_balance_monthly(history_monthly, *, months: int = 24) -> dict[str, list[SeriesPointV6]]` — clone of `fetch_remit_monthly`: `get_history_window(ids, limit=months*len(ids), table="metric_history_monthly")`, reversed to chronological, keyed by metric_id. (Landmines #1 / #6 / #14.)
- **Keep** `fetch_fx_flows` (daily, unit-tested) untouched.

**`brief/pipeline_v6.py`**
- Add an explicit `fx` branch in `_stamp_chart_series` (mirror the `remit` / `bb` / `tbond` branches): call `fetch_fx_balance_monthly(history_monthly_client)`, flatten `dict.values()` into `section.series`, graceful `try/except` + `logger.warning`, `continue`.
- **Remove** `"fx": "fx_flows"` from `_CHART_FETCHERS_BY_SLUG` (it moves to the explicit monthly branch). After this, the HTTP map holds only `dse` + `iran`.

**`lib/chartConfigs.ts`**
- Add `fxBalanceConfig(ctx)` implementing §3 (manual cumulative stacking; net computed; ÷1000; zero rule; USD-bn ticks).
- Register `fxBalance: fxBalanceConfig` in the `chartConfigs` registry.
- Repoint `SECTION_TO_CHART.fx` from `"fxFlows"` → `"fxBalance"`.
- Update `CHART_CARD_HEADS.fx` title + subtitle (keep `fig: "01"`).
- **Keep** `fxFlowsConfig` (retained, unused) — do not delete.

**`app/components/BriefChart.tsx`**
- No new registration. `fxBalance` uses line + Filler + (Time or Category)Scale — all already registered (landmine #2 satisfied). Use a monthly **TimeScale** x-axis for consistency with cpiTrend / remitFlow (the brainstorm mockup used a category axis for convenience; production uses TimeScale).

## 6. Landmine — manual cumulative stacking (new, numbered for AGENTS.md)

The inflow stack must be built by **manual cumulative values** (remittance dataset data = `exports + remittance`, `fill: "-1"` down to the exports area), **not** Chart.js `scales.y.stacked: true`. With `y.stacked` on, the negative imports area and the overlay net line are also folded into the stack, producing a wrong chart. This was caught in the brainstorm mockup (inflows rendered at ~$4bn instead of the correct ~$7bn). Add as a numbered landmine in `AGENTS.md`.

## 7. Tests

- **New:** `tests/test_fetch_fx_balance_monthly.py` — mirror `test_fetch_yield_ladder_monthly.py`: assert all three series returned, chronological oldest-first, `table="metric_history_monthly"`, `limit == months*3`, keyed by metric_id; assert against `_FX_BALANCE_MONTHLY_METRIC_IDS`.
- **Update** `tests/test_pipeline_v6_chart_series_propagation.py` (same shape as the F5 tbond updates):
  - `_CHART_FETCHERS_BY_SLUG` membership test → now `{dse, iran}`.
  - `populates_chartable_sections` → mock `fetch_fx_balance_monthly`; assert fx populated via the monthly branch (fx leaves the HTTP-mock set).
  - `threads_http_and_today` → now 2 HTTP fetchers (dse, iran); patch `fetch_fx_balance_monthly` to a no-op dict.
  - `handles_*_exception_gracefully` → add fx to the monthly-branch isolation / raise-and-warn coverage.
  - `skips_when_section_absent` → fx is monthly-dispatched now; keep the brief chartless (banking + fiscal).
- **Keep** the existing `fetch_fx_flows` tests green (fetcher retained).
- **TS:** no unit-test runner; `tsc --noEmit` + `eslint` are the gates.

## 8. Verification & Rollout

- `tsc --noEmit` clean · `eslint` clean · full `pytest` green.
- Preview-before-prod (per Adnan's standing rule): build a `/preview?fixture=` fixture with the fx section's `series` set to the 24-month exports/imports/remittance points; verify FIG.01 renders on local + the Vercel branch preview (desktop 1440 + mobile 390, zero console errors); show before/after vs the current stacked bar. Adnan approves the live preview before merge.
- Merge as a squash PR; the preview-fixture commit is reverted before merge (F5/F6 precedent).
- Deploy: the SPA auto-deploys from `main` (Vercel); the chart draws once the Hetzner pipeline pulls `main` and publishes (the `git pull` on `~/the-brief` before the next `brief.timer` fire). No new Python deps.

## 9. Decisions Made (from brainstorm, 2026-05-31)

- **Direction A — diverging balance** (inflows up, imports down, net line) chosen over B (coverage) and C (net-only) via the visual companion. Net line is the hero.
- **24 months · USD bn.**
- **Stacked inflows** (exports + remittance distinct), not a single combined inflow area — keeps the composition (how much remittance is doing the lifting) visible.
- **Replace, don't augment:** `fxBalance` replaces `fxFlows` on §fx; old config/fetcher retained but unused (F5 precedent). No multi-chart container needed.
- **Net computed in the SPA config**, not fetched.
- **§fx KPI / "Latest:" line left as-is** for now (not switched to the net). Revisit only if it reads as a discrepancy in preview.
