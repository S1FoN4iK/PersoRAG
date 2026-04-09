
import os
import sqlite3
import threading
import time
from typing import Optional

from config import HISTORY_DB, MAX_HISTORY


_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    db_dir = os.path.dirname(HISTORY_DB)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    _conn = sqlite3.connect(HISTORY_DB, check_same_thread=False, isolation_level=None)
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            character_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            ts REAL NOT NULL
        )
    """)
    _conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_user_char
        ON messages(user_id, character_id, id)
    """)
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS user_state (
            user_id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL
        )
    """)
    return _conn


def get_history(user_id: str, character_id: str) -> list[dict]:
    """Возвращает последние MAX_HISTORY сообщений в хронологическом порядке."""
    with _lock:
        cur = _connect().execute(
            """
            SELECT role, content FROM (
                SELECT id, role, content FROM messages
                WHERE user_id = ? AND character_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) ORDER BY id ASC
            """,
            (user_id, character_id, MAX_HISTORY),
        )
        return [{"role": r, "content": c} for r, c in cur.fetchall()]


def add_message(user_id: str, character_id: str, role: str, content: str) -> None:
    with _lock:
        _connect().execute(
            "INSERT INTO messages(user_id, character_id, role, content, ts) VALUES (?, ?, ?, ?, ?)",
            (user_id, character_id, role, content, time.time()),
        )


def clear_history(user_id: str, character_id: str) -> None:
    with _lock:
        _connect().execute(
            "DELETE FROM messages WHERE user_id = ? AND character_id = ?",
            (user_id, character_id),
        )


def get_user_character(user_id: str, default: str) -> str:
    with _lock:
        cur = _connect().execute(
            "SELECT character_id FROM user_state WHERE user_id = ?", (user_id,)
        )
        row = cur.fetchone()
        return row[0] if row else default


def set_user_character(user_id: str, character_id: str) -> None:
    with _lock:
        _connect().execute(
            """
            INSERT INTO user_state(user_id, character_id) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET character_id = excluded.character_id
            """,
            (user_id, character_id),
        )
