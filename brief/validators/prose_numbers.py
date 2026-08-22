"""P2 fact-checker — post-editor number & period validator (2026-08-22 audit #204,
two-pass review). See AGENTS.md landmine 20's neighbour section on the editor/
sub-editor split and AGENT_LEARNINGS.md's 2026-08-22 entry for the failure modes
this closes: the editor invents month labels ("July print" on June's number),
invents counts ("fourteen reads", sourceless), and states figures that don't
trace to anything the builders actually produced.

Round-2 engineering review REJECTED a naive "prose vs. the metric's own
published value string" validator with: "that would have passed every wrong
number because the payload itself carries them — validate against the
BUILDER/source values." Every check in this module therefore compares prose
against `sections_raw` (the deterministic builder output BEFORE the editor
ever saw it), never against the editor's own formatted `MetricV6.value`.

Two severities, matching the existing `DenylistViolationError` /
`_run_deterministic_gate` split in `brief/pipeline_v6.py`:

  BLOCK  — `check_metric_sub_numbers`, `check_metric_sub_periods`,
           `check_count_claims`. A metric's own `sub` field is a NARROW,
           high-confidence surface: it is short, it is about ONE metric (plus
           its section siblings), and the editor was never given license to
           invent a number there. A violation raises `ProseNumberViolationError`
           and the caller (`pipeline_v6._run_prose_number_gate`) re-raises it
           as a `V6PublishError` subclass — same propagation shape as the
           denylist check, i.e. it HOLDS the publish.

  WARN   — `check_lede_numbers_against_builder_values`. The lede fields
           (`todays_call`/`tldr`/`verdict`/`analysis`) legitimately compose
           arithmetic across the whole issue in ways this module cannot fully
           anticipate (a "how are we framing today" sentence might reasonably
           cite two sections' numbers together). Warn-first, tighten later —
           `BRIEF_PROSE_VALIDATOR_STRICT=1` upgrades this to BLOCK for a
           future flip once the false-positive rate is known from the logs.

Tolerance: "half a unit in the last printed decimal" of the NUMBER BEING
CHECKED (the prose token, not the source value) — an integer-printed "733"
tolerates ±0.5, "9.50" tolerates ±0.005. This is deliberately generous toward
the editor's own rounding choices and strict about anything beyond that.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any


class ProseNumberViolationError(RuntimeError):
    """BLOCK-mode hard fail. Independent of `brief.pipeline_v6.V6PublishError`
    on purpose — this module must not import pipeline_v6 at module level (it
    would close an import cycle: pipeline_v6 imports THIS module). The caller
    in pipeline_v6.py catches this and re-raises a `V6PublishError` subclass
    so it reaches `cli.py`'s existing exit-code-4 handling."""


@dataclass(frozen=True)
class NumberWarning:
    """One WARN-mode figure with no builder-value match, for the caller to log
    / Discord-alert. `nearest_value`/`nearest_delta` are None only when the
    whole issue has no builder value in this token's category at all."""

    field_path: str
    matched_text: str
    normalized_value: float
    category: str
    nearest_value: float | None
    nearest_delta: float | None

    def describe(self) -> str:
        if self.nearest_value is None:
            near = "no builder value exists in this category anywhere in the issue"
        else:
            near = f"nearest builder-derived value {self.nearest_value:g} (Δ{self.nearest_delta:g})"
        return f"{self.field_path}: {self.matched_text!r} matches no builder value — {near}"


# ─── unit normalization ────────────────────────────────────────────────────
# Currency-magnitude scale, expressed relative to "mn" (million) as the base —
# arbitrary choice, only has to be internally consistent. 1 crore = 10 million.
_CURRENCY_SCALE: dict[str, float] = {
    "mn": 1.0, "million": 1.0,
    "cr": 10.0, "crore": 10.0,
    "bn": 1000.0, "billion": 1000.0,
    "tn": 1_000_000.0, "trillion": 1_000_000.0,
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


# Matches a number optionally preceded by a currency symbol/word and/or
# followed by a magnitude/percent/bp unit. Only kept when EITHER the currency
# OR the unit group actually matched — a bare "5" (a count, a year, an
# ordinal) is out of scope for value-matching; see module docstring.
_TOKEN_RE = re.compile(
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
    r"(?P<unit>\s?(?:bn|mn|cr|tn|bp)\b|%)?",
    re.IGNORECASE,
)


def _extract_money_percent_tokens(text: str) -> list[dict[str, Any]]:
    """Every currency/percent/bp figure in `text`, normalized + tolerance-stamped.

    Bare numbers (no currency symbol, no bn/mn/cr/tn/%/bp unit) are skipped
    entirely — they are far more often a year, an ordinal, or a count than a
    value assertion, and this module's job is precision over recall on that
    front (the count-claim regex below covers the specific invented-count
    failure mode instead).
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

        out.append({
            "matched_text": m.group(0).strip(),
            "category": category,
            "currency": currency_norm,
            "normalized_value": value * scale,
            "tolerance": 0.5 * (10 ** -decimals) * scale,
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


def _best_match(
    token: dict[str, Any], allowed: list[dict[str, Any]]
) -> tuple[bool, float | None, float | None]:
    """(matched_within_tolerance, nearest_value, nearest_delta) for `token`
    against `allowed`. Only compares within the same category, and (when both
    sides carry a currency code) the same currency."""
    nearest_value: float | None = None
    nearest_delta: float | None = None
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
        if nearest_delta is None or delta < nearest_delta:
            nearest_delta = delta
            nearest_value = entry["normalized_value"]
    matched = nearest_delta is not None and nearest_delta <= token["tolerance"]
    return matched, nearest_value, nearest_delta


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
    standing value, e.g. the BB policy corridor) are excluded: their `as_of`
    is a restamp date, not a decision date, so it carries no honest period to
    check against."""
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
        str(m["label"]).strip().casefold(): m
        for m in raw_metrics
        if m.get("label")
    }


# ─── count-claim pattern ───────────────────────────────────────────────────
# The pipeline never provides a "how many reads/prints/sessions" count field
# to the editor — this pattern is therefore an effective ban until it does.
_COUNT_CLAIM_RE = re.compile(
    r"(?:across|for|in)\s+(?:\w+teen|\w+ty|\d+)\s+(?:reads|prints|sessions|days)\b",
    re.IGNORECASE,
)


# ─── BLOCK-mode checks ─────────────────────────────────────────────────────


def check_metric_sub_numbers(
    final_brief: Any, raw_sections_by_slug: dict[str, dict[str, Any]]
) -> None:
    """Every currency/percent/bp figure in a published metric's `sub` must
    trace to that section's builder values (its own, a sibling's, or a
    pairwise derived delta). Raises on the first mismatch."""
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
                    near = (
                        f"nearest {nearest_value:g} (Δ{nearest_delta:g})"
                        if nearest_value is not None
                        else "no builder value in this category at all"
                    )
                    raise ProseNumberViolationError(
                        f"prose-number gate: {section.slug}.metrics[{i}].sub "
                        f"({pub_metric.label!r}) cites {token['matched_text']!r} "
                        f"which matches no builder value in this section "
                        f"({near}; tolerance ±{token['tolerance']:.4g}). "
                        "Publish held."
                    )


def check_metric_sub_periods(
    final_brief: Any, raw_sections_by_slug: dict[str, dict[str, Any]]
) -> None:
    """Every month-name token in a published metric's `sub` must equal the
    metric's own data period or a same-section sibling's — never a month the
    model invented. Periods come from `as_of`, never from prose."""
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
            raw_metric = raw_by_label.get(pub_metric.label.strip().casefold())
            if raw_metric is not None and raw_metric.get("cadence") == "event":
                # An event-cadence sub may legitimately name the actual
                # decision date ("held since the 30 Jul cut") which has
                # nothing to do with its daily-restamped `as_of` — landmine 24.
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
                    raise ProseNumberViolationError(
                        f"prose-number gate: {section.slug}.metrics[{i}].sub "
                        f"({pub_metric.label!r}) names {match.group(0)!r} which "
                        "matches no metric's actual data period in this section "
                        "— periods come from data, never the model. Publish held."
                    )


def check_count_claims(final_brief: Any) -> None:
    """Blocks any sourceless "across/for/in N reads/prints/sessions/days"
    claim anywhere in the brief's prose (audit #204's "fourteen reads")."""
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


# ─── WARN-mode check ───────────────────────────────────────────────────────

_LEDE_FIELD_NAMES = ("tldr", "verdict", "analysis")


def check_lede_numbers_against_builder_values(
    final_brief: Any, raw_sections: list[dict[str, Any]], *, strict: bool = False,
) -> list[NumberWarning]:
    """Every currency/percent figure in todays_call/tldr/verdict/analysis that
    matches NO builder value anywhere in the issue (union across sections,
    same tolerance + pairwise derivations). Returns the list of warnings;
    raises `ProseNumberViolationError` on the first one instead when `strict`
    (BRIEF_PROSE_VALIDATOR_STRICT=1) — a future block-mode flip."""
    all_raw_metrics = [m for s in raw_sections for m in (s.get("metrics") or [])]
    allowed = _build_allowed_values(all_raw_metrics)
    warnings: list[NumberWarning] = []

    def _scan(field_path: str, text: str | None) -> None:
        if not text:
            return
        for token in _extract_money_percent_tokens(text):
            matched, nearest_value, nearest_delta = _best_match(token, allowed)
            if not matched:
                warnings.append(NumberWarning(
                    field_path=field_path,
                    matched_text=token["matched_text"],
                    normalized_value=token["normalized_value"],
                    category=token["category"],
                    nearest_value=nearest_value,
                    nearest_delta=nearest_delta,
                ))

    _scan("brief.todays_call", final_brief.brief.todays_call)
    for s in final_brief.sections:
        for field_name in _LEDE_FIELD_NAMES:
            _scan(f"{s.slug}.{field_name}", getattr(s, field_name, None))

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
    """BLOCK checks first (raise on first violation), then the WARN-mode lede
    scan. Caller owns logging/alerting the returned warnings — this module
    has no Discord dependency, to stay independently testable."""
    raw_by_slug = {s["slug"]: s for s in raw_sections if "slug" in s}
    check_metric_sub_numbers(final_brief, raw_by_slug)
    check_metric_sub_periods(final_brief, raw_by_slug)
    check_count_claims(final_brief)
    return check_lede_numbers_against_builder_values(final_brief, raw_sections, strict=strict)
