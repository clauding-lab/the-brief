"""Read EconDelta's `latest.json` snapshot from a co-located file path.

The VPS Brief pipeline reads `/home/adnan/econdelta/data/latest.json` directly;
tests pass a path to a fixture. No HTTP.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(os.environ.get("ECONDELTA_DATA", "/home/adnan/econdelta/data/latest.json"))


class EconDeltaUnavailable(Exception):
    """Raised when the snapshot can't be read or parsed."""


@dataclass(frozen=True)
class EconDeltaSnapshot:
    updated_at: datetime
    sources_status: dict[str, dict[str, Any]]
    data: dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

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
        )
    except (KeyError, ValueError) as e:
        raise EconDeltaUnavailable(f"EconDelta snapshot malformed: {e}") from e
