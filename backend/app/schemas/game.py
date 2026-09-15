"""游戏相关 DTO（与前端 TypeScript 类型逐字段同名同形，snake_case）。"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------- 请求体 ----------

class CreateGameRequest(BaseModel):
    person_scope: Optional[str] = Field(default=None, description="人物范围，1..30 字")
    max_rounds: Optional[int] = Field(default=None, ge=1, le=20)


class AskRequest(BaseModel):
    text: str


class GuessRequest(BaseModel):
    text: str


class SkipRequest(BaseModel):
    current_phase: Optional[Literal["question", "guess"]] = None


# ---------- 响应体 ----------

class PersonDTO(BaseModel):
    name: str
    hint: str
    intro: str


class QARecordDTO(BaseModel):
    seq: int
    kind: Literal["ask", "skip"]
    question: Optional[str]
    answer: Optional[Literal["yes", "no"]]
    round: int


class GuessRecordDTO(BaseModel):
    seq: int
    kind: Literal["guess", "skip"]
    guess: Optional[str]
    is_correct: Optional[bool]
    round: int


class LastAnswerDTO(BaseModel):
    question: str
    answer: Literal["yes", "no"]


class GuessHintDTO(BaseModel):
    guess: str
    message: str


class ResultDTO(BaseModel):
    type: Literal["win", "exhausted", "aborted"]
    title: str
    message: str
    person: Optional[PersonDTO]


class GameDTO(BaseModel):
    session_id: str
    status: Literal["idle", "playing", "result"]
    phase: Optional[Literal["question", "guess"]]
    current_round: int
    person_hint: str
    max_rounds: int
    questions_used: int
    questions_remaining: int
    guesses_used: int
    guesses_remaining: int
    qa_history: list[QARecordDTO]
    guess_history: list[GuessRecordDTO]
    result: Optional[ResultDTO]
    last_answer: Optional[LastAnswerDTO]
    last_guess_hint: Optional[GuessHintDTO]
    host_message: Optional[str]
    created_at: str
    updated_at: str
