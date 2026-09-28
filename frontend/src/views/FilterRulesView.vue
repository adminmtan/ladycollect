<template>
  <div class="filter-rules-view">
    <!-- 顶部统计卡 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :xs="24" :sm="8">
        <div class="glass-card stat-card">
          <div class="stat-icon" style="background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(59, 130, 246, 0.05))">
            <el-icon :size="24"><Filter /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">规则总数</div>
            <div class="stat-value">{{ stats.totalRules }}</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="8">
        <div class="glass-card stat-card">
          <div class="stat-icon" style="background: linear-gradient(135deg, rgba(34, 197, 94, 0.2), rgba(34, 197, 94, 0.05))">
            <el-icon :size="24"><Collection /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">关键词总数</div>
            <div class="stat-value">{{ stats.totalKeywords }}</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="8">
        <div class="glass-card stat-card">
          <div class="stat-icon" style="background: linear-gradient(135deg, rgba(245, 158, 11, 0.2), rgba(245, 158, 11, 0.05))">
            <el-icon :size="24"><MagicStick /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">本周学习</div>
            <div class="stat-value">{{ stats.weeklyLearned }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 主体 -->
    <div class="glass-card main-card">
      <div class="card-header">
        <div class="header-title">
          <el-icon><Filter /></el-icon>
          <span>智能过滤规则</span>
          <span class="header-hint">不喜欢 → 自动学习 → 采集时过滤</span>
        </div>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新建规则
        </el-button>
      </div>

      <!-- tab + 筛选 -->
      <div class="filter-toolbar">
        <el-tabs v-model="activeTab" @tab-change="onTabChange">
          <el-tab-pane label="全部" name="all"></el-tab-pane>
          <el-tab-pane label="站点级" name="site"></el-tab-pane>
          <el-tab-pane label="全局" name="global"></el-tab-pane>
        </el-tabs>
        <el-select
          v-model="filterType"
          placeholder="类型"
          clearable
          style="width: 160px"
          @change="onFilterTypeChange"
        >
          <el-option label="exclude（不含）" value="exclude" />
          <el-option label="include（仅含）" value="include" />
          <el-option label="tag（标签）" value="tag" />
        </el-select>
      </div>

      <!-- 列表 -->
      <el-empty v-if="!store.loading && !filteredRules.length" description="还没有规则，去标记几篇不喜欢的帖子试试" />

      <div v-else class="rule-list">
        <div v-for="r in filteredRules" :key="r.id" class="rule-item" :class="{ disabled: !r.enabled }">
          <div class="rule-main">
            <div class="rule-header">
              <span class="rule-name">{{ r.name }}</span>
              <span :class="['scope-badge', `scope-${r.scope}`]">
                {{ r.scope === 'global' ? '全局' : '站点' }}
              </span>
              <span :class="['type-badge', `type-${r.rule_type}`]">
                {{ typeText(r.rule_type) }}
              </span>
              <span v-if="r.scope === 'site' && r.site_id" class="site-ref">
                {{ siteName(r.site_id) }}
              </span>
            </div>
            <div class="rule-stats">
              <span class="stat-pill">
                <el-icon><Key /></el-icon>
                {{ r.keyword_count }} 关键词
              </span>
              <span class="stat-pill stat-pill-hit">
                <el-icon><Aim /></el-icon>
                命中 {{ r.hit_count_total }}
              </span>
              <span class="rule-time">更新于 {{ formatTime(r.updated_at) }}</span>
            </div>
            <div v-if="r.note" class="rule-note">{{ r.note }}</div>
          </div>
          <div class="rule-actions">
            <el-switch v-model="r.enabled" @change="toggleEnabled(r)" />
            <el-button link type="primary" @click="openKeywordsDialog(r)">编辑关键词</el-button>
            <el-popconfirm title="确认删除该规则？关联关键词也会一并删除" @confirm="remove(r)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建/编辑规则 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑规则' : '新建规则'"
      width="560px"
      class="rule-dialog"
    >
      <el-form :model="form" label-width="100px" class="rule-form">
        <el-form-item label="规则名">
          <el-input v-model="form.name" placeholder="如：色花堂 自动 exclude" />
        </el-form-item>
        <el-form-item label="范围">
          <el-radio-group v-model="form.scope">
            <el-radio value="site">站点级</el-radio>
            <el-radio value="global">全局</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.scope === 'site'" label="关联站点">
          <el-select v-model="form.site_id" placeholder="选择站点" style="width: 100%">
            <el-option v-for="s in sites" :key="s.id" :label="`${s.name} (${s.host})`" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="规则类型">
          <el-select v-model="form.rule_type" style="width: 100%">
            <el-option label="exclude（命中即丢弃）" value="exclude" />
            <el-option label="include（必须命中）" value="include" />
            <el-option label="tag（命中后归类标记）" value="tag" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!editingId" label="初始关键词">
          <el-input
            v-model="form.keywordsText"
            type="textarea"
            :rows="4"
            placeholder="每行一个，或逗号 / 空格分隔"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" placeholder="可选" />
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

    <!-- 关键词编辑弹窗 -->
    <el-dialog
      v-model="keywordsDialogVisible"
      :title="editingRule ? `关键词 - ${editingRule.name}` : '关键词'"
      width="680px"
      class="keywords-dialog"
    >
      <div v-if="editingRule" class="keywords-editor">
        <div class="add-row">
          <el-input
            v-model="newKeywordInput"
            placeholder="输入关键词后回车添加；多个用逗号或空格分隔"
            @keyup.enter="addKeyword"
          />
          <el-button type="primary" @click="addKeyword" :disabled="!newKeywordInput.trim()">
            <el-icon><Plus /></el-icon>
            添加
          </el-button>
        </div>
        <el-empty v-if="!editingRule.keywords?.length" description="暂无关键词" />
        <div v-else class="keyword-chips">
          <div
            v-for="k in editingRule.keywords"
            :key="k.id"
            class="keyword-chip"
          >
            <span class="keyword-text">{{ k.keyword }}</span>
            <span :class="['source-tag', `source-${k.source}`]">{{ sourceText(k.source) }}</span>
            <span class="hit-count" v-if="k.hit_count > 0">命中 {{ k.hit_count }}</span>
            <el-button
              link
              type="danger"
              size="small"
              class="chip-delete"
              @click="deleteKeyword(k.id)"
            >
              <el-icon><Close /></el-icon>
            </el-button>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="keywordsDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Filter,
  Collection,
  MagicStick,
  Key,
  Aim,
  Plus,
  Close,
} from '@element-plus/icons-vue'
import { useFilterRulesStore } from '@/stores/filterRules'
import { useSiteStore } from '@/stores/sites'
import { feedbackApi, type FilterRuleSummary } from '@/api'

const store = useFilterRulesStore()
const siteStore = useSiteStore()
const route = useRoute()
const sites = computed(() => siteStore.sites)

const activeTab = ref<'all' | 'site' | 'global'>('all')
const filterType = ref<string>('')

const dialogVisible = ref(false)
const keywordsDialogVisible = ref(false)
const editingId = ref<number | null>(null)
const editingRule = ref<any | null>(null)
const newKeywordInput = ref('')

const form = reactive({
  name: '',
  scope: 'site' as 'site' | 'global',
  site_id: undefined as number | undefined,
  rule_type: 'exclude' as 'exclude' | 'include' | 'tag',
  enabled: true,
  note: '',
  keywordsText: '',
})

const filteredRules = computed(() => {
  let list = store.rules
  if (activeTab.value !== 'all') {
    list = list.filter((r) => r.scope === activeTab.value)
  }
  if (filterType.value) {
    list = list.filter((r) => r.rule_type === filterType.value)
  }
  return list
})

const stats = computed(() => {
  const totalRules = store.rules.length
  const totalKeywords = store.rules.reduce((acc, r) => acc + r.keyword_count, 0)
  const weeklyLearned = store.rules.reduce((acc, r) => {
    const updated = new Date(r.updated_at).getTime()
    const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000
    if (updated >= weekAgo) {
      return acc + r.keyword_count
    }
    return acc
  }, 0)
  return { totalRules, totalKeywords, weeklyLearned }
})

function typeText(t: string) {
  const map: Record<string, string> = {
    exclude: '不含',
    include: '仅含',
    tag: '标签',
  }
  return map[t] || t
}

function sourceText(s: string) {
  const map: Record<string, string> = {
    manual: '手动',
    learned: 'AI 学习',
    user_dislike: '不喜欢',
    user_like: '喜欢',
  }
  return map[s] || s
}

function siteName(id?: number | null) {
  if (id == null) return ''
  const s = sites.value.find((x) => x.id === id)
  return s ? `${s.name} (${s.host})` : `#${id}`
}

function formatTime(s: string) {
  if (!s) return '-'
  return s.replace('T', ' ').slice(0, 16)
}

function onTabChange() {
  /* 触发 filteredRules 重计算 */
}

function onFilterTypeChange() {
  /* 触发 filteredRules 重计算 */
}

async function toggleEnabled(r: FilterRuleSummary) {
  try {
    await store.update(r.id, { enabled: r.enabled })
    ElMessage.success(r.enabled ? '已启用' : '已停用')
  } catch (e: any) {
    ElMessage.error(e.message)
    r.enabled = !r.enabled
  }
}

function resetForm() {
  form.name = ''
  form.scope = 'site'
  form.site_id = undefined
  form.rule_type = 'exclude'
  form.enabled = true
  form.note = ''
  form.keywordsText = ''
}

function openCreate() {
  resetForm()
  editingId.value = null
  dialogVisible.value = true
}

function openEdit(r: FilterRuleSummary) {
  editingId.value = r.id
  form.name = r.name
  form.scope = r.scope
  form.site_id = r.site_id ?? undefined
  form.rule_type = r.rule_type
  form.enabled = r.enabled
  form.note = r.note ?? ''
  form.keywordsText = ''
  dialogVisible.value = true
}

function parseKeywords(text: string): string[] {
  return (text || '')
    .split(/[\n,，;；\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

async function submit() {
  if (!form.name) {
    ElMessage.warning('请填写规则名')
    return
  }
  if (form.scope === 'site' && !form.site_id) {
    ElMessage.warning('站点级规则必须选择关联站点')
    return
  }
  try {
    if (editingId.value) {
      await store.update(editingId.value, {
        name: form.name,
        scope: form.scope,
        site_id: form.scope === 'site' ? form.site_id ?? null : null,
        rule_type: form.rule_type,
        enabled: form.enabled,
        note: form.note || null,
      })
      ElMessage.success('已保存')
    } else {
      const keywords = parseKeywords(form.keywordsText)
      await store.create({
        name: form.name,
        scope: form.scope,
        site_id: form.scope === 'site' ? form.site_id ?? null : null,
        rule_type: form.rule_type,
        enabled: form.enabled,
        note: form.note || null,
        keywords,
      })
      ElMessage.success('已创建')
    }
    dialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

async function remove(r: FilterRuleSummary) {
  try {
    await store.remove(r.id)
    ElMessage.success('已删除')
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

async function openKeywordsDialog(r: FilterRuleSummary) {
  editingRule.value = await store.fetchOne(r.id)
  keywordsDialogVisible.value = true
}

async function addKeyword() {
  if (!editingRule.value || !newKeywordInput.value.trim()) return
  const kws = parseKeywords(newKeywordInput.value)
  if (!kws.length) return
  try {
    await store.addKeywords(editingRule.value.id, kws)
    newKeywordInput.value = ''
    ElMessage.success(`已添加 ${kws.length} 个关键词`)
    // 重新拉取以获取最新 hit_count 等
    editingRule.value = await store.fetchOne(editingRule.value.id)
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

async function deleteKeyword(kid: number) {
  if (!editingRule.value) return
  try {
    await ElMessageBox.confirm('确认删除该关键词？', '删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await store.deleteKeyword(editingRule.value.id, kid)
    editingRule.value = await store.fetchOne(editingRule.value.id)
    ElMessage.success('已删除')
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

onMounted(async () => {
  await siteStore.fetch()
  await store.fetch()
  // 支持 ?site_id=... 自动定位：tab 切到"站点级"并预填表单
  const qSite = Number(route.query.site_id)
  if (qSite && !Number.isNaN(qSite)) {
    activeTab.value = 'site'
    resetForm()
    form.scope = 'site'
    form.site_id = qSite
    dialogVisible.value = true
  }
})

watch(
  () => route.query.site_id,
  (v) => {
    const id = Number(v)
    if (id && !Number.isNaN(id)) {
      activeTab.value = 'site'
      resetForm()
      form.scope = 'site'
      form.site_id = id
      dialogVisible.value = true
    }
  }
)
</script>

<style scoped>
.filter-rules-view {
  width: 100%;
}

/* 统计卡片 */
.stats-row {
  margin-bottom: 24px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
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

/* 主卡片 */
.main-card {
  padding: 0;
  overflow: hidden;
}

.card-header {
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

.header-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--color-muted-foreground);
  margin-left: 8px;
}

/* 工具栏 */
.filter-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  gap: 16px;
  flex-wrap: wrap;
}

.filter-toolbar :deep(.el-tabs__nav-wrap::after) {
  background: rgba(255, 255, 255, 0.06);
}

.filter-toolbar :deep(.el-tabs__item) {
  color: var(--color-muted-foreground) !important;
  font-weight: 500;
}

.filter-toolbar :deep(.el-tabs__item.is-active) {
  color: var(--color-accent) !important;
}

.filter-toolbar :deep(.el-tabs__active-bar) {
  background: var(--color-accent) !important;
}

/* 规则列表 */
.rule-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px 24px;
}

.rule-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: var(--radius-lg);
  transition: all var(--transition-normal);
}

.rule-item:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.12);
}

.rule-item.disabled {
  opacity: 0.5;
}

.rule-main {
  flex: 1;
  min-width: 0;
}

.rule-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.rule-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-foreground);
}

.scope-badge,
.type-badge,
.source-tag,
.site-ref {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 20px;
  font-weight: 600;
}

.scope-site {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.scope-global {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.type-exclude {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-destructive);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.type-include {
  background: rgba(34, 197, 94, 0.15);
  color: var(--color-accent);
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.type-tag {
  background: rgba(148, 163, 184, 0.15);
  color: var(--color-muted-foreground);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.site-ref {
  background: var(--color-muted);
  color: var(--color-muted-foreground);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.rule-stats {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 4px;
}

.stat-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-muted-foreground);
  background: var(--color-muted);
  padding: 4px 10px;
  border-radius: 20px;
  font-family: var(--font-heading);
  font-weight: 500;
}

.stat-pill .el-icon {
  font-size: 14px;
}

.stat-pill-hit {
  background: rgba(34, 197, 94, 0.1);
  color: var(--color-accent);
}

.rule-time {
  font-size: 12px;
  color: var(--color-muted-foreground);
  font-family: var(--font-heading);
}

.rule-note {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-muted-foreground);
  line-height: 1.5;
}

.rule-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 表单 */
.rule-dialog :deep(.el-dialog__header),
.keywords-dialog :deep(.el-dialog__header) {
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.rule-dialog :deep(.el-dialog__body),
.keywords-dialog :deep(.el-dialog__body) {
  padding: 24px;
}

.rule-dialog :deep(.el-dialog__footer),
.keywords-dialog :deep(.el-dialog__footer) {
  padding: 16px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

/* 关键词编辑 */
.keywords-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.add-row {
  display: flex;
  gap: 8px;
}

.add-row .el-input {
  flex: 1;
}

.keyword-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.keyword-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: var(--color-muted);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}

.keyword-chip:hover {
  border-color: var(--color-accent);
}

.keyword-text {
  font-family: var(--font-heading);
  font-size: 13px;
  color: var(--color-foreground);
  font-weight: 500;
}

.source-manual {
  background: rgba(148, 163, 184, 0.15);
  color: var(--color-muted-foreground);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.source-learned {
  background: rgba(34, 197, 94, 0.15);
  color: var(--color-accent);
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.source-user_dislike {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-destructive);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.source-user_like {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.hit-count {
  font-family: var(--font-heading);
  font-size: 11px;
  color: var(--color-muted-foreground);
  background: rgba(255, 255, 255, 0.04);
  padding: 2px 6px;
  border-radius: 10px;
}

.chip-delete {
  margin-left: 2px;
}
</style>
