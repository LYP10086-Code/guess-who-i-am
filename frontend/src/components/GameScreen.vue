<script setup lang="ts">
import { computed } from 'vue'
import { useGameStore } from '../stores/game'
import QuestionPanel from './QuestionPanel.vue'
import GuessPanel from './GuessPanel.vue'
import HostBubble from './HostBubble.vue'
import HistoryList from './HistoryList.vue'

const store = useGameStore()
const dto = computed(() => store.dto!)

async function onAbandon() {
  if (window.confirm('确定要放弃本局吗？放弃后将揭晓答案。')) {
    await store.abandonGame()
  }
}
</script>

<template>
  <section class="game">
    <!-- 顶部信息 -->
    <header class="header">
      <div class="header-left">
        <span class="hint-badge">范围：{{ dto.person_hint }}</span>
        <span class="round-badge">
          第 {{ dto.current_round }} / {{ dto.max_rounds }} 轮
        </span>
      </div>
      <button class="btn-ghost abandon-btn" :disabled="store.loading" @click="onAbandon">
        放弃游戏
      </button>
    </header>

    <!-- 次数展示（必须） -->
    <div class="counters">
      <div class="counter" :class="{ exhausted: dto.questions_remaining === 0 }">
        <div class="counter-label">提问机会</div>
        <div class="counter-text">
          你有 {{ dto.max_rounds }} 次提问机会，当前已使用
          <strong>{{ dto.questions_used }}</strong> 次，剩余
          <strong>{{ dto.questions_remaining }}</strong> 次
        </div>
      </div>
      <div class="counter" :class="{ exhausted: dto.guesses_remaining === 0 }">
        <div class="counter-label">猜测机会</div>
        <div class="counter-text">
          你有 {{ dto.max_rounds }} 次猜测机会，当前已使用
          <strong>{{ dto.guesses_used }}</strong> 次，剩余
          <strong>{{ dto.guesses_remaining }}</strong> 次
        </div>
      </div>
    </div>

    <!-- 猜错提示条 -->
    <div v-if="dto.last_guess_hint" class="hint-banner">
      {{ dto.last_guess_hint.message }}，请继续提问。
    </div>

    <HostBubble v-if="dto.host_message" :message="dto.host_message" />

    <!-- 阶段面板 -->
    <QuestionPanel v-if="store.phase === 'question'" />
    <GuessPanel v-else-if="store.phase === 'guess'" />

    <HistoryList />
  </section>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.header-left {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.hint-badge {
  background: var(--color-primary-soft);
  color: var(--color-primary);
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
}

.round-badge {
  font-size: 13px;
  color: var(--color-text-subtle);
}

.abandon-btn {
  font-size: 13px;
  padding: 6px 14px;
}

.counters {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.counter {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
}

.counter.exhausted {
  border-color: var(--color-danger);
  background: var(--color-danger-soft);
}

.counter-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-subtle);
  margin-bottom: 2px;
}

.counter-text {
  font-size: 13px;
}

.counter-text strong {
  color: var(--color-primary);
  font-size: 15px;
}

.counter.exhausted .counter-text strong {
  color: var(--color-danger);
}

.hint-banner {
  background: var(--color-warning-soft);
  color: var(--color-warning);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  font-size: 14px;
  margin-bottom: var(--space-3);
}

@media (max-width: 560px) {
  .counters {
    grid-template-columns: 1fr;
  }
}
</style>
