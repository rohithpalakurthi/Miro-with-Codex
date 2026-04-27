from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

sys.path.append(str(Path(__file__).resolve().parents[1]))

import requests
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / "runtime"
ALERT_STATE = RUNTIME_DIR / "incident_alerts.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _save(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def send_incident(title: str, detail: str, severity: str = "warn", *, throttle_seconds: int = 900) -> Dict[str, Any]:
    load_dotenv(ROOT / ".env")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    key = hashlib.sha256("{}|{}|{}".format(severity, title, detail[:160]).encode("utf-8")).hexdigest()
    state = _load(ALERT_STATE, {"sent": {}})
    last_sent = float(state.get("sent", {}).get(key, 0) or 0)
    if time.time() - last_sent < throttle_seconds:
        return {"ok": True, "sent": False, "reason": "throttled", "key": key}

    payload = {
        "severity": severity,
        "title": title,
        "detail": detail,
        "created_at": _now(),
    }
    if not token or not chat_id:
        state.setdefault("queued", []).append(payload)
        _save(ALERT_STATE, state)
        return {"ok": False, "sent": False, "reason": "telegram_not_configured", "incident": payload}

    text = "<b>MIRO INCIDENT [{}]</b>\n<b>{}</b>\n{}\n<i>{}</i>".format(
        severity.upper(),
        title,
        detail,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    try:
        response = requests.post(
            "https://api.telegram.org/bot{}/sendMessage".format(token),
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        body = response.json()
        ok = bool(body.get("ok"))
        if ok:
            state.setdefault("sent", {})[key] = time.time()
        else:
            state.setdefault("failed", []).append({"incident": payload, "response": body})
        _save(ALERT_STATE, state)
        return {"ok": ok, "sent": ok, "status": response.status_code, "response": body, "key": key}
    except Exception as exc:
        state.setdefault("failed", []).append({"incident": payload, "error": str(exc)})
        _save(ALERT_STATE, state)
        return {"ok": False, "sent": False, "error": str(exc), "incident": payload}


def main() -> None:
    title = sys.argv[1] if len(sys.argv) > 1 else "Manual incident test"
    detail = sys.argv[2] if len(sys.argv) > 2 else "Operator requested incident alert test."
    json.dump(send_incident(title, detail, "info", throttle_seconds=0), sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
