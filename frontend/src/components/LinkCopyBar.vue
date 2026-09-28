<template>
  <div class="link-copy-bar">
    <div class="bar-left">
      <span class="selection-info">
        <el-icon><Check /></el-icon>
        已选 <strong>{{ selectedIds.length }}</strong> / {{ total }} 条
      </span>
    </div>
    <div class="bar-center">
      <el-checkbox-group v-model="kinds" size="default">
        <el-checkbox label="magnet" value="magnet">magnet</el-checkbox>
        <el-checkbox label="ed2k" value="ed2k">ed2k</el-checkbox>
      </el-checkbox-group>
    </div>
    <div class="bar-right">
      <el-button @click="onCopy('text')" :disabled="!selectedIds.length" class="btn-ghost">
        <el-icon><DocumentCopy /></el-icon>
        复制文本
      </el-button>
      <el-button type="primary" @click="onCopy('clipboard')" :disabled="!selectedIds.length" class="btn-accent">
        <el-icon><DocumentChecked /></el-icon>
        一键复制
      </el-button>
      <el-button type="danger" plain :disabled="!selectedIds.length" @click="onDeleteBatch" class="btn-danger">
        <el-icon><Delete /></el-icon>
        删除选中
      </el-button>
      <div class="bar-divider"></div>
      <el-button @click="$emit('selectAll')" class="btn-ghost btn-sm">
        全选当前
      </el-button>
      <el-button @click="$emit('selectNone')" class="btn-ghost btn-sm">
        清空选择
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, DocumentCopy, DocumentChecked, Delete } from '@element-plus/icons-vue'

const props = defineProps<{
  selectedIds: number[]
  total: number
}>()

const emit = defineEmits<{
  (e: 'selectAll'): void
  (e: 'selectNone'): void
  (e: 'copy', payload: { ids: number[]; kinds: string[]; mode: 'text' | 'clipboard' }): void
  (e: 'delete', ids: number[]): void
}>()

const kinds = ref<string[]>(['magnet', 'ed2k'])

function onCopy(mode: 'text' | 'clipboard') {
  if (!kinds.value.length) {
    ElMessage.warning('请至少选择一种链接类型')
    return
  }
  if (!props.selectedIds.length) {
    ElMessage.warning('请先选择帖子')
    return
  }
  emit('copy', { ids: [...props.selectedIds], kinds: [...kinds.value], mode })
}

async function onDeleteBatch() {
  if (!props.selectedIds.length) {
    ElMessage.warning('请先选择帖子')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${props.selectedIds.length} 条帖子吗？此操作不可撤销。`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  emit('delete', [...props.selectedIds])
}
</script>

<style scoped>
.link-copy-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.08) 0%, rgba(27, 35, 54, 0.6) 100%);
  border: 1px solid rgba(34, 197, 94, 0.15);
  border-radius: var(--radius-lg);
  padding: 14px 20px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  backdrop-filter: blur(8px);
}

.bar-left {
  display: flex;
  align-items: center;
}

.selection-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--color-foreground);
}

.selection-info .el-icon {
  color: var(--color-accent);
}

.selection-info strong {
  color: var(--color-accent);
  font-weight: 700;
  font-family: var(--font-heading);
}

.bar-center {
  display: flex;
  align-items: center;
}

.bar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.bar-divider {
  width: 1px;
  height: 24px;
  background: rgba(255, 255, 255, 0.1);
  margin: 0 4px;
}

/* 按钮样式 */
.btn-accent {
  background: linear-gradient(135deg, var(--color-accent) 0%, #16a34a 100%) !important;
  border: none !important;
  color: var(--color-on-accent) !important;
  font-weight: 600;
}

.btn-accent:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.3);
}

.btn-accent:disabled {
  background: var(--color-muted) !important;
  color: var(--color-muted-foreground) !important;
  opacity: 0.6;
}

.btn-ghost {
  background: transparent !important;
  border: 1px solid var(--color-border) !important;
  color: var(--color-foreground) !important;
}

.btn-ghost:hover:not(:disabled) {
  background: var(--color-muted) !important;
  border-color: var(--color-muted-foreground) !important;
}

.btn-ghost:disabled {
  opacity: 0.4;
}

.btn-danger {
  background: rgba(239, 68, 68, 0.1) !important;
  border: 1px solid rgba(239, 68, 68, 0.3) !important;
  color: var(--color-destructive) !important;
}

.btn-danger:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.2) !important;
}

.btn-danger:disabled {
  opacity: 0.4;
}

.btn-sm {
  padding: 8px 12px !important;
  font-size: 13px !important;
}

@media (max-width: 768px) {
  .link-copy-bar {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }

  .bar-center,
  .bar-right {
    justify-content: flex-start;
  }

  .bar-divider {
    display: none;
  }
}
</style>
