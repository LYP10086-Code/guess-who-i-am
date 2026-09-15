"""
tools.py - 工具 schema 与 handler（v3）

5 个工具：
  start_game / answer_question / judge_guess / skip_guess / end_game

- handler 通过 get_session() 取 contextvar（Web）或模块级单例（CLI）
- 玩家原文（提问/猜测）由 orchestrator/CLI 在调用 LLM 前写入 session.pending_*
- Web 端的 skip/retry/abandon 是纯本地动作，不经 LLM（见 services/orchestrator.py）
"""

import os

import person_history
from game_state import (
    get_session,
    AnswerType,
    GameStatus,
    Phase,
    ResultType,
    InvalidPhaseError,
    GameNotActiveError,
    QuestionBudgetExhausted,
    GuessBudgetExhausted,
)

# start_game 撞车时最多拒绝 N 次，第 N+1 次仍重复则放行（避免开局死循环）
def _max_start_attempts() -> int:
    try:
        return max(1, int(os.getenv("GWI_START_MAX_RETRY", "3")))
    except ValueError:
        return 3


# ---------- 工具 schema ----------

TOOLS = [
    {
        "name": "start_game",
        "description": (
            "开局：主持人选定一位人物并初始化游戏。仅在游戏未开始时调用一次。"
            "target_person 对玩家保密，绝不直接告知；person_hint 给玩家的范围提示；"
            "person_intro 在揭晓时附带的简介。"
            "必须同时回填 canonical_name（规范姓名）与 aliases（字/号/别名数组，无别名给空数组）；"
            "禁止选择系统提示中'本局禁止选择的人物'（含别名）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_person": {"type": "string", "description": "主持人选定的人物姓名（可与规范名一致）"},
                "canonical_name": {"type": "string", "description": "该人物的规范姓名（用于去重比对）"},
                "aliases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "字/号/尊称等别名，无别名给空数组 []",
                },
                "person_hint": {"type": "string", "description": "给玩家的范围提示，如'中国历史人物'"},
                "person_intro": {"type": "string", "description": "揭晓时附带的简短人物介绍"},
            },
            "required": ["target_person", "person_hint", "person_intro"],
        },
    },
    {
        "name": "answer_question",
        "description": (
            "回答玩家的判断性问题。仅在 QUESTION 阶段调用。"
            "answer 只能是'是'或'不是'。调用后进入本轮 GUESS 阶段（消耗本轮提问机会）。"
            "若玩家的问题不是可用'是/不是'回答的判断题，不要调用本工具，"
            "直接用文本礼貌要求玩家换一个判断题。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "answer": {"type": "string", "enum": ["是", "不是"], "description": "二元答复"},
                "reasoning": {"type": "string", "description": "可选，主持人内部判定依据，不展示给玩家"},
            },
            "required": ["answer"],
        },
    },
    {
        "name": "judge_guess",
        "description": (
            "判定玩家本轮的猜测。仅在 GUESS 阶段调用，每轮最多 1 次（消耗本轮猜测机会）。"
            "由你判断玩家猜测与 target_person 是否语义匹配（含别名/字号/尊称）。"
            "is_correct=true 时游戏直接胜利；错误且未到第 10 轮时自动进入下一轮提问；"
            "错误且为第 10 轮时游戏结束并揭晓答案。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "is_correct": {"type": "boolean", "description": "猜测是否正确"},
                "guess_text": {"type": "string", "description": "玩家猜测文本（原样回填）"},
                "feedback": {"type": "string", "description": "可选，给玩家的反馈"},
            },
            "required": ["is_correct", "guess_text"],
        },
    },
    {
        "name": "skip_guess",
        "description": (
            "玩家放弃本次猜测机会。仅在 GUESS 阶段调用（消耗本轮猜测机会）。"
            "调用后进入下一轮提问；若已是第 10 轮则游戏结束（exhausted）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "可选，跳过原因"},
            },
            "required": [],
        },
    },
    {
        "name": "end_game",
        "description": (
            "仅用于玩家主动放弃（abort）时中止本局并揭晓答案。"
            "**不得**用于判定胜负：玩家猜对由 judge_guess(is_correct=true) 自动完成，"
            "10 轮用尽由 judge_guess/skip_guess 在末轮自动完成；"
            "调用 end_game(win/lose) 会被系统拒绝。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "outcome": {"type": "string", "enum": ["abort"]},
                "reveal_message": {"type": "string", "description": "可选，自定义揭晓文本"},
            },
            "required": ["outcome"],
        },
    },
]


# ---------- 阶段 → 允许调用的工具（白名单，agent_runner 派发前强校验） ----------

def _phase_whitelist(session) -> set[str]:
    if session.status == GameStatus.IDLE:
        return {"start_game"}
    if session.status == GameStatus.RESULT:
        return set()
    # PLAYING：end_game(abort) 在提问/猜测阶段均允许
    if session.current_phase == Phase.QUESTION:
        return {"answer_question", "end_game"}
    if session.current_phase == Phase.GUESS:
        return {"judge_guess", "skip_guess", "end_game"}
    return set()


def is_tool_allowed(session, tool_name: str) -> bool:
    """越权工具调用在 handler 执行前拦截，保证状态零修改。"""
    return tool_name in _phase_whitelist(session)


def tool_denied_message(session, tool_name: str) -> str:
    phase = session.current_phase.value if session.current_phase else session.status.value
    allowed = "、".join(sorted(_phase_whitelist(session))) or "（游戏已结束，无可用工具）"
    return _err(
        f"当前阶段（{phase}）不允许调用工具 {tool_name}，本阶段仅允许：{allowed}。"
        "请改用允许的工具，或仅输出文本引导玩家。"
    )


# ---------- handler 实现 ----------

def _err(msg: str) -> str:
    return f"[ERROR] {msg}"


def handle_start_game(
    target_person: str,
    person_hint: str,
    person_intro: str,
    canonical_name: str = "",
    aliases: list[str] | None = None,
) -> str:
    s = get_session()

    canonical = (canonical_name or target_person or "").strip()
    alias_list = [a.strip() for a in (aliases or []) if isinstance(a, str) and a.strip()]
    # 展示名也纳入别名集合，防止 canonical/展示名不一致时漏判
    display = (target_person or "").strip()
    if display and display != canonical:
        alias_list.append(display)

    # 去重校验（规范名 + 别名交叉比对，按 scope 过滤）
    if person_history.is_recent(canonical, alias_list, scope=s.config.person_scope):
        s.start_attempts += 1
        if s.start_attempts <= _max_start_attempts():
            recent = "、".join(person_history.recent_names(s.config.person_scope))
            return _err(
                f"人物「{canonical}」（含其别名）最近已使用过。最近已用人物：{recent}。"
                f"请重新选择一位不在上述名单中的{person_hint or s.config.person_scope}"
                "（注意字、号、尊称也视为同一人），并再次调用 start_game，"
                "同时回填新人物的 canonical_name 与 aliases。"
            )
        # 连续撞车超限：放行，避免开局死循环（仍会登记并随 FIFO 淘汰）

    try:
        s.start(target_person=target_person, person_hint=person_hint, person_intro=person_intro)
    except Exception as e:  # 状态机错误统一回给 LLM
        return _err(str(e))

    # 成功开局后登记（CLI / Web 共用同一 JSON 注册表）；落盘失败不阻塞游戏
    try:
        person_history.record(canonical, alias_list, scope=s.config.person_scope)
    except OSError as e:
        import sys
        print(f"[WARN] 最近人物注册表写入失败（不影响本局）：{e}", file=sys.stderr)

    max_r = s.config.max_rounds
    return (
        f"游戏已初始化。目标人物已选定（保密）。"
        f"范围提示：{person_hint}。共 {max_r} 轮，每轮 1 次提问 + 1 次猜测，跳过也消耗对应机会。"
        f"请向玩家宣布游戏开始并邀请其提问。"
    )


def handle_answer_question(answer: str, reasoning: str = "") -> str:
    s = get_session()
    try:
        ans = AnswerType(answer)
    except ValueError:
        return _err(f"answer 必须是 '是' 或 '不是'，收到：{answer}")

    # 真实提问原文由调用方写入 pending_question
    question = (s.pending_question or "").strip() or "(玩家本轮提问)"
    try:
        s.record_answer(ans, question=question)
    except (InvalidPhaseError, GameNotActiveError) as e:
        return _err(str(e))
    except QuestionBudgetExhausted:
        return _err("提问次数已用尽，请调用 end_game(lose) 揭晓答案")

    return (
        f"{ans.value}。剩余提问次数：{s.questions_remaining}。"
        f"当前为 GUESS 阶段（第 {s.current_round} 轮），玩家本轮可猜测 1 次，"
        f"或跳过本次猜测（跳过同样消耗猜测机会）。"
    )


def handle_judge_guess(is_correct: bool, guess_text: str, feedback: str = "") -> str:
    s = get_session()
    # 真实猜测原文优先取 pending_guess
    real_guess = (s.pending_guess or "").strip() or guess_text
    try:
        outcome = s.record_guess(is_correct=bool(is_correct), guess_text=real_guess)
    except (InvalidPhaseError, GameNotActiveError) as e:
        return _err(str(e))
    except GuessBudgetExhausted:
        return _err("猜测次数已用尽，请调用 end_game(lose)")

    if outcome is ResultType.WIN:
        return (
            f"猜测正确：{real_guess} = {s.target_person}。游戏胜利。"
            f"请用一句主持人话术恭喜玩家（系统已揭晓人物信息，无需再调用其他工具）。"
        )
    if outcome is ResultType.EXHAUSTED:
        return (
            f"猜测错误，且第 {s.config.max_rounds} 轮已用尽，未猜中。游戏结束。"
            f"请用主持人话术告知玩家次数用完（系统将揭晓答案，无需再调用其他工具）。"
        )
    # 猜错但有余量：已自动进入下一轮提问
    return (
        f"猜测错误，并不是{real_guess}。剩余猜测次数：{s.guesses_remaining}。"
        f"当前为 QUESTION 阶段（第 {s.current_round} 轮），请简短告知玩家猜错并邀请继续提问。"
    )


def handle_skip_guess(reason: str = "") -> str:
    s = get_session()
    try:
        outcome = s.record_skip_guess()
    except (InvalidPhaseError, GameNotActiveError) as e:
        return _err(str(e))
    except GuessBudgetExhausted:
        return _err("猜测次数已用尽，请调用 end_game(lose)")

    if outcome is ResultType.EXHAUSTED:
        return (
            f"已跳过本次猜测，且第 {s.config.max_rounds} 轮已用尽，未猜中。游戏结束。"
            f"请用主持人话术告知玩家次数用完（系统将揭晓答案）。"
        )
    return (
        f"已跳过本次猜测（消耗 1 次猜测机会）。剩余猜测次数：{s.guesses_remaining}。"
        f"当前为 QUESTION 阶段（第 {s.current_round} 轮），请玩家继续提问。"
    )


def handle_end_game(outcome: str, reveal_message: str = "") -> str:
    s = get_session()

    # 胜负只能由 judge_guess（末轮 skip_guess）产生，end_game 只允许 abort
    if outcome != "abort":
        return _err(
            f"end_game 不支持 outcome={outcome}：胜负判定只能调用 judge_guess"
            "（is_correct=true/false），10 轮用尽由系统自动判定；"
            "玩家主动放弃时才调用 end_game(outcome=abort)。"
        )

    # 已终态：幂等返回揭晓信息
    if s.is_terminal:
        return reveal_message or (
            f"游戏已结束（{s.result.type.value if s.result else 'result'}）。"
            f"答案：{s.target_person}。{s.person_intro}"
        )

    try:
        s.to_result(ResultType.ABORTED)
    except GameNotActiveError as e:
        return _err(str(e))

    if reveal_message:
        return reveal_message
    return f"游戏中止。答案是 {s.target_person}。{s.person_intro or ''}"


# ---------- dispatch map ----------

TOOL_HANDLERS = {
    "start_game": handle_start_game,
    "answer_question": handle_answer_question,
    "judge_guess": handle_judge_guess,
    "skip_guess": handle_skip_guess,
    "end_game": handle_end_game,
}
