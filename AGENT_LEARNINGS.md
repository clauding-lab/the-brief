# Agent Learning Rulebook — The Brief

A running log of lessons learned the hard way while shipping The Brief.

Different from `AGENTS.md` — that file documents **stable conventions and landmines** (the codebase is structured this way; don't break it). This file documents **incidents and lessons** (this is what went wrong, and here's how to prevent recurrence).

**Author:** AI agents under Adnan's direction. Appended on every incident; entries are point-in-time observations that may go stale but the lesson stays.

## How to add an entry

When something ships broken, when a methodology gap is exposed, or when a smoke test catches a real bug:

1. Write the entry below using the template.
2. If the lesson generalizes across Adnan's other projects, also append to the global rulebook at `~/.claude/AGENT_LEARNINGS.md`.
3. Save to AI auto-memory at `~/.claude/projects/-Users-adnanrashid-Projects-clauding-lab-the-brief/memory/` so future Claude sessions inherit.
4. If the lesson is a stable codebase rule, distill into a numbered `AGENTS.md` landmine.

## Entry template

```markdown
## YYYY-MM-DD — vX.Y.Z | Short title

**Trigger:** what surfaced the issue.

**What went wrong:** root cause in plain English; cite file:line if useful.

**Lesson:** the generalizable rule in one sentence.

**Prevention:** concrete steps (validator, smoke checklist, CI gate).

**Hotfix:** what shipped to resolve.

**Cross-references:** AGENTS.md landmine, auto-memory key, global rulebook entry.
```

---

## Entries (most recent first)

## 2026-05-31 — PR #107 | Chart re-point deployed after the daily publish → live chart blank until next publish

**Trigger:** After merging + deploying F3 (§fx External Flow Balance — a chart *re-point*) to `main` + Hetzner at ~13:00 BDT, the live production fx chart rendered **blank**, even though the Vercel branch preview (with a fixture) rendered perfectly at 1440 and 390 with 0 console errors.

**What went wrong:** The SPA reads each section's chart `series` from the **published brief** (`get_latest_brief` RPC, `app/page.tsx:24`), NOT live from `metric_history`. Today's brief was published at 06:56 BDT by the OLD pipeline, so its fx section still carried the old daily keys (`monthly_export` / `monthly_import` / `monthly_remittance`, 90 daily points — verified via the RPC). The new `fxBalanceConfig` guards on `hasAnyData(ctx.series, ["exports_usd_mn_monthly", …])` → the new monthly keys weren't in the published data → `emptyLineConfig()` → blank. The preview looked fine because its fixture already had the new monthly keys. Because F3 (like F5/tbond) is a REPLACEMENT chart, the user-visible result is blank-vs-old-chart (a regression), not blank-vs-empty-slot.

**Lesson:** A chart re-point or new monthly chart only renders after a fresh pipeline publish stamps the new series into the brief. Deploying it *after* the day's 06:30 publish leaves the live chart blank until the next scheduled publish — and the Vercel preview is NOT sufficient proof, because its fixture carries the new keys.

**Prevention:** At deploy time for any chart re-point / new chart: (a) deploy BEFORE the day's 06:30 BDT publish so the first fire carries the new series, OR (b) plan a manual `python -m brief.cli run --publish` on Hetzner (regenerates the FULL editorial brief — Anthropic token cost + editor_v6 hang risk, so it's Adnan's call), OR (c) explicitly flag the "blank until next publish" window to Adnan and let him choose. ALWAYS smoke-check the LIVE prod chart after a re-point deploy, not just the Vercel preview. `brief.timer` fires Mon–Fri + Sun 06:30 BDT (Saturday skipped).

**Hotfix:** None applied — Adnan chose to wait for the Mon 06:30 BDT auto-publish, which self-heals (the new pipeline stamps the monthly fx series). F3 code itself is correct and verified end-to-end.

**Cross-references:** AGENTS.md landmine #17; auto-memory `project_chart_repoint_publish_gap`; relates to `feedback_preview_before_prod` and `feedback_chartjs_register_and_preview`. (Kept project-scoped — tied to The Brief's publish-then-read architecture — not promoted to the global rulebook.)

## 2026-05-30 — Saturday publish refused on a stale weekly_wrap lens; Opus 4.8/xhigh bump validated

**Trigger:** Manual fire of a missing Saturday (2026-05-30) brief, mid Opus 4.8/xhigh model bump (PR #102). The editor refused 3× — "today_lens is weekly_wrap, but this isn't Friday."

**What went wrong:** `score_lens` (`brief/builders/lens.py`) sets `weekly_wrap` only on Fridays, but its quiet-day fallback returned `previous_lens` verbatim. A quiet Saturday (markets closed → all sections score ~0) inherited Friday's `weekly_wrap`; the standard `editor_v6` prompt — which since v1.4.0 explicitly forbids emitting a weekly-wrap — refused the entire brief. This was the **first Saturday since that v1.4.0 guard shipped (05-27)**, so the bug sat latent for days. After the lens fix the editor passed, but `subeditor_v6` then failed 3× with an opaque `Claude CLI exited 1` (empty stderr) — which *looked* like it could be the Opus 4.8/xhigh bump but was **not**: an identical 3rd run succeeded (issue #121 published, 8 emails sent). It was a transient Anthropic API failure.

**Lesson:** (1) A mode value valid only on some days must never be carried forward by a "reuse yesterday" fallback onto a day whose consumer rejects it. (2) Don't blame your most-recent change for a failure until you've isolated it — a coincident transient API error mimicked a model regression; a plain retry told them apart.

**Prevention:** lens fix + regression test `test_quiet_day_never_inherits_weekly_wrap_on_non_friday`; `max_client` now surfaces the CLI's **stdout** on non-zero exit (PR #104) so `exited 1` is never opaque again; retry transient subprocess failures before deep-diving (see `feedback_editor_v6_transient_retry`).

**Hotfix:** PR #103 (lens guard), PR #104 (stdout-on-error). Model bump (PR #102, Opus 4.8/xhigh) validated end-to-end — editor ~6 min, sub-editor ~8 min, both well under the 30-min per-call timeout; editor was actually *faster* than the old 4.6/high.

**Cross-references:** AGENTS.md "Anthropic model selection" note (now `opus-4-8`/`xhigh`); global `~/.claude/AGENT_LEARNINGS.md`; auto-memory `reference_brief_opus48_lens_dataage`.

## 2026-05-29 — v1.5.1 | v1.4.0 publish broken for 2 days — code-schema and DB-schema must ship together

**Trigger:** user noticed Thursday 2026-05-28's brief was on the site but "almost nothing" rendered — masthead + Today's Call only, no sections below. Asked for a check before approving a Friday retry.

**What went wrong:** TWO independent v1.4.0 (PR #95, 2026-05-27 14:28 UTC) regressions stacked, blocking every publish for 48 hours:

1. **Missing migration for the new `Section.chart_read` field.** v1.4.0 added the `ChartReadV6` Pydantic model and the SPA render component but no `migrations/0004_*.sql` to add the column to the production `sections` table. Thursday's 06:30 BDT auto-fire was the first publish after v1.4.0 — the editor produced 11 sections with `chart_read` populated, the publisher inserted the brief row, then the sections insert blew up with PGRST204 `Could not find the 'chart_read' column of 'sections' in the schema cache`. Brief #118 was left orphaned in Supabase: `status=published` but 0 sections / 0 metrics / 0 news / 0 chart_series. The SPA's `get_latest_brief` still showed it, hence the "almost nothing" rendering.

2. **Editor schema-shape mismatch on `MetricV6.value` and `MetricV6.delta`.** The v1.4.0 banker-grade editor prompt began emitting `metric.value` as raw numbers (e.g., `35.1112` for FX reserves) and at least one `metric.delta` as a structured `{value, direction, window}` dict — where the Pydantic schema required pre-formatted strings (`"$35.11B"` / `"+0.99% WoW"`). Every retry after the chart_read fix produced 34+ Pydantic validation errors before Supabase was even contacted.

Friday 2026-05-29's 06:30 BDT auto-fire separately hit a 3-attempt editor timeout that exactly matched the systemd `TimeoutStartSec=90min` (3 × 1800s) and was SIGTERM'd — that's its own separate failure mode (covered by AGENTS.md landmine #13) but it would have hit both schema errors above on retry.

**Lesson:** Code-schema and DB-schema must ship in the SAME PR. When adding a field to a Pydantic / TypeScript type that flows to Supabase, write the matching SQL migration alongside it — and apply that migration to production before the next scheduled publish (or use a feature flag if the migration is delayed). For schema-shape changes to fields the editor is allowed to populate (numeric `value`, structured `delta`), update the Pydantic coercers in the SAME PR as the prompt change so the publish never sees a half-state.

**Prevention:**
- Add a CI smoke test that imports the Pydantic schema and exercises it against a representative fixture from `public/fixtures/`. A dry-run publish in CI against a Supabase migration-applied test schema would catch both v1.4.0 failures.
- When changing the editor prompt, write a corresponding test that feeds a synthetic editor output (with the new shape — numeric value, structured delta, etc.) through the Pydantic validator. The test should pass before the prompt PR merges.
- For any new field introduced on the data path (Pydantic → publisher → Supabase), the PR checklist requires either (a) a migration file and a verified production apply, or (b) explicit field nullability + a documented backfill plan.
- For schema migrations specifically: every PR that adds a column should include the migration file AND a 1-line "production-applied: yes/no" note in the PR description. CI can lint this.

**Hotfix:**
- PR #99 (2026-05-29 09:24 BDT): `migrations/0004_section_chart_read.sql` adding `chart_read jsonb` column + `NOTIFY pgrst 'reload schema'`. Applied to production via Supabase MCP `apply_migration`.
- PR #100 / v1.5.1 (2026-05-29 10:16 BDT): two `field_validator(mode='before')` coercers on `MetricV6` — `value` and `delta_pct` stringify numerics via `:.10g` (precision preserved); `delta` renders the editor's `{value, direction, window}` dict as banker-style `"+0.99% WoW"` / `"−0.99% WoW"` (Unicode minus, pretty-cased window). Strings and None still pass through unchanged.
- Thursday's #118 manually re-fired (became #119, brief_date 2026-05-28) at 10:39 BDT — 11 sections, 5 chart series, notifier sent 8 emails. Orphaned #118 row deleted.
- Friday's weekly_wrap manually re-fired (#120, brief_date 2026-05-29) at 11:01 BDT — 11 sections, 5 chart series, notifier sent 8 emails. Subscribers received both emails within ~25 min of each other.

**Side effects worth flagging:**
- Manual re-fires auto-increment `issue_no` from `max + 1`; they do NOT overwrite an existing issue based on `brief_date`. Thursday's content shipped as #119 (not #118) and required a manual DELETE of the orphan. If a future retry follows this pattern, expect the same two-step (publish + orphan cleanup).
- Subscribers got two emails ~25 min apart. For future double-retries, consider adding `--no-notify` on the first retry and firing the notifier manually after both publishes are confirmed.

**Cross-references:** AGENTS.md landmines #7 (`source_as_of` migration gap — same pattern as #1 above), #13 (Anthropic morning latency — separate cause for Friday's initial failure). Migrations 0004. PRs #99, #100. CHANGELOG entry [1.5.1]. Auto-memory keys `project_brief_publish_v6_failures.md`.

---

## 2026-05-27 — v1.4.0 | Banker-Grade Read shipped via 5-PR phased rollout

**Trigger:** session-resume brainstorm asked "what more can we develop to attract the banker audience feeding their info, insight, and analytical needs." Bottleneck identified as DEPTH (not acquisition/retention); depth flavor as INTERPRETATION (not history alone / peer / desk). Five phases shipped over the same session via subagent-driven-development: Phase 0.5 (preview infra), Phase 1 (history_anchors compute), Phase 2 (6 new validators + sub-editor checks + Master.md vocabulary tiers), Phase 3 (editor prompt rewrite + macro builder reading 8 monthly metrics from metric_history_monthly + CPI 24-month chart), Phase 4 (ChartRead SPA render).

**What went well:**
- Two-stage review per phase (spec compliance → code quality) caught real bugs before merge: Phase 1's FY formula inversion (would have labelled every FY metric one year off), Phase 1's self-anchor in last_lower_than (could return current month as historical anchor), Phase 2's substring matching on single-word tokens ("robust" matching "robustly"), Phase 3's CPI chart series limit bug (PostgREST `limit=24` for 3 metric_ids returns 8 rows per metric not 24 — see below), Phase 4's grid layout bug (bare `<p>` tags as direct children of `.tb-analysis` would scatter across the 2-column grid).
- The `/preview?fixture=<name>` infrastructure (Phase 0.5) was load-bearing — it let the user verify the real v1.4.0 editor output on a Vercel preview URL before any production publish, satisfying the preview-before-prod rule even for editorial pipeline changes that normally would only verify on the next 06:30 BDT auto-fire.
- Sub-editor revised 13 issues during the Phase 3 dry-run — banker-grade specificity enforcement caught real banal language and missing time anchors and rewrote them. The validators are actually working.
- Brevo 14d baseline: 46.15% unique open rate (36/78 delivered, 0 bounces) — frozen as v1.4.0 success-criterion baseline.

**What went wrong:**
1. **Phase-ordering bug: editor prompt added `chart_read` to OUTPUT SCHEMA in Phase 3, but the Pydantic `BriefPayloadV6` schema update was scheduled for Phase 4 Task 4.2.** Result: Phase 3 dry-run failed because the editor produced a field the strict Pydantic validator rejected with `extra_forbidden`. Caught at Phase 3 dry-run (Vercel preview gate); fixed by pulling Task 4.2 forward into Phase 3 (commit `96469ed`). **Lesson:** editor prompt and editor-output schema validation must move in lockstep — they're two sides of the same contract.

2. **CPI chart series under-fetched.** Code-quality reviewer caught that `fetch_macro_cpi_series` called `get_history_window([3 metric_ids], limit=24)`, but PostgREST applies `limit` to the TOTAL result set across all metric_ids interleaved. Result: ~8 rows per metric instead of the intended 24 months. Fix: multiply the limit by the metric count. **Lesson:** when batching multiple ids in PostgREST `in.()`, limits are global, not per-id. See AGENTS.md addendum below.

3. **`.tb-analysis` grid layout swallowed bare children.** Phase 4 implementer's first version rendered `chart_read` as three bare `<p>` tags inside `<div className="tb-analysis tb-chart-read">`. But `.tb-analysis` is `display: grid; grid-template-columns: 140px 1fr` — direct children become grid items in alternating columns. Caught by code-quality review before merge; fixed by wrapping in `<span className="label">Chart read</span>` + `<div className="body">` matching the canonical `.tb-analysis` use in the same file. **Lesson:** always read the CSS of "reused" classes before assuming they just style text. Grid + flex container classes have child-position semantics.

4. **Vercel deployment protection blocked the preview-before-prod workflow.** Every Vercel `.vercel.app` preview URL was gated behind Vercel SSO by default, blocking unauthenticated review. Toggled in Vercel dashboard → set "Vercel Authentication" to "Only Production Deployments" so previews are publicly accessible. Brief content is already public; no privacy concern.

5. **Test mock data ordering hid a real bug.** Phase 3 test mock for `get_history_window` returned rows in ASC order, but production PostgREST returns DESC. The `reversed()` call in `fetch_macro_cpi_series` was untested. Code-quality reviewer flagged; fixed by aligning mock to production + adding chronological-order assertion that fails if `reversed()` is removed.

**Lessons (durable):**
- The 2-stage review (spec then quality) per PR is genuinely catching real bugs. Don't skip either even when phases feel small.
- For PostgREST `in.()` batched queries, `limit` is GLOBAL across all ids — multiply by ID count to get per-id rows.
- Reused CSS classes carry child-position semantics if they're grid/flex containers. Always check the class definition before assuming it's "just styling".
- Editor prompt extensions that touch OUTPUT SCHEMA need the Pydantic validator extended at the SAME TIME. Phase-splitting these is fragile.
- Preview-before-prod is the right discipline; the cost is one small infrastructure PR (`/preview` route + `--write-fixture` flag) but the value is genuine pre-merge confidence on every editorial change.

**Prevention:**
- New AGENTS.md landmine (see addendum below) for PostgREST `in.()` limit gotcha.
- The grid-class hazard worth a landmine too — but it's adjacent to existing landmine #2 (Chart.js scale registration). Adding a generic "always check CSS class definition before reusing" landmine would be too broad. Adnan to consider whether this graduates to a landmine.

**Hotfix path if first 06:30 BDT publish post-merge fails:**
- If editor voice is off → patch in v1.4.1 by tightening prompt.
- If render breaks → CSS-only patch in v1.4.1.
- If macro data is wrong → re-run EconDelta backfill via `scripts/seed_macro_monthly.py` (separate repo).

**Cross-references:** PRs #92, #93, #94, #95, #96, #97. Spec: `docs/superpowers/specs/2026-05-27-banker-grade-read-design.md`. Plan: `docs/superpowers/plans/2026-05-27-banker-grade-read.md`. Brevo baseline: 46.15% unique opens over 2026-05-13 to 2026-05-27.

---

## 2026-05-27 — v1.2.1 / v1.3.0 / v1.3.1 | Three CHANGELOG entries shipped without git tags or GH releases

**Trigger:** session resume after 18 days idle. Auditing the repo's GitHub state surfaced that the latest release on GH was v1.2.0 (2026-05-16), but CHANGELOG.md already contained `[1.2.1]`, `[1.3.0]`, `[1.3.1]` entries. `package.json` was on `1.3.1`. Only `v1.3.1` had a git tag and GH release; v1.2.1 and v1.3.0 had drifted silent for weeks.

**What went wrong:** the release loop (bump → CHANGELOG → tag → GH release) was getting partially completed. The CHANGELOG entries went in with the corresponding PRs (#79 v1.2.1, #82 v1.3.0). The version bump in `package.json` happened. But the tag + GH release step was skipped or deferred and then forgotten. A reader of GitHub releases would have seen v1.2.0 as the latest, even though the production code was running v1.3.1.

**Lesson:** a CHANGELOG entry that doesn't have a matching git tag and GH release is not a release — it's a half-shipped artefact. The release loop must complete in one session.

**Prevention:**
- AGENTS.md landmine #11 codifies the rule: tag + GH release happen in the same loop as the CHANGELOG entry and version bump.
- AGENTS.md landmine #12 codifies that `package.json` is the source of truth for version; CHANGELOG and README must match.
- After publishing a non-latest release retroactively, ALWAYS verify the `Latest` flag is on the genuinely latest version via `gh release edit vX.Y.Z --latest`. GH auto-bumps `Latest` to the most recently published, not the highest-version, by default.

**Hotfix:** 2026-05-27 — created annotated tags `v1.3.0` (at `d6515a2`, PR #82 merge) and `v1.2.1` (at `04e694e`, PR #79 merge). Published matching GH releases. Re-pinned `--latest` to v1.3.1 twice (GH bumped it on each publish).

**Cross-references:** AGENTS.md landmines #11, #12; commits in this branch's hygiene PR; auto-memory `feedback_changelog_tag_release_lockstep.md` (to be saved if not already present).

---

## 2026-05-26 — v1.3.1 | Notifier privacy: Brevo `to` array exposed every subscriber's address

**Trigger:** review of `brief/notifier.py::send_via_brevo` while approving v1.3.1. Each brief publish was making one Brevo API call with every subscriber packed into the `to` array, so every recipient saw every other recipient's email address in the To: header.

**What went wrong:** the original send path was optimised for fewer API calls — one POST, N recipients, Brevo handles the fan-out. But Brevo treats the `to` array as a literal multi-recipient envelope. Each subscriber's email client showed the full subscriber list in the To: header. At ~dozens of subscribers it was an outright privacy leak; at the ~hundreds the brief is aiming for, it would have been a serious data incident.

**Lesson:** email sends to multiple distinct recipients must NEVER share an envelope unless explicitly BCC'd. Default to one POST per recipient, even at the cost of more API calls. Brevo (and most transactional providers) bill per-recipient anyway — rate-limit concerns at current scale are negligible.

**Prevention:**
- AGENTS.md landmine #3 captures the rule.
- `tests/test_notifier.py` now asserts the privacy contract directly: `send_via_brevo` is mocked to verify each POST carries exactly one address. The partial-failure shape (succeed, fail, succeed) is also covered.
- Return contract preserved: `(sent_count, last_message_id, first_error_or_None)`.

**Hotfix:** PR #83 (2026-05-26) — `send_via_brevo` now iterates subscribers sequentially, one POST per address. Shipped as part of v1.3.1.

**Cross-references:** AGENTS.md landmine #3; CHANGELOG v1.3.1 Fixed section; PR #83.

---

## 2026-05-09 — pre-v1.0 | Chart cards stale because `tb_*` tables are LEGACY (not EconDelta-fed)

**Trigger:** four chart cards on the live SPA (Brent, DSEX, Yield Curve, LNG JKM) showed data 8–29 days old. The working premise going in was: "EconDelta scrapers populate the `tb_*` tables; fix EconDelta and the charts will refresh."

**What went wrong:** the `tb_*` tables had no writer at all after the V6 cutover deleted `the-brief/ingest.py` on 2026-05-04. EconDelta does write fresh data — but to `metric_history` with different metric_ids (`brent_crude_usd_barrel`, `dsex`, `tbond_bond_5y`, `tbond_bond_10y`, `tbill_91d_yield_pct`, `tbill_182d_yield`, `tbill_364d_yield`). The chart fetchers in the brief repo still pointed at the legacy `tb_*` tables. Two days of EconDelta-side investigation chased a symptom in the wrong repo.

**Lesson:** when stale data surfaces, FIRST check who writes the table. `grep -rE '(tb_brent|tb_dsex|tb_lng|tb_yield)' .` returned zero matches in either repo — that's the moment the premise should have flipped. Don't assume that because the schema lives in repo A, the writer also lives there.

**Prevention:**
- AGENTS.md landmine #1 captures the legacy/active table mapping (`tb_*` LEGACY → `metric_history` with new IDs).
- AGENTS.md landmine #6 captures the specific metric_id renames (e.g., live DSEX is `dsex`, not `dse_dsex_close`).
- Diagnostic flow for stale-data investigations: `grep` for the table name in BOTH repos before deep-diving the scraper.

**Hotfix:** PR #60 (2026-05-09) — repointed `brief/chart_series_fetcher.py` to read from `metric_history` using the live metric_ids. Followups: PR #61 (yield-curve V3 layout + Brent/DSEX polish), PR #62 (CategoryScale registration — see next entry).

**Cross-references:** AGENTS.md landmines #1, #6, #7; econdelta repo's `docs/handoff/2026-05-09-brief-charts-repoint.md`; auto-memory `project_brief_tb_tables_legacy.md` (in the econdelta project's memory dir).

---

## 2026-05-09 — pre-v1.0 | Yield-curve chart silently failed after repoint because CategoryScale wasn't registered

**Trigger:** after PR #61 landed the yield-curve repoint to `metric_history`, the chart rendered as a blank card. Browser console threw an unregistered-scale error.

**What went wrong:** `app/components/BriefChart.tsx` registers Chart.js components explicitly (Chart.js is tree-shaken — nothing is auto-registered). The legacy `tb_yield_curve` renderer used a different axis configuration. The new metric_history-driven curve switched to a category-typed x-axis with tenor labels (91d / 182d / 364d / 5y / 10y) but `CategoryScale` was never added to the registration block. Result: silent render failure.

**Lesson:** Chart.js is tree-shaken — every controller, element, and scale must be explicitly registered before use. When adding or modifying a chart kind, audit which scales it depends on and confirm they're registered in the same PR.

**Prevention:**
- AGENTS.md landmine #2 captures the rule.
- When adding a chart, the checklist is: identify scale types (Linear / Category / Time / Logarithmic / Radial), register them in `BriefChart.tsx`, then deploy.
- Visual smoke check on a Vercel preview before merging chart PRs.

**Hotfix:** PR #62 (2026-05-09) — added `CategoryScale` to the registration block in `BriefChart.tsx`.

**Cross-references:** AGENTS.md landmine #2; PR #62.

---
