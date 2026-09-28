<template>
  <div class="sites-view">
    <div class="glass-card">
      <!-- 头部 -->
      <div class="table-header">
        <div class="header-title">
          <el-icon><Setting /></el-icon>
          <span>站点配置</span>
        </div>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新增站点
        </el-button>
      </div>

      <!-- 表格 -->
      <el-table :data="store.sites" v-loading="store.loading" empty-text="暂无站点" class="dark-table">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" width="160">
          <template #default="{ row }">
            <span class="site-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="host" label="域名" width="180" />
        <el-table-column prop="base_url" label="Base URL" min-width="200" />
        <el-table-column label="适配器" width="220">
          <template #default="{ row }">
            <div class="adapter-tags">
              <span :class="['adapter-tag', row.adapter === 'sehuatang' ? 'tag-warning' : 'tag-info']">
                {{ row.adapter || 'onemei' }}
              </span>
              <span v-if="row.adapter === 'sehuatang' && row.forum_fid" class="adapter-tag tag-plain">
                FID {{ row.forum_fid }}
              </span>
              <span v-if="row.list_urls?.length" class="adapter-tag tag-plain">
                {{ row.list_urls.length }} 个 URL
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="user_agent" label="UA" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="ua-text">{{ row.user_agent || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="fingerprint_seed" label="指纹" width="90">
          <template #default="{ row }">
            <span class="seed-text">{{ row.fingerprint_seed ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="过滤规则" width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              size="small"
              @click="goFilterRules(row.id)"
              class="rule-link"
            >
              <el-icon><Filter /></el-icon>
              管理过滤规则
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <span :class="['status-pill', row.enabled ? 'status-active' : 'status-inactive']">
              {{ row.enabled ? '启用' : '停用' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <div class="action-buttons">
              <el-button link type="primary" @click="probe(row)" class="btn-link">连通性</el-button>
              <el-button link type="primary" @click="openEdit(row)" class="btn-link">编辑</el-button>
              <el-popconfirm title="确认删除该站点？" @confirm="remove(row)">
                <template #reference>
                  <el-button link type="danger" class="btn-link">删除</el-button>
                </template>
              </el-popconfirm>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑站点' : '新增站点'" width="600px" class="site-dialog">
      <el-form :model="form" label-width="100px" size="default" class="site-form">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="如：1mei 主站" />
        </el-form-item>
        <el-form-item label="域名">
          <el-input v-model="form.host" placeholder="1mei.live" />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="form.base_url" placeholder="https://1mei.live" />
        </el-form-item>
        <el-form-item label="适配器">
          <el-select v-model="form.adapter" style="width: 100%" @change="onAdapterChange">
            <el-option label="onemei (默认 / WordPress 主题)" value="onemei" />
            <el-option label="sehuatang (Discuz! 论坛, 强制 CloakBrowser)" value="sehuatang" />
          </el-select>
        </el-form-item>

        <!-- 论坛站点专属配置 -->
        <div v-if="form.adapter === 'sehuatang'" class="config-section">
          <el-alert type="warning" :closable="false" show-icon class="config-alert">
            <template #title>
              <span>论坛板块 FID（Discuz）</span>
              <span class="alert-hint">例如 国产原创=2，使用 URL 形如 <code>forum-{fid}-{page}.html</code></span>
            </template>
          </el-alert>
          <el-form-item label="板块 FID">
            <el-input v-model="form.forum_fid" placeholder="如 2（国产原创），留空 + 填下方 URL 列表 = 自定义入口" />
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
          <el-input-number v-model="form.fingerprint_seed" :min="0" :max="999999" placeholder="CloakBrowser fingerprint seed" />
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
            <span class="alert-hint">包含 / 排除关键词、用户反馈学习规则统一在过滤规则页面管理</span>
          </template>
        </el-alert>
        <div class="rule-migrate-actions">
          <el-button type="primary" plain @click="goFilterRules(form.id)">
            <el-icon><Filter /></el-icon>
            前往过滤规则页面
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
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Setting, Plus, Filter } from '@element-plus/icons-vue'
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

async function probe(s: Site) {
  const loading = ElMessage({ message: '正在测试连通性...', duration: 0 })
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
  router.push({ path: '/filter-rules', query: siteId ? { site_id: String(siteId) } : undefined })
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

/* 站点名称 */
.site-name {
  font-weight: 600;
  color: var(--color-foreground);
}

/* UA 文本 */
.ua-text {
  font-family: var(--font-heading);
  font-size: 12px;
  color: var(--color-muted-foreground);
}

/* 指纹种子 */
.seed-text {
  font-family: var(--font-heading);
  font-size: 12px;
  color: var(--color-muted-foreground);
}

/* 适配器标签 */
.adapter-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.adapter-tag {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.tag-warning {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.tag-info {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.tag-plain {
  background: var(--color-muted);
  color: var(--color-muted-foreground);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

/* 过滤规则入口（迁移后） */
.rule-link {
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* link 按钮重置：去掉默认蓝色超链接外观，改成中性按钮文本 */
.dark-table :deep(.btn-link),
.dark-table :deep(.rule-link) {
  color: var(--color-foreground);
  text-decoration: none;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: color 0.15s, background 0.15s;
}

.dark-table :deep(.btn-link:hover),
.dark-table :deep(.rule-link:hover) {
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-accent);
}

/* 危险色按钮需要保留语义色 */
.dark-table :deep(.btn-link.el-button--danger) {
  color: #f87171;
}
.dark-table :deep(.btn-link.el-button--danger:hover) {
  background: rgba(248, 113, 113, 0.12);
  color: #fca5a5;
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

/* 状态胶囊 */
.status-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.status-active {
  background: rgba(34, 197, 94, 0.15);
  color: var(--color-accent);
}

.status-inactive {
  background: var(--color-muted);
  color: var(--color-muted-foreground);
}

/* 操作按钮 */
.action-buttons {
  display: flex;
  gap: 4px;
}

/* 表单 */
.site-dialog :deep(.el-dialog__header) {
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.site-dialog :deep(.el-dialog__body) {
  padding: 24px;
}

.site-dialog :deep(.el-dialog__footer) {
  padding: 16px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.config-section {
  margin-bottom: 16px;
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
}
</style>
