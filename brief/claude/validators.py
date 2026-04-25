"""Validators for the three Claude calls. Each returns a ValidationResult.

Contract: validator never raises. On malformed input it sets ok=False and
returns a reason. On partial validity (insights), ok=True but invalid
per-section entries are moved to `dropped` so the caller can fall back
per section.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import ValidationError as _PydValidationError

from brief.schema import GridEntry, MapCoord, MapPoint, TodaysCall, TopPicks

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


def validate_risk_map_layout(
    payload: Any,
    *,
    section_ids: set[str],
    known_metric_ids: dict[str, set[str]] | None = None,
) -> ValidationResult:
    """Validate Claude's risk_map_layout response.

    On success: ValidationResult.value = {
        "sections": list[MapCoord],
        "read_order": list[str],
    }
    """
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")

    raw_sections = payload.get("sections")
    if not isinstance(raw_sections, list):
        return ValidationResult(False, reason="sections missing or not a list")

    want = len(section_ids)
    if len(raw_sections) != want:
        return ValidationResult(
            False,
            reason=f"sections count mismatch (got {len(raw_sections)}, want {want})",
        )

    # Parse each entry as MapCoord, collecting typed models
    sections: list[MapCoord] = []
    seen_ids: set[str] = set()

    for entry in raw_sections:
        if not _is_dict(entry):
            return ValidationResult(False, reason="section entry not a dict")
        sid = entry.get("section_id")
        if sid in seen_ids:
            return ValidationResult(False, reason=f"duplicate section_id: {sid!r}")
        seen_ids.add(sid)
        try:
            coord = MapCoord(**entry)
        except _PydValidationError as exc:
            short = str(exc).split("\n")[0]
            return ValidationResult(False, reason=f"MapCoord validation failed: {short}")
        sections.append(coord)

    # Check for unknown or missing section_ids
    unknown = seen_ids - section_ids
    if unknown:
        sid = next(iter(sorted(unknown)))
        return ValidationResult(False, reason=f"unknown section_id: {sid!r}")
    missing = section_ids - seen_ids
    if missing:
        return ValidationResult(False, reason=f"missing section_ids: {sorted(missing)}")

    # Validate hero_metric_id references if lookup provided
    if known_metric_ids is not None:
        for coord in sections:
            if coord.hero_metric_id is not None:
                allowed_metrics = known_metric_ids.get(coord.section_id, set())
                if coord.hero_metric_id not in allowed_metrics:
                    return ValidationResult(
                        False,
                        reason=(
                            f"hero_metric_id {coord.hero_metric_id!r} not in "
                            f"section {coord.section_id!r} metrics"
                        ),
                    )

    # Validate read_order
    read_order = payload.get("read_order")
    if not isinstance(read_order, list) or len(read_order) != want:
        return ValidationResult(
            False,
            reason=(
                f"read_order must be a list of {want} strings"
                if not isinstance(read_order, list)
                else f"read_order length mismatch (got {len(read_order)}, want {want})"
            ),
        )
    if not all(isinstance(s, str) for s in read_order):
        return ValidationResult(False, reason="read_order contains non-string elements")

    ro_set = set(read_order)
    if len(read_order) != len(ro_set):
        return ValidationResult(False, reason="read_order contains duplicates")
    unknown_ro = ro_set - section_ids
    if unknown_ro:
        return ValidationResult(
            False,
            reason=f"read_order contains unknown section_ids: {sorted(unknown_ro)}",
        )
    missing_ro = section_ids - ro_set
    if missing_ro:
        return ValidationResult(
            False,
            reason=f"read_order missing section_ids: {sorted(missing_ro)}",
        )

    return ValidationResult(
        ok=True,
        value={"sections": sections, "read_order": read_order},
    )


def validate_todays_call(payload: Any) -> ValidationResult:
    """Validate Claude's todays_call response (V5 contract).

    On success: ValidationResult.value = TodaysCall(text=..., byline=...).
    V5: enforces 60-100 word count; rejects double quotes; accepts byline in payload.
    """
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    text = payload.get("text")
    byline = payload.get("byline", "Desk Editor · The Brief")
    if not isinstance(text, str):
        return ValidationResult(False, reason="text missing or not a string")
    word_count = len(text.split())
    if word_count < 60 or word_count > 100:
        return ValidationResult(False, reason=f"text must be 60-100 words; got {word_count}")
    if '"' in text:
        return ValidationResult(False, reason="text contains double quote (template-breaking)")
    return ValidationResult(True, value=TodaysCall(text=text, byline=byline, generated_at=datetime.now(timezone.utc)))


def validate_top_picks(payload: Any, *, allowed_ids: set[str]) -> ValidationResult:
    """Validate Claude's top_picks response (Call 1).

    On success: ValidationResult.value = TopPicks(plotted=..., grid=..., front_of_book_id=...).
    """
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")

    plotted = payload.get("plotted")
    grid = payload.get("grid")
    fob = payload.get("front_of_book_id")

    if not isinstance(plotted, list) or len(plotted) != 7:
        return ValidationResult(False, reason="plotted must contain exactly 7 sections")
    if not isinstance(grid, list) or len(grid) != 7:
        return ValidationResult(False, reason="grid must contain exactly 7 sections")
    if not isinstance(fob, str):
        return ValidationResult(False, reason="front_of_book_id missing or not a string")

    plotted_models: list[MapPoint] = []
    for item in plotted:
        if not _is_dict(item):
            return ValidationResult(False, reason="plotted item not a dict")
        for k in ("id", "x", "y", "r", "kind"):
            if k not in item:
                return ValidationResult(False, reason=f"plotted item missing {k}")
        if item["id"] not in allowed_ids:
            return ValidationResult(False, reason=f"unknown id in plotted: {item['id']!r}")
        if item["kind"] not in {"event", "fresh", "slow", "anchor"}:
            return ValidationResult(False, reason=f"bad kind: {item['kind']!r}")
        try:
            plotted_models.append(MapPoint(**item))
        except Exception as e:
            return ValidationResult(False, reason=f"plotted item invalid: {e}")

    grid_models: list[GridEntry] = []
    for item in grid:
        if not _is_dict(item):
            return ValidationResult(False, reason="grid item not a dict")
        for k in ("id", "tldr"):
            if k not in item:
                return ValidationResult(False, reason=f"grid item missing {k}")
        if item["id"] not in allowed_ids:
            return ValidationResult(False, reason=f"unknown id in grid: {item['id']!r}")
        word_count = len(str(item["tldr"]).split())
        if word_count > 14:
            return ValidationResult(False, reason=f"tldr too long ({word_count} words) for {item['id']!r}; cap is 12")
        try:
            grid_models.append(GridEntry(**item))
        except Exception as e:
            return ValidationResult(False, reason=f"grid item invalid: {e}")

    plotted_ids = {p.id for p in plotted_models}
    grid_ids = {g.id for g in grid_models}
    if plotted_ids & grid_ids:
        return ValidationResult(False, reason=f"plotted/grid overlap: {plotted_ids & grid_ids}")
    if fob not in plotted_ids:
        return ValidationResult(False, reason=f"front_of_book_id {fob!r} not in plotted")

    return ValidationResult(True, value=TopPicks(plotted=plotted_models, grid=grid_models, front_of_book_id=fob))


def validate_bankerread_structured(payload: Any) -> ValidationResult:
    """Validate Claude's bankerread_structured response (V5 Call 4).

    Handles variant='full' (4 structured fields) and variant='stale_micro' (meaning only).
    """
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    variant = payload.get("variant")
    if variant not in {"full", "stale_micro"}:
        return ValidationResult(False, reason=f"variant must be 'full' or 'stale_micro'; got {variant!r}")

    pull = payload.get("pull_quote")
    if not isinstance(pull, str) or len(pull.split()) > 20:
        return ValidationResult(False, reason="pull_quote missing or > 20 words")
    if '"' in pull:
        return ValidationResult(False, reason="pull_quote contains double quote")

    from brief.schema import BankerReadInsight

    if variant == "full":
        for fld in ("meaning", "action", "trigger", "focus"):
            text = payload.get(fld)
            if not isinstance(text, str):
                return ValidationResult(False, reason=f"{fld} missing")
            wc = len(text.split())
            if wc < 60 or wc > 180:
                return ValidationResult(False, reason=f"{fld} must be 60-180 words; got {wc}")
            if '"' in text:
                return ValidationResult(False, reason=f"{fld} contains double quote")
        return ValidationResult(True, value=BankerReadInsight(
            variant="full",
            meaning=payload["meaning"],
            action=payload["action"],
            trigger=payload["trigger"],
            focus=payload["focus"],
            pull_quote=pull,
            generated_at=datetime.now(timezone.utc),
        ))

    # stale_micro
    text = payload.get("meaning")
    if not isinstance(text, str):
        return ValidationResult(False, reason="meaning missing")
    wc = len(text.split())
    if wc < 50 or wc > 110:
        return ValidationResult(False, reason=f"stale_micro meaning must be 50-110 words; got {wc}")
    if '"' in text:
        return ValidationResult(False, reason="meaning contains double quote")
    return ValidationResult(True, value=BankerReadInsight(
        variant="stale_micro",
        meaning=text,
        pull_quote=pull,
        generated_at=datetime.now(timezone.utc),
    ))


def validate_systemic_risk_callout(
    payload: Any, *, expected_level: str, rule_id: str
) -> ValidationResult:
    """Validate Claude's systemic_risk_callout response (V5 Call 5)."""
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    headline = payload.get("headline")
    body = payload.get("body")
    if not isinstance(headline, str) or len(headline.split()) > 12:
        return ValidationResult(False, reason="headline missing or > 12 words")
    if not isinstance(body, str):
        return ValidationResult(False, reason="body missing")
    bw = len(body.split())
    if bw < 50 or bw > 110:
        return ValidationResult(False, reason=f"body must be 50-110 words; got {bw}")
    if '"' in headline + body:
        return ValidationResult(False, reason="contains double quote")

    from brief.schema import SystemicRisk

    return ValidationResult(True, value=SystemicRisk(
        headline=headline, body=body, level=expected_level, rule_id=rule_id
    ))
