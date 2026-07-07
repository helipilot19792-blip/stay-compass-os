#!/usr/bin/env python3

"""
Stay Compass Device Service
"""

import logging
import time


LOG_FILE = "/tmp/stay-compass-device.log"


def setup_logging():
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )


def log(message):
    print(message)
    logging.info(message)


def main():
    setup_logging()

    log("===================================")
    log(" Stay Compass Device Service")
    log(" Version 0.1.0")
    log("===================================")
    log("Starting device service...")

    try:
        while True:
            log("Device service running...")
            time.sleep(10)
    except KeyboardInterrupt:
        log("Stay Compass Device Service stopped.")


if __name__ == "__main__":
    main()