"""环境配置。"""

from __future__ import annotations

import os


class Settings:
    app_name: str = "Guess Who I Am API"
    app_version: str = "3.0.0"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    default_person_scope: str = os.getenv("GWI_PERSON_SCOPE", "中国历史人物")
    default_max_rounds: int = int(os.getenv("GWI_MAX_ROUNDS", "10"))
    min_rounds: int = 1
    max_rounds_limit: int = 20

    scope_min_len: int = 1
    scope_max_len: int = 30
    text_min_len: int = 1
    text_max_len: int = 200

    session_ttl_seconds: int = int(os.getenv("GWI_SESSION_TTL", "1800"))  # 30 分钟
    reaper_interval_seconds: int = 300


settings = Settings()
