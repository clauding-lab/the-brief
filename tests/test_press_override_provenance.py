"""Owner decision (c), 26 Sep 2026 BDT: an owner-approved press override shows its press source.

EconDelta's `_apply_media_overrides` re-asserts a human-approved press figure into
`metric_history` with source `media-approved:<outlet>` (e.g. NPL 32.78% @ 2026-06-30 from
The Daily Star). Such a figure is the press's, not Bangladesh Bank's: the card must say
"via The Daily Star (approved)" and must never print "BB". An outlet slug with no explicit
name mapping is shown as the slug itself — never a guessed publication name.
"""
from datetime import date

import pytest

from brief import pipeline_v6
from brief.builders import BuilderContext, banking, bb, fiscal, macro
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow
from brief.press_override import PressOverride
from brief.v6_schema import BriefPayloadV6
from brief.validators.prose_numbers import check_press_figure_attribution

TODAY = date(2026, 9, 26)
NPL_PRESS = HistoryRow("banking_npl_pct", date(2026, 6, 30), 32.78, "media-approved:thedailystar")


class History:
    def __init__(self, *rows):
        self.rows = {r.metric_id: r for r in rows}

    def get_latest(self, metric_id, **kwargs):
        return self.rows.get(metric_id)

    def get_at_or_before(self, metric_id, as_of, **kwargs):
        row = self.rows.get(metric_id)
        return row if row is not None and row.as_of <= as_of else None


def built(builder, *rows):
    snap = EconDeltaSnapshot(None, {}, {})
    return {m.id: m for m in builder.build(BuilderContext(snap, History(*rows), TODAY)).metrics}


# (builder, card id, the history id an override for that card is written to)
OVERRIDE_READERS = [
    (banking, "banking_npl_pct", "banking_npl_pct"),  # EconDelta gross_npl_ratio alias
    (banking, "banking_car_pct", "banking_car_pct"),  # banking_sector_crar alias
    (fiscal, "fiscal_nbr_collected_trn", "fiscal_nbr_collected_trn"),  # tax_revenue conversion
    (bb, "bb_policy_rate", "policy_rate_repo"),
    (bb, "bb_call_money", "call_money_rate"),
    (macro, "private_credit_growth_yoy_monthly", "private_sector_credit_yoy_pct"),
]


@pytest.mark.parametrize("builder,card_id,history_id", OVERRIDE_READERS,
                         ids=[c for _, c, _ in OVERRIDE_READERS])
def test_a_card_built_from_an_approved_press_row_names_the_outlet_not_bb(builder, card_id, history_id):
    row = HistoryRow(history_id, date(2026, 6, 30), 12.34, "media-approved:thedailystar")
    card = built(builder, row)[card_id]
    assert (card.value, card.as_of) == (12.34, date(2026, 6, 30))
    assert card.source == "via The Daily Star (approved)"
    assert card.press_override == PressOverride("thedailystar", 12.34, date(2026, 6, 30))
    assert card.source_url is None  # a BB link on a press figure would re-attribute it


@pytest.mark.parametrize("builder,card_id,history_id", OVERRIDE_READERS,
                         ids=[c for _, c, _ in OVERRIDE_READERS])
def test_an_ordinary_history_row_keeps_its_builder_source(builder, card_id, history_id):
    card = built(builder, HistoryRow(history_id, date(2026, 6, 30), 12.34, "EconDelta"))[card_id]
    assert card.press_override is None
    assert card.source in ("BB", "NBR")


@pytest.mark.parametrize("row_source,label", [
    ("media-approved:thedailystar", "via The Daily Star (approved)"),
    ("media-approved:tbsnews", "via The Business Standard (approved)"),
    # No explicit name mapping: the slug is shown as written, never a guessed outlet name.
    ("media-approved:newagebd", "via newagebd (approved)"),
    ("media-approved:www.example.org", "via www.example.org (approved)"),
    # EconDelta's own label when media_review carries no outlet.
    ("media-approved:press", "via press (approved)"),
])
def test_outlet_names_are_explicit_and_unknown_slugs_are_shown_verbatim(row_source, label):
    card = built(banking, HistoryRow("banking_npl_pct", date(2026, 6, 30), 32.78, row_source))
    assert card["banking_npl_pct"].source == label


# ── The published card: its `sub` is the only per-metric text Section.tsx renders ──
def _publish(monkeypatch, sections, model_sections, keep_alert=False):
    """Run the whole publish sequence with fake Editor/Sub-editor output; return the payload."""
    from brief.publication_identity import PublishIdentity
    model_brief = {"brief": {"issue_no": 1, "volume": 1, "brief_date": TODAY.isoformat()},
                   "sections": model_sections}

    def fake_model(*, label, input_obj, **kw):
        return model_brief if label == "editor_v6" else {"verdict": "pass", "issues": []}

    fakes = {"fetch_previous_brief": lambda: None,
             "fetch_recent_news": lambda **kw: [], "fetch_metric_definitions": list,
             "_fetch_series_summaries": lambda *a, **kw: {},
             "_stamp_chart_series": lambda *a, **kw: None, "_call_with_retries": fake_model}
    if not keep_alert:
        fakes["_alert"] = lambda message: None
    for name, fake in fakes.items():
        monkeypatch.setattr(pipeline_v6, name, fake)
    published = []
    monkeypatch.setattr(pipeline_v6, "publish_brief", lambda payload, **kw: published.append(payload) or "local")
    assert pipeline_v6.run_publish(sections, TODAY, expected_identity=PublishIdentity(1, TODAY)) == "local"
    return published[0]


def _banking_model_section(npl_sub):
    slug, ord_v6, group = pipeline_v6.V5_TO_V6["banking"]
    return {"slug": slug, "ord": ord_v6, "title": "Banking", "group_key": group,
            "metrics": [{"label": "NPL Ratio", "value": "32.78%", "sub": npl_sub},
                        {"label": "CAR", "value": "1.56%", "sub": "BB FSR, Sep 2025"}]}


@pytest.mark.parametrize("model_sub", ["BB FSR · Jun 2026", "Bangladesh Bank, Q2", "", None])
def test_the_published_press_card_names_the_outlet_whatever_the_model_wrote(monkeypatch, model_sub):
    """Owner decision (c): the reader sees "via The Daily Star (approved)" under the figure,
    with its own period; a model sub that credits BB (or none at all) does not survive."""
    section = banking.build(BuilderContext(
        EconDeltaSnapshot(None, {}, {}),
        History(NPL_PRESS, HistoryRow("banking_car_pct", date(2025, 9, 30), 1.56, "EconDelta")), TODAY))
    payload = _publish(monkeypatch, [section], [_banking_model_section(model_sub)])
    cards = {m.label: m for s in payload.sections for m in s.metrics}
    assert cards["NPL Ratio"].sub == "Q2 2026 · via The Daily Star (approved)"
    # An ordinary BB card is untouched by the press stamp.
    assert cards["CAR"].sub == "BB FSR, Sep 2025"


def test_prose_that_credits_bb_with_the_press_figure_is_flagged(monkeypatch):
    """The model's prose must not re-attribute an approved press figure to BB. The check is
    WARN-mode like every other prose figure check (landmine 34), so it joins the grouped alert."""
    section = banking.build(BuilderContext(EconDeltaSnapshot(None, {}, {}), History(NPL_PRESS), TODAY))
    raw = pipeline_v6._to_v6_raw([section], today=TODAY)
    model = _banking_model_section("")
    model["tldr"] = "Bangladesh Bank puts the NPL ratio at 32.78%. Capital stays thin."
    model["analysis"] = "The Daily Star's 32.78% reading is the approved figure; BB's own FSR last said 35.73%."
    payload = BriefPayloadV6.model_validate({"brief": {"issue_no": 1, "volume": 1,
                                                       "brief_date": TODAY.isoformat()},
                                             "sections": [model]})
    warnings = check_press_figure_attribution(payload, {s["slug"]: s for s in raw})
    assert [(w.kind, w.field_path) for w in warnings] == [("press_figure_credited_to_bb", "banking.tldr")]


def test_prose_attribution_check_is_silent_without_a_press_figure():
    section = banking.build(BuilderContext(
        EconDeltaSnapshot(None, {}, {}),
        History(HistoryRow("banking_npl_pct", date(2026, 6, 30), 32.78, "EconDelta")), TODAY))
    raw = pipeline_v6._to_v6_raw([section], today=TODAY)
    model = {**_banking_model_section(""), "tldr": "Bangladesh Bank puts the NPL ratio at 32.78%."}
    payload = BriefPayloadV6.model_validate({"brief": {"issue_no": 1, "volume": 1,
                                                       "brief_date": TODAY.isoformat()},
                                             "sections": [model]})
    assert check_press_figure_attribution(payload, {s["slug"]: s for s in raw}) == []


def test_a_cpi_card_whose_newest_official_reading_is_a_press_row_names_the_outlet():
    """The CPI food card picks the newest official reading across the daily and monthly
    tables; when that reading is an approved press row, the card carries its outlet."""
    press = HistoryRow("food_inflation", date(2026, 8, 31), 7.91, "media-approved:tbsnews",
                       date(2026, 8, 31))
    card = built(macro, press)["cpi_p2p_food_monthly"]
    assert (card.value, card.as_of) == (7.91, date(2026, 8, 31))
    assert card.source == "via The Business Standard (approved)"
    assert card.press_override == PressOverride("tbsnews", 7.91, date(2026, 8, 31))


def test_a_bb_credit_for_the_press_figure_reaches_the_grouped_prose_alert(monkeypatch):
    """The attribution check runs inside the real prose-number gate of the publish sequence."""
    section = banking.build(BuilderContext(EconDeltaSnapshot(None, {}, {}), History(
        NPL_PRESS, HistoryRow("banking_car_pct", date(2025, 9, 30), 1.56, "EconDelta")), TODAY))
    alerts = []
    model = {**_banking_model_section(""), "tldr": "BB data put the NPL ratio at 32.78% in June."}
    monkeypatch.setattr(pipeline_v6, "_alert", alerts.append)
    payload = _publish(monkeypatch, [section], [model], keep_alert=True)
    assert payload.sections[0].tldr == "BB data put the NPL ratio at 32.78% in June."  # WARN, not rewrite
    assert any("press_figure_credited_to_bb" in a and "banking.tldr" in a for a in alerts)


# ── Round 1: the derived Real Policy Rate names an approved press input ─────
# The card is repo − p2p CPI. Both inputs are ids EconDelta's `_apply_media_overrides` can
# write (`policy_rate_repo`, `point_to_point_inflation`). Decision (c): a press figure is never
# credited to BB (or BBS); the derivation note names the outlet on the leg it came from, and
# that note is what `_stamp_real_policy_rate_sub` publishes as the card's `sub`.
MPC_CUT = date(2026, 7, 30)
REPO_OFFICIAL = HistoryRow("policy_rate_repo", date(2026, 9, 25), 9.5, "EconDelta")
CPI_OFFICIAL = HistoryRow("point_to_point_inflation", date(2026, 8, 31), 8.29, "EconDelta")
CPI_PRESS = HistoryRow("point_to_point_inflation", date(2026, 8, 31), 8.10,
                       "media-approved:thedailystar")
REPO_PRESS = HistoryRow("policy_rate_repo", date(2026, 9, 25), 9.25, "media-approved:tbsnews")

REAL_POLICY_PRESS_CASES = [
    pytest.param(CPI_PRESS, REPO_OFFICIAL, 1.40,
                 "BB+The Daily Star (9.50% repo (30 Jul cut) − 8.10% Aug p2p CPI "
                 "via The Daily Star (approved))",
                 "9.50% repo (30 Jul cut) − 8.10% Aug p2p CPI via The Daily Star (approved)",
                 id="press-cpi-leg"),
    pytest.param(CPI_OFFICIAL, REPO_PRESS, 0.96,
                 "The Business Standard+BBS (9.25% repo (30 Jul cut) via The Business Standard "
                 "(approved) − 8.29% Aug p2p CPI)",
                 "9.25% repo (30 Jul cut) via The Business Standard (approved) − 8.29% Aug p2p CPI",
                 id="press-repo-leg"),
]


def _real_policy_card(monkeypatch, *rows):
    monkeypatch.setattr("brief.builders.bb._LAST_MPC_DECISION", MPC_CUT)
    return built(macro, *rows)["real_policy_rate_monthly"]


@pytest.mark.parametrize("cpi,repo,value,source,note", REAL_POLICY_PRESS_CASES)
def test_a_real_policy_rate_derived_from_a_press_input_names_that_outlet(
        monkeypatch, cpi, repo, value, source, note):
    """A press leg is credited to its outlet in both the source prefix and the leg itself;
    the official leg keeps its agency. BB+BBS would credit a press figure to BB/BBS."""
    card = _real_policy_card(monkeypatch, cpi, repo)
    assert card.value == pytest.approx(value)
    assert card.source == source
    assert card.press_override is None  # the derived value is not the press row's value


def test_a_real_policy_rate_from_official_inputs_still_credits_bb_and_bbs(monkeypatch):
    card = _real_policy_card(monkeypatch, CPI_OFFICIAL, REPO_OFFICIAL)
    assert card.source == "BB+BBS (9.50% repo (30 Jul cut) − 8.29% Aug p2p CPI)"


def _macro_payload(sub):
    slug, ord_v6, group = pipeline_v6.V5_TO_V6["macro"]
    return BriefPayloadV6.model_validate({
        "brief": {"issue_no": 1, "volume": 1, "brief_date": TODAY.isoformat()},
        "sections": [{"slug": slug, "ord": ord_v6, "title": "Macro", "group_key": group,
                      "metrics": [{"label": "Real Policy Rate", "value": "1.4%", "sub": sub}]}]})


@pytest.mark.parametrize("cpi,repo,value,source,note", REAL_POLICY_PRESS_CASES)
def test_the_published_real_policy_rate_sub_shows_the_press_outlet(
        monkeypatch, cpi, repo, value, source, note):
    """`sub` is the only per-card text the SPA renders, so the outlet must survive the stamp."""
    monkeypatch.setattr("brief.builders.bb._LAST_MPC_DECISION", MPC_CUT)
    section = macro.build(BuilderContext(EconDeltaSnapshot(None, {}, {}), History(cpi, repo), TODAY))
    raw = pipeline_v6._to_v6_raw([section], today=TODAY)
    payload = _macro_payload("Aug 2026")
    pipeline_v6._stamp_real_policy_rate_sub(payload, raw)
    assert payload.sections[0].metrics[0].sub == f"Aug 2026 · {note}"


@pytest.mark.parametrize("cpi,repo,value,source,note", REAL_POLICY_PRESS_CASES)
def test_the_prose_gate_removes_exactly_the_stamped_press_note(
        monkeypatch, cpi, repo, value, source, note):
    """The prose gate's mirror of the stamper must strip the whole machine note (outlet
    included), leaving only the editor's own words to be number-checked."""
    from brief.validators.prose_numbers import _editor_written_sub
    card = _real_policy_card(monkeypatch, cpi, repo)
    raw_metric = {"label": "Real Policy Rate", "value": card.value, "source": card.source}
    assert _editor_written_sub(f"Aug 2026 · {note}", raw_metric) == "Aug 2026"


def test_a_real_policy_rate_with_both_legs_from_one_outlet_credits_only_that_outlet(monkeypatch):
    """Neither BB nor BBS supplied a leg, so neither is credited; the outlet is named once."""
    repo = HistoryRow("policy_rate_repo", date(2026, 9, 25), 9.25, "media-approved:thedailystar")
    card = _real_policy_card(monkeypatch, CPI_PRESS, repo)
    assert card.source == ("The Daily Star (9.25% repo (30 Jul cut) via The Daily Star (approved) "
                           "− 8.10% Aug p2p CPI via The Daily Star (approved))")
