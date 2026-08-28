# Design — The Brief design language

## What this is

Canonical reference for **how The Brief looks** — typography, color, spacing, components, block kinds. Read it before touching `app/globals.css`, before designing a new section, before composing a Long View.

The companion file `Master.md` covers voice and copy.

---

## Identity

- **Production palette**: `steel-crimson` — cool steel paper background, sharp crimson accent.
- **Alternate palette**: `bone` — warm cream paper, deeper red accent. Used in email rendering and certain preview surfaces.
- **The band**: the masthead (and its sticky-bar echo) sits on a full-bleed `--band` surface that resolves **per theme** (v2.4.0, owner decision 2026-08-28): ink `#0B0F12` in dark, paper in light — light mode is one uninterrupted paper sheet with no dark surfaces. The ink band is the **dark-mode and brand identity** (icons, hero, social card keep the ink ground). The browser chrome follows: `theme-color` is a per-scheme pair (`#E6E9EB` light / `#0B0F12` dark), runtime-synced to the in-app toggle.
- **Mood**: morning-paper rigor. Like a Reuters dealer's screen layered onto FT Weekend.
- Mono typography first. Georgia serif only in email body for editorial weight.
- No shadows. No gradients. No rounded corners > 2px. No animations beyond opacity/blur for stale state.

---

## Theme axis (v2.3.0; band per-theme since v2.4.0)

Light/dark is **orthogonal to palette** and keyed on `<html data-theme>`, set pre-paint by the FOUC guard in `app/layout.tsx` and flipped by `ThemeToggle` (choice persists in `localStorage["thebrief.theme"]`; first visits follow the OS until an explicit click).

- **Dark is steel-crimson only, by decision.** `bone` is the email identity and stays light forever. `color-scheme` is palette-scoped accordingly.
- In dark, the band (#0B0F12) and dark paper (#101418) are ~1.04:1 — **accepted**: dark reads as "all band"; the `--band-rule` border keeps the edge legible.
- In light (v2.4.0), the band IS `--paper` (1.00:1) — the deliberate mirror: light reads as "all paper." The band's and sticky bar's `border-bottom` promote to full `--rule` in light so the seam stays legible (the same call the print contract makes).
- Charts are canvas: token values are snapshotted at build time, so every chart **rebuilds** on a theme flip via `lib/useTheme.ts` in `BriefChart`'s dep array. Print forces `data-theme="light"` (ClientApp's printMode effect + `beforeprint`), which rides the same mechanism.

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

### Band tokens (per-theme since v2.4.0 — ink in dark, paper in light)

The `:root` values are the DARK branch (dark inherits them unchanged); in light every band token re-points at the light palette via `[data-palette="steel-crimson"]:not([data-theme="dark"])`. Do not treat these as cross-palette constants — every consumer (band, sticky bar, band link, on-band toggle, Subscribe panel) resolves per theme.

| Token | Dark (`:root` value) | Light (resolves to) | Role |
|---|---|---|---|
| `--band` | `#0B0F12` | `var(--paper)` `#E6E9EB` | Band ground (masthead, sticky bar, Subscribe CTA panel) |
| `--band-ink` | `#E6E9EB` | `var(--ink)` (16.2:1) | Primary text on the band |
| `--band-ink-2` | `rgba(230,233,235,0.92)` (13.38:1) | `var(--ink-2)` | Today's Call body on the band |
| `--band-mute` | `rgba(230,233,235,0.55)` (5.31:1) | `var(--ink-3)` (6.20:1) | Meta/labels on the band |
| `--band-rule` | `rgba(230,233,235,0.40)` (3.33:1) | `var(--rule-soft)` — hairlines only; the on-band toggle's control border takes an explicit `--ink-3` (rule-soft is 1.55:1, under the 3:1 floor), and the band/sticky `border-bottom` promotes to full `--rule` | Hairlines + control borders on the band |
| `--band-accent` | `oklch(0.62 0.21 25)` (4.77:1) | `var(--accent)` (4.44:1 — rides the recorded small-text exemption) | Accent on the band |

### Palette — `steel-crimson` (production), light and dark

| Token | Light | Dark | Role |
|---|---|---|---|
| `--paper` | `#E6E9EB` | `#101418` | Page background |
| `--paper-2` | `#D9DDE0` | `#161B20` | Card / inset background |
| `--paper-3` | `#C8CDD0` | `#1D242A` | Deeper inset |
| `--ink` | `#0B0F12` | `#DEE3E6` | Primary text |
| `--ink-2` | `#1F2428` | `#C3C9CD` | Secondary text |
| `--ink-3` | `#4F5559` | `#8A9195` | Tertiary text / section labels |
| `--ink-4` | `#7A8084` | `#848B90` | Quaternary / decorative & disabled ONLY |
| `--rule` | `#0B0F12` | `#AEB5B9` | Hair rules (full — dark stays dimmer than text) |
| `--rule-soft` | `rgba(11,15,18,0.20)` | `rgba(222,227,230,0.30)` | Hair rules (soft) |
| `--rule-faint` | `rgba(11,15,18,0.09)` | `rgba(222,227,230,0.16)` | Hair rules (faintest) + tile grout |
| `--accent` | `oklch(0.55 0.21 25)` | `oklch(0.66 0.19 25)` | Headline accents, link underlines |
| `--accent-soft` | `oklch(0.55 0.21 25 / 0.16)` | `oklch(0.66 0.19 25 / 0.16)` | Backgrounds derived from accent |

### Palette — `bone` (alternate)

The legacy cream-paper palette. Used as the email visual identity. **Light forever — no dark variant exists or will.**

| Token | Value |
|---|---|
| `--paper` | `#EDE7DD` |
| `--ink` | `#2B0E12` |
| `--accent` | `oklch(0.42 0.14 25)` |

(Full token set lives in `app/globals.css` under `[data-palette="bone"]`.)

### Semantic tone

| Token | Light (steel-crimson) | Dark | Meaning | When to use |
|---|---|---|---|---|
| `--bull` | `oklch(0.45 0.10 150)` | `oklch(0.62 0.10 150)` | Positive direction | Profit growth, healthy ratio, eligibility met |
| `--bear` | `oklch(0.55 0.21 25)` | `oklch(0.66 0.19 25)` | Negative direction | Loss, NPL widening, regulatory block, default risk |
| `--warn` | `oklch(0.62 0.14 75)` | `oklch(0.70 0.13 75)` | Caution / friction | Rule-imposed, ambiguous outcome, contested |
| `--neu` | `var(--ink-3)` | `var(--ink-3)` | Neutral / monochrome | Default when no directional signal |

`--bear` always equals `--accent` in this identity. Tone tinting is **optional and earned**. Don't tint every value — tint only when the direction is the editorial point.

---

## The crimson budget (v2.3.0 — five jobs)

Accent appears in exactly five jobs; everything else is monochrome:

1. **Live pulse + chart latest-point** — the pulse dot, the chart's latest-point dot and its `.tb-chart-latest` caption (they pair). FIG labels are `--ink-3`.
2. **Today's Call label** (`--band-accent` on the band — resolves per theme since v2.4.0: band red on ink in dark, `--accent` on paper in light).
3. **Bear tone** — LEAD/TODAY'S LEAD flags, bear deltas, bear verdict tints.
4. **Active nav** — `.tb-secnav-item.active` and the lead section's `.is-lead` item.
5. **Underlines** — the Subscribe band link's border, input focus underline, and the submit button's hover label underline.

`::selection` keeps accent. Emphasis inside verdict prose is weight (`--ink`, 500), never accent.

---

## Typography scale (v2.3.0 — the ratified 1c card)

**Ceiling rule: nothing on the brief page renders larger than the wordmark, at any viewport.** (Wordmark floor 40px > the 36px phone runway; desktop 54 > 44 runway > 30 CTA head > 28 titles.)

| Surface | Size (desktop / ≤920 / print) | Weight |
|---|---|---|
| Wordmark | clamp(40px, 5vw, 54px) / same clamp / 44px | 200 |
| Section title | 28px inline after its `§NN · Group` eyebrow / 24 / 24 | 300 |
| Banker runway number | 44 / 36 / — | 200 |
| Banker verdict | 17 (19 hero) | 300 |
| Subscribe CTA head | 30 / 26 / hidden | 200 |
| Today's Call body | clamp(13px, 1.6vw, 15px), normal (not italic) | 400 |
| KPI tile value | 16px | 300 |
| Snapshot cell value | 18px | 300 |
| TLDR | 13px, normal | 400 |
| Long View title | clamp(20px, 2.4vw, 26px) | 400 |
| Long View stat value | clamp(30px, 3.5vw, 44px) | 200 |
| Long View lead | 13.5px, normal | 400 |
| Body prose (analysis, Long View prose) | ≥13px — compactness comes from spacing and chrome, never body-copy shrink | 300–400 |
| Bar chart label | 11px | 500 |
| Comparison row value | 17–19px | 300 |

**Label tier (floor 9px):** any uppercase label carrying load-bearing information at ≤10.5px sits on `--ink-3`, never `--ink-4` (`--ink-4` = decorative marks and disabled states only). KPI/snapshot tile labels 9px/500/0.14em; section eyebrow 9.5px/500/0.16em (scoped `.tb-section-head .eyebrow`); group label 10px/500/0.16em; news meta 9.5px; FIG label 9.5px/600/0.14em; watch/risk headers 9.5px/600.

Letter-spacing:
- Small-caps eyebrows: **0.14–0.18em** (the 0.22em tier is retired)
- Normal body text: **−0.005em** (slightly tighter than default)
- Stat values: **−0.01em**

---

## Long View block kinds

The Long View is the only surface with a composable block system. Five block kinds ship in v1.3.0:

| Kind | When to use | Visual behavior |
|---|---|---|
| `prose` | Argumentative essay, single-topic analysis | 1–3 mono paragraphs, optional eyebrow |
| `comparison` | Before/after grid (3+ rows) | 2-col card grid, auto-promotes to 3-col at ≥7 rows, tone-tinted "after" value |
| `stat` | Single headline metric | Large mono value (≤44px — under the wordmark ceiling) + small-caps label + 1–2 sentence body |
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
| `.hair` | `--rule` | Masthead / Long View top-and-tail separators (band-scoped to `--band-rule` inside the band) |
| `.hair-soft` | `--rule-soft` | Between sections, between block rows |
| `.hair-faint` | `--rule-faint` | Inside complex grids only — easy to overuse. Also the tile-grid grout ground. |

---

## Section structure

Every regular brief section follows the same internal grid (top-to-bottom):

1. **Head row** — `§NN · Group` eyebrow inline-baseline with the 28px title; verdict line right-aligned with its tone mark.
2. **TLDR strip** — one 13px paragraph.
3. **Chart** — when data warrants (`SignatureChart` or section-specific `BriefChart`) — or the news rail for chartless sections.
4. **KPI tile grid** — every stored metric as a grout-gap tile (label → value → sub → vintage footer). **Summary pills are absorbed into this grid**: pills are highlight KPIs (per the shipped editor prompt), deduplicated against metric values; survivors render as tiles after the metrics.
5. **DS30 movers** — where present.
6. **Banker read** — verdict / watch / risk three-line, runway number.
7. **Analysis** — labeled paragraph block.

A sticky `SecNav` rail tracks the active section via IntersectionObserver; the lead (weight ≥ 2) section's item carries the accent.

The **snapshot strip** above the SecNav derives six canonical cells (USD/BDT mid, DSEX, 91d T-Bill cut-off, Brent, Gold, Monthly Remittance) from section metrics whenever no dedicated snapshot section exists — which is every real issue today.

---

## PWA (v2.3.0)

- Installable: `app/manifest.ts` (standalone display, `#0B0F12` ground) + band-identity icons ("B." mark; maskable variant keeps the mark in the central safe zone). The manifest ground stays ink even with a paper light mode: manifest splash is Android-only behavior (iOS ignores it), and the launch frame staying the brand mark is deliberate. Icons, hero, and the social card keep the ink ground — the brand mark is dark; the light app is not.
- **Online-only by decision** — no service worker; the local `lastBrief` cache is write-only. A minimal SW (shell + last issue) is the queued follow-up.
- Safe-area inset ownership lives in `app/globals.css` §4.3-tagged rules: `.tb-body`/`.tb-band-inner` (sides), `.tb-secnav` (top calc), `.tb-stickybar-inner` (top + sides), `.tb-foot` (sides + home-indicator bottom), `.tb-skip:focus`. **Longhands only** — a later `padding:` shorthand silently wipes an inset longhand.
- iOS status bar is `default` (v2.4.0): an opaque system bar following the OS appearance. `black-translucent` (v2.3.0) drew white glyphs over the page — sound only while the top of every route was ink, which a paper light mode (and /archive, which never had the band) breaks; iOS offers no per-theme API for this static meta. Accepted residual: in dark standalone the bar follows the OS, mismatching only when the in-app toggle diverges from it.

---

## Email design

The release email mirrors the **bone** palette, not the steel-crimson site palette. This is deliberate — email lives in inboxes where the visual contract has to survive the recipient's client and dark-mode rendering. The cream paper reads as "morning newspaper" across light/dark modes and across Gmail/Outlook/Apple Mail. **The site's dark theme changes nothing here: bone = email = light forever.**

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

## Accessibility exemptions (recorded, deliberate)

- **De-emphasis opacities fail AA on purpose** — transient states, not AA-bound: `0.32` (quiet sections, unavailable-in-diff), `0.34` (unchanged rows/tile content in diff), `0.40` (statstack in diff), `0.42` (Long View diff-stale), `0.55` (`is-unavailable`), `0.65` (quiet hover).
- **Light `--accent` small text at 4.44:1** on `--paper` (chart-latest caption, Today's Call label off-band, banker eyebrow, active nav number) — pre-existing, marginally under AA's 4.5:1; recorded with an optional lift to ~`oklch(0.52 0.21 25)` as an owner decision.

---

## Responsive

**Principle (v2.3.0): no new breakpoints.** Density comes from `auto-fit`/`minmax()` grids and `clamp()` type, not added media queries. **Stretched orphan cells at intermediate widths are accepted** (e.g. 6 snapshot cells → 4+2 at 768/834) — revisit with per-grid caps only if real screenshots read badly.

- KPI tiles: `minmax(130px, 1fr)`; snapshot cells `minmax(150px, 1fr)`; news rail `minmax(220px, 1fr)` (headlines keeps its fixed 4-col contract).
- Long View comparison block: 2-col grid → single column below 640px viewport
- 3-col comparison auto-promotion (at ≥7 rows) collapses to 2-col below 900px, single below 640px
- Bar chart SVG: renders at **1:1 CSS pixels** (ResizeObserver-measured viewBox, v2.4.0) so its 11px labels are real 11px at every width — the earlier stretch-to-fit scaling rendered them as low as ~4.7px on tablets, under the 9px label floor
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
- No raw hex values in component code — always reference a CSS variable. **Carve-out:** `app/manifest.ts` may carry the `#0B0F12` literal, `layout.tsx`'s `viewport.themeColor` carries the per-scheme pair (`#E6E9EB` / `#0B0F12`), and `ClientApp`'s theme-color meta effect mirrors the same two hexes (metadata surfaces can't read CSS variables — the three sites must stay in sync with `--paper`/`--band`); image assets carry raw color by nature.
- No fonts/sizes/colors specified inside `content/long-view.ts` data — the component renders with palette tokens

---

## Versioning

This document tracks the visual contract as of **v2.4.0** (light mode fully paper — the ink band becomes the dark-mode and brand identity; per-theme band tokens; per-scheme browser chrome; iOS status bar `default`; bar-chart type at 1:1 px; on v2.3.0's 1c facelift base). Changes that affect the contract — new block kinds, palette tweaks, typography revisions — bump the minor or major version per `CHANGELOG.md` and require a separate platform-level PR (not a per-pin Long View PR).

Per-pin Long View PRs must NOT touch `app/globals.css`, `Design.md`, `CHANGELOG.md`, or `package.json`.
