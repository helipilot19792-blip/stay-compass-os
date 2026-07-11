# Remote Support

Stay Compass OS supports secure remote SSH support through Tailscale.

## Overview

- Devices keep using ordinary OpenSSH and the existing `scadmin` Linux account.
- Tailscale provides private connectivity to the Raspberry Pi without router port forwarding.
- The local admin page at `http://127.0.0.1:8750/` is the only place where enrollment keys can be submitted.
- Auth keys, API keys, and enrollment secrets must never be committed to GitHub or stored in `device/config.json`.

## Create An Auth Key

1. Sign in to the Tailscale admin console.
2. Open the Keys page.
3. Generate an auth key for device enrollment.
4. Prefer a one-off key when practical.
5. If you use a reusable key, protect it like any other production secret.

Do not paste a real auth key into this repository, documentation, screenshots, or source control.

## First-Time Enrollment

1. Open the device's local admin page on the Raspberry Pi.
2. Unlock the page with the local admin PIN.
3. Open `Remote Support`.
4. Confirm the device status and device name.
5. Paste the Tailscale auth key into the hidden key field.
6. Use `Show key` only if needed for local verification.
7. Select `Enable Remote Support`.
8. Wait for the status to show `Connected`.

The auth key is submitted only to the local backend, passed to the root helper briefly, and then discarded. The current implementation uses Tailscale's supported `--auth-key=file:/path` form with a short-lived root-only temp file because the CLI does not provide a documented stdin auth-key mode.

## Device Identity

- Each device keeps a persistent Stay Compass device ID in `/var/lib/stay-compass/device-id`.
- The installer creates the ID once and reuses it across reboots and updates.
- Tailscale enrollment uses a stable hostname derived from that ID, such as `stay-compass-123456`.
- This does not change the Raspberry Pi's normal Linux hostname.

## SSH From Windows

After enrollment, connect from a Tailscale-connected Windows PC with:

```powershell
ssh scadmin@100.x.y.z
```

If MagicDNS is enabled for the Tailnet, you can also use:

```powershell
ssh scadmin@stay-compass-123456
```

## Find The Tailscale IP

- Open the device's local admin page.
- Go to `Remote Support`.
- Read the `Tailscale IP` field.

You can also confirm the device and IP in the Tailscale admin console.

## Disable Or Remove Remote Support

- `Disconnect Temporarily` runs `tailscale down`.
  This usually preserves enrollment and can be reversed locally.
- `Logout Remote Support` runs `tailscale logout`.
  This removes the device from the Tailnet and requires a new auth key to enroll again.

Either action can immediately terminate an active SSH session.

## Revoke A Lost Device

1. Sign in to the Tailscale admin console.
2. Open the Machines or Devices page.
3. Find the Stay Compass device hostname.
4. Expire, disable, or remove the device from the Tailnet.
5. If needed, revoke the auth key used during enrollment.

## Testing After Deployment

1. Run the Stay Compass installer on the Pi.
2. Confirm `tailscaled` starts without blocking the kiosk.
3. Open local admin and enroll the device through `Remote Support`.
4. Confirm the page shows `Connected` and a Tailscale IP.
5. From a Tailscale-connected Windows PC, run `ssh scadmin@<tailscale-ip>`.
6. Confirm `Disconnect Temporarily` drops connectivity.
7. Confirm `Logout Remote Support` removes access and requires a new auth key.
