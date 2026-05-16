# The Long View v1.2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace v1.1.0's single-shape LongView data model with a composable block system (prose / comparison / stat / bullet-list), rendered in the brief's actual mono + steel-crimson design language. Also fixes v1.1.0's serif inheritance bug.

**Architecture:** Discriminated `Block` union in `types/brief.ts`. One render component per block kind under `app/components/LongView*Block-ish.tsx`. The existing `LongView.tsx` becomes a thin dispatcher that iterates `data.blocks` and switches on `block.kind`. CSS rewrite enforces explicit `font-family: var(--mono)` on every `.tb-longview*` class and adds new per-block classes.

**Tech Stack:** TypeScript + React 19 + Next.js 16 (App Router). No new dependencies. No new test framework (continues v1.1.0's tsc + eslint + next build + Vercel preview verification strategy).

**Spec:** `docs/superpowers/specs/2026-05-16-the-long-view-v1.2.0-design.md`

---

## Scope Decisions Locked

- 4 block kinds in v1.2.0: `prose`, `comparison`, `stat`, `bullet-list`.
- `LongViewData.blocks: Block[]` replaces `body_paragraphs` + `chart_spec` (atomic breaking change; safe because `content/long-view.ts` exports `null` today).
- `ChartSpec`, `ChartSpecAnnotation`, `ChartSpecSeries` interfaces removed entirely (chart support deferred — will return as `ChartBlock` in v1.3.0+ when needed).
- Comparison auto-picks columns: 2-col default, 3-col when `rows.length >= 7`. No `columns` field in data.
- Tone tinting (`"bull" | "bear" | "warn" | "neu"`) is optional per-item, defaults to monochrome.
- Markdown-light in bullet-list items: `**bold**` only.
- Mono explicit on every `.tb-longview*` class (fix v1.1.0 serif inheritance bug).
- Active brief palette via tokens only — never hard-code colors or fonts in components.
- Same SPA placement: between Overview group and Banking group via `Fragment` in `ClientApp.tsx`. No wire-up changes.
- No new tests / no test framework adoption — continues the existing static-check + Vercel preview verification.

---

## Task 1: Update types — add Block union + new block interfaces, remove ChartSpec types

**Files:**
- Modify: `types/brief.ts`

- [ ] **Step 1: Read the current Long View section in `types/brief.ts`**

Run: `grep -n "Long View\|LongView\|ChartSpec\|Block" /Users/adnanrashid/conductor/workspaces/the-brief/beirut/types/brief.ts`
Expected output (after v1.1.0): lines showing `ChartSpecSeries`, `ChartSpecAnnotation`, `ChartSpec`, `LongViewData` interfaces.

- [ ] **Step 2: Replace the entire Long View section (interfaces `ChartSpecSeries`, `ChartSpecAnnotation`, `ChartSpec`, and `LongViewData`) with the v1.2.0 type set**

Find the existing block:

```typescript
// --- Long View (pinned editorial insert, v1.1.0+) ---

export interface ChartSpecSeries {
  name: string;
  data: Array<[string | number, number]>; // [x, y] tuples; x can be a label or ISO date
}

export interface ChartSpecAnnotation {
  x: string | number;
  label: string;
}

export interface ChartSpec {
  kind: "line" | "bar" | "stacked_bar" | "donut";
  title: string;
  x_axis: string;
  y_axis: string;
  series: ChartSpecSeries[];
  annotations?: ChartSpecAnnotation[];
}

export interface LongViewData {
  posted_at: string;          // ISO 8601 UTC; rendered to Asia/Dhaka in the eyebrow
  title: string;              // 5–10 words, no trailing punctuation
  lead: string;               // 1–2 sentences
  body_paragraphs: string[];  // 1–3 paragraphs
  chart_spec: ChartSpec | null; // v1.1.0: always null. v1.1.1: chart-capable.
  banker_read: string;        // 1 paragraph takeaway
}
```

Replace it with:

```typescript
// --- Long View (pinned editorial insert, v1.2.0+) ---
// v1.2.0 replaces the single-shape model with a composable Block system.
// ChartSpec types removed; chart rendering will return as a `ChartBlock`
// kind in v1.3.0+ when the first chart-bearing upload arrives.

export interface ProseBlock {
  kind: "prose";
  paragraphs: string[];          // 1-3 paragraphs; never more
}

export interface ComparisonRow {
  title: string;                 // "Penal interest on overdue loans"
  before: string;                // "1.5%" | "BANNED" | "Revealed"
  after: string;                 // "0.5%" | "AT 7.5%" | "Rescheduled"
  description: string;           // 1-line context (required)
  tone?: Tone;                   // optional; "bull"|"bear"|"neu" semantically meaningful
}

export interface ComparisonBlock {
  kind: "comparison";
  before_label: string;          // "Interim" — short, 1-2 words ideal
  after_label: string;           // "BNP-led" — short, 1-2 words ideal
  rows: ComparisonRow[];         // 3-10 rows typical; auto 3-col grid when >= 7
}

export interface StatBlock {
  kind: "stat";
  value: string;                 // "3.8" | "12,400" | "10.0"
  unit?: string;                 // "×" | "CR" | "%" | "BPS" — rendered smaller
  label: string;                 // small-caps eyebrow text
  body: string;                  // 1-2 sentence framing paragraph
  tone?: Tone;                   // optional; tints just the value
}

export interface BulletListItem {
  text: string;                  // supports inline **bold** via markdown-light
  tone?: Tone;                   // optional; tints just the leading mark
}

export interface BulletListBlock {
  kind: "bullet-list";
  eyebrow?: string;              // optional small-caps header above the list
  items: BulletListItem[];       // 2-7 items
}

export type Block =
  | ProseBlock
  | ComparisonBlock
  | StatBlock
  | BulletListBlock;

export interface LongViewData {
  posted_at: string;             // ISO 8601 UTC (unchanged from v1.1.0)
  title: string;                 // 5–10 words (unchanged)
  lead: string;                  // 1–2 sentences (unchanged)
  blocks: Block[];               // REPLACES v1.1.0's body_paragraphs + chart_spec
  banker_read: string;           // 1 paragraph (unchanged)
}
```

The new types reference `Tone` which already exists at the top of `types/brief.ts` (`export type Tone = "bull" | "bear" | "warn" | "neu";`).

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd /Users/adnanrashid/conductor/workspaces/the-brief/beirut && npx tsc --noEmit 2>&1 | head -30`
Expected: errors in `app/components/LongView.tsx` because it still references `data.body_paragraphs` and `data.chart_spec`. THIS IS EXPECTED — we'll fix LongView.tsx in Task 6. For now, no other files should error.

If other files (besides LongView.tsx) show errors, stop and report.

- [ ] **Step 4: Commit**

```bash
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut add types/brief.ts
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut commit -m "feat(longview): v1.2.0 types — Block union + 4 block kinds (LongView.tsx temporarily broken)"
```

---

## Task 2: Create `LongViewProse.tsx`

**Files:**
- Create: `app/components/LongViewProse.tsx`

- [ ] **Step 1: Create the file with this exact content**

```typescript
import type { ProseBlock } from "@/types/brief";

interface LongViewProseProps {
  block: ProseBlock;
}

export function LongViewProse({ block }: LongViewProseProps) {
  return (
    <div className="tb-longview-prose">
      {block.paragraphs.map((paragraph, i) => (
        <p key={i}>{paragraph}</p>
      ))}
    </div>
  );
}
```

No `"use client"` directive — this is a pure render component. It inherits client-bundling from the `LongView.tsx` parent (which IS `"use client"`).

- [ ] **Step 2: Verify TypeScript compiles for this file in isolation**

Run: `cd /Users/adnanrashid/conductor/workspaces/the-brief/beirut && npx tsc --noEmit 2>&1 | grep -E "LongViewProse" | head -10`
Expected: no errors mentioning `LongViewProse.tsx`. (The pre-existing `LongView.tsx` errors are still present from Task 1 — that's expected.)

- [ ] **Step 3: Commit**

```bash
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut add app/components/LongViewProse.tsx
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut commit -m "feat(longview): add LongViewProse block component"
```

---

## Task 3: Create `LongViewComparison.tsx`

**Files:**
- Create: `app/components/LongViewComparison.tsx`

- [ ] **Step 1: Create the file with this exact content**

```typescript
import type { ComparisonBlock } from "@/types/brief";

interface LongViewComparisonProps {
  block: ComparisonBlock;
}

// Auto-pick column count: 2 default, 3 when the row count crosses the
// threshold where vertical scroll becomes the bigger cost than internal
// card cramping. Tuned at >= 7 from the visual mockup tradeoff.
const THREE_COLUMN_THRESHOLD = 7;

export function LongViewComparison({ block }: LongViewComparisonProps) {
  const useThreeColumns = block.rows.length >= THREE_COLUMN_THRESHOLD;
  const gridClass = useThreeColumns
    ? "tb-longview-cmp-grid-3"
    : "tb-longview-cmp-grid-2";

  return (
    <div className="tb-longview-cmp">
      <div className="tb-longview-cmp-header">
        {block.before_label} &nbsp;→&nbsp; {block.after_label}
      </div>
      <div className="tb-longview-cmp-rule" />
      <div className={gridClass}>
        {block.rows.map((row, i) => {
          const afterToneClass = row.tone
            ? `tb-longview-cmp-val-${row.tone}`
            : "";
          return (
            <div key={i} className="tb-longview-cmp-row">
              <div className="tb-longview-cmp-row-title">{row.title}</div>
              <div className="tb-longview-cmp-vals">
                <div>
                  <div className="tb-longview-cmp-lab">{block.before_label}</div>
                  <div className="tb-longview-cmp-val">{row.before}</div>
                </div>
                <div>
                  <div className="tb-longview-cmp-lab">{block.after_label}</div>
                  <div className={`tb-longview-cmp-val ${afterToneClass}`.trim()}>
                    {row.after}
                  </div>
                </div>
              </div>
              <p className="tb-longview-cmp-desc">{row.description}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify the file compiles**

Run: `cd /Users/adnanrashid/conductor/workspaces/the-brief/beirut && npx tsc --noEmit 2>&1 | grep -E "LongViewComparison" | head -10`
Expected: no errors mentioning `LongViewComparison.tsx`.

- [ ] **Step 3: Commit**

```bash
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut add app/components/LongViewComparison.tsx
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut commit -m "feat(longview): add LongViewComparison block (auto 2/3 col grid, tone tint)"
```

---

## Task 4: Create `LongViewStat.tsx`

**Files:**
- Create: `app/components/LongViewStat.tsx`

- [ ] **Step 1: Create the file with this exact content**

```typescript
import type { StatBlock } from "@/types/brief";

interface LongViewStatProps {
  block: StatBlock;
}

export function LongViewStat({ block }: LongViewStatProps) {
  const toneClass = block.tone ? `tb-longview-stat-tone-${block.tone}` : "";
  return (
    <div className="tb-longview-stat">
      <div className={`tb-longview-stat-num ${toneClass}`.trim()}>
        {block.value}
        {block.unit && (
          <span className="tb-longview-stat-unit">{block.unit}</span>
        )}
      </div>
      <div className="tb-longview-stat-meta">
        <div className="tb-longview-stat-label">{block.label}</div>
        <p className="tb-longview-stat-body">{block.body}</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify the file compiles**

Run: `cd /Users/adnanrashid/conductor/workspaces/the-brief/beirut && npx tsc --noEmit 2>&1 | grep -E "LongViewStat" | head -10`
Expected: no errors mentioning `LongViewStat.tsx`.

- [ ] **Step 3: Commit**

```bash
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut add app/components/LongViewStat.tsx
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut commit -m "feat(longview): add LongViewStat block (big mono number + framing)"
```

---

## Task 5: Create `LongViewBulletList.tsx`

**Files:**
- Create: `app/components/LongViewBulletList.tsx`

- [ ] **Step 1: Create the file with this exact content**

```typescript
import type { ReactNode } from "react";
import type { BulletListBlock } from "@/types/brief";

interface LongViewBulletListProps {
  block: BulletListBlock;
}

// Markdown-light: split text on **...** segments and render <strong> for each.
// No other markdown features (no italic, no links, no nested lists).
// Regex is anchored to a non-greedy match between paired **...**.
function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    const match = part.match(/^\*\*([^*]+)\*\*$/);
    if (match) {
      return <strong key={i}>{match[1]}</strong>;
    }
    return <span key={i}>{part}</span>;
  });
}

export function LongViewBulletList({ block }: LongViewBulletListProps) {
  return (
    <div className="tb-longview-bullets">
      {block.eyebrow && (
        <>
          <div className="tb-longview-bullets-eyebrow">{block.eyebrow}</div>
          <div className="tb-longview-bullets-rule" />
        </>
      )}
      <ul>
        {block.items.map((item, i) => {
          const toneClass = item.tone
            ? `tb-longview-bullets-tone-${item.tone}`
            : "";
          return (
            <li key={i} className={toneClass}>
              <span className="tb-longview-bullets-mark">▸</span>
              <span>{renderInline(item.text)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Verify the file compiles**

Run: `cd /Users/adnanrashid/conductor/workspaces/the-brief/beirut && npx tsc --noEmit 2>&1 | grep -E "LongViewBulletList" | head -10`
Expected: no errors mentioning `LongViewBulletList.tsx`.

- [ ] **Step 3: Commit**

```bash
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut add app/components/LongViewBulletList.tsx
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut commit -m "feat(longview): add LongViewBulletList block (markdown-light bold + tone marks)"
```

---

## Task 6: Rewrite `LongView.tsx` as a block dispatcher

**Files:**
- Modify: `app/components/LongView.tsx` (full rewrite)

- [ ] **Step 1: Replace the entire contents of `app/components/LongView.tsx` with this**

```typescript
"use client";

import { useEffect, useState } from "react";
import type { Block, LongViewData } from "@/types/brief";
import { Hair } from "./Hair";
import { formatLongViewEyebrow } from "@/lib/format";
import { LongViewProse } from "./LongViewProse";
import { LongViewComparison } from "./LongViewComparison";
import { LongViewStat } from "./LongViewStat";
import { LongViewBulletList } from "./LongViewBulletList";

interface LongViewProps {
  data: LongViewData | null;
}

// Compare today vs posted_at, both interpreted in Asia/Dhaka, returning true
// when today's calendar date is STRICTLY after the posted calendar date.
// Uses en-CA locale because it formats as YYYY-MM-DD which sorts lexically.
function isPostedBeforeToday(postedAt: string): boolean {
  const posted = new Date(postedAt);
  if (isNaN(posted.getTime())) return false;
  const opts: Intl.DateTimeFormatOptions = { timeZone: "Asia/Dhaka" };
  const todayBDT = new Date().toLocaleDateString("en-CA", opts);
  const postedBDT = posted.toLocaleDateString("en-CA", opts);
  return todayBDT > postedBDT;
}

// Dispatch a block to its render component by discriminator.
function renderBlock(block: Block, index: number) {
  switch (block.kind) {
    case "prose":
      return <LongViewProse key={index} block={block} />;
    case "comparison":
      return <LongViewComparison key={index} block={block} />;
    case "stat":
      return <LongViewStat key={index} block={block} />;
    case "bullet-list":
      return <LongViewBulletList key={index} block={block} />;
  }
}

export function LongView({ data }: LongViewProps) {
  const [stale, setStale] = useState(false);

  useEffect(() => {
    if (!data) return;

    const recompute = () => {
      const diffOn = document.body.classList.contains("tb-diff");
      setStale(diffOn && isPostedBeforeToday(data.posted_at));
    };

    recompute();

    // Watch for diff-mode toggle (ClientApp toggles body.tb-diff via classList).
    const obs = new MutationObserver(recompute);
    obs.observe(document.body, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, [data]);

  if (!data) return null;

  return (
    <section
      id="longview"
      className={`tb-longview${stale ? " tb-diff-stale" : ""}`}
      aria-labelledby="longview-title"
    >
      <div className="tb-longview-eyebrow">{formatLongViewEyebrow(data.posted_at)}</div>
      <Hair style={{ marginTop: 12, marginBottom: 20 }} />

      <h2 id="longview-title" className="tb-longview-title">
        {data.title}
      </h2>

      <p className="tb-longview-lead">{data.lead}</p>

      <div className="tb-longview-blocks">
        {data.blocks.map((block, i) => renderBlock(block, i))}
      </div>

      <Hair style={{ marginTop: 28, marginBottom: 16 }} />
      <div className="tb-longview-takeaway">
        <div className="tb-longview-takeaway-label">BANKER READ</div>
        <p>{data.banker_read}</p>
      </div>
    </section>
  );
}
```

Key changes from v1.1.0:
- Removed `data.body_paragraphs.map` JSX
- Removed `data.chart_spec` placeholder JSX
- Added 4 component imports (`LongViewProse`, `LongViewComparison`, `LongViewStat`, `LongViewBulletList`)
- Added `renderBlock()` dispatcher function
- Added `<div className="tb-longview-blocks">` wrapper for block iteration
- Imported `Block` type (in addition to `LongViewData`)

- [ ] **Step 2: Update `content/long-view.ts` comment to reference the new shape**

Replace the contents of `content/long-view.ts` with:

```typescript
import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = null;
```

(Only the comment changes — the export still emits `null`.)

- [ ] **Step 3: Verify TypeScript compiles end-to-end**

Run: `cd /Users/adnanrashid/conductor/workspaces/the-brief/beirut && npx tsc --noEmit 2>&1 | tail -20`
Expected: clean exit, no errors. The earlier Task 1 break is now fixed.

- [ ] **Step 4: Verify ESLint is clean across all changed files**

Run: `cd /Users/adnanrashid/conductor/workspaces/the-brief/beirut && npx eslint app/components/LongView.tsx app/components/LongViewProse.tsx app/components/LongViewComparison.tsx app/components/LongViewStat.tsx app/components/LongViewBulletList.tsx content/long-view.ts 2>&1 | tail -20`
Expected: no errors. (Warnings about unused vars or React rules should be addressed before commit.)

- [ ] **Step 5: Verify the build is clean**

Run: `cd /Users/adnanrashid/conductor/workspaces/the-brief/beirut && npx next build 2>&1 | tail -20`
Expected: build completes; no errors. (CSS will look broken until Task 7 lands, but build itself must pass — only HTML/JS is compiled at this stage.)

- [ ] **Step 6: Commit**

```bash
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut add app/components/LongView.tsx content/long-view.ts
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut commit -m "feat(longview): rewrite LongView as block dispatcher"
```

---

## Task 7: Rewrite Long View CSS in `app/globals.css`

**Files:**
- Modify: `app/globals.css` (replace the v1.1.0 Long View section at the end)

- [ ] **Step 1: Find the existing v1.1.0 Long View CSS block**

Run: `grep -n "Long View (pinned editorial insert" /Users/adnanrashid/conductor/workspaces/the-brief/beirut/app/globals.css`
Expected: one line, the section header comment.

- [ ] **Step 2: Replace the v1.1.0 section (everything from that header comment to end-of-file) with the v1.2.0 CSS**

Old block (everything from `/* --- The Long View (pinned editorial insert, v1.1.0+) --- */` to EOF) is replaced with:

```css
/* --- The Long View (pinned editorial insert, v1.2.0+) --- */
/* All .tb-longview* classes set font-family explicitly to fix the v1.1.0
   serif inheritance bug where headings rendered in browser-default serif. */

.tb-longview {
  padding: 56px 0 48px;
  margin-top: 12px;
  margin-bottom: 12px;
  scroll-margin-top: 110px;
  border-top: 1px solid var(--rule-soft);
  border-bottom: 1px solid var(--rule-soft);
  font-family: var(--mono);
}
.tb-longview * { font-family: var(--mono); }

.tb-longview-eyebrow {
  font-size: 10.5px;
  letter-spacing: 0.22em;
  color: var(--ink-3);
  font-weight: 600;
  text-transform: uppercase;
}

.tb-longview-title {
  font-size: clamp(24px, 2.8vw, 36px);
  line-height: 1.12;
  font-weight: 400;
  letter-spacing: -0.02em;
  margin: 0 0 14px;
  text-wrap: balance;
  color: var(--ink);
}

.tb-longview-lead {
  font-size: 14px;
  line-height: 1.55;
  font-style: italic;
  color: var(--ink-2);
  margin: 0 0 24px;
  max-width: 62ch;
}

/* Vertical gap between consecutive blocks */
.tb-longview-blocks > * + * {
  margin-top: 24px;
}

/* --- Prose block --- */
.tb-longview-prose p {
  font-size: 13.5px;
  line-height: 1.65;
  margin: 0 0 12px;
  max-width: 70ch;
  color: var(--ink-2);
}
.tb-longview-prose p:last-child { margin-bottom: 0; }

/* --- Comparison block --- */
.tb-longview-cmp-header {
  font-size: 10.5px;
  letter-spacing: 0.22em;
  color: var(--ink-3);
  font-weight: 600;
  text-transform: uppercase;
  margin-bottom: 12px;
}
.tb-longview-cmp-rule {
  height: 1px;
  background: var(--rule);
  margin-bottom: 14px;
}
.tb-longview-cmp-grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.tb-longview-cmp-grid-3 {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}
@media (max-width: 600px) {
  .tb-longview-cmp-grid-2,
  .tb-longview-cmp-grid-3 {
    grid-template-columns: 1fr;
  }
}
.tb-longview-cmp-row {
  border: 1px solid var(--rule-soft);
  padding: 14px 16px;
  background: var(--paper-2);
}
.tb-longview-cmp-grid-3 .tb-longview-cmp-row {
  padding: 12px 14px;
}
.tb-longview-cmp-row-title {
  font-size: 10px;
  letter-spacing: 0.18em;
  color: var(--ink-3);
  text-transform: uppercase;
  font-weight: 600;
  margin: 0 0 12px;
  line-height: 1.45;
  min-height: 2.4em;
}
.tb-longview-cmp-vals {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 8px;
}
.tb-longview-cmp-lab {
  font-size: 9.5px;
  letter-spacing: 0.18em;
  color: var(--ink-3);
  text-transform: uppercase;
  margin-bottom: 3px;
}
.tb-longview-cmp-val {
  font-size: 18px;
  color: var(--ink);
  font-weight: 300;
  letter-spacing: -0.01em;
  line-height: 1.1;
}
.tb-longview-cmp-grid-3 .tb-longview-cmp-val { font-size: 17px; }
.tb-longview-cmp-val-bull { color: var(--bull); }
.tb-longview-cmp-val-bear { color: var(--bear); }
.tb-longview-cmp-val-neu  { color: var(--ink); }
.tb-longview-cmp-desc {
  font-size: 12px;
  line-height: 1.5;
  color: var(--ink-2);
  margin: 0;
}

/* --- Stat block --- */
.tb-longview-stat {
  border: 1px solid var(--rule);
  padding: 24px 28px;
  background: var(--paper-2);
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 28px;
  align-items: center;
}
@media (max-width: 480px) {
  .tb-longview-stat {
    grid-template-columns: 1fr;
    gap: 14px;
  }
}
.tb-longview-stat-num {
  font-size: clamp(40px, 5vw, 64px);
  font-weight: 200;
  letter-spacing: -0.03em;
  line-height: 0.95;
  color: var(--ink);
}
.tb-longview-stat-unit {
  font-size: 0.5em;
  color: var(--ink-3);
  margin-left: 4px;
}
.tb-longview-stat-tone-bull { color: var(--bull); }
.tb-longview-stat-tone-bear { color: var(--bear); }
.tb-longview-stat-tone-warn { color: var(--warn); }
.tb-longview-stat-tone-neu  { color: var(--ink); }
.tb-longview-stat-label {
  font-size: 11px;
  letter-spacing: 0.2em;
  color: var(--ink-3);
  text-transform: uppercase;
  font-weight: 600;
  margin-bottom: 8px;
}
.tb-longview-stat-body {
  font-size: 13px;
  line-height: 1.55;
  color: var(--ink-2);
  margin: 0;
  max-width: 50ch;
}

/* --- Bullet-list block --- */
.tb-longview-bullets-eyebrow {
  font-size: 10.5px;
  letter-spacing: 0.22em;
  color: var(--ink-3);
  font-weight: 600;
  text-transform: uppercase;
}
.tb-longview-bullets-rule {
  height: 1px;
  background: var(--rule-soft);
  margin: 8px 0 0;
}
.tb-longview-bullets ul {
  list-style: none;
  padding: 0;
  margin: 0;
}
.tb-longview-bullets li {
  display: grid;
  grid-template-columns: 16px 1fr;
  gap: 10px;
  padding: 10px 0;
  border-top: 1px solid var(--rule-soft);
  font-size: 13px;
  line-height: 1.55;
  color: var(--ink-2);
}
.tb-longview-bullets li:first-child {
  border-top: 0;
  padding-top: 4px;
}
.tb-longview-bullets-mark {
  color: var(--ink-3);
  font-weight: 600;
}
.tb-longview-bullets-tone-bull .tb-longview-bullets-mark { color: var(--bull); }
.tb-longview-bullets-tone-bear .tb-longview-bullets-mark { color: var(--bear); }
.tb-longview-bullets-tone-warn .tb-longview-bullets-mark { color: var(--warn); }
.tb-longview-bullets strong {
  font-weight: 600;
  color: var(--ink);
  letter-spacing: -0.005em;
}

/* --- Banker read takeaway (kept from v1.1.0, mono explicit) --- */
.tb-longview-takeaway {
  padding: 12px 0;
}
.tb-longview-takeaway-label {
  font-size: 10.5px;
  letter-spacing: 0.22em;
  color: var(--ink-3);
  font-weight: 600;
  margin-bottom: 10px;
}
.tb-longview-takeaway p {
  font-size: 17px;
  line-height: 1.5;
  font-weight: 300;
  letter-spacing: -0.005em;
  margin: 0;
  max-width: 65ch;
  text-wrap: pretty;
}

/* Diff-stale state (kept from v1.1.0) */
.tb-longview.tb-diff-stale {
  opacity: 0.42;
  filter: blur(1px);
  pointer-events: none;
  transition: opacity 200ms ease, filter 200ms ease;
}

/* Sibling-margin restore — Banking group sits after LongView, not after
   a .tb-group, so the existing .tb-group + .tb-group rule doesn't match.
   (Kept from v1.1.0.) */
.tb-longview + .tb-group {
  margin-top: 64px;
}
```

Note what's REMOVED from the v1.1.0 block:
- `.tb-longview-chart-placeholder` rule (chart block deferred; no consumer)
- `.tb-longview-body p` rule (replaced by `.tb-longview-prose p` since the v1.1.0 body became a block)

- [ ] **Step 3: Verify the build is clean**

Run: `cd /Users/adnanrashid/conductor/workspaces/the-brief/beirut && npx next build 2>&1 | tail -20`
Expected: build completes; no CSS parse errors.

- [ ] **Step 4: Commit**

```bash
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut add app/globals.css
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut commit -m "feat(longview): rewrite CSS for v1.2.0 blocks (mono explicit, new block classes)"
```

---

## Task 8: Rewrite `docs/longview-workflow.md` recipe

**Files:**
- Modify: `docs/longview-workflow.md` (full rewrite)

- [ ] **Step 1: Replace the entire contents of `docs/longview-workflow.md` with this content**

```markdown
# The Long View — workflow (v1.2.0)

This file is the contract for the Long View workflow on The Brief. It has two halves: **Editorial** (what to write) and **Operational** (how to ship it). Both halves must be followed for every Long View pin.

The Long View is a pinned editorial section between the Overview group and the Banking group on The Brief's SPA. It replaces whatever was previously pinned. Posted at most once per week. The output is composed from a small block vocabulary in the brief's visual language (mono + steel-crimson palette + tone tinting where it earns its keep).

**v1.2.0 design philosophy:** *Be creative within the design theme.* The brief provides four block kinds (`prose`, `comparison`, `stat`, `bullet-list`) and a strict visual contract (mono typography, palette tokens only, small-caps eyebrows, optional tone tinting). Compose blocks to match the source slide's structure. Do not invent new block kinds, new typography, or new colors.

---

## Trigger

The user sends a Discord message to Copotron (Hetzner) OR types in their local Claude Code terminal session:

```
<attach PDF or JPEG>
longview
   — OR —
longview - <optional hint to steer your framing>
```

When you see this pattern, follow this entire workflow without improvising.

---

## Editorial half — what you write

### Audience

The Brief is read by banking professionals in Bangladesh — business heads (corporate, SME, retail), risk heads, treasury heads at Tier-1 banks. Write for that reader.

### Voice register

- Banker-native vocabulary: NPL, CRR, repo, SDF, Sukuk, ALCO, MPS, BB, Tier-1 capital, provisioning, advance-deposit ratio.
- Concrete numbers; never round away precision the source provides.
- Implications oriented to credit committees, ALCO, treasury desks.
- No journalese ("amid", "in a stunning move", "moreover"), no LLM tells ("delve", "myriad", "tapestry"), no hedging when the source is clear.

### Output schema

Edit `content/long-view.ts` to look exactly like this (filling in your extracted data):

```typescript
import type { LongViewData } from "@/types/brief";

export const longView: LongViewData | null = {
  posted_at: "<ISO 8601 UTC timestamp — use now()>",
  title: "<5–10 words, no trailing punctuation>",
  lead: "<1–2 sentences setting up the insight>",
  blocks: [
    // 1–4 blocks; pick the right kinds for the slide
  ],
  banker_read: "<1 paragraph; the takeaway for a banker reader>",
};
```

### Block kinds

You compose `blocks: []` using these four kinds. Always pick the kind that matches the source slide's structure — do not force a structural block when prose carries the meaning.

**1. Prose** — paragraphs of analysis. Use when the slide is text-driven (an argument, narrative, single-topic analysis) or when no clean structure can be extracted.

```typescript
{
  kind: "prose",
  paragraphs: [
    "<paragraph 1>",
    "<paragraph 2>",
    // 1–3 paragraphs; never more
  ],
}
```

**2. Comparison** — before/after rows with descriptions. Use when the slide is a structured comparison grid (3+ rows of paired values). Each row has a title, before value, after value, and a 1-line description. Optional `tone` per row tints the AFTER value (`"bull"` green for positive direction, `"bear"` red for negative, `"neu"` monochrome).

```typescript
{
  kind: "comparison",
  before_label: "<short label, 1–2 words ideal>",  // e.g., "Interim"
  after_label: "<short label, 1–2 words ideal>",   // e.g., "BNP-led"
  rows: [
    {
      title: "<row title>",
      before: "<value>",          // "1.5%" | "BANNED" | "Revealed"
      after: "<value>",           // "0.5%" | "AT 7.5%" | "Rescheduled"
      description: "<1-line context>",
      tone: "bull",               // optional
    },
    // 3–10 rows typical; 7+ auto-promotes to 3-column grid
  ],
}
```

Keep `before_label` and `after_label` SHORT (1–2 words). They appear both at the block header and inside each row card.

**3. Stat** — a single headline metric. Use when the slide is built around one number (a ratio, a percentage, a count) with framing context. The value renders huge mono; the label and body sit beside it.

```typescript
{
  kind: "stat",
  value: "<numeric string>",       // "3.8" | "12,400" | "10.0"
  unit: "<optional unit>",         // "×" | "CR" | "%" | "BPS"
  label: "<small-caps eyebrow>",   // e.g., "RATIO · TOP-HALF VS BOTTOM-HALF NPL"
  body: "<1–2 sentence framing>",
  tone: "bear",                    // optional; tints just the value
}
```

**4. Bullet-list** — structured points. Use for "three signals" / "what we learned" / "key takeaways" slides. Items can use `**bold**` markdown-light for leading emphasis. Optional `tone` per item tints the leading mark (▸).

```typescript
{
  kind: "bullet-list",
  eyebrow: "<optional small-caps header>",
  items: [
    { text: "**Strong lead.** Body of the point.", tone: "bull" },
    { text: "Plain point without leading bold.", tone: "warn" },
    // 2–7 items
  ],
}
```

### Composition rules

| Slide shape | Primary block | Often paired with |
|---|---|---|
| Argumentative essay / single-topic analysis | `prose` (1–3 paragraphs) | optional `bullet-list` closer |
| Before/after comparison grid (3+ rows) | `comparison` | optional `prose` intro + `prose` closing thought |
| Headline metric driving the slide | `stat` | `bullet-list` of supporting context, or `prose` for narrative |
| Listed takeaways (e.g., "Three signals") | `bullet-list` | optional `prose` intro |
| Mixed slide (intro + structure + closing) | composed (multiple blocks) | up to ~4 blocks per pin |
| Slide that doesn't fit any of the above | `prose` with structural description | flag the gap in your reply to the user |

**Hard constraints:**
- Maximum **4 blocks** per Long View. More than that, the slide should probably be two pins.
- Don't repeat the same block kind back-to-back. Two prose blocks in a row → merge.
- `title`, `lead`, `banker_read` remain mandatory framing. Blocks are the *middle* of the Long View.
- Block ordering: lead → most-important visual block first → supporting blocks → closing block → banker_read.

**When to fall back to prose despite a tempting structural block:**
- Comparison with only 1–2 rows → use prose.
- Stat where the number is approximate or doesn't actually carry the slide → use prose.
- Bullet-list of 1 item → use prose with that item as a paragraph.
- Slide where prose carries the meaning even with some numbers → use prose.

### Forbiddens

- **Do not fabricate numbers** not in the source. If the slide is unclear, reply to the user and stop.
- **Do not introduce block kinds outside the four shipped** (`prose`, `comparison`, `stat`, `bullet-list`).
- **Do not specify colors, fonts, sizes, or styles in the data.** The component renders with palette tokens. Your job is structural data; the brief handles the visual contract.
- **Do not add a source-attribution field** (no "Source: BB MPS, May 2026" line).
- **Do not add a "view original" link.**
- **Do not fold opinion into the lead.** Opinion lives in `banker_read`.
- **Do not edit `CHANGELOG.md` or `package.json`** in a Long View pin PR. Per-pin PRs touch ONLY `content/long-view.ts`. Platform version bumps (v1.2.x → v1.3.0) happen in separate platform-change PRs.

---

## Operational half — how you ship it

### 0. Where to run this

- **On Hetzner (Copotron via Discord):** the repo lives at `/home/adnan/the-brief/`.
- **On the user's Mac (local Claude Code):** the repo lives at `~/Projects/clauding-lab/the-brief/` OR inside a Conductor workspace under `~/conductor/workspaces/the-brief/<name>/`. Confirm with `git rev-parse --show-toplevel` if unsure.

### 1. Save the source

Generate a UUID for the source file and save it:

```bash
UUID=$(python3 -c "import uuid; print(uuid.uuid4())")
EXT="<pdf or jpg, from the attachment>"
mkdir -p pins
# Move/copy the attachment to pins/$UUID.$EXT
```

Keep this file path — you may need to re-read it on a `redo`.

### 2. Branch off main

```bash
git fetch origin main
git checkout main
git pull
git checkout -b longview/<3-4-word-slug-from-your-read>
```

### 3. Read the source

Open the PDF or JPEG and extract per the Editorial half above. If a hint was provided after `longview - `, weight your framing toward it.

### 4. Edit `content/long-view.ts`

Replace the entire contents with the new `longView` export per the schema. Use the appropriate block kind(s). Verify locally:

```bash
npx tsc --noEmit
```

### 5. Commit and push

```bash
git add content/long-view.ts
git commit -m "longview: <title in lowercase, ~10 words>"
git push -u origin longview/<your-slug>
```

### 6. Open a PR for the Vercel preview

```bash
gh pr create \
  --head longview/<your-slug> \
  --base main \
  --title "longview: <title>" \
  --body "Pinned Long View update. Preview will be ready shortly. Source kept at pins/$UUID.$EXT."
```

### 7. Wait for Vercel preview

```bash
gh pr checks --watch
gh pr view --json statusCheckRollup --jq '.statusCheckRollup[] | select(.context // .name | test("Vercel")) | .targetUrl // .detailsUrl' | head -1
```

Capture the preview URL — that's what you reply to the user with.

### 8. Reply to the user

```
Draft ready.
Preview: <vercel-preview-url>
Reply with one of:
  publish
  redo: <new hint>
  cancel
```

### 9. Handle the user's response

**`publish`** — Merge to main:

```bash
gh pr merge <pr-number> --squash --delete-branch
```

Reply: `Merged to main. Vercel deploying production. Live on thebrief.clauding-lab.com — pinned until replaced.`

**`redo: <hint>`** — Re-read the same source file with the new hint:

```bash
# Re-read pins/$UUID.$EXT, re-extract per the new hint
# Edit content/long-view.ts with the new data
git commit -am "longview: redo per hint — <hint summary>"
git push --force-with-lease=longview/<slug>:$(git rev-parse HEAD~1) origin longview/<slug>
# If the no-arg --force-with-lease fails because the remote-tracking ref
# doesn't exist (Conductor workspace quirk), use the fetch+FETCH_HEAD fallback:
#   git fetch origin longview/<slug>
#   git push --force-with-lease=longview/<slug>:$(git rev-parse FETCH_HEAD) origin longview/<slug>
gh pr checks --watch
```

Reply with the (same) preview URL once the rebuild completes.

**`cancel`** — Close the PR, delete the branch, delete the source:

```bash
gh pr close <pr-number> --delete-branch
rm -f pins/$UUID.$EXT
```

Reply: `Cancelled. Draft deleted.`

### 10. Hard rules — do not break

- **Never merge to main without showing the user the Vercel preview URL first.**
- **Never commit the PDF/JPEG to the repo.** Only `content/long-view.ts` changes in this PR.
- **Never edit `content/long-view.ts` outside this workflow.**
- **Never edit `CHANGELOG.md` or `package.json` in a Long View pin PR.**
- **If anything goes wrong** (Vercel build fails, git push fails, source unreadable), reply to the user with the exact error and stop. Do not auto-retry on shared-state writes.

---

## Failure modes — quick reference

| Symptom | Likely cause | Action |
|---|---|---|
| `npx tsc --noEmit` fails after your edit | Type mismatch in your new `longView` value | Re-check the `LongViewData` + `Block` shapes in `types/brief.ts`; fix and retry. |
| Vercel build fails on the preview | Runtime React error from the new data | Pull the failure summary from `gh pr checks`, fix locally, push. If still failing, hand back to user. |
| `gh pr merge` fails | Merge conflict on `content/long-view.ts` | Surface the error verbatim. Rebase or ask the user. Don't auto-resolve. |
| User goes silent after preview | Normal | Draft branch sits indefinitely. Leave it. |
| Slide doesn't fit any block kind | Genuinely unique structure | Use `prose` with descriptive paragraphs; flag the gap in your reply so the user can design a new block kind in a future v1.2.x. |
| User starts a second `longview` before resolving first | Pending draft conflict | Reply: "There's an open Long View draft on branch `longview/<previous>` (preview: …). Cancel or treat as redo?" |

---

## Quick reference — what files this workflow touches

| File | Why |
|---|---|
| `content/long-view.ts` | The pinned data. Edit per workflow. |
| `pins/<uuid>.<ext>` | Local copy of the source on disk. Not in git. |

That's it. Everything else (the component, the styles, the wiring, the recipe) lives outside the per-pin workflow and is not edited here.
```

- [ ] **Step 2: Commit**

```bash
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut add docs/longview-workflow.md
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut commit -m "docs(longview): rewrite recipe for v1.2.0 blocks + composition rules"
```

---

## Task 9: CHANGELOG + version bump to v1.2.0

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `package.json`

- [ ] **Step 1: Read the current top of `CHANGELOG.md`**

Run: `head -10 /Users/adnanrashid/conductor/workspaces/the-brief/beirut/CHANGELOG.md`
Expected: current top entry is v1.1.0.

- [ ] **Step 2: Insert a new v1.1.0 entry — wait, v1.2.0 — ABOVE the `## [1.1.0]` heading**

Insert this entry directly above the `## [1.1.0]` heading (with one blank line between the new entry and the v1.1.0 heading):

```markdown
## [1.2.0] — 2026-05-18

### Added
- **Composable Long View blocks.** `LongViewData.blocks: Block[]` replaces `body_paragraphs` + `chart_spec`. Four block kinds ship: `prose`, `comparison`, `stat`, `bullet-list`. Claude composes a Long View by stacking blocks; mixing kinds within a single pin is supported.
- `LongViewProse`, `LongViewComparison`, `LongViewStat`, `LongViewBulletList` — one render component per block kind, each in its own file under `app/components/`.
- Auto column-count for comparison block: 2-col default, 3-col when row count ≥ 7.
- Optional tone tinting (`"bull" | "bear" | "warn" | "neu"`) on comparison row AFTER values, stat values, and bullet-list marks. Defaults to monochrome.
- Markdown-light (`**bold**`) inside bullet-list item text.

### Changed
- **Mono typography enforced.** Every `.tb-longview*` CSS class now sets `font-family: var(--mono)` explicitly. Fixes the v1.1.0 inheritance bug where headings rendered in browser-default serif.
- `LongView.tsx` is now a thin dispatcher: iterates `data.blocks` and switches on `block.kind` to render the right block component. The eyebrow / title / lead / banker_read structure is unchanged.
- `docs/longview-workflow.md` recipe rewritten with the block vocabulary, composition rules, and the explicit "per-pin PRs touch only `content/long-view.ts`" rule (resolves the CHANGELOG ambiguity that surfaced in v1.1.0).

### Fixed
- v1.1.0 Long View rendered in serif because the CSS didn't specify `font-family`. v1.2.0 makes mono explicit on every `.tb-longview*` class so the section blends with the rest of the brief.

### Removed
- `ChartSpec`, `ChartSpecAnnotation`, `ChartSpecSeries` interfaces removed from `types/brief.ts`.
- `chart_spec` field on `LongViewData` removed.
- `.tb-longview-chart-placeholder` and `.tb-longview-body p` CSS rules removed (replaced by per-block CSS).

### Deferred
- Chart rendering. Will return as a `ChartBlock` kind in v1.3.0+ when the first chart-bearing slide upload arrives. Until then, slides with charts should describe the chart's shape in a `prose` block (per the recipe).
```

- [ ] **Step 3: Bump `package.json` version from `1.1.0` to `1.2.0`**

Edit `package.json`, change line 3 from:
```json
  "version": "1.1.0",
```
to:
```json
  "version": "1.2.0",
```

- [ ] **Step 4: Verify both files**

```bash
head -5 /Users/adnanrashid/conductor/workspaces/the-brief/beirut/CHANGELOG.md
grep '"version"' /Users/adnanrashid/conductor/workspaces/the-brief/beirut/package.json
```
Expected: CHANGELOG shows the new v1.2.0 entry at the top; package.json shows `"version": "1.2.0"`.

- [ ] **Step 5: Commit**

```bash
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut add CHANGELOG.md package.json
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut commit -m "chore(v1.2.0): bump version 1.1.0 -> 1.2.0 + CHANGELOG entry"
```

---

## Task 10: Push branch, open PR, verify on Vercel preview

**Files:** None (operational task).

- [ ] **Step 1: Push the feature branch**

```bash
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut push -u origin clauding-lab/long-view-v1.2.0
```
Expected: branch pushed.

- [ ] **Step 2: Open the PR (with explicit `--head` per Conductor workspace quirk)**

```bash
cd /Users/adnanrashid/conductor/workspaces/the-brief/beirut && gh pr create \
  --head clauding-lab/long-view-v1.2.0 \
  --base main \
  --title "feat(v1.2.0): The Long View — composable blocks + mono/steel" \
  --body "$(cat <<'EOF'
## Summary

v1.2.0 replaces v1.1.0's single-shape Long View data model with a composable
block system, and fixes the serif inheritance bug so the section finally
renders in the brief's actual mono + steel-crimson design language.

- Spec: \`docs/superpowers/specs/2026-05-16-the-long-view-v1.2.0-design.md\`
- Plan: \`docs/superpowers/plans/2026-05-16-the-long-view-v1.2.0.md\`

## What's in this PR

- Four block kinds: \`prose\`, \`comparison\`, \`stat\`, \`bullet-list\`.
- \`LongViewData.blocks: Block[]\` replaces \`body_paragraphs\` + \`chart_spec\`.
- One render component per block kind (\`LongViewProse\`, \`LongViewComparison\`,
  \`LongViewStat\`, \`LongViewBulletList\`).
- \`LongView.tsx\` rewritten as a thin dispatcher.
- CSS rewrite: every \`.tb-longview*\` class sets \`font-family: var(--mono)\`
  explicitly (fixes v1.1.0 serif bug).
- Recipe rewritten with block vocabulary, composition rules, and the
  per-pin / per-platform CHANGELOG distinction.
- \`ChartSpec*\` types removed; chart rendering deferred to v1.3.0+.

## Test plan

- [x] \`npx tsc --noEmit\` clean
- [x] \`npx next build\` clean
- [x] \`npx eslint\` clean
- [ ] Vercel preview deploys green
- [ ] Visual check on preview: null state renders no Long View section
- [ ] Visual check on preview: temporarily seed sample data exercising all 4
      block kinds; verify the section renders in mono + steel; verify
      diff-stale state blurs the section when posted_at is in the past
- [ ] Revert sample data to \`null\` before merge
EOF
)"
```

- [ ] **Step 3: Wait for Vercel preview to finish building**

```bash
gh pr checks --watch
```

Once green, extract the preview URL:

```bash
gh pr view --json statusCheckRollup \
  --jq '.statusCheckRollup[] | select(.name // .context | tostring | test("Vercel")) | .targetUrl // .detailsUrl' \
  | head -1
```

Also fetch the Vercel auto-comment for the human-friendly preview URL (the one ending in `.vercel.app`):

```bash
gh pr view --json comments --jq '.comments[].body' | grep -oE "https://the-brief-git-[a-z0-9-]+\.vercel\.app" | head -1
```

- [ ] **Step 4: Smoke 1 — null state**

Open the preview URL. Expected:
- Page renders normally.
- NO Long View section visible (because `longView === null`).
- Sections in normal order: Overview → Banking → Markets → Real Economy → Policy.
- No console errors.

- [ ] **Step 5: Smoke 2 — temporarily seed sample data exercising all 4 block kinds**

Edit `content/long-view.ts` temporarily:

```typescript
import type { LongViewData } from "@/types/brief";

export const longView: LongViewData | null = {
  posted_at: "2026-05-12T00:30:00Z",
  title: "BNP government loosens six prudential rules in three months",
  lead: "Banking regulation across six dimensions has eased in the BNP government's first three months, reversing the Interim government's post-Hasina tightening.",
  blocks: [
    {
      kind: "stat",
      value: "6",
      unit: "",
      label: "RULES EASED · FIRST 90 DAYS",
      body: "Across penal interest, loan exit, lending caps, conversion factors, pre-merger return, and NPL treatment — all six dimensions move in the same loosening direction.",
      tone: "bull",
    },
    {
      kind: "comparison",
      before_label: "Interim",
      after_label: "BNP-led",
      rows: [
        { title: "Penal interest on overdue loans", before: "1.5%", after: "0.5%", description: "Reduces punitive measures, loosens borrower burden.", tone: "bull" },
        { title: "Loan exit downpayment", before: "10%", after: "1–2%", description: "Significant barrier reduction for loan closure.", tone: "bull" },
        { title: "Single group lending cap (funded)", before: "15%", after: "25%", description: "Enhanced corporate access to credit.", tone: "bull" },
        { title: "Non-funded conversion factor", before: "0.50", after: "0.25", description: "Reduced risk weighting for non-cash instruments.", tone: "bull" },
        { title: "Pre-merger owner return", before: "BANNED", after: "AT 7.5%", description: "Selective re-entry permitted at a set threshold.", tone: "bull" },
        { title: "Non-performing loan (NPL) treatment", before: "Revealed", after: "Rescheduled", description: "Focus on repayment planning over public disclosure." },
      ],
    },
    {
      kind: "bullet-list",
      eyebrow: "What to watch next",
      items: [
        { text: "**Provisioning rules.** Likely the next BNP move; current 1% general provision feels conservative given the rest of the loosening.", tone: "warn" },
        { text: "**Tier-1 bank quarterly results.** Q1 numbers from the four banks reporting late May will show whether the easing flows through to recovery rates.", tone: "bull" },
        { text: "Public disclosure norms could tighten again under opposition pressure. Watch the Parliamentary Standing Committee minutes." },
      ],
    },
    {
      kind: "prose",
      paragraphs: [
        "The pattern is consistent across all six rule changes: punitive measures soften, capacity opens, and disclosure-heavy obligations get replaced with operational ones. None of these changes individually moves the needle on a healthy bank's economics. Together, they widen the operating envelope for the entire industry.",
      ],
    },
  ],
  banker_read: "Treasury desks pricing fixed-rate Ijara product against the upcoming MPS should anchor on the corridor, not the cut-off. If the corridor narrows, the Sukuk curve repricing will be steep — re-hedge before the May 28 auction window.",
};
```

Push:

```bash
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut add content/long-view.ts
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut commit -m "test(longview): temporarily seed sample data for v1.2.0 preview smoke"
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut push
```

Wait for Vercel rebuild:

```bash
gh pr checks --watch
```

- [ ] **Step 6: Smoke 2 verification on the preview URL**

Open the preview URL (refresh if already open). Expected:
- Long View section renders between Overview and Banking.
- Eyebrow reads `EDITOR'S PIN · POSTED TUE 12 MAY` (or Mon, depending on locale).
- Title and lead render in MONO (the brief's actual typography).
- Background is the brief's steel-crimson cool gray (not warm cream).
- **Block 1 (stat):** big mono "6" on the left, label + body on the right.
- **Block 2 (comparison):** 6 rows in a 2-col grid (3 rows × 2 cols), each row card has Interim/BNP-led labeled values, AFTER values are tinted green (`tone: bull`) except the NPL treatment row (no tone).
- **Block 3 (bullet-list):** eyebrow "What to watch next", 3 items with mixed tone marks.
- **Block 4 (prose):** single paragraph at the bottom.
- BANKER READ section at the very bottom of the LongView.
- No console errors.

Test diff-mode:

```javascript
// In browser DevTools console:
localStorage.setItem("thebrief.diffMode", "1");
location.reload();
```

After reload, expected:
- Body has class `tb-diff`.
- Long View section is blurred + dimmed (`.tb-diff-stale` applied because `posted_at` 2026-05-12 < today).
- The section is non-interactive.

Disable diff mode and reload to confirm the section returns to full opacity.

- [ ] **Step 7: Revert the sample data to `null`**

```bash
cat > /Users/adnanrashid/conductor/workspaces/the-brief/beirut/content/long-view.ts <<'EOF'
import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = null;
EOF

git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut add content/long-view.ts
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut commit -m "chore(longview): revert sample data, ship with null state"
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut push
gh pr checks --watch
```

Verify the preview URL once more:
- No Long View section visible.
- Normal section order restored.

- [ ] **Step 8: Pause for user approval**

Reply to the user with the preview URL and ask: "Smoke checks passed. All 4 block kinds rendered correctly in mono + steel; diff-stale works; null state ships. Ready to merge to main and tag v1.2.0?"

Do NOT merge until the user replies `yes` / `publish` / `merge`.

---

## Task 11: Merge to main, tag v1.2.0, push tag, create GitHub release

**Files:** None (operational task).

- [ ] **Step 1: Merge the PR (only after user approval from Task 10 Step 8)**

```bash
gh pr merge <pr-number> --squash --delete-branch
```

Per session memory, `gh pr merge` from Conductor workspaces errors locally with `'main' is already used by worktree at ...` but ALWAYS succeeds server-side. Verify with:

```bash
gh pr view <pr-number> --json state,mergeCommit --jq '.state + " " + (.mergeCommit.oid // "")'
```

Expected: `MERGED <sha>`.

- [ ] **Step 2: Tag v1.2.0 on the squash-merge commit**

```bash
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut fetch origin main
MERGE_SHA=$(gh pr view <pr-number> --json mergeCommit --jq .mergeCommit.oid)
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut tag -a v1.2.0 "$MERGE_SHA" -m "v1.2.0 — Composable blocks + mono/steel

Replaces v1.1.0's single-shape Long View data model with a composable block
system. Four block kinds: prose, comparison, stat, bullet-list. Claude
composes a Long View by stacking blocks in the brief's visual language
(mono typography, steel-crimson palette, optional tone tinting).

Fixes v1.1.0's serif inheritance bug.

Chart support deferred again — will return as ChartBlock in v1.3.0+ when
a chart-bearing slide upload arrives."
git -C /Users/adnanrashid/conductor/workspaces/the-brief/beirut push origin v1.2.0
```

- [ ] **Step 3: Create the GitHub release**

```bash
cat > /tmp/release-notes-v1.2.0.md <<'EOF'
## v1.2.0 — Composable blocks + mono/steel

Replaces v1.1.0's single-shape Long View data model with a composable block system. Four block kinds ship: `prose`, `comparison`, `stat`, `bullet-list`. Claude composes a Long View by stacking blocks; mixing kinds in one pin is supported.

### Highlights

- **Four blocks → many slide shapes.** A comparison-grid slide becomes a `comparison` block. A headline-metric slide becomes a `stat` block. A "three signals" slide becomes a `bullet-list`. A narrative essay becomes `prose`. Real slides usually mix.
- **Brief's actual design language.** Mono typography (JetBrains Mono) is now explicit on every `.tb-longview*` class. Renders in the active palette (currently steel-crimson) via tokens only — no hard-coded colors.
- **Optional tone tinting** for directional signal: `"bull"` (green), `"bear"` (red), `"warn"` (amber), `"neu"` (monochrome). Defaults to monochrome.
- **Comparison auto-promotes** from 2-col to 3-col grid when row count ≥ 7.
- **Markdown-light** (`**bold**`) inside bullet-list items.

### Fixed

- v1.1.0's Long View shipped in browser-default serif because the CSS didn't specify `font-family`. v1.2.0 makes mono explicit on every class.

### Deferred

- Chart rendering. Will return as `ChartBlock` in v1.3.0+ when a chart-bearing slide upload makes the case.

### Recipe

`docs/longview-workflow.md` is rewritten with the new block vocabulary and composition rules. Any Claude Code session in the repo auto-loads `CLAUDE.md` which points at the recipe.

### Full changelog

See `CHANGELOG.md` v1.2.0 entry.
EOF

gh release create v1.2.0 --notes-file /tmp/release-notes-v1.2.0.md --title "v1.2.0 — Composable blocks + mono/steel"
```

- [ ] **Step 4: Verify release on GitHub**

```bash
gh release view v1.2.0
```

Expected: release is published with the notes above; tag points to the squash-merge commit.

---

## Task 12 (post-merge): Hetzner pull main

**Files:** None (operational task; no changes needed to `/home/adnan/CLAUDE.md` for v1.2.0 — the pointer is unchanged, only the recipe file content changed).

- [ ] **Step 1: SSH to Hetzner and pull main**

```bash
ssh adnan@135.181.43.68 'cd ~/the-brief && git fetch origin && git pull origin main && echo "---" && ls app/components/LongView*.tsx && echo "---" && git tag --sort=-v:refname | head -3 && echo "---" && git log --oneline -3'
```

Expected:
- Pull succeeds.
- 5 LongView*.tsx files listed: `LongView.tsx`, `LongViewProse.tsx`, `LongViewComparison.tsx`, `LongViewStat.tsx`, `LongViewBulletList.tsx`.
- `v1.2.0` is the top tag.
- HEAD is the squash-merge commit.

- [ ] **Step 2 (optional): Sanity smoke — re-upload the original BNP slide to Copotron**

This is the test that v1.1.0 failed (the BNP slide collapsed into prose). With v1.2.0, Copotron should now produce a `comparison` block (or compose `comparison` + supporting blocks).

In Discord, send Copotron:

```
<re-attach the original BNP prudential-changes PDF/JPEG>
longview
```

Expected Copotron behavior:
- Reads the source per the new recipe.
- Builds a Long View with at least one `comparison` block (and possibly a leading `prose` intro + closing `prose` or `bullet-list`).
- Pushes a branch, opens a PR, replies with the preview URL.

Open the preview URL. Verify the rendered output matches the visual mockups from brainstorming — mono + steel + comparison cards in a 2-col grid.

Reply `cancel` in Discord to clean up the test PR. (This is a verification, not a real pin.)

- [ ] **Step 3: Mark v1.2.0 complete**

Update memory if needed; otherwise the v1.2.0 cycle is shipped.

---

## Definition of Done (per spec §16)

- [x] Tasks 1-9: types + 4 component files + LongView dispatcher + CSS + recipe + CHANGELOG/version
- [x] Task 10: Vercel preview verified visually (null state, sample state exercising all 4 blocks, diff-stale state)
- [x] Task 11: merged to main, tagged v1.2.0, GitHub release published
- [x] Task 12: Hetzner pulled; optional Copotron BNP re-upload smoke

---

## Notes for the engineer executing this plan

- Frequent commits. Every task ends with a commit. Don't batch.
- Tasks 1-6 are sequential; Task 1 deliberately leaves `LongView.tsx` in a temporarily broken state — that's expected. The break is fixed in Task 6.
- Tasks 2-5 (4 new component files) could technically be parallelized but the plan keeps them serial for simpler review. If subagent-driven, dispatch one per task.
- Conductor workspace quirks (per session memory):
  - `gh pr merge` errors locally but succeeds server-side. Verify via `gh pr view`.
  - `gh pr create` MUST use `--head <branch>` explicitly (Conductor's `remote.origin.fetch` is restricted to main).
  - `git push --force-with-lease` (no-arg) fails because `origin/<feature>` remote-tracking refs aren't auto-fetched. Use `--force-with-lease=branch:$(git rev-parse FETCH_HEAD)`.
- Don't add a `Co-Authored-By` trailer in commit messages.
- If anything genuinely doesn't fit the spec/plan during implementation, stop and flag rather than improvising.
