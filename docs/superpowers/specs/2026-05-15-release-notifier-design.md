# Release Notifier — V6 Email Send on Publish

**Status:** Design approved 2026-05-15 (sample email validated in Gmail)
**Author:** Adnan
**Implements:** Restore subscriber email-on-publish functionality, deleted with commit `9ff80e4` on 2026-05-04.

## Context

Every weekday + Sunday 06:30 BDT `brief.service` publishes a new issue to Supabase. Before V6, the publish pipeline also sent a plain-text digest to subscribers via Brevo. That sender was deleted on 2026-05-04 in `9ff80e4` ("drop V5 notification stack + clean env example") because the V5 HTML path was its only caller; the commit author (Adnan) noted at the time that *"a future V6 notification feature would be cleaner written fresh than reviving V5."*

V6 has been running for six weeks with no notifier. Five subscribers in the `subscribers` table have been receiving zero emails. This spec restores the feature, V6-native and lean.

## Goal

After every successful `brief.cli run --publish`, send an HTML+text email to every row in `subscribers` containing the masthead, Today's Call, lead headline, and a link to the full edition.

## Out of scope

- One-click unsubscribe automation (use `mailto:` link in v1; subscribers can reply or email manually). Proper opt-out flow is a separate spec.
- Discord webhook restoration (`brief/notify.py` was also deleted in `9ff80e4`; not requested).
- `run_report.json` builder (`brief/report.py`, also deleted; not needed in V6 since Supabase is the canonical artifact).
- Email open / click tracking, A/B testing, per-subscriber personalization.
- HTML email templating engine — v1 uses inline-styled HTML in Python.
- Bounce / complaint webhook handling. Monitor Brevo dashboard manually.
- Domain-level SPF/DKIM setup. v1 sends from `adnan.rshd@gmail.com` via Brevo's shared infrastructure. Deliverability improvement is a separate task.

## Architecture

Single new module: `brief/notifier.py` (~150 lines). Three public callables:

```python
@dataclass(frozen=True)
class Subscriber:
    name: str
    email: str
    organisation: str | None

@dataclass(frozen=True)
class NotifyResult:
    sent_count: int           # subscribers that Brevo accepted in the API call
    skipped_count: int        # rows skipped (missing email, etc.) — usually 0
    message_id: str | None    # Brevo's message-id from the 2xx response
    error: str | None         # short error tag if anything failed; None on success


def fetch_subscribers() -> list[Subscriber]:
    """Read from Supabase `subscribers` via SUPABASE_SERVICE_KEY."""

def render_email(brief: Brief, lead_news: News | None) -> tuple[str, str, str]:
    """Return (subject, html_body, text_body). Pure — no I/O, no env reads.
    When lead_news is None, the LEAD HEADLINE section is omitted entirely
    (not rendered as '(no lead headline today)') to keep the email tight."""

def notify(brief_id: UUID) -> NotifyResult:
    """Top-level entry. Fail-open: any error logged and swallowed,
    NotifyResult.error carries a short tag."""
```

### Hook point

In `brief/cli.py::_run_v6_publish`, after the existing `log.info("V6 publish ok: brief_id=%s", brief_id)` line. The notifier call is guarded by a flag so manual / test runs can suppress it:

```python
if not ns.no_notify:
    from brief.notifier import notify
    result = notify(brief_id)
    log.info("notifier: sent=%d skipped=%d", result.sent_count, result.skipped_count)
```

New CLI flag: `--no-notify` (default: notify is ON, matches user expectation that publishing = notifying).

### Env vars (already in `/etc/brief.env`)

- `BREVO_API_KEY` — restored 2026-05-15
- `FROM_EMAIL=adnan.rshd@gmail.com` — already present
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — already used by publisher

No new env config required. `.env.example` gets two lines re-added to reflect reality (currently doesn't mention them since the V5-strip).

## Data flow

```
brief.cli run --publish
   └─→ pipeline_v6.run_publish() succeeds, returns brief_id
       └─→ cli._run_v6_publish logs "V6 publish ok"
           └─→ notify(brief_id):
               ├─→ Supabase: GET briefs WHERE id=brief_id           (1 row)
               ├─→ Supabase: GET sections WHERE brief_id=...
               │            AND slug='headlines'                    (1 row)
               ├─→ Supabase: GET news WHERE section_id=...
               │            ORDER BY ord LIMIT 1                    (1 row, may be empty)
               ├─→ Supabase: GET subscribers                        (N rows)
               ├─→ render_email(brief, lead_news) → (subj, html, txt)
               ├─→ POST api.brevo.com/v3/smtp/email × 1
               │     payload: {sender, to:[all subs], subject, htmlContent, textContent}
               │     Brevo dedupes multi-recipient delivery itself
               └─→ Log {sent_count, skipped_count, message_id}
```

One Brevo POST per publish, regardless of subscriber count. Brevo handles per-recipient delivery server-side.

## Email format

Validated 2026-05-15 by sending sample for Issue 107 to `adnan.rshd@gmail.com`. User approved.

### Subject

```
The Brief · No. {issue_no:02d} · {weekday} {DD} {Mmm} {YYYY} · {lens_phrase}
```

Examples:
- Mon-Thu daily: `The Brief · No. 108 · Mon 18 May 2026 · daily read`
- Friday wrap: `The Brief · No. 107 · Fri 15 May 2026 · weekly wrap`
- Sunday: `The Brief · No. 109 · Sun 17 May 2026 · daily read`

`lens_phrase` mapping:
- `weekly_wrap` → `weekly wrap`
- `daily` / null / anything else → `daily read`

### HTML body

Single-column 600px max-width, cream-paper palette to mirror the site identity. Georgia for editorial weight (masthead + Today's Call + lead headline). System sans for chrome. Inline styles only — no `<style>` block (Outlook strips them). Amber-gold (`#a67c2e`) section labels. Hairlines (`1px solid #e6dfd1`) between sections. `mailto:` unsubscribe footer.

Structure (top to bottom):
1. Eyebrow: `The Brief · Vol. NN · No. NNN` (small caps)
2. Big date: `Fri 15 May 2026` (Georgia 32px)
3. Sub-line: `{HH:MM} BDT · {lens_phrase}` — `HH:MM` derived from `brief.published_at` rendered in `Asia/Dhaka` (honest publish time; for the 06:30 auto-fire it shows ~`06:32 BDT`, for a manual re-run like Issue 107 it shows `15:33 BDT`)
4. Hairline
5. Section label `TODAY'S CALL`
6. Today's Call body (split into `<p>` per double-newline in source text)
7. Hairline
8. Section label `LEAD HEADLINE`
9. Headline (linked to `source_url`)
10. `{source} · {HH:MM} BDT` — `HH:MM` derived from `news.published_at` rendered in `Asia/Dhaka` (the news item's own time, not the brief's)
11. Hairline
12. CTA: `Full edition →` link to https://thebrief.clauding-lab.com/
13. Unsubscribe footer (mailto:)

### Plain text body

Identical content to HTML, no markup. Section labels in UPPERCASE. Hairlines as `\n\n`. Final line `Full edition → https://thebrief.clauding-lab.com/`. Unsubscribe instruction as last line.

Both bodies sent in the same Brevo request; clients that prefer text pick `textContent`, modern clients pick `htmlContent`.

## Error handling

Strict fail-open principle. The brief in Supabase is the canonical artifact; the email is a best-effort amplifier. Any failure in the notifier must NOT crash `brief.cli run --publish`.

| Failure | Behavior |
|---|---|
| `BREVO_API_KEY` env var missing or empty | Log `WARNING notifier: BREVO_API_KEY not set, skipping send`. Return `NotifyResult(sent=0, skipped=N, error="no_api_key")`. |
| Supabase fetch of brief/sections/news fails | Log `ERROR notifier: failed to fetch brief data: <err>`. Return early with error. |
| Supabase fetch of subscribers fails | Log `ERROR notifier: failed to fetch subscribers: <err>`. Return early. |
| Subscribers list is empty | Log `INFO notifier: no subscribers, skipping`. Return cleanly. |
| Brevo API non-2xx response | Log `ERROR notifier: Brevo returned <status>: <body>`. Return with error. |
| Network timeout (Brevo, 30s) | Log `ERROR notifier: Brevo timeout`. Return with error. |
| Unexpected exception | Log full traceback, return error. Do not propagate. |

`_run_v6_publish` calls `notify()` inside a try/except that catches anything escaped. Even if the notifier code itself has a bug, the V6 publish exit code stays 0.

## Testing

Three layers:

1. **`render_email` unit tests** — given a fixture `Brief` + lead `News`, assert subject string format, assert HTML contains expected elements, assert text contains expected lines. Tests run pure-in-memory; no Brevo, no Supabase.
2. **`notify` integration test** — uses Supabase client mocked at the HTTP boundary; uses `urllib.request.urlopen` mocked to assert the Brevo payload structure. No real network.
3. **Manual dry-run** — CLI flag `--no-notify` exists; for one-off testing a separate `scripts/render_brief_email.py` script renders the email for any `issue_no` and writes both bodies to `/tmp/` for visual inspection without sending. Not committed for v1 — out of scope.

Coverage target: `render_email` and `notify` at 90%+. Edge cases: brief with no lead headline, brief with empty Today's Call, empty subscribers list, multi-paragraph Today's Call.

## Migration / deployment

No DB migration. No new env vars in `/etc/brief.env`. No new dependencies (uses `urllib.request` from stdlib, same as the deleted V5 sender).

On merge:
1. Hetzner: `cd ~/the-brief && git pull --ff-only` (standard recipe)
2. No systemd restart needed — next `brief.service` fire picks up the new module automatically
3. Next morning's auto-fire (Mon 2026-05-18 06:30 BDT) is the live canary

If anything goes wrong in the first live run:
- Brief still publishes to Supabase (notifier is fail-open)
- Logs show `notifier: ...` lines distinct from `v6_publisher: ...`
- Hotfix: revert just the notifier hook in `cli.py` while keeping the module — fastest path to disabling without losing the implementation

## Decisions made

- **Port-back, not greenfield.** Restore the pattern the commit author originally wrote; V6-adapt where data shapes have changed. (Confirmed by user 2026-05-15.)
- **HTML + plain text both, not text-only.** (Confirmed by user 2026-05-15.) Brevo accepts both in one call.
- **Subject line:** `The Brief · No. {N} · {weekday} {DD} {Mmm} {YYYY} · {lens_phrase}`. (Confirmed by user 2026-05-15.)
- **No "TOP 3 SIGNALS" section** in V6 email — V6 folds signals into `todays_call` as long-form prose, so the V4 dedicated section becomes a duplicate. Drop it.
- **`mailto:` unsubscribe**, not a built-in route. v1 simplicity; proper opt-out flow is a future spec.
- **Notify ON by default**, opt-out via `--no-notify` flag. Matches user expectation that "publishing = notifying."
- **One Brevo POST per publish**, multi-recipient `to:` list. Brevo handles per-address delivery server-side. Cheaper and faster than N requests.
- **Send from `adnan.rshd@gmail.com`** via Brevo shared infrastructure. No domain DKIM/SPF setup in v1. Deliverability improvements (custom sender domain, DMARC) are a follow-up.

## Open questions

None active. Ready to plan.

## References

- Deleted code recovered from `git show 9ff80e4^:brief/email_send.py` and `git show 179beae^:brief/render/v4/email_digest.py`.
- Sample email approved 2026-05-15 — Brevo messageId `<202605151043.67638140215@smtp-relay.mailin.fr>` delivered to `adnan.rshd@gmail.com`.
- Subscriber table schema: `id uuid, name text NOT NULL, organisation text, email text NOT NULL, created_at timestamptz`. 5 rows as of 2026-05-15.
- Brief schema (relevant cols): `id, issue_no, volume, brief_date, published_at, todays_call, lens, frame, read_minutes`.
- Existing related project memories: `feedback_editor_v6_transient_retry.md`, `feedback_chartjs_register_and_preview.md`.
