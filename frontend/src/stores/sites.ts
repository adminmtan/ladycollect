import { defineStore } from 'pinia'
import { ref } from 'vue'
import { sitesApi, type Site, type SiteCreate } from '@/api'

export const useSiteStore = defineStore('sites', () => {
  const sites = ref<Site[]>([])
  const loading = ref(false)

  async function fetch() {
    loading.value = true
    try {
      sites.value = await sitesApi.list()
    } finally {
      loading.value = false
    }
  }

  async function create(payload: SiteCreate) {
    const s = await sitesApi.create(payload)
    await fetch()
    return s
  }

  async function update(id: number, payload: Partial<SiteCreate>) {
    const s = await sitesApi.update(id, payload)
    await fetch()
    return s
  }

  async function remove(id: number) {
    await sitesApi.remove(id)
    await fetch()
  }

  async function probe(id: number) {
    return sitesApi.probe(id)
  }

  return { sites, loading, fetch, create, update, remove, probe }
})
