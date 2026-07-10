#!/bin/bash
set -euo pipefail

echo "Configuring silent boot..."

BOOT_DIR="/boot/firmware"

if [ ! -d "$BOOT_DIR" ]; then
    BOOT_DIR="/boot"
fi

CONFIG_TXT="$BOOT_DIR/config.txt"
CMDLINE_TXT="$BOOT_DIR/cmdline.txt"
BACKUP_DIR="/opt/stay-compass/backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
CONFIG_BACKUP="$BACKUP_DIR/config.txt.$TIMESTAMP.bak"
CMDLINE_BACKUP="$BACKUP_DIR/cmdline.txt.$TIMESTAMP.bak"
ROLLBACK_SCRIPT="$BACKUP_DIR/rollback-boot-config-$TIMESTAMP.sh"

if [ ! -f "$CONFIG_TXT" ] || [ ! -f "$CMDLINE_TXT" ]; then
    echo "ERROR: Unable to locate Raspberry Pi boot configuration files."
    exit 1
fi

sudo mkdir -p "$BACKUP_DIR"
sudo cp "$CONFIG_TXT" "$CONFIG_BACKUP"
sudo cp "$CMDLINE_TXT" "$CMDLINE_BACKUP"
sudo cp "$CONFIG_BACKUP" "$BACKUP_DIR/config.txt.bak"
sudo cp "$CMDLINE_BACKUP" "$BACKUP_DIR/cmdline.txt.bak"

cleanup() {
    rm -f "$TEMP_CONFIG" "$TEMP_CMDLINE"
}

rollback_on_error() {
    echo "Boot configuration update failed. Restoring previous files..."
    sudo cp "$CONFIG_BACKUP" "$CONFIG_TXT"
    sudo cp "$CMDLINE_BACKUP" "$CMDLINE_TXT"
}

TEMP_CONFIG="$(mktemp)"
TEMP_CMDLINE="$(mktemp)"

trap cleanup EXIT
trap 'rollback_on_error' ERR

python3 - "$CONFIG_TXT" "$CMDLINE_TXT" "$TEMP_CONFIG" "$TEMP_CMDLINE" <<'PY'
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
cmdline_path = Path(sys.argv[2])
temp_config_path = Path(sys.argv[3])
temp_cmdline_path = Path(sys.argv[4])

config_lines = config_path.read_text(encoding="utf-8").splitlines()
config_updates = {
    "disable_splash": "1",
}
config_removals = {
    "auto_initramfs",
}

seen = set()
updated_lines = []

for line in config_lines:
    stripped = line.strip()

    if not stripped or stripped.startswith("#") or "=" not in stripped:
        updated_lines.append(line)
        continue

    key, _, value = stripped.partition("=")

    if key in config_removals:
        continue

    if key in config_updates:
        updated_lines.append(f"{key}={config_updates[key]}")
        seen.add(key)
        continue

    updated_lines.append(line)

for key, value in config_updates.items():
    if key not in seen:
        updated_lines.append(f"{key}={value}")

original_cmdline = cmdline_path.read_text(encoding="utf-8")
cmdline = original_cmdline.strip()
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

new_cmdline_parts = filtered_parts + required_parts
new_cmdline = " ".join(new_cmdline_parts)

if not new_cmdline or "\n" in new_cmdline or "\r" in new_cmdline:
    raise SystemExit("cmdline.txt must contain exactly one non-empty line.")

required_existing_prefixes = [
    "root=",
    "rootfstype=",
]
for prefix in required_existing_prefixes:
    if any(part.startswith(prefix) for part in parts) and not any(
        part.startswith(prefix) for part in new_cmdline_parts
    ):
        raise SystemExit(f"Refusing to write cmdline.txt without required parameter: {prefix}")

for required_flag in ["rootwait", "fsck.repair=yes"]:
    if required_flag in parts and required_flag not in new_cmdline_parts:
        raise SystemExit(f"Refusing to write cmdline.txt without required parameter: {required_flag}")

if not any(line.strip() == "disable_splash=1" for line in updated_lines):
    raise SystemExit("config.txt validation failed: disable_splash=1 missing.")

if any(line.strip().startswith("auto_initramfs=") for line in updated_lines):
    raise SystemExit("config.txt validation failed: legacy auto_initramfs setting still present.")

temp_config_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
temp_cmdline_path.write_text(new_cmdline + "\n", encoding="utf-8")
PY

sudo install -m 644 "$TEMP_CONFIG" "$CONFIG_TXT"
sudo install -m 644 "$TEMP_CMDLINE" "$CMDLINE_TXT"

sudo tee "$ROLLBACK_SCRIPT" >/dev/null <<EOF
#!/bin/bash
set -euo pipefail
sudo cp "$CONFIG_BACKUP" "$CONFIG_TXT"
sudo cp "$CMDLINE_BACKUP" "$CMDLINE_TXT"
echo "Restored boot configuration from:"
echo "  $CONFIG_BACKUP"
echo "  $CMDLINE_BACKUP"
EOF
sudo chmod +x "$ROLLBACK_SCRIPT"

sudo systemctl unmask getty@tty1.service >/dev/null 2>&1 || true

trap - ERR
echo "Silent boot configuration applied."
echo "Rollback script saved to: $ROLLBACK_SCRIPT"
