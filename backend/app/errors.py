"""错误码枚举、ApiError、统一错误信封。"""

from __future__ import annotations

import contextvars
import uuid
from enum import Enum
from typing import Any, Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


# ---------- request_id ----------

REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "gwi_request_id", default=""
)


def new_request_id() -> str:
    rid = f"req-{uuid.uuid4().hex[:16]}"
    REQUEST_ID.set(rid)
    return rid


# ---------- 错误码 ----------

class ErrorCode(str, Enum):
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    INVALID_PHASE = "INVALID_PHASE"
    PHASE_CONFLICT = "PHASE_CONFLICT"
    QUESTION_BUDGET_EXHAUSTED = "QUESTION_BUDGET_EXHAUSTED"
    GUESS_BUDGET_EXHAUSTED = "GUESS_BUDGET_EXHAUSTED"
    GAME_NOT_ACTIVE = "GAME_NOT_ACTIVE"
    EMPTY_INPUT = "EMPTY_INPUT"
    INPUT_TOO_LONG = "INPUT_TOO_LONG"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    NOT_YES_NO_QUESTION = "NOT_YES_NO_QUESTION"
    INVALID_GUESS = "INVALID_GUESS"
    RATE_LIMITED = "RATE_LIMITED"
    UPSTREAM_LLM_ERROR = "UPSTREAM_LLM_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_ERROR_HTTP: dict[ErrorCode, int] = {
    ErrorCode.SESSION_NOT_FOUND: 404,
    ErrorCode.INVALID_PHASE: 409,
    ErrorCode.PHASE_CONFLICT: 409,
    ErrorCode.QUESTION_BUDGET_EXHAUSTED: 409,
    ErrorCode.GUESS_BUDGET_EXHAUSTED: 409,
    ErrorCode.GAME_NOT_ACTIVE: 409,
    ErrorCode.EMPTY_INPUT: 422,
    ErrorCode.INPUT_TOO_LONG: 422,
    ErrorCode.INVALID_PARAMETER: 422,
    ErrorCode.NOT_YES_NO_QUESTION: 422,
    ErrorCode.INVALID_GUESS: 422,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.UPSTREAM_LLM_ERROR: 502,
    ErrorCode.INTERNAL_ERROR: 500,
}

_ERROR_DEFAULT_MESSAGE: dict[ErrorCode, str] = {
    ErrorCode.SESSION_NOT_FOUND: "会话不存在或已过期，请重新开始游戏。",
    ErrorCode.INVALID_PHASE: "当前阶段不允许该操作，请刷新后重试。",
    ErrorCode.PHASE_CONFLICT: "页面状态已过期，正在同步最新状态。",
    ErrorCode.QUESTION_BUDGET_EXHAUSTED: "提问次数已用完。",
    ErrorCode.GUESS_BUDGET_EXHAUSTED: "猜测次数已用完。",
    ErrorCode.GAME_NOT_ACTIVE: "游戏已结束，请重新开始一局。",
    ErrorCode.EMPTY_INPUT: "内容不能为空。",
    ErrorCode.INPUT_TOO_LONG: "内容最多 200 字。",
    ErrorCode.INVALID_PARAMETER: "参数校验失败。",
    ErrorCode.NOT_YES_NO_QUESTION: "请重新提问，不是判断题，不能用『是』或『否』回答。",
    ErrorCode.INVALID_GUESS: "请输入你要猜测的人物名称。",
    ErrorCode.RATE_LIMITED: "操作过于频繁，请稍后再试。",
    ErrorCode.UPSTREAM_LLM_ERROR: "主持人暂时开小差，请重试。",
    ErrorCode.INTERNAL_ERROR: "服务开小差了，请稍后再试。",
}


class ApiError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        status_code: Optional[int] = None,
    ) -> None:
        self.code = code
        self.message = message or _ERROR_DEFAULT_MESSAGE[code]
        self.details = details or {}
        self.status_code = status_code or _ERROR_HTTP[code]
        super().__init__(self.message)


def error_envelope(code: str, message: str, details: Optional[dict] = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
        "request_id": REQUEST_ID.get() or f"req-{uuid.uuid4().hex[:16]}",
    }


# ---------- FastAPI 异常处理器 ----------

async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(exc.code.value, exc.message, exc.details),
    )


async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = {"issues": exc.errors()}
    # 对常见字段错误给出更友好的中文消息
    message = "参数校验失败，请检查输入。"
    for err in exc.errors():
        if err.get("type") in ("missing", "value_error"):
            message = "请填写完整内容后再提交。"
            break
    return JSONResponse(
        status_code=422,
        content=error_envelope(
            ErrorCode.INVALID_PARAMETER.value, message, details
        ),
    )


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=error_envelope(
            ErrorCode.INTERNAL_ERROR.value,
            _ERROR_DEFAULT_MESSAGE[ErrorCode.INTERNAL_ERROR],
        ),
    )
