"""Builder: Executive Signals — consumes Claude Call 2 output.

Phase 2 stub: produces empty SectionData so the smoke matrix passes; the
real exec_signals list is injected in Phase 3 via ctx.claude_outputs.
"""
from __future__ import annotations

from brief.schema import ExecSignal, SectionData
from . import BuilderContext


def build(ctx: BuilderContext) -> SectionData:
    raw = (ctx.claude_outputs or {}).get("exec_signals") or {}
    signals_payload = raw.get("signals", []) if isinstance(raw, dict) else []
    signals: list[ExecSignal] = []
    for s in signals_payload:
        try:
            signals.append(ExecSignal(
                direction=s["direction"],
                text=s["text"],
                section_anchor=s["section_anchor"],
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return SectionData(
        id="exec",
        title="Executive Signals",
        freshness="fresh" if signals else "pending",
        exec_signals=signals or None,
    )
