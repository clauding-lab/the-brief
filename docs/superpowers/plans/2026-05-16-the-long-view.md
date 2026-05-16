# The Long View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pinned editorial section to The Brief called "The Long View" that the editor uploads via Discord (Copotron) or local terminal, recreated natively in cream-paper editorial style, replaceable via a single commit. Sits between the Overview and Banking groups. Persists across daily issues until replaced. Blurs in diff mode after its posted date.

**Architecture:** Repo-as-truth (no Supabase row, no API). Content lives in `content/long-view.ts` (`null` = nothing pinned). The section renders via a new `<LongView>` client component in `app/components/`. Preview-before-publish uses Vercel preview deployments on the feature branch. Claude Code (Copotron on Hetzner, or local terminal) reads PDFs/JPEGs natively under the subscription — no Anthropic API integration.

**Tech Stack:** TypeScript + React 19 + Next.js 16 (App Router). No new runtime dependencies. Existing visual primitives (`Hair`, cream-paper CSS tokens). Chart rendering deferred to v1.1.1; v1.1.0 ships text-only.

**Spec:** `docs/superpowers/specs/2026-05-16-the-long-view-design.md`

---

## Scope Decisions Made in This Plan

- **v1.1.0 ships text-only.** `BriefChart.tsx` is tightly coupled to the `Section` shape, so reusing it for a chart driven by `chart_spec` would require an adapter component and Section-shape gymnastics. Defer chart rendering to v1.1.1; the type stays in the schema, but the recipe instructs Claude Code to emit `chart_spec: null` for v1.1.0 and describe charts in body paragraphs instead.
- **`longView` is imported directly in `ClientApp.tsx`**, not routed through `BriefPayload`. The spec's earlier mention of updating `lib/staticFallback.ts` is unnecessary — `longView` is build-time static data, not Supabase-served dynamic data.
- **CSS uses existing design tokens** (`--accent`, `--ink-3`, `--rule`, `--rule-soft`, `--mono`). No new CSS variables.

---

## Task 1: Add LongView types to types/brief.ts

**Files:**
- Modify: `types/brief.ts` (append after line 109, before `BriefPayload` close)

- [ ] **Step 1: Read current `types/brief.ts`** so you know what's already there. Confirm `LongViewData`, `ChartSpec`, and `ChartSpecSeries` do NOT exist yet.

Run: `grep -E "LongViewData|ChartSpec" types/brief.ts`
Expected: no output (these symbols don't exist).

- [ ] **Step 2: Append the new interfaces to `types/brief.ts`**

Add the following at the end of the file (after `BriefPayload` definition):

```typescript
// --- Long View (pinned editorial insert, v1.1.0+) ---

export interface ChartSpecSeries {
  name: string;
  data: Array<[string | number, number]>; // [x, y] tuples; x can be a label or ISO date
}

export interface ChartSpec {
  kind: "line" | "bar" | "stacked_bar" | "donut";
  title: string;
  x_axis: string;
  y_axis: string;
  series: ChartSpecSeries[];
  annotations?: Array<{ x: string | number; label: string }>;
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

- [ ] **Step 3: Verify TypeScript compiles**

Run: `npx tsc --noEmit`
Expected: PASS (no new errors introduced; types compile because no consumer references them yet).

- [ ] **Step 4: Commit**

```bash
git add types/brief.ts
git commit -m "feat(longview): add LongViewData + ChartSpec types"
```

---

## Task 2: Create `content/long-view.ts` with initial null state

**Files:**
- Create: `content/long-view.ts`

- [ ] **Step 1: Ensure the `content/` directory exists at the repo root**

Run: `mkdir -p content && ls -la content`
Expected: `content/` directory exists (may be empty or contain other files; harmless if it already existed).

- [ ] **Step 2: Create `content/long-view.ts`**

Write the file with this exact content:

```typescript
import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data, commit, and
// let the user preview on a Vercel branch deployment before merging to main.
// See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = null;
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add content/long-view.ts
git commit -m "feat(longview): initialize content/long-view.ts with null state"
```

---

## Task 3: Add `formatLongViewEyebrow` helper to `lib/format.tsx`

**Files:**
- Modify: `lib/format.tsx` (append at end)

- [ ] **Step 1: Verify `lib/format.tsx` exists and current `formatBriefDate` doesn't pin a timezone (it uses local time)**

Run: `grep -n "formatBriefDate\|formatNewsMeta" lib/format.tsx`
Expected: both exist. Confirm `formatNewsMeta` uses `timeZone: "Asia/Dhaka"` (line ~21) — this is the pattern to follow to avoid React #418 hydration mismatch.

- [ ] **Step 2: Append the new helper**

Add at the end of `lib/format.tsx`:

```typescript
// Format an ISO timestamp as the Long View eyebrow:
//   EDITOR'S PIN · POSTED MON 12 MAY
// Day-of-week + day + month, all caps, pinned to Asia/Dhaka to avoid the
// SSR (UTC) vs CSR (BDT) day-number mismatch that bit us on news-item dates
// (React #418). See lib/format.tsx::formatNewsMeta for the same pattern.
export function formatLongViewEyebrow(postedAt: string): string {
  const d = new Date(postedAt);
  if (isNaN(d.getTime())) return "EDITOR'S PIN";
  const parts = d
    .toLocaleDateString("en-GB", {
      weekday: "short",
      day: "2-digit",
      month: "short",
      timeZone: "Asia/Dhaka",
    })
    .toUpperCase()
    .split(" ");
  // en-GB returns "MON, 12 MAY" — strip the comma after weekday, keep the rest.
  const weekday = parts[0]?.replace(",", "") ?? "";
  const day = parts[1] ?? "";
  const month = parts[2] ?? "";
  return `EDITOR'S PIN · POSTED ${weekday} ${day} ${month}`;
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 4: Smoke-check the helper manually with a one-liner**

Run:
```bash
node -e "
const { formatLongViewEyebrow } = require('./lib/format.tsx');
// Note: tsx isn't directly runnable by node; this is illustrative only.
// Real verification happens via the LongView component render on Vercel preview.
"
```
Expected: skip; the function is only consumed by the component.  Smoke-verification will land in Task 10 (Vercel preview). For now, the type-check is the gate.

- [ ] **Step 5: Commit**

```bash
git add lib/format.tsx
git commit -m "feat(longview): add formatLongViewEyebrow helper (Asia/Dhaka pinned)"
```

---

## Task 4: Create the `<LongView>` component

**Files:**
- Create: `app/components/LongView.tsx`

- [ ] **Step 1: Confirm `app/components/Hair.tsx` exists** (used as the hair-rule visual separator)

Run: `ls app/components/Hair.tsx`
Expected: file exists.

- [ ] **Step 2: Create `app/components/LongView.tsx`**

Write the file with this exact content:

```typescript
"use client";

import { useEffect, useState } from "react";
import type { LongViewData } from "@/types/brief";
import { Hair } from "./Hair";
import { formatLongViewEyebrow } from "@/lib/format";

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

export function LongView({ data }: LongViewProps) {
  // Track whether the section should render with the diff-stale treatment.
  // True iff: body has the .tb-diff class AND today (BDT) > posted_at (BDT).
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

      {data.chart_spec && (
        <div className="tb-longview-chart-placeholder" role="note">
          <em>Chart rendering for The Long View ships in v1.1.1. The data below
          and in the body paragraphs reflects the source.</em>
        </div>
      )}

      <div className="tb-longview-body">
        {data.body_paragraphs.map((paragraph, i) => (
          <p key={i}>{paragraph}</p>
        ))}
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

- [ ] **Step 3: Verify TypeScript compiles**

Run: `npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 4: Verify ESLint is clean**

Run: `npx eslint app/components/LongView.tsx`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add app/components/LongView.tsx
git commit -m "feat(longview): add LongView component with diff-stale support"
```

---

## Task 5: Add CSS classes to `app/globals.css`

**Files:**
- Modify: `app/globals.css` (append at end)

- [ ] **Step 1: Append the Long View styles**

Add at the end of `app/globals.css`:

```css
/* --- The Long View (pinned editorial insert, v1.1.0+) --- */

.tb-longview {
  padding: 56px 0 48px;
  margin-top: 12px;
  margin-bottom: 12px;
  scroll-margin-top: 110px;
  border-top: 1px solid var(--rule-soft);
  border-bottom: 1px solid var(--rule-soft);
}

.tb-longview-eyebrow {
  font-size: 10.5px;
  letter-spacing: 0.22em;
  color: var(--ink-3);
  font-weight: 600;
  text-transform: uppercase;
}

.tb-longview-title {
  font-size: clamp(28px, 3.2vw, 40px);
  line-height: 1.18;
  font-weight: 400;
  letter-spacing: -0.015em;
  margin: 0 0 16px;
  text-wrap: balance;
}

.tb-longview-lead {
  font-size: 18px;
  line-height: 1.55;
  font-style: italic;
  color: var(--ink-2, var(--ink-3));
  margin: 0 0 24px;
  max-width: 62ch;
}

.tb-longview-chart-placeholder {
  padding: 16px 20px;
  background: var(--color-surface-2, #f4f4f4);
  border-left: 3px solid var(--accent);
  color: var(--color-muted, #666);
  font-size: 13px;
  margin: 0 0 24px;
}

.tb-longview-body p {
  font-size: 15.5px;
  line-height: 1.65;
  margin: 0 0 16px;
  max-width: 70ch;
}

.tb-longview-body p:last-child {
  margin-bottom: 0;
}

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

/* Diff-mode: the section is stale after its posted_at day. Recede so the
   daily diff view stays focused on the day's fresh content. Mirrors the
   existing body.tb-diff dimming pattern but with an additional blur. */
.tb-longview.tb-diff-stale {
  opacity: 0.42;
  filter: blur(1px);
  pointer-events: none;
  transition: opacity 200ms ease, filter 200ms ease;
}

/* When LongView sits between Overview and Banking, the existing
   .tb-group + .tb-group rule (margin-top: 64px) doesn't match Banking
   anymore because LongView is between them. Restore the same spacing
   so the Overview→LongView→Banking flow keeps the brief's existing
   inter-group rhythm. */
.tb-longview + .tb-group {
  margin-top: 64px;
}
```

- [ ] **Step 2: Verify the CSS is well-formed by running `next build`**

Run: `npx next build 2>&1 | tail -40`
Expected: build completes; no CSS parse errors. May surface a fresh build cache; that's fine.

- [ ] **Step 3: Commit**

```bash
git add app/globals.css
git commit -m "feat(longview): add cream-paper styles for The Long View"
```

---

## Task 6: Wire `<LongView>` into `ClientApp.tsx`

**Files:**
- Modify: `app/components/ClientApp.tsx` (three changes: extend react import, add component/data imports, render insertion)

- [ ] **Step 1: Extend the existing react import to include `Fragment`**

Find line 3:
```typescript
import { useEffect, useState, useCallback } from "react";
```

Replace with:
```typescript
import { useEffect, useState, useCallback, Fragment } from "react";
```

- [ ] **Step 2: Add LongView component + data imports after the `StatusBar` import (around line 13)**

Add these two lines:
```typescript
import { LongView } from "./LongView";
import { longView } from "@/content/long-view";
```

- [ ] **Step 3: Insert `<LongView>` after the Overview group using a React Fragment**

Find the existing groups render block (around line 202):

```typescript
        {groupedSections.map(({ key, sections }) => (
          <div key={key} className="tb-group" data-group={key}>
            <div className="tb-group-header">
              <span className="tb-group-label">{GROUP_LABELS[key]}</span>
              <span className="tb-group-rule" aria-hidden="true" />
            </div>
            {sections.map((s) => (
              <Section
                key={s.slug}
                section={s}
                diffMode={diffMode}
                displayOrd={displayOrdBySlug.get(s.slug)}
              />
            ))}
          </div>
        ))}
```

Replace it with:

```typescript
        {groupedSections.map(({ key, sections }) => (
          <Fragment key={key}>
            <div className="tb-group" data-group={key}>
              <div className="tb-group-header">
                <span className="tb-group-label">{GROUP_LABELS[key]}</span>
                <span className="tb-group-rule" aria-hidden="true" />
              </div>
              {sections.map((s) => (
                <Section
                  key={s.slug}
                  section={s}
                  diffMode={diffMode}
                  displayOrd={displayOrdBySlug.get(s.slug)}
                />
              ))}
            </div>
            {/* The Long View sits between Overview and the next group (Banking).
                Renders nothing when `longView` is null. Fragment is used (vs. a
                wrapping div) so the existing `.tb-group + .tb-group` adjacent-
                sibling CSS rule still matches across groups. The new rule
                `.tb-longview + .tb-group` (added in Task 5) restores the 64px
                top margin on Banking, which is preceded by LongView instead of
                an adjacent .tb-group. */}
            {key === "overview" && <LongView data={longView} />}
          </Fragment>
        ))}
```

**Why a React Fragment, not a wrapping div with `display: contents`:** `display: contents` keeps the wrapper in the DOM tree, which breaks the adjacent-sibling selector `.tb-group + .tb-group` for the existing inter-group spacing. A Fragment doesn't create a DOM node, so the existing rule keeps working between Banking/Markets/Real Economy/Policy. The Overview→LongView→Banking gap is restored by the new `.tb-longview + .tb-group` rule.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 4: Verify build is clean**

Run: `npx next build 2>&1 | tail -20`
Expected: build completes without errors.

- [ ] **Step 5: Commit**

```bash
git add app/components/ClientApp.tsx
git commit -m "feat(longview): render LongView between Overview and Banking groups"
```

---

## Task 7: Create repo-root `CLAUDE.md` pointer

**Files:**
- Create: `CLAUDE.md` (at repo root)

- [ ] **Step 1: Verify the file does not exist yet**

Run: `ls CLAUDE.md 2>&1`
Expected: `ls: CLAUDE.md: No such file or directory` (or equivalent).

- [ ] **Step 2: Create `CLAUDE.md` with the pointer content**

Write this exact content:

```markdown
# The Brief — Claude operating notes

When a user uploads a PDF or JPEG with the word `longview` (in Discord or terminal), read `docs/longview-workflow.md` and follow it exactly. Do not improvise the schema or the workflow — the recipe is the contract.

The Long View is a pinned editorial section, replaced by editing `content/long-view.ts` and shipping the change via a Vercel-previewed PR to main. See the recipe for the full sequence.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(longview): add repo CLAUDE.md pointer to longview recipe"
```

---

## Task 8: Create the recipe — `docs/longview-workflow.md`

**Files:**
- Create: `docs/longview-workflow.md`

- [ ] **Step 1: Verify `docs/` directory exists**

Run: `ls -d docs/ 2>&1`
Expected: `docs/` directory exists (it already holds `superpowers/`).

- [ ] **Step 2: Create the recipe file**

Write this exact content (~140 lines):

```markdown
# The Long View — workflow

This file is the contract for the Long View workflow on The Brief. It has two halves: **Editorial** (what to write) and **Operational** (how to ship it). Both halves must be followed for every Long View pin.

The Long View is a pinned editorial section that sits between the Overview group and the Banking group on The Brief's SPA. It replaces whatever was previously pinned. Posted at most once per week. Re-rendered in the brief's cream-paper editorial style from a source PDF or JPEG the editor uploads.

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

The Brief is read by banking professionals in Bangladesh — business heads (corporate, SME, retail), risk heads, and treasury heads at Tier-1 banks. Write for that reader.

### Voice register

- Banker-native vocabulary: NPL, CRR, repo, SDF, Sukuk, ALCO, MPS, BB (Bangladesh Bank), Tier-1 capital, provisioning, advance-deposit ratio.
- Concrete numbers; never round away precision the source provides.
- Implications oriented to credit committees, ALCO, treasury desks.
- No journalese ("amid", "in a stunning move", "moreover"), no LLM tells ("delve", "myriad", "tapestry"), no hedging when the source is clear.

### Output schema

Edit `content/long-view.ts` to look exactly like this (filling in your extracted data):

```typescript
import type { LongViewData } from "@/types/brief";

export const longView: LongViewData | null = {
  posted_at: "<ISO 8601 UTC timestamp, e.g. 2026-05-18T00:30:00Z — use now()>",
  title: "<5–10 words, no trailing punctuation>",
  lead: "<1–2 sentences setting up the insight>",
  body_paragraphs: [
    "<paragraph 1>",
    "<paragraph 2>",
    // 1–3 total; never more.
  ],
  chart_spec: null,  // v1.1.0: always null. v1.1.1: chart rendering ships.
  banker_read: "<1 paragraph; the takeaway for a banker reader>",
};
```

### Forbiddens

- **Do not fabricate numbers** not in the source. If the slide is unclear, say so in your reply to the user and stop.
- **Do not add a source-attribution field** (no "Source: BB MPS, May 2026" line). The spec explicitly excludes this.
- **Do not add a "view original" link.** The reader sees only the recreation.
- **Do not fold opinion into the lead.** Opinion lives in `banker_read`.
- **Do not emit a `chart_spec` other than `null` in v1.1.0.** If the source has a chart, describe its shape in `body_paragraphs` (e.g., "The slide shows cut-off yields falling from 8.95% to 8.57% across four auctions"). Chart rendering ships in v1.1.1.

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
# Example: longview/sukuk-spread-deepdive
```

### 3. Read the source

Open the PDF or JPEG and extract per the Editorial half above. If a hint was provided after `longview - `, weight your framing toward it.

### 4. Edit `content/long-view.ts`

Replace the entire contents with the new `longView` export per the schema. Verify locally:

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

Reply (via the Discord `reply` tool on Hetzner, or normal terminal output on Mac):

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
# Note: if the no-arg --force-with-lease fails because the remote-tracking
# ref doesn't exist (Conductor workspace quirk), use:
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

- **Never merge to main without showing the user the Vercel preview URL first.** Even if you're confident the data is good.
- **Never commit the PDF/JPEG to the repo.** Only `content/long-view.ts` and (later) a CHANGELOG entry change in this PR. The source stays on disk under `pins/`.
- **Never edit `content/long-view.ts` outside this workflow.** Daily editorial content has its own pipeline (`brief.service`, Supabase); the Long View is the only thing in `content/`.
- **If anything goes wrong** (Vercel build fails, git push fails, source file is unreadable), reply to the user with the exact error and stop. Do not auto-retry on shared-state writes.

---

## Failure modes — quick reference

| Symptom | Likely cause | Action |
|---|---|---|
| `npx tsc --noEmit` fails after your edit | Type mismatch in your new `longView` value | Re-check the `LongViewData` shape in `types/brief.ts`; fix and retry. |
| Vercel build fails on the preview | Usually a runtime React error from the new data | Pull the failure summary from `gh pr checks`, fix locally, push. If still failing, hand back to user. |
| `gh pr merge` fails | Merge conflict on `content/long-view.ts` (another `longview/*` branch landed) | Surface the error verbatim. Rebase or ask the user. Don't auto-resolve. |
| User goes silent after preview | Normal | Draft branch sits indefinitely. Leave it; no auto-cleanup. |
| User starts a second `longview` upload before resolving the first | Pending draft conflict | Reply: "There's an open Long View draft on branch `longview/<previous>` (preview: …). Cancel that and start fresh, or treat this as a `redo` of the open draft?" |

---

## Quick reference — what files this workflow touches

| File | Why |
|---|---|
| `content/long-view.ts` | The pinned data. Edit per workflow. |
| `pins/<uuid>.<ext>` | Local copy of the source on disk. Not in git. |

That's it. Everything else (the component, the styles, the wiring) lives outside the per-pin workflow and is not edited here.
```

- [ ] **Step 3: Commit**

```bash
git add docs/longview-workflow.md
git commit -m "docs(longview): add the Long View workflow recipe"
```

---

## Task 9: CHANGELOG entry + version bump to v1.1.0

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `package.json` (version field)

- [ ] **Step 1: Read the current top of `CHANGELOG.md`**

Run: `head -30 CHANGELOG.md`
Expected: current top entry is v1.0.1.

- [ ] **Step 2: Insert a new v1.1.0 entry above v1.0.1**

Add this entry directly above the `## [1.0.1]` heading:

```markdown
## [1.1.0] — 2026-05-18

### Added
- **The Long View** — a pinned editorial section that the editor uploads via Discord (Copotron on Hetzner) or local terminal. Claude Code reads the uploaded PDF or JPEG natively and re-renders it as a native cream-paper section. Sits between the Overview and Banking groups; replaces only when a new upload lands. Blurs in diff mode after its posted date.
- `content/long-view.ts` — the pinned data file; edited via the workflow recipe.
- `app/components/LongView.tsx` — the render component.
- `docs/longview-workflow.md` — the recipe (editorial + operational halves).
- `CLAUDE.md` at repo root — pointer to the recipe for any Claude Code session opened in the repo.
- `LongViewData` + `ChartSpec` interfaces in `types/brief.ts`.
- `formatLongViewEyebrow` in `lib/format.tsx` (Asia/Dhaka-pinned).

### Changed
- `app/components/ClientApp.tsx` renders `<LongView>` between the Overview group and the Banking group when `content/long-view.ts` exports non-null.

### Deferred
- Chart rendering in the Long View (`chart_spec` field exists in the type, but the v1.1.0 component renders a placeholder if a non-null `chart_spec` is provided). Real Chart.js rendering ships in v1.1.1 if and when a user upload contains a chart that needs recreation.
```

- [ ] **Step 3: Bump `package.json` version from `1.0.1` to `1.1.0`**

Edit `package.json`, change line 3:

```json
  "version": "1.1.0",
```

(was `"version": "1.0.1",`)

- [ ] **Step 4: Verify both files**

Run:
```bash
head -5 CHANGELOG.md
grep '"version"' package.json
```
Expected: CHANGELOG shows the new v1.1.0 entry at the top; package.json shows `"version": "1.1.0"`.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md package.json
git commit -m "chore(v1.1.0): bump version 1.0.1 -> 1.1.0 + CHANGELOG entry"
```

---

## Task 10: Push, open PR, smoke-test on Vercel preview

**Files:** None (operational task).

- [ ] **Step 1: Push the feature branch**

```bash
git push -u origin clauding-lab/long-view
```
Expected: push succeeds; the branch is now visible on GitHub.

- [ ] **Step 2: Open the PR**

```bash
gh pr create \
  --title "feat(v1.1.0): The Long View — pinned editorial insert" \
  --body "$(cat <<'EOF'
## Summary

Adds **The Long View**, a pinned editorial section that the editor uploads via Discord (Copotron) or local terminal. Claude Code reads the uploaded PDF/JPEG natively (under the subscription, no Anthropic API), re-renders it as a native cream-paper section, and lets it sit between the Overview and Banking groups until replaced.

- Spec: `docs/superpowers/specs/2026-05-16-the-long-view-design.md`
- Plan: `docs/superpowers/plans/2026-05-16-the-long-view.md`
- Recipe (the workflow contract): `docs/longview-workflow.md`

## What's in this PR

- Types: `LongViewData`, `ChartSpec`
- Initial null data: `content/long-view.ts`
- Render component: `app/components/LongView.tsx`
- Styles: `.tb-longview*` + `.tb-diff-stale` in `app/globals.css`
- Wire-up in `ClientApp.tsx` (between Overview and Banking)
- Repo `CLAUDE.md` pointer + the recipe
- CHANGELOG v1.1.0 + version bump

## What's NOT in this PR (deferred to v1.1.1)

- Chart rendering. v1.1.0 ships text-only; if `chart_spec` is non-null, a placeholder note renders. First user upload that needs a chart triggers v1.1.1.

## Test plan

- [ ] `npx tsc --noEmit` clean
- [ ] `npx next build` clean
- [ ] `npx eslint` clean
- [ ] Vercel preview deploys green
- [ ] On the Vercel preview, with `content/long-view.ts` temporarily seeded with sample data, the section renders between Overview and Banking
- [ ] Eyebrow reads `EDITOR'S PIN · POSTED <DAY> <DD> <MON>` in BDT
- [ ] Diff-mode toggle (`localStorage.thebrief.diffMode = "1"` + reload) blurs the section when posted_at is in the past
- [ ] Revert sample data to `null` before merge — production should ship with no Long View pinned (first real pin comes via the Discord/terminal workflow)
EOF
)"
```

- [ ] **Step 3: Wait for Vercel preview to finish building**

```bash
gh pr checks --watch
```

Once the build completes, get the preview URL:

```bash
gh pr view --json statusCheckRollup \
  --jq '.statusCheckRollup[] | select(.name // .context | tostring | test("Vercel")) | .targetUrl // .detailsUrl' \
  | head -1
```

- [ ] **Step 4: Smoke 1 — null state**

Open the preview URL. Expected:
- Page renders normally.
- NO Long View section visible (because `longView === null`).
- No console errors.
- Sections in normal order: Overview → Banking → Markets → Real Economy → Policy.

- [ ] **Step 5: Smoke 2 — temporarily seed sample data for visual verification**

Edit `content/long-view.ts` temporarily:

```typescript
import type { LongViewData } from "@/types/brief";

export const longView: LongViewData | null = {
  posted_at: "2026-05-12T00:30:00Z",
  title: "Sukuk yields are absorbing rate-cut signals before policy moves",
  lead: "Across four BB Sukuk auctions in the last month, the cut-off yield has compressed 38 bps while the repo–SDF corridor stayed wide. Sovereign demand is pricing easing the policy desk has not yet signaled.",
  body_paragraphs: [
    "The cut-off in the latest 2-year Ijara Sukuk came in 12 bps below the prior auction, the fourth consecutive decline in a series that began before the March MPS. Bid-cover has climbed from 2.4× to 3.1× over the same window.",
    "What's interesting is the directional gap between the curve and the corridor. The repo–SDF window has held at 200 bps since January, but Sukuk repricing implies the market is positioning for a narrowing — either through a repo cut or an SDF lift — within the next 4 weeks.",
  ],
  chart_spec: null,
  banker_read: "Treasury desks pricing fixed-rate Ijara product against the upcoming MPS should anchor on the corridor, not the cut-off. If the corridor narrows, the Sukuk curve repricing will be steep — re-hedge before the May 28 auction window.",
};
```

Commit + push:

```bash
git add content/long-view.ts
git commit -m "test(longview): temporarily seed sample data for preview smoke"
git push
```

Wait for the Vercel rebuild (`gh pr checks --watch`).

- [ ] **Step 6: Smoke 2 verification on the new preview URL**

Open the (same) preview URL. Expected:
- Long View section renders between Overview and Banking.
- Eyebrow reads `EDITOR'S PIN · POSTED TUE 12 MAY` (or whatever weekday `2026-05-12` is in BDT).
- Title, lead (italic), 2 paragraphs, and the BANKER READ takeaway all render with cream-paper styling.
- No chart placeholder (because `chart_spec` is null).
- No console errors.

Open DevTools, run:

```javascript
localStorage.setItem("thebrief.diffMode", "1");
location.reload();
```

After reload, expected:
- Body has class `tb-diff`.
- Long View section is blurred / dimmed (`.tb-diff-stale` applied because `2026-05-12 < today`).
- The section is non-interactive (`pointer-events: none`).

Then disable diff mode and reload to confirm the section returns to full opacity.

- [ ] **Step 7: Revert the sample data**

```bash
cat > content/long-view.ts <<'EOF'
import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data, commit, and
// let the user preview on a Vercel branch deployment before merging to main.
// See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = null;
EOF

git add content/long-view.ts
git commit -m "chore(longview): revert sample data, ship with null state"
git push
gh pr checks --watch
```

Verify the preview URL one last time:
- No Long View section visible.
- Normal section order.

- [ ] **Step 8: Pause for user approval**

Reply to the user with the preview URL and ask: "Smoke checks passed. Ready to merge to main and tag v1.1.0?"

Do NOT merge until the user replies `yes` / `publish` / `merge`.

---

## Task 11: Merge to main, tag v1.1.0, push tag, create GitHub release

**Files:** None (operational task).

- [ ] **Step 1: Merge the PR (only after user approves Task 10 Step 8)**

```bash
gh pr merge <pr-number> --squash --delete-branch
```

Note: per session memory, `gh pr merge` from Conductor workspaces often errors locally with `'main' is already used by worktree at ...` but ALWAYS succeeds server-side. Verify with:

```bash
gh pr view <pr-number> --json state,mergeCommit --jq '.state + " " + (.mergeCommit.oid // "")'
```

Expected: `MERGED <sha>`.

- [ ] **Step 2: Tag v1.1.0 on the squash-merge commit**

```bash
git fetch origin main
MERGE_SHA=$(gh pr view <pr-number> --json mergeCommit --jq .mergeCommit.oid)
git tag -a v1.1.0 "$MERGE_SHA" -m "v1.1.0 — The Long View

Pinned editorial insert that the editor uploads via Discord (Copotron) or
local terminal. Claude Code re-renders the source PDF/JPEG natively in the
brief's cream-paper editorial style.

Charts deferred to v1.1.1."
git push origin v1.1.0
```

- [ ] **Step 3: Create the GitHub release**

```bash
cat > /tmp/release-notes-v1.1.0.md <<'EOF'
## v1.1.0 — The Long View

A pinned editorial section that sits between the Overview and Banking groups on The Brief. The editor uploads a slide or infographic (PDF/JPEG) via Discord (Copotron) or local terminal; Claude Code reads it natively under the subscription (no Anthropic API), re-renders it as native cream-paper content, and pins it until replaced.

### Highlights

- One Discord upload pins a Long View; one reply (`publish`) makes it live.
- Vercel preview deployments handle the preview-before-publish step.
- Diff-mode blurs the section after its posted date so the daily diff view stays focused on the day's fresh content.
- Repo is the source of truth — no Supabase table, no Anthropic API. Git history is the audit trail.

### Deferred

- Chart rendering inside the Long View. v1.1.0 ships text-only; v1.1.1 will add Chart.js support when the first user upload needs a chart.

### Recipe / workflow

`docs/longview-workflow.md` is the contract. Any Claude Code session in the repo auto-loads `CLAUDE.md` which points at the recipe.

### Full changelog

See `CHANGELOG.md` v1.1.0 entry.
EOF

gh release create v1.1.0 --notes-file /tmp/release-notes-v1.1.0.md --title "v1.1.0 — The Long View"
```

- [ ] **Step 4: Verify release on GitHub**

```bash
gh release view v1.1.0
```

Expected: release is published with the notes above; tag points to the squash-merge commit.

---

## Task 12 (post-merge): Hetzner pull + Copotron CLAUDE.md update

**Files:** `/home/adnan/CLAUDE.md` on Hetzner (NOT in git — Hetzner-local user config).

- [ ] **Step 1: SSH to Hetzner and pull main**

```bash
ssh adnan@135.181.43.68 'cd ~/the-brief && git pull origin main && ls docs/longview-workflow.md'
```

Expected: pull succeeds; `docs/longview-workflow.md` exists on Hetzner.

- [ ] **Step 2: Send the prompt to Copotron in Discord**

(Switch to Discord. Send this verbatim to Copotron.)

```
Update /home/adnan/CLAUDE.md to add a third section for the Long View workflow on The Brief.

Append the following after the existing content (leave one blank line between
the current last line and the new section header):

# The Brief — Long View workflow

The Brief publishing pipeline lives at `/home/adnan/the-brief/` on this box
(Python pipeline via `brief.service` systemd unit + Next.js SPA deployed to Vercel).

When the user uploads a PDF or JPEG to Discord with the word `longview`
(optionally followed by `- <hint>`):

1. `cd /home/adnan/the-brief`
2. Save the attachment to `~/the-brief/pins/<uuid>.<ext>`
3. Read `CLAUDE.md` (project-root pointer)
4. Read `docs/longview-workflow.md` (the full recipe)
5. Follow the recipe exactly — do not improvise the schema, do not skip the
   Vercel-preview step, do not merge to main before the user replies "publish"

After appending, run `cat /home/adnan/CLAUDE.md` and reply with the full content
so I can verify it looks right.
```

- [ ] **Step 3: Verify Copotron's reply matches expectations**

Confirm the cat output shows three sections:
1. Communication (existing)
2. Environment (existing)
3. The Brief — Long View workflow (new)

If the output looks wrong (formatting drift, missing lines), reply to Copotron with a correction.

- [ ] **Step 4: End-to-end smoke test**

In Discord, send Copotron a real test:

```
<attach a small test PDF or JPEG with a clear data point>
longview
```

Expected behavior from Copotron:
- Saves the source to `~/the-brief/pins/<uuid>.<ext>`
- Creates a `longview/<slug>` branch
- Edits `content/long-view.ts` with extracted data
- Pushes the branch
- Waits for Vercel preview
- Replies with the preview URL + `publish | redo | cancel` prompt

If Copotron does this correctly, reply `cancel` (we don't want a test pin in production). Confirm Copotron closes the PR and deletes the source.

---

## Definition of Done (per spec §15)

- [x] Tasks 1–9: code, types, content, component, CSS, wire-up, CLAUDE.md, recipe, CHANGELOG + version all merged
- [x] Task 10: Vercel preview verified visually (null state, sample state, diff-stale state)
- [x] Task 11: merged to main, tagged v1.1.0, GitHub release published
- [x] Task 12: Hetzner pulled, Copotron CLAUDE.md updated, end-to-end Discord smoke passed

---

## Notes for the engineer executing this plan

- Frequent commits. Every task ends with a commit. Don't batch.
- The brief has no JS/TS test framework — `tsc`, `eslint`, `next build`, and Vercel preview are the test surface. Don't try to add Vitest in this plan.
- Conductor workspace quirks (per session memory):
  - `gh pr merge` from a Conductor workspace errors locally but succeeds server-side. Verify via `gh pr view --json state,mergeCommit`.
  - `git push --force-with-lease` (no-arg) fails because `origin/<feature>` remote-tracking refs aren't auto-fetched. Use `--force-with-lease=branch:$(git rev-parse FETCH_HEAD)`.
- Don't add a `Co-Authored-By` trailer in commit messages (global setting per `~/.claude/settings.json`).
- If chart_spec rendering becomes necessary mid-implementation (a user upload arrives with a critical chart), STOP and create a v1.1.1 plan rather than extending this PR.
