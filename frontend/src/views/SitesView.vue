<template>
  <div class="sites-view">
    <div class="glass-card">
      <!-- 头部：标题 + 计数 + 主操作 -->
      <div class="table-header">
        <div class="header-left">
          <el-icon class="header-icon"><Setting /></el-icon>
          <span class="header-title">站点配置</span>
          <span v-if="store.sites.length" class="header-count">
            {{ store.sites.length }} 个站点 ·
            <span class="active-count">{{ activeCount }} 启用</span>
          </span>
        </div>
        <div class="header-right">
          <el-button @click="store.fetch()" :loading="store.loading" plain>
            <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
          </el-button>
          <el-button type="primary" @click="openCreate">
            <el-icon style="margin-right: 4px"><Plus /></el-icon>新增站点
          </el-button>
        </div>
      </div>

      <!-- 表格 -->
      <el-table
        :data="store.sites"
        v-loading="store.loading"
        empty-text="暂无站点 — 点击右上「新增站点」开始"
        class="dark-table"
      >
        <el-table-column prop="id" label="#" width="56">
          <template #default="{ row }">
            <span class="row-id">{{ row.id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="140" width="160">
          <template #default="{ row }">
            <div class="site-name">
              <span class="site-name-text">{{ row.name }}</span>
              <span v-if="!row.enabled" class="disabled-dot" title="已停用">·</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="host" label="域名" min-width="150">
          <template #default="{ row }">
            <span class="mono host-text">{{ row.host }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="base_url" label="Base URL" min-width="220">
          <template #default="{ row }">
            <span class="mono url-text" :title="row.base_url">{{ row.base_url }}</span>
          </template>
        </el-table-column>
        <el-table-column label="适配器" width="200">
          <template #default="{ row }">
            <div class="adapter-stack">
              <span class="chip" :class="`chip-${adapterTone(row.adapter)}`">
                {{ row.adapter || 'onemei' }}
              </span>
              <span v-if="row.adapter === 'sehuatang' && row.forum_fid" class="meta-chip">
                FID {{ row.forum_fid }}
              </span>
              <span v-if="row.list_urls?.length" class="meta-chip">
                {{ row.list_urls.length }} URL
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="高级" width="100" align="center">
          <template #default="{ row }">
            <el-tooltip
              placement="top"
              :show-after="200"
              :content="advancedTooltip(row)"
            >
              <span class="advanced-summary mono">{{ advancedSummary(row) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="过滤规则" width="110" align="center">
          <template #default="{ row }">
            <el-button link size="small" @click="goFilterRules(row.id)" class="rule-link">
              <el-icon style="margin-right: 2px"><Filter /></el-icon>规则
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="84" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              @change="onToggle(row, $event)"
              size="small"
              class="enable-switch"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right" align="right">
          <template #default="{ row }">
            <div class="action-buttons">
              <el-button link size="small" @click="probe(row)" class="action-link">测试</el-button>
              <el-button link size="small" @click="openEdit(row)" class="action-link">编辑</el-button>
              <el-popconfirm
                :title="`确认删除「${row.name}」？`"
                confirm-button-text="删除"
                cancel-button-text="取消"
                @confirm="remove(row)"
              >
                <template #reference>
                  <el-button link size="small" class="action-link danger">删除</el-button>
                </template>
              </el-popconfirm>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 表格底部 status bar -->
      <div v-if="store.sites.length" class="table-footer">
        <span class="footer-item">
          <span class="footer-dot active" />
          启用 {{ activeCount }}
        </span>
        <span class="footer-divider" />
        <span class="footer-item">
          <span class="footer-dot inactive" />
          停用 {{ store.sites.length - activeCount }}
        </span>
        <span class="footer-divider" />
        <span class="footer-item">共 {{ store.sites.length }} 条</span>
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? '编辑站点' : '新增站点'"
      width="640px"
      class="site-dialog"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="100px" size="default" class="site-form">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：1mei 主站" />
        </el-form-item>
        <el-form-item label="域名" required>
          <el-input v-model="form.host" placeholder="1mei.live" />
        </el-form-item>
        <el-form-item label="Base URL" required>
          <el-input v-model="form.base_url" placeholder="https://1mei.live" />
        </el-form-item>
        <el-form-item label="适配器">
          <el-select v-model="form.adapter" style="width: 100%" @change="onAdapterChange">
            <el-option label="onemei（默认 / WordPress 主题）" value="onemei" />
            <el-option label="sehuatang（Discuz! 论坛，强制浏览器）" value="sehuatang" />
          </el-select>
        </el-form-item>

        <!-- 论坛站点专属配置 -->
        <div v-if="form.adapter === 'sehuatang'" class="config-section">
          <el-alert type="warning" :closable="false" show-icon class="config-alert">
            <template #title>
              <span>论坛板块 FID（Discuz）</span>
              <span class="alert-hint">
                例如「国产原创」= 2，URL 形如
                <code>forum-{fid}-{page}.html</code>
              </span>
            </template>
          </el-alert>
          <el-form-item label="板块 FID">
            <el-input
              v-model="form.forum_fid"
              placeholder="如 2（国产原创）；留空 + 填下方 URL 列表 = 自定义入口"
            />
          </el-form-item>
        </div>

        <el-alert type="info" :closable="false" show-icon class="config-alert">
          <template #title>
            <span>本站点列表 URL（可选，自定义入口）</span>
            <span class="alert-hint">留空则走默认模板（WP list_all / forum 板块页）</span>
          </template>
        </el-alert>
        <el-form-item label="URL 列表">
          <el-input
            v-model="form.list_urls_text"
            type="textarea"
            :rows="4"
            placeholder="每行一个完整 URL，作为本任务的列表页入口。&#10;示例：&#10;https://sehuatang.org/forum-2-1.html&#10;https://sehuatang.org/forum-37-1.html"
          />
        </el-form-item>

        <el-form-item label="UA（可选）">
          <el-input v-model="form.user_agent" placeholder="留空使用默认" />
        </el-form-item>
        <el-form-item label="代理（可选）">
          <el-input v-model="form.proxy" placeholder="socks5://user:pass@host:1080" />
        </el-form-item>
        <el-form-item label="指纹种子">
          <el-input-number
            v-model="form.fingerprint_seed"
            :min="0"
            :max="999999"
            placeholder="DrissionPage fingerprint seed"
          />
        </el-form-item>

        <!-- 过滤词迁移提示（关键词维护已统一到过滤规则页面） -->
        <el-alert
          type="success"
          :closable="false"
          show-icon
          class="config-alert rule-migrate-hint"
        >
          <template #title>
            <span>标题关键词已迁移到「过滤规则」</span>
            <span class="alert-hint">
              包含 / 排除关键词、用户反馈学习规则统一在过滤规则页面管理
            </span>
          </template>
        </el-alert>
        <div class="rule-migrate-actions">
          <el-button type="primary" plain @click="goFilterRules(form.id)">
            <el-icon style="margin-right: 4px"><Filter /></el-icon>前往过滤规则页面
          </el-button>
        </div>

        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
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
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Setting, Plus, Filter, Refresh } from '@element-plus/icons-vue'
import { useSiteStore } from '@/stores/sites'
import type { Site, SiteCreate } from '@/api'

const store = useSiteStore()
const dialogVisible = ref(false)
const router = useRouter()
const form = reactive<
  SiteCreate & {
    id?: number
    list_urls_text?: string
    forum_fid?: string
  }
>({
  name: '',
  host: '',
  base_url: '',
  user_agent: '',
  proxy: '',
  fingerprint_seed: undefined,
  adapter: 'onemei',
  forum_fid: '',
  list_urls: [],
  list_urls_text: '',
  enabled: true,
  note: '',
})

const activeCount = computed(
  () => store.sites.filter((s) => s.enabled).length,
)

function adapterTone(adapter?: string): string {
  switch ((adapter || 'onemei').toLowerCase()) {
    case 'sehuatang':
      return 'accent'
    case 'onemei':
      return 'muted'
    default:
      return 'muted'
  }
}

function advancedSummary(row: Site): string {
  const parts: string[] = []
  if (row.fingerprint_seed != null) parts.push(`#${row.fingerprint_seed}`)
  if (row.proxy) parts.push('proxy')
  if (row.user_agent) parts.push('UA')
  return parts.length ? parts.join(' · ') : '—'
}

function advancedTooltip(row: Site): string {
  const lines: string[] = []
  lines.push(`UA: ${row.user_agent || '默认'}`)
  lines.push(`代理: ${row.proxy || '无'}`)
  lines.push(`指纹: ${row.fingerprint_seed ?? '未设置'}`)
  return lines.join('\n')
}

function parseLines(text: string): string[] {
  return (text || '')
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function resetForm() {
  Object.assign(form, {
    id: undefined,
    name: '',
    host: '',
    base_url: '',
    user_agent: '',
    proxy: '',
    fingerprint_seed: undefined,
    adapter: 'onemei',
    forum_fid: '',
    list_urls: [],
    list_urls_text: '',
    enabled: true,
    note: '',
  })
}

function onAdapterChange() {
  if (form.adapter !== 'sehuatang') form.forum_fid = ''
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(s: Site) {
  const urls = s.list_urls || []
  Object.assign(form, {
    id: s.id,
    name: s.name,
    host: s.host,
    base_url: s.base_url,
    user_agent: s.user_agent || '',
    proxy: s.proxy || '',
    fingerprint_seed: s.fingerprint_seed ?? undefined,
    adapter: s.adapter || 'onemei',
    forum_fid: s.forum_fid || '',
    list_urls: [...urls],
    list_urls_text: urls.join('\n'),
    enabled: s.enabled,
    note: s.note || '',
  })
  dialogVisible.value = true
}

async function submit() {
  if (!form.name || !form.host || !form.base_url) {
    ElMessage.warning('请填写名称、域名、Base URL')
    return
  }
  const payload: any = {
    ...form,
    list_urls: parseLines(form.list_urls_text || ''),
    forum_fid: form.adapter === 'sehuatang' ? (form.forum_fid || null) : null,
  }
  delete payload.list_urls_text
  if (payload.fingerprint_seed === undefined || payload.fingerprint_seed === null) {
    delete payload.fingerprint_seed
  }
  if (form.id) {
    await store.update(form.id, payload)
    ElMessage.success('已更新')
  } else {
    await store.create(payload)
    ElMessage.success('已创建')
  }
  dialogVisible.value = false
}

async function remove(s: Site) {
  await store.remove(s.id)
  ElMessage.success('已删除')
}

async function onToggle(row: Site, val: boolean | string | number) {
  const next = Boolean(val)
  await store.update(row.id, { enabled: next })
  row.enabled = next
  ElMessage.success(next ? '已启用' : '已停用')
}

async function probe(s: Site) {
  const loading = ElMessage({ message: '正在测试连通性…', duration: 0 })
  try {
    const r = await store.probe(s.id)
    loading.close()
    if (r.ok) {
      ElMessage.success(`连通正常：${r.title}（${r.status}）`)
    } else {
      ElMessage.error(`连通失败：${r.error || r.status}`)
    }
  } catch (e: any) {
    loading.close()
    ElMessage.error(`连通失败：${e.message}`)
  }
}

function goFilterRules(siteId?: number) {
  dialogVisible.value = false
  router.push({
    path: '/filter-rules',
    query: siteId ? { site_id: String(siteId) } : undefined,
  })
}

onMounted(() => store.fetch())
</script>

<style scoped>
.sites-view {
  width: 100%;
}

.sites-view > .glass-card {
  padding: 0;
  overflow: hidden;
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
.dark-table :deep(.el-table__body-wrapper tr:hover td) {
  background: rgba(34, 197, 94, 0.04) !important;
}
.dark-table :deep(.el-table__body-wrapper tr.disabled-row td) {
  opacity: 0.55;
}

/* ============ 字段 ============ */
.row-id {
  font-family: var(--font-heading);
  font-size: 12px;
  color: var(--color-muted-foreground);
}
.site-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.site-name-text {
  font-weight: 600;
  color: var(--color-foreground);
  font-size: 14px;
}
.disabled-dot {
  color: var(--color-muted-foreground);
  font-size: 18px;
  line-height: 1;
}

.mono {
  font-family: var(--font-heading);
}
.host-text {
  font-size: 12.5px;
  color: var(--color-foreground);
}
.url-text {
  font-size: 12px;
  color: var(--color-muted-foreground);
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}

.advanced-summary {
  font-size: 11.5px;
  color: var(--color-muted-foreground);
  letter-spacing: 0.2px;
}

/* ============ chip（统一胶囊语言） ============ */
.adapter-stack {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.chip {
  font-family: var(--font-heading);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.3px;
  padding: 3px 9px;
  border-radius: 12px;
  background: var(--color-muted);
  color: var(--color-muted-foreground);
  border: 1px solid rgba(255, 255, 255, 0.06);
}
.chip-accent {
  background: rgba(34, 197, 94, 0.1);
  border-color: rgba(34, 197, 94, 0.25);
  color: var(--color-accent);
}
.meta-chip {
  font-family: var(--font-heading);
  font-size: 10.5px;
  color: var(--color-muted-foreground);
  padding: 2px 7px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

/* ============ action link ============ */
.action-buttons {
  display: inline-flex;
  gap: 2px;
  justify-content: flex-end;
}
.action-link {
  font-size: 12.5px !important;
  color: var(--color-foreground) !important;
  padding: 4px 8px !important;
  border-radius: 4px !important;
  font-weight: 500;
  transition: color 0.15s, background 0.15s;
}
.action-link:hover {
  background: rgba(34, 197, 94, 0.08) !important;
  color: var(--color-accent) !important;
}
.action-link.danger {
  color: #f87171 !important;
}
.action-link.danger:hover {
  background: rgba(239, 68, 68, 0.1) !important;
  color: #fca5a5 !important;
}

.rule-link {
  font-size: 12.5px !important;
  color: var(--color-accent) !important;
  padding: 4px 8px !important;
  border-radius: 4px !important;
  font-weight: 500;
}
.rule-link:hover {
  background: rgba(34, 197, 94, 0.08) !important;
}

.enable-switch {
  --el-switch-on-color: var(--color-accent);
}

/* ============ footer status bar ============ */
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
  background: var(--color-muted-foreground);
}
.footer-dot.active {
  background: var(--color-accent);
  box-shadow: 0 0 6px var(--color-accent);
}
.footer-divider {
  width: 1px;
  height: 12px;
  background: rgba(255, 255, 255, 0.08);
}

/* ============ 弹窗 ============ */
.site-dialog :deep(.el-dialog__header) {
  padding: 18px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.site-dialog :deep(.el-dialog__body) {
  padding: 22px 24px;
}
.site-dialog :deep(.el-dialog__footer) {
  padding: 14px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.config-section {
  margin-bottom: 12px;
}
.config-alert {
  margin-bottom: 12px;
}
.config-alert :deep(.el-alert__title) {
  font-size: 13px;
}
.alert-hint {
  color: var(--color-muted-foreground);
  margin-left: 8px;
  font-size: 12px;
}
.alert-hint code {
  background: var(--color-muted);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-heading);
  font-size: 11px;
  color: var(--color-accent);
}

.rule-migrate-hint :deep(.el-alert__title) {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.rule-migrate-actions {
  display: flex;
  justify-content: flex-start;
  margin: 8px 0 20px;
}
</style>
