#!/bin/bash
set -e

echo "Installing Stay Compass kiosk service..."

sudo mkdir -p /opt/stay-compass
sudo mkdir -p /opt/stay-compass/device

sudo cp launcher/start-kiosk.sh /opt/stay-compass/start-kiosk.sh
sudo chmod +x /opt/stay-compass/start-kiosk.sh

sudo cp device/stay-compass-device.py /opt/stay-compass/device/stay-compass-device.py
sudo cp device/config.json /opt/stay-compass/device/config.json
sudo chmod +x /opt/stay-compass/device/stay-compass-device.py

sudo cp services/stay-compass-kiosk.service /etc/systemd/system/stay-compass-kiosk.service

sudo systemctl daemon-reload

echo "Kiosk service installed."