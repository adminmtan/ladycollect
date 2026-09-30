<template>
  <div class="login-view">
    <!-- 左侧：品牌分屏 -->
    <section class="brand-pane">
      <div class="brand-bg" />
      <div class="brand-grain" />

      <div class="brand-content">
        <!-- 顶部 status 行 -->
        <div class="brand-meta">
          <span class="status-dot" />
          <span class="status-label">System Online</span>
          <span class="brand-version">v0.1.0</span>
        </div>

        <!-- 巨大引言（不超过 3 行） -->
        <h1 class="brand-headline">
          静默地<br />
          <span class="headline-accent">替你把内容收集到位</span>
        </h1>

        <p class="brand-sub">
          一个面向 NAS 的轻量采集面板。<br />
          站点 · 任务 · 帖子 · 智能过滤规则，统一在你的浏览器里。
        </p>

        <!-- 底部小特征（无 meta-label） -->
        <div class="brand-tags">
          <span class="tag-pill">
            <span class="tag-dot" />
            Docker 一键部署
          </span>
          <span class="tag-pill">
            <span class="tag-dot" />
            自动学习过滤规则
          </span>
          <span class="tag-pill">
            <span class="tag-dot" />
            Web 访问零依赖
          </span>
        </div>
      </div>
    </section>

    <!-- 右侧：表单 -->
    <section class="form-pane">
      <div class="form-wrap">
        <!-- 顶部 brand logo（小屏才显示，与左侧呼应）-->
        <div class="mobile-brand">
          <div class="mb-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.48 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"
                fill="currentColor"
              />
            </svg>
          </div>
          <span>采集管理</span>
        </div>

        <!-- 切换 setup / login -->
        <header class="form-head">
          <h2 class="form-title">
            {{ mode === 'setup' ? '初始化系统' : '欢迎回来' }}
          </h2>
          <p class="form-sub">
            {{
              mode === 'setup'
                ? '为这台 NAS 第一次设置管理员密码。设置后请妥善保存。'
                : '请输入你的账号密码以继续。'
            }}
          </p>
        </header>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          @submit.prevent="submit"
          @keyup.enter="submit"
          class="login-form"
        >
          <el-form-item v-if="mode === 'setup'" label="管理员账号" prop="username">
            <el-input
              v-model="form.username"
              placeholder="例如 admin"
              autocomplete="username"
              size="large"
              class="login-input"
            />
          </el-form-item>

          <el-form-item label="账号" v-if="mode === 'login'" prop="username">
            <el-input
              v-model="form.username"
              placeholder="请输入用户名"
              autocomplete="username"
              size="large"
              class="login-input"
            />
          </el-form-item>

          <el-form-item :label="mode === 'setup' ? '设置密码' : '密码'" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              :placeholder="mode === 'setup' ? '至少 8 位，建议混合大小写+符号' : '请输入密码'"
              :autocomplete="mode === 'setup' ? 'new-password' : 'current-password'"
              size="large"
              class="login-input"
            />
            <span v-if="mode === 'setup'" class="field-hint">
              <el-icon><View /></el-icon>
              点击右侧眼睛图标可显示明文，请务必记住后再提交。
            </span>
          </el-form-item>

          <el-button
            type="primary"
            size="large"
            :loading="submitting"
            class="submit-btn"
            native-type="submit"
          >
            {{
              mode === 'setup'
                ? '完成初始化'
                : '登录'
            }}
            <el-icon class="submit-icon"><ArrowRight /></el-icon>
          </el-button>

          <p v-if="hint" class="hint" :class="hintType">{{ hint }}</p>

          <!-- 底部小提示：Docker 首次密码从哪看 + 一键填默认账号 -->
          <div v-if="mode === 'login'" class="docker-hint">
            <span class="dot" />
            <span>
              Docker 首次启动？默认账号 <strong>admin</strong>，密码在该容器
              <code>docker logs &lt;container&gt;</code> 输出中可见一次。
              <a class="quick-fill" @click.prevent="fillDefault">一键填默认账号</a>
            </span>
          </div>
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
import { ArrowRight, View } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const mode = ref<'login' | 'setup'>('login')
const formRef = ref<FormInstance>()
const submitting = ref(false)
const hint = ref('')
const hintType = ref<'error' | 'info'>('info')

const form = reactive({
  username: '',
  password: '',
})

const year = new Date().getFullYear()

const rules = reactive<FormRules>({
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    {
      validator: (_r, v, cb) => {
        if (mode.value === 'setup' && (!v || v.length < 8)) {
          cb(new Error('至少 8 位'))
          return
        }
        cb()
      },
      trigger: 'blur',
    },
  ],
})

onMounted(async () => {
  try {
    const init = await auth.checkInitialized()
    if (!init) {
      mode.value = 'setup'
      hint.value = '首次启动，请设置管理员密码。设置后无法跳过。'
      hintType.value = 'info'
    }
  } catch (e: any) {
    // 后端 unreachable：仍进 login，至少给用户一个机会
    hint.value = '无法连接后端，先尝试登录；若持续异常请检查服务。'
    hintType.value = 'error'
  }
})

async function submit() {
  if (submitting.value) return
  const ok = await formRef.value?.validate().catch(() => false)
  if (!ok) return
  submitting.value = true
  hint.value = ''
  try {
    if (mode.value === 'setup') {
      await auth.setup(form.username.trim(), form.password)
      // setup 成功后自动登录一次
      const r = await auth.login(form.username.trim(), form.password)
      ElMessage.success(`初始化完成，欢迎 ${r.user.username}`)
      router.replace((route.query.next as string) || '/')
      return
    }
    const r = await auth.login(form.username.trim(), form.password)
    ElMessage.success(`欢迎 ${r.user.username}`)
    router.replace((route.query.next as string) || '/')
  } catch (e: any) {
    hint.value = e?.message || '登录失败'
    hintType.value = 'error'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.login-view {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 100vh;
  background: var(--color-background);
  color: var(--color-foreground);
  font-family: var(--font-body);
}

/* =========== 左侧：品牌 =========== */
.brand-pane {
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: stretch;
  padding: 80px 72px;
  border-right: 1px solid rgba(255, 255, 255, 0.04);
}

.brand-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 18% 22%, rgba(34, 197, 94, 0.22) 0%, transparent 55%),
    radial-gradient(circle at 82% 78%, rgba(59, 130, 246, 0.14) 0%, transparent 60%),
    linear-gradient(180deg, var(--color-card) 0%, var(--color-background) 100%);
  animation: drift 18s ease-in-out infinite alternate;
}

.brand-grain {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.5;
  background-image:
    radial-gradient(rgba(255, 255, 255, 0.045) 1px, transparent 1px);
  background-size: 3px 3px;
  mix-blend-mode: overlay;
}

@keyframes drift {
  0%   { transform: translate3d(0, 0, 0) scale(1); }
  100% { transform: translate3d(-2%, 1.5%, 0) scale(1.04); }
}

.brand-content {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 560px;
  margin: auto 0;
  display: flex;
  flex-direction: column;
  gap: 48px;
}

.brand-meta {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  font-family: var(--font-heading);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--color-muted-foreground);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-accent);
  box-shadow: 0 0 12px rgba(34, 197, 94, 0.65);
  animation: pulse 2.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50%      { transform: scale(1.25); }
}

.brand-version {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
}

.brand-headline {
  margin: 0;
  font-family: var(--font-heading);
  font-weight: 600;
  font-size: clamp(40px, 4.6vw, 76px);
  line-height: 1.06;
  letter-spacing: -0.02em;
  color: var(--color-foreground);
}

.headline-accent {
  background: linear-gradient(120deg, #22C55E 0%, #4ade80 40%, #86efac 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.brand-sub {
  margin: 0;
  font-size: 17px;
  line-height: 1.7;
  color: var(--color-muted-foreground);
  max-width: 460px;
}

.brand-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.tag-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  font-size: 13px;
  color: var(--color-foreground);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  backdrop-filter: blur(10px);
}

.tag-dot {
  width: 6px;
  height: 6px;
  background: var(--color-accent);
  border-radius: 50%;
}

/* =========== 右侧：表单 =========== */
.form-pane {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 80px 56px;
  background: linear-gradient(180deg, #0d1322 0%, var(--color-background) 100%);
}

.form-wrap {
  width: 100%;
  max-width: 420px;
  margin: auto;
}

.mobile-brand {
  display: none;
  align-items: center;
  gap: 12px;
  margin-bottom: 32px;
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
  margin-bottom: 36px;
}

.form-title {
  margin: 0 0 10px;
  font-family: var(--font-heading);
  font-size: 32px;
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

.login-form :deep(.el-form-item__label) {
  font-family: var(--font-heading);
  font-weight: 500;
  font-size: 12px;
  letter-spacing: 0.04em;
  color: var(--color-muted-foreground);
  text-transform: uppercase;
  padding-bottom: 6px;
}

.login-form :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.03) !important;
  border-radius: 10px;
  padding: 4px 12px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08) !important;
  transition: box-shadow 0.15s ease;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: inset 0 0 0 1px var(--color-accent) !important;
}

.login-form :deep(.el-input__inner),
.login-form :deep(.el-input__inner::placeholder) {
  color: var(--color-foreground);
}

.login-form :deep(.el-input__inner::placeholder) {
  color: rgba(148, 163, 184, 0.42);
  font-style: italic;
  font-weight: 400;
  letter-spacing: 0.2px;
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
  margin-top: 8px;
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

.submit-btn:active {
  transform: translateY(0);
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

.docker-hint {
  display: flex;
  gap: 10px;
  margin-top: 26px;
  padding: 14px 16px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--color-muted-foreground);
}

.docker-hint strong {
  color: var(--color-foreground);
  font-family: var(--font-heading);
}

.docker-hint code {
  padding: 1px 6px;
  border-radius: 4px;
  font-family: var(--font-heading);
  font-size: 12px;
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-foreground);
}

.docker-hint .dot {
  width: 6px;
  height: 6px;
  margin-top: 8px;
  border-radius: 50%;
  background: var(--color-accent);
  flex-shrink: 0;
}

.form-foot {
  margin-top: 24px;
  text-align: center;
  font-family: var(--font-heading);
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--color-muted-foreground);
}

/* =========== 响应式 =========== */
@media (max-width: 980px) {
  .login-view {
    grid-template-columns: 1fr;
  }
  .brand-pane {
    display: none;
  }
  .form-pane {
    padding: 56px 24px 32px;
  }
  .mobile-brand {
    display: inline-flex;
  }
}
</style>
