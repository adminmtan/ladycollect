<template>
  <button
    type="button"
    class="chip-toggle"
    :class="[`color-${activeColor}`, { 'is-active': modelValue }]"
    @click="toggle"
  >
    <span class="chip-dot"></span>
    <span class="chip-label">{{ label }}</span>
  </button>
</template>

<script setup lang="ts">
const props = defineProps<{
  modelValue?: boolean
  label: string
  activeColor?: 'accent' | 'warning'
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'change', v: boolean): void
}>()

function toggle() {
  const v = !props.modelValue
  emit('update:modelValue', v)
  emit('change', v)
}
</script>

<style scoped>
.chip-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  background: var(--color-muted);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  font-size: 12px;
  color: var(--color-muted-foreground);
  cursor: pointer;
  transition: all var(--transition-fast);
  height: 28px;
  font-family: var(--font-heading);
  text-transform: lowercase;
  letter-spacing: 0.3px;
}

.chip-toggle:hover {
  border-color: var(--color-muted-foreground);
  color: var(--color-foreground);
}

.chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  transition: all var(--transition-fast);
}

/* accent = green */
.chip-toggle.color-accent.is-active {
  background: rgba(34, 197, 94, 0.12);
  border-color: rgba(34, 197, 94, 0.4);
  color: var(--color-accent);
}
.chip-toggle.color-accent.is-active .chip-dot {
  background: var(--color-accent);
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.5);
}

/* warning = amber (ed2k) */
.chip-toggle.color-warning.is-active {
  background: rgba(245, 158, 11, 0.12);
  border-color: rgba(245, 158, 11, 0.4);
  color: #f59e0b;
}
.chip-toggle.color-warning.is-active .chip-dot {
  background: #f59e0b;
  box-shadow: 0 0 8px rgba(245, 158, 11, 0.5);
}
</style>
