"""LLM 客户端：加载根目录 .env，构造 Anthropic 单例。"""

from __future__ import annotations

import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

# backend/app/llm/client.py → parents[3] = 项目根目录（.env 所在处）
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_PATH = _REPO_ROOT / ".env"

if _ENV_PATH.exists():
    load_dotenv(dotenv_path=_ENV_PATH, override=False)

_CLIENT: Anthropic | None = None


def get_client() -> Anthropic:
    global _CLIENT
    if _CLIENT is None:
        base_url = os.getenv("ANTHROPIC_BASE_URL") or None
        if base_url:
            # 兼容国内 Anthropic 兼容端点（避免误用 SDK 旧 token 变量）
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
        _CLIENT = Anthropic(base_url=base_url)
    return _CLIENT


def get_model() -> str:
    return os.getenv("MODEL_ID", "claude-sonnet-4-6")
