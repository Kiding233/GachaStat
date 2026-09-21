<!-- META: P64 | module:保底系统 | status:designing | last:2026-09-21 | depends:P55,P56 -->

# P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构

> 日期：2026-08-24（2026-09-16 补三条强制约束 + §3.1.5 形式化 + target_featured 反例；**2026-09-18 事实同步**：全量行号刷新至 P81 清理后的代码 + GUI 两处事实修正 + legacy 迁移描述更新；**同日裁决 P82 并入的三项**：接线 / 保留 priority / 顺序两层定性，见 §1.5；**2026-09-21 概率操作乘法化 + 状态可见性裁决**：§3.1.5 重写为乘性因子版 + §3.1.2 D20 分布空间归属 + §3.9 S8 实施方案 + §3.10 状态可见性与 G3 真实建模 + S8/S9 子块；跨保底读状态裁决为不纳入；G15 按「精确建模原则」重估为缺口；**同日增补三项架构改进**：§3.11 表达能力与边界、§3.12 组合正确性验收、§3.13 不变式运行时校验 + S10/S11 子块；**§3.14 条件外置**（条件提为独立对象 + ConditionalModifier 包装器；三方案比较与 R/F 等价性实测）+ S12 子块） | 状态：设计中（2026-08-23 初版 → 2026-08-24 双层纯函数重建）
> 触发：P56 审查发现的「触发器 × 选择器 × 拓扑 × 效果」四维抽象 + 组合爆炸。**2026-08-24 设计重建**：用户追问「最优雅架构」，从领域本质重新理解保底 → 提出 Tracker + Modifier + Lifecycle 三元组纯函数架构；用户裁决命名 Tracker+Modifier。
> 依赖：P55✅（counter 驱动正交分解 + deltas 展开）+ P56✅（6 个事件驱动类 + Flag/Counter/_redistribute_scope + LifecycleConfig，作为等价性基准）
> 合并：**P82（保底管道顺序接通）于 2026-09-16 并入本计划**，见 §1.5；其结论直接影响 §1.3 的 G5 项与 §3.6 的 priority 设计，P82 文件已归档
> 命名：Tracker（追踪器，状态转移）+ Modifier（概率修正器）+ Lifecycle（生命周期）

## 〇、演进定位——为什么现在重建是合理的

P55 和 P56 **不是被否定，是被提炼**。它们把散的逻辑收敛到可组合的零件，为重建凑齐了输入。

| 阶段 | 解决的问题 | 交付的零件 |
|------|-----------|-----------|
| P55 | counter 驱动内部混乱（soft 三套写法、hard 另起炉灶） | CounterBasedBehavior 基类、SoftStepBehavior 唯一 soft 实现、deltas 展开、PityDef 扁平字段、_resolve_order 排序 |
| P56 | 事件驱动从无到有 | Flag/Counter 状态原语、_redistribute_scope 概率工具、LifecycleConfig、DrawInfo/PityContext 管道、6 个事件驱动类 |
| 共同选择 | 分类式扩张——counter 驱动 vs 事件驱动两类，每类内部再细分 | 新机制 = 新类，rotating_soft 靠 SoftPityMixin 拼 |

**分类本身成了包袱**：counter 驱动难道不是事件驱动吗。每抽一次计数加一、出了 SSR 清零，这不就是事件驱动的状态机。soft 的记忆是无条件递增，rotating 是歪中翻转，targeted 是命中定轨清零——只是事件分支不同。两类本质是同一种东西。

**新方案对 P55/P56 的继承**（零件保留，分类维度重建）：

| 基础设施 | P55/P56 已交付 | P64 如何复用 |
|---------|---------------|-------------|
| 状态容器 | PityState 三层嵌套、_build_pity_state_init、P75 rebind 纪律 | 完全保留，Tracker 读写同一个 PityState，Pity 统一 rebind |
| 上下文管道 | DrawInfo/PityContext（含 scope_cards/card_to_slot） | 完全保留，Tracker 和 Modifier 都消费同一个 PityContext |
| 概率工具 | _redistribute_scope 按基础权重分配 | 完全保留，所有 Modifier 最终落点都是它 |
| 注册与调度 | BEHAVIOR_REGISTRY、_resolve_order、_validate_behaviors、PityEngine 调度 | 接口保留，registry 条目从 class 指向 preset 工厂，调度层加 priority |
| 配置层 | PityDef 扁平字段、TOML 解析 | 字段保留，新增 priority，preset 工厂消费已有字段 |
| 测试资产 | 10 个类型的现有测试 | 全部转为等价性测试的基准真值来源 |

## 一、问题

### 1.1 组合爆炸（核心问题）

现有 [pity.py](gacha_simulator/core/pity.py) **全量 10 类**的正交组合已现裂痕（P55/P56 各自交付时各管一类，组合靠硬编码）：

```
rotating × soft = RotatingSoftBehavior          （SoftPityMixin 拼）
rotating × cr = RotatingCRBehavior              （继承 rotating 再叠加）
rotating × cr × soft = RotatingCRSoftBehavior   （mixin + 继承三层）
targeted × soft = TargetedSoftBehavior           （mixin 拼）
```

[`SoftPityMixin`](gacha_simulator/core/pity.py#L509) 缓解了 soft 维度，但 cr 是 RotatingBehavior 子类（[pity.py:556](gacha_simulator/core/pity.py#L556)）、targeted 是独立类（[pity.py:615](gacha_simulator/core/pity.py#L615)）。新增任意拓扑维度（如 inverse 必歪），将与每个现有维度再组合。每类重复实现 `_scope_total_prob`/`_featured_slots`/`_is_trigger_rarity` 骨架（[pity.py:490-498](gacha_simulator/core/pity.py#L490-L498)、[pity.py:694-698](gacha_simulator/core/pity.py#L694-L698) 等多处），after_draw（状态更新）与 before_draw（概率修正）硬编码耦合在各类的 if/else 里。**counter 驱动的 soft/hard 另起一套基类，与事件驱动完全不通**。

### 1.2 剩余缺口盘点（2026-08-24 核实，含双信源）

| 缺口 | 现状核实 | P64 角色 |
|------|---------|---------|
| G1 幻塔连中后必歪 | 真缺口——rotating 只支持「歪→必中」，不支持「中→必歪」 | 新增 `ForceNonFeatured` Modifier + inverse preset |
| G16 幻塔完全不重置 | 单行——[`_should_reset`](gacha_simulator/core/pity.py#L200-L203) 加 `reset="never"` 分支 | **独立先行**（独立 commit，不并 P64） |
| G19 尘白禁区不歪池 | **✅ 矛盾已解决（2026-09-18 独立调研）**：确认真实机制为「每次出金 100% 为当期 UP」。依据：三个相互独立信源直述同一规则（snowbreak.gg / Steam 社区 / Stage1st）+ 期望值数学自洽（不歪池综合出金率 1.24% 时拿 UP 期望约 80.6 抽，与米池的 80.65 抽相等；若提前出金仅 50% 为 UP，期望应约 121 抽，与三方实测数据冲突）+ 官方对米池必写「占出率 50%」而对特选池从不写该条款的对比。手册已据此修正：§15.3 配置由 `hard(target_featured=true)` 改为 `targeted(fate_threshold=0)` 加 `selected_card_init`；§15.4「165 箱当前无此机制」改为「P58 已覆盖」；§21 G19 行同步 | **已处置**；顺带发现手册全部 `targeted` 配置均缺 `selected_card`（见下方注） |

> **2026-09-18 顺带发现（手册层面，P64 范围外）**：手册的 `targeted` 配置除本次修正的尘白 2 处外，其余 **7 处**均未配 `selected_card_init`：绝区零 `epitomized_weapon`（定轨武器，`fate_threshold=1`）与 `bangboo_select`（邦布池，`=0`）；鸣潮 `wengine_targeted`（定轨武器，`=1`）、`ww_standard_weapon_select`（常驻武器，`=0`）、`ww_beginner_select`（新手池，`=0`）；§十四 `lds_mixed_select`（`=1`）；异环 `yihuan_wp_targeted`（武器定轨，`=1`）。**这不是配置缺陷**——`selected_card` 是运行时状态，定轨类玩法本就由策略层经 `switch_epitomized_target`（[gacha_service.py:292](gacha_simulator/service/gacha_service.py#L292)）在模拟中设定目标，把目标写死在 TOML 里反而与机制不符。但手册原先未说明这一点，读者照抄且不配策略时会遇到保底不生效且无任何提示。**已处置**：手册 §〇「保底 type 速查」补说明，列出两条设置途径与静默退化的行为。实测依据：`targeted` 的必中分支条件为 `self._guaranteed.is_set() or (selected and ...)`（[pity.py:652](gacha_simulator/core/pity.py#L652)），只判 `selected` 是否非空（实测填不存在的卡 ID 与填真实卡 ID 效果相同，均使概率由 0.001/0.001 变为 0.002/0.0）；`after_draw` 在 `selected is None` 时直接 return，命定值不累积。

### 1.3 保底相关缺口完整盘点（2026-08-24 逐条核实，双信源纪律）

> 信源纪律：两个以上不同信源一致且无矛盾才能确定为机制，否则标注「待确认」。见 [feedback-search-report-discipline](../../../.claude/projects/d--Users-DELL-Desktop-gacha-simulator----------/memory/feedback-search-report-discipline.md)。

| 缺口 | 语义 | 归属 |
|------|------|------|
| G13 战双新手首次 40 | `hard.threshold` 首次特殊值（[手册:2304](docs/主流抽卡游戏卡池机制配置转换手册.md#L2304)，40 vs 60） | 🟢 配置即可（2026-08-24 双信源确认：[caoteng951](https://www.caoteng951.cn/tengzx01/4662.html) + [9game](https://www.9game.cn/zspms/4456638.html)）：`hard(threshold=60, counter_init=20)`，首次 40 触发、归零后续 60 |
| G2 阴阳师神眷阈值 | 神眷 = 「出 SSR/SP 概率掉落 + 累抽 450/800 必定获得」（[手册:2284](docs/主流抽卡游戏卡池机制配置转换手册.md#L2284)，机制双信源确认 2026-08-24：[17173 2023](http://news.17173.com/z/yys/content/01112023/111739115.shtml) + [9game 2023](https://www.9game.cn/yys/9780872.html)） | 🟡 **milestone 层扩展（2026-08-24 归属修正）**：神眷是兑换道具（资源），「必定获得」本质是累抽奖励（milestone at=动态 threshold），非保底概率；450/800 依赖全图鉴状态（跨系统状态）。与 G14（pity 动态 threshold）分属两系统，P64 范围外 |
| G14 战双命运池浮动 | 每次保底周期随机 T∈[80,100]、非保底出 S 1.5%、出 S 重置重抽 T（[手册:2305](docs/主流抽卡游戏卡池机制配置转换手册.md#L2305)，机制双信源确认 2026-08-24：[doyo](https://www.doyo.cn/news/26839.html) + [taptap 数学分析](https://www.taptap.cn/moment/15230243631530325)） | 🟡 后续扩展方向：T 分布未公布（U13）；确认后 P64 条件谓词可表达「counter ≥ 随机 T」 |
| G5 绝区零执行顺序 | 福利保底（`hard(max_triggers=1)`）应先于 targeted——当前 `_BTYPE_ORDER` hard=1 < targeted=3 已满足（[手册:554](docs/主流抽卡游戏卡池机制配置转换手册.md#L554) 描述过时，2026-08-24 核实） | ✅ **纳入 P64 主线**：显式化现有隐式顺序 + 提供覆盖能力（调度层 `priority`），见 §3.6 |
| G15 pjsk 加权抽数 | 付费石双倍天井进度（[手册:2306](docs/主流抽卡游戏卡池机制配置转换手册.md#L2306)，付费 +1 / 免费 +0.5） | 🔴 **缺口（2026-09-21 重估）**：原记「🟢 近似可配」（`reward.resources_gained` 每抽按池注入 + exchange pool 兑换 50/100 档），但按「精确建模原则」（CLAUDE.md §二）近似不计入已覆盖。该近似有语义打折（卡附带产出 vs 动作进度）与配置脆性（全 reward 需配）两处偏差，严格语义需 milestone `weight_by_pool`（milestone 层，P64 范围外） |
| G3 崩坏3 UP 保护排除已拥有 | 精准补给每 50 抽必出 UP 装备，但**已获得的装备从 UP 组中排除**（[手册:963](docs/主流抽卡游戏卡池机制配置转换手册.md#L963)） | ✅ **归本计划**（2026-09-21 裁决）：做**真实建模**，需 S8 卡级管道（子集定向）+ S9 状态可见性（读 `acquired`），方案见 §3.10.4。原记「pool 层过滤」属近似（会让普通抽卡也不出已拥有装备），已按「精确建模原则」否决 |

> **关键洞察**：G14（战双命运池）是 pity 层「hard 触发条件的动态化」（threshold 每次重置随机 T）：P64 的「条件谓词 → 概率修正」抽象若延伸到 counter 驱动型可统一表达（hard 本身即「counter ≥ threshold → ForceFeatured」特例），记为后续扩展方向。G2（阴阳师神眷）是 milestone 层「累抽奖励动态 threshold」（450/800 按全图鉴状态，2026-08-24 归属修正），非 pity 层。G13 已由 `counter_init=20` 配置即可表达（2026-08-24 双信源确认），非扩展方向。

### 1.5 P82 并入：保底管道执行顺序（2026-09-16 实测完成）

**合并说明**：P82（保底管道顺序接通）于 2026-09-16 并入本计划，P82 文件归档。其结论直接影响 §1.3 的 G5 项与 §3.6 的 priority 设计，**已于 2026-09-18 裁决，见本节末的裁决结论**。

**P82 的问题**：`_resolve_order()`（[pity.py:916](gacha_simulator/core/pity.py#L916)）会计算排序（稀有度 rank → type 顺序 → name），但其结果**只写入 `self._behavior_list`**，而三个调度入口（`get_probabilities` / `before_draw` / `after_draw`）走的是 `get_behaviors_for_pool()` → `spec.pity_names`，后者由 `batch_simulator.py:173-177` 按 **TOML 定义顺序**构造。即排序算了但未接入概率管道，`P30 #11` 的「顺序由定义顺序决定」在代码上仍成立。

**P82 的实测结论（2026-09-16）**：

| 配置场景 | 顺序是否影响结果 |
|---------|----------------|
| soft + soft（同 / 异目标槽位） | 否。概率变换数学可交换（手算 + 95 抽序列对比双重验证） |
| soft + hard | 否。hard 触发时覆盖一切，未触发时无作用 |
| rotating / targeted / hard 的各类组合 | 否 |
| **跨 scope（保 ssr + 保 sr）** | 否。层级保护使低稀有度保底不改变高稀有度保底的可窃取总量 |
| **含 `rotating_cr` 的组合** | **是**。46 组随机扫描中 12 组敏感，最大差异 30/95 抽 |

`rotating_cr` 敏感的根因是它**消费全局 `random`**（`before_draw` 内 `random.random() < cr_base_rate`），顺序改变导致随机流错位，属随机源共享的副作用，非概率语义上的顺序依赖。

**对 G5 / §3.6 priority 设计的影响（重要）**：

G5 的原设计是「`_resolve_order` 排序 key 加 `priority`」。P82 实测表明**单靠排序键无法表达顺序语义**：多数保底组合本就顺序无关（可交换），因此加 `priority` 后即使排序生效，也不会改变任何概率输出，仅对齐含 `rotating_cr` 配置的随机流。

实施 P64 时需先裁决以下三项（**已于 2026-09-18 裁决，结论见本节末**）：

| # | 待裁决 | 说明 |
|---|-------|------|
| 1 | `_resolve_order()` 存废 | 接线（让排序生效）/ 废弃（删除或标注未接通）/ 暂缓。P82 实测倾向废弃，因收益近零而引入「含 `rotating_cr` 配置结果会变」的语义成本 |
| 2 | `priority` 是否仍需引入 | 若裁决 1 为废弃，G5 的 priority 设计失去落脚点；若保留，需说明它要解决什么实际问题（当前 `_BTYPE_ORDER` hard=1 < targeted=3 已满足绝区零需求，[§1.3](#) 已核实）。**2026-09-16 补**：§3.1.5.5 的反例表明顺序并非普遍无关（`target_featured=True` 的 soft 与 hard 共存时结果不同），但该敏感性来自组合本身而非排序键，priority 能否覆盖它取决于裁决 1 的取向 |
| 3 | 新架构下顺序语义的归属 | 若 Tracker+Modifier 让 Modifier 变得可自由组合，需明确「组合顺序」是语义的一部分还是实现细节；P82 的实测数据（多数组合可交换）可作为该判定的依据 |

**P82 全文**：`docs/03-归档/P82 保底管道顺序接通——_resolve_order 未接入概率管道.md`（含完整机制链路、五种候选方案的取舍、四条风险分析、验收标准）

**裁决结论（2026-09-18，用户裁决）**

| # | 裁决 | 连带 |
|---|------|------|
| 1 | **接线**：让 `_resolve_order()` 的排序结果成为概率管道的实际执行顺序（P82 方案 A） | 见下方「接线实施方案」 |
| 2 | **保留 `priority`**：接线后「TOML 书写顺序」不再是可用的顺序控制手段，`priority` 成为唯一的覆盖入口；G5 原设计即含它，能力保留 | PityDef `priority` 字段 + `_resolve_order` 排序键插入 + GUI 控件（§3.6 M3） |
| 3 | **分两层定性**：保底**之间**的顺序由排序键决定，属语义的一部分（配置者经 `priority` 干预）；保底**内部**的 Modifier 链顺序由 preset 固定，属实现细节，不对外配置 | 文档中两处「顺序」须分开表述，避免混为一谈 |

**接线实施方案（2026-09-18 拟定）**

- **核心改动点**：`PityEngine.get_behaviors_for_pool()`（[pity.py:1189-1200](gacha_simulator/core/pity.py#L1189-L1200)）的输出顺序，三个调度入口共用它，改此处即改管道。
- **实现取向（推荐：独立排序视图）**：`PityEngine.__init__` 在 behavior 全部构造完成后，为每个 pool 预计算排序后的保底名列表（如 `self._pool_order: Dict[str, List[str]]`），`get_behaviors_for_pool()` 消费该视图；`PoolPitySpec.pity_names` **保持 TOML 顺序不动**。
  - 理由：`pity_names` 兼有第二职责——[banner.py:261](gacha_simulator/core/banner.py#L261) 用 `','.join(pity_spec.pity_names)` 生成 `draw_pity_names` 输出串，下游（[process_trace.py:123-125](gacha_simulator/core/process_trace.py#L123-L125)、[streaming.py:174-176](gacha_simulator/core/streaming.py#L174-L176)）以 `split(',')` + set 消费，**语义与顺序无关**，但字面顺序会进 golden 快照。独立视图使输出串保持不变，把行为变更面收窄到「概率管道顺序」一处。
- **排序键**：`(rarity rank, _BTYPE_ORDER, name)`（P55 既定），接线后 `_BTYPE_ORDER` 真正生效；`priority` 插入位置为 rank 之后、type order 之前（§3.6 M3）。
- **行为变更面**：仅「同一池内、书写顺序与排序键不一致」的配置受影响。已实测（P82 §六 + §3.1.5.5）敏感集合为两类：含 `rotating_cr` 者（随机流错位）、`target_featured=True` 的 soft 与 hard 共存者（真实概率语义）；其余组合数学可交换，接线不改变其输出。**2026-09-18 补第三类（实测新发现）**：跨 type 顺序发生反转且存在 `depends_on` 时，依赖方的状态键**创建时机**会变（旧顺序在源触发当轮就执行依赖方 `after_draw` 并创建其 `counter` 键；新顺序下该轮依赖方仍未激活、键延后到下次 `before_draw` 才创建）。实测（rotating 源 + hard 依赖，`pity_names` 由 `(source, dependent)` 反转为 `(dependent, source)`）：依赖方 `_active` 最终值不变（均为 True），但 `PityState` 快照的键存在性有差异。该差异只在 `depends_on` 配置中出现，当前 `config.toml` 无此配置。当前 `config.toml` 示例仅一条保底定义，不受影响。
- **验证要求（基线固化 + 等价对照）**：接线前用固定种子跑 `config.toml` 与既有测试配置，固化 `CompactResult` 快照；接线后同种子重跑逐字段对比，差异必须逐一归因到上述三类，否则视为回归。`tests/core/test_pity_integration.py::TestDependsOnIntegration` 与 `TestMultiPityCoordination` 两组用例是该验证的重点观察对象（前者的 `pity_names=('source', 'dependent')` 接线后会反转，断言仍应通过；后者 `('rot', 'hard90')` 同样反转，概率断言应不变）。
- **排期建议：独立先行**（同 G16 模式，独立 commit）。理由：与 P64 主线的重构正交、可独立验收；`_resolve_order`/`_validate_behaviors` 在 P64 §3.2 中的「逻辑零改动」结论不受影响。排期最终以用户裁决为准。

### 1.4 为什么旧分类掩盖了统一性（2026-08-24 新增）

counter 驱动难道不是事件驱动吗。每抽一次计数加一、出了 SSR 清零，这不就是事件驱动的状态机。soft 的记忆是无条件递增，rotating 是歪中翻转，targeted 是命中定轨清零——只是事件分支不同。两类本质是同一种东西，**记忆的不同形态**。

三个统一性被分类掩盖：

1. **状态原语统一**：P56 提炼的 Flag/Counter 已是通用原语，但被关在事件驱动一侧，counter 驱动另起一套计数逻辑，本可以是同一个 CounterTracker。
2. **生命周期统一**：`deactivate_on_early_hit`/`depends_on` 在 P55 只给 counter 驱动用，P64 计划想给事件驱动补上——说明它本就与驱动类型无关，是正交包装层。
3. **概率解读统一**：`SoftStepBehavior._compute_probabilities` 和 `RotatingBehavior.before_draw` 都在做「读状态算概率」，但因分属两类各写各的。

## 二、目标

- **用 Tracker + Modifier + Lifecycle 三元组重建全部保底类型**（不再分 counter 驱动 vs 事件驱动两类），现有 10 个类型退化为 **preset**（三元组的具名组合）
- 新机制 = 新增 Tracker 或 Modifier 零件，**不再写新类**；任意 Tracker × 任意 Modifier 自由组合
- **等价性保证（P64 验收核心）**：同配置下旧类 vs 新引擎，固定种子逐场对比概率分布 + 状态快照完全一致（全部类型，含 counter 驱动）
- 覆盖 G1（inverse preset）+ G16（独立先行 `reset="never"`）+ G5（调度层**接线** + `priority` 显式排序，2026-09-18 裁决，见 §1.5）+ G3（UP 保护排除已拥有，真实建模，2026-09-21 裁决，见 §3.10.4）
- PityEngine 调度层接口签名兼容（`_resolve_order` 加 `priority` 排序优先级，新增行为全 0 时与现状一致），GUI 参数描述（params/ui_params）不变

## 三、方案

### 3.0 领域本质——保底是什么

退回领域本质，忘掉现有 10 个类的名字。保底是一个数学对象：`P(本次出什么 | 历史)`。所有保底机制都在回答同一个问题——在给定历史下如何修改基础概率分布。历史只有两种形态，**计数**（抽了多少次没出）和**标记**（上次歪了还是中了）。概率修改也只有两种形态，**连续提升**和**离散强制**。

保底由三件独立的事组成：

```
历史 ──[Tracker 追踪]──→ 状态 ──[Modifier 修正]──→ 概率
                          ↑                       ↓
                        事件                     分布
                          └──[Lifecycle 生命周期]──┘  正交包装层
```

| 概念 | 职责 | 纯函数签名 | 中文 |
|------|------|-----------|------|
| Tracker | 看到什么事件，如何更新状态 | `(State, Event) -> State` | 追踪器 |
| Modifier | 当前是什么状态，如何修正概率 | `(State, BaseDistribution) -> Distribution` | 修正器 |
| Lifecycle | 这个机制什么时候活着 | 包装层（Always/Once/Dependent） | 生命周期 |

三件完全独立：Tracker 不管概率怎么算，Modifier 不管状态怎么来，Lifecycle 不管前两者是什么。一个保底机制就是三件的组合：`Pity = Tracker(s) + Modifier(s) + Lifecycle`。

**与旧分类的对比**：旧版把领域切成 counter 驱动 vs 事件驱动两类，每类内部再细分。新版按 Tracker/Modifier/Lifecycle 三个正交维度切，任意 Tracker × 任意 Modifier 自由组合。

### 3.1 抽象层（新建 `core/pity_tracker.py` + `core/pity_modifier.py`）

#### 3.1.1 Tracker（追踪器）—— `(State, Event) -> State`

Tracker 是 pure 函数：给定旧状态和本次抽卡事件，返回新状态。事件 = `PityContext`（含 `DrawInfo.reward_rarity/is_featured/reward_id` + `PityState`）。每个 Tracker 读写 `PityState` 中自己声明的键。

| Tracker | 语义 | 对应现有 | 状态键 |
|---------|------|---------|--------|
| `CounterTracker(scope, reset_on)` | 每抽 +1；出金重置：`reset_on="scope"`（出触发稀有度即重置）、`"featured"`（仅 featured 重置）、`"never"`（永不重置，G16） | CounterBasedBehavior 计数逻辑 | `counter` |
| `FlagTracker(judge, inverse)` | 出 scope 时，judge 命中/未命中翻转标记 | RotatingBehavior guaranteed | `guaranteed` |
| `StreakTracker(judge, threshold, probs)` | 连续未命中计数，未命中 +1、命中清零；叠加随机拦截（CR） | RotatingCRBehavior cr_counter | `cr_counter` |
| `FateTracker(judge)` | 出 scope 时，命中定轨清零多键/未命中累积多键 | TargetedBehavior fate/losses | `fate_points`, `losses`, `guaranteed`, `lost_rotating`（另**读**外部注入的 `selected_card`，见 L4） |

> **G16 自然落位**：`CounterTracker(reset_on="never")` 去掉重置规则即可，无需特殊分支。
> **G13 自然落位**：`CounterTracker(init=20, threshold=60)` 首次 40。
> **G14 自然落位**（后续扩展）：`RandomThresholdTracker(range=(80,100))` 每次重置随机阈值。

**计数器相位（N1，强制，2026-09-16 定稿）**

问题：旧 `CounterBasedBehavior.before_draw`（[pity.py:179-187](gacha_simulator/core/pity.py#L179-L187)）与 `SoftPityMixin.before_draw`（[pity.py:529-533](gacha_simulator/core/pity.py#L529-L533)）都是**先自增、再用自增后的值算概率**，实测 `hard(threshold=90)` 首次 100% 出现在**第 90 抽**。若把递增放到 `after_draw`，第 90 抽读到 89、首次触发落到第 91 抽。总次数两者相同，差的是**读相位**，故「每抽加一次」的表述覆盖不了它。

**方案（计数型 Tracker 分两段，非计数型只在 after 侧）**。「计数型」的界定必须**显式列出**：`CounterTracker.counter` 属计数型（旧 `before_draw` 推进）；`StreakTracker.cr_counter` **不属**（旧实现只在 `after_draw` 累加与清零，[pity.py:590-600](gacha_simulator/core/pity.py#L590-L600)），若按「计数器」字面把它划入计数型，`advance` 会每抽多推进一次。

| 方法 | 调用点 | 计数型 Tracker | 非计数型 Tracker |
|------|-------|---------------|-----------------|
| `advance(ctx, state, name, readonly)` | `Pity.before_draw` 首段 | `readonly=True` 只读不写；否则 `counter += 1` | no-op |
| `commit(ctx, state, name)` | `Pity.after_draw` | 命中时 `counter ← 0` | 置位/清位/累积 |

与旧实现结构同构（旧代码本就是 before 侧 `incr()`、after 侧 `reset()`），故在未触发下述例外时，`state` 中的计数值与旧实现逐位相同，「状态快照逐场一致」这条验收无需适配。

**例外（`deactivate_on_early_hit`，2026-09-16 补）**：旧 `CounterBasedBehavior.after_draw`（[pity.py:189-198](gacha_simulator/core/pity.py#L189-L198)）在 `_on_reset(ctx)` 返回 True 时**提前 return，跳过 `_counter().reset()`**；而 `SoftStepBehavior._on_reset` / `HardPityBehavior._on_reset`（[pity.py:329-337](gacha_simulator/core/pity.py#L329-L337)、[pity.py:405-413](gacha_simulator/core/pity.py#L405-L413)）恰在 `deactivate_on_early_hit=True` 时清 `_active` 并返回 True。实测：`hard(threshold=90, deactivate_on_early_hit=True)` 在第 5 抽命中后 counter 仍为 5（未重置），无该配置时归 0（概率流不受影响，差异只落在状态快照与 `get_counter()`）。故 `commit` 的语义须是「**Lifecycle 退役动作与重置同序判定，退役则跳过重置**」，不能写成无条件的「命中即归零」。

**已排除的替代方案**：把 `counter_init` 与重置值都改成 1，使 after 侧递增也能对齐读数。数学上可对齐，但 `state` 中的值会整体偏移 1（抽完第 1 抽后 counter 为 2，而旧实现为 1），连带快照对比、`get_counter()` 查询、GUI 展示、`counter_init` 的用户含义（G13 的 `counter_init=20` 表示「已垫 20 抽」）全部平移，把一处相位约定扩散成全局数字偏移。

**不选「读时虚拟 +1」**：那会让「Modifier 读到的值」与「state 中的值」相差 1，任何读 counter 的下游代码都要区分用途，是长期负债。

**测试断言**：`hard(threshold=90)` 首次 100% 出现在第 90 抽；`soft` 的 boost 起始抽数；`readonly=True` 查询不推进计数。


**did_fire 统一语义（M4，强制，2026-09-16 裁决）**：`Pity.did_fire` 供 `PityEngine.after_draw` 的 depends_on 激活传播使用（[pity.py:1340](gacha_simulator/core/pity.py#L1340)，全代码唯一调用点）。**统一语义 = 「本次抽卡是否让本保底回到初始状态」**，由各 Tracker 的 `did_reset(ctx, state, name)` 提供，`Pity.did_fire = any(tr.did_reset(...))`。

现状三类并不一致，`did_reset` 需把 rotating/targeted 收严：

| 旧类 | 现状 did_fire | 统一后 `did_reset` | 变化 |
|------|--------------|-------------------|------|
| counter 驱动（soft/hard） | `_should_reset(ctx)`，按 `reset` 配置（[pity.py:200-206](gacha_simulator/core/pity.py#L200-L206)） | 同左（`scope`→出该稀有度；`featured`→出 featured，**无 scope 门控**） | 无 |
| rotating | `ctx.draw.is_featured`（[pity.py:500-503](gacha_simulator/core/pity.py#L500-L503)） | 出 scope ∧ is_featured | **加 scope 门控** |
| targeted | `_is_hit(ctx)`，即 `reward_id == selected`（[pity.py:699-701](gacha_simulator/core/pity.py#L699-L701)） | 出 scope ∧ reward_id == selected | **加 scope 门控** |

> **2026-09-18 注**：上表「现状 did_fire」列记录的是 2026-09-16 统一**之前**的行为，所引行号已随该次修改指向统一**之后**的代码（其中 rotating/targeted 两行现已含 scope 门控）。该列仅作历史对照，勿据以判断当前实现。

**理由**：现状的 rotating/targeted 在「出非 scope 稀有度的 UP」时 `did_fire` 为真，但其状态并未翻转（`after_draw` 的 scope 门控把它们挡在外面），`depends_on` 依赖方因此被提前激活。统一后 `did_fire` 与 `after_draw` 里的重置分支**严格同条件**。

**影响面（行为变更，激活只会更严格、不会更宽）**：现有 `config.toml` 无 `depends_on`；`tests/core/test_pity_integration.py` 的被依赖方为 rotating、抽到的是 SSR featured，两种语义下同为 True。

**✅ 已于 2026-09-16 独立落地**（早于 P64 主线）：`RotatingBehavior.did_fire` 与 `TargetedBehavior.did_fire` 各加 scope 门控，`RotatingCRBehavior` 的冗余覆写删除。验证方式为「用改动前的 `pity.py` 跑新增测试」，`TestDidFireUnified` 5 例中 3 例失败（正是测 scope 门控的 3 例），确认测试有效；落地后全量 `pytest` 1573 passed，确认无隐藏依赖。P64 实施时应按此语义写 `did_reset`，勿回退。

**三点须显式声明（2026-09-16 补）**：

1. **`never` 行是新增后的语义，不是现状**：现有 `_should_reset` **没有** `never` 分支，恒 False 只是「稀有度字符串永不等于 `'never'`」的偶然结果。该分支由 §3.8 的 G16 独立先行新增。
2. **`featured` 的不对称是有意保留**：counter 驱动型的 `featured` 分支只看 `is_featured`、无 scope 门控（[pity.py:201-202](gacha_simulator/core/pity.py#L201-L202)），与 rotating/targeted 统一后带 scope 门控的语义不同。它属 `reset` 配置的既有语义，不在本次统一范围内；但须写明，否则「did_fire 统一」会被误读为三类完全同构。
3. **`reset` 取值无白名单，未知值静默永不重置（P64 范围外）**：`create_behavior` 仅在 `pdef.reset` 为 truthy 时透传该参数（[pity.py:879-880](gacha_simulator/core/pity.py#L879-L880)，故空串回退 `scope`）；一旦传入非空值，`_should_reset` 便对其做 `reward_rarity == reset` 比较（[pity.py:200-203](gacha_simulator/core/pity.py#L200-L203)），故任何既非 `'featured'` 又不等于稀有度名的值（如 legacy 值 `'featured_ssr'`）恒 False（永不重置）。**2026-09-18 更新**：原描述的触达路径已随 P81 B11 消失——`_migrate_legacy_pity`（旧 TOML 自动迁移）整函数删除，改为 `_check_pity_format()` 对旧格式显式抛 `ConfigError`（[config_toml.py:385-421](gacha_simulator/core/config_toml.py#L385-L421)）；`tests/test_config_toml.py` 中守护该值的 `TestMigrateLegacyPity`/`test_reset_preserved` 亦被 `TestRejectLegacyPityFormat` 整类替换。**缺陷本体不变**——新格式 TOML 的 `reset` 仍无取值白名单（[config_toml.py:687](gacha_simulator/core/config_toml.py#L687) 直接透传），手写 `reset = "featured_ssr"` 仍恒 False。已独立登记为保底系统 [03-审计.md](docs/01-活跃/subsystems/保底系统/03-审计.md) 异常 6（状态：待裁决）。

**键集语义（L4，等价性前提）**：Tracker 声明的键**仅当初始值为 truthy 时才预建 state 键**（`if init: set()`），与旧 `_build_pity_state_init`（[pity.py:987-1023](gacha_simulator/core/pity.py#L987-L1023)）在 `guaranteed_init=False`、`counter_init=0`、`fate_points_init=0` 时不预建键的行为一致。

**两个例外（实现不得套用 truthy 规则）**：

1. `selected_card` 是**无条件注入**（同函数内 `state.set(pdef.name, "selected_card", sc)`，`sc` 为 None 也写），targeted 家族的初始快照里必然有该键。若新实现按 truthy 规则处理，`to_dict()` 比对会少该键。
2. `selected_card` 的**写入者不是 Tracker**，而是策略层的 `NonDrawAction`（[gacha_service.py:292](gacha_simulator/service/gacha_service.py#L292)、[gacha_service.py:294](gacha_simulator/service/gacha_service.py#L294)），`FateTracker` 只读它。故 Tracker 允许读「不由自己声明的键」，`selected_card` 的初始化路径独立于 Tracker 声明。

#### 3.1.2 Modifier（修正器）—— `(State, BaseDistribution) -> Distribution`

> **2026-09-21 修订**：本表已由 **§3.14** 修订（**条件外置**：触发条件从各 Modifier 内部提出为独立的 Condition 对象，效果实现不变）。本表保留作历史形态与术语索引，实施以 §3.14 为准。

Modifier 是 pure 函数（除 InterceptModifier 显式依赖 RNG）：给定当前状态和基础分布，返回修正后分布。**实现形态为乘性因子向量**（§3.1.5.1）：每个 Modifier 产出一个因子 `m`，链式应用即逐元素相乘再归一化。「列表顺序」因此退化为**因子求值的先后**，不再是可交换性的来源（可交换性由 §3.1.5.5 的判据决定）。语义上全部复用 `_redistribute_scope` 的「scope 内重分配」。

| Modifier | 语义 | 对应现有 | 触发条件 |
|----------|------|---------|---------|
| `BoostModifier(deltas, scope)` | 读 counter 算 boost% 提概率（连续提升） | SoftStepBehavior._compute_probabilities | Always（计数驱动） |
| `ForceFeaturedModifier(flag, scope)` | 标记置位 → 目标组 100% | rotating/CR guaranteed 分支 | `state[flag] == True` |
| `ForceNonFeaturedModifier(flag, scope)` | 标记置位 → 非 UP 100%（**G1 新增**） | 幻塔必歪 | `state[flag] == True` |
| `ForceSelectedModifier(flag, card)` | 标记/阈值满足 → 定轨卡（或子集）100% | targeted _resolve_selected_slots | `state[flag] or fate_ready` |
| `InterceptModifier(probs, base_rate)` | 读 streak 计数 + 掷随机数决定是否拦截为 100% UP | CR before_draw 随机分支 | 计数+随机 |
| `ThresholdForceModifier(threshold, scope)` | 计数 ≥ threshold → 强制 100% | HardPityBehavior | `counter >= threshold` |
| `BaseRatioModifier(scope)` | 按当前比例 redistribute（兜底） | rotating/targeted 默认分支 | Always |

**Modifier 链契约（强制）**：Pity 的 `before_draw` 按 `modifiers` 列表**顺序应用、非短路**，每个 Modifier 在前一个的输出上操作（因子逐元素相乘）。覆盖型 Modifier（ForceFeatured 把非目标槽位置 0）以因子 0 吸收前序调整，这正是 §3.1.5.5 吸收引理的实现对应。soft 抬高的 scope 总量在 guaranteed 下全部流入 featured，与旧 SoftPityMixin「先 soft 后事件」等价。

**分布空间归属（D20，2026-09-21 新增）**：Modifier 的输入输出是**卡级**分布（真实分布）。「槽位」是操作内部的临时聚合表示，由操作自行聚合与还原（还原即对单卡概率施加统一缩放，语义为「保持组内当前比例」）。管道不再以槽位级向量作为传输格式，`banner.py` 的 `scale_factors` 还原段随之删除。收益有三：① **单卡定向**成为可能（双 UP 池定轨、G3 的「UP 组排除已拥有」，二者本受同一约束制约）；② 消除聚合与还原的往返；③ 让 §3.1.5 的乘性算子形式直接覆盖实现。代价见 §3.1.5.4 的让步声明与 §六 的等价性口径放宽。**实施方案（改哪些函数、接口怎么变、边界怎么处理）见 §3.9**。

**InterceptModifier 随机数消耗协议（H4，强制，2026-09-16 补短路条件）**：rotating_cr 旧类 before_draw 用模块级 `random.random()`（[pity.py:576](gacha_simulator/core/pity.py#L576)、[pity.py:583](gacha_simulator/core/pity.py#L583)）做条件分支，消耗次数随分支而定。`InterceptModifier` 必须在**完全相同的条件与顺序**下消耗相同数量的随机数，否则固定种子轨迹即刻分叉。实现为**单决策 Modifier**：guaranteed 或 readonly 时不触发（返回 None）；非 guaranteed 时按 cr_base_rate / cr_state_probs 判定，命中返回 ForceFeatured 分布、未命中返回 None。等价性测试必须含 `cr_state_probs` 含 (0,1) 中间值的用例。

**短路条件（不可省略）**：旧实现两处消费均带前置短路，`self._cr_base_rate > 0 and random.random() < ...` 与 `state_prob > 0 and random.random() < state_prob`。故 `cr_base_rate == 0` 或 `state_prob == 0` 时**不消耗**随机数，`state_prob >= 1.0` 分支同样**不消耗**。若 `InterceptModifier` 写成 `if random.random() < rate`（省去 `> 0`），配 0 的场合会多消耗一个随机数、随机流整体后移。现状代码在这一点上是正确的，本条仅为实施约束。

**另三条须逐位复刻的协议内容（2026-09-16 补）**：

1. **下标裁剪**：`idx = min(cr_counter.value(), len(cr_state_probs) - 1)`（[pity.py:578](gacha_simulator/core/pity.py#L578)）须原样保留，取值下标是裁剪后的 `idx`，不是 `cr_counter` 本身。
2. **空表分支不消耗**：`cr_state_probs` 为空列表时 `idx = -1`、`if idx >= 0` 为假（[pity.py:579](gacha_simulator/core/pity.py#L579)），整段 state_prob 检查被跳过、**不消耗**随机数。这是第三条不消耗路径，短路枚举须含它。
3. **链中位置固定**：旧实现的 CR 判定发生在 soft（mixin 先算，[pity.py:529-533](gacha_simulator/core/pity.py#L529-L533)）之后、父类 `R_r` 之前，故 `InterceptModifier` 在 Modifier 链中的位置必须固定在 `BoostModifier` 之后，否则随机流位置改变。

#### 3.1.3 Lifecycle（生命周期）—— 正交包装层

| Lifecycle | 语义 | 对应现有 |
|-----------|------|---------|
| `AlwaysActive` | 永远生效 | 默认 |
| `OnceActive(max_triggers=1)` | 触发 N 次后退役（福利保底） | hard(max_triggers=1) |
| `DependentActive(depends_on)` | 依赖另一个 Pity 激活 | depends_on 图 |

Lifecycle 独立于 Tracker/Modifier，只管 `is_active` 判定和 `deactivate_on_early_hit` 统一（P64 增量能力，使事件驱动型也可用；**必须同步移除 [config_toml.py:652-660](gacha_simulator/core/config_toml.py#L652-L660) 的拒绝分支 H3**）。

**`is_active` 早退对事件驱动型是行为变更（2026-09-16 补，须与等价性范围显式隔离）**：旧实现中只有 `CounterBasedBehavior` 读写 `_active`（[pity.py:180](gacha_simulator/core/pity.py#L180)、[pity.py:190](gacha_simulator/core/pity.py#L190)），`RotatingBehavior` / `TargetedBehavior` **完全不读它**；而引擎的 depends_on 传播会**写** `_active`（[pity.py:1342](gacha_simulator/core/pity.py#L1342)）。即旧实现里「事件驱动型配了 `depends_on`」是**惰性**的：标志被写入但无人读，`before_draw` / `after_draw` 照常执行。

§3.1.4 骨架在 `before_draw` / `after_draw` 首行统一做 `is_active` 早退，会让这类配置**真正生效**（未激活前不改分布、不更新状态）。这是概率流改变，不是「只收严」，故：

- 属 P64 增量能力，须**单独验收**（判据：配 `depends_on` 的事件驱动型，激活前 `before_draw` 返回原分布、`after_draw` 不更新状态）
- 等价性验收须**显式排除**「事件驱动型 + `depends_on`」这类配置，否则与 N1/M4 的等价性主张冲突

#### 3.1.4 统一 Pity 骨架

```python
class Pity(PityBehavior):
    """统一保底骨架——Tracker + Modifier + Lifecycle 三元组。"""
    def __init__(self, *, name, state, scope, btype,
                 trackers: List[Tracker],
                 modifiers: List[Modifier],
                 lifecycle: Lifecycle = AlwaysActive(),
                 priority: int = 0):
        self._name = name; self._state = state
        self._scope = scope; self._btype = btype
        self._priority = priority
        self._trackers = trackers; self._modifiers = modifiers
        self._lifecycle = lifecycle
        self.is_event_driven = True  # 统一后不再区分 counter/event
        # 状态键由各 Tracker 声明，Pity 统一创建 Flag/Counter 遥控器
        # Lifecycle 初始化 _active 标记

    def _rebind_state(self, state):          # P75 纪律——统一实现
        self._state = state
        for tr in self._trackers: tr.rebind(state, self._name)
        self._lifecycle.rebind(state, self._name)

    def before_draw(self, ctx, readonly=False):
        if not self._lifecycle.is_active(self._state, self._name):
            return ctx.current.copy()
        for tr in self._trackers:            # N1：计数型先在 before 侧推进
            tr.advance(ctx, self._state, self._name, readonly=readonly)
        out = ctx.current.copy()
        for mod in self._modifiers:
            nxt = mod.apply(ctx, self._state, self._name, out, readonly)
            if nxt is not None:
                out = nxt                    # 链式应用（非短路）；S8 后即因子逐元素相乘
        return out

    def after_draw(self, ctx):
        if not self._lifecycle.is_active(self._state, self._name):
            return
        for tr in self._trackers:            # N1：此处只落重置/翻转/累积
            tr.commit(ctx, self._state, self._name)
        if self._lifecycle.should_deactivate(ctx, self._state, self._name):
            self._lifecycle.deactivate(self._state, self._name)

    def did_fire(self, ctx):
        # M4：统一为「本次抽卡是否让本保底回到初始状态」
        return any(tr.did_reset(ctx, self._state, self._name) for tr in self._trackers)
```

### 3.1.5 形式化：表达力与顺序判据（2026-09-21 乘法因子版重写）

> **本节定位**：描述 **S8 完成后**架构的数学形态（卡级分布 + 乘性因子向量）。S1–S5 期间的 Modifier 内部实现沿用槽位法（与旧类逐位一致，等价性由 §六 实测保证）；S8 把算子实现切换为因子法后，本节直接覆盖实现。
>
> **重写理由（2026-09-21）**：原版以槽位空间上的三个基本算子 `{B, R, F}` 为基底，与「概率操作统一为卡级乘性因子」这一目标形态不同构；原引理 2.1/2.2/2.3 描述的多是槽位结构的偶然性质（如「单槽位使组内重写退化」），在卡级管道下不再成立。乘法版把可交换性判据压缩为一条复合律加一条吸收引理，判据从「逐条引理」变为「逐元素比较因子」。

#### 3.1.5.1 定义：乘性算子

一次抽卡有 n 个互斥结果（实现里即池中的卡，或等价地槽位）。所有概率分布构成单纯形

```
Δⁿ⁻¹ = { p ∈ Rⁿ : pᵢ ≥ 0, Σᵢ pᵢ = 1 }
```

**乘性算子**由一个因子向量 m ∈ Rⁿ（m ≥ 0 逐元素）定义：

```
Φ_m(p) = (m ⊙ p) / ⟨m, p⟩,     其中  ⟨m, p⟩ = Σᵢ mᵢ pᵢ
```

即「逐元素乘因子，再归一化」。它把「概率操作」从『分布到分布的任意映射』收缩为『用一个非负向量调制分布』，这是本节全部论证的基础。

**性质 1（对数坐标）**：log Φ_m(p) = log p + log m − log⟨m,p⟩。乘性算子在 log 空间是**加性平移再归一化**，即指数族的自然参数平移。

**性质 2（良定义条件）**：⟨m, p⟩ > 0 当且仅当 m 在 p 的支撑上不全为零。这是本形式化唯一的边界来源，见 3.1.5.6。

#### 3.1.5.2 三个基本算子的因子形式

记 scope 为 S，目标集 T ⊆ S，`p(A) = Σ_{c∈A} p_c`，`P = p(S)`。

| 算子 | 语义 | 因子 m_c |
|------|------|---------|
| `R_r(T)` | scope 内重分配，使 T 占 scope 总量的比例恰为 r，scope 总量不变 | c ∈ T：`rP / p(T)`；c ∈ S\T：`(1−r)P / (P − p(T))`；其余：1 |
| `F(T)` | **全池置零**后 T 占满 scope，**更高稀有度槽位还原原值** | c ∈ T：`P / p(T)`；c ∈ S\T：0；**更高稀有度槽：1**（还原）；**更低稀有度槽：0** |
| `B_β(T; Q)` | 从源集 Q 取比例 β，按 p 比例转给 T | c ∈ T：`1 + β·p(Q)/p(T)`；c ∈ Q：`1 − β`；其余：1 |

**归一化系数 ⟨m,p⟩ 的取值（逐项验算，2026-09-21 独立审查修正）**：`R_r` 与 `B_β` 在 `T ⊊ S`、`T ∩ Q = ∅` 时恒为 1；`F` 恒为 `P + p(更高稀有度)`，仅当 scope 为最高稀有度时等于 1（这正是 `HardPityBehavior` 保留高层级槽位的效果）。

三者都只需 `Φ_m` 的归一化即可正确落地，故 ⟨m,p⟩ 是否等于 1 **不影响正确性**；但「复合时无须归一化、可直接相乘」这一便利只在 ⟨m,p⟩ = 1 时成立。旧算子的 ⟨m,p⟩ = 1 主要源于其设计本就保持全局概率和为 1。

**与旧实现的对应**：`R_r` 由 `_redistribute_scope(ctx, r, ...)` 实现；`F` 由 `HardPityBehavior._compute_probabilities` 实现；`B_β` 由 `SoftStepBehavior._compute_probabilities` 实现。

**基底的完备性**：还须计入恒等元 `id`（m ≡ 1）。所有早退路径（`counter < τ`、`pool <= 0`、`scope_slots` 为空、featured 槽位为空等）返回的都是恒等元。

**组内比例的语义（关键）**：`R_r(T)` 的因子在 T 内**是常数**（T 内所有 c 乘同一个数），等价于「**保持组内当前比例**」。而旧实现在目标槽内按**基础权重 w** 重写。两者在「组内比例 = 基础权重比例」时数值相同，一旦存在卡级定向（如 targeted 锁定单卡）就分开。S8 采用**保持当前比例**语义，理由见 3.1.5.3 与 3.1.5.4。

#### 3.1.5.3 复合律与顺序敏感的两类来源

**复合律**：

```
Φ_{m₂}(Φ_{m₁}(p)) = (m₁ ⊙ m₂ ⊙ p) / ⟨m₁ ⊙ m₂, p⟩      （m₂ 在 Φ_{m₁}(p) 处取值）
```

**判据的正确用法（2026-09-21 审查修正）**：可交换性**不能**由「因子是否依赖分布」直接判定——`B_β` 的因子含 `p(Q)/p(T)`（依赖当前分布），却与同类可交换（§3.1.5.5 推论表第 1 行）。唯一可用的判据是**逐元素比较两种顺序下的因子乘积**（吸收引理为其特例）。因子依赖分布只是「**可能**不可交换」的来源：它使 `m₂` 的求值点随顺序改变，是否真的改变乘积须逐元素验证。

**顺序敏感的两类来源（2026-09-21 定性）**：

| 类型 | 例子 | 性质 |
|------|------|------|
| **约束冲突（语义）** | `soft(target_featured=True)` 与 `hard` 共存 | 两个算子对同一 scope 的约束无法同时满足，顺序即裁决方式。**这是语义正确的表现**，不是缺陷 |
| **随机数消费（实现）** | 含 `rotating_cr` 的配置 | 因子本身可交换，但 `InterceptModifier` 消费全局 `random`，换序导致随机流错位。数学上若随机源独立则无影响，它只影响固定种子下的可复现性与样本路径。**这是实现绑定的副作用** |

对第一类，正规处置是**显式定义组合语义**（当前为顺序执行 + §1.5 裁决的 `priority` 覆盖），而非消除敏感。另有一种理论上可行的替代语义是**约束求解**（把每个保底写成对分布的约束，求解满足全部约束的分布），它能彻底消除顺序敏感且冲突时较严约束自然胜出，代价是每个算子都须能写成约束形式（带随机拦截的 `rotating_cr` 写不了），且求解远比顺序应用昂贵。当前采用顺序执行是工程上的取舍。

#### 3.1.5.4 定理 1（表达力包含）

**命题**：在组内比例不变式

```
p_c / p(C_s) = w_c / w(C_s)      （对每个槽 s 及其卡集 C_s）
```

成立的前提下，旧 10 类的每个概率算子都等价于三个基本乘性算子的有限复合；每个状态转移 T 都是条件赋值语句的有限复合。

**证明**（构造性）：

| 类型 | 概率算子 | 状态转移 T |
|------|---------|-----------|
| `soft_step` | `B_β(T)` | 出 scope 时 `counter ← 0` |
| `hard` | `F(T)`（触发时），否则 `id` | 同上 |
| `rotating` | `R_r(S_f)`，r = 1 若 guaranteed，否则 `p(S_f)/p(S_c)` | 出 scope 时 `guaranteed ← is_featured` |
| `rotating_cr` | 命中 ? `R_1(S_f)` : `R_r(S_f)` | 父类 + 出 scope 且 ¬was_g 时 `cr ← is_featured ? 0 : cr+1` |
| `targeted` | （guaranteed 或 fate 就绪）? `R_1(T_sel)` : `R_r(S_f)` | 命中定轨卡时四键清零，否则四键累积 |
| 各 `_soft` | 父算子 ∘ `B_β` | 父类 T 加 counter 清零 |

每个算子长度不超过 2；每个 T 只含条件赋值，无循环、无跨调用内存。

**唯一须显式声明的让步**：旧算子在目标组内按**基础权重**重写，乘性算子在目标组内按**当前比例**缩放，两者仅在不变量成立时数值相同。故本定理是「**不变式下包含**」，而非原版的「严格包含」。代价换来的是 3.1.5.3 的复合律，以及卡级定向（targeted 锁定单卡、G3 从 UP 组排除已拥有）的表达能力。

> **`rotating_cr` 的命中分支是 `R_1` 而非 `F`**（2026-09-16 核对结论，乘法版沿用）：它由 `_force_featured`（[pity.py:586-589](gacha_simulator/core/pity.py#L586-L589)）实现，内部调 `_redistribute_scope(ctx, 1.0, ...)`，只把 scope 内总量给 featured、scope 外原样保留。实测同一输入（0.5 / 0.5 / 0.08 / 0.9）下 `_force_featured` 得 {ssr_featured: 0.02, ssr: 0, sr: 0.08, r: 0.9}，`F(S_f)` 得 {ssr_featured: 1.0, ssr: 0, sr: 0, r: 0}。结论不因此改变（`R_1 ∈ {R}`），但构造表须按 `R_1` 记。

**效力**：本定理证的是**表达力包含**（存在一个 preset 表达旧行为），不保证实现出的 preset 与旧代码位级一致（浮点运算顺序差异），后者由等价性测试承担。

#### 3.1.5.5 定理 2（可交换性判据）

由 3.1.5.3 的复合律，可交换性判定归结为**逐元素比较两个顺序下的因子乘积**；实践中只需一条引理：

**吸收引理**：若算子 `Φ_m` 在某集合 U 上取 `m|_U = 0`，则任何**先于**它作用的算子在 U 上的因子都被吸收（乘 0 得 0），故复合在 U 上可交换且结果恒为 0。

**推论表**（重算版）：

| 组合 | 可交换 | 依据 |
|------|-------|------|
| soft + soft（同 scope，同目标集） | 是 | `B_β` 的因子在源集上为常数 `1−β`，相乘可交换；复合等价于 `B_{1−(1−β₁)(1−β₂)}` |
| soft + soft（同 scope，异目标集） | 是 | 实测 200 组无反例。两算子目标集不同，但不互相写入对方的源集，逐元素相乘顺序无关 |
| soft + soft（异 scope） | 是 | 低稀有度算子的源集与目标集都落在高稀有度算子的源集之内 |
| soft(T_soft = S) + hard | 是 | **2026-09-21 审查修正**：soft 的目标集等于整个 scope 时其源集为空（[pity.py:299-300](gacha_simulator/core/pity.py#L299-L300) 的 `if not non_target: return result`），`B` 退化为恒等，可交换性**平凡成立**。原论证「`F` 在源集 Q 上取 0，由吸收引理」中的 T 只能是 hard 的目标集，与行标签的 T（soft 的目标集）不是同一个集合，属指代冲突 |
| **soft(target_featured=True) + hard** | **否** | `F` 的零点集是 `S \ T`，而 T 收窄为 featured 后该集合**仍然有量**（非 featured 的 standard 槽），`B` 在那里仍能取量，吸收引理前提不满足 |
| 含 `rotating_cr` 的组合 | 否 | 非代数问题：因子本身可交换，但 `InterceptModifier` 消费全局 `random`，换序导致 ω 消费位置改变、样本路径分叉 |

**反例实测（2026-09-16，对 P82 §六 结论的修正；乘法版结论不变）**：soft(`target_featured=True`，deltas 使第 6 抽起 boost) + hard(threshold=8)，两种 `pity_names` 顺序，12 抽概率序列对比：

```
target_featured=False  顺序敏感抽数 = []                    （与 P82 结论一致）
target_featured=True   顺序敏感抽数 = [8, 9, 10, 11, 12]     （反例）

第 8 抽（hard 触发那一抽）：
  [soft, hard] = {'sr': 0.0, 'ssr': 0.5, 'ssr_featured': 0.5}
  [hard, soft] = {'sr': 0.0, 'ssr': 0.2, 'ssr_featured': 0.8}
```

**故 P82 的「仅含 `rotating_cr` 的配置会变」应修正为「含 `rotating_cr`，或 `target_featured=True` 的 soft 与 hard 共存的配置会变」。**

**原引理 2.3 的处置**：原版引理 2.3 称「在当前槽位结构下，参数取『保持当前比例』的 `R` 是恒等映射，原因是单槽位使组内重写退化」。乘法版下该引理**不再需要**：`R_r(T)` 的因子在 T 内是常数、在 `S\T` 内也是常数，当 r 取「当前比例」时两个常数均为 1，恒等性直接由因子读出，无须借助槽位结构。

#### 3.1.5.6 未覆盖（边界）

| 项 | 为何只能测 / 说明 |
|----|-----------|
| 位级一致 | 定理 1 保证构造存在，不保证浮点运算顺序一致；卡级管道下聚合次数随算子数增加，差异量级仍在 1e-16，但 §六 的等价性口径须由「完全一致」放宽为「容差内一致」 |
| 随机数消费次数 | 可证，但需先把 H4 的短路条件写死，再把 ω 显式化为消费序列逐位比对 |
| 全配置组合 | 组合空间过大，采样测试只覆盖有限点；本节的判据用于缩小「必须实测」的范围 |
| **因子在 p 的支撑上全为零** | 由性质 2，此时 `Φ_m` 未定义（⟨m,p⟩ = 0）。语义上这是「提升一个概率为零的集合」，物理上不应发生（保底不作用于零概率组）。实现约定：返回原分布，与现行早退路径一致 |
| **`p(T) = 0`（目标组当前无概率）** | 因子 `P/p(T)` 除零**发散**——与上一行方向相反（不是全零而是无穷），`F` 与 `R` 均受影响，实测抛 `ZeroDivisionError`。由 §3.9.5 的 `T == 0` 分支处理（返回恒等） |
| **`T = S` 且 `r < 1`** | `S\T` 为空，⟨m,p⟩ = 1 − (1−r)·P ≠ 1。§3.1.5.5 推论表的 `soft(T = S)` 一行即此情形，其可交换性论证须按此重述 |
| **`B_β` 的 `T ∩ Q ≠ ∅`** | 因子的三项推导依赖 T 与源集不交；当前实现源集取「非目标集」故不交成立（[pity.py:295-302](gacha_simulator/core/pity.py#L295-L302)），但这是**隐含前提**，须显式声明 |
| 约束求解语义 | 3.1.5.3 提到的替代组合语义未实现，其表达力与代价未评估 |

---

### 3.2 preset 映射（现有 10 类 → preset，含 counter 驱动统一）

registry（[pity.py:714](gacha_simulator/core/pity.py#L714)）条目新增 `preset` 字段（工厂函数），`class` 字段对事件驱动型置空；counter 驱动型（soft_step/hard）同步 preset 化。`create_behavior` 检测 `entry.get("preset")` 走新路径。

```python
def _preset_rotating():
    return dict(
        trackers=[FlagTracker(judge="featured", hit="clear", miss="set", flag="guaranteed")],
        modifiers=[ForceFeaturedModifier(flag="guaranteed"), BaseRatioModifier()],
        flags={"guaranteed": False},
    )

def _preset_hard():
    return dict(
        trackers=[CounterTracker(scope="ssr", reset_on="scope")],
        modifiers=[ThresholdForceModifier(threshold=90), BaseRatioModifier()],
        counters={"counter": 0},
    )

def _preset_soft_step():
    return dict(
        trackers=[CounterTracker(scope="ssr", reset_on="scope")],
        modifiers=[BoostModifier(deltas=((73,0),(17,5.88))), BaseRatioModifier()],
        counters={"counter": 0},
    )
```

| 现有 type | preset 三元组（含完整状态声明，H2 补全） |
|-----------|------------------------------------------|
| hard | Tracker: CounterTracker(reset_on="scope")；Modifier: [ThresholdForce(threshold), BaseRatio] |
| soft_step | Tracker: CounterTracker(reset_on="scope")；Modifier: [BoostModifier(deltas), BaseRatio] |
| soft_interval/soft_additive | 同 soft_step，deltas 由 preset 工厂展开（M6：`_SOFT_SUFFIX_TYPES` 展开职责从 `SoftPityMixin._init_soft_pity` 移入工厂） |
| rotating | Tracker: FlagTracker(judge="featured")；Modifier: [ForceFeatured(guaranteed), BaseRatio]；Flag: guaranteed |
| rotating_soft | rotating + CounterTracker + [BoostModifier, ForceFeatured, BaseRatio]（含 **触发稀有度重置抽数 counter**：hit/miss 两分支都 ResetCounter，对齐 [pity.py:534-537](gacha_simulator/core/pity.py#L534-L537)） |
| rotating_cr | rotating + StreakTracker(judge="featured", **was_guaranteed 守卫**：仅抽前 guaranteed 未置位时更新，对齐 [pity.py:590-600](gacha_simulator/core/pity.py#L590-L600))；Modifier: [ForceFeatured(guaranteed), InterceptModifier, BaseRatio] |
| rotating_cr_soft | rotating_cr + BoostModifier（含 counter 重置 + was_guaranteed 守卫） |
| targeted | Tracker: FateTracker(judge="selected"，**补全 losses/lost_rotating**，对齐 [pity.py:666-669](gacha_simulator/core/pity.py#L666-L669)、[pity.py:672-675](gacha_simulator/core/pity.py#L672-L675))；Modifier: [ForceSelected(guaranteed_or_fate_ready), BaseRatio]；Flags: guaranteed, lost_rotating；Counters: fate_points, losses |
| targeted_soft | targeted + BoostModifier（含 counter 重置） |

`_btype` 保留，故 `_resolve_order`（[pity.py:916](gacha_simulator/core/pity.py#L916)）/ `_validate_behaviors`（[pity.py:933](gacha_simulator/core/pity.py#L933)）排序校验逻辑零改动（**2026-09-18**：P82 接线独立先行后，排序结果被 `get_behaviors_for_pool()` 消费；P64 主线不改其排序逻辑，仅经 M3 新增 `priority` 键）。`params`/`ui_params` 保留，GUI 参数控件零改动。

### 3.3 G1 inverse preset（新增）

幻塔连中必歪：出 UP 后下一次 SSR 必非 UP。与 rotating 对偶：

```python
def _preset_rotating_inverse():
    return dict(
        trackers=[FlagTracker(judge="featured", hit="set", miss="clear", flag="forced_loss")],
        modifiers=[ForceNonFeaturedModifier(flag="forced_loss"), BaseRatioModifier()],
        flags={"forced_loss": False},
    )
```

注册为 `rotating_inverse`（display_name「反向轮换保底（连中必歪）」）。`ForceNonFeaturedModifier` 复用 `_redistribute_scope` 反向调用。

### 3.4 软保底统一（不再分阶段二）

新架构下 soft 不再是 mixin，而是 `CounterTracker + BoostModifier`。**无需分阶段**，全部 10 个类型在同一阶段 preset 化：

- `SoftStepBehavior`/`HardPityBehavior` 同步退役为 preset（CounterTracker + 对应 Modifier）
- `SoftPityMixin` + 3 个 `_soft` 类同步退役
- **deltas 展开职责移交（M6）**：`SoftPityMixin._init_soft_pity` 唯一做 `soft_start/soft_end/soft_increment → deltas` 展开（[pity.py:511-528](gacha_simulator/core/pity.py#L511-L528)），退役后该展开移入 preset 工厂（依赖 create_behavior 已透传的 soft_* 参数，[pity.py:864-874](gacha_simulator/core/pity.py#L864-L874)）

`rotating_soft` = rotating 的 Tracker/Modifier 各加一项，`_SOFT_SUFFIX_TYPES` 处理移除；任意 Tracker × 任意 Modifier 自由组合，不再需要每组合一个类。

### 3.5 Lifecycle 统一（P64 增量能力）

`deactivate_on_early_hit` 目前只在 counter 驱动型（[pity.py:334-336](gacha_simulator/core/pity.py#L334-L336)、[pity.py:410-412](gacha_simulator/core/pity.py#L410-L412)）实现，且 config_toml 对事件驱动型配置该参数直接抛 ConfigError（[config_toml.py:652-660](gacha_simulator/core/config_toml.py#L652-L660)）。P64 统一进 Lifecycle 包装层，使全部类型可用。**必须同步移除 config_toml 的拒绝分支（H3）**，否则增量能力无法配置。**此为增量能力（旧事件驱动类无此能力），不在等价性范围内**。覆盖手册 §16.6 终末地 80/120 协调「若 120 用 rotating 表达」的场景。

### 3.6 与引擎/配置/GUI 对接

- **PityEngine**（[pity.py:1124](gacha_simulator/core/pity.py#L1124)）：调度层接口签名不变，`before_draw`/`after_draw`/`get_probabilities` 调用链不变，P75 rebind 由 Pity 统一实现。**G5 priority（2026-09-18 裁决：保留并实施，与接线配套）**：`_resolve_order`（[pity.py:916](gacha_simulator/core/pity.py#L916)）排序 key 加 `priority` 优先级（位于稀有度 rank 之后、type order 之前）。**透传（M3）**：`PityDef` 新增 `priority: int = 0`，`create_behavior` 构造后设置 `pity._priority` 属性（Pity 与 counter 驱动统一，不改构造签名）——priority 全 0 时排序结果与现状完全一致，显式 priority 覆盖 type 顺序。**论证**：接线（§1.5 裁决 1）使排序键成为管道顺序的唯一来源，配置者不再能靠「TOML 书写顺序」控制优先级，`priority` 因此成为唯一的顺序覆盖入口；当前 `_BTYPE_ORDER` hard=1 < targeted=3 已满足绝区零 G5 需求，priority 的价值是「显式化现有隐式顺序 + 提供未来场景覆盖」。**接线本身建议独立先行（§1.5 实施方案），本项随主线实施**
- **PityDef/TOML**：现有 type 名继续有效（preset 别名）；`rotating_inverse` 新 type 无需新字段；`PityDef.priority` 新增；参数透传（[pity.py:864-892](gacha_simulator/core/pity.py#L864-L892)）逻辑保留，目标从具体类变 preset 工厂
- **GUI config_panel**：**2026-09-18 事实修正（两处）**——① 保底 type 下拉**不是** registry 驱动，而是硬编码列表 `_PITY_TYPES`（[config_panel.py:2019-2031](gacha_simulator/gui/config_panel.py#L2019-L2031)，10 项；[config_panel.py:2084](gacha_simulator/gui/config_panel.py#L2084) 处 `addItems`），新增 `rotating_inverse` 须**手工追加**该列表，否则 GUI 不可选（由 registry 驱动的是**参数控件**，[config_panel.py:2765-2772](gacha_simulator/gui/config_panel.py#L2765-L2772)，该部分「零改动」成立）；② **GUI 现无 reset 控件**，`_apply_pity_edit` 不写 `pd['reset']`，`reset` 仅在 load/save 路径透传（[config_panel.py:6349](gacha_simulator/gui/config_panel.py#L6349)、[config_panel.py:7190](gacha_simulator/gui/config_panel.py#L7190)），故 G16 的 GUI 部分是**新建控件**而非「下拉加一项」；③ priority 编辑控件（G5）同为新建；参数控件零改动
- **config/config.toml**：新增幻塔 `rotating_inverse` + G16 示例配置
- **GachaService 定轨识别（H1，强制）**：[gacha_service.py:275](gacha_simulator/service/gacha_service.py#L275) 用 `isinstance(bh, TargetedBehavior)` 识别定轨保底（`switch_epitomized_target`/`cancel_epitomized_path` 两条 NonDrawAction 流程）。targeted preset 化后 bh 变为 `Pity` 实例，isinstance 恒 False → 定轨流程整体失效。须改为 `getattr(bh, '_btype', '') in ('targeted', 'targeted_soft')`（或 Pity 加 `_is_targeted` 标记），波及范围表补 `service/gacha_service.py`
- **G14 动态 threshold（后续扩展）**：`RandomThresholdTracker(range=(80,100))` 每次重置随机阈值，`ThresholdForceModifier` 读随机阈值判定，与 G16 同属 Tracker 维度扩展，无需新 Modifier

### 3.7 范围边界（不建模）

- **G2 阴阳师神眷动态 threshold**：属 milestone 层累抽奖励（见 §1.3），P64 范围外
- **`switch_allowed`/`switch_resets_progress`（定轨切换规则）**属 GachaService 策略层职责（P56 NonDrawAction），切换逻辑 P64 不改；**定轨识别方式须适配 preset 化**（§3.6 H1，isinstance → `_btype` 判断），否则 P56 定轨流程失效
- **槽位粒度约束（S8 前的既有边界，2026-09-21 实测）**：`compute_scope_mappings` 对每个稀有度只生成一个 featured 槽，故同一稀有度下的多张 featured 卡**共享一个槽位**，槽内各卡的相对比例恒等于基础权重比例（槽位级算子只做统一缩放，无机制可改组内比例）。后果是**双 UP 池的定轨失真**：`targeted` 锁定其中一张后，必中触发时该槽位按基础权重平摊（实测 `up_a` = `up_b` = 50%），目标卡拿不到 100%。此约束继承自 P56，P64 §3.1.5 亦未解除；由 **S8 的卡级管道**解决（目标集合可细到单卡）。另注：崩坏3 的 G3（UP 组排除已拥有）受同一约束制约，手册原将其归为 pool 层是架构约束下的权宜。**2026-09-21 裁决：G3 做真实建模**（依 CLAUDE.md §二「精确建模原则」，不接受 pool 层近似），需 S8 的卡级管道加上 §3.10 的状态可见性，方案见 §3.10.4
- **G15 pjsk 加权抽数**：**2026-09-21 重估**——原记「🟢 近似可配（reward 注入 + 兑换池）」，但按「精确建模原则」（CLAUDE.md §二）近似不计入已覆盖，本条改为**待消除的缺口**；严格语义需 milestone `weight_by_pool`（milestone 层，P64 范围外）
- **跨保底状态读取**：**不纳入**（2026-09-21 裁决，依手册全量查证「零真实需求」），且由 §3.10.3 的 `StateView` 在架构上关闭。关联需求走 `depends_on`（声明式依赖边）或状态合并
- **`type="custom"` 完全声明式 TOML 状态机不实现**（用户裁决，过度设计）——如需「组合内置片段」，在 preset 数据化之上小步扩展（阶段三预留，不承诺）

### 3.8 G16 独立先行（`reset="never"`）

幻塔「出金不重置」单行改动，**独立 commit 先行**，不并 P64 主线（counter 驱动与事件驱动在新架构下本就统一为 Tracker 维度，但 G16 作为单行能力独立可先交付）：

```python
# 新架构：CounterTracker(reset_on="never") 即永不重置，无特殊分支
# 旧架构兼容（G16 先行阶段，P64 主线前）：
def _should_reset(self, ctx):                       # pity.py:200
    if self._reset == "featured":
        return ctx.draw.is_featured
    if self._reset == "never":
        return False                                # 新增：永不重置
    return ctx.draw.reward_rarity == self._reset
```

配套：PityDef/config_toml 的 reset 枚举加 `"never"`、GUI **新建 reset 输入控件**并加「永不重置」选项（现无该控件，见 §3.6 事实修正）、一条测试、手册 G16 从「🔵 待 P64」改「✅ 已覆盖」。P64 主线落地后该分支由 `CounterTracker(reset_on="never")` 自然承载。

### 3.9 概率操作路径重构（S8 实施方案，2026-09-21 新增）

> §3.1.2 的 D20 是**声明**（分布空间归属改为卡级），§3.1.5 是**数学形式**（乘性算子），本节是**实施方案**（改哪些函数、接口怎么变、边界怎么处理）。三者配套，缺一则 S8 不可执行。
>
> **过渡期纪律**：S1–S5 期间本节内容全部**不实施**，Modifier 内部沿用槽位法，以保证与旧类位级一致（§六 S1–S5 口径）。S8 一次性切换，验收对 S5 产物取 1e-12 容差。

#### 3.9.1 现状路径与目标路径

**现状**（[banner.py:226-248](gacha_simulator/core/banner.py#L226-L248)，卡级与槽位级往返四次）：

```
probabilities = {r.id: p for r, p in pool.rewards}              # 卡级
rarity_probs  = aggregate_probs_by_rarity(pool, pity_spec)      # 卡级 → 槽位级（聚合）
adjusted      = pity_engine.before_draw(key, state, rarity_probs)   # 槽位级管道
if rarity_probs != adjusted:
    scale_factors = {slot: new / old for slot, new in adjusted.items()}   # 算缩放
    for rwd_id in probabilities:                                # 槽位 → 卡级（还原）
        slot = f'{infer_rarity_from_spec(rwd_id, spec) or "ssr"}_featured' 或稀有度名
        if slot in scale_factors:
            probabilities[rwd_id] *= scale_factors[slot]
pool._apply_probabilities(probabilities)
```

**目标**（S8 后，往返全部消失）：

```
probabilities = {r.id: p for r, p in pool.rewards}              # 卡级
adjusted      = pity_engine.before_draw(key, state, probabilities)   # 卡级管道
pool._apply_probabilities(adjusted)
```

净删除：`aggregate_probs_by_rarity` 的调用（banner 侧）、`scale_factors` 段（11 行）、`infer_rarity_from_spec` 的槽位反查用途。

#### 3.9.2 Modifier 接口：产出因子，引擎做归一化

**接口变更**（S8）：Modifier 从「返回修正后的分布」改为「返回因子向量」，归一化收到引擎层统一做。

```python
class Modifier:
    def factor(self, ctx, view, dist, readonly) -> Optional[Dict[str, float]]:
        """返回因子向量 {card_id: m}；未列出的卡默认 m = 1；None 表示恒等。

        view：状态视图。S8 期间是 PityState 的薄包装（可读全部命名空间），
              S9 后收紧为「只含自身命名空间」的 StateView（§3.10.3）。
              签名按最终形态定型，避免两阶段各改一次。
        """

# Pity 骨架
for mod in self._modifiers:
    m = mod.factor(ctx, self._view, out, readonly)
    if m is not None:
        out = _apply_factor(out, m)      # (m ⊙ out) / ⟨m, out⟩

def _apply_factor(dist, m):
    out = {c: dist[c] * m.get(c, 1.0) for c in dist}
    total = sum(out.values())
    return dist if total <= 0 else {c: v / total for c, v in out.items()}
```

> **与 §3.1.4 骨架的关系**：本节的内循环（`mod.factor(...)` + `_apply_factor`）在 S8 替换 §3.1.4 骨架 `before_draw` 中的 `mod.apply(...) -> out` 三行；S1–S5 期间按 §3.1.4 原样实现，`factor()` 方法在 S8 引入（过渡期可保留 `apply()` 作为默认实现，`factor()` 缺省时回退到它）。

**为什么归一化放引擎层**：§3.1.5.2 已证三个基本算子的 ⟨m,p⟩ 恒为 1，归一化在数学上是恒等操作；但把它放在引擎层有两个好处：① Modifier 只负责「算出调制系数」，职责单一；② 边界（⟨m,p⟩ = 0）只需在一处处理。`dist` 参数保留在 `factor()` 中，因为因子依赖当前分布（`R_r` 的因子含 `p(T)`，见 §3.1.5.2 表）。

**因子向量按稀疏给出**：Modifier 只需列出被改动的卡，其余默认 1。组级操作给出整组的因子，单卡定向给出单张的因子，两者是同一种东西（这正是 §3.1.5 与「槽位收回操作内部」合流之处）。

#### 3.9.3 组件处置表

| 组件 | 处置 | 说明 |
|------|------|------|
| `PoolPitySpec.scope_cards` / `featured_cards` | **保留** | 卡集合，是分组的真相源；Modifier 据此确定 scope 与 target |
| `PoolPitySpec.scope_slots` / `featured_slots` / `card_to_slot` | **删除** | 槽位名与卡→槽位映射在卡级管道下无消费者。`_resolve_selected_slots` 的目标定位改为直接给出卡集合 `(selected,)` |
| `compute_scope_mappings` | **改造** | 只产出 `scope_cards` / `featured_cards`（及其反向索引），不再生成槽位名 |
| `aggregate_probs_by_rarity` | **删除** | 唯一调用点在 [banner.py:227](gacha_simulator/core/banner.py#L227)；同时清 `core/__init__.py` 的导出 |
| `_redistribute_scope(ctx, ratio, total, target_slots, scope)` | **替换** | 改为卡级版 `factor_redistribute(dist, scope_cards, target_cards, ratio, base_weights)`，产出因子向量而非新分布 |
| `infer_rarity_from_spec` | **保留**（用途收窄） | 2026-09-21 审查修正：其调用者中，pool.py:270/275 在 `aggregate_probs_by_rarity` 内、banner.py:242/244 与 :209 在 `scale_factors` 段内，**均在 S8 的删除范围内**；`_infer_rarity`（[pity.py:1344](gacha_simulator/core/pity.py#L1344)）用的是 `spec.ssr_ids` / `scope_cards` 而非本函数。故 S8 后其**唯一消费者**是 `banner.py` 的同一段——须在 S8 时确认是否还有保留价值 |
| `DrawInfo.scope_slots` / `featured_slots` / `card_to_slot` | **删除** | 随 `PoolPitySpec` 同步；`DrawInfo.base_probabilities` 语义由「槽位级」改为「卡级」 |
| `service/batch_simulator.py` | **改造** | [batch_simulator.py:183-192](gacha_simulator/service/batch_simulator.py#L183-L192) 解包 `compute_scope_mappings` 的五元组并构造含槽位字段的 `PoolPitySpec`——与 worst_impact 同属构造点，须同步改造。**2026-09-21 审查补** |
| `core/__init__.py` | **改造** | 除 `aggregate_probs_by_rarity` 外，`_redistribute_scope` 的导出（[core/\_\_init\_\_.py:20](gacha_simulator/core/__init__.py#L20)、`:117`）在 S8 替换后亦须一并处理。**2026-09-21 审查补** |
| `tests/` | **改造** | 6 个文件直接消费槽位结构：`test_pity_rotating.py`（import 并调用 `_redistribute_scope`）、`test_pity_integration.py` / `test_pity.py` / `test_pity_lifecycle.py` / `test_pity_targeted.py`（构造带槽位字段的 `PoolPitySpec`）。**2026-09-21 审查补** |
| `core/worst_impact.py` | **改造** | 第二处 `PoolPitySpec` 构造点（[worst_impact.py:506-548](gacha_simulator/core/worst_impact.py#L506-L548)），其中含**硬编码槽位名**（`{'ssr': ('ssr', 'ssr_featured')}`、`card_to_slot[cid] = 'ssr_featured'` 等回退分支）。S8 后只构造卡集合字段（`scope_cards` / `featured_cards` / `featured_ids` / `ssr_ids`） |
| `Pool._apply_probabilities` | **保留** | 接收卡级分布，语义不变 |
| `CompactResult` 输出字段 | **不受影响** | 已核对：无槽位相关字段（`draw_pity_names` 等均为池/保底名，非槽位名） |

#### 3.9.4 卡级版重分配辅助

`_redistribute_scope` 的卡级对应物，是所有组级 Modifier 的公共落点：

```python
def factor_redistribute(dist, scope_cards, target_cards, ratio):
    """把 scope 内总量按 ratio 分给 target 组；两侧都写因子，故 ⟨m,p⟩ 恒为 1。

    关键：ratio >= 1（目标占满 scope）时，源侧必须**显式写 0 因子**而非跳过。
    跳过会让 ⟨m,p⟩ = 1 + (P − T) ≠ 1，归一化不再是恒等操作，目标组只能拿到
    P/(1+P−T) —— 实测 ratio=1、T/P=0.3 时目标仅占 scope 的 58.8% 而非 100%，
    直接破坏所有 Force 型路径（ForceFeatured / ForceSelected / G3）。
    """
    P = sum(dist[c] for c in scope_cards)
    T = sum(dist[c] for c in target_cards)
    tset = set(target_cards)
    m = {}
    if T > 0 and ratio > 0:
        k = ratio * P / T
        for c in target_cards:
            m[c] = k
    if P - T > 0:
        if ratio >= 1:
            for c in scope_cards:
                if c not in tset:
                    m[c] = 0.0
        else:
            k2 = (1 - ratio) * P / (P - T)
            for c in scope_cards:
                if c not in tset:
                    m[c] = k2
    return m or None
```

三处与现状的差别：① 目标与源都是**卡集合**而非槽位名；② 组内按**当前比例**（因子在组内是常数）而非基础权重，语义理由见 §3.1.5.2「组内比例的语义」；③ 返回因子而非分布。

**单卡定向的写法**：`target_cards = (selected,)`，`T` 即该卡当前概率，因子 `k = ratio * P / T` 把它抬到 ratio·P。这就是 S8 解决双 UP 定轨失真（§3.7）与 G3（UP 组排除已拥有）的机制：前者传单卡，后者传「未拥有的 UP 子集」。

#### 3.9.5 边界处理

| 情形 | 处理 | 依据 |
|------|------|------|
| `T == 0`（`target_cards` 非空但组内当前概率为 0） | 目标因子跳过；`ratio < 1` 时**源侧仍会写因子**（源侧被缩放、目标不动） | 语义上是「提升一个概率为零的集合」，物理上不应发生（§3.1.5.6）。**2026-09-21 审查修正**：原稿称「与现行早退路径一致」属**引用错位**——`total <= 0` 的早退在 `SoftStepBehavior`/`HardPityBehavior` 内（[pity.py:278-279](gacha_simulator/core/pity.py#L278-L279) 等），不在 `_redistribute_scope` 调用链上；且现码在此情形走 `f_total_w > 0` 的 else 分支（按槽位均分兜底，[pity.py:427-430](gacha_simulator/core/pity.py#L427-L430)），与 S8 的行为不同 |
| `P == 0`（scope 内全零） | 同上 | 同上 |
| `P - T == 0`（目标占满 scope） | 只给目标加因子，源侧写 0 因子（`ratio >= 1` 分支），不跳过 | **2026-09-21 审查修正**：原稿称「现状已有等价分支」不成立——`_redistribute_scope` 的保护对象是**基础权重和 `Σw`**（[pity.py:425](gacha_simulator/core/pity.py#L425)、[pity.py:436](gacha_simulator/core/pity.py#L436)），不是 `P − T`。实测 `dist={a:0.5, b:0.0, c:0.5}`、`scope={a,b}`、`target={a}`、`ratio=0.5` 时，现码把零概率槽 `b` 从 0 造到 0.25，卡级版保持 0——两者**不等价**，须在 S8 验收中专项覆盖 |
| 归一化后总量 ≤ 0 | 返回原分布 | `_apply_factor` 内的退化保护 |

#### 3.9.6 对只读查询的影响

`PityEngine.get_probabilities(pool_id, state, base)` 与 `before_draw` 走同一路径，S8 后同样改为卡级进出。`readonly=True` 时 Modifier 不推进计数（N1 纪律），但**因子照算**——否则「查询」与「抽卡前」会给出不同分布，破坏 P16 的查询/修改分离语义。

**接线（§1.5）与 S8 的交互**：接线引入的 `_pool_order` 独立排序视图作用于「按哪个顺序遍历保底」，与本节改造的「单个保底内部如何算概率」是正交的两层，互不影响。

---

### 3.10 状态可见性与 G3 真实建模（2026-09-21 裁决）

#### 3.10.1 四类状态的处置

Modifier 在 `factor(ctx, ...)` 中能读到什么，是表达力的一个独立维度（与分布空间正交）。裁决如下：

| 状态 | 真实需求 | 裁决 | 依据 |
|------|---------|------|------|
| 本保底的状态 | 大量 | 保持 | 计数、标志、命定值等 |
| **其他保底的状态** | **零** | **不纳入**，且架构上关闭（3.10.3） | 手册全量查证（2026-09-21）：所有「清零 / 重置 / 联动 / 互斥」描述均属三类——保底自身计数被重置、同名保底跨池共享、资源生命周期（P77）；**无一处需读其他保底状态** |
| **GachaState**（持有 / 资源） | G3 一处 | **开放**，经 `reads` 显式声明（3.10.2） | CLAUDE.md §二「精确建模原则」：G3 不接受 pool 层近似 |
| 时间 | 零 | 不开放 | 时间型机制属 Banner lifecycle 层，P61 已覆盖 |

两处最像「跨保底读取」的机制已逐一排除：

- **绝区零 G5**：`hard(max_triggers=1)` 与 `targeted` 同时作用于同 scope（[手册:560](docs/主流抽卡游戏卡池机制配置转换手册.md#L560)）——这是**执行顺序**问题，由 §1.5 裁决的 `priority` 处理，不涉及状态读取
- **终末地计数器 3**：「获得首个 UP 后 240 抽」看似依赖另一保底的触发事件，实为**自身 Flag 门控**（出 UP 时置位，计数器仅在置位后推进），单保底内即可表达

#### 3.10.2 `reads` 声明机制

外部状态经配置**显式声明**才可读，避免隐式耦合。

```toml
[[pity]]
name = "bh3_precision_up"
type = "hard"
scope = "ssr"
target_featured = true
threshold = 50
reads = ["acquired"]        # 声明：本保底需要读「玩家持有」
```

```python
@dataclass
class PityContext:
    draw: DrawInfo
    current: Dict[str, float]
    state: 'StateView'
    external: Optional['ExternalView'] = None    # 按 PityDef.reads 填充；未声明则为 None

class ExternalView:
    """外部状态的只读视图——只暴露查询方法，不暴露可变对象。"""
    def owns(self, card_id: str) -> int: ...          # 该卡持有张数
    def balance(self, resource_id: str) -> float: ...
```

**校验（第三道防线的同类）**：`reads` 中的名称必须是已知状态源（`acquired` / `resources`），否则 `config_toml._build_pity()` 抛 `ConfigError`。**`time` 不列入白名单**——时间型机制属 Banner lifecycle 层（P61 已覆盖），保底层不需要读时间（§3.10.1）。**2026-09-21 审查修正：原稿 `ExternalView` 含 `now()`、白名单含 `time`，与 §3.10.1 的裁决自相矛盾**理由与 `scope` 白名单相同——**防止拼写错误导致保底静默失效**。

**填充通路（2026-09-21 审查补）**：`GachaState` 位于 `Banner.draw(state, ...)` 与服务层，而 `PityEngine` 目前只接收 `PityState`。S9 的取值方式为**给调度入口加可选参数**：

```python
PityEngine.before_draw(pool_id, state, base_probabilities, external=None)
PityEngine.get_probabilities(pool_id, state, base_probabilities, external=None)
```

既有调用方不传即保持原行为，故 §六 的「调度层接口签名不变」应理解为**既有调用形式不变**，而非参数列表冻结。填充者由 `Banner.draw` 担任（它同时持有 `GachaState` 与 `PityState`），按该池各保底 `reads` 的并集构造 `ExternalView`。§四 的波及范围须相应补 `core/banner.py`（S9）。

**在形式化中的位置**：资产是历史的确定函数 `w_t = W(h_t)`，读它只是读历史的一个摘要，故**不扩大 §3.1.5 的表达类**（仍是计数器自动机可计算的因果函数）。它扩大的是**方便性**（无须把资产编码进 PityState）与**显式性**（依赖进配置、进快照、可校验）。

#### 3.10.3 关闭跨保底读取（StateView）

现状有一个**无守卫的口子**：`PityState` 全局共享，Modifier 拿到的是整个对象，`state.get('别的保底名', 'key', 0)` 今天就能跑通且不报错。既然真实需求为零（3.10.1），处置是**架构上关闭**，而非把它正规化。

```python
class StateView:
    """限定在单个保底命名空间内的只读视图。"""
    def __init__(self, state: 'PityState', name: str):
        self._ns = state.data.get(name, {})
    def get(self, key, default=None):
        return self._ns.get(key, default)
```

Modifier 的 state 参数由 `PityState` 改为 `StateView`，读他人键天然返回 default。「跨保底读」由「靠纪律禁止」变为「架构上做不到」，且**不破坏任何现有机制**（真实需求为零；2026-09-21 独立审查已全库枚举 `PityState` 读取点：Modifier 内的读取全部落在自身命名空间，Modifier 外的读取不经 `state` 参数，不受影响）。

**命名空间绑定须显式（2026-09-21 审查补）**：组合型 `_soft` 族存在**两个**命名空间——`SoftPityMixin._init_soft_pity` 以 `name + '_soft'` 构造内部 `SoftStepBehavior`（[pity.py:527](gacha_simulator/core/pity.py#L527)），而 mixin 自身的 `_counter` 在 `name` 下。`StateView` 的 `name` 取哪个须在 S9 实施时明确，否则「读自己」也会返回 default，落进本文反复强调的静默失效模式。

**不影响 `depends_on`**：激活传播由引擎在 `PityEngine.after_draw` 中执行（`state.set(dep_name, "_active", True)`），不经过 Modifier，故不受 StateView 影响。

#### 3.10.4 G3 真实建模（崩坏3 精准补给）

机制（[手册 §7.3](docs/主流抽卡游戏卡池机制配置转换手册.md#L959)）：精准补给每 50 抽必出 UP 装备，但**已获得的装备从 UP 组中排除**。

**为什么不能沿用 pool 层近似**：pool 层过滤（把已拥有的卡从 reward 列表移除）会让**每次抽卡**都不出它们，而真实机制只作用于「50 抽 UP 保护」这一个触发点——普通抽卡仍可产出已拥有的装备。按「精确建模原则」这是语义打折，不接受。手册原先将其归为 pool 层，是架构约束下的权宜。

**实现**：新增 Modifier 零件 `ForceNotOwnedModifier`，即 §3.1.2 表中 `ForceSelectedModifier` 的**动态目标**变体：

```python
class ForceNotOwnedModifier:
    """把 scope 内总量强制导向「未拥有的目标卡」子集（G3）。"""
    def __init__(self, scope, field='featured_cards'):
        self._scope = scope
        self._field = field

    def factor(self, ctx, view, dist, readonly):
        pool_cards = getattr(ctx.draw, self._field).get(self._scope, ())
        target = tuple(c for c in pool_cards if ctx.external.owns(c) == 0)
        if not target:
            return None            # 全部已拥有——退化，返回恒等（§3.1.5.6）
        return factor_redistribute(dist, ctx.draw.scope_cards[self._scope], target, 1.0)
```

配套：配置加 `reads = ["acquired"]`；`BEHAVIOR_REGISTRY` 注册新 preset（或作为 `hard` preset 的可替换末位 Modifier——**待 S9 实施时定**）。

**「全部已拥有」的退化分支：待确认（2026-09-21 审查修正）**。手册 §7.1 / §7.3 / §21 均未描述该情形，**无信源**。当前拟定为「返回恒等」（无可导向目标），但这意味着该次 50 抽的「必出 UP」不发生，与手册「每 50 抽必 UP 装备」的字面表述可能冲突。按「不凭空断言」纪律标为**待确认**，实施前需查证游戏机制或由用户裁定。原稿直接判「合理选择」并为其设验收，属越权断言。

**与 §3.7 槽位粒度约束的关系**：G3 同时需要 S8（子集定向）与本节（状态可见性），两者都到位才可表达。

---

### 3.11 架构的表达能力与边界（2026-09-21 新增）

> **为什么单列一节**：P64 的定位是「通用保底引擎」，其价值取决于「能表达什么、不能表达什么」是否清晰可判。此前的边界信息散落在 §3.1.5.6（数学边界）、§3.7（范围边界）、§3.9.5（实现边界）、§3.10.1（状态裁决）四处，遇到新机制时判定成本高、且容易误判（本轮审查即发现 `F` 算子的定义被写错）。本节把三类信息集中，并给出**判定方法**而非仅列清单。

#### 3.11.1 表达能力（三层，互相正交）

| 维度 | 能力 | 形式化位置 |
|------|------|-----------|
| **状态空间** | `Z^k × {0,1}^m`：k 个计数器 + m 个标志，数量由 preset 静态声明 | §3.1.5.1 |
| **分布空间** | **卡级**任意子集上的乘性因子调制（S8 前为槽位级） | §3.1.5.2、§3.1.2 D20 |
| **状态可见性** | 本保底状态 + `reads` 声明的外部状态（`acquired` / `resources`）；**不含**其他保底状态 | §3.10 |
| 抽样模型 | 从分布独立抽样（`ξ ~ p`） | §3.1.5.1 |

**判定方法**：给定一个新机制，问三个问题——
1. 它的历史依赖能否用**有限个计数器/标志**声明？（能 → 状态空间够）
2. 它的概率操作能否写成**因子向量**？（能 → 分布空间够；注意因子可依赖当前分布）
3. 它需要读的信息是否在**本保底状态或 `reads` 白名单**内？（是 → 状态可见性够）

三问皆「是」则可表达，且实现方式是「新增 Tracker 或 Modifier 零件，不改架构」（§二目标）。

#### 3.11.2 边界（三类，各附判定依据）

| 边界 | 内容 | 依据 |
|------|------|------|
| **非抽样型抽卡** | 结果不是「从分布独立抽样」的机制（如异环棋盘：掷骰前进、落点由当前位置决定，属马尔可夫转移）。入口在 **pool 层**（`pool.draw`）而非 pity 层 | [手册 §20.2](docs/主流抽卡游戏卡池机制配置转换手册.md#L2039) |
| **跨保底状态耦合** | 「A 触发后修改 B 的状态」不能表达（`StateView` 架构上关闭，§3.10.3）。替代：`depends_on`（激活传播）、状态合并、或同名共享 | §3.10.1 裁决；手册全量查证「零真实需求」 |
| **求值顺序敏感** | 因子依赖当前分布时，换序一般改变结果（§3.1.5.3）。这是**语义属性**（约束冲突），非实现缺陷；处置方式为 §1.5 裁决的接线 + `priority` | §3.1.5.5 推论表 |

**另有一条数学边界**（`⟨m,p⟩ = 0` 等退化情形）见 §3.1.5.6，属实现层约定，不影响能力判定。

#### 3.11.3 不复用的邻近能力（避免误判）

- **时间型机制**（开池后 N 天概率提升等）属 Banner lifecycle 层（P61），不属保底
- **累抽奖励**（里程碑、补偿箱）属 milestone 层（P58），旁路注入而非改概率
- **池子可用性 / 切换**属 Banner lifecycle；**资源到期**属 `[resources.lifecycle]`（P77）
- **已获装备过滤**（G3）**属保底层**（2026-09-21 归属更正，见 §3.10.4）——它与 pool 层的 reward 分发相邻但不同：后者影响每次抽卡，前者只影响保底触发点

---

### 3.12 组合正确性验收（2026-09-21 新增）

> **问题**：P64 的核心承诺是「任意 Tracker × 任意 Modifier 自由组合，不再写新类」，但 §六 的验收全是**等价性**——验证 10 个 preset 与旧类一致。这只是「旧能力没有退化」，**完全没有验证新能力**。一个 `soft + rotating_cr + targeted` 三重组合在旧架构下没有对应的类，新架构声称能表达，却无任何测试证明它能正确工作。
>
> 组合空间无限，用例测试覆盖不了，必须换方法。

**3.12.1 不变式断言（性质测试）**

对随机生成的零件组合，断言以下性质恒成立：

| 不变式 | 内容 |
|--------|------|
| 归一性 | `Σ p = 1`（容差 1e-12） |
| 非负性 | 所有卡的概率 ≥ 0 |
| 因子合法性 | 所有因子 ≥ 0；因子在 p 的支撑上不全为 0 |
| 状态键合法 | Tracker 写入的键在其声明集内（`StateView` 保证读，写侧需另查） |
| 确定性 | 同种子 + 同配置 → 逐位相同 |

**3.12.2 合法组合判据**

不是所有组合都有意义，需要定义「合法」并在构造期检查（与 `_validate_behaviors` 的四条规则同层）：

- 同一键被两个 Tracker 声明的冲突（如两个 `CounterTracker` 都写 `counter`）
- Modifier 引用了不存在的状态键
- Lifecycle 依赖图成环（现有 `_build_activation_graph` 已部分覆盖）

**3.12.3 与等价性验收的分工**

| | 验证什么 | 方法 |
|---|---|---|
| 等价性（§六 主线） | 旧能力未退化 | 与旧类逐场对比 |
| 组合正确性（本节） | 新能力可用且自洽 | 性质测试 + 合法组合判据 |

两者互补：等价性是「守」，组合正确性是「攻」。

---

### 3.13 不变式运行时校验（2026-09-21 新增）

> **问题**：架构里有一批**隐式不变式**（分布归一、组内比例关系、因子非负、Tracker 只读自己的键、计数相位），**破坏了不会报错**。§五 风险表自己承认：「两者共同点是均不报错、只让结果静默偏移」。
>
> 「静默失效」在本系统反复出现：scope 写错、`reset` 取值非法、`targeted` 缺 `selected_card`、CR 短路条件写错——每一次都靠人肉排查。

**设计**：加一层**可开关**的校验（调试模式或测试模式下启用，生产关闭），在每次 `before_draw` / `after_draw` 后断言关键性质，破坏时立即抛出并指明位置（保底名 + 键 + 期望/实际）。

```python
class InvariantChecker:
    """可开关的不变式校验——仅在 debug/test 模式启用。"""
    def check_after_before_draw(self, pool_id, dist, engine): ...
    def check_after_after_draw(self, pool_id, state, engine): ...
```

**校验项**（初版）：

| 层 | 项 |
|----|-----|
| 分布 | `Σp = 1`；所有 `p ≥ 0` |
| 状态 | Tracker 写入的键在声明集内；计数型计数器的值单调（除重置外） |
| 因子 | 非负；在 p 的支撑上不全为 0 |
| 生命周期 | `_active` 只由引擎的激活传播与本保底的退役动作写入 |

**与性能的关系**：校验只在开关打开时运行，且检查项为 O(卡数)，对生产路径无影响。§五 风险表的相关条目可据此更新缓解手段。

---

### 3.14 条件外置（2026-09-21 新增）

> **本节是对 §3.1.2 Modifier 表的修订**：把「条件」从各 Modifier 内部提出来成为独立对象，**效果部分保持不变**。§3.1.2 的表格保留作历史形态与术语索引，实施以本节为准。
>
> **方案取舍**：本轮在三种方案中选定「只拆条件」。另两种（保持现状、彻底骨架化）的比较见 3.14.5。

#### 3.14.1 问题：条件散落在 Modifier 内部

§3.1.2 表里 Modifier 的「触发条件」列各不相同（`state[flag] == True` / `counter >= threshold` / `fate 就绪` / 恒真），且都写在类的 `factor` 方法里。后果有三：

- **条件不可组合**：要表达「两个前提同时成立才触发」必须写新类
- **条件不可单测**：测判断逻辑要构造完整 Modifier 与上下文
- **G14 要写新类**：战双命运池的「counter ≥ 随机阈值 T」与「counter ≥ 常数」形状不同，按现状须新增一个 Modifier

而 §3.1.5.4 的构造表早已把结构写成三元表达式（`hard` 的算子 = `c ≥ τ ? F : id`），那个条件部分就是这里要提出来的东西。

#### 3.14.2 设计：条件作为包装器

**不改 Modifier 的效果实现**，只把内部的 `if` 换成一层包装：

```python
class ConditionalModifier:
    """给内层 Modifier 加触发条件；条件不成立时返回 None（恒等）。"""
    def __init__(self, modifier, condition):
        self._mod, self._cond = modifier, condition

    def factor(self, ctx, view, dist, readonly):
        if not self._cond.test(ctx, view, dist):
            return None
        return self._mod.factor(ctx, view, dist, readonly)
```

各 Modifier 去掉内部判断，只剩因子计算。以 `ForceFeaturedModifier` 为例：

```python
class ForceFeaturedModifier:
    """把 scope 内总量占满 featured 组。何时生效由外层条件决定。"""
    def __init__(self, scope):
        self._scope = scope

    def factor(self, ctx, view, dist, readonly):
        return factor_redistribute(dist, ctx.draw.scope_cards[self._scope],
                                   ctx.draw.featured_cards[self._scope], 1.0)
```

preset 组装时套上条件：

```python
_preset_rotating = dict(
    trackers=[FlagTracker(judge="featured", hit="clear", miss="set", flag="guaranteed")],
    modifiers=[
        ConditionalModifier(ForceFeaturedModifier("ssr"), FlagCondition("guaranteed")),
        BaseRatioModifier("ssr"),                    # 无条件
    ],
    flags={"guaranteed": False},
)
```

| Modifier（保留） | 因子计算 | 组装时的条件 |
|---|---|---|
| `ForceFeaturedModifier` | 占满 featured 组 | `FlagCondition('guaranteed')` |
| `ForceNonFeaturedModifier`（G1） | 占满非 UP 组 | `FlagCondition('forced_loss')` |
| `ForceSelectedModifier` | 占满定轨卡 / 子集 | `Or(FlagCondition('guaranteed'), FateReadyCondition(τ))` |
| `ForceNotOwnedModifier`（G3） | 占满「UP ∩ 未拥有」 | `Always()` |
| `ThresholdForceModifier`（hard） | **F 语义**（见 3.14.3） | `CounterCondition('counter', τ)` |
| `BoostModifier`（soft） | `factor_redistribute(scope=源集∪目标集, ratio=(T+βQ)/(T+Q))` | `Always()` |
| `BaseRatioModifier` | 按当前比例（恒等） | `Always()` |
| `InterceptModifier`（CR） | 随机拦截 | **例外，见下** |

**Condition 类族**（纯读，无副作用）：`Always` / `Flag` / `Counter`（≥ 阈值）/ `FateReady` / `Ratio`（某组占比 ≥ r）/ `Owned`（持有数 == n）/ `RandomThreshold`（G14：counter ≥ 随机阈值）；组合子 `And` / `Or` / `Not`（与 `stop_condition` 的树形结构同构）。

**`InterceptModifier` 是唯一例外**：它的「条件」要消费全局 `random`（H4 协议：`cr_base_rate` 与 `cr_state_probs` 两处掷骰），而 `ConditionalModifier` 要求条件纯读。故它保持内部判断并单列，理由写入实现注释。

**不进 TOML**：Condition 作为代码级 building block，与 P69 的复合策略同构（`_strategy_key = None` 哨兵）。依据是 §3.7 已裁决的「`type="custom"` 完全声明式 TOML 状态机不实现（过度设计）」。

#### 3.14.3 等价性依据（2026-09-21 实跑）

本方案**不改任何因子的计算路径**，只改「何时调用它」（判断从类内部移到包装器，求值时机相同）。故等价性是结构性保证，以下是 `factor_redistribute` 的正确性实测，供 S8 与本节共用。

**R 类（单槽目标）：与现行逐卡一致，无需附加前提。**

```
场景：scope=(ssr, ssr_featured)，featured=(up)，base=(0.005, 0.004, 0.05, 0.941)
对比：现行（_redistribute_scope 槽位级 + banner 的 scale_factors 还原） vs 卡级 factor_redistribute

ratio=1.0 : 现行 {ssr_featured:0.009, ssr:0.0, sr:0.05, r:0.941}      新 同  ✓
ratio=0.5 : 现行 {ssr_featured:0.0045, ssr:0.0045, ...}               新 同  ✓
ratio=0.25: 现行 {ssr_featured:0.00225, ssr:0.00675, ...}             新 同  ✓
（逐卡差异 < 1e-15）
```

原因：R 类的目标恒为**单槽**（`compute_scope_mappings` 每稀有度只生成一个 featured 槽；`_resolve_selected_slots` 亦返回单槽元组）。单槽时不存在「槽间分配」这一层，槽内无论按基础权重还是按当前比例都退化为同一个式子。

**F 类（hard）：与 R 不等价，其因子计算不可复用 `factor_redistribute`。**

```
hard(scope='ssr') 触发时，现行输出 {ssr_featured: 1.0, ssr: 0.0, sr: 0.0, r: 0.0}
若改用 R_1                         →  {ssr_featured: 0.009, ssr: 0.0, sr: 0.05, r: 0.941}
```

差 100 倍，非精度问题：`R_1` 只让 **scope 内部**重新分配（SSR 总量仍 0.9%），`hard` 要求**全局占满**（SSR 占 100%）。按比例抽样下前者根本不是「必出」。

F 另有两点与 R 不同（§3.1.5.2 的表已按实现记录）：① 范围是**全池置零 + 更高稀有度豁免**（`hard(scope='sr')` 实测 Σ=1.009 ≠ 1，SSR 原值被保留）；② **槽间**按基础权重分配（`target_featured=False` 时目标含两个槽），而 R 类在卡级下按当前比例。第 ② 点在「槽间比例 = 基础权重比例」时与旧实现一致，但该不变量会被 R 操作破坏（如 `R_1(featured)` 把非 featured 槽清零），故不能依赖。

**结论**：`ThresholdForceModifier` 保留自己的 F 语义实现，不改为 `factor_redistribute` 调用。这是本方案与「彻底骨架化」的关键差别（3.14.5）。

#### 3.14.4 Condition 与 EventMatch 的分工（命名区分）

系统里有两处判断，**不合并**，且在命名上分开以免被误读为「同一概念的两份实现」：

| | **Condition**（本节的） | **EventMatch**（Tracker 侧，不新增抽象） |
|---|---|---|
| 位置 | Modifier 内，`before_draw` | Tracker 的 `commit`，`after_draw` |
| 输入 | 状态 + 当前分布 | 本次抽卡的结果（出了哪张卡） |
| 作用 | 决定「要不要改概率」 | 决定「状态怎么转移」 |

不可合并的技术原因：抽后那一刻 `PityContext.current` 是空字典（[pity.py:1355](gacha_simulator/core/pity.py#L1355) 构造时传 `current={}`），分布参数在抽后无意义。强行统一会得到 `test(ctx, view, dist=None, event=None)` 的万能谓词，读者须先判断时机才知道哪些参数有效。

#### 3.14.5 方案取舍：为什么只拆条件

本轮在三种方案间比较（第四种「拆到最碎」因概念数超过收益未纳入）：

| 维度 | A 保持现状 | **B 只拆条件（选中）** | C 彻底骨架化 |
|------|-----------|----------------------|-------------|
| 代码单元 | 7 类 | 7 类 + 条件族 + 1 包装器 | 3 骨架 + 条件族 |
| 读者需理解的概念 | 1（Modifier） | 2（Modifier、Condition） | 3（+ 四参数） |
| 新增机制成本 | 写一个新类 | 写一个类**或**一个条件 | 给一组参数 |
| **等价性风险** | 无 | **低**（因子代码一行不动） | 中（因子代码重写，需逐类重验） |
| 条件的可组合 / 可单测 | ✗ | ✓ | ✓ |
| G14 落位 | 要写新类 | 换一个 Condition | 换一个 Condition |
| preset 声明长度 | 短 | 中 | 长 |
| 声明可读性 | 类名即语义 | 好（类名 + 条件） | 中（须查参数表） |
| 消除「仅 target 不同」的类间重复 | ✗ | ✗ | ✓ |

**B 与 C 的收益差距只在最后一行**：`ForceFeatured` / `ForceNonFeatured` / `BaseRatio` 三者只差一个 target，C 会合并它们，B 保留。而这一重复是**既有的**，非拆条件所引入。

**C 的代价**在「等价性风险」一行：它要重写每类的因子计算并逐类重验。2026-09-21 的审查已证明这类重写容易引入静默错误（`factor_redistribute` 的 `ratio=1` 分支即为实例，且未被既有测试捕获）。

**选 B 的理由**：收益 ÷ 风险最优。它拿到了条件外置的全部实质收益（G14 可扩展、条件可组合可单测、触发时机显式化），代价仅一层包装器，且因子路径不动、无需重验。

**不封死 C**：将来若「仅 target 不同」的重复确实碍事，可在条件已外置的基础上再合并内层，那时只动一件事。

#### 3.14.6 修订范围

| 位置 | 改动 |
|------|------|
| §3.1.2 | Modifier 表标注「已由 §3.14 修订」；新增 Condition 类族清单；各 Modifier 去掉内部条件判断 |
| §3.2 | preset 映射表补「组装时的条件」一列 |
| §3.3 | G1 inverse preset 用 `ConditionalModifier(ForceNonFeatured, FlagCondition('forced_loss'))` |
| §3.4 | 软保底去掉内部条件（`Always`），ratio 仍按 3.14.2 表 |
| §3.10.4 | G3 用 `ConditionalModifier(ForceNotOwned, Always())` |
| §四 | 新增 `core/pity_condition.py`（Condition 类族，~80 行） |
| §七 | GATE 加 S12 |

**风险**：① Condition 必须纯读无副作用（由 §3.13 的不变式校验覆盖）；② `RandomThresholdCondition`（G14）需在状态中持久化随机阈值，属 Tracker 侧的扩展，与条件本身正交；③ 包装器多一层对象，preset 声明变长（见 3.14.5 的可读性行）。

---

## 四、波及范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/pity_tracker.py` | **新增** | Tracker 家族（CounterTracker/FlagTracker/StreakTracker/FateTracker）+ Lifecycle（AlwaysActive/OnceActive/DependentActive）（~120 行） |
| `core/pity_condition.py` | **新增**（**S12**） | Condition 类族（7 个内置 + 3 个组合子），纯读无副作用；配套 `ConditionalModifier` 包装器（~80 行） |
| `core/pity_modifier.py` | **新增** | Modifier 家族（BoostModifier/ForceFeaturedModifier/ForceNonFeaturedModifier/ForceSelectedModifier/InterceptModifier/ThresholdForceModifier/BaseRatioModifier）（~150 行）。**S8**：实现形态切换为乘性因子向量（§3.1.5.1） |
| `core/pool.py` | 修改（**S8**） | 删除 `aggregate_probs_by_rarity`（[pool.py:244](gacha_simulator/core/pool.py#L244)，唯一调用点在 banner）+ `core/__init__.py` 导出行；`compute_scope_mappings` 改造为只产出卡集合 |
| `core/worst_impact.py` | 修改（**S8**） | 第二处 `PoolPitySpec` 构造点去掉硬编码槽位名（[worst_impact.py:506-548](gacha_simulator/core/worst_impact.py#L506-L548)） |
| `core/state.py` | 修改（**S9**） | `ExternalView` 只读查询视图（`owns` / `balance` / `now`），供 `reads` 声明的保底消费 |
| `core/config_store.py` | 修改（**S9**） | `PityDef` 新增 `reads: tuple[str, ...] = ()` |
| `core/config_toml.py` | 修改（**S9**） | `reads` 的解析 + 状态源白名单校验（未知名称抛 `ConfigError`）、round-trip 写回 |
| `core/pity.py` | 修改（**S9**） | `PityContext` 加 `external` 字段；`StateView` 限定 Modifier 的状态视野；新增 `ForceNotOwnedModifier` 零件 |
| `core/banner.py` | 修改（**S8 / S9**） | **S9**：作为 `ExternalView` 的填充者，按该池各保底 `reads` 的并集构造并传入调度入口（§3.10.2）。**S8**：删除 `scale_factors` 聚合/还原段（[banner.py:229-246](gacha_simulator/core/banner.py#L229-L246)），概率管道改传卡级分布；`aggregate_probs_by_rarity` 的调用点随之移除。**2026-09-21 审查修正：原写 `service/banner.py` 路径不存在** |
| `core/pity.py` | **重构** | 统一 Pity 骨架 + 10 个类型改造为 registry preset + `_BTYPE_ORDER` 加 `rotating_inverse` + `_resolve_order` 加 `priority` 排序（G5）。**G16 独立先行（不混入本行重构，§3.8）**：`_should_reset` 加 `never` 分支。**P82 接线独立先行（§1.5 裁决 1）**：`PityEngine` 独立排序视图 + `get_behaviors_for_pool()` 改消费它 |
| `core/config_toml.py` | 修改 | reset 枚举 `never` + `rotating_inverse` 校验放行 + **移除事件驱动型 deactivate_on_early_hit 拒绝分支（H3）** |
| `core/config_store.py` | 修改 | PityDef 新增 `priority` 字段（G5） |
| `gui/config_panel.py` | 修改 | **新建 reset 控件**并加「永不重置」（G16，现无该控件）；`_PITY_TYPES` 硬编码列表手工追加 `rotating_inverse`（type 下拉非 registry 驱动）；priority 编辑控件（G5） |
| `service/gacha_service.py` | 修改 | 定轨识别 `isinstance(bh, TargetedBehavior)` → `getattr(bh, '_btype', '') in ('targeted', 'targeted_soft')`（H1） |
| `config/config.toml` | 更新 | 幻塔 `rotating_inverse` + G16 示例段 |
| `tests/` | 新增/修改 | 等价性测试（旧类 vs 新引擎，全部类型）+ G1/G5/G16 测试 |
| 手册 | 更新 | G1/G16 登记（G19/G13/G2/G14/G15/G5 已同步，2026-08-24） |

**不受影响**（S1–S5 期间）：PityEngine 调度层接口签名、`_validate_behaviors`、PityState/DrawInfo/PityContext、`_redistribute_scope`、GUI 参数控件、P75 `_rebind_state` 纪律（Pity 统一实现后语义不变）。**2026-09-21 审查修正**：`_redistribute_scope` 与 `DrawInfo`/`PityContext` 的槽位字段在 **S8** 中会被替换或删除（见 §3.9.3），此处的「不受影响」仅指 S1–S5

## 五、风险

| 风险 | 缓解 |
|------|------|
| 等价性破坏（重构回归）——preset 与旧类行为偏差 | **等价性测试守门**：固定种子，逐场对比 before_draw 输出概率分布 + after_draw 后状态快照完全一致；覆盖全部 10 个类型（含 counter 驱动）；P56 现有测试天然构成基准 |
| 软保底/硬保底 preset 化风险——`_compute_probabilities` 移植 | 全量 preset 化一次完成；等价性测试覆盖全部组合（含 soft 叠加三态） |
| Modifier 链顺序语义与现有 mixin 嵌套不完全一致 | Modifier 链「顺序应用非短路」契约明确写入设计；等价性测试覆盖 guaranteed / 非 guaranteed / 软保底叠加三态 |
| registry/GUI 兼容——preset 化后参数描述失效 | `params`/`ui_params` 原样保留；GUI 控件零改动，round-trip 验收覆盖 |
| P75 `_rebind_state` 纪律在 Pity 中退化 | Pity 统一实现 Trackers/Modifiers/Lifecycle 的 rebind 委托；独立测试断言跨模拟状态隔离 |
| 增量能力（事件驱动 deactivate）误入等价性范围 | 明确标注「旧类无此能力，不在等价性范围」，单独验收用例 |
| G16 与 P64 并行改 `_should_reset` 冲突 | G16 独立先行（单 commit 先落地），P64 重构时 CounterTracker 自然承载，无交叉 |
| CR 随机数消耗不齐（等价性 RNG 分叉） | InterceptModifier 随机数消耗协议（§3.1.2 H4）；等价性测试含 `cr_state_probs` (0,1) 中间值用例 |
| 全量 10 类 preset 化改动面扩大 | 不分阶段（软保底不再分阶段二），一次完成；等价性测试全量守门 |
| **S8 卡级管道引入的浮点差异与零概率退化** | 浮点差异量级 1e-16，等价性口径已在 §六 放宽为 1e-12 并单独设 S8 验收；零概率退化（因子在 p 支撑上全零）由 §3.1.5.6 约定「返回原分布」处理，与现行早退路径一致 |
| **映射表未写死的实现细节致等价性失败**（计数相位 / CR 随机数短路） | 两条已在 §3.1 列为强制约束（N1 / H4），§六 设对应断言；两者共同点是均不报错、只让结果静默偏移，故必须在 S1/S5 显式实现与断言。did_fire 一项已按 §3.1.1 M4 裁决为统一语义，属行为变更，走独立验收（可先行） |

## 六、验收标准

### 主线（Tracker + Modifier 统一骨架 + G1 + G5）

- [ ] **S1–S5 口径**：全部 10 个类型同配置下，新引擎输出概率分布 + 状态快照与旧类**逐场完全一致**（固定种子，含 hard/soft_step/rotating/rotating_cr/targeted/soft 组合各基准）。此阶段 Modifier 内部沿用槽位法，故要求位级一致
- [ ] **S8 口径**：切换为卡级乘性因子后，与 **S5 的产物**逐场对比，概率分布**容差 1e-12 内一致**、状态快照**完全一致**（浮点求和顺序改变导致，量级 1e-16，见 §3.1.5.6）。差异超出容差即为回归
- [ ] **S8 单卡定向**：双 UP 池定轨（`targeted` 锁定其中一张）在必中触发时该卡拿到 100%，不再按基础权重平摊（当前实测为 50/50，见 §3.7）

### S9（状态可见性与 G3）

- [ ] **S9 口径 · reads**：`reads` 声明的保底能读到对应外部状态；未声明时 `ctx.external` 为 `None`；`reads` 写未知状态源在配置加载期抛 `ConfigError`（防拼写致静默失效）
- [ ] **S9 口径 · StateView**：Modifier 读其他保底的键返回 default（架构上关闭，§3.10.3）；`depends_on` 的激活传播不受影响（引擎侧执行，不经过 Modifier）
- [ ] **G3 专项（精确建模判据）**：崩坏3 精准补给「50 抽 UP 保护排除已拥有」——① 保底触发时已拥有的 UP 装备不被选中；② **普通抽卡仍能产出已拥有的装备**（这是与 pool 层近似的分界，必须单独断言）；③ 全部 UP 均已拥有时退化为恒等（§3.10.4）
- [ ] `cr_state_probs` 含 (0,1) 中间值的用例等价性通过（随机数消耗对齐，H4）
- [ ] **计数相位（N1）**：`hard(threshold=90)` 首次 100% 出现在第 90 抽；`soft` 的 boost 起始抽数与旧实现相同
- [ ] **did_fire 统一语义（M4）**：三类的 `did_fire` 均等价于「本次抽卡是否让本保底回到初始状态」，与各自 `after_draw` 的重置分支严格同条件；rotating/targeted 新补的 scope 门控属增量能力，按「不在等价性范围内」单独验收
- [ ] **N1 例外**：`deactivate_on_early_hit=True` 且命中时，`commit` 跳过 counter 重置，状态快照与 `get_counter()` 与旧实现一致
- [ ] **Lifecycle 增量能力单独验收**：配 `depends_on` 的事件驱动型在激活前不改分布、不更新状态（旧实现为惰性，属行为变更，不在等价性范围内）
- [ ] **CR 随机数短路（H4）**：`cr_base_rate == 0` 与 `cr_state_probs` 含 0 的用例中，随机数消费次数与旧实现逐位相同
- [ ] `rotating_inverse` preset 正确：出 UP → 下一次 SSR 必非 UP；出非 UP → 恢复基础比例（G1）
- [ ] PityEngine 调度层**既有调用形式**不变（`before_draw`/`after_draw`/`get_probabilities` 的既有实参不变；**S9 新增可选参数 `external`**，见 §3.10.2）；`_validate_behaviors` 逻辑不变
- [ ] **接线（§1.5 裁决 1）**：概率管道顺序由 `_resolve_order` 排序键决定而非 TOML 书写顺序；独立排序视图方案下 `draw_pity_names` 输出串保持不变；固定种子基线对照完成，差异逐一归因到「含 `rotating_cr`」或「`target_featured=True` 的 soft 与 hard 共存」两类
- [ ] G5 priority：PityDef `priority` 字段生效，显式 priority 覆盖 type 顺序；priority 全 0 时排序结果与接线后默认序一致（当前 hard 已在 targeted 前，绝区零默认顺序已满足）
- [ ] Lifecycle 统一：config_toml 拒绝分支已移除，事件驱动型配置 `deactivate_on_early_hit` 后出 UP 即退役
- [ ] GachaService 定轨流程（H1）：targeted preset 化后 `switch_epitomized_target`/`cancel_epitomized_path` 仍正常
- [ ] P75 rebind：Pity 统一实现正确，跨模拟状态隔离测试通过
- [ ] 任意 Tracker × 任意 Modifier 组合自由（新 preset 无需新类）
- [ ] `_SOFT_SUFFIX_TYPES` 处理、`SoftPityMixin`、旧 counter 驱动类退役
- [ ] GUI round-trip：preset 参数编辑 → 保存 → 重载一致；新 type 出现在下拉（须手工追加 `_PITY_TYPES` 硬编码列表，非自动）
- [ ] pytest 全量通过

### G16（独立先行）

- [ ] `reset="never"`：hard 保底出金不重置 counter，每 N 抽白送保底金；`reset="featured"`/默认行为不受影响
- [ ] 手册缺口登记同步（**2026-09-18 核实：G13/G2/G14/G15/G19 已同步**）：G16 由「🔵 待 P64」（[手册:2287](docs/主流抽卡游戏卡池机制配置转换手册.md#L2287)、[手册:775](docs/主流抽卡游戏卡池机制配置转换手册.md#L775)）改「✅ 已覆盖」；G1 由「🔴 高优先级 · → 待 P64 状态机引擎」（[手册:2283](docs/主流抽卡游戏卡池机制配置转换手册.md#L2283)）改「🟡 P64 设计中」；G5（[手册:2296](docs/主流抽卡游戏卡池机制配置转换手册.md#L2296)）待 priority 裁决后更新

## 七、GATE 任务分解

> G16 独立 2 子块 + P82 接线独立 2 子块 + 主线 12 子块（含全量 preset 化、S8 概率操作乘法化、S9 状态可见性与 G3、S10 组合验收、S11 不变式校验、S12 条件外置），共 16 子块；G16 与 P82 接线均独立先行，不占 P64 主线。

### GATE-1 任务清单（checkbox）

**G16 独立先行（独立 commit，~1 人时——GUI 需新建 reset 控件，非改下拉）**
- [ ] G16-1 `_should_reset` 加 `never` 分支 + PityDef/config_toml reset 枚举 + GUI **新建 reset 控件**（含「永不重置」）
- [ ] G16-2 测试（hard 出金不重置）+ 手册缺口登记同步（G16/G13/G2/G14/G15/G5；G19 已同步）

**P82 接线独立先行（独立 commit，建议排期；见 §1.5 裁决 1）**
- [ ] P82-1 `PityEngine` 独立排序视图（`self._pool_order` 于 behavior 构造后预计算）+ `get_behaviors_for_pool()` 改为消费排序视图，`PoolPitySpec.pity_names` 保持 TOML 顺序不动
- [ ] P82-2 基线固化 + 等价对照：接线前用固定种子跑 `config.toml` 与既有测试配置固化 `CompactResult` 快照，接线后同种子重跑逐字段对比，差异归因到敏感集合；确认 `draw_pity_names` 输出串不变

**主线：Tracker + Modifier 统一骨架（~10 人时）**
- [ ] S1 新建 `core/pity_tracker.py`：Tracker 家族（CounterTracker/FlagTracker/StreakTracker/FateTracker）+ Lifecycle（AlwaysActive/OnceActive/DependentActive）。**须实现 §3.1.1 的 N1 双段接口**（`advance` 仅供 `CounterTracker` 在 before_draw 推进，`StreakTracker` 的 `cr_counter` 不适用；`commit` 落重置与翻转，且须处理 `deactivate_on_early_hit` 的跳过重置例外）与 **M4 的 `did_reset`**（统一为「本次是否回到初始状态」，counter 家族 `featured` 分支保留无 scope 门控的不对称）
- [ ] S2 新建 `core/pity_modifier.py`：Modifier 家族（BoostModifier/ForceFeaturedModifier/ForceNonFeaturedModifier/ForceSelectedModifier/InterceptModifier/ThresholdForceModifier/BaseRatioModifier）
- [ ] S3 统一 Pity 骨架（Tracker + Modifier + Lifecycle 三元组）+ P75 rebind 委托
- [ ] S4 registry 改造：10 个类型改造为 `preset` 工厂 + `create_behavior` 双路径（preset / 旧类兼容）+ deltas 展开职责移交（M6）
- [ ] S5 preset 映射：全部 10 个类型 preset 化 + 等价性测试（旧 vs 新，固定种子逐场，含 `cr_state_probs` 中间值用例 H4）+ 三条强制约束的专项断言（N1 触发抽数 / M4 did_fire 三类语义 / H4 短路条件下随机数消费次数）
- [ ] S6 G1 `rotating_inverse` + G5 `priority`（PityDef priority + _resolve_order 排序）+ GachaService 定轨识别适配（H1，`isinstance` → `_btype` 判断）+ config_toml 拒绝分支移除（H3）+ GUI `_PITY_TYPES` 硬编码列表追加新 type
- [ ] S7 GUI round-trip 验收（含 `_PITY_TYPES` 追加）+ 手册示例 + pytest 全量
- [ ] S8 **概率操作路径重构**（方案见 **§3.9**，声明见 §3.1.2 D20，数学形式见 §3.1.5）：
  - [ ] S8-1 Modifier 接口改为 `factor(...) -> Optional[因子向量]`，`_apply_factor` 做归一化（§3.9.2）
  - [ ] S8-2 管道改传卡级分布：`banner.py` 删除 `aggregate_probs_by_rarity` 调用与 `scale_factors` 还原段（§3.9.1）
  - [ ] S8-3 `_redistribute_scope` 替换为卡级版 `factor_redistribute`，语义切为「保持组内当前比例」（§3.9.4）
  - [ ] S8-4 删除 `scope_slots`/`featured_slots`/`card_to_slot`（`PoolPitySpec` + `DrawInfo`），`compute_scope_mappings` 改造为只产卡集合，删除 `aggregate_probs_by_rarity` 及其导出行（§3.9.3）
  - [ ] S8-5 边界处理（`T == 0` / `P == 0` / `P − T == 0`）按 §3.9.5；只读查询口径同 §3.9.6
  - [ ] S8-6 验收：按 §六 的 S8 口径（对 S5 产物容差 1e-12）+ 单卡定向专项
- [ ] S9 **状态可见性与 G3 真实建模**（方案见 **§3.10**）：
  - [ ] S9-1 `StateView` 限定 Modifier 状态视野（关闭跨保底读，§3.10.3），Modifier 签名定型为 `factor(ctx, view, dist, readonly)`
  - [ ] S9-2 `PityDef.reads` + `ExternalView` + 配置层白名单校验（§3.10.2）
  - [ ] S9-3 `ForceNotOwnedModifier` 新零件 + G3 配置示例 + 手册 §7.3 缺口归属更正（§3.10.4）
  - [ ] S9-4 验收：§六 的 S9 口径三条 + G3 专项三条
- [ ] S10 **组合正确性验收**（方案见 **§3.12**）：
  - [ ] S10-1 不变式性质测试：随机组合零件，断言归一性 / 非负性 / 因子合法性 / 状态键合法 / 确定性（§3.12.1）
  - [ ] S10-2 合法组合判据 + 构造期检查（与 `_validate_behaviors` 同层，§3.12.2）
- [ ] S11 **不变式运行时校验**（方案见 **§3.13**）：可开关的 `InvariantChecker`，覆盖分布 / 状态 / 因子 / 生命周期四层；生产关闭
- [ ] S12 **条件外置**（方案见 **§3.14**）：
  - [ ] S12-1 `core/pity_condition.py`：Condition 类族（`Always`/`Flag`/`Counter`/`FateReady`/`Ratio`/`Owned`/`RandomThreshold` + `And`/`Or`/`Not`）
  - [ ] S12-2 `ConditionalModifier` 包装器 + 各 Modifier 去掉内部条件判断（效果实现**不动**）
  - [ ] S12-3 `InterceptModifier` 保持内部判断（消费随机数，不适用纯读条件），理由写入实现注释
  - [ ] S12-4 验收：条件不成立时返回 `None`（恒等）与改前的内部判断逐场一致；`ThresholdForceModifier` 的 F 语义保持（不得改为 `factor_redistribute`，依 §3.14.3）；`RandomThresholdCondition`（G14）专项

### GATE-5 回滚策略

- **回滚单元**：G16 独立；主线整体一次回滚（全量 preset 化不分阶段，保留旧类到等价性测试通过为止）
- **等价性测试失败**：立即停止主线，保留失败 preset 为「未迁移」，回退 registry 到该 preset 指向旧类
- **G16**：独立 commit，与 P64 主线完全解耦，可随时 cherry-pick 或 revert
- **发布前**：主线完成后一次性移除旧保底类（无历史包袱原则，`RELEASED=False`）

---

*设计评审记录：2026-08-23 用户裁决路线 B（代码组合）、soft 纳入、无完全声明式状态机、G16 独立先行。2026-08-23 独立审查 14 项修正（H1-H4/M1-M6/L1-L4）。2026-08-24 设计重建：Tracker+Modifier 双层纯函数架构（用户裁决命名），范围从事件驱动 6 类扩大到全部保底类型统一，G2 归 milestone 层修正。本计划未含 ISSUE 体系——待 plan-review 工作流审查后补充。*
