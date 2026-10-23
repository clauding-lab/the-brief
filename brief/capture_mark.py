"""The newest EconDelta capture a live Brief run has already read (a high-water mark).

The five-minute ExonVPS -> Hetzner pull (`rsync -t`, R2 task G3 read-only check of
28 Sep 2026) copies whatever latest.json ExonVPS holds, with no capture-time check: a
restored or rolled-back older snapshot arrives as faithfully as a new one. Readiness
compares each snapshot's capture with this mark, so an older capture that replaced a
newer one is reported ("capture went backwards"), never read as current.

Contract:
- only a live, non-held run advances the mark (brief.cli, under the publication lock). It
  is recorded after the readiness hold check and BEFORE run_publish, so it means "read by a
  live run that passed readiness", not "published": that run may still fail later;
  dry runs replay other days and fixtures, so they read it but never move it;
- the mark is never lowered; an unusable mark (unreadable, malformed, naive, or later
  than now) is logged and treated as unknown - never as proof of a regression;
- neither reading nor saving the mark ever raises or blocks the publish.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Beside publication.lock: the directory brief.service's ReadWritePaths already grants.
_STATE_DIR = Path(".local/state/the-brief")
_MARK_FILE = "econdelta-capture-mark.json"


def mark_path() -> Path:
    """Resolved per call from the service user's home (tests point it elsewhere)."""
    return Path.home() / _STATE_DIR / _MARK_FILE


def read_capture_mark(now: datetime) -> datetime | None:
    """The newest capture a live run read and passed readiness with, or None when there is
    none or it is unusable."""
    try:
        mark = datetime.fromisoformat(json.loads(mark_path().read_text(encoding="utf-8"))["captured_at"])
    except FileNotFoundError:
        return None
    # JSON/Unicode errors are ValueErrors; a hand-crafted, deeply nested mark makes the decoder
    # raise RecursionError (R2 G3 review probe), which must not crash the run either.
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        _log_unusable(type(exc).__name__)
        return None
    problem = "no timezone" if mark.utcoffset() is None else "later than now" if mark > now else None
    if problem is not None:
        _log_unusable(problem)
        return None
    return mark


def record_capture_mark(captured: datetime | None, *, previous: datetime | None) -> None:
    """Advance the mark to `captured` when it is newer than `previous`; never lower it."""
    if captured is None or (previous is not None and captured <= previous):
        return
    path = mark_path()
    temporary = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary.write_text(json.dumps({"captured_at": captured.isoformat()}) + "\n", encoding="utf-8")
        os.replace(temporary, path)  # atomic: a reader sees the old mark or the new one
    except OSError as exc:
        logger.warning("capture mark not saved (%s); the next run cannot compare against this "
                       "capture", type(exc).__name__)


def _log_unusable(why: str) -> None:
    logger.warning("capture mark unusable (%s); capture-regression check skipped this run", why)
