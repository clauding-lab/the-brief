# The Long View v1.2.0 — composable blocks + mono/steel design system

**Date:** 2026-05-16
**Status:** Draft (post-brainstorm, awaiting plan)
**Target version:** v1.2.0
**Owner:** Adnan
**Prior versions:** v1.1.0 (text-only prose, shipped same day at `fa6bd41`)

---

## 1. Problem & Goal

v1.1.0 shipped a working pipeline (Discord/terminal → Claude Code → Vercel preview → publish) but the data model only supports one render shape: a title + lead + prose paragraphs + an optional chart placeholder + a banker takeaway. The first real upload — a structured comparison-grid infographic on BNP government prudential changes — collapsed into 3 paragraphs of narrative, losing the at-a-glance visual structure that the source was designed for.

There are TWO connected problems:

**a) The data model is too narrow.** A Long View today can only be "prose." Real slides come in many shapes (comparison grids, headline-metric callouts, structured takeaway lists, eventually charts/timelines/donuts). Each new shape needs its own render mode.

**b) The visual identity drifted.** v1.1.0's `.tb-longview*` CSS didn't specify `font-family`, so headings and paragraphs inherited browser-default serif (Georgia-ish). The rest of the brief is JetBrains Mono on the steel-crimson palette. The Long View shipped looking like a foreign object — different typography, accidentally warmer perceived background. Bug.

**Goal:** Replace the single-shape data model with a **composable block system**, ship four block kinds at launch, and fix the typography so the Long View renders in the brief's actual mono + steel design language. Claude composes a Long View from blocks; the brief provides the visual contract; the result blends with the rest of the issue.

**Design philosophy (from brainstorm):** *Claude is creative within the design theme.* The brief provides a small, well-designed visual vocabulary (4 block kinds, mono typography, steel-crimson palette, small-caps eyebrows, tone-tinted accents). Claude picks the right blocks for each slide and composes them; Claude does NOT invent new visual styles, new typography, new color choices.

## 2. Out of Scope

- **Chart rendering inside a Long View.** Deferred from v1.1.0 to v1.1.1, now deferred further to v1.3.0+ (or whenever a slide-with-chart upload makes the case). The `chart_spec` field from v1.1.0 is removed entirely; chart rendering will be a new `ChartBlock` kind added later via the block extension mechanism. No-op for v1.2.0.
- **Decorative icons.** Source slides often have icons (scales, percent, dollar, banned, etc.). The brief is icon-free today and v1.2.0 stays that way. The visual language leans on typography and tone tinting.
- **Mixing color palettes inside a Long View.** Claude does not get to introduce dark backgrounds, gradients, or non-brand colors even when the source slide has them. Always renders in the active brief palette.
- **Custom block kinds beyond the four shipped.** No "image embed," "video," "iframe," "table-with-arbitrary-columns," etc. If a slide doesn't fit the four kinds, use prose with a description.
- **Admin web UI for editing Long Views.** Still terminal/Discord only.
- **`/longview/archive` page or history index.** Git history remains the archive.
- **Per-pin CHANGELOG entries.** Routine Long View pins do not bump version or update CHANGELOG. Only platform-level changes (v1.2.x → v1.3.0) bump version.

## 3. User Experience

Same Discord/terminal trigger as v1.1.0. Same preview-then-publish flow via Vercel branch deployments. The only thing that changes is **what Copotron / Claude Code produces in `content/long-view.ts`** — instead of `body_paragraphs: string[]`, it produces `blocks: Block[]`, and the rendered output matches the slide's structure.

Example A — BNP rule-change slide (your first upload, redone):

```
EDITOR'S PIN · POSTED SAT 16 MAY

BNP government loosens six prudential rules in three months
Banking regulation across six dimensions has eased; the Interim
government's post-Hasina tightening is being reversed.

INTERIM → BNP-LED GOVERNMENT
[comparison block: 6 rows in a 2-col grid]

(optional closing prose)

BANKER READ
[the takeaway]
```

Example B — a headline-metric slide:

```
EDITOR'S PIN · POSTED FRI 22 MAY

Tier-1 NPL ratios show divergence widening, not narrowing
[lead]

[stat block: 3.8× ratio with framing paragraph]

[bullet-list block: 3 takeaway points]

BANKER READ
[the takeaway]
```

Example C — three-signals analytical slide:

```
EDITOR'S PIN · POSTED THU 21 MAY

Three signals from the May MPS that aren't in the headline
[lead]

[bullet-list block: 3 items with tone marks]

[prose block: closing context]

BANKER READ
[the takeaway]
```

Composition is the point — the slide's *structure*, not just its words, gets translated into the brief's visual language.

## 4. Architecture

```
┌───────────────────────────────────────────────────────────────┐
│  content/long-view.ts                                         │
│    export const longView: LongViewData | null = {             │
│      posted_at, title, lead,                                  │
│      blocks: [Block, Block, Block, ...],   ← NEW              │
│      banker_read,                                             │
│    }                                                          │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│  app/components/LongView.tsx (rewritten)                      │
│    1. Renders eyebrow (existing) + title + lead               │
│    2. Iterates data.blocks, switches on block.kind:           │
│       - prose       → <LongViewProse>                         │
│       - comparison  → <LongViewComparison>                    │
│       - stat        → <LongViewStat>                          │
│       - bullet-list → <LongViewBulletList>                    │
│    3. Renders banker_read takeaway                            │
│    4. Handles diff-stale state (existing)                     │
└───────────────────────────────────────────────────────────────┘
```

**Key properties:**
- **Backward-incompatible LongViewData**, but no live data exists to migrate (`content/long-view.ts` exports `null` since v1.1.0 shipped). Migration is zero-data — just update the type and any sample fixture.
- **Each block component is single-purpose** (~50-80 lines, one file each). Easy to test, easy to extend.
- **Type-safe discriminated union.** Adding a future block kind (e.g., `ChartBlock`, `TimelineBlock`) is purely additive — add a new union member + a new component, update the switch.
- **No new dependencies.** Pure TypeScript + React 19 + the existing CSS tokens.

## 5. File-Level Changes

| File | Status | Purpose |
|---|---|---|
| `types/brief.ts` | Updated | Replace `LongViewData.body_paragraphs` + `chart_spec` with `blocks: Block[]`. Add `Block` discriminated union + 4 block interfaces + `ComparisonRow` + `BulletListItem`. Remove `ChartSpec` + `ChartSpecSeries` + `ChartSpecAnnotation` (deferred chart support is no longer in this type system; will return when chart block ships). |
| `content/long-view.ts` | Unchanged | Still exports `null`. First v1.2.0 pin populates with the new shape. |
| `app/components/LongView.tsx` | Rewritten | Renders title + lead + blocks (switch on kind) + banker_read. Keeps diff-stale MutationObserver logic. |
| `app/components/LongViewProse.tsx` | **NEW** | Renders a prose block (1-3 paragraphs, max-width 70ch, mono italic? no — mono regular). |
| `app/components/LongViewComparison.tsx` | **NEW** | Renders comparison block: header + 2-col grid (auto-collapse to 1 on narrow). Tone-tinted AFTER values. |
| `app/components/LongViewStat.tsx` | **NEW** | Renders stat block: big mono number + optional unit + small-caps label + framing paragraph. Card-style on `paper-2` background. |
| `app/components/LongViewBulletList.tsx` | **NEW** | Renders bullet-list block: optional eyebrow + ul/li with tone-tinted marks. |
| `app/components/ClientApp.tsx` | Unchanged | Still imports `LongView` and `longView` exactly as in v1.1.0. The block dispatch is internal to LongView. |
| `app/globals.css` | Updated | Add CSS for each block class. **Explicitly set `font-family: var(--mono)` on every `.tb-longview*` class** to fix the v1.1.0 serif inheritance bug. Existing styles get the mono override; new block styles are mono-native. |
| `docs/longview-workflow.md` | Rewritten | Expanded recipe: editorial half adds "voice for each block kind"; operational half unchanged; **new section on block composition** — when to use prose vs comparison vs stat vs bullet-list, how to mix multiple blocks in one pin, what slide shapes map to what block combinations. |
| `CHANGELOG.md` | Updated | v1.2.0 entry: Added (4 block kinds), Changed (LongViewData breaking shape, mono typography enforced), Fixed (v1.1.0 serif bug), Deferred (chart rendering pushed further out). |
| `package.json` | Updated | `"version": "1.1.0"` → `"1.2.0"`. |

## 6. Data Shape — `LongViewData` v1.2.0

```typescript
// types/brief.ts (Long View section, replacing v1.1.0 types)

import type { Tone } from "@/types/brief"; // existing tone literal: "bull"|"bear"|"warn"|"neu"

// --- Block kinds (discriminated union by `kind`) ---

export interface ProseBlock {
  kind: "prose";
  paragraphs: string[];          // 1-3 paragraphs; never more
}

export interface ComparisonRow {
  title: string;                 // "Penal interest on overdue loans"
  before: string;                // "1.5%" | "BANNED" | "Revealed"
  after: string;                 // "0.5%" | "AT 7.5%" | "Rescheduled"
  description: string;           // 1-line context (required)
  tone?: Tone;                   // optional; only "bull"|"bear"|"neu" semantically meaningful here
}

export interface ComparisonBlock {
  kind: "comparison";
  before_label: string;          // "Interim government"
  after_label: string;           // "BNP-led government"
  rows: ComparisonRow[];         // 3-10 rows typical
  // Column count is auto-picked by the component: 2 default, 3 when rows.length >= 7.
}

export interface StatBlock {
  kind: "stat";
  value: string;                 // "3.8" | "12,400" | "10.0"
  unit?: string;                 // "×" | "CR" | "%" | "BPS"
  label: string;                 // small-caps eyebrow: "RATIO · TOP-HALF VS BOTTOM-HALF NPL"
  body: string;                  // 1-2 sentence framing paragraph
  tone?: Tone;                   // optional; tints just the value
}

export interface BulletListItem {
  text: string;                  // body text; supports inline **strong** via simple markdown-light
  tone?: Tone;                   // optional; tints just the leading mark
}

export interface BulletListBlock {
  kind: "bullet-list";
  eyebrow?: string;              // optional small-caps header
  items: BulletListItem[];       // 2-7 items
}

export type Block =
  | ProseBlock
  | ComparisonBlock
  | StatBlock
  | BulletListBlock;

// --- The Long View ---

export interface LongViewData {
  posted_at: string;             // ISO 8601 UTC (unchanged from v1.1.0)
  title: string;                 // 5–10 words (unchanged)
  lead: string;                  // 1–2 sentences (unchanged)
  blocks: Block[];               // REPLACES v1.1.0's body_paragraphs + chart_spec
  banker_read: string;           // 1 paragraph (unchanged)
}
```

**Migration from v1.1.0:** `content/long-view.ts` currently exports `null` (no live data). The breaking change to `LongViewData` is therefore zero-data. Any in-flight Long View draft branch (if any) needs to be rebased; one such branch (`longview/bnp-prudential-rollback` from the smoke test) was already cancelled.

## 7. Render Detail — Per Block

All blocks use:
- **Typography:** JetBrains Mono throughout (`font-family: var(--mono)`).
- **Palette:** active brief palette via tokens (`--paper`, `--paper-2`, `--ink`, `--ink-2`, `--ink-3`, `--rule`, `--rule-soft`, `--bull`, `--bear`, `--warn`, `--accent`).
- **Card surface:** `var(--paper-2)` for the slightly darker card background (works against any palette).
- **Spacing:** 24px vertical gap between consecutive blocks within one Long View.

### 7a. ProseBlock

```
<paragraph 1>

<paragraph 2>

<paragraph 3 — optional>
```

- 1-3 paragraphs, mono regular, 13.5px, line-height 1.65, max-width 70ch.
- 12px margin between paragraphs.
- No card wrapper — paragraphs sit directly on the Long View's background.

### 7b. ComparisonBlock

```
INTERIM → BNP-LED GOVERNMENT                ← small-caps header eyebrow
─────────────── (hair line)

┌─ row card ──────────┐  ┌─ row card ──────────┐
│ ROW TITLE           │  │ ROW TITLE           │
│ Interim    BNP-led  │  │ Interim    BNP-led  │
│ 1.5%       0.5%     │  │ 10%        1–2%     │  ← AFTER tinted bull/bear if tone set
│ description...       │  │ description...      │
└─────────────────────┘  └─────────────────────┘

(more row cards, 2 per row)
```

- Block header: small-caps with `before_label → after_label`.
- Hair rule below header.
- 2-column grid via CSS `repeat(2, 1fr)` with 14px gap. Auto-collapses to 1 column under 600px viewport.
- **Auto 3-column upgrade:** when `rows.length >= 7`, switch to `repeat(3, 1fr)` with 12px gap and tighter card padding. Component logic, no data field needed.
- Each row card: 1px `--rule-soft` border, `--paper-2` background, 14×16px padding.
- Row card structure:
  - `.row-title` — 10px small-caps, 0.18em letter-spacing, `--ink-3`, min-height 2.4em (keeps card heights aligned).
  - 2-col internal grid: `Interim` / `BNP-led` labels above values.
  - Values: 18px mono regular weight 300. AFTER value gets tone tint (`--bull` | `--bear` | `--warn`) when `tone` is set.
  - `.desc` — 12px mono regular, `--ink-2`.

### 7c. StatBlock

```
┌────────────────────────────────────────────────┐
│                                                │
│  3.8×        RATIO · TOP-HALF VS BOTTOM-HALF   │
│              The five healthiest Tier-1 banks  │
│              now sit at 2.1%...                │
│                                                │
└────────────────────────────────────────────────┘
```

- 2-col internal grid: `auto 1fr`, 28px gap, vertically centered.
- LEFT: big number — `clamp(40px, 5vw, 64px)`, mono weight 200, letter-spacing -0.03em. Unit (if present) renders inline at 0.5em size, `--ink-3` color.
- RIGHT: small-caps label (11px, 0.2em letter-spacing, `--ink-3`) above body paragraph (13px, line-height 1.55, `--ink-2`, max-width 50ch).
- Outer card: 1px `--rule` border (stronger than comparison rows because there's only one stat per block), `--paper-2` background, 24×28px padding.
- Tone tinting on the number when `tone` is set.
- Responsive: collapses to single column under 480px (number stacks above label/body).

### 7d. BulletListBlock

```
OPTIONAL EYEBROW (small-caps)
───────────────────

▸  **Strong leading clause.** Body of the bullet point follows...

▸  **Another bullet's lead.** With body text...

▸  Bullet without leading strong text. Plain body.
```

- Optional `eyebrow` rendered above as small-caps (10.5px, 0.22em letter-spacing) with hair rule below.
- `<ul>` with no default list style. Each `<li>` has internal grid `16px 1fr` — mark column + content column.
- Mark character: `▸` (right-pointing triangle); color follows `item.tone` (`--bull` | `--bear` | `--warn`; default `--ink-3`).
- Hair rule between items (`border-top: 1px solid --rule-soft`).
- Item text: 13px mono regular, line-height 1.55, `--ink-2`.
- **Markdown-light:** `**bold**` in `item.text` renders as `<strong>` with `font-weight: 600` and `color: --ink` (slightly darker than body). No other markdown — no italics, no links, no lists-within-lists. Implemented inline in `LongViewBulletList.tsx` with a simple regex replace.

## 8. Design System Contract

The Long View renders inside the brief's existing design tokens. Specifically:

| Token | What it is | Where used |
|---|---|---|
| `--mono` | JetBrains Mono font stack | Every `.tb-longview*` element (explicit, fixes v1.1.0 bug) |
| `--paper` | Active palette base background | Long View background (inherited from `body`) |
| `--paper-2` | Slightly darker card surface | Comparison row cards, Stat block card |
| `--paper-3` | Even darker accent surface | Reserved for future block kinds |
| `--ink` | Primary text color | Block titles, big numbers, strong text |
| `--ink-2` | Secondary text color | Body paragraphs, descriptions |
| `--ink-3` | Tertiary / muted text color | Eyebrows, labels, marks |
| `--rule` | Strong rule color | Stat card border, hair under block header |
| `--rule-soft` | Light divider color | Row card borders, list-item dividers |
| `--bull` | Green tone (oklch ~0.45 0.10 150) | Bullish tone tint on values + marks |
| `--bear` | Red tone (oklch ~0.55 0.21 25) | Bearish tone tint on values + marks |
| `--warn` | Amber tone (oklch ~0.62 0.14 75) | Warning tone tint on marks |
| `--accent` | Active palette accent (red/crimson) | Reserved; no v1.2.0 block uses it directly |

**Rules Claude follows:**
- Never specify hex colors, font families, or font sizes in content. The data layer carries only structural information; the component layer renders with these tokens.
- `tone` is opt-in per item/row. When unset, the element renders monochrome (`--ink` or `--ink-2`). Tone tinting is for *directional signal*, not decoration.
- The brief's palette is configurable (currently steel-crimson). The Long View renders correctly in any palette because it only uses tokens, never hard-coded colors.

## 9. Composition Rules (Recipe)

The `docs/longview-workflow.md` recipe is rewritten to teach Claude:

**Block selection — which kind for which shape:**

| Slide shape | Primary block | Often paired with |
|---|---|---|
| Argumentative essay / single-topic analysis | prose (1–3 paragraphs) | optional bullet-list closer |
| Before/after comparison grid (3+ rows) | comparison | optional prose intro + prose closing thought |
| Headline metric driving the slide | stat | bullet-list of supporting context, or prose for narrative |
| Listed takeaways (e.g., "Three signals") | bullet-list | optional prose intro |
| Mixed slide with intro + structure + closing | composed (multiple blocks) | up to ~4 blocks per pin |
| Slide that doesn't fit any of the above | prose with structural description in words | flag the gap in your reply to user |

**Hard constraints on composition:**
- Maximum 4 blocks per Long View. More than that = the slide should probably be two separate pins.
- Don't repeat the same block kind back-to-back (e.g., two prose blocks in a row → merge into one).
- `title`, `lead`, `banker_read` remain mandatory framing — blocks are the *middle* of the Long View, not the whole thing.
- Block ordering matters. Lead → first block (most important visual) → supporting blocks → closing block → banker_read.

**When to use prose despite a tempting structural block:**
- Comparison with only 1-2 rows → use prose, describe in words.
- Stat where the number is approximate or doesn't carry the slide → use prose.
- Bullet-list of 1 item → use prose, write the one point as a paragraph.
- Slide where the *prose carries the meaning* — even with some numbers — and structure would feel forced.

**When NOT to use a block:**
- The slide content can't be cleanly extracted into structured fields without inventing data. Always use prose + describe what you can't recreate.

## 10. Placement in the SPA

Unchanged from v1.1.0. The Long View renders between the Overview group and the Banking group in `ClientApp.tsx`. The `Fragment`-based wire-up and the `.tb-longview + .tb-group { margin-top: 64px }` margin rule both stay. Only the *internals* of `<LongView>` change.

## 11. Recipe Updates — `docs/longview-workflow.md`

The recipe file is rewritten end-to-end. Major changes from v1.1.0:

- **Section 2 (Editorial half)** — Output schema now shows `blocks: Block[]` instead of `body_paragraphs`. New subsection "block kinds" lists all 4 with examples.
- **New section: Block selection** — the table from §9 above, plus paired examples.
- **New section: Composition** — how to stack blocks within one Long View.
- **Forbiddens list updated:**
  - Remove "Do not emit chart_spec other than null" (chart_spec is gone).
  - Add "Do not introduce block kinds outside the four shipped (prose, comparison, stat, bullet-list)."
  - Add "Do not specify colors, fonts, or sizes in the data — the component renders with tokens."
- **Operational half — unchanged.** Same 10-step sequence (UUID → branch → read → edit → push → PR → wait Vercel → reply → handle response → hard rules).
- **The CHANGELOG-touching ambiguity that Copotron flagged** is resolved explicitly: "Per-pin Long View PRs touch ONLY `content/long-view.ts`. Do NOT touch `CHANGELOG.md` or `package.json` — those bump only on platform-level changes (v1.2.x → v1.3.0)."

## 12. Failure Modes

| Symptom | Likely cause | Action |
|---|---|---|
| Slide doesn't fit any block kind | Genuinely unique slide structure | Use prose with structural description; flag the gap in your reply so we can design a new block in a future v1.2.x |
| Comparison block has only 1-2 rows | Slide isn't really a comparison-grid | Fall back to prose; per recipe rule |
| Block component renders blank | Type mismatch in block data | `tsc` should catch this; if not, Vercel build fails and we fix the type |
| Composition feels wrong | Too many blocks (>4) | Reduce to 3-4; consider whether this should be two separate pins |
| Tone tinting feels overused | Tone set on every value | Recipe rule: tone is for directional signal, not decoration. Default to no tone. |
| User redo asks to "make it prose" | Editor disagrees with extracted structure | Re-run with `--redo --hint "use prose only"`; component falls back to prose easily |

## 13. Testing

Same static-check strategy as v1.1.0 (the brief has no JS/TS test framework today; adding one is still scope creep):

- `npx tsc --noEmit` — must pass with the new block union types.
- `npx next build` — must pass.
- `npx eslint app/components/LongView*.tsx` — must be clean for all 5 component files.
- **Vercel preview** is the primary visual verification. Each block kind is exercised by a sample data fixture during the implementation plan's smoke phase.
- Manual end-to-end smoke: upload a real PDF/JPEG via Discord, verify Copotron composes the right blocks, verify preview renders correctly, reply `cancel` to clean up.

## 14. Decisions Made

| Decision | Choice | Rationale |
|---|---|---|
| Data model | Composable blocks (discriminated union) | Single discriminator (option A) too rigid; generic markup (option C) too loose. Discriminated union with per-block-kind components gives type safety + composability. |
| Block kinds in v1.2.0 | 4 (prose, comparison, stat, bullet-list) | Covers ~80% of likely slide shapes per brainstorm. Future kinds (chart, timeline, donut, quote) deferred to v1.2.x when real uploads need them. |
| Column count for comparison | Auto-pick (2 default, 3 when rows ≥ 7) | Simpler data shape — one fewer field for Claude. Component decides. |
| Tone tinting | On by default (opt-in per item via `tone` field) | Gives directional signal when it matters; defaults to monochrome when unset. |
| Typography | Monospace everywhere (`font-family: var(--mono)` explicit) | Matches the brief's actual identity; fixes v1.1.0's serif inheritance bug. |
| Palette | Active brief palette via tokens (currently steel-crimson) | Never hard-code colors; render correctly under any palette. |
| Icons | None | Brief is icon-free; cream-paper editorial aesthetic doesn't need decorative icons. |
| Markdown in bullet-list items | `**bold**` only | Minimum useful emphasis; no full markdown to avoid scope creep. |
| File organization | Flat under `app/components/` with `LongView*` prefix | Matches existing brief conventions (BankerRead, BriefChart, SignatureChart all flat). |
| Chart support | Deferred again | No v1.2.0 chart uploads yet; `chart_spec` removed from types; will return as `ChartBlock` when needed. |
| CHANGELOG per-pin | No | Per-pin Long View PRs touch only `content/long-view.ts`. Platform changes (v1.2.x → v1.3.0) bump version. Resolves Copotron's ambiguity flag. |

## 15. Open Questions / Deferred

- **Chart block kind.** When the first user upload contains a critical chart, design + ship `ChartBlock` as v1.3.0. Likely Chart.js-based, reusing the brief's existing `BriefChart` setup with a Long-View-specific adapter.
- **Timeline block.** For slides showing temporal progression. Defer until needed.
- **Quote/pull-out block.** For slides built around a single authoritative quote. Defer.
- **Donut/breakdown block.** For pie/donut percentage splits. Defer.
- **Markdown-light extensions in prose.** Currently prose paragraphs are plain strings. If editors want `**bold**` in prose too, mirror the bullet-list implementation.
- **Block-level tone defaults.** Currently tone is per-item. A future enhancement might let blocks set a default tone applied to all internal items (e.g., a "all rows are bullish" comparison block).
- **Stale-branch cleanup cron on Hetzner.** Still deferred from v1.1.0.

## 16. Definition of Done

- [ ] `types/brief.ts` updated: `LongViewData.blocks: Block[]` replaces `body_paragraphs` + `chart_spec`. All 6 new block-related interfaces present. `ChartSpec`, `ChartSpecAnnotation`, `ChartSpecSeries` removed.
- [ ] `app/components/LongView.tsx` rewritten: switches on `block.kind` and dispatches to per-block components. Keeps diff-stale MutationObserver.
- [ ] 4 new component files created (`LongViewProse`, `LongViewComparison`, `LongViewStat`, `LongViewBulletList`).
- [ ] `app/globals.css` updated: explicit `font-family: var(--mono)` on every `.tb-longview*` class. New CSS for each block kind. Comparison grid auto-promotes 2→3 columns at ≥7 rows.
- [ ] `docs/longview-workflow.md` rewritten with the block vocabulary, composition rules, and updated forbiddens.
- [ ] CHANGELOG v1.2.0 entry with Added / Changed / Fixed / Deferred sections.
- [ ] `package.json` version bumped to `1.2.0`.
- [ ] `npx tsc --noEmit` clean.
- [ ] `npx next build` clean.
- [ ] `npx eslint` clean.
- [ ] Vercel preview renders all 4 block kinds correctly (via temporary sample data on the feature branch; reverted to `null` before merge).
- [ ] Mono + steel rendering verified visually — the Long View now blends with the rest of the brief.
- [ ] Manual end-to-end smoke test: re-upload the BNP PDF to Copotron, verify the output is now a comparison block (not collapsed prose), reply `publish` to a real Long View, verify production.
- [ ] After merge: tag `v1.2.0`, push, `gh release create` with notes from CHANGELOG.

---

## References

- `docs/superpowers/specs/2026-05-16-the-long-view-design.md` — v1.1.0 spec (parent).
- `docs/superpowers/plans/2026-05-16-the-long-view.md` — v1.1.0 plan.
- v1.1.0 release: https://github.com/clauding-lab/the-brief/releases/tag/v1.1.0
- v1.1.0 PR: https://github.com/clauding-lab/the-brief/pull/73
- Smoke-test PR (cancelled): https://github.com/clauding-lab/the-brief/pull/74
- Brainstorm mockups: `.superpowers/brainstorm/9226-1778950150/content/` (gitignored)
