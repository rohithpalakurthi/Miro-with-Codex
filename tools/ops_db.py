from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "runtime" / "miro_ops.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            ok INTEGER NOT NULL,
            detail TEXT,
            summary TEXT,
            payload_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metric_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL,
            payload_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS promotion_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            strategy TEXT NOT NULL,
            action TEXT NOT NULL,
            stage TEXT,
            approved_for TEXT,
            note TEXT,
            payload_json TEXT
        )
        """
    )
    conn.commit()


def record_audit_event(entry: Dict[str, Any], payload: Any = None) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO audit_events(created_at, actor, action, ok, detail, summary, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.get("time") or _now(),
                entry.get("actor") or "system",
                entry.get("action") or "unknown",
                1 if entry.get("ok", True) else 0,
                entry.get("detail") or "",
                entry.get("result_summary") or "",
                json.dumps(payload if payload is not None else entry, default=str),
            ),
        )


def recent_audit_events(limit: int = 100) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def record_metric_snapshot(source: str, metric: str, value: Optional[float], payload: Any = None) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO metric_snapshots(created_at, source, metric, value, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (_now(), source, metric, value, json.dumps(payload if payload is not None else {}, default=str)),
        )


def metric_history(metric: str = "balance", limit: int = 100) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM metric_snapshots
            WHERE metric = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (metric, max(1, min(int(limit), 500))),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def record_promotion_event(strategy: str, action: str, promotion: Dict[str, Any], note: str = "") -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO promotion_events(created_at, strategy, action, stage, approved_for, note, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                strategy,
                action,
                promotion.get("status") or promotion.get("override_stage") or "",
                promotion.get("approved_for") or "",
                note,
                json.dumps(promotion, default=str),
            ),
        )


def recent_promotion_events(limit: int = 50) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM promotion_events ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def database_summary() -> Dict[str, Any]:
    with _connect() as conn:
        tables = {}
        for table in ("audit_events", "metric_snapshots", "promotion_events"):
            count = conn.execute("SELECT COUNT(*) AS c FROM {}".format(table)).fetchone()["c"]
            latest = conn.execute("SELECT created_at FROM {} ORDER BY id DESC LIMIT 1".format(table)).fetchone()
            tables[table] = {"count": count, "latest": latest["created_at"] if latest else None}
    return {"path": str(DB_PATH), "tables": tables}


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    payload = item.pop("payload_json", None)
    if payload:
        try:
            item["payload"] = json.loads(payload)
        except json.JSONDecodeError:
            item["payload"] = payload
    return item
