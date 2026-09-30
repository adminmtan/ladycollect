<template>
  <!-- 公开页（登录、初始化等）直接铺满全屏 -->
  <router-view v-if="$route.meta?.layout === 'blank'" />

  <!-- 其他页面套侧栏 + 顶栏布局 -->
  <el-container v-else class="app-container">
    <!-- 侧边导航 -->
    <el-aside class="sidebar">
      <!-- Logo 区域 -->
      <div class="sidebar-logo">
        <div class="logo-icon">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" fill="currentColor"/>
          </svg>
        </div>
        <span class="logo-text">采集管理</span>
      </div>

      <!-- 导航菜单 -->
      <el-menu
        :default-active="$route.path"
        router
        class="sidebar-menu"
      >
        <el-menu-item index="/">
          <el-icon><DataLine /></el-icon>
          <span>总览</span>
        </el-menu-item>
        <el-menu-item index="/sites">
          <el-icon><Setting /></el-icon>
          <span>站点配置</span>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><Operation /></el-icon>
          <span>采集任务</span>
        </el-menu-item>
        <el-menu-item index="/posts">
          <el-icon><Document /></el-icon>
          <span>采集结果</span>
        </el-menu-item>
        <el-menu-item index="/filter-rules">
          <el-icon><Filter /></el-icon>
          <span>过滤规则</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Tools /></el-icon>
          <span>设置</span>
        </el-menu-item>
      </el-menu>

      <!-- 底部：系统版本 / 引擎状态卡片 -->
      <div class="sidebar-footer">
        <SystemStatusCard />
        <el-button class="logout-btn" link @click="onLogout" v-if="auth.isAuthenticated">
          <el-icon><SwitchButton /></el-icon>
          登出 ({{ auth.user?.username }})
        </el-button>
      </div>
    </el-aside>

    <!-- 主内容区 -->
    <el-container class="main-container">
      <!-- 顶部栏 -->
      <el-header class="topbar">
        <div class="topbar-left">
          <span class="topbar-title">数据采集管理系统</span>
        </div>
        <div class="topbar-right">
          <span class="current-time">{{ now }}</span>
        </div>
      </el-header>

      <!-- 内容区 -->
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { DataLine, Setting, Operation, Document, Filter, Tools, SwitchButton } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import SystemStatusCard from '@/components/SystemStatusCard.vue'

const auth = useAuthStore()
const router = useRouter()
const now = ref(new Date().toLocaleString())

let timer: any = null
onMounted(() => {
  timer = setInterval(() => (now.value = new Date().toLocaleString()), 1000)
})
onBeforeUnmount(() => clearInterval(timer))

async function onLogout() {
  try {
    await ElMessageBox.confirm('确定登出？', '提示', { type: 'warning' })
  } catch {
    return
  }
  await auth.logout()
  router.replace('/login')
}
</script>

<style scoped>
.app-container {
  height: 100vh;
  background: var(--color-background);
}

/* 侧边栏 */
.sidebar {
  width: 240px !important;
  background: linear-gradient(180deg, var(--color-card) 0%, var(--color-background) 100%);
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.sidebar::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 200px;
  background: radial-gradient(ellipse at top, rgba(34, 197, 94, 0.08) 0%, transparent 70%);
  pointer-events: none;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 24px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.logo-icon {
  width: 44px;
  height: 44px;
  background: linear-gradient(135deg, var(--color-accent) 0%, #16a34a 100%);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-on-accent);
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.3);
}

.logo-text {
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 600;
  color: var(--color-foreground);
  letter-spacing: -0.5px;
}

.sidebar-menu {
  flex: 1;
  padding: 16px 12px;
  border: none;
  background: transparent;
}

.sidebar-menu :deep(.el-menu-item) {
  height: 48px;
  line-height: 48px;
  border-radius: var(--radius-md);
  margin-bottom: 4px;
  font-weight: 500;
  transition: all var(--transition-normal);
}

.sidebar-menu :deep(.el-menu-item) .el-icon {
  font-size: 18px;
  margin-right: 12px;
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.15) 0%, rgba(34, 197, 94, 0.08) 100%) !important;
  border: 1px solid rgba(34, 197, 94, 0.2);
}

.sidebar-menu :deep(.el-menu-item.is-active)::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 24px;
  background: var(--color-accent);
  border-radius: 0 2px 2px 0;
}

.sidebar-footer {
  padding: 16px 14px 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: relative;
}
.sidebar-footer::before {
  content: '';
  position: absolute;
  top: 0;
  left: 14px;
  right: 14px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(34, 197, 94, 0.35), transparent);
  opacity: 0.6;
}

.tech-badges {
  display: none;
}

.tech-badge {
  display: none;
}
.logout-btn {
  font-size: 12px;
  color: var(--color-muted-foreground);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  transition: color 0.15s, background 0.15s;
}
.logout-btn :deep(.el-icon) {
  font-size: 14px;
}
.logout-btn:hover {
  color: var(--color-accent);
  background: rgba(34, 197, 94, 0.08);
}

/* 主内容区 */
.main-container {
  display: flex;
  flex-direction: column;
  background: var(--color-background);
}

/* 顶部栏 */
.topbar {
  height: 64px !important;
  background: var(--color-card);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  position: relative;
}

.topbar::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(34, 197, 94, 0.3), transparent);
}

.topbar-left {
  display: flex;
  align-items: center;
}

.topbar-title {
  font-family: var(--font-heading);
  font-size: 14px;
  font-weight: 500;
  color: var(--color-muted-foreground);
  letter-spacing: 0.5px;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.current-time {
  font-family: var(--font-heading);
  font-size: 13px;
  color: var(--color-muted-foreground);
  padding: 6px 12px;
  background: var(--color-muted);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

/* 内容区 */
.main-content {
  flex: 1;
  padding: 24px;
  overflow-x: hidden;
  overflow-y: auto;
  background: linear-gradient(135deg, var(--color-background) 0%, #0a0f1a 100%);
  min-width: 0;
}
</style>
