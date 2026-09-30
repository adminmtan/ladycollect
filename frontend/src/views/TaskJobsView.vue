<template>
  <div class="task-jobs-page">
    <!-- 顶部任务运行记录表格 -->
    <el-card class="jobs-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span class="header-title">任务运行记录</span>
            <el-tag v-if="taskId" size="small" class="task-tag">
              task #{{ taskId }}
            </el-tag>
            <span v-if="jobs.length" class="header-count">共 {{ jobs.length }} 次执行</span>
          </div>
          <el-button @click="refresh" size="small" :loading="loading" plain>
            <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
          </el-button>
        </div>
      </template>

      <el-alert
        v-if="loadError"
        :title="loadError"
        type="error"
        :closable="false"
        show-icon
        class="error-alert"
      />
      <el-table
        :data="jobs"
        empty-text="暂无运行记录"
        highlight-current-row
        @row-click="onJobClick"
        :row-class-name="rowClassName"
        class="jobs-table"
        style="width: 100%"
      >
        <el-table-column prop="id" label="ID" width="56">
          <template #default="{ row }">
            <span class="mono job-id">#{{ row.id }}</span>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="108">
          <template #default="{ row }">
            <span class="status-pill" :class="`status-${row.status}`">
              <el-icon v-if="row.status === 'running'" class="status-icon spin"><Loading /></el-icon>
              <el-icon v-else-if="row.status === 'done'" class="status-icon"><CircleCheckFilled /></el-icon>
              <el-icon v-else-if="row.status === 'failed'" class="status-icon"><CircleCloseFilled /></el-icon>
              <el-icon v-else-if="row.status === 'cancelled'" class="status-icon"><VideoPause /></el-icon>
              <el-icon v-else class="status-icon"><Clock /></el-icon>
              <span class="status-label">{{ statusLabel(row.status) }}</span>
            </span>
          </template>
        </el-table-column>

        <el-table-column label="进度" width="160">
          <template #default="{ row }">
            <div class="progress-cell">
              <div class="progress-bar">
                <div
                  class="progress-fill"
                  :class="`progress-${row.status}`"
                  :style="{ width: `${progressPct(row)}%` }"
                />
              </div>
              <div class="progress-text mono">
                <span class="page-num">{{ row.progress_pages || 0 }}</span>
                <span class="page-sep">/</span>
                <span class="page-total">{{ row.max_pages || '∞' }}</span>
                <span class="page-unit">页</span>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="发现 → 入库" width="130" align="right">
          <template #default="{ row }">
            <div class="pipeline mono">
              <span class="pipe-found">{{ formatNum(row.progress_posts || 0) }}</span>
              <span class="pipe-arrow">→</span>
              <span class="pipe-saved">{{ formatNum(row.posts_saved || 0) }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="开始" width="128">
          <template #default="{ row }">
            <div class="time-cell">
              <span class="time-date mono">{{ formatDate(row.started_at) }}</span>
              <span class="time-clock mono">{{ formatClock(row.started_at) }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="结束 / 耗时" width="132">
          <template #default="{ row }">
            <div class="time-cell">
              <span v-if="row.finished_at" class="time-date mono">{{ formatDate(row.finished_at) }}</span>
              <span v-else class="time-running">
                <span class="running-dot" />
                进行中
              </span>
              <span class="time-clock mono duration">{{ formatDuration(row) }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="error" label="备注" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error" class="error-cell" :class="`error-${row.status}`">
              {{ row.error }}
            </span>
            <span v-else-if="row.status === 'done'" class="error-ok">✓ 完成</span>
            <span v-else class="error-empty">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 日志卡片：终端风格 -->
    <el-card class="log-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span class="terminal-dots">
              <span class="dot red" />
              <span class="dot yellow" />
              <span class="dot green" />
            </span>
            <span class="header-title">任务运行日志</span>
            <span v-if="selectedJobId" class="job-badge">
              <span class="job-badge-label">job</span>
              <span class="job-badge-num">#{{ selectedJobId }}</span>
            </span>
            <span v-else class="header-hint">← 点击上方任一行查看对应日志</span>
          </div>
          <div class="header-right">
            <el-button
              v-if="selectedJobId !== null && selectedJobId !== latestJobId"
              size="small"
              plain
              @click="selectJob(latestJobId)"
              class="back-button"
            >
              <el-icon style="margin-right: 4px"><TopRight /></el-icon>回到最新
            </el-button>
            <el-select
              :model-value="selectedJobId ?? latestJobId"
              size="small"
              placeholder="切换 job"
              class="job-select"
              @change="onJobChange"
            >
              <el-option
                v-for="j in jobs"
                :key="j.id"
                :label="`job#${j.id} · ${j.status}`"
                :value="j.id"
              />
            </el-select>
          </div>
        </div>
      </template>

      <div v-if="!recentLog.length" class="log-empty">
        <span class="terminal-prompt">$</span> 该 job 暂无日志
      </div>
      <div v-else class="log-stream">
        <div
          v-for="(line, i) in recentLog"
          :key="i"
          class="log-line"
        >
          <span class="log-ts">[{{ line.ts }}]</span>
          <span class="log-job">[job#{{ line.jobId }}]</span>
          <span class="log-msg">{{ line.msg }}</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Refresh, TopRight, Loading, CircleCheckFilled, CircleCloseFilled, VideoPause, Clock } from '@element-plus/icons-vue'
import { tasksApi, type Job } from '@/api'

const route = useRoute()
const taskId = computed(() => {
  const raw = route.params.id
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : 0
})
const jobs = ref<Job[]>([])
const loading = ref(false)
const loadError = ref('')
// 用户当前选中的 job；null = 显示最新；切换后保留选择
const selectedJobId = ref<number | null>(null)
let timer: any = null

const latestJobId = computed(() => {
  if (!jobs.value.length) return 0
  return jobs.value.reduce((max, j) => (j.id > max ? j.id : max), 0)
})

const recentLog = computed(() => {
  if (!jobs.value.length) return []
  // 如果用户选了某个 jobId，只看这个 job 的日志；否则看最新的那个
  const targetId = selectedJobId.value ?? latestJobId.value
  if (!targetId) return []
  const job = jobs.value.find((j) => j.id === targetId)
  if (!job) return []
  const log = Array.isArray(job.log) ? job.log : []
  // 倒序：最新日志在最上方
  return log
    .slice()
    .reverse()
    .map((line: any) => ({
      ts: line?.ts || '',
      msg: line?.msg || '',
      jobId: job.id,
    }))
})

function rowClassName({ row }: { row: Job }) {
  if (row.id === (selectedJobId.value ?? latestJobId.value)) {
    return 'is-selected-row'
  }
  return ''
}

function onJobClick(row: Job) {
  selectJob(row.id)
}

function selectJob(id: number | null) {
  selectedJobId.value = id
}

function onJobChange(id: number) {
  selectedJobId.value = id
}

/* ===================== 格式化 helpers ===================== */
function statusLabel(s: string): string {
  return ({
    running: '运行中',
    done: '完成',
    failed: '失败',
    cancelled: '已取消',
    pending: '等待',
  } as Record<string, string>)[s] || s
}

function progressPct(row: Job): number {
  const max = row.max_pages || 0
  if (!max) return row.status === 'running' ? 8 : (row.progress_pages ? 100 : 0)
  return Math.min(100, Math.round(((row.progress_pages || 0) / max) * 100))
}

function formatNum(n: number): string {
  return n.toLocaleString('en-US')
}

// "2026-09-30T03:41:53.0..." → "09-30"
function formatDate(iso?: string | null): string {
  if (!iso) return '—'
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/)
  return m ? `${m[2]}-${m[3]}` : iso
}

// "2026-09-30T03:41:53.0..." → "03:41:53"
function formatClock(iso?: string | null): string {
  if (!iso) return '—'
  const m = iso.match(/T(\d{2}:\d{2}:\d{2})/)
  return m ? m[1] : iso
}

// "进行中 02:14" / "01:02:49" / "—"
function formatDuration(row: Job): string {
  if (!row.started_at) return '—'
  const start = new Date(row.started_at).getTime()
  const end = row.finished_at ? new Date(row.finished_at).getTime() : Date.now()
  if (isNaN(start) || isNaN(end) || end < start) return '—'
  let sec = Math.floor((end - start) / 1000)
  const h = Math.floor(sec / 3600); sec -= h * 3600
  const m = Math.floor(sec / 60); sec -= m * 60
  const running = !row.finished_at
  if (h > 0) return running ? `${h}h ${m}m` : `${h}h ${m}m ${sec}s`
  if (m > 0) return running ? `${m}m ${sec}s` : `${m}m ${sec}s`
  return `${sec}s`
}

// 当 task 切换或 jobs 列表更新，且当前没选 job 时，自动选最新
watch(jobs, (newJobs) => {
  if (!newJobs.length) {
    selectedJobId.value = null
    return
  }
  // 如果当前选中的 job 已经不存在（被清理），重置为最新
  if (selectedJobId.value && !newJobs.find((j) => j.id === selectedJobId.value)) {
    selectedJobId.value = null
  }
})

async function refresh() {
  if (!taskId.value) {
    loadError.value = `URL 缺少有效 task_id（参数=${String(route.params.id)}）`
    jobs.value = []
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    const rows = await tasksApi.listJobs(taskId.value)
    jobs.value = Array.isArray(rows) ? rows : []
    if (!jobs.value.length) {
      loadError.value = `任务 #${taskId.value} 暂无运行记录。可能原因：1) 任务太新还没跑；2) 历史 jobs 已被清理；3) task_id 错误。`
    }
  } catch (e: any) {
    jobs.value = []
    loadError.value = `加载运行记录失败：${e?.response?.data?.detail || e?.message || e}`
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 3000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<style scoped>
.task-jobs-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  width: 100%;
  min-width: 0;
}
/* 子组件 root element 同时带本组件的 data-v-xxx，可直接命中 */
.task-jobs-page > .jobs-card,
.task-jobs-page > .log-card {
  width: 100% !important;
  max-width: none !important;
  align-self: stretch;
  display: flex;
  flex-direction: column;
}
/* 穿透到子组件内部的 el-card 元素 */
.task-jobs-page :deep(.el-card__body) {
  width: 100%;
  flex: 1 1 auto;
}
.task-jobs-page :deep(.el-table) {
  width: 100% !important;
}
.task-jobs-page :deep(.el-table__inner-wrapper) {
  width: 100% !important;
  min-width: 0 !important;
}

/* ============ 通用 header ============ */
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 4px 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.header-title {
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 600;
  color: var(--color-foreground);
  letter-spacing: 0.2px;
}
.header-count {
  font-family: var(--font-heading);
  font-size: 12px;
  color: var(--color-muted-foreground);
  padding: 3px 10px;
  background: var(--color-muted);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.header-hint {
  font-size: 12px;
  color: var(--color-muted-foreground);
  font-style: italic;
}
.task-tag {
  background: rgba(34, 197, 94, 0.12) !important;
  border-color: rgba(34, 197, 94, 0.3) !important;
  color: var(--color-accent) !important;
  font-family: var(--font-heading);
  font-weight: 500;
}

/* ============ jobs 卡片 ============ */
.jobs-card :deep(.el-card__header) {
  background: linear-gradient(180deg, var(--color-card) 0%, rgba(27, 35, 54, 0.4) 100%);
  border-bottom: 1px solid rgba(34, 197, 94, 0.12);
  padding: 14px 20px;
}
.jobs-card :deep(.el-card__body) {
  padding: 16px 20px 20px;
}
.error-alert {
  margin-bottom: 14px;
}
.error-alert :deep(.el-alert__title) {
  font-family: var(--font-heading);
  font-size: 12px;
}

.jobs-table :deep(th.el-table__cell) {
  background: rgba(255, 255, 255, 0.02) !important;
  border-bottom: 1px solid rgba(34, 197, 94, 0.15) !important;
}
/* 选中行：整行统一绿色调，覆盖单元格 stripe + hover */
.jobs-table :deep(tr.is-selected-row) {
  background: rgba(34, 197, 94, 0.08) !important;
  box-shadow: inset 3px 0 0 var(--color-accent);
}
.jobs-table :deep(tr.is-selected-row td.el-table__cell) {
  background: transparent !important;
  border-bottom-color: rgba(34, 197, 94, 0.18) !important;
}
.jobs-table :deep(tr.is-selected-row:hover) {
  background: rgba(34, 197, 94, 0.12) !important;
}
.jobs-table :deep(tr.is-selected-row:hover td.el-table__cell) {
  background: transparent !important;
}
/* hover 行：整行统一浅色 */
.jobs-table :deep(tbody tr:hover) {
  background: rgba(34, 197, 94, 0.04) !important;
}
.jobs-table :deep(tbody tr:hover td.el-table__cell) {
  background: transparent !important;
}
.jobs-table :deep(td.el-table__cell) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.04) !important;
  transition: background 0.15s ease;
}
.jobs-table :deep(table) {
  table-layout: fixed !important;
  width: 100% !important;
}

.mono {
  font-family: var(--font-heading);
}
.job-id {
  color: var(--color-accent);
  font-weight: 500;
}

/* ===================== 时间 cell ===================== */
.time-cell {
  display: flex;
  flex-direction: column;
  gap: 1px;
  line-height: 1.25;
}
.time-date {
  color: var(--color-foreground);
  font-size: 11.5px;
  font-weight: 500;
}
.time-clock {
  color: var(--color-muted-foreground);
  font-size: 10.5px;
  letter-spacing: 0.2px;
}
.time-clock.duration {
  color: var(--color-accent);
  opacity: 0.85;
  font-size: 10.5px;
}
.time-running {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #eab308;
  font-size: 11.5px;
  font-weight: 500;
}
.running-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #eab308;
  box-shadow: 0 0 8px #eab308;
  animation: pulse-dot 1.6s ease-in-out infinite;
}
@keyframes pulse-dot {
  0%, 100% { transform: scale(1); opacity: 1; }
  50%      { transform: scale(1.4); opacity: 0.55; }
}

/* ===================== 进度 cell ===================== */
.progress-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}
.progress-bar {
  height: 4px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 2px;
  overflow: hidden;
  position: relative;
}
.progress-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s ease;
}
.progress-running {
  background: linear-gradient(90deg, #eab308 0%, #fde047 100%);
  box-shadow: 0 0 8px rgba(234, 179, 8, 0.5);
}
.progress-done {
  background: linear-gradient(90deg, var(--color-accent) 0%, #4ade80 100%);
}
.progress-failed {
  background: linear-gradient(90deg, #ef4444 0%, #f87171 100%);
}
.progress-cancelled {
  background: linear-gradient(90deg, #94a3b8 0%, #cbd5e1 100%);
}
.progress-pending {
  background: rgba(148, 163, 184, 0.3);
}
.progress-text {
  display: flex;
  align-items: baseline;
  gap: 3px;
  font-size: 10.5px;
  color: var(--color-muted-foreground);
}
.page-num { color: var(--color-foreground); font-weight: 600; }
.page-sep { opacity: 0.4; }
.page-total { color: var(--color-muted-foreground); }
.page-unit { margin-left: 1px; opacity: 0.65; }

/* ===================== 发现 → 入库 ===================== */
.pipeline {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
}
.pipe-found {
  color: var(--color-muted-foreground);
}
.pipe-arrow {
  color: var(--color-accent);
  opacity: 0.5;
  font-size: 11px;
  margin: 0 1px;
}
.pipe-saved {
  color: var(--color-accent);
  font-weight: 600;
}

/* ===================== 错误/备注 ===================== */
.error-cell {
  font-size: 12px;
  font-family: var(--font-heading);
  max-width: 100%;
  display: inline-block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
.error-cancelled {
  color: var(--color-muted-foreground);
  font-style: italic;
  opacity: 0.75;
}
.error-failed {
  color: #ef4444;
  font-weight: 500;
}
.error-running {
  color: #eab308;
  font-style: italic;
}
.error-ok {
  color: var(--color-accent);
  font-size: 12px;
  font-weight: 500;
}
.error-empty {
  color: var(--color-muted-foreground);
  opacity: 0.4;
}

/* ===================== 状态 pill ===================== */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 10px;
  font-family: var(--font-heading);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.2px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--color-muted-foreground);
  border: 1px solid rgba(255, 255, 255, 0.06);
  white-space: nowrap;
}
.status-icon {
  font-size: 11px;
  display: inline-flex;
}
.status-label { line-height: 1; }
.spin {
  animation: spin 1.2s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
.status-running {
  background: rgba(234, 179, 8, 0.14);
  border-color: rgba(234, 179, 8, 0.32);
  color: #fde047;
}
.status-done {
  background: rgba(34, 197, 94, 0.14);
  border-color: rgba(34, 197, 94, 0.32);
  color: var(--color-accent);
}
.status-failed {
  background: rgba(239, 68, 68, 0.14);
  border-color: rgba(239, 68, 68, 0.32);
  color: #f87171;
}
.status-cancelled {
  background: rgba(148, 163, 184, 0.12);
  border-color: rgba(148, 163, 184, 0.28);
  color: #cbd5e1;
}
.status-pending,
.status-info {
  background: rgba(148, 163, 184, 0.1);
  border-color: rgba(148, 163, 184, 0.3);
  color: #94a3b8;
}

/* ============ 日志卡片（终端风格） ============ */
.log-card {
  position: relative;
}
.log-card :deep(.el-card__header) {
  background: linear-gradient(180deg, var(--color-card) 0%, rgba(27, 35, 54, 0.4) 100%);
  border-bottom: 1px solid rgba(34, 197, 94, 0.12);
  padding: 14px 20px;
}
.log-card :deep(.el-card__body) {
  padding: 0;
}

.terminal-dots {
  display: inline-flex;
  gap: 6px;
  margin-right: 4px;
}
.terminal-dots .dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.terminal-dots .red { background: #ff5f57; }
.terminal-dots .yellow { background: #febc2e; }
.terminal-dots .green { background: #28c840; }

.job-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  border-radius: 6px;
  font-family: var(--font-heading);
  font-size: 12px;
}
.job-badge-label {
  color: var(--color-muted-foreground);
}
.job-badge-num {
  color: var(--color-accent);
  font-weight: 600;
}

.job-select {
  width: 180px;
}
.job-select :deep(.el-input__wrapper) {
  background: var(--color-muted);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
}
.back-button {
  border-color: rgba(34, 197, 94, 0.3);
  color: var(--color-accent);
}
.back-button:hover {
  background: rgba(34, 197, 94, 0.08);
  border-color: var(--color-accent);
}

/* ============ 日志流 ============ */
.log-stream {
  font-family: var(--font-heading);
  font-size: 12.5px;
  line-height: 1.7;
  background: rgba(0, 0, 0, 0.25);
  padding: 16px 20px 18px;
  max-height: 520px;
  overflow-y: auto;
  border-top: 1px solid rgba(34, 197, 94, 0.08);
}
.log-stream::-webkit-scrollbar {
  width: 6px;
}
.log-stream::-webkit-scrollbar-thumb {
  background: rgba(34, 197, 94, 0.2);
  border-radius: 3px;
}

.log-empty {
  padding: 24px 20px;
  font-family: var(--font-heading);
  font-size: 13px;
  color: var(--color-muted-foreground);
  background: rgba(0, 0, 0, 0.2);
}
.terminal-prompt {
  color: var(--color-accent);
  margin-right: 8px;
  font-weight: 600;
}

.log-line {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 1px 0;
  word-break: break-word;
}
.log-ts {
  color: #64748b;
  font-size: 11.5px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.log-job {
  color: var(--color-accent);
  font-size: 11.5px;
  flex-shrink: 0;
  font-weight: 500;
}
.log-msg {
  color: #cbd5e1;
  flex: 1;
  min-width: 0;
}
</style>