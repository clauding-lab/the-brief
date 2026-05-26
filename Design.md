# Design — The Brief design language

## What this is

Canonical reference for **how The Brief looks** — typography, color, spacing, components, block kinds. Read it before touching `app/globals.css`, before designing a new section, before composing a Long View.

The companion file `Master.md` covers voice and copy.

---

## Identity

- **Production palette**: `steel-crimson` — cool steel paper background, sharp crimson accent.
- **Alternate palette**: `bone` — warm cream paper, deeper red accent. Used in email rendering and certain preview surfaces.
- **Mood**: morning-paper rigor. Like a Reuters dealer's screen layered onto FT Weekend.
- Mono typography first. Georgia serif only in email body for editorial weight.
- No shadows. No gradients. No rounded corners > 2px. No animations beyond opacity/blur for stale state.

---

## Tokens (CSS custom properties)

All tokens are declared in `app/globals.css` under `:root` and the per-palette selectors. Components reference tokens — never raw values.

### Geometry

| Token | Value | Use |
|---|---|---|
| `--rhythm` | 28px | Vertical rhythm unit between major blocks |
| `--gutter` | 24px | Horizontal gutter / standard padding |
| `--hair` | 1px | Hair-rule thickness |

### Type

| Token | Value | Use |
|---|---|---|
| `--mono` | JetBrains Mono via next/font, fallback to `ui-monospace, 'SF Mono', Menlo, Consolas` | Everything except email body |

Email body uses **Georgia, serif** explicitly inlined (not as a CSS var) for client compatibility. Chrome inside the email uses `-apple-system, Segoe UI, Helvetica, Arial`.

### Palette — `steel-crimson` (production)

| Token | Value | Role |
|---|---|---|
| `--paper` | `#E6E9EB` | Page background |
| `--paper-2` | `#D9DDE0` | Card / inset background |
| `--paper-3` | `#C8CDD0` | Deeper inset |
| `--ink` | `#0B0F12` | Primary text |
| `--ink-2` | `#1F2428` | Secondary text |
| `--ink-3` | `#4F5559` | Tertiary text / section labels |
| `--ink-4` | `#7A8084` | Quaternary / disabled |
| `--rule` | `#0B0F12` | Hair rules (full) |
| `--rule-soft` | `rgba(11,15,18,0.20)` | Hair rules (soft) |
| `--rule-faint` | `rgba(11,15,18,0.09)` | Hair rules (faintest) |
| `--accent` | `oklch(0.55 0.21 25)` | Headline accents, link underlines |
| `--accent-soft` | `oklch(0.55 0.21 25 / 0.16)` | Backgrounds derived from accent |

### Palette — `bone` (alternate)

The legacy cream-paper palette. Used as the email visual identity.

| Token | Value |
|---|---|
| `--paper` | `#EDE7DD` |
| `--ink` | `#2B0E12` |
| `--accent` | `oklch(0.42 0.14 25)` |

(Full token set lives in `app/globals.css` under `[data-palette="bone"]`.)

### Semantic tone

| Token | Value (steel-crimson) | Meaning | When to use |
|---|---|---|---|
| `--bull` | `oklch(0.45 0.10 150)` | Positive direction | Profit growth, healthy ratio, eligibility met |
| `--bear` | `oklch(0.55 0.21 25)` | Negative direction | Loss, NPL widening, regulatory block, default risk |
| `--warn` | `oklch(0.62 0.14 75)` | Caution / friction | Rule-imposed, ambiguous outcome, contested |
| `--neu` | `var(--ink-3)` | Neutral / monochrome | Default when no directional signal |

Tone tinting is **optional and earned**. Don't tint every value — tint only when the direction is the editorial point.

---

## Typography scale

| Surface | Token | Size | Weight | Line-height |
|---|---|---|---|---|
| Long View title | mono | 24–32px (responsive) | 400 | 1.15 |
| Long View lead | mono | 14px | 400 | 1.55 |
| Long View prose | mono | 13.5px | 300 | 1.65 |
| Banker read paragraph | mono | 14.5px | 300 | 1.55 |
| Banker read label | mono small-caps | 10.5px | 600 | — |
| Block eyebrow | mono small-caps | 10.5px | 600 | — |
| Stat value | mono | 48–72px | 500 | 1.0 |
| Bar chart label | mono | 11px | 500 | — |
| Comparison row value | mono | 17–19px | 500 | 1.2 |

Letter-spacing:
- Small-caps eyebrows: **0.22em**
- Normal body text: **−0.005em** (slightly tighter than default)
- Stat values: **−0.01em**

---

## Long View block kinds

The Long View is the only surface with a composable block system. Five block kinds ship in v1.3.0:

| Kind | When to use | Visual behavior |
|---|---|---|
| `prose` | Argumentative essay, single-topic analysis | 1–3 mono paragraphs, optional eyebrow |
| `comparison` | Before/after grid (3+ rows) | 2-col card grid, auto-promotes to 3-col at ≥7 rows, tone-tinted "after" value |
| `stat` | Single headline metric | Huge mono value + small-caps label + 1–2 sentence body |
| `bullet-list` | Listed takeaways ("three signals," "key drivers") | Vertical list with leading ▸ marks, tone-tintable per item |
| `bar-chart` | Ranked numerical values, optional threshold | Inline SVG horizontal bars with optional vertical dashed reference line |

**Composition rules:**

- Maximum **4 blocks** per Long View.
- Don't repeat the same block kind back-to-back (two prose → merge into one).
- Block ordering: most-important visual block first, supporting blocks after, closing block last.
- Tone is structural — `bull` / `bear` / `warn` / `neu` — and optional. Don't tint every row.

The full editorial recipe lives in `docs/longview-workflow.md`.

---

## Hair rules

Three weights, all 1px:

| Class | Variable | Use |
|---|---|---|
| `.hair` | `--rule` | Masthead / Long View top-and-tail separators |
| `.hair-soft` | `--rule-soft` | Between sections, between block rows |
| `.hair-faint` | `--rule-faint` | Inside complex grids only — easy to overuse |

---

## Section structure

Every regular brief section follows the same internal grid (top-to-bottom):

1. **Section label** — small-caps, 10.5px, `--ink-3`
2. **Section title** — mono, larger
3. **Verdict line** — one-sentence stance
4. **TLDR strip** — one paragraph
5. **Summary pills** — categorical signals (e.g., "credit growth: weak," "spread: tightening")
6. **Banker read** — verdict / watch / risk three-line
7. **Metrics** — table of indicators with deltas and sparklines
8. **Chart** — when data warrants (`SignatureChart` or section-specific `BriefChart`)
9. **News** — top 3–5 headlines for the section

A sticky `SecNav` rail tracks the active section via IntersectionObserver.

---

## Email design

The release email mirrors the **bone** palette, not the steel-crimson site palette. This is deliberate — email lives in inboxes where the visual contract has to survive the recipient's client and dark-mode rendering. The cream paper reads as "morning newspaper" across light/dark modes and across Gmail/Outlook/Apple Mail.

| Token | Value | Use |
|---|---|---|
| Background | `#f7f2e8` | Page background |
| Card | `#fdfaf4` | Email body box |
| Border | `#e6dfd1` | Hair rules |
| Body ink | `#1a1814` | Primary text |
| Subtitle ink | `#7a6f5c` | Dates, captions |
| Section label | `#a67c2e` | Amber-gold small-caps |
| Underline | `#c9b88a` | Link underlines |

- Max width: **600px**
- Body font: **Georgia, serif** (15px / 1.65 line-height) for "Today's Call" paragraphs
- Lead headline: Georgia serif 18px with subtle border-bottom underline
- Chrome (eyebrows, dates): system sans
- Footer: 10px, muted ink, with mailto unsubscribe link

**Delivery contract:** one Brevo API call per subscriber so recipients never see each other's emails in the To: header. See `brief/notifier.py::send_via_brevo` (v1.3.1+).

---

## Diff-stale state

When the brief is being viewed as "today's diff vs prior issue":

- `.tb-longview.tb-diff-stale` — opacity 0.42, blur 1px, `pointer-events: none`, transitions over 200ms
- Applied to Long View when its `posted_at` is strictly before today's BDT calendar date AND the `tb-diff` body class is set
- Use for visually backgrounding non-fresh content during diff review

---

## Responsive

- Long View comparison block: 2-col grid → single column below 640px viewport
- 3-col comparison auto-promotion (at ≥7 rows) collapses to 2-col below 900px, single below 640px
- Bar chart SVG: scales via `preserveAspectRatio="xMidYMid meet"` — no special breakpoint logic needed
- Section metrics table: horizontal scroll on narrow viewports rather than wrapping
- Email: hardcoded 600px max-width; mobile clients render with proportional shrink

---

## Forbiddens

- No shadows (anywhere on the site or in email)
- No rounded corners > 2px — corners stay near-square for "morning paper" feel
- No gradients
- No animations except opacity + blur for diff-stale state
- No fonts outside the mono stack (and Georgia serif in email body only)
- No colors outside palette tokens
- No emoji in editorial copy or UI chrome
- No icons in section headers — use small-caps labels instead
- No raw hex values in component code — always reference a CSS variable
- No fonts/sizes/colors specified inside `content/long-view.ts` data — the component renders with palette tokens

---

## Versioning

This document tracks the visual contract as of **v1.3.1**. Changes that affect the contract — new block kinds, palette tweaks, typography revisions — bump the minor or major version per `CHANGELOG.md` and require a separate platform-level PR (not a per-pin Long View PR).

Per-pin Long View PRs must NOT touch `app/globals.css`, `Design.md`, `CHANGELOG.md`, or `package.json`.
