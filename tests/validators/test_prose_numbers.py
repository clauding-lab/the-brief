"""Unit tests for brief/validators/prose_numbers.py — the P2 fact-checker.

Fixtures below are the audit #204 findings + the round-2 review's own PASS
cases, reproduced verbatim from the task spec so a regression against the
real shape of the failure is caught, not an idealized one.
"""
from __future__ import annotations

import pytest

from brief.v6_schema import BriefPayloadV6
from brief.validators.prose_numbers import (
    ProseNumberViolationError,
    check_count_claims,
    check_lede_numbers_against_builder_values,
    check_metric_sub_numbers,
    check_metric_sub_periods,
    run_prose_number_gate,
)


def _brief(sections: list[dict]) -> BriefPayloadV6:
    return BriefPayloadV6.model_validate({
        "brief": {"issue_no": 204, "volume": 1, "brief_date": "2026-08-22"},
        "sections": sections,
    })


def _raw_section(slug: str, metrics: list[dict]) -> dict:
    return {"slug": slug, "metrics": metrics}


# ─── BLOCK: number-vs-builder-value ────────────────────────────────────────


def test_block_stale_flash_figure_presented_as_current():
    """The audit's headline finding: '$2.82bn' sub on a metric whose real
    builder value is 2858.68 (mn USD) — the stale mid-month flash quoted as
    though it were the official final."""
    raw = {"remit": _raw_section("remit", [
        {"label": "Monthly Remittance", "value": 2858.68, "unit": "mn USD", "as_of": "2026-07-31"},
    ])}
    brief = _brief([{
        "slug": "remit", "ord": 11, "title": "Remittance", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Monthly Remittance", "value": "$2.86bn", "sub": "$2.82bn — July final"}],
    }])
    with pytest.raises(ProseNumberViolationError, match=r"\$2\.82bn"):
        check_metric_sub_numbers(brief, raw)


def test_block_month_mismatch_july_print_on_june_period_metric():
    raw = {"fx": _raw_section("fx", [
        {"label": "Monthly Exports", "value": 4.20269, "unit": "bn USD", "as_of": "2026-06-30"},
    ])}
    brief = _brief([{
        "slug": "fx", "ord": 5, "title": "FX & External", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Monthly Exports", "value": "$4.20bn", "sub": "July print"}],
    }])
    with pytest.raises(ProseNumberViolationError, match=r"July"):
        check_metric_sub_periods(brief, raw)


def test_block_count_claim_fourteen_reads():
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "verdict": "Flat across fourteen reads — corridor unchanged.",
    }])
    with pytest.raises(ProseNumberViolationError, match=r"fourteen reads"):
        check_count_claims(brief)


def test_count_claim_passes_when_no_such_phrase_present():
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "verdict": "Corridor holds at 9.50%, unchanged since the 30 Jul cut.",
    }])
    check_count_claims(brief)  # must not raise


# ─── PASS cases from the review's own worked examples ──────────────────────


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
    check_metric_sub_numbers(brief, raw)  # must not raise


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
    check_metric_sub_numbers(brief, raw)  # must not raise


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
    check_metric_sub_numbers(brief, raw)  # must not raise


# ─── period-token nuances ───────────────────────────────────────────────────


def test_month_token_without_year_matches_any_year_with_that_month():
    raw = {"remit": _raw_section("remit", [
        {"label": "Monthly Remittance", "value": 2858.68, "unit": "mn USD", "as_of": "2026-07-31"},
    ])}
    brief = _brief([{
        "slug": "remit", "ord": 11, "title": "Remittance", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Monthly Remittance", "value": "$2.86bn", "sub": "Jul print, official"}],
    }])
    check_metric_sub_periods(brief, raw)  # must not raise


def test_month_token_with_wrong_year_still_blocks():
    raw = {"remit": _raw_section("remit", [
        {"label": "Monthly Remittance", "value": 2858.68, "unit": "mn USD", "as_of": "2026-07-31"},
    ])}
    brief = _brief([{
        "slug": "remit", "ord": 11, "title": "Remittance", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Monthly Remittance", "value": "$2.86bn", "sub": "Jul 2025 print"}],
    }])
    with pytest.raises(ProseNumberViolationError, match=r"Jul 2025"):
        check_metric_sub_periods(brief, raw)


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
    check_metric_sub_periods(brief, raw)  # must not raise — Mar is a sibling's period


def test_no_periods_available_for_section_is_a_noop():
    """A section with no parseable as_of anywhere just skips the check —
    never a false BLOCK from missing data."""
    raw = {"bb": _raw_section("bb", [{"label": "Policy Rate", "value": 9.5, "unit": "%"}])}
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 1,
        "metrics": [{"label": "Policy Rate", "value": "9.50%", "sub": "held since the Jul cut"}],
    }])
    check_metric_sub_periods(brief, raw)  # must not raise


# ─── numbers with no unit/currency marker are out of scope for BLOCK ───────


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
    check_metric_sub_numbers(brief, raw)  # must not raise


def test_bare_numbers_are_never_flagged_as_value_mismatches():
    raw = {"dse": _raw_section("dse", [{"label": "DSEX", "value": 5257.0, "unit": "index"}])}
    brief = _brief([{
        "slug": "dse", "ord": 6, "title": "DSE Markets", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "DSEX", "value": "5,257.00", "sub": "third straight session of gains"}],
    }])
    check_metric_sub_numbers(brief, raw)  # "third" has no digit token; must not raise


# ─── WARN mode ──────────────────────────────────────────────────────────────


def test_warn_flags_a_lede_figure_with_no_builder_match():
    raw = [_raw_section("bb", [{"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"}])]
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 2,
        "analysis": "The corridor now sits 200bp above the regional median.",
    }])
    warnings = check_lede_numbers_against_builder_values(brief, raw, strict=False)
    assert len(warnings) == 1
    assert "200bp" in warnings[0].matched_text
    assert "no builder value" in warnings[0].describe() or warnings[0].nearest_value is not None


def test_warn_does_not_flag_a_figure_that_matches_a_builder_value():
    raw = [_raw_section("bb", [{"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"}])]
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 2,
        "analysis": "The corridor holds at 9.50% this morning.",
    }])
    warnings = check_lede_numbers_against_builder_values(brief, raw, strict=False)
    assert warnings == []


def test_strict_mode_upgrades_warn_to_raise():
    raw = [_raw_section("bb", [{"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"}])]
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 2,
        "analysis": "The corridor now sits 200bp above the regional median.",
    }])
    with pytest.raises(ProseNumberViolationError):
        check_lede_numbers_against_builder_values(brief, raw, strict=True)


def test_todays_call_and_tldr_and_verdict_all_scanned_by_warn_mode():
    raw = [_raw_section("bb", [{"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22"}])]
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 2,
        "tldr": "Holding at 9.50% — data-dependent.",
        "verdict": "Holding at 9.50%, tightening bias intact.",
    }])
    brief.brief.todays_call = "The book stays defensive at 9.50% overnight cost of funds."
    warnings = check_lede_numbers_against_builder_values(brief, raw, strict=False)
    assert warnings == []  # every occurrence matches the same real 9.50 builder value


# ─── orchestrator ordering ──────────────────────────────────────────────────


def test_run_prose_number_gate_raises_on_first_block_violation_before_warn_scan():
    raw = [_raw_section("remit", [
        {"label": "Monthly Remittance", "value": 2858.68, "unit": "mn USD", "as_of": "2026-07-31"},
    ])]
    brief = _brief([{
        "slug": "remit", "ord": 11, "title": "Remittance", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Monthly Remittance", "value": "$2.86bn", "sub": "$2.82bn — July final"}],
    }])
    with pytest.raises(ProseNumberViolationError):
        run_prose_number_gate(brief, raw)


def test_run_prose_number_gate_clean_brief_returns_empty_warnings():
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


def test_event_cadence_metric_sub_may_name_a_decision_date_unrelated_to_its_restamp():
    """AGENTS.md landmine 24: `bb_policy_rate` is daily-restamped, so its
    `as_of` is always "today" — the corridor's actual decision date (the 30
    Jul MPC cut) has nothing to do with that restamp. A sub naming the real
    decision month must NOT be blocked as a period mismatch."""
    raw = {"bb": _raw_section("bb", [
        {"label": "Policy Rate", "value": 9.50, "unit": "%", "as_of": "2026-08-22", "cadence": "event"},
    ])}
    brief = _brief([{
        "slug": "bb", "ord": 3, "title": "Bangladesh Bank", "group_key": "banking",
        "weight": 2,
        "metrics": [{"label": "Policy Rate", "value": "9.50%", "sub": "held since the 30 Jul cut"}],
    }])
    check_metric_sub_periods(brief, raw)  # must not raise
