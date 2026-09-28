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
import math
import os
import re
import struct
import time
import unicodedata
from collections.abc import Callable
from datetime import date as date_t, timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, NamedTuple

from brief import chart_series_fetcher, pipeline as _pipeline
from brief.claude.max_client import MaxCallError, run_max
from brief.history import HttpClient, UrllibHttp
from brief.press_override import is_press_card_source
from brief.schema import Metric, SectionData
from brief.publication_identity import PublishIdentity, assert_identity, environment_paused
from brief.v6_publisher import (
    PublishError,
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
    sections: list[SectionData],
    *,
    today: date_t | None = None,
    extra_history_facts: dict[str, list[Any]] | None = None,
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

    `extra_history_facts` (issues 205-208) appends slug-keyed facts computed
    OUTSIDE the builders — today the dse session-low anchor, which needs the
    chart series a builder never sees. They are serialised through the exact
    same path as a builder's own `SectionData.history_facts`, so the editor
    cannot tell the two apart and needs no prompt change to use them.
    """
    out: list[dict[str, Any]] = []
    for s in sections:
        if s.id not in V5_TO_V6:
            continue
        slug, ord_v6, group = V5_TO_V6[s.id]
        history_facts = list(s.history_facts or []) + list(
            (extra_history_facts or {}).get(slug, [])
        )
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
                    for f in history_facts
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
    dict/list/string. Apply it ONLY to the copy handed to a prompt; any caller
    that needs the real values — `_index_previous_metrics`, `stamp_changed`,
    `mark_held_overs` — must run against the unscrubbed object, since
    `_build_editor_input` calls this after those, not before.

    As of 2026-08-26 this is the SUB-EDITOR's copy of `previous_brief` only.
    The Editor gets `_previous_brief_skeleton` instead — see that function for
    why scrubbing numbers proved insufficient on its own.
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


# The Editor's view of yesterday, 2026-08-26. Deliberately an ALLOWLIST of
# structural fields rather than a denylist of prose ones: a field added to the
# schema later is excluded by default, which is the safe direction. Every name
# here is either a slug, an enum-ish label, or an int the pipeline itself owns
# — nothing an editor could lift a sentence from.
_PREV_BRIEF_KEEP = ("issue_no", "volume", "lens", "frame")
_PREV_SECTION_KEEP = ("slug", "ord", "weight", "title", "group_key", "verdict_tone", "freshness")


def _previous_brief_skeleton(previous_brief: dict[str, Any] | None) -> dict[str, Any] | None:
    """Yesterday's SHAPE, with none of yesterday's words.

    Why this exists (issue 208, 2026-08-26). `_scrub_numbers` was the first
    attempt at this problem and it fixed the half it was aimed at: no figure
    from a previous issue can be copied forward. But it keeps every WORD, on
    the theory that the editor needs yesterday's prose for narrative
    continuity. Measured against real output, that theory cost more than it
    bought — where the underlying data had not moved, the editor read
    yesterday's sentence and restated it. Issue 207's `macro` section came
    back 100.0% byte-identical to 206's; 208 still had `banking` at 97.4%
    after a prompt rule (PR #178) explicitly forbade the reuse. Handing a
    model a finished draft and instructing it not to revise the draft is not a
    contest the instruction wins.

    So the editor no longer receives the draft. What it receives is what it
    demonstrably USES — which turned out to be almost entirely structural:

      · `cover_metric.section_slug` + each section's `weight` → hero rotation,
        the one use `editor_v6.txt` actually documents.
      · `verdict_tone` per section → whether a section's stance flipped.
      · `slug`/`ord`/`title`/`group_key`/`freshness` → the page's shape.
      · `metric_labels` → which metrics were on the page (labels, never values
        or their `sub` copy).

    Everything else the editor needs from the previous issue already reaches
    it by a path that reads the REAL, unscrubbed object earlier in
    `_build_editor_input` — `is_held_over` via `_index_previous_metrics`,
    headline de-duplication via `filter_headlines`/`recent_news`, lens
    rotation via the separate `previous_lens` argument. None of those are
    affected by this.

    What is genuinely lost: the editor can no longer see that it already made
    a point yesterday and pick a different angle. That is an acceptable trade.
    Restating a true, unmoved fact in today's words is the correct output and
    the voice rules say so explicitly; the alternative was measured above.

    The SUB-EDITOR still receives the full number-scrubbed prose (see
    `run_publish`), so the reviewer can still catch two issues landing
    near-identical — now as convergence rather than copying, but just as
    unwanted either way. Editor blind, reviewer sighted.

    Returns None for None (first run), mutates nothing.
    """
    if not previous_brief:
        return None
    brief = previous_brief.get("brief") or {}
    cover = brief.get("cover_metric") or {}
    skeleton_brief: dict[str, Any] = {k: brief.get(k) for k in _PREV_BRIEF_KEEP}
    # Only the two cover fields that carry no prose — `label`/`value`/`sub`/
    # `as_of` are exactly the figures and copy this function exists to drop.
    skeleton_brief["cover_metric"] = {
        "section_slug": cover.get("section_slug"),
        "tone": cover.get("tone"),
    }
    sections = []
    for s in previous_brief.get("sections") or []:
        row: dict[str, Any] = {k: s.get(k) for k in _PREV_SECTION_KEEP}
        row["metric_labels"] = [
            m.get("label") for m in (s.get("metrics") or []) if m.get("label")
        ]
        sections.append(row)
    return {"brief": skeleton_brief, "sections": sections}


def _build_editor_input(
    sections: list[SectionData],
    today: date_t,
    scraped_headlines: list[dict[str, Any]],
    *,
    expected_identity: PublishIdentity,
    previous_brief: dict[str, Any] | None,
    previous_lens: str | None,
    recent_news: list[dict[str, Any]],
    metric_definitions: list[dict[str, Any]],
    series_summaries: dict[str, dict[str, dict[str, Any]]] | None = None,
    derived_history_facts: dict[str, list[Any]] | None = None,
) -> tuple[dict[str, Any], str]:
    """Build editor input + return chosen lens.

    `expected_identity` is allocated once by the CLI before gather; this helper
    never reads or allocates issue numbers.

    Returns (editor_input, today_lens). Caller passes today_lens to the
    appropriate prompt template; mostly relevant when caller wants to log it.

    `series_summaries` (P2 fact-checker, 2026-08-22 audit #204, item 3) — a
    per-slug digest built by `_fetch_series_summaries`, defaulting to `{}` for
    any slug not present (no chart, or the fetch degraded). This is the fix
    for editor_v6.txt's false claim that raw input carries a chart's full
    `series` — it never has (`_stamp_chart_series` stamps the full series
    onto the FINAL brief, post-editor, for payload-size reasons; see that
    function's docstring). `chart_read` must derive only from this summary.

    `derived_history_facts` (issues 205-208) — slug-keyed `HistoryFact`s
    computed from those same series by `_fetch_series_summaries`, merged into
    each raw section's existing `history_facts` list by `_to_v6_raw`.
    """
    from brief.builders.lens import score_lens
    from brief.builders.dedup import filter_headlines
    from brief.builders.diff import _index_previous_metrics

    raw_sections = _to_v6_raw(
        sections, today=today, extra_history_facts=derived_history_facts
    )
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
        # Built AFTER prev_metrics_idx/is_held_over above ran against the real
        # values. Structure only — no figures (P0 fix, audit #204) and, since
        # 2026-08-26, no prose either: yesterday's wording was the draft the
        # editor kept revising instead of writing. See
        # `_previous_brief_skeleton`. The SUB-EDITOR's copy is rebuilt with the
        # prose restored in `run_publish` — it needs the wording to review it.
        "previous_brief": _previous_brief_skeleton(previous_brief),
        "scraped_headlines": filtered_headlines,
        "sections_raw": raw_sections,
        "meta": {
            "issue_no": expected_identity.issue_no,
            "volume": (previous_brief or {}).get("brief", {}).get("volume", 1),
            "brief_date": expected_identity.brief_date.isoformat(),
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


# The house style of a card number (Master.md "Numbers and currency"): builder
# unit -> (prefix, suffix). Where Master.md is silent, issue 235's published pills
# set the convention ("$98.32" a barrel, "$4,328.9/oz", a bare index or count).
_HOUSE_UNIT_STYLE: dict[str, tuple[str, str]] = {
    "%": ("", "%"),
    "bn USD": ("$", "bn"),
    "mn USD": ("$", "mn"),
    "USD/oz": ("$", "/oz"),
    "USD/bbl": ("$", ""),
    "crore BDT": ("Tk ", " cr"),
    "BDT trn": ("Tk ", "tn"),
    "BDT": ("", ""),       # the USD/BDT rate, bare as issue 235 printed it
    "index": ("", ""),
    "stocks": ("", ""),
    "items": ("", ""),
    "months": ("", " months"),
    "pp": ("", "pp"),  # a change of a % figure, in percentage points (R2 fix 16)
}
_MINUS = "−"  # Master.md: negatives use the minus glyph, not a hyphen
_FLOAT64_DIGITS = 15  # a double carries 15 faithful significant decimal digits
# Card ids whose producer feed is float32 (R2 fix 7b3, controller ruling 27 Sep
# 2026): EconDelta's commodity scraper reads Brent, WTI and gold from yfinance
# (scrapers/commodity_prices.py COMMODITY_SPEC; aggregate_latest.py names them
# brent_crude_usd_barrel / wti_crude_usd_barrel / gold_usd_oz), whose prices are
# float32 — 98.32 arrives widened as 98.31999969482422. Only these cards print
# float32's shortest decimal; no other feed's digits are ever shortened. A new
# float32 feed must be added here by name, never detected by its digits.
_FLOAT32_FEED_CARD_IDS: frozenset[str] = frozenset({
    "iranwar_brent_spot",  # iranwar.py <- brent_crude_usd_barrel
    "iranwar_wti_spot",    # iranwar.py <- wti_crude_usd_barrel
    "fx_gold_usd_oz",      # fx.py <- gold_usd_oz
})


def _float32_decimal(value: float) -> str | None:
    """The shortest decimal of a float32 reading widened to float64 (a feed's
    98.31999969482422 is float32's "98.32"), at any magnitude; None when
    `value` is no float32 (a float64 reading on a float32-feed card keeps its
    own digits). Callers use it only for `_FLOAT32_FEED_CARD_IDS`."""
    try:
        packed = struct.pack("<f", value)
    except OverflowError:
        return None
    if struct.unpack("<f", packed)[0] != value:
        return None
    return next(text for digits in range(1, 10)
                if struct.pack("<f", float(text := f"{value:.{digits}g}")) == packed)


def _source_number(value: float, *, float32_feed: bool = False) -> Decimal:
    """The number exactly as the source gave it: never padded, never rounded
    (Master.md: "only show what the source provided"). Only representation
    noise goes — float32 widening on a named float32 feed (`float32_feed`,
    whose noise can sit in any digit, whole-number ones too above 2**24), or
    float64 digits past the 15 a double holds faithfully (a derived
    1.2400000000000002 = 9.5 − 8.26, the Real Policy Rate). Any decimal of 15
    or fewer significant digits survives that cut unchanged; a whole-number
    float64 prints its own shortest decimal (never rounded into new digits).
    Printed by `_decimal_text` (plain notation, comma thousands, the minus glyph)
    via `_source_decimal`; cutting long tails for the screen is the SPA's job (lib/format.tsx cleanMetricValue, owner decision
    2026-08-29)."""
    if isinstance(value, int):
        text = str(int(value))  # int() also reads a bool as 1/0, as before
    elif float32_feed and (short := _float32_decimal(value)) is not None:
        text = short
    elif value.is_integer():
        text = repr(value)  # "100000008.0", "1e+20": never rounded into new digits
    else:
        text = f"{value:.{_FLOAT64_DIGITS}g}"
    return Decimal(text)


def _source_decimal(value: float, *, float32_feed: bool = False) -> str:
    """`_source_number` as card text (`_decimal_text`)."""
    return _decimal_text(_source_number(value, float32_feed=float32_feed))


def _decimal_text(number: Decimal) -> str:
    """Plain notation, comma thousands, no trailing zeros, the minus glyph."""
    whole, _, fraction = f"{abs(number):f}".partition(".")
    digits = f"{int(whole):,}" + (f".{fraction.rstrip('0')}" if fraction.rstrip("0") else "")
    return f"{_MINUS if number < 0 else ''}{digits}"


def _styled(number_text: str, unit: str, *, plus: bool = False) -> str:
    """The one house format around a `_decimal_text` number: the sign first (the
    minus glyph, or "+" for a non-zero rise when `plus` — a change figure), then
    the unit's prefix, the digits and the suffix (`_HOUSE_UNIT_STYLE`)."""
    negative = number_text.startswith(_MINUS)
    digits = number_text[1:] if negative else number_text
    sign = _MINUS if negative else ("+" if plus and digits != "0" else "")
    prefix, suffix = _HOUSE_UNIT_STYLE.get(unit, ("", f" {unit}" if unit else ""))
    return f"{sign}{prefix}{digits}{suffix}"


def _format_metric_value(value: Any, unit: str, metric_id: str | None = None) -> str:
    """Render a raw builder Metric's value as the card's display string, in the
    one house format (owner decision (g); R2 fix 7b round 1): the source's own
    decimal (`_source_decimal`) styled by its unit (`_HOUSE_UNIT_STYLE`) —
    "9.5%", "$37.3523bn", "−$3.31bn", "Tk 791.4875 cr", "103". An unmapped unit
    keeps the "<number> <unit>" fallback so a future metric still reconciles.
    `None` values (e.g. a metric the builder itself couldn't resolve) render as
    an em dash rather than the string "None" — and so do NaN/inf (R2 fix 7b),
    which `Metric` accepts and would otherwise print as "nan%": not a number
    anyone can read is an unknown reading. `metric_id` (the builder card id)
    selects float32 clean-up for `_FLOAT32_FEED_CARD_IDS` only (R2 fix 7b3)."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "—"
    if isinstance(value, (int, float)):
        return _styled(_source_decimal(value, float32_feed=metric_id in _FLOAT32_FEED_CARD_IDS), unit)
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
        if environment_paused():
            logger.info("Publication paused: alert suppressed: %s", message)
            return
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
        value=_format_metric_value(raw_metric.get("value"), raw_metric.get("unit") or "",
                                   raw_metric.get("id")),
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


def _enforce_observation_contract(
    final_brief: BriefPayloadV6,
    raw_sections: list[dict[str, Any]],
    *,
    model_output: bool = False,
    card_changes: dict[tuple[str, str], CardChange] | None = None,
) -> None:
    """Print every card's number from its builder observation; restore
    authoritative dates and held/release notes.

    R2 fix 16, owner decisions (h) and (i): each card's `delta`/`delta_pct` is set
    from `card_changes` (`_card_changes`, the builder's own dated history) or
    cleared — the model's change figures never survive a pass, and neither do
    those of a card with no builder counterpart. Bound summary pills are printed
    from their card; the banker-box runway survives only when it equals a checked
    builder figure (`_stamp_section_extras`).

    Owner decision (g), R2 fix 7b: the model chooses the cards, their labels
    and their commentary; it does not own their numbers. Each card's `value`
    is overwritten with the house format of the builder metric bound to its
    label in its OWN section (`_card_display_value`), so no number text the
    model wrote survives a pass. Replaces fix 7's parse-and-judge guard, whose
    word lists kept leaking. Unmatched labels are left to `_reconcile_metrics`.

    `model_output=True` marks the passes over model output (after the Editor, and
    after the Sub-editor + reconciliation). The model owns no `held_from` and no
    `next_print` there (editor_v6.txt: system-stamped): only a builder-stale card keeps
    a `held_from`, and every model `next_print` is cleared. Whether a
    fresh card wears an "As of" footer is left to the deterministic stamps that run
    next (`stamp_vintages`, `mark_held_overs`, `_stamp_remittance_sub`) — otherwise
    a model date on a fresh policy-corridor card published the writer-confirmation
    day as a held-over date. The default final pass runs after those stamps and
    only re-dates what they set to the builder observation.
    """
    raw_by_slug = {section["slug"]: section for section in raw_sections}
    raw_metrics = [m for section in raw_sections for m in section.get("metrics", []) or []]
    reprinted = 0
    for section in final_brief.sections:
        raw = raw_by_slug.get(section.slug, {})
        metrics = {_normalize_label(m["label"]): m for m in raw.get("metrics", [])}
        for metric in section.metrics:
            original = metrics.get(_normalize_label(metric.label))
            change = None if original is None else (card_changes or {}).get(
                (section.slug, original.get("id")))
            metric.delta, metric.delta_pct = change if change is not None else (None, None)
            if model_output:
                # Like `held_from`, the next-print footer is system-stamped (editor_v6.txt;
                # only `mark_held_overs` sets it, after these passes): a model one could
                # print a rejected figure or date beside a held card's "As of".
                metric.next_print = None
            if original is None:
                continue  # existing reconciliation rejects invented labels
            printed = _card_display_value(section, original)
            reprinted += metric.value != printed
            _carry_to_duplicate_pills(section, metric.value, printed)
            metric.value = printed
            observed = original.get("as_of")
            if observed:
                observed = date_t.fromisoformat(str(observed))
            # Model-supplied dates cannot override the builder's accepted observation,
            # and on model output they cannot create a held-over footer at all.
            keep_held = original.get("stale") or (metric.held_from and not model_output)
            metric.held_from = observed if keep_held else None
            source = original.get("source", "")
            if original.get("stale") or "provisional" in source.lower():
                prefix = "Held reading" if original.get("stale") else "Provisional reading"
                metric.sub = source if original.get("id") == "remit_monthly_mn" else " · ".join(filter(None, [prefix, original.get("period"), source]))
            elif is_press_card_source(source):
                # Owner decision (c): an approved press figure names its outlet; a model sub
                # crediting it to BB is replaced, never appended to.
                metric.sub = " · ".join(filter(None, [original.get("period"), source]))
        _stamp_section_extras(section, raw_by_slug.get(section.slug), raw_metrics)
    if reprinted:
        logger.info("v6: %d card value(s) re-printed from builder observations "
                    "(model number text discarded)", reprinted)


# R2 fix 7b, inventory §C: the builder's `headlines_count` is the scraped pool,
# but the card has always shown the curated list the reader sees beside it.
_HEADLINES_COUNT_ID = "headlines_count"


def _card_display_value(section: SectionV6, raw_metric: dict[str, Any]) -> str:
    """The number the pipeline prints on one card (owner decision (g)): the
    builder observation in the house format `_format_metric_value` — the same
    printer as protected-metric re-injection and the remittance stamp. The
    Headlines count card counts the headline items published in its own
    section; the model's count is never printed."""
    unit = raw_metric.get("unit") or ""
    if raw_metric.get("id") == _HEADLINES_COUNT_ID:
        return _format_metric_value(len(section.news), unit)
    return _format_metric_value(raw_metric.get("value"), unit, raw_metric.get("id"))


# Section.tsx hides a summary pill whose display key equals a same-section card
# value's: cleanMetricValue (lib/format.tsx — collapse "$$", truncate a 3+
# decimal tail to 2 unless that reads as zero) + trim + lowercase. Mirrored
# here with ASCII digit classes, as in JavaScript.
_SPA_LONG_DECIMAL = re.compile(r"^(\D*?)(-?[\d,]+)\.(\d{3,})(\D*)$", re.ASCII)


def _spa_display_key(value: str | None) -> str:
    collapsed = re.sub(r"\${2,}", "$", value or "")
    match = _SPA_LONG_DECIMAL.match(collapsed)
    if match:
        prefix, whole, frac, suffix = match.groups()
        if float(f"{whole.replace(',', '')}.{frac[:2]}") != 0:
            collapsed = f"{prefix}{whole}.{frac[:2]}{suffix}"
    return collapsed.strip().lower()


def _carry_to_duplicate_pills(section: SectionV6, model_text: str, printed: str) -> None:
    """A pill the SPA hid as a duplicate of this card's model text takes the
    card's printed text, so it stays hidden instead of resurfacing as an extra
    tile with the model's number. Other pills have no code source and keep
    their text (inventory §B). Empty text never counts as a duplicate."""
    key = _spa_display_key(model_text)
    if not key:
        return
    section.summary_pills = [
        pill.model_copy(update={"value": printed}) if _spa_display_key(pill.value) == key else pill
        for pill in section.summary_pills
    ]


# ── R2 fix 16, owner decisions (h) and (i): pills, change figures, runway ────
# (h) A summary pill restating a card of its OWN section prints that card's number.
# The binding is explicit, per concept: (section slug, pill key after
# `_normalize_label`) -> the builder card id. Listed: keys seen on real pages (issue
# 235, issues 199-205) that name exactly one card's measure in that section, plus
# their tenor siblings. Never bound: a key carrying a period ("NPL · Q1", "REMIT ·
# JUL" — the period is a claim code does not check), a composite ("BREADTH"), an
# ambiguous name ("CPI 12M": average or point-to-point?; "REAL RATE"; "PVT CREDIT":
# level or growth?) and another section's figure. Reasons per key:
# .superpowers/sdd/.../r2-claude/fix16-pill-bindings.md.
_PILL_CARD_BINDINGS: dict[tuple[str, str], str] = {
    ("headlines", "headlines"): "headlines_count",
    ("bb", "policy rate"): "bb_policy_rate",
    # BB money-market usage: "call money" is the overnight market; tenors are named.
    ("bb", "call money"): "bb_call_money",
    ("bb", "o/n call"): "bb_call_money",
    ("bb", "7d call"): "bb_call_money_7d",
    ("bb", "14d call"): "bb_call_money_14d",
    # The section's one reserves card is BB gross reserves (landmine 24); no net/BPM6 card.
    ("bb", "reserves"): "bb_gross_reserves",
    ("banking", "npl ratio"): "banking_npl_pct",
    ("banking", "car"): "banking_car_pct",
    ("fx", "usd/bdt"): "fx_usd_bdt_mid",
    ("fx", "reserves"): "fx_gross_reserves",
    ("fx", "gold"): "fx_gold_usd_oz",
    ("fx", "exports"): "fx_monthly_exports",
    ("fx", "trade gap"): "fx_trade_gap",
    ("dse", "dsex"): "dsex",
    ("dse", "turnover"): "dse_turnover_crore",
    ("tbond", "91d tbill"): "tbond_tbill_91d",
    ("tbond", "91d bill"): "tbond_tbill_91d",
    ("tbond", "182d tbill"): "tbond_tbill_182d",
    ("tbond", "182d bill"): "tbond_tbill_182d",
    ("tbond", "364d tbill"): "tbond_tbill_364d",
    ("tbond", "364d bill"): "tbond_tbill_364d",
    ("tbond", "5y bond"): "tbond_bond_5y",
    ("tbond", "10y bond"): "tbond_bond_10y",
    ("fiscal", "nbr ytd"): "fiscal_nbr_collected_trn",
    ("fiscal", "govt borrow"): "fiscal_govt_borrow_trn",
    ("macro", "cpi 12m avg"): "cpi_12m_avg_monthly",
    ("macro", "m2 yoy"): "m2_growth_yoy_monthly",
    ("macro", "real policy"): "real_policy_rate_monthly",
    ("iran", "brent"): "iranwar_brent_spot",
    ("iran", "wti"): "iranwar_wti_spot",
    ("remit", "remittance"): "remit_monthly_mn",
}


def _stamp_bound_pills(section: SectionV6, raw_by_id: dict[str, dict[str, Any]]) -> None:
    """Print each bound pill from its card's observation with the card's own
    printer (`_card_display_value`), so pill and card show one figure and the
    SPA merges them (spec §7.1). A bound pill whose card was not built today has
    no checked figure: it is removed, never printed from the model. Unbound
    pills keep the model's text."""
    kept: list[Any] = []
    for pill in section.summary_pills:
        metric_id = _PILL_CARD_BINDINGS.get((section.slug, _normalize_label(pill.key)))
        if metric_id is None:
            kept.append(pill)
        elif (raw_metric := raw_by_id.get(metric_id)) is not None:
            kept.append(pill.model_copy(update={"value": _card_display_value(section, raw_metric)}))
        else:
            logger.warning("v6: removed pill %s/%r: its card %s was not built today",
                           section.slug, pill.key, metric_id)
    section.summary_pills = kept


# (i) The banker-box runway: its number must be a plain decimal and, styled with a
# builder card's unit, show on screen what that card shows.
_RUNWAY_MAX_DIGITS = 40  # well past the 17 significant digits any source float carries
_PLAIN_NUMBER = re.compile(r"([−-]?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?", re.ASCII)


def _plain_number(text: str) -> Decimal | None:
    match = _PLAIN_NUMBER.fullmatch(text.strip())
    if match is None:
        return None
    sign, whole, fraction = match.groups()
    number = Decimal(whole.replace(",", "") + (fraction or ""))
    return -number if sign else number


def _runway_is_checked(runway: Any, raw_metrics: list[dict[str, Any]]) -> bool:
    """True when the runway's value+unit equal, after the house formatter and the
    SPA's screen cut, a checked builder figure anywhere in the brief (same unit)."""
    number = _plain_number(runway.value)
    if number is None:
        return False
    unit = _normalize_label(runway.unit)
    for raw_metric in raw_metrics:
        raw_unit = raw_metric.get("unit") or ""
        if raw_metric.get("id") == _HEADLINES_COUNT_ID or _normalize_label(raw_unit) != unit:
            continue  # the headlines card does not print its builder value (inventory §C)
        card = _format_metric_value(raw_metric.get("value"), raw_unit, raw_metric.get("id"))
        if (_spa_display_key(_styled(_decimal_text(number), raw_unit)) == _spa_display_key(card)
                and _is_source_truncation(number, raw_metric.get("value"), raw_metric.get("id"))):
            return True
    return False


def _is_source_truncation(number: Decimal, value: Any, metric_id: Any) -> bool:
    """True when `number` is the source's own decimal cut toward zero at `number`'s
    decimal places. BankerRead.tsx prints the runway uncut (`splitBigNum`), so every
    digit it shows past the screen cut must be the source's too: "4.972" of
    4.972006730098555 is, a rounded "4.979" is not (fix 16 round 1). The source's
    digits are the card's stamped decimal (`_source_number`) or, for a float64
    feed, the float's own shortest decimal (its 16th-17th digits are not noise
    there); a float32 feed's widened digits are noise, so only its stamp counts."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return False
    feed = metric_id in _FLOAT32_FEED_CARD_IDS
    sources = {_source_number(value, float32_feed=feed)}
    if isinstance(value, float) and not feed:
        sources.add(Decimal(repr(value)))
    places = Decimal(1).scaleb(number.as_tuple().exponent)
    try:
        with localcontext() as ctx:
            ctx.prec = _RUNWAY_MAX_DIGITS
            return any(source.quantize(places, rounding=ROUND_DOWN) == number for source in sources)
    except InvalidOperation:
        return False  # more digits than any source decimal carries


# (i) A card's change figures, computed from the builder's own dated history.
class CardChange(NamedTuple):
    delta: str
    delta_pct: str | None


# Units of a positive level, where a percent change means something. A % figure
# moves in percentage points (no percent-of-percent); counts and ratios get none.
_PCT_CHANGE_UNITS = frozenset({"index", "BDT", "USD/oz", "USD/bbl", "bn USD", "mn USD",
                               "crore BDT", "BDT trn"})


def _previous_reading(metric: Metric, source_pct: Decimal | None = None) -> float | None:
    """The previous observation before the card's `as_of`: the latest earlier
    history point, only when the history carries this card's own reading at its
    `as_of` (same series, same unit), only when that previous date holds one
    reading, and only when that point is proven the immediately previous one (no
    missing row bridged): by the source's own percent change for the card's
    session when one is at hand (`source_pct`, `_source_confirms`), otherwise by
    the card's cadence (`_is_immediately_previous`; for a monthly or quarterly
    card the preceding period, each period read once, so restamps in either
    month never count). Otherwise None — never a guess."""
    value = metric.value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    points = metric.history_points or []
    current = [p.value for p in points if p.as_of == metric.as_of]
    if not current or not all(math.isclose(v, value, rel_tol=1e-9) for v in current):
        return None
    earlier = [p for p in points if p.as_of < metric.as_of]
    if not earlier:
        return None
    last = max(p.as_of for p in earlier)
    readings = {p.value for p in earlier if p.as_of == last}
    if len(readings) != 1:
        return None
    previous = readings.pop()
    if source_pct is not None:
        return previous if _source_confirms(metric, previous, source_pct) else None
    return previous if _is_immediately_previous(metric, last, points) else None


# fix 16 round 1: the previous reading must be the one IMMEDIATELY before the card's, so a
# row missing from history is never bridged (a two-session move is not the day's change).
# daily: the calendar day before `as_of` (fix 16b: Bangladesh holds Saturday make-up
# sessions and public holidays, and no trading calendar is kept, so a gap of more than one
# day — a weekend, a holiday — is not provably one session and the change is hidden unless
# the source's own change confirms it, `_SOURCE_CHANGE_PCT_CARD`). weekly/event (the T-bill auctions): at
# most the cadence's 7-day fresh window earlier. monthly/quarterly: the preceding period,
# and each of the two periods read exactly once — a period-dated release; more than one
# reading in a period means its dates are restamps (landmine 24), not releases.
_MAX_GAP_DAYS = {"weekly": 7, "event": 7}
_MONTHS_PER_PERIOD = {"monthly": 1, "quarterly": 3}


# fix 16b: cards whose source publishes its own percent change for the same session. That
# figure says which close the day's move was measured from, so it is the arbiter of "the
# previous session" whatever the calendar gap: a computed change is shown only when it
# agrees within the source's own rounding (half a unit of its last decimal), never looser
# than the screen's 2-decimal cut. A missing Saturday session, a holiday gap or a
# restamped copy disagrees with it. card id -> its sibling card in the same section.
_SOURCE_CHANGE_PCT_CARD: dict[str, str] = {
    "dsex": "dse_dsex_change_pct",  # DSE's own "DSEX %Δ" for the session (dse.py, `dsex_change_pct`)
}
_SOURCE_PCT_MAX_SLACK = Decimal("0.005")  # half of the SPA's 2-decimal on-screen cut


def _source_confirms(metric: Metric, previous: float, source_pct: Decimal) -> bool:
    feed = metric.id in _FLOAT32_FEED_CARD_IDS
    now = _source_number(metric.value, float32_feed=feed)
    before = _source_number(previous, float32_feed=feed)
    if before <= 0:
        return False
    slack = min(Decimal(5).scaleb(source_pct.as_tuple().exponent - 1), _SOURCE_PCT_MAX_SLACK)
    return abs((now - before) / before * 100 - source_pct) <= slack


def _source_change_pct(metric: Metric, cards: dict[str, Metric]) -> Decimal | None:
    """The source's own percent change for the card's session: its bound sibling
    card, when that card is a finite number dated the card's own `as_of`."""
    sibling = cards.get(_SOURCE_CHANGE_PCT_CARD.get(metric.id, ""))
    if sibling is None or sibling.as_of != metric.as_of:
        return None
    value = sibling.value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return _source_number(value, float32_feed=sibling.id in _FLOAT32_FEED_CARD_IDS)


def _period_index(day: date_t, months: int) -> int:
    return (day.year * 12 + day.month - 1) // months


def _is_immediately_previous(metric: Metric, previous: date_t, points: list[Any]) -> bool:
    if metric.cadence == "daily":
        return previous == metric.as_of - timedelta(days=1)
    if metric.cadence in _MAX_GAP_DAYS:
        return (metric.as_of - previous).days <= _MAX_GAP_DAYS[metric.cadence]
    months = _MONTHS_PER_PERIOD.get(metric.cadence)
    if months is None:
        return False
    now, before = _period_index(metric.as_of, months), _period_index(previous, months)
    reads = [_period_index(p.as_of, months) for p in points]
    return before == now - 1 and reads.count(now) == 1 and reads.count(before) == 1


def _card_change(metric: Metric, source_pct: Decimal | None = None) -> CardChange | None:
    """Current minus previous in the card's house unit style (+ or the minus glyph;
    a % figure in pp), and the percent change for a positive level only. Both
    readings are the source's own decimals (`_source_number`), so float noise never
    becomes a digit. The Headlines count card prints a count of the page, not its
    builder value, so it never has a change."""
    previous = None if metric.id == _HEADLINES_COUNT_ID else _previous_reading(metric, source_pct)
    if previous is None:
        return None
    feed = metric.id in _FLOAT32_FEED_CARD_IDS
    now = _source_number(metric.value, float32_feed=feed)
    before = _source_number(previous, float32_feed=feed)
    change = now - before
    delta = _styled(_decimal_text(change), "pp" if metric.unit == "%" else metric.unit, plus=True)
    if metric.unit not in _PCT_CHANGE_UNITS or before <= 0 or now < 0:
        return CardChange(delta, None)
    ratio = change / before * 100
    with localcontext() as ctx:
        ctx.prec = _FLOAT64_DIGITS  # a computed ratio: 15 digits, the SPA cuts for the screen
        ratio = +ratio
    return CardChange(delta, _styled(_decimal_text(ratio), "%", plus=True))


def _card_changes(sections: list[SectionData]) -> dict[tuple[str, str], CardChange]:
    """(section slug, builder card id) -> the card's change, for every card whose
    own history supports one. Built once from the gathered sections (their
    `history_points` come from the single batched history read, landmine 23)."""
    changes: dict[tuple[str, str], CardChange] = {}
    for section in sections:
        if section.id not in V5_TO_V6:
            continue
        slug = V5_TO_V6[section.id][0]
        cards = {m.id: m for m in section.metrics}
        for metric in section.metrics:
            if (change := _card_change(metric, _source_change_pct(metric, cards))) is not None:
                changes[(slug, metric.id)] = change
    return changes


def _stamp_section_extras(section: SectionV6, raw: dict[str, Any] | None,
                          raw_metrics: list[dict[str, Any]]) -> None:
    """Bound pills from their cards (removed when no card stands behind them);
    the runway only when it equals a checked builder figure of the brief."""
    # A section the builders did not produce has no card behind a bound pill: those are
    # removed like a missing card (fix 16 round 1); unbound pills keep the model's text.
    _stamp_bound_pills(section, {m.get("id"): m for m in (raw or {}).get("metrics", []) or []})
    read = section.banker_read
    if read is not None and read.runway is not None and not _runway_is_checked(read.runway, raw_metrics):
        logger.info("v6: cleared runway %r %r in %s: no checked builder figure",
                    read.runway.value, read.runway.unit, section.slug)
        read.runway = None


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
# Review round 2026-08-27: both stampers match labels with `_normalize_label`,
# the SAME normalization `_reconcile_metrics` and the prose-number validator
# already use. Exact `!=` was a real hole: `_reject_invented_and_dedupe` keeps
# the EDITOR'S casing, so an editor writing "Import cover" got no stamp at all
# — and for Real Policy Rate that was doubly bad, because the validator's
# source-marker exemption still fired, leaving the sub both unstamped AND
# unchecked. Constants are pre-normalized so the comparison stays cheap.
_IMPORT_COVER_LABEL = _normalize_label("Import Cover")


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
    the EXACT note (never double-appends on a re-run; keyed on the full
    note, not the bare marker — editor prose can contain the marker phrase,
    which is how issue 210 lost the sibling stamp).
    """
    note: str | None = None
    for s in raw_sections:
        if s.get("slug") != "macro":
            continue
        for m in s.get("metrics", []) or []:
            if (
                _normalize_label(str(m.get("label") or "")) != _IMPORT_COVER_LABEL
                or m.get("value") is None
            ):
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
            if _normalize_label(pub.label) != _IMPORT_COVER_LABEL:
                continue
            current = pub.sub or ""
            # Idempotence keys on the EXACT note, never the bare marker: the
            # editor's own prose can legitimately contain the marker phrase
            # (issue 210's "repo above p2p CPI" skipped the sibling stamp
            # this way, 2026-08-28), and only the full note proves the
            # disclosure is already on the page.
            if note not in current:
                pub.sub = f"{current} · {note}" if current else note
        break


def _stamp_remittance_sub(
    final_brief: BriefPayloadV6, raw_sections: list[dict[str, Any]]
) -> None:
    """Keep the builder's remittance period/status after model validation.

    Replace the model's sub rather than appending contradictory month/finality
    prose. Label matching is normalized like the other deterministic stampers.
    """
    raw = next((m for section in raw_sections if section.get("slug") == "remit"
                for m in section.get("metrics", []) or []
                if m.get("id") == "remit_monthly_mn" and m.get("value") is not None), None)
    if raw is None:
        return
    note = raw.get("source") or ""
    if not note.startswith("BB · "):
        return
    for section in final_brief.sections:
        if section.slug != "remit":
            continue
        for pub in section.metrics:
            if _normalize_label(pub.label) == _normalize_label(str(raw.get("label") or "")):
                # The provenance and number are one observation: restore the
                # builder value with its verified unit before attaching the note.
                pub.value = _format_metric_value(raw["value"], raw.get("unit") or "", raw.get("id"))
                pub.sub = note
                # Runs after generic catalog/vintage passes: the source period
                # wins, and no source here verifies a next-release schedule.
                pub.held_from = (date_t.fromisoformat(str(raw["as_of"])[:10])
                                 if raw.get("stale") else None)
                pub.next_print = None


# The marker substring `macro._real_policy_rate`'s provenance note, this
# stamper and the published `sub` are all checked against, so a re-run never
# double-appends. Mirrors `_IMPORT_COVER_SUB_MARKER` exactly.
_REAL_POLICY_RATE_SUB_MARKER = "p2p CPI"
_REAL_POLICY_RATE_LABEL = _normalize_label("Real Policy Rate")


def _stamp_real_policy_rate_sub(
    final_brief: BriefPayloadV6, raw_sections: list[dict[str, Any]]
) -> None:
    """Force the published Real Policy Rate metric's `sub` to show its own
    arithmetic — which repo rate, minus which CPI print (2026-08-26).

    Same mechanism as `_stamp_import_cover_sub`, and for the same reason:
    `MetricV6` has no `source` field, so the builder's note (set on the RAW
    metric's `source` by `macro._real_policy_rate`) is dropped the moment the
    editor's output is validated. `sub` is the only free-text field that
    reaches the reader.

    Why this metric needs it. Real Policy Rate is the one macro figure whose
    published number appears NOWHERE in its own inputs: the reader sees
    "1.2%" and has no way to tell whether the repo leg was the pre-cut 10.00
    or the post-cut 9.50 — which is exactly the 50bp error the 2026-08-26
    review found live in production. Printing "9.50% repo − 8.32%
    Jul p2p CPI" beside it makes the same class of mistake self-evident on
    the page instead of only in the builder.

    The note is read from the BUILDER's raw output every run, never
    hardcoded, so it always names the leg the restamp-lag guard actually
    resolved. A no-op when the raw metric has no value (a leg was missing
    this issue), when its `source` carries no note (the derivation did not
    take its success path), or when the published `sub` already contains the
    EXACT note (keyed on the full note, not the bare marker — issue 210's
    editor sub "Jul 2026, repo above p2p CPI." contained the marker and the
    old check skipped the stamp, publishing 1.18 with no provenance).
    """
    note: str | None = None
    for s in raw_sections:
        if s.get("slug") != "macro":
            continue
        for m in s.get("metrics", []) or []:
            if (
                _normalize_label(str(m.get("label") or "")) != _REAL_POLICY_RATE_LABEL
                or m.get("value") is None
            ):
                continue
            src = m.get("source") or ""
            if "repo" in src and _REAL_POLICY_RATE_SUB_MARKER in src:
                # Strip the leading source prefix and trailing bracket:
                # "BB+BBS (9.50% repo − 8.32% Jul p2p CPI)" → the inner note.
                # The closing bracket (when later than the marker) keeps a
                # press leg's trailing "via <outlet> (approved)" — decision (c).
                start = src.find("(") + 1
                end = max(src.find(_REAL_POLICY_RATE_SUB_MARKER) + len(
                    _REAL_POLICY_RATE_SUB_MARKER
                ), src.rfind(")"))
                if start > 0 and end > start:
                    note = src[start:end]
        break

    if not note:
        return

    for section in final_brief.sections:
        if section.slug != "macro":
            continue
        for pub in section.metrics:
            if _normalize_label(pub.label) != _REAL_POLICY_RATE_LABEL:
                continue
            current = pub.sub or ""
            # Exact-note idempotence — see _stamp_import_cover_sub. This is
            # the issue-210 fix: the editor wrote "Jul 2026, repo above p2p
            # CPI." and the old marker-substring check read that as already-
            # stamped, so the corrected 1.18 published with no provenance.
            if note not in current:
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


# Issues 207/208: the digest exposed only first/last/min/max, so an editor
# asked for "a year earlier" reached for the only backward-looking number it
# had — `first_value`, the START of the window. On `cpi_12m_avg_monthly` that
# is a 24-MONTH-old figure (9.95, Aug 2024) printed as a 12-month-old one; the
# true year-ago point was 9.77 (Jul 2025). The window start and the year-ago
# point are different facts, and the digest now carries both.
#
# Real monthly series are stamped month-START or month-END inconsistently, so
# an exact 365-day hit is not guaranteed — the nearest point inside this
# tolerance counts, and anything outside it yields NO year-ago point at all.
# Substituting the nearest-available point on a short window would recreate
# exactly the misread this field exists to end.
_YEAR_AGO_TOLERANCE_DAYS = 45


def _point_field(p: Any, name: str) -> Any:
    """One field off a SeriesPointV6-like object — an attribute on the model,
    a key on a plain dict. Shared by every series reducer below."""
    return getattr(p, name) if hasattr(p, name) else p[name]


def _coerce_ts(raw: Any) -> date_t | None:
    """A series point's `ts` as a date — accepts the ISO strings the fetchers
    emit and a bare `date`, returns None for anything unparseable."""
    if isinstance(raw, date_t):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return date_t.fromisoformat(raw[:10])
    except ValueError:
        return None


def _prior_year_point(
    ordered: list[Any], last_ts: Any, get: Any
) -> tuple[Any, Any] | None:
    """`(value, ts)` for the point closest to ONE YEAR before `last_ts`, or
    None when the window does not reach back that far (nearest candidate more
    than `_YEAR_AGO_TOLERANCE_DAYS` off) or the timestamps are unparseable."""
    newest = _coerce_ts(last_ts)
    if newest is None:
        return None
    target = newest - timedelta(days=365)

    best: Any = None
    best_gap: int | None = None
    for p in ordered:
        stamped = _coerce_ts(get(p, "ts"))
        if stamped is None:
            continue
        gap = abs((stamped - target).days)
        if best_gap is None or gap < best_gap:
            best, best_gap = p, gap

    if best is None or best_gap > _YEAR_AGO_TOLERANCE_DAYS:
        return None
    return get(best, "value"), get(best, "ts")


def summarize_series_points(points: list[Any]) -> dict[str, dict[str, Any]]:
    """Reduce a flat list of SeriesPointV6-like objects (`.key`/`.ts`/`.value`
    attributes, or dicts with the same keys) into a compact per-series-key
    digest: `{n, first_ts, first_value, last_ts, last_value, min, max,
    value_1y_ago, ts_1y_ago}`.

    `value_1y_ago`/`ts_1y_ago` (issues 207/208) are the point nearest one year
    before `last_ts`, both None when the window does not reach back a year —
    see `_prior_year_point`. They exist so "a year earlier" has an honest
    number to cite that is NOT the window's `first_value`.

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
    _get = _point_field
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
        last_ts = _get(ordered[-1], "ts")
        year_ago = _prior_year_point(ordered, last_ts, _get)
        out[key] = {
            "n": len(ordered),
            "first_ts": _get(ordered[0], "ts"),
            "first_value": values[0],
            "last_ts": last_ts,
            "last_value": values[-1],
            "min": min(values),
            "max": max(values),
            "value_1y_ago": year_ago[0] if year_ago else None,
            "ts_1y_ago": year_ago[1] if year_ago else None,
        }
    return out


# ─── dse session-low anchor (issues 205-208) ──────────────────────────────
# `dse` is the one charted section that emits NO `history_facts`, so when the
# editor wanted a "lowest since" line it had nothing to inline verbatim and
# invented one: "a ten-session low" appeared BYTE-IDENTICAL across issues
# 205, 206, 207 and 208 while the real rank moved 38 -> 41 -> 42. The
# hyphenated count-claim catcher in `brief/validators/prose_numbers.py` sees
# it, but only WARNs — a catcher is not a source.
#
# The rank is computable from the dsex point array the pipeline ALREADY
# fetches for the dse digest, so this costs no extra request (landmine 23's
# spirit: one fetch, many uses). It is emitted as a `HistoryFact`, in the same
# shape `macro.py` produces, so it rides the existing history-facts-verbatim
# contract through `_to_v6_raw` — no editor-prompt change is needed.
#
# Both guards come from `history_anchors` rather than fresh constants, because
# they encode the same judgement: LOOKBACK_MIN (a rank under 3 is degenerate —
# it fires on any single-session move) and MIN_DATA_POINTS["daily"] (under 30
# points a "since" claim is nominal, not statistical). A window LOW produces
# NO fact at all — never a fabricated rank.
_DSEX_SERIES_KEY = "dsex"


def _sessions_since_lower(ordered: list[Any], get: Any) -> int | None:
    """How many points back from the newest the most recent LOWER value sits.

    `ordered` must be ascending by ts. Returns 1 when the immediately
    preceding point is lower, and None when NO point in the window is lower —
    i.e. the newest value is the window low, which is a fact this function
    deliberately refuses to rank.
    """
    if len(ordered) < 2:
        return None
    current = get(ordered[-1], "value")
    if not isinstance(current, (int, float)):
        return None
    for back, point in enumerate(reversed(ordered[:-1]), start=1):
        value = get(point, "value")
        if isinstance(value, (int, float)) and value < current:
            return back
    return None


def _dsex_session_low_fact(points: list[Any]) -> Any | None:
    """A `HistoryFact` naming how many sessions back the last lower DSEX close
    sits, or None when the window is too short, the rank is degenerate, or the
    newest close is the window low. See the block comment above."""
    from brief.history_anchors import LOOKBACK_MIN, MIN_DATA_POINTS, HistoryFact

    ordered = [
        p for p in sorted(points, key=lambda p: _point_field(p, "ts"))
        if _point_field(p, "value") is not None
    ]
    if len(ordered) < MIN_DATA_POINTS["daily"]:
        return None

    rank = _sessions_since_lower(ordered, _point_field)
    if rank is None or rank < LOOKBACK_MIN:
        return None

    prior = ordered[-1 - rank]
    prior_value = float(_point_field(prior, "value"))
    prior_date = _coerce_ts(_point_field(prior, "ts"))
    if prior_date is None:
        return None

    formatted = f"{prior_value:,.2f}"
    return HistoryFact(
        metric_id=_DSEX_SERIES_KEY,
        kind="since_lower",
        phrase=(
            f"a {rank}-session low ({formatted} on "
            f"{prior_date:%d %b} the last lower close)"
        ),
        reference_value=prior_value,
        reference_value_formatted=formatted,
        reference_as_of=prior_date.isoformat(),
    )


def _fetch_series_summaries(
    *,
    today: date_t,
    http: HttpClient,
    supabase_url: str,
    service_key: str,
    history_facts_out: dict[str, list[Any]] | None = None,
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

    `history_facts_out` (issues 205-208) is an OUT-parameter, filled with
    `{slug: [HistoryFact, ...]}` for facts derivable from the series fetched
    here — today just the dse session-low anchor. An out-parameter rather than
    a second return value so this function's own return SHAPE stays exactly
    what every existing caller and test already reads; the caller forwards the
    collected facts to `_build_editor_input`, which merges them into the raw
    sections' existing `history_facts` field. Omit it (the default) and no
    facts are computed at all.
    """
    from brief.history import MetricHistoryClient as _MetricHistoryClient

    history_monthly_client = _MetricHistoryClient(
        url=supabase_url, service_key=service_key, http=http,
    )
    out: dict[str, dict[str, dict[str, Any]]] = {}

    for slug, fn_name in _SUMMARY_MONTHLY_FETCHERS.items():
        try:
            fn = getattr(chart_series_fetcher, fn_name)
            series_by_id = (fn(history_monthly_client) if slug == "tbond"
                            else fn(history_monthly_client, today=today))
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
        if history_facts_out is not None:
            # Same point array the digest above was built from — no second fetch.
            session_low = _dsex_session_low_fact(dsex_series)
            if session_low is not None:
                history_facts_out.setdefault("dse", []).append(session_low)
    except Exception:  # noqa: BLE001 — graceful degradation
        logger.warning("v6: series_summary pre-fetch failed for slug=dse", exc_info=True)

    try:
        brent_series = chart_series_fetcher.fetch_brent(
            http=http, supabase_url=supabase_url, service_key=service_key, today=today,
        )
        out["iran"] = summarize_series_points(brent_series)
    except Exception:  # noqa: BLE001 — graceful degradation
        logger.warning("v6: series_summary pre-fetch failed for slug=iran", exc_info=True)

    # banking (DOMMR/BOFR overnight rates) is the third daily HTTP fetcher —
    # one batched fetch, digested per key (dommr + bofr), mirroring how the
    # bb reserves digest carries its two monthly keys. The editor's chart_read
    # should lead on the PRIMARY series (dommr) per the existing convention.
    try:
        mm_series = chart_series_fetcher.fetch_money_market(
            http=http, supabase_url=supabase_url, service_key=service_key, today=today,
        )
        out["banking"] = summarize_series_points(mm_series)
    except Exception:  # noqa: BLE001 — graceful degradation
        logger.warning("v6: series_summary pre-fetch failed for slug=banking", exc_info=True)

    return out


# ─── Phase E.2 — chart series enricher ────────────────────────────────
# Per-slug chart fetcher dispatch. Sections not in this map skip chart_series
# stamping (frontend hides the chart slot when series is empty). The values
# correspond to function names on the `chart_series_fetcher` module — we look
# them up dynamically so test monkeypatching just works.
_CHART_FETCHERS_BY_SLUG: dict[str, str] = {
    "dse": "dsex",
    "iran": "brent",
    # §04 Banking DOMMR/BOFR overnight money-market two-line chart — a daily
    # metric_history fetcher, so it rides the generic HTTP dispatch below
    # (list-returning else branch, same as brent).
    "banking": "money_market",
    # fx moved to the metric_history_monthly External Flow Balance branch (F3);
    # fetch_fx_flows is retained (unit-tested) but no longer slug-dispatched.
    # tbond moved to the metric_history_monthly yield-ladder branch (F5);
    # fetch_yield_curve is retained (unit-tested) but no longer slug-dispatched.
}

# Every slug `_stamp_chart_series` fetches a chart for: its six
# metric_history_monthly branches (mirrored by `_SUMMARY_MONTHLY_FETCHERS`)
# plus the HTTP dispatch map above. Used only to NAME chartless sections in logs.
_CHARTABLE_SLUGS: frozenset[str] = (
    frozenset(_SUMMARY_MONTHLY_FETCHERS) | frozenset(_CHART_FETCHERS_BY_SLUG)
)


def _discard_model_chart_data(final_brief: BriefPayloadV6) -> list[str]:
    """R2 fix 6: the model may not supply chart data.

    `series`, `notes` and `movers` are machine-stamped AFTER the model runs.
    editor_v6.txt says `series`/`notes` are "ALWAYS empty in your output", and
    the model is never given the chart points or the DS30 movers at all, so
    anything the Editor or the Sub-editor put there is invented by
    construction. Clear it on every section before stamping, so only
    `_stamp_chart_series` output can publish — including when a fetch raises
    or credentials are missing. Returns the slugs that carried model data.

    Review round 1: a card's `spark` (the SPA's per-card sparkline) is chart
    data too. No deterministic code stamps it, so any non-empty `spark` is
    model-sourced; it is cleared to None (the SPA's "no sparkline" state).
    """
    dirty = [
        s.slug for s in final_brief.sections
        if s.series or s.notes or s.movers is not None or any(m.spark for m in s.metrics)
    ]
    for section in final_brief.sections:
        section.series = []
        section.notes = []
        section.movers = None
        section.metrics = [_without_spark(m) for m in section.metrics]
    if dirty:
        logger.warning(
            "v6: discarded model-supplied chart data (series/notes/movers/spark) "
            "for slug(s) %s — only machine-stamped chart data may publish",
            ", ".join(dirty),
        )
    return dirty


def _without_spark(metric: MetricV6) -> MetricV6:
    """The card unchanged except for no sparkline (a copy, never an in-place edit)."""
    return metric if metric.spark is None else metric.model_copy(update={"spark": None})


def _log_chartless_sections(final_brief: BriefPayloadV6, reason: str) -> None:
    """Name every chartable section that will publish with an empty chart, and
    why. The chart is dropped, never the brief (see `run_publish`)."""
    missing = [
        s.slug for s in final_brief.sections
        if s.slug in _CHARTABLE_SLUGS and not s.series
    ]
    if missing:
        logger.warning(
            "v6: slug(s) %s ship with no chart series — %s", ", ".join(missing), reason,
        )


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
    whole publish. Any series/notes/movers already on the brief (i.e. written
    by the model) are discarded first (R2 fix 6), so a failed fetch can never
    leave model points standing in for the chart.
    """
    from brief.history import MetricHistoryClient as _MetricHistoryClient
    history_monthly_client = _MetricHistoryClient(
        url=supabase_url, service_key=service_key, http=http,
    )
    _discard_model_chart_data(final_brief)

    for section in final_brief.sections:
        # v1.4.0 — macro CPI trend chart uses metric_history_monthly
        if section.slug == "macro":
            try:
                series_by_id = chart_series_fetcher.fetch_macro_cpi_series(history_monthly_client, today=today)
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
                series_by_id = chart_series_fetcher.fetch_remit_monthly(history_monthly_client, today=today)
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
                series_by_id = chart_series_fetcher.fetch_reserves_monthly(history_monthly_client, today=today)
                section.series = [pt for pts in series_by_id.values() for pt in pts]
            except Exception:  # noqa: BLE001 — graceful degradation
                logger.warning(
                    "v6: reserves series fetch failed for slug=bb",
                    exc_info=True,
                )
            continue

        # F5 — §tbond full yield ladder, last 3 months (metric_history_monthly).
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
            # The chart's bottom footnote ("built from auctions through …").
            # Its OWN try/except, deliberately: the footnote is a caption, and
            # losing it must never cost us the curve that just fetched fine.
            try:
                note = chart_series_fetcher.fetch_yield_ladder_last_auction(history_monthly_client)
                if note is not None:
                    section.notes = [*(section.notes or []), note]
            except Exception:  # noqa: BLE001 — graceful degradation
                logger.warning(
                    "v6: yield-ladder last-auction note fetch failed for slug=tbond",
                    exc_info=True,
                )
            continue

        # F3 — §fx External Flow Balance, last 24 months (metric_history_monthly).
        # Replaces the daily fetch_fx_flows path (fx removed from the HTTP map below).
        if section.slug == "fx":
            try:
                series_by_id = chart_series_fetcher.fetch_fx_balance_monthly(history_monthly_client, today=today)
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
                series_by_id = chart_series_fetcher.fetch_fiscal_monthly(history_monthly_client, today=today)
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

    _log_chartless_sections(
        final_brief, "chart fetch failed or returned no points (see warnings above)",
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
        # Second-precision stamps collide when two failures land inside the same
        # second, and the whole point of dumping per attempt is that attempt 2's
        # evidence must not erase attempt 1's. Suffix rather than overwrite.
        suffix = 2
        while path.exists():
            path = log_dir / f"{label}_raw_{stamp}-{suffix}.txt"
            suffix += 1
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
                    "messages — stitched into %d chars (output_tokens=%s of which "
                    "thinking=%s). The per-response ceiling covers thinking too; "
                    "compare the two before assuming the brief itself is too long.",
                    label, result.assistant_messages, len(result.raw_text or ""),
                    result.tokens.get("output"), result.tokens.get("thinking"),
                )
            if result.parsed is None:
                # Dump BEFORE raising. `_LAST_RAW[label]` was set two lines up
                # and the next attempt overwrites it, so an un-dumped failure is
                # gone for good — and the parse-failure path never called the
                # dumper at all, only the schema-validation path below did. On
                # 2026-08-23 two editor attempts died here with the full 32.5 KB
                # response sitting in that stash; all that survived was the 200
                # chars below, which are the same `{"brief": {"issue_no": ...`
                # preamble on every attempt and say nothing about WHERE the JSON
                # broke. Truncation failures are diagnosable only from the tail.
                dump = _dump_raw_on_failure(label)
                raise V6PublishError(
                    f"{label}: result.parsed is None "
                    f"(raw_len={len(result.raw_text or '')}, "
                    f"assistant_messages={result.assistant_messages}, "
                    f"output_tokens={result.tokens.get('output')} of which "
                    f"thinking={result.tokens.get('thinking')}, "
                    f"full response saved to {dump or 'nowhere — nothing stashed'}; "
                    f"tail: {(result.raw_text or '')[-200:]!r})"
                )
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
      - `_call_with_retries` rides out transient Anthropic failures (529
        "Overloaded" spells at the 04:00-06:00 BDT window; AGENTS.md #13, #120).
        2026-06-22 (issue 144): the sub-editor lost a whole edition to a 529 spell
        that 3 quick retries couldn't outlast — hence the longer backoff.

        The per-attempt timeout was 600s until 2026-08-27, when issue 209 was lost
        to FIVE consecutive 600s timeouts. That was not a transient spell: the
        deadline had been set at roughly the job's own median runtime, so about
        half of all attempts were failing by construction. Measured successes:
        589.2s (issue 207), 585.9s (issue 208) — 98% and 97.7% of the 600s budget.
        A retry cannot rescue a call that is slow rather than broken, so five
        attempts at a too-short deadline bought nothing; the fix is headroom, not
        more tries.

        Sized against brief.service's 90-min TimeoutStartSec: 3 x 1200s plus the
        15s + 45s backoff is 61 min, which leaves ~18 min of margin after a
        typical ~11-min editor draft. Raising attempts back to 5 at this timeout
        does NOT fit (103 min) — it needs TimeoutStartSec raised first.

        Two known gaps deliberately left alone here, because neither was the
        failure mode and both want their own change: the editor gets 1800s for a
        job that measures 530-670s (over-generous where this one was starved),
        and the malformed-review loop below can run `_call_with_retries` twice,
        so the true worst case is 2 x 61 min and already exceeded the systemd cap
        before this change.
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
            timeout_s=1200,
            attempts=3,
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
    count-claim anywhere in the brief (`check_count_claims` — the only
    UNCONDITIONAL BLOCK post-round-2 review, corpus-verified 14/14 TP, 0 FP;
    P2 fact-checker, 2026-08-22 audit #204), OR a hyphenated-attributive
    count-claim in a block-scoped section that matches no machine-fed history
    fact (`check_hyphenated_count_claims` + `_HYPHENATED_COUNT_BLOCK_SLUGS`,
    owner-approved 2026-08-28), OR — only when
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


# Refused-figure lines listed in the grouped alert: at most 10, and fewer when their length would
# push the closing "N more" line past Discord's 1990-char cut (`alerts._MAX_CONTENT`); a real
# refused line runs ~150-190 chars (R2 fix C1, round 1).
_MAX_REFUSED_ALERT_LINES = 10


def _refused_alert_lines(refused: list[_prose_numbers.NumberWarning], head: str) -> list[str]:
    """The refused group's listed lines plus, when any are left out, ONE line counting them —
    the longest such run whose every line arrives whole after `head` inside `alerts._MAX_CONTENT`."""
    from brief.alerts import _MAX_CONTENT

    listed = [f"    {w.describe()}" for w in refused[:_MAX_REFUSED_ALERT_LINES]]
    while True:
        not_listed = len(refused) - len(listed)
        more = ([(f"    … and {not_listed} more refused or undated figure(s) not listed here "
                  "(each is in the brief log)")] if not_listed > 0 else [])
        if not listed or len(head) + len("\n".join(["", *listed, *more])) <= _MAX_CONTENT:
            return [*listed, *more]
        listed = listed[:-1]


def _format_prose_number_alert(warnings: list["_prose_numbers.NumberWarning"]) -> str:
    """One Discord message for ALL of this issue's WARN-mode figures, grouped
    by section (H3, round-2 review item 6) — a publish with N warnings used
    to send N separate Discord messages, which drowns the channel on a bad
    day and reads as N unrelated incidents instead of one. Truncation to
    Discord's 2000-char cap is `alerts.send_discord_alert`'s job; this only
    shapes the content.

    R2 fix H6 review r1: the refused-figure lines are listed FIRST, under their own heading and
    once each (not again in their section), because a real day's grouped alert runs 4k-14k chars
    and Discord is sent only the first `alerts._MAX_CONTENT`; appended last, the one signal H6
    adds was cut off. The header count still covers every warning.

    R2 fix C1: the refused group lists at most `_MAX_REFUSED_ALERT_LINES` and closes with ONE
    line counting the rest; beyond ~12 lines the 1990-char cut dropped the later ones silently.
    Round 1: the count is by characters too (`_refused_alert_lines`), because the producer's real
    'unavailable (as of …)' reason makes lines long enough that 10 of them pushed the count line
    past the cut."""
    refused = [w for w in warnings if w.kind == _prose_numbers.REFUSED_FIGURE_KIND]
    by_section: dict[str, list["_prose_numbers.NumberWarning"]] = {}
    for w in warnings:
        by_section.setdefault(w.section, []).append(w)
    lines = [f"WARN: The Brief prose-number gate — {len(warnings)} figure(s) across {len(by_section)} section(s):"]
    if refused:
        lines.append(f"  [refused or undated today — {len(refused)} figure(s)]")
        lines.extend(_refused_alert_lines(refused, "\n".join(lines)))
    for section, all_section_warnings in by_section.items():
        section_warnings = [w for w in all_section_warnings if w.kind != _prose_numbers.REFUSED_FIGURE_KIND]
        if not section_warnings:
            continue
        lines.append(f"  [{section}]")
        for w in section_warnings:
            lines.append(f"    {w.describe()}")
    return "\n".join(lines)


# Issue 206 regression (defect a+b net): a section's own DAILY metric must
# not silently disagree with the newest point its OWN plotted chart series
# shows for the SAME series key. On 24 Aug the DSEX close tile carried
# as_of=2026-08-24 (the RUN date — dse.py's own bug, fixed separately) while
# the section's chart_read (driven by series_summary.last_ts) correctly said
# 23 Aug — two contradictory dates in one section, and nothing checked that
# they agreed.
#
# WARN-mode is deliberate, not provisional-by-oversight: a chart series can
# legitimately lag its metric by one session (EconDelta's aggregate and this
# pipeline's series_summary pre-fetch are two independent fetches ~10-15
# minutes apart — see `_fetch_series_summaries`'s docstring), and BLOCKing on
# that would fail the 08:00 BDT publish on an ordinary day. Promote to BLOCK
# only after WARN-log volume in production shows a near-zero false-positive
# rate, matching the staging discipline `check_count_claims` already earned
# (AGENTS.md landmine 34) — this constant exists so that decision is a single
# documented flip, not a rewrite.
_PROMOTE_AS_OF_VS_SERIES_WARN_TO_BLOCK = False


def _check_daily_as_of_vs_series_summary(
    raw_sections: list[dict[str, Any]],
) -> list[str]:
    """WARN-mode tripwire: for every DAILY-cadence metric, compare its own
    `as_of` against `last_ts` of the SAME series key in its section's
    `series_summary` digest (present on `raw_sections[i]["series_summary"]`
    since `_build_editor_input` stamps it — see item 3's tests above).

    Only checks metrics whose id has a matching series_summary key — a daily
    metric with no chart (or a digest fetch that degraded to `{}`) is simply
    skipped, since this is a disagreement check, not a presence check.
    Non-daily cadences are out of scope here by design: a monthly card's
    period legitimately differing from its chart's newest point is defect
    (4)'s concern (`prose_numbers.check_card_period_vs_chart_series`, also
    WARN-mode), not this tripwire's.

    Returns human-readable warning strings, never raises.
    """
    warnings: list[str] = []
    for s in raw_sections:
        slug = s.get("slug", "?")
        summary = s.get("series_summary") or {}
        for m in s.get("metrics", []):
            if m.get("cadence") != "daily":
                continue
            mid = m.get("id")
            digest = summary.get(mid)
            if not digest:
                continue
            last_ts = digest.get("last_ts")
            as_of = m.get("as_of")
            if not last_ts or not as_of or last_ts == as_of:
                continue
            warnings.append(
                f"{slug}.{mid}: metric as_of={as_of} disagrees with its own "
                f"plotted chart series' newest point last_ts={last_ts}"
            )
    return warnings


# R2 fix 6: a card and its OWN section's chart must not print two numbers for
# the same concept and the same date. Checked against the FINAL stamped
# series (the tripwire above only sees the pre-editor digest). Only pairs
# where the card and the chart provably read the same series for the same
# period are listed; ambiguous pairs (reserves daily-vs-monthly writer, T-bill
# cut-off vs monthly ladder, NBR FYTD vs single-month revenue) are left to
# the owner — see the fix-6 report. WARN-mode, like the sibling above:
# numbers are never rewritten and the publish is never held on a chart.
class _CardChartPair(NamedTuple):
    chart_key: str                           # SeriesPointV6.key the fetcher stamps
    card_unit: str                           # builder unit the scale rule assumes
    point_to_card: Callable[[float], float]  # chart value -> card value


def _same_value(value: float) -> float:
    return value


def _usd_mn_to_bn_2dp(value: float) -> float:
    """fx.py: official mn USD row -> bn USD card, rounded to 2dp."""
    return round(value / 1000, 2)


_CARD_CHART_PAIRS: dict[tuple[str, str], _CardChartPair] = {
    ("macro", "cpi_12m_avg_monthly"): _CardChartPair("cpi_12m_avg_monthly", "%", _same_value),
    ("macro", "cpi_p2p_food_monthly"): _CardChartPair("cpi_p2p_food_monthly", "%", _same_value),
    ("macro", "cpi_p2p_nonfood_monthly"): _CardChartPair(
        "cpi_p2p_nonfood_monthly", "%", _same_value),
    ("fx", "fx_monthly_exports"): _CardChartPair(
        "exports_usd_mn_monthly", "bn USD", _usd_mn_to_bn_2dp),
    ("remit", "remit_monthly_mn"): _CardChartPair(
        "remittance_usd_mn_monthly", "mn USD", _same_value),
    ("dse", "dsex"): _CardChartPair("dsex", "index", _same_value),
    ("iran", "iranwar_brent_spot"): _CardChartPair("brent", "USD/bbl", _same_value),
}
# Float noise only: both sides are the same stored number, not two estimates.
_CARD_CHART_REL_TOL = 1e-6


def _card_chart_mismatch(
    section: SectionV6, raw: dict[str, Any], pair: _CardChartPair,
) -> str | None:
    """One card against its own chart's point(s) for the card's own date."""
    where = f"{section.slug}.{raw.get('id')}"
    value = raw.get("value")
    as_of = str(raw.get("as_of") or "")[:10]
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not as_of:
        return None
    if raw.get("unit") != pair.card_unit:
        return (f"{where}: card unit {raw.get('unit')!r} is not the {pair.card_unit!r} "
                f"this check assumes; cannot compare it with chart series {pair.chart_key!r}")
    points = [p.value for p in section.series
              if p.key == pair.chart_key and p.ts[:10] == as_of]
    wrong = [v for v in points if not math.isclose(
        pair.point_to_card(v), float(value), rel_tol=_CARD_CHART_REL_TOL, abs_tol=1e-9)]
    if not wrong:
        return None
    return (f"{where}: card value {value} for {as_of} disagrees with its own chart "
            f"series {pair.chart_key!r} point {wrong[0]} for the same date")


def _check_cards_against_stamped_series(
    final_brief: BriefPayloadV6, raw_sections: list[dict[str, Any]],
) -> list[str]:
    """For every PUBLISHED card in `_CARD_CHART_PAIRS`, compare the builder's
    value (the card's number, already bound by `_enforce_observation_contract`)
    with its own section's stamped chart point for the card's date. No point
    for that date is not a contradiction. Returns warnings; never raises."""
    raw_by_slug = {s.get("slug"): s for s in raw_sections}
    warnings: list[str] = []
    for section in final_brief.sections:
        raw_metrics = {
            _normalize_label(m.get("label") or ""): m
            for m in (raw_by_slug.get(section.slug) or {}).get("metrics", [])
        }
        for published in section.metrics:
            raw = raw_metrics.get(_normalize_label(published.label))
            pair = _CARD_CHART_PAIRS.get((section.slug, raw.get("id"))) if raw else None
            warning = _card_chart_mismatch(section, raw, pair) if pair else None
            if warning:
                warnings.append(warning)
    return warnings


def _run_card_chart_gate(
    final_brief: BriefPayloadV6, raw_sections: list[dict[str, Any]],
) -> list[str]:
    """Log + one grouped alert for card/chart contradictions (WARN-mode)."""
    warnings = _check_cards_against_stamped_series(final_brief, raw_sections)
    if not warnings:
        logger.info("v6 card-vs-chart gate: clean")
        return warnings
    for w in warnings:
        logger.warning("v6 card-vs-chart gate (WARN): %s", w)
    _alert(
        "WARN: The Brief card-vs-chart gate — "
        f"{len(warnings)} card(s) disagree with their own chart point for the "
        "same date (nothing rewritten, publish not held):\n"
        + "\n".join(f"  {w}" for w in warnings)
    )
    return warnings


def _refusal_reason(record: dict[str, Any]) -> str:
    quality = record.get("quality")
    said = f"marked {quality!r}" if quality not in ("verified", "held") else "published but the reader refused"
    return f"{said}, undated" if not record.get("as_of") else f"{said} (as of {record['as_of']})"


def _refused_figures(snapshot: Any, today: date_t) -> tuple[_prose_numbers.RefusedFigure, ...]:
    """R2 fix H6, owner decision (n): today's figures the producer refused or left undated —
    every record in the snapshot the builders were given (`GatheredSections.snapshot`) that the
    reader does not accept (`observation()` and `writer_confirmation()` both None: quality
    `unavailable`, no date, a future date, no evidence, or a value that disagrees with its
    scalar), with a finite value. A review-REJECTED quote is not among them: the producer drops
    a rejected family from latest.json before writing it (EconDelta aggregate_latest.py,
    granular-reject path: popped from `data`/`domains`, replaced by a dated held predecessor or
    omitted), so its value never reaches the Brief. No snapshot (a plain section list) -> ()."""
    from brief.history import finite_number

    observations = getattr(snapshot, "observations", None)
    if not isinstance(observations, dict):
        return ()
    refused = []
    for metric_id, record in sorted(observations.items()):
        if not isinstance(record, dict) or not finite_number(record.get("value")):
            continue
        if (snapshot.observation(metric_id, today=today) is not None
                or snapshot.writer_confirmation(metric_id, today=today) is not None):
            continue
        refused.append(_prose_numbers.RefusedFigure(
            metric_id=metric_id, value=float(record["value"]), reason=_refusal_reason(record)))
    return tuple(refused)


def _cover_card(final_brief: BriefPayloadV6, raw_sections: list[dict[str, Any]]
                ) -> tuple[SectionV6, dict[str, Any], MetricV6] | None:
    """The checked card the cover points to: its `section_slug` (the hero section when it names
    none), then the card whose label equals the cover's — whole, or before a " · " period tag
    ("NPL RATIO · Q4 2025") — and that has a builder observation."""
    cover = final_brief.brief.cover_metric
    slug = cover.section_slug or next((s.slug for s in final_brief.sections if s.weight == 2), None)
    section = next((s for s in final_brief.sections if s.slug == slug), None)
    raw = next((r for r in raw_sections if r.get("slug") == slug), None)
    if section is None or raw is None:
        return None
    wanted = {_normalize_label(cover.label), _normalize_label(cover.label.split(" · ", 1)[0])}
    card = next((m for m in section.metrics if _normalize_label(m.label) in wanted), None)
    if card is None:
        return None
    original = next((m for m in raw.get("metrics") or []
                     if _normalize_label(m.get("label", "")) == _normalize_label(card.label)), None)
    return None if original is None else (section, original, card)


def _stamp_cover_metric(final_brief: BriefPayloadV6, raw_sections: list[dict[str, Any]]) -> None:
    """Controller ruling (R2 fix H6): no model-written cover number reaches the public `briefs`
    row (the cover is not rendered since the Cover component retired). The cover's value is
    printed from the checked card it points to by fix 7b's printer (`_card_display_value`);
    `held_from`/`next_print` are that card's own system stamps; `as_of` survives only when it
    equals the card's builder date or period label. A cover pointing at no checked card keeps
    its words but none of its numbers: the value is the printer's unknown reading ("—") and
    the three dates are cleared. (The cover itself stays: dropping it is the stuck-hero rule's
    job, and that rule deliberately keeps a cover whose hero section has no cards.)"""
    cover = final_brief.brief.cover_metric
    if cover is None:
        return
    found = _cover_card(final_brief, raw_sections)
    if found is None:
        final_brief.brief.cover_metric = cover.model_copy(update={
            "value": _format_metric_value(None, ""), "as_of": None, "held_from": None, "next_print": None})
        logger.info("v6: cleared cover_metric %r numbers — it points at no checked card", cover.label)
        return
    section, original, card = found
    dated = {str(original.get("as_of") or "").strip(), _normalize_label(str(original.get("period") or ""))} - {""}
    as_of = cover.as_of if cover.as_of and (
        cover.as_of.strip() in dated or _normalize_label(cover.as_of) in dated) else None
    final_brief.brief.cover_metric = cover.model_copy(update={
        "value": _card_display_value(section, original), "as_of": as_of,
        "held_from": card.held_from, "next_print": card.next_print})


def _run_prose_number_gate(
    final_brief: BriefPayloadV6, raw_sections: list[dict[str, Any]],
    refused: tuple[_prose_numbers.RefusedFigure, ...] = (),
) -> list["_prose_numbers.NumberWarning"]:
    """Wire `brief.validators.prose_numbers` in (P2 fact-checker, 2026-08-22
    audit #204, round-2 review). `check_count_claims` is the only
    UNCONDITIONAL BLOCK-mode check (14/14 TP, 0 FP against a 25-real-issue
    corpus replay) and HOLDS the publish via `ProseNumberGateError`;
    `check_hyphenated_count_claims` holds it too, but ONLY for the sections in
    `_HYPHENATED_COUNT_BLOCK_SLUGS` (dse) and only for a count matching no
    machine-fed history fact (owner-approved 2026-08-28). Everything else
    (sub numbers/periods, metric.value vs raw, lede figures) is WARN-mode —
    collected and sent as ONE grouped Discord alert (H3), never blocking —
    UNLESS `BRIEF_PROSE_VALIDATOR_STRICT=1`, which upgrades the whole set to
    the same hard-fail (a documented future flip, not yet default; see the
    module docstring in brief/validators/prose_numbers.py for the corpus
    evidence behind this staging).

    R2 fix H6, owner decision (n): every other model text field (frame, titles, pills, news,
    cover label/sub) and the `refused` figures join the SAME grouped alert, WARN-only even
    under strict — never a hold."""
    strict = os.environ.get("BRIEF_PROSE_VALIDATOR_STRICT", "").strip() == "1"
    try:
        warnings = _prose_numbers.run_prose_number_gate(final_brief, raw_sections, strict=strict,
                                                        refused=refused)
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
    expected_identity: PublishIdentity,
    scraped_headlines: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
    write_fixture_path: str | None = None,
) -> str | None:
    """Execute the 2-call publish flow with fresh-brief V1 wiring.

    Live callers must enter through the CLI publication lock and supply the
    identity allocated there; direct historical replay must be a dry-run.

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

    if expected_identity.brief_date != today:
        raise V6PublishError("Run date differs from trusted publication identity")

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
    # Facts derivable from those same series that no builder can see (issues
    # 205-208 — the dse session-low rank). Filled by `_fetch_series_summaries`,
    # merged into the raw sections by `_build_editor_input`.
    derived_history_facts: dict[str, list[Any]] = {}
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
                history_facts_out=derived_history_facts,
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
        expected_identity=expected_identity,
        previous_brief=previous,
        previous_lens=previous_lens,
        recent_news=recent_news,
        metric_definitions=metric_definitions,
        series_summaries=series_summaries,
        derived_history_facts=derived_history_facts,
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

    try:
        assert_identity(editor_brief, expected_identity)
    except ValueError as exc:
        raise V6PublishError(str(exc)) from exc

    # R2 fix 16: change figures from the builders' own dated history, computed once.
    card_changes = _card_changes(sections)
    _enforce_observation_contract(editor_brief, editor_input["sections_raw"], model_output=True,
                                  card_changes=card_changes)

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
    # The Sub-Editor's `previous_brief` is NOT the Editor's. The Editor got a
    # structural skeleton so it could not copy yesterday's sentences; the
    # reviewer gets yesterday's full wording (figures scrubbed) because
    # comparing WORDING is the whole point of §7's CARRIED-FORWARD PROSE
    # check, and a reviewer that cannot see the previous text cannot run it.
    subeditor_input = {
        "editor_output": editor_brief.model_dump(mode="json"),
        "raw_data": {**editor_input, "previous_brief": _scrub_numbers(previous)},
    }
    review = _run_subeditor(subeditor_prompt, subeditor_input)

    if review.verdict == "fail":
        msgs = [f"  · [{i.severity}] {i.section}.{i.field}: {i.problem}" for i in review.issues]
        raise V6PublishError(f"subeditor verdict=fail with {len(review.issues)} issues:\n" + "\n".join(msgs))

    if review.verdict == "revise" and review.revised_brief is not None:
        final_brief = review.revised_brief
        try:
            assert_identity(final_brief, expected_identity)
        except ValueError as exc:
            raise V6PublishError(str(exc)) from exc
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
    _enforce_observation_contract(final_brief, editor_input["sections_raw"], model_output=True,
                                  card_changes=card_changes)
    # M-A, review round 2: deterministically stamps the macro Import Cover
    # metric's `sub` with its dual-period note — MetricV6 has no `source`
    # field, so nothing upstream of this call guarantees the note survives.
    _stamp_import_cover_sub(final_brief, editor_input["sections_raw"])
    # Same mechanism, same reason (2026-08-26): the Real Policy Rate's own
    # arithmetic — which repo rate minus which CPI print — is the only thing
    # that makes a restamp-lag error visible on the page.
    _stamp_real_policy_rate_sub(final_brief, editor_input["sections_raw"])

    # Restore the remittance observation before comparing published numbers;
    # the second pass below keeps its period authoritative after generic stamps.
    _stamp_remittance_sub(final_brief, editor_input["sections_raw"])
    stamp_changed(final_brief, previous)
    mark_held_overs(final_brief, previous, metric_definitions)
    # Vintage stamping runs LAST of the three and never overwrites
    # mark_held_overs, so a metric the catalog can explain keeps the catalog's
    # answer. In practice the catalog explains none of them — it has no
    # `section_slug` or `last_print_date` column in production — which is why
    # the "held from" footer had never rendered before this ran. See
    # brief/vintage.py.
    vintaged = stamp_vintages(final_brief, sections, today=today)
    _stamp_remittance_sub(final_brief, editor_input["sections_raw"])
    _stamp_freshness(final_brief, editor_input["sections_raw"])

    # Phase E.2 — chart series enricher. Skip silently when supabase env is
    # missing (e.g. dry-run from a workstation without secrets). Charts are
    # render-layer data; degraded charts must not block a publish.
    # R2 fix 6: whatever chart data the model wrote is discarded first, on
    # every path, so a skipped or failed stamp leaves an empty chart — never
    # model points.
    _discard_model_chart_data(final_brief)
    supabase_cfg: tuple[str, str] | None = _resolve_supabase_config()
    if supabase_cfg is None:
        logger.warning(
            "v6: skipping chart series stamp — SUPABASE_URL or service key missing in env"
        )
        _log_chartless_sections(
            final_brief, "chart not stamped: Supabase credentials missing in env",
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
    _enforce_observation_contract(final_brief, editor_input["sections_raw"],
                                  card_changes=card_changes)
    # R2 fix H6 (controller ruling): the cover's numbers from its checked card, or none at all.
    _stamp_cover_metric(final_brief, editor_input["sections_raw"])
    _run_prose_number_gate(final_brief, editor_input["sections_raw"],
                           refused=_refused_figures(getattr(sections, "snapshot", None), today))

    # Issue 206 tripwire (defect a+b net): a daily metric disagreeing with
    # its own chart series' newest point. WARN-mode only — see
    # `_PROMOTE_AS_OF_VS_SERIES_WARN_TO_BLOCK`'s docstring for why this must
    # never hold the publish today.
    as_of_warnings = _check_daily_as_of_vs_series_summary(editor_input["sections_raw"])
    if as_of_warnings:
        for w in as_of_warnings:
            logger.warning("v6 as_of-vs-series gate (WARN): %s", w)
        _alert(
            "WARN: The Brief as_of-vs-series gate — "
            f"{len(as_of_warnings)} daily metric(s) disagree with their own "
            "chart series:\n" + "\n".join(f"  {w}" for w in as_of_warnings)
        )
    else:
        logger.info("v6 as_of-vs-series gate: clean")

    _run_card_chart_gate(final_brief, editor_input["sections_raw"])

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
        return publish_brief(final_brief, expected_identity=expected_identity)
    except PublishError as e:
        raise V6PublishError(f"Supabase publish failed: {e}") from e
