"""Deterministic post-LLM diff stamping for V6 briefs.

Walks the editor's output against the previous published brief and stamps
`changed=true/false` on every news item and metric. Replaces the missing
diff signal that V5 used to compute and that V6 dropped.
"""
from __future__ import annotations

import re
from datetime import date as date_t, timedelta
from typing import Any, Iterable

from brief.v6_schema import BriefPayloadV6


_PUNCT_WHITESPACE = re.compile(r"[^\w]+")


def _normalize_headline(text: str) -> str:
    """Lowercase + strip non-word characters. Whitespace and punctuation collapse.

    # NOTE: Python's `\\w` does not match Unicode combining marks (Mn/Mc).
    # Bengali matras (া, ি, ্, etc.) get stripped. Distinct Bengali headlines
    # that share their consonant skeleton may collide. Acceptable for now;
    # revisit if a real collision is observed in production.
    """
    return _PUNCT_WHITESPACE.sub("", text.lower())


def _index_previous_news(previous_brief: dict[str, Any] | None) -> set[tuple[str, str]]:
    """Build a set of (headline_normalized, source_url) keys from the previous brief."""
    if not previous_brief:
        return set()
    keys: set[tuple[str, str]] = set()
    for section in previous_brief.get("sections", []):
        for n in section.get("news", []) or []:
            keys.add((
                _normalize_headline(n.get("headline", "")),
                (n.get("source_url") or "").strip(),
            ))
    return keys


def _index_previous_metrics(previous_brief: dict[str, Any] | None) -> dict[tuple[str, str], str]:
    """Build a map of (section_slug, label) → previous value text."""
    if not previous_brief:
        return {}
    out: dict[tuple[str, str], str] = {}
    for section in previous_brief.get("sections", []):
        slug = section.get("slug", "")
        for m in section.get("metrics", []) or []:
            out[(slug, m.get("label", ""))] = m.get("value", "")
    return out


def stamp_changed(current: BriefPayloadV6, previous_brief: dict[str, Any] | None) -> None:
    """Mutate `current` in place: stamp `changed=True/False` on every news + metric.

    Rules:
    - News: changed=True if (normalized_headline, source_url) is NOT in previous brief.
    - Metric: changed=True if (slug, label) IS in previous brief AND value text differs.
              changed=True also if (slug, label) is brand new (not in previous).
              changed=False if (slug, label) matches and value text is identical.
    - When previous_brief is None: everything is changed=True (cold start).
    """
    prev_news = _index_previous_news(previous_brief)
    prev_metrics = _index_previous_metrics(previous_brief)

    for section in current.sections:
        for n in section.news:
            key = (_normalize_headline(n.headline), (n.source_url or "").strip())
            n.changed = key not in prev_news

        for m in section.metrics:
            key = (section.slug, m.label)
            if key not in prev_metrics:
                m.changed = True
            else:
                m.changed = prev_metrics[key] != m.value


_CADENCE_DAYS: dict[str, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 91,
    "annual": 365,
}

_CADENCE_LABEL: dict[str, str] = {
    "monthly": "next month",
    "quarterly": "next quarter",
    "annual": "next year",
}

_HELD_OVER_CADENCES = {"monthly", "quarterly", "annual"}


def _compute_next_print(last_print: date_t, cadence: str) -> str:
    """Return a free-text label for the next expected print, e.g. 'Jul 2026' or 'Q3 2026'."""
    days = _CADENCE_DAYS.get(cadence, 0)
    if not days:
        return _CADENCE_LABEL.get(cadence, "")
    next_date = last_print + timedelta(days=days)
    if cadence == "quarterly":
        # Tag with quarter label
        q = (next_date.month - 1) // 3 + 1
        return f"Q{q} {next_date.year} (≈ {next_date.strftime('%b %Y')})"
    if cadence == "monthly":
        return next_date.strftime("%b %Y")
    if cadence == "annual":
        return str(next_date.year)
    return next_date.isoformat()


def _index_definitions(definitions: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(section_slug, label) → catalog row."""
    return {(d.get("section_slug", ""), d.get("label", "")): d for d in definitions}


def mark_held_overs(
    current: BriefPayloadV6,
    previous_brief: dict[str, Any] | None,
    metric_definitions: Iterable[dict[str, Any]],
) -> None:
    """Mutate `current` in place: annotate held-over metrics with held_from + next_print.

    A metric is held-over if all of:
      - It exists in the previous brief at the same (slug, label)
      - Its value text is identical (i.e. changed=False)
      - Its cadence in the catalog is monthly/quarterly/annual

    Daily/weekly metrics are never held-over (they should be moving).
    """
    if not previous_brief:
        return

    catalog = _index_definitions(metric_definitions)

    for section in current.sections:
        for m in section.metrics:
            if m.changed:
                continue
            row = catalog.get((section.slug, m.label))
            if not row:
                continue
            cadence = row.get("cadence", "")
            if cadence not in _HELD_OVER_CADENCES:
                continue
            last_print_str = row.get("last_print_date")
            if not last_print_str:
                continue
            try:
                last_print = date_t.fromisoformat(last_print_str)
            except ValueError:
                continue
            m.held_from = last_print
            m.next_print = _compute_next_print(last_print, cadence)
