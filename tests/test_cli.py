# tests/test_cli.py
from __future__ import annotations

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
