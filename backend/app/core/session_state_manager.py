from __future__ import annotations

from threading import Lock
from uuid import UUID

from app.schemas.session_state import SessionState

from .session_store import SessionStore


class SessionStateManager:
    """会话状态管理：内存为一级缓存，SQLite 为持久层。

    写操作直接透写落库；读操作在内存未命中时回落到数据库，因此进程重启后
    未完成的设计（含参数台账、计算记录、待决问题）可以原样续接。
    """

    def __init__(self, store: SessionStore | None = None):
        self._states: dict[UUID, SessionState] = {}
        self._session_keys: dict[str, UUID] = {}
        self._lock = Lock()
        self._store = store if store is not None else SessionStore()

    @property
    def store(self) -> SessionStore:
        return self._store

    def create(self, state: SessionState) -> SessionState:
        with self._lock:
            self._states[state.session_id] = state
        self._store.save(state)
        return state

    def get(self, session_id: UUID) -> SessionState | None:
        state = self._states.get(session_id)
        if state is not None:
            return state
        state = self._store.load(session_id)
        if state is not None:
            with self._lock:
                self._states[session_id] = state
        return state

    def update(self, state: SessionState) -> SessionState:
        with self._lock:
            self._states[state.session_id] = state
        self._store.save(state)
        return state

    def bind_session_key(self, session_key: str, session_id: UUID) -> None:
        with self._lock:
            self._session_keys[session_key] = session_id
        self._store.bind_key(session_key, session_id)

    def get_by_session_key(self, session_key: str) -> SessionState | None:
        session_id = self._session_keys.get(session_key)
        if session_id is None:
            session_id = self._store.resolve_key(session_key)
            if session_id is None:
                return None
            with self._lock:
                self._session_keys[session_key] = session_id
        return self.get(session_id)

    def list_recent(self, limit: int = 20) -> list[dict]:
        return self._store.list_recent(limit)

    def delete(self, session_id: UUID) -> bool:
        with self._lock:
            self._states.pop(session_id, None)
            for key, value in list(self._session_keys.items()):
                if value == session_id:
                    self._session_keys.pop(key)
        return self._store.delete(session_id)
