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
  `check_count_claims`, and only as a TRIPWIRE on the common surface
  forms, not an exhaustive ban: "for twelve reads" ("twelve" doesn't end
  in "teen"/"ty") and "through fourteen reads" ("through" isn't in the
  preposition list) both pass uncaught. Its corpus replay: 17 true
  positives across 9 real issues (#184, #197-#204) — 16 in fiscal
  sections across #197-#204, plus one in issue #184's
  `fx.chart_read.context` ("held 122.85 for fourteen prints") — 0 false
  positives, once the noun list is narrowed to (reads|prints) —
  "days"/"sessions" contributed zero true positives and a real false
  positive ("...in 14 days" as a plain duration statement, not a
  count-of-observations claim).

  BLOCK, SCOPED (added 2026-08-28, owner-approved) —
  `check_hyphenated_count_claims`, for the sections in
  `_HYPHENATED_COUNT_BLOCK_SLUGS` (today: `dse`) AND only for the claim
  shape the supply side can answer (`_is_blockable_shape`:
  session/print/read + "low"). The hyphenated ATTRIBUTIVE shape ("a
  ten-session low") shipped byte-identical across issues 205-208 while the
  real rank ran 38 -> 42; PR #185 now feeds `dse` the true rank as a
  history fact, so a session-low claim there matching neither that fact nor
  any other sourced count is invented by construction. A claim whose NUMBER
  matches a machine-supplied count is legitimate and produces nothing at
  all. Outside that slug set — where no count is supplied and a finding
  means "unverifiable", not "invented" — and outside that shape — where no
  fact of the kind could ever exist to clear it — it stays WARN.

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
    """BLOCK-mode hard fail — raised by `check_count_claims` (unconditional,
    anywhere in the brief), by `check_hyphenated_count_claims` for a section
    in `_HYPHENATED_COUNT_BLOCK_SLUGS` (scoped, 2026-08-28), and by the
    orchestrator when `BRIEF_PROSE_VALIDATOR_STRICT=1` upgrades a WARN.
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
            # Both are read by `_effective_tolerance`: `scale` distinguishes a
            # raw price ("$7", 1.0) from a suffix-inflated one ("Tk3.5tn", 1e6),
            # and `approx` records whether the writer marked their own rounding.
            "scale": scale,
            "approx": bool(m.group("approx")),
            # Character span within `text` — only `check_year_ago_claims` reads
            # it, to pick the token NEAREST a phrase rather than any token in
            # the field. Every other caller ignores it.
            "span": m.span(),
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


# ─── chart-series + history-fact grounding (2026-08-23) ────────────────────
# Issue 205's run logged 62 WARNs and NOT ONE was a wrong number. 27 were
# `chart_read.*` lines and the rest split between metric subs and
# banker_read. The cause is that #167 shipped two halves that disagree:
#
#   - the editor half started sending `series_summary` (a per-series digest
#     of {n, first_ts, first_value, last_ts, last_value, min, max}) and the
#     prompt now REQUIRES chart_read be derived from it — "$31.09bn in Nov
#     2025" is the reserves chart's own `first_value`/`first_ts`;
#   - the validator half only ever collected `raw_metrics[].value` plus
#     pairwise diffs, so every one of those honest citations was unmatched.
#
# The same disagreement covers `history_facts`, which the prompt requires be
# woven in VERBATIM including the parenthetical ("highest since Apr 2022
# (10.9% then)") — the phrase's value and its as-of month were both unknown
# to this module, so following the prompt guaranteed a WARN.
#
# Scope boundary, deliberately narrow: ONLY the four digest values the
# editor was actually handed (first/last/min/max) are admitted. A MID-series
# point stays unmatched on purpose — the editor never received it, so citing
# one is still an invention, which is exactly what the prompt's "never claim
# a mid-series value" rule says. Series values also do NOT participate in
# `_build_allowed_values`'s pairwise-diff derivation: that would widen the
# allowed set combinatorially (4 values x every series x every metric) with
# no corpus evidence that the editor derives spreads off chart endpoints.

# Series-key -> the builder `unit` string its values are denominated in, so
# they go through the SAME `_metric_category` normalization as metric values
# rather than a parallel scale table. Keys follow `chart_series_fetcher`'s
# naming convention; `tests/validators/test_prose_numbers_series_scope.py`
# pins this map against that module's real key list so a new series cannot
# be added there without being classified here.
#
# An UNKNOWN key is admitted as NOTHING — never guessed at scale 1.0. A
# wrong scale would silently widen the allowed set by a factor of 1000 and
# let a genuinely invented figure match; a missing key merely costs a WARN
# that a human reads. Fail toward the false positive, never the false
# negative.
_SERIES_KEY_EXACT_UNITS: dict[str, str] = {
    "brent": "USD",   # brent_crude_usd_barrel — a bare per-barrel price
    "dsex": "index",  # plain: index points, never cited with $ or %
}


def _series_key_unit(key: str) -> str | None:
    """The builder-style `unit` string for a chart series key, or None when
    the key is unrecognised (see the fail-toward-false-positive note above)."""
    if key in _SERIES_KEY_EXACT_UNITS:
        return _SERIES_KEY_EXACT_UNITS[key]
    k = key.lower()
    if "usd_bn" in k:
        return "USD bn"
    if "usd_mn" in k:
        return "USD mn"
    if k.endswith("_cr") or "_cr_" in k:
        return "BDT cr"
    if k.startswith("cpi_"):
        return "%"
    if k.startswith("yield_") or k.startswith("tbill_"):
        return "%"
    return None


# The digest fields the editor is actually shown — the complete set of
# chart values it can honestly cite. See the scope-boundary note above.
# `value_1y_ago` joined in the issues-207/208 fix: `summarize_series_points`
# now hands the editor the point one year before `last_ts`, so it is a number
# the editor legitimately received and may cite (and the honest replacement
# for the `first_value` misread `check_year_ago_claims` catches below).
_SERIES_DIGEST_VALUE_FIELDS = ("first_value", "last_value", "min", "max", "value_1y_ago")


def _series_summary_entries(series_summary: Any) -> list[dict[str, Any]]:
    """Normalized allowed-value entries for one section's `series_summary`."""
    if not isinstance(series_summary, dict):
        return []
    entries: list[dict[str, Any]] = []
    for key, digest in series_summary.items():
        if not isinstance(digest, dict):
            continue
        unit = _series_key_unit(str(key))
        if unit is None:
            continue
        for field in _SERIES_DIGEST_VALUE_FIELDS:
            norm = _normalize_metric_value(unit, digest.get(field))
            if norm is not None:
                entries.append(norm)
    return entries


def _series_summary_periods(series_summary: Any) -> set[tuple[int, int]]:
    """{(month, year)} for a section's chart endpoints plus its year-ago point
    — `first_ts`/`last_ts`/`ts_1y_ago` are the only three dates the digest
    exposes, so they are the only three a chart sentence can honestly name."""
    periods: set[tuple[int, int]] = set()
    if not isinstance(series_summary, dict):
        return periods
    for digest in series_summary.values():
        if not isinstance(digest, dict):
            continue
        for field in ("first_ts", "last_ts", "ts_1y_ago"):
            d = _parse_iso_date(digest.get(field))
            if d is not None:
                periods.add((d.month, d.year))
    return periods


def _history_fact_entries(history_facts: Any) -> list[dict[str, Any]]:
    """Normalized allowed-value entries for a section's `history_facts`.

    `reference_value_formatted` is a DISPLAY string ("10.9%", "$3.61bn",
    "103.55"), so it is parsed with the same `_extract_money_percent_tokens`
    used on prose — that guarantees a phrase quoted verbatim normalizes
    identically to the token extracted back out of it. Bare numbers ("103.55")
    yield no token and are simply not admitted, matching the extractor's own
    "bare numbers are out of scope" rule on the prose side.
    """
    entries: list[dict[str, Any]] = []
    if not isinstance(history_facts, list):
        return entries
    for fact in history_facts:
        if not isinstance(fact, dict):
            continue
        formatted = fact.get("reference_value_formatted")
        if not isinstance(formatted, str):
            continue
        for token in _extract_money_percent_tokens(formatted):
            entries.append({
                "category": token["category"],
                "currency": token["currency"],
                "normalized_value": token["normalized_value"],
            })
    return entries


def _history_fact_periods(history_facts: Any) -> set[tuple[int, int]]:
    """{(month, year)} for each history fact's `reference_as_of` — the month
    a "highest since <month>" phrase legitimately names."""
    periods: set[tuple[int, int]] = set()
    if not isinstance(history_facts, list):
        return periods
    for fact in history_facts:
        if not isinstance(fact, dict):
            continue
        d = _parse_iso_date(fact.get("reference_as_of"))
        if d is not None:
            periods.add((d.month, d.year))
    return periods


def _grounding_entries(raw_section: Any) -> list[dict[str, Any]]:
    """Every non-metric allowed value a section carries: chart digest + history
    facts. Kept separate from `_build_allowed_values` so these never feed its
    pairwise-diff derivation (see the scope-boundary note above)."""
    if not isinstance(raw_section, dict):
        return []
    return (
        _series_summary_entries(raw_section.get("series_summary"))
        + _history_fact_entries(raw_section.get("history_facts"))
    )


# The policy corridor. These three are not "the BB section's numbers" — they
# are the levels the WHOLE brief is written against, so any section may cite
# them: "the front stays below the 9.5% policy" (tbond, issue 206) is correct
# prose that the per-section checker had nothing to match it to.
#
# Scoped to an explicit id allowlist rather than "any section may cite any other
# section's metrics". That looser rule would roughly tenfold the accepted set
# (~38 metrics across 12 sections) and is exactly the widening #171 warned
# against: a checker that accepts too much still LOOKS like it is working.
# Anchors are appended alongside the grounding entries and therefore never feed
# `_build_allowed_values`'s pairwise-diff derivation.
_CORRIDOR_ANCHOR_IDS: frozenset[str] = frozenset({
    "bb_policy_rate",  # the repo rate — the corridor's midpoint
    "bb_sdf",          # standing deposit facility — the floor
    "bb_slf",          # standing lending facility — the ceiling
})


def _corridor_anchor_entries(
    raw_sections_by_slug: dict[str, dict[str, Any]], *, exclude_slug: str | None = None
) -> list[dict[str, Any]]:
    """Normalized values for the corridor anchors, wherever they live.

    `exclude_slug` skips the section that already has them in its own metric
    list (bb), so they are not counted twice for it.
    """
    out: list[dict[str, Any]] = []
    for slug, raw_section in sorted(raw_sections_by_slug.items()):
        if slug == exclude_slug or not isinstance(raw_section, dict):
            continue
        for m in raw_section.get("metrics") or []:
            if m.get("id") not in _CORRIDOR_ANCHOR_IDS:
                continue
            norm = _normalize_metric_value(m.get("unit", ""), m.get("value"))
            if norm is not None:
                out.append(norm)
    return out


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
    # Issue-206 fix: the cap exists to undo SUFFIX inflation — "$3bn" buying a
    # ±500mn band purely because `bn` is a coarse unit. An UNSUFFIXED price
    # (scale 1.0) has no such inflation to undo: half a dollar on "$7" is just
    # half a dollar. Yet the cap (1% = $0.07) crushed the widened ulp anyway,
    # which made the "~" approximation marker completely INERT for currency —
    # we shipped a marker and then neutralised it. "Brent–WTI spread ~$7"
    # against a true 7.24 was flagged despite being correct, honestly rounded,
    # and explicitly marked as rounded.
    #
    # Deliberately requires BOTH conditions, because either alone is unsafe:
    #   - "~Tk3.5tn" (approx, scale 1e6) would otherwise buy a ±Tk1tn band;
    #   - "$7" with no "~" reads as exact, so it stays capped.
    # "$3bn" (no marker, scale 1e3) keeps its flag — that is the round
    # rhetorical-threshold class #171 chose to leave visible, unchanged here.
    if token.get("approx") and token.get("scale") == 1.0:
        return base
    magnitude = abs(entry["normalized_value"])
    floor = 0.005 * magnitude
    cap = 0.01 * magnitude
    return min(max(base, floor), cap)


def _same_bucket(token: dict[str, Any], entry: dict[str, Any]) -> bool:
    """Whether a prose token and a normalized candidate are comparable at all:
    same category, and same currency when BOTH sides name one. The rule
    `_best_match` applies inline; named here so `check_year_ago_claims` shares
    it rather than restating it."""
    if entry["category"] != token["category"]:
        return False
    return not (
        token["currency"] is not None
        and entry["currency"] is not None
        and token["currency"] != entry["currency"]
    )


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


# Matches pipeline_v6._REAL_POLICY_RATE_SUB_MARKER exactly — the same
# mechanism as the import-cover marker above, one metric later.
# `_stamp_real_policy_rate_sub` deterministically stamps the macro Real
# Policy Rate metric's `sub` with its own arithmetic ("9.50% repo (30 Jul
# cut) − 8.32% Jul p2p CPI"), sourced from the raw builder metric's OWN
# `source`.
#
# CORRECTED in the 2026-08-27 review round. An earlier version of this
# comment claimed BOTH legs are untraceable "because the corridor anchor
# entries only reach *other* sections". That is wrong:
# `_corridor_anchor_entries` is called with `exclude_slug=section.slug`, so
# for the macro section it INCLUDES the bb section's repo/SDF/SLF anchors —
# the repo leg is already reachable and needs no exemption. The leg that
# genuinely needs one is the p2p CPI print: it is an INPUT to the
# derivation, published by macro under no metric of its own, so it traces to
# nothing. The month tokens ("30 Jul cut", "Jul p2p CPI") need the same
# treatment — a stamp the pipeline wrote itself is not a hallucination to
# catch.
_REAL_POLICY_RATE_SOURCE_MARKER = "p2p cpi"

# The exact-cased markers the pipeline stampers slice on. Detection stays
# case-insensitive (the predicates above); the SLICE mirrors what
# `pipeline_v6` actually wrote, and any case drift returns None — which
# checks the whole field, the safe direction.
_IMPORT_COVER_SLICE_MARKER = "import bill"
_REAL_POLICY_RATE_SLICE_MARKER = "p2p CPI"
# The separator both stampers join their note on when the editor already
# wrote something (`f"{current} · {note}"`).
_MACHINE_SUB_SEPARATOR = " · "


def _is_machine_stamped_real_policy_rate(raw_metric: dict[str, Any]) -> bool:
    src = str(raw_metric.get("source") or "").lower()
    return "repo" in src and _REAL_POLICY_RATE_SOURCE_MARKER in src


def _machine_stamped_note(raw_metric: dict[str, Any]) -> str | None:
    """Reconstruct the EXACT segment a `pipeline_v6` stamper derives from
    this raw metric's `source`, mirroring that stamper's own slicing.

    Returns None when no stamper applies, so the caller checks the whole
    field. Detection is by the raw `source` marker (never the display label)
    so it tracks the mechanism that produces the text.
    """
    src = str(raw_metric.get("source") or "")
    if _is_machine_stamped_dual_period(raw_metric):
        start = src.find("reserves")
        end = src.find(_IMPORT_COVER_SLICE_MARKER)
        if start >= 0 and end > start:
            return src[start:end + len(_IMPORT_COVER_SLICE_MARKER)]
    if _is_machine_stamped_real_policy_rate(raw_metric):
        start = src.find("(") + 1
        end = src.find(_REAL_POLICY_RATE_SLICE_MARKER)
        if start > 0 and end > start:
            return src[start:end + len(_REAL_POLICY_RATE_SLICE_MARKER)]
    return None


def _editor_written_sub(pub_sub: str, raw_metric: dict[str, Any] | None) -> str:
    """The part of a published `sub` the EDITOR wrote.

    REVIEW FIX (2026-08-27). Both stampers APPEND — `f"{current} · {note}"` —
    so a whole-field exemption stopped checking the editor's own prose in any
    sub that also carried a stamp. That is strictly worse than having no
    stamp at all: the editor's numbers are exactly what this gate exists to
    check, and the machine's are the only ones that never needed checking.
    Probe that found it: an editor sub reading "…up from 0.34% in June and
    99.9% off the 2023 peak. · 9.50% repo − 8.32% Jul p2p CPI" produced ZERO
    warnings under the whole-field exemption; 0.34%, 99.9% and an invented
    month all sailed through.

    So: remove exactly the machine segment (plus the separator it was joined
    with) and hand the remainder back to be checked normally. When the
    published text does not contain the reconstructed segment — the editor
    wrote its own version rather than the stamper appending one — nothing is
    removed and the whole field is checked.
    """
    if raw_metric is None:
        return pub_sub
    note = _machine_stamped_note(raw_metric)
    if not note:
        return pub_sub
    idx = pub_sub.find(note)
    if idx < 0:
        return pub_sub
    start = idx
    if pub_sub[:idx].endswith(_MACHINE_SUB_SEPARATOR):
        start = idx - len(_MACHINE_SUB_SEPARATOR)
    return (pub_sub[:start] + pub_sub[idx + len(note):]).strip()


# ─── count-claim pattern ───────────────────────────────────────────────────
# Round-2 corpus replay (25 real issues, #180-#204): narrowed from
# (reads|prints|sessions|days) to (reads|prints) — "days" and "sessions"
# contributed ZERO true positives across the corpus and "days" produced a
# real false positive ("BB hasn't published reserves in 14 days" — a plain
# duration statement, not an invented observation count). With this narrower
# noun list: 17 true positives across 9 issues (#184, #197-#204; 16 fiscal
# section hits across #197-#204 plus one in issue #184's fx.chart_read.context,
# "held 122.85 for fourteen prints"), 0 false positives. This is a TRIPWIRE
# on the common surface forms, not an exhaustive ban — "for twelve reads"
# ("twelve" doesn't end in "teen"/"ty") and "through fourteen reads"
# ("through" isn't in the preposition alternation) both pass uncaught.
_COUNT_CLAIM_RE = re.compile(
    r"(?:across|for|in)\s+(?:\w+teen|\w+ty|\d+)\s+(?:reads|prints)\b",
    re.IGNORECASE,
)


# ─── BLOCK-mode check (the only one) ───────────────────────────────────────


def check_count_claims(final_brief: Any) -> None:
    """Blocks any sourceless "across/for/in N reads/prints" claim anywhere in
    the brief's prose (audit #204's "fourteen reads"). The ONLY unconditional
    BLOCK in this module — a tripwire on the common surface forms (see
    `_COUNT_CLAIM_RE`'s comment for the confirmed gaps), not an exhaustive
    ban. Round-2 corpus replay: 17/17 true positives, 0 false positives
    across 9 of 25 real published issues (the other 16 have no such
    phrasing at all)."""
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


# ─── hyphenated-attributive count claim (issue 206; BLOCK in dse 2026-08-28) ──
# Round-2 (#204) narrowed `_COUNT_CLAIM_RE` to the PREPOSITIONAL shape
# ("across ten sessions"). Issue 205/206 printed the SAME invented-count
# defect in a different surface shape — the hyphenated ATTRIBUTIVE form ("a
# ten-session low", "12-day streak") — which that regex cannot match at all
# (no preposition, and "ten" ends in neither "teen" nor "ty").
#
# Golden-corpus replay (tests/fixtures/real_issues/, issues #199-#205, the
# same real published rows the BLOCK-mode check's corpus lives in): **3 true
# positives, 0 false positives.** All 3 are the SAME real issue-205 defect
# this pattern was built to catch, repeated three ways in one issue —
# `dse.verdict` ("DSEX grinds to a ten-session low on drained turnover"),
# `dse.banker_read.verdict` ("...5,769.71, a ten-session low but..."), and
# `dse.metrics[].sub` ("last session (20 Aug) — a ten-session low"). Issues
# #199-#204 (6 of the 7 fixtures) produce zero hits.
#
# Cannot collide with the plain-duration false positive round 2 already fixed
# ("BB hasn't published reserves in 14 days") — that phrase has no hyphen at
# all, so the two shapes are structurally disjoint, not just tuned apart.
#
# `count`, `unit` and `extreme` are named groups so the claimed NUMBER and the
# claim's SHAPE can both be inspected. The count slot accepts an optional
# hyphenated prefix (`(?:\w+-)?`) so English compounds are captured WHOLE —
# "forty-two-session low" yields "forty-two", not the tail "two". That was a
# live false-block, not a hypothetical: the real DSEX rank is 42, ten of the
# last year's sixty-eight fact-days land in the compound band (22, 23, 24, 28,
# 33, 38, 41, 42), and the editor's register prefers word forms. The
# alternation the count slot replaces (`(?:\w+|\d+)`) was redundant — `\w+`
# already matches a digit run — and the optional prefix only ever WIDENS an
# existing match's span, never creates one, so the set of matched sentences is
# unchanged.
_HYPHENATED_COUNT_CLAIM_RE = re.compile(
    r"\b(?P<count>(?:\w+-)?\w+)-(?P<unit>session|day|week|print|read)s?\s+"
    r"(?P<extreme>low|high|streak|run)\b",
    re.IGNORECASE,
)

# The count words the editor's register actually produces, plus the bare tens.
# Digits are the fact side's own format (`_dsex_session_low_fact` writes
# `f"a {rank}-session"`), so word-vs-digit comparison is NUMERIC, never textual.
_COUNT_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_COUNT_TENS = frozenset({20, 30, 40, 50, 60, 70, 80, 90})


def _parse_count_token(token: str) -> int | None:
    """The integer a count slot names, or None when it names no number at all
    ("a MULTI-session low"). None is not "zero" — it is "nothing to check".

    Handles the English tens-plus-unit compound ("forty-two" -> 42). Anything
    else hyphenated falls back to the TAIL token, which is what the pattern
    used to capture — so a shape this function cannot read is never worse off
    than before, and "risk-free ten-session low" still reads 10.
    """
    token = token.casefold()
    if "-" in token:
        head, _, tail = token.rpartition("-")
        tens, unit = _COUNT_WORDS.get(head), _COUNT_WORDS.get(tail)
        if tens in _COUNT_TENS and unit is not None and 1 <= unit <= 9:
            return tens + unit
        token = tail
    if token.isdigit():
        return int(token)
    return _COUNT_WORDS.get(token)


def _sourced_counts(raw_section: dict[str, Any] | None) -> set[int]:
    """Every count a machine-computed history fact supplies for this section.

    Read from `sections_raw[].history_facts` — the same serialized shape
    `pipeline_v6._to_v6_raw` hands the editor, so what the check accepts is
    exactly what the editor was given to inline. The rank lives ONLY inside
    `phrase`: `history_anchors.HistoryFact` has no rank field (its structured
    fields are metric_id/kind/phrase/reference_value*/reference_as_of), so the
    phrase is re-scanned with the SAME regex the claim is matched by — one
    pattern, one definition of "a count claim", both sides.
    """
    if not raw_section:
        return set()
    facts = raw_section.get("history_facts") or []
    counts: set[int] = set()
    for fact in facts:
        phrase = (
            fact.get("phrase") if isinstance(fact, dict)
            else getattr(fact, "phrase", None)
        )
        for match in _HYPHENATED_COUNT_CLAIM_RE.finditer(str(phrase or "")):
            value = _parse_count_token(match.group("count"))
            if value is not None:
                counts.add(value)
    return counts


# Sections where an unmatched hyphenated count claim HOLDS THE PUBLISH rather
# than warning. Owner-approved 2026-08-28, deliberately scoped to `dse` and
# not the whole brief, on two facts that hold there and nowhere else:
#
#   1. `dse` has four fabricated editions ON THE RECORD — "a ten-session low"
#      shipped byte-identical across issues 205-208 while the true rank ran
#      38 -> 41 -> 42. This is a demonstrated, repeating production defect,
#      not a hypothetical.
#   2. Since PR #185 the pipeline FEEDS `dse` a real machine-computed rank
#      (`pipeline_v6._dsex_session_low_fact`) through the history-facts-
#      verbatim contract. An honest alternative now exists, so a claim that
#      matches neither that fact nor any other sourced count in the section
#      is a fabrication BY CONSTRUCTION, not merely an unverifiable figure.
#
# Every other section fails test 2: nothing supplies it a count of any kind,
# so a finding there means "unverifiable", not "invented", and it stays WARN.
# Add a slug here only once that section has its own machine-fed count. `bb`
# and `tbond` look superficially similar and are NOT candidates: their prose is
# dense with instrument names wearing this exact shape ("the 14-day call money
# rate", "the 91-day T-Bill"), counted 25 times across 15 real issues.
_HYPHENATED_COUNT_BLOCK_SLUGS = frozenset({"dse"})

# Which SHAPE of claim a block slug can hold the publish over. Narrower than
# the pattern the check warns on, and the narrowing is not a hedge — it is
# what the supply side can actually answer:
#
#   * `_dsex_session_low_fact` emits a `since_lower` rank and nothing else, so
#     a HIGH / STREAK / RUN claim has no possible sourced counterpart. Blocking
#     one would be unclearable by an honest editor: the publish holds on a
#     sentence with no correct alternative to write.
#   * DAY and WEEK forms are ordinary derivable market prose ("a 52-week low"
#     is computable from any price series and needs no supplied count), while
#     `session`/`print`/`read` are OBSERVATION counts — the same three nouns
#     the count-claim family has always treated as invented-by-default.
#
# Demonstrated, not theorised: before this narrowing, "a 52-week low", "a
# five-session high" and "a three-day run of declines" each held the publish
# through the real gate. Corpus-verified: narrowing keeps 13/13 real true
# positives across issues #205-#208 (all of them session-lows) and removes the
# entire legitimate-phrase false-block surface. Everything outside this shape
# still WARNs, everywhere, exactly as before.
_BLOCKABLE_COUNT_UNITS = frozenset({"session", "print", "read"})
_BLOCKABLE_COUNT_EXTREME = "low"


def _is_blockable_shape(match: "re.Match[str]") -> bool:
    return (
        match.group("unit").lower() in _BLOCKABLE_COUNT_UNITS
        and match.group("extreme").lower() == _BLOCKABLE_COUNT_EXTREME
    )


def check_hyphenated_count_claims(
    final_brief: Any,
    raw_sections_by_slug: dict[str, dict[str, Any]] | None = None,
) -> list[NumberWarning]:
    """Sibling of `check_count_claims` for the hyphenated-attributive
    count-claim shape. Scans the SAME prose surface as the BLOCK-mode check
    (`_collect_prose_fields`), since it is the same invented-count defect
    wearing a different shape.

    A claim is LEGITIMATE when its number matches a count supplied by that
    section's own machine-computed history facts (`_sourced_counts`) — the
    only place in the whole payload a count of observations ever comes from
    (no builder emits a count field; that is the premise the original check
    was built on). Legitimate claims produce nothing: no warning, no block.

    An unmatched claim BLOCKS — raising `ProseNumberViolationError`, the same
    error family `check_count_claims` raises, so it reaches `cli.py`'s exit
    code 4 through `pipeline_v6._run_prose_number_gate` — only when ALL THREE
    hold: its section is in `_HYPHENATED_COUNT_BLOCK_SLUGS`, its count parses
    to a number, and its shape is one the supply side can actually answer
    (`_is_blockable_shape` — session/print/read + "low"). Everything else is
    collected as a WARN, exactly as it has been since PR #175.

    Two deliberate scope limits on the BLOCK: a count slot naming no number
    ("a multi-session low") has no figure to compare and no fabricated rank to
    hold a publish over, and a shape with no possible sourced counterpart
    ("a 52-week low", "a five-session high") could never be cleared by an
    honest editor. Both warn instead.

    ACCEPTED RISK, on the record. The supply side fails OPEN and the claim
    side now fails CLOSED. `_fetch_series_summaries` swallows a fetch failure
    and yields no facts (deliberately — the editor still runs without chart
    grounding), while an unmatched session-low claim here holds the publish.
    So a transient Supabase hiccup plus a habitual phrase is a held edition.
    The exposure is bounded by how often a fact exists at all: on the real
    series a fact is available roughly 31% of mornings (63.1% of days the rank
    is under `LOOKBACK_MIN`, 5.5% are window lows — both suppress the fact by
    design, and on those mornings there is no honest rank to print either).
    Judged the right trade: the failure mode is a held publish, which is
    visible and recoverable, versus four editions of a fabricated figure,
    which was neither.

    A residual, named rather than hidden: legitimacy is matched on the NUMBER
    alone, so a WARN-class shape reusing a sourced number ("a 42-week low"
    beside a 42-session fact) passes silently. Those shapes cannot block
    anyway, so the cost is one missing log line.

    `raw_sections_by_slug` defaults to empty — a caller with no raw sections
    can still run the pattern, it simply has no fact to legitimize anything
    with.
    """
    from brief.pipeline_v6 import _collect_prose_fields  # lazy: avoids the import cycle

    raw_by_slug = raw_sections_by_slug or {}
    sourced_by_section: dict[str, set[int]] = {}
    warnings: list[NumberWarning] = []
    for field_path, text in _collect_prose_fields(final_brief):
        section = field_path.split(".", 1)[0]
        if section not in sourced_by_section:
            sourced_by_section[section] = _sourced_counts(raw_by_slug.get(section))
        sourced = sourced_by_section[section]
        # Every claim in the field, not just the first: a sourced claim must
        # never shield a fabricated one sitting behind it in the same string.
        # At most ONE warning per field is still emitted, preserving the
        # per-field counting the golden-corpus replay pins.
        for match in _HYPHENATED_COUNT_CLAIM_RE.finditer(text):
            claimed = _parse_count_token(match.group("count"))
            if claimed is not None and claimed in sourced:
                continue
            if (
                section in _HYPHENATED_COUNT_BLOCK_SLUGS
                and claimed is not None
                and _is_blockable_shape(match)
            ):
                known = (
                    "machine-supplied counts here: "
                    + ", ".join(str(c) for c in sorted(sourced))
                    if sourced else "no sourced count exists for this section"
                )
                raise ProseNumberViolationError(
                    f"prose-number gate: hyphenated count-claim "
                    f"{match.group(0)!r} at {field_path!r} — {section!r} is a "
                    f"BLOCK-scoped section and this count matches no "
                    f"machine-supplied history fact ({known}). No builder "
                    "emits a count field; an unsourced count here is invented "
                    "(issues 205-208, 'a ten-session low' byte-identical "
                    "across four editions while the real rank ran 38-42). "
                    "Publish held."
                )
            warnings.append(NumberWarning(
                kind="hyphenated_count_claim",
                section=section,
                field_path=field_path,
                matched_text=match.group(0),
                normalized_value=float(claimed) if claimed is not None else 0.0,
                category="count",
                nearest_value=None,
                nearest_delta=None,
            ))
            break
    return warnings


# ─── WARN-mode: card period vs its own chart series (issue 206, item 4) ────
# The CPI honesty regression: `macro`'s food/non-food cards printed June
# while the chart plotted UNDER them showed July's unofficial archive
# figure — same section, same series key, two different months, and nothing
# anywhere flagged the disagreement to a reader.
#
# WARN, not FAIL, for one cycle — a deliberate task decision, not the
# original root-cause investigation's FAIL-mode recommendation. Promote to
# BLOCK only after production WARN-log volume confirms this fires on real
# defects and nothing else, matching `check_count_claims`'s own staging
# discipline (AGENTS.md landmine 34) before IT was allowed to hold a
# publish.
_PROMOTE_CARD_VS_CHART_WARN_TO_BLOCK = False


def check_card_period_vs_chart_series(
    final_brief: Any, raw_sections_by_slug: dict[str, dict[str, Any]],
) -> list[NumberWarning]:
    """WARN when a published metric's own period (`as_of`, from the raw
    builder metric — never the published row, which carries no `as_of` at
    all) is OLDER than the newest point its OWN section's chart plots for
    the SAME series key (the raw metric's `id`, matched against
    `series_summary`'s digest keys).

    Directional by design: a card NEWER than its chart (the chart
    legitimately lagging — the two are separate fetches ~10-15 minutes
    apart, see `_fetch_series_summaries`'s docstring) is not a lie about the
    card's own period and must not warn. Only "older" is the honesty
    violation this exists to catch — a reader believing a card describes a
    more recent read than the chart under it actually supports.

    Skips any metric whose id has no matching series_summary key (no chart,
    or a digest fetch that degraded) — a disagreement check, not a presence
    check, same convention as
    `pipeline_v6._check_daily_as_of_vs_series_summary`'s daily-cadence
    sibling."""
    warnings: list[NumberWarning] = []
    for section in final_brief.sections:
        raw_section = raw_sections_by_slug.get(section.slug)
        if raw_section is None:
            continue
        summary = raw_section.get("series_summary") or {}
        raw_by_label = _raw_metric_by_label(raw_section.get("metrics") or [])
        for i, pub_metric in enumerate(section.metrics):
            raw_metric = raw_by_label.get(_normalize_label(pub_metric.label))
            if raw_metric is None:
                continue
            mid = raw_metric.get("id")
            digest = summary.get(mid)
            if not digest:
                continue
            last_ts = digest.get("last_ts")
            card_period = raw_metric.get("as_of")
            if not last_ts or not card_period:
                continue
            if str(card_period) >= str(last_ts):  # ISO dates — lexicographic == chronological
                continue
            warnings.append(NumberWarning(
                kind="card_vs_chart_period",
                section=section.slug,
                field_path=f"{section.slug}.metrics[{i}]",
                matched_text=(
                    f"card period {card_period} is older than its own chart's "
                    f"newest plotted point {last_ts}"
                ),
                normalized_value=0.0,
                category="period",
                nearest_value=None,
                nearest_delta=None,
            ))
    return warnings


# ─── WARN-mode: "a year earlier" naming the window start (issues 207/208) ──
# The defect is a LABEL, not a number. `summarize_series_points` used to hand
# the editor only {n, first/last, min, max}, so the only backward-looking
# figure it had was `first_value` — the START of the window. On
# `cpi_12m_avg_monthly` that window is 24 MONTHS long, so "down from 9.95% a
# year earlier" cited an Aug-2024 figure as a Jul-2025 one; the true year-ago
# point was 9.77. Every existing check passed it, correctly: 9.95 really is in
# the digest. Nothing was comparing the figure to the PERIOD claimed for it.
#
# The pipeline half of this fix adds `value_1y_ago`/`ts_1y_ago` to the digest,
# so there is now an honest number to cite. This check catches prose that
# still points at the window start.
#
# Deliberately narrow, for precision: it fires ONLY when the nearest figure in
# the same clause matches `first_value` AND fails `value_1y_ago`. A digest with
# no year-ago point says nothing (no honest alternative exists to name), and a
# digest whose two values coincide says nothing (nothing to distinguish).
# WARN-mode, like every check here except `check_count_claims` — AGENTS.md
# landmine 34.
#
# Golden-corpus replay (tests/fixtures/real_issues/, issues #199-#205): 1 true
# positive, 0 false positives. The hit is issue #205's real
# `macro.chart_read.signal` — "CPI 12m-avg eased to 8.66% as of the Jul 2026
# print — down from 9.95% a year earlier" — against a digest whose window
# starts 2024-08-01 at 9.95 and whose year-ago point is 9.77 at 2025-07-01.
# #199-#203 carry the phrase zero times; #204 carries it zero times.
#
# KNOWN SCOPE LIMIT, inherited not introduced: the same issue's
# `dse.chart_read.signal` ("up from 5,389.17 a year earlier") is NOT checked,
# because a bare index number carries no currency symbol and no unit suffix and
# `_extract_money_percent_tokens` skips those by design (module docstring). A
# bare digit is far more often a year or a count than a value assertion;
# widening the extractor for this check would trade one wrong number for a lot
# of noise everywhere else.
_YEAR_AGO_PHRASE_RE = re.compile(r"\ba year (?:earlier|ago|back)\b", re.IGNORECASE)

# Clause separators. A decimal point never matches: `[.;:!?]` must be followed
# by whitespace, and "9.95" has a digit there. The em/en dashes are Master.md's
# sentence separators, always spaced.
_CLAUSE_BOUNDARY_RE = re.compile(r"[.;:!?]\s+|\s+[—–]\s+")


def _clause_bounds(text: str, at: int) -> tuple[int, int]:
    """(start, end) of the clause containing offset `at`."""
    start, end = 0, len(text)
    for m in _CLAUSE_BOUNDARY_RE.finditer(text):
        if m.end() <= at:
            start = m.end()
        elif m.start() >= at:
            end = m.start()
            break
    return start, end


def _nearest_token(clause: str, phrase_at: int) -> dict[str, Any] | None:
    """The currency/percent token closest to `phrase_at` within `clause`."""
    tokens = _extract_money_percent_tokens(clause)
    if not tokens:
        return None
    return min(
        tokens,
        key=lambda t: min(abs(t["span"][0] - phrase_at), abs(t["span"][1] - phrase_at)),
    )


def _section_prose_fields(section: Any) -> list[tuple[str, str]]:
    """(field_path, text) for one section's prose surfaces — the same set
    `check_lede_numbers_against_builder_values` scans, minus `brief.todays_call`
    which belongs to no section and therefore has no digest to check against.

    Deliberately a separate list rather than a refactor of that check's inline
    `_scan` calls: it is the module's most corpus-tested function and rewiring
    its traversal for an unrelated check is not worth the regression risk (the
    same reasoning `_fetch_series_summaries` records for not refactoring
    `_stamp_chart_series`)."""
    fields: list[tuple[str, str]] = []
    for name in _LEDE_SIMPLE_FIELDS:
        text = getattr(section, name, None)
        if text:
            fields.append((f"{section.slug}.{name}", text))
    banker_read = getattr(section, "banker_read", None)
    if banker_read is not None:
        if banker_read.verdict:
            fields.append((f"{section.slug}.banker_read.verdict", banker_read.verdict))
        for i, w in enumerate(banker_read.watch or []):
            if w:
                fields.append((f"{section.slug}.banker_read.watch[{i}]", w))
        for i, r in enumerate(banker_read.risk or []):
            if r:
                fields.append((f"{section.slug}.banker_read.risk[{i}]", r))
    chart_read = getattr(section, "chart_read", None)
    if chart_read is not None:
        for name in ("signal", "context", "implication"):
            text = getattr(chart_read, name, None)
            if text:
                fields.append((f"{section.slug}.chart_read.{name}", text))
    return fields


def check_year_ago_claims(
    final_brief: Any, raw_sections_by_slug: dict[str, dict[str, Any]]
) -> list[NumberWarning]:
    """WARN when a figure labelled "a year earlier/ago/back" is the section
    chart's WINDOW START rather than its year-ago point. See the block comment
    above for the corpus story and the deliberate narrowness."""
    warnings: list[NumberWarning] = []
    for section in final_brief.sections:
        raw_section = raw_sections_by_slug.get(section.slug)
        if not isinstance(raw_section, dict):
            continue
        summary = raw_section.get("series_summary")
        if not isinstance(summary, dict):
            continue

        # (first_value_entry, year_ago_entry, first_ts, ts_1y_ago) per series
        pairs: list[tuple[dict[str, Any], dict[str, Any], Any, Any]] = []
        for key, digest in summary.items():
            if not isinstance(digest, dict):
                continue
            unit = _series_key_unit(str(key))
            if unit is None:
                continue
            first = _normalize_metric_value(unit, digest.get("first_value"))
            year_ago = _normalize_metric_value(unit, digest.get("value_1y_ago"))
            if first is None or year_ago is None:
                continue
            if first["normalized_value"] == year_ago["normalized_value"]:
                # The window start IS the year-ago point — nothing to mislabel.
                continue
            pairs.append((first, year_ago, digest.get("first_ts"), digest.get("ts_1y_ago")))
        if not pairs:
            continue

        for field_path, text in _section_prose_fields(section):
            for phrase in _YEAR_AGO_PHRASE_RE.finditer(text):
                start, end = _clause_bounds(text, phrase.start())
                token = _nearest_token(text[start:end], phrase.start() - start)
                if token is None:
                    continue
                for first, year_ago, first_ts, ts_1y_ago in pairs:
                    if not _same_bucket(token, first):
                        continue
                    first_delta = abs(token["normalized_value"] - first["normalized_value"])
                    if first_delta > _effective_tolerance(token, first):
                        continue
                    ago_delta = abs(token["normalized_value"] - year_ago["normalized_value"])
                    if ago_delta <= _effective_tolerance(token, year_ago):
                        continue  # it matches the honest point too — not a mislabel
                    warnings.append(NumberWarning(
                        kind="year_ago_mislabel",
                        section=section.slug,
                        field_path=field_path,
                        matched_text=(
                            f"{token['matched_text']} labelled {phrase.group(0)!r} is the "
                            f"chart's window START ({first_ts}), not its year-ago point "
                            f"({ts_1y_ago})"
                        ),
                        normalized_value=token["normalized_value"],
                        category=token["category"],
                        nearest_value=year_ago["normalized_value"],
                        nearest_delta=ago_delta,
                    ))
                    break
    return warnings


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
        # Subs legitimately cite the chart ("up from a $71.18 window low"),
        # quote history facts ("highest since Apr 2022 (10.9% then)"), and
        # measure against the policy corridor ("below the 9.5% policy").
        allowed = (
            _build_allowed_values(raw_metrics)
            + _grounding_entries(raw_section)
            + _corridor_anchor_entries(raw_sections_by_slug, exclude_slug=section.slug)
        )
        raw_by_label = _raw_metric_by_label(raw_metrics)
        for i, pub_metric in enumerate(section.metrics):
            if not pub_metric.sub:
                continue
            raw_metric = raw_by_label.get(_normalize_label(pub_metric.label))
            # Only the deterministic machine segment is dropped — the
            # editor's own prose in the same field is still checked.
            sub_text = _editor_written_sub(pub_metric.sub, raw_metric)
            if not sub_text:
                continue
            for token in _extract_money_percent_tokens(sub_text):
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
        # A history fact's own as-of month is the month "highest since Apr
        # 2022 (10.9% then)" names — and the prompt REQUIRES that phrase be
        # woven in verbatim, so omitting it made following the prompt a
        # guaranteed WARN. Chart endpoints are deliberately NOT added here:
        # a metric's `sub` describes the metric, and no false positive in the
        # issue-205 corpus came from a sub naming a chart endpoint's month.
        periods = _section_periods(raw_metrics) | _history_fact_periods(
            raw_section.get("history_facts")
        )
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
            # `_stamp_import_cover_sub` deliberately names TWO different
            # months by construction, and `_stamp_real_policy_rate_sub` names
            # the CPI month and the MPC decision month — deterministic
            # pipeline output, not hallucinations to catch. Only that segment
            # is dropped; an invented month in the editor's own half of the
            # same field still warns.
            sub_text = _editor_written_sub(pub_metric.sub, raw_metric)
            if not sub_text:
                continue
            for match in _MONTH_TOKEN_RE.finditer(sub_text):
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
    # `chart_read.*` is BY DEFINITION about the chart, and #167's prompt
    # requires it be derived from `series_summary` — so the digest values
    # have to be in scope here or every chart line WARNs (27 of issue 205's
    # 62 did). Union across sections, matching this check's existing
    # cross-section scope for metric values.
    allowed = _build_allowed_values(all_raw_metrics)
    for raw_section in raw_sections:
        allowed = allowed + _grounding_entries(raw_section)
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
    """The two BLOCK-capable checks run FIRST, adjacent, so a hold never
    depends on what some WARN-mode check did before it:
    `check_count_claims` (raises unconditionally, anywhere in the brief),
    then `check_hyphenated_count_claims` (raises only for a section in
    `_HYPHENATED_COUNT_BLOCK_SLUGS` whose count matches no machine-supplied
    history fact — owner-approved 2026-08-28; WARN everywhere else, and its
    WARN findings still join the collected list below).

    Then every remaining WARN-mode check runs and its findings are collected
    into one list. When `strict` (BRIEF_PROSE_VALIDATOR_STRICT=1), the first
    collected warning is escalated to a raise instead of being returned — a
    documented future flip, not this PR's default (see module docstring)."""
    check_count_claims(final_brief)

    raw_by_slug = {s["slug"]: s for s in raw_sections if "slug" in s}
    warnings: list[NumberWarning] = []
    warnings.extend(check_hyphenated_count_claims(final_brief, raw_by_slug))
    warnings.extend(check_metric_sub_numbers(final_brief, raw_by_slug))
    warnings.extend(check_metric_sub_periods(final_brief, raw_by_slug))
    warnings.extend(check_metric_value_vs_raw(final_brief, raw_by_slug))
    warnings.extend(check_lede_numbers_against_builder_values(final_brief, raw_sections))
    warnings.extend(check_card_period_vs_chart_series(final_brief, raw_by_slug))
    warnings.extend(check_year_ago_claims(final_brief, raw_by_slug))

    if warnings and strict:
        raise ProseNumberViolationError(
            f"prose-number gate (STRICT — BRIEF_PROSE_VALIDATOR_STRICT=1): "
            f"{warnings[0].describe()}. Publish held."
        )
    return warnings
