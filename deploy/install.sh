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
