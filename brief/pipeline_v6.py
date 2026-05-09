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
import os
import re
import time
from datetime import date as date_t
from typing import Any

from brief import chart_series_fetcher, pipeline as _pipeline
from brief.claude.max_client import MaxCallError, run_max
from brief.history import HttpClient, UrllibHttp
from brief.schema import SectionData
from brief.v6_publisher import (
    PublishError,
    fetch_max_issue_no,
    fetch_metric_definitions,
    fetch_previous_brief,
    fetch_recent_news,
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
    "fiscal":    ("fiscal",    8, "policy"),
    "macro":     ("macro",     9, "markets"),
    "iranwar":   ("iran",      10, "policy"),
    "remit":     ("remit",     11, "markets"),
    "comm":      ("comm",      12, "markets"),
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
    *,
    previous_brief: dict[str, Any] | None,
    previous_lens: str | None,
    recent_news: list[dict[str, Any]],
    metric_definitions: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    """Build editor input + return chosen lens.

    Returns (editor_input, today_lens). Caller passes today_lens to the
    appropriate prompt template; mostly relevant when caller wants to log it.
    """
    from brief.builders.lens import score_lens
    from brief.builders.dedup import filter_headlines
    from brief.builders.diff import _index_previous_metrics

    next_issue = fetch_max_issue_no() + 1
    raw_sections = _to_v6_raw(sections)

    # Index prev brief metrics by (slug, label) → prev_value_text. Used as the
    # magnitude fallback when V5 metrics carry no Delta object (see
    # _diff_value_to_sigma docstring) and as the held-over signal for the
    # editor (see _compute_is_held_over).
    prev_metrics_idx = _index_previous_metrics(previous_brief)

    # Stamp `is_held_over` on each raw_section metric so the editor sees it.
    # This is what the editor prompt's "do not pick is_held_over for cover_metric"
    # rule reads. Daily/weekly metrics never count as held; only quarterly/monthly
    # metrics with unchanged value text.
    for s in raw_sections:
        for m in s.get("metrics", []) or []:
            m["is_held_over"] = _compute_is_held_over(
                m.get("value"),
                prev_metrics_idx.get((s["slug"], m["label"])),
                m.get("cadence"),
            )

    # Compute today's lens
    sections_for_lens = [
        {
            "slug": s["slug"],
            "freshness_days_since_refresh": _days_since_refresh(s.get("freshness")),
            "metrics": [
                {
                    "label": m["label"],
                    "value": m["value"],
                    "delta_sigma": _delta_sigma(
                        m,
                        metric_definitions,
                        prev_value=prev_metrics_idx.get((s["slug"], m["label"])),
                    ),
                    "is_held_over": m.get("is_held_over", False),
                }
                for m in s.get("metrics", []) or []
            ],
        }
        for s in raw_sections
    ]
    lens, lens_breakdown = score_lens(sections_for_lens, today=today, previous_lens=previous_lens)
    logger.info("v6: lens=%s, score breakdown=%s", lens, lens_breakdown)

    # Filter scraped headlines against last 5 issues
    filtered_headlines, dropped = filter_headlines(scraped_headlines, recent_news)
    if dropped:
        logger.info("v6: filter_headlines dropped %d re-runs", dropped)

    return {
        "today": today.isoformat(),
        "today_lens": lens,
        "previous_brief": previous_brief,
        "scraped_headlines": filtered_headlines,
        "sections_raw": raw_sections,
        "meta": {
            "issue_no": next_issue,
            "volume": (previous_brief or {}).get("brief", {}).get("volume", 1),
            "brief_date": today.isoformat(),
        },
    }, lens


def _days_since_refresh(freshness: str | None) -> int:
    """Map V5's freshness label to a days-since-refresh number for the lens scorer.

    'fresh' → 0 (today), 'warning' → 5, 'stale' → 14, 'unavailable' → 30.
    """
    return {"fresh": 0, "warning": 5, "stale": 14, "unavailable": 30}.get(freshness or "stale", 14)


def _delta_sigma(
    metric: dict[str, Any],
    definitions: list[dict[str, Any]],
    *,
    prev_value: Any = None,
) -> float:
    """Best-effort σ-move estimate.

    Order of preference:
      1. metric.delta.value — V5 builders' explicit Delta object (only bb_reserves
         currently emits this).
      2. metric.delta_pct — future-shape fallback for builders that publish a
         pre-computed pct.
      3. abs(value_text - prev_value_text) / max(|prev|, 0.5), clamped — the
         post-Phase-4 fallback (this is what makes the lens rotate today since
         most V5 metrics don't populate the Delta object).

    Returns 0.0 if none of the above produces a signal.
    """
    delta = metric.get("delta")
    if isinstance(delta, dict):
        value = delta.get("value")
        if isinstance(value, (int, float)):
            return abs(float(value))
    delta_pct = metric.get("delta_pct")
    if delta_pct is not None:
        try:
            if isinstance(delta_pct, (int, float)):
                return abs(float(delta_pct) / 2.0)
            return abs(float(str(delta_pct).strip("%+")) / 2.0)
        except (ValueError, TypeError):
            pass  # fall through to prev-value diff
    if prev_value is not None:
        return _diff_value_to_sigma(metric.get("value"), prev_value)
    return 0.0


_NUMERIC_STRIP = re.compile(r"[^\d.\-]")


def _diff_value_to_sigma(curr: Any, prev: Any) -> float:
    """Numeric-tolerant relative-change magnitude for value text.

    Strips non-numeric chars from string values ("35.73%" → 35.73,
    "$113.95" → 113.95, "৳15,400" → 15400) before diffing. Returns
    `min(abs(a - b) / max(|b|, 0.5), 1.0)` so a 5% relative move scores ~0.05
    and anything past 100% relative move clamps to 1.0.

    Returns 0.0 when either side is unparseable, both sides parse equal, or
    prev is None — i.e. when no comparison is possible the lens scorer sees
    no magnitude signal, same as today's pre-fix behavior.

    Special case: prev numerically zero → return abs(curr) (clamped to 1.0)
    so a metric moving from 0 to non-zero registers as movement, not /0 NaN.
    """
    a = _parse_numeric(curr)
    b = _parse_numeric(prev)
    if a is None or b is None:
        return 0.0
    if abs(b) < 1e-9:
        return min(abs(a), 1.0)
    return min(abs(a - b) / max(abs(b), 0.5), 1.0)


def _parse_numeric(v: Any) -> float | None:
    """Best-effort parse of a numeric or numeric-prefixed string. None on failure."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        stripped = _NUMERIC_STRIP.sub("", v)
        if not stripped or stripped in {".", "-", ".-", "-."}:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


_HELD_OVER_CADENCES = frozenset({"monthly", "quarterly"})


def _compute_is_held_over(curr_value: Any, prev_value: Any, cadence: Any) -> bool:
    """Return True iff the metric should be treated as held-over for the editor.

    A metric is held-over when:
      - Its cadence is monthly or quarterly (annual not used in V5 schema;
        daily/weekly/event metrics should be moving — an unchanged value
        there is a freshness issue, not a held-over case)
      - There IS a previous brief value to compare against (cold start →
        nothing is held)
      - Current and previous values match — compared numerically when both
        parse as numbers (V5 builders emit floats like 35.73; previous brief
        stores editor-formatted strings like "35.73%"), with string equality
        as a fallback for non-numeric values

    Editor reads `is_held_over=True` and skips the metric for cover_metric.
    """
    if prev_value is None:
        return False
    if cadence not in _HELD_OVER_CADENCES:
        return False
    curr_num = _parse_numeric(curr_value)
    prev_num = _parse_numeric(prev_value)
    if curr_num is not None and prev_num is not None:
        return abs(curr_num - prev_num) < 1e-6
    return curr_value == prev_value


def _stamp_freshness(final_brief: BriefPayloadV6, raw_sections: list[dict[str, Any]]) -> None:
    """Mutate `final_brief.sections[i].freshness` in place by slug lookup.

    `raw_sections` is the V6-shape list emitted by `_to_v6_raw` — each dict
    carries `slug` and `freshness` (the V5-derived label). The editor doesn't
    set freshness on its output; we propagate the deterministic V5 signal here,
    post-LLM, so the SPA can collapse dead sections (Phase D.2).

    Only sets when raw provides a non-None freshness value — preserves any
    existing value when raw omits the key or carries None. Sections present
    in `final_brief` but not in `raw_sections` are also left untouched.
    """
    freshness_by_slug: dict[str, Any] = {
        s["slug"]: s.get("freshness") for s in raw_sections if "slug" in s
    }
    for section in final_brief.sections:
        fresh = freshness_by_slug.get(section.slug)
        if fresh is not None:
            section.freshness = fresh


# ─── Phase E.2 — chart series enricher ────────────────────────────────
# Per-slug chart fetcher dispatch. Sections not in this map skip chart_series
# stamping (frontend hides the chart slot when series is empty). The values
# correspond to function names on the `chart_series_fetcher` module — we look
# them up dynamically so test monkeypatching just works.
_CHART_FETCHERS_BY_SLUG: dict[str, str] = {
    "fx": "fx_flows",
    "dse": "dsex",
    "iran": "brent",
    "tbond": "yield_curve",
}


def _stamp_chart_series(
    final_brief: BriefPayloadV6,
    *,
    today: date_t,
    http: HttpClient,
    supabase_url: str,
    service_key: str,
) -> None:
    """Fetch time-series from Supabase for chartable sections; stamp in place.

    Iterates final_brief.sections; for each slug present in
    `_CHART_FETCHERS_BY_SLUG`, dispatches the matching `chart_series_fetcher.*`
    function and assigns the result to `section.series` (and `section.notes`
    for the dse fetcher which returns both).

    Failures on individual fetchers log a warning and leave that section's
    series empty — graceful degradation, one bad scrape does not break the
    whole publish.
    """
    for section in final_brief.sections:
        fn_suffix: str | None = _CHART_FETCHERS_BY_SLUG.get(section.slug)
        if fn_suffix is None:
            continue
        fn_name: str = f"fetch_{fn_suffix}"
        try:
            fn = getattr(chart_series_fetcher, fn_name)
            if fn_suffix == "dsex":
                series, notes = fn(
                    http=http,
                    supabase_url=supabase_url,
                    service_key=service_key,
                    today=today,
                )
                section.series = series
                section.notes = notes
            else:
                series = fn(
                    http=http,
                    supabase_url=supabase_url,
                    service_key=service_key,
                    today=today,
                )
                section.series = series
        except Exception:  # noqa: BLE001 — graceful degradation per spec
            logger.warning(
                "v6: chart series fetcher failed for slug=%s (fn=%s)",
                section.slug,
                fn_name,
                exc_info=True,
            )


def _resolve_supabase_config() -> tuple[str, str] | None:
    """Read SUPABASE_URL + service key from env. Returns None when missing
    so the chart enricher can skip gracefully (degraded charts != fatal).
    """
    url: str | None = os.environ.get("SUPABASE_URL")
    key: str | None = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
    )
    if not url or not key:
        return None
    return url, key


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
    """Execute the 2-call publish flow with fresh-brief V1 wiring.

    Pipeline shape:
      1. Compute today_lens (data-driven Mon–Thu, weekly_wrap on Friday)
      2. Filter scraped_headlines against last 5 issues
      3. Editor LLM produces brief
      4. Subeditor LLM reviews
      5. stamp_changed (post-LLM diff)
      6. mark_held_overs (post-LLM honesty)
      7. Publish to Supabase
    """
    from brief.builders.diff import stamp_changed, mark_held_overs

    previous = fetch_previous_brief()
    previous_lens = (previous or {}).get("brief", {}).get("lens")
    recent_news = fetch_recent_news(n_issues=5)
    metric_definitions = fetch_metric_definitions()
    if not metric_definitions:
        logger.warning(
            "v6: metric_definitions empty — held-over annotation will no-op. "
            "Check catalog table + RLS."
        )

    editor_input, today_lens = _build_editor_input(
        sections,
        today,
        scraped_headlines or [],
        previous_brief=previous,
        previous_lens=previous_lens,
        recent_news=recent_news,
        metric_definitions=metric_definitions,
    )

    issue_no = editor_input["meta"]["issue_no"]
    logger.info(
        "v6: issue_no=%d, %d sections raw, lens=%s",
        issue_no, len(editor_input["sections_raw"]), today_lens,
    )

    # ── Friday branch ──────────────────────────────────────────────
    is_friday = today.weekday() == 4
    if is_friday:
        from brief.builders.weekly import build_weekly_input
        editor_input = build_weekly_input(editor_input, today=today)
        editor_prompt_file = "editor_v6_friday.txt"
        logger.info("v6: Friday wrap — using editor_v6_friday.txt + weekly_diffs block")
    else:
        editor_prompt_file = "editor_v6.txt"

    # ── Call 1: Editor ─────────────────────────────────────────────
    editor_prompt = _pipeline._load_prompt(editor_prompt_file).replace("{today}", today.isoformat())
    editor_raw = _call_with_retries(
        label="editor_v6", prompt_template=editor_prompt, input_obj=editor_input, timeout_s=1800,
    )
    try:
        editor_brief = BriefPayloadV6.model_validate(editor_raw)
    except Exception as e:
        raise V6PublishError(f"editor_v6 output failed schema validation: {e}") from e

    # Force lens onto the brief — the LLM should set it but we guarantee it
    editor_brief.brief.lens = today_lens

    logger.info(
        "v6: editor produced brief with %d sections, hero=%s, frame=%s",
        len(editor_brief.sections),
        next((s.slug for s in editor_brief.sections if s.weight == 2), None),
        editor_brief.brief.frame,
    )

    # ── Call 2: Sub-editor ─────────────────────────────────────────
    subeditor_prompt = _pipeline._load_prompt("subeditor_v6.txt")
    subeditor_input = {"editor_output": editor_brief.model_dump(mode="json"), "raw_data": editor_input}
    review_raw = _call_with_retries(
        label="subeditor_v6", prompt_template=subeditor_prompt, input_obj=subeditor_input, timeout_s=1800,
    )
    try:
        review = SubeditorReview.model_validate(review_raw)
    except Exception as e:
        logger.warning("v6: subeditor output failed schema validation, passing editor output: %s", e)
        review = SubeditorReview(verdict="pass")

    if review.verdict == "fail":
        msgs = [f"  · [{i.severity}] {i.section}.{i.field}: {i.problem}" for i in review.issues]
        raise V6PublishError(f"subeditor verdict=fail with {len(review.issues)} issues:\n" + "\n".join(msgs))

    if review.verdict == "revise" and review.revised_brief is not None:
        final_brief = review.revised_brief
        # Re-force lens on revised brief
        final_brief.brief.lens = today_lens
        logger.info("v6: subeditor revised brief, %d issues fixed", len(review.issues))
    else:
        final_brief = editor_brief
        if review.issues:
            logger.info("v6: subeditor passed with %d warnings", len(review.issues))
        else:
            logger.info("v6: subeditor passed clean")

    # ── Post-LLM: deterministic diff + held-over stamping ──────────
    stamp_changed(final_brief, previous)
    mark_held_overs(final_brief, previous, metric_definitions)
    _stamp_freshness(final_brief, editor_input["sections_raw"])

    # Phase E.2 — chart series enricher. Skip silently when supabase env is
    # missing (e.g. dry-run from a workstation without secrets). Charts are
    # render-layer data; degraded charts must not block a publish.
    supabase_cfg: tuple[str, str] | None = _resolve_supabase_config()
    if supabase_cfg is None:
        logger.warning(
            "v6: skipping chart series stamp — SUPABASE_URL or service key missing in env"
        )
    else:
        supabase_url, service_key = supabase_cfg
        _stamp_chart_series(
            final_brief,
            today=today,
            http=UrllibHttp(),
            supabase_url=supabase_url,
            service_key=service_key,
        )

    logger.info(
        "v6: stamp_changed + mark_held_overs + stamp_freshness + stamp_chart_series done; "
        "changed_news=%d, held_metrics=%d, unavailable_sections=%d, chart_sections=%d",
        sum(1 for s in final_brief.sections for n in s.news if n.changed),
        sum(1 for s in final_brief.sections for m in s.metrics if m.held_from),
        sum(1 for s in final_brief.sections if s.freshness == "unavailable"),
        sum(1 for s in final_brief.sections if s.series),
    )

    # If every metric in the hero (weight=2) section is unchanged from the
    # previous brief, the editor was forced to feature a stuck metric as
    # cover_metric. Strip it — the SPA hides the big-number block when
    # cover_metric is None, and the brief opens cleanly with the masthead +
    # headlines column. Cold start (previous=None) → stamp_changed marks
    # everything changed=True → this branch never fires.
    hero_section = next((s for s in final_brief.sections if s.weight == 2), None)
    if (
        hero_section is not None
        and hero_section.metrics
        and all(m.changed is False for m in hero_section.metrics)
    ):
        final_brief.brief.cover_metric = None
        logger.info(
            "v6: stripped cover_metric — every hero (%s) metric is unchanged from previous brief",
            hero_section.slug,
        )

    if dry_run:
        logger.info("v6: dry_run=True, skipping Supabase publish")
        return None

    try:
        return publish_brief(final_brief)
    except PublishError as e:
        raise V6PublishError(f"Supabase publish failed: {e}") from e
