"""Phase E.2 — backend chart series enricher.

After the LLM produces final_brief, a deterministic helper fetches time-series
from `metric_history` and stamps it onto `final_brief.sections[i].series` so
the SPA can render charts. dse/iran/banking are HTTP-dispatched; fx joins
bb/tbond/macro/remit on the monthly branches, stamped from
metric_history_monthly; the rest get an empty series list and the frontend
hides their chart slot.

Coverage:
  1. `_CHART_FETCHERS_BY_SLUG` dispatch table contains exactly the HTTP-dispatched
     slugs (dse/iran) and no others (fx/tbond moved to the monthly branches).
  2. Each per-section fetcher in `chart_series_fetcher` produces well-formed
     `SeriesPointV6` objects (key + ISO date + numeric value) given a mocked
     PostgREST `metric_history` response.
  3. The DSEX fetcher returns a (series, notes) tuple — notes is always empty
     because `metric_history` has no event/label columns.
  4. The yield-curve fetcher normalizes metric_ids → "yield_3m/6m/1y/5y/10y"
     keys (consistent with `lib/chartConfigs.ts` tenorMap).
  5. Empty Supabase response → empty list, no crash.
  6. `_stamp_chart_series` only populates the 4 chartable sections; non-
     chartable sections retain empty series.
  7. A failing fetcher logs a warning but does not crash the pipeline; other
     sections still get stamped (graceful degradation).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import pytest

from brief import chart_series_fetcher, pipeline_v6
from brief.history import HistoryRow, HttpClient
from brief.v6_schema import (
    BriefPayloadV6,
    BriefV6,
    SectionV6,
    SeriesNoteV6,
    SeriesPointV6,
)


# ─── HTTP stub ─────────────────────────────────────────────────────────


class _FakeHttp:
    """Records GETs and replies from a queue of canned (status, body) pairs.

    Mirrors the `MetricHistoryClient` HttpClient Protocol shape used in
    `tests/test_history.py`. POSTs are not used here.
    """

    def __init__(self, responses: list[tuple[int, Any]]) -> None:
        self._responses: list[tuple[int, Any]] = list(responses)
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, *, headers: dict[str, str]) -> tuple[int, Any]:
        self.requests.append((url, headers))
        if not self._responses:
            return 200, []
        return self._responses.pop(0)

    def post(self, url: str, *, headers: dict[str, str], json: Any) -> tuple[int, Any]:  # pragma: no cover
        raise AssertionError("POST not expected for chart series fetchers")


def _http(responses: list[tuple[int, Any]]) -> _FakeHttp:
    return _FakeHttp(responses)


# ─── Constants under test ──────────────────────────────────────────────


SUPABASE_URL = "https://test.supabase.co"
SERVICE_KEY = "test-service-key"
TODAY = date(2026, 5, 8)


# ─── Dispatch table ────────────────────────────────────────────────────


def test_chart_fetchers_by_slug_only_includes_http_dispatched_sections() -> None:
    """The HTTP dispatch dict contains exactly dse/iran/banking.

    fx joined the monthly branches via the metric_history_monthly External Flow
    Balance branch (F3), tbond moved to the yield-ladder branch (F5), and
    bb/macro/remit are stamped via their own monthly-archive branches — none of
    those go through _CHART_FETCHERS_BY_SLUG. banking (DOMMR/BOFR overnight
    money-market) is a daily metric_history fetcher, so it rides the HTTP
    dispatch like brent.
    """
    assert set(pipeline_v6._CHART_FETCHERS_BY_SLUG.keys()) == {
        "dse",
        "iran",
        "banking",
    }


# ─── Per-section fetcher tests ─────────────────────────────────────────


def test_fetch_fx_flows_emits_one_point_per_metric_history_row() -> None:
    """fx fetcher returns SeriesPointV6 list keyed by metric_id."""
    rows: list[dict[str, Any]] = [
        {"metric_id": "monthly_export", "as_of": "2026-04-30", "value": 4.2},
        {"metric_id": "monthly_export", "as_of": "2026-05-31", "value": 4.5},
        {"metric_id": "monthly_remittance", "as_of": "2026-04-30", "value": 2.1},
        {"metric_id": "monthly_import", "as_of": "2026-04-30", "value": 6.0},
    ]
    http: _FakeHttp = _http([(200, rows)])
    series: list[SeriesPointV6] = chart_series_fetcher.fetch_fx_flows(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
        months=12,
    )
    assert len(series) == 4
    keys: set[str | None] = {p.key for p in series}
    assert keys == {"monthly_export", "monthly_remittance", "monthly_import"}
    by_key: dict[str | None, list[SeriesPointV6]] = {}
    for p in series:
        by_key.setdefault(p.key, []).append(p)
    assert len(by_key["monthly_export"]) == 2
    assert by_key["monthly_export"][0].ts == "2026-04-30"
    assert by_key["monthly_export"][0].value == 4.2


def test_fetch_fx_flows_returns_empty_on_empty_response() -> None:
    """No rows → empty series, no crash."""
    http: _FakeHttp = _http([(200, [])])
    series: list[SeriesPointV6] = chart_series_fetcher.fetch_fx_flows(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    assert series == []


def test_fetch_fx_flows_returns_empty_on_http_error() -> None:
    """500 from Supabase → empty list (graceful degradation)."""
    http: _FakeHttp = _http([(500, None)])
    series: list[SeriesPointV6] = chart_series_fetcher.fetch_fx_flows(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    assert series == []


def test_fetch_fx_flows_filters_to_three_metric_ids() -> None:
    """The PostgREST URL filters metric_id to exactly the 3 fx flow ids."""
    http: _FakeHttp = _http([(200, [])])
    chart_series_fetcher.fetch_fx_flows(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    url: str = http.requests[0][0]
    assert "monthly_export" in url
    assert "monthly_remittance" in url
    assert "monthly_import" in url


def test_fetch_dsex_emits_one_point_per_row() -> None:
    """DSEX fetcher emits a SeriesPointV6 for every metric_history row."""
    rows: list[dict[str, Any]] = [
        {"metric_id": "dsex", "as_of": "2026-05-01", "value": 5210.42},
        {"metric_id": "dsex", "as_of": "2026-05-02", "value": 5215.10},
        {"metric_id": "dsex", "as_of": "2026-05-05", "value": 5180.00},
    ]
    http: _FakeHttp = _http([(200, rows)])
    series, notes = chart_series_fetcher.fetch_dsex(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    assert len(series) == 3
    assert all(p.key == "dsex" for p in series)
    assert series[0].ts == "2026-05-01"
    assert series[0].value == 5210.42
    assert notes == []


def test_fetch_dsex_returns_empty_notes_even_with_data() -> None:
    """metric_history has no event/show_label columns; notes are always [].

    The legacy `tb_dsex_daily` show_label/event annotation feature is gone;
    DSEX fetcher's tuple shape is preserved so callers don't break, but the
    notes list is always empty.
    """
    rows: list[dict[str, Any]] = [
        {"metric_id": "dsex", "as_of": "2026-05-01", "value": 5210.42},
        {"metric_id": "dsex", "as_of": "2026-05-02", "value": 5215.10},
    ]
    http: _FakeHttp = _http([(200, rows)])
    series, notes = chart_series_fetcher.fetch_dsex(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    assert len(series) == 2
    assert notes == []


def test_fetch_dsex_filters_to_dsex_metric_id() -> None:
    """The PostgREST URL filters on metric_id=eq.dsex."""
    http: _FakeHttp = _http([(200, [])])
    chart_series_fetcher.fetch_dsex(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    url: str = http.requests[0][0]
    assert "metric_history" in url
    assert "metric_id=eq.dsex" in url


def test_fetch_dsex_returns_empty_on_empty_response() -> None:
    """No rows → empty series + empty notes."""
    http: _FakeHttp = _http([(200, [])])
    series, notes = chart_series_fetcher.fetch_dsex(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    assert series == []
    assert notes == []


def test_fetch_money_market_emits_one_point_per_row_keyed_by_metric_id() -> None:
    """DOMMR/BOFR fetcher returns SeriesPointV6 list keyed by metric_id, one
    point per metric_history row — both keys from a single batched request."""
    rows: list[dict[str, Any]] = [
        {"metric_id": "dommr", "as_of": "2026-08-26", "value": 9.15},
        {"metric_id": "dommr", "as_of": "2026-08-27", "value": 9.18},
        {"metric_id": "bofr", "as_of": "2026-08-26", "value": 9.20},
        {"metric_id": "bofr", "as_of": "2026-08-27", "value": 9.23},
    ]
    http: _FakeHttp = _http([(200, rows)])
    series: list[SeriesPointV6] = chart_series_fetcher.fetch_money_market(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    assert len(series) == 4
    assert len(http.requests) == 1, "both rates come from one batched request"
    by_key: dict[str | None, list[SeriesPointV6]] = {}
    for p in series:
        by_key.setdefault(p.key, []).append(p)
    assert set(by_key) == {"dommr", "bofr"}
    assert by_key["dommr"][-1].ts == "2026-08-27"
    assert by_key["dommr"][-1].value == 9.18
    assert by_key["bofr"][-1].value == 9.23


def test_fetch_money_market_filters_to_the_two_overnight_ids() -> None:
    """The PostgREST URL targets metric_history with metric_id=in.(dommr,bofr) —
    the stored-but-not-charted 1-week tenors (dommr_1w/bofr_1w) are excluded."""
    http: _FakeHttp = _http([(200, [])])
    chart_series_fetcher.fetch_money_market(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    url: str = http.requests[0][0]
    assert "metric_history" in url
    assert "dommr" in url
    assert "bofr" in url
    assert "dommr_1w" not in url
    assert "bofr_1w" not in url


def test_fetch_money_market_drops_unknown_metric_ids() -> None:
    """Rows outside dommr/bofr (e.g. a 1-week tenor leaking through) are
    dropped defensively, mirroring fetch_yield_curve."""
    rows: list[dict[str, Any]] = [
        {"metric_id": "dommr_1w", "as_of": "2026-08-27", "value": 9.30},
        {"metric_id": "dommr", "as_of": "2026-08-27", "value": 9.18},
    ]
    http: _FakeHttp = _http([(200, rows)])
    series: list[SeriesPointV6] = chart_series_fetcher.fetch_money_market(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    assert len(series) == 1
    assert series[0].key == "dommr"


def test_fetch_money_market_returns_empty_on_empty_response() -> None:
    """No rows → empty list, no crash."""
    http: _FakeHttp = _http([(200, [])])
    series: list[SeriesPointV6] = chart_series_fetcher.fetch_money_market(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    assert series == []


def test_fetch_money_market_returns_empty_on_http_error() -> None:
    """500 from Supabase → empty list (graceful degradation)."""
    http: _FakeHttp = _http([(500, None)])
    series: list[SeriesPointV6] = chart_series_fetcher.fetch_money_market(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    assert series == []


def test_fetch_brent_emits_one_point_per_row() -> None:
    """Brent fetcher → key='brent', ts=as_of, value=jsonb-coerced float."""
    rows: list[dict[str, Any]] = [
        {"metric_id": "brent_crude_usd_barrel", "as_of": "2026-04-09", "value": 88.50},
        {"metric_id": "brent_crude_usd_barrel", "as_of": "2026-05-08", "value": 91.20},
    ]
    http: _FakeHttp = _http([(200, rows)])
    series: list[SeriesPointV6] = chart_series_fetcher.fetch_brent(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    assert len(series) == 2
    assert all(p.key == "brent" for p in series)
    assert series[0].ts == "2026-04-09"
    assert series[0].value == 88.50


def test_fetch_brent_filters_to_brent_metric_id() -> None:
    """The PostgREST URL targets metric_history with metric_id=eq.brent_crude_usd_barrel."""
    http: _FakeHttp = _http([(200, [])])
    chart_series_fetcher.fetch_brent(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    url: str = http.requests[0][0]
    assert "metric_history" in url
    assert "metric_id=eq.brent_crude_usd_barrel" in url


def test_fetch_brent_returns_empty_on_empty_response() -> None:
    """No rows → empty list."""
    http: _FakeHttp = _http([(200, [])])
    series: list[SeriesPointV6] = chart_series_fetcher.fetch_brent(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    assert series == []


def test_fetch_yield_curve_normalizes_metric_ids_to_tenor_keys() -> None:
    """5 metric_ids → keys 'yield_3m'/'6m'/'1y'/'5y'/'10y'."""
    rows: list[dict[str, Any]] = [
        {"metric_id": "tbill_91d_yield_pct", "as_of": "2026-05-01", "value": 5.5},
        {"metric_id": "tbill_182d_yield", "as_of": "2026-05-01", "value": 6.0},
        {"metric_id": "tbill_364d_yield", "as_of": "2026-05-01", "value": 6.5},
        {"metric_id": "tbond_bond_5y", "as_of": "2026-05-01", "value": 7.5},
        {"metric_id": "tbond_bond_10y", "as_of": "2026-05-01", "value": 8.1},
    ]
    http: _FakeHttp = _http([(200, rows)])
    series: list[SeriesPointV6] = chart_series_fetcher.fetch_yield_curve(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    keys: set[str | None] = {p.key for p in series}
    assert keys == {"yield_3m", "yield_6m", "yield_1y", "yield_5y", "yield_10y"}
    by_key: dict[str | None, SeriesPointV6] = {p.key: p for p in series}
    assert by_key["yield_3m"].value == 5.5
    assert by_key["yield_3m"].ts == "2026-05-01"
    assert by_key["yield_10y"].value == 8.1


def test_fetch_yield_curve_drops_unknown_metric_ids() -> None:
    """metric_ids outside the 5-tenor mapping are dropped (defensive)."""
    rows: list[dict[str, Any]] = [
        {"metric_id": "tbond_bond_2y_legacy", "as_of": "2026-05-01", "value": 6.5},
        {"metric_id": "tbond_bond_5y", "as_of": "2026-05-01", "value": 7.5},
    ]
    http: _FakeHttp = _http([(200, rows)])
    series: list[SeriesPointV6] = chart_series_fetcher.fetch_yield_curve(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    assert len(series) == 1
    assert series[0].key == "yield_5y"


def test_fetch_yield_curve_filters_to_5_metric_ids() -> None:
    """The PostgREST URL filters metric_id to exactly the 5 tenor ids."""
    http: _FakeHttp = _http([(200, [])])
    chart_series_fetcher.fetch_yield_curve(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    url: str = http.requests[0][0]
    assert "metric_history" in url
    for metric_id in (
        "tbill_91d_yield_pct",
        "tbill_182d_yield",
        "tbill_364d_yield",
        "tbond_bond_5y",
        "tbond_bond_10y",
    ):
        assert metric_id in url


def test_fetch_yield_curve_returns_empty_on_empty_response() -> None:
    """No snapshots → empty list."""
    http: _FakeHttp = _http([(200, [])])
    series: list[SeriesPointV6] = chart_series_fetcher.fetch_yield_curve(
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
        today=TODAY,
    )
    assert series == []


# ─── Authentication / URL sanity ───────────────────────────────────────


@pytest.mark.parametrize(
    "fetcher_name",
    ["fetch_fx_flows", "fetch_dsex", "fetch_brent", "fetch_yield_curve", "fetch_money_market"],
)
def test_fetchers_set_authorization_headers(fetcher_name: str) -> None:
    """Every fetcher passes apikey + Authorization Bearer headers."""
    http: _FakeHttp = _http([(200, [])])
    fn = getattr(chart_series_fetcher, fetcher_name)
    fn(http=http, supabase_url=SUPABASE_URL, service_key=SERVICE_KEY, today=TODAY)
    assert http.requests, "fetcher should issue at least one HTTP GET"
    _, headers = http.requests[0]
    assert headers.get("apikey") == SERVICE_KEY
    assert headers.get("Authorization") == f"Bearer {SERVICE_KEY}"


# ─── _stamp_chart_series helper ────────────────────────────────────────


def _make_section(slug: str, ord_v6: int, group: str) -> SectionV6:
    """Minimal SectionV6 for a slug; group_key must be Literal-valid."""
    return SectionV6(
        slug=slug,
        ord=ord_v6,
        title=f"Section {slug.upper()}",
        group_key=group,  # type: ignore[arg-type]
    )


def _full_brief() -> BriefPayloadV6:
    """An 11-section brief covering the V5_TO_V6 roster.

    The `comm` section still exists in the brief (LNG content), it just no
    longer has a chart fetcher post-V6 repoint.
    """
    sections: list[SectionV6] = [
        _make_section("headlines", 2, "overview"),
        _make_section("bb", 3, "banking"),
        _make_section("banking", 4, "banking"),
        _make_section("fx", 5, "markets"),
        _make_section("dse", 6, "markets"),
        _make_section("tbond", 7, "markets"),
        _make_section("fiscal", 8, "policy"),
        _make_section("macro", 9, "markets"),
        _make_section("iran", 10, "policy"),
        _make_section("remit", 11, "markets"),
        _make_section("comm", 12, "markets"),
    ]
    return BriefPayloadV6(
        brief=BriefV6(issue_no=1, volume=1, brief_date=TODAY),
        sections=sections,
    )


def test_stamp_chart_series_populates_chartable_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All chartable slugs get series; the chartless ones stay empty.

    HTTP-dispatched: dse/iran/banking. Monthly-archive branches: fx (F3 External
    Flow Balance), bb (F2 reserves), tbond (F5 yield ladder), macro (CPI),
    remit (F6), fiscal (F7b NBR).
    Chartless: headlines, comm (comm de-charted post-LNG-drop).
    """
    dsex_series: list[SeriesPointV6] = [SeriesPointV6(key="dsex", ts="2026-05-01", value=5210.0)]
    dsex_notes: list[SeriesNoteV6] = []
    brent_series: list[SeriesPointV6] = [SeriesPointV6(key="brent", ts="2026-05-08", value=91.2)]
    mm_series: list[SeriesPointV6] = [
        SeriesPointV6(key="dommr", ts="2026-05-07", value=9.18),
        SeriesPointV6(key="bofr", ts="2026-05-07", value=9.23),
    ]
    fx_pt = SeriesPointV6(key="exports_usd_mn_monthly", ts="2026-03-01", value=3489.8)
    reserves_pt = SeriesPointV6(key="gross_reserves_usd_bn_monthly", ts="2026-03-01", value=34.1)
    ladder_pt = SeriesPointV6(key="yield_5y_monthly", ts="2026-04-01", value=10.75)
    macro_pt = SeriesPointV6(key="cpi_12m_avg_monthly", ts="2026-04-01", value=9.5)
    remit_pt = SeriesPointV6(key="remittance_usd_mn_monthly", ts="2026-03-01", value=3755.1)
    fiscal_pt = SeriesPointV6(key="nbr_revenue_monthly_cr", ts="2025-03-01", value=32245.0)

    monkeypatch.setattr(chart_series_fetcher, "fetch_dsex", lambda **_: (dsex_series, dsex_notes))
    monkeypatch.setattr(chart_series_fetcher, "fetch_brent", lambda **_: brent_series)
    monkeypatch.setattr(chart_series_fetcher, "fetch_money_market", lambda **_: mm_series)
    monkeypatch.setattr(
        chart_series_fetcher, "fetch_fx_balance_monthly", lambda *_a, **_k: {fx_pt.key: [fx_pt]}
    )
    monkeypatch.setattr(
        chart_series_fetcher, "fetch_reserves_monthly", lambda *_a, **_k: {reserves_pt.key: [reserves_pt]}
    )
    monkeypatch.setattr(
        chart_series_fetcher, "fetch_yield_ladder_monthly", lambda *_a, **_k: {ladder_pt.key: [ladder_pt]}
    )
    monkeypatch.setattr(
        chart_series_fetcher, "fetch_macro_cpi_series", lambda *_a, **_k: {macro_pt.key: [macro_pt]}
    )
    monkeypatch.setattr(
        chart_series_fetcher, "fetch_remit_monthly", lambda *_a, **_k: {remit_pt.key: [remit_pt]}
    )
    monkeypatch.setattr(
        chart_series_fetcher, "fetch_fiscal_monthly", lambda *_a, **_k: {fiscal_pt.key: [fiscal_pt]}
    )

    final_brief: BriefPayloadV6 = _full_brief()
    pipeline_v6._stamp_chart_series(
        final_brief,
        today=TODAY,
        http=_http([]),
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
    )
    by_slug: dict[str, SectionV6] = {s.slug: s for s in final_brief.sections}

    # Chartable: have series
    assert by_slug["fx"].series == [fx_pt]
    assert by_slug["dse"].series == dsex_series
    assert by_slug["dse"].notes == dsex_notes
    assert by_slug["iran"].series == brent_series
    assert by_slug["bb"].series == [reserves_pt]
    assert by_slug["tbond"].series == [ladder_pt]
    assert by_slug["macro"].series == [macro_pt]
    assert by_slug["remit"].series == [remit_pt]
    assert by_slug["fiscal"].series == [fiscal_pt]
    assert by_slug["banking"].series == mm_series

    # Chartless: empty
    for slug in ("headlines", "comm"):
        assert by_slug[slug].series == [], f"{slug} should have empty series"
        assert by_slug[slug].notes == [], f"{slug} should have empty notes"


def test_stamp_chart_series_handles_fetcher_exception_gracefully(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If one fetcher raises, others still succeed; pipeline does not crash."""
    brent_series: list[SeriesPointV6] = [SeriesPointV6(key="brent", ts="2026-05-08", value=91.2)]

    def _bad_dsex(**_: Any) -> tuple[list[SeriesPointV6], list[SeriesNoteV6]]:
        raise RuntimeError("simulated network blip")

    def _ok_brent(**_: Any) -> list[SeriesPointV6]:
        return brent_series

    def _empty_dict(*_a: Any, **_k: Any) -> dict[str, list[SeriesPointV6]]:
        return {}

    monkeypatch.setattr(chart_series_fetcher, "fetch_dsex", _bad_dsex)
    monkeypatch.setattr(chart_series_fetcher, "fetch_brent", _ok_brent)
    monkeypatch.setattr(chart_series_fetcher, "fetch_money_market", lambda **_: [])
    # Isolate the monthly-archive branches so they don't hit the real client
    # via the fake HTTP stub (they're exercised in their own tests below).
    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_balance_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_yield_ladder_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_reserves_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_macro_cpi_series", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_fiscal_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_remit_monthly", _empty_dict)

    final_brief: BriefPayloadV6 = _full_brief()

    with caplog.at_level(logging.WARNING, logger="brief.pipeline_v6"):
        pipeline_v6._stamp_chart_series(
            final_brief,
            today=TODAY,
            http=_http([]),
            supabase_url=SUPABASE_URL,
            service_key=SERVICE_KEY,
        )

    by_slug: dict[str, SectionV6] = {s.slug: s for s in final_brief.sections}
    assert by_slug["iran"].series == brent_series, "iran still stamped despite dsex failure"
    assert by_slug["dse"].series == [], "dse left empty after fetcher exception"
    assert by_slug["dse"].notes == [], "dse notes left empty after fetcher exception"
    # A warning should have been logged for the failing fetcher
    assert any(
        "dse" in record.getMessage().lower() or "dsex" in record.getMessage().lower()
        for record in caplog.records
    ), f"expected warning mentioning dse fetcher; got {[r.getMessage() for r in caplog.records]}"


def test_stamp_chart_series_handles_monthly_branch_exception_gracefully(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If the fx (External Flow Balance), bb (reserves), tbond (yield-ladder),
    or fiscal (F7b NBR) monthly fetchers raise, the pipeline leaves those series
    empty, logs a warning, and does not crash."""

    def _raise(*_a: Any, **_k: Any) -> dict[str, list[SeriesPointV6]]:
        raise RuntimeError("simulated monthly-archive blip")

    def _empty_dict(*_a: Any, **_k: Any) -> dict[str, list[SeriesPointV6]]:
        return {}

    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_balance_monthly", _raise)
    monkeypatch.setattr(chart_series_fetcher, "fetch_reserves_monthly", _raise)
    monkeypatch.setattr(chart_series_fetcher, "fetch_yield_ladder_monthly", _raise)
    monkeypatch.setattr(chart_series_fetcher, "fetch_fiscal_monthly", _raise)
    # Isolate the other branches so only fx/bb/tbond/fiscal failures are under test.
    monkeypatch.setattr(chart_series_fetcher, "fetch_dsex", lambda **_: ([], []))
    monkeypatch.setattr(chart_series_fetcher, "fetch_brent", lambda **_: [])
    monkeypatch.setattr(chart_series_fetcher, "fetch_money_market", lambda **_: [])
    monkeypatch.setattr(chart_series_fetcher, "fetch_macro_cpi_series", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_remit_monthly", _empty_dict)

    final_brief: BriefPayloadV6 = _full_brief()

    with caplog.at_level(logging.WARNING, logger="brief.pipeline_v6"):
        pipeline_v6._stamp_chart_series(
            final_brief,
            today=TODAY,
            http=_http([]),
            supabase_url=SUPABASE_URL,
            service_key=SERVICE_KEY,
        )

    by_slug: dict[str, SectionV6] = {s.slug: s for s in final_brief.sections}
    # All raising branches degrade to empty without crashing the publish.
    assert by_slug["fx"].series == [], "fx left empty after fx-balance fetcher exception"
    assert by_slug["bb"].series == [], "bb left empty after reserves fetcher exception"
    assert by_slug["tbond"].series == [], "tbond left empty after yield-ladder fetcher exception"
    assert by_slug["fiscal"].series == [], "fiscal left empty after fiscal fetcher exception"
    messages = " ".join(r.getMessage().lower() for r in caplog.records)
    assert "fx" in messages, f"expected a warning mentioning fx; got {messages!r}"
    assert "bb" in messages, f"expected a warning mentioning bb; got {messages!r}"
    assert "tbond" in messages, f"expected a warning mentioning tbond; got {messages!r}"
    assert "fiscal" in messages, f"expected a warning mentioning fiscal; got {messages!r}"


def test_stamp_chart_series_skips_when_section_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A brief without 'fx' section just skips the fx fetcher; no crash."""
    called: list[str] = []

    def _ok_fx(*_a: Any, **_k: Any) -> dict[str, list[SeriesPointV6]]:
        called.append("fx")
        return {}

    def _ok_dsex(**_: Any) -> tuple[list[SeriesPointV6], list[SeriesNoteV6]]:
        called.append("dse")
        return [], []

    def _ok_brent(**_: Any) -> list[SeriesPointV6]:
        called.append("iran")
        return []

    def _ok_ladder(*_a: Any, **_k: Any) -> dict[str, list[SeriesPointV6]]:
        called.append("tbond")
        return {}

    def _ok_reserves(*_a: Any, **_k: Any) -> dict[str, list[SeriesPointV6]]:
        called.append("bb")
        return {}

    def _ok_money_market(**_: Any) -> list[SeriesPointV6]:
        called.append("banking")
        return []

    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_balance_monthly", _ok_fx)
    monkeypatch.setattr(chart_series_fetcher, "fetch_dsex", _ok_dsex)
    monkeypatch.setattr(chart_series_fetcher, "fetch_brent", _ok_brent)
    monkeypatch.setattr(chart_series_fetcher, "fetch_money_market", _ok_money_market)
    monkeypatch.setattr(chart_series_fetcher, "fetch_yield_ladder_monthly", _ok_ladder)
    monkeypatch.setattr(chart_series_fetcher, "fetch_reserves_monthly", _ok_reserves)

    # Brief with only comm + headlines — none of the chartable slugs
    # (bb is chartable via the F2 reserves branch, fiscal via the F7b NBR
    # branch, and banking via the money-market HTTP dispatch, so none of
    # those can stand in here).
    minimal_brief: BriefPayloadV6 = BriefPayloadV6(
        brief=BriefV6(issue_no=1, volume=1, brief_date=TODAY),
        sections=[
            _make_section("comm", 12, "markets"),
            _make_section("headlines", 2, "overview"),
        ],
    )
    pipeline_v6._stamp_chart_series(
        minimal_brief,
        today=TODAY,
        http=_http([]),
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
    )
    assert called == [], "no fetchers should run when brief has no chartable sections"


# ─── run_publish integration: chart series stamping wired in ───────────


def test_run_publish_stamps_chart_series_on_final_brief(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_publish calls _stamp_chart_series so series land on the published payload."""
    monday: date = date(2026, 5, 4)

    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SERVICE_KEY)
    monkeypatch.setattr(pipeline_v6, "fetch_previous_brief", lambda: None)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 0)
    monkeypatch.setattr(pipeline_v6, "fetch_recent_news", lambda n_issues=5: [])
    monkeypatch.setattr(pipeline_v6, "fetch_metric_definitions", lambda: [])

    fx_pt = SeriesPointV6(key="exports_usd_mn_monthly", ts="2026-04-30", value=3489.8)

    monkeypatch.setattr(
        chart_series_fetcher, "fetch_fx_balance_monthly", lambda *_a, **_k: {fx_pt.key: [fx_pt]}
    )
    monkeypatch.setattr(
        chart_series_fetcher,
        "fetch_dsex",
        lambda **_: ([], []),
    )
    monkeypatch.setattr(chart_series_fetcher, "fetch_brent", lambda **_: [])
    monkeypatch.setattr(chart_series_fetcher, "fetch_yield_ladder_monthly", lambda *_a, **_k: {})

    editor_output: dict[str, Any] = {
        "brief": {
            "issue_no": 1,
            "volume": 1,
            "brief_date": monday.isoformat(),
            "status": "published",
        },
        "sections": [
            {
                "slug": "fx",
                "ord": 5,
                "title": "FX Markets",
                "group_key": "markets",
                "weight": 1,
                "verdict": "BDT pegged",
                "verdict_tone": "neu",
            },
        ],
    }
    subeditor_output: dict[str, Any] = {"verdict": "pass", "issues": []}

    def fake_call(*, label: str, **_: Any) -> dict[str, Any]:
        if label == "editor_v6":
            return editor_output
        if label == "subeditor_v6":
            return subeditor_output
        raise AssertionError(f"unexpected label: {label}")

    monkeypatch.setattr(pipeline_v6, "_call_with_retries", fake_call)

    captured: list[BriefPayloadV6] = []
    monkeypatch.setattr(
        pipeline_v6,
        "publish_brief",
        lambda payload: captured.append(payload) or "fake-uuid",
    )

    # V5 input must include an fx section so editor_input["sections_raw"]
    # carries fx — BriefPayloadV6 accepts arbitrary slugs at the section level.
    from brief.schema import SectionData

    v5_sections: list[SectionData] = [
        SectionData(id="fx", title="FX Markets", metrics=[], freshness="fresh"),
    ]
    result: str | None = pipeline_v6.run_publish(v5_sections, monday)
    assert result == "fake-uuid"
    assert len(captured) == 1
    published: BriefPayloadV6 = captured[0]
    by_slug: dict[str, SectionV6] = {s.slug: s for s in published.sections}
    assert "fx" in by_slug
    assert by_slug["fx"].series == [fx_pt], (
        f"fx section should have stamped series; got {by_slug['fx'].series!r}"
    )


def test_run_publish_skips_chart_stamping_when_supabase_env_missing(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When SUPABASE_URL or service key is missing, chart stamping no-ops with
    a warning — the pipeline must still publish (degraded charts are non-fatal).
    """
    monday: date = date(2026, 5, 4)

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    monkeypatch.setattr(pipeline_v6, "fetch_previous_brief", lambda: None)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 0)
    monkeypatch.setattr(pipeline_v6, "fetch_recent_news", lambda n_issues=5: [])
    monkeypatch.setattr(pipeline_v6, "fetch_metric_definitions", lambda: [])

    # Sanity: if a fetcher gets called we'd know via this raising stub.
    def _should_not_run(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("fetcher should not run without supabase env")

    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_balance_monthly", _should_not_run)

    editor_output: dict[str, Any] = {
        "brief": {
            "issue_no": 1,
            "volume": 1,
            "brief_date": monday.isoformat(),
            "status": "published",
        },
        "sections": [
            {
                "slug": "fx",
                "ord": 5,
                "title": "FX Markets",
                "group_key": "markets",
                "weight": 1,
            },
        ],
    }
    subeditor_output: dict[str, Any] = {"verdict": "pass", "issues": []}

    def fake_call(*, label: str, **_: Any) -> dict[str, Any]:
        if label == "editor_v6":
            return editor_output
        if label == "subeditor_v6":
            return subeditor_output
        raise AssertionError(f"unexpected label: {label}")

    monkeypatch.setattr(pipeline_v6, "_call_with_retries", fake_call)
    monkeypatch.setattr(pipeline_v6, "publish_brief", lambda payload: "fake-uuid")

    from brief.schema import SectionData

    v5_sections: list[SectionData] = [
        SectionData(id="fx", title="FX Markets", metrics=[], freshness="fresh"),
    ]

    with caplog.at_level(logging.WARNING, logger="brief.pipeline_v6"):
        result: str | None = pipeline_v6.run_publish(v5_sections, monday)

    assert result == "fake-uuid"
    # Some warning mentioning chart series / supabase env should have been logged
    messages: list[str] = [r.getMessage().lower() for r in caplog.records]
    assert any("chart" in m or "supabase" in m for m in messages), (
        f"expected a warning about skipped chart stamping; got {messages}"
    )


# ─── Stamping uses the dispatch table ──────────────────────────────────


def test_stamp_chart_series_threads_http_and_today_to_fetchers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every HTTP-dispatched fetcher (dse/iran/banking) receives http,
    supabase_url, service_key, today. The monthly-archive branches
    (fx/bb/tbond/macro/remit) take a history client instead and are covered
    separately."""
    captured: list[dict[str, Any]] = []

    def _record(**kwargs: Any) -> list[SeriesPointV6]:
        captured.append(kwargs)
        return []

    def _record_dsex(**kwargs: Any) -> tuple[list[SeriesPointV6], list[SeriesNoteV6]]:
        captured.append(kwargs)
        return [], []

    monkeypatch.setattr(chart_series_fetcher, "fetch_dsex", _record_dsex)
    monkeypatch.setattr(chart_series_fetcher, "fetch_brent", _record)
    monkeypatch.setattr(chart_series_fetcher, "fetch_money_market", _record)
    # Isolate the monthly-archive branches (history-client signature, not the
    # http/today kwargs under test here) so they don't hit the fake HTTP stub.
    def _empty_dict(*_a: Any, **_k: Any) -> dict[str, list[SeriesPointV6]]:
        return {}

    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_balance_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_reserves_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_yield_ladder_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_macro_cpi_series", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_remit_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_fiscal_monthly", _empty_dict)

    final_brief: BriefPayloadV6 = _full_brief()
    http: HttpClient = _http([])
    pipeline_v6._stamp_chart_series(
        final_brief,
        today=TODAY,
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
    )
    assert len(captured) == 3, "all 3 HTTP-dispatched fetchers should be dispatched"
    for kw in captured:
        assert kw["http"] is http
        assert kw["supabase_url"] == SUPABASE_URL
        assert kw["service_key"] == SERVICE_KEY
        assert kw["today"] == TODAY


# ─── F4 — DS30 movers stamping ─────────────────────────────────────────


def test_stamp_chart_series_stamps_dse_movers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dse section gets `movers` stamped from `fetch_dse_movers`, alongside
    the existing dsex chart series (the two are independent fields)."""
    from brief.v6_schema import MoverRowV6

    mover = MoverRowV6(ticker="FINEFOODS", price=577.0, return_pct=16.57)
    dsex_series: list[SeriesPointV6] = [SeriesPointV6(key="dsex", ts="2026-05-01", value=5210.0)]

    monkeypatch.setattr(chart_series_fetcher, "fetch_dsex", lambda **_: (dsex_series, []))
    monkeypatch.setattr(chart_series_fetcher, "fetch_dse_movers", lambda **_k: [mover])
    # Isolate every other branch so only the dse section is under test.
    monkeypatch.setattr(chart_series_fetcher, "fetch_brent", lambda **_: [])
    monkeypatch.setattr(chart_series_fetcher, "fetch_money_market", lambda **_: [])

    def _empty_dict(*_a: Any, **_k: Any) -> dict[str, list[SeriesPointV6]]:
        return {}

    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_balance_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_reserves_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_yield_ladder_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_macro_cpi_series", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_remit_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_fiscal_monthly", _empty_dict)

    final_brief: BriefPayloadV6 = _full_brief()
    pipeline_v6._stamp_chart_series(
        final_brief,
        today=TODAY,
        http=_http([]),
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
    )
    by_slug: dict[str, SectionV6] = {s.slug: s for s in final_brief.sections}
    assert by_slug["dse"].movers == [mover]
    # The chart series is stamped independently of the movers field.
    assert by_slug["dse"].series == dsex_series


def test_stamp_chart_series_dse_movers_failure_is_isolated(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A `fetch_dse_movers` exception is swallowed (warning logged) without
    killing the dse chart series; `movers` is left None."""
    dsex_series: list[SeriesPointV6] = [SeriesPointV6(key="dsex", ts="2026-05-01", value=5210.0)]

    def _raise(**_k: Any) -> list[Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(chart_series_fetcher, "fetch_dsex", lambda **_: (dsex_series, []))
    monkeypatch.setattr(chart_series_fetcher, "fetch_dse_movers", _raise)
    monkeypatch.setattr(chart_series_fetcher, "fetch_brent", lambda **_: [])
    monkeypatch.setattr(chart_series_fetcher, "fetch_money_market", lambda **_: [])

    def _empty_dict(*_a: Any, **_k: Any) -> dict[str, list[SeriesPointV6]]:
        return {}

    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_balance_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_reserves_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_yield_ladder_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_macro_cpi_series", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_remit_monthly", _empty_dict)
    monkeypatch.setattr(chart_series_fetcher, "fetch_fiscal_monthly", _empty_dict)

    final_brief: BriefPayloadV6 = _full_brief()
    with caplog.at_level(logging.WARNING, logger="brief.pipeline_v6"):
        # Must NOT raise — the movers failure is isolated in its own try/except.
        pipeline_v6._stamp_chart_series(
            final_brief,
            today=TODAY,
            http=_http([]),
            supabase_url=SUPABASE_URL,
            service_key=SERVICE_KEY,
        )
    by_slug: dict[str, SectionV6] = {s.slug: s for s in final_brief.sections}
    # Chart series survives the movers failure (failure isolated).
    assert by_slug["dse"].series == dsex_series
    assert by_slug["dse"].movers is None
    messages = " ".join(r.getMessage().lower() for r in caplog.records)
    assert "movers" in messages, f"expected a warning mentioning movers; got {messages!r}"


# ─── CPI card-vs-chart honesty (issue 206, item 4) ──────────────────────
#
# Fixture mirrors PRODUCTION on 2026-08-24: daily food_inflation/
# non_food_inflation newest is 2026-06-30 = 8.6/9.61; the monthly archive
# carries a July row for all three CPI series, but only cpi_12m_avg_monthly's
# July point (8.66) is genuinely official (source=bb_inflation_page,
# independently confirmed by the daily general_inflation row) — July food
# (7.16) is arithmetic (source=derived_implied_weight_bb_inflation) and July
# non-food (9.28) is labelled bb_inflation_page but acknowledged upstream
# (econdelta's own backfill script) as never verified against a live page.


class _CpiDailyHistoryStub:
    """Minimal `metric_history` (daily) client stand-in for macro.build()."""

    _ROWS: dict[str, HistoryRow] = {}  # populated below, after HistoryRow import

    def get_latest(self, metric_id: str, *, table: str = "metric_history"):
        return self._ROWS.get(metric_id)

    def get_at_or_before(self, metric_id: str, as_of: date, *, table: str = "metric_history"):
        return None  # real_policy_rate's repo leg — not under test here


class _CpiMonthlyHistoryStub:
    """Minimal `metric_history_monthly` client stand-in — serves both
    `get_latest` (macro.py's archive_id reads) and `get_history_window`
    (chart_series_fetcher's anchor-mode fetch), from the SAME seeded rows."""

    _ARCHIVE_ROWS: dict[str, list[HistoryRow]] = {}  # populated below

    def get_latest(self, metric_id: str, *, table: str = "metric_history_monthly"):
        rows = self._ARCHIVE_ROWS.get(metric_id)
        return max(rows, key=lambda r: r.as_of) if rows else None

    def get_history_window(self, metric_ids, *, limit=None, table="metric_history_monthly", **_kw):
        # PostgREST anchor mode returns most-recent-first.
        return {
            mid: sorted(self._ARCHIVE_ROWS.get(mid, []), key=lambda r: r.as_of, reverse=True)
            for mid in metric_ids
        }


def _seed_cpi_fixture() -> None:
    from brief.history import HistoryRow as _HistoryRow

    _CpiDailyHistoryStub._ROWS = {
        "food_inflation": _HistoryRow(
            metric_id="food_inflation", as_of=date(2026, 6, 30), value=8.6, source="EconDelta",
        ),
        "non_food_inflation": _HistoryRow(
            metric_id="non_food_inflation", as_of=date(2026, 6, 30), value=9.61, source="EconDelta",
        ),
    }
    _CpiMonthlyHistoryStub._ARCHIVE_ROWS = {
        "cpi_12m_avg_monthly": [
            _HistoryRow(metric_id="cpi_12m_avg_monthly", as_of=date(2026, 6, 1),
                        value=8.32, source="bb_inflation_page"),
            _HistoryRow(metric_id="cpi_12m_avg_monthly", as_of=date(2026, 7, 1),
                        value=8.66, source="bb_inflation_page"),
        ],
        "cpi_p2p_food_monthly": [
            _HistoryRow(metric_id="cpi_p2p_food_monthly", as_of=date(2026, 6, 1),
                        value=8.6, source="bb_inflation_page"),
            _HistoryRow(metric_id="cpi_p2p_food_monthly", as_of=date(2026, 7, 1),
                        value=7.16, source="derived_implied_weight_bb_inflation"),
        ],
        "cpi_p2p_nonfood_monthly": [
            _HistoryRow(metric_id="cpi_p2p_nonfood_monthly", as_of=date(2026, 6, 1),
                        value=9.61, source="bb_inflation_page"),
            _HistoryRow(metric_id="cpi_p2p_nonfood_monthly", as_of=date(2026, 7, 1),
                        value=9.28, source="bb_inflation_page"),
        ],
    }


def test_macro_cpi_card_period_is_never_older_than_its_own_chart_series() -> None:
    """Issue 206 regression. Must FAIL on base (pre-fix) for food + non-food
    — their cards read June while their chart plots July's unofficial
    figure — and PASS for 12m-avg, which was never wrong (its July point is
    genuinely official)."""
    from brief.builders import BuilderContext
    from brief.builders.macro import build as macro_build
    from brief.econdelta import EconDeltaSnapshot

    _seed_cpi_fixture()
    ctx = BuilderContext(
        snapshot=EconDeltaSnapshot(
            updated_at=datetime(2026, 8, 24, 3, 15, tzinfo=timezone.utc),
            sources_status={}, data={},
        ),
        history=_CpiDailyHistoryStub(),
        history_monthly=_CpiMonthlyHistoryStub(),
        today=date(2026, 8, 24),
    )
    section = macro_build(ctx)
    cards_by_id = {m.id: m for m in section.metrics}

    chart_series = chart_series_fetcher.fetch_macro_cpi_series(ctx.history_monthly)
    newest_plotted = {
        mid: max((p.ts for p in pts), default=None) for mid, pts in chart_series.items()
    }

    for mid in ("cpi_p2p_food_monthly", "cpi_p2p_nonfood_monthly", "cpi_12m_avg_monthly"):
        card_period = cards_by_id[mid].as_of.isoformat()
        assert card_period >= newest_plotted[mid], (
            f"{mid}: card period {card_period} is OLDER than its own chart's "
            f"newest plotted point {newest_plotted[mid]}"
        )


def test_fetch_macro_cpi_series_keeps_the_official_12m_avg_july_point() -> None:
    """The July 12m-avg point (8.66, genuinely official) must survive the
    honesty filter — this is the point the earlier regression prose
    ('CPI 12m-avg eased to 8.66% as of the Jul 2026 print') truthfully
    describes, and truncating it would turn a TRUE statement into a FALSE
    one."""
    _seed_cpi_fixture()
    out = chart_series_fetcher.fetch_macro_cpi_series(_CpiMonthlyHistoryStub())
    ts_values = {p.ts: p.value for p in out["cpi_12m_avg_monthly"]}
    assert ts_values.get("2026-07-01") == 8.66


def test_fetch_macro_cpi_series_drops_the_derived_july_food_point() -> None:
    _seed_cpi_fixture()
    out = chart_series_fetcher.fetch_macro_cpi_series(_CpiMonthlyHistoryStub())
    ts_values = {p.ts for p in out["cpi_p2p_food_monthly"]}
    assert "2026-07-01" not in ts_values
    assert "2026-06-01" in ts_values


def test_fetch_macro_cpi_series_drops_the_owner_pending_july_nonfood_point() -> None:
    """9.28 is labelled bb_inflation_page (which LOOKS official) but is
    denylisted as owner-pending — a source-string whitelist alone cannot
    catch this; the explicit pending entry is required (see its comment)."""
    _seed_cpi_fixture()
    out = chart_series_fetcher.fetch_macro_cpi_series(_CpiMonthlyHistoryStub())
    ts_values = {p.ts for p in out["cpi_p2p_nonfood_monthly"]}
    assert "2026-07-01" not in ts_values
    assert "2026-06-01" in ts_values


# ─── CPI archive honesty gate must not truncate the whole history ────────
#
# Repair-agent regression (blocking review finding, post-merge of the "issue
# 206, item 4" honesty gate). Production's `metric_history_monthly` CPI trio
# carries `source='macro_observer_seed'` for every row before 2026-04-01 (the
# Phase-1 seeded backfill later extended by live `bb_inflation_page`
# appenders from April 2026 on) — confirmed live via anon Supabase read on
# 2026-08-24: 513 of 525 CPI-trio rows are `macro_observer_seed`, spanning
# 2012-01 through 2026-03; only 12 rows (the last 4 months per series) carry
# `bb_inflation_page`/`derived_implied_weight_bb_inflation`.
#
# The two fixtures above only ever seed June+July, so they could not catch
# `_OFFICIAL_CPI_SOURCES` excluding `macro_observer_seed` too — which is
# exactly what shipped: `fetch_macro_cpi_series(months=24)` collapsed the
# 24-month CPI Trend chart to 3-4 points, deleting ~20 months of real BB
# CPI history the chart had shown since v2.0.0's frozen-charts fix. This
# fixture mirrors the real producer's source mix (20 months seeded, 4
# months live) so the truncation is caught by the suite, not just by
# production.
def _seed_cpi_fixture_realistic_24_months() -> None:
    from brief.history import HistoryRow as _HistoryRow

    seeded_rows: dict[str, list[_HistoryRow]] = {mid: [] for mid in (
        "cpi_12m_avg_monthly", "cpi_p2p_food_monthly", "cpi_p2p_nonfood_monthly",
    )}
    # 20 months of the historical seed, oldest-looking id first (2024-08 .. 2026-03).
    for i in range(20):
        year, month = 2024 + (8 + i - 1) // 12, (8 + i - 1) % 12 + 1
        as_of = date(year, month, 1)
        for mid, base in (
            ("cpi_12m_avg_monthly", 9.0), ("cpi_p2p_food_monthly", 8.5),
            ("cpi_p2p_nonfood_monthly", 9.5),
        ):
            seeded_rows[mid].append(_HistoryRow(
                metric_id=mid, as_of=as_of, value=base + i * 0.01,
                source="macro_observer_seed",
            ))
    # 4 live official months (2026-04 .. 2026-07), matching production's
    # per-series shape: 12m-avg has all 4 official; food/non-food each have
    # 3 official (Apr/May/Jun) plus one excluded July point.
    for mid, official_months in (
        ("cpi_12m_avg_monthly", [(2026, 4, 8.6), (2026, 5, 8.63), (2026, 6, 8.66), (2026, 7, 8.69)]),
        ("cpi_p2p_food_monthly", [(2026, 4, 8.4), (2026, 5, 8.5), (2026, 6, 8.6)]),
        ("cpi_p2p_nonfood_monthly", [(2026, 4, 9.4), (2026, 5, 9.5), (2026, 6, 9.61)]),
    ):
        for year, month, value in official_months:
            seeded_rows[mid].append(_HistoryRow(
                metric_id=mid, as_of=date(year, month, 1), value=value,
                source="bb_inflation_page",
            ))
    # The two known-unofficial July points stay excluded regardless.
    seeded_rows["cpi_p2p_food_monthly"].append(_HistoryRow(
        metric_id="cpi_p2p_food_monthly", as_of=date(2026, 7, 1), value=7.16,
        source="derived_implied_weight_bb_inflation",
    ))
    seeded_rows["cpi_p2p_nonfood_monthly"].append(_HistoryRow(
        metric_id="cpi_p2p_nonfood_monthly", as_of=date(2026, 7, 1), value=9.28,
        source="bb_inflation_page",  # owner-pending denylisted despite the label
    ))
    _CpiMonthlyHistoryStub._ARCHIVE_ROWS = seeded_rows


def test_fetch_macro_cpi_series_keeps_the_seeded_history_not_just_the_live_tail() -> None:
    """The honesty gate must drop only genuinely unofficial POINTS (arithmetic
    derivations, owner-pending rows) — not the entire pre-appender seeded
    archive. `macro_observer_seed` is real historical BB CPI data, not a
    fabrication; excluding it collapses the chart from 24 months to a stub."""
    _seed_cpi_fixture_realistic_24_months()
    out = chart_series_fetcher.fetch_macro_cpi_series(_CpiMonthlyHistoryStub(), months=24)

    # 12m-avg: 20 seeded + 4 official, nothing excluded → all 24 survive.
    assert len(out["cpi_12m_avg_monthly"]) == 24
    # food/non-food: 20 seeded + 3 official; the July point is excluded → 23.
    assert len(out["cpi_p2p_food_monthly"]) == 23
    assert len(out["cpi_p2p_nonfood_monthly"]) == 23

    # The seeded history itself must still be present, not just the live tail.
    food_ts = {p.ts for p in out["cpi_p2p_food_monthly"]}
    assert "2024-08-01" in food_ts, (
        "seeded history (source=macro_observer_seed) was dropped — the chart "
        "would show only the last few months instead of a real 24-month trend"
    )
