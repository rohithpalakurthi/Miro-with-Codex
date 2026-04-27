from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = ROOT / "runtime" / "live_mode_lock.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load() -> Dict[str, Any]:
    try:
        if LOCK_FILE.exists():
            return json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"unlocked": False, "reason": "Live mode locked by default"}


def _save(payload: Dict[str, Any]) -> Dict[str, Any]:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = _now().isoformat()
    LOCK_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def status() -> Dict[str, Any]:
    payload = _load()
    expires_at = payload.get("expires_at")
    if payload.get("unlocked") and expires_at:
        try:
            if datetime.fromisoformat(expires_at) <= _now():
                payload = lock("Live unlock expired")
        except Exception:
            payload = lock("Invalid live unlock expiry")
    return payload


def unlock(*, actor: str = "dashboard", minutes: int = 30, reason: str = "Manual unlock") -> Dict[str, Any]:
    minutes = max(1, min(int(minutes), 240))
    return _save({
        "unlocked": True,
        "actor": actor,
        "reason": reason,
        "expires_at": (_now() + timedelta(minutes=minutes)).isoformat(),
    })


def lock(reason: str = "Manual lock") -> Dict[str, Any]:
    return _save({
        "unlocked": False,
        "reason": reason,
        "expires_at": None,
    })
