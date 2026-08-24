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

## 2026-08-24 — unreleased | Issue 206: DSEX printed a nonexistent session date plus a fabricated "ten-session low", and the CPI cards split across two tables from their own chart

**Trigger:** issue 206's DSE card read "5,722 · −1.10% on the 24 Aug session — a ten-session low" while the same section's `chart_read` correctly said "as of the 23 Aug session" — two dates in one section. Root-cause investigation also found the macro section's CPI Food/Non-Food cards were printing June while the chart plotted underneath them showed July.

**What went wrong:** three separate defects, one shared shape — a number's SESSION or PERIOD was discarded or diverged before it reached the reader:
1. `brief/builders/dse.py`'s fresh branch stamped `as_of = ctx.today` on every DSE metric. EconDelta's snapshot has no per-key session date, and the brief fires at 08:00 BDT — before DSE's own 10:00 BDT open — so `ctx.today` was never a valid session date. `period_label(ctx.today, "daily")` produced the literal "24 Aug 2026" and `editor_v6.txt` orders the editor to print a metric's `period` verbatim.
2. `check_count_claims`'s BLOCK-mode regex only matched the PREPOSITIONAL count-claim shape ("across ten sessions"). "A ten-session low" is a hyphenated ATTRIBUTIVE shape the same regex family never covered — a fabricated observation count nothing in the pipeline supplies, printed twice more in issue 205's fixture before this fix.
3. `brief/builders/macro.py` routed the three CPI cards through THREE different read paths (one archive, two live daily), while `chart_series_fetcher.fetch_macro_cpi_series` pulled all three from the monthly archive — with no honesty check tying a card's own period to its own chart's newest point, and no source-based filter distinguishing an official BB print from an arithmetic-derived or owner-unverified archive row.

**Lesson:** (a) a value pulled from a point-in-time snapshot with no embedded date must be dated from a source that HAS a real date (history, not the clock) whenever the two could legitimately be different sessions — this is a general shape, not a DSE-specific one. (b) a fabricated-count regex family needs its surface-shape coverage re-audited whenever a new phrasing is caught in production, corpus-replayed before promotion, exactly like the original check was. (c) a card and its own chart must be checked against each other, not just each independently against the builder — two honestly-computed numbers can still disagree with each other if they're read from different tables with different freshness, and nothing short of an explicit cross-check catches that.

**Prevention:** `dse.py`'s fresh branch now resolves `as_of` from a matching history row (value-verified same session) or the last BD trading day strictly before now — never the run date. `_HYPHENATED_COUNT_CLAIM_RE` extends the count-claim family as WARN-mode (golden-corpus replay: 3 TP — issue #205's real defect, repeated 3 ways — 0 FP across #199-#205). `fetch_macro_cpi_series` now drops any archive point that isn't an official print (`is_official_cpi_point`, source-allowlist + an explicit owner-pending denylist entry for the one point a source string alone can't catch); `macro.py`'s CPI food/non-food specs gained a scoped "newest official row across live+archive" resolver (opt-in per spec, every other `live_id` spec unchanged). Two new WARN-mode tripwires — `pipeline_v6._check_daily_as_of_vs_series_summary` (daily cadence) and `prose_numbers.check_card_period_vs_chart_series` (any cadence, directional: only "card older than its own chart" fires) — both ship WARN, not BLOCK, for one cycle, with an explicitly named promote-to-block constant each, matching the count-claim check's own staging discipline before its corpus replay earned BLOCK.

**Hotfix:** `brief/builders/dse.py` (session-date resolution + trading-day fallback), `brief/validators/prose_numbers.py` (`check_hyphenated_count_claims`, `check_card_period_vs_chart_series`), `brief/pipeline_v6.py` (`_check_daily_as_of_vs_series_summary`), `brief/chart_series_fetcher.py` (`is_official_cpi_point`, `fetch_macro_cpi_series` filtering), `brief/builders/macro.py` (`_resolve_newest_official_cpi`, `dual_source_official` opt-in flag). Card VALUES did not change (food/non-food stay on June's official print); only the chart's plotted endpoint and the two new WARN tripwires changed. Separately: the test suite was leaking small raw-dump files into the repo's real `logs/` dir on every run (any test that exercises `_dump_raw_on_failure` for real) — `tests/v6/test_pipeline_v6.py` gained an autouse fixture redirecting those writes to pytest's `tmp_path`; production dump behavior is unchanged.

**Cross-references:** AGENTS.md landmine 35 (session-vs-run-date; notes the same pattern is still OPEN in `iranwar.py`/`fx.py`/`bb.py`/`headlines.py`), landmine 34 (the prose-number gate's BLOCK/WARN staging discipline this PR's two new checks and one extended regex all followed). Not fixed here, filed separately: the EconDelta `as_of`-stamping shift + missing 20 Aug DSEX row (different repo, needs Adnan's sign-off and an external source of truth); econdelta's `food_inflation`/`non_food_inflation` still read the lagging MEI PDF instead of BB's live econdata/inflation page.

## 2026-08-22 — unreleased | PR #167 round 2: a publish-holding check shipped without corpus replay would have held 25/25 real mornings at 0.6% precision

**Trigger:** an engineering review of PR #167 (the P2 post-editor number/period fact-checker) replayed its two BLOCK-mode checks — `check_metric_sub_numbers` and `check_metric_sub_periods` — against 25 real published issues (#180–#204) instead of trusting the synthetic unit-test fixtures that had already shipped green.

**What went wrong:** the checks were designed, tested, and merge-ready entirely against hand-built fixtures that looked exactly like the failure modes they were meant to catch — and never once run against a real published issue before being wired to hold the daily publish. Against the real corpus: 25 of 25 issues would have held, 527 BLOCK hits, only 3 true positives (0.6% precision). Worse, the review's real audit findings weren't even where the check was looking — 3 of the 5 known #204 falsehoods (including the headline "$2.82bn" figure) lived in a metric's own published `value`, and the check only ever read `sub`. A check that is precise against fixtures it was designed to pass is not evidence it is precise against the data it will actually run on.

**Lesson:** a check that can hold the daily publish must be corpus-replayed against real historical output before it ships as BLOCK, not just unit-tested against fixtures written to match its own design. Synthetic fixtures prove a check catches what its author imagined; only real data proves it catches what actually happens — and reveals what it's looking at the wrong field for.

**Prevention:** golden-corpus regression tests (`tests/validators/test_prose_numbers_golden_corpus.py`, `tests/fixtures/real_issues/*.json` — real anon-fetched published rows, not synthetic) now sit alongside the unit tests. Severity is staged, not asserted: only a corpus-verified near-zero-false-positive surface (`check_count_claims`, 17 true positives / 0 false positives across 9 of the 25 real issues) is allowed to BLOCK; everything else is WARN-only until production log volume earns the same confidence, gated behind `BRIEF_PROSE_VALIDATOR_STRICT=1` as an explicit, documented future promotion — never silently upgraded.

**Hotfix:** PR #167's round-2 reshape — `check_metric_sub_numbers`/`check_metric_sub_periods` demoted to WARN (batched into ONE Discord alert per publish, grouped by section, not one message per warning); a new `check_metric_value_vs_raw` added specifically to read the field (`value`) the original design missed; count-claim noun list narrowed from `(reads|prints|sessions|days)` to `(reads|prints)` after "days"/"sessions" contributed zero true positives and a real false positive ("BB hasn't published reserves in 14 days").

**Cross-references:** AGENTS.md landmine 34, `tests/validators/test_prose_numbers_golden_corpus.py`, the 2026-08-22 audit #204 entry below (the original incident this fact-checker was built to prevent a recurrence of).

## 2026-08-22 — unreleased | Audit #204: the front page was printing false numbers — flash data presented as final, mismatched-vintage derivations, and an editor free to invent figures

**Trigger:** a two-pass audit of issue #204 found the front page's remittance card citing a frozen mid-month provisional figure as if it were BB's official number ($2.82bn vs the real $2.86bn), a trade gap and an import-cover ratio each silently combining two different reporting months into one number, a "real policy rate" that mixed a post-rate-cut reading with a pre-cut inflation print, a stale-data footer that blamed Bangladesh Bank for "overdue" data when the pipeline only knew its own copy was old, and — separately — the AI editor inventing a "$80 FY27 crude" budget-assumption motif with no basis anywhere in Bangladesh's actual budget documents.

**What went wrong:** several independent root causes, all sharing one shape — a number's VINTAGE (which period, how confirmed) was discarded before it reached the reader:
1. `remit.py`/`fx.py` read a daily-restamped "flash" series and presented it under the same label a genuine official final would carry, with no signal that it was provisional.
2. `macro.py`'s import cover and `fx.py`'s trade gap each divided/subtracted two values from different calendar months without checking they matched, and dated the RESULT by whichever leg happened to be freshest — hiding the mismatch instead of surfacing it.
3. `macro.py`'s real policy rate paired "today's" corridor rate with "today's" inflation print regardless of whether a rate cut had landed between the two prints' actual reference dates.
4. `vintage.py` had a source-blaming word ("overdue") baked into a note that only reflects the PIPELINE's own read-age, not anything about the source's publishing behaviour.
5. `pipeline_v6.py` fed the editor the ENTIRE previous issue — numbers included — as "context for continuity," with nothing stopping the model from quoting an old figure forward verbatim, or inventing a new one and having it survive unfiltered into Supabase.

**Lesson:** a number is not just a value — it is a value PLUS a period PLUS a confidence level, and any pipeline stage that drops one of those three while keeping the other two has produced a number that can lie by omission. Corollary from review round 1: a SAFETY NET for that problem (a hallucination denylist, a staleness gate) is itself a new piece of logic that needs the same scrutiny — the first cut of the denylist scanned the FULL serialized brief including chart data points, and the first cut of the import-cover gate was strict enough to suppress the metric on every real production day, flipping an honestly "stale" section badge into a false "history is accumulating" one. A fix that trades one honesty bug for a new outage or a new false signal is not done.

**Prevention:** (a) every builder that reads a monthly archive now goes through a shared `official_monthly_bn()` helper (`brief/builders/__init__.py`) that normalizes to month-end and full float precision, logging by name on every non-success path; (b) derived metrics that legitimately combine two vintages (import cover) now say so explicitly in their `source` field and date themselves by the OLDER/rate-limiting leg, never the fresher one; (c) derived metrics where mixing vintages is NOT legitimate (trade gap) are suppressed outright rather than computed; (d) the hallucination denylist scans PROSE FIELDS ONLY and requires context co-occurrence for its broadest pattern; (e) `_scrub_numbers` strips every figure — string or numeric leaf — from the previous issue before it reaches the editor's prompt, proven non-mutating by a deep-equal test; (f) new regression tests pin the EXACT real production numbers from the audit (reserves 36.4222bn @ 31 Jul, imports 5826.2mn @ 31 Mar → cover ≈6.25, §03 stays "stale") rather than synthetic round numbers, so a future change that reintroduces the bug fails against the real shape of the data, not an idealized one.

**Hotfix:** PR #165 (`fix/p0-honesty`), two review rounds. See AGENTS.md landmines 27(a) (rewritten — `metric_history_monthly` gained live appenders 2026-08-08, superseding the "dead table" framing) and the editor/sub-editor convention note (exit code 4 now also covers a denylist hit).

**Cross-references:** AGENTS.md landmine 27 (a/b/c), landmine 24 (event-cadence writer-liveness, same "don't trust a fresh `as_of` blindly" family), 2026-08-08 entry below (the live-appenders backfill this incident's fixes build on), econdelta PRs #123/#124.

## 2026-08-09 — v2.0.1 | The stream-stitching fix never ran: `thinking` and the answer share one `message.id`, and our de-dup threw the answer away

**Trigger:** two failed publishes in two days — issue 190 (2026-08-08, 15:59 BDT re-fire) and issue 192 (2026-08-09, 08:13 BDT scheduled run), both `editor_v6 output failed schema validation` where Pydantic was handed a valid *inner* object (a `chart_read`, then a `NewsItemV6`) instead of the brief. The signature of issues 181/183 — which we had already "fixed" on 2026-08-02.

**What went wrong:** `_collect_stream_messages` (`brief/claude/max_client.py`) de-duplicated assistant events by `message.id`. That assumed one event per message. With `--effort xhigh` the CLI emits ONE assistant message as TWO events sharing an id: the `thinking` block first, the `text` block second. The de-dup kept the thinking-only event (no text) and skipped the event carrying the brief, so `texts` came back EMPTY — and the empty-texts branch falls back to `result_event["result"]`, which holds only the FINAL assistant message. In other words the function silently reverted to the `--output-format json` behaviour it was written to replace, on every single call. On a normal day that fallback still contains the whole brief, so nothing looked wrong. On a day the payload was cut off, the pipeline got the tail and rejected a fragment. The cut-off alarm keys on `assistant_messages > 1`; the count was 0, so it could never fire — for a week the loudest evidence was the alarm's silence.

**Lesson:** when a fix's success path and its fallback produce identical output on the happy path, the fix is unverified in production — assert on the mechanism (was anything actually collected?), not on the outcome.

**Prevention:** four regression tests in `tests/claude/test_max_client_stream_stitching.py::TestThinkingAndTextShareOneMessageId` replay the real thinking-on stream shape, including a cut-off payload where every chunk trails its own thinking event. The stream shape was confirmed by a live probe before writing the fix, not assumed: two events, both `msg_011CdrRxd9KybSrDcRoVj6zx`, blocks `thinking` then `text`. The earlier tests modelled thinking as its own message id — which is why they passed against broken code.

**Hotfix:** de-duplicate on `(message.id, that event's text)` instead of `message.id`, skip events with no text, and count only text-bearing events so `assistant_messages` stays a true cut-off signal. Re-emitted events (identical id AND text) are still de-duplicated; a continuation chunk differs in text and is kept.

**Cross-references:** AGENTS.md landmine 26, AGENT_LEARNINGS 2026-08-02 (issue 183), auto-memory `project_brief_publish_v6_failures`.

## 2026-08-08 — v2.0.0 | Four charts served 5-month-old data with zero visible symptoms — the seeded `metric_history_monthly` series had no live producer, and the freshness alert was wallpaper

**Trigger:** owner asked why the fig.07 remittance chart's x-axis stopped at March 2026 while the same page's stat card cited July's flash.

**What went wrong:** The remittance, External Flow Balance, CPI, and yield-ladder charts all read `metric_history_monthly` series that were one-shot seeded from a third-party aggregator (`macro_observer_seed`) which stopped publishing after March 2026. Nothing on our side appended new months. The charts kept rendering a full, healthy-looking window ("last N months that exist"), so nothing looked broken; EconDelta's sentinel flagged the staleness daily from ~mid-April, but as ~20 of 41 digest items — alert fatigue swallowed it. Two prose/data pipes made it invisible: captions and headline stats read the fresh daily `metric_history` ids, so the words stayed current while the lines froze.

**Lesson:** a chart whose data source can die while the chart still renders beautifully needs its own freshness alarm — page-level plausibility ("it renders") proves nothing about currency.

**Prevention:** EconDelta now maintains the series live (append-only monthly appenders, PRs #123/#124), and its sentinel digest lists `CHART_FEEDING_METRIC_IDS` breaches first under a dedicated reader-visible tier, with parked-but-visible ids surfacing on heartbeat day. The Brief needed zero code changes — fetchers auto-extend — but any data fix reaches readers only after a publish (`python -m brief.cli run --publish --no-notify` for off-schedule; a same-day run replaces the same issue_no in place, confirmed on issue #191).

**Hotfix:** official-values backfill Apr–Jun 2026 (remittance/exports/CPI trio) + May–Jul 2026 (all 8 yield tenors from `auction_results`), then same-day republish of issue #191 — all four charts verified extended in PROD HTML. Imports honestly remains at its true frontier (BB publishes cif ~2 months late); exports' ongoing source is parked research (EPB portal is JS-rendered).

**Cross-references:** econdelta AGENTS.md landmines 50–51, econdelta AGENT_LEARNINGS 2026-08-08 entries, global rulebook 2026-08-08 entry, auto-memory `project_frozen_charts_fix_2026_08_08`.

## 2026-08-08 — v1.6.9 | An off-schedule `systemctl start brief.service` republish mints a new issue AND re-emails every subscriber — neither is what "just re-run it" means

**Trigger:** the day's original 08:00 BDT publish held (exit 4) — the editor/sub-editor exchange returned a fragment instead of a full `BriefPayloadV6`, a shape-drift the retry logic did not treat as transient. A single manual retry of the same call cleared it, so the underlying data was never bad; the response shape was. Rather than re-running the pipeline directly, the box was re-fired the same way `brief.timer` fires it: `systemctl start brief.service`. That produced two side effects nobody had reasoned through, both discovered only after the fact:

**What went wrong:** `systemctl start brief.service` runs the exact same `ExecStart` the timer uses — `python -m brief.cli run --publish` with no override flags. Two consequences follow mechanically, neither of them a bug in the strict sense, both wrong for what was actually intended:

1. **It mints a NEW `issue_no`, it does not rebuild the day's issue.** `v6_publisher.publish_brief` computes `issue_no` fresh per call rather than keying off `brief_date`; there is no "re-publish issue N" mode, only "publish the next issue." The result: 2026-08-08 now has **two published issues, #189 and #190**, both live in Supabase. The owner reviewed both and ruled to keep them rather than delete either — but that is a one-off call, not a precedent; a future off-schedule re-fire that produces a genuinely bad second issue will need the same delete-or-keep decision made deliberately, not by default.
2. **It re-emails every subscriber.** `brief.service`'s `ExecStart` has notifier `notify=on` by default (the same path the 06:00 daily fire uses) — there is no separate "quiet" unit for manual re-fires. Every subscriber who received the morning's #189 email also received #190. This is the same class of harm landmine #3 (one-Brevo-POST-per-subscriber privacy contract) protects against, just triggered by an operational habit rather than a code bug: the code did exactly what it was told; what it was told was wrong for the situation.

**Lesson:** `systemctl start brief.service` is the RIGHT command for "the scheduled fire didn't happen, run it as if it had" (a missed-fire catch-up, which legitimately wants a new issue and a real notify). It is the WRONG command for "the day's issue needs correcting, run it again" (an off-schedule same-day republish, which wants neither a second issue_no nor a second round of emails). The two scenarios look identical at the shell prompt and are operationally opposite.

**Prevention:** off-schedule same-day republishes MUST invoke the CLI directly with `--no-notify`, not `systemctl start`:

```bash
set -a; source /etc/brief.env; set +a
.venv/bin/python -m brief.cli run --publish --no-notify
```

This still mints a new `issue_no` today (the publisher has no "overwrite issue N" mode — a real gap, not addressed by this fix) but stops the re-notify. `systemctl start brief.service` stays correct and intended for a genuine missed-fire catch-up, where a fresh issue and a fresh notify are both wanted. README's "Manual fire" runbook (Operations section) documents the missed-fire case only; it should gain an explicit off-schedule-republish variant with `--no-notify` so the next incident doesn't rediscover this by re-emailing subscribers again. Not yet fixed: publisher still cannot target/replace an existing `issue_no`, so two same-day published issues remains reachable by design, not just by mistake.

**Hotfix:** none shipped to code this round — this is a documentation-and-runbook lesson, not a pipeline bug. #189 and #190 both stand, per owner sign-off. The editor/sub-editor shape-drift that triggered the original hold cleared on a single retry and was not independently investigated further; if it recurs, it needs its own entry (see AGENTS.md landmine 26 on cut-off/shape-drift editor responses for the closest existing mechanism).

**Cross-references:** AGENTS.md landmine 3 (notifier privacy contract — one POST per subscriber, the mechanism this incident exercised correctly but unnecessarily), landmine 26 (cut-off/shape-drift editor responses), landmine 21 (self-deploy — no human checkpoint between merge and the next scheduled fire; this incident shows the same "the unit just does what it's told" property applies to manual fires too). Global rulebook: candidate for promotion if another clauding-lab project's systemd unit conflates "catch-up" and "republish" the same way.

## 2026-08-05 — pipeline | Sub-editor gate had a second fail-open door: a well-formed `revise` with no `revised_brief` shipped the unreviewed brief

**Trigger:** external repo audit, adversarially verified by reproducing the failure end-to-end — constructing the exact `SubeditorReview` shape and executing it through the schema/pipeline rather than reading the code and inferring.

**What went wrong:** the 2026-07-09 fix below closed the malformed-JSON escape route but missed a second one in the same gate. `revised_brief` on `SubeditorReview` was `Optional` with no cross-field check, so a well-formed `{verdict:"revise", issues:[{severity:"error", ...}], revised_brief:null}` validated cleanly. `pipeline_v6.run_publish`'s branch only distinguished `revise` from not-`revise`, so the `else` arm ran for this case too, shipped the UNREVISED editor brief, and logged `"subeditor passed with N warnings"` — a false statement, since the verdict was `revise`, not `pass`. Omitting the largest field (`revised_brief`, a full nested brief payload) is the cheapest way for a token-pressured model to still return schema-valid JSON.

**Lesson:** an `Optional` field on an otherwise-strict schema is still a fail-open path. "A review gate must never fail OPEN" (2026-07-09 entry below) applies to every escape route the schema allows, not just the one that broke last time. `test_subeditor_review_revise_requires_brief`'s own docstring had labelled this exact fallback "intentional" — the test was affirming the fail-open path the rule forbids.

**Prevention:** `SubeditorReview` gained a `model_validator(mode="after")` rejecting `verdict="revise"` with `revised_brief=None` at construction — routes into the existing malformed-review retry-then-hold path (`_run_subeditor`), never auto-pass. Because a validator only guards `model_validate` (not `model_construct()` or bare attribute assignment — no `validate_assignment` on this model), `run_publish`'s branch was also rewritten as an explicit `if verdict == "revise" / elif verdict == "pass" / else raise V6PublishError` — the publish gate now enforces "never ship without a revised_brief" as its OWN invariant, not solely the schema's. The gate log only says "passed" on `verdict == "pass"`. The test that had called the fallback "intentional" is flipped to assert the `ValidationError` and now cites this rule in its docstring. New/changed tests: `test_subeditor_revise_without_brief_holds_never_ships_unrevised`, `test_subeditor_revise_without_brief_holds_even_for_warn_only_issues` (severity-blind — the prompt permits fixing warn-only issues via revise, so a future severity-scoped validator would reopen this), `test_publish_gate_holds_on_non_pass_verdict_even_if_validator_bypassed`, and the rewritten `test_subeditor_review_revise_requires_brief`.

**Hotfix:** `brief/v6_schema.py` (`SubeditorReview._revise_requires_brief`) + `brief/pipeline_v6.py` (`run_publish`'s verdict branch, explicit `elif`/`else raise`) — commits `418784c` + `58b9645` on `fix/subeditor-revise-requires-brief`.

**Cross-references:** 2026-07-09 entry below (malformed-review auto-pass — same gate, the escape route this entry closes); AGENTS.md landmine 20 (editor↔sub-editor lockstep); branch `fix/subeditor-revise-requires-brief`.

## 2026-08-02 — v1.6.1 | The editor was never misbehaving: we read one message of a multi-message answer, and the alarm we built for it could not fire

**Trigger:** `brief.service` failed at 06:44 BDT on a normal Sunday daily (issue #183), then again on a manual re-fire at 07:48 BDT. Identical signature to the three failures of 2026-07-31 (issue #181), which the v1.6.0 hotfix was supposed to have closed.

**What went wrong:** three compounding mistakes, only the first of which was known.

1. **The read.** When the editor's payload crosses the model's per-response output cap it is cut off mid-JSON and continues in a NEW assistant message. `--output-format json` reports only the FINAL message in `result`, so the pipeline received the tail of the brief. `_extract_json_object` (`brief/claude/max_client.py`) then "rescued" the first balanced `{…}` in that tail — a lone section object — and Pydantic rejected it with 18 `extra_forbidden` errors. The editor's work was correct and complete every single time; six good sections were binned on 2026-08-02 alone.

2. **The 2026-07-31 fix did nothing.** It pinned `CLAUDE_CODE_MAX_OUTPUT_TOKENS` to 64,000 on the belief that the default was lower and the ceiling was tunable. It is not: 64,000 is the model's hard per-response cap on `claude-opus-4-8` (asking for 128,000 returns 64,000). The change set the value to what it already was. **It was merged to `main` on the strength of an untested assumption, and the probe that disproved it took two minutes to run — after the merge.**

3. **The alarm built to catch a recurrence could not fire.** It was gated on `parsed is None and num_turns > 1`. Both halves were wrong. `parsed` is not None, because the preamble fallback successfully extracts a fragment — the rescue path masks the failure it was meant to reveal. And `num_turns` stays **1**: a cut-off-and-continued response is one turn, not several. The alarm was silent through two more production failures while the exact condition it named was occurring.

**Lesson:** when a fix rests on a claim about someone else's system ("the default is lower", "the ceiling is configurable"), probe the claim before merging, not after — and never gate a diagnostic on the success of a rescue path, because the rescue is what hides the problem.

**Prevention:**
- `run_max` now reads `--output-format stream-json` and stitches every assistant text block in arrival order, which reconstructs the payload byte-for-byte; length stops being a failure mode. Verified against a forced-truncation probe (`CLAUDE_CODE_MAX_OUTPUT_TOKENS=1200`, 3 assistant messages, stitched output parsed clean).
- The cut-off alarm now keys on **assistant-message count**, fires whether or not the payload parsed, and is tested for both traps above (`tests/claude/test_max_client_stream_stitching.py`).
- The raw-output dump from v1.6.0 is the one thing that worked — it turned a four-hour blind diagnosis into a twenty-minute one. Keep it.

**Hotfix:** PR #141 — stream-json stitching + corrected alarm + 19 tests. The v1.6.0 token pin is left in place (documented as a no-op against the current model, meaningful again if a future model raises the cap).

**Cross-references:** AGENTS.md landmine #26; supersedes the diagnosis in the v1.6.0 entry for issue #181.

## 2026-07-09 — pipeline | Sub-editor auto-pass shipped unreviewed briefs; validators.py was dead code

**Trigger:** 2026-07-04 ecosystem review (handoff item 7). Two findings in the publish path: (1) `pipeline_v6.run_publish` handled a malformed `SubeditorReview` by logging a warning and setting `review = SubeditorReview(verdict="pass")` — so a sub-editor call that returned well-formed JSON in the wrong shape published the editor's draft UNREVIEWED, with no test covering it. (2) `brief/claude/validators.py` (704 lines of hard, testable slop/abbreviation/chart-read checks) was imported by NOTHING in the publish path — the deterministic backstop existed but never ran.

**What went wrong:** (1) the failure handler chose availability over correctness — "couldn't parse the review, ship anyway". A self-review that silently degrades to "pass" is worse than no review: it looks reviewed. (2) writing a validator library and never wiring it is the same as not writing it; the sub-editor's LLM checks had no deterministic partner. Note the interaction with #120: `_call_with_retries` already retries the sub-editor 5× on *transient API* failures — but a well-formed-yet-invalid `SubeditorReview` returns successfully from that layer, so the auto-pass sat *after* the retry, untouched by #120.

**Lesson:** (1) a review gate must never fail OPEN — malformed review → retry once, then HOLD (yesterday's brief stays live), never auto-pass. (2) a deterministic validator is only a gate if something calls it every publish.

**Prevention:** (1) `_run_subeditor` wraps the call in a retry-once loop; two malformed reviews raise `V6PublishError` (exit 4). Tests `test_subeditor_malformed_twice_holds_never_auto_pass` and `test_subeditor_malformed_once_then_valid_passes`. (2) `_run_deterministic_gate` runs validators.py over the final brief prose (todays_call, banker_read, analysis, chart_read) every publish — **log-only** for now (a deterministic false-positive must not hold the 06:30 fire; escalate specific checks to hard-fail once the logs prove precision). Tests `test_deterministic_gate_flags_banal_and_bad_chart_read` + `..._clean_brief_zero_violations`.

**Hotfix:** `brief/pipeline_v6.py` — `_run_subeditor` (retry-once-then-hold) + `_run_deterministic_gate` (log-only), wired into `run_publish` (this PR).

**Cross-references:** AGENTS.md landmine 20 (editor↔sub-editor lockstep), #13/#120 (transient Anthropic retries — orthogonal layer); handoff `docs/handoff/2026-07-04-review-fixes.md` items 7 + 9; B2 sub-editor prompt proposals (items 8-9) are sign-off-gated and shipped separately.

## 2026-07-09 — publish path | Non-atomic publish could serve a half-written brief (#118 mechanism, now fixed)

**Trigger:** 2026-07-04 ecosystem review (handoff item 4). `v6_publisher.publish_brief` wrote the `briefs` row with `status='published'` (schema default) BEFORE its sections/metrics/news/chart_series landed, over separate non-transactional PostgREST POSTs. A mid-loop failure (child-POST 4xx/5xx, systemd `TimeoutStartSec` SIGTERM, OOM-kill) left a row the SPA served as an empty/partial brief — the orphaned-brief-#118 mechanism (see 2026-05-29 entry). Verified still live: `test_publish_brief_atomic_flow` asserted call ORDER only, and the sole error test failed on the initial DELETE (the safe case). No test covered briefs-INSERT-ok + a later child POST failing.

**What went wrong:** publish and durability were coupled to the same write. Visibility (`status='published'`) was granted at the very first row insert, so any later failure exposed a partial brief. PostgREST cannot span a DB transaction across these POSTs, so "insert everything then it's visible" was never actually atomic.

**Lesson:** when a multi-row write can't be one DB transaction, gate reader visibility on a SINGLE final flip. Write everything invisibly first (a `draft`), then make it visible with one last status update. Confirmed the reader gate first: `get_latest_brief` is `... where status = 'published' ...` (introspected via SQL editor), so a `draft` is genuinely invisible.

**Prevention:** Two-phase publish — INSERT the brief as `status='draft'`, POST all children, then `PATCH status='published'` as the LAST call. A failure anywhere before the flip raises, leaving a draft (invisible) that the next publish's DELETE clears. Regression test `test_publish_brief_stays_draft_when_child_post_fails` asserts a child-POST failure raises AND never flips to published; `test_publish_brief_atomic_flow` now asserts DELETE → draft-INSERT → children → published-PATCH-last order.

**Hotfix:** `brief/v6_publisher.py::publish_brief` rewritten two-phase (this PR). No migration needed — `briefs.status` already NOT NULL default `'published'` with no CHECK, accepts `'draft'`; `get_latest_brief` already filters published.

**Cross-references:** AGENTS.md landmine 22 (updated: hole now closed), landmine 18 (#118 orphan); 2026-05-29 v1.5.1 entry (original #118); handoff `docs/handoff/2026-07-04-review-fixes.md` item 4.

## 2026-07-09 — SPA | Masthead showed a hardcoded fake clock ("14:02 BST"), wrong TZ everywhere

**Trigger:** 2026-07-04 ecosystem review (handoff item 2). The masthead's Live indicator rendered a literal `14:02 BST` string next to the pulsing dot — a fabricated, frozen clock that never reflected reality and used the wrong timezone label (BST = British Summer Time; the product is Asia/Dhaka, BDT). `SubscribeCTA` compounded it with "7am BST" / "7am sharp" in three places (wrong time AND wrong TZ; publish is 06:30 BDT).

**What went wrong:** a placeholder from a design mockup shipped as if it were live data. `StatusBar.tsx` already had the correct implementation (inline Asia/Dhaka formatting of `_fetchedAt`), but the masthead didn't reuse it — and `_fetchedAt` lived on the `BriefPayload` root, un-plumbed into Masthead's props. A fake timestamp next to a "Live" dot is a credibility leak on a product whose whole pitch is timely, accurate data.

**Lesson:** never ship a hardcoded time/number as if it were live; if a real value exists elsewhere (here `_fetchedAt` in StatusBar), plumb it rather than fake it. And label the timezone the product actually runs in — BDT, not BST.

**Prevention:** Masthead now takes a `fetchedAt` prop (plumbed from `ClientApp` → `data._fetchedAt`) and formats it Asia/Dhaka like StatusBar, dropping to just the source label when no fetch time exists (never a fabricated clock). SubscribeCTA copy fixed to "06:30 BDT" ×3. Housekeeping PR also corrected AGENTS.md landmines 17/21 ("Saturday skipped" → 7 days/week post-#116) — same family of stale-time drift.

**Cross-references:** `app/components/Masthead.tsx`, `StatusBar.tsx` (reference impl), `SubscribeCTA.tsx`; handoff `docs/handoff/2026-07-04-review-fixes.md` item 2; Master.md ("06:30 BDT", never "early morning").

## 2026-06-07 — PR #114 | Economist/FT voice retune shipped — two shipping-mechanics traps caught

**Trigger:** Retuning the Desk Editor + Sub-Editor voice to an Economist/FT four-dial register, then shipping it before the next scheduled send. The voice change itself was clean (verified via a no-prod dry-run render); two *non-voice* traps surfaced during the ship.

**What went wrong:** (1) **Merge ≠ deploy.** After merging #114 to `main`, the new prompts were NOT live — `brief.service` `ExecStart` is just `python -m brief.cli run --publish` with no `git pull`, and Hetzner's checkout sat 1 commit behind. A scheduled run would have shipped the old voice. (2) **Wrong "redundant commit" call during a `main` sync.** Syncing the diverged local `main`, I judged two unpushed commits redundant by reading the LOCAL working-tree `AGENTS.md` (which of course still contained them) and dropped both via `git rebase --onto origin/main c043082 main`. One (`855449c`/#18) was genuinely on origin; the other (`c043082`/Context7 #19 rail) was NOT — it existed only locally. I briefly dropped real work.

**Lesson:** (1) On The Brief a GitHub merge deploys nothing — the box must `git pull` before the timer fires. (2) Never judge a local commit "already upstream" by reading the local file; verify against `origin/main` directly.

**Prevention:** (1) After any merge that must reach a scheduled brief, `git pull --ff-only origin main` on Hetzner and confirm `HEAD` == merge commit (now AGENTS.md landmine 21). (2) Before dropping "redundant" local commits, run `git cherry -v origin/main main` (commits with an equivalent already upstream are marked `-`) or `git grep <content> origin/main -- <file>` — never a read of the local working tree.

**Hotfix:** (1) Pulled Hetzner to `8a4be52`, verified the new prompts on the box. (2) `git cherry-pick c043082` restored the Context7 rail (now `d92eb9c`; `main` ahead 1, unpushed — Adnan's call to push).

**Cross-references:** AGENTS.md landmines 20 (Editor↔Sub-Editor voice lockstep) + 21 (merge ≠ deploy); auto-memory `project_brief_editor_voice_register`; source preference `feedback_communication_tone_economist_ft` (econdelta memory dir).

## 2026-06-07 — PR #113 (chart) + this PR (caption) | F7b NBR chart shipped, but its chart_read named the wrong metric (stale editor chart-list)

**Trigger:** F7b added the §Fiscal section's first chart (NBR monthly tax revenue, FIG.09). After a manual publish the chart rendered perfectly — but its `chart_read.signal` read "LATEST: GOVT BANK BORROW YTD 1.25" (the section's *borrow* headline), not the NBR series it plots.

**What went wrong:** Two things. (1) The editor prompt (`brief/claude/prompts/editor_v6.txt:68` + `editor_v6_friday.txt:69`) hard-ENUMERATES the chart-bearing sections — "dse, iran/brent, tbond/yieldCurve, fx/fxFlows, macro/cpiTrend" — and the list was STALE: it never gained `fiscal` (nor `bb`/`remit`). With §fiscal absent, the editor didn't know the chart plots NBR and anchored chart_read on the section's headline (govt bank borrow). (2) Data-lineage trap: §Fiscal's headline CARDS (`fiscal_*_trn` YTD) come from a separate external MoF/IMED/BB pipeline, while the new CHART plots EconDelta's `nbr_revenue_monthly_cr` (monthly, BDT crore) — two different metrics in one section, so "describe the chart" must name which series.

**Lesson:** Adding a chart to a NEW section is not just `SECTION_TO_CHART` + a builder — the editor prompt's chart-bearing-sections enumeration must also gain the section + its charted metric, or the LLM `chart_read` mislabels (especially when the section's headline metric differs from the charted series).

**Prevention:** When wiring a chart for a section whose chart metric ≠ its headline metric, add `<slug>/<configKey> (charts <metric_id> — <what it is>)` to the chart-read list in BOTH `editor_v6.txt` and `editor_v6_friday.txt`, naming the series so `chart_read.signal` describes the chart, not the headline. The enumeration is also currently missing `bb`/`remit` — refresh it when next touching the prompt. (Worth an AGENTS landmine.)

**Hotfix:** PR #113 shipped the chart (correct). This PR adds `fiscal/fiscalNbr` + an NB to both editor prompts; it applies at the next scheduled publish (no off-cycle re-publish — verify the live chart_read then).

**Cross-references:** §Fiscal data lineage (cards = external `fiscal_*_trn`; chart = EconDelta `nbr_revenue_monthly_cr`); upstream backfill = econdelta auto-memory `project_econdelta_fiscal_backfill`; the 2026-05-31 PR #107 entry (landmine #17).

**Aside — an SSH-dropped manual publish looks stuck but succeeds:** the F7b manual `brief.cli run --publish --no-notify` over `ssh hetzner` had its connection drop ~22s in (right after the editor-stage log line); the captured output FROZE and looked hung/failed, but the remote pipeline kept running and published issue 130 ~22 min later. Verify a long manual publish via the DB (`briefs.issue_no` / `published_at` jumped), NOT the frozen SSH output. `--no-notify` correctly suppressed the subscriber email.

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
