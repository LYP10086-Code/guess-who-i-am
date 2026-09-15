<script setup lang="ts">
import { computed, ref } from 'vue'
import { useGameStore } from '../stores/game'

const store = useGameStore()
const dto = computed(() => store.dto!)

const text = ref('')
const localError = ref('')

const panelError = computed(() =>
  store.error?.code === 'INVALID_GUESS' ? store.error.message : '',
)
const budgetEmpty = computed(() => dto.value.guesses_remaining === 0)

async function submit() {
  localError.value = ''
  const value = text.value.trim()
  if (!value) {
    localError.value = '内容不能为空'
    return
  }
  const next = await store.guess(value)
  if (next) text.value = ''
}

async function skipGuess() {
  await store.skip('guess')
}
</script>

<template>
  <section class="panel">
    <h2 class="panel-title">猜测阶段</h2>
    <p class="panel-hint">
      根据已有的问答，直接输入你猜测的人物名称（支持别名、字号）。
    </p>

    <div v-if="dto.last_answer" class="last-answer">
      主持人对上一问题的回答：
      <strong :class="dto.last_answer.answer">
        {{ dto.last_answer.answer === 'yes' ? '是' : '不是' }}
      </strong>
    </div>

    <div v-if="panelError" class="banner banner-warning">{{ panelError }}</div>
    <div v-if="localError" class="banner banner-danger">{{ localError }}</div>
    <div v-if="budgetEmpty" class="banner banner-danger">猜测次数已用完。</div>

    <input
      v-model="text"
      type="text"
      maxlength="200"
      :disabled="store.loading || budgetEmpty"
      placeholder="例如：曹操"
      @keydown.enter="submit"
    />

    <div class="actions">
      <button
        class="btn-primary"
        :disabled="store.loading || budgetEmpty"
        @click="submit"
      >
        {{ store.loading ? '判定中…' : '我猜是…' }}
      </button>
      <button
        class="btn-secondary"
        :disabled="store.loading || budgetEmpty"
        title="跳过将消耗本次猜测机会"
        @click="skipGuess"
      >
        跳过猜测，继续提问（消耗 1 次猜测）
      </button>
    </div>
  </section>
</template>

<style scoped>
.panel {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: var(--space-5);
  margin-bottom: var(--space-4);
}

.panel-title {
  margin: 0 0 var(--space-1);
  font-size: 18px;
}

.panel-hint {
  margin: 0 0 var(--space-3);
  color: var(--color-text-subtle);
  font-size: 13px;
}

.last-answer {
  font-size: 13px;
  color: var(--color-text-subtle);
  margin-bottom: var(--space-3);
}

.last-answer strong.yes {
  color: var(--color-success);
}

.last-answer strong.no {
  color: var(--color-danger);
}

.banner {
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  font-size: 13px;
  margin-bottom: var(--space-3);
}

.banner-warning {
  background: var(--color-warning-soft);
  color: var(--color-warning);
}

.banner-danger {
  background: var(--color-danger-soft);
  color: var(--color-danger);
}

.actions {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-top: var(--space-4);
}
</style>
