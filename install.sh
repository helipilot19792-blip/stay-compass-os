#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VERSION=$(cat "$SCRIPT_DIR/VERSION")

echo ""
echo "=================================="
echo " Stay Compass OS Installer"
echo " Version $VERSION"
echo "=================================="
echo ""

bash "$SCRIPT_DIR/scripts/install-packages.sh"
bash "$SCRIPT_DIR/scripts/install-splash.sh"
bash "$SCRIPT_DIR/scripts/install-kiosk.sh"

echo ""
echo "Stay Compass OS $VERSION installation complete."
echo ""