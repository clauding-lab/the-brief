# The Long View — workflow

This file is the contract for the Long View workflow on The Brief. It has two halves: **Editorial** (what to write) and **Operational** (how to ship it). Both halves must be followed for every Long View pin.

The Long View is a pinned editorial section that sits between the Overview group and the Banking group on The Brief's SPA. It replaces whatever was previously pinned. Posted at most once per week. Re-rendered in the brief's cream-paper editorial style from a source PDF or JPEG the editor uploads.

---

## Trigger

The user sends a Discord message to Copotron (Hetzner) OR types in their local Claude Code terminal session:

```
<attach PDF or JPEG>
longview
   — OR —
longview - <optional hint to steer your framing>
```

When you see this pattern, follow this entire workflow without improvising.

---

## Editorial half — what you write

### Audience

The Brief is read by banking professionals in Bangladesh — business heads (corporate, SME, retail), risk heads, and treasury heads at Tier-1 banks. Write for that reader.

### Voice register

- Banker-native vocabulary: NPL, CRR, repo, SDF, Sukuk, ALCO, MPS, BB (Bangladesh Bank), Tier-1 capital, provisioning, advance-deposit ratio.
- Concrete numbers; never round away precision the source provides.
- Implications oriented to credit committees, ALCO, treasury desks.
- No journalese ("amid", "in a stunning move", "moreover"), no LLM tells ("delve", "myriad", "tapestry"), no hedging when the source is clear.

### Output schema

Edit `content/long-view.ts` to look exactly like this (filling in your extracted data):

```typescript
import type { LongViewData } from "@/types/brief";

export const longView: LongViewData | null = {
  posted_at: "<ISO 8601 UTC timestamp, e.g. 2026-05-18T00:30:00Z — use now()>",
  title: "<5–10 words, no trailing punctuation>",
  lead: "<1–2 sentences setting up the insight>",
  body_paragraphs: [
    "<paragraph 1>",
    "<paragraph 2>",
    // 1–3 total; never more.
  ],
  chart_spec: null,  // v1.1.0: always null. v1.1.1: chart rendering ships.
  banker_read: "<1 paragraph; the takeaway for a banker reader>",
};
```

### Forbiddens

- **Do not fabricate numbers** not in the source. If the slide is unclear, say so in your reply to the user and stop.
- **Do not add a source-attribution field** (no "Source: BB MPS, May 2026" line). The spec explicitly excludes this.
- **Do not add a "view original" link.** The reader sees only the recreation.
- **Do not fold opinion into the lead.** Opinion lives in `banker_read`.
- **Do not emit a `chart_spec` other than `null` in v1.1.0.** If the source has a chart, describe its shape in `body_paragraphs` (e.g., "The slide shows cut-off yields falling from 8.95% to 8.57% across four auctions"). Chart rendering ships in v1.1.1.

---

## Operational half — how you ship it

### 0. Where to run this

- **On Hetzner (Copotron via Discord):** the repo lives at `/home/adnan/the-brief/`.
- **On the user's Mac (local Claude Code):** the repo lives at `~/Projects/clauding-lab/the-brief/` OR inside a Conductor workspace under `~/conductor/workspaces/the-brief/<name>/`. Confirm with `git rev-parse --show-toplevel` if unsure.

### 1. Save the source

Generate a UUID for the source file and save it:

```bash
UUID=$(python3 -c "import uuid; print(uuid.uuid4())")
EXT="<pdf or jpg, from the attachment>"
mkdir -p pins
# Move/copy the attachment to pins/$UUID.$EXT
```

Keep this file path — you may need to re-read it on a `redo`.

### 2. Branch off main

```bash
git fetch origin main
git checkout main
git pull
git checkout -b longview/<3-4-word-slug-from-your-read>
# Example: longview/sukuk-spread-deepdive
```

### 3. Read the source

Open the PDF or JPEG and extract per the Editorial half above. If a hint was provided after `longview - `, weight your framing toward it.

### 4. Edit `content/long-view.ts`

Replace the entire contents with the new `longView` export per the schema. Verify locally:

```bash
npx tsc --noEmit
```

### 5. Commit and push

```bash
git add content/long-view.ts
git commit -m "longview: <title in lowercase, ~10 words>"
git push -u origin longview/<your-slug>
```

### 6. Open a PR for the Vercel preview

```bash
gh pr create \
  --title "longview: <title>" \
  --body "Pinned Long View update. Preview will be ready shortly. Source kept at pins/$UUID.$EXT."
```

### 7. Wait for Vercel preview

```bash
gh pr checks --watch
gh pr view --json statusCheckRollup --jq '.statusCheckRollup[] | select(.context // .name | test("Vercel")) | .targetUrl // .detailsUrl' | head -1
```

Capture the preview URL — that's what you reply to the user with.

### 8. Reply to the user

Reply (via the Discord `reply` tool on Hetzner, or normal terminal output on Mac):

```
Draft ready.
Preview: <vercel-preview-url>
Reply with one of:
  publish
  redo: <new hint>
  cancel
```

### 9. Handle the user's response

**`publish`** — Merge to main:

```bash
gh pr merge <pr-number> --squash --delete-branch
```

Reply: `Merged to main. Vercel deploying production. Live on thebrief.clauding-lab.com — pinned until replaced.`

**`redo: <hint>`** — Re-read the same source file with the new hint:

```bash
# Re-read pins/$UUID.$EXT, re-extract per the new hint
# Edit content/long-view.ts with the new data
git commit -am "longview: redo per hint — <hint summary>"
git push --force-with-lease=longview/<slug>:$(git rev-parse HEAD~1) origin longview/<slug>
# Note: if the no-arg --force-with-lease fails because the remote-tracking
# ref doesn't exist (Conductor workspace quirk), use:
#   git fetch origin longview/<slug>
#   git push --force-with-lease=longview/<slug>:$(git rev-parse FETCH_HEAD) origin longview/<slug>
gh pr checks --watch
```

Reply with the (same) preview URL once the rebuild completes.

**`cancel`** — Close the PR, delete the branch, delete the source:

```bash
gh pr close <pr-number> --delete-branch
rm -f pins/$UUID.$EXT
```

Reply: `Cancelled. Draft deleted.`

### 10. Hard rules — do not break

- **Never merge to main without showing the user the Vercel preview URL first.** Even if you're confident the data is good.
- **Never commit the PDF/JPEG to the repo.** Only `content/long-view.ts` and (later) a CHANGELOG entry change in this PR. The source stays on disk under `pins/`.
- **Never edit `content/long-view.ts` outside this workflow.** Daily editorial content has its own pipeline (`brief.service`, Supabase); the Long View is the only thing in `content/`.
- **If anything goes wrong** (Vercel build fails, git push fails, source file is unreadable), reply to the user with the exact error and stop. Do not auto-retry on shared-state writes.

---

## Failure modes — quick reference

| Symptom | Likely cause | Action |
|---|---|---|
| `npx tsc --noEmit` fails after your edit | Type mismatch in your new `longView` value | Re-check the `LongViewData` shape in `types/brief.ts`; fix and retry. |
| Vercel build fails on the preview | Usually a runtime React error from the new data | Pull the failure summary from `gh pr checks`, fix locally, push. If still failing, hand back to user. |
| `gh pr merge` fails | Merge conflict on `content/long-view.ts` (another `longview/*` branch landed) | Surface the error verbatim. Rebase or ask the user. Don't auto-resolve. |
| User goes silent after preview | Normal | Draft branch sits indefinitely. Leave it; no auto-cleanup. |
| User starts a second `longview` upload before resolving the first | Pending draft conflict | Reply: "There's an open Long View draft on branch `longview/<previous>` (preview: …). Cancel that and start fresh, or treat this as a `redo` of the open draft?" |

---

## Quick reference — what files this workflow touches

| File | Why |
|---|---|
| `content/long-view.ts` | The pinned data. Edit per workflow. |
| `pins/<uuid>.<ext>` | Local copy of the source on disk. Not in git. |

That's it. Everything else (the component, the styles, the wiring) lives outside the per-pin workflow and is not edited here.
