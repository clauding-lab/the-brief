# The Brief · V4 Retarget Decisions

**Date:** 2026-04-23
**Supersedes:** render target in `docs/superpowers/specs/2026-04-21-the-brief-redesign.md` §4 (renderer) and §7 (section inventory).
**Complements:** `docs/superpowers/plans/2026-04-21-brief-redesign-part1-foundations-through-render.md` (Part 1 plan — Phases 1–3 untouched; Phase 4 renderer retargeted per this doc).

This addendum freezes the 55 sub-decisions taken across 13 design questions comparing the trimmed spec's existing render target against the `The Brief v4 · Map Front` design handoff. It is the source of truth for the V4 renderer.

---

## 1. Layout

### Rendered order (top → bottom)

1. **Dateline** — live oxblood ticker strip (V4 new)
2. **Masthead + Today's Call** — V4 split layout: giant serif headline on left, editor's note on right
3. **Risk Map + Detail pane** — 2D scatter (movement today × significance for the book), click-to-reveal detail pane (V4 new)
4. **Flow Index** — 12 sections in map-implied read order, 2 rows × 6 columns (V4 new)
5. **§01 Major News Headlines** — kept from current, moved from its V4 position (§09) to just after the front door
6. **§02 Bangladesh Bank** (Policy & rates)
7. **§03 Banking Sector**
8. **§04 Dhaka Stock Exchange**
9. **§05 T-Bill & T-Bond**
10. **§06 BDT/USD FX & Reserves**
11. **§07 Macroeconomic Indicators**
12. **§08 Domestic Food Prices (DAM)**
13. **§09 Global Commodities**
14. **§10 Remittances**
15. **§14 US–Iran War Impact**
16. **§15 Fiscal & Budget**
17. **§16 NBR Tax Revenue**
18. **Colophon** — V4 oxblood-bordered footer

**Absorbed:** §00 Executive Summary is absorbed into Today's Call (no standalone section).

**Cut from current 17:** §11 RMG, §12 International Trade & LDC, §13 US Tariff Impact, §17 Power & Energy, §18 Regional Peers.

**Cut from trimmed spec's Keep-list:** §12 Trade and §13 Tariff (user re-confirmed exclusion on 2026-04-23).

**Total numbered sections rendered:** 13 (§01 + §02–§10 + §14 + §15 + §16). **Total front-door blocks:** 4 (Dateline + Masthead/Call + Risk Map + Flow Index).

---

## 2. Visual system

- **Fonts:** Source Serif 4 (variable, opsz 8–60, weights 400/600/700/900 + italic) for display; Inter (400/500/600/700) for body and chrome; JetBrains Mono (400/500/600) for numbers, labels, dates.
- **Colors:**
  - Paper: `--paper #f7f3e9`, `--paper-2 #ede7d6`, `--paper-3 #e0d9c3`
  - Ink: `--ink #171310` through `--ink-4 #a29785`
  - Signature: `--ox #6b1f27`, `--ox-2 #8a2a33`, `--ox-ink #2a0a0f`, `--ox-wash #f3e4e3`
  - Semantic: `--up #2f6b3a`, `--down #a8322a`, `--warn #b57a15`, `--watch #2a4d7a`, each with soft `-bg` variant
  - Gold: `#f4c95d` for dateline pulse dot and BankerRead highlights
- **Paper-light only** — no dark mode toggle.
- **Noise texture:** SVG `feTurbulence` at 0.05 opacity applied to `<body>`.
- **Spacing tokens:** `--pad-col 28px`, `--pad-row 22px`, `--h-gap 64px`. Compact-density override: 18 / 14 / 40.

---

## 3. Section header

- Big oxblood numeral in Source Serif 4 weight 900 at 92–140px, **no `§` prefix** — just `02`, `03`, etc.
- **No emoji icons** anywhere in section headers.
- Mono-uppercase kicker label (e.g. `POLICY & RATES`) below the numeral.
- Serif-bold 30–42px italic-emphasized title (e.g. `The Governor held.` *`Again.`* — where the italic word is in `--ink-2` for emphasis).
- Italic Source Serif 4 dek, 15px, max 64ch.
- Meta pills aligned right: cadence pill + source + date in mono.
- **Per-section pull quote** below the header: oxblood left border, Source Serif 4 italic 22–30px, large `"` glyph decoration, `cite` line with `BankerRead · §NN Section`.

---

## 4. Metric card anatomy

- **Staleness dot** top-left: `.fresh` (green), `.warn` (amber ring), `.stale` (amber ring), `.pending` (blue).
- **Mono label** uppercase, 10.5px, `.14em` letter-spacing.
- **Cadence pill** top-right: `daily` (green border), `weekly` (watch-blue border), `monthly` (ink-2 border), `event` (oxblood border), `pending` (watch-blue fill).
- **Value:** mono tabular-nums 30px for regular, **Source Serif 4 bold 56–84px** for hero variant.
- **Delta line:** mono 12px with `▲` / `▼` / `–` prefix, colored by direction.
- **Inline sparkline:** 12-point SVG line, 140×32 regular / 220×42 hero, stroke color matches delta direction.
- **Optional note:** Inter 12.5px, `--ink-2`, max 50ch.
- **Next-release pill:** shows on `pending` state with `Next release MMM D`.
- **Foot:** optional `Stale` or `Aging` pill + source + `· asOf`.
- **Hero variant:** spans `grid-column: span 2`, paper-2 background, 3px oxblood left border, thin soft rule on top/right/bottom.

---

## 5. BankerRead

- **Structured variant (§02–§08 and §14–§16):** 4 required fields — `meaning`, `action`, `trigger`, `focus` — rendered as `§A`, `§B`, `§C`, `§D` with mono gold labels. §A gets a 52px oxblood serif drop cap on its first letter.
- **Free-form variant (§01 Headlines only):** single paragraph, same dark card chrome.
- **Card chrome:** `#14110e` background, 4px oxblood left border, gold-italic "BankerRead" label, subtle `rgba(232,223,201,0.14)` separators, "Jump to §NN" anchor link in foot.
- **Placement:** inline per-section only. No toggle. No consolidated bottom `§10 BankerRead` block.
- **Dedicated `pull` field** — a 1-line oxblood pull quote separate from the 4 structured fields, used at the top of each section.

---

## 6. Charts

| Chart | Behaviour | Data source |
|---|---|---|
| Per-metric sparkline (12pt) | Inline inside every `Metric` card | `metric_history` (new builder-owned table, last-12 tail) |
| Yield Curve (6 tenors: 3M/6M/1Y/2Y/5Y/10Y + prev-week dashed) | §05 T-Bond section | Keep existing Supabase `tb_yieldcurve_history` |
| Oil chart (12 sessions + event pins IAEA/OPEC+/Hormuz) | §14 section | Keep `tb_oil_history` for line; event pins **hardcoded** in `brief/builders/iranwar.py` (editor-curated per edition) |
| DSE Breadth numerals (74/162/58 advancing/declining/unchanged) | §04 DSE | New scrape method in `brief/builders/dse.py` from DSE website |
| Sector Heat (8-tile heatmap: Banks/NBFI/Textile/Pharma/Fuel/Telecom/Food/IT) | §04 DSE | New scrape method in `brief/builders/dse.py` |
| LNG | Demoted to a `Metric` card only (no standalone chart) | `metric_history` |
| T-Bill (as standalone) | Rolled into Yield Curve (removed as dedicated chart) | — |

**Risk flag on DSE scrapes:** per prior session notes, BB/DSE are ASN-blocked from Hetzner VPS. DSE breadth + sector heat must **graceful-degrade** to "§ Section Unavailable" card if scrape fails. Builder returns a `degraded=True` SectionData in that case.

---

## 7. Headlines (§01) section

- V4 3-tier layout:
  - **Lead story (`hl lead`):** oxblood top border 3px, source badge (oxblood on ink bg) + source name + "Lead" marker aligned right, Source Serif 4 bold 30px headline with italic-oxblood emphasis on key phrase, secondary dek, **KeyPoints dark card** (ink-black bg, oxblood left border, gold "Key points · for the book" header, 3 bullets with oxblood `§` glyph markers and gold-highlighted key phrases), timestamp.
  - **Right column (`grid-23`):** 4 compact `hl` items — badge + name + 19px serif headline + time, no deks, no emphasis.
  - **Bottom row (`grid-3`):** 3 medium `hl` items — badge + headline + short dek + time.
- **Total 8 stories per edition** (curated, not the 20 in current).
- **BankerRead kept at bottom** but free-form (not 4-field structured) — the one exception in the schema. Single paragraph across all headlines.

---

## 8. Miscellaneous UI chrome

- **Navigation:** no top dropdown bar. Jumps happen via Flow Index click, Risk Map dot click (detail pane has `Jump to §NN ↓` link), and per-BankerRead `Jump to §NN` anchor.
- **Tweaks panel** (floating bottom-right): kept in the V4 React source but **stripped from production render** per §10 below. Only active inside Claude.ai Design edit mode.
- **Section Unavailable state:** **keep current behaviour** — render the section with `n/a` values in Metric cards plus a `FreshTag` date marker. Do **not** use V4's dashed-border `unavail` card treatment.
- **Colophon footer:** V4 treatment — `3px double` oxblood top border, mono 3-column row: brand (oxblood) + source list + next edition timestamp.
- **Staleness surface:** via the staleness dot and pill-in-foot on every Metric card. No standalone FreshTag per section (FreshTag only surfaces on §-unavailable sections per the exception above).

---

## 9. Risk Map · Flow Index · Today's Call

### Risk Map

- **12 dots** covering all numbered sections **except §01 Headlines** (Headlines is a content stream, not plottable).
- Axes: X = movement today 0–10, Y = significance for the book today 0–10.
- 4 quadrant backgrounds (slow/structural, active/material, dormant, noise) with soft paper fills.
- Dot types (color): `event` (oxblood), `fresh print` (green), `slow/structural` (amber), `anchor` (ink).
- Dot radius `r` is also a per-section editorial call.
- Positions, types, and radii emitted by a **new Claude call** — see §10.
- **Mobile:** simplified render — smaller dots, tighter grid, no axis labels, no quadrant captions. Minimum viewport width supported: 390px (iPhone 17).

### Flow Index

- **12 entries** (same set as Risk Map — all numbered sections except §01 Headlines).
- Layout: 2 rows × 6 columns on desktop, responsive breakpoints at 4 cols (900px) and 2 cols (560px).
- Each entry: ranked numeral (oxblood serif italic 28px), mono kicker (`§NN · Section`), serif 14.5px one-line section title.
- Click-to-scroll to the corresponding section.
- Order is emitted by the same Claude call as the Risk Map layout.

### Today's Call

- Editorial paragraph in the upper-right of the Masthead block, `grid-template-columns: 1.55fr 1fr`.
- **2–3 sentences, ~55 words** max.
- Source: **new Claude call** — see §10.
- Signed: `— Desk Editor · The Brief`.

---

## 10. Claude call roster (5 total)

All calls run against `claude -p` on the Max subscription via `brief/claude/max_client.py` subprocess wrapper.

| # | Call | Input | Output contract | Fallback on failure |
|---|---|---|---|---|
| 1 | `headlines_curation` | All scraped headlines + per-section SectionData summary + lead-nominee list | Lead `headline_id` + ordered `right_column[4]` + `bottom[3]` + per-lead `keypoints[3]` strings | Render all scraped headlines unordered, no lead emphasis |
| 2 | `exec_signals` | All SectionData | `exec_signals: List[{kind, text, anchor, num}]` — 5–7 entries | Skip signals; Today's Call still renders |
| 3 | `bankerread_insights` | All SectionData (spine + keep) + today's `exec_signals` | Per section: `{meaning, action, trigger, focus, pull}` (structured) for §02–§08, §14–§16; `{text}` (freeform) for §01 Headlines | Drop the BankerRead aside + pull quote for that section; section still renders |
| 4 | `risk_map_layout` | **NEW.** All SectionData (12 plottable sections) + `bankerread_insights` output + `exec_signals` output | Per section: `{x: 0-10, y: 0-10, r: 20-50, type: event\|fresh\|slow\|anchor, hero_metric_id: str\|null}`. Plus `read_order: List[section_id]` (12 entries, ordered) | Python computes deterministic `(x, y, type)` from freshness + \|delta\|; no hero anywhere (zero-hero grids); read_order sorted by \|delta\| descending |
| 5 | `todays_call` | **NEW.** All SectionData + `bankerread_insights` output + `risk_map_layout` output | `{text: str (<=55 words, 2-3 sentences), byline: "Desk Editor · The Brief"}` | Use the lead-position section's (highest y × x) BankerRead `pull` string as the Today's Call text |

Prompt files are named `brief/claude/prompts/<call>.txt`. A `bankerread_stale.txt` variant already exists in the Part 1 plan; no new stale variants are added in this retarget (fallback handling covers stale/fail cases).

---

## 11. Schema deltas from Part 1 plan

Part 1 plan defines `brief/schema.py` with Pydantic models. The V4 retarget needs:

- `BankerReadInsight` → **discriminated union** by `kind` literal:
  - `structured`: `meaning, action, trigger, focus, pull` (all str, all required)
  - `freeform`: `text, pull` (text required, pull optional)
- New `MapCoord` model: `section_id: str, x: float (0-10), y: float (0-10), r: int (20-50), type: Literal["event","fresh","slow","anchor"], hero_metric_id: str | None`.
- New `TodaysCall` model: `text: str (max ~55 words validated at ~400 chars), byline: str`.
- `Metric` → add `hero: bool = False` (populated from `risk_map_layout` output at render time — not at build time).
- `SectionData` → add `pull: str | None = None` (populated from `bankerread_insights` output).
- `RunResult` → add `map_coords: List[MapCoord]`, `todays_call: TodaysCall`, `read_order: List[str]`.

---

## 12. Timing conventions

Per user-global rule: **all times displayed in BDT (UTC+6), never UTC**. Oil chart's `Apr 21 05:00 GMT` label becomes `Apr 21 11:00 BDT`.

Date format tokens standardized:

| Context | Token | Example |
|---|---|---|
| Masthead title | `DDD DD MMM YYYY` | `Tue 21 Apr 2026` |
| Section meta (event date) | `MMM D` | `Apr 17` |
| Intraday times | `HH:MM BDT` | `06:15 BDT` |
| Monthly print | `MMM 'YY` | `Mar '26` |
| Colophon next-edition | `DD MMM · HH:MM BDT` | `22 Apr · 06:15 BDT` |

---

## 13. Production polish

- **Motion:** V4 restraint only — the dateline's gold dot pulses (`pulse` 2s infinite). All other animations: hover-background swaps on exec-item / flow-idx / readfirst li, nothing else. No scroll reveals. No micro-interactions on Metric cards.
- **Edit-mode artifacts:** strip all `EDITMODE-BEGIN` / `EDITMODE-END` markers, the `TWEAK_DEFAULTS` block, the `__edit_mode_*` postMessage listeners, and the `Tweaks` React component from production render. The renderer emits a clean shell with no dev-tool hooks.
- **Fallback policy:** see §10 "Fallback on failure" column. Every call has a defined degrade path; no call is allowed to abort the pipeline.

---

## 14. Distribution (email)

- The Brief's existing Brevo email path is retained.
- Email version is a **plain-text digest**, not a render or screenshot. Recipient sees:
  - Today's Call (full 55-word paragraph + byline)
  - Top 3 `exec_signals` entries (text + anchor URL)
  - Lead headline (title + source + link)
  - A single `Full edition →` deep-link to the hosted HTML.
- No inline images, no inline HTML rendering, no attached PDF.

---

## 15. Mobile render differences

- Minimum supported viewport: **390px** (iPhone 17 standard).
- Risk Map: simplified SVG (smaller dots, tighter axes, no quadrant captions) below 760px.
- Masthead: stacks to single column; title first, Today's Call below.
- Flow Index: 2 columns (from 2×6 desktop → 6×2 mobile).
- Metric grids: 2-col at 900px, 1-col at 560px (CSS already present in V4 source).
- Headlines: single column, lead first, then 4 compact, then 3 with deks.
- Tweaks panel (if ever shown): full-width bottom sheet. Moot in production since stripped.

---

## 16. Non-changes (preserved from Part 1 plan)

To be explicit about what this addendum does *not* change:

- `brief/schema.py` core types (`Metric`, `SectionData` shapes stay — only the additions above).
- `brief/cadence.py` — untouched.
- `brief/econdelta.py` reader — untouched.
- `brief/history.py` Supabase client — untouched (still writes `metric_history` per Part 1).
- `brief/headlines.py` scraper port — untouched.
- Builder files for §02–§16 — existing content stays. Only two additions: `dse.py` gains breadth + sector-heat scrape methods; `iranwar.py` gains a hardcoded `OIL_EVENTS` constant.
- Phase 1 (scaffolding), Phase 2 (builders), Phase 3 (Claude integration for existing 3 calls) from the Part 1 plan — **execute as written**. Phase 3 gains 2 additional tasks for calls 4 and 5; see Part 1B plan.
- Phase 4 (Renderer) from the Part 1 plan — **replaced in full** by Part 1B's renderer phase.

---

## 17. Open items deliberately NOT decided in this addendum

Moved to Part 2 ops plan or later:

- `pdfjs-dist` 3.x → 5.x bump (unrelated to render work).
- Final migration of charts from `tb_*` to `metric_history` (deferred to post-shadow-soak).
- DSE scrape reliability against ASN-block — gracefully degrades if blocked; root-cause fix is a separate workstream.
- `oil_events` curation workflow (manual editorial for now; can automate later).
- Whether the §01 Headlines BankerRead voice should evolve to structured as well over time.
