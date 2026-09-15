<script setup lang="ts">
import { computed } from 'vue'
import { useGameStore } from '../stores/game'
import type { GuessRecordDTO, QARecordDTO } from '../types/api'

const store = useGameStore()
const dto = computed(() => store.dto!)

interface RoundRow {
  round: number
  qa?: QARecordDTO
  guess?: GuessRecordDTO
}

const rows = computed<RoundRow[]>(() => {
  const qaByRound = new Map<number, QARecordDTO>()
  const guessByRound = new Map<number, GuessRecordDTO>()
  dto.value.qa_history.forEach((r) => qaByRound.set(r.round, r))
  dto.value.guess_history.forEach((r) => guessByRound.set(r.round, r))

  const maxRound = Math.max(
    dto.value.current_round,
    ...dto.value.qa_history.map((r) => r.round),
    ...dto.value.guess_history.map((r) => r.round),
    0,
  )

  const out: RoundRow[] = []
  for (let r = 1; r <= maxRound; r++) {
    out.push({ round: r, qa: qaByRound.get(r), guess: guessByRound.get(r) })
  }
  return out
})
</script>

<template>
  <section v-if="rows.length" class="history">
    <h3 class="history-title">历史记录</h3>
    <div class="history-head">
      <span class="col-round">轮次</span>
      <span class="col-q">提问</span>
      <span class="col-g">猜测</span>
    </div>
    <div v-for="row in rows" :key="row.round" class="history-row">
      <span class="col-round">第 {{ row.round }} 轮</span>
      <span class="col-q">
        <template v-if="!row.qa">—</template>
        <template v-else-if="row.qa.kind === 'skip'">
          <em>已跳过提问</em>
        </template>
        <template v-else>
          {{ row.qa.question }}
          <strong :class="row.qa.answer">{{ row.qa.answer === 'yes' ? '是' : '不是' }}</strong>
        </template>
      </span>
      <span class="col-g">
        <template v-if="!row.guess">—</template>
        <template v-else-if="row.guess.kind === 'skip'">
          <em>已跳过猜测</em>
        </template>
        <template v-else>
          {{ row.guess.guess }}
          <span :class="['mark', row.guess.is_correct ? 'right' : 'wrong']">
            {{ row.guess.is_correct ? '✓ 猜对' : '✗ 猜错' }}
          </span>
        </template>
      </span>
    </div>
  </section>
</template>

<style scoped>
.history {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: var(--space-5);
}

.history-title {
  margin: 0 0 var(--space-3);
  font-size: 16px;
}

.history-head,
.history-row {
  display: grid;
  grid-template-columns: 72px 1fr 1fr;
  gap: var(--space-3);
  font-size: 13px;
  padding: var(--space-2) 0;
}

.history-head {
  color: var(--color-text-subtle);
  border-bottom: 1px solid var(--color-border);
  font-weight: 600;
}

.history-row {
  border-bottom: 1px dashed var(--color-border);
}

.history-row:last-child {
  border-bottom: none;
}

.col-q strong {
  margin-left: 6px;
}

.col-q strong.yes {
  color: var(--color-success);
}

.col-q strong.no {
  color: var(--color-danger);
}

.mark {
  margin-left: 6px;
  font-weight: 600;
}

.mark.right {
  color: var(--color-success);
}

.mark.wrong {
  color: var(--color-danger);
}

em {
  color: var(--color-text-subtle);
}
</style>
