# The Brief — Claude operating notes

Daily Bangladesh-economy banking-style brief for senior banking professionals at Tier-1 banks. Next.js 16 SPA + Python pipeline + Supabase. Owner: Adnan (vibe-coder; he directs AI agents — do not assume he reads code, do not skip plain-English explanations).

## Read these first

| File | What it covers |
|---|---|
| [`AGENTS.md`](./AGENTS.md) | Build / test / release commands, repo structure, **29 numbered landmines**. Required before any code change. |
| [`VISION.md`](./VISION.md) | What auto-merges vs needs sign-off. Required before opening a PR that changes user-visible behavior. |
| [`AGENT_LEARNINGS.md`](./AGENT_LEARNINGS.md) | Past incidents and the rules that came out of them. Read when something feels load-bearing. |
| [`Master.md`](./Master.md) | Voice, audience, copy conventions. Read before generating prose, headlines, or Long View text. |
| [`Design.md`](./Design.md) | Visual language, palette tokens, block kinds. Read before touching CSS or a component in `app/components/`. |

## Special workflows

- **Long View uploads** — when a user uploads a PDF or JPEG along with the word `longview` (in Discord via Copotron, or in a local terminal session), read [`docs/longview-workflow.md`](./docs/longview-workflow.md) and follow it exactly. Do not improvise the schema or workflow — the recipe is the contract. The Long View is a pinned editorial section between Overview and Banking on the SPA; replaced by editing `content/long-view.ts` and shipping via a Vercel-previewed PR to `main`.
- **Daily auto-fire** — the daily publish runs as `brief.service` on Hetzner (systemd timer), NOT GitHub Actions. The V1 cron was retired in PR #57. Manual fire pattern lives in the README's Operations section.

## Cross-cutting rules

Adnan's global rules live in `~/.claude/CLAUDE.md` (loaded automatically by Claude Code). When that file conflicts with this one or `AGENTS.md`, project-specific rules win.

No `Co-Authored-By: Claude` trailer in commits (attribution is disabled globally). Conventional Commits format. Times in BDT (UTC+6). Plain-English explanations for every technical term.
