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
