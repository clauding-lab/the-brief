"""The sub-editor's retry budget must fit inside brief.service's start timeout.

Issue 209 (2026-08-27) was lost to five consecutive 600s sub-editor timeouts.
The deadline had been set at roughly the job's own median runtime — measured
successes ran 589.2s (issue 207) and 585.9s (issue 208), i.e. 98% and 97.7% of
the 600s budget — so roughly half of all attempts were failing by construction
and no number of retries could help.

Nothing in the suite noticed, because nothing compared the retry budget against
the wall-clock the unit file actually allows. These tests do exactly that: they
read the real numbers out of `_run_subeditor` and `_call_with_retries` rather
than restating them, so raising `attempts` without raising `TimeoutStartSec`
fails here instead of in production at 08:00.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_PIPELINE = _ROOT / "brief" / "pipeline_v6.py"
_UNIT = pathlib.Path("/etc/systemd/system/brief.service")

# The editor's own draft has to come out of the same 90-minute window. Measured
# 529.9s / 669.4s / 670.5s across issues 207-209; 12 min is the observed ceiling
# rounded up, NOT the editor's own 1800s allowance, which it has never come near.
_EDITOR_BUDGET_S = 12 * 60


def _subeditor_call_kwargs() -> dict[str, int]:
    """The `timeout_s` / `attempts` literals `_run_subeditor` actually passes.

    Parsed from the source rather than imported, because they are call-site
    literals with no runtime handle to read them off.
    """
    tree = ast.parse(_PIPELINE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "_run_subeditor":
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            if getattr(call.func, "id", None) != "_call_with_retries":
                continue
            return {
                kw.arg: kw.value.value
                for kw in call.keywords
                if kw.arg in ("timeout_s", "attempts") and isinstance(kw.value, ast.Constant)
            }
    raise AssertionError("_run_subeditor no longer calls _call_with_retries with literals")


def _backoff_delays() -> list[int]:
    """`_call_with_retries`'s `delays` list, read from source for the same reason."""
    tree = ast.parse(_PIPELINE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "_call_with_retries":
            continue
        for stmt in ast.walk(node):
            if (
                isinstance(stmt, ast.Assign)
                and getattr(stmt.targets[0], "id", None) == "delays"
                and isinstance(stmt.value, ast.List)
            ):
                return [e.value for e in stmt.value.elts]
    raise AssertionError("_call_with_retries no longer defines a literal `delays` list")


def _worst_case_subeditor_seconds() -> int:
    kw = _subeditor_call_kwargs()
    attempts, timeout_s = kw["attempts"], kw["timeout_s"]
    delays = _backoff_delays()
    # One backoff between attempts, none after the last; the list caps at its
    # final value the same way `_call_with_retries` indexes it.
    waits = sum(delays[min(i, len(delays) - 1)] for i in range(attempts - 1))
    return attempts * timeout_s + waits


def test_the_timeout_gives_real_headroom_over_a_measured_run() -> None:
    """A deadline at the median runtime is a coin flip, not a timeout.

    589.2s was a SUCCESS under the old 600s budget. Demanding 1.5x the slowest
    measured success keeps the next slow-but-healthy run from being killed.
    """
    slowest_measured_success_s = 589.2
    timeout_s = _subeditor_call_kwargs()["timeout_s"]
    assert timeout_s >= slowest_measured_success_s * 1.5, (
        f"sub-editor timeout {timeout_s}s leaves only "
        f"{timeout_s / slowest_measured_success_s:.2f}x over a measured success"
    )


@pytest.mark.skipif(not _UNIT.exists(), reason="brief.service unit not on this box")
def test_the_retry_budget_fits_under_the_real_systemd_start_timeout() -> None:
    """Read the cap off the installed unit, so the two cannot drift apart."""
    m = re.search(r"^TimeoutStartSec=(\d+)min", _UNIT.read_text(encoding="utf-8"), re.M)
    assert m, "brief.service no longer declares TimeoutStartSec in minutes"
    cap_s = int(m.group(1)) * 60
    used_s = _EDITOR_BUDGET_S + _worst_case_subeditor_seconds()
    assert used_s <= cap_s, (
        f"editor ({_EDITOR_BUDGET_S}s) + sub-editor retries "
        f"({_worst_case_subeditor_seconds()}s) = {used_s}s exceeds "
        f"TimeoutStartSec {cap_s}s — raise TimeoutStartSec or cut attempts"
    )


def test_the_retry_budget_fits_under_ninety_minutes_off_box() -> None:
    """The same assertion with the cap hardcoded, so CI enforces it too.

    Update this constant only together with the unit file — that is the pairing
    the 2026-08-27 loss came from getting wrong in the other direction.
    """
    used_s = _EDITOR_BUDGET_S + _worst_case_subeditor_seconds()
    assert used_s <= 90 * 60, f"{used_s}s exceeds the 90-min TimeoutStartSec"
