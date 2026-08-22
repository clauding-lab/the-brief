"""Tests for `_scrub_numbers` — the previous-brief numeric scrub.

P0 honesty fix (2026-08-22 audit #204): the editor is fed the PREVIOUS issue's
full payload (`previous_brief`) for narrative continuity, and reads the
numbers in there too — the audit found exact old figures ("$2.82bn",
"fourteen reads") fossilizing forward across issues. `_scrub_numbers`
replaces every digit-sequence in string values with a placeholder before that
object reaches the editor prompt, while `_index_previous_metrics` /
`stamp_changed` / `mark_held_overs` keep reading the real, unscrubbed values.
"""
from __future__ import annotations

from datetime import date

from brief import pipeline_v6
from brief.pipeline_v6 import _build_editor_input, _scrub_numbers
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


def test_non_string_leaves_pass_through_unchanged():
    """Structural ints/floats/bools/None are not text — only string prose and
    stringified figures carry a "digit-sequence" in the sense this scrub
    targets. issue_no/volume stay real ints for downstream logic."""
    obj = {"issue_no": 190, "volume": 2, "changed": True, "held_from": None}
    assert _scrub_numbers(obj) == obj


def test_none_passes_through():
    assert _scrub_numbers(None) is None


def test_empty_containers_pass_through():
    assert _scrub_numbers({}) == {}
    assert _scrub_numbers([]) == []


# ── integration: only the editor's copy is scrubbed ─────────────────────────

def _section(metrics: list) -> SectionData:
    return SectionData(id="remit", title="Remittance", metrics=metrics, freshness="fresh")


def test_editor_input_previous_brief_is_scrubbed(monkeypatch):
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
    assert editor_input["previous_brief"]["brief"]["todays_call"] == \
        "Remittances hit $‹n›bn in July."
    # "2.82" must not survive anywhere in the scrubbed copy.
    assert "2.82" not in str(editor_input["previous_brief"])


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


def test_none_previous_brief_does_not_crash_the_scrub(monkeypatch):
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 0)
    editor_input, _ = _build_editor_input(
        [], date(2026, 8, 22), [],
        previous_brief=None, previous_lens=None,
        recent_news=[], metric_definitions=[],
    )
    assert editor_input["previous_brief"] is None
