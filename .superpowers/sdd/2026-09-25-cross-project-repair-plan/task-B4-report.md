# B4 — signup limiting and complete subscriber delivery

Completed implementation and worker verification on 26 September 2026 BDT. Base: `63dd111`. Controller owns independent code, TypeScript, Python, and security reviews and the later release decision.

## Commits

- `75236a3` — `fix(signup): share limits across canonical network addresses`
- `0b56a76` — `fix(notifier): fetch every subscriber page before delivery`

## Behavior and requirements

- `networkRateLimitKey` validates with Node's standard-library `isIP`, expands compressed IPv6 and embedded IPv4 tails, and uses canonical first-64-bit network keys. IPv4-mapped IPv6 and its native IPv4 address share a counter. Invalid, missing, scoped, bracketed, oversized, and malformed addresses share one unknown bucket. The sixth request across hosts/spellings in one network is rejected; other networks remain independent.
- The route still selects `x-real-ip` first, otherwise the last `x-forwarded-for` token. Existing best-effort warm-instance storage and one-minute window are unchanged. No distributed limiter or dependency addition.
- Subscriber pages use the already verified UUID primary key: `select=id,name,email,organisation&order=id.asc&limit=1000`, then `id=gt.<last-id>`. Continue until an empty page, including when a short page reflects a server cap. Totals are not requested or trusted; malformed/incorrect totals cannot truncate the audience. Each UUID must strictly advance, and every row's required fields/email/organisation are checked before returning.
- Normalize email by stripping outer whitespace and lowercasing. Deduplicate across all pages before delivery; the first row in UUID order supplies display fields. Preserve `fetch_subscribers() -> list[Subscriber]`.
- A later page failure or malformed/non-progressing page raises before any send. `notify` returns a bounded error category and no attempted sends on fetch failure. Raw exception strings/tracebacks, which can contain subscriber addresses or credentials, are no longer logged from fetch/send failures.
- One Brevo POST per normalized recipient remains enforced, with exactly one `to` recipient and no `cc`/`bcc`. A successful HTTP acceptance counts even if its optional response body lacks usable JSON/message ID. `sent_count` means provider acceptance, not confirmed inbox delivery. `failed_count` is attempted minus accepted; network failure can mean acceptance was not confirmed.
- Partial delivery now uses the existing Discord alert transport and an error log with sent/attempted/failed counts; publication remains successful. There is no retry, regeneration, or audience resend. B1 identity/pause/lock/same-day suppression code is unchanged; focused/full tests cover those existing safeguards.

## Evidence and documentation

- Reused `live-openapi-definitions.json`'s verified `subscribers.id` UUID primary-key metadata; did not fetch subscriber data or change credentials.
- Read repository AGENTS/VISION, task brief/context, executing-plans/TDD/verification skills and Supabase skill. Read installed Next.js 16.3.4 route-handler documentation. No Next/Supabase client library API call was changed; address parsing and HTTP pagination use standard-library primitives.
- Checked current primary PostgREST documentation for lower server caps, optional totals, ordering and `gt` filtering:
  - https://docs.postgrest.org/en/stable/references/api/pagination_count.html
  - https://docs.postgrest.org/en/stable/references/api/tables_views.html#horizontal-filtering
- New fixtures contain only synthetic recipient names/emails/UUIDs. No live emails, Discord messages, model calls, production writes, pushes, merges or deployment.

## Exact verification commands and outcomes

Run from `/Users/adnanrashid/Projects/clauding-lab/the-brief/.worktrees/data-reliability-20260925` using the existing runtimes.

1. `npm run test -- lib/ipRateLimitKey.test.ts app/api/subscribe/route.test.ts`
   - RED: three real route bypass assertions returned 200 instead of 429; new helper suite failed because implementation did not yet exist. Three unchanged-header/window checks already passed.
   - GREEN after implementation: **32 passed**.
2. `.venv/bin/python -m pytest -q tests/test_notifier.py tests/test_cli.py > /tmp/b4-python-red.log 2>&1`
   - RED: **24 failures** covering complete pagination, malformed/non-progressing pages, dedup-before-send, page-two failure, error redaction, accepted-response counting, and partial delivery alert.
3. `.venv/bin/python -m pytest -q tests/test_notifier.py tests/test_cli.py > /tmp/b4-python-green.log 2>&1`
   - GREEN: **115 passed**, no failure section.
4. `npm run test > /tmp/b4-vitest-full.log 2>&1`
   - Exit 0; **111 passed across 6 files**.
5. `npm run lint -- --ignore-pattern '.superpowers/**' > /tmp/b4-lint.log 2>&1`
   - Exit 0; source lint clean. Scratch downloaded JavaScript under the controller's ignored `.superpowers` workspace is excluded, following the handoff; source lint policy was not changed.
6. `.venv/bin/python -m pytest -q --junitxml=/tmp/b4-pytest-full.xml > /tmp/b4-pytest-full.log 2>&1`
   - Exit 0; XML verifies **1340 collected, 1339 passed, 1 existing server-only skip, 0 errors/failures**, 11.175 seconds. Coverage **93%** (rounded). Run began **26 September 2026 01:34 BDT**.
7. `npm run build > /tmp/b4-build.log 2>&1`
   - Exit 0; production build and static page generation complete.
8. `npx tsc --noEmit > /tmp/b4-tsc.log 2>&1`
   - Exit 0; separate TypeScript check clean after build.
9. `git diff --check`
   - Exit 0; no whitespace errors.

The required frozen full-check matrix ran once after implementation; it was not repeated for this report. Initial red runs and final green runs are distinct, intentional TDD phases.

## Self-review and limits

- Reviewed route header precedence, IPv6 zero expansion, IPv4-mapped equivalence, invalid-input bucket bounding, UUID ordering/cursor progression, dedup order, private Brevo payloads, failure tags and reporting against the task checklist.
- Pagination is a sequence of reads, not a database snapshot. Concurrent signups behind a UUID cursor may start receiving the next edition; this repair guarantees traversal of the stable list and does not promise a transactional audience snapshot.
- This does not claim exactly-once email delivery. R3's durable publication/crash guard remains separate and release-blocking. Timeout outcomes may be uncertain, and no automatic retry was added.
- The existing per-instance rate limiter does not coordinate across serverless instances or cold starts.
- Worker made no release/version edits. Controller handles release-worthy batch versioning and governance.
- Existing controller-owned unstaged generated Next.js block in `AGENTS.md` was preserved and excluded from both commits.

## Review fix round 1 — 26 September 2026 BDT

Controller bundled the four reviews. Fixed the HIGH signup/notifier Unicode mismatch and MEDIUM incident-wording issue; no additional implementation scope was added. Applied the receiving-code-review skill after reproducing the concrete cases.

- `506ce65` — `fix(signup): align stored email rules with delivery validation`
- `8ce1479` — `fix(notifier): report unconfirmed provider acceptance honestly`

The shared fixture `tests/fixtures/subscriber_email_contract.json` defines normalization and accepted/rejected boundary cases. Actual signup tests assert the exact stored insert value, while Python's real paginated fetch must accept/deduplicate those same stored/raw cases. Both implementations trim **ASCII outer spaces only**, lowercase before the length check, and reject **C0/C1 controls, DEL, Unicode whitespace and BOM**. U+0084/U+0085/U+0086, additional Unicode spaces, boundary controls and BOM are covered; ordinary Unicode letters, case expansion (U+0130), and plus tags remain supported. Existing incompatible rows still stop every send before delivery; they are not skipped or silently repaired.

CLI logs/alerts now use `accepted` and `acceptance unconfirmed`, including the zero-confirmation and crash paths. They explicitly say timed-out attempts may already have been accepted and warn against resending everyone. A crash no longer falsely claims it occurred before any sends. The underlying compatibility fields `sent_count`/`failed_count` retain their documented accepted/unconfirmed meaning; publication success and no automatic retry remain unchanged.

### Round-1 exact checks

- `npm run test -- lib/ipRateLimitKey.test.ts app/api/subscribe/route.test.ts > /tmp/b4-r1-ts-red.log 2>&1` — RED: **13 failed / 45 passed**, reproducing storage normalization and invalid-character cases.
- `.venv/bin/python -m pytest -q tests/test_notifier.py tests/test_cli.py > /tmp/b4-r1-python-red.log 2>&1` — RED: **10 incompatible-character/boundary cases failed** before implementation.
- `.venv/bin/python -m pytest -q tests/test_cli.py > /tmp/b4-r1-cli-red.log 2>&1` — RED: **3 incident wording assertions failed**, including crash-state uncertainty.
- `npm run test -- lib/ipRateLimitKey.test.ts app/api/subscribe/route.test.ts > /tmp/b4-r1-ts-green.log 2>&1` — exit 0, **58 passed**, **26 September 2026 01:47 BDT**.
- `.venv/bin/python -m pytest -q tests/test_notifier.py tests/test_cli.py --junitxml=/tmp/b4-r1-python-green.xml > /tmp/b4-r1-python-green.log 2>&1` — exit 0, **141 passed / 0 skipped / 0 failures**, XML time 0.951 seconds.
- `npm run lint -- --ignore-pattern '.superpowers/**' > /tmp/b4-r1-lint.log 2>&1` — exit 0, source lint clean.
- `npx tsc --noEmit > /tmp/b4-r1-tsc.log 2>&1` — exit 0.
- `git diff --check` — exit 0.

Per the controller's scope, no full suite or production build was repeated in this review round. Initial full-check evidence above applies to the original implementation; focused checks cover this correction.

### Blocking deployment prerequisite: existing stored recipients

**Not executed; production rollout remains conditional.** Controller ruling preserves the complete-validated-audience contract. Before activating the stricter notifier, run a privileged **read-only** validation using this candidate's `fetch_subscribers()` and existing server credentials. Output only aggregate counts/fixed error categories, never recipient names, addresses, IDs, response bodies or raw exceptions. If validation fails, block rollout until the owner reviews and resolves the incompatible stored rows; this task does not authorize deleting or skipping them.

The following prepared check calls only the subscriber GET path, never `notify()` or Brevo. It is intentionally shown here rather than executed:

```python
import json
import sys
from brief.notifier import fetch_subscribers, _error_tag

try:
    recipients = fetch_subscribers()
except Exception as error:
    print(json.dumps({"validation_complete": False,
                      "unique_recipients": None,
                      "error_category": _error_tag(error)}))
    sys.exit(1)
print(json.dumps({"validation_complete": True,
                  "unique_recipients": len(recipients),
                  "error_category": None}))
```

An error count cannot honestly be inferred after the first invalid row; the blocked result therefore reports no invented audience total. Record the candidate commit, BDT time and sanitized outcome. The repaired signup boundary must be active, or signup writes held, before the final check and notifier activation so the old permissive writer cannot reintroduce incompatible rows during rollout. No signup pause, data repair or deployment was performed here. R3's separate durable publication/crash prerequisite still applies.
