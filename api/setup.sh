#!/bin/bash
# mybuilding API — Setup Hetzner (one-time)
# Usage : bash /root/mybuilding/api/setup.sh

set -e
echo "[mybuilding-api] Setup..."

cd /root/mybuilding/api

# Venv
python3 -m venv venv
venv/bin/pip install --quiet -r requirements.txt
echo "  ✓ venv + deps"

# Systemd
cp mybuilding-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable mybuilding-api
systemctl restart mybuilding-api
echo "  ✓ systemd service démarré"

systemctl status mybuilding-api --no-pager
echo "[mybuilding-api] Done. API sur http://127.0.0.1:3001"
