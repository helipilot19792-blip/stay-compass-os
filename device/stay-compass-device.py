#!/usr/bin/env python3

"""
Stay Compass Device Service
"""

import json
import logging
import socket
import subprocess
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"

LOG_FILE = "/tmp/stay-compass-device.log"
NETWORK_CHECK_HOST = "1.1.1.1"
NETWORK_CHECK_PORT = 53
NETWORK_TIMEOUT_SECONDS = 3

CHROMIUM_BIN = "/usr/bin/chromium"


def setup_logging():
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )


def log(message):
    print(message)
    logging.info(message)


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as config_file:
        return json.load(config_file)


def has_network():
    try:
        socket.create_connection(
            (NETWORK_CHECK_HOST, NETWORK_CHECK_PORT),
            timeout=NETWORK_TIMEOUT_SECONDS,
        )
        return True
    except OSError:
        return False


def launch_chromium(pwa_url):
    log("Launching Chromium...")

    return subprocess.Popen(
        [
            CHROMIUM_BIN,
            "--kiosk",
            "--noerrdialogs",
            "--disable-infobars",
            "--disable-session-crashed-bubble",
            pwa_url,
        ]
    )


def main():
    setup_logging()
    config = load_config()
    pwa_url = config.get("pwa_url")

    log("===================================")
    log(" Stay Compass Device Service")
    log(" Version 0.1.0")
    log("===================================")
    log(f"PWA URL: {pwa_url}")
    log("Starting device service...")

    chromium_process = None

    try:
        while True:
            if not has_network():
                log("Network offline. Waiting...")
                time.sleep(10)
                continue

            if chromium_process is None:
                chromium_process = launch_chromium(pwa_url)

            if chromium_process.poll() is not None:
                log("Chromium exited. Restarting...")
                chromium_process = launch_chromium(pwa_url)

            time.sleep(5)

    except KeyboardInterrupt:
        log("Stay Compass Device Service stopped.")

        if chromium_process is not None and chromium_process.poll() is None:
            log("Stopping Chromium...")
            chromium_process.terminate()


if __name__ == "__main__":
    main()