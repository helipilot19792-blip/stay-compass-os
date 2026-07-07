#!/bin/bash
set -e

echo "Installing Stay Compass kiosk service..."

sudo mkdir -p /opt/stay-compass
sudo cp launcher/start-kiosk.sh /opt/stay-compass/start-kiosk.sh
sudo chmod +x /opt/stay-compass/start-kiosk.sh

sudo cp services/stay-compass-kiosk.service /etc/systemd/system/stay-compass-kiosk.service

sudo systemctl daemon-reload
sudo systemctl enable stay-compass-kiosk.service

echo "Kiosk service installed."