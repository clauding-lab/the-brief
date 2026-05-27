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
