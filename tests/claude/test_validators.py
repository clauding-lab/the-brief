from brief.claude.validators import (
    validate_curation, validate_signals, validate_insights,
    validate_risk_map_layout, validate_todays_call,
    ValidationResult,
)
from brief.schema import MapCoord, TodaysCall


def test_curation_valid():
    payload = {"selected": [{"url": "u1", "domain": "fx", "weight": "high"},
                            {"url": "u2", "domain": "banking", "weight": "med"}],
               "rationale_bullet": "mixed signal day"}
    r = validate_curation(payload, allowed_urls={"u1", "u2", "u3"})
    assert r.ok is True
    assert r.value == payload


def test_curation_rejects_unknown_url():
    payload = {"selected": [{"url": "INVENTED", "domain": "fx", "weight": "high"}],
               "rationale_bullet": "x"}
    r = validate_curation(payload, allowed_urls={"u1"})
    assert r.ok is False


def test_curation_rejects_bad_weight():
    payload = {"selected": [{"url": "u1", "domain": "fx", "weight": "HUGE"}],
               "rationale_bullet": "x"}
    r = validate_curation(payload, allowed_urls={"u1"})
    assert r.ok is False


def test_signals_valid():
    payload = {"signals": [
        {"direction": "bull", "text": "Reserves up", "section_anchor": "bb"},
    ], "traffic_status": "neu"}
    r = validate_signals(payload, allowed_anchors={"bb", "fx"})
    assert r.ok is True


def test_signals_rejects_bad_anchor():
    payload = {"signals": [{"direction": "bull", "text": "x",
                            "section_anchor": "nope"}],
               "traffic_status": "neu"}
    r = validate_signals(payload, allowed_anchors={"bb"})
    assert r.ok is False


def test_signals_rejects_too_long_text():
    long = " ".join(["word"] * 30)
    payload = {"signals": [{"direction": "bull", "text": long,
                            "section_anchor": "bb"}],
               "traffic_status": "neu"}
    r = validate_signals(payload, allowed_anchors={"bb"})
    assert r.ok is False


def test_insights_full_requires_four_sentences():
    payload = {"insights": {"bb": ["a", "b", "c", "d"],
                            "fx": ["a", "b", "c"]}}
    r = validate_insights(payload, allowed_section_ids={"bb", "fx"}, stale=False)
    assert r.ok is True
    assert set(r.value["insights"].keys()) == {"bb"}
    assert "fx" in r.dropped


def test_insights_stale_requires_one_sentence():
    payload = {"insights": {"remit": ["no fresh data; x"]}}
    r = validate_insights(payload, allowed_section_ids={"remit"}, stale=True)
    assert r.ok is True


def test_insights_rejects_double_quotes():
    payload = {"insights": {"bb": ['has "bad" quotes', "b", "c", "d"]}}
    r = validate_insights(payload, allowed_section_ids={"bb"}, stale=False)
    assert r.ok is True
    assert "bb" in r.dropped  # dropped for invalid quotes


# ---------------------------------------------------------------------------
# Shared fixture data for risk_map_layout tests
# ---------------------------------------------------------------------------

_SECTION_IDS = {
    "bb", "macro", "fx", "remit", "dse", "tbond",
    "iranwar", "headlines", "exec", "comm", "banking",
    "dam", "fiscal", "nbr",
}

_READ_ORDER = [
    "headlines", "bb", "macro", "fx", "remit", "dse",
    "tbond", "iranwar", "exec", "comm", "banking", "dam",
    "fiscal", "nbr",
]


def _make_sections(overrides: dict | None = None) -> list[dict]:
    """Build 14 valid section dicts, one per section_id.

    Pass overrides={section_id: {field: value}} to tweak specific entries.
    """
    overrides = overrides or {}
    sections = []
    for i, sid in enumerate(_SECTION_IDS):
        entry = {
            "section_id": sid,
            "x": float(i % 10),
            "y": float((i * 2) % 10),
            "r": 30,
            "type": "anchor",
            "hero_metric_id": None,
        }
        if sid in overrides:
            entry.update(overrides[sid])
        sections.append(entry)
    return sections


def _make_payload(
    sections: list[dict] | None = None,
    read_order: list[str] | None = None,
) -> dict:
    return {
        "sections": sections if sections is not None else _make_sections(),
        "read_order": read_order if read_order is not None else list(_READ_ORDER),
    }


# ---------------------------------------------------------------------------
# validate_risk_map_layout tests
# ---------------------------------------------------------------------------


def test_risk_map_layout_happy_path():
    r = validate_risk_map_layout(_make_payload(), section_ids=_SECTION_IDS)
    assert r.ok is True
    assert len(r.value["sections"]) == 14
    assert isinstance(r.value["sections"][0], MapCoord)
    assert set(r.value["read_order"]) == _SECTION_IDS
    assert len(r.value["read_order"]) == 14


def test_risk_map_layout_missing_section():
    sections = _make_sections()
    # Drop one entry (remove "bb")
    sections = [s for s in sections if s["section_id"] != "bb"]
    payload = _make_payload(sections=sections)
    r = validate_risk_map_layout(payload, section_ids=_SECTION_IDS)
    assert r.ok is False
    assert "missing" in r.reason or "mismatch" in r.reason


def test_risk_map_layout_extra_section():
    sections = _make_sections()
    # Add a 15th entry
    sections.append({
        "section_id": "extra",
        "x": 1.0,
        "y": 1.0,
        "r": 30,
        "type": "anchor",
        "hero_metric_id": None,
    })
    payload = _make_payload(sections=sections)
    r = validate_risk_map_layout(payload, section_ids=_SECTION_IDS)
    assert r.ok is False
    assert "mismatch" in r.reason or "unknown" in r.reason or "count" in r.reason


def test_risk_map_layout_x_out_of_range():
    sections = _make_sections(overrides={"bb": {"x": 11.1}})
    r = validate_risk_map_layout(_make_payload(sections=sections), section_ids=_SECTION_IDS)
    assert r.ok is False
    assert "MapCoord" in r.reason or "x" in r.reason or "validation" in r.reason.lower()


def test_risk_map_layout_invalid_hero_metric_id():
    sections = _make_sections(overrides={"bb": {"hero_metric_id": "unknown_metric"}})
    known = {sid: {"metric_a", "metric_b"} for sid in _SECTION_IDS}
    r = validate_risk_map_layout(
        _make_payload(sections=sections),
        section_ids=_SECTION_IDS,
        known_metric_ids=known,
    )
    assert r.ok is False
    assert "hero_metric_id" in r.reason


def test_risk_map_layout_read_order_duplicate():
    # Drop "nbr", add "bb" twice
    bad_order = [sid for sid in _READ_ORDER if sid != "nbr"] + ["bb"]
    r = validate_risk_map_layout(
        _make_payload(read_order=bad_order),
        section_ids=_SECTION_IDS,
    )
    assert r.ok is False
    assert "read_order" in r.reason


def test_risk_map_layout_invalid_type():
    sections = _make_sections(overrides={"macro": {"type": "invalid"}})
    r = validate_risk_map_layout(_make_payload(sections=sections), section_ids=_SECTION_IDS)
    assert r.ok is False


# ---------------------------------------------------------------------------
# validate_todays_call tests
# ---------------------------------------------------------------------------


def test_todays_call_happy_path():
    text = (
        "Bangladesh's foreign-exchange reserves climbed for a third straight week "
        "as remittance inflows held firm, narrowing the current-account gap and "
        "giving the central bank room to hold its policy rate steady into the next "
        "quarter without triggering further taka depreciation against the dollar."
    )
    r = validate_todays_call({"text": text})
    assert r.ok is True
    assert r.value.text == text
    assert r.value.byline == "Desk Editor · The Brief"


def test_todays_call_empty_text():
    r = validate_todays_call({"text": ""})
    assert r.ok is False


def test_todays_call_long_text_is_accepted():
    # No length cap — spec allows 60-100 words (~700 chars at max)
    text = "x" * 700
    r = validate_todays_call({"text": text})
    assert r.ok is True


def test_todays_call_contains_desk_editor():
    r = validate_todays_call({"text": "Markets rally — Desk Editor picks top story."})
    assert r.ok is False
    assert "Desk Editor" in r.reason


def test_todays_call_contains_double_quote():
    r = validate_todays_call({"text": 'He said "bullish" on taka.'})
    assert r.ok is False
    assert "double quote" in r.reason
