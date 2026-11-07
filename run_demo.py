"""Local demo launcher: FastAPI on 127.0.0.1:8000 + Streamlit on 127.0.0.1:8501.

Stdlib only. Refuses to start if either port is already in use (it will not
kill an unknown process). Monitors both children - if either exits, the other
is stopped and the exit code is reported. Ctrl+C terminates only the children
it started. Logs go to artifacts/logs/.

Equivalent manual commands:

    $env:PYTHONPATH = 'src'   # PowerShell
    python -m uvicorn smart_librarian.api.app:app --host 127.0.0.1 --port 8000
    python -m streamlit run apps/streamlit_app.py --server.address 127.0.0.1 ^
        --server.port 8501
"""

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
LOG_DIR = ROOT / "artifacts" / "logs"
# Loopback-only demo: plain HTTP on 127.0.0.1 is intentional for local use;
# it is not authentication or transport security. Any remote/tunneled
# deployment requires TLS termination plus real authentication, neither of
# which exists in this local fixture.
API_HOST, UI_HOST = "127.0.0.1", "127.0.0.1"
DEFAULT_API_PORT, DEFAULT_UI_PORT = 8000, 8501
# Default URLs (kept for compatibility); --api-port/--ui-port override.
API_URL = f"http://{API_HOST}:{DEFAULT_API_PORT}"  # NOSONAR - loopback demo
UI_URL = f"http://{UI_HOST}:{DEFAULT_UI_PORT}"  # NOSONAR - loopback demo


def _port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


_MODE_APP_TARGETS = {
    "challenge": "smart_librarian.api.app:create_challenge_app",
    "public": "smart_librarian.api.app:app",
    "legacy": "smart_librarian.api.app:create_legacy_app",
}


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api-port", type=_port, default=DEFAULT_API_PORT)
    parser.add_argument("--ui-port", type=_port, default=DEFAULT_UI_PORT)
    parser.add_argument(
        "--mode", choices=sorted(_MODE_APP_TARGETS), default="challenge",
        help="challenge (default): builder-pack demo; public: real-data-only; "
             "legacy: synthetic + public domains without challenge routes.",
    )
    parser.add_argument(
        "--background", action="store_true",
        help="Windows only: register a one-time Windows Task Scheduler job "
             "for the current user that runs this same demo, so it keeps "
             "running after the launching terminal closes. Prints the "
             "generated task name and its schtasks /End stop command.",
    )
    parser.add_argument("--background-worker", action="store_true",
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.api_port == args.ui_port:
        parser.error("--api-port and --ui-port must differ")
    if args.background and args.background_worker:
        parser.error("--background and --background-worker are mutually "
                     "exclusive")
    if (args.background or args.background_worker) and os.name != "nt":
        parser.error("--background is only supported on Windows")
    return args


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def wait_for_http(url: str, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except OSError:
            time.sleep(0.4)
    return False


def main(argv=None) -> int:
    args = parse_args(argv)
    api_url = f"http://{API_HOST}:{args.api_port}"  # NOSONAR - loopback demo
    ui_url = f"http://{UI_HOST}:{args.ui_port}"  # NOSONAR - loopback demo
    worker_log = None
    if args.background_worker:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        worker_log = open(
            LOG_DIR / f"launcher-{args.api_port}-{args.ui_port}.log", "a",
            encoding="utf-8")
        sys.stdout = sys.stderr = worker_log
    # Load allowed keys from .env before capturing the environment so both
    # children see them; process env still wins inside load_dotenv.
    sys.path.insert(0, str(SRC))
    from smart_librarian.settings import load_dotenv

    load_dotenv(ROOT / ".env")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for name, port in (("API", args.api_port), ("UI", args.ui_port)):
        if port_in_use("127.0.0.1", port):
            print(
                f"Port {port} is already in use; refusing to start {name}. "
                "Stop the other process or choose different ports manually.",
                file=sys.stderr,
            )
            return 2

    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["SMART_LIBRARIAN_API_URL"] = api_url

    if args.background:
        return _launch_background(args, api_url, ui_url)

    children = []
    api_log = ui_log = None
    try:
        # Append mode: never truncate a log another launch may have written.
        api_log = open(LOG_DIR / f"api-{args.api_port}.log", "a",
                       encoding="utf-8")
        ui_log = open(LOG_DIR / f"ui-{args.ui_port}.log", "a",
                      encoding="utf-8")
        _start_api(env, api_log, children, args.api_port, api_url,
                   mode=args.mode, background_worker=args.background_worker)
        _start_ui(env, ui_log, children, args.ui_port, ui_url,
                  background_worker=args.background_worker)
        return _monitor(children)
    except KeyboardInterrupt:
        print("\nStopping demo processes...", flush=True)
        return 0
    finally:
        _terminate(children)
        for handle in (api_log, ui_log, worker_log):
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass


def _console_python() -> str:
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        candidate = exe[:-len("pythonw.exe")] + "python.exe"
        if os.path.exists(candidate):
            return candidate
    return exe


def _window_python() -> str:
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        candidate = exe[:-len("python.exe")] + "pythonw.exe"
        if os.path.exists(candidate):
            return candidate
    return ""


def _background_command(args) -> list:
    return [
        _window_python(), str(ROOT / "run_demo.py"),
        "--background-worker",
        "--mode", args.mode,
        "--api-port", str(args.api_port),
        "--ui-port", str(args.ui_port),
    ]


def _scheduler_task_name(args) -> str:
    return (f"SmartLibrarianDemo-{args.api_port}-{args.ui_port}"
            f"-{uuid.uuid4().hex[:8]}")


def _launch_background(args, api_url, ui_url) -> int:
    command = subprocess.list2cmdline(_background_command(args))
    if not _window_python():
        print(
            "Paired pythonw.exe not found next to the interpreter; "
            "background launch requires a windowless supervisor. No "
            "fallback process was launched.", file=sys.stderr, flush=True)
        return 5
    name = _scheduler_task_name(args)
    try:
        create = subprocess.run(
            ["schtasks", "/Create", "/TN", name, "/SC", "ONCE",
             "/ST", "00:00", "/TR", command],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Could not run schtasks: {exc}", file=sys.stderr,
              flush=True)
        return 5
    if create.returncode != 0:
        print(
            "Task Scheduler registration failed "
            f"({(create.stderr or create.stdout).strip()}); no fallback "
            "process was launched.", file=sys.stderr, flush=True,
        )
        return 5
    try:
        run = subprocess.run(
            ["schtasks", "/Run", "/TN", name],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(
            f"Task '{name}' was registered but could not be started "
            f"({exc}); no fallback process was launched.",
            file=sys.stderr, flush=True,
        )
        return 5
    if run.returncode != 0:
        print(
            f"Task '{name}' was registered but could not be started "
            f"({(run.stderr or run.stdout).strip()}); no fallback "
            "process was launched.",
            file=sys.stderr, flush=True,
        )
        return 5
    print(
        f"Demo registered as scheduled task '{name}' and started in "
        "the background (current user, no console window).",
        flush=True,
    )
    if not wait_for_http(f"{api_url}/api/health", timeout=60.0):
        print(
            f"API failed health check for task '{name}'; see "
            f"artifacts/logs/api-{args.api_port}.log. Stop it with: "
            f"schtasks /End /TN {name}",
            file=sys.stderr, flush=True,
        )
        return 3
    if not wait_for_http(ui_url, timeout=90.0):
        print(
            f"UI failed health check for task '{name}'; see "
            f"artifacts/logs/ui-{args.ui_port}.log. Stop it with: "
            f"schtasks /End /TN {name}",
            file=sys.stderr, flush=True,
        )
        return 4
    print(f"API ready at {api_url}", flush=True)
    print(f"UI ready at {ui_url}", flush=True)
    print(
        f"The demo runs as scheduled task '{name}' in the background "
        "for the current user; it does not survive logoff/reboot or "
        "guarantee a visible window. Stop it later with: "
        f"schtasks /End /TN {name}",
        flush=True,
    )
    return 0


def _child_spawn_kwargs(background_worker) -> dict:
    if background_worker:
        return {
            "stdin": subprocess.DEVNULL,
            "creationflags": getattr(
                subprocess, "CREATE_NO_WINDOW", 0x08000000),
        }
    return {}


def _start_api(env, log, children, port, url, mode="challenge",
               background_worker=False) -> None:
    target = _MODE_APP_TARGETS[mode]
    command = [_console_python(), "-m", "uvicorn", target,
               "--host", API_HOST, "--port", str(port)]
    if ":" in target and target.rsplit(":", 1)[1].startswith("create_"):
        command.append("--factory")
    api = subprocess.Popen(
        command,
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
        **_child_spawn_kwargs(background_worker),
    )
    # Register before any fallible wait so cleanup always owns it.
    children.append(("API", api))
    print(f"API starting (pid {api.pid}) ...", flush=True)
    if not wait_for_http(f"{url}/api/health"):
        print(f"API failed health check; see artifacts/logs/api-{port}.log",
              file=sys.stderr)
        raise SystemExit(3)
    print(f"API ready at {url}", flush=True)


def _start_ui(env, log, children, port, url,
              background_worker=False) -> None:
    ui = subprocess.Popen(
        [_console_python(), "-m", "streamlit", "run",
         str(ROOT / "apps" / "streamlit_app.py"),
         "--server.address", UI_HOST, "--server.port", str(port),
         "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
        **_child_spawn_kwargs(background_worker),
    )
    children.append(("UI", ui))
    print(f"UI starting (pid {ui.pid}) ...", flush=True)
    if not wait_for_http(url):
        print(f"UI failed health check; see artifacts/logs/ui-{port}.log",
              file=sys.stderr)
        raise SystemExit(4)
    print(f"UI ready at {url}", flush=True)
    print("Press Ctrl+C to stop both processes.", flush=True)


def _monitor(children) -> int:
    """If either child exits, report and stop the other."""
    while True:
        for name, process in children:
            code = process.poll()
            if code is not None:
                print(f"{name} exited with code {code}; stopping demo.",
                      file=sys.stderr, flush=True)
                return code or 1
        time.sleep(1.0)


def _terminate(children) -> None:
    """Terminate only the children this launcher spawned."""
    for name, process in children:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    sys.exit(main())
