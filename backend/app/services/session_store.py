"""内存会话仓库：session_id → SessionEntry。

- 单进程内存；每会话一把 asyncio.Lock 串行化动作
- 空闲 TTL（默认 30 分钟）惰性清理 + 后台 reaper 兜底
- 终态后由 orchestrator 调用 release() 立即释放
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from game_state import GameConfig, GameSession

from ..config import settings


@dataclass
class SessionEntry:
    session: GameSession
    messages: list = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_active: float = field(default_factory=time.monotonic)
    host_message: Optional[str] = None

    def touch(self) -> None:
        self.last_active = time.monotonic()


class SessionStore:
    def __init__(self, ttl_seconds: int = settings.session_ttl_seconds) -> None:
        self._entries: dict[str, SessionEntry] = {}
        self._ttl = ttl_seconds

    # ---------- 基本操作 ----------

    def create(
        self,
        max_rounds: int = settings.default_max_rounds,
        person_scope: str = settings.default_person_scope,
    ) -> SessionEntry:
        sid = str(uuid.uuid4())
        config = GameConfig(max_rounds=max_rounds, person_scope=person_scope)
        session = GameSession(config=config)
        session.session_id = sid
        entry = SessionEntry(session=session)
        self._entries[sid] = entry
        return entry

    def get(self, session_id: str) -> Optional[SessionEntry]:
        entry = self._entries.get(session_id)
        if entry is None:
            return None
        if time.monotonic() - entry.last_active > self._ttl:
            self._entries.pop(session_id, None)
            return None
        entry.touch()
        return entry

    def release(self, session_id: str) -> None:
        """终态后立即释放（结果数据已随响应返回前端）。"""
        self._entries.pop(session_id, None)

    def purge_expired(self) -> int:
        now = time.monotonic()
        expired = [
            sid for sid, e in self._entries.items()
            if now - e.last_active > self._ttl
        ]
        for sid in expired:
            self._entries.pop(sid, None)
        return len(expired)

    def active_count(self) -> int:
        return len(self._entries)


# 全局单例
session_store = SessionStore()
