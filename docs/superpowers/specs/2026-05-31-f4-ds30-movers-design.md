# F4 — DS30 Movers (blue-chip 1-month gainers + losers) — Design

**Status:** approved (brainstorm 2026-05-31, visual companion Option B + price-as-faint-sub).
**Goal:** Add a ranked **DS30 Movers** block to §dse — top 5 1-month gainers and top 5 losers among the 30 DSE blue-chip stocks — rendered full-width below the FIG.02 DSEX chart. Not a Chart.js chart; a tabular ranked list computed at publish time from per-ticker closes.

---

## 1. Context & data availability

- **Per-ticker close data EXISTS** in Supabase `metric_history` as `dse_close_<TICKER>` — exactly the **30 DS30 constituents** (the DSE blue-chip index), 38 trading days present (2026-04-01 → 2026-05-24), same table the SPA charts already read.
- **Blue-chip universe = DS30**, defined upstream in EconDelta (`config/dse_ds30_constituents.json`). The Brief derives the universe self-containedly from the `dse_close_*` metric_ids actually present in `metric_history` — no DS30 list is copied into this repo.
- The existing §dse chart (`fetch_dsex`, `dsexConfig`) is **index-level** (`metric_id=dsex`) and does not touch per-ticker data — F4 is new territory, no overlap.

### The dependency that shapes this design (the freshness gate)
- `dse_close_*` is currently written **only by a one-time backfill** (`econdelta/scripts/backfill_dse_dayend.py`). The **daily** DSE scraper writes index-level metrics only (DSEX, turnover, breadth) — it does NOT iterate the DS30 list. So per-ticker closes are **frozen at 2026-05-24** while the index updates daily.
- **Decision:** build the full Brief side now, verified against the frozen 38-day data, but **gate go-live** so stale per-ticker data never ships. The gate is data-freshness-driven and self-healing (see §5). The EconDelta daily-writer work is the explicit go-live prerequisite and is tracked as a **separate task, out of this F4 scope**.

---

## 2. The block (visual — approved Option B)

- Eyebrow: `DS30 · Movers` … `1-Month` (right-aligned), on a hairline-ruled header.
- **Two columns**, full-width below the FIG.02 chart card: **Gainers** (left, green) | **Losers** (right, red), **up to 5 per side**.
- Each row: **ticker** (primary, mono) + **৳price faint sub** (`--ink-3`, small) + **return %** (right-aligned, `tabular-nums`, tone-colored by sign). Hair-faint divider between rows.
- Column sub-headers `Gainers` / `Losers` tone-tinted. Renders only when `movers` is non-empty.

---

## 3. Data & computation (publish-time, in The Brief)

A new `fetch_dse_movers` in `brief/chart_series_fetcher.py`, mirroring the `fetch_dsex` HTTP pattern:

1. Discover the DS30 universe from `metric_history` (`metric_id like 'dse_close_%'`) — the set of `dse_close_*` ids present (mind the PostgREST 1000-row cap, landmine #14: query distinct ids / bounded slices, not one unbounded pull).
2. For each ticker:
   - `latest` = most-recent close (max `as_of`).
   - `prior` = most-recent close with `as_of <= (latest_as_of − 1 calendar month)` (holiday → falls back to the prior trading day; calendar-month per `dateutil.relativedelta(months=1)` or equivalent).
   - `return_pct = round((latest/prior − 1) * 100, 2)`. **Skip the ticker** if `prior` is missing or `0`.
3. **Gainers** = tickers with `return_pct > 0`, sorted descending, capped at 5. **Losers** = `return_pct < 0`, sorted ascending (most negative first), capped at 5. Exactly-flat (`0`) tickers appear in neither. (Honest in a down month: the gainers column may show fewer than 5 — never a red number under "Gainers".)
4. Return one ordered list: gainers (desc) then losers (asc), each row `{ticker, price, return_pct}` where `price` = the latest close.

**Edge cases:** fewer than 5 on a side → show fewer. Zero valid movers → return `None` (block hidden). Ties on return broken by ticker name (stable, deterministic — no `Math.random`/time).

---

## 4. Schema + migration (code-schema and DB-schema ship together — the `chart_read` lesson, AGENT_LEARNINGS 2026-05-29)

- `brief/v6_schema.py`: new `MoverRowV6(_Lenient)` = `{ ticker: str, price: float, return_pct: float }`; add `movers: Optional[list[MoverRowV6]] = None` to `SectionV6`. (SectionV6 is `_Strict` — the field MUST be declared or it's rejected.)
- **`migrations/0005_section_movers.sql`** (MANDATORY, in this PR): `ALTER TABLE public.sections ADD COLUMN IF NOT EXISTS movers jsonb;` + `COMMENT` + `NOTIFY pgrst, 'reload schema';`. Applied to prod **before** the next publish, or the brief orphans like #118 (PGRST204).
- `brief/v6_publisher.py`: `movers` stays on the `sections` row (JSONB) — it is NOT added to the child-table `exclude={metrics,news,series,notes}` set.

---

## 5. Freshness gate (the go-live mechanism)

In `fetch_dse_movers`, before returning: compute the per-ticker data's latest `as_of` (also queries the `dsex` index's latest `as_of` for the reference) and compare. If the per-ticker data lags the index by **more than `STALE_LAG_DAYS = 4` calendar days** (a single named constant, tunable), return `None` → `section.movers` stays `None` → the SPA renders nothing.

- **Today:** per-ticker frozen 24 May, index current → gated → block hidden in prod. Correct.
- **After EconDelta wires the daily writer:** per-ticker as_of catches up to the index → gate passes → block **auto-activates**, no flag flip, no redeploy.
- **Preview:** the fixture supplies `section.movers` directly (bypassing the fetcher), so the build is fully verifiable now — exactly the F3 fixture pattern.

---

## 6. SPA render

- `types/brief.ts`: `Mover = { ticker: string; price: number; return_pct: number }`; add `movers?: Mover[]` to `Section`.
- `app/components/Section.tsx`: a new full-width block below the chart card, gated on `movers && movers.length`. Partition by sign (`return_pct > 0` → Gainers column desc; `< 0` → Losers column asc).
- `app/globals.css`: `.tb-movers` (two-column grid), `.tb-mover-row` (ticker + faint ৳price sub + return%), reusing the `.tb-kpi-rail` typography vocabulary (eyebrow, `tabular-nums`, `--ink-3` sub, hair dividers, `--bull`/`--bear`). No new design primitives; respects Design.md (no shadows/gradients/animation).

---

## 7. Tests

- `tests/test_fetch_dse_movers.py` (TDD): calendar-month anchor + holiday fallback; skip ticker missing prior/zero; gainers>0 desc / losers<0 asc capping at 5; thin-side (<5) handling; deterministic tie-break; **freshness gate** both states (fresh → returns movers; stale → `None`); the structured-shape (`MoverRowV6`).
- Pipeline dispatch test: §dse stamps `section.movers` from `fetch_dse_movers`; graceful degradation on fetcher exception (mirrors the bb/tbond/fx monthly-branch tests).
- Preview fixture `public/fixtures/f4-preview-2026-05-31.json` with the real DS30 movers; Playwright at 1440 + 390, 0 console errors; verify the gainers/losers columns, faint ৳price sub, tone colors.

---

## 8. Go-live gate (explicit, out of F4 scope)

F4 ships **dark in production** (freshness gate hides it) until EconDelta writes `dse_close_*` daily — promote `backfill_dse_dayend.py` into the daily DSE timer, iterating `dse_ds30_constituents.json`. Tracked as a separate EconDelta task; NOT done under this F4 PR.

---

## 9. Decisions made

- Layout **B** (gainers + losers, two columns), **5 per side**, **full-width below FIG.02**, **৳price as a faint sub** under each ticker.
- **Calendar-month** return (latest close vs most-recent close at/before latest−1 month), not a fixed 22-trading-day lookback.
- Field name **`movers`** (single sorted list; SPA splits by sign), not separate gainers/losers fields.
- Freshness gate is **index-relative** (`STALE_LAG_DAYS = 4`), self-healing; no manual flag.
- Universe derived **from `dse_close_*` ids present in Supabase**, not a copied DS30 list.
- Returns computed **in The Brief** at publish time (not precomputed in EconDelta).

## 10. Rollback / out of scope

- Pre-merge: drop the branch. Post-merge/pre-go-live: the freshness gate already hides the block, so a bad publish shows nothing rather than wrong data; revert the squash commit if needed.
- **Out of scope:** the EconDelta daily `dse_close_*` writer (the go-live prerequisite); any change to the existing §dse DSEX chart; sector/sub-index movers.
