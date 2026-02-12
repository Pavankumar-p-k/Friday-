from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  note TEXT NOT NULL,
                  due_at TEXT NOT NULL,
                  is_done INTEGER NOT NULL DEFAULT 0,
                  notified_at TEXT,
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT NOT NULL,
                  user_text TEXT NOT NULL,
                  assistant_text TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  created_at TEXT NOT NULL
                )
                """
            )
            # Lightweight migration for pre-existing databases.
            columns = conn.execute("PRAGMA table_info(reminders)").fetchall()
            column_names = {str(row["name"]) for row in columns}
            if "notified_at" not in column_names:
                conn.execute("ALTER TABLE reminders ADD COLUMN notified_at TEXT")
            conn.commit()

    def save_history(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str,
        mode: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO history(session_id, user_text, assistant_text, mode, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, user_text, assistant_text, mode, _utc_now_iso()),
            )
            conn.commit()

    def add_reminder(self, note: str, due_at: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reminders(note, due_at, is_done, created_at)
                VALUES (?, ?, 0, ?)
                """,
                (note, due_at, _utc_now_iso()),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def list_reminders(self, include_done: bool = False) -> list[dict[str, str | int]]:
        query = "SELECT * FROM reminders"
        args: tuple[int, ...] | tuple[()] = ()
        if not include_done:
            query += " WHERE is_done = ?"
            args = (0,)
        query += " ORDER BY due_at ASC"

        with self._connect() as conn:
            rows = conn.execute(query, args).fetchall()
            result: list[dict[str, str | int]] = []
            for row in rows:
                result.append(
                    {
                        "id": int(row["id"]),
                        "note": str(row["note"]),
                        "due_at": str(row["due_at"]),
                        "is_done": int(row["is_done"]),
                        "created_at": str(row["created_at"]),
                    }
                )
            return result

    def complete_reminder(self, reminder_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE reminders SET is_done = 1 WHERE id = ?",
                (reminder_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_due_unnotified(self, before_iso: str) -> list[dict[str, str | int]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reminders
                WHERE is_done = 0
                  AND notified_at IS NULL
                  AND due_at <= ?
                ORDER BY due_at ASC
                """,
                (before_iso,),
            ).fetchall()

            result: list[dict[str, str | int]] = []
            for row in rows:
                result.append(
                    {
                        "id": int(row["id"]),
                        "note": str(row["note"]),
                        "due_at": str(row["due_at"]),
                        "is_done": int(row["is_done"]),
                        "created_at": str(row["created_at"]),
                    }
                )
            return result

    def mark_reminder_notified(self, reminder_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE reminders SET notified_at = ? WHERE id = ?",
                (_utc_now_iso(), reminder_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_recent_history(self, session_id: str, limit: int = 10) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, user_text, assistant_text, mode, created_at
                FROM history
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
            return [
                {
                    "session_id": str(row["session_id"]),
                    "user_text": str(row["user_text"]),
                    "assistant_text": str(row["assistant_text"]),
                    "mode": str(row["mode"]),
                    "created_at": str(row["created_at"]),
                }
                for row in rows
            ]
