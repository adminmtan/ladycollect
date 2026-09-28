<template>
  <div class="tasks-view">
    <div class="glass-card">
      <!-- 头部 -->
      <div class="table-header">
        <div class="header-title">
          <el-icon><Operation /></el-icon>
          <span>采集任务</span>
        </div>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新建任务
        </el-button>
      </div>

      <!-- 表格 -->
      <el-table :data="store.tasks" v-loading="store.loading" empty-text="暂无任务" class="dark-table">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="站点" width="180">
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
        <el-table-column prop="name" label="任务名">
          <template #default="{ row }">
            <span class="task-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="kind" label="类型" width="140">
          <template #default="{ row }">
            <span class="kind-badge">{{ kindText(row.kind) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关键字 / 日期 / 分类" width="220">
          <template #default="{ row }">
            <div class="task-params">
              <span v-if="row.keyword" class="param-item">
                <el-icon><Search /></el-icon>
                {{ row.keyword }}
              </span>
              <span v-if="row.date_from || row.date_to" class="param-item">
                <el-icon><Calendar /></el-icon>
                {{ row.date_from || '...' }} ~ {{ row.date_to || '...' }}
              </span>
              <span v-if="row.category" class="param-item">
                <el-icon><Folder /></el-icon>
                {{ row.category }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="max_pages" label="页数" width="70" align="center" />
        <el-table-column label="定时" width="200">
          <template #default="{ row }">
            <div class="schedule-info">
              <span v-if="row.schedule_enabled && row.cron" class="cron-badge">
                <el-icon><Clock /></el-icon>
                {{ row.cron }}
              </span>
              <span v-else class="text-muted cron-none">未启用</span>
              <span v-if="row.schedule_enabled && row.next_run_at" class="next-run">
                下次：{{ formatTime(row.next_run_at) }}
              </span>
              <span v-else-if="row.last_run_at" class="last-run">
                上次：{{ formatTime(row.last_run_at) }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <div class="action-buttons">
              <el-button link type="primary" :loading="runningId === row.id" @click="runNow(row)">
                立即采集
              </el-button>
              <el-button
                v-if="row.running_job_id"
                link
                type="danger"
                :loading="stoppingId === row.id"
                @click="stopNow(row)"
              >
                停止
              </el-button>
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="primary" @click="$router.push(`/tasks/${row.id}/jobs`)">记录</el-button>
              <el-popconfirm title="确认删除该任务？" @confirm="remove(row)">
                <template #reference>
                  <el-button link type="danger">删除</el-button>
                </template>
              </el-popconfirm>
            </div>
          </template>
        </el-table-column>
      </el-table>
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
import { Operation, Plus, Search, Calendar, Folder, Clock } from '@element-plus/icons-vue'
import { useSiteStore } from '@/stores/sites'
import { useTaskStore } from '@/stores/tasks'
import type { Task, TaskCreate, TaskUpdate } from '@/api'

const store = useTaskStore()
const sitesStore = useSiteStore()
const sites = computed(() => sitesStore.sites)

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
  try {
    await store.run(row.id, row.site_ids?.[0])
    ElMessage.success('已提交后台任务')
  } catch (e: any) {
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
      ElMessage.success(`已停止（job_id=${r.job_id}）`)
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
}

.tasks-view > .glass-card {
  padding: 0;
  overflow: hidden;
}

/* 表格头部 */
.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-foreground);
}

.header-title .el-icon {
  font-size: 20px;
  color: var(--color-accent);
}

/* 表格样式 */
.dark-table {
  padding: 0;
}

.dark-table :deep(.el-table__header-wrapper th) {
  background: var(--color-muted) !important;
  color: var(--color-foreground);
  font-weight: 600;
  font-size: 13px;
  border: none !important;
  padding: 14px 12px;
}

.dark-table :deep(.el-table__body-wrapper td) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.04) !important;
  padding: 14px 12px;
}

.dark-table :deep(.el-table__body-wrapper tr:hover td) {
  background: rgba(255, 255, 255, 0.02) !important;
}

/* 站点标签 */
.site-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.site-tag {
  font-size: 11px;
  padding: 2px 8px;
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
  border-radius: 4px;
  font-weight: 500;
}

.site-tag-more {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--color-muted);
  color: var(--color-muted-foreground);
  border-radius: 4px;
}

/* 任务名 */
.task-name {
  font-weight: 600;
  color: var(--color-foreground);
}

/* 类型徽章 */
.kind-badge {
  font-size: 12px;
  padding: 4px 10px;
  background: var(--color-muted);
  color: var(--color-muted-foreground);
  border-radius: 20px;
  font-weight: 500;
}

/* 任务参数 */
.task-params {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.param-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-muted-foreground);
}

.param-item .el-icon {
  font-size: 14px;
}

/* 定时信息 */
.schedule-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cron-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-family: var(--font-heading);
  padding: 4px 10px;
  background: rgba(34, 197, 94, 0.12);
  color: var(--color-accent);
  border-radius: 20px;
  font-weight: 500;
}

.cron-badge .el-icon {
  font-size: 14px;
}

.cron-none {
  font-size: 12px;
}

.next-run, .last-run {
  font-size: 11px;
  color: var(--color-muted-foreground);
  font-family: var(--font-heading);
}

/* 操作按钮 */
.action-buttons {
  display: flex;
  gap: 4px;
}

/* 弹窗样式 */
.task-dialog :deep(.el-dialog__header) {
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.task-dialog :deep(.el-dialog__body) {
  padding: 24px;
}

.task-dialog :deep(.el-dialog__footer) {
  padding: 16px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

/* 表单提示 */
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
}

.form-hint-inline {
  font-size: 12px;
  color: var(--color-muted-foreground);
  margin-left: 12px;
}
</style>
