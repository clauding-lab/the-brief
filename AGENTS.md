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
  claude/             Anthropic API wrappers (editor + sub-editor + lens-scorer)
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
- **Chart series IDs:** `brief/chart_series_fetcher.py` reads from Supabase `metric_history`. Live IDs: `brent_crude_usd_barrel`, `dsex`, `tbond_bond_5y`, `tbond_bond_10y`, `tbill_91d_yield_pct`, `tbill_182d_yield`, `tbill_364d_yield`. `comm_lng_jkm` exists but has no scraper. See landmine #6 for the "legacy vs live" map.
- **Section ordering:** sections render in `group_key` order. Group dividers and stale collapsing are in `app/components/ClientApp.tsx`. Each section carries `freshness` and `pills` populated by the pipeline.
- **Editor / sub-editor split:** the Python pipeline uses two Claude calls per brief — an "editor" mega-prompt that drafts, then a "sub-editor" self-review that returns a `pass | fail` verdict. The editor is in `brief/claude/editor.py`; the sub-editor is in `brief/claude/subeditor.py`. Exit code `4` means the sub-editor failed.
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

17. **Chart series render from the PUBLISHED brief, not live `metric_history` — a chart re-point deployed AFTER the day's 06:30 publish shows BLANK until the next publish.** The SPA reads each section's `series` from `get_latest_brief` (`app/page.tsx`); a config that newly reads different metric_ids (e.g. F3 `fxBalanceConfig`, F5 `yieldLadderConfig`) finds the OLD keys in the already-published brief, fails its `hasAnyData` guard, and renders empty. The Vercel preview uses a fixture with the NEW keys, so it looks fine even when prod is blank — ALWAYS verify the LIVE prod chart after a re-point deploy. Mitigate by deploying before the 06:30 BDT fire, planning a manual `brief.cli run --publish`, or flagging the blank-until-next-publish window. `brief.timer`: Mon–Fri + Sun 06:30 BDT (Saturday skipped). See AGENT_LEARNINGS.md 2026-05-31.

18. **A new `SectionV6` JSONB field ships WITH its migration in the same PR, and the migration is applied to prod BEFORE the code publishes — an agent CANNOT apply the DDL itself.** Adding a section field (e.g. `chart_read`, F4 `movers`) means a Pydantic model + a `migrations/000N_*.sql` (`ALTER TABLE public.sections ADD COLUMN IF NOT EXISTS <col> jsonb; COMMENT …; NOTIFY pgrst, 'reload schema';`) + leaving the field OUT of the publisher's child-table `exclude` set. There is **no programmatic DDL path** (no `psql`, no Supabase CLI, no service-role key locally, no `DATABASE_URL` on Hetzner; PostgREST can't run DDL) — hand Adnan the SQL for the Supabase SQL editor (`https://supabase.com/dashboard/project/<ref>/sql/new`), then verify the column with an anon SELECT (`/rest/v1/sections?select=<col>&limit=1` → HTTP 200) before merge/deploy. Skipping/mis-ordering the migration orphans the next brief with PGRST204 (Brief #118, `chart_read`). See AGENT_LEARNINGS.md 2026-05-29.

## 19. Library/framework API calls → Context7 first

Before writing or editing code that calls a third-party library or framework API,
query **Context7** for current, version-pinned docs — do NOT rely on training-cutoff memory.

- **Flow:** `resolve-library-id` (name → `/org/project` ID) → `query-docs` (PIN the version this repo ships, e.g. `/vercel/next.js/v16.2.4`).
- **Applies to:** `next` 16 (App Router, `app/`), `react` / `react-dom` 19, `@supabase/supabase-js` 2, `chart.js` 4 + `chartjs-adapter-date-fns` 3, `date-fns` 4 (SPA side); `anthropic` (Python SDK, `brief/claude/`) and `pydantic` 2 (pipeline side).
- **Skip for:** business/domain logic, general programming concepts, or libraries Context7 does not index.
- **Query specifically:** library + version + exact task (e.g. `chart.js 4 register CategoryScale for a bar chart` or `@supabase/supabase-js 2 select with in.() filter and limit`), never one-word topics like "auth".

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
- Touch `brief/claude/*.py` prompt content — these are the editor and sub-editor mega-prompts; tweaks change the voice of every brief.

For everything else, see `VISION.md` for what auto-merges vs needs sign-off.

## Cross-cutting rules

Adnan's global rules live in `~/.claude/CLAUDE.md` (loaded automatically by Claude Code). When that file conflicts with this one, this file wins because it's project-specific.

For history of past incidents and the rules derived from them, see `AGENT_LEARNINGS.md`.
