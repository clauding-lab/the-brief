"""Deterministic post-LLM diff stamping for V6 briefs.

Walks the editor's output against the previous published brief and stamps
`changed=true/false` on every news item and metric. Replaces the missing
diff signal that V5 used to compute and that V6 dropped.
"""
from __future__ import annotations

import re
from typing import Any

from brief.v6_schema import BriefPayloadV6


_PUNCT_WHITESPACE = re.compile(r"[^\w]+")


def _normalize_headline(text: str) -> str:
    """Lowercase + strip non-word characters. Whitespace and punctuation collapse."""
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
