# tests/test_cli.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from brief import cli


@pytest.fixture(autouse=True)
def _isolated_publication_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("BRIEF_DRY_RUN", raising=False)


def test_cli_rejects_unknown_subcommand():
    with pytest.raises(SystemExit) as ei:
        cli.main(["sneeze"])
    assert ei.value.code != 0


def test_cli_run_without_publish_returns_1():
    """Running without --publish returns exit code 1 (V5 HTML path is gone)."""
    rc = cli.main(["run"])
    assert rc == 1


def test_cli_default_today_uses_bdt_not_system_date():
    """A manual re-fire on the UTC Hetzner box between 00:00-06:00 BDT must
    resolve `today` to the BDT date, not the earlier UTC system date — the
    pipeline's own default (PipelineConfig.today) already does this via
    now_bdt().date(); the CLI must match it instead of using date.today()."""
    from datetime import date as _date, datetime as _datetime, timedelta as _timedelta, timezone as _timezone

    bdt_now = _datetime(2026, 8, 5, 2, 30, tzinfo=_timezone(_timedelta(hours=6)))  # 08-05 BDT
    system_utc_today = _date(2026, 8, 4)  # UTC box clock still reads 08-04

    with patch("brief.cli.date") as mock_date, \
         patch("brief.cli.now_bdt", return_value=bdt_now), \
         patch("brief.cli._run_v6_publish", return_value=3) as mock_run:
        mock_date.today.return_value = system_utc_today
        mock_date.fromisoformat = _date.fromisoformat  # keep real parsing for --today
        rc = cli.main(["run", "--publish", "--dry-run", "--no-notify"])

    assert rc == 3
    resolved_today = mock_run.call_args.args[1]  # `today` positional passed to _run_v6_publish
    assert resolved_today == _date(2026, 8, 5), (
        f"expected the BDT date 2026-08-05, got {resolved_today} "
        "(CLI used the box's system date instead of now_bdt())"
    )


def test_cli_today_override_still_wins_over_bdt_clock():
    """--today explicitly passed on the command line must still override the
    now_bdt() default, unchanged by this fix."""
    from datetime import date as _date, datetime as _datetime, timedelta as _timedelta, timezone as _timezone

    bdt_now = _datetime(2026, 8, 5, 2, 30, tzinfo=_timezone(_timedelta(hours=6)))

    with patch("brief.cli.now_bdt", return_value=bdt_now), \
         patch("brief.cli._run_v6_publish", return_value=3) as mock_run:
        rc = cli.main(["run", "--publish", "--dry-run", "--no-notify", "--today=2026-01-01"])

    assert rc == 3
    resolved_today = mock_run.call_args.args[1]
    assert resolved_today == _date(2026, 1, 1)


def test_cli_run_help_shows_publish_flag():
    """--help for the run subcommand must mention --publish."""
    with pytest.raises(SystemExit) as ei:
        cli.main(["run", "--help"])
    # SystemExit(0) is the normal exit from --help
    assert ei.value.code == 0


def test_write_fixture_without_dry_run_exits_with_error(capsys):
    """--write-fixture without --dry-run must exit 1 and print a clear error."""
    args = ["run", "--publish", "--write-fixture=/tmp/x.json"]  # NO --dry-run
    exit_code = cli.main(args)
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "--write-fixture requires --dry-run" in err


def test_write_fixture_creates_valid_json_on_dry_run(tmp_path: Path):
    """--write-fixture writes a BriefPayload JSON to disk when --dry-run is set.

    Verifies:
    - Exit code is 3 (dry-run-ok)
    - The fixture file is created at the requested path
    - The file contains valid JSON with top-level 'brief' and 'sections' keys

    TDD RED: Before adding --write-fixture to the argparser, cli.main raises
    SystemExit(2) (argparse unrecognised-argument) and the assertions never run.
    """
    fixture_path = tmp_path / "fixture.json"

    # Minimal BriefPayloadV6-shaped dict that the pipeline produces after a
    # dry run. Patch run_publish so no Anthropic API / Supabase calls happen.
    _minimal_payload = {
        "brief": {
            "issue_no": 99,
            "volume": 1,
            "brief_date": "2026-05-28",
            "lens": "neutral",
            "frame": "steady-state",
            "todays_call": "Test call.",
            "status": "published",
        },
        "sections": [
            {
                "slug": "banking",
                "ord": 4,
                "title": "Banking",
                "group_key": "banking",
                "weight": 1,
                "metrics": [],
                "news": [],
                "series": [],
                "notes": [],
            }
        ],
    }

    with patch("brief.cli._run_v6_publish") as mock_cli_run:

        # _run_v6_publish is what cli.main actually calls. In the implemented
        # version it receives write_fixture_path and writes the file. Until the
        # --write-fixture flag exists, argparse raises SystemExit(2) before
        # _run_v6_publish is ever reached.
        def _fake_cli_run(cfg, today, dry_run, notify_enabled, write_fixture_path=None,
                          preview_notify_enabled=False):
            # Simulate the implemented behaviour: write fixture + return 3.
            if write_fixture_path and dry_run:
                import json as _json
                with open(write_fixture_path, "w") as fh:
                    _json.dump(_minimal_payload, fh, indent=2)
            return 3

        mock_cli_run.side_effect = _fake_cli_run

        rc = cli.main([
            "run", "--publish", "--dry-run", "--no-notify",
            f"--write-fixture={fixture_path}",
        ])

    assert rc == 3, f"Expected exit code 3 (dry-run-ok), got {rc}"
    assert fixture_path.exists(), "--write-fixture path was not created"

    content = json.loads(fixture_path.read_text())
    assert "brief" in content, "Fixture JSON missing 'brief' key"
    assert "sections" in content, "Fixture JSON missing 'sections' key"


# ── Item 5d — notifier fail-loud ─────────────────────────────────────────────


def _run_publish_with_notify(notify_result=None, notify_raises=None):
    """Drive cli._run_v6_publish through a successful publish with a mocked
    notifier, returning (exit_code, mock_alert)."""
    from datetime import date as _date

    from brief.pipeline import PipelineConfig

    cfg = PipelineConfig(today=_date(2026, 7, 9), enable_headlines=False)

    with patch("brief.v6_publisher.fetch_same_day_briefs", return_value=[]), \
         patch("brief.v6_publisher.fetch_max_issue_no", return_value=235), \
         patch("brief.cli.gather", return_value=[]), \
         patch("brief.pipeline_v6.run_publish", return_value="brief-id-1"), \
         patch("brief.notifier.notify") as mock_notify, \
         patch("brief.alerts.send_discord_alert") as mock_alert:
        if notify_raises is not None:
            mock_notify.side_effect = notify_raises
        else:
            mock_notify.return_value = notify_result
        rc = cli._run_v6_publish(
            cfg, _date(2026, 7, 9), dry_run=False, notify_enabled=True,
        )
    return rc, mock_alert


def test_notifier_zero_sent_with_audience_alerts_but_exit_0(caplog):
    """sent=0 with attempted>0 = total delivery failure: Discord alert + error log,
    but exit stays 0 (the published brief is canonical; email is the amplifier)."""
    from brief.notifier import NotifyResult

    result = NotifyResult(sent_count=0, skipped_count=0, message_id=None,
                          error="brevo_http_500", attempted_count=8)
    with caplog.at_level("ERROR", logger="brief.cli"):
        rc, mock_alert = _run_publish_with_notify(notify_result=result)

    assert rc == 0
    mock_alert.assert_called_once()
    msg = mock_alert.call_args.args[0]
    assert "delivered to NOBODY" in msg
    assert "attempted=8" in msg
    assert any("DELIVERED TO NOBODY" in r.message for r in caplog.records)


def test_notifier_success_does_not_alert():
    from brief.notifier import NotifyResult

    result = NotifyResult(sent_count=8, skipped_count=0, message_id="m-1",
                          error=None, attempted_count=8)
    rc, mock_alert = _run_publish_with_notify(notify_result=result)
    assert rc == 0
    mock_alert.assert_not_called()


def test_notifier_empty_subscriber_list_is_not_an_incident():
    """sent=0 because the list is genuinely empty ("no_subscribers") is a fine
    state — no alert."""
    from brief.notifier import NotifyResult

    result = NotifyResult(sent_count=0, skipped_count=0, message_id=None,
                          error="no_subscribers", attempted_count=0)
    rc, mock_alert = _run_publish_with_notify(notify_result=result)
    assert rc == 0
    mock_alert.assert_not_called()


def test_notifier_prefetch_failure_alerts():
    """sent=0 with an error BEFORE the audience could be counted (fetch/auth
    failures, attempted=0) must still alert."""
    from brief.notifier import NotifyResult

    result = NotifyResult(sent_count=0, skipped_count=0, message_id=None,
                          error="fetch_subs: boom", attempted_count=0)
    rc, mock_alert = _run_publish_with_notify(notify_result=result)
    assert rc == 0
    mock_alert.assert_called_once()


def test_notifier_crash_alerts_and_exit_0():
    rc, mock_alert = _run_publish_with_notify(notify_raises=RuntimeError("kaboom"))
    assert rc == 0
    mock_alert.assert_called_once()
    assert "CRASHED" in mock_alert.call_args.args[0]


@pytest.mark.parametrize("raw", ["1", "true", "yes", "on", " TRUE "])
def test_environment_pause_applies_to_service_arguments(raw, monkeypatch):
    monkeypatch.setenv("BRIEF_DRY_RUN", raw)
    with patch("brief.cli._run_v6_publish", return_value=3) as run:
        assert cli.main(["run", "--publish"]) == 3
    assert run.call_args.kwargs["dry_run"] is True
    assert run.call_args.kwargs["notify_enabled"] is False


def test_pause_precedes_fixture_validation_and_disables_preview(monkeypatch):
    monkeypatch.setenv("BRIEF_DRY_RUN", "1")
    with patch("brief.cli._run_v6_publish", return_value=3) as run:
        assert cli.main(["run", "--publish", "--write-fixture=x.json", "--preview-notify"]) == 3
    assert run.call_args.kwargs["preview_notify_enabled"] is False


@pytest.mark.parametrize("raw", ["tru", "2", "disabled"])
def test_invalid_pause_fails_before_any_work(raw, monkeypatch, capsys):
    monkeypatch.setenv("BRIEF_DRY_RUN", raw)
    with patch("brief.cli._run_v6_publish") as run:
        assert cli.main(["run", "--publish", "--write-fixture=x.json"]) == 1
    run.assert_not_called()
    assert "Invalid BRIEF_DRY_RUN" in capsys.readouterr().err


def test_live_today_override_cannot_backdate():
    with patch("brief.cli._run_v6_publish") as run:
        assert cli.main(["run", "--publish", "--today=2026-01-01"]) == 1
    run.assert_not_called()


def test_live_cli_two_processes_lock_through_delivery(tmp_path):
    """A competing CLI must stop before identity/gather/model/write/send work."""
    import os
    import subprocess
    import sys
    import time

    script = r'''
import sys, time
from pathlib import Path
from unittest.mock import patch
from brief import cli
from brief.notifier import NotifyResult
root, role = Path(sys.argv[1]), sys.argv[2]
def mark(stage):
    with (root / (role + '.events')).open('a') as f:
        f.write(stage + '\n')
def same_day(*args):
    mark('identity')
    return []
def gather(cfg):
    mark('gather')
    return []
def publish(*args, **kwargs):
    mark('model'); mark('write')
    return 'id'
def notify(*args):
    mark('send')
    if role == 'owner':
        (root / 'ready').touch()
        deadline = time.monotonic() + 10
        while not (root / 'release').exists():
            if time.monotonic() > deadline:
                raise RuntimeError('test synchronization timed out')
            time.sleep(.02)
    return NotifyResult(sent_count=1, skipped_count=0, message_id='m', error=None, attempted_count=1)
with patch('brief.cli.gather', side_effect=gather), \
     patch('brief.headlines.scrape_all', return_value=[]), \
     patch('brief.v6_publisher.fetch_same_day_briefs', side_effect=same_day, create=True), \
     patch('brief.v6_publisher.fetch_max_issue_no', return_value=235), \
     patch('brief.pipeline_v6.run_publish', side_effect=publish), \
     patch('brief.notifier.notify', side_effect=notify):
    sys.exit(cli.main(['run', '--publish']))
'''
    env = {**os.environ, "HOME": str(tmp_path), "BRIEF_DRY_RUN": "0",
           "PYTHONPATH": str(Path.cwd())}
    owner = subprocess.Popen([sys.executable, "-c", script, str(tmp_path), "owner"],
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while not (tmp_path / "ready").exists():
            assert owner.poll() is None, owner.communicate()
            assert time.monotonic() < deadline, "owner did not reach delivery"
            time.sleep(.02)
        loser = subprocess.run([sys.executable, "-c", script, str(tmp_path), "loser"],
                               env=env, cwd=tmp_path, capture_output=True, timeout=5)
        assert loser.returncode == 4, loser.stderr.decode()
        assert not (tmp_path / "loser.events").exists()
        (tmp_path / "release").touch()
        assert owner.wait(timeout=5) == 0
        assert (tmp_path / "owner.events").read_text().splitlines() == [
            "identity", "gather", "model", "write", "send",
        ]
        lock = tmp_path / ".local/state/the-brief/publication.lock"
        assert lock.is_file(), "release must never unlink the shared lock inode"
        inode = lock.stat().st_ino
        retry = subprocess.run([sys.executable, "-c", script, str(tmp_path), "retry"],
                               env=env, cwd=tmp_path, capture_output=True, timeout=5)
        assert retry.returncode == 0, retry.stderr.decode()
        assert lock.stat().st_ino == inode
    finally:
        (tmp_path / "release").touch()
        if owner.poll() is None:
            owner.kill()
        owner.communicate(timeout=5)


@pytest.mark.parametrize("raw", [None, "", "0", "false", "no", "off", " OFF "])
def test_false_environment_switch_cannot_override_explicit_dry_run(raw, monkeypatch):
    if raw is not None:
        monkeypatch.setenv("BRIEF_DRY_RUN", raw)
    with patch("brief.cli._run_v6_publish", return_value=3) as run:
        assert cli.main(["run", "--publish", "--dry-run"]) == 3
    assert run.call_args.kwargs["dry_run"] is True
    assert run.call_args.kwargs["notify_enabled"] is False


@pytest.mark.parametrize("status,should_send", [("published", False), ("draft", False)])
def test_same_day_replacement_reuses_identity_and_never_automatically_resends(status, should_send):
    from datetime import date
    from brief.notifier import NotifyResult
    from brief.pipeline import PipelineConfig
    from brief.publication_identity import PublishIdentity

    today = date(2026, 9, 25)
    with patch("brief.v6_publisher.fetch_same_day_briefs", return_value=[
        {"issue_no": 235, "brief_date": today.isoformat(), "status": status},
    ]) as read, \
         patch("brief.v6_publisher.fetch_max_issue_no", return_value=235) as maximum, \
         patch("brief.cli.gather", return_value=[]), \
         patch("brief.pipeline_v6.run_publish", return_value="id") as run, \
         patch("brief.notifier.notify", return_value=NotifyResult(
             sent_count=1, skipped_count=0, message_id="m", error=None, attempted_count=1,
         )) as notify:
        assert cli._run_v6_publish(PipelineConfig(today=today, enable_headlines=False), today,
                                   dry_run=False, notify_enabled=True) == 0
    read.assert_called_once_with(today)
    maximum.assert_called_once()
    assert run.call_args.kwargs["expected_identity"] == PublishIdentity(235, today)
    assert notify.called is should_send


def test_same_day_conflict_holds_before_gather_or_model():
    from datetime import date
    from brief.pipeline import PipelineConfig

    today = date(2026, 9, 25)
    rows = [{"issue_no": n, "brief_date": today.isoformat()} for n in [234, 235]]
    with patch("brief.v6_publisher.fetch_same_day_briefs", return_value=rows), \
         patch("brief.v6_publisher.fetch_max_issue_no", return_value=235), \
         patch("brief.cli.gather") as gather, \
         patch("brief.pipeline_v6.run_publish") as run, \
         patch("brief.notifier.notify") as notify:
        assert cli._run_v6_publish(PipelineConfig(today=today), today, False, True) == 4
    gather.assert_not_called()
    run.assert_not_called()
    notify.assert_not_called()


@pytest.mark.parametrize("preview", [False, True])
def test_paused_real_service_flow_has_zero_writes_or_notifications(monkeypatch, tmp_path, preview):
    import shlex
    from datetime import datetime
    from brief import pipeline_v6

    monkeypatch.setenv("BRIEF_DRY_RUN", "1")
    fixture = tmp_path / "paused.json"
    service = Path("deploy/brief.service").read_text()
    command = next(line.split("=", 1)[1] for line in service.splitlines() if line.startswith("ExecStart="))
    args = shlex.split(command)[3:]  # actual python -m brief.cli service arguments
    if preview:
        args += [f"--write-fixture={fixture}", "--preview-notify"]
    payload = {
        "brief": {"issue_no": 236, "volume": 1, "brief_date": "2026-09-24",
                  "todays_call": "Inflation reached 99.99%.", "status": "published"},
        "sections": [{"slug": "bb", "ord": 3, "title": "Bangladesh Bank",
                      "group_key": "banking", "weight": 1}],
    }
    methods = []
    def request(method, path, *args, **kwargs):
        methods.append(method)
        assert method == "GET", "pause must never write to Supabase"
        return [{"issue_no": 235}] if "order=issue_no.desc" in path else []

    with patch("brief.cli.now_bdt", return_value=datetime(2026, 9, 24, 8)), \
         patch("brief.cli.gather", return_value=[]), \
         patch("brief.headlines.scrape_all", return_value=[]), \
         patch("brief.v6_publisher._request", side_effect=request), \
         patch("brief.pipeline_v6._resolve_supabase_config", return_value=None), \
         patch("brief.pipeline_v6._call_with_retries", side_effect=[
             payload, {"verdict": "pass", "issues": [], "revised_brief": None},
         ]), \
         patch("brief.pipeline_v6._alert", wraps=pipeline_v6._alert) as warning, \
         patch("brief.alerts.send_discord_alert") as alert, \
         patch("brief.notifier.notify") as notify, \
         patch("brief.preview_notify.notify_preview") as notify_preview:
        assert cli.main(args) == 3
    assert methods and set(methods) == {"GET"}
    warning.assert_called()  # real degraded-data/prose warning traversed the pause guard
    alert.assert_not_called()
    notify.assert_not_called()
    notify_preview.assert_not_called()
    assert fixture.exists() is preview


def test_explicit_dry_run_preview_still_sends_when_not_paused(tmp_path):
    with patch("brief.cli._run_v6_publish", return_value=3) as run:
        assert cli.main(["run", "--publish", "--dry-run", "--preview-notify",
                         f"--write-fixture={tmp_path / 'preview.json'}"]) == 3
    assert run.call_args.kwargs["preview_notify_enabled"] is True


def test_failed_published_replacement_leaves_draft_and_retry_still_never_sends():
    """A draft retry is ambiguous: the original published version may be emailed."""
    from datetime import date
    from brief.pipeline import PipelineConfig
    from brief.pipeline_v6 import V6PublishError

    today = date(2026, 9, 25)
    row = {"issue_no": 235, "brief_date": today.isoformat(), "status": "published"}
    attempts = 0
    identities = []
    def publish(*args, expected_identity, **kwargs):
        nonlocal attempts
        attempts += 1
        identities.append(expected_identity)
        if attempts == 1:
            row["status"] = "draft"  # draft inserted, then a child POST failed
            raise V6PublishError("child insert failed")
        row["status"] = "published"
        return "replacement-id"

    cfg = PipelineConfig(today=today, enable_headlines=False)
    with patch("brief.v6_publisher.fetch_same_day_briefs", side_effect=lambda _: [dict(row)]), \
         patch("brief.v6_publisher.fetch_max_issue_no", return_value=235), \
         patch("brief.cli.gather", return_value=[]), \
         patch("brief.pipeline_v6.run_publish", side_effect=publish), \
         patch("brief.notifier.notify") as notify:
        assert cli._run_v6_publish(cfg, today, False, True) == 4
        assert row["status"] == "draft"
        assert cli._run_v6_publish(cfg, today, False, True) == 0
    assert identities[0] == identities[1]
    assert identities[1].issue_no == 235
    notify.assert_not_called()


def test_notifier_partial_delivery_alerts_without_republishing(caplog):
    from brief.notifier import NotifyResult

    result = NotifyResult(sent_count=2, skipped_count=0, message_id="accepted",
                          error="HTTP 503", attempted_count=3)
    with caplog.at_level("ERROR", logger="brief.cli"):
        rc, alert = _run_publish_with_notify(notify_result=result)
    assert rc == 0
    alert.assert_called_once()
    assert "PARTIAL DELIVERY" in alert.call_args.args[0]
    assert "sent=2" in alert.call_args.args[0]
    assert "attempted=3" in alert.call_args.args[0]
    assert "failed=1" in alert.call_args.args[0]
    assert any("PARTIAL DELIVERY" in record.message for record in caplog.records)
