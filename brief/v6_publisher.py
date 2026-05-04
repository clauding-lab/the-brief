"""Supabase REST publisher for V6 briefs.

Service-role auth, idempotent same-day re-publish (DELETE by issue_no relies on
ON DELETE CASCADE — verified for sections/metrics/news/chart_series/chart_notes).

Pure urllib — no new dependencies vs the V5 history client. Reads
SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY from env (Hetzner: /etc/brief.env
loads them via systemd EnvironmentFile).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from brief.v6_schema import BriefPayloadV6

logger = logging.getLogger(__name__)


class PublishError(RuntimeError):
    """Raised when a Supabase write fails or the env is missing."""


def _config() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise PublishError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY env vars. "
            "On Hetzner these come from /etc/brief.env via systemd EnvironmentFile."
        )
    return url.rstrip("/"), key


def _request(
    method: str,
    path: str,
    body: Any | None = None,
    *,
    prefer_return: str | None = None,
    timeout_s: int = 30,
) -> Any:
    url, key = _config()
    full_url = f"{url}/rest/v1{path}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer_return:
        headers["Prefer"] = f"return={prefer_return}"

    data = None if body is None else json.dumps(body, default=str).encode("utf-8")
    req = urllib.request.Request(full_url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:500]
        raise PublishError(
            f"Supabase {method} {path} → HTTP {e.code}: {body_text}"
        ) from e
    except urllib.error.URLError as e:
        raise PublishError(f"Supabase {method} {path} → network error: {e}") from e


# ───────────────────────────────────────────────────────────────────────
# Read helpers (used by editor input prep)
# ───────────────────────────────────────────────────────────────────────


def fetch_previous_brief() -> dict[str, Any] | None:
    """Return the most recent published brief as a dict, or None.

    Used by the editor prompt to compute changed flags + rotate the hero.
    """
    rows = _request(
        "GET",
        "/briefs?status=eq.published&order=brief_date.desc&limit=1",
    )
    if not rows:
        return None
    brief = rows[0]
    sections = _request(
        "GET",
        f"/sections?brief_id=eq.{brief['id']}&order=ord.asc&select=*,metrics(*),news(*)",
    ) or []
    return {"brief": brief, "sections": sections}


def fetch_max_issue_no() -> int:
    """Highest issue_no in the table, or 0 if empty. Next issue is this + 1."""
    rows = _request("GET", "/briefs?select=issue_no&order=issue_no.desc&limit=1")
    if not rows:
        return 0
    return int(rows[0]["issue_no"])


def fetch_metric_history(metric_id: str, days: int = 90) -> list[dict[str, Any]]:
    """Pull recent points from the V5 metric_history table for chart series.

    Returned shape: [{as_of: 'YYYY-MM-DD', value: <num>}], ordered ascending.
    Empty list when no history.
    """
    rows = _request(
        "GET",
        f"/metric_history?metric_id=eq.{metric_id}&order=as_of.desc&limit={days}"
        "&select=as_of,value",
    ) or []
    return list(reversed(rows))


# ───────────────────────────────────────────────────────────────────────
# Write — atomic publish
# ───────────────────────────────────────────────────────────────────────


def publish_brief(payload: BriefPayloadV6) -> str:
    """Idempotently publish a validated V6 brief. Returns the new brief.id (UUID).

    Flow:
      1. DELETE FROM briefs WHERE issue_no = N  (cascades to sections/metrics/news/charts)
      2. INSERT brief row, get uuid
      3. For each section: INSERT, get uuid, INSERT children
    """
    issue_no = payload.brief.issue_no
    logger.info("v6_publisher: deleting existing rows for issue_no=%d", issue_no)
    _request("DELETE", f"/briefs?issue_no=eq.{issue_no}")

    brief_row = payload.brief.model_dump(mode="json")
    # status is set by the schema default; published_at is set by db default if absent
    inserted_briefs = _request(
        "POST",
        "/briefs",
        body=brief_row,
        prefer_return="representation",
    )
    if not inserted_briefs:
        raise PublishError("INSERT briefs returned empty response")
    brief_id = inserted_briefs[0]["id"]
    logger.info("v6_publisher: brief inserted id=%s issue_no=%d", brief_id, issue_no)

    for section in payload.sections:
        section_row = section.model_dump(
            mode="json",
            exclude={"metrics", "news", "series", "notes"},
        )
        section_row["brief_id"] = brief_id
        inserted_sections = _request(
            "POST",
            "/sections",
            body=section_row,
            prefer_return="representation",
        )
        section_id = inserted_sections[0]["id"]

        if section.metrics:
            metrics_rows = [
                {**m.model_dump(mode="json"), "section_id": section_id, "ord": i}
                for i, m in enumerate(section.metrics)
            ]
            _request("POST", "/metrics", body=metrics_rows)

        if section.news:
            news_rows = [
                {**n.model_dump(mode="json"), "section_id": section_id, "ord": i}
                for i, n in enumerate(section.news)
            ]
            _request("POST", "/news", body=news_rows)

        if section.series:
            series_rows = [
                {
                    "section_id": section_id,
                    "series_key": p.key or section.slug,
                    "ts": p.ts,
                    "value": p.value,
                }
                for p in section.series
            ]
            _request("POST", "/chart_series", body=series_rows)

        if section.notes:
            note_rows = [
                {
                    "section_id": section_id,
                    "series_key": n.series_key,
                    "ts": n.ts,
                    "label": n.label,
                    "detail": n.detail,
                }
                for n in section.notes
            ]
            _request("POST", "/chart_notes", body=note_rows)

    logger.info(
        "v6_publisher: published issue %d with %d sections",
        issue_no,
        len(payload.sections),
    )
    return brief_id
