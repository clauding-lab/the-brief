"""Unit tests for brief/validators/prose_numbers.py — the P2 fact-checker.

Round-2 reshape: BLOCK is now `check_count_claims` ONLY (25-real-issue
corpus replay: 14 TP, 0 FP). `check_metric_sub_numbers`,
`check_metric_sub_periods`, `check_metric_value_vs_raw`, and
`check_lede_numbers_against_builder_values` are WARN-mode — they return
`list[NumberWarning]` and never raise (except through the orchestrator's
`strict` escalation). Fixtures reproduce the audit's real findings plus the
concrete corpus defects round 2 caught (missing "trn" unit, machine-stamped
import-cover dual periods, approximation markers, coarse-currency false
passes).
"""
from __future__ import annotations

import pytest

from brief.v6_schema import BriefPayloadV6
from brief.validators.prose_numbers import (
    ProseNumberViolationError,
    check_card_period_vs_chart_series,
    check_count_claims,
    check_hyphenated_count_claims,
    check_lede_numbers_against_builder_values,
    check_metric_sub_numbers,
    check_metric_sub_periods,
    check_metric_value_vs_raw,
    run_prose_number_gate,
)


def _brief(sections: list[dict]) -> BriefPayloadV6:
    return BriefPayloadV6.model_validate({
        "brief": {"issue_no": 204, "volume": 1, "brief_date": "2026-08-22"},
        "sections": sections,
    })


def _raw_section(slug: str, metrics: list[dict]) -> dict:
    return {"slug": slug, "metrics": metrics}


# ─── BLOCK: count-claims — the ONLY unconditional BLOCK post-round-2 ───────


def test_block_count_claim_fourteen_reads():
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "verdict": "Flat across fourteen reads — corridor unchanged.",
    }])
    with pytest.raises(ProseNumberViolationError, match=r"fourteen reads"):
        check_count_claims(brief)


def test_block_count_claim_fourteen_prints():
    brief = _brief([{
        "slug": "fiscal", "ord": 8, "title": "Fiscal", "group_key": "policy",
        "weight": 1,
        "banker_read": {
            "verdict": "The fiscal read stays frozen at Tk3.61tn, unmoved for a while now.",
            "watch": ["The next monthly NBR print — flat in fourteen prints so far"],
            "risk": ["Slippage against the full-year target"],
        },
    }])
    with pytest.raises(ProseNumberViolationError, match=r"fourteen prints"):
        check_count_claims(brief)


def test_count_claim_passes_when_no_such_phrase_present():
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "verdict": "Corridor holds at 9.50%, unchanged since the 30 Jul cut.",
    }])
    check_count_claims(brief)  # must not raise


def test_count_claim_narrowed_nouns_no_longer_flag_a_plain_duration_statement():
    """Round-2 corpus fix: 'in 14 days' is a plain duration statement, not an
    invented observation count. Dropping 'days'/'sessions' from the noun
    list was the fix for this exact real false positive
    (`tests/test_pipeline_v6_freshness_propagation.py`'s own fixture)."""
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "tldr": "BB hasn't published reserves in 14 days.",
    }])
    check_count_claims(brief)  # must not raise


def test_count_claim_narrowed_nouns_no_longer_flag_sessions():
    brief = _brief([{
        "slug": "dse", "ord": 6, "title": "DSE Markets", "group_key": "markets",
        "weight": 1,
        "tldr": "DSEX has drifted sideways across 14 sessions.",
    }])
    check_count_claims(brief)  # must not raise — "sessions" contributed zero TPs, dropped


# ─── WARN: check_hyphenated_count_claims — issue 206's "ten-session low" ───


def test_count_claim_catches_hyphenated_session_low():
    """Issue 205/206 regression: '_COUNT_CLAIM_RE' only matches the
    prepositional form ('across ten sessions'); the hyphenated ATTRIBUTIVE
    form ('a ten-session low') is a different surface shape and passed
    uncaught, printing a count nothing in the pipeline supplies. WARN-only —
    see `_HYPHENATED_COUNT_CLAIM_RE`'s comment for the golden-corpus replay."""
    brief = _brief([{
        "slug": "dse", "ord": 6, "title": "DSE Markets", "group_key": "markets",
        "weight": 1,
        "verdict": "DSEX grinds to a ten-session low on drained turnover.",
    }])
    warnings = check_hyphenated_count_claims(brief)
    assert len(warnings) == 1
    assert warnings[0].kind == "hyphenated_count_claim"
    assert "ten-session low" in warnings[0].matched_text


def test_hyphenated_count_claim_catches_a_day_streak():
    brief = _brief([{
        "slug": "fiscal", "ord": 8, "title": "Fiscal", "group_key": "policy",
        "weight": 1,
        "tldr": "NBR collections have held flat on a 12-day streak.",
    }])
    warnings = check_hyphenated_count_claims(brief)
    assert len(warnings) == 1
    assert "12-day streak" in warnings[0].matched_text


def test_hyphenated_count_claim_does_not_flag_the_plain_duration_form():
    """The known-legit form round 2 already protected — 'in 14 days' has no
    hyphen, so the two shapes can never collide by construction."""
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "tldr": "BB hasn't published reserves in 14 days.",
    }])
    assert check_hyphenated_count_claims(brief) == []


def test_hyphenated_count_claim_passes_clean_prose():
    brief = _brief([{
        "slug": "dse", "ord": 6, "title": "DSE Markets", "group_key": "markets",
        "weight": 1,
        "verdict": "Corridor holds at 9.50%, unchanged since the 30 Jul cut.",
    }])
    assert check_hyphenated_count_claims(brief) == []


def test_orchestrator_includes_hyphenated_count_claims_in_warn_findings():
    raw = [_raw_section("dse", [{"label": "DSEX close", "value": 5722.21, "unit": "index", "as_of": "2026-08-23"}])]
    brief = _brief([{
        "slug": "dse", "ord": 6, "title": "DSE Markets", "group_key": "markets",
        "weight": 1,
        "verdict": "DSEX grinds to a ten-session low on drained turnover.",
    }])
    warnings = run_prose_number_gate(brief, raw, strict=False)
    kinds = {w.kind for w in warnings}
    assert "hyphenated_count_claim" in kinds


# ─── WARN: check_card_period_vs_chart_series — issue 206's CPI cards ──────


def test_card_period_older_than_chart_produces_a_warning():
    """Issue 206 regression: the CPI food card read June while its own
    chart plotted July's unofficial archive figure — the reader sees a card
    and the chart under it naming two different months for the same series,
    with nothing flagging the disagreement. WARN, not FAIL, for one cycle."""
    raw = [{
        "slug": "macro",
        "metrics": [{"id": "cpi_p2p_food_monthly", "label": "CPI Food (P-to-P)",
                     "cadence": "monthly", "as_of": "2026-06-30"}],
        "series_summary": {
            "cpi_p2p_food_monthly": {"last_ts": "2026-07-01", "last_value": 7.16},
        },
    }]
    raw_by_slug = {r["slug"]: r for r in raw}
    brief = _brief([{
        "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "CPI Food (P-to-P)", "value": "8.6%"}],
    }])
    warnings = check_card_period_vs_chart_series(brief, raw_by_slug)
    assert len(warnings) == 1
    assert warnings[0].kind == "card_vs_chart_period"
    assert warnings[0].section == "macro"


def test_card_period_matching_chart_produces_no_warning():
    raw = [{
        "slug": "macro",
        "metrics": [{"id": "cpi_p2p_food_monthly", "label": "CPI Food (P-to-P)",
                     "cadence": "monthly", "as_of": "2026-06-30"}],
        "series_summary": {"cpi_p2p_food_monthly": {"last_ts": "2026-06-30"}},
    }]
    raw_by_slug = {r["slug"]: r for r in raw}
    brief = _brief([{
        "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "CPI Food (P-to-P)", "value": "8.6%"}],
    }])
    assert check_card_period_vs_chart_series(brief, raw_by_slug) == []


def test_card_period_newer_than_chart_is_not_a_lie_and_produces_no_warning():
    """A card NEWER than its own chart's newest point (the chart legitimately
    lagging) is not what this check exists to catch — directional, per its
    own name ('never OLDER than')."""
    raw = [{
        "slug": "macro",
        "metrics": [{"id": "cpi_12m_avg_monthly", "label": "CPI 12m Avg",
                     "cadence": "monthly", "as_of": "2026-07-01"}],
        "series_summary": {"cpi_12m_avg_monthly": {"last_ts": "2026-06-01"}},
    }]
    raw_by_slug = {r["slug"]: r for r in raw}
    brief = _brief([{
        "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "CPI 12m Avg", "value": "8.66%"}],
    }])
    assert check_card_period_vs_chart_series(brief, raw_by_slug) == []


def test_card_period_check_skips_a_metric_with_no_matching_series_key():
    raw = [{
        "slug": "macro",
        "metrics": [{"id": "reer_monthly", "label": "REER", "cadence": "monthly",
                     "as_of": "2026-03-01"}],
        "series_summary": {"cpi_p2p_food_monthly": {"last_ts": "2026-07-01"}},
    }]
    raw_by_slug = {r["slug"]: r for r in raw}
    brief = _brief([{
        "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "REER", "value": "102.78"}],
    }])
    assert check_card_period_vs_chart_series(brief, raw_by_slug) == []


def test_orchestrator_includes_card_period_vs_chart_series_in_warn_findings():
    raw = [{
        "slug": "macro",
        "metrics": [{"id": "cpi_p2p_food_monthly", "label": "CPI Food (P-to-P)",
                     "cadence": "monthly", "as_of": "2026-06-30"}],
        "series_summary": {"cpi_p2p_food_monthly": {"last_ts": "2026-07-01"}},
    }]
    brief = _brief([{
        "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "CPI Food (P-to-P)", "value": "8.6%"}],
    }])
    warnings = run_prose_number_gate(brief, raw, strict=False)
    kinds = {w.kind for w in warnings}
    assert "card_vs_chart_period" in kinds


# ─── WARN: check_metric_sub_numbers ────────────────────────────────────────


def test_warn_stale_flash_figure_presented_as_current():
    """The audit's headline finding: '$2.82bn' sub on a metric whose real
    builder value is 2858.68 (mn USD). WARN-mode post-round-2 — this alone
    no longer holds the publish (that gap is why check_metric_value_vs_raw
    exists — see below)."""
    raw = {"remit": _raw_section("remit", [
        {"label": "Monthly Remittance", "value": 2858.68, "unit": "mn USD", "as_of": "2026-07-31"},
    ])}
    brief = _brief([{
        "slug": "remit", "ord": 11, "title": "Remittance", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Monthly Remittance", "value": "$2.86bn", "sub": "$2.82bn — July final"}],
    }])
    warnings = check_metric_sub_numbers(brief, raw)
    assert len(warnings) == 1
    assert "$2.82bn" in warnings[0].matched_text
    assert warnings[0].section == "remit"
    assert warnings[0].kind == "sub_number"


def test_pass_derived_bp_spread_between_two_section_metrics():
    """'19bp under the 9.50% policy' — call money 9.31 + policy 9.50, both
    real bb.py metrics; the bp figure is a legitimate derived spread."""
    raw = {"bb": _raw_section("bb", [
        {"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"},
        {"label": "Overnight Call Money", "value": 9.31, "unit": "%", "as_of": "2026-08-22"},
    ])}
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "metrics": [{
            "label": "Overnight Call Money", "value": "9.31%",
            "sub": "19bp under the 9.50% policy",
        }],
    }])
    assert check_metric_sub_numbers(brief, raw) == []


def test_pass_half_ulp_tolerance_on_integer_printed_crore_figure():
    """'Tk733cr' against a raw builder value of 732.8318 — half a unit in the
    last printed digit (an integer print tolerates ±0.5)."""
    raw = {"fiscal": _raw_section("fiscal", [
        {"label": "NBR Collections", "value": 732.8318, "unit": "crore BDT", "as_of": "2026-07-31"},
    ])}
    brief = _brief([{
        "slug": "fiscal", "ord": 8, "title": "Fiscal", "group_key": "policy",
        "weight": 1,
        "metrics": [{"label": "NBR Collections", "value": "Tk732.83cr", "sub": "Tk733cr collected in July"}],
    }])
    assert check_metric_sub_numbers(brief, raw) == []


def test_pass_derived_bp_gap_below_a_regulatory_floor():
    """'844bp below the 10% floor' with CAR 1.56 — derived |10-1.56| = 8.44
    (844bp) against two real metrics in the same section."""
    raw = {"banking": _raw_section("banking", [
        {"label": "CAR", "value": 1.56, "unit": "%", "as_of": "2026-06-30"},
        {"label": "Regulatory Floor", "value": 10.0, "unit": "%", "as_of": "2026-06-30"},
    ])}
    brief = _brief([{
        "slug": "banking", "ord": 4, "title": "Banking", "group_key": "banking",
        "weight": 2,
        "metrics": [{"label": "CAR", "value": "1.56%", "sub": "844bp below the 10% floor"}],
    }])
    assert check_metric_sub_numbers(brief, raw) == []


def test_negative_value_with_masterdotmd_minus_glyph_matches_a_signed_raw_value():
    """Master.md mandates the minus GLYPH (−, U+2212) for negatives, not a
    hyphen. A trade-gap deficit sub must compare against the raw value's
    actual sign, not its absolute magnitude."""
    raw = {"fx": _raw_section("fx", [
        {"label": "Trade Gap", "value": -1.62, "unit": "bn USD", "as_of": "2026-06-30"},
    ])}
    brief = _brief([{
        "slug": "fx", "ord": 5, "title": "FX & External", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Trade Gap", "value": "−$1.62bn", "sub": "gap widens to −$1.62bn"}],
    }])
    assert check_metric_sub_numbers(brief, raw) == []


def test_bare_numbers_are_never_flagged_as_value_mismatches():
    raw = {"dse": _raw_section("dse", [{"label": "DSEX", "value": 5257.0, "unit": "index"}])}
    brief = _brief([{
        "slug": "dse", "ord": 6, "title": "DSE Markets", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "DSEX", "value": "5,257.00", "sub": "third straight session of gains"}],
    }])
    assert check_metric_sub_numbers(brief, raw) == []  # "third" has no digit token


# ─── round-2 corpus fixes ───────────────────────────────────────────────────


def test_bdt_trn_unit_matches_its_own_tn_suffixed_sub():
    """Round-2 corpus defect (item 3a): the real fiscal.py unit string is
    'BDT trn' — 'trn' does not contain 'tn' as a substring, so this used to
    fall into a 'plain' bucket that could never match the 'tn'-suffixed
    token a sub would use to restate its OWN value. A fiscal sub honestly
    restating "Tk3.61tn" against a raw value of 3.61 (BDT trn) must pass."""
    raw = {"fiscal": _raw_section("fiscal", [
        {"label": "NBR collected YTD", "value": 3.61, "unit": "BDT trn", "as_of": "2026-06-30"},
    ])}
    brief = _brief([{
        "slug": "fiscal", "ord": 8, "title": "Fiscal", "group_key": "policy",
        "weight": 1,
        "metrics": [{"label": "NBR collected YTD", "value": "Tk3.61tn", "sub": "flat at Tk3.61tn"}],
    }])
    assert check_metric_sub_numbers(brief, raw) == []


def test_approximation_marker_widens_tolerance_to_a_full_unit():
    """Round-2 corpus defect (item 3c): '~8bp' is a deliberate hedge — the
    editor is signalling its OWN precision is coarser than the printed
    decimal count suggests. It must accept a precise 8.6bp derived spread,
    which the standard half-ulp (±0.5bp) would reject."""
    raw = {"bb": _raw_section("bb", [
        {"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"},
        {"label": "Overnight Call Money", "value": 9.414, "unit": "%", "as_of": "2026-08-22"},
    ])}
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "metrics": [{"label": "Overnight Call Money", "value": "9.41%", "sub": "~8bp under policy"}],
    }])
    assert check_metric_sub_numbers(brief, raw) == []


def test_without_approximation_marker_the_same_gap_still_warns():
    """Companion to the above: WITHOUT the '~', the tight half-ulp tolerance
    applies and the same 8.6bp-vs-8bp gap is flagged."""
    raw = {"bb": _raw_section("bb", [
        {"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"},
        {"label": "Overnight Call Money", "value": 9.414, "unit": "%", "as_of": "2026-08-22"},
    ])}
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "metrics": [{"label": "Overnight Call Money", "value": "9.41%", "sub": "8bp under policy"}],
    }])
    assert len(check_metric_sub_numbers(brief, raw)) == 1


def test_coarse_currency_figure_no_longer_gets_a_free_pass():
    """Round-2 corpus defect (item 3d): '$3bn' vs a true 2858.68mn (2.86bn)
    used to pass silently — its own half-ulp (±0.5bn = ±500mn) swallowed a
    141mn gap. The tolerance is now floored at 0.5% and capped at 1% of the
    matched value (28.59mn here), so this now warns."""
    raw = {"remit": _raw_section("remit", [
        {"label": "Monthly Remittance", "value": 2858.68, "unit": "mn USD", "as_of": "2026-07-31"},
    ])}
    brief = _brief([{
        "slug": "remit", "ord": 11, "title": "Remittance", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Monthly Remittance", "value": "$2.86bn", "sub": "$3bn — July final"}],
    }])
    warnings = check_metric_sub_numbers(brief, raw)
    assert len(warnings) == 1
    assert "$3bn" in warnings[0].matched_text


def test_currency_floor_still_allows_a_legitimate_close_rounding():
    """The same floor/cap machinery must not turn honest rounding into a
    false warning: $2.86bn against 2858.68mn (a 1.32mn gap, well inside even
    the tightened 14.29mn floor) still passes."""
    raw = {"remit": _raw_section("remit", [
        {"label": "Monthly Remittance", "value": 2858.68, "unit": "mn USD", "as_of": "2026-07-31"},
    ])}
    brief = _brief([{
        "slug": "remit", "ord": 11, "title": "Remittance", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Monthly Remittance", "value": "$2.86bn", "sub": "$2.86bn — July final"}],
    }])
    assert check_metric_sub_numbers(brief, raw) == []


def test_percent_and_bp_tokens_are_unaffected_by_the_currency_floor_cap():
    """The floor/cap is scoped to currency tokens only (item 3d's explicit
    wording) — a percent figure's plain half-ulp tolerance is unchanged."""
    raw = {"bb": _raw_section("bb", [
        {"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"},
    ])}
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "metrics": [{"label": "Policy Rate", "value": "9.50%", "sub": "holds at 9.50%"}],
    }])
    assert check_metric_sub_numbers(brief, raw) == []


# ─── WARN: check_metric_sub_periods ─────────────────────────────────────────


def test_warn_month_mismatch_july_print_on_june_period_metric():
    raw = {"fx": _raw_section("fx", [
        {"label": "Monthly Exports", "value": 4.20269, "unit": "bn USD", "as_of": "2026-06-30"},
    ])}
    brief = _brief([{
        "slug": "fx", "ord": 5, "title": "FX & External", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Monthly Exports", "value": "$4.20bn", "sub": "July print"}],
    }])
    warnings = check_metric_sub_periods(brief, raw)
    assert len(warnings) == 1
    assert "July" in warnings[0].matched_text
    assert warnings[0].kind == "sub_period"


def test_month_token_without_year_matches_any_year_with_that_month():
    raw = {"remit": _raw_section("remit", [
        {"label": "Monthly Remittance", "value": 2858.68, "unit": "mn USD", "as_of": "2026-07-31"},
    ])}
    brief = _brief([{
        "slug": "remit", "ord": 11, "title": "Remittance", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Monthly Remittance", "value": "$2.86bn", "sub": "Jul print, official"}],
    }])
    assert check_metric_sub_periods(brief, raw) == []


def test_month_token_with_wrong_year_still_warns():
    raw = {"remit": _raw_section("remit", [
        {"label": "Monthly Remittance", "value": 2858.68, "unit": "mn USD", "as_of": "2026-07-31"},
    ])}
    brief = _brief([{
        "slug": "remit", "ord": 11, "title": "Remittance", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Monthly Remittance", "value": "$2.86bn", "sub": "Jul 2025 print"}],
    }])
    warnings = check_metric_sub_periods(brief, raw)
    assert len(warnings) == 1
    assert "Jul 2025" in warnings[0].matched_text


def test_month_token_matches_a_sibling_metrics_period_not_just_its_own():
    raw = {"macro": _raw_section("macro", [
        {"label": "CPI 12m Avg", "value": 5.2, "unit": "%", "as_of": "2026-06-30"},
        {"label": "Import Cover", "value": 6.25, "unit": "months", "as_of": "2026-03-31"},
    ])}
    brief = _brief([{
        "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Import Cover", "value": "6.25", "sub": "on the Mar print"}],
    }])
    assert check_metric_sub_periods(brief, raw) == []  # Mar is a sibling's period


def test_no_periods_available_for_section_is_a_noop():
    """A section with no parseable as_of anywhere just skips the check —
    never a false warning from missing data."""
    raw = {"bb": _raw_section("bb", [{"label": "Policy Rate", "value": 9.5, "unit": "%"}])}
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "metrics": [{"label": "Policy Rate", "value": "9.50%", "sub": "held since the Jul cut"}],
    }])
    assert check_metric_sub_periods(brief, raw) == []


def test_event_cadence_metric_sub_may_name_a_decision_date_unrelated_to_its_restamp():
    """AGENTS.md landmine 24: `bb_policy_rate` is daily-restamped, so its
    `as_of` is always "today" — the corridor's actual decision date (the 30
    Jul MPC cut) has nothing to do with that restamp. A sub naming the real
    decision month must NOT warn as a period mismatch."""
    raw = {"bb": _raw_section("bb", [
        {"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22", "cadence": "event"},
    ])}
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 2,
        "metrics": [{"label": "Policy Rate", "value": "9.50%", "sub": "held since the 30 Jul cut"}],
    }])
    assert check_metric_sub_periods(brief, raw) == []


def test_t_bill_cutoff_rates_are_also_event_cadence_exempted():
    """The exemption is cadence-based, not a hardcoded bb-only rule — the
    three T-Bill cut-off rates (tbond.py) are event-cadence too, restamped
    daily between auctions the same way the policy corridor is."""
    raw = {"tbond": _raw_section("tbond", [
        {"label": "91d T-Bill cut-off", "value": 8.90, "unit": "%",
         "as_of": "2026-08-22", "cadence": "event"},
    ])}
    brief = _brief([{
        "slug": "tbond", "ord": 7, "title": "T-Bonds & T-Bills", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "91d T-Bill cut-off", "value": "8.90%",
                     "sub": "unchanged since the 12 Aug auction"}],
    }])
    assert check_metric_sub_periods(brief, raw) == []


def test_machine_stamped_import_cover_sub_is_exempt_from_the_period_check():
    """Round-2 corpus defect (item 3b): `_stamp_import_cover_sub` (pipeline_v6.py)
    deterministically appends a dual-period note ("reserves 31 Jul ÷ Mar
    import bill") to the macro Import Cover metric — by construction it
    names TWO different months. Detected via the raw metric's OWN `source`
    marker (matching the stamping function's own detection), not via label
    casefold, so it survives a label rename."""
    raw = {"macro": _raw_section("macro", [
        {"label": "Import Cover", "value": 6.25, "unit": "months", "as_of": "2026-03-31",
         "cadence": "monthly", "source": "BB (reserves 31 Jul ÷ Mar import bill)"},
    ])}
    brief = _brief([{
        "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Import Cover", "value": "6.25",
                     "sub": "reserves 31 Jul ÷ Mar import bill"}],
    }])
    assert check_metric_sub_periods(brief, raw) == []


def test_import_cover_exemption_does_not_leak_to_other_macro_metrics():
    """The exemption is per-metric (via its OWN source marker), not
    section-wide — a genuinely wrong month on a SIBLING metric in the same
    section must still warn."""
    raw = {"macro": _raw_section("macro", [
        {"label": "Import Cover", "value": 6.25, "unit": "months", "as_of": "2026-03-31",
         "cadence": "monthly", "source": "BB (reserves 31 Jul ÷ Mar import bill)"},
        {"label": "CPI 12m Avg", "value": 5.2, "unit": "%", "as_of": "2026-06-30", "cadence": "monthly"},
    ])}
    brief = _brief([{
        "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "CPI 12m Avg", "value": "5.2%", "sub": "September print eases further"}],
    }])
    warnings = check_metric_sub_periods(brief, raw)
    assert len(warnings) == 1
    assert "September" in warnings[0].matched_text


# ─── WARN: check_metric_value_vs_raw (new, item 4) ─────────────────────────


def test_value_vs_raw_catches_the_actual_2_82bn_headline_falsehood():
    """The exact gap round 2 identified: the audit's '$2.82bn' falsehood
    lived in the metric's own headline `value`, not `sub` — round 1's checks
    never read `value` at all. This check does."""
    raw = {"remit": _raw_section("remit", [
        {"label": "Monthly Remittance", "value": 2858.68, "unit": "mn USD", "as_of": "2026-07-31"},
    ])}
    brief = _brief([{
        "slug": "remit", "ord": 11, "title": "Remittance", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Monthly Remittance", "value": "$2.82bn"}],
    }])
    warnings = check_metric_value_vs_raw(brief, raw)
    assert len(warnings) == 1
    assert warnings[0].field_path == "remit.metrics[0].value"
    assert warnings[0].kind == "value_vs_raw"


def test_value_vs_raw_passes_when_headline_matches_the_raw_value():
    raw = {"bb": _raw_section("bb", [
        {"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"},
    ])}
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "metrics": [{"label": "Policy Rate", "value": "9.50%"}],
    }])
    assert check_metric_value_vs_raw(brief, raw) == []


def test_value_vs_raw_is_a_noop_when_no_raw_counterpart_exists():
    raw = {"bb": _raw_section("bb", [])}
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "metrics": [{"label": "Policy Rate", "value": "9.50%"}],
    }])
    assert check_metric_value_vs_raw(brief, raw) == []


# ─── WARN: check_lede_numbers_against_builder_values (extended surface) ────


def test_warn_flags_a_lede_figure_with_no_builder_match():
    raw = [_raw_section("bb", [{"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"}])]
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 2,
        "analysis": "The corridor now sits 200bp above the regional median.",
    }])
    warnings = check_lede_numbers_against_builder_values(brief, raw)
    assert len(warnings) == 1
    assert "200bp" in warnings[0].matched_text


def test_warn_does_not_flag_a_figure_that_matches_a_builder_value():
    raw = [_raw_section("bb", [{"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"}])]
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 2,
        "analysis": "The corridor holds at 9.50% this morning.",
    }])
    assert check_lede_numbers_against_builder_values(brief, raw) == []


def test_todays_call_and_tldr_and_verdict_all_scanned():
    raw = [_raw_section("bb", [{"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"}])]
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 2,
        "tldr": "Holding at 9.50% — data-dependent.",
        "verdict": "Holding at 9.50%, tightening bias intact.",
    }])
    brief.brief.todays_call = "The book stays defensive at 9.50% overnight cost of funds."
    assert check_lede_numbers_against_builder_values(brief, raw) == []


def test_banker_read_watch_and_risk_are_now_scanned():
    """Round-2 extension (item 4b): banker_read.* joins the lede surface."""
    raw = [_raw_section("bb", [{"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"}])]
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 2,
        "banker_read": {
            "verdict": "The corridor holds firm against a backdrop of steady liquidity conditions.",
            "watch": ["A jump to 200bp above the regional median would change the calculus"],
            "risk": ["Imported inflation re-accelerating"],
        },
    }])
    warnings = check_lede_numbers_against_builder_values(brief, raw)
    assert len(warnings) == 1
    assert warnings[0].field_path == "bb.banker_read.watch[0]"


def test_chart_read_figures_are_now_scanned():
    """Round-2 extension (item 4b): chart_read.* joins the lede surface."""
    raw = [_raw_section("dse", [{"label": "DSEX", "value": 5257.0, "unit": "index", "as_of": "2026-08-20"}])]
    brief = _brief([{
        "slug": "dse", "ord": 6, "title": "DSE Markets", "group_key": "markets",
        "weight": 1,
        "chart_read": {
            "signal": "DSEX climbed 12% since Q2 2026 on heavy volume.",
            "context": "Third weekly gain since Q2 2026.",
            "implication": "Watch for profit-taking into the weekend.",
        },
    }])
    warnings = check_lede_numbers_against_builder_values(brief, raw)
    assert len(warnings) == 1
    assert warnings[0].field_path == "dse.chart_read.signal"


def test_cpi_12m_avg_chart_read_survives_the_cpi_honesty_truncation():
    """Regression noted in the issue 206 CPI investigation's risk notes: the
    chart_read prose 'CPI 12m-avg eased to 8.66% as of the Jul 2026 print' is
    TRUE — the July 12m-avg point is genuinely official — and must keep
    passing every gate after `fetch_macro_cpi_series` truncates the OTHER
    two CPI series' unofficial July points. `series_summary` here is the
    POST-FIX shape: cpi_12m_avg_monthly still ends July (official, kept);
    the food/non-food series end June (unofficial July, dropped).

    Exercises all three relevant checks, not just `check_lede_numbers_
    against_builder_values` — `check_card_period_vs_chart_series` and
    `_check_daily_as_of_vs_series_summary` were only verified by hand
    before (repair-agent finding); both are asserted here directly so the
    docstring's "must keep passing every gate" claim is actually proven,
    not just believed. `_check_daily_as_of_vs_series_summary` lives in
    `brief.pipeline_v6` and only looks at daily-cadence metrics — these are
    monthly, so it is expected to produce nothing for this fixture; the
    import is local to keep this validator test file's imports scoped to
    `brief.validators`."""
    raw = [{
        "slug": "macro",
        "metrics": [
            {"id": "cpi_12m_avg_monthly", "label": "CPI 12m Avg", "cadence": "monthly",
             "value": 8.66, "unit": "%", "as_of": "2026-07-01"},
            {"id": "cpi_p2p_food_monthly", "label": "CPI Food (P-to-P)", "cadence": "monthly",
             "value": 8.6, "unit": "%", "as_of": "2026-06-30"},
            {"id": "cpi_p2p_nonfood_monthly", "label": "CPI Non-Food (P-to-P)", "cadence": "monthly",
             "value": 9.61, "unit": "%", "as_of": "2026-06-30"},
        ],
        "series_summary": {
            "cpi_12m_avg_monthly": {"n": 2, "first_ts": "2026-06-01", "first_value": 8.32,
                                     "last_ts": "2026-07-01", "last_value": 8.66,
                                     "min": 8.32, "max": 8.66},
            "cpi_p2p_food_monthly": {"n": 1, "first_ts": "2026-06-01", "first_value": 8.6,
                                      "last_ts": "2026-06-01", "last_value": 8.6,
                                      "min": 8.6, "max": 8.6},
            "cpi_p2p_nonfood_monthly": {"n": 1, "first_ts": "2026-06-01", "first_value": 9.61,
                                         "last_ts": "2026-06-01", "last_value": 9.61,
                                         "min": 9.61, "max": 9.61},
        },
    }]
    brief = _brief([{
        "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
        "weight": 1,
        "metrics": [
            {"label": "CPI 12m Avg", "value": "8.66%"},
            {"label": "CPI Food (P-to-P)", "value": "8.6%"},
            {"label": "CPI Non-Food (P-to-P)", "value": "9.61%"},
        ],
        "chart_read": {
            "signal": "CPI 12m-avg eased to 8.66% as of the Jul 2026 print.",
            "context": "The trailing average has cooled from June's 8.32%.",
            "implication": "Headline disinflation continues, food and non-food yet to confirm.",
        },
    }])
    warnings = check_lede_numbers_against_builder_values(brief, raw)
    chart_warnings = [w for w in warnings if w.field_path.startswith("macro.chart_read")]
    assert chart_warnings == [], f"a TRUE chart_read figure warned: {[w.describe() for w in chart_warnings]}"

    raw_by_slug = {r["slug"]: r for r in raw}
    card_vs_chart_warnings = check_card_period_vs_chart_series(brief, raw_by_slug)
    assert card_vs_chart_warnings == [], (
        f"a card older-than-chart warning fired on a fixture where every card "
        f"is >= its own chart's newest point: {[w.describe() for w in card_vs_chart_warnings]}"
    )

    from brief.pipeline_v6 import _check_daily_as_of_vs_series_summary
    daily_warnings = _check_daily_as_of_vs_series_summary(raw)
    assert daily_warnings == [], (
        f"monthly-cadence CPI metrics should never trip the daily-only "
        f"tripwire: {daily_warnings}"
    )


# ─── orchestrator ────────────────────────────────────────────────────────────


def test_orchestrator_raises_on_count_claim_unconditionally():
    raw = [_raw_section("bb", [{"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"}])]
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "verdict": "Flat across fourteen reads — corridor unchanged.",
    }])
    with pytest.raises(ProseNumberViolationError, match=r"fourteen reads"):
        run_prose_number_gate(brief, raw)


def test_orchestrator_default_mode_never_blocks_on_warn_findings():
    """The former audit headline ('$2.82bn') no longer holds the publish by
    itself in default mode — it surfaces as a WARN via the orchestrator's
    combined list, same as every other non-count-claim check."""
    raw = [_raw_section("remit", [
        {"label": "Monthly Remittance", "value": 2858.68, "unit": "mn USD", "as_of": "2026-07-31"},
    ])]
    brief = _brief([{
        "slug": "remit", "ord": 11, "title": "Remittance", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Monthly Remittance", "value": "$2.82bn", "sub": "$2.82bn — July final"}],
    }])
    warnings = run_prose_number_gate(brief, raw, strict=False)
    assert len(warnings) >= 1
    kinds = {w.kind for w in warnings}
    assert "value_vs_raw" in kinds  # caught via the metric's own headline value
    assert "sub_number" in kinds    # AND via its sub — both surfaces fire


def test_orchestrator_strict_mode_escalates_any_warning_to_a_raise():
    raw = [_raw_section("bb", [{"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"}])]
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 2,
        "analysis": "The corridor now sits 200bp above the regional median.",
    }])
    with pytest.raises(ProseNumberViolationError, match=r"STRICT"):
        run_prose_number_gate(brief, raw, strict=True)


def test_orchestrator_clean_brief_returns_empty_warnings():
    raw = [_raw_section("bb", [
        {"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22", "cadence": "event"},
    ])]
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 2,
        "metrics": [{"label": "Policy Rate", "value": "9.50%", "sub": "held since the 30 Jul cut"}],
        "analysis": "The corridor holds at 9.50%.",
    }])
    assert run_prose_number_gate(brief, raw) == []


# ─── Grounding: chart series + history facts (issue-205 false-positive class) ─
#
# Production issue #205 threw 62 WARNs, 27 of them in `chart_read` blocks. The
# cause was scope, not arithmetic: the editor is handed a per-series digest
# (`series_summary`) and a list of `history_facts` alongside the metric table,
# is INSTRUCTED to cite both, and the gate only ever looked at the metric
# table. These tests pin the fix and, just as importantly, pin its LIMITS —
# an over-wide allowed set is a silently broken gate, which is worse than a
# noisy one.


def _digest(first_ts, first_value, last_ts, last_value, lo, hi, n=12):
    return {
        "n": n,
        "first_ts": first_ts, "first_value": first_value,
        "last_ts": last_ts, "last_value": last_value,
        "min": lo, "max": hi,
    }


def test_series_key_unit_maps_the_real_key_shapes():
    from brief.validators.prose_numbers import _series_key_unit

    assert _series_key_unit("gross_reserves_usd_bn_monthly") == "USD bn"
    assert _series_key_unit("remittance_usd_mn_monthly") == "USD mn"
    assert _series_key_unit("nbr_revenue_monthly_cr") == "BDT cr"
    assert _series_key_unit("cpi_12m_avg_monthly") == "%"
    assert _series_key_unit("yield_10y_monthly") == "%"
    assert _series_key_unit("tbill_91d_yield_monthly") == "%"
    assert _series_key_unit("brent") == "USD"
    assert _series_key_unit("dsex") == "index"


def test_series_key_unit_admits_nothing_for_an_unknown_key():
    """Fail toward the false positive. A key whose unit we cannot infer must
    contribute NO allowed values — guessing scale 1.0 would, for a key that
    is really billions, widen the allowed set a thousandfold and let an
    invented figure sail through. A missed clearance is noise; a wrong
    clearance is a broken gate."""
    from brief.validators.prose_numbers import _series_key_unit, _series_summary_entries

    assert _series_key_unit("some_new_series_nobody_mapped") is None
    entries = _series_summary_entries(
        {"some_new_series_nobody_mapped": _digest("2025-11-01", 31.09, "2026-08-01", 26.5, 26.5, 31.09)}
    )
    assert entries == []


def test_series_summary_entries_admit_the_four_digest_values_only():
    """first/last/min/max are the ONLY values the editor is shown. A
    mid-series point it never saw must stay unmatched — if prose cites one,
    that is a number the editor could not have read, and the WARN is right."""
    from brief.validators.prose_numbers import _series_summary_entries

    entries = _series_summary_entries(
        {"gross_reserves_usd_bn_monthly": _digest("2025-11-01", 31.09, "2026-08-01", 26.5, 25.9, 31.09)}
    )
    # bn USD normalizes into the millions base the metric side uses.
    values = sorted(e["normalized_value"] for e in entries)
    # Four fields in, four entries out: 31.09 is BOTH first_value and max.
    assert values == [25900.0, 26500.0, 31090.0, 31090.0]
    assert all(e["category"] == "currency" and e["currency"] == "USD" for e in entries)


def test_series_summary_entries_tolerate_junk():
    from brief.validators.prose_numbers import _series_summary_entries, _series_summary_periods

    assert _series_summary_entries(None) == []
    assert _series_summary_entries({"k": "not-a-dict"}) == []
    assert _series_summary_periods(None) == set()
    assert _series_summary_periods({"k": {"first_ts": "garbage"}}) == set()


def test_series_summary_periods_are_the_two_endpoints():
    from brief.validators.prose_numbers import _series_summary_periods

    assert _series_summary_periods(
        {"dsex": _digest("2025-11-03", 4900.0, "2026-08-21", 5400.0, 4700.0, 5500.0)}
    ) == {(11, 2025), (8, 2026)}


def test_history_fact_entries_parse_the_display_string():
    """`reference_value_formatted` is what the prompt tells the editor to
    quote verbatim, so it is parsed with the SAME token extractor used on the
    prose — round-tripping a phrase through both sides must normalize to the
    same number or the clearance would not fire."""
    from brief.validators.prose_numbers import _history_fact_entries

    entries = _history_fact_entries([
        {"metric_id": "cpi", "kind": "highest_since", "phrase": "highest since Apr 2022 (10.9% then)",
         "reference_value_formatted": "10.9%", "reference_as_of": "2022-04-01"},
        {"metric_id": "res", "kind": "highest_since", "phrase": "highest since Nov 2025 ($31.09bn then)",
         "reference_value_formatted": "$31.09bn", "reference_as_of": "2025-11-01"},
    ])
    percent = [e for e in entries if e["category"] == "percent"]
    money = [e for e in entries if e["category"] == "currency"]
    assert [e["normalized_value"] for e in percent] == [10.9]
    assert [e["normalized_value"] for e in money] == [31090.0]


def test_history_fact_entries_skip_bare_numbers():
    """A bare "103.55" yields no money/percent token — matching the prose
    side, which does not police bare numbers either. Admitting it would mean
    admitting a scale-free number into every category at once."""
    from brief.validators.prose_numbers import _history_fact_entries

    assert _history_fact_entries([{"reference_value_formatted": "103.55"}]) == []
    assert _history_fact_entries(None) == []
    assert _history_fact_entries(["not-a-dict"]) == []


def test_history_fact_periods():
    from brief.validators.prose_numbers import _history_fact_periods

    assert _history_fact_periods([
        {"reference_as_of": "2022-04-01"}, {"reference_as_of": "2025-11-30"},
        {"reference_as_of": None}, {"no_key": 1},
    ]) == {(4, 2022), (11, 2025)}


def test_chart_window_low_in_a_metric_sub_is_cleared_by_the_digest():
    """Issue #205, iran section, verbatim shape: "up from a $71.18 window
    low" in a METRIC SUB — the sub checker needed the grounding too, not just
    the lede checker."""
    brief = _brief([{
        "slug": "iran", "ord": 9, "title": "Oil", "group_key": "markets", "weight": 1,
        "metrics": [{"label": "Brent spot", "value": "$76.40",
                     "sub": "Up from a $71.18 window low."}],
    }])
    raw = _raw_section("iran", [
        {"label": "Brent spot", "value": 76.40, "unit": "USD", "cadence": "daily", "as_of": "2026-08-22"},
    ])
    assert len(check_metric_sub_numbers(brief, {"iran": raw})) == 1

    raw["series_summary"] = {"brent": _digest("2025-11-01", 63.2, "2026-08-22", 76.40, 71.18, 82.0)}
    assert check_metric_sub_numbers(brief, {"iran": raw}) == []


def test_history_fact_phrase_clears_both_its_value_and_its_month():
    """Issue #205, macro section: "highest since Apr 2022 (10.9% then)" threw
    TWO warnings — a sub_number for 10.9% and a sub_period for Apr 2022 — for
    a phrase the prompt required be quoted verbatim."""
    brief = _brief([{
        "slug": "macro", "ord": 7, "title": "Macro", "group_key": "policy", "weight": 1,
        "metrics": [{"label": "CPI Food (P-to-P)", "value": "11.00%",
                     "sub": "Highest since Apr 2022 (10.9% then)."}],
    }])
    raw = _raw_section("macro", [
        {"label": "CPI Food (P-to-P)", "value": 11.00, "unit": "%", "cadence": "monthly",
         "as_of": "2026-07-01"},
    ])
    assert len(check_metric_sub_numbers(brief, {"macro": raw})) == 1
    assert len(check_metric_sub_periods(brief, {"macro": raw})) == 1

    raw["history_facts"] = [{
        "metric_id": "cpi_p2p_food", "kind": "highest_since",
        "phrase": "highest since Apr 2022 (10.9% then)",
        "reference_value_formatted": "10.9%", "reference_as_of": "2022-04-01",
    }]
    assert check_metric_sub_numbers(brief, {"macro": raw}) == []
    assert check_metric_sub_periods(brief, {"macro": raw}) == []


def test_lede_prose_can_cite_the_chart_window_start():
    """Issue #205, banking/reserves: "$31.09bn in Nov 2025" is the reserves
    chart's `first_value` — real, editor-visible, and previously flagged."""
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking", "weight": 1,
        "analysis": "Reserves have bled from $31.09bn in Nov 2025 to today's print.",
    }])
    raw = _raw_section("bb", [
        {"label": "Gross Reserves", "value": 26.5, "unit": "bn USD", "cadence": "weekly",
         "as_of": "2026-08-21"},
    ])
    assert len(check_lede_numbers_against_builder_values(brief, [raw])) == 1

    raw["series_summary"] = {
        "gross_reserves_usd_bn_monthly": _digest("2025-11-01", 31.09, "2026-08-01", 26.5, 25.9, 31.09)
    }
    assert check_lede_numbers_against_builder_values(brief, [raw]) == []


def test_grounding_never_feeds_the_pairwise_diff_derivation():
    """Deliberate scope boundary. `_build_allowed_values` derives every
    pairwise difference between builder values so prose can say "up 12bp".
    Chart digests carry hundreds of values; letting them into that derivation
    would admit a combinatorial soup of differences and effectively disable
    the gate. A chart-derived DELTA therefore still warns — correctly, since
    the editor was never shown it as a number."""
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking", "weight": 1,
        "analysis": "Reserves are down $4.59bn since the window opened.",  # 31.09 - 26.5
    }])
    raw = _raw_section("bb", [
        {"label": "Gross Reserves", "value": 26.5, "unit": "bn USD", "cadence": "weekly",
         "as_of": "2026-08-21"},
    ])
    raw["series_summary"] = {
        "gross_reserves_usd_bn_monthly": _digest("2025-11-01", 31.09, "2026-08-01", 26.5, 25.9, 31.09)
    }
    assert len(check_lede_numbers_against_builder_values(brief, [raw])) == 1


# ─── issue 206: unsuffixed "~" prices + cross-section corridor anchors ──────


def test_approx_marker_now_survives_the_cap_on_an_unsuffixed_price():
    """Issue 206: 'Brent-WTI spread ~$7' against a true 7.24 (Brent 94.09 -
    WTI 86.85) was flagged despite being correct, honestly rounded, and
    explicitly marked as rounded. The 1% cap ($0.07 here) crushed the widened
    ulp, which made the '~' marker inert for every currency token."""
    raw = {"iran": _raw_section("iran", [
        {"label": "Brent spot", "value": 94.09, "unit": "USD", "as_of": "2026-08-22"},
        {"label": "WTI spot", "value": 86.85, "unit": "USD", "as_of": "2026-08-22"},
    ])}
    brief = _brief([{
        "slug": "iran", "ord": 12, "title": "Oil", "group_key": "markets", "weight": 1,
        "metrics": [{"label": "WTI spot", "value": "$86.85", "sub": "Brent-WTI spread ~$7"}],
    }])
    assert check_metric_sub_numbers(brief, raw) == []


def test_the_same_price_without_the_marker_is_still_capped():
    """Either condition alone is unsafe, so both are required. '$7' with no
    '~' reads as an exact figure and keeps its flag."""
    raw = {"iran": _raw_section("iran", [
        {"label": "Brent spot", "value": 94.09, "unit": "USD", "as_of": "2026-08-22"},
        {"label": "WTI spot", "value": 86.85, "unit": "USD", "as_of": "2026-08-22"},
    ])}
    brief = _brief([{
        "slug": "iran", "ord": 12, "title": "Oil", "group_key": "markets", "weight": 1,
        "metrics": [{"label": "WTI spot", "value": "$86.85", "sub": "Brent-WTI spread $7"}],
    }])
    warnings = check_metric_sub_numbers(brief, raw)
    assert len(warnings) == 1
    assert "$7" in warnings[0].matched_text


def test_the_approx_exemption_does_not_reach_suffixed_figures():
    """The dangerous half: '~Tk3.5tn' against a true 3.61tn is a 110bn gap.
    Exempting it would buy a +/-Tk1tn band (a full unit at 1e6 scale), so the
    exemption is scoped to scale 1.0 and this still warns."""
    raw = {"fiscal": _raw_section("fiscal", [
        {"label": "NBR collected YTD", "value": 3_610_000.0, "unit": "mn BDT", "as_of": "2026-06-30"},
    ])}
    brief = _brief([{
        "slug": "fiscal", "ord": 9, "title": "Fiscal", "group_key": "realeco", "weight": 1,
        "metrics": [{"label": "NBR collected YTD", "value": "Tk3.61tn", "sub": "~Tk3.5tn on the year"}],
    }])
    warnings = check_metric_sub_numbers(brief, raw)
    assert len(warnings) == 1
    assert "Tk3.5tn" in warnings[0].matched_text


def test_a_section_may_measure_against_the_policy_corridor():
    """Issue 206: tbond's 'the front stays below the 9.5% policy' is correct -
    9.5% is published in the SAME brief's bb section - but the per-section
    checker had nothing to match it against."""
    raw = {
        "tbond": _raw_section("tbond", [
            {"label": "364d T-Bill cut-off", "value": 9.17, "unit": "%", "as_of": "2026-08-21"},
        ]),
        "bb": _raw_section("bb", [
            {"id": "bb_policy_rate", "label": "Policy Rate", "value": 9.5, "unit": "%",
             "as_of": "2026-08-21"},
        ]),
    }
    brief = _brief([{
        "slug": "tbond", "ord": 8, "title": "Govt Bonds", "group_key": "markets", "weight": 1,
        "metrics": [{"label": "364d T-Bill cut-off", "value": "9.17%",
                     "sub": "the front stays below the 9.5% policy"}],
    }])
    assert check_metric_sub_numbers(brief, raw) == []


def test_a_non_anchor_value_from_another_section_is_still_flagged():
    """The allowlist is the whole point: gross reserves live in bb too, but
    they are not a corridor anchor, so tbond may not silently cite them."""
    raw = {
        "tbond": _raw_section("tbond", [
            {"label": "364d T-Bill cut-off", "value": 9.17, "unit": "%", "as_of": "2026-08-21"},
        ]),
        "bb": _raw_section("bb", [
            {"id": "bb_gross_reserves", "label": "Gross Reserves", "value": 36420.0,
             "unit": "mn USD", "as_of": "2026-07-01"},
        ]),
    }
    brief = _brief([{
        "slug": "tbond", "ord": 8, "title": "Govt Bonds", "group_key": "markets", "weight": 1,
        "metrics": [{"label": "364d T-Bill cut-off", "value": "9.17%",
                     "sub": "cover from $36.42bn reserves"}],
    }])
    warnings = check_metric_sub_numbers(brief, raw)
    assert len(warnings) == 1
    assert "$36.42bn" in warnings[0].matched_text


def test_corridor_anchors_do_not_feed_the_pairwise_diff_derivation():
    """Anchors ride alongside the grounding entries, never into
    `_build_allowed_values`. If they fed the diff logic, tbond could derive
    9.5 - 9.17 = 0.33 and '33bp' would pass with nothing behind it."""
    raw = {
        "tbond": _raw_section("tbond", [
            {"label": "364d T-Bill cut-off", "value": 9.17, "unit": "%", "as_of": "2026-08-21"},
        ]),
        "bb": _raw_section("bb", [
            {"id": "bb_policy_rate", "label": "Policy Rate", "value": 9.5, "unit": "%",
             "as_of": "2026-08-21"},
        ]),
    }
    brief = _brief([{
        "slug": "tbond", "ord": 8, "title": "Govt Bonds", "group_key": "markets", "weight": 1,
        "metrics": [{"label": "364d T-Bill cut-off", "value": "9.17%", "sub": "33bp under policy"}],
    }])
    warnings = check_metric_sub_numbers(brief, raw)
    assert len(warnings) == 1
    assert "33bp" in warnings[0].matched_text


def test_bb_does_not_double_count_its_own_anchors():
    """`exclude_slug` keeps bb's own corridor metrics from being appended
    twice; the section still validates normally against them."""
    raw = {"bb": _raw_section("bb", [
        {"id": "bb_policy_rate", "label": "Policy Rate", "value": 9.5, "unit": "%",
         "as_of": "2026-08-21"},
        {"id": "bb_call_money", "label": "Overnight Call Money", "value": 9.26, "unit": "%",
         "as_of": "2026-08-21"},
    ])}
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking", "weight": 1,
        "metrics": [{"label": "Overnight Call Money", "value": "9.26%",
                     "sub": "24bp under the 9.5% policy"}],
    }])
    assert check_metric_sub_numbers(brief, raw) == []


def test_round_rhetorical_threshold_still_warns_after_the_206_widenings():
    """The three '$90' hits in issue 206 ('watch whether $94 holds above $90')
    are a level to watch, not a reading. Neither issue-206 change touches
    them - '$90' carries no '~' - and that is deliberate: a checker that
    accepts round levels would also accept an invented figure."""
    raw = [_raw_section("iran", [
        {"label": "Brent spot", "value": 94.09, "unit": "USD", "as_of": "2026-08-22"},
        {"label": "WTI spot", "value": 86.85, "unit": "USD", "as_of": "2026-08-22"},
    ])]
    brief = _brief([{
        "slug": "iran", "ord": 12, "title": "Oil", "group_key": "markets", "weight": 1,
        "metrics": [{"label": "Brent spot", "value": "$94.09", "sub": "near range top"}],
        "analysis": "Position for a wider import bill if Brent holds above $90 into the next prints.",
    }])
    warnings = check_lede_numbers_against_builder_values(brief, raw)
    assert [w.matched_text.strip() for w in warnings] == ["$90"]
