# GitHub 与 files.shenqianqian.com 发布约定（草案）

状态：**待部署验证**。这里是 `football` 项目拟采用的路径和发布协议，不表示服务器目录、DNS 路由或凭据已实际配置。不能将现有 `btcproxy` 路径复用到足球项目。

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
4. 测试发布由人工触发 GitHub Actions；稳定发布需审核通过的 tag/commit，并由人工确认。
5. 上传到唯一临时目录，远端校验 SHA256，随后原子移动到不可变 release 目录。
6. 验证公网文件可读取且哈希一致，再原子更新 `channels/test.json` 或 `channels/stable.json`。失败不得修改原渠道指针。
7. 回滚通过恢复渠道指针到旧版本；保留历史发布文件。

**初期不启用自动发布**，优先实现测试、打包与校验；待服务器连接和权限验收后再启用上传步骤。

## 4. SSH/安全约定

- 已知文件服务器 SSH 端口：`37767`（SSH 使用 `-p`，SCP 使用 `-P`）；部署前重新确认服务器地址和防火墙。
- GitHub Actions 密钥需作为 Secrets/Environment Secrets 管理；固定可信 `known_hosts`，使用 `StrictHostKeyChecking=yes`，不得盲目跳过指纹校验。
- 只能上传经过明确列举的构建产物；严禁上传 `.env`、API Token、数据库、个人数据、TLS/CA 私钥、训练原始数据或含凭据的日志。
- 公网目录中的文件必须允许 Web 服务器读取，但不能让其具有执行或随意覆盖权限。
- 发布不自动重启运行服务器上的模型/API。

## 5. 发布前待确认事项

- `football` 对应的站点目录及 HTTPS 路由是否存在（当前尚未创建）。
- GitHub Actions 是否能安全复用之前的 SSH Secrets，或需要 football 专用最小权限发布账号。
- 实际运行服务器、目标系统、版本包形态（源码包/Docker 镜像/可执行程序）。
- 测试/正式发布审批人、保护环境与保留/回滚策略。

在以上事项验证前，不向 files 服务器执行任何写入操作。
