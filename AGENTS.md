# Football 足球比分预测项目：长期交接记忆

> **给未来新对话 / AI 开发助手的入口文档。** 本文件总结项目目标、历史决策、现有实现、部署信息、权限边界和下一步工作。新会话若能访问 `byebyezhy/football`，请先阅读本文件，再核验 GitHub `main` 分支与实际线上状态，不要求用户反复复述已确定的事情。
>
> 建档时间：**2026-10-29（Asia/Shanghai）**。这是持续维护的交接文件，不是实时状态接口；每次开发结束，请同步更新关键决策与未完成事项。**严禁在本文件写入任何 SSH 私钥、密码、Token、数据库凭据或真实 `.env`。**

## 0. 新对话请先这样接手

1. 识别项目为中文 **football 足球比分概率预测平台**，GitHub 仓库：[`byebyezhy/football`](https://github.com/byebyezhy/football)，默认分支 `main`。
2. 阅读本文件，以及 `README.md`、`docs/ARCHITECTURE_V1.md`、`docs/DATA_SOURCES.md`、`docs/DEPLOY_VPS.md`；以**当前代码和实际 CI/服务状态**为准，旧文档可能仍写“手工发布”。
3. 读取 [当前测试发布指针](https://files.shenqianqian.com/football/channels/test.json)，从中确认实际版本、commit、tarball URL、SHA256；不要把本文的历史版本当成最新版本。
4. 检查 [GitHub Actions](https://github.com/byebyezhy/football/actions) 和最新 PR/commit，确认测试及发布任务真实成功后再推进下一阶段。
5. 用户已提供 2026-10-29 的网站截图：`fb.linmeng.ai` 页面正常渲染，UI 显示“数据服务已连接”，但历史比赛数为 **0**。后续重点是修复数据源首次加载的本地权限问题、导入真实赛果、验证首场预测；网站截图不等同于所有 HTTPS/API 外部验收均通过。
6. 默认使用中文与用户交流，主动推进工作。**用户已经明确授权助手直接完成 GitHub 代码提交、创建 PR、检查 CI、合并 PR、触发/重跑构建与 files 测试发布，不要再逐项要求用户去 GitHub 点击。VPS 登录、安装、更新、回滚由用户亲自执行，助手只负责给出经核对的命令和诊断。**

## 1. 产品目标与不变的架构原则

- 核心是**赛前足球比分概率预测**：输出精确比分概率矩阵、胜/平/负概率，支持 Top 5 比分及历史回测；不是宣称必胜或保证盈利的投注平台。
- 借鉴 [`penaltyblog`](https://github.com/martineastwood/penaltyblog) 的预测模型和 [`soccerdata`](https://github.com/probberechts/soccerdata) 的采集实现；优先以依赖/适配器方式复用，而不是整库复制。
- 关键产品要求：**预测引擎 + 可持续扩充的多个采集源**。新增采集源应通过插件契约接入，不能让业务层或模型依赖单一爬虫。
- 当前从历史赛果、Poisson、Dixon–Coles 和一个联赛的严格时间回测起步；后续才扩展 fixtures、team_stats、xG、odds、lineups、injuries、Elo 等。
- 数据需要标准化球队、联赛、比赛标识，保留来源与采集时间，防止重复/冲突；所有赛前预测和回测严格禁止使用赛后才知道的数据。
- 长期产品方向可发展为“有依据、能复盘”的中文足球分析台：今日赛程、单场分析、多模型对比、预测快照、赛后复盘、校准与数据源健康状况。目前**并未全部实现**。
- 不能凭模拟数据或未经验证的模型输出宣称预测准确率；要用真实授权历史数据比较 Brier、log loss、RPS、比分命中率、校准。

## 2. 当前代码与功能（V0.2 基础版）

| 组件 | 位置 / 当前能力 |
| --- | --- |
| Python 包与 CLI | `pyproject.toml`；Python >=3.11；入口 `football` |
| 数据采集插件 | `src/football_predictor/sources/`；能力契约/注册表，已实现 `SoccerdataMatchHistory` 历史赛果适配器 |
| 模型 | `src/football_predictor/models/penaltyblog_adapter.py`；Poisson / Dixon–Coles，按截止时间训练 |
| 数据契约/CSV | `domain.py`、`results_io.py`；标准化赛果及受控文件写入 |
| 回测 | `backtest.py`；按比赛日期 walk-forward，Brier、RPS、log loss、精确比分指标 |
| 数据库 | `storage.py`；PostgreSQL 最小赛果表、来源字段、幂等导入；尚无完整迁移/多源冲突系统 |
| 预测服务 | `forecast_service.py`；按数据版本/日期缓存拟合，避免明显的未来赛果泄漏 |
| Web/API | `web/app.py`、`web/static/index.html`；联赛、球队、日期、模型选择，显示 1X2 和 Top 5 比分 |
| VPS 部署 | `Dockerfile`、`compose.yaml`、`deploy/Caddyfile`；FastAPI + PostgreSQL + Caddy HTTPS |
| 测试 | `tests/`；离线契约、回测、API、存储、构建/发布工具测试 |

主要 API：`/healthz`、`/api/status`、`/api/competitions`、`/api/teams`、`/api/predict`。无真实赛果时网站应显示**空状态**，不能伪造预测。初版 API 对历史赛果即时拟合模型，尚无未来赛程自动发现或完整的生产缓存/调度体系。

常见 CLI：

```bash
# 安装需要的功能
python -m pip install -e '.[all,web,test]'

# 离线测试
PYTHONPATH=src python -m unittest discover -s tests -v

# 授权数据源抓取/导出历史赛果
football fetch-results --league 'ENG-Premier League' --season '2024-25' \
  --as-of 2026-10-29 --output data/raw/epl-2024-25.csv

# 离线回测
football backtest-csv --csv data/raw/epl-2024-25.csv \
  --model dixon_coles --min-training 100 --output reports/epl-2024-25.json

# VPS 数据库导入（以已存在且获许可的 CSV 文件为前提）
football import-results --csv data/raw/epl-2024-25.csv
```

CSV 列：`competition,season,date,home_team,away_team,home_goals,away_goals`；可选 `source_id`。访问 Football-Data.co.uk 曾受开发环境 DNS/网络限制，**不能据此假定 VPS 已经成功采集真实赛果**。

## 3. 已完成的 GitHub 阶段

- PR **#1–#5**：设计/源插件和模型/CSV 抓取与回测/构建发布工作流/Web + PostgreSQL + VPS Docker 骨架；均已合并。
- PR **#6**：[自动化 test 发布](https://github.com/byebyezhy/football/pull/6)，已合并到 `main`，merge commit `2e475657b784007746f3143733b1b831aeb2f611`。该 PR 的 Foundation checks 通过。
- CI 已验证基础离线测试（历史一次完整测试为 27 项：25 通过、2 项因可选第三方依赖缺失而跳过）；不同环境可能有不同结果，需看最新 Actions。
- PR #6 合并触发 [发布工作流 run #3](https://github.com/byebyezhy/football/actions/runs/40825389859)：首次构建成功、发布因 files SSH 登录拒绝失败。用户在服务器为 `footballdeploy` 解除公钥认证限制后，助手使用 GitHub 连接器**重跑失败任务**，发布最终成功。
- **2026-10-29 已独立验证的历史测试包**：`v0.2.3`，commit `2e475657b784007746f3143733b1b831aeb2f611`，公开包 `https://files.shenqianqian.com/football/releases/v0.2.3/football-v0.2.3.tar.gz`，SHA256 `bbeb1050d10ae78c89053f86563524bf95fdabb63c51411d8584d493db23d63e`。当时公网 `channels/test.json` 与 tarball 的实际 SHA256 一致。**之后如有新提交，请以渠道指针为准。**

## 4. GitHub → files 自动构建发布（已跑通）

仓库 Actions 工作流：

- `.github/workflows/foundation-checks.yml`：PR 及 `main` 的基础测试。
- `.github/workflows/publish-files.yml`：**每次推送/合并到 `main`，自动测试、打包唯一版本 `v0.2.<GitHub workflow run_number>`，用 SSH 上传并在 HTTPS SHA256 复核后更新 `test` 渠道**。
- 仍支持 `workflow_dispatch` 的 `build-only`、`publish-new`、`promote-existing`。`stable` **不能自动跟随 main**，需要匹配版本的 Git tag，并有明确的发布决策。
- `scripts/build_release.py` 只打包白名单源码、文档、部署文件，拒绝私人配置/原始数据；`scripts/publish_files.py` 执行不可变版本目录创建、校验、原子渠道切换。
- 自动发布错误会直接使 GitHub job 失败；不得仅凭包构建成功就报告 files 发布成功。已有失败任务优先使用 GitHub 接口重跑失败 job。
- **2026-10-29 最终明确的职责边界：自动化止于 files 的公开发行包与渠道版本管理。不要为 VPS 配置 GitHub Actions SSH Secret，不要建立自动部署到 VPS 的工作流，也不要请求 VPS root 凭据。用户登录 VPS，手工安装和更新。**

文件服务器：

| 事项 | 已约定值 |
| --- | --- |
| 地址 | `files.shenqianqian.com` |
| SSH 端口 | `37767`（ssh `-p`、scp `-P`） |
| 足球专用用户 | `footballdeploy`；不要混用矿池的 `btcdeploy` |
| 远端目录 | `/srv/files/public/football/` |
| 公开渠道 | `https://files.shenqianqian.com/football/channels/test.json`；`stable.json` 另行受控发布 |
| 不可变包 | `releases/<version>/football-<version>.tar.gz`，同目录含 `SHA256SUMS`、`release.json` |
| GitHub Actions Secrets | `FILES_SSH_USER`、`FILES_SSH_KEY`、`FILES_KNOWN_HOSTS`，均为**Repository Secrets**；不得读取、打印或写入文档 |

files SSH 服务器历史配置是全局 `PubkeyAuthentication no`，`Match User btcdeploy` 允许公钥；用户后又为 `footballdeploy` 加入单独允许的 `Match User`，在 2026-10-29 确认返回 `yes`，重跑发布成功。该服务器是**文件分发服务器**，不要让其承担采集、数据库或预测 API 运行。

用户明确允许足球源码发行包**公开下载**。但数据库、`.env`、私钥、凭据、原始第三方数据绝不放在公开目录。

## 5. 运行 VPS 与网站（用户已提供上线截图，尚无真实赛果）

| 事项 | 值 / 状态 |
| --- | --- |
| VPS | Ubuntu 24.04，公网 IP `45.12.52.34`；用户表示硬件与基础环境已准备好 |
| VPS SSH | `root@45.12.52.34:22`；仅用户自己登录，不授予 GitHub Actions / 助手远程登录凭据 |
| 网站 | `https://fb.linmeng.ai` |
| 推荐部署路径 | `/opt/football/releases/football-<version>`，原始下载 `/opt/football/downloads/<version>` |
| 容器 | `api`（FastAPI）、`db`（PostgreSQL 16）、`caddy`（80/443 HTTPS） |
| 内网服务 | PostgreSQL 5432、API 8000 不直接暴露公网 |
| 密码 | VPS 上创建本地 `.env`，填写强随机 `POSTGRES_PASSWORD`，**不上传 GitHub/files** |
| 健康检查 | `https://fb.linmeng.ai/healthz` 和 `/api/status` |

**2026-10-29 用户已将发布的 v0.2.5 安装到 VPS，并发送网站截图：前端已渲染，页面显示数据服务已连接；历史赛果 0 场。** 用户在 VPS 容器里执行 `football source-preview --league 'ENG-Premier League' --season '2024-25' --as-of 2026-10-29`，报错 `Permission denied: /usr/local/lib/python3.11/site-packages/tls_requests/bin/release.json` 和同目录原生 `.so`：`tls_requests` 在首次运行时需要下载原生库，而 API 容器以无权写 site-packages 的非 root 用户运行。下一步修复方法是在 Docker **构建阶段以 root 身份预加载原生库**，然后以非 root 身份进行加载检查；不要为了临时绕过这个错误将生产容器改成 root。完整的升级/采集步骤见 `docs/DEPLOY_VPS.md`，外部 HTTPS/API 是否持续正常仍应另外验证。

操作上，由用户自己检查 VPS 的 SSH、端口、防火墙、现有服务和磁盘，再动手部署；保留数据库 Docker 命名卷，绝不执行 `docker compose down -v`。所有部署变更要有回滚方式。用户将 `.env` 和原始 CSV 数据保存在 VPS 私有的 `/opt/football/shared/` 中，每个新版本目录复用，不允许发布到 files。

## 6. 未完成、不得误报为完成的事项

1. **第一优先：修复首次采集的非 root 权限问题并交付新版到 files。** 用户已按旧版 v0.2.5 成功启动网站，但 `source-preview` 因 `tls_requests` 原生库首次运行写权限失败。修复后跑 CI（包括实际容器构建、非 root 只读运行验证），合并发布，再提供用户自行升级 VPS 的命令。**不要求用户开放 VPS SSH 给助手，不尝试自动远程部署。**
2. **第二优先：真实足球数据。** 在可合法访问来源的环境中，抓取至少一个联赛的历史结果，导入数据库并验证站点联赛/球队/比分预测功能。不得用伪造数据冒充实测。预装的 `soccerdata` 历史适配器还没在新版容器完成成功抓取验证。
3. **第三优先：可信回测。** 使用多个完整赛季做 walk-forward，公开真实样本量、Brier/log loss/RPS/精确比分命中与简单基线对照，避免时间穿越。
4. **之后：数据源扩展。** 加 fixtures、xG、赔率等插件、球队 ID 映射、源冲突处理、可审计的采集时间戳、限速缓存、定时任务和错误告警。
5. **之后：工程增强。** 数据库迁移、历史预测快照、模型版本持久化、依赖锁定、API 鉴权/限流与监控；VPS 部署仍须遵守“用户手工执行”约定。
6. **文档同步：** `README.md`、`docs/RELEASES.md`、`docs/IMPLEMENTATION_STATUS.md` 部分文字仍描述“人工审核/手动发布/服务器待验证”。它们是旧阶段记录，应在适当 PR 中更新；当前工作流代码与本文件更新的历史事实优先。

### GitHub 仓库可见性提醒

用户曾明确希望 `football` 仓库为 **Private**（GitHub Free 账号）；但 2026-10-29 GitHub REST API 对 `byebyezhy/football` 返回 `private: false`，未登录页面也可查看仓库。**这是尚未解决的设置差异，需核对 GitHub 实时可见性并在有管理权限时修正。** 发布包允许公开，并不等于用户同意仓库持续公开。任何情况下 GitHub Secrets 都不得进入源码或日志。

## 7. 与用户协作的长期规则

- 用户精通服务器、网络和硬件，对 SSH/CI 配置细节有时需要可直接复制的命令；尽量给出准确操作、预期结果和可验证的结论。
- **常规 GitHub 操作由助手负责到底：** 计划 → 小范围代码修改 → 创建 PR → 查 CI → 通过后合并 → 查自动包与 files 测试渠道 → 报告链接/版本/校验。不要每一步让用户手工审核或点击按钮。用户此前已明确授权这些动作。
- **VPS 安装/更新由用户亲自执行：** 助手提供复制即用、含校验和回滚说明的命令，用户通过 `root@45.12.52.34:22` 登录后操作。**不要再次建议把 VPS root 私钥交给 GitHub/助手，也不要要求配置 VPS SSH Secret；这是用户明确拒绝的方案。**
- `stable`/正式生产环境变更、敏感凭据/权限调整、破坏性操作、不可逆删除等应遵守实际授权与安全边界；不能把上述 GitHub 日常授权误解为无限制的服务器 root 权限。
- 保持谨慎承诺：没查到的状态标“未验证”；失败时贴具体日志摘要和下一步；不要凭猜测声称操作成功。
- 用户希望项目能够持续扩充数据采集源和预测模型，采用插件式架构；避免为短期演示牺牲未来扩展性。
- 每次有**重要状态变化**（VPS 上线、新数据源接入、正式版发布、部署位置、密钥权限结构变化、测试/回测结论）都应更新本文件中相应章节，并与实际代码/线上证据一致。

## 8. 给新对话的简短状态摘要

**当前已完成：** 数据源插件和 Poisson/Dixon–Coles 预测骨架、CSV 导入/回测、FastAPI 网站代码、PostgreSQL/Caddy Docker 部署包、GitHub 自动 CI/PR 合并流程、GitHub → files 测试版自动发布链路，`v0.2.5` 已发布、用户 VPS 的网站页面已显示（数据服务连接、0 场历史赛果）。

**当前未完成：** 修复旧镜像 `tls_requests` 首次下载依赖时的权限问题、独立 HTTPS/API 验收、真实历史数据导入、线上预测、实证精度报告，以及后续扩展采集源/调度/正式版发布。

**现在应做：** 完成 Docker 构建期 TLS 原生库预加载与 CI 只读容器验证，发布新版到 files；然后按 `docs/DEPLOY_VPS.md` 向用户提供 VPS 手工升级和采集/入库命令，绝不创建 VPS 自动部署工作流。不要让用户再次解释 football / files / GitHub / PR / SSH 的整套背景。

---

> **续写约定：** 这个文档可以在不同会话持续更新；历史事实要注明“截至何时”，实时发布版本与线上健康以 GitHub Actions、公网 test 指针和 VPS 实际探测为准。本文件承载项目记忆，但它本身不能神奇地让一个未连接仓库、未附加项目文件的新对话自动读取它；需要确保新对话可以访问此仓库文件，或把它添加到 ChatGPT 项目文件/项目指令入口。
