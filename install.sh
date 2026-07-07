#!/bin/bash
set -e

echo "Stay Compass OS installer starting..."

echo "Backing up current kiosk files..."
mkdir -p backups

sudo cp /opt/stay-compass/start-kiosk.sh backups/start-kiosk.sh 2>/dev/null || true
sudo cp /home/compass/.bash_profile backups/compass-bash-profile 2>/dev/null || true

echo "Backup complete."
echo "Installer finished."
