<template>
  <div
    class="chip-daterange"
    :class="{ 'is-active': !!modelValue }"
  >
    <span class="chip-icon"><el-icon><Calendar /></el-icon></span>
    <span class="chip-label">{{ label }}</span>
    <input
      type="date"
      class="date-input"
      :value="startStr"
      @change="onStartChange"
    />
    <span class="date-arrow">→</span>
    <input
      type="date"
      class="date-input"
      :value="endStr"
      @change="onEndChange"
    />
    <span v-if="modelValue" class="date-clear" @click.stop="onClear">
      <el-icon><Close /></el-icon>
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Calendar, Close } from '@element-plus/icons-vue'

const props = defineProps<{
  modelValue: [string, string] | null
  label: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: [string, string] | null): void
  (e: 'change', v: [string, string] | null): void
}>()

const startStr = computed(() => props.modelValue?.[0] || '')
const endStr = computed(() => props.modelValue?.[1] || '')

function emit_(v: [string, string] | null) {
  emit('update:modelValue', v)
  emit('change', v)
}

function onStartChange(e: Event) {
  const v = (e.target as HTMLInputElement).value
  if (!v) return emit_(endStr.value ? [endStr.value, endStr.value] : null)
  emit_([v, endStr.value || v])
}

function onEndChange(e: Event) {
  const v = (e.target as HTMLInputElement).value
  if (!v) return emit_(startStr.value ? [startStr.value, startStr.value] : null)
  emit_([startStr.value || v, v])
}

function onClear() {
  emit_(null)
}
</script>

<style scoped>
.chip-daterange {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  background: var(--color-muted);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  font-size: 12px;
  color: var(--color-muted-foreground);
  transition: all var(--transition-fast);
  height: 28px;
}

.chip-daterange:hover {
  border-color: var(--color-muted-foreground);
  color: var(--color-foreground);
}

.chip-daterange.is-active {
  background: rgba(34, 197, 94, 0.12);
  border-color: rgba(34, 197, 94, 0.4);
  color: var(--color-accent);
}

.chip-icon {
  display: inline-flex;
  font-size: 12px;
  opacity: 0.85;
}

.chip-label {
  font-family: var(--font-heading);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  opacity: 0.8;
}

.date-input {
  appearance: none;
  -webkit-appearance: none;
  background: transparent;
  border: none;
  outline: none;
  color: inherit;
  font-family: var(--font-heading);
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  padding: 0;
  width: 96px;
  cursor: pointer;
}

.date-input::-webkit-calendar-picker-indicator {
  filter: invert(0.6);
  opacity: 0.5;
  cursor: pointer;
}

.date-arrow {
  color: rgba(255, 255, 255, 0.3);
  font-size: 11px;
}

.date-clear {
  display: inline-flex;
  cursor: pointer;
  font-size: 12px;
  opacity: 0.6;
}
.date-clear:hover {
  opacity: 1;
  color: var(--color-destructive);
}
</style>
