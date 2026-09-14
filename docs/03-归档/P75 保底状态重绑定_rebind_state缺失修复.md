<!-- META: P75 | module:subsystems/保底系统 | status:done | last:2026-08-07 | depends:P55✅→P60✅,P56✅ | priority:high -->

# P75 保底状态重绑定 _rebind_state 缺失修复——保底快照恒空根治

> 日期：2026-08-06 | 状态：设计中（方案已确认，待独立审查）
> 触发：脆弱性分析保底水位、方案搜索保底水位表恒空的实测缺陷；根因回溯到 P55 重构后 `_rebind_state` 设计未落地
> 背景：P55 引入「behaviors 由引擎工厂统一创建、绑定引擎构造时 state」；P55 文档设计了 `_rebind_state` 机制解决「构造时 state」与「per-call state」分裂，但该机制从未写进代码

## 一、问题

**现象**：`banner_end_pity_states` 恒为 `{'data': {}}`。脆弱性分析的保底水位统计、方案搜索面板的保底水位表恒空（实测注入保底后保底触发 87 次、240 条存档全空）。

**根因链**（已通过代码追踪 + 运行时实验确认）：

1. P55 重构后，behaviors 在 `PityEngine` 构造时经 `create_behavior(pdef, self._state)` 绑定引擎自建的 state（账本 A），计数器写入 A（[pity.py:1197](gacha_simulator/core/pity.py#L1197)）。
2. GachaService 每次模拟 `clone()` 自己的 pity_state（账本 B，[gacha_service.py:191](gacha_simulator/service/gacha_service.py#L191)），传给 `before_draw/after_draw`，并在 `on_banner_end` 序列化 B（[gacha_service.py:384](gacha_simulator/service/gacha_service.py#L384)）。
3. P55 文档 line 1785-1812 逐字预见了 A/B 分裂并设计了 `_rebind_state`（每次调度前把 behaviors 的 Counter/Flag 重绑到 per-call state），但**从未实现**。当前 `before_draw` 只有 `self._state = state`（重绑引擎指针，[pity.py:1296](gacha_simulator/core/pity.py#L1296)），未重绑 behaviors。
4. 结果：计数器写 A、存档取 B、查询（`get_counter/get_probabilities`）读 `self._state`（被重绑的 B）而 A 上有计数，三者不交叉。保底快照空、策略层只读保底错、账本 A 跨模拟残留计数。

## 二、目标

1. `banner_end_pity_states` 非空（保底快照恢复）。验收口径见第六节：**须含指定 behavior 名下的 `counter` 键且数值与模拟进度一致**，仅非空不足（`_active`/`{name}_soft` 等 Flag-only 键恒在，见 ISSUE-103）。
2. 策略层只读保底（`get_probabilities`）读到正确计数。
3. 跨模拟计数残留消除（每条模拟从独立初始状态开始）。
4. **固定种子单模拟行为等价**（逐种子 fresh env 对比：除下列四类**预期修复字段**外，单模拟 total_draws / pity_triggers / card_counts 等不漂移）。修复后批聚合中 sim2+ 从初始态开始导致的整体分布变化是预期正确性收益，不计入回归；方案搜索/退路搜索（[retreat_search.py:202](gacha_simulator/core/retreat_search.py#L202) `_simulate_with_resource` 经 `run_batch_parallel` 500 模拟聚合）/最差影响等聚合输出属同一范畴，整体漂移归入预期收益、不做逐值等价比对，但须做字段级方向性核对（ISSUE-105 / ISSUE-111）。

<!-- REVIEW-R1-FIX: ISSUE-100 -->
<!-- REVIEW-R1-FIX: ISSUE-101 -->
   预期修复字段（从「逐字段一致」比对集排除，不视为回归）：
   - `banner_end_pity_states`：空 → 非空（保底快照恢复，原目标）。
   - `draw_pity_counter_max` 及下游派生 `counter_max` / `pool_counter_max`：修复前 `get_counter` 读账本 B 而 B 从不被写，恒 0；修复后变真实值（ISSUE-100）。
   - **depends_on 依赖链配置下的 sim1 整体概率行为**：修复前依赖方 `_active` Flag 绑账本 A、激活写账本 B（A/B 永不交叉），依赖方恒 inactive、其概率调整从不生效；修复后 rebind 重绑 Flag 到 B，依赖方首次真正激活，sim1 的 total_draws / pity_triggers / card_counts 随之漂移。这是修复而非回归，须在阶段 1 基线中显式声明（ISSUE-101）。

<!-- REVIEW-R1-FIX: ISSUE-126 -->
   - **depends_on 门控范围限制声明（ISSUE-126）**：上述「依赖方恒 inactive → 首次真正激活」的激活语义**仅对 counter 型依赖方**（soft/hard 等 `CounterBasedBehavior` 子类，构造期创建 `_active` 且 before_draw 首行检查，[pity.py:124-126](gacha_simulator/core/pity.py#L124-L126)、[pity.py:154-156](gacha_simulator/core/pity.py#L154-L156)）成立。**rotating/targeted 等事件驱动型行为构造时从不创建 `_active`**（RotatingBehavior.__init__ 仅建 `_guaranteed`，[pity.py:464-473](gacha_simulator/core/pity.py#L464-L473)），其 before_draw 也不检查 `_active`（[pity.py:475-487](gacha_simulator/core/pity.py#L475-L487)、TargetedBehavior [pity.py:633-648](gacha_simulator/core/pity.py#L633-L648)）——作为 depends_on 依赖方时「恒生效」，无论源是否 did_fire，计划的「依赖方恒 inactive / 首次真正激活」对它们是错误描述。本计划按「**depends_on 门控仅对 counter 型依赖方生效**」声明该限制；阶段 1 基线补事件驱动依赖方场景、阶段 5 验收相应限定（见下）。

<!-- REVIEW-R1-FIX: ISSUE-107 -->
   - **含 selected_card_init（且 guaranteed_init 或 fate_points_init ≥ threshold）的 targeted 场景 sim1 概率行为**：修复前 B 恒空 → `selected_card` 读默认 None → guaranteed 分支 `_resolve_selected_slots(None)` 返回全部 featured 槽位（无收窄，[pity.py:671-672](gacha_simulator/core/pity.py#L671-L672)）；修复后阶段 3 快照使 B 含 selected_card → guaranteed 100% 分配收窄到单卡槽，该场景 sim1 的 card_counts 必然漂移。这是修复而非回归，须在阶段 1 基线中显式声明、仅作方向性记录（ISSUE-107）。

## 三、方案

按 P55 文档已有蓝图（line 1791-1812, 1910-1934）实现 `_rebind_state`，不发明新机制。

### 阶段 1：等价基线（实现前固化 golden）

开发期验证用。`.recycle_bin/` 下基线脚本，固定种子跑覆盖场景，dump 关键指标到 JSON：
- 场景矩阵：10 种 behavior（`soft_interval`/`soft_additive`/`soft_step`/`hard`/`rotating`/`rotating_soft`/`rotating_cr`/`rotating_cr_soft`/`targeted`/`targeted_soft`）+ 多保底组合 + **depends_on 依赖链（如 rotating→hard 的 depends_on，见 ISSUE-101；hard 为 counter 型依赖方故能激活）** + **事件驱动型依赖方场景（ISSUE-126）**：补一条 rotating/targeted 作为 depends_on 依赖方的配置（如 hard→rotating），声明其不受门控约束（恒生效、修复前后行为不变），避免实施者误以为该场景 sim1 会漂移而误判 + 定轨切换（switch_epitomized_target）+ **初始定轨目标（selected_card_init）/ 大保底初始态（guaranteed_init）/ 定轨点数初始态（fate_points_init）** + 策略 `smart` 与 `pity_reserve`。
<!-- REVIEW-R1-FIX: ISSUE-131 -->
- **fate_points_init 场景（ISSUE-131，与 ISSUE-107 漂移字段 4 对齐）**：补一条「selected_card_init + fate_points_init ≥ threshold（无 guaranteed_init）」的 targeted 场景——guaranteed=False 时定轨分支经 `_resolve_selected_slots` 同样在首抽立即收窄到单卡槽、sim1 的 card_counts 漂移。该场景 sim1 漂移与 ISSUE-107 场景同列第四类预期修复字段，仅作方向性记录、不参与逐字段等价比对；不补该场景则修复后此配置的 sim1 漂移会被阶段 1 等价比对误判为回归。

<!-- REVIEW-R1-FIX: ISSUE-125 -->
- **插件/复合策略回归范围声明（ISSUE-125，响应 P75-STRAT-03）**：核心复合策略（`DrawSegmentStrategy`/`PriorityChainStrategy`/`ConditionalStrategy`）与插件策略（`strategies/example_phased.py` 经 `DrawSegmentStrategy`/`PriorityChainStrategy` 组合 `PityReserveStrategy`）同样经公共入口 `get_pity_probabilities`（strategy.py:133-155，内部走 `PityEngine.get_probabilities`）依赖保底概率。修复后这些组合策略的决策输入从残留账本 A 切到干净账本 B，行为变化为**透明正确性收益**，但当前场景矩阵只覆盖内置 smart 与 pity_reserve，未覆盖组合路径。**处置**：基线场景矩阵补一条「复合策略经 `PriorityChainStrategy` 组合 `pity_reserve` 读取保底概率」的等价对照（固定种子、逐条单模拟，仅作修复前后方向性记录）；若实施者判断组合策略逐值等价比对成本过高，可显式声明「插件/复合策略修复后行为变化归入预期收益、不做逐值等价比对」，但须在阶段 1 基线中至少记录一次修复前快照，保证实施后漂移可归因。该声明同步写入阶段 5/6 回归范围。
- 固化指标：`total_draws`、`pity_triggers`、`card_counts`、`banner_end_resources`（**基准集**）。
- **预期漂移字段（ISSUE-100）**：`draw_pity_counter_max`（CompactResult 字段，[collector.py:124](gacha_simulator/core/collector.py#L124)）修复前因 `get_counter` 读账本 B 而恒 0，修复后为真实值；下游派生 `counter_max`（[process_trace.py:126](gacha_simulator/core/process_trace.py#L126)，过程分析面板 UI 展示）与 `pool_counter_max`（[streaming.py](gacha_simulator/core/streaming.py) 六条流式路径合并 + extract_aggregate）随之为非 0。基线脚本若 dump 了 compact 序列化或过程分析输出，须对上述字段显式过滤，避免误判漂移。
- **粒度（审查补充）**：固定种子**逐条单模拟**（每条 fresh env）对比，`max_workers=1`（`run_batch_parallel` 用 `imap_unordered`，多 worker 种子分配非确定 + 现状 A 跨模拟污染使批结果不可复现）。

<!-- REVIEW-R1-FIX: ISSUE-105 -->
- **方案搜索/退路搜索输出方向性快照（ISSUE-105）**：同配置跑一次 `plan_search`/`retreat_search` 聚合路径（`core/retreat_search.py`），记录 `min_resource`、推荐方案、成功率曲线、Pareto 点数量作为实现前快照；实现后重跑，核对输出在合理区间漂移（不要求逐值一致）。该输出属批聚合预期收益范围，但必须有 before/after 对照，否则无法区分正确性收益与新引入偏差。
- 实现后重跑对比，除四类预期修复字段外逐字段一致：`banner_end_pity_states`（空→非空）、`draw_pity_counter_max` 及下游 `counter_max`/`pool_counter_max`（0→真实值，ISSUE-100）、**含 depends_on 依赖链配置的 sim1 整体概率行为（inactive→active，ISSUE-101）**、**含 selected_card_init + guaranteed_init/fate_points_init≥threshold 的 targeted 场景 sim1 概率行为（无收窄→单卡收窄，ISSUE-107）**。后两类场景仅作方向性记录并单独声明漂移，不参与逐字段等价比对。

### 阶段 2：pity.py 实现 `_rebind_state`

给每个有 Counter/Flag 的类实现重绑。**纯重定向，不复制旧值**（审查修正：rebind 发生在每条模拟第一次调度，此时旧绑定是上一轮模拟的账本 B1；复制旧值会把 B1 结束水位带进本轮 B2，重新引入跨模拟残留）。初始值完全由阶段 3 的完整快照承载。

| 类 | 需重绑字段 |
|---|---|
| `PityBehavior`（基类） | 默认空实现（供 `hasattr`） |
| `CounterBasedBehavior` | **`self._state = state`（关键，`_counter()` 从此派生，[pity.py:139](gacha_simulator/core/pity.py#L139)）** + `self._active = Flag(state, name, "_active")` + 调 `_on_rebind_state(state)` |
| `SoftStepBehavior` / `HardPityBehavior` | 无额外字段（继承基类） |
| `RotatingBehavior` | `self._guaranteed = Flag(state, name, "guaranteed")` |
| `RotatingCRBehavior` | `self._cr_counter = Counter(state, name, "cr_counter")` + super() |
| `TargetedBehavior` | `self._guaranteed`/`self._losses`/`self._lost_flag`/`self._fate_points` 全量重创 |
| `SoftPityMixin` | `self._counter = Counter(state, name, "counter")` + `self._soft_engine._rebind_state(state)` + `super()` |
| 三个 Soft 组合类 | 经 MRO 自动继承 |

要点：
- Counter/Flag 是轻量值对象，重创 O(1)；SoftPityMixin 用 `super()` 链（须在继承列表首位，既有约束）。
- **按当前代码为准，不照抄 P55 蓝图**（审查提示：蓝图含已删除的 `self._triggers` 字段，勿一并加回）。
- **legacy state=None 守卫（ISSUE-102）**：`HardPityBehavior.__init__`（[pity.py:331-335](gacha_simulator/core/pity.py#L331-L335)）在 `state=None` 时直接 return、不调用 `CounterBasedBehavior.__init__`，实例缺 `_name`/`_active`/`_state`。引擎级 `_rebind_state` 遍历时，除 P55 蓝图建议的 `hasattr(bh, '_rebind_state')` 守卫外，还须对 legacy 实例显式跳过：`getattr(bh, '_legacy_mode', False)` 为真时跳过 rebind（否则继承的 `_rebind_state` 触发 `Flag(state, self._name, '_active')` 因缺 `_name` 而 AttributeError）。
<!-- REVIEW-R1-FIX: ISSUE-126 -->
- **depends_on 门控范围声明（ISSUE-126）**：本计划**不为 rotating/targeted 家族新增 `_active` Flag 与 before_draw 首行门控**——P55 蓝图 `_active` 门控本就只面向 counter 型 depends_on，事件驱动型依赖方保持「恒生效」现状（不发明新机制，见第二节 ISSUE-126 限制声明）。若后续需求要求事件驱动型依赖方也受 depends_on 门控，须在此阶段为 `RotatingBehavior`/`TargetedBehavior` 补 `_active` 构造（`depends_on is None` 时 set，与 CounterBasedBehavior [pity.py:124-126](gacha_simulator/core/pity.py#L124-L126) 一致）并同步阶段 3 快照/rebind 表逐行列明。✅ **已裁决（2026-08-06）：不扩展**——本计划按「门控仅对 counter 型依赖方生效」处理。

<!-- REVIEW-R1-FIX: ISSUE-121 -->
- **`_on_rebind_state` 钩子契约（ISSUE-121）**：该钩子非本计划新发明，系 P55 蓝图 `_rebind_state` 设计的组成部分——归档文档 `docs/03-归档/P55 保底体系重构——正交分解与Context驱动的独立保底架构.md` line 1922-1924 已定义其契约为「**子类覆写点——重绑定子类特有的 Counter/Flag；默认空实现（no-op）**」。本计划照此落地：`CounterBasedBehavior._rebind_state()` 完成 `self._state = state` + `self._active = Flag(...)` 后调用 `self._on_rebind_state(state)`，基类提供空实现。**当前 10 种 behavior 均无覆写需求**（各自特有字段已由阶段 2 表逐行列明，如 RotatingCRBehavior 的 `_cr_counter`、SoftPityMixin 的 `_counter`/`_soft_engine`），钩子仅为未来新增带特有 Counter/Flag 的 behavior 预留扩展点；实现时不得因「无覆写者」删除该调用，否则未来扩展会静默漏 rebind。文档同步见第四节（P55 归档文档引用路径）与阶段 4 纪律固化（「新 behavior 必须实现 `_rebind_state`」条目明确含「子类特有字段经 `_on_rebind_state` 覆写」）。
- 单测必须覆盖「sim1 跑完 → sim2 从初始态开始」的跨模拟隔离断言。

<!-- REVIEW-R1-FIX: ISSUE-108 -->
<!-- REVIEW-R1-FIX: ISSUE-115 -->
- **`draw_pity_counter_max` 语义定义（ISSUE-108）**：定义为**本次调度抽前峰值**——`before_draw` incr 之后、`after_draw` reset 之前的计数。现状采集点在 `banner.draw` 返回后（[gacha_service.py:318](gacha_simulator/service/gacha_service.py#L318)），counter 型 behavior 的 `after_draw` 在 reward 命中 scope 时 `_counter().reset()`（[pity.py:173](gacha_simulator/core/pity.py#L173)），触发抽（如 hard-90 强制保底）在读取前已被重置为 0 → 记录 0 而非峰值；`process_trace` 的 `counter_max`（[process_trace.py:126](gacha_simulator/core/process_trace.py#L126)）对 hard-90 池得到 89 而非 90。**修复方式**：采集点迁移至 `banner.draw` 内部 after_draw 之前——banner.draw（[banner.py:226-248](gacha_simulator/core/banner.py#L226-L248)）把 `before_draw → pool.draw → after_draw` 全部捆绑在内部完成、返回后才轮到 gacha_service 读取，触发抽的 counter 在 after_draw 内已被 reset，故「抽前峰值」只能在 banner.draw 内部 after_draw 前采集各 behavior counter 峰值并经 **`DrawOutcome` 新字段暴露**（DrawOutcome 目前仅在 banner.py 构造、gacha_service 消费，改动面可控），gacha_service.py:312-319 改从该值取 max。这是对 `gacha_simulator/core/banner.py` 的实质改动（见第四节波及范围）。✅ **已裁决（2026-08-06）：接受迁移**——触碰 `gacha_service.py` 与 `banner.py`，接受「不动 gacha_service.py」约束的例外（on_banner_end 序列化之外），`counter_max` 记录真实抽前峰值（hard-90 = 90）。

### 阶段 3：账本 B 初始状态与 A 同源（审查补充 + 修正）

`env.pity_state_init` 两个生产方（[batch_simulator.py:698-713](gacha_simulator/service/batch_simulator.py#L698-L713)、[worst_impact.py:255-262](gacha_simulator/core/worst_impact.py#L255-L262)）只构造 `counter`，而 A（`_build_pity_state_init`）含 `counter`+`guaranteed_init`+`fate_points_init`+`selected_card_init`。纯重定向后 B 若缺失这些初始态，`_active` 读默认 False，`before_draw` 直接返回原概率，**计数型保底永不触发**。

修正（审查发现 2 + ISSUE-106）：
- **无条件产出（唯一路径）**：只要 `pity_engine is not None` 就取 `pity_engine._state.to_dict()`，而非仅 counter_init>0 时。快照须在 engine 构造完成后取（behaviors 构造期会向 A 写 `_active=True`，[pity.py:125-126](gacha_simulator/core/pity.py#L125-L126)）。
- **None 守卫**：`pity_engine._state` 在 legacy 签名下可能为 None（[pity.py:1181](gacha_simulator/core/pity.py#L1181)），取快照前判空。
<!-- REVIEW-R1-FIX: ISSUE-106 -->
- **备选路径已删除（ISSUE-106）**：原备选「提取 `pity_defs_list` 用 `_build_pity_state_init(...).to_dict()`」不可用——`_build_pity_state_init`（[pity.py:1005-1041](gacha_simulator/core/pity.py#L1005-L1041)）只写 counter/guaranteed/fate_points/selected_card，**从不写 `_active`**；`CounterBasedBehavior` 的 `_active` 在构造期由 `__init__` set（[pity.py:124-126](gacha_simulator/core/pity.py#L124-L126)），阶段 2 的 rebind 又是纯重定向不 set，B 缺 `_active` 时 `is_set()` 读默认 False，`before_draw` 首行提前返回（[pity.py:155-156](gacha_simulator/core/pity.py#L155-L156)），计数型保底（soft/hard）永不触发。legacy `pity_engine._state=None` 兜底分支若复用此路径同样缺 `_active`。故仅保留主路径（engine._state.to_dict()），其天然含构造期 `_active=True`；若将来新增其他快照来源，须按构造期语义对 `depends_on is None` 的 behavior 补 `_active=True`。

### 阶段 4：公开入口首行 rebind

`before_draw` / `after_draw` / `get_probabilities`（只读查询，**关键**，否则策略层 `pity_reserve` 读错）首行 `self._rebind_state(state)`。

<!-- REVIEW-R1-FIX: ISSUE-109 -->
**引擎级 `_rebind_state` 契约（ISSUE-109）**：PityEngine 级 `_rebind_state(state)` 须**同时执行 `self._state = state`**（`get_counter`/`get_trigger_count` 等无参查询读 `self._state`，[pity.py:1368-1369](gacha_simulator/core/pity.py#L1368-L1369)，正确性依赖该赋值）并遍历 `_behavior_list` 对非 legacy 实例调各 behavior 的 `_rebind_state(state)`；对 `getattr(bh, '_legacy_mode', False)` 为真的实例跳过。当前 `before_draw` 首行的 `self._state = state`（[pity.py:1296](gacha_simulator/core/pity.py#L1296)）替换为 `self._rebind_state(state)` 后，`self._state = state` 的职责并入引擎级实现，不得遗漏。

<!-- REVIEW-R1-FIX: ISSUE-130 -->
**与 P55 蓝图 AUDIT-BREAK-26 的偏离声明（ISSUE-104）**：蓝图要求「所有公开入口方法首行 rebind」，但 `get_counter` / `get_trigger_count` / `is_guaranteed` / `is_active` / **`get_state_summary`**（[pity.py:1368-1383](gacha_simulator/core/pity.py#L1368-L1383)，`get_state_summary` 直接读 `self._state.data` 建 dict、同样无 `state` 参数，ISSUE-130 补入）**均无 `state` 参数**，无法自 rebind，只能依赖「先序入口（before_draw/after_draw/get_probabilities）已 rebind」的时序。本计划显式声明此偏离：**上述五个只读查询（豁免清单，ISSUE-104 + ISSUE-130 补全后闭合）依赖先序入口的 rebind 时序，不各自 rebind**——未来新增无 `state` 参数、直接读 `self._state` 的只读查询，须先判定纳入本豁免清单还是改走引擎级 rebind，不得默认豁免。阶段 5 以 `get_counter` 时序用例（gacha_service.py:318 在 `banner.draw` 后读到当前模拟计数）验证该时序假设。⚠ 该集成锚点依赖 ISSUE-108 采集点迁移裁决（ISSUE-127）：若迁移通过，gacha_service.py:318 不再调用 get_counter（改读 DrawOutcome 暴露字段），此锚点失效，`get_counter` 时序改由引擎级单测（ISSUE-109，rebind 后首次 get_counter 即读 B 上值）独立覆盖；若裁决否决迁移，则保留 gacha_service.py:318 集成锚点。两处处置见阶段 5。

<!-- REVIEW-R1-FIX: ISSUE-120 -->
**`is_active` 默认值语义缺陷（ISSUE-120）**：`is_active(name)`（[pity.py:1377-1378](gacha_simulator/core/pity.py#L1377-L1378)）返回 `self._state.get(name, "_active", True)`，默认值 **True**——与修复后的 depends_on 激活语义直接矛盾：阶段 3 完整快照下，依赖方 B 初始不含 `_active` 键（构造期 `depends_on is not None` 时不 set，[pity.py:124-126](gacha_simulator/core/pity.py#L124-L126)），`before_draw` 首行 `is_set()` 读默认 False → 依赖方初始 inactive，直到源 behavior `did_fire` 后引擎写 B `_active=True`；而此时 `is_active(dep)` 若被调用会读默认 True，与「激活才生效」语义相悖。该查询当前无运行时调用方（前轮 STRAT-04 确认仅 tests/归档文档），但本计划声称完成 depends_on 激活语义修复，须消除此遗留盲区。**处置**：实现阶段同步把 `is_active` 默认值由 True 改为 **False**（与 `before_draw` 首行 `is_set()` 的默认 False 语义一致；正常 behavior 的 `_active=True` 由构造期 set + 阶段 3 快照承载，不受默认值影响），并标注该方法「已无运行时调用方，保留仅供策略层未来使用」。阶段 5 追加断言锁定该语义（见下）。

<!-- REVIEW-R1-FIX: ISSUE-122 -->
**`get_probabilities` API 契约漂移声明（ISSUE-122）**：阶段 4 让 `get_probabilities`（[pity.py:1265](gacha_simulator/core/pity.py#L1265)）首行 `_rebind_state(state)`，其语义从 P55 归档文档定义的「**不修改状态的查询**」（归档文档 line 3503 表格）**漂移为带重绑副作用的入口**：执行后 `self._state` 指针改写、全部 `_behavior_list` 各 behavior 的 Counter/Flag 重创，随后该次查询调度（readonly=True）本身不写计数，但已产生状态重绑副作用。当前唯一调用方 strategy.py:153（`get_pity_probabilities`）传 `ctx._pity_state` 即模拟 B，经 ISSUE-116 自愈时序锁定无实际回归；但**必须显式记录该契约变化**，防止未来插件策略/分析查询路径基于「纯只读」旧假设对非当前 state 调用而读错概率（STRAT-02 关切）。**处置**：① 实现阶段同步更新 `get_probabilities` docstring（pity.py:1265-1267 现称「不修改保底计数器」）为「首行重绑 state 至传入参数、随后以只读语义查询」；② P55 归档文档 line 3503「不修改状态的查询」定义同步修订（标注：P75 起首行 rebind，仅「查询不写计数」仍成立）；③ 本计划的「下游消费端只核对不改」范围不变。波及范围见第四节。

<!-- REVIEW-R1-FIX: ISSUE-123 -->
**rebind 必须先于 spec=None 早退（ISSUE-123）**：`get_probabilities` 与 `before_draw` 均在函数体前段做 `spec = self.pool_specs.get(pool_id); if spec is None: return` 早退（[pity.py:1268-1270](gacha_simulator/core/pity.py#L1268-L1270)、[pity.py:1297-1299](gacha_simulator/core/pity.py#L1297-L1299)）。**实现约束：`self._rebind_state(state)` 必须是函数体首行、先于该早退**——即使 pool_id 无效（spec=None，如策略层误传裸键），也须先把 behaviors 与 engine._state 重绑到当前 per-call state，使无效查询不残留上一轮绑定。实施者不得把 rebind 插入 spec 检查之后。当前策略层已统一传全限定键（strategy.py:51），实际无无效池调用路径，但该顺序约束必须写入实现说明，防止未来新增入口时插错位置。阶段 5 补断言锁定（见下）。

**纪律固化（待办，与阶段 1 IMPACT-07 呼应 + ISSUE-109）**：波及范围追加 `CLAUDE.md` 扩展指南「新保底行为」条目，补记**四条**纪律——「新 behavior 必须实现 `_rebind_state`（或确认走基类空实现；子类特有字段经 `_on_rebind_state` 覆写，见 ISSUE-121）」「新只读查询不得依赖未 rebind 的 `self._state`」「**所有带 `state` 参数的公开入口方法必须在首行 rebind，且须先于任何 spec=None 早退（ISSUE-123）**」（P55 蓝图 AUDIT-BREAK-26 原始纪律；ISSUE-104 只豁免无 `state` 参数的查询，不豁免有参入口，防止未来新增有参公开入口时静默漏 rebind）与「**`per-call state` 必须由阶段 3 快照派生（或含构造期 `_active`/`guaranteed` 等初始 Flag 键），否则 counter 型保底静默失效（ISSUE-128）**」——修复后 `before_draw` 首行 rebind 把 `_active` 重创为指向 per-call state（阶段 2 表 CounterBasedBehavior 行），非快照来源 state 缺 `_active` 键时 `is_set()` 读默认 False → 直接早退 → soft/hard 概率调整永不生效；所有生产路径（batch_simulator._run_single / worst_impact / 两个 profile 脚本）均从 `env.pity_state_init` 传快照故安全，风险集中在直接构造 engine 的既有测试与未来调用方。

### 阶段 5：测试

- 适配现有 `tests/test_pity*.py`（直接调 engine 的用例）与 `tests/core/test_vulnerability.py`。

<!-- REVIEW-R1-FIX: ISSUE-124 -->
- **既有批聚合数值断言逐文件核对（ISSUE-124，响应 P75-TEST-1）**：对含 `_run(num=N, seed=42, strategy_key='smart'/'pool_quota')` 批聚合 + `total_draws`/`card_counts` 边界断言的既有测试逐文件核对，明确其 store 是否启用保底（`pity_enabled=True` + `pity_defs`）、断言是否落在预期漂移字段，产出**适配/豁免清单**，避免实施后 FAIL 无预案。预查结论：`tests/test_banner.py` 的批聚合断言（[test_banner.py:258](tests/test_banner.py#L258)、[test_banner.py:315-316](tests/test_banner.py#L315-L316)、[test_banner.py:325-327](tests/test_banner.py#L325-L327)）均经 `_make_store` 默认 `pity_enabled=False`（无保底引擎 → 无保底状态可漂移），`TestReproducibility`（[test_banner.py:393-406](tests/test_banner.py#L393-L406)）同为无保底配置、锁 Banner 状态不跨模拟泄漏；`tests/core/test_streaming.py` 与 `tests/core/test_gdr.py` grep 无 pity 引用 → 预期豁免。核对流程：对清单内每条测试确认（a）store 无保底 → 豁免；（b）store 有保底但断言不落在 `draw_pity_counter_max`/`counter_max`/`pool_counter_max` 或 depends_on/selected_card_init 场景 sim1 概率行为 → 豁免；（c）落在上述预期漂移字段 → 移入阶段 1 基线声明为预期修复，测试断言改为方向性核对。实施后 `pytest -q` 若仍 FAIL，先对照此清单判定属「预期漂移未声明」还是「实现回归」。
- 新增 `_rebind_state` 单测：**纯重定向**（重绑后 A 值不变、B 独立）+ **跨模拟隔离断言**（sim1 跑完 → sim2 从初始态开始）+ counter_init=0 但有 rotating/targeted 初始态的配置下保底正常触发。
- 新增回归：保底快照含**指定 behavior 名下的 `counter` 键且数值与模拟进度一致**（模拟后 `banner_end_pity_states` 内 `{name}` 命名空间含 `counter` 键——仅断言「快照非空」不足：`_active`/`{name}_soft` 等 Flag-only 键在阶段 3 无条件快照下恒在，可空过，见 ISSUE-103）。
  <!-- REVIEW-R1-FIX: ISSUE-127 -->
  - **`get_counter` 时序确认（ISSUE-127，与 ISSUE-108 采集点迁移协调）**：原定「gacha_service.py:318 在 `banner.draw` 后读到当前模拟计数」的集成锚点与 ISSUE-108 迁移冲突——迁移通过后 gacha_service.py:312-319 改从 `DrawOutcome` 暴露字段取池级峰值、不再调用 `get_counter`，该锚点失效。**协调处置**：若 ISSUE-108 迁移通过（推荐），此用例改写为断言 `DrawOutcome` 暴露字段的**抽前峰值**语义（配合下条 hard-90 == 90 断言），`get_counter` 时序由引擎级单测（ISSUE-109，见后）独立覆盖；若裁决否决迁移，则保留 gacha_service.py:318 锚点。
- 新增回归（ISSUE-100 + ISSUE-108）：模拟后 `draw_pity_counter_max` 非零（修复前恒 0），语义为**抽前峰值**——对 hard-90 强制保底池断言 `draw_pity_counter_max` 及派生 `counter_max` **== 90（而非 89/0）**；并抽样验证 process_trace 派生 `counter_max` 与流式 `pool_counter_max` 随之为真实值。
- 新增回归（ISSUE-102）：legacy 签名（`state=None`）构造 engine + rebind 不崩溃（与阶段 3 legacy None 守卫测试合并）。

<!-- REVIEW-R1-FIX: ISSUE-106 -->
- 新增回归（ISSUE-106）：counter_init=0 且无 guaranteed 初始态（engine 正常构造、`_active` 构造期 set）的配置下，soft/hard 计数型保底仍正常触发（保底快照含 counter 键且触发次数 > 0）。

<!-- REVIEW-R1-FIX: ISSUE-128 -->
- 新增断言（ISSUE-128，非快照 state 契约边界）：以**非阶段 3 快照来源**的 state 调 counter 型保底入口（如 `GachaService(pity_engine=..., pity_state=None)` 或直接 `engine.before_draw(pid, 空PityState(), ...)`，即 per-call state 缺构造期 `_active` 键），断言其**静默失效**（before_draw 首行 `_active` 读默认 False → 直接早退 → soft/hard 概率调整不生效），或显式声明其为**不支持用法**——二选一，实现阶段定并记录于测试注释，防止未来调用方静默踩坑。该断言同时锁定阶段 4 纪律「per-call state 必须由阶段 3 快照派生」的边界。

<!-- REVIEW-R1-FIX: ISSUE-109 -->
<!-- REVIEW-R1-FIX: ISSUE-130 -->
- 新增回归（ISSUE-109）：引擎级 `_rebind_state` 后 `get_counter` 立即读到当前 per-call state 的计数（rebind 后首次 get_counter 即返回 B 上值，无需先经 before_draw）。同一用例一并断言 **`get_state_summary` 读 B**（ISSUE-130——rebind 后首次调用即返回 B 命名空间的 dict，与 `get_counter` 同属 ISSUE-104 豁免清单，均依赖引擎级 `_rebind_state` 同步执行 `self._state = state` 的契约，[pity.py:1380-1383](gacha_simulator/core/pity.py#L1380-L1383)）。

<!-- REVIEW-R1-FIX: ISSUE-120 -->
<!-- REVIEW-R1-FIX: ISSUE-133 -->
- 新增断言（ISSUE-120）：depends_on 依赖链配置下，依赖方 B **未激活时** `is_active(dep)` 返回 **False**（而非默认 True）；源 behavior `did_fire` 激活后再查返回 True。**时序前置（ISSUE-133）**：`is_active` 读 `self._state`（[pity.py:1377-1378](gacha_simulator/core/pity.py#L1377-L1378)），引擎构造后、任何入口调用前 `self._state` 是构造期 A（对 depends_on 依赖方同样无 `_active` 键 → 返回 False），此时直接断言表面通过但测的是 **A 而非 B**、无法验证阶段 3 快照→B 链路。断言实现必须先以当前 per-call state 调一次 `get_probabilities`（或 `before_draw`）触发 rebind，再断言 `is_active(dep)` 为 False，确保读取对象是 B；激活后再查 True 同理先经 rebind。与 ISSUE-109 引擎级 rebind 单测顺序对齐。与阶段 3 快照断言合并：B 初始快照不含依赖方 `_active` 键、`is_active` 读 False、`before_draw` 不生效，三者一致锁定「激活才生效」修复语义。若实施时放弃改默认值、改走「标注已废弃」路线，则该断言降级为「依赖方未激活时 `is_active` 不被运行时调用方使用」的文档声明，须同步注明处置变更。**适用范围限定（ISSUE-126）**：该断言仅对 **counter 型依赖方**成立（阶段 3 快照下其 B 缺 `_active` 键 → `is_active` 读 False → `before_draw` 不生效，三者一致）；对 rotating/targeted 事件驱动型依赖方，B 快照无 `_active` 键 → `is_active` 返回 False（断言表面通过），但其 before_draw 不检查 `_active`、仍实际生效——验收与真实激活语义脱节。故本用例只覆盖 counter 型依赖方，事件驱动型依赖方按第二节限制声明为不受门控（恒生效）。

<!-- REVIEW-R1-FIX: ISSUE-123 -->
- 新增断言（ISSUE-123）：无效 pool_id（不在 `pool_specs` 中的裸键）调 `get_probabilities`/`before_draw` 早退返回后，断言 behaviors 与 engine._state 仍绑定当前 per-call state（如随后用有效 pool_id 调 `get_counter` 立即读到该 state 计数、无需再经有效入口），锁定「rebind 先于 spec=None 早退」的实现顺序约束。

<!-- REVIEW-R1-FIX: ISSUE-116 -->
- 新增回归（ISSUE-116）：交错时序用例——用**独立 state 对象**（非当前模拟 state）调 `get_probabilities` 后，再以当前模拟 state 调 `before_draw`，断言 behavior 已重绑回模拟 state（如 counter 写入生效、后续 `get_counter` 读到正确值）。锁定阶段 4 重绑副作用的自愈时序：`get_probabilities` 首行 `_rebind_state` 会把 behaviors 重绑到查询方传入的 state，直至下一次 `before_draw` 才纠正，任何未来只读查询方（脆弱性/方案搜索等路径）传入独立 state 均依赖该时序，须以用例锁定防回归。

<!-- REVIEW-R1-FIX: ISSUE-117 -->
- 新增回归（ISSUE-117）：`tests/core/test_vulnerability.py` 补充用例——构造含 `_active`/`guaranteed` Flag-only 命名空间的完整快照（对齐阶段 3 无条件 to_dict() 的真实结构），断言其**不进入 `pity_stats_at_pool_end`**（保底水位表无 0 噪声行），与 vulnerability.py 跳过不含 `counter` 键命名空间的逻辑（ISSUE-103）配对锁定。现有 fixture（[test_vulnerability.py:214](tests/core/test_vulnerability.py#L214) `{'data': {'soft_pity': {'counter': i % 90}}}`）只有 counter 命名空间、无 Flag-only 命名空间，修复后真实快照必然含 Flag-only 命名空间，该 fixture 无法暴露消费端跳过回归，须新用例补齐。

### 阶段 6：全量回归

- `pytest -q` + H7（ruff）。

<!-- REVIEW-R1-FIX: ISSUE-105 -->
<!-- REVIEW-R1-FIX: ISSUE-111 -->
- **面板输出方向性核对（ISSUE-105 / ISSUE-111）**：带保底配置手动/脚本跑一次各下游消费端，核对输出在合理区间且语义正确（整体分布变化属预期收益，不做逐值等价比对）：
  - `worst_impact` 面板：`expected_pools` 列表非空且行数合理（99 池 + draw_target + 多 worker 场景）。
  - `plan_search` 面板：保底水位表首次真实填充（行数与均值在合理区间）；QSpinBox 默认值变 `int(round(snap.mean))` 后正常。⚠ 提示（ISSUE-118）：保底水位表数据源为方案搜索 tab 接收的 `_vulnerability_result`（[plan_search_panel.py:1276-1286](gacha_simulator/gui/plan_search_panel.py#L1276-L1286) `set_vulnerability_result`），基于已存 CompactResult 计算——修复前保存的旧结果 `banner_end_pity_states` 为空，**必须重跑模拟生成新结果才生效**，否则面板保底水位表恒空、易被误判为修复无效；核对时以修复后新跑的结果为准。
  - `retreat_search` 面板：退路点搜索起始计数从 0 变表内均值，搜索结果正常产出（`min_resource`、Pareto 点数量变化记录为方向性快照）。
  - 脆弱性分析：PAVA `theta_tilde`、changepoint `x_star_*`、`vulnerability_intervals` 聚合输出方向性记录（无反转、无异常跳变）。

<!-- REVIEW-R1-FIX: ISSUE-113 -->
- **既有验证脚本适配（ISSUE-113）**：`scripts/p61_verify.py` 的 `compare_single`（107-128 行）对 golden 与 `compact.to_dict()` 逐字段严格比对，跳过集 `TIME_WINDOW_FIELDS`/`SKIP_FIELDS`（33-44 行）不含 `draw_pity_counter_max`，golden 由 `scripts/p61_baseline.py` 修复前生成（该字段恒 0）→ 修复后必然 DIFF → exit(1) FAIL。处置二选一：把 `draw_pity_counter_max`（及下游 `counter_max`/`pool_counter_max` 若被序列化）加入跳过集，或修复后同种子重新生成 golden 固化；若走跳过字段，其真实值由阶段 5 的 ISSUE-100/108 回归独立断言。

## 四、波及范围

- `gacha_simulator/core/pity.py`（`_rebind_state` + 入口调用 + 引擎级 `self._state = state` 契约，ISSUE-109；`get_probabilities` docstring「不修改保底计数器」改为首行 rebind 语义，ISSUE-122；rebind 先于 spec=None 早退的顺序约束，ISSUE-123；`is_active` 默认值 True → False 及废弃标注，ISSUE-120）
- `gacha_simulator/service/batch_simulator.py`（`env.pity_state_init` 完整化）
- `gacha_simulator/core/worst_impact.py`（`pity_state_init` 完整化 + **删除死代码 `_get_initial_pity_state`（[worst_impact.py:534-543](gacha_simulator/core/worst_impact.py#L534-L543)，唯一调用点 :256 随阶段 3 改完失去调用方，同一提交内移除，ISSUE-110）**）
<!-- REVIEW-R1-FIX: ISSUE-132 -->
- **追加（ISSUE-132）**：`gacha_simulator/core/retreat_config.py`（RetreatConfigBuilder 的 PityDef 拷贝补 `selected_card_init=pd.selected_card_init`，[retreat_config.py:117-135](gacha_simulator/core/retreat_config.py#L117-L135) 现漏拷该字段——阶段 3 使完整时间线分支（from_pool_id=None，直接 from_config_store）的 snapshot 携带 selected_card_init，而截断分支仍丢失，制造「完整分支定轨首抽收窄、截断分支不收窄」的不对称；补拷后两分支一致。若实施时判定拷贝层不改，须显式声明「退路点 targeted 场景仅 counter 维度生效」为已知限制并纳入阶段 6 方向性核对）
<!-- REVIEW-R1-FIX: ISSUE-110 -->
<!-- REVIEW-R1-FIX: ISSUE-119 -->
- 测试：`tests/test_pity.py`、`tests/core/test_pity_*.py`、`tests/core/test_vulnerability.py`（Flag-only 命名空间跳过用例，ISSUE-117）
- **追加（ISSUE-103）**：`gacha_simulator/core/vulnerability.py`（pity 水位统计遍历 `ps.data` 时跳过不含 `counter` 键的命名空间，消除修复后快照非空引入的 `_active`/`{name}_soft` Flag-only 噪声 0 行）
- **追加（ISSUE-104 + ISSUE-109 + ISSUE-128）**：`CLAUDE.md` 扩展指南「新保底行为」条目（补记**四条** rebind 纪律，含 ISSUE-128「per-call state 必须由阶段 3 快照派生」契约，见阶段 4）
- **追加（ISSUE-108）**：`gacha_simulator/core/banner.py`（banner.draw 在 after_draw 前采集各 behavior counter 峰值并经 `DrawOutcome` 新字段暴露，改动面见阶段 2 语义说明）+ `gacha_simulator/service/gacha_service.py` 仅调整 `pool_counter_max` 采集位置（改从 DrawOutcome 暴露字段取 max，见阶段 2 语义说明），`on_banner_end` 序列化逻辑不动。⚠ 待人工裁决：该改动触碰 `gacha_service.py` 与 `banner.py`，与既有「不动 gacha_service.py」约束冲突，需确认范围。
- **追加（ISSUE-113）**：`scripts/p61_verify.py` / `scripts/p61_baseline.py` / `tests/fixtures/baseline_pool_golden.json`（既有验证脚本适配，见阶段 6）
- **追加（ISSUE-112 + ISSUE-114，文档同步）**：`docs/00-meta/模块状态矩阵.md` 第 154 行 P55 路径修正为 `docs/03-归档/P55 保底体系重构——正交分解与Context驱动的独立保底架构.md`（当前指向 `docs/01-活跃/subsystems/保底系统/P55...` 已失效，实际文件在归档目录根级、**无「保底系统」子目录**，已实测）；本计划引用的「P55 蓝图 line 1785-1812 / 1791-1812 / 1910-1934」来源为归档文档 `docs/03-归档/P55 保底体系重构——正交分解与Context驱动的独立保底架构.md`（同一条无子目录路径），随提交在计划/代码注释中注明——写入代码注释时必须以该无子目录路径为准，避免悬空引用
- **追加（ISSUE-122，归档文档同步）**：P55 归档文档 line 3503 `PityEngine.get_probabilities()`「不修改状态的查询」定义同步修订为「P75 起首行 rebind 到 per-call state，仅查询不写计数」（`_on_rebind_state` 契约来源 line 1922-1924 同文，见阶段 2）
<!-- REVIEW-R1-FIX: ISSUE-112 -->
<!-- REVIEW-R1-FIX: ISSUE-114 -->
- 不动：`collector.py`；`gacha_service.py` 的 `on_banner_end` 序列化（rebind 后 B 有数据）

**下游消费端（只核对不改，ISSUE-105 / ISSUE-111 / ISSUE-125）**：`gui/plan_search_panel.py`、`gui/retreat_search_panel.py`、`core/retreat_search.py`、`core/worst_impact.py`、`core/vulnerability.py`——修复后保底水位数据首次真实填充，其聚合输出（min_resource、保底水位表、PAVA/changepoint）按阶段 6 做方向性核对，无代码改动；**策略消费端（ISSUE-125）**：`strategies/example_phased.py`、`core/strategy.py`（复合策略类 DrawSegmentStrategy/PriorityChainStrategy/ConditionalStrategy 及 `get_pity_probabilities` 读取路径）、`core/strategy_loader.py`——修复后决策输入从账本 A 切到干净账本 B，行为变化归入预期收益，仅按阶段 1 记录修复前快照供归因，无代码改动；<!-- REVIEW-R1-FIX: ISSUE-129 -->**性能脚本（ISSUE-129）**：`scripts/profile_sim.py`（预热 + 串行 20 次，[profile_sim.py:93](scripts/profile_sim.py#L93)、[profile_sim.py:97](scripts/profile_sim.py#L97)、[profile_sim.py:111](scripts/profile_sim.py#L111)）与 `scripts/profile_simulation.py`（预热 + 串行 10 次，[profile_simulation.py:108](scripts/profile_simulation.py#L108)、[profile_simulation.py:113](scripts/profile_simulation.py#L113)）直接构造 `GachaService` 连跑多次 `run_simulation_compact`（不经 `run_batch_parallel`，正确传入 `env.pity_state_init` 故不崩溃）——修复前账本 A 跨 run 残留使各 run 相互污染（预热污染后续测量）；修复后每 run 从快照派生独立 B'、预热不再预热任何共享账本、串行测量语义变化（测量值趋向更均匀）。**处置**：显式声明两脚本不参与正确性核对、仅作性能采样，修复后测量值变化属预期，无代码改动。

## 五、风险

| 风险 | 缓解 |
|------|------|
| 静默概率变化（改抽卡核心） | 阶段 1 golden（逐种子单模拟、max_workers=1）逐字段对照，任何漂移立即暴露 |
| 初始状态丢失（selected_card/guaranteed 等） | 阶段 3 `env.pity_state_init` 无条件完整产出 + 基线含定轨初始场景 |
| **重引入跨模拟残留（审查发现 1）** | 阶段 2 纯重定向不复制旧值 + 隔离单测（sim1 跑完 → sim2 从初始态） |
| **计数型保底永不触发（审查发现 2）** | 阶段 3 无条件产出完整快照，counter_init=0 场景进基线 |
| **depends_on 激活修复被误判为回归（ISSUE-101）** | 阶段 1 场景矩阵显式含 depends_on 依赖链，该场景 sim1 漂移声明为预期修复、不参与等价比对 |
| **draw_pity_counter_max 从 0 变真实值被误判漂移（ISSUE-100）** | 阶段 1 固化与比对集显式排除该字段及下游 counter_max / pool_counter_max + 阶段 5 非零断言 |
| **legacy state=None behavior rebind 崩溃（ISSUE-102）** | 阶段 2 引擎级 rebind 对 `_legacy_mode` 实例跳过 + legacy 构造 + rebind 不崩溃用例 |
| SoftPityMixin MRO 顺序 | 组合类专项测试 |
| 策略层回归（pity_reserve 只读保底） | 策略场景进基线 |
| 基线不可复现（多 worker） | 基线统一 max_workers=1 |
| **方案搜索/退路搜索输出静默漂移（ISSUE-105）** | 阶段 1 增加搜索输出方向性快照（min_resource、Pareto 点数量、成功率曲线）+ 阶段 6 面板输出核对，声明属预期收益范围 |
| **selected_card_init + guaranteed_init/fate_points_init≥threshold 场景 sim1 漂移被误判回归（ISSUE-107 / ISSUE-131）** | 该场景列为第四类预期修复字段，基线仅作方向性记录、不参与逐字段等价比对；阶段 1 场景矩阵已含 fate_points_init≥threshold（无 guaranteed_init）场景（ISSUE-131） |
| **draw_pity_counter_max off-by-one / 语义未定义（ISSUE-108）** | 显式定义「抽前峰值」语义 + 采集点迁移至 after_draw 前 + 阶段 5 断言 hard-90 == 90 |
| **备选快照路径缺 `_active` 致计数型保底永不触发（ISSUE-106）** | 删除备选路径、仅保留 engine._state.to_dict() 主路径 + counter_init=0 无 guaranteed 初始态触发单测 |
| **引擎级 rebind 漏更新 self._state（ISSUE-109）** | 明确 PityEngine._rebind_state 契约（同时 self._state = state + 跳过 legacy 实例）+ get_counter 时序断言 |
| **既有 p61_verify 验证脚本修复后 FAIL（ISSUE-113）** | 把 draw_pity_counter_max 及下游加入跳过集或同种子重生成 golden 固化 |
| **is_active 默认值 True 与依赖方初始 inactive 语义矛盾（ISSUE-120）** | 实现阶段改默认值 False（与 is_set() 默认一致）+ 阶段 5 断言锁定；当前无运行时调用方，改动面可控 |
| **get_probabilities 纯只读契约漂移为带重绑副作用（ISSUE-122）** | 显式声明契约变化 + 同步更新 docstring 与 P55 归档文档定义 + 阶段 5 断言锁定首行 rebind 语义 |
| **rebind 插在 spec=None 早退后致无效池查询不 rebind（ISSUE-123）** | 明确「rebind 必须首行、先于早退」实现约束 + 阶段 5 无效 pool_id 断言 |
| **既有批聚合数值断言实施后 FAIL 无预案（ISSUE-124）** | 阶段 5 逐文件核对清单（预查：无保底 store 豁免、预期漂移字段移入阶段 1 声明） |
| **插件/复合策略保底读取路径漂移无法归因（ISSUE-125）** | 阶段 1 基线记录复合策略修复前快照或显式声明归入预期收益 |
| **depends_on 门控对事件驱动型依赖方不生效被误判（ISSUE-126）** | 限制声明（门控仅对 counter 型依赖方生效）+ 阶段 1 基线补事件驱动依赖方场景（恒生效、不漂移）+ 阶段 5 断言限定适用范围；是否扩展 ✅ **已裁决（2026-08-06）：不扩展** |
| **stage-5 get_counter 锚点与 ISSUE-108 迁移冲突（ISSUE-127）** | 协调处置：迁移通过则改写为断言 DrawOutcome 抽前峰值（hard-90==90）、get_counter 时序由 ISSUE-109 引擎级单测覆盖；否决则保留 gacha_service.py:318 锚点 |
| **非快照 state 致 counter 型保底静默禁用（ISSUE-128）** | 阶段 4 纪律固化「per-call state 必须由阶段 3 快照派生」+ 阶段 5 非快照 state 负向断言（或声明为不支持用法）；生产路径均传快照故无实际风险 |
| **profile 脚本跨 run 污染语义变化未声明（ISSUE-129）** | 下游清单补记两脚本 + 显式声明不参与正确性核对、测量值变化属预期 |
<!-- REVIEW-R1-FIX: ISSUE-130 -->
| **只读查询豁免清单不完整，未来调用方读到构造期 A / 上一轮 B 残留（ISSUE-130）** | 偏离声明补全 `get_state_summary`（与四个查询同级）、豁免清单闭合 + 阶段 5 ISSUE-109 用例断言 rebind 后 `get_state_summary` 读 B |
<!-- REVIEW-R1-FIX: ISSUE-132 -->
| **截断退路点 targeted 场景 selected_card_init 丢失、与完整分支不对称（ISSUE-132）** | RetreatConfigBuilder PityDef 拷贝补 `selected_card_init=pd.selected_card_init`（或显式声明为已知限制 + 纳入阶段 6 方向性核对） |
<!-- REVIEW-R1-FIX: ISSUE-133 -->
| **is_active 断言时序未指定，表面通过但测 A 而非 B（ISSUE-133）** | 阶段 5 ISSUE-120 断言明确前置步骤：先以当前 per-call state 调 get_probabilities/before_draw 触发 rebind，再断言 is_active(dep)，与 ISSUE-109 引擎级单测顺序对齐 |

## 六、验收标准

- [ ] 实现前等价基线 dump 完成（golden，逐种子单模拟 + max_workers=1）
- [ ] `_rebind_state` 单测通过（纯重定向 + 跨模拟隔离断言 + 运行态不复制）
- [ ] 实现后重跑基线：除四类预期修复字段外逐字段一致（`banner_end_pity_states` 空→非空、`draw_pity_counter_max` 及下游 `counter_max`/`pool_counter_max` 0→真实值 [ISSUE-100]、含 depends_on 依赖链配置的 sim1 概率行为 [ISSUE-101]、含 selected_card_init + guaranteed_init/fate_points_init≥threshold 的 targeted 场景 sim1 概率行为 [ISSUE-107]）
- [ ] `banner_end_pity_states` 含指定 behavior 名下的 `counter` 键且数值与模拟进度一致（仅非空不足——`_active`/`{name}_soft` 等 Flag-only 键恒在可空过，见 ISSUE-103）
- [ ] selected_card_init / guaranteed_init 场景初始状态不丢失
- [ ] counter_init=0 但有 rotating/targeted 初始态的配置下保底正常触发（ISSUE-106 补充：counter_init=0 且无 guaranteed 初始态的 soft/hard 计数型保底同样触发）
- [ ] 策略层 `pity_reserve` 只读保底正确
- [ ] `draw_pity_counter_max` 语义为抽前峰值：hard-90 强制保底池该字段及派生 `counter_max` == 90（ISSUE-108；⚠ 该验收项无条件成立的前提是「采集点迁移至 banner.draw 内部 after_draw 前 + DrawOutcome 暴露字段」的人工裁决通过，若裁决否决迁移、退回「抽后值」语义，则此项不成立、须同步降级为记录实际值）
- [ ] 引擎级 `_rebind_state` 后 `get_counter` 立即读到当前 per-call state 计数（ISSUE-109）
- [ ] depends_on 依赖方未激活时 `is_active(dep)` 返回 False、激活后返回 True（默认值已改 False 或已标注废弃，ISSUE-120；**仅 counter 型依赖方适用，ISSUE-126**）
- [ ] depends_on 门控范围已声明：仅对 counter 型依赖方生效，事件驱动型依赖方保持恒生效现状；阶段 1 基线已含事件驱动依赖方场景（ISSUE-126）
- [ ] stage-5 `get_counter` 时序用例与 ISSUE-108 采集点迁移已协调：迁移通过则改断言 DrawOutcome 抽前峰值（配合 hard-90 == 90），`get_counter` 时序由 ISSUE-109 引擎级单测覆盖；否决则保留 gacha_service.py:318 锚点（ISSUE-127）
- [ ] 非快照 state 契约边界已处理：阶段 4 纪律含「per-call state 必须由阶段 3 快照派生」+ 阶段 5 负向断言或显式声明为不支持用法（ISSUE-128）
- [ ] `scripts/profile_sim.py` / `scripts/profile_simulation.py` 已列入下游清单并声明不参与正确性核对（ISSUE-129）
- [ ] `_on_rebind_state` 按 P55 蓝图契约实现（基类默认空实现 + 供子类覆写的扩展点，当前 10 种 behavior 无覆写需求，ISSUE-121）
- [ ] `get_probabilities` docstring 与 P55 归档文档 line 3503「不修改状态的查询」定义已同步修订为「首行 rebind、查询不写计数」（ISSUE-122）
- [ ] 无效 pool_id 查询（spec=None 早退）后 behaviors 与 engine._state 仍绑定当前 per-call state（rebind 先于早退，ISSUE-123）
- [ ] 既有批聚合数值断言核对清单产出（test_banner.py 等适配/豁免，无保底 store 豁免、预期漂移字段移入阶段 1 声明，ISSUE-124）
- [ ] 插件/复合策略回归范围已声明：基线至少记录一次复合策略（PriorityChainStrategy 组合 pity_reserve）修复前快照或显式声明归入预期收益（ISSUE-125）
- [ ] 方案搜索/退路搜索/最差影响/脆弱性 PAVA 面板输出方向性核对通过（ISSUE-105 / ISSUE-111）
- [ ] `scripts/p61_verify.py` 修复后不 FAIL（跳过字段或重生成 golden，ISSUE-113）
- [ ] `worst_impact._get_initial_pity_state` 已随阶段 3 删除、无残留调用（[worst_impact.py:534-543](gacha_simulator/core/worst_impact.py#L534-L543)，ISSUE-110 / ISSUE-119）
- [ ] 模块状态矩阵第 154 行 P55 路径已修正为 `docs/03-归档/P55 保底体系重构——正交分解与Context驱动的独立保底架构.md`（归档根目录、无「保底系统」子目录，ISSUE-112 / ISSUE-114）
- [ ] `pytest -q` 全量通过
- [ ] 带保底跑模拟后脆弱性分析 `pity_stats_at_pool_end` 含 counter 键（排除 `_active`/`{name}_soft` 等 Flag-only 命名空间——脆弱性消费端 [vulnerability.py:758](gacha_simulator/core/vulnerability.py#L758) 遍历 `ps.data` 时跳过不含 `counter` 键的命名空间，避免水位 0 噪声行，见 ISSUE-103）

## ⚠ 自动化审查阻塞项

- 未解决问题：0 个
- 详情：[]
- 原因：6 轮对抗循环未收敛。

## 自动化审查记录

<details>
<summary>第 1 次审查（2026-06-11）——P38 工作流自动化</summary>

- 复杂度: complex | 变更性质: evolutionary
- 阶段 1 影响面: 35 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 34 个

</details>
