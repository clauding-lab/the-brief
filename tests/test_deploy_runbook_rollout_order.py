"""The runbook runs the merged install.sh, and no fire runs new code under the old unit (R2 C2 round 1).

The Hetzner checkout only moves at a brief.service fire (ExecStartPre `git pull --ff-only origin
main`, AGENTS.md landmine 21). So right after a merge, /home/adnan/the-brief/deploy/install.sh is
still the PRE-merge copy: it installs the old unit and never creates the publication lock
directory. Review probe (R2 C2 adversarial r0): that stale install.sh provisions no lock
directory, and publication_lock() under the old unit's read-only home fails with EACCES — the next
08:00 BDT fire publishes nothing. Two rules follow for any runbook step that runs install.sh on a
host that already has the timer:

1. the merged code is pulled (as the service user, fast-forward only) and HEAD is checked BEFORE
   install.sh runs, so the install is the merged one;
2. brief.timer is stopped BEFORE the merge, so no timer fire can self-pull the new code and run it
   under the old unit in the gap (landmine 21: hands-on steps go before the merge, not after);
3. no fire is still RUNNING when the checkout is pulled (round 2): stopping the timer does not stop
   a brief.service that is already active (Type=oneshot, TimeoutStartSec=90min, so 08:00 to about
   09:30 BDT), and brief.cli imports pipeline_v6 / readiness / notifier lazily, so a pull mid-run
   makes that fire publish with old code and send with new code. The runbook must show
   `systemctl is-active brief.service brief-export.service` printing `inactive` before the pull.
4. (controller close, 29 Sep 2026) the idle check must also treat `failed` as not running: a
   oneshot that held (exit 4) or failed stays `failed` until its next start, so a check that only
   accepts `inactive` can never be met the morning after a hold. And it must look for a publish
   OUTSIDE systemd: the README 'Manual fire' re-run (nohup, landmine 13) is invisible to
   `systemctl is-active`, so the runbook needs a process check (pgrep) before the pull too. The
   weekly brief-export.timer is stopped with brief.timer, so an export cannot start mid-rollout.

Static checks of deploy/README.md only: nothing here runs a command or touches a box.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNBOOK = REPO_ROOT / "deploy" / "README.md"
FRESH_HOST_SECTION = "One-time install"  # no installed unit or timer exists yet on a fresh host

PULL = re.compile(r"\bgit\b.*\bpull\b")
SERVICE_USER_FF_PULL = re.compile(
    r"^sudo -u adnan git -C /home/adnan/the-brief pull --ff-only origin main$")
HEAD_CHECK = re.compile(r"\bgit -C /home/adnan/the-brief (log -1|rev-parse)\b")
TIMER_STOP = re.compile(r"\bsystemctl (stop|disable --now) brief\.timer\b")
# The numbered merge step itself, not the bare word: a stop step whose own note says "merge"
# must not satisfy the ordering rule (round-2 review mutant).
MERGE_STEP = re.compile(r"^\s*\d+\.\s+Merge the PR\b", re.MULTILINE)
IDLE_CHECK = re.compile(r"\bsystemctl is-active\b")
SERVICES_THAT_RUN_THE_CHECKOUT = ("brief.service", "brief-export.service")
# A publish started by hand (README 'Manual fire') runs `python -m brief.cli run` outside systemd.
MANUAL_RUN_CHECK = re.compile(r"\bpgrep\b.*brief(\[\.\]|\\\.|\.)cli")
EXPORT_TIMER_STOP = re.compile(r"\bsystemctl (stop|disable --now)\b.*\bbrief-export\.timer\b")


def _sections() -> list[tuple[str, str]]:
    """(heading, body) for every ## / ### section of the runbook."""
    sections: list[tuple[str, str]] = []
    heading, body = "", []
    for line in RUNBOOK.read_text().splitlines():
        if re.match(r"#{2,3} ", line):
            sections.append((heading, "\n".join(body)))
            heading, body = line.lstrip("#").strip(), []
        else:
            body.append(line)
    sections.append((heading, "\n".join(body)))
    return sections


def _install_runs(body: str) -> list[int]:
    """Offsets of every inline command that runs install.sh (prose mentions do not count)."""
    return [m.start() for m in re.finditer(r"`([^`]+)`", body)
            if m.group(1).startswith("sudo ") and m.group(1).rstrip().endswith("deploy/install.sh")]


def _commands_before(body: str, offset: int) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"`([^`]+)`", body[:offset])]


def _sections_running_install() -> list[tuple[str, str]]:
    return [(heading, body) for heading, body in _sections() if _install_runs(body)]


def _existing_host_rollouts() -> list[tuple[str, str]]:
    return [(h, b) for h, b in _sections_running_install() if h != FRESH_HOST_SECTION]


def test_the_runbook_has_an_existing_host_rollout_to_check():
    # Guards the parametrization below: the post-merge install step must stay findable.
    assert _existing_host_rollouts(), "deploy/README.md no longer runs install.sh on an existing host"


@pytest.mark.parametrize(("heading", "body"), _sections_running_install(),
                         ids=[h for h, _ in _sections_running_install()])
def test_install_runs_only_after_the_merged_code_is_pulled(heading, body):
    first_install = _install_runs(body)[0]
    assert any(PULL.search(cmd) for cmd in _commands_before(body, first_install)), (
        f"'{heading}': install.sh runs before any git pull, so the box runs the PRE-merge "
        "install.sh (old unit, no lock directory)")


@pytest.mark.parametrize(("heading", "body"), _existing_host_rollouts(),
                         ids=[h for h, _ in _existing_host_rollouts()])
def test_existing_host_pull_is_the_service_user_fast_forward_of_main_and_head_is_checked(heading, body):
    before = _commands_before(body, _install_runs(body)[0])
    pulls = [i for i, cmd in enumerate(before) if SERVICE_USER_FF_PULL.search(cmd)]
    # As adnan: a root pull can leave root-owned files in .git that break the unit's own self-pull;
    # --ff-only: a diverged checkout fails loudly instead of merging; HEAD check: proves the merge
    # commit is what install.sh comes from.
    assert pulls, f"'{heading}': no `sudo -u adnan git -C /home/adnan/the-brief pull --ff-only origin main`"
    assert any(HEAD_CHECK.search(cmd) for cmd in before[pulls[0] + 1:]), (
        f"'{heading}': HEAD is not checked between the pull and install.sh")


@pytest.mark.parametrize(("heading", "body"), _existing_host_rollouts(),
                         ids=[h for h, _ in _existing_host_rollouts()])
def test_existing_host_timer_is_stopped_before_the_merge(heading, body):
    install = _install_runs(body)[0]
    stops = [m.start() for m in re.finditer(r"`([^`]+)`", body[:install]) if TIMER_STOP.search(m.group(1))]
    assert stops, f"'{heading}': brief.timer is not stopped before install.sh — an 08:00 fire in the gap " \
                  "self-pulls the new code and runs it under the old unit"
    pulls = [m.start() for m in re.finditer(r"`([^`]+)`", body[:install]) if PULL.search(m.group(1))]
    assert pulls, f"'{heading}': no pull before install.sh to order the timer stop against"
    merge_steps = [m.start() for m in MERGE_STEP.finditer(body)]
    assert merge_steps, f"'{heading}': no numbered 'Merge the PR' step to order the timer stop against"
    assert stops[0] < merge_steps[0] < pulls[0], (
        f"'{heading}': the timer stop must come before the merge step, and the pull after it")


def _backticked(body: str, end: int) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1)) for m in re.finditer(r"`([^`]+)`", body[:end])]


@pytest.mark.parametrize(("heading", "body"), _existing_host_rollouts(),
                         ids=[h for h, _ in _existing_host_rollouts()])
def test_existing_host_checkout_is_pulled_only_when_no_fire_is_running(heading, body):
    install = _install_runs(body)[0]
    commands = _backticked(body, install)
    stops = [at for at, cmd in commands if TIMER_STOP.search(cmd)]
    pulls = [at for at, cmd in commands if PULL.search(cmd)]
    assert stops and pulls, f"'{heading}': needs a timer stop and a pull before install.sh"
    idle_checks = [(at, cmd) for at, cmd in commands
                   if IDLE_CHECK.search(cmd) and stops[0] < at < pulls[0]]
    # A stopped timer does not stop a fire already running; the pull must wait for it to end.
    assert idle_checks, (
        f"'{heading}': no `systemctl is-active` check between the timer stop and the pull — a fire "
        "still running would publish with old code and send with the pulled code")
    at, cmd = idle_checks[0]
    missing = [svc for svc in SERVICES_THAT_RUN_THE_CHECKOUT if not re.search(rf"\b{re.escape(svc)}\b", cmd)]
    assert not missing, f"'{heading}': the idle check does not cover {missing}"
    assert "`inactive`" in body[at:pulls[0]], (
        f"'{heading}': the idle check must say it has to print `inactive` before the pull")


@pytest.mark.parametrize(("heading", "body"), _existing_host_rollouts(),
                         ids=[h for h, _ in _existing_host_rollouts()])
def test_a_unit_whose_last_run_held_or_failed_counts_as_not_running(heading, body):
    # A held fire (exit 4) leaves brief.service `failed` until its next start; an idle check that
    # only accepts `inactive` blocks the rollout the morning after any hold.
    install = _install_runs(body)[0]
    commands = _backticked(body, install)
    pulls = [at for at, cmd in commands if PULL.search(cmd)]
    idle = [at for at, cmd in commands if IDLE_CHECK.search(cmd) and at < pulls[0]]
    assert idle, f"'{heading}': no idle check before the pull"
    step = body[idle[0]:pulls[0]]
    assert "`failed`" in step, f"'{heading}': the idle check must say `failed` also means not running"
    for running_state in ("`active`", "`activating`", "`deactivating`"):
        assert running_state in step, f"'{heading}': the idle check must say to wait on {running_state}"


@pytest.mark.parametrize(("heading", "body"), _existing_host_rollouts(),
                         ids=[h for h, _ in _existing_host_rollouts()])
def test_a_manual_publish_outside_systemd_is_also_waited_for_before_the_pull(heading, body):
    # The README 'Manual fire' re-run (nohup `python -m brief.cli run --publish`) is not
    # brief.service, so `systemctl is-active` prints inactive/failed while it publishes.
    install = _install_runs(body)[0]
    commands = _backticked(body, install)
    stops = [at for at, cmd in commands if TIMER_STOP.search(cmd)]
    pulls = [at for at, cmd in commands if PULL.search(cmd)]
    assert stops and pulls, f"'{heading}': needs a timer stop and a pull before install.sh"
    assert any(MANUAL_RUN_CHECK.search(cmd) and stops[0] < at < pulls[0] for at, cmd in commands), (
        f"'{heading}': no pgrep check for a hand-started brief.cli run between the timer stop and "
        "the pull — a manual publish in flight would mix old and pulled code")


@pytest.mark.parametrize(("heading", "body"), _existing_host_rollouts(),
                         ids=[h for h, _ in _existing_host_rollouts()])
def test_the_weekly_export_timer_is_stopped_with_the_publish_timer(heading, body):
    install = _install_runs(body)[0]
    commands = _backticked(body, install)
    merge_steps = [m.start() for m in MERGE_STEP.finditer(body)]
    assert merge_steps, f"'{heading}': no numbered 'Merge the PR' step"
    assert any(EXPORT_TIMER_STOP.search(cmd) and at < merge_steps[0] for at, cmd in commands), (
        f"'{heading}': brief-export.timer is not stopped before the merge — a Saturday 09:30 BDT "
        "export could start between the idle check and the pull")
