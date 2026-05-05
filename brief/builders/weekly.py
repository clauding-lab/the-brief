"""Friday weekly-wrap input builder.

Augments the standard editor input with a `weekly_diffs` block: Mon–Fri
section deltas, biggest-σ-mover, sectoral verdicts. The Friday editor
prompt consumes this block to produce a 5-day synthesis.
"""
from __future__ import annotations

from datetime import date as date_t, timedelta
from typing import Any


def build_weekly_input(base_input: dict[str, Any], *, today: date_t) -> dict[str, Any]:
    """Take the standard editor_input and add a `weekly_diffs` block for Friday.

    For V1, weekly_diffs is a placeholder block that summarizes today's sections
    only — the Friday prompt instructs the editor to synthesize across Mon–Fri
    using its own context. A V2 enhancement could fetch Mon–Thu briefs from
    Supabase and compute exact per-day deltas; for V1 we rely on the editor's
    access to previous_brief plus its instruction to write a wrap.
    """
    if today.weekday() != 4:
        raise ValueError(f"build_weekly_input called on non-Friday: {today} (weekday={today.weekday()})")

    out = dict(base_input)
    out["today_lens"] = "weekly_wrap"
    out["weekly_diffs"] = {
        "week_of": (today - timedelta(days=today.weekday())).isoformat(),
        "today": today.isoformat(),
        "note": "Synthesize across Mon–Fri using your access to previous_brief and the sections in this input. Highlight biggest movers of the week.",
    }
    return out
