<!-- META: P64 | module:保底系统 | status:designing | last:2026-09-18 | depends:P55,P56 -->

# P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构

> 日期：2026-08-24（2026-09-16 补三条强制约束 + §3.1.5 形式化 + target_featured 反例；**2026-09-18 事实同步**：全量行号刷新至 P81 清理后的代码 + GUI 两处事实修正 + legacy 迁移描述更新；**同日裁决 P82 并入的三项**：接线 / 保留 priority / 顺序两层定性，见 §1.5） | 状态：设计中（2026-08-23 初版 → 2026-08-24 双层纯函数重建）
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
| G15 pjsk 加权抽数 | 付费石双倍天井进度（[手册:2306](docs/主流抽卡游戏卡池机制配置转换手册.md#L2306)，付费 +1 / 免费 +0.5） | 🟢 近似可配（2026-08-24）：`reward.resources_gained` 每抽按池注入 + exchange pool 兑换 50/100 档；语义打折（卡附带产出 vs 动作进度）+ 配置脆性（全 reward 需配），严格语义留 milestone `weight_by_pool`（milestone 层，P64 范围外） |

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
| 2 | `priority` 是否仍需引入 | 若裁决 1 为废弃，G5 的 priority 设计失去落脚点；若保留，需说明它要解决什么实际问题（当前 `_BTYPE_ORDER` hard=1 < targeted=3 已满足绝区零需求，[§1.3](#) 已核实）。**2026-09-16 补**：§3.1.5.4 的反例表明顺序并非普遍无关（`target_featured=True` 的 soft 与 hard 共存时结果不同），但该敏感性来自组合本身而非排序键，priority 能否覆盖它取决于裁决 1 的取向 |
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
- **行为变更面**：仅「同一池内、书写顺序与排序键不一致」的配置受影响。已实测（P82 §六 + §3.1.5.4）敏感集合为两类：含 `rotating_cr` 者（随机流错位）、`target_featured=True` 的 soft 与 hard 共存者（真实概率语义）；其余组合数学可交换，接线不改变其输出。**2026-09-18 补第三类（实测新发现）**：跨 type 顺序发生反转且存在 `depends_on` 时，依赖方的状态键**创建时机**会变（旧顺序在源触发当轮就执行依赖方 `after_draw` 并创建其 `counter` 键；新顺序下该轮依赖方仍未激活、键延后到下次 `before_draw` 才创建）。实测（rotating 源 + hard 依赖，`pity_names` 由 `(source, dependent)` 反转为 `(dependent, source)`）：依赖方 `_active` 最终值不变（均为 True），但 `PityState` 快照的键存在性有差异。该差异只在 `depends_on` 配置中出现，当前 `config.toml` 无此配置。当前 `config.toml` 示例仅一条保底定义，不受影响。
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
- 覆盖 G1（inverse preset）+ G16（独立先行 `reset="never"`）+ G5（调度层**接线** + `priority` 显式排序，2026-09-18 裁决，见 §1.5）
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

Modifier 是 pure 函数（除 InterceptModifier 显式依赖 RNG）：给定当前状态和基础分布，返回修正后分布。全部复用 `_redistribute_scope` 按基础权重分配。多个 Modifier 可叠加，**列表顺序即优先级**。

| Modifier | 语义 | 对应现有 | 触发条件 |
|----------|------|---------|---------|
| `BoostModifier(deltas, scope)` | 读 counter 算 boost% 提概率（连续提升） | SoftStepBehavior._compute_probabilities | Always（计数驱动） |
| `ForceFeaturedModifier(flag, scope)` | 标记置位 → 目标槽位 100% | rotating/CR guaranteed 分支 | `state[flag] == True` |
| `ForceNonFeaturedModifier(flag, scope)` | 标记置位 → 非 UP 100%（**G1 新增**） | 幻塔必歪 | `state[flag] == True` |
| `ForceSelectedModifier(flag, card)` | 标记/阈值满足 → 定轨卡槽位 100% | targeted _resolve_selected_slots | `state[flag] or fate_ready` |
| `InterceptModifier(probs, base_rate)` | 读 streak 计数 + 掷随机数决定是否拦截为 100% UP | CR before_draw 随机分支 | 计数+随机 |
| `ThresholdForceModifier(threshold, scope)` | 计数 ≥ threshold → 强制 100% | HardPityBehavior | `counter >= threshold` |
| `BaseRatioModifier(scope)` | 按当前比例 redistribute（兜底） | rotating/targeted 默认分支 | Always |

**Modifier 链契约（强制）**：Pity 的 `before_draw` 按 `modifiers` 列表**顺序应用、非短路**，每个 Modifier 在前一个的输出上操作。覆盖型 Modifier（ForceFeatured 把非目标槽位置 0）自然覆盖前序 Modifier 的概率调整。soft 抬高的 scope 总量在 guaranteed 下全部流入 featured——与旧 SoftPityMixin「先 soft 后事件」等价。

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
                out = nxt                    # 链式应用（非短路）
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

### 3.1.5 形式化：表达力与顺序判据（2026-09-16 新增）

> **2026-09-16 独立核对后的修订**：定理 1 构造表的 `rotating_cr` 项由 `F` 改为 `R_1`（`_force_featured` 用的是 `_redistribute_scope(…, 1.0, …)`）；基底显式纳入恒等元；引理 2.1 / 2.2 / 2.3 补适用条件；`F` 的目标为空集补入边界表。

> 目的：把「新架构能否表达现有全部保底」与「组合顺序何时影响结果」从实测归纳提升为可推导的判据。实测只覆盖采样点，推导才能界定边界。

#### 3.1.5.1 定义

一次抽卡有 n 个互斥槽位 S（实现里即 `ssr_featured` / `ssr` / `sr` 等），基础权重 w ∈ R^n_+（`base_probabilities`），基础分布 p₀ = w / Σw。一个保底机制是三个映射：

```
M : 𝒮 → (Δⁿ⁻¹ → Δⁿ⁻¹)     状态决定一个概率算子
T : 𝒮 × Ξ → 𝒮             状态转移，Ξ 为一次抽卡事件（出了哪个槽位）
D : 𝒮 × Ξ → {0,1}         发动判据（did_fire）
```

抽卡循环：`pₜ = M(sₜ)(p₀)`，`ξₜ ~ pₜ`，`sₜ₊₁ = T(sₜ, ξₜ)`。

把 M 定义为「状态给出算子」而非「分布到分布」，是为容纳 `rotating` 一类比例依赖当前分布的情形：它读的是链式复合的输入分布，恰好是算子复合的自然对象。

#### 3.1.5.2 旧实现只有三种基本算子

| 算子 | 来源 | 作用 |
|------|------|------|
| `B_β(T)` | `SoftStepBehavior._compute_probabilities` | 源集（非目标且非更高稀有度）整体乘 (1-β)，取出的量按 w 比例分给目标 T |
| `R_r(T)` | `_redistribute_scope` | scope 内按 w 比例重写，使 T 占 scope 总量的比例恰为 r，scope 总量不变 |
| `F(T)` | `HardPityBehavior._compute_probabilities`（[pity.py:360-401](gacha_simulator/core/pity.py#L360-L401)） | T 按 w 比例占满、其余置 0，更高稀有度槽位保留原值 |

基底还须计入**恒等元 `id`**：所有早退路径（`counter < τ`、`pool <= 0`、`scope_slots` 为空、featured 槽位为空等）都返回 `ctx.current.copy()`，不把 `id` 列入则「`hard(counter < τ)` 是 {B, R, F} 的有限复合」在字面上不成立。

#### 3.1.5.3 定理 1（表达力包含）

**命题**：旧 10 类的每个 M 都是 {B, R, F} 的有限复合；每个 T 都是条件赋值语句的有限复合。

**证明**（构造性，逐类展开）：

| 类型 | M | T |
|------|---|---|
| `soft_step` | `B_β(c)` | 出 scope 时 `c ← 0` |
| `hard` | `c ≥ τ ? F : id` | 同上 |
| `rotating` | `R_r(S_f)`，r = 1 若 g，否则 p(S_f)/p(S_c) | 出 scope 时 `g ← is_featured` |
| `rotating_cr` | 命中 ? `R_1(S_f)` : `R_r(S_f)` | 父类 + 出 scope 且 ¬was_g 时 `cr ← is_featured ? 0 : cr+1` |

> **`rotating_cr` 的命中分支是 `R_1` 而非 `F`**：它由 `_force_featured`（[pity.py:586-589](gacha_simulator/core/pity.py#L586-L589)）实现，内部调 `_redistribute_scope(ctx, 1.0, ...)`，只把 scope 内总量给 featured、scope 外原样保留。实测同一输入（0.5 / 0.5 / 0.08 / 0.9）下 `_force_featured` 得 {ssr_featured: 0.02, ssr: 0, sr: 0.08, r: 0.9}，`F(S_f)` 得 {ssr_featured: 1.0, ssr: 0, sr: 0, r: 0}。定理结论不因此改变（`R_1 ∈ {R}`），但构造表须按 `R_1` 记。
| `targeted` | （g 或 fate 就绪）? `R_1(T_sel)` : `R_r(S_f)` | 命中定轨卡时四键清零，否则四键累积 |
| 各 `_soft` | `M_父 ∘ B_β` | 父类 T 加 counter 清零 |

`R` 的参数 r 依赖当前分布，但依赖的是复合输入的分布，故复合仍是算子复合。每个 M 长度不超过 2；每个 T 只含条件赋值，无循环、无跨调用内存（逐行读代码可得）。

新架构的 M 是 Modifier 的顺序复合，T 是 Tracker 的顺序复合，故**旧的 ⊂ 新的**。∎

**效力**：本定理证的是**表达力包含**（存在一个 preset 表达旧行为），不保证实现出的 preset 与旧代码位级一致（浮点运算顺序差异），后者由等价性测试承担。

#### 3.1.5.4 定理 2（可交换性判据）

> 用途：§1.5 三项待裁决中的「组合顺序是语义还是实现细节」需要判据，本定理给出判据而非实测扫描。

**引理 2.1**：若算子 X 不改变 F 作用域之外的**更高稀有度**槽位，则 `F(T) ∘ X = F(T)`。F 在 T 所在 scope 内的输出只依赖 w 与 T，与输入的 scope 内取值无关；但它**保留更高稀有度槽位的原值**（[pity.py:394-399](gacha_simulator/core/pity.py#L394-L399)），故对这部分槽位不具吸收性。反例：`F_sr ∘ B_ssr ≠ F_sr`（`B_ssr` 改动了 ssr 槽位，`F_sr` 会把改动后的值原样保留；实测输入 (0.01, 0.01, 0.08, 0.9) 下前者 ssr 槽为 0.255，后者为 0.01）。推论表中用到本引理的那一行（soft 与 hard 同 scope）满足条件，因为 `B` 的层级保护不改动更高稀有度槽位。

**引理 2.2**：若（a）X 的源集 ⊇ Y 的源集 ∪ Y 的目标集，（b）X 对源集内所有槽位用同一缩放因子，（c）X 把取出的量按**只依赖 w 的固定权重**交给目标，（d）Y 的写入全部落在 X 的源集之内，则 `X ∘ Y = Y ∘ X`。（a）是核心条件；（b）（c）保证 X 是「统一缩放 + 固定权重再分配」型算子；（d）防止 Y 写到 X 的源集之外。四个条件在「异 scope soft」场景下均满足。本引理是**充分条件而非充要条件**（同 scope 但 `target_featured` 不同的两条 soft 不满足其假设，却仍可交换）。

**引理 2.3**：在**当前槽位结构下**（`compute_scope_mappings` 对每个稀有度只生成一个 featured 槽与一个非 featured 槽，[pity.py:1040-1082](gacha_simulator/core/pity.py#L1040-L1082)），参数取「保持当前比例」的 `R` 是恒等映射。原因不是「保持比例」本身蕴含恒等，而是**单槽位使组内重写退化**：一个 featured 槽的「按 w 比例分配」只能把该槽自身概率原样保留。**若槽位结构泛化**（同一稀有度出现多个 featured 槽），`R(r = 当前比例)` 会用 w 重写组内比例而不再恒等（实测：两 featured 槽结构下，输入 (0.7, 0.2, 0.1) 经 R 得 (0.45, 0.45, 0.1)），rotating / targeted 的默认分支届时需重新论证等价性。

**推论**：

| 组合 | 可交换 | 依据 |
|------|-------|------|
| soft + soft（同 scope，同 target_featured） | 是 | 复合为 `B_(1-(1-β₁)(1-β₂))`，乘法可交换 |
| soft + soft（同 scope，异 target_featured） | 是 | 实测 200 组无反例；此项**不适用**上一行的 `B_乘积` 依据（两者目标集不同），可交换性来自引理 2.2 的推广形式 |
| soft + soft（异 scope） | 是 | `B_ssr` 源集 {sr, r} ⊇ `B_sr` 源集 {r} ∪ 目标 {sr}，且统一缩放，由引理 2.2 |
| soft(T=scope) + hard | 是 | `B ∘ F` 中 B 的源集被 F 清零、pool=0 早退，故 = F；`F ∘ B` 由引理 2.1 = F |
| **soft(target_featured=True) + hard** | **否** | F 后 scope 内非 featured 槽位非零，B 仍有源可偷，`B ∘ F ≠ F` |
| 含 `rotating_cr` 的组合 | 否 | 非代数问题：M_cr 是算子族 M(ω)，顺序改变导致 ω 消费位置改变、样本路径分叉 |

**反例实测（2026-09-16，对 P82 §六 结论的修正）**：soft(`target_featured=True`，deltas 使第 6 抽起 boost) + hard(threshold=8)，两种 `pity_names` 顺序，12 抽概率序列对比：

```
target_featured=False  顺序敏感抽数 = []                    （与 P82 结论一致）
target_featured=True   顺序敏感抽数 = [8, 9, 10, 11, 12]     （反例）

第 8 抽（hard 触发那一抽）：
  [soft, hard] = {'sr': 0.0, 'ssr': 0.5, 'ssr_featured': 0.5}
  [hard, soft] = {'sr': 0.0, 'ssr': 0.2, 'ssr_featured': 0.8}
```

数值与引理推导一致。「hard 触发时覆盖一切」这一理由只在 soft 的目标集等于整个 scope 时成立；`target_featured=True` 时 soft 以 featured 为目标，会继续从 hard 刚铺好的非 featured 部分偷。**故 P82 的「仅含 `rotating_cr` 的配置会变」应修正为「含 `rotating_cr`，或 `target_featured=True` 的 soft 与 hard 共存的配置会变」。**

#### 3.1.5.5 未覆盖（边界）

| 项 | 为何只能测 |
|----|-----------|
| 位级一致 | 定理 1 保证构造存在，不保证浮点运算顺序一致；1e-16 量级差异可能被下游阈值放大 |
| 随机数消费次数 | 可证，但需先把 H4 的短路条件写死，再把 ω 显式化为消费序列逐位比对 |
| 全配置组合 | 组合空间过大，采样测试只覆盖有限点；本节的判据用于缩小「必须实测」的范围 |
| `F` 的目标为空集 | `featured_slots[scope]` 键存在但值为空元组时，取槽位处的 `.get(self._scope, scope_slots)`（[pity.py:282](gacha_simulator/core/pity.py#L282)、[pity.py:377](gacha_simulator/core/pity.py#L377) 两处内联代码；`_featured_slots` 方法自身用 `.get(self._scope, ())`，[pity.py:497](gacha_simulator/core/pity.py#L497)）只对「键不存在」回退，会得到空元组并向 `_redistribute_scope` 传入空目标集、导致分布退化。§3.1.5.2 的算子在目标集非空前提下定义，该情形未覆盖 |

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
- **G15 pjsk 加权抽数**：近似可配（reward 注入 + 兑换池），严格语义留 milestone `weight_by_pool`（milestone 层，P64 范围外）
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

## 四、波及范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/pity_tracker.py` | **新增** | Tracker 家族（CounterTracker/FlagTracker/StreakTracker/FateTracker）+ Lifecycle（AlwaysActive/OnceActive/DependentActive）（~120 行） |
| `core/pity_modifier.py` | **新增** | Modifier 家族（BoostModifier/ForceFeaturedModifier/ForceNonFeaturedModifier/ForceSelectedModifier/InterceptModifier/ThresholdForceModifier/BaseRatioModifier）（~150 行） |
| `core/pity.py` | **重构** | 统一 Pity 骨架 + 10 个类型改造为 registry preset + `_BTYPE_ORDER` 加 `rotating_inverse` + `_resolve_order` 加 `priority` 排序（G5）。**G16 独立先行（不混入本行重构，§3.8）**：`_should_reset` 加 `never` 分支。**P82 接线独立先行（§1.5 裁决 1）**：`PityEngine` 独立排序视图 + `get_behaviors_for_pool()` 改消费它 |
| `core/config_toml.py` | 修改 | reset 枚举 `never` + `rotating_inverse` 校验放行 + **移除事件驱动型 deactivate_on_early_hit 拒绝分支（H3）** |
| `core/config_store.py` | 修改 | PityDef 新增 `priority` 字段（G5） |
| `gui/config_panel.py` | 修改 | **新建 reset 控件**并加「永不重置」（G16，现无该控件）；`_PITY_TYPES` 硬编码列表手工追加 `rotating_inverse`（type 下拉非 registry 驱动）；priority 编辑控件（G5） |
| `service/gacha_service.py` | 修改 | 定轨识别 `isinstance(bh, TargetedBehavior)` → `getattr(bh, '_btype', '') in ('targeted', 'targeted_soft')`（H1） |
| `config/config.toml` | 更新 | 幻塔 `rotating_inverse` + G16 示例段 |
| `tests/` | 新增/修改 | 等价性测试（旧类 vs 新引擎，全部类型）+ G1/G5/G16 测试 |
| 手册 | 更新 | G1/G16 登记（G19/G13/G2/G14/G15/G5 已同步，2026-08-24） |

**不受影响**：PityEngine 调度层接口签名、`_validate_behaviors`、PityState/DrawInfo/PityContext、_redistribute_scope、GUI 参数控件、P75 `_rebind_state` 纪律（Pity 统一实现后语义不变）

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
| **映射表未写死的实现细节致等价性失败**（计数相位 / CR 随机数短路） | 两条已在 §3.1 列为强制约束（N1 / H4），§六 设对应断言；两者共同点是均不报错、只让结果静默偏移，故必须在 S1/S5 显式实现与断言。did_fire 一项已按 §3.1.1 M4 裁决为统一语义，属行为变更，走独立验收（可先行） |

## 六、验收标准

### 主线（Tracker + Modifier 统一骨架 + G1 + G5）

- [ ] 全部 10 个类型同配置下，新引擎输出概率分布 + 状态快照与旧类**逐场完全一致**（固定种子，含 hard/soft_step/rotating/rotating_cr/targeted/soft 组合各基准）
- [ ] `cr_state_probs` 含 (0,1) 中间值的用例等价性通过（随机数消耗对齐，H4）
- [ ] **计数相位（N1）**：`hard(threshold=90)` 首次 100% 出现在第 90 抽；`soft` 的 boost 起始抽数与旧实现相同
- [ ] **did_fire 统一语义（M4）**：三类的 `did_fire` 均等价于「本次抽卡是否让本保底回到初始状态」，与各自 `after_draw` 的重置分支严格同条件；rotating/targeted 新补的 scope 门控属增量能力，按「不在等价性范围内」单独验收
- [ ] **N1 例外**：`deactivate_on_early_hit=True` 且命中时，`commit` 跳过 counter 重置，状态快照与 `get_counter()` 与旧实现一致
- [ ] **Lifecycle 增量能力单独验收**：配 `depends_on` 的事件驱动型在激活前不改分布、不更新状态（旧实现为惰性，属行为变更，不在等价性范围内）
- [ ] **CR 随机数短路（H4）**：`cr_base_rate == 0` 与 `cr_state_probs` 含 0 的用例中，随机数消费次数与旧实现逐位相同
- [ ] `rotating_inverse` preset 正确：出 UP → 下一次 SSR 必非 UP；出非 UP → 恢复基础比例（G1）
- [ ] PityEngine 调度层接口签名不变（`before_draw`/`after_draw`/`get_probabilities`）；`_validate_behaviors` 逻辑不变
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

> G16 独立 2 子块 + P82 接线独立 2 子块 + 主线 7 子块（含全量 preset 化），共 11 子块；G16 与 P82 接线均独立先行，不占 P64 主线。

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

### GATE-5 回滚策略

- **回滚单元**：G16 独立；主线整体一次回滚（全量 preset 化不分阶段，保留旧类到等价性测试通过为止）
- **等价性测试失败**：立即停止主线，保留失败 preset 为「未迁移」，回退 registry 到该 preset 指向旧类
- **G16**：独立 commit，与 P64 主线完全解耦，可随时 cherry-pick 或 revert
- **发布前**：主线完成后一次性移除旧保底类（无历史包袱原则，`RELEASED=False`）

---

*设计评审记录：2026-08-23 用户裁决路线 B（代码组合）、soft 纳入、无完全声明式状态机、G16 独立先行。2026-08-23 独立审查 14 项修正（H1-H4/M1-M6/L1-L4）。2026-08-24 设计重建：Tracker+Modifier 双层纯函数架构（用户裁决命名），范围从事件驱动 6 类扩大到全部保底类型统一，G2 归 milestone 层修正。本计划未含 ISSUE 体系——待 plan-review 工作流审查后补充。*
