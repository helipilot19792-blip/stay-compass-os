#!/bin/bash
set -e

echo "Configuring silent boot..."

BOOT_DIR="/boot/firmware"

if [ ! -d "$BOOT_DIR" ]; then
    BOOT_DIR="/boot"
fi

CONFIG_TXT="$BOOT_DIR/config.txt"
CMDLINE_TXT="$BOOT_DIR/cmdline.txt"
BACKUP_DIR="/opt/stay-compass/backups"

if [ ! -f "$CONFIG_TXT" ] || [ ! -f "$CMDLINE_TXT" ]; then
    echo "ERROR: Unable to locate Raspberry Pi boot configuration files."
    exit 1
fi

sudo mkdir -p "$BACKUP_DIR"
sudo cp "$CONFIG_TXT" "$BACKUP_DIR/config.txt.bak"
sudo cp "$CMDLINE_TXT" "$BACKUP_DIR/cmdline.txt.bak"

sudo python3 - "$CONFIG_TXT" "$CMDLINE_TXT" <<'PY'
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
cmdline_path = Path(sys.argv[2])

config_lines = config_path.read_text(encoding="utf-8").splitlines()
config_updates = {
    "disable_splash": "1",
}

seen = set()
updated_lines = []

for line in config_lines:
    stripped = line.strip()

    if not stripped or stripped.startswith("#") or "=" not in stripped:
        updated_lines.append(line)
        continue

    key, _, value = stripped.partition("=")

    if key in config_updates:
        updated_lines.append(f"{key}={config_updates[key]}")
        seen.add(key)
        continue

    updated_lines.append(line)

for key, value in config_updates.items():
    if key not in seen:
        updated_lines.append(f"{key}={value}")

config_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

cmdline = cmdline_path.read_text(encoding="utf-8").strip()
parts = [part for part in cmdline.split() if part]

filtered_parts = []
for part in parts:
    if part == "quiet":
        continue
    if part == "splash":
        continue
    if part.startswith("console=tty1"):
        continue
    if part.startswith("plymouth.enable="):
        continue
    if part == "plymouth.ignore-serial-consoles":
        continue
    if part.startswith("logo."):
        continue
    if part.startswith("vt.global_cursor_default="):
        continue
    if part.startswith("loglevel="):
        continue
    if part.startswith("rd.udev.log_level="):
        continue
    if part.startswith("systemd.show_status="):
        continue
    if part.startswith("systemd.log_level="):
        continue
    if part.startswith("consoleblank="):
        continue
    filtered_parts.append(part)

required_parts = [
    "quiet",
    "loglevel=0",
    "logo.nologo",
    "vt.global_cursor_default=0",
    "consoleblank=0",
    "rd.udev.log_level=0",
    "systemd.show_status=false",
    "systemd.log_level=notice",
    "plymouth.enable=0",
]

cmdline_path.write_text(" ".join(filtered_parts + required_parts) + "\n", encoding="utf-8")
PY

sudo systemctl unmask getty@tty1.service >/dev/null 2>&1 || true

echo "Silent boot configuration applied."
