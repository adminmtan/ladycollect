import { defineStore } from 'pinia'
import { ref } from 'vue'
import { postsApi, type Post, type PostPage } from '@/api'

export type PostSort = 'created_desc' | 'created_asc' | 'post_date_desc' | 'post_date_asc'

export interface PostQuery {
  site_id?: number
  keyword?: string
  date_from?: string
  date_to?: string
  has_magnet?: boolean
  has_ed2k?: boolean
  job_id?: number
  // 入库日期（Post.created_at）
  created_from?: string
  created_to?: string
  // 排序
  sort?: PostSort
  page?: number
  page_size?: number
}

export const usePostStore = defineStore('posts', () => {
  const items = ref<Post[]>([])
  const total = ref(0)
  const loading = ref(false)
  const query = ref<PostQuery>({ page: 1, page_size: 24, sort: 'created_desc' })

  // 请求代际计数器：每次 fetch() 入口自增，loadMore() / fetch() 内部 await 后
  // 比较捕获的 token 是否仍是最新，避免旧请求的响应覆盖新请求的状态（orders 反
  // 序覆盖乱序）。典型场景：用户在 loadAll 进行中切换筛选条件，或 lAll 循环
  // 里某一页响应超时后新 fetch 已经重置 items。
  let generation = 0

  async function fetch(q: PostQuery = {}) {
    const myGen = ++generation
    loading.value = true
    try {
      query.value = { page: 1, page_size: 24, ...q }
      const data: PostPage = await postsApi.list(query.value)
      // 丢弃旧请求的响应（用户已在更晚一次 fetch 中重置了列表）
      if (myGen !== generation) return
      items.value = data.items
      total.value = data.total
    } finally {
      if (myGen === generation) loading.value = false
    }
  }

  async function loadMore() {
    const myGen = generation
    loading.value = true
    try {
      query.value.page = (query.value.page || 1) + 1
      const data = await postsApi.list(query.value)
      // 丢弃旧请求的响应（重置后 page 已经被重置为 1，旧的 page=N+1 响应没意义）
      if (myGen !== generation) return
      items.value = items.value.concat(data.items)
      total.value = data.total
    } finally {
      if (myGen === generation) loading.value = false
    }
  }

  function reset() {
    items.value = []
    total.value = 0
    query.value = { page: 1, page_size: 24 }
  }

  async function copyLinks(postIds: number[], kinds: string[] = ['magnet', 'ed2k']) {
    const text = await postsApi.copyLinksText(postIds, kinds)
    try {
      await navigator.clipboard.writeText(text)
    } catch (e) {
      // 浏览器拒绝时回退到临时 textarea
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      try {
        document.execCommand('copy')
      } catch (e2) {
        console.warn('复制失败：', e2)
      }
      document.body.removeChild(ta)
    }
    return text
  }

  return { items, total, loading, query, fetch, loadMore, copyLinks, reset }
})
