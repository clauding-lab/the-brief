"""Headline re-run filter for V6 briefs.

Drops candidates whose (normalized_headline, source_url) appeared in the
last N issues. Pure function, deterministic, no LLM.
"""
from __future__ import annotations

import re
from typing import Any


_PUNCT_WHITESPACE = re.compile(r"[^\w]+")


def _normalize(text: str) -> str:
    """Lowercase + strip non-word characters. Whitespace and punctuation collapse.

    # NOTE: Python's `\\w` does not match Unicode combining marks (Mn/Mc).
    # Bengali matras (া, ি, ্, etc.) get stripped. Distinct Bengali headlines
    # that share their consonant skeleton may collide. Acceptable for now;
    # revisit if a real collision is observed in production. Keep in lockstep
    # with diff.py:_normalize_headline — if they drift, see plan §2.3.
    """
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

    Candidates whose key is empty (both headline and source_url missing/empty)
    are kept unconditionally — we can't tell duplicates apart, so we don't
    risk silently dropping unrelated malformed records.
    """
    seen = {_key(h) for h in history}
    kept: list[dict[str, Any]] = []
    dropped = 0
    for c in candidates:
        k = _key(c)
        if k == ("", ""):
            kept.append(c)
            continue
        if k in seen:
            dropped += 1
            continue
        kept.append(c)
    return kept, dropped
