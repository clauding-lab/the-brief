# B3 Item 11 — §02 Money-Market Line (overnight call money + term premium) — Design

**Status:** approved (brainstorm 2026-07-10). Second of the three remaining B3 items, sequenced **11 → 10 → 13**.
**Goal:** Give §02 "Policy & Rates" the one number it's missing — the **overnight call-money rate** — as a guaranteed KPI tile, and hand the editor the **tenor curve** (7-day / 14-day) as a prose-feed signal so the section can finally say *where money actually trades* and *how comfortable liquidity is*. Pipeline-only: one builder file + its tests. No migration, no SPA change, no new component, no prompt edit.

---

## 1. Context & data availability

- §02 "Policy & Rates (Bangladesh Bank)" is `brief/builders/bb.py`. It currently emits **4 metrics**: `bb_policy_rate`, `bb_sdf`, `bb_slf`, `bb_gross_reserves` (the corridor + reserves, all live from `metric_history` after item 12 / PR #136).
- The frontend renders **at most 5 KPI tiles per section** — `app/components/Section.tsx:189` maps `metrics.slice(0, 5)`. §02 uses 4 of 5 slots, so there is room for **exactly one** more tile.
- The money-market data EXISTS in Supabase `metric_history`, anon-readable, daily-fresh, and is currently **unread by The Brief**. Verified live 2026-07-10 (all `age_days` 0–1):

  | Source id | Value | Role in this design |
  |---|---|---|
  | `call_money_rate` | 9.56% | → **tile** (`bb_call_money`). This *is* the overnight / 1-day rate (`call_money_rate_1d` is identical, 9.56). |
  | `call_money_rate_7d` | 9.41% | → context (prose-feed, no tile) |
  | `call_money_rate_14d` | 11.19% | → context (prose-feed, no tile) |

- **Deliberately dropped** (banker's call, Adnan, 2026-07-10): `crr_utilisation_pct` (5.12%) and `slr_utilisation_pct` (18.81%) are statutory floors every bank maintains by regulation — no signal, so no mention. `interbank_repo_data` (Tk 5,592 cr) is a raw volume with no baseline the reader can interpret — dropped for the same "no signal, no mention" reason. `call_money_rate_90d` (age 9) and the monthly `banking_excess_liquid` / `deposits_held_with_bb_crr` (age 35) are too stale to carry a daily liquidity read.

### The editorial read this surfaces (confirmed by Adnan, the banker)
Overnight money at **9.56%**, sitting *below* the 10.0% policy repo and inside the 7.5–11.5% corridor → **comfortable interbank liquidity** (a push toward SLF 11.5% would signal a squeeze). The **14-day point at 11.19%**, ~1.6pp above the 1-day, is a **term premium** reading as *expected tightening / month-end pressure*, not current stress.

---

## 2. The change (one file: `brief/builders/bb.py`)

Three new reads from `metric_history`, following the `_rate_metric` helper item 12 already established (a small helper or inline reads — implementation-plan detail):

| New metric id | Source id | Label | Unit | Cadence | Tile? |
|---|---|---|---|---|---|
| `bb_call_money` | `call_money_rate` | **Overnight Call Money** | % | daily | **yes (tile #4)** |
| `bb_call_money_7d` | `call_money_rate_7d` | Call Money · 7-day | % | daily | no |
| `bb_call_money_14d` | `call_money_rate_14d` | Call Money · 14-day | % | daily | no |

**Metric order is load-bearing** because the frontend slices the first 5. Final `metrics` list order:

```
[ bb_policy_rate, bb_sdf, bb_slf, bb_call_money, bb_gross_reserves,   ← first 5 = the tiles
  bb_call_money_7d, bb_call_money_14d ]                               ← positions 6–7, editor-only
```

- Call money slots in as **tile #4** — editorially it belongs beside the corridor rates (the reader sees, in one row, the corridor *and* where money trades within it).
- Reserves holds **tile #5**. The tenor points sit *after* Reserves so they can never displace it from the tile row (a `slice(0,5)` that pushed Reserves to position 7 would silently drop it — the trap this ordering avoids).

Section title, id, and `source="BB"` / `source_url` are unchanged.

---

## 3. Two decisions locked (both deliberately diverge from item 12)

### (a) Omit-on-missing — no fallback constant
Item 12's corridor falls back to a hardcoded constant (`_FALLBACK_SDF_PCT` etc.) with `stale=True` when a row is missing — justified because Policy/SDF/SLF are *standing* rates that persist between decisions. **Call money is the opposite: a fast daily rate.** A hardcoded fallback would misrepresent where money trades *today*. So:

> If `call_money_rate` is absent or non-numeric, the builder emits **no** `bb_call_money` metric — §02 gracefully renders its original 4 tiles. The tenor points (`bb_call_money_7d` / `_14d`) are emitted **only when the overnight tile is present** (and each still needs its own live row): the money-market feed is **atomic around the overnight rate**. This keeps the section coherent (no orphan tenor without its headline) *and* **structurally guarantees the tenor points are never tiles** — with the overnight present, the tile-eligible core is 5 (Policy / SDF / SLF / Call Money / Reserves), so any tenor lands at list index ≥ 5, outside `slice(0, 5)`. **No fabricated numbers, ever.**

### (b) Ship builder-only now — editor-prompt nudge deferred
The **tile is a guaranteed win** — it renders from the section data regardless of what the LLM editor does. The **prose liquidity line** depends on the editor choosing to write about the new metrics. Rather than speculatively editing the §02 editor prompt now (a sign-off + LOCKSTEP + dry-run-render item per the 2026-07-04 handoff §B2), we:

1. Ship the data-availability change (this PR, pipeline-only, no sign-off gate).
2. Read the real dry-run render.
3. Add a **targeted §02 prompt nudge only if** the render shows the editor ignoring the tenor signal — as a **separate small sign-off PR** (LOCKSTEP-safe: it asks the editor to *use* data it now has, contradicting no existing rule).

---

## 4. Enrichment & freshness (no new fetch)

- **Sparkline for free.** `brief/pipeline.py:117` collects `all_ids = {every metric id across all sections}` and issues **one** batched `get_history_window` call (line 121), attaching `history_values` to each metric. `bb_call_money` (and the tenor points) join that existing call automatically → the tile gets its sparkline with **no second window call**. Landmine 23 (single-batched-window contract) is respected — the builder itself issues zero history calls.
- **`extras` and `history_facts` are the wrong channels for the tenor curve.** `SectionData.extras` is never serialized into the editor input (`_to_v6_raw`, `pipeline_v6.py:61` omits it). `history_facts` is strictly for *historical* anchors (`brief/history_anchors.py`: `kind` is a fixed Literal — `since_lower` / `vs_period` / `extreme_in_window` …; the editor inlines the phrase verbatim). A *current* cross-sectional term structure fits neither without abusing an abstraction. So the tenor points ride as plain section **metrics** — `_to_v6_raw` serializes `s.metrics` in full (not sliced to 5), so positions 6–7 reach the editor as prose inputs while never rendering as tiles.
- **Freshness.** Each metric carries its real `as_of`; `section_freshness(metrics, today)` decides §02's badge as today. No stale-flag gymnastics — omit-on-missing already covers the failure case. Cadence is `daily`, like the daily-restamped corridor rates (landmine 24 territory: a daily `as_of` is a restamp, not a decision date — but call money genuinely *is* a daily rate, so this is the honest cadence, not a workaround).

### Mis-feature risk (assessed, accepted without a prompt rule)
The editor picks one brief-wide `cover_metric`; a 14-day call-money tenor will not out-rank DSEX / reserves / policy for the Cover, and within §02 the clear labels ("Overnight Call Money" vs "Call Money · 14-day") keep the prose sane. No `is_held_over`-style guard is needed (daily metrics never count as held anyway). If the dry-run render disproves this, it folds into the deferred §02 prompt nudge (3b).

---

## 5. Tests (TDD, behavior-based, RED-proven — item-12 rigor)

`tests/builders/test_bb.py` gains money-market cases, each provable-RED (delete the change → it fails):

1. **Tile present:** with a `metric_history` double returning `call_money_rate=9.56`, `bb.build` emits a `bb_call_money` metric — value 9.56, label "Overnight Call Money", unit "%", `source="BB"`, within the first 5 metrics (renders as a tile).
2. **Tenor context present, non-tile:** `bb_call_money_7d` / `bb_call_money_14d` present with live values at **list `.index() >= 5`** (0-based — i.e. outside `slice(0, 5)`, so never a tile). Assert on list position, not just membership.
3. **Omit-on-missing + atomic feed:** history lacking `call_money_rate` → **no** `bb_call_money` metric **and no tenor metrics even if** `call_money_rate_7d` / `_14d` rows exist; §02 emits its original 4 metrics; no exception. (This is the structural guarantee that a tenor point can never occupy a tile slot.)
4. **No second window call:** reuse the existing single-batched-call invariant — the builder issues no `get_history_window` of its own (the `_FakeHistory` double without `get_history_window` must not crash on `bb.build`; enrichment happens later in the pipeline).
5. **Corridor + reserves untouched:** item-12 assertions (SDF 7.5 live, reserves from `gross_reserves_usd_bn`, `bb_gross_reserves` id preserved) still pass — regression guard that ordering/insertion didn't disturb them.

Full gate: `.venv/bin/pytest -q` → exit 0 (item-12 baseline: 626 passed); `bb.py` stays 100% covered.

---

## 6. Ship gate & verification (pipeline-only)

- **No SPA preview** (brief/*.py produces no meaningful Vercel diff). Gate per handoff §B3: the **no-prod dry-run fixture render** reviewed by Adnan, plus **post-06:30 prod verify** (landmine 17 — the tile appears on prod only after the next 06:30 BDT publish rebuilds §02).
- Substitute the item-12 proof pattern where `/tmp/brief.env` is absent: a live-Supabase anon-key render script that builds a real `MetricHistoryClient`, runs `bb.build`, and prints the §02 metrics (asserts `bb_call_money == 9.56`, tenor points present, order correct).
- **Prod verify (next morning):** `thebrief.clauding-lab.com` §02 shows an **Overnight Call Money** tile at ~9.56% beside the corridor.

---

## 7. Decisions made

- **Form:** call-money tile + prose liquidity line (not a dedicated micro-block, not prose-only). One new tile fills the free 5th slot.
- **Content:** overnight call money (tile) + 7d/14d tenor (prose signal). CRR, SLR, interbank repo **dropped** (no signal / no baseline).
- **(a) Omit-on-missing**, no fallback constant — diverges from item 12; justified by the metric being a fast daily rate.
- **(b) Builder-only now**, §02 editor-prompt nudge deferred to a separate sign-off PR gated on render evidence.
- **Order:** rates+reserves first (5 tiles), tenor context last — protects Reserves' tile slot. Tenor emitted **only alongside the overnight tile** (atomic feed) — structurally guarantees tenor is never a tile.
- Tenor rides as plain metrics (positions 6–7), not `extras` (dead) or `history_facts` (historical-only).

---

## 8. Rollback / out of scope / cross-references

- **Rollback:** pre-merge → drop the branch. Post-merge → omit-on-missing means the worst case is a missing tile, never a wrong number; revert the squash commit if needed.
- **Out of scope:** the §02 editor-prompt nudge (deferred sign-off PR, item 3b); any SPA/CSS change; a call-money DoD delta (would need a week-ago prior → blocked by the single-window contract, same as item 12's reserves delta — the sparkline carries the trend instead).
- **Cross-reference for item 13:** `call_money_rate_7d` / `_14d` (and `bb_call_money`) have **no `metric_definitions` rows**, so `v_metric_freshness` cannot bless them. When item 13 swaps §02's freshness to the view, it must seed definition rows for the metrics this item introduces — noted here so item 13 inherits the list.
