from __future__ import annotations

from datetime import datetime, timezone
import json
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS voice_history (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT NOT NULL,
                  transcript TEXT NOT NULL,
                  reply TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  llm_backend TEXT NOT NULL,
                  stt_backend TEXT NOT NULL,
                  tts_backend TEXT NOT NULL,
                  meta_json TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dashboard_logs (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  level TEXT NOT NULL,
                  message TEXT NOT NULL,
                  source TEXT NOT NULL,
                  meta_json TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dashboard_settings (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS action_history (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT NOT NULL,
                  actor TEXT NOT NULL,
                  tool TEXT NOT NULL,
                  args_json TEXT NOT NULL DEFAULT '{}',
                  success INTEGER NOT NULL,
                  message TEXT NOT NULL,
                  data_json TEXT NOT NULL DEFAULT '{}',
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

    def save_voice_history(
        self,
        session_id: str,
        transcript: str,
        reply: str,
        mode: str,
        llm_backend: str,
        stt_backend: str = "",
        tts_backend: str = "",
        meta: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        meta_json = json.dumps(meta or {}, ensure_ascii=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO voice_history(
                  session_id, transcript, reply, mode, llm_backend, stt_backend, tts_backend, meta_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    transcript,
                    reply,
                    mode,
                    llm_backend,
                    stt_backend,
                    tts_backend,
                    meta_json,
                    _utc_now_iso(),
                ),
            )
            conn.commit()

    def list_voice_history(self, limit: int = 50) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, transcript, reply, mode, llm_backend, stt_backend, tts_backend, meta_json, created_at
                FROM voice_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            result: list[dict[str, object]] = []
            for row in rows:
                result.append(
                    {
                        "id": int(row["id"]),
                        "session_id": str(row["session_id"]),
                        "transcript": str(row["transcript"]),
                        "reply": str(row["reply"]),
                        "mode": str(row["mode"]),
                        "llm_backend": str(row["llm_backend"]),
                        "stt_backend": str(row["stt_backend"]),
                        "tts_backend": str(row["tts_backend"]),
                        "meta": _safe_json_load(str(row["meta_json"])),
                        "created_at": str(row["created_at"]),
                    }
                )
            return result

    def save_dashboard_log(
        self,
        level: str,
        message: str,
        source: str,
        meta: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        meta_json = json.dumps(meta or {}, ensure_ascii=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO dashboard_logs(level, message, source, meta_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (level.upper(), message, source, meta_json, _utc_now_iso()),
            )
            conn.commit()

    def list_dashboard_logs(self, limit: int = 100) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, level, message, source, meta_json, created_at
                FROM dashboard_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            result: list[dict[str, object]] = []
            for row in rows:
                result.append(
                    {
                        "id": int(row["id"]),
                        "level": str(row["level"]),
                        "message": str(row["message"]),
                        "source": str(row["source"]),
                        "meta": _safe_json_load(str(row["meta_json"])),
                        "created_at": str(row["created_at"]),
                    }
                )
            return result

    def upsert_dashboard_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO dashboard_settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, _utc_now_iso()),
            )
            conn.commit()

    def get_dashboard_settings(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value FROM dashboard_settings ORDER BY key ASC"
            ).fetchall()
            return {str(row["key"]): str(row["value"]) for row in rows}

    def save_action_history(
        self,
        session_id: str,
        actor: str,
        tool: str,
        args: dict[str, object],
        success: bool,
        message: str,
        data: dict[str, object] | None = None,
    ) -> None:
        args_json = json.dumps(args, ensure_ascii=True)
        data_json = json.dumps(data or {}, ensure_ascii=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO action_history(session_id, actor, tool, args_json, success, message, data_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    actor,
                    tool,
                    args_json,
                    1 if success else 0,
                    message,
                    data_json,
                    _utc_now_iso(),
                ),
            )
            conn.commit()

    def list_action_history(self, limit: int = 50) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, actor, tool, args_json, success, message, data_json, created_at
                FROM action_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            result: list[dict[str, object]] = []
            for row in rows:
                result.append(
                    {
                        "id": int(row["id"]),
                        "session_id": str(row["session_id"]),
                        "actor": str(row["actor"]),
                        "tool": str(row["tool"]),
                        "args": _safe_json_load(str(row["args_json"])),
                        "success": bool(int(row["success"])),
                        "message": str(row["message"]),
                        "data": _safe_json_load(str(row["data_json"])),
                        "created_at": str(row["created_at"]),
                    }
                )
            return result

    def get_dashboard_stats(self) -> dict[str, int]:
        with self._connect() as conn:
            history_count = int(conn.execute("SELECT COUNT(*) FROM history").fetchone()[0])
            voice_count = int(conn.execute("SELECT COUNT(*) FROM voice_history").fetchone()[0])
            action_count = int(conn.execute("SELECT COUNT(*) FROM action_history").fetchone()[0])
            action_success = int(
                conn.execute("SELECT COUNT(*) FROM action_history WHERE success = 1").fetchone()[0]
            )
            action_fail = int(
                conn.execute("SELECT COUNT(*) FROM action_history WHERE success = 0").fetchone()[0]
            )
            logs_count = int(conn.execute("SELECT COUNT(*) FROM dashboard_logs").fetchone()[0])
        return {
            "chat_history_count": history_count,
            "voice_history_count": voice_count,
            "action_history_count": action_count,
            "action_success_count": action_success,
            "action_failure_count": action_fail,
            "log_count": logs_count,
        }


def _safe_json_load(value: str) -> dict[str, object]:
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}
