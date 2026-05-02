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

    def get_latest(self, metric_id: str) -> HistoryRow | None:
        q = urllib.parse.urlencode({
            "metric_id": f"eq.{metric_id}",
            "select":    "metric_id,as_of,value,source,ingested_at",
            "order":     "as_of.desc",
            "limit":     "1",
        })
        url = f"{self.url}/rest/v1/metric_history?{q}"
        status, body = self.http.get(url, headers=self._headers())
        if status != 200 or not body:
            return None
        row = body[0]
        return HistoryRow(
            metric_id=row["metric_id"],
            as_of=date.fromisoformat(row["as_of"]),
            value=row["value"],
            source=row["source"],
        )

    def get_history_window(
        self,
        metric_ids: Sequence[str],
        *,
        days: int = 14,
        today: date | None = None,
    ) -> dict[str, list[float]]:
        """Batched fetch of last `days` chronological readings for many metric ids.

        Returns a dict keyed by metric_id with values ordered oldest-to-newest.
        Non-numeric and null values are filtered out (sparkline-friendly).
        Returns an empty dict on empty input or HTTP failure — best-effort,
        the render layer treats missing history as no sparkline.
        """
        if not metric_ids:
            return {}
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
