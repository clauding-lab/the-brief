"""The operator runbook carries the measured release order of the data-reliability repair (R3d).

Controller ruling 28 Sep 2026 (evidence C/r2-claude/fixG2-compat.md), step 2 amended 29 Sep
2026: the deployed Brief a810fcb ignores the new producer's additive fields, while the NEW Brief
on the OLD producer drops the USD/BDT, gold, Brent and WTI cards and HOLDs every publish on
unrepaired NBR history. So the order is producer -> R1 history repair (before the producer's
first metric_history write) and the owner-reviewed round-4 NBR exclusion -> owner-applied
migration 0006 -> the new Brief before its 08:00 BDT fire, deployed through the existing
"Rolling out a unit change" steps (install.sh after the merge, C2) -> roll back the Brief first.
The old 'Brief consumer first' order (fix 12) is superseded and must not come back.

The publisher is ONE atomic database call since R3 (migration 0006), so the runbook must not
keep describing a delete-then-insert publisher.

Static checks of deploy/README.md only: nothing here runs a command or touches a box.
"""
from __future__ import annotations

import re
from pathlib import Path

RUNBOOK = Path(__file__).resolve().parent.parent / "deploy" / "README.md"
UNIT_ROLLOUT_ANCHOR = "#publication-identity-concurrency-and-maintenance-pause"

# Each milestone of the order: (name, every pattern its numbered step must contain).
MILESTONES = (
    ("producer", (r"EconDelta", r"\bH5\b", r"01:00 BDT")),
    ("history repair", (r"\bR1\b", r"\(d\).*\(l\)", r"metric_history", r"02:55 BDT")),
    ("migration", (r"0006", r"SQL editor")),
    ("brief", (r"install\.sh", r"08:00 BDT", r"first daily write")),
)


def _section(title_pattern: str) -> str:
    text = RUNBOOK.read_text()
    match = re.search(rf"^## [^\n]*{title_pattern}[^\n]*\n(.*?)(?=^## |\Z)", text,
                      flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)
    assert match, f"no '## …{title_pattern}…' section in deploy/README.md"
    return match.group(1)


def _numbered_steps(body: str) -> list[str]:
    """Top-level numbered steps (`1. …`), each with its indented continuation lines, whitespace collapsed (line wraps never matter)."""
    return [" ".join(m.group(0).split()) for m in re.finditer(r"^\d+\.\s.*?(?=^\d+\.\s|^\S|\Z)", body,
                                            flags=re.MULTILINE | re.DOTALL)]


def _step_of(steps: list[str], patterns: tuple[str, ...]) -> int | None:
    found = [i for i, step in enumerate(steps) if all(re.search(p, step, flags=re.DOTALL) for p in patterns)]
    return found[0] if found else None


def _order() -> str:
    return _section("release order")


def test_release_steps_run_producer_then_history_repair_then_migration_then_brief() -> None:
    order = _order()
    steps = _numbered_steps(order)
    positions = {name: _step_of(steps, patterns) for name, patterns in MILESTONES}
    assert None not in positions.values(), positions
    ordered = [positions[name] for name, _ in MILESTONES]
    assert ordered == sorted(ordered) and len(set(ordered)) == len(ordered), positions


def test_new_brief_waits_for_the_round_four_nbr_exclusion() -> None:
    order = _order()
    steps = _numbered_steps(order)
    round_four = _step_of(steps, (r"round[- ]4", r"after 2026-09-24", r"must not go live"))
    brief = _step_of(steps, MILESTONES[3][1])
    assert round_four is not None and brief is not None and round_four < brief


def test_brief_deploy_reuses_the_unit_rollout_steps_instead_of_duplicating_them() -> None:
    order = _order()
    brief_step = _numbered_steps(order)[_step_of(_numbered_steps(order), MILESTONES[3][1])]
    assert UNIT_ROLLOUT_ANCHOR in brief_step and "Rolling out a unit change" in brief_step
    inline_installs = [c for c in re.findall(r"`([^`]+)`", order)
                       if c.startswith("sudo ") and c.rstrip().endswith("install.sh")]
    assert inline_installs == []


def _rollback_paragraph(body: str) -> str:
    match = re.search(r"^\*\*Roll ?back\b.*?(?=\n\s*\n|\Z)", body, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)
    assert match, "no bold '**Rollback…' paragraph in the release-order section"
    return " ".join(match.group(0).split())


def _timing_words_before(step: str, event: str) -> list[str]:
    """The word (before/after) that qualifies each mention of `event` in one step."""
    return [w.lower() for w in re.findall(rf"\b(before|after)\s+{event}", step, flags=re.IGNORECASE)]


def test_rollback_starts_with_the_brief() -> None:
    rollback = _rollback_paragraph(_order())
    assert re.match(r"\*\*(?:Rollback:\s*)?Roll back the Brief first\b", rollback, flags=re.IGNORECASE), rollback[:80]
    assert not re.search(r"\b(never|not|n't)\b[^.]{0,40}roll back the Brief first", rollback, flags=re.IGNORECASE)
    brief_at = rollback.find("Brief")
    producer_at = min((i for i in (rollback.find("EconDelta"), rollback.find("producer")) if i >= 0), default=-1)
    assert producer_at == -1 or brief_at < producer_at, rollback


def test_history_repair_lands_before_the_producers_first_history_write() -> None:
    steps = _numbered_steps(_order())
    repair = steps[_step_of(steps, MILESTONES[1][1])]
    words = _timing_words_before(repair, r"(?:its|the (?:new )?producer's) first `?metric_history`? write")
    assert words and set(words) == {"before"}, words


def test_producer_is_merged_before_the_nightly_gitpull() -> None:
    steps = _numbered_steps(_order())
    producer = steps[_step_of(steps, MILESTONES[0][1])]
    words = _timing_words_before(producer, r"(?:the )?01:00 BDT")
    assert words and set(words) == {"before"}, words


def test_new_brief_deploy_cannot_skip_install_sh() -> None:
    steps = _numbered_steps(_order())
    brief = steps[_step_of(steps, MILESTONES[3][1])]
    assert re.search(r"self-pull alone never installs the unit", brief)
    assert re.search(r"without it,? no fire can publish", brief)
    assert not re.search(r"\boptional\b", brief)


def test_runbook_describes_publication_as_one_atomic_call() -> None:
    identity = _section("Publication identity")
    assert "publish_brief_atomic" in identity
    assert "deletes the old row" not in RUNBOOK.read_text()


# --- R3d fix round 1 -------------------------------------------------------------------------
# B4 (C/task-B4-report.md "Blocking deployment prerequisite"; progress: "Recipient preflight ...
# remain R3 release prerequisites"): before the stricter notifier is activated, a read-only,
# counts-only check of the stored recipients must pass, AFTER the repaired signup is live (the
# merge's Vercel deploy) so the old permissive signup cannot add an incompatible row behind it.
# B5 / C/task-R3-brief.md: the 09:45 BDT watchdog is installed together with this release.
HEARTBEAT_ANCHOR = "#off-box-heartbeat-exonvps-0945-bdt-cron"
RELEASE_ORDER_ANCHOR = "#coordinated-release-order-data-reliability-repair-r2--r3"


def _brief_step() -> str:
    steps = _numbered_steps(_order())
    return steps[_step_of(steps, MILESTONES[3][1])]


def test_recipient_check_runs_after_the_repaired_signup_is_live_and_before_the_timers_restart() -> None:
    step = _brief_step()
    merged = re.search(r"steps 1[–-]5 of", step)
    check = re.search(r"fetch_subscribers\(\)", step)
    restart = re.search(r"steps 6[–-]7 of", step)
    assert merged and check and restart, "split the unit rollout around the recipient check"
    assert merged.start() < check.start() < restart.start()
    between = step[merged.start():check.start()]
    assert re.search(r"Vercel production", between), "the repaired signup must be live before the check"
    assert re.search(r"read-only", step) and re.search(r"counts? (?:and|or) (?:an? )?(?:error )?categor", step)
    assert re.search(r"validation_complete", step)
    assert re.search(r"(?:does not|doesn't) (?:print|show) `?true|fails?[^.]*do not run (?:`?install\.sh|steps 6)", step)


def test_watchdog_moves_to_0945_in_the_same_release() -> None:
    steps = _numbered_steps(_order())
    brief = _step_of(steps, MILESTONES[3][1])
    watchdog = _step_of(steps, (r"09:45 BDT", r"heartbeat", re.escape(HEARTBEAT_ANCHOR)))
    assert watchdog is not None and brief is not None and watchdog == brief + 1
    assert re.search(r"07:30", steps[watchdog]) and re.search(r"exactly one", steps[watchdog])


# G2 §8 (R/fixG2-compat.md) and the 28 Sep ruling: the deployed Brief on the new producer is NOT
# unchanged; its measured transition-window effects must be in the rollout plan.
def test_release_order_carries_the_measured_transition_window_caveats() -> None:
    order = _order()
    assert not re.search(r"builds the same cards|byte-identical cards", order)
    for caveat in (r"Trade Gap", r"quarantin", r"Non-trading day", r"02:55 BDT archive"):
        assert re.search(caveat, order), caveat


def test_release_order_says_what_the_old_brief_does_if_a_later_step_slips() -> None:
    order = _order()
    slip = re.search(r"^\*\*If [^\n]*slips?\b.*?(?=\n\s*\n|\Z)", order, flags=re.MULTILINE | re.DOTALL)
    assert slip, "no '**If … slips' paragraph"
    text = " ".join(slip.group(0).split())
    assert re.search(r"a810fcb", text) and re.search(r"do not merge `?the-brief#215", text, flags=re.IGNORECASE)


def test_no_release_doc_claims_the_deployed_brief_is_unchanged_on_the_new_producer() -> None:
    root = RUNBOOK.parent.parent
    for name in ("AGENTS.md", "AGENT_LEARNINGS.md", "deploy/README.md"):
        assert not re.search(r"byte-identical cards|builds the same cards", (root / name).read_text()), name


# R3 design (C/r3-publication-design.md): "Do not reactivate the old DELETE publisher. Leave its
# timer paused until a corrected atomic publisher is available." A plain stop does not hold:
# brief.timer is Persistent=true, so a reboot re-arms it and catches the missed fire up.
def test_release_rollback_disables_the_timer_instead_of_only_stopping_it() -> None:
    rollback = _rollback_paragraph(_order())
    assert "systemctl disable --now brief.timer" in rollback
    assert not re.search(r"keep\s+`?brief\.timer`?\s+stopped", rollback)


# --- R3d fix round 2 -------------------------------------------------------------------------
# Round-1 tests pinned the keywords of these rules, not their qualifiers: a runbook that
# re-enabled the pre-R3 publisher after a rollback, skipped the Vercel wait, let a failed
# recipient check carry on, or kept the old 07:30 heartbeat still passed (reviewer probes
# review-scratch/fixR3d-spec-r1/probe.py and fixR3d-adversarial-r1/runbook_mutants.py; mutant
# harness C/r2-claude/fixR3d-r2-mutants/runbook_mutants.py).

# Re-arming the timer in any form: `systemctl enable|start|restart … brief.timer` or "re-enable".
_REARMS_THE_TIMER = re.compile(r"\b(?:re-?)?enabl(?:e|es|ed|ing)\b|systemctl\s+(?:start|restart)\b[^`]*brief\.timer",
                               flags=re.IGNORECASE)


def _paragraph_starting(body: str, bold_lead: str) -> str:
    match = re.search(rf"^{re.escape(bold_lead)}.*?(?=\n\s*\n|\Z)", body, flags=re.MULTILINE | re.DOTALL)
    assert match, f"no paragraph starting {bold_lead!r}"
    return " ".join(match.group(0).split())


def test_release_rollback_never_lets_the_pre_r3_publisher_run_again() -> None:
    rollback = _rollback_paragraph(_order())
    assert re.search(r"\bFirst `sudo systemctl disable --now brief\.timer`", rollback), \
        "disabling the timer must be the rollback's FIRST action"
    assert not re.search(r"\boptional", rollback, flags=re.IGNORECASE)
    assert not _REARMS_THE_TIMER.search(rollback), _REARMS_THE_TIMER.search(rollback)
    assert re.search(r"keep `brief\.timer` disabled\b(?:(?!\. ).)*?\buntil a corrected atomic publisher is merged",
                     rollback), "the timer stays disabled until a corrected ATOMIC publisher is merged"
    assert re.search(r"\brun no `brief\.cli run --publish` from a pre-R3 checkout", rollback)


def test_generic_rollback_sends_any_rollback_across_r3_to_the_release_order() -> None:
    generic = _section(r"Rollback")
    assert RELEASE_ORDER_ANCHOR in generic
    assert re.search(r"0006|publish_brief_atomic", generic)
    assert re.search(r"delete-and-insert", generic)
    across_r3 = _paragraph_starting(generic, "**Not for a rollback across the R3 merge**")
    assert RELEASE_ORDER_ANCHOR in across_r3
    assert re.search(r"`disable --now` the timer first and keep it disabled until a corrected atomic publisher "
                     r"is merged", across_r3)
    assert not _REARMS_THE_TIMER.search(across_r3), _REARMS_THE_TIMER.search(across_r3)


def _recipient_check_code() -> str:
    match = re.search(r"```bash\n(.*?fetch_subscribers.*?)```", _order(), flags=re.DOTALL)
    assert match, "no bash block with the recipient check"
    return "\n".join(line.strip() for line in match.group(1).splitlines())


def test_recipient_check_waits_for_the_live_signup_and_blocks_the_release_on_failure() -> None:
    step = _brief_step()
    assert re.search(r"\bfirst wait until Vercel production serves the merge commit\b", step)
    assert not re.search(r"\b(?:no|not|n't|never|without|skip)\b[^.]{0,40}wait until Vercel", step,
                         flags=re.IGNORECASE)
    assert re.search(r"If it fails \([^)]*\), do not run steps 6[–-]7: run `sudo systemctl disable --now "
                     r"brief\.timer`[^.]*?, and stop\.", step)
    assert not re.search(r"\b(?:still|carry on|continue|go ahead|proceed)\b[^.]{0,30}steps 6", step,
                         flags=re.IGNORECASE)
    assert re.search(r"\bOnly after it passes, steps 6[–-]7", step)
    for removal in re.finditer(r"\b(?:delete|remove|drop|skip)\b", step, flags=re.IGNORECASE):
        assert "never" in step[max(0, removal.start() - 25):removal.start()], \
            f"incompatible subscriber rows are reviewed, never removed: …{step[removal.start() - 40:removal.end() + 20]}…"


def test_recipient_check_snippet_fails_loudly_when_validation_fails() -> None:
    code = _recipient_check_code()
    tried, _, rest = code.partition("except Exception")
    failure, _, success = rest.partition('print(json.dumps({\\"validation_complete\\": True')
    assert "len(fetch_subscribers())" in tried and success, code
    assert '\\"validation_complete\\": False' in failure and '\\"validation_complete\\": True' not in failure
    exits = re.findall(r"sys\.exit\((\d+)\)", failure)
    assert exits and all(int(code_) != 0 for code_ in exits), exits


def test_slip_default_is_to_keep_the_old_brief_paused() -> None:
    slip = re.search(r"^\*\*If [^\n]*slips?\b.*?(?=\n\s*\n|\Z)", _order(), flags=re.MULTILINE | re.DOTALL)
    assert slip
    parts = re.search(r"- \(a\)(.*?)- \(b\)(.*)", " ".join(slip.group(0).split()))
    assert parts, "the slip paragraph needs options (a) and (b)"
    keep_paused, resume = parts.groups()
    assert re.match(r"\s*keep it paused\b", keep_paused) and re.match(r"\s*resume it\b", resume)
    assert "no decision is recorded" in keep_paused and "no decision is recorded" not in resume


def test_heartbeat_switch_replaces_the_0730_line_before_0945_the_same_morning() -> None:
    steps = _numbered_steps(_order())
    step = steps[_step_of(steps, (r"09:45 BDT", r"heartbeat", re.escape(HEARTBEAT_ANCHOR)))]
    assert re.search(r"\bthe same morning, before 09:45 BDT\b", step)
    words = _timing_words_before(step, r"09:45 BDT")
    assert words and set(words) == {"before"}, words
    assert re.search(r"\breplace the old 07:30 BDT heartbeat line \(`30 7 \* \* \*`\) with the 09:45 BDT one", step)
    assert not re.search(r"\b(?:keep|leave)\b[^.]{0,30}07:30|\badd the 09:45", step, flags=re.IGNORECASE)


def test_transition_window_says_the_old_brief_hides_its_trade_gap_card() -> None:
    order = " ".join(_order().replace("**", "").split())
    assert re.search(r"\bhide its Trade Gap card\b", order)
    assert not re.search(r"\b(?:keeps?|shows?|still shows?)\s+its Trade Gap card", order, flags=re.IGNORECASE)


# --- R3d controller close (2 Oct 2026) ---------------------------------------------------------
# Round-2 reviewers inverted rules whose qualifier was never pinned ('before' -> 'after', 'keep
# stopped' -> 'let run', 'service_role only' -> 'and anon'); every mutant still passed
# (review-scratch/fixR3d-adversarial-r2/r2_mutants.py, fixR3d-spec-r2/new_mutants.py). Each
# binding release sentence is now pinned verbatim (whitespace-collapsed), so an inversion fails.
_BINDING_RELEASE_SENTENCES = (
    # Step 3 (round 4) and step 5 (the new Brief) precede the new Brief's first fire.
    "Round 4 NBR exclusion, owner-reviewed, before the new Brief's first fire.",
    "Until round 4 is applied the new Brief must not go live.",
    "**The new Brief, before its 08:00 BDT fire.** First confirm the new producer's first daily write has landed:",
    # Step 4: the migration precedes the Brief merge and grants EXECUTE to service_role only.
    "Migration 0006, owner-applied through the Supabase SQL editor**, before the Brief merge",
    "(EXECUTE for `service_role` only)",
    # Step 2: a late R1 keeps the producer's timers stopped.
    "If R1 cannot finish before 02:55 BDT, keep the EconDelta aggregate timers stopped until it has",
    # Before step 1: the pause is a real stop.
    "Pause the Brief with a real stop, not only the environment flag",
    # Rollback (R3 design: never a schema drop or a table restore as a code rollback).
    "Leave migration 0006 in place; it is additive and the old reader code ignores it.",
    "Never restore a whole-table backup as a code rollback.",
    # B4: incompatible stored rows are reviewed by the owner, never removed.
    "The owner reviews the incompatible stored rows; never delete or skip them to get past this check.",
    "first wait until Vercel production serves the merge commit, so the old, looser signup cannot add a bad row "
    "after the check. Then run this read-only check.",
)


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def test_binding_release_sentences_are_stated_exactly() -> None:
    order = _collapsed(_order())
    missing = [s for s in _BINDING_RELEASE_SENTENCES if s not in order]
    assert missing == [], missing


def test_release_order_never_inverts_its_timing_or_privilege_rules() -> None:
    order = _collapsed(_order())
    inversions = (
        r"\bafter (?:its|the new Brief's) (?:08:00 BDT|first) fire",
        r"\bafter the Brief merge\b",
        r"\b(?:no need|not need|without)\b[^.]{0,40}first daily write",
        r"\blet\b[^.]{0,60}aggregate[^.]{0,40}\brun\b",
        r"environment flag alone is enough|real stop is optional",
        r"EXECUTE for[^)]*\b(?:anon|authenticated|PUBLIC)\b",
        r"\b(?:drop|revert|remove)\b[^.]{0,20}migration 0006",
        r"(?<!Never )restor\w* a whole-table backup",
        r"\b(?:prune|purge|clean up|delete|remove|drop|skip)\b[^.]{0,30}(?:incompatible|stored) (?:subscriber )?rows",
        r"\b(?:never|not|n't)\s+hide its Trade Gap card",
        r"\bcheck\b[^.]{0,30}\bbefore the merge\b",
    )
    found = [p for p in inversions if re.search(p, order, flags=re.IGNORECASE)]
    assert found == [], found


def test_release_rollback_runs_no_publisher_by_service_or_cli() -> None:
    rollback = _rollback_paragraph(_order())
    assert not re.search(r"systemctl\s+(?:start|restart)\b[^`]*brief\.(?:timer|service)", rollback), rollback
    publishes = len(re.findall(r"brief\.cli run --publish", rollback))
    forbidden_ones = len(re.findall(r"\brun no `brief\.cli run --publish`", rollback))
    assert publishes == forbidden_ones == 1, (publishes, forbidden_ones)


def test_slip_lead_never_chooses_the_old_publisher_by_default() -> None:
    slip = re.search(r"^\*\*If [^\n]*slips?\b.*?(?=\n\s*\n|\Z)", _order(), flags=re.MULTILINE | re.DOTALL)
    assert slip
    lead, _, options = _collapsed(slip.group(0)).partition("- (a)")
    assert options, "the slip paragraph needs options (a) and (b)"
    assert not re.search(r"\(b\)|\bresume\b|systemctl\s+start", lead, flags=re.IGNORECASE), lead
