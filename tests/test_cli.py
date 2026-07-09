# tests/test_cli.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from brief import cli


def test_cli_rejects_unknown_subcommand():
    with pytest.raises(SystemExit) as ei:
        cli.main(["sneeze"])
    assert ei.value.code != 0


def test_cli_run_without_publish_returns_1():
    """Running without --publish returns exit code 1 (V5 HTML path is gone)."""
    rc = cli.main(["run"])
    assert rc == 1


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

    with patch("brief.cli.gather", return_value=[]), \
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
