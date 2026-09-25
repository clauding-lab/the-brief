"""Code-owned edition identity and the single-host live publication lock."""
from __future__ import annotations

import fcntl
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from brief.v6_schema import BriefPayloadV6


@dataclass(frozen=True)
class PublishIdentity:
    issue_no: int
    brief_date: date


def resolve_identity(
    today: date, *, same_day_rows: list[dict[str, Any]], max_issue_no: int,
) -> PublishIdentity:
    """Reuse the unique daily row (including drafts), or allocate max + 1.

    Called once under the CLI lock for live publication. Conflicting rows are
    an operator repair, never permission to select an arbitrary deletion target.
    """
    if type(max_issue_no) is not int or max_issue_no < 0:
        raise ValueError("Invalid maximum publication issue number")
    if len(same_day_rows) > 1:
        raise ValueError("Conflicting same-day publication rows")
    if same_day_rows:
        row = same_day_rows[0]
        issue = row.get("issue_no")
        if (type(issue) is not int or not 0 < issue <= max_issue_no
                or row.get("brief_date") != today.isoformat()):
            raise ValueError("Conflicting same-day publication identity")
        return PublishIdentity(issue, today)
    return PublishIdentity(max_issue_no + 1, today)


def assert_identity(payload: BriefPayloadV6, expected: PublishIdentity) -> None:
    """Reject model metadata drift before any database write."""
    if (payload.brief.issue_no, payload.brief.brief_date) != (
        expected.issue_no, expected.brief_date,
    ):
        raise ValueError("Model changed the trusted publication identity")


def environment_paused() -> bool:
    """Read the strict operator pause switch; misspellings fail closed."""
    raw = os.environ.get("BRIEF_DRY_RUN", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"", "0", "false", "no", "off"}:
        return False
    raise ValueError("Invalid BRIEF_DRY_RUN value")


class PublicationBusyError(RuntimeError):
    """Another process owns the live publication and delivery window."""


@contextmanager
def publication_lock() -> Iterator[None]:
    """Nonblocking per-user flock, shared by every checkout and working directory.

    Never unlink: waiters and later invocations must keep using the same inode.
    The service's PrivateTmp must not isolate this lock from manual CLI runs.
    This coordinates one user on one host, not distributed database writers.
    """
    directory = Path.home() / ".local/state/the-brief"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    # mkdir's mode does not validate an existing directory. Open without
    # following symlinks, inspect that exact inode, then open the lock relative
    # to it so path replacement cannot redirect us after the safety check.
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        directory_info = os.fstat(directory_fd)
        if (not stat.S_ISDIR(directory_info.st_mode)
                or directory_info.st_uid != os.geteuid()
                or stat.S_IMODE(directory_info.st_mode) & 0o077):
            raise RuntimeError(
                "Publication lock directory must be private and owned by this user"
            )
        fd = os.open(
            "publication.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600, dir_fd=directory_fd,
        )
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                raise RuntimeError("Publication lock must be a regular file owned by this user")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise PublicationBusyError("Another live publication holds the publication lock") from exc
            yield
        finally:
            os.close(fd)
    finally:
        os.close(directory_fd)
