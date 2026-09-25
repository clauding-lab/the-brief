"""Consumer regressions driven by source dates, never collection clocks."""
from datetime import date
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

TODAY = date(2026, 9, 25)


class History:
    def __init__(self, rows=()):
        self.rows = {r.metric_id: r for r in rows}

    def get_latest(self, metric_id, **kwargs):
        return self.rows.get(metric_id)

    def get_history_window(self, metric_ids, **kwargs):
        return {mid: [self.rows[mid]] if mid in self.rows else [] for mid in metric_ids}


def snapshot(tmp_path, data, observations=None):
    payload = {"updated_at": "2026-09-25T01:00:00+06:00", "data": data}
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
