import axios from 'axios'

const api = axios.create({
  baseURL: '/',
  timeout: 30000,
})

// Token 注入：每次请求带 Bearer
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('cp_token')
  if (token) {
    config.headers = config.headers || {}
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    // 优先带出详细诊断信息（解决「保存 Network Error 但同源 GET 正常」的排查）
    let detail = ''
    if (err?.response) {
      // 服务器返回了 HTTP 状态码
      detail = err.response.data?.detail || err.response.data?.message || err.response.statusText
    } else if (err?.request) {
      // 请求发出去但没收到响应：网络层 / 代理 / CORS preflight 失败 / 服务进程死亡
      detail = `请求无响应（Network Error）— ${err.message || 'unknown'}`
    } else {
      detail = err?.message || '请求失败'
    }
    // 401 → 跳登录
    if (err?.response?.status === 401 && !window.location.pathname.startsWith('/login')) {
      localStorage.removeItem('cp_token')
      const next = encodeURIComponent(window.location.pathname + window.location.search)
      window.location.replace(`/login?next=${next}`)
    }
    return Promise.reject(new Error(detail || '请求失败'))
  },
)

export interface Site {
  id: number
  name: string
  host: string
  base_url: string
  user_agent?: string | null
  cookies?: string | null
  proxy?: string | null
  fingerprint_seed?: number | null
  adapter?: 'onemei' | 'sehuatang' | null
  forum_fid?: string | null
  list_urls?: string[] | null
  enabled: boolean
  note?: string | null
  created_at: string
  updated_at: string
}

export interface SiteCreate extends Omit<Site, 'id' | 'created_at' | 'updated_at'> {}

export interface SiteUpdate {
  name?: string
  host?: string
  base_url?: string
  user_agent?: string | null
  cookies?: string | null
  proxy?: string | null
  fingerprint_seed?: number | null
  adapter?: 'onemei' | 'sehuatang' | null
  forum_fid?: string | null
  list_urls?: string[] | null
  enabled?: boolean
  note?: string | null
}

export interface Task {
  id: number
  site_ids: number[]
  name: string
  kind: 'list_all' | 'list_search' | 'list_date' | 'list_category'
  keyword?: string | null
  date_from?: string | null
  date_to?: string | null
  category?: string | null
  max_pages: number
  max_concurrent: number
  only_with_links: boolean
  cron?: string | null
  schedule_enabled: boolean
  name_template?: string | null
  next_run_at?: string | null
  last_run_at?: string | null
  status: string
  running_job_id?: number | null
  created_at: string
}

export interface TaskCreate extends Omit<Task, 'id' | 'status' | 'created_at' | 'next_run_at' | 'last_run_at'> {}

export interface TaskUpdate {
  site_ids?: number[]
  name?: string
  kind?: string
  keyword?: string | null
  date_from?: string | null
  date_to?: string | null
  category?: string | null
  max_pages?: number
  max_concurrent?: number
  only_with_links?: boolean
  cron?: string | null
  schedule_enabled?: boolean
  name_template?: string | null
}

export interface Job {
  id: number
  task_id: number
  display_name?: string | null
  status: string
  progress_pages: number
  progress_posts: number
  posts_saved: number
  error?: string | null
  log: any[]
  started_at?: string | null
  finished_at?: string | null
  created_at: string
}

export interface JobFolder {
  job_id: number
  task_id: number
  display_name?: string | null
  task_name: string
  status: string
  posts_count: number
  progress_pages?: number
  progress_posts?: number
  error?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at: string
}

export interface JobFolderPage {
  items: JobFolder[]
  total: number
  page: number
  page_size: number
}

export interface Post {
  id: number
  site_id: number
  task_id?: number | null
  job_id?: number | null
  post_id: number
  slug: string
  url: string
  title: string
  author?: string | null
  post_date?: string | null
  cover?: string | null
  summary?: string | null
  magnet: string[]
  ed2k: string[]
  created_at: string
  updated_at: string
}

export interface PostPage {
  items: Post[]
  total: number
  page: number
  page_size: number
}

export interface OverviewStats {
  total_posts: number
  with_magnet: number
  with_ed2k: number
  total_sites: number
  total_tasks: number
  total_jobs: number
  recent_posts_7d: number
}

export const sitesApi = {
  list: () => api.get<Site[]>('/api/sites').then((r) => r.data),
  create: (payload: SiteCreate) => api.post<Site>('/api/sites', payload).then((r) => r.data),
  update: (id: number, payload: Partial<SiteCreate>) =>
    api.patch<Site>(`/api/sites/${id}`, payload).then((r) => r.data),
  remove: (id: number) => api.delete(`/api/sites/${id}`).then((r) => r.data),
  probe: (id: number) => api.post(`/api/sites/${id}/probe`).then((r) => r.data),
}

export const tasksApi = {
  list: (site_id?: number) =>
    api.get<Task[]>('/api/tasks', { params: site_id ? { site_id } : {} }).then((r) => r.data),
  create: (payload: TaskCreate) => api.post<Task>('/api/tasks', payload).then((r) => r.data),
  update: (id: number, payload: TaskUpdate) => api.patch<Task>(`/api/tasks/${id}`, payload).then((r) => r.data),
  remove: (id: number) => api.delete(`/api/tasks/${id}`).then((r) => r.data),
  run: (id: number, use_browser?: boolean) =>
    api
      .post(`/api/tasks/${id}/run`, null, { params: use_browser === undefined ? {} : { use_browser } })
      .then((r) => r.data),
  stop: (id: number) => api.post(`/api/tasks/${id}/stop`).then((r) => r.data),
  listJobs: (id: number) => api.get<Job[]>(`/api/tasks/${id}/jobs`).then((r) => r.data),
  getJob: (jobId: number) => api.get<Job>(`/api/tasks/jobs/${jobId}`).then((r) => r.data),
}

export const postsApi = {
  list: (params: {
    site_id?: number
    keyword?: string
    date_from?: string
    date_to?: string
    has_magnet?: boolean
    has_ed2k?: boolean
    job_id?: number
    created_from?: string
    created_to?: string
    sort?: 'created_desc' | 'created_asc' | 'post_date_desc' | 'post_date_asc'
    page?: number
    page_size?: number
  }) => api.get<PostPage>('/api/posts', { params }).then((r) => r.data),
  /** 按当前筛选条件取「全部 Post id」（用于「复制文本」弹窗展示全量链接） */
  allIds: (params: {
    site_id?: number
    keyword?: string
    date_from?: string
    date_to?: string
    has_magnet?: boolean
    has_ed2k?: boolean
    job_id?: number
    created_from?: string
    created_to?: string
    sort?: 'created_desc' | 'created_asc' | 'post_date_desc' | 'post_date_asc'
  }) =>
    api
      .get<{ ids: number[]; total: number; truncated: boolean }>('/api/posts/all-ids', { params })
      .then((r) => r.data),
  listFolders: (params: { site_id?: number; task_id?: number; page?: number; page_size?: number }) =>
    api.get<JobFolderPage>('/api/posts/jobs/folders', { params }).then((r) => r.data),
  get: (id: number) => api.get<Post>(`/api/posts/${id}`).then((r) => r.data),
  /** 单条删除 Post */
  remove: (id: number) => api.delete(`/api/posts/${id}`).then((r) => r.data),
  copyLinksText: (post_ids: number[], kinds: string[] = ['magnet', 'ed2k']) =>
    api.post('/api/posts/copy-links/text', { post_ids, kinds }, { responseType: 'text' }).then((r) => r.data),

  /** 重新访问详情页，补抓 cover / post_date / magnet / ed2k（只回填空字段，不破坏已有数据） */
  recrawl: (post_ids: number[]) =>
    api.post<{ updated: number; failed: number; items: any[] }>('/api/posts/recrawl', { post_ids }).then((r) => r.data),

  /** 批量删除 Post（请求体带 ids） */
  removeMany: (post_ids: number[]) =>
    api.delete<{ ok: boolean; deleted: number }>('/api/posts', { data: { post_ids } }).then((r) => r.data),

  /** 删除整个 JobFolder（连带其 Post；Task 保留） */
  removeFolder: (job_id: number) =>
    api.delete<{ ok: boolean; deleted_posts: number; deleted_job: number }>(
      `/api/posts/jobs/${job_id}`,
    ).then((r) => r.data),
}

export const statsApi = {
  overview: () => api.get<OverviewStats>('/api/stats/overview').then((r) => r.data),
  recentJobs: (limit = 10) => api.get<Job[]>('/api/stats/recent-jobs', { params: { limit } }).then((r) => r.data),
}

// ============== 智能过滤规则 ==============
export interface FilterKeyword {
  id: number
  rule_id: number
  keyword: string
  source: 'manual' | 'learned' | 'user_dislike' | 'user_like'
  weight: number
  hit_count: number
  created_at: string
}

export interface FilterRuleSummary {
  id: number
  name: string
  scope: 'site' | 'global'
  site_id?: number | null
  rule_type: 'exclude' | 'include' | 'tag'
  enabled: boolean
  note?: string | null
  keyword_count: number
  hit_count_total: number
  created_at: string
  updated_at: string
}

export interface FilterRule extends FilterRuleSummary {
  keywords: FilterKeyword[]
}

export interface FilterRuleCreate {
  name: string
  scope: 'site' | 'global'
  site_id?: number | null
  rule_type: 'exclude' | 'include' | 'tag'
  enabled?: boolean
  note?: string | null
  keywords?: string[]
}

export interface FilterRuleUpdate {
  name?: string
  scope?: 'site' | 'global'
  site_id?: number | null
  rule_type?: 'exclude' | 'include' | 'tag'
  enabled?: boolean
  note?: string | null
}

export interface UserFeedback {
  id: number
  post_id?: number | null
  site_id?: number | null
  title: string
  action: 'dislike' | 'like'
  keywords_extracted: string[]
  rule_id?: number | null
  rule_type?: string | null
  note?: string | null
  created_at: string
}

export interface DislikeResponse {
  ok: boolean
  rule_id: number
  rule_name: string
  keywords_added: string[]
  extractor: 'ai' | 'local'
  post_deleted: boolean
}

export interface LikeResponse {
  ok: boolean
  rule_id: number
  rule_name: string
  keywords_added: string[]
  extractor: 'ai' | 'local'
  post_deleted: boolean
}

export const filterRulesApi = {
  list: (params?: { site_id?: number; scope?: string; rule_type?: string; enabled?: boolean }) =>
    api.get<FilterRuleSummary[]>('/api/filter-rules', { params }).then((r) => r.data),
  get: (id: number) => api.get<FilterRule>(`/api/filter-rules/${id}`).then((r) => r.data),
  create: (payload: FilterRuleCreate) =>
    api.post<FilterRule>('/api/filter-rules', payload).then((r) => r.data),
  update: (id: number, payload: FilterRuleUpdate) =>
    api.patch<FilterRule>(`/api/filter-rules/${id}`, payload).then((r) => r.data),
  remove: (id: number) => api.delete(`/api/filter-rules/${id}`).then((r) => r.data),
  addKeywords: (id: number, keywords: string[]) =>
    api
      .post<FilterKeyword[]>(`/api/filter-rules/${id}/keywords`, { keywords })
      .then((r) => r.data),
  deleteKeyword: (ruleId: number, keywordId: number) =>
    api.delete(`/api/filter-rules/${ruleId}/keywords/${keywordId}`).then((r) => r.data),
}

export const feedbackApi = {
  dislike: (postId: number, ruleId?: number) =>
    api
      .post<DislikeResponse>(`/api/posts/${postId}/dislike`, ruleId ? { rule_id: ruleId } : {})
      .then((r) => r.data),
  like: (postId: number, ruleId?: number) =>
    api
      .post<LikeResponse>(`/api/posts/${postId}/like`, ruleId ? { rule_id: ruleId } : {})
      .then((r) => r.data),
  history: (params?: { site_id?: number; action?: string; rule_id?: number; limit?: number }) =>
    api.get<UserFeedback[]>('/api/feedback', { params }).then((r) => r.data),
}

// ============== App Settings ==============
export interface AppSetting {
  key: string
  value: string | null
  masked: boolean
  source: 'db' | 'default'
  updated_at: string | null
  // _meta 才有下面三个
  label?: string
  description?: string
  placeholder?: string
}

export interface AppSettingTestResponse {
  ok: boolean
  message: string
  latency_ms?: number | null
  model_reply?: string | null
}

export const settingsApi = {
  list: () => api.get<AppSetting[]>('/api/settings').then((r) => r.data),
  meta: () => api.get<AppSetting[]>('/api/settings/_meta').then((r) => r.data),
  update: (key: string, value: string | null) =>
    api.put<AppSetting>(`/api/settings/${key}`, { value }).then((r) => r.data),
  test: (payload: { base_url?: string; api_key?: string; model?: string; timeout?: number }) =>
    api.post<AppSettingTestResponse>('/api/settings/test', payload).then((r) => r.data),
}

// ============== Auth ==============
export interface AuthUser {
  id: number
  username: string
  role: 'admin' | 'user'
  must_change_password: boolean
}

export const authApi = {
  initialized: () =>
    api.get<{ initialized: boolean }>('/api/auth/initialized').then((r) => r.data),
  setup: (payload: { username: string; password: string }) =>
    api.post<{ ok: boolean }>('/api/auth/setup', payload).then((r) => r.data),
  login: (payload: { username: string; password: string }) =>
    api
      .post<{ token: string; user: AuthUser; must_change_password: boolean }>(
        '/api/auth/login',
        payload,
      )
      .then((r) => r.data),
  me: () => api.get<AuthUser>('/api/auth/me').then((r) => r.data),
  logout: () => api.post<{ ok: boolean }>('/api/auth/logout').then((r) => r.data),
  changePassword: (payload: { current_password: string; new_password: string }) =>
    api.post<{ ok: boolean }>('/api/auth/change-password', payload).then((r) => r.data),
}

export default api
