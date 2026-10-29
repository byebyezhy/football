# Football — 足球比分概率预测平台

基于 [penaltyblog](https://github.com/martineastwood/penaltyblog) 与 [soccerdata](https://github.com/probberechts/soccerdata) 的可扩展足球预测项目。

## 项目目标

- 可插拔数据采集：比赛结果、赛程、球队统计、xG 等数据源可持续扩展。
- 统一数据层：匹配球队、联赛和比赛 ID，保留来源、采集时间与质量状态。
- 可替换预测模型：首版使用 Poisson / Dixon–Coles，输出完整比分概率矩阵。
- 严格历史回测：按照时间切分，只使用预测时刻已知的数据，保存预测快照。
- API 与管理后台：逐步展示比赛预测、数据源健康度、模型版本和回测指标。

## V1 设计文档

- [技术架构与阶段验收](docs/ARCHITECTURE_V1.md)
- [数据源插件接口规范](docs/DATA_SOURCES.md)
- [GitHub 与 files 文件服务器发布约定](docs/RELEASES.md)
- [当前实现与下一阶段任务](docs/IMPLEMENTATION_STATUS.md)
- [VPS 部署与域名配置](docs/DEPLOY_VPS.md)

## V0.3 多赛季自动采集与实证回测

- 网站 `https://fb.linmeng.ai`，用户在 Ubuntu 24.04 VPS 自行部署；截至 2026-10-29 已验证一季英超 380 场赛果入库，中文球队展示正常。
- 保留 V0.2 的 FastAPI 比分概率预测、Poisson/Dixon–Coles、PostgreSQL 和 Caddy；新增 `/api/sources`、`/api/backtests` 只读接口及回测网页。
- `worker` 是独立、非 root 的后台容器：启动后补充英超近五个完整赛季与当前赛季，按日检查当前赛季、按月复查历史赛季。失败隔离且不会删除原有比赛。
- 已有球队/比赛主键不变；自动导入与管理员 CLI 共享幂等入库机制，保存采集结果/失败状态供运维查看。
- 以真实历史赛果进行滚动 walk-forward 回测，默认评估最近 48 个有比赛的日期；Poisson 与 Dixon–Coles 报告保存到 PostgreSQL，页面仅读取预先计算的结果，不在公网请求中训练模型。
- 数据库新增两张**仅追加**表：`source_sync_runs`、`model_backtest_reports`。升级保留既有 `match_results`、数据库卷和本地 `.env`。
- 仍无未来赛程、xG、赔率、真实赛前快照，不能把回测指标称为未来比赛命中率保证。

V0.3 首次自动采集和回测需在用户部署后通过 VPS 日志与 `/api/backtests` **实测验收**；发布代码成功不代表后台任务已跑完。详见 [Ubuntu VPS 手工升级与验证](docs/DEPLOY_VPS.md)。

## 代码骨架（V1.0 开发中）

- `src/football_predictor/sources/`：能力注册表和 Soccerdata 历史结果适配器。
- `src/football_predictor/models/`：Penaltyblog Poisson / Dixon–Coles 模型适配器。
- `src/football_predictor/domain.py`：与外部库无关的输入/输出数据契约。
- `tests/`：不依赖外网、模拟第三方接口的离线契约测试。
- `src/football_predictor/backtest.py`：按比赛日期分组、严格使用此前赛果的 walk-forward 回测。

运行离线测试（无需抓取网站或安装模型依赖）：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

安装所需组件（开发机器具备访问软件包源的条件时）：

```bash
python3 -m pip install -e '.[all]'
```

试读英超历史赛果（将访问第三方数据源，遵守其使用条款）：

```bash
football source-preview --league 'ENG-Premier League' --season '2024-25' --as-of 2026-10-28
```

读取并导出历史赛果，再生成逐场回测报告（两个命令都需要先安装可选依赖；第一个命令需要访问数据网站）：

```bash
football fetch-results --league 'ENG-Premier League' --season '2024-25' \
  --as-of 2026-10-28 --output data/raw/epl-2024-25.csv

football backtest-csv --csv data/raw/epl-2024-25.csv \
  --model dixon_coles --min-training 100 --output reports/epl-2024-25.json
```

注意：CSV 写入采用“文件必须不存在”规则，防止误覆盖；回测只隔离同日赛果，赔率、阵容、xG 等外部赛前特征仍需独立的发布时间快照机制。

V0.3 新增管理员命令（不会触发网站部署、不会上传原始数据到 files）：

```bash
football sync-results --league 'ENG-Premier League' --as-of 2026-10-29
football backtest-db --competition 'ENG-Premier League' --as-of 2026-10-29 --evaluation-dates 48
```

正式部署后无需手动运行，Compose 的 `worker` 容器会定期执行。管理员命令只供诊断或主动复算。

用内部标准格式的 CSV 离线拟合模型并预测指定球队：

```bash
football predict-csv --csv matches.csv --home Arsenal --away Chelsea --as-of 2025-08-01
```

CSV 列：`competition,season,date,home_team,away_team,home_goals,away_goals`，可选 `source_id`。
未在真实多赛季数据上完成验收前，不能宣称任何准确率指标。

## 开发与发布约定

- `main` 为合并后的主分支，助手负责 feature PR、CI、合并和 files 发布；不要求用户逐项点击 GitHub。
- GitHub Actions 在 `main` 合并后自动构建唯一版本并发布至 files 的 `test` 渠道，保留手工稳定版提升/回滚入口。
- `files.shenqianqian.com` 仅用于存储公开发行文件；不作为预测 API、采集任务或数据库的运行服务器。
- 不向发行服务器上传数据库、凭据、`.env`、密钥或其他私有数据。
- 发布版本可在 `test` 与 `stable` 渠道间进行经过哈希校验的切换。VPS 由用户亲自 SSH 安装/更新，绝不将 root 私钥交给 GitHub，详见 [发布操作指南](docs/RELEASES.md)。

> 项目状态：V0.3 自动采集与回测代码待 VPS 真实运行验证；网站 V0.2.7 已成功上线并导入 380 场英超比赛。
