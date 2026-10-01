# syntax=docker/dockerfile:1.7
# ============================================================
# Crawler Panel - 多阶段构建
# Stage 1 (node): 构建前端产物
# Stage 2 (python): 安装后端依赖并打包最终镜像
# Stage 3 (runtime): 最小运行时镜像（基于 cloakhq/cloakbrowser）
# ============================================================

# ---------- 1) 前端构建 ----------
FROM node:20-bookworm-slim AS frontend-build
WORKDIR /build
# 仅先拷 package*.json，最大化依赖层缓存
COPY frontend/package.json frontend/package-lock.json* ./frontend/
WORKDIR /build/frontend
RUN npm install --no-audit --no-fund
# 再拷源码（高频改动层）
COPY frontend/ ./
RUN npm run build

# ---------- 2) Python 依赖收集（仅提取 wheel 列表） ----------
# 不在这里装，保持镜像小。在 runtime stage 内统一安装。

# ---------- 3) 运行时镜像 ----------
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8080 \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 系统依赖：Python + Chromium 运行库（cloakbrowser/playwright 需要）+ 编译工具链
# 复制自 cloakhq/cloakbrowser Dockerfile 外加构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        curl ca-certificates \
        # Chromium 运行依赖
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
        libdbus-1-3 libdrm2 libxkbcommon0 libatspi2.0-0 libxcomposite1 \
        libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
        libcairo2 libasound2 libx11-xcb1 libfontconfig1 libx11-6 \
        libxcb1 libxext6 libxshmfence1 \
        libglib2.0-0 libgtk-3-0 libpangocairo-1.0-0 libcairo-gobject2 \
        libgdk-pixbuf-2.0-0 libxss1 libxtst6 fonts-liberation \
        fonts-noto-color-emoji fonts-unifont fonts-freefont-ttf \
        fonts-ipafont-gothic fonts-wqy-zenhei fonts-tlwg-loma-otf \
        fonts-urw-base35 \
        xvfb xdotool openbox \
        # C 扩展编译（兜底，万一 wheel 不齐）
        gcc libffi-dev libssl-dev libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 顺序很关键：先把 backend/ 拷进来。
# pyproject.toml 里 [tool.setuptools.packages.find] where=["backend"]，如果
# pip install -e . 时 backend/ 不存在，setuptools egg_info 会报
#   error: error in 'egg_base' option: 'backend' does not exist
# 把 backend/ 一起 COPY 不会显著影响缓存命中：pyproject.toml 仍然在最顶层
# 决定 pip install 层的 cache key，backend 内容变更只影响这一层。
COPY pyproject.toml ./
COPY backend ./backend
# 注入版本元数据（运行时通过 envvars 读，/api/health 返回）
# APP_VERSION / GIT_SHA / BUILT_AT 由 GH Actions 通过 --build-arg 传入
ARG APP_VERSION=dev
ARG GIT_SHA=unknown
ARG BUILT_AT=unknown
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILT_AT=${BUILT_AT}
# cloakbrowser 直接依赖 cryptography + playwright + httpx（pip show cloakbrowser），
# Dockerfile 用 --no-deps 装 cloakbrowser（resolver 冲突，见 46ab4db），所以这些都
# 必须显式装。--no-deps 跳过 transitive deps 会让 Docker 镜像缺 cryptography，
# 运行时 sehuatang 浏览器任务启动时 No module named 'cryptography'（job#7 失败案例）。
# 本地 venv 之前能跑是因为 playwright 拖带了 cryptography；Docker 全新构建没人替它装。
# httpx pyproject 已声明，这里不重复。
RUN set -o pipefail ; \
    pip install --no-cache-dir --break-system-packages -e . \
        cryptography \
        playwright \
        > /tmp/pip.out 2> /tmp/pip.err ; \
    rc=$? ; \
    echo "==== main deps pip install exit=$rc ====" ; \
    tail -n 50 /tmp/pip.err ; \
    rm -rf /root/.cache /tmp/*.whl /tmp/pip.out /tmp/pip.err ; \
    exit $rc

# cloakbrowser 装在最后，--no-deps 复用上面已装的 cryptography/playwright，避免 resolver 冲突
RUN set -o pipefail ; \
    pip install --no-cache-dir --break-system-packages --no-deps cloakbrowser > /tmp/cloak.out 2> /tmp/cloak.err ; \
    rc=$? ; \
    echo "==== cloakbrowser pip install exit=$rc ====" ; \
    tail -n 50 /tmp/cloak.err ; \
    rm -rf /root/.cache /tmp/*.whl /tmp/cloak.out /tmp/cloak.err ; \
    exit $rc

# 验证关键依赖都已安装（构建期断言，不通过会让镜像构建失败）
# 关键：cryptography 是 playwright 启动 Browser 时的 lazy import（playwright/_impl/_api_types.py
# 通过 cryptography.x509 验 TLS 证书），所以"import playwright"不足以暴露 cryptography 缺失。
# 必须显式 import cryptography 才能在 build 期抓到 No module named 'cryptography' 这种
# 只在运行时才会触发的 import 链断裂。
# 实现说明：直接用 python3 -c "..." 内嵌多行字符串会被 BuildKit 解析报错（把字面量内换行
# 当成新指令），用 <<'PYEOF' heredoc 又依赖 frontend 1.4+；最稳的写法是用 printf 把多行
# Python 写到 /tmp/verify_deps.py，再让 python3 执行该文件。
RUN printf '%s\n' \
    'import cryptography, httpx, playwright, cloakbrowser' \
    'from importlib.metadata import version' \
    'print("deps OK: cryptography", version("cryptography"),' \
    '      "| httpx", version("httpx"),' \
    '      "| playwright", version("playwright"),' \
    '      "| cloakbrowser", version("cloakbrowser"))' \
    > /tmp/verify_deps.py && \
    python3 /tmp/verify_deps.py && \
    rm /tmp/verify_deps.py

# 前端产物（来自 stage 1）拷到 backend 的 static 目录，让 FastAPI 直接挂载。
COPY --from=frontend-build /build/frontend/dist ./frontend-dist
RUN mkdir -p /app/backend/app/static && \
    cp -r /app/frontend-dist/. /app/backend/app/static/ && \
    rm -rf /app/frontend-dist

# 持久化目录
RUN mkdir -p /app/data /app/data/profile /app/data/logs /app/data/logs/archive

# 入口
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]

# 默认健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["curl", "-fsS", "http://localhost:8080/api/health"]

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
