#!/bin/bash
set -e

echo "Installing Stay Compass boot splash..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SPLASH_SOURCE="$PROJECT_DIR/assets/splash.png"
SPLASH_TARGET="/usr/share/plymouth/themes/stay-compass/splash.png"

if [ ! -f "$SPLASH_SOURCE" ]; then
    echo "ERROR: Missing splash image at $SPLASH_SOURCE"
    exit 1
fi

sudo apt install -y plymouth plymouth-themes

sudo mkdir -p /usr/share/plymouth/themes/stay-compass

sudo cp "$SPLASH_SOURCE" "$SPLASH_TARGET"

echo "Splash image copied."
echo "Done."