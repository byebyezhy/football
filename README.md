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

## 开发与发布约定

- `main` 为审核合并后的主分支。后续功能通过 feature 分支、Pull Request、人工审核合并。
- GitHub Actions 负责检查、构建和发布工件。
- `files.shenqianqian.com` 仅用于存储公开发行文件；不作为预测 API、采集任务或数据库的运行服务器。
- 不向发行服务器上传数据库、凭据、`.env`、密钥或其他私有数据。
- 公开文件发布流程在部署参数确认前不启用。

> 项目状态：V1 架构设计中，尚未部署或进行准确率验证。
