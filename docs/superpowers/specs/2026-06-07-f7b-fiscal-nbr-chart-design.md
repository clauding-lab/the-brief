# F7b — NBR monthly-trend chart in The Brief §Fiscal

**Date:** 2026-06-07
**Status:** Approved design (pre-implementation)
**Author:** Claude (directed by Adnan)
**Repo:** the-brief — branch `feat/f7b-fiscal-nbr-chart` (worktree `.worktrees/f7b-fiscal-nbr`, cut from `origin/main` because local `main` is diverged + the checkout is shared).
**Scope:** Add ONE monthly-trend chart (NBR tax revenue) to the §Fiscal section. Borrow + ADP charts and any multi-chart architecture are explicit non-goals.

---

## Context

EconDelta backfilled monthly fiscal data into Supabase `metric_history_monthly` (PR #72, 2026-06-07): `nbr_revenue_monthly_cr` (28 months Jul'23→Oct'25, single-month BDT crore, clean), plus provisional `govt_bank_borrow_monthly_cr` and annual `adp_completion_pct_annual`.

The Brief's **§Fiscal section today renders headline CARDS only** (no chart): "Govt bank borrow YTD: BDT 0.92tn", "NBR collected YTD: BDT 2.88tn", fed by 4 `fiscal_*` metrics (YTD-trillions / target / ADP%) that come from a **separate external pipeline (MoF/IMED/BB), not EconDelta**. EconDelta's `*_monthly_cr` ids are referenced **nowhere** in the Brief — so this is **net-new, clean-slate wiring** with no conflict with the existing cards.

The Brief's chart pipeline already reads `metric_history_monthly` for 5 sections (CPI, remit, reserves, yield, fx) via a consistent `fetch_*_monthly` pattern. `SECTION_TO_CHART` is strictly **1:1** (one section → one chart). Adding a single chart fits that pattern with zero schema change. (Three charts would need a multi-chart redesign — deferred.)

---

## Goal

The §Fiscal section gains its first time-series chart: a single **line** showing NBR single-month tax revenue across the ~28 available months (Jul'23→Oct'25, BDT crore). The existing fiscal cards are untouched. Complements the "where we are now (YTD)" cards with "the monthly trend."

---

## Design

(File:line references are from the 2026-06-07 map; verify at implementation — they may have shifted.)

### 1. Data fetch — `brief/chart_series_fetcher.py`
Mirror `fetch_remit_monthly` (the canonical single-metric monthly fetcher):
```python
_FISCAL_MONTHLY_METRIC_IDS: tuple[str, ...] = ("nbr_revenue_monthly_cr",)

def fetch_fiscal_monthly(history_monthly: MetricHistoryClient, *, months: int = 30
                         ) -> dict[str, list[SeriesPointV6]]:
    grouped = history_monthly.get_history_window(
        _FISCAL_MONTHLY_METRIC_IDS,
        limit=months * len(_FISCAL_MONTHLY_METRIC_IDS),
        table="metric_history_monthly",
    )
    out: dict[str, list[SeriesPointV6]] = {}
    for mid in _FISCAL_MONTHLY_METRIC_IDS:
        rows = grouped.get(mid, [])
        out[mid] = [SeriesPointV6(key=mid, ts=r.as_of.isoformat(), value=r.value)
                    for r in reversed(rows)]
    return out
```
`months=30` covers all 28 available with headroom. Single-metric now; the tuple makes adding borrow/ADP later a one-line change.

### 2. Pipeline wiring — `brief/pipeline_v6.py` `_stamp_chart_series`
`V5_TO_V6` already maps `fiscal` (ord 8, group "policy") but never stamped series for it. Add a fiscal branch alongside the other `metric_history_monthly` branches (macro/remit/bb/tbond/fx):
```python
if section.slug == "fiscal":
    try:
        s = chart_series_fetcher.fetch_fiscal_monthly(history_monthly_client)
        section.series = [pt for pts in s.values() for pt in pts]
    except Exception:
        logger.warning("fiscal chart series fetch failed", exc_info=True)
```
Graceful degradation: on failure, `section.series` stays empty → the SPA hides the chart slot; the cards still render.

### 3. Chart builder — `lib/chartConfigs.ts`
Add a `fiscalNbr` builder mirroring `remitFlow` (single line, month x-axis, BDT-crore y-formatter, `hasAnyData()` guard → `emptyLineConfig()`). Wire:
- register `fiscalNbr` in the `chartConfigs` registry;
- `SECTION_TO_CHART["fiscal"] = "fiscalNbr"`;
- `CHART_CARD_HEADS["fiscal"] = { fig: "09", title: "NBR Tax Revenue", subtitle: "Monthly · BDT crore" }` (FIG.09 = next available).

Confirm the Chart.js scales the builder uses are already registered in `BriefChart.tsx` (the existing line charts use the same Category/Linear scales, so no new registration expected).

### 4. Behavior
- Cards **kept** (separate `fiscal_*` data path); chart **added**.
- `Section.tsx`'s `series.length > 1` chart-enable gate is satisfied by the 28 points → chart renders.
- The chart shows NBR's seasonality (the June fiscal-year-end spike — 52,720 vs ~28k typical).

---

## Testing (TDD)

- **Python** — `tests/test_fetch_fiscal_monthly.py` (mirror `test_fetch_reserves_monthly`): asserts it calls `get_history_window` with `table="metric_history_monthly"` + correct limit, returns a dict keyed by metric_id, output chronological (oldest-first). Plus a pipeline assertion that §fiscal ends with ≥1 series point when the fetcher returns data.
- **TS** — `fiscalNbr` builder test: a fixture series → assert valid `ChartConfiguration` with a non-empty dataset; empty series → `emptyLineConfig()`.

---

## Safety / deployment

- Implement in the isolated worktree off `origin/main` (diverged local main + shared checkout — the concurrent-checkout landmine).
- **AGENTS landmine #17 (re-point blank-until-publish):** a chart re-point renders blank on live until the next 06:30 BDT auto-publish. Deploy pre-window or trigger a manual publish post-merge, then verify the live chart renders.
- **AGENTS landmine #18 (new section field needs migration first):** N/A here — no schema change (1:1 chart, no new JSONB field).

---

## Non-goals

- Borrow + ADP charts (follow-on; borrow needs the provisional caveat, ADP is annual/sparse).
- The multi-chart-per-section architecture (`Section.charts[]` / array-valued `SECTION_TO_CHART`).
- The existing `fiscal_*` headline cards (untouched).
- The noted `fiscal.py` `get_latest` table-default discrepancy (the builder may read `metric_history` while cadence is `monthly`) — **flagged, not fixed here** (separate concern; the cards currently render, so not blocking).

---

## Rollout

1. TDD the fetch → pipeline branch → builder + wiring (this branch).
2. Local verify: Python tests + TS build/test green; a local pipeline dry-run shows §fiscal `series` populated.
3. PR → merge → deploy with the publish-timing mitigation → verify the live chart on the Brief.
