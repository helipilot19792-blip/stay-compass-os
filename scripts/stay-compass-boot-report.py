#!/usr/bin/env python3

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


SERVICE_USER = "compass"
DISPLAY = ":0"
XAUTHORITY = f"/home/{SERVICE_USER}/.Xauthority"
OUTPUT_DIR = Path("/var/lib/stay-compass/boot-performance")
JSON_REPORT = OUTPUT_DIR / "last-report.json"
TEXT_REPORT = OUTPUT_DIR / "last-report.txt"


def run_command(command):
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )


def parse_duration(value):
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(ms|s|min)", value.strip())

    if not match:
        raise ValueError(f"Unsupported duration format: {value}")

    amount = float(match.group(1))
    unit = match.group(2)

    if unit == "ms":
        return amount / 1000
    if unit == "s":
        return amount
    if unit == "min":
        return amount * 60

    raise ValueError(f"Unsupported duration unit: {unit}")


def read_systemd_timestamp(unit_name):
    result = run_command(
        [
            "systemctl",
            "show",
            unit_name,
            "--property=ActiveEnterTimestampMonotonic",
            "--value",
        ]
    )

    if result.returncode != 0:
        return None

    value = result.stdout.strip()
    if not value.isdigit():
        return None

    return int(value) / 1_000_000


def read_startup_breakdown():
    result = run_command(["systemd-analyze", "time"])
    if result.returncode != 0:
        return {}

    line = result.stdout.strip()

    durations = {}
    for label in ("firmware", "loader", "kernel", "userspace"):
        match = re.search(rf"([0-9.]+(?:ms|s|min)) \({label}\)", line)
        if match:
            durations[label] = parse_duration(match.group(1))

    total_match = re.search(r"= ([0-9.]+(?:ms|s|min))", line)
    if total_match:
        durations["total"] = parse_duration(total_match.group(1))

    return durations


def chromium_visible():
    checks = [
        [
            "runuser",
            "-u",
            SERVICE_USER,
            "--",
            "env",
            f"DISPLAY={DISPLAY}",
            f"XAUTHORITY={XAUTHORITY}",
            "xdotool",
            "search",
            "--onlyvisible",
            "--class",
            "chromium",
        ],
        [
            "runuser",
            "-u",
            SERVICE_USER,
            "--",
            "env",
            f"DISPLAY={DISPLAY}",
            f"XAUTHORITY={XAUTHORITY}",
            "xdotool",
            "search",
            "--onlyvisible",
            "--class",
            "Chromium",
        ],
    ]

    return any(run_command(command).returncode == 0 for command in checks)


def wait_for_chromium():
    while True:
        if chromium_visible():
            return time.monotonic()
        time.sleep(0.25)


def quit_plymouth():
    run_command(["plymouth", "quit"])


def write_report(report):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "Stay Compass Boot Performance Report",
        f"Generated at: {report['generated_at']}",
        "",
        f"Time from power-on to splash: {report['time_from_power_on_to_splash_seconds']:.3f}s",
        f"Time splash is displayed: {report['time_splash_is_displayed_seconds']:.3f}s",
        f"Time until Chromium becomes visible: {report['time_until_chromium_visible_seconds']:.3f}s",
        f"Total boot time: {report['total_boot_time_seconds']:.3f}s",
    ]
    TEXT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    startup = read_startup_breakdown()
    firmware_time = startup.get("firmware", 0.0)
    loader_time = startup.get("loader", 0.0)
    splash_monotonic = read_systemd_timestamp("plymouth-start.service") or 0.0

    chromium_visible_monotonic = wait_for_chromium()
    chromium_visible_seconds = firmware_time + loader_time + chromium_visible_monotonic
    splash_seconds = firmware_time + loader_time + splash_monotonic
    splash_duration_seconds = max(0.0, chromium_visible_seconds - splash_seconds)
    total_boot_time = startup.get("total", chromium_visible_seconds)

    quit_plymouth()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "time_from_power_on_to_splash_seconds": round(splash_seconds, 3),
        "time_splash_is_displayed_seconds": round(splash_duration_seconds, 3),
        "time_until_chromium_visible_seconds": round(chromium_visible_seconds, 3),
        "total_boot_time_seconds": round(total_boot_time, 3),
    }

    write_report(report)


if __name__ == "__main__":
    main()
