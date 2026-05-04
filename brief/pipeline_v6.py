"""V6 publish pipeline — 2 Opus calls, atomic Supabase write.

Flow:
  1. Reuse pipeline.gather() to build raw section data (deterministic, no Claude)
  2. Adapt V5 SectionData → V6 raw input (slug rename, ord assignment, group_key)
  3. Call 1: editor_v6 — produces full BriefPayloadV6 JSON
  4. Validate against Pydantic schema
  5. Call 2: subeditor_v6 — reads brief + raw, returns pass/revise/fail
  6. Resolve final brief
  7. Atomic publish via v6_publisher
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date as date_t
from typing import Any

from brief import pipeline as _pipeline
from brief.claude.max_client import MaxCallError, run_max
from brief.schema import SectionData
from brief.v6_publisher import (
    PublishError,
    fetch_max_issue_no,
    fetch_previous_brief,
    publish_brief,
)
from brief.v6_schema import BriefPayloadV6, SubeditorReview

logger = logging.getLogger(__name__)

# V5 section.id → V6 slug, ord, group_key. Sections not in this map are dropped.
V5_TO_V6: dict[str, tuple[str, int, str]] = {
    "headlines": ("headlines", 2, "overview"),
    "bb":        ("bb",        3, "banking"),
    "banking":   ("banking",   4, "banking"),
    "fx":        ("fx",        5, "markets"),
    "dse":       ("dse",       6, "markets"),
    "tbond":     ("tbond",     7, "markets"),
    "macro":     ("macro",     9, "markets"),
    "iranwar":   ("iran",      10, "policy"),
}


class V6PublishError(RuntimeError):
    """Raised when the publish flow fails (Claude error, validation error, write error)."""


def _to_v6_raw(sections: list[SectionData]) -> list[dict[str, Any]]:
    """Convert V5 SectionData → JSON shape the editor prompt expects.

    V5 doesn't carry verdict/verdict_tone fields directly; the editor derives
    them from the section's kicker/tldr/bankerread.pull text and metric tones.
    """
    out: list[dict[str, Any]] = []
    for s in sections:
        if s.id not in V5_TO_V6:
            continue
        slug, ord_v6, group = V5_TO_V6[s.id]
        out.append(
            {
                "slug": slug,
                "ord": ord_v6,
                "title": s.title,
                "group_key": group,
                "freshness": s.freshness,
                "freshness_reason": s.freshness_reason,
                "kicker": s.kicker,
                "tldr": s.tldr,
                "pull": s.pull,
                "metrics": [m.model_dump(mode="json") for m in s.metrics],
                "news": [n.model_dump(mode="json") for n in s.news],
            }
        )
    out.sort(key=lambda x: x["ord"])
    return out


def _build_editor_input(
    sections: list[SectionData],
    today: date_t,
    scraped_headlines: list[dict[str, Any]],
) -> dict[str, Any]:
    previous = fetch_previous_brief()
    next_issue = fetch_max_issue_no() + 1
    return {
        "today": today.isoformat(),
        "previous_brief": previous,
        "scraped_headlines": scraped_headlines,
        "sections_raw": _to_v6_raw(sections),
        "meta": {
            "issue_no": next_issue,
            "volume": (previous or {}).get("brief", {}).get("volume", 1),
            "brief_date": today.isoformat(),
        },
    }


def _call_with_retries(
    *,
    label: str,
    prompt_template: str,
    input_obj: dict[str, Any],
    timeout_s: int = 1800,
    attempts: int = 3,
) -> dict[str, Any]:
    """Run Claude max with exponential backoff. Returns parsed JSON or raises."""
    body = prompt_template + "\n\nINPUT JSON:\n" + json.dumps(input_obj, default=str, indent=2)
    delays = [5, 15, 45]
    last_err: Exception | None = None

    for i in range(attempts):
        try:
            result = run_max(prompt=body, timeout_s=timeout_s)
            if result.parsed is None:
                raise V6PublishError(f"{label}: result.parsed is None (raw: {result.raw_text[:200]!r})")
            return result.parsed  # type: ignore[no-any-return]
        except (MaxCallError, V6PublishError) as e:
            last_err = e
            logger.warning("%s attempt %d/%d failed: %s", label, i + 1, attempts, e)
            if i < attempts - 1:
                time.sleep(delays[i])
    raise V6PublishError(f"{label}: failed after {attempts} attempts: {last_err}")


def run_publish(
    sections: list[SectionData],
    today: date_t,
    *,
    scraped_headlines: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> str | None:
    """Execute the 2-call publish flow. Returns published brief id, or None on dry-run.

    Raises V6PublishError on subeditor verdict='fail' or any Claude/Supabase error.
    """
    editor_input = _build_editor_input(
        sections, today, scraped_headlines or []
    )
    issue_no = editor_input["meta"]["issue_no"]
    logger.info("v6: issue_no=%d, %d sections raw", issue_no, len(editor_input["sections_raw"]))

    # ── Call 1: Editor ─────────────────────────────────────────────
    editor_prompt = _pipeline._load_prompt("editor_v6.txt").replace("{today}", today.isoformat())
    editor_raw = _call_with_retries(
        label="editor_v6",
        prompt_template=editor_prompt,
        input_obj=editor_input,
        timeout_s=1800,
    )
    try:
        editor_brief = BriefPayloadV6.model_validate(editor_raw)
    except Exception as e:
        raise V6PublishError(f"editor_v6 output failed schema validation: {e}") from e
    logger.info(
        "v6: editor produced brief with %d sections, hero=%s",
        len(editor_brief.sections),
        next((s.slug for s in editor_brief.sections if s.weight == 2), None),
    )

    # ── Call 2: Sub-editor ─────────────────────────────────────────
    subeditor_prompt = _pipeline._load_prompt("subeditor_v6.txt")
    subeditor_input = {
        "editor_output": editor_brief.model_dump(mode="json"),
        "raw_data": editor_input,
    }
    review_raw = _call_with_retries(
        label="subeditor_v6",
        prompt_template=subeditor_prompt,
        input_obj=subeditor_input,
        timeout_s=1800,
    )
    try:
        review = SubeditorReview.model_validate(review_raw)
    except Exception as e:
        # Sub-editor failure is non-fatal — fall back to editor output unrevised
        logger.warning("v6: subeditor output failed schema validation, passing editor output: %s", e)
        review = SubeditorReview(verdict="pass")

    # ── Resolve verdict ────────────────────────────────────────────
    if review.verdict == "fail":
        msgs = [f"  · [{i.severity}] {i.section}.{i.field}: {i.problem}" for i in review.issues]
        raise V6PublishError(
            f"subeditor verdict=fail with {len(review.issues)} issues:\n" + "\n".join(msgs)
        )

    if review.verdict == "revise" and review.revised_brief is not None:
        final_brief = review.revised_brief
        logger.info("v6: subeditor revised brief, %d issues fixed", len(review.issues))
    else:
        final_brief = editor_brief
        if review.issues:
            logger.info(
                "v6: subeditor passed with %d warnings: %s",
                len(review.issues),
                [i.problem for i in review.issues],
            )
        else:
            logger.info("v6: subeditor passed clean")

    if dry_run:
        logger.info("v6: dry_run=True, skipping Supabase publish")
        return None

    try:
        return publish_brief(final_brief)
    except PublishError as e:
        raise V6PublishError(f"Supabase publish failed: {e}") from e
