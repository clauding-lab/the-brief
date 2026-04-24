"""Small JSX helpers shared by every section template."""
from __future__ import annotations

from typing import Optional

from brief.schema import BankerReadInsight, FreshnessKind


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace('"', "&quot;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )


def attr(name: str, value: object) -> str:
    """Render a JSX attribute. Returns '' when value is None."""
    if value is None:
        return ""
    return f'{name}="{_esc(str(value))}"'


def fmt_num(n: object, decimals: int = 2) -> str:
    if n is None:
        return "—"
    try:
        return f"{float(n):,.{decimals}f}"
    except (TypeError, ValueError):
        return str(n)


_PILL_CLASS = {
    "fresh":       "",
    "warning":     "pill pill-warning",
    "stale":       "pill pill-stale",
    "pending":     "pill pill-pending",
    "unavailable": "pill pill-unavailable",
}


def freshness_pill(kind: FreshnessKind) -> str:
    if kind == "fresh":
        return ""
    label = {
        "warning": "Approaching stale",
        "stale": "Stale",
        "pending": "Awaiting next release",
        "unavailable": "Data missing",
    }[kind]
    cls = _PILL_CLASS[kind]
    return f'<span className="{cls}">{label}</span>'


def bankerread_tag(br: BankerReadInsight | None) -> str:
    if br is None:
        return ""
    if br.kind == "structured":
        joined = f"{br.meaning} {br.action} {br.trigger} {br.focus}"
    else:
        joined = br.text
    joined = joined.replace('"', "'").replace("\n", " ")
    return f'<BankerRead insight="{_esc(joined)}" />'
