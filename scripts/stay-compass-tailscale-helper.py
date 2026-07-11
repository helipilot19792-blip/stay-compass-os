#!/usr/bin/env python3

import json
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path


TAILSCALE_BIN = "/usr/bin/tailscale"
SYSTEMCTL_BIN = "/usr/bin/systemctl"
DEVICE_ID_PATH = Path("/var/lib/stay-compass/device-id")
SSH_SERVICE_NAME = "ssh"
ALLOWED_OPERATIONS = {"status", "enroll", "down", "logout"}
AUTH_KEY_REDACTION_RE = re.compile(r"tskey-[A-Za-z0-9_-]+")


def redact_sensitive_text(text):
    if not text:
        return ""
    sanitized = str(text).replace("\r", " ").replace("\n", " ").strip()
    sanitized = AUTH_KEY_REDACTION_RE.sub("<redacted>", sanitized)
    return " ".join(sanitized.split())


def read_command_output(result):
    return (result.stdout or result.stderr or "").strip()


def run_command(command, *, input_text=None, timeout=60):
    return subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
    )


def command_exists(path):
    return Path(path).exists()


def service_is_active(service_name):
    result = run_command([SYSTEMCTL_BIN, "is-active", service_name], timeout=15)
    return result.returncode == 0 and result.stdout.strip() == "active"


def ensure_service_running(service_name):
    enable_result = run_command([SYSTEMCTL_BIN, "enable", service_name], timeout=30)
    if enable_result.returncode != 0:
        raise RuntimeError(
            f"Unable to enable {service_name}: {redact_sensitive_text(read_command_output(enable_result))}"
        )

    start_result = run_command([SYSTEMCTL_BIN, "start", service_name], timeout=30)
    if start_result.returncode != 0:
        raise RuntimeError(
            f"Unable to start {service_name}: {redact_sensitive_text(read_command_output(start_result))}"
        )


def normalize_device_id(raw_value):
    value = str(raw_value or "").strip()
    if re.fullmatch(r"SC-\d{6}", value):
        return value
    if re.fullmatch(r"stay-compass-\d{6}", value):
        return value.upper().replace("STAY-COMPASS-", "SC-")
    return ""


def build_tailscale_hostname(device_id):
    normalized = normalize_device_id(device_id)
    if normalized.startswith("SC-"):
        return f"stay-compass-{normalized.split('-', 1)[1].lower()}"

    fallback = re.sub(r"[^a-z0-9-]+", "-", str(device_id or "").lower()).strip("-")
    if not fallback:
        fallback = "stay-compass-unknown"
    if not fallback.startswith("stay-compass-"):
        fallback = f"stay-compass-{fallback}"
    return fallback[:63]


def ensure_device_id(device_id_path=DEVICE_ID_PATH):
    device_id_path.parent.mkdir(parents=True, exist_ok=True)

    if device_id_path.exists():
        existing = normalize_device_id(device_id_path.read_text(encoding="utf-8"))
        if existing:
            return existing

    for _ in range(20):
        candidate = f"SC-{random.SystemRandom().randrange(0, 1_000_000):06d}"
        if normalize_device_id(candidate):
            device_id_path.write_text(candidate + "\n", encoding="utf-8")
            os.chmod(device_id_path, 0o644)
            return candidate

    raise RuntimeError("Unable to generate a persistent Stay Compass device ID.")


def load_tailscale_status_payload():
    result = run_command([TAILSCALE_BIN, "status", "--json"], timeout=30)
    if result.returncode != 0:
        raise RuntimeError(redact_sensitive_text(read_command_output(result)))
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Unable to parse tailscale status output: {error}") from error


def read_tailscale_ipv4():
    result = run_command([TAILSCALE_BIN, "ip", "-4"], timeout=20)
    if result.returncode != 0:
        return ""

    for line in (result.stdout or "").splitlines():
        candidate = line.strip()
        if candidate:
            return candidate
    return ""


def parse_status_payload(payload, *, installed, service_running, fallback_hostname, device_id, last_error=""):
    backend_state = str(payload.get("BackendState") or "").strip()
    self_info = payload.get("Self") or {}
    dns_name = str(self_info.get("DNSName") or "").strip().rstrip(".")
    display_name = str(self_info.get("HostName") or "").strip()
    health_items = payload.get("Health") or []
    first_health = ""
    for item in health_items:
        candidate = redact_sensitive_text(item)
        if candidate:
            first_health = candidate
            break

    tailscale_ip = read_tailscale_ipv4() if service_running and installed else ""
    connected = backend_state.lower() == "running" and bool(tailscale_ip)
    enrolled = backend_state.lower() not in {"", "needslogin", "nostate"}
    if backend_state.lower() == "running":
        enrolled = True

    device_name = dns_name.split(".", 1)[0] if dns_name else display_name or fallback_hostname
    if not backend_state:
        if not installed:
            backend_state = "Not installed"
        elif not service_running:
            backend_state = "Service stopped"
        else:
            backend_state = "Not enrolled"

    status_label = "Disconnected"
    if not installed:
        status_label = "Not installed"
    elif not service_running:
        status_label = "Disconnected"
    elif connected:
        status_label = "Connected"
    elif backend_state.lower() in {"needslogin", "nostate"}:
        status_label = "Not enrolled"

    return {
        "installed": bool(installed),
        "service_running": bool(service_running),
        "backend_state": backend_state,
        "connected": bool(connected),
        "enrolled": bool(enrolled),
        "status_label": status_label,
        "tailscale_ip": tailscale_ip,
        "tailscale_hostname": device_name or fallback_hostname,
        "device_name": device_id,
        "display_name": display_name or device_name or fallback_hostname,
        "last_error": redact_sensitive_text(last_error or first_health),
    }


def collect_status():
    device_id = ensure_device_id()
    hostname = build_tailscale_hostname(device_id)
    installed = command_exists(TAILSCALE_BIN) and command_exists(SYSTEMCTL_BIN)

    if not installed:
        return {
            "installed": False,
            "service_running": False,
            "backend_state": "Not installed",
            "connected": False,
            "enrolled": False,
            "status_label": "Not installed",
            "tailscale_ip": "",
            "tailscale_hostname": hostname,
            "device_name": device_id,
            "display_name": hostname,
            "last_error": "",
        }

    service_running = service_is_active("tailscaled")
    if not service_running:
        return {
            "installed": True,
            "service_running": False,
            "backend_state": "Service stopped",
            "connected": False,
            "enrolled": False,
            "status_label": "Disconnected",
            "tailscale_ip": "",
            "tailscale_hostname": hostname,
            "device_name": device_id,
            "display_name": hostname,
            "last_error": "",
        }

    try:
        payload = load_tailscale_status_payload()
    except RuntimeError as error:
        return {
            "installed": True,
            "service_running": True,
            "backend_state": "Not enrolled",
            "connected": False,
            "enrolled": False,
            "status_label": "Not enrolled",
            "tailscale_ip": "",
            "tailscale_hostname": hostname,
            "device_name": device_id,
            "display_name": hostname,
            "last_error": redact_sensitive_text(str(error)),
        }

    return parse_status_payload(
        payload,
        installed=True,
        service_running=True,
        fallback_hostname=hostname,
        device_id=device_id,
    )


def read_auth_key_from_stdin():
    auth_key = sys.stdin.read().strip()
    if not auth_key:
        raise RuntimeError("A Tailscale auth key is required.")
    return auth_key


def tailscale_up_with_auth_key(auth_key, hostname):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        temp_path = handle.name
        handle.write(auth_key)

    try:
        os.chmod(temp_path, 0o600)
        command = [
            TAILSCALE_BIN,
            "up",
            f"--auth-key=file:{temp_path}",
            f"--hostname={hostname}",
            "--accept-dns=true",
            "--accept-routes=false",
            "--reset",
        ]
        result = run_command(command, timeout=90)
        if result.returncode != 0:
            raise RuntimeError(redact_sensitive_text(read_command_output(result)))
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def enroll():
    if not command_exists(TAILSCALE_BIN):
        raise RuntimeError("Tailscale is not installed.")

    device_id = ensure_device_id()
    hostname = build_tailscale_hostname(device_id)
    auth_key = read_auth_key_from_stdin()

    ensure_service_running("tailscaled")
    try:
        ensure_service_running(SSH_SERVICE_NAME)
    except RuntimeError:
        pass

    tailscale_up_with_auth_key(auth_key, hostname)
    status = collect_status()
    status["message"] = "Remote support enabled."
    return status


def tailscale_down():
    result = run_command([TAILSCALE_BIN, "down"], timeout=45)
    if result.returncode != 0:
        raise RuntimeError(redact_sensitive_text(read_command_output(result)))
    status = collect_status()
    status["message"] = "Remote support disconnected."
    return status


def tailscale_logout():
    result = run_command([TAILSCALE_BIN, "logout"], timeout=45)
    if result.returncode != 0:
        raise RuntimeError(redact_sensitive_text(read_command_output(result)))
    status = collect_status()
    status["message"] = "Remote support logged out."
    return status


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in ALLOWED_OPERATIONS:
        print(json.dumps({"error": "Unsupported remote support operation."}))
        return 2

    operation = args[0]

    try:
        if operation == "status":
            payload = collect_status()
        elif operation == "enroll":
            payload = enroll()
        elif operation == "down":
            payload = tailscale_down()
        else:
            payload = tailscale_logout()
    except Exception as error:
        print(json.dumps({"error": redact_sensitive_text(str(error))}))
        return 1

    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
