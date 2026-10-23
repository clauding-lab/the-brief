"""A card's number is printed by code from the builder's checked observation (R2 fix 7b).

Owner decision (g), 26 Sep 2026: the model chooses which cards appear, their
labels and their commentary; the NUMBER on every card is printed by the
pipeline from the builder metric bound to that label, in the house format
(`_format_metric_value`, Master.md "Numbers and currency"). Whatever number text the Editor or the Sub-editor
writes — honest, reformatted, contradicted or garbage — never reaches the
published object. Replaces fix 7's parse-and-judge guard.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from brief import pipeline_v6
from brief.pipeline_v6 import _enforce_observation_contract
from brief.publication_identity import PublishIdentity
from brief.schema import Metric, SectionData
from brief.v6_schema import (
    BriefPayloadV6,
    BriefV6,
    MetricV6,
    NewsItemV6,
    SectionV6,
    SummaryPillV6,
)

TODAY = date(2026, 9, 25)


def _brief(slug: str, label: str, value: str, *, pills: list[str] = (),
           news: int = 0) -> BriefPayloadV6:
    section = SectionV6(
        slug=slug, ord=6, title="T", group_key="markets",
        metrics=[MetricV6(label=label, value=value)],
        summary_pills=[SummaryPillV6(key=f"P{i}", value=v) for i, v in enumerate(pills)],
        news=[NewsItemV6(headline=f"headline {i}") for i in range(news)],
    )
    return BriefPayloadV6(brief=BriefV6(issue_no=1, volume=1, brief_date=TODAY), sections=[section])


def _raw(slug: str, label: str, value: Any, unit: str, metric_id: str = "card") -> list[dict[str, Any]]:
    return [{"slug": slug, "metrics": [{
        "id": metric_id, "label": label, "value": value, "unit": unit, "as_of": "2026-09-22",
        "source": "DSE", "stale": False, "cadence": "daily", "period": "22 Sep 2026"}]}]


# (what the model wrote, builder value, builder unit, what must publish)
MODEL_TEXT_VS_OBSERVATION = [
    # The owner's examples and fix 7's review leaks.
    ("rose 140", 140, "stocks", "140"),
    ("140 gainers", 227, "stocks", "227"),
    ("▼36.42", 36.42, "bn USD", "$36.42bn"),
    ("$36.42 per gram", 4380.4, "USD/oz", "$4,380.4/oz"),
    ("10%", 9.5, "%", "9.5%"),
    ("garbage !!", 80.25, "USD/bbl", "$80.25"),
    ("", 80.25, "USD/bbl", "$80.25"),
    ("NaN", 80.25, "USD/bbl", "$80.25"),
    ("N/A", 5883.91, "index", "5,883.91"),
    ("$0.0tn", 36.42, "bn USD", "$36.42bn"),
    ("9.50% (was 10.00%)", 9.5, "%", "9.5%"),
    ("~$36.42bn", 36.42, "bn USD", "$36.42bn"),
    ("(80.25)", 80.25, "USD/bbl", "$80.25"),
    ("-80.25", 80.25, "USD/bbl", "$80.25"),
    ("‑1.77%", 1.77, "%", "1.77%"),
    ("9.50% revised", 9.5, "%", "9.5%"),
    ("$36.42bn NOK", 36.42, "bn USD", "$36.42bn"),
    ("€36.42bn", 36.42, "bn USD", "$36.42bn"),
    ("$3.5bn", 2970, "mn USD", "$2,970mn"),
    ("Tk3.61 lakh", 3.61, "BDT trn", "Tk 3.61tn"),
    # Honest but free-formatted model text is re-printed in the house format too.
    ("$$36.42bn", 36.42, "bn USD", "$36.42bn"),
    ("5,883.91 index", 5883.91, "index", "5,883.91"),
    ("-$1.77bn", -1.77, "bn USD", "−$1.77bn"),
    ("9.50 percent", 9.5, "%", "9.5%"),
    ("8.67%", 8.666, "pct", "8.666 pct"),
    ("Tk926cr", 926, "crore BDT", "Tk 926 cr"),
    ("6.28mo", 6.28, "months", "6.28 months"),
]


@pytest.mark.parametrize("model_output", [True, False], ids=["model-pass", "final-pass"])
@pytest.mark.parametrize("model_text,observed,unit,published", MODEL_TEXT_VS_OBSERVATION)
def test_the_published_card_number_is_the_builders_observation_whatever_the_model_wrote(
    model_text: str, observed: Any, unit: str, published: str, model_output: bool,
) -> None:
    card = _brief("dse", "Card", model_text)
    _enforce_observation_contract(card, _raw("dse", "Card", observed, unit),
                                  model_output=model_output)
    assert card.sections[0].metrics[0].value == published


# ── The house format (review round 1, controller findings C1–C3) ─────────────
# Master.md "Numbers and currency": comma thousands, "%" with no space, the minus
# glyph U+2212, "$" for USD, "Tk" for taka, and "only show what the source
# provided" — so the stamp prints the source's own clean decimal, never padded
# and never rounded. Float32 feeds widened to float64 (Brent 98.31999969482422)
# print their float32 decimal, and float64 arithmetic noise past 15 significant
# digits (a derived 1.2400000000000002) is not a digit the source gave. Cutting
# long tails for the screen stays the SPA's job (lib/format.tsx cleanMetricValue,
# owner decision 2026-08-29: truncate to 2 decimals, never round).
# (builder value, builder unit, the text the card must carry)
HOUSE_FORMAT = [
    (9.5, "%", "9.5%"),                        # no padding to 9.50
    (11.0, "%", "11%"),
    (8.645, "%", "8.645%"),                    # no rounding to 8.64 (screen: 8.64)
    (8.3198, "%", "8.3198%"),                  # screen: 8.31
    (-0.18332, "%", "−0.18332%"),              # minus glyph; screen: −0.18%
    (1.2400000000000002, "%", "1.24%"),        # float64 arithmetic noise dropped (9.5 − 8.26)
    # Float32 widening rows (98.31999969482422, 4328.89990234375, 5540.31982421875,
    # 65536.1015625) moved to FLOAT32_FEED below (R2 fix 7b3): clean-up is now
    # decided by the card's source, so each row names a float32-feed card.
    (122.9959, "index", "122.9959"),           # screen: 122.99
    (5540.32037, "index", "5,540.32037"),      # screen: 5,540.32
    (36.4222, "bn USD", "$36.4222bn"),         # a plain float64 keeps every digit
    (37.3523, "bn USD", "$37.3523bn"),
    (-3.31, "bn USD", "−$3.31bn"),
    (2858.68, "mn USD", "$2,858.68mn"),
    (1234567.0, "mn USD", "$1,234,567mn"),
    (791.4875, "crore BDT", "Tk 791.4875 cr"),
    (4.15, "BDT trn", "Tk 4.15tn"),
    (123.22, "BDT", "123.22"),                 # a USD/BDT rate, as issue 235 showed it
    (4.972006730098555, "months", "4.97200673009856 months"),
    (103, "stocks", "103"),                    # counts are bare whole numbers
    (227.0, "stocks", "227"),
    (9, "items", "9"),
    (0.0, "%", "0%"),
    (-0.0, "%", "0%"),
    (0.00001, "%", "0.00001%"),                # never exponent notation
    (1.5, "widgets", "1.5 widgets"),           # an unmapped unit keeps "<number> <unit>"
    (1.5, "", "1.5"),
]


@pytest.mark.parametrize("model_output", [True, False], ids=["model-pass", "final-pass"])
@pytest.mark.parametrize("observed,unit,published", HOUSE_FORMAT)
def test_a_card_prints_the_sources_own_decimal_in_the_house_style(
    observed: Any, unit: str, published: str, model_output: bool,
) -> None:
    card = _brief("dse", "Card", "model text")
    _enforce_observation_contract(card, _raw("dse", "Card", observed, unit), model_output=model_output)
    assert card.sections[0].metrics[0].value == published


# A float64 whose own decimal is short and exact is the source's number, even when
# the same bits also happen to be a float32. Clean-up may only drop noise digits;
# it must never replace a digit the source gave with another (R2 fix 7b round 2:
# 100000008.0 printed as "$100,000,010mn", 2500000.25 as "Tk 2,500,000.2 cr").
# (builder value, builder unit, the text the card must carry)
EXACT_SOURCE_DIGITS = [
    (100000008.0, "mn USD", "$100,000,008mn"),         # also exactly a float32
    (123456792.0, "crore BDT", "Tk 123,456,792 cr"),   # also exactly a float32
    (2500000.25, "crore BDT", "Tk 2,500,000.25 cr"),   # also exactly a float32
    (131072.0625, "index", "131,072.0625"),            # also exactly a float32
    (131072.03125, "index", "131,072.03125"),          # 11 digits, also exactly a float32
    (1048576.125, "index", "1,048,576.125"),           # also exactly a float32
    (1099511627776.0, "index", "1,099,511,627,776"),   # 2**40, also exactly a float32
    (1234567890123456.0, "index", "1,234,567,890,123,456"),  # 16 whole digits
    (12345678901234568.0, "index", "12,345,678,901,234,568"),
]


@pytest.mark.parametrize("model_output", [True, False], ids=["model-pass", "final-pass"])
@pytest.mark.parametrize("observed,unit,published", EXACT_SOURCE_DIGITS)
def test_a_card_never_prints_a_digit_the_source_did_not_give(
    observed: float, unit: str, published: str, model_output: bool,
) -> None:
    card = _brief("dse", "Card", "model text")
    _enforce_observation_contract(card, _raw("dse", "Card", observed, unit), model_output=model_output)
    assert card.sections[0].metrics[0].value == published


# ── Float32 clean-up is decided by the source, never guessed (R2 fix 7b3) ─────
# EconDelta reads Brent, WTI and gold from yfinance (scrapers/commodity_prices.py
# COMMODITY_SPEC), whose prices are float32: 98.32 arrives widened as
# 98.31999969482422. Only those three cards print float32's shortest decimal, at
# ANY magnitude — round 2's digit-count guess left gold 8,193.43 as
# 8193.4296875 (screen: 8,193.42). A float64 reading on those cards keeps its digits.
# (card id, builder value, builder unit, the text the card must carry)
FLOAT32_FEED = [
    ("iranwar_brent_spot", 98.31999969482422, "USD/bbl", "$98.32"),
    ("iranwar_wti_spot", 61.279998779296875, "USD/bbl", "$61.28"),
    ("iranwar_wti_spot", 92.25, "USD/bbl", "$92.25"),               # exact in float32 already
    ("fx_gold_usd_oz", 4328.89990234375, "USD/oz", "$4,328.9/oz"),
    ("fx_gold_usd_oz", 5540.31982421875, "USD/oz", "$5,540.32/oz"),
    ("fx_gold_usd_oz", 8193.4296875, "USD/oz", "$8,193.43/oz"),     # the review's case
    ("fx_gold_usd_oz", 65536.1015625, "USD/oz", "$65,536.1/oz"),
    ("fx_gold_usd_oz", 123456.78125, "USD/oz", "$123,456.78/oz"),
    ("fx_gold_usd_oz", 1234567.75, "USD/oz", "$1,234,567.8/oz"),
    ("fx_gold_usd_oz", 4380.4, "USD/oz", "$4,380.4/oz"),            # a float64 reading: no float32 path
]


@pytest.mark.parametrize("model_output", [True, False], ids=["model-pass", "final-pass"])
@pytest.mark.parametrize("card_id,observed,unit,published", FLOAT32_FEED)
def test_a_float32_feed_card_prints_the_feeds_own_short_decimal_at_any_size(
    card_id: str, observed: float, unit: str, published: str, model_output: bool,
) -> None:
    card = _brief("fx", "Card", "model text")
    _enforce_observation_contract(card, _raw("fx", "Card", observed, unit, card_id),
                                  model_output=model_output)
    assert card.sections[0].metrics[0].value == published


# The same bits on a card whose feed is NOT float32 are the source's own digits:
# never shortened, even though they happen to be exact float32 values.
# (builder value, builder unit, the text the card must carry)
NOT_A_FLOAT32_FEED = [
    (5540.31982421875, "index", "5,540.31982421875"),
    (65536.1015625, "index", "65,536.1015625"),
    (8193.4296875, "USD/oz", "$8,193.4296875/oz"),
    (123456.78125, "index", "123,456.78125"),
    (2500000.25, "crore BDT", "Tk 2,500,000.25 cr"),
]


@pytest.mark.parametrize("model_output", [True, False], ids=["model-pass", "final-pass"])
@pytest.mark.parametrize("card_id", ["card", "dse_ds30", "fx_usd_bdt_mid"])
@pytest.mark.parametrize("observed,unit,published", NOT_A_FLOAT32_FEED)
def test_a_card_from_any_other_feed_keeps_every_digit_even_if_it_fits_a_float32(
    observed: float, unit: str, published: str, card_id: str, model_output: bool,
) -> None:
    card = _brief("dse", "Card", "model text")
    _enforce_observation_contract(card, _raw("dse", "Card", observed, unit, card_id),
                                  model_output=model_output)
    assert card.sections[0].metrics[0].value == published


@pytest.mark.parametrize("observed", [None, float("nan"), float("inf"), float("-inf")])
def test_an_unknown_observation_prints_the_unavailable_mark_never_the_models_number(observed: Any) -> None:
    card = _brief("iran", "Brent spot", "$80.25")
    _enforce_observation_contract(card, _raw("iran", "Brent spot", observed, "USD/bbl"))
    assert card.sections[0].metrics[0].value == "—"


def test_a_builder_string_value_prints_as_the_builder_gave_it() -> None:
    card = _brief("banking", "NPL Ratio", "36%")
    _enforce_observation_contract(card, _raw("banking", "NPL Ratio", "35.73%", "%"))
    assert card.sections[0].metrics[0].value == "35.73%"


def test_the_label_binds_case_and_space_insensitively_like_reconciliation() -> None:
    card = _brief("dse", "  dsex CLOSE ", "5,999")
    _enforce_observation_contract(card, _raw("dse", "DSEX close", 5540.32037, "index"))
    assert card.sections[0].metrics[0].value == "5,540.32037"


def test_a_card_prints_its_own_sections_observation_not_a_same_label_card_elsewhere() -> None:
    card = _brief("fx", "Gross Reserves", "$99bn")
    raw = _raw("bb", "Gross Reserves", 40.0, "bn USD") + _raw("fx", "Gross Reserves", 37.3523, "bn USD")
    _enforce_observation_contract(card, raw)
    assert card.sections[0].metrics[0].value == "$37.3523bn"


def test_the_stamp_is_stable_across_repeated_passes() -> None:
    card = _brief("dse", "DSEX close", "rose 140")
    raw = _raw("dse", "DSEX close", 5540.32037, "index")
    for model_output in (True, True, False):
        _enforce_observation_contract(card, raw, model_output=model_output)
    assert card.sections[0].metrics[0].value == "5,540.32037"


# ── Headlines count: the number of headlines actually published (inventory §C) ──

@pytest.mark.parametrize("model_text", ["12", "57", "twelve"])
def test_the_headlines_count_card_counts_the_headlines_published_beside_it(model_text: str) -> None:
    """The builder's count is the scraped pool; the card has always meant the curated
    list the reader sees. Code counts that list; neither the pool size nor the model's
    own claim is printed."""
    card = _brief("headlines", "Headlines count", model_text, news=9)
    _enforce_observation_contract(card, _raw("headlines", "Headlines count", 57, "items",
                                             metric_id="headlines_count"))
    assert card.sections[0].metrics[0].value == "9"  # a bare whole number (finding C5)


# ── Summary pills that duplicated a card keep duplicating it (SPA hide rule) ──

@pytest.mark.parametrize("model_text,pill", [
    ("$36.42bn", "$36.42bn"),        # exact duplicate
    ("$36.42bn", "$$36.42BN"),       # SPA collapses $$ and compares case-insensitively
    ("$36.4212bn", "$36.42bn"),      # SPA truncates a 3+ decimal tail before comparing
    ("$36.42bn", "  $36.42bn "),     # SPA trims
])
def test_a_pill_the_spa_hid_as_a_duplicate_of_the_card_stays_hidden(model_text: str, pill: str) -> None:
    """Section.tsx hides a pill whose display text equals a same-section card value.
    Re-printing the card must not turn a hidden duplicate into an extra tile carrying
    the model's number: the duplicate pill takes the card's printed text."""
    card = _brief("fx", "Gross Reserves", model_text, pills=[pill])
    _enforce_observation_contract(card, _raw("fx", "Gross Reserves", 37.3523, "bn USD"))
    section = card.sections[0]
    assert section.metrics[0].value == "$37.3523bn"
    assert section.summary_pills[0].value == "$37.3523bn"


@pytest.mark.parametrize("pill", ["$37.35bn", "36.42", "", "Tk4.15tn"])
def test_a_pill_that_was_its_own_tile_keeps_its_text(pill: str) -> None:
    """Pills have no code source (inventory §B): a pill the SPA showed stays as it was."""
    card = _brief("fx", "Gross Reserves", "$36.42bn", pills=[pill])
    _enforce_observation_contract(card, _raw("fx", "Gross Reserves", 36.42, "bn USD"))
    assert card.sections[0].summary_pills[0].value == pill



def test_an_empty_card_text_never_makes_an_empty_pill_a_duplicate() -> None:
    """Section.tsx: an empty pill value never counts as a duplicate, so it keeps its tile."""
    card = _brief("fx", "Gross Reserves", "", pills=[""])
    _enforce_observation_contract(card, _raw("fx", "Gross Reserves", 36.42, "bn USD"))
    assert card.sections[0].summary_pills[0].value == ""

# ── End to end: every model pass is re-printed before anything reads it ─────

def _dse_sections() -> list[SectionData]:
    return [SectionData(id="dse", title="DSE", freshness="fresh", metrics=[
        Metric(id="dsex", label="DSEX close", value=5540.32037, unit="index",
               as_of=date(2026, 9, 22), source="DSE", cadence="daily"),
        Metric(id="dse_declining", label="Declining", value=227, unit="stocks",
               as_of=date(2026, 9, 22), source="DSE", cadence="daily"),
    ])]


def _model_brief(dsex: str, declining: str) -> dict[str, Any]:
    return {"brief": {"issue_no": 1, "volume": 1, "brief_date": TODAY.isoformat()},
            "sections": [{"slug": "dse", "ord": 6, "title": "DSE", "group_key": "markets",
                          "metrics": [{"label": "DSEX close", "value": dsex},
                                      {"label": "Declining", "value": declining}]}]}


def _run(monkeypatch: pytest.MonkeyPatch, review: dict[str, Any],
         previous: dict[str, Any] | None = None) -> tuple[BriefPayloadV6, dict[str, Any]]:
    """run_publish with fake Editor/Sub-editor; returns (published, sub-editor input)."""
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(pipeline_v6, "_alert", lambda message: None)
    monkeypatch.setattr(pipeline_v6, "fetch_previous_brief", lambda: previous)
    monkeypatch.setattr(pipeline_v6, "fetch_recent_news", lambda **kw: [])
    monkeypatch.setattr(pipeline_v6, "fetch_metric_definitions", list)
    monkeypatch.setattr(pipeline_v6, "_resolve_supabase_config", lambda: None)
    seen: dict[str, Any] = {}

    def fake_call(*, label: str, input_obj: dict[str, Any], **_: Any) -> dict[str, Any]:
        if label == "editor_v6":
            return _model_brief("rose 140", "140 gainers")
        seen.update(input_obj)
        return review

    monkeypatch.setattr(pipeline_v6, "_call_with_retries", fake_call)
    captured: list[BriefPayloadV6] = []
    monkeypatch.setattr(pipeline_v6, "publish_brief",
                        lambda payload, **kw: captured.append(payload) or "local")
    assert pipeline_v6.run_publish(_dse_sections(), TODAY,
                                   expected_identity=PublishIdentity(1, TODAY)) == "local"
    return captured[0], seen


def _values(section: dict[str, Any] | SectionV6) -> list[str]:
    metrics = section["metrics"] if isinstance(section, dict) else section.metrics
    return [m["value"] if isinstance(m, dict) else m.value for m in metrics]


def test_the_subeditor_only_ever_sees_code_printed_card_numbers(monkeypatch) -> None:
    published, subeditor_input = _run(monkeypatch, {"verdict": "pass", "issues": []})
    assert _values(subeditor_input["editor_output"]["sections"][0]) == ["5,540.32037", "227"]
    assert _values(published.sections[0]) == ["5,540.32037", "227"]


def test_a_number_the_subeditor_rewrites_never_publishes_or_moves_the_changed_dot(monkeypatch) -> None:
    """The revised brief is re-printed BEFORE stamp_changed compares with yesterday, so a
    model rewrite of an unchanged reading neither publishes nor lights the changed dot."""
    revised = _model_brief("9,999", "▼36.42")
    previous = {"sections": [{"slug": "dse", "metrics": [
        {"label": "DSEX close", "value": "5,540.32037"}, {"label": "Declining", "value": "227"}]}]}
    published, _ = _run(monkeypatch, {"verdict": "revise", "issues": [
        {"section": "dse", "field": "metrics", "severity": "warn", "problem": "reformatted the tiles"}],
        "revised_brief": revised}, previous=previous)
    cards = published.sections[0].metrics
    assert [m.value for m in cards] == ["5,540.32037", "227"]
    assert [m.changed for m in cards] == [False, False]


# ── The stamp → screen contract (R2 fix 7b3) ──────────────────────────────────
# tests/fixtures/card_display_contract.json is read by BOTH runtimes: this test pins
# builder value → the string Python stamps; lib/format.test.ts pins that same string
# → what cleanMetricValue shows the reader. A change on either side breaks one of them.
_DISPLAY_CONTRACT = json.loads(
    (Path(__file__).parent / "fixtures" / "card_display_contract.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("model_output", [True, False], ids=["model-pass", "final-pass"])
@pytest.mark.parametrize("row", _DISPLAY_CONTRACT["rows"], ids=lambda row: row["stamped"])
def test_the_card_text_the_spa_contract_expects_is_what_the_stamp_prints(
    row: dict[str, Any], model_output: bool,
) -> None:
    card = _brief("fx", "Card", "model text")
    _enforce_observation_contract(card, _raw("fx", "Card", row["value"], row["unit"], row["card_id"]),
                                  model_output=model_output)
    assert card.sections[0].metrics[0].value == row["stamped"]
