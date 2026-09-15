# -*- coding: utf-8 -*-
"""输入确定性预检（CLI / Web 共用的单一事实源）。

仅包含高精度的启发式规则：命中即确定性拒绝，不调 LLM、不计次。
设计原则是"宁可漏判（交给 LLM），不可误判"。
"""

from __future__ import annotations

import re

# 猜测框输入了疑问句的高置信特征：问号 / 句末语气词 / 问事短语
_QUESTION_PATTERN = re.compile(
    r"[?？]|吗\s*$|呢\s*$|是不是|有没有|是否|会不会|能不能|可不可以|对不对|多少|哪里|哪儿|谁是|什么"
)

# 猜测阶段误输入问题时的统一提示（Web 422 message / CLI 本地提示共用）
GUESS_INPUT_IS_QUESTION = (
    "这里需要直接输入你猜测的人物姓名（如：杜甫），而不是一个问题；"
    "不想猜可跳过本次猜测。"
)


def looks_like_question(text: str) -> bool:
    """猜测入口的疑问句式预检（高精度，宁可漏判不误判）。"""
    return bool(_QUESTION_PATTERN.search(text or ""))
