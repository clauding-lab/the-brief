# Fresh Brief Every Morning — V1 Design

**Date:** 2026-05-05
**Status:** Draft for user review
**Scope:** V1 — all five editorial-discipline directives (A through E below)

---

## Objective

Make The Brief feel genuinely fresh every weekday morning, not just technically updated. A morning newsletter is a contract: 9 minutes of the reader's time in exchange for something they didn't know yesterday. Today's V6 publisher repeatedly breaks that contract — same headlines reappear day-to-day, same Number of the Day for three days running, same editorial framing in "Today's Call". This spec encodes editorial discipline into the V6 prompt + pipeline so the brief honors the contract by construction.

---

## Why this exists — three reported bugs and one deeper failure

### Reported bugs (all surface-level symptoms of the same underlying gap)

1. **"Number of the Day" stuck on NPL 35.73%.** Cover metric for Issues 88, 89, 91 all show NPL ratio (Q4 2025 print, last refreshed April). Editor's hero rule says *"if NPL > 30%, banking leads"* — never expires.

2. **Only 4 headlines + diff toggle blanks them.** V6 editor prompt says *"select and order 4"*; V5 used to deliver 12. Worse, every news/metric in Issues 89/90/91 has `changed=false` because the V5 deterministic diff stamping was removed in the V6 cutover and the V6 editor prompt never instructs the LLM to set `changed`. SPA's `body.tb-diff` CSS rule then blanks every `:not(.is-changed)` row → diff toggle hides the entire page.

3. **~90% same content as yesterday.** Compounds Bug 2. Quarterly metrics (NPL, CAR) genuinely cannot move daily; without `changed` flags, the brief can't visually distinguish "held over because data is quarterly" from "freshly published today". Same headlines literally repeat across days (e.g. *"Will cenbank's Tk40,000cr refinance scheme fuel inflation?"* in both Issue 89 and Issue 91, identical wording, identical source). Editor LLM has access to `previous_brief` but no instruction to vary structure or de-emphasize repeats.

### The deeper failure

The system has no concept of **fresh**. No rule against repeating yesterday's headlines. No rule against repeating yesterday's editorial framing. No deterministic signal showing what genuinely moved overnight. No rotation of analytical perspective. Fixing the three bugs alone produces a slightly less-broken version of the same disease.

This spec encodes "fresh" as a first-class property of the publish pipeline.

---

## The five directives (V1 scope)

### A. Ban headline re-runs

A deterministic gatekeeper at the front of the editor pipeline drops any candidate headline that appeared in the **last 5 issues** (one work-week). Match key: `(headline_normalized, source_url)` — lowercase + strip punctuation/whitespace. No LLM judgment.

If the filter shrinks the candidate pool below the editor's headline target (12), the editor proceeds with what it has and notes the constraint in the run log. We do not re-introduce repeats to hit a count.

### B. Today's lens (data-driven, Mon–Thu) + Friday weekly wrap

Mon–Thu: each section is scored on `freshness × magnitude × signal`, the highest-scoring section wins, that section is the lens. Editor receives `today_lens="banking"` (or whichever) as a top-level input field and is constrained to lead with that section.

- **freshness** (0–1): `max(0, 1 − days_since_refresh / 14)`. Today=1.0, 7d ago=0.5, ≥14d=0.
- **magnitude** (0–1): largest metric movement in the section as `min(1, |Δ| / σ_30d)`. σ from 30-day rolling stdev of the metric's history; if history <10 points, default σ to 1× the metric's mean (proxy).
- **signal** (0–1): `1 − (held_over_count / total_metric_count)` — penalizes sections dominated by held-overs.

`section_score = freshness × magnitude × signal`. Tie-break order: (1) highest magnitude alone, (2) alphabetical by slug. **Degenerate case** — if every section scores `< 0.05` (genuinely quiet day, all held-overs and no movement), fall back to the previous brief's lens *unless* the previous brief was also a quiet-day fallback for ≥2 issues running, in which case rotate to the next slug alphabetically. Logged as `lens_fallback=quiet_day`.

Friday: lens is hardcoded to `weekly_wrap`. Pipeline gathers Mon–Fri's diffs into a `weekly_diffs` block. A separate prompt (`editor_v6_friday.txt`) produces a 5-day synthesis: biggest movers of the week, sectoral verdicts, "next week's watch list".

### C. Mark held-overs honestly

After the editor runs, a deterministic post-processor inspects each metric and news item:

- A metric is **held-over** if its `(section_slug, label)` matches a metric in the previous brief AND its `value` text is identical AND the metric's catalog cadence is monthly/quarterly/annual.
- Held-over metrics get `held_from: <date_of_first_appearance>` and `next_print: <last_print + cadence_interval>` populated.
- News items can also be held-over if a paraphrased version slipped past A's filter — same headline_normalized, different source_url. (Rare; deferred to V2 to handle properly via semantic match.)

The SPA renders held-overs as a third visual state (see "SPA display" below).

### D. Stamp `changed` flags deterministically

After the editor runs, a deterministic post-processor walks `final_brief` against `previous_brief` and stamps `changed=true/false` on every news item and metric:

- News: `changed=true` if `(headline_normalized, source_url)` is NOT present in the previous brief
- Metrics: `changed=true` if `(section_slug, label)` is present in the previous brief AND the `value` text differs

The editor prompt's schema doc gains a note for `changed`, `held_from`, `next_print`: *"system-stamped — do not set yourself; the publisher fills these post-LLM."* Subeditor's role is unchanged; it does not touch system-stamped fields.

### E. Rotate the editorial frame in `todays_call`

Six named frames, defined in the editor prompt:

| Frame | When the editor picks it |
|---|---|
| sovereign-debt | Government debt / fiscal pressure / refinance / budget items lead |
| FX-runway | Reserves / FX rate / remittance / import-cover items lead |
| credit-cycle | NPL / CAR / sector credit growth items lead |
| rates-curve | Yield curve / T-bill / T-bond / monetary policy items lead |
| external-shock | Brent / global commodity / Iran-war / external macro items lead |
| weekly-wrap | Friday only — synthesizes the week |

Editor receives `today_lens` from the lens scorer and picks the frame that fits the lens + today's data. Frame appears as a tag on `todays_call`. The paragraph runs through that frame so the prose rotates structurally even when the data overlaps. Same numbers, fresh angle.

---

## Architecture

### Pipeline shape

Today (V6.0):
```
gather() → editor_v6 LLM → subeditor_v6 LLM → publish_brief()
```

V1:
```
gather()
  → score_lens(today, sections, previous_brief)              [B] → today_lens
  → filter_headlines(scraped_pool, last_5_issues)            [A] → filtered_pool
  → editor_v6 LLM (today_lens, filtered_pool, prev_brief)    [B,E] (rewritten prompt)
  → stamp_changed(final_brief, previous_brief)               [D]
  → mark_held_overs(final_brief, metric_definitions)         [C]
  → subeditor_v6 LLM                                         (unchanged role)
  → publish_brief()
```

Friday branches at the editor step:
```python
if today.weekday() == 4:  # Friday
    editor_prompt = _load_prompt("editor_v6_friday.txt")
    editor_input["weekly_diffs"] = _build_weekly_diffs(today)
else:
    editor_prompt = _load_prompt("editor_v6.txt")
```

Both LLM calls remain. Everything new is deterministic Python around them.

### New modules

- `brief/builders/diff.py` — `stamp_changed()`, `mark_held_overs()` pure functions
- `brief/builders/lens.py` — `score_lens()` pure function, returns `(lens_slug, score_breakdown)`
- `brief/builders/dedup.py` — `filter_headlines()` pure function, returns `(filtered_pool, dropped_count)`
- `brief/builders/weekly.py` — `_build_weekly_diffs(today)` for Friday wrap

All four are pure functions with fixture-driven tests; no Supabase or Claude calls. Wired into `pipeline_v6.py` `run_publish()`.

### Schema additions

Supabase migrations:
```sql
ALTER TABLE metrics ADD COLUMN held_from DATE;
ALTER TABLE metrics ADD COLUMN next_print TEXT;
ALTER TABLE news    ADD COLUMN held_from DATE;
ALTER TABLE briefs  ADD COLUMN lens TEXT;
ALTER TABLE briefs  ADD COLUMN frame TEXT;
```

`v6_schema.py` mirrors with `Optional[]` fields:
- `MetricV6.held_from: Optional[date_t]`, `MetricV6.next_print: Optional[str]`
- `NewsItemV6.held_from: Optional[date_t]`
- `BriefV6.lens: Optional[str]`, `BriefV6.frame: Optional[str]`

`changed` already exists on `MetricV6` and `NewsItemV6`; no migration needed there.

### Editor prompt rewrite (`editor_v6.txt`, Mon–Thu)

Five surgical changes:

1. **Drop the "NPL > 30% → banking lead" rule (lines 80–86).** Replace with:
   > "Lead with the section named in `today_lens`. The cover metric is the highest-magnitude metric in that section that is not held-over. Exactly ONE section has `weight=2`; that section is `today_lens`."

2. **Headlines section: 4 → 12 (line 113).** Add: *"Items in `previously_seen_headlines` are filtered from your pool — do not re-include them."*

3. **Add `today_frame` instruction.** Editor picks one frame from the table in directive E. Frame is recorded in `BriefV6.frame`. The `todays_call` paragraph must execute the frame's analytical lens.

4. **Schema doc updates.** New fields `changed`, `held_from`, `next_print` are listed in the schema with the marker *"system-stamped post-LLM; do not set yourself."*

5. **Stale-data tightening (line 104–110).** When a metric has `held_from` populated, `banker_read.verdict` MUST acknowledge it explicitly: *"Held from 18 Apr — next print Q1 2026 in late July."* No more pretending stale data is news.

### Editor prompt — Friday (`editor_v6_friday.txt`, new file)

Different shape from Mon–Thu. Input includes `weekly_diffs` (Mon–Fri's per-section deltas). Output structure:

- `cover_metric` = biggest σ-mover of the week (not today's pick)
- `todays_call` (renamed mentally to "weekly_wrap") = 5-paragraph synthesis: macro arc, banking arc, markets arc, external arc, "next week's watch list"
- Sections receive `verdict` lines that read across the whole week, not the day
- `today_lens="weekly_wrap"`, `today_frame="weekly-wrap"`

### SPA display changes

`app/components/Section.tsx`, `Cover.tsx`, `StatStack.tsx` and `app/globals.css`:

Three states for items now (was binary changed/not):

| State | Visual | Diff-toggle behavior |
|---|---|---|
| `changed=true` | Full opacity, "·NEW" tag, dot indicator | Highlighted |
| `held_over=true` (`held_from` present) | Muted color, footer line `"Held from {held_from} · next print {next_print}"` | **Not blanked** — shown as muted |
| Default (`changed=false`, no `held_from`) | Standard opacity | Blanked under diff toggle (existing) |

CSS additions:
- `.is-held-over` class — muted color, smaller footer
- Update `body.tb-diff .tb-section .tb-news-item:not(.is-changed)` rule to also exclude `.is-held-over`

Masthead pill component (new, small): displays `"Mon · banking lens · sovereign-debt frame"` or `"Fri · weekly wrap"`. Positioned in `app/components/Masthead.tsx`.

---

## First-run / missing-previous-brief behavior

When `previous_brief` is `None` (first run after a wipe, or genuinely Issue 1):

- `stamp_changed` marks every news item and metric as `changed=true` (everything is new by definition)
- `filter_headlines` returns the candidate pool unchanged (nothing to filter against)
- `mark_held_overs` does nothing (cannot detect repeats without history)
- `score_lens` falls back to a fixed day-of-week cycle (Mon=banking, Tue=fx, Wed=macro, Thu=banking, Fri=weekly_wrap) for the very first issue, then resumes data-driven scoring on Issue 2 once history exists

Logged as `cold_start=true` on the run log so it's distinguishable from steady-state.

---

## Defaults — locked unless flagged in user review

| Choice | Default | Why |
|---|---|---|
| Re-run window for headline filter | Last 5 issues | One work-week of memory; configurable in `pipeline_v6.RERUN_WINDOW` |
| News identity match | `(headline_normalized, source_url)` | Deterministic, no LLM cost; semantic match deferred to V2 |
| Metric identity match | `(section_slug, label)` | Stable; "changed" = `value` text differs |
| Held-over data source | `metric_definitions.cadence` from V3 catalog | Already populated; quarterly → +3mo, monthly → +1mo, annual → +12mo |
| Lens override on shock days | Deferred to V2 | V1's data-driven scorer already responds to magnitude |
| Subeditor role | Unchanged | Reviews tone/voice; does not touch system-stamped fields |
| Lens tie-break | Alphabetical by slug | Deterministic; rare in practice |
| Friday detection | `today.weekday() == 4` (Mon=0…Fri=4) | Standard Python convention |
| `next_print` formatting | Free text label, e.g. `"Q1 2026 in late July"` | Allows nuance the cadence math can't capture |

---

## Test surface

| Module | Test type | Notes |
|---|---|---|
| `stamp_changed` | Unit | Fixtures: brief with no diffs, brief with all-new, brief with mix |
| `filter_headlines` | Unit | Fixtures: empty history, exact match, normalized match, paraphrase (must NOT filter — V2 territory) |
| `score_lens` | Unit | Fixtures: all-fresh, all-stale, single-mover, tie cases |
| `mark_held_overs` | Unit | Fixtures: fresh metric (no annotation), held quarterly (annotated), held monthly (annotated), missing cadence (no annotation, log warning) |
| `_build_weekly_diffs` | Unit | Fixture: 5-day synthetic week, verifies aggregation |
| `pipeline_v6.run_publish` Mon–Thu | Integration | Frozen previous_brief fixture; verifies all 4 primitives wire correctly + editor input shape |
| `pipeline_v6.run_publish` Friday | Integration | Friday fixture; verifies wrap path + Friday prompt |
| Schema validation | Unit | New fields accepted, defaults correct |
| SPA snapshot | Component | Section.tsx renders 3 visual states correctly |

Coverage target: ≥80% on new code (per project rule).

---

## Shipping plan — 5 PRs

| PR | Scope | Behavior change | Why this order |
|---|---|---|---|
| 1 | Schema + migration + Pydantic field additions | None (additive) | Unblocks PRs 2–5; safe to merge alone |
| 2 | Core diff primitives: `stamp_changed`, `filter_headlines`, `mark_held_overs` + tests | None (utilities only, not wired) | Verify deterministic logic in isolation |
| 3 | Lens scorer: `score_lens` + tests | None (utility only, not wired) | Same — verify in isolation |
| 4 | Editor prompt rewrite + Mon–Thu pipeline wiring | Live: today_lens drives editor; diff stamping live; held-overs annotated; headlines = 12 | First user-visible change — Mon–Thu briefs become fresh |
| 5 | Friday wrap + SPA polish (held-over render, lens pill) | Live: Friday produces weekly wrap; SPA shows third state | Completes V1 |

Estimate: 3–4 focused days. PRs 1–3 ship safely without behavior change so deterministic primitives can be verified before going live; PRs 4–5 are the user-visible flips.

---

## Out of scope (V2+)

- **Semantic headline dedup.** If exact-match dedup proves too leaky (paraphrased repeats slip through), V1.1 adds embedding-based or cheap-LLM dedup as a second filter pass.
- **Lens shock override.** A named-event override (Hormuz re-escalation, FX peg break, BB rate decision) that force-rotates the lens regardless of data score.
- **Per-reader memory.** "You've already seen this" tracking per subscriber — would require auth-tied state. Not on the roadmap.
- **Multi-frame todays_call.** Right now one frame per day. V2 could support a primary + secondary frame for hybrid days.
- **EconDelta-side cache invalidation.** If repeat headlines turn out to come from EconDelta's scrape pool not refreshing daily (rather than just no new news), that's a fix in the EconDelta repo, not here.

---

## Open questions for user review

None blocking. All "Defaults" are locked unless the user flags one during spec review.

---

## Acceptance — V1 done when

- Mon–Thu morning brief leads with a section determined by data, not by a hardcoded NPL>30% rule
- Diff toggle on the SPA shows actually-new items highlighted, held-overs muted with their next-print date, everything else faded — no blank pages
- No headline appears in two consecutive briefs (verifiable via SQL: `SELECT headline FROM news GROUP BY headline HAVING COUNT(DISTINCT brief_id) > 1` should return zero rows for current week)
- Friday's brief is structurally a weekly wrap, not a daily snapshot
- `todays_call` paragraph runs through one of six named frames, recorded in `briefs.frame`
- All new code has ≥80% test coverage
