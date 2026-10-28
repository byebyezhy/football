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

用内部标准格式的 CSV 离线拟合模型并预测指定球队：

```bash
football predict-csv --csv matches.csv --home Arsenal --away Chelsea --as-of 2025-08-01
```

CSV 列：`competition,season,date,home_team,away_team,home_goals,away_goals`，可选 `source_id`。
当前已有自动执行的离线回测程序，但还没有在线 API 或经过真实足球数据集评估的预测指标。

## 开发与发布约定

- `main` 为审核合并后的主分支。后续功能通过 feature 分支、Pull Request、人工审核合并。
- GitHub Actions 负责检查、构建和发布工件。
- `files.shenqianqian.com` 仅用于存储公开发行文件；不作为预测 API、采集任务或数据库的运行服务器。
- 不向发行服务器上传数据库、凭据、`.env`、密钥或其他私有数据。
- 公开文件发布流程在部署参数确认前不启用。

> 项目状态：V1.0 代码骨架阶段，尚未部署或完成真实数据集上的准确率验证。
