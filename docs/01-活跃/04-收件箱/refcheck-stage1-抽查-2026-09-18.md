# refcheck 人工抽查清单

- 配置：`D:\Users\DELL\Desktop\gacha_simulator\抽卡模拟与分析程序\tools\refcheck\refcheck.toml`
- 种子 `20260918`，样本 20 条，取自 341 条引用
- 判定口径：解析到的目标与范围**是否就是文中所指的那一处**
- 命令：`python tools/refcheck/refcheck.py sample --n 20 --seed 20260918`

| # | 位置 | 上下文 | 原文 | 解析到 | 所属符号/章节 | 判定 |
|---|---|---|---|---|---|---|
| 1 | `docs/01-活跃/04-收件箱/quality-2026-08-03.md:94` | prose/plain | `plotly_charts.py:695` | `gacha_simulator/visualization/plotly_charts.py` | - | |
| 2 | `docs/01-活跃/panels/方案搜索/P26 退路搜索与资源目标搜索理论改进计划.md:98` | prose/plain | `gdr.py:814-828` | `gacha_simulator/core/gdr.py` | - | |
| 3 | `docs/01-活跃/subsystems/Bootstrap引擎/P48 Bootstrap UI集成计划.md:25` | prose/plain | `analysis_panel.py:1339` | `gacha_simulator/gui/analysis_panel.py` | AnalysisWorker._run_impl | |
| 4 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:339` | prose/plain | `gdr.py:427` | `gacha_simulator/core/gdr.py` | 模块级 | |
| 5 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:348` | prose/plain | `distribution.py:273` | `gacha_simulator/core/distribution.py` | - | |
| 6 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:979` | prose/plain | `gdr.py:805-818` | `gacha_simulator/core/gdr.py` | - | |
| 7 | `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:54` | md-link/link | `](gacha_simulator/core/pity.py#L200-L203)` | `gacha_simulator/core/pity.py` | CounterBasedBehavior._should_reset | |
| 8 | `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:77` | md-link/link | `](gacha_simulator/core/pity.py#L916)` | `gacha_simulator/core/pity.py` | _resolve_order | |
| 9 | `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:385` | prose/plain | `pity.py:394-399` | `gacha_simulator/core/pity.py` | HardPityBehavior._compute_probabilities | |
| 10 | `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:488` | md-link/link | `](gacha_simulator/core/pity.py#L511-L528)` | `gacha_simulator/core/pity.py` | SoftPityMixin._init_soft_pity | |
| 11 | `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:500` | md-link/link | `](gacha_simulator/gui/config_panel.py#L2765-L2772)` | `gacha_simulator/gui/config_panel.py` | ConfigPanel._build_param_widgets | |
| 12 | `docs/01-活跃/subsystems/应用打包/P73 scipy依赖替换-混合策略与golden等价对照.md:16` | md-link/link | `](gacha_simulator/core/vulnerability.py#L182)` | `gacha_simulator/core/vulnerability.py` | _wilson_ci | |
| 13 | `docs/01-活跃/subsystems/性能分析/00-档案.md:17` | prose/plain | `multiprocessing/pool.py:861` | `未解析(配置声明为外部)` | - | |
| 14 | `docs/01-活跃/subsystems/性能分析/01-理论.md:132` | prose/plain | `multiprocessing/pool.py:861` | `未解析(配置声明为外部)` | - | |
| 15 | `docs/01-活跃/subsystems/性能分析/05-笔记.md:183` | prose/plain | `core/gdr.py:825` | `gacha_simulator/core/gdr.py` | - | |
| 16 | `docs/01-活跃/subsystems/性能分析/P83 性能分析平台——多路径测量·基线回归·现场剖析.md:25` | prose/plain | `multiprocessing/pool.py:861` | `未解析(配置声明为外部)` | - | |
| 17 | `docs/02-待办/Ps04 资源定义自动生成按钮改造——从覆盖陷阱到汇总扫描.md:152` | prose/plain | `_version.py:13` | `gacha_simulator/_version.py` | 模块级 | |
| 18 | `docs/05-参考资料/外部研究/外部研究报告对项目启发分析.md:41` | prose/plain | `strategy.py:23` | `gacha_simulator/core/strategy.py` | 模块级 | |
| 19 | `tests/gui/test_startup.py:29` | string/plain | `main.py:35` | `gacha_simulator/main.py` | 模块级 | |
| 20 | `tests/gui/test_startup.py:41` | string/plain | `main.py:124` | `gacha_simulator/main.py` | 模块级 | |

统计：{'line_out_of_range': 5, 'ok': 7, 'module_level': 5, 'external': 3}

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

### 2. `docs/01-活跃/panels/方案搜索/P26 退路搜索与资源目标搜索理论改进计划.md:98`

- 原文：`gdr.py:814-828`（prose / plain / line_out_of_range）
- 解析到：`gacha_simulator/core/gdr.py`

**引用所在处（箭头为引用行）**

```
     96 | **原始编号**：N1
     97 | 
>>   98 | **现状**（`compute_success_probability()`，`gdr.py:814-828`）：
     99 | - 对 `lower_is_better=True` 的 GDR（`resource_consumed`、`resource_per_card`），成功判定逻辑为 `val <= gdr_threshold`
    100 | - p(r) 因此呈**单调递减**：更多资源 → 更高 GDR 值 → P(GDR ≤ threshold) 下降
```

**被引目标**：`gacha_simulator/core/gdr.py` 共 813 行，引用写的是 `gdr.py:814-828`，对不上，故无对应内容。文件末尾如下（line_out_of_range）：

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

### 3. `docs/01-活跃/subsystems/Bootstrap引擎/P48 Bootstrap UI集成计划.md:25`

- 原文：`analysis_panel.py:1339`（prose / plain / ok）
- 解析到：`gacha_simulator/gui/analysis_panel.py`，所属 `AnalysisWorker._run_impl` [201, 1447]
- 目标指纹：`ast-v1:b6a17754be062919`
- 所在章节：`核心发现：Bootstrap 不适用于二项比例` [21, 29]

**引用所在处（箭头为引用行）**

```
     23 | 方案搜索面板（T5-T8）和脆弱性面板（T9）中涉及的指标本质是**二项比例**（k 次成功 / N 次模拟）。二项比例的置信区间有精确的解析解——**Wilson score interval**——它在有限样本下的覆盖概率**优于** Bootstrap 百分位法：
     24 | 
>>   25 | - Wilson CI：O(1) 解析公式，覆盖概率最接近名义水平，代码库已在 P43 成功率分析中使用（`analysis_panel.py:1339`）
     26 | - Bootstrap BCa：对二项比例无优势，计算成本 O(B·N)，B=1000 时比 Wilson 慢 ~1000 倍，且离散型数据的 BCa 校正有已知问题（Efron 1987 §6）
     27 | 
```

**被引行号处的内容**（引用写的是 1339-1339，箭头为起始行）

```
   1336 |                     title='成功率分析',
   1337 |                     layout_hints={'footnote': subtitle},
   1338 |                 )
>> 1339 |             step_done('成功率分析')
   1340 | 
   1341 |         if 'transition_analysis' in self.selected:
   1342 |             trans = []
```

所属符号：`AnalysisWorker._run_impl` [201, 1447]，指纹 `ast-v1:b6a17754be062919`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 4. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:339`

- 原文：`gdr.py:427`（prose / plain / module_level）
- 解析到：`gacha_simulator/core/gdr.py`
- 目标指纹：`line-v1:7f01071f2afa2006`
- 所在章节：`A 类：compute 函数——统一在 `**kw` 中接收 `resource_id`，默认 `'draw_resource'`（15 处：11 改动 + 2 worst_impact 适配 + 2 调用方确认）` [330, 351]

**引用所在处（箭头为引用行）**

```
    337 | | 4 | `_gdr_resource_remaining()` | `gdr.py:328` | `'draw_resource'` → `resource_id` |
    338 | | 5 | `_gdr_resource_efficiency()` | `gdr.py:357` | 同上 |
>>  339 | | 6 | `_gdr_resource_per_card()` | `gdr.py:427` | 同上（obtained≤0 返回 `nan`） |
    340 | | 7 | `_gdr_resource_consumed()` | `gdr.py:439` | 同上 |
    341 | | 8 | `_gdr_draw_conversion_efficiency()` | `gdr.py:449` | **不展开**，保持硬编码 |
```

**被引行号处的内容**（引用写的是 427-427，箭头为起始行）

```
    424 |         compatible_with_min_resource=False,
    425 |     ),
    426 |     'resource_per_card': GDRDefinition(
>>  427 |         key='resource_per_card',
    428 |         display_name='每目标卡资源消耗',
    429 |         default_threshold=0.0,
    430 |         compute_from_compact=_gdr_resource_per_card,
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 5. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:348`

- 原文：`distribution.py:273`（prose / plain / line_out_of_range）
- 解析到：`gacha_simulator/core/distribution.py`

**引用所在处（箭头为引用行）**

```
    346 | | 13 | `WorstImpactCalculator.analyze()` EVT 跳过 | `worst_impact.py:150-152` | `self.gdr_key in ('resource_remaining', ...)` → `is_resource_gdr(self.gdr_key)` ——`:qualified` key 不在此硬编码元组中 |
    347 | | 14 | `resource_remaining_distribution()` | `risk_analysis.py:15` | 已有 `resource` 参数默认 `'draw_resource'`——函数体无需改，需确认调用方传入正确 `resource_id` |
>>  348 | | 15 | `from_resource_remaining()` | `distribution.py:273` | 已有 `resource` 参数默认 `'draw_resource'`——同上 |
    349 | 
    350 | > **v18 修正**：item 12-13（`worst_impact.py`）实际只需 2 行改动。`_build_success_checker()` 已走在 `make_gdr_calculator` → `GDRCalculator` 统一路径上，GDR 判定部分由 S1.4 自动修复。`ConditionalResourceDistribution` 已有 `resource=` 参数——line 366 修好后自动取正确值。item 14-15 函数体已参数化，仅需确认 S3 面板适配时调用方传入正确的 `resource_id`。
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

### 6. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:979`

- 原文：`gdr.py:805-818`（prose / plain / line_out_of_range）
- 解析到：`gacha_simulator/core/gdr.py`

**引用所在处（箭头为引用行）**

```
    977 | - [x] 决定日期：2026-06-10（v11 命名一致性与架构图审查——15 项修正，详见修订日志。核心变更：`parse_gdr_key` 公共 API 命名、架构图完善、§3.4 v1→v2 术语更新、计数精确化、废弃引用清理。**审查通过，可启动实施**）
    978 | - [x] 决定日期：2026-06-10（v14 P27 排序决策——P27 先合入 → P22 紧随其后）——已被 v15 取代
>>  979 | - [x] **决定日期：2026-06-10（v15 P27 状态核实——P22 无需等待，可立即启动）**：经核实，原 P27 权重数据流重构的核心部分（ConfigStore 三 property + config_panel getter 删除）已合入 main，`GDRContext.compute()` 便利方法未实施且 P22 不需要。P22 面板层直接通过 `self._store.desire_weights` 等取权重后传给 `compute_gdr_from_compact()` 即可。P27 的已合入部分位于 `config_store.py:143-156` 和 `gdr.py:805-818`（`make_gdr_calculator`），均与 P22 改动区域不重叠。P22 无任何前置等待项
    980 | - [x] **决定日期：2026-06-11（v17 实施前审查——4 处遗漏 + 4 项优化）**：① `worst_impact.py` 7 处硬编码补充为 A 类 items 12-13 + §3.4.5 适配条目；② `streaming.py` 6 处硬编码记录为已知限制（热力图资源轴不跟随 GDR 资源类型），不纳入 P22 修改范围；③ `risk_analysis.py` + `distribution.py` 2 处确认调用方传参，函数体无需改；④ `_DRAW_UNIT_GDR_KEYS` 显式删除列入 S2.2；⑤ S1 内部顺序调整为 S1.1→S1.2b→S1.2→S1.3（`resolve_gdr_definition` 提前以支持测试动态阈值）；⑥ S2.5 增加第 7 步热力图一致性检查；⑦ 风险表 +2 条（`streaming.py` 低风险 + `worst_impact.py` 中风险）。核心架构不变。**审查通过，可启动实施**
    981 | - [x] **决定日期：2026-06-11（v18 最差影响统一性核实）**：`_build_success_checker()` 已走 `make_gdr_calculator` → `GDRCalculator` 统一路径——S1.4 修好 `GDRCalculator` 后最差影响 GDR 判定**自动修复**。`ConditionalResourceDistribution` 已有 `resource=` 参数。实际需改 2 行（line 366 `_resource_name` 来源 + line 150-152 EVT 跳过元组 → `is_resource_gdr`），非 v17 估计的 7 处。worst_impact 风险从中降为低。B 类补充「为何不用 GDRCalculator 统一」说明——`GDRCalculator` 不暴露 `compatible_with_min_resource`/`display_name`/`default_threshold`，元数据查询用轻量 `resolve_gdr_definition` 更合适。**审查通过，可启动实施**
```

**被引目标**：`gacha_simulator/core/gdr.py` 共 813 行，引用写的是 `gdr.py:805-818`，对不上，故无对应内容。文件末尾如下（line_out_of_range）：

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

### 7. `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:54`

- 原文：`](gacha_simulator/core/pity.py#L200-L203)`（md-link / link / ok）
- 解析到：`gacha_simulator/core/pity.py`，所属 `CounterBasedBehavior._should_reset` [200, 203]
- 目标指纹：`ast-v1:3eef0e89c04236f2`
- 所在章节：`1.2 剩余缺口盘点（2026-08-24 核实，含双信源）` [49, 58]

**引用所在处（箭头为引用行）**

```
     52 | |------|---------|---------|
     53 | | G1 幻塔连中后必歪 | 真缺口——rotating 只支持「歪→必中」，不支持「中→必歪」 | 新增 `ForceNonFeatured` Modifier + inverse preset |
>>   54 | | G16 幻塔完全不重置 | 单行——[`_should_reset`](gacha_simulator/core/pity.py#L200-L203) 加 `reset="never"` 分支 | **独立先行**（独立 commit，不并 P64） |
     55 | | G19 尘白禁区不歪池 | **✅ 矛盾已解决（2026-09-18 独立调研）**：确认真实机制为「每次出金 100% 为当期 UP」。依据：三个相互独立信源直述同一规则（snowbreak.gg / Steam 社区 / Stage1st）+ 期望值数学自洽（不歪池综合出金率 1.24% 时拿 UP 期望约 80.6 抽，与米池的 80.65 抽相等；若提前出金仅 50% 为 UP，期望应约 121 抽，与三方实测数据冲突）+ 官方对米池必写「占出率 50%」而对特选池从不写该条款的对比。手册已据此修正：§15.3 配置由 `hard(target_featured=true)` 改为 `targeted(fate_threshold=0)` 加 `selected_card_init`；§15.4「165 箱当前无此机制」改为「P58 已覆盖」；§21 G19 行同步 | **已处置**；顺带发现手册全部 `targeted` 配置均缺 `selected_card`（见下方注） |
     56 | 
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

### 8. `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:77`

- 原文：`](gacha_simulator/core/pity.py#L916)`（md-link / link / ok）
- 解析到：`gacha_simulator/core/pity.py`，所属 `_resolve_order` [916, 930]
- 目标指纹：`ast-v1:d01bad079c38e57c`
- 所在章节：`1.5 P82 并入：保底管道执行顺序（2026-09-16 实测完成）` [73, 122]

**引用所在处（箭头为引用行）**

```
     75 | **合并说明**：P82（保底管道顺序接通）于 2026-09-16 并入本计划，P82 文件归档。其结论直接影响 §1.3 的 G5 项与 §3.6 的 priority 设计，**已于 2026-09-18 裁决，见本节末的裁决结论**。
     76 | 
>>   77 | **P82 的问题**：`_resolve_order()`（[pity.py:916](gacha_simulator/core/pity.py#L916)）会计算排序（稀有度 rank → type 顺序 → name），但其结果**只写入 `self._behavior_list`**，而三个调度入口（`get_probabilities` / `before_draw` / `after_draw`）走的是 `get_behaviors_for_pool()` → `spec.pity_names`，后者由 `batch_simulator.py:173-177` 按 **TOML 定义顺序**构造。即排序算了但未接入概率管道，`P30 #11` 的「顺序由定义顺序决定」在代码上仍成立。
     78 | 
     79 | **P82 的实测结论（2026-09-16）**：
```

**被引行号处的内容**（引用写的是 916-916，箭头为起始行）

```
    913 | }
    914 | 
    915 | 
>>  916 | def _resolve_order(behaviors, rarity_rank=None):
    917 |     """按稀有度层级→type 优先级排序 behavior 列表。
    918 | 
    919 |     P55 §3.3：高稀有度先执行（rank 值小→优先级高），同稀有度内
```

所属符号：`_resolve_order` [916, 930]，指纹 `ast-v1:d01bad079c38e57c`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 9. `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:385`

- 原文：`pity.py:394-399`（prose / plain / ok）
- 解析到：`gacha_simulator/core/pity.py`，所属 `HardPityBehavior._compute_probabilities` [360, 401]
- 目标指纹：`ast-v1:ab012308c7ae93f4`
- 所在章节：`3.1.5.4 定理 2（可交换性判据）` [381, 414]

**引用所在处（箭头为引用行）**

```
    383 | > 用途：§1.5 三项待裁决中的「组合顺序是语义还是实现细节」需要判据，本定理给出判据而非实测扫描。
    384 | 
>>  385 | **引理 2.1**：若算子 X 不改变 F 作用域之外的**更高稀有度**槽位，则 `F(T) ∘ X = F(T)`。F 在 T 所在 scope 内的输出只依赖 w 与 T，与输入的 scope 内取值无关；但它**保留更高稀有度槽位的原值**（[pity.py:394-399](gacha_simulator/core/pity.py#L394-L399)），故对这部分槽位不具吸收性。反例：`F_sr ∘ B_ssr ≠ F_sr`（`B_ssr` 改动了 ssr 槽位，`F_sr` 会把改动后的值原样保留；实测输入 (0.01, 0.01, 0.08, 0.9) 下前者 ssr 槽为 0.255，后者为 0.01）。推论表中用到本引理的那一行（soft 与 hard 同 scope）满足条件，因为 `B` 的层级保护不改动更高稀有度槽位。
    386 | 
    387 | **引理 2.2**：若（a）X 的源集 ⊇ Y 的源集 ∪ Y 的目标集，（b）X 对源集内所有槽位用同一缩放因子，（c）X 把取出的量按**只依赖 w 的固定权重**交给目标，（d）Y 的写入全部落在 X 的源集之内，则 `X ∘ Y = Y ∘ X`。（a）是核心条件；（b）（c）保证 X 是「统一缩放 + 固定权重再分配」型算子；（d）防止 Y 写到 X 的源集之外。四个条件在「异 scope soft」场景下均满足。本引理是**充分条件而非充要条件**（同 scope 但 `target_featured` 不同的两条 soft 不满足其假设，却仍可交换）。
```

**被引行号处的内容**（引用写的是 394-399，箭头为起始行）

```
    391 |             for s in target_slots:
    392 |                 result[s] = per
    393 | 
>>  394 |         # 保留非目标槽位的稀有度层级保护——更高稀有度不变
    395 |         scope_rank = ctx.draw.rarity_rank.get(self._scope, 99)
    396 |         for rarity, rank in ctx.draw.rarity_rank.items():
    397 |             if rank < scope_rank:
    398 |                 for s in ctx.draw.scope_slots.get(rarity, ()):
    399 |                     result[s] = ctx.current.get(s, 0.0)
    400 | 
    401 |         return result
    402 | 
```

所属符号：`HardPityBehavior._compute_probabilities` [360, 401]，指纹 `ast-v1:ab012308c7ae93f4`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 10. `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:488`

- 原文：`](gacha_simulator/core/pity.py#L511-L528)`（md-link / link / ok）
- 解析到：`gacha_simulator/core/pity.py`，所属 `SoftPityMixin._init_soft_pity` [511, 528]
- 目标指纹：`ast-v1:60c9d21f84a470c6`
- 所在章节：`3.4 软保底统一（不再分阶段二）` [482, 491]

**引用所在处（箭头为引用行）**

```
    486 | - `SoftStepBehavior`/`HardPityBehavior` 同步退役为 preset（CounterTracker + 对应 Modifier）
    487 | - `SoftPityMixin` + 3 个 `_soft` 类同步退役
>>  488 | - **deltas 展开职责移交（M6）**：`SoftPityMixin._init_soft_pity` 唯一做 `soft_start/soft_end/soft_increment → deltas` 展开（[pity.py:511-528](gacha_simulator/core/pity.py#L511-L528)），退役后该展开移入 preset 工厂（依赖 create_behavior 已透传的 soft_* 参数，[pity.py:864-874](gacha_simulator/core/pity.py#L864-L874)）
    489 | 
    490 | `rotating_soft` = rotating 的 Tracker/Modifier 各加一项，`_SOFT_SUFFIX_TYPES` 处理移除；任意 Tracker × 任意 Modifier 自由组合，不再需要每组合一个类。
```

**被引行号处的内容**（引用写的是 511-528，箭头为起始行）

```
    508 | 
    509 | class SoftPityMixin:
    510 |     """混入软保底——委托 P55 SoftStepBehavior deltas 引擎。MRO 关键：mixin 必须在继承列表首位。"""
>>  511 |     def _init_soft_pity(self, name, state, scope, **kwargs):
    512 |         assert hasattr(self, '_scope'), 'SoftPityMixin._init_soft_pity: 父类 __init__ 必须先于本方法调用'
    513 |         from .config_toml import _expand_soft_to_deltas  # noqa: E402
    514 |         soft_deltas = kwargs.get('soft_deltas')
    515 |         if soft_deltas:
    516 |             btype = 'soft_step'
    517 |             deltas = soft_deltas
    518 |             if isinstance(deltas, (list, tuple)) and len(deltas) == 0:
    519 |                 btype = 'soft_interval'
    520 |                 deltas = ((0, 0.0),)
    521 |         elif kwargs.get('soft_increment') is not None:
   ...  | （还有 10 行）
```

所属符号：`SoftPityMixin._init_soft_pity` [511, 528]，指纹 `ast-v1:60c9d21f84a470c6`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 11. `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:500`

- 原文：`](gacha_simulator/gui/config_panel.py#L2765-L2772)`（md-link / link / ok）
- 解析到：`gacha_simulator/gui/config_panel.py`，所属 `ConfigPanel._build_param_widgets` [2764, 2837]
- 目标指纹：`ast-v1:08e2cb970dfcada7`
- 所在章节：`3.6 与引擎/配置/GUI 对接` [496, 504]

**引用所在处（箭头为引用行）**

```
    498 | - **PityEngine**（[pity.py:1124](gacha_simulator/core/pity.py#L1124)）：调度层接口签名不变，`before_draw`/`after_draw`/`get_probabilities` 调用链不变，P75 rebind 由 Pity 统一实现。**G5 priority（2026-09-18 裁决：保留并实施，与接线配套）**：`_resolve_order`（[pity.py:916](gacha_simulator/core/pity.py#L916)）排序 key 加 `priority` 优先级（位于稀有度 rank 之后、type order 之前）。**透传（M3）**：`PityDef` 新增 `priority: int = 0`，`create_behavior` 构造后设置 `pity._priority` 属性（Pity 与 counter 驱动统一，不改构造签名）——priority 全 0 时排序结果与现状完全一致，显式 priority 覆盖 type 顺序。**论证**：接线（§1.5 裁决 1）使排序键成为管道顺序的唯一来源，配置者不再能靠「TOML 书写顺序」控制优先级，`priority` 因此成为唯一的顺序覆盖入口；当前 `_BTYPE_ORDER` hard=1 < targeted=3 已满足绝区零 G5 需求，priority 的价值是「显式化现有隐式顺序 + 提供未来场景覆盖」。**接线本身建议独立先行（§1.5 实施方案），本项随主线实施**
    499 | - **PityDef/TOML**：现有 type 名继续有效（preset 别名）；`rotating_inverse` 新 type 无需新字段；`PityDef.priority` 新增；参数透传（[pity.py:864-892](gacha_simulator/core/pity.py#L864-L892)）逻辑保留，目标从具体类变 preset 工厂
>>  500 | - **GUI config_panel**：**2026-09-18 事实修正（两处）**——① 保底 type 下拉**不是** registry 驱动，而是硬编码列表 `_PITY_TYPES`（[config_panel.py:2019-2031](gacha_simulator/gui/config_panel.py#L2019-L2031)，10 项；[config_panel.py:2084](gacha_simulator/gui/config_panel.py#L2084) 处 `addItems`），新增 `rotating_inverse` 须**手工追加**该列表，否则 GUI 不可选（由 registry 驱动的是**参数控件**，[config_panel.py:2765-2772](gacha_simulator/gui/config_panel.py#L2765-L2772)，该部分「零改动」成立）；② **GUI 现无 reset 控件**，`_apply_pity_edit` 不写 `pd['reset']`，`reset` 仅在 load/save 路径透传（[config_panel.py:6349](gacha_simulator/gui/config_panel.py#L6349)、[config_panel.py:7190](gacha_simulator/gui/config_panel.py#L7190)），故 G16 的 GUI 部分是**新建控件**而非「下拉加一项」；③ priority 编辑控件（G5）同为新建；参数控件零改动
    501 | - **config/config.toml**：新增幻塔 `rotating_inverse` + G16 示例配置
    502 | - **GachaService 定轨识别（H1，强制）**：[gacha_service.py:275](gacha_simulator/service/gacha_service.py#L275) 用 `isinstance(bh, TargetedBehavior)` 识别定轨保底（`switch_epitomized_target`/`cancel_epitomized_path` 两条 NonDrawAction 流程）。targeted preset 化后 bh 变为 `Pity` 实例，isinstance 恒 False → 定轨流程整体失效。须改为 `getattr(bh, '_btype', '') in ('targeted', 'targeted_soft')`（或 Pity 加 `_is_targeted` 标记），波及范围表补 `service/gacha_service.py`
```

**被引行号处的内容**（引用写的是 2765-2772，箭头为起始行）

```
   2762 |     # ── 动态控件构建 ──
   2763 | 
   2764 |     def _build_param_widgets(self, btype: str) -> dict:
>> 2765 |         """根据 BEHAVIOR_REGISTRY 中 btype 的 params 元数据生成控件。
   2766 |         返回 {param_name: widget} dict。
   2767 |         """
   2768 |         widgets = {}
   2769 |         # 清除旧控件
   2770 |         self._clear_dynamic_widgets()
   2771 | 
   2772 |         entry = BEHAVIOR_REGISTRY.get(btype, {})
   2773 |         params_meta = entry.get('params', {})
   2774 | 
   2775 |         for pname, pmeta in params_meta.items():
```

所属符号：`ConfigPanel._build_param_widgets` [2764, 2837]，指纹 `ast-v1:08e2cb970dfcada7`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 12. `docs/01-活跃/subsystems/应用打包/P73 scipy依赖替换-混合策略与golden等价对照.md:16`

- 原文：`](gacha_simulator/core/vulnerability.py#L182)`（md-link / link / ok）
- 解析到：`gacha_simulator/core/vulnerability.py`，所属 `_wilson_ci` [175, 200]
- 目标指纹：`ast-v1:e1e74dd1d90db318`
- 所在章节：`一、问题` [8, 26]

**引用所在处（箭头为引用行）**

```
     14 | | [core/bootstrap.py](gacha_simulator/core/bootstrap.py#L12) | 顶层导入 | `scipy.stats.bootstrap`（BCa / percentile）、`scipy.stats.genpareto`（fit / rvs） |
     15 | | [core/evt_tail.py](gacha_simulator/core/evt_tail.py#L16) | 顶层导入 | `scipy.stats.genpareto.fit` |
>>   16 | | [core/vulnerability.py](gacha_simulator/core/vulnerability.py#L182) | 惰性导入 | `scipy.stats.norm.ppf`（Wilson CI） |
     17 | | [core/comparison_analyzer.py](gacha_simulator/core/comparison_analyzer.py#L52) | 惰性导入 | `skew` / `kurtosis` / `ks_2samp` / `mannwhitneyu` / `ttest_ind` |
     18 | 
```

**被引行号处的内容**（引用写的是 182-182，箭头为起始行）

```
    179 | 
    180 |     Args:
    181 |         n_success: 成功计数
>>  182 |         n_total: 总计数
    183 |         level: 置信水平
    184 | 
    185 |     Returns:
```

所属符号：`_wilson_ci` [175, 200]，指纹 `ast-v1:e1e74dd1d90db318`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 13. `docs/01-活跃/subsystems/性能分析/00-档案.md:17`

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

### 14. `docs/01-活跃/subsystems/性能分析/01-理论.md:132`

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

### 15. `docs/01-活跃/subsystems/性能分析/05-笔记.md:183`

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

### 16. `docs/01-活跃/subsystems/性能分析/P83 性能分析平台——多路径测量·基线回归·现场剖析.md:25`

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

### 17. `docs/02-待办/Ps04 资源定义自动生成按钮改造——从覆盖陷阱到汇总扫描.md:152`

- 原文：`_version.py:13`（prose / plain / module_level）
- 解析到：`gacha_simulator/_version.py`
- 目标指纹：`line-v1:a192c79fa577c8d9`
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

### 18. `docs/05-参考资料/外部研究/外部研究报告对项目启发分析.md:41`

- 原文：`strategy.py:23`（prose / plain / module_level）
- 解析到：`gacha_simulator/core/strategy.py`
- 目标指纹：`line-v1:87f92f498c20708b`
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

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 19. `tests/gui/test_startup.py:29`

- 原文：`main.py:35`（string / plain / module_level，按全局别名裁决）
- 解析到：`gacha_simulator/main.py`
- 目标指纹：`line-v1:70307ab009fe2979`

**引用所在处（箭头为引用行）**

```
     27 | @pytest.fixture(scope="module")
     28 | def qapp():
>>   29 |     """等价 main.py:35 — 创建 QApplication。"""
     30 |     app = QApplication.instance()
     31 |     if app is None:
```

**被引行号处的内容**（引用写的是 35-35，箭头为起始行）

```
     32 |     _ICON_PATH = get_resource('app_icon.png')
     33 | 
     34 |     QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
>>   35 |     app = QApplication(sys.argv)
     36 |     from gacha_simulator.gui.wheel_blocker import GlobalWheelBlocker
     37 |     app.installEventFilter(GlobalWheelBlocker(app))
     38 |     app.setApplicationName("GachaStat")
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 20. `tests/gui/test_startup.py:41`

- 原文：`main.py:124`（string / plain / module_level，按全局别名裁决）
- 解析到：`gacha_simulator/main.py`
- 目标指纹：`line-v1:c7798f1f233497de`

**引用所在处（箭头为引用行）**

```
     39 | @pytest.fixture(scope="module")
     40 | def main_window(qapp):
>>   41 |     """等价 main.py:124 — 创建 MainWindow（最高风险步骤）。"""
     42 |     from gacha_simulator.gui import MainWindow
     43 | 
```

**被引行号处的内容**（引用写的是 124-124，箭头为起始行）

```
    121 |     except Exception:
    122 |         pass
    123 | 
>>  124 |     window = MainWindow()
    125 |     window.show()
    126 | 
    127 |     # ── Ps03：Ctrl+R 重启快捷键（开发调试用）──
```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

