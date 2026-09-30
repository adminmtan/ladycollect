<template>
  <div class="system-status" :title="tooltipText">
    <!-- 顶条：脉冲指示器 + 版本号 -->
    <div class="status-top">
      <span class="status-pulse" :class="{ 'is-pulsing': isHealthy }">
        <span class="pulse-dot"></span>
      </span>
      <span class="status-version">v{{ version }}</span>
      <span class="status-channel">{{ channel }}</span>
    </div>

    <!-- 中部：关键指标三联 -->
    <div class="status-metrics">
      <div class="metric" title="今日入库">
        <span class="metric-value">{{ metrics.todayPosts }}</span>
        <span class="metric-label">今日入库</span>
      </div>
      <div class="metric-sep"></div>
      <div class="metric" title="活跃任务">
        <span class="metric-value">{{ metrics.runningJobs }}</span>
        <span class="metric-label">活跃任务</span>
      </div>
      <div class="metric-sep"></div>
      <div class="metric" title="引擎状态">
        <span class="metric-value status-text">
          {{ engineLabel }}
        </span>
        <span class="metric-label">采集引擎</span>
      </div>
    </div>

    <!-- 底部：心跳时间线 -->
    <div class="status-foot">
      <span class="foot-label">心跳</span>
      <span class="foot-time mono">{{ heartbeat }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'

const VERSION = '2.4.0'
const CHANNEL = 'stable'

const version = ref(VERSION)
const channel = ref(CHANNEL)
const now = ref(new Date())

let timer: any = null
onMounted(() => {
  timer = setInterval(() => (now.value = new Date()), 1000)
})
onBeforeUnmount(() => clearInterval(timer))

// 引擎状态——目前恒为 CloakBrowser ready；后续可从 /api/health 拿真实指标
const isHealthy = ref(true)
const engineLabel = computed(() => (isHealthy.value ? 'CloakBrowser' : 'offline'))

// 模拟指标（实际可由 /api/stats/overview 注入）
const metrics = ref({
  todayPosts: 0,
  runningJobs: 0,
})

// 心跳时间
const heartbeat = computed(() => {
  const d = now.value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})

const tooltipText = computed(
  () => `Crawler Hub · ${channel.value} · build ${version.value} · 心跳 ${heartbeat.value}`,
)
</script>

<style scoped>
.system-status {
  position: relative;
  background:
    radial-gradient(ellipse at top left, rgba(34, 197, 94, 0.12) 0%, transparent 60%),
    linear-gradient(180deg, rgba(27, 35, 54, 0.95) 0%, rgba(15, 23, 42, 0.85) 100%);
  border: 1px solid rgba(34, 197, 94, 0.18);
  border-radius: 10px;
  padding: 11px 12px 10px;
  backdrop-filter: blur(10px);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.04) inset,
    0 8px 24px rgba(0, 0, 0, 0.35);
  overflow: hidden;
  isolation: isolate;
  cursor: default;
  transition: border-color var(--transition-normal), transform var(--transition-normal);
}

.system-status:hover {
  border-color: rgba(34, 197, 94, 0.35);
  transform: translateY(-1px);
}

/* 顶部细线强调 */
.system-status::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(34, 197, 94, 0.7) 50%,
    transparent 100%
  );
}

/* 背景网格（subtle dotted pattern） */
.system-status::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image: radial-gradient(
    rgba(34, 197, 94, 0.08) 1px,
    transparent 1px
  );
  background-size: 14px 14px;
  background-position: -7px -7px;
  z-index: -1;
  opacity: 0.6;
  pointer-events: none;
}

/* 顶部条：脉冲 + 版本 */
.status-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.status-pulse {
  position: relative;
  width: 8px;
  height: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-accent);
  box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.5);
}

.status-pulse.is-pulsing .pulse-dot {
  animation: pulse-ring 1.8s ease-out infinite;
}

@keyframes pulse-ring {
  0% {
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.55);
  }
  70% {
    box-shadow: 0 0 0 8px rgba(34, 197, 94, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0);
  }
}

.status-version {
  font-family: var(--font-heading);
  font-size: 13px;
  font-weight: 600;
  color: var(--color-foreground);
  letter-spacing: 0.3px;
}

.status-channel {
  font-family: var(--font-heading);
  font-size: 9.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--color-accent);
  background: rgba(34, 197, 94, 0.12);
  border: 1px solid rgba(34, 197, 94, 0.3);
  padding: 1px 5px;
  border-radius: 3px;
  margin-left: auto;
  line-height: 1.4;
}

/* 三联指标 */
.status-metrics {
  display: flex;
  align-items: stretch;
  gap: 0;
  padding: 7px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  margin-bottom: 8px;
}

.metric {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 4px;
  min-width: 0;
}

.metric-value {
  font-family: var(--font-heading);
  font-size: 14px;
  font-weight: 600;
  color: var(--color-foreground);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.metric-value.status-text {
  font-size: 11px;
  letter-spacing: 0;
}

.metric-label {
  font-size: 9.5px;
  font-weight: 500;
  color: var(--color-muted-foreground);
  text-transform: uppercase;
  letter-spacing: 0.6px;
}

.metric-sep {
  width: 1px;
  background: linear-gradient(
    180deg,
    transparent,
    rgba(255, 255, 255, 0.1),
    transparent
  );
  margin: 2px 4px;
}

/* 底部心跳 */
.status-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  color: var(--color-muted-foreground);
}

.foot-label {
  font-family: var(--font-heading);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  font-size: 9px;
}

.foot-time {
  font-family: var(--font-heading);
  color: var(--color-foreground);
  font-variant-numeric: tabular-nums;
  font-size: 11px;
  letter-spacing: 0.3px;
}
</style>
