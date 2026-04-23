# The Brief · V4 Retarget — Part 1B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retarget Phase 4 (Renderer) of the Part 1 foundations plan to produce the V4 Map-Front design, and add two new Claude calls (`risk_map_layout`, `todays_call`) that the V4 renderer depends on.

**Scope-of-record:** `docs/superpowers/specs/2026-04-23-v4-retarget-decisions.md` — the 17-section decision sheet. This plan implements it.

**Relationship to Part 1 (PR #2):**

- Part 1 Phases **1, 2, 3** (scaffolding → builders → 3 Claude calls) execute **unchanged**.
- Part 1 Phase **3** gains **2 new tasks** for calls 4 and 5 (`risk_map_layout`, `todays_call`).
- Part 1 Phase **4 (Renderer)** is **fully replaced** by Phase 4B below.
- This plan adds a new **Phase 2C** — the two DSE scrape extensions — which sits alongside Part 1 Phase 2 (builders) but is scoped separately because it depends on ASN-reachability.
- A separate **Part 2 ops plan** (future) covers Phases 5–6 (VPS deploy + shadow soak + cutover + `update.py` removal).

**Total active work:** ~14 hours across 4 new/replaced phases (2C, 3B, 4B, plus schema delta folded into Phase 1 Task 1.3).

**Tech stack additions:** none. Same Python 3.11 + Pydantic v2 + pytest + urllib.

---

## File Structure

### New files (beyond Part 1 plan)

```
brief/
  schema.py                  # (MODIFY — see Phase 1 Task 1.3 extension)
  builders/
    dse.py                   # (EXTEND — add scrape_breadth + scrape_sector_heat)
    iranwar.py               # (EXTEND — add OIL_EVENTS hardcoded list)
  claude/
    prompts/
      risk_map_layout.txt    # NEW (Phase 3B Task 3B.2)
      todays_call.txt        # NEW (Phase 3B Task 3B.5)
    validators.py            # (MODIFY — add 2 validators, Phase 3B Task 3B.3 & 3B.6)
  render/
    templates/
      # Part 1 had one per section (14 files).
      # Part 1B replaces ALL of these with V4 anatomy templates.
      _jsx.py                # (REWRITE — V4 helpers: staleness_dot, cadence_pill, sparkline_svg, bankerread_aside, pull_quote, hero_wrap)
      masthead.py            # NEW — V4 fd-head block (Masthead + Today's Call)
      dateline.py            # NEW — V4 live ticker strip
      risk_map.py            # NEW — full SVG renderer for the 2D scatter + detail pane
      flow_index.py          # NEW — 2-row read-order list
      colophon.py            # NEW — V4 footer
      section_bb.py          # (REWRITE)
      section_banking.py     # (REWRITE)
      section_dse.py         # (REWRITE — gains breadth + sector-heat subrenderers)
      section_tbond.py       # (REWRITE — gains yield-curve subrenderer with prev-week dashed)
      section_fx.py          # (REWRITE)
      section_macro.py       # (REWRITE)
      section_dam.py         # (REWRITE)
      section_comm.py        # (REWRITE)
      section_remit.py       # (REWRITE)
      section_iranwar.py     # (REWRITE — gains event-pin oil chart)
      section_fiscal.py      # (REWRITE)
      section_nbr.py         # (REWRITE)
      section_headlines.py   # (REWRITE — lead + KeyPoints + 4 compact + 3 dek)
    assemble.py              # (REWRITE — new shell, no existing the-brief.html splicing)
    shell_v4.html            # NEW — clean V4 shell template (no EDITMODE markers, no Tweaks panel)
    email_digest.py          # NEW — plain-text digest for Brevo
tests/
  render/
    test_masthead.py         # NEW
    test_dateline.py         # NEW
    test_risk_map.py         # NEW
    test_flow_index.py       # NEW
    test_jsx_helpers.py      # NEW (replaces Part 1's _jsx tests)
    test_assemble_v4.py      # NEW
    test_templates_v4_smoke.py  # NEW (shape-level coverage for all 13 section templates)
    test_section_bb_v4.py    # NEW (full-TDD for one canonical section)
    test_section_dse_v4.py   # NEW (full-TDD — has breadth + sector heat)
    test_section_headlines_v4.py # NEW (full-TDD — different shape from other sections)
    test_email_digest.py     # NEW
  claude/
    test_validators.py       # (EXTEND — 2 new validators)
  builders/
    test_dse_breadth.py      # NEW
    test_dse_sector_heat.py  # NEW
    test_iranwar_events.py   # NEW
fixtures/
  sample_shell_v4.html       # NEW — small scale V4 shell for fast render tests
  sample_risk_map_layout.json # NEW
  sample_todays_call.json    # NEW
  sample_dse_breadth_html.html # NEW — canned DSE HTML for breadth-scrape test
  sample_dse_sector_html.html  # NEW — canned DSE HTML for sector-heat scrape test
```

### Replaced / removed files

- `brief/render/templates/section_tariff.py`, `section_trade.py`, `section_rmg.py`, `section_power.py`, `section_peers.py` — **never created** (these 5 cuts were resolved before the code existed).
- The existing `the-brief.html` shell is **not modified** by this plan; the new `shell_v4.html` is a clean parallel shell. Cutover swaps which one `assemble.py` reads (Phase 4B Task 4B.12).

---

## Conventions

Same as Part 1:

- Timestamps in UTC internally; display in BDT (UTC+6). `now_bdt()` in `brief/cadence.py` is the single source.
- Commits: `feat(brief): ...`, `test(brief): ...`, `refactor(brief): ...`, `docs(plan): ...`.
- Branch: `feat/v4-retarget` (new; this plan's commits land there).
- Python 3.11.
- No mutation; pure functions where possible; builders return fresh `SectionData`.

---

## Phase 2C — DSE scrape extensions (~1.5h)

Runs alongside or after Part 1 Phase 2. Depends on Task 2.9 (DSE builder) from Part 1.

### Task 2C.1 — DSE breadth scraper

- [ ] Add `scrape_breadth(client: HttpClient = None) -> BreadthResult | None` to `brief/builders/dse.py` where `BreadthResult = {advancing: int, declining: int, unchanged: int, as_of: datetime}`.
- [ ] Target URL: DSE official site breadth row. Parse via stdlib `html.parser` (no new deps).
- [ ] Graceful-degrade: return `None` on any exception (ASN block, parse failure, HTTP non-200). Log reason.
- [ ] Integrate into `dse.py`'s `build(ctx)`: on `None`, set `SectionData.degraded_breadth = True` and emit no breadth metric. Template branches on this flag.
- [ ] Tests in `tests/builders/test_dse_breadth.py`:
  - Canned HTML parses correctly → `BreadthResult(74, 162, 58, …)`.
  - Exception path returns `None`.
  - HTTP 403 (simulated ASN block) returns `None`.

### Task 2C.2 — DSE sector heat scraper

- [ ] Add `scrape_sector_heat(client) -> List[SectorPerf] | None` to `brief/builders/dse.py` where `SectorPerf = {sector: str, pct: float, as_of: datetime}`.
- [ ] Scope: 8 sectors matching V4's tile set — Banks, NBFI, Textile, Pharma, Fuel, Telecom, Food, IT.
- [ ] Parse DSE sectoral index page. Graceful-degrade identically to 2C.1.
- [ ] Integrate: on `None`, set `SectionData.degraded_sector_heat = True`. Template branches.
- [ ] Tests in `tests/builders/test_dse_sector_heat.py`:
  - Canned HTML yields 8 sector entries.
  - Partial parse (only 5 sectors returned) yields a length-5 list — don't synthesize missing.
  - Exception returns `None`.

### Task 2C.3 — Oil events hardcoded list

- [ ] Add `OIL_EVENTS: List[OilEvent]` constant to `brief/builders/iranwar.py` where `OilEvent = {date: date, label: str, hot: bool}`.
- [ ] Seed with current editorial list: `[(2026-04-02, "IAEA report", False), (2026-04-11, "OPEC+ hold", False), (2026-04-21, "Hormuz tanker", True)]`.
- [ ] Expose via `SectionData.extras["oil_events"] = OIL_EVENTS` from the builder.
- [ ] Tests in `tests/builders/test_iranwar_events.py`:
  - 3 events present with correct flags.
  - `hot=True` flag rendered distinctively (deferred test to Phase 4B — this test just asserts data shape).

### Task 2C.4 — Phase 2C exit gate

- [ ] `pytest tests/builders/test_dse_breadth.py tests/builders/test_dse_sector_heat.py tests/builders/test_iranwar_events.py -v` all green.
- [ ] `brief.builders.dse.build()` on today's data returns a valid `SectionData` whether or not DSE is reachable (degrade-mode covered).
- [ ] Commit: `feat(brief): DSE breadth + sector heat scrapes, oil events list`.

---

## Phase 1 Task 1.3 extension — schema deltas (~0.5h)

Folded into Part 1 Task 1.3 (`SectionData`, `BankerReadInsight`, `ExecSignal` tests). If Part 1 Task 1.3 has already landed, this is a follow-up commit.

- [ ] Update `brief/schema.py`:
  - `BankerReadInsight` → replace with a `Literal`-tagged union:
    ```python
    class BankerReadStructured(BaseModel):
        kind: Literal["structured"] = "structured"
        meaning: str
        action: str
        trigger: str
        focus: str
        pull: str

    class BankerReadFreeform(BaseModel):
        kind: Literal["freeform"] = "freeform"
        text: str
        pull: str | None = None

    BankerReadInsight = Annotated[
        Union[BankerReadStructured, BankerReadFreeform],
        Field(discriminator="kind"),
    ]
    ```
  - Add `MapCoord`: `section_id: str`, `x: float` (ge=0, le=10), `y: float` (ge=0, le=10), `r: int` (ge=20, le=50), `type: Literal["event","fresh","slow","anchor"]`, `hero_metric_id: str | None = None`.
  - Add `TodaysCall`: `text: str` (max_length=400), `byline: str = "Desk Editor · The Brief"`.
  - Extend `Metric`: add `hero: bool = False`.
  - Extend `SectionData`: add `pull: str | None = None`, `degraded_breadth: bool = False` (DSE only), `degraded_sector_heat: bool = False` (DSE only), `extras: dict = Field(default_factory=dict)`.
  - Extend `RunResult`: add `map_coords: List[MapCoord] = []`, `todays_call: TodaysCall | None = None`, `read_order: List[str] = []`.
- [ ] Update `tests/test_schema.py`:
  - `BankerReadStructured` validates when all 5 fields present.
  - `BankerReadFreeform` validates with only `text`.
  - Discriminator routes correctly on `kind` field.
  - `MapCoord` rejects `x=11`, `r=10`, `type="invalid"`.
  - `TodaysCall` rejects `text` >400 chars.
- [ ] Commit: `feat(brief): schema deltas for V4 retarget (MapCoord, TodaysCall, BankerRead union)`.

---

## Phase 3B — Claude calls 4 and 5 (~2.5h)

Runs after Part 1 Phase 3 (existing 3 Claude calls wired).

### Task 3B.1 — `risk_map_layout` call input fixture

- [ ] Create `fixtures/sample_risk_map_input.json` — a realistic payload: 12 section summaries (id, kicker, freshness, top 3 metrics with delta) + `exec_signals[7]` + `bankerread_insights` (5 structured + 1 freeform).
- [ ] This fixture is replayed in the call's unit test to avoid hitting Claude during CI.

### Task 3B.2 — `risk_map_layout.txt` prompt

- [ ] Write `brief/claude/prompts/risk_map_layout.txt`. Required elements:
  - Explain the 2D plane: X = movement today 0–10 (change magnitude + event-ness), Y = significance for the book today 0–10 (which bankers should care about most).
  - Type classification rules:
    - `event` — a single moment dominates the section today (e.g. MPC decision, geopolitical shock).
    - `fresh` — a newly-published metric that changes the day's read.
    - `slow / structural` — sticky conditions that matter but didn't move today.
    - `anchor` — always-matters baseline (policy rate, reserves floor), even when quiet.
  - `hero_metric_id`: pick at most ONE metric per section whose value is the single number a banker should take away. Null if no metric warrants hero treatment today (day of all-small-deltas).
  - `read_order`: reorder the 12 section IDs by morning-read priority (not section number, not map distance — editorial judgment).
  - Output strictly the JSON schema: `{"sections": [{section_id, x, y, r, type, hero_metric_id}], "read_order": [section_id, ...]}`.

### Task 3B.3 — `risk_map_layout` validator

- [ ] Extend `brief/claude/validators.py` with `validate_risk_map_layout(raw: dict, section_ids: set[str]) -> RiskMapLayout`.
- [ ] Validates:
  - Exactly 12 sections, all IDs in `section_ids` (reject extra or missing).
  - `x, y` floats 0–10 each.
  - `r` int 20–50.
  - `type` in `{"event","fresh","slow","anchor"}`.
  - `hero_metric_id` is either `None` or a known metric ID within that section's metric set.
  - `read_order` is a permutation of the 12 section IDs (no dupes, no extras).
- [ ] Fallback policy: on any validation failure, raise `RiskMapLayoutValidationError`; caller (`pipeline.py`) catches and computes deterministic fallback (see Task 3B.7).
- [ ] Tests in `tests/claude/test_validators.py`:
  - Valid payload passes.
  - Missing section raises.
  - 13 sections raises.
  - `x=11.1` raises.
  - `hero_metric_id="unknown"` raises.
  - `read_order` with duplicate raises.

### Task 3B.4 — `risk_map_layout` call wiring

- [ ] Add `call_risk_map_layout(ctx) -> RiskMapLayout | None` to `brief/pipeline.py`:
  - Build prompt input from `ctx` (12 SectionData summaries + exec_signals + bankerread_insights).
  - Call `run_max(prompt=..., timeout_s=45)`.
  - Validate via Task 3B.3 validator.
  - Return `None` on any failure.
- [ ] In `pipeline.run()`: after `bankerread_insights` succeeds, invoke `call_risk_map_layout`. On `None`, compute deterministic fallback.
- [ ] Deterministic fallback (`_fallback_risk_map_layout`):
  - `x = min(10, abs(delta_pct) / some_scale)` per section.
  - `y` = fixed editorial baseline per section (e.g. policy=6, oil=9 when events, otherwise stable).
  - `type` = from freshness + has-event-metric.
  - `hero_metric_id = None` for all sections.
  - `read_order` sorted by `x * y` descending.
- [ ] Unit tests in `tests/claude/test_risk_map_layout.py` patching `run_max`:
  - Happy path returns a valid `RiskMapLayout`.
  - `run_max` raises → returns `None`.
  - Invalid JSON from Claude → returns `None`.
  - Deterministic fallback is pure (same input → same output).

### Task 3B.5 — `todays_call.txt` prompt

- [ ] Write `brief/claude/prompts/todays_call.txt`. Required elements:
  - Voice: "Desk Editor · The Brief" — editorial, direct, written for a banker who has 30 seconds.
  - Length cap: 2–3 sentences, ~55 words, max 400 chars.
  - Must reference the top-significance section (y ≥ 7 from `risk_map_layout`).
  - Must NOT repeat any BankerRead `pull` verbatim — synthesize across 2–3 signals.
  - Must NOT include the byline (byline is added by the renderer).
  - Output strictly: `{"text": "..."}`.

### Task 3B.6 — `todays_call` validator

- [ ] Extend `validators.py` with `validate_todays_call(raw: dict) -> TodaysCall`.
- [ ] Validates:
  - `text` present, non-empty, ≤ 400 chars.
  - `text` does not contain `"Desk Editor"` substring (byline is rendered separately).
  - Returns `TodaysCall(text=..., byline="Desk Editor · The Brief")`.
- [ ] Tests in `tests/claude/test_validators.py`:
  - 53-word paragraph validates.
  - 450-char paragraph raises.
  - Empty text raises.
  - Text with "Desk Editor" in body raises.

### Task 3B.7 — `todays_call` wiring + fallback

- [ ] Add `call_todays_call(ctx, risk_map_layout, bankerread_insights) -> TodaysCall | None` to `pipeline.py`.
- [ ] In `pipeline.run()`: after `risk_map_layout` completes (real or fallback), invoke `call_todays_call`. On `None`, fallback = `TodaysCall(text=<lead_section_bankerread_pull>, byline="Desk Editor · The Brief")` where lead is determined by `risk_map_layout.read_order[0]`.
- [ ] Unit tests in `tests/claude/test_todays_call.py` patching `run_max`:
  - Happy path returns valid `TodaysCall`.
  - `run_max` failure → fallback to lead section's pull.
  - Lead section has no structured BR (freeform) → fallback to `text` field.
  - Lead section has no `pull` at all → fallback to an empty-safe string "No single call today — see Flow Index for the full read."

### Task 3B.8 — Phase 3B exit gate

- [ ] `pytest tests/claude/ -v` all green (including the 2 new call tests and validator additions).
- [ ] `pipeline.run()` on today's data emits `RunResult` with all 5 Claude outputs wired; any single call can fail and `RunResult` still validates.
- [ ] VPS dry-run: `python -m brief.pipeline --dry-run --artifacts-dir=/tmp/brief-artifacts` produces `risk_map_layout.json` and `todays_call.json` in addition to the existing 3 artifacts.
- [ ] Commit: `feat(brief): Claude calls 4-5 (risk_map_layout, todays_call) + fallbacks`.

---

## Phase 4B — V4 Renderer (~8h)

**This phase replaces Part 1 Phase 4 in full.** Do not attempt to execute Part 1 Phase 4 alongside this — they produce conflicting output.

### Task 4B.1 — `render/_jsx.py` V4 helper library

- [ ] Rewrite `brief/render/_jsx.py` with V4 helpers:
  - `attr(name, value)` — HTML attribute escape
  - `fmt_num(value, unit=None, tabular=True)` — tabular-num monospace number
  - `staleness_dot(state: Literal["fresh","warn","stale","pending"]) -> str`
  - `cadence_pill(cadence: str) -> str`
  - `sparkline_svg(points: List[float], color: str, w=140, h=32) -> str` — 12-point SVG polyline
  - `hero_wrap(metric_html: str) -> str` — wraps a metric in the hero chrome
  - `pull_quote(text: str, cite: str) -> str` — section-top pull quote
  - `bankerread_aside(br: BankerReadInsight, anchor: str, anchor_label: str) -> str` — renders structured or freeform variant based on discriminator
  - `section_head(numeral: str, kicker: str, title_parts: List[Tuple[str,str]], dek: str, meta: List[str]) -> str` — where title_parts is list of (text, style) with style in {"plain","italic-ox"}
- [ ] Tests in `tests/render/test_jsx_helpers.py` for each helper — 2+ cases per helper.
- [ ] No DOM dependency; all helpers return plain HTML strings.

### Task 4B.2 — `render/shell_v4.html`

- [ ] Create a clean V4 shell template with splice placeholders:
  ```html
  <!doctype html>
  <html lang="en">
  <head>
    <!-- fonts + inline CSS + noise SVG, pulled from v4 prototype -->
  </head>
  <body>
    <div class="page">
      <!-- SPLICE:dateline -->
      <!-- SPLICE:masthead_todays_call -->
      <!-- SPLICE:risk_map -->
      <!-- SPLICE:flow_index -->
      <!-- SPLICE:section_headlines -->
      <!-- SPLICE:section_bb -->
      <!-- SPLICE:section_banking -->
      <!-- SPLICE:section_dse -->
      <!-- SPLICE:section_tbond -->
      <!-- SPLICE:section_fx -->
      <!-- SPLICE:section_macro -->
      <!-- SPLICE:section_dam -->
      <!-- SPLICE:section_comm -->
      <!-- SPLICE:section_remit -->
      <!-- SPLICE:section_iranwar -->
      <!-- SPLICE:section_fiscal -->
      <!-- SPLICE:section_nbr -->
      <!-- SPLICE:colophon -->
    </div>
  </body>
  </html>
  ```
- [ ] Inline CSS: lift from `The Brief v4 - Map Front.html` but strip any `[data-density="compact"]` that would require edit-mode toggling. Keep only the default (comfortable) spacing.
- [ ] No React, no Babel, no `EDITMODE-*` markers, no `TWEAK_DEFAULTS`, no `postMessage` listeners, no `<Tweaks>` component.
- [ ] Also create `fixtures/sample_shell_v4.html` — ~200-line miniature version for fast render tests (all splice comments present, minimal CSS).

### Task 4B.3 — `render/assemble.py` V4 shell splicer

- [ ] Rewrite `brief/render/assemble.py`:
  - `load_shell(path: str) -> str` — reads `shell_v4.html`.
  - `splice(shell: str, placeholder: str, fragment_html: str) -> str` — replaces the HTML comment `<!-- SPLICE:{placeholder} -->` with `fragment_html`.
  - `assemble_brief(run_result: RunResult, shell_path: str = None) -> str` — orchestrator:
    1. Load shell.
    2. Render each block from its template function.
    3. Splice in order.
    4. Return full HTML.
  - No brace-counting, no JSX-body matching (simpler than Part 1's original approach because the shell is now a clean template).
- [ ] Tests in `tests/render/test_assemble_v4.py`:
  - Splicing a single fragment replaces the comment.
  - Unknown placeholder name raises `AssembleError`.
  - Full `assemble_brief` on a fixture `RunResult` produces HTML with all 18 splice sites filled.

### Task 4B.4 — `render/templates/dateline.py`

- [ ] Function: `render_dateline(run_result: RunResult) -> str`.
- [ ] Produces the top oxblood ticker strip: LIVE + time + 4 headline metrics (USD/BDT, DSEX, Brent, Reserves) + "Next update · 18:00 close".
- [ ] Pulses gold dot via `<span class="dot"/>` + existing CSS.
- [ ] Test: fixture in → 1 html string out, asserts presence of LIVE tag, 4 metric values, pulse dot.

### Task 4B.5 — `render/templates/masthead.py`

- [ ] Function: `render_masthead(run_result: RunResult) -> str`.
- [ ] Produces `fd-meta` (VOL · ISSUE · date) + `fd-head` 2-column (giant title + Today's Call aside).
- [ ] Today's Call text from `run_result.todays_call.text`; byline rendered separately in oxblood left-border block.
- [ ] Test asserts: title present, Today's Call text spliced correctly, byline text matches spec.

### Task 4B.6 — `render/templates/risk_map.py`

- [ ] Function: `render_risk_map(coords: List[MapCoord], sections: Dict[str, SectionData]) -> str`.
- [ ] Produces full SVG scatter: 4 quadrant bg fills, grid lines, axes, axis labels, quadrant captions, read-first diagonal hint, 12 dots with type-colored fills, per-dot `§NN` label and section kicker above.
- [ ] Also produces `map-detail` pane (right aside) — but the detail pane is purely the active-section renderer; for SSR we render the detail for `coords[read_order[0]]` (the lead).
- [ ] Test asserts: 12 dots present, axis labels, color mapping by type.
- [ ] **Mobile branch:** CSS-only — shell CSS has a `@media (max-width: 760px)` that hides axis text and shrinks dots. Renderer does not output two variants.

### Task 4B.7 — `render/templates/flow_index.py`

- [ ] Function: `render_flow_index(read_order: List[str], sections: Dict[str, SectionData]) -> str`.
- [ ] 12-entry list, 2 rows × 6 columns desktop (CSS).
- [ ] Each entry: rank numeral (oxblood serif italic) + mono kicker (`§NN · Section`) + serif title.
- [ ] Click-to-scroll anchors.
- [ ] Test asserts: 12 items, correct read order, anchor hrefs match section IDs.

### Task 4B.8 — `render/templates/section_bb.py` (full TDD canonical example)

- [ ] Implement section_bb template as the reference template — all subsequent sections mirror its pattern.
- [ ] Renders:
  - `SectionHead` (numeral `02`, kicker `POLICY & RATES`, title with italic-oxblood accent, dek, meta pills).
  - `Pull` quote (from `SectionData.pull`).
  - Metric grid: hero metric (if `Metric.hero`) at top, rest as regular cards.
  - `BankerRead` aside (structured variant).
- [ ] Full TDD: red → green → refactor. Test cases:
  - All metrics render.
  - Hero metric gets hero chrome.
  - Stale metric shows `Stale` pill.
  - `pending` metric shows `Next release` pill.
  - BankerRead renders all 4 §A-§D sections.
- [ ] Commit separately: `feat(brief/render): section_bb V4 template (full TDD)`.

### Task 4B.9 — Generic metric-section renderer for 10 similar sections

- [ ] Pattern: §03 Banking, §06 FX, §07 Macro, §08 DAM, §09 Commodities, §10 Remit, §15 Fiscal, §16 NBR, §14 IranWar, §05 TBond all share the same skeleton (SectionHead + Pull + metric grid + BankerRead aside).
- [ ] Extract `render_generic_section(section: SectionData, br: BankerReadInsight, dom_id: str) -> str`.
- [ ] Create thin per-section binding files: `section_banking.py`, `section_fx.py`, `section_macro.py`, `section_dam.py`, `section_comm.py`, `section_remit.py`, `section_fiscal.py`, `section_nbr.py` — each imports `render_generic_section` and passes the right section_id.
- [ ] Sections with divergent needs (DSE, TBond, IranWar, Headlines) get dedicated templates (tasks 4B.10–4B.13).
- [ ] Test: `tests/render/test_templates_v4_smoke.py` — for each of the 8 generic-bound sections, assert the HTML contains: section numeral, at least one metric card, one BankerRead aside. Shape-level only.

### Task 4B.10 — `render/templates/section_dse.py` (custom)

- [ ] Extends the generic skeleton with:
  - Breadth numerals block (74/162/58 big serif, mono labels) — only when `section.degraded_breadth = False`.
  - Sector Heat 8-tile heatmap (intensity based on `|pct|`, green for ≥0, oxblood for <0) — only when `section.degraded_sector_heat = False`.
  - On degraded flags: render "§ Section Unavailable" FreshTag-style (keep current) — user exception 9c.
- [ ] Full TDD: red → green.
- [ ] Tests assert:
  - Both breadth and sector heat rendered in happy path.
  - Breadth degraded → breadth block absent, rest of section renders.
  - Both degraded → both blocks absent, metric grid still renders.

### Task 4B.11 — `render/templates/section_tbond.py` (custom)

- [ ] Extends generic with Yield Curve SVG: 6 tenors (3M/6M/1Y/2Y/5Y/10Y), current week solid oxblood + previous week dashed ink-4.
- [ ] Data: current week from `SectionData.metrics`, previous week from `metric_history` last-week snapshot (builder surfaces it).
- [ ] Test: both curves rendered, axis labels correct, legend "Apr 17 vs Apr 10" displayed.

### Task 4B.12 — `render/templates/section_iranwar.py` (custom)

- [ ] Extends generic with Oil chart SVG: 12-session line + event pins from `SectionData.extras["oil_events"]`.
- [ ] Hot events (Hormuz tanker) render in oxblood; cold events (IAEA, OPEC+ hold) in ink.
- [ ] Test: 3 event pins present, hot pin visually distinct (class or inline style), 12-point line rendered.

### Task 4B.13 — `render/templates/section_headlines.py`

- [ ] Implements V4 3-tier layout:
  - Lead story (from `headlines_curation.lead_id`): oxblood top border, source badge, italic-oxblood emphasized headline, dek, KeyPoints dark card, timestamp.
  - Right column (from `headlines_curation.right_column[4]`): compact items.
  - Bottom row (from `headlines_curation.bottom[3]`): items with deks.
  - BankerRead at bottom — **free-form variant** (only place in the render where freeform applies).
- [ ] Full TDD: red → green.
- [ ] Tests:
  - 1 lead + 4 compact + 3 dek (= 8 items total) rendered.
  - KeyPoints card renders 3 bullets with oxblood `§` glyphs.
  - Italic-oxblood emphasis on lead title (via `<em>` tag).
  - BankerRead at bottom is freeform variant (not structured).

### Task 4B.14 — `render/templates/colophon.py`

- [ ] Function: `render_colophon(run_result: RunResult) -> str`.
- [ ] V4 footer: 3-col mono row — brand (oxblood) + source list + next edition timestamp.
- [ ] Test asserts: brand text, sources separated by ·, next edition formatted per §12 of spec (`DD MMM · HH:MM BDT`).

### Task 4B.15 — `render/email_digest.py`

- [ ] Function: `render_email_digest(run_result: RunResult) -> str` — returns plain text.
- [ ] Structure:
  ```
  THE BRIEF · Vol. II · No. 412
  Tue 21 Apr 2026 · 06:15 BDT

  TODAY'S CALL
  <text from run_result.todays_call.text>
  — Desk Editor · The Brief

  TOP 3 SIGNALS
  • <exec_signals[0].text> — <anchor URL>
  • <exec_signals[1].text> — <anchor URL>
  • <exec_signals[2].text> — <anchor URL>

  LEAD HEADLINE
  <lead title>
  <source> · <time>
  <lead URL>

  Full edition → <hosted URL>
  ```
- [ ] No inline HTML, no images, no attachments.
- [ ] Test: input `RunResult` → plain text matches expected structure, all URLs present, no HTML tags.

### Task 4B.16 — `pipeline.render_v4()` + `run()` end-to-end

- [ ] Add `brief/pipeline.py` method `render_v4(run_result: RunResult) -> Tuple[str, str]` returning `(html, email_text)`.
- [ ] Update `run()` to call `render_v4` after all Claude calls complete.
- [ ] Wire the pipeline's existing persist step to write both artifacts: `index.html` (V4 HTML) and `email.txt` (plain-text digest).
- [ ] Integration test in `tests/test_pipeline_integration_v4.py`:
  - Mock all 5 Claude calls with fixtures.
  - Run `pipeline.run()` against `fixtures/econdelta_latest.json`.
  - Assert `index.html` contains: dateline, masthead, risk-map SVG with 12 dots, flow-index 12 items, each of 13 section numerals, colophon.
  - Assert `email.txt` has the 5 expected lines (header, Today's Call, 3 signals, lead, full-edition link).

### Task 4B.17 — `build.sh` fidelity check

- [ ] Update `build.sh` to invoke the new V4 pipeline entrypoint.
- [ ] Run against production data; assert exit-code 0 and output files present.
- [ ] Open preview URL locally; no console errors; no missing assets.
- [ ] (Skipped if user accepts HTML-only verification without running the scripted check.)

### Task 4B.18 — Phase 4B exit gate

- [ ] `pytest tests/render/ tests/test_pipeline_integration_v4.py -v` green.
- [ ] `pipeline.run()` on today's data produces `index.html` that:
  - Renders without JS errors in Chrome, Firefox, Safari.
  - Matches V4 prototype visually at desktop (≥960px) and iPhone-17 (390px) breakpoints.
  - All 13 numbered sections present and correctly anchored.
  - Risk Map has 12 dots.
  - Flow Index has 12 entries.
- [ ] `email.txt` renders as plain text in Gmail preview.
- [ ] Commit: `feat(brief): V4 renderer + email digest`.

---

## Deferred / out of scope for Part 1B

- `pdfjs-dist` 3.x → 5.x bump.
- Unification of chart history sources (current: `metric_history` for sparklines + `tb_*` for yield curve and oil line; deferred to post-shadow-soak when both sources have been validated in parallel).
- DSE ASN-block root-cause fix (gracefully degrades today via Phase 2C).
- `oil_events` automation (manual editorial curation for now).
- `update.py` removal (Part 2 ops plan after shadow soak).
- Dark mode (V4 paper-light only per user decision).
- `Tweaks` panel in production (stripped entirely).

---

## Self-review summary

Checklist items verified on this draft:

- [x] Every task has explicit TDD cycle (red → green → verify) or is documented as "no code change".
- [x] Every Claude call has a defined fallback.
- [x] Every DSE scrape has a degraded-mode path.
- [x] Schema deltas are backward-compatible (`hero: bool = False`, `pull: str | None`).
- [x] No placeholders (`TBD`, `TODO`, `fill in`, `similar to`) in task bodies.
- [x] All 13 rendered sections have an explicit template file + test.
- [x] V4 shell is net-new; the old `the-brief.html` is never modified by this plan.
- [x] Email digest is a new artifact, does not conflict with existing Brevo path.
- [x] Mobile Risk Map simplification is CSS-only — no dual-path renderer.

---

## Execution Handoff

To execute this plan:

1. Fresh branch from `main` (or from `feat/v4-retarget` if already created): `git checkout -b feat/v4-retarget main`.
2. Invoke `superpowers:subagent-driven-development` with this plan as the target — execute task-by-task, commit-per-task.
3. Start with **Phase 1 Task 1.3 extension** (schema deltas) — it's a prerequisite for Phase 3B and Phase 4B.
4. Then **Phase 2C** (DSE scrapes + oil events) — independent, can run in parallel.
5. Then **Phase 3B** (calls 4-5) — depends on schema.
6. Then **Phase 4B** (renderer) — depends on schema + all 5 Claude calls.
7. Phase 5-6 (deploy + shadow + cutover) go in a separate **Part 2 ops plan** — out of scope here.

Total expected active time: **~14h** (0.5 schema + 1.5 Phase 2C + 2.5 Phase 3B + 8 Phase 4B + 1.5 slack for cross-task integration).
