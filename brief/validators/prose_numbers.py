"""P2 fact-checker — post-editor number & period validator (2026-08-22 audit #204).

Two review rounds shaped this module, both with real corpus evidence, not
just first-principles design:

Round 1 REJECTED a naive "prose vs. the metric's own published value string"
validator with: "that would have passed every wrong number because the
payload itself carries them — validate against the BUILDER/source values."
Every check therefore compares prose against `sections_raw` (the
deterministic builder output BEFORE the editor ever saw it).

Round 2 REJECTED the first cut's BLOCK scope after replaying it against 25
real published issues (#180-#204): 25/25 would have held the publish, 527
BLOCK hits, only 3 true positives (0.6% precision) — while 3 of the 5
audit falsehoods passed UNCAUGHT, because the check that would have caught
them (`check_metric_sub_numbers`) only ever looked at `sub`, never at the
metric's own headline `value` (where the "$2.82bn" falsehood actually
lived). The reshape below is round 2's verdict, not a guess:

  BLOCK (raises `ProseNumberViolationError`, holds the publish) — ONLY
  `check_count_claims`. Its corpus replay: 14 true positives (all the
  fiscal "fourteen reads/prints" phrasing), 0 false positives, once the
  noun list is narrowed to (reads|prints) — "days"/"sessions" contributed
  zero true positives and real false positives ("...in 14 days" as a
  plain duration statement, not a count-of-observations claim).

  WARN (logged + Discord-alerted in ONE grouped message, never blocks) —
  everything else: `check_metric_sub_numbers`, `check_metric_sub_periods`,
  `check_metric_value_vs_raw` (new — the check that would have caught the
  $2.82bn falsehood, since it lived in `value`, not `sub`), and
  `check_lede_numbers_against_builder_values` (extended to banker_read.*
  and chart_read.* on top of todays_call/tldr/verdict/analysis).
  `BRIEF_PROSE_VALIDATOR_STRICT=1` upgrades ALL of these to BLOCK — a
  documented FUTURE flip, not this PR's default, and only once the WARN
  log volume in production proves a near-zero real false-positive rate
  the way the count-claim check's corpus replay already did.

Tolerance: "half a unit in the last printed decimal" of the NUMBER BEING
CHECKED — an integer-printed "733" tolerates ±0.5, "9.50" tolerates
±0.005. Two corpus-driven refinements on top of that base:
  - A "~" approximation marker widens it to a full unit instead of half
    (so a deliberately-hedged "~8bp" accepts a precise 8.6bp).
  - For CURRENCY tokens only, the tolerance is floored at 0.5% of the
    matched value and capped at 1% — a coarse "$3bn" no longer gets a free
    pass against a true 2.86bn just because its own half-ulp (±0.5bn) is
    wide; percent/bp tokens are unaffected (their half-ulp is already
    tight relative to their typical magnitude).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any


class ProseNumberViolationError(RuntimeError):
    """BLOCK-mode hard fail — raised ONLY by `check_count_claims` (and by the
    orchestrator when `BRIEF_PROSE_VALIDATOR_STRICT=1` upgrades a WARN).
    Independent of `brief.pipeline_v6.V6PublishError` on purpose — this
    module must not import pipeline_v6 at module level (it would close an
    import cycle: pipeline_v6 imports THIS module). The caller in
    pipeline_v6.py catches this and re-raises a `V6PublishError` subclass so
    it reaches `cli.py`'s existing exit-code-4 handling."""


@dataclass(frozen=True)
class NumberWarning:
    """One WARN-mode figure with no builder-value match, for the caller to
    log / batch into a single Discord alert. `section` is the slug (or
    "brief" for brief-level fields) — the caller groups by this. `kind`
    names which check produced it, for the alert message and for tests.
    `nearest_value`/`nearest_delta` are None only when the whole scope has
    no builder value in this token's category at all."""

    kind: str
    section: str
    field_path: str
    matched_text: str
    normalized_value: float
    category: str
    nearest_value: float | None
    nearest_delta: float | None

    def describe(self) -> str:
        if self.nearest_value is None:
            near = "no builder value exists in this category anywhere in scope"
        else:
            near = f"nearest builder-derived value {self.nearest_value:g} (Δ{self.nearest_delta:g})"
        return f"[{self.kind}] {self.field_path}: {self.matched_text!r} matches no builder value — {near}"


def _normalize_label(label: str) -> str:
    """NFC + strip + casefold — the SAME normalization
    `pipeline_v6._normalize_label` uses for `_reconcile_metrics`'s
    cross-source label matching. Deliberately duplicated (not imported —
    this module avoids a module-level dependency on pipeline_v6) rather than
    the plain `.strip().casefold()` this module used before round 2: that
    was flagged as a real robustness gap, not just a style nit, since it's
    the SAME (section, label) key every other post-editor pass keys on."""
    return unicodedata.normalize("NFC", label).strip().casefold()


# ─── unit normalization ────────────────────────────────────────────────────
# Currency-magnitude scale, expressed relative to "mn" (million) as the base —
# arbitrary choice, only has to be internally consistent. 1 crore = 10 million.
# "trn" (not just "tn") is a real builder unit string (fiscal.py: "BDT trn") —
# missing it was a round-2 corpus defect: "trn" doesn't contain "tn" as a
# substring, so `_metric_category("BDT trn")` fell through to a "plain"
# bucket that could never match the "tn"-suffixed token a sub would use to
# restate its OWN value ("Tk3.61tn"), producing a pure false positive.
_CURRENCY_SCALE: dict[str, float] = {
    "mn": 1.0, "million": 1.0,
    "cr": 10.0, "crore": 10.0,
    "bn": 1000.0, "billion": 1000.0,
    "tn": 1_000_000.0, "trn": 1_000_000.0, "trillion": 1_000_000.0,
}


def _metric_category(unit: str) -> tuple[str, float, str | None]:
    """Classify a builder Metric's own `unit` string into
    (category, scale_to_base, currency_code).

    `category` is "percent", "currency", or "plain:<unit>" (a catch-all for
    index/months/stocks/items-style units with no honest cross-metric
    comparison). `scale_to_base` converts a value in `unit` into the
    category's canonical base (percent points for "percent"; millions for
    "currency"). A currency unit with NO magnitude suffix (`USD/bbl`,
    `USD/oz`) still categorizes as "currency" with scale 1.0 — Brent's
    $108.17 must be comparable to a bare "$108.17" in prose, not shoved into
    a unique plain-bucket that can never match anything.
    """
    u = (unit or "").lower()
    if "%" in u:
        return "percent", 1.0, None
    currency = "USD" if "usd" in u else ("BDT" if ("bdt" in u or "tk" in u) else None)
    if currency is not None:
        for suffix, factor in _CURRENCY_SCALE.items():
            if suffix in u:
                return "currency", factor, currency
        return "currency", 1.0, currency
    return f"plain:{u}", 1.0, None


# Matches a number optionally preceded by an approximation marker, a sign,
# and/or a currency symbol/word, and optionally followed by a magnitude/
# percent/bp unit. Only kept when EITHER the currency OR the unit group
# actually matched — a bare "5" (a count, a year, an ordinal) is out of
# scope for value-matching; see module docstring.
_TOKEN_RE = re.compile(
    # "~" is a deliberate approximation marker — widens tolerance below.
    r"(?P<approx>~\s*)?"
    # Master.md mandates the minus GLYPH (−, U+2212) for negatives, never a
    # hyphen — captured separately from ASCII '-' so a sentence's em-dash
    # (—, U+2014) is never mistaken for a sign; distinct code points, no
    # regex ambiguity between the two. Two sign slots because a sign can
    # precede the currency symbol ("−$1.62bn") or sit between it and the
    # digits ("$−1.62bn") — both are seen in real desk prose.
    r"(?P<sign1>[-−])?"
    r"(?P<currency>\$|Tk\s?|৳|USD\s?|BDT\s?)?"
    r"(?P<sign2>[-−])?"
    r"(?P<number>\d[\d,]*(?:\.\d+)?)"
    r"(?P<unit>\s?(?:bn|mn|cr|trn|tn|bp)\b|%)?",
    re.IGNORECASE,
)


def _extract_money_percent_tokens(text: str) -> list[dict[str, Any]]:
    """Every currency/percent/bp figure in `text`, normalized + tolerance-stamped.

    Bare numbers (no currency symbol, no bn/mn/cr/tn/%/bp unit) are skipped
    entirely — they are far more often a year, an ordinal, or a count than a
    value assertion, and this module's job is precision over recall on that
    front (the count-claim regex covers the specific invented-count failure
    mode instead).
    """
    out: list[dict[str, Any]] = []
    for m in _TOKEN_RE.finditer(text):
        currency_raw = m.group("currency")
        unit_raw = m.group("unit")
        if not currency_raw and not unit_raw:
            continue
        num_str = m.group("number")
        try:
            value = float(num_str.replace(",", ""))
        except ValueError:
            continue
        if m.group("sign1") or m.group("sign2"):
            value = -value
        decimals = len(num_str.split(".")[1]) if "." in num_str else 0

        currency_norm: str | None = None
        if currency_raw:
            c = currency_raw.strip().lower()
            if c in ("$", "usd"):
                currency_norm = "USD"
            elif c in ("tk", "bdt", "৳"):
                currency_norm = "BDT"

        unit_norm = (unit_raw or "").strip().lower()
        if unit_norm == "%":
            category, scale = "percent", 1.0
        elif unit_norm == "bp":
            category, scale = "percent", 0.01
        elif unit_norm in _CURRENCY_SCALE:
            category, scale = "currency", _CURRENCY_SCALE[unit_norm]
        else:
            # currency symbol present, no magnitude suffix — a raw price
            category, scale = "currency", 1.0

        # Round-2 fix: "~8bp accepts 8.6bp" — an approximation marker signals
        # the editor's OWN precision is coarser than the printed decimal
        # count suggests, so the tolerance widens from half a unit to a full
        # one in the token's native (pre-scale) form.
        ulp_multiplier = 1.0 if m.group("approx") else 0.5
        out.append({
            "matched_text": m.group(0).strip(),
            "category": category,
            "currency": currency_norm,
            "normalized_value": value * scale,
            "tolerance": ulp_multiplier * (10 ** -decimals) * scale,
        })
    return out


def _normalize_metric_value(unit: str, value: Any) -> dict[str, Any] | None:
    """A raw builder metric's (category, currency, normalized_value), or None
    when the value isn't numeric (a suppressed/None metric, or a string
    value carries nothing this module can compare against)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    category, scale, currency = _metric_category(unit)
    return {"category": category, "currency": currency, "normalized_value": float(value) * scale}


def _build_allowed_values(raw_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every raw metric's own normalized value, PLUS the pairwise |a−b| for
    any two metrics sharing a (category, currency) bucket — the "19bp under
    the 9.50% policy" derived-spread case. Diffs are first-order only (no
    diff-of-diffs)."""
    entries: list[dict[str, Any]] = []
    for m in raw_metrics:
        norm = _normalize_metric_value(m.get("unit", ""), m.get("value"))
        if norm is not None:
            entries.append(norm)

    derived: list[dict[str, Any]] = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a, b = entries[i], entries[j]
            if a["category"] != b["category"]:
                continue
            if a["currency"] is not None and b["currency"] is not None and a["currency"] != b["currency"]:
                continue
            derived.append({
                "category": a["category"],
                "currency": a["currency"] or b["currency"],
                "normalized_value": abs(a["normalized_value"] - b["normalized_value"]),
            })
    return entries + derived


def _effective_tolerance(token: dict[str, Any], entry: dict[str, Any]) -> float:
    """The tolerance to use for THIS (token, candidate) pair.

    Round-2 corpus fix (item 3d): for CURRENCY tokens only, a coarse
    half-ulp (e.g. ±0.5bn for a bare "$3bn") is floored at 0.5% of the
    candidate's own magnitude and capped at 1% — "$3bn" no longer silently
    passes against a true 2.86bn just because writing it with zero decimals
    happens to buy a ±500mn band. Percent/bp tokens are unaffected: their
    half-ulp is already tight relative to typical percentage magnitudes, and
    the round-2 review scoped this fix to "currency tokens" specifically.
    """
    base = token["tolerance"]
    if token["category"] != "currency":
        return base
    magnitude = abs(entry["normalized_value"])
    floor = 0.005 * magnitude
    cap = 0.01 * magnitude
    return min(max(base, floor), cap)


def _best_match(
    token: dict[str, Any], allowed: list[dict[str, Any]]
) -> tuple[bool, float | None, float | None]:
    """(matched_within_tolerance, nearest_value, nearest_delta) for `token`
    against `allowed`. Only compares within the same category, and (when both
    sides carry a currency code) the same currency. A candidate matches when
    it is within ITS OWN effective tolerance (see `_effective_tolerance` —
    this varies per candidate for currency tokens); when none match, the
    NUMERICALLY closest candidate is reported for diagnostics.
    """
    candidates: list[tuple[float, float, float]] = []  # (delta, value, tolerance)
    for entry in allowed:
        if entry["category"] != token["category"]:
            continue
        if (
            token["currency"] is not None
            and entry["currency"] is not None
            and token["currency"] != entry["currency"]
        ):
            continue
        delta = abs(entry["normalized_value"] - token["normalized_value"])
        candidates.append((delta, entry["normalized_value"], _effective_tolerance(token, entry)))

    if not candidates:
        return False, None, None
    for delta, value, tolerance in candidates:
        if delta <= tolerance:
            return True, value, delta
    delta, value, _tolerance = min(candidates, key=lambda c: c[0])
    return False, value, delta


# ─── month/period tokens ───────────────────────────────────────────────────
# No IGNORECASE — lowercase "may" is a modal verb, not a month (same reasoning
# as brief/claude/validators.py's TEMPORAL_REGEX).
_MONTH_NAMES: dict[str, int] = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_TOKEN_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"\.?\s*(\d{4})?\b"
)


def _parse_iso_date(raw: Any) -> date | None:
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _section_periods(raw_metrics: list[dict[str, Any]]) -> set[tuple[int, int]]:
    """{(month, year), ...} for every NON-EVENT-cadence raw metric's `as_of`
    in a section — the ONLY legitimate source of a period claim (never the
    model). Event-cadence metrics (AGENTS.md landmine 24 — a daily-restamped
    standing value, e.g. the BB policy corridor OR the T-Bill cut-off rates,
    all of which are re-upserted daily between auctions) are excluded: their
    `as_of` is a restamp date, not a decision date, so it carries no honest
    period to check against."""
    periods: set[tuple[int, int]] = set()
    for m in raw_metrics:
        if m.get("cadence") == "event":
            continue
        d = _parse_iso_date(m.get("as_of"))
        if d is not None:
            periods.add((d.month, d.year))
    return periods


def _raw_metric_by_label(raw_metrics: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        _normalize_label(str(m["label"])): m
        for m in raw_metrics
        if m.get("label")
    }


# Matches pipeline_v6._IMPORT_COVER_SUB_MARKER exactly — `_stamp_import_cover_sub`
# deterministically stamps a dual-period note (e.g. "reserves 31 Jul ÷ Mar
# import bill") onto the macro Import Cover metric's `sub`, sourced from the
# raw builder metric's OWN `source` field. That note legitimately names TWO
# different months by construction (the whole point of the metric is that it
# combines two vintages) — round-2 fix (item 3b): detect this by the RAW
# metric's stable `source` pattern (the same marker the stamping function
# itself checks for), not by testing the display label, so the exemption
# tracks the mechanism that produces the text rather than a metric name that
# could drift.
_IMPORT_COVER_SOURCE_MARKER = "import bill"


def _is_machine_stamped_dual_period(raw_metric: dict[str, Any]) -> bool:
    src = str(raw_metric.get("source") or "").lower()
    return "reserves" in src and _IMPORT_COVER_SOURCE_MARKER in src


# ─── count-claim pattern ───────────────────────────────────────────────────
# Round-2 corpus replay (25 real issues, #180-#204): narrowed from
# (reads|prints|sessions|days) to (reads|prints) — "days" and "sessions"
# contributed ZERO true positives across the corpus and "days" produced a
# real false positive ("BB hasn't published reserves in 14 days" — a plain
# duration statement, not an invented observation count). With this narrower
# noun list: 14 true positives, 0 false positives, all of them the fiscal
# section's "fourteen reads/prints" phrasing.
_COUNT_CLAIM_RE = re.compile(
    r"(?:across|for|in)\s+(?:\w+teen|\w+ty|\d+)\s+(?:reads|prints)\b",
    re.IGNORECASE,
)


# ─── BLOCK-mode check (the only one) ───────────────────────────────────────


def check_count_claims(final_brief: Any) -> None:
    """Blocks any sourceless "across/for/in N reads/prints" claim anywhere in
    the brief's prose (audit #204's "fourteen reads"). The ONLY unconditional
    BLOCK in this module — round-2 corpus replay: 14/14 true positives, 0
    false positives across 25 real published issues."""
    from brief.pipeline_v6 import _collect_prose_fields  # lazy: pipeline_v6 imports this module

    for field_path, text in _collect_prose_fields(final_brief):
        match = _COUNT_CLAIM_RE.search(text)
        if match:
            raise ProseNumberViolationError(
                f"prose-number gate: count-claim {match.group(0)!r} at "
                f"{field_path!r} — no count field is ever provided to the "
                "editor; this is an invented figure (2026-08-22 audit #204, "
                "'fourteen reads'). Publish held."
            )


# ─── WARN-mode checks ───────────────────────────────────────────────────────


def check_metric_sub_numbers(
    final_brief: Any, raw_sections_by_slug: dict[str, dict[str, Any]]
) -> list[NumberWarning]:
    """Every currency/percent/bp figure in a published metric's `sub` must
    trace to that section's builder values (its own, a sibling's, or a
    pairwise derived delta). WARN-mode (round 2 — see module docstring)."""
    warnings: list[NumberWarning] = []
    for section in final_brief.sections:
        raw_section = raw_sections_by_slug.get(section.slug)
        if raw_section is None:
            continue
        raw_metrics = raw_section.get("metrics") or []
        allowed = _build_allowed_values(raw_metrics)
        for i, pub_metric in enumerate(section.metrics):
            if not pub_metric.sub:
                continue
            for token in _extract_money_percent_tokens(pub_metric.sub):
                matched, nearest_value, nearest_delta = _best_match(token, allowed)
                if not matched:
                    warnings.append(NumberWarning(
                        kind="sub_number",
                        section=section.slug,
                        field_path=f"{section.slug}.metrics[{i}].sub",
                        matched_text=token["matched_text"],
                        normalized_value=token["normalized_value"],
                        category=token["category"],
                        nearest_value=nearest_value,
                        nearest_delta=nearest_delta,
                    ))
    return warnings


def check_metric_sub_periods(
    final_brief: Any, raw_sections_by_slug: dict[str, dict[str, Any]]
) -> list[NumberWarning]:
    """Every month-name token in a published metric's `sub` must equal the
    metric's own data period or a same-section sibling's — never a month the
    model invented. Periods come from `as_of`, never from prose. WARN-mode
    (round 2 — see module docstring)."""
    warnings: list[NumberWarning] = []
    for section in final_brief.sections:
        raw_section = raw_sections_by_slug.get(section.slug)
        if raw_section is None:
            continue
        raw_metrics = raw_section.get("metrics") or []
        periods = _section_periods(raw_metrics)
        raw_by_label = _raw_metric_by_label(raw_metrics)
        if not periods:
            continue
        months_only = {m for m, _y in periods}
        for i, pub_metric in enumerate(section.metrics):
            if not pub_metric.sub:
                continue
            raw_metric = raw_by_label.get(_normalize_label(pub_metric.label))
            if raw_metric is not None and raw_metric.get("cadence") == "event":
                # An event-cadence sub may legitimately name the actual
                # decision date ("held since the 30 Jul cut") which has
                # nothing to do with its daily-restamped `as_of` — landmine 24.
                continue
            if raw_metric is not None and _is_machine_stamped_dual_period(raw_metric):
                # `_stamp_import_cover_sub` deliberately names TWO different
                # months by construction — not a hallucination to catch.
                continue
            for match in _MONTH_TOKEN_RE.finditer(pub_metric.sub):
                month_num = _MONTH_NAMES.get(match.group(1).lower())
                if month_num is None:
                    continue
                year_str = match.group(2)
                if year_str:
                    ok = (month_num, int(year_str)) in periods
                else:
                    ok = month_num in months_only
                if not ok:
                    warnings.append(NumberWarning(
                        kind="sub_period",
                        section=section.slug,
                        field_path=f"{section.slug}.metrics[{i}].sub",
                        matched_text=match.group(0),
                        normalized_value=float(month_num),
                        category="period",
                        nearest_value=None,
                        nearest_delta=None,
                    ))
    return warnings


def check_metric_value_vs_raw(
    final_brief: Any, raw_sections_by_slug: dict[str, dict[str, Any]]
) -> list[NumberWarning]:
    """NEW (round 2, item 4) — the check that would have caught the actual
    "$2.82bn" audit falsehood: it lived in the metric's own headline
    `value`, not in `sub`, and nothing in round 1's checks ever read
    `value`. Post-#158's metric reconciliation, a published metric's `value`
    should ALWAYS trace to the SAME (section, label) raw builder value —
    any warning here is either a genuine editor substitution (the audit's
    failure mode) or a reconcile-path bug, both worth surfacing. WARN-mode."""
    warnings: list[NumberWarning] = []
    for section in final_brief.sections:
        raw_section = raw_sections_by_slug.get(section.slug)
        if raw_section is None:
            continue
        raw_by_label = _raw_metric_by_label(raw_section.get("metrics") or [])
        for i, pub_metric in enumerate(section.metrics):
            if not pub_metric.value:
                continue
            raw_metric = raw_by_label.get(_normalize_label(pub_metric.label))
            if raw_metric is None:
                continue
            raw_norm = _normalize_metric_value(raw_metric.get("unit", ""), raw_metric.get("value"))
            if raw_norm is None:
                continue
            for token in _extract_money_percent_tokens(str(pub_metric.value)):
                if token["category"] != raw_norm["category"]:
                    continue
                if (
                    token["currency"] is not None
                    and raw_norm["currency"] is not None
                    and token["currency"] != raw_norm["currency"]
                ):
                    continue
                tolerance = _effective_tolerance(token, raw_norm)
                delta = abs(token["normalized_value"] - raw_norm["normalized_value"])
                if delta > tolerance:
                    warnings.append(NumberWarning(
                        kind="value_vs_raw",
                        section=section.slug,
                        field_path=f"{section.slug}.metrics[{i}].value",
                        matched_text=token["matched_text"],
                        normalized_value=token["normalized_value"],
                        category=token["category"],
                        nearest_value=raw_norm["normalized_value"],
                        nearest_delta=delta,
                    ))
    return warnings


# Fields scanned for the lede WARN check, beyond todays_call — extended in
# round 2 (item 4b) to banker_read.* and chart_read.*, the two prose surfaces
# most likely to compose figures across a section the way todays_call does.
_LEDE_SIMPLE_FIELDS = ("tldr", "verdict", "analysis")


def check_lede_numbers_against_builder_values(
    final_brief: Any, raw_sections: list[dict[str, Any]], *, strict: bool = False,
) -> list[NumberWarning]:
    """Every currency/percent figure in todays_call/tldr/verdict/analysis/
    banker_read.*/chart_read.* that matches NO builder value anywhere in the
    issue (union across sections, same tolerance + pairwise derivations).

    `strict` is accepted here for standalone-callable ergonomics (calling
    this check in isolation, outside the orchestrator, still supports an
    immediate escalation) but `run_prose_number_gate` does NOT pass it —
    the orchestrator collects EVERY WARN-producing check's findings first
    and escalates once, at the end, so all of them get the same
    `BRIEF_PROSE_VALIDATOR_STRICT=1` treatment rather than just this one."""
    all_raw_metrics = [m for s in raw_sections for m in (s.get("metrics") or [])]
    allowed = _build_allowed_values(all_raw_metrics)
    warnings: list[NumberWarning] = []

    def _scan(section_slug: str, field_path: str, text: str | None) -> None:
        if not text:
            return
        for token in _extract_money_percent_tokens(text):
            matched, nearest_value, nearest_delta = _best_match(token, allowed)
            if not matched:
                warnings.append(NumberWarning(
                    kind="lede_number",
                    section=section_slug,
                    field_path=field_path,
                    matched_text=token["matched_text"],
                    normalized_value=token["normalized_value"],
                    category=token["category"],
                    nearest_value=nearest_value,
                    nearest_delta=nearest_delta,
                ))

    _scan("brief", "brief.todays_call", final_brief.brief.todays_call)
    for s in final_brief.sections:
        for field_name in _LEDE_SIMPLE_FIELDS:
            _scan(s.slug, f"{s.slug}.{field_name}", getattr(s, field_name, None))
        banker_read = getattr(s, "banker_read", None)
        if banker_read is not None:
            _scan(s.slug, f"{s.slug}.banker_read.verdict", banker_read.verdict)
            for i, w in enumerate(banker_read.watch or []):
                _scan(s.slug, f"{s.slug}.banker_read.watch[{i}]", w)
            for i, r in enumerate(banker_read.risk or []):
                _scan(s.slug, f"{s.slug}.banker_read.risk[{i}]", r)
        chart_read = getattr(s, "chart_read", None)
        if chart_read is not None:
            _scan(s.slug, f"{s.slug}.chart_read.signal", chart_read.signal)
            _scan(s.slug, f"{s.slug}.chart_read.context", chart_read.context)
            _scan(s.slug, f"{s.slug}.chart_read.implication", chart_read.implication)

    if warnings and strict:
        raise ProseNumberViolationError(
            f"prose-number gate (STRICT — BRIEF_PROSE_VALIDATOR_STRICT=1): "
            f"{warnings[0].describe()}. Publish held."
        )
    return warnings


# ─── orchestrator ──────────────────────────────────────────────────────────


def run_prose_number_gate(
    final_brief: Any, raw_sections: list[dict[str, Any]], *, strict: bool = False,
) -> list[NumberWarning]:
    """`check_count_claims` first (raises unconditionally — the ONLY
    BLOCK-mode check post-round-2). Then every WARN-mode check runs and its
    findings are collected into one list. When `strict`
    (BRIEF_PROSE_VALIDATOR_STRICT=1), the first collected warning is
    escalated to a raise instead of being returned — a documented future
    flip, not this PR's default (see module docstring)."""
    check_count_claims(final_brief)

    raw_by_slug = {s["slug"]: s for s in raw_sections if "slug" in s}
    warnings: list[NumberWarning] = []
    warnings.extend(check_metric_sub_numbers(final_brief, raw_by_slug))
    warnings.extend(check_metric_sub_periods(final_brief, raw_by_slug))
    warnings.extend(check_metric_value_vs_raw(final_brief, raw_by_slug))
    warnings.extend(check_lede_numbers_against_builder_values(final_brief, raw_sections))

    if warnings and strict:
        raise ProseNumberViolationError(
            f"prose-number gate (STRICT — BRIEF_PROSE_VALIDATOR_STRICT=1): "
            f"{warnings[0].describe()}. Publish held."
        )
    return warnings
