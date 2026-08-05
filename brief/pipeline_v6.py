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
from pathlib import Path
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
from brief.vintage import stamp_vintages, vintage_payload
from brief.claude import validators as _validators

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
    # "comm" removed in v1.6.7 — see brief/builders/__init__.py. Ord 12 is left
    # unused rather than renumbered: ord only has to sort, and reusing a retired
    # slot would silently re-home a future section into Commodities' place.
}


class V6PublishError(RuntimeError):
    """Raised when the publish flow fails (Claude error, validation error, write error)."""


def _to_v6_raw(
    sections: list[SectionData], *, today: date_t | None = None
) -> list[dict[str, Any]]:
    """Convert V5 SectionData → JSON shape the editor prompt expects.

    V5 doesn't carry verdict/verdict_tone fields directly; the editor derives
    them from the section's kicker/tldr/bankerread.pull text and metric tones.

    v1.4.0: also serialises SectionData.history_facts so the editor can weave
    pre-formatted historical anchor phrases verbatim into prose (spec §3.2).

    v1.6.4: stamps `vintage` on every metric that is past its cadence's fresh
    threshold. `as_of` already reached the editor inside the metric dump, but a
    bare date carries no threshold, so the editor had no way to know 2026-03-01
    was five months stale — which is how #184 paired a March REER with that
    day's spot rate in one clause. The section-level `freshness` flag did not
    help there: it is worst-of, so it says a section contains something old
    without saying WHICH metric, and it says nothing at all when the stale
    number is borrowed into a different section's prose.
    """
    out: list[dict[str, Any]] = []
    for s in sections:
        if s.id not in V5_TO_V6:
            continue
        slug, ord_v6, group = V5_TO_V6[s.id]
        metrics_raw: list[dict[str, Any]] = []
        for m in s.metrics:
            dumped = m.model_dump(mode="json")
            # None on a fresh metric — an "as of today" on today's number is
            # noise, and noise is how a real staleness signal gets ignored.
            dumped["vintage"] = vintage_payload(m, today=today)
            metrics_raw.append(dumped)
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
                "metrics": metrics_raw,
                "news": [n.model_dump(mode="json") for n in s.news],
                "history_facts": [
                    {
                        "metric_id": f.metric_id,
                        "kind": f.kind,
                        "phrase": f.phrase,
                        "reference_value_formatted": f.reference_value_formatted,
                        "reference_as_of": f.reference_as_of,
                    }
                    for f in (s.history_facts or [])
                ],
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
    raw_sections = _to_v6_raw(sections, today=today)

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
    "dse": "dsex",
    "iran": "brent",
    # fx moved to the metric_history_monthly External Flow Balance branch (F3);
    # fetch_fx_flows is retained (unit-tested) but no longer slug-dispatched.
    # tbond moved to the metric_history_monthly yield-ladder branch (F5);
    # fetch_yield_curve is retained (unit-tested) but no longer slug-dispatched.
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

    v1.4.0: the macro section's CPI trend chart is fetched via
    `fetch_macro_cpi_series` which uses `MetricHistoryClient` (not the direct
    HTTP helpers used by the other fetchers) to read `metric_history_monthly`.

    Failures on individual fetchers log a warning and leave that section's
    series empty — graceful degradation, one bad scrape does not break the
    whole publish.
    """
    from brief.history import MetricHistoryClient as _MetricHistoryClient
    history_monthly_client = _MetricHistoryClient(
        url=supabase_url, service_key=service_key, http=http,
    )

    for section in final_brief.sections:
        # v1.4.0 — macro CPI trend chart uses metric_history_monthly
        if section.slug == "macro":
            try:
                series_by_id = chart_series_fetcher.fetch_macro_cpi_series(history_monthly_client)
                flat_series = [pt for pts in series_by_id.values() for pt in pts]
                section.series = flat_series
            except Exception:  # noqa: BLE001 — graceful degradation
                logger.warning(
                    "v6: macro CPI series fetch failed for slug=macro",
                    exc_info=True,
                )
            continue

        # F6 — §08 remittance 12-month chart also reads metric_history_monthly
        if section.slug == "remit":
            try:
                series_by_id = chart_series_fetcher.fetch_remit_monthly(history_monthly_client)
                section.series = [pt for pts in series_by_id.values() for pt in pts]
            except Exception:  # noqa: BLE001 — graceful degradation
                logger.warning(
                    "v6: remit series fetch failed for slug=remit",
                    exc_info=True,
                )
            continue

        # F2 — §02 Policy & Rates reserves two-line (metric_history_monthly)
        if section.slug == "bb":
            try:
                series_by_id = chart_series_fetcher.fetch_reserves_monthly(history_monthly_client)
                section.series = [pt for pts in series_by_id.values() for pt in pts]
            except Exception:  # noqa: BLE001 — graceful degradation
                logger.warning(
                    "v6: reserves series fetch failed for slug=bb",
                    exc_info=True,
                )
            continue

        # F5 — §tbond full yield ladder, last 2 months (metric_history_monthly).
        # Replaces the daily fetch_yield_curve path (tbond removed from the
        # _CHART_FETCHERS_BY_SLUG HTTP map below).
        if section.slug == "tbond":
            try:
                series_by_id = chart_series_fetcher.fetch_yield_ladder_monthly(history_monthly_client)
                section.series = [pt for pts in series_by_id.values() for pt in pts]
            except Exception:  # noqa: BLE001 — graceful degradation
                logger.warning(
                    "v6: yield-ladder series fetch failed for slug=tbond",
                    exc_info=True,
                )
            continue

        # F3 — §fx External Flow Balance, last 24 months (metric_history_monthly).
        # Replaces the daily fetch_fx_flows path (fx removed from the HTTP map below).
        if section.slug == "fx":
            try:
                series_by_id = chart_series_fetcher.fetch_fx_balance_monthly(history_monthly_client)
                section.series = [pt for pts in series_by_id.values() for pt in pts]
            except Exception:  # noqa: BLE001 — graceful degradation
                logger.warning(
                    "v6: fx-balance series fetch failed for slug=fx",
                    exc_info=True,
                )
            continue

        # F7b — §fiscal NBR monthly tax-revenue line (metric_history_monthly).
        if section.slug == "fiscal":
            try:
                series_by_id = chart_series_fetcher.fetch_fiscal_monthly(history_monthly_client)
                section.series = [pt for pts in series_by_id.values() for pt in pts]
            except Exception:  # noqa: BLE001 — graceful degradation
                logger.warning(
                    "v6: fiscal series fetch failed for slug=fiscal",
                    exc_info=True,
                )
            continue

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
                # F4 — DS30 movers (separate structured field; None when the
                # freshness gate hides it or data is unavailable).
                try:
                    section.movers = chart_series_fetcher.fetch_dse_movers(
                        http=http,
                        supabase_url=supabase_url,
                        service_key=service_key,
                        today=today,
                    )
                except Exception:  # noqa: BLE001 — graceful degradation
                    logger.warning(
                        "v6: dse-movers fetch failed for slug=dse", exc_info=True
                    )
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


# Raw text of the most recent LLM response per label, kept ONLY so a downstream
# schema failure can dump the evidence to disk (issue 181, 2026-07-31: three
# publishes died on "schema validation failed" and the raw output was discarded
# every time, so four runs produced zero diagnostic signal). Deliberately a
# module-level stash rather than a change to _call_with_retries' return type —
# six tests patch that function and rely on it returning the parsed dict.
_LAST_RAW: dict[str, str] = {}


def _dump_raw_on_failure(label: str) -> str | None:
    """Write the last raw response for *label* to logs/. Returns the path, or
    None when there is nothing stashed (e.g. under a patched _call_with_retries)
    or the write itself fails — diagnostics must never mask the real error."""
    raw = _LAST_RAW.get(label)
    if not raw:
        return None
    try:
        log_dir = Path(__file__).resolve().parents[1] / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        path = log_dir / f"{label}_raw_{stamp}.txt"
        path.write_text(raw)
        return str(path)
    except Exception:  # noqa: BLE001 — never let the dumper eclipse the failure
        logger.exception("%s: could not write raw-output dump", label)
        return None


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
    # Longer exponential-ish backoff so a transient Anthropic "529 Overloaded" spell at the
    # 04:00–06:00 BDT publish window (AGENTS.md landmine #13) gets ridden out instead of
    # burning all attempts in <1 min. Caps at the last value if attempts exceeds the list.
    delays = [15, 45, 120, 300]
    last_err: Exception | None = None

    for i in range(attempts):
        try:
            result = run_max(prompt=body, timeout_s=timeout_s)
            _LAST_RAW[label] = result.raw_text or ""
            if result.assistant_messages > 1:
                # Recovered, not lost: run_max stitched the continuation messages
                # back together. Still worth saying loudly — it means the payload
                # is at the model's hard per-response ceiling (issue 183).
                # `num_turns` is NOT this signal: a cut-off-and-continued
                # response is still one turn, which is why the issue-181 warning
                # here never fired.
                logger.warning(
                    "%s: response was CUT OFF and continued across %d assistant "
                    "messages — stitched into %d chars (output_tokens=%s). The "
                    "payload is at the per-response ceiling.",
                    label, result.assistant_messages, len(result.raw_text or ""),
                    result.tokens.get("output"),
                )
            if result.parsed is None:
                raise V6PublishError(f"{label}: result.parsed is None (raw: {result.raw_text[:200]!r})")
            return result.parsed  # type: ignore[no-any-return]
        except (MaxCallError, V6PublishError) as e:
            last_err = e
            logger.warning("%s attempt %d/%d failed: %s", label, i + 1, attempts, e)
            if i < attempts - 1:
                time.sleep(delays[min(i, len(delays) - 1)])
    raise V6PublishError(f"{label}: failed after {attempts} attempts: {last_err}")


def _run_subeditor(
    subeditor_prompt: str, subeditor_input: dict[str, Any]
) -> SubeditorReview:
    """Run the sub-editor self-review and parse its verdict, retrying ONCE on a
    malformed SubeditorReview, then HOLDING — never auto-passing.

    Two retry layers, different failure modes:
      - `_call_with_retries` (attempts=5) rides out transient Anthropic failures
        (529 "Overloaded" spells at the 04:00-06:00 BDT window; AGENTS.md #13, #120).
        2026-06-22 (issue 144): the sub-editor lost a whole edition to a 529 spell
        that 3 quick retries couldn't outlast — hence 5 x 600s + the longer backoff,
        which still fits under brief.service's 90-min TimeoutStartSec after the
        editor's ~9-min draft.
      - THIS loop re-runs the whole sub-editor when it returns well-formed JSON that
        is NOT a valid SubeditorReview. Previously such output silently became
        `verdict="pass"` and shipped an UNREVIEWED brief. Now: one retry, then a
        hold (raise) so yesterday's brief stays live rather than an unreviewed one
        going out. (2026-07-09 review, item 7 — never auto-pass.)
    """
    last_err: Exception | None = None
    for attempt in range(2):  # initial attempt + exactly one retry
        review_raw = _call_with_retries(
            label="subeditor_v6",
            prompt_template=subeditor_prompt,
            input_obj=subeditor_input,
            timeout_s=600,
            attempts=5,
        )
        try:
            return SubeditorReview.model_validate(review_raw)
        except Exception as e:  # noqa: BLE001 — any parse/validation failure retries then holds
            last_err = e
            logger.warning(
                "v6: sub-editor returned a malformed SubeditorReview "
                "(attempt %d/2): %s",
                attempt + 1,
                e,
            )
    dump = _dump_raw_on_failure("subeditor_v6")
    raise V6PublishError(
        "sub-editor returned a malformed review twice — holding the publish "
        "(never auto-pass an unreviewed brief; yesterday's brief stays live). "
        f"Raw output saved to {dump or 'nowhere — nothing stashed'}. "
        f"Last error: {last_err}"
    )


def _run_deterministic_gate(final_brief: BriefPayloadV6) -> int:
    """Deterministic post-editor prose backstop (issue 156 review, item 7).

    `brief/claude/validators.py` holds hard, testable versions of the checks the
    sub-editor polices non-deterministically (slop blocklist, chart_read caps +
    temporal anchor, Tier-2 first-use expansion). Those validators were imported
    by NOTHING in the publish path. This wires them over the FINAL brief's prose
    and LOGS every violation.

    Deliberately **log-only (downgrade+log), not hard-fail**: a deterministic
    false-positive must never hold the 06:30 publish, and this is a P2 backstop to
    the sub-editor's LLM gate, not a replacement. It surfaces the exact signal
    (banal language, uncapped/anchorless chart_reads, bare Tier-2 abbreviations)
    in journalctl / the dry-run render so drift is visible. Escalating a specific
    check to hard-fail is a follow-up once the logs establish its precision.

    Returns the total violation count (also emitted in the summary log line).
    """
    violations = 0

    def _flag(where: str, reason: str) -> None:
        nonlocal violations
        violations += 1
        logger.warning("v6 gate: %s — %s", where, reason)

    def _check_banal(where: str, text: str | None) -> None:
        if not text:
            return
        res = _validators.validate_no_banal_language(text)
        if not res.ok:
            _flag(where, res.reason)

    _check_banal("brief.todays_call", final_brief.brief.todays_call)

    for s in final_brief.sections:
        prose_bits: list[str] = []

        if s.verdict:
            _check_banal(f"{s.slug}.verdict", s.verdict)
            prose_bits.append(s.verdict)

        if s.banker_read is not None:
            _check_banal(f"{s.slug}.banker_read.verdict", s.banker_read.verdict)
            prose_bits.append(s.banker_read.verdict)
            prose_bits.extend(s.banker_read.watch)
            prose_bits.extend(s.banker_read.risk)

        if s.analysis:
            _check_banal(f"{s.slug}.analysis", s.analysis)
            prose_bits.append(s.analysis)

        if s.chart_read is not None:
            cr = s.chart_read.model_dump(mode="json")
            for check_name, fn in (
                ("temporal_anchor", _validators.validate_chart_read_temporal_anchor),
                ("length", _validators.validate_chart_read_length),
                ("implication_quality", _validators.validate_chart_read_implication_quality),
            ):
                res = fn(cr)
                if not res.ok:
                    _flag(f"{s.slug}.chart_read.{check_name}", res.reason)
            _check_banal(f"{s.slug}.chart_read.signal", s.chart_read.signal)
            _check_banal(f"{s.slug}.chart_read.context", s.chart_read.context)
            _check_banal(f"{s.slug}.chart_read.implication", s.chart_read.implication)
            prose_bits.extend(
                [s.chart_read.signal, s.chart_read.context, s.chart_read.implication]
            )

        # §13 abbreviation policy — per-section concatenated prose (item 9 asked to
        # move the bare-Tier-2 check into the deterministic gate).
        section_text = " ".join(b for b in prose_bits if b)
        if section_text.strip():
            res = _validators.validate_abbreviation_policy(
                section_text,
                tier1_set=_validators.TIER1_ABBREVS,
                tier2_expansions=_validators.TIER2_ABBREVS_AND_EXPANSIONS,
            )
            if not res.ok:
                _flag(f"{s.slug}.abbreviation", res.reason)

    if violations:
        logger.warning(
            "v6 gate: %d deterministic prose violation(s) — see warnings above "
            "(log-only, publish NOT blocked)",
            violations,
        )
    else:
        logger.info("v6 gate: deterministic prose checks clean")
    return violations


def run_publish(
    sections: list[SectionData],
    today: date_t,
    *,
    scraped_headlines: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
    write_fixture_path: str | None = None,
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
        dump = _dump_raw_on_failure("editor_v6")
        keys = list(editor_raw.keys()) if isinstance(editor_raw, dict) else type(editor_raw).__name__
        raise V6PublishError(
            f"editor_v6 output failed schema validation (top-level keys={keys}; "
            f"raw output saved to {dump or 'nowhere — nothing stashed'}): {e}"
        ) from e

    # Force lens onto the brief — the LLM should set it but we guarantee it
    editor_brief.brief.lens = today_lens

    logger.info(
        "v6: editor produced brief with %d sections, hero=%s, frame=%s",
        len(editor_brief.sections),
        next((s.slug for s in editor_brief.sections if s.weight == 2), None),
        editor_brief.brief.frame,
    )

    # ── Call 2: Sub-editor ─────────────────────────────────────────
    # Retry-once-then-hold; NEVER auto-pass a malformed review (see _run_subeditor).
    subeditor_prompt = _pipeline._load_prompt("subeditor_v6.txt")
    subeditor_input = {"editor_output": editor_brief.model_dump(mode="json"), "raw_data": editor_input}
    review = _run_subeditor(subeditor_prompt, subeditor_input)

    if review.verdict == "fail":
        msgs = [f"  · [{i.severity}] {i.section}.{i.field}: {i.problem}" for i in review.issues]
        raise V6PublishError(f"subeditor verdict=fail with {len(review.issues)} issues:\n" + "\n".join(msgs))

    if review.verdict == "revise" and review.revised_brief is not None:
        final_brief = review.revised_brief
        # Re-force lens on revised brief
        final_brief.brief.lens = today_lens
        logger.info("v6: subeditor revised brief, %d issues fixed", len(review.issues))
    elif review.verdict == "pass":
        final_brief = editor_brief
        if review.issues:
            logger.info("v6: subeditor passed with %d warnings", len(review.issues))
        else:
            logger.info("v6: subeditor passed clean")
    else:
        # A review gate must never fail OPEN (AGENT_LEARNINGS.md). This is
        # a belt-and-suspenders check: SubeditorReview's model_validator
        # already rejects verdict="revise" with revised_brief=None at
        # construction time, but that guarantee is input-shape-only — it
        # does not survive model_construct() or attribute reassignment
        # (validate_assignment is not set). Enforce the invariant here too
        # so the publish gate itself can never ship an unreviewed brief.
        raise V6PublishError(
            f"subeditor verdict={review.verdict!r} reached the publish gate "
            "without a revised_brief — holding (a review gate must never fail OPEN)"
        )

    # ── Post-LLM: deterministic diff + held-over stamping ──────────
    stamp_changed(final_brief, previous)
    mark_held_overs(final_brief, previous, metric_definitions)
    # Vintage stamping runs LAST of the three and never overwrites
    # mark_held_overs, so a metric the catalog can explain keeps the catalog's
    # answer. In practice the catalog explains none of them — it has no
    # `section_slug` or `last_print_date` column in production — which is why
    # the "held from" footer had never rendered before this ran. See
    # brief/vintage.py.
    vintaged = stamp_vintages(final_brief, sections, today=today)
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
        "v6: stamp_changed + mark_held_overs + stamp_vintages + stamp_freshness + "
        "stamp_chart_series done; changed_news=%d, held_metrics=%d, vintaged_metrics=%d, "
        "unavailable_sections=%d, chart_sections=%d",
        sum(1 for s in final_brief.sections for n in s.news if n.changed),
        sum(1 for s in final_brief.sections for m in s.metrics if m.held_from),
        vintaged,
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

    # Deterministic post-editor prose gate (issue 156 review, item 7). Log-only —
    # runs in dry-run too, so the no-prod fixture render (landmine 21) shows the signal.
    # The try/except makes "log-only" STRUCTURAL, not incidental: without it the gate
    # could only not crash because validators.py's never-raise contract and the V6
    # schema invariants happen to hold — if either regresses, a cosmetic backstop
    # would hard-block the 06:30 fire. A gate crash is logged and publish proceeds.
    try:
        _run_deterministic_gate(final_brief)
    except Exception:  # noqa: BLE001 — the log-only gate must never block a publish
        logger.warning(
            "v6 gate: deterministic gate crashed — continuing, publish NOT blocked "
            "(log-only backstop by design)",
            exc_info=True,
        )

    if dry_run:
        logger.info("v6: dry_run=True, skipping Supabase publish")
        if write_fixture_path:
            payload = final_brief.model_dump(mode="json")
            Path(write_fixture_path).parent.mkdir(parents=True, exist_ok=True)
            with open(write_fixture_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, indent=2, default=str))
            logger.info("v6: fixture written to %s", write_fixture_path)
        return None

    try:
        return publish_brief(final_brief)
    except PublishError as e:
        raise V6PublishError(f"Supabase publish failed: {e}") from e
