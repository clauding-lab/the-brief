from brief.claude.validators import (
    BANAL_TOKENS,
    TEMPORAL_TOKENS,
    DESK_WORDS,
    ACTION_VERBS,
    TIER1_ABBREVS,
    TIER2_ABBREVS_AND_EXPANSIONS,
)


def test_banal_tokens_includes_known_ai_tells():
    assert "delve" in BANAL_TOKENS
    assert "myriad" in BANAL_TOKENS
    assert "tapestry" in BANAL_TOKENS
    assert "amid" in BANAL_TOKENS
    assert "moreover" in BANAL_TOKENS


def test_temporal_tokens_includes_anchor_words():
    assert "since" in TEMPORAL_TOKENS
    assert "vs" in TEMPORAL_TOKENS
    assert "last" in TEMPORAL_TOKENS
    assert "above" in TEMPORAL_TOKENS


def test_desk_words_includes_banker_vocab():
    assert "treasury" in DESK_WORDS
    assert "alm" in DESK_WORDS
    assert "alco" in DESK_WORDS
    assert "lcr" in DESK_WORDS


def test_action_verbs_includes_decisional_verbs():
    assert "watch" in ACTION_VERBS
    assert "expect" in ACTION_VERBS
    assert "tighten" in ACTION_VERBS


def test_tier1_abbreviations_includes_bb_and_friends():
    assert "BB" in TIER1_ABBREVS
    assert "NBR" in TIER1_ABBREVS
    assert "MPS" in TIER1_ABBREVS
    assert "NPL" in TIER1_ABBREVS
    assert "USD/BDT" in TIER1_ABBREVS


def test_tier2_expansions_includes_prudential_ratios():
    assert TIER2_ABBREVS_AND_EXPANSIONS["LCR"] == "Liquidity Coverage Ratio"
    assert TIER2_ABBREVS_AND_EXPANSIONS["NSFR"] == "Net Stable Funding Ratio"
    assert TIER2_ABBREVS_AND_EXPANSIONS["REER"] == "Real Effective Exchange Rate"


# ---------------------------------------------------------------------------
# Task 2.2: validate_no_banal_language
# ---------------------------------------------------------------------------

from brief.claude.validators import validate_no_banal_language


def test_validate_no_banal_language_passes_clean_text():
    result = validate_no_banal_language("Brent +2.4% to $87.20, third weekly gain since Q2 2024.")
    assert result.ok


def test_validate_no_banal_language_fails_on_delve():
    result = validate_no_banal_language("We delve into the implications for ALCO.")
    assert not result.ok
    assert "delve" in result.reason.lower()


def test_validate_no_banal_language_fails_on_amid():
    result = validate_no_banal_language("Sentiment soured amid policy uncertainty.")
    assert not result.ok


def test_validate_no_banal_language_is_case_insensitive():
    result = validate_no_banal_language("Markets navigate INTRICATE terrain.")
    assert not result.ok


# ---------------------------------------------------------------------------
# Task 2.3: validate_chart_read_temporal_anchor
# ---------------------------------------------------------------------------

from brief.claude.validators import validate_chart_read_temporal_anchor


def test_validate_chart_read_temporal_anchor_passes_with_since():
    chart_read = {
        "signal": "Brent +2.4% to $87.20.",
        "context": "Highest since Q2 2024 ($91.40 then).",
        "implication": "Watch H2 import bills.",
    }
    assert validate_chart_read_temporal_anchor(chart_read).ok


def test_validate_chart_read_temporal_anchor_passes_with_year_token():
    chart_read = {"signal": "x", "context": "First time above 5% in 2025.", "implication": "y"}
    assert validate_chart_read_temporal_anchor(chart_read).ok


def test_validate_chart_read_temporal_anchor_fails_without_anchor():
    chart_read = {"signal": "x", "context": "Inflation remains elevated.", "implication": "y"}
    assert not validate_chart_read_temporal_anchor(chart_read).ok


# ---------------------------------------------------------------------------
# Task 2.4: validate_chart_read_implication_quality
# ---------------------------------------------------------------------------

from brief.claude.validators import validate_chart_read_implication_quality


def test_validate_chart_read_implication_quality_passes_with_desk_word():
    chart_read = {"signal": "x", "context": "y", "implication": "Watch ALCO positioning."}
    assert validate_chart_read_implication_quality(chart_read).ok


def test_validate_chart_read_implication_quality_passes_with_action_verb():
    chart_read = {"signal": "x", "context": "y", "implication": "Expect rate hold next MPS."}
    assert validate_chart_read_implication_quality(chart_read).ok


def test_validate_chart_read_implication_quality_fails_on_generic():
    chart_read = {"signal": "x", "context": "y", "implication": "May affect the economy."}
    assert not validate_chart_read_implication_quality(chart_read).ok


# ---------------------------------------------------------------------------
# Task 2.5: validate_chart_read_length + validate_history_claim_has_reference
# ---------------------------------------------------------------------------

from brief.claude.validators import (
    validate_chart_read_length,
    validate_history_claim_has_reference,
)


def test_validate_chart_read_length_passes_under_caps():
    chart_read = {
        "signal": " ".join(["word"] * 25),       # exactly 25
        "context": " ".join(["word"] * 20),      # exactly 20
        "implication": " ".join(["word"] * 25),  # exactly 25
    }
    assert validate_chart_read_length(chart_read).ok


def test_validate_chart_read_length_fails_on_signal_over_25():
    chart_read = {"signal": " ".join(["word"] * 26), "context": "x", "implication": "y"}
    result = validate_chart_read_length(chart_read)
    assert not result.ok
    assert "signal" in result.reason


def test_validate_chart_read_length_fails_on_context_over_20():
    chart_read = {"signal": "x", "context": " ".join(["w"] * 21), "implication": "y"}
    result = validate_chart_read_length(chart_read)
    assert not result.ok
    assert "context" in result.reason


def test_validate_history_claim_has_reference_passes_with_parens():
    used_facts = [{
        "phrase": "lowest 12-month CPI since Sep 2021 (4.8% then)",
        "reference_value_formatted": "4.8%",
    }]
    text = "Inflation eased to 5.2% — lowest 12-month CPI since Sep 2021 (4.8% then)."
    assert validate_history_claim_has_reference(text, used_facts).ok


def test_validate_history_claim_has_reference_fails_when_parens_dropped():
    used_facts = [{
        "phrase": "lowest 12-month CPI since Sep 2021 (4.8% then)",
        "reference_value_formatted": "4.8%",
    }]
    text = "Inflation eased to 5.2% — lowest 12-month CPI since Sep 2021."  # parens dropped
    result = validate_history_claim_has_reference(text, used_facts)
    assert not result.ok


# ---------------------------------------------------------------------------
# Task 2.6: validate_abbreviation_policy
# ---------------------------------------------------------------------------

from brief.claude.validators import validate_abbreviation_policy


def test_validate_abbreviation_policy_passes_when_tier2_expanded_on_first_use():
    text = (
        "LCR (Liquidity Coverage Ratio) pressure rises in mid-tier banks. "
        "LCR will tighten further if BB acts."
    )
    assert validate_abbreviation_policy(
        text,
        tier1_set=TIER1_ABBREVS,
        tier2_expansions=TIER2_ABBREVS_AND_EXPANSIONS,
    ).ok


def test_validate_abbreviation_policy_fails_when_tier2_unexpanded():
    text = "LCR pressure rises in mid-tier banks. Treasury desks should watch the rate."
    result = validate_abbreviation_policy(
        text,
        tier1_set=TIER1_ABBREVS,
        tier2_expansions=TIER2_ABBREVS_AND_EXPANSIONS,
    )
    assert not result.ok
    assert "LCR" in result.reason


def test_validate_abbreviation_policy_passes_when_no_tier2_in_text():
    text = "NPL ratio at 35.7% — BB MPS due Wednesday."
    assert validate_abbreviation_policy(
        text,
        tier1_set=TIER1_ABBREVS,
        tier2_expansions=TIER2_ABBREVS_AND_EXPANSIONS,
    ).ok


# ---------------------------------------------------------------------------
# Fix 1: Word-boundary checks — substring false-positive regressions
# ---------------------------------------------------------------------------


def test_validate_no_banal_language_does_not_match_substring():
    # "robustly" should NOT trigger "robust" banal flag
    assert validate_no_banal_language("Robustly capitalised banks weathered the storm.").ok
    # But "robust" alone or with punctuation SHOULD
    assert not validate_no_banal_language("A robust framework is needed.").ok


def test_validate_chart_read_implication_quality_does_not_match_car_in_scar():
    # "car" is a desk word substring but should not match in "scar"
    chart_read = {"signal": "x", "context": "y", "implication": "Old scar healing slowly."}
    assert not validate_chart_read_implication_quality(chart_read).ok


def test_validate_chart_read_temporal_anchor_does_not_match_next_in_context():
    # "next" in "context" should not trigger temporal anchor
    chart_read = {"signal": "x", "context": "Within the context of policy.", "implication": "y"}
    assert not validate_chart_read_temporal_anchor(chart_read).ok


# ---------------------------------------------------------------------------
# Fix 5: validate_chart_read_length — implication-over-25 test
# ---------------------------------------------------------------------------


def test_validate_chart_read_length_fails_on_implication_over_25():
    chart_read = {"signal": "x", "context": "y", "implication": " ".join(["w"] * 26)}
    result = validate_chart_read_length(chart_read)
    assert not result.ok
    assert "implication" in result.reason
