#!/bin/bash
set -e

echo "Installing Stay Compass boot assets..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SPLASH_SOURCE="$PROJECT_DIR/assets/splash.png"
INSTALL_DIR="/opt/stay-compass/assets"
BIN_DIR="/opt/stay-compass/bin"
THEME_SOURCE_DIR="$PROJECT_DIR/plymouth/stay-compass"
THEME_INSTALL_DIR="/usr/share/plymouth/themes/stay-compass"

if [ ! -f "$SPLASH_SOURCE" ]; then
    echo "ERROR: Missing splash image at $SPLASH_SOURCE"
    exit 1
fi

if [ ! -d "$THEME_SOURCE_DIR" ]; then
    echo "ERROR: Missing Plymouth theme at $THEME_SOURCE_DIR"
    exit 1
fi

sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$BIN_DIR"
sudo mkdir -p "$THEME_INSTALL_DIR"
sudo cp "$SPLASH_SOURCE" "$INSTALL_DIR/splash.png"
sudo cp "$SPLASH_SOURCE" "$THEME_INSTALL_DIR/splash.png"
sudo cp "$THEME_SOURCE_DIR/stay-compass.plymouth" "$THEME_INSTALL_DIR/stay-compass.plymouth"
sudo cp "$THEME_SOURCE_DIR/stay-compass.script" "$THEME_INSTALL_DIR/stay-compass.script"
sudo cp "$PROJECT_DIR/scripts/stay-compass-boot-report.py" "$BIN_DIR/stay-compass-boot-report.py"
sudo chmod +x "$BIN_DIR/stay-compass-boot-report.py"

sudo cp "$PROJECT_DIR/services/stay-compass-splash.service" /etc/systemd/system/stay-compass-splash.service
sudo cp "$PROJECT_DIR/services/stay-compass-boot-report.service" /etc/systemd/system/stay-compass-boot-report.service
sudo systemctl daemon-reload
sudo systemctl enable stay-compass-splash.service
sudo systemctl enable stay-compass-boot-report.service

echo "Boot assets installed to $INSTALL_DIR"
echo "Splash theme and services installed."
echo "Done."
