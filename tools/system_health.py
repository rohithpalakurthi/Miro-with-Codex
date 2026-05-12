from __future__ import annotations

import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_ENV = [
    "MT5_LOGIN",
    "MT5_PASSWORD",
    "MT5_SERVER",
]

OPTIONAL_ENV = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "NGROK_AUTHTOKEN",
]

PLACEHOLDER_MARKERS = ("your_", "your-", "changeme", "change_me", "placeholder", "example")

REQUIRED_PATHS = [
    "launch.py",
    "agents/master_trader/miro_dashboard_server.py",
    "paper_trading/logs",
    "backtesting/reports",
    "live_execution/bridge",
]

RUNTIME_FILES = {
    "agent_supervisor": "runtime/agent_supervisor.json",
    "agents_pid": "runtime/agents.pid",
    "agents_status": "paper_trading/logs/agents_status.json",
    "paper_state": "paper_trading/logs/state.json",
    "live_price": "dashboard/frontend/live_price.json",
    "bridge_status": "tradingview/bridge_status.json",
    "setup_supervisor": "agents/orchestrator/setup_supervisor.json",
}

PORTS = {
    "dashboard_5055": 5055,
    "tradingview_webhook_5056": 5056,
}


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _age_seconds(path: Path) -> int | None:
    if not path.exists():
        return None
    return int(time.time() - path.stat().st_mtime)


def _port_open(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.25)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()


def _check(name: str, status: str, detail: str, impact: str = "") -> Dict[str, str]:
    return {
        "name": name,
        "status": status,
        "detail": detail,
        "impact": impact,
    }


def _env_status(key: str, *, required: bool) -> Dict[str, str]:
    value = (os.getenv(key) or "").strip()
    if not value:
        return {"status": "blocker" if required else "warn", "detail": "missing"}
    lowered = value.lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return {"status": "blocker" if required else "warn", "detail": "placeholder value"}
    if key == "MT5_LOGIN" and not value.isdigit():
        return {"status": "blocker", "detail": "must be numeric"}
    return {"status": "ok", "detail": "present"}


def run_health_check() -> Dict[str, Any]:
    if load_dotenv:
        load_dotenv(ROOT / ".env", override=True)
    checks: List[Dict[str, str]] = []

    # 1. Dependency Checks
    import importlib.util
    deps = ["MetaTrader5", "pandas", "numpy", "flask", "requests", "dotenv"]
    for dep in deps:
        found = importlib.util.find_spec(dep) is not None if dep != "dotenv" else importlib.util.find_spec("dotenv") is not None
        # Handle cases like python-dotenv which is imported as 'dotenv'
        if not found and dep == "dotenv":
             found = importlib.util.find_spec("dotenv") is not None

        checks.append(_check(
            "dep {}".format(dep),
            "ok" if found else "blocker",
            "installed" if found else "missing",
            "Required library for the framework to function."
        ))

    # 2. Process Checks (MT5)
    import subprocess
    mt5_running = False
    try:
        if sys.platform == "win32":
            output = subprocess.check_output(['tasklist'], string=True)
            mt5_running = "terminal.exe" in output.lower()
        else:
            # Linux check for wine/mt5
            output = subprocess.check_output(['ps', 'ax'], stderr=subprocess.STDOUT).decode('utf-8')
            mt5_running = "terminal.exe" in output.lower() or "metatrader" in output.lower()
    except Exception:
        pass

    checks.append(_check(
        "process MT5",
        "ok" if mt5_running else "warn",
        "running" if mt5_running else "not found",
        "MT5 terminal must be open for live bridge/data feed."
    ))

    for key in REQUIRED_ENV:
        env = _env_status(key, required=True)
        checks.append(_check(
            "env {}".format(key),
            env["status"],
            env["detail"],
            "Required for MT5 login and live account reads.",
        ))

    for key in OPTIONAL_ENV:
        env = _env_status(key, required=False)
        checks.append(_check(
            "env {}".format(key),
            env["status"],
            env["detail"],
            "Optional, but enables alerts, AI reasoning, or mobile tunnel.",
        ))

    for rel in REQUIRED_PATHS:
        path = ROOT / rel
        checks.append(_check(
            "path {}".format(rel),
            "ok" if path.exists() else "blocker",
            "exists" if path.exists() else "missing",
            "Core file/folder required for startup.",
        ))

    for name, rel in RUNTIME_FILES.items():
        path = ROOT / rel
        age = _age_seconds(path)
        if age is None:
            status = "warn"
            detail = "missing"
        elif age > 900:
            status = "warn"
            detail = "stale {}s".format(age)
        else:
            status = "ok"
            detail = "fresh {}s".format(age)
        checks.append(_check(
            "runtime {}".format(name),
            status,
            detail,
            "Fresh runtime files mean agents are actively writing state.",
        ))

    for name, port in PORTS.items():
        active = _port_open(port)
        checks.append(_check(
            "port {}".format(name),
            "ok" if active else "warn",
            "listening" if active else "not listening",
            "Expected when the dashboard/webhook service is running.",
        ))

    mt5_state = _load_json(ROOT / "live_execution/bridge/mt5_state.json", {})
    bridge_status = _load_json(ROOT / "tradingview/bridge_status.json", {})
    paper_state = _load_json(ROOT / "paper_trading/logs/state.json", {})

    blockers = [c for c in checks if c["status"] == "blocker"]
    warnings = [c for c in checks if c["status"] == "warn"]
    score = round(max(0, 100 - len(blockers) * 18 - len(warnings) * 5), 1)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "blocked" if blockers else "warn" if warnings else "ok",
        "score": score,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "checks": checks,
        "snapshots": {
            "mt5": mt5_state,
            "bridge_status": bridge_status,
            "paper_balance": paper_state.get("account", {}).get("balance", paper_state.get("balance")),
        },
        "next_actions": [
            c["name"] + ": " + c["detail"]
            for c in blockers[:4] + warnings[:4]
        ] or ["All setup checks are green. Continue paper/demo validation."],
    }


def main() -> None:
    json.dump(run_health_check(), sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
