#!/bin/bash
set -e

echo "Installing Stay Compass boot assets..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SPLASH_SOURCE="$PROJECT_DIR/assets/splash.png"
INSTALL_DIR="/opt/stay-compass/assets"

if [ ! -f "$SPLASH_SOURCE" ]; then
    echo "ERROR: Missing splash image at $SPLASH_SOURCE"
    exit 1
fi

sudo mkdir -p "$INSTALL_DIR"
sudo cp "$SPLASH_SOURCE" "$INSTALL_DIR/splash.png"

echo "Boot assets installed to $INSTALL_DIR"
echo "Done."