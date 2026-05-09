"""Phase E.2 — chart series fetchers.

Pure functions that pull time-series from `metric_history` (the EconDelta-fed
canonical store) and return `SeriesPointV6` (and optionally `SeriesNoteV6`)
objects ready to be stamped onto `BriefPayloadV6.sections[i].series`.

All four fetchers query the same `metric_history` table with different
`metric_id` filters. The legacy `tb_brent_daily` / `tb_dsex_daily` /
`tb_yield_curve` tables are frozen (last writer was the deleted
`the-brief/ingest.py` from V6 cutover, commit 2317436); the live data now
flows through EconDelta scrapers into `metric_history` under different ids.

Each fetcher accepts an injectable `HttpClient` (mirrors
`brief.history.MetricHistoryClient`'s seam) so tests can mock without hitting
the network. Failures degrade to empty list — the SPA hides chart slots
when the series array is empty.
"""
from __future__ import annotations

import logging
import urllib.parse
from datetime import date as date_t
from datetime import timedelta
from typing import Any

from brief.history import HttpClient
from brief.v6_schema import SeriesNoteV6, SeriesPointV6

logger = logging.getLogger(__name__)

# Per-section knobs — kept module-level so a future change can adjust without
# editing call sites.

_FX_METRIC_IDS: tuple[str, ...] = (
    "monthly_export",
    "monthly_remittance",
    "monthly_import",
)

_BRENT_METRIC_ID: str = "brent_crude_usd_barrel"
_DSEX_METRIC_ID: str = "dsex"

# Yield curve canonical keys — metric_id → "yield_<tenor>" matching
# lib/chartConfigs.ts tenorMap. Five tenors live in metric_history:
# 3M / 6M / 1Y T-bills, plus 5Y / 10Y T-bonds.
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
