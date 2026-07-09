# Stay Compass OS

Version: 0.1.0

## Purpose

Stay Compass OS is a secure operating system for dedicated guest display devices.

Its purpose is to provide a reliable, appliance-like experience that boots directly into the Stay Compass application while remaining easy to deploy, maintain, and update.

Stay Compass OS is responsible for the device itself. Guest data is provided by external services through approved APIs and is not managed directly by the operating system.

## Design Principles

- Appliance-first experience
- Secure by default
- Remote management capable
- Automatic recovery from failures
- Offline tolerant
- Hardware agnostic where practical

## System Components

- Installer
- Boot Experience
- Kiosk
- Local Admin Mode
- Device Services
- Configuration
- Update System
- Recovery System

## Local Admin Mode

Stay Compass devices run a local admin portal on `http://127.0.0.1:8750/`.

The device service opens a locked staff-access screen when internet connectivity is unavailable long enough to indicate setup or recovery is needed. Guests can see only the neutral connection message. Admin tools and detailed diagnostics require the local `admin_pin` before any controls or device details are exposed.

The portal is intended to hold device-only workflows:

- Wi-Fi scanning and connection changes
- Device registration
- Local diagnostics
- Update and restart controls

Admin actions are protected by the local `admin_pin` value in `device/config.json`. Production builds should replace the default PIN during provisioning.

## Update System

On each kiosk service start, the device service checks the configured Git remote after network connectivity is available. When a newer commit exists, Chromium opens a local updating screen with a progress bar while `/opt/stay-compass/run-update.sh` pulls the update and re-runs the installer.

The updater uses the local fields in `device/config.json`:

- `auto_update_on_boot`
- `update_repo_dir`
- `update_remote`
- `update_branch`

The installer preserves existing per-device config values, including the admin PIN, so software updates do not reset local access settings.

## Release Roadmap

### 0.1.0
- Project structure
- Installer
- Git repository
- Versioning

### 0.2.0
- Custom boot splash
- Kiosk launcher
- Chromium watchdog
- Offline detection

### 0.3.0
- Wi-Fi provisioning
- Local admin mode
- Device registration
- Automatic updates
