"""
person_history.py - 最近使用人物注册表（第 1+2 层去重方案）

- 进程级单例，独立于 session 生命周期（终态释放会话不影响注册表）
- JSON 落盘：geuss_who_i_am/data/recent_persons.json，服务/CLI 重启后仍生效
- FIFO 保留最近 N 位（默认 10），按 person_scope 隔离
- 线程锁 + 原子写（临时文件 os.replace），损坏文件自动备份并重置
- 去重以"规范名 + 别名集合"交叉比对，防止"苏轼/苏东坡"绕过

环境变量：
    GWI_RECENT_PERSONS     保留人数（默认 10）
    GWI_RECENT_PERSONS_FILE 自定义 JSON 路径（测试用）
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DEFAULT_FILE = Path(__file__).resolve().parent / "data" / "recent_persons.json"


def _file_path() -> Path:
    custom = os.getenv("GWI_RECENT_PERSONS_FILE")
    return Path(custom) if custom else _DEFAULT_FILE


def _limit() -> int:
    try:
        return max(1, int(os.getenv("GWI_RECENT_PERSONS", "10")))
    except ValueError:
        return 10


def _normalize(name: str) -> str:
    return (name or "").strip()


def _norm_scope(scope: str) -> str:
    return (scope or "").strip()


# ---------- 数据结构 ----------

@dataclass
class PersonEntry:
    canonical: str                       # 规范名
    aliases: list[str] = field(default_factory=list)
    scope: str = "中国历史人物"
    ts: str = ""

    def name_set(self) -> set[str]:
        names = {_normalize(self.canonical)}
        names.update(_normalize(a) for a in self.aliases if _normalize(a))
        return {n for n in names if n}

    def to_dict(self) -> dict:
        return {
            "canonical": self.canonical,
            "aliases": self.aliases,
            "scope": self.scope,
            "ts": self.ts,
        }

    @staticmethod
    def from_dict(raw: dict) -> "PersonEntry":
        aliases = raw.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []
        return PersonEntry(
            canonical=str(raw.get("canonical", "")).strip(),
            aliases=[str(a).strip() for a in aliases if str(a).strip()],
            scope=str(raw.get("scope", "")).strip(),
            ts=str(raw.get("ts", "")),
        )


# ---------- 注册表 ----------

_lock = threading.Lock()


def _load() -> list[PersonEntry]:
    path = _file_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("注册表根结构不是数组")
        entries = [PersonEntry.from_dict(item) for item in raw if isinstance(item, dict)]
        return [e for e in entries if e.canonical]
    except (json.JSONDecodeError, ValueError, OSError):
        # 损坏：备份后重置，避免阻塞开局
        try:
            backup = path.with_suffix(f".corrupt-{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
            path.rename(backup)
        except OSError:
            pass
        return []


def _save(entries: list[PersonEntry]) -> None:
    path = _file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        [e.to_dict() for e in entries], ensure_ascii=False, indent=2
    )
    # 原子写：同目录临时文件 + os.replace，防止 0 字节/半写文件
    fd, tmp_name = tempfile.mkstemp(
        prefix=".recent_persons.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------- 公开 API ----------

def recent_entries(scope: Optional[str] = None, limit: Optional[int] = None) -> list[PersonEntry]:
    """返回最近使用记录（按时间升序，最新在末尾）；可按 scope 过滤。"""
    with _lock:
        entries = _load()
    if scope is not None:
        target = _norm_scope(scope)
        entries = [e for e in entries if e.scope == target]
    n = limit if limit is not None else _limit()
    return entries[-n:]


def recent_names(scope: Optional[str] = None, limit: Optional[int] = None) -> list[str]:
    """人类可读的展示串，如 '苏轼（苏东坡、苏子瞻）'。"""
    out: list[str] = []
    for e in recent_entries(scope, limit):
        extra = [a for a in e.aliases if a != e.canonical]
        out.append(f"{e.canonical}（{'、'.join(extra)}）" if extra else e.canonical)
    return out


def is_recent(canonical: str, aliases: Optional[list[str]] = None,
              scope: Optional[str] = None) -> bool:
    """候选人物（规范名+别名）是否与最近记录中任一人物重名（交叉比对）。"""
    candidate = {_normalize(canonical)}
    candidate.update(_normalize(a) for a in (aliases or []))
    candidate = {n for n in candidate if n}
    if not candidate:
        return False
    for entry in recent_entries(scope):
        if candidate & entry.name_set():
            return True
    return False


def record(canonical: str, aliases: Optional[list[str]] = None,
           scope: str = "中国历史人物") -> None:
    """成功开局后登记人物（FIFO，去旧留新）。"""
    name = _normalize(canonical)
    if not name:
        return
    alias_list = [_normalize(a) for a in (aliases or [])]
    alias_list = [a for a in dict.fromkeys(alias_list) if a and a != name]
    entry = PersonEntry(
        canonical=name,
        aliases=alias_list,
        scope=_norm_scope(scope) or "中国历史人物",
        ts=datetime.now(timezone.utc).isoformat(),
    )
    with _lock:
        entries = _load()
        # 同 scope 下同名（含别名交叉）先剔除旧记录，保证 FIFO 语义
        entry_names = entry.name_set()
        entries = [
            e for e in entries
            if not (e.scope == entry.scope and (entry_names & e.name_set()))
        ]
        entries.append(entry)
        _save(entries[-_limit():])


def exclusion_block(scope: Optional[str] = None) -> str:
    """生成注入 SYSTEM prompt 的结构化排除区块；无记录时返回空串。"""
    names = recent_names(scope)
    if not names:
        return ""
    lines = "\n".join(f"- {n}" for n in names)
    return (
        "## 本局禁止选择的人物\n"
        f"以下人物在最近 {len(names)} 局中已使用过，本局**禁止**再次选择"
        "（包括其字、号、别名、尊称；例如列表中有\"苏轼\"，则\"苏东坡/子瞻\"同样禁止）：\n"
        f"{lines}\n"
        "请优先选择与上述人物不同朝代、不同知名度层级的人物，保证多样性。\n"
        "调用 start_game 时必须回填 canonical_name（规范姓名）与 aliases"
        "（字/号/别名数组，无别名给空数组）。"
    )
