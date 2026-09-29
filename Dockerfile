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

# 只先拷 manifest，最大化依赖层缓存
COPY pyproject.toml ./
# 调试：去掉 quiet，让 pip 把所有行都打出来；并且不去掉 stderr，便于诊断
RUN pip install --no-cache-dir --break-system-packages -e . 2>&1 | tail -200 ; \
    echo "==== pip install exit=${PIPESTATUS[0]} ====" ; \
    rm -rf /root/.cache /tmp/*.whl

# 后端源码（高频改动层）
COPY backend ./backend

# 前端产物（来自 stage 1）
COPY --from=frontend-build /build/frontend/dist ./frontend-dist
RUN mkdir -p /app/backend/app/static && \
    cp -r /app/frontend-dist/. /app/backend/app/static/ && \
    rm -rf /app/frontend-dist

# 持久化目录
RUN mkdir -p /app/data /app/data/profile

# 入口
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]

# 默认健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["curl", "-fsS", "http://localhost:8080/api/health"]

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
