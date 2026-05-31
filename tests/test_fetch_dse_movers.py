"""Unit tests for fetch_dse_movers (F4 — DS30 Movers)."""
from __future__ import annotations

from datetime import date

from brief.chart_series_fetcher import STALE_LAG_DAYS, fetch_dse_movers
from brief.v6_schema import MoverRowV6


class _FakeHttp:
    """Routes GETs by URL substring to canned (status, body) PostgREST replies."""

    def __init__(self, *, idx_latest, data_latest, current, prior):
        self.idx_latest = idx_latest
        self.data_latest = data_latest
        self.current = current  # list[{metric_id, value}] on the latest date
        self.prior = prior      # list[{metric_id, as_of, value}] in the prior window

    def get(self, url, headers=None):
        if "metric_id=eq.dsex" in url:
            return 200, [{"as_of": self.idx_latest}]
        # latest dse_close_* date probe — match limit=1 precisely so it does not
        # also catch the current-slice query's limit=100 ("limit=1" is a substring
        # of "limit=100"). The probe omits as_of, so anchor on that distinction.
        if "limit=1&" in url or url.endswith("limit=1"):
            return 200, [{"as_of": self.data_latest}]
        if f"as_of=eq.{self.data_latest}" in url:
            return 200, self.current
        return 200, self.prior  # prior window


def _curr(pairs):  # {TICKER: price}
    return [{"metric_id": f"dse_close_{t}", "value": v} for t, v in pairs.items()]


def _prior(rows):  # list of (TICKER, as_of, price)
    return [{"metric_id": f"dse_close_{t}", "as_of": d, "value": v} for t, d, v in rows]


def test_returns_gainers_then_losers_with_calendar_month_return():
    http = _FakeHttp(
        idx_latest="2026-05-24", data_latest="2026-05-24",
        current=_curr({"FINEFOODS": 577.0, "CITYBANK": 28.7, "GP": 300.0}),
        prior=_prior([
            ("FINEFOODS", "2026-04-23", 495.0),
            ("CITYBANK", "2026-04-23", 32.4),
            ("GP", "2026-04-23", 300.0),
        ]),
    )
    out = fetch_dse_movers(http=http, supabase_url="https://x", service_key="k", today=date(2026, 5, 31))
    assert out is not None
    assert all(isinstance(m, MoverRowV6) for m in out)
    tickers = [m.ticker for m in out]
    assert tickers == ["FINEFOODS", "CITYBANK"]
    fine = next(m for m in out if m.ticker == "FINEFOODS")
    assert fine.price == 577.0 and fine.return_pct == 16.57


def test_freshness_gate_returns_none_when_data_lags_index():
    http = _FakeHttp(
        idx_latest="2026-05-31", data_latest="2026-05-24",
        current=_curr({"FINEFOODS": 577.0}), prior=_prior([("FINEFOODS", "2026-04-23", 495.0)]),
    )
    assert STALE_LAG_DAYS == 4
    assert fetch_dse_movers(http=http, supabase_url="https://x", service_key="k", today=date(2026, 5, 31)) is None


def test_returns_none_when_no_data():
    class _Empty:
        def get(self, url, headers=None):
            return 200, []
    assert fetch_dse_movers(http=_Empty(), supabase_url="https://x", service_key="k", today=date(2026, 5, 31)) is None


def test_skips_ticker_missing_prior_anchor():
    http = _FakeHttp(
        idx_latest="2026-05-24", data_latest="2026-05-24",
        current=_curr({"FINEFOODS": 577.0, "ROBI": 30.2}),
        prior=_prior([("FINEFOODS", "2026-04-23", 495.0)]),
    )
    out = fetch_dse_movers(http=http, supabase_url="https://x", service_key="k", today=date(2026, 5, 31))
    assert [m.ticker for m in out] == ["FINEFOODS"]


def test_freshness_gate_passes_at_boundary():
    # lag == STALE_LAG_DAYS (4 days) must PASS the gate
    http = _FakeHttp(
        idx_latest="2026-05-28", data_latest="2026-05-24",
        current=_curr({"FINEFOODS": 577.0}),
        prior=_prior([("FINEFOODS", "2026-04-23", 495.0)]),
    )
    assert fetch_dse_movers(http=http, supabase_url="https://x", service_key="k", today=date(2026, 5, 31)) is not None


def test_freshness_gate_fails_one_past_boundary():
    # lag == STALE_LAG_DAYS + 1 (5 days) must FAIL the gate
    http = _FakeHttp(
        idx_latest="2026-05-29", data_latest="2026-05-24",
        current=_curr({"FINEFOODS": 577.0}),
        prior=_prior([("FINEFOODS", "2026-04-23", 495.0)]),
    )
    assert fetch_dse_movers(http=http, supabase_url="https://x", service_key="k", today=date(2026, 5, 31)) is None


def test_calendar_month_clamps_to_short_february():
    http = _FakeHttp(
        idx_latest="2026-03-31", data_latest="2026-03-31",
        current=_curr({"FINEFOODS": 600.0}),
        prior=_prior([("FINEFOODS", "2026-02-26", 500.0)]),
    )
    out = fetch_dse_movers(http=http, supabase_url="https://x", service_key="k", today=date(2026, 4, 1))
    assert out is not None and out[0].ticker == "FINEFOODS" and out[0].return_pct == 20.0


def test_prior_window_uses_most_recent_on_or_before_target():
    # PostgREST returns order=as_of.desc; fake passes prior through verbatim.
    http = _FakeHttp(
        idx_latest="2026-05-24", data_latest="2026-05-24",
        current=_curr({"FINEFOODS": 600.0}),
        prior=_prior([
            ("FINEFOODS", "2026-04-23", 500.0),  # most recent <= target (2026-04-24) → should win
            ("FINEFOODS", "2026-04-10", 400.0),  # older, must be ignored
        ]),
    )
    out = fetch_dse_movers(http=http, supabase_url="https://x", service_key="k", today=date(2026, 5, 31))
    # 600/500 - 1 = +20.0 (uses 500, NOT 400 which would give +50.0)
    assert out is not None and out[0].return_pct == 20.0
