from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.append(str(Path(__file__).resolve().parents[1]))

from agents.orchestrator.setup_supervisor import evaluate_setup
from tools.agent_supervisor import (
    start as start_agents,
    start_webhook,
    start_watchdog,
    status as agents_status,
    watchdog_status,
)
from tools.system_health import REQUIRED_PATHS, ROOT, run_health_check


STATE_FILE = ROOT / "runtime" / "self_healing_agent.json"
LOCK_FILE = ROOT / "runtime" / "self_healing_agent.lock"
DASHBOARD_PID_FILE = ROOT / "runtime" / "dashboard.pid"
DASHBOARD_OUT_LOG = ROOT / "logs" / "dashboard_standalone.out.log"
DASHBOARD_ERR_LOG = ROOT / "logs" / "dashboard_standalone.err.log"
DISCOVERY_REPORT = ROOT / "backtesting" / "reports" / "autonomous_discovery.json"
DISCOVERY_DATA = ROOT / "backtesting" / "data" / "XAUUSD_M5.csv"

UNSAFE_FIXES = {
    "env",
    "orchestrator_verdict",
    "live_safety",
    "promotion_stage",
    "discovery_acceptance",
    "lifecycle_active",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save(payload: Dict[str, Any]) -> Dict[str, Any]:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = _now()
    STATE_FILE.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload


def _port_open(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _pid_running(pid: int | None) -> bool:
    if not pid:
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


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip()) if path.exists() else None
    except Exception:
        return None


def _start_dashboard() -> Dict[str, Any]:
    if _port_open(5055):
        return {"ok": True, "action": "start_dashboard", "message": "Dashboard already listening on 5055."}
    pid = _read_pid(DASHBOARD_PID_FILE)
    if _pid_running(pid):
        return {"ok": True, "action": "start_dashboard", "message": "Dashboard process already running.", "pid": pid}

    DASHBOARD_OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        [sys.executable, "agents/master_trader/miro_dashboard_server.py"],
        cwd=str(ROOT),
        stdout=DASHBOARD_OUT_LOG.open("ab"),
        stderr=DASHBOARD_ERR_LOG.open("ab"),
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        close_fds=True,
    )
    DASHBOARD_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PID_FILE.write_text(str(process.pid), encoding="utf-8")
    deadline = time.time() + 15
    while time.time() < deadline:
        if _port_open(5055):
            return {"ok": True, "action": "start_dashboard", "message": "Dashboard started.", "pid": process.pid}
        if process.poll() is not None:
            break
        time.sleep(0.5)
    return {"ok": False, "action": "start_dashboard", "message": "Dashboard did not start within timeout.", "pid": process.pid}


def _repair_paths() -> Dict[str, Any]:
    created: List[str] = []
    for rel in REQUIRED_PATHS:
        target = ROOT / rel
        if rel.endswith(".py"):
            continue
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created.append(rel)
    return {"ok": True, "action": "repair_paths", "created": created}


def _cleanup_temp_files(max_age_seconds: int = 300) -> Dict[str, Any]:
    removed: List[str] = []
    logs_dir = ROOT / "paper_trading" / "logs"
    if logs_dir.exists():
        for path in logs_dir.glob("agents_status.json.*.tmp"):
            try:
                if time.time() - path.stat().st_mtime > max_age_seconds:
                    path.unlink()
                    removed.append(str(path.relative_to(ROOT)))
            except Exception:
                pass
    return {"ok": True, "action": "cleanup_temp_files", "removed": removed}


def _run_quick_discovery() -> Dict[str, Any]:
    if DISCOVERY_REPORT.exists():
        return {"ok": True, "action": "quick_discovery", "message": "Discovery report already exists."}
    if not DISCOVERY_DATA.exists():
        return {
            "ok": False,
            "action": "quick_discovery",
            "message": "Missing backtesting/data/XAUUSD_M5.csv. Export MT5 data before discovery.",
        }
    result = subprocess.run(
        [
            sys.executable,
            "backtesting/research/autonomous_discovery.py",
            "--strategy",
            "v15f",
            "--max-candidates",
            "4",
            "--max-specs",
            "8",
            "--max-bars",
            "4000",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=90,
    )
    return {
        "ok": result.returncode == 0,
        "action": "quick_discovery",
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-1000:],
        "stderr_tail": result.stderr[-1000:],
    }


def _unsafe_reason(check: Dict[str, Any]) -> str | None:
    name = str(check.get("name", ""))
    status = str(check.get("status", "ok")).lower()
    if name.startswith("env ") and status != "ok":
        return "Credentials/secrets must be edited by the operator."
    if name in UNSAFE_FIXES and status != "ok":
        return "Trading gate is intentionally not auto-overridden."
    return None


class SelfHealingAgent:
    def run_once(self) -> Dict[str, Any]:
        if LOCK_FILE.exists() and time.time() - LOCK_FILE.stat().st_mtime < 45:
            return _save({"ok": True, "status": "locked", "actions": [], "skipped": ["Another self-heal pass is active."]})
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")

        actions: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        try:
            health = run_health_check()
            setup = evaluate_setup()

            actions.append(_repair_paths())
            actions.append(_cleanup_temp_files())

            if not agents_status().get("running"):
                actions.append(start_agents())
            if not watchdog_status().get("running"):
                actions.append(start_watchdog())
            if not _port_open(5055):
                actions.append(_start_dashboard())
            if not _port_open(5056):
                actions.append(start_webhook())
            if not DISCOVERY_REPORT.exists():
                actions.append(_run_quick_discovery())

            for check in list(health.get("checks", [])) + list(setup.get("checks", [])):
                reason = _unsafe_reason(check)
                if reason:
                    skipped.append({"name": check.get("name"), "detail": check.get("detail"), "reason": reason})

            final_health = run_health_check()
            final_setup = evaluate_setup()
            return _save(
                {
                    "ok": True,
                    "status": "repaired" if actions else "observed",
                    "actions": actions,
                    "skipped": skipped[:20],
                    "health": {
                        "status": final_health.get("status"),
                        "score": final_health.get("score"),
                        "blockers": final_health.get("blocker_count"),
                        "warnings": final_health.get("warning_count"),
                    },
                    "setup": {
                        "status": final_setup.get("status"),
                        "score": final_setup.get("setup_score"),
                        "blockers": final_setup.get("blocker_count"),
                        "warnings": final_setup.get("warning_count"),
                        "next_actions": final_setup.get("next_actions", []),
                    },
                    "policy": "Safe auto-repair only. No credential edits, live unlocks, risk cap changes, or trade forcing.",
                }
            )
        finally:
            try:
                LOCK_FILE.unlink()
            except Exception:
                pass

    def run(self, interval_seconds: int = 60) -> None:
        print("[SelfHealer] Running every {}s".format(interval_seconds))
        while True:
            try:
                result = self.run_once()
                print(
                    "[SelfHealer] {} health={} setup={} actions={}".format(
                        result.get("status"),
                        (result.get("health") or {}).get("status"),
                        (result.get("setup") or {}).get("status"),
                        len(result.get("actions", [])),
                    )
                )
            except Exception as exc:
                _save({"ok": False, "status": "error", "error": str(exc)})
                print("[SelfHealer] Error: {}".format(exc))
            time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="MIRO self-healing setup/runtime agent.")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    agent = SelfHealingAgent()
    if args.loop:
        agent.run(interval_seconds=args.interval)
    else:
        json.dump(agent.run_once(), sys.stdout, indent=2, default=str)
        print()


if __name__ == "__main__":
    main()
