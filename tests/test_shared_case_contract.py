"""R2 task G1: the consumer side of the shared case list (contract `r2_case_contract`).

EconDelta's tests/test_shared_case_contract.py proves each record, row and receipt below is
exactly what its real aggregate, daily writer or monthly appender makes of the case's raw
input. Here the same records go through the real builders, the readiness check and the
publish sequence with FAKE Editor/Sub-editor responses that try to re-date readings,
reintroduce a rejected value, drop the protected corridor and erase held/provisional
explanations. None of that may reach the published brief.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from brief import pipeline_v6
from brief.builders import BuilderContext, dse, fx
from brief.econdelta import EconDeltaSnapshot, load_snapshot
from brief.history import HistoryRow
from brief.readiness import assess
from tests.test_producer_consumer_contract import (
    BRIEF_RUN, TODAY, contradictions, gathered_sections, held_readings)
from tests.upstream_liveness import LIVE_UPSTREAM, POLLED_UPSTREAM

CONTRACT = json.loads((Path(__file__).parent / "fixtures/contracts/brief-observations-v1.json").read_text())
CASES = CONTRACT["r2_case_contract"]
BINDING, CORRIDOR = CONTRACT["builder_binding_contract"], CONTRACT["writer_confirmation_contract"]
RUN_RECEIPT = {"status": "ok", "attempted_at": BINDING["aggregate_captured_at"]}


# ── The real 25 Sep run, changed only as each case's producer output says ──

def variant_run(tmp_path, variant_id: str):
    """latest.json and metric_history of the real run with the variant's own records: a null
    record/row is one the producer no longer publishes (EconDelta proves every other record
    and row is unchanged)."""
    variant = CASES["run_variants"][variant_id]
    records = {**{mid: r["observation"] for mid, r in BINDING["records"].items()},
               **{r["expected"]["metric_id"]: r["expected"] for r in CORRIDOR["records"]}}
    rows = {mid: r["metric_history_row"] for mid, r in BINDING["records"].items()}
    rows.update({r["expected"]["metric_id"]: r["metric_history_row"] for r in CORRIDOR["records"]})
    records = {mid: r for mid, r in {**records, **variant["observations"]}.items() if r is not None}
    rows = {mid: r for mid, r in {**rows, **variant["metric_history_rows"]}.items() if r is not None}
    path = tmp_path / "latest.json"
    path.write_text(json.dumps({
        "updated_at": BINDING["aggregate_captured_at"],
        "sources_status": {**BINDING["sources_status"], **POLLED_UPSTREAM},
        "data": {mid: r["value"] for mid, r in records.items()}, "observations": records,
        "write_status": {"daily": RUN_RECEIPT, "monthly": RUN_RECEIPT}}))
    history = [HistoryRow(r["metric_id"], date.fromisoformat(r["as_of"]), r["value"], r["source"])
               for r in rows.values()]
    return load_snapshot(path), history


def cards_of(sections) -> dict:
    return {m.id: m for s in sections for m in s.metrics}


def test_a_provisional_flash_reaches_its_card_and_readiness_as_provisional(tmp_path, monkeypatch):
    snap, rows = variant_run(tmp_path, "provisional-remittance-flash")
    cards = cards_of(gathered_sections(monkeypatch, snap, rows))
    remit = cards["remit_monthly_mn"]
    assert (remit.value, remit.as_of, remit.source) == (2970.0, date(2026, 8, 31), "BB · Aug 2026, provisional")
    result = assess(snap, persisted_rows=cards.values(), now=BRIEF_RUN)
    assert contradictions(result) == []
    assert sorted(result.reasons) == sorted([
        *held_readings(snap), "monthly_remittance: provisional reading from 2026-08-31",
        "remit_monthly_mn: provisional reading from 2026-08-31"])


def test_a_value_without_its_period_is_unavailable_and_prints_no_nbr_figure(tmp_path, monkeypatch):
    snap, rows = variant_run(tmp_path, "missing-period-tax-revenue")
    cards = cards_of(gathered_sections(monkeypatch, snap, rows))
    assert cards["fiscal_nbr_collected_trn"].value is None
    result = assess(snap, persisted_rows=cards.values(), now=BRIEF_RUN)
    assert contradictions(result) == []
    assert result.unavailable == ("fiscal_nbr_collected_trn", "nbr_fytd_collected_cr", "tax_revenue")
    assert result.state == "degraded"


def test_a_rejected_family_prints_its_dated_predecessor_as_a_held_reading(tmp_path, monkeypatch):
    snap, rows = variant_run(tmp_path, "rejected-brent-with-dated-predecessor")
    cards = cards_of(gathered_sections(monkeypatch, snap, rows))
    brent = cards["iranwar_brent_spot"]
    assert (brent.value, brent.as_of, brent.stale) == (97.1, date(2026, 9, 22), True)
    result = assess(snap, persisted_rows=cards.values(), now=BRIEF_RUN)
    assert contradictions(result) == []
    assert sorted(result.reasons) == held_readings(snap)
    assert "brent_crude_usd_barrel: held reading from 2026-09-22" in result.reasons


def test_a_rejected_family_without_a_predecessor_has_no_card(tmp_path, monkeypatch):
    snap, rows = variant_run(tmp_path, "rejected-brent-without-predecessor")
    cards = cards_of(gathered_sections(monkeypatch, snap, rows))
    assert "iranwar_brent_spot" not in cards
    assert "iranwar_wti_spot" in cards  # the rest of the family's section still builds
    result = assess(snap, persisted_rows=cards.values(), now=BRIEF_RUN)
    assert contradictions(result) == []
    assert sorted(result.reasons) == held_readings(snap)


# ── The publish sequence with a fake model that tampers with every protected fact ──

def publish(monkeypatch, sections, model_sections: list[dict], alerts: list[str] | None = None,
            today: date = TODAY):
    """run_publish with fake Editor AND Sub-editor (revise) returning the same tampered brief."""
    from brief.publication_identity import PublishIdentity

    published = fake_publish_stage(monkeypatch, model_sections, alerts, today)
    assert pipeline_v6.run_publish(sections, today, expected_identity=PublishIdentity(1, today)) == "local"
    return {s.slug: {m.label: m for m in s.metrics} for s in published[0].sections}


def fake_publish_stage(monkeypatch, model_sections: list[dict], alerts: list[str] | None = None,
                       today: date = TODAY) -> list:
    """Fake models, fetches and alert sink for run_publish; returns the list publish_brief fills."""
    model_brief = {"brief": {"issue_no": 1, "volume": 1, "brief_date": today.isoformat()},
                   "sections": model_sections}
    sink = alerts if alerts is not None else []
    fakes = {"_alert": sink.append, "fetch_previous_brief": lambda: None,
             "fetch_recent_news": lambda **kw: [], "fetch_metric_definitions": list,
             "_fetch_series_summaries": lambda *a, **kw: {}, "_stamp_chart_series": lambda *a, **kw: None,
             "_call_with_retries": lambda *, label, **kw: (
                 model_brief if label == "editor_v6"
                 else {"verdict": "revise", "issues": [], "revised_brief": model_brief})}
    for name, fake in fakes.items():
        monkeypatch.setattr(pipeline_v6, name, fake)
    published: list = []
    monkeypatch.setattr(pipeline_v6, "publish_brief", lambda payload, **kw: published.append(payload) or "local")
    return published


def number(printed: str) -> float | None:
    """The number a published card prints (house format is presentation, not the rule)."""
    from brief.builders.diff import _parse_numeric

    return _parse_numeric(printed)


def model_section(v5_id: str, metrics: list[dict]) -> dict:
    slug, ord_v6, group = pipeline_v6.V5_TO_V6[v5_id]
    return {"slug": slug, "ord": ord_v6, "title": slug, "group_key": group, "metrics": metrics}


TAMPER_WTI = {"value": "$91.00/bbl", "sub": "Fresh print today", "held_from": "2026-09-24",
              "next_print": "today, 28 Sep"}
BRENT_REJECTED_VALUE = 98.32  # the 23 Sep quote the review rejects in the rejected-brent variants
# `next_print` is system-stamped (editor_v6.txt); the SPA prints it after "As of <held_from>".
BRENT_REJECTED = {"value": f"${BRENT_REJECTED_VALUE}/bbl", "sub": "Fresh print today", "held_from": None,
                  "next_print": f"${BRENT_REJECTED_VALUE} printed 23 Sep"}
REMIT_FINAL = {"value": "$2.97bn", "sub": "August final", "held_from": None}
NBR_UNDATED_VALUE = 4.15  # the WSEI tax total whose period header is missing in that variant
NBR_UNDATED = {"value": f"Tk {NBR_UNDATED_VALUE}trn", "sub": "FY26"}
INVENTED_NBR = "NBR collected (FYTD)"  # no builder card carries this label


def tampered_brief(sections) -> list[dict]:
    """Every tampering at once: drop the corridor, re-date and re-value fresh cards, restore the
    rejected Brent figure (value and next-print footer), erase held/provisional notes, print the
    NBR total on the builder's own NBR card (undated in the missing-period variant) and on an
    invented one."""
    cards = cards_of(sections)
    wti, remit = cards["iranwar_wti_spot"].label, cards["remit_monthly_mn"].label
    brent_label = cards["iranwar_brent_spot"].label if "iranwar_brent_spot" in cards else "Brent spot"
    nbr = cards["fiscal_nbr_collected_trn"].label
    return [model_section("bb", []),
            model_section("iranwar", [{"label": wti, **TAMPER_WTI}, {"label": brent_label, **BRENT_REJECTED}]),
            model_section("remit", [{"label": remit, **REMIT_FINAL}]),
            model_section("fiscal", [{"label": nbr, **NBR_UNDATED}, {"label": INVENTED_NBR, **NBR_UNDATED}])]


PUBLISHED_SECTIONS = ("bb", "iranwar", "remit", "fiscal")


@pytest.mark.parametrize("variant_id", sorted(CASES["run_variants"]))
def test_no_model_tampering_reaches_the_published_brief(tmp_path, monkeypatch, variant_id):
    snap, rows = variant_run(tmp_path, variant_id)
    sections = [s for s in gathered_sections(monkeypatch, snap, rows) if s.id in PUBLISHED_SECTIONS]
    cards = cards_of(sections)
    out = publish(monkeypatch, sections, tampered_brief(sections))

    # Protected corridor re-injected with the producer's own rates.
    corridor = {r["expected"]["metric_id"]: r["expected"]["value"] for r in CORRIDOR["records"]}
    assert sorted(out["bb"]) == ["Policy Rate", "SDF", "SLF"]
    assert [number(out["bb"][label].value) for label in ("Policy Rate", "SDF", "SLF")] == [
        corridor[m] for m in ("policy_rate_repo", "policy_rate_sdf", "policy_rate_slf")]
    # A fresh card keeps its accepted number and gains no held-over date.
    wti = out["iran"][cards["iranwar_wti_spot"].label]
    assert (number(wti.value), wti.held_from) == (snap.observations["wti_crude_usd_barrel"]["value"], None)
    # Today's rejected Brent figure never publishes: the held predecessor, or no Brent card.
    brent = snap.observations.get("brent_crude_usd_barrel")
    printed = [m for m in out["iran"].values() if number(m.value) == BRENT_REJECTED_VALUE]
    # No run here has a catalog next-release date (no metric definitions, no previous brief), so
    # every next-print footer would be the model's: none publishes.
    assert [(slug, label, m.next_print) for slug, cards_out in out.items()
            for label, m in cards_out.items() if m.next_print] == []
    if variant_id.startswith("rejected-brent"):
        assert printed == []
        assert [m.label for m in out["iran"].values() if str(BRENT_REJECTED_VALUE) in m.model_dump_json()] == []
        if brent is None:
            assert list(out["iran"]) == [cards["iranwar_wti_spot"].label]
        else:
            card = out["iran"][cards["iranwar_brent_spot"].label]
            assert (number(card.value), card.held_from) == (brent["value"], date.fromisoformat(brent["as_of"]))
            assert card.sub.startswith("Held reading · 22 Sep 2026")
    else:  # an accepted, current Brent reading publishes as such
        assert [(m.label, m.held_from) for m in printed] == [(cards["iranwar_brent_spot"].label, None)]
    # The remittance card keeps the builder's figure, period and release status, whatever the
    # model called it ("August final"): the provisional flash, or the official July final.
    remit = out["remit"][cards["remit_monthly_mn"].label]
    provisional = snap.observations["remit_monthly_mn"]["release_status"] == "provisional"
    assert number(remit.value) == cards["remit_monthly_mn"].value
    assert "August final" not in remit.sub
    assert ("provisional" in remit.sub, "final" in remit.sub) == (provisional, not provisional)
    # An NBR total the producer could not date never prints, whatever the model writes on the
    # builder's own NBR card; an invented card never publishes; a dated total prints as built.
    fiscal = out.get("fiscal", {})
    assert INVENTED_NBR not in fiscal
    nbr = fiscal.get(cards["fiscal_nbr_collected_trn"].label)
    if variant_id == "missing-period-tax-revenue":
        assert cards["fiscal_nbr_collected_trn"].value is None
        assert nbr is None or number(nbr.value) is None
        assert [m.label for m in fiscal.values() if number(m.value) == NBR_UNDATED_VALUE] == []
    else:
        assert number(nbr.value) == cards["fiscal_nbr_collected_trn"].value


# ── Model prose (card subs, analysis): the prose-number gate is the guard there ──
PROSE_VARIANTS = ("missing-period-tax-revenue", "rejected-brent-with-dated-predecessor",
                  "rejected-brent-without-predecessor")


def prose_brief(sections, variant_id: str, *, tampered: bool) -> tuple[list[dict], tuple[str, ...]]:
    """(model sections, gate locations that must be named): the variant's refused figure — the
    undated NBR total or the rejected Brent quote — written into model-owned prose, or the same
    cards with figure-free prose (the control)."""
    cards = cards_of(sections)
    if variant_id == "missing-period-tax-revenue":
        sub = f"NBR final, Tk {NBR_UNDATED_VALUE}trn" if tampered else "NBR"
        card = {"label": cards["fiscal_nbr_collected_trn"].label, "value": "—", "sub": sub}
        return ([model_section("bb", []), model_section("fiscal", [card])],
                (f"fiscal.metrics[0].sub: 'Tk {NBR_UNDATED_VALUE}trn'",))
    sub = f"Brent at ${BRENT_REJECTED_VALUE} today" if tampered else "Oil spot"
    iran = model_section("iranwar", [{"label": cards["iranwar_wti_spot"].label, "value": "$92.25", "sub": sub}])
    analysis = f"Brent jumped to ${BRENT_REJECTED_VALUE} a barrel on 23 Sep." if tampered else "Oil held steady."
    return ([model_section("bb", []), {**iran, "analysis": analysis}],
            (f"iran.metrics[0].sub: '${BRENT_REJECTED_VALUE}'", f"iran.analysis: '${BRENT_REJECTED_VALUE}'"))


@pytest.mark.parametrize("variant_id", PROSE_VARIANTS)
def test_a_refused_figure_in_model_prose_is_alerted_and_held_under_strict_mode(tmp_path, monkeypatch, variant_id):
    """Card values are code-printed; card subs and section analysis stay the model's words. A
    refused figure written there is caught by the prose-number gate: by default (owner-staged,
    AGENTS.md prose-number gate) it is named in ONE grouped WARN alert and the brief still
    publishes; with BRIEF_PROSE_VALIDATOR_STRICT=1 the publish is held. The figure-free
    control publishes under strict, so the hold is the tampered figure's doing."""
    from brief.publication_identity import PublishIdentity

    snap, rows = variant_run(tmp_path, variant_id)

    def sections():
        return [s for s in gathered_sections(monkeypatch, snap, rows) if s.id in PUBLISHED_SECTIONS]

    tampered, named = prose_brief(sections(), variant_id, tampered=True)
    alerts: list[str] = []
    publish(monkeypatch, sections(), tampered, alerts)
    gate_alerts = [a for a in alerts if "prose-number gate" in a]
    assert len(gate_alerts) == 1
    assert [location for location in named if location not in gate_alerts[0]] == []

    monkeypatch.setenv("BRIEF_PROSE_VALIDATOR_STRICT", "1")
    published = fake_publish_stage(monkeypatch, tampered)
    with pytest.raises(pipeline_v6.ProseNumberGateError):
        pipeline_v6.run_publish(sections(), TODAY, expected_identity=PublishIdentity(1, TODAY))
    assert published == []
    clean, _ = prose_brief(sections(), variant_id, tampered=False)
    assert publish(monkeypatch, sections(), clean)


# ── Holiday closure: DSE shut for Eid-ul-Adha, 25-31 May 2026 ──
HOLIDAY = CASES["holiday_closure"]


def holiday_dse(monkeypatch, quality: str):
    """(dse section, readiness) for the holiday run's records as the producer marks them:
    'verified' with the holiday list; 'held' without it — EconDelta's
    test_the_same_session_without_the_holiday_calendar_would_read_as_held proves that
    publication differs in quality alone. The builder's dsebd.org fallbacks are faked out
    (no network), as in gathered_sections."""
    monkeypatch.setattr(dse, "scrape_breadth", lambda *a, **k: None)
    monkeypatch.setattr(dse, "scrape_sector_heat", lambda *a, **k: None)
    run = datetime.fromisoformat(HOLIDAY["aggregate_now"])
    records = {mid: {**r, "quality": quality} for mid, r in HOLIDAY["observations"].items()}
    snap = EconDeltaSnapshot(updated_at=run, sources_status={**HOLIDAY["sources_status"], **LIVE_UPSTREAM},
                             data={mid: r["value"] for mid, r in records.items()}, observations=records,
                             write_status={"daily": {**RUN_RECEIPT, "attempted_at": HOLIDAY["aggregate_now"]},
                                           "monthly": {**RUN_RECEIPT, "attempted_at": HOLIDAY["aggregate_now"]}})

    class Rows:
        def get_latest(self, metric_id, **kwargs):
            row = HOLIDAY["metric_history_rows"].get(metric_id)
            return row and HistoryRow(row["metric_id"], date.fromisoformat(row["as_of"]), row["value"], row["source"])

    today = date.fromisoformat(HOLIDAY["brief_today"])
    section = dse.build(BuilderContext(snap, Rows(), today))
    result = assess(snap, persisted_rows=section.metrics,
                    now=datetime.combine(today, datetime.min.time(), timezone.utc) + timedelta(hours=2))
    return section, result


def test_the_last_session_before_a_holiday_closure_prints_as_a_current_dse_reading(monkeypatch):
    section, result = holiday_dse(monkeypatch, "verified")
    dsex = next(m for m in section.metrics if m.id == "dsex")
    assert (dsex.value, dsex.as_of, dsex.stale) == (HOLIDAY["observations"]["dsex"]["value"], date(2026, 5, 24), False)
    assert (result.state, result.reasons) == ("ready", ())


def test_a_dse_session_the_producer_holds_prints_as_a_held_reading(monkeypatch):
    """A session EconDelta publishes as 'held' (no confirmed new session) must not print as
    today's market: every DSE card from a held record is stale, and the published DSEX card
    carries the held note and date whatever the model writes. The verified run stays current."""
    held, result = holiday_dse(monkeypatch, "held")
    assert [(m.id, m.as_of, m.stale) for m in held.metrics if not m.stale] == []
    assert {m.as_of for m in held.metrics} == {date(2026, 5, 24)}
    # The section badge says stale too, without the history fallback's "Non-trading day" note.
    assert (held.freshness, held.freshness_reason) == ("stale", None)
    assert result.state == "degraded" and contradictions(result) == []
    verified, _ = holiday_dse(monkeypatch, "verified")
    model = [model_section("dse", [{"label": "DSEX close", "value": "5,540", "sub": "Today's close",
                                    "held_from": None, "next_print": "today, 28 Sep"}])]
    today = date.fromisoformat(HOLIDAY["brief_today"])
    published = {q: publish(monkeypatch, [s], model, today=today)[pipeline_v6.V5_TO_V6["dse"][0]]["DSEX close"]
                 for q, s in (("held", held), ("verified", verified))}
    # Both print the 24 May session's date (the verified one via the daily vintage footer, the
    # market having been shut since); only the held one is published as a held reading.
    # The footer's "next print" is system-stamped; the model's "today, 28 Sep" never shows.
    assert {q: (card.held_from, card.sub.startswith("Held reading · "), card.next_print)
            for q, card in published.items()} == {
        "held": (date(2026, 5, 24), True, None), "verified": (date(2026, 5, 24), False, None)}


# ── Bangladesh-calendar crossings: month, FY, year and leap-day starts ──
BD = CONTRACT["bangladesh_calendar_contract"]
BD_FOREX = [c for c in BD["cases"] if c["record"]["source"] == "bb_forex"]


@pytest.mark.parametrize("case", BD_FOREX, ids=lambda c: c["case_id"])
def test_each_bb_forex_calendar_case_reaches_the_fx_card_only_when_the_producer_accepts_it(case):
    """The record EconDelta publishes for the case (verified, or its own record marked
    unavailable when the date is ahead of the capture's Dhaka day)."""
    record = case["record"] if case["producer_eligible"] else {**case["record"], "quality": "unavailable"}
    run = datetime.fromisoformat(case["aggregate_now"])
    receipt = {"status": "ok", "attempted_at": case["aggregate_now"]}
    snap = EconDeltaSnapshot(updated_at=run, sources_status=POLLED_UPSTREAM, data={"usd_bdt_mid": record["value"]},
                             observations={"usd_bdt_mid": record},
                             write_status={"daily": receipt, "monthly": receipt})
    today = date.fromisoformat(case["brief_today"])
    card = next((m for m in fx.build(BuilderContext(snap, None, today)).metrics if m.id == "fx_usd_bdt_mid"), None)
    result = assess(snap, persisted_rows=[card] if card else [],
                    now=datetime.combine(today, datetime.min.time(), timezone.utc) + timedelta(hours=2))
    if case["consumer_accepted"]:
        assert (card.value, card.as_of.isoformat(), card.stale) == (record["value"], record["as_of"], False)
        assert "usd_bdt_mid" not in result.unavailable and contradictions(result) == []
    else:
        assert card is None
        assert result.unavailable == ("usd_bdt_mid",) and contradictions(result) == []


def test_every_calendar_boundary_the_case_list_names_has_an_accepted_and_a_refused_day():
    boundaries = {c["case_id"].rsplit("-", 1)[0] for c in BD_FOREX if c["case_id"].startswith("bb-forex-")}
    for boundary in ("bb-forex-month-start", "bb-forex-fy-start", "bb-forex-year-start",
                     "bb-forex-leap-day", "bb-forex-after-leap-day"):
        verdicts = {c["consumer_accepted"] for c in BD_FOREX if c["case_id"].startswith(boundary)}
        assert verdicts == {True, False}, boundary
    assert boundaries


# ── Equal yield on a new auction: the chart's last-auction note reads the refreshed rung ──
REFRESH = CONTRACT["monthly_contract"]["yield_refresh"]


@pytest.mark.parametrize("source_as_of,expected", [
    ("stored_source_as_of", "stored_source_as_of"), ("candidate_source_as_of", "candidate_source_as_of")],
    ids=["before-refresh", "after-refresh"])
def test_the_yield_ladder_names_the_auction_its_rung_was_last_confirmed_by(source_as_of, expected):
    from brief.chart_series_fetcher import (
        _YIELD_LADDER_MONTHLY_METRIC_IDS, fetch_yield_ladder_last_auction, fetch_yield_ladder_monthly)

    month = date.fromisoformat(REFRESH["grouping_key"])
    stored = date.fromisoformat(REFRESH[source_as_of])

    class Monthly:
        def get_history_window(self, metric_ids, **kwargs):
            return {mid: [HistoryRow(mid, month, REFRESH["candidate_value"], "econdelta_yield_ladder", stored)]
                    for mid in metric_ids}

    note = fetch_yield_ladder_last_auction(Monthly())
    assert (note.ts, note.label) == (REFRESH[expected], "last auction")
    ladder = fetch_yield_ladder_monthly(Monthly())
    assert {(p.ts, p.value) for mid in _YIELD_LADDER_MONTHLY_METRIC_IDS for p in ladder[mid]} == {
        (REFRESH["grouping_key"], REFRESH["candidate_value"])}


# ── Partial writer failure: EconDelta's own receipt for one failed leg beside a confirmed one ──
PARTIAL = CASES["partial_writer_failure"]


def test_a_failed_monthly_leg_holds_even_beside_a_leg_that_confirmed_rows():
    from tests.test_readiness_monthly_lag import T, judge
    from tests.test_readiness_quiet_day_contract import quiet_day

    assert PARTIAL["attempted_at"] == T
    macro = PARTIAL["macro"]
    assert (macro["legs"]["cpi"]["status"], macro["legs"]["cpi"]["confirmed_rows"]) == ("ok", 3)
    failed = judge(_with_macro(quiet_day(), macro), sources=LIVE_UPSTREAM)
    assert failed.state == "hold"
    assert [r for r in failed.reasons if r.startswith("monthly persistence failed")] != []
    # The same run with remittance merely lagging (the quiet day's reading) does not hold.
    lagging = {**macro, "legs": {**macro["legs"], "remittance": _QUIET_MACRO()["legs"]["remittance"]}}
    assert judge(_with_macro(quiet_day(), _recombined(lagging)), sources=LIVE_UPSTREAM).state != "hold"


def _QUIET_MACRO() -> dict:
    from tests.test_readiness_monthly_lag import caught_up

    return caught_up()["monthly"]["legs"]["chart_appenders"]["legs"]["macro"]


def _recombined(macro: dict) -> dict:
    """A macro parent whose status follows its legs (EconDelta combine_monthly)."""
    from tests.test_readiness_monthly_lag import parent

    return {**parent(macro["legs"]), "reason": macro["reason"]}


def _with_macro(write_status: dict, macro: dict) -> dict:
    """Swap the macro leg into the quiet day's real nesting, parents recomputed from their legs."""
    from tests.test_readiness_monthly_lag import parent

    monthly = write_status["monthly"]["legs"]
    appenders = parent({**monthly["chart_appenders"]["legs"], "macro": macro})
    return {**write_status, "monthly": parent({**monthly, "chart_appenders": appenders})}
