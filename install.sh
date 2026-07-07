#!/bin/bash
set -e

echo "Stay Compass OS installer starting..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/scripts/install-packages.sh"

echo "Stay Compass OS installer finished."