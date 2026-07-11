#!/bin/bash
set -u

log() {
    echo "[stay-compass-tailscale] $1"
}

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    log "This installer must run as root."
    exit 1
fi

log "Checking Tailscale installation..."

if command -v tailscale >/dev/null 2>&1 && command -v tailscaled >/dev/null 2>&1; then
    log "Tailscale is already installed."
else
    log "Installing Tailscale using the official Linux installer..."
    if ! curl -fsSL https://tailscale.com/install.sh | sh; then
        log "Tailscale installation failed."
        exit 1
    fi
fi

mkdir -p /opt/stay-compass/bin
mkdir -p /var/lib/stay-compass

python3 - "/var/lib/stay-compass/device-id" <<'PY'
import os
import random
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
existing = path.read_text(encoding="utf-8").strip() if path.exists() else ""

if not re.fullmatch(r"SC-\d{6}", existing):
    existing = f"SC-{random.SystemRandom().randrange(0, 1_000_000):06d}"
    path.write_text(existing + "\n", encoding="utf-8")

os.chmod(path, 0o644)
PY

if command -v systemctl >/dev/null 2>&1; then
    log "Enabling tailscaled service..."
    if ! systemctl enable tailscaled >/dev/null 2>&1; then
        log "Unable to enable tailscaled."
        exit 1
    fi
    if ! systemctl start tailscaled >/dev/null 2>&1; then
        log "Unable to start tailscaled."
        exit 1
    fi

    if systemctl list-unit-files ssh.service >/dev/null 2>&1; then
        log "Ensuring OpenSSH is enabled for scadmin access..."
        systemctl enable ssh >/dev/null 2>&1 || true
        systemctl start ssh >/dev/null 2>&1 || true
    fi
fi

log "Tailscale support is ready."
