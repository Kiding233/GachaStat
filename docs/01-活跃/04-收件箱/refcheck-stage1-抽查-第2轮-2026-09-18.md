<!-- refcheck:generated：本文件由 refcheck 产出，扫描时按标记自动剔除。-->

# refcheck 人工抽查清单

- 配置：`D:\Users\DELL\Desktop\gacha_simulator\抽卡模拟与分析程序\tools\refcheck\refcheck.toml`
- 种子 `20260918`，样本 20 条，取自去重后 277 条引用
- 已剔除本工具自产清单 1 个：`docs/01-活跃/04-收件箱/refcheck-stage1-抽查-2026-09-18.md`
- 判定口径：解析到的目标与范围**是否就是文中所指的那一处**
- 命令：`python tools/refcheck/refcheck.py sample --n 20 --seed 20260918`

| # | 位置 | 上下文 | 原文 | 解析到 | 所属符号/章节 | 目标侧疑点 | 判定 |
|---|---|---|---|---|---|---|---|
| 1 | `docs/01-活跃/04-收件箱/quality-2026-08-03.md:17` | prose/plain | `resource_gain.py:24` | `gacha_simulator/core/resource_gain.py` | 模块级 | 模块级单行锚点落在注释上（指纹永不变化）；文中点名 `ScheduleResourceGain`，它不覆盖目标行（它在 37-58）（建议 37-58） | |
| 2 | `docs/01-活跃/panels/方案搜索/P26 退路搜索与资源目标搜索理论改进计划.md:98` | prose/plain | `gdr.py:814-828` | `gacha_simulator/core/gdr.py` | - | - | |
| 3 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:148` | prose/plain | `analysis_panel.py:304` | `gacha_simulator/gui/analysis_panel.py` | AnalysisWorker._run_impl | - | |
| 4 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:583` | prose/plain | `resource_search_panel.py:73` | `.recycle_bin/2026-09-17-p81-archived-panels/resource_search_panel.py` | ResourceSearchWorker._extract_cost_per_draw | - | |
| 5 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:791` | prose/plain | `plan_search_panel.py:698` | `gacha_simulator/gui/plan_search_panel.py` | PlanSearchPanel._setup_params_group | - | |
| 6 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:797` | prose/plain | `resource_search_panel.py:322` | `.recycle_bin/2026-09-17-p81-archived-panels/resource_search_panel.py` | ResourceSearchPanel._setup_ui | - | |
| 7 | `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:798` | prose/plain | `retreat_search_panel.py:346` | `.recycle_bin/2026-09-17-p81-archived-panels/retreat_search_panel.py` | RetreatSearchPanel._setup_ui | - | |
| 8 | `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:67` | md-link/link | `](docs/主流抽卡游戏卡池机制配置转换手册.md#L2305)` | `docs/主流抽卡游戏卡池机制配置转换手册.md` | - | - | |
| 9 | `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:428` | md-link/link | `](gacha_simulator/core/pity.py#L714)` | `gacha_simulator/core/pity.py` | 模块级 | - | |
| 10 | `docs/01-活跃/subsystems/应用打包/P73 scipy依赖替换-混合策略与golden等价对照.md:90` | md-link/link | `](gacha_simulator/core/bootstrap.py#L57)` | `gacha_simulator/core/bootstrap.py` | BootstrapEngine._percentile_ci | - | |
| 11 | `docs/01-活跃/subsystems/性能分析/00-档案.md:17` | prose/plain | `multiprocessing/pool.py:861` | `未解析(配置声明为外部)` | - | - | |
| 12 | `docs/01-活跃/subsystems/性能分析/01-理论.md:132` | prose/plain | `multiprocessing/pool.py:861` | `未解析(配置声明为外部)` | - | - | |
| 13 | `docs/01-活跃/subsystems/性能分析/04-问题.md:26` | prose/plain | `profile_simulation.py:92` | `scripts/profile_simulation.py` | 模块级 | - | |
| 14 | `docs/01-活跃/subsystems/性能分析/04-问题.md:75` | prose/plain | `gacha_service.py:65` | `gacha_simulator/service/gacha_service.py` | _derive_pool_type | - | |
| 15 | `docs/01-活跃/subsystems/性能分析/P83 性能分析平台——多路径测量·基线回归·现场剖析.md:25` | prose/plain | `multiprocessing/pool.py:861` | `未解析(配置声明为外部)` | - | - | |
| 16 | `docs/01-活跃/subsystems/性能分析/P83 性能分析平台——多路径测量·基线回归·现场剖析.md:627` | prose/plain | `scripts/profile_sim.py:51` | `scripts/profile_sim.py` | main | - | |
| 17 | `docs/01-活跃/subsystems/性能分析/P83 性能分析平台——多路径测量·基线回归·现场剖析.md:631` | prose/plain | `scripts/profile_gui.py:43` | `scripts/profile_gui.py` | run_simulation_cycle | - | |
| 18 | `docs/02-待办/P41 目标卡实例权重架构改造——可行性分析.md:419` | prose/plain | `gdr.py:770-815` | `gacha_simulator/core/gdr.py` | - | - | |
| 19 | `docs/02-待办/P84 文档与代码互引管理（双向标记与漂移检测）.md:724` | prose/plain | `gui/batch_simulator.py:5` | `gacha_simulator/gui/batch_simulator.py` | - | - | |
| 20 | `docs/02-待办/Ps04 资源定义自动生成按钮改造——从覆盖陷阱到汇总扫描.md:152` | prose/plain | `_version.py:13` | `gacha_simulator/_version.py` | 模块级 | - | |

统计：{'module_level': 3, 'line_out_of_range': 3, 'ok': 5, 'out_of_scope': 3, 'external': 3, 'untracked': 3}
带目标侧疑点的样本：1 / 20

---

## 逐条上下游对照

### 1. `docs/01-活跃/04-收件箱/quality-2026-08-03.md:17`

- 原文：`resource_gain.py:24`（prose / plain / module_level）
- 解析到：`gacha_simulator/core/resource_gain.py`
- 目标指纹：`line-v1:4449aa018c607cba`
- 本行点名且在目标文件内有定义的符号：['ScheduleResourceGain']
- **目标侧疑点**：模块级单行锚点落在注释上（指纹永不变化），建议锚点 `37-58`
- **目标侧疑点**：文中点名 `ScheduleResourceGain`，它不覆盖目标行（它在 37-58），建议锚点 `37-58`
- 所在章节：`持续存在` [15, 18]

**引用所在处（箭头为引用行）**

```
     15 | ### 持续存在
     16 | 
>>   17 | - **`DAY = 86400` 两处定义**：`strategy_context_builder.py:25` 与 `resource_gain.py:24`（`ScheduleResourceGain.DAY`）。秒/天换算魔数双源，注释已承认「与 resource_gain.py ... 一致」但未消除。建议引用共享（如从 resource_gain import 或提公共常量）。低优先级——两值当前相同，漂移风险有限，但正因如此更应在计划内顺手收敛。
     18 | 
     19 | ### 已确认消除 ✅
```

**被引行号处的内容**（引用写的是 24-24，箭头为起始行）

```
     21 | # 将来若需亚日粒度收入（如「每 6 小时回体力」）：**正确路径是给日程表加时间
     22 | # 粒度**（把 ScheduleResourceGain.DAY 由常量改为可配 tick），因其账目为绝对
     23 | # 定位且有界；不要复活按时长计数的周期型实现——它在「单次等待短于一个周期」
>>   24 | # 时会丢弃余数。
     25 | 
     26 | 
     27 | class ResourceGainFunction(ABC):
```

文中点名符号的实际位置（建议锚点 `37-58`）：

```
     35 | 
     36 | 
>>   37 | class ScheduleResourceGain(ResourceGainFunction):
     38 |     DAY = 86400
     39 | 
     40 |     def __init__(self, schedule: Dict[int, Dict[str, float]], total_days: int = 365):
     41 |         self.schedule = schedule
     42 |         self.total_days = total_days
     43 | 
     44 |     def compute(self, elapsed_time: float, state: 'GachaState') -> Dict[str, float]:
     45 |         current_day = int(state.real_time // self.DAY)
     46 |         new_day = int((state.real_time + elapsed_time) // self.DAY)
     47 | 
     48 |         result: Dict[str, float] = {}
   ...  | （还有 10 行）
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

### 3. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:148`

- 原文：`analysis_panel.py:304`（prose / plain / ok）
- 解析到：`gacha_simulator/gui/analysis_panel.py`，所属 `AnalysisWorker._run_impl` [201, 1447]
- 目标指纹：`ast-v1:b6a17754be062919`
- 所在章节：`2.4 不抽卡参考线（跨模块）` [143, 151]

**引用所在处（箭头为引用行）**

```
    146 | |------|-----------|
    147 | | `batch_simulator.py` / `gacha_panel.py` | no_draw 模拟仅记录 `draw_resource` 最终值 |
>>  148 | | `analysis_panel.py:304` | 参考线值直接 `no_draw_ref / cost_per_draw` |
    149 | 
    150 | ---
```

**被引行号处的内容**（引用写的是 304-304，箭头为起始行）

```
    301 |             self._emit('生成GDR分布...', int(completed / total_steps * 100))
    302 |             for metric_name, chart_types in self.gdr_dist_selections.items():
    303 |                 metric_key = _display_to_key.get(metric_name, metric_name)
>>  304 |                 dist = gdr_dists.get(metric_key)
    305 |                 if not dist or dist.n == 0:
    306 |                     continue
    307 | 
```

所属符号：`AnalysisWorker._run_impl` [201, 1447]，指纹 `ast-v1:b6a17754be062919`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 4. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:583`

- 原文：`resource_search_panel.py:73`（prose / plain / out_of_scope）
- 解析到：`.recycle_bin/2026-09-17-p81-archived-panels/resource_search_panel.py`，所属 `ResourceSearchWorker._extract_cost_per_draw` [72, 86]
- 目标指纹：`ast-v1:9f4257ef4b57a92e`
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

### 5. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:791`

- 原文：`plan_search_panel.py:698`（prose / plain / ok）
- 解析到：`gacha_simulator/gui/plan_search_panel.py`，所属 `PlanSearchPanel._setup_params_group` [668, 751]
- 目标指纹：`ast-v1:cf22e286509a8ad5`
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

### 6. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:797`

- 原文：`resource_search_panel.py:322`（prose / plain / out_of_scope）
- 解析到：`.recycle_bin/2026-09-17-p81-archived-panels/resource_search_panel.py`，所属 `ResourceSearchPanel._setup_ui` [304, 480]
- 目标指纹：`ast-v1:8f8632417caef5d1`
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

### 7. `docs/01-活跃/subsystems/GDR系统/P22 多资源类型分布实施方案.md:798`

- 原文：`retreat_search_panel.py:346`（prose / plain / out_of_scope）
- 解析到：`.recycle_bin/2026-09-17-p81-archived-panels/retreat_search_panel.py`，所属 `RetreatSearchPanel._setup_ui` [245, 417]
- 目标指纹：`ast-v1:9d638961b533ebff`
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

### 8. `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:67`

- 原文：`](docs/主流抽卡游戏卡池机制配置转换手册.md#L2305)`（md-link / link / ok）
- 解析到：`docs/主流抽卡游戏卡池机制配置转换手册.md`
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

### 9. `docs/01-活跃/subsystems/保底系统/P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构.md:428`

- 原文：`](gacha_simulator/core/pity.py#L714)`（md-link / link / module_level）
- 解析到：`gacha_simulator/core/pity.py`
- 目标指纹：`line-v1:e3774797d473530e`
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

### 10. `docs/01-活跃/subsystems/应用打包/P73 scipy依赖替换-混合策略与golden等价对照.md:90`

- 原文：`](gacha_simulator/core/bootstrap.py#L57)`（md-link / link / ok）
- 解析到：`gacha_simulator/core/bootstrap.py`，所属 `BootstrapEngine._percentile_ci` [57, 65]
- 目标指纹：`ast-v1:c4cae4f9b111be88`
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

### 11. `docs/01-活跃/subsystems/性能分析/00-档案.md:17`

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

### 12. `docs/01-活跃/subsystems/性能分析/01-理论.md:132`

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

### 13. `docs/01-活跃/subsystems/性能分析/04-问题.md:26`

- 原文：`profile_simulation.py:92`（prose / plain / untracked）
- 解析到：`scripts/profile_simulation.py`
- 目标指纹：`line-v1:f7abefbdf705bd98`
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

### 14. `docs/01-活跃/subsystems/性能分析/04-问题.md:75`

- 原文：`gacha_service.py:65`（prose / plain / ok）
- 解析到：`gacha_simulator/service/gacha_service.py`，所属 `_derive_pool_type` [56, 65]
- 目标指纹：`ast-v1:6e3478071d48be60`
- 所在章节：``Pool.output` @property 已确认是热区` [60, 78]

**引用所在处（箭头为引用行）**

```
     73 | 
     74 | - **换算**：30 次模拟共 498,684 次 `output` 调用 ≈ **每次模拟 16,600 次**
>>   75 | - **机制**：`core/pool.py:160` 的 `output` 实现为 `all(r.id == NO_CARD_ID for r, _ in self.rewards)`，每次访问全量扫 `rewards`；而 `self.rewards` 是静态配置，该值对给定 Pool **恒定不变**。调用点在 `pool.py:177`（`is_exchange`）与 `gacha_service.py:65,67`
     76 | - **附带**：`is_exchange`（4.7%）同样调用 `self.output`，两者合计构成一条「每次访问都重算静态事实」的热路径
     77 | - **处置**：本平台只负责把它测出来；优化（缓存或预计算）属 P12 范畴
```

**被引行号处的内容**（引用写的是 65-65，箭头为起始行）

```
     62 |         return '资源'
     63 |     if pool.output == 'card' and not pool.random:
     64 |         return '兑换'
>>   65 |     return '角色'
     66 | 
     67 | 
     68 | # ── P79（阶段 3）：零进度兜底 ──────────────────────────────────────
```

所属符号：`_derive_pool_type` [56, 65]，指纹 `ast-v1:6e3478071d48be60`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 15. `docs/01-活跃/subsystems/性能分析/P83 性能分析平台——多路径测量·基线回归·现场剖析.md:25`

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

### 16. `docs/01-活跃/subsystems/性能分析/P83 性能分析平台——多路径测量·基线回归·现场剖析.md:627`

- 原文：`scripts/profile_sim.py:51`（prose / plain / untracked）
- 解析到：`scripts/profile_sim.py`，所属 `main` [5, 114]
- 目标指纹：`ast-v1:88f1e4473c53f0cc`
- 所在章节：`阶段 2：inline 适配器与失效脚本接管` [623, 635]

**引用所在处（箭头为引用行）**

```
    625 | | 项 | 内容 |
    626 | |---|---|
>>  627 | | 修复 | `scripts/profile_sim.py:51` / `:81` 的 `strategy_name`；`run_batch_parallel` 关键字（`1a` 已实测现签名为 `strategy_key`） |
    628 | | 修复 | `scripts/profile_simulation.py:55` / `:92` 同型；并处置与 `profile_sim.py` 的本地重复 |
    629 | | 修复 | `scripts/verify_p26_integration.py:173`、`scripts/verify_p26_pity_causality.py:95`（**已入库文件**，修的是仓库缺陷） |
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

### 17. `docs/01-活跃/subsystems/性能分析/P83 性能分析平台——多路径测量·基线回归·现场剖析.md:631`

- 原文：`scripts/profile_gui.py:43`（prose / plain / untracked）
- 解析到：`scripts/profile_gui.py`，所属 `run_simulation_cycle` [40, 268]
- 目标指纹：`ast-v1:b03fbf6d6da56e6b`
- 所在章节：`阶段 2：inline 适配器与失效脚本接管` [623, 635]

**引用所在处（箭头为引用行）**

```
    629 | | 修复 | `scripts/verify_p26_integration.py:173`、`scripts/verify_p26_pity_causality.py:95`（**已入库文件**，修的是仓库缺陷） |
    630 | | 新增 | `perf/adapters/inline.py`：`is_user_path=False` |
>>  631 | | 修改 | `scripts/profile_gui.py:43` 的导入路径改指 `service.batch_simulator`（`2f`）。**`gui/batch_simulator.py` 空文件本体的去留归 P81** |
    632 | | 测试 | T3 的 `inline` 部分（`2e`） |
    633 | 
```

**被引行号处的内容**（引用写的是 43-43，箭头为起始行）

```
     40 | def run_simulation_cycle(store, N, max_workers, label):
     41 |     import numpy as np
     42 | 
>>   43 |     from gacha_simulator.gui.batch_simulator import (
     44 |         SimulationEnvBuilder, run_batch_parallel,
     45 |     )
     46 |     from gacha_simulator.core.streaming import (
```

所属符号：`run_simulation_cycle` [40, 268]，指纹 `ast-v1:b03fbf6d6da56e6b`

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 18. `docs/02-待办/P41 目标卡实例权重架构改造——可行性分析.md:419`

- 原文：`gdr.py:770-815`（prose / plain / line_out_of_range）
- 解析到：`gacha_simulator/core/gdr.py`

**引用所在处（箭头为引用行）**

```
    417 | | `_gdr_target_card_draws` | 同上 |
    418 | 
>>  419 | history-based 路径（`compute_all_gdr`，`gdr.py:770-815`）中 `weighted_satisfaction(history, ctx, get_weight, miss_cost_func)` 同样适配——`get_weight` / `miss_cost_func` callable 内部切换至 `resolve_instance_weight`。适配方式与 compact 路径一致（`card_weights` 优先，旧 Dict fallback）。
    420 | 
    421 | ### 5.6 GDRCalculator / make_gdr_calculator 过渡
```

**被引目标**：`gacha_simulator/core/gdr.py` 共 813 行，引用写的是 `gdr.py:770-815`，对不上，故无对应内容。文件末尾如下（line_out_of_range）：

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

### 19. `docs/02-待办/P84 文档与代码互引管理（双向标记与漂移检测）.md:724`

- 原文：`gui/batch_simulator.py:5`（prose / plain / line_out_of_range）
- 解析到：`gacha_simulator/gui/batch_simulator.py`

**引用所在处（箭头为引用行）**

```
    722 | |---|---|---|
    723 | | 1 | 链接文本与链接目标被重复计数（去重键只按「行, 列」） | 同一「文件, 行」上出现多条引用的有 **58 行、贡献 180 条**；按行去重得 219 条，独立审查按「同一引用两半」配对得 271 条。口径不同，**虚增量级在 20% 到 35%** |
>>  724 | | 2 | 别名命中即返回，不看限定路径 | 写全路径的引用（如 `gui/batch_simulator.py:5`）会被静默改写成另一候选；且 `batch_simulator.py` 那条裁决的前提是那个空文件保持为空 |
    725 | | 3 | 抽样分层未含 `untracked` 与 `out_of_scope` | 23 条（占 6.7%）本次**零覆盖**，且统计行不显示「有类别从未抽到」 |
    726 | | 4 | 抽查稿落在扫描范围内（`04-收件箱/`） | **自污染已实测**：抽查稿自身贡献 105 条，总数 341 → 446，稿中写的复现命令不再产出那 20 条 |
```

**被引目标**：`gacha_simulator/gui/batch_simulator.py` 共 0 行，引用写的是 `gui/batch_simulator.py:5`，对不上，故无对应内容。文件末尾如下（line_out_of_range）：

```

```

- 判定（目标与范围是否就是文中所指的那一处）：____
- 备注：

### 20. `docs/02-待办/Ps04 资源定义自动生成按钮改造——从覆盖陷阱到汇总扫描.md:152`

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

