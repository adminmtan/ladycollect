/** Pinia auth store: token + 当前用户 + 守卫 */
import { defineStore } from 'pinia'
import { authApi, type AuthUser } from '@/api'

const TOKEN_KEY = 'cp_token'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '' as string,
    user: null as AuthUser | null,
    initialized: false as boolean,
  }),
  getters: {
    isAuthenticated: (s) => !!s.token,
    mustChangePassword: (s) => !!s.user?.must_change_password,
  },
  actions: {
    setToken(t: string) {
      this.token = t
      localStorage.setItem(TOKEN_KEY, t)
    },
    clear() {
      this.token = ''
      this.user = null
      localStorage.removeItem(TOKEN_KEY)
    },
    async checkInitialized() {
      const { initialized } = await authApi.initialized()
      this.initialized = initialized
      return initialized
    },
    async fetchMe() {
      try {
        this.user = await authApi.me()
        return this.user
      } catch (e) {
        this.clear()
        throw e
      }
    },
    async login(username: string, password: string) {
      const r = await authApi.login({ username, password })
      this.setToken(r.token)
      this.user = r.user
      return r
    },
    async logout() {
      try { await authApi.logout() } catch {}
      this.clear()
    },
    async changePassword(current_password: string, new_password: string) {
      await authApi.changePassword({ current_password, new_password })
      if (this.user) this.user.must_change_password = false
    },
    async setup(username: string, password: string) {
      await authApi.setup({ username, password })
      this.initialized = true
    },
  },
})
