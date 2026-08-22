"""Supabase `metric_history` client — HTTP seam, JSON body.

Abstracts PostgREST so tests inject a mock `http` object with `.get()`/`.post()`
returning `(status, json_body_or_none)`. Production passes a urllib wrapper.
"""
from __future__ import annotations

import json as _json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class HistoryRow:
    metric_id: str
    as_of: date
    value: Any
    source: str


@runtime_checkable
class HttpClient(Protocol):
    def get(self, url: str, *, headers: dict[str, str]) -> tuple[int, Any]: ...
    def post(self, url: str, *, headers: dict[str, str], json: Any) -> tuple[int, Any]: ...


class UrllibHttp:
    def get(self, url: str, *, headers: dict[str, str]) -> tuple[int, Any]:  # pragma: no cover
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, _json.loads(resp.read() or b"null")

    def post(self, url: str, *, headers: dict[str, str], json: Any) -> tuple[int, Any]:  # pragma: no cover
        req = urllib.request.Request(
            url,
            data=_json.dumps(json).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
            return resp.status, (_json.loads(body) if body else None)


class MetricHistoryClient:
    def __init__(self, *, url: str, service_key: str, http: HttpClient | None = None):
        self.url = url.rstrip("/")
        self.key = service_key
        self.http = http or UrllibHttp()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def get_latest(self, metric_id: str, *, table: str = "metric_history") -> HistoryRow | None:
        """Fetch the most recent row for `metric_id` from `table`.

        `table` defaults to 'metric_history'. Pass 'metric_history_monthly' to
        read the long-horizon monthly archive used by history_anchors.
        """
        url = (
            f"{self.url}/rest/v1/{table}"
            f"?metric_id=eq.{urllib.parse.quote(metric_id)}"
            "&order=as_of.desc&limit=1"
        )
        status, body = self.http.get(url, headers=self._headers())
        if status != 200 or not body:
            return None
        row = body[0]
        return HistoryRow(
            metric_id=row["metric_id"],
            as_of=date.fromisoformat(row["as_of"]),
            value=float(row["value"]) if isinstance(row["value"], (int, float, str)) else row["value"],
            source=row["source"],
        )

    def get_at_or_before(
        self, metric_id: str, as_of: date, *, table: str = "metric_history"
    ) -> HistoryRow | None:
        """Fetch the most recent row for `metric_id` dated at or before `as_of`.

        Needed for period-consistent derivations (P0 honesty fix, 2026-08-22
        audit #204): pairing "latest repo rate" with "latest inflation reading"
        silently mixes vintages when a rate cut lands between the two prints. A
        Jun inflation print must pair with the Jun repo rate — this fetches
        exactly that, walking backward from `as_of` rather than always reading
        today's value.
        """
        url = (
            f"{self.url}/rest/v1/{table}"
            f"?metric_id=eq.{urllib.parse.quote(metric_id)}"
            f"&as_of=lte.{as_of.isoformat()}"
            "&order=as_of.desc&limit=1"
        )
        status, body = self.http.get(url, headers=self._headers())
        if status != 200 or not body:
            return None
        row = body[0]
        return HistoryRow(
            metric_id=row["metric_id"],
            as_of=date.fromisoformat(row["as_of"]),
            value=float(row["value"]) if isinstance(row["value"], (int, float, str)) else row["value"],
            source=row["source"],
        )

    def get_history_window(
        self,
        metric_ids: Sequence[str],
        *,
        days: int = 14,
        today: date | None = None,
        limit: int | None = None,
        table: str = "metric_history",
    ) -> dict[str, list[float]] | dict[str, list[HistoryRow]]:
        """Batched fetch for many metric ids, with two calling modes:

        **Sparkline mode** (existing): pass `days` + optionally `today`.
        Returns `dict[str, list[float]]` ordered oldest-to-newest. Non-numeric
        values are filtered out — sparkline-friendly.

        **Anchor mode** (new): pass `limit` and optionally `table`.
        Returns `dict[str, list[HistoryRow]]` ordered most-recent-first
        (PostgREST `order=as_of.desc`). Used by history_anchors.py to compute
        historical facts from metric_history or metric_history_monthly.

        Returns an empty dict on empty input or HTTP failure — best-effort.
        """
        if not metric_ids:
            return {} if limit is None else {mid: [] for mid in metric_ids}

        # ── Anchor mode: limit-based, returns HistoryRow objects ─────────────
        if limit is not None:
            ids_csv = ",".join(urllib.parse.quote(mid) for mid in metric_ids)
            url = (
                f"{self.url}/rest/v1/{table}"
                f"?metric_id=in.({ids_csv})"
                f"&order=as_of.desc&limit={limit}"
            )
            status, body = self.http.get(url, headers=self._headers())
            if status != 200 or not body:
                return {mid: [] for mid in metric_ids}
            grouped: dict[str, list[HistoryRow]] = {mid: [] for mid in metric_ids}
            for row in body:
                try:
                    value = float(row["value"])
                except (TypeError, ValueError):
                    continue
                grouped.setdefault(row["metric_id"], []).append(
                    HistoryRow(
                        metric_id=row["metric_id"],
                        as_of=date.fromisoformat(row["as_of"]),
                        value=value,
                        source=row["source"],
                    )
                )
            return grouped

        # ── Sparkline mode: days-based, returns float lists ─────────────────
        if today is None:
            today = date.today()
        cutoff = today - timedelta(days=days)
        ids_csv = ",".join(metric_ids)
        q = urllib.parse.urlencode({
            "metric_id": f"in.({ids_csv})",
            "as_of":     f"gte.{cutoff.isoformat()}",
            "select":    "metric_id,as_of,value",
            "order":     "metric_id,as_of.asc",
        })
        url = f"{self.url}/rest/v1/metric_history?{q}"
        status, body = self.http.get(url, headers=self._headers())
        if status != 200 or not body:
            return {}
        out: dict[str, list[float]] = {}
        for row in body:
            v = row.get("value")
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            out.setdefault(row["metric_id"], []).append(float(v))
        return out

    def upsert_many(self, rows: list[HistoryRow]) -> bool:
        if not rows:
            return True
        url = f"{self.url}/rest/v1/metric_history?on_conflict=metric_id,as_of"
        payload = [
            {"metric_id": r.metric_id, "as_of": r.as_of.isoformat(),
             "value": r.value, "source": r.source}
            for r in rows
        ]
        status, _ = self.http.post(
            url,
            headers=self._headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            json=payload,
        )
        return status in (200, 201, 204)
