"""Launcher configuration checks: the demo binds loopback HTTP only.

Not a production TLS test - TLS is intentionally absent for the local
loopback demo (see run_demo.py comment and docs/ARCHITECTURE.md).
"""

import importlib.util
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def _load_run_demo():
    spec = importlib.util.spec_from_file_location(
        "run_demo", ROOT / "run_demo.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LauncherConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_demo = _load_run_demo()

    def test_api_url_is_loopback_http(self):
        parsed = urlparse(self.run_demo.API_URL)
        self.assertEqual(parsed.scheme, "http")
        self.assertEqual(parsed.hostname, "127.0.0.1")

    def test_ui_url_is_loopback_http(self):
        parsed = urlparse(self.run_demo.UI_URL)
        self.assertEqual(parsed.scheme, "http")
        self.assertEqual(parsed.hostname, "127.0.0.1")

    def test_port_args_defaults_and_validation(self):
        args = self.run_demo.parse_args([])
        self.assertEqual((args.api_port, args.ui_port), (8000, 8501))
        args = self.run_demo.parse_args(
            ["--api-port", "8001", "--ui-port", "8502"]
        )
        self.assertEqual((args.api_port, args.ui_port), (8001, 8502))
        for bad in (["--api-port", "0"], ["--api-port", "70000"],
                    ["--api-port", "8501", "--ui-port", "8501"]):
            with self.assertRaises(SystemExit):
                self.run_demo.parse_args(bad)


class _FakeProcess:
    def __init__(self, poll_code=None, pid=111):
        self._code = poll_code
        self.pid = pid
        self.terminated = False
        self.killed = False

    def poll(self):
        return self._code

    def terminate(self):
        self.terminated = True
        if self._code is None:
            self._code = -15

    def wait(self, timeout=None):
        return self._code

    def kill(self):
        self.killed = True


class LauncherLifecycleTests(unittest.TestCase):
    """Mocked lifecycle checks - no real processes or sockets created."""

    @classmethod
    def setUpClass(cls):
        cls.run_demo = _load_run_demo()

    def _run(self, processes, health_results):
        spawn = iter(processes)
        with (
            mock.patch.object(self.run_demo, "port_in_use", return_value=False),
            mock.patch.object(
                self.run_demo.subprocess, "Popen",
                side_effect=lambda *a, **k: next(spawn),
            ),
            mock.patch.object(
                self.run_demo, "wait_for_http",
                side_effect=list(health_results),
            ),
            mock.patch("builtins.open", mock.mock_open()),
        ):
            try:
                return self.run_demo.main([])
            except SystemExit as exc:
                return exc.code

    def test_api_health_failure_terminates_spawned_child(self):
        api, ui = _FakeProcess(), _FakeProcess()
        code = self._run([api, ui], [False])
        self.assertEqual(code, 3)
        self.assertTrue(api.terminated)
        self.assertFalse(api.killed)
        self.assertFalse(ui.terminated)  # UI never spawned

    def test_ui_health_failure_terminates_both_children(self):
        api, ui = _FakeProcess(), _FakeProcess()
        code = self._run([api, ui], [True, False])
        self.assertEqual(code, 4)
        self.assertTrue(api.terminated)
        self.assertTrue(ui.terminated)

    def test_child_exit_returns_code_and_stops_sibling(self):
        api, ui = _FakeProcess(poll_code=0), _FakeProcess()
        code = self._run([api, ui], [True, True])
        self.assertEqual(code, 1)
        self.assertFalse(api.terminated)  # already exited on its own
        self.assertTrue(ui.terminated)


if __name__ == "__main__":
    unittest.main()
