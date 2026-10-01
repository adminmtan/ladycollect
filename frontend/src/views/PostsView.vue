<template>
  <div class="posts-view">
    <!-- Sticky 过滤栏 -->
    <div class="filter-shell">
      <div class="filter-shell-inner glass-card">
        <!-- 第 1 行：搜索 + 总数 + 智能整理 -->
        <div class="filter-row filter-row-primary">
          <div class="search-block">
            <el-icon class="search-icon"><Search /></el-icon>
            <input
              v-model="keywordDraft"
              type="text"
              class="search-input"
              placeholder="搜索标题或磁链关键字（按 / 快速聚焦）"
              @keyup.enter="onFiltersChange"
            />
            <span v-if="keywordDraft" class="search-clear" @click="keywordDraft = ''">
              <el-icon><CircleClose /></el-icon>
            </span>
          </div>

          <div class="filter-right">
            <span class="result-stat">
              共 <strong>{{ store.total.toLocaleString() }}</strong> 条
              <span v-if="activeFilterCount" class="filter-stat-sep">·</span>
              <span v-if="activeFilterCount" class="filter-stat-active">
                {{ activeFilterCount }} 个筛选
              </span>
            </span>

            <button
              class="curate-btn"
              :disabled="!store.total"
              @click="openCurate"
              title="AI 拆解关键词 + 手动确认 + 批量删除"
            >
              <el-icon><MagicStick /></el-icon>
              <span>智能整理</span>
            </button>
          </div>
        </div>

        <!-- 第 2 行：高级过滤 chip + 重置 -->
        <div class="filter-row filter-row-secondary">
          <div class="filter-chips">
            <ChipSelect
              v-model="filters.site_id"
              :options="siteOptions"
              placeholder="全部站点"
              icon="Compass"
              @change="onFiltersChange"
            />
            <ChipDateRange
              v-model="postDateRange"
              label="发布日期"
              @change="onFiltersChange"
            />
            <ChipDateRange
              v-model="createdRange"
              label="入库日期"
              @change="onFiltersChange"
            />
            <ChipSelect
              v-model="filters.sort"
              :options="sortOptions"
              placeholder="入库时间（新→旧）"
              icon="Sort"
              @change="onFiltersChange"
            />
            <ChipToggle
              v-model="filters.has_magnet"
              label="magnet"
              active-color="accent"
              @change="onFiltersChange"
            />
            <ChipToggle
              v-model="filters.has_ed2k"
              label="ed2k"
              active-color="warning"
              @change="onFiltersChange"
            />
          </div>
          <button class="reset-btn" @click="reset">
            <el-icon><RefreshLeft /></el-icon>
            <span>重置</span>
          </button>
        </div>

        <!-- 第 3 行：当前激活的过滤 chip（点击删除） -->
        <div v-if="activeChips.length" class="filter-row filter-row-active">
          <span class="active-label">激活条件：</span>
          <span
            v-for="chip in activeChips"
            :key="chip.key"
            class="active-chip"
            @click="chip.onRemove"
          >
            <span class="active-chip-label">{{ chip.label }}</span>
            <el-icon class="active-chip-x"><Close /></el-icon>
          </span>
        </div>
      </div>
    </div>

    <!-- 工具条：仅选中条目后浮出 -->
    <div v-if="selectedIds.length > 0" class="link-bar-shell">
      <LinkCopyBar
        ref="linkBarRef"
        :selected-ids="selectedIds"
        :total="store.total"
        @copy="onCopy"
        @select-all="selectAllLoaded"
        @select-none="clearSelection"
        @delete="onDeleteBatch"
      />
    </div>

    <!-- 列表主体（仅卡片视图） -->
    <div class="posts-body">
      <el-empty
        v-if="!store.loading && !store.items.length"
        description="暂无帖子"
        class="empty-state"
      >
        <template #image>
          <div class="empty-illustration">
            <svg width="80" height="80" viewBox="0 0 24 24" fill="none">
              <path d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
        </template>
      </el-empty>

      <el-row v-else :gutter="10" class="posts-grid">
        <el-col
          v-for="p in store.items"
          :key="p.id"
          :xs="24"
          :sm="12"
          :md="8"
          :lg="6"
          :xl="4"
          style="margin-bottom: 10px"
        >
          <PostCard
            :post="p"
            selectable
            deletable
            v-model="selected[p.id]"
            @update:modelValue="syncSelection"
            @deleted="onDeletePost"
            @disliked="onDislikedPost"
            @liked="onLikedPost"
            @open-curate="openCurateForSingle"
          />
        </el-col>
      </el-row>

      <!-- 加载更多 / 全部加载 -->
      <div v-if="store.items.length" class="load-more">
        <div class="load-info">
          已加载 <strong>{{ store.items.length }}</strong> / {{ store.total.toLocaleString() }}
        </div>

        <div class="load-actions" v-if="store.items.length < store.total">
          <el-button
            @click="loadMore"
            :loading="store.loading"
            class="btn-ghost load-btn"
          >
            <el-icon><Plus /></el-icon>
            加载更多
          </el-button>
          <el-button
            @click="loadAll"
            :loading="loadingAll"
            class="btn-accent load-btn"
            title="一次性把当前筛选条件下的所有帖子加载到列表"
          >
            <el-icon><Bottom /></el-icon>
            全部加载
          </el-button>
        </div>
        <span v-else class="load-end">— 已全部加载 —</span>
      </div>
    </div>

    <!-- 预览弹窗 -->
    <el-dialog v-model="previewVisible" :title="previewTitle" width="80%" top="5vh" class="preview-dialog">
      <div v-if="previewPost" class="preview-content">
        <div class="preview-meta">
          <span class="meta-item">
            <el-icon><Calendar /></el-icon>
            {{ previewPost.post_date || '-' }}
          </span>
          <span class="meta-item">
            <el-icon><User /></el-icon>
            @{{ previewPost.author || '匿名' }}
          </span>
          <a :href="previewPost.url" target="_blank" class="open-link">
            <el-icon><Link /></el-icon>
            打开原页面
          </a>
        </div>
        <img v-if="previewPost.cover" :src="previewPost.cover" class="preview-cover" />
        <div v-if="previewPost.magnet?.length" class="link-block">
          <div class="link-header">
            <el-icon><Link /></el-icon>
            <span>magnet × {{ previewPost.magnet.length }}</span>
          </div>
          <div v-for="(m, i) in previewPost.magnet" :key="'m' + i" class="link-text">{{ m }}</div>
        </div>
        <div v-if="previewPost.ed2k?.length" class="link-block">
          <div class="link-header">
            <el-icon><Connection /></el-icon>
            <span>ed2k × {{ previewPost.ed2k.length }}</span>
          </div>
          <div v-for="(e, i) in previewPost.ed2k" :key="'e' + i" class="link-text">{{ e }}</div>
        </div>
      </div>
    </el-dialog>

    <!-- 下载链接弹窗 -->
    <el-dialog v-model="linksDialogVisible" :title="linksDialogTitle" width="680px" top="8vh" class="links-dialog">
      <el-input
        v-model="linksDialogText"
        type="textarea"
        :rows="18"
        readonly
        class="links-textarea"
      />
      <template #footer>
        <el-button @click="linksDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="copyAllLinks">一键复制全部</el-button>
      </template>
    </el-dialog>

    <!-- 智能整理弹窗 -->
    <CurateDialog
      v-model="curateVisible"
      :post-ids="curatePostIds"
      :site-id="filters.site_id"
      @committed="onCurateCommitted"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search,
  CircleClose,
  RefreshLeft,
  Close,
  Plus,
  Bottom,
  MagicStick,
  Calendar,
  User,
  Link,
  Connection,
  Compass,
  Sort,
} from '@element-plus/icons-vue'
import { useSiteStore } from '@/stores/sites'
import { usePostStore, type PostQuery } from '@/stores/posts'
import { postsApi, feedbackApi } from '@/api'
import LinkCopyBar from '@/components/LinkCopyBar.vue'
import PostCard from '@/components/PostCard.vue'
import ChipSelect from '@/components/filter/ChipSelect.vue'
import ChipDateRange from '@/components/filter/ChipDateRange.vue'
import ChipToggle from '@/components/filter/ChipToggle.vue'
import CurateDialog from '@/components/CurateDialog.vue'

const siteStore = useSiteStore()
const sites = computed(() => siteStore.sites)
const store = usePostStore()

/* ============ 筛选 ============ */
const filters = reactive<PostQuery>({
  site_id: undefined,
  keyword: '',
  has_magnet: undefined,
  has_ed2k: undefined,
  sort: 'created_desc',
})

const keywordDraft = ref('')
const postDateRange = ref<[string, string] | null>(null)
const createdRange = ref<[string, string] | null>(null)

// debounce 关键字
let keywordTimer: any = null
watch(keywordDraft, (v) => {
  clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => {
    filters.keyword = v
    onFiltersChange()
  }, 280)
})

/* ============ 选项 ============ */
const siteOptions = computed(() =>
  sites.value.map((s: any) => ({ label: `${s.name} (${s.host})`, value: s.id })),
)
const sortOptions = [
  { label: '入库时间（新→旧）', value: 'created_desc' },
  { label: '入库时间（旧→新）', value: 'created_asc' },
  { label: '发布日期（新→旧）', value: 'post_date_desc' },
  { label: '发布日期（旧→新）', value: 'post_date_asc' },
]

/* ============ 激活条件 chips ============ */
const activeChips = computed(() => {
  const chips: { key: string; label: string; onRemove: () => void }[] = []
  if (filters.site_id) {
    const s = sites.value.find((x: any) => x.id === filters.site_id)
    chips.push({
      key: 'site',
      label: `站点 · ${s?.name || s?.host || filters.site_id}`,
      onRemove: () => {
        filters.site_id = undefined
        onFiltersChange()
      },
    })
  }
  if (postDateRange.value) {
    chips.push({
      key: 'postDate',
      label: `发布 · ${postDateRange.value[0]} → ${postDateRange.value[1]}`,
      onRemove: () => {
        postDateRange.value = null
        onFiltersChange()
      },
    })
  }
  if (createdRange.value) {
    chips.push({
      key: 'created',
      label: `入库 · ${createdRange.value[0]} → ${createdRange.value[1]}`,
      onRemove: () => {
        createdRange.value = null
        onFiltersChange()
      },
    })
  }
  if (filters.keyword) {
    chips.push({
      key: 'keyword',
      label: `关键字 · ${filters.keyword}`,
      onRemove: () => {
        keywordDraft.value = ''
        filters.keyword = ''
        onFiltersChange()
      },
    })
  }
  if (filters.sort && filters.sort !== 'created_desc') {
    const so = sortOptions.find((x) => x.value === filters.sort)
    chips.push({
      key: 'sort',
      label: `排序 · ${so?.label || filters.sort}`,
      onRemove: () => {
        filters.sort = 'created_desc'
        onFiltersChange()
      },
    })
  }
  if (filters.has_magnet) {
    chips.push({
      key: 'magnet',
      label: 'magnet',
      onRemove: () => {
        filters.has_magnet = undefined
        onFiltersChange()
      },
    })
  }
  if (filters.has_ed2k) {
    chips.push({
      key: 'ed2k',
      label: 'ed2k',
      onRemove: () => {
        filters.has_ed2k = undefined
        onFiltersChange()
      },
    })
  }
  return chips
})

const activeFilterCount = computed(() => activeChips.value.length)

/* ============ 选中 ============ */
const selected = reactive<Record<number, boolean>>({})
const selectedIds = computed(() =>
  Object.entries(selected)
    .filter(([, v]) => v)
    .map(([k]) => Number(k)),
)

function selectAllLoaded() {
  for (const p of store.items) selected[p.id] = true
}

function clearSelection() {
  for (const k of Object.keys(selected)) delete selected[Number(k)]
}

/* ============ 操作 ============ */
function reset() {
  Object.assign(filters, {
    site_id: undefined,
    keyword: '',
    has_magnet: undefined,
    has_ed2k: undefined,
    sort: 'created_desc',
  })
  keywordDraft.value = ''
  postDateRange.value = null
  createdRange.value = null
  fetchPosts()
}

async function fetchPosts() {
  const q: PostQuery = {
    site_id: filters.site_id,
    keyword: filters.keyword || undefined,
    has_magnet: filters.has_magnet,
    has_ed2k: filters.has_ed2k,
    date_from: postDateRange.value?.[0],
    date_to: postDateRange.value?.[1],
    created_from: createdRange.value?.[0],
    created_to: createdRange.value?.[1],
    sort: filters.sort,
    page: 1,
    page_size: 30,
  }
  Object.keys(selected).forEach((k) => (selected[Number(k)] = false))
  await store.fetch(q)
  if (store.items.length === 0 && store.total === 0 && !store.loading) {
    await new Promise((r) => setTimeout(r, 500))
    await store.fetch(q)
  }
}

async function loadMore() {
  await store.loadMore()
}

const loadingAll = ref(false)
async function loadAll() {
  loadingAll.value = true
  try {
    await fetchPosts() // 先重置回第 1 页（store.fetch() 会 bump generation）
    // 逐页拉取直到装满 store.total；如果用户在循环期间切换筛选条件，
    // store.fetch() 会再次 bump generation 并重置 items，循环会因 generation
    // mismatch 在 store.loadMore 内被静默丢弃，然后 while 条件自然失败退出
    while (store.items.length < store.total && !store.loading) {
      await store.loadMore()
    }
  } finally {
    loadingAll.value = false
  }
}

async function onFiltersChange() {
  await fetchPosts()
}

function syncSelection() {
  /* 触发 selectedIds 重新计算 */
}

async function onDeletePost(postId: number) {
  try {
    await ElMessageBox.confirm(
      `确定删除这篇帖子吗？\n\n${(store.items.find((x) => x.id === postId)?.title || '').slice(0, 60) || '(无标题)'}`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await postsApi.remove(postId)
    ElMessage.success('已删除')
    const i = store.items.findIndex((x) => x.id === postId)
    if (i !== -1) store.items.splice(i, 1)
    store.total = Math.max(0, store.total - 1)
  } catch (e: any) {
    ElMessage.error(`删除失败：${e?.message || e}`)
  }
}

async function onDislikePost(row: any) {
  try {
    await ElMessageBox.confirm(
      `确定不喜欢这篇帖子吗？\n\n${(row.title || '').slice(0, 80) || '(无标题)'}`,
      '标记为不喜欢',
      {
        type: 'warning',
        confirmButtonText: '确认不喜欢',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  try {
    const res = await feedbackApi.dislike(row.id)
    ElMessage.success(
      res.keywords_added?.length
        ? `已学习 ${res.keywords_added.length} 个关键词`
        : '已标记',
    )
    const i = store.items.findIndex((x) => x.id === row.id)
    if (i !== -1) store.items.splice(i, 1)
    store.total = Math.max(0, store.total - 1)
    delete selected[row.id]
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

async function onLikePost(row: any) {
  try {
    const res = await feedbackApi.like(row.id)
    ElMessage.success(
      `已收藏：提取 ${res.keywords_added?.length || 0} 个关键词到 include 规则`,
    )
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

async function onDislikedPost(payload: { postId: number }) {
  const i = store.items.findIndex((x) => x.id === payload.postId)
  if (i !== -1) store.items.splice(i, 1)
  store.total = Math.max(0, store.total - 1)
  delete selected[payload.postId]
}

async function onLikedPost(_payload: unknown) {
  /* no-op */
}

async function onDeleteBatch(ids: number[]) {
  try {
    const res = await postsApi.removeMany(ids)
    ElMessage.success(`已删除 ${res.deleted} 条`)
    const idSet = new Set(ids)
    for (let i = store.items.length - 1; i >= 0; i--) {
      if (idSet.has(store.items[i].id)) store.items.splice(i, 1)
    }
    store.total = Math.max(0, store.total - res.deleted)
    for (const id of ids) delete selected[id]
    if (store.items.length < 30 && store.items.length < store.total) {
      await store.loadMore()
    }
  } catch (e: any) {
    ElMessage.error(`删除失败：${e?.message || e}`)
  }
}

async function onCopy(payload: { ids: number[]; kinds: string[]; mode: 'text' | 'clipboard' }) {
  try {
    if (payload.mode === 'clipboard') {
      if (!payload.ids.length) {
        ElMessage.warning('请先勾选要复制的帖子')
        return
      }
      const text = await postsApi.copyLinksText(payload.ids, payload.kinds)
      await writeClipboard(text)
      ElMessage.success(`已复制选中的 ${payload.ids.length} 条链接到剪贴板`)
      return
    }
    const params: any = {
      site_id: filters.site_id,
      keyword: filters.keyword || undefined,
      has_magnet: filters.has_magnet,
      has_ed2k: filters.has_ed2k,
      date_from: postDateRange.value?.[0],
      date_to: postDateRange.value?.[1],
      created_from: createdRange.value?.[0],
      created_to: createdRange.value?.[1],
      sort: filters.sort,
    }
    const { ids, total, truncated } = await postsApi.allIds(params)
    if (!ids.length) {
      ElMessage.warning('当前筛选条件下没有帖子')
      return
    }
    const text = await postsApi.copyLinksText(ids, payload.kinds)
    linksDialogText.value = text.trim()
    linksDialogTitle.value = `下载链接（共 ${total} 条${truncated ? '，仅展示前 5000 条' : ''}）`
    linksDialogVisible.value = true
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

async function writeClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    try {
      document.execCommand('copy')
    } catch {}
    document.body.removeChild(ta)
  }
}

/* ============ 智能整理 ============ */
const curateVisible = ref(false)
const curatePostIds = ref<number[]>([])

function openCurate() {
  // 三种场景:
  //   1. 用户勾选了帖子: 用 post_ids (mode=single/multi)
  //   2. 用户选了站点: 传 site_id (mode=site)
  //   3. 都没选: 全站过滤关键词聚合 (mode=global, 只读)
  if (selectedIds.value.length) {
    curatePostIds.value = [...selectedIds.value]
  } else {
    curatePostIds.value = []
  }
  curateVisible.value = true
}

function openCurateForSingle(payload: { postId: number }) {
  // 单帖 dislike 模式：弹窗打开 mode=single，候选关键词 = AI 对该帖输出的关键词
  curatePostIds.value = [payload.postId]
  curateVisible.value = true
}

async function onCurateCommitted(payload: { keywordsAdded: string[]; postsDeleted: number; ruleId: number }) {
  // 从本地列表移除被删的 post
  const deletedIds = new Set(store.items.filter((p) => p.id).map((p) => p.id)) // placeholder; will be re-fetched
  // 后端已删，前端只需刷新（重新 fetch 会少掉这些）
  // 同时清掉本地选择
  for (const id of [...selectedIds.value]) delete selected[id]
  await fetchPosts()
}

/* ============ 弹窗 ============ */
const linksDialogVisible = ref(false)
const linksDialogText = ref('')
const linksDialogTitle = ref('下载链接')

async function copyAllLinks() {
  await writeClipboard(linksDialogText.value)
  ElMessage.success('已复制到剪贴板')
  linksDialogVisible.value = false
}

const previewVisible = ref(false)
const previewPost = ref<any>(null)
const previewTitle = computed(() => previewPost.value?.title || '详情')

const linkBarRef = ref<InstanceType<typeof LinkCopyBar> | null>(null)

/* ============ 快捷键 / 生命周期 ============ */
function onKeydown(e: KeyboardEvent) {
  if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) {
    e.preventDefault()
    const input = document.querySelector('.search-input') as HTMLInputElement | null
    input?.focus()
  }
}

onMounted(async () => {
  await siteStore.fetch()
  await fetchPosts()
  window.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.posts-view {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ============ 过滤栏（非 sticky，正常流式滚动，避免多层 sticky 互压） ============ */
.filter-shell {
  margin: 0;
}

.filter-shell-inner {
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: relative;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.filter-row-primary {
  justify-content: space-between;
}

.filter-row-secondary {
  flex-wrap: wrap;
  justify-content: space-between;
}

.filter-row-active {
  flex-wrap: wrap;
  gap: 6px;
  border-top: 1px dashed rgba(255, 255, 255, 0.06);
  padding-top: 10px;
}

/* ============ 搜索框 ============ */
.search-block {
  position: relative;
  flex: 1;
  max-width: 560px;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 14px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--color-muted-foreground);
  font-size: 16px;
  pointer-events: none;
}

.search-input {
  width: 100%;
  background: var(--color-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 10px 38px 10px 42px;
  color: var(--color-foreground);
  font-family: var(--font-body);
  font-size: 13.5px;
  outline: none;
  transition: all var(--transition-fast);
}

.search-input::placeholder {
  color: #CBD5E1;
  opacity: 1;
}

.search-input:hover {
  border-color: var(--color-muted-foreground);
}

.search-input:focus {
  border-color: var(--color-accent);
  background: rgba(34, 197, 94, 0.04);
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.15);
}

.search-clear {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--color-muted-foreground);
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
}
.search-clear:hover {
  color: var(--color-accent);
}

/* ============ 右侧统计 + 智能整理按钮 ============ */
.filter-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.result-stat {
  font-size: 12.5px;
  color: var(--color-muted-foreground);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.result-stat strong {
  color: var(--color-foreground);
  font-family: var(--font-heading);
  font-weight: 600;
  font-size: 14px;
  margin: 0 2px;
}

.filter-stat-sep {
  margin: 0 6px;
  color: rgba(255, 255, 255, 0.15);
}

.filter-stat-active {
  color: var(--color-accent);
  font-weight: 500;
}

.curate-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 14px;
  height: 36px;
  background: linear-gradient(135deg, var(--color-accent) 0%, #16a34a 100%);
  border: none;
  border-radius: var(--radius-md);
  color: var(--color-on-accent);
  font-family: var(--font-body);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.06) inset, 0 2px 8px rgba(34, 197, 94, 0.2);
}

.curate-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.06) inset, 0 6px 16px rgba(34, 197, 94, 0.35);
}

.curate-btn:disabled {
  background: var(--color-muted);
  color: var(--color-muted-foreground);
  cursor: not-allowed;
  box-shadow: none;
}

.curate-btn .el-icon {
  font-size: 14px;
}

/* ============ Chip 行 ============ */
.filter-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.reset-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-muted-foreground);
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.reset-btn:hover {
  color: var(--color-accent);
  border-color: var(--color-accent);
}

/* ============ 激活条件 chips ============ */
.active-label {
  font-size: 11.5px;
  color: var(--color-muted-foreground);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  font-family: var(--font-heading);
  margin-right: 2px;
}

.active-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: var(--color-accent);
  border-radius: 20px;
  font-size: 11.5px;
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: var(--font-heading);
}

.active-chip:hover {
  background: rgba(34, 197, 94, 0.2);
  border-color: rgba(34, 197, 94, 0.5);
}

.active-chip-x {
  font-size: 11px;
  opacity: 0.7;
}

/* ============ Link bar（非 sticky） ============ */
.link-bar-shell {
  margin: 0;
}

/* ============ Posts body ============ */
.posts-body {
  min-height: 200px;
}

.posts-view {
  /* 防止子元素溢出挤压卡片布局 */
  max-width: 100%;
  min-width: 0;
}

.posts-grid {
  margin: 0 !important;
  max-width: 100%;
}

.posts-grid > [class*="el-col"] {
  min-width: 0;
}

/* ============ 加载更多 ============ */
.load-more {
  margin: 24px auto 12px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.load-info {
  font-size: 12px;
  color: var(--color-muted-foreground);
  font-family: var(--font-heading);
  font-variant-numeric: tabular-nums;
}
.load-info strong {
  color: var(--color-foreground);
  font-weight: 600;
}

.load-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: center;
}

.load-btn {
  min-width: 140px;
}

.load-end {
  font-size: 12px;
  color: var(--color-muted-foreground);
  font-family: var(--font-heading);
  letter-spacing: 1px;
}

/* ============ 预览弹窗 ============ */
.preview-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.preview-meta {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 12px 16px;
  background: var(--color-muted);
  border-radius: var(--radius-md);
}
.preview-meta .meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--color-muted-foreground);
}
.preview-cover {
  width: 100%;
  max-height: 300px;
  object-fit: cover;
  border-radius: var(--radius-md);
}
.link-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--color-foreground);
}
.link-text {
  word-break: break-all;
  font-family: var(--font-heading);
  font-size: 12px;
  line-height: 1.6;
}

.links-textarea :deep(textarea) {
  font-family: var(--font-heading) !important;
  font-size: 13px !important;
  line-height: 1.6 !important;
}

.empty-state {
  padding: 60px 20px;
}
.empty-illustration {
  width: 80px;
  height: 80px;
  margin: 0 auto;
  color: var(--color-muted-foreground);
  opacity: 0.5;
}

/* ============ 响应式 ============ */
@media (max-width: 1100px) {
  .filter-row-secondary {
    flex-direction: column;
    align-items: stretch;
  }
  .reset-btn {
    align-self: flex-end;
  }
}
</style>