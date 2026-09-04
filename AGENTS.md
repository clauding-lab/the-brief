# AGENTS.md — The Brief

Operational rules for AI coding agents (Claude Code, Cursor, Codex CLI, etc.) working in this repo. Read this in full before making any code change.

## What this project is

The Brief is a daily Bangladesh-economy banking-style brief for senior banking professionals at Tier-1 banks (business heads, risk heads, treasury heads, ALCO/MANCO members). It ships:

- A **Next.js 16 SPA** at `https://thebrief.clauding-lab.com/` (Vercel, continuous-deploy from `main`).
- A **Python pipeline** (`brief/`) that composes each day's brief and writes it to **Supabase** (project `ssbliukchgibjcjohibi`).
- A **Brevo transactional email** sent per-publish to opted-in subscribers (one POST per subscriber — see landmine #3).

Owner: solo dev (Adnan, Bangladesh, UTC+6). Vibe-coded — Adnan directs AI agents, does not hand-write code himself. All explanations, summaries, and prose should be in **plain English with technical terms briefly explained**, never assume Adnan reads code.

## Repository structure

```
app/                  Next.js 16 App Router pages + components
  components/         BriefChart, LongView*, Section, Masthead, Cover, …
brief/                Python pipeline package
  builders/           per-section composers (macro, fiscal, remit, …)
  render/             v5 HTML render (legacy; v6 writes JSON to Supabase)
  claude/             Anthropic API wrapper (max_client.py) + validators.py + prompts/ (editor_v6, subeditor_v6)
  pipeline.py         orchestration entry; v6_publisher.py writes Supabase rows
  cli.py              `python -m brief.cli run --publish [--dry-run]`
  notifier.py         Brevo send (per-subscriber — landmine #3)
  chart_series_fetcher.py  reads metric_history (NOT tb_* — landmine #1)
content/              long-view.ts   pinned editorial pin (Long View)
deploy/               systemd units, env templates, deploy notes for Hetzner
docs/                 longview-workflow.md (recipe contract), specs/, plans/
fixtures/             test inputs (real headlines, real macro snapshots, etc.)
lib/                  format.tsx (BDT helpers), supabase clients
migrations/           Supabase SQL migrations
public/               static assets (favicon, og image)
scripts/              one-shot debugging scripts
tests/                pytest — see test_pipeline_v6_*, test_notifier.py, etc.
types/                brief.ts (LongViewData, Block, BriefRow, …)
CHANGELOG.md          version history (keep-a-changelog style)
Master.md             brand & voice — read before generating prose
Design.md             design language — read before touching CSS/components
```

## Build, Test, Run

| Goal | Command |
|---|---|
| **SPA dev server** | `npm run dev` → http://localhost:3000 |
| **SPA production build** | `npm run build && npx tsc --noEmit` |
| **SPA lint** | `npm run lint` (ESLint flat config) |
| **Python unit tests** | `.venv/bin/pytest -q` |
| **Python dry-run publish** | `set -a; source /tmp/brief.env; set +a; .venv/bin/python -m brief.cli run --publish --dry-run --no-notify` |
| **Real publish (production)** | runs as `brief.service` on Hetzner — see landmine #5 |

Notes:
- Use **`npm`**, NOT `pnpm` — repo's lockfile is `package-lock.json`.
- Python uses `.venv/` at the repo root. `requirements.txt` is runtime; `requirements-dev.txt` is pytest + linters.
- The Vercel build uses `rm -rf .venv && npm run build` (per `vercel.json`) — the Python venv must not be packaged for the SPA. See landmine #4.

## Release flow

1. PR merges to `main`. CI green. Squash merge is the default.
2. After a release-worthy batch:
   - Bump `package.json` `version` field.
   - Add a CHANGELOG entry (keep-a-changelog format; see prior `[1.x.x]` blocks).
   - Update README's "Current: vX.Y.Z" line if present.
3. Tag the merge commit: `git tag -a v<X.Y.Z> <hash> -m "<short title>"` then `git push origin v<X.Y.Z>`.
4. Publish a GitHub release with body matching the CHANGELOG entry: `gh release create v<X.Y.Z> --title "..." --notes "..."`.
5. Confirm GH `Latest` flag is correct — see landmine #11.

Vercel auto-deploys from `main`; the SPA serves the new version within a few minutes. The Python pipeline picks up the new version on the next `brief.service` fire.

## Coding style

- **TypeScript/React:** ESLint flat config (`eslint.config.mjs`); `next` rules; idiomatic React 19 + Next 16 App Router. Format with the project's existing style (no Prettier configured at repo root).
- **Python:** project follows PEP 8; type hints required on new public functions. `pytest` for tests. Tests live in `tests/`, mirror the package layout where possible.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, etc.) with optional scope (`feat(spa):`, `fix(pipeline+spa):`). Imperative mood. **No `Co-Authored-By: Claude` lines** — attribution is disabled globally; do not re-add.
- **Files:** keep modules focused; ~400 lines typical, 800 max.

## Key conventions

These are shape rules that govern HOW code/configs/data are named, structured, and wired together in this repo. A fresh AI agent should match them without re-discovering.

- **Timestamps:** stored as UTC ISO 8601 in Supabase (`as_of`, `posted_at`, `published_at`, `created_at`). The SPA formats to BDT (`Asia/Dhaka`) at render via `lib/format.tsx`. Never do timezone math in JS where Python could pin it; see landmine #10.
- **Long View schema:** `content/long-view.ts` exports a `LongViewData` from `types/brief.ts`. Five block kinds are exhaustive: `prose`, `comparison`, `stat`, `bullet-list`, `bar-chart`. The recipe for adding/replacing a pin lives at `docs/longview-workflow.md` — follow it exactly.
- **Chart series IDs:** `brief/chart_series_fetcher.py` reads from Supabase `metric_history`. Live IDs: `brent_crude_usd_barrel`, `dsex`, `tbond_bond_5y`, `tbond_bond_10y`, `tbill_91d_yield_pct`, `tbill_182d_yield`, `tbill_364d_yield`, and since v2.4.x `dommr` + `bofr` (BB Money Market Reference Rates, written by EconDelta's `money_market_ref_rate` fan-out with REAL value-dates; banking §04's chart — its series keys must stay in sync across chart_series_fetcher, chartConfigs, and chartMeta CHART_SPECS, guarded by the parity test in `lib/chartMeta.test.ts`). `comm_lng_jkm` and `lng_price_usd_mmbtu` are both dead to this repo as of v1.6.7: the Commodities section that read them was retired (see landmine #30), so no builder asks for either id. See landmine #6 for the "legacy vs live" map.
- **Section ordering:** sections render in `group_key` order. Group dividers and stale collapsing are in `app/components/ClientApp.tsx`. Each section carries `freshness` and `pills` populated by the pipeline.
- **Editor / sub-editor split:** the Python pipeline uses two Claude calls per brief — an "editor" mega-prompt that drafts, then a "sub-editor" self-review that returns a `pass | fail` verdict. Both calls go through `run_max()` in `brief/claude/max_client.py`; `pipeline_v6.py` drives them with the `editor_v6.txt` / `editor_v6_friday.txt` and `subeditor_v6.txt` prompt templates (`brief/claude/prompts/`), and `brief/claude/validators.py` holds the hard, testable checks behind the sub-editor's verdict. There is no `editor.py` or `subeditor.py` — those filenames have never existed in this repo. Exit code `4` means `V6PublishError` reached `cli.py` — that covers a sub-editor `fail` verdict, a malformed-review hold, a `DenylistViolationError` from `_run_deterministic_gate`'s hard-fail hallucination check (added 2026-08-22, audit #204), AND (added 2026-08-22, same audit's round-2 follow-up) a `ProseNumberGateError` from the post-editor number/period validator (see landmine 34). All four hold the publish the same way; check the log line for which one fired.
- **CSS-only / docs-as-separate-PR rule:** typo fixes in prose copy and CSS-only tweaks don't need a version bump or a CHANGELOG entry. Substantial component/pipeline changes do. Master.md, Design.md, and `docs/longview-workflow.md` edits should ship in their own PR to keep diffs clean.
- **Anthropic model selection:** there is a SINGLE model pin — the `run_max()` defaults in `brief/claude/max_client.py` (`model="claude-opus-4-8"`, `effort="xhigh"`). Both the editor and the sub-editor inherit it; `pipeline_v6.py` does not override per phase, and no Sonnet path exists. `--effort` drives *adaptive thinking* on Opus 4.7+ (high/xhigh/max → deep thinking automatically); there is no separate thinking flag and `MAX_THINKING_TOKENS` is ignored. Don't downgrade to older models; don't bump to newer ones without confirming the prompt contract still holds (run a `--dry-run --write-fixture` and validate against the V6 schema + preview before shipping).

## Known landmines (read before touching these areas)

1. **`tb_*` tables in Supabase are LEGACY.** `tb_brent_daily`, `tb_dsex_daily`, `tb_lng_jkm_weekly`, `tb_yield_curve` had no writer after the V6 cutover deleted the original `the-brief/ingest.py` (2026-05-04). Live data comes from EconDelta's `metric_history` writer. `brief/chart_series_fetcher.py` was repointed to `metric_history` in PR #60 (2026-05-09). **Don't add new readers of `tb_*` tables.** The handoff doc lives in the econdelta repo at `docs/handoff/2026-05-09-brief-charts-repoint.md`.

2. **Chart.js requires explicit scale registration.** All Chart.js controllers, elements, AND scales must be registered in `app/components/BriefChart.tsx` before use. PR #62 fixed a yield-curve render that silently failed because `CategoryScale` wasn't registered. When adding a new chart kind: identify the scales it needs (Linear, Category, Time, …) and register them in the same PR.

3. **Notifier privacy: one Brevo POST per subscriber.** Never pack multiple subscribers into a single Brevo `to` array — the To: header exposes each recipient's address to every other recipient. `brief/notifier.py::send_via_brevo` iterates and sends one POST per subscriber. Tests assert the privacy contract directly. PR #83 fixed the original leak.

4. **Vercel build wipes `.venv`.** `vercel.json` runs `rm -rf .venv && npm run build`. Don't put SPA dependencies inside the Python venv. Don't add Python build steps to the Vercel pipeline — the SPA build must be self-contained.

5. **`brief.service` on Hetzner is canonical; GHA cron is retired.** The V1 `Daily Brief Update` GitHub Actions cron was retired in PR #57. All publishes now run via systemd timer on Hetzner `clauding-lab`. Don't reintroduce a GH Actions cron for publishes.

6. **Live DSEX metric_id is `dsex`, NOT `dse_dsex_close`.** The latter is legacy and stops at 2026-04-21. Same pattern: live Brent is `brent_crude_usd_barrel`, not `brent_crude`. When in doubt, query `metric_history` for max(as_of) per metric_id and trust the freshest.

7. **`source_as_of` column shipped in code but not in production Supabase.** The May 4 schema work added the column to migrations but the migration was never applied. Aggregate runs without it (column is opportunistic). Don't write queries that REQUIRE `source_as_of` unless you've verified the migration is applied first.

8. **CSS-only / docs-as-separate-PR rule.** Bundling a typo fix or CSS tweak with a feature PR muddies the diff. Master.md, Design.md, and `docs/longview-workflow.md` are CONTRACT files — Claude reads them to compose Long View pins. Editing them inside a feature PR risks the next session reading half-old, half-new contract.

9. **Long View schema is the contract.** `content/long-view.ts` follows `LongViewData` in `types/brief.ts`. The 5 block kinds are exhaustive. Don't invent a 6th without a version bump and design review. The recipe at `docs/longview-workflow.md` is the source of truth for editorial AND operational steps — follow it without improvising.

10. **Times in BDT for humans, UTC ISO 8601 for storage.** All Supabase timestamps are UTC. The SPA formats to `Asia/Dhaka` at render via `lib/format.tsx`. PR #63 fixed a news-date tz hydration bug — don't introduce code that does timezone math in JS where Python could pin it.

11. **Tag every CHANGELOG version on its merge commit, same day as the release.** v1.2.1 and v1.3.0 CHANGELOG entries lived for weeks without git tags or GH releases (caught + backfilled 2026-05-27). When bumping version + CHANGELOG, push the annotated tag and create the GH release in the same loop. Also: GH auto-marks the most-recently-published release as `Latest` regardless of version — verify and re-pin `--latest` with `gh release edit` if needed.

12. **`package.json` `version` is the source of truth.** README "Current: vX.Y.Z" line and CHANGELOG entries should match. Bump all three together. Don't bump only one.

13. **Anthropic API transient failures are common at 04:00–06:00 BDT.** The publish window overlaps with high traffic / token rotation on Anthropic's side. If `brief.service` fails with timeout or 401, a manual re-fire often succeeds. See the manual-fire snippet in README's Operations section. Don't deep-dive an Anthropic issue without trying a retry first.

14. **PostgREST `in.(...)` query `limit` is GLOBAL across all matched `metric_id`s, NOT per-id.** When batching multiple metric_ids in a single `get_history_window` call (e.g., the 3 CPI series for the macro chart), use `limit = months * len(metric_ids)` — not `limit = months`. Caught in v1.4.0 Phase 3: `fetch_macro_cpi_series([3 ids], limit=24)` was returning ~8 rows per metric instead of 24 months each, because PostgREST sorts the merged result set by `as_of.desc` then caps at 24 rows total. The denser metric eats the cap.

15. **`.tb-analysis` is a `display: grid; grid-template-columns: 140px 1fr` container.** Bare children become grid items in alternating columns — a `<p>` placed directly inside would scatter across the label/body columns and render broken. When reusing `.tb-analysis` (e.g., the new ChartRead block in v1.4.0), wrap children in the canonical `<span className="label">EYEBROW</span>` + `<div className="body"><p>...</p>...</div>` structure. The pattern is already in use for the regular Analysis block at the bottom of each `app/components/Section.tsx` — copy that shape.

16. **Diverging area charts with an overlay line must stack inflows manually, NOT via `scales.y.stacked`.** A config like `fxBalanceConfig` in `lib/chartConfigs.ts` that stacks positive inflow areas under a net-balance overlay line must use **manual cumulative dataset values + `fill:'-1'`** to band the areas, not Chart.js `scales.y.stacked`. Turning on `y.stacked` folds the negative outflow areas and the overlay line into the stack, so the bands render wrong — caught in the F3 brainstorm mockup, where inflows showed ~$4bn instead of ~$7bn.

17. **Chart series render from the PUBLISHED brief, not live `metric_history` — a chart re-point deployed AFTER the day's 08:00 publish shows BLANK until the next publish.** The SPA reads each section's `series` from `get_latest_brief` (`app/page.tsx`); a config that newly reads different metric_ids (e.g. F3 `fxBalanceConfig`, F5 `yieldLadderConfig`) finds the OLD keys in the already-published brief, fails its `hasAnyData` guard, and renders empty. The Vercel preview uses a fixture with the NEW keys, so it looks fine even when prod is blank — ALWAYS verify the LIVE prod chart after a re-point deploy. Mitigate by deploying before the 08:00 BDT fire, planning a manual `brief.cli run --publish`, or flagging the blank-until-next-publish window. `brief.timer`: Mon–Sun 08:00 BDT (7 days/week since PR #116, 2026-07-04 — `OnCalendar=Mon..Sun`; Saturday is no longer skipped). See AGENT_LEARNINGS.md 2026-05-31.

18. **A new `SectionV6` JSONB field ships WITH its migration in the same PR, and the migration is applied to prod BEFORE the code publishes — an agent CANNOT apply the DDL itself.** Adding a section field (e.g. `chart_read`, F4 `movers`) means a Pydantic model + a `migrations/000N_*.sql` (`ALTER TABLE public.sections ADD COLUMN IF NOT EXISTS <col> jsonb; COMMENT …; NOTIFY pgrst, 'reload schema';`) + leaving the field OUT of the publisher's child-table `exclude` set. There is **no programmatic DDL path** (no `psql`, no Supabase CLI, no service-role key locally, no `DATABASE_URL` on Hetzner; PostgREST can't run DDL) — hand Adnan the SQL for the Supabase SQL editor (`https://supabase.com/dashboard/project/<ref>/sql/new`), then verify the column with an anon SELECT (`/rest/v1/sections?select=<col>&limit=1` → HTTP 200) before merge/deploy. Skipping/mis-ordering the migration orphans the next brief with PGRST204 (Brief #118, `chart_read`). See AGENT_LEARNINGS.md 2026-05-29. **Self-deploy sharpens this ordering:** since `brief.service` gained an `ExecStartPre` self-pull (PR #133), a merged PR is pulled and run UNATTENDED at the next 08:00 fire — there is no longer a human checkpoint between merge and production. Any PR that needs manual steps (this landmine's Supabase DDL, new deps in `requirements.txt`, new `/etc/brief.env` vars) must have those steps applied BEFORE the merge, not after.

## 19. Library/framework API calls → Context7 first

Before writing or editing code that calls a third-party library or framework API,
query **Context7** for current, version-pinned docs — do NOT rely on training-cutoff memory.

- **Flow:** `resolve-library-id` (name → `/org/project` ID) → `query-docs` (PIN the version this repo ships, e.g. `/vercel/next.js/v16.2.4`).
- **Applies to:** `next` 16 (App Router, `app/`), `react` / `react-dom` 19, `@supabase/supabase-js` 2, `chart.js` 4 + `chartjs-adapter-date-fns` 3, `date-fns` 4 (SPA side); `anthropic` (Python SDK, `brief/claude/`) and `pydantic` 2 (pipeline side).
- **Skip for:** business/domain logic, general programming concepts, or libraries Context7 does not index.
- **Query specifically:** library + version + exact task (e.g. `chart.js 4 register CategoryScale for a bar chart` or `@supabase/supabase-js 2 select with in.() filter and limit`), never one-word topics like "auth".

## 20. Editor voice and Sub-Editor enforcement move in LOCKSTEP

The editorial register is **the Daily Star business desk** — plain, declarative, reported prose: full sentences, not telegrams; one idea at a time; the mechanism explained in ordinary words; the facts carrying the judgment; neutrality toward institutions. This is the SINGLE register (PR #174, v2.2.0, 2026-08-24), superseding the Economist/FT four-dial register of PR #114 — the four calibration dials and the "wit is earned" allowance are gone, and `Master.md` is the binding voice contract the prompts implement. It is set in `brief/claude/prompts/editor_v6.txt` + `editor_v6_friday.txt` AND policed by `subeditor_v6.txt` (§7 voice-sanity, §12 slop blocklist).

- **Change one, change the other.** Retune the Editor's voice without the Sub-Editor and the Sub-Editor flattens it back out on its revise pass. §7 polices the register on its own voice-sanity checklist (telegram compression, neutrality, performed candour, humour — read the prompt for the current list; it does not check every Editor rule, e.g. mechanism-in-ordinary-words is Editor-side only); §12's blocklist (delve/myriad/robust/amid/moreover…) is LLM-slop and stays.
- **CI enforces the sync, partially.** `tests/claude/test_prompt_voice_consistency.py` (shipped by #174) requires the `## Voice rules` block to be BYTE-IDENTICAL in `editor_v6.txt` and `editor_v6_friday.txt` — copy it, don't paraphrase — asserts the neutrality and no-humour clauses where they must appear, and bans the retired register's terms across all four voice-bearing files (both editor prompts, `subeditor_v6.txt`, `Master.md`). A partial voice edit fails CI instead of shipping; a red run there means a paraphrased block or a stale file, not a Python bug.
- **The guardrail:** nothing salesy, motivational, or guru-flavoured ("if it could appear on a LinkedIn post, delete it") — with the irreverence dial retired, the test now polices marketing and performed-candour drift, and the plain reported register wins every tie. The banker-grade specificity contract, abbreviation tiers, history-facts-verbatim, and char limits are unchanged — register is texture, not discipline.
- **Verify a real render before merging a voice change** — prompt text alone won't show drift. See landmine 21 for the no-prod dry-run.

## 21. Merging to `main` self-deploys at the next timer fire — there is no human checkpoint

Since `brief.service` gained an `ExecStartPre` self-pull (PR #133, `deploy/brief.service:37-39`), a merge to `main` is picked up automatically: the unit runs `brief_guard.sh` (refuses anything but `main`), then `git pull --ff-only origin main` (best-effort — a network-blackholed pull still runs the publish on the current checkout), then `brief_guard.sh` again, before `ExecStart` fires the publish. No SSH or manual `git pull` is needed to ship a merged PR — it runs UNATTENDED at the next `brief.timer` fire (Mon–Sun 08:00 BDT — 7 days/week since PR #116, 2026-07-04; time moved 06:30 → 08:00 in PR #149 so the fire lands after EconDelta's aggregate). **What still needs a hands-on step BEFORE the merge, not after:** anything the self-pull can't apply for you — Supabase DDL (landmine #18), new deps in `requirements.txt`, new `/etc/brief.env` vars. Land those on the box first, then merge. A non-fast-forwardable checkout is skipped silently (deploy/README.md's Daily operation section) — the second `brief_guard.sh` call logs the post-pull branch + short `HEAD` to the journal, so read that to confirm the fire actually ran the merge commit. To preview output WITHOUT touching prod: `brief.cli run --publish --dry-run --write-fixture <path>` (no Supabase write, no email) rendered from a throwaway `git worktree` on the feature branch, then read the JSON. See AGENT_LEARNINGS.md 2026-06-07.

## 22. `publish_brief` is a TWO-PHASE near-atomic write — keep the draft→published flip LAST

`v6_publisher.publish_brief` inserts the `briefs` row as **`status='draft'`**, POSTs all sections/metrics/news/chart_series, then **`PATCH status='published'` as the very LAST call**. The SPA's `get_latest_brief` RPC filters `WHERE status='published'`, so a brief is invisible until that single flip — a mid-loop failure leaves a draft (invisible) that the next publish's DELETE clears. This closed the orphaned-brief-#118 / served-half-brief hole (fixed 2026-07-09; AGENT_LEARNINGS 2026-07-09 + 2026-05-29). It is NOT a real DB transaction (PostgREST can't span one) — the guarantee is that reader visibility rides on the one final status flip.

**When editing the publisher:** never move the `status='published'` PATCH earlier, never insert the brief row as `published`, and never grant visibility before every child row is written. If `get_latest_brief` is ever changed to stop filtering `status='published'`, this guarantee breaks — the two must stay in lockstep. Regression tests `test_publish_brief_stays_draft_when_child_post_fails` and `test_publish_brief_atomic_flow` (`tests/v6/test_v6_publisher.py`) enforce the order + never-publish-on-partial-failure. Note: `pipeline_v6.py`'s module docstring still says "atomic Supabase write" loosely — the real mechanism is this two-phase flip. The 2026-07-04 ecosystem-review fix plan is at `docs/handoff/2026-07-04-review-fixes.md`.

## 23. Builders read history through the pipeline's SINGLE batched `get_history_window` call — never add a second

`brief/pipeline.gather()` enriches every metric's sparkline via ONE `_enrich_metric_history` call that issues exactly one `MetricHistoryClient.get_history_window(...)`, and `tests/test_pipeline_integration.py::test_gather_enriches_metric_history_values` asserts `get_history_window.assert_called_once()`. A section builder that adds its OWN `get_history_window` call (e.g. to compute a week-ago prior for a WoW delta) makes it two → that test fails. If a builder needs a prior/trend value, use the sparkline already attached downstream (`Metric.history_values`) or a single `get_latest` — do NOT open a second window fetch from inside a builder. (B3 item 12, 2026-07-10: this constraint forced the `bb` reserves WoW delta to be dropped rather than computed from an honest week-ago prior.)

## 24. Live corridor/reserves ids: `policy_rate_*` are daily-restamped (`as_of` ≠ decision date); reserves is `gross_reserves_usd_bn`, NOT `bb_gross_reserves`

EconDelta re-upserts the standing BB policy corridor to `metric_history` every day, so `policy_rate_repo` / `policy_rate_sdf` / `policy_rate_slf` rows always carry `as_of` = the run date, not the MPC decision date. Read them for the VALUE via `history.get_latest`, keep `cadence="event"`, and never present that `as_of` as "the rate changed on this date." `brief/builders/bb.py` reads these live (**repo/sdf/slf = 9.50/7.50/11.00 as of the 2026-07-30 MPC cut**; the retired hardcoded 8.5 SDF is gone). Live reserves id is `gross_reserves_usd_bn`; the legacy `bb_gross_reserves` id has had **no writer since 2026-03-01** — do not read it (extends landmine #6's live-vs-legacy map). **It is NOT "fresh daily" any more (corrected 2026-09-02):** since econdelta #97 (1 Aug 2026) EconDelta stamps the row with BB's month-END date (`as_of` 2026-06-30, 2026-07-31, …) and the new month's figure only lands ~11 days after month-end, yet `bb.py` and `fx.py` both declare it `cadence="weekly"` (fresh ≤7d, stale >10d). A weekly badge on a month-end-stamped feed is stale on arrival and stays stale until the next month lands — §02 and §04 read "stale" in every issue checked (212–215 directly; a sweep found 117/117 since #98), so the badge carries no information there. Fix is a cadence re-declaration (monthly, or a reserves-specific threshold), not a data repair. When a corridor read fails (history unreachable / row missing), `bb.py` falls back to a module last-known constant marked `stale=True` — never blank, never a fallback mislabelled as live.

**`cadence="event"` is bounded on the RESTAMP date, not unconditionally fresh (changed 2026-08-03, PR #142).** It used to return `"fresh"` for every event metric no matter what, which meant §02 was *structurally incapable* of reporting staleness — and did read "fresh" for the four days The Brief printed the pre-cut 10.00% policy rate. `brief/cadence.py` now treats event freshness as a **writer-liveness check**: `stale=True` (fallback-sourced) → `"stale"`; otherwise ≤7d since restamp → `"fresh"`, ≤10d → `"warning"`, else `"stale"`. A standing rate that has not MOVED in years still reads fresh — only a writer that stops confirming it goes stale. **The `_FALLBACK_*_PCT` constants in `bb.py` go out of date at every MPC decision** — bump them in the PR that reacts to the move, with `_LAST_MPC_DECISION`; `tests/builders/test_bb.py::test_fallback_constants_match_the_latest_mpc_decision` guards the pre-cut values specifically.

**Corollary (2026-08-27, Real Policy Rate incident): `at_or_before(date)` on a restamped series returns the restamp LAG, not the value in force on that date.** EconDelta restamped the 30 Jul MPC cut only on 03 Aug, so `at_or_before(31 Jul)` returned the pre-cut 10.00% and the brief printed Real Policy Rate 1.68% instead of 1.18% for weeks. Whenever a decision date sits between the row you fetched and the reading you pair it with, the fetched row is stale by construction — check `_LAST_MPC_DECISION` (as `_real_policy_rate`'s guard now does, bounded by `_REAL_POLICY_MAX_MONTHS_APART`) before trusting an `at_or_before` read on any `cadence="event"` id. See AGENT_LEARNINGS.md 2026-08-27.

## 25. The 5-tile render cap is GONE — every stored metric tiles; tenor tile-eligibility is an OPEN owner decision

`app/components/Section.tsx` renders a section's FULL stored metrics list (the
historical `metrics.slice(0, 5)` cap was removed 2026-08-05, PR #157, after it
silently unpainted stored macro metrics — CPI 12m Avg, M2 YoY, REER). Two
consequences supersede the original wording (B3 item 11, 2026-07-10):
- Builder list order is ADVISORY, not load-bearing: the daily editor reorders
  (and drops) metrics before storage, so "first 5" was never a real guarantee
  post-editor anyway (see the 2026-08-05 SDF diagnosis memo).
- The cap was the ONLY thing keeping `bb.py`'s call-money tenor points
  (7d/14d) off the tile row. **After PR #158, `bb` typically stores 6-7
  metrics, not ≤5** — pipeline reconciliation (`PROTECTED_METRIC_IDS` +
  `_reconcile_metrics` in `brief/pipeline_v6.py`) re-injects any of the
  corridor's protected metrics (`bb_policy_rate`, `bb_sdf`, `bb_slf`) the
  editor drops, and HARD-FAILS the publish if one is still absent after
  reconciliation; it also rejects any editor-returned metric with no
  counterpart in the raw builder output, closing an "invented tile" hole (a
  synthetic "Breadth" label existed in no builder, §06 `dse`, issues
  177-180). The tenors themselves are NOT protected and are NEVER
  re-injected by that mechanism — when they tile, it is only because the
  editor chose to KEEP them in its own output and the render cap (now gone)
  no longer cuts them off, the same as any other metric the editor decides
  to show. Whether the tenors should tile at all, or move to a separate
  never-tiled context feed, is an OPEN question for Adnan (domain call —
  sdf-diagnosis memo). Do NOT decide it unilaterally in code.

## 26. A cut-off Claude response continues in a NEW assistant message — read the STREAM, and never trust `num_turns` or `result` to tell you it happened

`run_max` calls the CLI with `--output-format stream-json --verbose` and stitches every `type: "assistant"` text block in arrival order (`_parse_cli_stdout` in `brief/claude/max_client.py`). This is load-bearing, not a style choice:

- **`--output-format json` loses data.** Its single `result` field holds only the FINAL assistant message. When the editor's payload crosses the model's per-response output cap it is cut mid-JSON and continues in a new message, so `result` is the *tail of the brief*. Do not switch back to `json` to "simplify".
- **64,000 output tokens is a HARD cap on `claude-opus-4-8`, not a default.** `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000` comes back 64,000. Raising the value buys nothing; there is no headroom to purchase. (v1.6.0 shipped a pin that set the value to what it already was.)
- **`num_turns` is NOT a truncation signal.** A cut-off-and-continued response is still ONE turn. Key cut-off detection on the number of assistant messages (`MaxCallResult.assistant_messages`).
- **Never gate a truncation alarm on `parsed is None`.** `_extract_json_object`'s preamble fallback will happily extract the first balanced `{…}` out of a tail — a lone section object — so parsing *appears* to succeed while the brief is gone. The rescue path masks the failure; the alarm must fire on the structural signal regardless of parse outcome.
- **`thinking` and the answer text share ONE `message.id` — never de-duplicate on the id alone.** With `--effort xhigh` (our pin) the CLI splits a single assistant message into TWO stream events with the same id: the `thinking` block first, the `text` block second. De-duplicating by id kept the thinking-only event and discarded the brief, leaving zero collected text — which silently dropped `_parse_cli_stdout` into its "no assistant text" fallback, i.e. the `result` field, i.e. exactly the data loss the stream parsing exists to prevent. De-duplicate on `(message.id, that event's text)` and count only text-bearing events. Verified live: two events, both `msg_011CdrRxd9KybSrDcRoVj6zx`, blocks `thinking` then `text`.
- **A fallback that hides a parsing bug is worse than no fallback.** The id-dedup defect was invisible for a week because on a non-truncated day the `result` field happens to hold the whole brief — the pipeline published normally and the alarm (`assistant_messages > 1`) could never fire from a count of zero.
- The `_dump_raw_on_failure` stash in `pipeline_v6.py` writes the STITCHED text to `logs/<label>_raw_<stamp>.txt` on any parse/schema failure. Keep it — it is the only reason issue #183 was diagnosed in twenty minutes rather than four hours.

Cost of getting this wrong: 5 failed publishes across 2026-07-31 (#181, three runs) and 2026-08-02 (#183, two runs), one merged no-op fix, and a silent alarm — then 2 more (#190 on 2026-08-08, #192 on 2026-08-09) after the stream fix shipped but never ran. See AGENT_LEARNINGS.md 2026-08-02 and 2026-08-09.

## 27. `metric_history_monthly` has NO live writer — treat it as an archive, and never date a derived figure by its freshest input

Two rules from the v1.6.3 macro repoint, both of which had already cost real issues.

**(a) UPDATED 2026-08-22 (audit #204 review round 1, H2): `metric_history_monthly` gained LIVE APPENDERS on 2026-08-08 and is no longer uniformly dead — official finals SHOULD be read from it where an appender exists.** This landmine originally said the table was dead: its newest period was 2026-05-01 (a 2023 backfill), nothing wrote it, and §03 Macro reading all 8 of its metrics from it shipped 155–183-day-old figures with no freshness signal firing. That changed in econdelta PRs #123/#124 (2026-08-08): EconDelta now runs append-only monthly appenders for `remittance_usd_mn_monthly`, `exports_usd_mn_monthly`, the CPI trio (`cpi_12m_avg_monthly` + the P-to-P pair), `gross_reserves_usd_bn_monthly` / `net_reserves_bpm6_usd_bn_monthly`, and the 8 govt yield tenors — confirmed by a same-day official-values backfill + republish of issue #191 (see AGENT_LEARNINGS.md 2026-08-08, "Four charts served 5-month-old data..."). The 2026-08-22 P0 honesty fixes (audit #204) repoint `remit.py` and `fx.py`'s exports/trade-gap reads onto these official finals instead of the daily "flash" series that used to substitute for them, and `macro.py`'s import cover onto the official `imports_usd_mn_monthly`.

**Verified against production, not just this incident record.** Orchestrator anon-key `curl` against `metric_history_monthly`, 2026-08-22 (recorded in PR #165's comment thread): `remittance_usd_mn_monthly` latest = 2858.68 @ 2026-07; `exports_usd_mn_monthly` latest = 4202.69 @ 2026-06; `imports_usd_mn_monthly` latest = 5826.2 @ 2026-03 — matching this landmine's figures exactly.

**Two ids are rate-limited by their SOURCE, not a dead appender — this is expected, not a bug.** `imports_usd_mn_monthly` trails several months behind reserves because BB publishes customs-cleared import data on its own multi-month lag; `macro.py`'s import-cover gate (4 months, review round 1 decision H1) and `fx.py`'s trade-gap gate (same calendar month only) are both built around this specific, known lag — see their docstrings. `exports_usd_mn_monthly`'s ongoing scrape beyond the initial backfill is parked research (EPB's portal is JS-rendered and hard to automate), so its freshest row can also sit behind even though the appender itself isn't dead.

**Do not point a NEW metric at this table without checking whether it has a live appender first** (`select=as_of&order=as_of.desc&limit=1` — if the newest row is recent, it's live; if it's stuck months back, treat it as archive-only until confirmed otherwise). `brief/builders/macro.py` has each metric declare its own source (`live_id` / `derive` / `archive_id`); copy that shape rather than reintroducing one hardcoded table for a whole section.

Three macro metrics still read it **on purpose**: REER (in no table, ever), CPI 12-month-average (a different published measure from the point-to-point series EconDelta collects — not derivable from it), and M2 YoY (needs 13 months of `broad_money`; 4 exist). Each needs a scraper in EconDelta, not a wiring change here. They are left reading the archive rather than blanked because `section_freshness` is worst-of, so their real age keeps §03 labelled `stale` — **that is load-bearing.** Blanking them or dropping them from the section would flip §03 to `fresh` and re-hide the problem. Delete an archive metric only when its live replacement lands.

**(b) A derived metric is only as current as its OLDEST input.** `_derive` in `macro.py` dates its result `min(as_of)` across inputs. Issue #184 printed *"REER at 102.78 keeping the taka dear as the peg eases to 123.82"* — a March index and that day's spot rate in one clause — because nothing anywhere recorded that the two were months apart. Dating a derivation by its freshest input recreates exactly that. A missing input or a `ZeroDivisionError` returns `None`; half a derivation is not a number.

**(c) Live-series history anchors are not yet trustworthy.** EconDelta restamps monthly concepts daily, so a row count is not a history — `food_inflation` is 37 rows carrying 6 distinct values across 3 months. `MIN_DATA_POINTS["monthly"]` is 6 *real periods*, so "lowest since…" computed over the live table would be counting restamps as observations. History facts stay on the archive metrics until the live series carry a year of genuine monthly points. (This also keeps the builder inside landmine #23 — the archive facts run on the separate `history_monthly` client.)

Live ids confirmed against production 2026-08-03: `food_inflation`, `non_food_inflation`, `private_sector_credit_yoy_pct`, `policy_rate_repo`, `general_inflation`, `gross_reserves_usd_bn`, `monthly_import`.

## 28. `mark_held_overs` reads two columns that do not exist — a shipped feature can be dead for months and look fine

`mark_held_overs` keys on `(section_slug, label)` from `metric_definitions` and reads `last_print_date`. Production's `metric_definitions` has **79 rows and 18 columns, and neither `section_slug` nor `last_print_date` is one of them.** Every lookup has missed since v1.2.0. Measured 2026-08-03: **0** of the last 1000 published metric rows carry `held_from`, **0** carry `next_print`. The "As of …" footer in `Section.tsx`, its `tb-held-footer` CSS, the `is-held-over` render branch and the `anySignal` diff-mode gate have all been live, correct, and unreachable the entire time.

Nothing surfaced it because a no-op that writes nothing looks identical to a no-op that had nothing to write: no exception, no log line, no failing test — the tests fed it a stub catalog that *did* have the columns. The footer's absence read as "no metric is held over today," which was plausible every single day.

Rules:
- **A pipeline stage that consults the catalog must be verified against the PRODUCTION table, not a fixture.** `select=*&limit=1` on the real table and read the keys back. A fixture proves your code works on the schema you imagined.
- **Prefer the metric's own fields over a catalog join.** `brief/vintage.py` computes the vintage from `as_of` + `cadence`, which the builder already set. Nothing to migrate, nothing to drift.
- **When a feature's whole output is "sometimes nothing", assert it produces something.** `stamp_vintages` returns a count and `pipeline_v6` logs `vintaged_metrics=%d` for exactly this reason: a run where that number is 0 across all sections is now visible in the journal.
- `stamp_vintages` runs after `mark_held_overs` and never overwrites it — if the catalog is ever fixed, the catalog's real last-print date wins over `as_of`, which only approximates it.

**It happened again within the hour.** v1.6.4 — the release that fixed the above — shipped a `vintage.next_print` field that was *also* unreachable by construction: a vintage only exists past the cadence's fresh threshold, and every fresh threshold is longer than that cadence's publication interval (monthly 35 vs 30, weekly 7 vs 7, quarterly 95 vs 91), so the computed "next print" was always already in the past. Two lessons, both cheap:

- **Run it against production before calling it done.** Green tests said nothing; one live run printed *"As of 2026-03-01 · next print Mar 2026"* and the bug was obvious in a glance. For any change to what the brief displays, execute the builder against real Supabase rows and read the output as a reader would.
- **An `or` in an assertion is a smell.** The v1.6.4 test read `assert next_print == "Mar 2026" or next_print == "Apr 2026"` — written that way because the correct answer wasn't obvious, which is exactly the moment to stop and work it out rather than widen the assertion until it passes. It accepted the broken value on the first run.

## 29. A metric wired to an id nobody writes is invisible — and it fakes a "warming up" badge

Three ids shipped inside live sections and had **never had a single row**, in `metric_history` or `metric_history_monthly`, since the tables existed: `fiscal_nbr_target_trn`, `fiscal_adp_pct`, `remit_yoy_pct`. Removed in v1.6.6. A fourth, `comm_lng_jkm`, had 12 rows from a hand-run ingest, died 2026-04-20, and kept printing 15.00 USD/MMBtu for 105 days.

The blank tile was the harmless half. The damage was to the badge: `value is None` scores "unavailable", and `section_freshness` promotes that to **"warming_up"** for the five `SECTIONS_WITHOUT_LEGACY_BACKFILL` sections. So `fiscal` and `remit` told every reader that data was accumulating and would arrive shortly — for ids with nothing behind them, indefinitely. Both read "fresh" once the dead metrics were unwired, which is what their live numbers had been all along.

Rules:
- **Before adding a metric to a builder, confirm the id has rows.** `metric_history?select=as_of,value&metric_id=eq.<id>&limit=1`. A builder is a *reader*; wiring one up does not cause anything to write.
- **"warming_up" is a promise with a deadline.** It means "history is accumulating, expect this to resolve in ~7 runs". If a section has worn it for months, the cause is a dead id, not a slow one — go and check rather than assume the backfill is still catching up.
- **Repoint, don't just re-source.** `comm_lng_jkm` (JKM spot marker) and `lng_price_usd_mmbtu` (Pink Sheet's Japan *import* price) are different numbers. When you move a tile to a new series, the label and `source` move with it, or you have printed one market's price under another market's name.
- **Related, and NOT yet fixed:** a **future-dated `as_of` reads as "fresh"** and gets no vintage — every branch of `metric_freshness` computes `today - as_of` and compares upward, so a negative age lands in the first bucket. EconDelta writes IMF projections dated 2027–2031 into `debt_gdp_ratio` (an actuals id, ingested 2026-08-02). No Brief builder reads that id today, which is the only reason it has not printed a 2031 forecast as this morning's number. Note that some future stamps are legitimate — the Pink Sheet stamps `as_of` at the reporting month's last day — so the fix is a per-cadence tolerance, not a blanket rejection.

## 30. Retiring a section means four deletions, and the map entry is the one that matters

v1.6.7 removed **Commodities** (`comm`). It had two tiles: LNG, whose only source had frozen for 105 days before v1.6.6 repointed it, and Gold, which moved into `fx` as a reserve asset. A one-tile section is not a section.

Removing a builder file is the easy part. Four things have to go, and they fail differently:

1. **`brief/builders/<id>.py`** — delete it. Anything still importing it fails at *collection*, which is loud and fine.
2. **`SPINE_BUILDER_IDS`** in `brief/builders/__init__.py` — miss this and `gather()` tries to import a module that is gone.
3. **`V5_TO_V6`** in `brief/pipeline_v6.py` — this is the quiet one. The map is the gate: `_to_v6_raw` drops any `SectionData` whose id it does not know, and forwards any id it does. A stale entry reserves an ord and a group for a section that can no longer be built; a missing entry silently discards a section that still is.
4. **The retired ord.** Leave the number unused; do not renumber the survivors. Ords only have to sort. Reusing a retired slot re-homes some future section into the dead one's position, and nothing will flag it.

Rules:
- **Moving a tile between sections is not free — check the destination's tile budget first.** The editor prompt caps a section at 5 metrics and *chooses* which to drop. Gold moved into an `fx` that already held 6, so it would have been landing in a section with no room. Two tiles left to make space: EUR/BDT (the one the editor was already discarding) and `fx_monthly_remittance`, which printed 2.82 bn USD while §11 printed the same BB figure as 2820.0 mn USD — one number, twice, under one label.
- **Carry the disappearance signal with the tile.** `comm`'s badge went "unavailable" when the snapshot stopped carrying `gold_usd_oz`. `fx` computes its badge from spot rates only, deliberately, so Gold had to be added to `badge_metrics` explicitly. Drop that step and Gold could vanish for months under a green badge — which is exactly how LNG survived 105 days.

**Correction (v1.6.8).** The first draft of this landmine said `dam` was "in the second state" — built daily and dropped by the map. That was wrong, and the mistake is instructive enough to leave on the record. `dam` was never in `ALL_BUILDER_IDS`, and `gather()` iterates exactly that tuple, so `brief/builders/dam.py` was never imported and its nine metrics were never built. **Check the registry before the map.** A file in `brief/builders/` is not evidence that anything runs it; the tuple in `__init__.py` is the only thing that decides.

## 31. A dormant builder file is not harmless — it lies to the next reader, and it can leave live entries behind

`brief/builders/dam.py` (DAM Food Prices, nine items) shipped in the original 9-builder batch, was never registered, and sat unimported for months. Deleted in v1.6.8.

The cost was not runtime — there was none. It was that the file existed, looked complete, and made a section that had never once run appear to be part of the product. It cost real diagnostic time twice, including an incorrect finding published to the owner.

Worse, it had left a live entry behind it. `SECTIONS_WITHOUT_LEGACY_BACKFILL` in `brief/cadence.py` still listed `"dam"`. That set promotes an "unavailable" badge to **"warming_up"** — "history is accumulating, expect this shortly" — a promise made on behalf of a section that could not exist and so could never be kept. Nothing anywhere would have reported that.

Rules:
- **`ls brief/builders/` is not the section list. `ALL_BUILDER_IDS` is.** Before reasoning about what a builder does in production, confirm something actually calls it.
- **When you delete a builder, grep the id across `brief/` — not just the registry and the map.** Freshness sets, cadence overrides, validator allowlists and chart-series maps all key off section ids and none of them fail loudly on a stale entry. A test now pins that every id in `SECTIONS_WITHOUT_LEGACY_BACKFILL` is a buildable section.
- **Deleting a reader does not delete the data.** EconDelta still collects these prices; The Brief simply stopped carrying a tile for them. If Food Prices is ever wanted, it comes back as a new builder against live data — not by reviving this file, whose nine ids had been frozen at identical values for 92 days.

## 32. The publish time is coupled to EconDelta's aggregate — moving either one alone silently ages the brief

`brief.timer` fires **08:00 BDT (02:00 UTC)**, moved from 06:30 in v1.6.9. The number is not a preference; it is downstream of when EconDelta finishes writing `metric_history`.

Before the move, the ordering was inverted and nobody noticed: The Brief fired at 06:30 BDT while EconDelta's `aggregate_latest` stage ran at **13:00 BDT**. Every brief was therefore built on an aggregate that was **~17 hours old** — yesterday afternoon's. A fix landed in EconDelta in the morning could not reach the next morning's issue; it had to wait a full extra day. The two schedules were set years apart by different changes and were never checked against each other.

EconDelta now fetches from ~01:30 BDT and its aggregate lands ~02:55 BDT, roughly five hours ahead of this pipeline.

Rules:
- **These two schedules are one schedule.** Changing `brief.timer` here, or any `econdelta-*.timer` in the other repo, means re-checking the other side. Neither repo's tests can see the other, so nothing will fail.
- **EconDelta's parse stage must stay out of ~05:00–06:00 BDT.** That window is 16:00–17:00 US Pacific, Anthropic's peak; the LLM parse preflight failed 12 consecutive times there in May 2026. This is the real constraint on how late the chain can start, and therefore on how early this brief can fire.
- **The publish time is printed to readers.** `SubscribeCTA.tsx` states it three times and `Master.md` fixes the phrasing. A timer change that skips the copy leaves the signup box promising subscribers a delivery time they will not get.

## 33. A same-day republish REPLACES the day's issue in place; an off-schedule run on any other day mints a new issue — the same command does both

`python -m brief.cli run --publish --no-notify` (env: `set -a && . /etc/brief.env && set +a` — NOT a repo-local `.env`) behaves differently depending on whether an issue already exists for the current `brief_date`:

- **Same day as an existing published issue:** `v6_publisher` deletes that `issue_no`'s rows and re-inserts under the SAME number (verified 2026-08-08 23:38 BDT: the 08:00 BDT auto-publish had minted #191; the evening republish logged `deleting existing rows for issue_no=191` and re-published #191 in place). No issue-count inflation, nobody emailed.
- **Any other day (missed fire, next-day correction):** it computes max+1 and mints a NEW issue (the #189/#190 double-issue incident, AGENT_LEARNINGS 2026-08-08).

So "re-run today's publish to pick up fresh chart data" is safe and idempotent on issue numbering — but do not assume that safety extends past midnight BDT, and never use bare `systemctl start brief.service` for either case (it re-emails every subscriber; landmine 3's mechanism). See AGENT_LEARNINGS.md 2026-08-08 (both entries).

## 34. The post-editor number/period validator (`brief/validators/prose_numbers.py`) checks prose against the BUILDER's raw values, never the editor's own formatted string — `check_count_claims` is the only UNCONDITIONAL BLOCK, and since 2026-08-28 the hyphenated-attributive family BLOCKS too, scoped to `_HYPHENATED_COUNT_BLOCK_SLUGS`

P2 fact-checker (2026-08-22 audit #204). Two engineering reviews shaped this, both on real corpus evidence:

Round 1 rejected the first cut outright: "prose-vs-payload would have passed every wrong number because the payload itself carries them — validate against the BUILDER/source values." Every check therefore reads `sections_raw` (pre-editor, deterministic) as ground truth, never `MetricV6.value` in isolation.

**Round 2 rejected round 1's BLOCK scope after replaying it against 25 real published issues (#180–#204): 25/25 would have held the publish, 527 BLOCK hits, only 3 true positives (0.6% precision) — while 3 of the 5 audit falsehoods passed UNCAUGHT, because the number check only ever read `sub`, never the metric's own headline `value` (where the "$2.82bn" falsehood actually lived).** The reshape below is round 2's verdict:

- **BLOCK** (hard-fails via `ProseNumberGateError`, a `V6PublishError` — exit code 4, same as the denylist check) — **`check_count_claims` ONLY.** A sourceless `"across/for/in N reads/prints"` count-claim anywhere in the brief's prose (the pipeline never supplies a count field) — a TRIPWIRE on the common surface forms, not an exhaustive ban: the reviewer confirmed "for twelve reads" ("twelve" doesn't end in "teen"/"ty") and "through fourteen reads" ("through" isn't in the preposition list) both pass uncaught. Corpus-verified: **17 true positives across 9 issues (#184, #197–#204)** — 16 in fiscal sections across #197–#204, plus one in issue #184's `fx.chart_read.context` ("held 122.85 for fourteen prints") — 0 false positives, once the noun list was narrowed to `(reads|prints)` — "days" and "sessions" contributed zero true positives and a real false positive ("BB hasn't published reserves in 14 days" — a plain duration statement, not an invented observation count; see `AGENT_LEARNINGS.md`'s round-2 entry).
- **BLOCK, SCOPED** (added 2026-08-28, **owner-approved** — same `ProseNumberGateError`, same exit code 4) — **`check_hyphenated_count_claims`, and only where THREE conditions all hold: the section slug is in `_HYPHENATED_COUNT_BLOCK_SLUGS` (today: `dse`), the claimed count parses to a number, and the claim wears a shape the supply side can answer (`_is_blockable_shape` — `session`/`print`/`read` + "low").** The hyphenated ATTRIBUTIVE shape ("a ten-session low") is the same invented-count defect wearing a different surface; it shipped WARN-only from PR #175 and printed BYTE-IDENTICAL across issues 205, 206, 207 and 208 while the real rank ran 38 → 41 → 42. Two things make `dse` — and only `dse` — block-worthy: those four fabricated editions are on the record, and since PR #185 the pipeline FEEDS that section a real machine-computed rank (`pipeline_v6._dsex_session_low_fact`, riding the history-facts-verbatim contract into `sections_raw[].history_facts`). **A claim is LEGITIMATE when it matches a builder value or a machine-fed history-fact count** — the check parses the rank out of each fact's own `phrase` with the same regex it matches claims by (`HistoryFact` carries no rank field), and compares NUMERICALLY, so a word-form claim including an English compound ("a forty-two-session low", captured whole, not as its tail "two") clears a digit fact (42). Unmatched in a block slug = fabrication by construction = publish held; unmatched anywhere else = WARN, because no other section has a sourced count to have used instead.
  - **Why the shape narrowing is not a hedge.** `_dsex_session_low_fact` emits a `since_lower` rank and nothing else, so a HIGH/STREAK/RUN claim has no possible sourced counterpart — blocking one holds the publish on a sentence an honest editor cannot rewrite. DAY and WEEK forms are ordinary derivable market prose ("a 52-week low" is computable from any price series). Before the narrowing, "a 52-week low", "a five-session high" and "a three-day run of declines" each held the publish through the real gate. Narrowing keeps **13/13 real true positives across #205–#208** (all session-lows) and deletes the whole legitimate-phrase false-block surface.
  - **Two more deliberate limits:** no tolerance on an integer rank (a "40-session low" against a true 42 blocks — a rank is a count, not a measurement), and a count slot naming no number ("a multi-session low") warns rather than holding an 08:00 publish.
  - **ACCEPTED RISK — the two sides fail in opposite directions.** The fact SUPPLY fails open (`_fetch_series_summaries` swallows a fetch failure and yields no facts, so the editor still runs), while the CLAIM now fails closed. A transient Supabase hiccup plus a habitual phrase is therefore a held edition. Bounded by how often a fact exists at all: ~31% of mornings on the real series (63.1% of days the rank is under `LOOKBACK_MIN`, 5.5% are window lows — both suppress the fact by design, and on those mornings there is no honest rank to print either). Traded knowingly: a held publish is visible and recoverable, four editions of a fabricated figure were neither.
  - **Adding a slug** requires that section to have its OWN machine-fed count. `bb` and `tbond` are NOT candidates despite looking similar — their prose is dense with instrument names wearing this exact shape ("the 14-day call money rate", "the 91-day T-Bill"), counted 25 times across 15 real issues. `tests/validators/test_prose_numbers.py::test_the_block_scope_is_exactly_dse` pins the frozenset so growth is deliberate, and `test_the_real_producers_phrase_round_trips_into_the_extractor` chains the producer's phrasing to the extractor so a reworded fact ("a 42-session closing low") fails a test instead of silently holding every honest morning.
- **WARN** (logged, then batched into ONE Discord alert per publish grouped by section — never one message per warning) — everything else: `check_metric_sub_numbers` and `check_metric_sub_periods` (the round-1 checks, demoted), `check_metric_value_vs_raw` (NEW — compares a published metric's own headline `value` against the SAME `(section, label)` raw value; this is the check that would have caught "$2.82bn", since it lived in `value`, not `sub`), and `check_lede_numbers_against_builder_values` (extended to `banker_read.*` and `chart_read.*` on top of `todays_call`/`tldr`/`verdict`/`analysis`). `BRIEF_PROSE_VALIDATOR_STRICT=1` upgrades ALL of these to the same hard-fail — a documented FUTURE flip, not this PR's default, and only once production WARN-log volume proves a near-zero real false-positive rate the way the count-claim check's corpus replay already did (WARN volume in the #199–#204 golden-corpus tests runs 79–112 per issue with the extended banker_read/chart_read surface — expected under "warn-first, tighten later", not yet flip-ready).

Every currency/percent/bp figure must trace to that section's raw values (its own, a sibling's, or a pairwise `|a−b|` derived delta, e.g. "19bp under the 9.50% policy") within tolerance = half a unit in the LAST PRINTED DIGIT of the prose token (an integer "733" tolerates ±0.5, "9.50" tolerates ±0.005) — with two corpus-driven refinements: a `~` approximation marker widens this to a FULL unit ("~8bp" accepts a precise 8.6bp), and for CURRENCY tokens only the tolerance is floored at 0.5% and capped at 1% of the matched value (a coarse "$3bn" no longer gets a free pass against a true 2.86bn just because its own half-ulp is wide). Every month-name token in a `sub` must equal that metric's own data period or a same-section sibling's, sourced from `as_of` — **except event-cadence metrics** (the BB policy corridor AND the three T-Bill cut-off rates in `tbond.py` — any metric with `cadence="event"`, landmine 24), whose `as_of` is a daily restamp date, not a decision date, so a sub naming the real decision/auction month ("held since the 30 Jul cut") is exempted entirely — and except the macro Import Cover metric's machine-stamped dual-period note (`pipeline_v6._stamp_import_cover_sub`), detected via the raw metric's own `source` marker (not its label), since it legitimately names two different months by construction.

Numbers with no currency symbol and no recognized unit suffix (`%`/`bp`/`bn`/`mn`/`cr`/`trn`/`tn`) are skipped entirely — a bare digit is far more often a year, an ordinal, or an unrelated count than a value assertion, and precision matters more than recall here. `"BDT trn"` (the real `fiscal.py` unit string) is a distinct key from `"tn"` — `"trn"` does not contain `"tn"` as a substring, so missing it was a real round-2 corpus defect, not a hypothetical. Negative figures use Master.md's minus GLYPH (−, U+2212), captured separately from the ASCII hyphen and the em-dash (—, U+2014) sentence separator so none of the three collide.

`period` is a field on every raw metric in `sections_raw[].metrics[]` (`brief/vintage.py`'s `period_label`, exported publicly for this), always present — unlike `vintage`, which only exists past a metric's fresh threshold. `series_summary` is a per-section field (n/first_ts/first_value/last_ts/last_value/min/max, built by `pipeline_v6._fetch_series_summaries`) fixing the prior lie that the editor's raw input carried a chart's actual `series`/`notes` — it never did; those are stamped onto the FINAL brief post-editor (`_stamp_chart_series`, unmoved, unchanged, deliberately NOT sharing a fetch with the pre-editor digest — chart data can legitimately move in the ~10-15 minutes between the two calls, and reusing a stale pre-editor fetch for the published chart would trade one honesty bug for another) for payload-size reasons. `chart_read` must derive only from `series_summary`.

Golden-corpus regression tests live at `tests/validators/test_prose_numbers_golden_corpus.py`, built from the REAL published rows for issues #199–#204 (`tests/fixtures/real_issues/`) — not synthetic data.

## 35. A snapshot value is dated by the SESSION, never by `ctx.today` — DSE opens 10:00 BDT, and the brief fires before that

Issue 206 (2026-08-24). EconDelta's snapshot dict (`brief/econdelta.py`, `EconDeltaSnapshot.data`) is a flat key→value map with NO per-key session date, so a builder that stamps `as_of = ctx.today` on every fresh value dates the number by when the pipeline RAN, not by the trading session it actually describes. The brief publishes at 08:00 BDT (landmine 32) — DSE's own session does not open until 10:00 BDT — so on the fresh branch `ctx.today` is **never** a valid session date, not even on an ordinary trading day. `brief/builders/dse.py`'s fresh branch printed "24 Aug 2026" for a snapshot that still held the 23 Aug close, while the same section's `chart_read` (driven by `series_summary.last_ts`, a real session date) correctly said 23 Aug — two contradictory dates in one section, and nothing anywhere checked that they agreed.

Fixed in `dse.py`: resolve `as_of` from `ctx.history.get_latest(src_key).as_of` when the history row's VALUE matches the snapshot value (same confirmed session); otherwise fall back to the last BD trading day strictly before `ctx.today` (`brief.cadence.is_bd_trading_day`) — never the run date itself. A new WARN-mode tripwire (`pipeline_v6._check_daily_as_of_vs_series_summary`) also flags any daily metric whose `as_of` disagrees with its own section's chart-series `last_ts`, as a backstop that would have caught this even without the root-cause fix.

**OPEN follow-up, not yet fixed:** the identical pattern — `as_of = ctx.today` on a fresh snapshot read, no per-key session date available to check against — still lives in `brief/builders/iranwar.py` (Brent), `brief/builders/fx.py` (USD/BDT spot, gold), `brief/builders/bb.py` (reserves), and `brief/builders/headlines.py`. None of these were touched by this fix; each needs its own root-cause check (does the source actually carry a session/publish date the builder could read instead of stamping the clock?) before applying the same repoint. Do not assume the same fix mechanically transplants — dse.py's fix works because `ctx.history` carries a real per-session `as_of` for the SAME src_key; confirm that precondition holds for each sibling before repeating the pattern.

## 36. Next.js re-creates the viewport `<meta>` nodes on every client navigation — a runtime meta mutation must be root-mounted, pre-paint-stamped, and head-observed

v2.4.0's per-theme `theme-color` first shipped as a `useEffect` inside ClientApp that `setAttribute`'d the two metas. Adversarially refuted before merge, with the mechanism read from `node_modules`: the App Router renders the Viewport head element with a per-request key, so every client navigation unmounts and re-mounts the `<meta name="theme-color">` nodes with their STATIC media-pair content — the mutation dies on the first `<Link>` click, and routes that never mount ClientApp (`/archive`) never get it at all. React's effect-destruction order also ran the useTheme observer teardown BEFORE ClientApp's print-restore, so a dark user exiting `?print=1` kept light chrome.

The shipped shape (copy it for any future runtime `<head>` mutation):
1. **Pre-paint stamp in the FOUC inline script** (`app/layout.tsx`) — the metas parse before the script in the served HTML (verified), so hard loads on EVERY route are correct before first paint; a `DOMContentLoaded` fallback covers ordering drift.
2. **A root-layout client component** (`app/components/ThemeColorSync.tsx`) — exists on every route, re-applies on `useTheme` + `usePathname` changes, and holds a `MutationObserver` on `document.head` (guarded: only write when the content differs, or the observer loops) to catch Next swapping the nodes mid-session.

Verify all three scenarios when touching this: hard-load `/archive` with the toggle diverging from the OS; client-nav `/` → `/archive`; `?print=1` from dark, then navigate away. The three theme-color hexes (viewport pair, FOUC stamp, ThemeColorSync) must stay in sync with `--paper`/`--band` — Design.md's raw-hex carve-out names all three sites.

## 37. `content/long-view.ts` is CONTENDED — another session can replace or rewrite the live pin mid-day, so fetch and re-read before any pin edit or judgment

The pin is written by whichever session the owner happens to speak to — local terminals and Copotron via Discord both ship pin PRs. Two collisions inside 24 hours (28–29 Aug 2026): PR #195's prose touch-up died unmerged because Copotron merged a NEW pin (#191) mid-wave; the next day, a queued voice pass on #191 turned out moot because an owner-requested trim (#202, merged 12:30 BDT) had already rewritten the prose under the synced register. Before judging or editing the pin: `git fetch origin` then `git log origin/main -- content/long-view.ts`, pull, and read the CURRENT text — never work from a cached read or a previous session's description of it. The recipe and Master.md register travel with the repo, so any session's rewrite inherits the rules; verify what is actually live, not what you remember shipping.

## 38. When several sections flip stale on the same day, check EconDelta's aggregate FIRST — a hard reject freezes every aggregate-written id at once while the brief keeps publishing, and the log names the wrong culprit

31 Aug–2 Sep 2026: EconDelta's `aggregate_latest` exited 1 on all 9 fires (02:55 BDT plus the two `Restart=on-failure` re-runs at ~03:01/~03:07) with `opus review REJECTED (hard): … missing=[treasury_bill_outstanding, …] — keeping yesterday's latest.json`. Nothing was written to `metric_history` after 30 Aug 03:16 BDT, so `dsex`, `dommr`/`bofr`, `usd_bdt_*`, `call_money_*`, `policy_rate_*`, the food prices — every id the aggregate owns — froze at as_of 27–30 Aug together, while `dse_close_*` (the separate `dse_dayend` scraper) kept flowing. The Brief noticed nothing: issues 213–215 published on time with honest `stale` badges (7/10 sections on #215), and the publish gate does not block on a stuck upstream. Three things to know before you diagnose:

1. **"REJECTED (hard) … missing=[ids]" means a DEAD SOURCE, not a reviewer problem.** The Opus reviewer had been soft-rejecting the same anomalies for a week with the upsert still landing. The escalation to hard reject is a deterministic rule in `_quarantine_flagged`: any flagged id absent from `data` ⇒ `hard_reject`. Here BB had moved its `gsom.bb.org.bd` treasury pages around 1 Jul; `parse_all` masked the 404 with a 60-day `stale_fallback` that expired on 31 Aug. Tuning the reviewer would not have fixed it. Fixes: econdelta #133 (URL repoint) + #134 (fiscal-year-reset guard for the "collapsed ~90%" half) — and those two were NOT enough. On 3 Sep the 02:55 BDT run only "passed" because the Opus review itself was skipped (`opus review involuntarily skipped: claude_exit_1`) and the upsert went through unreviewed; the 03:16 retry then hard-rejected again on `treasury_bill_outstanding`. econdelta #135 (guard hardening) + #136 (fetch the gsom page for an EXPLICIT date and alarm on stale holdovers) closed it the same day; first clean reviewed fire 4 Sep 02:56 BDT (146 rows). A "fix merged" is not a "feed recovered" — read the next morning's `run_logs` row before calling it done.
2. **Where to look, in order:** Supabase `run_logs?source=eq.aggregate&order=started_at.desc` (anon-readable; `status`, `exit_code`, `error` tail) → ExonVPS `~/econdelta/logs/aggregate-systemd.log{,.1,.N.gz}` (`journalctl` is not readable for `adnan-local`) → `metric_history` max(`as_of`) per id (landmine #6's method). Then confirm the fix is actually ON THE BOX: `git log -1` there vs `origin/main` — the 01:00 BDT `econdelta-gitpull.timer` is the only deploy path and it runs `--ff-only`.
3. **The 03:15 BDT `econdelta-aggregate-retry.timer` is a no-op on exactly the nights it matters.** The on-failure restarts already spend `StartLimitBurst=3`, so the 03:15 start is refused (no log line, no `run_logs` row). Do not read "the retry also failed" into its silence, and do not expect it to rescue a rejecting night. On a night the 02:55 run SUCCEEDS the burst is unspent, so the 03:15 timer fires and runs the aggregate a second time (4 Sep 2026: OK at 02:56 and again at 03:16, same 146-row upsert) — two `run_logs` rows on a good night is the timer doing its job, not a double-write bug.

Landmine #32 says the two schedules are one schedule; this is the failure mode of that coupling. See the 2026-09-02 health-review session note.

## Communication & timezone

- **All times in BDT (UTC+6).** When generating timestamps, dates, or schedules, convert to BDT and label it.
- **Plain-English explanations** of technical terms in conversation, even obvious ones. Adnan reads but doesn't write code.
- **No emojis** in code or commits unless explicitly requested.
- **Short, scannable updates** — Adnan reads on mobile often.

## Out-of-scope behaviors

Do not, without explicit user sign-off:

- Edit Master.md, Design.md, `docs/longview-workflow.md` — these are CONTRACT files Claude reads. Sign-off required.
- Add new dependencies in `package.json` or `requirements.txt`.
- Bump `next`, `react`, `chart.js`, `@supabase/supabase-js` beyond patch versions.
- Modify CHANGELOG.md historical entries (anything below the current pending-release section).
- Run `git push origin v*` (tag pushes typically trigger releases).
- Run `git push --force` against any branch.
- Skip hooks (`--no-verify`, `--no-gpg-sign`, etc.).
- Touch `vercel.json` or `.github/workflows/` without explaining the change in the PR description.
- Touch `migrations/` SQL files without confirming the migration target environment (local vs production Supabase).
- Touch `brief/claude/prompts/*.txt` prompt content (editor_v6, editor_v6_friday, subeditor_v6 — the mega-prompts; the old `brief/claude/*.py` wording predated the prompts moving to `.txt` files); tweaks change the voice of every brief.

For everything else, see `VISION.md` for what auto-merges vs needs sign-off.

## Cross-cutting rules

Adnan's global rules live in `~/.claude/CLAUDE.md` (loaded automatically by Claude Code). When that file conflicts with this one, this file wins because it's project-specific.

For history of past incidents and the rules derived from them, see `AGENT_LEARNINGS.md`.
