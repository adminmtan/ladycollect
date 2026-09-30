<template>
  <div class="post-card" :class="{ 'is-selected': checked, 'is-fading': fading }">
    <!-- 左上角选择框 -->
    <el-checkbox v-if="selectable" v-model="checked" class="post-checkbox" />

    <!-- 右上角站点角标 -->
    <div v-if="siteName" class="post-site-badge">
      <el-icon style="margin-right: 4px"><Compass /></el-icon>
      <span class="post-site-badge-name">{{ siteName }}</span>
    </div>

    <!-- hover 浮出：喜欢 / 不喜欢 / 删除 三件套 -->
    <div class="post-actions" v-if="!hideActions">
      <el-button
        class="action-btn action-btn-like"
        size="small"
        type="success"
        plain
        circle
        :loading="loadingLike"
        :title="'喜欢（加入 include 学习）'"
        @click.stop="onLike"
      >
        <el-icon><Star /></el-icon>
      </el-button>
      <el-button
        class="action-btn action-btn-dislike"
        size="small"
        type="danger"
        plain
        circle
        :loading="loadingDislike"
        :title="'不喜欢（自动学习 exclude 规则）'"
        @click.stop="onDislike"
      >
        <el-icon><CloseBold /></el-icon>
      </el-button>
      <el-button
        v-if="deletable"
        class="action-btn action-btn-delete"
        size="small"
        type="info"
        plain
        circle
        title="直接删除（不学习）"
        @click.stop="onDelete"
      >
        <el-icon><Delete /></el-icon>
      </el-button>
    </div>

    <!-- 封面 -->
    <a :href="post.url" target="_blank" class="post-card-cover-wrap">
      <img
        v-if="post.cover && !imgFailed"
        :src="post.cover"
        class="post-card-cover"
        referrerpolicy="strict-origin-when-cross-origin"
        loading="lazy"
        @error="onImgError"
      />
      <div v-else class="post-card-cover post-card-cover--placeholder">
        <el-icon style="font-size: 32px; margin-bottom: 4px"><Picture /></el-icon>
        <span v-if="post.cover && imgFailed">封面加载失败</span>
        <span v-else>暂无封面</span>
      </div>
    </a>

    <div class="post-card-body">
      <!-- 标题 -->
      <a :href="post.url" target="_blank" class="post-card-title" :title="post.title">
        {{ post.title || '(无标题)' }}
      </a>

      <!-- 元信息 -->
      <div class="post-card-meta">
        <span class="meta-item">
          <el-icon><Calendar /></el-icon>
          <span>{{ formatPostDate(post.created_at) }}</span>
        </span>
        <span v-if="post.post_date" class="meta-item meta-date">
          <el-icon><Clock /></el-icon>
          <span>{{ formatPostDate(post.post_date) }}</span>
        </span>
      </div>

      <!-- 链接标签 -->
      <div class="post-card-tags">
        <span v-if="magnetCount > 0" class="link-tag tag-magnet">
          <el-icon style="margin-right: 3px"><Link /></el-icon>
          magnet × {{ magnetCount }}
        </span>
        <span v-if="ed2kCount > 0" class="link-tag tag-ed2k">
          <el-icon style="margin-right: 3px"><Connection /></el-icon>
          ed2k × {{ ed2kCount }}
        </span>
        <span v-if="magnetCount === 0 && ed2kCount === 0" class="link-tag tag-empty">
          暂无下载链接
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Calendar,
  Clock,
  Compass,
  Connection,
  Delete,
  Link,
  Picture,
  Star,
  CloseBold,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { feedbackApi, type Post } from '@/api'
import { useSiteStore } from '@/stores/sites'

const props = defineProps<{
  post: Post
  selectable?: boolean
  deletable?: boolean
  modelValue?: boolean
  hideActions?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'deleted', postId: number): void
  (e: 'disliked', payload: { postId: number; ruleId: number; keywords: string[]; extractor: string }): void
  (e: 'liked', payload: { postId: number; ruleId: number; keywords: string[]; extractor: string }): void
  (e: 'open-curate', payload: { postId: number }): void
}>()

const siteStore = useSiteStore()
const checked = computed({
  get: () => props.modelValue ?? false,
  set: (v) => emit('update:modelValue', v),
})

const imgFailed = ref(false)
const fading = ref(false)
const loadingLike = ref(false)
const loadingDislike = ref(false)

function onImgError() {
  imgFailed.value = true
}

function fadeOut() {
  fading.value = true
  setTimeout(() => {
    fading.value = false
  }, 350)
}

async function onDelete() {
  try {
    await ElMessageBox.confirm(
      `确定删除这篇帖子吗？\n\n${props.post.title?.slice(0, 60) || '(无标题)'}`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  emit('deleted', props.post.id)
}

async function onDislike() {
  // dislike 走弹窗：弹窗打开 mode=single，候选关键词 = AI 对该帖输出的关键词
  // 用户在弹窗里可编辑/确认，确认后关键词写入规则 + 帖子被删除
  emit('open-curate', { postId: props.post.id })
}

async function onLike() {
  loadingLike.value = true
  try {
    const res = await feedbackApi.like(props.post.id)
    ElMessage.success({
      message: `已收藏：提取 ${res.keywords_added?.length || 0} 个关键词到 include 规则（来源：${res.extractor === 'ai' ? 'AI' : '本地规则'}）`,
      duration: 3500,
    })
    emit('liked', {
      postId: props.post.id,
      ruleId: res.rule_id,
      keywords: res.keywords_added,
      extractor: res.extractor,
    })
  } catch (e: any) {
    ElMessage.error(e.message || '操作失败')
  } finally {
    loadingLike.value = false
  }
}

const siteName = computed(() => {
  const site = siteStore.sites.find((s) => s.id === props.post.site_id)
  return site?.name || site?.host || ''
})

const magnetCount = computed(() => props.post.magnet?.length || 0)
const ed2kCount = computed(() => props.post.ed2k?.length || 0)

function formatPostDate(s: string): string {
  const d = parseDate(s)
  if (!d) return s
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function parseDate(s: string): Date | null {
  if (!s) return null
  const d = new Date(s)
  if (!Number.isNaN(d.getTime())) return d
  const m = s.match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/)
  if (m) {
    return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]))
  }
  const m2 = s.match(/(\d{4})-(\d{2})-(\d{2})/)
  if (m2) return new Date(Number(m2[1]), Number(m2[2]) - 1, Number(m2[3]))
  return null
}
</script>

<style scoped>
.post-card {
  position: relative;
  background: linear-gradient(135deg, var(--color-card) 0%, rgba(27, 35, 54, 0.8) 100%);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: all var(--transition-normal);
  display: flex;
  flex-direction: column;
  height: 100%;
}

.post-card:hover {
  border-color: rgba(255, 255, 255, 0.15);
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}

.post-card.is-selected {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.2);
}

.post-card.is-fading {
  opacity: 0;
  transform: scale(0.96);
  pointer-events: none;
}

/* 复选框 */
.post-checkbox {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 3;
  background: rgba(15, 23, 42, 0.85);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  backdrop-filter: blur(4px);
}

.post-checkbox :deep(.el-checkbox__inner) {
  background: var(--color-muted);
  border-color: var(--color-border);
}

.post-checkbox :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background: var(--color-accent);
  border-color: var(--color-accent);
}

/* 站点徽章 */
.post-site-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 3;
  display: inline-flex;
  align-items: center;
  max-width: calc(100% - 130px);
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.9) 0%, rgba(99, 102, 241, 0.9) 100%);
  border-radius: var(--radius-sm);
  backdrop-filter: blur(4px);
}

.post-site-badge-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 操作按钮组 */
.post-actions {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 4;
  display: flex;
  gap: 6px;
  opacity: 0;
  transform: translateY(-4px);
  transition: all var(--transition-normal);
}

/* 卡片有站点徽章时，操作按钮移到下一行 */
.post-card:has(.post-site-badge) .post-actions {
  top: 42px;
}

.post-card:hover .post-actions {
  opacity: 1;
  transform: translateY(0);
}

.action-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  background: rgba(15, 23, 42, 0.85) !important;
  backdrop-filter: blur(4px);
  transition: all var(--transition-fast);
}

.action-btn-like:hover {
  background: rgba(34, 197, 94, 0.2) !important;
  transform: scale(1.1);
}

.action-btn-dislike:hover {
  background: rgba(239, 68, 68, 0.2) !important;
  transform: scale(1.1);
}

.action-btn-delete:hover {
  background: rgba(148, 163, 184, 0.2) !important;
  transform: scale(1.1);
}

/* 封面 */
.post-card-cover-wrap {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: var(--color-muted);
  position: relative;
}

.post-card-cover {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform var(--transition-slow);
}

.post-card-cover-wrap:hover .post-card-cover {
  transform: scale(1.05);
}

.post-card-cover--placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--color-muted-foreground);
  font-size: 12px;
}

/* 主体 */
.post-card-body {
  padding: 14px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
}

.post-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-foreground);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-decoration: none;
  transition: color var(--transition-fast);
}

.post-card-title:hover {
  color: var(--color-accent);
}

/* 元信息 */
.post-card-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: var(--color-muted-foreground);
  line-height: 1.5;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.meta-item .el-icon {
  font-size: 14px;
}

.meta-date {
  color: var(--color-muted-foreground);
  opacity: 0.8;
}

/* 链接标签 */
.post-card-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: auto;
  padding-top: 4px;
}

.link-tag {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 20px;
  transition: all var(--transition-fast);
}

.tag-magnet {
  background: rgba(34, 197, 94, 0.15);
  color: var(--color-accent);
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.tag-magnet:hover {
  background: rgba(34, 197, 94, 0.25);
}

.tag-ed2k {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.tag-ed2k:hover {
  background: rgba(245, 158, 11, 0.25);
}

.tag-empty {
  background: var(--color-muted);
  color: var(--color-muted-foreground);
  border: 1px solid rgba(255, 255, 255, 0.06);
}
</style>
