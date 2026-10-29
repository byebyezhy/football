# Football 网站：Ubuntu 24.04 VPS 手工部署与更新

> 维护日期：2026-10-29。**明确职责：助手负责 GitHub 代码、PR、CI、合并和发布到 files；用户自己登录 VPS 执行安装、更新和回滚。不要再创建 VPS 的 GitHub Actions SSH 密钥，也不要对 VPS 自动部署。**
>
> 以下示例适用于用户确认的 VPS：`root@45.12.52.34:22`，域名 `fb.linmeng.ai`。用户已经将 Cloudflare DNS 设置为灰云（DNS only），公开 DNS A 记录已核实指向 `45.12.52.34`。本文件只是操作指南；除非健康检查真实通过，不能宣称网站已经部署成功。

## 1. 责任划分与安全约定

- GitHub `main` 合并后，`.github/workflows/publish-files.yml` 自动构建、测试、上传不可变源码版本包，并更新 [files 的 test 版本指针](https://files.shenqianqian.com/football/channels/test.json)。
- `files.shenqianqian.com` **只公开分发安装包**，不运行网站、数据库或采集任务。发布包公开可下载已获用户同意。
- VPS 完全由用户通过 SSH 管理。**不配置 `VPS_SSH_KEY`、不让 GitHub Actions 远程登录 VPS**；助手可提供/核验命令、诊断日志和更新步骤。
- 每次部署按 `test.json` 查实际版本。版本号会随着合并持续递增，不能长期写死 `v0.2.0` 或 `v0.2.4`。
- 不要把 `.env`、数据库、私钥、SSH 密钥或原始受许可数据上传 GitHub/files。

## 2. 检查 VPS 基础环境

在自己的终端登录 VPS：

```bash
ssh root@45.12.52.34 -p 22
```

确认 Ubuntu/Docker 和网络状态：

```bash
cat /etc/os-release
docker --version
docker compose version
ss -lntp
```

如果缺少 Docker Engine 或 Compose plugin，按 [Docker 官方 Ubuntu 安装指南](https://docs.docker.com/engine/install/ubuntu/) 安装。不要未经检查就覆盖已有 Docker、反向代理或防火墙配置。确保系统及云厂商防火墙允许 `80/tcp`、`443/tcp`，并始终保留 `22/tcp` 的 SSH 通道；`8000/5432` 不需要对公网开放。Caddy 使用域名自动申请与续期 HTTPS 证书。先检查端口 `80/443` 是否已有其他服务。

如 VPS 缺少后续命令，需要预先安装 `curl`、`python3`、`openssl`。当前发布包是 Docker 构建所需源码快照，不是预编译 Docker 镜像。

## 3. 下载当前 test 版本并核对 SHA256

全部操作在 VPS 的 root Shell 中执行。先读取最新版本：

```bash
RELEASE_VERSION="$(curl -fsSL https://files.shenqianqian.com/football/channels/test.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')"
echo "$RELEASE_VERSION"
```

应输出 `v0.2.N` 形式，例如 `v0.2.4`。**请确认版本号确实是 `v` 加三个数字字段，不要在版本为空或异常时继续。**

```bash
mkdir -p "/opt/football/downloads/$RELEASE_VERSION" /opt/football/releases /opt/football/shared/data/raw
cd "/opt/football/downloads/$RELEASE_VERSION"

curl -fL --retry 3 -o "football-$RELEASE_VERSION.tar.gz" \
  "https://files.shenqianqian.com/football/releases/$RELEASE_VERSION/football-$RELEASE_VERSION.tar.gz"
curl -fL --retry 3 -o SHA256SUMS \
  "https://files.shenqianqian.com/football/releases/$RELEASE_VERSION/SHA256SUMS"

sha256sum -c SHA256SUMS
```

**只有看到 `football-vX.Y.Z.tar.gz: OK` 才继续安装。** 版本目录不可覆盖；若已存在，先检查旧目录与容器状态。

```bash
test ! -e "/opt/football/releases/football-$RELEASE_VERSION" && \
  tar -xzf "football-$RELEASE_VERSION.tar.gz" -C /opt/football/releases

cd "/opt/football/releases/football-$RELEASE_VERSION"
```

## 4. 首次设置数据库密码、持久化数据并启动

这一步把密码及用户导入的 CSV 放到 `/opt/football/shared/`。**后续更新重复使用同一密码与数据目录，不要重新生成数据库密码，也不要删除 Docker 数据卷。**

```bash
mkdir -p /opt/football/shared/data/raw

if [ ! -e /opt/football/shared/.env ]; then
  cp .env.example /opt/football/shared/.env
  chmod 600 /opt/football/shared/.env
  DB_PASS="$(openssl rand -hex 32)"
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$DB_PASS/" /opt/football/shared/.env
  unset DB_PASS
fi

ln -s /opt/football/shared/.env .env
ln -s /opt/football/shared/data data
```

`ln -s` 只适用于新的、尚未配置过的版本目录；如果提示目标已存在，先检查原有 `.env` / `data`，**不要盲目覆盖**。

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

首次构建会下载 Python 基础镜像及 Soccerdata/Penaltyblog 等依赖，可能需要几分钟。Compose 固定项目名为 `football`：PostgreSQL 数据和 Caddy 证书保存在 Docker 命名卷中。应用将在数据库健康后初始化最小赛果表；在没有真实赛果时首页显示空状态，这是预期行为。

## 5. 验收网站并诊断失败

```bash
curl -fsS https://fb.linmeng.ai/healthz
curl -fsS https://fb.linmeng.ai/api/status
```

预期 `/healthz` 返回 `{"status":"ok","service":"football-api"}`；`/api/status` 应包含数据库状态。网站首页：`https://fb.linmeng.ai/`；接口文档：`https://fb.linmeng.ai/api/docs`。

若出现 502、503、521、证书错误或空白页，先检查：

```bash
docker compose ps
docker compose logs --tail=100 api db caddy
ss -lntp
```

重点核对 DNS 是否指向 `45.12.52.34`、云平台与系统防火墙是否允许 80/443、端口是否被旧 Nginx/Caddy 占用、容器是否健康、Caddy 是否正常签发证书。不要在排障时执行 `docker compose down -v`。

## 6. 首次导入真实历史赛果

当前网站只有预测逻辑和最小数据库，**没有预装真实赛果、没有自动抓取未来赛程，也没有验证过的实战预测准确率**。需要使用获得授权的数据源获取标准 CSV。

Soccerdata MatchHistory 可用时，可以先检查连通性，再采集到容器的临时目录，最后复制到 VPS 的持久化原始数据目录。请在**新版 Docker 镜像**内运行；早期 v0.2.5 镜像的非 root 用户首次采集时，会因为 `tls_requests` 无法写入自身的本地 `.so` 缓存而报 `Permission denied`，已在后续构建中改为镜像构建时预置该库。

```bash
cd "/opt/football/releases/football-$RELEASE_VERSION"

docker compose exec api football source-preview \
  --league 'ENG-Premier League' --season '2024-25' --as-of 2026-10-29

docker compose exec api football fetch-results \
  --league 'ENG-Premier League' --season '2024-25' --as-of 2026-10-29 \
  --output /tmp/epl-2024-25.csv

API_CONTAINER="$(docker compose ps -q api)"
docker cp "$API_CONTAINER:/tmp/epl-2024-25.csv" \
  /opt/football/shared/data/raw/epl-2024-25.csv

docker compose exec api football import-results --csv /app/data/epl-2024-25.csv
```

请确保 `source-preview` 真正返回比赛，且 `fetch-results` 提示已成功保存，再运行 `docker cp` 和 `import-results`；若采集失败，停在该步骤并记录错误，不要将空文件当作真实赛果。`fetch-results` 拒绝覆盖现有目标文件；重复运行之前，应先确认临时文件是否存在。

如果来源无法访问，也可以从获得授权的其他来源准备标准 CSV，放在 VPS `/opt/football/shared/data/raw/`，例如：

```bash
cp /root/epl-2024-25.csv /opt/football/shared/data/raw/epl-2024-25.csv

cd "/opt/football/releases/football-$RELEASE_VERSION"
docker compose exec api football import-results --csv /app/data/epl-2024-25.csv
```

注意 CSV 来源和文件名只是示例；请先实际准备该文件。重复导入会跳过已有比赛，避免重复记录。导入后重新访问 `/api/status` 和首页联赛/球队选项。

## 7. 以后升级：只更新 VPS，不需要改 GitHub

1. 助手完成新代码的 PR、CI、合并与 files 发布后，会告知最新版本，并提供 `test.json` 和 SHA256 验证结果。
2. **用户自己登录 VPS**。在当前已运行版本目录执行数据库备份：

```bash
mkdir -p /opt/football/backups
umask 077
docker compose exec -T db pg_dump -U football football > "/opt/football/backups/football-$(date +%Y%m%d-%H%M%S).sql"
```

3. 重复第 3 节下载/校验/解压**新版本**，然后进入新版本目录。重复第 4 节中共享 `.env` 与 `data` 的链接步骤（已经存在的共享文件绝不重新生成），执行：

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

4. 重复第 5 节 HTTPS/API 验收。不要同时从旧版本目录运行 `docker compose up`；固定项目名 `football` 会让新版本接管同一组服务与命名卷。
5. 若需回滚，先确认数据库 Schema 兼容，再进入旧版本目录执行 `docker compose up -d --build`。**绝不执行 `docker compose down -v`**，那会删除数据卷。

## 8. 安全边界与后续开发

- `.env`、PostgreSQL 数据卷、数据库备份与原始数据只存在 VPS 的私有存储，不通过 files 发布。
- 公网 API 当前没有账户认证/限流/风控，先以小流量验证；正式推广前补上运维监控与安全措施。
- 新采集源、新模型、自动采集调度、可靠数据快照、真实赛季回测、模型版本管理均是后续阶段，不能当作当前已上线功能。
- **不要为方便部署而让 GitHub Actions 持有 VPS root 密钥或其他 VPS 凭据**；这是用户在 2026-10-29 明确选择的长期职责划分。
