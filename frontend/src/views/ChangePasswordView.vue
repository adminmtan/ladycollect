<template>
  <div class="change-password-view">
    <section class="form-pane">
      <div class="form-wrap">
        <div class="mobile-brand">
          <div class="mb-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"
                fill="currentColor"
              />
            </svg>
          </div>
          <span>采集管理</span>
        </div>

        <header class="form-head">
          <h2 class="form-title">
            {{ forced ? '请先设置一个新密码' : '修改密码' }}
          </h2>
          <p class="form-sub">
            {{
              forced
                ? '首次登录或密码过期，必须设置一个新密码才能继续使用。'
                : '为了账号安全，建议使用至少 8 位且混合大小写 + 符号的强密码。'
            }}
          </p>
        </header>

        <el-alert
          v-if="forced"
          type="warning"
          show-icon
          :closable="false"
          class="forced-banner"
        >
          <template #title>
            <span>这是一次性强制改密流程，完成前无法访问系统。</span>
          </template>
        </el-alert>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          @submit.prevent="submit"
          @keyup.enter="submit"
          class="password-form"
        >
          <el-form-item label="当前密码" prop="current_password">
            <el-input
              v-model="form.current_password"
              type="password"
              show-password
              placeholder="请输入当前使用的密码"
              autocomplete="current-password"
              size="large"
            />
          </el-form-item>

          <el-form-item label="新密码" prop="new_password">
            <el-input
              v-model="form.new_password"
              type="password"
              show-password
              placeholder="至少 8 位，建议混合大小写 + 符号"
              autocomplete="new-password"
              size="large"
            />
            <span v-if="form.new_password" class="field-hint">
              <el-icon><Lock /></el-icon>
              点击右侧眼睛图标可显示明文，请务必记住后再提交。
            </span>
          </el-form-item>

          <el-form-item label="确认新密码" prop="confirm_password">
            <el-input
              v-model="form.confirm_password"
              type="password"
              show-password
              placeholder="再次输入新密码以确认"
              autocomplete="new-password"
              size="large"
            />
          </el-form-item>

          <el-button
            type="primary"
            size="large"
            :loading="submitting"
            class="submit-btn"
            native-type="submit"
          >
            {{ forced ? '设置新密码并继续' : '更新密码' }}
            <el-icon class="submit-icon"><ArrowRight /></el-icon>
          </el-button>

          <p v-if="hint" class="hint" :class="hintType">{{ hint }}</p>

          <!-- 非强制流程：允许取消返回 -->
          <el-button
            v-if="!forced"
            link
            class="cancel-btn"
            @click="onCancel"
          >
            <el-icon><Back /></el-icon>
            返回
          </el-button>
        </el-form>
      </div>

      <footer class="form-foot">
        © {{ year }} · Crawler Panel
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { ArrowRight, Lock, Back } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const forced = ref(false) // 强制模式（首次登录 / must_change_password）
const formRef = ref<FormInstance>()
const submitting = ref(false)
const hint = ref('')
const hintType = ref<'error' | 'info'>('info')

const form = reactive({
  current_password: '',
  new_password: '',
  confirm_password: '',
})

const year = new Date().getFullYear()

const rules = reactive<FormRules>({
  current_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    {
      validator: (_r, v, cb) => {
        if (!v || v.length < 8) {
          cb(new Error('至少 8 位'))
          return
        }
        if (form.current_password && v === form.current_password) {
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
        if (v !== form.new_password) return cb(new Error('两次密码不一致'))
        cb()
      },
      trigger: 'blur',
    },
  ],
})

onMounted(async () => {
  // 路由标记：?forced=1 表示强制改密（守卫把用户踢过来时带上）
  if (route.query.forced === '1') {
    forced.value = true
  } else if (auth.user?.must_change_password) {
    forced.value = true
  }

  // 强制模式下：必须确保 user 已 hydrate（防止 stale token）
  if (forced.value && !auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      // fetch 失败 → token 无效，回登录
      router.replace('/login')
    }
  }

  // 如果系统提示强制改密，但又没有当前密码（不可能发生在正常流程，留个兜底）：
  // 让用户填即可（后端会用 token 鉴权，不需要当前密码字段）
  // —— 但我们的后端 change-password 要求 current_password，所以保留即可
})

async function submit() {
  if (submitting.value) return
  const ok = await formRef.value?.validate().catch(() => false)
  if (!ok) return
  submitting.value = true
  hint.value = ''
  try {
    await auth.changePassword(form.current_password, form.new_password)
    ElMessage.success(forced.value ? '密码设置完成，欢迎使用' : '密码已更新')
    // 改完后清空表单敏感字段
    form.current_password = ''
    form.new_password = ''
    form.confirm_password = ''
    // 跳到原想去的地方（守卫会塞 ?next=...），或者默认 / 登录完成
    const next = (route.query.next as string) || '/'
    router.replace(next)
  } catch (e: any) {
    hint.value = e?.message || '修改失败'
    hintType.value = 'error'
  } finally {
    submitting.value = false
  }
}

function onCancel() {
  router.back()
}
</script>

<style scoped>
.change-password-view {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, #0d1322 0%, var(--color-background) 100%);
  color: var(--color-foreground);
  font-family: var(--font-body);
  padding: 24px;
}

.form-pane {
  position: relative;
  width: 100%;
  max-width: 480px;
  display: flex;
  flex-direction: column;
  padding: 56px 48px;
  background: linear-gradient(180deg, #0d1322 0%, var(--color-background) 100%);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 18px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.5);
}

.mobile-brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 28px;
  font-family: var(--font-heading);
  font-size: 16px;
  color: var(--color-foreground);
}

.mb-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--color-accent), #16a34a);
  color: var(--color-on-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 14px rgba(34, 197, 94, 0.32);
}

.form-head {
  margin-bottom: 24px;
}

.form-title {
  margin: 0 0 10px;
  font-family: var(--font-heading);
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--color-foreground);
}

.form-sub {
  margin: 0;
  font-size: 14px;
  color: var(--color-muted-foreground);
  line-height: 1.6;
}

.forced-banner {
  margin-bottom: 24px;
  border-radius: 10px;
}

.password-form :deep(.el-form-item__label) {
  font-family: var(--font-heading);
  font-weight: 500;
  font-size: 12px;
  letter-spacing: 0.04em;
  color: var(--color-muted-foreground);
  text-transform: uppercase;
  padding-bottom: 6px;
}

.password-form :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.03) !important;
  border-radius: 10px;
  padding: 4px 12px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08) !important;
  transition: box-shadow 0.15s ease;
}

.password-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: inset 0 0 0 1px var(--color-accent) !important;
}

.password-form :deep(.el-input__inner) {
  color: var(--color-foreground);
}

.password-form :deep(.el-input__inner::placeholder) {
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

.submit-btn {
  width: 100%;
  height: 48px;
  margin-top: 12px;
  border-radius: 10px;
  font-family: var(--font-heading);
  font-weight: 600;
  letter-spacing: 0.04em;
  background: linear-gradient(135deg, var(--color-accent) 0%, #16a34a 100%);
  border: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  box-shadow: 0 6px 18px rgba(34, 197, 94, 0.34);
  transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
}

.submit-btn:hover {
  transform: translateY(-1px);
  filter: brightness(1.04);
  box-shadow: 0 10px 24px rgba(34, 197, 94, 0.45);
}

.submit-icon {
  transition: transform 0.15s ease;
}

.submit-btn:hover .submit-icon {
  transform: translateX(3px);
}

.hint {
  margin: 18px 0 0;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.55;
}

.hint.info {
  color: var(--color-muted-foreground);
  background: rgba(59, 130, 246, 0.07);
  border: 1px solid rgba(59, 130, 246, 0.18);
}

.hint.error {
  color: #fca5a5;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.25);
}

.cancel-btn {
  margin-top: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
  color: var(--color-muted-foreground);
  width: 100%;
}

.cancel-btn:hover {
  color: var(--color-foreground);
}

.form-foot {
  margin-top: 24px;
  text-align: center;
  font-family: var(--font-heading);
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--color-muted-foreground);
}
</style>
