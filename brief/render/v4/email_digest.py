"""V4 plain-text email digest for subscriber distribution.

Renders a human-readable plain-text summary of the Brief for email delivery.
No HTML tags. No HTML entities. Pure UTF-8 with standard line endings.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from brief.pipeline import RunResult

_BDT_TZ = ZoneInfo("Asia/Dhaka")
_HOSTED_URL = "https://the-brief.example.com/"
_VOL_ISSUE = "Vol. II · No. 412"


def _strip_html(text: str) -> str:
    """Remove any accidental HTML tags and unescape common entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    return text.strip()


def _clean(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    return " ".join(_strip_html(text).split())


def _fmt_dateline(now: datetime) -> str:
    """Format as 'Tue 24 Apr 2026 · 06:15 BDT'."""
    day_date = now.strftime("%a %-d %b %Y")
    time_str = now.strftime("%H:%M BDT")
    return f"{day_date} · {time_str}"


def render_email_digest(run_result: "RunResult") -> str:
    """Return plain-text email digest for subscribers.

    Structure:
        THE BRIEF · Vol. II · No. 412
        Tue 24 Apr 2026 · 06:15 BDT

        TODAY'S CALL
        <todays_call.text>
        — <todays_call.byline>

        TOP 3 SIGNALS
        • <sig 1>
        • <sig 2>
        • <sig 3>

        LEAD HEADLINE
        <title>
        <source> · <time HH:MM BDT>
        <url>

        Full edition → https://the-brief.example.com/
    """
    now = datetime.now(tz=_BDT_TZ)
    dateline = _fmt_dateline(now)

    lines: list[str] = []

    # ── Masthead ──────────────────────────────────────────────────────────────
    lines.append(f"THE BRIEF · {_VOL_ISSUE}")
    lines.append(dateline)
    lines.append("")

    # ── Today's Call ─────────────────────────────────────────────────────────
    lines.append("TODAY'S CALL")
    tc = run_result.todays_call
    if tc is not None:
        lines.append(_clean(tc.text))
        lines.append(f"— {_clean(tc.byline)}")
    else:
        lines.append("(no editorial call today)")
    lines.append("")

    # ── Top 3 Signals ────────────────────────────────────────────────────────
    lines.append("TOP 3 SIGNALS")
    signals_raw = (
        run_result.claude_outputs.get("exec_signals", {}).get("signals", [])
        if run_result.claude_outputs
        else []
    )
    if signals_raw:
        for sig in signals_raw[:3]:
            sig_text = _clean(sig.get("text", ""))
            anchor = sig.get("section_anchor", "")
            if anchor:
                lines.append(f"• {sig_text} — #{anchor}")
            else:
                lines.append(f"• {sig_text}")
    else:
        lines.append("(no signals today)")
    lines.append("")

    # ── Lead Headline ─────────────────────────────────────────────────────────
    lines.append("LEAD HEADLINE")
    headlines_section = next(
        (s for s in run_result.sections if s.id == "headlines"), None
    )
    lead_item = None
    if headlines_section and headlines_section.news:
        lead_item = headlines_section.news[0]

    if lead_item is not None:
        lines.append(_clean(lead_item.title))
        pub_time = lead_item.published.astimezone(_BDT_TZ).strftime("%H:%M BDT")
        lines.append(f"{_clean(lead_item.source)} · {pub_time}")
        lines.append(lead_item.url)
    else:
        lines.append("(no lead headline today)")
    lines.append("")

    # ── Footer ───────────────────────────────────────────────────────────────
    lines.append(f"Full edition → {_HOSTED_URL}")

    return "\n".join(lines)
