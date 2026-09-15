<script setup lang="ts">
defineProps<{ message: string }>()
</script>

<template>
  <div class="host-bubble">
    <span class="host-avatar">主持人</span>
    <span class="host-text">{{ message }}</span>
  </div>
</template>

<style scoped>
.host-bubble {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-primary);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-3);
}

.host-avatar {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: var(--color-primary);
  border-radius: 6px;
  padding: 2px 8px;
}

.host-text {
  font-size: 14px;
}
</style>
