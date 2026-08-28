# The Brief — 1c facelift change list, v2

**Supersedes `facelift-changes.md` (v1) entirely.** This is the single source of truth for the facelift: values, code, decisions, and PR slicing. Where this file and the v1 README or the prototype disagree, this file wins — the prototype (`The Brief 1c App.dc.html`) remains a *mood* reference only; every implementable value lives here. Grounded in `app/globals.css`, `Masthead.tsx`, `ClientApp.tsx`, `SnapshotStrip.tsx`, `layout.tsx`, `lib/chartConfigs.ts` as of v2.2.0 / `main` (`2149c8e`).

**Why a v2:** a 20-agent adversarial review (2026-08-25) verified v1's "Now" column as accurate but found six implementation-breaking gaps, a density scale that undershot the ratified 1c review card, and three false premises. This v2 was then itself adversarially verified twice (values/contrast/code pass + completeness pass, 2026-08-26) and every confirmed defect folded back in. §11 lists the judgment calls awaiting owner veto.

---

## 0 · What changed from v1

| v1 defect | v2 resolution |
|---|---|
| Density rows changed desktop base rules only; ≤920px / print overrides inverted the design on mobile & print (review-confirmed) | Every density row in §6 carries paired ≤920px / print values; the two `is-unavailable` rows are paired too |
| `.tb-btn-cta` invisible on band (`--ink` = `--band` = `#0B0F12`) (review-confirmed) | Masthead Subscribe becomes a band text link (§5.3); the `.tb-btn-cta` CSS block is deleted |
| Masthead descendants unstyled on the band (kernel confirmed: `.tb-published`; the rest specified only in README/prototype, which v2 supersedes) | Complete `.tb-band`-scoped override block in §5.2; Published stamp explicitly kept |
| Chart.js snapshots palette at build; toggle never repaints canvases (review-confirmed) | `lib/useTheme.ts` + `theme` in BriefChart's dep array (§3, ships in PR A) |
| Print renders dark tokens on white; band prints as ink slab; toggle not in hide lists (review-confirmed) | Full print contract in §9: light tokens forced at body AND `:root` level, alias tokens included, theme forced light in print modes so charts follow, band reset, both hide lists, scale rows updated |
| `.tb-stickybar .meta` (0,2,0) outranks band color → 2.54:1 (review-confirmed) | Explicit `.tb-stickybar .meta { color: var(--band-mute) }` (§5.4) |
| Dark `.tb-cta-dark`: panel inverts near-white and its three hardcoded `rgba(244,239,230,·)` texts collapse to 1.07–1.10:1; v1's token swap didn't fix the background | Panel repointed to `--band`/`--band-ink` (§7.8); two-tier alpha preserved via `--band-ink-2` |
| Scale compressed past the ratified 1c card (titles 20, verdicts 13, runway 34) (review-confirmed) | Ratified card numbers restored: titles 28, verdicts 17, runway 44, wordmark ≤54 (§6) |
| Long View untouched → its 64px stat out-scales the new wordmark (review-confirmed) | Long View compact pass (§7.6) + ceiling rule |
| Label tier at 8.5px `--ink-4` fails AA in both themes | Label floor 9px; load-bearing labels on `--ink-3`; dark `--ink-4` = `#848B90` (§1) |
| ThemeToggle froze first-visit OS preference; null-render CLS; contradictory ARIA; 17px hit target | Rewritten component (§2): persists only on click, storage re-checked inside the OS listener, CSS-keyed label (no hydration dependency at all), fixed accessible name, ≥24px target |
| "ONE PR" vs "3 PRs" contradiction; Design.md bundled into a feature PR (landmine 8) | Four PRs (§10) |
| False premises: `cover_metric` "always null"; `lastBrief` "warm start"; "tagline lives in the footer" | Corrected: Cover retirement + snapshot fallback + skip-link fix (§7.5); PWA declared online-only (§4.4); tagline moved into the footer line (§5.3) |
| Safe-area rules shrank the desktop gutter and were dead/overridden on phones | `max()`/`calc()` longhands + paired ≤920px inset rules incl. the sticky bar (§4.3) |
| README/values contradictions (chart-latest accent, band-vs-ink naming, Today's Call rgba, accent-budget arithmetic) | Resolved with explicit decisions (§8, §5); raw rgba values tokenized |

Deliberately **cut from scope**: the paired Remittance+Commodities row (needs invented pairing logic; revisit post-ship if wanted).

---

## 1 · Tokens — `app/globals.css`

Add to `:root` (cross-palette; the band is ink in **both** themes — that is the point of the band):

```css
:root {
  --band:        #0B0F12;
  --band-ink:    #E6E9EB;
  --band-ink-2:  rgba(230, 233, 235, 0.92);  /* Today's Call body on the band — 13.38:1 */
  --band-mute:   rgba(230, 233, 235, 0.55);  /* 5.31:1 on --band — meta/labels */
  --band-rule:   rgba(230, 233, 235, 0.40);  /* hairlines + control borders on the band — 3.33:1, clears the 3:1 non-text floor */
  --band-accent: oklch(0.62 0.21 25);        /* 4.77:1 on --band */
}
```

v1's `--band-rule` at 0.25 alpha measured 2.00:1 — below the 3:1 UI-component floor for the toggle's border; 0.40 clears it. The byline's v1 value `rgba(230,233,235,0.45)` (3.92:1 at 9px — fails AA) is **not** carried over; the byline uses `--band-mute`.

Dark theme block (theme attribute lives on `<html>` alongside `data-palette`):

```css
[data-palette="steel-crimson"][data-theme="dark"] {
  --paper:        #101418;
  --paper-2:      #161B20;
  --paper-3:      #1D242A;   /* currently referenced nowhere — kept for table symmetry */
  --ink:          #DEE3E6;
  --ink-2:        #C3C9CD;
  --ink-3:        #8A9195;   /* 5.78:1 on --paper */
  --ink-4:        #848B90;   /* 5.35 on --paper, 5.01 on --paper-2, 4.54 on --paper-3 — AA on every surface.
                                (v1's #5C6367 was 3.03:1; the first v2 draft's #787F84 still failed on paper-2/3.) */
  --rule:         #AEB5B9;   /* 8.91:1. v1 had #DEE3E6 (= --ink): hairlines as bright as text. Now rule < text. */
  --rule-soft:    rgba(222, 227, 230, 0.30);
  --rule-faint:   rgba(222, 227, 230, 0.16); /* v1 0.10 was near-invisible; matters for chart gridlines */
  --accent:       oklch(0.66 0.19 25);       /* 5.44:1 on --paper, 5.10:1 on --paper-2. v1's 0.62/0.21 measured
                                                4.58:1 on --paper and 4.29:1 on --paper-2 — an outright AA fail there. */
  --accent-soft:  oklch(0.66 0.19 25 / 0.16);
  --bull:         oklch(0.62 0.10 150);      /* 5.31:1 */
  --bear:         oklch(0.66 0.19 25);       /* bear always equals accent in this identity */
  --warn:         oklch(0.70 0.13 75);       /* 6.79:1 */
  --neu:          var(--ink-3);
}
html[data-palette="steel-crimson"][data-theme="dark"]  { color-scheme: dark; }
html[data-palette="steel-crimson"][data-theme="light"] { color-scheme: light; }
```

Notes:

- **`color-scheme` is palette-scoped** (v1 applied it unconditionally, which would have given a dark-toggled `bone` page dark scrollbars around light paper). **Dark mode is steel-crimson-only, by decision** — `bone` is the email identity (Design.md:159) and stays light forever; PR D writes this into Design.md.
- The alias tokens `--color-muted: var(--ink-3)` / `--color-surface-2: var(--paper-2)` (globals.css:25-26) follow the theme **only because `:root` and the dark block sit on the same element (`<html>`)** — a `var()` inside a custom property is substituted where the property is *declared*, and descendants inherit the already-substituted value. This is why §9's print blocks must redeclare the aliases explicitly (browser-verified: without that, held-over text and the lens pill print with dark values).
- `.tb-delta-bull/.tb-delta-bear .tb-delta-pct` uses `opacity: 0.7` (globals.css:807-808) — ~3:1 in dark. Add: `[data-theme="dark"] .tb-delta-bull .tb-delta-pct, [data-theme="dark"] .tb-delta-bear .tb-delta-pct { opacity: 0.9; }` (4.52/4.60:1).
- **Diff-mode / de-emphasis opacities fail AA in both themes today, deliberately.** The full exempt set (PR D records it): `0.32` (quiet sections :847, unavailable-in-diff :507), `0.34` (unchanged rows :854), `0.40` (statstack :862), `0.42` (Long View diff-stale :1446), `0.55` (`is-unavailable` :494), `0.65` (quiet hover :850). Transient de-emphasis, not AA-bound.
- **Label-tier rule (new, both themes):** any uppercase label carrying load-bearing information at ≤10.5px sits on `--ink-3`, never `--ink-4` (`--ink-4` = decorative marks and disabled states — globals.css:20-24 already says this; PR C moves the three violators `.tb-secnav-item .num` :383, `.tb-group-label` :469, `.tb-unavailable-note` :500 to `--ink-3`; the input placeholder :750 may stay).
- **Light-accent AA note:** light `--accent` `oklch(0.55 0.21 25)` measures **4.44:1 on `--paper`** / 3.96:1 on `--paper-2` — marginally below AA for the small accent-text jobs (§8: chart-latest 11px, Today's Call label, banker eyebrow, active nav num). Pre-existing, unchanged by this facelift; recorded as an exemption in PR D, with an optional lift to ~`oklch(0.52 0.21 25)` as owner veto §11.11.

## 2 · Theme toggle — `app/components/ThemeToggle.tsx` + FOUC guard

**Single source of truth is `document.documentElement.dataset.theme`**, written pre-hydration by the FOUC script and mutated only by the toggle (and the OS listener below). The button's visible label is CSS-keyed on `[data-theme]`, so the component renders identically on server and client — no hydration dependency, no first-frame flicker, no `suppressHydrationWarning` needed anywhere in the component.

```tsx
"use client";
import { useEffect } from "react";

const KEY = "thebrief.theme";

export function ThemeToggle({ onBand = false }: { onBand?: boolean }) {
  // Follow OS changes only while the visitor has never chosen explicitly.
  // localStorage is re-checked INSIDE the handler — a click that stores a
  // choice immediately stops the OS listener from overriding it.
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      try {
        const s = localStorage.getItem(KEY);
        if (s === "light" || s === "dark") return;
      } catch { /* ignore */ }
      document.documentElement.dataset.theme = mq.matches ? "dark" : "light";
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const flip = () => {
    const cur = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(KEY, next); } catch { /* ignore */ }
  };

  return (
    <button
      type="button"
      className={`tb-theme-toggle${onBand ? " on-band" : ""}`}
      aria-label="Toggle dark mode"
      onClick={flip}
    >
      <span aria-hidden="true">◐ </span>
      <span className="when-light">Dark</span>
      <span className="when-dark">Light</span>
    </button>
  );
}
```

ARIA model: plain action button with the **state-independent** name "Toggle dark mode" (a state-dependent name would be stale for the first client pass on dark loads); the glyph is hidden from AT.

```css
.tb-theme-toggle {
  font: inherit; font-size: 9.5px; letter-spacing: 0.16em; text-transform: uppercase;
  padding: 7px 12px; min-height: 24px;          /* WCAG 2.5.8 floor; v1 was ~17px */
  border: 1px solid var(--ink-3);               /* --rule-soft measured 1.54:1 light / 2.35:1 dark — fails the 3:1
                                                   component floor; --ink-3 is 6.20:1 light / 5.78:1 dark */
  color: var(--ink-3); background: transparent; cursor: pointer;
}
.tb-theme-toggle.on-band { color: var(--band-ink); border-color: var(--band-rule); }
.tb-theme-toggle .when-dark { display: none; }
[data-theme="dark"] .tb-theme-toggle .when-dark  { display: inline; }
[data-theme="dark"] .tb-theme-toggle .when-light { display: none; }
```

Mount points: masthead meta row right cell (`onBand`), **and** the StickyBar right cell (`onBand`). The StickyBar's hidden state is `aria-hidden` + `pointer-events: none` but still in tab order — add `inert` to the StickyBar `<header>` when not visible (StickyBar.tsx:17) so the hidden toggle can't be tabbed into. Both mounts are in the print hide lists (§9.3).

**FOUC guard** — first child of `<body>` in `layout.tsx` (the layout renders no `<head>` element; a body-first blocking script is the standard next-themes placement and runs before paint):

```tsx
<body>
  <script dangerouslySetInnerHTML={{ __html:
    `try{var t=localStorage.getItem("thebrief.theme");if(t!=="light"&&t!=="dark"){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=t}catch(e){}`
  }} />
  {children}
</body>
```

`<html>` gains `suppressHydrationWarning` (the script adds `data-theme` before hydration; React 19 would otherwise warn — and might reconcile the attribute away):

```tsx
<html lang="en" data-palette="steel-crimson" suppressHydrationWarning className={jetbrainsMono.variable}>
```

CSP note: this is the app's first inline script; if the planned nonce-based CSP ever lands it needs the nonce. One-line comment in layout.tsx, no code now.

**`theme-color` decision:** browser-chrome color stays `#0B0F12` in both themes — "the nameplate is always ink" extended to the browser UI. The toggle does not mutate the meta tag. (Owner veto §11.6.)

## 3 · Chart re-theming — `lib/useTheme.ts` + `BriefChart.tsx` (ships in PR A)

Chart.js paints to canvas: `buildPalette()` resolves 13 tokens via `getComputedStyle(document.documentElement)` at chart-build time (`lib/chartConfigs.ts:87-125`) and the strings are baked into the config. Nothing re-renders charts when `data-theme` flips — the dep array at `BriefChart.tsx:137` has no theme input — so a toggle leaves every mounted canvas drawn in the old theme's inks (light `--ink` on dark paper = 1.04:1, `--ink-2` 1.18:1, ticks `--ink-3` 2.45:1 — effectively invisible). Canvas count: the `SECTION_TO_CHART` map has 9 entries; **8** charts mount on real issues (204/205), **4** on the bundled 117 fixture — so a preview smoke-load with the 117 fixture exercises only 4 of 9 configs (§10.1 uses issue 205 as well). The chartConfigs.ts:83-84 comment anticipated exactly this switch. Fix:

```ts
// lib/useTheme.ts
"use client";
import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

function subscribe(onChange: () => void) {
  const mo = new MutationObserver(onChange);
  mo.observe(document.documentElement, { attributeFilter: ["data-theme"] });
  return () => mo.disconnect();
}
const getSnapshot = (): Theme =>
  document.documentElement.dataset.theme === "dark" ? "dark" : "light";
const getServerSnapshot = (): Theme => "light";

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
```

(`useSyncExternalStore` uses `getServerSnapshot` for both the server and hydration render, then re-reads `getSnapshot` post-commit — so no hydration mismatch on dark loads. One observer per consumer (~9 on a full page) is acceptable; a module-level singleton with a listener set is a fine refinement, not required.)

In `BriefChart.tsx`:

```tsx
const theme = useTheme();
// effect deps: [section.series, section.notes, configKey, reducedMotion, staleSeries, theme]
```

The existing destroy-on-cleanup path (BriefChart.tsx:126-132) makes the rebuild safe. `Section.tsx`'s frozen `staleSeries` memoization (:17-22, :61-76 — a prior review fix) is untouched: only a real theme flip re-runs the effect. SVG surfaces (`Sparkline.tsx`, `SignatureChart.tsx`) use live `var()` and theme for free. Print interaction: §9.1c forces `data-theme` to light in print modes, which re-runs this same effect — one mechanism covers toggle and print.

## 4 · PWA — installable on iPhone/iPad

### 4.1 Manifest — new `app/manifest.ts`

```ts
import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "The Brief — Bangladesh business intelligence",
    short_name: "The Brief",
    description: "Daily macro & markets read for Bangladesh banking professionals.",
    start_url: "/",
    display: "standalone",
    background_color: "#0B0F12",
    theme_color: "#0B0F12",
    icons: [
      { src: "/icon.png", sizes: "192x192", type: "image/png" },
      { src: "/apple-icon.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
```

`app/icon.png` (192×192) and `app/apple-icon.png` (512×512) already serve at `/icon.png` / `/apple-icon.png` (verified real routes) — the manifest points at them instead of duplicating files. Only `public/icons/maskable-512.png` is new — **it must exist in the same PR**: Chrome silently withholds the install prompt when a declared icon 404s.

**Icon refresh:** both PNGs are dated 5 May (pre-facelift identity). Regenerate all three in PR B with the new mark (band ground, `--band-ink` "B." with `--band-accent` period). Raw hex in image assets is fine; the manifest/viewport hex needs the Design.md carve-out (§10.3 item 8).

### 4.2 `layout.tsx` — viewport + appleWebApp

There is currently no `viewport` export and no `themeColor` (verified), so those are additive. `appleWebApp` **already exists** at layout.tsx:42-44 — extend it, don't add a duplicate key:

```ts
import type { Viewport } from "next";
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#0B0F12",
};
// extend the EXISTING metadata.appleWebApp object:
appleWebApp: { title: "The Brief", statusBarStyle: "black-translucent" },
```

Landmine 19: `MetadataRoute.Manifest` and `Viewport` are Next 16 APIs — verify against Context7 (`/vercel/next.js` at the repo's version) before writing.

### 4.3 Safe areas — `app/globals.css`

Rules: insets appear in **both** the base rules and the ≤920px block (each preserving its tier's gutter), and every affected selector is written as **one rule using longhands** — a later `padding:` shorthand silently wipes an earlier inset longhand, which is exactly how the first draft broke itself. Canonical declarations (these are THE padding declarations for these selectors; §5/§6 add no others):

```css
/* base (desktop gutter stays 32px) */
.tb-body   { padding-left: max(32px, env(safe-area-inset-left));
             padding-right: max(32px, env(safe-area-inset-right)); }
.tb-secnav { top: calc(50px + env(safe-area-inset-top)); }
.tb-stickybar-inner { padding: 12px 32px;
                      padding-top: calc(12px + env(safe-area-inset-top)); }
.tb-band-inner { max-width: 1280px; margin: 0 auto;
                 padding-left: max(32px, env(safe-area-inset-left));
                 padding-right: max(32px, env(safe-area-inset-right)); }
.tb-masthead-full { padding-top: calc(24px + env(safe-area-inset-top));
                    padding-bottom: 26px; border-bottom: none; }

/* inside the existing @media (max-width: 920px) block — REPLACE the current
   .tb-secnav / .tb-body / .tb-stickybar-inner lines, keeping the 20px gutter */
.tb-secnav { top: calc(48px + env(safe-area-inset-top)); margin: 0 -20px; }
.tb-body   { padding-left: max(20px, env(safe-area-inset-left));
             padding-right: max(20px, env(safe-area-inset-right)); }
.tb-band-inner { padding-left: max(20px, env(safe-area-inset-left));
                 padding-right: max(20px, env(safe-area-inset-right)); }
.tb-stickybar-inner { padding: 10px 20px;
                      padding-top: calc(10px + env(safe-area-inset-top)); }
```

The sticky bar is the surface that actually sits under the iOS clock with `black-translucent` + `viewportFit: cover` — its inset must survive at ≤920, hence the explicit replacement above (the existing `:967` shorthand would otherwise clobber it). `.tb-statusbar` gets no inset (desktop-only element, `display:none` ≤920).

PR B preview checks: (a) `lib/useNavOffset.ts:29` does `parseFloat(getComputedStyle(el).top)` — confirm in Chrome + Safari standalone the `calc()` resolves to used pixels (the `|| 0` fallback fails silently as "sections land ~50px under the nav"); (b) full-bleed negative margins stay keyed to 32/20px gutters — check for horizontal overflow at 375 landscape on a notched device.

### 4.4 Offline — honest version

**The installed app is online-only in this pass.** v1's justification ("the `thebrief.lastBrief` cache warm-starts") is false: the cache is **write-only** (written at ClientApp.tsx:119-123, read nowhere; the `"cache"` DataSource branch in three components is dead code). A standalone app launched offline shows a bare error page. Decision: ship online-only, state it in the PR body, queue a minimal SW (cache shell + last issue) as the follow-up PR. Optional adjacent fix, own sign-off line (§11.7): wire the cache into ClientApp's initial state so a previously-loaded page warm-starts.

## 5 · The ink band — masthead + sticky bar

### 5.1 Structure: true full-bleed via a band wrapper

v1's `margin: 0 -32px` bleeds only to `.tb-body`'s 1280px content box — a floating 1344px rectangle on a 1920px monitor, while the band-colored StickyBar is viewport-wide; the identity anchor would change shape on scroll. Restructure `ClientApp.tsx` (elisions marked — everything not shown is **unchanged**, including the PREVIEW-MODE banner and `<StickyBar>` between the skip link and the band):

```tsx
<a href="#content" className="tb-skip">Skip to content</a>
{/* …PREVIEW-MODE banner, <StickyBar …/> — unchanged… */}
<div className="tb-band">
  <div className="tb-band-inner">
    <Masthead … />   {/* Masthead's root <header id="masthead"> is unchanged */}
  </div>
</div>
<main id="content" className="tb-body">
  {/* …snapshot strip, secnav, sections, CTA — unchanged… */}
</main>
```

- `.tb-band` is a **`<div>`**, not a `<header>` — Masthead's root already is a `<header>`, and `header` may not nest inside `header`; a second top-level header would also add a spurious `banner` landmark next to StickyBar's.
- The skip link retargets `#content` (`<main id="content">` already exists at ClientApp.tsx:265 and always renders). Do **not** drop the `id` when editing the `<main>` line. Today's `href="#cover"` is already dead on null-cover issues (Cover renders an empty `display:none` div) — this fixes that too.
- `#masthead` (the sticky-reveal observer target, ClientApp.tsx:173) now measures the inner box excluding band padding — see the §5.4 retune note.

```css
.tb-band {
  background: var(--band);
  color: var(--band-ink);
  border-bottom: 1px solid var(--band-rule);
}
/* .tb-band-inner and .tb-masthead-full padding: §4.3 owns those declarations. */
```

In **dark** mode the band (#0B0F12) is nearly the same luminance as dark paper (1.04:1) — accepted: dark reads as "all band", the `--band-rule` border keeps the edge legible. Recorded in Design.md (PR D).

### 5.2 Band-scoped descendant overrides (the block v1 was missing)

```css
.tb-band .hair                        { background: var(--band-rule); }
.tb-band .tb-masthead-meta            { color: var(--band-mute); }
.tb-band .tb-masthead-meta .pulse     { background: var(--band-accent); }  /* light --accent is a visibly darker red on the band (3.56:1) */
.tb-band .tb-published                { color: var(--band-mute); }   /* v2.1.0 honesty stamp — KEPT */
.tb-band .tb-readtime                 { color: var(--band-mute); font-size: 10.5px; }
.tb-band .tb-todays-call              { border-top: 1px solid var(--band-rule); }  /* its only divider from the nameplate row — kept, tokened */
.tb-band .tb-todays-call .label       { color: var(--band-accent); }
.tb-band .tb-todays-call .body        { color: var(--band-ink-2); }
.tb-band .tb-todays-call .byline      { color: var(--band-mute); }
.tb-band .tb-wordmark-big .dot        { color: var(--band-accent); }
.tb-band .tb-masthead-lens-pill       { background: none; padding: 0; border-radius: 0; color: var(--band-mute); }
.tb-band .tb-masthead-lens-pill .tb-mlp-day { color: var(--band-ink); }
```

The **meta row keeps all four elements**: `No./Vol` · `date + lens pill` · `Live pulse + fetch stamp + Published stamp + theme toggle`. The Published stamp is a v2.1.0 honesty fix (Masthead.tsx:54-58: publish time from the payload, page-load clock separate) and must survive. Meta row type stays 10.5px/0.18em; pulse dot stays 6px.

### 5.3 Nameplate row + Subscribe link — `Masthead.tsx` restructure

The hero block becomes a two-cell row (this layout is new — the prototype is not needed to build it):

```css
.tb-masthead-hero {
  display: flex; justify-content: space-between; align-items: flex-end; gap: 24px;
  padding: 18px 0;                      /* §6 row: was 28 0 / 24 0(≤920) */
}
.tb-masthead-aside { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }
@media (max-width: 480px) {
  .tb-masthead-hero { flex-direction: column; align-items: flex-start; gap: 10px; }
  .tb-masthead-aside { align-items: flex-start; }
}
```

```tsx
<div className="tb-masthead-hero">
  <h1 className="tb-wordmark-big">The Brief<span className="dot">.</span></h1>
  <div className="tb-masthead-aside">
    <div className="tb-readtime">READ TIME · {read_minutes} MIN · {sectionCount} SECTIONS</div>
    <a href="#subscribe" className="tb-band-link" onClick={/* MOVED from the old .tb-btn-cta:
        preventDefault + scrollIntoView(#subscribe, { behavior: reducedMotion ? "auto" : "smooth" })
        — Masthead.tsx:132-141 today */}>
      Subscribe →
    </a>
  </div>
</div>
```

- Wordmark: `clamp(40px, 5vw, 54px)`, weight 200, letter-spacing −0.04em, line-height 0.9. (Floor is 40px, not 38: below 760px the clamp pins to its floor, and the ≤920 runway is 36px — the §6 ceiling rule must hold at *every* viewport.)
- The section count relocates here — real per-issue content; `sectionCount` prop and ClientApp wiring **kept**.
- `.tb-band-link`: `font-size: 10.5px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--band-ink); border-bottom: 1px solid var(--band-accent); padding-bottom: 2px;`
- **Deletions in Masthead.tsx:** the `.tb-tag-row` block (:124-129, all four chips — count relocated above), the `.tb-masthead-actions` block (:130-142 — its scroll handler moves to the link above), the whole `.tb-masthead-foot` wrapper, the **second `<Hair />` at :121** (otherwise it stacks a duplicate rule against `.tb-band`'s border-bottom), and the tagline block (:104-108). The first `<Hair />` (:99, under the meta row) stays.
- **Dead CSS to delete with them** (landmine-30 discipline, full inventory): `.tb-masthead-foot` :260-264 **and its ≤920 override :966**, `.tb-tag-row` :265, `.tb-masthead-actions` :265, `.tb-tagline` :212-218, `.tb-btn-cta` + `:hover` :267-277 (nothing else renders it), and `.tag`/`.tag-soft`/`.tag-accent` :126-138 (only consumers were the tag chips; `.tag-accent` was already dead). Their print hide-list entries (`body.tb-print .tb-masthead-actions` :1037, `.tb-btn-cta` :1038 and in :1072-1073) go too.
- **Tagline:** deleted from the masthead; its first sentence **replaces** "Bangladesh business intelligence" in the footer line (ClientApp.tsx:316): `The Brief · Daily macro & markets read for Bangladesh banking professionals · Vol. N · Issue N`. The other two sentences are dropped. (Owner veto §11.2.)

### 5.4 StickyBar

```css
.tb-stickybar        { background: var(--band); border-bottom: 1px solid var(--band-rule); color: var(--band-ink); }
.tb-stickybar .meta  { color: var(--band-mute); }   /* (0,2,0) selector — must be explicit */
.tb-stickybar .pulse { background: var(--band-accent); }
.tb-stickybar .wordmark .dot { color: var(--band-accent); }
```

Plus §4.3's inset, §2's toggle echo (+`inert` when hidden), and the reveal retune note: the masthead is now ~half its old height and `#masthead` excludes band padding, so the `rootMargin: "-40px"` reveal (ClientApp.tsx:172-183) fires earlier, ink-to-ink — check on a 375px preview, retune if it flickers.

## 6 · Density & type scale — ratified 1c card numbers

Scale decision: v1 compressed one full step below the ratified 1c card with no recorded rationale, for a 14-minute read aimed at senior bankers. v2 restores the card's numbers. **The prototype's tighter values are superseded.**

Rows list desktop / ≤920px / print. "—" = no override exists at that tier and none is added (the ≤480 block redeclares nothing below). *(n)* = the ≤920/print cells are **new** rules, not edits.

| Selector | Now (desktop / ≤920 / print) | v2 (desktop / ≤920 / print) |
|---|---|---|
| `.tb-wordmark-big` | clamp(96,14vw,168) / 72 / 64 | **clamp(40px,5vw,54px) / delete the 72px override / 44** |
| `.tb-masthead-full` padding | 36 0 28 / — / 18 0 14 | **§4.3's longhand rule / same / 14 0 12** |
| `.tb-masthead-hero` padding | 28 0 / 24 0 / — | **18 0 / 14 0 / 10 0** *(n print)* |
| `.tb-section` padding | 64 0 56 / 44 0 36 / 28 0 · 24 0 | **28 0 24 / 24 0 20 / 24 0 (both print paths)** |
| `.tb-section-title` | 48 w200 own line / 32 / 32 | **28 w300 inline after §NN eyebrow / 24 / 24** |
| `.tb-section.is-unavailable .tb-section-title` | 22 w500 / 19 / — | **20 w500 / 18 / —** |
| `.tb-section.is-unavailable` padding | 28 0 28 / 20 0 20 / — | **16 0 16 / 14 0 14 / —** (a dead section must occupy less than a live one — 56px vs 52px was an inversion) |
| `.tb-group + .tb-group` | 64 / 44 / 24 | **26 / 22 / 20** |
| `.tb-longview + .tb-group` | 64 / — / — (no overrides exist today) | **26 / 22 *(n)* / 20 *(n)*** |
| `.tb-banker-runway .num` | 84 / 64 / — | **44 / 36 / —** (36, not 40: must stay under the wordmark's 40px floor on phones) |
| `.tb-banker-verdict` | 22 / — / — | **17 w300, line-height 1.55 / same / same** |
| `.tb-banker.is-hero .tb-banker-verdict` | 30 / — / — | **19** |
| `.tb-banker.is-hero::before` | 3px accent bar | **2px** |
| `.tb-banker` padding-top | 28 / — / — | **14** |
| `.tb-banker.is-hero` padding-top | 36 (more specific — wins over the row above) | **20** |
| `.tb-tldr` | 13.5 italic / — / — | **13 normal — KEPT as its own block** (pipeline-generated per-section paragraph; dropping it is a content decision this facelift does not take) |
| `.tb-todays-call .body` | 17 italic / — / — | **clamp(13px,1.6vw,15px) normal** |
| `.tb-cta-dark .head` | 56 / 38 / — | **30 w200 / 26 / —** |
| `.tb-readtime` | 11 / — / — | **10.5 (band-scoped, §5.2)** |

Supporting type (floors raised from v1/prototype's 8.5px):

- **Label floor: 9px.** KPI/snapshot tile labels 9px/500/0.14em `--ink-3`. Section `§NN` eyebrow 9.5px/500/0.16em `--ink-3` — **scoped as `.tb-section-head .eyebrow`**, not the shared `.eyebrow` class (also used by SnapshotStrip and Section elsewhere).
- KPI tile value 16px; snapshot value 18px; sub-lines 10.5–11px. News headline 12.5px w500; detail 11px; meta 9.5px/0.08em. Watch/risk headers 9.5px/600 `--ink-3`; items 11px/1.5 `--ink-2`. Group label 10px/500/0.16em `--ink-3`. Verdict line 13px w500 (the tone `Mark` already renders inside `.tb-section-verdict` — Section.tsx:136-138; no wiring needed, only the size respec). FIG label 9.5px/600/0.14em `--ink-3`.
- Body prose (`.tb-analysis .body`, Long View prose) stays ≥13px — compactness comes from spacing and chrome, not body-copy shrink.

**Ceiling rule (Design.md, PR D): nothing on the brief page renders larger than the wordmark, at any viewport.** Post-table check: wordmark floor 40 > runway ≤920 36; desktop 54 > 44 runway > 30 CTA > 28 titles. Holds.

**Section-head markup change (goes with the inline title):** `Section.tsx:93` and :127-128 currently render the eyebrow as a block `<div>` *above* the title — the head row becomes `<div className="tb-section-head"><div><span className="eyebrow">§NN · Group</span> <h2 className="tb-section-title">Title</h2></div><div className="tb-section-verdict">…</div></div>` with eyebrow and title inline-baseline. Small JSX change; spec'd here so no one opens the prototype for it.

## 7 · Section surfaces

### 7.1 KPI tile grid (replaces the rail layout; absorbs summary pills)

```css
.tb-kpi-rail {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 1px;
  background: var(--rule-faint);          /* grout */
  border: 1px solid var(--rule-faint);
}
.tb-kpi-row { background: var(--paper); padding: 10px 14px; display: flex; flex-direction: column; gap: 4px; }
.tb-kpi-value { font-size: 16px; }
.tb-kpi-label { font-size: 9px; letter-spacing: 0.14em; color: var(--ink-3); }

/* diff mode: dim the CONTENT, not the tile surface — a 0.34 tile composites
   its paper toward the grout and reads as a filled block (the same
   compounding problem globals.css:867-872 records). REPLACES the .tb-kpi-row
   arm of the existing rule at :851-856: */
body.tb-diff .tb-section .tb-kpi-row:not(.is-changed):not(.is-held-over) > * { opacity: 0.34; }
```

Implementation contract:

- **The cell class stays `.tb-kpi-row`** — `is-changed`/`is-held-over` and the diff selectors target it. Do not rename.
- **JSX reorder in `Section.tsx` (:254-279):** today one wrapper div holds label + sub + held-footer with the value as a *sibling* — under column-flex that renders label → sub → "As of…" → value. Reorder to label → value → sub → held-footer (held-footer at 11px spans the tile below the sub).
- Remove the `<Hair>` separators between rows (Section.tsx Fragment) — the grout gap replaces them.
- **Pills merge into the same grid as tiles** (`{key, value, tone}` — same rendering shape as a metric's label/value/tone; the editor prompt defines pills as "highlight KPIs", so this is a union of like surfaces). **De-dup rule (new v2 decision):** compare exact strings after `cleanMetricValue` (which only collapses repeated `$` — lib/format.tsx:99-102) plus `.trim()` and case-fold; drop any pill whose value matches a same-section metric value (22/29 fixture pills do). Surviving pills render as tiles after the metrics. No pill's *information* goes unshown — duplicates are already on screen as metrics; unique pills get tiles.
- **Headlines section** carries 0–1 metrics on real data (1 in issues 204/205, 0 in the 117 fixture): its pills join whatever metrics exist in the one tile grid; a pills-only grid is needed only when the metric count is zero.
- The pipeline keeps emitting `summary_pills` untouched (prompt edits out of scope, AGENTS.md:355).
- Delete `.tb-summary-pills` CSS (:540-571 and ≤920 :988-991) when the merge lands.
- Width check at preview: the rail is the `1fr` half of a `1.6fr 1fr` grid — ~151px tiles at 1280; long labels ("Overnight Call Money") wrap 2–3 lines at 9px. Verify legibility at 1280; bump `minmax` to 150px if it reads cramped.

### 7.2 Snapshot strip — fallback + plumbing (prerequisite for §7.5)

**Corrected premise:** no payload emits a `snapshot` *section at all* (slugs in 117/204/205: headlines, bb, banking, fx, dse, tbond, fiscal, macro, iran, remit[, comm]) — so `SnapshotStrip` bails at its `if (!section) return null` guard (SnapshotStrip.tsx:11) before the `is_snapshot` filter is ever reached, and `id="snapshot"` **never renders on real data** (ClientApp's scroll-spy already `.concat(["snapshot"])`s a target that does not exist — :151, :60-63). The strip is empty today; "the snapshot strip carries the numbers" was false.

Plumbing (this is a component change, not a pure CSS one):

- `SnapshotStrip` prop becomes `sections: Section[]` (ClientApp passes the full array).
- Logic: if a `snapshot`-slug section exists with `is_snapshot` metrics, use it (current behavior). Otherwise **derive** the cells by case-insensitive substring label lookup, using the measured real labels: `USD/BDT mid` (fx) · `DSEX` (dse) · `91d T-Bill cut-off` (tbond) · `Brent` (iran) · `Gold` (fx on real issues; comm fallback) · `Monthly Remittance` (remit). Skip missing ones; render nothing only if all six miss.
- Fallback header: static eyebrow `Market snapshot`, no verdict line (those fields read off the snapshot section, which doesn't exist in fallback mode).
- `id="snapshot"` stays on the root — with the fallback it now actually renders, making the existing scroll-spy entry meaningful for the first time.

```css
.tb-snapshot-row {
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1px; background: var(--rule-faint); border: 1px solid var(--rule-faint);
  padding-top: 0;
}
.tb-snapshot-cell { background: var(--paper); padding: 10px 14px; border-right: none; }
```

Delete the desktop divider rules (:332-337) **and all four ≤920 snapshot lines (:970-973** — :970 is the grid rule, :971-973 the cell block whose `:nth-child(odd)` borders only made sense in a fixed 2-col grid**)**. Cell: label 9px `--ink-3`, value 18px with the existing **56×18** sparkline (v1's 44×13 respec dropped — the component ships 56×18), sub 10.5px tone-colored when directional. (Owner veto §11.4.)

### 7.3 News rail

- Base `.tb-news-rail`: `repeat(auto-fit, minmax(220px, 1fr))`; replace the ≤920 override (:985) with `.tb-news-rail { gap: 20px; }` — deleting the whole line would also revert phones to the desktop 28/36px gap.
- **`.tb-news-rail.is-headlines` keeps its 4-column contract and both responsive overrides** (:650-654, :986, :1022). Decision recorded.

### 7.4 Masthead deletions — see §5.3 (tag row, foot, second Hair, tagline; full dead-CSS inventory there).

### 7.5 Cover retirement

Corrected premise: recent issues do **not** reliably ship `cover_metric: null` — issue 205 carries one; the pipeline strips it only when every hero metric is unchanged, and four tests assert preservation. Retiring Cover is an **editorial decision** (§11.3), on these terms:

- SPA-only: `Cover.tsx` and its CSS go; `cover_metric` stays in pipeline, schema, `BRIEF_SELECT`, tests. PR body states a v2.1.0-era surface is retired deliberately.
- The number still appears on cover days — every metric renders in its section, and §7.2's fallback keeps a numbers strip at the top (⚠ §7.2 must land in the same PR or earlier). What is lost is the oversized "Today's Number" treatment — the scale competition 1c removes.
- **Skip link:** retargets `#content` (§5.1). No id relocation — the first draft's "move `id=cover` onto the strip" was impossible (the strip root already carries `id="snapshot"`).
- **Full dead-CSS inventory (landmine 30):** base `.tb-cover` block :447-461 (incl. `:empty`, `.lede`, `.bignum`, `.dot`), `.tb-cover-asof` :810-821, `.tb-cover-line.is-changed` :832-843 — note :832-833 and :853 are **shared selector lists**: remove only the `.tb-cover-line` arms, keep the `.tb-news-item`/`.tb-kpi-row` arms — ≤920 rows :977-978, print rows :1055-1056 and :1076. (`.tb-cover-line` has no .tsx producer today; it goes fully dead.)

### 7.6 Long View compact pass (was entirely missing from v1)

| Selector | Now | v2 |
|---|---|---|
| `.tb-longview` padding | 56px 0 48px | 32px 0 28px |
| `.tb-longview-title` | clamp(24,2.8vw,36) | clamp(20px,2.4vw,26px) |
| `.tb-longview-stat-num` | clamp(40,5vw,64) | **clamp(30px,3.5vw,44px)** (= runway scale, under the wordmark ceiling) |
| `.tb-longview-lead` | 14px italic | 13.5px normal |
| 0.22em tracked-caps set → 0.16em, 10px: | `.tb-longview-eyebrow` :1127, `.tb-longview-bullets-eyebrow` :1297, `.tb-longview-bar-eyebrow` :1345, `.tb-longview-takeaway-label` :1427 | all four → 10px/600/0.16em (matching the §6 label tier) |

Everything else keeps current sizes — body/prose blocks are ≥12px; the small labels (`.tb-longview-cmp-lab` 9.5px, `.tb-longview-cmp-row-title` 10px, `.tb-longview-bar-ref-text` 9.5px, `.tb-longview-bar-unit` 10.5px, `.tb-longview-stat-label` 11px/0.2em) already sit at or above the 9px floor and stay. Diff-stale untouched.

### 7.7 Section head + SecNav

- Head row per §6 (eyebrow inline with 28px title — markup change spec'd there); verdict 13px w500 with its existing tone `Mark`; warn/bear verdicts may tint the line.
- SecNav: **new** — the lead section's item (weight ≥ 2) gets `is-lead` → `color: var(--accent)`, mirroring the hero flag; small wiring in ClientApp (weights already computed) + SecNav prop. `.tb-secnav-item .num` → `--ink-3` (§1).

### 7.8 Subscribe CTA panel

`.tb-cta-dark` reverses out via `background: var(--ink)` — in dark that inverts to a near-white panel and its three hardcoded cream rgbas collapse to 1.07–1.10:1. Pin the panel to the band, where band tokens hold in both themes:

```css
.tb-cta-dark {
  background: var(--band);
  color: var(--band-ink);
}
.tb-cta-dark .eyebrow { color: var(--band-mute); }        /* was rgba(244,239,230,0.55) */
.tb-cta-dark .body    { color: var(--band-ink-2); }       /* was rgba(244,239,230,0.78) — two tiers preserved */
.tb-cta-dark .head .accent { color: var(--band-accent); }
```

Replace the two inline styles in `SubscribeCTA.tsx` — `:89` → `var(--band-mute)`, divider `:95` → `var(--band-rule)` (the only two hardcoded colors in app/**/*.tsx). Form panel unchanged except §8's submit hover. The three `08:00 BDT` statements (SubscribeCTA.tsx:80/101/116) must survive the restyle — v2 decision (the publish-time coupling itself, AGENTS.md #32, is untouched by this work).

## 8 · Crimson budget — restated honestly

v1 claimed "exactly 4 jobs" then assigned six. The real budget is **five jobs**:

1. **Live pulse + chart latest-point dot and caption** — `.tb-chart-latest` keeps accent (decision: it pairs with the accent dot); `.tb-chart-fig` → `var(--ink-3)`.
2. **Today's Call label** (`--band-accent` on the band).
3. **Bear tone** — LEAD/TODAY'S LEAD flags, bear deltas, bear verdict tints.
4. **Active nav** — `.tb-secnav-item.active` + the new `is-lead` item.
5. **Underlines** — `.tb-band-link` border, input focus underline, and the button-hover label underline below.

Removed from accent: `.tb-chart-fig` (→ ink-3), `.tb-btn-submit:hover` (→ stays `var(--ink)` fill; the label gains an accent underline — job 5), `.tb-banker-verdict em` (→ `var(--ink)`, weight 500, no italic). (`.tb-btn-cta` is deleted outright, §5.3.) `::selection` keeps accent.

AA note recorded here (see §1's light-accent note): the small accent-text jobs measure 4.44:1 in light — pre-existing, exempted in PR D, optional lift in §11.11.

## 9 · Print contract (both `?print=1` and native print)

Print was repaired in v2.1.0 and is the most fragile surface here. All in PR C:

**9.1 Force light tokens — at three levels, all needed:**

*(a)* Redeclare the full light steel-crimson set **on `body`** in both print paths — a property declared on `body` beats the value inherited from `html`'s dark block for every body descendant (verified empirically; this is also why the tokens must NOT be forced via bare `:root`/`html` selectors, which lose to the (0,2,0) dark block). **The two alias tokens must be redeclared too** — they substitute where *declared*, so a body-level `--ink-3` never reaches `--color-muted` defined on `:root` (browser-verified: without this, held-over text and the lens pill print with dark values):

```css
body.tb-print {
  --paper: #E6E9EB; --paper-2: #D9DDE0; --paper-3: #C8CDD0;
  --ink: #0B0F12; --ink-2: #1F2428; --ink-3: #4F5559; --ink-4: #7A8084;
  --rule: #0B0F12; --rule-soft: rgba(11,15,18,0.20); --rule-faint: rgba(11,15,18,0.09);
  --accent: oklch(0.55 0.21 25); --accent-soft: oklch(0.55 0.21 25 / 0.16);
  --bull: oklch(0.45 0.10 150); --bear: oklch(0.55 0.21 25); --warn: oklch(0.62 0.14 75);
  --neu: var(--ink-3);
  --color-muted: var(--ink-3); --color-surface-2: var(--paper-2);
  background: white;
}
@media print { body { /* identical token block */ background: white; color: black; } }
```

*(b)* `html`-level force, placed **after** the dark block in source order so the (0,2,0) tie breaks toward print — this fixes `html`'s own `background: var(--paper)` (dark gutters behind `?print=1`) and any `getComputedStyle(documentElement)` token read:

```css
:root.tb-print-root { /* same token block */ background: white; }
@media print { :root[data-theme="dark"] { /* same token block */ background: white; } }
```

ClientApp's printMode effect (which toggles `body.tb-print` at :92) also toggles `tb-print-root` on `document.documentElement`.

*(c)* **Charts:** canvases ignore CSS overrides — they must be rebuilt with light tokens. The printMode effect additionally forces `document.documentElement.dataset.theme = "light"` while print mode is on (saving and restoring the prior value on exit); §3's `useTheme` then rebuilds every chart. For native print, a `beforeprint`/`afterprint` listener does the same — best-effort: the async rebuild may or may not beat the print snapshot, so a dark-theme user's native Cmd+P can still capture dark chart inks (**1.29:1 on white — invisible**; this is why the mechanism exists — the first draft wrongly called dark-on-white chart lines "readable"). `?print=1` is fully correct; native-print-from-dark is best-effort and the `?print=1` route is the documented path. (Owner veto §11.12.)

**9.2 Band prints as paper** (mirror of the `.tb-section.is-hero` reset at :1050; without it, print-background suppression leaves `--band-ink` near-white text on white — an invisible nameplate). Both paths (`body.tb-print .tb-band …` and the same selectors under `@media print`):

```css
.tb-band { background: white; border-bottom: 1px solid var(--rule); color: var(--ink); }
.tb-band .hair { background: var(--rule-soft); }
.tb-band .tb-masthead-meta, .tb-band .tb-published, .tb-band .tb-readtime,
.tb-band .tb-todays-call .byline, .tb-band .tb-masthead-lens-pill { color: var(--ink-3); }
.tb-band .tb-masthead-lens-pill .tb-mlp-day { color: var(--ink); }   /* (0,3,0) — outranks the reset above; must be explicit */
.tb-band .tb-todays-call { border-top-color: var(--rule-soft); }
.tb-band .tb-todays-call .body { color: var(--ink); }
.tb-band .tb-todays-call .label { color: var(--accent); }
.tb-band .tb-wordmark-big .dot { color: var(--accent); }
```

**9.3 Hide lists.** Add `.tb-theme-toggle` and `.tb-band-link` to **both** lists by their own class (`body.tb-print …` :1032-1041 and `@media print` :1072-1074 — the :1026-1031 comment records why hiding an ancestor is not enough). Remove the now-dead `.tb-masthead-actions` / `.tb-btn-cta` entries (§5.3).

**9.4 Scale + stale rules.** `body.tb-print .tb-section-title` 32 → **24**; `.tb-wordmark-big` 64 → **44**; `.tb-masthead-full` 18 0 14 → **14 0 12**; `.tb-group + .tb-group` 24 → **20**; both paths' `.tb-section` padding → **24px 0**; delete the `.tb-cover` print rows (§7.5). `page-break-inside` rules unchanged.

## 10 · Governance

### 10.1 Four PRs

1. **PR A — tokens + dark mode + toggle + chart re-theme** (§1, §2, §3). Default stays light. Note: the toggle itself is a **visible new control** in the masthead and StickyBar — user-visible change, sign-off applies (VISION.md:21); "self-contained" ≠ invisible.
2. **PR B — PWA** (§4).
3. **PR C — 1c facelift** (§5–§9) + version bump: `package.json` 2.2.0 → **2.3.0**, README badge (inside the badge image URL), CHANGELOG entry (`[Unreleased]` already holds the 2026-08-24 DSEX/CPI fixes — they ship under this version; don't rewrite them).
4. **PR D — Design.md amendment** (§10.3) with its own "as of v2.3.0" line. Merge immediately after C, same session; no Long View pin between C and D (landmine 8's half-old/half-new window). Then annotated tag `v2.3.0` + GH release `--latest` — tag push is a sign-off step (AGENTS.md:350).

**Preview gate on every PR (definition of done):** Vercel preview URL to the owner + screenshots at **375 / 768 / 834 / 1024 / 1280** in both themes; PR C adds `?print=1` + native Cmd+P PDF in both themes; PR B adds an iPhone standalone-install check. Fixtures: `public/fixtures/today-live-2026-05-27.json` (issue 117 — the bundled fixture, already in place) **and** issue 205 — copy `tests/fixtures/real_issues/issue_205.json` into `public/fixtures/` first (`/preview` reads only `public/fixtures/`, app/preview/page.tsx:45; note the copy becomes publicly served). Issue 205 is the fixture that exercises the §7.2 fallback, §7.5 (live cover_metric), and 8-of-9 chart configs (the 117 fixture mounts only 4).

**Test strategy (explicit decision):** no new dev dependencies — the vitest suite is node-env pure-logic and cannot see any of this; the preview gate is the verification. Automated UI coverage = a separate pre-approved dependency PR (VISION.md:28). "Tests pass" is **not** proof-of-done for this work.

### 10.2 Landmines + repo rules that intersect

**#2** (chart changes need a preview smoke-load — §3 touches BriefChart: smoke-load charts, with issue 205 per §10.1) · **#4** (nothing near .venv/vercel.json) · **#8** (Design.md in its own PR = D) · **#11/#12** (version+tag+release same day; bump package.json + README badge + CHANGELOG together) · **#17** (chart re-point publish gap — does NOT apply: no metric_id changes) · **#19** (Context7 for Next 16 APIs) · **#21** (brief.service self-pulls — irrelevant: this is a Vercel-only surface; nothing to do on Hetzner) · **#30** (retiring something means finding every entry — the dead-CSS inventories in §5.3/§7.5/§7.1/§7.2 are that discipline) · **#31** (by analogy from builders to CSS: no dormant selectors — hence the full inventories) · **#32** (publish-time coupling — untouched; the 08:00 BDT copy rule in §7.8 is a v2 decision, not this landmine). Email rule: **notifier.py and the bone email identity untouched — no dark email, ever** (Design.md:157-177, VISION.md:26; not a numbered landmine). Design.md:211's no-raw-hex rule: manifest/viewport carve-out in §10.3.

### 10.3 Design.md amendment checklist (PR D)

1. Band tokens + dark token table (full set incl. bull/bear/warn — tone table gains light/dark columns).
2. Revised type scale: rows for wordmark, section title, KPI/snapshot values, runway, Today's Call; the **wordmark ceiling rule (any viewport)**; label floor 9px + ink-3 rule; delete "Stat value 48–72px".
3. Section structure list: title inline with eyebrow; pills absorbed into the KPI tile grid (correct the stale "categorical signals" line — the shipped editor prompt defines pills as highlight KPIs).
4. Crimson budget = the five jobs of §8.
5. Theme axis: light/dark orthogonal to palette; **dark is steel-crimson only; bone = email = light forever**; dark band ≈ paper accepted ("all band").
6. Letter-spacing: eyebrows 0.14–0.18em (was 0.22em).
7. New PWA section: safe-area inset ownership; standalone online-only status; SW follow-up.
8. Raw-hex carve-out: `manifest.ts` + `viewport.themeColor` may carry `#0B0F12` literals; everywhere else the no-hex rule stands.
9. AA exemptions recorded: the six de-emphasis opacities (§1 list) + light-accent small text at 4.44:1 (§1 note).
10. Versioning line updated (currently "as of v1.3.1") + responsive principle: "no new breakpoints; auto-fit/minmax + clamp; **stretched orphan cells at intermediate widths are accepted** (e.g. 6 snapshot cells → 4+2 at 768/834) — revisit with per-grid caps only if the 834 screenshots read badly."

## 11 · Owner-veto register (decisions this file takes; say the word to flip any)

1. **Density = the ratified 1c card** (28/17/44/54), not v1/prototype's tighter scale.
2. **Tagline replaces "Bangladesh business intelligence" in the footer line** (first sentence only).
3. **Cover retires** (SPA-only) with the §7.2 snapshot fallback + `#content` skip link; pipeline field stays.
4. **Snapshot strip derives six canonical cells** when no snapshot section exists (i.e., on every real issue today).
5. **`.tb-chart-latest` keeps accent**; budget restated as five jobs.
6. **Browser `theme-color` stays `#0B0F12` in both themes.**
7. **PWA ships online-only**; optional `lastBrief` read wire-up is a separate sign-off.
8. **Dark palette vs v1:** rule `#AEB5B9`, rule-faint 0.16, ink-4 `#848B90`, accent/bear `oklch(0.66 0.19 25)`, band-rule 0.40.
9. **Remittance+Commodities pairing cut.**
10. **tldr kept** as its own 13px block.
11. **Light accent stays `oklch(0.55 0.21 25)`** (4.44:1 small-text exemption recorded) — optional lift to ~0.52 L if you want strict AA.
12. **Native print from dark theme is best-effort for chart inks** (`?print=1` is the guaranteed path); a hard guarantee would need a sync pre-print chart rebuild — follow-up if it matters.

## 12 · Amendment 2026-08-28 — light mode is completely paper (v2.4.0)

**Owner decision (Adnan, 2026-08-28, explicit):** light mode carries NO dark surfaces. The ink band becomes dark-mode-only; in light, the masthead band, the sticky bar, and the Subscribe panel all render as paper — one uninterrupted sheet, the mirror of dark's accepted "reads as all band". Trigger: on iPhone, light mode rendered the band + Today's Call as a dark slab under light-grey browser chrome, and `black-translucent` was independently already broken on `/archive` (no band on that route → invisible white status-bar glyphs over paper).

**Mechanism — per-theme band tokens, not new selector families.** The six `--band-*` tokens stay defined on `:root` with their ink values (dark inherits unchanged); a light block keyed `[data-palette="steel-crimson"]:not([data-theme="dark"])` re-points them at the light palette: `--band→var(--paper)`, `--band-ink→var(--ink)`, `--band-ink-2→var(--ink-2)`, `--band-mute→var(--ink-3)`, `--band-rule→var(--rule-soft)`, `--band-accent→var(--accent)`. Every §5.2 descendant override, the sticky bar, `.tb-band-link`, and `.tb-cta-dark` resolve correctly with zero selector churn. `:not([data-theme="dark"])` (not `[data-theme="light"]`) so the no-JS frame gets the paper band; keyed to steel-crimson so bone (the email identity, light forever) is untouched. Two explicit light extras: the band's and sticky bar's `border-bottom` promote to full `--rule` (the seam is now the only edge — §9.2 print made the same call), and `.tb-theme-toggle.on-band` takes `--ink-3` text/border (the `--rule-soft` mapping is 1.55:1, under the 3:1 control floor — the §2 trap). Measured on `--paper`: band-ink 15.78:1, band-mute 6.20:1, band-accent 4.44:1 (the §11.11 small-text exemption carries over).

**Chrome + PWA consequences.**
- `viewport.themeColor` becomes a `prefers-color-scheme` media pair (`#E6E9EB` light / `#0B0F12` dark) — **this overturns veto §11.6**. Media pairs track the OS, not our toggle, and Next RE-CREATES the viewport meta nodes on every client navigation (the Viewport head element is keyed per request — review-verified in next/dist/server/app-render), so a one-shot mutation cannot survive a route change. Two mechanisms therefore keep the chrome honest on EVERY route including /archive: the FOUC script stamps both metas with the resolved theme pre-paint on hard loads (with a DOMContentLoaded fallback if the metas parse later than the script), and a root-mounted `ThemeColorSync` client component re-stamps on theme changes (via `useTheme`'s data-theme MutationObserver — covers toggle, OS listener, print force/restore) plus pathname changes, with a head MutationObserver catching Next's node swaps.
- `appleWebApp.statusBarStyle` reverts to `"default"` (PR B's original value). iOS has no per-theme API for this static meta; `black-translucent` + a paper top = invisible white glyphs (the PR B bug, already live on `/archive`). Accepted residual: in dark standalone the system bar follows the OS appearance, mismatching only when the in-app toggle diverges from the OS.
- `manifest.ts` `background_color`/`theme_color` stay ink `#0B0F12`: manifest splash is Chromium/Android-only behavior (iOS ignores it — the PWA's primary target), and the launch frame staying the brand mark on Android is deliberate. Flip on owner request only.
- Icons, hero.svg artwork, and the social card (`/icon.png` via `openGraph`/`twitter` images) keep the ink-ground "B." as the brand mark — normal for light apps to carry dark icons; the hero comment no longer claims "both themes".

**Superseded clauses in THIS file** (wording above stands as history; this section wins on conflict): §1's "cross-palette constants … ink in BOTH themes" token framing; §2:172's fixed theme-color decision; §4.1's manifest rationale (values unchanged, rationale now Android-splash + brand); §4.2's viewport/appleWebApp code blocks; §4.3:285's "sticky bar sits under the iOS clock with black-translucent" note; §5 intro + §5.1's "ink in BOTH themes" contract (the :325 dark band≈paper acceptance SURVIVES); §5.2's commentary (rules unchanged, now per-theme); §5.3's band-link color rationale; §5.4's "ink-to-ink reveal" note (paper-to-paper in light); §7.8/§8's "band tokens hold in both themes" pinning rationale (the panel now follows the theme; the light panel/form seam uses the same band-rule edge as dark); §9.2's preamble (narrows to "load-bearing when printing from dark" — but NOT redundant from light: §9.2 still whitens the band ground, `--paper` #E6E9EB → true white, and darkens Today's Call body, `--ink-2` → `--ink`, so the print rules must never be scoped dark-only; print blocks byte-identical); §10.3 item 8's carve-out (now the media pair + the ClientApp hexes); veto §11.6 (overturned, this section is the record); §11.8's band-rule 0.40 note (dark-only now).

**Verification matrix for this amendment:** light + dark at 375/768/1280 on `/` (fixture + live), `/issue/[no]`, `/preview`, and `/archive`; toggle both directions incl. sticky-bar state; `?print=1` from both themes; chart repaint on flip (charts verified clean — `buildPalette` samples no band token). Design.md records the contract change in its own PR (landmine 8), version v2.4.0-class.
