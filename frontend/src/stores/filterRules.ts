import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  filterRulesApi,
  type FilterRule,
  type FilterRuleCreate,
  type FilterRuleSummary,
  type FilterRuleUpdate,
} from '@/api'

export const useFilterRulesStore = defineStore('filterRules', () => {
  const rules = ref<FilterRuleSummary[]>([])
  const loading = ref(false)
  const currentRule = ref<FilterRule | null>(null)

  async function fetch(params?: { site_id?: number; scope?: string; rule_type?: string; enabled?: boolean }) {
    loading.value = true
    try {
      rules.value = await filterRulesApi.list(params)
    } finally {
      loading.value = false
    }
  }

  async function fetchOne(id: number) {
    currentRule.value = await filterRulesApi.get(id)
    return currentRule.value
  }

  async function create(payload: FilterRuleCreate) {
    const r = await filterRulesApi.create(payload)
    await fetch()
    return r
  }

  async function update(id: number, payload: FilterRuleUpdate) {
    const r = await filterRulesApi.update(id, payload)
    await fetch()
    if (currentRule.value?.id === id) currentRule.value = r
    return r
  }

  async function remove(id: number) {
    await filterRulesApi.remove(id)
    if (currentRule.value?.id === id) currentRule.value = null
    await fetch()
  }

  async function addKeywords(ruleId: number, keywords: string[]) {
    const added = await filterRulesApi.addKeywords(ruleId, keywords)
    if (currentRule.value?.id === ruleId) {
      currentRule.value.keywords = [...added, ...currentRule.value.keywords]
      currentRule.value.keyword_count = currentRule.value.keywords.length
    }
    await fetch()
    return added
  }

  async function deleteKeyword(ruleId: number, keywordId: number) {
    await filterRulesApi.deleteKeyword(ruleId, keywordId)
    if (currentRule.value?.id === ruleId) {
      currentRule.value.keywords = currentRule.value.keywords.filter((k) => k.id !== keywordId)
      currentRule.value.keyword_count = currentRule.value.keywords.length
    }
    await fetch()
  }

  return {
    rules,
    loading,
    currentRule,
    fetch,
    fetchOne,
    create,
    update,
    remove,
    addKeywords,
    deleteKeyword,
  }
})
