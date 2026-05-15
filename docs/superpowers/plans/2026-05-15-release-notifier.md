# Release Notifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore subscriber email-on-publish to V6, deleted with commit `9ff80e4` on 2026-05-04. Build `brief/notifier.py` (~150 lines), wire it into `cli._run_v6_publish`, fail-open everywhere.

**Architecture:** Single new module with three public functions (`fetch_subscribers`, `render_email`, `notify`) + two dataclasses. Stdlib-only (`urllib.request`), follows the existing `brief/v6_publisher.py` pattern for Supabase PostgREST access and the deleted `brief/email_send.py` pattern for Brevo. Hook point: one new line in `cli._run_v6_publish` plus a `--no-notify` opt-out flag.

**Tech Stack:** Python 3.11+ stdlib only, pytest with `monkeypatch.setattr`, Supabase PostgREST (`/rest/v1/...`), Brevo transactional API (`POST /v3/smtp/email`).

**Spec:** `docs/superpowers/specs/2026-05-15-release-notifier-design.md`

---

## Reference — Recovering deleted prior art

Useful when shaping unit tests and matching the original V5 patterns:

```bash
git show 9ff80e4^:brief/email_send.py     # Brevo sender (39 lines)
git show 9ff80e4^:tests/test_email_send.py # Test pattern (68 lines)
git show 179beae^:brief/render/v4/email_digest.py # V4 plain-text template
```

Existing in-tree references:
- `brief/v6_publisher.py:1-50` — Supabase request helper (`_config`, `_request`) — mirror this style for `fetch_subscribers` and `fetch_brief_data`
- `brief/cli.py:_parse` — argparse pattern for adding `--no-notify`
- `brief/cli.py:_run_v6_publish` — hook point for the `notify()` call

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `brief/notifier.py` | **CREATE** (~150 lines) | All notifier logic: dataclasses, fetch, render, send, orchestrate |
| `brief/cli.py` | **MODIFY** (+ ~8 lines) | Add `--no-notify` flag in `_parse`; call `notify(brief_id)` at end of `_run_v6_publish` |
| `tests/test_notifier.py` | **CREATE** (~250 lines) | Unit tests for render + send + notify orchestration, all `urlopen` mocked |
| `.env.example` | **MODIFY** (+2 lines) | Re-add `BREVO_API_KEY=` and `FROM_EMAIL=` blocks that were dropped on 2026-05-04 |
| `docs/superpowers/plans/2026-05-15-release-notifier.md` | **THIS FILE** | This plan |

No new dependencies. `requirements.txt` and `requirements-dev.txt` untouched.

---

### Task 1: Bootstrap `brief/notifier.py` with dataclasses

**Files:**
- Create: `brief/notifier.py`
- Create: `tests/test_notifier.py`

- [ ] **Step 1: Write the failing test**

Append to a new file `tests/test_notifier.py`:

```python
"""Unit tests for brief.notifier — release email notifier."""
from __future__ import annotations

from brief.notifier import Subscriber, NotifyResult


def test_subscriber_dataclass_is_frozen_and_has_expected_fields():
    s = Subscriber(name="Mehrin Rahman", email="m@brac.bank.com", organisation="BRAC")
    assert s.name == "Mehrin Rahman"
    assert s.email == "m@brac.bank.com"
    assert s.organisation == "BRAC"
    # frozen → mutation raises
    import dataclasses
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        s.email = "other@example.com"  # type: ignore[misc]


def test_notify_result_has_expected_fields_with_defaults():
    r = NotifyResult(sent_count=5, skipped_count=0, message_id="abc", error=None)
    assert r.sent_count == 5
    assert r.skipped_count == 0
    assert r.message_id == "abc"
    assert r.error is None
```

- [ ] **Step 2: Run test, verify it fails**

```bash
.venv/bin/pytest tests/test_notifier.py -v
```

Expected: `ImportError: cannot import name 'Subscriber' from 'brief.notifier'`

- [ ] **Step 3: Write minimal implementation**

Create `brief/notifier.py`:

```python
"""Release email notifier for V6 briefs.

Sends an HTML+plain-text digest to every row in `subscribers` after a
successful `brief.cli run --publish`. Fail-open: any error logged and
swallowed; the Supabase brief is the canonical artifact.

Spec: docs/superpowers/specs/2026-05-15-release-notifier-design.md
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Subscriber:
    """One row from the public.subscribers table."""
    name: str
    email: str
    organisation: str | None


@dataclass(frozen=True)
class NotifyResult:
    """Return value from notify(); summarises what happened."""
    sent_count: int            # subscribers Brevo accepted in the API call
    skipped_count: int         # rows skipped client-side (e.g. missing email)
    message_id: str | None     # Brevo's message-id from the 2xx response
    error: str | None          # short error tag if anything failed; None on success
```

- [ ] **Step 4: Run test, verify it passes**

```bash
.venv/bin/pytest tests/test_notifier.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add brief/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): scaffold module with Subscriber + NotifyResult dataclasses"
```

---

### Task 2: `render_subject()` — subject-line formatting

**Files:**
- Modify: `brief/notifier.py` (add function)
- Modify: `tests/test_notifier.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_notifier.py`:

```python
from datetime import date
from brief.notifier import render_subject


def test_render_subject_friday_weekly_wrap():
    subj = render_subject(issue_no=107, brief_date=date(2026, 5, 15), lens="weekly_wrap")
    assert subj == "The Brief · No. 107 · Fri 15 May 2026 · weekly wrap"


def test_render_subject_weekday_daily():
    subj = render_subject(issue_no=108, brief_date=date(2026, 5, 18), lens="daily")
    assert subj == "The Brief · No. 108 · Mon 18 May 2026 · daily read"


def test_render_subject_unknown_lens_falls_back_to_daily_read():
    subj = render_subject(issue_no=99, brief_date=date(2026, 4, 15), lens="something_new")
    assert subj == "The Brief · No. 99 · Wed 15 Apr 2026 · daily read"


def test_render_subject_null_lens_falls_back_to_daily_read():
    subj = render_subject(issue_no=99, brief_date=date(2026, 4, 15), lens=None)
    assert subj == "The Brief · No. 99 · Wed 15 Apr 2026 · daily read"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
.venv/bin/pytest tests/test_notifier.py::test_render_subject_friday_weekly_wrap -v
```

Expected: `ImportError: cannot import name 'render_subject'`

- [ ] **Step 3: Write minimal implementation**

Append to `brief/notifier.py`:

```python
from datetime import date as date_t

_LENS_PHRASE = {
    "weekly_wrap": "weekly wrap",
}
_DEFAULT_LENS_PHRASE = "daily read"


def render_subject(*, issue_no: int, brief_date: date_t, lens: str | None) -> str:
    """Return the subject line for a brief release email.

    Format: "The Brief · No. {N} · {Weekday} {DD} {Mmm} {YYYY} · {lens phrase}"
    """
    lens_phrase = _LENS_PHRASE.get(lens or "", _DEFAULT_LENS_PHRASE)
    date_str = brief_date.strftime("%a %d %b %Y")
    return f"The Brief · No. {issue_no} · {date_str} · {lens_phrase}"
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
.venv/bin/pytest tests/test_notifier.py -v
```

Expected: `6 passed` (2 from Task 1 + 4 new)

- [ ] **Step 5: Commit**

```bash
git add brief/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): render_subject() — lens-aware subject line"
```

---

### Task 3: `render_text()` — plain-text body

**Files:**
- Modify: `brief/notifier.py` (add function + fixture helpers)
- Modify: `tests/test_notifier.py` (add tests + a Brief/News fixture builder)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_notifier.py`:

```python
from datetime import datetime, timezone
from brief.notifier import BriefRow, NewsRow, render_text


def _fixture_brief() -> BriefRow:
    """A realistic V6 brief row built from Issue 107 (2026-05-15)."""
    return BriefRow(
        id="f54ac95d-2127-44f4-bb02-9bd0f7fc5de8",
        issue_no=107,
        volume=1,
        brief_date=date(2026, 5, 15),
        published_at=datetime(2026, 5, 15, 9, 33, 12, tzinfo=timezone.utc),
        todays_call=(
            "Fitch went negative on BD Wednesday — first rating action.\n\n"
            "USD/BDT held 122.75 all five sessions.\n\n"
            "Next week: May CPI print."
        ),
        lens="weekly_wrap",
    )


def _fixture_lead_news() -> NewsRow:
    return NewsRow(
        headline="Fitch revises Bangladesh outlook to negative amid Middle East fallout",
        source="The Daily Star",
        source_url="https://www.thedailystar.net/business/economy/news/fitch-revises-bangladesh-outlook-negative-amid-middle-east-fallout-4175171",
        published_at=datetime(2026, 5, 14, 0, 30, 16, tzinfo=timezone.utc),
    )


def test_render_text_contains_masthead_and_dateline():
    text = render_text(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert "THE BRIEF · Vol. 01 · No. 107" in text
    assert "Fri 15 May 2026" in text
    # 09:33 UTC → 15:33 BDT (UTC+6)
    assert "15:33 BDT" in text
    assert "weekly wrap" in text


def test_render_text_contains_todays_call_paragraphs():
    text = render_text(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert "TODAY'S CALL" in text
    assert "Fitch went negative on BD Wednesday" in text
    assert "USD/BDT held 122.75" in text
    assert "Next week: May CPI print." in text


def test_render_text_contains_lead_headline_block():
    text = render_text(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert "LEAD HEADLINE" in text
    assert "Fitch revises Bangladesh outlook to negative amid Middle East fallout" in text
    assert "The Daily Star" in text
    # 00:30 UTC May 14 → 06:30 BDT May 14
    assert "06:30 BDT" in text
    assert "https://www.thedailystar.net/business/economy/news/fitch-revises-bangladesh-outlook-negative-amid-middle-east-fallout-4175171" in text


def test_render_text_omits_lead_section_when_lead_news_is_none():
    text = render_text(brief=_fixture_brief(), lead_news=None)
    assert "LEAD HEADLINE" not in text
    assert "(no lead headline today)" not in text


def test_render_text_ends_with_full_edition_link_and_unsubscribe():
    text = render_text(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert "Full edition → https://thebrief.clauding-lab.com/" in text
    assert "Unsubscribe" in text
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
.venv/bin/pytest tests/test_notifier.py -v
```

Expected: `ImportError: cannot import name 'BriefRow' from 'brief.notifier'`

- [ ] **Step 3: Write minimal implementation**

Append to `brief/notifier.py`:

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_BDT = ZoneInfo("Asia/Dhaka")
_HOSTED_URL = "https://thebrief.clauding-lab.com/"


@dataclass(frozen=True)
class BriefRow:
    """Subset of the briefs row that the notifier needs."""
    id: str
    issue_no: int
    volume: int
    brief_date: date_t
    published_at: datetime
    todays_call: str
    lens: str | None


@dataclass(frozen=True)
class NewsRow:
    """One row from the news table — used for the lead headline."""
    headline: str
    source: str
    source_url: str | None
    published_at: datetime | None


def _hhmm_bdt(ts: datetime | None) -> str:
    """Format a timestamp as HH:MM BDT. None → empty string."""
    if ts is None:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(_BDT).strftime("%H:%M BDT")


def _lens_phrase(lens: str | None) -> str:
    return _LENS_PHRASE.get(lens or "", _DEFAULT_LENS_PHRASE)


def render_text(*, brief: BriefRow, lead_news: NewsRow | None) -> str:
    """Plain-text body for the release email.

    LEAD HEADLINE section is omitted entirely when lead_news is None.
    """
    lines: list[str] = []
    masthead_no = f"No. {brief.issue_no}"
    masthead_vol = f"Vol. {brief.volume:02d}"
    lines.append(f"THE BRIEF · {masthead_vol} · {masthead_no}")
    lines.append(f"{brief.brief_date.strftime('%a %d %b %Y')} · {_hhmm_bdt(brief.published_at)}  [{_lens_phrase(brief.lens)}]")
    lines.append("")

    lines.append("TODAY'S CALL")
    # todays_call may be multi-paragraph — emit as-is, preserving blank-line separators
    lines.append(brief.todays_call.strip())
    lines.append("")

    if lead_news is not None:
        lines.append("LEAD HEADLINE")
        lines.append(lead_news.headline)
        time_part = _hhmm_bdt(lead_news.published_at)
        meta = f"{lead_news.source} · {time_part}" if time_part else lead_news.source
        lines.append(meta)
        if lead_news.source_url:
            lines.append(lead_news.source_url)
        lines.append("")

    lines.append(f"Full edition → {_HOSTED_URL}")
    lines.append("")
    lines.append("---")
    lines.append("You're getting this because you subscribed at thebrief.clauding-lab.com.")
    lines.append("Unsubscribe: reply to this email with 'Unsubscribe' in the subject.")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
.venv/bin/pytest tests/test_notifier.py -v
```

Expected: `11 passed` (6 prior + 5 new)

- [ ] **Step 5: Commit**

```bash
git add brief/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): render_text() — plain-text body with masthead, Today's Call, lead headline"
```

---

### Task 4: `render_html()` — HTML body

**Files:**
- Modify: `brief/notifier.py` (add function)
- Modify: `tests/test_notifier.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_notifier.py`:

```python
from brief.notifier import render_html


def test_render_html_has_doctype_and_inline_styled_body():
    html = render_html(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert html.startswith("<!DOCTYPE html>")
    assert "background:#f7f2e8" in html  # cream-paper outer bg
    assert "background:#fdfaf4" in html  # card bg
    # Outlook-safe: NO <style> block, only inline styles
    assert "<style" not in html


def test_render_html_renders_masthead_and_dateline():
    html = render_html(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert "Vol. 01" in html
    assert "No. 107" in html
    assert "Fri 15 May 2026" in html
    assert "15:33 BDT" in html
    assert "weekly wrap" in html


def test_render_html_renders_todays_call_as_paragraphs():
    html = render_html(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    # Each \n\n becomes a <p>
    assert html.count("<p style=") >= 3  # 3 paragraphs in fixture todays_call
    assert "Fitch went negative on BD Wednesday" in html
    assert "USD/BDT held 122.75" in html


def test_render_html_renders_lead_headline_with_link():
    html = render_html(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert 'href="https://www.thedailystar.net/' in html
    assert "Fitch revises Bangladesh outlook to negative" in html
    assert "The Daily Star" in html
    assert "06:30 BDT" in html


def test_render_html_omits_lead_section_when_lead_news_is_none():
    html = render_html(brief=_fixture_brief(), lead_news=None)
    assert "LEAD HEADLINE" not in html
    # Hairline count is one fewer when no lead section
    assert html.count("border-top:1px solid #e6dfd1") == 2  # date->call, call->cta


def test_render_html_escapes_special_chars_in_todays_call():
    brief = BriefRow(
        id="x", issue_no=1, volume=1, brief_date=date(2026, 1, 1),
        published_at=datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
        todays_call="Risk & rate <test> entities",
        lens=None,
    )
    html = render_html(brief=brief, lead_news=None)
    assert "Risk &amp; rate &lt;test&gt; entities" in html
    assert "Risk & rate <test>" not in html  # un-escaped form must NOT appear
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
.venv/bin/pytest tests/test_notifier.py::test_render_html_has_doctype_and_inline_styled_body -v
```

Expected: `ImportError: cannot import name 'render_html'`

- [ ] **Step 3: Write minimal implementation**

Append to `brief/notifier.py`:

```python
import html as _html


def _esc(s: str) -> str:
    """HTML-escape a runtime string. Always use for user/editor-derived text."""
    return _html.escape(s, quote=True)


def render_html(*, brief: BriefRow, lead_news: NewsRow | None) -> str:
    """HTML body — single-column 600px, Outlook-safe inline styles.

    Cream-paper palette mirrors the site identity; Georgia for editorial weight,
    system sans for chrome, amber-gold (#a67c2e) section labels, hairline rules.
    """
    paragraphs = [p.strip() for p in brief.todays_call.split("\n\n") if p.strip()]
    paragraphs_html = "".join(
        f'<p style="margin:0 0 14px;">{_esc(p)}</p>' for p in paragraphs[:-1]
    ) + (f'<p style="margin:0;">{_esc(paragraphs[-1])}</p>' if paragraphs else "")

    lead_block = ""
    if lead_news is not None:
        headline_html = _esc(lead_news.headline)
        if lead_news.source_url:
            headline_html = (
                f'<a href="{_esc(lead_news.source_url)}" '
                f'style="color:#1a1814;text-decoration:none;border-bottom:1px solid #c9b88a;">'
                f'{headline_html}</a>'
            )
        time_part = _hhmm_bdt(lead_news.published_at)
        meta = f"{_esc(lead_news.source)} · {time_part}" if time_part else _esc(lead_news.source)
        lead_block = (
            '<div style="font-size:10px;letter-spacing:0.16em;text-transform:uppercase;'
            'color:#a67c2e;font-weight:600;">Lead Headline</div>'
            f'<div style="font-family:Georgia,serif;font-size:18px;font-weight:400;'
            f'line-height:1.35;color:#1a1814;margin-top:10px;">{headline_html}</div>'
            f'<div style="font-size:12px;color:#7a6f5c;margin-top:6px;">{meta}</div>'
            '<hr style="border:none;border-top:1px solid #e6dfd1;margin:24px 0;">'
        )

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:32px 16px;background:#f7f2e8;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1a1814;">
<table cellpadding="0" cellspacing="0" border="0" align="center" style="max-width:600px;width:100%;background:#fdfaf4;padding:32px 28px;border:1px solid #e6dfd1;">
  <tr><td>
    <div style="font-family:Georgia,serif;font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:#7a6f5c;">The Brief &middot; Vol. {brief.volume:02d} &middot; No. {brief.issue_no}</div>
    <div style="font-family:Georgia,serif;font-size:32px;font-weight:400;line-height:1.1;color:#1a1814;margin-top:6px;">{brief.brief_date.strftime("%a %d %b %Y")}</div>
    <div style="font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#9a8e75;margin-top:4px;">{_hhmm_bdt(brief.published_at)} &middot; {_lens_phrase(brief.lens)}</div>
    <hr style="border:none;border-top:1px solid #e6dfd1;margin:24px 0;">

    <div style="font-size:10px;letter-spacing:0.16em;text-transform:uppercase;color:#a67c2e;font-weight:600;">Today's Call</div>
    <div style="font-family:Georgia,serif;font-size:15px;line-height:1.65;color:#2a2620;margin-top:10px;">
      {paragraphs_html}
    </div>
    <hr style="border:none;border-top:1px solid #e6dfd1;margin:24px 0;">

    {lead_block}
    <a href="{_HOSTED_URL}" style="display:inline-block;font-size:12px;letter-spacing:0.16em;text-transform:uppercase;color:#1a1814;font-weight:600;border-bottom:2px solid #1a1814;text-decoration:none;padding-bottom:2px;">Full edition &rarr;</a>
    <div style="font-size:10px;color:#9a8e75;margin-top:20px;">You're getting this because you subscribed at thebrief.clauding-lab.com. <a href="mailto:adnan.rshd@gmail.com?subject=Unsubscribe%20-%20The%20Brief" style="color:#9a8e75;">Unsubscribe</a>.</div>
  </td></tr>
</table>
</body></html>"""
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
.venv/bin/pytest tests/test_notifier.py -v
```

Expected: `17 passed`

- [ ] **Step 5: Commit**

```bash
git add brief/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): render_html() — inline-styled cream-paper HTML body"
```

---

### Task 5: `render_email()` — wire subject + text + HTML

**Files:**
- Modify: `brief/notifier.py` (add top-level function)
- Modify: `tests/test_notifier.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_notifier.py`:

```python
from brief.notifier import render_email


def test_render_email_returns_three_strings():
    subject, html, text = render_email(brief=_fixture_brief(), lead_news=_fixture_lead_news())
    assert isinstance(subject, str) and subject.startswith("The Brief · No. 107")
    assert html.startswith("<!DOCTYPE html>")
    assert text.startswith("THE BRIEF · Vol. 01 · No. 107")


def test_render_email_handles_no_lead_news():
    subject, html, text = render_email(brief=_fixture_brief(), lead_news=None)
    assert "LEAD HEADLINE" not in html
    assert "LEAD HEADLINE" not in text
    assert subject == "The Brief · No. 107 · Fri 15 May 2026 · weekly wrap"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
.venv/bin/pytest tests/test_notifier.py::test_render_email_returns_three_strings -v
```

Expected: `ImportError: cannot import name 'render_email'`

- [ ] **Step 3: Write minimal implementation**

Append to `brief/notifier.py`:

```python
def render_email(*, brief: BriefRow, lead_news: NewsRow | None) -> tuple[str, str, str]:
    """Return (subject, html_body, text_body) for a brief release email.

    Pure function — no I/O, no env reads. Use for unit-testing and dry-run rendering.
    """
    subject = render_subject(
        issue_no=brief.issue_no,
        brief_date=brief.brief_date,
        lens=brief.lens,
    )
    html = render_html(brief=brief, lead_news=lead_news)
    text = render_text(brief=brief, lead_news=lead_news)
    return subject, html, text
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
.venv/bin/pytest tests/test_notifier.py -v
```

Expected: `19 passed`

- [ ] **Step 5: Commit**

```bash
git add brief/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): render_email() — wires subject/html/text together"
```

---

### Task 6: `fetch_subscribers()` — Supabase GET

**Files:**
- Modify: `brief/notifier.py` (add function + Supabase config helper)
- Modify: `tests/test_notifier.py` (add tests with mocked urlopen)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_notifier.py`:

```python
import json as _json
import brief.notifier as notifier_mod
from brief.notifier import fetch_subscribers


class _FakeResp:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self) -> bytes:
        return self._body


def test_fetch_subscribers_returns_list_of_subscriber(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        body = _json.dumps([
            {"name": "Mehrin", "email": "m@brac.com", "organisation": "BRAC"},
            {"name": "Tareq", "email": "t@city.com", "organisation": None},
        ]).encode()
        return _FakeResp(body)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    subs = fetch_subscribers()

    assert len(subs) == 2
    assert subs[0] == Subscriber(name="Mehrin", email="m@brac.com", organisation="BRAC")
    assert subs[1].organisation is None
    assert "/rest/v1/subscribers" in captured["url"]
    assert captured["headers"].get("Apikey") == "test-key" or captured["headers"].get("apikey") == "test-key"


def test_fetch_subscribers_returns_empty_when_table_empty(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")

    def fake_urlopen(req, timeout=None):
        return _FakeResp(b"[]")

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    assert fetch_subscribers() == []


def test_fetch_subscribers_raises_on_missing_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    with __import__("pytest").raises(RuntimeError, match="SUPABASE_URL"):
        fetch_subscribers()
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
.venv/bin/pytest tests/test_notifier.py::test_fetch_subscribers_returns_list_of_subscriber -v
```

Expected: `ImportError: cannot import name 'fetch_subscribers'`

- [ ] **Step 3: Write minimal implementation**

Append to `brief/notifier.py`:

```python
import os
import urllib.request
from urllib.request import urlopen, Request


def _supabase_config() -> tuple[str, str]:
    """Same pattern as brief/v6_publisher.py::_config — service-role auth."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY env vars. "
            "On Hetzner these come from /etc/brief.env via systemd EnvironmentFile."
        )
    return url.rstrip("/"), key


def fetch_subscribers() -> list[Subscriber]:
    """GET /rest/v1/subscribers — all rows ordered by created_at desc."""
    url, key = _supabase_config()
    req = Request(
        f"{url}/rest/v1/subscribers?select=name,email,organisation&order=created_at.desc",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=30) as r:
        rows = _json_loads(r.read())
    return [
        Subscriber(name=row["name"], email=row["email"], organisation=row.get("organisation"))
        for row in rows
    ]


def _json_loads(data: bytes) -> list[dict]:
    import json as _stdjson
    return _stdjson.loads(data.decode("utf-8"))
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
.venv/bin/pytest tests/test_notifier.py -v
```

Expected: `22 passed`

- [ ] **Step 5: Commit**

```bash
git add brief/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): fetch_subscribers() — Supabase service-key GET"
```

---

### Task 7: `fetch_brief_data()` — load brief row + lead news

**Files:**
- Modify: `brief/notifier.py` (add function)
- Modify: `tests/test_notifier.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_notifier.py`:

```python
from brief.notifier import fetch_brief_data


def test_fetch_brief_data_returns_brief_and_lead_news(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")

    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        if "/briefs?" in req.full_url:
            body = _json.dumps([{
                "id": "f54ac95d", "issue_no": 107, "volume": 1,
                "brief_date": "2026-05-15", "published_at": "2026-05-15T09:33:12+00:00",
                "todays_call": "Fitch went negative.", "lens": "weekly_wrap",
            }]).encode()
        elif "/sections?" in req.full_url:
            body = _json.dumps([{"id": "sec-uuid"}]).encode()
        elif "/news?" in req.full_url:
            body = _json.dumps([{
                "headline": "Fitch revises Bangladesh outlook to negative",
                "source": "The Daily Star",
                "source_url": "https://example.com/x",
                "published_at": "2026-05-14T00:30:00+00:00",
            }]).encode()
        else:
            raise AssertionError(f"unexpected URL: {req.full_url}")
        return _FakeResp(body)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    brief, lead = fetch_brief_data("f54ac95d")
    assert brief.issue_no == 107
    assert brief.todays_call == "Fitch went negative."
    assert lead is not None
    assert lead.headline.startswith("Fitch revises Bangladesh")
    assert lead.source == "The Daily Star"


def test_fetch_brief_data_returns_none_lead_when_no_headlines_section(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")

    def fake_urlopen(req, timeout=None):
        if "/briefs?" in req.full_url:
            body = _json.dumps([{
                "id": "x", "issue_no": 1, "volume": 1,
                "brief_date": "2026-05-15", "published_at": "2026-05-15T00:30:00+00:00",
                "todays_call": "x", "lens": None,
            }]).encode()
        elif "/sections?" in req.full_url:
            body = b"[]"  # no headlines section
        else:
            raise AssertionError(f"unexpected URL: {req.full_url}")
        return _FakeResp(body)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    brief, lead = fetch_brief_data("x")
    assert lead is None


def test_fetch_brief_data_returns_none_lead_when_section_has_no_news(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")

    def fake_urlopen(req, timeout=None):
        if "/briefs?" in req.full_url:
            body = _json.dumps([{
                "id": "x", "issue_no": 1, "volume": 1,
                "brief_date": "2026-05-15", "published_at": "2026-05-15T00:30:00+00:00",
                "todays_call": "x", "lens": None,
            }]).encode()
        elif "/sections?" in req.full_url:
            body = _json.dumps([{"id": "sec-uuid"}]).encode()
        elif "/news?" in req.full_url:
            body = b"[]"
        else:
            raise AssertionError(f"unexpected URL: {req.full_url}")
        return _FakeResp(body)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    brief, lead = fetch_brief_data("x")
    assert lead is None
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
.venv/bin/pytest tests/test_notifier.py::test_fetch_brief_data_returns_brief_and_lead_news -v
```

Expected: `ImportError: cannot import name 'fetch_brief_data'`

- [ ] **Step 3: Write minimal implementation**

Append to `brief/notifier.py`:

```python
from datetime import datetime as _dt


def _parse_iso(s: str | None) -> datetime | None:
    """Parse ISO 8601 (with or without timezone) → datetime."""
    if not s:
        return None
    # Supabase returns "2026-05-15T09:33:12.488474+00:00" — Python 3.11+ fromisoformat handles it
    return _dt.fromisoformat(s)


def fetch_brief_data(brief_id: str) -> tuple[BriefRow, NewsRow | None]:
    """GET brief row + lead news (first headlines-section row by ord)."""
    url, key = _supabase_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }

    def _get(path: str) -> list[dict]:
        with urlopen(Request(f"{url}/rest/v1{path}", headers=headers), timeout=30) as r:
            return _json_loads(r.read())

    brief_rows = _get(f"/briefs?id=eq.{brief_id}&select=id,issue_no,volume,brief_date,published_at,todays_call,lens")
    if not brief_rows:
        raise RuntimeError(f"brief id={brief_id} not found in Supabase")
    b = brief_rows[0]
    brief = BriefRow(
        id=b["id"],
        issue_no=b["issue_no"],
        volume=b["volume"],
        brief_date=date_t.fromisoformat(b["brief_date"]),
        published_at=_parse_iso(b["published_at"]),  # type: ignore[arg-type]
        todays_call=b.get("todays_call") or "",
        lens=b.get("lens"),
    )

    section_rows = _get(f"/sections?brief_id=eq.{brief_id}&slug=eq.headlines&select=id&limit=1")
    if not section_rows:
        return brief, None
    section_id = section_rows[0]["id"]

    news_rows = _get(f"/news?section_id=eq.{section_id}&select=headline,source,source_url,published_at&order=ord.asc&limit=1")
    if not news_rows:
        return brief, None
    n = news_rows[0]
    lead = NewsRow(
        headline=n["headline"],
        source=n["source"],
        source_url=n.get("source_url"),
        published_at=_parse_iso(n.get("published_at")),
    )
    return brief, lead
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
.venv/bin/pytest tests/test_notifier.py -v
```

Expected: `25 passed`

- [ ] **Step 5: Commit**

```bash
git add brief/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): fetch_brief_data() — load brief row + lead news from Supabase"
```

---

### Task 8: `send_via_brevo()` — HTTP POST to Brevo

**Files:**
- Modify: `brief/notifier.py` (add function)
- Modify: `tests/test_notifier.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_notifier.py`:

```python
from brief.notifier import send_via_brevo


def test_send_via_brevo_posts_correct_payload_and_returns_message_id(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = _json.loads(req.data.decode())
        return _FakeResp(b'{"messageId":"<abc@brevo>"}', status=201)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    result = send_via_brevo(
        api_key="test-key",
        from_email="adnan.rshd@gmail.com",
        from_name="The Brief",
        subscribers=[
            Subscriber(name="A", email="a@x.com", organisation=None),
            Subscriber(name="B", email="b@y.com", organisation="Y"),
        ],
        subject="The Brief · No. 107",
        html_body="<html/>",
        text_body="plain",
    )

    assert result == (2, "<abc@brevo>", None)  # (sent_count, message_id, error)
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert captured["body"]["sender"] == {"email": "adnan.rshd@gmail.com", "name": "The Brief"}
    assert captured["body"]["to"] == [
        {"email": "a@x.com", "name": "A"},
        {"email": "b@y.com", "name": "B"},
    ]
    assert captured["body"]["subject"] == "The Brief · No. 107"
    assert captured["body"]["htmlContent"] == "<html/>"
    assert captured["body"]["textContent"] == "plain"


def test_send_via_brevo_returns_error_on_network_failure(monkeypatch):
    def boom(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(notifier_mod, "urlopen", boom)

    sent, msg_id, err = send_via_brevo(
        api_key="k", from_email="a@x.com", from_name="The Brief",
        subscribers=[Subscriber(name="A", email="a@x.com", organisation=None)],
        subject="s", html_body="h", text_body="t",
    )
    assert sent == 0
    assert msg_id is None
    assert "connection refused" in err


def test_send_via_brevo_returns_error_on_non_2xx(monkeypatch):
    import urllib.error

    def http_err(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized",
            hdrs=None, fp=__import__("io").BytesIO(b'{"message":"invalid api key"}'),
        )

    monkeypatch.setattr(notifier_mod, "urlopen", http_err)

    sent, msg_id, err = send_via_brevo(
        api_key="bad", from_email="a@x.com", from_name="The Brief",
        subscribers=[Subscriber(name="A", email="a@x.com", organisation=None)],
        subject="s", html_body="h", text_body="t",
    )
    assert sent == 0
    assert msg_id is None
    assert "401" in err
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
.venv/bin/pytest tests/test_notifier.py::test_send_via_brevo_posts_correct_payload_and_returns_message_id -v
```

Expected: `ImportError: cannot import name 'send_via_brevo'`

- [ ] **Step 3: Write minimal implementation**

Append to `brief/notifier.py`:

```python
import urllib.error

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def send_via_brevo(
    *,
    api_key: str,
    from_email: str,
    from_name: str,
    subscribers: list[Subscriber],
    subject: str,
    html_body: str,
    text_body: str,
) -> tuple[int, str | None, str | None]:
    """POST to Brevo's transactional API.

    Returns (sent_count, message_id, error). On any failure, sent_count is 0,
    message_id is None, error is a short string.
    """
    import json as _stdjson

    payload = {
        "sender": {"email": from_email, "name": from_name},
        "to": [{"email": s.email, "name": s.name} for s in subscribers],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": text_body,
    }
    req = Request(
        _BREVO_URL,
        data=_stdjson.dumps(payload).encode("utf-8"),
        headers={
            "api-key": api_key,
            "content-type": "application/json",
            "accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=30) as r:
            body = _stdjson.loads(r.read().decode("utf-8"))
            return len(subscribers), body.get("messageId"), None
    except urllib.error.HTTPError as e:
        return 0, None, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return 0, None, f"{type(e).__name__}: {e}"
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
.venv/bin/pytest tests/test_notifier.py -v
```

Expected: `28 passed`

- [ ] **Step 5: Commit**

```bash
git add brief/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): send_via_brevo() — fail-open HTTP POST to Brevo API"
```

---

### Task 9: `notify()` — top-level orchestration

**Files:**
- Modify: `brief/notifier.py` (add function + logger)
- Modify: `tests/test_notifier.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_notifier.py`:

```python
from brief.notifier import notify


def test_notify_happy_path(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")
    monkeypatch.setenv("BREVO_API_KEY", "brevo-key")
    monkeypatch.setenv("FROM_EMAIL", "adnan@example.com")

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        if "/briefs?" in url:
            body = _json.dumps([{
                "id": "f54ac95d", "issue_no": 107, "volume": 1,
                "brief_date": "2026-05-15", "published_at": "2026-05-15T09:33:12+00:00",
                "todays_call": "x", "lens": "weekly_wrap",
            }]).encode()
        elif "/sections?" in url:
            body = _json.dumps([{"id": "sec-uuid"}]).encode()
        elif "/news?" in url:
            body = _json.dumps([{
                "headline": "h", "source": "s",
                "source_url": "https://example.com",
                "published_at": "2026-05-14T00:30:00+00:00",
            }]).encode()
        elif "/subscribers?" in url:
            body = _json.dumps([
                {"name": "Mehrin", "email": "m@brac.com", "organisation": "BRAC"},
            ]).encode()
        elif url == "https://api.brevo.com/v3/smtp/email":
            body = b'{"messageId":"<abc@brevo>"}'
        else:
            raise AssertionError(f"unexpected URL: {url}")
        return _FakeResp(body)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    result = notify("f54ac95d")

    assert result.sent_count == 1
    assert result.message_id == "<abc@brevo>"
    assert result.error is None


def test_notify_returns_no_api_key_error_when_brevo_key_missing(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    # urlopen should not be called — so set a tripwire
    def tripwire(*a, **kw):
        raise AssertionError("urlopen called despite missing BREVO_API_KEY")
    monkeypatch.setattr(notifier_mod, "urlopen", tripwire)

    result = notify("f54ac95d")
    assert result.sent_count == 0
    assert result.error == "no_api_key"


def test_notify_returns_no_subscribers_when_table_empty(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")
    monkeypatch.setenv("BREVO_API_KEY", "brevo-key")
    monkeypatch.setenv("FROM_EMAIL", "adnan@example.com")

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        if "/briefs?" in url:
            body = _json.dumps([{
                "id": "x", "issue_no": 1, "volume": 1,
                "brief_date": "2026-05-15", "published_at": "2026-05-15T00:30:00+00:00",
                "todays_call": "x", "lens": None,
            }]).encode()
        elif "/sections?" in url:
            body = b"[]"
        elif "/subscribers?" in url:
            body = b"[]"
        else:
            raise AssertionError(f"unexpected URL: {url}")
        return _FakeResp(body)

    monkeypatch.setattr(notifier_mod, "urlopen", fake_urlopen)

    result = notify("x")
    assert result.sent_count == 0
    assert result.error == "no_subscribers"


def test_notify_swallows_unexpected_exception(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")
    monkeypatch.setenv("BREVO_API_KEY", "brevo-key")

    def boom(req, timeout=None):
        raise RuntimeError("unexpected!")

    monkeypatch.setattr(notifier_mod, "urlopen", boom)

    result = notify("x")
    assert result.sent_count == 0
    assert result.error is not None
    assert "unexpected" in result.error.lower()
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
.venv/bin/pytest tests/test_notifier.py::test_notify_happy_path -v
```

Expected: `ImportError: cannot import name 'notify'`

- [ ] **Step 3: Write minimal implementation**

Append to `brief/notifier.py`:

```python
import logging

logger = logging.getLogger(__name__)


def notify(brief_id: str) -> NotifyResult:
    """Top-level entry. Fail-open: any error logged and returned in NotifyResult.

    Reads BREVO_API_KEY, FROM_EMAIL, SUPABASE_URL, SUPABASE_SERVICE_KEY from env.
    """
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    if not api_key:
        logger.warning("notifier: BREVO_API_KEY not set, skipping send")
        return NotifyResult(sent_count=0, skipped_count=0, message_id=None, error="no_api_key")

    from_email = os.environ.get("FROM_EMAIL", "").strip() or "noreply@example.com"

    try:
        brief, lead_news = fetch_brief_data(brief_id)
    except Exception as e:
        logger.exception("notifier: failed to fetch brief data: %s", e)
        return NotifyResult(sent_count=0, skipped_count=0, message_id=None, error=f"fetch_brief: {e}")

    try:
        subscribers = fetch_subscribers()
    except Exception as e:
        logger.exception("notifier: failed to fetch subscribers: %s", e)
        return NotifyResult(sent_count=0, skipped_count=0, message_id=None, error=f"fetch_subs: {e}")

    if not subscribers:
        logger.info("notifier: no subscribers, skipping send")
        return NotifyResult(sent_count=0, skipped_count=0, message_id=None, error="no_subscribers")

    subject, html_body, text_body = render_email(brief=brief, lead_news=lead_news)

    sent_count, message_id, error = send_via_brevo(
        api_key=api_key,
        from_email=from_email,
        from_name="The Brief",
        subscribers=subscribers,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
    )

    if error:
        logger.error("notifier: Brevo send failed: %s", error)
    else:
        logger.info("notifier: sent=%d message_id=%s", sent_count, message_id)

    return NotifyResult(
        sent_count=sent_count,
        skipped_count=0,
        message_id=message_id,
        error=error,
    )
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
.venv/bin/pytest tests/test_notifier.py -v
```

Expected: `32 passed`

- [ ] **Step 5: Commit**

```bash
git add brief/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): notify() — top-level orchestration with fail-open error handling"
```

---

### Task 10: Wire `notify()` into `cli._run_v6_publish`

**Files:**
- Modify: `brief/cli.py` (add `--no-notify` flag + call notify after V6 publish ok)

- [ ] **Step 1: Read the current cli.py to confirm exact line locations**

```bash
cat brief/cli.py
```

Locate two regions:
- The `_parse()` function (~line 28-40) — argparse setup
- The end of `_run_v6_publish()` (~line 82-86) — after the `log.info("V6 publish ok: brief_id=%s", brief_id)` line

- [ ] **Step 2: Add the `--no-notify` flag in `_parse()`**

In `brief/cli.py`, locate this block in `_parse()`:

```python
    r.add_argument("--today", default=None,
                   help="Override today's date (YYYY-MM-DD); default: system date")
    return p.parse_args(argv)
```

Replace with:

```python
    r.add_argument("--today", default=None,
                   help="Override today's date (YYYY-MM-DD); default: system date")
    r.add_argument("--no-notify", action="store_true",
                   help="Skip the subscriber email notifier after a successful publish")
    return p.parse_args(argv)
```

- [ ] **Step 3: Wire `notify()` into `_run_v6_publish`**

In `brief/cli.py`, locate this block at the end of `_run_v6_publish()`:

```python
    if dry_run:
        log.info("V6 dry-run: editor + subeditor passed, no Supabase write")
        return 3
    log.info("V6 publish ok: brief_id=%s", brief_id)
    return 0
```

The function takes `cfg` and `today` and `dry_run` as args, but not `ns`. The flag check has to happen in `main()` and be passed in. Restructure:

Change the `_run_v6_publish` signature in `brief/cli.py`:

```python
def _run_v6_publish(cfg: PipelineConfig, today: date, dry_run: bool, notify_enabled: bool) -> int:
```

Change the end of `_run_v6_publish` to:

```python
    if dry_run:
        log.info("V6 dry-run: editor + subeditor passed, no Supabase write")
        return 3
    log.info("V6 publish ok: brief_id=%s", brief_id)

    if notify_enabled and brief_id:
        try:
            from brief.notifier import notify as _notify
            result = _notify(brief_id)
            log.info(
                "notifier: sent=%d skipped=%d message_id=%s error=%s",
                result.sent_count, result.skipped_count, result.message_id, result.error,
            )
        except Exception:
            # Last-resort fail-open: even an import error must not crash a successful publish
            log.exception("notifier: unexpected exception (publish remains successful)")

    return 0
```

Change the `main()` invocation in `brief/cli.py`:

```python
    if ns.publish:
        return _run_v6_publish(cfg, today, dry_run=ns.dry_run, notify_enabled=not ns.no_notify)
```

- [ ] **Step 4: Smoke-check with dry-run**

```bash
.venv/bin/python -m brief.cli run --publish --dry-run --no-notify
```

Expected: Exit code 3 (V6 dry-run-ok). Confirms `--no-notify` parses and `_run_v6_publish` still works for dry runs.

```bash
echo $?
```

Expected: `3`

- [ ] **Step 5: Full test suite — nothing else broke**

```bash
.venv/bin/pytest -q
```

Expected: All previous tests still pass (~444 before this PR + 32 new notifier tests = 476+ passing).

- [ ] **Step 6: Commit**

```bash
git add brief/cli.py
git commit -m "feat(cli): wire notifier into _run_v6_publish + --no-notify opt-out flag"
```

---

### Task 11: Re-add `BREVO_API_KEY` and `FROM_EMAIL` to `.env.example`

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Read current `.env.example`**

```bash
cat .env.example
```

Confirm the current state (no BREVO_API_KEY, no FROM_EMAIL — these were dropped in `9ff80e4`).

- [ ] **Step 2: Add the two lines back in the Publisher block**

Locate this section in `.env.example`:

```
# ─── Publisher (Python pipeline, Phase 2) ─────────────────────
ANTHROPIC_API_KEY=sk-ant-...
BREVO_API_KEY=xkeysib-...
SUPABASE_SERVICE_KEY=eyJ...
SUPABASE_URL=https://ssbliukchgibjcjohibi.supabase.co
ALPHA_VANTAGE_KEY=your-key-here
ALERT_WEBHOOK_URL=https://hooks.slack.com/...
```

The `BREVO_API_KEY=xkeysib-...` line is already present (we confirmed earlier). Add `FROM_EMAIL` immediately below it. Replace the block with:

```
# ─── Publisher (Python pipeline, Phase 2) ─────────────────────
ANTHROPIC_API_KEY=sk-ant-...
BREVO_API_KEY=xkeysib-...
FROM_EMAIL=hello@thebrief.clauding-lab.com
SUPABASE_SERVICE_KEY=eyJ...
SUPABASE_URL=https://ssbliukchgibjcjohibi.supabase.co
ALPHA_VANTAGE_KEY=your-key-here
ALERT_WEBHOOK_URL=https://hooks.slack.com/...
```

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs(env): re-add FROM_EMAIL to .env.example (notifier dependency)"
```

---

### Task 12: Live smoke test on Hetzner + open PR

**Files:** (none modified)

- [ ] **Step 1: Push the feature branch**

```bash
git push -u origin feat/release-notifier
```

Expected: branch `feat/release-notifier` pushed to origin with all 11 commits (10 implementation + 1 docs).

- [ ] **Step 2: Open PR via gh — DO NOT MERGE YET**

```bash
gh pr create --base main --head feat/release-notifier --title "feat(notifier): restore release email send on V6 publish" --body "$(cat <<'EOF'
## Summary

Restores subscriber-email-on-publish, deleted with commit \`9ff80e4\` on 2026-05-04 ("drop V5 notification stack"). New \`brief/notifier.py\` (~150 lines) wired into \`cli._run_v6_publish\` via one extra line + a new \`--no-notify\` opt-out flag.

Spec: \`docs/superpowers/specs/2026-05-15-release-notifier-design.md\`
Plan: \`docs/superpowers/plans/2026-05-15-release-notifier.md\`
Sample email validated 2026-05-15 against Issue 107 → \`adnan.rshd@gmail.com\` (Brevo messageId \`202605151043.67638140215\`); user approved before spec write.

## What it does

After every successful \`brief.cli run --publish\`:
1. Fetches the brief row + lead headline from Supabase
2. Fetches all rows from \`subscribers\`
3. Renders HTML + plain-text body
4. POSTs once to Brevo with multi-recipient \`to:\` list

Fail-open: any error logged, NotifyResult.error carries a short tag, publish exit code stays 0.

## Out of scope (separate specs)

- One-click unsubscribe automation (uses \`mailto:\` link for now)
- Discord webhook restoration (\`brief/notify.py\`, also in 9ff80e4)
- Open/click tracking, DKIM/SPF setup, bounce-webhook handling

## Test plan

- [ ] CI: \`pytest -q\` green (32 new tests in tests/test_notifier.py)
- [ ] After merge: Hetzner \`git pull --ff-only && git log -1\`
- [ ] Manual live trigger on Hetzner: \`.venv/bin/python -m brief.cli run --publish --dry-run\` → still exit 3, no notifier invoked
- [ ] Manual live trigger WITH notify: \`sudo systemctl start brief.service\` → check logs/brief-systemd.log for \`notifier: sent=N message_id=...\` line, check inbox
- [ ] Next auto-fire (Sun 2026-05-17 06:30 BDT) — Issue 109 lands in inbox automatically
EOF
)"
```

Capture the PR URL printed.

- [ ] **Step 3: Live smoke test on Hetzner (do NOT touch production until PR is approved)**

After PR is reviewed and merged via \`gh pr merge --squash --delete-branch\`:

```bash
ssh adnan@135.181.43.68 "cd ~/the-brief && git pull --ff-only && git log -1 --oneline"
```

Expected: HEAD is now the squash-merge commit.

- [ ] **Step 4: One-off live send to validate end-to-end on Hetzner**

The next scheduled fire is Sun 2026-05-17 06:30 BDT. To validate sooner, trigger a notifier-only call against the most recent brief_id (Issue 107) via Python REPL on Hetzner:

```bash
ssh adnan@135.181.43.68 'cd ~/the-brief && set -a && source /etc/brief.env && set +a && .venv/bin/python -c "from brief.notifier import notify; r = notify(\"f54ac95d-2127-44f4-bb02-9bd0f7fc5de8\"); print(r)"'
```

Expected: \`NotifyResult(sent_count=5, skipped_count=0, message_id='<...>', error=None)\`

Verify \`adnan.rshd@gmail.com\` receives the email in inbox (or spam, mark inbox).

- [ ] **Step 5: Verify Sunday 2026-05-17 06:30 BDT auto-fire**

After Sunday's fire, check Hetzner logs:

```bash
ssh adnan@135.181.43.68 "tail -50 ~/the-brief/logs/brief-systemd.log | grep notifier"
```

Expected: \`notifier: sent=5 message_id=<...> error=None\`

Check inbox — should see Issue 109 by ~06:35 BDT.

- [ ] **Step 6: Close out**

If all 5 sub-steps pass, the feature is live. No further commits needed. Optionally save a project memory:

```
~/.claude/projects/-Users-adnanrashid-Projects-clauding-lab-the-brief/memory/feedback_notifier_live.md
```

---

## Self-Review

**Spec coverage check** — running through each spec section:

| Spec section | Where in plan |
|---|---|
| Goal: every publish sends to all subscribers | Tasks 9 (notify orchestration), 10 (CLI hook) |
| `brief/notifier.py` with Subscriber + NotifyResult dataclasses | Task 1 |
| `fetch_subscribers()` | Task 6 |
| `render_email()` returning (subject, html, text) | Tasks 2-5 |
| `notify(brief_id)` top-level | Task 9 |
| Hook at end of `_run_v6_publish` | Task 10 |
| `--no-notify` opt-out flag | Task 10 |
| Env vars BREVO_API_KEY, FROM_EMAIL, SUPABASE_* | Task 9 (used), Task 11 (.env.example) |
| Subject format `The Brief · No. N · ...` | Task 2 |
| HTML body with cream-paper palette, Georgia, hairlines | Task 4 |
| Plain text fallback | Task 3 |
| Fail-open behavior table (7 rows) | Task 9 covers all 7 via try/except |
| One Brevo POST per publish, multi-recipient | Task 8 (payload structure) |
| Lead news omitted entirely if None | Tasks 3, 4, 5 (explicit tests) |
| Testing: unit + mocked integration | Tasks 1-9 each include tests |
| Migration: no DB, no env, no deps | Verified — none added |
| Decisions all confirmed | Yes — all decisions baked into specific tasks |

No gaps.

**Placeholder scan** — searched for "TBD", "TODO", "implement later", "similar to Task", "add appropriate" — none found. All code blocks contain actual code. All commands include expected output where relevant.

**Type consistency check:**
- `BriefRow` defined in Task 3, used in Tasks 3-9 — consistent fields throughout.
- `NewsRow` defined in Task 3, used in Tasks 3-9 — `headline`, `source`, `source_url`, `published_at` consistent.
- `Subscriber` defined in Task 1, used in Tasks 6, 8, 9 — `name`, `email`, `organisation` consistent.
- `NotifyResult` defined in Task 1, used in Tasks 9, 10 — `sent_count`, `skipped_count`, `message_id`, `error` consistent.
- `render_email` signature `(*, brief, lead_news) -> (subject, html, text)` — same in Task 5 and Task 9.
- `notify(brief_id: str) -> NotifyResult` — Task 9 and Task 10 consistent.
- `_supabase_config()` introduced Task 6, reused Task 7 — same return shape `(url, key)`.
- `_hhmm_bdt`, `_lens_phrase`, `_esc`, `_parse_iso`, `_json_loads` are all module-private helpers — consistent throughout.

All good.
