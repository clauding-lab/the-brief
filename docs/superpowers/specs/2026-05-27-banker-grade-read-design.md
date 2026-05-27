# Banker-Grade Read — v1.4.0 design

**Date:** 2026-05-27
**Codename:** Banker-Grade Read
**Target release:** v1.4.0
**Status:** Brainstorm complete, awaiting implementation plan
**Source conversation:** 2026-05-27 brainstorming session — "what more can we develop to attract the banker audience feeding their info, insight, and analytical needs"

---

## 1. Context

Existing readers of The Brief say they want more **analytical depth** — interpretation and implications, not more raw data. The brief's content surfaces (`banker_read`, `analysis`, `tldr`, `cover.sub`) already exist and are rendered, but they aren't reliably banker-grade: many sections produce restatement rather than implication. Chart cards have no interpretation attached at all.

Banker-essential **historical context** is also missing. Tier-1 banking professionals frame decisions in terms of "vs last MPS / vs Q3 2024 / since the pandemic." The brief's pipeline stores this data in two Supabase tables (`metric_history` for daily/weekly, `metric_history_monthly` for monthly long-horizon) but has no compute layer that surfaces references to it. EconDelta's `/macro` PWA uses `metric_history_monthly` with 30+ pre-aggregated monthly series (CPI variants, REER, real policy rate, M1/M2 YoY, credit growth split, etc.) — The Brief currently reads none of them.

This spec defines v1.4.0 — a pipeline + prompt + minimal-UI upgrade that closes both gaps.

## 2. Decision history (from brainstorm)

1. **Bottleneck** identified as **depth**, not acquisition or retention.
2. **Depth flavor** = **interpretation** — "tell me what to think about each number." Not peer awareness, not historical context alone, not desk-specific framing.
3. **Approach** = combined **prompt upgrade (A) + Chart Read (B)** — the original "Next Read" forward-looking anchor (C) deferred to v1.5+.
4. **EconDelta audit** revealed `metric_history_monthly` is unused by the brief and contains 30+ banker-essential monthly series. Adds **macro section enrichment** to v1.4.0 scope (Path B).
5. **Visual diff minimized** — no new CSS, no new components — Chart Read renders inside existing `.tb-analysis` styling.
6. **Historical claims must carry the actual reference data point** in parens to build reader confidence — claims become auditable, density doubles.
7. **Web search sanity check** of EconDelta historical claims — budget 3 per brief, materiality threshold 25%.
8. **Abbreviation tier policy** added — Tier-1 bare-use list extended in Master.md; Tier-2 expand-on-first-use; Tier-3 always-expand-or-rephrase.

## 3. Scope (in)

### 3.1 Historical anchors compute layer (NEW)

New module `brief/history_anchors.py`. Reads `metric_history` (daily/weekly) and `metric_history_monthly` (monthly long-horizon) and produces `HistoryFact` instances per metric for the editor to weave into prose.

```python
@dataclass(frozen=True)
class HistoryFact:
    metric_id: str
    kind: Literal["since_lower", "since_higher", "vs_period", "extreme_in_window", "first_cross_since"]
    phrase: str                        # pre-formatted prose, e.g. "lowest 12-month CPI since Sep 2021"
    reference_value: float             # raw numeric reference point
    reference_value_formatted: str     # display-ready ("4.8%", "$87.20", "Tk 12,400 cr")
    reference_as_of: str               # ISO date or period label ("2021-09-01", "Q3 2024")
```

**Primitives** (all cadence-aware via `metric_definitions.cadence`):

- `last_lower_than(metric_id, current_value, since_data_points=N)` → ISO date of most recent crossing below.
- `last_higher_than(metric_id, current_value, since_data_points=N)` → ISO date of most recent crossing above.
- `pct_change_since(metric_id, current_value, ref_date_or_label)` → bp/% delta with formatted phrase.
- `rolling_extremes(metric_id, window_data_points)` → `{min, max, percentile_rank, current_position}`.
- `first_cross_since(metric_id, current_value, threshold, direction, since_data_points)` → ISO date.

**Cadence-aware table selection:**

| Cadence (from `metric_definitions`) | Source table | Window default |
|---|---|---|
| `daily` | `metric_history` | 365 data points |
| `weekly` | `metric_history` | 52 data points |
| `monthly` | `metric_history_monthly` | 60 data points (5 years) |
| `quarterly` | `metric_history` | 16 data points (4 years) |
| `fiscal_year` | `metric_history` | 5 data points |

**Guard rules:**

- `min_data_points` per cadence prevents nominal "since" claims (daily ≥30, weekly ≥12, monthly ≥6, quarterly ≥4, FY ≥3). Below threshold → return no facts of that kind.
- Rolling windows count **data points**, not calendar days — robust to scraper outages (e.g., `forex.timer` dead since 2026-05-05 per AGENT_LEARNINGS.md cross-references).
- Returns empty list if metric has insufficient history.
- Reads `metric_definitions.format` (`comma-2dp`, `percent-1dp`, etc.) to render `reference_value_formatted` consistently with the rest of the brief.

### 3.2 Editor prompt upgrade (Approach A)

Surface: `brief/claude/prompts/editor_v6.txt` and `editor_v6_friday.txt`.

**Banker-grade specificity rubric** added as a new section. Single test: *would a Tier-1 banker reading this take an action OR update a mental model?* Two filters that must both pass:

| Filter | Pass example | Fail example |
|---|---|---|
| **Time-anchored** — names a specific period, event, or trajectory | "lowest since Q2 2021", "watch Wednesday's MPS", "third consecutive monthly deceleration" | "remains elevated", "continues to be a concern", "in coming weeks" |
| **Implications-oriented** — leads to a desk decision or mental-model update | "ALM mismatch risk for FRA-tied LT loans", "watch H2 receivables 60-90 DPD bump", "expect MPC to hold given excess liquidity" | "may affect import bills", "could impact the economy", "is being closely monitored" |

Worked contrast for an oil-price chart read:
- **BANAL:** "Brent rose 2.4%. Higher oil prices may affect import bills."
- **BANKER-GRADE:** "Brent +2.4% to $87.20, third weekly gain since Q2 2024. For energy-importer credit lines, watch H2 receivables 60-90 DPD bump on the next refi cycle."

**Field-by-field constraints** (added to existing field instructions):

| Field | New constraint |
|---|---|
| `Section.banker_read.verdict` | (existing: 2-3 sentences, 80-300 chars) + MUST contain at least one of: desk word, action verb, or time anchor. |
| `Section.banker_read.watch[]` (per item) | MUST have a time anchor (Wednesday's MPS, Q3 disclosure, next auction, after MFEC, by year-end). |
| `Section.banker_read.risk[]` (per item) | MUST name a desk-relevant impact (ALM mismatch, LCR pressure, RWA bump, NPL recognition, FX squeeze, deposit outflow). |
| `Section.analysis` | (existing: 3-5 sentences, hero only) + each paragraph references ≥1 number AND its implication. No purely descriptive paragraphs. |
| `Section.tldr` | (existing: 8-14 words) + MUST contain directional language (up/down/tightening/easing/firming/softening/widening/narrowing). |
| `Cover.sub` | (existing: ≤60 chars) + MUST include either a delta vs prior period OR an implication OR a historical anchor — not bare restatement. Historical anchors live in this field; no new `Cover.history_anchor`. |
| `ChartRead.signal` (NEW) | ≤25 words. What the chart shows, direction-clear, ≥1 number. |
| `ChartRead.context` (NEW) | ≤20 words. REQUIRED temporal anchor + reference value in parens. |
| `ChartRead.implication` (NEW) | ≤25 words. MUST contain at least one of: desk word, action verb, time anchor. |

**`history_facts` input** added to the editor's JSON input per section:

```json
"history_facts": [
  {
    "metric_id": "cpi_12m_avg_monthly",
    "kind": "since_lower",
    "phrase": "lowest 12-month CPI since Sep 2021",
    "reference_value_formatted": "4.8%",
    "reference_as_of": "2021-09-01"
  }
]
```

**Editor instructions:**

1. Weave **at least one** fact into `chart_read.context` for chart-bearing sections, and into `banker_read.verdict` or `analysis` where it sharpens the call.
2. When you cite a `since_lower / since_higher / first_cross_since` fact, **append the reference value in parens** so the claim is auditable: "lowest 12-month CPI since Sep 2021 **(4.8% then)**", "first time Brent above $90 since 2023 **($91.40 last cross)**".
3. Never invent historical claims not present in `history_facts`. If you want to say "lowest since X", X must come from facts.

**Voice safeguards:**

- No new historical claims outside `history_facts`.
- No tone shift toward regulators or government — Master.md's *neutral and diplomatic* rule remains dominant. Sharper desk talk is allowed; sharper political talk is not.

### 3.3 Abbreviation tier policy (extends `Master.md`)

Master.md currently defines a starter "Preferred abbreviations" list (BB, NBR, BSEC, ADP, MPS, MPC, YoY, H1/H2, Q1-Q4). v1.4.0 extends it into a three-tier policy:

**Tier 1 — bare use always (never expand):**

- Institutions: BB, NBR, BSEC, IMF, WB, ADB, GoB
- Policy: MPS, MPC, ADP, SDF, SLF, CRR, SLR
- Instruments: T-Bill, T-Bond, FDR
- Markets: USD/BDT, NPL, ALCO, MANCO
- Capital: Tier-1, Tier-2
- Time: YoY, MoM, QoQ, MTD, YTD, FY, H1, H2, Q1–Q4
- Units: bp, cr, Tk, $

**Tier 2 — expand on first use per section, bare thereafter:**

- Prudential ratios: LCR (Liquidity Coverage Ratio), NSFR (Net Stable Funding Ratio), RWA (Risk-Weighted Assets), CAR (Capital Adequacy Ratio), CRAR (Capital to Risk-weighted Assets Ratio)
- Risk: ALM (Asset-Liability Management), DPD (Days Past Due), ECL (Expected Credit Loss)
- Treasury: FRA (Forward Rate Agreement), IRS (Interest Rate Swap), REER (Real Effective Exchange Rate), NEER (Nominal Effective Exchange Rate)
- Banks: SCB (State-Owned Commercial Bank — distinct from Scheduled Commercial Bank), GSIB (Global Systemically Important Bank), D-SIB (Domestic Systemically Important Bank)

**Tier 3 — always expand, or rephrase to a 2-3 word noun phrase:**

- Anything not in Tier 1-2. Including ICAAP, IFRS, Basel III/IV, IBOR, ESG, KYC/AML.
- If forced to use, expand every occurrence; otherwise rephrase ("under Basel capital framework" instead of "under Basel III").

**Where it lives:** Master.md gains a new subsection "Banker vocabulary tiers" between the existing "Preferred abbreviations" and "Avoid" tables.

### 3.4 Sub-editor checks (`brief/claude/prompts/subeditor_v6.txt`)

Seven new checklist items, added to the existing checklist:

1. **Specificity check** — every interpretive field (`banker_read.verdict`, `chart_read.implication`, `analysis` paragraphs) passes time-anchored AND implications-oriented filters. Banal language only → `revise`.
2. **Temporal-anchor check on `chart_read.context`** — must contain at least one of: `since`, `vs`, `last`, `above`, `below`, `back to`, `next`, a YYYY year, or a month/quarter token. Otherwise → `revise`.
3. **History claim audit** — every claim of the shape "lowest/highest since X" or "first time above/below Y since Z" must trace to an item in the section's `history_facts` input. Hallucinated history → `revise` (rewrite without the claim) or `fail` if it's load-bearing.
4. **History reference-value check** — time-anchored claims of kind `since_lower` / `since_higher` / `first_cross_since` MUST append the reference value in parens. If missing → `revise` with value inserted from `history_facts`.
5. **Web search sanity check** (NEW — uses Anthropic SDK `web_search` tool):
   - Budget: **max 3 web searches per brief**.
   - Trigger: only on `since_lower / since_higher / first_cross_since` claims (high-confidence, audit-worthy). Skip `vs_period` and `extreme_in_window`.
   - **Materiality threshold: contradiction = >25% delta on metric value OR a different reference period.**
   - Decision matrix:
     | Web search outcome | Action |
     |---|---|
     | Confirms EconDelta claim | no action |
     | No signal / sources thin | no action (trust EconDelta) |
     | Contradicts EconDelta, **>25% delta** OR different reference period | `revise` — soften or omit, log divergence |
     | Contradicts but ≤25% delta and same reference period | log only (treat as noise, trust EconDelta) |
   - Failure mode: network/rate-limit error → proceed without verification. Brief never blocks on web search.
   - Logging: every search result + decision goes into the run report (extend `run_report` schema with `history_audit: [{claim, search_result, action}]`).
6. **Banal-language scan** — search interpretive fields for any token in the blocklist (see §3.5). Hits → `revise`.
7. **Abbreviation policy check** — per section, scan for non-Tier-1 abbreviations. First occurrence must be expanded. Tier-3 must be expanded every time. Violations → `revise`.

### 3.5 Validators (`brief/claude/validators.py`)

Five new functions, callable at both sub-editor time AND JSON schema validation time (defense in depth):

```python
def validate_no_banal_language(text: str) -> ValidationResult: ...
def validate_chart_read_temporal_anchor(chart_read: dict) -> ValidationResult: ...
def validate_chart_read_implication_quality(chart_read: dict) -> ValidationResult: ...
def validate_history_claim_has_reference(text: str, used_facts: list[HistoryFact]) -> ValidationResult: ...
def validate_abbreviation_policy(section_text: str, tier1_set: frozenset, tier2_set: frozenset) -> ValidationResult: ...
```

**Module-level constants:**

```python
BANAL_TOKENS = frozenset({
    # AI tells
    "delve", "myriad", "tapestry", "navigate", "intricate", "robust",
    # journalese
    "amid", "moreover", "stunning move", "in a development",
    # hedging without source
    "could potentially", "may possibly", "it remains to be seen",
    # vague time
    "in coming weeks", "in the coming months",
})

TEMPORAL_TOKENS = frozenset({"since", "vs", "last", "above", "below", "back to", "next"})
TEMPORAL_REGEX = r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Q[1-4])\s*(20\d{2})?\b"

DESK_WORDS = frozenset({
    "treasury", "credit", "risk", "alm", "alco", "manco",
    "lcr", "rwa", "npl", "car", "tier-1", "primary dealer",
    "remittance", "import lc", "export lc", "fdr", "deposit",
})

ACTION_VERBS = frozenset({
    "watch", "expect", "position", "brace", "firm", "soften",
    "tighten", "ease", "widen", "narrow", "anchor", "signal",
})

TIER1_ABBREVS = frozenset({...})  # see §3.3
TIER2_ABBREVS = frozenset({...})  # see §3.3, with expansion mapping
```

### 3.6 Macro section enrichment

Surface: `brief/builders/macro.py` (currently a placeholder reading only 5 metric_ids).

**Rewrite to read 8 banker-essential monthly metrics from `metric_history_monthly`:**

| Metric | Banker relevance |
|---|---|
| `cpi_12m_avg_monthly` | smoothed trend — preferred CPI gauge |
| `cpi_p2p_food_monthly` | food inflation — retail credit risk signal |
| `cpi_p2p_nonfood_monthly` | core inflation proxy — desk-relevant |
| `real_policy_rate_monthly` | banker-essential — drives ALM positioning |
| `reer_monthly` | competitiveness gauge — export credit risk |
| `private_credit_growth_yoy_monthly` | banking-system depth |
| `m2_growth_yoy_monthly` | money supply growth |
| `import_cover_months_monthly` | FX reserve adequacy |

Each metric:
- Rendered as a metric card in the existing tabular pattern (no new card chrome).
- Calls `history_anchors.py` to produce HistoryFacts.
- Facts piped to the editor through the section's `history_facts` input.

**ONE new chart in macro section: CPI 24-month trend.**

- New `chartConfigs.cpiTrend` entry in `lib/chartConfigs.ts`.
- 3 lines: 12m-avg headline (steel token), food (warn token), non-food (neu token).
- 24-month x-axis (`TimeScale`, already registered in `BriefChart.tsx` — AGENTS.md landmine #2 honored).
- Y-axis = percent (`LinearScale`, already registered).
- Uses existing chart card chrome — no new component, no new CSS.

### 3.7 ChartRead schema + render

**New field in `types/brief.ts`:**

```typescript
export interface ChartRead {
  signal: string;        // ≤25 words, direction-clear, ≥1 number
  context: string;       // ≤20 words, REQUIRED temporal anchor + reference value
  implication: string;   // ≤25 words, desk word OR action verb OR time anchor
}

export interface Section {
  // ...existing fields...
  chart_read?: ChartRead | null;
}
```

**Render in `app/components/Section.tsx`** — three paragraphs in an existing `.tb-analysis` block, immediately under `<BriefChart>`:

```tsx
{chartConfigKey && <BriefChart section={section} configKey={chartConfigKey} />}
{chartConfigKey && chart_read && (
  <div className="tb-analysis tb-chart-read">
    <p>{chart_read.signal}</p>
    {chart_read.context && <p>{chart_read.context}</p>}
    <p>{chart_read.implication}</p>
  </div>
)}
```

- `.tb-chart-read` is a **marker class for spec / future targeting** — ships with **zero CSS rules**.
- All styling cascades from existing `.tb-analysis` — no new component, no new CSS variables, no new typography scale.
- Email render uses the same existing `.tb-analysis` patterns; no email-specific overrides needed.

### 3.8 Failure-mode handling

- Sub-editor `revise` outcomes: retry once with the failed check spelled out; ship the second output even if still imperfect.
- Web search failures (network, rate limit): proceed without verification. Brief never blocks on web search.
- History anchors compute failures: editor sees empty `history_facts`, falls back to non-historical context (still satisfies temporal-anchor check via "vs last X" relative language).
- ChartRead missing for a chart-bearing section: section renders without the prose block — backward-compatible.

**The 06:30 BDT publish window is hard. Quality enforcement never blocks the brief from shipping. Banal prose ships if retries fail.**

## 4. Non-goals

- No new sections.
- No new visual primitives or CSS classes (`.tb-chart-read` is a marker only).
- No new components (Chart Read renders inline via `.tb-analysis`).
- No new field on `Cover` (historical anchors pack into existing `Cover.sub`).
- No desk-specific personalization.
- No real-time alerts, push notifications, or API.
- No retroactive rewrites of old briefs (Section.chart_read is optional; missing → no render).
- No "story recurrence" history (last-time-this-circular-type-broke) — deferred.
- No reading from sources outside Supabase for historical data.
- No additional macro charts (REER, real policy rate, credit-growth split) — deferred to v1.5.0.
- No Banking Pulse section (NPL/CRAR quarterly + call money daily) — deferred to v1.6.0.

## 5. Success criteria

| Measure | Target |
|---|---|
| Every Section with a chart has a populated `chart_read` (currently 5 charts → 6 with new CPI) | 6/6 = 100% |
| `ChartRead.context` contains a temporal anchor (rule-checked by validator) | 100% |
| `ChartRead.context` cites a reference value when kind is `since_lower / since_higher / first_cross_since` | 100% of applicable claims |
| Every monthly metric in `metric_history_monthly` has ≥1 `HistoryFact` available | 100% |
| Sub-editor banal-language reject rate (first 5 days) | ≤ 30% |
| Web search verification calls per brief | ≤ 3 |
| Web search contradictions logged (without blocking publish) | day 1 |
| Macro section displays 8 new monthly metrics + 1 new CPI trend chart | shipped day 1 |
| `Cover.sub` includes a historical anchor when notable | best-effort; ≥1 occurrence in first week |
| Subscriber email open rate (rolling 14-day) | +5pp or stable |

## 6. Implementation phases (proposed — implementation plan refines)

**Phase 1 — Compute layer + tests** (no UI impact, no prompt change)
- `brief/history_anchors.py` module — 5 primitive functions, cadence-aware
- HistoryFact dataclass + serialization for editor input
- Tests: cadence routing, gap robustness, min_data_points guards
- Module-level constants in `validators.py`

**Phase 2 — Validators + sub-editor checklist + Master.md vocabulary tiers** (no UI impact)
- Five new validator functions in `validators.py`
- Sub-editor prompt checklist additions (specificity, temporal anchor, history reference, web search, banal, abbreviation)
- Web search tool wiring in sub-editor (Anthropic SDK `web_search`, 3-search budget)
- Master.md "Banker vocabulary tiers" subsection
- Tests: validator unit tests against banal/specific examples

**Phase 3 — Editor prompt + macro builder + new CPI chart config**
- `editor_v6.txt` and `editor_v6_friday.txt` updates: specificity contract, field constraints, history_facts weaving, abbreviation policy, reference-value-in-parens
- `brief/builders/macro.py` rewrite: 8 monthly metrics from `metric_history_monthly`, history_facts pipe to editor
- `lib/chartConfigs.ts`: new `cpiTrend` config
- Tests: macro builder integration, chartConfigs unit test

**Phase 4 — ChartRead schema + render**
- `types/brief.ts`: `ChartRead` interface + `Section.chart_read` field
- `app/components/Section.tsx`: render block under `<BriefChart>`
- Editor instruction: populate `chart_read` for every chart-bearing section
- Cover.sub editor instruction: write historical anchor here when notable
- Tests: Section.tsx render unit tests (3 states — full, partial, null)

**Phase 5 — Release: v1.4.0**
- CHANGELOG entry
- package.json bump
- README badge + footer sync
- Tag + GH release (per AGENTS.md landmine #11)

## 7. Out-of-scope decisions deferred

| Item | Target release |
|---|---|
| ChartRead + history for Long View `bar-chart` blocks | v1.4.1 (CSS-only patch since schema generalizes) |
| Story-recurrence history ("last time NBR did X") | v1.4.x on demand |
| "Next Read" forward-looking anchor in Cover | after v1.4.0 lands |
| Additional macro charts (REER, real policy rate, credit-growth split) | **v1.5.0 — "Macro Depth"** |
| Banking Pulse section (quarterly NPL + CRAR + daily call money rate) | **v1.6.0 — "Banking Pulse"** |
| Desk-specific framing ("for treasury / credit / risk") | v2.0.0 — major surface change |
| API / Brief Numbers as subscriber perk | v2.x — different product |

## 8. Cross-references

- `AGENTS.md` landmine #1 (tb_* tables LEGACY) — history queries target `metric_history` and `metric_history_monthly`, not `tb_*`
- `AGENTS.md` landmine #2 (Chart.js scale registration) — new CPI chart uses `TimeScale` + `LinearScale`, both already registered
- `AGENTS.md` landmine #6 (live metric_ids) — `metric_history_monthly` IDs are the v3 canonical names (e.g., `cpi_12m_avg_monthly`)
- `AGENTS.md` landmine #11 (tag every CHANGELOG version) — applies to v1.4.0 release flow
- `AGENT_LEARNINGS.md` — v1.4.0's banker-grade-read incident, if any, will be logged here post-ship
- `Master.md` — receives the abbreviation tier policy extension
- `Design.md` — no new entries; reuses existing `.tb-analysis` typography contract
- `docs/longview-workflow.md` — unchanged; Long View `bar-chart` block ChartRead deferred to v1.4.1
- EconDelta repo `db/migrations/0001_metric_history.sql` and `0006_metric_history_monthly.sql` — read-only consumption
- EconDelta repo `pwa/pages/macro.jsx` `KEY_METRICS_USED` — reference list for the 8 monthly metrics we'll pull

## 9. Risks

1. **Editor prompt bloat.** Adding ~50-80 lines to `editor_v6.txt` may push the prompt above token budgets or change model behavior in non-obvious ways. Mitigation: phase 3 testing on a fresh-brief test fixture first, side-by-side with the current prompt.

2. **Web search latency.** Each search adds ~1-2s. With budget 3 per brief, worst-case +6s on the sub-editor call. Mitigation: parallel search calls where possible; hard timeout per search.

3. **History data sparsity on newer metrics.** Some metrics in `metric_history_monthly` may have <6 months of data. The `min_data_points` guard handles this gracefully — editor sees empty facts and writes non-historical context. Risk is silent under-anchoring, not failure.

4. **`.tb-analysis` density on non-hero sections.** Today `.tb-analysis` only renders on hero sections (1-2 per brief). With ChartRead, it appears on every chart-bearing section (5-6 per brief). Visual density goes up. Mitigation: ship as-is; if mobile feels heavy, tighten `.tb-chart-read p { margin-block: 0.4em }` as a CSS-only follow-up (the AGENT_LEARNINGS v1.2.1 lesson is the precedent).

5. **Banal-language false positives.** "Robust" is on the blocklist but could appear legitimately ("Robust deposit growth at 14% YoY"). Mitigation: blocklist is a heuristic; sub-editor's `revise` is recoverable; if false positives are high, narrow the blocklist via a v1.4.x patch.

## 10. Test plan

**Unit tests (Phase 1):**
- `tests/test_history_anchors.py`: each primitive function against fixture metric_history data; gap robustness; min_data_points guards; cadence routing.

**Unit tests (Phase 2):**
- `tests/test_validators.py` extended: banal-language detection, temporal-anchor detection, implication-quality scoring, abbreviation policy enforcement.

**Integration tests (Phase 3):**
- `tests/test_pipeline_v6_macro_enrichment.py`: macro builder reads 8 monthly metrics; HistoryFacts populated; editor input shape verified.

**Component tests (Phase 4):**
- `tests/components/section_chart_read.spec.tsx` (or equivalent React testing setup): 3 render states — full, partial, null.

**End-to-end smoke (Phase 5):**
- Dry-run publish locally: `python -m brief.cli run --publish --dry-run --no-notify`. Inspect output for `chart_read` population per section, abbreviation expansion, historical anchors with reference values.
- Vercel preview deploy: visual eyeball that the macro CPI chart renders and Chart Read paragraphs appear under each chart.
- First production publish: monitor `run_report` for web search budget compliance, sub-editor reject rate, validator pass rate.

---

**End of design spec.** The implementation plan (next step) will turn each phase into specific tasks with file paths, line targets, and ordering.
