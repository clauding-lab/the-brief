"""Headline re-run filter for V6 briefs.

Drops candidates whose (normalized_headline, source_url) appeared in the
last N issues. Pure function, deterministic, no LLM.
"""
from __future__ import annotations

import re
from typing import Any


_PUNCT_WHITESPACE = re.compile(r"[^\w]+")


def _normalize(text: str) -> str:
    return _PUNCT_WHITESPACE.sub("", (text or "").lower())


def _key(item: dict[str, Any]) -> tuple[str, str]:
    return (_normalize(item.get("headline", "")), (item.get("source_url") or "").strip())


def filter_headlines(
    candidates: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Return (kept_candidates, dropped_count).

    A candidate is dropped if its (normalized_headline, source_url) appears
    anywhere in `history`. Order of kept items is preserved.

    `history` is the flat union of news items from the previous N issues —
    the caller (pipeline_v6) is responsible for assembling it.
    """
    seen = {_key(h) for h in history}
    kept: list[dict[str, Any]] = []
    dropped = 0
    for c in candidates:
        if _key(c) in seen:
            dropped += 1
            continue
        kept.append(c)
    return kept, dropped
