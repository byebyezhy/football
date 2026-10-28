# Football V1 技术架构

状态：设计基线（2026-10-28）。本文件规定首版开发边界；不代表服务器已部署或预测精度已得到验证。

## 1. 目标和边界

- 面向赛前比赛，生成各精确比分的概率分布，并由同一分布推导胜/平/负和总进球概率。
- 将采集源、数据标准化、特征、训练、预测、回测、API 分层，做到数据源和模型都可替换。
- 从一个联赛（建议英超）、完整赛季历史数据和离线回测起步，再扩充联赛。
- 初版不做赛中实时模型、不提供保证盈利或准确率承诺、不让 files 服务器执行模型。

## 2. 依赖与边界

| 模块 | 首版方案 | 自有边界 |
| --- | --- | --- |
| 数据采集 | `soccerdata` 作为一组外部来源适配器 | 自有 `SourceAdapter`、调度、质量检查、统一 ID、来源记录 |
| 预测 | `penaltyblog` 的 Poisson / Dixon–Coles | 自有 `ModelAdapter`、训练窗口、特征版本、快照、评估 |
| 数据库 | PostgreSQL | 源记录、标准化实体、事实与快照、预测结果 |
| 服务 | Python + FastAPI（第二阶段启用） | 只读取可信数据，不触发无界同步抓取 |
| 后台任务 | 定时任务/队列（具体实现待定） | 幂等任务、限流、重试、监控 |

优先以依赖方式使用上游库，避免复制其整个代码库；如需改动上游内部，应隔离封装并记录补丁和许可义务。`penaltyblog` 也有采集器，不把其抓取逻辑与 `soccerdata` 直接混杂进业务层。

## 3. 数据流程

1. Adapter 获取原始响应并附加 `source`、外部 ID、`fetched_at`、时间范围、采集状态、授权与缓存元数据。
2. Raw store 保留可审计的原始记录（对敏感/受限制数据按许可和保存策略处理）。
3. Normalizer 将联赛、球队、比赛映射为内部稳定 ID；同一比赛可保留多个来源的观测值。
4. Validator 识别重复、冲突、无效比分、未来时刻、缺失字段、失效数据；有冲突时保留证据，按明确规则选取用于训练的版本。
5. Feature builder 以 `as_of`（预测时刻）生成特征快照，禁止引用该时刻之后发布或采集的数据。
6. Model trainer 按联赛和时间窗口训练，持久化模型工件、配置、代码版本、数据版本和训练截止时间。
7. Predictor 产生完整的比分概率矩阵、派生概率和不可变的赛前预测记录。
8. Evaluator 在比赛完赛后对历史预测打分，并保存各模型版本的样本量及指标。

## 4. 建议的最小数据模型

| 表/实体 | 必要字段（示意） | 说明 |
| --- | --- | --- |
| `competitions` | `id`, `name`, `country`, `season` | 内部赛季与赛事 ID |
| `teams` | `id`, `canonical_name`, `country` | 内部球队 ID |
| `source_entities` | `source`, `entity_type`, `external_id`, `internal_id`, `alias` | 不同来源的球队/赛事映射 |
| `fixtures` | `id`, `competition_id`, `home_team_id`, `away_team_id`, `kickoff_utc`, `status` | 唯一内部比赛 ID |
| `source_observations` | `source`, `fixture_id`, `field`, `value`, `observed_at`, `fetched_at`, `raw_ref` | 字段级可追踪证据；同一字段可多来源 |
| `match_results` | `fixture_id`, `home_goals`, `away_goals`, `is_final`, `provenance_id` | 仅正式结果进入训练标签 |
| `feature_snapshots` | `fixture_id`, `as_of`, `features_json`, `dataset_version` | 防止回测的数据穿越 |
| `model_runs` | `id`, `model_kind`, `params`, `train_cutoff`, `dataset_version`, `code_revision`, `artifact_ref` | 可复现 |
| `predictions` | `id`, `fixture_id`, `model_run_id`, `created_at`, `as_of`, `score_grid`, `home_win`, `draw`, `away_win` | 不可变赛前记录 |
| `evaluation_runs` | `id`, `model_run_id`, `cutoff`, `n_matches`, `metrics_json` | 可比较的离线或在线评估 |

所有时间以 UTC 存储。数据库迁移工具和索引设计在实现阶段补充。训练时不能使用最终结果作为赛前特征，也不能将赛前尚未发布的赔率/阵容作为输入。

## 5. 模型接口与评估

```python
class ModelAdapter:
    def fit(self, matches, *, train_cutoff, config): ...
    def predict(self, fixture, *, as_of): ...  # 返回 ScoreGrid 和元数据
    def save(self, path): ...
    def load(self, path): ...
```

首版至少对比：联赛均值基线、独立 Poisson、Dixon–Coles（含时间衰减）。统一输出从 0:0 到指定最大进球数的概率矩阵，检验非负、有限值和概率归一化，并显式记录截断及归一化策略。

采用 walk-forward 回测：每次只用截止赛前已完成的比赛及当时可用的外部数据训练。保存预测生成时间、预测时点、实际结果、训练样本量和版本。

- 胜平负：multiclass Brier、log loss、RPS、校准曲线；附样本量和分联赛结果。
- 精确比分：Top-1 / Top-3 / Top-5 命中率、实际比分的负对数概率；处理矩阵截断以免把范围外比分当成零概率。
- 与简单基线以及合规获得的市场隐含概率比较；只比较同一批比赛和同一赛前时间截面。

## 6. 分期与验收

**V1.0 数据与离线预测**

- 一个联赛、至少一个可重复运行的结果数据源，具备统一 ID、幂等导入、数据质量报告。
- 基于 `penaltyblog` 的两个模型产生比分矩阵和胜平负概率。
- 严格时间隔离的历史回测，可重复得到一致指标。
- 单元测试覆盖适配器契约、球队映射、重复导入、数据穿越和概率归一化。

**V1.1 自动化和 API**

- 增量抓取、调度/失败重试、数据源健康指标。
- FastAPI 读取预测与回测结果；不在请求中直接进行任意外部抓取。

**V1.2 扩展能力**

- 接入 xG、Elo、赔率等新适配器；启用模型对照/融合前必须通过同一时间切分回测。

验收不以“宣称准确率高”作为标准，而以复现性、完整性、数据时点正确性、可观测性和经验证的指标为准。
