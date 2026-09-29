# 采集管理应用：1mei.live 采集面板

基于 CloakBrowser（反爬指纹） + DrissionPage（点击分页） + Scrapling（自适应解析）构建的采集核心，FastAPI + SQLite 后端、Vue 3 前端，单 docker-compose 一键部署。

## 功能

- 多域名配置（站点 host/cookie/proxy/UA 切换）
- 按日期范围 + 关键字 + 分类 过滤采集
- 列表 + 详情入库（标题、日期、magnet、ed2k、封面）
- 卡片式浏览 + 多选一键复制下载链接（magnet / ed2k / 全部）

## 技术栈

- **后端**：FastAPI + SQLModel + APScheduler + Uvicorn
- **前端**：Vue 3 + Vite + Element Plus + Pinia + Vue Router
- **采集**：CloakBrowser + DrissionPage + Scrapling
- **数据库**：SQLite（`data/app.db`）
- **部署**：单 docker-compose（基于 `cloakhq/cloakbrowser` 镜像）

## 本地开发

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8080
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

## Docker 部署（NAS 推荐）

### 首次部署

```bash
# 1) 拷贝环境变量模板并编辑（填 CLOAKBROWSER_LICENSE_KEY 等）
cp .env.example .env

# 2) 拉取并启动
docker compose pull && docker compose up -d

# 3) 查看首次自动生成的 admin 密码（仅首次启动显示一次）
docker logs crawler-panel 2>&1 | grep -A2 'CrawlerPanel'
# 输出类似：
#   [CrawlerPanel] 首次启动完成，已生成管理员账号
#     用户名: admin
#     密码 : Ab1X-yJ2-Nm9p
```

> 数据持久化到 `./data/`（挂载进容器的 `/app/data`），重启/升级容器数据都不丢。
> 升级时**数据目录里的 `.jwt_secret` 不变**，所有已登录 token 保持有效。

### 升级（升级镜像）

```bash
# 1) 修改 .env 里的 IMAGE_TAG（默认 latest；想用固定版就改成 v0.1.0 这种）
# 2) 拉新镜像并滚动升级
docker compose pull && docker compose up -d

# 只看最近启动发生了什么
docker logs --tail=100 crawler-panel
```

如果想"自动升级"（NAS 守护进程拉 latest）：上 [Watchtower](https://github.com/containrrr/watchtower)：

```bash
docker run -d --name watchtower \
  --restart always \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --schedule "0 0 4 * * *" \
  crawler-panel
```

### GHCR 发布（开发者侧）

CI 自动：往 `main` 推 → 自动出 `latest` 和 `main-<sha>` 标签；
推 `v0.1.0` tag → 自动出 `0.1.0`、`0.1`、`latest`。

镜像推到 `ghcr.io/adminmtan/ladycollect`（GHCR，GitHub 自带容器仓库，跟仓走，**不需要额外配置 secret**，用仓库内置的 `GITHUB_TOKEN` + `packages: write` 权限即可）。

**手动推**（不走 CI 时）：

```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx \
  ./scripts/push.sh
```

需要 PAT（Personal Access Token），勾选 `write:packages` 权限。

## 目录结构

参见 [架构方案文档](.cursor/plans/采集管理应用架构方案_4c9a30d9.plan.md)。
