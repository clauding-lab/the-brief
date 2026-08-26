"""Tests for what a previous issue is allowed to hand forward.

Two layers, added a fortnight apart, aimed at the same contamination:

* `_scrub_numbers` (P0, 2026-08-22 audit #204) — no FIGURE from a previous
  issue reaches a prompt. The audit found exact old numbers ("$2.82bn",
  "fourteen reads") fossilizing forward. This is now the SUB-EDITOR's copy.
* `_previous_brief_skeleton` (2026-08-26, issue 208) — no WORDING from a
  previous issue reaches the EDITOR. Scrubbing numbers left every sentence
  intact, and where the data had not moved the editor simply restated
  yesterday's line: `macro` came back 100.0% byte-identical in issue 207, and
  a prompt rule forbidding it (PR #178) still left `banking` at 97.4% in 208.

Throughout, `_index_previous_metrics` / `stamp_changed` / `mark_held_overs`
keep reading the real, unscrubbed object — neither layer may disturb that.
"""
from __future__ import annotations

from datetime import date

from brief import pipeline_v6
from brief.pipeline_v6 import (
    _build_editor_input,
    _previous_brief_skeleton,
    _scrub_numbers,
)
from brief.schema import SectionData


# ── unit: the scrub itself ───────────────────────────────────────────────────

def test_scrubs_a_bare_number_in_a_string():
    assert _scrub_numbers("155 days old") == "‹n› days old"


def test_currency_symbol_and_unit_suffix_survive_around_the_placeholder():
    """The example from the audit: "$2.82bn" fossilized forward verbatim."""
    assert _scrub_numbers("July $2.82bn") == "July $‹n›bn"


def test_percent_sign_survives_around_the_placeholder():
    assert _scrub_numbers("9.16% headline inflation") == "‹n›% headline inflation"


def test_decimal_number_is_one_token_not_two():
    assert _scrub_numbers("$14.09 crude") == "$‹n› crude"


def test_thousands_commas_are_part_of_the_token():
    assert _scrub_numbers("2,858.68 mn") == "‹n› mn"


def test_multiple_numbers_in_one_string_are_all_scrubbed():
    assert _scrub_numbers("from 2820.0 to 2858.68") == "from ‹n› to ‹n›"


def test_words_and_structure_survive_the_scrub():
    text = "Reserves firmed to $35.11B; the book stays defensive on import cover."
    scrubbed = _scrub_numbers(text)
    assert "Reserves firmed to $" in scrubbed
    assert "the book stays defensive on import cover." in scrubbed
    assert "35.11" not in scrubbed


def test_a_string_with_no_digits_is_unchanged():
    assert _scrub_numbers("no figures here") == "no figures here"


def test_recurses_into_nested_dicts_and_lists():
    obj = {
        "brief": {"todays_call": "Reserves at $35.11B."},
        "sections": [{"metrics": [{"value": "2820.0", "label": "Remittance"}]}],
    }
    scrubbed = _scrub_numbers(obj)
    assert scrubbed["brief"]["todays_call"] == "Reserves at $‹n›B."
    assert scrubbed["sections"][0]["metrics"][0]["value"] == "‹n›"
    assert scrubbed["sections"][0]["metrics"][0]["label"] == "Remittance"


def test_allowlisted_structural_keys_survive_as_real_numbers():
    """issue_no/volume/ord/weight/read_minutes are pipeline bookkeeping, not
    prose the editor could quote forward — they stay real ints/floats."""
    obj = {"issue_no": 190, "volume": 2, "ord": 3, "weight": 1, "read_minutes": 8}
    assert _scrub_numbers(obj) == obj


def test_bools_and_none_pass_through_unscrubbed():
    """bool is a subclass of int in Python — it must never be treated as a
    figure to scrub, and None already carries no number."""
    obj = {"changed": True, "held_from": None, "hero": False}
    assert _scrub_numbers(obj) == obj


def test_non_allowlisted_numeric_leaves_are_scrubbed_to_none():
    """M2, review round 1: a NUMERIC leaf under a key that isn't on the
    allowlist is a figure the editor could quote forward just as easily as a
    string one — e.g. a metric that hasn't been stringified yet, or any raw
    numeric field the editor's own re-read of `previous_brief` could copy."""
    obj = {"value": 2820.0, "delta_pct": 0.99, "count": 14}
    assert _scrub_numbers(obj) == {"value": None, "delta_pct": None, "count": None}


def test_movers_prices_and_returns_are_scrubbed():
    """M2, review round 1: DS30 mover rows carry numeric `price`/`return_pct`
    fields directly (not stringified) — these must not reach the editor
    unscrubbed, the same as any other previous-issue figure."""
    obj = {"movers": [
        {"ticker": "SQUARE", "price": 245.5, "return_pct": 3.2},
        {"ticker": "GP", "price": 310.0, "return_pct": -1.4},
    ]}
    scrubbed = _scrub_numbers(obj)
    for row in scrubbed["movers"]:
        assert row["price"] is None
        assert row["return_pct"] is None
    # Non-numeric fields (ticker) are untouched.
    assert [r["ticker"] for r in scrubbed["movers"]] == ["SQUARE", "GP"]


def test_allowlist_applies_per_leaf_key_not_per_container():
    """A list of dicts under the "movers" key must NOT inherit "movers" as
    the key context for each item's OWN fields — only a leaf's immediate
    key (e.g. "price") decides whether it's scrubbed."""
    obj = {"movers": [{"weight": 99.5}]}
    # "weight" IS allowlisted (a section's structural weight, 1 or 2) — so
    # even nested inside a list this specific key name survives, proving the
    # key context flows from the dict's OWN keys, not the outer container.
    assert _scrub_numbers(obj) == {"movers": [{"weight": 99.5}]}


def test_scrub_never_mutates_the_original_object():
    """Every branch must return a NEW structure — `_build_editor_input`
    reuses `previous_brief` for `_index_previous_metrics`/`stamp_changed`/
    `mark_held_overs` before this runs, and a future call must see the same
    real values, not whatever the editor's copy was scrubbed into."""
    import copy

    original = {
        "brief": {"volume": 1, "todays_call": "Remittances hit $2.82bn in July."},
        "sections": [{"metrics": [{"value": 2820.0, "label": "Remittance"}],
                      "movers": [{"ticker": "SQUARE", "price": 245.5}]}],
    }
    before = copy.deepcopy(original)
    _scrub_numbers(original)
    assert original == before


def test_none_passes_through():
    assert _scrub_numbers(None) is None


def test_empty_containers_pass_through():
    assert _scrub_numbers({}) == {}
    assert _scrub_numbers([]) == []


# ── integration: only the editor's copy is scrubbed ─────────────────────────

def _section(metrics: list) -> SectionData:
    return SectionData(id="remit", title="Remittance", metrics=metrics, freshness="fresh")


def test_editor_input_previous_brief_carries_no_prose_and_no_figures(monkeypatch):
    """The editor's copy drops `todays_call` outright — prose AND figure."""
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 190)
    previous = {
        "brief": {"volume": 1, "todays_call": "Remittances hit $2.82bn in July."},
        "sections": [],
    }
    editor_input, _ = _build_editor_input(
        [], date(2026, 8, 22), [],
        previous_brief=previous, previous_lens=None,
        recent_news=[], metric_definitions=[],
    )
    assert "todays_call" not in editor_input["previous_brief"]["brief"]
    assert "2.82" not in str(editor_input["previous_brief"])
    assert "Remittances" not in str(editor_input["previous_brief"])


def test_editor_input_meta_volume_still_reads_the_real_unscrubbed_number(monkeypatch):
    """The scrub applies to the copy the editor reads as prose; `meta.volume`
    is structural bookkeeping and must stay a real, usable int."""
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 190)
    previous = {"brief": {"volume": 3}, "sections": []}
    editor_input, _ = _build_editor_input(
        [], date(2026, 8, 22), [],
        previous_brief=previous, previous_lens=None,
        recent_news=[], metric_definitions=[],
    )
    assert editor_input["meta"]["volume"] == 3


def test_build_editor_input_does_not_mutate_the_caller_supplied_previous_brief(monkeypatch):
    """M2, review round 1: the missing test the reviewer demanded — the
    ORIGINAL `previous_brief` dict passed into `_build_editor_input` (which
    `_index_previous_metrics`/`stamp_changed`/`mark_held_overs` all read
    downstream in `run_publish`) must be byte-for-byte the same object after
    the scrubbed copy is built for the editor prompt."""
    import copy

    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 190)
    previous = {
        "brief": {"volume": 1, "todays_call": "Remittances hit $2.82bn in July."},
        "sections": [{"slug": "remit", "metrics": [{"label": "Monthly Remittance", "value": "2820.0"}]}],
    }
    before = copy.deepcopy(previous)
    _build_editor_input(
        [], date(2026, 8, 22), [],
        previous_brief=previous, previous_lens=None,
        recent_news=[], metric_definitions=[],
    )
    assert previous == before


def test_none_previous_brief_does_not_crash_the_scrub(monkeypatch):
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 0)
    editor_input, _ = _build_editor_input(
        [], date(2026, 8, 22), [],
        previous_brief=None, previous_lens=None,
        recent_news=[], metric_definitions=[],
    )
    assert editor_input["previous_brief"] is None


# ── the editor's skeleton: shape kept, wording gone ──────────────────────────

def _realistic_previous() -> dict:
    """Shaped like a real `fetch_previous_brief()` row, prose in every field
    that has ever carried it — so a new prose field slipping through the
    allowlist shows up as a failure here rather than in tomorrow's issue."""
    return {
        "brief": {
            "id": "c1b4ed0e",
            "issue_no": 208,
            "volume": 2,
            "brief_date": "2026-08-26",
            "lens": "dse",
            "frame": "credit-cycle",
            "read_minutes": 15,
            "status": "published",
            "todays_call": "The equity market is the clearest read this issue.",
            "cover_metric": {
                "label": "DSEX · 25 AUG 2026",
                "value": "5,640",
                "sub": "Ten-session low as turnover drains to Tk507cr",
                "tone": "warn",
                "as_of": "25 Aug 2026",
                "section_slug": "dse",
            },
        },
        "sections": [
            {
                "id": "698a3b7e",
                "brief_id": "c1b4ed0e",
                "slug": "bb",
                "ord": 3,
                "weight": 1,
                "title": "Policy & Rates (Bangladesh Bank)",
                "group_key": "banking",
                "verdict_tone": "neu",
                "freshness": "stale",
                "verdict": "The front holds sub-policy while the reserve read stays weeks old.",
                "tldr": "Call front sits below policy; the reserve read is weeks old.",
                "analysis": "Liquidity is not the constraint — demand is.",
                "banker_read": {
                    "verdict": "The corridor front holds easy — overnight call at 9.2%.",
                    "watch": ["Whether the 14-day call holds above the 11.0% SLF ceiling"],
                    "risk": ["Deposit rates lagging the falling bill curve"],
                    "runway": {"value": "4.85", "unit": "mo import cover"},
                },
                "chart_read": {
                    "signal": "Gross reserves $36.42bn as of the Jul 2026 print.",
                    "context": "Rebuild stalled below the $37.58bn peak.",
                    "implication": "Treasury: watch the next read.",
                },
                "summary_pills": [{"key": "POLICY RATE", "value": "9.5%", "tone": "neu"}],
                "movers": [{"ticker": "SQUARE", "price": 245.5}],
                "news": [{"headline": "BB holds the repo at 9.5%"}],
                "metrics": [
                    {
                        "label": "Overnight Call Money",
                        "value": "9.2%",
                        "sub": "30bp under the 9.5% policy — the front holds easy",
                        "tone": "neu",
                        "ord": 0,
                        "weight": 2,
                    }
                ],
            }
        ],
    }


def test_skeleton_keeps_the_structural_fields_the_editor_documents():
    """Hero rotation and stance-flip detection are the two uses `editor_v6.txt`
    names for `previous_brief`. Both must survive, or the skeleton has cut too
    deep and the editor loses something it was told to rely on."""
    sk = _previous_brief_skeleton(_realistic_previous())
    assert sk["brief"]["cover_metric"]["section_slug"] == "dse"   # hero rotation
    assert sk["brief"]["lens"] == "dse"
    assert sk["brief"]["frame"] == "credit-cycle"
    assert sk["brief"]["issue_no"] == 208
    assert sk["brief"]["volume"] == 2
    section = sk["sections"][0]
    assert section["slug"] == "bb"
    assert section["ord"] == 3
    assert section["weight"] == 1
    assert section["verdict_tone"] == "neu"                        # stance flip
    assert section["freshness"] == "stale"
    assert section["title"] == "Policy & Rates (Bangladesh Bank)"
    assert section["group_key"] == "banking"
    assert section["metric_labels"] == ["Overnight Call Money"]


def test_skeleton_drops_every_prose_bearing_field():
    """The point of the change. Named field-by-field rather than by a blanket
    substring sweep so a regression says WHICH field came back."""
    section = _previous_brief_skeleton(_realistic_previous())["sections"][0]
    for field in (
        "verdict", "tldr", "analysis", "banker_read", "chart_read",
        "summary_pills", "movers", "news", "metrics",
    ):
        assert field not in section, f"prose field {field!r} reached the editor"
    brief = _previous_brief_skeleton(_realistic_previous())["brief"]
    assert "todays_call" not in brief
    assert set(brief["cover_metric"]) == {"section_slug", "tone"}


def test_no_sentence_from_yesterday_survives_anywhere_in_the_skeleton():
    """Belt and braces over the field-by-field test: the actual sentences from
    issue 208 must not appear at any depth, however the shape is rearranged."""
    blob = str(_previous_brief_skeleton(_realistic_previous()))
    for phrase in (
        "The front holds sub-policy",
        "Call front sits below policy",
        "Liquidity is not the constraint",
        "The corridor front holds easy",
        "Rebuild stalled",
        "Ten-session low",
        "the front holds easy",
        "BB holds the repo",
    ):
        assert phrase not in blob, f"carried forward: {phrase!r}"


def test_no_figure_from_yesterday_survives_in_the_skeleton():
    """`_scrub_numbers` is not applied here — the allowlist is what keeps
    figures out. That is stronger (a new field is excluded by default) but it
    means this has to be asserted directly."""
    blob = str(_previous_brief_skeleton(_realistic_previous()))
    for figure in ("5,640", "9.2%", "36.42", "37.58", "11.0", "4.85", "245.5", "Tk507cr"):
        assert figure not in blob, f"figure survived: {figure!r}"


def test_a_new_schema_field_is_excluded_by_default():
    """The allowlist direction. If a future migration adds a prose column, it
    must not reach the editor just because nobody remembered to deny it."""
    prev = _realistic_previous()
    prev["sections"][0]["editors_note"] = "A sentence a future schema might add."
    prev["brief"]["standfirst"] = "And one at brief level."
    sk = _previous_brief_skeleton(prev)
    assert "editors_note" not in sk["sections"][0]
    assert "standfirst" not in sk["brief"]


def test_skeleton_handles_none_and_empty_shapes():
    assert _previous_brief_skeleton(None) is None
    assert _previous_brief_skeleton({}) is None
    assert _previous_brief_skeleton({"brief": {}, "sections": []}) == {
        "brief": {
            "issue_no": None, "volume": None, "lens": None, "frame": None,
            "cover_metric": {"section_slug": None, "tone": None},
        },
        "sections": [],
    }


def test_skeleton_tolerates_a_section_with_no_metrics():
    prev = _realistic_previous()
    prev["sections"][0]["metrics"] = None
    assert _previous_brief_skeleton(prev)["sections"][0]["metric_labels"] == []


def test_skeleton_never_mutates_the_original():
    """Same contract as `_scrub_numbers`: `stamp_changed` / `mark_held_overs`
    read the real object after this runs."""
    import copy

    prev = _realistic_previous()
    before = copy.deepcopy(prev)
    _previous_brief_skeleton(prev)
    assert prev == before


def test_the_two_copies_differ_exactly_as_intended():
    """Editor blind, reviewer sighted — the split `run_publish` relies on.

    The Sub-Editor's §7 CARRIED-FORWARD PROSE check compares WORDING against
    `raw_data.previous_brief`. If both copies were reduced to the skeleton the
    reviewer would have nothing to compare and the check would silently become
    a no-op — the failure mode this pins.
    """
    prev = _realistic_previous()
    editors = str(_previous_brief_skeleton(prev))
    reviewers = str(_scrub_numbers(prev))
    sentence = "The corridor front holds easy"
    assert sentence not in editors
    assert sentence in reviewers
    # ...and the reviewer's copy is still figure-free.
    assert "9.2" not in reviewers
