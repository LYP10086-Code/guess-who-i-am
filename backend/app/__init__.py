"""backend 包初始化：保证 geuss_who_i_am 目录在 sys.path 上。

无论 uvicorn 从哪个工作目录启动，都能导入顶层模块 game_state / tools / prompts。
"""

import os
import sys

_GWI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../geuss_who_i_am
if _GWI_DIR not in sys.path:
    sys.path.insert(0, _GWI_DIR)
