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
    directory.mkdir(parents=True, mode=0o700)
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


def test_lock_refuses_symlink_directory_without_creating_lock(tmp_path, monkeypatch):
    from brief.publication_identity import publication_lock

    monkeypatch.setenv("HOME", str(tmp_path))
    directory = tmp_path / ".local/state/the-brief"
    directory.parent.mkdir(parents=True)
    target = tmp_path / "other-directory"
    target.mkdir(mode=0o700)
    directory.symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError):
        with publication_lock():
            pytest.fail("a symlink directory must not be accepted")
    assert list(target.iterdir()) == []
    assert directory.is_symlink()


@pytest.mark.parametrize("mode", [0o777, 0o770, 0o755, 0o710, 0o707])
def test_lock_refuses_nonprivate_directory_without_repair(tmp_path, monkeypatch, mode):
    import stat
    from brief.publication_identity import publication_lock

    monkeypatch.setenv("HOME", str(tmp_path))
    directory = tmp_path / ".local/state/the-brief"
    directory.mkdir(parents=True)
    directory.chmod(mode)  # Deliberately misprovisioned; ignore the shell's umask.
    before = directory.stat()
    with pytest.raises(RuntimeError, match="Publication lock directory"):
        with publication_lock():
            pytest.fail("a nonprivate directory must not be accepted")
    assert not (directory / "publication.lock").exists()
    assert stat.S_IMODE(directory.stat().st_mode) == mode
    assert directory.stat().st_uid == before.st_uid


def test_lock_refuses_directory_owned_by_another_effective_user(tmp_path, monkeypatch):
    from brief.publication_identity import publication_lock

    monkeypatch.setenv("HOME", str(tmp_path))
    directory = tmp_path / ".local/state/the-brief"
    directory.mkdir(parents=True, mode=0o700)
    original_owner = directory.stat().st_uid
    # Exercise the ownership comparison without requiring privileged chown.
    monkeypatch.setattr("brief.publication_identity.os.geteuid", lambda: original_owner + 1)
    with pytest.raises(RuntimeError, match="Publication lock directory"):
        with publication_lock():
            pytest.fail("a directory owned by another effective user must be refused")
    assert not (directory / "publication.lock").exists()
    assert directory.stat().st_uid == original_owner


def test_existing_private_directory_keeps_lock_inode(tmp_path, monkeypatch):
    import stat
    from brief.publication_identity import publication_lock

    monkeypatch.setenv("HOME", str(tmp_path))
    directory = tmp_path / ".local/state/the-brief"
    directory.mkdir(parents=True, mode=0o700)
    lock = directory / "publication.lock"
    with publication_lock():
        inode = lock.stat().st_ino
    with publication_lock():
        assert lock.stat().st_ino == inode
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_lock_file_open_stays_in_the_validated_directory(tmp_path, monkeypatch):
    import os
    from pathlib import Path
    from brief.publication_identity import publication_lock

    monkeypatch.setenv("HOME", str(tmp_path))
    directory = tmp_path / ".local/state/the-brief"
    directory.mkdir(parents=True, mode=0o700)
    parked = tmp_path / "validated-directory"
    replacement = tmp_path / "replacement"
    replacement.mkdir(mode=0o700)
    real_open = os.open

    def replace_path_before_file_open(path, flags, mode=0o777, *, dir_fd=None):
        if Path(path).name == "publication.lock":
            directory.rename(parked)
            directory.symlink_to(replacement, target_is_directory=True)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("brief.publication_identity.os.open", replace_path_before_file_open)
    with publication_lock():
        assert (parked / "publication.lock").is_file()
        assert list(replacement.iterdir()) == []
    assert (parked / "publication.lock").is_file()
