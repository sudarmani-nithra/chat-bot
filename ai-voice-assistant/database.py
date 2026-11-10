"""
Database Management Module.
Supports MySQL with automated SQLite fallback for local development.
Handles calls, conversation transcripts, lead status tracking, order payloads,
and idempotent webhook deduplication.
"""

import os
import json
import sqlite3
import datetime
from typing import Dict, Any, List, Optional
import config

_DB_TYPE = "sqlite"
_SQLITE_PATH = config.SQLITE_DB_PATH


def _get_connection():
    global _DB_TYPE
    if config.MYSQL_HOST and config.MYSQL_PASSWORD and not config.USE_SQLITE_FALLBACK:
        try:
            import pymysql
            conn = pymysql.connect(
                host=config.MYSQL_HOST,
                port=config.MYSQL_PORT,
                user=config.MYSQL_USER,
                password=config.MYSQL_PASSWORD,
                database=config.MYSQL_DATABASE,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True
            )
            _DB_TYPE = "mysql"
            return conn
        except Exception as e:
            print(f"[DB] MySQL connection failed: {e}. Falling back to SQLite.")

    # Fallback to SQLite
    _DB_TYPE = "sqlite"
    conn = sqlite3.connect(_SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes tables if they do not exist."""
    conn = _get_connection()
    cursor = conn.cursor()


    if _DB_TYPE == "sqlite":
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id TEXT UNIQUE NOT NULL,
                mobile TEXT NOT NULL,
                proid TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'ta',
                status TEXT NOT NULL DEFAULT 'INITIATED',
                lead_status TEXT NOT NULL DEFAULT 'UNDECIDED',
                is_simulated INTEGER NOT NULL DEFAULT 1,
                order_payload TEXT,
                product_snapshot TEXT,
                duration_seconds INTEGER DEFAULT 0,
                telephony_call_sid TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id TEXT NOT NULL,
                speaker TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS webhook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                call_id TEXT,
                event_type TEXT,
                payload TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    else:
        # MySQL schema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS calls (
                id INT AUTO_INCREMENT PRIMARY KEY,
                call_id VARCHAR(64) UNIQUE NOT NULL,
                mobile VARCHAR(20) NOT NULL,
                proid VARCHAR(64) NOT NULL,
                language VARCHAR(10) NOT NULL DEFAULT 'ta',
                status VARCHAR(32) NOT NULL DEFAULT 'INITIATED',
                lead_status VARCHAR(32) NOT NULL DEFAULT 'UNDECIDED',
                is_simulated TINYINT(1) NOT NULL DEFAULT 1,
                order_payload TEXT,
                product_snapshot TEXT,
                duration_seconds INT DEFAULT 0,
                telephony_call_sid VARCHAR(100),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transcripts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                call_id VARCHAR(64) NOT NULL,
                speaker VARCHAR(20) NOT NULL,
                text TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_call_id (call_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS webhook_events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                event_id VARCHAR(100) UNIQUE NOT NULL,
                call_id VARCHAR(64),
                event_type VARCHAR(64),
                payload TEXT,
                processed_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

    conn.close()


def create_call(
    call_id: str,
    mobile: str,
    proid: str,
    language: str,
    is_simulated: bool = True,
    product_snapshot: Optional[Dict[str, Any]] = None,
    telephony_call_sid: Optional[str] = None
) -> Dict[str, Any]:
    """Creates a new voice call record."""
    conn = _get_connection()
    cursor = conn.cursor()
    prod_json = json.dumps(product_snapshot or {}, ensure_ascii=False)

    now = datetime.datetime.now().isoformat()
    if _DB_TYPE == "sqlite":
        cursor.execute(
            """
            INSERT INTO calls (call_id, mobile, proid, language, status, lead_status, is_simulated, product_snapshot, telephony_call_sid, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'INITIATED', 'UNDECIDED', ?, ?, ?, ?, ?)
            """,
            (call_id, mobile, proid, language, 1 if is_simulated else 0, prod_json, telephony_call_sid, now, now)
        )
        conn.commit()
    else:
        cursor.execute(
            """
            INSERT INTO calls (call_id, mobile, proid, language, status, lead_status, is_simulated, product_snapshot, telephony_call_sid, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'INITIATED', 'UNDECIDED', %s, %s, %s, NOW(), NOW())
            """,
            (call_id, mobile, proid, language, 1 if is_simulated else 0, prod_json, telephony_call_sid)
        )
    conn.close()
    return get_call(call_id)


def update_call_status(
    call_id: str,
    status: Optional[str] = None,
    lead_status: Optional[str] = None,
    order_payload: Optional[Dict[str, Any]] = None,
    duration_seconds: Optional[int] = None,
    telephony_call_sid: Optional[str] = None
) -> None:
    """Updates call state, lead outcome, and optional strict order JSON."""
    conn = _get_connection()
    cursor = conn.cursor()

    updates = []
    params = []

    if status:
        updates.append("status = ?")
        params.append(status)
    if lead_status:
        updates.append("lead_status = ?")
        params.append(lead_status)
    if order_payload is not None:
        updates.append("order_payload = ?")
        # Enforce strict JSON output
        params.append(json.dumps(order_payload, ensure_ascii=False) if order_payload else None)
    if duration_seconds is not None:
        updates.append("duration_seconds = ?")
        params.append(duration_seconds)
    if telephony_call_sid:
        updates.append("telephony_call_sid = ?")
        params.append(telephony_call_sid)

    now = datetime.datetime.now().isoformat()
    updates.append("updated_at = ?")
    params.append(now)

    if updates:
        params.append(call_id)
        if _DB_TYPE == "sqlite":
            query = f"UPDATE calls SET {', '.join(updates)} WHERE call_id = ?"
            cursor.execute(query, params)
            conn.commit()
        else:
            query = f"UPDATE calls SET {', '.join([u.replace('?', '%s') for u in updates])} WHERE call_id = %s"
            cursor.execute(query, params)

    conn.close()


def add_transcript(call_id: str, speaker: str, text: str) -> None:
    """Appends a speech turn to conversation transcript."""
    conn = _get_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    if _DB_TYPE == "sqlite":
        cursor.execute(
            "INSERT INTO transcripts (call_id, speaker, text, created_at) VALUES (?, ?, ?, ?)",
            (call_id, speaker.upper(), text, now)
        )
        conn.commit()
    else:
        cursor.execute(
            "INSERT INTO transcripts (call_id, speaker, text, created_at) VALUES (%s, %s, %s, NOW())",
            (call_id, speaker.upper(), text)
        )
    conn.close()


def get_call(call_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves full call record by call_id."""
    conn = _get_connection()
    cursor = conn.cursor()
    if _DB_TYPE == "sqlite":
        cursor.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
    else:
        cursor.execute("SELECT * FROM calls WHERE call_id = %s", (call_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        d = row

    if d.get("order_payload"):
        try:
            d["order_payload"] = json.loads(d["order_payload"])
        except Exception:
            pass
    if d.get("product_snapshot"):
        try:
            d["product_snapshot"] = json.loads(d["product_snapshot"])
        except Exception:
            pass
    d["is_simulated"] = bool(d.get("is_simulated"))
    return d


def get_call_transcript(call_id: str) -> List[Dict[str, Any]]:
    """Retrieves all conversation transcript items for a call."""
    conn = _get_connection()
    cursor = conn.cursor()
    if _DB_TYPE == "sqlite":
        cursor.execute(
            "SELECT speaker, text, created_at FROM transcripts WHERE call_id = ? ORDER BY id ASC",
            (call_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"speaker": r["speaker"], "text": r["text"], "timestamp": r["created_at"]} for r in rows]
    else:
        cursor.execute(
            "SELECT speaker, text, created_at FROM transcripts WHERE call_id = %s ORDER BY id ASC",
            (call_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"speaker": r["speaker"], "text": r["text"], "timestamp": str(r["created_at"])} for r in rows]


def list_calls(limit: int = 50, lead_status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lists recent calls with optional status filtering."""
    conn = _get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM calls"
    params = []

    if lead_status:
        query += " WHERE lead_status = ?" if _DB_TYPE == "sqlite" else " WHERE lead_status = %s"
        params.append(lead_status.upper())

    query += " ORDER BY id DESC LIMIT ?" if _DB_TYPE == "sqlite" else " ORDER BY id DESC LIMIT %s"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r) if _DB_TYPE == "sqlite" else r
        if d.get("order_payload"):
            try:
                d["order_payload"] = json.loads(d["order_payload"])
            except Exception:
                pass
        if d.get("product_snapshot"):
            try:
                d["product_snapshot"] = json.loads(d["product_snapshot"])
            except Exception:
                pass
        d["is_simulated"] = bool(d.get("is_simulated"))
        result.append(d)
    return result


def is_event_processed(event_id: str) -> bool:
    """Idempotency check to prevent duplicate order generation or processing."""
    if not event_id:
        return False
    conn = _get_connection()
    cursor = conn.cursor()
    if _DB_TYPE == "sqlite":
        cursor.execute("SELECT 1 FROM webhook_events WHERE event_id = ?", (event_id,))
    else:
        cursor.execute("SELECT 1 FROM webhook_events WHERE event_id = %s", (event_id,))
    found = cursor.fetchone()
    conn.close()
    return bool(found)


def record_webhook_event(event_id: str, call_id: Optional[str], event_type: str, payload: Dict[str, Any]) -> None:
    """Records processed webhook event."""
    conn = _get_connection()
    cursor = conn.cursor()
    p_json = json.dumps(payload, ensure_ascii=False)
    now = datetime.datetime.now().isoformat()
    try:
        if _DB_TYPE == "sqlite":
            cursor.execute(
                "INSERT INTO webhook_events (event_id, call_id, event_type, payload, processed_at) VALUES (?, ?, ?, ?, ?)",
                (event_id, call_id, event_type, p_json, now)
            )
            conn.commit()
        else:
            cursor.execute(
                "INSERT INTO webhook_events (event_id, call_id, event_type, payload, processed_at) VALUES (%s, %s, %s, %s, NOW())",
                (event_id, call_id, event_type, p_json)
            )
    except Exception as e:
        print(f"[DB] Error recording event {event_id}: {e}")
    conn.close()


# Initialize tables on import safely
try:
    init_db()
except Exception as e:
    print(f"[DB] Initial database setup warning (will retry on demand): {e}")

