"""The systemd failure alert must carry useful context without leaking secrets."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "brief_alert.sh"


def _run_alert(tmp_path: Path, unit: str, log: str) -> dict:
    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    (tools / "curl").write_text(
        '#!/bin/sh\nwhile [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "--data" ]; then printf "%s" "$2" > "$CAPTURE"; fi\n'
        '  shift\ndone\nprintf 204\n'
    )
    (tools / "journalctl").write_text('#!/bin/sh\nprintf "journal fallback\\n"\n')
    for name in ("curl", "journalctl"):
        (tools / name).chmod(0o755)
    script = tmp_path / "brief_alert.sh"
    script.write_text(SCRIPT.read_text().replace(
        "/home/adnan/the-brief/logs/brief-systemd.log", str(tmp_path / "brief-systemd.log")
    ))
    (tmp_path / "brief-systemd.log").write_text(log)
    env = dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}",
               DISCORD_ALERT_WEBHOOK_URL="https://discord.test/webhooks/secret-token",
               CAPTURE=str(tmp_path / "payload.json"))
    result = subprocess.run(["bash", str(script), unit], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    return json.loads((tmp_path / "payload.json").read_text())


def test_brief_failure_reads_application_exception_and_redacts(tmp_path: Path) -> None:
    log = ("old line\n" * 300 + "V6PublishError: hold\n"
           "Authorization: Bearer secret-authorization\n"
           "api-key: secret-api-key\n"
           "https://discord.com/api/webhooks/123/secret-token\n"
           "subscriber@example.com\n")
    content = _run_alert(tmp_path, "brief.service", log)["content"]
    assert "V6PublishError" in content
    for secret in ("secret-authorization", "secret-api-key", "secret-token",
                   "subscriber@example.com"):
        assert secret not in content
    assert len(content) <= 2000


def test_other_allowlisted_unit_uses_journal_and_unknown_unit_is_rejected(tmp_path: Path) -> None:
    assert "journal fallback" in _run_alert(tmp_path, "brief-export.service", "unused")["content"]
    assert "journal fallback" in _run_alert(tmp_path, "chess-prodigy-prune.service", "unused")["content"]
    assert "journal fallback" not in _run_alert(tmp_path, "--unit=ssh.service", "unused")["content"]
