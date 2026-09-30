# Ladycollect NAS 部署包

把这个目录里的文件 **scp/rsync 到 NAS 上**（例如 `~/ladycollect/` 或 `/volume1/docker/ladycollect/`），然后：

```bash
cd ~/ladycollect                  # 或你的部署目录
cp .env.example .env              # 编辑填入密钥
docker compose pull               # 拉最新镜像
docker compose up -d              # 启动
```

目录里包含：

- `docker-compose.yml` — 主应用 + watchtower（自动跟 GHCR `:latest`）
- `.env.example` — 必填环境变量模板
- `README.md` — 详细说明

## 镜像来源

`ghcr.io/adminmtan/ladycollect:latest` — GitHub Actions 在每次 push 到 `main` 后自动 build + push。

## 自动更新策略

- `watchtower` 每 **86400 秒（24 小时）**检查一次 GHCR `:latest`
- 只更新带 `com.enable.watchtower=true` label 的容器（避免误伤其他）
- 自动清理旧镜像 (`--cleanup`)
- 拉取失败 → 旧容器继续跑，不影响服务
