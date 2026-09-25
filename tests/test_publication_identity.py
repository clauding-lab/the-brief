"""Trusted daily edition allocation: the model never owns the write target."""
from dataclasses import FrozenInstanceError
from datetime import date
from types import SimpleNamespace

import pytest

from brief.publication_identity import PublishIdentity, assert_identity, resolve_identity

TODAY = date(2026, 9, 25)


def test_new_date_allocates_max_plus_one():
    assert resolve_identity(TODAY, same_day_rows=[], max_issue_no=235) == PublishIdentity(236, TODAY)


@pytest.mark.parametrize("status", ["published", "draft"])
def test_same_day_and_draft_retry_reuse_identity(status):
    rows = [{"issue_no": 235, "brief_date": TODAY.isoformat(), "status": status}]
    assert resolve_identity(TODAY, same_day_rows=rows, max_issue_no=235) == PublishIdentity(235, TODAY)


@pytest.mark.parametrize("rows", [
    [{"issue_no": 234, "brief_date": "2026-09-25"}, {"issue_no": 235, "brief_date": "2026-09-25"}],
    [{"issue_no": 235, "brief_date": "2026-09-24"}],
    [{"issue_no": 0, "brief_date": "2026-09-25"}],
    [{"issue_no": 236, "brief_date": "2026-09-25"}],
])
def test_conflicting_rows_hold(rows):
    with pytest.raises(ValueError):
        resolve_identity(TODAY, same_day_rows=rows, max_issue_no=235)


def test_identity_is_immutable():
    identity = PublishIdentity(236, TODAY)
    with pytest.raises(FrozenInstanceError):
        identity.issue_no = 1


@pytest.mark.parametrize("issue,day", [(1, date(2026, 4, 20)), (236, date(2026, 4, 20)), (1, TODAY)])
def test_model_cannot_change_either_identity_field(issue, day):
    payload = SimpleNamespace(brief=SimpleNamespace(issue_no=issue, brief_date=day))
    with pytest.raises(ValueError, match="trusted publication identity"):
        assert_identity(payload, PublishIdentity(236, TODAY))


def test_lock_refuses_symlink_without_touching_target(tmp_path, monkeypatch):
    from brief.publication_identity import publication_lock

    monkeypatch.setenv("HOME", str(tmp_path))
    directory = tmp_path / ".local/state/the-brief"
    directory.mkdir(parents=True)
    target = tmp_path / "other-file"
    target.write_text("unchanged")
    (directory / "publication.lock").symlink_to(target)
    with pytest.raises(OSError):
        with publication_lock():
            pytest.fail("symlink must never become the shared lock")
    assert target.read_text() == "unchanged"


def test_lock_releases_after_exception_without_unlinking(tmp_path, monkeypatch):
    from brief.publication_identity import publication_lock

    monkeypatch.setenv("HOME", str(tmp_path))
    lock = tmp_path / ".local/state/the-brief/publication.lock"
    with pytest.raises(RuntimeError, match="pipeline failed"):
        with publication_lock():
            inode = lock.stat().st_ino
            raise RuntimeError("pipeline failed")
    with publication_lock():
        assert lock.stat().st_ino == inode
