# Stay Compass Boot Sequence

## Overview

Stay Compass OS uses the stock Raspberry Pi boot flow and keeps the existing kiosk and device service architecture in place.

The installer now adds a branded Plymouth splash during early boot, suppresses visible firmware and kernel output on HDMI, and keeps the splash on screen until Chromium is visible.

## Boot Flow

1. Raspberry Pi firmware loads the kernel and initramfs from `/boot/firmware`.
2. The installer configures `config.txt` with `disable_splash=1` and `auto_initramfs=1`.
3. The installer rewrites `cmdline.txt` to include `quiet splash` and suppress visible kernel and systemd status text on the display.
4. Plymouth starts from the initramfs and renders the Stay Compass splash before normal userspace finishes booting.
5. `stay-compass-splash.service` keeps Plymouth in boot splash mode while the system reaches the kiosk target.
6. `stay-compass-kiosk.service` starts X on `tty1`, launches Openbox, and then hands off to the existing Python device service.
7. The device service launches Chromium when network connectivity is available.
8. `stay-compass-boot-report.service` waits for a visible Chromium window, records boot timings, and then dismisses the splash.

## Files Managed By The Installer

- `/boot/firmware/config.txt` or `/boot/config.txt`
- `/boot/firmware/cmdline.txt` or `/boot/cmdline.txt`
- `/usr/share/plymouth/themes/stay-compass/`
- `/etc/systemd/system/stay-compass-splash.service`
- `/etc/systemd/system/stay-compass-kiosk.service`
- `/etc/systemd/system/stay-compass-boot-report.service`
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

The boot configuration is re-applied on every install run, the Plymouth theme is installed from this repository, and initramfs is rebuilt automatically. That keeps the appliance boot experience reproducible across fresh installs, reboots, and package updates.
