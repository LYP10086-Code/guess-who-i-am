"""
game_state.py - 猜猜我是谁：状态机与数据模型（v3）

设计要点（见 design.md §4.2）：
- 固定 10 轮，每轮 = 1 次提问 + 1 次猜测，顺序固定「先提问、后猜测」
- 跳过消耗对应机会：跳过提问消耗本轮提问；跳过猜测消耗本轮猜测
- 猜错且仍有余量 → 直接回下一轮提问（last_guess_hint 携带提示）
- 状态三态：idle / playing / result（win|exhausted|aborted）
- 会话获取：优先 contextvar（Web 每请求一会话），回退模块级单例（CLI）
"""

from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ---------- 枚举 ----------

class GameStatus(str, Enum):
    IDLE = "idle"
    PLAYING = "playing"
    RESULT = "result"


class Phase(str, Enum):
    QUESTION = "question"   # 等待玩家提问
    GUESS = "guess"         # 等待玩家猜测或跳过


class AnswerType(str, Enum):
    YES = "是"
    NO = "不是"


class ResultType(str, Enum):
    WIN = "win"
    EXHAUSTED = "exhausted"
    ABORTED = "aborted"


# ---------- 领域错误（orchestrator 边界映射为错误码） ----------

class GameStateError(RuntimeError):
    """状态机错误基类。"""


class InvalidPhaseError(GameStateError):
    """动作与当前阶段不符。"""


class GameNotActiveError(GameStateError):
    """游戏不在进行中。"""


class QuestionBudgetExhausted(GameStateError):
    pass


class GuessBudgetExhausted(GameStateError):
    pass


# ---------- 配置 ----------

@dataclass
class GameConfig:
    max_rounds: int = 10
    person_scope: str = "中国历史人物"
    model: str = ""  # 由入口从 .env 注入

    @property
    def max_questions(self) -> int:
        return self.max_rounds

    @property
    def max_guesses(self) -> int:
        return self.max_rounds


# ---------- 记录 ----------

@dataclass
class QARecord:
    seq: int                       # 全局序号（与 questions_used 一致）
    kind: str                      # "ask" | "skip"
    question: Optional[str]        # kind=skip 时为 None
    answer: Optional[AnswerType]   # kind=skip 时为 None
    round: int = 0


@dataclass
class GuessRecord:
    seq: int                       # 全局序号（与 guesses_used 一致）
    kind: str                      # "guess" | "skip"
    guess: Optional[str]
    is_correct: Optional[bool]
    round: int = 0


@dataclass
class SessionResult:
    type: ResultType


@dataclass
class LastAnswer:
    question: str
    answer: AnswerType


@dataclass
class GuessHint:
    guess: str
    message: str


# ---------- 会话 ----------

@dataclass
class GameSession:
    config: GameConfig = field(default_factory=GameConfig)
    session_id: str = ""

    # 由 start_game 写入
    target_person: str = ""
    person_hint: str = ""
    person_intro: str = ""

    # 状态
    status: GameStatus = GameStatus.IDLE
    current_round: int = 0                 # 0 未开局；开局后从 1 开始
    current_phase: Optional[Phase] = None
    result: Optional[SessionResult] = None

    # 计数
    questions_used: int = 0
    guesses_used: int = 0

    # 历史
    qa_history: list[QARecord] = field(default_factory=list)
    guess_history: list[GuessRecord] = field(default_factory=list)

    # 展示辅助
    last_answer: Optional[LastAnswer] = None
    last_guess_hint: Optional[GuessHint] = None

    # 瞬态：orchestrator 在调用 LLM 前写入玩家原文，工具 handler 读取
    pending_question: Optional[str] = None
    pending_guess: Optional[str] = None

    # 瞬态：开局阶段 start_game 因人物撞车被拒绝的次数（超限后放行，防死循环）
    start_attempts: int = 0

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ---------- 派生字段 ----------

    @property
    def questions_remaining(self) -> int:
        return self.config.max_rounds - self.questions_used

    @property
    def guesses_remaining(self) -> int:
        return self.config.max_rounds - self.guesses_used

    @property
    def is_terminal(self) -> bool:
        return self.status == GameStatus.RESULT

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    # ---------- 内部守卫 ----------

    def _require_playing(self) -> None:
        if self.status != GameStatus.PLAYING:
            raise GameNotActiveError("游戏当前不在进行中")

    def _require_phase(self, phase: Phase) -> None:
        self._require_playing()
        if self.current_phase != phase:
            expect = "提问" if phase == Phase.QUESTION else "猜测"
            raise InvalidPhaseError(f"当前阶段不是{expect}阶段")

    # ---------- 状态转移 ----------

    def start(
        self,
        target_person: str,
        person_hint: str,
        person_intro: str,
        session_id: str = "",
    ) -> None:
        if self.status != GameStatus.IDLE:
            raise GameStateError("游戏已开局，不可重复 start")
        self.target_person = target_person
        self.person_hint = person_hint or self.config.person_scope
        self.person_intro = person_intro
        if session_id:
            self.session_id = session_id
        elif not self.session_id:
            self.session_id = str(uuid.uuid4())
        self.status = GameStatus.PLAYING
        self.current_round = 1
        self.current_phase = Phase.QUESTION
        self.result = None
        self.touch()

    def record_answer(self, answer: AnswerType, question: str) -> None:
        """答题成功：question → guess（同轮），questions_used +1。"""
        self._require_phase(Phase.QUESTION)
        if self.questions_remaining <= 0:
            raise QuestionBudgetExhausted("提问次数已用尽")
        self.questions_used += 1
        self.qa_history.append(
            QARecord(
                seq=self.questions_used,
                kind="ask",
                question=question,
                answer=answer,
                round=self.current_round,
            )
        )
        self.last_answer = LastAnswer(question=question, answer=answer)
        self.last_guess_hint = None
        self.current_phase = Phase.GUESS
        self.touch()

    def record_skip_question(self) -> None:
        """跳过提问：question → guess（同轮），消耗本轮提问机会。"""
        self._require_phase(Phase.QUESTION)
        if self.questions_remaining <= 0:
            raise QuestionBudgetExhausted("提问次数已用尽")
        self.questions_used += 1
        self.qa_history.append(
            QARecord(
                seq=self.questions_used,
                kind="skip",
                question=None,
                answer=None,
                round=self.current_round,
            )
        )
        self.last_guess_hint = None
        self.current_phase = Phase.GUESS
        self.touch()

    def record_guess(self, is_correct: bool, guess_text: str) -> Optional[ResultType]:
        """
        猜测：guess → win / 下一轮 question / exhausted。
        guesses_used 一律 +1。返回 ResultType(win|exhausted)；猜错进下一轮时返回 None。
        """
        self._require_phase(Phase.GUESS)
        if self.guesses_remaining <= 0:
            raise GuessBudgetExhausted("猜测次数已用尽")

        self.guesses_used += 1
        self.guess_history.append(
            GuessRecord(
                seq=self.guesses_used,
                kind="guess",
                guess=guess_text,
                is_correct=is_correct,
                round=self.current_round,
            )
        )

        if is_correct:
            self._to_result(ResultType.WIN)
            return ResultType.WIN

        if self.current_round >= self.config.max_rounds:
            self._to_result(ResultType.EXHAUSTED)
            return ResultType.EXHAUSTED

        # 猜错但仍有余量：直接回下一轮提问
        self.last_guess_hint = GuessHint(
            guess=guess_text,
            message=f"回答错误，并不是{guess_text}",
        )
        self.current_round += 1
        self.current_phase = Phase.QUESTION
        self.touch()
        return None  # 猜错但有余量：已进入下一轮提问

    def record_skip_guess(self) -> Optional[ResultType]:
        """跳过猜测：guess → 下一轮 question（消耗本轮猜测）/ exhausted（末轮）。"""
        self._require_phase(Phase.GUESS)
        if self.guesses_remaining <= 0:
            raise GuessBudgetExhausted("猜测次数已用尽")

        self.guesses_used += 1
        self.guess_history.append(
            GuessRecord(
                seq=self.guesses_used,
                kind="skip",
                guess=None,
                is_correct=None,
                round=self.current_round,
            )
        )

        if self.current_round >= self.config.max_rounds:
            self._to_result(ResultType.EXHAUSTED)
            return ResultType.EXHAUSTED

        self.current_round += 1
        self.current_phase = Phase.QUESTION
        self.touch()
        return None

    def back_to_question(self) -> None:
        """retry 兼容入口：回到当前轮提问阶段，不消耗次数、不递增轮次。"""
        self._require_playing()
        self.current_phase = Phase.QUESTION
        self.touch()

    def abort(self) -> None:
        """主动放弃 → result/aborted。"""
        self._require_playing()
        self._to_result(ResultType.ABORTED)

    def to_result(self, result_type: ResultType) -> None:
        if self.status != GameStatus.PLAYING:
            raise GameNotActiveError("游戏当前不在进行中")
        self._to_result(result_type)

    def _to_result(self, result_type: ResultType) -> None:
        self.status = GameStatus.RESULT
        self.current_phase = None
        self.result = SessionResult(type=result_type)
        self.touch()


# ---------- contextvar + 模块级单例（CLI/Web 共用） ----------

_CURRENT_SESSION: contextvars.ContextVar[Optional[GameSession]] = contextvars.ContextVar(
    "gwi_current_session", default=None
)

_SESSION: Optional[GameSession] = None


def set_current_session(session: GameSession) -> contextvars.Token:
    return _CURRENT_SESSION.set(session)


def reset_current_session(token: contextvars.Token) -> None:
    _CURRENT_SESSION.reset(token)


def init_session(config: Optional[GameConfig] = None) -> GameSession:
    """CLI 入口：初始化模块级单例。"""
    global _SESSION
    _SESSION = GameSession(config=config or GameConfig())
    _SESSION.session_id = str(uuid.uuid4())
    return _SESSION


def get_session() -> GameSession:
    """优先取 contextvar 中的当前请求会话（Web），否则取模块级单例（CLI）。"""
    sess = _CURRENT_SESSION.get()
    if sess is not None:
        return sess
    if _SESSION is not None:
        return _SESSION
    raise RuntimeError("GameSession 尚未初始化，请先调用 init_session() 或 set_current_session()")


def get_config() -> GameConfig:
    return get_session().config
