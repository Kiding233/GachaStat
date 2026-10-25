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
├── core/       # 引擎：池子、状态、策略、保底、GDR、溢出、里程碑、分析算法（无 GUI 依赖）
│               #   milestone.py — 累抽奖励引擎（P58，独立于 PityEngine，旁路注入）
├── service/    # GachaService + batch_simulator
├── gui/        # PyQt6 面板（Tab 列表见 main.py，C1 cron 自动同步）
│               # wheel_blocker.py — QApplication 全局事件过滤器，统一拦截
│               #   QComboBox/QAbstractSpinBox 滚轮并转发至外层 ScrollArea
├── config/     # 配置文件（TOML 格式，单文件 config.toml）
└── visualization/  # matplotlib 中文字体

benchmarks/     # 开发侧性能测量资产（P83）——**不进发布产物**，定位同 py-spy
                #   perf/ 测量内核（plan/record/report/`__main__` 薄壳）
                #   perf/adapters/ 四路径适配器：cli / gui-qt / webui / inline
                #   perf/profilers/ stage.py + cprofile.py（worker 侧注入）+ pyspy.py
                #   测试不在本树内，在 tests/benchmarks/；硬规则见 benchmarks/README.md
```

**核心数据流：** `ConfigStore → SimulationEnvBuilder → SimulationEnv → GachaService(banners, strategy, stop_cond) → run_simulation(CompactCollector) → CompactResult → SharedResultCollector`。单一模式：`CompactResult`（O(1) 内存，`to_dict()`/`from_dict()` 序列化）；逐抽明细路径已由 P81（2026-09-17）删除。**P61：** 配置单位为 Banner（`[[banner]]`，内含多 Pool + Lifecycle 规则），`store.pools` 为只读展平视图；GachaService 构造桥对 `List[Pool]`/`List[Banner]` 双型收纳为运行时 `self._banners`；`env.pools` 承载 `List[Banner]`（深拷贝隔离跨模拟状态）。

**版本号：** 见 `gacha_simulator/_version.py`（Pride Versioning: MAJOR=PROUD / MINOR=DEFAULT / PATCH=SHAME）。C1 每日同步到 `技术栈.md`。

---

## 二、架构约束

### 精确建模原则（机制模拟的唯一验收标准）

**本项目做的是机制的精确建模，不是机制的近似再现。在机制模拟上只接受等价实现，不接受近似实现。**

- **判据**：一个机制被判定为「已支持」，当且仅当存在一种配置或实现，其行为与真实机制**逐项等价**（概率行为、状态转移、边界条件三者都算）。数值上接近、语义上打折、或只在特定参数区间成立，都不算已支持。
- **近似的处置**：若某机制当前只能用近似表达，必须**显式登记为缺口**（手册中以「近似可配」「语义打折」等字样标注，如 G15 pjsk 加权抽数），并按既有缺口登记渠道处理（手册各节的「功能缺口」表 + §21 总缺口汇总 + 计划登记到模块状态矩阵），不得计入「已覆盖」。
- **推论**：已登记的近似条目是**待消除的债务**，不是可接受的终态；遇到「只能近似表达」的场合，默认登记缺口，而非交付近似。
- **与「无历史包袱原则」的分工**：后者管**变更方式**（未发布期允许一次性迁移与破坏性变更），本条管**目标形态**（最终交付必须是等价实现）。近似不因「反正是模拟」而被接受。

### 可达性不作为免责理由（2026-10-15 用户裁定）

**判定一个缺陷、缺口或行为差异的严重度时，「随包 `config.toml` 跑不到 / 默认配置不可达 / 当前无生产调用 / 只在构造型配置下出现」不构成降级或免修的理由。用户会配置任意语义合理的配置。**

- **判据**：严重度按「**是否存在一个语义合理的配置能触发它**」判，**不**按「随包配置是否触发」判。
- **允许的用途**：上述事实**可以登记为现状**（说明当前是否已被触发、影响谁），但**不得**用作「不必修 / 只登记即可 / 低优先级」的依据。
- **文档同理**：「本配置当前不存在」「手册无此配置」「该路径今日不可达」**不是**缺口可以不闭合的理由。一个能力只要**语义上被所建模的机制需要**，就必须实现，或**显式登记为缺口**（与精确建模原则同源）。
- **推论（审查与自查都要照此问）**：判断一处行为差异是否为缺陷时，**先问「有没有一个语义合理的配置能暴露它」**，而不是「我们的样例配置能不能碰到」。
- **对既有登记的效力**：本原则**追溯适用**：此前以「默认配置不可达」为由降级或只登记的条目，须按本原则**重新定级**（该修的修、该排期的排期），不得沿用旧的免责结论。

### 无历史包袱原则（发布前生效）

本项目**尚未上线**：`config.toml` 仅为示例与测试用文件，无真实用户数据、无历史结果文件。因此在未发布阶段，允许：
- 一次性迁移配置格式，不维护新旧双路径
- 删除兼容机制，代码只保留新形态
- 变更必须配「基线固化 + 等价对照」验证：迁移前用旧配置跑固定种子模拟，固化 CompactResult golden 快照，迁移后同种子重跑逐字段对比，保证行为等价

**保险措施**：发布状态标志见 `gacha_simulator/_version.py` 的 `RELEASED`。**正式上线 / 真实用户接入时，必须把 `RELEASED` 改为 `True`**，此后本原则立即失效：
- 禁止一次性迁移、删除兼容机制、破坏配置格式；所有变更默认「兼容优先」
- 每次会话（CLAUDE.md 自动加载）与编写/审查计划时检查 `RELEASED`：`False` 才可继续使用迁移方式，`True` 必须反向决策

### 独立审查原则（编写与审查分离）

**核心规则：编写者不得自审。** 主 agent 编写或修改的文件，在正式审核/检查类任务（代码审查、计划审查、质量评审、提交前核查等）中，必须派出子 agent 独立检查，不得由主 agent 自查充当结论。

- **验证与审查分离**：开发中的功能验证（跑测试、调试、确认行为）属主 agent 职责，不在此列；本原则约束的是对产物作正式检查并作为结论的环节
- **子 agent 独立性**：子 agent 不携带主 agent 会话上下文，以文件内容与代码库为准独立判断，允许质疑既有决策
- **提示词边界**：主 agent 只提供审查范围与检查清单，不得在提示词中引导子 agent 得出特定结论，否则独立性退化为橡皮图章
- **豁免**：一行 typo、纯文档表述修改等极简单改动可不派子 agent，但仍须通过既有 hook 门控（H7 ruff / H5 一致性校验）
- **理由**：编写者自查存在固有盲区（编写时的心智模型与意图偏差），独立第三方视角是审查有效性的前提；E1 独立评估、P38 五阶段对抗审查、peer-review 工作流均基于同一原则

### 决策报告原则

需要用户决策时，报告必须「自包含」，用户无需翻阅代码或文档即可理解并做决定。按理解路径组织：先铺理解前提，再诊断现状，最后落到决策结论。简单决策（yes/no、小选择）压缩为 1-2 句；复杂决策（方案权衡、边界裁决）完整覆盖下列要素：

1. **决策预告**：开头一句话声明需要决策，避免误读为普通说明
2. **背景**（问题无法自明定位时）：问题出现在哪个文件/场景
3. **概念解释**（涉及代码库内部机制或冷僻概念时）：按下方「解释规范」执行
4. **设计意图**（涉及某概念/行为时）：该机制原始设计意图，作为「预期行为」的依据
5. **现状 vs 预期**（涉及边界/异常时）：正常情况下的预期行为 + 当前实际行为 + 差异
6. **可能原因**（必须）：成因假设；不适用时明确说明「不适用」及原因
7. **问题**：完整描述要决定什么
8. **选项与推荐**：可行选项 + 推荐项及理由

**解释规范（分级）：**
- **决策依据必解释**：选项判断所依赖的机制/术语，首次出现必须让用户理解其行为，不得仅抛名字
- **相关性分级**：与决策无关或用户已熟悉的引用可省略解释；拿不准熟悉度时倾向解释
- **聚合解释**：涉及相互关联的一组机制时，用一段话整体说明关系与本次涉及的部分，不必逐个解释
- **写作格式**：短解释用括号（如 `_redistribute_scope()`（rotating/targeted 保底家族共用的范围重分配函数））；需完整句展开时用冒号（如 `_redistribute_scope()`：它负责把超范围外的保底计数移交给下一个池）

反例（决策依据裸抛名字）：「此问题涉及 `_redistribute_scope()` 的调用时机」
正例：「此问题涉及 `_redistribute_scope()`（rotating/targeted 保底家族共用的范围重分配函数），它与本次决策的关系是……」

### 策略 (`core/strategy.py` + `strategies/builtin/*.py`)

**P69 架构：** `STRATEGY_REGISTRY: Dict[str, StrategyMeta]`——`@register_strategy(key, display_name, *, params, internal)` 装饰器副作用自动注册。`StrategyMeta` dataclass 封装 `key`/`display_name`/`description`/`cls`/`params: List[ParamDescriptor]`/`internal`/`disabled`/`plugin_path`/`_invalid_state`。`create_strategy(key, params)` 数据驱动工厂——查 meta → `_invalid_state` 守卫 → 合并默认值 → `ParamDescriptor.validate()` → `cls(**resolved)`。`_validate_registry()` 模块导入时自动执行（5 项检查）。`strategy_type_to_key()` / `strategy_key_to_type()` 保留。

**ParamDescriptor 类族**（`core/param_descriptor.py`，零 Qt 依赖）：`FloatParam`/`IntParam`/`BoolParam`/`StrParam`/`StringListParam`/`PoolIntMapParam`——纯数据类，`validate()` 方法类型+范围校验。GUI 控件创建在 `gui/param_renderer.py`（未实现时由 `config_panel._on_strategy_type_changed` 直接实例化）。

**策略组织：** 8 个内置策略拆分至 `strategies/builtin/*.py`，与插件策略统一目录结构。框架核心（`Strategy` ABC / `StrategyContext` / `StrategyMeta` / `register_strategy` / `create_strategy`）保留在 `core/strategy.py`。`StrategyContext` 含新字段 `future_resource_gains`/`inter_pool_pity_links`/`time_discount`（均带默认值），由 `core/strategy_context_builder.py` 的 `build_strategy_context()` 集中构造。

**插件系统**（`core/strategy_loader.py`）：`load_plugin_strategies(plugin_dir)` 扫描 `strategies/*.py`，importlib 动态加载，装饰器自动注册。加载失败注册 `_invalid_state` 占位。`disable_plugin_strategy()` / `enable_plugin_strategy()` 启停；改插件文件后用「重新扫描」重载（`load_plugin_strategies` 每次新建模块并 `exec_module`，重扫即重载，故不另设单插件重载接口）。GUI 插件管理面板（`gui/plugin_manager_panel.py`）提供启用/禁用/重新扫描。禁用状态持久化到 TOML `[plugins].disabled`。

**复合策略**（`core/strategy.py`，代码级 building block——不进入 TOML/GUI）：`DrawSegmentStrategy`（按抽数分段）/ `PriorityChainStrategy`（优先级降级链）/ `ConditionalStrategy`（lambda 条件分支）。三者均设 `_strategy_key = None` 哨兵。旧 `CompositeStrategy` 已于 P81 批 B（2026-09-17）删除（全库零引用，`_strategy_key = None` 故无数据驱动引用）。

**枯竭态契约（P79）：** 策略在「不再有任何想做的事」时必须返回**推进时间**的等待，不得返回 `WaitAction(duration=0)`（后者让 `real_time` 冻结、时间型停止条件永远够不着，循环只能烧满 `max_iterations`）。统一入口是 `core/strategy.py` 的 `next_event_wait(ctx) -> float`（86400 秒硬上限），调用点一律写 `return WaitAction(duration=next_event_wait(ctx))`——helper 返回时长而非 Action，直接返回 float 会让动作分发三路 `isinstance` 全部落空并抛 `ValueError`。

**P60 变更：** `acquired` 改为 `@property`，从 `state.acquired` 实时读取——单一真相源。**P56 新增：** `NonDrawAction`（`type='non_draw'`）——策略可返回非抽卡动作（`switch_epitomized_target` 切换定轨目标 / `cancel_epitomized_path` 取消定轨），由 `gacha_service._apply_non_draw()` 分发执行。

### 保底 (`core/pity.py`)

**P64 架构（Tracker + Modifier + Lifecycle 三元组）：** `Pity(PityBehavior)`（`core/pity.py`）是**统一骨架**，每个保底由三族零件组装而成；它**不继承** `CounterBasedBehavior`，三个分类标志 `is_soft`/`is_hard`/`is_event_driven` 由 `btype` 经 `pity_primitives` 的模块级常量 `_SOFT_TYPES`/`_HARD_TYPES`/`_EVENT_DRIVEN_TYPES` 推导。三族零件分居三个新模块：`core/pity_tracker.py`（`Tracker` 协议 + `CounterTracker`/`FlagTracker`/`StreakTracker`/`FateTracker`/`NamespaceTracker`；`Lifecycle` 协议 + `AlwaysActive`/`FiniteActive`/`DependentActive`/`DependentFiniteActive`）、`core/pity_modifier.py`（`Modifier` 协议 + `HardModifier`/`SoftModifier`/`RotatingModifier`/`NonFeaturedModifier`/`SelectedModifier`/`NotOwnedModifier`）、`core/pity_primitives.py`（叶子原语层：`DrawInfo`/`PityContext`/`Counter`/`Flag`/`LifecycleConfig`/`PityState` + 三个类型集合常量；`pity.py` 保留 re-export，既有导入路径不变）。`Pity` 构造期顺序不可颠倒：收集零件命名空间 → 汇总三族声明键集 `_declared_keys` → `Lifecycle.initialize()` 写初始 `_active` → 建默认 view 与命名空间 view → 按 truthy 规则消费 `flags`/`counters`。

**`BEHAVIOR_REGISTRY`（13 条目）：** 每条目为 `class: None` + `preset` 工厂函数（`preset(pdef) -> dict`，键集恰为 `trackers`/`modifiers`/`lifecycle` + 可选 `flags`/`counters`）。10 个旧行为类已**从注册表与公共导出面退役**（`core/__init__.py` 的 re-export 同批双删，AUDIT-BREAK-8），但其**类本体仍保留在 `pity.py` 直到发布前一次性移除**（GATE-5 末条；`PoolPitySpec` 的槽位字段与 `compute_scope_mappings` 减量按 ISSUE-901 推迟到同一 commit）。条目与 preset 的对应：`soft_interval`/`soft_additive`/`soft_step` 三条共用 `_preset_soft_step`；`hard`→`_preset_hard`；`rotating`→`_preset_rotating`；`rotating_inverse`→`_preset_rotating_inverse`（G1 幻塔「连中必歪」，S6a 新增）；`rotating_soft`→`_preset_rotating_soft`；`rotating_cr`→`_preset_rotating_cr`；`rotating_cr_soft`→`_preset_rotating_cr_soft`；`targeted`→`_preset_targeted`；`targeted_soft`→`_preset_targeted_soft`。字典书写顺序 = GUI 下拉顺序（S6a 起 `_PITY_TYPES` 由它生成）。`_validate_registry()` 导入期自检**只判 `preset` 可调用**（既不调用 preset、也不校验其返回键集；未知键查多 / 缺 `lifecycle` 查漏两道校验在 `create_behavior` 运行期）。

**`create_behavior(pdef, state, **extra)`（双路径）：** 条目含 `preset` 则走 preset 分支：`preset(pdef)` 取 dict，两道互补校验（未知键 / 缺 `lifecycle`）后**按名取键**构造 `Pity`（禁止 `**built` 直展开）；否则走**旧类兼容分支**（`cls(**params)`，保留到发布前）。`target_featured=true` 配 `soft_*` 类型在本函数内类型级硬拒（裁决 7B，2026-10-05）。

**`PityEngine(pool_specs, pity_defs: List[PityDef], rarity_rank=None, state=None, invariants=None)`：** 逐条 `create_behavior()` 构造，**构造失败即抛 `ConfigError`**（S4-5 起不再 `logger.warning` 后跳过，避免「配置里写了保底、运行时该保底不存在且无可见报错」）；随后 `_resolve_order(behaviors, rarity_rank)` 排序（排序键 `(稀有度 rank, -priority, _BTYPE_ORDER, name)`，`priority` **数值大者先执行**，S6b 定）+ `_validate_behaviors()` 校验（重名校验 + scope 重叠 `ConfigError`）。**排序结果已接入概率管道（P82-1）**：`__init__` 预计算 `self._pool_order`（排序在池成员上的子序），三个调度入口经 `get_behaviors_for_pool()` 消费；`PoolPitySpec.pity_names` 保持 TOML 定义顺序不动（`banner.draw_pity_names` 依赖它进 golden 快照）。旧签名 `PityEngine(pool_specs, pity_defs: Dict, behaviors: Dict)` 已于 P81 A3（2026-09-17）删除（含 `behaviors` 形参与 `_legacy_mode` 分支）。`PoolPitySpec` 含 `scope_cards`/`featured_cards`/`scope_slots`/`featured_slots`/`card_to_slot`；`compute_scope_mappings(pool)` 工厂函数预计算。池匹配使用 `fnmatch` 通配符。

**其他设施：** `PityState` 为三层嵌套 namespace 容器；`Counter`/`Flag` 遥控器；`DrawInfo`（frozen dataclass）抽卡静态事实；`PityContext` 管道载体；`LifecycleConfig`（frozen：`deactivate_on_early_hit`/`depends_on`）；`build_lifecycle(pdef)`：生命周期字段 → Lifecycle 对象的唯一转换点（ISSUE-301）；`_build_pity_state_init()`：从 `PityDef` 注入 `counter_init`/`guaranteed_init`/`fate_points_init` 初始状态；`_expand_soft_to_deltas()`：`soft_interval`/`soft_additive` 语法糖 → deltas。

**P75 `_rebind_state` 纪律（强制，四条）：** `PityEngine` 每次调度（`before_draw`/`after_draw`/`get_probabilities`）首行调用 `_rebind_state(state)`，把 behaviors 的 Counter/Flag 重绑到 per-call state，**纯重定向不复制旧值**，初始值完全由 `env.pity_state_init`（阶段 3 完整快照，engine 构造后取 `_state.to_dict()`）承载；绑定对象不同则计数器写入错账本、保底快照恒空（P75 根因）。**新增保底行为/查询时四条纪律：** 1) **新 behavior 必须实现 `_rebind_state`**（或确认走基类空实现；子类特有 Counter/Flag 经 `_on_rebind_state` 覆写，不得因「无覆写者」删除该调用）；2) **新只读查询不得依赖未 rebind 的 `self._state`**（无 `state` 参数的只读查询须纳入 ISSUE-104 豁免清单或改走引擎级 rebind，不得默认豁免）；3) **所有带 `state` 参数的公开入口方法必须在首行 rebind，且先于任何 spec=None 早退**；4) **`per-call state` 必须由 `env.pity_state_init` 快照派生或含构造期 `_active`/`guaranteed` 等初始 Flag 键**，否则 `_active` 读默认 False、计数型保底静默失效。P64 下同一条纪律落到三族零件的 `rebind`（`Pity._rebind_state` 对每个零件**无条件**调用）：Tracker / Modifier 是 `rebind(state, name)` **两实参**，Lifecycle 是 `rebind(state, name, namespaces)` **三实参**（`pity_tracker.py` 侧标 ISSUE-917：漏传即 `X_soft._active` 跨场不重绑、仍指上一场 state）。

**P64 S8 / S9 的增补（2026-10）。** 概率管道已由「卡级 → 槽位级 → 卡级」的四次往返改为**卡级增量一次到底**：`Modifier` 的唯一接口是 `compute_delta(view, dist, ctx) -> Optional[Dict[str, float]]`（三参定稿），归一化由框架的 `_apply_delta(dist, d)` 统一做，转移族共用助手 `transfer_linear(dist, A, Q, amount, shape, weights)`；这两个函数住**叶子层** `core/pity_primitives.py`（`pity.py` 只 re-export，§3.1.6 的单向依赖）。`aggregate_probs_by_rarity` 与 `infer_rarity_from_spec` 已删除；`banner.py` 改卡级直传。状态可见性两侧分工：`StateView`（`pity.py`）限定 Modifier **只读自身命名空间**（关闭跨保底读），`SimView`（`core/state.py`，只暴露 `owns(card_id)`，含初始持有）经 `PityContext.sim`（**非 Optional**，三处调度入口必填参）向保底暴露模拟级只读事实。`core/invariants.py` 的 `InvariantChecker` 可开关地做四层运行时校验（生产默认 `None`，零开销）。`BEHAVIOR_REGISTRY` 另有两条 G3 排除已获得型（`hard_exclude_owned_skip` / `hard_exclude_owned_any`，差别只在「全部 UP 均已拥有」时的两形态）。**策略侧的「是否已拥有」判据**一律取 `ctx.state.total_holding(card_id)`（含初始持有），`ctx.acquired`（P60 语义：本次模拟**新获得**）不得用于该判据。

### GachaState (`core/state.py`)

dataclass——模拟状态一等公民。`resources`（资源）、`acquired`（卡牌持有，P60 新增）、`acquired_by_path`（P63 路径切片）、`real_time`、`total_actions`、`extra_state`。`pity_counters` 字段已删除。P60 新增方法：`add_card(card_id, path, overflow_bands) → Dict[str, float]` / `get_card_count(card_id)` / `total_holding(card_id)`（`initial_counts` 自 P64 S9-2 起是 `GachaState` 的**字段**，两个方法均不再收该形参）。P63：`add_card()` 统一溢出管道——接受分段表，内部匹配区间并返回溢出资源（无规则返回 `{}`）；`clone()` 深拷贝 `acquired_by_path`。P61：`get_available_pools()` 方法已删除——池子可用性由 Banner 级 `is_available(real_time)` 判定（时间窗口 + lifecycle 激活，见扩展指南「新 Banner 生命周期规则」）。

### 溢出 (`core/overflow.py`)

P63 新建——`OverflowBand` dataclass（`min`/`max: int|None`/`resources`，`None`=∞）+ `match_overflow_bands(bands, n)` + `expand_sugar_to_bands(first, nth, excess)` 语法糖展开。分段表统一表示 CardAcquired 触发点的溢出规则，替代旧 `compute_bonus_resources()`（已删除）。

### GDR (`core/gdr.py`)

`UNIFIED_GDR_REGISTRY` 定义 21 种广义出率指标（含 P62 4 个可达变体）。单路计算：`compute_from_compact`（O(1)）。**P81（2026-09-17）** 删除了 `compute_from_history`（O(T)，逐抽遍历 `InfoVector`）字段与其 22 个函数族，理由是该路径的输入类型随 InfoVector 明细路径一并消失。**P62 变更：** `GDRDefinition.needs_store: bool = False` 标志位——告知调用方该 GDR 需传入 `store` 方可正确计算（如 `_obtainable` 可达变体）。`filter_target_specs_by_obtainable(target_specs, store, final_time) -> Dict[str, int]` 公共函数——依据池子开放时间判定目标卡可达性，`store=None` 时保守回退返回原始 `target_specs`。**P61 变更（ISSUE-009/310）：** 可达判定数据源由 `store.pools` 的 `start_day`（天）改为 `store.banner.banners` 的 `available_from`（秒）——比较单位由天修正为秒（晚开池早停场景可达性收严，ISSUE-307），`pool_start` 键为全限定 `{banner_id}.{pool_id}`（与 `card_defs[].pools` 同键空间）；GDR 转化效率白名单由 `pool_type in ('角色','武器','')` 改为推导属性 `output == 'card' and random`（§3.13.1，类型字段已退役）。4 个 `_obtainable` 后缀 GDR key（`target_achievement_obtainable` / `target_collection_obtainable` / `all_targets_obtainable` / `weighted_satisfaction_obtainable`）分母仅含模拟期间池子已开放的目标卡，排除不可达卡的虚降/永久惩罚。`compute_gdr_from_compact()` / `compute_gdr_from_cumulative()` / `compute_success_probability()` 均新增 `store=None` 参数并透传至 wrapper；`GDRCalculator.__init__` / `make_gdr_calculator()` 同理。`streaming.py` 累积快照新增 `pool_end_time` 字段供可达过滤使用。

**调用规范（强制）：** 必须用 `make_gdr_calculator(store, target_specs, gdr_key)` 构造 `GDRCalculator`——权重从 `ConfigStore` 自动提取。**禁止绕过直接调** `compute_gdr_from_compact`/`compute_success_probability`（权重易漏传、静默退化 1.0）。例外：`process_trace.py`/`per_pool_analysis.py` 通过 `**kwargs` 透传权重。**P60 变更：** `PityProgressAtT` 读取 `history[t].pity_state`（dict，非 PityState 对象）时，必须通过 `PityState.from_dict()` 反序列化后再使用 `ps.get(name, 'counter', 0)`——禁止直接对 dict 调用 3 参数 `get()`（TypeError）。

### 过程分析 (`core/process_trace.py` + `core/process_analysis.py`)

每池推断 7 种事件类型 + 池子成败（B 维度），4 种交叉统计（AA/BB/AB/BA），5 种事件组合模式。

### 流式分析 (`core/streaming.py`)

`SharedResultCollector` + `StreamingAnalyzer` 边模拟边提取边丢弃，内存 O(1)。

### 停止条件 · 并行模拟 · GUI · 配置

`STOP_CONDITION_REGISTRY` 注册 6 种条件 → `create_stop_condition()`。并行模拟用 `Pool(initializer=_wk_init)`，11 个全局变量注入子进程。GUI 用 QThread+Worker 模式，Plotly 图表通过 `ChartWebView` 渲染。配置文件 TOML 格式 → `config_toml.py` 读写（单一 `config.toml`）。**P55 变更：** `PityDef` 扁平化为 26 个独立类型字段（`scope`/`target_featured`/`deltas`/`threshold`/`counter_init`/`guaranteed_init`/`fate_points_init`/`selected_card_init`/`soft_start`/`soft_end`/`soft_increment`/`soft_deltas`/`cr_*`/`fate_threshold`/`switch_*`/`reset`/`pools`/`deactivate_on_early_hit`/`depends_on`/`max_triggers`/`priority`，字段数以 `dataclasses.fields(PityDef)` 为准），旧 `params` dict 已移除；`PityConfig.counter_init` 移至每个 `PityDef.counter_init`。旧格式 TOML 由 `_check_pity_format()` 显式拒绝（抛 `ConfigError` 提示手工迁移；P81 B11 2026-09-17 起不再自动迁移——原 `_is_legacy_format()` + `_migrate_legacy_pity()` 已删，因其把 legacy 值原样保留会使保底计数器永不重置）；`_pitydef_to_toml()` round-trip 写回；`_expand_soft_to_deltas()` 展开语法糖参数。P64 起 `lifecycle`/`reset`/`target_featured` 三者由 preset 工厂从 `PityDef` 字段直接转换（`build_lifecycle(pdef)` / `CounterTracker(reset_on=pdef.reset or scope)` / `_target_of(pdef)`），**preset 分支**不再经 `create_behavior` 的参数组装段（旧 `lifecycle_kwargs` 段已随 S4-4 删除）；**旧类兼容分支保留 `reset` 与 `target_featured` 两处的组装**（`pity.py:1519-1523`，注释自标「旧类分支专属」），随发布前一次性移除旧类时一并删除；**`PityDef.scope` 已于 2026-09-16 接线**：`create_behavior()` 优先取 `PityDef.scope`，缺省回退 `BEHAVIOR_REGISTRY` 条目的 `default_scope`（13 条目全为 `"ssr"`），跨稀有度保底自此可配置；配套两道校验，`config_toml._build_pity()` 对 scope 做白名单校验（不在 `[rarities].ranks` 内即 ConfigError，防「scope 写错致保底静默失效」），`PityEngine.__init__` 在构造 behavior 前做重名校验（抛 ValueError，补上「TOML 层已有、直构 PityDef 路径缺失」的缺口）。`rarity_rank` 从 `ConfigStore.[rarities].ranks` 解析（小写归一化），传递至 PityEngine 和 `_resolve_order`。

### 并行模拟入口（强制）

所有批量/并行模拟必须通过 `service/batch_simulator.py` 的 `run_batch_parallel()` 执行。
禁止直接使用 `multiprocessing.Pool` + `GachaService` 的组合。
CLI / GUI / 脚本 / 测试均通过此统一入口。

### 扩展指南

| 扩展 | 入口 |
|------|------|
| 新 GDR | `core/gdr.py` + `UNIFIED_GDR_REGISTRY` 注册 `GDRDefinition` |
| 新溢出规则 | `core/overflow.py` → `CardDefEntry.overflow_bands` / `[rarity_defaults]` TOML 段 / GUI「满突溢出」标签页 |
| 新 Banner 生命周期规则 | `[[banner.lifecycle]]` TOML 段（P61）——`condition`（pool_draws/banner_draws/card_obtained/pool_exhausted/time_window）+ `action`（switch_to/exhaust_banner）；`card_obtained` 的匹配值存 `pool` 字段（`match`=card_id/rarity）；`time_window` 的 `at` 为秒（UI/TOML 层以天书写，解析边界 `*DAY`） |
| 新策略 | `strategies/builtin/` 或 `strategies/` 插件目录 —— `@register_strategy` 装饰器 + `Strategy` ABC；枯竭态须返回推进时间的等待，用 `core/strategy.py` 的 `next_event_wait(ctx)`（见「策略」一节的枯竭态契约） |
| 新停止条件 | ① 在 `core/stop_condition.py` 实现条件类（`check(state, stats)` + `description()`；`stats` 必填，无 `history` 形参）并在 `STOP_CONDITION_REGISTRY` 注册条目——`params` 为 `List[ParamDescriptor]`（`core/param_descriptor.py`）② 声明它在 `[stop_condition]` TOML 段中的嵌套形态（复合节点带 `mode`+`conditions`、否定节点 `mode='not'` 恰带一子节点、叶子节点带 `type`+平铺参数），工厂 `create_stop_condition(tree)` 按「`conditions` → `mode` → `type`」分派 ③ 表达式（GUI 编辑视图，不落盘）由 `core/stop_condition_expr.py` 解析 ④ 形态问题（叶子含**未声明参数键**、节点带 `mode` 却缺 `conditions`）由 `core/stop_condition.py` 的 `stop_condition_shape_issues(tree)` 统一报出：加载期写入 `load_warnings`，保存闸门的 tree 分支（WebUI）阻断。**参数键名即契约**，改键名会让旧配置的那一项静默落回默认值（该校验负责把它喊出来） |
| 新面板 | `gui/` + `MainWindow._setup_ui()` 注册 Tab |
| 新保底行为 | `core/pity.py` → `BEHAVIOR_REGISTRY` 注册条目（`class: None` + `preset` 工厂 + `params` 控件声明 + `display_name`/`default_scope`，与既有 13 条目同形）。零件扩展点三族分立：新 Tracker / Lifecycle → `core/pity_tracker.py`（`Tracker` 子类覆写 `rebind`/`advance`/`prepare`/`commit`/`did_reset`/`state_keys()` 中真正承担的相位；`Lifecycle` 子类覆写 `initialize`/`is_active`/`should_deactivate`/`deactivate`/`rebind`）、新 Modifier → `core/pity_modifier.py`（`Modifier` 子类，M1 期自实现 `apply(ctx, view, dist, readonly)`，S8 起改只写 `compute_delta`）。新增 `btype` 还须同步三处：`_BTYPE_ORDER`（`core/pity.py`，排序键）、`_PITY_TYPE_KEYS`（`core/config_toml.py`，TOML 键契约，漏加即合法键被硬拒）、`default_scope` 与 `params`（registry 条目，GUI 控件与下拉顺序） |
| 新里程碑 | `core/milestone.py` → `MilestoneEngine` 计数器引擎 + `[[milestone]]` TOML 段（P58）——`threshold`/`repeat`/`max_triggers`/`banner`/`bonus_reward`（cards/resources/random_cards 三字段任意组合）；`register_milestone_engine(notifier, engine)` 订阅 `after_draw` 事件（priority=0，P61 装配点）。P78：`alternate_rewards`（交替奖励序列——每次触发取下一条、索引模长度循环）+ `offset`（首节点相位偏移，仅首节点生效）；无交替/零偏移里程碑条件写键省略（round-trip 纪律） |
| 新自选券 | `[[select_voucher]]` TOML 段（P78）——`voucher`（资源 id）→ `cards`（可兑换卡显式列表），只记券不落卡（供查询/展示）；`ConfigStore.get_select_voucher_candidates(voucher_id)`/`is_select_voucher()` 读取接口；解析期自动补全 `resource_defs`（setdefault 保留既有显示名） |
| 新资源生命周期 | `core/resource_lifecycle.py` + `[resources.lifecycle]` TOML 段（P77）：`resource_id` + 到期时刻二选一（`expire_at` 天，解析边界 `*DAY`／`expire_with_banner` 对齐该 banner 下架时刻）+ `on_expire` 二选一（转换 `{convert_to, from, to}` 按「每 from 个换 to 个」，零头随源作废／清零 `{clear}`）；到期由 `GachaService` 三处时间检查点（等待期／每抽后／循环收尾）结算，策略经 `ctx.resource_expiry` 感知余额与剩余天数；记账为转换 = 源 `total_consumed` + 目标 `total_gained`。**与 `[[banner.lifecycle]]` 的分工**：本段管**资源**的到期转换/清零（时间驱动，复用 banner 的 `available_until` 只是取时刻的快捷写法），`[[banner.lifecycle]]` 管**池子**的可用性与切换（条件驱动）；两者互不消费对方事件，同一资源被多池共用时只需一条规则 |
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

### 引用标记（refcheck）

文档与代码之间的互引由双向标记承载（`tools/refcheck/`），漂移由工具检测。**要建引用、改动了被引内容、或提交前核对时，必须调用 `refcheck` skill**；说明书由工具自己打印（`python tools/refcheck/refcheck.py manual`），不在本文件复述。

### 文件删除规则

**禁止擅自删除文件。** 需删除时：
- **文档**（`.md`、`.txt` 等）→ 移入 `docs/03-归档/` 归档文件夹
- **代码及其他文件** → 移入项目根目录 `.recycle_bin/` 垃圾桶文件夹

不得直接 `rm` / `rm -rf` 删除任何文件，除非用户明确要求。
