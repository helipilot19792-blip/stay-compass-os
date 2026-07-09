#!/usr/bin/env python3

"""
Stay Compass Device Service
"""

import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs


BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"

LOG_FILE = "/tmp/stay-compass-device.log"
NETWORK_CHECK_HOST = "1.1.1.1"
NETWORK_CHECK_PORT = 53
NETWORK_TIMEOUT_SECONDS = 3
OFFLINE_ADMIN_DELAY_SECONDS = 20
ADMIN_HOST = "127.0.0.1"
ADMIN_PORT = 8750
UPDATE_HELPER = "/opt/stay-compass/run-update.sh"

CHROMIUM_BIN = "/usr/bin/chromium"
NMCLI_BIN = "/usr/bin/nmcli"
SUDO_BIN = "/usr/bin/sudo"

APP_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stay Compass</title>
  <style>
    html, body {
      width: 100%%;
      height: 100%%;
      margin: 0;
      overflow: hidden;
      background: #ffffff;
    }
    body {
      position: relative;
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    iframe {
      width: 100%%;
      height: 100%%;
      border: 0;
      display: block;
      background: #ffffff;
    }
    .admin-trigger {
      position: fixed;
      top: 0;
      left: 0;
      width: 56px;
      height: 56px;
      z-index: 10;
      background: transparent;
    }
  </style>
</head>
<body>
  <div id="adminTrigger" class="admin-trigger" aria-hidden="true"></div>
  <iframe id="appFrame" title="Stay Compass" loading="eager"></iframe>
  <script>
    const gesture = {
      count: 0,
      firstTapAt: 0,
      requiredTaps: 5,
      windowMs: 5000
    };

    async function openAdmin() {
      try {
        await fetch("/api/open-admin", { method: "POST" });
      } catch (error) {
        // Navigation below still works offline because this shell and admin page are local.
      }
      window.location.replace("/admin");
    }

    function registerAdminTap() {
      const now = Date.now();
      if (!gesture.firstTapAt || now - gesture.firstTapAt > gesture.windowMs) {
        gesture.firstTapAt = now;
        gesture.count = 0;
      }

      gesture.count += 1;

      if (gesture.count >= gesture.requiredTaps) {
        gesture.count = 0;
        gesture.firstTapAt = 0;
        openAdmin();
      }
    }

    document.querySelector("#adminTrigger").addEventListener("pointerdown", (event) => {
      event.preventDefault();
      registerAdminTap();
    });

    document.querySelector("#appFrame").src = %(pwa_url_json)s;
  </script>
</body>
</html>
"""

ADMIN_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stay Compass Admin</title>
  <style>
    :root {
      --keyboard-height: 0px;
      color-scheme: light;
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f4f6f8;
      color: #17202a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 28px;
      overflow-x: hidden;
    }
    body.keyboard-open {
      place-items: start center;
      padding-bottom: calc(var(--keyboard-height) + 28px);
    }
    main {
      width: min(920px, 100%);
      background: #ffffff;
      border: 1px solid #d7dde3;
      border-radius: 8px;
      box-shadow: 0 18px 60px rgba(23, 32, 42, 0.12);
      overflow: hidden;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      padding: 28px;
      border-bottom: 1px solid #e6eaee;
      background: #fbfcfd;
    }
    h1, h2 { margin: 0; line-height: 1.15; }
    h1 { font-size: 28px; }
    h2 { font-size: 18px; margin-bottom: 14px; }
    p { margin: 8px 0 0; color: #53616f; }
    section { padding: 24px 28px; border-bottom: 1px solid #edf0f2; }
    section:last-child { border-bottom: 0; }
    .status {
      min-width: 180px;
      text-align: right;
      font-weight: 700;
      color: #8a5a00;
    }
    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(240px, 320px);
      gap: 18px;
      align-items: end;
    }
    label {
      display: grid;
      gap: 7px;
      font-size: 13px;
      font-weight: 700;
      color: #324150;
    }
    input, select {
      width: 100%;
      min-height: 44px;
      border: 1px solid #bcc7d1;
      border-radius: 6px;
      padding: 10px 12px;
      font: inherit;
      background: #ffffff;
    }
    input, textarea {
      scroll-margin-bottom: calc(var(--keyboard-height) + 24px);
    }
    button {
      min-height: 44px;
      border: 0;
      border-radius: 6px;
      padding: 10px 15px;
      font: inherit;
      font-weight: 800;
      cursor: pointer;
      background: #155c5f;
      color: #ffffff;
    }
    button.secondary {
      background: #e8edf1;
      color: #23313f;
    }
    .touch-keyboard {
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      z-index: 20;
      padding: 12px;
      background: #101820;
      border-top: 4px solid #155c5f;
      box-shadow: 0 -16px 40px rgba(16, 24, 32, 0.22);
    }
    .keyboard-inner {
      width: min(920px, 100%);
      margin: 0 auto;
      display: grid;
      gap: 8px;
    }
    .keyboard-row {
      display: flex;
      gap: 8px;
      justify-content: center;
    }
    .keyboard-key {
      min-width: 0;
      min-height: 46px;
      flex: 1 1 0;
      padding: 8px 10px;
      border: 1px solid rgba(255, 255, 255, 0.14);
      background: #24313d;
      color: #ffffff;
      border-radius: 6px;
      font-size: 18px;
    }
    .keyboard-key.wide { flex-grow: 1.6; }
    .keyboard-key.extra-wide { flex-grow: 4; }
    .keyboard-key.active {
      background: #f0b429;
      color: #101820;
    }
    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 16px;
    }
    .message {
      margin-top: 14px;
      min-height: 22px;
      font-weight: 700;
      color: #155c5f;
    }
    .locked {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(160px, 220px);
      gap: 14px;
      align-items: end;
    }
    .hidden { display: none; }
    dl {
      display: grid;
      grid-template-columns: max-content minmax(0, 1fr);
      gap: 8px 16px;
      margin: 0;
    }
    dt { font-weight: 800; color: #324150; }
    dd { margin: 0; color: #53616f; word-break: break-word; }
    @media (max-width: 760px) {
      body { padding: 14px; place-items: stretch; }
      body.keyboard-open { padding-bottom: calc(var(--keyboard-height) + 14px); }
      header, section { padding: 20px; }
      header { display: block; }
      .status { text-align: left; margin-top: 12px; }
      .grid, .locked { grid-template-columns: 1fr; }
      .keyboard-key { min-height: 42px; padding: 7px 8px; font-size: 16px; }
      .touch-keyboard { padding: 10px 8px; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Stay Compass</h1>
        <p id="screenDescription">Connection is unavailable. Staff access is required for device settings.</p>
      </div>
      <div id="networkStatus" class="status">Checking...</div>
    </header>

    <section id="lockSection">
      <h2>Staff Access</h2>
      <div class="locked">
        <label>
          Admin PIN
          <input id="unlockPin" type="password" inputmode="numeric" autocomplete="off">
        </label>
        <button id="unlock" type="button">Unlock</button>
      </div>
      <div id="lockMessage" class="message"></div>
    </section>

    <section id="wifiSection" class="hidden">
      <h2>Wi-Fi</h2>
      <div class="grid">
        <label>
          Network
          <select id="ssid"></select>
        </label>
        <button id="scan" class="secondary" type="button">Scan Networks</button>
        <label>
          Wi-Fi Password
          <input id="password" type="password" autocomplete="current-password">
        </label>
      </div>
      <div class="actions">
        <button id="connect" type="button">Connect Wi-Fi</button>
        <button id="openApp" class="secondary" type="button">Open Stay Compass</button>
      </div>
      <div id="message" class="message"></div>
    </section>

    <section id="diagnosticsSection" class="hidden">
      <h2>Diagnostics</h2>
      <dl>
        <dt>App URL</dt><dd id="appUrl">-</dd>
        <dt>Admin URL</dt><dd>http://127.0.0.1:8750/</dd>
        <dt>Device</dt><dd id="deviceName">-</dd>
        <dt>Network</dt><dd id="networkDetail">-</dd>
      </dl>
    </section>
  </main>
  <div id="touchKeyboard" class="touch-keyboard hidden" aria-label="Touch keyboard"></div>
  <script>
    const els = {
      appUrl: document.querySelector("#appUrl"),
      connect: document.querySelector("#connect"),
      diagnosticsSection: document.querySelector("#diagnosticsSection"),
      deviceName: document.querySelector("#deviceName"),
      lockMessage: document.querySelector("#lockMessage"),
      lockSection: document.querySelector("#lockSection"),
      message: document.querySelector("#message"),
      networkDetail: document.querySelector("#networkDetail"),
      networkStatus: document.querySelector("#networkStatus"),
      openApp: document.querySelector("#openApp"),
      password: document.querySelector("#password"),
      screenDescription: document.querySelector("#screenDescription"),
      scan: document.querySelector("#scan"),
      ssid: document.querySelector("#ssid"),
      touchKeyboard: document.querySelector("#touchKeyboard"),
      unlock: document.querySelector("#unlock"),
      unlockPin: document.querySelector("#unlockPin"),
      wifiSection: document.querySelector("#wifiSection")
    };
    const TEXT_INPUT_SELECTOR = 'input[type="text"], input[type="password"], input[type="search"], input[type="email"], input[type="url"], input[type="tel"], input:not([type]), textarea';
    const KEYBOARD_MARGIN = 16;

    let adminPin = "";

    function setMessage(text) {
      els.message.textContent = text;
    }

    function setLockMessage(text) {
      els.lockMessage.textContent = text;
    }

    async function api(path, options = {}) {
      const response = await fetch(path, options);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Request failed");
      }
      return data;
    }

    async function refreshStatus() {
      const status = await api("/api/status");
      els.networkStatus.textContent = status.online ? "Online" : "Offline";
      els.networkStatus.style.color = status.online ? "#155c5f" : "#8a2d16";
    }

    async function refreshAdminStatus() {
      const body = new URLSearchParams({ pin: adminPin });
      const status = await api("/api/admin-status", { method: "POST", body });
      els.appUrl.textContent = status.pwa_url || "-";
      els.deviceName.textContent = status.hostname || "-";
      els.networkDetail.textContent = status.online ? "Internet check passed" : "Internet check failed";
      els.networkStatus.textContent = status.online ? "Online" : "Offline";
      els.networkStatus.style.color = status.online ? "#155c5f" : "#8a2d16";
    }

    function showAdmin() {
      els.lockSection.classList.add("hidden");
      els.wifiSection.classList.remove("hidden");
      els.diagnosticsSection.classList.remove("hidden");
      els.screenDescription.textContent = "Device setup, Wi-Fi recovery, and local diagnostics.";
      hideTouchKeyboard();
    }

    function isKeyboardInput(element) {
      return Boolean(element && element.matches && element.matches(TEXT_INPUT_SELECTOR));
    }

    function updateKeyboardHeight() {
      const keyboardHeight = els.touchKeyboard.classList.contains("hidden")
        ? 0
        : Math.ceil(els.touchKeyboard.getBoundingClientRect().height);
      document.documentElement.style.setProperty("--keyboard-height", `${keyboardHeight}px`);
      return keyboardHeight;
    }

    function hideTouchKeyboard() {
      els.touchKeyboard.classList.add("hidden");
      document.body.classList.remove("keyboard-open");
      activeKeyboardInput = null;
      updateKeyboardHeight();
    }

    function showTouchKeyboard(input) {
      if (!isKeyboardInput(input)) return;
      activeKeyboardInput = input;
      els.touchKeyboard.classList.remove("hidden");
      document.body.classList.add("keyboard-open");
      renderTouchKeyboard();
      updateKeyboardHeight();
      window.requestAnimationFrame(() => ensureInputVisible(input));
    }

    let activeKeyboardInput = null;
    let keyboardShift = false;
    let keyboardCaps = false;

    function ensureInputVisible(input) {
      if (!isKeyboardInput(input) || els.touchKeyboard.classList.contains("hidden")) return;

      const rect = input.getBoundingClientRect();
      const keyboardTop = els.touchKeyboard.getBoundingClientRect().top;
      const visibleBottom = keyboardTop - KEYBOARD_MARGIN;
      const visibleTop = KEYBOARD_MARGIN;

      if (rect.bottom > visibleBottom) {
        window.scrollBy({ top: rect.bottom - visibleBottom, behavior: "smooth" });
      } else if (rect.top < visibleTop) {
        window.scrollBy({ top: rect.top - visibleTop, behavior: "smooth" });
      }
    }

    function keyboardLetter(value) {
      return keyboardShift || keyboardCaps ? value.toUpperCase() : value;
    }

    function inputText(value) {
      if (!activeKeyboardInput) return;
      activeKeyboardInput.focus();
      const start = activeKeyboardInput.selectionStart ?? activeKeyboardInput.value.length;
      const end = activeKeyboardInput.selectionEnd ?? activeKeyboardInput.value.length;
      activeKeyboardInput.setRangeText(value, start, end, "end");
      activeKeyboardInput.dispatchEvent(new Event("input", { bubbles: true }));
      if (keyboardShift && !keyboardCaps) {
        keyboardShift = false;
        renderTouchKeyboard();
      }
    }

    function backspaceInput() {
      if (!activeKeyboardInput) return;
      activeKeyboardInput.focus();
      const start = activeKeyboardInput.selectionStart ?? activeKeyboardInput.value.length;
      const end = activeKeyboardInput.selectionEnd ?? activeKeyboardInput.value.length;
      if (start !== end) {
        activeKeyboardInput.setRangeText("", start, end, "end");
      } else if (start > 0) {
        activeKeyboardInput.setRangeText("", start - 1, start, "end");
      }
      activeKeyboardInput.dispatchEvent(new Event("input", { bubbles: true }));
    }

    function keyboardButton(label, options = {}) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `keyboard-key ${options.className || ""}`.trim();
      button.textContent = label;
      if (options.active) {
        button.classList.add("active");
      }
      button.addEventListener("click", () => options.onClick());
      return button;
    }

    function addKeyboardRow(container, keys) {
      const row = document.createElement("div");
      row.className = "keyboard-row";
      for (const key of keys) {
        if (typeof key === "string") {
          row.appendChild(keyboardButton(keyboardLetter(key), { onClick: () => inputText(keyboardLetter(key)) }));
        } else {
          row.appendChild(keyboardButton(key.label, key));
        }
      }
      container.appendChild(row);
    }

    // Touch keyboard is initialized here so the local admin/setup page works offline on kiosk touchscreens.
    function initTouchKeyboard() {
      els.touchKeyboard.addEventListener("pointerdown", (event) => {
        event.preventDefault();
      });

      document.addEventListener("focusin", (event) => {
        const target = event.target;
        if (isKeyboardInput(target)) {
          showTouchKeyboard(target);
        }
      });

      document.addEventListener("focusout", (event) => {
        if (!isKeyboardInput(event.target)) {
          return;
        }
        window.setTimeout(() => {
          const nextTarget = document.activeElement;
          if (isKeyboardInput(nextTarget)) {
            showTouchKeyboard(nextTarget);
            return;
          }
          hideTouchKeyboard();
        }, 0);
      });

      document.addEventListener("pointerdown", (event) => {
        const target = event.target;
        if (els.touchKeyboard.contains(target)) {
          return;
        }

        if (isKeyboardInput(target)) {
          window.setTimeout(() => showTouchKeyboard(target), 0);
          return;
        }

        if (isKeyboardInput(document.activeElement)) {
          document.activeElement.blur();
        } else {
          hideTouchKeyboard();
        }
      });

      window.addEventListener("resize", () => {
        updateKeyboardHeight();
        ensureInputVisible(activeKeyboardInput);
      });
    }

    function renderTouchKeyboard() {
      els.touchKeyboard.innerHTML = "";
      const inner = document.createElement("div");
      inner.className = "keyboard-inner";

      addKeyboardRow(inner, ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]);
      addKeyboardRow(inner, ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"]);
      addKeyboardRow(inner, ["a", "s", "d", "f", "g", "h", "j", "k", "l"]);
      addKeyboardRow(inner, [
        { label: "Shift", className: "wide", active: keyboardShift, onClick: () => { keyboardShift = !keyboardShift; renderTouchKeyboard(); } },
        "z", "x", "c", "v", "b", "n", "m",
        { label: "Back", className: "wide", onClick: backspaceInput }
      ]);
      addKeyboardRow(inner, [
        { label: "Caps", className: "wide", active: keyboardCaps, onClick: () => { keyboardCaps = !keyboardCaps; renderTouchKeyboard(); } },
        { label: "!", onClick: () => inputText("!") },
        { label: "@", onClick: () => inputText("@") },
        { label: "#", onClick: () => inputText("#") },
        { label: "$", onClick: () => inputText("$") },
        { label: "%", onClick: () => inputText("%") },
        { label: "&", onClick: () => inputText("&") },
        { label: "*", onClick: () => inputText("*") },
        { label: "?", onClick: () => inputText("?") },
        { label: "Done", className: "wide", onClick: () => { if (activeKeyboardInput) activeKeyboardInput.blur(); else hideTouchKeyboard(); } }
      ]);
      addKeyboardRow(inner, [
        { label: "-", onClick: () => inputText("-") },
        { label: "_", onClick: () => inputText("_") },
        { label: "+", onClick: () => inputText("+") },
        { label: "=", onClick: () => inputText("=") },
        { label: ".", onClick: () => inputText(".") },
        { label: ",", onClick: () => inputText(",") },
        { label: "/", onClick: () => inputText("/") },
        { label: ":", onClick: () => inputText(":") },
        { label: ";", onClick: () => inputText(";") },
        { label: "Space", className: "extra-wide", onClick: () => inputText(" ") }
      ]);

      els.touchKeyboard.appendChild(inner);
      updateKeyboardHeight();
    }

    async function unlockAdmin() {
      setLockMessage("Checking PIN...");
      adminPin = els.unlockPin.value;
      const body = new URLSearchParams({ pin: adminPin });
      await api("/api/unlock", { method: "POST", body });
      showAdmin();
      setMessage("Admin mode unlocked.");
      await refreshAdminStatus();
      await scanNetworks();
    }

    async function scanNetworks() {
      setMessage("Scanning networks...");
      const body = new URLSearchParams({ pin: adminPin });
      const data = await api("/api/networks", { method: "POST", body });
      els.ssid.innerHTML = "";
      for (const network of data.networks) {
        const option = document.createElement("option");
        option.value = network.ssid;
        option.textContent = `${network.ssid} (${network.signal || "?"}%) ${network.security || ""}`;
        els.ssid.appendChild(option);
      }
      setMessage(data.networks.length ? "Choose a network and connect." : "No networks found.");
    }

    async function connectWifi() {
      setMessage("Connecting...");
      const body = new URLSearchParams({
        ssid: els.ssid.value,
        password: els.password.value,
        pin: adminPin
      });
      const data = await api("/api/wifi", { method: "POST", body });
      setMessage(data.message);
      window.setTimeout(refreshStatus, 3000);
    }

    async function openApp() {
      const data = await api("/api/open-app", { method: "POST" });
      setMessage(data.message);
    }

    els.scan.addEventListener("click", scanNetworks);
    els.connect.addEventListener("click", connectWifi);
    els.openApp.addEventListener("click", openApp);
    els.unlock.addEventListener("click", () => unlockAdmin().catch((error) => setLockMessage(error.message)));
    els.unlockPin.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        unlockAdmin().catch((error) => setLockMessage(error.message));
      }
    });

    initTouchKeyboard();
    refreshStatus().catch((error) => setMessage(error.message));
    window.setInterval(() => {
      if (adminPin) {
        refreshAdminStatus().catch(() => {});
      } else {
        refreshStatus().catch(() => {});
      }
    }, 10000);
  </script>
</body>
</html>
"""

UPDATE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stay Compass Update</title>
  <style>
    :root {
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #101820;
      color: #f7fbff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 32px;
    }
    main {
      width: min(760px, 100%);
      text-align: center;
    }
    h1 {
      margin: 0;
      font-size: clamp(32px, 6vw, 58px);
      line-height: 1.05;
      letter-spacing: 0;
    }
    p {
      margin: 18px auto 0;
      max-width: 560px;
      color: #c9d6df;
      font-size: 20px;
      line-height: 1.45;
    }
    .bar {
      width: 100%;
      height: 22px;
      margin-top: 38px;
      overflow: hidden;
      border-radius: 6px;
      background: #31404d;
      border: 1px solid #4f6070;
    }
    .fill {
      width: 3%;
      height: 100%;
      background: #57c4b8;
      transition: width 400ms ease;
    }
    .meta {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      margin-top: 14px;
      color: #dce8ef;
      font-weight: 800;
    }
    @media (max-width: 640px) {
      body { padding: 20px; }
      p { font-size: 17px; }
      .meta { display: block; text-align: left; }
      .meta span { display: block; margin-top: 8px; }
    }
  </style>
</head>
<body>
  <main>
    <h1>Updating Stay Compass</h1>
    <p id="message">Checking for the newest device software...</p>
    <div class="bar" aria-label="Update progress">
      <div id="fill" class="fill"></div>
    </div>
    <div class="meta">
      <span id="phase">Preparing</span>
      <span id="progress">0%</span>
    </div>
  </main>
  <script>
    async function refresh() {
      const response = await fetch("/api/update-status");
      const status = await response.json();
      const progress = Math.max(0, Math.min(100, status.progress || 0));

      document.querySelector("#fill").style.width = `${progress}%`;
      document.querySelector("#progress").textContent = `${progress}%`;
      document.querySelector("#phase").textContent = status.phase || "Updating";
      document.querySelector("#message").textContent = status.message || "Working...";
    }

    refresh().catch(() => {});
    window.setInterval(() => refresh().catch(() => {}), 1000);
  </script>
</body>
</html>
"""


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


def run_command(command, timeout=30, cwd=None):
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )


def has_network():
    try:
        socket.create_connection(
            (NETWORK_CHECK_HOST, NETWORK_CHECK_PORT),
            timeout=NETWORK_TIMEOUT_SECONDS,
        )
        return True
    except OSError:
        return False


def terminate_process(process):
    if process is None or process.poll() is not None:
        return

    process.terminate()

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def launch_chromium(url):
    log(f"Launching Chromium: {url}")

    return subprocess.Popen(
        [
            CHROMIUM_BIN,
            "--kiosk",
            "--noerrdialogs",
            "--disable-infobars",
            "--disable-session-crashed-bubble",
            url,
        ]
    )


def parse_nmcli_escaped_fields(line):
    fields = []
    current = []
    escaped = False

    for character in line:
        if escaped:
            current.append(character)
            escaped = False
            continue

        if character == "\\":
            escaped = True
            continue

        if character == ":":
            fields.append("".join(current))
            current = []
            continue

        current.append(character)

    fields.append("".join(current))
    return fields


def scan_wifi_networks():
    result = run_command(
        [
            NMCLI_BIN,
            "-t",
            "--escape",
            "yes",
            "-f",
            "SSID,SECURITY,SIGNAL",
            "dev",
            "wifi",
            "list",
            "--rescan",
            "yes",
        ],
        timeout=45,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to scan Wi-Fi networks.")

    networks = []
    seen_ssids = set()

    for line in result.stdout.splitlines():
        ssid, security, signal = (parse_nmcli_escaped_fields(line) + ["", "", ""])[:3]
        ssid = ssid.strip()

        if not ssid or ssid in seen_ssids:
            continue

        seen_ssids.add(ssid)
        networks.append(
            {
                "ssid": ssid,
                "security": security.strip(),
                "signal": signal.strip(),
            }
        )

    return networks


def connect_wifi(ssid, password):
    command = [NMCLI_BIN, "dev", "wifi", "connect", ssid]

    if password:
        command.extend(["password", password])

    result = run_command(command, timeout=60)

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to connect Wi-Fi.")


def valid_admin_pin(config, form):
    return bool(config.get("admin_pin")) and form.get("pin") == config.get("admin_pin")


def update_progress(state, phase, progress, message, error=None):
    state["update"] = {
        "phase": phase,
        "progress": progress,
        "message": message,
        "error": error,
        "updated_at": time.time(),
    }
    log(f"Update: {phase} {progress}% - {message}")


def get_update_config(config):
    return {
        "enabled": config.get("auto_update_on_boot", True),
        "repo_dir": config.get("update_repo_dir"),
        "remote": config.get("update_remote", "origin"),
        "branch": config.get("update_branch", "main"),
    }


def get_command_output(command_result):
    return (command_result.stdout or command_result.stderr).strip()


def find_available_update(config, state):
    update_config = get_update_config(config)

    if not update_config["enabled"]:
        update_progress(state, "Ready", 0, "Automatic update check is disabled.")
        return None

    repo_dir = update_config["repo_dir"]

    if not repo_dir or not (Path(repo_dir) / ".git").exists():
        update_progress(state, "Ready", 0, "No update source repository is configured.")
        return None

    update_progress(state, "Checking", 8, "Checking for device updates...")
    check_result = run_command([SUDO_BIN, UPDATE_HELPER, "check"], timeout=120)

    if check_result.returncode == 20:
        update_progress(state, "Ready", 0, "Device software is already current.")
        return None

    if check_result.returncode != 0:
        update_progress(
            state,
            "Ready",
            0,
            f"Update check failed: {get_command_output(check_result)}",
            error=get_command_output(check_result),
        )
        return None

    update_progress(state, "Available", 24, "A new device update is available.")
    return update_config


def apply_available_update(update_config, state):
    update_progress(state, "Downloading", 38, "Downloading the newest device software...")
    result = run_command(
        [SUDO_BIN, UPDATE_HELPER, "apply"],
        timeout=900,
    )

    if result.returncode != 0:
        message = get_command_output(result) or "Update helper failed."
        update_progress(state, "Failed", 100, message, error=message)
        return False

    update_progress(state, "Restarting", 100, "Update installed. Restarting Stay Compass...")
    time.sleep(2)
    terminate_process(state.get("chromium_process"))
    os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve())])
    return True


def maybe_update_on_boot(config, state):
    update_config = find_available_update(config, state)

    if not update_config:
        return False

    state["chromium_process"] = launch_chromium(f"http://{ADMIN_HOST}:{ADMIN_PORT}/updating")
    return apply_available_update(update_config, state)


def make_admin_handler(config, state):
    app_html = APP_HTML % {
        "pwa_url_json": json.dumps(config.get("pwa_url") or ""),
    }

    class AdminHandler(BaseHTTPRequestHandler):
        server_version = "StayCompassAdmin/0.1"

        def log_message(self, format, *args):
            log(f"Admin portal: {format % args}")

        def send_json(self, payload, status=HTTPStatus.OK):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def read_form(self):
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8")
            return {key: values[0] for key, values in parse_qs(body).items()}

        def do_GET(self):
            if self.path == "/app":
                body = app_html.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path == "/" or self.path == "/admin":
                body = ADMIN_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path == "/updating":
                body = UPDATE_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path == "/api/status":
                self.send_json(
                    {
                        "online": has_network(),
                    }
                )
                return

            if self.path == "/api/update-status":
                self.send_json(state.get("update", {}))
                return

            self.send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self):
            if self.path == "/api/unlock":
                form = self.read_form()

                if not valid_admin_pin(config, form):
                    self.send_json(
                        {"error": "Invalid admin PIN."},
                        status=HTTPStatus.UNAUTHORIZED,
                    )
                    return

                self.send_json({"message": "Admin mode unlocked."})
                return

            if self.path == "/api/admin-status":
                form = self.read_form()

                if not valid_admin_pin(config, form):
                    self.send_json(
                        {"error": "Invalid admin PIN."},
                        status=HTTPStatus.UNAUTHORIZED,
                    )
                    return

                self.send_json(
                    {
                        "hostname": socket.gethostname(),
                        "online": has_network(),
                        "pwa_url": config.get("pwa_url"),
                    }
                )
                return

            if self.path == "/api/networks":
                form = self.read_form()

                if not valid_admin_pin(config, form):
                    self.send_json(
                        {"error": "Invalid admin PIN."},
                        status=HTTPStatus.UNAUTHORIZED,
                    )
                    return

                try:
                    self.send_json({"networks": scan_wifi_networks()})
                except Exception as error:
                    self.send_json(
                        {"error": str(error)},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                return

            if self.path == "/api/wifi":
                form = self.read_form()

                if not valid_admin_pin(config, form):
                    self.send_json(
                        {"error": "Invalid admin PIN."},
                        status=HTTPStatus.UNAUTHORIZED,
                    )
                    return

                ssid = form.get("ssid", "").strip()

                if not ssid:
                    self.send_json(
                        {"error": "Choose a Wi-Fi network first."},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return

                try:
                    connect_wifi(ssid, form.get("password", ""))
                    self.send_json(
                        {
                            "message": (
                                "Wi-Fi connection saved. The kiosk will reopen "
                                "Stay Compass after the internet check passes."
                            )
                        }
                    )
                except Exception as error:
                    self.send_json(
                        {"error": str(error)},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                return

            if self.path == "/api/open-app":
                state["requested_mode"] = "app"
                self.send_json({"message": "Opening Stay Compass..."})
                return

            if self.path == "/api/open-admin":
                state["requested_mode"] = "admin"
                self.send_json({"message": "Opening admin mode..."})
                return

            self.send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    return AdminHandler


def start_admin_server(config, state):
    handler = make_admin_handler(config, state)
    server = ThreadingHTTPServer((ADMIN_HOST, ADMIN_PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log(f"Admin portal listening at http://{ADMIN_HOST}:{ADMIN_PORT}/")
    return server


def main():
    setup_logging()
    config = load_config()
    pwa_url = config.get("pwa_url")
    admin_url = f"http://{ADMIN_HOST}:{ADMIN_PORT}/"
    app_url = f"http://{ADMIN_HOST}:{ADMIN_PORT}/app"
    state = {
        "chromium_process": None,
        "requested_mode": None,
        "update": {
            "phase": "Preparing",
            "progress": 0,
            "message": "Preparing update check...",
            "error": None,
            "updated_at": time.time(),
        },
    }

    log("===================================")
    log(" Stay Compass Device Service")
    log(" Version 0.1.0")
    log("===================================")
    log(f"PWA URL: {pwa_url}")
    log("Starting device service...")

    start_admin_server(config, state)

    chromium_process = None
    current_mode = None
    offline_since = None
    update_checked = False

    try:
        while True:
            online = has_network()
            target_mode = "app"
            forced_mode = None

            if not online:
                if offline_since is None:
                    offline_since = time.monotonic()

                if time.monotonic() - offline_since >= OFFLINE_ADMIN_DELAY_SECONDS:
                    target_mode = "admin"
                elif current_mode is None:
                    log("Network offline. Waiting before admin mode...")
                    time.sleep(5)
                    continue
            else:
                offline_since = None

                if not update_checked:
                    update_checked = True
                    maybe_update_on_boot(config, state)
                    chromium_process = state.get("chromium_process")
                    current_mode = "update" if chromium_process else None

            if state.get("requested_mode") in {"app", "admin"}:
                forced_mode = state["requested_mode"]
                target_mode = forced_mode
                state["requested_mode"] = None

            target_url = app_url if target_mode == "app" else admin_url

            if current_mode != target_mode or forced_mode == target_mode:
                if target_mode == "admin":
                    log("Opening admin mode.")
                else:
                    log("Opening Stay Compass app.")

                terminate_process(chromium_process)
                chromium_process = launch_chromium(target_url)
                state["chromium_process"] = chromium_process
                current_mode = target_mode

            if chromium_process.poll() is not None:
                log("Chromium exited. Restarting current mode...")
                chromium_process = launch_chromium(target_url)
                state["chromium_process"] = chromium_process

            time.sleep(5)

    except KeyboardInterrupt:
        log("Stay Compass Device Service stopped.")

        log("Stopping Chromium...")
        terminate_process(chromium_process)


if __name__ == "__main__":
    main()
