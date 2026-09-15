<script setup lang="ts">
import { useGameStore } from '../stores/game'

const store = useGameStore()
</script>

<template>
  <section class="start-card">
    <h1 class="title">猜猜我是谁</h1>
    <p class="subtitle">AI 主持人心里想了一位中国历史人物，通过提问与猜测找出 TA！</p>

    <ul class="rules">
      <li>共 <strong>10 轮</strong>，每轮先提 1 个「是/不是」问题，再进行 1 次猜测</li>
      <li>提问与猜测各 10 次机会，<strong>跳过也会消耗本次机会</strong></li>
      <li>猜错且仍有轮次时，自动回到下一轮提问</li>
      <li>非判断题会被拒绝，且不消耗提问次数</li>
    </ul>

    <button
      class="btn-primary start-btn"
      :disabled="store.loading"
      @click="store.start()"
    >
      {{ store.loading ? '主持人正在准备中…' : '开始游戏' }}
    </button>
  </section>
</template>

<style scoped>
.start-card {
  margin-top: 12vh;
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: var(--space-6);
  text-align: center;
}

.title {
  font-size: 34px;
  margin: 0 0 var(--space-3);
  color: var(--color-primary);
}

.subtitle {
  color: var(--color-text-subtle);
  margin: 0 0 var(--space-5);
}

.rules {
  text-align: left;
  display: inline-block;
  margin: 0 auto var(--space-6);
  padding-left: var(--space-5);
  color: var(--color-text);
  font-size: 15px;
}

.rules li {
  margin-bottom: var(--space-2);
}

.start-btn {
  display: block;
  width: 220px;
  margin: 0 auto;
  font-size: 17px;
  padding: 12px 24px;
}
</style>
