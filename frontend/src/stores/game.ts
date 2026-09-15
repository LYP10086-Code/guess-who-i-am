import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError } from '../api/client'
import * as api from '../api/games'
import type { GameDTO, GameStatus, Phase } from '../types/api'

export const useGameStore = defineStore('game', () => {
  // ---------- state ----------
  const dto = ref<GameDTO | null>(null)
  const loading = ref(false)
  const error = ref<ApiError | null>(null)
  const toast = ref<string | null>(null)

  // ---------- getters ----------
  const uiState = computed<GameStatus>(() => dto.value?.status ?? 'idle')
  const phase = computed<Phase | null>(() => dto.value?.phase ?? null)

  let toastTimer: ReturnType<typeof setTimeout> | null = null
  function showToast(message: string) {
    toast.value = message
    if (toastTimer) clearTimeout(toastTimer)
    toastTimer = setTimeout(() => {
      toast.value = null
    }, 2800)
  }

  async function safeRefresh() {
    if (!dto.value) return
    try {
      dto.value = await api.getGame(dto.value.session_id)
    } catch {
      /* 同步失败保持本地快照 */
    }
  }

  /** 统一动作封装：成功整体替换 dto；失败按错误码分流。 */
  async function runAction(
    action: () => Promise<GameDTO>,
    options: { toastOnError?: boolean } = {},
  ): Promise<GameDTO | null> {
    loading.value = true
    error.value = null
    try {
      const next = await action()
      dto.value = next
      return next
    } catch (e) {
      if (e instanceof ApiError) {
        switch (e.code) {
          case 'INVALID_PHASE':
          case 'PHASE_CONFLICT':
            // 状态不同步：静默 GET 同步，不弹错
            await safeRefresh()
            return dto.value
          case 'QUESTION_BUDGET_EXHAUSTED':
          case 'GUESS_BUDGET_EXHAUSTED':
            await safeRefresh()
            showToast(e.message)
            return dto.value
          case 'SESSION_NOT_FOUND':
            dto.value = null
            showToast('会话已过期，请重新开始游戏。')
            return null
          case 'NOT_YES_NO_QUESTION':
          case 'INVALID_GUESS':
            // 面板内提示，保留输入与当前面板
            error.value = e
            return null
          default:
            error.value = e
            if (options.toastOnError !== false) showToast(e.message)
            return null
        }
      }
      showToast('网络异常，请稍后重试。')
      return null
    } finally {
      loading.value = false
    }
  }

  // ---------- actions ----------
  function start() {
    return runAction(() => api.createGame({}), { toastOnError: true })
  }

  function ask(text: string) {
    if (!dto.value) return Promise.resolve(null)
    return runAction(
      () => api.askQuestion(dto.value!.session_id, text),
      { toastOnError: true },
    )
  }

  function guess(text: string) {
    if (!dto.value) return Promise.resolve(null)
    return runAction(
      () => api.makeGuess(dto.value!.session_id, text),
      { toastOnError: true },
    )
  }
  function skip(currentPhase: Phase) {
    if (!dto.value) return Promise.resolve(null)
    return runAction(
      () => api.skipPhase(dto.value!.session_id, currentPhase),
      { toastOnError: true },
    )
  }

  function retryToQuestion() {
    if (!dto.value) return Promise.resolve(null)
    return runAction(() => api.retry(dto.value!.session_id))
  }

  function abandonGame() {
    if (!dto.value) return Promise.resolve(null)
    return runAction(() => api.abandon(dto.value!.session_id))
  }

  function clearPanelError() {
    error.value = null
  }

  return {
    dto,
    loading,
    error,
    toast,
    uiState,
    phase,
    showToast,
    start,
    ask,
    guess,
    skip,
    retryToQuestion,
    abandonGame,
    clearPanelError,
  }
})
