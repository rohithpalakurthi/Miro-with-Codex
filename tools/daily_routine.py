from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.append(str(Path(__file__).resolve().parents[1]))

from tools.incident_alerts import send_incident
from tools.system_health import run_health_check


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "runtime" / "daily_routine.json"


def _run_step(name: str, cmd: List[str]) -> Dict[str, Any]:
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=900)
        return {
            "name": name,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
        }
    except Exception as exc:
        return {"name": name, "ok": False, "error": str(exc)}


def run_daily_routine(*, execute_heavy: bool = False) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    health = run_health_check()
    steps.append({"name": "system_health", "ok": health["status"] != "blocked", "summary": health})

    if execute_heavy:
        steps.append(_run_step("refresh_promotion_status", [sys.executable, "backtesting/research/refresh_promotion_status.py"]))
        steps.append(_run_step("walk_forward", [sys.executable, "backtesting/research/run_walk_forward.py"]))
    else:
        steps.append({"name": "heavy_research", "ok": True, "skipped": True, "reason": "execute_heavy=false"})

    ok = all(step.get("ok") for step in steps)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "steps": steps,
        "next_action": "review blockers" if not ok else "continue monitoring",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    send_incident(
        "Daily routine {}".format("passed" if ok else "needs attention"),
        "Health status: {} | steps: {}".format(health["status"], len(steps)),
        "info" if ok else "warn",
        throttle_seconds=3600,
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MIRO daily autonomous maintenance routine.")
    parser.add_argument("--execute-heavy", action="store_true", help="Run heavier research/backtest jobs.")
    args = parser.parse_args()
    json.dump(run_daily_routine(execute_heavy=args.execute_heavy), sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
