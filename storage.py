"""SQLite-backed local chat history and user status storage.

Every peer keeps its own history -- there is no shared/server-side database.
"""
from __future__ import annotations

import sqlite3
import threading


class Storage:
    def __init__(self, db_path: str = "chat_history.db"):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_tables()

    def _init_tables(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    text TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    status TEXT
                )
                """
            )
            self._conn.commit()

    def save_message(self, chat_id: str, sender: str, text: str, timestamp: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages(chat_id, sender, text, timestamp) VALUES (?, ?, ?, ?)",
                (chat_id, sender, text, timestamp),
            )
            self._conn.commit()

    def get_history(self, chat_id: str) -> list[tuple[str, str, float]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT sender, text, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp",
                (chat_id,),
            )
            return cur.fetchall()

    def set_user_status(self, username: str, status: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO users(username, status) VALUES (?, ?)
                ON CONFLICT(username) DO UPDATE SET status = excluded.status
                """,
                (username, status),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
