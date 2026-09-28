import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { settingsApi, type AppSetting, type AppSettingTestResponse } from '@/api'

export const useSettingsStore = defineStore('settings', () => {
  const items = ref<AppSetting[]>([])
  const loading = ref(false)
  const testing = ref(false)

  /** 用于表单展示的合并视图（带 label/description/placeholder 等元数据） */
  const meta = ref<AppSetting[]>([])

  async function fetch() {
    loading.value = true
    try {
      const [list, metaData] = await Promise.all([settingsApi.list(), settingsApi.meta()])
      items.value = list
      // 把 label/description/placeholder 注入到 items
      const metaMap = new Map(metaData.map((m) => [m.key, m]))
      items.value = list.map((it) => {
        const m = metaMap.get(it.key)
        return m ? { ...it, label: m.label, description: m.description, placeholder: m.placeholder } : it
      })
      meta.value = metaData
    } finally {
      loading.value = false
    }
  }

  async function update(key: string, value: string | null) {
    const updated = await settingsApi.update(key, value)
    // 局部更新
    const idx = items.value.findIndex((x) => x.key === key)
    if (idx >= 0) {
      // 保留 meta 信息
      const old = items.value[idx]
      items.value[idx] = { ...old, ...updated }
    }
    return updated
  }

  async function test(payload: { base_url?: string; api_key?: string; model?: string; timeout?: number }): Promise<AppSettingTestResponse> {
    testing.value = true
    try {
      return await settingsApi.test(payload)
    } finally {
      testing.value = false
    }
  }

  function findByKey(key: string): AppSetting | undefined {
    return items.value.find((x) => x.key === key)
  }

  const apiKeyConfigured = computed(() => {
    const it = findByKey('openai_api_key')
    if (!it) return false
    return it.source === 'db' && !!it.value
  })

  return { items, loading, testing, meta, fetch, update, test, findByKey, apiKeyConfigured }
})
