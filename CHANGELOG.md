# Changelog

All notable changes to The Brief are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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

---

## [1.0.1] — 2026-05-15 · Same-day patch

### Fixed

- **Every "In this issue" rail item is now clickable** (#71). The keyword→section map shipped in v1.0.0 only matched 7 narrow patterns and had two bugs (`imf → bb` should have been `→ macro`; `remittance → "remit"` slug never existed). Most banking-domain headlines (BB policy, tax, NBR, FDI, budget) had nothing to match, so 8-of-12 rail items in Issue 108 were inert. Expanded the map to seven well-scoped patterns covering bb / banking / tbond / fx / dse / iran / macro with word-boundary anchors on every single-letter token, and added a fallback to the always-present `headlines` section for items that still don't match a specific topic. **Every row in the rail is now clickable.**

### Changed

- **`brief/notifier.py` style + correctness cleanup** (carryover from v1.0.0 reviews):
  - All stdlib imports hoisted to the top of the file (was: 7 mid-file imports accumulated task-by-task during TDD).
  - `_json_loads` helper defined before its first caller (was: defined after `fetch_subscribers`, worked via late binding but read strangely).
  - `BriefRow.published_at` widened to `datetime | None` and the `# type: ignore[arg-type]` comment removed (was: declared non-nullable but `_parse_iso` could return `None`).
  - `send_via_brevo` response decode now uses `_json_loads(r.read())` for consistency (was: inline `_stdjson.loads(r.read().decode("utf-8"))`).
  - `_LENS_PHRASE` annotated as `dict[str, str]`.
  - `_lens_phrase` got a one-line docstring; `_json_loads`, `_parse_iso`, `_supabase_config` similarly.
  - Double space in `render_text` dateline tightened to single space.
  - Module re-organized into labeled sections: Constants / Logger / Dataclasses / Private helpers / Render layer / Fetch layer / Send layer / Orchestration. Function bodies unchanged.

- **Defensive `urlencode` on `brief_id` and `section_id`** in `fetch_brief_data` PostgREST queries (low risk today — both are Supabase-generated UUIDs — but cheap insurance against future callers passing tainted strings).

- **`FROM_EMAIL` silent fallback now logs a warning** (`brief/notifier.py`). When the env var is unset and the notifier falls back to `noreply@example.com`, a warning is logged calling out the operational risk (Brevo will reject sends from an unverified sender). Was previously invisible.

- **`brief/cli.py` docstring** now notes that notifier failures don't change exit code 0 — the Supabase brief is the canonical artifact, the email is a best-effort amplifier. Helps operators debugging a missing send.

- **Package version 1.0.0 → 1.0.1** in `package.json`.

### Pull requests

- #71 — `fix(spa): make every 'In this issue' item clickable`
- (this PR, after merge) — `chore(notifier): cleanup carryover from v1.0.0 reviews + bump to 1.0.1`

### Hetzner deploy

`git pull --ff-only` on `~/the-brief`. No env, no migration, no systemd restart. Next `brief.service` fire (Sun 2026-05-17 06:30 BDT) picks up the cleaner notifier. The rail fix is SPA-only (Vercel auto-deploy).

---

## [1.0.0] — 2026-05-15 · "Banking professionals release"

The first production release. The brief now publishes itself, validates itself, distributes itself by email, and reads honestly across the full banking professional audience — not just treasury desks.

### Added

- **Release email notifier** (`brief/notifier.py` · #64) — HTML + plain-text digest sent to every row in `subscribers` after a successful publish. One Brevo POST per issue, multi-recipient `to:` list. Fail-open: notifier errors never crash the publish. 35 unit tests cover render, fetch, send, and orchestration paths against `urlopen`-mocked Supabase and Brevo. End-to-end validated 2026-05-15 against Issue 107 (`messageId 202605151212.44321990402@smtp-relay.mailin.fr`, 5 subscribers).
- **`--no-notify` CLI flag** on `brief.cli run --publish` — opt out of the email send for manual / test runs.
- **iOS PWA home-screen title** "The Brief" (#65) — via `appleWebApp.title` in Next.js metadata. Previously truncated to "TheBrief—Bangl…" because iOS fell back to the full `<title>`.
- **Clickable "In this issue" rail** (#69) — every headline in the masthead's right rail now jumps to its matching section on click. Same `scrollIntoView` pattern as the existing Subscribe CTA. Hover + focus-visible affordances.
- **Project memory: editor_v6 transient retry pattern** — captures the operational lesson from 2026-05-15 that some `editor_v6` failures are transient Anthropic-side issues; manual retry is the right first move before debugging deeper.

### Changed

- **Audience widened: treasury desks → banking professionals** (#66 · #67).
  - Editor prompts (`editor_v6.txt`, `editor_v6_friday.txt`) now name the reader as "a business head (corporate/SME/retail) and/or a risk head and/or a treasury head at a Tier-1 bank of Bangladesh."
  - Public masthead tagline and `<meta description>` updated to match.
  - Voice (terse, declarative, em-dashes, banker-to-banker) is unchanged.
- **Read-time target ~9 / ~10 min → ~15 min** (#67 · #68).
  - Mon–Thu prompt's "They have ~9 minutes" and Friday's "~10 minutes" both raised to "~15 minutes."
  - `read_minutes` JSON range tightened to `<int 13..17>` from `<int 7..12>` (Mon–Thu) and `<int 8..12>` (Friday).
  - UI fallbacks (`Masthead`, `ClientApp`, `staticFallback`) bumped `?? 9` → `?? 15` so the cold-start display reflects the new target.
  - Wider target carries more analytical depth — more `banker_read` paragraphs, more `analysis` blocks, more "why this matters" prose.
- **`brief.service` `TimeoutStartSec` documented as 90 min in repo** (#63) — the deployed unit on Hetzner has been running with `TimeoutStartUSec=1h 30min` for some time; the repo template still claimed 20 min. Truth-up so a re-deploy from the repo doesn't accidentally kill `editor_v6` mid-retry. The 90-min cap exactly matches `_call_with_retries`'s budget (3 attempts × 1800s + delays).
- **Package version bumped 0.1.0 → 1.0.0** in `package.json`.

### Fixed

- **React `#418` hydration mismatch on every page load** (#63). `formatNewsMeta` called `toLocaleDateString` with no `timeZone` argument, so SSR (Node, UTC) and CSR (browser, BDT/UTC+6) rendered different day numbers for any `published_at` near midnight UTC = 06:00 BDT — and 06:30 BDT is the brief's publish window. Pinning `timeZone: "Asia/Dhaka"` eliminates the mismatch on both sides. Persistent 1-error-per-load is now 0.

### Security

- **XSS hardening in the email HTML renderer** (#64). `_esc` (HTML-escape with `quote=True`) is applied to every editor-derived string. `source_url` href is dropped if the scheme is not `http://` or `https://` — blocks `javascript:`, `data:`, `vbscript:` and other scheme-based XSS vectors. Two regression tests cover both cases.

### Deferred

- Notifier style debt — mid-file imports, `BriefRow.published_at` type annotation, `urlencode(brief_id)`, `FROM_EMAIL` silent fallback policy. ~30 lines, no behavioural change. Will land as a follow-up patch.
- One-click unsubscribe — current behaviour: reply with "Unsubscribe" in the subject. Automated opt-out flow is a separate spec.

### Hetzner deploy notes

- `git pull --ff-only` on `~/the-brief` is enough — no systemd restart, no migration.
- Required env in `/etc/brief.env`: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (or `SUPABASE_SERVICE_KEY`), `BREVO_API_KEY`, `FROM_EMAIL`, `ANTHROPIC_API_KEY`, `ECONDELTA_DATA`.
- First live canary at v1.0.0: Sun 2026-05-17 06:30 BDT → Issue 109 with the broader audience + ~15-min target + email-to-all-subscribers.

---

## Pre-1.0 history

The Brief has been writing and publishing daily since April 2026 across several internal architecture milestones:

- **V1** (2026-04-20s) — original assembler, HTML render to GitHub Pages.
- **V4** (2026-04-24) — pipeline rewrite, email digest as plain-text, V4 templates.
- **V5** (2026-04-25 → 2026-05-04) — cream-paper HTML newspaper render, deploy-to-Hetzner, shadow soak, cutover.
- **V6** (2026-05-04) — replaced static HTML render with Next.js SPA reading from Supabase. Editor + subeditor LLM split. The V5 notification stack (`brief/notify.py`, `brief/report.py`, `brief/email_send.py`) was deleted as part of the cutover with the explicit intent that a future V6 notifier would be written fresh.
- **V6 polish** (2026-05-04 → 2026-05-14) — chart fixes (PRs #58–#62), `metric_history` repointing, chart card heads matching EconDelta `/macro`.
- **v1.0.0** (2026-05-15) — this release. Resurrects the notifier (V6-native, fresh, 150 lines, 35 tests), broadens audience, raises the read-time target, polishes the iOS PWA + masthead navigation, fixes the long-standing React #418 hydration warning.

For commit-level history before v1.0.0, see `git log --until 2026-05-15` on `main`.

[1.0.0]: https://github.com/clauding-lab/the-brief/releases/tag/v1.0.0
