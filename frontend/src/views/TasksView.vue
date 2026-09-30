<template>
  <div class="tasks-view">
    <div class="glass-card">
      <!-- 头部 -->
      <div class="table-header">
        <div class="header-left">
          <el-icon class="header-icon"><Operation /></el-icon>
          <span class="header-title">采集任务</span>
          <span v-if="store.tasks.length" class="header-count">
            {{ store.tasks.length }} 个 ·
            <span class="active-count">{{ runningCount }} 运行中</span>
          </span>
        </div>
        <div class="header-right">
          <el-button @click="store.fetch()" :loading="store.loading" plain>
            <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
          </el-button>
          <el-button type="primary" @click="openCreate">
            <el-icon style="margin-right: 4px"><Plus /></el-icon>新建任务
          </el-button>
        </div>
      </div>

      <!-- 表格 -->
      <el-table
        :data="store.tasks"
        v-loading="store.loading"
        empty-text="暂无任务 — 点击右上「新建任务」开始"
        class="dark-table tasks-table"
        style="width: 100%"
        :cell-style="{ verticalAlign: 'middle' }"
      >
        <el-table-column prop="id" label="#" width="56">
          <template #default="{ row }">
            <span class="row-id mono">#{{ row.id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="站点" width="140">
          <template #default="{ row }">
            <div v-if="row.site_ids?.length" class="site-tags">
              <span v-for="sid in row.site_ids.slice(0, 2)" :key="sid" class="site-tag">
                {{ siteName(sid) }}
              </span>
              <span v-if="row.site_ids.length > 2" class="site-tag-more">+{{ row.site_ids.length - 2 }}</span>
            </div>
            <span v-else class="text-muted">无</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="任务名" min-width="140" width="180">
          <template #default="{ row }">
            <span class="task-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="kind" label="类型" width="82">
          <template #default="{ row }">
            <span class="kind-chip">{{ kindText(row.kind) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关键字 / 日期" min-width="140" width="168">
          <template #default="{ row }">
            <div class="task-params">
              <span v-if="row.keyword" class="param-item">
                <el-icon><Search /></el-icon>{{ row.keyword }}
              </span>
              <span v-if="row.date_from || row.date_to" class="param-item">
                <el-icon><Calendar /></el-icon>
                {{ row.date_from || '...' }} ~ {{ row.date_to || '...' }}
              </span>
              <span v-if="row.category" class="param-item">
                <el-icon><Folder /></el-icon>{{ row.category }}
              </span>
              <span v-if="!row.keyword && !row.date_from && !row.date_to && !row.category" class="text-muted">—</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="max_pages" label="页" width="50" align="center">
          <template #default="{ row }">
            <span class="mono metric">{{ row.max_pages }}</span>
          </template>
        </el-table-column>
        <el-table-column label="定时" width="120">
          <template #default="{ row }">
            <div class="schedule-info">
              <span v-if="row.schedule_enabled && row.cron" class="cron-chip">
                <el-icon><Clock /></el-icon>{{ row.cron }}
              </span>
              <span v-else class="cron-none">未启用</span>
              <span v-if="row.schedule_enabled && row.next_run_at" class="next-run mono">
                下次 {{ formatTime(row.next_run_at) }}
              </span>
              <span v-else-if="row.last_run_at" class="last-run mono">
                上次 {{ formatTime(row.last_run_at) }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="172" align="center">
          <template #default="{ row }">
            <div class="action-group">
              <el-tooltip
                v-if="!row.running_job_id"
                content="启动"
                placement="top"
                :show-after="200"
              >
                <button
                  class="icon-btn icon-btn-run"
                  :class="{ 'is-loading': runningId === row.id }"
                  :disabled="runningId === row.id"
                  @click="runNow(row)"
                  aria-label="启动"
                >
                  <el-icon><VideoPlay /></el-icon>
                </button>
              </el-tooltip>
              <el-tooltip
                v-else
                content="停止"
                placement="top"
                :show-after="200"
              >
                <button
                  class="icon-btn icon-btn-stop"
                  :class="{ 'is-loading': stoppingId === row.id }"
                  :disabled="stoppingId === row.id"
                  @click="stopNow(row)"
                  aria-label="停止"
                >
                  <el-icon><VideoPause /></el-icon>
                </button>
              </el-tooltip>
              <el-tooltip content="编辑" placement="top" :show-after="200">
                <button class="icon-btn icon-btn-edit" @click="openEdit(row)" aria-label="编辑">
                  <el-icon><Edit /></el-icon>
                </button>
              </el-tooltip>
              <el-tooltip content="记录" placement="top" :show-after="200">
                <button class="icon-btn icon-btn-jobs" @click="$router.push(`/tasks/${row.id}/jobs`)" aria-label="记录">
                  <el-icon><Document /></el-icon>
                </button>
              </el-tooltip>
              <el-popconfirm
                :title="`确认删除「${row.name}」？`"
                confirm-button-text="删除"
                cancel-button-text="取消"
                trigger="click"
                @confirm="remove(row)"
              >
                <template #reference>
                  <button class="icon-btn icon-btn-delete" aria-label="删除">
                    <el-icon><Delete /></el-icon>
                  </button>
                </template>
              </el-popconfirm>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="store.tasks.length" class="table-footer">
        <span class="footer-item">
          <span class="footer-dot running" />
          运行中 {{ runningCount }}
        </span>
        <span class="footer-divider" />
        <span class="footer-item">共 {{ store.tasks.length }} 个任务</span>
        <span class="footer-spacer" />
        <span class="footer-hint">操作列含启动/停止/编辑/记录/删除</span>
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑采集任务' : '新建采集任务'" width="660px" class="task-dialog">
      <el-form :model="form" label-width="110px" class="task-form">
        <el-form-item label="站点（多选）">
          <el-select
            v-model="form.site_ids"
            multiple
            placeholder="选择 1 个或多个站点，一次采集全部覆盖"
            style="width: 100%"
            :disabled="editing"
          >
            <el-option v-for="s in sites" :key="s.id" :label="`${s.name} (${s.host})`" :value="s.id" />
          </el-select>
          <div class="form-hint">已选 <b>{{ form.site_ids?.length || 0 }}</b> 个站点：{{ selectedSiteNames || '（无）' }}</div>
        </el-form-item>
        <el-form-item label="任务名">
          <el-input v-model="form.name" placeholder="如：每日福利" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.kind" style="width: 100%" :disabled="editing">
            <el-option label="全部列表（按页）" value="list_all" />
            <el-option label="按关键字搜索" value="list_search" />
            <el-option label="按日期归档" value="list_date" />
            <el-option label="按分类" value="list_category" />
          </el-select>
          <div class="form-hint">色花堂等论坛站的板块 FID / 多 URL 入口，请在「站点配置」里设置</div>
        </el-form-item>
        <el-form-item v-if="form.kind === 'list_search'" label="关键字">
          <el-input v-model="form.keyword" placeholder="搜索关键字" />
        </el-form-item>
        <template v-if="form.kind === 'list_date'">
          <el-form-item label="起始日期">
            <el-date-picker v-model="form.date_from" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
          <el-form-item label="结束日期">
            <el-date-picker v-model="form.date_to" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </template>
        <el-form-item v-if="form.kind === 'list_category'" label="分类 slug">
          <el-input v-model="form.category" placeholder="如 daily / fuli / acg" />
        </el-form-item>
        <el-form-item label="最大页数">
          <el-input-number v-model="form.max_pages" :min="1" :max="500" />
        </el-form-item>
        <el-form-item label="并发数">
          <el-input-number v-model="form.max_concurrent" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="仅保留有链接">
          <el-switch v-model="form.only_with_links" />
        </el-form-item>

        <el-divider content-position="left">定时采集（可选）</el-divider>

        <el-form-item label="启用定时">
          <el-switch v-model="form.schedule_enabled" />
          <span class="form-hint-inline">开启后按 cron 自动采集</span>
        </el-form-item>
        <el-form-item label="Cron 表达式">
          <el-input
            v-model="form.cron"
            placeholder="例如：0 3 * * *（每天 03:00）"
            :disabled="!form.schedule_enabled"
          />
          <div class="form-hint">
            5 字段格式：分 时 日 月 周。例如 <code>0 3 * * *</code>=每天 03:00，<code>*/30 * * * *</code>=每 30 分钟
          </div>
        </el-form-item>
        <el-form-item label="Job 名模板">
          <el-input v-model="form.name_template" placeholder="{task} {ymd}" />
          <div class="form-hint">
            占位符：<code>{task}</code>=任务名 <code>{date}</code>=YYYY-MM-DD <code>{ymd}</code>=YYYYMMDD<br />
            例：<code>{task}-{ymd}</code> → "每日福利-20260913"
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Operation, Plus, Search, Calendar, Folder, Clock, VideoPlay, VideoPause, Refresh, Edit, Document, Delete } from '@element-plus/icons-vue'
import { useSiteStore } from '@/stores/sites'
import { useTaskStore } from '@/stores/tasks'
import type { Task, TaskCreate, TaskUpdate } from '@/api'

const store = useTaskStore()
const sitesStore = useSiteStore()
const sites = computed(() => sitesStore.sites)

const runningCount = computed(
  () => store.tasks.filter((t) => t.running_job_id).length,
)

const selectedSiteNames = computed(() => {
  const ids = form.site_ids || []
  const names = ids
    .map((id) => sites.value.find((x) => x.id === id))
    .filter((s): s is NonNullable<typeof s> => s != null)
    .map((s) => `${s.name} (${s.host})`)
  return names.join(' / ')
})

const dialogVisible = ref(false)
const editing = ref<Task | null>(null)
const runningId = ref<number | null>(null)
const stoppingId = ref<number | null>(null)
let pollTimer: any = null

const form = reactive<TaskCreate>({
  site_ids: [],
  name: '',
  kind: 'list_all',
  keyword: '',
  date_from: undefined as any,
  date_to: undefined as any,
  category: '',
  max_pages: 10,
  max_concurrent: 3,
  only_with_links: true,
  cron: '',
  schedule_enabled: false,
  name_template: '',
})

function resetForm() {
  Object.assign(form, {
    site_ids: [],
    name: '',
    kind: 'list_all',
    keyword: '',
    date_from: undefined,
    date_to: undefined,
    category: '',
    max_pages: 10,
    max_concurrent: 3,
    only_with_links: true,
    cron: '',
    schedule_enabled: false,
    name_template: '',
  })
}

function openCreate() {
  editing.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: Task) {
  editing.value = row
  Object.assign(form, {
    site_ids: Array.isArray(row.site_ids) ? [...row.site_ids] : [],
    name: row.name,
    kind: row.kind,
    keyword: row.keyword || '',
    date_from: row.date_from || undefined,
    date_to: row.date_to || undefined,
    category: row.category || '',
    max_pages: row.max_pages,
    max_concurrent: row.max_concurrent,
    only_with_links: row.only_with_links,
    cron: row.cron || '',
    schedule_enabled: row.schedule_enabled,
    name_template: row.name_template || '',
  })
  dialogVisible.value = true
}

async function submit() {
  if (!form.site_ids?.length) return ElMessage.warning('请至少选择一个站点')
  if (!form.name) return ElMessage.warning('请填写任务名')
  if (form.schedule_enabled && !form.cron) {
    return ElMessage.warning('启用定时必须填写 Cron 表达式')
  }
  try {
    if (editing.value) {
      const payload: TaskUpdate = {
        site_ids: [...form.site_ids],
        name: form.name,
        kind: form.kind,
        keyword: form.keyword || null,
        date_from: form.date_from || null,
        date_to: form.date_to || null,
        category: form.category || null,
        max_pages: form.max_pages,
        max_concurrent: form.max_concurrent,
        only_with_links: form.only_with_links,
        cron: form.cron || null,
        schedule_enabled: form.schedule_enabled,
        name_template: form.name_template || null,
      }
      await store.update(editing.value.id, payload, form.site_ids[0])
      ElMessage.success('已更新')
    } else {
      await store.create({ ...form })
      ElMessage.success('已创建')
    }
    dialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

async function runNow(row: Task) {
  runningId.value = row.id
  // 乐观更新：先把按钮切到「停止」态，等下次 fetch 校正
  row.running_job_id = -1
  try {
    await store.run(row.id, row.site_ids?.[0])
    ElMessage.success('已提交后台任务')
    await store.fetch()
  } catch (e: any) {
    row.running_job_id = undefined
    ElMessage.error(e.message)
  } finally {
    runningId.value = null
  }
}

async function stopNow(row: Task) {
  stoppingId.value = row.id
  try {
    const r = await store.stop(row.id, row.site_ids?.[0])
    if (r.ok) {
      // 乐观更新：立刻清掉 running_job_id，按钮切回「启动」
      row.running_job_id = undefined
      ElMessage.success(`已停止（job_id=${r.job_id}）`)
      await store.fetch()
    } else {
      ElMessage.warning(r.msg || '当前没有正在运行的 Job')
    }
  } catch (e: any) {
    ElMessage.error(`停止失败：${e?.message || e}`)
  } finally {
    stoppingId.value = null
  }
}

async function remove(row: Task) {
  await store.remove(row.id, row.site_ids?.[0])
  ElMessage.success('已删除')
}

function siteName(id?: number) {
  if (id == null) return '-'
  const s = sites.value.find((x) => x.id === id)
  return s ? `${s.name}` : `#${id}`
}

function kindText(kind: string) {
  const map: Record<string, string> = {
    list_all: '全部列表',
    list_search: '关键字搜索',
    list_date: '日期归档',
    list_category: '分类',
  }
  return map[kind] || kind
}

function formatTime(s: string) {
  if (!s) return ''
  return s.replace('T', ' ').slice(0, 16)
}

onMounted(async () => {
  await sitesStore.fetch()
  await store.fetch()
  pollTimer = setInterval(() => store.fetch(), 3000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.tasks-view {
  width: 100%;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.tasks-view > .glass-card {
  padding: 0;
  overflow: hidden;
  width: 100%;
  display: flex;
  flex-direction: column;
}

.tasks-view > .glass-card > .el-table,
.tasks-view > .glass-card .dark-table {
  width: 100% !important;
  flex: 1 1 auto;
}

.tasks-view > .glass-card .el-table__inner-wrapper,
.tasks-view > .glass-card .el-table__body-wrapper {
  width: 100% !important;
}

.tasks-view > .glass-card .el-table__header-wrapper table,
.tasks-view > .glass-card .el-table__body-wrapper table {
  width: 100% !important;
}

/* ============ 头部 ============ */
.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  gap: 16px;
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
.header-icon {
  font-size: 20px;
  color: var(--color-accent);
}
.header-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-foreground);
  letter-spacing: 0.2px;
  font-family: var(--font-heading);
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
.active-count {
  color: var(--color-accent);
  font-weight: 500;
}

/* ============ 表格 ============ */
.dark-table {
  padding: 0;
}
.dark-table :deep(.el-table__header-wrapper th) {
  background: rgba(255, 255, 255, 0.025) !important;
  color: var(--color-muted-foreground);
  font-weight: 500;
  font-size: 12px;
  letter-spacing: 0.3px;
  text-transform: uppercase;
  border: none !important;
  padding: 12px 12px;
}
.dark-table :deep(.el-table__body-wrapper td) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.04) !important;
  padding: 14px 12px;
  vertical-align: middle;
}

/* 关键：让 el-table 严格按 width 分配列宽，不被内容撑开 */
.dark-table :deep(table) {
  table-layout: fixed !important;
  width: 100% !important;
}
.dark-table :deep(colgroup col) {
  width: auto !important;
}
.dark-table :deep(.el-table__body-wrapper tr:hover td) {
  background: rgba(34, 197, 94, 0.04) !important;
}

/* ============ 字段 ============ */
.row-id {
  font-family: var(--font-heading);
  font-size: 12px;
  color: var(--color-muted-foreground);
}
.task-name {
  font-weight: 600;
  color: var(--color-foreground);
  font-size: 14px;
}
.mono {
  font-family: var(--font-heading);
}
.metric {
  color: var(--color-foreground);
  font-size: 13px;
}

.site-tags {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
}
.site-tag {
  font-size: 11px;
  padding: 2px 8px;
  background: rgba(34, 197, 94, 0.1);
  color: var(--color-accent);
  border: 1px solid rgba(34, 197, 94, 0.2);
  border-radius: 4px;
  font-weight: 500;
  font-family: var(--font-heading);
}
.site-tag-more {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--color-muted);
  color: var(--color-muted-foreground);
  border-radius: 4px;
}

/* 类型 chip */
.kind-chip {
  font-size: 11.5px;
  padding: 3px 9px;
  background: var(--color-muted);
  color: var(--color-muted-foreground);
  border-radius: 12px;
  font-weight: 500;
  font-family: var(--font-heading);
  letter-spacing: 0.2px;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

/* 任务参数 */
.task-params {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.param-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-muted-foreground);
}
.param-item .el-icon {
  font-size: 13px;
  opacity: 0.8;
}

/* 定时 */
.schedule-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cron-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-family: var(--font-heading);
  padding: 2px 8px;
  background: rgba(34, 197, 94, 0.1);
  color: var(--color-accent);
  border: 1px solid rgba(34, 197, 94, 0.25);
  border-radius: 10px;
  font-weight: 500;
  width: fit-content;
}
.cron-chip .el-icon {
  font-size: 12px;
}
.cron-none {
  font-size: 12px;
  color: var(--color-muted-foreground);
}
.next-run,
.last-run {
  font-size: 11px;
  color: var(--color-muted-foreground);
}

/* ============ 操作 icon 组 ============ */
.action-group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  justify-content: center;
}
.icon-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--color-muted-foreground);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
  font-size: 14px;
  transition: all 0.15s ease;
}
.icon-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.08);
}
.icon-btn:focus-visible {
  outline: 2px solid rgba(34, 197, 94, 0.4);
  outline-offset: 1px;
}
.icon-btn:disabled,
.icon-btn.is-loading {
  cursor: not-allowed;
  opacity: 0.5;
}
.icon-btn .el-icon {
  font-size: 14px;
}
.icon-btn-run {
  color: var(--color-accent);
}
.icon-btn-run:hover {
  background: rgba(34, 197, 94, 0.12);
  border-color: rgba(34, 197, 94, 0.4);
  color: var(--color-accent);
  box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.08);
}
.icon-btn-stop {
  color: #eab308;
}
.icon-btn-stop:hover {
  background: rgba(234, 179, 8, 0.12);
  border-color: rgba(234, 179, 8, 0.4);
  color: #fbbf24;
  box-shadow: 0 0 0 2px rgba(234, 179, 8, 0.08);
}
.icon-btn-edit {
  color: #60a5fa;
}
.icon-btn-edit:hover {
  background: rgba(96, 165, 250, 0.12);
  border-color: rgba(96, 165, 250, 0.4);
  color: #93c5fd;
}
.icon-btn-jobs {
  color: #a78bfa;
}
.icon-btn-jobs:hover {
  background: rgba(167, 139, 250, 0.12);
  border-color: rgba(167, 139, 250, 0.4);
  color: #c4b5fd;
}
.icon-btn-delete {
  color: #f87171;
}
.icon-btn-delete:hover {
  background: rgba(239, 68, 68, 0.14);
  border-color: rgba(239, 68, 68, 0.45);
  color: #fca5a5;
  box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.08);
}

/* ============ footer ============ */
.table-footer {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.04);
  background: rgba(0, 0, 0, 0.15);
  font-family: var(--font-heading);
  font-size: 12px;
  color: var(--color-muted-foreground);
}
.footer-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.footer-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.footer-dot.running {
  background: #eab308;
  box-shadow: 0 0 6px #eab308;
}
.footer-divider {
  width: 1px;
  height: 12px;
  background: rgba(255, 255, 255, 0.08);
}
.footer-spacer {
  flex: 1;
}
.footer-hint {
  font-style: italic;
  color: var(--color-muted-foreground);
  opacity: 0.7;
}

/* ============ 弹窗 ============ */
.task-dialog :deep(.el-dialog__header) {
  padding: 18px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.task-dialog :deep(.el-dialog__body) {
  padding: 22px 24px;
}
.task-dialog :deep(.el-dialog__footer) {
  padding: 14px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.form-hint {
  font-size: 12px;
  color: var(--color-muted-foreground);
  line-height: 1.5;
  margin-top: 6px;
}
.form-hint code {
  background: var(--color-muted);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-heading);
  font-size: 11px;
  color: var(--color-accent);
}
.form-hint-inline {
  font-size: 12px;
  color: var(--color-muted-foreground);
  margin-left: 12px;
}
</style>
