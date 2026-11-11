#!/usr/bin/env python3
"""Start the local API and Vite together; stop both when either exits or Ctrl-C arrives."""
from pathlib import Path
import os
import signal
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
if not (root / "dashboard/node_modules").is_dir():
    raise SystemExit("Frontend dependencies missing. Run: cd dashboard && npm ci")
try:
    import fastapi, uvicorn  # noqa: F401
except ImportError:
    raise SystemExit('API dependencies missing. Run: python -m pip install -e ".[dashboard,research,dev]"')

environment = os.environ.copy()
environment["PYTHONPATH"] = str(root / "src") + os.pathsep + environment.get("PYTHONPATH", "")
commands = [([sys.executable, "-m", "uvicorn", "quant_dashboard.app:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "info"], root),
            (["npm", "run", "dev"], root / "dashboard")]
processes = []


def stop(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop)
try:
    for command, directory in commands:
        processes.append(subprocess.Popen(command, cwd=directory, env=environment, start_new_session=True))
    print("\nDashboard: http://127.0.0.1:5173\nAPI docs:  http://127.0.0.1:8000/docs\nCtrl-C stops both services.\n", flush=True)
    while all(p.poll() is None for p in processes):
        time.sleep(0.3)
except KeyboardInterrupt:
    pass
finally:
    for process in processes:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
