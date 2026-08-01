# CLAUDE.md

GachaStat 抽卡概率模拟与分析系统。版本号/Tab 列表由 C1 cron 自动同步。Harness 生态说明见第三层。

## 一、项目事实

**技术栈：** Python 3.10+ · PyQt6 · numpy · Plotly (WebEngine) · pytest+cov · binsreg (CCFF 2024) · PySDTest v0.0.21 (L2 随机占优可选依赖)
并行模拟：`multiprocessing.Pool` + worker initializer 模式

```bash
pip install -e ".[dev]"                              # CLI/headless 安装
pip install -e ".[gui,dev]"                          # GUI 安装（含 PyQt6）
python -m gacha_simulator.main                       # GUI
python -m gacha_simulator.cli -n 1000 -w 4 -s 42     # CLI
pytest --cov=gacha_simulator                         # 测试
```

**架构分层：**
```
gacha_simulator/
├── core/       # 引擎：池子、状态、策略、保底、GDR、溢出、分析算法（无 GUI 依赖）
├── service/    # GachaService + batch_simulator
├── gui/        # PyQt6 面板（Tab 列表见 main.py，C1 cron 自动同步）
│               # wheel_blocker.py — QApplication 全局事件过滤器，统一拦截
│               #   QComboBox/QAbstractSpinBox 滚轮并转发至外层 ScrollArea
├── config/     # 配置文件（TOML 格式，单文件 config.toml）
└── visualization/  # matplotlib 中文字体
```

**核心数据流：** `ConfigStore → SimulationEnvBuilder → SimulationEnv → GachaService(pools, strategy, stop_cond) → run_simulation(CompactCollector) → CompactResult → SharedResultCollector`。两种模式：紧凑 `CompactResult`（主流，O(1) 内存，`to_dict()`/`from_dict()` 序列化）/ 完整 `List[InfoVector]`（逐抽记录）。

**版本号：** 见 `gacha_simulator/_version.py`（Pride Versioning: MAJOR=PROUD / MINOR=DEFAULT / PATCH=SHAME）。C1 每日同步到 `技术栈.md`。

---

## 二、架构约束

### 无历史包袱原则（发布前生效）【P61 确立】

本项目**尚未上线**：`config.toml` 仅为示例与测试用文件，无真实用户数据、无历史结果文件。因此在 P61 落地及此后未发布阶段，允许：
- 一次性迁移配置格式（`[[pool]]` → `[[banner]]`），不维护新旧双路径
- 删除兼容机制（自动包装 / dual-write / 三路匹配 / 双键并存），代码只保留新形态
- 变更必须配「基线固化 + 等价对照」验证：迁移前用旧配置跑固定种子模拟，固化 CompactResult golden 快照，迁移后同种子重跑逐字段对比，保证行为等价

**保险措施**：发布状态标志见 `gacha_simulator/_version.py` 的 `RELEASED`。**正式上线 / 真实用户接入时，必须把 `RELEASED` 改为 `True`**，此后本原则立即失效：
- 禁止一次性迁移、删除兼容机制、破坏配置格式；所有变更默认「兼容优先」
- 每次会话（CLAUDE.md 自动加载）与编写/审查计划时检查 `RELEASED`：`False` 才可继续使用迁移方式，`True` 必须反向决策

### 策略 (`core/strategy.py` + `strategies/builtin/*.py`)

**P69 架构：** `STRATEGY_REGISTRY: Dict[str, StrategyMeta]`——`@register_strategy(key, display_name, *, params, internal)` 装饰器副作用自动注册。`StrategyMeta` dataclass 封装 `key`/`display_name`/`description`/`cls`/`params: List[ParamDescriptor]`/`internal`/`disabled`/`plugin_path`/`_invalid_state`。`create_strategy(key, params)` 数据驱动工厂——查 meta → `_invalid_state` 守卫 → 合并默认值 → `ParamDescriptor.validate()` → `cls(**resolved)`。`_validate_registry()` 模块导入时自动执行（5 项检查）。`strategy_type_to_key()` / `strategy_key_to_type()` 保留。

**ParamDescriptor 类族**（`core/param_descriptor.py`，零 Qt 依赖）：`FloatParam`/`IntParam`/`BoolParam`/`StrParam`/`StringListParam`/`PoolIntMapParam`——纯数据类，`validate()` 方法类型+范围校验。GUI 控件创建在 `gui/param_renderer.py`（未实现时由 `config_panel._on_strategy_type_changed` 直接实例化）。

**策略组织：** 8 个内置策略拆分至 `strategies/builtin/*.py`，与插件策略统一目录结构。框架核心（`Strategy` ABC / `StrategyContext` / `StrategyMeta` / `register_strategy` / `create_strategy`）保留在 `core/strategy.py`。`StrategyContext` 含新字段 `future_resource_gains`/`inter_pool_pity_links`/`time_discount`（均带默认值），由 `core/strategy_context_builder.py` 的 `build_strategy_context()` 集中构造。

**插件系统**（`core/strategy_loader.py`）：`load_plugin_strategies(plugin_dir)` 扫描 `strategies/*.py`，importlib 动态加载，装饰器自动注册。加载失败注册 `_invalid_state` 占位。`reload_plugin_strategy()` / `disable_plugin_strategy()` / `enable_plugin_strategy()` 热重载。GUI 插件管理面板（`gui/plugin_manager_panel.py`）提供启用/禁用/重新扫描。禁用状态持久化到 TOML `[plugins].disabled`。

**复合策略**（`core/strategy.py`，代码级 building block——不进入 TOML/GUI）：`DrawSegmentStrategy`（按抽数分段）/ `PriorityChainStrategy`（优先级降级链）/ `ConditionalStrategy`（lambda 条件分支）。三者均设 `_strategy_key = None` 哨兵。旧 `CompositeStrategy` 保留并发出 `DeprecationWarning`。

**P60 变更：** `acquired` 改为 `@property`，从 `state.acquired` 实时读取——单一真相源。**P56 新增：** `NonDrawAction`（`type='non_draw'`）——策略可返回非抽卡动作（`switch_epitomized_target` 切换定轨目标 / `cancel_epitomized_path` 取消定轨），由 `gacha_service._apply_non_draw()` 分发执行。

### 保底 (`core/pity.py`)

**类结构（P55+P56）：** `PityBehavior`（ABC）→ `CounterBasedBehavior`（ABC——`btype` 参数推导 `is_soft`/`is_hard`/`is_event_driven`，`_on_reset()` 钩子，`before_draw`/`after_draw` 生命周期）→ `SoftStepBehavior`（RLE deltas 驱动软保底）/ `HardPityBehavior`（阈值触发 100%）。事件驱动型（P56）：`RotatingBehavior`（纯净大小保底，guaranteed flag 二态翻转）/ `RotatingCRBehavior`（RotatingBehavior 子类，捕获明光——cr_counter + cr_state_probs + cr_base_rate）/ `TargetedBehavior`（定轨——selected_card 锁定 + fate_points 累积 + switch_allowed/switch_resets_progress 切换规则）。`SoftPityMixin` 混入软保底（委托 SoftStepBehavior deltas 引擎）→ `RotatingSoftBehavior` / `RotatingCRSoftBehavior` / `TargetedSoftBehavior`（各 ~5 行增量）。模块级 `_redistribute_scope()` 供 rotating/targeted 家族共用。**`BEHAVIOR_REGISTRY`** 注册 10 种保底类型：4 种 counter 驱动型（`soft_interval`/`soft_additive`/`soft_step`→`SoftStepBehavior`，`hard`→`HardPityBehavior`）+ 6 种事件驱动型（`rotating`→`RotatingBehavior` / `rotating_soft`→`RotatingSoftBehavior` / `rotating_cr`→`RotatingCRBehavior` / `rotating_cr_soft`→`RotatingCRSoftBehavior` / `targeted`→`TargetedBehavior` / `targeted_soft`→`TargetedSoftBehavior`）。`create_behavior(pdef, state)` 工厂——新格式（`PityDef` 扁平字段），含 P56 参数（`cr_counter_threshold`/`cr_base_rate`/`cr_state_probs`/`fate_threshold`/`switch_allowed`/`switch_resets_progress`/`soft_deltas`/`guaranteed_init`/`fate_points_init`）全参数传递。

**`PityEngine`（P55 新签名）：** `PityEngine(pool_specs, pity_defs: List[PityDef], state: PityState, rarity_rank)`——内部通过 `create_behavior()` 构造 behavior 实例，经 `_resolve_order(behaviors, rarity_rank)`（按稀有度层级→type 优先级排序）+ `_validate_behaviors()`（重名校验+scope 重叠 ConfigError）后存入 `_behavior_list`。旧签名 `PityEngine(pool_specs, pity_defs: Dict, behaviors: Dict)` 向后兼容。`PoolPitySpec` 含 `scope_cards`/`featured_cards`/`scope_slots`/`featured_slots`（featured/standard 独立槽位）；`compute_scope_mappings(pool)` 工厂函数预计算。池匹配使用 `fnmatch` 通配符。

**其他设施：** `PityState`——三层嵌套 namespace；`Counter`/`Flag` 遥控器；`DrawInfo`（frozen dataclass）抽卡静态事实；`PityContext` 管道载体；`LifecycleConfig`（frozen——`max_triggers`/`deactivate_on_early_hit`/`depends_on`）；`_build_pity_state_init()`——从 `PityDef` 注入 `counter_init`/`guaranteed_init`/`fate_points_init` 初始状态；`_expand_soft_to_deltas()`——`soft_interval`/`soft_additive` 语法糖 → deltas。

### GachaState (`core/state.py`)

dataclass——模拟状态一等公民。`resources`（资源）、`acquired`（卡牌持有，P60 新增）、`acquired_by_path`（P63 路径切片）、`real_time`、`total_actions`、`extra_state`。`pity_counters` 字段已删除。P60 新增方法：`add_card(card_id, path, overflow_bands, initial_counts) → Dict[str, float]` / `get_card_count(card_id)` / `total_holding(card_id, initial_counts)`。P63：`add_card()` 统一溢出管道——接受分段表，内部匹配区间并返回溢出资源（无规则返回 `{}`）；`clone()` 深拷贝 `acquired_by_path`。

### 溢出 (`core/overflow.py`)

P63 新建——`OverflowBand` dataclass（`min`/`max: int|None`/`resources`，`None`=∞）+ `match_overflow_bands(bands, n)` + `expand_sugar_to_bands(first, nth, excess)` 语法糖展开。分段表统一表示 CardAcquired 触发点的溢出规则，替代旧 `compute_bonus_resources()`（已删除）。

### GDR (`core/gdr.py` + `core/generalized_drop_rate.py`)

`UNIFIED_GDR_REGISTRY` 定义 21 种广义出率指标（含 P62 4 个可达变体）。两路计算：`compute_from_compact`（O(1)）/ `compute_from_history`（O(T)）。**P62 变更：** `GDRDefinition.needs_store: bool = False` 标志位——告知调用方该 GDR 需传入 `store` 方可正确计算（如 `_obtainable` 可达变体）。`filter_target_specs_by_obtainable(target_specs, store, final_time) -> Dict[str, int]` 公共函数——依据池子 `start_day ≤ final_time` 判定目标卡可达性，`store=None` 时保守回退返回原始 `target_specs`。4 个 `_obtainable` 后缀 GDR key（`target_achievement_obtainable` / `target_collection_obtainable` / `all_targets_obtainable` / `weighted_satisfaction_obtainable`）分母仅含模拟期间池子已开放的目标卡，排除不可达卡的虚降/永久惩罚。`compute_gdr_from_compact()` / `compute_gdr_from_cumulative()` / `compute_success_probability()` 均新增 `store=None` 参数并透传至 wrapper；`GDRCalculator.__init__` / `make_gdr_calculator()` 同理。`streaming.py` 累积快照新增 `pool_end_time` 字段供可达过滤使用。

**调用规范（强制）：** 必须用 `make_gdr_calculator(store, target_specs, gdr_key)` 构造 `GDRCalculator`——权重从 `ConfigStore` 自动提取。**禁止绕过直接调** `compute_gdr_from_compact`/`compute_success_probability`（权重易漏传、静默退化 1.0）。例外：`process_trace.py`/`per_pool_analysis.py` 通过 `**kwargs` 透传权重。**P60 变更：** `PityProgressAtT` 读取 `history[t].pity_state`（dict，非 PityState 对象）时，必须通过 `PityState.from_dict()` 反序列化后再使用 `ps.get(name, 'counter', 0)`——禁止直接对 dict 调用 3 参数 `get()`（TypeError）。

### 过程分析 (`core/process_trace.py` + `core/process_analysis.py`)

每池推断 7 种事件类型 + 池子成败（B 维度），4 种交叉统计（AA/BB/AB/BA），5 种事件组合模式。

### 流式分析 (`core/streaming.py`)

`SharedResultCollector` + `StreamingAnalyzer` 边模拟边提取边丢弃，内存 O(1)。

### 停止条件 · 并行模拟 · GUI · 配置

`STOP_CONDITION_REGISTRY` 注册 6 种条件 → `create_stop_condition()`。并行模拟用 `Pool(initializer=_wk_init)`，11 个全局变量注入子进程。GUI 用 QThread+Worker 模式，Plotly 图表通过 `ChartWebView` 渲染。配置文件 TOML 格式 → `config_toml.py` 读写（单一 `config.toml`）。**P55 变更：** `PityDef` 扁平化为 23 个独立类型字段（`scope`/`target_featured`/`deltas`/`threshold`/`counter_init`/`guaranteed_init`/`fate_points_init`/`soft_start`/`soft_end`/`soft_increment`/`reset`/`pools`/`max_triggers`/`deactivate_on_early_hit`/`depends_on` 等），旧 `params` dict 已移除；`PityConfig.counter_init` 移至每个 `PityDef.counter_init`。`_is_legacy_format()` + `_migrate_legacy_pity()` 自动迁移旧格式 TOML；`_pitydef_to_toml()` round-trip 写回；`_expand_soft_to_deltas()` 展开语法糖参数。`create_behavior()` 完整传递 lifecycle/reset/target_featured。`rarity_rank` 从 `ConfigStore.[rarities].ranks` 解析（小写归一化），传递至 PityEngine 和 `_resolve_order`。

### 并行模拟入口（强制）

所有批量/并行模拟必须通过 `service/batch_simulator.py` 的 `run_batch_parallel()` 执行。
禁止直接使用 `multiprocessing.Pool` + `GachaService` 的组合。
CLI / GUI / 脚本 / 测试均通过此统一入口。

### 扩展指南

| 扩展 | 入口 |
|------|------|
| 新 GDR | `core/gdr.py` + `UNIFIED_GDR_REGISTRY` 注册 `GDRDefinition` |
| 新溢出规则 | `core/overflow.py` → `CardDefEntry.overflow_bands` / `[rarity_defaults]` TOML 段 / GUI「满突溢出」标签页 |
| 新策略 | `strategies/builtin/` 或 `strategies/` 插件目录 —— `@register_strategy` 装饰器 + `Strategy` ABC |
| 新停止条件 | `core/stop_condition.py` + `STOP_CONDITION_REGISTRY` 注册 |
| 新面板 | `gui/` + `MainWindow._setup_ui()` 注册 Tab |
| 新保底行为 | `core/pity.py` → `BEHAVIOR_REGISTRY` 注册 type→class+params 元数据 + 实现 `CounterBasedBehavior` 子类（counter 驱动）或 `PityBehavior` 子类（事件驱动） |
| 新卡片维度 | `CardDefEntry.tags`（单值）/`CardDefEntry.list_tags`（多值）——TOML 中 `[card.tags]` 加一行即可，无需改代码（P65） |
| 新配置项 | `ConfigStore` → `config_toml.py` → `config_panel.py` → `SimulationEnvBuilder` |
| 新脆弱性分析方法 | `core/vulnerability.py` 中新增私有函数（如新的分箱策略或推断方法），通过 `_fit_vulnerability_pava` 主入口集成 |
| 新随机占优检验 | `core/comparison_analyzer.py` → `dd_bootstrap_test_v2()` + `compute_dominance_matrix_v2()` → `compute_dominance_matrix()` 派发器（当前：v2=PySDTest Donald-Hsu 2016 选择性重中心化 / v1=等式中心化 Bootstrap） |

---

## 三、Harness 使用指南

### Hooks（9 个，自动触发）

| # | 触发 | 行为 | 阻塞 |
|---|------|------|------|
| H1 | SessionStart | 注入 git log + P0 + eval 报告 + checkpoint | 永不 |
| H2 | 每次 Bash | 拦截 `rm -rf /`/`git push --force main` | exit 2 |
| H3 | git commit | Conventional Commits 格式 (`feat:`/`fix:`) | exit 2 |
| H4 | Write/Edit 后 | 自动追加变更日志到 05-笔记 | 永不 |
| H5 | git commit | 版本号/Tab 一致性校验 | exit 2 |
| H6 | Stop | >7 天未更新文档提醒 | 永不 |
| H7 | git commit | `ruff check` + 目录边界（ms 级） | exit 2 |
| H8 | PreCompact | 保存 checkpoint（worktree 感知） | 永不 |
| H9 | git push | `pytest -q`（min 级） | exit 2 |

**被阻止时：** H3→修正 commit message · H5→更新技术栈.md · H7→`ruff check --fix` · H9→修复失败测试
**紧急绕过：** 创建 `HARNESS_BYPASS` 文件 → H7/H9 降级为 warn-only（C4 30min 内自动删除）

### Cron Agents（6 个） + Evaluator（1 个）

| Agent | 频率 | 产出 |
|-------|------|------|
| C1 doc-syncer | 5:07 | 版本/Tab 同步 + `[auto]` commit |
| C2 matrix-syncer | 5:37 | 矩阵偏差 → `04-收件箱/matrix-drift-*.md` |
| C3 weekly-writer | 9:07 | 周一：本周聚焦 + `[auto]` commit |
| C4 stale-detector | 6:07 | 腐烂检测 + 收件箱清理 + BYPASS 过期删除 |
| C5 quality-reviewer | 10:07 | 周一：代码质量 → `04-收件箱/quality-*.md` |
| C6 heartbeat-monitor | 8:07 | cron 静默失败警报 |
| **E1** deep-evaluator | 每 6h | 独立审查 → `04-收件箱/eval-*.md`（SessionStart 自动注入） |

### Planner

`/plan <种子>` → AI 搜索影响面 → 创建计划文件（含 META 头）→ 注册到模块状态矩阵

### 计划审查工作流 (P38)

`/workflow plan-review "{计划文件路径}"` → 五阶段对抗验证流水线：
阶段 0 分类 → 阶段 1 扇出影响面 → 阶段 2 对抗循环 (Finder→Fixer→Verifier → 收敛) → 阶段 3 可行性门控 (6 项检查) → 阶段 4 代码审计

产出 `04-收件箱/peer-review-{plan}-{date}.md`，H1 SessionStart 自动注入。E1 交叉验证 peer-review 发现与 eval 发现的一致性。

### 故障排查

commit 被 H7 阻止 → `ruff check` 修复 · push 被 H9 阻止 → `pytest -q` 修复 · cron 静默失败 → 检查 `heartbeat-alert-*.md`（CronCreate 7 天过期需重新注册） · worktree hooks 不触发 → 已知限制（合并回主分支时二次检查）

### 文档体系

三文件制：`模块.md` + `理论.md` + `05-笔记.md`（H4 自动维护）。计划文件含 META 头，全局约定见 `docs/00-meta/全局约定.md`，活跃计划见 `模块状态矩阵.md`。

### 文件删除规则

**禁止擅自删除文件。** 需删除时：
- **文档**（`.md`、`.txt` 等）→ 移入 `docs/03-归档/` 归档文件夹
- **代码及其他文件** → 移入项目根目录 `.recycle_bin/` 垃圾桶文件夹

不得直接 `rm` / `rm -rf` 删除任何文件，除非用户明确要求。
