<template>
  <div class="settings-view">
    <div class="glass-card main-card">
      <!-- 顶部说明 -->
      <div class="card-header">
        <div class="header-title">
          <el-icon><Tools /></el-icon>
          <span>系统设置</span>
          <span class="header-hint">账户安全 · AI 服务配置</span>
        </div>
      </div>

      <!-- 标签切换 -->
      <el-tabs v-model="activeTab" class="settings-tabs" type="card">
        <!-- 账户安全 -->
        <el-tab-pane label="账户安全" name="security">
          <template #label>
              <span class="tab-label">
                <el-icon><Lock /></el-icon>
                账户安全
              </span>
            </template>
          <div class="tab-content">
            <div class="section-intro">
              <h3 class="section-title">修改密码</h3>
              <p class="section-desc">
                修改当前账号 <strong>{{ auth.user?.username || 'admin' }}</strong> 的登录密码。
                至少 8 位，建议混合大小写 + 符号。
              </p>
            </div>

            <el-alert
              v-if="mustChangeHint"
              type="warning"
              show-icon
              :closable="false"
              class="forced-banner"
            >
              <template #title>
                <span>系统检测到当前账号首次登录或密码已过期，请尽快修改密码。</span>
              </template>
            </el-alert>

            <el-form
              ref="pwdFormRef"
              :model="pwdForm"
              :rules="pwdRules"
              label-position="top"
              label-width="120px"
              class="security-form"
              @submit.prevent="onChangePassword"
              @keyup.enter="onChangePassword"
            >
              <el-form-item label="当前密码" prop="current_password">
                <el-input
                  v-model="pwdForm.current_password"
                  type="password"
                  show-password
                  placeholder="请输入当前使用的密码"
                  autocomplete="current-password"
                  size="large"
                />
              </el-form-item>

              <el-form-item label="新密码" prop="new_password">
                <el-input
                  v-model="pwdForm.new_password"
                  type="password"
                  show-password
                  placeholder="至少 8 位，建议混合大小写 + 符号"
                  autocomplete="new-password"
                  size="large"
                />
                <span v-if="pwdForm.new_password" class="field-hint">
                  <el-icon><View /></el-icon>
                  点击右侧眼睛图标可显示明文，请务必记住后再提交。
                </span>
              </el-form-item>

              <el-form-item label="确认新密码" prop="confirm_password">
                <el-input
                  v-model="pwdForm.confirm_password"
                  type="password"
                  show-password
                  placeholder="再次输入新密码以确认"
                  autocomplete="new-password"
                  size="large"
                />
              </el-form-item>

              <div class="form-actions">
                <el-button
                  type="primary"
                  size="large"
                  :loading="pwdSubmitting"
                  @click="onChangePassword"
                >
                  <el-icon><Check /></el-icon>
                  更新密码
                </el-button>
              </div>
            </el-form>
          </div>
        </el-tab-pane>

        <!-- AI 配置 -->
        <el-tab-pane name="ai">
          <template #label>
              <span class="tab-label">
                <el-icon><MagicStick /></el-icon>
                AI 配置
              </span>
            </template>
          <div class="tab-content">
            <div class="section-intro">
              <h3 class="section-title">AI 配置（OpenAI 兼容）</h3>
              <p class="section-desc">
                用于「不喜欢」反馈触发的关键词自动学习。
              </p>
              <span :class="['status-pill', store.apiKeyConfigured ? 'status-active' : 'status-inactive']">
                <el-icon><Connection /></el-icon>
                {{ store.apiKeyConfigured ? 'AI 已启用' : 'AI 未启用（降级到本地规则）' }}
              </span>
            </div>

            <el-form
              v-loading="store.loading"
              :model="form"
              label-position="top"
              label-width="120px"
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
        </el-tab-pane>
      </el-tabs>
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import {
  Tools,
  Connection,
  RefreshLeft,
  Check,
  InfoFilled,
  Lock,
  View,
  MagicStick,
} from '@element-plus/icons-vue'
import { useSettingsStore } from '@/stores/settings'
import { useAuthStore } from '@/stores/auth'
import type { AppSettingTestResponse } from '@/api'

const store = useSettingsStore()
const auth = useAuthStore()

// Tab 切换
const activeTab = ref('security')

// ===== 账户安全 =====
const pwdFormRef = ref<FormInstance>()
const pwdSubmitting = ref(false)
const pwdForm = reactive({
  current_password: '',
  new_password: '',
  confirm_password: '',
})

const mustChangeHint = computed(() => !!auth.user?.must_change_password)

const pwdRules = reactive<FormRules>({
  current_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    {
      validator: (_r, v, cb) => {
        if (!v || v.length < 8) {
          cb(new Error('至少 8 位'))
          return
        }
        if (pwdForm.current_password && v === pwdForm.current_password) {
          cb(new Error('新密码不能与当前密码相同'))
          return
        }
        cb()
      },
      trigger: 'blur',
    },
  ],
  confirm_password: [
    {
      validator: (_r, v, cb) => {
        if (!v) return cb(new Error('请再次输入新密码'))
        if (v !== pwdForm.new_password) return cb(new Error('两次密码不一致'))
        cb()
      },
      trigger: 'blur',
    },
  ],
})

async function onChangePassword() {
  if (pwdSubmitting.value) return
  const ok = await pwdFormRef.value?.validate().catch(() => false)
  if (!ok) return
  pwdSubmitting.value = true
  try {
    await auth.changePassword(pwdForm.current_password, pwdForm.new_password)
    ElMessage.success('密码已更新')
    pwdForm.current_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
  } catch (e: any) {
    ElMessage.error(e.message || '更新失败')
  } finally {
    pwdSubmitting.value = false
  }
}

// ===== AI 配置（原逻辑迁移）=====
const form = reactive<Record<string, any>>({})
const showSecrets = reactive<Record<string, boolean>>({})
const testResult = ref<AppSettingTestResponse | null>(null)

const orderedItems = computed(() => store.items)

function formatTime(s: string) {
  if (!s) return '-'
  return s.replace('T', ' ').slice(0, 16)
}

async function fetchAndHydrate() {
  await store.fetch()
  for (const it of store.items) {
    form[it.key] = it.value ?? ''
    showSecrets[it.key] = false
  }
}

onMounted(async () => {
  // 必须首次进入 AI tab 才拉，避免 prompt 拖到账号页首屏
  // 但当前 activeTab 已经是 security，所以延后到切到 AI 再 fetch
})

watch(activeTab, async (val) => {
  if (val === 'ai' && store.items.length === 0) {
    await fetchAndHydrate()
  }
})

function buildSavePayload() {
  const payload: { key: string; value: string | null }[] = []
  for (const it of store.items) {
    const current = form[it.key] ?? ''
    if (it.masked) {
      const looksMasked = typeof current === 'string' && current.includes('•')
      const isEmpty = current === '' || current == null
      if (looksMasked) continue
      if (isEmpty) {
        payload.push({ key: it.key, value: null })
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
    await fetchAndHydrate()
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
    for (const it of store.items) {
      await store.update(it.key, null)
    }
    await fetchAndHydrate()
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

/* Tabs 样式覆盖 */
.settings-tabs {
  padding: 16px 24px 0;
}

.settings-tabs :deep(.el-tabs__header) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  margin: 0 0 16px;
}

.settings-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.settings-tabs :deep(.el-tabs__item) {
  font-family: var(--font-heading);
  font-weight: 500;
  font-size: 14px;
  color: var(--color-muted-foreground);
  padding: 0 18px;
  height: 40px;
  line-height: 40px;
  border: none !important;
  background: transparent !important;
  transition: color 0.15s ease;
}

.settings-tabs :deep(.el-tabs__item.is-active) {
  color: var(--color-foreground);
}

.settings-tabs :deep(.el-tabs__active-bar) {
  background: var(--color-accent);
  height: 2px;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.tab-label .el-icon {
  font-size: 16px;
}

.tab-content {
  padding: 8px 4px 16px;
}

.section-intro {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 24px;
}

.section-title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 600;
  color: var(--color-foreground);
}

.section-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-muted-foreground);
}

.section-desc strong {
  color: var(--color-foreground);
  font-family: var(--font-heading);
}

.forced-banner {
  margin-bottom: 20px;
  border-radius: 10px;
}

/* 账户安全表单 */
.security-form,
.settings-form {
  max-width: 720px;
}

.security-form :deep(.el-form-item__label),
.settings-form :deep(.el-form-item__label) {
  font-family: var(--font-heading);
  font-weight: 500;
  font-size: 12px;
  letter-spacing: 0.04em;
  color: var(--color-muted-foreground);
  text-transform: uppercase;
  padding-bottom: 6px;
}

.security-form :deep(.el-input__wrapper),
.settings-form :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.03) !important;
  border-radius: 10px;
  padding: 4px 12px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08) !important;
  transition: box-shadow 0.15s ease;
}

.security-form :deep(.el-input__wrapper.is-focus),
.settings-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: inset 0 0 0 1px var(--color-accent) !important;
}

.security-form :deep(.el-input__inner),
.settings-form :deep(.el-input__inner) {
  color: var(--color-foreground);
}

.security-form :deep(.el-input__inner::placeholder),
.settings-form :deep(.el-input__inner::placeholder) {
  color: var(--color-muted-foreground);
}

.field-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-muted-foreground);
}

.field-hint .el-icon {
  font-size: 14px;
  color: var(--color-accent);
}

/* AI 配置 */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  width: fit-content;
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

/* 操作区 */
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 18px;
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