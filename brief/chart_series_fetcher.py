"""Phase E.2 — chart series fetchers.

Pure functions that pull time-series from Supabase tables and return
`SeriesPointV6` (and optionally `SeriesNoteV6`) objects ready to be stamped
onto `BriefPayloadV6.sections[i].series`.

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

# Yield curve canonical keys — month → "yield_Ny" lowercase, consistent with
# EconDelta `chartConfigs` so frontend dataset names line up trivially.
_YIELD_TENOR_KEY_BY_MONTHS: dict[int, str] = {
    24: "yield_2y",
    60: "yield_5y",
    120: "yield_10y",
    240: "yield_20y",
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
    """Pull last `days` of DSEX daily closes from `tb_dsex_daily`.

    Every row produces a SeriesPointV6 keyed 'dsex'. Rows with both
    `show_label = true` and a non-null `event` field additionally produce a
    SeriesNoteV6 (event → label, ts = date, series_key='dsex').
    """
    cutoff: date_t = today - timedelta(days=days)
    q: str = urllib.parse.urlencode(
        {
            "date": f"gte.{cutoff.isoformat()}",
            "select": "date,close,event,show_label",
            "order": "date.asc",
        }
    )
    url: str = f"{supabase_url.rstrip('/')}/rest/v1/tb_dsex_daily?{q}"
    rows: list[dict[str, Any]] = _safe_get(http, url, service_key=service_key)
    series: list[SeriesPointV6] = []
    notes: list[SeriesNoteV6] = []
    for row in rows:
        ts: Any = row.get("date")
        close: float | None = _coerce_float(row.get("close"))
        if close is None or not isinstance(ts, str):
            continue
        series.append(SeriesPointV6(key="dsex", ts=ts, value=close))
        event: Any = row.get("event")
        show_label: Any = row.get("show_label")
        if show_label is True and isinstance(event, str) and event.strip():
            notes.append(SeriesNoteV6(series_key="dsex", ts=ts, label=event))
    return series, notes


def fetch_brent(
    *,
    http: HttpClient,
    supabase_url: str,
    service_key: str,
    today: date_t,
    days: int = 90,
) -> list[SeriesPointV6]:
    """Pull last `days` of Brent prices from `tb_brent_daily`.

    Returns SeriesPointV6 list keyed 'brent', ts=date, value=price_usd.
    """
    cutoff: date_t = today - timedelta(days=days)
    q: str = urllib.parse.urlencode(
        {
            "date": f"gte.{cutoff.isoformat()}",
            "select": "date,price_usd",
            "order": "date.asc",
        }
    )
    url: str = f"{supabase_url.rstrip('/')}/rest/v1/tb_brent_daily?{q}"
    rows: list[dict[str, Any]] = _safe_get(http, url, service_key=service_key)
    out: list[SeriesPointV6] = []
    for row in rows:
        ts: Any = row.get("date")
        price: float | None = _coerce_float(row.get("price_usd"))
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
    """Pull last `snapshots` of yield-curve snapshots from `tb_yield_curve`.

    Filters to canonical 4 tenors (2Y/5Y/10Y/20Y) via tenor_months, normalizes
    keys to 'yield_Ny' (lowercase y suffix). Tenors outside the canonical set
    (e.g. 91-day, 6-month) are dropped.

    Snapshot windowing is approximate: we fetch a generous date window
    (snapshots × 35 days) since snapshot cadence isn't guaranteed weekly.
    """
    # Fetch generously, keyed on snapshot_date. 35 days per snapshot leaves
    # headroom for irregular publish cadence; the order=asc + downstream
    # render layer handle deduplication if too many rows come back.
    cutoff: date_t = today - timedelta(days=snapshots * 35)
    months_csv: str = ",".join(str(m) for m in _YIELD_TENOR_KEY_BY_MONTHS.keys())
    q: str = urllib.parse.urlencode(
        {
            "snapshot_date": f"gte.{cutoff.isoformat()}",
            "tenor_months": f"in.({months_csv})",
            "select": "snapshot_date,tenor,tenor_months,yield_pct",
            "order": "snapshot_date.asc,tenor_months.asc",
        }
    )
    url: str = f"{supabase_url.rstrip('/')}/rest/v1/tb_yield_curve?{q}"
    rows: list[dict[str, Any]] = _safe_get(http, url, service_key=service_key)
    out: list[SeriesPointV6] = []
    for row in rows:
        ts: Any = row.get("snapshot_date")
        tenor_months: Any = row.get("tenor_months")
        y: float | None = _coerce_float(row.get("yield_pct"))
        if (
            y is None
            or not isinstance(ts, str)
            or not isinstance(tenor_months, int)
            or tenor_months not in _YIELD_TENOR_KEY_BY_MONTHS
        ):
            continue
        key: str = _YIELD_TENOR_KEY_BY_MONTHS[tenor_months]
        out.append(SeriesPointV6(key=key, ts=ts, value=y))
    return out


def fetch_lng(
    *,
    http: HttpClient,
    supabase_url: str,
    service_key: str,
    today: date_t,
    weeks: int = 26,
) -> list[SeriesPointV6]:
    """Pull last `weeks` of LNG JKM weekly prices from `tb_lng_jkm_weekly`.

    Returns SeriesPointV6 keyed 'lng_jkm', ts=week_start, value=price_usd_mmbtu.
    """
    cutoff: date_t = today - timedelta(weeks=weeks)
    q: str = urllib.parse.urlencode(
        {
            "week_start": f"gte.{cutoff.isoformat()}",
            "select": "week_start,price_usd_mmbtu",
            "order": "week_start.asc",
        }
    )
    url: str = f"{supabase_url.rstrip('/')}/rest/v1/tb_lng_jkm_weekly?{q}"
    rows: list[dict[str, Any]] = _safe_get(http, url, service_key=service_key)
    out: list[SeriesPointV6] = []
    for row in rows:
        ts: Any = row.get("week_start")
        price: float | None = _coerce_float(row.get("price_usd_mmbtu"))
        if price is None or not isinstance(ts, str):
            continue
        out.append(SeriesPointV6(key="lng_jkm", ts=ts, value=price))
    return out
