"""Read EconDelta's `latest.json` snapshot from a co-located file path.

The VPS Brief pipeline reads `/home/adnan/econdelta/data/latest.json` directly;
tests pass a path to a fixture. No HTTP.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from brief.history import finite_number

DEFAULT_PATH = Path(os.environ.get("ECONDELTA_DATA", "/home/adnan/econdelta/data/latest.json"))


class EconDeltaUnavailable(Exception):
    """Raised when the snapshot can't be read or parsed."""


@dataclass(frozen=True)
class EconDeltaSnapshot:
    updated_at: datetime
    sources_status: dict[str, dict[str, Any]]
    data: dict[str, Any]
    observations: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def observation(self, key: str, *, today: date) -> dict[str, Any] | None:
        """Read one complete producer record, bound to this scalar and concept.

        Matching values alone are not date evidence: identity, source evidence,
        quality, date basis and capture boundary must all agree as well.
        """
        item = self.observations.get(key)
        if not isinstance(item, dict):
            return None
        value = item.get("value")
        if (item.get("metric_id") != key or not finite_number(value)
                or not finite_number(self.get(key))
                or value != self.get(key) or item.get("quality") not in ("verified", "held")
                or item.get("date_basis") != "observation"
                or not isinstance(item.get("source"), str) or not item["source"].strip()
                or not isinstance(item.get("evidence"), str) or not item["evidence"].strip()):
            return None
        try:
            observed = date.fromisoformat(item["as_of"])
            captured = datetime.fromisoformat(item["captured_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError, AttributeError):
            return None
        if captured.utcoffset() is None or observed > min(today, captured.date()):
            return None
        return item

    def source_age_hours(self, source_id: str) -> float | None:
        s = self.sources_status.get(source_id)
        if not s:
            return None
        v = s.get("age_hours")
        return float(v) if v is not None else None

    def source_status(self, source_id: str) -> str | None:
        s = self.sources_status.get(source_id)
        return s.get("status") if s else None


def load_snapshot(path: Path | str = DEFAULT_PATH) -> EconDeltaSnapshot:
    p = Path(path)
    try:
        with p.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError as e:
        raise EconDeltaUnavailable(f"EconDelta snapshot not found: {p}") from e
    except json.JSONDecodeError as e:
        raise EconDeltaUnavailable(f"EconDelta snapshot unparseable: {p}: {e}") from e

    try:
        updated_at = datetime.fromisoformat(payload["updated_at"].replace("Z", "+00:00"))
        return EconDeltaSnapshot(
            updated_at=updated_at,
            sources_status=payload.get("sources_status", {}),
            data=payload.get("data", {}),
            observations=payload.get("observations", {}) if isinstance(payload.get("observations"), dict) else {},
        )
    except (KeyError, ValueError, AttributeError) as e:
        raise EconDeltaUnavailable(f"EconDelta snapshot malformed: {e}") from e
