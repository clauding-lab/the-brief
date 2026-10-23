# Data-reliability repair — release evidence (SKELETON)

**Status: skeleton.** Written 1–2 Oct 2026 BDT during R3d, before any release step. Every
`TO FILL AT RELEASE` marker is a placeholder: nothing under it has happened yet. Only the
sections marked **Recorded** cite evidence that already exists; they quote it, they do not
add to it. Times are BDT (UTC+6).

Plan: task R3 of the repair plan (`2026-09-25-cross-project-repair-plan.md` and
`2026-09-25-data-repair-rollout.md`; local, uncommitted files under `docs/superpowers/plans/`
in the owner's main checkout; R3's text is copied to `C/task-R3-brief.md`). Release order and
pause: `deploy/README.md` "Coordinated release order" (AGENTS.md landmine 44).

---

## 0. Where the evidence lives

The working evidence is NOT in git. It sits in the git-ignored folder
`.superpowers/sdd/2026-09-25-cross-project-repair-plan/` of the repair worktree on the owner's
Mac (called **C** below), with the per-task logs in `C/r2-claude/` (called **R**). Keep that
folder until release and the seven-cycle observation are finished; do not delete it as cleanup.

| What | Where |
|---|---|
| Task ledger, owner decisions (a)–(n), controller rulings | `C/progress.md` |
| R1 history-repair manifest (round 3, committed code) | EconDelta `docs/reviews/2026-09-25-history-repair-manifest.md`; `C/r1-round3-committed/` |
| Backup restore rehearsal | `C/restore-rehearsal-report.md`, `C/restore-rehearsal-review.md` |
| Compatibility both ways (release order) | `R/fixG2-compat.md` |
| Snapshot transfer facts | `R/sync-readonly-20260928/summary.md`, EconDelta `docs/integration.md` |
| R3 test database (disposable clone) | `C/r3-env/README.md` |
| R3 design | `C/r3-publication-design.md` |
| R3a migration rehearsal | `R/fixR3a-report.md`, `R/fixR3a-round1-report.md` |
| R3b publisher + receipt | `R/fixR3b-report.md` |
| R3c single-snapshot readers | `R/fixR3c-report.md` |
| R3d payload limits, round trip, draft hiding, static fallback | `R/fixR3d-report.md` |

## 1. Commits, PRs and manifests

**Recorded.** R2 committed 29 Sep 2026: the Brief `677f7c1`, EconDelta `b3d341d`, `ebeeec3`,
`7af7599` on branch `fix/data-reliability-20260925`; draft PRs `the-brief#215`,
`econdelta#137`, CI green at the time (C/progress.md). R3 (migration 0006, publisher, readers,
docs) is not committed at the time of writing.

TO FILL AT RELEASE:
- Final merge commits (both repos), PR links, CI run links.
- R1 manifest SHA-256 actually applied, round-4 NBR exclusion manifest SHA-256, receipts.
- Migration 0006 SHA-256 as pasted into the SQL editor; captured function definition and grants afterwards.

## 2. Before any merge: installed state

TO FILL AT RELEASE (read-only checks, with times):
- Installed timers on ExonVPS and Hetzner (`systemctl list-timers`), the Hetzner five-minute snapshot pull cron line.
- `CLAUDE_BINARY` executable, free disk on both boxes, Supabase project ref.
- Manual prerequisites landed: migration 0006 applied and verified; R1 (and round 4) applied with receipts.
- The ExonVPS heartbeat cron line as installed before the release (task B5 recorded `30 7 * * *` on 25 Sep 2026; re-read it, do not assume).

Not here: the B4 recipient-contract check runs AFTER the Brief merge, once Vercel production
serves the repaired signup, and before `install.sh` (runbook step 5); the B5 09:45 BDT
heartbeat is switched the same morning (runbook step 6). Both are rows in section 3.

## 3. Release window (stage by stage)

| Stage | Planned BDT | Result (TO FILL AT RELEASE) |
|---|---|---|
| Writers paused (both timers stopped, idle checks) | | |
| EconDelta producer merged; 01:00 gitpull HEAD | 01:00 | |
| R1 (d)+(l) applied, before the first `metric_history` write | before 02:55 | |
| Source collection / parse / aggregate, landed rows, `write_status` | 01:10–03:15 | |
| Sentinel | 03:35 | |
| Snapshot on Hetzner (hash, capture time) | every 5 min | |
| Round-4 NBR exclusion applied; NBR 06-30 / 07-31 rows vs before-images | before 08:00 | |
| Migration 0006 verified (function, grants, schema reload) | before the Brief merge | |
| The Brief merged, pulled, HEAD checked; Vercel production serves the merge commit | before 08:00 | |
| B4 recipient-contract check: commit, BDT time, printed line (count/category only, never addresses); PASS or BLOCKED | after Vercel, before `install.sh` | |
| `install.sh`, unit + lock dir checked | before 08:00 | |
| B5 heartbeat: 07:30 line replaced by 09:45; `crontab -l` shows exactly one heartbeat line | before 09:45 | |
| One approved-channel `TEST ALERT` (log routing) | | |
| Dry-run preview (exit 3), fixture reviewed | | |
| First live fire: issue / date, receipt `created_new_identity` | 08:00 | |
| Watchdog | 09:45 | |
| If step 3 or 4 slipped: owner decision (a) keep `a810fcb` paused / (b) resume it, and when | before 07:50 | |

Transition-window watch (runbook "Transition window"; `R/fixG2-compat.md` §8), TO FILL AT
RELEASE for every `a810fcb` issue published on the new producer: Trade Gap card shown or
hidden; any Opus-review quarantine on the first night and which cards it blanked; the DSE
section reason on a trading day.

## 4. Controlled live publish and test messages

TO FILL AT RELEASE: the reviewed `--no-notify` publish (same issue number kept, nothing
deleted, every child row present, published flip last, nobody re-emailed); one TEST alert to
the approved channel and one email to the approved owner recipient, with receipt CONFIRMED
(not only HTTP acceptance).

## 5. R3 rehearsal on the disposable test database (design tests 1–10)

**Recorded** (see the reports in section 0 for commands, counts and exit codes): R3a design
tests 1, 2, 3, 5, 6, 9 and the permission matrix (GREEN 167 PASS / 0 FAIL after round 1);
R3b receipt gating and response loss (design test 4); R3c mixed-revision readers (design
test 7). The test database is a clone, not production: no Supabase gateway, request-size
limit unknown, one CPU (C/r3-env/README.md "Fidelity limits").

**Recorded — design test 8** (2 Oct 2026 00:11–00:12 BDT, `R/fixR3d-v2-rehearsal.log`:
51 PASS / 0 FAIL, exit 0; 6 of 6 reader mutants caught, `R/fixR3d-v2-mutants.log`). Product
publisher → `/rest/v1` proxy → PostgREST 14.5 → PostgreSQL 17.6; test issue 236 dated that day.

- Round trip: a payload giving every `BriefPayloadV6` field a value (issue 235's real rows plus
  SYNTHETIC values for the fields empty there) came back field-for-field equal from the stored
  rows, `get_latest_brief`, the permalink reader, the previous-brief reader, the notifier
  header and lead story, recent news and the archive index, on the new-issue path and on the
  same-day replacement path (only the documented adapter mappings applied).
- Size basis: the schema's maxima where it has them (18 sections, 6 pills a section,
  1,000-character verdict, 4 watch/risk items); otherwise 2 × the largest value of each family
  in any of the clone's 147 real issues (largest single issue: 228). Maximum edition: 18
  sections, 130 metrics, 80 news, 1,526 chart points, 16 notes; 290,426-byte request.

| Measurement | Result | Budget |
|---|---|---|
| Publish, inside the database (service role) | 417 ms | 8 s statement / 8 s lock |
| Publish, end to end through the product publisher | 972 ms | 30 s HTTP timeout |
| Each reader of that edition, end to end | 424–881 ms | 30 s |
| `get_latest_brief` as anon, inside the database | 77 ms | 3 s |
| Chart points ×5 / ×10 / ×20 (0.67 / 1.15 / 2.1 MB): publish inside the database | 996 / 1,709 / 2,957 ms | 8 s |
| Same, anon `get_latest_brief` inside the database | 195 / 318 / 500 ms | 3 s |

- Draft hiding: a SYNTHETIC draft dated after the published issue stayed invisible to every
  reader (latest, permalink, archive, previous, recent news, notifier, anon table read).
- Static fallback: with no published edition, `get_latest_brief` returns
  `{"brief": null, "sections": []}`, which `app/page.tsx` turns into the static issue
  (`app/page.test.tsx`).
- End-to-end times include the Mac → Finland SSH tunnel; production's publisher runs on Hetzner.

## 6. Seven scheduled cycles

TO FILL AT RELEASE, one row per day, consecutive:

| Day | Producer commit | Newest source periods | Persistence (`write_status`) | Snapshot (hash, capture) | Issue / date | Publish done | Subscribers attempted / accepted / failed | Alerts | Public URL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | | |
| 2 | | | | | | | | | |
| 3 | | | | | | | | | |
| 4 | | | | | | | | | |
| 5 | | | | | | | | | |
| 6 | | | | | | | | | |
| 7 | | | | | | | | | |

Email API acceptance is not receipt; record bounce/receipt information separately. Include at
least one simulated failure in non-production.

## 7. Final release gate

TO FILL AT RELEASE: all 29 findings resolved with evidence; no unclassified consumed source
gap; all supported tests pass on the frozen tree (Mac and Linux CI); repaired rows read back;
backup restore demonstrated; seven days without unexplained freezes, duplicates or false
alarms. A source still blocked is an incomplete objective unless the owner accepts its visible
fallback.

## 8. Versions, tags and live verification

TO FILL AT RELEASE: version bump (package.json, lockfile, README, CHANGELOG together, landmine
12), tags on the merge commits, GitHub releases and the `Latest` flag (landmine 11); deployed
commit on Hetzner, ExonVPS and Vercel; live charts after the first repaired publish (landmine
17).

## 9. Rollback record

TO FILL AT RELEASE (only if used): what was rolled back, in which order (the Brief first), the
commands run, and the state afterwards.
