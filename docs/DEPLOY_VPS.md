# Football 网站 V0.2 / Ubuntu 24.04 VPS 部署手册

本项目 VPS 目标：`45.12.52.34`，网站域名 `https://fb.linmeng.ai`。文件服务器 `https://files.shenqianqian.com/football/` 负责分发已经过 SHA256 校验的**公开源码发布包**。仓库所有者已明确允许发布包被公开下载。

> 当前状态：网站代码已合并，但**尚未在 VPS 上安装或验证**。本手册中的 VPS 命令需要具备该服务器登录权限的操作者执行。

## 1. 网络与基础环境

1. 在 `linmeng.ai` 的 DNS 中创建 `A fb → 45.12.52.34`；如无 IPv6，不创建 AAAA。使用 `dig +short fb.linmeng.ai` 核验。
2. 防火墙允许 `80/tcp`、`443/tcp`，并确保你实际使用的 **SSH 端口已经放行**。如果使用 UFW，请先核验 SSH 规则，再执行任何启用防火墙的操作，避免锁在服务器外。
3. `5432`（PostgreSQL）和 `8000`（FastAPI）**不向公网发布**；Compose 通过内部网络连接数据库/API。
4. 按 [Docker 官方 Ubuntu 安装说明](https://docs.docker.com/engine/install/ubuntu/) 安装 Docker Engine 和 Compose plugin，随后执行 `docker --version`、`docker compose version` 验收。
5. 确保 VPS 上没有其他服务占用 `80/443`。Caddy 通过公开 DNS 自动申请/续期证书；公网路由及证书签发取决于服务器防火墙和 DNS。

## 2. GitHub 自动构建并发布到 test

1. 代码 PR 审查并合并到 `main` 后，`Build and optionally publish football release` 会自动测试、打包并发布到 `test`。
2. 自动包使用 `v0.2.<该工作流运行序号>` 的不可变版本号，每次运行唯一；发布脚本先做本地 SHA256 和 HTTPS 公网下载复核，成功后才更新 `channels/test.json`。
3. 访问 `https://files.shenqianqian.com/football/channels/test.json`，读取当前版本及 SHA256，再下载指向的包。**不要假设最新发布包就是固定的 v0.2.0**。
4. `workflow_dispatch` 手动发布仍保留，用于指定版本、`build-only`、`promote-existing` 以及配合匹配 Git tag 的 `stable` 发布。

发布命令有版本不可覆盖约束：同一个版本发布后不允许二次 `publish-new`；只切渠道使用 `promote-existing`。

## 3. 在 VPS 拉取并校验版本

以下示例以 `v0.2.0` 为例。请在 VPS 登录后运行（假定使用具备管理 Docker 权限的账号）：

```bash
sudo mkdir -p /opt/football/releases /opt/football/downloads/v0.2.0
cd /opt/football/downloads/v0.2.0

curl -fL --retry 3 -o football-v0.2.0.tar.gz \
  https://files.shenqianqian.com/football/releases/v0.2.0/football-v0.2.0.tar.gz
curl -fL --retry 3 -o SHA256SUMS \
  https://files.shenqianqian.com/football/releases/v0.2.0/SHA256SUMS
sha256sum -c SHA256SUMS
```

**只有出现 `football-v0.2.0.tar.gz: OK` 才继续。** 如果目录 `/opt/football/releases/football-v0.2.0` 已经存在，应先检查，不要直接覆盖。

```bash
sudo tar -xzf football-v0.2.0.tar.gz -C /opt/football/releases
cd /opt/football/releases/football-v0.2.0
```

## 4. 配置数据库密码并启动

```bash
sudo cp .env.example .env
sudo chmod 600 .env
openssl rand -hex 32
sudo nano .env
```

将生成的随机密码粘贴到 `.env` 的 `POSTGRES_PASSWORD=` 后面。**不要将 `.env` 发给别人、提交至 GitHub，或放到文件服务器的公开目录。**

```bash
sudo docker compose config --quiet
sudo docker compose up -d --build
sudo docker compose ps
```

首次构建需要下载 Python / Soccerdata / Penaltyblog 依赖，可能需要一些时间。`api` 在数据库健康后启动并自动初始化最小赛果表；`caddy` 在 API 健康后启动并尝试为 `fb.linmeng.ai` 配置 HTTPS。

健康检查：

```bash
curl -fsS https://fb.linmeng.ai/healthz
curl -fsS https://fb.linmeng.ai/api/status
```

页面地址：`https://fb.linmeng.ai/`；交互式接口文档：`https://fb.linmeng.ai/api/docs`。

## 5. 首次导入真实历史赛果

当前数据库默认没有比赛数据，网站会显示空状态；**不会生成演示假预测**。在可以访问第三方赛果网站的环境里，使用已实现的 `football fetch-results` 导出标准 CSV，例如：

```bash
football fetch-results --league 'ENG-Premier League' --season '2024-25' \
  --as-of 2026-10-29 --output epl-2024-25.csv
```

遵守数据提供方的使用条款。此前开发环境访问 Football-Data.co.uk 曾因 DNS 超时失败；实际源站可访问性仍需在 VPS 上确认。

将 CSV 放到**VPS 当前版本目录**的 `data/raw/` 下，然后导入（当前 API 的 Compose 将其只读挂载到 `/app/data`）：

```bash
sudo mkdir -p data/raw
# 将获得授权的 CSV 拷贝到 data/raw/epl-2024-25.csv
sudo docker compose exec api football import-results --csv /app/data/epl-2024-25.csv
```

导入有独立赛程唯一约束，重复导入会跳过已有比赛，不会悄悄覆盖赛果。完成后刷新 `/api/status`，首页联赛/球队下拉框会出现可选项。

注意当前接口是**对历史赛果进行即时模型拟合**，不自动产生未来赛程；首次预测可能较慢。赔率、赛前 xG、阵容时间快照、赛程自动调度和后台模型版本管理留待下一阶段。

## 6. 更新与回滚原则

- 每次更新使用新的唯一版本号和新目录，不覆盖旧发布包。
- `compose.yaml` 固定项目名 `football`，数据库/Caddy 证书以 Docker 命名卷保留，不因应用源码目录变化而被覆盖。
- 更新前备份 PostgreSQL（例如通过 `pg_dump` 导出至**非公开、受限目录**）。
- 切旧版本时先检查其配置与数据库 Schema 是否兼容，再从对应版本目录执行 `docker compose up -d --build`。
- 不要为回滚执行 `docker compose down -v`：`-v` 会删除数据库卷，造成实际数据丢失。

## 7. 安全边界

- 文件服务器发布包允许公开下载，但其中绝不能包含 `.env`、数据库、私钥、原始客户数据。构建脚本只打包白名单文件。
- VPS 的 `.env`、PostgreSQL 认证凭据、Docker 数据卷不经 files 服务器分发。
- 公开 API 当前未实现访问账号/风控/限流，首次版本适合小流量测试；生产公开推广前应补充限流、采集调度和运维告警。
