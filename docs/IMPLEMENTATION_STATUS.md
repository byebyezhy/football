# V1.0 实现进度

日期：2026-10-28

## 当前 PR 已提供

- Python 包、可安装 CLI 和可扩展的 `SourceRegistry`。
- `SoccerdataMatchHistory`：使用官方 `MatchHistory.read_games()` 获取历史赛果，过滤不完整或未来日期记录，报告无法解析的数据。
- `PenaltyblogModel`：独立包装 Poisson / Dixon-Coles 的训练及比分矩阵输出；按训练截止日期排除未来赛果。
- 离线模拟接口测试、基础 GitHub Actions 运行测试。

## 本 PR 尚未提供

- 对真实外部采集网站的端到端联调（离线 CI 不访问第三方网站）。
- PostgreSQL 数据库、球队映射/跨源冲突处理、原始数据溯源表。
- 完整 `as_of` 数据可见性语义、逐场 walk-forward 回测、模型版本持久化。
- 在线预测 API、后台页面、自动采集调度器。
- GitHub Actions 对 files.shenqianqian.com 的 SSH 发布与服务器实际目录配置。

## 下一 PR 的验收重点

1. 使用单一联赛的授权历史数据进行一次真实数据抓取与持久化，验证列名和球队映射。
2. 完成至少两个赛季的 walk-forward 回测，保持训练数据和预测时间严格隔离。
3. 固定第三方依赖版本并增加集成测试，确保上游 API 变化可被识别。
4. 核验 files 服务端发布目录与密钥作用域，单独提交受控发布 workflow。

> 任何由样例代码生成的比分概率都不应被视为经过回测验证的实战预测。
