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


class BackgroundLauncherTests(unittest.TestCase):
    """--background registers a scheduled task; no real spawns occur."""

    @classmethod
    def setUpClass(cls):
        cls.run_demo = _load_run_demo()

    def test_option_parses(self):
        if self.run_demo.os.name != "nt":
            self.skipTest("--background is Windows-only")
        args = self.run_demo.parse_args(["--background"])
        self.assertTrue(args.background)

    def test_non_windows_rejected(self):
        with mock.patch.object(self.run_demo.os, "name", "posix"):
            with self.assertRaises(SystemExit):
                self.run_demo.parse_args(["--background"])
            with self.assertRaises(SystemExit):
                self.run_demo.parse_args(["--background-worker"])

    def test_mutually_exclusive_flags(self):
        if self.run_demo.os.name != "nt":
            self.skipTest("Windows-only flags")
        with self.assertRaises(SystemExit):
            self.run_demo.parse_args(
                ["--background", "--background-worker"])

    def test_spawn_command_forwards_mode_and_ports_without_recursion(
            self):
        args = mock.Mock(mode="challenge", api_port=8021, ui_port=8521)
        command = self.run_demo._background_command(args)
        joined = self.run_demo.subprocess.list2cmdline(
            [str(c) for c in command])
        self.assertIn("--mode challenge", joined)
        self.assertIn("--api-port 8021", joined)
        self.assertIn("--ui-port 8521", joined)
        self.assertIn("--background-worker", command)
        self.assertNotIn("--background", command)
        self.assertTrue(str(command[1]).endswith("run_demo.py"))
        self.assertIn('"', joined)

    def test_background_command_uses_paired_pythonw(self):
        args = mock.Mock(mode="challenge", api_port=8021, ui_port=8521)
        exe = self.run_demo._background_command(args)[0]
        if self.run_demo._window_python():
            self.assertTrue(exe.lower().endswith("pythonw.exe"))
        else:
            self.assertEqual(exe, "")

    def test_console_python_swaps_pythonw(self):
        with mock.patch.object(
                self.run_demo.sys, "executable",
                r"C:\py\pythonw.exe"):
            with mock.patch.object(
                    self.run_demo.os.path, "exists", return_value=True):
                self.assertEqual(
                    self.run_demo._console_python(), r"C:\py\python.exe")
            with mock.patch.object(
                    self.run_demo.os.path, "exists", return_value=False):
                self.assertEqual(
                    self.run_demo._console_python(), r"C:\py\pythonw.exe")

    def test_child_spawn_kwargs_only_when_worker(self):
        plain = self.run_demo._child_spawn_kwargs(False)
        self.assertEqual(plain, {})
        worker = self.run_demo._child_spawn_kwargs(True)
        self.assertIs(worker["stdin"],
                      self.run_demo.subprocess.DEVNULL)
        self.assertTrue(worker["creationflags"] & 0x08000000)

    def test_start_api_uses_console_python_and_no_window(self):
        captured = {}

        def fake_popen(*a, **k):
            captured.update(k)
            captured["cmd"] = a[0]
            return _FakeProcess()

        with (
            mock.patch.object(
                self.run_demo.subprocess, "Popen", side_effect=fake_popen
            ),
            mock.patch.object(
                self.run_demo, "wait_for_http", return_value=True
            ),
            mock.patch.object(
                self.run_demo.sys, "executable", r"C:\py\pythonw.exe"
            ),
            mock.patch.object(
                self.run_demo.os.path, "exists", return_value=True
            ),
        ):
            children = []
            self.run_demo._start_api(
                {}, mock.Mock(), children, 8024,
                "http://127.0.0.1:8024", background_worker=True)
        self.assertTrue(captured["cmd"][0].lower().endswith("python.exe"))
        self.assertIs(captured["stdin"],
                      self.run_demo.subprocess.DEVNULL)
        self.assertTrue(captured["creationflags"] & 0x08000000)

    def test_task_names_unique(self):
        args = mock.Mock(api_port=8021, ui_port=8521)
        names = {self.run_demo._scheduler_task_name(args)
                 for _ in range(4)}
        self.assertEqual(len(names), 4)
        self.assertTrue(all(
            n.startswith("SmartLibrarianDemo-8021-8521-") for n in names))

    def _run_background(self, health_results, port_free=True,
                        create_rc=0, run_rc=0, create_exc=None,
                        run_exc=None):
        spawned = []
        run_calls = []

        def fake_popen(*a, **k):
            proc = _FakeProcess()
            spawned.append(proc)
            return proc

        def fake_run(cmd, **k):
            run_calls.append(cmd)
            if "/Create" in cmd and create_exc:
                raise create_exc
            if "/Run" in cmd and run_exc:
                raise run_exc
            rc = create_rc if "/Create" in cmd else run_rc
            return mock.Mock(returncode=rc,
                             stderr="denied" if rc else "",
                             stdout="")

        with (
            mock.patch.object(
                self.run_demo, "port_in_use",
                return_value=not port_free,
            ),
            mock.patch.object(
                self.run_demo.subprocess, "Popen", side_effect=fake_popen
            ),
            mock.patch.object(
                self.run_demo.subprocess, "run", side_effect=fake_run
            ),
            mock.patch.object(
                self.run_demo, "wait_for_http",
                side_effect=list(health_results),
            ),
            mock.patch("builtins.open", mock.mock_open()),
        ):
            try:
                code = self.run_demo.main(["--background"])
            except SystemExit as exc:
                code = exc.code
        return code, spawned, run_calls

    def test_occupied_port_refuses_spawn(self):
        code, spawned, run_calls = self._run_background(
            [], port_free=False)
        self.assertEqual(code, 2)
        self.assertEqual(spawned, [])
        self.assertEqual(run_calls, [])

    def test_background_registers_and_runs_task(self):
        code, spawned, run_calls = self._run_background([True, True])
        self.assertEqual(code, 0)
        self.assertEqual(spawned, [])
        self.assertEqual(len(run_calls), 2)
        create, run = run_calls
        self.assertIn("/Create", create)
        self.assertIn("/Run", run)
        self.assertNotIn("/F", create)
        self.assertNotIn("/IT", create)
        self.assertNotIn("/RU", create)
        name = create[create.index("/TN") + 1]
        self.assertTrue(name.startswith("SmartLibrarianDemo-8000-8501-"))
        self.assertIn(name, run)
        tr = create[create.index("/TR") + 1]
        self.assertIn("--mode challenge", tr)
        self.assertIn("--background-worker", tr)
        self.assertNotIn(" --background ", tr + " ")

    def test_create_failure_returns_nonzero_no_spawn(self):
        code, spawned, run_calls = self._run_background(
            [True, True], create_rc=1)
        self.assertEqual(code, 5)
        self.assertEqual(spawned, [])
        self.assertEqual(len(run_calls), 1)

    def test_run_failure_returns_nonzero(self):
        code, spawned, run_calls = self._run_background(
            [True, True], run_rc=1)
        self.assertEqual(code, 5)
        self.assertEqual(spawned, [])
        self.assertEqual(len(run_calls), 2)

    def test_create_oserror_returns_nonzero(self):
        code, spawned, _ = self._run_background(
            [True, True], create_exc=OSError("missing schtasks"))
        self.assertEqual(code, 5)
        self.assertEqual(spawned, [])

    def test_create_timeout_returns_nonzero(self):
        code, spawned, _ = self._run_background(
            [True, True],
            create_exc=self.run_demo.subprocess.TimeoutExpired(
                "schtasks", 60))
        self.assertEqual(code, 5)
        self.assertEqual(spawned, [])

    def test_run_oserror_returns_nonzero(self):
        code, spawned, run_calls = self._run_background(
            [True, True], run_exc=OSError("denied"))
        self.assertEqual(code, 5)
        self.assertEqual(spawned, [])
        self.assertEqual(len(run_calls), 2)

    def test_run_timeout_returns_nonzero(self):
        code, spawned, run_calls = self._run_background(
            [True, True],
            run_exc=self.run_demo.subprocess.TimeoutExpired(
                "schtasks", 60))
        self.assertEqual(code, 5)
        self.assertEqual(spawned, [])
        self.assertEqual(len(run_calls), 2)

    def test_missing_pythonw_returns_nonzero_no_spawn(self):
        with (
            mock.patch.object(
                self.run_demo, "port_in_use", return_value=False
            ),
            mock.patch.object(
                self.run_demo, "_window_python", return_value=""
            ),
            mock.patch.object(
                self.run_demo.subprocess, "run"
            ) as run_mock,
            mock.patch("builtins.open", mock.mock_open()),
        ):
            code = self.run_demo.main(["--background"])
        self.assertEqual(code, 5)
        run_mock.assert_not_called()

    def test_health_failure_returns_nonzero(self):
        code, spawned, _ = self._run_background([False])
        self.assertEqual(code, 3)
        code, spawned, _ = self._run_background([True, False])
        self.assertEqual(code, 4)


if __name__ == "__main__":
    unittest.main()
