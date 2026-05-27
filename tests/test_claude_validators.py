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
