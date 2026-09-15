"""
hooks.py - s04 风格的扩展点

事件：
  UserPromptSubmit  : REPL 收到玩家输入后、写入 history 前
  PostToolUse       : 每个工具执行后
"""

from game_state import get_session, GameStatus, Phase, GameConfig



# 注册表：event -> [callable]
_HOOKS = {
    "UserPromptSubmit": [],
    "PostToolUse": [],
}


def register_hook(event: str, fn):
    if event not in _HOOKS:
        raise ValueError(f"未知事件：{event}")
    _HOOKS[event].append(fn)


def trigger_hooks(event: str, payload):
    """
    顺序执行某事件的所有 hook。任一 hook 可返回字符串，
    用作"短路信号"（如 UserPromptSubmit 检测到 quit 时返回 'abort'）。
    """
    results = []
    for fn in _HOOKS.get(event, []):
        r = fn(payload)
        if r is not None:
            results.append(r)
    return results


# ---------- 内置 hook ----------

_ABORT_KEYWORDS = {"q", "exit", "quit", "放弃", "中止", "结束"}


def on_user_prompt_submit(query: str):
    """
    预处理玩家输入：
    - 检测放弃意图 → 返回 'abort' 信号（由 REPL 处理）
    """
    text = query.strip().lower()
    if text in _ABORT_KEYWORDS:
        return "abort"
    return None


def on_post_tool_use(payload):
    """
    payload: {"tool": name, "result": str}
    目前主要用于日志/调试，无短路逻辑。
    """
    # 留作扩展点：例如 PostToolUse(answer_question) 时检查末轮失败
    # 但状态机本身已在 handler 内完成转移，此处保持空实现。
    return None

# def on_question_check(text: str, session: GameConfig):
#     """
#     检查玩家输入是否为问题：
#     - 是问题 → 返回 None
#     - 否 → 返回 'question_check_failed' 信号（由 REPL 处理）
#     """
#     if session.status == GameStatus.PLAYING and session.current_phase == Phase.GUESS:
#         if looks_like_question(text):
#             return None
#     return "question_check_failed"



# 默认注册
register_hook("UserPromptSubmit", on_user_prompt_submit)
register_hook("PostToolUse", on_post_tool_use)
# register_hook("QuestionCheck", on_question_check)
