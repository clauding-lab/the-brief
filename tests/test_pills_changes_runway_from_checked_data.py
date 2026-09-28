"""Pills, snapshot-strip change figures and the banker-box runway come from checked data (R2 fix 16).

Owner decisions (h) and (i), 27 Sep 2026 (builds on fix 7b's card-value stamp):
(h) A summary pill whose key names the same concept as a card of its OWN section (an
    explicit per-concept binding table, never fuzzy text matching) prints that card's
    code-printed number, so pill and card always agree and Section.tsx merges them
    (spec §7.1). News-fact pills and pills without a bound card keep the model's text.
(i) A card's `delta`/`delta_pct` (the snapshot strip's change line) is computed by code
    from the builder's own dated history — the previous observation of a different period
    before the card's `as_of`, in a history that carries the card's own reading at that
    date — and is cleared whenever no such history exists. The banker-box `runway`
    survives only when its number and unit equal, in the house format, a checked builder
    figure in the brief; otherwise it is cleared.
Every rule runs on every model pass: after the Editor (what the Sub-editor reads), after
the Sub-editor's revision, and on the final object.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from brief import pipeline_v6
from brief.history import MetricHistoryClient
from brief.pipeline import _enrich_metric_history
from brief.publication_identity import PublishIdentity
from brief.schema import Metric, SectionData
from brief.v6_schema import BriefPayloadV6

TODAY = date(2026, 9, 25)
_V5_ID = {"iran": "iranwar"}
_MODEL_DELTA, _MODEL_PCT = "+999", "+50%"


def _metric(metric_id: str, label: str, value: Any, unit: str, *, as_of: date = date(2026, 9, 22),
            cadence: str = "daily", points: list[tuple[date, float]] | None = None,
            source: str = "BB") -> Metric:
    extra = {} if points is None else {"history_points": [{"as_of": d, "value": v} for d, v in points]}
    return Metric(id=metric_id, label=label, value=value, unit=unit, as_of=as_of, source=source,
                  cadence=cadence, **extra)


def _builder(slug: str, *metrics: Metric) -> SectionData:
    return SectionData(id=_V5_ID.get(slug, slug), title=slug.upper(), freshness="fresh",
                       metrics=list(metrics))


def _section(slug: str, cards: list[dict[str, Any]], *, pills: list[tuple[str, str]] = (),
             runway: dict[str, str] | None = None, news: int = 0) -> dict[str, Any]:
    _, ord_, group = pipeline_v6.V5_TO_V6[_V5_ID.get(slug, slug)]
    section: dict[str, Any] = {
        "slug": slug, "ord": ord_, "title": slug.upper(), "group_key": group, "metrics": cards,
        "summary_pills": [{"key": k, "value": v} for k, v in pills],
        "news": [{"headline": f"headline {i}"} for i in range(news)]}
    if runway is not None:
        section["banker_read"] = {"verdict": "The desk reads this as a steady week.", "runway": runway}
    return section


def _card(label: str, value: str = "model text", delta: str | None = _MODEL_DELTA,
          delta_pct: str | None = _MODEL_PCT) -> dict[str, Any]:
    return {"label": label, "value": value, "delta": delta, "delta_pct": delta_pct}


def _model(*sections: dict[str, Any]) -> dict[str, Any]:
    return {"brief": {"issue_no": 1, "volume": 1, "brief_date": TODAY.isoformat()},
            "sections": list(sections)}


def _publish(monkeypatch: pytest.MonkeyPatch, builders: list[SectionData], editor: dict[str, Any],
             revised: dict[str, Any] | None = None) -> tuple[BriefPayloadV6, dict[str, Any]]:
    """run_publish with a fake Editor and Sub-editor (revise when `revised` is given);
    returns (published object, the Sub-editor's input). No network, no model."""
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(pipeline_v6, "_alert", lambda message: None)
    monkeypatch.setattr(pipeline_v6, "fetch_previous_brief", lambda: None)
    monkeypatch.setattr(pipeline_v6, "fetch_recent_news", lambda **kw: [])
    monkeypatch.setattr(pipeline_v6, "fetch_metric_definitions", list)
    monkeypatch.setattr(pipeline_v6, "_resolve_supabase_config", lambda: None)
    review = ({"verdict": "pass", "issues": []} if revised is None else
              {"verdict": "revise", "revised_brief": revised, "issues": [
                  {"section": None, "field": "cards", "severity": "warn", "problem": "rewrote the figures"}]})
    seen: dict[str, Any] = {}

    def fake_call(*, label: str, input_obj: dict[str, Any], **_: Any) -> dict[str, Any]:
        if label == "editor_v6":
            return editor
        seen.update(json.loads(json.dumps(input_obj, default=str)))
        return review

    monkeypatch.setattr(pipeline_v6, "_call_with_retries", fake_call)
    captured: list[BriefPayloadV6] = []
    monkeypatch.setattr(pipeline_v6, "publish_brief",
                        lambda payload, **kw: captured.append(payload) or "local")
    assert pipeline_v6.run_publish(builders, TODAY,
                                   expected_identity=PublishIdentity(1, TODAY)) == "local"
    return captured[0], seen


def _published_section(published: BriefPayloadV6, slug: str):
    return next(s for s in published.sections if s.slug == slug)


def _reviewed_section(subeditor_input: dict[str, Any], slug: str) -> dict[str, Any]:
    return next(s for s in subeditor_input["editor_output"]["sections"] if s["slug"] == slug)


# ── (h) Pills that restate a card of their own section ───────────────────────
# (section, builder card, the pill key the model wrote, the model's pill text, what publishes)
BOUND_PILLS = [
    ("bb", ("bb_policy_rate", "Policy Rate", 9.5, "%"), "POLICY RATE", "10%", "9.5%"),
    ("bb", ("bb_call_money", "Overnight Call Money", 8.79, "%"), "CALL MONEY", "8.8%", "8.79%"),
    ("bb", ("bb_gross_reserves", "Gross Reserves", 37.3523, "bn USD"), "RESERVES", "$37.4bn", "$37.3523bn"),
    ("banking", ("banking_npl_pct", "NPL Ratio", 32.78, "%"), "NPL RATIO", "33%", "32.78%"),
    ("banking", ("banking_car_pct", "CAR", 1.56, "%"), "CAR", "1.6%", "1.56%"),
    ("fx", ("fx_usd_bdt_mid", "USD/BDT mid", 123.22, "BDT"), "USD/BDT", "123.5", "123.22"),
    ("fx", ("fx_gross_reserves", "Gross Reserves", 37.3523, "bn USD"), "RESERVES", "$37.35bn", "$37.3523bn"),
    ("fx", ("fx_gold_usd_oz", "Gold", 4328.89990234375, "USD/oz"), "GOLD", "$4,329/oz", "$4,328.9/oz"),
    ("dse", ("dsex", "DSEX close", 5540.32037, "index"), "DSEX", "5,540", "5,540.32037"),
    ("dse", ("dse_turnover_crore", "Turnover", 791.4875, "crore BDT"), "TURNOVER", "Tk791cr", "Tk 791.4875 cr"),
    ("tbond", ("tbond_tbill_91d", "91d T-Bill cut-off", 8.3198, "%"), "91D TBILL", "8.32%", "8.3198%"),
    ("tbond", ("tbond_tbill_364d", "364d T-Bill cut-off", 8.47, "%"), "364D TBILL", "8.5%", "8.47%"),
    ("tbond", ("tbond_bond_10y", "10y Govt Bond", 8.54, "%"), "10Y BOND", "8.6%", "8.54%"),
    ("fiscal", ("fiscal_nbr_collected_trn", "NBR collected YTD", 4.15, "BDT trn"), "NBR YTD", "Tk4.2tn", "Tk 4.15tn"),
    ("fiscal", ("fiscal_govt_borrow_trn", "Govt bank borrow YTD", 0.94, "BDT trn"), "GOVT BORROW", "Tk1tn", "Tk 0.94tn"),
    ("macro", ("cpi_12m_avg_monthly", "CPI 12m Avg", 8.66, "%"), "CPI 12M AVG", "8.7%", "8.66%"),
    ("macro", ("m2_growth_yoy_monthly", "M2 YoY", 11.76, "%"), "M2 YoY", "12%", "11.76%"),
    ("macro", ("real_policy_rate_monthly", "Real Policy Rate", 1.2400000000000002, "%"), "REAL POLICY",
     "+1.24%", "1.24%"),
    ("iran", ("iranwar_brent_spot", "Brent spot", 98.31999969482422, "USD/bbl"), "BRENT", "$99", "$98.32"),
    ("iran", ("iranwar_wti_spot", "WTI spot", 92.25, "USD/bbl"), "WTI", "$92", "$92.25"),
    ("remit", ("remit_monthly_mn", "Monthly Remittance", 2858.68, "mn USD"), "REMITTANCE", "$2.97bn", "$2,858.68mn"),
]


def _bound_pill_case(slug: str, card: tuple[str, str, Any, str]) -> tuple[list[SectionData], list[dict]]:
    metric_id, label, value, unit = card
    return [_builder(slug, _metric(metric_id, label, value, unit))], [_card(label)]


@pytest.mark.parametrize("revise", [False, True], ids=["editor-pass", "subeditor-revision"])
@pytest.mark.parametrize("slug,card,key,model_text,printed", BOUND_PILLS,
                         ids=[f"{r[0]}-{r[2]}" for r in BOUND_PILLS])
def test_a_pill_restating_a_card_of_its_section_prints_that_cards_checked_number(
    monkeypatch, slug: str, card: tuple, key: str, model_text: str, printed: str, revise: bool,
) -> None:
    builders, cards = _bound_pill_case(slug, card)
    editor = _model(_section(slug, cards, pills=[(key, model_text)]))
    revised = _model(_section(slug, cards, pills=[(key, "999 rewritten")])) if revise else None
    published, reviewed = _publish(monkeypatch, builders, editor, revised)
    if not revise:
        assert reviewed and _reviewed_section(reviewed, slug)["summary_pills"][0]["value"] == printed
    section = _published_section(published, slug)
    assert section.summary_pills[0].value == printed
    # The pill and its card show one figure, so Section.tsx merges them (spec §7.1).
    assert pipeline_v6._spa_display_key(section.summary_pills[0].value) == \
        pipeline_v6._spa_display_key(section.metrics[0].value)


def test_the_headlines_pill_counts_the_headlines_published_like_its_card(monkeypatch) -> None:
    builders = [_builder("headlines", _metric("headlines_count", "Headlines count", 57, "items"))]
    editor = _model(_section("headlines", [_card("Headlines count", "12")],
                             pills=[("HEADLINES", "12 items")], news=9))
    section = _published_section(_publish(monkeypatch, builders, editor)[0], "headlines")
    assert (section.metrics[0].value, section.summary_pills[0].value) == ("9", "9")


def test_a_bound_pill_key_matches_whatever_its_case_or_surrounding_space(monkeypatch) -> None:
    builders, cards = _bound_pill_case("bb", ("bb_policy_rate", "Policy Rate", 9.5, "%"))
    editor = _model(_section("bb", cards, pills=[("  Policy rate ", "10%")]))
    assert _published_section(_publish(monkeypatch, builders, editor)[0], "bb").summary_pills[0].value == "9.5%"


# (section, a card that section builds, pill key, model text) — news facts, period-qualified,
# composite, ambiguous or other-section figures: no bound card, so the model's text stays.
UNBOUND_PILLS = [
    ("headlines", ("headlines_count", "Headlines count", 57, "items"), "DIGITAL BANKS", "5 approved"),
    ("headlines", ("headlines_count", "Headlines count", 57, "items"), "NBFI REFUND", "Tk50 lakh"),
    ("headlines", ("headlines_count", "Headlines count", 57, "items"), "BRENT", "$94.09"),
    ("banking", ("banking_npl_pct", "NPL Ratio", 32.78, "%"), "DOMMR", "8.84%"),
    ("banking", ("banking_npl_pct", "NPL Ratio", 32.78, "%"), "NPL · Q1", "32.26%"),
    ("banking", ("banking_car_pct", "CAR", 1.56, "%"), "CAR · Q3", "1.6%"),
    ("dse", ("dse_advancing", "Advancing", 103, "stocks"), "BREADTH", "103/227"),
    ("iran", ("iranwar_brent_spot", "Brent spot", 98.32, "USD/bbl"), "OFF Q3 HIGH", "$108.35"),
    ("iran", ("iranwar_brent_spot", "Brent spot", 98.32, "USD/bbl"), "SPREAD", "~$7"),
    ("remit", ("remit_monthly_mn", "Monthly Remittance", 2858.68, "mn USD"), "YoY (JUL)", "+18%"),
    ("remit", ("remit_monthly_mn", "Monthly Remittance", 2858.68, "mn USD"), "REMIT · JUL", "$2.82bn"),
    ("macro", ("cpi_12m_avg_monthly", "CPI 12m Avg", 8.66, "%"), "CPI 12M", "8.68%"),
    ("macro", ("real_policy_rate_monthly", "Real Policy Rate", 1.24, "%"), "REAL RATE", "0.84%"),
    ("macro", ("private_credit_growth_yoy_monthly", "Private Credit YoY", 4.98, "%"), "PVT CREDIT", "5%"),
    ("tbond", ("tbond_bond_10y", "10y Govt Bond", 8.54, "%"), "5S10S", "~8bp"),
]


@pytest.mark.parametrize("revise", [False, True], ids=["editor-pass", "subeditor-revision"])
@pytest.mark.parametrize("slug,card,key,model_text", UNBOUND_PILLS, ids=[f"{r[0]}-{r[2]}" for r in UNBOUND_PILLS])
def test_a_pill_with_no_bound_card_keeps_the_models_text(
    monkeypatch, slug: str, card: tuple, key: str, model_text: str, revise: bool,
) -> None:
    builders, cards = _bound_pill_case(slug, card)
    editor = _model(_section(slug, cards, pills=[(key, model_text)]))
    revised = editor if revise else None
    published, _ = _publish(monkeypatch, builders, editor, revised)
    assert _published_section(published, slug).summary_pills[0].value == model_text


def test_a_bound_pill_whose_card_was_not_built_today_never_prints_the_models_number(monkeypatch) -> None:
    """The bb builder produced no reserves observation today: the RESERVES pill has no checked
    figure behind it, so it is removed rather than printed from the model."""
    builders = [_builder("bb", _metric("bb_policy_rate", "Policy Rate", 9.5, "%"))]
    editor = _model(_section("bb", [_card("Policy Rate")],
                             pills=[("RESERVES", "$37.35bn"), ("POLICY RATE", "10%"), ("OUTLOOK", "Hold")]))
    pills = _published_section(_publish(monkeypatch, builders, editor)[0], "bb").summary_pills
    assert [(p.key, p.value) for p in pills] == [("POLICY RATE", "9.5%"), ("OUTLOOK", "Hold")]


_UNBUILT_FISCAL_PILLS = [("NBR YTD", "Tk 9.99tn"), ("GOVT BORROW", "Tk 5tn"), ("OUTLOOK", "Tight")]


@pytest.mark.parametrize("revise", [False, True], ids=["editor-pass", "subeditor-revision"])
def test_a_bound_pill_in_a_section_not_built_today_never_prints_the_models_number(
    monkeypatch, revise: bool,
) -> None:
    """fix 16 round 1 (review MEDIUM): the builders produced no fiscal section today, so NBR YTD
    and GOVT BORROW (both bound to fiscal cards) have no checked figure behind them: removed,
    exactly as for a missing card in a built section. The unbound OUTLOOK pill keeps its text."""
    builders = [_builder("dse", _metric("dsex", "DSEX close", 5540.32037, "index"))]
    editor = _model(_section("dse", [_card("DSEX close")]),
                    _section("fiscal", [_card("NBR collected YTD", "Tk 4.15tn")],
                             pills=[] if revise else _UNBUILT_FISCAL_PILLS))
    revised = _model(_section("dse", [_card("DSEX close")]),
                     _section("fiscal", [_card("NBR collected YTD", "Tk 4.15tn")], pills=_UNBUILT_FISCAL_PILLS))
    published, reviewed = _publish(monkeypatch, builders, editor, revised if revise else None)
    if not revise:
        pills = _reviewed_section(reviewed, "fiscal")["summary_pills"]
        assert [(p["key"], p["value"]) for p in pills] == [("OUTLOOK", "Tight")]
    pills = _published_section(published, "fiscal").summary_pills
    assert [(p.key, p.value) for p in pills] == [("OUTLOOK", "Tight")]


def test_the_final_pass_removes_bound_pills_of_a_section_not_built_today() -> None:
    builder = _builder("dse", _metric("dsex", "DSEX close", 5540.32037, "index"))
    brief = BriefPayloadV6.model_validate(_model(
        _section("dse", [_card("DSEX close")]),
        _section("fiscal", [_card("NBR collected YTD", "Tk 4.15tn")], pills=_UNBUILT_FISCAL_PILLS)))
    pipeline_v6._enforce_observation_contract(brief, pipeline_v6._to_v6_raw([builder]), card_changes={})
    fiscal = next(s for s in brief.sections if s.slug == "fiscal")
    assert [(p.key, p.value) for p in fiscal.summary_pills] == [("OUTLOOK", "Tight")]


def test_every_bound_card_is_one_its_own_sections_builder_emits() -> None:
    """A binding to an id the section's builder never emits would silently never bind."""
    builders_dir = Path(pipeline_v6.__file__).parent / "builders"
    v5_by_slug = {slug: v5 for v5, (slug, _o, _g) in pipeline_v6.V5_TO_V6.items()}
    bindings = pipeline_v6._PILL_CARD_BINDINGS
    assert bindings, "the binding table is empty"
    for (slug, key), metric_id in bindings.items():
        assert key == pipeline_v6._normalize_label(key), f"key {key!r} is not normalised"
        source = (builders_dir / f"{v5_by_slug[slug]}.py").read_text(encoding="utf-8")
        assert f'"{metric_id}"' in source, f"{slug}/{key}: {metric_id} is not built by {v5_by_slug[slug]}.py"


# ── (i) Change figures: computed from the builder's own dated history, or cleared ──
D = date  # brevity in the tables below
SEP21, SEP22 = D(2026, 9, 21), D(2026, 9, 22)
# (section, builder card incl. its dated history points, published delta, published delta_pct)
CHANGES = [
    pytest.param("dse", _metric("dsex", "DSEX close", 5540.32037, "index", points=[
        (D(2026, 9, 18), 5532.14854), (SEP21, 5550.49562), (SEP22, 5540.32037)]),
        "−10.17525", "−0.183321467065674%", id="index-level-falls"),
    pytest.param("tbond", _metric("tbond_tbill_91d", "91d T-Bill cut-off", 8.3198, "%", as_of=SEP21,
                                  cadence="event", points=[(D(2026, 9, 14), 8.3374), (SEP21, 8.3198)]),
        "−0.0176pp", None, id="percent-metric-moves-in-points-never-percent-of-percent"),
    pytest.param("fx", _metric("fx_gold_usd_oz", "Gold", 4328.89990234375, "USD/oz", as_of=D(2026, 9, 23),
                               points=[(SEP22, 4300.10009765625), (D(2026, 9, 23), 4328.89990234375)]),
        "+$28.8/oz", "+0.669751866235669%", id="float32-feed-uses-the-feeds-own-decimals"),
    pytest.param("fx", _metric("fx_gross_reserves", "Gross Reserves", 37.3523, "bn USD", as_of=D(2026, 8, 31),
                               cadence="monthly", points=[(D(2026, 7, 31), 36.42), (D(2026, 8, 31), 37.3523)]),
        "+$0.9323bn", "+2.55985722130697%", id="monthly-previous-month"),
    pytest.param("bb", _metric("bb_call_money", "Overnight Call Money", 8.79, "%", points=[
        (SEP21, 8.79), (SEP22, 8.79)]), "0pp", None, id="unchanged-reading-prints-zero"),
    pytest.param("dse", _metric("dse_advancing", "Advancing", 103, "stocks", points=[
        (SEP21, 140), (SEP22, 103)]), "−37", None, id="count-has-no-percent-change"),
    pytest.param("fx", _metric("fx_trade_gap", "Trade Gap", -3.31, "bn USD", as_of=D(2026, 6, 1), cadence="monthly",
                               points=[(D(2026, 5, 1), -1.77), (D(2026, 6, 1), -3.31)]),
        "−$1.54bn", None, id="no-percent-change-from-a-negative-level"),
    pytest.param("fx", _metric("fx_trade_gap", "Trade Gap", -0.5, "bn USD", as_of=D(2026, 6, 1), cadence="monthly",
                               points=[(D(2026, 5, 1), 1.0), (D(2026, 6, 1), -0.5)]),
        "−$1.5bn", None, id="no-percent-change-when-a-level-turns-negative"),
    pytest.param("macro", _metric("import_cover_months_monthly", "Import Cover", 4.97, "months", as_of=D(2026, 6, 1),
                                  cadence="monthly", points=[(D(2026, 5, 1), 4.87), (D(2026, 6, 1), 4.97)]),
        "+0.1 months", None, id="ratio-in-months-has-no-percent-change"),
    pytest.param("dse", _metric("dsex", "DSEX close", 5540.32037, "index", points=[
        (SEP21, 5550.49562), (SEP22, 5540.32037), (D(2026, 9, 23), 5600.0)]),
        "−10.17525", "−0.183321467065674%", id="a-later-reading-is-never-the-previous-one"),
    # ── cleared: no honest previous observation ──
    # fix 16b (review MEDIUM): Bangladesh holds real Saturday make-up sessions (DSE 23 May 2026),
    # so Thursday is not provably the session before a Sunday. Without the source's own change
    # for the session (see SOURCE_ARBITER_CHANGES) a weekend gap is hidden, never bridged. Real
    # rows; round 1 showed "−96.61455" here, which DSE's own 13 Sep change confirms only when
    # that figure is at hand — the confirmed case lives in SOURCE_ARBITER_CHANGES.
    pytest.param("dse", _metric("dsex", "DSEX close", 5418.55361, "index", as_of=D(2026, 9, 13), points=[
        (D(2026, 9, 8), 5539.32016), (D(2026, 9, 10), 5515.16816), (D(2026, 9, 13), 5418.55361)]),
        None, None, id="a-weekend-gap-is-not-provably-one-session-without-the-sources-change"),
    pytest.param("bb", _metric("bb_call_money", "Overnight Call Money", 8.79, "%", as_of=D(2026, 9, 13), points=[
        (D(2026, 9, 10), 8.75), (D(2026, 9, 13), 8.79)]),
        None, None, id="a-bd-daily-card-across-a-weekend-is-hidden-a-saturday-may-have-been-a-session"),
    # fix 16 round 1 (review HIGH): history lacks the 9 Sep session (DSE's own 10 Sep change,
    # −22.70854, implies a 9 Sep close of 5537.8767). A two-session move is not the day's change.
    pytest.param("dse", _metric("dsex", "DSEX close", 5515.16816, "index", as_of=D(2026, 9, 10), points=[
        (D(2026, 9, 7), 5567.42309), (D(2026, 9, 8), 5539.32016), (D(2026, 9, 10), 5515.16816)]),
        None, None, id="a-missing-session-is-never-bridged"),
    pytest.param("tbond", _metric("tbond_tbill_91d", "91d T-Bill cut-off", 8.3198, "%", as_of=SEP21,
                                  cadence="event", points=[(D(2026, 9, 7), 8.5899), (SEP21, 8.3198)]),
                 None, None, id="a-missing-weekly-auction-is-never-bridged"),
    pytest.param("fx", _metric("fx_gross_reserves", "Gross Reserves", 37.3523, "bn USD", as_of=D(2026, 8, 31),
                               cadence="monthly", points=[(D(2026, 6, 30), 36.1), (D(2026, 8, 31), 37.3523)]),
                 None, None, id="a-missing-month-is-never-bridged"),
    # fix 16 round 1 (review MEDIUM): a monthly figure restamped daily across a month boundary is
    # the same release twice, never "unchanged on the previous month" (real NBR rows, Aug→Sep).
    pytest.param("fiscal", _metric("fiscal_nbr_collected_trn", "NBR collected YTD", 3.61, "BDT trn",
                                   as_of=D(2026, 9, 2), cadence="monthly",
                                   points=[(D(2026, 8, d), 3.61) for d in range(19, 30)] + [(D(2026, 9, 2), 3.61)]),
                 None, None, id="restamps-across-a-month-boundary-are-not-a-previous-month"),
    pytest.param("fiscal", _metric("fiscal_nbr_collected_trn", "NBR collected YTD", 4.15, "BDT trn",
                                   as_of=D(2026, 10, 1), cadence="monthly",
                                   points=[(D(2026, 9, d), 4.15) for d in range(17, 31)] + [(D(2026, 10, 1), 4.15)]),
                 None, None, id="a-restamp-only-window-across-1-oct-gives-no-change"),
    pytest.param("fx", _metric("fx_gross_reserves", "Gross Reserves", 37.3523, "bn USD", as_of=D(2026, 9, 1),
                               cadence="monthly", points=[(D(2026, 8, 30), 36.42), (D(2026, 8, 31), 36.42),
                                                          (D(2026, 9, 1), 37.3523)]),
                 None, None, id="a-previous-month-read-more-than-once-is-a-restamp-not-a-release"),
    pytest.param("fiscal", _metric("fiscal_nbr_collected_trn", "NBR collected YTD", 3.61, "BDT trn",
                                   as_of=D(2026, 9, 14), cadence="monthly",
                                   points=[(D(2026, 8, 31), 3.61)] + [(D(2026, 9, d), 3.61) for d in range(1, 15)]),
                 None, None, id="a-current-month-read-more-than-once-is-a-restamp-not-a-release"),
    pytest.param("fiscal", _metric("fiscal_nbr_collected_trn", "NBR collected YTD", 3.61, "BDT trn",
                                   as_of=D(2026, 9, 1), cadence="monthly",
                                   points=[(D(2026, 8, 31), 3.61)] + [(D(2026, 9, d), 3.61) for d in range(1, 6)]),
                 None, None, id="a-card-month-restamped-after-its-date-is-not-a-release"),
    pytest.param("dse", _metric("dsex", "DSEX close", 5540.32037, "index"), None, None, id="no-history"),
    pytest.param("dse", _metric("dsex", "DSEX close", 5540.32037, "index", points=[(SEP22, 5540.32037)]),
                 None, None, id="history-holds-only-the-current-reading"),
    pytest.param("remit", _metric("remit_monthly_mn", "Monthly Remittance", 2858.68, "mn USD", as_of=D(2026, 7, 1),
                                  cadence="monthly", points=[(D(2026, 6, 1), 2500.0), (D(2026, 7, 1), 2970.0)]),
                 None, None, id="history-does-not-carry-this-cards-reading"),
    pytest.param("dse", _metric("dsex", "DSEX close", 5540.32037, "index", points=[
        (D(2026, 9, 18), 5532.14854), (SEP21, 5540.32037)]), None, None,
        id="history-reading-sits-on-another-date-than-the-card"),
    pytest.param("fiscal", _metric("fiscal_nbr_collected_trn", "NBR collected YTD", 4.15, "BDT trn",
                                   as_of=D(2026, 9, 24), cadence="monthly",
                                   points=[(D(2026, 9, d), 4.15) for d in range(11, 25)]),
                 None, None, id="same-month-restamps-are-not-a-previous-observation"),
    pytest.param("dse", _metric("dsex", "DSEX close", 5540.32037, "index", points=[
        (SEP21, 5550.49562), (SEP21, 5549.0), (SEP22, 5540.32037)]), None, None,
        id="two-different-readings-on-the-previous-date"),
    pytest.param("dse", _metric("dsex", "DSEX close", None, "index", points=[(SEP21, 5550.49562)]),
                 None, None, id="no-current-number"),
    pytest.param("headlines", _metric("headlines_count", "Headlines count", 57, "items", points=[
        (D(2026, 9, 24), 40), (D(2026, 9, 25), 57)], as_of=D(2026, 9, 25)),
        None, None, id="headlines-card-prints-a-count-of-the-page-not-the-builder-value"),
]


@pytest.mark.parametrize("revise", [False, True], ids=["editor-pass", "subeditor-revision"])
@pytest.mark.parametrize("slug,metric,delta,delta_pct", CHANGES)
def test_a_cards_change_figures_are_computed_from_its_own_history_or_cleared(
    monkeypatch, slug: str, metric: Metric, delta: str | None, delta_pct: str | None, revise: bool,
) -> None:
    builders = [_builder(slug, metric)]
    editor = _model(_section(slug, [_card(metric.label)]))
    revised = _model(_section(slug, [_card(metric.label, delta="−1", delta_pct="−1%")])) if revise else None
    published, reviewed = _publish(monkeypatch, builders, editor, revised)
    if not revise:
        card = _reviewed_section(reviewed, slug)["metrics"][0]
        assert (card["delta"], card["delta_pct"]) == (delta, delta_pct)
    card = _published_section(published, slug).metrics[0]
    assert (card.delta, card.delta_pct) == (delta, delta_pct)


def test_a_card_in_a_section_not_built_today_carries_no_change_figures(monkeypatch) -> None:
    """A known section the builders did not produce keeps the model's cards (reconciliation),
    but no checked history stands behind any change figure on them."""
    builders = [_builder("dse", _metric("dsex", "DSEX close", 5540.32037, "index"))]
    editor = _model(_section("dse", [_card("DSEX close")]),
                    _section("fiscal", [_card("NBR collected YTD", "Tk 4.15tn")]))
    card = _published_section(_publish(monkeypatch, builders, editor)[0], "fiscal").metrics[0]
    assert (card.delta, card.delta_pct) == (None, None)


def test_the_final_pass_recomputes_change_figures_whatever_the_object_carries() -> None:
    builder = _builder("dse", _metric("dsex", "DSEX close", 5540.32037, "index",
                                      points=[(SEP21, 5550.49562), (SEP22, 5540.32037)]))
    brief = BriefPayloadV6.model_validate(_model(_section("dse", [_card("DSEX close")])))
    pipeline_v6._enforce_observation_contract(brief, pipeline_v6._to_v6_raw([builder]),
                                              card_changes=pipeline_v6._card_changes([builder]))
    card = brief.sections[0].metrics[0]
    assert (card.delta, card.delta_pct) == ("−10.17525", "−0.183321467065674%")
    pipeline_v6._enforce_observation_contract(brief, pipeline_v6._to_v6_raw([builder]))
    assert (card.delta, card.delta_pct) == (None, None)  # no checked history handed in: cleared


# ── fix 16b: the source's own day change is the arbiter of "the previous session" ──
# DSE publishes its own DSEX percent change for each session (the "DSEX %Δ" card, dse.py
# `dsex_change_pct`). When that figure for the SAME session is at hand, a computed change is
# shown only when it agrees with it within the source's own rounding (half a unit of its last
# decimal) — whatever the calendar gap. So a missing Saturday make-up session, a holiday or a
# restamped copy can never pass as the previous session. All closes and DSE figures below are
# real rows (R1 repaired snapshot); expected strings worked out separately with Decimal.
MAY21, MAY23, MAY24, MAY25 = D(2026, 5, 21), D(2026, 5, 23), D(2026, 5, 24), D(2026, 5, 25)
_MAY_WEEK = [(D(2026, 5, 19), 5211.54156), (D(2026, 5, 20), 5222.38191), (MAY21, 5264.12281)]
_SEP_WEEK = [(D(2026, 9, 8), 5539.32016), (D(2026, 9, 10), 5515.16816), (D(2026, 9, 13), 5418.55361)]
# (dsex card, DSE's own change pct card for a session or None, published delta, delta_pct)
SOURCE_ARBITER_CHANGES = [
    # the reviewer's probe: Sat 23 May 2026 was a real session and its row is missing
    pytest.param(_metric("dsex", "DSEX close", 5335.86964, "index", as_of=MAY24,
                         points=[*_MAY_WEEK, (MAY24, 5335.86964)]),
                 (MAY24, 0.14094), None, None, id="a-missing-saturday-session-disagrees-with-the-sources-change"),
    pytest.param(_metric("dsex", "DSEX close", 5335.86964, "index", as_of=MAY24,
                         points=[*_MAY_WEEK, (MAY24, 5335.86964)]),
                 None, None, None, id="a-missing-saturday-session-without-the-sources-change-is-hidden"),
    pytest.param(_metric("dsex", "DSEX close", 5335.86964, "index", as_of=MAY24,
                         points=[*_MAY_WEEK, (MAY23, 5328.35993), (MAY24, 5335.86964)]),
                 (MAY24, 0.14094), "+7.50971", "+0.140938489491268%",
                 id="the-day-after-a-saturday-session-is-measured-from-it"),
    pytest.param(_metric("dsex", "DSEX close", 5328.35993, "index", as_of=MAY23,
                         points=[*_MAY_WEEK, (MAY23, 5328.35993)]),
                 (MAY23, 1.22028), "+64.23712", "+1.22028156102232%",
                 id="a-saturday-session-confirmed-by-the-source-is-shown"),
    pytest.param(_metric("dsex", "DSEX close", 5328.35993, "index", as_of=MAY23,
                         points=[*_MAY_WEEK, (MAY23, 5328.35993)]),
                 None, None, None, id="a-saturday-session-without-the-sources-change-is-hidden"),
    pytest.param(_metric("dsex", "DSEX close", 5418.55361, "index", as_of=D(2026, 9, 13), points=_SEP_WEEK),
                 (D(2026, 9, 13), -1.7518), "−96.61455", "−1.75179699325795%",
                 id="a-weekend-gap-the-sources-change-confirms-is-shown"),
    # the 25 May row is a restamped copy of the 24 May close (landmine 24 class): not a session
    pytest.param(_metric("dsex", "DSEX close", 5335.86964, "index", as_of=MAY25,
                         points=[*_MAY_WEEK, (MAY23, 5328.35993), (MAY24, 5335.86964), (MAY25, 5335.86964)]),
                 (MAY25, 0.14094), None, None, id="a-restamped-copy-the-day-before-disagrees-with-the-sources-change"),
    pytest.param(_metric("dsex", "DSEX close", 5515.16816, "index", as_of=D(2026, 9, 10), points=_SEP_WEEK[:2]),
                 (D(2026, 9, 10), -0.41006), None, None, id="a-missing-weekday-session-disagrees-with-the-sources-change"),
    pytest.param(_metric("dsex", "DSEX close", 5418.55361, "index", as_of=D(2026, 9, 13), points=_SEP_WEEK),
                 (D(2026, 9, 13), -1.75171), None, None,
                 id="a-sources-change-differing-past-its-own-rounding-hides-the-change"),
    # hypothetical coarse source figure (1 decimal): its rounding (±0.05) would admit the bridged
    # +1.36294% two-session move; a difference the screen's 2-decimal cut shows is never admitted
    pytest.param(_metric("dsex", "DSEX close", 5335.86964, "index", as_of=MAY24,
                         points=[*_MAY_WEEK, (MAY24, 5335.86964)]),
                 (MAY24, 1.4), None, None, id="a-coarse-source-change-never-vouches-for-a-gap-visible-on-screen"),
    pytest.param(_metric("dsex", "DSEX close", 5418.55361, "index", as_of=D(2026, 9, 13), points=_SEP_WEEK),
                 (D(2026, 9, 10), -1.7518), None, None, id="the-sources-change-for-another-session-confirms-nothing"),
    pytest.param(_metric("dsex", "DSEX close", 5540.32037, "index", points=[
        (D(2026, 9, 18), 5532.14854), (SEP21, 5550.49562), (SEP22, 5540.32037)]),
                 (SEP22, -0.18332), "−10.17525", "−0.183321467065674%",
                 id="consecutive-sessions-the-source-agrees-with-are-shown"),
]


def _dse_builders(metric: Metric, source: tuple[date, float] | None) -> list[SectionData]:
    cards = [metric] if source is None else [
        metric, _metric("dse_dsex_change_pct", "DSEX %Δ", source[1], "%", as_of=source[0])]
    return [_builder("dse", *cards)]


@pytest.mark.parametrize("revise", [False, True], ids=["editor-pass", "subeditor-revision"])
@pytest.mark.parametrize("metric,source,delta,delta_pct", SOURCE_ARBITER_CHANGES)
def test_a_daily_change_is_shown_only_from_the_session_proven_to_be_the_previous_one(
    monkeypatch, metric: Metric, source: tuple[date, float] | None,
    delta: str | None, delta_pct: str | None, revise: bool,
) -> None:
    editor = _model(_section("dse", [_card("DSEX close")]))
    revised = _model(_section("dse", [_card("DSEX close", delta="−1", delta_pct="−1%")])) if revise else None
    published, reviewed = _publish(monkeypatch, _dse_builders(metric, source), editor, revised)
    if not revise:
        card = next(c for c in _reviewed_section(reviewed, "dse")["metrics"] if c["label"] == "DSEX close")
        assert (card["delta"], card["delta_pct"]) == (delta, delta_pct)
    card = next(c for c in _published_section(published, "dse").metrics if c.label == "DSEX close")
    assert (card.delta, card.delta_pct) == (delta, delta_pct)


def test_the_final_pass_never_bridges_a_missing_saturday_session() -> None:
    builders = _dse_builders(_metric("dsex", "DSEX close", 5335.86964, "index", as_of=MAY24,
                                     points=[*_MAY_WEEK, (MAY24, 5335.86964)]), (MAY24, 0.14094))
    brief = BriefPayloadV6.model_validate(_model(_section("dse", [_card("DSEX close")])))
    pipeline_v6._enforce_observation_contract(brief, pipeline_v6._to_v6_raw(builders),
                                              card_changes=pipeline_v6._card_changes(builders))
    card = brief.sections[0].metrics[0]
    assert (card.delta, card.delta_pct) == (None, None)


# ── The one batched history read keeps each point's date (landmine 23) ────────

class _Http:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows, self.calls = rows, 0

    def get(self, url: str, *, headers: dict[str, str]) -> tuple[int, Any]:
        self.calls += 1
        return 200, self.rows


def test_the_single_history_read_attaches_dated_points_to_each_card() -> None:
    http = _Http([{"metric_id": "dsex", "as_of": "2026-09-21", "value": 5550.49562},
                  {"metric_id": "dsex", "as_of": "2026-09-22", "value": 5540.32037},
                  {"metric_id": "dse_advancing", "as_of": "2026-09-22", "value": "n/a"}])
    client = MetricHistoryClient(url="https://example.invalid", service_key="k", http=http)
    dsex = _metric("dsex", "DSEX close", 5540.32037, "index")
    _enrich_metric_history([_builder("dse", dsex)], client, today=TODAY)
    assert http.calls == 1
    assert dsex.history_values == [5550.49562, 5540.32037]
    points = getattr(dsex, "history_points", None) or []
    assert [(p.as_of, p.value) for p in points] == [(SEP21, 5550.49562), (SEP22, 5540.32037)]


def test_history_without_dates_keeps_the_sparkline_but_can_never_anchor_a_change() -> None:
    class Undated:
        def get_history_window(self, ids: list[str], **kwargs: Any) -> dict[str, list[float]]:
            return {"dsex": [5550.49562, 5540.32037]}

    dsex = _metric("dsex", "DSEX close", 5540.32037, "index")
    _enrich_metric_history([_builder("dse", dsex)], Undated(), today=TODAY)
    assert dsex.history_values == [5550.49562, 5540.32037]
    assert getattr(dsex, "history_points", None) is None


# ── (i) The banker-box runway: kept only when it equals a checked builder figure ──
RUNWAY_BUILDERS = [
    _builder("fx", _metric("fx_usd_bdt_mid", "USD/BDT mid", 123.22, "BDT", as_of=TODAY)),
    _builder("macro", _metric("import_cover_months_monthly", "Import Cover", 4.972006730098555, "months",
                              as_of=D(2026, 6, 1), cadence="monthly")),
    _builder("tbond", _metric("tbond_tbill_91d", "91d T-Bill cut-off", 8.3198, "%", as_of=SEP21, cadence="event")),
]
RUNWAY_KEPT = [
    {"value": "4.97", "unit": "months"},           # what the Import Cover card shows (4.97 months)
    {"value": "4.972006730098555", "unit": "months"},
    {"value": "4.97", "unit": "MONTHS"},           # the SPA prints the unit label in capitals anyway
    {"value": "123.22", "unit": "BDT"},
    {"value": "8.31", "unit": "%"},                # the 91d card shows 8.31% (owner's truncation rule)
    {"value": "8.3198", "unit": "%"},
    {"value": "4.972", "unit": "months"},          # a truncation of the source's own decimal
    {"value": "4.97200673009856", "unit": "months"},  # the card's own stamped decimal (15 digits)
    {"value": "8.319", "unit": "%"},
]
RUNWAY_CLEARED = [
    {"value": "4.97", "unit": "mo import cover"},  # issue 235: a label, not the builder's unit
    {"value": "6.28", "unit": "mo import cover · 31 Jul read"},
    {"value": "$1.05bn", "unit": "monthly cover over the trade gap"},
    {"value": "0", "unit": "bp of CAR buffer above the 10% floor"},
    {"value": "4.98", "unit": "months"},           # not the figure
    {"value": "4.9", "unit": "months"},
    {"value": "8.32", "unit": "%"},                # rounded, but the card shows 8.31%
    {"value": "123.22", "unit": "index"},          # the digits of USD/BDT under another unit
    {"value": "~4.97", "unit": "months"},
    {"value": "4.97 months", "unit": "months"},
    {"value": "", "unit": "months"},
    # fix 16 round 1 (review MEDIUM): BankerRead.tsx prints the runway uncut, so digits past the
    # screen cut are shown too; they must be the source's own (4.972006…, 8.3198), never invented.
    {"value": "4.979", "unit": "months"},          # e.g. 4.97899 rounded: not the source's digits
    {"value": "4.97999", "unit": "months"},
    {"value": "4.97201", "unit": "months"},        # 4.972006… rounded at the 5th decimal, not cut
    {"value": "8.3199", "unit": "%"},
    {"value": "8.31999", "unit": "%"},
]


def _runway_editor(runway: dict[str, str]) -> dict[str, Any]:
    return _model(_section("fx", [_card("USD/BDT mid")], runway=runway),
                  _section("macro", [_card("Import Cover")]),
                  _section("tbond", [_card("91d T-Bill cut-off")]))


@pytest.mark.parametrize("runway", RUNWAY_KEPT, ids=lambda r: f"{r['value']} {r['unit']}")
def test_a_runway_equal_to_a_checked_builder_figure_is_kept(monkeypatch, runway: dict[str, str]) -> None:
    published, reviewed = _publish(monkeypatch, RUNWAY_BUILDERS, _runway_editor(runway))
    assert _reviewed_section(reviewed, "fx")["banker_read"]["runway"] == runway
    assert _published_section(published, "fx").banker_read.runway.model_dump() == runway


@pytest.mark.parametrize("revise", [False, True], ids=["editor-pass", "subeditor-revision"])
@pytest.mark.parametrize("runway", RUNWAY_CLEARED, ids=lambda r: f"{r['value']} {r['unit']}")
def test_a_runway_matching_no_checked_builder_figure_is_cleared(
    monkeypatch, runway: dict[str, str], revise: bool,
) -> None:
    editor = _runway_editor({"value": "4.97", "unit": "months"} if revise else runway)
    published, reviewed = _publish(monkeypatch, RUNWAY_BUILDERS, editor,
                                   _runway_editor(runway) if revise else None)
    if not revise:
        assert _reviewed_section(reviewed, "fx")["banker_read"]["runway"] is None
    assert _published_section(published, "fx").banker_read.runway is None


def test_a_runway_equal_to_the_headlines_builder_value_is_cleared(monkeypatch) -> None:
    """The Headlines card prints a count of the page, never its builder value (fix 7b §C),
    so the builder's 57 is not a figure the page shows: a runway of 57 items is cleared."""
    builders = [*RUNWAY_BUILDERS, _builder("headlines", _metric("headlines_count", "Headlines count", 57,
                                                                "items", as_of=TODAY))]
    editor = _model(_section("fx", [_card("USD/BDT mid")], runway={"value": "57", "unit": "items"}),
                    _section("headlines", [_card("Headlines count")], news=3))
    published, reviewed = _publish(monkeypatch, builders, editor)
    assert _reviewed_section(reviewed, "fx")["banker_read"]["runway"] is None
    assert _published_section(published, "fx").banker_read.runway is None


def test_the_final_pass_clears_a_runway_that_matches_nothing() -> None:
    brief = BriefPayloadV6.model_validate(_runway_editor({"value": "5", "unit": "months"}))
    pipeline_v6._enforce_observation_contract(brief, pipeline_v6._to_v6_raw(RUNWAY_BUILDERS))
    assert brief.sections[0].banker_read.runway is None


# ── The stamp → screen contract for change figures (shared with lib/format.test.ts) ──
_CONTRACT = json.loads((Path(__file__).parent / "fixtures" / "card_display_contract.json")
                       .read_text(encoding="utf-8"))


@pytest.mark.parametrize("row", _CONTRACT.get("change_rows", [None]), ids=lambda r: (r or {}).get("delta"))
def test_the_change_text_the_spa_contract_expects_is_what_the_pipeline_prints(monkeypatch, row) -> None:
    assert row is not None, "card_display_contract.json has no change_rows"
    prev, cur = row["previous"], row["current"]
    metric = _metric(row["card_id"], row["label"], cur["value"], row["unit"], cadence=row["cadence"],
                     as_of=D.fromisoformat(cur["as_of"]),
                     points=[(D.fromisoformat(prev["as_of"]), prev["value"]),
                             (D.fromisoformat(cur["as_of"]), cur["value"])])
    published, _ = _publish(monkeypatch, [_builder(row["slug"], metric)],
                            _model(_section(row["slug"], [_card(row["label"])])))
    card = _published_section(published, row["slug"]).metrics[0]
    assert (card.delta, card.delta_pct) == (row["delta"], row["delta_pct"])
