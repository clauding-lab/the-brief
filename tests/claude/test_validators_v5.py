from brief.claude.validators import validate_top_picks


VALID_PAYLOAD = {
    "plotted": [
        {"id": "bb",      "x": 1.2, "y": 6.0, "r": 24, "kind": "anchor"},
        {"id": "macro",   "x": 2.2, "y": 7.8, "r": 32, "kind": "slow"},
        {"id": "fx",      "x": 3.4, "y": 6.3, "r": 28, "kind": "slow"},
        {"id": "remit",   "x": 6.0, "y": 7.0, "r": 30, "kind": "fresh"},
        {"id": "dse",     "x": 6.5, "y": 4.8, "r": 26, "kind": "fresh"},
        {"id": "tbond",   "x": 5.0, "y": 5.4, "r": 24, "kind": "fresh"},
        {"id": "iranwar", "x": 9.4, "y": 9.1, "r": 38, "kind": "event"},
    ],
    "grid": [
        {"id": "banking", "tldr": "NPL 35.73% — historic high"},
        {"id": "comm", "tldr": "LNG JKM $10.4 flat WoW"},
        {"id": "fiscal", "tldr": "NBR YTD 2.84tn"},
        {"id": "nbr", "tldr": "Mar VAT print due Sun"},
        {"id": "dam", "tldr": "Onion +12% WoW"},
        {"id": "headlines", "tldr": "9 curated stories"},
        {"id": "exec", "tldr": "6 prints · 3 watches"},
    ],
    "front_of_book_id": "iranwar",
}

ALL_IDS = {"bb", "macro", "fx", "remit", "dse", "tbond", "iranwar",
           "banking", "comm", "fiscal", "nbr", "dam", "headlines", "exec"}


def test_top_picks_valid():
    result = validate_top_picks(VALID_PAYLOAD, allowed_ids=ALL_IDS)
    assert result.ok
    assert result.value.front_of_book_id == "iranwar"


def test_top_picks_rejects_wrong_plotted_count():
    bad = dict(VALID_PAYLOAD)
    bad["plotted"] = VALID_PAYLOAD["plotted"][:5]
    result = validate_top_picks(bad, allowed_ids=ALL_IDS)
    assert not result.ok
    assert "exactly 7" in result.reason


def test_top_picks_rejects_overlapping_plotted_and_grid():
    bad = dict(VALID_PAYLOAD)
    bad["grid"] = [{"id": "bb", "tldr": "x"}] + VALID_PAYLOAD["grid"][1:]
    result = validate_top_picks(bad, allowed_ids=ALL_IDS)
    assert not result.ok
    assert "overlap" in result.reason.lower()


def test_top_picks_rejects_unknown_id():
    bad = dict(VALID_PAYLOAD)
    bad["plotted"] = list(VALID_PAYLOAD["plotted"])
    bad["plotted"][0] = {"id": "ghost", "x": 1, "y": 1, "r": 10, "kind": "anchor"}
    result = validate_top_picks(bad, allowed_ids=ALL_IDS)
    assert not result.ok
    assert "ghost" in result.reason


def test_top_picks_rejects_front_of_book_not_in_plotted():
    bad = dict(VALID_PAYLOAD)
    bad["front_of_book_id"] = "banking"  # banking is in grid, not plotted
    result = validate_top_picks(bad, allowed_ids=ALL_IDS)
    assert not result.ok
    assert "front_of_book" in result.reason


def test_top_picks_rejects_tldr_too_long():
    bad = {**VALID_PAYLOAD, "grid": [
        *VALID_PAYLOAD["grid"][:6],
        {"id": "exec", "tldr": "this is way too long " * 10},
    ]}
    result = validate_top_picks(bad, allowed_ids=ALL_IDS)
    assert not result.ok
    assert "tldr" in result.reason.lower()


# ---------------------------------------------------------------------------
# Task 12: validate_todays_call (V5 — Call 3)
# ---------------------------------------------------------------------------

from brief.claude.validators import validate_todays_call


def test_todays_call_valid():
    payload = {
        "text": "Hormuz is priced risk, not scarcity. " * 10,
        "byline": "Desk Editor · The Brief",
    }
    result = validate_todays_call(payload)
    assert result.ok


def test_todays_call_rejects_too_short():
    payload = {"text": "Short.", "byline": "x"}
    result = validate_todays_call(payload)
    assert not result.ok
    assert "60-100" in result.reason


def test_todays_call_rejects_too_long():
    payload = {"text": "word " * 200, "byline": "x"}
    result = validate_todays_call(payload)
    assert not result.ok


def test_todays_call_rejects_double_quotes_in_text():
    payload = {
        "text": 'Hormuz is "priced risk" not scarcity. ' * 10,
        "byline": "x",
    }
    result = validate_todays_call(payload)
    assert not result.ok
    assert "double quote" in result.reason.lower()


# ---------------------------------------------------------------------------
# Task 13: validate_bankerread_structured (V5 — Call 4) + stale variant
# ---------------------------------------------------------------------------

from brief.claude.validators import validate_bankerread_structured


def test_bankerread_structured_full_valid():
    payload = {
        "variant": "full",
        "meaning": "word " * 90,
        "action": "word " * 90,
        "trigger": "word " * 90,
        "focus": "word " * 90,
        "pull_quote": "Concise editorial line.",
    }
    result = validate_bankerread_structured(payload)
    assert result.ok
    assert result.value.variant == "full"


def test_bankerread_structured_stale_valid():
    payload = {
        "variant": "stale_micro",
        "meaning": "word " * 80,
        "pull_quote": "Concise editorial line.",
    }
    result = validate_bankerread_structured(payload)
    assert result.ok
    assert result.value.action is None


def test_bankerread_structured_full_rejects_short_field():
    payload = {
        "variant": "full",
        "meaning": "too short",
        "action": "word " * 90,
        "trigger": "word " * 90,
        "focus": "word " * 90,
        "pull_quote": "Quote",
    }
    result = validate_bankerread_structured(payload)
    assert not result.ok
    assert "meaning" in result.reason


def test_bankerread_structured_rejects_double_quote():
    payload = {
        "variant": "full",
        "meaning": ('word ' * 60) + '"x"',
        "action": "word " * 90,
        "trigger": "word " * 90,
        "focus": "word " * 90,
        "pull_quote": "x",
    }
    result = validate_bankerread_structured(payload)
    assert not result.ok


def test_bankerread_structured_rejects_long_pull_quote():
    payload = {
        "variant": "full",
        "meaning": "word " * 90,
        "action": "word " * 90,
        "trigger": "word " * 90,
        "focus": "word " * 90,
        "pull_quote": "word " * 30,
    }
    result = validate_bankerread_structured(payload)
    assert not result.ok
    assert "pull_quote" in result.reason
