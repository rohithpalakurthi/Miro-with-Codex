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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            symbol TEXT,
            strategy TEXT,
            decision TEXT NOT NULL,
            confidence REAL,
            entry REAL,
            stop_loss REAL,
            take_profit REAL,
            risk_json TEXT,
            context_json TEXT,
            outcome_json TEXT,
            status TEXT NOT NULL
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


def record_trade_decision(
    *,
    symbol: str = "",
    strategy: str = "",
    decision: str = "HOLD",
    confidence: Optional[float] = None,
    entry: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    risk: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    outcome: Optional[Dict[str, Any]] = None,
    status: str = "observed",
) -> Dict[str, Any]:
    payload = {
        "created_at": _now(),
        "symbol": symbol,
        "strategy": strategy,
        "decision": decision,
        "confidence": confidence,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk": risk or {},
        "context": context or {},
        "outcome": outcome or {},
        "status": status,
    }
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO trade_decisions(
                created_at, symbol, strategy, decision, confidence, entry, stop_loss,
                take_profit, risk_json, context_json, outcome_json, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["created_at"],
                symbol,
                strategy,
                decision,
                confidence,
                entry,
                stop_loss,
                take_profit,
                json.dumps(payload["risk"], default=str),
                json.dumps(payload["context"], default=str),
                json.dumps(payload["outcome"], default=str),
                status,
            ),
        )
        payload["id"] = cursor.lastrowid
    return payload


def recent_trade_decisions(limit: int = 100) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM trade_decisions ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [_decision_row_to_dict(row) for row in rows]


def database_summary() -> Dict[str, Any]:
    with _connect() as conn:
        tables = {}
        for table in ("audit_events", "metric_snapshots", "promotion_events", "trade_decisions"):
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


def _decision_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    for column, target in (
        ("risk_json", "risk"),
        ("context_json", "context"),
        ("outcome_json", "outcome"),
    ):
        raw = item.pop(column, None)
        if raw:
            try:
                item[target] = json.loads(raw)
            except json.JSONDecodeError:
                item[target] = raw
        else:
            item[target] = {}
    return item
