from __future__ import annotations

import html
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
CONTROL_FILE = ROOT / "runtime" / "telegram_control.json"
HISTORY_FILE = ROOT / "runtime" / "telegram_messages.json"
DIGEST_FILE = ROOT / "runtime" / "telegram_digest.json"

CATEGORIES = {
    "startup": "Startup/online/offline notices",
    "tunnel": "Dashboard tunnel and ngrok updates",
    "incident": "Watchdog, health, and runtime warnings",
    "trade": "Trade entries, exits, and position management",
    "system": "General system diagnostics and tests",
    "crypto": "Crypto scanner signals and status",
    "command": "Replies to Telegram commands from you",
    "research": "Backtest, optimizer, and strategy research reports",
}

DEFAULT_CONTROL = {
    "enabled": True,
    "muted": False,
    "mode": "instant",
    "digest_max_items": 20,
    "categories": {name: True for name in CATEGORIES},
}


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
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _merge_control(raw: Dict[str, Any] | None = None) -> Dict[str, Any]:
    control = dict(DEFAULT_CONTROL)
    control["categories"] = dict(DEFAULT_CONTROL["categories"])
    if isinstance(raw, dict):
        for key in ("enabled", "muted", "mode", "digest_max_items"):
            if key in raw:
                control[key] = raw[key]
        if isinstance(raw.get("categories"), dict):
            control["categories"].update({str(k): bool(v) for k, v in raw["categories"].items()})
    if control["mode"] not in ("instant", "digest"):
        control["mode"] = "instant"
    control["digest_max_items"] = max(3, min(100, int(control.get("digest_max_items", 20) or 20)))
    return control


def load_control() -> Dict[str, Any]:
    return _merge_control(_load(CONTROL_FILE, {}))


def save_control(update: Dict[str, Any]) -> Dict[str, Any]:
    current = load_control()
    if "enabled" in update:
        current["enabled"] = bool(update["enabled"])
    if "muted" in update:
        current["muted"] = bool(update["muted"])
    if "mode" in update:
        mode = str(update["mode"]).lower()
        if mode in ("instant", "digest"):
            current["mode"] = mode
    if "digest_max_items" in update:
        current["digest_max_items"] = max(3, min(100, int(update["digest_max_items"] or 20)))
    if isinstance(update.get("categories"), dict):
        for key, value in update["categories"].items():
            if key in CATEGORIES:
                current["categories"][key] = bool(value)
    _save(CONTROL_FILE, current)
    return current


def classify_message(text: str, fallback: str = "system") -> str:
    lower = (text or "").lower()
    if "tunnel" in lower or "ngrok" in lower or "dashboard" in lower and "url" in lower:
        return "tunnel"
    if "incident" in lower or "watchdog" in lower or "stopped" in lower or "degraded" in lower:
        return "incident"
    if "crypto" in lower or "btc/" in lower or "eth/" in lower:
        return "crypto"
    if "trade" in lower or "position manager" in lower or "position" in lower or "order" in lower:
        return "trade"
    if "online" in lower or "offline" in lower or "interface" in lower:
        return "startup"
    return fallback if fallback in CATEGORIES else "system"


def record_message(payload: Dict[str, Any]) -> None:
    history = _load(HISTORY_FILE, {"items": []})
    items = history.setdefault("items", [])
    items.append(payload)
    del items[:-200]
    _save(HISTORY_FILE, history)


def queue_digest(payload: Dict[str, Any]) -> None:
    digest = _load(DIGEST_FILE, {"items": []})
    items = digest.setdefault("items", [])
    items.append(payload)
    del items[:-500]
    _save(DIGEST_FILE, digest)


def recent_messages(limit: int = 50) -> Dict[str, Any]:
    history = _load(HISTORY_FILE, {"items": []})
    items = list(history.get("items", []))[-limit:]
    grouped: Dict[str, List[Dict[str, Any]]] = {name: [] for name in CATEGORIES}
    for item in reversed(items):
        grouped.setdefault(item.get("category", "system"), []).append(item)
    return {"items": list(reversed(items)), "grouped": grouped}


def digest_status() -> Dict[str, Any]:
    digest = _load(DIGEST_FILE, {"items": []})
    items = digest.get("items", [])
    by_category: Dict[str, int] = {name: 0 for name in CATEGORIES}
    for item in items:
        by_category[item.get("category", "system")] = by_category.get(item.get("category", "system"), 0) + 1
    return {"pending_count": len(items), "by_category": by_category, "items": items[-50:]}


def clear_digest() -> Dict[str, Any]:
    _save(DIGEST_FILE, {"items": []})
    return digest_status()


def _credentials() -> tuple[str, str]:
    load_dotenv(ROOT / ".env")
    return os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")


def _send_raw(text: str, parse_mode: str = "HTML") -> Dict[str, Any]:
    token, chat_id = _credentials()
    if not token or not chat_id:
        return {"ok": False, "sent": False, "reason": "telegram_not_configured"}
    response = requests.post(
        "https://api.telegram.org/bot{}/sendMessage".format(token),
        data={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
        timeout=10,
    )
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}
    return {"ok": bool(body.get("ok")), "sent": bool(body.get("ok")), "status": response.status_code, "response": body}


def send_message(
    text: str,
    *,
    category: str | None = None,
    title: str | None = None,
    parse_mode: str = "HTML",
    force: bool = False,
) -> Dict[str, Any]:
    control = load_control()
    category = category if category in CATEGORIES else classify_message(text)
    payload = {
        "time": _now(),
        "category": category,
        "title": title or _plain_title(text),
        "text": text,
        "mode": control["mode"],
    }

    muted = (
        not control.get("enabled", True)
        or control.get("muted", False)
        or not control.get("categories", {}).get(category, True)
        or (control.get("mode") == "digest" and not force and category != "command")
    )
    if muted and not force:
        payload["status"] = "queued" if control.get("mode") == "digest" else "muted"
        queue_digest(payload)
        record_message(payload)
        return {"ok": True, "sent": False, "muted": True, "queued": True, "category": category}

    result = _send_raw(text, parse_mode=parse_mode)
    payload["status"] = "sent" if result.get("sent") else "failed"
    payload["result"] = {k: v for k, v in result.items() if k != "response"}
    record_message(payload)
    return {**result, "category": category}


def send_digest(force: bool = True) -> Dict[str, Any]:
    control = load_control()
    digest = _load(DIGEST_FILE, {"items": []})
    items = digest.get("items", [])
    if not items:
        return {"ok": True, "sent": False, "reason": "no_pending_digest"}
    selected = items[-control["digest_max_items"] :]
    counts: Dict[str, int] = {}
    for item in items:
        counts[item.get("category", "system")] = counts.get(item.get("category", "system"), 0) + 1
    lines = ["<b>MIRO Telegram Digest</b>", "Pending messages: {}".format(len(items)), ""]
    for category, count in counts.items():
        lines.append("<b>{}</b>: {}".format(html.escape(category.title()), count))
    lines.append("")
    lines.append("<b>Latest</b>")
    for item in selected:
        ts = str(item.get("time", ""))[11:19]
        lines.append("{} [{}] {}".format(ts, html.escape(item.get("category", "system")), html.escape(item.get("title", ""))[:90]))
    result = send_message("\n".join(lines), category="system", title="Telegram digest", force=force)
    if result.get("sent"):
        clear_digest()
    return result


def _plain_title(text: str) -> str:
    cleaned = (text or "").replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
    first = cleaned.strip().splitlines()[0] if cleaned.strip() else "Telegram message"
    return first[:120]
