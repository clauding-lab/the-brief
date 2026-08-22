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
import unicodedata
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
from brief.v6_schema import BriefPayloadV6, MetricV6, SectionV6, SubeditorReview
from brief.vintage import period_label, stamp_vintages, vintage_payload
from brief.claude import validators as _validators
from brief.validators import prose_numbers as _prose_numbers

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


class MetricReconciliationError(V6PublishError):
    """Raised when a PROTECTED_METRIC_IDS metric is still absent after
    `_reconcile_metrics` runs — e.g. the section itself failed to build, or
    the builder itself omitted the id today. This must HARD-FAIL the publish
    (surfaces as CLI exit code 4, same as a sub-editor verdict=fail): unlike
    `_run_deterministic_gate` (a log-only prose backstop that must never hold
    the fire on a false positive), a missing protected metric is never a false
    positive — the corridor either printed or it didn't (memo 2026-08-05, §4)."""


# Metric ids the editor_v6 prompt may never drop, keyed by V6 section slug.
# `_reconcile_metrics` re-injects any of these missing from the editor's
# output, sourced from the builder's own raw metric. The BB corridor is the
# reason §02 exists — SDF reached production in only 1 of the last 12 issues,
# SLF in 4, before this guard (sdf-diagnosis-2026-08-05.md §3.2). Extend this
# set deliberately; it is a hard-fail list, not a "nice to keep" list.
PROTECTED_METRIC_IDS: dict[str, frozenset[str]] = {
    "bb": frozenset({"bb_policy_rate", "bb_sdf", "bb_slf"}),
}

# Every slug a builder can legitimately produce (SectionV6.slug has no
# Pydantic allowlist — extra="forbid" only guards field NAMES, not values).
# _reconcile_metrics uses this to tell "a known section that just didn't
# build today" (routine — e.g. a test fixture, or a builder that threw) from
# "a slug the editor invented out of nothing" (never legitimate — rejected
# loudly, review finding L3).
VALID_V6_SLUGS: frozenset[str] = frozenset(slug for slug, _ord, _group in V5_TO_V6.values())


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
            # P2 fact-checker (2026-08-22 audit #204, item 2): ALWAYS present,
            # unlike `vintage` above — the deterministic period label for this
            # metric's OWN data, so the editor never has to infer or invent a
            # month/quarter name. Same underlying function `vintage.py` uses
            # for stale/warning metrics; here it runs unconditionally.
            dumped["period"] = period_label(m.as_of, m.cadence)
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


# P0 honesty fix (2026-08-22 audit #204): matches any digit-sequence,
# including internal thousands-commas and a decimal point, as one token — so
# "2.82" inside "$2.82bn" is replaced whole, leaving the surrounding "$" and
# "bn" untouched. Deliberately does NOT try to also swallow attached currency
# symbols or unit suffixes; leaving them in place keeps the sentence readable
# while still making the actual figure unrecoverable.
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_NUMBER_PLACEHOLDER = "‹n›"

# M2, review round 1: numeric LEAF values (not just numbers embedded in
# strings) are scrubbed too — a mover's `price`/`return_pct`, a still-raw
# `value`/`delta`, etc. Only STRUCTURAL bookkeeping keys survive unscrubbed;
# everything else that could read as "a figure from a previous issue" does
# not reach the editor's copy.
_SCRUB_ALLOWLIST_KEYS = frozenset({"issue_no", "volume", "ord", "weight", "read_minutes"})


def _scrub_numbers(obj: Any, *, key: str | None = None) -> Any:
    """Recursively replace every figure in `obj` with a placeholder, so no
    number from a previous brief can be copied forward into today's prose.

    The contamination this closes: `pipeline_v6._build_editor_input` feeds the
    previous issue's full payload to the editor as `previous_brief`, for
    narrative continuity ("yesterday we said X, today Y"). But the editor
    reads numbers in there too, and the 2026-08-22 audit found exact old
    figures ("$2.82bn", "fourteen reads") fossilizing forward across issues —
    the editor was quoting yesterday's number instead of computing today's.
    Scrubbing keeps every WORD and the object's structure intact (so the
    continuity narrative still works) while making every number unrecoverable.

    Three cases:
      - str: every digit-sequence inside it is replaced (`_NUMBER_RE`).
      - int/float (excluding bool): replaced wholesale with None, UNLESS its
        dict key is in `_SCRUB_ALLOWLIST_KEYS` (structural bookkeeping the
        pipeline itself needs downstream, e.g. `issue_no`/`volume` — never
        prose the editor could quote). This is what keeps a mover's
        `price`/`return_pct`, or a still-numeric `metric.value`, from
        reaching the editor unscrubbed (review round 1, M2).
      - dict/list: rebuilt recursively; a dict passes its OWN key down to
        each value so the allowlist check applies at the leaf, not the
        container.
    bool passes through unscrubbed — it isn't a figure, and `bool` is a
    subclass of `int` in Python so it must be checked before the numeric case.

    This function never mutates `obj` — every branch returns a NEW
    dict/list/string. Apply it ONLY to the copy handed to the editor prompt;
    any caller that needs the real values — `_index_previous_metrics`,
    `stamp_changed`, `mark_held_overs` — must run against the unscrubbed
    object, since `_build_editor_input` calls this after those, not before.
    """
    if isinstance(obj, str):
        return _NUMBER_RE.sub(_NUMBER_PLACEHOLDER, obj)
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)):
        if key in _SCRUB_ALLOWLIST_KEYS:
            return obj
        return None
    if isinstance(obj, dict):
        return {k: _scrub_numbers(v, key=k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub_numbers(v, key=key) for v in obj]
    return obj


def _build_editor_input(
    sections: list[SectionData],
    today: date_t,
    scraped_headlines: list[dict[str, Any]],
    *,
    previous_brief: dict[str, Any] | None,
    previous_lens: str | None,
    recent_news: list[dict[str, Any]],
    metric_definitions: list[dict[str, Any]],
    series_summaries: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> tuple[dict[str, Any], str]:
    """Build editor input + return chosen lens.

    Returns (editor_input, today_lens). Caller passes today_lens to the
    appropriate prompt template; mostly relevant when caller wants to log it.

    `series_summaries` (P2 fact-checker, 2026-08-22 audit #204, item 3) — a
    per-slug digest built by `_fetch_series_summaries`, defaulting to `{}` for
    any slug not present (no chart, or the fetch degraded). This is the fix
    for editor_v6.txt's false claim that raw input carries a chart's full
    `series` — it never has (`_stamp_chart_series` stamps the full series
    onto the FINAL brief, post-editor, for payload-size reasons; see that
    function's docstring). `chart_read` must derive only from this summary.
    """
    from brief.builders.lens import score_lens
    from brief.builders.dedup import filter_headlines
    from brief.builders.diff import _index_previous_metrics

    next_issue = fetch_max_issue_no() + 1
    raw_sections = _to_v6_raw(sections, today=today)
    for s in raw_sections:
        s["series_summary"] = (series_summaries or {}).get(s["slug"], {})

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
        # Scrubbed AFTER prev_metrics_idx/is_held_over above ran against the
        # real values — this copy is for narrative continuity only, never a
        # source of figures the editor can copy forward (P0 fix, audit #204).
        "previous_brief": _scrub_numbers(previous_brief),
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
    from brief.builders.diff import _parse_numeric

    a = _parse_numeric(curr)
    b = _parse_numeric(prev)
    if a is None or b is None:
        return 0.0
    if abs(b) < 1e-9:
        return min(abs(a), 1.0)
    return min(abs(a - b) / max(abs(b), 0.5), 1.0)


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
    from brief.builders.diff import _values_equal

    if prev_value is None:
        return False
    if cadence not in _HELD_OVER_CADENCES:
        return False
    return _values_equal(curr_value, prev_value)


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


def _format_metric_value(value: Any, unit: str) -> str:
    """Render a raw builder Metric's numeric value as the display string a
    MetricV6 expects. Mirrors editor output for the units the protected set
    actually uses (percent, 2dp — e.g. "9.50%", matching the corridor's
    existing display); falls back to "<value> <unit>" for anything else so a
    future protected id (a non-percent metric) still reconciles instead of
    crashing. `None` values (e.g. a metric the builder itself couldn't
    resolve) render as an em dash rather than the string "None"."""
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        if unit == "%":
            return f"{value:.2f}%"
        if unit:
            return f"{value:,.2f} {unit}"
        return f"{value:.10g}"
    return str(value)


def _normalize_label(label: str) -> str:
    """Normalize a metric label for cross-source comparison.

    NFC Unicode form, trimmed, casefolded. Matching this way — not exact
    string equality — stops a harmless case/whitespace/Unicode drift between
    the builder and the editor (e.g. "DSEX Close" vs "DSEX close") from being
    treated as an invented metric and silently deleted. Before this, a
    rejection this trivial would have emptied §06 `dse` to one tile with only
    a journalctl WARNING to show for it (follow-up review, H2, 2026-08-05).
    """
    return unicodedata.normalize("NFC", label).strip().casefold()


def _alert(message: str) -> None:
    """Best-effort ops alert for a reconciliation event a human should see
    same-day. `brief.alerts.send_discord_alert` already guarantees it never
    raises; the try/except here only guards the local import, matching
    `brief.cli`'s existing alert call sites — reconciliation must never fail
    (or fail to publish) because the alert path itself broke."""
    try:
        from brief.alerts import send_discord_alert
        send_discord_alert(message)
    except Exception:
        logger.exception("v6 reconcile: send_discord_alert itself failed")


def _metric_v6_from_raw(raw_metric: dict[str, Any]) -> MetricV6:
    """Build a MetricV6 for re-injection from one raw builder Metric dict
    (an entry of `sections_raw[i]["metrics"]`, i.e. `Metric.model_dump()`).

    Deliberately minimal — only `label` and a formatted `value`. Everything
    else (tone, delta, spark, changed, held_from…) is prose/diff polish the
    editor or the later stamp_* passes would normally add; a re-injected
    metric skipping that polish is a strictly better outcome than the metric
    not existing on the page at all.
    """
    label = raw_metric.get("label")
    if not label:
        raise ValueError(f"v6 reconcile: raw metric missing 'label': {raw_metric!r}")
    return MetricV6(
        label=label,
        value=_format_metric_value(raw_metric.get("value"), raw_metric.get("unit") or ""),
    )


def _reject_invented_and_dedupe(
    section: SectionV6, raw_metrics: list[dict[str, Any]]
) -> None:
    """Mutate `section.metrics` in place: drop any metric whose (normalized)
    label has no counterpart among `raw_metrics` — an editor invention, e.g.
    a synthetic "Breadth" tile merged from Advancing + Declining that exists
    in no builder (issues 177-180) — then drop same-label duplicates, keeping
    the first occurrence (an editor returning one metric twice).

    Every rejection is loud: logged at ERROR and pushed to Discord (H2). The
    deletion itself still happens — an invented label must never publish —
    but it must never again be discoverable only by grepping journalctl nine
    issues later.
    """
    raw_norm_labels = {_normalize_label(m["label"]) for m in raw_metrics if "label" in m}

    kept: list[MetricV6] = []
    dropped = 0
    for m in section.metrics:
        if _normalize_label(m.label) in raw_norm_labels:
            kept.append(m)
            continue
        dropped += 1
        logger.error(
            "v6 reconcile: REJECTED invented metric — section=%s label=%r "
            "has no counterpart among %d raw metric label(s)",
            section.slug, m.label, len(raw_norm_labels),
        )
        _alert(
            f"ALERT: The Brief editor returned metric label={m.label!r} in "
            f"section={section.slug!r} with no counterpart in the builder's "
            f"raw output — DROPPED before publish. Verify this was a genuine "
            f"invention and not a real metric under a label that failed to "
            f"match. Inspect: journalctl -u brief.service -n 200 --no-pager"
        )

    seen_norm_labels: set[str] = set()
    deduped: list[MetricV6] = []
    for m in kept:
        norm = _normalize_label(m.label)
        if norm in seen_norm_labels:
            logger.warning(
                "v6 reconcile: section=%s dropped duplicate metric label=%r "
                "(kept first occurrence)", section.slug, m.label,
            )
            continue
        seen_norm_labels.add(norm)
        deduped.append(m)
    section.metrics = deduped

    if dropped:
        logger.warning(
            "v6 reconcile: section=%s dropped %d invented metric(s); %d survive",
            section.slug, dropped, len(section.metrics),
        )


def _reinject_protected_metrics(
    section: SectionV6, raw_metrics: list[dict[str, Any]]
) -> None:
    """Mutate `section.metrics` in place: re-insert any `PROTECTED_METRIC_IDS`
    metric still missing after `_reject_invented_and_dedupe`, sourced from its
    raw builder `Metric`.

    Inserted AT ITS RAW BUILDER INDEX, clamped to the current list length —
    not appended to the tail (M1). Appending put SDF at ord=5, below both
    call-money tenors, breaking §02's corridor hierarchy on every re-inject.
    This does NOT re-sort metrics already present: the editor's legitimate
    reordering of the metrics it kept survives untouched — only the missing
    protected metric's own position is decided, and only relative to raw
    builder order.
    """
    protected_ids = PROTECTED_METRIC_IDS.get(section.slug, frozenset())
    if not protected_ids:
        return

    kept_labels = {_normalize_label(m.label) for m in section.metrics}
    editor_stored_count = len(kept_labels)  # fixed once — NOT recomputed per
    # reinject below, which would over-count already-reinjected metrics from
    # earlier in this same loop as if the editor had stored them (L2).
    built_count = len(raw_metrics)

    for i, raw_metric in enumerate(raw_metrics):  # builder order
        metric_id = raw_metric.get("id")
        label = raw_metric.get("label")
        if metric_id not in protected_ids or not label:
            continue
        norm_label = _normalize_label(label)
        if norm_label in kept_labels:
            continue
        reinjected = _metric_v6_from_raw(raw_metric)
        insert_at = min(i, len(section.metrics))
        section.metrics.insert(insert_at, reinjected)
        kept_labels.add(norm_label)
        logger.warning(
            "v6 reconcile: RE-INJECTED protected metric — section=%s id=%s "
            "label=%r at index=%d (builder built %d, editor stored %d before "
            "any reinjection)",
            section.slug, metric_id, label, insert_at, built_count,
            editor_stored_count,
        )


def _verify_protected_presence(
    final_brief: BriefPayloadV6, raw_by_slug: dict[str, dict[str, Any]]
) -> None:
    """Split verification, per finding H1 — not every missing protected
    metric is the same failure:

    - The raw builder never produced it today (no raw counterpart for the
      slug at all, or the id is absent from the raw metrics list): a routine
      upstream blip — a network timeout inside `bb.py`'s `history.get_latest`
      calls, for instance, which `brief/pipeline.py:89-96` already degrades
      to an empty-metrics `SectionData` rather than crashing the whole
      publish. Reconciliation has nothing to re-inject from. This is logged
      at ERROR and alerted to Discord, and the publish CONTINUES — converting
      a routine blip (today: one greyed section) into a lost morning edition
      would be a worse failure than the one this function exists to prevent.
    - The raw builder DID produce it, but it is still missing from the final
      brief after `_reinject_protected_metrics` ran — which only happens if
      the editor deleted the WHOLE section around it (re-injection into an
      existing section is deterministic and cannot fail once raw data
      exists). This is not a blip; the data existed and the editor discarded
      it. HARD-FAILS via `MetricReconciliationError`.
    """
    section_by_slug = {s.slug: s for s in final_brief.sections}
    hard_missing: list[str] = []

    for slug, protected_ids in PROTECTED_METRIC_IDS.items():
        raw_section = raw_by_slug.get(slug)
        raw_metrics: list[dict[str, Any]] = (raw_section or {}).get("metrics") or []
        raw_by_id = {m.get("id"): m for m in raw_metrics}
        section = section_by_slug.get(slug)
        final_labels = (
            {_normalize_label(m.label) for m in section.metrics}
            if section is not None else set()
        )

        for metric_id in protected_ids:
            raw_metric = raw_by_id.get(metric_id)
            if raw_metric is None:
                logger.error(
                    "v6 reconcile: DEGRADED — protected metric %s.%s was not "
                    "built today (builder error, or the source row is "
                    "missing) — publish CONTINUES with %s degraded",
                    slug, metric_id, slug,
                )
                _alert(
                    f"ALERT: The Brief §{slug} builder did not produce "
                    f"protected metric {metric_id!r} today — publishing "
                    f"anyway with {slug} degraded. This is a builder-side "
                    f"blip (H1), not a hold. Inspect: journalctl -u "
                    f"brief.service -n 200 --no-pager"
                )
                continue
            if _normalize_label(raw_metric.get("label") or "") not in final_labels:
                hard_missing.append(f"{slug}.{metric_id}")

    if hard_missing:
        raise MetricReconciliationError(
            "v6 reconcile: protected metric(s) were built by the raw "
            "pipeline but are absent from the final brief after "
            f"reconciliation — holding the publish: {hard_missing}"
        )


def _reconcile_metrics(
    final_brief: BriefPayloadV6, raw_sections: list[dict[str, Any]]
) -> None:
    """Deterministic post-editor metric reconciliation (sdf-diagnosis-2026-08-05.md §4).

    `editor_v6.txt:49` grants the editor discretionary authority to reorder
    and drop "low-signal" metrics, capped at 5 per section — and nothing
    downstream ever validated what survived: an empty `metrics` list passes
    the V6 schema, and the publisher writes whatever the editor returned
    verbatim. Consequences, all closed here:

      1. The editor can INVENT a metric that exists in no builder (e.g.
         "Breadth" merged from Advancing + Declining, issues 177-180), or a
         whole SECTION that maps to no builder at all — neither `MetricV6`
         nor `SectionV6.slug` carries an allowlist, so nothing objected.
      2. A section fed more than 5 metrics loses whichever ones the editor
         judges least newsworthy that day — for §02 `bb`, that meant SDF
         survived only 1 of the last 12 issues and SLF only 4 (builder order
         carries no downstream meaning post-editor — AGENTS.md landmine 25).

    Per-section (mutates `final_brief.sections[i].metrics` in place via the
    helpers below): reject invented metric labels + dedupe
    (`_reject_invented_and_dedupe`), then re-inject missing protected metrics
    at their builder index (`_reinject_protected_metrics`). A section whose
    slug has no raw counterpart is left untouched UNLESS the slug itself is
    not a real V6 slug at all (`VALID_V6_SLUGS`) — an editor-invented
    section is dropped from `final_brief.sections` entirely and alerted, not
    silently published.

    Brief-wide: `_verify_protected_presence` — HARD-FAILS
    (`MetricReconciliationError`) only when the raw builder proved a
    protected metric existed today and the final brief still doesn't have
    it; a protected metric the builder itself never produced today degrades
    the section and alerts instead of blocking the whole publish (H1).
    """
    raw_by_slug: dict[str, dict[str, Any]] = {
        s["slug"]: s for s in raw_sections if "slug" in s
    }

    kept_sections: list[SectionV6] = []
    for section in final_brief.sections:
        raw_section = raw_by_slug.get(section.slug)

        if raw_section is None:
            if section.slug not in VALID_V6_SLUGS:
                logger.error(
                    "v6 reconcile: REJECTED invented section — slug=%r matches "
                    "no known V6 slug; %d metric(s) discarded with it",
                    section.slug, len(section.metrics),
                )
                _alert(
                    f"ALERT: The Brief editor invented section slug="
                    f"{section.slug!r} with no counterpart in any builder — "
                    f"DROPPED before publish. Inspect: journalctl -u "
                    f"brief.service -n 200 --no-pager"
                )
                continue  # drop — do not publish an invented section
            kept_sections.append(section)  # known slug, just didn't build today
            continue

        raw_metrics: list[dict[str, Any]] = raw_section.get("metrics") or []
        _reject_invented_and_dedupe(section, raw_metrics)
        _reinject_protected_metrics(section, raw_metrics)
        kept_sections.append(section)

    final_brief.sections = kept_sections
    _verify_protected_presence(final_brief, raw_by_slug)


# M-A, review round 2 (2026-08-22 audit #204): the marker substring the
# builder's dual-period note and the published `sub` field are both checked
# against, so a re-run never double-appends.
_IMPORT_COVER_SUB_MARKER = "import bill"


def _stamp_import_cover_sub(
    final_brief: BriefPayloadV6, raw_sections: list[dict[str, Any]]
) -> None:
    """Force the published Import Cover metric's `sub` to name both periods
    the ratio combines (M-A, review round 2, 2026-08-22 audit #204).

    `MetricV6` has no `source` field: the builder's dual-period note (set on
    the RAW metric's `source` by `macro._import_cover`, H1 review round 1)
    is dropped the moment the editor's output is validated against the V6
    schema — `_Lenient.model_config` is `extra="ignore"`, so an editor that
    faithfully copied `source` through would still lose it, and one that
    didn't never had a chance either way. `sub` is the only free-text field
    `MetricV6` actually carries to the reader. This pass runs
    deterministically, AFTER `_reconcile_metrics`, and reads the note from
    the BUILDER's raw output — never from the editor's memory of it — so the
    dual-period disclosure reaches the reader regardless of what (or
    whether) the editor wrote into `sub`.

    A no-op when the raw metric has no value (suppressed this issue), when
    its `source` carries no dual-period note (i.e. `_import_cover` didn't
    take its success path), or when the published `sub` already contains
    the marker phrase (never double-appends on a re-run).
    """
    note: str | None = None
    for s in raw_sections:
        if s.get("slug") != "macro":
            continue
        for m in s.get("metrics", []) or []:
            if m.get("label") != "Import Cover" or m.get("value") is None:
                continue
            src = m.get("source") or ""
            if "reserves" in src and _IMPORT_COVER_SUB_MARKER in src:
                start = src.find("reserves")
                end = src.find(_IMPORT_COVER_SUB_MARKER) + len(_IMPORT_COVER_SUB_MARKER)
                note = src[start:end]
        break

    if not note:
        return

    for section in final_brief.sections:
        if section.slug != "macro":
            continue
        for pub in section.metrics:
            if pub.label != "Import Cover":
                continue
            current = pub.sub or ""
            if _IMPORT_COVER_SUB_MARKER not in current:
                pub.sub = f"{current} · {note}" if current else note
        break


# ─── P2 fact-checker — pre-editor series_summary (item 3) ──────────────
# Slug → chart_series_fetcher function name for the `*_monthly` group (each
# returns dict[metric_id, list[SeriesPointV6]]). Mirrors the per-slug
# dispatch inside `_stamp_chart_series` below deliberately — see
# `_fetch_series_summaries`'s docstring for why this is a SEPARATE, smaller
# fetch rather than a refactor of that (already tested) function.
_SUMMARY_MONTHLY_FETCHERS: dict[str, str] = {
    "macro": "fetch_macro_cpi_series",
    "remit": "fetch_remit_monthly",
    "bb": "fetch_reserves_monthly",
    "tbond": "fetch_yield_ladder_monthly",
    "fx": "fetch_fx_balance_monthly",
    "fiscal": "fetch_fiscal_monthly",
}


def summarize_series_points(points: list[Any]) -> dict[str, dict[str, Any]]:
    """Reduce a flat list of SeriesPointV6-like objects (`.key`/`.ts`/`.value`
    attributes, or dicts with the same keys) into a compact per-series-key
    digest: `{n, first_ts, first_value, last_ts, last_value, min, max}`.

    Groups by `key` (points with no key fall into `"series"`), sorts each
    group by `ts` before reducing — callers don't need to pre-sort, and the
    daily HTTP fetchers already return ascending order anyway so this is a
    no-op there. Points with a None `value` are skipped entirely (round-2
    review, item 7) — `SeriesPointV6.value` is typed non-optional, but this
    function also accepts plain dicts from callers that haven't gone through
    that validation yet, and `min()`/`max()` on a None-containing list raises
    a `TypeError` that would otherwise take down the whole pre-editor fetch.
    A key whose points are ALL None-valued is dropped from the output rather
    than emitting an empty/nonsensical digest.
    """
    def _get(p: Any, name: str) -> Any:
        return getattr(p, name) if hasattr(p, name) else p[name]

    by_key: dict[str, list[Any]] = {}
    for p in points:
        if _get(p, "value") is None:
            continue
        key = _get(p, "key") or "series"
        by_key.setdefault(key, []).append(p)

    out: dict[str, dict[str, Any]] = {}
    for key, pts in by_key.items():
        if not pts:
            continue
        ordered = sorted(pts, key=lambda p: _get(p, "ts"))
        values = [_get(p, "value") for p in ordered]
        out[key] = {
            "n": len(ordered),
            "first_ts": _get(ordered[0], "ts"),
            "first_value": values[0],
            "last_ts": _get(ordered[-1], "ts"),
            "last_value": values[-1],
            "min": min(values),
            "max": max(values),
        }
    return out


def _fetch_series_summaries(
    *, today: date_t, http: HttpClient, supabase_url: str, service_key: str,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Pre-editor lightweight chart-series digest, keyed by V6 section slug
    (P2 fact-checker, 2026-08-22 audit #204, item 3 — "the prompt FALSELY
    tells [the editor] input contains `series`; series are stamped AFTER the
    editor runs").

    Calls the SAME `chart_series_fetcher` functions `_stamp_chart_series`
    calls post-editor, but keeps only `summarize_series_points`'s digest —
    never the full point array — so the editor gets honest "what does the
    chart actually show" grounding without paying the payload-size cost of
    sending every point twice. `_stamp_chart_series` is UNCHANGED and still
    fetches + stores the FULL series after the editor runs; this is a
    separate, smaller, EARLIER fetch, not a replacement for it (deliberately
    NOT refactored into a shared helper — `_stamp_chart_series` is small,
    already tested, and touching its internals for this is not worth the
    risk of destabilizing it; the per-slug branch list here is intentionally
    duplicated, not extracted).

    Graceful degradation matches `_stamp_chart_series`: any one fetcher
    failing logs a WARNING and that slug's summary is simply absent from the
    result (the editor input then carries `series_summary: {}` for it —
    treated as "no chart data available", never a fatal error).
    """
    from brief.history import MetricHistoryClient as _MetricHistoryClient

    history_monthly_client = _MetricHistoryClient(
        url=supabase_url, service_key=service_key, http=http,
    )
    out: dict[str, dict[str, dict[str, Any]]] = {}

    for slug, fn_name in _SUMMARY_MONTHLY_FETCHERS.items():
        try:
            fn = getattr(chart_series_fetcher, fn_name)
            series_by_id = fn(history_monthly_client)
            flat = [pt for pts in series_by_id.values() for pt in pts]
            out[slug] = summarize_series_points(flat)
        except Exception:  # noqa: BLE001 — graceful degradation
            logger.warning(
                "v6: series_summary pre-fetch failed for slug=%s (fn=%s)",
                slug, fn_name, exc_info=True,
            )

    # dse + iran (brent) use the daily HTTP fetchers — different signature.
    try:
        dsex_series, _notes = chart_series_fetcher.fetch_dsex(
            http=http, supabase_url=supabase_url, service_key=service_key, today=today,
        )
        out["dse"] = summarize_series_points(dsex_series)
    except Exception:  # noqa: BLE001 — graceful degradation
        logger.warning("v6: series_summary pre-fetch failed for slug=dse", exc_info=True)

    try:
        brent_series = chart_series_fetcher.fetch_brent(
            http=http, supabase_url=supabase_url, service_key=service_key, today=today,
        )
        out["iran"] = summarize_series_points(brent_series)
    except Exception:  # noqa: BLE001 — graceful degradation
        logger.warning("v6: series_summary pre-fetch failed for slug=iran", exc_info=True)

    return out


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


# P0 honesty fix (2026-08-22 audit #204): hard-denylisted hallucination
# signatures. The editor invented a "$80 FY27 [crude]" budget-assumption
# motif — repeated with "$14.09" — that has no basis anywhere in Bangladesh's
# actual FY27 budget. Unlike the rest of `_run_deterministic_gate` (a log-only
# backstop that must never hold the publish on a false positive), these
# patterns are specific enough that a false positive is not a realistic risk
# PROVIDED the scan is scoped to prose: HARD-FAIL, don't log-and-ship.
#
# Review round 1 (C1, BLOCKER): the first cut of this check scanned
# `model_dump_json()` of the WHOLE brief, including chart series points,
# sparklines and movers. A chart value that happens to serialize as
# `...5114.09...` matches the bare `\$?14\.09` pattern with zero relation to
# the FY27 hallucination — a real reviewer reproduction, and it would have
# held the publish for as long as that data point stayed in the trailing
# window (up to a year for a monthly series). Two fixes, both required:
#   1. Scan PROSE FIELDS ONLY (`_collect_prose_fields`) — never
#      `metric.value`, `spark`, `series`, `notes`, or `movers`.
#   2. The bare "$14.09" pattern is replaced with a CO-OCCURRENCE rule: a
#      "14.09" only blocks when the SAME prose field also mentions FY27,
#      $80, "crude", or "budget" — i.e. it has to look like the actual
#      hallucination, not just contain that one number. A genuine desk line
#      like "Brent settled at $14.09 on thin volume" has none of that context
#      and must PASS.
# The $80<->FY27 proximity patterns (either word order) are unchanged and
# still hard-fail on their own — they are specific enough already.
_FY27_80_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\$80\b[^.]{0,60}FY.?27", re.IGNORECASE),
    re.compile(r"FY.?27[^.]{0,60}\$80\b", re.IGNORECASE),
)
# H-A, review round 2: bounded on both sides so "14.09" is only matched when
# it is the WHOLE number, not a substring of a larger one. The bare version
# (no lookaround) matched "14.09" inside "Tk1,214.09", "314.09bn", "3,914.09"
# and "4,014.09" — real banker-grade figures with nothing to do with the
# audit's hallucination. `(?<![\d.,])` refuses a digit/period/comma
# immediately before the match (so it can't be the tail of a bigger number);
# `(?!\d)` refuses a digit immediately after (so "14.099" doesn't match either).
_1409_RE = re.compile(r"(?<![\d.,])\$?14\.09(?!\d)")
_1409_CONTEXT_RE = re.compile(r"FY.?27|\$80\b|crude|budget", re.IGNORECASE)


class DenylistViolationError(V6PublishError):
    """Raised when a hard-denylisted hallucination pattern appears in the
    final brief's PROSE. See the 2026-08-22 audit (issue #204): the editor
    invented an "$80 FY27" crude-price budget assumption and a "$14.09"
    figure with no basis in Bangladesh's actual FY27 budget. This must
    propagate and hold the publish — see the call site in `run_publish`,
    which re-raises this specific error THROUGH the blanket
    `except Exception` that otherwise makes the deterministic gate log-only.
    """


class ProseNumberGateError(V6PublishError):
    """Raised when `brief.validators.prose_numbers` finds a sourceless
    count-claim anywhere in the brief (`check_count_claims` — the ONLY
    unconditional BLOCK post-round-2 review, corpus-verified 14/14 TP, 0 FP;
    P2 fact-checker, 2026-08-22 audit #204), OR — only when
    `BRIEF_PROSE_VALIDATOR_STRICT=1` — any WARN-mode figure/period mismatch.
    Same propagation shape as `DenylistViolationError` — see
    `_run_prose_number_gate`, which wraps `prose_numbers.ProseNumberViolationError`
    into this so it reaches `cli.py`'s existing exit-code-4 handling
    (AGENTS.md's editor/sub-editor convention note)."""


def _collect_prose_fields(final_brief: BriefPayloadV6) -> list[tuple[str, str]]:
    """Every prose text surface the denylist may scan, as (field_path, text).

    Deliberately excludes anything numeric/series-shaped — `metric.value`,
    `metric.delta`/`delta_pct`, `spark`, `series`, `movers` — so a real chart
    data point can never trip a prose-hallucination pattern (C1). `metric.sub`,
    `cover_metric.sub`, and `notes[].detail` ARE included: they are free-text
    the editor writes, the same kind of surface `todays_call` is (L-C, review
    round 2 — `notes[].detail` was originally lumped in with the numeric
    exclusions by mistake; it is prose, `series_key`/`ts` on the same object
    are not).

    Deliberately ALSO excludes (L-C): closed-vocabulary/structural strings the
    editor picks from a fixed set or copies verbatim rather than composes —
    `brief.lens`, `brief.frame` (enum-like slugs), section/metric/news
    `label`/`title` fields, and `notes[].label` (a short annotation tag, not
    prose). None of these are places a multi-sentence hallucination could
    hide, and scanning them would only add false-positive surface.
    """
    fields: list[tuple[str, str]] = []
    if final_brief.brief.todays_call:
        fields.append(("brief.todays_call", final_brief.brief.todays_call))
    if final_brief.brief.cover_metric is not None and final_brief.brief.cover_metric.sub:
        fields.append(("brief.cover_metric.sub", final_brief.brief.cover_metric.sub))
    for s in final_brief.sections:
        if s.tldr:
            fields.append((f"{s.slug}.tldr", s.tldr))
        if s.verdict:
            fields.append((f"{s.slug}.verdict", s.verdict))
        if s.analysis:
            fields.append((f"{s.slug}.analysis", s.analysis))
        if s.banker_read is not None:
            fields.append((f"{s.slug}.banker_read.verdict", s.banker_read.verdict))
            for i, w in enumerate(s.banker_read.watch):
                fields.append((f"{s.slug}.banker_read.watch[{i}]", w))
            for i, r in enumerate(s.banker_read.risk):
                fields.append((f"{s.slug}.banker_read.risk[{i}]", r))
        if s.chart_read is not None:
            fields.append((f"{s.slug}.chart_read.signal", s.chart_read.signal))
            fields.append((f"{s.slug}.chart_read.context", s.chart_read.context))
            fields.append((f"{s.slug}.chart_read.implication", s.chart_read.implication))
        for i, pill in enumerate(s.summary_pills):
            fields.append((f"{s.slug}.summary_pills[{i}].value", pill.value))
        for i, n in enumerate(s.news):
            fields.append((f"{s.slug}.news[{i}].headline", n.headline))
            if n.detail:
                fields.append((f"{s.slug}.news[{i}].detail", n.detail))
        for i, m in enumerate(s.metrics):
            if m.sub:
                fields.append((f"{s.slug}.metrics[{i}].sub", m.sub))
        for i, note in enumerate(s.notes):
            if note.detail:
                fields.append((f"{s.slug}.notes[{i}].detail", note.detail))
    return fields


def _check_hard_denylist(final_brief: BriefPayloadV6) -> None:
    """Hard-fail if any denylisted hallucination pattern appears in PROSE.

    Raises `DenylistViolationError`; never returns a count like the log-only
    checks below — this is a HOLD, not a signal.
    """
    for field_path, text in _collect_prose_fields(final_brief):
        for pattern in _FY27_80_PATTERNS:
            if pattern.search(text):
                raise DenylistViolationError(
                    f"v6 gate: hard denylist match at {field_path!r} "
                    f"({pattern.pattern!r}) — this is the '$80 FY27' "
                    "hallucination from the 2026-08-22 audit (issue #204); "
                    "the editor invented a figure with no basis in "
                    "Bangladesh's actual FY27 budget. Publish held."
                )
        if _1409_RE.search(text) and _1409_CONTEXT_RE.search(text):
            raise DenylistViolationError(
                f"v6 gate: hard denylist match at {field_path!r} "
                "('$14.09' co-occurring with FY27/$80/crude/budget context) "
                "— this is the 2026-08-22 audit's (issue #204) hallucinated "
                "figure, not a coincidental number. Publish held."
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

    EXCEPTION: `_check_hard_denylist`, run first, is NOT log-only — see its
    docstring and `DenylistViolationError`. It is called from inside this
    function (per the 2026-08-22 audit's spec) but raises rather than
    incrementing the violation count, and the call site in `run_publish` lets
    that specific exception propagate through the blanket catch-all below.

    Returns the total violation count (also emitted in the summary log line).
    """
    _check_hard_denylist(final_brief)  # raises DenylistViolationError — must propagate

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


def _format_prose_number_alert(warnings: list["_prose_numbers.NumberWarning"]) -> str:
    """One Discord message for ALL of this issue's WARN-mode figures, grouped
    by section (H3, round-2 review item 6) — a publish with N warnings used
    to send N separate Discord messages, which drowns the channel on a bad
    day and reads as N unrelated incidents instead of one. Truncation to
    Discord's 2000-char cap is `alerts.send_discord_alert`'s job; this only
    shapes the content."""
    by_section: dict[str, list["_prose_numbers.NumberWarning"]] = {}
    for w in warnings:
        by_section.setdefault(w.section, []).append(w)
    lines = [f"WARN: The Brief prose-number gate — {len(warnings)} figure(s) across {len(by_section)} section(s):"]
    for section, section_warnings in by_section.items():
        lines.append(f"  [{section}]")
        for w in section_warnings:
            lines.append(f"    {w.describe()}")
    return "\n".join(lines)


def _run_prose_number_gate(
    final_brief: BriefPayloadV6, raw_sections: list[dict[str, Any]],
) -> list["_prose_numbers.NumberWarning"]:
    """Wire `brief.validators.prose_numbers` in (P2 fact-checker, 2026-08-22
    audit #204, round-2 review). `check_count_claims` is the ONLY BLOCK-mode
    check post-round-2 (14/14 TP, 0 FP against a 25-real-issue corpus replay)
    and HOLDS the publish via `ProseNumberGateError`. Everything else
    (sub numbers/periods, metric.value vs raw, lede figures) is WARN-mode —
    collected and sent as ONE grouped Discord alert (H3), never blocking —
    UNLESS `BRIEF_PROSE_VALIDATOR_STRICT=1`, which upgrades the whole set to
    the same hard-fail (a documented future flip, not yet default; see the
    module docstring in brief/validators/prose_numbers.py for the corpus
    evidence behind this staging)."""
    strict = os.environ.get("BRIEF_PROSE_VALIDATOR_STRICT", "").strip() == "1"
    try:
        warnings = _prose_numbers.run_prose_number_gate(final_brief, raw_sections, strict=strict)
    except _prose_numbers.ProseNumberViolationError as e:
        raise ProseNumberGateError(str(e)) from e

    if warnings:
        for w in warnings:
            logger.warning("v6 prose-number gate (WARN): %s", w.describe())
        _alert(_format_prose_number_alert(warnings))
        logger.warning(
            "v6 prose-number gate: %d WARN-mode figure(s) with no builder "
            "match (log-only unless BRIEF_PROSE_VALIDATOR_STRICT=1)",
            len(warnings),
        )
    else:
        logger.info("v6 prose-number gate: clean")
    return warnings


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

    # P2 fact-checker (2026-08-22 audit #204, item 3): a lightweight PRE-editor
    # chart digest. Resolved separately from the post-editor supabase_cfg below
    # — this is an earlier, smaller fetch, not a substitute for `_stamp_chart_series`.
    series_summaries: dict[str, dict[str, dict[str, Any]]] = {}
    pre_editor_supabase_cfg = _resolve_supabase_config()
    if pre_editor_supabase_cfg is None:
        logger.warning(
            "v6: skipping series_summary pre-fetch — SUPABASE_URL or service key missing in env"
        )
    else:
        pre_url, pre_key = pre_editor_supabase_cfg
        try:
            series_summaries = _fetch_series_summaries(
                today=today, http=UrllibHttp(), supabase_url=pre_url, service_key=pre_key,
            )
        except Exception:  # noqa: BLE001 — the editor still runs without chart grounding
            logger.warning(
                "v6: series_summary pre-fetch failed entirely — editor gets no "
                "chart grounding this issue",
                exc_info=True,
            )

    editor_input, today_lens = _build_editor_input(
        sections,
        today,
        scraped_headlines or [],
        previous_brief=previous,
        previous_lens=previous_lens,
        recent_news=recent_news,
        metric_definitions=metric_definitions,
        series_summaries=series_summaries,
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

    # ── Post-LLM: metric reconciliation FIRST, then diff + held-over ────
    # Deterministic post-editor metric reconciliation (sdf-diagnosis-2026-08-05.md
    # §4, Fix A) runs BEFORE stamp_changed/mark_held_overs/stamp_vintages —
    # not after them. A re-injected protected metric must be visible to those
    # three passes so it gets a real "changed" dot and vintage "As of…"
    # footer like any other metric, instead of silently defaulting to
    # changed=False/no vintage because it was spliced in after they already
    # ran (follow-up review, M2). The original "after" placement was
    # justified by proximity to `_stamp_freshness`, which is section-level
    # and doesn't care about metric identity either way — that justification
    # doesn't extend to stamp_changed/mark_held_overs/stamp_vintages, which
    # all key off individual metrics. Must HARD-FAIL (raise) on a genuine
    # loss, unlike the log-only `_run_deterministic_gate` below — see
    # MetricReconciliationError's docstring for why the two do not share a
    # log-only rationale.
    _reconcile_metrics(final_brief, editor_input["sections_raw"])
    # M-A, review round 2: deterministically stamps the macro Import Cover
    # metric's `sub` with its dual-period note — MetricV6 has no `source`
    # field, so nothing upstream of this call guarantees the note survives.
    _stamp_import_cover_sub(final_brief, editor_input["sections_raw"])

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
    #
    # EXCEPTION: DenylistViolationError (P0 honesty fix, 2026-08-22 audit #204)
    # is a deliberate HARD-FAIL, not a gate crash — re-raised THROUGH this
    # catch-all so the "$80 FY27" / "$14.09" hallucination signature holds the
    # publish instead of being logged and shipped.
    try:
        _run_deterministic_gate(final_brief)
    except DenylistViolationError:
        raise
    except Exception:  # noqa: BLE001 — the log-only gate must never block a publish
        logger.warning(
            "v6 gate: deterministic gate crashed — continuing, publish NOT blocked "
            "(log-only backstop by design)",
            exc_info=True,
        )

    # P2 fact-checker (2026-08-22 audit #204, item 1): the number/period
    # validator, run right after the editor/sub-editor output is FINAL —
    # after every deterministic stamp above has had its say on `sub` text —
    # and before publish. BLOCK-mode violations propagate (ProseNumberGateError
    # is a V6PublishError subclass); WARN-mode figures are logged and returned.
    _run_prose_number_gate(final_brief, editor_input["sections_raw"])

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
