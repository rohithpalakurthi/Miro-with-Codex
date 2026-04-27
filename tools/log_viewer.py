from __future__ import annotations

from pathlib import Path
from typing import Dict


ROOT = Path(__file__).resolve().parents[1]

LOGS: Dict[str, Path] = {
    "agents": ROOT / "logs" / "agents_supervisor.log",
    "dashboard": ROOT / "logs" / "dashboard.log",
    "telegram": ROOT / "agents" / "telegram" / "sent_alerts.json",
    "optimizer": ROOT / "agents" / "orchestrator" / "improvement_log.json",
    "bridge": ROOT / "tradingview" / "webhook_log.json",
}


def tail_log(name: str = "agents", max_chars: int = 8000) -> Dict[str, object]:
    path = LOGS.get(name, LOGS["agents"])
    max_chars = max(500, min(int(max_chars), 40000))
    if not path.exists():
        return {"name": name, "path": str(path), "exists": False, "content": ""}
    data = path.read_bytes()
    chunk = data[-max_chars:]
    return {
        "name": name,
        "path": str(path),
        "exists": True,
        "size": len(data),
        "content": chunk.decode("utf-8", errors="replace"),
    }
