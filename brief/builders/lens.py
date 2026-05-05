"""Data-driven daily lens scorer for V6 briefs.

Mon–Thu: pick the section with highest score_freshness × score_magnitude × score_signal.
Friday: lens hardcoded to "weekly_wrap".

Returns (lens_slug, breakdown_dict) for logging visibility.
"""
from __future__ import annotations

from datetime import date as date_t
from typing import Any


_QUIET_DAY_THRESHOLD = 0.05


def _freshness_score(days_since_refresh: int) -> float:
    """Linear decay: today=1.0, 7d=0.5, ≥14d=0.0."""
    if days_since_refresh < 0:
        days_since_refresh = 0
    return max(0.0, 1.0 - days_since_refresh / 14.0)


def _magnitude_score(metrics: list[dict[str, Any]]) -> float:
    """Largest |delta_sigma| in section, clamped to [0, 1]."""
    if not metrics:
        return 0.0
    best = 0.0
    for m in metrics:
        ds = abs(float(m.get("delta_sigma", 0.0) or 0.0))
        if ds > best:
            best = ds
    return min(1.0, best)


def _signal_score(metrics: list[dict[str, Any]]) -> float:
    """1 − fraction of metrics flagged is_held_over. Empty section → 0."""
    if not metrics:
        return 0.0
    held = sum(1 for m in metrics if m.get("is_held_over"))
    return 1.0 - (held / len(metrics))


def score_lens(
    sections: list[dict[str, Any]],
    *,
    today: date_t,
    previous_lens: str | None,
) -> tuple[str, dict[str, Any]]:
    """Pick today's editorial lens.

    Friday → "weekly_wrap" unconditionally.
    Mon–Thu → highest section_score = freshness × magnitude × signal.
    Quiet day (all scores < 0.05) → fall back to previous_lens, else alphabetically first slug.

    Returns (lens_slug, breakdown) where breakdown has per-section score components
    plus an optional "fallback" key.
    """
    if today.weekday() == 4:  # Friday
        return "weekly_wrap", {"reason": "friday"}

    breakdown: dict[str, Any] = {}
    for s in sections:
        slug = s["slug"]
        f = _freshness_score(int(s.get("freshness_days_since_refresh", 0) or 0))
        m = _magnitude_score(s.get("metrics", []) or [])
        sig = _signal_score(s.get("metrics", []) or [])
        score = f * m * sig
        breakdown[slug] = {"freshness": f, "magnitude": m, "signal": sig, "score": score}

    if not breakdown:
        return "banking", {"fallback": "no_sections"}

    # Find highest-scoring section
    best_slug = None
    best_score = -1.0
    for slug, b in breakdown.items():
        if b["score"] > best_score or (b["score"] == best_score and (best_slug is None or slug < best_slug)):
            best_score = b["score"]
            best_slug = slug

    if best_score < _QUIET_DAY_THRESHOLD:
        if previous_lens:
            breakdown["fallback"] = "quiet_day"
            return previous_lens, breakdown
        breakdown["fallback"] = "quiet_day_alpha"
        return sorted(breakdown.keys() - {"fallback"})[0], breakdown

    return best_slug or "banking", breakdown
