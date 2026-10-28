# GitHub 与 files.shenqianqian.com 发布约定

状态：**手动发布代码已实现，服务器连通性尚未验收**。本仓库提供构建、校验、上传和渠道切换逻辑；不表示服务器目录、HTTPS 路由、GitHub Secrets 或环境审批已实际配置。不能将现有 `btcproxy` 路径复用到足球项目。

## 1. 职责划分

- **GitHub**：代码、feature 分支、Pull Request、人工审核合并、CI、版本标签及构建工件。
- **files.shenqianqian.com**：通过 HTTPS 分发不可变版本包、校验和、版本元数据、渠道指针。它**不运行**采集、模型、API 或数据库。
- **运行服务器（待定）**：部署数据库、采集调度器、训练任务和 API；由独立的部署流程处理。

## 2. 建议目录与公网 URL

```text
/srv/files/public/football/
  releases/v0.1.0/
    football-v0.1.0.tar.gz
    SHA256SUMS
    release.json
  channels/
    test.json
    stable.json
```

公网根路径拟为 `https://files.shenqianqian.com/football/`。其中 `releases/<version>/` 发布后不可覆盖；`channels/*.json` 原子替换，只指向已验证的固定版本。服务器路径及 Nginx 映射需要读取线上配置后确认。

## 3. GitHub 流程

1. 从 `main` 建 feature 分支，提交代码和测试。
2. PR 经人工审核和 CI 通过后手工合并；不启用自动合并。
3. 每个版本记录来源 commit、依赖锁定信息、构建时间、版本、SHA256。
4. 测试发布由人工触发 GitHub Actions；稳定发布只能从与版本号对应的 Git tag 发起，并由人工确认。
5. 上传到唯一临时目录，远端校验 SHA256，随后原子移动到不可变 release 目录。
6. 验证公网文件可读取且哈希一致，再原子更新 `channels/test.json` 或 `channels/stable.json`。失败不得修改原渠道指针。
7. `promote-existing` 可以将已发布、SHA256/commit 完全一致的版本切换到渠道；选旧版本的 tag 再操作即可回滚渠道指针，历史文件保留。

**不启用自动发布**：只有 `workflow_dispatch` 手动运行。默认 `build-only`，不读取 SSH 密钥、不连接文件服务器。

## 4. 操作入口与模式

PR 审核合并后进入 `byebyezhy/football` → **Actions** → **Build and optionally publish football release** → **Run workflow**。

| 选项 | 作用 | Git ref 限制 |
| --- | --- | --- |
| `build-only` | 执行离线测试，构建源码 tar.gz、`SHA256SUMS`、`release.json` 并上传到 Actions Artifact；默认选项 | `main`，或与版本一致的 tag |
| `publish-new` | 在新的版本目录发布；拒绝覆盖同名版本，验证公网下载哈希后原子更新渠道 | `test` 可用 `main`/tag；`stable` 只能用同名 tag |
| `promote-existing` | 校验已有 release 的公网元数据、代码 commit 和 tar 哈希，再原子更改渠道指针；支持测试→稳定、回滚 | 与 `publish-new` 一致 |

输入版本如 `v0.1.0`；渠道为 `test` 或 `stable`。**已发布过的相同版本不要选择 `publish-new`**，应改选 `promote-existing`；旧版本的 SHA256 必须和当前选中的 Git ref 构建结果一致。

构建工件只包含经过白名单筛选的 `README.md`、`pyproject.toml` 和 `src/**/*.py`、`docs/**/*.md`、`tests/**/*.py`。不包含 `.env`、`data/`、模型产物、`.git/`、私钥、CI 凭据或抓取的数据。该 tar.gz 是源码快照，`pyproject.toml` 的 Python 包版本目前仍处于 `0.1.0.dev0`。

## 5. GitHub Environment 与 SSH 准备（需仓库管理员完成一次）

1. 仓库 **Settings → Environments** 创建环境 `football-files`。建议设置 Required reviewers，并仅允许受信任的分支及版本 tag 部署；单人审核时留意 GitHub 的防止自我批准选项。
2. 只在环境 `football-files` 中新增以下 **Environment secrets**，不用发送到聊天窗口：
   - `FILES_SSH_USER`：有权写入足球发布目录的专用 SSH 用户；尽量不用 root。
   - `FILES_SSH_KEY`：该用户的专用 Ed25519 私钥完整内容（对应公钥需配置到文件服务器账号）。
   - `FILES_KNOWN_HOSTS`：经过独立验证的 SSH 主机公钥记录，必须匹配 `[files.shenqianqian.com]:37767`。**不要仅凭未核验的 ssh-keyscan 输出建立信任。**
3. 在服务器确认 `/srv/files/public/football` 与公网 `https://files.shenqianqian.com/football/` 的实际映射和权限。工作流在 `publish-new` 时可以建立 `releases/`、`channels/` 和 `.staging/` 子目录，但不会修改 Nginx。
4. 首次运行先选 `build-only` 确认工件，再人工选 `publish-new` + `test`；等公网校验成功后，将同一 commit 打标签 `v0.1.0`，从这个 tag 运行 `promote-existing` + `stable`。

### 安全校验与故障处理

- 构建前运行离线测试；源码包白名单、文件哈希、commit、版本号校验均通过后才可上传。
- SSH 使用固定 `37767` 端口、专用密钥、`StrictHostKeyChecking=yes` 和经过验证的 `known_hosts`；密钥仅存在临时运行器中。
- 上传到唯一临时目录，服务器 `sha256sum -c` 成功后移动到 `releases/<version>/`，**不覆盖已有版本**。
- 从公网完整 GET 下载 tar.gz，SHA256 匹配后才允许 `channels/*.json` 原子替换。网络或校验失败不会更新渠道，但可能留下已上传的不可变版本，需要用 `promote-existing` 补充确认。
- 若 Nginx 映射或服务器权限有误，部署作业会失败；不要把失败视为已成功发布。
- 回滚不删除文件：选择旧版本对应 tag，以 `promote-existing` 更新稳定渠道。受控发布依赖 GitHub 环境审批配置，**创建这个环境本身不等于已经启用 Required reviewers**。

## 6. SSH/安全约定

- 已知文件服务器 SSH 端口：`37767`（SSH 使用 `-p`，SCP 使用 `-P`）；部署前重新确认服务器地址和防火墙。
- GitHub Actions 密钥需作为 Secrets/Environment Secrets 管理；固定可信 `known_hosts`，使用 `StrictHostKeyChecking=yes`，不得盲目跳过指纹校验。
- 只能上传经过明确列举的构建产物；严禁上传 `.env`、API Token、数据库、个人数据、TLS/CA 私钥、训练原始数据或含凭据的日志。
- 公网目录中的文件必须允许 Web 服务器读取，但不能让其具有执行或随意覆盖权限。
- 发布不自动重启运行服务器上的模型/API。

## 7. 发布前待确认事项

- `football` 对应的站点目录及 HTTPS 路由是否存在（当前尚未创建）。
- `football-files` Environment Secrets、审批规则和专用 SSH 账号是否已配置（旧仓库 Secrets 不会自动共享）。
- 实际运行服务器、目标系统、版本包形态（源码包/Docker 镜像/可执行程序）。
- 测试/正式发布审批人、保护环境与保留/回滚策略。

在这些环境准备和线上映射验证前，**仅运行 `build-only`**。此 PR 不会对 files 服务器执行任何写入操作。
