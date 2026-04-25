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
