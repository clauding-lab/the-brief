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


# ─── check_hyphenated_count_claims — issue 206's "ten-session low" ─────────
# WARN everywhere, BLOCK inside `_HYPHENATED_COUNT_BLOCK_SLUGS` (dse) since
# the 2026-08-28 owner-approved promotion. A claim whose COUNT matches a
# machine-fed history fact for the same section is legitimate and never fires.


def _dse_section(**fields) -> dict:
    return {
        "slug": "dse", "ord": 6, "title": "DSE Markets", "group_key": "markets",
        "weight": 1, **fields,
    }


def _history_fact(phrase: str, *, metric_id: str = "dsex") -> dict:
    """The serialized shape `pipeline_v6._to_v6_raw` writes into
    `sections_raw[].history_facts` — five keys, `phrase` carrying the rank."""
    return {
        "metric_id": metric_id,
        "kind": "since_lower",
        "phrase": phrase,
        "reference_value_formatted": "5,722.21",
        "reference_as_of": "2026-08-23",
    }


_REAL_SESSION_LOW_FACT = _history_fact(
    "a 42-session low (5,722.21 on 23 Aug the last lower close)"
)


def test_hyphenated_count_claim_sourced_by_a_history_fact_is_legitimate():
    """PR #185 feeds `dse` a REAL machine-computed session rank through the
    history-facts-verbatim contract. Prose that inlines that rank is the
    honest output the whole fix exists to produce — it must neither warn nor
    block, or the fix would be unshippable alongside its own catcher."""
    raw = {"dse": {"slug": "dse", "metrics": [],
                   "history_facts": [_REAL_SESSION_LOW_FACT]}}
    brief = _brief([_dse_section(
        verdict="DSEX grinds to a 42-session low on drained turnover.",
    )])
    assert check_hyphenated_count_claims(brief, raw) == []


def test_the_block_scope_is_exactly_dse():
    """Pin the scope itself, not just its behaviour. Shrinking it is pinned by
    every WARN test below and growing it toward `fiscal` by
    `test_hyphenated_count_claim_outside_the_block_scope_stays_warn`, but
    ARBITRARY growth was not — and the sections most likely to be added next
    are the ones that would false-block immediately.

    PRECONDITION for adding a slug: that section must have its OWN machine-fed
    count, the way `dse` has `_dsex_session_low_fact`. `bb` and `tbond` do not,
    and their prose is dense with instrument names that wear the same shape
    ("the 14-day call money rate", "the 91-day T-Bill") — a reviewer counted 25
    such phrases across 15 real issues. Adding either slug on the strength of
    "it looks similar" holds a publish on the first honest morning."""
    from brief.validators.prose_numbers import _HYPHENATED_COUNT_BLOCK_SLUGS

    assert _HYPHENATED_COUNT_BLOCK_SLUGS == frozenset({"dse"})


# ─── FIX 1: compound word-forms ("forty-two-session") ──────────────────────


def test_compound_word_form_claim_clears_a_digit_fact():
    """The live rank is 42 and the editor's register prefers word forms, so
    the compound band is where an honest claim actually lands. Capturing only
    the tail token ("two") turned every "forty-two-session low" into a
    fabrication and would have held an honest morning."""
    raw = {"dse": {"slug": "dse", "metrics": [],
                   "history_facts": [_REAL_SESSION_LOW_FACT]}}
    brief = _brief([_dse_section(
        verdict="DSEX grinds to a forty-two-session low on drained turnover.",
    )])
    assert check_hyphenated_count_claims(brief, raw) == []


def test_compound_word_form_fabrication_still_blocks():
    """Widening the capture must not blunt the catch: a compound that names
    the WRONG rank is still an invented figure."""
    raw = {"dse": {"slug": "dse", "metrics": [],
                   "history_facts": [_REAL_SESSION_LOW_FACT]}}
    brief = _brief([_dse_section(
        verdict="DSEX grinds to a thirty-seven-session low on drained turnover.",
    )])
    with pytest.raises(ProseNumberViolationError, match=r"thirty-seven-session low"):
        check_hyphenated_count_claims(brief, raw)


def test_compound_word_form_matched_text_names_the_whole_count():
    """The reported phrase must be the one a human would go looking for."""
    brief = _brief([{
        "slug": "fiscal", "ord": 8, "title": "Fiscal", "group_key": "policy",
        "weight": 1,
        "tldr": "NBR collections have held flat on a twenty-one-day streak.",
    }])
    warnings = check_hyphenated_count_claims(brief, {})
    assert warnings[0].matched_text.startswith("twenty-one-day")
    assert warnings[0].normalized_value == 21.0


# ─── FIX 2: only session/print/read + "low" can ever hard-block ────────────


def test_a_52_week_low_only_warns_in_dse():
    """Standard derivable market prose. No fact of that shape is ever fed, so
    a BLOCK on it could never be cleared by an honest editor — it would just
    hold the publish on a correct sentence."""
    raw = {"dse": {"slug": "dse", "metrics": [],
                   "history_facts": [_REAL_SESSION_LOW_FACT]}}
    brief = _brief([_dse_section(
        verdict="DSEX closed at a 52-week low on drained turnover.",
    )])
    warnings = check_hyphenated_count_claims(brief, raw)
    assert len(warnings) == 1
    assert warnings[0].section == "dse"


def test_a_session_high_only_warns_in_dse():
    """`_dsex_session_low_fact` emits a `since_lower` rank and nothing else,
    so a HIGH claim has no possible sourced counterpart — unblockable by
    construction, therefore never blocked."""
    raw = {"dse": {"slug": "dse", "metrics": [],
                   "history_facts": [_REAL_SESSION_LOW_FACT]}}
    brief = _brief([_dse_section(
        verdict="DSEX printed a five-session high on thin turnover.",
    )])
    warnings = check_hyphenated_count_claims(brief, raw)
    assert len(warnings) == 1
    assert warnings[0].section == "dse"


def test_a_day_run_only_warns_in_dse():
    raw = {"dse": {"slug": "dse", "metrics": [],
                   "history_facts": [_REAL_SESSION_LOW_FACT]}}
    brief = _brief([_dse_section(
        verdict="DSEX extended a three-day run of declines.",
    )])
    warnings = check_hyphenated_count_claims(brief, raw)
    assert len(warnings) == 1
    assert warnings[0].section == "dse"


def test_a_print_low_still_blocks_in_dse():
    """The blockable noun set is (session|print|read), not `session` alone —
    the same three the count-claim family has always treated as
    observation counts."""
    raw = {"dse": {"slug": "dse", "metrics": [],
                   "history_facts": [_REAL_SESSION_LOW_FACT]}}
    brief = _brief([_dse_section(
        verdict="DSEX ground out a ten-print low on drained turnover.",
    )])
    with pytest.raises(ProseNumberViolationError, match=r"ten-print low"):
        check_hyphenated_count_claims(brief, raw)


# ─── FIX 3: the producer's phrase must round-trip into the extractor ───────


def test_the_real_producers_phrase_round_trips_into_the_extractor():
    """Chains the REAL producer to the REAL extractor so they can only change
    together. Every other test here hands the check a hand-written phrase, so
    a future rewording of `_dsex_session_low_fact` ("a 42-session closing
    low", "lowest close in 42 sessions" — both extract NOTHING) would leave
    those green while every honest morning silently became a hold. This test
    goes points -> production fact -> production `_to_v6_raw` serialization ->
    `_sourced_counts`, asserting the rank survives the whole chain."""
    from datetime import date as _date, timedelta as _timedelta

    from brief.pipeline_v6 import _dsex_session_low_fact, _to_v6_raw
    from brief.schema import SectionData
    from brief.validators.prose_numbers import _sourced_counts

    start = _date(2026, 6, 1)
    values = [5900.0] * 30 + [5601.44] + [5800.0 + i for i in range(5)] + [5640.09]
    points = [
        {"key": "dsex", "ts": (start + _timedelta(days=i)).isoformat(), "value": v}
        for i, v in enumerate(values)
    ]

    fact = _dsex_session_low_fact(points)
    assert fact is not None, "fixture drifted — the producer emitted no fact"

    raw = _to_v6_raw(
        [SectionData(id="dse", title="DSE Markets", freshness="fresh", metrics=[])],
        today=_date(2026, 7, 15),
        extra_history_facts={"dse": [fact]},
    )
    assert _sourced_counts(raw[0]) == {6}, (
        f"the producer's phrase {fact.phrase!r} no longer yields its own rank "
        "to the extractor — an honest claim would now BLOCK"
    )


def test_hyphenated_count_claim_word_form_matches_a_digit_fact():
    """The editor writes count words, the fact carries digits — matching is
    NUMERIC, not textual, or every word-form restatement of an honest rank
    would block."""
    raw = {"dse": {"slug": "dse", "metrics": [],
                   "history_facts": [_history_fact("a 12-session low (5,601.44 on 22 Jun the last lower close)")]}}
    brief = _brief([_dse_section(
        verdict="DSEX grinds to a twelve-session low on drained turnover.",
    )])
    assert check_hyphenated_count_claims(brief, raw) == []


def test_hyphenated_count_claim_blocks_in_dse_when_the_fact_says_otherwise():
    """Issue 205's REAL defect: 'a ten-session low' shipped byte-identical
    across four editions while the true rank ran 38 -> 42. With a real rank
    now supplied, an unmatched claim in `dse` is a fabrication by
    construction — BLOCK, not WARN (owner-approved, 2026-08-28)."""
    raw = {"dse": {"slug": "dse", "metrics": [],
                   "history_facts": [_REAL_SESSION_LOW_FACT]}}
    brief = _brief([_dse_section(
        verdict="DSEX grinds to a ten-session low on drained turnover.",
    )])
    with pytest.raises(ProseNumberViolationError, match=r"ten-session low"):
        check_hyphenated_count_claims(brief, raw)


def test_hyphenated_count_claim_off_by_two_still_blocks_in_dse():
    """No tolerance on an integer session rank: 40 is not 42. A rank is a
    COUNT of observations, not a measurement — there is no last-printed-digit
    half-ulp to widen (the module's currency/percent tolerance ladder does not
    apply here), so close-but-wrong is simply wrong."""
    raw = {"dse": {"slug": "dse", "metrics": [],
                   "history_facts": [_REAL_SESSION_LOW_FACT]}}
    brief = _brief([_dse_section(
        verdict="DSEX grinds to a 40-session low on drained turnover.",
    )])
    with pytest.raises(ProseNumberViolationError, match=r"40-session low"):
        check_hyphenated_count_claims(brief, raw)


def test_hyphenated_count_claim_blocks_in_dse_with_no_history_facts_at_all():
    """The rank guards (`LOOKBACK_MIN`, `MIN_DATA_POINTS['daily']`, window
    low) make `_dsex_session_low_fact` return None rather than a fabricated
    rank — so 'no fact' is a legitimate pipeline state. An editor that writes
    a session-low claim ANYWAY, with nothing to source it from, is the exact
    fabrication case: BLOCK."""
    raw = {"dse": {"slug": "dse", "metrics": [], "history_facts": []}}
    brief = _brief([_dse_section(
        verdict="DSEX grinds to a ten-session low on drained turnover.",
    )])
    with pytest.raises(ProseNumberViolationError, match=r"no sourced count"):
        check_hyphenated_count_claims(brief, raw)


def test_dse_with_no_fact_and_no_claim_is_clean():
    """The other half of the rank-guard interplay: fact suppressed, editor
    writes no count claim — nothing to catch, nothing to hold."""
    raw = {"dse": {"slug": "dse", "metrics": [], "history_facts": []}}
    brief = _brief([_dse_section(
        verdict="DSEX slips 1.10% on drained turnover; no fresh low.",
    )])
    assert check_hyphenated_count_claims(brief, raw) == []


def test_hyphenated_count_claim_outside_the_block_scope_stays_warn():
    """Scoped promotion: `fiscal` has no machine-supplied count of any kind,
    so there is no honest alternative for the editor to have used — it warns,
    exactly as it has since PR #175, and the publish proceeds."""
    brief = _brief([{
        "slug": "fiscal", "ord": 8, "title": "Fiscal", "group_key": "policy",
        "weight": 1,
        "tldr": "NBR collections have held flat on a 12-day streak.",
    }])
    warnings = check_hyphenated_count_claims(brief, {})
    assert len(warnings) == 1
    assert warnings[0].kind == "hyphenated_count_claim"
    assert warnings[0].section == "fiscal"
    assert "12-day streak" in warnings[0].matched_text


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
    brief = _brief([_dse_section(
        verdict="Corridor holds at 9.50%, unchanged since the 30 Jul cut.",
    )])
    assert check_hyphenated_count_claims(brief) == []


def test_hyphenated_count_claim_with_a_non_numeric_count_word_stays_warn_in_dse():
    """Documented scope limit of the BLOCK. The regex's count slot is `\\w+`,
    so it also matches quantifiers that name no number at all ('a
    multi-session low'). Those carry no fabricated figure and nothing to
    compare against a fact, and holding a 08:00 publish over one would be a
    worse trade than logging it — the BLOCK requires a parsed number."""
    raw = {"dse": {"slug": "dse", "metrics": [],
                   "history_facts": [_REAL_SESSION_LOW_FACT]}}
    brief = _brief([_dse_section(
        verdict="DSEX grinds to a multi-session low on drained turnover.",
    )])
    warnings = check_hyphenated_count_claims(brief, raw)
    assert len(warnings) == 1
    assert warnings[0].section == "dse"


def test_hyphenated_count_claim_checks_every_claim_in_a_field_not_just_the_first():
    """A field whose FIRST claim is sourced must not shield a second,
    fabricated one behind it — the legitimacy test is per claim.

    Both claims wear the blockable session-low shape here: after the FIX-2
    narrowing, a second claim in a WARN-class shape (day/week, high/streak/
    run) would only warn, which would make this test pass for the wrong
    reason."""
    raw = {"dse": {"slug": "dse", "metrics": [],
                   "history_facts": [_REAL_SESSION_LOW_FACT]}}
    brief = _brief([_dse_section(
        verdict=(
            "DSEX grinds to a 42-session low on drained turnover; "
            "DS30 sits at a nine-session low of its own."
        ),
    )])
    with pytest.raises(ProseNumberViolationError, match=r"nine-session low"):
        check_hyphenated_count_claims(brief, raw)


def test_a_dse_fact_does_not_legitimize_another_sections_claim():
    """Facts are section-scoped: `dse`'s rank says nothing about `fiscal`."""
    raw = {"dse": {"slug": "dse", "metrics": [],
                   "history_facts": [_REAL_SESSION_LOW_FACT]}}
    brief = _brief([{
        "slug": "fiscal", "ord": 8, "title": "Fiscal", "group_key": "policy",
        "weight": 1,
        "tldr": "NBR collections have held flat on a 42-day streak.",
    }])
    warnings = check_hyphenated_count_claims(brief, raw)
    assert len(warnings) == 1
    assert warnings[0].section == "fiscal"


def test_orchestrator_blocks_a_fabricated_dse_hyphenated_count_claim():
    raw = [{
        "slug": "dse",
        "metrics": [{"label": "DSEX close", "value": 5722.21, "unit": "index",
                     "as_of": "2026-08-23"}],
        "history_facts": [_REAL_SESSION_LOW_FACT],
    }]
    brief = _brief([_dse_section(
        verdict="DSEX grinds to a ten-session low on drained turnover.",
    )])
    with pytest.raises(ProseNumberViolationError, match=r"ten-session low"):
        run_prose_number_gate(brief, raw, strict=False)


def test_orchestrator_lets_a_sourced_dse_claim_through():
    raw = [{
        "slug": "dse",
        "metrics": [{"label": "DSEX close", "value": 5722.21, "unit": "index",
                     "as_of": "2026-08-23"}],
        "history_facts": [_REAL_SESSION_LOW_FACT],
    }]
    brief = _brief([_dse_section(
        verdict="DSEX grinds to a 42-session low on drained turnover.",
    )])
    warnings = run_prose_number_gate(brief, raw, strict=False)
    assert "hyphenated_count_claim" not in {w.kind for w in warnings}


def test_orchestrator_includes_hyphenated_count_claims_in_warn_findings():
    """Outside the block scope the orchestrator still only collects."""
    raw = [_raw_section("fiscal", [{"label": "NBR collected YTD", "value": 3.61,
                                    "unit": "BDT trn", "as_of": "2026-06-30"}])]
    brief = _brief([{
        "slug": "fiscal", "ord": 8, "title": "Fiscal", "group_key": "policy",
        "weight": 1,
        "tldr": "NBR collections have held flat on a 12-day streak.",
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


# ─── the Real Policy Rate machine stamp (2026-08-26) ───────────────────────
# `pipeline_v6._stamp_real_policy_rate_sub` writes the metric's own
# arithmetic into `sub` ("9.50% repo − 8.32% Jul p2p CPI"). Neither leg is a
# macro raw value — the repo rate lives in the BB section and the p2p CPI
# print is an INPUT to the derivation, never published as its own macro
# metric — and the month it names is the inflation reading's, not necessarily
# the metric's own period. Deterministic pipeline output must never WARN, so
# the exemption keys on the same raw `source` marker the stamper itself uses.

_RPR_RAW_SOURCE = "BB+BBS (9.50% repo (30 Jul cut) − 8.32% Jul p2p CPI)"
_RPR_STAMPED_SUB = "9.50% repo (30 Jul cut) − 8.32% Jul p2p CPI"


def _real_policy_rate_raw_and_brief(
    source: str, *, as_of: str = "2026-07-31", sub: str = _RPR_STAMPED_SUB,
):
    raw = {"macro": _raw_section("macro", [
        {"label": "Real Policy Rate", "value": 1.18, "unit": "%", "as_of": as_of,
         "cadence": "monthly", "source": source},
        {"label": "CPI 12m Avg", "value": 5.2, "unit": "%", "as_of": as_of,
         "cadence": "monthly"},
    ])}
    brief = _brief([{
        "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Real Policy Rate", "value": "1.2%", "sub": sub}],
    }])
    return raw, brief


def test_machine_stamped_real_policy_rate_segment_is_exempt_from_the_number_check():
    raw, brief = _real_policy_rate_raw_and_brief(_RPR_RAW_SOURCE)
    assert check_metric_sub_numbers(brief, raw) == []


def test_machine_stamped_real_policy_rate_segment_is_exempt_from_the_period_check():
    """The stamped segment names the CPI month and the MPC decision month by
    construction. Fixture forces a divergence from the metric's own period so
    the assertion is not vacuous."""
    raw, brief = _real_policy_rate_raw_and_brief(_RPR_RAW_SOURCE, as_of="2026-08-31")
    assert check_metric_sub_periods(brief, raw) == []


def test_real_policy_rate_period_exemption_needs_the_marker_not_the_label():
    raw, brief = _real_policy_rate_raw_and_brief("BB+BBS", as_of="2026-08-31")
    assert check_metric_sub_periods(brief, raw) != []


def test_real_policy_rate_exemption_needs_the_marker_not_the_label():
    """Without the stamper's marker on the raw `source`, the same sub is
    editor prose again and warns normally — the exemption tracks the
    MECHANISM that produced the text, not the metric's display name."""
    raw, brief = _real_policy_rate_raw_and_brief("BB+BBS")
    assert check_metric_sub_numbers(brief, raw) != []


# ── REVIEW FIX 1: the exemption is scoped to the MACHINE SEGMENT ────────────
# `_stamp_real_policy_rate_sub` APPENDS its note to whatever the editor
# already wrote (" · " separator). A whole-field exemption therefore stopped
# checking the EDITOR'S OWN prose in the same `sub` — a strictly worse
# outcome than before the stamp existed, since the editor's numbers are
# exactly what the gate is for. Only the deterministic segment is removed;
# the remainder is checked normally.

_EDITOR_PROSE = "Positive but thin, up from 0.34% in June and 99.9% off the 2023 peak."


def test_editor_prose_beside_the_machine_stamp_is_still_checked():
    """The reviewer's probe, as a fixture. `0.34%` and `99.9%` are the
    editor's own inventions and trace to nothing in the macro section — they
    must warn even though the same `sub` carries a machine segment."""
    raw, brief = _real_policy_rate_raw_and_brief(
        _RPR_RAW_SOURCE, sub=f"{_EDITOR_PROSE} · {_RPR_STAMPED_SUB}",
    )
    matched = {w.matched_text for w in check_metric_sub_numbers(brief, raw)}
    assert "0.34%" in matched
    assert "99.9%" in matched


def test_the_machine_segments_own_legs_never_warn_beside_editor_prose():
    """The other half of the same fixture: the stamp's two legs are removed
    before checking, so neither the repo leg nor the CPI leg contributes a
    warning even when the field also carries editor prose."""
    raw, brief = _real_policy_rate_raw_and_brief(
        _RPR_RAW_SOURCE, sub=f"{_EDITOR_PROSE} · {_RPR_STAMPED_SUB}",
    )
    matched = {w.matched_text for w in check_metric_sub_numbers(brief, raw)}
    assert "8.32%" not in matched
    assert "9.50%" not in matched


def test_editor_month_beside_the_machine_stamp_is_still_checked():
    """Same scoping for the period check: the editor's invented September
    warns; the segment's own Jul tokens do not."""
    raw, brief = _real_policy_rate_raw_and_brief(
        _RPR_RAW_SOURCE, as_of="2026-08-31",
        sub=f"September print eases further. · {_RPR_STAMPED_SUB}",
    )
    warnings = check_metric_sub_periods(brief, raw)
    assert len(warnings) == 1
    assert "September" in warnings[0].matched_text


def test_import_cover_editor_prose_is_checked_on_a_production_shaped_sub():
    """The commit's original "provable no-op for import cover" claim was
    FALSE for production shapes — the golden corpus simply carries no
    `source` key, so the exemption could not fire there at all. Against a
    production-shaped raw metric it did fire, and it silenced the editor's
    own numbers. This pins them back."""
    raw = {"macro": _raw_section("macro", [
        {"label": "Import Cover", "value": 6.25, "unit": "months", "as_of": "2026-03-31",
         "cadence": "monthly", "source": "BB (reserves 31 Jul ÷ Mar import bill)"},
    ])}
    brief = _brief([{
        "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
        "weight": 1,
        "metrics": [{"label": "Import Cover", "value": "6.25",
                     "sub": "Reserves would cover $99.9bn at 12.5% cover. "
                            "· reserves 31 Jul ÷ Mar import bill"}],
    }])
    matched = {w.matched_text for w in check_metric_sub_numbers(brief, raw)}
    assert "$99.9bn" in matched
    assert "12.5%" in matched


def test_import_cover_machine_segment_alone_still_warns_nothing():
    """The scoping must not regress the original exemption: a `sub` that is
    ONLY the machine segment stays clean on both checks."""
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
    assert check_metric_sub_numbers(brief, raw) == []
    assert check_metric_sub_periods(brief, raw) == []


def test_machine_segment_exemption_survives_a_label_the_editor_recased():
    """Review fix 2's other half: the validator already normalizes labels, so
    a recased published label must still find its raw metric — otherwise the
    machine segment is checked as if it were editor prose."""
    raw, brief = _real_policy_rate_raw_and_brief(_RPR_RAW_SOURCE)
    brief.sections[0].metrics[0].label = "Real policy rate"
    assert check_metric_sub_numbers(brief, raw) == []


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


# ─── WARN: "a year earlier" naming the window start (issues 207/208) ────────


def _year_ago_digest(**overrides):
    """A 24-month CPI digest: the window STARTS at 9.95 (Aug 2024) and the
    honest 12-months-back point is 9.77 (Jul 2025) — the exact production
    shape behind the defect."""
    digest = {
        "n": 24,
        "first_ts": "2024-08-01", "first_value": 9.95,
        "last_ts": "2026-07-01", "last_value": 8.88,
        "min": 8.88, "max": 9.95,
        "value_1y_ago": 9.77, "ts_1y_ago": "2025-07-01",
    }
    digest.update(overrides)
    return digest


def _year_ago_brief(context: str):
    return _brief([{
        "slug": "macro", "ord": 9, "title": "Macro & Inflation", "group_key": "markets",
        "weight": 1,
        "chart_read": {
            "signal": "The trailing average keeps grinding lower.",
            "context": context,
            "implication": "Real rates stay positive into the next MPC.",
        },
    }])


def _year_ago_raw():
    return [{
        "slug": "macro",
        "metrics": [{"label": "CPI 12m Avg", "value": 8.88, "unit": "%",
                     "cadence": "monthly", "as_of": "2026-07-01"}],
        "series_summary": {"cpi_12m_avg_monthly": _year_ago_digest()},
    }]


def test_year_ago_claim_warns_when_it_names_the_window_start():
    """Issues 207/208: "a year earlier" carried 9.95 — the START of a 24-MONTH
    window (Aug 2024), not the 12-months-back point (9.77, Jul 2025). The
    figure is real and it clears every value check, because `first_value` is
    genuinely in the digest — the LIE is the label attached to it."""
    from brief.validators.prose_numbers import check_year_ago_claims

    brief = _year_ago_brief("CPI 12m-avg is down from 9.95% a year earlier.")
    warnings = check_year_ago_claims(brief, {r["slug"]: r for r in _year_ago_raw()})

    assert len(warnings) == 1
    assert warnings[0].kind == "year_ago_mislabel"
    assert warnings[0].section == "macro"
    assert warnings[0].field_path == "macro.chart_read.context"
    assert "9.95" in warnings[0].matched_text
    # the honest number is reported so a human can see the correction
    assert warnings[0].nearest_value == 9.77


def test_year_ago_claim_is_clean_when_it_names_the_real_year_ago_point():
    from brief.validators.prose_numbers import check_year_ago_claims

    brief = _year_ago_brief("CPI 12m-avg is down from 9.77% a year earlier.")
    assert check_year_ago_claims(brief, {r["slug"]: r for r in _year_ago_raw()}) == []


def test_year_ago_claim_is_silent_when_the_window_has_no_year_ago_point():
    """No `value_1y_ago` means there is no honest alternative to point at, so
    the check says nothing rather than guessing — same fail-quiet convention
    the rest of the module uses."""
    from brief.validators.prose_numbers import check_year_ago_claims

    raw = _year_ago_raw()
    raw[0]["series_summary"]["cpi_12m_avg_monthly"] = _year_ago_digest(
        value_1y_ago=None, ts_1y_ago=None
    )
    brief = _year_ago_brief("CPI 12m-avg is down from 9.95% a year earlier.")
    assert check_year_ago_claims(brief, {r["slug"]: r for r in raw}) == []


def test_year_ago_claim_ignores_a_number_in_a_different_clause():
    """Precision guard: only the number in the SAME clause as the phrase is
    the one being labelled "a year earlier". A window-start figure quoted in
    a neighbouring sentence is not a mislabel."""
    from brief.validators.prose_numbers import check_year_ago_claims

    brief = _year_ago_brief(
        "The series opened at 9.95% back in Aug 2024. It is down from 9.77% a year earlier."
    )
    assert check_year_ago_claims(brief, {r["slug"]: r for r in _year_ago_raw()}) == []


def test_year_ago_claim_never_blocks_and_rides_the_orchestrator():
    """WARN-mode only — `run_prose_number_gate` must return the finding, never
    raise on it (`check_count_claims` stays the only unconditional BLOCK,
    AGENTS.md landmine 34)."""
    brief = _year_ago_brief("CPI 12m-avg is down from 9.95% a year earlier.")
    warnings = run_prose_number_gate(brief, _year_ago_raw())
    assert any(w.kind == "year_ago_mislabel" for w in warnings)
