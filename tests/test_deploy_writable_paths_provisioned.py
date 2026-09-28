"""Every directory a unit needs writable must exist before systemd starts that unit (R2 task C2).

systemd builds a unit's sandbox before ExecStartPre runs. Under ProtectHome=read-only a
ReadWritePaths entry WITHOUT a '-' prefix must already exist, or the unit is refused at
namespace setup and nothing publishes. A '-' entry that is missing is skipped instead, so the
directory stays read-only inside the sandbox — for the publication lock directory that means
the lock can never be created, which is why the lock directory must stay a required entry.

Controller check on Hetzner (29 Sep 2026 ~03:20 BDT, read-only): /home/adnan/.local/state/
the-brief did not exist. deploy/install.sh is the only provisioning step the runbook runs, so
it must create every such directory before its "systemd units" step. Static checks of the
repo's deploy files only: nothing here runs install.sh or touches a box.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY = REPO_ROOT / "deploy"
INSTALL = DEPLOY / "install.sh"
UNITS_STEP = "[install] systemd units"
SERVICE_USER = "adnan"
BOX_REPO = "/home/adnan/the-brief"
# The Claude CLI's own login state: created by `claude` itself, never by this repo.
CLAUDE_HOME = "/home/adnan/.claude"
LOCK_SUBDIR = ".local/state/the-brief"  # pinned to publication_lock() by the first test below
LOCK_DIR = f"/home/{SERVICE_USER}/{LOCK_SUBDIR}"  # brief.service runs as User=adnan


@dataclass(frozen=True)
class Provisioned:
    path: str
    owner: str
    mode: int | None
    idempotent: bool


def _required_writable_paths() -> list[tuple[str, str]]:
    """(unit, path) for every ReadWritePaths entry without the '-' (skip-if-missing) prefix."""
    found: list[tuple[str, str]] = []
    for unit in sorted(DEPLOY.glob("*.service")):
        for line in unit.read_text().splitlines():
            if line.strip().startswith("ReadWritePaths="):
                entries = line.split("=", 1)[1].split()
                found.extend((unit.name, entry) for entry in entries if not entry.startswith("-"))
    return found


def _steps_before_units() -> list[str]:
    lines = INSTALL.read_text().splitlines()
    marker = next(i for i, line in enumerate(lines) if UNITS_STEP in line)
    return [line.strip() for line in lines[:marker]
            if line.strip() and not line.strip().startswith(("#", "echo "))]


def _expand(word: str, variables: dict[str, str]) -> str:
    return re.sub(r"\$\{?([A-Z_]+)\}?", lambda m: variables.get(m.group(1), m.group(0)), word)


def _operands(args: list[str], valued_flags: set[str]) -> tuple[dict[str, str], list[str]]:
    flags: dict[str, str] = {}
    operands: list[str] = []
    pending: str | None = None
    for arg in args:
        if pending is not None:
            flags[pending] = arg
            pending = None
        elif arg in valued_flags:
            pending = arg
        elif arg.startswith("-"):
            flags[arg] = ""
        else:
            operands.append(arg)
    return flags, operands


def _octal(text: str | None) -> int | None:
    return int(text, 8) if text is not None and re.fullmatch(r"0?[0-7]{3}", text) else None


def _provisioned_before_units() -> dict[str, Provisioned]:
    """What install.sh leaves on disk, by path, before it installs any unit file."""
    variables: dict[str, str] = {}
    made: dict[str, Provisioned] = {}
    for step in _steps_before_units():
        words = [_expand(w, variables) for w in shlex.split(step)]
        assignment = re.fullmatch(r"([A-Z_]+)=(\S+)", step)
        if assignment:
            variables[assignment.group(1)] = _expand(assignment.group(2), variables)
            continue
        user = "root"
        if words[:2] == ["sudo", "-u"]:
            user, words = words[2], words[3:]
        command, args = words[0], words[1:]
        if command == "mkdir":
            flags, paths = _operands(args, {"-m"})
            for path in paths:
                made[path] = Provisioned(path, user, _octal(flags.get("-m")), "-p" in flags)
        elif command == "install" and "-d" in args:
            flags, paths = _operands(args, {"-m", "-o", "-g"})
            for path in paths:
                made[path] = Provisioned(path, flags.get("-o", user), _octal(flags.get("-m", "755")), True)
        elif command == "chmod":
            _, operands = _operands(args, set())
            for path in operands[1:]:
                if path in made:
                    made[path] = Provisioned(path, made[path].owner, _octal(operands[0]), made[path].idempotent)
    return made


def _exists_before_units(path: str, made: dict[str, Provisioned]) -> bool:
    # A created directory's parents exist too (mkdir -p / install -d create every component).
    return any(created == path or created.startswith(path.rstrip("/") + "/") for created in made)


def test_the_publication_lock_lives_in_the_service_users_state_directory(tmp_path, monkeypatch):
    from brief.publication_identity import publication_lock

    monkeypatch.setenv("HOME", str(tmp_path))
    with publication_lock():
        pass
    assert (tmp_path / LOCK_SUBDIR / "publication.lock").is_file()


def test_the_lock_directory_stays_a_required_writable_path_of_the_publisher_unit():
    # A '-' prefix would let systemd skip a missing directory and leave it read-only inside the
    # sandbox, so the lock could never be created and every live publish would fail.
    assert ("brief.service", LOCK_DIR) in _required_writable_paths()


def test_install_script_has_a_units_step_to_order_provisioning_against():
    assert any(UNITS_STEP in line for line in INSTALL.read_text().splitlines())


@pytest.mark.parametrize(("unit", "path"), _required_writable_paths())
def test_every_required_writable_path_exists_before_its_unit_is_installed(unit, path):
    inside_repo = path == BOX_REPO or path.startswith(BOX_REPO + "/")
    made = _provisioned_before_units()
    assert inside_repo or path == CLAUDE_HOME or _exists_before_units(path, made), (
        f"{unit} requires {path} writable, but deploy/install.sh does not create it before "
        f"'{UNITS_STEP}' — systemd would refuse to start the unit")


def test_install_creates_the_lock_directory_private_and_owned_by_the_service_user():
    made = _provisioned_before_units()
    assert LOCK_DIR in made, f"deploy/install.sh never creates {LOCK_DIR} before '{UNITS_STEP}'"
    lock_dir = made[LOCK_DIR]
    # publication_lock() refuses a directory it does not own or that has any group/other bit.
    assert lock_dir.owner == SERVICE_USER
    assert lock_dir.mode == 0o700
    assert lock_dir.idempotent, "a re-run of install.sh must not fail on the existing directory"
