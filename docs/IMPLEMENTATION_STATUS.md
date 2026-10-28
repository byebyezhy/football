# V1.0 实现进度

日期：2026-10-29；包含 release-workflow 分支的变更。

## 当前 PR 已提供

- Python 包、可安装 CLI 和可扩展的 `SourceRegistry`。
- `SoccerdataMatchHistory`：使用官方 `MatchHistory.read_games()` 获取历史赛果，过滤不完整或未来日期记录，报告无法解析的数据。
- `PenaltyblogModel`：独立包装 Poisson / Dixon-Coles 的训练及比分矩阵输出；按训练截止日期排除未来赛果。
- 离线模拟接口测试、基础 GitHub Actions 运行测试。
- `fetch-results`：从 Soccerdata 导出标准化 CSV（不会覆盖已有文件）。
- `backtest-csv`：逐日滚动训练，对每场计算 Brier、RPS、1X2 log loss、比分 Top-1/3/5 和比分 log loss。
- 安装 Soccerdata 2026.43.0 与 Penaltyblog 1.13.1 后，模型真实 API 及合成数据回测的集成测试通过。
- 新增 `build-only` / `publish-new` / `promote-existing` 人工发布流程：带版本与 commit 的源码 tar.gz、SHA256、SSH 安全传输、HTTPS 完整校验、渠道原子更新与旧版回滚。文件服务器权限及公网映射仍待线上验收。

## 本 PR 尚未提供

- 对真实外部采集网站的端到端联调：当前执行环境访问 Football-Data.co.uk 出现 DNS 超时；未获取真实比赛数据，不能报告实测预测准确率。
- PostgreSQL 数据库、球队映射/跨源冲突处理、原始数据溯源表。
- 完整 `as_of` 数据可见性语义（尤其赔率和 xG 的发布时间快照）及模型版本持久化；当前 walk-forward 只确保不同比赛日期的赛果不会泄漏。
- 在线预测 API、后台页面、自动采集调度器。
- 文件服务器 SSH 部署账号/密钥、GitHub Environment 审批与 HTTPS 目录映射的实际配置（发布代码已实现，但尚未实际连通）。

## 下一 PR 的验收重点

1. 使用单一联赛的授权历史数据进行一次真实数据抓取与持久化，验证列名和球队映射。
2. 使用至少两个赛季的真实结果运行已实现的 walk-forward，核验时间隔离并输出第一份可复现基线报告。
3. 固定第三方依赖版本并增加集成测试，确保上游 API 变化可被识别。
4. 配置 `football-files` GitHub Environment、校验 SSH 主机指纹和 Nginx 映射，然后先运行 `build-only`，再做一次 `test` 渠道实际上传验收。

> 任何由样例代码生成的比分概率都不应被视为经过回测验证的实战预测。
