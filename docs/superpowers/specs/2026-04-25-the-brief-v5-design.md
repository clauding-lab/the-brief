# The Brief — V5 Design (2026-04-25)

**Status:** Approved design. Ready for implementation planning.
**Author:** Adnan Rashid (+ Claude Code brainstorming session)
**Scope:** Visual + editorial redesign. Data plumbing (V4) preserved.
**Replaces:** the V4 visual layer (`brief/render/v4/`) and the V4 prompt set. Builders, history, freshness, schema core, deploy stack are reused.
**Reference designs:** `docs/superpowers/v5-design-ref/The Brief v4 - Map Front.html` (visual) and `https://thebrief.clauding-lab.com/` (content depth).

## 1. Context and motivation

### Trigger

V4 (the 2026-04-21 redesign) shipped data plumbing, freshness handling, and a deterministic renderer scoped to "preserve existing visual layout." The V4 spec deliberately put visual redesign out of scope. The implementation matched that scope and produced a page that, on first end-to-end smoke run on 2026-04-25, looked roughly 10% of the visual fidelity of the existing reference design and content depth: section-meta pills rendered as escaped HTML, banker's reads collapsed to single sentences, no live status banner, no risk-map quadrant labels, no per-section structure beyond stacked text. Production-ready was unachievable on the original Sun 2026-04-26 06:30 BDT timer; the timer is disabled.

### Product direction

The Brief is a daily Bangladesh-economy intelligence digest aimed at senior bankers (CFO, CRO, Head of SME Banking, Head of Corporate Banking, Treasury Head). The reader opens the page at 06:30 BDT before the work day. The page must be:

1. **Visually distinguishable** from a Bloomberg copy — opinionated, magazine-quality, recognizably *The Brief*.
2. **Banker-actionable** — every section ends with a structured "what does this mean for my book today" panel.
3. **Daily-fresh and curated** — top sections rotate by day based on actual signal, not by section number.
4. **Resilient** — section-level degradation does not block the page; QA pass blocks demonstrably bad editions.

### Non-goals

- Mobile-responsive layout — V5 is desktop-first. Mobile is a follow-up.
- Dark mode toggle — V5 ships light-only.
- Email-specific V5 template — V4 email continues until web V5 stabilizes.
- PDF export — never asked for; defer indefinitely.
- 14-bubble all-sections risk map — chart is intentionally limited to a curated 7 per day.

## 2. Design principles

1. **Two layers of curation per edition.** Builders feed structured data for all 14 sections; an editorial Claude call picks today's 7 for the front-of-book risk map and 7 for the secondary "also today" grid. Every section still gets a full page deeper.
2. **Claude writes prose, never numbers.** All metric values trace to a deterministic builder. Claude composes editorial wrapping (banker's read, today's call, systemic-risk callout, pull quotes, headlines curation) from inputs that already exist as typed `SectionData`.
3. **Multi-paragraph banker's read.** V4's 4-sentence banker's read is replaced by a structured `{meaning, action, trigger, focus}` where each field is 80-150 words of prose, plus a one-line `pull_quote` for the risk map.
4. **Editorial QA as a pipeline stage.** A pre-flight Claude call reviews the assembled output and either approves or blocks the ship. Numbers consistency, contradiction detection, missing-content checks, tone, escaped-HTML scanning.
5. **Side-by-side coexistence with V4.** A `BRIEF_RENDERER` env flag selects v4 or v5 at runtime. Pilot section ships first; remaining 13 use V4 fallback in the same edition until templatized. Cutover is flipping the flag.

## 3. Architecture

### Module layout

```
brief/
├── schema.py                   # Pydantic — extended with V5 fields (back-compat)
├── render/
│   ├── v4/                     # Untouched. Used as fallback.
│   └── v5/                     # NEW
│       ├── __init__.py
│       ├── shell_v5.html       # Top-level page shell
│       ├── _jsx.py             # V5 helpers (extends v4 helpers; doesn't replace)
│       ├── _tokens.py           # Design tokens (oxblood, serif/mono pairing, spacing scale)
│       ├── tokens.css          # Same tokens emitted as :root CSS variables
│       ├── chrome/
│       │   ├── live_banner.py
│       │   ├── masthead.py
│       │   ├── todays_call.py
│       │   ├── risk_map.py
│       │   ├── secondary_grid.py
│       │   ├── front_of_book.py
│       │   └── colophon.py
│       └── templates/
│           ├── _section_base.py   # Shared per-section render shape
│           ├── section_bb.py
│           ├── section_macro.py
│           ├── section_fx.py
│           ├── section_remit.py
│           ├── section_dse.py
│           ├── section_tbond.py
│           ├── section_iranwar.py
│           ├── section_banking.py
│           ├── section_dam.py
│           ├── section_comm.py
│           ├── section_fiscal.py
│           ├── section_nbr.py
│           ├── section_headlines.py
│           └── section_exec.py
├── claude/
│   ├── max_client.py           # extended_thinking_budget kwarg added
│   ├── validators.py           # gains 4 new validators
│   └── prompts/
│       ├── top_picks.txt              # NEW (replaces risk_map_layout)
│       ├── todays_call.txt            # NEW
│       ├── bankerread_structured.txt  # NEW (replaces bankerread.txt)
│       ├── bankerread_stale.txt       # rewritten for multi-paragraph stale
│       ├── systemic_risk_callout.txt  # NEW
│       ├── editorial_qa.txt           # NEW
│       └── headlines_curation.txt     # rewritten for V5 voice
└── pipeline.py                 # gains BRIEF_RENDERER dispatch + Call 6 QA gate
```

### Data flow

```
04:30 BDT
   │
   ▼
1. GATHER (deterministic, V4 preserved) — EconDelta + Supabase metric_history + headlines scrape
   │
   ▼
2. BUILD SectionData (V4 preserved) — 14 builders, each emits SectionData with V5 fields populated
   │
   ▼
3. NARRATIVE — six Claude calls, all Opus 4.7 with extended thinking
      Call 1: top_picks (~$1)
      Call 2: headlines_curation (~$1)
      Call 3: todays_call (~$1)
      Call 4: bankerread_structured × 14 (~$2 each = $28)
      Call 5: systemic_risk_callout × N (~$1 each, ~3-7 active = $3-7)
      Call 6: editorial_qa (~$2)
   Total: ~$36-40 mid-quality, $50-60 max-quality
   │
   ▼
4. RENDER (BRIEF_RENDERER=v5 → render/v5/, else v4) — splice section fragments + chrome into shell_v5.html
   │
   ▼
5. EDITORIAL QA GATE
   pass → continue to step 6
   block → halt; preserve yesterday's index.html; Discord alert with reasons
   │
   ▼
6. PERSIST + DISTRIBUTE — Supabase upsert, git commit, push artifacts; email deferred until web V5 stable
```

## 4. Front-of-book chrome

The reader's first 700px of the page. Every element here is V5-new.

### 4.1 Live status banner

Top of page; oxblood (`var(--ox)`) background; mono font; pure data, no Claude.

```
LIVE · 06:15 BDT · DHAKA · USD/BDT 122.70 · DSEX 5,232 · BRENT $95.10 · RESERVES $34.12BN · NEXT UPDATE · 18:00 CLOSE
```

Source: a deterministic helper that pulls from EconDelta + Supabase. No editorial.

### 4.2 Masthead

```
VOL. II · NO. 412 · BANGLADESH · DAILY SUN-FRI · TUE 21 APR 2026

The Brief, plotted.                              [TODAY'S CALL panel: ~80 words editorial]
— Seven sections arranged by how much they
  moved and how much the book cares — not
  by section number.
```

Title: serif w/ italic accent on "Brief, plotted." (`<em class="italic-ox">`). Subtitle: italic serif, 11px. TODAY'S CALL panel: oxblood left border, ~80-word paragraph from Call 3 (`todays_call`).

### 4.3 Risk map (top-7)

Bubble plot: x = movement today (0-10), y = significance for the banker's book (0-10). Quadrant labels: SLOW STRUCTURAL (top-left), ACTIVE MATERIAL (top-right), DORMANT (bottom-left), NOISE (bottom-right). Bubbles colored by `kind`: oxblood (event), green (fresh print), gold (slow / structural), black (anchor). Per-bubble label = section number + kicker.

Plot positions and bubble radius come from Call 1 (`top_picks`). Selected sections are exactly 7. Validator enforces `len(plotted) == 7`.

### 4.4 Front-of-book section preview

Right side of the risk map. The single section Call 1 marks `front_of_book_id` gets a structured preview here:

- Section number + kicker (`§08 · IRAN · OIL`)
- Italic-serif title (`Risk premium — not scarcity.`)
- Highlighted callout (~30 words): the section's `pull_quote`
- 2-4 metric cards (Brent / WTI / War-risk premia / Feed-through)
- Action / Trigger paragraph from the section's `bankerread.action` and `bankerread.trigger` fields
- "JUMP TO §NN" anchor link

### 4.5 Secondary 7-card grid

Below the risk map, before the full section pages begin. One small card per *unfeatured* section (the 7 not on the map):

```
ALSO TODAY · 7 SECTIONS NOT ON THE MAP

[§09 Banking] · NPL 35.73% — historic high ▼ →
[§10 Comm]    · LNG JKM $10.4 — flat WoW · stale →
[§11 Fiscal]  · NBR collected 2.84tn YTD · stale →
[§12 NBR]     · VAT 38.2bn — Mar print due Sun · stale →
[§13 DAM]     · Onion +12% WoW ▼ →
[§14 Headlines] · 9 curated stories →
[§15 Exec]    · 6 prints · 3 watches →
```

Each card: kicker · tldr (≤12 words) · freshness pill · jump-arrow. The tldr is generated by Call 1 from each section's metrics + headlines (Claude doesn't write a separate tldr per section in a separate call — it batches into Call 1).

### 4.6 Colophon

Bottom of page. Volume / issue / date / sources used / total render time / total compute cost. Static; no editorial.

## 5. Per-section template

Every section uses the same shape. The shape is fully deterministic given populated `SectionData`. Empty optional fields are not rendered (no "Section Unavailable" stragglers).

```
§NN  KICKER · cadence-pill · freshness-pill                              [stale-banner if stale]

Italic-serif title (e.g. "Governor held. Again.")
TLDR line (e.g. "4th consecutive hold; credit growth undershooting.")

[3-PILL SUMMARY ROW]
[KEY METRIC pill]      [CHANGE pill]      [CONTEXT pill — optional]

[SYSTEMIC-RISK CALLOUT — only when systemic_risk is populated]
⚠  Headline (bold)
   Body paragraph from Call 5

[METRIC CARDS GRID — 3-4 cards]
[hero metric card with status badge: HISTORIC HIGH / RECORD LOW / CRITICAL / FLAT / WATCH]
[supporting metric cards]

[SPARKLINE — when ≥7 history rows exist for the section's primary metric]
12-point line chart from sparkline_svg(history_values)

[NEWS BULLETS — when section has news items]
●  Headline 1
   Lede paragraph (~40 words, from item.summary)
   SOURCE / DATE
●  Headline 2
   …

[BANKER'S READ panel — dark background, gold §A/B/C/D labels]
§A MEANING   80-150 word paragraph
§B ACTION    80-150 word paragraph
§C TRIGGER   80-150 word paragraph
§D FOCUS     80-150 word paragraph

[anchor link "← back to map"]
```

Each block is conditional on data. A "warming up" section without history shows kicker + title + 3-pill + the warming_up message. No fake placeholders.

## 6. Editorial pipeline — six Claude calls

All calls use Claude Max CLI subprocess with `claude-opus-4-7`, `--output-format json`, `--tools ""`, `--permission-mode bypassPermissions`. Extended thinking budget configurable per call; defaults below. Auth via `~/.claude/.credentials.json` on VPS.

### Call 1 — `top_picks`

- **When:** after all 14 builders have produced `SectionData`; before `bankerread_structured`.
- **Input:** array of all 14 sections' compact summaries: `{id, kicker, freshness, key_metric: {label, value, delta_pct, direction}, news_count, has_systemic_risk}`. Plus today's date and previous edition's `front_of_book_id` (for variety).
- **Job:** rank sections by today's signal, choose 7 to plot + 7 for grid. For each plotted section: `{id, x, y, r, kind: "event|fresh|slow|anchor"}`. For each grid section: `{id, tldr: ≤12 words}`. Choose `front_of_book_id`.
- **Output schema:** `TopPicks` (see §7).
- **Validator:** exactly 7 plotted, exactly 7 in grid, union covers all 14, `front_of_book_id` ∈ plotted, every `id` is a real section id.
- **Extended thinking:** 16k tokens. Encourages deliberate ranking.
- **Fallback on validator failure:** use deterministic significance scoring (today's `|delta_pct|` × `freshness_weight` + 5 if any systemic risk) — top 7 plotted, rest gridded, top by significance is `front_of_book_id`.

### Call 2 — `headlines_curation`

- **When:** parallel with Call 1.
- **Input:** 12-30 scraped headlines `{title, url, source, published}`.
- **Job:** select 8-15, classify domain, weight high/med/low, write 1-line rationale.
- **Output schema:** `{selected: [{url, domain, weight, lede: str (~40 words)}], rationale_bullet: str}`.
- **Validator:** every `url` ∈ input set; every `weight` ∈ {high, med, low}; lede 25-55 words.
- **Extended thinking:** 8k tokens.
- **Fallback:** display all scraped headlines without curation.

### Call 3 — `todays_call`

- **When:** after Call 1 and Call 2 (uses their outputs).
- **Input:** the 7 plotted sections' compact summaries + the curated headlines + the previous edition's `todays_call` text (for narrative continuity).
- **Job:** write a single ~80-word editorial paragraph for the masthead's TODAY'S CALL panel. Voice: declarative, banker-direct (e.g. *"Hormuz is priced risk, not scarcity. With food CPI sticky at 10.4% and reserves flat-not-building, the margin for a second incident is narrower than it looks. Hedge the oil book — not the headline."*).
- **Output schema:** `{text: str, byline: "Desk Editor · The Brief"}`.
- **Validator:** 60-100 words, no double quotes.
- **Extended thinking:** 12k tokens.
- **Fallback:** carry over yesterday's `todays_call` text with a "(carried over)" suffix.

### Call 4 — `bankerread_structured` (×14, one per section)

- **When:** after Calls 1+2 finish; can run in parallel across 14 sections.
- **Input:** the section's `SectionData` (metrics + freshness + news + history deltas) + today's `top_picks` placement (so Claude knows if section is featured) + previous edition's banker's read for the same section.
- **Job:** produce structured banker's read with four multi-paragraph fields:
  - `meaning` — what today's data means for the book (80-150 words)
  - `action` — a named action with exposure threshold (80-150 words)
  - `trigger` — a metric + threshold to watch (80-150 words)
  - `focus` — strategic focus for the week (80-150 words)
  Plus `pull_quote`: one editorial sentence (≤20 words) suitable for the risk map.
- **Output schema:** `BankerReadInsight` (see §7).
- **Validator:** each field is 60-180 words; `pull_quote` ≤20 words; no double quotes (template-breaking); no markdown fences.
- **Stale variant:** sections with `freshness != "fresh"` get `bankerread_stale.txt` — single 60-100 word paragraph that draws on news instead of metrics, plus the same `pull_quote` rule. Output schema: `BankerReadInsight(variant="stale_micro", meaning=<paragraph>, pull_quote=<line>, action=None, trigger=None, focus=None)`. V5 template branches on `variant`: when `stale_micro`, render only the `meaning` block + `pull_quote`; skip §B/§C/§D blocks.
- **Extended thinking:** 12k tokens per section.
- **Fallback:** per-section — use yesterday's banker's read with "(carried over from {date})" stamp.

### Call 5 — `systemic_risk_callout` (×N, conditional)

- **When:** after Call 4 for sections where the builder set `risk_active=True` based on deterministic rules (e.g. NPL > 30%, USD/BDT > 124, Brent 7-day Δ > +20%, reserves < $32bn).
- **Input:** the section's `SectionData` + the metrics that triggered the rule.
- **Job:** write a 60-100 word red-card paragraph: headline (≤12 words) + body explaining the systemic dimension and why it matters today.
- **Output schema:** `SystemicRisk { headline, body, level: "warning"|"critical" }`.
- **Validator:** body 50-110 words; level is bound to which rule fired.
- **Extended thinking:** 8k tokens.
- **Fallback:** suppress the callout for the day; section renders without it.

### Call 6 — `editorial_qa` (NEW — pre-flight)

- **When:** after assemble produces `index.html`, before push to git or email.
- **Input:** all section payloads (compact, ~6k tokens) + the rendered HTML stripped of CSS/script (~6k tokens). Total input ~12k.
- **Job:** scan for issues that should block the ship:
  1. **Numeric contradictions** across sections (e.g. one section: "DSEX rallied"; another: "DSEX fell").
  2. **Stale numbers** silently presented as fresh (`as_of` > 60d on a metric not flagged warming_up).
  3. **Empty editorial** where it should be populated (banker's read, systemic_risk callout, today's call).
  4. **Visible escaped HTML** (`&lt;span` or similar artifacts) in narrative text.
  5. **Tone breaks** — one section sounds frantic while everything else is calm, with no warrant from the data.
  6. **Missing front-of-book** elements (the chosen `front_of_book_id` section's `pull_quote` is empty).
  7. **Hallucinated URLs** in headlines (every URL in the rendered page must be in the input set).
- **Output schema:** `{ status: "pass" | "block", issues: [{section_id: str | null, severity: "info|warn|block", message: str}], shippable: bool }`.
- **Decision rule:** `shippable = (status == "pass") AND (no issue with severity == "block")`. If `shippable == false` → halt pipeline; preserve yesterday's `index.html` on `main`; Discord alert lists block reasons.
- **Validator:** schema validation only.
- **Extended thinking:** 16k tokens (maximum reasoning headroom for this gate).
- **Fallback if Call 6 itself fails (timeout, malformed output):** default to ship with Discord warning. Don't let infra failure on the QA gate block the ship — that becomes its own incident.

### Token + cost budget

| Call | Output | Extended thinking | $ estimate |
|---|---|---|---|
| 1 — top_picks | ~2k | 16k | $1.0 |
| 2 — headlines_curation | ~2k | 8k | $0.8 |
| 3 — todays_call | ~0.5k | 12k | $0.7 |
| 4 — bankerread_structured ×14 | ~3k each = 42k | 12k each | $2.0 × 14 = $28 |
| 5 — systemic_risk_callout ×~5 | ~0.5k each | 8k each | $0.7 × 5 = $3.5 |
| 6 — editorial_qa | ~1k | 16k | $1.5 |
| **Total** | ~50k output | — | **~$35** typical, **~$60** maximum |

## 7. Schema changes (`brief/schema.py`)

All changes are additive (V4 fields preserved); V4 renderer ignores new fields.

```python
# Existing types unchanged: Delta, Metric, NewsItem, FreshnessKind, CadenceKind

class BankerReadInsight(BaseModel):
    # Legacy V4 field — populated only when variant == "v4_legacy". V5 templates ignore.
    sentences: list[str] | None = None
    # V5 fields — populated for variant in {"full", "stale_micro"}. V4 templates ignore.
    # In stale_micro: only `meaning` and `pull_quote` are populated; action/trigger/focus = None.
    meaning: str | None = None
    action: str | None = None
    trigger: str | None = None
    focus: str | None = None
    pull_quote: str | None = None
    generated_at: datetime
    variant: Literal["full", "stale_micro", "v4_legacy"] = "full"

class SystemicRisk(BaseModel):
    headline: str
    body: str
    level: Literal["warning", "critical"]
    rule_id: str  # which deterministic rule fired

class MapPoint(BaseModel):
    id: str
    x: float
    y: float
    r: float
    kind: Literal["event", "fresh", "slow", "anchor"]

class GridEntry(BaseModel):
    id: str
    tldr: str  # ≤12 words

class TopPicks(BaseModel):
    plotted: list[MapPoint]   # exactly 7
    grid: list[GridEntry]     # exactly 7
    front_of_book_id: str

class TodaysCall(BaseModel):
    text: str
    byline: str = "Desk Editor · The Brief"
    generated_at: datetime

class QAIssue(BaseModel):
    section_id: str | None
    severity: Literal["info", "warn", "block"]
    message: str

class EditorialQAResult(BaseModel):
    status: Literal["pass", "block"]
    issues: list[QAIssue]
    shippable: bool

class SectionData(BaseModel):
    id: str
    title: str
    kicker: str                # NEW (was implied)
    tldr: str                  # NEW
    metrics: list[Metric]
    news: list[NewsItem]
    freshness: FreshnessKind
    freshness_reason: str | None = None
    bankerread: BankerReadInsight | None = None
    systemic_risk: SystemicRisk | None = None  # NEW; populated only when builder rule fires
    risk_active: bool = False                    # NEW; deterministic flag
    history_values: list[float] | None = None    # NEW; for sparkline rendering
```

## 8. Cadence and operations

- **Schedule:** `OnCalendar=Mon..Fri,Sun 02:30:00 UTC` (= 04:30 BDT). 2-hour buffer to 06:30 BDT publish.
- **Discord alerts:** triggered when (a) any Call 1-3 or Call 6 fails, (b) ≥3 of Call 4's 14 sections fail, (c) total duration > 100 min, (d) Call 6 returns `shippable=false`.
- **Rollback:** `BRIEF_RENDERER=v4` reverts to V4 templates immediately. `BRIEF_DRY_RUN=1` skips push entirely. Both env vars in `/etc/brief.env`.
- **Fallback editions:** if Call 6 blocks, the previous edition's `index.html` remains on `main`; the new edition is preserved on `shadow/<date>` for human review.

## 9. Visual style — design tokens

```python
# brief/render/v5/_tokens.py
COLORS = {
    "ox":         "#6b1f27",   # oxblood — accents, banner, brand
    "ink_1":      "#171310",   # body text
    "ink_3":      "#777",      # secondary text
    "ink_4":      "#aaa",      # tertiary
    "paper_1":    "#faf6ee",   # default page bg
    "paper_2":    "#f1ead9",   # card bg
    "paper_3":    "#e8e1cd",   # alt card bg
    "gold":       "#c89a3f",   # warn / attention
    "red":        "#a83a3a",   # critical
    "green":      "#3a8f4f",   # fresh / up
}
TYPE = {
    "serif_display":   "'Source Serif 4', 'Georgia', serif",
    "serif_text":      "'Source Serif 4', 'Georgia', serif",
    "mono":            "'JetBrains Mono', 'Menlo', monospace",
    "sans":            "'Inter', system-ui, sans-serif",
}
SPACE = {  # rem-multiples
    "xs": 0.25, "sm": 0.5, "md": 1, "lg": 1.5, "xl": 2.5, "2xl": 4,
}
```

Design tokens emit both as Python constants (used by render helpers) and as CSS `:root` variables (used by `shell_v5.html` stylesheet).

## 10. Out of scope

- Mobile-responsive layout
- Dark mode toggle
- Email-specific V5 template
- PDF export
- All-14-bubble static risk map
- Subscriber growth funnel / signup flow
- Internationalization (English-only)
- Comments / engagement / personalization

## 11. Success criteria

The V5 redesign is successful when all hold for 7 consecutive editions post-cutover:

1. All 14 sections render in V5 templates (no V4 fallback in mixed mode).
2. Top-7 picker chooses different sections day-to-day based on actual signal — not static.
3. Banker's read per section is multi-paragraph (≥60 words per field) and quotable.
4. Pre-flight Call 6 either passes cleanly or blocks legitimate issues; no false-positive blocks for ≥7 days.
5. 04:30 BDT start → 06:30 BDT publish, with ≥1 Claude rate-limit retry observed and survived.
6. Per-edition cost lands $30-90 (allow exploration; tighten after).
7. Visual artifact (`index.html`) is recognizably *The Brief* — a banker who saw the magazine reference can identify the V5 page as the same product.

## 12. References

- V4 spec: `docs/superpowers/specs/2026-04-21-the-brief-redesign.md`
- V5 visual reference: `docs/superpowers/v5-design-ref/The Brief v4 - Map Front.html` (from `claude.ai/design`)
- V5 content depth reference: `https://thebrief.clauding-lab.com/`
- V4 implementation tree: `brief/render/v4/`
- Brainstorming session: 2026-04-25 (this document is the output)
