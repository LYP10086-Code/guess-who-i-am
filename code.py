#!/usr/bin/env python3
"""
guess-who-i-am / code.py - 猜猜我是谁 CLI（v3 薄封装）

运行（在项目根目录下）：
    python code.py

依赖：
    pip install -r backend/requirements.txt
    .env 需配置 ANTHROPIC_API_KEY / MODEL_ID（可选 ANTHROPIC_BASE_URL）

设计：
    - Agent Loop 已抽取到 backend/app/llm/agent_runner.py，CLI/Web 共用
    - 5 个工具：start_game / answer_question / judge_guess / skip_guess / end_game
    - 阶段状态机（question → guess）由 game_state.py 强制
    - hooks: UserPromptSubmit 检测放弃意图
"""

import os
import sys

# 让 `python geuss_who_i_am/code.py` 也能导入同目录模块与 backend 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import readline  # noqa: F401  保留 s01 风格
except ImportError:
    pass

from dotenv import load_dotenv

load_dotenv(override=True)

from game_state import (  # noqa: E402
    init_session, get_session, GameStatus, Phase, ResultType, GameConfig,
)
import person_history  # noqa: E402
from input_guard import looks_like_question, GUESS_INPUT_IS_QUESTION  # noqa: E402
from prompts import build_system_prompt  # noqa: E402
from hooks import trigger_hooks  # noqa: E402
from backend.app.llm.agent_runner import run_agent_loop  # noqa: E402
from backend.app.llm.client import get_model  # noqa: E402


# ---------- 配置 ----------

def make_config() -> GameConfig:
    cfg = GameConfig()
    cfg.person_scope = os.getenv("GWI_PERSON_SCOPE", "中国历史人物")
    if os.getenv("GWI_MAX_ROUNDS"):
        try:
            cfg.max_rounds = int(os.getenv("GWI_MAX_ROUNDS"))
        except ValueError:
            pass
    cfg.model = get_model()
    return cfg


# ---------- 状态行 ----------

def render_status_line() -> str:
    s = get_session()
    if s.status == GameStatus.IDLE:
        return "[等待开局]"
    if s.status == GameStatus.RESULT:
        rtype = s.result.type.value if s.result else "result"
        return f"[游戏结束 - {rtype}]"
    phase_zh = "提问" if s.current_phase == Phase.QUESTION else "猜测"
    return (
        f"[第 {s.current_round}/{s.config.max_rounds} 轮 · {phase_zh}阶段 · "
        f"剩余提问 {s.questions_remaining} · 剩余猜测 {s.guesses_remaining}]"
    )


# ---------- 终局处理 ----------

def handle_abort() -> bool:
    """玩家放弃：优先本地状态机直接中止（不依赖 LLM）。"""
    s = get_session()
    if s.is_terminal:
        return True
    if s.status == GameStatus.PLAYING:
        s.abort()
    print(f"游戏中止。答案是 {s.target_person}。{s.person_intro}")
    return True


# ---------- 入口 ----------

def main():
    cfg = make_config()
    session = init_session(cfg)
    system_prompt = build_system_prompt(
        cfg.person_scope,
        cfg.max_rounds,
        exclusion_block=person_history.exclusion_block(cfg.person_scope),
    )

    print("=" * 56)
    print(" 猜猜我是谁 / Guess Who I Am")
    print("=" * 56)
    print(f" 模型: {cfg.model}    范围: {cfg.person_scope}    上限: {cfg.max_rounds} 轮")
    print(" 输入 quit / q / 放弃 / exit 可中止游戏。")
    print("=" * 56)
    print()

    messages: list = []
    while True:
        s = get_session()
        if s.is_terminal:
            rtype = s.result.type if s.result else ResultType.ABORTED
            if rtype == ResultType.WIN:
                print(f"\n恭喜猜对！答案就是 {s.target_person}。")
            elif rtype == ResultType.EXHAUSTED:
                print(f"\n次数用完，游戏结束。答案是 {s.target_person}。")
            else:
                print(f"\n游戏已中止。答案是 {s.target_person}。")
            print("再见！")
            break

        prompt_prefix = f"\001\033[36m\002{render_status_line()} >> \001\033[0m\002"
        try:
            query = input(prompt_prefix)
        except (EOFError, KeyboardInterrupt):
            print()
            handle_abort()
            break


        text = query.strip()
        if not text:
            continue

        # UserPromptSubmit hook（含放弃意图检测）
        signals = trigger_hooks("UserPromptSubmit", query)
        if "abort" in signals:
            handle_abort()
            break
        # # QuestionCheck hook（含问题校验）
        # signals = trigger_hooks("QuestionCheck", text, s)
        




        # 冗余校验（与 Web /guesses 同一规则，见 input_guard.py）：
        # 猜测阶段误输入疑问句 → 本地确定性拦截，不调 LLM、不计次
        if s.status == GameStatus.PLAYING and s.current_phase == Phase.GUESS:
            if looks_like_question(text):
                print(f"\033[33m{GUESS_INPUT_IS_QUESTION}\033[0m")
                print()
                continue

        # 将玩家原文写入会话，供工具 handler 记录真实问题/猜测
        if s.status == GameStatus.PLAYING and s.current_phase == Phase.QUESTION:
            session.pending_question = text
            content = f"玩家提问：{text}"
        elif s.status == GameStatus.PLAYING and s.current_phase == Phase.GUESS:
            session.pending_guess = text
            content = f"玩家猜测：{text}"
        else:
            content = text

        messages.append({"role": "user", "content": content})
        host_text = run_agent_loop(session, messages, system_prompt=system_prompt)
        if host_text:
            print(host_text)
        print()


if __name__ == "__main__":
    main()
