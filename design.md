# 猜猜我是谁 — 系统架构设计说明书（Web 版 v3）

> 本文档是"猜猜我是谁"项目的**总体架构与接口实现规范**，覆盖前端（Vue3 + TS）、
> API 路由层（FastAPI）、后端（复用 learn-claude-code 的 Agent Harness）三层。
>
- 业务来源：[readme.md](./readme.md)
- 本文档取代 v1（CLI 配对轮次）、v2（双计数器独立可跳过）中与本次规则冲突的部分；CLI（[code.py](./code.py)）保留可运行。
- 本文档只做设计，不含代码。

---

## 〇、规则演进与本版变更

| 项 | v1（CLI 版） | v2（Web 旧版） | v3（本版） |
|---|---|---|---|
| 次数模型 | 10 个配对轮次 | **提问/猜测双计数器独立**，各 10 次 | **固定 10 轮**，每轮 1 次提问 + 1 次猜测（先提问后猜测） |
| 提问可否跳过 | 不可 | 可跳过，**不消耗次数** | **可跳过，消耗本轮提问机会**（直接进入本轮猜测） |
| 猜测可否跳过 | 可跳过，回下一轮 | 可跳过，**不消耗次数** | **可跳过，消耗本轮猜测机会**（进入下一轮提问，或第 10 轮后结束） |
| 猜错后的体验 | 直接继续 | 进入 result/wrong 结果页，点"再试一下"回提问 | **直接回到提问阶段**，页面提示"回答错误/并不是"；无需独立结果页 |
| 次数耗尽 | 第 10 轮未中即失败 | 双计数器任一耗尽 | 第 10 轮猜测（或跳过）后未中 → exhausted |
| 会话存储 | 进程内单例 | 内存 + 30min 空闲 TTL | 内存 + 30min 空闲 TTL；**仅存当前局，终态后自动释放** |
| skip/retry/abandon | 走 LLM | 不走 LLM | **不走 LLM**（本地状态流转 + 注入系统通知） |

### 最终业务规则（v3 定稿）

1. **固定 10 轮**：每一轮内含 **1 次提问机会** 与 **1 次猜测机会**，顺序固定为「先提问、后猜测」。
   - 等价于：`max_questions = max_guesses = max_rounds = 10`。
2. **跳过消耗对应机会**：
   - **跳过提问** → 消耗本轮提问机会，直接进入本轮的猜测阶段；
   - **跳过猜测** → 消耗本轮猜测机会，进入下一轮的提问阶段；若当前已是第 10 轮，则游戏结束（exhausted）。
3. **提问阶段**：提交一个「是/不是」判断题 → AI 回答后进入本轮猜测阶段；或跳过提问（消耗提问机会）→ 进入本轮猜测阶段。
4. **非判断题**：AI 判定无法用「是/不是」回答时，**拒绝回答且不计次**，停留在提问阶段，页面提示「请重新提问」或「不是判断题，不能用『是』或『否』回答」。
5. **猜测阶段**：提交一次人物猜测 → AI 语义判定（兼容别名/字号）：
   - **正确** → 结果状态（win），揭晓人物信息，展示恭喜界面，提供「**再玩一次**」按钮重新开始；
   - **错误且仍有剩余轮次** → **直接回到提问阶段**（下一轮），页面提示「回答错误」或「并不是 {guess}」；不进入独立结果页；
   - **错误且已是第 10 轮** → 结果状态（exhausted），展示「次数用完，游戏结束」并揭晓答案。
6. **「再试一下」语义**：固定回到提问阶段。由于猜错后系统已自动回到提问阶段，本版不再设独立的 wrong 结果页与 retry 强依赖；retry 接口作为兼容/安全入口保留，行为恒为回到提问阶段。
7. 玩家可在游玩中主动放弃（abandon）→ 结果状态（aborted），揭晓答案。
8. 终态（win / exhausted / aborted）只能「再玩一次」（创建新游戏）。
9. **会话存储**：仅内存保存当前局；`skip` / `retry` / `abandon` 不调用 LLM；终态后会话自动从内存释放（结果数据已随最后一次响应返回前端）。

---

## 一、系统总体架构

```
┌───────────────────────────────────────────────────────────────┐
│  浏览器  frontend/   Vue 3 + TypeScript + Vite + Pinia + Axios│
│                                                               │
│   StartScreen ──开始──▶ GameScreen(question → guess)          │
│                                │ 猜对/耗尽/放弃                │
│                                ▼                               │
│                            ResultScreen(win/exhausted/aborted)│
│                                                               │
│   猜错(有余量) ──自动──▶ 回 GameScreen(question) + 提示条       │
└──────────────────────────────┬────────────────────────────────┘
                               │ HTTP/JSON  /api/v1/*
                               │ 开发期 Vite proxy :5173 → :8000
┌──────────────────────────────▼────────────────────────────────┐
│  API 路由层  backend/app/  FastAPI + Pydantic                 │
│                                                               │
│  routes/games.py   端点（创建/查询/提问/猜测/跳过/重试/放弃）   │
│  schemas/          请求/响应 DTO、错误模型                      │
│  errors.py         错误码枚举 → 统一错误信封 + HTTP 状态码      │
└──────────────────────────────┬────────────────────────────────┘
                               │ 函数调用（同进程）
┌──────────────────────────────▼────────────────────────────────┐
│  服务层  services/                                            │
│                                                               │
│  orchestrator.py   动作编排：DTO↔会话、驱动 LLM、提取工具结果   │
│  session_store.py  session_id → {GameSession, messages[],Lock}│
│                    内存存储 + 空闲 TTL(30min) + 终态自动释放    │
└──────────────────────────────┬────────────────────────────────┘
                               │ 复用（learn-claude-code 既有模块）
┌──────────────────────────────▼────────────────────────────────┐
│  Agent Harness  (learn-claude-code 范式)                      │
│                                                               │
│  game_state.py   GameSession 状态机（10 轮配对 + skip 消耗）   │
│  tools.py        start_game/answer_question/judge_guess/      │
│                  skip_guess/end_game  ← TOOL_HANDLERS 派发     │
│  prompts.py      主持人 SYSTEM（v3 规则：10 轮、跳过消耗）      │
│  hooks.py        UserPromptSubmit / PostToolUse               │
│  llm/agent_runner.py  agent_loop（从 code.py 抽取，可注入会话） │
└───────────────────────────────────────────────────────────────┘
```

**分层原则**

- 前端只认 HTTP 契约，不知道后端是 LLM；
- FastAPI 路由层只做校验/序列化/错误映射，不含游戏规则；
- 规则唯一事实源在 `game_state.py` 状态机；LLM 只负责"选人物、答题、判猜"，**状态流转由 Python 强制**；
- 复用现有 Agent Loop（`client.messages.create → tool_use → TOOL_HANDLERS → tool_result`），不重写智能部分。

---

## 二、技术栈与运行形态

| 层 | 技术 | 版本/说明 |
|---|---|---|
| 前端 | Vue 3 + `<script setup>` + TypeScript | Vue ^3.4 / TS ^5.4 |
| 构建 | Vite ^5 | dev port 5173，proxy `/api` → `http://localhost:8000` |
| 状态 | Pinia ^2 | 单 store：`game` |
| 请求 | Axios ^1 | **baseURL 固定为相对路径 `/api/v1`**（全项目唯一策略，不写绝对地址） |
| 路由 | 不引入 vue-router | 三态由 store 驱动组件切换，无 URL 页面 |
| 后端 | FastAPI ^0.115 + Uvicorn | `uvicorn backend.app.main:app --reload --port 8000` |
| 校验 | Pydantic v2 | 与 TypeScript 类型一一对应 |
| LLM | anthropic SDK（现有） | 配置沿用根目录 `.env`（`ANTHROPIC_API_KEY` / `MODEL_ID` / 可选 `ANTHROPIC_BASE_URL`） |
| Python | ^3.10 | 现有环境 Python 3.14 亦可 |

开发期：前端 5173、后端 8000，CORS 仅放行 `http://localhost:5173`。
生产形态（可选）：FastAPI `StaticFiles` 托管前端构建产物，单端口同源访问。

---

## 三、目录结构（目标态）

```
geuss_who_i_am/
  readme.md                     # 业务说明（不改）
  design.md                     # 本文档
  code.py                       # CLI 入口（v3 薄封装，复用 agent_runner）
  game_state.py                 # 领域模型+状态机（v3 扩展，CLI/Web 共用）
  person_history.py             # 最近人物注册表（JSON 落盘 FIFO，去重数据源，CLI/Web 共用）
  prompts.py                    # SYSTEM prompt（v3 规则 + 最近人物排除区块）
  tools.py                      # 工具 schema+handler（改造：会话从 contextvar 解析、start_game 去重）
  hooks.py                      # 扩展点（保留）
  data/                         # 运行时数据（git 忽略）
    recent_persons.json         # 最近 10 位已用人物（首次开局自动创建）
  start.ps1 / start.cmd         # Windows 一键拉起前后端脚本
  backend/
    requirements.txt            # fastapi / uvicorn[standard] / pydantic / anthropic / python-dotenv
    app/
      __init__.py
      main.py                   # FastAPI 实例、CORS、异常处理、lifespan
      config.py                 # 环境配置、CORS、TTL、默认轮次
      errors.py                 # ErrorCode 枚举 + ApiError + exception handlers
      api/
        __init__.py
        routes/
          __init__.py
          games.py              # 端点
      schemas/
        __init__.py
        game.py                 # GameDTO / 请求体 / ResultDTO ...
        error.py                # ErrorEnvelope
      services/
        __init__.py
        session_store.py        # 内存会话仓库 + TTL + per-session Lock + 终态释放
        orchestrator.py         # create/ask/guess/skip/retry/abandon 编排
      llm/
        __init__.py
        client.py               # Anthropic 客户端与 .env 加载
        agent_runner.py         # run_agent_loop(session, messages) 抽取自 code.py
  frontend/
    package.json
    vite.config.ts              # proxy /api → http://localhost:8000
    tsconfig.json
    index.html
    src/
      main.ts
      App.vue                   # 按 store.uiState 切换三大屏
      env.d.ts
      types/
        api.ts                  # 与后端契约逐字段一致的 TS 类型（唯一事实源）
      api/
        client.ts               # axios 实例 + 响应/错误拦截器
        games.ts                # 接口函数
      stores/
        game.ts                 # Pinia store（dto / loading / error / 动作）
      components/
        StartScreen.vue         # 状态①
        GameScreen.vue          # 状态②容器（计数/历史/放弃按钮/猜错提示条）
        QuestionPanel.vue       #   提问阶段面板（含"跳过提问"）
        GuessPanel.vue          #   回答阶段面板（含"跳过猜测"）
        ResultScreen.vue        # 状态③（win/exhausted/aborted）
        HostBubble.vue          # AI 主持人发言气泡（可选）
        HistoryList.vue         # 问答/猜测历史
      styles/
        tokens.css              # 颜色/圆角/间距 token
```

---

## 四、数据模型

### 4.1 枚举（API 契约一律使用英文小写串，中文展示由前端负责）

| 枚举 | 取值 | 含义 |
|---|---|---|
| `GameStatus` | `idle` / `playing` / `result` | 对应前端三态；result 下由 `result.type` 细分 |
| `Phase` | `question` / `guess` | 仅 `playing` 时有值 |
| `AnswerValue` | `yes` / `no` | AI 对判断题的二元答复 |
| `ResultType` | `win` / `exhausted` / `aborted` | 终态结果类型（**移除 wrong**，猜错有余量直接回提问） |
| `GuessKind` | `guess` / `skip` | 猜测历史条目类型 |
| `QuestionKind` | `ask` / `skip` | 提问历史条目类型（区分提问与跳过提问） |

> 领域层内部沿用的中文 `是/不是`（[game_state.py](./game_state.py) `AnswerType`）在 orchestrator 边界映射为 `yes/no`。

### 4.2 领域模型（game_state.py，v3 扩展）

```
GameConfig
  max_rounds: int = 10          # 固定 10 轮；校验范围 1..20
  person_scope: str = "中国历史人物"
  model: str                     # 来自 .env

GameSession
  session_id: str                # uuid4，由 store 分配
  target_person / person_hint / person_intro: str
  status: GameStatus             # idle|playing|result
  current_phase: Phase | None    # playing 时 question|guess
  current_round: int             # 1..max_rounds
  questions_used / guesses_used: int
  qa_history: list[QARecord]
  guess_history: list[GuessRecord]
  result: SessionResult | None   # 进入 result 时写入
  last_answer: {question:str, answer:AnswerValue} | None
  last_guess_hint: {guess:str, message:str} | None   # 猜错后回提问时的提示
  created_at / updated_at: datetime

QARecord    { seq:int, kind:QuestionKind, question:str|None, answer:AnswerValue|None }
GuessRecord { seq:int, kind:GuessKind, guess:str|None, is_correct:bool|None }
SessionResult { type:ResultType }   # win/exhausted/aborted 均不可重试

派生量
  max_questions = max_rounds
  max_guesses   = max_rounds
  questions_remaining = max_rounds - questions_used
  guesses_remaining   = max_rounds - guesses_used
  is_terminal         = status==result
```

**状态转移（唯一事实源，所有 handler 必须遵守）**

```
        POST /games（start_game 工具）
 idle ───────────────────────────────▶ playing / question (round=1)

       ┌───────────────────────────────────────────────────────┐
       │              playing                                  │
       │                                                       │
       │  question 阶段（round = r）:                          │
       │    提问成功 ──────────────▶ guess (round=r)           │
       │       questions_used += 1                             │
       │    跳过提问 ──────────────▶ guess (round=r)           │
       │       questions_used += 1（消耗本轮提问机会）          │
       │    非判断题 ──────────────▶ 停留 question，不计次      │
       │                                                       │
       │  guess 阶段（round = r）:                             │
       │    猜测正确 ──────────────▶ result/win                │
       │       guesses_used += 1                               │
       │    猜测错误 & r<max ─────▶ question (round=r+1)        │
       │       guesses_used += 1，写 last_guess_hint           │
       │    猜测错误 & r==max ────▶ result/exhausted           │
       │       guesses_used += 1，揭晓 person                  │
       │    跳过猜测 & r<max ─────▶ question (round=r+1)        │
       │       guesses_used += 1（消耗本轮猜测机会）            │
       │    跳过猜测 & r==max ────▶ result/exhausted           │
       │       guesses_used += 1                               │
       │                                                       │
       │    abandon ───────────────▶ result/aborted            │
       └───────────────────────────────────────────────────────┘

 result/{win,exhausted,aborted} ── POST /games ──▶ 新会话
```

**阶段守卫（硬约束）**

| 当前 | 允许动作 | 拒绝时错误码 |
|---|---|---|
| `idle` | 仅创建新游戏 | `GAME_NOT_ACTIVE` |
| `playing/question` | 提问、跳过提问、放弃 | 提问类外动作 → `INVALID_PHASE` |
| `playing/guess` | 猜测、跳过猜测、放弃 | 同上 |
| `result/*` | 仅创建新游戏/查询 | 其他 → `GAME_NOT_ACTIVE` |

> v3 不再有 `result/wrong`，故无需 retry 守卫；retry 接口仅作为兼容入口，对 playing 状态恒等回到当前轮提问阶段（不消耗次数），对 result 返回 `GAME_NOT_ACTIVE`。

**预算守卫**

- `playing/question` 时若 `questions_remaining==0` 仍提问/跳过提问 → `QUESTION_BUDGET_EXHAUSTED`；
  （正常流程下 `questions_remaining==0` 意味着 round==max_rounds 且已提问，应处于 guess 阶段，此守卫为兜底。）
- `playing/guess` 时若 `guesses_remaining==0` → `GUESS_BUDGET_EXHAUSTED`（同上兜底）。

### 4.3 API DTO（schemas/game.py，TypeScript 类型与其逐字段同名同形）

**GameDTO（所有动作接口的统一响应体——单一事实源，前端整体替换 store）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | string(uuid) | 会话 ID |
| `status` | enum | `idle`/`playing`/`result` |
| `phase` | string\|null | `question`/`guess`/`null` |
| `current_round` | int | 当前轮次 1..max_rounds |
| `person_hint` | string | 开局给玩家的范围提示，如"中国历史人物" |
| `max_rounds` | int | 固定 10 |
| `questions_used` | int | 已使用提问次数（含跳过提问） |
| `questions_remaining` | int | 剩余提问次数 |
| `guesses_used` | int | 已使用猜测次数（含跳过猜测） |
| `guesses_remaining` | int | 剩余猜测次数 |
| `qa_history` | QARecordDTO[] | 按 seq 升序 |
| `guess_history` | GuessRecordDTO[] | 按 seq 升序 |
| `result` | ResultDTO\|null | 仅 status=result 非空 |
| `last_answer` | `{question:string, answer:'yes'\|'no'}` \| null | 最近一次答复 |
| `last_guess_hint` | `{guess:string, message:string}` \| null | 猜错后回提问时的提示（如"回答错误，并不是 X"） |
| `host_message` | string\|null | 本轮 AI 主持人文本（可能为空） |
| `created_at` | string(date-time) | ISO8601 UTC |
| `updated_at` | string(date-time) | ISO8601 UTC |

> 前端展示文案示例：`你有 {max_rounds} 次猜测机会，当前已使用 {guesses_used} 次，剩余 {guesses_remaining} 次`；提问同理。

**QARecordDTO**：`seq: int`、`kind: "ask"|"skip"`、`question: string|null`、`answer: "yes"|"no"|null`
**GuessRecordDTO**：`seq: int`、`kind: "guess"|"skip"`、`guess: string|null`、`is_correct: boolean|null`
**ResultDTO**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | enum | `win`/`exhausted`/`aborted` |
| `title` | string | 展示标题（如"恭喜答对"） |
| `message` | string | 展示文案 |
| `person` | PersonDTO\|null | **win/exhausted/aborted 均非空**（揭晓答案） |

**PersonDTO**：`name: string`、`hint: string`、`intro: string`

**请求体**

| 接口 | 体 |
|---|---|
| POST /games | `CreateGameRequest` |
| POST /questions | `AskRequest` |
| POST /guesses | `GuessRequest` |
| POST /skip | `SkipRequest` |
| POST /retry | 无（空对象 `{}`） |
| POST /abandon | 无 |

```
CreateGameRequest {
  person_scope?:    string  // 1..30 字，默认"中国历史人物"
  max_rounds?:      int     // 1..20，默认 10（同时作用于提问与猜测上限）
}
AskRequest   { text: string }   // strip 后长度 1..200
GuessRequest { text: string }   // strip 后长度 1..200
SkipRequest  { current_phase?: "question"|"guess" }  // 可选乐观守卫
```

> 移除 `max_questions` / `max_guesses` 独立字段，统一由 `max_rounds` 决定。

### 4.4 错误模型（schemas/error.py，错误信封）

所有非 2xx 响应**统一形态**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `error.code` | string | 大写下划线错误码（程序判定用） |
| `error.message` | string | 中文人类可读信息（可直接展示） |
| `error.details` | object | 可选，字段级细节（如 `{"field":"text"}`） |
| `request_id` | string | 本次请求 ID（日志关联） |

---

## 五、API 接口实现规范

### 5.1 强制要求（前后端共同遵守）

1. **基础路径**：所有接口以 `/api/v1` 为前缀；路径中 `session_id` 为 uuid4 字符串。
2. **编码**：请求/响应一律 `application/json; charset=utf-8`，时间一律 ISO8601 UTC。
3. **成功响应体 = 完整 GameDTO**（创建接口返回 201，其余 200）。前端拿到后**整体替换**本地快照，禁止基于本地计数自行推算。
4. **错误响应体 = 错误信封**，HTTP 状态码语义化（见错误码表），前端不得仅靠 HTTP 码判断业务分支，必须读 `error.code`。
5. **无状态 HTTP**：会话由 `session_id` 标识；服务端串行处理同一会话动作（per-session lock），不保证并发请求顺序时，冲突返回 `PHASE_CONFLICT`。
6. **幂等性**：GET 安全幂等；POST 动作均**非幂等**（会推进状态/消耗次数）。`skip.current_phase` 为可选乐观守卫，与服务端当前阶段不一致时返回 `PHASE_CONFLICT`（不产生任何状态变更）。
7. **字段命名**：JSON 一律 snake_case；TS interface 直接使用 snake_case 字段名，**不做改名映射层**（避免契约漂移）。
8. **人物保密**：`result.person` 只在 `win`/`exhausted`/`aborted` 出现；任何 `playing` 响应中禁止携带 `target_person` 信息（`host_message` 亦受 prompt 约束不得泄露）。
9. **跨域**：开发期仅允许 `http://localhost:5173`；允许方法 GET/POST/OPTIONS，允许头 `Content-Type`。
10. **鉴权**：v1 本地单机无鉴权（无用户体系）；预留 `X-API-Key` 头，默认不校验。
11. **限流（建议实现，非强制）**：单 session 30 次动作/分钟，超限 429。
12. **LLM 故障不产生脏状态**：调用 LLM 的动作（创建/提问/猜测）只有在状态机成功提交后才落账；LLM 超时/报错 → 502，状态不变、次数不扣。
13. **跳过/重试/放弃不走 LLM**：`skip` / `retry` / `abandon` 为纯本地状态流转，仅向 `messages[]` 注入系统通知消息，保证下次 LLM 调用认知一致。
14. **终态自动释放**：会话进入 `result` 终态后，session_store 在响应返回后异步移除该会话（结果数据已随响应返回）；30 分钟空闲 TTL 为兜底。

### 5.2 接口总览

| # | 方法 | 路径 | 作用 | 成功码 | 需要阶段 |
|---|---|---|---|---|---|
| 1 | POST | `/api/v1/games` | 创建并开始一局（AI 选人物） | 201 | 任意 |
| 2 | GET | `/api/v1/games/{session_id}` | 查询当前完整状态 | 200 | 任意 |
| 3 | POST | `/api/v1/games/{session_id}/questions` | 提交判断题 | 200 | playing/question |
| 4 | POST | `/api/v1/games/{session_id}/guesses` | 提交人物猜测 | 200 | playing/guess |
| 5 | POST | `/api/v1/games/{session_id}/skip` | 跳过当前阶段（消耗对应机会） | 200 | playing |
| 6 | POST | `/api/v1/games/{session_id}/retry` | 回到提问阶段（兼容入口，不消耗次数） | 200 | playing |
| 7 | POST | `/api/v1/games/{session_id}/abandon` | 放弃本局并揭晓 | 200 | playing |

### 5.3 逐接口规范

#### 1) POST `/api/v1/games` — 创建/开始游戏

- 请求体 `CreateGameRequest`（全字段可选）
- 编排：建会话（status=idle, current_round=1, questions_used=0, guesses_used=0）→ 注入首条用户消息"请开始游戏，人物范围：{scope}"→ 运行 agent_loop → AI 必须调用 `start_game` → 置 `playing/question`。
- 校验：`person_scope` strip 后 1..30；`max_rounds` 1..20。
- 成功 **201**：GameDTO（`phase="question"`，`current_round=1`，计数 0，`result=null`，`host_message`=AI 开场白）。
- 失败：422 `INVALID_PARAMETER`；502 `UPSTREAM_LLM_ERROR`。

#### 2) GET `/api/v1/games/{session_id}` — 查询状态

- 无请求体；成功 **200** GameDTO；会话不存在/已释放 404 `SESSION_NOT_FOUND`。
- 用途：页面刷新后恢复三态；不推进任何状态。

#### 3) POST `/api/v1/games/{session_id}/questions` — 提问

- 请求体 `AskRequest { text }`
- 校验规则：
  - `text` 必填，strip 后长度 1..200，否则 422 `EMPTY_INPUT` / `INPUT_TOO_LONG`（`details.field="text"`）；
  - 阶段必须为 `playing/question`，否则 409 `INVALID_PHASE`；
  - `questions_remaining==0` → 409 `QUESTION_BUDGET_EXHAUSTED`（不消耗次数）。
- 编排：追加用户消息 `玩家提问：{text}` → agent_loop：
  - AI 调用 `answer_question(yes/no)` → 状态机记账 `questions_used += 1`、`question→guess`，返回 **200** GameDTO，`last_answer.answer` 为 `yes/no`；
  - AI 未调用工具、仅返回文本（判定为非判断题/无法回答）→ **422 `NOT_YES_NO_QUESTION`**，`message` 取 AI 文本或固定文案「请重新提问，不是判断题，不能用『是』或『否』回答」，**状态不变、次数不扣**，前端停留提问面板并展示原因；
  - AI 误调其他工具（工具层已返回 [ERROR]）→ 编排层归一为 409 `INVALID_PHASE` 或重试一次后 502。
- 其他错误：404 / 502 `UPSTREAM_LLM_ERROR`。

#### 4) POST `/api/v1/games/{session_id}/guesses` — 猜测

- 请求体 `GuessRequest { text }`，文本校验同提问（`EMPTY_INPUT` / `INPUT_TOO_LONG`）。
- 阶段必须 `playing/guess`，否则 409 `INVALID_PHASE`；`guesses_remaining==0` → 409 `GUESS_BUDGET_EXHAUSTED`。
- 编排：追加 `玩家猜测：{text}` → agent_loop → AI 调用 `judge_guess(is_correct, guess_text)`，状态机：
  - 正确 → `guesses_used += 1`，`status=result, result.type=win`，`result.person=PersonDTO`；
  - 错误且 `current_round < max_rounds` → `guesses_used += 1`，`current_round += 1`，`phase=question`，写入 `last_guess_hint={guess: text, message: "回答错误，并不是 X"}`（X 为玩家猜测文本），**status 仍为 playing**，返回 **200** GameDTO；
  - 错误且 `current_round == max_rounds` → `guesses_used += 1`，`status=result, result.type=exhausted`，`result.person=PersonDTO`。
- 成功 **200** GameDTO（前端按 `status` 渲染：playing→QuestionPanel 并展示 `last_guess_hint`；result→ResultScreen）。
- 其余：404 / 422 / 502。

#### 5) POST `/api/v1/games/{session_id}/skip` — 跳过当前阶段

- 请求体 `SkipRequest { current_phase? }`。
- 行为（**纯本地状态流转，不调用 LLM，消耗对应机会**）：
  - 当前 `question` → `questions_used += 1`，置 `guess`（同一轮）；
  - 当前 `guess` → `guesses_used += 1`，然后：
    - 若 `current_round < max_rounds` → `current_round += 1`，置 `question`；
    - 若 `current_round == max_rounds` → `status=result, result.type=exhausted`，揭晓 person。
- `current_phase` 传入但与服务端不符 → 409 `PHASE_CONFLICT`，无副作用。
- 非 playing → 409 `GAME_NOT_ACTIVE`。
- 成功 **200** GameDTO，`host_message=null`（跳过不产生 AI 台词），`last_guess_hint=null`。
- 上下文一致性：服务端向该会话 `messages[]` 追加一条系统说明消息（`[系统通知] 玩家跳过了本阶段…`），保证下次 AI 调用时认知一致。

#### 6) POST `/api/v1/games/{session_id}/retry` — 回到提问阶段（兼容入口）

- 仅 `playing` 可用（result 终态调用 → 409 `GAME_NOT_ACTIVE`）。
- 行为：本地置回 `playing/question`（**不消耗次数、不递增轮次**），向 `messages[]` 追加系统通知。
- 由于 v3 猜错有余量时已自动回到提问阶段，本接口主要用于前端显式「再试一下」或异常恢复；正常流程可不调用。
- 成功 **200** GameDTO（`phase="question"`）。

#### 7) POST `/api/v1/games/{session_id}/abandon` — 放弃

- 仅 `playing` 可用（result 终态调用 → 409 `GAME_NOT_ACTIVE`）。
- 行为：本地置 `result/aborted`，`result.person` 揭晓；不调用 LLM。
- 成功 **200** GameDTO。

### 5.4 错误码总表

| HTTP | code | 触发场景 | 前端处理 |
|---|---|---|---|
| 404 | `SESSION_NOT_FOUND` | session_id 不存在/已过期/已释放 | 提示后回到未开始态 |
| 409 | `INVALID_PHASE` | 动作与当前阶段不符（如 question 阶段提交猜测） | 刷新状态，切换面板 |
| 409 | `PHASE_CONFLICT` | skip 的 current_phase 乐观守卫不一致 | 静默 GET 同步后重渲染 |
| 409 | `QUESTION_BUDGET_EXHAUSTED` | 提问次数为 0 仍提问/跳过提问 | 禁用提问，引导直接猜测 |
| 409 | `GUESS_BUDGET_EXHAUSTED` | 猜测次数为 0 仍猜测/跳过猜测 | 禁用猜测 |
| 409 | `GAME_NOT_ACTIVE` | 对终态/非本局执行动作 | 刷新状态 |
| 422 | `EMPTY_INPUT` | text strip 后为空 | 输入框红字"内容不能为空" |
| 422 | `INPUT_TOO_LONG` | text > 200 字 | 红字"最多 200 字" |
| 422 | `INVALID_PARAMETER` | 其他参数校验失败（含 details） | 按字段展示 |
| 422 | `NOT_YES_NO_QUESTION` | AI 判定不是"是/不是"问题，不计次 | 面板内提示「请重新提问，不是判断题…」，留在提问阶段 |
| 429 | `RATE_LIMITED` | 超出单会话动作频率 | 按钮置灰 2 秒后重试 |
| 502 | `UPSTREAM_LLM_ERROR` | LLM 超时/限流/返回异常；状态未落账 | Toast"主持人暂时开小差，请重试" |
| 500 | `INTERNAL_ERROR` | 未预期异常 | 通用错误提示 |

### 5.5 请求/响应示例

提问成功（200）：
```json
{
  "session_id": "b1e7...uuid",
  "status": "playing",
  "phase": "guess",
  "current_round": 1,
  "person_hint": "中国历史人物",
  "max_rounds": 10,
  "questions_used": 1, "questions_remaining": 9,
  "guesses_used": 0, "guesses_remaining": 10,
  "qa_history": [{"seq": 1, "kind": "ask", "question": "是男性吗？", "answer": "yes"}],
  "guess_history": [],
  "result": null,
  "last_answer": {"question": "是男性吗？", "answer": "yes"},
  "last_guess_hint": null,
  "host_message": "是。",
  "created_at": "2026-09-13T02:00:00Z",
  "updated_at": "2026-09-13T02:00:03Z"
}
```

猜错但有余量（200，status=playing，自动回提问）：
```json
{
  "status": "playing", "phase": "question",
  "current_round": 2,
  "questions_remaining": 9, "guesses_remaining": 9,
  "result": null,
  "last_guess_hint": {"guess": "诸葛亮", "message": "回答错误，并不是诸葛亮"},
  "host_message": null,
  "...": "..."
}
```

第 10 轮猜错（200，status=result/exhausted）：
```json
{
  "status": "result", "phase": null,
  "current_round": 10,
  "guesses_used": 10, "guesses_remaining": 0,
  "result": {
    "type": "exhausted",
    "title": "次数用完",
    "message": "次数用完，游戏结束。",
    "person": {"name": "曹操", "hint": "...", "intro": "..."}
  },
  "last_guess_hint": null,
  "...": "..."
}
```

错误（422 非判断题）：
```json
{
  "error": {
    "code": "NOT_YES_NO_QUESTION",
    "message": "请重新提问，不是判断题，不能用『是』或『否』回答。",
    "details": {}
  },
  "request_id": "req-9f31..."
}
```

---

## 六、API 路由层与服务层设计（FastAPI）

### 6.1 main.py 职责

- 创建 `FastAPI(title="Guess Who I Am API", version="3.0.0")`；
- CORS 中间件：origins=`http://localhost:5173`，allow credentials=False；
- 注册 games router（prefix `/api/v1`）；
- 注册全局异常处理器：`ApiError → 错误信封`、`RequestValidationError → INVALID_PARAMETER`、
  未捕获异常 → `INTERNAL_ERROR`；响应中注入 `request_id`（uuid4，挂到 contextvar 供日志关联）；
- lifespan：初始化 session_store 清理线程（惰性 TTL + 终态释放）、初始化 LLM client。

### 6.2 routes/games.py

- 只做：路径/路径参数/Pydantic 入参解析 → 调 orchestrator → 返回 DTO；
- 显式 `response_model=GameDTO`、`status_code=201/200`；
- 不写规则、不直接 import tools handler。

### 6.3 services/orchestrator.py（动作编排，核心）

| 函数 | 逻辑要点 |
|---|---|
| `create_game(req)` | 生成 uuid；建 GameSession（round=1，计数 0）+ 独立 `messages=[]`；绑定 contextvar 会话；注入开局用户消息；运行 agent_loop；校验 AI 确实调用 `start_game`；写 playing/question；返回 DTO |
| `ask(sid, text)` | 加 per-session 锁 → 阶段守卫 → 运行 agent_loop → 根据"状态是否 question→guess 且计数+1"判定成功；未推进则把 AI 文本包成 `NOT_YES_NO_QUESTION` |
| `guess(sid, text)` | 守卫 → agent_loop → 依据 `current_round` 与 `is_correct` 映射 win / playing(question, round+1, last_guess_hint) / exhausted |
| `skip(sid, guard)` | 本地流转（见 §5.3-5），**消耗对应计数**，追加系统通知消息，无 LLM 调用 |
| `retry(sid)` | playing 态置回 question，不消耗次数不进轮；追加系统通知 |
| `abandon(sid)` | 本地置 aborted，填 person |
| `to_dto(session)` | 领域模型→GameDTO 的唯一转换函数（yes/no 映射、person 可见性控制、host_message 提取、last_guess_hint 透传） |

**LLM 调用模板消息**：提问/猜测时以玩家原文构造 user 消息（不经过 AI 自由文本路由，防止绕过工具）；
AI 返回的最终 text block 提取为 `host_message`；tool_result 中的 `[ERROR]` 不直接透传给前端，
由编排层归一到错误码。

### 6.4 services/session_store.py

- `dict[session_id -> SessionEntry]`，`SessionEntry = {session, messages, lock, last_active}`；
- `asyncio.Lock`（每会话一把）串行化动作；
- 空闲 TTL 30 分钟惰性清理（每次 GET/动作刷新 `last_active`）；
- **终态自动释放**：orchestrator 在动作使会话进入 `result`（win/exhausted/aborted）并成功返回响应后，调用 `session_store.release(sid)` 移除该会话；结果数据已在响应中，前端不再依赖该 session；
- v1 仅单进程内存；横向扩展预留接口（`get/save/delete/release`），未来可换 Redis。

### 6.5 对现有 harness 代码的改造点（实现阶段执行，本文件不写代码）

1. `game_state.py`：
   - `GameStatus` 扩展 `idle/playing/result`；`Phase` 保留 `question/guess`；
   - 新增 `current_round`、`max_rounds`；`max_questions/max_guesses` 派生为 `max_rounds`；
   - `record_answer`：`questions_used += 1`，`question→guess`；
   - `record_skip_question`：`questions_used += 1`，`question→guess`（同轮）；
   - `record_guess`：`guesses_used += 1`，按 round 决定 win / `round+1, question` / exhausted；
   - `record_skip_guess`：`guesses_used += 1`，按 round 决定 `round+1, question` / exhausted；
   - 新增 `to_result(type)`、`back_to_question()`（retry 用，不计数不进轮）；
   - 保存真实 `question`/`guess` 文本（由 orchestrator 透传）。
2. `tools.py`：handler 不再读模块级单例，改为从 `contextvars.ContextVar` 取"当前请求会话"；
   保留 `init_session/get_session` 供 CLI（code.py）以默认 context 运行，做到 CLI/Web 共用。
3. `prompts.py`：SYSTEM 更新为 v3 规则：固定 10 轮、每轮先提问后猜测、跳过消耗对应机会、猜错有余量自动回提问、非判断题拒答。
4. `llm/agent_runner.py`：把 [code.py](./code.py) 的 `agent_loop` 抽出为 `run_agent_loop(session, messages)`，
   工具派发仍用 `TOOL_HANDLERS`；CLI 改为薄封装调用它。
5. `code.py`（CLI）：保留可运行；行为差异（v1 配对轮次 vs v3）后续可单独对齐，不阻塞 Web。
6. 开局去重（人物不连续重复，详见 §6.6）：新增 `person_history.py`；`start_game` 增加 `canonical_name/aliases` 入参与 handler 端撞车拒绝；`prompts.build_system_prompt` 增加 `exclusion_block` 形参；`GameSession` 增加瞬态 `start_attempts`。

### 6.6 开局人物去重机制（最近 10 局，第 1+2 层方案）

**问题**：开局 prompt 完全相同 + 模型对名人的头部偏好，会导致连续多局选中同一人物；prompt cache 本身不决定生成结果，随机数种子无效（且 Anthropic Messages API 无 seed 参数）。

**方案 = 进程级 JSON 注册表（第 1 层）+ 服务端强校验重选（第 2 层）：**

1. `person_history.py`（CLI/Web 共用的进程级模块，独立于 session 生命周期）：
   - 落盘 `geuss_who_i_am/data/recent_persons.json`，FIFO 保留最近 **10** 位（`GWI_RECENT_PERSONS` 可调），重启不丢；
   - 每条记录 `{canonical, aliases[], scope, ts}`，按 `person_scope` 隔离；
   - 线程锁 + 临时文件 `os.replace` 原子写；文件损坏自动备份为 `*.corrupt-时间戳.json` 并重置；
   - 比对以"规范名 ∪ 别名"集合交叉命中，防止"苏轼 vs 苏东坡/子瞻"绕过。
2. 开局注入：`create_game`（以及 CLI 启动）调用 `person_history.exclusion_block(scope)` 生成结构化排除区块，
   经 `build_system_prompt(..., exclusion_block=)` 注入 SYSTEM；区块每局不同，天然破坏前缀缓存（无需随机数）；
   对局中的 ask/guess 不携带该区块（人物已选定）。
3. 服务端强校验：`start_game` 必须回填 `canonical_name` 与 `aliases`；handler 命中最近名单时返回
   `[ERROR] 该人物最近已使用，请重选…`——复用既有 agent_loop 的 tool_result 回灌循环，模型自动再次调用 start_game，
   无需额外编排；会话保持 `idle`、次数不扣。
4. 防死循环：`session.start_attempts` 计数，撞车拒绝超过上限（默认 3，`GWI_START_MAX_RETRY`）后放行并照常登记。
5. 仅在 `start()` 成功后才 `record()`；落盘失败仅 stderr 告警，不阻塞游戏。

**未采纳**：① 开局随机数（API 无 seed，软扰动不可靠，不解决头部偏好）；② 内置候选人物池 + Python 抽取（第 3 层，100% 不重复但需维护人物库，留待后续选人质量问题时再做）。

### 6.7 错位输入与越权工具的三层防护

**问题（corner case）**：① QUESTION 阶段玩家直接发来人名（如"杜甫"），模型若越权调 `end_game(win)` 会产生"0 次猜测的脏胜利终局"；② GUESS 阶段玩家发来问题（如"他是唐朝人吗？"），模型若误调 `judge_guess(is_correct=true)` 则没用任何人名就获胜。

**防护：**

1. **第 1 层：阶段 → 工具白名单（`tools.is_tool_allowed`，agent_runner 派发前强校验）**
   - `idle`：仅 `start_game`；`QUESTION`：仅 `answer_question`、`end_game`；`GUESS`：仅 `judge_guess`、`skip_guess`、`end_game`；`RESULT`：无。
   - 越权调用**不执行 handler、状态零修改**，直接回灌 `[ERROR] 当前阶段不允许…` 让模型改用合法工具或输出文本。
   - `end_game` 收紧为**仅支持 `outcome=abort`**（schema enum 同步）：win 只能由 `judge_guess(is_correct=true)` 产生，exhausted 由末轮 `judge_guess/skip_guess` 自动产生；收到 win/lose 返回 `[ERROR]`。
2. **第 2 层：orchestrator 终态/不变量检查**
   - ask() 循环后若进入终态（白名单下仅可能是模型识别到"我不玩了"触发 end_game(abort)）：正常返回 aborted DTO 并释放会话，不再误报 NOT_YES_NO_QUESTION。
   - guess() 终态分支增加不变量断言：`win ⇒ guesses_used≥1 且最后一条 GuessRecord 为非空 guess`；`exhausted ⇒ guesses_used==max_rounds`；`aborted` 恒合法。不满足则释放会话并返回 502。
   - 修复失败回滚时 `messages[-1]` content 为 list 时 `.startswith` 崩溃的隐患（`_last_entry_is_user_prompt` 做类型守卫）。
3. **第 3 层：猜测入口确定性预检（不调 LLM、不计次）**
   - 规则单一事实源在根模块 `input_guard.py`（`looks_like_question()` + 统一提示文案），CLI 与 Web 共用，禁止各自拷贝正则。
   - `/guesses` 在状态守卫后、写消息/调 LLM 前预检：`?？`、句末 `吗/呢`、`是不是/有没有/是否/会不会/能不能/可不可以/对不对/多少/哪里/谁是/什么` 命中 → 直接 `422 INVALID_GUESS`。
   - CLI（`code.py` 主循环，abort hook 之后、写 pending_guess 之前）执行同一预检：命中则黄色打印提示并 `continue`，不调 LLM、不写消息、不计次。
   - `/questions` **不做**反向硬拦截（"他生活在唐代"这类无标记陈述句也是合法判断题，误伤率高）；错位由模型文本引导 + 前端既有"跳过提问"按钮解决。
   - 残留风险：猜测框输入无疑问标记的非人名（如"唐朝""丞相"）无法确定性识别，需第 3 层候选人物库（规范名比对）才能根治。

---

## 七、前端设计（Vue3 + TypeScript）

### 7.1 三态状态机（与后端枚举严格一致）

```
uiState = dto.status ∈ {idle, playing, result}

idle ── start() 成功 ─▶ playing(question, round=1)

playing:
  question 面板：
    ask() 成功            → playing(guess, round=r)
    ask() NOT_YES_NO_QUESTION → 停留 question，面板内提示（状态不切换、不计次）
    skip('question')      → playing(guess, round=r)，questions_used+1
  guess 面板：
    guess() 正确          → result.win
    guess() 错误 & r<max  → playing(question, round=r+1)，展示 last_guess_hint
    guess() 错误 & r==max → result.exhausted
    skip('guess') & r<max → playing(question, round=r+1)，guesses_used+1
    skip('guess') & r==max→ result.exhausted
    abandon()             → result.aborted

result:
  win / exhausted / aborted：[再玩一次] → start() 新会话 → playing
```

页面**不自行维护轮次/剩余次数**，一律读 DTO 的 `current_round / questions_used / questions_remaining / guesses_used / guesses_remaining / phase / status`。

### 7.2 页面与组件

| 组件 | 对应状态 | 内容与交互 |
|---|---|---|
| `StartScreen.vue` | ①idle | 标题"猜猜我是谁"、副标题（共 10 轮，每轮 1 次提问+1 次猜测，可跳过但消耗机会）、"开始游戏"按钮 → `store.start()`；加载中按钮 loading |
| `GameScreen.vue` | ②playing 容器 | 顶部：人物范围提示、**当前轮次/总轮次**、**提问计数**（你有 10 次提问机会，已使用 X 次，剩余 Y 次）、**猜测计数**（你有 10 次猜测机会，已使用 X 次，剩余 Y 次）、"放弃游戏"按钮（二次确认）；中部按 `phase` 切换 QuestionPanel/GuessPanel；猜错提示条（`last_guess_hint` 非空时黄色条展示「回答错误，并不是 X」）；底部 HistoryList |
| `QuestionPanel.vue` | playing/question | 输入框（maxlength=200，字数统计）+ "提问"按钮 + "跳过提问，直接去猜"次按钮（消耗本次提问机会）；`questions_remaining==0` 时提问与跳过按钮均禁用；错误 `NOT_YES_NO_QUESTION` 以黄色提示条展示「请重新提问，不是判断题，不能用『是』或『否』回答」，输入内容保留 |
| `GuessPanel.vue` | playing/guess | 输入框 + "我猜是…"主按钮 + "跳过猜测，继续提问"次按钮（消耗本次猜测机会）；`guesses_remaining==0` 时主按钮与跳过按钮均禁用 |
| `ResultScreen.vue` | ③result | 按 `result.type` 分支：**win**=人物卡（name+intro，恭喜文案）+ [再玩一次]；**exhausted**="次数用完，游戏结束" + 揭晓人物卡 + [再玩一次]；**aborted**="游戏已中止"+答案揭晓+[再玩一次] |
| `HistoryList.vue` | playing | qa_history 展示"Q/是·否/跳过提问"；guess_history 展示猜测/跳过记录 |
| `HostBubble.vue` | playing | 展示 `host_message`（无则不渲染） |

**计数展示规范**（必须）：
- 提问：`你有 {max_rounds} 次提问机会，当前已使用 {questions_used} 次，剩余 {questions_remaining} 次`
- 猜测：`你有 {max_rounds} 次猜测机会，当前已使用 {guesses_used} 次，剩余 {guesses_remaining} 次`
- 轮次：`第 {current_round} / {max_rounds} 轮`

### 7.3 数据层

**`src/types/api.ts`**：与 §4.3 逐字段对应的 interface（GameDTO / ResultDTO / PersonDTO / QARecordDTO / GuessRecordDTO / 各请求体 / 枚举字面量联合类型 / ApiError）。**snake_case 原样保留，禁止改名。**

**`src/api/client.ts`**：
- `axios.create({ baseURL: '/api/v1', timeout: 60000 })`（LLM 动作较慢，超时 60s）；
- 响应拦截器：成功直接返回 `response.data as GameDTO`；
- 错误拦截器：统一抛出 `ApiError(code, message, details, requestId)`（取 `error.code`，无信封时归一 `INTERNAL_ERROR`）。
- **不配置任何绝对后端地址**；跨域问题由 Vite proxy 解决（唯一路径策略）。

**`src/api/games.ts`**：`createGame / getGame / ask / guess / skipPhase / retry / abandon` 函数，URL 与 §5.2 完全一致。

**`src/stores/game.ts（Pinia）**：

| 项 | 说明 |
|---|---|
| state | `dto: GameDTO\|null`、`loading: boolean`、`error: ApiError\|null`、`lastRejectedQuestion: string\|null` |
| getters | `uiState`（idle/playing/result）、`phase`、`isResult*`、`canAsk/canSkipQuestion/canGuess/canSkipGuess`（全部由 DTO 计数派生）、`guessHint`（取 `dto.last_guess_hint`） |
| actions | 每个 action 调接口后 `dto = returnedDTO`（整体替换）、清错误；失败写 `error` 并按 code 决定是否保留面板（NOT_YES_NO_QUESTION 时记录提示不跳转）；404 时 `dto=null` 回 idle |

### 7.4 校验与错误展示规则（前端）

| 场景 | 规则 |
|---|---|
| 空文本 | 提交前拦截，不发请求；输入框红字"内容不能为空" |
| 超长 | maxlength=200 + 计数；服务端 422 兜底 |
| 请求中 | 当前面板主/次按钮全部 loading 禁用，防重复提交 |
| `NOT_YES_NO_QUESTION` | 面板内黄色提示条显示 `error.message`（或固定「请重新提问，不是判断题，不能用『是』或『否』回答」），输入内容保留 |
| `INVALID_PHASE/PHASE_CONFLICT` | 自动 `getGame()` 同步后重渲染，不弹错 |
| `*_BUDGET_EXHAUSTED` | 同步状态，按钮自然禁用 + Toast 一句说明 |
| `UPSTREAM_LLM_ERROR/500` | Toast 错误文案；输入保留，可原样重试 |
| 404 | Toast"会话已过期"，回 idle |
| 猜错提示 | `last_guess_hint` 非空时，在 QuestionPanel 顶部黄色条展示「回答错误，并不是 {guess}」，用户下一次提问/跳过时清除 |

### 7.5 Vite 代理与环境

- `vite.config.ts`：`server.proxy['/api'] = { target: 'http://localhost:8000', changeOrigin: true }`；
- 前端不读任何密钥；LLM 配置只存在于后端进程与根目录 `.env`。

---

## 八、关键时序（端到端）

**开始 → 提问 → 猜对：**
```
StartScreen --POST /games--> orchestrator 注入开局消息 → agent_loop
  → AI: tool start_game(曹操,中国历史人物,...) → 201 GameDTO(playing/question, round=1)
QuestionPanel --POST /questions{是男性吗?}--> agent_loop
  → AI: tool answer_question(yes) → 200 GameDTO(playing/guess, round=1, questions_used=1)
GuessPanel --POST /guesses{曹操}--> AI: tool judge_guess(true)
  → 200 GameDTO(result/win, person={曹操,...}) → ResultScreen 人物卡 + [再玩一次]
```

**提问阶段跳过（消耗提问机会）→ 猜错（有余量，自动回提问）：**
```
question(round=1) --POST /skip{current_phase:"question"}--> 200 (playing/guess, round=1, questions_used=1)
guess(round=1) --POST /guesses{诸葛亮}--> judge_guess(false), round<max
  → 200 (playing/question, round=2, guesses_used=1, last_guess_hint="回答错误，并不是诸葛亮")
QuestionPanel 顶部展示黄色提示条，继续提问
```

**猜测阶段跳过（消耗猜测机会）：**
```
guess(round=r<max) --POST /skip{current_phase:"guess"}--> 200 (playing/question, round=r+1, guesses_used+=1)
```

**第 10 轮猜错 → exhausted：**
```
guess(round=10)（guesses_used 由 9→10，错误）→ 200 (result/exhausted, person 揭晓)
ResultScreen 显示"次数用完，游戏结束" + [再玩一次]
```

**非判断题（不计次）：**
```
question --POST /questions{他是谁？}--> AI 未调用 answer_question
  → 422 NOT_YES_NO_QUESTION，状态不变、questions_used 不变
QuestionPanel 黄色提示："请重新提问，不是判断题，不能用『是』或『否』回答"
```

---

## 九、本地联调步骤（设计约定）

1. 后端：`geuss_who_i_am/` 下安装 `backend/requirements.txt`，根目录 `.env` 已具备 `ANTHROPIC_API_KEY`/`MODEL_ID`；
   `uvicorn backend.app.main:app --reload --port 8000`（工作目录为 `geuss_who_i_am/`，使现有 game_state/tools 等模块可导入）。
2. 前端：`cd frontend && npm install && npm run dev`（5173）。
3. 冒烟顺序：开始 → 提问（验证 yes/no 与计数+1）→ 跳过提问（验证提问计数+1、进 guess）→ 猜（错）→ 验证自动回 question + 提示条 + 轮次+1 + 猜测计数+1 → 跳过猜测（验证猜测计数+1、进下一轮 question）→ 连续猜错至 exhausted；另测放弃、刷新恢复（GET）、非判断题 422 不计次、终态后 GET 404（已释放）。

---

## 十、待确认决策点（默认值已给，可调整）

| # | 决策点 | 默认 |
|---|---|---|
| 1 | 轮次模型 | **固定 10 轮**，每轮 1 提问 + 1 猜测，先提问后猜测 |
| 2 | 跳过是否消耗次数 | **消耗**对应机会（跳过提问耗提问、跳过猜测耗猜测） |
| 3 | 猜错有余量后的去向 | **直接回到提问阶段**（下一轮），页面提示"回答错误，并不是 X"，无独立 wrong 结果页 |
| 4 | "再试一下"语义 | 固定回提问阶段；本版猜错已自动回提问，retry 接口作兼容/安全入口 |
| 5 | 非判断题处理 | 拒绝且**不计次**（422 NOT_YES_NO_QUESTION），提示"请重新提问…" |
| 6 | 前端计数展示 | 必须展示「你有 N 次机会，已使用 X 次，剩余 Y 次」（提问与猜测分别展示） |
| 7 | 输入长度 | 提问/猜测文本 strip 后 **1..200** 字 |
| 8 | 会话存储与 TTL | 单进程内存，空闲 **30 分钟**过期；**终态后自动释放** |
| 9 | skip/retry/abandon 是否走 LLM | **不走**，本地流转 + 向 messages 注入系统通知 |
| 10 | 流式输出 | v1 **不做**（同步等完整 GameDTO）；v2 可加 SSE 推送 host_message |
| 11 | 鉴权/多用户 | v1 无；预留 X-API-Key |
| 12 | CLI 与 Web 规则差异 | CLI 已同步为 v3 薄封装，与 Web 共用 agent_runner |
| 13 | 连续多局选中同一人物 | **最近 10 人 JSON 注册表 + start_game 服务端去重（撞车经工具循环自动重选，上限 3 次）**；不用随机数种子；详见 §6.6 |

---

## 十一、设计自检清单

| 检查项 | 结论 |
|---|---|
| 三个前端状态（未开始/游玩/结果）有独立组件与进入退出路径 | ✓ §7.1/7.2 |
| 固定 10 轮，每轮先提问后猜测，跳过消耗对应机会 | ✓ §0/§4.2/§5.3-5 |
| 猜错有余量直接回提问阶段并提示，猜错第 10 轮进入 exhausted | ✓ §4.2/§5.3-4/§8 |
| 猜对展示恭喜界面 + 「再玩一次」 | ✓ ResultDTO.win + ResultScreen |
| 次数用完展示"次数用完，游戏结束"并揭晓 | ✓ result.exhausted |
| 前端展示"已使用/剩余"次数（提问与猜测） | ✓ §7.2 计数展示规范 |
| 非判断题拒绝且不计次，提示"请重新提问…" | ✓ §5.3-3 / §5.4 NOT_YES_NO_QUESTION |
| skip/retry/abandon 不走 LLM | ✓ §5.1-13 / §5.3 |
| 会话仅存当前局，终态后自动释放 + 30min TTL 兜底 | ✓ §5.1-14 / §6.4 |
| 接口总览/强制要求/请求响应格式/字段名/错误码/校验规则齐全 | ✓ §5 全节 |
| 数据模型（领域+DTO+枚举+状态机）明确 | ✓ §4 |
| API 路由层（FastAPI）职责与服务层编排明确 | ✓ §6 |
| 现有 learn-claude-code 代码作为后端被复用与最小改造点明确 | ✓ §6.5 |
| 前后端字段契约单一事实源、无改名映射 | ✓ §5.1-7 / §7.3 |
| LLM 故障不产生脏状态/脏计数 | ✓ §5.1-12 / §6.3 |
