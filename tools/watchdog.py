from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

sys.path.append(str(Path(__file__).resolve().parents[1]))

from tools.agent_supervisor import restart, start, status
from tools.incident_alerts import send_incident
from tools.system_health import run_health_check


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_STATUS = ROOT / "runtime" / "watchdog.json"


def _save(payload: Dict[str, Any]) -> Dict[str, Any]:
    WATCHDOG_STATUS.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    WATCHDOG_STATUS.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def check_once(*, auto_recover: bool = True) -> Dict[str, Any]:
    health = run_health_check()
    proc = status()
    actions = []

    severe = health["status"] == "blocked" or health.get("score", 100) < 50
    stale_runtime = any(
        c["name"].startswith("runtime ") and c["status"] == "warn" and "stale" in c["detail"]
        for c in health.get("checks", [])
    )

    if auto_recover and not proc["running"]:
        actions.append(start())
        send_incident("Agents were stopped", "Watchdog started launch.py supervisor.", "warn")
    elif auto_recover and stale_runtime and proc["running"]:
        actions.append(restart())
        send_incident("Runtime state stale", "Watchdog restarted agents because runtime files stopped updating.", "warn")
    elif severe:
        send_incident("Health score degraded", "Status {} score {}.".format(health["status"], health["score"]), "warn")

    return _save({
        "health_status": health["status"],
        "health_score": health["score"],
        "agent_process": proc,
        "auto_recover": auto_recover,
        "actions": actions,
        "next_actions": health.get("next_actions", []),
    })


def loop(interval_seconds: int = 120, *, auto_recover: bool = True) -> None:
    while True:
        check_once(auto_recover=auto_recover)
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="MIRO watchdog for stale agents/runtime health.")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=120)
    parser.add_argument("--no-recover", action="store_true")
    args = parser.parse_args()
    if args.loop:
        loop(interval_seconds=args.interval, auto_recover=not args.no_recover)
    else:
        json.dump(check_once(auto_recover=not args.no_recover), sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
