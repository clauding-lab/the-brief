# Changelog

All notable changes to The Brief are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- P2 post-editor number/period fact-checker (2026-08-22 audit #204, round-2 follow-up): a new deterministic gate reads the editor/sub-editor's final output back against the deterministic BUILDER values (never the editor's own formatted text) before every publish. A sourceless "across fourteen reads" style count-claim still HOLDS the publish outright (corpus-verified: 14 true positives, 0 false positives across 25 real published issues once narrowed to reads/prints only). Everything else — a metric's `sub` citing a figure or period that doesn't trace to the builder data, or a metric's own headline `value` diverging from its raw source — is logged and sent as one grouped Discord alert per publish, not yet held; a `BRIEF_PROSE_VALIDATOR_STRICT=1` flag exists to promote these to the same hard-fail once production log volume shows a low false-positive rate. Every published metric now also carries a deterministic `period` label so the editor never has to guess a month/quarter, and a compact chart digest (`series_summary`) replaces a prompt claim that was simply false (the editor never actually received a chart's full data).

### Changed
- **User-visible:** the FX & External section's freshness badge now reflects its stalest constituent metric (reserves, exports, trade gap) instead of only the spot rate and Gold, both of which refresh daily and could never age. On today's real data shape this section now correctly reads "stale" instead of a false "fresh" — flagging for Adnan's sign-off per VISION.md's "ask twice" rule for anything readers see in tomorrow morning's brief.

### Fixed
- Front page and subscriber emails were printing false or fabricated numbers (2026-08-22 audit #204). Remittance and exports cards read a daily "flash" figure instead of the official monthly final; the trade gap and import cover silently mixed figures from different reporting months; the "real policy rate" paired a post-rate-cut repo reading with a pre-cut inflation print; a stale-data footer said a number was "overdue," implying Bangladesh Bank hadn't published when the pipeline only knew its own copy was old; the AI editor could copy exact figures forward from yesterday's brief verbatim, and had separately invented a "$80 FY27 crude" budget assumption with no basis in Bangladesh's actual budget; the subscribe box claimed a fabricated reader count and a one-click unsubscribe that doesn't exist; the unsubscribe email pointed at a different mailbox than the one it was actually sent from, and logged full subscriber addresses on send failure.
- Review round 1 fixes to the above (same audit): the hallucination denylist is now scoped to prose only and requires FY27/$80/crude/budget context before flagging "$14.09" — the original version would have held every publish for up to a year on a chart value that happened to end in those digits. Import cover's freshness gate widened from >1 month to >4 months to match how Bangladesh Bank's own methodology mixes a near-current reserves reading against a lagged monthly import figure — production's real 4-month gap was being wrongly suppressed, which flipped an honestly "stale" macro badge into a false "history is accumulating" one. Unsubscribe now uses a dedicated, verified-deliverable address, separate from the technical sending address; the Brevo List-Unsubscribe header ships feature-flagged OFF pending a controlled real-send test.

---

## [2.0.2] — 2026-08-11

### Removed
- The "In this issue" rail in the masthead. It re-listed the first twelve headlines from §01, which the reader then met again in full a screen later — duplication that pushed the first real content further down without adding a way to navigate that `SecNav` did not already provide. The masthead hero is now a single column: wordmark, tagline, Today's Call.

---

## [2.0.1] — 2026-08-09

### Fixed
- The editor's answer is no longer discarded when the model thinks first. With `--effort xhigh` the Claude CLI splits one assistant message into two stream events sharing a `message.id` — thinking, then text — and de-duplicating by that id dropped the event carrying the brief. Nothing was collected, so the reader silently fell back to the CLI's final-message-only field: the exact data loss the v1.6.x stream stitching was written to prevent, on every editor call since. It stayed invisible until a payload was cut off, then the pipeline received the tail and rejected a fragment — two lost publishes (#190, #192).

---

## [2.0.0] — 2026-08-08

First tagged release since v1.5.1 — 59 merged PRs (#103–#160) over ten weeks. Full narrative release notes live on the GitHub release page.

### Changed
- Daily publish moved from 06:30 to 08:00 BDT so every issue reads same-morning EconDelta data instead of yesterday afternoon's (#149); publishes all seven days including Saturday (#116).
- Editorial voice recast to an Economist/FT register, with the sub-editor's checks updated in lockstep (#114).

### Fixed
- Sub-editor safety gate no longer fails open: malformed reviews retry once then hold the publish; protected metrics (SDF/SLF corridor and peers) are force-reinserted if the editor drops them, and a publish blocks if they are still missing (#126, #151, #158).
- Macro section renders every stored metric — a hardcoded five-tile cap had been silently discarding CPI 12-month average, M2 growth, and REER (#157).
- Frozen policy rates no longer read as "fresh"; every figure carries a visible data-age stamp for both the AI editor and the reader (#142–#145).
- Numerous dead-source repoints (DSEX tile, DSE tiles, corridor/reserves), timezone-date bugs, and a two-phase publish so a crash can never leave a half-visible issue (#123, #124, #125, #136, #152, #154).

### Added
- Five new charts (two-line reserves, 8-tenor yield ladder, external flows, DSE top movers, NBR revenue trend) and Long View essays (#105–#113, #159).
- Failure alerting (service crash, zero-recipient sends), daily off-site health check, weekly archive export, and self-updating deploys (#127, #129, #131, #133–#135).
- Server-side hardening of the subscribe endpoint: validation, honeypot, rate limit, header-injection protection (#128).

### Security
- CI test workflow (python-tests + web-build) now gates every PR (#156).

## [1.6.9] — 2026-08-04

### Changed
- **The daily publish moves from 06:30 BDT to 08:00 BDT** (`brief.timer`: `00:30 UTC` → `02:00 UTC`). The old time put this pipeline *ahead* of the data it reads: EconDelta's `aggregate_latest` stage ran at 13:00 BDT, so every brief was built on an aggregate roughly **17 hours old** — yesterday afternoon's — and any upstream fix landing in the morning could not reach the next morning's issue. EconDelta's chain moves to the small hours in the companion change (fetch ~01:30, aggregate ~02:55 BDT), leaving about five hours of headroom before this fire.
- **Reader-facing copy follows the timer.** `SubscribeCTA.tsx` states the delivery time in three places (hero line, form eyebrow, post-signup confirmation); all now read 08:00 BDT. Leaving them would have promised subscribers a delivery time they no longer get.
- `Master.md` copy convention updated to the new time (contract file — changed on the owner's explicit instruction to reschedule).
- README: cadence table, architecture diagram, deployment table, and the stale `Mon–Fri + Sun` cadence badge (7 days/week since PR #116) all corrected; version badge unstuck from 1.5.1.

### Added
- **Landmine 32** — the publish time and EconDelta's aggregate are one schedule, not two. Records the constraint that binds them: EconDelta's LLM parse stage must stay clear of ~05:00–06:00 BDT (16:00–17:00 US Pacific, Anthropic's peak), where its preflight failed 12 consecutive times in May 2026. That is what sets how early this brief can fire.

### Known limits
- **The two repos cannot test each other.** Nothing here fails if EconDelta's timers move back; the coupling is documented, not enforced.
- **This does not ship itself.** `brief.timer` lives in `/etc/systemd/system/` and needs a root copy + `daemon-reload` on Hetzner. Because the unit is `Persistent=true`, reloading after 02:00 UTC on the switch-over day makes systemd treat that slot as missed and fire an immediate catch-up publish. The safe window is between the old fire and the new one.

### Tests
- No behavioural code changed; the notifier derives its printed time from the run timestamp rather than a constant, so no test was pinned to 06:30.
- Full suite green: **721 passed**, 91% coverage. (The 1.6.7/1.6.8 entries state 716/719 — those came from counting progress dots by eye rather than from `--collect-only`, and are each short by two. The counts are wrong; the "green" is not. Left uncorrected because CHANGELOG history is sign-off-gated.)

---

## [1.6.8] — 2026-08-04

### Removed
- **`brief/builders/dam.py` (DAM Food Prices, nine items) is deleted.** It shipped in the original 9-builder batch, was never registered, and had never run: `gather()` iterates `ALL_BUILDER_IDS`, `dam` was in neither `SPINE_BUILDER_IDS` nor `KEEP_BUILDER_IDS`, so the module was never imported and its nine metrics were never built. Removed at the owner's decision after the alternative — shipping it — was weighed and declined: its nine ids had been frozen at byte-identical values for **92 days**, so publishing the section would have meant putting a three-month-old rice price in front of a bank treasury.
- **`"dam"` removed from `SECTIONS_WITHOUT_LEGACY_BACKFILL`** in `brief/cadence.py`. This is the part that was live. Membership in that set promotes an "unavailable" badge to **"warming_up"** — "history is accumulating, expect this shortly". It was making that promise on behalf of a section that could not exist, so it could never be kept, and nothing anywhere would have reported it.

### Fixed (documentation)
- **A wrong finding published in 1.6.7 is corrected.** That release's *Known limits* said `dam` "builds nine food-price metrics every day that no reader ever sees" — built and then discarded by the `V5_TO_V6` map. It was never built. The map was the wrong place to look; the registry tuple decides. The 1.6.7 entry and landmine 30 now carry the correction rather than a silent edit, because "check the registry before the map" is the lesson.

### Known limits
- **Deleting the reader does not fix the data.** EconDelta still collects these prices and they are still frozen. That is an EconDelta scraper fault and is tracked separately.
- The upstream cause remains the same class of bug as the policy-rate and gross-reserves incidents: a series that stops moving while its timestamp keeps refreshing reads green everywhere. Stillness detection is the next change.

### Tests
- 5 new in `tests/builders/test_dam_deleted.py`, including a general-form guard that **every id in `SECTIONS_WITHOUT_LEGACY_BACKFILL` is a section something can actually build** — the leftover that caused this one would now fail at the suite instead of surviving for months.
- Full suite green: **719 passed**.

---

## [1.6.7] — 2026-08-04

### Removed
- **§12 Commodities is gone.** It carried two tiles. LNG's only live source is a World Bank Pink Sheet series whose download URL is edition-pinned upstream and has frozen silently before — v1.6.6 had just repointed it off `comm_lng_jkm`, which died 2026-04-20 after printing the same 15.00 for 105 days. Gold was the only genuine daily reading in the section, and a one-tile section is not a section. LNG is not re-homed: a monthly Japanese contract-average import price is a commodity-desk number, and this brief is not a commodity desk.
- `brief/builders/comm.py` deleted; `comm` dropped from `SPINE_BUILDER_IDS` and from `V5_TO_V6`. **Ord 12 is left unused rather than renumbered** — ords only have to sort, and reusing a retired slot would silently re-home whichever future section inherited it.
- **`fx_monthly_remittance`, a duplicate.** §05 printed it as "2.82 bn USD" while §11 Remittance printed `remit_monthly_mn` as "2820.0 mn USD" — the same Bangladesh Bank figure, twice, in one issue, under one label. The copy went; §11 is the section that exists to report it.
- **`fx_eur_bdt`.** The editor prompt caps a section at 5 metrics and *chooses* which to drop; EUR/BDT was the one it was already discarding on its own.

### Changed
- **Gold moved to §05 FX & External**, unchanged in value, unit, source and cadence — it reads the same `gold_usd_oz` key off the same EconDelta snapshot. It is a reserve asset, so it sits with reserves rather than in a card of its own. FX now ships exactly 5 metrics, which is the cap, so every remaining tile publishes instead of competing for a slot.
- **Gold joins the FX freshness badge.** FX computes its badge from spot rates only — deliberately, so that a 30-day-old reserves print does not drag the whole section into "stale". Gold is stamped with today's date every run and so can never age into stale, but a snapshot that stops carrying `gold_usd_oz` yields `value = None`, which scores "unavailable". Adding it keeps the disappearance visible. `comm`'s badge used to provide that signal, and dropping it silently would have been the regression — it is how LNG survived 105 days.

### Known limits
- **This does not fix the class of bug that killed the LNG tile.** A frozen series that keeps a fresh timestamp still reads green anywhere it is daily-restamped. That is now the third occurrence in this codebase (policy rate, DAM food prices, gross reserves), and stillness detection is proposed separately, not smuggled into a section removal.
- **`brief/builders/dam.py` is a nine-metric Food Prices builder that has never run.** Ship-or-delete is a decision, not a cleanup, so it is left for its own change. Recorded as landmine 30. *(Corrected in 1.6.8: this entry first said the section was built daily and dropped by the map. It was not built at all — `dam` is absent from `ALL_BUILDER_IDS`, which is the tuple `gather()` iterates, so the module was never imported. The conclusion was unaffected; the mechanism as published was wrong.)*

### Tests
- 10 new tests in `tests/builders/test_commodities_retired.py`, organised around the three ways a section removal goes half-right: the slug surviving in a map the builder no longer backs, Gold's *value* silently changing during the move, and Gold's disappearance ceasing to be visible. Plus one in `tests/test_pipeline_v6_phase_a_sections.py` pinning that `_to_v6_raw` **drops** a section id the map does not know — which is both why the map entry had to go and why `dam` has never shipped.
- Full suite green: **716 passed**.

---

## [1.6.6] — 2026-08-03

### Removed
- **Three metrics that had never once had a value.** `fiscal_nbr_target_trn` ("NBR full-year target"), `fiscal_adp_pct` ("ADP utilisation") and `remit_yoy_pct` ("YoY %") were wired into shipping sections and have **zero rows in `metric_history` and `metric_history_monthly`** — not stale, never written, by any scraper in either repo. They rendered as permanently blank tiles.
- The blank tile was the harmless half. `value is None` scores "unavailable", and `section_freshness` promotes that to **"warming_up"** for the five `SECTIONS_WITHOUT_LEGACY_BACKFILL` sections — so **Fiscal** and **Remittance** told readers data was accumulating and would arrive shortly, indefinitely, for ids with nothing behind them. Both sections now read **"fresh"**, which is what their live metrics had been all along.
- The real loss is the NBR target: "NBR collected YTD 3.61 trn" wants "against an X trn target" beside it, and that is the half a desk acts on. It is a published budget figure, so the fix is to source it — deliberately **not** to hardcode a constant, which is how the policy corridor came to print a superseded 10.0% for weeks (landmine 24).

### Changed
- **The LNG tile now reads a series someone still writes.** `comm_lng_jkm` was last written **2026-04-20** and has no scraper in either repo; it had been printing 15.00 USD/MMBtu for **105 days**. The comm builder now reads `lng_price_usd_mmbtu`, which EconDelta's World Bank Pink Sheet scraper writes monthly (12.83, 30 Jun 2026 — 34 days old).
- **Relabelled "LNG JKM" → "LNG (Japan)", source → "World Bank Pink Sheet", cadence weekly → monthly.** These are *different series*: the Pink Sheet's "Liquefied natural gas, Japan" is Japan's monthly average **import** price, contract-weighted; JKM is a spot cargo marker. Carrying the old label over the new value would print one market's price under another market's name, and this brief's readers price LNG for a living. The cadence change matters too — a monthly series judged on a weekly clock reads stale within days of every print.
- This is not a permanent fix and is not claimed as one: the Pink Sheet scraper's download URL is edition-pinned upstream and has silently frozen on a stale edition before. The improvement is that when it stalls, v1.6.4's vintage now dates it on the page instead of letting it go quiet.

### Known limits
- **A future-dated `as_of` still reads as "fresh"** and gets no vintage — every branch of `metric_freshness` computes `today - as_of` and compares upward, so a negative age lands in the first bucket. EconDelta writes IMF projections dated 2027–2031 into `debt_gdp_ratio`, an actuals id. No Brief builder reads that id, which is the only reason a 2031 forecast has not printed as a current number. Not fixed here: some future stamps are legitimate (the Pink Sheet stamps `as_of` at the reporting month's last day), so the fix is a per-cadence tolerance and a change to freshness semantics across every metric — proposed, not smuggled into this release. Recorded as landmine 29.

### Tests
- 10 new tests in `tests/builders/test_dead_metrics.py`, including that the dead ids are **not even queried** (a removed metric that still costs a round-trip is half-removed), that a genuinely missing row *still* degrades the section (the removal must not buy a green badge by disabling the signal), and that a frozen Pink Sheet surfaces as old rather than silent.
- Full suite green: **712 passed**.

---

## [1.6.5] — 2026-08-03

### Removed
- **`vintage.next_print` — it was unreachable by construction.** v1.6.4 shipped a next-print hint (`as_of` + a per-cadence interval). A vintage only exists once a metric is past its cadence's **fresh threshold**, and every fresh threshold is *longer* than that cadence's publication interval — monthly 35 vs 30, weekly 7 vs 7, quarterly 95 vs 91, daily 1 trading day vs 1 — so `as_of + interval` had **always already passed** by the time anything asked for it. It could not have been right for any metric, on any day. Caught by running the merged code against production, where REER rendered as *"As of 2026-03-01 · next print **Mar 2026**"* — a next print in the same month as the as-of.
- Rolling it forward to the next *future* period was considered and rejected as the worse fix. REER has never been collected by anyone; any date offered would be an invented schedule, and this module's entire value is that its output can be trusted. "Overdue" is already in `note` — a fact rather than a forecast.
- `stamp_vintages` no longer writes `next_print` at all. The field stays on the published metric and in the SPA footer: `mark_held_overs` reads a real publication date and is the only thing entitled to write it, so blanking it here would clobber that path the day the catalog is fixed.

### Tests
- The v1.6.4 test asserted `next_print == "Mar 2026" or next_print == "Apr 2026"` — an either/or that **accepted the broken answer**. Replaced with a test that the field does not exist, carrying the threshold-vs-interval proof in its docstring, plus one that stamping leaves a catalog-set `next_print` untouched.
- Full suite green: **702 passed**.

---

## [1.6.4] — 2026-08-03

### Added
- **Per-metric vintages.** Every number now carries its own age, computed from its own `as_of` and cadence — no catalog lookup, nothing to migrate. Anything past its cadence's *fresh* threshold gets a period label ("Mar 2026", "Q1 2026"), an age in days, and a next-print hint. A fresh metric gets nothing: "as of today" on today's number is noise, and noise is how a real staleness signal gets ignored.
- **The editor is told which numbers are old, before it writes.** `as_of` already reached it inside the metric dump, but a bare date carries no threshold — nothing said 2026-03-01 was five months back. Issue #184 printed *"REER at 102.78 keeping the taka dear as the peg eases to 123.82"*: a March index and that day's spot rate in one clause. The section-level `freshness` badge could not have prevented it — it is worst-of, so it says a section *contains* something old without saying which metric, and it says nothing at all when a stale number is borrowed into another section's prose. The prompt now carries a hard rule against pairing a vintaged number with a current one without naming the vintage.
- **The vintage is stamped onto the published metric too**, so the footer and the prose cannot contradict each other.

### Fixed
- **The "held from" footer has never rendered once.** Shipped in v1.2.0; its only writer, `mark_held_overs`, reads `section_slug` and `last_print_date` off `metric_definitions`, and **production has neither column** (79 rows, 18 columns, verified 2026-08-03). Every lookup missed: **0** of the last 1000 published metric rows carry `held_from`, 0 carry `next_print`. The footer, its CSS and its render branch have been live and unreachable for months, and nothing surfaced it — a no-op that writes nothing looks exactly like a no-op with nothing to write. `stamp_vintages` now populates the field from the metric's own `as_of`, runs *after* `mark_held_overs`, and never overwrites it.
- The footer reads **"As of 01 Mar 2026"**, not "Held from" — a monthly index published in March is not being *held*, it is simply March's number.
- The footer no longer hides when `changed` is true. A number can move *and* still be five months old — the first issue after a source repoint is exactly that case, and that is precisely when the reader needs the date.
- `formatVintageDate` pins the date to Asia/Dhaka. A bare ISO date parses as UTC midnight, which renders as the previous day anywhere behind UTC — the same hydration mismatch (React #418) already fixed for news dates.
- `pipeline_v6` now logs `vintaged_metrics=%d`, so a run that stamps nothing is visible in the journal instead of looking like a quiet day.

### Known limits
- Vintages are computed from `as_of`, which for `event`-cadence metrics is a daily *restamp* date, not a decision date (landmine 24). Those are worded "last confirmed …" and carry no next-print, because an MPC has no schedule to promise.
- A next-print hint is a coarse cadence-plus-N guess, not a release calendar. No BB/BBS publication schedule is wired in.
- `mark_held_overs` remains broken; this release routes around it rather than fixing the catalog. Fixing it means a migration adding `section_slug` and `last_print_date` to `metric_definitions` and a writer for them.

### Tests
- `tests/test_vintage.py` — 22 new: when a vintage exists at all (fresh → none, warning band → yes, `value=None` → none, unknown cadence → none rather than a guess); period labels at the precision the cadence carries (a monthly series has no meaningful day-of-month); event-cadence wording and its empty next-print; the literal #184 REER case at the age it actually had; the editor payload's exact keys; and stamping — including that it never overwrites `mark_held_overs`, that a moved-but-old metric is still stamped, that an editor-invented label gets no vintage, and that a vintage cannot leak across sections sharing a label.
- Full suite green: **700 passed**.

---

## [1.6.3] — 2026-08-03

### Fixed
- **§03 Macro & Inflation was reading a dead table.** All 8 macro metrics were fetched from `metric_history_monthly`, which has **no live writer** — its newest period is 2026-05-01 and the newest ingest of any kind is a 2023 backfill. Every macro number The Brief has printed since was **155–183 days old**, while EconDelta had current readings for most of them sitting in `metric_history` the whole time. Five of the eight are now repointed; each metric declares where its value comes from instead of all eight sharing one hardcoded table.
  - **Direct repoint (3):** `cpi_p2p_food_monthly` → `food_inflation`, `cpi_p2p_nonfood_monthly` → `non_food_inflation`, `private_credit_growth_yoy_monthly` → `private_sector_credit_yoy_pct`. Published ids are unchanged — only the source moves.
  - **Derived (2):** Real Policy Rate = `policy_rate_repo` − `general_inflation`; Import Cover = `gross_reserves_usd_bn` ÷ `monthly_import`. Both formulas were confirmed by reproducing the figures issue #184 actually printed (1.29% = 10.00 − 8.71; 5.86 months implies a 5.82bn monthly bill against a collected 5.8), not inferred from the metric names.
  - A derived figure is dated by its **stalest** input, never its freshest. #184 printed a March REER beside that day's spot rate in a single clause because nothing recorded that the two were months apart.

### Known limits
- **Three metrics stay old, and this release does not pretend otherwise.** REER appears in no table, ever. CPI 12-month-average is a different published measure from the point-to-point series EconDelta collects, so it cannot be derived from it. M2 YoY needs 13 months of `broad_money` and only 4 exist. Each needs a scraper, not wiring. They keep reading the archive rather than being blanked, because `section_freshness` is worst-of — so their real age keeps §03 honestly labelled **stale**. The section does **not** start claiming to be fresh because five of its eight metrics now are.
- History facts ("lowest since…") remain archive-only. The live series hold ~4 months restamped across many dates — `food_inflation` is 37 rows carrying 6 distinct values — so anchors computed over them would be counting restamps as observations. Revisit once the live series carry a year of genuine monthly points.

### Tests
- `tests/builders/test_macro.py` rewritten around the three-way split: live metrics read `metric_history` and only that table, archive metrics still read `metric_history_monthly`, both derivations reproduce their arithmetic, a derived metric is dated by its stalest input, a missing input or a zero denominator yields `None` rather than an invented number, and a raising history client cannot take the section down.
- The honesty guard is explicit: with the three archive metrics five months old, `section.freshness == "stale"` — while the five repointed metrics on their own compute `fresh`.
- Full suite green: **678 passed**.

---

## [1.6.2] — 2026-08-03

### Fixed
- **§02 Policy & Rates could not report staleness — under any circumstance.** `metric_freshness` returned `"fresh"` for every `cadence="event"` metric unconditionally, and the BB policy corridor is the only user of that cadence. When EconDelta's corridor froze at the pre-cut 10.00% repo rate, The Brief printed it for four days (#181–#184) with §02's badge reading **fresh** the entire time. The freshness system was not broken; it was pointed at nothing. Event cadence is now a **writer-liveness check**: EconDelta re-stamps these rows daily, so ≤7 days since the last restamp reads `fresh`, ≤10 days `warning`, beyond that `stale`. A standing rate that has not *moved* in years still reads fresh — only a writer that stops confirming it goes stale.
- **`Metric.stale` was decorative.** `bb.py` marks a corridor rate `stale=True` when it falls back to a last-known constant, and its docstring promised an outage "never presents a possibly-outdated rate as current" — but nothing read the flag. A total `metric_history` outage rendered §02 as **fresh** while printing three hardcoded constants. `metric_freshness` now honours `stale=True` on event metrics. Scoped to event cadence deliberately: every other builder's fallback carries a real historical `as_of` and already ages correctly.
- **The corridor fallback constants held the PRE-CUT rates.** BB cut the repo 10.00 → 9.50 and the SLF 11.50 → 11.00 on 2026-07-30, its first cut in six years. `_FALLBACK_POLICY_RATE_PCT` / `_FALLBACK_SLF_PCT` still read 10.0 / 11.5 four days later, so a history outage would have printed a corridor that no longer existed. Now 9.50 / 7.50 / 11.00, pinned to `_LAST_MPC_DECISION = 2026-07-30`, and a fallback metric now carries the decision date as its `as_of` instead of today's.

### Tests
- 5 new event-cadence tests in `tests/test_cadence.py`: fresh-while-restamping, warning at 9 days, **stale when the writer stops** (the case that returned `"fresh"` before), fallback-stale-even-when-stamped-today, and a guard that the `value=None` → `"unavailable"` check still runs ahead of the event branch.
- 3 new tests in `tests/builders/test_bb.py`: the fallback constants no longer equal the retired pre-cut corridor (the same shape of guard that keeps the retired 8.5 SDF from resurfacing), a full history outage forces `section.freshness == "stale"`, and a corridor whose rows stopped being restamped goes stale while still rendering its values.
- Full suite green: **670 passed**.

### Followup
- `AGENTS.md` landmine #24 rewritten: event cadence is bounded, and the `_FALLBACK_*_PCT` constants are now a documented per-MPC-decision maintenance item.
- Not covered here: §03 Macro still reads `metric_history_monthly`, which has no live writer (all 8 metrics 155–183 days old). That is a read-path repoint, tracked separately.

---

## [1.6.1] — 2026-08-02

### Fixed
- **The editor's brief is no longer thrown away when it outgrows one response.** When the payload crosses the model's per-response output cap, the editor is cut off mid-JSON and continues in a NEW assistant message. `--output-format json` reports only the FINAL message in `result`, so the pipeline received the *tail* of the brief; `_extract_json_object` then salvaged the first balanced object out of that tail — a lone section — and Pydantic rejected it with 18 `extra_forbidden` errors. `run_max` now reads `--output-format stream-json --verbose` and stitches every assistant text block in arrival order, reconstructing the payload byte-for-byte. Five publishes died this way: #181 (three runs, 2026-07-31) and #183 (two runs, 2026-08-02).
- **The cut-off alarm now actually fires.** The v1.6.0 alarm was gated on `parsed is None and num_turns > 1`. Both halves were wrong: the preamble fallback rescues a fragment so `parsed` is not None, and a cut-off-and-continued response is still ONE turn so `num_turns` stays 1. It stayed silent through two further production failures. Detection now keys on `MaxCallResult.assistant_messages` and fires whether or not the stitched payload parsed.

### Changed
- **`DEFAULT_MAX_OUTPUT_TOKENS` documented as a no-op against the current model.** 64,000 is the hard per-response cap on `claude-opus-4-8` — requesting 128,000 returns 64,000 — so v1.6.0's pin set the value to what it already was and bought no headroom. The constant stays (it is still what the CLI is told, and becomes meaningful again if a future model raises the cap) but is no longer presented as the fix.
- `MaxCallResult` gains `assistant_messages`; `num_turns` is still surfaced but is no longer load-bearing.

### Tests
- 19 new tests in `tests/claude/test_max_client_stream_stitching.py`: multi-message stitching (including the exact #183 tail-fragment signature), duplicate-event de-duplication, `thinking`-block exclusion, non-JSON noise tolerance, usage/cost from the result event, alarm-fires-when-parsed and alarm-fires-at-num_turns-1, and backward compatibility with the single-object `json` payload shape.
- Verified against the real CLI with a forced-truncation probe (`CLAUDE_CODE_MAX_OUTPUT_TOKENS=1200`): 3 assistant messages, stitched output parsed clean.
- Full suite green: 663 passed.

### Followup
- New `AGENTS.md` landmine #26 and an `AGENT_LEARNINGS.md` entry for 2026-08-02.

---

## [1.6.0] — 2026-06-12

### Added
- **Long View: side-by-side stat + chart pairing.** When a `bar-chart` block directly follows a `stat` block, the Long View now renders them as a single paired card — the stat on the left (~60%), the compact bar-chart on the right (~40%) — instead of two stacked full-width blocks. The chart's SVG auto-scales into the narrower column, reading as a glanceable companion to the headline number; below 700px the pair stacks vertically. No schema change: pairing is driven purely by block order in `content/long-view.ts` (a `bar-chart` after a `stat`), keeping layout out of the pin data per the Long View contract. New `.tb-longview-pair` style in `app/globals.css`; grouping pass in `app/components/LongView.tsx`.

---

## [1.5.1] — 2026-05-29

### Fixed
- **v1.4.0 publish regression unblocked.** The v1.4.0 banker-grade editor prompt occasionally emitted `MetricV6.value` as a raw number (e.g., `35.1112`) and `MetricV6.delta` as a structured `{value, direction, window}` dict where the schema previously required pre-formatted strings. Every publish since v1.4.0 (Thursday #118 and Friday #119) failed Pydantic validation before reaching Supabase. `MetricV6` now ships two `field_validator(mode="before")` coercers that stringify numerics (preserving precision via `:.10g`) and render the delta dict as banker-style `"+0.99% WoW"` / `"−0.99% WoW"`. Pre-formatted strings still pass through unchanged.
- **Adjacent test fix:** `tests/test_cli.py::test_write_fixture_creates_valid_json_on_dry_run` had a stale mock signature missing the `preview_notify_enabled` kwarg added in v1.5.0 (PR #98). Now accepts the flag.

### Schema migration shipped separately (also part of the v1.4.0 unblock)
- **`migrations/0004_section_chart_read.sql`** (PR #99, merged earlier today) — added the `chart_read` jsonb column to the production `sections` table. v1.4.0 shipped the Pydantic + SPA render for `Section.chart_read` but skipped writing the matching SQL migration, so the first publish under v1.4.0 (Thursday) blew up with `PGRST204: column not found` and Brief #118 ended up orphaned in production (status=published, 0 sections / 0 metrics / 0 news). Migration applied, schema cache reloaded, PostgREST now sees the column.

### Tests
- 9 new tests on `MetricV6.value` / `MetricV6.delta` covering: string pass-through, int + float coercion (with precision preservation), delta-dict rendering for up/down directions with and without window, plain-string passthrough, None passthrough, numeric delta coercion.
- Full suite green: 545 passed in 161s.

### Followup
- Append `AGENT_LEARNINGS.md` entry: "code-schema and DB-schema must ship together — when adding a field to a Pydantic / TS type that flows to Supabase, write the matching SQL migration in the SAME PR." Distill into a new `AGENTS.md` landmine alongside #7.
- After merge: re-fire Thursday's #118 (`brief.cli run --publish --today=2026-05-28`) to overwrite the orphaned brief with full sections; then re-fire Friday's #119 (`--today=2026-05-29`) as a normal weekly_wrap retry.

---

## [1.5.0] — 2026-05-27

### Added
- **Preview-ready notifications.** New module `brief/preview_notify.py` sends two pings when the pipeline runs in dry-run with `--write-fixture` and the new `--preview-notify` flag: a Discord webhook message and a Brevo email to a dedicated recipient (NOT the subscriber list). Each channel is independent — one failing does not block the other. The ping includes the production-reachable preview URL (`https://thebrief.clauding-lab.com/preview?fixture=<name>.json`), the brief date + issue number, and the draft `todays_call` snippet for at-a-glance review.
- **New CLI flag `--preview-notify`** on `brief.cli`. Requires `--write-fixture`. Fires the notify module after the dry-run completes; failures log a warning but never change the exit code (the fixture write is the canonical artifact).
- **New env vars in `deploy/brief.env.example`**: `DISCORD_PREVIEW_WEBHOOK_URL` (channel webhook in Discord Server Settings → Integrations → Webhooks), `PREVIEW_EMAIL_RECIPIENT` (single address for editorial review, deliberately not the subscriber list). Reuses existing `BREVO_API_KEY` + `FROM_EMAIL` from the subscriber notifier.
- **10 new tests** in `tests/test_preview_notify.py` covering: URL builder, fixture metadata extraction (with missing-field tolerance), Discord ping body shape + error handling, Brevo email payload + HTML-escape on `todays_call` (XSS guard), and the orchestrator's independent-channel + missing-env paths.

### Notes
- No production data path changes. Daily auto-fire publish behaviour at 06:30 BDT is unchanged — preview notifications only fire when both `--write-fixture` and `--preview-notify` are explicitly passed.

---

## [1.4.0] — 2026-05-27

### Added
- **Historical anchors compute layer** (`brief/history_anchors.py`) — five cadence-aware primitives (`last_lower_than`, `last_higher_than`, `pct_change_since`, `rolling_extremes`, `first_cross_since`) that produce `HistoryFact` instances with pre-formatted parens phrases. Reads `metric_history` for daily/weekly/quarterly/fiscal_year and `metric_history_monthly` for monthly long-horizon. The compute layer is the sole formatter of "lowest since X (Y then)" prose — the editor inlines verbatim.
- **`Section.chart_read` field** with structured `{signal, context, implication}` — three short paragraphs rendered as a "Chart read" eyebrow block under every chart card using existing `.tb-analysis` styling. No new CSS, no new component.
- **`ChartReadV6` Pydantic model** in `brief/v6_schema.py` validating the new field.
- **Eight banker-essential monthly metrics in the Macro section**, read from `metric_history_monthly` (previously unused by The Brief): `cpi_12m_avg_monthly`, `cpi_p2p_food_monthly`, `cpi_p2p_nonfood_monthly`, `real_policy_rate_monthly`, `reer_monthly`, `private_credit_growth_yoy_monthly`, `m2_growth_yoy_monthly`, `import_cover_months_monthly`.
- **CPI 24-month trend chart in the Macro section** — new `chartConfigs.cpiTrend` config with three lines (headline 12m-avg, food, non-food).
- **Six new validators** in `brief/claude/validators.py`: `validate_no_banal_language`, `validate_chart_read_temporal_anchor`, `validate_chart_read_implication_quality`, `validate_chart_read_length`, `validate_history_claim_has_reference`, `validate_abbreviation_policy`.
- **Banker Vocabulary Tiers** subsection in `Master.md` defining Tier-1 (bare use), Tier-2 (expand on first use per section), Tier-3 (always expand or rephrase) abbreviation policy.
- **`/preview?fixture=<name>` SPA route** (shipped earlier in v1.4.0 as Phase 0.5) — server-rendered preview path for dry-run fixtures with a yellow "PREVIEW MODE" banner. Enables editorial review of brief content on a separate URL before production publish.
- **`brief/cli.py --write-fixture` flag** — dry-runs can now write directly to a fixture JSON file ready for SPA loading.

### Changed
- **Editor prompt** (`brief/claude/prompts/editor_v6.txt` + `editor_v6_friday.txt`) — banker-grade specificity contract (time-anchored AND implications-oriented), history_facts weaving rules (use `phrase` verbatim including parens), three-tier abbreviation policy, macro section per-section override allowing all 8 metrics (not capped at 5), `chart_read` added to OUTPUT SCHEMA.
- **Sub-editor prompt** (`brief/claude/prompts/subeditor_v6.txt`) — six new checklist items: specificity, temporal anchor on `chart_read.context`, history claim audit, history reference-value preservation, banal-language scan, abbreviation policy.
- **`Cover.sub`** — packs historical anchors verbatim when a `since_lower / since_higher / first_cross_since` HistoryFact exists for the cover metric.
- **`MetricHistoryClient.get_latest()` and `.get_history_window()`** — extended with optional `table` kwarg supporting `metric_history_monthly`.

### Scoped out for v1.4.0 (deferred)
- **Web search sanity check on historical claims** (spec §3.4 #5) — `max_client.py` wraps the Claude CLI subprocess with `--tools ""`, which disables tool-use. Enabling `web_search` requires a code change and CLI version verification. Deferred to a v1.4.x patch.

### Dependencies
- No new dependencies. No version bumps on `next`, `react`, `chart.js`, or `@supabase/supabase-js`.

---

## [1.3.2] — 2026-05-27

### Added
- **`AGENTS.md` at the repo root** — operational rules for AI coding agents working in this repo. Covers build/test/release commands, repo structure (Next.js SPA + Python pipeline + Supabase), key conventions (timestamp storage, Long View schema, chart series IDs, editor/sub-editor split, CSS-only/docs-as-separate-PR rule), and 13 numbered landmines covering recent incidents: `tb_*` legacy tables, Chart.js scale registration, notifier privacy, Vercel build wiping `.venv`, V1 GHA cron retirement, live-vs-legacy metric_id renames, `source_as_of` migration gap, Long View schema as contract, BDT/UTC time conventions, the 2026-05-27 CHANGELOG/tag drift, `package.json` as version source of truth, and Anthropic API transient retry rule.
- **`VISION.md` at the repo root** — auto-merge vs sign-off scopes. Long View content PRs that follow the recipe auto-merge; new block kinds, prompt edits, notifier changes, schema migrations, framework bumps, Master.md / Design.md / longview-workflow.md edits all need sign-off.
- **`AGENT_LEARNINGS.md` at the repo root** — running incident log. Seeded with four entries (most recent first): the 2026-05-27 CHANGELOG/tag drift caught at session-resume; the v1.3.1 notifier privacy leak (PR #83); the May 9 `tb_*` legacy tables ambush (PRs #60, #61); the May 9 Chart.js `CategoryScale` silent failure (PR #62).

### Changed
- **`CLAUDE.md` rewritten** from a 5-line longview-workflow pointer to a proper orientation file. Points at all five governance/content docs (AGENTS.md, VISION.md, AGENT_LEARNINGS.md, Master.md, Design.md) in a "read these first" table. The longview-upload workflow trigger is preserved in a Special workflows section.
- **README version badge + footer** bumped 1.0.0 → 1.3.1 (had been stale since v1.0.0 shipped 2026-05-15), then to 1.3.2 with this release.

### Chore
- **`.gitignore`** now ignores three local-only tool outputs: `.graphifyignore` (graphify config), `graphify-out/` (graphify HTML/JSON outputs, ~6.4MB), `.playwright-mcp/` (Playwright MCP cache).
- **V5 Plan-B wave 1 and wave 2 plan docs** committed to `docs/superpowers/plans/`. All sibling plan docs (pre-wave, wave-3) were already tracked; wave-1 and wave-2 had been written and used to ship PRs #21 and #22 (2026-04-29) but were never committed.

---

## [1.3.1] — 2026-05-26

### Added
- **`Master.md` at the repo root** — canonical brand & voice guide. Covers audience (Tier-1 BD banking professionals: business / risk / treasury / management committee / ALCO / credit committee), tone (clinical, fact-based, quietly analytical; explicitly neutral and diplomatic toward regulators and government while keeping substance fact-based), voice register, surface-specific voice (Today's Call, Banker's Read, Long View, email subject/body), word-level conventions (preferred-abbreviations table + avoid table), numbers/currency rules, honorifics, channel norms, pre-publish checklist.
- **`Design.md` at the repo root** — canonical design language guide. Captures identity (steel-crimson production palette, bone alternate for email), tokens (geometry, type, both palettes, semantic tone with oklch values), typography scale, Long View block kinds (all 5 shipped including bar-chart), hair rules, section structure, email design, diff-stale state, responsive rules, forbiddens, versioning rules.

### Fixed
- **Notifier privacy.** `brief/notifier.py::send_via_brevo` previously packed every subscriber into a single Brevo `to` array, exposing each recipient's address to every other recipient. Each subscriber now gets their own Brevo API call so the To: header only contains their own address. Sequential per-subscriber posts — well under any rate limit at current subscriber counts. Return contract preserved: `(sent_count, last_message_id, first_error_or_None)`. Tests updated to assert the privacy contract directly + cover partial-failure shape (succeed, fail, succeed).

---

## [1.3.0] — 2026-05-24

### Added
- **`bar-chart` block kind for Long View.** Renders a horizontal bar chart with optional vertical reference line (e.g., a regulatory threshold), per-item tone tinting, and an optional unit caption. Implemented as inline SVG with `viewBox`-driven responsive scaling; preserves the mono typography and palette-token visual contract. `BarChartBlock` adds to the `Block` union; `LongViewBarChart.tsx` is the dispatched component.
- Tone classes for bar fills (`bull`, `bear`, `warn`, `neu`) plus a neutral default. Reference line uses the `bear` palette token to signal a regulatory cut.

### Changed
- `LongView.tsx` dispatcher gains a fifth `case "bar-chart"`. No change to the eyebrow / title / lead / blocks / banker_read frame.
- `docs/longview-workflow.md` editorial-half should be updated separately to teach composers when to use bar-chart vs comparison. (Not in this PR — typo-fix CSS-only versioning rule preserves docs-as-separate-PR.)

### Notes
- Triggered by the first chart-bearing Long View upload (BB SPCD Circular No. 06 + listed-bank paid-up-capital ranking, 24 May 2026). The v1.2.0 CHANGELOG entry deferred chart rendering to "v1.3.0+ when the first chart-bearing slide upload arrives" — that day is today.

---

## [1.2.1] — 2026-05-22

### Changed
- **Banker-read typography tightened.** `.tb-longview-takeaway p` reduced from `font-size: 17px` to `14.5px` and `line-height: 1.5` to `1.55`. The takeaway paragraph was the largest body element in the Long View — heavier than the lead (14px) and prose (13.5px) — which made it dominate narrow mobile viewports. The "BANKER READ" small-caps label above the paragraph already carries the emphasis; the body text doesn't need to be larger than the lead.

---

## [1.2.0] — 2026-05-18

### Added
- **Composable Long View blocks.** `LongViewData.blocks: Block[]` replaces `body_paragraphs` + `chart_spec`. Four block kinds ship: `prose`, `comparison`, `stat`, `bullet-list`. Claude composes a Long View by stacking blocks; mixing kinds within a single pin is supported.
- `LongViewProse`, `LongViewComparison`, `LongViewStat`, `LongViewBulletList` — one render component per block kind, each in its own file under `app/components/`.
- Auto column-count for comparison block: 2-col default, 3-col when row count ≥ 7.
- Optional tone tinting (`"bull" | "bear" | "warn" | "neu"`) on comparison row AFTER values, stat values, and bullet-list marks. Defaults to monochrome.
- Markdown-light (`**bold**`) inside bullet-list item text.

### Changed
- **Mono typography enforced.** Every `.tb-longview*` CSS class now sets `font-family: var(--mono)` explicitly. Fixes the v1.1.0 inheritance bug where headings rendered in browser-default serif.
- `LongView.tsx` is now a thin dispatcher: iterates `data.blocks` and switches on `block.kind` to render the right block component. The eyebrow / title / lead / banker_read structure is unchanged.
- `docs/longview-workflow.md` recipe rewritten with the block vocabulary, composition rules, and the explicit "per-pin PRs touch only `content/long-view.ts`" rule (resolves the CHANGELOG ambiguity that surfaced in v1.1.0).

### Fixed
- v1.1.0 Long View rendered in serif because the CSS didn't specify `font-family`. v1.2.0 makes mono explicit on every `.tb-longview*` class so the section blends with the rest of the brief.

### Removed
- `ChartSpec`, `ChartSpecAnnotation`, `ChartSpecSeries` interfaces removed from `types/brief.ts`.
- `chart_spec` field on `LongViewData` removed.
- `.tb-longview-chart-placeholder` and `.tb-longview-body p` CSS rules removed (replaced by per-block CSS).

### Deferred
- Chart rendering. Will return as a `ChartBlock` kind in v1.3.0+ when the first chart-bearing slide upload arrives. Until then, slides with charts should describe the chart's shape in a `prose` block (per the recipe).

---

## [1.1.0] — 2026-05-18

### Added
- **The Long View** — a pinned editorial section that the editor uploads via Discord (Copotron on Hetzner) or local terminal. Claude Code reads the uploaded PDF or JPEG natively and re-renders it as a native cream-paper section. Sits between the Overview and Banking groups; replaces only when a new upload lands. Blurs in diff mode after its posted date.
- `content/long-view.ts` — the pinned data file; edited via the workflow recipe.
- `app/components/LongView.tsx` — the render component.
- `docs/longview-workflow.md` — the recipe (editorial + operational halves).
- `CLAUDE.md` at repo root — pointer to the recipe for any Claude Code session opened in the repo.
- `LongViewData` + `ChartSpec` interfaces in `types/brief.ts`.
- `formatLongViewEyebrow` in `lib/format.tsx` (Asia/Dhaka-pinned).

### Changed
- `app/components/ClientApp.tsx` renders `<LongView>` between the Overview group and the Banking group when `content/long-view.ts` exports non-null.

### Deferred
- Chart rendering in the Long View (`chart_spec` field exists in the type, but the v1.1.0 component renders a placeholder if a non-null `chart_spec` is provided). Real Chart.js rendering ships in v1.1.1 if and when a user upload contains a chart that needs recreation.

---

## [1.0.1] — 2026-05-15 · Same-day patch

### Fixed

- **Every "In this issue" rail item is now clickable** (#71). The keyword→section map shipped in v1.0.0 only matched 7 narrow patterns and had two bugs (`imf → bb` should have been `→ macro`; `remittance → "remit"` slug never existed). Most banking-domain headlines (BB policy, tax, NBR, FDI, budget) had nothing to match, so 8-of-12 rail items in Issue 108 were inert. Expanded the map to seven well-scoped patterns covering bb / banking / tbond / fx / dse / iran / macro with word-boundary anchors on every single-letter token, and added a fallback to the always-present `headlines` section for items that still don't match a specific topic. **Every row in the rail is now clickable.**

### Changed

- **`brief/notifier.py` style + correctness cleanup** (carryover from v1.0.0 reviews):
  - All stdlib imports hoisted to the top of the file (was: 7 mid-file imports accumulated task-by-task during TDD).
  - `_json_loads` helper defined before its first caller (was: defined after `fetch_subscribers`, worked via late binding but read strangely).
  - `BriefRow.published_at` widened to `datetime | None` and the `# type: ignore[arg-type]` comment removed (was: declared non-nullable but `_parse_iso` could return `None`).
  - `send_via_brevo` response decode now uses `_json_loads(r.read())` for consistency (was: inline `_stdjson.loads(r.read().decode("utf-8"))`).
  - `_LENS_PHRASE` annotated as `dict[str, str]`.
  - `_lens_phrase` got a one-line docstring; `_json_loads`, `_parse_iso`, `_supabase_config` similarly.
  - Double space in `render_text` dateline tightened to single space.
  - Module re-organized into labeled sections: Constants / Logger / Dataclasses / Private helpers / Render layer / Fetch layer / Send layer / Orchestration. Function bodies unchanged.

- **Defensive `urlencode` on `brief_id` and `section_id`** in `fetch_brief_data` PostgREST queries (low risk today — both are Supabase-generated UUIDs — but cheap insurance against future callers passing tainted strings).

- **`FROM_EMAIL` silent fallback now logs a warning** (`brief/notifier.py`). When the env var is unset and the notifier falls back to `noreply@example.com`, a warning is logged calling out the operational risk (Brevo will reject sends from an unverified sender). Was previously invisible.

- **`brief/cli.py` docstring** now notes that notifier failures don't change exit code 0 — the Supabase brief is the canonical artifact, the email is a best-effort amplifier. Helps operators debugging a missing send.

- **Package version 1.0.0 → 1.0.1** in `package.json`.

### Pull requests

- #71 — `fix(spa): make every 'In this issue' item clickable`
- (this PR, after merge) — `chore(notifier): cleanup carryover from v1.0.0 reviews + bump to 1.0.1`

### Hetzner deploy

`git pull --ff-only` on `~/the-brief`. No env, no migration, no systemd restart. Next `brief.service` fire (Sun 2026-05-17 06:30 BDT) picks up the cleaner notifier. The rail fix is SPA-only (Vercel auto-deploy).

---

## [1.0.0] — 2026-05-15 · "Banking professionals release"

The first production release. The brief now publishes itself, validates itself, distributes itself by email, and reads honestly across the full banking professional audience — not just treasury desks.

### Added

- **Release email notifier** (`brief/notifier.py` · #64) — HTML + plain-text digest sent to every row in `subscribers` after a successful publish. One Brevo POST per issue, multi-recipient `to:` list. Fail-open: notifier errors never crash the publish. 35 unit tests cover render, fetch, send, and orchestration paths against `urlopen`-mocked Supabase and Brevo. End-to-end validated 2026-05-15 against Issue 107 (`messageId 202605151212.44321990402@smtp-relay.mailin.fr`, 5 subscribers).
- **`--no-notify` CLI flag** on `brief.cli run --publish` — opt out of the email send for manual / test runs.
- **iOS PWA home-screen title** "The Brief" (#65) — via `appleWebApp.title` in Next.js metadata. Previously truncated to "TheBrief—Bangl…" because iOS fell back to the full `<title>`.
- **Clickable "In this issue" rail** (#69) — every headline in the masthead's right rail now jumps to its matching section on click. Same `scrollIntoView` pattern as the existing Subscribe CTA. Hover + focus-visible affordances.
- **Project memory: editor_v6 transient retry pattern** — captures the operational lesson from 2026-05-15 that some `editor_v6` failures are transient Anthropic-side issues; manual retry is the right first move before debugging deeper.

### Changed

- **Audience widened: treasury desks → banking professionals** (#66 · #67).
  - Editor prompts (`editor_v6.txt`, `editor_v6_friday.txt`) now name the reader as "a business head (corporate/SME/retail) and/or a risk head and/or a treasury head at a Tier-1 bank of Bangladesh."
  - Public masthead tagline and `<meta description>` updated to match.
  - Voice (terse, declarative, em-dashes, banker-to-banker) is unchanged.
- **Read-time target ~9 / ~10 min → ~15 min** (#67 · #68).
  - Mon–Thu prompt's "They have ~9 minutes" and Friday's "~10 minutes" both raised to "~15 minutes."
  - `read_minutes` JSON range tightened to `<int 13..17>` from `<int 7..12>` (Mon–Thu) and `<int 8..12>` (Friday).
  - UI fallbacks (`Masthead`, `ClientApp`, `staticFallback`) bumped `?? 9` → `?? 15` so the cold-start display reflects the new target.
  - Wider target carries more analytical depth — more `banker_read` paragraphs, more `analysis` blocks, more "why this matters" prose.
- **`brief.service` `TimeoutStartSec` documented as 90 min in repo** (#63) — the deployed unit on Hetzner has been running with `TimeoutStartUSec=1h 30min` for some time; the repo template still claimed 20 min. Truth-up so a re-deploy from the repo doesn't accidentally kill `editor_v6` mid-retry. The 90-min cap exactly matches `_call_with_retries`'s budget (3 attempts × 1800s + delays).
- **Package version bumped 0.1.0 → 1.0.0** in `package.json`.

### Fixed

- **React `#418` hydration mismatch on every page load** (#63). `formatNewsMeta` called `toLocaleDateString` with no `timeZone` argument, so SSR (Node, UTC) and CSR (browser, BDT/UTC+6) rendered different day numbers for any `published_at` near midnight UTC = 06:00 BDT — and 06:30 BDT is the brief's publish window. Pinning `timeZone: "Asia/Dhaka"` eliminates the mismatch on both sides. Persistent 1-error-per-load is now 0.

### Security

- **XSS hardening in the email HTML renderer** (#64). `_esc` (HTML-escape with `quote=True`) is applied to every editor-derived string. `source_url` href is dropped if the scheme is not `http://` or `https://` — blocks `javascript:`, `data:`, `vbscript:` and other scheme-based XSS vectors. Two regression tests cover both cases.

### Deferred

- Notifier style debt — mid-file imports, `BriefRow.published_at` type annotation, `urlencode(brief_id)`, `FROM_EMAIL` silent fallback policy. ~30 lines, no behavioural change. Will land as a follow-up patch.
- One-click unsubscribe — current behaviour: reply with "Unsubscribe" in the subject. Automated opt-out flow is a separate spec.

### Hetzner deploy notes

- `git pull --ff-only` on `~/the-brief` is enough — no systemd restart, no migration.
- Required env in `/etc/brief.env`: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (or `SUPABASE_SERVICE_KEY`), `BREVO_API_KEY`, `FROM_EMAIL`, `ANTHROPIC_API_KEY`, `ECONDELTA_DATA`.
- First live canary at v1.0.0: Sun 2026-05-17 06:30 BDT → Issue 109 with the broader audience + ~15-min target + email-to-all-subscribers.

---

## Pre-1.0 history

The Brief has been writing and publishing daily since April 2026 across several internal architecture milestones:

- **V1** (2026-04-20s) — original assembler, HTML render to GitHub Pages.
- **V4** (2026-04-24) — pipeline rewrite, email digest as plain-text, V4 templates.
- **V5** (2026-04-25 → 2026-05-04) — cream-paper HTML newspaper render, deploy-to-Hetzner, shadow soak, cutover.
- **V6** (2026-05-04) — replaced static HTML render with Next.js SPA reading from Supabase. Editor + subeditor LLM split. The V5 notification stack (`brief/notify.py`, `brief/report.py`, `brief/email_send.py`) was deleted as part of the cutover with the explicit intent that a future V6 notifier would be written fresh.
- **V6 polish** (2026-05-04 → 2026-05-14) — chart fixes (PRs #58–#62), `metric_history` repointing, chart card heads matching EconDelta `/macro`.
- **v1.0.0** (2026-05-15) — this release. Resurrects the notifier (V6-native, fresh, 150 lines, 35 tests), broadens audience, raises the read-time target, polishes the iOS PWA + masthead navigation, fixes the long-standing React #418 hydration warning.

For commit-level history before v1.0.0, see `git log --until 2026-05-15` on `main`.

[1.0.0]: https://github.com/clauding-lab/the-brief/releases/tag/v1.0.0
