# Football：GitHub 与 files.shenqianqian.com 发行约定

> 更新时间：2026-10-29。**GitHub → files 自动发行已经实际验证成功。VPS 由用户手工安装和更新，不属于自动发布链路。** 不要沿用旧版“仅手动触发、尚未验证连通性”的说明。

## 1. 各方职责

| 位置/角色 | 负责的事 | 不负责的事 |
| --- | --- | --- |
| GitHub `byebyezhy/football` | 源码、测试、feature PR、助手检查 CI 与合并、版本工件、自动发布 `test` | VPS root 登录与服务器安装 |
| `files.shenqianqian.com` | HTTPS 公开提供不可变源码包、SHA256、版本元数据、`test/stable` 指针 | 数据库、预测 API、爬虫、Docker 运行 |
| Ubuntu 24.04 VPS `45.12.52.34` | **用户自己**通过 `root:22` 登录，安装/更新/回滚 Docker 网站 | GitHub Actions 不持有 VPS 密钥，不自动部署 |
| 助手 | 写代码、测试、提交 PR、检查并合并、验证 files 公网包、提供 VPS 操作命令 | 不请求 VPS SSH 私钥、不替用户登录 VPS |

用户明确要求常规 GitHub 操作由助手完成，不要每次让用户手工点击；同时明确拒绝 GitHub Actions 自动 SSH 部署 VPS。这个边界需要长期保持。

## 2. 自动测试版本发布（已跑通）

1. 助手从 `main` 创建功能分支，提交代码及测试，创建 PR。
2. `.github/workflows/foundation-checks.yml` 对 PR 运行测试；助手核对成功后直接合并。
3. `main` 的新提交自动触发 `.github/workflows/publish-files.yml`。GitHub 先通过离线测试，再生成不可变版本 `v0.2.<workflow_run_number>`、tar.gz、`SHA256SUMS`、`release.json`。
4. 工作流通过文件服务器专用 SSH 账号上传到 `/srv/files/public/football/releases/<version>/`；远端校验 SHA256、原子确定不可变目录。
5. 从公网 HTTPS **完整下载 tar.gz**，复核 SHA256 成功后，才原子更新 `channels/test.json`。上传/公开下载/校验失败均不得宣称发布成功。
6. 助手核对 GitHub Actions `package`、`publish` 结果及公网 test 指针后，把版本号、包链接和验证结果告诉用户；用户决定何时在 VPS 安装该版本。

当前测试版权威入口：

```text
https://files.shenqianqian.com/football/channels/test.json
```

不要把文档里的某个历史版本号当成最新版本。2026-10-29 曾验证 `v0.2.3`，后续提交会自动生成更高版本。

## 3. files 上的发布目录

```text
/srv/files/public/football/
  releases/
    v0.2.N/
      football-v0.2.N.tar.gz
      SHA256SUMS
      release.json
  channels/
    test.json
    stable.json
```

- 发布后的 `releases/<version>/` **不可覆盖**。
- `channels/*.json` 只是指针，可经验证后原子切换；不要用删除历史版本来实现回滚。
- 公开源码 tar.gz 包含经过白名单选取的 README/pyproject/部署文件及 Python 源码、文档、测试；**不包含** `.env`、SSH 私钥、数据库、原始数据、CI 密钥等。

## 4. 保留的手动工作流输入

自动 `main` → `test` 是日常默认路径，但 `workflow_dispatch` 仍提供：

| 操作 | 行为 | 适用情况 |
| --- | --- | --- |
| `build-only` | 运行测试并产生 Actions 工件，但不向 files 上传 | 单独核验 |
| `publish-new` | 创建不可变发行目录并更新渠道；同版本已存在则拒绝覆盖 | 明确指定新版本发布 |
| `promote-existing` | 验证已存在的版本/commit/SHA256，再切换渠道 | 渠道提升或回滚 |

`test` 可从 `main` 或匹配的 tag 发布；**`stable` 必须从与版本号相符的 Git tag 发布，不随 `main` 自动更新**。正式版或回滚应由用户明确指定目标版本；助手可代办 GitHub 操作，但不能默认为所有测试版直接升级稳定版。

## 5. files SSH 安全配置（已经完成）

- SSH：`files.shenqianqian.com:37767`。
- 专用用户：`footballdeploy`；与矿池项目的 `btcdeploy` 分离。
- GitHub 仓库级 Actions Secrets：`FILES_SSH_USER`、`FILES_SSH_KEY`、`FILES_KNOWN_HOSTS`。不要把 Secret 值放入聊天、日志、仓库或公开发行包。
- 工作流使用 `StrictHostKeyChecking=yes`、经过核验的 known_hosts 和非交互 SSH 登录。
- 历史问题：files SSH 配置默认 `PubkeyAuthentication no`，仅 `btcdeploy` 例外；用户为 `footballdeploy` 单独开启公钥认证后，2026-10-29 重跑 GitHub 发布任务成功。
- 发行服务器只允许上传足球项目自己的路径，不共享矿池项目目录，也不执行预测服务。

## 6. VPS 安装与升级（**用户操作**）

- 运行服务器：`root@45.12.52.34:22`，Ubuntu 24.04，网站 `https://fb.linmeng.ai`。
- 用户已将 Cloudflare DNS 改为灰云，公开 A 记录指向 `45.12.52.34`；网站仍需在 VPS 上真正安装启动。
- 助手**只负责 files 上的版本管理**，不能自动往 VPS 推送、重启容器或替用户创建 `VPS_SSH_KEY`。
- 用户在 VPS 上从 `test.json` 查询实际版本，下载 tar.gz 和 `SHA256SUMS`、核验后解压，复用私有 `.env`、数据与 Docker 卷，运行 `docker compose up -d --build`，再核验 HTTPS/API。
- 详见 **[Ubuntu VPS 手工部署与更新指南](DEPLOY_VPS.md)**；不要用旧版硬编码 `v0.2.0` 的步骤。

## 7. 变更、回滚与文档维护原则

- files 版本以 commit + SHA256 + 不可变目录固定，可追溯历史。
- 测试版构建成功但发布失败时，只报告构建成功；优先由助手用 GitHub 工具重跑失败的发布作业并检查公网指针。
- VPS 更新前用户自己备份数据库；如需恢复旧代码，检查数据库兼容性后在旧目录运行 Compose。**绝不执行 `docker compose down -v`**。
- 功能、流程和服务器状态有变化时，助手负责同步更新仓库根目录的 `AGENTS.md` 与相关文档。新对话先读 `AGENTS.md`，再核对 `main`、Actions、test 指针和 VPS 用户反馈。
- 用户曾要求仓库为 Private，但 2026-10-29 GitHub API 曾返回 `private: false`；请将此作为需核对的设置差异。发行包可公开下载不代表用户同意仓库永久公开。
