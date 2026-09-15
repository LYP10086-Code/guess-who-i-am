<script setup lang="ts">
import { useGameStore } from './stores/game'
import StartScreen from './components/StartScreen.vue'
import GameScreen from './components/GameScreen.vue'
import ResultScreen from './components/ResultScreen.vue'

const store = useGameStore()
</script>

<template>
  <div class="app-shell">
    <StartScreen v-if="store.uiState === 'idle'" />
    <GameScreen v-else-if="store.uiState === 'playing'" />
    <ResultScreen
      v-else-if="store.uiState === 'result' && store.dto?.result"
      :result="store.dto.result"
    />

    <transition name="toast">
      <div v-if="store.toast" class="toast">{{ store.toast }}</div>
    </transition>
  </div>
</template>

<style scoped>
.app-shell {
  max-width: 760px;
  margin: 0 auto;
  padding: var(--space-5) var(--space-4) var(--space-6);
}

.toast {
  position: fixed;
  left: 50%;
  bottom: 40px;
  transform: translateX(-50%);
  background: rgba(31, 41, 55, 0.92);
  color: #fff;
  padding: 10px 18px;
  border-radius: var(--radius-md);
  font-size: 14px;
  z-index: 50;
  box-shadow: var(--shadow-card);
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}
</style>
