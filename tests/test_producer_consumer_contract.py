"""Consumer regressions driven by source dates, never collection clocks."""
from datetime import date, datetime, timezone
import json
from pathlib import Path

import pytest

from brief.builders import BuilderContext
from brief.builders import fx, iranwar, macro, remit
from brief.builders.diff import _parse_numeric, _values_equal
from brief.chart_series_fetcher import fetch_macro_cpi_series, is_official_cpi_point
from brief.econdelta import load_snapshot
from brief.history import HistoryRow
from brief import pipeline_v6
from brief.v6_schema import BriefPayloadV6, BriefV6, MetricV6, SectionV6
from tests.upstream_liveness import POLLED_UPSTREAM

TODAY = date(2026, 9, 25)


class History:
    def __init__(self, rows=()):
        self.rows = {r.metric_id: r for r in rows}

    def get_latest(self, metric_id, **kwargs):
        return self.rows.get(metric_id)

    def get_history_window(self, metric_ids, **kwargs):
        return {mid: [self.rows[mid]] if mid in self.rows else [] for mid in metric_ids}


def snapshot(tmp_path, data, observations=None):
    # sources_status: EconDelta's LatestBundle has always required it (load_snapshot does too).
    payload = {"updated_at": "2026-09-25T01:00:00+06:00", "sources_status": {}, "data": data}
    if observations is not None:
        payload["observations"] = observations
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(payload))
    return load_snapshot(path)


def observation(mid, base_value, as_of="2026-09-23", **overrides):
    return {"metric_id": mid, "value": base_value, "as_of": as_of,
            "unit": {"gold_usd_oz": "USD/oz", "usd_bdt_mid": "BDT",
                     "remit_monthly_mn": "USD million"}.get(mid, "USD/barrel"), "source": "source fixture", "source_url": None,
            "captured_at": "2026-09-25T01:00:00+06:00", "quality": "verified",
            "date_basis": "observation", "evidence": "dated source fixture",
            "dependencies": [], "release_status": "unknown", **overrides}


def context(tmp_path, *, data=None, observations=None, rows=(), monthly=()):
    return BuilderContext(snapshot(tmp_path, data or {}, observations), History(rows), TODAY,
                          history_monthly=History(monthly))


def test_official_cpi_writer_and_point_exclusions():
    assert is_official_cpi_point("cpi_p2p_food_monthly", "2026-08-01", "econdelta_daily_cpi")
    assert not is_official_cpi_point("cpi_p2p_food_monthly", "2026-07-01", "derived_weighted")
    assert not is_official_cpi_point("cpi_p2p_nonfood_monthly", "2026-07-01", "econdelta_daily_cpi")


def test_monthly_cpi_cards_and_chart_keep_concepts_and_true_month_end(tmp_path):
    rows = [HistoryRow(mid, date(2026, 8, 1), value, "econdelta_daily_cpi") for mid, value in
            [("cpi_12m_avg_monthly", 8.66), ("cpi_p2p_food_monthly", 7.5),
             ("cpi_p2p_nonfood_monthly", 9.0)]]
    ctx = context(tmp_path, monthly=rows)
    cards = {m.id: m for m in macro.build(ctx).metrics}
    chart = fetch_macro_cpi_series(ctx.history_monthly)
    for row in rows:
        assert cards[row.metric_id].value == row.value
        assert cards[row.metric_id].as_of == date(2026, 8, 31)
        assert chart[row.metric_id][0].value == row.value
        assert chart[row.metric_id][0].ts == "2026-08-31"


@pytest.mark.parametrize("builder,mid,display", [(iranwar, "brent_crude_usd_barrel", "iranwar_brent_spot"),
    (iranwar, "wti_crude_usd_barrel", "iranwar_wti_spot"),
    (fx, "gold_usd_oz", "fx_gold_usd_oz"), (fx, "usd_bdt_mid", "fx_usd_bdt_mid")])
def test_direct_quotes_keep_source_date(tmp_path, builder, mid, display):
    ctx = context(tmp_path, data={mid: 123.4}, observations={mid: observation(mid, 123.4)})
    card = next(m for m in builder.build(ctx).metrics if m.id == display)
    assert (card.value, card.as_of) == (123.4, date(2026, 9, 23))


@pytest.mark.parametrize("metadata", [None, {}, {"quality": "unavailable"}, {"as_of": "2026-09-26"},
    {"date_basis": "unknown"}, {"date_basis": "writer_confirmation"}, {"value": 99},
    {"metric_id": "other"}, {"captured_at": "bad"}, {"evidence": ""}])
def test_unknown_or_mismatched_quotes_never_inherit_a_date(tmp_path, metadata):
    mid = "brent_crude_usd_barrel"
    observations = None if metadata is None else {mid: observation(mid, 80, **metadata)}
    if metadata == {}:
        observations = {}
    ctx = context(tmp_path, data={mid: 80}, observations=observations,
                  rows=[HistoryRow(mid, TODAY, 80, "econdelta")])
    section = iranwar.build(ctx)
    assert not section.metrics
    assert section.freshness == "unavailable"


def test_legacy_fallback_preserves_entire_dated_history_record(tmp_path):
    mid = "brent_crude_usd_barrel"
    ctx = context(tmp_path, data={mid: 85}, rows=[HistoryRow(mid, TODAY, 80, "dated source",
                                                         date(2026, 9, 22))])
    card = iranwar.build(ctx).metrics[0]
    assert (card.value, card.as_of, card.source, card.stale) == (80, date(2026, 9, 22), "dated source", True)


def test_old_july_remittance_remains_july_final(tmp_path):
    ctx = context(tmp_path, rows=[HistoryRow("remit_monthly_mn", TODAY, 2820, "econdelta")],
                  monthly=[HistoryRow("remittance_usd_mn_monthly", date(2026, 7, 1), 2858.68, "bb")])
    card = remit.build(ctx).metrics[0]
    assert (card.value, card.as_of) == (2858.68, date(2026, 7, 31))
    assert "final" in card.source and "Jul 2026" in card.source


@pytest.mark.parametrize("release,period,expected", [("provisional", "2026-08-31", 2970),
    ("unknown", "2026-08-31", 2858.68), ("provisional", "2026-07-31", 2858.68),
    ("provisional", "2026-10-31", 2858.68)])
def test_remittance_selects_verified_period_then_release(tmp_path, release, period, expected):
    mid = "remit_monthly_mn"
    ctx = context(tmp_path, data={mid: 2970}, observations={mid: observation(mid, 2970, period,
        release_status=release, unit="USD million")},
        monthly=[HistoryRow("remittance_usd_mn_monthly", date(2026, 7, 1), 2858.68, "bb")])
    assert remit.build(ctx).metrics[0].value == expected


def test_remittance_note_survives_model_and_is_idempotent(tmp_path):
    mid = "remit_monthly_mn"
    ctx = context(tmp_path, data={mid: 2970}, observations={mid: observation(mid, 2970, "2026-08-31",
        release_status="provisional", unit="USD million")})
    raw = remit.build(ctx)
    final = BriefPayloadV6(brief=BriefV6(issue_no=1, volume=1, brief_date=TODAY), sections=[
        SectionV6(slug="remit", ord=11, title="Remittance", group_key="banking", metrics=[
            MetricV6(label="Monthly remittance", value="$2.97bn", sub="September final")])])
    sections = [{"slug": "remit", "metrics": [m.model_dump(mode="json") for m in raw.metrics]}]
    pipeline_v6._stamp_remittance_sub(final, sections)
    pipeline_v6._stamp_remittance_sub(final, sections)
    card = final.sections[0].metrics[0]
    assert card.sub.count("provisional") == 1
    assert "Aug 2026" in card.sub and "September" not in card.sub
    assert card.held_from == date(2026, 8, 31)


def test_unicode_minus_survives_diff_and_lens():
    assert _parse_numeric("−1.25%") == -1.25
    assert not _values_equal("−1.25%", "+1.25%")
    assert _values_equal(-1.25, "−1.25%")
    assert pipeline_v6._diff_value_to_sigma(-1.25, "−1.25%") == 0.0
    assert pipeline_v6._diff_value_to_sigma(-1.25, "+1.25%") == 1.0


@pytest.mark.parametrize("bucket,source,monthly,expected", [
    ("2026-08-01", None, True, "2026-08-31"),
    ("2026-09-01", None, True, None),
    ("2026-09-01", "2026-09-21", True, "2026-09-21"),
    ("2026-08-01", "2026-07-31", True, None),
    ("2026-08-01", "2026-09-30", True, None),
    ("2026-09-23", None, False, "2026-09-23"),
    ("2026-09-23", "2026-09-21", False, "2026-09-21"),
])
def test_observation_date_distinguishes_month_buckets_and_daily_evidence(bucket, source, monthly, expected):
    from brief.history import observation_date
    row = HistoryRow("series", date.fromisoformat(bucket), 1, "official",
                     date.fromisoformat(source) if source else None)
    got = observation_date(row, today=TODAY, monthly=monthly)
    assert got == (date.fromisoformat(expected) if expected else None)


def test_cpi_denied_month_cannot_escape_by_using_month_end():
    assert not is_official_cpi_point("cpi_p2p_nonfood_monthly", "2026-07-31", "econdelta_daily_cpi")


def test_shared_epb_contract_reaches_card_and_chart(tmp_path):
    from brief.chart_series_fetcher import fetch_fx_balance_monthly
    contract = json.loads((Path(__file__).parent / "fixtures/contracts/brief-observations-v1.json").read_text())
    entries = contract["monthly_contract"]["epb_evidence"]["rows"]
    august = next(r for r in entries if r["as_of"] == "2026-08-01")
    row = HistoryRow(august["metric_id"], date.fromisoformat(august["as_of"]), august["value"],
                     august["source"], date.fromisoformat(august["source_as_of"]))
    ctx = context(tmp_path, monthly=[row])
    card = next(m for m in fx.build(ctx).metrics if m.id == "fx_monthly_exports")
    point = fetch_fx_balance_monthly(ctx.history_monthly)[row.metric_id][0]
    assert (card.value, card.as_of) == (4.43, date(2026, 8, 31))
    assert (point.value, point.ts) == (4429.45, "2026-08-31")


def test_shared_producer_fiscal_conversion_preserves_bank_concept(tmp_path):
    from brief.builders import fiscal
    contract = json.loads((Path(__file__).parent / "fixtures/contracts/brief-observations-v1.json").read_text())
    case = next(c for c in contract["cases"] if c["case_id"] == "mei-deficit-financing-fy26")
    bank = next(r for r in case["expected_outputs"] if r["metric_id"] == "bank_borrowing_for_deficit_financing")
    domestic = next(r for r in case["expected_outputs"] if r["metric_id"] == "domestic_borrowing_for_budget_deficit")
    ctx = context(tmp_path, rows=[
        HistoryRow("fiscal_bank_borrow_trn", date.fromisoformat(bank["as_of"]), round(bank["value"] / 100000, 2), "BB"),
        HistoryRow("fiscal_govt_borrow_trn", date.fromisoformat(domestic["as_of"]), round(domestic["value"] / 100000, 2), "BB")])
    card = next(m for m in fiscal.build(ctx).metrics if m.id == "fiscal_govt_borrow_trn")
    assert (card.value, card.as_of) == (1.66, date(2026, 6, 30))


def test_remittance_does_not_relabel_billions_as_millions(tmp_path):
    mid = "remit_monthly_mn"
    ctx = context(tmp_path, data={mid: 2.97}, observations={mid: observation(mid, 2.97,
        "2026-08-31", unit="USD billion", release_status="provisional")})
    assert remit.build(ctx).metrics == []


def test_held_quote_keeps_its_date_and_cannot_read_fresh(tmp_path):
    mid = "brent_crude_usd_barrel"
    ctx = context(tmp_path, data={mid: 80}, observations={mid: observation(mid, 80,
        "2026-09-24", quality="held")})
    card = iranwar.build(ctx).metrics[0]
    from brief.cadence import metric_freshness
    assert card.stale and card.as_of == date(2026, 9, 24)
    assert metric_freshness(card, today=TODAY) != "fresh"


QUOTE_CASES = [
    (iranwar, "brent_crude_usd_barrel", "iranwar_brent_spot", "USD/barrel", "USD/bbl"),
    (iranwar, "wti_crude_usd_barrel", "iranwar_wti_spot", "USD/barrel", "USD/bbl"),
    (fx, "gold_usd_oz", "fx_gold_usd_oz", "USD/oz", "USD/oz"),
    (fx, "usd_bdt_mid", "fx_usd_bdt_mid", "BDT", "BDT"),
]


@pytest.mark.parametrize("builder,mid,display,source_unit,display_unit", QUOTE_CASES)
def test_quotes_accept_actual_producer_units(tmp_path, builder, mid, display, source_unit, display_unit):
    ctx = context(tmp_path, data={mid: 123.4}, observations={mid: observation(mid, 123.4, unit=source_unit)})
    card = next(m for m in builder.build(ctx).metrics if m.id == display)
    assert (card.value, card.unit) == (123.4, display_unit)


@pytest.mark.parametrize("builder,mid,display,source_unit,display_unit", QUOTE_CASES)
@pytest.mark.parametrize("bad_unit", ["USD thousand/oz", None, "", "unknown"])
def test_quotes_reject_wrong_scale_or_missing_units(tmp_path, builder, mid, display, source_unit, display_unit, bad_unit):
    item = observation(mid, 3.31, unit=bad_unit)
    if bad_unit is None:
        item.pop("unit")
    ctx = context(tmp_path, data={mid: 3.31}, observations={mid: item})
    assert display not in {m.id for m in builder.build(ctx).metrics}


@pytest.mark.parametrize("bad_value", [True, float("nan"), float("inf"), -float("inf"), 10**400],
                         ids=["bool", "nan", "inf", "negative-inf", "overflow-int"])
@pytest.mark.parametrize("path", ["snapshot", "history", "history-http"])
def test_bad_gold_number_does_not_erase_valid_fx_cards(tmp_path, bad_value, path):
    from brief.history import MetricHistoryClient
    from urllib.parse import parse_qs, urlparse
    data = {"usd_bdt_mid": 123.4}
    observations = {"usd_bdt_mid": observation("usd_bdt_mid", 123.4, unit="BDT")}
    rows = [HistoryRow("gross_reserves_usd_bn", date(2026, 8, 31), 35, "BB")]
    monthly = [HistoryRow("exports_usd_mn_monthly", date(2026, 8, 1), 4000, "EPB"),
               HistoryRow("imports_usd_mn_monthly", date(2026, 8, 1), 6000, "BB")]
    if path == "snapshot":
        data["gold_usd_oz"] = bad_value
        observations["gold_usd_oz"] = observation("gold_usd_oz", bad_value, unit="USD/oz")
    else:
        rows.append(HistoryRow("gold_usd_oz", TODAY, bad_value, "dated source", date(2026, 9, 23)))
    ctx = context(tmp_path, data=data, observations=observations, rows=rows, monthly=monthly)
    if path == "history-http":
        class Http:
            def get(self, url, **kwargs):
                mid = parse_qs(urlparse(url).query)["metric_id"][0][3:]
                row = next((r for r in rows if r.metric_id == mid), None)
                return 200, [{"metric_id": mid, "as_of": row.as_of.isoformat(), "value": row.value,
                              "source": row.source, "source_as_of": row.source_as_of.isoformat()
                              if row.source_as_of else None}] if row else []
        ctx = BuilderContext(ctx.snapshot, MetricHistoryClient(url="https://fixture", service_key="test", http=Http()),
                             TODAY, history_monthly=ctx.history_monthly)
    cards = {m.id: m.value for m in fx.build(ctx).metrics}
    assert cards == {"fx_usd_bdt_mid": 123.4, "fx_gross_reserves": 35,
                     "fx_monthly_exports": 4, "fx_trade_gap": -2}


@pytest.mark.parametrize("daily_source_date", [None, date(2026, 6, 30)])
def test_daily_cpi_restamp_cannot_outrank_august_print(tmp_path, daily_source_date):
    ctx = context(tmp_path, rows=[HistoryRow("food_inflation", date(2026, 9, 24), 7, "econdelta", daily_source_date)],
                  monthly=[HistoryRow("cpi_p2p_food_monthly", date(2026, 8, 1), 6, "econdelta_daily_cpi")])
    card = next(m for m in macro.build(ctx).metrics if m.id == "cpi_p2p_food_monthly")
    assert (card.value, card.as_of) == (6, date(2026, 8, 31))


def test_daily_cpi_without_evidenced_period_is_unavailable(tmp_path):
    ctx = context(tmp_path, rows=[HistoryRow("food_inflation", date(2026, 9, 24), 7, "econdelta")])
    assert next(m for m in macro.build(ctx).metrics if m.id == "cpi_p2p_food_monthly").value is None


def test_daily_cpi_can_use_matching_snapshot_period(tmp_path):
    ctx = context(tmp_path, data={"food_inflation": 7},
                  observations={"food_inflation": observation("food_inflation", 7, "2026-06-30", unit="%")},
                  rows=[HistoryRow("food_inflation", date(2026, 9, 24), 7, "econdelta")])
    card = next(m for m in macro.build(ctx).metrics if m.id == "cpi_p2p_food_monthly")
    assert (card.value, card.as_of) == (7, date(2026, 6, 30))


@pytest.mark.parametrize("slug,mid", [("macro", "cpi_12m_avg_monthly"), ("remit", "remittance_usd_mn_monthly"),
    ("bb", "gross_reserves_usd_bn_monthly"), ("fx", "exports_usd_mn_monthly"), ("fiscal", "nbr_revenue_monthly_cr")])
def test_historical_issue_cutoff_reaches_chart_and_editor_summary(monkeypatch, slug, mid):
    from datetime import datetime, timezone
    from urllib.parse import parse_qs, urlparse
    import brief.chart_series_fetcher as fetchers
    # The computer has reached September, but this issue is from mid-August.
    monkeypatch.setattr(fetchers, "now_bdt", lambda: datetime(2026, 9, 25, tzinfo=timezone.utc))
    class Http:
        def get(self, url, **kwargs):
            query = parse_qs(urlparse(url).query)
            if "metric_history_monthly" in url and mid in query.get("metric_id", [""])[0]:
                return 200, [{"metric_id": mid, "as_of": "2026-08-01", "value": 8, "source": "econdelta_daily_cpi"},
                             {"metric_id": mid, "as_of": "2026-07-01", "value": 7, "source": "econdelta_daily_cpi"}]
            return 200, []
    cutoff = date(2026, 8, 15)
    kwargs = dict(today=cutoff, http=Http(), supabase_url="https://fixture", service_key="test")
    final = BriefPayloadV6(brief=BriefV6(issue_no=1, volume=1, brief_date=cutoff), sections=[
        SectionV6(slug=slug, ord=1, title=slug, group_key="banking")])
    pipeline_v6._stamp_chart_series(final, **kwargs)
    assert [(p.ts, p.value) for p in final.sections[0].series] == [("2026-07-31", 7)]
    summary = pipeline_v6._fetch_series_summaries(**kwargs)
    assert summary[slug][mid]["last_ts"] == "2026-07-31"
    assert summary[slug][mid]["last_value"] == 7


@pytest.mark.parametrize("mid", ["brent_crude_usd_barrel", "wti_crude_usd_barrel"])
def test_oil_accepts_compatible_bbl_unit_alias(tmp_path, mid):
    ctx = context(tmp_path, data={mid: 80}, observations={mid: observation(mid, 80, unit="USD/bbl")})
    card = iranwar.build(ctx).metrics[0]
    assert (card.value, card.unit) == (80, "USD/bbl")


@pytest.mark.parametrize("snapshot_overrides,expected_value,expected_date", [
    ({}, 6.0, date(2026, 8, 31)),
    ({"quality": "unavailable"}, 6.5, date(2026, 7, 31)),
    ({"date_basis": "unknown"}, 6.5, date(2026, 7, 31)),
    ({"unit": "unknown"}, 6.5, date(2026, 7, 31)),
])
def test_cpi_compares_newer_dated_history_without_reviving_rejected_snapshot(
    tmp_path, snapshot_overrides, expected_value, expected_date,
):
    item = observation("food_inflation", 7.0, "2026-06-30", unit="%")
    item.update(snapshot_overrides)
    ctx = context(tmp_path, data={"food_inflation": 7.0}, observations={"food_inflation": item},
                  rows=[HistoryRow("food_inflation", date(2026, 9, 24), 6.0,
                                   "econdelta", date(2026, 8, 31))],
                  monthly=[HistoryRow("cpi_p2p_food_monthly", date(2026, 7, 1), 6.5,
                                      "econdelta_daily_cpi")])
    card = next(m for m in macro.build(ctx).metrics if m.id == "cpi_p2p_food_monthly")
    assert (card.value, card.as_of) == (expected_value, expected_date)


# ── Policy-corridor writer confirmations: shared allowlist and date provenance ──
CONTRACT = Path(__file__).parent / "fixtures/contracts/brief-observations-v1.json"
CORRIDOR_CARD_IDS = {"bb_policy_rate", "bb_sdf", "bb_slf"}


def corridor_snapshot(tmp_path):
    """Load EconDelta's own contract records exactly as the producer serialises them."""
    contract = json.loads(CONTRACT.read_text())["writer_confirmation_contract"]
    records = {r["expected"]["metric_id"]: r["expected"] for r in contract["records"]}
    receipt = {"status": "ok", "attempted_at": contract["aggregate_captured_at"]}
    path = tmp_path / "corridor.json"
    path.write_text(json.dumps({
        "updated_at": contract["aggregate_captured_at"], "sources_status": POLLED_UPSTREAM,
        "data": {mid: r["value"] for mid, r in records.items()}, "observations": records,
        "write_status": {"daily": receipt, "monthly": receipt}}))
    return contract, load_snapshot(path), records


def corridor_history_rows(contract):
    """metric_history rows exactly as EconDelta's daily writer stores the contract records
    (EconDelta's tests/test_review_contract_fixtures.py proves the producer writes these)."""
    return [HistoryRow(row["metric_id"], date.fromisoformat(row["as_of"]), row["value"], row["source"])
            for row in (record["metric_history_row"] for record in contract["records"])]


def test_writer_confirmation_allowlist_is_pinned_by_the_shared_contract(tmp_path):
    from brief.econdelta import WRITER_CONFIRMATION_IDS
    contract, snap, records = corridor_snapshot(tmp_path)
    assert sorted(contract["metric_ids"]) == sorted(WRITER_CONFIRMATION_IDS)
    assert sorted(records) == sorted(WRITER_CONFIRMATION_IDS)
    for mid, record in records.items():
        confirmation = snap.writer_confirmation(mid, today=TODAY)
        assert (confirmation.value, confirmation.confirmed_on.isoformat()) == (record["value"], record["as_of"])
        assert snap.observation(mid, today=TODAY) is None


def test_live_corridor_card_is_dated_by_the_producers_row_only_as_a_liveness_clock(tmp_path):
    """Real producer data, not an idealised split: EconDelta stores the confirmation date
    itself as metric_history.as_of, so the live card's internal as_of IS the writer's
    confirmation day. It stays an event-cadence liveness clock (landmine 24): not stale,
    and no age/held note reaches the editor while the writer keeps confirming. Only the
    outage fallback is dated by the MPC decision. Whether the live card should show
    _LAST_MPC_DECISION instead is an OPEN owner decision; this pins today's behaviour so
    that any change is deliberate."""
    from datetime import datetime, timezone
    from brief.builders import bb
    from brief.readiness import assess
    from brief.vintage import period_label
    contract, snap, records = corridor_snapshot(tmp_path)
    rows = corridor_history_rows(contract)
    (confirmation_day,) = {date.fromisoformat(r["as_of"]) for r in records.values()}
    assert {(row.metric_id, row.value) for row in rows} == {(m, r["value"]) for m, r in records.items()}
    assert {row.as_of for row in rows} == {confirmation_day} != {bb._LAST_MPC_DECISION}
    for history, card_date, stale in ((History(rows), confirmation_day, False),
                                      (None, bb._LAST_MPC_DECISION, True)):
        section = bb.build(BuilderContext(snap, history, TODAY))
        cards = [m for m in section.metrics if m.id in CORRIDOR_CARD_IDS]
        assert len(cards) == 3
        assert {(c.as_of, c.cadence, c.stale) for c in cards} == {(card_date, "event", stale)}
        raw = [m for m in pipeline_v6._to_v6_raw([section], today=TODAY)[0]["metrics"]
               if m["id"] in CORRIDOR_CARD_IDS]
        assert {m["period"] for m in raw} == {period_label(card_date, "event")}
        # A fresh corridor card carries no vintage to the editor; a fallback carries its MPC one.
        assert {(m["vintage"] or {}).get("as_of") for m in raw} == {
            card_date.isoformat() if stale else None}
        readiness = assess(snap, persisted_rows=section.metrics,
                           now=datetime(2026, 9, 25, 2, tzinfo=timezone.utc))
        assert (readiness.state, readiness.reasons) == ("ready", ())


@pytest.mark.parametrize("verdict", ["pass", "revise"])
@pytest.mark.parametrize("live", [True, False], ids=["live-history", "history-outage"])
def test_model_cannot_publish_a_held_over_date_on_a_corridor_card(tmp_path, monkeypatch, live, verdict):
    """editor_v6.txt forbids the model to set held_from (system-stamped). If a model date
    survived, a fresh corridor card would publish the writer's confirmation day as a
    held-over "As of" footer (Section.tsx). Through the whole publish sequence, the fake
    Editor and Sub-editor both stamp that day: a fresh card publishes no held date, and
    an outage fallback publishes only its MPC decision date. The Sub-editor must review
    those same held dates, never the Editor's."""
    from brief.builders import bb
    from brief.publication_identity import PublishIdentity
    contract, snap, records = corridor_snapshot(tmp_path)
    history = History(corridor_history_rows(contract)) if live else None
    section = bb.build(BuilderContext(snap, history, TODAY))
    (confirmation_day,) = {r["as_of"] for r in records.values()}
    slug, ord_v6, group = pipeline_v6.V5_TO_V6["bb"]
    model_brief = {"brief": {"issue_no": 1, "volume": 1, "brief_date": TODAY.isoformat()},
                   "sections": [{"slug": slug, "ord": ord_v6, "title": "BB", "group_key": group,
                                 "metrics": [{"label": c.label, "value": f"{c.value:.2f}%",
                                              "held_from": confirmation_day}
                                             for c in section.metrics if c.id in CORRIDOR_CARD_IDS]}]}
    review = {"verdict": verdict, "issues": []}
    if verdict == "revise":
        review["revised_brief"] = model_brief
    reviewed = []

    def fake_model(*, label, input_obj, **kw):
        if label == "editor_v6":
            return model_brief
        reviewed.append(input_obj["editor_output"])
        return review

    fakes = {"_alert": lambda message: None, "fetch_previous_brief": lambda: None,
             "fetch_recent_news": lambda **kw: [], "fetch_metric_definitions": lambda: [],
             "_fetch_series_summaries": lambda *a, **kw: {},
             "_stamp_chart_series": lambda *a, **kw: None, "_call_with_retries": fake_model}
    for name, fake in fakes.items():
        monkeypatch.setattr(pipeline_v6, name, fake)
    published = []
    monkeypatch.setattr(pipeline_v6, "publish_brief", lambda payload, **kw: published.append(payload) or "local")
    assert pipeline_v6.run_publish([section], TODAY, expected_identity=PublishIdentity(1, TODAY)) == "local"
    held = None if live else bb._LAST_MPC_DECISION
    assert {m["held_from"] for s in reviewed[0]["sections"] if s["slug"] == slug
            for m in s["metrics"]} == {held and held.isoformat()}
    cards = [m for s in published[0].sections if s.slug == slug for m in s.metrics]
    assert sorted(c.label for c in cards) == ["Policy Rate", "SDF", "SLF"]
    assert {c.held_from for c in cards} == {held}


# ── One real EconDelta aggregate run through every real builder and the readiness check ──
BRIEF_RUN = datetime(2026, 9, 25, 2, tzinfo=timezone.utc)  # the 08:00 BDT publish
# Production's official July remittance final (metric_history_monthly, captured 25 Sep 2026
# 14:49 BDT). remit.py prefers it to the August flash, whose WSEI column carries no P/R mark.
OFFICIAL_REMITTANCE = HistoryRow("remittance_usd_mn_monthly", date(2026, 7, 1), 2858.68,
                                 "bb_wageremitance", date(2026, 7, 1))
BOUND_CARDS = {  # builder card -> the accepted record it displays
    "fx_gold_usd_oz": "gold_usd_oz", "iranwar_brent_spot": "brent_crude_usd_barrel",
    "iranwar_wti_spot": "wti_crude_usd_barrel", "dsex": "dsex",
    # The day's rate, dated by the Dhaka calendar and captured before UTC midnight (fix #12).
    "fx_usd_bdt_mid": "usd_bdt_mid",
    **{mid: mid for mid in ("tbond_tbill_91d", "tbond_tbill_182d", "tbond_tbill_364d", "tbond_bond_5y",
                            "tbond_bond_10y", "banking_npl_pct", "banking_car_pct", "fiscal_nbr_collected_trn")},
    # The public id kept its name when the card became BANK-only borrowing (fiscal.py).
    "fiscal_govt_borrow_trn": "fiscal_bank_borrow_trn",
}


class Tables:
    """metric_history / metric_history_monthly as PostgREST serves them: newest as_of first."""

    def __init__(self, daily=(), monthly=()):
        self.tables = {"metric_history": sorted(daily, key=lambda r: r.as_of, reverse=True),
                       "metric_history_monthly": sorted(monthly, key=lambda r: r.as_of, reverse=True)}

    def get_latest(self, metric_id, *, table="metric_history"):
        return next((r for r in self.tables[table] if r.metric_id == metric_id), None)

    def get_at_or_before(self, metric_id, as_of, *, table="metric_history"):
        return next((r for r in self.tables[table] if r.metric_id == metric_id and r.as_of <= as_of), None)

    def get_history_window(self, metric_ids, **kwargs):
        rows = self.tables["metric_history"]
        return {mid: [r.value for r in reversed(rows) if r.metric_id == mid] for mid in metric_ids}


def aggregate_run(tmp_path, **observation_changes):
    """latest.json and the metric_history rows of the contract's one real aggregate run."""
    contract = json.loads(CONTRACT.read_text())
    binding, corridor = contract["builder_binding_contract"], contract["writer_confirmation_contract"]
    records = {**{mid: r["observation"] for mid, r in binding["records"].items()},
               **{r["expected"]["metric_id"]: r["expected"] for r in corridor["records"]}}
    records = {mid: {**r, **observation_changes.get(mid, {})} for mid, r in records.items()}
    stored = [r["metric_history_row"] for r in [*binding["records"].values(), *corridor["records"]]
              if r["metric_history_row"]]
    receipt = {"status": "ok", "attempted_at": binding["aggregate_captured_at"]}
    # A current producer also reports its CPI/M2 source polls (R2 fix 5); without them readiness
    # degrades for unknown liveness and would mask what these tests say about the run itself.
    sources_status = {**binding["sources_status"], **POLLED_UPSTREAM}
    path = tmp_path / "latest.json"
    path.write_text(json.dumps({
        "updated_at": binding["aggregate_captured_at"], "sources_status": sources_status,
        "data": {mid: r["value"] for mid, r in records.items()}, "observations": records,
        "write_status": {"daily": receipt, "monthly": receipt}}))
    rows = [HistoryRow(r["metric_id"], date.fromisoformat(r["as_of"]), r["value"], r["source"]) for r in stored]
    return load_snapshot(path), rows


def gathered_sections(monkeypatch, snap, daily):
    """Every section the real builders produce (brief.pipeline.gather) from this snapshot and history."""
    from brief import pipeline
    from brief.builders import dse
    history = Tables(daily, [OFFICIAL_REMITTANCE])
    monkeypatch.setattr(pipeline, "_build_history", lambda cfg: history)
    monkeypatch.setattr(dse, "scrape_breadth", lambda *a, **k: None)
    monkeypatch.setattr(dse, "scrape_sector_heat", lambda *a, **k: None)
    return pipeline.gather(pipeline.PipelineConfig(today=TODAY, enable_headlines=False),
                           snapshot_override=snap)


def gathered_cards(monkeypatch, snap, daily):
    """Every card the real builders produce (brief.pipeline.gather) from this snapshot and history."""
    return [m for s in gathered_sections(monkeypatch, snap, daily) for m in s.metrics]


def contradictions(result):
    return [r for r in result.reasons if "disagree" in r or "inconsistent" in r]


def held_readings(snap) -> list[str]:
    """The run's own held records (producer quality "held"), as readiness must report them."""
    return sorted(f"{mid}: held reading from {obs['as_of']}" for mid, obs in snap.observations.items()
                  if isinstance(obs, dict) and obs.get("quality") == "held")


def test_one_real_aggregate_run_through_every_builder_is_not_held(tmp_path, monkeypatch):
    """Source labels ("DSE" for dse_market, "BB" for BB auction cut-offs and FSR ratios, "NBR"
    for WSEI tax revenue), the "BDT trn" unit spelling and the bank-only borrowing card are
    how legitimate producer records reach the cards; none of them is a contradiction."""
    from brief.readiness import assess
    snap, rows = aggregate_run(tmp_path)
    cards = {m.id: m for m in gathered_cards(monkeypatch, snap, rows)}
    for card_id, mid in BOUND_CARDS.items():  # the comparisons below have real material
        observation = snap.observations[mid]
        assert (cards[card_id].value, cards[card_id].as_of.isoformat()) == (
            observation["value"], observation["as_of"]), card_id
    remittance = cards["remit_monthly_mn"]
    assert (remittance.value, remittance.as_of) == (2858.68, date(2026, 7, 1))
    result = assess(snap, persisted_rows=cards.values(), now=BRIEF_RUN)
    assert contradictions(result) == []
    assert result.state == "degraded"  # held monthly readings, honestly reported
    assert sorted(result.reasons) == held_readings(snap) != []  # and nothing but them


def test_the_days_usd_bdt_card_is_printed_after_the_0256_bdt_aggregate_run(tmp_path, monkeypatch):
    """The run captured bb_forex at 01:35 BDT (the previous UTC day) with the Dhaka date
    2026-09-25. That reading is the day's rate: the producer accepts and stores it, and the
    fx card prints it, so readiness does not report USD/BDT as unavailable."""
    from brief.readiness import assess
    snap, rows = aggregate_run(tmp_path)
    assert snap.observations["usd_bdt_mid"]["quality"] == "verified"
    assert any(r.metric_id == "usd_bdt_mid" and r.as_of == date(2026, 9, 25) for r in rows)
    cards = {m.id: m for m in gathered_cards(monkeypatch, snap, rows)}
    card = cards["fx_usd_bdt_mid"]
    assert (card.value, card.as_of, card.source, card.stale) == (123.22, date(2026, 9, 25), "bb_forex", False)
    result = assess(snap, persisted_rows=cards.values(), now=BRIEF_RUN)
    assert "usd_bdt_mid" not in result.unavailable
    assert contradictions(result) == []


def test_the_days_usd_bdt_card_survives_every_model_pass_and_publishes_its_stamped_rate(tmp_path, monkeypatch):
    """R2 fix 7b round 1 (controller finding C4). The same real 02:56 BDT run, now through the
    whole publish sequence with fake Editor and Sub-editor: the fx builder's USD/BDT card
    survives reconciliation and publishes the accepted 123.22 in the house format, whatever
    number the model wrote; a fresh card carries no held date."""
    from brief.publication_identity import PublishIdentity
    snap, rows = aggregate_run(tmp_path)
    (fx_section,) = [s for s in gathered_sections(monkeypatch, snap, rows) if s.id == "fx"]
    slug, ord_v6, group = pipeline_v6.V5_TO_V6["fx"]
    model_brief = {"brief": {"issue_no": 1, "volume": 1, "brief_date": TODAY.isoformat()},
                   "sections": [{"slug": slug, "ord": ord_v6, "title": "FX", "group_key": group,
                                 "metrics": [{"label": "USD/BDT mid", "value": "Tk 999 ▲"},
                                             {"label": "Gold", "value": "$4,329/oz"}]}]}
    fakes = {"_alert": lambda message: None, "fetch_previous_brief": lambda: None,
             "fetch_recent_news": lambda **kw: [], "fetch_metric_definitions": list,
             "_fetch_series_summaries": lambda *a, **kw: {}, "_stamp_chart_series": lambda *a, **kw: None,
             "_call_with_retries": lambda *, label, **kw: (
                 model_brief if label == "editor_v6" else {"verdict": "pass", "issues": []})}
    for name, fake in fakes.items():
        monkeypatch.setattr(pipeline_v6, name, fake)
    published = []
    monkeypatch.setattr(pipeline_v6, "publish_brief", lambda payload, **kw: published.append(payload) or "local")
    assert pipeline_v6.run_publish([fx_section], TODAY, expected_identity=PublishIdentity(1, TODAY)) == "local"
    cards = {m.label: m for s in published[0].sections if s.slug == slug for m in s.metrics}
    assert (cards["USD/BDT mid"].value, cards["USD/BDT mid"].held_from) == ("123.22", None)
    assert cards["Gold"].value == "$4,328.9/oz"  # the float32 feed's own decimal, no noise


@pytest.mark.parametrize("row,mid", [
    # Restamps R1 left unresolved: the card would print a FY26 total as 24 Sep 2026.
    (HistoryRow("fiscal_nbr_collected_trn", date(2026, 9, 24), 4.15, "EconDelta"), "fiscal_nbr_collected_trn"),
], ids=["restamped-history"])
def test_production_history_rows_that_contradict_the_accepted_record_still_hold(tmp_path, monkeypatch, row, mid):
    """Exact production rows (C/r1-repaired-snapshot) newer than the accepted record."""
    from brief.readiness import assess
    snap, rows = aggregate_run(tmp_path)
    result = assess(snap, persisted_rows=gathered_cards(monkeypatch, snap, [*rows, row]), now=BRIEF_RUN)
    assert result.state == "hold"
    assert contradictions(result) == [f"{mid}: builder and accepted observation disagree"]


# The exact production override row (media_review id 9, C/r1-repaired-snapshot): an approved
# Daily Star figure EconDelta's _apply_media_overrides writes after the normal upsert.
NPL_PRESS = HistoryRow("banking_npl_pct", date(2026, 6, 30), 32.78, "media-approved:thedailystar")


def test_an_owner_approved_press_override_card_is_accepted_and_names_its_outlet(tmp_path, monkeypatch):
    """DELIBERATE, OWNER-APPROVED POLICY CHANGE (owner decision (c), 26 Sep 2026 BDT). This
    production row used to HOLD every publish, because the card printed it as "BB" and so could
    not show where the figure came from. The card now names the approved outlet, and readiness
    accepts it because the card's value, date and source are exactly the press row the banking
    builder read. The accepted record (BB FSR 35.73 @ 2025-09-30) is older, so this is the
    newer approved figure, not a contradiction."""
    from brief.readiness import assess
    snap, rows = aggregate_run(tmp_path)
    cards = {m.id: m for m in gathered_cards(monkeypatch, snap, [*rows, NPL_PRESS])}
    npl = cards["banking_npl_pct"]
    assert (npl.value, npl.as_of, npl.source) == (32.78, date(2026, 6, 30), "via The Daily Star (approved)")
    result = assess(snap, persisted_rows=cards.values(), now=BRIEF_RUN)
    assert contradictions(result) == []
    assert result.state == "degraded"  # the same held monthly readings as the plain run
    assert sorted(result.reasons) == held_readings(snap) != []


# R2 fix H2: EconDelta's media_overrides receipt for that same override once its exact
# readback confirms both written ids (EconDelta tests/test_media_override_readback.py
# CONFIRMED_NPL_RECEIPT), and the receipt when the readback finds one of them missing.
CONFIRMED_NPL_OVERRIDE = {"status": "ok", "confirmed_rows": 2, "failures": [],
                          "reason": "2 row(s) written and confirmed by exact readback"}
MISSING_NPL_OVERRIDE = {"status": "failed", "confirmed_rows": 1,
                        "reason": "readback failed (readback missing): banking_npl_pct 2026-06-30; "
                                  "1 row(s) written and confirmed by exact readback",
                        "failures": [{"operation": "readback", "category": "readback missing",
                                      "detail": "banking_npl_pct 2026-06-30"}]}


@pytest.mark.parametrize("receipt,extra", [
    (CONFIRMED_NPL_OVERRIDE, []),
    (MISSING_NPL_OVERRIDE, ["approved press override persistence failed: " + MISSING_NPL_OVERRIDE["reason"]]),
], ids=["confirmed by exact readback", "readback missing"])
def test_an_active_override_changes_readiness_only_when_its_readback_fails(tmp_path, monkeypatch, receipt, extra):
    """The real aggregate run with the production press row: a confirmed override receipt
    adds nothing to the plain run's reasons; a failed readback adds exactly its own reason."""
    from dataclasses import replace
    from brief.readiness import assess
    snap, rows = aggregate_run(tmp_path)
    stamped = {**receipt, "attempted_at": snap.write_status["daily"]["attempted_at"]}
    snap = replace(snap, write_status={**snap.write_status, "media_overrides": stamped})
    result = assess(snap, persisted_rows=gathered_cards(monkeypatch, snap, [*rows, NPL_PRESS]), now=BRIEF_RUN)
    assert contradictions(result) == []
    assert sorted(result.reasons) == sorted([*held_readings(snap), *extra])
    assert result.state == "degraded"  # the contract run's own held monthly readings, never a hold


PRESS_DEPARTURES = [  # a press-bound card whose printed field is no longer the press row
    ("source", "BB"), ("source", "via The Business Standard (approved)"),
    ("value", 32.77), ("as_of", date(2026, 3, 31)), ("unit", "BDT crore"),
]


@pytest.mark.parametrize("field,altered", PRESS_DEPARTURES, ids=[f"{f}-{v}" for f, v in PRESS_DEPARTURES])
def test_a_press_override_card_that_departs_from_its_press_row_holds(tmp_path, monkeypatch, field, altered):
    from brief.readiness import assess
    snap, rows = aggregate_run(tmp_path)
    cards = [m.model_copy(update={field: altered}) if m.id == "banking_npl_pct" else m
             for m in gathered_cards(monkeypatch, snap, [*rows, NPL_PRESS])]
    result = assess(snap, persisted_rows=cards, now=BRIEF_RUN)
    assert result.state == "hold"
    assert contradictions(result) == ["banking_npl_pct: builder and accepted observation disagree"]


def test_a_press_figure_older_than_the_accepted_record_holds(tmp_path, monkeypatch):
    """History lost the official FSR row, so the builder falls back to an older approved press
    figure while the accepted record is newer: a real contradiction, never hidden by approval."""
    from brief.readiness import assess
    snap, rows = aggregate_run(tmp_path)
    older_press = HistoryRow("banking_npl_pct", date(2025, 6, 30), 30.12, "media-approved:thedailystar")
    daily = [r for r in rows if r.metric_id != "banking_npl_pct"] + [older_press]
    result = assess(snap, persisted_rows=gathered_cards(monkeypatch, snap, daily), now=BRIEF_RUN)
    assert result.state == "hold"
    assert contradictions(result) == ["banking_npl_pct: builder and accepted observation disagree"]


def test_a_press_label_the_builder_did_not_bind_to_a_press_row_holds(tmp_path, monkeypatch):
    """Only the builder's own read of a media-approved row vouches for a press label."""
    from brief.readiness import assess
    snap, rows = aggregate_run(tmp_path)
    cards = [m.model_copy(update={"source": "via The Daily Star (approved)", "value": 32.78,
                                  "as_of": date(2026, 6, 30)}) if m.id == "banking_npl_pct" else m
             for m in gathered_cards(monkeypatch, snap, rows)]
    assert all(m.press_override is None for m in cards)
    result = assess(snap, persisted_rows=cards, now=BRIEF_RUN)
    assert result.state == "hold"
    assert contradictions(result) == ["banking_npl_pct: builder and accepted observation disagree"]


ALTERED_CARDS = [  # (card, altered field, altered value)
    ("iranwar_brent_spot", "value", 98.33), ("iranwar_brent_spot", "as_of", date(2026, 9, 22)),
    ("iranwar_brent_spot", "unit", "USD/mmbtu"), ("iranwar_brent_spot", "source", "wti_crude"),
    ("fx_gold_usd_oz", "value", 4329.0), ("fx_gold_usd_oz", "source", "bb_forex"),
    ("dsex", "value", 5540.3), ("dsex", "as_of", date(2026, 9, 21)), ("dsex", "source", "BB"),
    ("tbond_tbill_91d", "as_of", date(2026, 9, 14)), ("tbond_tbill_91d", "source", "DSE"),
    ("fiscal_govt_borrow_trn", "value", 1.65), ("fiscal_govt_borrow_trn", "as_of", date(2026, 5, 31)),
    ("fiscal_govt_borrow_trn", "unit", "BDT crore"), ("fiscal_govt_borrow_trn", "source", "NBR"),
    ("fiscal_nbr_collected_trn", "unit", "BDT bn"), ("fiscal_nbr_collected_trn", "source", "BB"),
    ("banking_npl_pct", "value", 32.78),
    ("fx_usd_bdt_mid", "value", 123.25), ("fx_usd_bdt_mid", "as_of", date(2026, 9, 24)),
]


@pytest.mark.parametrize("card_id,field,altered", ALTERED_CARDS,
                         ids=[f"{c}-{f}" for c, f, _ in ALTERED_CARDS])
def test_a_card_that_departs_from_its_accepted_record_holds(tmp_path, monkeypatch, card_id, field, altered):
    from brief.readiness import assess
    snap, rows = aggregate_run(tmp_path)
    cards = [m.model_copy(update={field: altered}) if m.id == card_id else m
             for m in gathered_cards(monkeypatch, snap, rows)]
    result = assess(snap, persisted_rows=cards, now=BRIEF_RUN)
    assert result.state == "hold"
    assert contradictions(result) == [f"{BOUND_CARDS[card_id]}: builder and accepted observation disagree"]


@pytest.mark.parametrize("mid", ["dsex", "tbond_tbill_91d", "banking_car_pct", "fiscal_nbr_collected_trn",
                                 "fiscal_bank_borrow_trn"])
def test_a_display_label_only_stands_for_its_own_producer_source(tmp_path, monkeypatch, mid):
    """A quarantine recovery from an undated legacy archive is source "archive"; the card's
    label ("DSE", "BB", "NBR") does not vouch for that record."""
    from brief.readiness import assess
    snap, rows = aggregate_run(tmp_path, **{mid: {"source": "archive"}})
    result = assess(snap, persisted_rows=gathered_cards(monkeypatch, snap, rows), now=BRIEF_RUN)
    assert result.state == "hold"
    assert contradictions(result) == [f"{mid}: builder and accepted observation disagree"]


def _named(publisher):  # remit.py's own card, relabelled as another publisher's figure
    return lambda card: card.model_copy(update={"source": card.source.replace("BB · ", f"{publisher} · ", 1)})


@pytest.mark.parametrize("flash_release,printed,mislabel", [
    # The real August flash carries no P/R mark, so remit.py prints the official July final; a card
    # printing that flash as "provisional" carries a release status no producer record states.
    ("unknown", "BB · Jul 2026, final", lambda card: card.model_copy(update={
        "value": 2970.0, "as_of": date(2026, 8, 31), "source": "BB · Aug 2026, provisional"})),
    ("unknown", "BB · Jul 2026, final", _named("The Daily Star")),
    ("provisional", "BB · Aug 2026, provisional", _named("The Daily Star")),
], ids=["unmarked-flash-called-provisional", "official-final-under-another-publisher",
        "flash-under-another-publisher"])
def test_a_remittance_card_with_an_invented_status_or_publisher_holds(tmp_path, monkeypatch, flash_release,
                                                                      printed, mislabel):
    from brief.readiness import assess
    snap, rows = aggregate_run(tmp_path, remit_monthly_mn={"release_status": flash_release})
    cards = gathered_cards(monkeypatch, snap, rows)
    (card,) = [m for m in cards if m.id == "remit_monthly_mn"]
    assert card.source.startswith(printed)  # the real builder's card, which is not held
    assert contradictions(assess(snap, persisted_rows=cards, now=BRIEF_RUN)) == []
    result = assess(snap, persisted_rows=[mislabel(m) if m is card else m for m in cards], now=BRIEF_RUN)
    assert result.state == "hold"
    assert contradictions(result) == ["remit_monthly_mn: builder and accepted observation disagree"]
