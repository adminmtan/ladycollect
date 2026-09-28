<template>
  <el-card>
    <template #header>
      <div style="display: flex; align-items: center; gap: 12px">
        <span>任务运行记录</span>
        <el-tag v-if="taskId" size="small" type="info">task_id={{ taskId }}</el-tag>
        <span class="text-muted" v-if="jobs.length">共 {{ jobs.length }} 条</span>
        <div style="flex: 1"></div>
        <el-button @click="refresh" size="small" :loading="loading">刷新</el-button>
      </div>
    </template>
    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    />
    <el-table :data="jobs" empty-text="暂无运行记录">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="progress_pages" label="页" width="80" />
      <el-table-column prop="progress_posts" label="发现" width="80" />
      <el-table-column prop="posts_saved" label="入库" width="80" />
      <el-table-column prop="started_at" label="开始" width="170" />
      <el-table-column prop="finished_at" label="结束" width="170" />
      <el-table-column prop="error" label="错误" show-overflow-tooltip />
    </el-table>

    <el-card shadow="never" style="margin-top: 16px">
      <template #header>
        最近日志（合并 {{ jobs.length }} 次执行，按时间倒序，最多 100 行）
      </template>
      <div v-if="!jobs.length" class="text-muted">暂无</div>
      <div v-for="(line, i) in recentLog" :key="i" class="text-muted" style="padding: 2px 0">
        <span class="text-muted">[{{ line.ts }}] [job#{{ line.jobId }}]</span> {{ line.msg }}
      </div>
    </el-card>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute } from 'vue-router'
import { tasksApi, type Job } from '@/api'

const route = useRoute()
const taskId = computed(() => {
  const raw = route.params.id
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : 0
})
const jobs = ref<Job[]>([])
const loading = ref(false)
const loadError = ref('')
let timer: any = null

const recentLog = computed(() => {
  if (!jobs.value.length) return []
  // ★ 合并当前 task 所有 jobs 的日志，按时间倒序（最新在上）
  // 之前是只看「最新一个 job」日志，会漏掉之前跑的 job 信息
  const merged: { ts: string; msg: string; jobId: number }[] = []
  for (const j of jobs.value) {
    const log = Array.isArray(j.log) ? j.log : []
    for (const line of log) {
      merged.push({
        ts: line?.ts || '',
        msg: line?.msg || '',
        jobId: j.id,
      })
    }
  }
  // 时间倒序；同 ts 保持稳定
  merged.sort((a, b) => (a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0))
  return merged.slice(0, 100) // 限制显示 100 行
})

function statusType(s: string) {
  if (s === 'done') return 'success'
  if (s === 'running') return 'warning'
  if (s === 'failed') return 'danger'
  return 'info'
}

async function refresh() {
  if (!taskId.value) {
    loadError.value = `URL 缺少有效 task_id（参数=${String(route.params.id)}）`
    jobs.value = []
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    const rows = await tasksApi.listJobs(taskId.value)
    jobs.value = Array.isArray(rows) ? rows : []
    if (!jobs.value.length) {
      loadError.value = `任务 #${taskId.value} 暂无运行记录。可能原因：1) 任务太新还没跑；2) 历史 jobs 已被清理；3) task_id 错误。`
    }
  } catch (e: any) {
    jobs.value = []
    loadError.value = `加载运行记录失败：${e?.response?.data?.detail || e?.message || e}`
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 3000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>
