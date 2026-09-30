<template>
  <div class="chip-select" :class="{ 'is-active': modelValue !== undefined && modelValue !== null && modelValue !== '' }">
    <span class="chip-icon">
      <component :is="iconComp" />
    </span>
    <span class="chip-label" v-if="label">{{ label }}</span>
    <select
      class="chip-native"
      :value="modelValue ?? ''"
      @change="onChange"
    >
      <option v-if="placeholder" value="">{{ placeholder }}</option>
      <option v-for="opt in options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
    </select>
    <span class="chip-caret">
      <el-icon><CaretBottom /></el-icon>
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CaretBottom, Compass, Sort } from '@element-plus/icons-vue'

const props = defineProps<{
  modelValue?: any
  options: { label: string; value: any }[]
  placeholder?: string
  label?: string
  icon?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: any): void
  (e: 'change', v: any): void
}>()

const ICONS: Record<string, any> = { Compass, Sort }
const iconComp = computed(() => ICONS[props.icon || 'Compass'] || Compass)

function onChange(e: Event) {
  const raw = (e.target as HTMLSelectElement).value
  let v: any = raw
  // 如果原选项里有数字，按数字解析
  if (props.options.length) {
    const found = props.options.find((o) => String(o.value) === raw)
    if (found) v = found.value
  }
  // 空值 → undefined
  if (v === '') v = undefined
  emit('update:modelValue', v)
  emit('change', v)
}
</script>

<style scoped>
.chip-select {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  background: var(--color-muted);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  font-size: 12px;
  color: var(--color-muted-foreground);
  cursor: pointer;
  transition: all var(--transition-fast);
  position: relative;
  height: 28px;
}

.chip-select:hover {
  border-color: var(--color-muted-foreground);
  color: var(--color-foreground);
}

.chip-select.is-active {
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

.chip-native {
  appearance: none;
  -webkit-appearance: none;
  background: transparent;
  border: none;
  outline: none;
  color: inherit;
  font-family: var(--font-body);
  font-size: 12.5px;
  font-weight: 500;
  padding-right: 4px;
  cursor: pointer;
  min-width: 100px;
  max-width: 200px;
}

.chip-native option {
  background: var(--color-card);
  color: var(--color-foreground);
}

.chip-caret {
  display: inline-flex;
  font-size: 10px;
  opacity: 0.6;
  pointer-events: none;
}
</style>
