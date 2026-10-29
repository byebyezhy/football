# 数据源插件规范（V1）

## 1. 原则

`soccerdata` 是首批数据源的实现依赖，不是全系统数据格式的唯一拥有者。我们的业务层只依赖内部 `SourceAdapter` 契约及标准化实体。新增网站或 API 时，仅需新增适配器、能力声明、配置、映射和测试。

## 2. 能力驱动的插件

统一定义能力：`results`、`fixtures`、`team_stats`、`xg`、`odds`、`lineups`、`injuries`。不强迫每个插件实现所有能力；不存在的能力必须明确声明，而非返回伪造的空数据。

```python
from dataclasses import dataclass
from typing import Protocol, FrozenSet

@dataclass(frozen=True)
class FetchContext:
    competition_id: str
    season: str
    as_of_utc: str

class SourceAdapter(Protocol):
    name: str
    capabilities: FrozenSet[str]

    def fetch(self, capability: str, ctx: FetchContext):
        """返回统一批次 Envelope；含记录、来源、时间戳与异常摘要。"""
        ...
```

示例目录：`collectors/sources/soccerdata_results.py`、`collectors/sources/understat_xg.py`、`collectors/sources/vendor_api.py`。注册表按名称加载，不让模型代码直接导入第三方爬虫。

## 3. 统一记录 Envelope

每条观测至少保存：

- `source_name`、`source_record_id`、`record_type`、`schema_version`；
- `fetched_at_utc`（本次获取）、`published_at_utc` / `effective_at_utc`（来源能提供时）、`as_of_utc`；
- `competition_external_id`、`home_team_external_id`、`away_team_external_id`；
- 规范化的 UTC 比赛时间和状态、统计字段、单位；
- 原始记录的安全引用或内容哈希、授权/保留策略标记；
- `validation_status`、警告和错误信息。

来源没有公开/生效时间时不能假定数据早已存在；回测应采用保守的 `fetched_at_utc` 约束或排除该特征。原始 ID 不直接作为内部主键。

## 4. 运行规范

1. **幂等**：按来源、外部 ID、数据版本去重；重复执行不生成重复比赛。
2. **限速**：遵守来源条款、robots 和请求限制；对 429/5xx 做有界退避，不绕过访问控制。
3. **缓存**：显式配置 TTL 和强制刷新策略。Soccerdata 自身缓存不能替代我们的更新时间审计。
4. **映射**：统一球队名和联赛 ID；有歧义时进入人工复核队列，不自行猜测。
5. **质量**：监测数据延迟、缺失率、冲突率、任务成功率、最后成功时间。
6. **安全**：API 密钥从运行环境获取；不写入仓库、日志或公开发布包。
7. **合规**：逐来源核实抓取、保存、再分发和商用许可；开源库许可不等于第三方数据授权。

## 5. 初始来源优先级

| 来源 | 初期用途 | 备注 |
| --- | --- | --- |
| Football-Data.co.uk / Soccerdata MatchHistory | 历史结果与部分赔率 | 优先建立可回测基线 |
| FBref / Soccerdata | 球队与赛事统计 | 可用性与授权需持续监测 |
| Understat / Soccerdata | xG | 等结果基线稳定后接入 |
| Club Elo / Soccerdata | 球队实力评级 | 注意免费服务的访问条件和历史时点 |
| 未来商业 API / 自有爬虫 | 赛程、伤停及其他 | 同一契约增加适配器 |

### Football-Data 历史 CSV 编码兼容（2026-10-29）

在实际 VPS 首轮自动同步中，英超 2021–22 赛季因 `KeyError: 'league'` 失败。经核对官方 `/mmz4281/2122/E0.csv` 的真实响应，其开头现在是 UTF-8 BOM 字节 `EF BB BF`；而 Soccerdata 的 MatchHistory 对 2024–25 之前的 CSV 仍使用 Latin-1 解码，因此首列被误读成 `ï»¿Div`，无法映射为 `league`。

`SoccerdataMatchHistory` 对**仅此类 `KeyError('league')`** 提供受限兼容回退：沿用 Soccerdata 的下载/缓存接口，校验预期来源、赛季和 BOM，按 UTF-8（无法解码时 Latin-1）读取官方 CSV 中的 `Div/Date/HomeTeam/AwayTeam/FTHG/FTAG`，继续通过统一赛果校验与数据库幂等写入。其他字段错误或非 BOM 内容不被掩盖。已用真实 2021–22 英超源 CSV 离线解析出 380 场、0 个无效行；**只有用户升级后重新同步，才能确认 VPS 数据库补齐成功**。

## 6. 每次新增插件的验收清单

- 有适配器单测、离线样本、字段字典、能力说明；
- 失败/超时/限速不会破坏其他源的正常采集；
- 映射可重复，冲突有记录，不覆盖原始证据；
- 能在不修改预测模型的前提下启用或停用；
- 数据许可、凭据管理与刷新频率明确。
