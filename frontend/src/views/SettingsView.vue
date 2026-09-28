<template>
  <div class="settings-view">
    <div class="glass-card main-card">
      <!-- 顶部说明 -->
      <div class="card-header">
        <div class="header-title">
          <el-icon><Tools /></el-icon>
          <span>AI 配置（OpenAI 兼容）</span>
          <span class="header-hint">用于「不喜欢」反馈触发的关键词自动学习</span>
        </div>
        <div class="header-status">
          <span :class="['status-pill', store.apiKeyConfigured ? 'status-active' : 'status-inactive']">
            <el-icon><Connection /></el-icon>
            {{ store.apiKeyConfigured ? 'AI 已启用' : 'AI 未启用（降级到本地规则）' }}
          </span>
        </div>
      </div>

      <!-- 表单 -->
      <el-form
        v-loading="store.loading"
        :model="form"
        label-width="140px"
        label-position="right"
        class="settings-form"
      >
        <div
          v-for="item in orderedItems"
          :key="item.key"
          class="field-row"
        >
          <el-form-item :label="item.label || item.key">
            <template v-if="item.masked">
              <!-- api_key 专用：密码框 + 显示/隐藏 -->
              <el-input
                v-model="form[item.key]"
                :type="showSecrets[item.key] ? 'text' : 'password'"
                :placeholder="item.placeholder || ''"
                show-password
                clearable
              >
                <template #suffix>
                  <el-button
                    link
                    type="primary"
                    size="small"
                    @click="showSecrets[item.key] = !showSecrets[item.key]"
                  >
                    {{ showSecrets[item.key] ? '隐藏' : '显示' }}
                  </el-button>
                </template>
              </el-input>
            </template>
            <template v-else-if="item.key === 'openai_timeout'">
              <el-input-number
                v-model="form[item.key]"
                :min="5"
                :max="120"
                :step="5"
                style="width: 200px"
              />
            </template>
            <template v-else>
              <el-input
                v-model="form[item.key]"
                :placeholder="item.placeholder || ''"
                clearable
              />
            </template>

            <div class="field-meta">
              <span v-if="item.description" class="field-desc">{{ item.description }}</span>
              <span :class="['source-tag', `source-${item.source}`]">
                {{ item.source === 'db' ? '已自定义' : '使用默认值' }}
              </span>
              <span v-if="item.updated_at" class="field-time">
                更新于 {{ formatTime(item.updated_at) }}
              </span>
            </div>
          </el-form-item>
        </div>

        <!-- 操作 -->
        <div class="form-actions">
          <el-button @click="onReset" :disabled="store.loading">
            <el-icon><RefreshLeft /></el-icon>
            恢复默认
          </el-button>
          <el-button @click="onTest" :loading="store.testing">
            <el-icon><Connection /></el-icon>
            测试连接
          </el-button>
          <el-button type="primary" @click="onSave" :disabled="store.loading">
            <el-icon><Check /></el-icon>
            保存
          </el-button>
        </div>

        <!-- 测试结果 -->
        <el-alert
          v-if="testResult"
          :type="testResult.ok ? 'success' : 'error'"
          :closable="true"
          show-icon
          class="test-result"
          @close="testResult = null"
        >
          <template #title>
            <span>{{ testResult.message }}</span>
            <span v-if="testResult.latency_ms != null" class="latency">
              {{ testResult.latency_ms }} ms
            </span>
          </template>
          <div v-if="testResult.model_reply" class="reply-preview">
            <span class="reply-label">模型返回：</span>
            <code>{{ testResult.model_reply }}</code>
          </div>
        </el-alert>
      </el-form>
    </div>

    <!-- 帮助卡 -->
    <div class="glass-card help-card">
      <div class="card-header">
        <div class="header-title">
          <el-icon><InfoFilled /></el-icon>
          <span>使用说明</span>
        </div>
      </div>
      <ul class="help-list">
        <li>本服务使用 OpenAI 兼容协议，支持 OpenAI、DeepSeek、Azure OpenAI、Ollama、自建网关等任何提供 <code>/chat/completions</code> 的服务。</li>
        <li>API Key 存储在本地数据库 <code>app_settings</code> 表（已加密持久化），不会上传到任何第三方。</li>
        <li>未配置 API Key 时，关键词提取自动降级到本地规则（中文 n-gram + 停用词），效果较弱但可用。</li>
        <li>建议用 <code>gpt-4o-mini</code> / <code>deepseek-chat</code> / <code>qwen-turbo</code> 这类廉价模型，单次提取消耗 token 极少。</li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Tools,
  Connection,
  RefreshLeft,
  Check,
  InfoFilled,
} from '@element-plus/icons-vue'
import { useSettingsStore } from '@/stores/settings'
import type { AppSettingTestResponse } from '@/api'

const store = useSettingsStore()

// 表单状态（按 key 索引；api_key 保留为输入值，可能为已脱敏的旧值，使用时需清空）
const form = reactive<Record<string, any>>({})
// 控制哪些敏感字段以明文显示
const showSecrets = reactive<Record<string, boolean>>({})
const testResult = ref<AppSettingTestResponse | null>(null)

const orderedItems = computed(() => store.items)

onMounted(async () => {
  await store.fetch()
  // 用 store 的当前值回填（带掩码的字段也填，UI 在切换显示时由用户改写）
  for (const it of store.items) {
    form[it.key] = it.value ?? ''
    showSecrets[it.key] = false
  }
})

function formatTime(s: string) {
  if (!s) return '-'
  return s.replace('T', ' ').slice(0, 16)
}

/** 真实可提交的 payload：跳过未修改的掩码字段（保持 db 原值） */
function buildSavePayload() {
  const payload: { key: string; value: string | null }[] = []
  for (const it of store.items) {
    const current = form[it.key] ?? ''
    if (it.masked) {
      // 如果还是掩码值（带 •）或原值没变，不提交（保留 db 旧值）
      const looksMasked = typeof current === 'string' && current.includes('•')
      const isEmpty = current === '' || current == null
      if (looksMasked) continue
      if (isEmpty) {
        payload.push({ key: it.key, value: null }) // 清空
      } else {
        payload.push({ key: it.key, value: current })
      }
    } else {
      payload.push({ key: it.key, value: current === '' ? null : String(current) })
    }
  }
  return payload
}

async function onSave() {
  const updates = buildSavePayload()
  if (updates.length === 0) {
    ElMessage.info('没有需要保存的修改')
    return
  }
  try {
    for (const u of updates) {
      await store.update(u.key, u.value)
    }
    ElMessage.success('已保存')
    testResult.value = null
    // 重新拉一次（让 store 里同步 source/updated_at）
    await store.fetch()
    // 回填表单（api_key 会变回掩码形式）
    for (const it of store.items) {
      form[it.key] = it.value ?? ''
    }
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  }
}

async function onTest() {
  testResult.value = null
  const payload = {
    base_url: form.openai_base_url || undefined,
    api_key: (form.openai_api_key && !String(form.openai_api_key).includes('•'))
      ? form.openai_api_key
      : undefined,
    model: form.openai_model || undefined,
    timeout: form.openai_timeout ? Number(form.openai_timeout) : undefined,
  }
  try {
    const r = await store.test(payload)
    testResult.value = r
    if (r.ok) {
      ElMessage.success('连接成功')
    } else {
      ElMessage.error(r.message)
    }
  } catch (e: any) {
    testResult.value = { ok: false, message: e.message || '测试失败' }
    ElMessage.error(e.message || '测试失败')
  }
}

async function onReset() {
  try {
    // 全部置空（=回退默认）
    for (const it of store.items) {
      await store.update(it.key, null)
    }
    await store.fetch()
    for (const it of store.items) {
      form[it.key] = it.value ?? ''
    }
    testResult.value = null
    ElMessage.success('已恢复默认配置')
  } catch (e: any) {
    ElMessage.error(e.message || '恢复失败')
  }
}
</script>

<style scoped>
.settings-view {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.main-card,
.help-card {
  padding: 0;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-foreground);
}

.header-title .el-icon {
  font-size: 20px;
  color: var(--color-accent);
}

.header-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--color-muted-foreground);
  margin-left: 8px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.status-pill .el-icon {
  font-size: 14px;
}

.status-active {
  background: rgba(34, 197, 94, 0.15);
  color: var(--color-accent);
}

.status-inactive {
  background: var(--color-muted);
  color: var(--color-muted-foreground);
}

.settings-form {
  padding: 28px 32px 32px;
}

.field-row {
  margin-bottom: 8px;
}

.field-meta {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.field-desc {
  font-size: 12px;
  color: var(--color-muted-foreground);
  line-height: 1.5;
  flex: 1;
  min-width: 200px;
}

.source-tag {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 20px;
  font-weight: 600;
  white-space: nowrap;
}

.source-db {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.source-default {
  background: var(--color-muted);
  color: var(--color-muted-foreground);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.field-time {
  font-size: 11px;
  color: var(--color-muted-foreground);
  font-family: var(--font-heading);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 12px;
  padding-top: 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.test-result {
  margin-top: 20px;
}

.latency {
  margin-left: 12px;
  font-family: var(--font-heading);
  font-size: 12px;
  color: var(--color-muted-foreground);
}

.reply-preview {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--color-muted);
  border-radius: var(--radius-md);
  font-family: var(--font-heading);
  font-size: 12px;
}

.reply-label {
  color: var(--color-muted-foreground);
  margin-right: 6px;
}

.reply-preview code {
  color: var(--color-accent);
}

/* 帮助卡 */
.help-card {
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.help-list {
  list-style: none;
  margin: 0;
  padding: 20px 32px 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.help-list li {
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-muted-foreground);
  padding-left: 16px;
  position: relative;
}

.help-list li::before {
  content: '•';
  position: absolute;
  left: 0;
  color: var(--color-accent);
}

.help-list code {
  background: var(--color-muted);
  color: var(--color-foreground);
  padding: 1px 6px;
  border-radius: 4px;
  font-family: var(--font-heading);
  font-size: 12px;
}
</style>
