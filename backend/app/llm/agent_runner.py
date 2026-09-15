"""Agent Loop：从 code.py 抽取的核心循环，CLI / Web 共用。

run_agent_loop(session, messages, system_prompt=...)：
- 将 session 绑定到 contextvar，工具 handler 通过 get_session() 取得；
- 复用 learn-claude-code 范式：messages.create → tool_use → TOOL_HANDLERS → tool_result；
- 无工具调用即结束，返回最后一条 assistant 文本（host_message）。
"""

from __future__ import annotations

from typing import Optional

from game_state import GameSession, set_current_session, reset_current_session
from hooks import trigger_hooks
from tools import (
    TOOLS,
    TOOL_HANDLERS,
    is_tool_allowed,
    tool_denied_message,
)

from .client import get_client, get_model


class AgentLoopError(RuntimeError):
    pass


class UpstreamLLMError(AgentLoopError):
    """LLM 超时/限流/返回异常；调用方保证状态未落账。"""

# loop_count = 0
def run_agent_loop(
    session: GameSession,
    messages: list,
    *,
    system_prompt: str,
    max_iterations: int = 8,
    max_tokens: int = 2000,
) -> Optional[str]:
    # global loop_count
    # loop_count += 1
    token = set_current_session(session)
    try:
        client = get_client()
        last_text: Optional[str] = None

        for _ in range(max_iterations):
            try:
                response = client.messages.create(
                    model=get_model(),
                    system=system_prompt,
                    messages=messages,
                    tools=TOOLS,
                    max_tokens=max_tokens,
                )
            except Exception as e:  # anthropic SDK 各类异常归一
                raise UpstreamLLMError(str(e)) from e

            messages.append({"role": "assistant", "content": response.content})
            # print(f"@@@@@@@loop {loop_count}########\nmessages: {messages}\n")

            text_blocks = [
                block.text for block in response.content
                if getattr(block, "type", None) == "text"
            ]
            if text_blocks:
                last_text = "\n".join(text_blocks)

            tool_calls = [
                block for block in response.content
                if getattr(block, "type", None) == "tool_use"
            ]
            if not tool_calls:
                return last_text

            results = []
            for block in tool_calls:
                # 阶段白名单：越权工具不执行 handler，状态零修改
                if not is_tool_allowed(session, block.name):
                    output = tool_denied_message(session, block.name)
                else:
                    handler = TOOL_HANDLERS.get(block.name)
                    if handler is None:
                        output = f"[ERROR] 未知工具：{block.name}"
                    else:
                        try:
                            output = handler(**block.input)
                        except TypeError as e:
                            output = f"[ERROR] 参数错误：{e}"
                        except Exception as e:
                            output = f"[ERROR] {e}"
                trigger_hooks("PostToolUse", {"tool": block.name, "result": output})
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
            # print(f"@@@@@@@loop {loop_count}########\nresults: {results}\n")
            messages.append({"role": "user", "content": results})

        return last_text
    finally:
        reset_current_session(token)
