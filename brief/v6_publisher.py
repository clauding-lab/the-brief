"""Supabase REST publisher for V6 briefs.

Service-role auth. Publication is ONE call to the database function
`publish_brief_atomic` (migration 0006): the whole edition commits in a single
transaction or nothing changes, and a same-day replacement keeps the issue's
identity. The function's validated receipt is the only notification authority.

Pure urllib — no new dependencies vs the V5 history client. Reads
SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY from env (Hetzner: /etc/brief.env
loads them via systemd EnvironmentFile).
"""
from __future__ import annotations

import http.client
import json
import logging
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from brief.v6_schema import BriefPayloadV6
from brief.publication_identity import PublishIdentity, assert_identity

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
    timeout_s: int = 30,
) -> Any:
    url, key = _config()
    full_url = f"{url}/rest/v1{path}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
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


# Every header-plus-content read below is ONE PostgREST request rooted at
# `briefs` (one SQL statement, so one database snapshot). A same-day correction
# that commits between two separate requests would otherwise pair the old
# header with the new children (R3c; design test 7). Newest-first uses the same rule
# as `get_latest_brief` (a historical duplicate date resolves to its highest
# issue); ordinal children get an `id` tie-breaker so the order is deterministic.
_BRIEF_HEADER_COLUMNS = (
    "id,issue_no,volume,brief_date,published_at,status,read_minutes,cover_metric,"
    "created_at,todays_call,lens,frame"
)
_NEWEST_PUBLISHED_FIRST = "status=eq.published&order=brief_date.desc,issue_no.desc"
_BY_ORD = "ord.asc,id.asc"


def fetch_previous_brief() -> dict[str, Any] | None:
    """Return the most recent published brief as a dict, or None.

    Used by the editor prompt to compute changed flags + rotate the hero.
    Header and sections come from one request (one snapshot).
    """
    rows = _request(
        "GET",
        f"/briefs?select={_BRIEF_HEADER_COLUMNS},sections(*,metrics(*),news(*))"
        f"&{_NEWEST_PUBLISHED_FIRST}&limit=1"
        f"&sections.order={_BY_ORD}&sections.metrics.order={_BY_ORD}"
        f"&sections.news.order={_BY_ORD}",
    )
    if not rows:
        return None
    brief = {key: value for key, value in rows[0].items() if key != "sections"}
    return {"brief": brief, "sections": rows[0].get("sections") or []}


def fetch_max_issue_no() -> int:
    """Highest issue_no in the table, or 0 if empty. Next issue is this + 1."""
    rows = _request("GET", "/briefs?select=issue_no&order=issue_no.desc&limit=1")
    if not rows:
        return 0
    return int(rows[0]["issue_no"])


def fetch_same_day_briefs(today: date) -> list[dict[str, Any]]:
    """Read published AND draft identities so retries never mint another issue."""
    return _request(
        "GET", f"/briefs?brief_date=eq.{today.isoformat()}&select=issue_no,brief_date,status",
    ) or []


def fetch_recent_news(n_issues: int = 5) -> list[dict[str, Any]]:
    """Return the flat list of news items from the most recent N published briefs.

    Used by filter_headlines() to dedupe today's candidate pool against the
    last work-week of news. One request (one snapshot) for all N issues.
    """
    briefs = _request(
        "GET",
        f"/briefs?select=id,sections(news(headline,source_url))"
        f"&{_NEWEST_PUBLISHED_FIRST}&limit={n_issues}"
        f"&sections.order={_BY_ORD}&sections.news.order={_BY_ORD}",
    ) or []
    return [
        item
        for brief in briefs
        for section in brief.get("sections") or []
        for item in section.get("news") or []
    ]


def fetch_metric_definitions() -> list[dict[str, Any]]:
    """Return the metric catalog rows.

    Consumed by mark_held_overs which keys on (section_slug, label) and reads
    last_print_date. The current production schema lacks both section_slug
    and last_print_date — see migration 0003 (pending) — so for now
    mark_held_overs gracefully no-ops on every metric. Selecting all columns
    means consumers can pick up new fields as the schema evolves without
    further code changes.
    """
    return _request("GET", "/metric_definitions?select=*") or []


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
# Write — atomic publish (R3, migration 0006)
# ───────────────────────────────────────────────────────────────────────

_RPC_PATH = "/rpc/publish_brief_atomic"
_RECEIPT_KEYS = frozenset(
    {"brief_id", "issue_no", "brief_date", "published_at", "created_new_identity"}
)
_UNKNOWN_OUTCOME = (
    "the database may have committed this edition; do NOT resend — a restart "
    "reuses today's identity and suppresses email"
)


@dataclass(frozen=True)
class PublishReceipt:
    """The database's answer for one committed publication.

    `created_new_identity` means THIS transaction created today's issue. It is
    the only notification authority; it says nothing about delivery.
    """

    brief_id: str
    issue_no: int
    brief_date: date
    published_at: datetime
    created_new_identity: bool


def _receipt_error(reason: str) -> PublishError:
    return PublishError(f"Publication receipt {reason}; {_UNKNOWN_OUTCOME}")


def _canonical_uuid(value: Any) -> str:
    try:
        if isinstance(value, str) and str(uuid.UUID(value)) == value:
            return value
    except ValueError:
        pass
    raise _receipt_error("has an invalid brief_id")


def _aware_timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        raise _receipt_error("has an invalid published_at")
    return parsed


def _validated_receipt(raw: Any, expected: PublishIdentity) -> PublishReceipt:
    """Every field typed, and the identity exactly the trusted one — or raise."""
    if not isinstance(raw, dict) or set(raw) != _RECEIPT_KEYS:
        raise _receipt_error("is missing, empty or has unexpected fields")
    issue_no, brief_date = raw["issue_no"], raw["brief_date"]
    if type(issue_no) is not int or issue_no != expected.issue_no:
        raise _receipt_error("names a different issue")
    if not isinstance(brief_date, str) or brief_date != expected.brief_date.isoformat():
        raise _receipt_error("names a different date")
    if type(raw["created_new_identity"]) is not bool:
        raise _receipt_error("has an invalid created_new_identity")
    return PublishReceipt(
        brief_id=_canonical_uuid(raw["brief_id"]),
        issue_no=issue_no,
        brief_date=expected.brief_date,
        published_at=_aware_timestamp(raw["published_at"]),
        created_new_identity=raw["created_new_identity"],
    )


def publish_brief(payload: BriefPayloadV6, *, expected_identity: PublishIdentity) -> PublishReceipt:
    """Publish a validated V6 brief in ONE database transaction; return its receipt.

    `publish_brief_atomic` takes an advisory lock, re-checks the trusted
    identity against today's rows, replaces the edition's children under the
    SAME brief UUID and flips `published` last — all or nothing. A failure
    leaves the previous complete edition untouched (landmine 22's rule that
    visibility is granted last now holds inside one transaction).

    Fails closed: any HTTP error, a missing function (PGRST202), a timeout or
    a lost/malformed/mismatched receipt raises PublishError. There is no
    legacy DELETE+POST fallback and no automatic replay — a replay's success
    must never be read as permission to notify.
    """
    try:
        assert_identity(payload, expected_identity)
    except ValueError as exc:
        raise PublishError(str(exc)) from exc
    body = {
        "p_expected_issue_no": expected_identity.issue_no,
        "p_expected_brief_date": expected_identity.brief_date.isoformat(),
        "p_payload": payload.model_dump(mode="json"),
    }
    try:
        raw = _request("POST", _RPC_PATH, body=body)
    except PublishError as exc:
        if "PGRST202" in str(exc):
            raise PublishError(
                "publish_brief_atomic is missing (PGRST202): apply migration "
                "0006_publish_brief_atomic.sql; there is no legacy fallback"
            ) from exc
        raise
    except (OSError, ValueError, http.client.HTTPException) as exc:
        # The request may have reached the database: the answer, not the write, was lost.
        raise PublishError(f"Supabase POST {_RPC_PATH} answer lost ({exc!r}); {_UNKNOWN_OUTCOME}") from exc
    receipt = _validated_receipt(raw, expected_identity)
    logger.info(
        "v6_publisher: issue %d committed atomically (brief_id=%s, created_new_identity=%s, %d sections)",
        receipt.issue_no, receipt.brief_id, receipt.created_new_identity, len(payload.sections),
    )
    return receipt
