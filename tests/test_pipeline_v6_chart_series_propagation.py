"""Phase E.2 — backend chart series enricher.

After the LLM produces final_brief, a deterministic helper fetches time-series
from `metric_history` and stamps it onto `final_brief.sections[i].series` so
the SPA can render charts. Four sections are chartable (fx/dse/iran/tbond);
all others get an empty series list and the frontend hides their chart slot.

Coverage:
  1. `_CHART_FETCHERS_BY_SLUG` dispatch table contains exactly the 4 chartable
     slugs and no others (LNG/comm dropped post-V6 chart repoint).
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
from datetime import date
from typing import Any

import pytest

from brief import chart_series_fetcher, pipeline_v6
from brief.history import HttpClient
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


def test_chart_fetchers_by_slug_only_includes_4_chartable_sections() -> None:
    """The dispatch dict contains exactly fx/dse/iran/tbond — nothing else."""
    assert set(pipeline_v6._CHART_FETCHERS_BY_SLUG.keys()) == {
        "fx",
        "dse",
        "iran",
        "tbond",
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
    ["fetch_fx_flows", "fetch_dsex", "fetch_brent", "fetch_yield_curve"],
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


def test_stamp_chart_series_populates_4_sections_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only fx/dse/iran/tbond get series; other sections (incl. comm) stay empty."""
    fx_series: list[SeriesPointV6] = [SeriesPointV6(key="monthly_export", ts="2026-04-30", value=4.2)]
    dsex_series: list[SeriesPointV6] = [SeriesPointV6(key="dsex", ts="2026-05-01", value=5210.0)]
    dsex_notes: list[SeriesNoteV6] = []
    brent_series: list[SeriesPointV6] = [SeriesPointV6(key="brent", ts="2026-05-08", value=91.2)]
    yc_series: list[SeriesPointV6] = [SeriesPointV6(key="yield_5y", ts="2026-05-01", value=7.5)]

    def _fake_fx(**_: Any) -> list[SeriesPointV6]:
        return fx_series

    def _fake_dsex(**_: Any) -> tuple[list[SeriesPointV6], list[SeriesNoteV6]]:
        return dsex_series, dsex_notes

    def _fake_brent(**_: Any) -> list[SeriesPointV6]:
        return brent_series

    def _fake_yc(**_: Any) -> list[SeriesPointV6]:
        return yc_series

    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_flows", _fake_fx)
    monkeypatch.setattr(chart_series_fetcher, "fetch_dsex", _fake_dsex)
    monkeypatch.setattr(chart_series_fetcher, "fetch_brent", _fake_brent)
    monkeypatch.setattr(chart_series_fetcher, "fetch_yield_curve", _fake_yc)

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
    assert by_slug["fx"].series == fx_series
    assert by_slug["dse"].series == dsex_series
    assert by_slug["dse"].notes == dsex_notes
    assert by_slug["iran"].series == brent_series
    assert by_slug["tbond"].series == yc_series

    # Non-chartable (incl. comm post-LNG-drop): empty
    for slug in ("headlines", "bb", "banking", "fiscal", "macro", "remit", "comm"):
        assert by_slug[slug].series == [], f"{slug} should have empty series"
        assert by_slug[slug].notes == [], f"{slug} should have empty notes"


def test_stamp_chart_series_handles_fetcher_exception_gracefully(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If one fetcher raises, others still succeed; pipeline does not crash."""
    fx_series: list[SeriesPointV6] = [SeriesPointV6(key="monthly_export", ts="2026-04-30", value=4.2)]
    brent_series: list[SeriesPointV6] = [SeriesPointV6(key="brent", ts="2026-05-08", value=91.2)]

    def _ok_fx(**_: Any) -> list[SeriesPointV6]:
        return fx_series

    def _bad_dsex(**_: Any) -> tuple[list[SeriesPointV6], list[SeriesNoteV6]]:
        raise RuntimeError("simulated network blip")

    def _ok_brent(**_: Any) -> list[SeriesPointV6]:
        return brent_series

    def _empty_yc(**_: Any) -> list[SeriesPointV6]:
        return []

    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_flows", _ok_fx)
    monkeypatch.setattr(chart_series_fetcher, "fetch_dsex", _bad_dsex)
    monkeypatch.setattr(chart_series_fetcher, "fetch_brent", _ok_brent)
    monkeypatch.setattr(chart_series_fetcher, "fetch_yield_curve", _empty_yc)

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
    assert by_slug["fx"].series == fx_series, "fx still stamped despite dsex failure"
    assert by_slug["iran"].series == brent_series, "iran still stamped despite dsex failure"
    assert by_slug["dse"].series == [], "dse left empty after fetcher exception"
    assert by_slug["dse"].notes == [], "dse notes left empty after fetcher exception"
    # A warning should have been logged for the failing fetcher
    assert any(
        "dse" in record.getMessage().lower() or "dsex" in record.getMessage().lower()
        for record in caplog.records
    ), f"expected warning mentioning dse fetcher; got {[r.getMessage() for r in caplog.records]}"


def test_stamp_chart_series_skips_when_section_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A brief without 'fx' section just skips the fx fetcher; no crash."""
    called: list[str] = []

    def _ok_fx(**_: Any) -> list[SeriesPointV6]:
        called.append("fx")
        return []

    def _ok_dsex(**_: Any) -> tuple[list[SeriesPointV6], list[SeriesNoteV6]]:
        called.append("dse")
        return [], []

    def _ok_brent(**_: Any) -> list[SeriesPointV6]:
        called.append("iran")
        return []

    def _ok_yc(**_: Any) -> list[SeriesPointV6]:
        called.append("tbond")
        return []

    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_flows", _ok_fx)
    monkeypatch.setattr(chart_series_fetcher, "fetch_dsex", _ok_dsex)
    monkeypatch.setattr(chart_series_fetcher, "fetch_brent", _ok_brent)
    monkeypatch.setattr(chart_series_fetcher, "fetch_yield_curve", _ok_yc)

    # Brief with only bb + banking — none of the chartable slugs.
    minimal_brief: BriefPayloadV6 = BriefPayloadV6(
        brief=BriefV6(issue_no=1, volume=1, brief_date=TODAY),
        sections=[
            _make_section("bb", 3, "banking"),
            _make_section("banking", 4, "banking"),
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

    fx_series: list[SeriesPointV6] = [
        SeriesPointV6(key="monthly_export", ts="2026-04-30", value=4.2)
    ]

    def _fake_fx(**_: Any) -> list[SeriesPointV6]:
        return fx_series

    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_flows", _fake_fx)
    monkeypatch.setattr(
        chart_series_fetcher,
        "fetch_dsex",
        lambda **_: ([], []),
    )
    monkeypatch.setattr(chart_series_fetcher, "fetch_brent", lambda **_: [])
    monkeypatch.setattr(chart_series_fetcher, "fetch_yield_curve", lambda **_: [])

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
    assert by_slug["fx"].series == fx_series, (
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
    def _should_not_run(**_: Any) -> Any:
        raise AssertionError("fetcher should not run without supabase env")

    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_flows", _should_not_run)

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
    """Every dispatched fetcher receives http, supabase_url, service_key, today."""
    captured: list[dict[str, Any]] = []

    def _record(**kwargs: Any) -> list[SeriesPointV6]:
        captured.append(kwargs)
        return []

    def _record_dsex(**kwargs: Any) -> tuple[list[SeriesPointV6], list[SeriesNoteV6]]:
        captured.append(kwargs)
        return [], []

    monkeypatch.setattr(chart_series_fetcher, "fetch_fx_flows", _record)
    monkeypatch.setattr(chart_series_fetcher, "fetch_dsex", _record_dsex)
    monkeypatch.setattr(chart_series_fetcher, "fetch_brent", _record)
    monkeypatch.setattr(chart_series_fetcher, "fetch_yield_curve", _record)

    final_brief: BriefPayloadV6 = _full_brief()
    http: HttpClient = _http([])
    pipeline_v6._stamp_chart_series(
        final_brief,
        today=TODAY,
        http=http,
        supabase_url=SUPABASE_URL,
        service_key=SERVICE_KEY,
    )
    assert len(captured) == 4, "all 4 chartable fetchers should be dispatched"
    for kw in captured:
        assert kw["http"] is http
        assert kw["supabase_url"] == SUPABASE_URL
        assert kw["service_key"] == SERVICE_KEY
        assert kw["today"] == TODAY
