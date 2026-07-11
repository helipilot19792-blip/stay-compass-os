#!/usr/bin/env python3

"""
Stay Compass Device Service
"""

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"

LOG_FILE = "/tmp/stay-compass-device.log"
NETWORK_CHECK_HOST = "1.1.1.1"
NETWORK_CHECK_PORT = 53
NETWORK_TIMEOUT_SECONDS = 3
OFFLINE_ADMIN_DELAY_SECONDS = 20
OFFLINE_RECOVERY_STABLE_SECONDS = 6
OFFLINE_RECOVERY_SUCCESS_STREAK = 3
OFFLINE_RECOVERY_IDLE_GRACE_SECONDS = 8
OFFLINE_RECOVERY_POST_CONNECT_DELAY_SECONDS = 3
ADMIN_HOST = "127.0.0.1"
ADMIN_PORT = 8750
UPDATE_HELPER = "/opt/stay-compass/run-update.sh"
ADMIN_INACTIVITY_TIMEOUT_SECONDS = 30
ADMIN_LOCKOUT_SECONDS = 5 * 60
ADMIN_EXTENSION_DIR = "/opt/stay-compass/browser-extension/admin-hotspot"

CHROMIUM_BIN = "/usr/bin/chromium"
NMCLI_BIN = "/usr/bin/nmcli"
SUDO_BIN = "/usr/bin/sudo"
XRANDR_BIN = "/usr/bin/xrandr"
XINPUT_BIN = "/usr/bin/xinput"
COMPASS_USER = "compass"
DISPLAY_NAME = ":0"
MIN_BRIGHTNESS = 0.05
MAX_BRIGHTNESS = 1.0
SERVICE_VERSION = "0.1.0"
RECENT_LOGS = deque(maxlen=200)

DISPLAY_DEFAULTS = {
    "night_mode_enabled": False,
    "night_start": "21:00",
    "night_end": "07:00",
    "day_brightness": 1.0,
    "night_brightness": 0.3,
    "wake_brightness": 1.0,
    "wake_duration_seconds": 120,
    "xrandr_output": "HDMI-1",
}

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
    .pin-input-row {
      display: flex;
      gap: 10px;
      align-items: stretch;
    }
    .pin-input-row input {
      flex: 1 1 auto;
      min-width: 0;
    }
    .pin-toggle {
      flex: 0 0 auto;
      min-width: 84px;
      padding-inline: 16px;
      touch-action: manipulation;
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
          <div class="pin-input-row">
            <input id="unlockPin" type="password" inputmode="numeric" autocomplete="off">
            <button id="toggleUnlockPin" class="secondary pin-toggle" type="button" aria-pressed="false">Show</button>
          </div>
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

    <section id="displaySection" class="hidden">
      <h2>Display Settings</h2>
      <div class="grid">
        <label>
          <span>Night Mode Enabled</span>
          <select id="displayNightModeEnabled">
            <option value="true">Enabled</option>
            <option value="false">Disabled</option>
          </select>
        </label>
        <label>
          Night Start Time
          <input id="displayNightStart" type="time">
        </label>
        <label>
          Night End Time
          <input id="displayNightEnd" type="time">
        </label>
        <label>
          Day Brightness (%)
          <input id="displayDayBrightness" type="number" min="5" max="100" step="1">
        </label>
        <label>
          Night Brightness (%)
          <input id="displayNightBrightness" type="number" min="5" max="100" step="1">
        </label>
        <label>
          Wake Brightness (%)
          <input id="displayWakeBrightness" type="number" min="5" max="100" step="1">
        </label>
        <label>
          Wake Duration (seconds)
          <input id="displayWakeDurationSeconds" type="number" min="1" max="3600" step="1">
        </label>
        <label>
          xrandr Output
          <input id="displayXrandrOutput" type="text" autocomplete="off" placeholder="HDMI-1">
        </label>
      </div>
      <div class="actions">
        <button id="saveDisplaySettings" type="button">Save</button>
        <button id="previewNightMode" class="secondary" type="button">Preview Night Mode</button>
        <button id="restoreFullBrightness" class="secondary" type="button">Restore Full Brightness</button>
      </div>
      <div id="displayMessage" class="message"></div>
      <div id="displayWarning" class="message"></div>
    </section>
  </main>
  <div id="touchKeyboard" class="touch-keyboard hidden" aria-label="Touch keyboard"></div>
  <script>
    const els = {
      appUrl: document.querySelector("#appUrl"),
      connect: document.querySelector("#connect"),
      diagnosticsSection: document.querySelector("#diagnosticsSection"),
      displayDayBrightness: document.querySelector("#displayDayBrightness"),
      displayMessage: document.querySelector("#displayMessage"),
      displayNightBrightness: document.querySelector("#displayNightBrightness"),
      displayNightEnd: document.querySelector("#displayNightEnd"),
      displayNightModeEnabled: document.querySelector("#displayNightModeEnabled"),
      displayNightStart: document.querySelector("#displayNightStart"),
      displaySection: document.querySelector("#displaySection"),
      displayWarning: document.querySelector("#displayWarning"),
      displayWakeBrightness: document.querySelector("#displayWakeBrightness"),
      displayWakeDurationSeconds: document.querySelector("#displayWakeDurationSeconds"),
      displayXrandrOutput: document.querySelector("#displayXrandrOutput"),
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
      toggleUnlockPin: document.querySelector("#toggleUnlockPin"),
      unlock: document.querySelector("#unlock"),
      unlockPin: document.querySelector("#unlockPin"),
      wifiSection: document.querySelector("#wifiSection"),
      previewNightMode: document.querySelector("#previewNightMode"),
      restoreFullBrightness: document.querySelector("#restoreFullBrightness"),
      saveDisplaySettings: document.querySelector("#saveDisplaySettings")
    };
    const TEXT_INPUT_SELECTOR = 'input[type="text"], input[type="password"], input[type="search"], input[type="email"], input[type="url"], input[type="tel"], input:not([type]), textarea';
    const KEYBOARD_MARGIN = 16;
    const ADMIN_ACTIVITY_PING_MS = 5000;
    const ADMIN_PIN_GUARD_MS = 700;
    const LOCAL_ADMIN_API_BASE = "http://127.0.0.1:8750";

    let adminPin = "";
    let lastAdminActivityPingAt = 0;
    let unlockPinReadyAt = 0;
    let unlockPinVisible = false;

    function setMessage(text) {
      els.message.textContent = text;
    }

    function setLockMessage(text) {
      els.lockMessage.textContent = text;
    }

    function setDisplayMessage(text) {
      els.displayMessage.textContent = text;
    }

    function setDisplayWarning(text) {
      els.displayWarning.textContent = text || "";
      els.displayWarning.style.color = text ? "#8a2d16" : "#155c5f";
    }

    function syncUnlockPinToggle() {
      els.unlockPin.type = unlockPinVisible ? "text" : "password";
      els.toggleUnlockPin.textContent = unlockPinVisible ? "Hide" : "Show";
      els.toggleUnlockPin.setAttribute("aria-pressed", unlockPinVisible ? "true" : "false");
      els.toggleUnlockPin.setAttribute("aria-label", unlockPinVisible ? "Hide PIN" : "Show PIN");
    }

    function prepareUnlockPinInput() {
      unlockPinReadyAt = Date.now() + ADMIN_PIN_GUARD_MS;
      unlockPinVisible = false;
      syncUnlockPinToggle();
      els.unlockPin.value = "";
      window.setTimeout(() => {
        els.unlockPin.value = "";
        els.unlockPin.focus();
      }, ADMIN_PIN_GUARD_MS);
    }

    async function api(path, options = {}) {
      let response;
      try {
        response = await fetch(path, options);
      } catch (error) {
        throw new Error(`Failed to fetch ${path}: ${error.message}`);
      }

      const responseText = await response.text();
      let data = {};

      if (responseText) {
        try {
          data = JSON.parse(responseText);
        } catch (error) {
          data = { raw: responseText };
        }
      }

      if (!response.ok) {
        const details = data.error || data.message || data.raw || response.statusText || "Request failed";
        throw new Error(`${response.status} ${details}`);
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
      setDisplayWarning(status.display_warning || "");
    }

    function noteAdminActivity(force = false) {
      const now = Date.now();
      if (!force && now - lastAdminActivityPingAt < ADMIN_ACTIVITY_PING_MS) {
        return;
      }
      lastAdminActivityPingAt = now;
      fetch("/api/activity", { method: "POST" }).catch(() => {});
    }

    function showAdmin() {
      els.lockSection.classList.add("hidden");
      els.wifiSection.classList.remove("hidden");
      els.diagnosticsSection.classList.remove("hidden");
      els.displaySection.classList.remove("hidden");
      els.screenDescription.textContent = "Device setup, Wi-Fi recovery, and local diagnostics.";
      hideTouchKeyboard();
      noteAdminActivity(true);
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
      await loadDisplaySettings();
      await scanNetworks();
    }

    function brightnessToPercent(value) {
      return Math.round(Number(value || 0) * 100);
    }

    function percentToBrightness(value) {
      const numeric = Number(value || 0);
      return numeric / 100;
    }

    function fillDisplaySettings(settings) {
      els.displayNightModeEnabled.value = settings.night_mode_enabled ? "true" : "false";
      els.displayNightStart.value = settings.night_start || "21:00";
      els.displayNightEnd.value = settings.night_end || "07:00";
      els.displayDayBrightness.value = brightnessToPercent(settings.day_brightness);
      els.displayNightBrightness.value = brightnessToPercent(settings.night_brightness);
      els.displayWakeBrightness.value = brightnessToPercent(settings.wake_brightness);
      els.displayWakeDurationSeconds.value = settings.wake_duration_seconds ?? 120;
      els.displayXrandrOutput.value = settings.xrandr_output || "HDMI-1";
    }

    function readDisplaySettingsPayload() {
      return {
        pin: adminPin,
        display: {
          night_mode_enabled: els.displayNightModeEnabled.value === "true",
          night_start: els.displayNightStart.value,
          night_end: els.displayNightEnd.value,
          day_brightness: percentToBrightness(els.displayDayBrightness.value),
          night_brightness: percentToBrightness(els.displayNightBrightness.value),
          wake_brightness: percentToBrightness(els.displayWakeBrightness.value),
          wake_duration_seconds: Number(els.displayWakeDurationSeconds.value),
          xrandr_output: els.displayXrandrOutput.value
        }
      };
    }

    async function loadDisplaySettings() {
      const data = await api(`${LOCAL_ADMIN_API_BASE}/api/display-settings?pin=${encodeURIComponent(adminPin)}`);
      fillDisplaySettings(data.display);
      setDisplayWarning(data.warning || "");
      setDisplayMessage(data.message || "");
    }

    async function saveDisplaySettings() {
      setDisplayMessage("Saving display settings...");
      const data = await api(`${LOCAL_ADMIN_API_BASE}/api/display-settings`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(readDisplaySettingsPayload())
      });
      fillDisplaySettings(data.display);
      setDisplayWarning(data.warning || "");
      setDisplayMessage(data.message || "Display settings saved.");
      await refreshAdminStatus();
    }

    async function previewNightMode() {
      setDisplayMessage("Applying night preview...");
      const body = new URLSearchParams({ pin: adminPin });
      const data = await api(`${LOCAL_ADMIN_API_BASE}/api/display-preview-night`, { method: "POST", body });
      setDisplayWarning(data.warning || "");
      setDisplayMessage(data.message || "Night mode preview applied.");
      await refreshAdminStatus();
    }

    async function restoreFullBrightness() {
      setDisplayMessage("Restoring full brightness...");
      const body = new URLSearchParams({ pin: adminPin });
      const data = await api(`${LOCAL_ADMIN_API_BASE}/api/display-restore-brightness`, { method: "POST", body });
      setDisplayWarning(data.warning || "");
      setDisplayMessage(data.message || "Full brightness restored.");
      await refreshAdminStatus();
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
    els.saveDisplaySettings.addEventListener("click", (event) => {
      event.preventDefault();
      saveDisplaySettings().catch((error) => setDisplayMessage(error.message));
    });
    els.previewNightMode.addEventListener("click", () => previewNightMode().catch((error) => setDisplayMessage(error.message)));
    els.restoreFullBrightness.addEventListener("click", () => restoreFullBrightness().catch((error) => setDisplayMessage(error.message)));
    els.unlock.addEventListener("click", () => unlockAdmin().catch((error) => setLockMessage(error.message)));
    els.toggleUnlockPin.addEventListener("click", () => {
      unlockPinVisible = !unlockPinVisible;
      syncUnlockPinToggle();
      if (Date.now() >= unlockPinReadyAt) {
        els.unlockPin.focus();
      }
    });
    els.unlockPin.addEventListener("keydown", (event) => {
      if (Date.now() < unlockPinReadyAt) {
        event.preventDefault();
        return;
      }
      if (event.key === "Enter") {
        unlockAdmin().catch((error) => setLockMessage(error.message));
      }
    });
    els.unlockPin.addEventListener("beforeinput", (event) => {
      if (Date.now() < unlockPinReadyAt) {
        event.preventDefault();
      }
    });
    els.unlockPin.addEventListener("input", () => {
      if (Date.now() < unlockPinReadyAt) {
        els.unlockPin.value = "";
      }
    });

    ["pointerdown", "keydown", "input", "focusin"].forEach((eventName) => {
      document.addEventListener(eventName, () => noteAdminActivity(), true);
    });

    initTouchKeyboard();
    prepareUnlockPinInput();
    noteAdminActivity(true);
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

ADMIN_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stay Compass Device Settings</title>
  <style>
    :root {
      --keyboard-height: 0px;
      color-scheme: light;
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top right, rgba(19, 93, 95, 0.12), transparent 24rem),
        linear-gradient(180deg, #f2f6f7 0%, #e9eff0 100%);
      color: #162126;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      padding: 24px;
      overflow-x: hidden;
    }
    body.keyboard-open { padding-bottom: calc(var(--keyboard-height) + 24px); }
    .shell {
      width: min(1220px, 100%);
      margin: 0 auto;
      background: rgba(255, 255, 255, 0.96);
      border: 1px solid #d8e1e3;
      border-radius: 20px;
      box-shadow: 0 26px 80px rgba(22, 33, 38, 0.12);
      overflow: hidden;
      backdrop-filter: blur(14px);
    }
    .hero {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: start;
      padding: 28px;
      background: linear-gradient(135deg, #0f4f52 0%, #1b6f70 100%);
      color: #ffffff;
    }
    h1, h2, h3, h4, p { margin: 0; }
    h1 { font-size: 30px; line-height: 1.08; }
    h2 { font-size: 22px; line-height: 1.12; }
    h3 { font-size: 17px; line-height: 1.18; }
    p, li { color: #53616f; }
    .hero p, .hero .status-chip, .hero .pill { color: rgba(255, 255, 255, 0.9); }
    .hero-status {
      display: grid;
      gap: 10px;
      min-width: 220px;
      justify-items: end;
    }
    .status-chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.16);
      font-weight: 800;
    }
    .content {
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr);
      min-height: 680px;
    }
    .sidebar {
      border-right: 1px solid #e5ecee;
      background: #f8fbfb;
      padding: 20px;
    }
    .nav-list {
      display: grid;
      gap: 10px;
    }
    .nav-button {
      width: 100%;
      text-align: left;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid transparent;
      background: transparent;
      color: #29424a;
      font-weight: 800;
    }
    .nav-button.active {
      background: #e0efef;
      border-color: #b8d7d8;
      color: #0f4f52;
    }
    .sidebar-note {
      margin-top: 18px;
      padding: 14px;
      border-radius: 14px;
      background: #edf4f4;
      color: #466068;
      font-size: 13px;
      line-height: 1.45;
    }
    .main-panel {
      padding: 22px;
      display: grid;
      gap: 18px;
      align-content: start;
    }
    .lock-panel, .section-panel {
      background: #ffffff;
      border: 1px solid #dde6e8;
      border-radius: 18px;
      padding: 24px;
      box-shadow: 0 12px 34px rgba(24, 38, 45, 0.06);
    }
    .lock-panel {
      max-width: 760px;
      margin: 28px auto;
    }
    .locked-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 190px;
      gap: 14px;
      align-items: end;
      margin-top: 22px;
    }
    .section-header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
      margin-bottom: 18px;
    }
    .section-actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .card-grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 16px;
    }
    .card {
      grid-column: span 12;
      border: 1px solid #e1e8ea;
      border-radius: 16px;
      background: #fbfcfc;
      padding: 18px;
      display: grid;
      gap: 12px;
    }
    .card.half { grid-column: span 6; }
    .card.third { grid-column: span 4; }
    .card.two-third { grid-column: span 8; }
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .metric {
      padding: 14px;
      border-radius: 14px;
      background: #ffffff;
      border: 1px solid #e4ecee;
    }
    .metric .label {
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #69808a;
    }
    .metric .value {
      margin-top: 8px;
      font-size: 21px;
      font-weight: 800;
      color: #13272e;
      word-break: break-word;
    }
    .stack {
      display: grid;
      gap: 14px;
    }
    .field-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      align-items: end;
    }
    label {
      display: grid;
      gap: 7px;
      font-size: 13px;
      font-weight: 800;
      color: #2c4047;
    }
    input, select, textarea {
      width: 100%;
      min-height: 48px;
      padding: 11px 13px;
      border-radius: 12px;
      border: 1px solid #bfccd1;
      background: #ffffff;
      color: #162126;
      font: inherit;
      scroll-margin-bottom: calc(var(--keyboard-height) + 24px);
    }
    textarea {
      min-height: 200px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 13px;
    }
    button {
      min-height: 48px;
      border: 0;
      border-radius: 12px;
      padding: 11px 16px;
      font: inherit;
      font-weight: 800;
      cursor: pointer;
      background: #155c5f;
      color: #ffffff;
      touch-action: manipulation;
    }
    button.secondary {
      background: #e8eef0;
      color: #263740;
    }
    button.warning {
      background: #8a2d16;
    }
    button:disabled {
      cursor: not-allowed;
      opacity: 0.52;
    }
    .pin-input-row, .inline-actions {
      display: flex;
      gap: 10px;
      align-items: stretch;
      flex-wrap: wrap;
    }
    .pin-input-row input, .inline-actions > *:first-child {
      flex: 1 1 auto;
      min-width: 0;
    }
    .pin-toggle {
      min-width: 92px;
    }
    .checkbox-row {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      font-size: 13px;
      font-weight: 800;
      color: #2c4047;
    }
    .checkbox-row input {
      width: auto;
      min-height: 18px;
      margin: 0;
      padding: 0;
    }
    .message {
      min-height: 22px;
      font-weight: 800;
      color: #155c5f;
    }
    .message.error { color: #8a2d16; }
    .helper {
      font-size: 13px;
      color: #667983;
      line-height: 1.45;
    }
    .list {
      display: grid;
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .list-item {
      padding: 12px 14px;
      border-radius: 12px;
      background: #ffffff;
      border: 1px solid #e3eaec;
    }
    .log-box {
      background: #0f1b20;
      color: #d4ebed;
      border-radius: 14px;
      padding: 16px;
      min-height: 220px;
      overflow: auto;
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 13px;
      line-height: 1.45;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .kv {
      display: grid;
      grid-template-columns: max-content minmax(0, 1fr);
      gap: 8px 16px;
      align-items: start;
    }
    .kv dt {
      font-weight: 800;
      color: #31444b;
    }
    .kv dd {
      margin: 0;
      color: #53616f;
      word-break: break-word;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 10px;
      border-radius: 999px;
      background: #edf5f5;
      color: #0f4f52;
      font-size: 12px;
      font-weight: 800;
    }
    .hidden { display: none !important; }
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
      width: min(1220px, 100%);
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
      border-radius: 10px;
      font-size: 18px;
    }
    .keyboard-key.wide { flex-grow: 1.6; }
    .keyboard-key.extra-wide { flex-grow: 4; }
    .keyboard-key.active {
      background: #f0b429;
      color: #101820;
    }
    @media (max-width: 980px) {
      .content { grid-template-columns: 1fr; }
      .sidebar {
        border-right: 0;
        border-bottom: 1px solid #e5ecee;
      }
      .nav-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 760px) {
      body { padding: 12px; }
      body.keyboard-open { padding-bottom: calc(var(--keyboard-height) + 12px); }
      .hero, .main-panel, .sidebar, .lock-panel, .section-panel { padding: 18px; }
      .hero, .section-header, .locked-grid, .field-grid {
        grid-template-columns: 1fr;
        display: grid;
      }
      .hero-status {
        justify-items: start;
        min-width: 0;
      }
      .nav-list { grid-template-columns: 1fr; }
      .metric-grid { grid-template-columns: 1fr; }
      .card.half, .card.third, .card.two-third { grid-column: span 12; }
      .keyboard-key {
        min-height: 42px;
        font-size: 16px;
        padding: 7px 8px;
      }
      .touch-keyboard { padding: 10px 8px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="hero">
      <div class="stack">
        <div>
          <h1>Stay Compass Device Settings</h1>
          <p id="screenDescription">Local admin only. Use this page for device health, kiosk settings, Wi-Fi recovery, updates, and diagnostics.</p>
        </div>
        <div class="inline-actions">
          <span id="modePill" class="pill">Mode: Locked</span>
          <span id="versionPill" class="pill">Version: -</span>
        </div>
      </div>
      <div class="hero-status">
        <div id="networkStatus" class="status-chip">Checking network...</div>
        <button id="exitAdminMode" class="secondary" type="button">Return to Stay Compass</button>
        <div id="globalNotice" class="message"></div>
      </div>
    </div>
    <div id="lockSection" class="lock-panel">
      <h2>Staff Access</h2>
      <p>Enter the admin PIN to open the local Stay Compass OS device settings interface.</p>
      <div class="locked-grid">
        <label>
          Admin PIN
          <div class="pin-input-row">
            <input id="unlockPin" type="password" inputmode="numeric" autocomplete="off">
            <button id="toggleUnlockPin" class="secondary pin-toggle" type="button" aria-pressed="false">Show</button>
          </div>
        </label>
        <button id="unlock" type="button">Unlock</button>
      </div>
      <div class="helper">The PIN field stays empty on load, ignores input for the first 700ms, and focuses only after that delay.</div>
      <div id="lockMessage" class="message"></div>
    </div>
    <div id="adminShell" class="content hidden">
      <aside class="sidebar">
        <div class="nav-list">
          <button class="nav-button active" data-section="dashboard" type="button">Dashboard / Health</button>
          <button class="nav-button" data-section="settings" type="button">Stay Compass Settings</button>
          <button class="nav-button" data-section="display" type="button">Display</button>
          <button class="nav-button" data-section="wifi" type="button">Wi-Fi</button>
          <button class="nav-button" data-section="updates" type="button">Updates</button>
          <button class="nav-button" data-section="diagnostics" type="button">Diagnostics</button>
          <button class="nav-button" data-section="advanced" type="button">Advanced</button>
        </div>
        <div class="sidebar-note">This interface is local to <strong>127.0.0.1:8750</strong>. None of the device health or settings panels are exposed on the guest PWA.</div>
      </aside>
      <main class="main-panel">
        <section id="section-dashboard" class="section-panel">
          <div class="section-header">
            <div class="stack">
              <h2>Dashboard / Health</h2>
              <p>Quick status for the device, kiosk app, connectivity, and the most recent local warnings.</p>
            </div>
            <div class="section-actions">
              <button id="refreshOverview" class="secondary" type="button">Refresh</button>
            </div>
          </div>
          <div id="dashboardMetrics" class="metric-grid"></div>
          <div class="card-grid">
            <div class="card half">
              <h3>Software</h3>
              <dl class="kv">
                <dt>Version</dt><dd id="healthVersion">-</dd>
                <dt>PWA URL</dt><dd id="healthPwaUrl">-</dd>
                <dt>Chromium</dt><dd id="healthChromium">-</dd>
                <dt>Pairing / Token</dt><dd id="healthPairing">-</dd>
                <dt>Last update</dt><dd id="healthLastUpdate">-</dd>
              </dl>
            </div>
            <div class="card half">
              <h3>System</h3>
              <dl class="kv">
                <dt>Device</dt><dd id="healthDeviceName">-</dd>
                <dt>Internet</dt><dd id="healthInternet">-</dd>
                <dt>IP address</dt><dd id="healthIp">-</dd>
                <dt>Wi-Fi SSID</dt><dd id="healthSsid">-</dd>
                <dt>Uptime</dt><dd id="healthUptime">-</dd>
              </dl>
            </div>
            <div class="card half">
              <h3>Resources</h3>
              <dl class="kv">
                <dt>Disk usage</dt><dd id="healthDisk">-</dd>
                <dt>Memory usage</dt><dd id="healthMemory">-</dd>
                <dt>CPU temperature</dt><dd id="healthTemp">-</dd>
              </dl>
            </div>
            <div class="card half">
              <h3>Recent Issues</h3>
              <div class="stack">
                <div><strong>Last warning:</strong> <span id="healthWarning">None</span></div>
                <div><strong>Last error:</strong> <span id="healthError">None</span></div>
                <div><strong>Display warning:</strong> <span id="healthDisplayWarning">None</span></div>
              </div>
            </div>
          </div>
        </section>
        <section id="section-settings" class="section-panel hidden">
          <div class="section-header">
            <div class="stack">
              <h2>Stay Compass Settings</h2>
              <p>Local kiosk configuration for this device only.</p>
            </div>
          </div>
          <div class="card-grid">
            <div class="card two-third">
              <h3>Stay Compass App</h3>
              <div class="field-grid">
                <label>
                  PWA URL
                  <input id="settingsPwaUrl" type="url" autocomplete="off" placeholder="https://example.com/compass/">
                </label>
                <label>
                  Admin timeout seconds
                  <input id="settingsAdminTimeout" type="number" disabled>
                </label>
              </div>
              <div class="helper">The local safety timeout remains fixed at 30 seconds in this build.</div>
              <div class="inline-actions">
                <button id="saveSettings" type="button">Save Settings</button>
                <button id="returnToKiosk" class="secondary" type="button">Return to Kiosk</button>
                <button id="restartChromiumFromSettings" class="secondary" type="button">Restart App / Chromium</button>
              </div>
              <div id="settingsMessage" class="message"></div>
            </div>
            <div class="card third">
              <h3>Admin PIN</h3>
              <div class="stack">
                <label>
                  New PIN
                  <input id="newAdminPin" type="password" autocomplete="new-password">
                </label>
                <label>
                  Confirm new PIN
                  <input id="confirmAdminPin" type="password" autocomplete="new-password">
                </label>
                <button id="saveAdminPin" type="button">Change PIN</button>
                <div id="pinMessage" class="message"></div>
              </div>
            </div>
          </div>
        </section>
        <section id="section-display" class="section-panel hidden">
          <div class="section-header">
            <div class="stack">
              <h2>Display Settings</h2>
              <p>Night mode, brightness, and wake behavior for the local kiosk display.</p>
            </div>
          </div>
          <div class="card">
            <div class="field-grid">
              <label>
                Night mode enabled
                <select id="displayNightModeEnabled">
                  <option value="true">Enabled</option>
                  <option value="false">Disabled</option>
                </select>
              </label>
              <label>
                Night start
                <input id="displayNightStart" type="time">
              </label>
              <label>
                Night end
                <input id="displayNightEnd" type="time">
              </label>
              <label>
                Day brightness (%)
                <input id="displayDayBrightness" type="number" min="5" max="100" step="1">
              </label>
              <label>
                Night brightness (%)
                <input id="displayNightBrightness" type="number" min="5" max="100" step="1">
              </label>
              <label>
                Wake brightness (%)
                <input id="displayWakeBrightness" type="number" min="5" max="100" step="1">
              </label>
              <label>
                Wake duration (seconds)
                <input id="displayWakeDurationSeconds" type="number" min="1" max="3600" step="1">
              </label>
              <label>
                xrandr output
                <input id="displayXrandrOutput" type="text" autocomplete="off" placeholder="HDMI-1">
              </label>
            </div>
            <div class="inline-actions">
              <button id="saveDisplaySettings" type="button">Save Display Settings</button>
              <button id="previewNightMode" class="secondary" type="button">Preview Night Mode</button>
              <button id="restoreFullBrightness" class="secondary" type="button">Restore Full Brightness</button>
            </div>
            <div id="displayMessage" class="message"></div>
            <div id="displayWarning" class="message"></div>
          </div>
        </section>
        <section id="section-wifi" class="section-panel hidden">
          <div class="section-header">
            <div class="stack">
              <h2>Wi-Fi</h2>
              <p>Recover connectivity without leaving the local admin device settings page.</p>
            </div>
          </div>
          <div class="card">
            <div class="field-grid">
              <div class="stack">
                <div><strong>Current Wi-Fi:</strong> <span id="activeWifiSsid">Unavailable</span></div>
                <div class="helper">Disconnecting Wi-Fi may immediately terminate this SSH or admin session.</div>
              </div>
              <label>
                Network
                <select id="ssid"></select>
              </label>
              <div class="stack">
                <button id="scan" class="secondary" type="button">Scan Networks</button>
                <div class="helper">This keeps the existing local Wi-Fi workflow intact.</div>
              </div>
              <div class="stack">
                <label>
                  Wi-Fi password
                  <input id="password" type="password" autocomplete="current-password">
                </label>
                <label class="checkbox-row">
                  <input id="toggleWifiPassword" type="checkbox">
                  <span>Show password</span>
                </label>
              </div>
            </div>
            <div class="inline-actions">
              <button id="connect" type="button">Connect Wi-Fi</button>
              <button id="disconnectWifi" class="secondary" type="button">Disconnect Wi-Fi</button>
            </div>
            <div id="wifiMessage" class="message"></div>
          </div>
        </section>
        <section id="section-updates" class="section-panel hidden">
          <div class="section-header">
            <div class="stack">
              <h2>Updates</h2>
              <p>Surface the existing device update status and helper actions without rewriting OTA behavior.</p>
            </div>
          </div>
          <div class="card-grid">
            <div class="card half">
              <h3>Software Status</h3>
              <dl class="kv">
                <dt>Current version</dt><dd id="updateVersion">-</dd>
                <dt>Phase</dt><dd id="updatePhase">-</dd>
                <dt>Last status</dt><dd id="updateMessage">-</dd>
                <dt>Last check</dt><dd id="updateCheckedAt">-</dd>
              </dl>
            </div>
            <div class="card half">
              <h3>Update Actions</h3>
              <div class="stack">
                <div class="inline-actions">
                  <button id="checkUpdates" type="button">Check for Updates</button>
                  <button id="installUpdate" class="secondary" type="button">Install Update</button>
                </div>
                <div class="helper" id="updateActionHint">Local update controls appear only when the current device configuration supports them.</div>
                <div id="updatesMessage" class="message"></div>
              </div>
            </div>
          </div>
        </section>
        <section id="section-diagnostics" class="section-panel hidden">
          <div class="section-header">
            <div class="stack">
              <h2>Diagnostics</h2>
              <p>Recent device log output, service state, warnings, and a copyable diagnostics bundle.</p>
            </div>
            <div class="section-actions">
              <button id="refreshDiagnostics" class="secondary" type="button">Refresh Diagnostics</button>
              <button id="copyDiagnostics" class="secondary" type="button">Copy Diagnostics</button>
            </div>
          </div>
          <div class="card-grid">
            <div class="card half">
              <h3>Current State</h3>
              <dl class="kv">
                <dt>Mode</dt><dd id="diagMode">-</dd>
                <dt>Service uptime</dt><dd id="diagServiceUptime">-</dd>
                <dt>Display warning</dt><dd id="diagDisplayWarning">-</dd>
                <dt>Last update status</dt><dd id="diagLastUpdate">-</dd>
              </dl>
            </div>
            <div class="card half">
              <h3>Warnings / Errors</h3>
              <ul id="diagIssues" class="list"></ul>
            </div>
            <div class="card">
              <h3>Recent Device Log</h3>
              <div id="diagLog" class="log-box">Loading...</div>
            </div>
            <div class="card">
              <h3>Diagnostics Text</h3>
              <textarea id="diagnosticsText" readonly></textarea>
              <div id="diagnosticsMessage" class="message"></div>
            </div>
          </div>
        </section>
        <section id="section-advanced" class="section-panel hidden">
          <div class="section-header">
            <div class="stack">
              <h2>Advanced</h2>
              <p>High-impact local actions with confirmation prompts.</p>
            </div>
          </div>
          <div class="card-grid">
            <div class="card third">
              <h3>Restart Chromium / App</h3>
              <p>Restarts the local Chromium session and reopens the current local mode.</p>
              <button id="advancedRestartChromium" type="button">Restart Chromium / App</button>
            </div>
            <div class="card third">
              <h3>Reboot Device</h3>
              <p>Available only when this local build is granted a safe reboot path.</p>
              <button id="advancedReboot" class="warning" type="button" disabled>Reboot Device</button>
            </div>
            <div class="card third">
              <h3>Shutdown Device</h3>
              <p>Available only when a safe local shutdown path exists for the service user.</p>
              <button id="advancedShutdown" class="warning" type="button" disabled>Shutdown Device</button>
            </div>
            <div class="card">
              <h3>Factory Reset</h3>
              <p>This is a placeholder only. Factory reset is not implemented in the local admin service.</p>
              <button id="advancedFactoryReset" class="secondary" type="button" disabled>Factory Reset (Not Implemented)</button>
              <div id="advancedMessage" class="message"></div>
            </div>
          </div>
        </section>
      </main>
    </div>
  </div>
  <div id="touchKeyboard" class="touch-keyboard hidden" aria-label="Touch keyboard"></div>
  <script>
    const els = {
      adminShell: document.querySelector("#adminShell"),
      advancedMessage: document.querySelector("#advancedMessage"),
      advancedRestartChromium: document.querySelector("#advancedRestartChromium"),
      confirmAdminPin: document.querySelector("#confirmAdminPin"),
      connect: document.querySelector("#connect"),
      copyDiagnostics: document.querySelector("#copyDiagnostics"),
      dashboardMetrics: document.querySelector("#dashboardMetrics"),
      diagnosticsMessage: document.querySelector("#diagnosticsMessage"),
      diagnosticsText: document.querySelector("#diagnosticsText"),
      diagDisplayWarning: document.querySelector("#diagDisplayWarning"),
      diagIssues: document.querySelector("#diagIssues"),
      diagLastUpdate: document.querySelector("#diagLastUpdate"),
      diagLog: document.querySelector("#diagLog"),
      diagMode: document.querySelector("#diagMode"),
      diagServiceUptime: document.querySelector("#diagServiceUptime"),
      displayDayBrightness: document.querySelector("#displayDayBrightness"),
      displayMessage: document.querySelector("#displayMessage"),
      displayNightBrightness: document.querySelector("#displayNightBrightness"),
      displayNightEnd: document.querySelector("#displayNightEnd"),
      displayNightModeEnabled: document.querySelector("#displayNightModeEnabled"),
      displayNightStart: document.querySelector("#displayNightStart"),
      displayWarning: document.querySelector("#displayWarning"),
      displayWakeBrightness: document.querySelector("#displayWakeBrightness"),
      displayWakeDurationSeconds: document.querySelector("#displayWakeDurationSeconds"),
      displayXrandrOutput: document.querySelector("#displayXrandrOutput"),
      disconnectWifi: document.querySelector("#disconnectWifi"),
      exitAdminMode: document.querySelector("#exitAdminMode"),
      globalNotice: document.querySelector("#globalNotice"),
      activeWifiSsid: document.querySelector("#activeWifiSsid"),
      healthChromium: document.querySelector("#healthChromium"),
      healthDeviceName: document.querySelector("#healthDeviceName"),
      healthDisk: document.querySelector("#healthDisk"),
      healthDisplayWarning: document.querySelector("#healthDisplayWarning"),
      healthError: document.querySelector("#healthError"),
      healthInternet: document.querySelector("#healthInternet"),
      healthIp: document.querySelector("#healthIp"),
      healthLastUpdate: document.querySelector("#healthLastUpdate"),
      healthMemory: document.querySelector("#healthMemory"),
      healthPairing: document.querySelector("#healthPairing"),
      healthPwaUrl: document.querySelector("#healthPwaUrl"),
      healthSsid: document.querySelector("#healthSsid"),
      healthTemp: document.querySelector("#healthTemp"),
      healthUptime: document.querySelector("#healthUptime"),
      healthVersion: document.querySelector("#healthVersion"),
      healthWarning: document.querySelector("#healthWarning"),
      installUpdate: document.querySelector("#installUpdate"),
      lockMessage: document.querySelector("#lockMessage"),
      lockSection: document.querySelector("#lockSection"),
      modePill: document.querySelector("#modePill"),
      navButtons: Array.from(document.querySelectorAll(".nav-button")),
      networkStatus: document.querySelector("#networkStatus"),
      newAdminPin: document.querySelector("#newAdminPin"),
      password: document.querySelector("#password"),
      pinMessage: document.querySelector("#pinMessage"),
      previewNightMode: document.querySelector("#previewNightMode"),
      refreshDiagnostics: document.querySelector("#refreshDiagnostics"),
      refreshOverview: document.querySelector("#refreshOverview"),
      restoreFullBrightness: document.querySelector("#restoreFullBrightness"),
      returnToKiosk: document.querySelector("#returnToKiosk"),
      saveAdminPin: document.querySelector("#saveAdminPin"),
      saveDisplaySettings: document.querySelector("#saveDisplaySettings"),
      saveSettings: document.querySelector("#saveSettings"),
      scan: document.querySelector("#scan"),
      sections: Array.from(document.querySelectorAll(".section-panel")),
      settingsAdminTimeout: document.querySelector("#settingsAdminTimeout"),
      settingsMessage: document.querySelector("#settingsMessage"),
      settingsPwaUrl: document.querySelector("#settingsPwaUrl"),
      ssid: document.querySelector("#ssid"),
      touchKeyboard: document.querySelector("#touchKeyboard"),
      toggleWifiPassword: document.querySelector("#toggleWifiPassword"),
      toggleUnlockPin: document.querySelector("#toggleUnlockPin"),
      unlock: document.querySelector("#unlock"),
      unlockPin: document.querySelector("#unlockPin"),
      updateActionHint: document.querySelector("#updateActionHint"),
      updateCheckedAt: document.querySelector("#updateCheckedAt"),
      updateMessage: document.querySelector("#updateMessage"),
      updatePhase: document.querySelector("#updatePhase"),
      updateVersion: document.querySelector("#updateVersion"),
      updatesMessage: document.querySelector("#updatesMessage"),
      versionPill: document.querySelector("#versionPill"),
      wifiMessage: document.querySelector("#wifiMessage"),
      restartChromiumFromSettings: document.querySelector("#restartChromiumFromSettings"),
      checkUpdates: document.querySelector("#checkUpdates")
    };
    const TEXT_INPUT_SELECTOR = 'input[type="text"], input[type="password"], input[type="search"], input[type="email"], input[type="url"], input[type="tel"], input[type="number"], input[type="time"], input:not([type]), textarea';
    const KEYBOARD_MARGIN = 16;
    const ADMIN_ACTIVITY_PING_MS = 5000;
    const ADMIN_PIN_GUARD_MS = 700;
    const STATUS_POLL_MS = 2000;
    let adminPin = "";
    let latestOverview = null;
    let lastAdminActivityPingAt = 0;
    let unlockPinReadyAt = 0;
    let unlockPinVisible = false;
    let autoReturnNavigating = false;
    let activeSection = "dashboard";
    let activeKeyboardInput = null;
    let keyboardShift = false;
    let keyboardCaps = false;
    function setMessage(target, text, isError = false) {
      if (!target) return;
      target.textContent = text || "";
      target.classList.toggle("error", Boolean(text) && isError);
    }
    function syncUnlockPinToggle() {
      els.unlockPin.type = unlockPinVisible ? "text" : "password";
      els.toggleUnlockPin.textContent = unlockPinVisible ? "Hide" : "Show";
      els.toggleUnlockPin.setAttribute("aria-pressed", unlockPinVisible ? "true" : "false");
      els.toggleUnlockPin.setAttribute("aria-label", unlockPinVisible ? "Hide PIN" : "Show PIN");
    }
    function syncWifiPasswordToggle() {
      els.password.type = els.toggleWifiPassword.checked ? "text" : "password";
    }
    function prepareUnlockPinInput() {
      unlockPinReadyAt = Date.now() + ADMIN_PIN_GUARD_MS;
      unlockPinVisible = false;
      syncUnlockPinToggle();
      els.unlockPin.value = "";
      window.setTimeout(() => {
        els.unlockPin.value = "";
        els.unlockPin.focus();
      }, ADMIN_PIN_GUARD_MS);
    }
    async function api(path, options = {}) {
      let response;
      try {
        response = await fetch(path, options);
      } catch (error) {
        throw new Error(`Failed to fetch ${path}: ${error.message}`);
      }
      const responseText = await response.text();
      let data = {};
      if (responseText) {
        try {
          data = JSON.parse(responseText);
        } catch (error) {
          data = { raw: responseText };
        }
      }
      if (!response.ok) {
        const details = data.error || data.message || data.raw || response.statusText || "Request failed";
        throw new Error(`${response.status} ${details}`);
      }
      return data;
    }
    function noteAdminActivity(force = false) {
      const now = Date.now();
      if (!force && now - lastAdminActivityPingAt < ADMIN_ACTIVITY_PING_MS) return;
      lastAdminActivityPingAt = now;
      fetch("/api/activity", { method: "POST" }).catch(() => {});
    }
    function selectSection(sectionName) {
      activeSection = sectionName;
      for (const button of els.navButtons) {
        button.classList.toggle("active", button.dataset.section === sectionName);
      }
      for (const section of els.sections) {
        section.classList.toggle("hidden", section.id !== `section-${sectionName}`);
      }
      if (sectionName === "diagnostics" && adminPin) {
        loadDiagnostics().catch((error) => setMessage(els.diagnosticsMessage, error.message, true));
      }
      if (sectionName === "display" && adminPin) {
        loadDisplaySettings().catch((error) => setMessage(els.displayMessage, error.message, true));
      }
    }
    function showAdminShell() {
      els.lockSection.classList.add("hidden");
      els.adminShell.classList.remove("hidden");
      hideTouchKeyboard();
      noteAdminActivity(true);
      selectSection(activeSection);
    }
    function updateNetworkChip(online) {
      els.networkStatus.textContent = online ? "Internet online" : "Internet offline";
      els.networkStatus.style.background = online ? "rgba(255,255,255,0.2)" : "rgba(138,45,22,0.32)";
    }
    function maybeAutoReturnToPwa(status) {
      if (autoReturnNavigating) return;
      if (!status || !status.auto_return_pending || !status.pwa_url) return;
      autoReturnNavigating = true;
      setMessage(els.globalNotice, "Connection restored. Returning to Stay Compass...");
      window.setTimeout(() => {
        window.location.href = status.pwa_url;
      }, 1200);
    }
    async function pollStatus() {
      const status = await api("/api/status");
      updateNetworkChip(Boolean(status.online));
      maybeAutoReturnToPwa(status);
      return status;
    }
    function formatDateTime(value) {
      if (!value) return "Unavailable";
      const date = new Date(value * 1000);
      return Number.isNaN(date.getTime()) ? "Unavailable" : date.toLocaleString();
    }
    function formatPercent(numeric) {
      return typeof numeric === "number" ? `${numeric}%` : "Unavailable";
    }
    function formatDiskUsage(diskUsage) {
      if (!diskUsage) return "Unavailable";
      return `${diskUsage.used_gb} GB used of ${diskUsage.total_gb} GB (${formatPercent(diskUsage.used_percent)})`;
    }
    function formatMemoryUsage(memoryUsage) {
      if (!memoryUsage) return "Unavailable";
      return `${memoryUsage.used_mb} MB used of ${memoryUsage.total_mb} MB (${formatPercent(memoryUsage.used_percent)})`;
    }
    function renderDashboardMetrics(overview) {
      const metrics = [
        { label: "Device Health", value: overview.health.device_health || "-" },
        { label: "Internet", value: overview.health.internet_status || "-" },
        { label: "Chromium", value: overview.health.chromium_status || "-" },
        { label: "Mode", value: overview.diagnostics.mode || "-" }
      ];
      els.dashboardMetrics.innerHTML = "";
      for (const metric of metrics) {
        const card = document.createElement("div");
        card.className = "metric";
        card.innerHTML = `<div class="label">${metric.label}</div><div class="value">${metric.value}</div>`;
        els.dashboardMetrics.appendChild(card);
      }
    }
    function renderIssueList(items) {
      els.diagIssues.innerHTML = "";
      if (!items.length) {
        const item = document.createElement("li");
        item.className = "list-item";
        item.textContent = "No recent warnings or errors.";
        els.diagIssues.appendChild(item);
        return;
      }
      for (const entry of items) {
        const item = document.createElement("li");
        item.className = "list-item";
        item.textContent = `[${String(entry.level || "info").toUpperCase()}] ${entry.message || ""}`;
        els.diagIssues.appendChild(item);
      }
    }
    function renderOverview(overview) {
      latestOverview = overview;
      renderDashboardMetrics(overview);
      updateNetworkChip(Boolean(overview.health.internet_online));
      els.modePill.textContent = `Mode: ${overview.diagnostics.mode || "-"}`;
      els.versionPill.textContent = `Version: ${overview.health.software_version || "-"}`;
      els.healthVersion.textContent = overview.health.software_version || "-";
      els.healthPwaUrl.textContent = overview.health.pwa_url || "-";
      els.healthChromium.textContent = overview.health.chromium_status || "-";
      els.healthPairing.textContent = overview.health.pairing_status || "Unavailable";
      els.healthLastUpdate.textContent = overview.health.last_update_message || "No update activity recorded yet.";
      els.healthDeviceName.textContent = overview.health.device_name || "-";
      els.healthInternet.textContent = overview.health.internet_status || "-";
      els.healthIp.textContent = (overview.health.ip_addresses || []).join(", ") || "Unavailable";
      els.healthSsid.textContent = overview.health.wifi_ssid || "Unavailable";
      els.activeWifiSsid.textContent = overview.health.wifi_ssid || "Not connected";
      els.disconnectWifi.disabled = !overview.health.wifi_ssid;
      els.healthUptime.textContent = overview.health.uptime_human || "Unavailable";
      els.healthDisk.textContent = formatDiskUsage(overview.health.disk_usage);
      els.healthMemory.textContent = formatMemoryUsage(overview.health.memory_usage);
      els.healthTemp.textContent = typeof overview.health.cpu_temperature_c === "number" ? `${overview.health.cpu_temperature_c} C` : "Unavailable";
      els.healthWarning.textContent = overview.health.last_warning || "None";
      els.healthError.textContent = overview.health.last_error || "None";
      els.healthDisplayWarning.textContent = overview.diagnostics.display_warning || "None";
      els.settingsPwaUrl.value = overview.settings.pwa_url || "";
      els.settingsAdminTimeout.value = overview.settings.admin_timeout_seconds || 30;
      els.updateVersion.textContent = overview.updates.current_version || "-";
      els.updatePhase.textContent = overview.updates.status?.phase || "Ready";
      els.updateMessage.textContent = overview.updates.status?.message || "No update activity yet.";
      els.updateCheckedAt.textContent = formatDateTime(overview.updates.status?.updated_at);
      els.checkUpdates.disabled = !overview.updates.can_check;
      els.installUpdate.disabled = !overview.updates.can_install;
      els.updateActionHint.textContent = overview.updates.can_check ? "The local update helper is configured for this device." : "Update source repository is not configured on this device.";
      els.diagMode.textContent = overview.diagnostics.mode || "-";
      els.diagServiceUptime.textContent = overview.diagnostics.service_uptime_human || "Unavailable";
      els.diagDisplayWarning.textContent = overview.diagnostics.display_warning || "None";
      els.diagLastUpdate.textContent = overview.diagnostics.last_update_message || "No update activity yet.";
      renderIssueList([...(overview.diagnostics.recent_warnings || []), ...(overview.diagnostics.recent_errors || [])]);
    }
    async function refreshOverview() {
      const overview = await api(`/api/admin-overview?pin=${encodeURIComponent(adminPin)}`);
      renderOverview(overview);
      return overview;
    }
    function brightnessToPercent(value) {
      return Math.round(Number(value || 0) * 100);
    }
    function percentToBrightness(value) {
      return Number(value || 0) / 100;
    }
    function fillDisplaySettings(settings) {
      els.displayNightModeEnabled.value = settings.night_mode_enabled ? "true" : "false";
      els.displayNightStart.value = settings.night_start || "21:00";
      els.displayNightEnd.value = settings.night_end || "07:00";
      els.displayDayBrightness.value = brightnessToPercent(settings.day_brightness);
      els.displayNightBrightness.value = brightnessToPercent(settings.night_brightness);
      els.displayWakeBrightness.value = brightnessToPercent(settings.wake_brightness);
      els.displayWakeDurationSeconds.value = settings.wake_duration_seconds ?? 120;
      els.displayXrandrOutput.value = settings.xrandr_output || "HDMI-1";
    }
    function readDisplaySettingsPayload() {
      return {
        pin: adminPin,
        display: {
          night_mode_enabled: els.displayNightModeEnabled.value === "true",
          night_start: els.displayNightStart.value,
          night_end: els.displayNightEnd.value,
          day_brightness: percentToBrightness(els.displayDayBrightness.value),
          night_brightness: percentToBrightness(els.displayNightBrightness.value),
          wake_brightness: percentToBrightness(els.displayWakeBrightness.value),
          wake_duration_seconds: Number(els.displayWakeDurationSeconds.value),
          xrandr_output: els.displayXrandrOutput.value
        }
      };
    }
    async function loadDisplaySettings() {
      const data = await api(`/api/display-settings?pin=${encodeURIComponent(adminPin)}`);
      fillDisplaySettings(data.display);
      setMessage(els.displayWarning, data.warning || "");
      setMessage(els.displayMessage, data.message || "");
    }
    async function saveDisplaySettings() {
      setMessage(els.displayMessage, "Saving display settings...");
      const data = await api("/api/display-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(readDisplaySettingsPayload())
      });
      fillDisplaySettings(data.display);
      setMessage(els.displayWarning, data.warning || "");
      setMessage(els.displayMessage, data.message || "Display settings saved.");
      await refreshOverview();
    }
    async function previewNightMode() {
      setMessage(els.displayMessage, "Applying night preview...");
      const body = new URLSearchParams({ pin: adminPin });
      const data = await api("/api/display-preview-night", { method: "POST", body });
      setMessage(els.displayWarning, data.warning || "");
      setMessage(els.displayMessage, data.message || "Night mode preview applied.");
      await refreshOverview();
    }
    async function restoreFullBrightness() {
      setMessage(els.displayMessage, "Restoring full brightness...");
      const body = new URLSearchParams({ pin: adminPin });
      const data = await api("/api/display-restore-brightness", { method: "POST", body });
      setMessage(els.displayWarning, data.warning || "");
      setMessage(els.displayMessage, data.message || "Full brightness restored.");
      await refreshOverview();
    }
    async function scanNetworks() {
      setMessage(els.wifiMessage, "Scanning networks...");
      const body = new URLSearchParams({ pin: adminPin });
      const data = await api("/api/networks", { method: "POST", body });
      els.ssid.innerHTML = "";
      for (const network of data.networks) {
        const option = document.createElement("option");
        option.value = network.ssid;
        option.textContent = `${network.ssid} (${network.signal || "?"}%) ${network.security || ""}`.trim();
        els.ssid.appendChild(option);
      }
      setMessage(els.wifiMessage, data.networks.length ? "Choose a network and connect." : "No networks found.");
    }
    async function connectWifi() {
      setMessage(els.wifiMessage, "Connecting...");
      const body = new URLSearchParams({
        ssid: els.ssid.value,
        password: els.password.value,
        pin: adminPin
      });
      const data = await api("/api/wifi", { method: "POST", body });
      setMessage(els.wifiMessage, data.message || "Wi-Fi settings saved.");
      await Promise.all([refreshOverview(), scanNetworks()]);
    }
    async function disconnectCurrentWifi() {
      if (!window.confirm("Disconnect Wi-Fi now? This may immediately terminate the current SSH or admin session.")) return;
      setMessage(els.wifiMessage, "Disconnecting Wi-Fi...");
      const body = new URLSearchParams({ pin: adminPin });
      const data = await api("/api/wifi-disconnect", { method: "POST", body });
      setMessage(els.wifiMessage, data.message || "Wi-Fi disconnected.");
      await Promise.all([refreshOverview(), scanNetworks()]);
    }
    async function saveSettings() {
      setMessage(els.settingsMessage, "Saving local Stay Compass settings...");
      const data = await api("/api/settings/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: adminPin, pwa_url: els.settingsPwaUrl.value })
      });
      setMessage(els.settingsMessage, data.message || "Settings saved.");
      await refreshOverview();
    }
    async function changePin() {
      setMessage(els.pinMessage, "Saving new admin PIN...");
      const data = await api("/api/admin-pin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pin: adminPin,
          new_pin: els.newAdminPin.value,
          confirm_pin: els.confirmAdminPin.value
        })
      });
      adminPin = els.newAdminPin.value;
      els.newAdminPin.value = "";
      els.confirmAdminPin.value = "";
      setMessage(els.pinMessage, data.message || "Admin PIN updated.");
    }
    async function runAdminAction(action, targetMessage, confirmationText = "") {
      if (confirmationText && !window.confirm(confirmationText)) return;
      setMessage(targetMessage, "Running action...");
      const data = await api("/api/admin-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: adminPin, action })
      });
      setMessage(targetMessage, data.message || "Action requested.");
      await refreshOverview();
    }
    async function exitAdminMode() {
      const fallbackUrl = els.settingsPwaUrl.value || "/";
      const pwaUrl = (latestOverview && latestOverview.settings && latestOverview.settings.pwa_url) || fallbackUrl;
      setMessage(els.globalNotice, "Returning to the Stay Compass kiosk...");
      const data = await api("/api/admin-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: adminPin, action: "return_to_kiosk" })
      });
      const targetUrl = data.pwa_url || pwaUrl || "/";
      window.location.href = targetUrl;
    }
    async function loadDiagnostics() {
      const body = new URLSearchParams({ pin: adminPin });
      const diagnostics = await api("/api/diagnostics", { method: "POST", body });
      els.diagMode.textContent = diagnostics.mode || "-";
      els.diagServiceUptime.textContent = diagnostics.service_uptime_human || "Unavailable";
      els.diagDisplayWarning.textContent = diagnostics.display_warning || "None";
      els.diagLastUpdate.textContent = diagnostics.last_update_message || "No update activity yet.";
      renderIssueList([...(diagnostics.recent_warnings || []), ...(diagnostics.recent_errors || [])]);
      els.diagLog.textContent = (diagnostics.recent_log_lines || []).join("\\n") || "No recent device log lines available.";
      els.diagnosticsText.value = diagnostics.diagnostics_text || "";
      setMessage(els.diagnosticsMessage, "Diagnostics refreshed.");
    }
    async function copyDiagnostics() {
      const text = els.diagnosticsText.value || "";
      if (!text) {
        setMessage(els.diagnosticsMessage, "No diagnostics text is available yet.", true);
        return;
      }
      try {
        await navigator.clipboard.writeText(text);
      } catch (error) {
        els.diagnosticsText.focus();
        els.diagnosticsText.select();
        document.execCommand("copy");
      }
      setMessage(els.diagnosticsMessage, "Diagnostics text copied.");
    }
    async function unlockAdmin() {
      setMessage(els.lockMessage, "Checking PIN...");
      adminPin = els.unlockPin.value;
      const body = new URLSearchParams({ pin: adminPin });
      await api("/api/unlock", { method: "POST", body });
      showAdminShell();
      setMessage(els.globalNotice, "Admin mode unlocked.");
      await Promise.all([refreshOverview(), loadDisplaySettings(), scanNetworks(), loadDiagnostics()]);
    }
    function isKeyboardInput(element) {
      return Boolean(element && element.matches && element.matches(TEXT_INPUT_SELECTOR) && !element.disabled && !element.readOnly);
    }
    function updateKeyboardHeight() {
      const keyboardHeight = els.touchKeyboard.classList.contains("hidden") ? 0 : Math.ceil(els.touchKeyboard.getBoundingClientRect().height);
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
      return (keyboardShift || keyboardCaps) ? value.toUpperCase() : value.toLowerCase();
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
      if (options.active) button.classList.add("active");
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
    function initTouchKeyboard() {
      els.touchKeyboard.addEventListener("pointerdown", (event) => {
        event.preventDefault();
      });
      document.addEventListener("focusin", (event) => {
        const target = event.target;
        if (isKeyboardInput(target)) showTouchKeyboard(target);
      });
      document.addEventListener("focusout", (event) => {
        if (!isKeyboardInput(event.target)) return;
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
        if (els.touchKeyboard.contains(target)) return;
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
    for (const button of els.navButtons) {
      button.addEventListener("click", () => selectSection(button.dataset.section));
    }
    els.refreshOverview.addEventListener("click", () => refreshOverview().catch((error) => setMessage(els.globalNotice, error.message, true)));
    els.exitAdminMode.addEventListener("click", () => exitAdminMode().catch((error) => setMessage(els.globalNotice, error.message, true)));
    els.saveSettings.addEventListener("click", () => saveSettings().catch((error) => setMessage(els.settingsMessage, error.message, true)));
    els.returnToKiosk.addEventListener("click", () => exitAdminMode().catch((error) => setMessage(els.settingsMessage, error.message, true)));
    els.restartChromiumFromSettings.addEventListener("click", () => runAdminAction("restart_chromium", els.settingsMessage, "Restart Chromium now?").catch((error) => setMessage(els.settingsMessage, error.message, true)));
    els.saveAdminPin.addEventListener("click", () => changePin().catch((error) => setMessage(els.pinMessage, error.message, true)));
    els.saveDisplaySettings.addEventListener("click", (event) => {
      event.preventDefault();
      saveDisplaySettings().catch((error) => setMessage(els.displayMessage, error.message, true));
    });
    els.previewNightMode.addEventListener("click", () => previewNightMode().catch((error) => setMessage(els.displayMessage, error.message, true)));
    els.restoreFullBrightness.addEventListener("click", () => restoreFullBrightness().catch((error) => setMessage(els.displayMessage, error.message, true)));
    els.scan.addEventListener("click", () => scanNetworks().catch((error) => setMessage(els.wifiMessage, error.message, true)));
    els.connect.addEventListener("click", () => connectWifi().catch((error) => setMessage(els.wifiMessage, error.message, true)));
    els.disconnectWifi.addEventListener("click", () => disconnectCurrentWifi().catch((error) => setMessage(els.wifiMessage, error.message, true)));
    els.checkUpdates.addEventListener("click", () => runAdminAction("check_updates", els.updatesMessage).catch((error) => setMessage(els.updatesMessage, error.message, true)));
    els.installUpdate.addEventListener("click", () => runAdminAction("install_update", els.updatesMessage, "Install the latest available update now?").catch((error) => setMessage(els.updatesMessage, error.message, true)));
    els.refreshDiagnostics.addEventListener("click", () => loadDiagnostics().catch((error) => setMessage(els.diagnosticsMessage, error.message, true)));
    els.copyDiagnostics.addEventListener("click", () => copyDiagnostics().catch((error) => setMessage(els.diagnosticsMessage, error.message, true)));
    els.advancedRestartChromium.addEventListener("click", () => runAdminAction("restart_chromium", els.advancedMessage, "Restart Chromium now?").catch((error) => setMessage(els.advancedMessage, error.message, true)));
    els.unlock.addEventListener("click", () => unlockAdmin().catch((error) => setMessage(els.lockMessage, error.message, true)));
    els.toggleUnlockPin.addEventListener("click", () => {
      unlockPinVisible = !unlockPinVisible;
      syncUnlockPinToggle();
      if (Date.now() >= unlockPinReadyAt) els.unlockPin.focus();
    });
    els.toggleWifiPassword.addEventListener("change", syncWifiPasswordToggle);
    els.unlockPin.addEventListener("keydown", (event) => {
      if (Date.now() < unlockPinReadyAt) {
        event.preventDefault();
        return;
      }
      if (event.key === "Enter") unlockAdmin().catch((error) => setMessage(els.lockMessage, error.message, true));
    });
    els.unlockPin.addEventListener("beforeinput", (event) => {
      if (Date.now() < unlockPinReadyAt) event.preventDefault();
    });
    els.unlockPin.addEventListener("input", () => {
      if (Date.now() < unlockPinReadyAt) els.unlockPin.value = "";
    });
    ["pointerdown", "keydown", "input", "focusin"].forEach((eventName) => {
      document.addEventListener(eventName, () => noteAdminActivity(), true);
    });
    initTouchKeyboard();
    syncWifiPasswordToggle();
    prepareUnlockPinInput();
    pollStatus().catch((error) => setMessage(els.globalNotice, error.message, true));
    window.setInterval(() => {
      pollStatus().catch(() => {});
      if (!adminPin || autoReturnNavigating) return;
      refreshOverview().catch(() => {});
      if (activeSection === "diagnostics") loadDiagnostics().catch(() => {});
    }, STATUS_POLL_MS);
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
    RECENT_LOGS.append(
        {
            "timestamp": time.time(),
            "level": infer_log_level(message),
            "message": str(message),
        }
    )
    print(message)
    logging.info(message)


def infer_log_level(message):
    text = str(message).lower()
    if any(token in text for token in ["error", "failed", "traceback", "exception"]):
        return "error"
    if any(token in text for token in ["warning", "unavailable", "ignored", "invalid"]):
        return "warning"
    return "info"


def trim_text_lines(text, limit=80):
    lines = [line.rstrip() for line in str(text or "").splitlines()]
    if len(lines) <= limit:
        return lines
    return lines[-limit:]


def format_uptime(total_seconds):
    total_seconds = max(0, int(total_seconds or 0))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or parts:
        parts.append(f"{hours}h")
    if minutes or parts:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    config["display"] = normalize_display_config(config.get("display"))
    return config


def save_config(config):
    config_dir = CONFIG_FILE.parent
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=config_dir, delete=False) as config_file:
        json.dump(config, config_file, indent=2)
        config_file.write("\n")
        temp_name = config_file.name
    os.replace(temp_name, CONFIG_FILE)


def read_text_file(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def read_json_file(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def run_command(command, timeout=30, cwd=None, env=None):
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
        cwd=cwd,
        env=env,
    )


def float_or_default(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def bool_or_default(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def require_valid_http_url(value):
    candidate = str(value or "").strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("PWA URL must be a valid http:// or https:// address.")
    return candidate


def validate_new_pin(value):
    candidate = str(value or "").strip()
    if len(candidate) < 4:
        raise ValueError("Admin PIN must be at least 4 characters.")
    if len(candidate) > 32:
        raise ValueError("Admin PIN must be 32 characters or fewer.")
    return candidate


def clamp_brightness(value):
    return max(MIN_BRIGHTNESS, min(MAX_BRIGHTNESS, round(float(value), 2)))


def normalize_time_string(value, default):
    if not isinstance(value, str):
        return default

    parts = value.split(":")
    if len(parts) != 2:
        return default

    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return default

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return default

    return f"{hour:02d}:{minute:02d}"


def normalize_display_config(display_config):
    display = dict(DISPLAY_DEFAULTS)
    if isinstance(display_config, dict):
        display.update(display_config)

    display["night_mode_enabled"] = bool_or_default(display.get("night_mode_enabled"), DISPLAY_DEFAULTS["night_mode_enabled"])
    display["night_start"] = normalize_time_string(display.get("night_start"), DISPLAY_DEFAULTS["night_start"])
    display["night_end"] = normalize_time_string(display.get("night_end"), DISPLAY_DEFAULTS["night_end"])
    display["day_brightness"] = clamp_brightness(float_or_default(display.get("day_brightness"), DISPLAY_DEFAULTS["day_brightness"]))
    display["night_brightness"] = clamp_brightness(float_or_default(display.get("night_brightness"), DISPLAY_DEFAULTS["night_brightness"]))
    display["wake_brightness"] = clamp_brightness(float_or_default(display.get("wake_brightness"), DISPLAY_DEFAULTS["wake_brightness"]))
    display["wake_duration_seconds"] = max(1, min(24 * 60 * 60, int_or_default(display.get("wake_duration_seconds"), DISPLAY_DEFAULTS["wake_duration_seconds"])))
    display["xrandr_output"] = str(display.get("xrandr_output") or DISPLAY_DEFAULTS["xrandr_output"]).strip() or DISPLAY_DEFAULTS["xrandr_output"]
    return display


def validate_display_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object.")

    display_payload = payload.get("display")
    if not isinstance(display_payload, dict):
        raise ValueError("JSON body must include a display object.")

    for required_field in [
        "night_mode_enabled",
        "night_start",
        "night_end",
        "day_brightness",
        "night_brightness",
        "wake_brightness",
        "wake_duration_seconds",
        "xrandr_output",
    ]:
        if required_field not in display_payload:
            raise ValueError(f"Display field is required: {required_field}")

    if normalize_time_string(display_payload.get("night_start"), None) is None:
        raise ValueError("night_start must use HH:MM format.")
    if normalize_time_string(display_payload.get("night_end"), None) is None:
        raise ValueError("night_end must use HH:MM format.")

    try:
        float(display_payload.get("day_brightness"))
        float(display_payload.get("night_brightness"))
        float(display_payload.get("wake_brightness"))
    except (TypeError, ValueError):
        raise ValueError("Brightness values must be numbers.") from None

    try:
        int(display_payload.get("wake_duration_seconds"))
    except (TypeError, ValueError):
        raise ValueError("wake_duration_seconds must be an integer.") from None

    output_name = str(display_payload.get("xrandr_output") or "").strip()
    if not output_name:
        raise ValueError("xrandr_output is required.")

    return display_payload


def parse_time_to_minutes(value):
    normalized = normalize_time_string(value, DISPLAY_DEFAULTS["night_start"])
    hour, minute = normalized.split(":")
    return (int(hour) * 60) + int(minute)


def is_time_in_range(current_minutes, start_minutes, end_minutes):
    if start_minutes == end_minutes:
        return True
    if start_minutes < end_minutes:
        return start_minutes <= current_minutes < end_minutes
    return current_minutes >= start_minutes or current_minutes < end_minutes


def is_night_mode_active(display_config, now=None):
    if not display_config.get("night_mode_enabled"):
        return False

    now = now or time.localtime()
    current_minutes = (now.tm_hour * 60) + now.tm_min
    start_minutes = parse_time_to_minutes(display_config.get("night_start"))
    end_minutes = parse_time_to_minutes(display_config.get("night_end"))
    return is_time_in_range(current_minutes, start_minutes, end_minutes)


def get_display_status(state):
    with state["lock"]:
        command_warning = state.get("display_command_warning")
        monitor_warning = state.get("display_monitor_warning")
        last_applied = state.get("display_last_applied")
        preview_mode = state.get("display_override_mode")
        wake_until = state.get("display_wake_until", 0.0)
        display_config = dict(state["config"].get("display", {}))

    warning = " ".join(part for part in [command_warning, monitor_warning] if part)
    return {
        "warning": warning,
        "last_applied_brightness": last_applied,
        "night_active": is_night_mode_active(display_config),
        "preview_mode": preview_mode,
        "wake_active": wake_until > monotonic_seconds(),
    }


def set_display_warning(state, message, warning_type="command"):
    with state["lock"]:
        state[f"display_{warning_type}_warning"] = message or None


def clear_display_warning(state, warning_type="command"):
    set_display_warning(state, None, warning_type=warning_type)


def x11_command_env():
    env = os.environ.copy()
    env["DISPLAY"] = DISPLAY_NAME
    return env


def apply_xrandr_brightness(state, brightness, reason):
    with state["lock"]:
        display_config = dict(state["config"].get("display", {}))

    brightness = clamp_brightness(brightness)
    output_name = display_config.get("xrandr_output", DISPLAY_DEFAULTS["xrandr_output"])
    command = [
        XRANDR_BIN,
        "--output",
        output_name,
        "--brightness",
        f"{brightness:.2f}",
    ]
    result = run_command(command, timeout=15, env=x11_command_env())

    if result.returncode != 0:
        error_text = get_command_output(result) or "xrandr command failed."
        warning = f"Display brightness change failed for {output_name}: {error_text}"
        set_display_warning(state, warning, warning_type="command")
        log(f"{warning} Requested by {reason}.")
        return False

    clear_display_warning(state, warning_type="command")
    with state["lock"]:
        state["display_last_applied"] = brightness
        state["display_last_reason"] = reason
    log(f"Display brightness set to {brightness:.2f} on {output_name} ({reason}).")
    return True


def display_target_for_state(display_config, state, now_monotonic=None):
    now_monotonic = now_monotonic or monotonic_seconds()
    night_active = is_night_mode_active(display_config)

    with state["lock"]:
        override = state.get("display_override_brightness")
        override_mode = state.get("display_override_mode")
        wake_until = state.get("display_wake_until", 0.0)

    if override is not None:
        return clamp_brightness(override), override_mode or "manual override"

    if night_active:
        if wake_until > now_monotonic:
            return clamp_brightness(display_config["wake_brightness"]), "night wake"
        return clamp_brightness(display_config["night_brightness"]), "scheduled night mode"

    return clamp_brightness(display_config["day_brightness"]), "scheduled day mode"


def sync_display_brightness(state, force=False):
    with state["lock"]:
        display_config = dict(state["config"].get("display", {}))
        last_applied = state.get("display_last_applied")
        last_reason = state.get("display_last_reason")

    target_brightness, reason = display_target_for_state(display_config, state)
    if not force and last_applied is not None and abs(last_applied - target_brightness) < 0.001 and last_reason == reason:
        return True

    return apply_xrandr_brightness(state, target_brightness, reason)


def record_user_interaction(state, source, extend_admin=False):
    if extend_admin:
        record_admin_activity(state, source)

    with state["lock"]:
        display_config = dict(state["config"].get("display", {}))
        override_active = state.get("display_override_brightness") is not None

    if override_active or not is_night_mode_active(display_config):
        return

    wake_duration_seconds = display_config["wake_duration_seconds"]
    wake_until = monotonic_seconds() + wake_duration_seconds
    with state["lock"]:
        state["display_wake_until"] = wake_until
    log(f"Night wake triggered by {source}; brightening for {wake_duration_seconds}s.")
    sync_display_brightness(state)


def start_activity_monitor(state):
    def monitor():
        if not shutil.which(XINPUT_BIN):
            warning = "Global wake-on-touch is unavailable because xinput is not installed."
            set_display_warning(state, warning, warning_type="monitor")
            log(warning)
            return

        while not state.get("shutdown"):
            try:
                process = subprocess.Popen(
                    [
                        XINPUT_BIN,
                        "test-xi2",
                        "--root",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=x11_command_env(),
                )
                with state["lock"]:
                    state["activity_monitor_process"] = process
                log("Started xinput activity monitor for night wake events.")

                while not state.get("shutdown"):
                    line = process.stdout.readline()
                    if not line:
                        break
                    if "EVENT type" in line:
                        record_user_interaction(state, "xinput event")

                stderr_output = ""
                if process.stderr:
                    stderr_output = process.stderr.read().strip()
                if state.get("shutdown"):
                    break
                warning = stderr_output or "xinput activity monitor stopped unexpectedly."
                set_display_warning(state, f"Wake-on-touch monitor warning: {warning}", warning_type="monitor")
                log(f"Wake-on-touch monitor warning: {warning}")
            except Exception as error:
                warning = f"Wake-on-touch monitor failed: {error}"
                set_display_warning(state, warning, warning_type="monitor")
                log(warning)

            time.sleep(5)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    return thread


def update_display_config(config, payload):
    existing_display = config.get("display", {})
    submitted_display = validate_display_payload(payload)
    display = normalize_display_config({**existing_display, **submitted_display})
    config["display"] = display
    return display


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
            f"--disable-extensions-except={ADMIN_EXTENSION_DIR}",
            f"--load-extension={ADMIN_EXTENSION_DIR}",
            url,
        ]
    )


def monotonic_seconds():
    return time.monotonic()


def set_admin_deadline(state, source):
    deadline = monotonic_seconds() + ADMIN_INACTIVITY_TIMEOUT_SECONDS
    with state["lock"]:
        state["admin_deadline"] = deadline
    return deadline


def clear_admin_session(state):
    with state["lock"]:
        state["admin_deadline"] = 0.0
        state["admin_unlocked"] = False
        state["admin_last_activity_at"] = 0.0


def reset_admin_entry_state(state):
    with state["lock"]:
        state["admin_entry_reason"] = None
        state["auto_return_pending"] = False
        state["wifi_connect_started_at"] = 0.0
        state["wifi_connect_success_at"] = 0.0


def request_app_mode(state, source):
    with state["lock"]:
        state["requested_mode"] = "app"
        state["local_admin_navigation_pending"] = False
        state["local_app_navigation_pending"] = False
        state["admin_deadline"] = 0.0
        state["admin_unlocked"] = False
        state["admin_last_activity_at"] = 0.0
        state["admin_entry_reason"] = None
        state["auto_return_pending"] = False
        state["wifi_connect_started_at"] = 0.0
        state["wifi_connect_success_at"] = 0.0
        state["display_override_brightness"] = None
        state["display_override_mode"] = None
    log(f"App mode requested from {source}.")


def request_app_mode_local_navigation(state, source):
    with state["lock"]:
        state["requested_mode"] = "app"
        state["local_admin_navigation_pending"] = False
        state["local_app_navigation_pending"] = True
        state["admin_deadline"] = 0.0
        state["admin_unlocked"] = False
        state["admin_last_activity_at"] = 0.0
        state["admin_entry_reason"] = None
        state["auto_return_pending"] = False
        state["wifi_connect_started_at"] = 0.0
        state["wifi_connect_success_at"] = 0.0
        state["display_override_brightness"] = None
        state["display_override_mode"] = None
    log(f"App mode local navigation requested from {source}.")


def request_admin_mode(state, source, prefer_local_navigation=False, entry_reason="manual"):
    now = monotonic_seconds()

    with state["lock"]:
        lockout_until = state.get("admin_lockout_until", 0.0)

        if lockout_until > now:
            remaining = max(1, int(lockout_until - now))
            log(f"Admin request ignored from {source}; lockout active for {remaining}s more.")
            return False

        state["requested_mode"] = "admin"
        state["local_admin_navigation_pending"] = bool(prefer_local_navigation)
        state["local_app_navigation_pending"] = False
        state["admin_deadline"] = now + ADMIN_INACTIVITY_TIMEOUT_SECONDS
        state["admin_unlocked"] = False
        state["admin_last_activity_at"] = 0.0
        state["admin_entry_reason"] = entry_reason
        state["auto_return_pending"] = False
        state["wifi_connect_started_at"] = 0.0
        state["wifi_connect_success_at"] = 0.0

    log(f"Admin mode requested from {source} (entry reason: {entry_reason}).")
    return True


def queue_offline_recovery_return(state, source):
    with state["lock"]:
        if state.get("admin_entry_reason") != "offline_recovery":
            return False
        if state.get("auto_return_pending"):
            return False

        state["requested_mode"] = "app"
        state["local_admin_navigation_pending"] = False
        state["local_app_navigation_pending"] = True
        state["admin_deadline"] = 0.0
        state["admin_unlocked"] = False
        state["auto_return_pending"] = True

    log(f"Offline recovery: returning to configured PWA from {source}.")
    return True


def record_admin_activity(state, source):
    deadline = set_admin_deadline(state, source)
    with state["lock"]:
        state["admin_last_activity_at"] = monotonic_seconds()
    log(f"Admin activity detected from {source}; timeout reset to {int(deadline - monotonic_seconds())}s.")


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
        error_message = format_nmcli_error("Scanning Wi-Fi networks", result)
        log(f"Wi-Fi warning: {error_message}")
        raise RuntimeError("Unable to scan Wi-Fi networks right now.")

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


def list_wifi_connection_ids(ssid):
    try:
        result = run_command(
            [
                NMCLI_BIN,
                "-t",
                "--escape",
                "yes",
                "-f",
                "NAME,TYPE,802-11-wireless.ssid",
                "connection",
                "show",
            ],
            timeout=30,
        )
    except OSError:
        return []

    if result.returncode != 0:
        return []

    connection_ids = []
    for line in result.stdout.splitlines():
        name, connection_type, connection_ssid = (parse_nmcli_escaped_fields(line) + ["", "", ""])[:3]
        if connection_type.strip() != "802-11-wireless":
            continue
        if connection_ssid.strip() != ssid:
            continue
        if name.strip():
            connection_ids.append(name.strip())
    return connection_ids


def get_wifi_network_details(ssid):
    try:
        networks = scan_wifi_networks()
    except Exception as error:
        log(
            f"Wi-Fi connect: scan lookup for SSID {ssid!r} failed before connect "
            f"({error}). Falling back to existing NetworkManager data."
        )
        return {"ssid": ssid, "security": "", "signal": ""}

    for network in networks:
        if network.get("ssid") == ssid:
            return network

    return {"ssid": ssid, "security": "", "signal": ""}


def normalize_wifi_security(security):
    return " ".join(str(security or "").strip().upper().split())


def wifi_security_is_open(security):
    normalized = normalize_wifi_security(security)
    return normalized in {"", "--", "NONE", "OPEN"}


def wifi_security_is_personal(security):
    normalized = normalize_wifi_security(security)
    if not normalized or wifi_security_is_open(normalized):
        return False
    return "WPA" in normalized and "EAP" not in normalized and "802.1X" not in normalized


def wifi_security_is_enterprise(security):
    normalized = normalize_wifi_security(security)
    return "EAP" in normalized or "802.1X" in normalized


def format_command_for_log(command):
    redacted = []
    hide_next = False

    for token in command:
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
            continue

        redacted.append(token)
        if token in {
            "password",
            "wifi-sec.psk",
            "802-11-wireless-security.psk",
            "psk",
        }:
            hide_next = True

    return " ".join(redacted)


def redact_nmcli_output(text):
    if not text:
        return ""
    sanitized = str(text).replace("\r", " ").replace("\n", " ").strip()
    return " ".join(sanitized.split())


def format_nmcli_error(operation, result):
    details = redact_nmcli_output(get_command_output(result))
    if not details:
        details = "nmcli did not provide additional details."
    return f"{operation} failed (exit {result.returncode}): {details}"


def run_nmcli_or_raise(command, timeout, operation, user_message):
    log(f"Wi-Fi: running {format_command_for_log(command)}")
    result = run_command(command, timeout=timeout)

    if result.returncode != 0:
        error_message = format_nmcli_error(operation, result)
        log(f"Wi-Fi warning: {error_message}")
        raise RuntimeError(user_message)

    return result


def get_wifi_device(prefer_active=False):
    try:
        result = run_command(
            [
                NMCLI_BIN,
                "-t",
                "--escape",
                "yes",
                "-f",
                "DEVICE,TYPE,STATE",
                "device",
                "status",
            ],
            timeout=20,
        )
    except OSError:
        return None

    if result.returncode != 0:
        return None

    fallback_device = None

    for line in result.stdout.splitlines():
        device, device_type, state_text = (parse_nmcli_escaped_fields(line) + ["", "", ""])[:3]
        if device_type.strip() != "wifi":
            continue

        device = device.strip()
        if not device:
            continue

        if fallback_device is None:
            fallback_device = device

        normalized_state = state_text.strip().lower()
        if normalized_state in {"connected", "connecting", "connected (externally)"}:
            return device

    return None if prefer_active else fallback_device


def verify_wifi_security_profile(connection_id, expect_personal_security):
    fields = "802-11-wireless-security.key-mgmt,802-11-wireless-security.psk"
    result = run_command(
        [NMCLI_BIN, "--show-secrets", "-g", fields, "connection", "show", connection_id],
        timeout=20,
    )

    if result.returncode != 0:
        log(
            f"Wi-Fi warning: unable to inspect NetworkManager profile {connection_id!r} "
            f"after update ({format_nmcli_error('Inspecting Wi-Fi profile', result)})."
        )
        return

    lines = result.stdout.splitlines()
    key_mgmt = (lines[0] if len(lines) > 0 else "").strip()
    psk = (lines[1] if len(lines) > 1 else "").strip()

    if expect_personal_security:
        if key_mgmt != "wpa-psk" or not psk:
            log(
                f"Wi-Fi warning: NetworkManager profile {connection_id!r} is missing "
                f"required WPA Personal settings after creation (key-mgmt={key_mgmt!r}, "
                f"psk present={'yes' if bool(psk) else 'no'})."
            )
            raise RuntimeError(
                "Unable to save the Wi-Fi password correctly. Please try connecting again."
            )
        return

    if key_mgmt:
        log(
            f"Wi-Fi warning: open-network profile {connection_id!r} unexpectedly still "
            f"contains key management {key_mgmt!r}."
        )


def connect_wifi(ssid, password):
    network = get_wifi_network_details(ssid)
    security = network.get("security", "")
    is_open_network = wifi_security_is_open(security)
    is_personal_network = wifi_security_is_personal(security)

    if wifi_security_is_enterprise(security):
        raise RuntimeError(
            "This Wi-Fi page supports open networks and WPA/WPA2 Personal networks only."
        )

    if not is_open_network and not is_personal_network and security:
        raise RuntimeError(
            f"Unable to identify the security mode for {ssid!r}. Re-scan networks and try again."
        )

    if is_personal_network and not password:
        raise RuntimeError(f"Enter the Wi-Fi password for {ssid!r} and try again.")

    device = get_wifi_device(prefer_active=False)
    if not device:
        raise RuntimeError("No Wi-Fi adapter is available right now.")

    matching_connection_ids = list_wifi_connection_ids(ssid)
    if matching_connection_ids:
        log(
            f"Wi-Fi connect: removing {len(matching_connection_ids)} existing "
            f"NetworkManager profile(s) for SSID {ssid!r} before reconnect."
        )
    for connection_id in matching_connection_ids:
        delete_result = run_command(
            [NMCLI_BIN, "connection", "delete", connection_id],
            timeout=30,
        )
        if delete_result.returncode != 0:
            log(
                f"Wi-Fi connect: failed to delete existing profile {connection_id!r} "
                f"for SSID {ssid!r} (exit {delete_result.returncode})."
            )

    connection_id = ssid
    add_command = [
        NMCLI_BIN,
        "connection",
        "add",
        "type",
        "wifi",
        "ifname",
        device,
        "con-name",
        connection_id,
        "ssid",
        ssid,
    ]
    run_nmcli_or_raise(
        add_command,
        timeout=30,
        operation=f"Creating Wi-Fi profile for SSID {ssid!r}",
        user_message=f"Unable to prepare the Wi-Fi profile for {ssid!r}.",
    )

    common_settings = [
        NMCLI_BIN,
        "connection",
        "modify",
        connection_id,
        "connection.autoconnect",
        "yes",
        "802-11-wireless.mode",
        "infrastructure",
        "ipv4.method",
        "auto",
        "ipv6.method",
        "auto",
    ]
    run_nmcli_or_raise(
        common_settings,
        timeout=30,
        operation=f"Updating Wi-Fi profile for SSID {ssid!r}",
        user_message=f"Unable to save the Wi-Fi settings for {ssid!r}.",
    )

    if is_personal_network:
        secure_settings = [
            NMCLI_BIN,
            "connection",
            "modify",
            connection_id,
            "wifi-sec.key-mgmt",
            "wpa-psk",
            "wifi-sec.psk",
            password,
        ]
        run_nmcli_or_raise(
            secure_settings,
            timeout=30,
            operation=f"Applying WPA Personal settings to SSID {ssid!r}",
            user_message=(
                f"Unable to save the Wi-Fi password for {ssid!r}. Check the password and try again."
            ),
        )
        verify_wifi_security_profile(connection_id, expect_personal_security=True)
    else:
        verify_wifi_security_profile(connection_id, expect_personal_security=False)

    activate_command = [NMCLI_BIN, "connection", "up", connection_id]
    try:
        run_nmcli_or_raise(
            activate_command,
            timeout=60,
            operation=f"Activating Wi-Fi profile for SSID {ssid!r}",
            user_message=f"Unable to connect to {ssid!r}. Check the password and try again.",
        )
    except RuntimeError as error:
        failure_message = str(error)
        if is_open_network:
            failure_message = (
                f"Unable to connect to {ssid!r}. Check the signal and try again."
            )
        raise RuntimeError(failure_message)

    log(
        f"Wi-Fi connect: connection profile {connection_id!r} activated for SSID {ssid!r} "
        f"using {'open' if is_open_network else 'WPA/WPA2 Personal'} security."
    )


def disconnect_wifi():
    device = get_wifi_device(prefer_active=True)
    if not device:
        raise RuntimeError("No active Wi-Fi connection is available to disconnect.")

    log(f"Wi-Fi disconnect: invoking nmcli device disconnect for interface {device!r}.")
    result = run_command([NMCLI_BIN, "device", "disconnect", device], timeout=45)

    if result.returncode != 0:
        error_message = format_nmcli_error(f"Disconnecting Wi-Fi device {device!r}", result)
        log(f"Wi-Fi disconnect warning: {error_message}")
        raise RuntimeError("Unable to disconnect Wi-Fi right now.")

    log(f"Wi-Fi disconnect: nmcli reported success for interface {device!r}.")
    return {"device": device}


def valid_admin_pin(config, form):
    return bool(config.get("admin_pin")) and form.get("pin") == config.get("admin_pin")


def load_meminfo():
    details = {}
    for line in read_text_file("/proc/meminfo").splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        value = raw_value.strip().split()[0]
        try:
            details[key] = int(value)
        except ValueError:
            continue
    return details


def get_uptime_seconds():
    raw = read_text_file("/proc/uptime")
    if not raw:
        return None
    try:
        return int(float(raw.split()[0]))
    except (IndexError, ValueError):
        return None


def get_memory_usage():
    meminfo = load_meminfo()
    total_kb = meminfo.get("MemTotal")
    available_kb = meminfo.get("MemAvailable")
    if not total_kb or available_kb is None:
        return None
    used_kb = max(0, total_kb - available_kb)
    used_percent = round((used_kb / total_kb) * 100, 1) if total_kb else None
    return {
        "total_mb": round(total_kb / 1024, 1),
        "used_mb": round(used_kb / 1024, 1),
        "available_mb": round(available_kb / 1024, 1),
        "used_percent": used_percent,
    }


def get_disk_usage():
    try:
        usage = shutil.disk_usage("/")
    except OSError:
        return None
    total_gb = round(usage.total / (1024 ** 3), 1)
    used_gb = round((usage.total - usage.free) / (1024 ** 3), 1)
    free_gb = round(usage.free / (1024 ** 3), 1)
    used_percent = round(((usage.total - usage.free) / usage.total) * 100, 1) if usage.total else None
    return {
        "total_gb": total_gb,
        "used_gb": used_gb,
        "free_gb": free_gb,
        "used_percent": used_percent,
    }


def get_cpu_temperature_c():
    thermal_root = Path("/sys/class/thermal")
    try:
        zones = sorted(thermal_root.glob("thermal_zone*/temp"))
    except OSError:
        return None
    for zone in zones:
        raw = read_text_file(zone)
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 1000:
            value = value / 1000
        if value <= 0:
            continue
        return round(value, 1)
    return None


def get_ip_addresses():
    addresses = []
    try:
        result = run_command(["hostname", "-I"], timeout=10)
        if result.returncode == 0:
            addresses = [value for value in result.stdout.split() if value]
    except OSError:
        addresses = []
    return addresses


def get_connected_wifi_ssid():
    try:
        result = run_command(
            [
                NMCLI_BIN,
                "-t",
                "--escape",
                "yes",
                "-f",
                "ACTIVE,SSID",
                "dev",
                "wifi",
            ],
            timeout=20,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        active, ssid = (parse_nmcli_escaped_fields(line) + ["", ""])[:2]
        if active.strip().lower() == "yes" and ssid.strip():
            return ssid.strip()
    return None


def get_pairing_status(config):
    candidates = [
        ("pairing_token", "Pairing token configured"),
        ("device_token", "Device token configured"),
        ("auth_token", "Auth token configured"),
        ("pairing_code", "Pairing code configured"),
    ]
    for key, label in candidates:
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return {"available": True, "label": label}
    return {"available": False, "label": "Unavailable"}


def get_version_text(config):
    candidate_paths = [
        Path(config.get("update_repo_dir", "")) / "VERSION" if config.get("update_repo_dir") else None,
        BASE_DIR.parent / "VERSION",
        Path.cwd() / "VERSION",
    ]
    for path in candidate_paths:
        if not path:
            continue
        value = read_text_file(path)
        if value:
            return value
    return SERVICE_VERSION


def get_recent_log_entries(level=None, limit=20):
    items = list(RECENT_LOGS)
    if level:
        items = [item for item in items if item["level"] == level]
    return items[-limit:]


def get_last_log_entry(level=None):
    entries = get_recent_log_entries(level=level, limit=1)
    return entries[0] if entries else None


def get_recent_device_log_lines(limit=80):
    return trim_text_lines(read_text_file(LOG_FILE), limit=limit)


def build_diagnostics_text(config, state):
    overview = collect_admin_overview(config, state)
    health = overview["health"]
    diagnostics = overview["diagnostics"]
    lines = [
        f"Device name: {health.get('device_name') or '-'}",
        f"Software version: {health.get('software_version') or '-'}",
        f"PWA URL: {health.get('pwa_url') or '-'}",
        f"Internet: {health.get('internet_status') or '-'}",
        f"Chromium: {health.get('chromium_status') or '-'}",
        f"Mode: {diagnostics.get('mode') or '-'}",
        f"Uptime: {health.get('uptime_human') or '-'}",
        f"Service uptime: {diagnostics.get('service_uptime_human') or '-'}",
        f"Wi-Fi SSID: {health.get('wifi_ssid') or '-'}",
        f"IP addresses: {', '.join(health.get('ip_addresses') or []) or '-'}",
        f"Last update: {diagnostics.get('last_update_message') or '-'}",
        f"Display warning: {diagnostics.get('display_warning') or '-'}",
        "",
        "Recent warnings/errors:",
    ]
    for item in diagnostics.get("recent_warnings", []) + diagnostics.get("recent_errors", []):
        lines.append(f"- [{item.get('level')}] {item.get('message')}")
    lines.extend(["", "Recent log tail:"])
    lines.extend(diagnostics.get("recent_log_lines", []))
    return "\n".join(lines).strip()


def collect_admin_overview(config, state):
    with state["lock"]:
        chromium_process = state.get("chromium_process")
        current_mode = state.get("current_mode")
        admin_unlocked = state.get("admin_unlocked", False)
        admin_deadline = state.get("admin_deadline", 0.0)
        admin_entry_reason = state.get("admin_entry_reason")
        update_state = dict(state.get("update", {}))
        service_started_at = state.get("service_started_at", time.time())

    online = has_network()
    display_status = get_display_status(state)
    pairing_status = get_pairing_status(config)
    memory_usage = get_memory_usage()
    disk_usage = get_disk_usage()
    uptime_seconds = get_uptime_seconds()
    service_uptime_seconds = max(0, int(time.time() - service_started_at))
    current_mode_label = current_mode or "starting"
    if current_mode_label == "app":
        current_mode_label = "kiosk"
    elif current_mode_label == "admin" and not admin_unlocked:
        current_mode_label = "locked"

    if chromium_process is None:
        chromium_status = "Not running"
    elif chromium_process.poll() is None:
        chromium_status = "Running"
    else:
        chromium_status = f"Stopped ({chromium_process.poll()})"

    last_warning = get_last_log_entry("warning")
    last_error = get_last_log_entry("error")

    health = {
        "device_health": "Healthy" if online and not display_status.get("warning") else "Attention needed",
        "software_version": get_version_text(config),
        "device_name": socket.gethostname(),
        "pwa_url": config.get("pwa_url"),
        "internet_status": "Online" if online else "Offline",
        "internet_online": online,
        "chromium_status": chromium_status,
        "pairing_status": pairing_status["label"],
        "pairing_available": pairing_status["available"],
        "ip_addresses": get_ip_addresses(),
        "wifi_ssid": get_connected_wifi_ssid(),
        "uptime_seconds": uptime_seconds,
        "uptime_human": format_uptime(uptime_seconds) if uptime_seconds is not None else "Unavailable",
        "disk_usage": disk_usage,
        "memory_usage": memory_usage,
        "cpu_temperature_c": get_cpu_temperature_c(),
        "last_update_check_at": update_state.get("updated_at"),
        "last_update_message": update_state.get("message"),
        "last_warning": last_warning["message"] if last_warning else None,
        "last_error": last_error["message"] if last_error else None,
    }

    update_config = get_update_config(config)
    repo_dir = update_config.get("repo_dir")
    can_manage_updates = bool(repo_dir and (Path(repo_dir) / ".git").exists())
    diagnostics = {
        "mode": current_mode_label,
        "admin_entry_reason": admin_entry_reason,
        "admin_deadline_seconds": max(0, int(admin_deadline - monotonic_seconds())) if admin_deadline else 0,
        "service_uptime_seconds": service_uptime_seconds,
        "service_uptime_human": format_uptime(service_uptime_seconds),
        "display_warning": display_status.get("warning"),
        "recent_warnings": get_recent_log_entries(level="warning", limit=5),
        "recent_errors": get_recent_log_entries(level="error", limit=5),
        "recent_log_lines": get_recent_device_log_lines(limit=60),
        "last_update_message": update_state.get("message"),
        "last_update_check_at": update_state.get("updated_at"),
    }

    return {
        "health": health,
        "settings": {
            "pwa_url": config.get("pwa_url"),
            "admin_timeout_seconds": ADMIN_INACTIVITY_TIMEOUT_SECONDS,
            "admin_timeout_editable": False,
            "admin_pin_configured": bool(config.get("admin_pin")),
            "auto_update_on_boot": bool(config.get("auto_update_on_boot", True)),
        },
        "display": {
            "display": dict(config.get("display", {})),
            "status": display_status,
        },
        "updates": {
            "current_version": health["software_version"],
            "status": update_state,
            "can_check": can_manage_updates,
            "can_install": can_manage_updates,
        },
        "diagnostics": diagnostics,
        "actions": {
            "restart_chromium": True,
            "return_to_kiosk": True,
            "reboot": False,
            "shutdown": False,
            "factory_reset": False,
        },
    }
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


def save_admin_settings(config, state, payload):
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object.")

    pwa_url = require_valid_http_url(payload.get("pwa_url"))
    with state["lock"]:
        state["config"]["pwa_url"] = pwa_url
        save_config(state["config"])
        config["pwa_url"] = pwa_url
    log(f"Admin updated PWA URL to {pwa_url}.")
    return {"message": "Stay Compass settings saved.", "pwa_url": pwa_url}


def change_admin_pin(config, state, payload):
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object.")
    new_pin = validate_new_pin(payload.get("new_pin"))
    confirm_pin = str(payload.get("confirm_pin") or "").strip()
    if new_pin != confirm_pin:
        raise ValueError("New PIN and confirmation PIN must match.")

    with state["lock"]:
        state["config"]["admin_pin"] = new_pin
        save_config(state["config"])
        config["admin_pin"] = new_pin
    log("Admin PIN updated from local settings.")
    return {"message": "Admin PIN updated."}


def restart_chromium_session(state):
    with state["lock"]:
        chromium_process = state.get("chromium_process")
        current_mode = state.get("current_mode") or "app"
        if current_mode == "update":
            raise RuntimeError("Chromium cannot be restarted while an update is in progress.")
        state["requested_mode"] = "admin" if current_mode == "admin" else "app"
        state["local_admin_navigation_pending"] = False
        state["local_app_navigation_pending"] = False
        state["chromium_process"] = None
    terminate_process(chromium_process)
    log(f"Chromium restart requested from local admin while in {current_mode} mode.")
    return {"message": "Chromium restart requested."}


def handle_admin_action(config, state, payload):
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object.")

    action = str(payload.get("action") or "").strip()
    if action == "return_to_kiosk":
        request_app_mode_local_navigation(state, "admin return to kiosk")
        log("Return to kiosk requested from local admin.")
        return {
            "message": "Returning to the Stay Compass kiosk.",
            "pwa_url": config.get("pwa_url"),
        }
    if action == "restart_chromium":
        return restart_chromium_session(state)
    if action == "check_updates":
        log("Manual update check requested from local admin.")
        update_config = find_available_update(config, state)
        return {
            "message": state.get("update", {}).get("message"),
            "update_available": bool(update_config),
            "status": dict(state.get("update", {})),
        }
    if action == "install_update":
        log("Manual update install requested from local admin.")
        update_config = find_available_update(config, state)
        if not update_config:
            return {
                "message": state.get("update", {}).get("message") or "No update is available right now.",
                "status": dict(state.get("update", {})),
            }
        apply_available_update(update_config, state)
        return {"message": "Installing update...", "status": dict(state.get("update", {}))}
    if action in {"reboot", "shutdown", "factory_reset"}:
        raise RuntimeError(f"{action.replace('_', ' ').title()} is not available from local admin yet.")
    raise ValueError("Unsupported admin action.")


def make_admin_handler(config, state):
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

        def read_json(self):
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8")
            if not body.strip():
                return {}
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object.")
            return payload

        def read_query(self, parsed_url):
            return {key: values[0] for key, values in parse_qs(parsed_url.query).items()}

        def do_GET(self):
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            query = self.read_query(parsed_url)

            if path == "/" or path == "/admin":
                body = ADMIN_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/updating":
                body = UPDATE_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/api/status":
                with state["lock"]:
                    auto_return_pending = bool(state.get("auto_return_pending"))
                self.send_json(
                    {
                        "online": has_network(),
                        "auto_return_pending": auto_return_pending,
                        "pwa_url": config.get("pwa_url"),
                    }
                )
                return

            if path == "/api/update-status":
                self.send_json(state.get("update", {}))
                return

            if path == "/api/admin-overview":
                if not valid_admin_pin(config, query):
                    self.send_json(
                        {"error": "Invalid admin PIN."},
                        status=HTTPStatus.UNAUTHORIZED,
                    )
                    return
                self.send_json(collect_admin_overview(config, state))
                return

            if path == "/api/display-settings":
                if not valid_admin_pin(config, query):
                    self.send_json(
                        {"error": "Invalid admin PIN."},
                        status=HTTPStatus.UNAUTHORIZED,
                    )
                    return

                with state["lock"]:
                    display_config = dict(state["config"].get("display", {}))
                display_status = get_display_status(state)
                self.send_json(
                    {
                        "display": display_config,
                        "warning": display_status.get("warning"),
                        "message": (
                            "Night mode is currently active."
                            if display_status.get("night_active")
                            else "Day brightness is currently active."
                        ),
                        "status": display_status,
                    }
                )
                return

            self.send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self):
            path = urlparse(self.path).path

            if path == "/api/activity":
                record_user_interaction(state, "admin page activity", extend_admin=True)
                self.send_json({"ok": True})
                return

            if path == "/api/open-admin":
                if request_admin_mode(
                    state,
                    "extension hotspot",
                    prefer_local_navigation=True,
                    entry_reason="manual",
                ):
                    self.send_json({"message": "Opening admin mode..."})
                else:
                    self.send_json(
                        {"error": "Admin access is temporarily locked."},
                        status=HTTPStatus.TOO_MANY_REQUESTS,
                )
                return

            if path == "/api/unlock":
                form = self.read_form()

                now = monotonic_seconds()
                with state["lock"]:
                    lockout_until = state.get("admin_lockout_until", 0.0)

                    if lockout_until > now:
                        remaining = max(1, int(lockout_until - now))
                        log(f"Admin PIN blocked by lockout; {remaining}s remaining.")
                        self.send_json(
                            {
                                "error": (
                                    "Admin access is locked for 5 minutes after repeated "
                                    "invalid PIN attempts."
                                )
                            },
                            status=HTTPStatus.TOO_MANY_REQUESTS,
                        )
                        return

                if not valid_admin_pin(config, form):
                    with state["lock"]:
                        state["admin_failed_attempts"] = state.get("admin_failed_attempts", 0) + 1
                        failed_attempts = state["admin_failed_attempts"]
                        log(f"Wrong admin PIN attempt {failed_attempts}/3.")

                        if failed_attempts >= 3:
                            state["admin_failed_attempts"] = 0
                            state["admin_lockout_until"] = now + ADMIN_LOCKOUT_SECONDS
                            state["requested_mode"] = "app"
                            state["local_admin_navigation_pending"] = False
                            state["local_app_navigation_pending"] = False
                            state["admin_deadline"] = 0.0
                            state["admin_unlocked"] = False
                            state["admin_last_activity_at"] = 0.0
                            state["admin_entry_reason"] = None
                            state["auto_return_pending"] = False
                            state["wifi_connect_started_at"] = 0.0
                            state["wifi_connect_success_at"] = 0.0
                            log("Admin access locked for 5 minutes after 3 failed PIN attempts.")
                            self.send_json(
                                {
                                    "error": (
                                        "Too many invalid PIN attempts. "
                                        "Admin access is locked for 5 minutes."
                                    )
                                },
                                status=HTTPStatus.TOO_MANY_REQUESTS,
                            )
                            return

                    self.send_json(
                        {"error": "Invalid admin PIN."},
                        status=HTTPStatus.UNAUTHORIZED,
                    )
                    return

                with state["lock"]:
                    state["admin_failed_attempts"] = 0
                    state["admin_unlocked"] = True
                self.send_json({"message": "Admin mode unlocked."})
                return

            if path == "/api/admin-status":
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
                        "display_warning": get_display_status(state).get("warning"),
                    }
                )
                return

            if path == "/api/diagnostics":
                form = self.read_form()

                if not valid_admin_pin(config, form):
                    self.send_json(
                        {"error": "Invalid admin PIN."},
                        status=HTTPStatus.UNAUTHORIZED,
                    )
                    return

                overview = collect_admin_overview(config, state)
                overview["diagnostics"]["diagnostics_text"] = build_diagnostics_text(config, state)
                self.send_json(overview["diagnostics"])
                return

            if path == "/api/networks":
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

            if path == "/api/wifi":
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

                with state["lock"]:
                    state["wifi_connect_started_at"] = monotonic_seconds()
                    state["wifi_connect_success_at"] = 0.0

                try:
                    connect_wifi(ssid, form.get("password", ""))
                    with state["lock"]:
                        state["wifi_connect_success_at"] = monotonic_seconds()
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

            if path == "/api/wifi-disconnect":
                form = self.read_form()

                if not valid_admin_pin(config, form):
                    self.send_json(
                        {"error": "Invalid admin PIN."},
                        status=HTTPStatus.UNAUTHORIZED,
                    )
                    return

                try:
                    result = disconnect_wifi()
                    self.send_json(
                        {
                            "message": (
                                "Wi-Fi disconnected. Saved network profiles were left intact."
                            ),
                            "device": result.get("device"),
                        }
                    )
                except Exception as error:
                    with state["lock"]:
                        state["wifi_connect_started_at"] = 0.0
                    self.send_json(
                        {"error": str(error)},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                return

            if path == "/api/settings/save":
                try:
                    payload = self.read_json()

                    if not valid_admin_pin(config, payload):
                        self.send_json(
                            {"error": "Invalid admin PIN."},
                            status=HTTPStatus.FORBIDDEN,
                        )
                        return

                    self.send_json(save_admin_settings(config, state, payload))
                except (json.JSONDecodeError, ValueError) as error:
                    self.send_json(
                        {"error": str(error)},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                except OSError:
                    logging.exception("Failed to save local admin settings.")
                    self.send_json(
                        {"error": "Unable to save local settings right now."},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                return

            if path == "/api/admin-pin":
                try:
                    payload = self.read_json()

                    if not valid_admin_pin(config, payload):
                        self.send_json(
                            {"error": "Invalid admin PIN."},
                            status=HTTPStatus.FORBIDDEN,
                        )
                        return

                    self.send_json(change_admin_pin(config, state, payload))
                except (json.JSONDecodeError, ValueError) as error:
                    self.send_json(
                        {"error": str(error)},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                except OSError:
                    logging.exception("Failed to save admin PIN change.")
                    self.send_json(
                        {"error": "Unable to save the new admin PIN right now."},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                return

            if path == "/api/display-settings":
                try:
                    payload = self.read_json()

                    if not valid_admin_pin(config, payload):
                        self.send_json(
                            {"error": "Invalid admin PIN."},
                            status=HTTPStatus.FORBIDDEN,
                        )
                        return

                    with state["lock"]:
                        display_config = update_display_config(state["config"], payload)
                        state["display_override_brightness"] = None
                        state["display_override_mode"] = None
                        state["display_wake_until"] = 0.0
                        save_config(state["config"])

                    sync_display_brightness(state, force=True)
                    display_status = get_display_status(state)
                    self.send_json(
                        {
                            "ok": True,
                            "display": display_config,
                            "warning": display_status.get("warning"),
                        }
                    )
                except (json.JSONDecodeError, ValueError) as error:
                    self.send_json(
                        {"error": str(error)},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                except OSError:
                    logging.exception("Failed to save display settings.")
                    self.send_json(
                        {"error": "Unable to save display settings right now."},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                except Exception:
                    logging.exception("Unexpected error while saving display settings.")
                    self.send_json(
                        {"error": "Unable to apply display settings right now."},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                return

            if path == "/api/display-preview-night":
                form = self.read_form()

                if not valid_admin_pin(config, form):
                    self.send_json(
                        {"error": "Invalid admin PIN."},
                        status=HTTPStatus.UNAUTHORIZED,
                    )
                    return

                with state["lock"]:
                    display_config = dict(state["config"].get("display", {}))
                    state["display_override_brightness"] = display_config["night_brightness"]
                    state["display_override_mode"] = "night preview"

                sync_display_brightness(state, force=True)
                display_status = get_display_status(state)
                self.send_json(
                    {
                        "warning": display_status.get("warning"),
                        "message": "Night brightness preview applied.",
                        "status": display_status,
                    }
                )
                return

            if path == "/api/display-restore-brightness":
                form = self.read_form()

                if not valid_admin_pin(config, form):
                    self.send_json(
                        {"error": "Invalid admin PIN."},
                        status=HTTPStatus.UNAUTHORIZED,
                    )
                    return

                with state["lock"]:
                    state["display_override_brightness"] = MAX_BRIGHTNESS
                    state["display_override_mode"] = "full brightness restore"

                sync_display_brightness(state, force=True)
                display_status = get_display_status(state)
                self.send_json(
                    {
                        "warning": display_status.get("warning"),
                        "message": "Full brightness restored.",
                        "status": display_status,
                    }
                )
                return

            if path == "/api/admin-action":
                try:
                    payload = self.read_json()

                    if not valid_admin_pin(config, payload):
                        self.send_json(
                            {"error": "Invalid admin PIN."},
                            status=HTTPStatus.FORBIDDEN,
                        )
                        return

                    response = handle_admin_action(config, state, payload)
                    self.send_json(response)
                except (json.JSONDecodeError, ValueError) as error:
                    self.send_json(
                        {"error": str(error)},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                except RuntimeError as error:
                    self.send_json(
                        {"error": str(error)},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                except Exception:
                    logging.exception("Unexpected admin action failure.")
                    self.send_json(
                        {"error": "Unable to complete that admin action right now."},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                return

            if path == "/api/open-app":
                request_app_mode_local_navigation(state, "admin page button")
                self.send_json(
                    {
                        "message": "Opening Stay Compass...",
                        "pwa_url": config.get("pwa_url"),
                    }
                )
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
    state = {
        "config": config,
        "chromium_process": None,
        "lock": threading.Lock(),
        "requested_mode": None,
        "local_admin_navigation_pending": False,
        "local_app_navigation_pending": False,
        "shutdown": False,
        "current_mode": None,
        "admin_unlocked": False,
        "admin_deadline": 0.0,
        "admin_last_activity_at": 0.0,
        "admin_failed_attempts": 0,
        "admin_lockout_until": 0.0,
        "admin_entry_reason": None,
        "auto_return_pending": False,
        "wifi_connect_started_at": 0.0,
        "wifi_connect_success_at": 0.0,
        "service_started_at": time.time(),
        "activity_monitor_process": None,
        "display_last_applied": None,
        "display_last_reason": None,
        "display_override_brightness": None,
        "display_override_mode": None,
        "display_command_warning": None,
        "display_monitor_warning": None,
        "display_wake_until": 0.0,
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
    start_activity_monitor(state)
    sync_display_brightness(state, force=True)

    chromium_process = None
    current_mode = None
    offline_since = None
    recovery_online_since = None
    recovery_online_streak = 0
    recovery_wait_reason = None
    update_checked = False

    try:
        while True:
            online = has_network()
            target_mode = "app"

            with state["lock"]:
                requested_mode = state.get("requested_mode")
                local_admin_navigation_pending = state.get("local_admin_navigation_pending", False)
                local_app_navigation_pending = state.get("local_app_navigation_pending", False)
                admin_deadline = state.get("admin_deadline", 0.0)
                admin_unlocked = state.get("admin_unlocked", False)
                admin_entry_reason = state.get("admin_entry_reason")
                admin_last_activity_at = state.get("admin_last_activity_at", 0.0)
                auto_return_pending = state.get("auto_return_pending", False)
                wifi_connect_success_at = state.get("wifi_connect_success_at", 0.0)

            if not online:
                if recovery_online_since is not None:
                    log("Offline recovery: connectivity dropped again before return; resetting stability timer.")
                recovery_online_since = None
                recovery_online_streak = 0
                recovery_wait_reason = None

                if offline_since is None:
                    offline_since = time.monotonic()

                if time.monotonic() - offline_since >= OFFLINE_ADMIN_DELAY_SECONDS:
                    target_mode = "admin"
                    if current_mode != "admin" and requested_mode != "admin":
                        log("Offline recovery screen opened after connectivity loss.")
                        if request_admin_mode(
                            state,
                            "offline connectivity recovery",
                            prefer_local_navigation=False,
                            entry_reason="offline_recovery",
                        ):
                            with state["lock"]:
                                requested_mode = state.get("requested_mode")
                                local_admin_navigation_pending = state.get("local_admin_navigation_pending", False)
                                local_app_navigation_pending = state.get("local_app_navigation_pending", False)
                                admin_deadline = state.get("admin_deadline", 0.0)
                                admin_unlocked = state.get("admin_unlocked", False)
                                admin_entry_reason = state.get("admin_entry_reason")
                                admin_last_activity_at = state.get("admin_last_activity_at", 0.0)
                                auto_return_pending = state.get("auto_return_pending", False)
                                wifi_connect_success_at = state.get("wifi_connect_success_at", 0.0)
                elif current_mode is None:
                    log("Network offline. Waiting before admin mode...")
                    time.sleep(5)
                    continue
            else:
                offline_since = None

                if current_mode == "admin" and admin_entry_reason == "offline_recovery":
                    now = monotonic_seconds()

                    if recovery_online_since is None:
                        recovery_online_since = now
                        recovery_online_streak = 1
                        recovery_wait_reason = "stability"
                        log("Offline recovery: connectivity restored; waiting for stability before returning.")
                    else:
                        recovery_online_streak += 1

                    stable_seconds = now - recovery_online_since
                    success_age = now - wifi_connect_success_at if wifi_connect_success_at else None
                    recent_activity_age = now - admin_last_activity_at if admin_last_activity_at else None

                    if auto_return_pending:
                        if recovery_wait_reason != "returning":
                            recovery_wait_reason = "returning"
                            log("Offline recovery: local return to the configured PWA is pending.")
                    elif (
                        recovery_online_streak < OFFLINE_RECOVERY_SUCCESS_STREAK
                        or stable_seconds < OFFLINE_RECOVERY_STABLE_SECONDS
                    ):
                        if recovery_wait_reason != "stability":
                            recovery_wait_reason = "stability"
                            log("Offline recovery: waiting for connectivity to remain stable.")
                    elif (
                        wifi_connect_success_at
                        and success_age is not None
                        and success_age < OFFLINE_RECOVERY_POST_CONNECT_DELAY_SECONDS
                    ):
                        if recovery_wait_reason != "post_connect_delay":
                            recovery_wait_reason = "post_connect_delay"
                            log("Offline recovery: Wi-Fi reconnect succeeded; pausing briefly before return.")
                    elif (
                        not wifi_connect_success_at
                        and admin_unlocked
                        and admin_last_activity_at
                        and recent_activity_age is not None
                        and recent_activity_age < OFFLINE_RECOVERY_IDLE_GRACE_SECONDS
                    ):
                        if recovery_wait_reason != "admin_activity":
                            recovery_wait_reason = "admin_activity"
                            log("Offline recovery: installer activity detected; waiting before automatic return.")
                    elif queue_offline_recovery_return(state, "stable connectivity restored"):
                        recovery_wait_reason = "returning"
                else:
                    recovery_online_since = None
                    recovery_online_streak = 0
                    recovery_wait_reason = None

                if not update_checked:
                    update_checked = True
                    maybe_update_on_boot(config, state)
                    chromium_process = state.get("chromium_process")
                    current_mode = "update" if chromium_process else None
                    with state["lock"]:
                        state["current_mode"] = current_mode

            if current_mode == "admin" and admin_deadline and admin_deadline <= monotonic_seconds():
                log("Admin inactivity timeout reached; returning to Stay Compass app.")
                request_app_mode(state, "admin inactivity timeout")
                with state["lock"]:
                    requested_mode = state.get("requested_mode")

            if requested_mode in {"app", "admin"}:
                target_mode = requested_mode
                with state["lock"]:
                    state["requested_mode"] = None
                    state["local_admin_navigation_pending"] = False
                    state["local_app_navigation_pending"] = False
            elif current_mode == "admin":
                target_mode = "admin"

            target_url = pwa_url if target_mode == "app" else admin_url

            if current_mode != target_mode:
                if (
                    target_mode == "admin"
                    and requested_mode == "admin"
                    and local_admin_navigation_pending
                    and current_mode == "app"
                    and chromium_process is not None
                    and chromium_process.poll() is None
                ):
                    log("Opening admin mode without relaunch; Chromium is already navigating locally.")
                    current_mode = target_mode
                    with state["lock"]:
                        state["current_mode"] = current_mode
                elif (
                    target_mode == "app"
                    and requested_mode == "app"
                    and local_app_navigation_pending
                    and current_mode == "admin"
                    and chromium_process is not None
                    and chromium_process.poll() is None
                ):
                    log("Opening Stay Compass app without relaunch; Chromium is already navigating locally.")
                    current_mode = target_mode
                    with state["lock"]:
                        state["current_mode"] = current_mode
                elif target_mode == "admin":
                    log("Opening admin mode.")
                    terminate_process(chromium_process)
                    chromium_process = launch_chromium(target_url)
                    state["chromium_process"] = chromium_process
                    current_mode = target_mode
                    with state["lock"]:
                        state["current_mode"] = current_mode
                else:
                    log("Opening Stay Compass app.")
                    terminate_process(chromium_process)
                    chromium_process = launch_chromium(target_url)
                    state["chromium_process"] = chromium_process
                    current_mode = target_mode
                    with state["lock"]:
                        state["current_mode"] = current_mode

                if current_mode != "admin":
                    clear_admin_session(state)
                    reset_admin_entry_state(state)
                    recovery_online_since = None
                    recovery_online_streak = 0
                    recovery_wait_reason = None

            if chromium_process.poll() is not None:
                log("Chromium exited. Restarting current mode...")
                chromium_process = launch_chromium(target_url)
                state["chromium_process"] = chromium_process
                with state["lock"]:
                    state["current_mode"] = current_mode

            sync_display_brightness(state)
            time.sleep(1 if current_mode == "admin" else 5)

    except KeyboardInterrupt:
        log("Stay Compass Device Service stopped.")

        state["shutdown"] = True
        terminate_process(state.get("activity_monitor_process"))
        log("Stopping Chromium...")
        terminate_process(chromium_process)


if __name__ == "__main__":
    main()
