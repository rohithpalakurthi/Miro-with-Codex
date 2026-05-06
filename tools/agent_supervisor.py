from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / "runtime"
PID_FILE = RUNTIME_DIR / "agents.pid"
STATUS_FILE = RUNTIME_DIR / "agent_supervisor.json"
LOG_FILE = ROOT / "logs" / "agents_supervisor.log"
WATCHDOG_PID_FILE = RUNTIME_DIR / "watchdog.pid"
WATCHDOG_LOG_FILE = ROOT / "logs" / "watchdog.log"
WEBHOOK_PID_FILE = RUNTIME_DIR / "tradingview_webhook.pid"
WEBHOOK_LOG_FILE = ROOT / "logs" / "tradingview_webhook.log"
WEBHOOK_STATUS_FILE = ROOT / "tradingview" / "bridge_status.json"
SELF_HEALER_PID_FILE = RUNTIME_DIR / "self_healing_agent.pid"
SELF_HEALER_LOG_FILE = ROOT / "logs" / "self_healing_agent.log"


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
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "PID eq {}".format(pid), "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return str(pid) in result.stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


def _run_powershell(command: str, timeout: float = 5.0) -> str:
    if os.name != "nt":
        return ""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _command_line(pid: int | None) -> str:
    if not pid or os.name != "nt":
        return ""
    command = (
        "Get-CimInstance Win32_Process -Filter \"ProcessId = {}\" "
        "| Select-Object -ExpandProperty CommandLine"
    ).format(int(pid))
    return _run_powershell(command)


def _expected_process(pid: int | None, marker: str) -> bool:
    if not _process_running(pid):
        return False
    if os.name != "nt":
        return True
    command_line = _command_line(pid).lower()
    return bool(command_line and marker.lower() in command_line and "python" in command_line)


def _port_owner(port: int) -> int | None:
    if os.name == "nt":
        output = _run_powershell(
            "Get-NetTCPConnection -LocalPort {} -State Listen -ErrorAction SilentlyContinue "
            "| Select-Object -First 1 -ExpandProperty OwningProcess".format(int(port))
        )
        try:
            return int(output.splitlines()[0].strip()) if output else None
        except Exception:
            return None
    return None


def _matching_pids(marker: str) -> List[int]:
    if os.name != "nt":
        return []
    escaped = marker.replace("'", "''")
    output = _run_powershell(
        "Get-CimInstance Win32_Process | "
        "Where-Object {{ $_.CommandLine -and $_.CommandLine.ToLower().Contains('{}') -and $_.CommandLine.ToLower().Contains('python') }} "
        "| Select-Object -ExpandProperty ProcessId".format(escaped.lower()),
        timeout=8,
    )
    pids: List[int] = []
    for line in output.splitlines():
        try:
            pids.append(int(line.strip()))
        except Exception:
            pass
    return sorted(set(pids))


def _terminate_pids(pids: List[int], timeout: float) -> None:
    for pid in sorted(set(int(p) for p in pids if p)):
        if not _process_running(pid):
            continue
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=timeout)
        else:
            os.kill(int(pid), signal.SIGTERM)


def _write_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = _now()
    STATUS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def status() -> Dict[str, Any]:
    pid = _read_pid()
    port_pid = _port_owner(5055)
    if _expected_process(port_pid, "launch.py"):
        pid = port_pid
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(pid), encoding="utf-8")
    running = _expected_process(pid, "launch.py")
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
        stale_pids = _matching_pids("launch.py")
        if stale_pids:
            _terminate_pids(stale_pids, timeout)
        if PID_FILE.exists():
            PID_FILE.unlink()
        return _write_status({**current, "action": "stop", "message": "Agents already stopped."})

    try:
        if os.name == "nt":
            pids = _matching_pids("launch.py") or [int(pid)]
            _terminate_pids(pids, timeout)
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


def watchdog_status() -> Dict[str, Any]:
    pid = None
    try:
        if WATCHDOG_PID_FILE.exists():
            pid = int(WATCHDOG_PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        pid = None
    return {
        "service": "watchdog.py",
        "pid": pid,
        "running": _process_running(pid),
        "state": "running" if _process_running(pid) else "stopped",
        "pid_file": str(WATCHDOG_PID_FILE),
        "log_file": str(WATCHDOG_LOG_FILE),
        "updated_at": _now(),
    }


def start_watchdog() -> Dict[str, Any]:
    current = watchdog_status()
    if current["running"]:
        return _write_status({**current, "action": "start_watchdog", "message": "Watchdog already running."})
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    WATCHDOG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with WATCHDOG_LOG_FILE.open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, "tools/watchdog.py", "--loop"],
            cwd=str(ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            close_fds=True,
        )
    WATCHDOG_PID_FILE.write_text(str(process.pid), encoding="utf-8")
    time.sleep(1)
    return _write_status({**watchdog_status(), "action": "start_watchdog", "message": "Watchdog started."})


def stop_watchdog(timeout: float = 8.0) -> Dict[str, Any]:
    current = watchdog_status()
    pid = current.get("pid")
    if current["running"]:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=timeout)
        else:
            os.kill(int(pid), signal.SIGTERM)
    if WATCHDOG_PID_FILE.exists():
        WATCHDOG_PID_FILE.unlink()
    time.sleep(1)
    return _write_status({**watchdog_status(), "action": "stop_watchdog", "message": "Watchdog stopped."})


def self_healer_status() -> Dict[str, Any]:
    pid = None
    try:
        if SELF_HEALER_PID_FILE.exists():
            pid = int(SELF_HEALER_PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        pid = None
    return {
        "service": "tools/self_healing_agent.py",
        "pid": pid,
        "running": _process_running(pid),
        "state": "running" if _process_running(pid) else "stopped",
        "pid_file": str(SELF_HEALER_PID_FILE),
        "log_file": str(SELF_HEALER_LOG_FILE),
        "updated_at": _now(),
    }


def start_self_healer() -> Dict[str, Any]:
    current = self_healer_status()
    if current["running"]:
        return _write_status({**current, "action": "start_self_healer", "message": "Self-healer already running."})
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    SELF_HEALER_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SELF_HEALER_LOG_FILE.open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, "tools/self_healing_agent.py", "--loop"],
            cwd=str(ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            close_fds=True,
        )
    SELF_HEALER_PID_FILE.write_text(str(process.pid), encoding="utf-8")
    time.sleep(1)
    return _write_status({**self_healer_status(), "action": "start_self_healer", "message": "Self-healer started."})


def stop_self_healer(timeout: float = 8.0) -> Dict[str, Any]:
    current = self_healer_status()
    pid = current.get("pid")
    if current["running"]:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=timeout)
        else:
            os.kill(int(pid), signal.SIGTERM)
    if SELF_HEALER_PID_FILE.exists():
        SELF_HEALER_PID_FILE.unlink()
    time.sleep(1)
    return _write_status({**self_healer_status(), "action": "stop_self_healer", "message": "Self-healer stopped."})


def webhook_status() -> Dict[str, Any]:
    pid = None
    try:
        if WEBHOOK_PID_FILE.exists():
            pid = int(WEBHOOK_PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        pid = None
    port = int(os.getenv("TRADINGVIEW_WEBHOOK_PORT", "5056") or 5056)
    port_pid = _port_owner(port)
    if _expected_process(port_pid, "tradingview/webhook_server.py") or _expected_process(port_pid, "tradingview\\webhook_server.py"):
        pid = port_pid
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        WEBHOOK_PID_FILE.write_text(str(pid), encoding="utf-8")
    running = _expected_process(pid, "tradingview/webhook_server.py") or _expected_process(pid, "tradingview\\webhook_server.py")
    return {
        "service": "tradingview/webhook_server.py",
        "pid": pid,
        "running": running,
        "state": "running" if running else "stopped",
        "pid_file": str(WEBHOOK_PID_FILE),
        "log_file": str(WEBHOOK_LOG_FILE),
        "port": port,
        "updated_at": _now(),
    }


def _port_listening(port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _write_webhook_status(port: int) -> None:
    status_payload = {
        "ngrok_url": "",
        "webhook_ok": True,
        "webhook_url": "http://localhost:{}/webhook".format(port),
        "last_signal": None,
        "alert_count": 0,
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    WEBHOOK_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    WEBHOOK_STATUS_FILE.write_text(json.dumps(status_payload, indent=2), encoding="utf-8")


def start_webhook() -> Dict[str, Any]:
    current = webhook_status()
    if current["running"]:
        port = int(current.get("port", 5056) or 5056)
        if _port_listening(port):
            _write_webhook_status(port)
            return {**webhook_status(), "action": "start_webhook", "ok": True, "message": "TradingView webhook already running; bridge status refreshed."}
        return {**current, "action": "start_webhook", "ok": False, "message": "Webhook PID exists, but port {} is not listening.".format(port)}
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    WEBHOOK_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("TRADINGVIEW_WEBHOOK_PORT", "5056")
    with WEBHOOK_LOG_FILE.open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, "tradingview/webhook_server.py"],
            cwd=str(ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            close_fds=True,
            env=env,
        )
    WEBHOOK_PID_FILE.write_text(str(process.pid), encoding="utf-8")
    port = int(env["TRADINGVIEW_WEBHOOK_PORT"])
    deadline = time.time() + 5
    while time.time() < deadline:
        if process.poll() is not None:
            break
        if _port_listening(port):
            break
        time.sleep(0.25)

    current = webhook_status()
    if not current["running"] or not _port_listening(port):
        if WEBHOOK_PID_FILE.exists():
            WEBHOOK_PID_FILE.unlink()
        return {
            **webhook_status(),
            "action": "start_webhook",
            "ok": False,
            "message": "TradingView webhook failed to start. Check {}".format(WEBHOOK_LOG_FILE),
        }

    _write_webhook_status(port)
    return {**webhook_status(), "action": "start_webhook", "ok": True, "message": "TradingView webhook started."}


def stop_webhook(timeout: float = 8.0) -> Dict[str, Any]:
    current = webhook_status()
    pid = current.get("pid")
    if current["running"] or _matching_pids("tradingview"):
        if os.name == "nt":
            pids = _matching_pids("tradingview/webhook_server.py") + _matching_pids("tradingview\\webhook_server.py")
            _terminate_pids(pids or [int(pid)], timeout)
        else:
            os.kill(int(pid), signal.SIGTERM)
    if WEBHOOK_PID_FILE.exists():
        WEBHOOK_PID_FILE.unlink()
    time.sleep(1)
    return {**webhook_status(), "action": "stop_webhook", "message": "TradingView webhook stopped."}


def main() -> None:
    parser = argparse.ArgumentParser(description="Start/stop/restart MIRO launch.py agents.")
    parser.add_argument("action", choices=["status", "start", "stop", "restart", "watchdog-status", "watchdog-start", "watchdog-stop", "self-healer-status", "self-healer-start", "self-healer-stop", "webhook-status", "webhook-start", "webhook-stop"])
    args = parser.parse_args()
    actions = {
        "status": status,
        "start": start,
        "stop": stop,
        "restart": restart,
        "watchdog-status": watchdog_status,
        "watchdog-start": start_watchdog,
        "watchdog-stop": stop_watchdog,
        "self-healer-status": self_healer_status,
        "self-healer-start": start_self_healer,
        "self-healer-stop": stop_self_healer,
        "webhook-status": webhook_status,
        "webhook-start": start_webhook,
        "webhook-stop": stop_webhook,
    }
    json.dump(actions[args.action](), sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
