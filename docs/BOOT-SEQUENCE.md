# Stay Compass Boot Sequence

## Overview

Stay Compass OS uses the stock Raspberry Pi boot flow and keeps the existing kiosk and device service architecture in place.

The installer suppresses visible firmware and kernel output on HDMI, then shows the Stay Compass splash on the framebuffer while the kiosk stack starts.

## Boot Flow

1. Raspberry Pi firmware loads the kernel and initramfs from `/boot/firmware`.
2. The installer configures `config.txt` with `disable_splash=1` and `auto_initramfs=1`.
3. The installer rewrites `cmdline.txt` to include `quiet splash` and suppress visible kernel and systemd status text on the display.
4. Plymouth is explicitly disabled with `plymouth.enable=0`; this avoids a Raspberry Pi crash path observed with scripted Plymouth themes.
5. `stay-compass-splash.service` renders the Stay Compass splash on `/dev/fb0` with `fbi` before the kiosk target.
6. `stay-compass-kiosk.service` starts X on `tty1`, launches Openbox, and then hands off to the existing Python device service.
7. The device service starts the local admin portal on `127.0.0.1:8750`.
8. When network connectivity is available, the device service checks the configured Git repository for a newer commit.
9. If an update is available, Chromium opens a local update screen with a progress bar while the update helper pulls the new code and re-runs the installer.
10. After a successful update, the device service restarts itself into the newly installed code.
11. If no update is available, the device service launches Chromium into the Stay Compass app.
12. If network connectivity is unavailable, the device service opens a locked staff-access screen for Wi-Fi recovery.
13. `stay-compass-boot-report.service` waits for a visible Chromium window and records boot timings.

## Files Managed By The Installer

- `/boot/firmware/config.txt` or `/boot/config.txt`
- `/boot/firmware/cmdline.txt` or `/boot/cmdline.txt`
- `/etc/systemd/system/stay-compass-splash.service`
- `/etc/systemd/system/stay-compass-kiosk.service`
- `/etc/systemd/system/stay-compass-boot-report.service`
- `/etc/sudoers.d/stay-compass-update`
- `/opt/stay-compass/run-update.sh`
- `/opt/stay-compass/bin/stay-compass-boot-report.py`
- `/var/lib/stay-compass/boot-performance/last-report.json`
- `/var/lib/stay-compass/boot-performance/last-report.txt`

## Performance Report

After Chromium is visible, the installer-provided report service writes a baseline report to:

- `/var/lib/stay-compass/boot-performance/last-report.json`
- `/var/lib/stay-compass/boot-performance/last-report.txt`

The report captures:

- Time from power-on to splash
- Time the splash remained visible
- Time until Chromium became visible
- Total boot time reported by `systemd-analyze`

## Update Behavior

The device checks for updates once per kiosk service start, after internet connectivity is available. Updates are pulled from the configured Git remote and branch in `/opt/stay-compass/device/config.json`.

If the remote commit differs from the local checkout, the local update screen is shown at `http://127.0.0.1:8750/updating`, the update helper runs `git pull --ff-only`, and the installer is re-run. The device service then restarts itself so the newly installed code is active.

The installer preserves existing per-device config values, including `admin_pin`, and stamps the active repository path into `update_repo_dir`. This keeps updates from resetting local device settings.

The boot configuration is re-applied on every install run and the splash service is installed from this repository. That keeps the appliance boot experience reproducible across fresh installs, reboots, and package updates.
