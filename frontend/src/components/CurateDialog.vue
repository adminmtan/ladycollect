<template>
  <el-dialog
    v-model="visible"
    :title="null"
    width="1100px"
    top="4vh"
    class="curate-dialog"
    :close-on-click-modal="false"
    align-center
    destroy-on-close
  >
    <!-- 自定义 header -->
    <template #header>
      <div class="cd-header">
        <div class="cd-header-left">
          <span class="cd-icon">
            <el-icon><MagicStick /></el-icon>
          </span>
          <div class="cd-titles">
            <div class="cd-title">智能整理 · {{ modeLabel }}</div>
            <div class="cd-subtitle">
              <template v-if="mode === 'site'">
                <strong>{{ existingKeywords.length }}</strong> 个过滤关键词
                <span class="cd-sub-extra">（来自该站点当前规则）</span>
                · 将影响 <strong>{{ affected.length }}</strong> / {{ totalTitles }} 条帖子
              </template>
              <template v-else-if="mode === 'single'">
                AI 从当前帖子拆解出 <strong>{{ aiKeywords.length }}</strong> 个关键词
                <span class="cd-sub-extra">（确认后会写入该站点过滤规则并删除该帖）</span>
                · 规则已有 <strong>{{ existingKeywords.length }}</strong> 个
              </template>
              <template v-else>
                规则已有 <strong>{{ existingKeywords.length }}</strong> 个
                · AI 新增 <strong>{{ aiKeywords.length }}</strong> 个
                · 将影响 <strong>{{ affected.length }}</strong> / {{ totalTitles }} 条帖子
              </template>
              <span v-if="unmatchedCount > 0" class="cd-sub-extra">
                · {{ unmatchedCount }} 条不命中
              </span>
              · 提取器：{{ extractorLabel }}
            </div>
          </div>
        </div>
        <span class="cd-rule-chip">
          <el-icon><Filter /></el-icon>
          {{ ruleName }}
        </span>
      </div>
    </template>

    <div class="cd-body">
      <!-- 左侧：关键词编辑 -->
      <section class="cd-col cd-col-keywords">
        <div class="cd-col-head">
          <span class="cd-col-title">候选关键词</span>
          <span class="cd-col-hint">双击编辑 · 点击 × 删除</span>
        </div>

        <div class="cd-add-row">
          <input
            v-model="newKw"
            class="cd-add-input"
            placeholder="手动添加关键词，回车添加"
            @keyup.enter="onAddKw"
          />
          <button class="cd-add-btn" :disabled="!newKw.trim()" @click="onAddKw">
            <el-icon><Plus /></el-icon>
            添加
          </button>
        </div>

        <div v-if="!workingKeywords.length" class="cd-empty-mini">
          暂无关键词
        </div>

        <div v-else class="cd-kw-grid">
          <div
            v-for="(k, i) in workingKeywords"
            :key="`${k}-${i}`"
            class="cd-kw-chip"
            :class="{
              'is-editing': editingIndex === i,
              'is-affecting': affectedKeywords.has(k.toLowerCase()),
              'is-existing': isExisting(k),
              'is-new': isNew(k),
            }"
          >
            <span class="cd-kw-tag" :class="`tag-${kwTag(k)}`">
              {{ kwTagLabel(k) }}
            </span>
            <input
              v-if="editingIndex === i"
              v-model="workingKeywords[i]"
              class="cd-kw-edit"
              autofocus
              @blur="editingIndex = -1"
              @keyup.enter="editingIndex = -1"
              @keyup.esc="cancelEdit"
            />
            <span
              v-else
              class="cd-kw-text"
              :title="`双击编辑 · ${k}`"
              @dblclick="startEdit(i)"
            >{{ k }}</span>
            <span
              class="cd-kw-x"
              title="删除"
              @click="onRemoveKw(i)"
            >
              <el-icon><Close /></el-icon>
            </span>
          </div>
        </div>

        <div class="cd-stat-row">
          <div class="cd-stat">
            <span class="cd-stat-num">{{ workingKeywords.length }}</span>
            <span class="cd-stat-label">当前关键词</span>
          </div>
          <div class="cd-stat">
            <span class="cd-stat-num accent">{{ aiKeywordsCount }}</span>
            <span class="cd-stat-label">AI 新增</span>
          </div>
          <div class="cd-stat">
            <span class="cd-stat-num muted">{{ removedExistingCount }}</span>
            <span class="cd-stat-label">已移除</span>
          </div>
          <div class="cd-stat">
            <span class="cd-stat-num danger">{{ selectedDeleteCount }}</span>
            <span class="cd-stat-label">待删除</span>
          </div>
        </div>
      </section>

      <!-- 中间：分隔 -->
      <div class="cd-divider"></div>

      <!-- 右侧：匹配预览 -->
      <section class="cd-col cd-col-preview">
        <div class="cd-col-head">
          <span class="cd-col-title">受影响帖子预览</span>
          <span class="cd-col-hint">
            <el-checkbox
              v-model="selectAllAffected"
              :indeterminate="someAffectedSelected && !selectAllAffected"
              @change="onToggleAllAffected"
            >
              全选
            </el-checkbox>
            · 共 {{ affected.length }} 条
          </span>
        </div>

        <div v-if="!affected.length" class="cd-empty-mini">
          <template v-if="!workingKeywords.length">
            暂无关键词
          </template>
          <template v-else>
            当前 {{ workingKeywords.length }} 个关键词没有命中任何帖子
            <span v-if="totalTitles > 0" class="cd-empty-hint">
              · 共扫描了 {{ totalTitles }} 条
            </span>
          </template>
        </div>

        <div v-else class="cd-affected-list">
          <div
            v-for="item in affected"
            :key="item.post_id"
            class="cd-affected-item"
            :class="{ 'is-unchecked': !selectedDelete.has(item.post_id) }"
            @click="toggleAffected(item.post_id)"
          >
            <el-checkbox
              :model-value="selectedDelete.has(item.post_id)"
              @change="toggleAffected(item.post_id)"
              @click.stop
            />
            <div class="cd-affected-main">
              <div class="cd-affected-title" v-html="highlightTitle(item.title, item.matched_keywords)"></div>
              <div class="cd-affected-meta">
                <span class="kw-tag" v-for="k in item.matched_keywords" :key="k">{{ k }}</span>
              </div>
            </div>
            <span class="cd-affected-id">#{{ item.post_id }}</span>
          </div>
        </div>
      </section>
    </div>

    <template #footer>
      <div class="cd-footer">
        <div class="cd-footer-left">
          <span class="cd-footer-hint">
            取消勾选的帖子不会被删除；移走的关键词会从规则里物理删除，新增的会写入规则
          </span>
        </div>
        <div class="cd-footer-right">
          <el-button @click="visible = false">取消</el-button>
          <el-button
            type="primary"
            :loading="committing"
            :disabled="!workingKeywords.length || !selectedDeleteCount"
            @click="onCommit"
          >
            <el-icon><Select /></el-icon>
            写入 +{{ aiKeywordsCount }} 关键词并删除 {{ selectedDeleteCount }} 条
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Filter, Plus, Close, Select } from '@element-plus/icons-vue'
import { postsApi } from '@/api'

const props = defineProps<{
  modelValue: boolean
  /** 传入选中的 post id；为空时整站扫描 */
  postIds: number[]
  /** 备选：站点级批量整理 */
  siteId?: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (
    e: 'committed',
    payload: { keywordsAdded: string[]; postsDeleted: number; ruleId: number }
  ): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

/* ============ AI 返回数据 ============ */
const aiKeywords = ref<string[]>([])          // AI 这次新给的（不含已存在）
const existingKeywords = ref<string[]>([])     // 规则里原本就有的
const ruleId = ref<number>(0)
const ruleName = ref('')
const extractor = ref<'ai' | 'local'>('local')
const mode = ref<'site' | 'single' | 'multi' | 'global'>('site')  // 后端告知的场景
// 后端返回的原始命中帖子（title + site_id 都在这里，matched_keywords 留空，
// 前端按当前 workingKeywords 实时重算）
type RawPost = { post_id: number; title: string; site_id: number }
const originalPosts = ref<RawPost[]>([])
const totalTitles = ref(0)

const extractorLabel = computed(() => (extractor.value === 'ai' ? 'AI' : '本地规则'))

const modeLabel = computed(() => {
  if (mode.value === 'single') return '单帖整理'
  if (mode.value === 'multi') return '多帖整理'
  if (mode.value === 'global') return '全站过滤关键词总览'
  return '站点批量整理'
})

/* ============ 用户编辑态 ============ */
const workingKeywords = ref<string[]>([])
const editingIndex = ref(-1)
const newKw = ref('')
const selectedDelete = ref<Set<number>>(new Set())
const committing = ref(false)

/* ============ 派生：受 workingKeywords 实时联动 ============ */
const existingSet = computed(() => new Set(existingKeywords.value.map((k) => k.toLowerCase())))

function isExisting(k: string): boolean {
  return existingSet.value.has(k.trim().toLowerCase())
}
function isNew(k: string): boolean {
  return !existingSet.value.has(k.trim().toLowerCase())
}
// 来源标签: 'exist' (历史已存) / 'ai' (本次 AI 新建议) / 'manual' (用户手动加)
const aiSet = computed(
  () => new Set(aiKeywords.value.map((k) => k.trim().toLowerCase())),
)
function isAiSuggested(k: string): boolean {
  return aiSet.value.has(k.trim().toLowerCase())
}
function kwTag(k: string): 'exist' | 'ai' | 'manual' {
  if (isExisting(k)) return 'exist'
  if (isAiSuggested(k)) return 'ai'
  return 'manual'
}
function kwTagLabel(k: string): string {
  const t = kwTag(k)
  if (t === 'exist') return '已存'
  if (t === 'ai') return 'AI 新'
  return '手动'
}

const removedExistingCount = computed(() => {
  return existingKeywords.value.filter(
    (k) => !workingKeywords.value.some((w) => w.trim().toLowerCase() === k.trim().toLowerCase()),
  ).length
})

const aiKeywordsCount = computed(() => {
  return workingKeywords.value.filter((k) => !isExisting(k)).length
})

// 当前 workingKeywords（小写去空）
const workingSet = computed(
  () => new Set(workingKeywords.value.map((k) => k.trim().toLowerCase()).filter(Boolean)),
)

// 实时受影响帖子：根据 workingSet 过滤 originalPosts，并重算每条命中的 matched_keywords
const affected = computed(() => {
  const ks = workingSet.value
  const out: { post_id: number; title: string; site_id: number; matched_keywords: string[] }[] = []
  for (const p of originalPosts.value) {
    const t_lc = (p.title || '').toLowerCase()
    const hits: string[] = []
    for (const k of ks) {
      if (k && t_lc.includes(k)) hits.push(k)
    }
    if (hits.length) {
      out.push({
        post_id: p.post_id,
        title: p.title,
        site_id: p.site_id,
        matched_keywords: hits,
      })
    }
  }
  return out
})

// 当前命中的关键词集合（出现在 affected.matched_keywords 里）
const affectedKeywords = computed(() => {
  const s = new Set<string>()
  for (const a of affected.value) {
    for (const k of a.matched_keywords) s.add(k.toLowerCase())
  }
  return s
})

const unmatchedCount = computed(() => totalTitles.value - affected.value.length)

const selectedDeleteCount = computed(() => selectedDelete.value.size)
const selectAllAffected = ref(false)
const someAffectedSelected = computed(() => {
  if (!affected.value.length) return false
  return affected.value.some((a) => selectedDelete.value.has(a.post_id))
})

// 当 affected 因关键词删除而缩小时，自动从 selectedDelete 移除那些不再命中的 post_id
// （即使用户之前勾选过）
watch(
  () => affected.value.map((a) => a.post_id),
  (curIds) => {
    const curSet = new Set(curIds)
    let changed = false
    for (const pid of [...selectedDelete.value]) {
      if (!curSet.has(pid)) {
        selectedDelete.value.delete(pid)
        changed = true
      }
    }
    if (changed) selectedDelete.value = new Set(selectedDelete.value)

    // 同步 selectAllAffected 全选态
    if (curIds.length === 0) {
      selectAllAffected.value = false
    }
  },
)

function onToggleAllAffected(v: any) {
  if (v) {
    for (const a of affected.value) selectedDelete.value.add(a.post_id)
    selectedDelete.value = new Set(selectedDelete.value)
  } else {
    selectedDelete.value = new Set()
  }
}

/* ============ 加载预览 ============ */
watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return
    await loadPreview()
  },
)

async function loadPreview() {
  // reset
  aiKeywords.value = []
  existingKeywords.value = []
  workingKeywords.value = []
  selectedDelete.value = new Set()
  editingIndex.value = -1
  originalPosts.value = []

  try {
    const res = await postsApi.curatePreview({
      post_ids: props.postIds.length ? props.postIds : undefined,
      site_id: !props.postIds.length && props.siteId ? props.siteId : undefined,
      top_n: 10,
    })
    mode.value = res.mode || 'site'
    aiKeywords.value = res.ai_keywords || []
    existingKeywords.value = res.existing_keywords || []
    workingKeywords.value = [...(res.suggested_keywords || [])]
    ruleId.value = res.suggested_rule_id
    ruleName.value = res.suggested_rule_name
    extractor.value = res.extractor
    // ★ 用后端返回的 pool (全集) 当 originalPosts, 而不是 res.affected (只是初始命中的).
    // 这样用户手动加关键词后能正确从全集里筛受影响, 不会被后端初始过滤结果限制
    const poolSrc = (res.pool && res.pool.length) ? res.pool : (res.affected || [])
    originalPosts.value = poolSrc.map((p: any) => ({
      post_id: p.post_id,
      title: p.title,
      site_id: p.site_id,
    }))
    totalTitles.value = res.total_titles
    await nextTick()
    selectedDelete.value = new Set(affected.value.map((a) => a.post_id))
    selectAllAffected.value = affected.value.length > 0
  } catch (e: any) {
    ElMessage.error(e?.message || '智能整理预览失败')
    visible.value = false
  }
}

/* ============ 关键词编辑 ============ */
function startEdit(i: number) {
  editingIndex.value = i
}

function cancelEdit() {
  editingIndex.value = -1
  // 恢复原值（避免空字符串破坏 workingKeywords）
  if (workingKeywords.value.some((k) => !k.trim())) {
    workingKeywords.value = workingKeywords.value.filter((k) => k.trim())
  }
}

function onRemoveKw(i: number) {
  workingKeywords.value.splice(i, 1)
}

function onAddKw() {
  const raw = newKw.value.trim()
  if (!raw) return
  // 支持逗号/空格分隔多个
  const parts = raw.split(/[\n,，;；\s]+/).map((s) => s.trim()).filter(Boolean)
  // 大小写不敏感去重：避免 "Ads" 和 "ads" 同时出现在工作集里
  // （后端 curate_commit 也是按 .lower() 比较 previous_existing，详见 backend/app/api/posts.py:890）
  const existingLower = new Set(workingKeywords.value.map((k) => k.trim().toLowerCase()))
  for (const p of parts) {
    const key = p.toLowerCase()
    if (!existingLower.has(key)) {
      workingKeywords.value.push(p)
      existingLower.add(key)
    }
  }
  newKw.value = ''
}

/* ============ 高亮标题 ============ */
function highlightTitle(title: string, kws: string[]): string {
  let html = (title || '').replace(/[&<>]/g, (c) =>
    c === '&' ? '&amp;' : c === '<' ? '&lt;' : c === '>' ? '&gt;' : c,
  )
  for (const k of kws) {
    if (!k) continue
    const safe = k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const re = new RegExp(`(${safe})`, 'gi')
    html = html.replace(re, '<mark class="cd-hl">$1</mark>')
  }
  return html
}

/* ============ 切换受影响 ============ */
function toggleAffected(pid: number) {
  if (selectedDelete.value.has(pid)) {
    selectedDelete.value.delete(pid)
  } else {
    selectedDelete.value.add(pid)
  }
  selectedDelete.value = new Set(selectedDelete.value)
}

/* ============ 提交 ============ */
async function onCommit() {
  if (!workingKeywords.value.length) {
    ElMessage.warning('请至少保留 1 个关键词')
    return
  }
  if (!selectedDelete.value.size) {
    ElMessage.warning('请至少勾选 1 条要删除的帖子')
    return
  }
  committing.value = true
  try {
    const res = await postsApi.curateCommit({
      rule_id: ruleId.value,
      keywords: workingKeywords.value,
      previous_existing: existingKeywords.value,
      post_ids_to_delete: Array.from(selectedDelete.value),
      note: 'curate',
    })
    const summary = [
      res.keywords_added.length ? `+${res.keywords_added.length} 关键词` : '',
      res.keywords_removed.length ? `−${res.keywords_removed.length} 关键词` : '',
      `删除 ${res.posts_deleted} 条帖子`,
    ].filter(Boolean).join(' · ')
    ElMessage.success(summary || '已应用')
    emit('committed', {
      keywordsAdded: res.keywords_added,
      postsDeleted: res.posts_deleted,
      ruleId: res.rule_id,
    })
    visible.value = false
  } catch (e: any) {
    ElMessage.error(e?.message || '提交失败')
  } finally {
    committing.value = false
  }
}
</script>

<style scoped>
.curate-dialog :deep(.el-dialog__header) {
  padding: 18px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.curate-dialog :deep(.el-dialog__body) {
  padding: 0;
}
.curate-dialog :deep(.el-dialog__footer) {
  padding: 14px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

/* ============ Header ============ */
.cd-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.cd-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.cd-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.25), rgba(34, 197, 94, 0.05));
  color: var(--color-accent);
  font-size: 20px;
  border: 1px solid rgba(34, 197, 94, 0.35);
}

.cd-titles {
  min-width: 0;
}

.cd-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-foreground);
  letter-spacing: -0.2px;
}

.cd-subtitle {
  font-size: 12px;
  color: var(--color-muted-foreground);
  margin-top: 3px;
}

.cd-subtitle strong {
  color: var(--color-accent);
  font-family: var(--font-heading);
  font-weight: 600;
}

.cd-sub-extra {
  color: var(--color-muted-foreground);
  font-size: 11.5px;
}

.cd-rule-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: var(--color-accent);
  border-radius: 20px;
  font-size: 12px;
  font-family: var(--font-heading);
  font-weight: 500;
}

/* ============ Body ============ */
.cd-body {
  display: flex;
  min-height: 540px;
  max-height: 70vh;
}

.cd-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 18px 20px;
  min-width: 0;
}

.cd-col-keywords {
  flex: 0 0 380px;
  border-right: 1px solid rgba(255, 255, 255, 0.06);
}

.cd-col-preview {
  flex: 1;
}

.cd-col-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  margin-bottom: 14px;
}

.cd-col-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-foreground);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  font-family: var(--font-heading);
}

.cd-col-hint {
  font-size: 11.5px;
  color: var(--color-muted-foreground);
}

/* ============ Add row ============ */
.cd-add-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.cd-add-input {
  flex: 1;
  background: var(--color-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 8px 12px;
  color: var(--color-foreground);
  font-family: var(--font-body);
  font-size: 13px;
  outline: none;
  transition: all var(--transition-fast);
}

.cd-add-input:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.15);
}

.cd-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: linear-gradient(135deg, var(--color-accent) 0%, #16a34a 100%);
  color: var(--color-on-accent);
  border: none;
  border-radius: var(--radius-md);
  padding: 0 14px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.cd-add-btn:disabled {
  background: var(--color-muted);
  color: var(--color-muted-foreground);
  cursor: not-allowed;
}

.cd-add-btn:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.3);
}

/* ============ Keywords grid ============ */
.cd-kw-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  flex: 1;
  align-content: flex-start;
  overflow-y: auto;
  padding-bottom: 8px;
}

.cd-kw-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px 4px 4px;
  border-radius: 20px;
  background: var(--color-muted);
  border: 1px solid var(--color-border);
  font-size: 12.5px;
  color: var(--color-foreground);
  font-family: var(--font-heading);
  transition: all var(--transition-fast);
}

/* 已存在的关键词 → 蓝色边，灰色小标 */
.cd-kw-chip.is-existing {
  background: rgba(59, 130, 246, 0.08);
  border-color: rgba(59, 130, 246, 0.3);
  color: #93c5fd;
}

/* AI 新建议的关键词 → 绿色边 */
.cd-kw-chip.is-new {
  background: rgba(34, 197, 94, 0.08);
  border-color: rgba(34, 197, 94, 0.35);
  color: var(--color-accent);
}

.cd-kw-chip.is-affecting {
  /* 命中状态用更亮的强调色 */
  box-shadow: 0 0 0 1px rgba(34, 197, 94, 0.3);
}

.cd-kw-chip.is-existing.is-affecting {
  background: rgba(59, 130, 246, 0.15);
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.5);
}

.cd-kw-chip.is-editing {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.2);
}

.cd-kw-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 1px 6px;
  font-size: 9.5px;
  font-weight: 600;
  border-radius: 10px;
  letter-spacing: 0.3px;
  font-family: var(--font-heading);
  text-transform: uppercase;
  flex-shrink: 0;
}

.tag-exist {
  background: rgba(59, 130, 246, 0.2);
  color: #93c5fd;
  border: 1px solid rgba(59, 130, 246, 0.4);
}

.tag-new {
  background: rgba(34, 197, 94, 0.2);
  color: var(--color-accent);
  border: 1px solid rgba(34, 197, 94, 0.4);
}

.cd-kw-text {
  cursor: text;
  user-select: none;
  padding: 0 4px 0 2px;
}

.cd-kw-edit {
  background: transparent;
  border: none;
  outline: none;
  color: var(--color-foreground);
  font-family: var(--font-heading);
  font-size: 12.5px;
  width: 80px;
  padding: 0 4px;
}

.cd-kw-x {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  cursor: pointer;
  font-size: 11px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-muted-foreground);
  transition: all var(--transition-fast);
}

.cd-kw-x:hover {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-destructive);
}

.cd-empty-mini {
  padding: 32px 0;
  text-align: center;
  color: var(--color-muted-foreground);
  font-size: 12.5px;
}

.cd-empty-hint {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.35);
}

/* ============ Stat row ============ */
.cd-stat-row {
  display: flex;
  gap: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  margin-top: 12px;
}

.cd-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.cd-stat-num {
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 700;
  color: var(--color-foreground);
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.cd-stat-num.accent {
  color: var(--color-accent);
}

.cd-stat-num.danger {
  color: var(--color-destructive);
}

.cd-stat-num.muted {
  color: var(--color-muted-foreground);
}

.cd-stat-label {
  font-size: 10.5px;
  color: var(--color-muted-foreground);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-family: var(--font-heading);
}

/* ============ Preview column ============ */
.cd-affected-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-right: 4px;
}

.cd-affected-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.cd-affected-item:hover {
  background: rgba(34, 197, 94, 0.04);
  border-color: rgba(34, 197, 94, 0.2);
}

.cd-affected-item.is-unchecked {
  opacity: 0.45;
}

.cd-affected-main {
  flex: 1;
  min-width: 0;
}

.cd-affected-title {
  font-size: 13px;
  color: var(--color-foreground);
  line-height: 1.5;
  margin-bottom: 6px;
  word-break: break-word;
}

.cd-affected-title :deep(.cd-hl) {
  background: rgba(34, 197, 94, 0.25);
  color: var(--color-accent);
  padding: 0 2px;
  border-radius: 3px;
  font-weight: 600;
}

.cd-affected-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.kw-tag {
  display: inline-block;
  padding: 2px 8px;
  font-size: 10.5px;
  background: rgba(34, 197, 94, 0.15);
  color: var(--color-accent);
  border-radius: 10px;
  font-family: var(--font-heading);
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.cd-affected-id {
  font-family: var(--font-heading);
  font-size: 11px;
  color: var(--color-muted-foreground);
  white-space: nowrap;
}

/* ============ Footer ============ */
.cd-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.cd-footer-hint {
  font-size: 11.5px;
  color: var(--color-muted-foreground);
}

.cd-footer-right {
  display: flex;
  gap: 8px;
}

.cd-footer-right :deep(.el-button--primary) {
  background: linear-gradient(135deg, var(--color-accent) 0%, #16a34a 100%) !important;
  border: none !important;
  font-weight: 600;
}

/* ============ Scrollbar polish ============ */
.cd-kw-grid::-webkit-scrollbar,
.cd-affected-list::-webkit-scrollbar {
  width: 6px;
}
.cd-kw-grid::-webkit-scrollbar-thumb,
.cd-affected-list::-webkit-scrollbar-thumb {
  background: rgba(34, 197, 94, 0.2);
  border-radius: 3px;
}

/* ============ Responsive ============ */
@media (max-width: 960px) {
  .cd-body {
    flex-direction: column;
    max-height: 75vh;
  }
  .cd-col-keywords {
    flex: none;
    border-right: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    max-height: 280px;
  }
}
</style>