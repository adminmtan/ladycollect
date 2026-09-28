import { defineStore } from 'pinia'
import { ref } from 'vue'
import { tasksApi, type Task, type TaskCreate, type TaskUpdate, type Job } from '@/api'

export const useTaskStore = defineStore('tasks', () => {
  const tasks = ref<Task[]>([])
  const loading = ref(false)
  const currentJob = ref<Job | null>(null)

  async function fetch(site_id?: number) {
    loading.value = true
    try {
      tasks.value = await tasksApi.list(site_id)
    } finally {
      loading.value = false
    }
  }

  async function create(payload: TaskCreate) {
    const t = await tasksApi.create(payload)
    await fetch(payload.site_ids?.[0])
    return t
  }

  async function update(id: number, payload: TaskUpdate, site_id?: number) {
    const t = await tasksApi.update(id, payload)
    await fetch(site_id)
    return t
  }

  async function remove(id: number, site_id?: number) {
    await tasksApi.remove(id)
    await fetch(site_id)
  }

  async function run(id: number, site_id?: number) {
    await tasksApi.run(id)
    await fetch(site_id)
  }

  async function stop(id: number, site_id?: number) {
    const r = await tasksApi.stop(id)
    await fetch(site_id)
    return r
  }

  async function refreshJob(jobId: number) {
    currentJob.value = await tasksApi.getJob(jobId)
  }

  return { tasks, loading, currentJob, fetch, create, update, remove, run, stop, refreshJob }
})
