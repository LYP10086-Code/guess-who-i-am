<script setup lang="ts">
import { computed, ref } from 'vue'
import { useGameStore } from '../stores/game'

const store = useGameStore()
const dto = computed(() => store.dto!)

const text = ref('')
const localError = ref('')

const panelError = computed(() =>
  store.error?.code === 'NOT_YES_NO_QUESTION' ? store.error.message : '',
)
const budgetEmpty = computed(() => dto.value.questions_remaining === 0)

async function submit() {
  localError.value = ''
  const value = text.value.trim()
  if (!value) {
    localError.value = '内容不能为空'
    return
  }
  const next = await store.ask(value)
  if (next) text.value = ''
}

async function skipQuestion() {
  await store.skip('question')
}
</script>

<template>
  <section class="panel">
    <h2 class="panel-title">提问阶段</h2>
    <p class="panel-hint">提出一个可以用「是」或「否」回答的问题。</p>

    <div v-if="panelError" class="banner banner-warning">{{ panelError }}</div>
    <div v-if="localError" class="banner banner-danger">{{ localError }}</div>
    <div v-if="budgetEmpty" class="banner banner-danger">提问次数已用完，请直接进入猜测。</div>

    <textarea
      v-model="text"
      rows="2"
      maxlength="200"
      :disabled="store.loading || budgetEmpty"
      placeholder="例如：是男性吗？"
      @keydown.enter.meta="submit"
    />
    <div class="meta-row">
      <span class="char-count">{{ text.length }}/200</span>
    </div>

    <div class="actions">
      <button
        class="btn-primary"
        :disabled="store.loading || budgetEmpty"
        @click="submit"
      >
        {{ store.loading ? '请稍候…' : '提问' }}
      </button>
      <button
        class="btn-secondary"
        :disabled="store.loading || budgetEmpty"
        title="跳过将消耗本次提问机会"
        @click="skipQuestion"
      >
        跳过提问，直接去猜（消耗 1 次提问）
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
  margin: 0 0 var(--space-4);
  color: var(--color-text-subtle);
  font-size: 13px;
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

.meta-row {
  display: flex;
  justify-content: flex-end;
  margin: 2px 0 var(--space-3);
}

.char-count {
  font-size: 12px;
  color: var(--color-text-subtle);
}

.actions {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}
</style>
