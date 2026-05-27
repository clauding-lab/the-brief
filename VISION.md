# Vision

The Brief is a daily Bangladesh-economy banking-style brief for senior banking professionals at Tier-1 banks. It should keep delivering a clinical, fact-based 06:30 BDT read — concise enough to scan in ~15 minutes, deep enough to drive desk decisions — while preserving its voice (Master.md), its visual identity (Design.md), and the integrity of its data pipeline (EconDelta → Supabase → SPA + email).

The rules below scope what AI agents and contributors can ship without explicit sign-off.

## Merge by Default

- **Bug fixes** with a clear cause and bounded blast radius (single section, single block kind, single API endpoint).
- **Documentation, README, CHANGELOG** (pending-release section only), code-comment fixes.
- **Small UI/UX tweaks** that don't change layout, copy, or behavior materially — spacing, hover states, focus rings, single-class color tweaks.
- **New tests**, including coverage for existing code. Test-only PRs are always welcome.
- **Logging additions and small observability improvements** in `brief/` Python code.
- **Extensions to existing patterns** that follow the established shape — adding a new `metric_id` to `chart_series_fetcher.py`, adding a section to an existing builder, adding a fixture file.
- **Internal refactors** confined to a single module that don't change the external surface and keep tests green.
- **Dependency patch-version bumps** in `package.json` — *except* `next`, `react`, `chart.js`, `@supabase/supabase-js`, which need scrutiny even on patches.
- **Long View content PRs** that follow the schema and the visual contract in Master.md / Design.md / `docs/longview-workflow.md`. The recipe is the contract; following it is auto-merge.

## Needs Sign-Off

- **New features** — any change to user-visible behavior beyond a bug fix.
- **New Long View block kinds** — the 5 in v1.3.0 are exhaustive by design. A 6th needs a version bump and a design review.
- **New sections in the brief** — adding a `group_key`, a builder, a Supabase table, or a render component.
- **Pipeline architecture** — `brief/pipeline.py`, `brief/pipeline_v6.py`, `brief/v6_publisher.py`, `brief/v6_schema.py`, the editor/sub-editor split.
- **Anthropic prompt edits** — `brief/claude/*.py` mega-prompts (editor, sub-editor, lens-scorer). The voice of every brief depends on these.
- **Notifier / email-delivery changes** — `brief/notifier.py`, Brevo template, subscriber data flow. Privacy-impacting; see AGENTS.md landmine #3.
- **Master.md, Design.md, `docs/longview-workflow.md`** — these are CONTRACT files that Claude reads when composing pins. Editing them shifts what every future Long View looks and sounds like.
- **Dependency additions** in `package.json` or `requirements.txt`.
- **Dependency minor or major bumps**, and any bump of: `next`, `react`, `chart.js`, `@supabase/supabase-js`, `@supabase/ssr`, `anthropic` SDKs.
- **Toolchain / runtime version changes** — Node version, Python version, Next.js major.
- **Broad refactors** spanning >1 module or touching a public boundary (RPC contract, Supabase schema, types in `types/brief.ts`).
- **Architectural changes** — new dirs at repo root, new build steps, new long-running processes.
- **Release pipeline edits** — `vercel.json`, `.github/workflows/*`, signing config.
- **Supabase migrations in `migrations/`** — schema changes apply to production data. Migrations need a target-environment check before apply.
- **Auth / RLS changes** — Supabase policies that govern who can read briefs or subscribe.
- **Hetzner `brief.service` config** — `/etc/systemd/system/brief.{service,timer}`, `/etc/brief.env`. Changes affect the daily auto-fire.
- **Privacy-impacting changes** — telemetry, network destinations, data storage locations, log content. The notifier privacy fix (PR #83) is the reference case.
- **Anything that requires editing CHANGELOG.md historical entries** (below the pending-release section).

## When in doubt

If a change could conceivably surprise the user, ask first. Cost of one extra question << cost of one bad surprise. Specifically for The Brief: if the change touches what readers see in tomorrow morning's brief, ask. If it touches what subscribers receive in tomorrow's email, ask twice.
