import contextlib
import importlib.util
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


WORKSPACE = Path(__file__).resolve().parents[1]
HELPER_PATH = WORKSPACE / "scripts" / "stay-compass-tailscale-helper.py"
DEVICE_PATH = WORKSPACE / "device" / "stay-compass-device.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = load_module("stay_compass_tailscale_helper", HELPER_PATH)
device = load_module("stay_compass_device", DEVICE_PATH)


def result(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class RemoteSupportTests(unittest.TestCase):
    def test_redacts_auth_keys(self):
        text = "failed with tskey-auth-k123456 and more"
        self.assertNotIn("tskey-auth-k123456", helper.redact_sensitive_text(text))
        self.assertIn("<redacted>", helper.redact_sensitive_text(text))

    def test_persistent_device_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            device_id_path = Path(temp_dir) / "device-id"
            first = helper.ensure_device_id(device_id_path)
            second = helper.ensure_device_id(device_id_path)
            self.assertEqual(first, second)
            self.assertRegex(first, r"^SC-\d{6}$")

    def test_status_when_tailscale_not_installed(self):
        with mock.patch.object(helper, "command_exists", return_value=False), mock.patch.object(
            helper, "ensure_device_id", return_value="SC-123456"
        ):
            status = helper.collect_status()
        self.assertFalse(status["installed"])
        self.assertEqual(status["status_label"], "Not installed")

    def test_status_when_service_stopped(self):
        with mock.patch.object(helper, "command_exists", return_value=True), mock.patch.object(
            helper, "service_is_active", return_value=False
        ), mock.patch.object(helper, "ensure_device_id", return_value="SC-123456"):
            status = helper.collect_status()
        self.assertTrue(status["installed"])
        self.assertFalse(status["service_running"])
        self.assertEqual(status["backend_state"], "Service stopped")

    def test_status_when_installed_but_not_enrolled(self):
        with mock.patch.object(helper, "command_exists", return_value=True), mock.patch.object(
            helper, "service_is_active", return_value=True
        ), mock.patch.object(helper, "load_tailscale_status_payload", side_effect=RuntimeError("login required")), mock.patch.object(
            helper, "ensure_device_id", return_value="SC-123456"
        ):
            status = helper.collect_status()
        self.assertTrue(status["installed"])
        self.assertEqual(status["status_label"], "Not enrolled")
        self.assertFalse(status["connected"])

    def test_status_when_connected(self):
        payload = {
            "BackendState": "Running",
            "Self": {"DNSName": "stay-compass-123456.tail.example.ts.net", "HostName": "stay-compass-123456"},
            "Health": [],
        }
        with mock.patch.object(helper, "command_exists", return_value=True), mock.patch.object(
            helper, "service_is_active", return_value=True
        ), mock.patch.object(helper, "load_tailscale_status_payload", return_value=payload), mock.patch.object(
            helper, "read_tailscale_ipv4", return_value="100.64.0.10"
        ), mock.patch.object(helper, "ensure_device_id", return_value="SC-123456"):
            status = helper.collect_status()
        self.assertTrue(status["connected"])
        self.assertTrue(status["enrolled"])
        self.assertEqual(status["tailscale_ip"], "100.64.0.10")

    def test_status_when_disconnected_after_reboot(self):
        payload = {
            "BackendState": "Stopped",
            "Self": {"DNSName": "stay-compass-123456.tail.example.ts.net", "HostName": "stay-compass-123456"},
            "Health": ["network unreachable"],
        }
        with mock.patch.object(helper, "command_exists", return_value=True), mock.patch.object(
            helper, "service_is_active", return_value=True
        ), mock.patch.object(helper, "load_tailscale_status_payload", return_value=payload), mock.patch.object(
            helper, "read_tailscale_ipv4", return_value=""
        ), mock.patch.object(helper, "ensure_device_id", return_value="SC-123456"):
            status = helper.collect_status()
        self.assertFalse(status["connected"])
        self.assertEqual(status["backend_state"], "Stopped")

    def test_failed_enrollment_redacts_auth_key(self):
        stdout = io.StringIO()
        with mock.patch.object(helper, "ensure_device_id", return_value="SC-123456"), mock.patch.object(
            helper, "command_exists", return_value=True
        ), mock.patch.object(helper, "ensure_service_running"), mock.patch.object(
            helper, "tailscale_up_with_auth_key", side_effect=RuntimeError("invalid tskey-auth-k123456")
        ), mock.patch.object(helper, "collect_status", return_value={"installed": True}), mock.patch(
            "sys.stdin", io.StringIO("tskey-auth-k123456")
        ), contextlib.redirect_stdout(stdout):
            exit_code = helper.main(["enroll"])

        self.assertEqual(exit_code, 1)
        self.assertIn("<redacted>", stdout.getvalue())
        self.assertNotIn("tskey-auth-k123456", stdout.getvalue())

    def test_rejects_arbitrary_command_arguments(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = helper.main(["shell", "--unsafe"])
        self.assertEqual(exit_code, 2)
        self.assertIn("Unsupported remote support operation", stdout.getvalue())

    def test_logout_requires_confirmation(self):
        state = {"lock": threading.Lock(), "remote_support_last_error": ""}
        with self.assertRaises(RuntimeError):
            device.handle_remote_support_action(state, "logout", confirm=False)

    def test_disconnect_and_logout_actions_use_allowed_helper_calls(self):
        state = {"lock": threading.Lock(), "remote_support_last_error": ""}
        with mock.patch.object(device, "run_remote_support_helper", return_value={"message": "ok"}) as helper_mock, mock.patch.object(
            device, "get_remote_support_status", return_value={"status_label": "Disconnected"}
        ):
            device.handle_remote_support_action(state, "disconnect")
            device.handle_remote_support_action(state, "logout", confirm=True)

        helper_mock.assert_any_call("down")
        helper_mock.assert_any_call("logout")


if __name__ == "__main__":
    unittest.main()
