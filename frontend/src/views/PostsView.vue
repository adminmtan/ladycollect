<template>
  <div class="posts-view">
    <!-- 筛选卡片 -->
    <div class="glass-card filter-card">
      <div class="filter-header">
        <div class="filter-title">
          <el-icon><Filter /></el-icon>
          <span>筛选条件</span>
        </div>
        <el-button size="small" text @click="reset">
          <el-icon><Refresh /></el-icon>
          重置
        </el-button>
      </div>
      <el-form :inline="true" size="default" class="filter-form">
        <el-form-item label="站点">
          <el-select v-model="filters.site_id" placeholder="全部站点" clearable style="width: 180px" @change="onFiltersChange">
            <el-option v-for="s in sites" :key="s.id" :label="`${s.name} (${s.host})`" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键字">
          <el-input v-model="filters.keyword" placeholder="搜索标题" clearable style="width: 200px" @keyup.enter="onFiltersChange" />
        </el-form-item>
        <el-form-item label="发布日期">
          <el-date-picker
            v-model="postDateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="~"
            start-placeholder="起"
            end-placeholder="止"
            @change="onFiltersChange"
          />
        </el-form-item>
        <el-form-item label="入库日期">
          <el-date-picker
            v-model="createdRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="~"
            start-placeholder="起"
            end-placeholder="止"
            @change="onFiltersChange"
          />
        </el-form-item>
        <el-form-item label="排序">
          <el-select v-model="filters.sort" style="width: 170px" @change="onFiltersChange">
            <el-option label="入库时间（新→旧）" value="created_desc" />
            <el-option label="入库时间（旧→新）" value="created_asc" />
            <el-option label="发布日期（新→旧）" value="post_date_desc" />
            <el-option label="发布日期（旧→新）" value="post_date_asc" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-checkbox v-model="filters.has_magnet" :true-value="true" :false-value="undefined" @change="onFiltersChange">magnet</el-checkbox>
          <el-checkbox v-model="filters.has_ed2k" :true-value="true" :false-value="undefined" @change="onFiltersChange">ed2k</el-checkbox>
        </el-form-item>
      </el-form>
    </div>

    <!-- 工具条 -->
    <LinkCopyBar
      ref="linkBarRef"
      :selected-ids="selectedIds"
      :total="store.total"
      @copy="onCopy"
      @select-all="selectAll"
      @select-none="selectedIds = []"
      @delete="onDeleteBatch"
    />

    <!-- 空状态 -->
    <el-empty v-if="!store.loading && !store.items.length" description="暂无帖子" class="empty-state">
      <template #image>
        <div class="empty-illustration">
          <svg width="80" height="80" viewBox="0 0 24 24" fill="none">
            <path d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
      </template>
    </el-empty>

    <!-- 列表 -->
    <el-row :gutter="12" v-else>
      <el-col v-for="p in store.items" :key="p.id" :xs="24" :sm="12" :md="8" :lg="6" style="margin-bottom: 12px">
        <PostCard
          :post="p"
          selectable
          deletable
          v-model="selected[p.id]"
          @update:modelValue="syncSelection"
          @deleted="onDeletePost"
          @disliked="onDislikedPost"
          @liked="onLikedPost"
        />
      </el-col>
    </el-row>

    <!-- 加载更多 -->
    <div v-if="store.items.length < store.total" class="load-more">
      <el-button @click="loadMore" :loading="store.loading" class="btn-accent">
        加载更多（{{ store.items.length }}/{{ store.total }}）
      </el-button>
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Filter, Refresh, Calendar, User, Link, Connection } from '@element-plus/icons-vue'
import { useSiteStore } from '@/stores/sites'
import { usePostStore, type PostQuery } from '@/stores/posts'
import { postsApi } from '@/api'
import LinkCopyBar from '@/components/LinkCopyBar.vue'
import PostCard from '@/components/PostCard.vue'

const siteStore = useSiteStore()
const sites = computed(() => siteStore.sites)
const store = usePostStore()

// 筛选条件
const filters = reactive<PostQuery>({
  site_id: undefined,
  keyword: '',
  has_magnet: undefined,
  has_ed2k: undefined,
  sort: 'created_desc',
})

const postDateRange = ref<[string, string] | null>(null)
const createdRange = ref<[string, string] | null>(null)

// 选择状态
const selected = reactive<Record<number, boolean>>({})
const selectedIds = computed(() =>
  Object.entries(selected)
    .filter(([, v]) => v)
    .map(([k]) => Number(k)),
)

function reset() {
  Object.assign(filters, {
    site_id: undefined,
    keyword: '',
    has_magnet: undefined,
    has_ed2k: undefined,
    sort: 'created_desc',
  })
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
    page_size: 24,
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

async function onFiltersChange() {
  await fetchPosts()
}

function selectAll() {
  for (const p of store.items) selected[p.id] = true
}

function syncSelection() {
  /* 触发 selectedIds 重新计算 */
}

async function onDeletePost(postId: number) {
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

async function onDislikedPost(payload: { postId: number; ruleId: number; keywords: string[]; extractor: string }) {
  // dislike 端点已经把 post 删了，前端只需从列表移除 + 更新计数
  const i = store.items.findIndex((x) => x.id === payload.postId)
  if (i !== -1) store.items.splice(i, 1)
  store.total = Math.max(0, store.total - 1)
  // 同步清掉选择状态
  delete selected[payload.postId]
}

async function onLikedPost(payload: { postId: number; ruleId: number; keywords: string[]; extractor: string }) {
  // like 不删除 post，只把信息记到 console 方便调试
  // 前端无需额外操作，PostCard 已显示 toast
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
    if (store.items.length < 24 && store.items.length < store.total) {
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

onMounted(async () => {
  await siteStore.fetch()
  await fetchPosts()
})
</script>

<style scoped>
.posts-view {
  width: 100%;
}

/* 筛选卡片 */
.filter-card {
  padding: 20px;
  margin-bottom: 20px;
}

.filter-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.filter-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-foreground);
}

.filter-title .el-icon {
  color: var(--color-accent);
}

.filter-form {
  margin-top: 0;
}

/* 空状态 */
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

/* 加载更多 */
.load-more {
  text-align: center;
  margin-top: 24px;
}

/* 预览弹窗 */
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

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--color-muted-foreground);
}

.open-link {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--color-accent);
  transition: opacity var(--transition-fast);
}

.open-link:hover {
  opacity: 0.8;
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

/* 下载链接弹窗 */
.links-textarea :deep(textarea) {
  font-family: var(--font-heading) !important;
  font-size: 13px !important;
  line-height: 1.6 !important;
}
</style>
