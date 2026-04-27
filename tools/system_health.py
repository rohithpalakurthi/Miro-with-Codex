from __future__ import annotations

import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv


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

REQUIRED_PATHS = [
    "launch.py",
    "agents/master_trader/miro_dashboard_server.py",
    "paper_trading/logs",
    "backtesting/reports",
    "live_execution/bridge",
]

RUNTIME_FILES = {
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


def run_health_check() -> Dict[str, Any]:
    load_dotenv(ROOT / ".env")
    checks: List[Dict[str, str]] = []

    for key in REQUIRED_ENV:
        checks.append(_check(
            "env {}".format(key),
            "ok" if os.getenv(key) else "blocker",
            "present" if os.getenv(key) else "missing",
            "Required for MT5 login and live account reads.",
        ))

    for key in OPTIONAL_ENV:
        checks.append(_check(
            "env {}".format(key),
            "ok" if os.getenv(key) else "warn",
            "present" if os.getenv(key) else "missing",
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
