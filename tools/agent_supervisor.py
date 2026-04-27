from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / "runtime"
PID_FILE = RUNTIME_DIR / "agents.pid"
STATUS_FILE = RUNTIME_DIR / "agent_supervisor.json"
LOG_FILE = ROOT / "logs" / "agents_supervisor.log"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_pid() -> int | None:
    try:
        if PID_FILE.exists():
            return int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None
    return None


def _process_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


def _write_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = _now()
    STATUS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def status() -> Dict[str, Any]:
    pid = _read_pid()
    running = _process_running(pid)
    return {
        "service": "launch.py",
        "pid": pid,
        "running": running,
        "state": "running" if running else "stopped",
        "pid_file": str(PID_FILE),
        "log_file": str(LOG_FILE),
        "status_file": str(STATUS_FILE),
        "updated_at": _now(),
    }


def start() -> Dict[str, Any]:
    current = status()
    if current["running"]:
        return _write_status({**current, "action": "start", "message": "Agents already running."})

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    with LOG_FILE.open("ab") as log:
        process = subprocess.Popen(
            [python, "launch.py"],
            cwd=str(ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            close_fds=True,
        )
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    time.sleep(1)
    new_status = status()
    return _write_status({**new_status, "action": "start", "message": "Agents started."})


def stop(timeout: float = 12.0) -> Dict[str, Any]:
    current = status()
    pid = current.get("pid")
    if not current["running"]:
        if PID_FILE.exists():
            PID_FILE.unlink()
        return _write_status({**current, "action": "stop", "message": "Agents already stopped."})

    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=timeout)
        else:
            os.kill(int(pid), signal.SIGTERM)
            deadline = time.time() + timeout
            while time.time() < deadline and _process_running(int(pid)):
                time.sleep(0.25)
            if _process_running(int(pid)):
                os.kill(int(pid), signal.SIGKILL)
    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()

    time.sleep(1)
    new_status = status()
    return _write_status({**new_status, "action": "stop", "message": "Agents stopped."})


def restart() -> Dict[str, Any]:
    stop_result = stop()
    start_result = start()
    return _write_status({
        **start_result,
        "action": "restart",
        "message": "Agents restarted.",
        "stop_result": stop_result,
    })


def main() -> None:
    parser = argparse.ArgumentParser(description="Start/stop/restart MIRO launch.py agents.")
    parser.add_argument("action", choices=["status", "start", "stop", "restart"])
    args = parser.parse_args()
    actions = {
        "status": status,
        "start": start,
        "stop": stop,
        "restart": restart,
    }
    json.dump(actions[args.action](), sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
