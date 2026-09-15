<script setup lang="ts">
import { computed } from 'vue'
import type { ResultDTO } from '../types/api'
import { useGameStore } from '../stores/game'

const props = defineProps<{ result: ResultDTO }>()
const store = useGameStore()

const themeClass = computed(() => `result-${props.result.type}`)
const icon = computed(() => {
  switch (props.result.type) {
    case 'win':
      return '🎉'
    case 'exhausted':
      return '😅'
    default:
      return '🏳️'
  }
})
</script>

<template>
  <section class="result-card" :class="themeClass">
    <div class="icon">{{ icon }}</div>
    <h1 class="title">{{ result.title }}</h1>
    <p class="message">{{ result.message }}</p>

    <div v-if="result.person" class="person-card">
      <div class="person-name">{{ result.person.name }}</div>
      <div class="person-hint">{{ result.person.hint }}</div>
      <p class="person-intro">{{ result.person.intro }}</p>
    </div>

    <button class="btn-primary replay-btn" :disabled="store.loading" @click="store.start()">
      {{ store.loading ? '正在开启新局…' : '再玩一次' }}
    </button>
  </section>
</template>

<style scoped>
.result-card {
  margin-top: 10vh;
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: var(--space-6);
  text-align: center;
}

.icon {
  font-size: 48px;
  margin-bottom: var(--space-3);
}

.result-win .title {
  color: var(--color-success);
}

.title {
  font-size: 28px;
  margin: 0 0 var(--space-2);
}

.message {
  color: var(--color-text-subtle);
  margin: 0 0 var(--space-5);
}

.person-card {
  background: var(--color-primary-soft);
  border-radius: var(--radius-md);
  padding: var(--space-4) var(--space-5);
  margin-bottom: var(--space-5);
  text-align: left;
}

.person-name {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-primary);
}

.person-hint {
  font-size: 13px;
  color: var(--color-text-subtle);
  margin-bottom: var(--space-2);
}

.person-intro {
  margin: 0;
  font-size: 14px;
}

.replay-btn {
  width: 220px;
  font-size: 16px;
  padding: 12px 24px;
}
</style>
