#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Installing Stay Compass kiosk service..."

sudo mkdir -p /opt/stay-compass
sudo mkdir -p /opt/stay-compass/device

sudo cp "$PROJECT_DIR/launcher/start-kiosk.sh" /opt/stay-compass/start-kiosk.sh
sudo chmod +x /opt/stay-compass/start-kiosk.sh

sudo cp "$PROJECT_DIR/device/stay-compass-device.py" /opt/stay-compass/device/stay-compass-device.py
sudo cp "$PROJECT_DIR/device/config.json" /opt/stay-compass/device/config.json
sudo chmod +x /opt/stay-compass/device/stay-compass-device.py

sudo cp "$PROJECT_DIR/services/stay-compass-kiosk.service" /etc/systemd/system/stay-compass-kiosk.service

sudo systemctl daemon-reload
sudo systemctl enable stay-compass-kiosk.service

echo "Kiosk service installed."
