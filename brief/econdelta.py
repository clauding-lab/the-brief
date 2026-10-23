"""Read EconDelta's `latest.json` snapshot from a co-located file path.

The VPS Brief pipeline reads `/home/adnan/econdelta/data/latest.json` directly;
tests pass a path to a fixture. No HTTP.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from brief.history import finite_number

DEFAULT_PATH = Path(os.environ.get("ECONDELTA_DATA", "/home/adnan/econdelta/data/latest.json"))


class EconDeltaUnavailable(Exception):
    """Raised when the snapshot can't be read or parsed.

    `cause` is a fixed category (one of UNAVAILABLE_CAUSES) that is safe to put in an
    operator alert; the message itself carries the path and decoder detail for the log.
    """

    def __init__(self, message: str, *, cause: str) -> None:
        super().__init__(message)
        self.cause = cause


# Closed set of reasons a snapshot file could not be used. Never derived from error text.
UNAVAILABLE_CAUSES: tuple[str, ...] = ("missing", "truncated", "unparseable", "unreadable", "wrong shape")


# Mirrors EconDelta `utils/observations.py::WRITER_CONFIRMATION_IDS`: the ONLY ids
# whose records may carry date_basis="writer_confirmation". Both repos assert this
# set against `writer_confirmation_contract.metric_ids` in the shared fixture
# tests/fixtures/contracts/brief-observations-v1.json, so a one-sided change fails.
WRITER_CONFIRMATION_IDS: frozenset[str] = frozenset(
    {"policy_rate_repo", "policy_rate_sdf", "policy_rate_slf"})

# Mirrors EconDelta `utils/observations.py::BANGLADESH_CALENDAR_SOURCES`: producer sources
# whose record dates are Bangladesh calendar days (bb_forex, DSE trading dates, BB auction
# dates). Their capture is read on the Dhaka calendar: EconDelta's 02:56 BDT aggregate is
# still the previous UTC day. Pinned against `bangladesh_calendar_contract.sources` in the
# shared fixture by both repos. Every other source keeps the capture's own (UTC) date.
BANGLADESH_CALENDAR_SOURCES: frozenset[str] = frozenset({"auction_results", "bb_forex", "dse_market"})
_DHAKA = timezone(timedelta(hours=6))  # Asia/Dhaka: fixed UTC+6, no DST


def _capture_day(source: str, captured: datetime) -> date:
    """The calendar day of the capture in the calendar the record's date is written in."""
    return captured.astimezone(_DHAKA).date() if source in BANGLADESH_CALENDAR_SOURCES else captured.date()


@dataclass(frozen=True)
class WriterConfirmation:
    """EconDelta re-read a standing policy-corridor rate on `confirmed_on`.

    Writer-liveness evidence only. `confirmed_on` is NOT an observation date or
    an MPC decision date (AGENTS.md landmine 24) and must never be used as one;
    it deliberately has no `as_of` field so it cannot be mistaken for one.
    """
    metric_id: str
    value: float
    confirmed_on: date
    captured_at: datetime
    quality: str  # "verified" or "held"
    source: str


@dataclass(frozen=True)
class EconDeltaSnapshot:
    # None only for an unavailable snapshot: its capture time is unknown, never "now".
    updated_at: datetime | None
    sources_status: dict[str, dict[str, Any]]
    data: dict[str, Any]
    observations: dict[str, dict[str, Any]] = field(default_factory=dict)

    # As found: None when legacy-absent/null, else the producer's receipt block. A present
    # non-object block is kept (not rejected at load) so readiness holds on it as malformed.
    write_status: Any = None
    load_error: str | None = None
    load_cause: str | None = None  # one of UNAVAILABLE_CAUSES when load_error is set

    @classmethod
    def unavailable(cls, reason: str, *, cause: str | None = None) -> EconDeltaSnapshot:
        """No readable snapshot: no capture time, readings, source statuses or receipts."""
        return cls(updated_at=None, sources_status={}, data={}, load_error=reason, load_cause=cause)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def observation(self, key: str, *, today: date) -> dict[str, Any] | None:
        """Read one complete producer record, bound to this scalar and concept.

        Matching values alone are not date evidence: identity, source evidence,
        quality, date basis and capture boundary must all agree as well.
        """
        record = self._bound_record(key, today=today, date_basis="observation")
        return record[0] if record is not None else None

    def writer_confirmation(self, key: str, *, today: date) -> WriterConfirmation | None:
        """Read one allowlisted corridor confirmation with observation()'s integrity.

        Separate from observation() on purpose: the confirmation date is when the
        writer re-read a standing rate, never when it was observed or decided.
        Any other id carrying this basis (a restamped quote) is rejected here.
        """
        if key not in WRITER_CONFIRMATION_IDS:
            return None
        record = self._bound_record(key, today=today, date_basis="writer_confirmation")
        if record is None:
            return None
        item, confirmed_on, captured = record
        return WriterConfirmation(metric_id=key, value=item["value"], confirmed_on=confirmed_on,
                                  captured_at=captured, quality=item["quality"],
                                  source=item["source"])

    def _bound_record(self, key: str, *, today: date, date_basis: str
                      ) -> tuple[dict[str, Any], date, datetime] | None:
        """Shared integrity: identity, finite value equal to data[key], quality,
        source, evidence, basis, and a tz-aware capture not before the record date."""
        item = self.observations.get(key)
        if not isinstance(item, dict):
            return None
        value = item.get("value")
        if (item.get("metric_id") != key or not finite_number(value)
                or not finite_number(self.get(key))
                or value != self.get(key) or item.get("quality") not in ("verified", "held")
                or item.get("date_basis") != date_basis
                or not isinstance(item.get("source"), str) or not item["source"].strip()
                or not isinstance(item.get("evidence"), str) or not item["evidence"].strip()):
            return None
        try:
            dated = date.fromisoformat(item["as_of"])
            captured = datetime.fromisoformat(item["captured_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError, AttributeError):
            return None
        if captured.utcoffset() is None or dated > min(today, _capture_day(item["source"], captured)):
            return None
        return item, dated, captured

    def source_age_hours(self, source_id: str) -> float | None:
        s = self.sources_status.get(source_id)
        if not isinstance(s, dict):
            return None
        v = s.get("age_hours")
        return float(v) if v is not None else None

    def source_status(self, source_id: str) -> str | None:
        s = self.sources_status.get(source_id)
        return s.get("status") if isinstance(s, dict) else None


# Every producer version writes these (EconDelta LatestBundle, since the legacy v1 shape).
# observations (pre-E1) and write_status (pre-receipt, or its serialised None default)
# are legitimately absent from legacy snapshots, and stay absent: never a healthy default.
# write_status is receipt evidence, judged by readiness: malformed -> hold, not unavailable.
_REQUIRED_FIELDS = ("updated_at", "sources_status", "data")


def load_snapshot(path: Path | str = DEFAULT_PATH) -> EconDeltaSnapshot:
    p = Path(path)
    try:
        with p.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError as e:
        raise EconDeltaUnavailable(f"EconDelta snapshot not found: {p}", cause="missing") from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:  # truncated or corrupt bytes
        raise EconDeltaUnavailable(f"EconDelta snapshot unparseable: {p}: {e}",
                                   cause="truncated" if _ends_early(e) else "unparseable") from e
    except OSError as e:
        raise EconDeltaUnavailable(f"EconDelta snapshot unreadable: {p}: {e}", cause="unreadable") from e

    if not isinstance(payload, dict):
        raise _malformed(p, f"top-level JSON is {type(payload).__name__}, not an object")
    missing = [name for name in _REQUIRED_FIELDS if name not in payload]
    if missing:
        raise _malformed(p, "missing " + ", ".join(missing))
    return EconDeltaSnapshot(
        updated_at=_capture_time(payload["updated_at"], p),
        sources_status=_object_field(payload, "sources_status", p),
        data=_object_field(payload, "data", p),
        observations=_object_field(payload, "observations", p) if "observations" in payload else {},
        write_status=payload.get("write_status"),
    )


def _ends_early(error: json.JSONDecodeError | UnicodeDecodeError) -> bool:
    """The file stops before its JSON (or its last UTF-8 character) is complete: an empty
    file, a cut inside a string, or a decoder error at the very end of the content."""
    if isinstance(error, UnicodeDecodeError):
        return error.reason == "unexpected end of data"
    return error.msg.startswith("Unterminated string") or error.pos >= len(error.doc.rstrip())


def _malformed(p: Path, detail: str) -> EconDeltaUnavailable:
    return EconDeltaUnavailable(f"EconDelta snapshot malformed: {p}: {detail}", cause="wrong shape")


def _object_field(payload: dict[str, Any], name: str, p: Path) -> dict[str, Any]:
    value = payload[name]
    if not isinstance(value, dict):
        raise _malformed(p, f"{name} is {type(value).__name__}, not an object")
    return value


def _capture_time(raw: Any, p: Path) -> datetime:
    """The aggregate's capture instant; without a timezone its age is unknowable."""
    if not isinstance(raw, str):
        raise _malformed(p, f"updated_at is {type(raw).__name__}, not an ISO 8601 string")
    try:
        captured = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as e:
        raise _malformed(p, f"updated_at is not ISO 8601: {raw!r}") from e
    if captured.utcoffset() is None:
        raise _malformed(p, f"updated_at has no timezone: {raw!r}")
    return captured
