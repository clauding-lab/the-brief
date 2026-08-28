# The Long View — workflow (v1.7.0)

This file is the contract for the Long View workflow on The Brief. It has two halves: **Editorial** (what to write) and **Operational** (how to ship it). Both halves must be followed for every Long View pin.

The Long View is a pinned editorial section between the Overview group and the Banking group on The Brief's SPA. It replaces whatever was previously pinned. Posted at most once per week. The output is composed from a small block vocabulary in the brief's visual language (mono + steel-crimson palette + tone tinting where it earns its keep).

**Design philosophy:** *Be creative within the design theme.* The brief provides five block kinds (`prose`, `comparison`, `stat`, `bullet-list`, `bar-chart`) and a strict visual contract (mono typography, palette tokens only, small-caps eyebrows, optional tone tinting). Compose blocks to match the source slide's structure. Do not invent new block kinds, new typography, or new colors.

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

The Brief is read by banking professionals in Bangladesh — business heads (corporate, SME, retail), risk heads, treasury heads at Tier-1 banks. Write for that reader.

### Voice register

**`Master.md`'s Tone and Voice register sections are the binding register contract for all Long View prose** (synced into this workflow in v1.7.0). The register is the Daily Star business desk — plain, declarative, reported prose — the single register since PR #174 (v2.2.0, 24 Aug 2026), superseding the earlier Economist/FT register. Where this list and `Master.md` disagree, `Master.md` wins.

- Plain, declarative, reported sentences. One idea per sentence — do not stack three or four figures behind commas and a "so" clause; give each figure its own sentence.
- Full sentences everywhere, including bullet-list item bodies. Every clause gets a subject and a verb; fragments belong only in small-caps labels and eyebrows.
- Let the facts carry the judgment. State what happened and what follows from it; at most one rhetorical turn per pin. No editorialising, no performed candour.
- Attribute a figure to its publisher and data period in prose ("according to Bangladesh Bank", "in the 31 Jul print"). Attribution is not hedging — and it is not a "Source:" line, which stays forbidden in blocks (see Forbiddens).
- Neutral toward institutions: toward BB, NBR and the government, diplomatic in framing and fact-based in substance. Critique is expressed through the facts, never as a verdict on a policy or a named individual.
- Banker-native vocabulary: NPL, CRR, repo, SDF, Sukuk, ALCO, MPS, BB, Tier-1 capital, provisioning, advance-deposit ratio.
- Concrete numbers; never round away precision the source provides.
- Implications oriented to credit committees, ALCO, treasury desks.
- No journalese ("amid", "in a stunning move", "moreover"), no LLM tells ("delve", "myriad", "tapestry"), no hedging when the source is clear.

### Output schema

Edit `content/long-view.ts` to look exactly like this (filling in your extracted data):

```typescript
import type { LongViewData } from "@/types/brief";

export const longView: LongViewData | null = {
  posted_at: "<ISO 8601 UTC timestamp — use now()>",
  title: "<5–10 words, no trailing punctuation>",
  lead: "<1–2 sentences setting up the insight>",
  blocks: [
    // 1–4 blocks; pick the right kinds for the slide
  ],
  banker_read: "<1 paragraph; the takeaway for a banker reader>",
};
```

### Block kinds

You compose `blocks: []` using these five kinds. Always pick the kind that matches the source slide's structure — do not force a structural block when prose carries the meaning.

**1. Prose** — paragraphs of analysis. Use when the slide is text-driven (an argument, narrative, single-topic analysis) or when no clean structure can be extracted.

```typescript
{
  kind: "prose",
  paragraphs: [
    "<paragraph 1>",
    "<paragraph 2>",
    // 1–3 paragraphs; never more
  ],
}
```

**2. Comparison** — before/after rows with descriptions. Use when the slide is a structured comparison grid (3+ rows of paired values). Each row has a title, before value, after value, and a 1-line description. Optional `tone` per row tints the AFTER value (`"bull"` green for positive direction, `"bear"` red for negative, `"neu"` monochrome).

```typescript
{
  kind: "comparison",
  before_label: "<short label, 1–2 words ideal>",  // e.g., "Interim"
  after_label: "<short label, 1–2 words ideal>",   // e.g., "BNP-led"
  rows: [
    {
      title: "<row title>",
      before: "<value>",          // "1.5%" | "BANNED" | "Revealed"
      after: "<value>",           // "0.5%" | "AT 7.5%" | "Rescheduled"
      description: "<1-line context>",
      tone: "bull",               // optional
    },
    // 3–10 rows typical; 7+ auto-promotes to 3-column grid
  ],
}
```

Keep `before_label` and `after_label` SHORT (1–2 words). They appear both at the block header and inside each row card.

**3. Stat** — a single headline metric. Use when the slide is built around one number (a ratio, a percentage, a count) with framing context. The value renders huge mono; the label and body sit beside it.

```typescript
{
  kind: "stat",
  value: "<numeric string>",       // "3.8" | "12,400" | "10.0"
  unit: "<optional unit>",         // "×" | "CR" | "%" | "BPS"
  label: "<small-caps eyebrow>",   // e.g., "RATIO · TOP-HALF VS BOTTOM-HALF NPL"
  body: "<1–2 sentence framing>",
  tone: "bear",                    // optional; tints just the value
}
```

**4. Bullet-list** — structured points. Use for "three signals" / "what we learned" / "key takeaways" slides. Items can use `**bold**` markdown-light for leading emphasis. Both the bolded lead and the body are full sentences — no verbless fragments in item text (see Voice register). Optional `tone` per item tints the leading mark (▸).

```typescript
{
  kind: "bullet-list",
  eyebrow: "<optional small-caps header>",
  items: [
    { text: "**The strong lead is a short full sentence.** The body carries the supporting point.", tone: "bull" },
    { text: "An item without leading bold is still written as a full sentence.", tone: "warn" },
    // 2–7 items
  ],
}
```

**5. Bar-chart** — ranked values across named categories, with an optional vertical reference line. Added in v1.3.0. Use when the slide ranks the *same* measure across 2–12 categories (divisions, banks, sectors, years) and the ranking itself is the point. Bars render horizontally, sorted in the order you supply — supply them already sorted, the component does not sort for you.

```typescript
{
  kind: "bar-chart",
  eyebrow: "<optional small-caps header>",   // e.g., "SHARE OF UNITS HOLDING A TIN, BY DIVISION"
  unit: "<optional axis unit>",              // e.g., "% of units" | "Tk bn"
  reference: {                               // optional vertical line across the plot
    value: 8.7,                              // numeric position on the same scale as items
    label: "National 8.7%",                  // short caption for the line
  },
  items: [
    { label: "Dhaka", value: 13.6, display: "13.6%", tone: "neu" },
    { label: "Rangpur", value: 4.1, display: "4.1%", tone: "bear" },
    // 2–12 items
  ],
}
```

- `value` is the number that sets bar length and MUST be plain numeric (no `%`, no commas). `display` is the optional printed label on the bar — use it when the rendered form differs from the raw number (`13.6` → `"13.6%"`, `6040` → `"Tk 6,040cr"`). Omit `display` and the value prints via `toLocaleString()` (so `6040` renders as `6,040`, with no unit).
- `reference` is for a benchmark the bars should be read against — a national average, a regulatory floor, a prior-year level. Skip it when there is no meaningful benchmark; a reference line that means nothing is visual noise.
- `tone` per item tints the bar (`"bull"` / `"bear"` / `"neu"`). Tint to carry meaning (below the reference line = `bear`), not for decoration.

**Bar-chart vs comparison — pick by what the slide is doing:**

| The slide is… | Use |
|---|---|
| Ranking one measure across many named categories | `bar-chart` |
| Setting two *states* of several measures side by side (before/after, us/them) | `comparison` |
| Ranking, but only 2 categories | `comparison`, or `stat` if one number carries it |
| Ranking, but the values are not on a common scale | `comparison` — bars are meaningless without a shared scale |

### Composition rules

**The stat + bar-chart pair (v1.6.0).** Place a `stat` block *immediately* followed by a `bar-chart` block and the component automatically renders them side by side — stat ~60% left, chart ~40% right (`.tb-longview-pair`), stacking on narrow screens. This is driven purely by block order; there is no schema field to set and no way to opt out other than separating the two blocks. Use it when one headline number and its distribution belong to the same thought. If you want them full-width and stacked instead, put another block between them.

| Slide shape | Primary block | Often paired with |
|---|---|---|
| Argumentative essay / single-topic analysis | `prose` (1–3 paragraphs) | optional `bullet-list` closer |
| Before/after comparison grid (3+ rows) | `comparison` | optional `prose` intro + `prose` closing thought |
| Headline metric driving the slide | `stat` | `bullet-list` of supporting context, or `prose` for narrative |
| Listed takeaways (e.g., "Three signals") | `bullet-list` | optional `prose` intro |
| One measure ranked across categories | `bar-chart` | a `stat` placed immediately BEFORE it, to pair them side by side |
| Mixed slide (intro + structure + closing) | composed (multiple blocks) | up to ~4 blocks per pin |
| Slide that doesn't fit any of the above | `prose` with structural description | flag the gap in your reply to the user |

**Hard constraints:**
- Maximum **4 blocks** per Long View. More than that, the slide should probably be two pins.
- Don't repeat the same block kind back-to-back. Two prose blocks in a row → merge.
- `title`, `lead`, `banker_read` remain mandatory framing. Blocks are the *middle* of the Long View.
- Block ordering: lead → most-important visual block first → supporting blocks → closing block → banker_read.

**When to fall back to prose despite a tempting structural block:**
- Comparison with only 1–2 rows → use prose.
- Stat where the number is approximate or doesn't actually carry the slide → use prose.
- Bullet-list of 1 item → use prose with that item as a paragraph.
- Bar-chart where the categories aren't measured on one common scale → use `comparison`.
- Slide where prose carries the meaning even with some numbers → use prose.

### Forbiddens

- **Do not fabricate numbers** not in the source. If the slide is unclear, reply to the user and stop.
- **Do not introduce block kinds outside the five shipped** (`prose`, `comparison`, `stat`, `bullet-list`, `bar-chart`). The authority on what is shipped is `types/brief.ts`, not this file — if the two disagree, `types/brief.ts` wins and this file needs a PR.
- **Do not specify colors, fonts, sizes, or styles in the data.** The component renders with palette tokens. Your job is structural data; the brief handles the visual contract.
- **Do not add a source-attribution field** (no "Source: BB MPS, May 2026" line).
- **Do not add a "view original" link.**
- **Do not fold opinion into the lead.** Opinion lives in `banker_read`.
- **Do not edit `CHANGELOG.md` or `package.json`** in a Long View pin PR. Per-pin PRs touch ONLY `content/long-view.ts`. Platform version bumps (v1.2.x → v1.3.0) happen in separate platform-change PRs.

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
```

### 3. Read the source

Open the PDF or JPEG and extract per the Editorial half above. If a hint was provided after `longview - `, weight your framing toward it.

### 4. Edit `content/long-view.ts`

Replace the entire contents with the new `longView` export per the schema. Use the appropriate block kind(s). Verify locally:

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
  --head longview/<your-slug> \
  --base main \
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
# If the no-arg --force-with-lease fails because the remote-tracking ref
# doesn't exist (Conductor workspace quirk), use the fetch+FETCH_HEAD fallback:
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

- **Never merge to main without showing the user the Vercel preview URL first.**
- **Never commit the PDF/JPEG to the repo.** Only `content/long-view.ts` changes in this PR.
- **Never edit `content/long-view.ts` outside this workflow.**
- **Never edit `CHANGELOG.md` or `package.json` in a Long View pin PR.**
- **If anything goes wrong** (Vercel build fails, git push fails, source unreadable), reply to the user with the exact error and stop. Do not auto-retry on shared-state writes.

---

## Failure modes — quick reference

| Symptom | Likely cause | Action |
|---|---|---|
| `npx tsc --noEmit` fails after your edit | Type mismatch in your new `longView` value | Re-check the `LongViewData` + `Block` shapes in `types/brief.ts`; fix and retry. |
| Vercel build fails on the preview | Runtime React error from the new data | Pull the failure summary from `gh pr checks`, fix locally, push. If still failing, hand back to user. |
| `gh pr merge` fails | Merge conflict on `content/long-view.ts` | Surface the error verbatim. Rebase or ask the user. Don't auto-resolve. |
| User goes silent after preview | Normal | Draft branch sits indefinitely. Leave it. |
| Slide doesn't fit any block kind | Genuinely unique structure | Use `prose` with descriptive paragraphs; flag the gap in your reply so the user can design a new block kind in a future platform PR. |
| User starts a second `longview` before resolving first | Pending draft conflict | Reply: "There's an open Long View draft on branch `longview/<previous>` (preview: …). Cancel or treat as redo?" |

---

## Quick reference — what files this workflow touches

| File | Why |
|---|---|
| `content/long-view.ts` | The pinned data. Edit per workflow. |
| `pins/<uuid>.<ext>` | Local copy of the source on disk. Not in git. |

That's it. Everything else (the component, the styles, the wiring, the recipe) lives outside the per-pin workflow and is not edited here.
