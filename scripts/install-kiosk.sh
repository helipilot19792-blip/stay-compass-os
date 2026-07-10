#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="/opt/stay-compass/backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

echo "Installing Stay Compass kiosk service..."

sudo mkdir -p /opt/stay-compass
sudo mkdir -p /opt/stay-compass/device
sudo mkdir -p "$BACKUP_DIR"

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

if id compass >/dev/null 2>&1; then
    sudo chown -R compass:compass /opt/stay-compass/device
fi

sudo mkdir -p /opt/stay-compass/browser-extension/admin-hotspot
sudo cp "$PROJECT_DIR/browser-extension/admin-hotspot/background.js" /opt/stay-compass/browser-extension/admin-hotspot/background.js
sudo cp "$PROJECT_DIR/browser-extension/admin-hotspot/content.js" /opt/stay-compass/browser-extension/admin-hotspot/content.js
sudo python3 - "$PROJECT_DIR/browser-extension/admin-hotspot/manifest.template.json" "/opt/stay-compass/browser-extension/admin-hotspot/manifest.json" "/opt/stay-compass/device/config.json" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

template_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])
config_path = Path(sys.argv[3])

manifest = json.loads(template_path.read_text(encoding="utf-8"))
config = json.loads(config_path.read_text(encoding="utf-8"))
pwa_url = config.get("pwa_url", "").strip()
parsed = urlparse(pwa_url)

if not parsed.scheme or not parsed.netloc:
    raise SystemExit(f"Invalid pwa_url for admin hotspot extension: {pwa_url!r}")

pwa_match = f"{parsed.scheme}://{parsed.netloc}/*"

manifest["host_permissions"] = [
    pwa_match if entry == "__PWA_MATCH__" else entry
    for entry in manifest["host_permissions"]
]
manifest["content_scripts"][0]["matches"] = [
    pwa_match if entry == "__PWA_MATCH__" else entry
    for entry in manifest["content_scripts"][0]["matches"]
]

target_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
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

AUTLOGIN_DIR="/etc/systemd/system/getty@tty1.service.d"
AUTLOGIN_CONF="$AUTLOGIN_DIR/stay-compass-autologin.conf"
sudo mkdir -p "$AUTLOGIN_DIR"
if [ -f "$AUTLOGIN_CONF" ]; then
    sudo cp "$AUTLOGIN_CONF" "$BACKUP_DIR/getty-tty1-autologin.$TIMESTAMP.bak"
fi
sudo tee "$AUTLOGIN_CONF" >/dev/null <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin compass --noclear %I $TERM
EOF

COMPASS_HOME="$(getent passwd compass | cut -d: -f6)"
if [ -z "$COMPASS_HOME" ]; then
    echo "ERROR: Unable to determine compass home directory."
    exit 1
fi

COMPASS_BASH_PROFILE="$COMPASS_HOME/.bash_profile"
if sudo test -f "$COMPASS_BASH_PROFILE"; then
    sudo cp "$COMPASS_BASH_PROFILE" "$BACKUP_DIR/compass.bash_profile.$TIMESTAMP.bak"
fi

sudo python3 - "$COMPASS_BASH_PROFILE" <<'PY'
import sys
from pathlib import Path

profile_path = Path(sys.argv[1])
start_marker = "# >>> stay-compass kiosk >>>"
end_marker = "# <<< stay-compass kiosk <<<"
managed_block = """# >>> stay-compass kiosk >>>
if [ -z "${DISPLAY:-}" ] && [ "$(tty)" = "/dev/tty1" ]; then
    exec startx /opt/stay-compass/start-kiosk.sh -- :0 -nocursor
fi
# <<< stay-compass kiosk <<<"""

existing = ""
if profile_path.exists():
    existing = profile_path.read_text(encoding="utf-8")

if start_marker in existing and end_marker in existing:
    before, remainder = existing.split(start_marker, 1)
    _, after = remainder.split(end_marker, 1)
    updated = before.rstrip()
    if updated:
        updated += "\n\n"
    updated += managed_block
    after = after.lstrip("\n")
    if after:
        updated += "\n\n" + after.rstrip()
else:
    updated = existing.rstrip()
    if updated:
        updated += "\n\n"
    updated += managed_block

updated = updated.rstrip() + "\n"
profile_path.write_text(updated, encoding="utf-8")
PY
sudo chown compass:compass "$COMPASS_BASH_PROFILE"
sudo chmod 644 "$COMPASS_BASH_PROFILE"

sudo systemctl daemon-reload
sudo systemctl unmask getty@tty1.service >/dev/null 2>&1 || true
sudo systemctl enable getty@tty1.service
sudo systemctl disable stay-compass-kiosk.service >/dev/null 2>&1 || true

echo "Kiosk service installed."
