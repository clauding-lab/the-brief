from brief.claude.validators import (
    validate_curation, validate_signals, validate_insights,
    ValidationResult,
)


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
