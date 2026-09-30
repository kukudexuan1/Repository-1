"""SessionState 的 SQLite 持久化。"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import UUID

from app.schemas.session_state import SessionState

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    design_stage TEXT NOT NULL DEFAULT '',
    mode         TEXT NOT NULL DEFAULT '',
    family       TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL,
    payload      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_keys (
    session_key TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
"""


def default_db_path() -> Path:
    raw = os.getenv("DESIGN_DB_PATH", "").strip()
    if raw:
        return Path(raw)
    return Path("workspace") / "design_sessions.db"


class SessionStore:
    """SessionState 的读写存储。任何一次写入失败都只记日志，不影响设计流程。"""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self._lock = Lock()
        self._conn: sqlite3.Connection | None = None
        self._available = self._init_db()

    @property
    def available(self) -> bool:
        return self._available

    def _init_db(self) -> bool:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
            logger.info("会话持久化已启用: %s", self.db_path)
            return True
        except Exception as exc:  # noqa: BLE001 - 持久化不可用时降级为纯内存
            logger.error("会话持久化初始化失败，降级为内存模式: %s", exc)
            self._conn = None
            return False

    # ---- 会话 ----

    def save(self, state: SessionState) -> None:
        if not self._available or self._conn is None:
            return
        state.updated_at = datetime.now(timezone.utc)
        payload = json.dumps(state.model_dump(mode="json"), ensure_ascii=False)
        try:
            with self._lock:
                self._conn.execute(
                    """INSERT INTO sessions
                       (session_id, design_stage, mode, family, updated_at, payload)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(session_id) DO UPDATE SET
                         design_stage=excluded.design_stage,
                         mode=excluded.mode,
                         family=excluded.family,
                         updated_at=excluded.updated_at,
                         payload=excluded.payload""",
                    (
                        str(state.session_id),
                        state.design_stage.value,
                        state.mode.value,
                        state.design_spec.family,
                        state.updated_at.isoformat(),
                        payload,
                    ),
                )
                self._conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("会话 %s 落库失败: %s", state.session_id, exc)

    def load(self, session_id: UUID) -> SessionState | None:
        if not self._available or self._conn is None:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT payload FROM sessions WHERE session_id = ?",
                    (str(session_id),),
                ).fetchone()
        except Exception as exc:  # noqa: BLE001
            logger.error("会话 %s 读取失败: %s", session_id, exc)
            return None
        if row is None:
            return None
        return self._deserialize(row[0], session_id)

    def _deserialize(self, payload: str, session_id: UUID) -> SessionState | None:
        try:
            return SessionState.model_validate(json.loads(payload))
        except Exception as exc:  # noqa: BLE001 - 旧版快照与新模型不兼容时不应崩溃
            logger.error(
                "会话 %s 快照与当前 SessionState 定义不兼容（可能是版本升级）: %s",
                session_id,
                exc,
            )
            return None

    def list_recent(self, limit: int = 20) -> list[dict]:
        if not self._available or self._conn is None:
            return []
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT session_id, design_stage, mode, family, updated_at,
                              json_extract(payload, '$.design_spec.family_label'),
                              json_extract(payload, '$.design_spec.title'),
                              json_extract(payload, '$.active_agent'),
                              (SELECT COUNT(*) FROM json_each(json_extract(payload, '$.chat_history')))
                       FROM sessions ORDER BY updated_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            logger.error("会话列表读取失败: %s", exc)
            return []
        return [
            {
                "session_id": r[0],
                "design_stage": r[1],
                "mode": r[2],
                "family": r[3],
                "updated_at": r[4],
                "family_label": r[5] or "",
                "title": r[6] or "",
                "active_agent": r[7] or "none",
                "message_count": r[8] or 0,
            }
            for r in rows
        ]

    def delete(self, session_id: UUID) -> bool:
        if not self._available or self._conn is None:
            return False
        try:
            with self._lock:
                self._conn.execute(
                    "DELETE FROM sessions WHERE session_id = ?", (str(session_id),)
                )
                self._conn.execute(
                    "DELETE FROM session_keys WHERE session_id = ?", (str(session_id),)
                )
                self._conn.commit()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("会话 %s 删除失败: %s", session_id, exc)
            return False

    # ---- 前端会话键映射 ----

    def bind_key(self, session_key: str, session_id: UUID) -> None:
        if not self._available or self._conn is None:
            return
        try:
            with self._lock:
                self._conn.execute(
                    """INSERT INTO session_keys (session_key, session_id) VALUES (?, ?)
                       ON CONFLICT(session_key) DO UPDATE SET session_id=excluded.session_id""",
                    (session_key, str(session_id)),
                )
                self._conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("会话键 %s 绑定失败: %s", session_key, exc)

    def resolve_key(self, session_key: str) -> UUID | None:
        if not self._available or self._conn is None:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT session_id FROM session_keys WHERE session_key = ?",
                    (session_key,),
                ).fetchone()
        except Exception as exc:  # noqa: BLE001
            logger.error("会话键 %s 解析失败: %s", session_key, exc)
            return None
        if row is None:
            return None
        try:
            return UUID(row[0])
        except ValueError:
            return None

    def close(self) -> None:
        if self._conn is not None:
            with self._lock:
                self._conn.close()
                self._conn = None
