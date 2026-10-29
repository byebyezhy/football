# V0.2 实现进度

> **注意：以下 V0.2 历史记录并非当前实时状态。** 截至 2026-10-29，用户已在 VPS 成功部署 V0.2.7、导入真实英超 2024–25 赛季 380 场比赛，并确认中文队名显示正常。新开发目标是 **V0.3 后台自动多赛季采集 + 真实历史回测面板**。以仓库根目录的 `AGENTS.md`、本文件上方最新附注、GitHub Actions 和 files `test.json` 为准。

## V0.3 本轮新增（需在 VPS 真正运行后验收）

- 新增非 root `worker` Compose 后台容器：动态计算近五个完整赛季及当前赛季的英超赛季代码，成功同步按当前季 1 天、历史季 30 天间隔复查。
- 增量结果直接进入原有 PostgreSQL `match_results`，不覆盖已有赛果；新增来源运行记录表 `source_sync_runs` 与回测概要表 `model_backtest_reports`。
- 新增 `football sync-results`、`football backtest-db`，基于真实已入库赛果进行日期分组 walk-forward 回测；默认评估最近 48 个有比赛的日期。
- 公网新增只读 `/api/sources` 与 `/api/backtests`，网页展示 Poisson / Dixon–Coles 历史指标；回测计算不在 HTTP 请求线程中运行。
- 本轮代码与自动化单测不能代替 VPS 上真实源采集、后台性能和回测结果验证；若抓取失败，保留旧比赛和回测空状态。

---

日期：2026-10-29；包含 web-vps-foundation 分支的变更。

## 当前 PR 已提供

- Python 包、可安装 CLI 和可扩展的 `SourceRegistry`。
- `SoccerdataMatchHistory`：使用官方 `MatchHistory.read_games()` 获取历史赛果，过滤不完整或未来日期记录，报告无法解析的数据。
- `PenaltyblogModel`：独立包装 Poisson / Dixon-Coles 的训练及比分矩阵输出；按训练截止日期排除未来赛果。
- 离线模拟接口测试、基础 GitHub Actions 运行测试。
- `fetch-results`：从 Soccerdata 导出标准化 CSV（不会覆盖已有文件）。
- `backtest-csv`：逐日滚动训练，对每场计算 Brier、RPS、1X2 log loss、比分 Top-1/3/5 和比分 log loss。
- 安装 Soccerdata 2026.43.0 与 Penaltyblog 1.13.1 后，模型真实 API 及合成数据回测的集成测试通过。
- 新增 `build-only` / `publish-new` / `promote-existing` 人工发布流程：带版本与 commit 的源码 tar.gz、SHA256、SSH 安全传输、HTTPS 完整校验、渠道原子更新与旧版回滚。文件服务器权限及公网映射仍待线上验收。
- V0.2 Web MVP：FastAPI、静态首页、可按联赛/球队/日期进行 Poisson/Dixon–Coles 预测的 API、PostgreSQL 幂等赛果导入、Docker Compose + Caddy、公开版本包部署指南。新网站还未在 VPS 上部署。

## 本 PR 尚未提供

- 对真实外部采集网站的端到端联调：当前执行环境访问 Football-Data.co.uk 出现 DNS 超时；未获取真实比赛数据，不能报告实测预测准确率。
- 生产数据库 Schema 迁移工具、球队跨源映射/冲突处理、原始数据溯源表（当前仅有最小 PostgreSQL 赛果表与来源字段）。
- 完整 `as_of` 数据可见性语义（尤其赔率和 xG 的发布时间快照）及模型版本持久化；当前 walk-forward 只确保不同比赛日期的赛果不会泄漏。
- 自动采集调度器、真实赛程、账户后台、请求限流、模型离线快照及多联赛实证报告；V0.2 仅提供手动历史数据导入和初版公开 API。
- 文件服务器 GitHub Actions 发布、VPS 上的 `https://fb.linmeng.ai` 真实联调仍待验收；服务器端凭据由操作者自行保管。

## 下一 PR 的验收重点

1. 使用单一联赛的授权历史数据进行一次真实数据抓取与持久化，验证列名和球队映射。
2. 使用至少两个赛季的真实结果运行已实现的 walk-forward，核验时间隔离并输出第一份可复现基线报告。
3. 固定第三方依赖版本并增加集成测试，确保上游 API 变化可被识别。
4. GitHub `build-only` → 文件服务器 `publish-new` → VPS 按 SHA256 下载/构建 → `fb.linmeng.ai` HTTPS 验收。

> 任何由样例代码生成的比分概率都不应被视为经过回测验证的实战预测。
