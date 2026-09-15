"""/api/v1/games 路由：仅做入参解析 → 调 orchestrator → 返回 DTO。"""

from __future__ import annotations

from fastapi import APIRouter

from ...schemas.game import (
    AskRequest,
    CreateGameRequest,
    GameDTO,
    GuessRequest,
    SkipRequest,
)
from ...services import orchestrator

router = APIRouter(prefix="/games", tags=["games"])


@router.post("", response_model=GameDTO, status_code=201)
async def create_game(req: CreateGameRequest) -> GameDTO:
    return await orchestrator.create_game(req)


@router.get("/{session_id}", response_model=GameDTO)
async def get_game(session_id: str) -> GameDTO:
    return await orchestrator.get_game(session_id)


@router.post("/{session_id}/questions", response_model=GameDTO)
async def ask_question(session_id: str, req: AskRequest) -> GameDTO:
    return await orchestrator.ask(session_id, req.text)


@router.post("/{session_id}/guesses", response_model=GameDTO)
async def make_guess(session_id: str, req: GuessRequest) -> GameDTO:
    return await orchestrator.guess(session_id, req.text)


@router.post("/{session_id}/skip", response_model=GameDTO)
async def skip_phase(session_id: str, req: SkipRequest) -> GameDTO:
    return await orchestrator.skip(session_id, req.current_phase)


@router.post("/{session_id}/retry", response_model=GameDTO)
async def retry(session_id: str) -> GameDTO:
    return await orchestrator.retry(session_id)


@router.post("/{session_id}/abandon", response_model=GameDTO)
async def abandon(session_id: str) -> GameDTO:
    return await orchestrator.abandon(session_id)
