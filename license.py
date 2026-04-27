"""License key management for Webcatch Pro."""
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "licenses.db")

def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            key TEXT PRIMARY KEY,
            email TEXT,
            stripe_session_id TEXT,
            created_at TEXT,
            validated_at TEXT,
            is_valid INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def create_license(email: str = None, stripe_session_id: str = None) -> str:
    init_db()
    key = "wc-" + uuid.uuid4().hex[:24]
    conn = _get_conn()
    conn.execute(
        "INSERT INTO licenses (key, email, stripe_session_id, created_at) VALUES (?, ?, ?, ?)",
        (key, email, stripe_session_id, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()
    return key

def get_license(key: str) -> dict:
    init_db()
    conn = _get_conn()
    row = conn.execute("SELECT * FROM licenses WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def validate_license(key: str) -> bool:
    lic = get_license(key)
    return lic is not None and lic.get("is_valid", 0) == 1

def mark_validated(key: str):
    init_db()
    conn = _get_conn()
    conn.execute(
        "UPDATE licenses SET validated_at = ? WHERE key = ?",
        (datetime.now(timezone.utc).isoformat(), key)
    )
    conn.commit()
    conn.close()
