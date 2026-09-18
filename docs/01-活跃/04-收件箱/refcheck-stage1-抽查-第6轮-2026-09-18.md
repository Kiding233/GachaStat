<!-- refcheck:generated：本文件由 refcheck 产出，扫描时按标记自动剔除。-->

# refcheck 人工抽查清单

- 配置：`D:\Users\DELL\Desktop\gacha_simulator\抽卡模拟与分析程序\tools\refcheck\refcheck.toml`
- 语料指纹：HEAD `76fc1bbee5db48c2e63059c027a84198234d97e3`，414 个文件，去重后 269 条引用
- 种子 `20260918`，样本 24 条
- 已剔除本工具自产清单 5 个：`docs/01-活跃/04-收件箱/refcheck-stage1-抽查-2026-09-18.md`、`docs/01-活跃/04-收件箱/refcheck-stage1-抽查-第2轮-2026-09-18.md`、`docs/01-活跃/04-收件箱/refcheck-stage1-抽查-第3轮-2026-09-18.md`、`docs/01-活跃/04-收件箱/refcheck-stage1-抽查-第4轮-2026-09-18.md`、`docs/01-活跃/04-收件箱/refcheck-stage1-抽查-第5轮-2026-09-18.md`
- 判定口径：解析到的目标与范围**是否就是文中所指的那一处**
- 命令：`python tools/refcheck/refcheck.py sample --n 24 --seed 20260918`

| # | 位置 | 上下文 | 原文 | 解析到 | 所属符号/章节 | 目标侧疑点 | 判定 |
|---|---|---|---|---|---|---|---|
| 1 | `docs/01-活跃/04-收件箱/quality-2026-08-03.md:94` | prose/plain | `plotly_charts.py:695` | `gacha_simulator/visualization/plotly_charts.py` | - | - | |
| 2 | `docs/01-活跃/panels/方案搜索/P26 退路搜索与资源目标搜索理论改进计划.md:491` | prose/plain | `retreat_search.py:164` | `gacha_simulator/core/retreat_search.py` | PlanSearchEngine._check_gdr_compatibility | - | |
| 3 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:110` | prose/plain | `distribution.py:273` | `gacha_simulator/core/distribution.py` | - | - | |
| 4 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:340` | prose/plain | `gdr.py:439` | `gacha_simulator/core/gdr.py` | 模块级 | 队列：文中点名 `_gdr_resource_consumed`，它不覆盖目标行（它在 202-205）（建议 202-205） | |
| 5 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:342` | prose/plain | `gdr.py:869` | `gacha_simulator/core/gdr.py` | - | - | |
| 6 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:347` | prose/plain | `risk_analysis.py:15` | `.recycle_bin/2026-09-17-p81-archived-risk-analysis/risk_analysis.py` | RiskAnalyzer.resource_remaining_distribution | - | |
| 7 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:583` | prose/plain | `resource_search_panel.py:73` | `.recycle_bin/2026-09-17-p81-archived-panels/resource_search_panel.py` | ResourceSearchWorker._extract_cost_per_draw | - | |
| 8 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:791` | prose/plain | `plan_search_panel.py:698` | `gacha_simulator/gui/plan_search_panel.py` | PlanSearchPanel._setup_params_group | - | |
| 9 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:797` | prose/plain | `resource_search_panel.py:322` | `.recycle_bin/2026-09-17-p81-archived-panels/resource_search_panel.py` | ResourceSearchPanel._setup_ui | - | |
| 10 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:798` | prose/plain | `retreat_search_panel.py:346` | `.recycle_bin/2026-09-17-p81-archived-panels/retreat_search_panel.py` | RetreatSearchPanel._setup_ui | - | |
| 11 | `docs/01-活跃/subsystems/保底系统/03-审计.md:20` | prose/plain | `pity.py:200-203` | `gacha_simulator/core/pity.py` | CounterBasedBehavior._should_reset | - | |
| 12 | `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:67` | md-link/link | `](docs/主流抽卡游戏卡池机制配置转换手册.md#L2305)` | `docs/主流抽卡游戏卡池机制配置转换手册.md` | - | - | |
| 13 | `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:428` | md-link/link | `](gacha_simulator/core/pity.py#L714)` | `gacha_simulator/core/pity.py` | 模块级 | - | |
| 14 | `docs/01-活跃/subsystems/应用打包/P73 scipy依赖替换-混合策略与golden等价对照.md:90` | md-link/link | `](gacha_simulator/core/bootstrap.py#L57)` | `gacha_simulator/core/bootstrap.py` | BootstrapEngine._percentile_ci | - | |
| 15 | `docs/01-活跃/subsystems/性能分析/00-档案.md:17` | prose/plain | `multiprocessing/pool.py:861` | `未解析(配置声明为外部)` | - | - | |
| 16 | `docs/01-活跃/subsystems/性能分析/01-理论.md:132` | prose/plain | `multiprocessing/pool.py:861` | `未解析(配置声明为外部)` | - | - | |
| 17 | `docs/01-活跃/subsystems/性能分析/04-问题.md:25` | prose/plain | `scripts/profile_simulation.py:55` | `scripts/profile_simulation.py` | 模块级 | - | |
| 18 | `docs/01-活跃/subsystems/性能分析/04-问题.md:26` | prose/plain | `profile_simulation.py:92` | `scripts/profile_simulation.py` | 模块级 | - | |
| 19 | `docs/01-活跃/subsystems/性能分析/05-笔记.md:33` | prose/plain | `profile_sim.py:116` | `scripts/profile_sim.py` | 模块级 | - | |
| 20 | `docs/01-活跃/subsystems/性能分析/05-笔记.md:183` | prose/plain | `core/gdr.py:825` | `gacha_simulator/core/gdr.py` | - | - | |
| 21 | `docs/01-活跃/subsystems/性能分析/P83 性能分析平台——多路径测量·基线回归·现场剖析.md:19` | prose/plain | `scripts/profile_sim.py:51` | `scripts/profile_sim.py` | main | - | |
| 22 | `docs/01-活跃/subsystems/性能分析/P83 性能分析平台——多路径测量·基线回归·现场剖析.md:25` | prose/plain | `multiprocessing/pool.py:861` | `未解析(配置声明为外部)` | - | - | |
| 23 | `docs/02-待办/Ps04 资源定义自动生成按钮改造——从覆盖陷阱到汇总扫描.md:152` | prose/plain | `_version.py:13` | `gacha_simulator/_version.py` | 模块级 | - | |
| 24 | `docs/05-参考资料/外部研究/外部研究报告对项目启发分析.md:41` | md-link/link | `](gacha_simulator/core/strategy.py#L23)` | `gacha_simulator/core/strategy.py` | 模块级 | 门控：模块级单行锚点落在注释上（指纹永不变化）；队列：文中点名 `future_schedules`，它不覆盖目标行（它在 99-99）（建议 99-99） | |

统计：{'line_out_of_range': 4, 'ok': 5, 'module_level': 4, 'out_of_scope': 4, 'external': 3, 'untracked': 4}
带门控疑点的样本：1 / 24
命中复核队列的样本：2 / 24

---

## 逐条上下游对照

### 1. `docs/01-活跃/04-收件箱/quality-2026-08-03.md:94`

- 原文：`plotly_charts.py:695`（prose / plain / line_out_of_range）
- 解析到：`gacha_simulator/visualization/plotly_charts.py`

**引用所在处（箭头为引用行）**

```
     92 | 复合策略是插件 building block，文档描述的「跳过无操作等待」语义与实现背离，插件开发者按 docstring 理解会踩坑。**建议**：按真实语义改写 docstring（实现无错，文档有错）。
     93 | 
>>   94 | ### 🟡 [低] `plotly_charts.py:695` 过时注释
     95 | 
     96 | `fixedrange=False` 已允许垂直拖动，但注释仍写「限制垂直拖动：y 轴固定范围，仅允许横向平移」。本周 `fixedrange` 改动（7dc45a9）引入后未同步注释。
```

**被引目标**：`gacha_simulator/visualization/plotly_charts.py` 共 567 行，引用写的是 `plotly_charts.py:695`，对不上，故无对应内容。文件末尾如下（line_out_of_range）：

```
    560 | def encode_heatmap_binary(matrix: np.ndarray) -> str:
    561 |     """将大矩阵编码为 base64 二进制字符串，减少 HTML 嵌入体积。
    562 | 
    563 |     10,000×20 float64 矩阵：JSON ~3.2MB → base64 binary ~1.6MB。
    564 |     JS 侧解码: new Float64Array(Uint8Array.from(atob(data), ...).buffer)
    565 |     """
    566 |     buffer = matrix.astype(np.float64).tobytes()
    567 |     return base64.b64encode(buffer).decode("ascii")
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 2. `docs/01-活跃/panels/方案搜索/P26 退路搜索与资源目标搜索理论改进计划.md:491`

- 原文：`retreat_search.py:164`（prose / plain / ok）
- 解析到：`gacha_simulator/core/retreat_search.py`，所属 `PlanSearchEngine._check_gdr_compatibility` [153, 191]
- 目标指纹：`ast-v1:d58b07784a94ea7d`
- 引用所在章节（源文档）：`Q14: `seed=0` 硬编码 ⚔ 低等` [487, 496]
- 所在章节：`Q14: `seed=0` 硬编码 ⚔ 低等` [487, 496]

**引用所在处（箭头为引用行）**

```
    489 | **原始编号**：N2
    490 | 
>>  491 | **现状**（`retreat_search.py:164`——已修复，2026-06-10）：
    492 | - 原代码 `seed=0` 使不同 `resource_value` 的调用使用相同随机种子
    493 | - CRN（Common Random Numbers）是合法方差缩减技术，但本系统未声明其使用
```

**被引行号处的内容**（引用写的是 164-164，箭头为起始行）

```
    161 | 
    162 |         Returns:
    163 |             True 如果兼容（可以继续搜索），False 如果已设置 result 失败原因。
>>  164 |         """
    165 |         from gacha_simulator.core.gdr import resolve_gdr_definition
    166 |         gdr_def = resolve_gdr_definition(self.gdr_key)
    167 | 
```

所属符号：`PlanSearchEngine._check_gdr_compatibility` [153, 191]，指纹 `ast-v1:d58b07784a94ea7d`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 3. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:110`

- 原文：`distribution.py:273`（prose / plain / line_out_of_range）
- 解析到：`gacha_simulator/core/distribution.py`

**引用所在处（箭头为引用行）**

```
    108 | |------|------|-----------|
    109 | | `risk_analysis.py:15` | `resource_remaining_distribution()` | `resource: str = 'draw_resource'` ——已有参数，需确认调用方传参 |
>>  110 | | `distribution.py:273` | `from_resource_remaining()` | `resource: str = 'draw_resource'` ——同上 |
    111 | 
    112 | ### 2.2 分析面板（`gui/analysis_panel.py`）
```

**被引目标**：`gacha_simulator/core/distribution.py` 共 191 行，引用写的是 `distribution.py:273`，对不上，故无对应内容。文件末尾如下（line_out_of_range）：

```
    184 |     q75, q25 = np.percentile(data, [75, 25])
    185 |     iqr = q75 - q25
    186 |     if iqr == 0:
    187 |         return int(np.ceil(np.log2(n) + 1))
    188 |     bin_width = 2.0 * iqr / (n ** (1.0 / 3.0))
    189 |     data_range = max(data) - min(data)
    190 |     n_bins = int(np.ceil(data_range / bin_width)) if bin_width > 0 else 1
    191 |     return max(min_bins, min(max_bins, n_bins))
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 4. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:340`

- 原文：`gdr.py:439`（prose / plain / module_level）
- 解析到：`gacha_simulator/core/gdr.py`
- 目标指纹：`line-v1:a295ec79700aeef2`
- 本行点名且在目标文件内有定义的符号：['_gdr_resource_consumed']
- 引用所在章节（源文档）：`A 类：compute 函数——统一在 `**kw` 中接收 `resource_id`，默认 `'draw_resource'`（15 处：11 改动 + 2 worst_impact 适配 + 2 调用方确认）` [330, 351]
- 复核队列：文中点名 `_gdr_resource_consumed`，它不覆盖目标行（它在 202-205），建议锚点 `202-205`
- 所在章节：`A 类：compute 函数——统一在 `**kw` 中接收 `resource_id`，默认 `'draw_resource'`（15 处：11 改动 + 2 worst_impact 适配 + 2 调用方确认）` [330, 351]

**引用所在处（箭头为引用行）**

```
    338 | | 5 | `_gdr_resource_efficiency()` | `gdr.py:357` | 同上 |
    339 | | 6 | `_gdr_resource_per_card()` | `gdr.py:427` | 同上（obtained≤0 返回 `nan`） |
>>  340 | | 7 | `_gdr_resource_consumed()` | `gdr.py:439` | 同上 |
    341 | | 8 | `_gdr_draw_conversion_efficiency()` | `gdr.py:449` | **不展开**，保持硬编码 |
    342 | | 9 | `compute_gdr_from_cumulative()` | `gdr.py:869`（def）/ `879`（硬编码行） | `'draw_resource'` → `resource_id`（需在函数开头调用 `parse_gdr_key(gdr_key)` 获取 `resource_id`） |
```

**被引行号处的内容**（引用写的是 439-439，箭头为起始行）

```
    436 |         key='per_pool_draw_rate',
    437 |         display_name='每池下池出卡率',
    438 |         default_threshold=0.0,
>>  439 |         compute_from_compact=_gdr_per_pool_draw_rate,
    440 |     ),
    441 |     'weapon_character_ratio': GDRDefinition(
    442 |         key='weapon_character_ratio',
```

文中点名符号的实际位置（建议锚点 `202-205`）：

```
    200 | 
    201 | 
>>  202 | def _gdr_resource_consumed(compact, target_specs, **kw):
    203 |     """总资源消耗。越低越好。"""
    204 |     resource_id = kw.get('resource_id', 'draw_resource')
    205 |     return compact.get('total_consumed', {}).get(resource_id, 0)
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 5. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:342`

- 原文：`gdr.py:869`（prose / plain / line_out_of_range）
- 解析到：`gacha_simulator/core/gdr.py`

**引用所在处（箭头为引用行）**

```
    340 | | 7 | `_gdr_resource_consumed()` | `gdr.py:439` | 同上 |
    341 | | 8 | `_gdr_draw_conversion_efficiency()` | `gdr.py:449` | **不展开**，保持硬编码 |
>>  342 | | 9 | `compute_gdr_from_cumulative()` | `gdr.py:869`（def）/ `879`（硬编码行） | `'draw_resource'` → `resource_id`（需在函数开头调用 `parse_gdr_key(gdr_key)` 获取 `resource_id`） |
    343 | | 10 | `compute_vulnerability_analysis()` | `vulnerability.py:224` | `resource_key='draw_resource'` → `resource_id` |
    344 | | 11 | `plot_vulnerability_ridge()` | `vulnerability.py:613` | `.get('draw_resource')` → `.get(resource_id)` |
```

**被引目标**：`gacha_simulator/core/gdr.py` 共 813 行，引用写的是 `gdr.py:869`，对不上，故无对应内容。文件末尾如下（line_out_of_range）：

```
    806 |     }
    807 |     return compute_gdr_from_compact(
    808 |         pseudo_compact, target_specs, gdr_key,
    809 |         desire_weights, miss_cost_weights, card_value_weights,
    810 |         ssr_ids, weapon_character_map,
    811 |         store=store,
    812 |         **gdr_kwargs,
    813 |     )
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 6. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:347`

- 原文：`risk_analysis.py:15`（prose / plain / out_of_scope）
- 解析到：`.recycle_bin/2026-09-17-p81-archived-risk-analysis/risk_analysis.py`，所属 `RiskAnalyzer.resource_remaining_distribution` [15, 17]
- 目标指纹：`ast-v1:9aa4d5b85ec9ecde`
- 本行点名且在目标文件内有定义的符号：['resource_remaining_distribution']
- 引用所在章节（源文档）：`A 类：compute 函数——统一在 `**kw` 中接收 `resource_id`，默认 `'draw_resource'`（15 处：11 改动 + 2 worst_impact 适配 + 2 调用方确认）` [330, 351]
- 所在章节：`A 类：compute 函数——统一在 `**kw` 中接收 `resource_id`，默认 `'draw_resource'`（15 处：11 改动 + 2 worst_impact 适配 + 2 调用方确认）` [330, 351]

**引用所在处（箭头为引用行）**

```
    345 | | 12 | `WorstImpactCalculator._prepare_pool_info()` | `worst_impact.py:366` | `self._resource_name = ... 'draw_resource'` 回退值 → 优先从 `parse_gdr_key(self.gdr_key)[1]` 取值 |
    346 | | 13 | `WorstImpactCalculator.analyze()` EVT 跳过 | `worst_impact.py:150-152` | `self.gdr_key in ('resource_remaining', ...)` → `is_resource_gdr(self.gdr_key)` ——`:qualified` key 不在此硬编码元组中 |
>>  347 | | 14 | `resource_remaining_distribution()` | `risk_analysis.py:15` | 已有 `resource` 参数默认 `'draw_resource'`——函数体无需改，需确认调用方传入正确 `resource_id` |
    348 | | 15 | `from_resource_remaining()` | `distribution.py:273` | 已有 `resource` 参数默认 `'draw_resource'`——同上 |
    349 | 
```

**被引行号处的内容**（引用写的是 15-15，箭头为起始行）

```
     12 |         values = [gdr_func(h, self.ctx, **kwargs) for h in self.histories]
     13 |         return EmpiricalDistribution(values)
     14 | 
>>   15 |     def resource_remaining_distribution(self, resource: str = 'draw_resource') -> EmpiricalDistribution:
     16 |         values = [resource_remaining(h, self.ctx, resource) for h in self.histories]
     17 |         return EmpiricalDistribution(values)
     18 | 
```

所属符号：`RiskAnalyzer.resource_remaining_distribution` [15, 17]，指纹 `ast-v1:9aa4d5b85ec9ecde`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 7. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:583`

- 原文：`resource_search_panel.py:73`（prose / plain / out_of_scope）
- 解析到：`.recycle_bin/2026-09-17-p81-archived-panels/resource_search_panel.py`，所属 `ResourceSearchWorker._extract_cost_per_draw` [72, 86]
- 目标指纹：`ast-v1:9f4257ef4b57a92e`
- 本行点名且在目标文件内有定义的符号：['_extract_cost_per_draw']
- 引用所在章节（源文档）：`3.3.2 `_extract_cost_per_draw` 重复实现归并` [576, 592]
- 所在章节：`3.3.2 `_extract_cost_per_draw` 重复实现归并` [576, 592]

**引用所在处（箭头为引用行）**

```
    581 | |---|------|---------|------|
    582 | | 1 | `analysis_panel.py:1384` | `_extract_cost_per_draw(self)` | 返回 `float`，取第一个 `:` 分隔值 |
>>  583 | | 2 | ~~`resource_search_panel.py:73`~~ | ~~`_extract_cost_per_draw(pools)` 静态方法~~ | **已作废**（文件已归档，P81 C1） |
    584 | | 3 | ~~`resource_search_panel.py:87`~~ | ~~`_extract_cost_per_draw_from_entries(pool_entries)` 静态方法~~ | **已作废**（文件已归档，P81 C1） |
    585 | | 4 | `retreat_panel.py:249` | `_extract_cost_per_draw(self)` | 返回 `float`，与 #1 几乎相同 |
```

**被引行号处的内容**（引用写的是 73-73，箭头为起始行）

```
     70 | 
     71 |     @staticmethod
     72 |     def _extract_cost_per_draw(pools):
>>   73 |         if not pools:
     74 |             return 160
     75 |         for p in pools:
     76 |             # P61（Ph6 / AUDIT-BREAK-5 ③）：env.pools 承载 List[Banner]，读 banner.active_pool.cost
```

所属符号：`ResourceSearchWorker._extract_cost_per_draw` [72, 86]，指纹 `ast-v1:9f4257ef4b57a92e`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 8. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:791`

- 原文：`plan_search_panel.py:698`（prose / plain / ok）
- 解析到：`gacha_simulator/gui/plan_search_panel.py`，所属 `PlanSearchPanel._setup_params_group` [668, 751]
- 目标指纹：`ast-v1:cf22e286509a8ad5`
- 引用所在章节（源文档）：`阶段 2：`populate_gdr_combo()` 适配 + 分析面板（手动验收）` [781, 858]
- 所在章节：`阶段 2：`populate_gdr_combo()` 适配 + 分析面板（手动验收）` [781, 858]

**引用所在处（箭头为引用行）**

```
    789 |   | 调用方 | 文件 | 动作 |
    790 |   |--------|------|------|
>>  791 |   | 方案搜索 GDR 下拉 | `plan_search_panel.py:698` | 传 `resource_defs` |
    792 |   | 过程分析 GDR 下拉 | `process_analysis_panel.py:92` | 传 `resource_defs` |
    793 |   | 过程分析 条件 GDR 下拉 | `process_analysis_panel.py:226` | 传 `resource_defs` |
```

**被引行号处的内容**（引用写的是 698-698，箭头为起始行）

```
    695 |         self._gdr_hint_label.setStyleSheet("color: #c0392b; font-size: 11px; padding: 2px 0;")
    696 |         self._gdr_hint_label.setWordWrap(True)
    697 |         self._gdr_hint_label.setVisible(False)
>>  698 |         form.addRow("", self._gdr_hint_label)
    699 | 
    700 |         self.success_threshold_spin = QDoubleSpinBox()
    701 |         self.success_threshold_spin.setRange(0.0, 1.0)
```

所属符号：`PlanSearchPanel._setup_params_group` [668, 751]，指纹 `ast-v1:cf22e286509a8ad5`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 9. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:797`

- 原文：`resource_search_panel.py:322`（prose / plain / out_of_scope）
- 解析到：`.recycle_bin/2026-09-17-p81-archived-panels/resource_search_panel.py`，所属 `ResourceSearchPanel._setup_ui` [304, 480]
- 目标指纹：`ast-v1:8f8632417caef5d1`
- 引用所在章节（源文档）：`阶段 2：`populate_gdr_combo()` 适配 + 分析面板（手动验收）` [781, 858]
- 所在章节：`阶段 2：`populate_gdr_combo()` 适配 + 分析面板（手动验收）` [781, 858]

**引用所在处（箭头为引用行）**

```
    795 |   | 策略比较 GDR 下拉 | ~~`strategy_panel.py:386`~~ | **已作废**（文件已归档，P81 C1） |
    796 |   | 脆弱性分析 GDR 下拉 | `retreat_panel.py:150` | 传 `resource_defs` |
>>  797 |   | 资源搜索 GDR 下拉 | `resource_search_panel.py:322` | 已弃用（P8），跳过 |
    798 |   | 退路搜索 GDR 下拉 | `retreat_search_panel.py:346` | 已弃用（P8），跳过 |
    799 |   | `analysis_panel.py` | — | 不调用 `populate_gdr_combo`——走 `_gdr_names` 数据源切换（S2.2） |
```

**被引行号处的内容**（引用写的是 322-322，箭头为起始行）

```
    319 |         left_layout.addWidget(target_group)
    320 | 
    321 |         params_group = QGroupBox("搜索参数")
>>  322 |         params_layout = QFormLayout(params_group)
    323 | 
    324 |         self.strategy_label = QLabel("--")
    325 |         self.strategy_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
```

所属符号：`ResourceSearchPanel._setup_ui` [304, 480]，指纹 `ast-v1:8f8632417caef5d1`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 10. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:798`

- 原文：`retreat_search_panel.py:346`（prose / plain / out_of_scope）
- 解析到：`.recycle_bin/2026-09-17-p81-archived-panels/retreat_search_panel.py`，所属 `RetreatSearchPanel._setup_ui` [245, 417]
- 目标指纹：`ast-v1:9d638961b533ebff`
- 引用所在章节（源文档）：`阶段 2：`populate_gdr_combo()` 适配 + 分析面板（手动验收）` [781, 858]
- 所在章节：`阶段 2：`populate_gdr_combo()` 适配 + 分析面板（手动验收）` [781, 858]

**引用所在处（箭头为引用行）**

```
    796 |   | 脆弱性分析 GDR 下拉 | `retreat_panel.py:150` | 传 `resource_defs` |
    797 |   | 资源搜索 GDR 下拉 | `resource_search_panel.py:322` | 已弃用（P8），跳过 |
>>  798 |   | 退路搜索 GDR 下拉 | `retreat_search_panel.py:346` | 已弃用（P8），跳过 |
    799 |   | `analysis_panel.py` | — | 不调用 `populate_gdr_combo`——走 `_gdr_names` 数据源切换（S2.2） |
    800 | 
```

**被引行号处的内容**（引用写的是 346-346，箭头为起始行）

```
    343 |         self.gdr_combo = QComboBox()
    344 |         self.gdr_combo.setMaxVisibleItems(30)
    345 |         populate_gdr_combo(self.gdr_combo)
>>  346 |         self.gdr_combo.setCurrentIndex(1)
    347 |         search_form.addRow("GDR指标:", self.gdr_combo)
    348 | 
    349 |         self.gdr_threshold_spin = QDoubleSpinBox()
```

所属符号：`RetreatSearchPanel._setup_ui` [245, 417]，指纹 `ast-v1:9d638961b533ebff`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 11. `docs/01-活跃/subsystems/保底系统/03-审计.md:20`

- 原文：`pity.py:200-203`（prose / plain / ok）
- 解析到：`gacha_simulator/core/pity.py`，所属 `CounterBasedBehavior._should_reset` [200, 203]
- 目标指纹：`ast-v1:3eef0e89c04236f2`
- 引用所在章节（源文档）：`已发现的异常（非待审计，已确认）` [11, 23]
- 所在章节：`已发现的异常（非待审计，已确认）` [11, 23]

**引用所在处（箭头为引用行）**

```
     18 | | 4 | **`did_fire` 三类语义不一致**（**已修复 2026-09-16**）：统一为「本次抽卡是否让本保底回到初始状态」。rotating / targeted 补上 scope 门控，counter 驱动型不变（`_should_reset` 本就是该语义）。修复前：抽到非 scope 稀有度的 UP 时 rotating 的 `did_fire` 为真而状态未翻转，`depends_on` 依赖方被提前激活 | `pity.py:500-504` / `:699-701`（`RotatingCRBehavior` 的冗余覆写已删除）；唯一调用点 `pity.py:1340` | ✅ 已处置 |
     19 | | 5 | **`PityDef.scope` 合法但无对应卡时的静默失效**（2026-09-16 发现，已实测）：scope 白名单校验只保证 scope 在 `[rarities].ranks` 内；若该稀有度没有任何卡进入池子，`scope_slots` 里就没有该键，各类型在 `scope_slots` 为空或 `scope` 总概率为 0 时早退，概率修正恒不生效且无任何提示。实测：`scope='ur'`（ranks 内、池中无 ur 卡）连跑 7 抽，概率栈与基础分布逐抽相同，同时该保底的 `counter` 无重置地累加到 7 | `pity.py:278`（soft）/ `:373`（hard）/ `:467`（rotating）/ `:646`（targeted） | 待裁决（是否在配置加载期交叉校验「scope 有卡」） |
>>   20 | | 6 | **`reset` 取值无白名单，未知值静默永不重置**（2026-09-16 发现，2026-09-18 更新触达路径）：`create_behavior` 仅在 `pdef.reset` 为 truthy 时透传（空串回退 `scope`），非空值则由 `_should_reset` 做 `reward_rarity == reset` 比较，故任何既非 `'featured'` 又不等于稀有度名的值（如 legacy 值 `'featured_ssr'`）恒 False。实测：`hard(reset='featured_ssr')` 连出 3 次 featured SSR 后 counter 仍为 3（`reset='featured'` 时为 0）。**原触达路径已消失**：`_migrate_legacy_pity`（旧 TOML 自动迁移）与 `tests/test_config_toml.py` 中守护该值的 `TestMigrateLegacyPity`/`test_reset_preserved` 均随 P81 B11 删除，旧格式现由 `_check_pity_format()` 显式抛 `ConfigError` 拒绝 | `pity.py:200-203`、`:879-880`；`config_toml.py:687`、`:385-421` | 待裁决（补 `_should_reset` 分支，或加 `reset` 取值白名单。注意不能直接映射到 `'featured'`：后者是「出任意稀有度 featured」，语义更宽） |
     21 | 
     22 | 异常 2/3 修复前的现状断言曾固化在 `tests/core/test_pity_validate_behaviors.py`，修复后 `TestScopeNotWired` 改为 `TestScopeWired`（三项正向断言）、重名用例改为断言抛错。
```

**被引行号处的内容**（引用写的是 200-203，箭头为起始行）

```
    197 |         # ── 默认重置流程 ──
    198 |         self._counter().reset()
    199 | 
>>  200 |     def _should_reset(self, ctx: 'PityContext') -> bool:
    201 |         if self._reset == "featured":
    202 |             return ctx.draw.is_featured
    203 |         return ctx.draw.reward_rarity == self._reset
    204 | 
    205 |     def did_fire(self, ctx: 'PityContext') -> bool:
    206 |         return self._should_reset(ctx)
```

所属符号：`CounterBasedBehavior._should_reset` [200, 203]，指纹 `ast-v1:3eef0e89c04236f2`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 12. `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:67`

- 原文：`](docs/主流抽卡游戏卡池机制配置转换手册.md#L2305)`（md-link / link / ok）
- 解析到：`docs/主流抽卡游戏卡池机制配置转换手册.md`
- 引用所在章节（源文档）：`1.3 保底相关缺口完整盘点（2026-08-24 逐条核实，双信源纪律）` [59, 72]
- 被引侧章节指纹：`sec-v1:4e6815a6515433f6`（`17.7 不确定项` [2299, 2307]）
- 所在章节：`1.3 保底相关缺口完整盘点（2026-08-24 逐条核实，双信源纪律）` [59, 72]

**引用所在处（箭头为引用行）**

```
     65 | | G13 战双新手首次 40 | `hard.threshold` 首次特殊值（[手册:2304](docs/主流抽卡游戏卡池机制配置转换手册.md#L2304)，40 vs 60） | 🟢 配置即可（2026-08-24 双信源确认：[caoteng951](https://www.caoteng951.cn/tengzx01/4662.html) + [9game](https://www.9game.cn/zspms/4456638.html)）：`hard(threshold=60, counter_init=20)`，首次 40 触发、归零后续 60 |
     66 | | G2 阴阳师神眷阈值 | 神眷 = 「出 SSR/SP 概率掉落 + 累抽 450/800 必定获得」（[手册:2284](docs/主流抽卡游戏卡池机制配置转换手册.md#L2284)，机制双信源确认 2026-08-24：[17173 2023](http://news.17173.com/z/yys/content/01112023/111739115.shtml) + [9game 2023](https://www.9game.cn/yys/9780872.html)） | 🟡 **milestone 层扩展（2026-08-24 归属修正）**：神眷是兑换道具（资源），「必定获得」本质是累抽奖励（milestone at=动态 threshold），非保底概率；450/800 依赖全图鉴状态（跨系统状态）。与 G14（pity 动态 threshold）分属两系统，P64 范围外 |
>>   67 | | G14 战双命运池浮动 | 每次保底周期随机 T∈[80,100]、非保底出 S 1.5%、出 S 重置重抽 T（[手册:2305](docs/主流抽卡游戏卡池机制配置转换手册.md#L2305)，机制双信源确认 2026-08-24：[doyo](https://www.doyo.cn/news/26839.html) + [taptap 数学分析](https://www.taptap.cn/moment/15230243631530325)） | 🟡 后续扩展方向：T 分布未公布（U13）；确认后 P64 条件谓词可表达「counter ≥ 随机 T」 |
     68 | | G5 绝区零执行顺序 | 福利保底（`hard(max_triggers=1)`）应先于 targeted——当前 `_BTYPE_ORDER` hard=1 < targeted=3 已满足（[手册:554](docs/主流抽卡游戏卡池机制配置转换手册.md#L554) 描述过时，2026-08-24 核实） | ✅ **纳入 P64 主线**：显式化现有隐式顺序 + 提供覆盖能力（调度层 `priority`），见 §3.6 |
     69 | | G15 pjsk 加权抽数 | 付费石双倍天井进度（[手册:2306](docs/主流抽卡游戏卡池机制配置转换手册.md#L2306)，付费 +1 / 免费 +0.5） | 🟢 近似可配（2026-08-24）：`reward.resources_gained` 每抽按池注入 + exchange pool 兑换 50/100 档；语义打折（卡附带产出 vs 动作进度）+ 配置脆性（全 reward 需配），严格语义留 milestone `weight_by_pool`（milestone 层，P64 范围外） |
```

**被引行号处的内容**（引用写的是 2305-2305，箭头为起始行）

```
   2302 | |------|------|------|
   2303 | | 公测版本机制 | 三测数据——公测可能调整或回退至传统模式。**保底双黄已确认公测移除**（2026-06-17 交叉验证） | 🔴 高 |
   2304 | | 武器池 UP 率是 25% 还是 75% | 不同来源矛盾——25% 对应「歪率 75%」，75% 对应「UP 率 75%」。三测资料倾向于 25% UP（75% 歪） | 🔴 高 |
>> 2305 | 
   2306 | ---
   2307 | 
   2308 | ## 二十一、总缺口汇总
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 13. `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:428`

- 原文：`](gacha_simulator/core/pity.py#L714)`（md-link / link / module_level）
- 解析到：`gacha_simulator/core/pity.py`
- 目标指纹：`line-v1:e3774797d473530e`
- 引用所在章节（源文档）：`3.2 preset 映射（现有 10 类 → preset，含 counter 驱动统一）` [426, 466]
- 所在章节：`3.2 preset 映射（现有 10 类 → preset，含 counter 驱动统一）` [426, 466]

**引用所在处（箭头为引用行）**

```
    426 | ### 3.2 preset 映射（现有 10 类 → preset，含 counter 驱动统一）
    427 | 
>>  428 | registry（[pity.py:714](gacha_simulator/core/pity.py#L714)）条目新增 `preset` 字段（工厂函数），`class` 字段对事件驱动型置空；counter 驱动型（soft_step/hard）同步 preset 化。`create_behavior` 检测 `entry.get("preset")` 走新路径。
    429 | 
    430 | ```python
```

**被引行号处的内容**（引用写的是 714-714，箭头为起始行）

```
    711 | 
    712 | # ── P60 新增 → P55 更新：保底类型注册表（对齐 STRATEGY_REGISTRY） ──
    713 | 
>>  714 | BEHAVIOR_REGISTRY: Dict[str, dict] = {
    715 |     # ══ P55：counter 驱动型（4 种） ══
    716 |     "soft_interval": {
    717 |         "class": SoftStepBehavior,
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 14. `docs/01-活跃/subsystems/应用打包/P73 scipy依赖替换-混合策略与golden等价对照.md:90`

- 原文：`](gacha_simulator/core/bootstrap.py#L57)`（md-link / link / ok）
- 解析到：`gacha_simulator/core/bootstrap.py`，所属 `BootstrapEngine._percentile_ci` [57, 65]
- 目标指纹：`ast-v1:c4cae4f9b111be88`
- 本行点名且在目标文件内有定义的符号：['_percentile_ci']
- 引用所在章节（源文档）：`阶段划分` [59, 103]
- 所在章节：`阶段划分` [59, 103]

**引用所在处（箭头为引用行）**

```
     88 | 
     89 | - `scipy.stats.bootstrap` 移除 → 手写：
>>   90 |   - percentile：纯 numpy（复用已有 `_percentile_ci`，[bootstrap.py:57](gacha_simulator/core/bootstrap.py#L57)）
     91 |   - BCa：jackknife 加速系数 + 偏差校正（Efron & Tibshirani 1993），约 40 行
     92 | - 内部 `genpareto.fit` / `rvs` → 阶段二 gpd_fit 引擎
```

**被引行号处的内容**（引用写的是 57-57，箭头为起始行）

```
     54 | 
     55 |     # ── 内部工具 ──────────────────────────────────────────────
     56 | 
>>   57 |     def _percentile_ci(self, replicates: np.ndarray, point_est: float = None
     58 |                        ) -> Tuple[float, float, float, float]:
     59 |         """百分位法置信区间。"""
     60 |         if point_est is None:
```

所属符号：`BootstrapEngine._percentile_ci` [57, 65]，指纹 `ast-v1:c4cae4f9b111be88`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 15. `docs/01-活跃/subsystems/性能分析/00-档案.md:17`

- 原文：`multiprocessing/pool.py:861`（prose / plain / external，配置声明为外部）
- 解析到：`未解析`

**引用所在处（箭头为引用行）**

```
     15 | - **三份测量脚本全部失效**：`scripts/profile_gui.py`（413 行）、`scripts/profile_sim.py`（117 行）、`scripts/profile_simulation.py`（121 行）均无法运行，且因被 `.gitignore` 覆盖而从未入库，坏掉无人发现
     16 | - **唯一的自动化性能判据只管「失控」不管「变慢」**：`tests/test_p79_stop_condition_matrix.py` 的 8.4 闸门共 4 个用例，判据是迭代数上界 1000 与耗时阈值 0.5s，用于防止 `WaitAction(duration=0)` 空转复现，不是性能基准
>>   17 | - **剖析位置错了就测不到东西**：模拟的真实计算跑在 `multiprocessing.Pool` 子进程里（`service/batch_simulator.py` 的 `_wk_init` / `_wk_run_single`），2026-09-17 实测在主进程挂剖析器时，父进程主线程空等在 `multiprocessing/pool.py:861`
     18 | - **没有任何剖析工具链**：全仓 `cProfile` / `pstats` / `py-spy` / `yappi` / `line_profiler` 零命中，`pyproject.toml` 的 dev 依赖只有 `pytest` / `pytest-cov` / `pytest-timeout`
     19 | 
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 16. `docs/01-活跃/subsystems/性能分析/01-理论.md:132`

- 原文：`multiprocessing/pool.py:861`（prose / plain / external，配置声明为外部）
- 解析到：`未解析`

**引用所在处（箭头为引用行）**

```
    130 | **分工原则**：进基线的必须是确定性量，故用 `cProfile`；`py-spy` 用于阶段计时与 `cProfile` 都指不出所以然时的现场勘查（主进程串行段、IPC 等待、Qt 事件循环）。
    131 | 
>>  132 | **实测结论（2026-09-17）**：`py-spy 0.4.2` 在本机可用，`--subprocesses` 能采到 `multiprocessing` 子进程并命中 `_wk_run_single` / `build_strategy_context` / `create_strategy`（4 个 worker，8 秒 3193 样本）。同一次实测中，父进程主线程空等在 `multiprocessing/pool.py:861`——**这实证了在主进程挂剖析器测不到有用信息**。
    133 | 
    134 | **依赖边界**：`py-spy` 是独立可执行文件（`pip install py-spy`，但不可 `import`），只进开发依赖，**不进发布产物**。
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 17. `docs/01-活跃/subsystems/性能分析/04-问题.md:25`

- 原文：`scripts/profile_simulation.py:55`（prose / plain / untracked）
- 解析到：`scripts/profile_simulation.py`
- 目标指纹：`line-v1:375772e3eac16f92`
- 引用所在章节（源文档）：`三份性能测量脚本全部失效` [16, 32]
- 所在章节：`三份性能测量脚本全部失效` [16, 32]

**引用所在处（箭头为引用行）**

```
     23 | |------|--------|---------|
     24 | | `scripts/profile_sim.py:51` | `config_store.strategy_name` 已改名 `strategy_key` | `AttributeError: 'ConfigStore' object has no attribute 'strategy_name'. Did you mean: 'strategy_key'?`（已实跑复现） |
>>   25 | | `scripts/profile_simulation.py:55` | 同上 | 同上 |
     26 | | `scripts/profile_sim.py:81` / `profile_simulation.py:92` | `env.strategy_name` 同样失效 | — |
     27 | | `scripts/profile_gui.py:43` | 从 `gacha_simulator.gui.batch_simulator` 导入 | `ImportError: cannot import name 'SimulationEnvBuilder'`（已实跑复现） |
```

**被引行号处的内容**（引用写的是 55-55，箭头为起始行）

```
     52 |     initial_resources=env.initial_resources,
     53 |     num_simulations=N, max_workers=max_workers, seed=42,
     54 |     progress_callback=progress_callback,
>>   55 |     strategy_name=config_store.strategy_name,
     56 |     strategy_params=config_store.strategy_params,
     57 |     on_result=collector.on_result,
     58 | )
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 18. `docs/01-活跃/subsystems/性能分析/04-问题.md:26`

- 原文：`profile_simulation.py:92`（prose / plain / untracked）
- 解析到：`scripts/profile_simulation.py`
- 目标指纹：`line-v1:f7abefbdf705bd98`
- 引用所在章节（源文档）：`三份性能测量脚本全部失效` [16, 32]
- 所在章节：`三份性能测量脚本全部失效` [16, 32]

**引用所在处（箭头为引用行）**

```
     24 | | `scripts/profile_sim.py:51` | `config_store.strategy_name` 已改名 `strategy_key` | `AttributeError: 'ConfigStore' object has no attribute 'strategy_name'. Did you mean: 'strategy_key'?`（已实跑复现） |
     25 | | `scripts/profile_simulation.py:55` | 同上 | 同上 |
>>   26 | | `scripts/profile_sim.py:81` / `profile_simulation.py:92` | `env.strategy_name` 同样失效 | — |
     27 | | `scripts/profile_gui.py:43` | 从 `gacha_simulator.gui.batch_simulator` 导入 | `ImportError: cannot import name 'SimulationEnvBuilder'`（已实跑复现） |
     28 | 
```

**被引行号处的内容**（引用写的是 92-92，箭头为起始行）

```
     89 | target_set = TargetCardSet(targets)
     90 | 
     91 | random.seed(42)
>>   92 | strategy = create_strategy(env.strategy_name, env.strategy_params)
     93 | stop_cond = AllPoolsEndCondition(env.end_time)
     94 | pity_state = None
     95 | if env.pity_state_init:
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 19. `docs/01-活跃/subsystems/性能分析/05-笔记.md:33`

- 原文：`profile_sim.py:116`（prose / plain / untracked）
- 解析到：`scripts/profile_sim.py`
- 目标指纹：`line-v1:5f359aa0b359abca`
- 引用所在章节（源文档）：`2026-09-17 | 首次建档` [7, 39]
- 所在章节：`2026-09-17 | 首次建档` [7, 39]

**引用所在处（箭头为引用行）**

```
     31 | - 根因在代码级坐实：`service/batch_simulator.py:415` / `:441` / `:452`
     32 | - 加重因素：首版探针漏 `__main__` 守卫，spawn 级联起进程池
>>   33 | - **两份防护现有脚本里本来就有**（`profile_sim.py:116` 守卫、`:32-33,53` 流式收集器），手写驱动把两者同时丢掉
     34 | - 产物：`01-理论.md` §2 安全协议 5 条、§3 驱动复用约束（适配器不得新写驱动）
     35 | 
```

**被引行号处的内容**（引用写的是 116-116，箭头为起始行）

```
    113 |     print(f"  10次串行: {t_e - t_s:.1f}s → 1000次约 {(t_e-t_s)/10*1000:.0f}s")
    114 |     print(f"  并行加速比: 约 {(t_e-t_s)/10*1000/(t4-t3_):.1f}x")
    115 | 
>>  116 | if __name__ == '__main__':
    117 |     main()
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 20. `docs/01-活跃/subsystems/性能分析/05-笔记.md:183`

- 原文：`core/gdr.py:825`（prose / plain / line_out_of_range）
- 解析到：`gacha_simulator/core/gdr.py`

**引用所在处（箭头为引用行）**

```
    181 | **对端到端测量的结论：** 当前在 agent 执行环境下不可行。P83 的分段拆解覆盖用户真实感受的全部主要成本（spawn 1.16s / worker 1.82s / 主进程 extractor / 面板模块导入 4.13s），覆盖不到的为面板构造 + 分发执行，P12 实测约 0.2ms。故 §3.2 约束 D 在有意义的量级上成立。
    182 | 
>>  183 | **待办：** 本次文档改动（P83 与 `01-理论.md` 的成因表述更正 + 本条笔记）尚未提交——H7 门控被并行会话在途的 `core/gdr.py:825`（调用未定义的 `_build_legacy_registries()`）拦下，非本次改动所致。
    184 | 
    185 | **机器状态：** 八次探针后 `QtWebEngineProcess` 残留 0、近 1h python 残留 0。
```

**被引目标**：`gacha_simulator/core/gdr.py` 共 813 行，引用写的是 `core/gdr.py:825`，对不上，故无对应内容。文件末尾如下（line_out_of_range）：

```
    806 |     }
    807 |     return compute_gdr_from_compact(
    808 |         pseudo_compact, target_specs, gdr_key,
    809 |         desire_weights, miss_cost_weights, card_value_weights,
    810 |         ssr_ids, weapon_character_map,
    811 |         store=store,
    812 |         **gdr_kwargs,
    813 |     )
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 21. `docs/01-活跃/subsystems/性能分析/P83 性能分析平台——多路径测量·基线回归·现场剖析.md:19`

- 原文：`scripts/profile_sim.py:51`（prose / plain / untracked）
- 解析到：`scripts/profile_sim.py`，所属 `main` [5, 114]
- 目标指纹：`ast-v1:88f1e4473c53f0cc`
- 本行点名且在目标文件内有定义的符号：['config_store']
- 引用所在章节（源文档）：`一、问题` [12, 32]
- 所在章节：`一、问题` [12, 32]

**引用所在处（箭头为引用行）**

```
     17 | 
     18 | **2. 三份测量脚本全部失效且从未入库。**
>>   19 | - `scripts/profile_sim.py:51` 读 `config_store.strategy_name`，该属性已改名 `strategy_key`，实跑抛 `AttributeError`
     20 | - `scripts/profile_gui.py:43` 从 `gacha_simulator.gui.batch_simulator` 导入，而该文件是 **0 字节空文件**（2026-06-12 commit `e3b49c3` 清空，`git ls-files` 确认仍被跟踪），实跑抛 `ImportError`
     21 | - 三份脚本均被 `.gitignore:28,30`（`benchmark_chart.py` / `profile_*.py`，无目录限定）覆盖，从未入库，因此无 CI、无测试、无引用者，失效后无任何机制报警
```

**被引行号处的内容**（引用写的是 51-51，箭头为起始行）

```
     48 |         env=env, target_specs=target_specs, initial_resources=env.initial_resources,
     49 |         num_simulations=N, max_workers=workers, seed=42,
     50 |         progress_callback=on_progress,
>>   51 |         strategy_name=config_store.strategy_name,
     52 |         strategy_params=config_store.strategy_params,
     53 |         on_result=collector.on_result,
     54 |     )
```

所属符号：`main` [5, 114]，指纹 `ast-v1:88f1e4473c53f0cc`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 22. `docs/01-活跃/subsystems/性能分析/P83 性能分析平台——多路径测量·基线回归·现场剖析.md:25`

- 原文：`multiprocessing/pool.py:861`（prose / plain / external，配置声明为外部）
- 解析到：`未解析`

**引用所在处（箭头为引用行）**

```
     23 | **3. 唯一的自动化性能判据只管「失控」不管「变慢」。** `tests/test_p79_stop_condition_matrix.py` 的 8.4 闸门共 4 个用例（实跑 `4 passed`），判据是迭代数上界 1000 与耗时阈值 0.5s，用途是防止 `WaitAction(duration=0)` 空转复现。
     24 | 
>>   25 | **4. 剖析位置错了就测不到东西。** 模拟的真实计算跑在 `multiprocessing.Pool` 子进程里，2026-09-17 实测在主进程挂剖析器时，父进程主线程空等在 `multiprocessing/pool.py:861`。
     26 | 
     27 | **5. 无任何剖析工具链。** 全仓 `cProfile` / `pstats` / `py-spy` / `yappi` / `line_profiler` 零命中；`pyproject.toml` 的 dev 依赖只有 `pytest` / `pytest-cov` / `pytest-timeout`。
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 23. `docs/02-待办/Ps04 资源定义自动生成按钮改造——从覆盖陷阱到汇总扫描.md:152`

- 原文：`_version.py:13`（prose / plain / module_level）
- 解析到：`gacha_simulator/_version.py`
- 目标指纹：`line-v1:a192c79fa577c8d9`
- 引用所在章节（源文档）：`八、实施与验证` [148, 153]
- 所在章节：`八、实施与验证` [148, 153]

**引用所在处（箭头为引用行）**

```
    150 | - 实施：`gacha_simulator/gui/config_panel.py` 改 `_auto_generate_resource_defs`（空兜底不 `return` 继续扫描 + `getattr` 守卫）；`tests/gui/test_p78_config_panel.py` 新增 `test_auto_generate_empty_fallback`（ISSUE-124 兜底）+ `test_auto_generate_preserves_existing`（只补不覆盖，补复核缺陷 A）；「资源管理」→「资源获取」贯穿改名（L577/L3950/L4045/L5103/L6085/L6094）
    151 | - 验证：`tests/gui/test_p78_config_panel.py` 70 passed（含 2 条新增）+ `tests/test_p58_milestone.py` 51 passed + GUI 全量 145 passed + `ruff check` 通过
>>  152 | - 独立复核（CLAUDE.md 独立审查原则）：子 agent 审查实施产物，确认无阻塞问题，唯一非阻塞缺陷为「只补不覆盖」缺测试（已补）；`*_version.py:13` 残留「资源管理」历史日志文本不改（正确决策）
    153 | 
```

**被引行号处的内容**（引用写的是 13-13，箭头为起始行）

```
     10 |     ("2.4.0", "2026-07-29", "DEFAULT — P69 策略系统重构——统一策略组件框架：@register_strategy 装饰器 + StrategyMeta 数据驱动注册表 + ParamDescriptor 6种参数描述符 + 策略插件系统（扫描/加载/热重载）+ 8个内置策略拆分至 strategies/builtin/ + 3种复合策略 Building Block（DrawSegment/PriorityChain/Conditional）+ StrategyContext 上下文契约完善 + 插件管理 GUI + config_panel Tab 拆分"),
     11 |     ("2.3.0", "2026-07-20", "DEFAULT — P65 卡片标签系统：CardDefEntry 新增 tags/list_tags + TOML [[card]] 破坏性变更（段名单数化 + id→card_id）+ QListWidget 详情面板 + 动态标签表 + is_limited() 删除"),
     12 |     ("2.2.0", "2026-06-14", "DEFAULT — P44 池子批次抽卡（十连强制）：Pool/PoolConfig/PoolEntry 三级 batch_size + can_afford_batch 资源预检查 + 服务层批次循环 + 策略层 11 处适配 + 保底逐发直调"),
>>   13 |     ("2.1.0", "2026-06-12", "DEFAULT — P37 资源管理日历增强（事件分组 + 交互联动 + 默认视图）+ 默认模拟起始日期改为当天 + Harness 基础设施完善（H7 Windows 中文路径匹配修复——反斜杠归一化 + GBK 回退）+ 前进法卡牌排序修复——补回缺失 reverse=True（高 desire 优先）+ 全仓库 lint 清理"),
     14 |     ("2.0.0", "2026-06-09", "PROUD — 预发布版里程碑：面板合并（3→1 方案搜索）+ 数据管理层（ResultStore + 数据管理Tab）+ 比较分析面板（L1-L4 递进分析）+ 应用打包（PyInstaller onedir，608MB）+ 统一分箱模块（GDR直方图自动检测）+ 脆弱性分析独立Tab + 文档体系重构（六文件+主题计划模式）"),
     15 |     ("1.10.0", "2026-05-26", "DEFAULT — 文档体系重构：计划汇总整合（24 项已完成登记）、优先级路线图、Bootstrap 计划合并、小样本概率估计改进计划独立、Laplace 平滑→Wilson 得分区间方案、4 项计划归档；版本号里程碑——1.9.x 系列 6 个补丁版本合并发布"),
     16 |     ("1.9.6", "2026-05-26", "DEFAULT — Bootstrap 稳定性分析引擎（BootstrapEngine + BCa + GPD + Hill 估计器）+ GDR 扩展（+4 新指标 + lower_is_better 支持）+ P12-Phase1.5 GUI 性能优化（Extractor 移入 Worker + 单次遍历 + 轻量传输，1000 样本 10-15s → 2-3s）"),
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 24. `docs/05-参考资料/外部研究/外部研究报告对项目启发分析.md:41`

- 原文：`](gacha_simulator/core/strategy.py#L23)`（md-link / link / module_level）
- 解析到：`gacha_simulator/core/strategy.py`
- 目标指纹：`line-v1:87f92f498c20708b`
- 本行点名且在目标文件内有定义的符号：['StrategyContext', 'future_schedules']
- 引用所在章节（源文档）：`1.2 启发一：保底基数资产化 ★★★` [36, 62]
- **门控疑点**：模块级单行锚点落在注释上（指纹永不变化），建议锚点 `99-99`
- 复核队列：文中点名 `future_schedules`，它不覆盖目标行（它在 99-99），建议锚点 `99-99`
- 所在章节：`1.2 启发一：保底基数资产化 ★★★` [36, 62]

**引用所在处（箭头为引用行）**

```
     39 | 
     40 | **当前项目状态**：
>>   41 | - `StrategyContext` 已传入 `future_schedules`（[strategy.py:23](gacha_simulator/core/strategy.py#L23)），但**所有 7 种策略均未使用该字段**
     42 | - 策略决策完全基于当前池状态，不知道未来还有什么池子
     43 | - `pity_reserve` 只看当前池保底概率是否达阈值，不比较「继续抽」vs「保留基数到下一池」
```

**被引行号处的内容**（引用写的是 23-23，箭头为起始行）

```
     20 |     from .milestone import MilestoneEngine, MilestoneDef   # P58（M4a）：策略层里程碑查询
     21 | 
     22 | 
>>   23 | # ── 策略注册表元数据 ──────────────────────────────────────────────
     24 | 
     25 | 
     26 | @dataclass
```

文中点名符号的实际位置（建议锚点 `99-99`）：

```
     97 |     current_pools: List['Pool']
     98 |     all_pools: List['Pool']
>>   99 |     future_schedules: List[PoolSchedule]
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

