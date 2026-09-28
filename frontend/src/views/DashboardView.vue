<template>
  <div class="dashboard">
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col v-for="card in cards" :key="card.label" :xs="24" :sm="12" :lg="6">
        <div class="stat-card glass-card">
          <div class="stat-icon" :style="{ background: card.gradient }">
            <el-icon :size="24"><component :is="card.icon" /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">{{ card.label }}</div>
            <div class="stat-value">{{ formatNumber(card.value) }}</div>
          </div>
          <div class="stat-glow" :style="{ background: card.glow }"></div>
        </div>
      </el-col>
    </el-row>

    <!-- 主内容区 -->
    <el-row :gutter="12" class="content-row">
      <!-- 左侧：最近任务 -->
      <el-col :span="15">
        <div class="glass-card tasks-card">
          <div class="card-header">
            <div class="card-title">
              <el-icon><Clock /></el-icon>
              <span>最近任务</span>
            </div>
            <div class="live-indicator">
              <span class="live-dot"></span>
              <span>实时更新</span>
            </div>
          </div>
          <el-table :data="recentJobs" size="small" empty-text="暂无任务" class="dark-table">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="task_id" label="任务 ID" width="90" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <span :class="['status-badge', `status-${row.status}`]">
                  {{ statusText(row.status) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="progress_pages" label="已抓页" width="90" align="center" />
            <el-table-column prop="posts_saved" label="入库" width="80" align="center" />
            <el-table-column label="开始时间" min-width="160">
              <template #default="{ row }">
                <span class="time-text">{{ row.started_at || '-' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>

      <!-- 右侧：使用提示 -->
      <el-col :span="9">
        <div class="glass-card tips-card">
          <div class="card-header">
            <div class="card-title">
              <el-icon><Guide /></el-icon>
              <span>快速入门</span>
            </div>
          </div>
          <div class="tips-list">
            <div class="tip-item">
              <div class="tip-number">1</div>
              <div class="tip-content">
                <span class="tip-title">添加站点</span>
                <span class="tip-desc">在「站点配置」添加域名和入口 URL</span>
              </div>
            </div>
            <div class="tip-item">
              <div class="tip-number">2</div>
              <div class="tip-content">
                <span class="tip-title">创建任务</span>
                <span class="tip-desc">设置采集范围、关键字和分类条件</span>
              </div>
            </div>
            <div class="tip-item">
              <div class="tip-number">3</div>
              <div class="tip-content">
                <span class="tip-title">启动采集</span>
                <span class="tip-desc">系统自动启动 stealth Chromium</span>
              </div>
            </div>
            <div class="tip-item">
              <div class="tip-number">4</div>
              <div class="tip-content">
                <span class="tip-title">查看结果</span>
                <span class="tip-desc">多选复制 magnet 和 ed2k 链接</span>
              </div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { statsApi, type Job, type OverviewStats } from '@/api'
import { Document, Magnet, Link, DataLine, Clock, Guide } from '@element-plus/icons-vue'

const overview = ref<OverviewStats | null>(null)
const recentJobs = ref<Job[]>([])

const cards = computed(() => [
  {
    label: '采集总数',
    value: overview.value?.total_posts ?? 0,
    icon: Document,
    gradient: 'linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(59, 130, 246, 0.05) 100%)',
    glow: 'radial-gradient(circle at 80% 20%, rgba(59, 130, 246, 0.15) 0%, transparent 60%)',
  },
  {
    label: '含 magnet',
    value: overview.value?.with_magnet ?? 0,
    icon: Magnet,
    gradient: 'linear-gradient(135deg, rgba(34, 197, 94, 0.2) 0%, rgba(34, 197, 94, 0.05) 100%)',
    glow: 'radial-gradient(circle at 80% 20%, rgba(34, 197, 94, 0.15) 0%, transparent 60%)',
  },
  {
    label: '含 ed2k',
    value: overview.value?.with_ed2k ?? 0,
    icon: Link,
    gradient: 'linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(245, 158, 11, 0.05) 100%)',
    glow: 'radial-gradient(circle at 80% 20%, rgba(245, 158, 11, 0.15) 0%, transparent 60%)',
  },
  {
    label: '最近 7 天新增',
    value: overview.value?.recent_posts_7d ?? 0,
    icon: DataLine,
    gradient: 'linear-gradient(135deg, rgba(239, 68, 68, 0.2) 0%, rgba(239, 68, 68, 0.05) 100%)',
    glow: 'radial-gradient(circle at 80% 20%, rgba(239, 68, 68, 0.15) 0%, transparent 60%)',
  },
])

function formatNumber(num: number): string {
  if (num >= 10000) {
    return (num / 10000).toFixed(1) + 'w'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'k'
  }
  return num.toLocaleString()
}

function statusText(s: string) {
  const map: Record<string, string> = {
    done: '已完成',
    running: '采集中',
    failed: '失败',
    pending: '等待中',
  }
  return map[s] || s
}

onMounted(async () => {
  overview.value = await statsApi.overview()
  recentJobs.value = await statsApi.recentJobs(10)
})
</script>

<style scoped>
.dashboard {
  width: 100%;
}

/* 统计卡片行 */
.stats-row {
  margin-bottom: 24px;
}

.stat-card {
  position: relative;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  overflow: hidden;
  margin-bottom: 16px;
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-foreground);
  flex-shrink: 0;
}

.stat-content {
  flex: 1;
  min-width: 0;
}

.stat-label {
  font-size: 13px;
  color: var(--color-muted-foreground);
  margin-bottom: 4px;
  font-weight: 500;
}

.stat-value {
  font-family: var(--font-heading);
  font-size: 28px;
  font-weight: 700;
  color: var(--color-foreground);
  line-height: 1.2;
}

.stat-glow {
  position: absolute;
  top: 0;
  right: 0;
  width: 120px;
  height: 120px;
  pointer-events: none;
}

/* 内容行 */
.content-row {
  margin-bottom: 24px;
}

.glass-card {
  height: 100%;
}

.tasks-card {
  padding: 20px;
}

.tips-card {
  padding: 20px;
}

/* 卡片头部 */
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-foreground);
}

.card-title .el-icon {
  font-size: 20px;
  color: var(--color-accent);
}

/* 实时指示器 */
.live-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-muted-foreground);
}

.live-dot {
  width: 8px;
  height: 8px;
  background: var(--color-accent);
  border-radius: 50%;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.5;
    transform: scale(1.2);
  }
}

/* 表格 */
.dark-table {
  background: transparent;
}

.dark-table :deep(.el-table__header-wrapper th) {
  background: var(--color-muted) !important;
  color: var(--color-foreground);
  font-weight: 600;
  font-size: 13px;
  border: none !important;
}

.dark-table :deep(.el-table__body-wrapper tr) {
  background: transparent;
}

.dark-table :deep(.el-table__body-wrapper td) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.04) !important;
  background: transparent;
}

.dark-table :deep(.el-table__body-wrapper tr:hover td) {
  background: rgba(255, 255, 255, 0.02) !important;
}

/* 状态徽章 */
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.status-done {
  background: rgba(34, 197, 94, 0.15);
  color: var(--color-accent);
}

.status-running {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.status-failed {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-destructive);
}

.status-pending {
  background: rgba(148, 163, 184, 0.15);
  color: var(--color-muted-foreground);
}

.time-text {
  font-family: var(--font-heading);
  font-size: 12px;
  color: var(--color-muted-foreground);
}

/* 提示列表 */
.tips-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tip-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: var(--radius-md);
  border: 1px solid rgba(255, 255, 255, 0.04);
  transition: all var(--transition-normal);
}

.tip-item:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
}

.tip-number {
  width: 28px;
  height: 28px;
  background: linear-gradient(135deg, var(--color-accent) 0%, #16a34a 100%);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-heading);
  font-size: 14px;
  font-weight: 700;
  color: var(--color-on-accent);
  flex-shrink: 0;
}

.tip-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tip-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-foreground);
}

.tip-desc {
  font-size: 12px;
  color: var(--color-muted-foreground);
  line-height: 1.5;
}
</style>
