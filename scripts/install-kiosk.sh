#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Installing Stay Compass kiosk service..."

sudo mkdir -p /opt/stay-compass
sudo mkdir -p /opt/stay-compass/device

sudo cp "$PROJECT_DIR/launcher/start-kiosk.sh" /opt/stay-compass/start-kiosk.sh
sudo chmod +x /opt/stay-compass/start-kiosk.sh

sudo cp "$PROJECT_DIR/scripts/run-update.sh" /opt/stay-compass/run-update.sh
sudo chmod +x /opt/stay-compass/run-update.sh

sudo cp "$PROJECT_DIR/device/stay-compass-device.py" /opt/stay-compass/device/stay-compass-device.py
sudo chmod +x /opt/stay-compass/device/stay-compass-device.py

sudo python3 - "$PROJECT_DIR/device/config.json" "/opt/stay-compass/device/config.json" "$PROJECT_DIR" <<'PY'
import json
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])
repo_dir = sys.argv[3]

source_config = json.loads(source_path.read_text(encoding="utf-8"))
installed_config = {}

if target_path.exists():
    installed_config = json.loads(target_path.read_text(encoding="utf-8"))

merged_config = {**source_config, **installed_config}
merged_config["update_repo_dir"] = repo_dir
# Device service runs as compass, so the repo path must be readable.
target_path.write_text(
    json.dumps(merged_config, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
sudo chmod o+x "$(dirname "$PROJECT_DIR")"
sudo chmod -R o+rX "$PROJECT_DIR/.git"
if id compass >/dev/null 2>&1; then
    sudo usermod -aG netdev compass
fi

sudo tee /etc/sudoers.d/stay-compass-update >/dev/null <<'EOF'
compass ALL=(root) NOPASSWD: /opt/stay-compass/run-update.sh check, /opt/stay-compass/run-update.sh apply
EOF
sudo chmod 440 /etc/sudoers.d/stay-compass-update

sudo cp "$PROJECT_DIR/services/stay-compass-kiosk.service" /etc/systemd/system/stay-compass-kiosk.service

sudo systemctl daemon-reload
sudo systemctl enable stay-compass-kiosk.service

echo "Kiosk service installed."
