import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', component: () => import('@/views/LoginView.vue'), name: 'login', meta: { public: true } },
  { path: '/', component: () => import('@/views/DashboardView.vue'), name: 'dashboard' },
  { path: '/sites', component: () => import('@/views/SitesView.vue'), name: 'sites' },
  { path: '/tasks', component: () => import('@/views/TasksView.vue'), name: 'tasks' },
  { path: '/tasks/:id/jobs', component: () => import('@/views/TaskJobsView.vue'), name: 'task-jobs' },
  { path: '/posts', component: () => import('@/views/PostsView.vue'), name: 'posts' },
  { path: '/filter-rules', component: () => import('@/views/FilterRulesView.vue'), name: 'filter-rules' },
  { path: '/settings', component: () => import('@/views/SettingsView.vue'), name: 'settings' },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

let mePromise: Promise<any> | null = null

async function ensureMe() {
  const auth = useAuthStore()
  if (auth.user) return auth.user
  if (!mePromise) {
    mePromise = auth.fetchMe().catch((e) => {
      mePromise = null
      throw e
    })
  }
  return mePromise.finally(() => { mePromise = null; mePromise = null })
}

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  // 已登录的访问 /login 直接送回主页
  if (to.name === 'login' && auth.isAuthenticated) {
    try { await ensureMe() } catch {}
    if (auth.isAuthenticated) return { path: (to.query.next as string) || '/' }
  }
  // 公开页：放行
  if (to.meta?.public) return true
  // 没 token：直接跳登录
  if (!auth.isAuthenticated) {
    return { path: '/login', query: { next: to.fullPath } }
  }
  // 有 token 但还没 hydrate user：先 /api/auth/me
  if (!auth.user) {
    try {
      await ensureMe()
    } catch (e) {
      auth.clear()
      return { path: '/login', query: { next: to.fullPath } }
    }
  }
  return true
})

export default router
