from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
AUDIT_FILE = RUNTIME / "operator_audit.json"
BACKUP_DIR = ROOT / "backups" / "config_snapshots"

CONFIG_FILES = [
    "agents/master_trader/trading_config.json",
    "agents/master_trader/circuit_breaker_config.json",
    "live_execution/live_safety_config.json",
    "runtime/live_mode_lock.json",
]

RISK_EVENT_FILES = [
    "runtime/watchdog.json",
    "runtime/agent_supervisor.json",
    "runtime/incident_alerts.json",
    "live_execution/live_safety_status.json",
    "agents/master_trader/circuit_breaker_state.json",
    "agents/orchestrator/survival_state.json",
    "agents/orchestrator/setup_supervisor.json",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def audit(action: str, result: Any, *, actor: str = "dashboard", detail: str = "") -> Dict[str, Any]:
    entries = load_json(AUDIT_FILE, [])
    if not isinstance(entries, list):
        entries = []
    ok = True
    if isinstance(result, dict):
        ok = bool(result.get("ok", True)) and not bool(result.get("error"))
    entry = {
        "time": _now(),
        "actor": actor,
        "action": action,
        "ok": ok,
        "detail": detail,
        "result_summary": _summarize(result),
    }
    entries.append(entry)
    save_json(AUDIT_FILE, entries[-500:])
    return entry


def recent_audit(limit: int = 50) -> List[Dict[str, Any]]:
    entries = load_json(AUDIT_FILE, [])
    return list(reversed(entries[-limit:])) if isinstance(entries, list) else []


def _summarize(value: Any) -> str:
    if isinstance(value, dict):
        bits = []
        for key in ("status", "state", "action", "message", "reason", "error", "ok"):
            if key in value:
                bits.append("{}={}".format(key, value.get(key)))
        return " | ".join(bits)[:240] or "dict({})".format(len(value))
    return str(value)[:240]


def create_config_snapshot(label: str = "manual") -> Dict[str, Any]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / "{}_{}".format(stamp, safe_label(label))
    copied = []
    for rel in CONFIG_FILES:
        src = ROOT / rel
        if src.exists():
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(rel)
    manifest = {"created_at": _now(), "label": label, "files": copied}
    save_json(target / "manifest.json", manifest)
    audit("config_snapshot", manifest, detail=label)
    return {"ok": True, "snapshot": target.name, "path": str(target), "files": copied}


def list_config_snapshots() -> List[Dict[str, Any]]:
    if not BACKUP_DIR.exists():
        return []
    snapshots = []
    for path in sorted(BACKUP_DIR.iterdir(), reverse=True):
        if path.is_dir():
            manifest = load_json(path / "manifest.json", {})
            snapshots.append({"name": path.name, "path": str(path), **manifest})
    return snapshots


def restore_config_snapshot(name: str) -> Dict[str, Any]:
    source = (BACKUP_DIR / name).resolve()
    if not str(source).startswith(str(BACKUP_DIR.resolve())) or not source.exists():
        return {"ok": False, "error": "snapshot not found"}
    restored = []
    for rel in CONFIG_FILES:
        src = source / rel
        if src.exists():
            dst = ROOT / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            restored.append(rel)
    result = {"ok": True, "snapshot": name, "restored": restored}
    audit("config_restore", result, detail=name)
    return result


def risk_timeline(limit: int = 80) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for rel in RISK_EVENT_FILES:
        path = ROOT / rel
        payload = load_json(path, None)
        if payload is None:
            continue
        events.extend(_extract_events(rel, payload, path.stat().st_mtime))
    events.extend({
        "time": item.get("time"),
        "source": "operator_audit",
        "type": item.get("action"),
        "severity": "info" if item.get("ok") else "warn",
        "detail": item.get("result_summary") or item.get("detail", ""),
    } for item in load_json(AUDIT_FILE, []) if isinstance(item, dict))
    events = [e for e in events if e.get("time")]
    return sorted(events, key=lambda e: e["time"], reverse=True)[:limit]


def _extract_events(source: str, payload: Any, mtime: float) -> List[Dict[str, Any]]:
    fallback_time = datetime.fromtimestamp(mtime, timezone.utc).isoformat()
    if isinstance(payload, list):
        return [{
            "time": str(item.get("time") or item.get("timestamp") or item.get("updated_at") or fallback_time),
            "source": source,
            "type": item.get("action") or item.get("event") or "log",
            "severity": "info",
            "detail": _summarize(item),
        } for item in payload[-20:] if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    severity = "warn" if payload.get("status") in ("blocked", "warn", "PAUSED") or payload.get("allowed") is False else "info"
    detail = payload.get("reason") or payload.get("message") or payload.get("next_action") or _summarize(payload)
    return [{
        "time": str(payload.get("updated_at") or payload.get("generated_at") or payload.get("created_at") or fallback_time),
        "source": source,
        "type": payload.get("action") or payload.get("status") or "state",
        "severity": severity,
        "detail": str(detail),
    }]


def safe_label(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)[:40] or "manual"
