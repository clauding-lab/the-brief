"""Supabase `metric_history` client — HTTP seam, JSON body.

Abstracts PostgREST so tests inject a mock `http` object with `.get()`/`.post()`
returning `(status, json_body_or_none)`. Production passes a urllib wrapper.
"""
from __future__ import annotations

import json as _json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol, Sequence, runtime_checkable


def finite_number(value: Any) -> bool:
    """Whether a numeric scalar is finite and safely representable as a float."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError, TypeError):
        return False


def _history_number(value: Any) -> float | None:
    """PostgREST may serialize numeric columns as strings; reject bad scalars."""
    if isinstance(value, str):
        try:
            value = float(value)
        except (OverflowError, ValueError):
            return None
    return float(value) if finite_number(value) else None


@dataclass(frozen=True)
class HistoryRow:
    metric_id: str
    as_of: date
    value: Any
    source: str
    # The date the UNDERLYING observation carries, when the writer recorded one.
    # Distinct from `as_of`, which for `metric_history_monthly` is always the
    # FIRST of the month — a bucket label, not an observation date. The yield
    # ladder needs the real thing: a rung stamped `as_of=2026-08-01` may be
    # derived from an auction that cleared on 27 Aug, and the chart footnote
    # says so. Optional and last so positional construction stays valid.
    source_as_of: date | None = None


@dataclass(frozen=True)
class HistoryPoint:
    """One dated sparkline reading (R2 fix 16): the same row the batched
    sparkline read already returns, with its `as_of` kept so a card's change
    can be measured against the previous observation, not a guessed one."""
    as_of: date
    value: float


def observation_date(row: HistoryRow, *, today: date, monthly: bool = False) -> date | None:
    """Resolve source evidence; only completed monthly buckets gain month-end.

    A monthly source date must belong to its bucket. Daily/event dates retain
    their writer convention. Quote callers separately require explicit evidence
    because legacy aggregate daily rows may have been collection restamps.
    """
    from brief.cadence import month_end

    if not isinstance(row.as_of, date) or row.as_of > today:
        return None
    source_date = row.source_as_of
    if source_date is not None:
        if not isinstance(source_date, date) or source_date > today:
            return None
        if monthly and (source_date.year, source_date.month) != (row.as_of.year, row.as_of.month):
            return None
        return source_date
    if monthly:
        end = month_end(row.as_of)
        return end if end <= today else None
    return row.as_of


def _source_as_of(row: dict) -> date | None:
    """Best-effort read of a row's `source_as_of`.

    Tolerant on purpose: the column is absent on older rows and on tables that
    never had it, and a malformed value must degrade to "unknown" rather than
    take down a whole history fetch that is otherwise fine.
    """
    raw = row.get("source_as_of")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


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
        value = _history_number(row.get("value"))
        if value is None:
            return None
        return HistoryRow(
            metric_id=row["metric_id"],
            as_of=date.fromisoformat(row["as_of"]),
            value=value,
            source=row["source"],
            source_as_of=_source_as_of(row),
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
        value = _history_number(row.get("value"))
        if value is None:
            return None
        return HistoryRow(
            metric_id=row["metric_id"],
            as_of=date.fromisoformat(row["as_of"]),
            value=value,
            source=row["source"],
            source_as_of=_source_as_of(row),
        )

    def get_history_window(
        self,
        metric_ids: Sequence[str],
        *,
        days: int = 14,
        today: date | None = None,
        limit: int | None = None,
        table: str = "metric_history",
        dated: bool = False,
    ) -> dict[str, list[float]] | dict[str, list[HistoryRow]] | dict[str, list[HistoryPoint]]:
        """Batched fetch for many metric ids, with two calling modes:

        **Sparkline mode** (existing): pass `days` + optionally `today`.
        Returns `dict[str, list[float]]` ordered oldest-to-newest. Non-numeric
        values are filtered out — sparkline-friendly. With `dated=True` (R2 fix
        16) the same single query returns `HistoryPoint`s instead, keeping each
        row's `as_of`; a row whose `as_of` does not parse is skipped.

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
                        source_as_of=_source_as_of(row),
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
        out: dict[str, list[Any]] = {}
        for row in body:
            v = row.get("value")
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            if not dated:
                out.setdefault(row["metric_id"], []).append(float(v))
                continue
            try:
                as_of = date.fromisoformat(str(row.get("as_of"))[:10])
            except ValueError:
                continue  # an undated reading can never anchor a change
            out.setdefault(row["metric_id"], []).append(HistoryPoint(as_of, float(v)))
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
