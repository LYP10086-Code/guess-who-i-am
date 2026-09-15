// 与后端 schemas/game.py 逐字段同名同形（snake_case，禁止改名映射）

export type GameStatus = 'idle' | 'playing' | 'result'
export type Phase = 'question' | 'guess'
export type AnswerValue = 'yes' | 'no'
export type ResultType = 'win' | 'exhausted' | 'aborted'
export type GuessKind = 'guess' | 'skip'
export type QuestionKind = 'ask' | 'skip'

export interface PersonDTO {
  name: string
  hint: string
  intro: string
}

export interface QARecordDTO {
  seq: number
  kind: QuestionKind
  question: string | null
  answer: AnswerValue | null
  round: number
}

export interface GuessRecordDTO {
  seq: number
  kind: GuessKind
  guess: string | null
  is_correct: boolean | null
  round: number
}

export interface LastAnswerDTO {
  question: string
  answer: AnswerValue
}

export interface GuessHintDTO {
  guess: string
  message: string
}

export interface ResultDTO {
  type: ResultType
  title: string
  message: string
  person: PersonDTO | null
}

export interface GameDTO {
  session_id: string
  status: GameStatus
  phase: Phase | null
  current_round: number
  person_hint: string
  max_rounds: number
  questions_used: number
  questions_remaining: number
  guesses_used: number
  guesses_remaining: number
  qa_history: QARecordDTO[]
  guess_history: GuessRecordDTO[]
  result: ResultDTO | null
  last_answer: LastAnswerDTO | null
  last_guess_hint: GuessHintDTO | null
  host_message: string | null
  created_at: string
  updated_at: string
}

export interface CreateGameRequest {
  person_scope?: string
  max_rounds?: number
}

// ---------- 错误信封 ----------

export type ErrorCodeValue =
  | 'SESSION_NOT_FOUND'
  | 'INVALID_PHASE'
  | 'PHASE_CONFLICT'
  | 'QUESTION_BUDGET_EXHAUSTED'
  | 'GUESS_BUDGET_EXHAUSTED'
  | 'GAME_NOT_ACTIVE'
  | 'EMPTY_INPUT'
  | 'INPUT_TOO_LONG'
  | 'INVALID_PARAMETER'
  | 'NOT_YES_NO_QUESTION'
  | 'INVALID_GUESS'
  | 'RATE_LIMITED'
  | 'UPSTREAM_LLM_ERROR'
  | 'INTERNAL_ERROR'

export interface ApiErrorShape {
  code: ErrorCodeValue
  message: string
  details: Record<string, unknown>
}

export interface ErrorEnvelope {
  error: ApiErrorShape
  request_id: string
}
