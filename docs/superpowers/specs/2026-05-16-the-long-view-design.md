# The Long View — pinned editorial insert

**Date:** 2026-05-16
**Status:** Draft (post-brainstorm, awaiting plan)
**Target version:** v1.1.0
**Owner:** Adnan

---

## 1. Problem & Goal

The Brief publishes a fresh daily issue Mon–Fri + Sun. The daily content is good for "what happened today" but doesn't carry standalone analytical artifacts — slides, infographics, deep-dives — that the editor (Adnan) wants to put in front of readers for a longer beat. These are pieces the editor curates by hand: a slide from a BB monetary policy briefing, an infographic of NPL trends across Tier-1 banks, a one-page deep-dive on the spread between repo and SDF rates.

**Goal:** Add a single pinned editorial section to The Brief called **The Long View**. Adnan uploads a PDF or JPEG (a slide or infographic) via Discord (or local terminal); Claude Code reads it natively, re-renders it as a native cream-paper section in the brief's editorial style, and pins it into every issue until the next upload replaces it. Posted at most once a week.

The reader's experience: between the day's Overview group and the Banking group, they hit a small editorial pin — eyebrow `EDITOR'S PIN · POSTED MON 12 MAY`, title, lead, optional chart, paragraphs, and a banker takeaway. It reads as a slower-cadence companion to the daily news, not as another LLM-generated block.

## 2. Out of Scope

- **No drag-and-drop admin UI on the SPA.** Discord + Claude Code is the upload surface. A web admin route may be revisited in v2 if usage justifies it.
- **No Anthropic API integration.** Claude Code runs on the user's subscription. No new API keys, no per-token billing, no Pydantic extraction schema.
- **No Supabase table for Long View content.** Content lives in the repo (`content/long-view.ts`). Git history is the audit trail.
- **No "view original" link.** Reader sees only the recreation. The source PDF/JPEG is kept on Hetzner disk for re-extraction debugging, never exposed to the SPA.
- **No source-attribution field.** Claude does not extract or render "Source: …" lines below the chart.
- **No automated bounce/complaint handling.** The Long View is independent of the email notifier; nothing about pinning a Long View triggers a digest email.
- **No structured query over past Long Views.** Anyone who wants to see past pins runs `git log -p content/long-view.ts`.

## 3. User Experience

Two surfaces, same workflow:

### 3a. Discord (Copotron — Hetzner-resident Claude Code)

```
You:        <attach sukuk-deepdive.pdf>
            longview - emphasize the spread between repo and SDF rates

Copotron:   Reading the PDF…
            Created branch longview/sukuk-spread-deepdive.
            Vercel preview building…
            Preview ready: https://the-brief-<hash>.vercel.app/
            Reply with: publish | redo: <new hint> | cancel

You:        publish

Copotron:   Merged to main. Vercel deploying production.
            Live on thebrief.clauding-lab.com — pinned until replaced.
```

### 3b. Mac terminal (local Claude Code in the brief repo)

```
You:   here's a PDF — make it a long view. Emphasize the spread between
       repo and SDF rates. ~/Downloads/sukuk-deepdive.pdf

Claude: Reading the PDF…
        Created branch longview/sukuk-spread-deepdive.
        Vercel preview building…
        Preview ready: https://the-brief-<hash>.vercel.app/
        publish | redo: <new hint> | cancel?

You:   publish
```

Both paths invoke the same recipe file in the repo. Both reuse the same git/gh/Vercel workflow already in use across the brief.

## 4. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Claude Code (on Hetzner via Discord, OR on Mac locally)     │
│                                                               │
│   1. Read PDF/JPEG natively (no API call — subscription)     │
│   2. Save source: ~/the-brief/pins/<uuid>.<ext>              │
│   3. git checkout -b longview/<slug>                         │
│   4. Edit content/long-view.ts with structured data          │
│   5. Commit + push                                            │
│   6. gh pr create                                             │
│   7. gh pr checks --watch  (wait for Vercel build)           │
│   8. Extract preview URL from gh pr view                     │
│   9. Reply to user with preview URL                          │
│  10. On "publish": gh pr merge --squash --delete-branch      │
│      On "redo":    re-read, re-edit, force-push, same URL    │
│      On "cancel":  gh pr close --delete-branch + delete pin  │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼ (commit to main)
┌──────────────────────────────────────────────────────────────┐
│  Vercel auto-deploys main → thebrief.clauding-lab.com        │
│  SPA reads content/long-view.ts at build time                │
│  <LongView/> renders between Overview and Banking groups     │
└──────────────────────────────────────────────────────────────┘
```

**Key properties:**
- **Repo is the source of truth.** No DB row, no RPC change, no RLS. Content is a TypeScript module.
- **Vercel preview URLs are the preview mechanism.** Every branch push gets a unique URL. No custom preview route in the SPA.
- **Git history is the audit log.** `git log -p content/long-view.ts` shows every pin, ever.
- **Either trigger surface works.** Discord-on-Hetzner and Mac-terminal both invoke the same recipe.

## 5. File-Level Changes

| File | Status | Purpose |
|---|---|---|
| `content/long-view.ts` | **NEW** | The pinned data. Exports `longView: LongViewData \| null`. Edited per pin. |
| `types/brief.ts` | Updated | Adds `LongViewData` and `ChartSpec` interfaces. |
| `app/components/LongView.tsx` | **NEW** | Renders eyebrow + title + lead + optional chart + paragraphs + banker_read. Reads diff-stale state from `posted_at`. |
| `app/components/ClientApp.tsx` | Updated | Imports `longView`, renders `<LongView data={longView} />` immediately after the Overview group, before the Banking group. |
| `app/globals.css` | Updated | New classes: `.tb-longview`, `.tb-longview-eyebrow`, `.tb-longview-title`, `.tb-longview-lead`, `.tb-longview-body`, `.tb-longview-takeaway`, `.tb-diff-stale`. |
| `lib/staticFallback.ts` | Updated | Adds `longView: null` to the cold-start payload (defensive — the import is at build time but the fallback consumes the same `BriefPayload` shape). |
| `docs/longview-workflow.md` | **NEW** | The recipe. ~150 lines, human-friendly, both editorial and operational guidance. Read by Claude Code on every Long View invocation. |
| `CLAUDE.md` (repo root) | **NEW** | Two-line pointer: "When the user uploads a PDF/JPEG with the word `longview`, read `docs/longview-workflow.md` and follow it exactly." |

## 6. Data Shape — `content/long-view.ts`

```typescript
// content/long-view.ts
import type { LongViewData } from "@/types/brief";

export const longView: LongViewData | null = {
  posted_at: "2026-05-18T00:30:00Z",   // ISO 8601 UTC; eyebrow renders to BDT
  title: "Sukuk yields are absorbing rate-cut signals before policy moves",
  lead: "Across four BB Sukuk auctions in the last month, the cut-off yield has compressed 38 bps while the repo–SDF corridor stayed wide. Sovereign demand is pricing easing the policy desk has not yet signaled.",
  body_paragraphs: [
    "The cut-off in the latest 2-year Ijara Sukuk came in 12 bps below the prior auction…",
    "What's interesting is the bid-cover ratio: 2.4× in March, 3.1× in May…",
  ],
  chart_spec: {
    kind: "line",
    title: "BB Sukuk cut-off yield, last four auctions",
    x_axis: "Auction date",
    y_axis: "Yield (%)",
    series: [
      { name: "2-yr Ijara Sukuk", data: [["Feb 18", 8.95], ["Mar 17", 8.81], ["Apr 14", 8.62], ["May 12", 8.57]] },
    ],
  },
  banker_read: "Treasury desks pricing fixed-rate Ijara product against the upcoming MPS should anchor on the corridor, not the cut-off — if the corridor narrows in the next 4 weeks, the Sukuk curve repricing will be steep.",
};
```

**`null` semantics:** when `longView === null`, `<LongView>` renders nothing. This is how the section "doesn't exist yet" before the first pin, and how it can be temporarily un-pinned without losing the previous content from git history.

## 7. Render Detail — `<LongView />`

Visual layout (cream-paper, matching the brief's editorial register):

```
┌─────────────────────────────────────────────────┐
│   EDITOR'S PIN · POSTED MON 12 MAY              │ ← eyebrow (small caps, hair-rule above)
│                                                  │
│   Sukuk yields are absorbing rate-cut signals   │ ← title (serif, large)
│                                                  │
│   Across four BB Sukuk auctions in the last     │ ← lead (italic, larger than body)
│   month, the cut-off yield has compressed…      │
│                                                  │
│   ┌─────────────────────────────────────────┐  │ ← optional chart card (re-uses
│   │   BB Sukuk cut-off yield                 │  │   the brief's existing BriefChart
│   │   ╱╲                                     │  │   visual treatment)
│   │  ╱  ╲___                                 │  │
│   │ ╱       ╲___                             │  │
│   └─────────────────────────────────────────┘  │
│                                                  │
│   The cut-off in the latest 2-year…             │ ← body paragraph(s)
│                                                  │
│   What's interesting is the bid-cover ratio…    │ ← body paragraph(s)
│                                                  │
│   ─── BANKER READ ───                            │ ← takeaway (BankerRead-style block)
│   Treasury desks pricing fixed-rate Ijara…       │
│                                                  │
└─────────────────────────────────────────────────┘
```

- **Eyebrow date format:** `EDITOR'S PIN · POSTED MON 12 MAY`. Day-of-week + day + month-name, all caps, computed from `posted_at` converted to `Asia/Dhaka` (matches the `formatNewsMeta` pattern in `lib/format.tsx`).
- **Chart rendering:** reuses `BriefChart.tsx` and the `chartConfigs.ts` registration system. If a `chart_spec.kind` is added that doesn't yet exist in `chartConfigs.ts`, both files need updating (per saved memory `feedback_chartjs_register_and_preview.md`).
- **Diff-stale styling:** `<LongView>` reads `document.body.classList.contains("tb-diff")` and compares today (`Asia/Dhaka`) to `posted_at`. When diff mode is on AND `today > posted_at`, applies `tb-diff-stale` class: `opacity: 0.45; filter: blur(1px); pointer-events: none;`. The reader's daily diff view stays focused on the day's fresh content.

## 8. Placement in the SPA

The render order changes from:

```
Masthead → SnapshotStrip → SecNav → Cover →
  [Overview] → [Banking] → [Markets] → [Real Economy] → [Policy] →
SubscribeCTA
```

…to:

```
Masthead → SnapshotStrip → SecNav → Cover →
  [Overview] → [Long View if present] → [Banking] → [Markets] → [Real Economy] → [Policy] →
SubscribeCTA
```

Implementation in `ClientApp.tsx`:
- Iterate `groupedSections` as today.
- After rendering the `key === 'overview'` block, conditionally render `<LongView data={longView} />`.
- The Long View is NOT inside a `.tb-group` wrapper — it has its own visual treatment, distinct from the 5 daily groups.
- The "In this issue" rail (in `Masthead.tsx`) is NOT updated to include the Long View. The Long View is editor-pinned, not part of the day's headlines.

## 9. The Recipe — `docs/longview-workflow.md`

A single human-friendly markdown file, ~150 lines, that Claude Code reads at the start of every Long View invocation. Has two halves:

**Editorial half:**
- Audience: Bangladesh banking professionals (business / risk / treasury heads at Tier-1 banks)
- Voice register: banker-native vocabulary (NPL, CRR, repo, SDF, sukuk, ALCO, …), concrete numbers, implications for credit committees and treasury desks; no journalese, no LLM tells
- Output schema: the exact TypeScript shape of `content/long-view.ts` (posted_at, title, lead, body_paragraphs, chart_spec, banker_read)
- Chart conventions: `line` | `bar` | `stacked_bar` | `donut`, matching `chartConfigs.ts` patterns
- Forbiddens:
  - Don't fabricate numbers not in the source
  - Don't add source-attribution lines
  - Don't add a "view original" link
  - Don't fold opinion into the lead — opinion lives in `banker_read`

**Operational half:**
- Save attachment to `~/the-brief/pins/<uuid>.<ext>` (use `python -c "import uuid; print(uuid.uuid4())"` or equivalent)
- Branch naming: `longview/<3-4-word-slug>` (kebab-case from your read of the image)
- Commit message: `longview: <title in lowercase>`
- PR title and body templates
- Wait for Vercel build: `gh pr checks --watch` then extract URL from `gh pr view --json statusCheckRollup`
- Reply protocol exactly as documented in §3
- Cleanup on cancel: `gh pr close --delete-branch` AND `rm ~/the-brief/pins/<uuid>.*`
- **Hard rule:** never merge to main without showing the user the Vercel preview URL first

The file is written for both human and Claude readers. Adnan can edit the editorial-half guidance (voice, audience, forbiddens) over time without re-prompting; Claude rereads the file on every invocation.

## 10. CLAUDE.md pointers — repo + Hetzner

Two pointer files in two locations, because Claude Code's CLAUDE.md auto-load walks UP the directory tree but never DOWN into subdirectories, and Copotron (the Discord bot on Hetzner) launches with cwd `/home/adnan`, NOT inside the brief repo.

### 10a. Repo root — `~/the-brief/CLAUDE.md`

New file at the repo root, ~3 lines. Auto-loaded by any Claude Code session whose cwd is inside the brief repo (i.e., the Mac terminal path):

```markdown
# The Brief — Claude operating notes

When a user uploads a PDF or JPEG with the word `longview` (in Discord or terminal), read `docs/longview-workflow.md` and follow it exactly. Do not improvise the schema or the workflow — the recipe is the contract.
```

### 10b. Hetzner-local — `/home/adnan/CLAUDE.md` (Copotron)

Existing file (today has *Communication* and *Environment* sections). Append a third section so Copotron auto-loads the Long View pointer at session start. This file is NOT in git — it's Hetzner-local user config, applied once via the Discord prompt below (or manual SSH):

```markdown
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
```

**Discord prompt to send Copotron** (after `docs/longview-workflow.md` is merged to main and Hetzner has pulled):

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

Together, 10a + 10b ensure every entry point (Mac terminal in the repo, Copotron in Discord) auto-loads enough context to find and follow the recipe without the user re-explaining.

## 11. Failure Modes

| Failure | Detection | Recovery |
|---|---|---|
| Image unreadable / blank | Claude can't extract enough fields | Reply "Couldn't extract a clean structure — please retry with a clearer image." No branch created. |
| Vercel build fails on push | `gh pr checks` shows failure | Reply with the failure summary, attempt one targeted fix (usually a type error in `LongViewData`), re-push. If still failing, hand back to user. |
| Hetzner disk write fails | OS error on pin save | Reply with the error. No branch created. |
| `gh pr merge` fails after user says publish | Non-zero exit | Surface the error verbatim, suggest manual merge. Don't auto-retry — merge conflicts deserve a human. |
| User says `redo: <hint>` after preview | Normal path | Re-read same source file (same uuid in `pins/`), re-edit `content/long-view.ts`, `git commit --amend && git push --force-with-lease=branch:<sha>` (force-push pattern from session memory). Preview URL stays stable. |
| User goes silent after preview is sent | Detected by no response | Draft branch sits indefinitely. Daily cron (separate from this spec) could clean up `longview/*` branches older than 14 days — deferred. |
| User starts a second `longview` upload before resolving the first | New attachment in chat | Confirm with user: "There's an open Long View draft on branch `longview/foo` (preview: …). Cancel that and start fresh, or proceed with this one as a `redo` of the open draft?" |

## 12. Testing

The brief's SPA has no JS/TS test framework today — `package.json` ships only `next`, `eslint`, and `typescript`. Adding a test runner (Vitest or Jest) for one new component is scope creep. The testing strategy below reflects what's already available; if component tests become valuable later, adopting Vitest is a follow-up.

**Static checks (already in pipeline):**
- `npx tsc --noEmit` — `LongViewData` and `ChartSpec` interfaces must type-check against the sample value in `content/long-view.ts`. Both `null` and populated states must compile.
- `next build` — must succeed locally and on Vercel. Catches missing imports, runtime errors in server components, and the `app/longview/preview` route (if added later).
- `eslint` — must be clean.

**Vercel preview as the render test:**
- Every push to the feature branch triggers a Vercel preview build. The preview URL renders `<LongView>` in the exact production environment (Next.js 16, React 19, Tailwind/CSS, Chart.js). This is the primary correctness check before merging.
- Verify on the preview URL:
  - Section appears between the Overview group and the Banking group
  - Eyebrow renders correctly (`EDITOR'S PIN · POSTED MON 12 MAY`)
  - Optional chart renders when `chart_spec` is present, is omitted when null
  - Diff-mode toggle (`localStorage.thebrief.diffMode = "1"`) applies `tb-diff-stale` when today > posted_at (test by setting `posted_at` to yesterday in a draft and re-pushing)

**Manual smoke test (end-to-end, post-merge):**
- Upload a representative PDF (e.g., a slide from a BB monetary policy presentation) via Discord on Hetzner
- Verify branch created, Vercel preview builds green, preview URL renders correctly
- Reply `publish`, verify production deploys to `thebrief.clauding-lab.com`, live site shows the section
- The next day: toggle diff mode, verify section blurs

**No Python test surface changes.** The Python pipeline (`brief.cli`, `brief.notifier`, `brief.service`) is untouched.

## 13. Decisions Made (with rationale)

| Decision | Choice | Rationale |
|---|---|---|
| Render mode | Native re-render (extract → re-style) | Visual consistency with the rest of the brief; reuses existing components. |
| Placement | After Overview group, before Banking group | Daily-fresh content hits the reader first (Overview); pinned piece reads as a feature-well interlude, not a stale top-of-page banner. |
| Eyebrow format | `EDITOR'S PIN · POSTED MON 12 MAY` | Cadence is explicit to the reader; mitigates "is this issue stale?" reaction on day 4 of viewing the same pin. |
| Name | The Long View | Banker-native register; cadence-implying; no collision with existing brief vocabulary (`Lens`, `Today's Call`, `Banker Read`). |
| Diff blur | When `tb-diff` AND `today > posted_at` | Daily diff-mode reader stays focused on the day's fresh content; the pinned piece recedes after its post-day. |
| Trigger architecture | Claude Code on Hetzner (Discord) OR Mac terminal | Existing infrastructure; no new bot code; uses subscription billing, not API. |
| Storage | Repo (`content/long-view.ts`), not Supabase | At weekly cadence with manual curation, a DB row is overkill; git is a better audit trail than a `status` enum and partial unique index. |
| Preview mechanism | Vercel preview URLs from feature branch | Free, already deployed, renders exactly as production will — no custom preview route to build/maintain. |
| Prompt location | `docs/longview-workflow.md` + `CLAUDE.md` pointer | Auto-loaded for every session via CLAUDE.md; full recipe stays out of the always-on context to avoid bloat. |
| Recipe style | Human-friendly (~150 lines) | Editor (Adnan) can tune voice and audience guidance over time without re-prompting; readable to both human and Claude. |
| "View original" link | Skipped | User decision. Reader sees only the recreation. |
| Source-attribution field | Skipped | User decision. Editorial voice doesn't include attribution lines. |
| Discord trigger word | `longview` (no leading slash) | User preference. |
| Caption / hint | Optional free-text after `longview` | Lets the editor steer when needed, stays out of the way when the slide is self-explanatory. |
| Discord bot identity | Existing Claude-in-Discord, not a new bot | Avoids building a custom bot just for one workflow. |

## 14. Open Questions / Deferred

- **Stale-branch cleanup.** What happens to `longview/*` branches the user abandons without saying `publish` or `cancel`? Manual `gh pr close` works but is annoying. Probably worth a tiny daily cron on Hetzner that closes any `longview/*` branch older than 14 days. **Deferred** to v1.1.x or to whenever the first orphan branch appears.
- **Mobile Discord upload size limits.** Discord caps non-Nitro attachments at 25 MB. A real slide PDF can be larger; an infographic JPEG usually isn't. If a slide exceeds the limit, the user has to compress before uploading. **Documented in the recipe; no engineering needed.**
- **Multi-Long-View support.** Could the brief carry two pinned pieces (e.g., one weekly + one monthly)? The data model would change from `longView: T | null` to `longView: T[]`. **Out of scope for v1.1.0**, but the schema is forward-extensible.
- **"Pin a Long View *to* a specific issue."** Currently the Long View is global across all issues. A future variant could attach a Long View to issue 109 specifically and let it expire after that issue's day. **Not needed for the current product; flag for v2.**
- **Index of past Long Views.** A small `/longview/archive` page reading the file's git history. **Not requested; defer.**

## 15. Definition of Done

- [ ] `content/long-view.ts` exists with `export const longView: LongViewData | null = null` (initial state, nothing pinned)
- [ ] `types/brief.ts` has `LongViewData` + `ChartSpec` interfaces
- [ ] `app/components/LongView.tsx` renders correctly for non-null data, renders nothing for null
- [ ] `<LongView>` is wired into `ClientApp.tsx` between the Overview group and the Banking group
- [ ] CSS classes added to `app/globals.css` including the `tb-diff-stale` state
- [ ] `tb-diff-stale` triggers on the right combination of body class + `today > posted_at`
- [ ] `docs/longview-workflow.md` is written (full recipe, both halves)
- [ ] `CLAUDE.md` exists at repo root with the pointer (per §10a)
- [ ] Hetzner `/home/adnan/CLAUDE.md` updated with the Long View workflow section (per §10b — applied via Copotron Discord prompt after recipe lives on `main` and Hetzner has `git pull`'d)
- [ ] `npx tsc --noEmit` clean
- [ ] `next build` clean
- [ ] `eslint` clean
- [ ] Vercel preview build green, manual visual check on preview URL passes (placement, eyebrow, optional chart, diff-stale)
- [ ] Manual smoke test passes end-to-end via Discord on Hetzner: real upload, real preview URL, real publish
- [ ] Live site shows `<LongView>` correctly after a publish
- [ ] Diff mode on the next day correctly blurs the section
- [ ] CHANGELOG.md gets a v1.1.0 entry describing the addition
- [ ] No regressions in existing tests
- [ ] Vercel preview build is green before merging the spec implementation PR
- [ ] After merge: tag `v1.1.0`, push, `gh release create` with notes from CHANGELOG

---

## References

- `docs/superpowers/specs/2026-05-15-release-notifier-design.md` — most-recent spec; this one follows the same shape.
- `app/components/Masthead.tsx` — existing rail-clickability map; pattern for how a section component reads body classes and `Asia/Dhaka` dates.
- `lib/format.tsx::formatNewsMeta` — established pattern for pinning `timeZone: "Asia/Dhaka"` to dates to avoid SSR hydration mismatch (React #418).
- `brief/claude/prompts/editor_v6.txt` — existing prompt pattern; the Long View prompt is conceptually similar but operationally different (Claude Code, not API).
- Auto-memory `feedback_chartjs_register_and_preview.md` — chart type changes need `chartConfigs.ts` + `BriefChart.tsx` + Vercel preview smoke-load.
- Auto-memory `feedback_subagent_always.md` — implementation phase should be dispatched via subagent-driven-development.
- Saved session 2026-05-15 — v1.0.0 / v1.0.1 release-day notes; conductor workspace quirks for `gh pr merge` and `--force-with-lease`.
