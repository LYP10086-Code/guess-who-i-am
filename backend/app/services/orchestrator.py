"""动作编排层：DTO ↔ 会话、驱动 LLM、提取工具结果。

规则唯一事实源在 game_state.py；本层只负责：
- HTTP 入参校验 → 状态机守卫 → 调用 agent_loop（或纯本地流转）→ GameDTO
- 领域异常 → ApiError 错误码映射
- 终态后释放会话
"""

from __future__ import annotations

import asyncio
from typing import Optional

from input_guard import GUESS_INPUT_IS_QUESTION, looks_like_question

from game_state import (
    GameSession,
    GameStatus,
    Phase,
    AnswerType,
    ResultType,
    InvalidPhaseError,
    GameNotActiveError,
    QuestionBudgetExhausted,
    GuessBudgetExhausted,
)
import person_history
from prompts import build_system_prompt

from ..config import settings
from ..errors import ApiError, ErrorCode
from ..llm.agent_runner import run_agent_loop, UpstreamLLMError
from ..schemas.game import (
    CreateGameRequest,
    GameDTO,
    GuessHintDTO,
    GuessRecordDTO,
    LastAnswerDTO,
    PersonDTO,
    QARecordDTO,
    ResultDTO,
)
from .session_store import SessionEntry, session_store

# ---------- 常量 ----------

ANSWER_TO_API = {AnswerType.YES: "yes", AnswerType.NO: "no"}

_RESULT_META = {
    ResultType.WIN: ("恭喜答对", "恭喜你，猜对了！"),
    ResultType.EXHAUSTED: ("次数用完", "次数用完，游戏结束。"),
    ResultType.ABORTED: ("游戏已中止", "游戏已中止。"),
}

NOT_YES_NO_FALLBACK = "请重新提问，不是判断题，不能用『是』或『否』回答。"
INVALID_GUESS_FALLBACK = "请直接告诉我你猜测的人物名称。"


def _last_entry_is_user_prompt(entry: SessionEntry, prefix: str) -> bool:
    if not entry.messages:
        return False
    content = entry.messages[-1].get("content", "")
    return isinstance(content, str) and content.startswith(prefix)


def _result_invariants_hold(session: GameSession) -> bool:
    """终态不变量：win 必须有一次非空人名猜测；exhausted 必须用满 10 次猜测。"""
    if not session.is_terminal or session.result is None:
        return False
    rtype = session.result.type
    if rtype == ResultType.ABORTED:
        return True
    if rtype == ResultType.WIN:
        if session.guesses_used < 1 or not session.guess_history:
            return False
        last = session.guess_history[-1]
        return last.kind == "guess" and bool(last.guess and last.guess.strip())
    if rtype == ResultType.EXHAUSTED:
        return session.guesses_used == session.config.max_rounds
    return False


# ---------- 校验 ----------

def _validate_text(text: Optional[str]) -> str:
    if text is None:
        raise ApiError(ErrorCode.EMPTY_INPUT, details={"field": "text"})
    value = text.strip()
    if len(value) < settings.text_min_len:
        raise ApiError(ErrorCode.EMPTY_INPUT, details={"field": "text"})
    if len(value) > settings.text_max_len:
        raise ApiError(ErrorCode.INPUT_TOO_LONG, details={"field": "text"})
    return value


def _validate_scope(scope: Optional[str]) -> str:
    if scope is None:
        return settings.default_person_scope
    value = scope.strip()
    if not (settings.scope_min_len <= len(value) <= settings.scope_max_len):
        raise ApiError(
            ErrorCode.INVALID_PARAMETER,
            f"人物范围长度需为 {settings.scope_min_len}..{settings.scope_max_len} 字。",
            details={"field": "person_scope"},
        )
    return value


# ---------- 状态机异常映射 ----------

def _map_state_error(exc: Exception) -> ApiError:
    if isinstance(exc, QuestionBudgetExhausted):
        return ApiError(ErrorCode.QUESTION_BUDGET_EXHAUSTED)
    if isinstance(exc, GuessBudgetExhausted):
        return ApiError(ErrorCode.GUESS_BUDGET_EXHAUSTED)
    if isinstance(exc, GameNotActiveError):
        return ApiError(ErrorCode.GAME_NOT_ACTIVE)
    if isinstance(exc, InvalidPhaseError):
        return ApiError(ErrorCode.INVALID_PHASE, str(exc))
    return ApiError(ErrorCode.INTERNAL_ERROR)


def _require_entry(session_id: str) -> SessionEntry:
    entry = session_store.get(session_id)
    if entry is None:
        raise ApiError(ErrorCode.SESSION_NOT_FOUND)
    return entry


# ---------- DTO 转换（唯一出口） ----------

def to_dto(session: GameSession, host_message: Optional[str] = None) -> GameDTO:
    result_dto: Optional[ResultDTO] = None
    if session.status == GameStatus.RESULT and session.result is not None:
        title, message = _RESULT_META.get(
            session.result.type, ("游戏结束", "游戏结束。")
        )
        result_dto = ResultDTO(
            type=session.result.type.value,  # type: ignore[arg-type]
            title=title,
            message=message,
            person=PersonDTO(
                name=session.target_person,
                hint=session.person_hint,
                intro=session.person_intro,
            ),
        )

    qa = [
        QARecordDTO(
            seq=r.seq,
            kind=r.kind,  # type: ignore[arg-type]
            question=r.question,
            answer=ANSWER_TO_API.get(r.answer) if r.answer else None,
            round=r.round,
        )
        for r in session.qa_history
    ]
    guesses = [
        GuessRecordDTO(
            seq=r.seq,
            kind=r.kind,  # type: ignore[arg-type]
            guess=r.guess,
            is_correct=r.is_correct,
            round=r.round,
        )
        for r in session.guess_history
    ]

    last_answer = None
    if session.last_answer is not None:
        last_answer = LastAnswerDTO(
            question=session.last_answer.question,
            answer=ANSWER_TO_API[session.last_answer.answer],  # type: ignore[arg-type]
        )

    last_hint = None
    if session.last_guess_hint is not None:
        last_hint = GuessHintDTO(
            guess=session.last_guess_hint.guess,
            message=session.last_guess_hint.message,
        )

    return GameDTO(
        session_id=session.session_id,
        status=session.status.value,  # type: ignore[arg-type]
        phase=session.current_phase.value if session.current_phase else None,
        current_round=session.current_round,
        person_hint=session.person_hint or session.config.person_scope,
        max_rounds=session.config.max_rounds,
        questions_used=session.questions_used,
        questions_remaining=session.questions_remaining,
        guesses_used=session.guesses_used,
        guesses_remaining=session.guesses_remaining,
        qa_history=qa,
        guess_history=guesses,
        result=result_dto,
        last_answer=last_answer,
        last_guess_hint=last_hint,
        host_message=host_message,
        created_at=session.created_at.isoformat().replace("+00:00", "Z"),
        updated_at=session.updated_at.isoformat().replace("+00:00", "Z"),
    )


# ---------- LLM 调用 ----------

async def _run_llm(entry: SessionEntry, system_prompt: str) -> str:
    """在线程中跑阻塞式 agent_loop；LLM 异常归一为 502。"""
    try:
        host_text = await asyncio.to_thread(
            run_agent_loop,
            entry.session,
            entry.messages,
            system_prompt=system_prompt,
        )
    except UpstreamLLMError as e:
        raise ApiError(
            ErrorCode.UPSTREAM_LLM_ERROR,
            f"主持人服务暂时不可用：{e}"[:200],
        ) from e
    entry.host_message = host_text or None
    return host_text or ""


def _system_prompt_for(session: GameSession) -> str:
    return build_system_prompt(
        session.config.person_scope, session.config.max_rounds
    )


def _append_notice(entry: SessionEntry, text: str) -> None:
    """skip/retry/abandon 不走 LLM，仅注入系统通知保证上下文一致。"""
    entry.messages.append({"role": "user", "content": text})


# ---------- 动作 ----------

async def create_game(req: CreateGameRequest) -> GameDTO:
    scope = _validate_scope(req.person_scope)
    max_rounds = req.max_rounds or settings.default_max_rounds

    entry = session_store.create(max_rounds=max_rounds, person_scope=scope)
    session = entry.session
    # 开局注入最近人物排除区块；对局中的 ask/guess 不再携带（人物已选定）
    system_prompt = build_system_prompt(
        scope,
        max_rounds,
        exclusion_block=person_history.exclusion_block(scope),
    )

    entry.messages.append({
        "role": "user",
        "content": f"请开始游戏，人物范围：{scope}。共 {max_rounds} 轮，每轮先提问后猜测。",
    })

    host_text = await _run_llm(entry, system_prompt)

    # 校验 AI 确实调用了 start_game
    if session.status != GameStatus.PLAYING or not session.target_person:
        session_store.release(session.session_id)
        raise ApiError(ErrorCode.UPSTREAM_LLM_ERROR, "主持人未能完成开局，请重试。")

    return to_dto(session, host_message=host_text or None)


async def get_game(session_id: str) -> GameDTO:
    entry = _require_entry(session_id)
    return to_dto(entry.session, host_message=entry.host_message)


async def ask(session_id: str, text: Optional[str]) -> GameDTO:
    entry = _require_entry(session_id)
    value = _validate_text(text)
    session = entry.session

    async with entry.lock:
        if session.status != GameStatus.PLAYING:
            raise ApiError(ErrorCode.GAME_NOT_ACTIVE)
        if session.current_phase != Phase.QUESTION:
            raise ApiError(ErrorCode.INVALID_PHASE, "当前不是提问阶段。")
        if session.questions_remaining <= 0:
            raise ApiError(ErrorCode.QUESTION_BUDGET_EXHAUSTED)

        used_before = session.questions_used
        session.pending_question = value
        entry.messages.append({"role": "user", "content": f"玩家提问：{value}"})

        try:
            host_text = await _run_llm(entry, _system_prompt_for(session))
        except ApiError:
            # LLM 故障不产生脏状态/脏计数：撤回尚未被处理的用户消息
            session.pending_question = None
            if _last_entry_is_user_prompt(entry, "玩家提问："):
                entry.messages.pop()
            raise
        finally:
            session.pending_question = None

        # 提问动作只可能产生 answer_question 推进；若意外进入终态
        # （白名单下仅可能是 end_game(abort)），按放弃结算并释放会话
        if session.status == GameStatus.RESULT:
            dto = to_dto(session, host_message=host_text or None)
            session_store.release(session.session_id)
            return dto

        advanced = (
            session.status == GameStatus.PLAYING
            and session.current_phase == Phase.GUESS
            and session.questions_used == used_before + 1
        )
        if not advanced:
            # AI 未调用 answer_question：判定为非判断题，不计次
            raise ApiError(
                ErrorCode.NOT_YES_NO_QUESTION,
                host_text or NOT_YES_NO_FALLBACK,
            )

        return to_dto(session, host_message=host_text or None)


async def guess(session_id: str, text: Optional[str]) -> GameDTO:
    entry = _require_entry(session_id)
    value = _validate_text(text)
    session = entry.session

    async with entry.lock:
        if session.status != GameStatus.PLAYING:
            raise ApiError(ErrorCode.GAME_NOT_ACTIVE)
        if session.current_phase != Phase.GUESS:
            raise ApiError(ErrorCode.INVALID_PHASE, "当前不是猜测阶段，请先提问。")
        if session.guesses_remaining <= 0:
            raise ApiError(ErrorCode.GUESS_BUDGET_EXHAUSTED)

        # 第 3 层：猜测入口的确定性预检——明显是疑问句时不调 LLM、不计次
        # （规则单一事实源在 input_guard.py，CLI 共用同一规则）
        if looks_like_question(value):
            raise ApiError(ErrorCode.INVALID_GUESS, GUESS_INPUT_IS_QUESTION)

        used_before = session.guesses_used
        session.pending_guess = value
        entry.messages.append({"role": "user", "content": f"玩家猜测：{value}"})

        try:
            host_text = await _run_llm(entry, _system_prompt_for(session))
        except ApiError:
            session.pending_guess = None
            if _last_entry_is_user_prompt(entry, "玩家猜测："):
                entry.messages.pop()
            raise
        finally:
            session.pending_guess = None

        # 终局（win / exhausted / abort）或自动进入下一轮提问
        if session.status == GameStatus.RESULT:
            # 第 2 层：终态不变量断言（白名单正常时恒成立，属于防御性检查）
            if not _result_invariants_hold(session):
                session_store.release(session.session_id)
                raise ApiError(
                    ErrorCode.UPSTREAM_LLM_ERROR,
                    "终局状态异常（缺少有效猜测记录），本局已终止，请重新开局。",
                )
            dto = to_dto(session, host_message=host_text or None)
            session_store.release(session.session_id)
            return dto

        advanced = (
            session.status == GameStatus.PLAYING
            and session.current_phase == Phase.QUESTION
            and session.guesses_used == used_before + 1
        )
        if not advanced:
            # AI 未调用 judge_guess（要求澄清等），状态不变、次数不扣
            raise ApiError(
                ErrorCode.INVALID_GUESS,
                host_text or INVALID_GUESS_FALLBACK,
            )

        return to_dto(session, host_message=host_text or None)


async def skip(session_id: str, current_phase: Optional[str]) -> GameDTO:
    entry = _require_entry(session_id)
    session = entry.session

    async with entry.lock:
        if session.status != GameStatus.PLAYING:
            raise ApiError(ErrorCode.GAME_NOT_ACTIVE)
        if current_phase and current_phase != session.current_phase.value:
            raise ApiError(ErrorCode.PHASE_CONFLICT)

        entry.host_message = None

        if session.current_phase == Phase.QUESTION:
            try:
                session.record_skip_question()
            except (InvalidPhaseError, GameNotActiveError, QuestionBudgetExhausted) as e:
                raise _map_state_error(e) from e
            _append_notice(
                entry,
                f"[系统通知] 玩家跳过了本轮提问（提问机会 -1），直接进入 GUESS 阶段"
                f"（第 {session.current_round} 轮）。剩余提问 {session.questions_remaining} 次、"
                f"猜测 {session.guesses_remaining} 次。",
            )
            return to_dto(session, host_message=None)

        # guess 阶段
        try:
            outcome = session.record_skip_guess()
        except (InvalidPhaseError, GameNotActiveError, GuessBudgetExhausted) as e:
            raise _map_state_error(e) from e

        if outcome is ResultType.EXHAUSTED:
            _append_notice(
                entry,
                f"[系统通知] 玩家在第 {session.config.max_rounds} 轮跳过猜测，机会用尽，游戏结束。",
            )
            dto = to_dto(session, host_message=None)
            session_store.release(session.session_id)
            return dto

        _append_notice(
            entry,
            f"[系统通知] 玩家跳过了上一轮猜测（猜测机会 -1），进入第 {session.current_round} 轮"
            f" QUESTION 阶段。剩余提问 {session.questions_remaining} 次、"
            f"猜测 {session.guesses_remaining} 次。",
        )
        return to_dto(session, host_message=None)


async def retry(session_id: str) -> GameDTO:
    """'再试一下'兼容入口：回到当前轮提问阶段，不消耗次数、不递增轮次。"""
    entry = _require_entry(session_id)
    session = entry.session

    async with entry.lock:
        if session.status != GameStatus.PLAYING:
            raise ApiError(ErrorCode.GAME_NOT_ACTIVE)
        session.back_to_question()
        entry.host_message = None
        _append_notice(
            entry,
            f"[系统通知] 玩家请求回到提问阶段（不消耗次数），当前为第 {session.current_round} 轮 QUESTION。",
        )
        return to_dto(session, host_message=None)


async def abandon(session_id: str) -> GameDTO:
    entry = _require_entry(session_id)
    session = entry.session

    async with entry.lock:
        if session.status != GameStatus.PLAYING:
            raise ApiError(ErrorCode.GAME_NOT_ACTIVE)
        session.abort()
        entry.host_message = None
        _append_notice(entry, "[系统通知] 玩家主动放弃游戏（aborted），已揭晓答案。")
        dto = to_dto(session, host_message=None)
        session_store.release(session.session_id)
        return dto
