"""FastAPI 应用入口。

启动（工作目录为 geuss_who_i_am/）：
    uvicorn backend.app.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from .api.routes.games import router as games_router
from .config import settings
from .errors import (
    ApiError,
    api_error_handler,
    new_request_id,
    unhandled_error_handler,
    validation_error_handler,
)
from .services.session_store import session_store

logger = logging.getLogger("gwi")


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    # 后台 TTL 清理（惰性清理之外的兜底）
    stop_event = asyncio.Event()

    async def _reaper() -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=settings.reaper_interval_seconds
                )
            except asyncio.TimeoutError:
                removed = session_store.purge_expired()
                if removed:
                    logger.info("session reaper removed %s expired sessions", removed)

    task = asyncio.create_task(_reaper())
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    new_request_id()
    response = await call_next(request)
    return response


app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(games_router, prefix="/api/v1")


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict:
    return {"status": "ok", "active_sessions": session_store.active_count()}
