# V5 Fidelity Build Plan

**Goal**: bring V5 to V1 visual + functional parity, plus restore §14 executive signals.

**Audience**: future session (likely a fresh agent + Adnan) picking this up cold. Reads as a resume document — has enough context to start without re-deriving decisions.

**Status as of writing (2026-05-02 evening)**:
- Architecture (Option B, EconDelta → Supabase → consumers) shipped tonight.
- DSE/BB history fallback shipped — non-trading-day sections degrade gracefully.
- "§ Section unavailable" diagonal-stripe placeholder shipped — replaces "None" walls.
- Fiscal/remit unit conversions shipped, broken `macro_credit_growth` alias removed.
- Sunday morning auto-publish unblocked.

This plan builds on top of that foundation.

---

## What V5 is missing relative to V1 (the gap)

Source: 5 mockup screenshots Adnan shared on 2026-05-02, archived in
`~/.claude/image-cache/40b98959-fc45-4b46-9275-c88d9933436c/3.png` through `7.png`.

The V1 brief had 9 visual / structural elements that V5 has not yet ported:

1. **Banker quote at top of section** — V5 renders bankerread at the bottom; V1 leads with a pull-quote.
2. **Per-metric AGING chip** — orange pill on stale-but-not-yet-broken metrics.
3. **Source icons in headlines** — colored 2-3-letter lozenges (REU red, DS/TBS/FE/BBC/AJZ black).
4. **§14 executive signals** — V5 dropped Call 2 from `pipeline_v5.py`; section structurally cannot populate.
5. **Sparklines on hero metrics** — small inline SVG trend below the big number.
6. **History-fetch infrastructure** — feeds sparklines AND yield curve. Doesn't exist yet at the pipeline level.
7. **Newspaper-layout headlines (§09)** — full LEAD + KEY POINTS box + right-rail + secondary grid.
8. **Yield curve chart hero (§07 T-Bond)** — line chart of yields across 6 tenors, today vs prior week.
9. **Sector heatmap (§06 DSE)** — 4×2 grid with per-sector %change color coding.

Plus three data gaps that block downstream rendering:

- **NBR decomposition** (§12 still grayed out) — brief expects VAT/IT/Customs separately; we only scrape FYTD total.
- **Macro Credit Growth YoY %** (§03 dropped) — alias removed because no source; need to add scraper.
- **`fy_remittance` supporting card** in §05 — already wired but should verify in render.

---

## The three phases

Each phase is one focused session. Don't combine — context fatigue compounds.

### Phase 1 — Quick wins + foundation (3.5h)

Highest value per hour. All template-only or schema-only changes plus one infrastructure item that unblocks Phase 2.

| Item | Effort | Files touched |
|------|--------|---------------|
| 1.1 Banker quote at top | 30 min | `brief/render/v5/templates/_section_base.py` |
| 1.2 Per-metric AGING chip | 1h | `brief/schema.py`, `brief/cadence.py`, `brief/render/v5/_jsx.py` |
| 1.3 Source icons in headlines | 45 min | new `brief/sources.py`, `brief/render/v5/_jsx.py` |
| 1.4 History-fetch infrastructure | 1h | `brief/pipeline.py` (`gather()`), `brief/schema.py` (`Metric.history_values`) |
| 1.5 Sparklines on hero metrics | 30 min | `brief/render/v5/_jsx.py:metric_hero_card`, `brief/render/v5/styles.css` |

**Acceptance criteria**:
- Visiting a rendered brief shows the banker quote at top of macro/banking/fx (whichever has a bankerread).
- §03 macro CPI Food card shows an `AGING` orange chip when age > monthly tolerance (currently 35 days).
- §09 headlines section shows per-source colored lozenges (REU/DS/TBS/FE/BBC).
- §03 macro CPI Headline hero card shows an inline sparkline (last 14 days).
- Brief test suite still passes (currently 677).

**Implementation notes**:

- **1.1 banker quote at top** — in `_section_base.py:render_section_base`, move `bankerread_html` from after the metric grid to before. May want to retain bottom variant for sections with NO bankerread, OR introduce a new "section variant" enum (`hero_quote_first`, `hero_quote_last`, `chart_hero`) that templates pick. Start simple: always-top, see how it reads.

- **1.2 AGING chip** — compute at render time from `metric.as_of` + `metric.cadence` against tolerance map. Tolerances live in `brief/cadence.py:STALE_THRESHOLDS_HOURS_BY_CADENCE` already (matches EconDelta's). Render as `<span class="metric-aging-chip">AGING</span>` next to the source/date footer. CSS already has `.metric-badge`-style precedent — clone its shape with orange tint.

- **1.3 source icons** — taxonomy: `REU=Reuters` (red bg), `DS=Daily Star` (black), `TBS=The Business Standard` (black), `FE=Financial Express` (black), `BBC=BBC` (black on white), `AJZ=Al Jazeera` (black with amber accent), `FT=Financial Times` (pink/black per FT brand), `BBN=BB news`. Add `brief/sources.py` with a `SOURCE_BADGES: dict[str, dict]` map and a render helper. Hook into `headlines.py` builder to attach `source_code` per `Headline`. Render in `section_headlines.py`.

- **1.4 history fetch** — in `pipeline.gather()`, after `history = _build_history(cfg)`, fetch last 14 days of all known metric_ids in one batched PostgREST call. Build `history_map: dict[metric_id, list[float]]`. Pass into `BuilderContext` as `ctx.metric_history_map`. Add `Metric.history_values: list[float] | None = None` to schema. Builders attach `history_values=ctx.metric_history_map.get(mid)` per metric. Worth caching across renders if running multiple in succession.

- **1.5 sparklines** — `_jsx.py` already has `sparkline_svg(values, w, h)`. In `metric_hero_card`, when `metric.history_values and len(metric.history_values) >= 7`, emit the SVG below the big number. CSS: small max-width, oxblood stroke for hero metrics, ink-2 for supporting.

---

### Phase 2 — Layouts that need new data + chart (7h)

The three "real components" V5 is missing.

| Item | Effort | Files touched |
|------|--------|---------------|
| 2.1 Newspaper headlines layout (§09) | 2.5h | `brief/render/v5/templates/section_headlines.py`, `styles.css`, `brief/headlines.py` curator |
| 2.2 §14 exec signals — restore Call 2 | 1.5h | `brief/pipeline_v5.py`, `brief/render/v5/templates/section_exec.py` |
| 2.3 Yield curve chart hero (§07 T-Bond) | 3h | EconDelta scraper extension + `brief/render/v5/templates/section_tbond.py` + new `_jsx.py:line_chart_svg` |

**Acceptance criteria**:
- §09 renders a LEAD article (1) on the left with a dark KEY POINTS box, 4 right-rail mini-headlines (color-coded by source), 3 secondary headlines bottom row.
- §14 exec section shows 3-5 directional signals ("↑ NPL ratio breached 35% — provisioning gap widens to BDT X cr") with anchor links to relevant sections.
- §07 T-Bond shows the 4 small T-Bill rate cards top, 2 bond rate cards left, large yield curve chart with today vs last-week dotted line.

**Implementation notes**:

- **2.1 newspaper headlines** —
  - **Curator**: Claude `headlines_curation.txt` prompt already exists and outputs 8 categorized headlines. Extend to: `lead: {...}` (1 headline + key_points list of 3), `right_rail: [4 headlines]`, `secondary: [3 headlines]`. Probably add a new prompt variant `headlines_layout_v5.txt` rather than modifying existing.
  - **Template rebuild**: full grid layout. Left column = LEAD article (title 32px serif italic, lede 14px, dark KEY POINTS box with oxblood/amber bullets). Right column = 4 stacked horizontal cards with source-icon + headline + timestamp. Bottom row = 3 horizontal headlines with lede.
  - **CSS** for the dark KEY POINTS box: `background: var(--ink-1); color: var(--paper-2); padding: var(--space-md);` with oxblood `§` glyphs as bullets and amber-on-dark callouts.
  - **Tested**: Adnan's mockup is at `docs/design/v4-map-front-mockup.html` — extract exact CSS values from there. Don't reinvent.

- **2.2 §14 exec restore** —
  - Port the original `Call 2: exec_signals` from `pipeline.py` (lines ~424-441 in current code) into `pipeline_v5.py` as Call 2 between top_picks (Call 1) and todays_call (Call 3).
  - Prompt input: spine sections that are "fresh" or "warning" — use `SPINE_BUILDER_IDS = ("bb", "macro", "fx", "remit", "dse", "tbond", "iranwar", "headlines", "exec")` filtered.
  - Prompt output validates against `validate_signals(allowed_anchors=ALL_BUILDER_IDS)`.
  - Existing prompt at `brief/claude/prompts/exec_signals.txt` may need a V5 refresh — review for newspaper voice consistency.
  - Cost ~$0.30, ~30s per render. Acceptable.
  - Tests: existing `tests/test_pipeline.py` covers Call 2 contract; mirror in `test_pipeline_v5.py`.

- **2.3 yield curve chart** — heaviest item, breaks into 3 sub-tasks:
  - **a) Multi-tenor T-Bill scraper** — currently only 91-day. Same source URL (`bb.org.bd/en/index.php/monetaryactivity/treasury`). LLM extraction via existing hybrid parser; add 3 new indicators in `sources-v3.json` for 182-day, 364-day, 2Y bond. Each gets brief alias.
  - **b) Multi-tenor T-Bond scraper** — 5-year and 10-year BGTB. Same source. Same shape.
  - **c) Yield curve renderer** — new `brief/render/v5/_jsx.py:line_chart_svg(series, x_labels, y_min, y_max, width, height, comparison_series=None)`. Produces inline SVG with axis ticks, gridlines, two-color line series, dot markers per data point. ~150 lines of SVG path generation. Reference: `risk_map.py` already does precision SVG layout — same pattern.
  - **d) `section_tbond.py` template** — restructure into a 6-card-top + chart-bottom grid. Need: dimensions, margins, "YIELD CURVE · BDT GOVT" eyebrow, "APR 17 vs APR 10" delta callout. Mockup is image #5.

---

### Phase 3 — Last data gaps (5-6h, dedicated session)

| Item | Effort | Files touched |
|------|--------|---------------|
| 3.1 Sector heatmap (§06 DSE) — compute from constituents | 3-4h | EconDelta new scraper, `brief/builders/dse.py` extension, `_jsx.py:heatmap_svg` |
| 3.2 NBR decomposition scraper | 2h | EconDelta new indicator(s), brief alias updates |
| 3.3 Macro Credit Growth YoY scraper | 1h | EconDelta new indicator, brief alias re-add |

**Acceptance criteria**:
- §06 DSE shows the 4×2 sector heatmap with per-sector %change color coding (green positive, red negative).
- §12 NBR shows VAT/IT/Customs as 3 separate hero cards with month-over-month trends.
- §03 Macro shows Credit Growth YoY with a real percent value (currently null after we removed the broken alias).

**Implementation notes**:

- **3.1 sector heatmap (option C: compute from constituents)** —
  - **Why option C**: dsebd.org/sector_indices.php returns 404. Option (a) "find a working aggregator" was investigated — the alternatives (LBSL, broker portals) are unstable scraping targets. Option (b) "scrape individual DSE sector indices" requires DSE pages we couldn't reliably load. Option (c) is heavier but doesn't depend on a third party that can break.
  - **Mechanism**: each of the 8 sectors has 30-50 listed scrips. DSE publishes per-scrip daily change (advancing/declining flags + % move). Compute a sector aggregate by averaging weighted-by-market-cap or simple-average of constituent moves.
  - **Scope cut**: simple average is fine for V1 — the heatmap is a directional indicator, not a portfolio analytics tool.
  - **Sub-tasks**:
    - **a)** Static taxonomy: `config/dse_sector_constituents.json` with 8 sectors → list of scrip codes (~250 stocks total). Curate from DSE's published sector listings; commit as data file. Reviewable.
    - **b)** New EconDelta scraper `scrapers/dse_sector_heat.py` — daily; for each scrip in the taxonomy, scrape today's % change from DSE's per-scrip page or the market summary; aggregate by sector with simple average; emit `data["dse_sector_heat"] = {"Banks": -1.4, "NBFI": -1.1, ...}`.
    - **c)** Aggregator `flatten_data()` extension to surface the dict.
    - **d)** Brief render: new `_jsx.py:sector_heatmap_svg(map)` — 4×2 grid of tiles, color intensity proportional to abs(%), green positive / red negative. Wire into `section_dse.py` template.
  - **Risk**: scraping ~250 individual scrip pages per day is heavy. Mitigation: most stocks are in DSE's "Recent Market Information" CSV-style export — one scrape feeds all sectors. Investigate before committing to per-scrip scraping.
  - **Stale handling**: on non-trading day (which is when this matters most for graceful UX), fall back to last-trading-day map from history. Section_dse template already handles `stale=True`.

- **3.2 NBR decomposition** — currently brief expects `nbr_vat_bn`, `nbr_it_bn`, `nbr_customs_bn` separately. EconDelta only has FYTD total. The NBR press releases on TBS/Daily Star occasionally state component breakdowns ("VAT contributed Tk X cr, IT Tk Y cr, customs Tk Z cr"). Use article-discovery flow we already built (similar to `nbr_fytd_collected_*`) but with a different LLM prompt that extracts 3 component figures rather than 1 total. New indicators in `sources-v3.json`. Brief aliases `nbr_vat_bn ← nbr_vat_collected_bn` etc. Effort: ~2h.

- **3.3 Macro Credit Growth YoY** — currently the alias is gone. Two paths:
  - (i) Scrape BB monthly bulletin's "Private sector credit, % YoY" line. The MEI bulletin (publication 3/11) has this. New indicator `private_sector_credit_yoy_pct`. Brief alias `macro_credit_growth ← private_sector_credit_yoy_pct`. ~1h.
  - (ii) Compute from history: `private_sector_credit` 12 months ago vs today, percentage change. Won't work tonight (Supabase has only today's row), but will work in May 2027.
  - Recommend (i) — more robust.

---

## Cross-cutting infrastructure to introduce

These don't deserve their own phase but show up across multiple items. Build inline as needed.

- **`Metric.history_values: list[float]`** — added in Phase 1.4. Sparklines and yield curve both consume.
- **`metric.aging` computed at render time** — Phase 1.2.
- **`brief/sources.py` source taxonomy** — Phase 1.3, also feeds Phase 2.1 newspaper headlines.
- **`_jsx.py:line_chart_svg`** and **`_jsx.py:heatmap_svg`** — added in Phase 2.3 and Phase 3.1 respectively. Both reusable for future sections.
- **Extended `headlines_curation.txt` prompt** — Phase 2.1. Should NOT replace existing — add a new prompt alongside.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Sector heatmap CSV scrape source goes away | Med | High | Fall back to per-scrip scraping (heavier). Cache aggregate aggressively. Stale-fallback for graceful UX. |
| Multi-tenor T-Bond scraper hits Akamai issues | Low | Med | We have working stealth fetcher (`html_fetcher.py`); same source already worked for 91-day. |
| Newspaper headlines layout looks off in different viewport widths | Med | Low | Test 1024 / 1440 / 1920. CSS uses CSS Grid which handles this well. Mockup is at `docs/design/v4-map-front-mockup.html`. |
| §14 exec restore Claude prompt produces low-quality signals | Med | Med | Iterate on the prompt with a few smoke runs. The original V4 prompt is a starting point. |
| Phase 1 banker quote at top breaks sections without a bankerread | Med | Low | Conditional render — only emit the top-of-section quote when section.bankerread exists. |
| History-fetch adds latency to render | Low | Low | One PostgREST batched call. ~200ms. Acceptable. |
| AGING chip math wrong (off-by-one on tolerance) | Low | Low | Unit tests on the cadence-tolerance helper. |

---

## Resume instructions for next session

1. **Read this plan top to bottom** — it's the entry point.
2. **Confirm phasing with Adnan** — the 3 phases are sequenced; no need to revisit unless he changes scope.
3. **Pick a phase**. Start Phase 1 unless Adnan says otherwise.
4. **For each phase**:
   - Create one TaskCreate per item
   - Implement in order (1.1 → 1.2 → 1.3 → ...)
   - Run brief test suite after each item (must stay 677+)
   - Commit per item with descriptive message
5. **End-of-phase verification**: fire a brief render via the standard pattern (env-loaded, `--artifacts-dir /tmp/v5-fidelity-phase{N}`), pull HTML, eyeball against the relevant mockup screenshot.
6. **Don't push to deployed branch (`feat/v4-retarget`)** until phase verification passes. Use a feature branch like `feat/v5-fidelity-phase-1`.

### Where to find context

- **5 V1 mockup screenshots**: `~/.claude/image-cache/40b98959-fc45-4b46-9275-c88d9933436c/` — files `3.png` through `7.png` (image #3 = §03 macro, #4 = §06 DSE, #5 = §07 T-Bond, #6 = §09 headlines, #7 = §11 banking with stale).
- **V4 mockup HTML** (already in repo): `docs/design/v4-map-front-mockup.html` — extract exact CSS values from this for Phase 2.1 newspaper layout.
- **Today's render artefact**: `/tmp/v5-saturday-pm-v4/index.html` (locally on Adnan's Mac) — current state baseline.
- **EconDelta data contract** (cross-repo dependency): `econdelta/docs/data-contract.md`.
- **EconDelta indicator catalog** (101 entries): `econdelta/docs/indicator-catalog.md`.

### What NOT to do

- Don't combine phases into one session.
- Don't replace `_section_base.py` wholesale — extend.
- Don't add the §14 exec call without budget review (~$0.30/render adds up over weekly cron).
- Don't chase pixel-perfect parity with V1 mockups when the V5 newspaper aesthetic is already established. Match the structural elements; let the V5 look take the typography lead.
- Don't ship Phase 3.1 sector heatmap without the option-C constituent taxonomy committed first. Without it, the scraper has nothing to aggregate.

---

## Time budget

| Phase | Effort | When |
|-------|--------|------|
| Phase 1 | 3.5h | Session A |
| Phase 2 | 7h | Session B (split into 2.1+2.2 morning, 2.3 afternoon if needed) |
| Phase 3 | 5-6h | Session C |
| **Total** | **~16h** | 3 sessions |

This is sized for Adnan + agent collaboration at his typical pace. A more autonomous agent might compress; allow buffer for unforeseen scraping work.

---

## Out of scope

These are interesting but explicitly NOT V5 fidelity work. Defer to dedicated plans:

- **Mobile-first redesign** — V5 is primarily desktop-paper aesthetic. Mobile work is a separate effort.
- **Print stylesheet** — V1 had a print CSS; V5 doesn't. Real demand is unclear.
- **Email digest variant** — different output format, different concern.
- **Real-time / push-style updates** — V5 is daily morning publish. Real-time is a different system.
- **Per-user customization** — V5 is one-shape-for-all. Multi-tenant is a future concern.
- **Metric forecast / extrapolation** — analytical layer. Out of scope for the brief.

These can be revisited once V5 ships at full V1 fidelity.
