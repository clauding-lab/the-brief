"""Phase E.2 — chart series fetchers.

Pure functions that pull time-series from `metric_history` (the EconDelta-fed
canonical store) and return `SeriesPointV6` (and optionally `SeriesNoteV6`)
objects ready to be stamped onto `BriefPayloadV6.sections[i].series`.

All four original fetchers query the same `metric_history` table with different
`metric_id` filters. The legacy `tb_brent_daily` / `tb_dsex_daily` /
`tb_yield_curve` tables are frozen (last writer was the deleted
`the-brief/ingest.py` from V6 cutover, commit 2317436); the live data now
flows through EconDelta scrapers into `metric_history` under different ids.

v1.4.0: adds `fetch_macro_cpi_series` which reads from `metric_history_monthly`
(not `metric_history`) to fetch 24-month CPI series for the macro section's
cpiTrend chart. AGENTS.md landmine #1 — never reads tb_* tables.

Each fetcher accepts an injectable `HttpClient` (mirrors
`brief.history.MetricHistoryClient`'s seam) so tests can mock without hitting
the network. Failures degrade to empty list — the SPA hides chart slots
when the series array is empty.
"""
from __future__ import annotations

import calendar
import logging
import urllib.parse
from datetime import date as date_t
from datetime import timedelta
from typing import Any

from brief.history import HttpClient, MetricHistoryClient
from brief.v6_schema import MoverRowV6, SeriesNoteV6, SeriesPointV6

logger = logging.getLogger(__name__)

# Per-section knobs — kept module-level so a future change can adjust without
# editing call sites.

_FX_METRIC_IDS: tuple[str, ...] = (
    "monthly_export",
    "monthly_remittance",
    "monthly_import",
)

# F6 — §08 remittance 12-month chart (metric_history_monthly, USD mn).
_REMIT_MONTHLY_METRIC_IDS: tuple[str, ...] = ("remittance_usd_mn_monthly",)
_FISCAL_MONTHLY_METRIC_IDS: tuple[str, ...] = ("nbr_revenue_monthly_cr",)

# F3 — §fx external flow balance (metric_history_monthly, USD mn → bn in SPA).
_FX_BALANCE_MONTHLY_METRIC_IDS: tuple[str, ...] = (
    "exports_usd_mn_monthly",
    "imports_usd_mn_monthly",
    "remittance_usd_mn_monthly",
)

# F2 — §02 Policy & Rates reserves two-line chart (metric_history_monthly, USD bn).
_RESERVES_MONTHLY_METRIC_IDS: tuple[str, ...] = (
    "gross_reserves_usd_bn_monthly",
    "net_reserves_bpm6_usd_bn_monthly",
)

# F5 — §tbond full 8-tenor yield ladder (metric_history_monthly, yield %).
_YIELD_LADDER_MONTHLY_METRIC_IDS: tuple[str, ...] = (
    "tbill_91d_yield_monthly",
    "tbill_182d_yield_monthly",
    "tbill_364d_yield_monthly",
    "yield_2y_monthly",
    "yield_5y_monthly",
    "yield_10y_monthly",
    "yield_15y_monthly",
    "yield_20y_monthly",
)

_BRENT_METRIC_ID: str = "brent_crude_usd_barrel"
_DSEX_METRIC_ID: str = "dsex"

# F4 — DS30 blue-chip movers (per-ticker dse_close_*, computed at publish time).
_DSE_CLOSE_PREFIX: str = "dse_close_"
_DSE_MOVERS_PER_SIDE: int = 5
STALE_LAG_DAYS: int = 4  # per-ticker data must lag the dsex index by <= this many days

# Yield curve canonical keys — metric_id → "yield_<tenor>" matching
# lib/chartConfigs.ts tenorMap. Five tenors live in metric_history:
# 3M / 6M / 1Y T-bills, plus 5Y / 10Y T-bonds.
_CPI_METRIC_IDS: tuple[str, ...] = (
    "cpi_12m_avg_monthly",
    "cpi_p2p_food_monthly",
    "cpi_p2p_nonfood_monthly",
)

_YIELD_TENOR_KEY_BY_METRIC_ID: dict[str, str] = {
    "tbill_91d_yield_pct": "yield_3m",
    "tbill_182d_yield": "yield_6m",
    "tbill_364d_yield": "yield_1y",
    "tbond_bond_5y": "yield_5y",
    "tbond_bond_10y": "yield_10y",
}


# ─── HTTP helpers ──────────────────────────────────────────────────────


def _headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }


def _safe_get(http: HttpClient, url: str, *, service_key: str) -> list[dict[str, Any]]:
    """GET against PostgREST. On non-200 or non-list response, return empty list.

    Graceful-degradation: callers always get a list, never None, never an
    exception. PostgREST 4xx (e.g. unknown column) and 5xx are both logged at
    WARNING with the response body so schema drift surfaces in ops rather than
    failing silently. The enricher's per-section try/except in pipeline_v6
    still catches anything more pathological (e.g. http object blowing up).
    """
    status, body = http.get(url, headers=_headers(service_key))
    if status >= 400:
        logger.warning(
            "chart_series_fetcher: non-200 from PostgREST status=%s url=%s body=%r",
            status, url, body,
        )
        return []
    if status != 200 or not isinstance(body, list):
        return []
    return body


def _coerce_float(v: Any) -> float | None:
    """Cast numeric/numeric-string to float; None on failure. Filters bool."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


def _metric_history_url(
    *,
    supabase_url: str,
    metric_filter: str,
    cutoff: date_t,
) -> str:
    """Compose a PostgREST URL against `metric_history` with a metric_id filter.

    `metric_filter` is already PostgREST-formatted, e.g.
    `eq.brent_crude_usd_barrel` or `in.(a,b,c)`.
    """
    q: str = urllib.parse.urlencode(
        {
            "metric_id": metric_filter,
            "as_of": f"gte.{cutoff.isoformat()}",
            "select": "metric_id,as_of,value",
            "order": "as_of.asc",
        }
    )
    return f"{supabase_url.rstrip('/')}/rest/v1/metric_history?{q}"


# ─── Fetchers ──────────────────────────────────────────────────────────


def fetch_fx_flows(
    *,
    http: HttpClient,
    supabase_url: str,
    service_key: str,
    today: date_t,
    months: int = 12,
) -> list[SeriesPointV6]:
    """Pull last `months` of monthly_export / monthly_remittance / monthly_import
    points from `metric_history`. Returns one SeriesPointV6 per row, keyed by
    metric_id, ordered as Supabase returns them (asc by metric_id, as_of).
    """
    cutoff: date_t = today - timedelta(days=months * 31)
    ids_csv: str = ",".join(_FX_METRIC_IDS)
    q: str = urllib.parse.urlencode(
        {
            "metric_id": f"in.({ids_csv})",
            "as_of": f"gte.{cutoff.isoformat()}",
            "select": "metric_id,as_of,value",
            "order": "metric_id,as_of.asc",
        }
    )
    url: str = f"{supabase_url.rstrip('/')}/rest/v1/metric_history?{q}"
    rows: list[dict[str, Any]] = _safe_get(http, url, service_key=service_key)
    out: list[SeriesPointV6] = []
    for row in rows:
        value: float | None = _coerce_float(row.get("value"))
        as_of: Any = row.get("as_of")
        metric_id: Any = row.get("metric_id")
        if value is None or not isinstance(as_of, str) or not isinstance(metric_id, str):
            continue
        out.append(SeriesPointV6(key=metric_id, ts=as_of, value=value))
    return out


def fetch_dsex(
    *,
    http: HttpClient,
    supabase_url: str,
    service_key: str,
    today: date_t,
    days: int = 365,
) -> tuple[list[SeriesPointV6], list[SeriesNoteV6]]:
    """Pull last `days` of DSEX daily closes from `metric_history`
    (metric_id='dsex'). Returns (series, notes); notes is always empty since
    `metric_history` has no event/label columns — the legacy `tb_dsex_daily`
    show_label/event annotation feature is dropped.
    """
    cutoff: date_t = today - timedelta(days=days)
    url: str = _metric_history_url(
        supabase_url=supabase_url,
        metric_filter=f"eq.{_DSEX_METRIC_ID}",
        cutoff=cutoff,
    )
    rows: list[dict[str, Any]] = _safe_get(http, url, service_key=service_key)
    series: list[SeriesPointV6] = []
    for row in rows:
        ts: Any = row.get("as_of")
        close: float | None = _coerce_float(row.get("value"))
        if close is None or not isinstance(ts, str):
            continue
        series.append(SeriesPointV6(key="dsex", ts=ts, value=close))
    return series, []


def _minus_one_calendar_month(d: date_t) -> date_t:
    """Date one calendar month earlier, clamping day to the target month's length."""
    year: int = d.year - 1 if d.month == 1 else d.year
    month: int = 12 if d.month == 1 else d.month - 1
    last_day: int = calendar.monthrange(year, month)[1]
    return date_t(year, month, min(d.day, last_day))


def _latest_as_of(
    http: HttpClient, supabase_url: str, metric_filter: str, *, service_key: str
) -> date_t | None:
    """Most recent `as_of` for a metric_id filter (e.g. 'eq.dsex'), or None."""
    q: str = urllib.parse.urlencode(
        {"metric_id": metric_filter, "select": "as_of", "order": "as_of.desc", "limit": "1"}
    )
    rows: list[dict[str, Any]] = _safe_get(
        http, f"{supabase_url.rstrip('/')}/rest/v1/metric_history?{q}", service_key=service_key
    )
    raw: Any = rows[0].get("as_of") if rows else None
    if not isinstance(raw, str):
        return None
    try:
        return date_t.fromisoformat(raw)
    except ValueError:
        return None


def fetch_dse_movers(
    *,
    http: HttpClient,
    supabase_url: str,
    service_key: str,
    today: date_t,
) -> list[MoverRowV6] | None:
    """DS30 1-month movers: up to 5 gainers (return>0, desc) + 5 losers (<0, asc),
    each {ticker, price, return_pct}, computed from `dse_close_*` in metric_history.

    Returns None when per-ticker data is stale vs the live DSEX index (freshness
    gate) or unavailable — the SPA then renders nothing, so F4 ships dark until
    EconDelta writes dse_close_* daily. Calendar-month return; the prior anchor
    is the most recent close at/before (latest_as_of - 1 month).

    AGENTS.md landmine #14: bounded queries (latest-date slice + a small prior
    window), never an unbounded dse_close_* pull (30 tickers x history > 1000).

    `today` is accepted for dispatch-signature parity with the other fetchers but
    unused — the calendar-month anchor is derived from the DB's latest `dse_close_*`
    date, not wall-clock today.
    """
    data_latest: date_t | None = _latest_as_of(
        http, supabase_url, f"like.{_DSE_CLOSE_PREFIX}*", service_key=service_key
    )
    idx_latest: date_t | None = _latest_as_of(
        http, supabase_url, f"eq.{_DSEX_METRIC_ID}", service_key=service_key
    )
    if data_latest is None or idx_latest is None:
        return None
    if (idx_latest - data_latest).days > STALE_LAG_DAYS:  # freshness gate
        return None

    cur_q: str = urllib.parse.urlencode(
        {
            "metric_id": f"like.{_DSE_CLOSE_PREFIX}*",
            "as_of": f"eq.{data_latest.isoformat()}",
            "select": "metric_id,value",
            "limit": "100",  # landmine #14: 30 DS30 tickers → ≤30 rows; 100 headroom, never truncates
        }
    )
    latest_by_ticker: dict[str, float] = {}
    for row in _safe_get(
        http, f"{supabase_url.rstrip('/')}/rest/v1/metric_history?{cur_q}", service_key=service_key
    ):
        mid: Any = row.get("metric_id")
        val: float | None = _coerce_float(row.get("value"))
        if isinstance(mid, str) and val is not None:
            latest_by_ticker[mid] = val
    if not latest_by_ticker:
        return None

    target: date_t = _minus_one_calendar_month(data_latest)
    window_lo: date_t = target - timedelta(days=15)
    prior_q: str = urllib.parse.urlencode(
        [
            ("metric_id", f"like.{_DSE_CLOSE_PREFIX}*"),
            ("as_of", f"gte.{window_lo.isoformat()}"),
            ("as_of", f"lte.{target.isoformat()}"),
            ("select", "metric_id,as_of,value"),
            ("order", "as_of.desc"),
            # landmine #14: ≈300 rows expected in the 15-day window; 500 headroom.
            # desc order means each ticker's most-recent-≤-target is among the newest
            # rows, so correctness holds even at the cap.
            ("limit", "500"),
        ]
    )
    prior_by_ticker: dict[str, float] = {}
    for row in _safe_get(
        http, f"{supabase_url.rstrip('/')}/rest/v1/metric_history?{prior_q}", service_key=service_key
    ):
        mid = row.get("metric_id")
        val = _coerce_float(row.get("value"))
        if isinstance(mid, str) and val is not None and mid not in prior_by_ticker:
            prior_by_ticker[mid] = val  # desc order → first seen is most recent <= target

    movers: list[MoverRowV6] = []
    for mid, latest_price in latest_by_ticker.items():
        prior_price: float | None = prior_by_ticker.get(mid)
        if prior_price is None or prior_price == 0:
            continue
        ret: float = round((latest_price / prior_price - 1) * 100, 2)
        movers.append(
            MoverRowV6(ticker=mid[len(_DSE_CLOSE_PREFIX):], price=latest_price, return_pct=ret)
        )

    gainers: list[MoverRowV6] = sorted(
        [m for m in movers if m.return_pct > 0], key=lambda m: (-m.return_pct, m.ticker)
    )[:_DSE_MOVERS_PER_SIDE]
    losers: list[MoverRowV6] = sorted(
        [m for m in movers if m.return_pct < 0], key=lambda m: (m.return_pct, m.ticker)
    )[:_DSE_MOVERS_PER_SIDE]
    result: list[MoverRowV6] = gainers + losers
    return result or None


def fetch_brent(
    *,
    http: HttpClient,
    supabase_url: str,
    service_key: str,
    today: date_t,
    days: int = 90,
) -> list[SeriesPointV6]:
    """Pull last `days` of Brent prices from `metric_history`
    (metric_id='brent_crude_usd_barrel'). SeriesPointV6 list keyed 'brent'.
    """
    cutoff: date_t = today - timedelta(days=days)
    url: str = _metric_history_url(
        supabase_url=supabase_url,
        metric_filter=f"eq.{_BRENT_METRIC_ID}",
        cutoff=cutoff,
    )
    rows: list[dict[str, Any]] = _safe_get(http, url, service_key=service_key)
    out: list[SeriesPointV6] = []
    for row in rows:
        ts: Any = row.get("as_of")
        price: float | None = _coerce_float(row.get("value"))
        if price is None or not isinstance(ts, str):
            continue
        out.append(SeriesPointV6(key="brent", ts=ts, value=price))
    return out


def fetch_macro_cpi_series(
    history_monthly: MetricHistoryClient,
    *,
    months: int = 24,
) -> dict[str, list[SeriesPointV6]]:
    """Pull `months` rows of the three CPI series from `metric_history_monthly`.

    Returns a dict keyed by metric_id, each value a list of SeriesPointV6
    objects ordered chronologically (oldest-first) for the SPA chart renderer.

    AGENTS.md landmine #1: reads from metric_history_monthly, NOT tb_* tables.
    AGENTS.md landmine #6: uses _monthly-suffixed metric IDs.
    """
    grouped = history_monthly.get_history_window(
        _CPI_METRIC_IDS,
        limit=months * len(_CPI_METRIC_IDS),
        table="metric_history_monthly",
    )
    out: dict[str, list[SeriesPointV6]] = {}
    for mid in _CPI_METRIC_IDS:
        rows = grouped.get(mid, [])
        # rows are most-recent-first from PostgREST anchor mode; flip to chronological
        points: list[SeriesPointV6] = [
            SeriesPointV6(key=mid, ts=r.as_of.isoformat(), value=r.value)
            for r in reversed(rows)
        ]
        out[mid] = points
    return out


def fetch_remit_monthly(
    history_monthly: MetricHistoryClient,
    *,
    months: int = 12,
) -> dict[str, list[SeriesPointV6]]:
    """Pull `months` rows of monthly remittance from `metric_history_monthly`.

    Single-series sibling of `fetch_macro_cpi_series`; returns a dict keyed by
    metric_id with chronological (oldest-first) SeriesPointV6 lists.

    AGENTS.md landmine #1: reads metric_history_monthly, NOT tb_* tables.
    AGENTS.md landmine #6: uses the _monthly-suffixed metric ID.
    AGENTS.md landmine #14: limit is months * len(ids) (per-id, not global).
    """
    grouped = history_monthly.get_history_window(
        _REMIT_MONTHLY_METRIC_IDS,
        limit=months * len(_REMIT_MONTHLY_METRIC_IDS),
        table="metric_history_monthly",
    )
    out: dict[str, list[SeriesPointV6]] = {}
    for mid in _REMIT_MONTHLY_METRIC_IDS:
        rows = grouped.get(mid, [])
        out[mid] = [
            SeriesPointV6(key=mid, ts=r.as_of.isoformat(), value=r.value)
            for r in reversed(rows)
        ]
    return out


def fetch_fiscal_monthly(
    history_monthly: MetricHistoryClient,
    *,
    months: int = 30,
) -> dict[str, list[SeriesPointV6]]:
    """Pull `months` rows of monthly NBR tax revenue from `metric_history_monthly`
    for the F7b §fiscal chart (single-month figures, BDT crore).

    Single-series sibling of `fetch_remit_monthly`; returns a dict keyed by
    metric_id with chronological (oldest-first) SeriesPointV6 lists. months=30
    covers the ~28 backfilled months (Jul'23..Oct'25) with headroom.

    AGENTS.md landmine #1: reads metric_history_monthly, NOT tb_* tables.
    AGENTS.md landmine #6: uses the _monthly/_cr-suffixed EconDelta metric ID.
    AGENTS.md landmine #14: limit is months * len(ids) (per-id, not global).
    """
    grouped = history_monthly.get_history_window(
        _FISCAL_MONTHLY_METRIC_IDS,
        limit=months * len(_FISCAL_MONTHLY_METRIC_IDS),
        table="metric_history_monthly",
    )
    out: dict[str, list[SeriesPointV6]] = {}
    for mid in _FISCAL_MONTHLY_METRIC_IDS:
        rows = grouped.get(mid, [])
        out[mid] = [
            SeriesPointV6(key=mid, ts=r.as_of.isoformat(), value=r.value)
            for r in reversed(rows)
        ]
    return out


def fetch_fx_balance_monthly(
    history_monthly: MetricHistoryClient,
    *,
    months: int = 24,
) -> dict[str, list[SeriesPointV6]]:
    """Pull `months` of exports / imports / remittance from `metric_history_monthly`
    for the F3 §fx External Flow Balance chart (USD mn; SPA converts to bn).

    Multi-series sibling of `fetch_macro_cpi_series`; dict keyed by metric_id,
    chronological (oldest-first). The net basic balance is computed in the SPA
    config, not here.

    AGENTS.md landmine #1: reads metric_history_monthly, NOT tb_* tables.
    AGENTS.md landmine #6: uses the _monthly-suffixed metric IDs.
    AGENTS.md landmine #14: limit is months * len(ids) (per-id, not global).
    """
    grouped = history_monthly.get_history_window(
        _FX_BALANCE_MONTHLY_METRIC_IDS,
        limit=months * len(_FX_BALANCE_MONTHLY_METRIC_IDS),
        table="metric_history_monthly",
    )
    out: dict[str, list[SeriesPointV6]] = {}
    for mid in _FX_BALANCE_MONTHLY_METRIC_IDS:
        rows = grouped.get(mid, [])
        out[mid] = [
            SeriesPointV6(key=mid, ts=r.as_of.isoformat(), value=r.value)
            for r in reversed(rows)
        ]
    return out


def fetch_reserves_monthly(
    history_monthly: MetricHistoryClient,
    *,
    months: int = 13,
) -> dict[str, list[SeriesPointV6]]:
    """Pull `months` rows of gross + net (BPM6) reserves from
    `metric_history_monthly` for the F2 §02 two-line chart (USD bn).

    Multi-series sibling of `fetch_macro_cpi_series`; returns a dict keyed by
    metric_id with chronological (oldest-first) SeriesPointV6 lists.

    AGENTS.md landmine #1: reads metric_history_monthly, NOT tb_* tables.
    AGENTS.md landmine #6: uses the _monthly-suffixed metric IDs.
    AGENTS.md landmine #14: limit is months * len(ids) (per-id, not global).
    """
    grouped = history_monthly.get_history_window(
        _RESERVES_MONTHLY_METRIC_IDS,
        limit=months * len(_RESERVES_MONTHLY_METRIC_IDS),
        table="metric_history_monthly",
    )
    out: dict[str, list[SeriesPointV6]] = {}
    for mid in _RESERVES_MONTHLY_METRIC_IDS:
        rows = grouped.get(mid, [])
        out[mid] = [
            SeriesPointV6(key=mid, ts=r.as_of.isoformat(), value=r.value)
            for r in reversed(rows)
        ]
    return out


def fetch_yield_ladder_monthly(
    history_monthly: MetricHistoryClient,
    *,
    months: int = 2,
) -> dict[str, list[SeriesPointV6]]:
    """Pull `months` month-ends of the 8 govt yield tenors from
    `metric_history_monthly` for the F5 §tbond yield-ladder chart (yield %).

    Multi-series sibling of `fetch_macro_cpi_series`; returns a dict keyed by
    tenor metric_id with chronological (oldest-first) SeriesPointV6 lists. The
    SPA's yieldLadder config pivots these into a category (tenor) x-axis with
    one line per month-end.

    AGENTS.md landmine #1: reads metric_history_monthly, NOT tb_* tables.
    AGENTS.md landmine #6: uses the _monthly-suffixed metric IDs.
    AGENTS.md landmine #14: limit is months * len(ids) (per-id, not global).
    """
    grouped = history_monthly.get_history_window(
        _YIELD_LADDER_MONTHLY_METRIC_IDS,
        limit=months * len(_YIELD_LADDER_MONTHLY_METRIC_IDS),
        table="metric_history_monthly",
    )
    out: dict[str, list[SeriesPointV6]] = {}
    for mid in _YIELD_LADDER_MONTHLY_METRIC_IDS:
        rows = grouped.get(mid, [])
        out[mid] = [
            SeriesPointV6(key=mid, ts=r.as_of.isoformat(), value=r.value)
            for r in reversed(rows)
        ]
    return out


def fetch_yield_curve(
    *,
    http: HttpClient,
    supabase_url: str,
    service_key: str,
    today: date_t,
    snapshots: int = 12,
) -> list[SeriesPointV6]:
    """Pull last `snapshots` of yield-curve snapshots from `metric_history`.

    Queries 5 metric_ids in one round-trip (`metric_id=in.(...)`), one row per
    (metric_id, as_of). Maps metric_id → 'yield_<tenor>' key consistent with
    `lib/chartConfigs.ts` tenorMap (3M, 6M, 1Y, 5Y, 10Y). Unknown metric_ids
    are dropped.

    Snapshot windowing is approximate: a generous date window
    (snapshots × 35 days) covers irregular publish cadence.
    """
    cutoff: date_t = today - timedelta(days=snapshots * 35)
    ids_csv: str = ",".join(_YIELD_TENOR_KEY_BY_METRIC_ID.keys())
    url: str = _metric_history_url(
        supabase_url=supabase_url,
        metric_filter=f"in.({ids_csv})",
        cutoff=cutoff,
    )
    rows: list[dict[str, Any]] = _safe_get(http, url, service_key=service_key)
    out: list[SeriesPointV6] = []
    for row in rows:
        ts: Any = row.get("as_of")
        metric_id: Any = row.get("metric_id")
        y: float | None = _coerce_float(row.get("value"))
        if (
            y is None
            or not isinstance(ts, str)
            or not isinstance(metric_id, str)
            or metric_id not in _YIELD_TENOR_KEY_BY_METRIC_ID
        ):
            continue
        key: str = _YIELD_TENOR_KEY_BY_METRIC_ID[metric_id]
        out.append(SeriesPointV6(key=key, ts=ts, value=y))
    return out
