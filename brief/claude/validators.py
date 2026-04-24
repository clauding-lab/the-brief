"""Validators for the three Claude calls. Each returns a ValidationResult.

Contract: validator never raises. On malformed input it sets ok=False and
returns a reason. On partial validity (insights), ok=True but invalid
per-section entries are moved to `dropped` so the caller can fall back
per section.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

_VALID_WEIGHTS = {"high", "med", "low"}
_VALID_DIRECTIONS = {"bull", "bear", "warn", "watch"}
_VALID_TRAFFIC = {"bull", "bear", "warn", "neu"}


@dataclass
class ValidationResult:
    ok: bool
    value: Any = None
    reason: str = ""
    dropped: dict[str, str] = field(default_factory=dict)


def _is_dict(x: Any) -> bool:
    return isinstance(x, dict)


def validate_curation(payload: Any, *, allowed_urls: set[str]) -> ValidationResult:
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    selected = payload.get("selected")
    if not isinstance(selected, list) or not (8 <= len(selected) <= 15):
        # spec says 8-15, but tolerate smaller sets in case headline pool is thin
        if not isinstance(selected, list) or not (1 <= len(selected) <= 20):
            return ValidationResult(False, reason="selected size out of range")

    for item in selected:
        if not _is_dict(item):
            return ValidationResult(False, reason="selected item not a dict")
        url = item.get("url")
        weight = item.get("weight")
        if url not in allowed_urls:
            return ValidationResult(False, reason=f"unknown url: {url!r}")
        if weight not in _VALID_WEIGHTS:
            return ValidationResult(False, reason=f"bad weight: {weight!r}")
    if not isinstance(payload.get("rationale_bullet"), str):
        return ValidationResult(False, reason="rationale_bullet not a string")
    return ValidationResult(True, value=payload)


def validate_signals(payload: Any, *, allowed_anchors: set[str]) -> ValidationResult:
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    signals = payload.get("signals")
    if not isinstance(signals, list) or not signals:
        return ValidationResult(False, reason="no signals")
    for s in signals:
        if not _is_dict(s):
            return ValidationResult(False, reason="signal not a dict")
        if s.get("direction") not in _VALID_DIRECTIONS:
            return ValidationResult(False, reason=f"bad direction: {s.get('direction')!r}")
        if s.get("section_anchor") not in allowed_anchors:
            return ValidationResult(False, reason=f"bad anchor: {s.get('section_anchor')!r}")
        text = s.get("text")
        if not isinstance(text, str) or len(text.split()) > 20:
            return ValidationResult(False, reason="text too long or missing")
    if payload.get("traffic_status") not in _VALID_TRAFFIC:
        return ValidationResult(False, reason=f"bad traffic_status: {payload.get('traffic_status')!r}")
    return ValidationResult(True, value=payload)


def validate_insights(
    payload: Any, *, allowed_section_ids: Iterable[str], stale: bool,
) -> ValidationResult:
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    insights = payload.get("insights")
    if not _is_dict(insights):
        return ValidationResult(False, reason="insights not a dict")

    expected_len = 1 if stale else 4
    allowed = set(allowed_section_ids)
    kept: dict[str, list[str]] = {}
    dropped: dict[str, str] = {}

    for sid, sentences in insights.items():
        if sid not in allowed:
            dropped[sid] = "section not in allowed set"
            continue
        if not isinstance(sentences, list) or len(sentences) != expected_len:
            dropped[sid] = f"wrong sentence count (need {expected_len})"
            continue
        if not all(isinstance(s, str) for s in sentences):
            dropped[sid] = "non-string sentence"
            continue
        if any('"' in s for s in sentences):
            dropped[sid] = "contains double quote (JSX-breaking)"
            continue
        kept[sid] = list(sentences)

    return ValidationResult(
        ok=True,
        value={"insights": kept},
        dropped=dropped,
    )
