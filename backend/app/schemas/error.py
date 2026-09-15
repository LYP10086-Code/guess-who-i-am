"""统一错误信封 DTO（仅作文档化，实际响应由 errors.py 构造）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
    request_id: str
