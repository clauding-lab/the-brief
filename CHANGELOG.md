# Changelog

All notable changes to The Brief are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.6.1] — 2026-08-02

### Fixed
- **The editor's brief is no longer thrown away when it outgrows one response.** When the payload crosses the model's per-response output cap, the editor is cut off mid-JSON and continues in a NEW assistant message. `--output-format json` reports only the FINAL message in `result`, so the pipeline received the *tail* of the brief; `_extract_json_object` then salvaged the first balanced object out of that tail — a lone section — and Pydantic rejected it with 18 `extra_forbidden` errors. `run_max` now reads `--output-format stream-json --verbose` and stitches every assistant text block in arrival order, reconstructing the payload byte-for-byte. Five publishes died this way: #181 (three runs, 2026-07-31) and #183 (two runs, 2026-08-02).
- **The cut-off alarm now actually fires.** The v1.6.0 alarm was gated on `parsed is None and num_turns > 1`. Both halves were wrong: the preamble fallback rescues a fragment so `parsed` is not None, and a cut-off-and-continued response is still ONE turn so `num_turns` stays 1. It stayed silent through two further production failures. Detection now keys on `MaxCallResult.assistant_messages` and fires whether or not the stitched payload parsed.

### Changed
- **`DEFAULT_MAX_OUTPUT_TOKENS` documented as a no-op against the current model.** 64,000 is the hard per-response cap on `claude-opus-4-8` — requesting 128,000 returns 64,000 — so v1.6.0's pin set the value to what it already was and bought no headroom. The constant stays (it is still what the CLI is told, and becomes meaningful again if a future model raises the cap) but is no longer presented as the fix.
- `MaxCallResult` gains `assistant_messages`; `num_turns` is still surfaced but is no longer load-bearing.

### Tests
- 19 new tests in `tests/claude/test_max_client_stream_stitching.py`: multi-message stitching (including the exact #183 tail-fragment signature), duplicate-event de-duplication, `thinking`-block exclusion, non-JSON noise tolerance, usage/cost from the result event, alarm-fires-when-parsed and alarm-fires-at-num_turns-1, and backward compatibility with the single-object `json` payload shape.
- Verified against the real CLI with a forced-truncation probe (`CLAUDE_CODE_MAX_OUTPUT_TOKENS=1200`): 3 assistant messages, stitched output parsed clean.
- Full suite green: 663 passed.

### Followup
- New `AGENTS.md` landmine #26 and an `AGENT_LEARNINGS.md` entry for 2026-08-02.

---

## [1.6.0] — 2026-06-12

### Added
- **Long View: side-by-side stat + chart pairing.** When a `bar-chart` block directly follows a `stat` block, the Long View now renders them as a single paired card — the stat on the left (~60%), the compact bar-chart on the right (~40%) — instead of two stacked full-width blocks. The chart's SVG auto-scales into the narrower column, reading as a glanceable companion to the headline number; below 700px the pair stacks vertically. No schema change: pairing is driven purely by block order in `content/long-view.ts` (a `bar-chart` after a `stat`), keeping layout out of the pin data per the Long View contract. New `.tb-longview-pair` style in `app/globals.css`; grouping pass in `app/components/LongView.tsx`.

---

## [1.5.1] — 2026-05-29

### Fixed
- **v1.4.0 publish regression unblocked.** The v1.4.0 banker-grade editor prompt occasionally emitted `MetricV6.value` as a raw number (e.g., `35.1112`) and `MetricV6.delta` as a structured `{value, direction, window}` dict where the schema previously required pre-formatted strings. Every publish since v1.4.0 (Thursday #118 and Friday #119) failed Pydantic validation before reaching Supabase. `MetricV6` now ships two `field_validator(mode="before")` coercers that stringify numerics (preserving precision via `:.10g`) and render the delta dict as banker-style `"+0.99% WoW"` / `"−0.99% WoW"`. Pre-formatted strings still pass through unchanged.
- **Adjacent test fix:** `tests/test_cli.py::test_write_fixture_creates_valid_json_on_dry_run` had a stale mock signature missing the `preview_notify_enabled` kwarg added in v1.5.0 (PR #98). Now accepts the flag.

### Schema migration shipped separately (also part of the v1.4.0 unblock)
- **`migrations/0004_section_chart_read.sql`** (PR #99, merged earlier today) — added the `chart_read` jsonb column to the production `sections` table. v1.4.0 shipped the Pydantic + SPA render for `Section.chart_read` but skipped writing the matching SQL migration, so the first publish under v1.4.0 (Thursday) blew up with `PGRST204: column not found` and Brief #118 ended up orphaned in production (status=published, 0 sections / 0 metrics / 0 news). Migration applied, schema cache reloaded, PostgREST now sees the column.

### Tests
- 9 new tests on `MetricV6.value` / `MetricV6.delta` covering: string pass-through, int + float coercion (with precision preservation), delta-dict rendering for up/down directions with and without window, plain-string passthrough, None passthrough, numeric delta coercion.
- Full suite green: 545 passed in 161s.

### Followup
- Append `AGENT_LEARNINGS.md` entry: "code-schema and DB-schema must ship together — when adding a field to a Pydantic / TS type that flows to Supabase, write the matching SQL migration in the SAME PR." Distill into a new `AGENTS.md` landmine alongside #7.
- After merge: re-fire Thursday's #118 (`brief.cli run --publish --today=2026-05-28`) to overwrite the orphaned brief with full sections; then re-fire Friday's #119 (`--today=2026-05-29`) as a normal weekly_wrap retry.

---

## [1.5.0] — 2026-05-27

### Added
- **Preview-ready notifications.** New module `brief/preview_notify.py` sends two pings when the pipeline runs in dry-run with `--write-fixture` and the new `--preview-notify` flag: a Discord webhook message and a Brevo email to a dedicated recipient (NOT the subscriber list). Each channel is independent — one failing does not block the other. The ping includes the production-reachable preview URL (`https://thebrief.clauding-lab.com/preview?fixture=<name>.json`), the brief date + issue number, and the draft `todays_call` snippet for at-a-glance review.
- **New CLI flag `--preview-notify`** on `brief.cli`. Requires `--write-fixture`. Fires the notify module after the dry-run completes; failures log a warning but never change the exit code (the fixture write is the canonical artifact).
- **New env vars in `deploy/brief.env.example`**: `DISCORD_PREVIEW_WEBHOOK_URL` (channel webhook in Discord Server Settings → Integrations → Webhooks), `PREVIEW_EMAIL_RECIPIENT` (single address for editorial review, deliberately not the subscriber list). Reuses existing `BREVO_API_KEY` + `FROM_EMAIL` from the subscriber notifier.
- **10 new tests** in `tests/test_preview_notify.py` covering: URL builder, fixture metadata extraction (with missing-field tolerance), Discord ping body shape + error handling, Brevo email payload + HTML-escape on `todays_call` (XSS guard), and the orchestrator's independent-channel + missing-env paths.

### Notes
- No production data path changes. Daily auto-fire publish behaviour at 06:30 BDT is unchanged — preview notifications only fire when both `--write-fixture` and `--preview-notify` are explicitly passed.

---

## [1.4.0] — 2026-05-27

### Added
- **Historical anchors compute layer** (`brief/history_anchors.py`) — five cadence-aware primitives (`last_lower_than`, `last_higher_than`, `pct_change_since`, `rolling_extremes`, `first_cross_since`) that produce `HistoryFact` instances with pre-formatted parens phrases. Reads `metric_history` for daily/weekly/quarterly/fiscal_year and `metric_history_monthly` for monthly long-horizon. The compute layer is the sole formatter of "lowest since X (Y then)" prose — the editor inlines verbatim.
- **`Section.chart_read` field** with structured `{signal, context, implication}` — three short paragraphs rendered as a "Chart read" eyebrow block under every chart card using existing `.tb-analysis` styling. No new CSS, no new component.
- **`ChartReadV6` Pydantic model** in `brief/v6_schema.py` validating the new field.
- **Eight banker-essential monthly metrics in the Macro section**, read from `metric_history_monthly` (previously unused by The Brief): `cpi_12m_avg_monthly`, `cpi_p2p_food_monthly`, `cpi_p2p_nonfood_monthly`, `real_policy_rate_monthly`, `reer_monthly`, `private_credit_growth_yoy_monthly`, `m2_growth_yoy_monthly`, `import_cover_months_monthly`.
- **CPI 24-month trend chart in the Macro section** — new `chartConfigs.cpiTrend` config with three lines (headline 12m-avg, food, non-food).
- **Six new validators** in `brief/claude/validators.py`: `validate_no_banal_language`, `validate_chart_read_temporal_anchor`, `validate_chart_read_implication_quality`, `validate_chart_read_length`, `validate_history_claim_has_reference`, `validate_abbreviation_policy`.
- **Banker Vocabulary Tiers** subsection in `Master.md` defining Tier-1 (bare use), Tier-2 (expand on first use per section), Tier-3 (always expand or rephrase) abbreviation policy.
- **`/preview?fixture=<name>` SPA route** (shipped earlier in v1.4.0 as Phase 0.5) — server-rendered preview path for dry-run fixtures with a yellow "PREVIEW MODE" banner. Enables editorial review of brief content on a separate URL before production publish.
- **`brief/cli.py --write-fixture` flag** — dry-runs can now write directly to a fixture JSON file ready for SPA loading.

### Changed
- **Editor prompt** (`brief/claude/prompts/editor_v6.txt` + `editor_v6_friday.txt`) — banker-grade specificity contract (time-anchored AND implications-oriented), history_facts weaving rules (use `phrase` verbatim including parens), three-tier abbreviation policy, macro section per-section override allowing all 8 metrics (not capped at 5), `chart_read` added to OUTPUT SCHEMA.
- **Sub-editor prompt** (`brief/claude/prompts/subeditor_v6.txt`) — six new checklist items: specificity, temporal anchor on `chart_read.context`, history claim audit, history reference-value preservation, banal-language scan, abbreviation policy.
- **`Cover.sub`** — packs historical anchors verbatim when a `since_lower / since_higher / first_cross_since` HistoryFact exists for the cover metric.
- **`MetricHistoryClient.get_latest()` and `.get_history_window()`** — extended with optional `table` kwarg supporting `metric_history_monthly`.

### Scoped out for v1.4.0 (deferred)
- **Web search sanity check on historical claims** (spec §3.4 #5) — `max_client.py` wraps the Claude CLI subprocess with `--tools ""`, which disables tool-use. Enabling `web_search` requires a code change and CLI version verification. Deferred to a v1.4.x patch.

### Dependencies
- No new dependencies. No version bumps on `next`, `react`, `chart.js`, or `@supabase/supabase-js`.

---

## [1.3.2] — 2026-05-27

### Added
- **`AGENTS.md` at the repo root** — operational rules for AI coding agents working in this repo. Covers build/test/release commands, repo structure (Next.js SPA + Python pipeline + Supabase), key conventions (timestamp storage, Long View schema, chart series IDs, editor/sub-editor split, CSS-only/docs-as-separate-PR rule), and 13 numbered landmines covering recent incidents: `tb_*` legacy tables, Chart.js scale registration, notifier privacy, Vercel build wiping `.venv`, V1 GHA cron retirement, live-vs-legacy metric_id renames, `source_as_of` migration gap, Long View schema as contract, BDT/UTC time conventions, the 2026-05-27 CHANGELOG/tag drift, `package.json` as version source of truth, and Anthropic API transient retry rule.
- **`VISION.md` at the repo root** — auto-merge vs sign-off scopes. Long View content PRs that follow the recipe auto-merge; new block kinds, prompt edits, notifier changes, schema migrations, framework bumps, Master.md / Design.md / longview-workflow.md edits all need sign-off.
- **`AGENT_LEARNINGS.md` at the repo root** — running incident log. Seeded with four entries (most recent first): the 2026-05-27 CHANGELOG/tag drift caught at session-resume; the v1.3.1 notifier privacy leak (PR #83); the May 9 `tb_*` legacy tables ambush (PRs #60, #61); the May 9 Chart.js `CategoryScale` silent failure (PR #62).

### Changed
- **`CLAUDE.md` rewritten** from a 5-line longview-workflow pointer to a proper orientation file. Points at all five governance/content docs (AGENTS.md, VISION.md, AGENT_LEARNINGS.md, Master.md, Design.md) in a "read these first" table. The longview-upload workflow trigger is preserved in a Special workflows section.
- **README version badge + footer** bumped 1.0.0 → 1.3.1 (had been stale since v1.0.0 shipped 2026-05-15), then to 1.3.2 with this release.

### Chore
- **`.gitignore`** now ignores three local-only tool outputs: `.graphifyignore` (graphify config), `graphify-out/` (graphify HTML/JSON outputs, ~6.4MB), `.playwright-mcp/` (Playwright MCP cache).
- **V5 Plan-B wave 1 and wave 2 plan docs** committed to `docs/superpowers/plans/`. All sibling plan docs (pre-wave, wave-3) were already tracked; wave-1 and wave-2 had been written and used to ship PRs #21 and #22 (2026-04-29) but were never committed.

---

## [1.3.1] — 2026-05-26

### Added
- **`Master.md` at the repo root** — canonical brand & voice guide. Covers audience (Tier-1 BD banking professionals: business / risk / treasury / management committee / ALCO / credit committee), tone (clinical, fact-based, quietly analytical; explicitly neutral and diplomatic toward regulators and government while keeping substance fact-based), voice register, surface-specific voice (Today's Call, Banker's Read, Long View, email subject/body), word-level conventions (preferred-abbreviations table + avoid table), numbers/currency rules, honorifics, channel norms, pre-publish checklist.
- **`Design.md` at the repo root** — canonical design language guide. Captures identity (steel-crimson production palette, bone alternate for email), tokens (geometry, type, both palettes, semantic tone with oklch values), typography scale, Long View block kinds (all 5 shipped including bar-chart), hair rules, section structure, email design, diff-stale state, responsive rules, forbiddens, versioning rules.

### Fixed
- **Notifier privacy.** `brief/notifier.py::send_via_brevo` previously packed every subscriber into a single Brevo `to` array, exposing each recipient's address to every other recipient. Each subscriber now gets their own Brevo API call so the To: header only contains their own address. Sequential per-subscriber posts — well under any rate limit at current subscriber counts. Return contract preserved: `(sent_count, last_message_id, first_error_or_None)`. Tests updated to assert the privacy contract directly + cover partial-failure shape (succeed, fail, succeed).

---

## [1.3.0] — 2026-05-24

### Added
- **`bar-chart` block kind for Long View.** Renders a horizontal bar chart with optional vertical reference line (e.g., a regulatory threshold), per-item tone tinting, and an optional unit caption. Implemented as inline SVG with `viewBox`-driven responsive scaling; preserves the mono typography and palette-token visual contract. `BarChartBlock` adds to the `Block` union; `LongViewBarChart.tsx` is the dispatched component.
- Tone classes for bar fills (`bull`, `bear`, `warn`, `neu`) plus a neutral default. Reference line uses the `bear` palette token to signal a regulatory cut.

### Changed
- `LongView.tsx` dispatcher gains a fifth `case "bar-chart"`. No change to the eyebrow / title / lead / blocks / banker_read frame.
- `docs/longview-workflow.md` editorial-half should be updated separately to teach composers when to use bar-chart vs comparison. (Not in this PR — typo-fix CSS-only versioning rule preserves docs-as-separate-PR.)

### Notes
- Triggered by the first chart-bearing Long View upload (BB SPCD Circular No. 06 + listed-bank paid-up-capital ranking, 24 May 2026). The v1.2.0 CHANGELOG entry deferred chart rendering to "v1.3.0+ when the first chart-bearing slide upload arrives" — that day is today.

---

## [1.2.1] — 2026-05-22

### Changed
- **Banker-read typography tightened.** `.tb-longview-takeaway p` reduced from `font-size: 17px` to `14.5px` and `line-height: 1.5` to `1.55`. The takeaway paragraph was the largest body element in the Long View — heavier than the lead (14px) and prose (13.5px) — which made it dominate narrow mobile viewports. The "BANKER READ" small-caps label above the paragraph already carries the emphasis; the body text doesn't need to be larger than the lead.

---

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
