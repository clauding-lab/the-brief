# The Brief Redesign — Part 2 (VPS Deploy → Shadow Soak → Cutover) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the V4 pipeline shipped in Part 1 (343 tests green on `feat/v4-retarget` @ `c3d2e83`), deploy it to the Hetzner VPS under systemd, run a 3-day shadow soak against the existing GHA `update.py`, then cut over so the VPS is the sole producer and the old Anthropic-API pipeline stops spending.

**Architecture:** A thin `brief.cli` entrypoint runs `pipeline.run()`, writes `index.html` / `email.txt` / `run_report.json` to `--artifacts-dir`, optionally git-pushes to a branch, and posts a Discord webhook. Systemd timer fires `Sun..Fri 00:30 UTC` (06:30 BDT). Shadow mode pushes to `shadow/YYYY-MM-DD`, skips email, and flags drift vs the current GHA output. Cutover flips the VPS pipeline to push `main` + send email, and disables the GHA schedule. Rollback is a single env flag (`BRIEF_DRY_RUN=1`) plus re-enabling the GHA schedule.

**Tech Stack:** Python 3.11+ (VPS ships 3.14), pydantic v2, pytest, `subprocess` for `claude -p` and `git`, `urllib` for Supabase + Discord webhooks, systemd (unit + timer + logrotate), bash (`install.sh` / `uninstall.sh`). No new Python deps.

---

## Prerequisites & Invariants

Before starting:

- `feat/v4-retarget` @ `c3d2e83` is pushed, suite passes (343 tests).
- VPS has Python 3.11+ (`python3 --version`), `/home/adnan/.npm-global/bin/claude` resolves to CLI `2.1.119` or newer (1M-context build), and `~/.claude/.credentials.json` holds a live Max OAuth session.
- EconDelta is already deployed under `/home/adnan/econdelta/` with `data/latest.json` refreshed by its own timers — the Brief reads that file, does not re-scrape.
- Supabase `metric_history` table exists (Part 1 migration already applied in prod).
- The GHA workflow `daily-update.yml` still runs (produces today's `index.html` and email) — do NOT touch it until Phase 6 cutover. It is our safety net.

Hard invariants throughout:

1. **No Anthropic API calls on VPS.** Only Max OAuth via the CLI. No `ANTHROPIC_API_KEY` in `/etc/brief.env`.
2. **BDT times in outputs, UTC in systemd `OnCalendar`.** `06:30 BDT = 00:30 UTC`. The Brief's header dates render in BDT — never switch internals to UTC.
3. **Fail-closed.** If `pipeline.run()` raises, the CLI exits non-zero, systemd marks the run failed, the Discord webhook fires with a FAILED line, and nothing gets pushed to git.
4. **Shadow runs never email subscribers and never push to `main`.**
5. **`update.py` stays in the repo through Phase 6.7.** Removal is a final step, after 14 days of stable V4 operation.

---

## File Structure

### New files

```
brief/
  cli.py                      # argparse entrypoint: `python -m brief.cli run --artifacts-dir=... [--shadow] [--dry-run]`
  report.py                   # build_run_report() → dict, write_run_report(path, report)
  notify.py                   # post_discord(webhook_url, title, summary, status)
  gitops.py                   # push_artifacts(branch, artifacts_dir, message)

deploy/
  brief.env.example           # Template env file for /etc/brief.env
  brief.service               # systemd service (oneshot)
  brief.timer                 # systemd timer (Sun..Fri 00:30 UTC)
  install.sh                  # VPS install: clone, venv, systemd link, env file chmod
  uninstall.sh                # VPS uninstall: disable, unlink, leave env + logs
  logrotate.conf              # Rotate /home/adnan/the-brief/logs/*.log daily, 14 days
  README.md                   # Operator runbook (manual run, common failures)

docs/ops/
  part2-preflight.md          # Phase 5.1 checklist (operator-run before install)
  part2-shadow-observations.md # Phase 6.1/6.3 daily-drift notes scaffold
  part2-cutover-runbook.md    # Phase 6.4 step-by-step cutover
  part2-rollback-runbook.md   # Phase 6.5 rollback (BRIEF_DRY_RUN=1 + GHA re-enable)

tests/
  test_cli.py                 # argparse behavior + exit codes + artifact writes
  test_report.py              # run_report.json shape + cost aggregation + degraded flags
  test_notify.py              # Discord payload shape, network mocked
  test_gitops.py              # branch naming, commit message, push args (git mocked)
```

### Modified files

```
brief/pipeline.py             # call_reports gains cost_usd + duration_s + tokens (Task 5.4)
brief/claude/max_client.py    # MaxCallResult already exposes total_cost_usd; expose duration_s + input/output tokens (Task 5.4)
requirements.txt              # No new runtime deps; confirm current pin list unchanged
.github/workflows/daily-update.yml # Disable schedule (Phase 6.4 only; keep workflow_dispatch)
update.py                     # Add deprecation header (Phase 6.4); deletion deferred to 6.7
```

### Files that already exist and MUST NOT be touched in this plan

- `brief/pipeline.py` `run()` / `run_pipeline()` signatures — frozen from Part 1.
- `brief/render/v4/*` — frozen from Part 1.
- `brief/claude/max_client.py` `run_max()` signature — only the result dataclass gets new fields (additive, no breaking changes).
- `the-brief.html`, `build.sh` — legacy; no edits until cutover.

---

## Commit Strategy

- Every task ends with one commit. No task leaves uncommitted work across a step boundary.
- Commit type prefixes: `feat(cli|cli_report|cli_notify|gitops)`, `feat(deploy)`, `chore(deploy)`, `docs(ops)`, `ci(cutover)`, `chore(cleanup)`.
- Only Phase 6.4 and Phase 6.7 touch files outside `brief/`, `deploy/`, `docs/`, and `tests/` — that is intentional; all earlier tasks are VPS-deploy-neutral and safe to land on `docs/part2-plan` iteratively.
- After each phase exit gate passes, squash-merge `docs/part2-plan` into `feat/v4-retarget` (or a dedicated `feat/v4-deploy` branch if Part 1 PR is still open).

---

## Phase 5 — VPS Deploy

Goal: by end of Phase 5, running `sudo systemctl start brief.service` on the VPS produces `index.html`, `email.txt`, and `run_report.json` in `/home/adnan/the-brief/artifacts/`, pushes to branch `shadow/YYYY-MM-DD`, and posts a "clean" Discord message. **No email is sent. No push to `main`.**

### Task 5.1: VPS preflight verification

**Files:**
- Create: `docs/ops/part2-preflight.md`

Operator-run checklist. Does not execute anything from an agent; the agent authors the doc so the operator (adnan) can tick items before running `install.sh`.

- [ ] **Step 1: Write the preflight checklist**

```markdown
# Brief Part 2 — VPS Preflight Checklist

Run each command on the VPS (`ssh adnan@135.181.43.68` — or local if you're already there).
Tick the checkbox once the expected output is confirmed. Do not start `install.sh` until every item is green.

## 1. Binary resolution

- [ ] `/home/adnan/.npm-global/bin/claude --version` → prints `2.1.119` or newer.
- [ ] `echo $PATH | tr ':' '\n' | grep npm-global` → the `.npm-global/bin` path appears (interactive shell only; systemd won't see this — we pin via `CLAUDE_BINARY` in the service file).
- [ ] `/home/adnan/.npm-global/bin/claude -p "Reply only with the word ECHO" --model claude-opus-4-7 --output-format json --no-session-persistence --tools "" --permission-mode bypassPermissions` → returns JSON with `"result":"ECHO"` within 3 seconds.
- [ ] `/usr/bin/claude --version` either doesn't exist OR prints an older version — leave it; we will not use it.

## 2. EconDelta data source

- [ ] `ls -la /home/adnan/econdelta/data/latest.json` → file exists, mtime is within the last 24h.
- [ ] `jq '.generated_at' /home/adnan/econdelta/data/latest.json` → prints an ISO-8601 timestamp from today (or yesterday on weekends).
- [ ] `sudo -u adnan cat /home/adnan/econdelta/data/latest.json | head -c 200` → JSON is readable by the `adnan` user (the service runs as `adnan`).

## 3. Credentials

- [ ] `test -f /etc/brief.env || echo MISSING` → prints `MISSING` (we will create it in 5.9; abort install if this file already exists with other contents).
- [ ] `test -f /home/adnan/.claude/.credentials.json && stat -c '%a' /home/adnan/.claude/.credentials.json` → prints `600` or `640`. Max OAuth session must be live.

## 4. Supabase connectivity

- [ ] From VPS: `curl -sS -o /dev/null -w '%{http_code}\n' "$SUPABASE_URL/rest/v1/metric_history?select=metric_id&limit=1" -H "apikey: $SUPABASE_SERVICE_ROLE_KEY"` → prints `200`. (Use the values that will go into `/etc/brief.env`.)

## 5. Headlines scrape

- [ ] From VPS: `curl -sS -o /dev/null -w '%{http_code}\n' https://www.thedailystar.net/business` → prints `200`. Repeat for `prothomalo.com`, `tbsnews.net`, `dhakatribune.com`, `businessstandardbd.com`. Any `403` / `429` is an ASN block — flag it; we'll note in `docs/ops/part2-shadow-observations.md` and rely on the per-source degraded path.

## 6. Systemd readiness

- [ ] `systemctl --version` → 249 or newer.
- [ ] `test -d /etc/systemd/system && echo OK` → prints `OK`.
- [ ] `systemctl list-timers --all | grep econdelta` → existing econdelta timers appear (confirms the systemd-timer pattern is already proven on this host).

## 7. Disk

- [ ] `df -h /home/adnan` → at least 2 GB free.
- [ ] `df -h /` → at least 500 MB free (for `/var/log` journal).

When every item is ticked, proceed to `deploy/install.sh`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/ops/part2-preflight.md
git commit -m "docs(ops): part-2 VPS preflight checklist"
```

### Task 5.2: `brief.cli` entrypoint (TDD)

**Files:**
- Create: `brief/cli.py`
- Create: `tests/test_cli.py`

The CLI is the single entrypoint for systemd. Signature: `python -m brief.cli run --artifacts-dir=PATH [--shadow] [--dry-run] [--today=YYYY-MM-DD]`.

Exit codes:
- `0` — pipeline succeeded, all artifacts written.
- `1` — pipeline raised (unexpected). Stack printed to stderr. `run_report.json` NOT guaranteed to be written.
- `2` — pipeline completed but one or more Claude calls failed validation (fallbacks used). Artifacts written. Discord notify sends `status=degraded`.
- `3` — `--dry-run` was requested and completed successfully without writing artifacts.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli.py
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from brief import cli
from brief.pipeline import PipelineConfig, RunResult


@pytest.fixture
def fake_run_result() -> RunResult:
    return RunResult(
        sections=[],
        html="<html>ok</html>",
        claude_outputs={},
        call_reports=[
            {"name": "headlines_curation", "status": "ok", "reason": None,
             "cost_usd": 0.12, "duration_s": 2.1},
        ],
        map_coords=[],
        todays_call=None,
        read_order=[],
        email_text="email digest text",
    )


def test_cli_run_writes_all_artifacts(tmp_path: Path, monkeypatch, fake_run_result):
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    rc = cli.main(["run", f"--artifacts-dir={tmp_path}"])
    assert rc == 0
    assert (tmp_path / "index.html").read_text() == "<html>ok</html>"
    assert (tmp_path / "email.txt").read_text() == "email digest text"
    report = json.loads((tmp_path / "run_report.json").read_text())
    assert report["status"] == "ok"
    assert report["total_cost_usd"] == pytest.approx(0.12)


def test_cli_dry_run_does_not_write(tmp_path: Path, monkeypatch, fake_run_result):
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    rc = cli.main(["run", f"--artifacts-dir={tmp_path}", "--dry-run"])
    assert rc == 3
    assert not (tmp_path / "index.html").exists()


def test_cli_degraded_exit_code(tmp_path: Path, monkeypatch):
    degraded = RunResult(
        sections=[], html="x", claude_outputs={},
        call_reports=[{"name": "headlines_curation", "status": "error",
                       "reason": "timeout", "cost_usd": 0.0, "duration_s": 30.0}],
        email_text="x",
    )
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: degraded)
    rc = cli.main(["run", f"--artifacts-dir={tmp_path}"])
    assert rc == 2


def test_cli_pipeline_exception_returns_1(tmp_path: Path, monkeypatch):
    def boom(cfg, **kw):
        raise RuntimeError("econdelta missing")
    monkeypatch.setattr(cli, "run", boom)
    rc = cli.main(["run", f"--artifacts-dir={tmp_path}"])
    assert rc == 1


def test_cli_shadow_flag_threads_through(tmp_path: Path, monkeypatch, fake_run_result):
    captured = {}
    def spy(cfg, **kw):
        captured["shadow"] = kw.get("shadow", False)
        return fake_run_result
    monkeypatch.setattr(cli, "run_with_mode", spy)
    cli.main(["run", f"--artifacts-dir={tmp_path}", "--shadow"])
    assert captured["shadow"] is True


def test_cli_rejects_unknown_subcommand():
    with pytest.raises(SystemExit) as ei:
        cli.main(["sneeze"])
    assert ei.value.code != 0
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: all 6 fail with `ModuleNotFoundError: brief.cli`.

- [ ] **Step 3: Write minimal `brief/cli.py`**

```python
"""Thin CLI entrypoint for the Brief V4 pipeline.

Usage:
  python -m brief.cli run --artifacts-dir=PATH [--shadow] [--dry-run]
                         [--today=YYYY-MM-DD]

Exit codes:
  0 ok                    — all Claude calls succeeded, artifacts written
  1 error                 — pipeline raised; stack to stderr
  2 degraded              — pipeline completed but ≥1 Claude call failed
  3 dry-run-ok            — --dry-run requested, no artifacts written
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import date
from pathlib import Path

from brief.pipeline import PipelineConfig, RunResult, run
from brief.report import build_run_report, write_run_report


def run_with_mode(cfg: PipelineConfig, *, shadow: bool) -> RunResult:
    """Thin indirection to let tests stub the whole pipeline call."""
    return run(cfg)


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="brief", description="The Brief V4 pipeline CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Run the pipeline and write artifacts")
    r.add_argument("--artifacts-dir", required=True, type=Path)
    r.add_argument("--shadow", action="store_true",
                   help="Shadow mode: do not push to main, do not email")
    r.add_argument("--dry-run", action="store_true",
                   help="Run the pipeline but do not write artifacts")
    r.add_argument("--today", default=None,
                   help="Override today's date (YYYY-MM-DD); default: system date")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse(argv or sys.argv[1:])
    today = date.fromisoformat(ns.today) if ns.today else date.today()
    cfg = PipelineConfig(today=today)

    try:
        rr = run_with_mode(cfg, shadow=ns.shadow)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1

    if ns.dry_run:
        return 3

    ns.artifacts_dir.mkdir(parents=True, exist_ok=True)
    (ns.artifacts_dir / "index.html").write_text(rr.html, encoding="utf-8")
    (ns.artifacts_dir / "email.txt").write_text(rr.email_text, encoding="utf-8")

    report = build_run_report(rr, shadow=ns.shadow)
    write_run_report(ns.artifacts_dir / "run_report.json", report)

    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: 6 pass. Some tests depend on `brief.report` which doesn't exist yet — if those fail with `ImportError`, continue to Task 5.3 and come back to re-run.

- [ ] **Step 5: Confirm full suite still green**

Run: `.venv/bin/pytest --tb=no --no-cov -q`
Expected: 349 passed (343 prior + 6 new).

- [ ] **Step 6: Commit**

```bash
git add brief/cli.py tests/test_cli.py
git commit -m "feat(cli): add brief.cli run subcommand with exit-code contract"
```

### Task 5.3: `brief.report` — run_report.json writer (TDD)

**Files:**
- Create: `brief/report.py`
- Create: `tests/test_report.py`

Report schema (final shape — do not add fields beyond this without updating the plan):

```json
{
  "schema_version": 1,
  "generated_at": "2026-04-25T06:30:12+06:00",
  "today": "2026-04-25",
  "shadow": false,
  "status": "ok",
  "duration_s": 184.2,
  "call_reports": [
    {"name": "headlines_curation", "status": "ok", "reason": null,
     "cost_usd": 0.12, "duration_s": 2.1,
     "tokens": {"input": 1200, "output": 450}}
  ],
  "total_cost_usd": 1.23,
  "degraded_sections": ["dse"],
  "builder_failures": [],
  "git_push": {"branch": "shadow/2026-04-25", "sha": "abc1234", "pushed": true}
}
```

`status` rules:
- `ok` — every `call_reports[].status == "ok"` AND `builder_failures == []`.
- `degraded` — at least one call_report is `invalid` or `error`, OR at least one builder failed (but pipeline still returned).
- `error` — reserved for the CLI (returned when `run()` raises); `build_run_report` never emits this.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_report.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from brief.pipeline import RunResult
from brief.report import build_run_report, write_run_report


def _rr(call_reports: list[dict], sections=None) -> RunResult:
    return RunResult(
        sections=sections or [],
        html="", claude_outputs={},
        call_reports=call_reports, email_text="",
    )


def test_ok_when_all_calls_ok():
    rr = _rr([
        {"name": "headlines_curation", "status": "ok", "reason": None,
         "cost_usd": 0.12, "duration_s": 2.0},
        {"name": "exec_signals", "status": "ok", "reason": None,
         "cost_usd": 0.40, "duration_s": 6.0},
    ])
    r = build_run_report(rr, shadow=False)
    assert r["status"] == "ok"
    assert r["total_cost_usd"] == pytest.approx(0.52)
    assert r["degraded_sections"] == []


def test_degraded_when_one_call_invalid():
    rr = _rr([
        {"name": "headlines_curation", "status": "invalid", "reason": "missing key",
         "cost_usd": 0.10, "duration_s": 1.0},
        {"name": "exec_signals", "status": "ok", "reason": None,
         "cost_usd": 0.40, "duration_s": 6.0},
    ])
    r = build_run_report(rr, shadow=False)
    assert r["status"] == "degraded"


def test_degraded_when_call_error():
    rr = _rr([
        {"name": "headlines_curation", "status": "error", "reason": "timeout",
         "cost_usd": 0.0, "duration_s": 30.0},
    ])
    r = build_run_report(rr, shadow=False)
    assert r["status"] == "degraded"


def test_total_cost_handles_missing_cost_usd():
    rr = _rr([
        {"name": "headlines_curation", "status": "ok", "reason": None},  # no cost_usd
    ])
    r = build_run_report(rr, shadow=False)
    assert r["total_cost_usd"] == 0.0


def test_degraded_sections_collected_from_section_freshness():
    class FakeSection:
        def __init__(self, sid, freshness):
            self.id = sid
            self.freshness = freshness

    rr = _rr(
        [{"name": "x", "status": "ok", "cost_usd": 0.1, "duration_s": 1.0}],
        sections=[FakeSection("bb", "fresh"),
                  FakeSection("dse", "unavailable"),
                  FakeSection("fx", "stale")],
    )
    r = build_run_report(rr, shadow=False)
    assert r["degraded_sections"] == ["dse", "fx"]
    assert r["status"] == "degraded"  # unavailable/stale count as degraded


def test_shadow_flag_is_threaded():
    rr = _rr([{"name": "x", "status": "ok", "cost_usd": 0.0, "duration_s": 0.0}])
    r = build_run_report(rr, shadow=True)
    assert r["shadow"] is True


def test_write_run_report_roundtrips(tmp_path: Path):
    rr = _rr([{"name": "x", "status": "ok", "cost_usd": 1.5, "duration_s": 1.0}])
    report = build_run_report(rr, shadow=False)
    write_run_report(tmp_path / "run_report.json", report)
    loaded = json.loads((tmp_path / "run_report.json").read_text())
    assert loaded["total_cost_usd"] == 1.5
    assert loaded["schema_version"] == 1


def test_schema_version_is_pinned():
    rr = _rr([{"name": "x", "status": "ok", "cost_usd": 0.0, "duration_s": 0.0}])
    r = build_run_report(rr, shadow=False)
    assert r["schema_version"] == 1
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `.venv/bin/pytest tests/test_report.py -v`
Expected: 8 fail with `ModuleNotFoundError: brief.report`.

- [ ] **Step 3: Write `brief/report.py`**

```python
"""run_report.json writer.

Aggregates per-call status + cost into a single report blob. Consumed by
brief.cli (writes the file) and brief.notify (summarises for Discord).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brief.cadence import now_bdt
from brief.pipeline import RunResult

SCHEMA_VERSION = 1
_DEGRADED_FRESHNESS = {"stale", "unavailable", "pending"}


def build_run_report(rr: RunResult, *, shadow: bool) -> dict[str, Any]:
    call_reports: list[dict[str, Any]] = []
    total_cost = 0.0
    for cr in rr.call_reports:
        entry = dict(cr)
        entry.setdefault("cost_usd", 0.0)
        entry.setdefault("duration_s", 0.0)
        total_cost += float(entry["cost_usd"] or 0.0)
        call_reports.append(entry)

    degraded_sections = [
        getattr(s, "id", "?") for s in rr.sections
        if getattr(s, "freshness", "fresh") in _DEGRADED_FRESHNESS
    ]

    any_call_bad = any(cr["status"] != "ok" for cr in call_reports)
    status = "degraded" if (any_call_bad or degraded_sections) else "ok"

    now = now_bdt()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "today": now.date().isoformat(),
        "shadow": shadow,
        "status": status,
        "duration_s": 0.0,  # filled in by caller if wanted; CLI wraps run() for timing
        "call_reports": call_reports,
        "total_cost_usd": round(total_cost, 4),
        "degraded_sections": degraded_sections,
        "builder_failures": [],  # populated once builders surface structured errors
        "git_push": {"branch": None, "sha": None, "pushed": False},
    }


def write_run_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n",
                    encoding="utf-8")
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `.venv/bin/pytest tests/test_report.py -v`
Expected: 8 pass.

- [ ] **Step 5: Re-run the CLI test suite to close Task 5.2's dependency**

Run: `.venv/bin/pytest tests/test_cli.py tests/test_report.py -v`
Expected: 14 pass.

- [ ] **Step 6: Commit**

```bash
git add brief/report.py tests/test_report.py
git commit -m "feat(cli_report): run_report.json builder + writer"
```

### Task 5.4: Cost + duration tracking into `call_reports`

**Files:**
- Modify: `brief/pipeline.py` (4 `call_reports.append(...)` sites + the 2 new sites for `risk_map_layout` and `todays_call`)
- Modify: `brief/claude/max_client.py` (add `duration_s` and `tokens` to `MaxCallResult`)
- Test: `tests/claude/test_max_client.py` (add 2 tests)
- Test: `tests/test_pipeline_integration_v4.py` (assert new fields)

Today the 4 existing call_reports entries carry only `name`, `status`, `reason`. The report builder already tolerates missing `cost_usd` (Task 5.3 test), but shadow observations need real numbers. Thread `total_cost_usd` and a stopwatch through `run_max` → `call_*` sites.

- [ ] **Step 1: Write failing tests**

```python
# tests/claude/test_max_client.py — append

from unittest.mock import patch
from brief.claude.max_client import MaxCallResult, run_max


def test_max_call_result_exposes_duration_and_tokens():
    fake_stdout = json.dumps({
        "result": '{"x":1}',
        "usage": {"input_tokens": 100, "output_tokens": 50},
        "total_cost_usd": 0.0042,
    })
    with patch("subprocess.run") as m:
        m.return_value.stdout = fake_stdout
        m.return_value.returncode = 0
        m.return_value.stderr = ""
        r = run_max(prompt="hi")
    assert r.total_cost_usd == pytest.approx(0.0042)
    assert r.duration_s >= 0
    assert r.tokens == {"input": 100, "output": 50}
```

```python
# tests/test_pipeline_integration_v4.py — append

def test_call_reports_include_cost_and_duration(monkeypatch):
    # Use the existing run() path with a faked max client that returns a known cost
    ...  # (copy the pattern from existing V4 integration tests; assert
         # every call_report entry has cost_usd and duration_s keys, type float)
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `.venv/bin/pytest tests/claude/test_max_client.py::test_max_call_result_exposes_duration_and_tokens -v`
Expected: FAIL on missing `.duration_s` attribute.

- [ ] **Step 3: Extend `MaxCallResult`**

```python
# brief/claude/max_client.py — replace the dataclass
@dataclass(frozen=True)
class MaxCallResult:
    raw_text: str
    parsed: Any | None
    usage: dict[str, Any]
    total_cost_usd: float | None
    duration_s: float
    tokens: dict[str, int]  # {"input": N, "output": M}
```

```python
# inside run_max(...), before returning:
import time
_t0 = time.monotonic()  # place at the top of the try
# ... existing subprocess code ...
_duration = time.monotonic() - _t0
_usage = outer.get("usage") or {}
_tokens = {
    "input": int(_usage.get("input_tokens") or 0),
    "output": int(_usage.get("output_tokens") or 0),
}
return MaxCallResult(
    raw_text=raw_text,
    parsed=parsed,
    usage=_usage,
    total_cost_usd=outer.get("total_cost_usd"),
    duration_s=_duration,
    tokens=_tokens,
)
```

- [ ] **Step 4: Thread cost + duration into every `call_reports.append(...)` site**

For each `call_reports.append({...})` in `brief/pipeline.py`, the `try` block wraps `run_max(...)` → `MaxCallResult`. Capture the result (already done in most sites) and include:

```python
call_reports.append({
    "name": "headlines_curation",
    "status": "ok" if v.ok else "invalid",
    "reason": v.reason,
    "cost_usd": result.total_cost_usd or 0.0,
    "duration_s": result.duration_s,
    "tokens": result.tokens,
})
```

Apply the same pattern to the error branches (cost/duration are 0.0 / 0.0 there).

Also add `call_reports.append(...)` entries inside `call_risk_map_layout` and `call_todays_call` (currently silent on success). Their reports should land in `pr.call_reports` — extend the function signatures to take and append to the shared list.

- [ ] **Step 5: Run tests, confirm pass**

Run: `.venv/bin/pytest -v`
Expected: 349 + 2 new = 351 passed. Investigate any existing pipeline-integration test that asserted `call_count == 4` and update to 6 (4 existing + risk_map + todays_call).

- [ ] **Step 6: Commit**

```bash
git add brief/pipeline.py brief/claude/max_client.py tests/
git commit -m "feat(cli_report): cost_usd + duration_s + tokens in every call_report"
```

### Task 5.5: `brief.notify` — Discord webhook (TDD)

**Files:**
- Create: `brief/notify.py`
- Create: `tests/test_notify.py`

Discord message shape:

```
The Brief · Vol II · No 42 · 2026-04-25
✅ ok  —  duration 184s  —  cost $1.23
Lead: "Taka slides, central bank signals defence"
Shadow: https://github.com/clauding-lab/the-brief/tree/shadow/2026-04-25
```

(Error variant: `❌ error — RuntimeError: econdelta missing` and no lead / no link.)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_notify.py
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from brief.notify import build_payload, post_discord


def _report(**overrides):
    base = {
        "schema_version": 1,
        "generated_at": "2026-04-25T06:30:12+06:00",
        "today": "2026-04-25",
        "shadow": True,
        "status": "ok",
        "duration_s": 184.2,
        "total_cost_usd": 1.23,
        "degraded_sections": [],
        "call_reports": [],
        "git_push": {"branch": "shadow/2026-04-25",
                     "sha": "abc1234", "pushed": True},
    }
    base.update(overrides)
    return base


def test_payload_ok():
    p = build_payload(_report(), lead_headline="Taka slides",
                      repo_slug="clauding-lab/the-brief")
    assert "✅ ok" in p["content"]
    assert "$1.23" in p["content"]
    assert "shadow/2026-04-25" in p["content"]
    assert "Taka slides" in p["content"]


def test_payload_degraded():
    p = build_payload(_report(status="degraded", degraded_sections=["dse"]),
                      lead_headline=None,
                      repo_slug="clauding-lab/the-brief")
    assert "⚠️ degraded" in p["content"]
    assert "dse" in p["content"]


def test_payload_error_has_no_git_link():
    p = build_payload(_report(status="error",
                              git_push={"branch": None, "sha": None, "pushed": False}),
                      lead_headline=None,
                      repo_slug="clauding-lab/the-brief")
    assert "❌ error" in p["content"]
    assert "shadow/" not in p["content"]


def test_post_discord_sends_http_post(monkeypatch):
    captured = {}
    class _Resp:
        status = 204
        def read(self): return b""
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake_urlopen(req, timeout=10):
        captured["url"] = req.full_url
        captured["body"] = req.data.decode()
        return _Resp()
    monkeypatch.setattr("brief.notify.urlopen", fake_urlopen)
    rc = post_discord("https://discord.example/webhook/abc",
                      payload={"content": "hi"})
    assert rc == 204
    assert captured["url"] == "https://discord.example/webhook/abc"
    assert json.loads(captured["body"]) == {"content": "hi"}


def test_post_discord_swallows_non_2xx_and_returns_status(monkeypatch):
    class _Resp:
        status = 429
        def read(self): return b""
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr("brief.notify.urlopen", lambda *a, **k: _Resp())
    rc = post_discord("https://discord.example/webhook/abc", payload={"content": "x"})
    assert rc == 429  # caller logs; Discord flakiness must not fail the pipeline


def test_post_discord_network_failure_returns_zero(monkeypatch):
    def boom(*a, **k):
        raise OSError("dns")
    monkeypatch.setattr("brief.notify.urlopen", boom)
    rc = post_discord("https://discord.example/webhook/abc", payload={"content": "x"})
    assert rc == 0
```

- [ ] **Step 2: Run tests, confirm failure**

Run: `.venv/bin/pytest tests/test_notify.py -v`
Expected: 6 fail on `ModuleNotFoundError: brief.notify`.

- [ ] **Step 3: Write `brief/notify.py`**

```python
"""Discord webhook notifier for the Brief pipeline.

Intentionally swallows all network errors — Discord flakiness must never fail
a pipeline run. Returns the HTTP status code (or 0 on socket error) for logging.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen


def build_payload(
    report: dict[str, Any],
    *,
    lead_headline: str | None,
    repo_slug: str,
) -> dict[str, str]:
    status = report["status"]
    icon = {"ok": "✅", "degraded": "⚠️", "error": "❌"}.get(status, "❔")
    today = report["today"]
    duration = int(round(report.get("duration_s") or 0.0))
    cost = report.get("total_cost_usd") or 0.0
    lines = [f"The Brief · {today} · {icon} {status}",
             f"duration {duration}s · cost ${cost:.2f}"]
    if report.get("degraded_sections"):
        lines.append(f"degraded: {', '.join(report['degraded_sections'])}")
    if lead_headline:
        lines.append(f'Lead: "{lead_headline}"')
    gp = report.get("git_push") or {}
    if gp.get("pushed") and gp.get("branch"):
        lines.append(f"https://github.com/{repo_slug}/tree/{gp['branch']}")
    return {"content": "\n".join(lines)}


def post_discord(webhook_url: str, *, payload: dict[str, Any]) -> int:
    body = json.dumps(payload).encode("utf-8")
    req = Request(webhook_url, data=body,
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            return getattr(resp, "status", 0)
    except Exception:
        return 0
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `.venv/bin/pytest tests/test_notify.py -v`
Expected: 6 pass.

- [ ] **Step 5: Wire `post_discord` into `brief/cli.py`**

```python
# At the top of brief/cli.py
import os
from brief.notify import build_payload, post_discord

# Just before `return 0 if report["status"] == "ok" else 2`:
webhook = os.environ.get("DISCORD_WEBHOOK_URL")
if webhook:
    repo = os.environ.get("BRIEF_REPO_SLUG", "clauding-lab/the-brief")
    lead = rr.todays_call.headline if rr.todays_call else None
    post_discord(webhook, payload=build_payload(report, lead_headline=lead,
                                                 repo_slug=repo))
```

Add a CLI test that monkeypatches `post_discord` and asserts it was called exactly once when `DISCORD_WEBHOOK_URL` is set, zero times when unset.

- [ ] **Step 6: Run tests**

Run: `.venv/bin/pytest -v`
Expected: 351 + 6 new + 2 new CLI = 359 passed.

- [ ] **Step 7: Commit**

```bash
git add brief/notify.py brief/cli.py tests/test_notify.py tests/test_cli.py
git commit -m "feat(cli_notify): Discord webhook on every CLI run, fail-open"
```

### Task 5.6: `brief.gitops` — push artifacts to shadow branch (TDD)

**Files:**
- Create: `brief/gitops.py`
- Create: `tests/test_gitops.py`

Shadow soak requires pushing the rendered `index.html` back to the repo on a dated branch, so side-by-side diffs against the GHA output on `main` are easy. Cutover reuses the same function with `branch="main"` + `push=True`.

Requirements:
- Pure wrapper around `git` subprocess calls; no library deps.
- Callable: `push_artifacts(repo_dir, branch, artifacts_dir, message, *, dry_run=False)` → `{"branch": ..., "sha": ..., "pushed": bool}`.
- Creates the branch from `origin/main` fresh each call (shadow branches are disposable; overwrite OK).
- For `main`, cherry-picks on top of current `origin/main` (fast-forward-only; abort if main has diverged).
- Never force-pushes.
- `dry_run=True` → run all git commands locally but skip `git push`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_gitops.py
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, call

import pytest

from brief.gitops import push_artifacts


def _ok(stdout="abc1234\n"):
    return subprocess.CompletedProcess([], 0, stdout, "")


def test_shadow_branch_flow(tmp_path: Path, monkeypatch):
    calls = []
    def fake_run(argv, **kw):
        calls.append(argv)
        return _ok("abc1234\n")
    monkeypatch.setattr("brief.gitops.subprocess.run", fake_run)
    r = push_artifacts(repo_dir=tmp_path, branch="shadow/2026-04-25",
                       artifacts_dir=tmp_path / "artifacts",
                       message="shadow run 2026-04-25")
    assert r["pushed"] is True
    assert r["branch"] == "shadow/2026-04-25"
    # Expected git sequence:
    assert calls[0][:4] == ["git", "-C", str(tmp_path), "fetch"]
    assert "checkout" in calls[1]
    assert calls[-1][:5] == ["git", "-C", str(tmp_path), "push"]


def test_dry_run_does_not_push(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr("brief.gitops.subprocess.run",
                        lambda a, **k: (calls.append(a), _ok())[1])
    r = push_artifacts(repo_dir=tmp_path, branch="shadow/x",
                       artifacts_dir=tmp_path / "artifacts",
                       message="m", dry_run=True)
    assert r["pushed"] is False
    assert not any(a[:4] == ["git", "-C", str(tmp_path), "push"] for a in calls)


def test_main_branch_refuses_non_fast_forward(tmp_path: Path, monkeypatch):
    def fake_run(argv, **kw):
        if "merge-base" in argv:
            return _ok("deadbeef\n")
        if "rev-parse" in argv and "origin/main" in argv:
            return _ok("other123\n")  # origin/main advanced beyond merge-base
        return _ok()
    monkeypatch.setattr("brief.gitops.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="diverged|fast-forward"):
        push_artifacts(repo_dir=tmp_path, branch="main",
                       artifacts_dir=tmp_path / "artifacts",
                       message="cutover")
```

- [ ] **Step 2: Run tests, confirm failure**

- [ ] **Step 3: Write `brief/gitops.py`**

```python
"""Git push-back for Brief artifacts.

Shadow mode: fresh branch from origin/main, overwrite, push.
Main mode: fast-forward only; abort if main has advanced beyond our base.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _git(repo: Path, *args: str, check: bool = True) -> str:
    cp = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=check,
    )
    return cp.stdout.strip()


def push_artifacts(
    *,
    repo_dir: Path,
    branch: str,
    artifacts_dir: Path,
    message: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    _git(repo_dir, "fetch", "origin", "--prune")

    if branch == "main":
        base = _git(repo_dir, "merge-base", "HEAD", "origin/main")
        tip = _git(repo_dir, "rev-parse", "origin/main")
        if base != tip:
            raise RuntimeError(
                "main has diverged; refusing non-fast-forward push. "
                f"base={base[:8]} origin/main={tip[:8]}"
            )
        _git(repo_dir, "checkout", "main")
    else:
        # shadow: fresh branch from origin/main; overwrite local copy if exists
        _git(repo_dir, "checkout", "-B", branch, "origin/main")

    # Copy artifacts into the repo root (index.html, email.txt, run_report.json)
    for name in ("index.html", "email.txt", "run_report.json"):
        src = artifacts_dir / name
        if src.exists():
            (repo_dir / name).write_bytes(src.read_bytes())

    _git(repo_dir, "add", "index.html", "email.txt", "run_report.json")
    _git(repo_dir, "commit", "-m", message, check=False)  # no-op if nothing changed
    sha = _git(repo_dir, "rev-parse", "HEAD")

    pushed = False
    if not dry_run:
        _git(repo_dir, "push", "origin", branch)
        pushed = True
    return {"branch": branch, "sha": sha[:7], "pushed": pushed}
```

- [ ] **Step 4: Wire into `brief/cli.py`**

When `--shadow` is set: call `push_artifacts(repo_dir=Path.cwd(), branch=f"shadow/{today}", ...)`.
When neither `--shadow` nor `--dry-run`: call `push_artifacts(repo_dir=..., branch="main", ...)`.

Thread the returned dict into the `report["git_push"]` field before writing `run_report.json` (Task 5.3's placeholder field gets populated here).

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest -v`
Expected: +3 gitops tests, +2 CLI gitops-wiring tests = 364 passed.

- [ ] **Step 6: Commit**

```bash
git add brief/gitops.py brief/cli.py tests/
git commit -m "feat(gitops): push_artifacts with shadow-fresh / main-ff-only policy"
```

### Task 5.7: `deploy/brief.env.example` template

**Files:**
- Create: `deploy/brief.env.example`
- Create: `deploy/README.md` (partial — runbook, expanded in 5.11)

- [ ] **Step 1: Write the example env file**

```bash
# /etc/brief.env — chmod 640 root:adnan
# Copy to /etc/brief.env and fill in real values before `systemctl start brief.service`.

# --- Claude Max CLI -----------------------------------------------------------
# Pin absolute path so systemd (which does not source ~/.bashrc) finds the
# 1M-context 2.1.119 build at /home/adnan/.npm-global/bin/claude, not the
# older root-installed /usr/bin/claude.
CLAUDE_BINARY=/home/adnan/.npm-global/bin/claude

# --- EconDelta data source ----------------------------------------------------
ECONDELTA_DATA=/home/adnan/econdelta/data/latest.json

# --- Supabase (history read/write) -------------------------------------------
SUPABASE_URL=https://ssbliukchgibjcjohibi.supabase.co
SUPABASE_SERVICE_ROLE_KEY=REDACTED
SUPABASE_SERVICE_KEY=REDACTED

# --- Email (Brevo SMTP) -------------------------------------------------------
# Only read by the legacy update.py during shadow soak. Safe to leave set
# during shadow (VPS pipeline does not send). Required after cutover.
BREVO_API_KEY=REDACTED
FROM_EMAIL=adnan.rshd@gmail.com

# --- Notifications ------------------------------------------------------------
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/REDACTED

# --- Pipeline behaviour -------------------------------------------------------
# BRIEF_DRY_RUN=1 means: run the pipeline, compute the report, post Discord,
# but do NOT write artifacts and do NOT git push. Rollback switch.
BRIEF_DRY_RUN=0

# Repo slug used in Discord links. Do not change unless the repo moves.
BRIEF_REPO_SLUG=clauding-lab/the-brief
```

- [ ] **Step 2: Commit**

```bash
git add deploy/brief.env.example
git commit -m "feat(deploy): /etc/brief.env template"
```

### Task 5.8: systemd service + timer

**Files:**
- Create: `deploy/brief.service`
- Create: `deploy/brief.timer`

Modelled on `/home/adnan/econdelta/deploy/econdelta-aggregate.service` (confirmed working). Deltas: different working dir, different entrypoint, longer timeout, reads `/etc/brief.env`.

- [ ] **Step 1: Write `deploy/brief.service`**

```ini
[Unit]
Description=The Brief — daily Bangladesh economy digest (V4)
Documentation=https://github.com/clauding-lab/the-brief
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=adnan
Group=adnan
WorkingDirectory=/home/adnan/the-brief
EnvironmentFile=/etc/brief.env

ExecStart=/home/adnan/the-brief/.venv/bin/python -m brief.cli run \
  --artifacts-dir=/home/adnan/the-brief/artifacts \
  --shadow

# Resource limits — pipeline does ~6 subprocess calls to claude, each up to
# 64K tokens; memory stays well under 600M in practice.
MemoryMax=600M
MemoryHigh=500M
CPUQuota=80%
TasksMax=128

# Hardening
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/adnan/the-brief /home/adnan/.claude

# Timeouts — pipeline target 15m, hard cap 20m.
TimeoutStartSec=20min

# Logging — systemd journal + append to file
StandardOutput=append:/home/adnan/the-brief/logs/brief-systemd.log
StandardError=append:/home/adnan/the-brief/logs/brief-systemd.log
SyslogIdentifier=brief

[Install]
WantedBy=multi-user.target
```

Notes:
- `--shadow` is hard-coded in the service file for Phase 5. Cutover (Phase 6.4) replaces it with no flag.
- `ReadWritePaths` includes `~/.claude` because the Max CLI writes/reads `.credentials.json`. `ProtectHome=read-only` lets that one dir through via the RW allow-list.

- [ ] **Step 2: Write `deploy/brief.timer`**

```ini
[Unit]
Description=Run The Brief daily at 06:30 BDT (00:30 UTC)

[Timer]
OnCalendar=Sun..Fri 00:30 UTC
Persistent=true
Unit=brief.service

[Install]
WantedBy=timers.target
```

Notes:
- Sun..Fri in BDT maps to Sun..Fri in UTC at 00:30 (the BDT day is +6h, so Sun 06:30 BDT starts the same calendar day as Sun 00:30 UTC — no wrap).
- `Persistent=true` fires a missed run once the host comes back up (journal captures the catch-up).

- [ ] **Step 3: Commit**

```bash
git add deploy/brief.service deploy/brief.timer
git commit -m "feat(deploy): brief.service + brief.timer (Sun..Fri 00:30 UTC)"
```

### Task 5.9: `deploy/install.sh` + `deploy/uninstall.sh` + `deploy/logrotate.conf`

**Files:**
- Create: `deploy/install.sh` (bash, executable)
- Create: `deploy/uninstall.sh` (bash, executable)
- Create: `deploy/logrotate.conf`

Pattern: match `/home/adnan/econdelta/deploy/install.sh` — idempotent, uses `set -euo pipefail`, prints what it's about to do, bails if `/etc/brief.env` is missing.

- [ ] **Step 1: Write `deploy/install.sh`**

```bash
#!/usr/bin/env bash
# Install The Brief V4 pipeline on the VPS. Idempotent.
#
# Prereqs (see docs/ops/part2-preflight.md):
#   - Python 3.11+ available at /usr/bin/python3
#   - /home/adnan/.npm-global/bin/claude works (Max CLI 2.1.119+)
#   - /etc/brief.env exists, chmod 640, root:adnan
#   - Repo checked out at /home/adnan/the-brief
#
# Usage:  sudo /home/adnan/the-brief/deploy/install.sh

set -euo pipefail

REPO=/home/adnan/the-brief
ETC=/etc/brief.env
SYSD=/etc/systemd/system

if [[ $EUID -ne 0 ]]; then
  echo "must run as root (sudo)"; exit 1
fi
if [[ ! -f $ETC ]]; then
  echo "missing $ETC — copy from $REPO/deploy/brief.env.example and fill in values"; exit 1
fi

echo "[install] venv"
sudo -u adnan /usr/bin/python3 -m venv "$REPO/.venv"
sudo -u adnan "$REPO/.venv/bin/pip" install --upgrade pip
sudo -u adnan "$REPO/.venv/bin/pip" install -r "$REPO/requirements.txt"

echo "[install] artifacts + logs dirs"
sudo -u adnan mkdir -p "$REPO/artifacts" "$REPO/logs"

echo "[install] logrotate"
install -m 644 "$REPO/deploy/logrotate.conf" /etc/logrotate.d/brief

echo "[install] systemd units"
install -m 644 "$REPO/deploy/brief.service" "$SYSD/brief.service"
install -m 644 "$REPO/deploy/brief.timer"   "$SYSD/brief.timer"
chmod 640 "$ETC"; chown root:adnan "$ETC"

systemctl daemon-reload
systemctl enable brief.timer
systemctl start brief.timer

echo "[install] done. Next scheduled run:"
systemctl list-timers brief.timer --no-pager
echo
echo "To run immediately for verification:  sudo systemctl start brief.service"
echo "To tail logs:                         journalctl -u brief.service -f"
```

- [ ] **Step 2: Write `deploy/uninstall.sh`**

```bash
#!/usr/bin/env bash
# Uninstall The Brief. Leaves /etc/brief.env, logs, and artifacts in place.
# Run `rm -rf /home/adnan/the-brief/{artifacts,logs,.venv}` manually if you
# want a clean wipe.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "sudo please"; exit 1; fi

systemctl disable --now brief.timer || true
systemctl disable --now brief.service || true
rm -f /etc/systemd/system/brief.service /etc/systemd/system/brief.timer
rm -f /etc/logrotate.d/brief
systemctl daemon-reload
echo "[uninstall] done. /etc/brief.env and /home/adnan/the-brief left untouched."
```

- [ ] **Step 3: Write `deploy/logrotate.conf`**

```
/home/adnan/the-brief/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 adnan adnan
    sharedscripts
}
```

- [ ] **Step 4: Make the scripts executable + commit**

```bash
chmod +x deploy/install.sh deploy/uninstall.sh
git add deploy/install.sh deploy/uninstall.sh deploy/logrotate.conf
git update-index --chmod=+x deploy/install.sh deploy/uninstall.sh
git commit -m "feat(deploy): install.sh / uninstall.sh / logrotate.conf"
```

### Task 5.10: `deploy/README.md` operator runbook

**Files:**
- Create (overwrite): `deploy/README.md`

- [ ] **Step 1: Write the runbook**

```markdown
# The Brief — VPS operator runbook

## One-time install

1. Complete `docs/ops/part2-preflight.md`.
2. `ssh adnan@135.181.43.68`
3. `cd ~/the-brief && git checkout feat/v4-retarget && git pull`
4. `sudo cp deploy/brief.env.example /etc/brief.env`
5. Edit `/etc/brief.env` — fill every `REDACTED`. `sudo chmod 640 /etc/brief.env && sudo chown root:adnan /etc/brief.env`
6. `sudo deploy/install.sh`
7. `sudo systemctl start brief.service` (first manual run).
8. `journalctl -u brief.service -f` — watch to completion.
9. Inspect `~/the-brief/artifacts/run_report.json` — `status` must be `ok` or `degraded`.
10. Confirm Discord webhook fired. Confirm the `shadow/YYYY-MM-DD` branch exists on GitHub.

## Daily operation (after install)

Nothing to do. Timer fires Sun–Fri at 06:30 BDT automatically. Discord pings on every run.

## Common failures

| Symptom | Fix |
|---|---|
| `journalctl`: `Claude CLI binary not found: claude` | `/etc/brief.env` missing `CLAUDE_BINARY` or path wrong. Re-point at `/home/adnan/.npm-global/bin/claude`. |
| `journalctl`: `Claude CLI exited 1: Session not found` | Max OAuth expired. On the host: `claude` interactively, re-authenticate. |
| `run_report.json`: `status: degraded`, one call `"status": "error"`, `reason: "timed out"` | Expected during Bangladesh bank holidays when sources lag. Check the next-day run before alarming. |
| `git push` fails in logs | Deploy key missing or expired. See `docs/ops/part2-preflight.md` section 4 and re-issue. |
| Discord webhook silent | `DISCORD_WEBHOOK_URL` unset or wrong. `curl -X POST -H 'Content-Type: application/json' -d '{"content":"test"}' "$DISCORD_WEBHOOK_URL"` should return 204. |

## Rollback

See `docs/ops/part2-rollback-runbook.md`. TL;DR: `BRIEF_DRY_RUN=1` in `/etc/brief.env`, `sudo systemctl restart brief.timer`, re-enable GHA schedule in `.github/workflows/daily-update.yml`.

## Uninstall

`sudo deploy/uninstall.sh` — leaves env + logs + artifacts intact.
```

- [ ] **Step 2: Commit**

```bash
git add deploy/README.md
git commit -m "docs(deploy): VPS operator runbook"
```

### Task 5.11: VPS clone + first run (operator-driven, agent authors checklist)

**Files:**
- Create: `docs/ops/part2-first-run.md`

This is the only "on-host" step of Phase 5. Agent does not SSH to the VPS. It writes the checklist the operator follows. Success means `run_report.json` on disk, `shadow/YYYY-MM-DD` branch on GitHub, Discord ping received.

- [ ] **Step 1: Write the first-run checklist**

```markdown
# Brief Part 2 — First Run (VPS)

Perform after `deploy/install.sh` completes without error. Tick each item.

- [ ] `sudo systemctl status brief.timer` → `active (waiting)`, `Trigger:` shows the next 00:30 UTC firing.
- [ ] `sudo systemctl start brief.service` — trigger a manual run NOW (do not wait for timer).
- [ ] `journalctl -u brief.service -f` — watch until `Main PID ... (code=exited, status=0/SUCCESS)` or `status=2/DEGRADED`. Any other exit is a failure — read the stack, file an issue, do NOT proceed.
- [ ] `cat ~/the-brief/artifacts/run_report.json | jq '.status, .total_cost_usd, .degraded_sections, .git_push'` — expect:
  - `status` ∈ {`ok`, `degraded`}
  - `total_cost_usd` ≤ 5.00
  - `degraded_sections` — empty or a short list
  - `git_push.pushed` = `true`, branch = `shadow/<today>`
- [ ] GitHub: visit `https://github.com/clauding-lab/the-brief/tree/shadow/<today>` — commit present, `index.html` size 80–200 KB.
- [ ] Discord: ping received in the configured channel, contains today's date and a green/yellow status icon.
- [ ] Tail `~/the-brief/logs/brief-systemd.log` — no stack traces, no `claude-opus-4-7: unknown model` type errors.

If every item is green: Phase 5 exit gate passed. Proceed to Phase 6 (shadow soak).
```

- [ ] **Step 2: Commit**

```bash
git add docs/ops/part2-first-run.md
git commit -m "docs(ops): Phase 5 first-run checklist"
```

---

## Phase 5 Exit Gate

- `docs/ops/part2-first-run.md` ticked end-to-end.
- Full test suite green: `.venv/bin/pytest --tb=no --no-cov -q` → 364 passed (local).
- At least one `shadow/YYYY-MM-DD` branch on GitHub with `run_report.json` showing `"status": "ok"` or `"status": "degraded"` with documented reasons.
- Discord webhook delivered at least one notification.

If any check fails, fix and re-run Phase 5.x — do not start Phase 6.

---

## Phase 6 — Shadow Soak + Cutover

Goal: run V4 in shadow for 3+ consecutive clean days, diff against the GHA `update.py` output, then flip V4 to `main` + email and disable the GHA schedule. Keep a one-flag rollback path ready throughout.

### Task 6.1: Shadow-mode observation scaffold

**Files:**
- Create: `docs/ops/part2-shadow-observations.md`

The scaffold is the place adnan (operator) writes a daily note while the soak runs. Template is pre-filled with the comparison checklist.

- [ ] **Step 1: Write the scaffold**

```markdown
# Brief Part 2 — Shadow Observations

Log one entry per day during shadow soak. A run counts as **clean** iff every box is ticked. Cutover requires **3 consecutive clean days**.

---

## 2026-04-26 (Sun)

- Shadow branch: `shadow/2026-04-26` — commit `_____`
- GHA run: actions run `_____`
- [ ] Both pipelines produced an `index.html`.
- [ ] `jq '.status' shadow/run_report.json` == `"ok"`.
- [ ] All 3 original Claude calls (`headlines_curation`, `exec_signals`, `bankerread`) `status == "ok"`.
- [ ] Both new Claude calls (`risk_map_layout`, `todays_call`) `status == "ok"` or cleanly fell back.
- [ ] `degraded_sections` — `[]` OR documented below.
- [ ] `total_cost_usd` ≤ 5.00.
- [ ] Visual diff (eyeball GHA's `index.html` vs shadow's): V4 layout matches the decisions doc. Today's Call aside present. Risk map renders 12 dots. No missing sections. No sections showing raw JSON.
- [ ] Email digest (`email.txt`) — subject-line text plausible, 5 headlines present, links non-empty.

**Drift notes:** _____

**Decision:** [ ] clean  [ ] dirty → reason _____

---

## 2026-04-27 (Mon)
...same scaffold...

---

## Cutover eligibility

- [ ] 3 consecutive clean days (≥ 2026-04-XX)
- [ ] No rollbacks during the soak window
- [ ] No ad-hoc manual pipeline edits that would invalidate the observations

Once eligible: proceed to `docs/ops/part2-cutover-runbook.md`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/ops/part2-shadow-observations.md
git commit -m "docs(ops): shadow-observation daily scaffold (3 clean required)"
```

### Task 6.2: Cutover runbook

**Files:**
- Create: `docs/ops/part2-cutover-runbook.md`

- [ ] **Step 1: Write the runbook**

```markdown
# Brief Part 2 — Cutover Runbook

**Do not start this until `docs/ops/part2-shadow-observations.md` shows 3 consecutive clean days.**

## Step 1 — Pause the GHA schedule

Edit `.github/workflows/daily-update.yml`:

```yaml
on:
  # schedule:
  #   - cron: '30 0 * * 0-5'     # commented out; kept for quick re-enable
  workflow_dispatch:              # keep for emergencies
```

Commit on `main` directly (small, reversible):
```
git add .github/workflows/daily-update.yml
git commit -m "ci(cutover): pause GHA schedule; VPS is primary"
git push origin main
```

## Step 2 — Flip VPS pipeline to main + email

On the VPS:
```
sudo sed -i 's|--shadow|--push-main --email|' /etc/systemd/system/brief.service
sudo systemctl daemon-reload
```

(Agents: the actual CLI flags — `--push-main --email` — must already be implemented. See Task 6.4 pre-reqs in this plan.)

## Step 3 — Add deprecation header to `update.py`

```
# update.py
# DEPRECATED: superseded by brief.cli (V4 pipeline). This file is kept
# only for emergency rollback via GHA workflow_dispatch. Scheduled removal:
# 2026-05-09 (14 days after cutover).
```

## Step 4 — Verify next scheduled run

- `ssh adnan@135.181.43.68 'systemctl list-timers brief.timer --no-pager'`
- Confirm the next trigger is tomorrow 00:30 UTC.
- Next morning (06:30 BDT): confirm `main` branch got a new commit from `clauding-lab` deploy key, email landed in adnan's inbox, Discord said `✅ ok`, no `shadow/` branch from today (since we're in main mode now).

## Step 5 — Monitor 7 days

- Daily Discord check. Daily `jq '.status' main/run_report.json` on the VPS.
- Any `status == "error"` → execute rollback runbook immediately, do not wait.
- At day 7 (2026-05-03 at the earliest): cutover is ratified. Proceed to Task 6.7 (`update.py` removal).
```

- [ ] **Step 2: Commit**

```bash
git add docs/ops/part2-cutover-runbook.md
git commit -m "docs(ops): cutover runbook (requires 3 clean shadow days)"
```

### Task 6.3: Rollback runbook

**Files:**
- Create: `docs/ops/part2-rollback-runbook.md`

- [ ] **Step 1: Write the runbook**

```markdown
# Brief Part 2 — Rollback Runbook

Invoke when V4 produces a bad `index.html`, a hallucinated number, a silently empty section, or any failure that would be visible to subscribers.

**Target:** within 15 minutes, GHA is back in control and today's send is either the legacy output or paused.

## Option A — V4 ran and produced a bad output (most common)

1. `ssh adnan@135.181.43.68`
2. `sudo sed -i 's|BRIEF_DRY_RUN=0|BRIEF_DRY_RUN=1|' /etc/brief.env`
3. `sudo systemctl stop brief.service` (if still running)
4. If a bad commit already landed on `main`: `cd ~/the-brief && git revert HEAD && git push origin main`.
5. Locally, re-enable GHA schedule:
   ```
   git checkout main
   # uncomment the schedule block in .github/workflows/daily-update.yml
   git commit -am "ci(rollback): re-enable GHA schedule"
   git push origin main
   ```
6. Trigger the GHA workflow manually via `workflow_dispatch` if the subscribers need today's send.

## Option B — V4 hasn't run yet, pre-emptive disable

1. `ssh adnan@135.181.43.68`
2. `sudo systemctl disable --now brief.timer`
3. `sudo sed -i 's|BRIEF_DRY_RUN=0|BRIEF_DRY_RUN=1|' /etc/brief.env` (belt-and-braces).
4. Re-enable GHA schedule as in Option A step 5.

## Exit from rollback

Once the root cause is fixed and a fresh shadow-soak of 3 clean days completes: redo Task 6.2 cutover runbook.
```

- [ ] **Step 2: Commit**

```bash
git add docs/ops/part2-rollback-runbook.md
git commit -m "docs(ops): rollback runbook (BRIEF_DRY_RUN + GHA re-enable)"
```

### Task 6.4: CLI flags for main-push + email (pre-req for cutover)

**Files:**
- Modify: `brief/cli.py` (add `--push-main` and `--email` mutually-exclusive-with-`--shadow`)
- Modify: `tests/test_cli.py` (4 new tests)
- Modify: `brief/notify.py` (add `send_email` helper — SMTP via Brevo API, not the `anthropic` path)
- Create: `brief/email_send.py` (if SMTP complexity warrants a separate module)
- Create: `tests/test_email_send.py`

The cutover runbook references `--push-main --email`. Those flags must exist before the operator runs it. This task lands them on `docs/part2-plan` so they ship with Phase 5's V4 code base and are available at cutover time.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli.py — append

def test_shadow_and_push_main_are_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["run", f"--artifacts-dir={tmp_path}", "--shadow", "--push-main"])


def test_push_main_calls_gitops_with_main_branch(tmp_path, monkeypatch, fake_run_result):
    captured = {}
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    monkeypatch.setattr("brief.cli.push_artifacts",
                        lambda **kw: captured.update(kw) or
                                      {"branch": "main", "sha": "abc1234",
                                       "pushed": True})
    cli.main(["run", f"--artifacts-dir={tmp_path}", "--push-main"])
    assert captured["branch"] == "main"


def test_email_flag_invokes_send_email(tmp_path, monkeypatch, fake_run_result):
    sent = []
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    monkeypatch.setattr("brief.cli.send_email",
                        lambda **kw: sent.append(kw))
    monkeypatch.setenv("BREVO_API_KEY", "x")
    monkeypatch.setenv("FROM_EMAIL", "adnan@example.com")
    cli.main(["run", f"--artifacts-dir={tmp_path}", "--push-main", "--email"])
    assert len(sent) == 1
    assert sent[0]["from_email"] == "adnan@example.com"


def test_email_without_api_key_is_skipped(tmp_path, monkeypatch, fake_run_result, capsys):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.setattr(cli, "run", lambda cfg, **kw: fake_run_result)
    monkeypatch.setattr("brief.cli.push_artifacts",
                        lambda **kw: {"branch": "main", "sha": "x", "pushed": True})
    sent = []
    monkeypatch.setattr("brief.cli.send_email", lambda **kw: sent.append(kw))
    cli.main(["run", f"--artifacts-dir={tmp_path}", "--push-main", "--email"])
    assert sent == []  # gracefully skipped
```

- [ ] **Step 2: Extend `brief/cli.py`**

```python
# parser additions
group = r.add_mutually_exclusive_group()
group.add_argument("--shadow", action="store_true")
group.add_argument("--push-main", action="store_true",
                   help="Post-cutover: push artifacts to main")
r.add_argument("--email", action="store_true",
               help="Send the email digest via Brevo (requires BREVO_API_KEY)")

# body additions — between the write-artifacts block and the Discord post:
if ns.push_main or ns.shadow:
    from brief.gitops import push_artifacts
    branch = "main" if ns.push_main else f"shadow/{today.isoformat()}"
    gp = push_artifacts(
        repo_dir=Path.cwd(), branch=branch,
        artifacts_dir=ns.artifacts_dir,
        message=f"Brief {today.isoformat()} [{'main' if ns.push_main else 'shadow'}]",
    )
    report["git_push"] = gp
    # Re-write report.json with the push outcome folded in
    write_run_report(ns.artifacts_dir / "run_report.json", report)

if ns.email and os.environ.get("BREVO_API_KEY") and os.environ.get("FROM_EMAIL"):
    from brief.email_send import send_email
    send_email(
        from_email=os.environ["FROM_EMAIL"],
        api_key=os.environ["BREVO_API_KEY"],
        subject=f"The Brief · {today.isoformat()}",
        html=rr.html,
        text=rr.email_text,
    )
```

- [ ] **Step 3: Write `brief/email_send.py`**

```python
"""Send the email digest via Brevo's transactional-email REST API.

No new dependency — urllib only. Fail-open: log-and-skip on network error, do
not crash the pipeline (the artifact push is the canonical ship; email is a
best-effort amplifier).
"""
from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen

_BREVO = "https://api.brevo.com/v3/smtp/email"


def send_email(
    *,
    from_email: str,
    api_key: str,
    subject: str,
    html: str,
    text: str,
    to_emails: list[str] | None = None,
) -> int:
    payload: dict[str, Any] = {
        "sender": {"email": from_email},
        "to": [{"email": e} for e in (to_emails or [from_email])],
        "subject": subject,
        "htmlContent": html,
        "textContent": text,
    }
    req = Request(_BREVO, data=json.dumps(payload).encode(),
                  headers={"content-type": "application/json",
                           "api-key": api_key, "accept": "application/json"})
    try:
        with urlopen(req, timeout=30) as r:
            return getattr(r, "status", 0)
    except Exception:
        return 0
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest -v`
Expected: +4 CLI tests, +2 email_send tests = 370 passed.

- [ ] **Step 5: Commit**

```bash
git add brief/cli.py brief/email_send.py tests/
git commit -m "feat(cli): --push-main + --email flags for post-cutover use"
```

### Task 6.5: `update.py` removal

**Files:**
- Delete: `update.py`
- Delete: `ingest.py` (if unused post-cutover — confirm via `grep -r "from ingest" .`)
- Delete: `the-brief.html` (V1 shell, no longer referenced)
- Delete: `build.sh` (already a banner-only file per c0f91c3; remove entirely)
- Modify: `.github/workflows/daily-update.yml` (delete the file or strip to a no-op)
- Modify: `README.md` (update architecture description if it still references `update.py`)

**Do NOT start this task until 7 consecutive post-cutover days of clean V4 operation are recorded in `docs/ops/part2-shadow-observations.md` (continued post-cutover).** Target: 2026-05-09 at the earliest.

- [ ] **Step 1: Confirm no references to the doomed files**

```bash
grep -rn "from ingest\|import ingest\|update\.py\|the-brief\.html\|build\.sh" \
  --exclude-dir=.venv --exclude-dir=.git --exclude-dir=artifacts .
```

Expected output: only the deprecation header inside `update.py` itself, and possibly a mention in `README.md` / `docs/`. Nothing in `brief/`, `tests/`, or `deploy/`.

- [ ] **Step 2: Delete the files**

```bash
git rm update.py ingest.py the-brief.html build.sh
git rm .github/workflows/daily-update.yml
```

- [ ] **Step 3: Update `README.md`**

Replace any paragraph that explains "the-brief.html shell + update.py monolith + GHA schedule" with a short pointer: "See `brief/cli.py` for the pipeline entrypoint and `deploy/README.md` for VPS ops."

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest -v`
Expected: all tests still pass (none of them import the deleted modules).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore(cleanup): remove update.py / ingest.py / the-brief.html / build.sh / daily-update.yml"
```

### Task 6.6: Post-migration success-criteria audit

**Files:**
- Create: `docs/ops/part2-migration-audit.md`

Mirror the 8 success criteria from `docs/superpowers/specs/2026-04-21-the-brief-redesign.md` §10. Author a checklist where each criterion gets a single-line evidence cell. This doc is filled in once, 7 days after cutover, and committed to `main` as the definitive "migration complete" record.

- [ ] **Step 1: Write the audit scaffold**

```markdown
# Brief Part 2 — Migration Audit (7 days post-cutover)

Tick each criterion with evidence. Complete on 2026-05-09 at earliest.

| # | Criterion | Evidence | OK |
|---|---|---|---|
| 1 | Zero GHA runs in the last 7 days | `gh run list -w daily-update.yml --limit 20` → 0 scheduled | [ ] |
| 2 | Zero Anthropic API spend | Anthropic console → last-7-day usage == $0 | [ ] |
| 3 | Daily ship Sun–Fri | 5–6 commits on `main` with brief artifacts in the last 7 days | [ ] |
| 4 | No fabricated facts (10 random numeric spot checks) | Traced 10 values → all cite source + as_of | [ ] |
| 5 | Graceful degradation observed ≥1× | `jq -r 'select(.degraded_sections | length > 0) | .today' run_report.json` → ≥1 day | [ ] |
| 6 | Run duration < 15m (p95 over 7 days) | `jq .duration_s run_report.json` → max ≤ 900 | [ ] |
| 7 | Claude validators pass 100% | No `status: invalid` in any `call_reports` over 7 days | [ ] |
| 8 | Rollback rehearsed once | `BRIEF_DRY_RUN=1` + GHA re-enable + reversion recorded in dated note | [ ] |

**Migration complete when all 8 boxes are ticked.**
```

- [ ] **Step 2: Commit**

```bash
git add docs/ops/part2-migration-audit.md
git commit -m "docs(ops): post-cutover 7-day audit scaffold (success criteria)"
```

### Task 6.7: Land `docs/part2-plan` into mainline

**Files:** none (git only)

- [ ] **Step 1: Push the branch**

```bash
git push -u origin docs/part2-plan
```

- [ ] **Step 2: Open the PR** (manual — operator)

```bash
gh pr create --base feat/v4-retarget --head docs/part2-plan \
  --title "Part 2: VPS deploy + shadow soak + cutover" \
  --body "Implements the Part 2 plan authored on docs/part2-plan. See docs/superpowers/plans/2026-04-25-brief-part2-deploy-soak-cutover.md."
```

- [ ] **Step 3: Merge policy**

Squash-merge into `feat/v4-retarget` (not `main` — `main` still has the legacy V1 until cutover lands there separately). Keep the squash commit body linking to the plan doc.

---

## Phase 6 Exit Gate

- All 8 success criteria in `docs/ops/part2-migration-audit.md` green.
- `main` branch on GitHub has the V4 code, not `update.py`.
- Anthropic API usage console shows $0 for 7 consecutive days.
- Zero `brief/` hotfix commits on `main` during those 7 days.

---

## Self-Review Notes (author → reader)

- **Spec coverage.** Spec §8 Phases 5 & 6 → Tasks 5.1–5.11 + 6.1–6.7. Spec §10 success criteria → Task 6.6 audit. Spec §11 env vars → Task 5.7 `brief.env.example`. Spec's "env flag `BRIEF_DRY_RUN=1`" → Task 5.7 and rollback runbook (6.3). Spec's "Max OAuth via existing `~/.claude/.credentials.json`" → Task 5.8 service file's `ReadWritePaths`. Spec's "git push-back: SSH deploy key for `clauding-lab/the-brief` with `contents: write`" — assumed pre-existing; if not, add it to 5.1 preflight as an extra check.
- **Placeholder scan.** No "TBD" / "implement later" / "similar to Task N" — every code block is complete. The only narrative section is the self-review itself.
- **Type consistency.** `RunResult` fields used in tests match the dataclass in `brief/pipeline.py:491` (sections, html, claude_outputs, call_reports, map_coords, todays_call, read_order, email_text). `call_reports` entries add new keys (`cost_usd`, `duration_s`, `tokens`) in Task 5.4 — `build_run_report` in Task 5.3 tolerates missing keys via `setdefault`, so the ordering (5.3 before 5.4) is safe. `MaxCallResult` extension in Task 5.4 is purely additive.
- **Known weaknesses.** (a) Cost numbers from the CLI are the CLI's `total_cost_usd` field — the Max CLI's own billing is Claude-Max-subscription-level; this field is an API-equivalent estimate useful for budget alerts but does not reflect actual subscription spend. (b) Task 6.4 email wiring is only unit-tested; an integration test against Brevo would need a staging account — deferred as out-of-scope. (c) Phase 6.5 `update.py` removal deliberately hard-codes the 2026-05-09 date; if cutover slips, update that date to `cutover-date + 14 days`.

---

## References

- Spec: `docs/superpowers/specs/2026-04-21-the-brief-redesign.md` §8 Phase 5, §8 Phase 6, §10, §11.
- Part 1 plan: `docs/superpowers/plans/2026-04-21-brief-redesign-part1-foundations-through-render.md` (on branch `docs/part1-plan`).
- EconDelta deploy pattern: `~/Projects/clauding-lab/econdelta/deploy/`.
- Session that authored this plan: `~/.claude/session-data/2026-04-25-part2-plan-authoring-session.tmp`.
