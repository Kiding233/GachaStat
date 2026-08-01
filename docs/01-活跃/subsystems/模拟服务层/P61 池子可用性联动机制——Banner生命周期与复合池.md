<!-- META: P61 | module:模拟服务层 | status:designing | last:2026-08-01 -->

# P61 池子可用性联动机制——Banner生命周期与复合池

> 日期：2026-08-01 | 状态：设计中（原方案重写 + 五轮归约：类型/复刻推导化、Lifecycle 统一为 switch_to、方案甲）
> 触发：step池拆分建模（每步抽N次后解锁下一步）与终末地30抽取送抽池（强制插入、一次性、不计保底）需要池间可用性联动，当前仅支持基于时间窗口的单池独立可用性。
> 原方案归档：[P61 池子可用性联动机制——step链与送抽插入（规则引擎版）](../../../03-归档/P61 池子可用性联动机制——step链与送抽插入（规则引擎版）.md)（2026-06-20，已归档）

## 一、问题

### 1.1 功能缺口

当前池子可用性仅基于 `available_from` / `available_until` 时间窗口判断（`Pool.is_available_at()` → `GachaService.run_simulation` 的 `current_pools` 列表推导）。存在三个无法建模的场景：

| 场景 | 机制 | 缺失能力 |
|------|------|---------|
| **Step 池链** | 拆分 N 个阶梯，step N 抽满 M 次后解锁 step N+1，step N 不可用 | 池内阶段切换 + 抽数阈值触发 |
| **送抽插入** | 主池累计 30 抽 → 强制弹出独立送抽池 → 必须先抽送抽才回主池 → 送抽不计主池保底 | 强制插入 + 切换接管 + 一次性消耗 + 保底旁路 |
| **新手池关闭** | 抽满 N 次或出特定卡后永久关闭 | 退出条件触发 + 永久耗尽 |

更根本的问题有四个：

1. **配置单元 ≠ 模拟单元 ≠ 统计单元**：终末地的「限定寻访」对玩家而言是**一个卡池**，但当前方案要求用户手动创建 3 个 `[[pool]]`（主池 + 送抽池 + 档案池）并手动连线。统计时3行独立的 pool 数据需手动聚合。

2. **策略层看到的是物理池而非逻辑池**：策略需要理解 `INTERRUPTED`、`STEP_PASSED` 等内部状态，并在9个物理池之间做路由——这些是实现细节，不应该暴露给策略。

3. **每个新订阅者都要改 `gacha_service.py`**：加 P61 要加 `availability_engine.on_draw()`，加 P58 要加 `milestone_engine.on_draw()`。循环与每个组件紧耦合。

4. **规则引擎每迭代重算**：`遍历(pool, rule)` 笛卡尔积 O(P×R) 每轮重新评估——答案只在事件发生时改变。

### 1.2 设计反思（原方案的问题）

原 P61 方案（2026-06-20）采用 `AvailabilityEngine` 规则引擎——4 条规则通过注册表驱动，笛卡尔积评估。方案功能完整，但存在三个架构层面的概念混淆：

| 问题 | 原方案表现 | 根因 |
|------|-----------|------|
| 用「查询」替代「状态机」 | `InterruptRule` 每轮问「父池抽够30次了吗？」 | 转换条件检查 vs 状态存储分离 |
| 配置泄漏实现细节 | 用户手动创建3个 `[[pool]]` + `InterruptConfig` 连线 | Pool 是物理单位，用户需要的是逻辑单位 |
| 调用方依赖被调用方 | `gacha_service.py` 直接 import P61 和 P58 模块 | 回调模式下的紧耦合 |

## 二、目标

核心交付四个东西：

1. **Banner（逻辑卡池）** — 用户配置和统计的一等单位。内部包含多个 Pool（抽取源），Pool 对用户透明。Banner 自动管理 Pool 之间的切换、耗尽。
2. **Lifecycle（声明式生命周期）** — `on 条件 → action` 规则驱动阶段转换，替代规则引擎的每迭代重算。
3. **Notifier（轻量通知机制）** — `core/notifier.py`（~30行），P61和P58通过订阅同一事件总线协作，互不 import 对方模块。
4. **TransitionPreview（策略可见进度）** — 策略可查询「还差多少抽触发下一阶段」。

覆盖场景（与原方案一致）：

- [x] Step 池链：step1→step2→step3 按抽数阈值自动切换
- [x] 送抽插入：主池30抽后触发，切换到送抽池，送抽源消耗完毕后切回
- [x] 新手池关闭：`max_draws` 硬上限 + 可选 `card_obtained` 提前退出
- [x] 一次性池：`one_shot` pool 抽后永久不可用
- [x] 保底排除：`excludes_all_pity` pool 完全旁路保底引擎
- [x] 向后兼容：不写 `[[banner]]` 时现有 `[[pool]]` 自动包装为单 pool 的 banner

## 三、方案

### 3.1 核心概念

```
Banner（卡池——用户配置和统计的一等单位）
  ├─ Pool（内部池——自包含的抽取单元：cost + batch + rewards + 开关属性）
  ├─ Lifecycle（生命周期——on 条件 → action 的声明式规则）
  └─ TransitionPreview（策略可见的进度信息）

Notifier（通知机制——P61和P58共享的解耦层）
  ├─ subscribe(event_type, handler, priority)
  └─ emit(event_type, **data)
```

命名说明：`Banner` / `Pool` 沿用英文 gacha 社区的标准化区分——Banner 是抽取入口+规则，Pool 是奖池内容。

### 3.2 新增文件：`core/banner.py`

> **归属说明（方案甲）**：`Pool` 定义落在 `core/pool.py`（原地改造，见 §3.4），`core/banner.py` 只新建 `Banner` / `Lifecycle` / `TransitionRule`。下方集中展示全部数据结构，文件归属以 §3.4 为准。

```python
# ── 数据结构 ──

@dataclass
class Pool:
    """Banner 内部的独立抽取单元——自包含，不引用外部"""
    id: str                          # pool 标识符，如 "main"、"free_10pull"、"step2"
    cost: PoolCost                   # 抽取成本（必填——每个 Pool 独立确定）
    rewards: List[Tuple[Reward, float]]  # 奖励表（必填——内联，非引用）
    batch_size: int = 1              # 每次抽取连数
    one_shot: bool = False           # 一次性批次消耗——本池仅支持一次 batch（batch_size 抽，默认 1）
                                     # 后即标记 exhausted；批次中途不因 one_shot 耗尽而切换/终止，
                                     # 耗尽判定落在批次边界（REVIEW-R1-FIX: ISSUE-002，见 §3.5 批次语义）
                                     # ⚠ 待人工裁决（DECISION-1，见 §6.1 裁决门控）：原语义为「抽取1次后即
                                     # 标记 exhausted」，与旗舰 free_10pull（batch_size=10 + one_shot=true）
                                     # 直接冲突；本方案定为「一次性批次」以兑现「免费十连=10 抽」语义。
                                     # 默认选型已定（一次性批次）；若用户在 Ph1 启动前裁决改走旧语义，
                                     # 需同步调整 §3.5 批次语义 / §3.6 示例 / Ph9 用例 / §七 验收
    excludes_all_pity: bool = False  # 完全旁路保底引擎
    max_draws: Optional[int] = None  # 该 pool 的最大抽取次数（由引擎自动执行——pool 抽数达上限后自动标记 exhausted，无需手写 lifecycle 规则）

    # ── 推导属性（从 rewards 计算，非配置字段，见 §3.13.1）──
    #   output       = 'resource' if 全部 reward.id == '_no_card' else 'card'
    #   random       = bool(rewards) and (len(rewards) > 1 or rewards[0][1] < 1.0)     # 空 rewards 短路为 False
    #                  （tuple 表示：概率是元组第二元素，Reward 无 .prob 属性——REVIEW-R1-FIX: ISSUE-008）
    #   is_exchange  = output == 'card' and not random


@dataclass
class TransitionRule:
    """声明式转换规则：条件满足 → 切换到 target 池（或终结 Banner）"""
    condition: str                   # "pool_draws" | "banner_draws" | "card_obtained"
                                     # | "pool_exhausted" | "time_window"
    pool: Optional[str] = None       # 条件关联的 pool id（card_obtained 时为匹配目标）
    at_value: float = 0.0            # 阈值（pool_draws/banner_draws/time_window 条件时）。
                                     # time_window 为浮点【秒】（运行时单位，见下方「时间单位规范」ISSUE-001——
                                     #   与 Banner.available_from/until 一致；TOML/UI 层「天数」在解析/保存边界
                                     #   换算 *DAY///DAY，非直接落值）；
                                     # 抽数条件解析时校验为整数（REVIEW-R1-FIX: ISSUE-009）
    match: str = "card_id"           # card_obtained 的匹配方式："card_id" | "rarity"（与 LifecycleRuleEntry.match 对应）
    action: str = "switch_to"        # "switch_to"（停用当前活跃池 + 激活 target）
                                     # | "exhaust_banner"（终结 Banner，无需 target）
    target: Optional[str] = None     # 切换目标 pool id（action=switch_to 时必填）

    # ── 触发语义：边缘触发（edge-triggered）──
    # 条件从 False→True 转变的那次评估执行一次；持续满足不重复；条件回落后再满足可重新触发。
    # 阈值型（pool_draws/banner_draws/time_window）：单调递增，达到即触发一次。
    #   time_window 为当前模拟时间(秒) >= at_value(秒)，是 Banner 窗口内的阶段切换时间触发
    #   （ISSUE-001：运行时单位为秒，天数仅在 TOML/UI 边界换算）。
    # 事件型（card_obtained/pool_exhausted）：事件发生时本次评估为 True，每次事件都触发。
    _prev_satisfied: bool = False    # 上次评估时的条件满足状态（引擎维护，非配置字段）
```

> **时间单位规范（REVIEW-R1-FIX: ISSUE-001——统一为秒）**：运行时 `Banner.available_from` / `Banner.available_until` 与 `time_window` 条件的阈值（`TransitionRule.at_value` / `LifecycleRuleEntry.at`）一律以**秒**存储/求值——与模拟层 `real_time`、`end_time`、现状 `PoolSchedule.available_from/until`（batch_simulator.py:552-553 的 `start_day * DAY`）同单位。TOML/UI 层的「模拟内相对天数」在**解析边界**（config_toml `_wrap_pools_as_banners` / `_build_banners`）换算 `* DAY`、**保存边界**（`save_toml`）换算 `// DAY`（DAY=86400，沿用 batch_simulator.py:499 / core/resource_gain.py:24 常量，config_toml.py 侧自行定义或引入）。判定链据此对齐：`banner_end_times_sorted` 在 `real_time(秒) >= available_until(秒)` 触发 `on_banner_end`；`time_window` 在 `real_time(秒) >= at_value(秒)` 求值；策略 `wait_time = banner.available_until(秒) - real_time(秒)`；`AllPoolsEndCondition(end_time 秒)` 判定成立。现状 None end_day 兜底为 `(start_day + 21) * DAY` 秒（batch_simulator.py:511-513），计划 §3.13.4 对应 `+ 21 * DAY`（秒），两者等价——计划全文涉及「天数」的判断（§3.2 触发语义 / §3.4 包装 / §3.5 banner_end_times / §3.13.4 eff_end）均以本规范为唯一单位口径。


@dataclass
class TransitionPreview:
    """策略可读的进度信息——「还差多少触发什么」"""
    trigger: str                     # 触发条件类型
    remaining: int                   # 还差多少（阈值型语义；事件型为 -1，REVIEW-R1-FIX: ISSUE-305）：
                                     #   pool_draws/banner_draws：max(0, at_value - current_value) 剩余抽数
                                     #   time_window：max(0, ceil(at_value - 当前时间)) 向上取整剩余天数
                                     #     （不截断小数——2.5 天→3 而非 2，避免近边界垫刀 1 天误差）
                                     #   card_obtained/pool_exhausted（事件型）：无法预估剩余抽数 → -1
                                     #     （不可预估），策略必须 `pt.remaining >= 0` 守卫后再做垫刀决策
    at_value: float                  # 阈值（time_window 为浮点【秒】——运行时单位，TOML/UI 层天数经 *DAY 换算，
                                     #   ISSUE-001；抽数条件为整数——REVIEW-R1-FIX: ISSUE-009）
    current_value: int               # 当前进度
    action: str                      # "switch_to" | "exhaust_banner"
    description: str                 # 人类可读描述
    target_pool: Optional[str] = None
    switches_current: bool = False   # 触发后当前活跃池是否被停用（switch_to 且 target != 当前池）


@dataclass
class DrawOutcome:
    """单抽结果——携带本次实际产出的池与保底判定，避免事后读 active_pool_id 的时序歧义
    （REVIEW-R1-FIX: ISSUE-008）"""
    reward: "Reward"
    pool_id: str          # 本次抽卡实际产出的池 id（必须显式携带；draw 内仅可能因耗尽/自动 exhaust
                          # 改变状态，switch_to 统一由 after_draw 订阅触发——ISSUE-001）
    pity_triggered: bool  # 本次是否触发保底（featured_ids 判定，等价现状 gacha_service L305-316）
    triggered_pity_name: Optional[str] = None
                          # 触发保底名称（逗号拼接）。与 pity_triggered 同源计算——现状
                          # gacha_service.py:310-316 的 `','.join(spec.pity_names)` 逻辑迁入 Banner.draw，
                          # 随 DrawOutcome 返回（REVIEW-R1-FIX: ISSUE-003）。
                          # 供 collector.on_draw 的 triggered_pity_name（compact draw_pity_names）数据源，
                          # 否则 compact 逐抽记录该字段恒为 None、InfoVector 同步丢失


@dataclass
class Banner:
    """卡池——用户配置的一等单位"""
    id: str
    name: str
    pools: Dict[str, Pool]                          # pool_id → Pool
    lifecycle: List[TransitionRule]                # 平铺规则，每轮边缘触发评估（触发语义见 TransitionRule）
    max_draws: Optional[int] = None                 # Banner 级总抽数硬上限——由引擎自动执行（与 Pool.max_draws 对称，
                                                     #   REVIEW-R1-FIX: ISSUE-303）：每抽后 `_total_draws >= max_draws` →
                                                     #   自动 `_exhaust()`，无需手写 `banner_draws → exhaust_banner`
                                                     #   lifecycle 规则（§3.6 新手池示例已移除冗余规则）。该自动耗尽属
                                                     #   硬上限守卫、不评估 lifecycle 规则——与 ISSUE-001「转换单一触发点
                                                     #   （after_draw 订阅）」不冲突
    available_from: Optional[float] = None          # 时间窗口起点（唯一时间窗口，Pool 级已退役，见 §3.13.4）
    available_until: Optional[float] = None         # 时间窗口终点

    # 运行时状态（无 phase 概念——active_pool_id 是唯一阶段状态，见 §3.13.5）
    _active_pool_id: str = "main"    # 单活跃池模型：切换即停用旧池 + 激活新池
    _exhausted_pools: Set[str] = field(default_factory=set)
    _pool_draws: Dict[str, int] = field(default_factory=dict)
    _total_draws: int = 0

    # ── 策略可见属性 ──
    @property
    def is_available(self) -> bool: ...
    @property
    def is_exhausted(self) -> bool: ...
    @property
    def active_pool(self) -> Pool: ...
    @property
    def total_draws(self) -> int: ...
    @property
    def pending_transitions(self) -> List[TransitionPreview]: ...

    # ── 核心方法 ──
    def draw(self, state, pity_engine, pity_state, pool: Optional["Pool"] = None) -> "DrawOutcome":
        """路由到活跃 pool（或显式传入 pool）执行单抽（REVIEW-R1-FIX: ISSUE-003/004/005）：
        1) excludes_all_pity → 旁路 before_draw/after_draw，不触碰 pity_state（保底旁路）
        2) 正常 pool → P55 概率聚合(aggregate_probs_by_rarity，core 层模块级函数——REVIEW-R1-FIX: ISSUE-004)
           → before_draw 调整 → scale_factors 还原卡级概率 → _apply_probabilities → pool.draw() → after_draw
        3) 计算 pity_triggered + triggered_pity_name（featured_ids 判定 + spec.pity_names 拼接，等价现状
           gacha_service L305-316），携带实际产出 pool_id 返回 DrawOutcome

        顺序约定（REVIEW-R1-FIX: ISSUE-001——单一触发点）：draw() 内部【不】评估 _check_transitions。
        转换统一由「after_draw 事件 → P61 订阅（priority=1）→ banner._check_transitions()」触发，
        位于 emit 之后、下一抽之前——转换只影响下一抽，不污染本次返回的 pool_id。
        draw() 内部唯一可能的状态变化：当抽 pool 因 max_draws/one_shot 达到耗尽而标记 exhausted
        （公式见下方「耗尽判定归属与公式」：`one_shot and _pool_draws[id] >= batch_size` /
        `_pool_draws[id] >= max_draws`；Banner.max_draws 硬上限自动 exhaust——REVIEW-R1-FIX: ISSUE-302/303）。"""

    def _check_transitions(self, card_id: Optional[str] = None,
                           real_time: Optional[float] = None):
        """评估全部 lifecycle 规则，条件满足（边缘触发）时执行 switch_to / exhaust_banner。
        由 after_draw 事件订阅触发（P61 priority=1，装配见 §3.5「Notifier 装配位置」/ §5.2）——
        不直接由 Banner.draw 调用，避免同一次抽卡后 _check_transitions 被评估两次、同一 draw
        周期内级联触发第二次转换（REVIEW-R1-FIX: ISSUE-001）。每抽至多评估一次 → 至多一次转换。
        本次抽取的统计归属（pool_id）不受转换影响（REVIEW-R1-FIX: ISSUE-008）。

        输入来源（REVIEW-R1-FIX: ISSUE-001）——五个条件中 card_obtained / time_window 两个一等
        条件无法从 Banner 内部状态获取（无 card_id / real_time 落库），必须由 after_draw 订阅
        handler 透传事件数据：
        · card_obtained（事件型）：本抽产出 card_id（handler 传入）匹配条件 target
          （match="card_id" 精确卡 / match="rarity" 稀有度）
        · time_window（阈值型）：当前模拟 real_time（handler 从 state 取）评估 real_time >= at_value
        · pool_draws / banner_draws / pool_exhausted：从 Banner 内部状态
          （_pool_draws / _total_draws / _exhausted_pools）读取，无需入参"""

    def _switch_to(self, pool_id: str): ...    # 停用当前活跃池 + 激活 target
    def _exhaust(self): ...
```

> **兜底语义（活跃池耗尽，REVIEW-R1-FIX: ISSUE-010）**：单 Banner 内活跃池因 `max_draws` / `one_shot` 触发 exhausted 后，若无 `pool_exhausted` lifecycle 规则接管（允许只配置一个池），Banner **自动 exhaust**（等价 `exhaust_banner` 兜底）——`is_available=False`、策略侧 `is_exhausted=True`、`pending_transitions` 无挂起项，draw() 不再被调用。避免路由到已耗尽池产生未定义行为。该语义进入 `_exhaust()` 实现。
>
> **耗尽判定归属与公式（REVIEW-R1-FIX: ISSUE-002，批次边界机制修正——ISSUE-302）**：耗尽判定与标记在 `Banner.draw` 内执行（唯一逐抽粒度入口，`_pool_draws[id]` 每抽自增）：
> - `one_shot`：`_pool_draws[id] >= batch_size` 时标记 exhausted——判定天然落在批次末抽（一次性批次），批次中途不触发（与 §3.5 批次语义一致）。
> - `pool.max_draws`（Pool 级）：`_pool_draws[id] >= max_draws` 时标记 exhausted。**判定可能落在批次中途**（max_draws 非 batch_size 倍数，如 max_draws=15 / batch_size=10 时第 15 抽落在第 2 批次中途）——max_draws 是硬上限，标记后**立即生效**：batch 循环在下一抽入口检查 active 池已 exhausted（无 `pool_exhausted` 规则接管时 Banner 自动 exhaust 亦然），`break` 终止本批次剩余抽数，总抽数不被批次惯性突破（§3.5 批次循环新增守卫）。**旧表述「耗尽判定均落在批次边界」修正为**：one_shot 判定点在批次边界；pool.max_draws 判定点可能在批次中途、生效点为下一抽入口（batch 循环 break）。**⚠ 待人工裁决（DECISION-2，见 §6.1 裁决门控）**：批次中途耗尽处置选「立即生效 + batch 循环 break 终止剩余」，未选「继续抽完本批次」——后者会把 max_draws 语义退化为批次边界近似（15/10 时抽满 20）；默认选型已定（立即生效 + break）；若偏好批次原子性优先可改走「继续抽完」，需同步调整 §3.5 批次循环守卫与 Ph9 用例。
> - `banner.max_draws`（Banner 级）：`_total_draws >= max_draws` 时 Banner 直接 `_exhaust()`——与 Pool.max_draws 对称的引擎自动执行（ISSUE-303，见 §3.6 新手池示例修正），不评估 lifecycle 规则、与 ISSUE-001 单一触发点不冲突。

### 3.3 新增文件：`core/notifier.py`

```python
# ~30 行，P61 和 P58 的共享基础设施

class Notifier:
    """轻量同步通知机制——不是事件溯源，不存储事件日志"""

    def __init__(self):
        self._subscribers: Dict[str, List[tuple]] = {}
        # { event_type: [(priority, handler), ...] }

    def subscribe(self, event_type: str, handler: Callable, priority: int = 0):
        """注册订阅者。priority 越小越先执行。"""

    def emit(self, event_type: str, **data):
        """同步分发——按 priority 升序遍历，逐个调用，全部完成才返回"""
```

P61 和 P58 通过 Notifier 协作的方式：

```python
# P61 侧 —— 发射事实（契约以 §3.5 为唯一真相，键名/取值源统一——REVIEW-R1-FIX: ISSUE-005；
#   draw_count/card 旧键弃用，pool_id 取本次实际产出的全限定键，不读 active_pool_id）
notifier.emit("after_draw",
              banner_id=banner.id,
              pool_id=draw_pool_key,          # 全限定键 {banner_id}.{pool_id}，本次实际产出
              card_id=reward.id,
              pity_triggered=triggered,
              state=state, collector=collector)

# P58 侧 —— 订阅事实（P58 模块内部，P61 不知晓）。
# 实际装配以 §5.4 的 register_milestone_engine(notifier, engine) 装配函数为准——
# notifier 实例由装配层创建并注入（§3.5「Notifier 装配位置」/ ISSUE-301），P58 不直接持有变量
notifier.subscribe("after_draw", milestone_engine.after_draw, priority=0)
```

**关键约束：**
- Notifier 不存储事件历史——它不是事件溯源，只是分发机制
- 所有订阅者是同步调用的——emit() 返回时所有 handler 已执行完毕
- 优先级保证顺序：P58（资源注入，priority=0）→ P61（生命周期检查，priority=1），避免「P61检查时资源还没注入」的竞态
- P61 不 import P58 的任何符号，反之亦然

### 3.4 旧 Pool 与 Banner 的关系（方案甲：原地改造）

Banner 内的抽取单元就是旧 `Pool`（`core/pool.py`）**同一个类**，原地改造，不另起同名类：

- 旧 `Pool` 原地新增 P61 字段：`one_shot` / `excludes_all_pity` / `max_draws`
- 移除死字段：`pool_type`（类型改推导属性，见 §3.13.1）、`is_rerun` / `original_pool_id`（复刻走推导，见 §3.13.2）、`available_from` / `available_until`（时间窗口统一到 Banner 级，见 §3.13.4）
- 现有字段保留：`id` / `name` / `cost` / `rewards` / `batch_size` / `epitomizable_cards`
- 推导属性（非配置字段，从 rewards 计算，见 §3.13.1）：`output` / `random` / `is_exchange`（旧策略 `pool.is_exchange` 零改动）

**方法处置：**
- 保留：`__post_init__`（权重初始化）、`_apply_probabilities`（保底引擎调整概率，gacha_service L299/301 消费）、`draw()`
- 退役：`is_available_at()`（基于退役的 available_from/until，无法再工作）——消费点全部迁移到 Banner 级（见下）

**消费点适配（策略迁移是 Ph1 的强制组成部分，非可选项）：**
- `is_available_at()` 的活跃消费者：smart.py:49 / pity_reserve.py:37 / pool_quota.py:39 / stop_on_target.py:48（`pool.is_available_at(ctx.state.real_time)`）+ `GachaState.get_available_pools()`（state.py:90）。`available_until` 字段被 draw_target.py:39-41 / no_draw.py:22-23 / smart.py:66-67 / pity_reserve.py:56-57 / pool_quota.py:62-63 / stop_on_target.py:57-58 的 wait_time 计算读取。Ph1 删除字段/方法后，上述调用点全部抛 AttributeError——计划必须同步迁移策略，否则「现有策略不作修改即可运行」验收与实现直接冲突（REVIEW-R1-FIX: ISSUE-001）。
- **迁移方案（新增 Ph1a，见 §3.12）**——8 个内置策略（smart / pity_reserve / pool_quota / stop_on_target / draw_target / no_draw / fixed_count / target_hunting）统一以 `ctx.banners` 为读取源，逐项替换：
  - `pool.is_available_at(real_time)` → `banner.is_available`（§3.7 策略接口，可用性已含生命周期激活状态）
  - wait_time 计算：遍历 `ctx.banners`，取未耗尽 Banner 的 `banner.available_until - real_time`（`available_until is None` 跳过）——不再读 `pool.available_until`。二者均为秒（`banner.available_until` 经 §3.4 包装 *DAY，ISSUE-001），秒减秒结果正确，不再 86400 倍错位
  - `DrawAction(pool_id=...)` → `DrawAction(banner_id=banner.id, pool_id=pool.id)`（双字段契约，见 §3.5 / ISSUE-006）
  - `pool.is_exchange` 判定保留（§3.13.1 推导 property，零改动）；`pool.cost` / `pool.batch_size` 经 `banner.active_pool` 读取（`banner.active_pool.cost` / `.batch_size`）
  - **`pool_quota.py:45-48` 的配额判定（REVIEW-R1-FIX: ISSUE-002）**：`pid = pool.id; drawn = ctx.pool_draw_counts.get(pid, 0)`——逐池统计键全限定化后 `ctx.pool_draw_counts` 键为 `{banner_id}.{pool_id}`，裸 pid 查询**恒 0、配额永不满足、持续抽到资源耗尽**。改为遍历 `ctx.banners` 读 `banner.pool_draws.get(pool_id)`（§3.7 已暴露，pool_id 为 Banner 内裸池 id、非全限定键）判配额
  - **`pity_reserve.py:46` 的保底概率查询（REVIEW-R1-FIX: ISSUE-002）**：`pool_probs = ctx.get_pity_probabilities(pool.id)`——裸 pid 传 PityEngine 查不到全限定 spec（pity.py:1268-1270 `spec = self.pool_specs.get(pool_id)` 为 None 时回退未调整概率），保底阈值判定**静默退化为基础概率**。改为传全限定键 `{banner_id}.{pool_id}`，或 `StrategyContext` 新增 banner 维度查询接口（如 `get_pity_probabilities_for_banner(banner_id, pool_id)`，Ph5 排期）；二者任一须在 Ph9 以 banner 模式等价回归锁定（ISSUE-002）
  - fixed_count / target_hunting 目前只读 `ctx.current_pools`（无时间字段依赖）——**一并纳入 Ph1a 强制迁移（REVIEW-R1-FIX: ISSUE-003）**，原「可不迁移但须回归验证」取消。原因：`current_pools` 由 `active_banners[*].active_pool` 推导填充时，`[[pool]]` 自动包装模式下所有 Pool 的 `.id` 均为包装写死的 `'main'`——fixed_count.py:27 `DrawAction(pool_id=ctx.current_pools[0].id)` 得 `pool_id='main'`，多 Banner 共存时反查不唯一（§3.5 要点 5 的反查规避依赖 Ph1a 双字段，但这两个策略此前被豁免，自相矛盾）；target_hunting.py:25 `[p for p in ctx.current_pools if p.id in self.target_pool_ids]` 的 `target_pool_ids` 是用户配置的旧裸池 id（如 `'genshin_limited'`），与 `'main'` 永不匹配 → `target_pools` 恒空 → 策略静默只 WaitAction、永不抽卡。迁移内容与 8 策略一致：改读 `ctx.banners` + `DrawAction(banner_id=..., pool_id=...)` 双字段；`target_pool_ids` 参数改匹配 `banner_id`（兼容旧裸池 id 时按 `banner_id` 段匹配）。`current_pools` 保留仅供遗留只读，无内置策略再依赖
- `state.available_pools`（state.py:90）基于 Pool 时间窗口，P61 后由 Banner 可用性取代——**删除 `GachaState.get_available_pools()` 方法**，同步删除 `tests/core/test_state.py:73-82` 的 `test_get_available_pools`（该测试是方法唯一活跃消费者，且构造期传 `available_from`/`available_until` 关键字、随字段退役一并失效）。`core/state.py` 因此从「不触及」移入波及范围（删除一行方法 + 清理 import）（REVIEW-R1-FIX: ISSUE-002）

迁移路径（旧 Pool 直接作为 Banner 的抽取单元，无字段复制）：

```python
# 向后兼容：现有 [[pool]] 自动包装为 Banner（config_toml 解析时执行，操作 PoolEntry）
def _wrap_pools_as_banners(entries: List[PoolEntry]) -> List[BannerEntry]:
    """每个 PoolEntry 包装为单池 Banner——时间窗口从 start_day/end_day 上移到 Banner，
    并完整透传抽取语义字段，保证「现有 [[pool]] 行为完全不变」验收成立（REVIEW-R1-FIX: ISSUE-007）。
    透传清单（ISSUE-006 补全）：batch_size / exchange_card_id / epitomizable_cards / enabled /
    featured 标志（rewards dict 内）——distribution_template / bindings / target_specs 属配置/分析侧
    字段，不进入 Banner 运行时，由 flattened_pools 视图按 §3.9 重建。
    调用顺序（ISSUE-006）：必须在 _build_pools 全部步骤【之后】执行——rerun_of 第二步复制
    distribution（config_toml.py:1110-1115）与 featured_card_ids 统一填充（:1117-1119）完成后，
    再 _wrap；否则 rerun 池 distribution 为空、featured 丢失。"""
    banners = []
    for e in entries:
        if not e.enabled:
            # enabled=False 的 [[pool]] 包装前过滤——不生成 Banner（ISSUE-006）：
            # 等价现状 gdr.py:513 / worst_impact_panel.py:185 / retreat_panel.py:263 /
            # plan_search_panel.py:1259 的 `if p.enabled` 过滤；banner 模式下不出现即视为禁用
            continue
        rewards = [
            # PoolDistEntry → dict 转换（REVIEW-R1-FIX: ISSUE-304）：e.distribution 元素是 PoolDistEntry
            # dataclass（config_store.py:13-18，不可下标访问），而 BannerPoolEntry.rewards 标注 List[dict]、
            # §3.13.1 dict 形式推导 `rewards[0]['probability'] < 100.0` 与 featured 聚合
            # `{r['card_id'] for r in rewards if r.get('featured')}` 均按 dict 下标访问——必须在包装处统一
            # 转为 dict（card_id/probability/rarity/featured/resources_gained），否则 Ph6 运行时 TypeError
            {"card_id": de.card_id,
             "probability": de.probability,
             "rarity": de.rarity,
             "featured": de.featured,
             "resources_gained": dict(de.resources_gained or {})}
            for de in e.distribution
        ]   # featured 信息随 dict.featured 透传（banner 模式 per-reward featured，见 §3.9）
        if e.exchange_card_id:
            # 旧 exchange 池语义：is_exchange=bool(exchange_card_id)，产出该卡 100%——
            # 包装时展开为 100% 单卡分布（对齐 §3.6 的 exchange_card_id 语义）
            rewards = [{"card_id": e.exchange_card_id, "probability": 100.0}]
        banner = BannerEntry(
            id=e.pool_id, name=e.name, enabled=e.enabled,      # ← 透传 enabled（ISSUE-006，供 §3.13.4 可达判定）
            # available_until=None 兜底（REVIEW-R1-FIX: ISSUE-007）：end_day=None（永久池）时透传
            # None 而非 float(None) 抛 TypeError——None 语义为「永久开放」，end_time 计算由 Ph6 兜底
            # （§3.13.4），与现状 batch_simulator.py:511-513 的 None end_day → `(start_day+21)*DAY` 秒兜底等价
            # 时间单位（ISSUE-001）：start_day/end_day 为 TOML「天数」，解析边界换算 *DAY 为秒——
            # 与现状 batch_simulator.py:552-553 的 `start_day * DAY` 一致，Banner 运行时 available_from/
            # available_until 按秒存储（§3.2「时间单位规范」），否则 end_time / real_time 86400 倍错位
            available_from=float(e.start_day) * DAY,
            available_until=None if e.end_day is None else float(e.end_day) * DAY,
            pools=[BannerPoolEntry(
                id="main", cost=e.cost, rewards=rewards,
                batch_size=e.batch_size,                     # ← 透传：默认 1，batch 池不退化
                exchange_card_id=e.exchange_card_id,         # ← 透传：保留快捷方式
                epitomizable_cards=e.epitomizable_cards,     # ← P56 定轨候选卡透传
                # featured_card_ids 不设独立字段——由 rewards 的 featured=True 标志聚合：
                #   PoolPitySpec.featured_ids = {r['card_id'] for r in rewards if r.get('featured')}
                #   （batch_simulator.py:517 现状读 pe.featured_card_ids，banner 模式改读 rewards
                #    featured 聚合——保底重置判定数据源，ISSUE-006 / Ph6）
                #   （REVIEW-R1-FIX: ISSUE-304：rewards 已统一为 dict 表示——正常分支经上方
                #    PoolDistEntry→dict 转换、exchange 分支为 100% 单卡 dict——此聚合对两种分支均安全，
                #    无「对 PoolDistEntry 下标访问」的 TypeError）
            )],
        )
        banners.append(banner)
    return banners
```

**理由**：归约确认 `pool_type` / `is_rerun` / `original_pool_id` 是死代码或伪需求（§3.13）。方案乙（旧类保留 + 另起同名类）会让死字段继续存活，且字段复制制造「两套真相」，与单一真相源目标相悖。

### 3.5 GachaService 集成

> **集成契约要点（REVIEW-R1 修复）**：
> 1. `self._banners` 为 `Dict[str, Banner]`（banner_id → Banner，与现状 `self.pools` 的 dict 结构一致）——避免 `List` 无 `.get()` 的容器矛盾。（REVIEW-R1-FIX: ISSUE-006）
> 2. **逐抽结算归属**：`Banner.draw` 只负责「路由到活跃池 + P55 概率聚合/调整/还原 + 保底旁路 + 返回单抽结果」；**逐抽结算管线（spend / stats.on_draw / state.add_card 溢出 / collector.on_draw / 资源累加）与 batch 循环保留在 gacha_service**，与现状 L259-365 一致——不把 collector/stats/card_overflow_map/_initial_counts/资源累加等结算上下文整体搬进 Banner 造成签名膨胀。（REVIEW-R1-FIX: ISSUE-003）
> 3. **after_draw 按单抽粒度发射**——batch_size=10 的池每抽 emit 一次，P58 里程碑「每抽计数」与 collector 逐抽记录不丢。（REVIEW-R1-FIX: ISSUE-004）
> 4. **P55 聚合迁移（REVIEW-R1-FIX: ISSUE-005/004）**：`aggregate_probs_by_rarity`（featured/standard 槽位）+ `before_draw` 调整 + `scale_factors` 还原三段逻辑封装进 Banner.draw 内部，`pool._apply_probabilities` 仍在其中消费——送抽/step 等场景的槽位保底调整不静默丢失。**函数下沉（ISSUE-004）**：`_aggregate_probs_by_rarity` / `_infer_rarity_from_spec` 现为 GachaService 实例方法（gacha_service.py:123-171），core 层 Banner.draw 无法调用——下沉为 `core/pool.py` 模块级函数（`aggregate_probs_by_rarity(pool, pity_spec)` / `infer_rarity_from_spec(card_id, pity_spec)`，只依赖 `pool.rewards` + `PoolPitySpec` 结构），gacha_service 与 Banner.draw 共用。放 pool.py 而非 pity.py 以维持「不触及 core/pity.py」边界（Ph1 同步迁移，波及范围表已登记）。
> 5. **策略→服务动作契约（REVIEW-R1-FIX: ISSUE-006/004）**：`core/action.py` 的 `DrawAction` 新增 `banner_id: Optional[str] = None` 字段，且 `pool_id` 改为 `Optional[str] = None`（**ISSUE-004——现状 action.py:15-16 的 `pool_id: str` 无默认必填，`DrawAction(banner_id=banner.id)` 会 TypeError；给默认 None 后省略合法**）。派发规则：`banner_id` 优先；`banner_id=None` 时按 `pool_id` 反查唯一 Banner（旧单池兼容路径）；`pool_id=None` 时服务层经 `banner.active_pool` 路由（§3.5 伪代码 `pool = banner.active_pool` 已是此行为，与 action.pool_id 无关）。多 Banner 各含同名 `main` 时裸 `pool_id` 全局重复、映射歧义，故 Ph1a 策略迁移强制全部改写为 `DrawAction(banner_id=..., pool_id=...)` 双字段（显式 pool_id 为推荐写法，但可省——§3.7 示例合法）。主循环补全 **NonDrawAction 分支**（现状 gacha_service.py:367-368 → `_apply_non_draw` L87-121）：定轨切换/取消的 `action.params['pool_id']` 定位改为 `{banner_id}.{pool_id}` 全限定键（§3.11.3 命名空间），`pity_engine.get_behaviors_for_pool(pool_id)` 同步传全限定键。
> 6. **池结束快照机制迁移（REVIEW-R1-FIX: ISSUE-003）**：现状 `pool_end_times_sorted`（gacha_service.py:211-214，读 `Pool.available_until`）与 `collector.on_pool_end()`（L386-414）随字段退役失效。改为 `banner_end_times_sorted = sorted([(b.id, b.available_until) for b in banners.values() if b.available_until], key=lambda x: x[1])`，`on_pool_end(pid, ...)` → `on_banner_end(banner_id, ...)`，写 `CompactResult.banner_end_resources` / `banner_end_pity_states`。**单位（ISSUE-001）**：`banner.available_until` 为秒（§3.2「时间单位规范」），与 `real_time`（秒）同单位，`on_banner_end` 在 `real_time >= available_until` 触发——不再有现状秒、计划天 86400 倍错位（否则第 21 秒而非第 21 天触发池结束快照）。**P62 可达过滤（gdr.py:1115-1121）、per_pool_analysis.py:58/120/186 的 pool_end_times 累计快照、`core/vulnerability.py` 的 `pool_end_resources` / `pool_end_pity_states` 消费端一并迁移**（键语义：banner_id 取代 pool_id，Ph7 同步；vulnerability.py 若漏改，字段改名后 `r.get('pool_end_resources', {})` 静默拿到空 dict → `all_pool_ids` 为空 → `_fit_vulnerability_pava` 返回空 VulnerabilityAnalysisResult，脆弱性分析无声退化——REVIEW-R1-FIX: ISSUE-005）。
> 7. **emit 顺序（REVIEW-R1-FIX: ISSUE-014）**：`after_draw` emit 位于逐抽结算（stats.on_draw / add_card / collector.on_draw / combined_gained）**之后**、下一抽之前。P58 priority=0 注入的 milestone 资源进入 `state.resources`，但**不并入当抽** `combined_gained`/collector 记录（P63 单通道不可回溯）——里程碑资源注入语义为「下一抽起可用」，验收相应调整（见 §5.4）。
> 8. **`build_strategy_context` 签名（REVIEW-R1-FIX: ISSUE-005）**：下方伪代码以 `banners=` / `all_banners=` 关键字调用，但 `build_strategy_context()`（core/strategy_context_builder.py:24）当前签名无这两个参数——直接调用将 TypeError。Ph5 必须为 `core/strategy_context_builder.py` 新增 `banners` / `all_banners` 参数并透传进 `StrategyContext`；`current_pools` / `all_pools` 保留，由 `active_banners[*].active_pool` 推导填充——但内置策略（含 fixed_count / target_hunting）经 Ph1a 已全部迁移到 `banners`，不再依赖 `current_pools` 的裸 id 匹配（`[[pool]]` 包装模式下其元素 `.id` 全为 `'main'`、无法承载旧裸池 id，REVIEW-R1-FIX: ISSUE-003）。与 P58 M4a 共用同一函数签名，各自负责 `banners` / `_milestone_engine` 参数，避免合并冲突。
> 9. **时间单位规范（REVIEW-R1-FIX: ISSUE-001）**：运行时 `Banner.available_from`/`available_until` 与 `time_window` 阈值（`at_value`）以**秒**存储/求值，与 `real_time`/`end_time` 一致；TOML/UI 层「天数」在解析/保存边界 `* DAY` / `// DAY` 换算（DAY=86400，§3.2「时间单位规范」）。本节所有时间比较（`banner_end_times_sorted` 的 `real_time >= available_until`、`time_window` 的 `real_time >= at_value`、策略 `wait_time = available_until - real_time`、`AllPoolsEndCondition(end_time)`）均在秒单位下成立——不再出现「现状秒、计划天」的 86400 倍整体错位。
<!-- REVIEW-R2-FIX: AUDIT-BREAK-3 -->
> 10. **GachaService 构造桥（REVIEW-R1-FIX: GATE-3_依赖顺序，补充）**：`GachaService.__init__` 保持 `pools` 形参，但内部**双型收纳**为运行时 Banner 字典 `self._banners`：元素为 `Pool` → 就地单池包装 `Banner(id=p.id, name=p.name, pools={'main': p})`（键 `{pool_id}.main`，与 §3.4 [[pool]] 兼容包装一致；时间窗口 None 兜底，见 §3.13.4）；元素为 `Banner` → 直接收纳 `{b.id: b}`。任一分支保证原子提交后 `self._banners` 非空——`_run_single`（batch_simulator.py:228 传 `env.pools`）与现有 10 处测试（test_gacha_service.py:32/51/78/101/121、test_batch_service.py:25、test_batch_draw.py:171/212/260/314）直接构造 `GachaService([pool],...)` 均有池可路由。**桥与数据源分离**：Ph6 前 `List[Pool]` 路径的包装 Banner 时间窗口为 None（原子提交→Ph6 间时间窗口语义经 `PoolSchedule`/`end_time` 部分保留，banner 级窗口随 Ph6 从 `store.banner` 恢复）；Ph6 后 `from_config_store` 从 `store.banner` 构建运行时 Banner（多池/lifecycle/时间窗口），`SimulationEnv.pools` 承载 `List[Banner]`、`_run_single` 调用签名不变、`__init__` 直接收纳——任何阶段 `self._banners` 非空。
> 11. **全限定键推导口径（REVIEW-R1-FIX: ISSUE-021/AUDIT-BREAK-3，消除 `{pid}.{pid}` vs `{pid}.main` 歧义）**：全限定键一律由 **`f"{banner.id}.{pools字典键}"`** 推导——`pools` 字典键（`Banner.pools` 的 key）是唯一口径，**不得**用 `pool.id` 属性。构造桥 `Banner(id=p.id, pools={'main': p})` 中 `p` 的 `.id` 仍是旧 pool id（≠ 'main'），若 `DrawOutcome.pool_id` / `active_pool_id` 取 `pool.id` 会得到 `{旧pid}.{旧pid}`，与兼容模式约定 `{旧pid}.main`（§3.11.3）不一致。故 `Banner.draw` 返回的 `DrawOutcome.pool_id`、`active_pool_id`、`banner.pool_draws` 的键一律为 **pools 字典键**（单池包装下恒 'main'），`draw_pool_key = f"{banner.id}.{draw_pool_key_from_dict}"` 恒为 `{旧pid}.main`。§3.5 伪代码 `draw_pool_key = f"{banner.id}.{draw_pool_id}"` 中 `draw_pool_id` 即此口径（pools 字典键，非 Pool.id）。
> 12. **原子提交态 pity 键一致性（REVIEW-R1-FIX: ISSUE-021/AUDIT-BREAK-3，阻塞 2）**：Ph2 将 gacha_service 的 PityEngine 查询键（`get_spec`/`before_draw`/`after_draw`）改为全限定 `{banner_id}.{pool_id}`，但 `_build_pity_engine_from_gui`（batch_simulator.py:139-158）构建的 `pool_specs` 键在 **Ph6 前仍是裸 `pool.id`**（from_config_store 构造的 Pool 带旧裸 id）。原子提交态（Ph1-Ph2 落地、Ph6 未落地）下 gacha_service 以 `{旧pid}.main` 查询 → `pool_specs.get` 为 None → `before_draw` 保底调整静默跳过 → **soft pity 静默失效**，与 GATE-3『首提交后 pytest 全量通过』及『现有 `[[pool]]` 行为完全不变』验收直接冲突。处置：**pool_specs 键的全限定化提前并入原子提交**（随 Ph2 或构造桥一起落地）——原子提交态 `_build_pity_engine_from_gui`/`from_config_store` 的 pool_specs 键改为 `{pool.id}.main`（单池包装口径），fnmatch 三路匹配（§3.11.3，ISSUE-005）同步实现；Ph6 起键由 banner 池展开（多池/lifecycle）自然承接，无二次迁移。此改动把原 Ph6 的一部分（pool_specs 键全限定 + 三路 fnmatch）前移进原子单元，Ph6 仅保留「数据源改 store.banner + 多池展开 + featured/ssr/rarity 来源」。

```python
# gacha_service.py 的变更：current_pools → current_banners

def run_simulation(self, ...):
    banners = self._banners            # Dict[str, Banner]（banner_id → Banner）
    notifier = self._notifier          # Notifier 实例——装配见下方「Notifier 装配位置」（REVIEW-R1-FIX: ISSUE-001）

    for iteration in range(max_iterations):
        if _check(state, [], stats):
            break

        # 可用性过滤——Banner 级别，O(B) 而非 O(P)
        active_banners = [b for b in banners.values() if b.is_available]

        ctx = build_strategy_context(
            state=state,
            banners=active_banners,          # ← 替代 current_pools
            all_banners=list(banners.values()),  # ← 替代 all_pools（策略可查看未激活的 banner）
            ...
        )

        action = _strategy.select_action(ctx)

        if isinstance(action, DrawAction):
            # 动作契约（§3.5 要点 5 / ISSUE-006）：banner_id 优先；banner_id 为 None 时
            # 按 pool_id 反查唯一 Banner（旧单池兼容路径，多同名池时已由 Ph1a 强制双字段规避歧义）
            banner = banners.get(action.banner_id)
            pool = banner.active_pool
            batch_size = max(getattr(pool, 'batch_size', 1), 1)

            # ── 原子预检查：batch_size 发可负担性（与现状 L254-256 一致）──
            # REVIEW-R1-FIX: ISSUE-002：批次原子性与 mid-batch 成本剧变互斥——lifecycle 可在批次
            # 中途 switch_to 改变活跃池成本（旗舰 free_10pull 场景即触发），批次入口基于初池的
            # 预检查因此【不充分】。保留为优化；每抽对当前活跃池单独扣费检查（spend 返回 None
            # 即终止本批次剩余抽数，见下），保证不静默消耗预检查之外的资源。
            if not state.can_afford_batch(pool.cost, batch_size):
                continue

            # ── 批次逐发执行（batch 循环保留在 gacha_service，与现状 L259 一致）──
            for _ in range(batch_size):
                pool = banner.active_pool          # 每次重读活跃池（上一抽 lifecycle 可能已 switch_to）
                # ── 批次中途耗尽守卫（REVIEW-R1-FIX: ISSUE-302）──
                if banner.is_exhausted:
                    break                          # 本批次中途 active 池耗尽（pool.max_draws 非 batch_size
                                                   # 倍数，如 15/10 的第 15 抽在本抽后标记 exhausted）→
                                                   # 终止本批次剩余抽数——max_draws 硬上限不被批次惯性突破。
                                                   # free_10pull one_shot 判定在批次末（_pool_draws>=batch_size），
                                                   # pool_exhausted→switch_to 在下一批次入口生效，不触发此守卫
                spent = state.spend(pool.cost)     # 每抽对【当前活跃池】单独扣费——switch_to 后
                                                   # 新池成本以本抽为准，不可负担即返回 None
                                                   # 终止本批次剩余抽数（不扣预检查外资源）（ISSUE-002）
                if spent is None:
                    break                          # 防御性：与现状 L262-265 一致

                # ── one_shot / batch 语义约定（REVIEW-R1-FIX: ISSUE-002）──
                # one_shot = 「一次性批次」：该池执行一次 batch（batch_size 抽，默认 1）完成后才标记
                #   exhausted——批次中途【不】因 one_shot 耗尽而切换/终止，本批次抽满 batch_size 才
                #   耗尽，pool_exhausted → switch_to 在【下一次批次入口】生效。
                #   这使旗舰 free_10pull（batch_size=10 + one_shot=true）语义确定：一次 10 连消耗
                #   10 张 free_ticket 后切回 main，绝不中途改抽 main 的 orundum。
                # 其他 lifecycle 规则（pool_draws 阈值等）若批次中途 switch_to：剩余抽数按新池
                #   成本逐抽继续，不可负担即终止本批次（上面 per-draw 扣费检查兜底）。

                # Banner.draw：路由到活跃池 + P55 聚合/调整/还原 + 保底旁路 + after_draw，
                # 【不】评估 _check_transitions（单一触发点，ISSUE-001）
                # 返回 DrawOutcome（reward / pool_id 本次实际产出池 / pity_triggered / triggered_pity_name）
                out = banner.draw(state, _pity_engine, pity_state, pool)
                reward = out.reward
                draw_pool_id = out.pool_id          # 本次实际产出池的裸 id
                draw_pool_key = f"{banner.id}.{draw_pool_id}"   # 全限定统计键（REVIEW-R1-FIX: ISSUE-002）
                pity_triggered = out.pity_triggered
                triggered_pity_name = out.triggered_pity_name   # ISSUE-003：随 DrawOutcome 携带

                # ── 逐抽结算（与现状 L299-365 完全一致，此处仅列关键行）──
                #   stats.on_draw(reward.id, draw_pool_key, pity_triggered) / stats.pity_triggers
                #     —— stats/collector 键统一为全限定 {banner_id}.{pool_id}（ISSUE-002）
                #   rg = dict(reward.resources_gained or {})
                #   state.add_card(reward.id, path="draw", overflow_bands=..., initial_counts=...)  # P63 溢出
                #   resources 并入 rg；total_consumed / total_gained / combined_gained（紧凑模式）
                #   collector.on_draw(card_id=..., pool=..., pool_key=draw_pool_key, spent=...,
                #                     resources_gained=rg, pity_triggered=...,
                #                     triggered_pity_name=triggered_pity_name,   # ISSUE-003
                #                     pity_counter_max=..., ...)
                #     —— collector.on_draw 新增可选参数 pool_key（None 时回退 pool.id 保持旧契约）；
                #        非 None 时以 pool_key 记 pool_draw_counts/pool_card_counts/pool_pity_counts/
                #        draw_pool_ids（collector.py:62/101/112/114/116/120 现状读 pool.id，迁移为 pool_key）；
                #        InfoVectorCollector（collector.py:62）的 InfoVector.pool_id 同样取 pool_key——
                #        两模式键语义统一（全量历史不再裸 pool.id，ISSUE-006）

                # ── 单抽粒度 emit——batch 内每抽一次 ──
                # 事件契约（§3.5 唯一真相，ISSUE-005）：banner_id / pool_id=全限定键 / card_id / pity_triggered
                notifier.emit("after_draw",
                              banner_id=banner.id,
                              pool_id=draw_pool_key,
                              card_id=reward.id,
                              pity_triggered=pity_triggered,
                              state=state,
                              collector=collector)

            elif isinstance(action, NonDrawAction):
                # P56 定轨切换/取消（§3.5 要点 5 / ISSUE-006）——分支补全（现状 gacha_service.py:367-368）。
                # action.params['pool_id'] 为 {banner_id}.{pool_id} 全限定键（§3.11.3 命名空间统一）：
                # 1) 由 banners.get(params['banner_id']) 定位 Banner（params['banner_id'] 为 None 时反查）
                # 2) 经 banner.active_pool 定位池
                # 3) _apply_non_draw(..., pity_engine, pity_state) 内
                #    pity_engine.get_behaviors_for_pool(f"{banner_id}.{pool_id}") 定位 TargetedBehavior
                #    （epitomizable_cards 校验取 banner.active_pool.epitomizable_cards）
                self._apply_non_draw(action, banners, _pity_engine, pity_state)

            elif isinstance(action, WaitAction):
                # 等待分支与现状一致（real_time 推进 + resource_gain + on_wait）——不再按 pool_end_times
                # 触发 on_pool_end，改为 banner_end_times_sorted / on_banner_end（§3.5 要点 6 / ISSUE-003）
                ...

                # ── 等待期纯时间条件评估（REVIEW-R1-FIX: ISSUE-003）──
                # 等待周期是时间推进（非抽卡事件）——real_time 推进、资源结算后，对 active_banners 各
                #   Banner 调用一次 banner._check_transitions(real_time=state.real_time)：
                # · 仅纯时间条件（time_window：real_time(秒) >= at_value(秒)）可能在等待期由 False→True；
                #   card_obtained / pool_exhausted 是事件型、等待期无事件不触发；pool_draws / banner_draws
                #   等待期抽数不变不触发——评估安全，不会引入等待期之外的状态变化
                # · 若不评估：活跃池在 time_window 阈值前已不可抽（资源耗尽→策略 WaitAction）时，转换
                #   永远不触发、目标池永不可达（死锁至 max_iterations/停止条件）——与旧模型 current_pools
                #   每轮按 real_time 纯时间求值 is_available_at 的「随时间为真」语义不符（ISSUE-003）
                # · 与「单一触发点」（after_draw，ISSUE-001）不冲突：等待周期无抽卡、after_draw 不会触发，
                #   两触发点按动作类型互补（抽卡→after_draw；等待→本分支），每个动作周期至多评估一次、
                #   至多一次转换
```

**生命周期转换的时序（REVIEW-R1-FIX: ISSUE-001——单一触发点）**：Banner.draw 内部完成当抽的概率/保底结算并将实际产出池随返回结果携带（`draw_pool_id`），但**不评估 `_check_transitions`**。转换统一由逐抽结算后的 `notifier.emit("after_draw")` 触发——P61 以 priority=1 订阅该事件并调用 `banner._check_transitions()`（装配见下方「Notifier 装配位置」）——转换只影响**下一抽**，不污染本次 `after_draw` 的 `pool_id`。每抽至多触发一次转换，满足「每抽最多一次转换」语义。**等待期补充（REVIEW-R1-FIX: ISSUE-003）**：上述「每抽」指抽卡动作周期；**等待（WaitAction）周期**由 WaitAction 分支在 real_time 推进后对 `active_banners` 评估一次 `_check_transitions(real_time=...)`（见上方 WaitAction 伪代码注释）——仅 `time_window` 纯时间条件可能在等待期满足，保证「活跃池不可抽时目标池经 time_window 可达」与旧模型每轮纯时间求值语义一致；两触发点按动作类型互补，每个动作周期至多一次转换。

<!-- REVIEW-R1-FIX: ISSUE-301 -->
**Notifier 装配位置（REVIEW-R1-FIX: ISSUE-001，跨计划装配契约——ISSUE-301）**：`Notifier` 实例**不在 GachaService 内部创建**——由**装配层**统一创建并注入，保证与模拟循环 emit 的是同一实例：
- **创建点**：`batch_simulator._run_single`（batch_simulator.py:209，单/多进程构造 GachaService 的唯一入口）构造 GachaService 时创建 `notifier = Notifier()`，经 `GachaService.__init__` 新增可选参数 `notifier=None` 注入 `self._notifier`（为 None 时服务内 fallback 自建，仅供单测直构——批处理入口必须传共享实例）。
- **装配顺序（固定）**：① 装配层先调用 **P58 装配函数** `register_milestone_engine(notifier, engine)`（§5.4，P58 落地时提供）注册 `priority=0` 订阅 → ② 再构造 GachaService 注入同一 notifier → ③ GachaService 在 Ph2 注册 P61 `priority=1` 订阅。P58 不 import、不触碰 gacha_service（§5.2 契约成立的前提即此装配点），订阅经装配点回调落在与 emit 相同的实例上——解决「P58 拿不到 gacha_service 的 self._notifier」的集成缺口（旧写法订阅落在与 emit 无关的实例上，里程碑结算永不触发）。
P61 的转换处理器在 **Ph2** 的 gacha_service 装配处订阅：`self._notifier.subscribe("after_draw", self._on_banner_after_draw, priority=1)`——handler 形如 `def _on_banner_after_draw(self, banner_id, card_id, state, **kw): self._banners[banner_id]._check_transitions(card_id=card_id, real_time=state.real_time)`。**事件数据必须透传，不得用 `**kw` 丢弃（REVIEW-R1-FIX: ISSUE-001）**——`card_id`（本抽产出卡）与 `state.real_time`（当前模拟时间）是 `card_obtained` / `time_window` 两个一等生命周期条件的求值输入，Banner 内部无这两份数据（`draw()` 的 state 不落库）；否则 §3.6 新手池 `on = { card_obtained = "ssr_1" }` 提前关闭与 `on = { time_window = 21 }` 阶段切换在引擎层无法评估。**模拟循环只 emit 不 subscribe**——§5.2「gacha_service 不再需要改动」指 Ph0+Ph2 之后 P58 不再需要触碰 gacha_service，P61 的订阅装配本身落在 P61 自己的 Ph2 阶段；Notifier 创建与 P58 装配函数回调落在 P61 Ph0 的装配层（§3.12 Ph0 / §5.4 交付清单）。

### 3.6 TOML 配置

**标准卡池（向后兼容——不写 `[[banner]]` 时自动包装）：**

```toml
[[pool]]
id = "genshin_limited"
name = "角色活动祈愿"
cost = { intertwined = 1 }
# ... distribution ...
# → 自动包装为 Banner { id="genshin_limited", pools: { main: {...} } }
```

**新手池（max_draws 关闭）：**

```toml
[[banner]]
id = "genshin_beginner"
name = "新手祈愿"
max_draws = 20

[[banner.pool]]
id = "main"
cost = { acquaint = 1 }
batch_size = 10

[[banner.pool.reward]]
card_id = "noelle"
probability = 100.0
rarity = "sr"
featured = false
# ... 其余卡牌 ...

# max_draws = 20 已由引擎自动执行（每抽后 _total_draws >= 20 → 自动 exhaust，ISSUE-303）——
# 无需手写 [[banner.lifecycle]] banner_draws = 20 → exhaust_banner 的冗余规则（旧写法与此
# 自动执行并存会形成双路径；本示例以引擎自动执行为准，banner_draws 条件保留用于非 max_draws 场景）
```

> **状态更新（REVIEW-R1-FIX: ISSUE-001/306）**：`card_obtained`（card_id 精确匹配）与 `time_window` 两个条件已在引擎层可求值——本抽 `card_id` 与当前 `state.real_time` 经 §3.5 after_draw 订阅透传进 `_check_transitions`（签名见 §3.2）。终末地新手池「抽出任意 6★ 即关闭」所需的**稀有度匹配**（`match = "rarity"`，如 `rarity = "ssr"`）**列入 Ph1c 引擎交付项**（§3.12）：`_check_transitions` 在 `match='rarity'` 时经本抽产出卡的稀有度数据源判定——`Banner.draw` 返回的 `DrawOutcome.reward.extra_info['rarity']`（batch_simulator.py:521-524 现状注入，小写归一化）即数据源，无需新增配置/外部查询。**banner 模式的 rarity 数据源保留（REVIEW-R1-FIX: ISSUE-007）**：banner 模式 Pool 由 Ph6 从 `BannerPoolEntry.rewards`（dict，含 rarity 字段）构造，Ph6 必须从 `rewards[].rarity` 回填 `Reward.extra_info['rarity']`（小写归一化，等价 batch_simulator.py:521-524 现状注入）——否则 `extra_info['rarity']` KeyError 或恒空，`match='rarity'` 判定静默失效，与 Ph1c 交付项错位；Ph9 rarity 匹配用例须覆盖 banner 模式 Pool 路径。§3.10.5 已设计二级匹配控件（`card_id` / `rarity` 切换），交付口径与 §二 新手池关闭 [x] 勾选、§1.1 核心场景、§七 验收一致（ISSUE-306——原「rarity 待实施」措辞与覆盖勾选/验收错位，现统一为交付项）。

**终末地送抽插入 + 60抽档案：**

```toml
[[banner]]
id = "endfield_limited"
name = "终末地限定寻访"

[[banner.pool]]
id = "main"
cost = { orundum = 600 }
batch_size = 10

[[banner.pool.reward]]
card_id = "endfield_ssr_1"
probability = 0.6
rarity = "ssr"
featured = true
# ... 其余卡牌 ...

[[banner.pool]]
id = "free_10pull"
cost = { free_ticket = 1 }
batch_size = 10
one_shot = true
excludes_all_pity = true

[[banner.pool.reward]]
card_id = "endfield_ssr_1"
probability = 0.6
rarity = "ssr"
featured = true
# ... 奖励表（通常与 main 相同）...

[[banner.lifecycle]]
# main 抽满30次 → 切换到送抽池（main 自动停用）
on = { pool_draws = "main", at = 30 }
action = "switch_to"
target = "free_10pull"

[[banner.lifecycle]]
# 送抽耗尽 → 切回 main
on = { pool_exhausted = "free_10pull" }
action = "switch_to"
target = "main"

# ── P58 管辖（独立 [[milestone]] 段，不在 banner 内）──
[[milestone]]
banner = "endfield_limited"
at = 30
reward = { resource = "free_ticket", amount = 10 }

[[milestone]]
banner = "endfield_limited"
at = 60
reward = { resource = "next_banner_ticket", amount = 10 }
```

**Step-up 阶梯池：**

```toml
[[banner]]
id = "step_up"
name = "阶梯寻访"

[[banner.pool]]
id = "step1"
cost = { ticket = 1 }

[[banner.pool.reward]]
card_id = "ssr_1"
probability = 0.6
rarity = "ssr"
# ... 奖励表 ...

[[banner.pool]]
id = "step2"
cost = { ticket = 2 }
# rewards 同 step1（复制或共用编辑）

[[banner.pool.reward]]
card_id = "ssr_1"
probability = 0.6
rarity = "ssr"

[[banner.pool]]
id = "step3"
cost = { ticket = 3 }

[[banner.pool.reward]]
card_id = "ssr_1"
probability = 0.6
rarity = "ssr"

[[banner.lifecycle]]
on = { pool_draws = "step1", at = 10 }
action = "switch_to"
target = "step2"

[[banner.lifecycle]]
on = { pool_draws = "step2", at = 10 }
action = "switch_to"
target = "step3"
```

**完整字段参考（覆盖全部可选字段）：**

```toml
[[banner]]
id = "full_example"
name = "完整示例"
max_draws = 200                    # Banner 级总抽数硬上限（可省，0=无限制）——引擎自动执行，
                                   #   每抽后 _total_draws >= max_draws → 自动 exhaust（ISSUE-303）
available_from = 0.0               # 时间窗口起点（可省，模拟内相对天数——解析边界换算 *DAY 为秒，ISSUE-001）
available_until = 42.0             # 时间窗口终点（可省，同上——保存时 //DAY 换算回天数）

[[banner.pool]]
id = "main"
cost = { orundum = 600 }
batch_size = 10
max_draws = 100                    # Pool 级抽数上限（可省）
epitomizable_cards = ["ssr_1"]     # P56 定轨候选卡（可省）

[[banner.pool.reward]]
card_id = "ssr_1"
probability = 0.6
rarity = "ssr"
featured = true
resources_gained = { xp = 100 }    # 附带资源（可省）

[[banner.pool]]
id = "exchange_slot"
exchange_card_id = "ssr_2"         # 兑换快捷方式：自动生成 100% 单卡分布

[[banner.lifecycle]]
on = { time_window = 21 }          # 当前模拟时间 >= 21 天（阈值型；TOML 天数→解析时 *DAY=21*86400 秒，ISSUE-001）
action = "switch_to"
target = "free_10pull"

[[banner.lifecycle]]
on = { card_obtained = "ssr_1" }   # 获得指定卡 → 终结（card_id 匹配）
action = "exhaust_banner"

[[banner.lifecycle]]
on = { card_obtained = "ssr", match = "rarity" }   # 获得任意 SSR → 终结
action = "exhaust_banner"
```

### 3.7 策略层接口

策略通过 `StrategyContext.banners` 获取 Banner 列表，每个 Banner 暴露：

```python
# ── 可用性 ──
banner.is_available       # bool: 当前是否可以抽
banner.is_exhausted       # bool: 是否已永久关闭

# ── 当前状态 ──
banner.active_pool_id   # str: 当前活跃的 pool id（无 phase 概念——活跃池即阶段，见 §3.13.5）
banner.active_pool      # Pool: 当前活跃的 Pool 对象——成本/奖励/开关，策略决策必需（如 can_afford_batch(cost, batch)）

# ── 进度 ──
banner.total_draws        # int: 该 Banner 的总抽数（跨 pool 聚合）
banner.pool_draws       # Dict[str, int]: 每个 pool 的抽数（裸池 id 键——配额类策略（pool_quota）改读此，
                        #   不再用 ctx.pool_draw_counts（其键已全限定化 {banner_id}.{pool_id}，裸键查询恒 0，
                        #   ISSUE-002）

# ── 待处理转换（策略决策核心）──
banner.pending_transitions  # List[TransitionPreview]: 按 remaining 升序排列（-1 不可预估项排最后，ISSUE-305）
```

策略使用示例（SmartStrategy）：

```python
for banner in ctx.banners:
    for pt in banner.pending_transitions:
        # 送抽即将触发 → 垫刀（ISSUE-305：事件型 card_obtained/pool_exhausted 的 remaining=-1
        # 不可预估，须先守卫 pt.remaining >= 0——否则把事件型规则误判为「立刻可触发」而改判行为）
        if pt.remaining >= 0 and pt.remaining <= 5 and pt.switches_current:
            return DrawAction(banner_id=banner.id)   # pool_id 可省——默认 None 时服务层按 banner.active_pool
                                                     # 路由（§3.5 要点 5 / ISSUE-004）；显式双字段写法亦可

        # 送抽已激活（当前活跃池是送抽池）→ 优先消耗免费抽
        if banner.active_pool_id == "free_10pull":
            return DrawAction(banner_id=banner.id)   # pool_id 可省——默认 None 时服务层按 banner.active_pool
                                                     # 路由（§3.5 要点 5 / ISSUE-004）；显式双字段写法亦可

        # 离阈值远 → 不优先
        if pt.remaining > 20:
            continue
```

### 3.8 统计聚合

Banner 是统计的天然聚合边界：

```python
class BannerStats:
    banner_id: str
    total_draws: int              # 跨 pool 自动聚合
    total_cost: Dict[str, float]
    cards_obtained: Dict[str, int]
    pity_triggers: int            # 仅统计非 excludes_all_pity 的 pool
    pool_breakdown: Dict[str, PoolStats]  # 按需下钻
```

GDR 计算以 Banner 为单位——`banner_id` 替代 `pool_id` 作为统计维度。

**统计键命名空间（REVIEW-R1-FIX: ISSUE-002）**：`banner_id` 替代裸 `pool_id` 不只在 GDR 维度——**逐池统计键**（`pool_draw_counts` / `pool_card_counts` / `pool_pity_counts` / `draw_pool_ids` / `pool_types`）统一为全限定 `{banner_id}.{pool_id}`（与 §3.11.3 PityEngine 键空间、§3.9 `flattened_pools` 的 pool_id 一致）。`[[pool]]` 兼容模式退化为 `{旧pool_id}.main`（banner.id=旧 pool_id，内部池固定 'main'）——键格式变化，下游消费端同步迁移（见 §3.13.1 pool_types 键迁移清单）。`BannerStats.pool_breakdown` 同样以全限定键为下钻键。

**InfoVector.pool_id 同步全限定（REVIEW-R1-FIX: ISSUE-006）**：全量历史模式 `InfoVectorCollector.on_draw`（collector.py:62）的 `InfoVector.pool_id` 同步为全限定 `{banner_id}.{pool_id}`——`on_draw` 新增可选 `pool_key` 参数（None 时回退 `pool.id` 保持旧契约，与 CompactCollector 一致），`pool_id` 字段取 `pool_key`。否则同一模拟循环在紧凑（默认主流，全限定键）与全量历史（裸 id）两模式下 `draw_pool_ids` / `pool_card_counts` 键分裂，下游混用两模式结果（如 process_trace 消费紧凑全限定键、全量历史路径消费裸 id）时聚合错配。两模式键语义统一后无需消费端分支。

### 3.9 ConfigStore 数据模型

```python
# core/config_store.py —— 新增

@dataclass
class BannerPoolEntry:
    """Banner 内部池——从 TOML [[banner.pool]] 解析"""
    id: str                              # "main" | "free_10pull" | "step2"
    cost: str                            # TOML 字符串，如 "orundum:600"（必填）
    batch_size: int = 1                  # 每次抽取连数
    one_shot: bool = False
    excludes_all_pity: bool = False
    max_draws: Optional[int] = None
    exchange_card_id: Optional[str] = None                  # 兑换快捷方式（同旧 [[pool]]，写入后生成 100% 单卡分布）
    epitomizable_cards: List[str] = field(default_factory=list)  # P56 定轨候选卡
    rewards: List[dict] = field(default_factory=list)       # [[banner.pool.reward]] 解析——元素统一为 dict
                                                             # （card_id/probability/rarity/featured/resources_gained）；
                                                             # [[pool]] 自动包装经 §3.4 PoolDistEntry→dict 转换
                                                             # （REVIEW-R1-FIX: ISSUE-304），与 §3.13.1 dict 推导、
                                                             # featured 聚合、Ph6 Pool 构造兼容
    # output/random 不配置——从 rewards 推导（见 §3.13.1）


@dataclass
class LifecycleRuleEntry:
    """声明式转换规则——从 TOML [[banner.lifecycle]] 解析"""
    condition: str                       # "pool_draws" | "banner_draws"
                                         # | "card_obtained" | "pool_exhausted"
                                         # | "time_window"
    pool: Optional[str] = None           # 条件关联的 pool id（card_obtained 时为匹配目标）
    at: float = 0.0                      # 阈值（pool_draws/banner_draws 为整数抽数；time_window 为浮点【秒】——
                                         # TOML/UI 层以「模拟内相对天数」书写、解析边界 *DAY 换算为秒（ISSUE-001），
                                         # 与 Banner.available_from/until 精度一致——REVIEW-R1-FIX: ISSUE-009）
    match: str = "card_id"               # card_obtained 的匹配方式："card_id" | "rarity"
    action: str = "switch_to"            # "switch_to" | "exhaust_banner"
    target: Optional[str] = None         # 切换目标 pool id（action=switch_to 时必填）


@dataclass
class BannerEntry:
    """单个 Banner 定义——从 TOML [[banner]] 解析"""
    id: str
    name: str
    enabled: bool = True            # banner 模式 enabled 语义（REVIEW-R1-FIX: ISSUE-006）：
                                    # [[pool]] 自动包装时透传 PoolEntry.enabled；[[banner]] 默认 True。
                                    # §3.13.4 P62 可达判定 `enabled → available_from` 以此字段为准
    max_draws: Optional[int] = None
    available_from: Optional[float] = None
    available_until: Optional[float] = None
    pools: List[BannerPoolEntry] = field(default_factory=list)
    lifecycle: List[LifecycleRuleEntry] = field(default_factory=list)


@dataclass
class BannerConfig:
    """Banner 配置容器"""
    banners: List[BannerEntry] = field(default_factory=list)
```

`ConfigStore` 新增字段：

```python
banner: BannerConfig = field(default_factory=BannerConfig)
```

**`store.banner` 是运行时唯一数据源。** 旧 `store.pools`（`[[pool]]`）解析时经 `_wrap_pools_as_banners()` 立即包装为 `BannerEntry` 存入 `store.banner.banners`，不再作为运行时消费对象。`store.pools` 字段保留仅供旧代码读取兼容，P61 实施后逐步退役。

**`store.pools` 兼容视图（REVIEW-R1-FIX: ISSUE-007/010）**：`[[banner]]` 配置下 `store.pools` 不会被 `_wrap_pools_as_banners()` 填充（该函数只处理 `[[pool]]`）——若不做兼容，`store.pools` 为空的静默退化会让大量既有消费方拿到空列表而不报错：analysis_panel.py:177/1593/1619（extract_cost_per_draw_by_resource）、gacha_panel.py:283、main_window.py:276/387/431、resource_search_panel.py:276-278、worst_impact_panel.py:185、retreat_panel.py:217/271、cli.py:149、gdr.py:512。方案：`ConfigStore` 新增**只读扁平视图** `flattened_pools`（property：遍历 `store.banner.banners[*].pools[*]` 展平为 `PoolEntry` 列表，`pool_id` 取 `{banner_id}.{pool_id}`，cost/batch_size/rewards 透传；Banner 级 `available_from`/`available_until` 回填为 start_day/end_day）。`[[pool]]` 模式保持原语义。

**`store.pools` 读侧兜底机制（REVIEW-R1-FIX: ISSUE-006，消除『无需逐点改』三向矛盾）**：只读视图不能替 `store.pools` 字段本身取值——读 `store.pools` 的旧消费方拿到的仍是字段，banner 模式下为空列表（成本抽取/统计/模拟目标静默消失，正是要避免的退化）。⚠ 待人工裁决（DECISION-3，见 §6.1 裁决门控）：在「写侧 dual-write」与「消费方逐一改读 flattened_pools（点改清单入 Ph7/Ph8c）」两者间，本方案选**写侧 dual-write**（旧消费方零改动、与 ISSUE-010『store.pools 保持可变字段』相容）；默认选型已定（dual-write）；若倾向严格单一数据源，可改走点改清单。机制定为：Ph4 `_build_banners()` 解析完 `[[banner]]` 后，同步把 `flattened_pools` 的展平结果写回 `store.pools`（Legacy mirror，供旧字段读者拿非空数据）。`store.pools` 仍保持可变字段、不被属性化（见下条）；`flattened_pools` 是规范只读视图，新代码一律读它。写侧并存不互相覆盖（与下条 ISSUE-010 一致）：`config_toml.py:1107` 的 `[[pool]]` 解析 append 仅存在于 `[[pool]]` 模式（此时无 dual-write）；`config_panel.py:3879` 重绑 / `:3385/:3925` append 属旧「卡池配置」Tab 代码，随 Ph8 替换为「卡池管理」Tab 一并处理（写行为经 Ph8c 迁移清单确认）；解析期 dual-write 与编辑期写侧时序不重叠。保存侧按来源区分：`store.banner.banners` 非空 → 写 `[[banner]]`；为空 → 写 `[[pool]]`。§四『消费方零改动』以 dual-write 为成立前提。

**`store.pools` 保持可变字段，不属性化/只读化（REVIEW-R1-FIX: ISSUE-010）**：删去「或将 `pools` 属性化返回展平结果」的未定分支——`store.pools` 存在三处写侧，属性化/只读化会让全部写侧失效：`config_toml.py:1107`（`[[pool]]` 解析 append，Ph4 保留路径）、`config_panel.py:3879`（`store.pools = []` 整体重绑）、`config_panel.py:3385/:3925`（append）。**`flattened_pools` 是唯一的只读视图**；写侧永远写 `store.pools`，读侧经视图兜底。三处写侧列入 Ph4/Ph8c 迁移清单（保留写行为，仅确认与只读视图共存、不互相覆盖）。`_build_banners()`（Ph4）解析完 `[[banner]]` 后立即构建该视图。

**P62 可达过滤数据源（REVIEW-R1-FIX: ISSUE-009）**：`filter_target_specs_by_obtainable`（gdr.py:510-514）当前遍历 `store.pools` 构建 `pool_start[p.pool_id] = p.start_day`——banner 模式（`store.pools` 为空）会把所有目标卡判为不可达，4 个 `_obtainable` GDR 分母退化。改为遍历 `store.banner.banners`（`enabled` 判定 → `banner.available_from`）构建可达映射，与 §3.13.2 复刻时间线排序、§3.13.4 时间窗口上移共用同一数据源（Ph3 实施，文档同步表已登记说明）。

<!-- REVIEW-R2-FIX: AUDIT-BREAK-2 -->
<!-- REVIEW-R2-FIX: AUDIT-BREAK-4 -->
**保存侧双路径（REVIEW-R1-FIX: ISSUE-012）**：`save_toml()`（config_toml.py:89、_save_templates_and_pools :248-277）当前只从 `store.pools` 写 `[[pool]]`。P61 后：
- `store.banner.banners` 非空（含解析自 `[[banner]]` 或 `[[pool]]` 自动包装）→ 保存时写回 `[[banner]]`（含 `[[banner.pool]]` / `[[banner.lifecycle]]`），不再写 `[[pool]]`；
- `store.banner.banners` 为空（纯旧数据未加载 Banner）→ 保持现状只写 `[[pool]]`，**不写 `[[banner]]` 时现有 `[[pool]]` 行为完全不变**验收成立；
- 保存前先由 `flattened_pools` 快照，防止 `store.pools` 在 banner 模式已被清空时旧 `[[pool]]` 文件整体丢失；
- `pool_type` / `rerun_of` 解析残留排期 Ph4 清理：`PoolEntry.pool_type` / `rerun_of` 字段删除；`_build_pools`（config_toml.py:1032/1070-1071/1094/1102）、复刻复制（:1110-1115）、写出（:260-277）同步移除，旧 TOML 中这两个键解析时忽略（不报错）。**字段删除影响清单（读侧+写侧，ISSUE-007）**：`core/retreat_config.py:42-62`（`PoolEntry` 重建同时读 `p.pool_type`/`p.rerun_of` 并以之为关键字构造——Ph1a/Ph4 同步改不传）、`gui/config_panel.py:3241/4059`（读/写 pool_type）、`config_toml.py:1094`（写 pool_type）、**`gui/main_window.py:388`（`pool_type = pe.pool_type or (pe.bindings.get('type', '角色') ...)`——`pe.pool_type` 访问在 Ph4 删字段后 AttributeError，改为 `pe.bindings.get('type', '角色') if pe.bindings else '角色'`，AUDIT-BREAK-4）、`tests/core/test_batch_draw.py:24`（`PoolEntry(... pool_type='角色')` 关键字，Ph4 删字段后 TypeError，AUDIT-BREAK-4）、`tests/service/test_gacha_service.py:142`（`PoolEntry(... pool_type='角色')` 关键字，同 test_batch_draw.py:24，AUDIT-BREAK-2/4）**——随 Ph4 一并清理。

### 3.10 「卡池管理」Tab 设计

**替换**现有「卡池配置」Tab。与「保底机制」Tab 分工明确——Banner 管卡池结构和奖励，保底管概率修正规则。

核心理念：**Banner 是用户配置的一等单位**。每个 Banner 内含若干 Pool（自包含的抽取单元——cost/batch/rewards 全部内联）。Pool 之间通过 Lifecycle 规则自动切换。

#### 3.10.1 整体布局

```
┌─ 卡池管理 ────────────────────────────────────────────────────┐
│                                                                 │
│ ┌─ Banner列表 ──┐ ┌─ Banner详情 ───────────────────────────┐  │
│ │               │ │ 名称: [终末地限定寻访            ]       │  │
│ │ ✓ 终末地限定   │ │ ID:   [endfield_limited          ]     │  │
│ │   新手寻访     │ │ 最大抽数: [     ]                      │  │
│ │   标准寻访     │ │ 时间窗口: [0.0]~[21.0]                 │  │
│ │   阶梯寻访     │ │                                         │  │
│ │               │ │ ── [池] [生命周期] ──────────────────    │  │
│ │               │ │                                         │  │
│ │               │ │ ┌─ 上半：Pool 列表 ────────────────┐    │  │
│ │               │ │ │ID  │成本      │批│一│不          │    │  │
│ │               │ │ │main│orundum:..│10│☐│☐          │    │  │
│ │               │ │ │free│ticket:1  │10│☑│☑          │    │  │
│ │               │ │ └──────────────────────────────────┘    │  │
│ │               │ │      [添加] [移除选中]                    │  │
│ │               │ │ ─────────────────────────────────────    │  │
│ │               │ │ ┌─ 下半：选中池 rewards ─────────────┐   │  │
│ │ [添加] [移除]  │ │ │卡ID[▼]│概率%│稀有度│Feat│资源获取  │   │  │
│ │ [复制]         │ │ │endf_ssr│0.600│ SSR  │ ☑  │        │   │  │
│ │ [批量创建...]  │ │ │std_ssr │0.300│ SSR  │ ☐  │xp:100  │   │  │
│ │               │ │ └──────────────────────────────────┘    │  │
│ │               │ │  合计:100%  [添加] [移除选中] [缩放至100%] │  │
│ │               │ │       [从其他池导入...]                    │  │
│ │               │ │                                         │  │
│ │               │ │ （「生命周期」子标签页切换后↓↓）           │  │
│ │               │ │ ┌──────────────────────────────────┐    │  │
│ │               │ │ │关联池│条件      │阈值│动作    │目标│    │  │
│ │               │ │ │main  │pool_draws│30 │switch..│free│    │  │
│ │               │ │ │free  │pool_exh. │ — │switch..│main│    │  │
│ │               │ │ └──────────────────────────────────┘    │  │
│ │               │ │        [添加] [移除选中]                  │  │
│ └───────────────┘ └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.10.2 布局结构

- **左栏顶部**：`QLineEdit` 筛选框（匹配 Banner 名 / ID）——与「保底机制」Tab 的绑定池筛选一致，Banner 数量多时快速定位
- **左栏**（QListWidget，~180px）：Banner 列表，`currentRowChanged` 驱动右侧
- **右栏顶部**（QFormLayout，始终可见）：Banner 基础字段（4个）
- **右栏中部**（QTabWidget，**2个子标签页**）：池 / 生命周期
- **左栏底部**：`[添加] [移除] [复制] [批量创建...]`
- **[移除] 安全检查**：删除 Banner 前检查「保底机制」Tab 中是否有保底规则通过绑定池勾选了此 Banner 的 Pool，以及「累抽奖励」Tab 中是否有里程碑引用了此 Banner。若存在绑定关系，弹出确认对话框列出引用方，用户确认后自动解除绑定并删除
- **保存校验**：Banner `id` 全局唯一；Banner 内 Pool `id` 唯一；Pool `cost` 必填。违反时保存拦截并标红定位

#### 3.10.3 Banner 基础字段（QFormLayout，始终可见）

Banner 自身不抽卡——成本/批次/奖励都在 Pool 层级各自配置。

| 字段 | 控件 | 说明 |
|------|------|------|
| `name` | `QLineEdit` | 显示名称 |
| `id` | `QLineEdit` | 唯一标识符（可编辑——变更时级联更新生命周期/保底中的引用） |
| `max_draws` | `QSpinBox` | Banner 级硬上限，0=无限制——引擎自动执行（`_total_draws >= max_draws` → 自动 exhaust，无需手写 lifecycle，ISSUE-303） |
| `available_from` / `available_until` | `QDoubleSpinBox` | 模拟内相对天数（float）——UI/存储层为天数，保存/加载时经 `// DAY` / `* DAY` 与运行时秒值换算（ISSUE-001，Ph8 + Ph4 保存侧） |

#### 3.10.4 子标签页：「池」——上半 Pool 列表

5 列（删除了卡牌摘要列——奖励表在下半内联显示）：

| # | 列名 | 控件 | 说明 |
|---|------|------|------|
| 1 | ID | `QTableWidgetItem`（文本） | pool 标识符，内联编辑。变更时级联更新生命周期引用 |
| 2 | 成本 | `QLineEdit` 委托 | TOML 格式，如 `orundum:600`。必填 |
| 3 | 批次 | `QSpinBox` 委托 | 1–100，默认 1 |
| 4 | 一次性 | `QCheckBox` 委托 | `one_shot` |
| 5 | 不计保底 | `QCheckBox` 委托 | `excludes_all_pity` |

**交互细节**：
- 选中行变更 → 下半奖励表自动切换到该 Pool 的 rewards
- 按钮：`[添加] [移除选中]`

#### 3.10.5 子标签页：「池」——下半奖励表

内联编辑，5 列。卡ID 来自「卡牌定义」Tab 已注册的卡牌池——不可自由输入，必须从下拉列表选择。稀有度自动解析。

| # | 列名 | 控件 | 说明 |
|---|------|------|------|
| 1 | 卡ID | `QComboBox`（`setEditable(True)` + `QCompleter` 前缀搜索） | 下拉选项 = 已注册卡牌列表，显示格式 `card_id（名称）` 与卡牌定义 Tab 统一；新增行时为空，强制选择一张卡 |
| 2 | 概率(%) | `QDoubleSpinBox`（`setCellWidget`） | 0.000–100.000，3 位小数；`valueChanged` 实时更新合计 |
| 3 | 稀有度 | `QLabel`（只读，灰底） | 选中卡ID后从卡牌定义自动解析，不可编辑 |
| 4 | Featured | `QCheckBox`（`setCellWidget`） | 池子级属性，可编辑 |
| 5 | 资源获取 | `QLineEdit`（`setCellWidget`） | 格式 `res:amt,res:amt`；可为空 |

**交互细节**：

- **`[添加]`**：新增一行，卡ID为空。用户必须点击下拉列表选择一张已注册的卡。概率默认 0%
- **`[移除选中]`**：仅删除选中行——不自动缩放。概率合计暂时 <100%，由用户后续手动调整或缩放
- **`[缩放至100%]`**：将当前所有行按比例缩放至概率合计 100%。例：三行分别为 10/30/50（合计 90），点击后变为 11.11/33.33/55.56
- **无 `[+]` 快速注册**：注册新卡统一走「卡牌定义」Tab——降低实现成本，避免两处维护卡牌列表
- **无「默认3卡」**：不预设 SSR/SR/R 模板——每个池子独立配置
- 概率合计实时显示：绿色 = 99.9%–100.1%，红色 = 超标。保存时校验但不阻止

#### 3.10.5 子标签页：「生命周期」

QTableWidget 内联编辑，5 列：

| # | 列名 | 控件 | 说明 |
|---|------|------|------|
| 1 | 关联池 | `QComboBox` 委托 | 从当前 Banner 已有 Pool ID 列表动态填充——用户无法输入不存在的 Pool ID |
| 2 | 条件 | `QComboBox` 委托 | `pool_draws` / `banner_draws` / `card_obtained` / `pool_exhausted` / `time_window` |
| 3 | 阈值 | `QSpinBox` 委托 | `pool_draws`/`banner_draws` 为抽数；`time_window` 时切换为 `QDoubleSpinBox`（模拟内相对天数，保存/加载时 *DAY//DAY 与运行时秒换算，ISSUE-001）；`pool_exhausted`/`card_obtained` 时禁用（置灰） |
| 4 | 动作 | `QComboBox` 委托 | `switch_to` / `exhaust_banner` |
| 5 | 目标 | `QComboBox` 委托 | 从当前 Banner 已有 Pool ID 列表动态填充；动作为 `exhaust_banner` 时禁用 |

按钮：`[添加] [移除选中]`

**交互细节**：
- 「关联池」和「目标」的 QComboBox 选项实时取自当前 Banner 的 Pool ID 列表——添加/删除/重命名 Pool 后下拉自动同步，杜绝悬空引用
- 条件 = `time_window` 时，「关联池」禁用（置灰）——time_window 是 Banner 级时间条件（当前模拟时间(秒) >= 阈值(秒)，TOML 天数经 *DAY 换算，ISSUE-001），不关联特定 pool
- 当条件 = `card_obtained` 时，「阈值」列自动切换为二级匹配控件：
  - 左侧 `QComboBox`：匹配方式——`card_id`（指定卡牌）/ `rarity`（按稀有度），写入 `LifecycleRuleEntry.match`
  - 右侧：取值控件——`card_id` 模式为 QComboBox（已注册卡牌列表，`card_id（名称）` 格式）；`rarity` 模式为 QComboBox（SSR/SR/R，从「卡牌定义」Tab 已使用的稀有度动态填充）
  - 此设计用于终末地新手池「出任意 6★ 即关闭」——条件选 `card_obtained` → 匹配方式选 `rarity` → 取值选 `SSR`

#### 3.10.6 池子模板系统的去留

**移除「池子模板」表格。** 替代方案：

| 旧功能 | 新实现 |
|--------|--------|
| 模板表格定义奖励模式 | 创建 Banner → 在「池」子标签页配置第一个 Pool → 用「复制Banner」复制整个 Banner（含所有 Pool 的奖励表） |
| 「从模板批量添加」 | 「批量创建...」按钮——对话框：模板 Banner / 数量 / ID前缀 / 名称前缀 / 起始时间 / 间隔 → 批量生成 N 个 Banner，时间窗口自动偏移 |
| 复制奖励表 | 奖励表底部「从其他池导入...」按钮——选择已有 Banner 的 Pool 的 rewards 一键填入当前池 |

「批量创建」对话框：

```
┌─ 批量创建 Banner ───────────────────────────────┐
│                                                   │
│ 模板 Banner: [endfield_limited ▼]                  │
│ 数量: [8]    ID前缀: [banner_]   名称前缀: [角色池] │
│ 起始时间: [0.0]   间隔(天): [21.0]                  │
│                                                   │
│ 预览:                                              │
│ banner_1  角色池1  [0.0, 21.0]                     │
│ banner_2  角色池2  [21.0, 42.0]                    │
│ ...                                               │
│                                      [确定] [取消] │
└───────────────────────────────────────────────────┘
```

#### 3.10.7 现有方法适配

仿 P58 M7c 模式在三个方法中追加 Banner 数据流：

- **`apply_to_store()`**：遍历 `self._banner_defs` → `BannerEntry`（含 `BannerPoolEntry`/`LifecycleRuleEntry`）→ `store.banner.banners`
- **`set_config()`**：从 `store.banner.banners` 反序列化 → 回填 `self._banner_defs` + 刷新 Banner 列表
- **`get_config()`**：返回字典追加 `'banner': {...}` 键，供预览面板合成 Banner 摘要

**正向跨 Tab 数据流保留（REVIEW-R1-FIX: ISSUE-016）**：现有 `_sync_card_defs_from_pools()`（config_panel.py:3553-3612，池 rewards → 「卡牌定义」Tab 的 pools 字段）与 `_register_resources_from_pools()`（:3190，cost/资源获取 → 「资源管理」Tab 资源注册）当前从将被删除的 `pool_table` 行读取。P61 替换后这两个正向同步入口**改遍历 `store.banner.banners → pools[*]`**（经 §3.9 `flattened_pools` 视图读取，pool_id 用全限定键）；`_on_pool_cell_changed`（:3614-3626）的成本列资源注册同理改为 Banner Pool 编辑信号驱动。§3.10 替换「卡池配置」Tab 时**不得**牵连这两个方法——它们随 pool_table 删除后，「卡牌定义」的 pools 字段与资源注册将失去数据源（静默失效）。

### 3.11 「保底机制」Tab 增强

**保留**现有「保底机制」Tab 的整体结构（左保底列表 + 右 QFormLayout 动态详情）。BEHAVIOR_REGISTRY 驱动的动态表单体系继续工作。

**核心变更**：删除旧的 `pools` 手写 fnmatch 文本框——改用一个内联的「绑定池」勾选表格。用户不再需要手写 pattern，直接勾选 Banner.Pool 即可。TOML 存储仍用 `pools` fnmatch pattern（由 UI 自动生成/解析），引擎匹配逻辑不变。

#### 3.11.1 变更总览

> **事实验证（REVIEW-R1-FIX: ISSUE-015）**：config_panel.py 全文件无「生效范围 QGroupBox」「快速绑定 QDialog」控件（2026-08-01 grep 无匹配；QGroupBox 清单为池子模板/卡池配置/保底详情/deltas/捕获明光/抽卡策略/策略参数/目标卡/资源定义/资源获取规则/指定日期/日历预览/卡片详情/标签/多值标签/配置预览，均与这两项无关）。变更总览不再列出这两项——实际 UI 变更点仅为替换 `pity_pools_edit`（「适用池子」QLineEdit，config_panel.py:1010-1012）为绑定池勾选表格，工作量估算相应下调。

| 旧 | 新 | 说明 | 参见 |
|----|----|------|------|
| `pools` QLineEdit（手写 fnmatch，`pity_pools_edit`） | 「绑定池」QTableWidget（勾选表格） | 删除手写 pattern，直接勾选 | §3.11.2 |

#### 3.11.2 「绑定池」勾选表格

在保底详情 `QFormLayout` 底部——替代原来的「适用池子」文本框和「生效范围」面板。布局顺序保持「定义规则→配置参数→指定作用范围」的逻辑流：

```
┌─ 保底详情 ────────────────────────────────────────────┐
│ 名称: [ssr_soft         ]   类型: [soft_step ▼]       │
│ 稀有度: [ssr ▼]   目标: [☑ Featured]                  │
│                                                       │
│ ── 参数 ─────────────────────────────────────────     │
│ ... (BEHAVIOR_REGISTRY 动态参数：deltas / cr_probs)    │
│                                                       │
│ ── 绑定池 ───────────────────────────────────────     │
│ 筛选: [______________] 🔍     [全选] [全不选]         │
│ ┌──┬──────────────────┬──────┬──────────┬────────────┐│
│ │☑│ Banner            │ Pool     │ 说明        ││
│ ├──┼──────────────────┼──────┼──────────┼────────────┤│
│ │☑│ endfield_limited  │ main     │            ││
│ │☐│ endfield_limited  │ free     │不计保底,一次││
│ │☑│ standard_banner   │ main     │            ││
│ │☐│ step_up           │ step1    │            ││
│ │☐│ step_up           │ step2    │            ││
│ └──┴──────────────────┴──────┴──────────┴────────────┘│
└──────────────────────────────────────────────────────┘
```

| # | 列名 | 控件 | 说明 |
|---|------|------|------|
| 1 | ☑ | `QCheckBox`（`setCellWidget`） | 勾选 = 该保底规则绑定到此 Banner.Pool |
| 2 | Banner | `QTableWidgetItem`（只读） | Banner 名称 |
| 3 | Pool | `QTableWidgetItem`（只读） | Pool ID |
| 4 | 说明 | `QTableWidgetItem`（只读） | 合并显示标签：`excludes_all_pity` →「不计保底」/ `one_shot` →「一次性」；正常池留空 |

**交互细节**：
- 表格顶部有一行 `QLineEdit` 筛选器——输入关键词后表格仅显示匹配行（匹配 Banner 名 / Pool ID），方便 Banner 数量多时快速定位目标池
- 数据来源：遍历 `store.banner.banners` → 展开每个 Banner 的所有 Pool → 每行一个 `{banner_id}.{pool_id}`
- 「说明」列自动聚合 Pool 的特殊属性标签——用户无需逐列查看 `one_shot`/`excludes_all_pity`
- 加载时：读取 `pools` fnmatch pattern → 对每个 `{banner_id}.{pool_id}` 做三路匹配（全限定 / `banner_id` 段 / 裸 `pool_id` 段，REVIEW-R1-FIX: ISSUE-004）→ 任一命中即勾选对应行
- 保存时：从所有勾选行反向生成紧凑的 fnmatch pattern（共享前缀自动缩写为 `*`，精确 ID 用逗号分隔）→ 写回 `pools`
- 「全选」勾选所有行（生成 `*` = 匹配全部）；「全不选」取消所有勾选
- `excludes_all_pity=True` 的 Pool 仍然可以勾选（绑定是声明性的），但引擎不应用保底

#### 3.11.3 引擎匹配逻辑与池标识命名空间

TOML `pools` 字段仍存储 fnmatch pattern。引擎匹配流程不变——遍历所有 Banner 的所有 Pool，用 `{banner_id}.{pool_id}` 与 pattern 做 `fnmatch`。**兼容匹配规则（REVIEW-R1-FIX: ISSUE-004/005）**：对每个 `{banner_id}.{pool_id}` 键，除全限定 fnmatch 外，再分别对 `banner_id` 段与裸 `pool_id` 段各做一次 fnmatch——三路任一命中即绑定。这是必须的：fnmatch 是全串匹配，`fnmatch('genshin_limited.main', 'genshin_limited')` 为 False，不能只靠全限定匹配兑现旧裸池 id 模式的兼容；同时保留对裸 Pool ID 的匹配（向后兼容未迁移的 `[[pool]]`）。**三路匹配的实现面（ISSUE-005）**：不止 Ph8b UI「绑定池」加载，**运行期 `batch_simulator._build_pity_engine_from_gui`（batch_simulator.py:139-158）的 pool_specs 构建 fnmatch（:139-144 `any(fnmatch.fnmatch(pool.id, ptn) for ptn in pools_ptn)`）同样适用**——现状对裸 `pool.id` 匹配，兼容模式（`[[pool]]` 自动包装，键 `{旧pool_id}.main`）下旧 `PityDef.pools=["genshin_limited"]` 对全串 'genshin_limited.main' fnmatch 为 False、且无 banner_id 段拆分，保底规则在 **spec 构建期即不绑定**、soft pity 静默失效（直接违反「现有 `[[pool]]` 行为完全不变」验收）。Ph6 必须在该处实现三路匹配（拆 banner_id 段 / 裸 pool_id 段各做一次），Ph9 用『旧 `[[pool]]` + 旧 `pools`』用例锁定保底绑定等价。

<!-- REVIEW-R2-FIX: AUDIT-BREAK-3 -->
**池标识命名空间统一（REVIEW-R1-FIX: ISSUE-010）**：多 Banner 各含同名 `main` / `free_10pull` 时，裸 `pool.id` 无法作为 PityEngine 键（`pool_specs: Dict[str, PoolPitySpec]`，pity.py:1363-1364 按池 id 索引；gacha_service.py:270-276 get_spec/before_draw、L311 after_draw 均以裸 `pool.id` 传参——多 Banner 下直接撞 key、保底串池）。统一规则：
- **PityEngine 键空间与 fnmatch 全限定格式一致**：`{banner_id}.{pool_id}`（如 `endfield_limited.main`）
- `gacha_service` 在 `aggregate_probs_by_rarity`（下沉后的 core 层函数，ISSUE-004）/ `before_draw` / `after_draw` / `get_spec` 传参时用全限定键；`batch_simulator` 构建 `pool_specs` 时同用全限定键，且 `_build_pity_engine_from_gui` 的 pdef.pools fnmatch 匹配处实现三路兼容匹配（拆 banner_id 段 / 裸 pool_id 段各做一次，ISSUE-005 / Ph6）
- `[[pool]]` 单池包装模式下全限定键退化为 `{pool_id}.main`（banner.id = 旧 pool_id）——旧 `pools = ["genshin_limited"]` 经上述**三路兼容匹配**命中 `banner_id` 段（= 旧 pool_id）依旧匹配；旧 `pools = ["main"]` 命中裸 `pool_id` 段（REVIEW-R1-FIX: ISSUE-004，Ph8b 实现 + Ph9 测试锁定『旧 `[[pool]]` + 旧 `pools`』等价行为）
- **全限定键推导口径（REVIEW-R1-FIX: ISSUE-021/AUDIT-BREAK-3）**：全限定键 = `f"{banner.id}.{Banner.pools 字典键}"`（单池包装下字典键恒 'main'）——**pools 字典键是唯一口径，不是 `Pool.id` 属性**。构造桥 `Banner(id=p.id, pools={'main': p})` 里 `p.id` 仍为旧 pool id，若取 `pool.id` 会得 `{旧pid}.{旧pid}` 而非约定的 `{旧pid}.main`（AUDIT-BREAK-3 指出的键格式歧义）。`DrawOutcome.pool_id`、`active_pool_id`、`banner.pool_draws` 键、stats/collector/pool_types 键统一为此口径（§3.5 要点 11）
- **原子提交态 pool_specs 键全限定（REVIEW-R1-FIX: ISSUE-021/AUDIT-BREAK-3，阻塞 2）**：Ph2 查询键已全限定、而 `_build_pity_engine_from_gui` 的 pool_specs 键到 Ph6 才改——原子提交态 `get_spec('{旧pid}.main')` 查裸键引擎为 None、soft pity 静默失效。**pool_specs 键全限定 + fnmatch 三路匹配提前并入原子提交（随 Ph2/构造桥落地，见 §3.5 要点 12）**，Ph6 仅保留数据源改 store.banner 与多池展开
- §3.4/Ph1a 策略迁移的 `DrawAction` 因此强制双字段（`banner_id` + `pool_id`），服务层反查按全限定键定位（§3.5 要点 5 / ISSUE-006）
- `core/pity.py` 本身不改（`Dict[str, PoolPitySpec]` 无类型约束）——键命名空间由调用方（gacha_service / batch_simulator）统一，§四「不触及 core/pity.py」成立
- **命名空间超出 PityEngine（REVIEW-R1-FIX: ISSUE-002）**：同一 `{banner_id}.{pool_id}` 键空间同时用于 stats/collector/result_types 的逐池统计键（`pool_draw_counts` / `pool_card_counts` / `pool_pity_counts` / `draw_pool_ids` / `pool_types`），保证兼容模式（每个 `[[pool]]` 包装为含 'main' 内部池的 Banner）下多个 'main' 键在统计字典中不串池——否则跨 Banner 统计串池、保底重置归因（pool_card_counts/pool_pity_counts）与 GDR 分母错乱。详见 §3.8

### 3.12 实施阶段

| 阶段 | 内容 | 文件 | 预估 |
|------|------|------|:---:|
| Ph0 | `core/notifier.py` —— subscribe / emit / priority + **装配契约（REVIEW-R1-FIX: ISSUE-301）**：Notifier 由装配层（batch_simulator `_run_single` 构造 GachaService 处）创建并经新增构造参数注入 `GachaService.__init__`（`notifier=None` 时服务内 fallback 自建，批处理入口必须传共享实例）；装配层在构造服务**前**调用 **P58 装配函数** `register_milestone_engine(notifier, engine)` 注册 priority=0 订阅。**P61 + P58 共享基础设施**——Ph0 交付后两个计划可完全并行 | 新建 | ~30行+装配点 |
| Ph1 | `core/pool.py` —— 原地改造：加 one_shot/excludes_all_pity/max_draws，删 pool_type/is_rerun/original_pool_id/available_from/available_until（删除清单须对照现状 Pool 字段逐项核实，见下注），output/random/is_exchange 改推导 property + **新增模块级函数 `aggregate_probs_by_rarity` / `infer_rarity_from_spec`（下沉自 GachaService 方法，供 Banner.draw 与 gacha_service 共用，ISSUE-004）**。**与 Ph1a/Ph1b/Ph1c/Ph2/Ph5 同 commit 交付——最小可运行原子单元（REVIEW-R1-FIX: GATE-3，见下方「交付单元」注）**——避免字段已删而策略/构造点/gacha_service 消费点未迁移的中间态 TypeError/AttributeError（现状 gacha_service.py:211-214 `pool_end_times_sorted` / :224-226 `current_pools` 直接读 `p.available_until`/`p.available_from`，字段删除即必然崩溃） | 修改 | ~35行 |
| Ph1a <!-- REVIEW-R2-FIX: AUDIT-BREAK-1 --> | **策略迁移 + Pool 构造点迁移（新增，REVIEW-R1-FIX: ISSUE-001/008）** —— 8 个内置策略从 `pool.is_available_at`/`pool.available_until` 迁移到 `ctx.banners`（§3.4 迁移方案）并改 `DrawAction` 双字段（§3.5 要点 5）；**含 fixed_count / target_hunting（原「可不迁移」取消——current_pools 包装后元素 id 全为 'main'，target_hunting 的 `target_pool_ids` 匹配改 `banner_id`，REVIEW-R1-FIX: ISSUE-003）**；**另含 pool_quota / pity_reserve 两个裸 pool.id 消费点（ISSUE-002）**——pool_quota 的 `ctx.pool_draw_counts.get(pool.id)`（全限定化后恒 0、配额永不满足）改读 `banner.pool_draws`（§3.7）；pity_reserve 的 `ctx.get_pity_probabilities(pool.id)`（查不到全限定 spec、保底阈值退化基础概率）改传全限定键或经 StrategyContext 新增 banner 维度接口（Ph5）；`service/config_service.py:52-60`、`core/worst_impact.py:195-207`、`generator/schedule_generator.py:34-35` 的 `Pool(...)` 关键字构造改删字段后签名（时间窗口移 Banner 级、is_exchange 改 property、available_from/until 不再传）；**`service/config_service.py:25-58` 的 `export_pool_to_config` / `import_pool_from_config` 两个方法为死代码（REVIEW-R1-FIX: ISSUE-020/AUDIT-BREAK-1——全库 grep 无任何调用方，仅定义处命中）：`export_pool_to_config` 读 `p.available_from`/`p.available_until`（:36-37）、`import_pool_from_config` 以将删字段 `available_from`/`available_until`/`is_exchange` 为关键字构造 `Pool(...)`（:52-60），Ph1 删字段后两方法均必然 AttributeError/TypeError。处置：Ph1a **直接删除这两个方法**（死代码，无消费方，删后无影响面）；若保守保留类壳则删除方法体中的字段读写并标注废弃。AUDIT-BREAK-1 另注：Ph1 删字段后原子提交测试断裂属 GATE-3 已覆盖范围，本条仅补死代码清单**；**`service/batch_simulator.py` 的 `from_config_store`（:547-559）同属本清单但原计划漏列（REVIEW-R1-FIX: GATE-3_依赖顺序）——该处同样以将删字段为关键字构造 `Pool(...)`（`available_from=start_day*DAY` / `available_until=end_day*DAY` / `pool_type` / `is_exchange`），Ph1 删字段后首提交即 TypeError；Ph1a 一并删这四个关键字，时间窗口改由 PoolSchedule（:561-565）承载、`end_time` 计算（:568）不变，banner 模式数据源改造仍归 Ph6**；`core/retreat_config.py` 的 `PoolEntry` 重建**写侧**改不传 `pool_type`/`rerun_of`（retreat_config.py:50/54 现以已删字段为关键字构造——既 AttributeError 又 TypeError，ISSUE-007），读侧停止读 `PoolEntry.pool_type`——**与 Ph1 同 commit 交付（REVIEW-R1-FIX: GATE-3，见 §3.12 交付单元注）** | 修改 8 策略 + 6 文件 | ~95行 |
| Ph1b <!-- REVIEW-R2-FIX: AUDIT-BREAK-2 --> | `core/state.py` —— 删除 `GachaState.get_available_pools()`（REVIEW-R1-FIX: ISSUE-002；REVIEW-R1-FIX: GATE-3——方法体 `pool.is_available_at()` 随 Ph1 删字段即失效，必须与 Ph1 同 commit 交付），清理 `Pool` import 死依赖。**+ 同步删除 `tests/core/test_state.py::test_get_available_pools`（:73-82——构造 Pool 用将删 `available_from`/`available_until` 关键字 + 调已删方法，双断裂；REVIEW-R1-FIX: GATE-6_测试策略——删用例随本阶段并入原子单元，否则首提交后至 Ph9 前 pytest 必红，与 GATE-3『首提交后 pytest 全量通过』自相矛盾）+ 改写 `tests/service/test_gacha_service.py::test_env_builder_from_config_store_smoke`（:164 的 `env.pools[0].pool_type` 断言随 Ph1 删字段失效 → 改断言推导属性 `pool.output`/`pool.random` 或 §3.13.1 `derive_type`，REVIEW-R1-FIX: GATE-3_依赖顺序；**另 :142 的 `PoolEntry(... pool_type='角色')` 关键字——`PoolEntry.pool_type` 字段 Ph4 才删除，但同测试已在 Ph1b 改写范围，一并移除该关键字（At 阶段字段仍存在、移除无害），避免 Ph4 再断一次，AUDIT-BREAK-2/4**）** | 修改 | -13行 + 清理 |
| Ph1c | `core/banner.py` —— Banner + DrawOutcome + TransitionRule + TransitionPreview + Lifecycle 引擎（不含 Pool，直接引用 core/pool.py 的 Pool）+ **card_obtained rarity 匹配求值**（`match='rarity'` 经 `DrawOutcome.reward.extra_info['rarity']` 判定，ISSUE-306）| 新建 | ~225行 |
| Ph2 <!-- REVIEW-R2-FIX: AUDIT-BREAK-3 --> | `service/gacha_service.py` —— `current_pools` → `current_banners`（`Dict[str, Banner]`），banner 路由 + **保留逐抽结算管线**（spend/保底/统计/add_card/溢出/collector.on_draw，与现状 L259-365 一致）+ `after_draw` 单抽粒度 emit + **Notifier 装配**（`self._notifier` 创建 + P61 转换订阅 priority=1，ISSUE-001）+ **逐池统计键改全限定 `{banner_id}.{pool_id}`**（stats/collector/pool_types，ISSUE-002）+ **pool_specs 键全限定 + fnmatch 三路匹配（AUDIT-BREAK-3 阻塞 2，原子提交内必须与查询键同口径——`_build_pity_engine_from_gui`/`from_config_store` 的 pool_specs 键改 `{pool.id}.main` 并实现三路匹配，否则原子提交态 `get_spec('{旧pid}.main')` 查裸键引擎为 None、soft pity 静默失效；原 Ph6 的 ISSUE-005 部分前移到原子单元，见 §3.5 要点 12 / §3.11.3）**+ **collector.on_draw 传 `triggered_pity_name`**（取 DrawOutcome，ISSUE-003）+ **池结束快照机制迁移**（`pool_end_times_sorted`/`on_pool_end` → `banner_end_times_sorted`/`on_banner_end`，ISSUE-003）+ `pool_types` 数据源改造（ISSUE-004）+ NonDrawAction 全限定键分支（ISSUE-006）+ **WaitAction 分支等待期 `time_window` 评估**（real_time 推进后对 active_banners 调 `_check_transitions(real_time=...)`，REVIEW-R1-FIX: ISSUE-003）+ **`GachaService.__init__` 构造桥（REVIEW-R1-FIX: GATE-3_依赖顺序，契约见 §3.5 要点 10）——`pools` 双型收纳为运行时 Banner 字典 `self._banners`：元素为 `Pool` → 就地单池包装 `Banner(id=p.id, name=p.name, pools={'main': p})`（时间窗口 None 兜底）；元素为 `Banner` → 直接收纳 `{b.id: b}`——保证 `_run_single`（batch_simulator.py:228 传 `env.pools`）与现有测试直接构造 `GachaService([pool],...)` 后 `self._banners` 非空、`run_simulation` 可路由**——**与 Ph1/Ph1a/Ph1b/Ph1c/Ph5 同 commit 交付（REVIEW-R1-FIX: GATE-3，见 §3.12 交付单元注）**：本阶段无法独立落地——banner 路由需 Banner 类（Ph1c）、`build_strategy_context(banners=)` 需 Ph5、旧 `pool_end_times_sorted`/`current_pools` 字段读取在 Ph1 删字段后即崩、`self._banners` 需构造桥填补 | 修改 | ~120行变更 |
| Ph3 | `core/config_store.py` —— `BannerEntry` / `BannerPoolEntry` / `LifecycleRuleEntry` / `BannerConfig` dataclass + `ConfigStore` 新增 `banner` 字段 + `flattened_pools` 只读视图（ISSUE-007）| 修改 | ~80行 |
| Ph4 <!-- REVIEW-R2-FIX: AUDIT-BREAK-4 --> | `core/config_toml.py` —— `_build_banners()` 解析 `[[banner]]` + `[[banner.pool]]` + `[[banner.lifecycle]]` 段 + `_wrap_pools_as_banners()` 自动包装（完整透传 batch_size/exchange_card_id/epitomizable_cards + exchange 100% 展开 + **PoolDistEntry→dict 转换统一 rewards 元素类型**，ISSUE-304，见 §3.4）+ **保存侧双路径写回 `[[banner]]`**（ISSUE-012）+ **pool_type/rerun_of 解析/写出残留清理**（ISSUE-012，含 `PoolEntry.pool_type`/`rerun_of` 字段删除）+ **one_shot = 一次性批次 语义固化**（batch_size 抽完成后才耗尽，REVIEW-R1-FIX: ISSUE-002）+ **max_draws 非 batch_size 倍数批次中途耗尽语义固化**（耗尽标记在 draw 内、batch 循环 break 终止剩余，ISSUE-302）+ **Banner.max_draws 自动执行**（`_total_draws >= max_draws` → 自动 exhaust，新手池示例移除冗余 banner_draws 规则，ISSUE-303）| 修改 | ~125行 |
| Ph5 | `core/strategy.py` + `core/strategy_context_builder.py` —— `StrategyContext` 新增 `banners`/`all_banners` 字段（保留 `current_pools`/`all_pools` 向后兼容，`current_pools` 由 `active_banners[*].active_pool` 推导填充）；`build_strategy_context()` 新增 `banners`/`all_banners` 参数并透传（ISSUE-005）。**pity_reserve 若选 StrategyContext banner 维度 pity 概率接口方案（`get_pity_probabilities_for_banner(banner_id, pool_id)`，内部按全限定键查询 PityEngine），在此新增接口并透传（ISSUE-002，Ph1a 配合）**。与 P58 M4a 共用此函数签名，各自负责 `banners` / `_milestone_engine` 参数——**提前并入首提交（与 Ph1 同 commit 交付，REVIEW-R1-FIX: GATE-3，见 §3.12 交付单元注）**：`StrategyContext.banners` 字段与 `build_strategy_context` 的 `banners=` 参数是 Ph1a 策略迁移、Ph2 gacha_service 调用的前置依赖，必须随首提交落地，不可推迟到 Ph6 之后 | 修改 | ~16行 |
| Ph6 <!-- REVIEW-R2-FIX: AUDIT-BREAK-5 --> | `service/batch_simulator.py` —— `SimulationEnv` 新增 `banner_defs` 字段（**带默认值，保证跨进程 pickle 兼容**，ISSUE-011）+ `from_config_store` 改从 `store.banner` 解析（start_day/end_day → Banner.available_from/until **经 `* DAY` 换算为秒**，ISSUE-001；**`available_until=None` 永久池兜底：逐 Banner 有效结束时间 `eff_end = until if until is not None else from + 21 * DAY`、`end_time = max(eff_end)`，与现状 `(start_day + 21) * DAY` 秒等价**——REVIEW-R1-FIX: ISSUE-007/001；删除对 `pe.start_day/end_day/pool_type/exchange_card_id` 的依赖，ISSUE-011）+ **PoolPitySpec 在 banner 模式的 featured/ssr 来源 + 全限定键 `{banner_id}.{pool_id}`**（ISSUE-010/011）——`featured_ids` 由 banner 池 rewards 的 `featured=True` 标志聚合（`{r['card_id'] for r in rewards if r.get('featured')}`，替代 batch_simulator.py:517 的 `pe.featured_card_ids`，ISSUE-006）+ **Pool 构造时从 `rewards[].rarity` 回填 `Reward.extra_info['rarity']`（小写归一化，等价 batch_simulator.py:521-524 现状注入——`match='rarity'` 的 `_check_transitions` 唯一数据源，漏注入则 `extra_info['rarity']` KeyError 或恒空、新手池「出任意 6★ 即关闭」静默失效，ISSUE-007）** + **`_build_pity_engine_from_gui` 的 pool_specs fnmatch（batch_simulator.py:139-158）实现 §3.11.3 三路兼容匹配（对全限定键拆 banner_id 段/裸 pool_id 段各做一次）——兼容模式旧 `pools=["genshin_limited"]`（全串 `genshin_limited.main` fnmatch 为 False）不再在 spec 构建期失绑、soft pity 静默失效，ISSUE-005（**pool_specs 键全限定 + 三路匹配已前移至原子提交随 Ph2 落地，AUDIT-BREAK-3/§3.5 要点 12——Ph6 保留数据源改 store.banner + 多池展开，键自然承接，不重复实现**）** + TargetCard.pool_ids 标识规则（banner 级或全限定，ISSUE-011）+ PoolSchedule 时间源改 Banner 级 + **`env.pools` 运行时消费端迁移（AUDIT-BREAK-5——`SimulationEnv.pools` 改承载 `List[Banner]` 后，以下消费端对元素读裸 Pool 属性必然 AttributeError，原计划未纳入任何阶段）**：① `batch_simulator.py:676` 的 `all_drawable_ids = [r.id for p in pools for r, _ in p.rewards]`——改为遍历 banner 池展开（`b.pools[*].rewards` 或 `flattened_pools` 视图）；② `core/retreat_search.py:407-412` `_get_obtainable_card_ids`（`pool.is_exchange`/`pool.exchange_card_id`/`pool.rewards`）及同文件多处 `if not env.pools`/`for pool in env.pools`——改为按 banner 池展开读（`banner.pools.values()`）；③ `gui/resource_search_panel.py:61` `_extract_cost_per_draw(self._sim_env.pools)` 读 `p.cost`——改为 `banner.active_pool.cost` 或展平读取 | 修改 | ~85行 |
| Ph7 <!-- REVIEW-R2-FIX: AUDIT-BREAK-6 --> | 统计层适配 —— GDR / 过程分析 / 流式分析以 Banner 为聚合单位 + `CompactResult.pool_types` 由 output/random 推导填充（ISSUE-004）+ **逐池统计键/`pool_types` 键迁移到全限定 `{banner_id}.{pool_id}`**（gdr/process_trace/main_window/data_manager 消费端同步，ISSUE-002）+ `pool_end_resources`/`pool_end_pity_states` 消费端迁移到 banner_end（ISSUE-003，含 `core/vulnerability.py` 逐池分箱消费——REVIEW-R1-FIX: ISSUE-005，**含 `gui/gacha_panel.py:111` 的 `no_draw_results[0].get('pool_end_resources', {})`——字段改名后 `.get` 静默拿空 dict 无异常，须改 `.get('banner_end_resources', {})`，AUDIT-BREAK-6**）+ **可比性指纹/config_hash 纳入 Banner 级配置**（ISSUE-013）| 修改 | ~75行 |
| Ph8 | `gui/config_panel.py` ——「卡池管理」Tab：左Banner列表 + 右基础字段(4个) + 两子标签页（池/生命周期）+ PoolDistributionDialog 适配 BannerPoolEntry + **正向同步 `_sync_card_defs_from_pools`/`_register_resources_from_pools` 改读 banner 视图**（ISSUE-016）| 修改 | ~230行 |
| Ph8b | `gui/config_panel.py` ——「保底机制」Tab 增强：删除手写 `pools` 文本框 → 改为「绑定池」勾选表格（~60行；变更总览不含不存在的「生效范围 QGroupBox」「快速绑定 QDialog」，ISSUE-015）| 修改 | ~60行 |
| Ph8c | `gui/config_panel.py` —— `apply_to_store()`/`set_config()`/`get_config()` Banner 适配 + 移除池子模板 + `_setup_ui()` 注册 Tab + **`store.pools` 写侧确认**（:3879 重绑 / :3385/:3925 append 保持写可变字段，经 `flattened_pools` 只读视图兜底——ISSUE-010） | 修改 | ~55行 |
| Ph9 | `tests/test_banner.py` —— 覆盖 lifecycle 全部规则 + 送抽 + step + 新手池 + 向后兼容 + **策略迁移回归**（8 策略在 banner 模式跑通，ISSUE-001）+ **pool_quota / pity_reserve 在 banner 模式的等价回归**（配额判定与保底阈值不静默退化——`ctx.pool_draw_counts` 裸键、`get_pity_probabilities` 裸键全限定化后不再恒 0 / 回退基础概率，ISSUE-002）+ **时间窗口单位等价用例**（21 天开池在 `real_time >= 21*DAY` 秒时开放/关闭、`on_banner_end` 在第 21 天而非第 21 秒触发、`AllPoolsEndCondition` 秒判定，ISSUE-001）+ **无抽卡跨 time_window 用例**（等待分支触发 time_window 转换、目标池可达不死锁，ISSUE-003）+ **`_build_pity_engine_from_gui` 旧 `[[pool]]` + 旧 `pools` 保底绑定等价用例**（ISSUE-005）+ **card_obtained rarity 匹配用例**（终末地新手池「出任意 6★ 即关闭」——覆盖 banner 模式 Pool 经 Ph6 rarity 回填的路径，ISSUE-306/007）+ **max_draws 非 batch_size 倍数批次中途耗尽用例**（如 15/10，总抽数恒 15，ISSUE-302）+ **pending_transitions 事件型 remaining=-1 策略守卫用例**（ISSUE-305）| 新建/修改 | ~260行 |

> **实施前置自检（事实验证，Ph1 首步）**：对 `core/pool.py` 的 Pool dataclass 逐字段 diff 计划删除清单。当前（2026-08-01）Pool 字段为 `id/name/cost/rewards/available_from/available_until/is_exchange/is_rerun/original_pool_id/exchange_card_id/pool_type/batch_size/epitomizable_cards`——**无 `blocks_parent` 字段**（该字段来自 2026-06-20 已归档原方案，已修正删除清单）。动手前全局 grep 各待删字段的消费点，避免基于过时清单删错。同样，`config_toml.py` 实际位于 `core/` 目录（`config/` 目录仅含 `config.toml`），Ph4 路径以此为准。（REVIEW-R1-FIX: ISSUE-002）

<!-- REVIEW-R1-FIX: GATE-3 -->
<!-- REVIEW-R1-FIX: GATE-3_依赖顺序 -->
<!-- REVIEW-R1-FIX: GATE-6_测试策略 -->
<!-- REVIEW-R2-FIX: AUDIT-BREAK-7 -->
> **交付单元（原子 commit 边界，REVIEW-R1-FIX: GATE-3 / GATE-3_依赖顺序 / GATE-6_测试策略）**：计划的 **L1 阶段序无环**（Ph0→Ph1→Ph1a→Ph1b→Ph1c→Ph2→Ph3→Ph4→Ph5→Ph6→Ph7→Ph8/8b/8c→Ph9），但 **L2 输入/输出类型匹配**存在**多处同类中间态断裂**——最小可独立交付（一次 commit 落地、提交后系统整体可运行 + 现有 `pytest` 全量通过）的原子单元是 **{Ph1, Ph1a, Ph1b, Ph1c, Ph2, Ph5}**，而非原标注的 {Ph1, Ph1a}。断裂与随原子单元同 commit 的论证：
> 1. **Ph1 删除 `Pool.available_from`/`available_until` 后，gacha_service 立即断裂**：`gacha_service.py:211-214`（`pool_end_times_sorted`，读 `p.available_until`）与 `:224-226`（`current_pools` 推导，读 `p.available_from`/`p.available_until`）在 Ph2 完成迁移前 `run_simulation` 必然 AttributeError；`GachaState.get_available_pools()`（state.py:90，方法体 `pool.is_available_at()`）同源失效，须 Ph1b 同步删除。
> 2. **Ph1a 强制迁移 8 个策略到 `ctx.banners`，依赖 Ph5**：`StrategyContext.banners` 字段与 `build_strategy_context` 的 `banners=` 参数直到 Ph5 才落地——Ph1a 落地后至 Ph5 前策略层直接 AttributeError；Ph2 的 `build_strategy_context(banners=...)` 调用在 Ph5 前亦 TypeError。
> 3. **Ph2 依赖 Ph1c**：`run_simulation` 的 banner 路由（`banners.get(action.banner_id)` / `banner.draw(...)` / `banner.active_pool` / `banner.is_available`）全部消费 `core/banner.py` 的 `Banner` 类，无 Ph1c 则 Ph2 无对象可路由。
> 4. **GachaService 构造桥缺失（REVIEW-R1-FIX: GATE-3_依赖顺序）**：`_run_single`（batch_simulator.py:228）与现有 10 处测试直接构造 `GachaService([pool],...)`，计划此前未指定 `GachaService.__init__` 的 `pools → 运行时 Banner` 就地包装——§3.4 `_wrap_pools_as_banners` 只产出配置层 `BannerEntry`、`from_config_store` 直到 Ph6 才改读 `store.banner`，届时 `self._banners` 为空、`run_simulation` 无池可路由；且 `from_config_store`（batch_simulator.py:547-559）本身以将删字段为关键字构造 `Pool(...)`，Ph1 删字段后即 TypeError。随 Ph2 落地 `__init__` 双型构造桥（§3.5 要点 10）、随 Ph1a 迁移 `from_config_store` 构造点（§3.12 Ph1a）。
> 5. **test 删用例/断言时序矛盾（REVIEW-R1-FIX: GATE-6_测试策略）**：Ph1b（原子单元内）删 `get_available_pools` 方法，而 `tests/core/test_state.py::test_get_available_pools` 删用例原排 Ph9（单元外）——原子提交后至 Ph9 前该测试调已删方法 + 构造 Pool 用将删字段关键字，pytest 必红，与『首提交后 pytest 全量通过』自相矛盾；`test_env_builder_from_config_store_smoke`（test_gacha_service.py:164）断言 `env.pools[0].pool_type` 同样随 Ph1 删字段失效。两个测试改动随 Ph1b 并入原子单元。**既有测试破坏面不止此两项（REVIEW-R1-FIX: ISSUE-022/AUDIT-BREAK-7，完整清单见本注结论段）**——`test_pool.py`（直测退役的 `is_available_at`）、`test_gacha_service.py._make_pool`（:14-21）与 :68-69、`test_epitomizable_cards.py:189/202-205`、`test_pity_integration.py:97/150` 均以将删字段构造 `Pool(...)`、随 Ph1 断；`test_batch_draw.py:24` 与 `test_gacha_service.py:142` 以 `PoolEntry(pool_type=...)` 构造、随 Ph4 断——全部随原子单元/Ph4 排期，不得留在 Ph9 之后。
>
> **结论**：Ph1、Ph1a、Ph1b、Ph1c、Ph2、Ph5 **六阶段一次 commit 落地**（内部仍按表序实施、允许分步调试，但不得单独提交/发布中间态）；首提交后**现有 `pytest` 全量通过**——判据含 `test_state` 删用例与 `test_env_builder_from_config_store_smoke` 改写随原子单元同步落地、`GachaService` 构造桥使 `_run_single` 与直接构造的测试均有 `self._banners` 可用；**既有测试破坏面远大于上述两项（REVIEW-R1-FIX: ISSUE-022/AUDIT-BREAK-7）——以下既有测试以将删字段为关键字构造 `Pool(...)`/`PoolEntry(...)` 或直测将删 API，随 Ph1/Ph4 必断，须全部并入原子单元对应阶段，否则『首提交后 pytest 全量通过』不成立**：① `tests/core/test_pool.py:36-41`（`Pool(available_from=0, available_until=100)` + 直测已退役的 `pool.is_available_at()`，Ph1 删字段+退役方法即双断——用例删除或改断言推导属性）；② `tests/service/test_gacha_service.py:14-21` `_make_pool`（`available_from=0.0, available_until=...` 关键字，被 :32/51/78/101/121 等大量用例共用，Ph1 即断）与 :68-69（`test_initial_count_multiple_cards` 直接 `Pool(... available_from/available_until)`）；③ `tests/core/test_epitomizable_cards.py:189/202-205`（`Pool(pool_type='武器'/'角色', available_from=0, available_until=21)`）；④ `tests/core/test_pity_integration.py:97/150`（`Pool(pool_type='角色')`）；⑤ `tests/core/test_batch_draw.py:24` 与 `tests/service/test_gacha_service.py:142`（`PoolEntry(... pool_type='角色')`，随 Ph4 删 `PoolEntry.pool_type` 断——test_batch_draw 的该处随 Ph4 移除关键字，test_gacha_service 的随 Ph1b 一并移除，AUDIT-BREAK-2/4）。**注**：`tests/core/test_pity_config_toml.py:32/266` 的 `pool_type = "武器"` 是 TOML 配置字符串（旧键解析时忽略、不报错），无需改动；`tests/core/test_schedule.py:5-7` 测的是 `PoolSchedule.is_available_at`（非 `Pool`，PoolSchedule 保留），不受影响；`tests/core/test_process_analysis.py:26` 的 `pool_type='draw'` 是 `PoolEvent` 字段（非 `Pool.pool_type`），不受影响。；Ph9 `test_banner.py` 的 8 策略 banner 模式回归属**新增用例**、在 Ph9 交付，不构成首提交的通过判据。Ph3/Ph4/Ph6/Ph7/Ph8/8b/8c/Ph9 依序独立交付，各自保持可运行态。§六 风险表首行与 §5.3 实施顺序以本注为准。

<!-- REVIEW-R1-FIX: GATE-4 -->
> **实施前裁决门控（REVIEW-R1-FIX: GATE-4，清单见 §6.1）**：首提交落地前（Ph1 启动前）必须完成 **DECISION-1 / DECISION-2** 两项承重语义裁决（`one_shot` 语义、批次中途耗尽处置）；**DECISION-3** 在 Ph3/Ph4（`store.pools` 兜底机制落地）前、**DECISION-4** 在 Ph7（统计键/指纹迁移）前完成。计划已为每项写入**默认选型**（§6.1）——裁决输入 = 用户确认默认选型或改选备选；未裁决按默认选型实施，但默认与备选的语义差异已在 §6.1 逐项列出，**实施后改判将引发对应阶段返工**（影响面见 §6.1 表）。

### 3.13 类型与复刻：纯解析归约（设计决策记录）

本节记录一次设计归约（2026-08-01）：池子「类型」与「复刻」均不建模为 tag 或字符串字段，改为推导属性或纯解析推导。背景见 P61 走查讨论：运营命名不可靠，复刻本质是卡级时间出现。

#### 3.13.1 类型 → 推导属性（output / random，从 rewards 计算）

- 旧 `pool_type` 自由字符串（角色/武器/常驻/新手/混池/阶梯）**移除**，Banner 不再持有类型字段
- 机制本质由两个**可推导**维度描述（消耗维度已由 `cost` 字段承载，不重复）：
  - `output`：产出类型，`'card'`（抽卡）| `'resource'`（产出资源）
  - `random`：产出是否随机，`True`（概率抽取）| `False`（确定性兑换/固定产出）
- **两者都是推导 property，非配置字段，从 rewards 计算**：
  - `output = 'resource'` 当全部 reward.id 为 `_no_card`（资源池以 `_no_card` 占位行 + `resources_gained` 表达），否则 `'card'`
  - `random = bool(rewards) and (len(rewards) > 1 or rewards[0][1] < 1.0)`——**tuple 表示**（运行时 `Pool.rewards: List[Tuple[Reward, float]]`，pool.py:146，概率是元组第二元素，`Reward` 无 `.prob` 属性）；**dict 表示**（`BannerPoolEntry.rewards: List[dict]`，§3.9）时取 `rewards[0]['probability'] < 100.0`（概率%）。两种表示分别实现，避免照抄 `rewards[0].prob` 抛 AttributeError（REVIEW-R1-FIX: ISSUE-008）。概率已归一化；单卡 100% = 确定性；空 rewards 显式短路为 False，避免 `rewards[0]` 对空列表索引抛 IndexError（REVIEW-R1-FIX: ISSUE-010）
- 组合语义：
  - `output='card' and random=True` = 普通抽卡池
  - `output='card' and random=False` = 兑换池（100% 指定卡；`exchange_card_id` 快捷方式保留，写入后自动生成 100% 分布）
  - `output='resource'` = 资源池
- 角色/武器/常驻/新手/混池/阶梯全部是**运营命名**，不驱动任何分析逻辑（见消费点修正），不入字段，由 Banner 的 `name` 自然体现
- 消费点修正：
  - GDR 转化效率白名单（`_gdr_draw_conversion_efficiency`）由 `pool_type in ('角色','武器','')` 改为 `output == 'card' and random`。顺带修复「用户自定义类型被误排除」的 bug
  - 过程分析分类：`output == 'resource'` → resource；`output == 'card' and not random` → exchange；其余 → draw
  - **`CompactResult.pool_types` 数据管线（REVIEW-R1-FIX: ISSUE-004/002）**：`gacha_service.py:424` 的 `result.pool_types = {pid: p.pool_type ...}` 随 `pool_type` 字段退役必须改数据源——由推导属性填充 `{key: derive_type(pool)}`，`derive_type` 把 `output/random` 映射回旧三值（`output == 'resource'` → `'资源'`；`output == 'card' and not random` → `'兑换'`；其余 → `'角色'`）。**键格式改为全限定 `{banner_id}.{pool_id}`**（不再保持裸 pid——ISSUE-002；兼容模式退化为 `{旧pool_id}.main`）。**下游消费端键同步迁移**（值来源变推导 + 键格式变全限定，两处同时改）：
    - `core/gdr.py:457-471` 白名单：`pool_types` 键按调用方上下文（banner_id + pool_id）拼全限定键取，不再用裸 pool_id
    - `core/process_trace.py:103/149/194` 的 `pool_types.get(pool_id, '角色')`：`pool_id` 参数在 service 侧改为全限定键传入
    - `gui/main_window.py:386-389` 构建、`gui/data_manager_panel.py:397` 详情展示：遍历 `result.pool_types` 的键即为全限定键，展示时按需拆分 `banner_id` / `pool_id`
  - **兼容模式键格式影响 ⚠ 待人工裁决（DECISION-4，见 §6.1 裁决门控）**：`[[pool]]` 单池包装下全限定键为 `{旧pool_id}.main`，与旧数据集裸 `{pool_id}` 键不同——旧已保存 compact 结果的键需迁移映射，或由消费端兼容读取（与 Ph7 指纹/版本化一并处理，ISSUE-013）。默认选型：全限定键 + 消费端兼容读取（旧数据集经映射迁移，Ph7 一并处理）；保守替代方案：兼容模式（单池 Banner）下统计键保持裸 `{旧pool_id}`、仅 banner 模式用全限定键——代价是双键格式并存，需统一口径后由人工裁决
  - 若下游确需裸 `output/random`，另加 `result.pool_outputs` / `result.pool_randoms` 两个 dict 供精确消费（按需，非 P61 必做）
- 兼容：`is_exchange` 保留为 `output == 'card' and not random` 的 property，旧策略（`smart`/`pity_reserve`/`pool_quota`/`stop_on_target` 等）零改动
- 无 UI 入口需要：output/random 是推导值，用户不配置，统计层直接消费

#### 3.13.2 复刻 → 卡出现时间线（纯解析推导）

- 复刻不是独立概念/字段/tag。**唯一事实是每张 featured 卡的出现时间线**
- 推导规则：按时间窗口（`available_from`）排序所有 Banner 的 featured 卡出现事件（`Pool.rewards` 中 `featured=True`，等价 `featured_card_ids`）
  - 首元素 = debut（首发）
  - 后续元素 = 复刻
  - 相邻元素时差 = 复刻间隔（等歪 / A24 时间惩罚 / GDR 时间序列消费）
- 边界情况（双 up / 混合池）天然支持：复刻标记落在**卡**上，与池子整体是否「复刻池」无关
  - 单 up X 之后出现双 up X+Y：X 是时间线第二元素（复刻），Y 是首元素（debut）
  - 双 up X+Y 之后出现双 up X+Z：X 再次出现即复刻，与 Y/Z 完全无关
- 时间重叠（同一卡在两个时间窗口重叠的池都 featured）算两次出现（不同可获取窗口各算一次）
- `rerun_of`（整池复刻源）不再作为配置输入；「从其他池导入 rewards」按钮 = 内容继承的唯一机制（UI 复制分布），复刻标记由推导自动给出
- 旧死代码 `Pool.is_rerun` / `original_pool_id` 不迁移

#### 3.13.3 池子 tag 系统不建（YAGNI）

- 池子/Banner 级 tag 系统**不建**。类型已归约推导属性、复刻已归约推导，无真实消费点
- 卡片级 P65 tag（`tags`/`list_tags`）已落地，不受影响
- 未来若出现「按运营分类（角色/武器/常驻）分组分析」的真实需求，复用 P65 tags/list_tags 模式补充，届时再引入

#### 3.13.4 时间窗口统一到 Banner 级

- 可用性完全由 Banner 级 `available_from` / `available_until` + lifecycle 激活状态决定
- 旧 Pool 级 `available_from` / `available_until` **退役**（单活跃池模型下冗余，AND 语义无真实需求）
- `[[pool]]` 自动包装时，`start_day` / `end_day` 上移到 Banner（§3.4 `_wrap_pools_as_banners`）
- **永久 Banner（`available_until=None`）兜底（REVIEW-R1-FIX: ISSUE-007/001）**：`None` 语义 = 永久开放（运行时无结束窗口）。`from_config_store` 计算 `end_time` 采用**逐 Banner 有效结束时间**：`eff_end = b.available_until if b.available_until is not None else (b.available_from or 0) + 21 * DAY`，`end_time = max(eff_end for b in banners) if banners else 0`——单位为**秒**（ISSUE-001）：`+ 21 * DAY` 与现状 `(start_day + 21) * DAY`（batch_simulator.py:511-513 的 None end_day 兜底，banner.available_from 已是秒）逐池等价；end_time（秒）与 `banner_end_times_sorted` 的 `available_until`（秒）同单位，`AllPoolsEndCondition(end_time)` 以 `real_time(秒) >= end_time` 判定成立、资源收益日程按秒正确计算。期限与永久 Banner 混存时各自兜底、不会把永久池截断到其他池的窗口。`_wrap_pools_as_banners` 对 `e.end_day is None` 透传 None（§3.4），不再 `float(None)` 抛 TypeError
- 复刻时间线推导按各 Banner `available_from` 排序（§3.13.2 已一致）；复刻 = 新 Banner + 内容导入（「从其他池导入 rewards」按钮），不需要多 schedule 支持
- **P62 可达过滤对齐（REVIEW-R1-FIX: ISSUE-009/006）**：`filter_target_specs_by_obtainable`（gdr.py:510-514）当前遍历 `store.pools` 构建 `pool_start[p.pool_id] = p.start_day`。banner 模式改为遍历 `store.banner.banners`（`enabled` 判定 → `banner.available_from`——enabled 取 `BannerEntry.enabled` 字段，ISSUE-006），与 §3.13.2 复刻时间线排序、本节约时间窗口上移共用同一数据源——`store.pools` 为空时不再把目标卡整体误判为不可达（4 个 `_obtainable` GDR 分母退化）。`Banner.available_from` 成为可达判定、复刻排序、窗口判定的统一时间真相源

#### 3.13.5 phase 概念移除

- 统一 switch_to 模型下 `_phase` 冗余：`active_pool_id` 已表达当前阶段（送抽中断期 = 活跃池为 `free_10pull`）
- Banner 移除 `_phase` / `_phase_history` / `phase` property；`lifecycle` 平铺为 `List[TransitionRule]`，每轮边缘触发评估全部规则
- 策略用 `active_pool_id` 判断阶段（如 `active_pool_id == 'free_10pull'` 即送抽中断期）
- **单活跃池模型边界**：串行切换（阶梯/送抽）用单 Banner `switch_to`；并行自选（如原神角色池+武器池同时开）用多个独立 Banner，策略在 `active_banners` 间选择。单 Banner 内多池同时活跃且玩家自选不直接支持，建模为独立 Banner

## 四、波及范围

| 文件 | 变更性质 | 量级 |
|------|---------|:---:|
| `core/notifier.py` | **新建**（subscribe/emit/priority）+ **装配契约（REVIEW-R1-FIX: ISSUE-301）**：Notifier 由装配层创建并经新增构造参数注入 GachaService（`_run_single` 构造点，batch_simulator.py:209）；P58 经装配函数 `register_milestone_engine` 注册、订阅落在与 emit 相同的实例 | ~30行 |
| `core/banner.py` | **新建** | ~250行 |
| `core/config_store.py` | 新增 `BannerEntry` / `BannerPoolEntry` / `LifecycleRuleEntry` / `BannerConfig` + `ConfigStore.banner` 字段 + `flattened_pools` 兼容视图（ISSUE-007）| ~80行 |
| `core/pool.py` | **原地改造**：加 one_shot/excludes_all_pity/max_draws，删 pool_type/is_rerun/original_pool_id/available_from/available_until（无 blocks_parent 字段，见 §3.12 自检注），output/random/is_exchange 改推导 property + 模块级函数 `aggregate_probs_by_rarity`/`infer_rarity_from_spec`（ISSUE-004，供 Banner.draw 与 gacha_service 共用） | ~40行变更 |
| `core/state.py` | 删除 `GachaState.get_available_pools()`（ISSUE-002）——从「不触及」移入 | -1行 |
| `core/strategy.py` | `StrategyContext` 新增 `banners` + `all_banners` 字段 | +5行 |
| `core/strategy_context_builder.py` | `build_strategy_context()` 新增 `banners`/`all_banners` 参数并透传（ISSUE-005）——从「不触及」移入 | +6行 |
| `strategies/builtin/*.py`（8 个内置策略） | 从 `pool.is_available_at`/`pool.available_until` 迁移到 `ctx.banners` + `DrawAction` 双字段（ISSUE-001/006）——从「策略无需修改」移入**强制适配**（Ph1a）；含 fixed_count / target_hunting（原「可不迁移」取消——current_pools 元素 id 包装后全为 'main'，target_pool_ids 匹配改 banner_id，REVIEW-R1-FIX: ISSUE-003）；**含 pool_quota（`ctx.pool_draw_counts` 裸键→`banner.pool_draws`）/ pity_reserve（`get_pity_probabilities` 裸键→全限定或 banner 维度接口）两个消费点（ISSUE-002）** | ~95行变更 |
| `service/gacha_service.py` | `current_pools` → `current_banners` + Notifier 集成 + **Notifier 注入（新增 `notifier=` 构造参数，REVIEW-R1-FIX: ISSUE-301）** + 池结束快照迁移（ISSUE-003）+ `pool_types` 数据源改造（ISSUE-004）+ NonDrawAction 全限定键分支（ISSUE-006）+ **batch 循环耗尽守卫（ISSUE-302）** | ~105行变更 |
| `service/batch_simulator.py` <!-- REVIEW-R2-FIX: AUDIT-BREAK-5 --> | `SimulationEnv` 新增 `banner_defs`（带默认值）+ `from_config_store` 改读 `store.banner`（start_day/end_day *DAY 换算秒）+ 全限定 pity 键 + `_build_pity_engine_from_gui` 三路兼容匹配（ISSUE-005）+ **banner 模式 Pool 从 `rewards[].rarity` 回填 `extra_info['rarity']`**（ISSUE-007）+ TargetCard.pool_ids 规则（ISSUE-010/011）+ **Notifier 装配点（`_run_single` 创建+注入 GachaService、构造前回调 P58 装配函数，REVIEW-R1-FIX: ISSUE-301）** + **Ph1a 构造点迁移（`from_config_store` :547-559 删 `available_from`/`available_until`/`pool_type`/`is_exchange` 四个关键字，时间窗口改由 PoolSchedule 承载，REVIEW-R1-FIX: GATE-3_依赖顺序）** + **`all_drawable_ids` 构建（:676 读 `p.rewards`）改 banner 池展开（AUDIT-BREAK-5，Ph6）** | ~85行 |
| `service/config_service.py` <!-- REVIEW-R2-FIX: AUDIT-BREAK-1 --> | `Pool(...)` 关键字构造点迁移（ISSUE-008）+ **`export_pool_to_config`（:36-37 读 `p.available_from`/`p.available_until`）与 `import_pool_from_config`（:52-60 以将删字段构造 `Pool(...)`）两方法为死代码（无调用方，AUDIT-BREAK-1）——随 Ph1a 直接删除** | ~15行变更 |
| `core/config_toml.py` | `_build_banners()` + `_wrap_pools_as_banners()` + `[[banner]]` 解析 + 保存侧双路径写回 + pool_type/rerun_of 残留清理（ISSUE-012）| ~110行 |
| `core/worst_impact.py` | `Pool(...)` 关键字构造点迁移（ISSUE-008）| ~10行变更 |
| `generator/schedule_generator.py` | `PoolSchedule` 构造点迁移（ISSUE-008/011）| ~5行变更 |
| `core/retreat_config.py` | `PoolEntry` 重建写侧改不传 `pool_type`/`rerun_of`（retreat_config.py:50/54 现以已删字段为关键字构造，ISSUE-007）+ 读侧停止读 `pool_type`（ISSUE-008）| ~4行变更 |
| `core/collector.py` / `core/result_types.py` | `on_pool_end` → `on_banner_end` + `banner_end_resources`/`banner_end_pity_states` 字段（ISSUE-003）+ `on_draw` 新增可选 `pool_key` 参数（非 None 时以全限定键记 pool_draw_counts/pool_card_counts/pool_pity_counts/draw_pool_ids，ISSUE-002）+ **InfoVectorCollector 的 `InfoVector.pool_id` 同步取 `pool_key`**（collector.py:62，全量历史与紧凑两模式键语义统一，ISSUE-006）| ~35行变更 |
| `core/per_pool_analysis.py` | `pool_end_times` 累计快照消费端迁移到 banner_end（ISSUE-003）| ~10行变更 |
| `core/vulnerability.py` | `pool_end_resources`/`pool_end_pity_states` 消费迁移到 banner_end 语义（vulnerability.py:542-619/749-752 以裸 pool_id 逐池分箱——漏改则字段改名后静默拿到空 dict、脆弱性分析返回空结果，REVIEW-R1-FIX: ISSUE-005）| ~15行变更 |
| `core/gdr.py` | `compute_gdr_from_compact` 以 banner 聚合 + `pool_types` 消费（ISSUE-004）+ `filter_target_specs_by_obtainable` 改读 `store.banner`（ISSUE-009）| ~30行 |
| `core/process_trace.py` | `pool_types` 消费键对齐 + banner 聚合（ISSUE-004）| ~10行变更 |
| `core/retreat_search.py` <!-- REVIEW-R2-FIX: AUDIT-BREAK-5 --> | `env.pools` 运行时消费端迁移（AUDIT-BREAK-5，Ph6）——`_get_obtainable_card_ids`（:407-412 读 `pool.is_exchange`/`pool.exchange_card_id`/`pool.rewards`）及多处 `if not env.pools`/`for pool in env.pools` 改按 banner 池展开读 | ~12行变更 |
| `core/action.py` | `DrawAction` 新增 `banner_id` 字段 + `pool_id` 改 `Optional[str]`（默认 None，省略时服务层按 `banner.active_pool` 路由）（ISSUE-006/004）| +3行 |
| `gui/config_panel.py` | 「卡池管理」Tab：左列表右详情 + 两子标签页（池/生命周期）+ PoolDistributionDialog 适配 +「保底机制」Tab 增强（绑定池勾选表格替代手写pattern）+ `apply_to_store`/`set_config`/`get_config` 适配 + 移除池子模板 + 正向同步改读 banner 视图（ISSUE-016）+ Tab 注册 | ~380行 |
| `gui/main_window.py` / `gui/data_manager_panel.py` | `pool_types` 消费 + 可比性指纹 banner 维度（ISSUE-004/013）| ~20行变更 |
| `gui/analysis_panel.py` / `gacha_panel.py` / `resource_search_panel.py` / `worst_impact_panel.py` / `retreat_panel.py` / `cli.py` <!-- REVIEW-R2-FIX: AUDIT-BREAK-5 --> <!-- REVIEW-R2-FIX: AUDIT-BREAK-6 --> | `store.pools` 消费在 banner 模式经 Ph4 写侧 dual-write（Legacy mirror）保持非空，无需逐点改（ISSUE-007 / REVIEW-R1-FIX: ISSUE-006）；**两处例外（非 store.pools 消费，须随对应阶段迁移）——① `resource_search_panel.py:61` 消费 `env.pools`（运行时），Ph6 后元素为 `List[Banner]`、`p.cost` AttributeError（AUDIT-BREAK-5，Ph6）；② `gacha_panel.py:111` 读 `pool_end_resources` 键，Ph7 字段改名后 `.get` 静默空 dict（AUDIT-BREAK-6，Ph7）**| 0~（依赖 dual-write）+ ~6行 |
| `core/streaming.py` | 聚合提取器支持 banner 维度 | ~15行 |
| `tests/test_banner.py` | **新建**（含策略迁移回归，ISSUE-001）| ~200行 |
| `tests/core/test_state.py` <!-- REVIEW-R2-FIX: AUDIT-BREAK-7 --> | 删除 `test_get_available_pools`（随 Ph1b 并入原子单元，REVIEW-R1-FIX: GATE-6_测试策略，ISSUE-002）| -12行 |
| `tests/service/test_gacha_service.py` <!-- REVIEW-R2-FIX: AUDIT-BREAK-7 --> | 改写 `test_env_builder_from_config_store_smoke` 的 `pool_type` 断言 → 推导属性（随 Ph1b，REVIEW-R1-FIX: GATE-3_依赖顺序）+ **`_make_pool`（:14-21）与 `test_initial_count_multiple_cards`（:68-69）删 `available_from`/`available_until` 关键字（随 Ph1）；:142 `PoolEntry(pool_type='角色')` 移除关键字（随 Ph1b，AUDIT-BREAK-2/7）**| -3行 |
| `tests/core/test_pool.py` <!-- REVIEW-R2-FIX: AUDIT-BREAK-7 --> | `test_availability`（:36-41）以将删字段构造 `Pool` + 直测退役 `is_available_at`——删用例或改断言推导属性（随 Ph1/Ph1b）| -6行 |
| `tests/core/test_epitomizable_cards.py` <!-- REVIEW-R2-FIX: AUDIT-BREAK-7 --> | :189/202-205 的 `Pool(pool_type=..., available_from=0, available_until=21)` 关键字移除（随 Ph1）| -4行 |
| `tests/core/test_pity_integration.py` <!-- REVIEW-R2-FIX: AUDIT-BREAK-7 --> | :97/150 的 `Pool(pool_type='角色')` 关键字移除（随 Ph1）| -2行 |
| `tests/core/test_batch_draw.py` <!-- REVIEW-R2-FIX: AUDIT-BREAK-7 --> | :24 的 `PoolEntry(pool_type='角色')` 关键字移除（随 Ph4）| -1行 |

**不触及：** `core/pity.py`（引擎匹配逻辑与键命名空间除外——键空间由调用方统一为 `{banner_id}.{pool_id}`，见 §3.11.3，pity.py 文件本身不改）、`core/overflow.py`。`core/state.py` 仅删 `get_available_pools`（从「不触及」移入）。现有策略文件（`strategies/builtin/*.py`）**必须适配**（Ph1a 强制迁移，见 §3.4/§3.12）——「策略无需修改」验收取消。

**文档同步（REVIEW-R1 新增——原计划零登记）：** <!-- REVIEW-R1-FIX: ISSUE-011 -->

| 文档 | 同步项 |
|------|--------|
| `CLAUDE.md` | GDR 章节：`_gdr_draw_conversion_efficiency` 白名单由 `pool_type in ('角色','武器','')` 改为 `output == 'card' and random`（§3.13.1）；P62 可达过滤数据源说明随 `store.banner` 更新。GachaState 章节：`get_available_pools()` 方法已删除（state.py:90 消费点由 Banner 可用性取代，§3.4 / ISSUE-002）。Pool 章节：字段增删清单同步。扩展指南：新增「新 Banner 生命周期规则」入口 |
| `gacha_simulator/main.py` + `docs/01-活跃/subsystems/模拟服务层/01-理论.md`（技术栈.md） | Tab 名「卡池配置」→「卡池管理」（C1 doc-syncer 依赖 Tab 清单，同步 `_setup_ui()` 注册位置） |
| `docs/00-meta/模块状态矩阵.md` | P61 行状态实施后同步；P58 行仍为「📋 设计」，本计划不改变其状态 |
| `docs/01-活跃/.../05-笔记.md` | H4 自动维护，无需手动登记 |

## 五、与 P58 的关系

### 5.1 功能关系——互不依赖

P61 管理「哪些抽取源当前可用」（生命周期），P58 管理「抽到 N 次时额外送什么」（累抽奖励）。两者**功能上互不依赖**——P61 不关心 milestone 送了什么，P58 不关心 pool 之间如何切换。

但两者**共享同一个集成点**——`gacha_service.py` 模拟循环中「抽卡后」的位置：

```
gacha_service 模拟循环
    │
    ├─ pool.draw()
    ├─ pity_engine.after_draw()
    │
    └─ 【集成点】抽卡完成
        ├─ P61: 检查 lifecycle 转换条件
        └─ P58: 检查 milestone 触发条件
```

没有 Notifier 时，两个计划各自在 `gacha_service.py` 中插入自己的 inline 调用——这就制造了**隐式串行依赖**：不是因为功能需要对方先完成，而是因为修改同一行代码。

### 5.2 解耦方案——Ph0 = 公共平台

`core/notifier.py`（~30 行）是唯一的共享基础设施。它不属于 P61 也不属于 P58，由 P61 Ph0 交付：

```
Ph0: core/notifier.py + gacha_service 加一行 emit()
     （P61 负责实施，P58 声明依赖）
         │
         ├── P61 Ph1-9: Banner 全套
         │      订阅 "after_draw"（priority=1）→ banner._check_transitions(card_id, real_time)
         │      ——单一触发点（ISSUE-001）：Banner.draw 内部不评估转换，
         │        装配位置在 Ph2 的 gacha_service（见 §3.5「Notifier 装配位置」，
         │        handler 按事件 banner_id 反查 self._banners，并把事件中的 card_id 与
         │        state.real_time 透传给 _check_transitions——card_obtained / time_window
         │        两个一等条件的求值输入，REVIEW-R1-FIX: ISSUE-001）
         │
         └── P58 M1-8: Milestone 全套
                订阅 "after_draw"（priority=0）→ milestone_engine.after_draw()
                （里程碑结算以订阅函数形式落地——P58 当前尚未实施，
                  无现有 inline 代码可迁移，契约见 §5.4）
```

<!-- REVIEW-R1-FIX: ISSUE-301 -->
**Ph0 之后，P61 和 P58 完全并行**——各自只改自己的文件（`banner.py` / `milestone.py`），`gacha_service.py` 不再需要改动（「不再需要改动」指 Ph0+Ph2 之后——P61 的订阅装配落在 P61 自身 Ph2 阶段，P58 全程不触碰 gacha_service，见 §3.5 Notifier 装配位置）。**「P58 全程不触碰 gacha_service」成立的前提是 Notifier 装配点（ISSUE-301）**：Notifier 由装配层（batch_simulator `_run_single`）创建并注入 GachaService，P58 以装配函数 `register_milestone_engine(notifier, engine)` 在构造服务前注册——P58 的订阅与模拟循环 emit 落在同一实例，P58 无需也无法引用 gacha_service 内部 `self._notifier`（旧写法 `notifier.subscribe(...)` 未定义 notifier 变量来源，订阅将落在与 emit 无关的实例上）。

### 5.3 实施顺序

```
第一步：Ph0（core/notifier.py + gacha_service emit）—— ~30 行，半天
    │
    ├── P61 Ph1-9（Banner 全套）
    │       依赖：无。Ph0 交付后即可启。
    │       内部提交边界（REVIEW-R1-FIX: GATE-3，见 §3.12 交付单元注）：首提交 = {Ph1, Ph1a, Ph1b, Ph1c, Ph2, Ph5}
    │         一次落地（最小可运行原子单元——Ph1 删字段立即击穿 gacha_service 的 pool_end_times_sorted/current_pools
    │         与 GachaState.get_available_pools，Ph1a 依赖 StrategyContext.banners=Ph5、Ph2 依赖 Banner 类=Ph1c）；
    │         其后 Ph3/Ph4/Ph6/Ph7/Ph8/8b/8c/Ph9 各自独立交付
    │
    └── P58 M1-8（Milestone 全套）
            依赖：无。Ph0 交付后即可启。
```

**不提取独立 P 编号。** Notifier 太小（30 行），不值得单独成计划。P61 Ph0 交付，P58 的 M4 节声明 `depends: P61-Ph0` 即可。

### 5.4 P58 接入 Notifier 的改动

> **现状说明（2026-08-01 事实验证）**：截至本计划编制时，P58 尚未实施——全库 grep `milestone|_milestone_engine|MilestoneEngine` 仅命中 `core/state.py:115` 的一处文档注释（`path: "milestone_gift"`），`gacha_service.py` 全文件（442 行）中不存在任何 `_milestone_engine` inline 调用，模块状态矩阵中 P58 状态为「📋 设计」。因此本节描述的是**约定式接口契约**而非对现有代码的迁移——P58 落地时以本节契约为唯一集成依据。（REVIEW-R1-FIX: ISSUE-001）

P58 落地时，其里程碑结算逻辑（`_milestone_engine.after_draw(...)` + bonus 消费）应以订阅函数形式接入 Notifier，而非在 `gacha_service.py` 循环内插入 inline 调用：

<!-- REVIEW-R1-FIX: ISSUE-301 -->
```python
# P58 模块内 —— 订阅函数 + 装配函数（P58 落地时实施）
def _on_after_draw(banner_id, pool_id, card_id, pity_triggered, state, collector):
    if _milestone_engine:
        for entry in _milestone_engine.after_draw(banner_id, pool_id):   # 双参（§5.4 契约补充）
            # ... 消费 bonus（用 state/collector 更新资源）...

def register_milestone_engine(notifier, engine):
    """P61 Ph0 装配点回调（REVIEW-R1-FIX: ISSUE-301）——装配层在构造 GachaService 前调用。
    订阅落在与模拟循环 emit 相同的 Notifier 实例上（§3.5「Notifier 装配位置」）——
    P58 因此不 import、不触碰 gacha_service（§5.2 契约成立的前提即此装配点）。"""
    global _milestone_engine
    _milestone_engine = engine
    notifier.subscribe("after_draw", _on_after_draw, priority=0)

# 注册（P61 Ph0 交付后，由装配层在构造 GachaService 前调用）
#   from gacha_simulator.<p58模块> import register_milestone_engine
#   register_milestone_engine(notifier, _milestone_engine)

# gacha_service.py 中 —— P61 Ph0 交付的 emit 一行（契约见 §3.5——唯一真相，ISSUE-005）
#   pool_id 取本次实际产出的全限定键 {banner_id}.{pool_id}（draw_pool_key），
#   不读 banner.active_pool_id——active_pool_id 在 draw 内可能已因耗尽/转换改变（stale）
notifier.emit("after_draw",
              banner_id=banner.id, pool_id=draw_pool_key,
              card_id=reward.id, pity_triggered=triggered,
              state=state, collector=collector)
```

**P58 侧改动量预估：约 20 行**（订阅函数 + `register_milestone_engine` 装配函数 + 装配点注册一行）。此预估为契约假设，实际以 P58 实施为准——不承诺「原封不动迁移」或「逻辑完全不变」的工作量。P58 的 `MilestoneDef` / 计数器自管逻辑均不受影响：Notifier 是 P61 Ph0 提供的唯一集成依赖，P58 无需触碰 `gacha_service.py`（订阅经装配点回调落在同一实例，REVIEW-R1-FIX: ISSUE-301）。

**契约补充（REVIEW-R1-FIX: ISSUE-014，P61 计划内定稿，P58 落地以本节为准）：**
- **emit 与结算顺序**：§3.5 契约点 7——`after_draw` emit 位于逐抽结算（stats.on_draw / add_card / collector.on_draw / combined_gained）之后。P58 priority=0 注入的 milestone 资源进入 `state.resources`，但**不并入当抽** `combined_gained`/collector 记录（P63 单通道不可回溯）——里程碑资源注入语义为「下一抽起可用」。若 P58 需要当抽并入，须在 emit 前经 `collector`/`rg` 回调（超出本计划范围，P58 自行定夺）。
- **after_draw 订阅签名（banner 级过滤）**：订阅函数内 `_milestone_engine.after_draw(pool_id)` 单参不足——§5.5 `[[milestone]].banner` 过滤需要 banner_id。改传 `(banner_id, pool_id)` 双参，milestone 匹配以 `banner_id` 为准、`pool_id` 作为下钻信息；`pool_id` 为本次实际产出池的全限定键（§3.11.3）。
- **里程碑计数语义**：free_10pull / one_shot / 一次性池的抽数**计入** milestone 计数（「所有抽数无论出什么」无条件计数）；`excludes_all_pity` 仅旁路保底，不影响 milestone 抽数计数。

### 5.5 `[[milestone]].pools` → `[[milestone]].banner`

P58 的 `[[milestone]].pools` 字段用于过滤作用池子。Banner 模式后，milestone 应引用 `banner` 而非独立 `pool`：

```toml
# 旧写法（P58 当前）
[[milestone]]
pools = ["endfield_limited"]

# Banner 模式后——语义更准确
[[milestone]]
banner = "endfield_limited"       # 精确指向一个 Banner
```

此项改动属于 P58 范畴（`MilestoneDef.pools` → `banner`），不阻塞 P61。P58 可保留 `pools` 向后兼容，新增 `banner` 字段作为推荐用法。

## 六、风险

| 风险 | 缓解 |
|------|------|
| `current_pools` → `banners` 导致现有 8 种策略全部需要适配 | 策略迁移由 **Ph1a 强制完成**（与 Ph1/Ph1b/Ph1c/Ph2/Ph5 同 commit——首提交原子单元 {Ph1, Ph1a, Ph1b, Ph1c, Ph2, Ph5} 一次落地，REVIEW-R1-FIX: GATE-3，见 §3.12 交付单元注；避免中间态 AttributeError/TypeError）；`StrategyContext` 保留 `current_pools` 仅供兼容读（由 `active_banners[*].active_pool` 推导填充），策略层以 `banners` 为准。`current_pools` 元素在 `[[pool]]` 包装模式 `.id` 全为 `'main'`——fixed_count / target_hunting 因依赖裸 pool_id 匹配，一并纳入强制迁移（REVIEW-R1-FIX: ISSUE-001/003） |
| GachaService 构造桥：`_run_single`（batch_simulator.py:228）与现有测试直接构造 `GachaService([pool],...)`，Ph2 迁到 `self._banners` 后若构造链未就地包装运行时 Banner，`self._banners` 为空、run_simulation 无池可路由；`from_config_store`（:547-559）以将删字段关键字构造 `Pool(...)` 首提交即 TypeError（REVIEW-R1-FIX: GATE-3_依赖顺序） | `GachaService.__init__` 双型构造桥（§3.5 要点 10 / Ph2）——`List[Pool]` → 就地单池运行时 Banner 包装、`List[Banner]` → 直接收纳，任何阶段 `self._banners` 非空；`from_config_store` 删字段关键字随 Ph1a 迁移（时间窗口改由 PoolSchedule 承载，banner 数据源改造仍归 Ph6） |
| Banner 内部 pool 切换逻辑与 PityEngine 的交互复杂（送抽pool排除保底时，保底计数器跨pool是否继承） | Banner.draw() 内部显式分两路：`excludes_all_pity` 的 pool 完全旁路 `before_draw/after_draw`，不触碰 `pity_state`；正常 pool 走完整保底管线 |
| 生命周期规则遗漏边界条件（如送抽pool激活时主pool恰好也被时间窗口过期关闭） | 规则评估顺序：时间窗口（最先，直接 exhaust banner）→ 转换条件 → 可用性汇总。时间过期的 banner 不进入 `active_banners` |
| `[[banner]]` TOML 解析复杂度——pool / lifecycle 嵌套段与现有 `[[pool]]` 格式差异大 | `config_toml.py` 中检测到 `[[banner]]` 段时走新解析路径，`[[pool]]` 段保持现有解析路径不变。两者可共存于同一 TOML |
| 现有 `Pool` 对象缓存和共享引用（schedule_generator 等）与新 Banner 包装层的兼容 | `_wrap_pools_as_banners()` 包装而非替换——原始 Pool 对象保留在 `self._pools` dict 中，Banner 引用 Pool 而非复制 |
| 跨 Banner 依赖——如「Banner B 的某个 pool 需等待 Banner A 的 pool 耗尽后才开放」，当前 lifecycle 规则仅在单个 Banner 内部生效 | **已知限制，MVP 不覆盖。** 跨 Banner 事件可通过 Notifier 在后续版本支持——Banner 发射 `pool_exhausted` / `banner_exhausted` 事件，其他 Banner 订阅并据此切换活跃池。当前可用 TOML `available_from` 时间窗口近似模拟 |
| `card_obtained`（card_id 匹配）与 `time_window` 条件需要本抽 `card_id` / 模拟 `real_time`——Banner 内部无法获取 | 事件数据经 §3.5 after_draw 订阅透传：handler 把 `card_id` 与 `state.real_time` 传入 `_check_transitions(card_id, real_time)`（§3.2 签名 / §3.5 装配）——`card_obtained` card_id 匹配与 `time_window` 在引擎层已可求值（REVIEW-R1-FIX: ISSUE-001） |
| 等待期不评估 `time_window`：活跃池在 time_window 阈值前已不可抽（资源耗尽→策略 WaitAction）时，转换永不触发、目标池永不可达（死锁至 max_iterations/停止条件）；即使有抽卡，转换也延迟到阈值后首次抽卡才执行，与旧模型每轮按 real_time 纯时间求值 `is_available_at` 的「随时间为真」语义存在时隙差异（ISSUE-003） | WaitAction 分支在 real_time 推进、资源结算后对 `active_banners` 评估一次 `_check_transitions(real_time=...)`——仅 `time_window` 纯时间条件在等待期可满足（事件型/抽数型等待期不触发），与 after_draw 单一触发点按动作类型互补、每个动作周期至多一次转换（§3.5 WaitAction 分支 / ISSUE-003，Ph2）；Ph9 有「无抽卡跨 time_window」用例锁定目标池可达 |
| `card_obtained` 的 `rarity` 稀有度匹配（终末地新手池「出任意 6★ 即关闭」） | UI 已设计二级匹配控件（§3.10.5）；`rarity` 模式**列入 Ph1c 引擎交付**（REVIEW-R1-FIX: ISSUE-306）——`_check_transitions` 经 `DrawOutcome.reward.extra_info['rarity']`（batch_simulator 注入）判定，card_id / rarity 两模式均交付；Ph9 有对应用例锁定。**banner 模式数据源由 Ph6 从 `rewards[].rarity` 回填 `extra_info['rarity']`**（漏注入则 KeyError/恒空、静默失效，REVIEW-R1-FIX: ISSUE-007） |
| P55 槽位概率聚合（featured/standard + scale_factors 还原）从 gacha_service 迁入 Banner.draw，若遗漏则送抽/step 池保底概率行为退化 | Banner.draw 显式执行「聚合-调整-还原」三段（§3.5 契约）；聚合函数下沉为 core/pool.py 模块级函数，core 层与 service 层共用（ISSUE-004）；验收含 AUDIT-BREAK-8 回归（featured 卡保底概率与现状一致）（REVIEW-R1-FIX: ISSUE-005） |
| batch_size>1 池的 after_draw 粒度不明确——P58「每抽计数」与 collector 逐抽记录可能少计 | after_draw 按单抽粒度发射（batch 内每抽 emit 一次），batch 循环保留在 gacha_service（§3.5）（REVIEW-R1-FIX: ISSUE-004） |
| 批次原子预检查基于初池成本，lifecycle 批次中途 switch_to 改变活跃池成本（旗舰 free_10pull 第 1 抽即切回 main）→ 预检查与实际消耗不一致，仅持 free_ticket 时第 2 抽 spend 返回 None、免费十连实际只出 1 抽 | 批次内每抽对当前活跃池单独 afford 检查（spend 返回 None 即终止本批次剩余抽数）；one_shot 定义为「一次性批次」——批次中途不因 one_shot 耗尽切换，pool_exhausted → switch_to 落在批次边界（§3.5 / REVIEW-R1-FIX: ISSUE-002，Ph2 + Ph4） |
| `_wrap_pools_as_banners()` 未透传抽取语义，旧 `[[pool]]` 行为退化 | 完整透传 batch_size/exchange_card_id/epitomizable_cards/enabled/featured 标志 + exchange_card_id 展开为 100% 单卡分布 + 包装前过滤 enabled=False 池 + 包装在 rerun_of/featured 填充后执行（§3.4，ISSUE-006）；验收含 exchange/batch_size≠1/定轨/禁用池旧行为等价测试（REVIEW-R1-FIX: ISSUE-007） |
| 活跃池耗尽且无 lifecycle 接管（单池 Banner 只配一个池）时 draw() 行为未定义 | 兜底语义：Banner 自动 exhaust（§3.2）——`is_available=False`、`is_exhausted=True`；空 rewards 推导 random 显式短路为 False（§3.13.1），避免 IndexError（REVIEW-R1-FIX: ISSUE-010） |
| `Pool.available_until` 退役后 `pool_end_times_sorted`/`on_pool_end` 数据链断裂（P62 可达过滤 / per-pool 快照 / 脆弱性分析运行时数据源） | 迁移为 `banner_end_times_sorted`/`on_banner_end`，`CompactResult` 写 `banner_end_resources`/`banner_end_pity_states`；消费端含 `core/vulnerability.py`（逐池分箱，漏改则静默空结果）（§3.5 要点 6 / ISSUE-003 / REVIEW-R1-FIX: ISSUE-005，Ph2 + Ph7） |
| 永久 Banner（`available_until=None`）在 `from_config_store` 的 `end_time = max(available_until ...)` 计算遇 None 抛 TypeError，或 end_time=0 使结束条件/资源收益日程全部退化 | `available_until=None` 兜底：逐 Banner 有效结束时间 `eff_end = until if until is not None else from + 21 * DAY`、`end_time = max(eff_end)`（单位秒，与现状 `(start_day + 21) * DAY` 语义逐池等价，ISSUE-001）；`_wrap_pools_as_banners` 对 None end_day 透传 None 而非 `float(None)`（§3.13.4 / §3.4 / REVIEW-R1-FIX: ISSUE-007/001，Ph4 + Ph6） |
| `result.pool_types` 生成点读将删的 `Pool.pool_type`（gdr/process_trace/main_window/data_manager 消费） | 由 output/random 推导填充（`derive_type` 映射回旧三值）+ 键格式改全限定 `{banner_id}.{pool_id}`，下游消费端同步迁移键（§3.13.1 / ISSUE-004/002，Ph2 + Ph7） |
| DrawAction 无 `banner_id` 字段 + 主循环缺 NonDrawAction 分支（定轨 P56 在 banner 模型下断裂） | `DrawAction` 新增 `banner_id`；NonDrawAction 的 `pool_id` 定位改全限定键 `{banner_id}.{pool_id}`（§3.5 要点 5 / ISSUE-006，Ph2） |
| `store.pools` 在 banner 配置下为空 → 成本抽取/统计/模拟目标静默消失 | Ph4 `_build_banners()` 写侧 dual-write：把 `flattened_pools` 展平结果写回 `store.pools`（Legacy mirror），旧字段读者拿非空数据；`flattened_pools` 为规范只读视图（§3.9 / ISSUE-007 / REVIEW-R1-FIX: ISSUE-006，Ph3 + Ph4）——消费方零改动 |
| `Pool(...)` 关键字构造调用方（config_service/worst_impact/schedule_generator/retreat_config）在删字段后 TypeError | Ph1a 构造点迁移：删字段参数、时间窗口移 Banner 级、is_exchange 改 property、停止读 pool_type；retreat_config 的 `PoolEntry` 重建同时改不传 pool_type/rerun_of（写侧，ISSUE-007/008） |
| 多 Banner 各含同名 `main` 时 PityEngine 裸 `pool.id` 键冲突、保底串池 | 全限定键 `{banner_id}.{pool_id}` 统一键空间（§3.11.3 / ISSUE-010，Ph2/Ph6） |
| 旧 `PityDef.pools` 裸池 id fnmatch 模式（`pools = ["genshin_limited"]`）在 `[[pool]]` 包装模式（键 `genshin_limited.main`）下失绑——fnmatch 全串匹配命中不了 `banner_id` 段，保底规则静默不作用于该池 | 三路兼容匹配：全限定 / `banner_id` 段 / 裸 `pool_id` 段任一命中即绑定；Ph9 用『旧 `[[pool]]` + 旧 `pools`』用例锁定等价行为（§3.11.3 / REVIEW-R1-FIX: ISSUE-004，Ph8b） |
| 保存侧只写 `[[pool]]`，banner 配置无法 round-trip；pool_type/rerun_of 解析残留 | 保存侧双路径写回 `[[banner]]` + pool_type/rerun_of 残留清理（§3.9 / ISSUE-012，Ph4） |
| 可比性指纹/config_hash 不含 Banner 配置 → 仅 Banner 不同的数据集被判「配置相同」 | Ph7 指纹适配：pool_ids 指纹改 banner 维度、config_hash 纳入 Banner 级配置（ISSUE-013） |
| 原子提交态（Ph2 落地、Ph6 未落地）pity 键不一致：gacha_service 以全限定 `{旧pid}.main` 查询、`_build_pity_engine_from_gui` 的 pool_specs 键仍为裸 `pool.id` → `get_spec` 为 None、soft pity 静默失效（AUDIT-BREAK-3） | **pool_specs 键全限定 + fnmatch 三路匹配提前并入原子提交（随 Ph2，§3.5 要点 12）**——原子提交态键为 `{pool.id}.main`、与查询键同口径；Ph6 数据源切换后键自然承接 |
| 全限定键推导口径歧义：构造桥 `Banner(id=p.id, pools={'main': p})` 中 `p.id` ≠ 'main'，取 `pool.id` 得 `{旧pid}.{旧pid}` 而非约定 `{旧pid}.main`（AUDIT-BREAK-3） | 全限定键一律由 `f"{banner.id}.{Banner.pools 字典键}"` 推导（§3.5 要点 11）——`DrawOutcome.pool_id`/`active_pool_id`/`banner.pool_draws` 键统一为 pools 字典键 |
| `SimulationEnv.pools` 改承载 `List[Banner]` 后，`retreat_search.py:407-412`（`pool.is_exchange`/`pool.rewards`）、`resource_search_panel.py:61`（`p.cost`）、`batch_simulator.py:676`（`all_drawable_ids` 读 `p.rewards`）直接 AttributeError（AUDIT-BREAK-5，mapping item 10 gaps 2/3/4/5） | Ph6 一并迁移这三个运行时 `env.pools` 消费端为 banner 池展开读取（§3.12 Ph6 / §四 波及范围）——原计划未安排、现已排期 |
| `result.pool_end_resources` 字段改名 banner_end 后，`gacha_panel.py:111` 的 `.get('pool_end_resources', {})` 静默拿空 dict、无异常可发现（AUDIT-BREAK-6） | Ph7 将 gacha_panel.py:111 一并迁移为 `.get('banner_end_resources', {})`（§3.12 Ph7 / §四 波及范围） |
| 既有测试以将删字段构造 `Pool`/`PoolEntry` 或直测退役 API 的破坏面远超 GATE-6 排期的两项（AUDIT-BREAK-7） | 破坏点完整清单（test_pool / test_gacha_service._make_pool / test_epitomizable_cards / test_pity_integration / test_batch_draw / test_gacha_service:142）并入原子单元与 Ph4 排期（§3.12 交付单元结论段） |

<!-- REVIEW-R1-FIX: GATE-4 -->
### 6.1 实施前裁决门控（Decision Gates）——承重分叉清单

> **定位（REVIEW-R1-FIX: GATE-4）**：§六 风险表 20+ 项均有缓解，但下表中 **4 项「待人工裁决」是承重语义分叉**——计划已选默认分支并写入方案，但默认与备选实现出不同语义，实施后改判将返工。每项在**对应阶段启动前**须经用户裁决（语义属产品/验收口径，计划作者无法单方定夺）；未裁决时按「默认选型」实施。

| 编号 | 分叉点 | 默认选型（计划已写入） | 备选方案 | 语义差异 | 影响面 | 裁决时点 |
|------|--------|------------------------|----------|----------|--------|----------|
| **DECISION-1** | `one_shot` 语义（§3.2） | **一次性批次**——batch_size 抽完成后才 exhausted | 抽取 1 次即 exhausted | 默认使免费十连 =10 抽；备选使 free_10pull 退化为单抽 | §3.5 批次语义 / §3.6 示例 / Ph9 用例 / §七 验收 | **Ph1 启动前** |
| **DECISION-2** | 批次中途耗尽处置（§3.2） | **立即生效 + batch 循环 break 终止剩余**——max_draws 硬上限不被批次惯性突破（15/10 恒 15） | 继续抽完本批次 | 备选把 max_draws 退化为批次边界近似（15/10 抽满 20） | §3.5 批次循环守卫 / Ph9 用例（ISSUE-302） | **Ph1 启动前** |
| **DECISION-3** | `store.pools` 读侧兜底（§3.9） | **写侧 dual-write**（Legacy mirror 回填 `store.pools`）——旧消费方零改动 | 消费方逐一改读 `flattened_pools`（点改清单入 Ph7/Ph8c） | 备选严格单一数据源但改动面扩大、与 ISSUE-010「`store.pools` 保持可变字段」约束需重平衡 | §3.9 数据模型 / §四 6+ 消费方 / Ph4 + Ph8c | **Ph3/Ph4 启动前** |
| **DECISION-4** | 兼容模式统计键格式（§3.13.1） | **全限定 `{旧pool_id}.main`** + 旧数据集键迁移映射 / 消费端兼容读取（Ph7 指纹/版本化一并处理，ISSUE-013） | 兼容模式保持裸 `{旧pool_id}`——双键格式并存 | 备选不迁移旧数据但双键并存、消费端需区分来源 | 旧 compact 结果兼容 / Ph7 指纹 / gdr / process_trace / main_window / data_manager | **Ph7 启动前** |

**门控机制**：裁决经用户确认默认选型（或改选备选）后关闭对应门控；§3.12 实施前置自检后、首提交落地前完成 DECISION-1/2 裁决，DECISION-3/4 在其阶段启动前完成。裁决结果写回本节「默认选型」列。**改判代价**：DECISION-1/2 在 Ph1 落地后改判 → 重写 §3.5 批次循环与 Ph9 用例；DECISION-3 在 Ph4 后改判 → 重建消费方点改清单；DECISION-4 在 Ph7 后改判 → 重做统计键迁移。裁决因此必须早于对应阶段启动。

<!-- REVIEW-R1-FIX: GATE-5 -->
### 6.2 回滚策略

> **定位（REVIEW-R1-FIX: GATE-5）**：全计划此前无任何回滚/rollback/revert 内容。本计划含 breaking 变更（删 `Pool` 4 字段、改保存格式为 `[[banner]]`、统计键全限定化），须显式回滚策略。回滚以 GATE-3 原子 commit 边界为**可回滚点**（每 commit 落地后系统可运行 → 可逐 commit 回退）。

**三层回滚：**

| 层 | 可回滚机制 | 操作 | 前提 |
|----|-----------|------|------|
| **配置层** | 旧 `[[pool]]` 向后兼容 + 保存侧双路径（§3.9 ISSUE-012）——「不写 `[[banner]]` 时现有 `[[pool]]` 行为完全不变」 | 删除 `[[banner]]` 段即回到纯 `[[pool]]` 配置，旧版本解析器原样可读 | 配置文件从未在 P61 版本保存过 `[[banner]]`（见「保存格式回滚」注意） |
| **代码层** | GATE-3 commit 边界：首提交 = {Ph1, Ph1a, Ph1b, Ph1c, Ph2, Ph5} 一次落地；Ph3/Ph4/Ph6/Ph7/Ph8/8b/8c/Ph9 各自独立可运行 | 逐 commit `git revert <commit>`，或 `git checkout <前一可运行commit> -- <文件>` | 每个 commit 是完整可运行态（GATE-3 已保证） |
| **数据层** | 统计键全限定化前，旧 compact 结果以裸 `{pool_id}` 存储；回滚后旧代码读旧键仍兼容 | 不迁移旧结果；新结果经 DECISION-4 裁决的映射/兼容读取与旧结果隔离（ISSUE-013 指纹/版本化） | DECISION-4 裁决完成（§6.1） |

**回滚触发条件：**
1. **首提交（原子单元）**验证失败（`pytest` 不通过、8 策略 banner 模式回归失败、旧 `[[pool]]` 等价验收失败）→ **整体 revert 首提交**回 Ph0 态。首提交内部无中间态可部分回退（字段已删而策略未迁的中间态不可运行，这正是 GATE-3 强制同 commit 的原因）。
2. 任一后续阶段 commit 引入回归（模拟结果与旧版本批量差异 / GDR / 保底 / 池结束快照异常）→ 定位该 commit 并 revert。
3. **保存格式回滚**：若配置文件已在 P61 版本保存为 `[[banner]]`，回滚到旧版本（仅解析 `[[pool]]`）会让池数据整体丢失——回滚前须经 Ph4 `flattened_pools` 导出为 `[[pool]]` 回退格式，或连同配置文件一起回退（config.toml 受 git 管理时最简：`git checkout <旧commit> -- gacha_simulator/config/config.toml`，代码+配置同 commit 回退天然一致）。
4. 数据分析侧：可比性指纹 / `config_hash` 含 Banner 维度（ISSUE-013）——回滚代码后旧数据集与 P61 版本结果可区分，不被误判「配置相同」。

**不可部分回滚点**：首提交的字段删除（`Pool.available_from/until`、`pool_type`、`is_rerun`、`original_pool_id`）在落地后固化——单独 revert 字段删除而保留 Banner 路由会立即 AttributeError。回滚首提交 = 整体回到 Ph0（Notifier 保留，其余撤销）。计划因此将**配置层**（向后兼容）与**代码层**（commit 边界）分离回滚，避免「配置已迁移而代码未回滚」或反之的错位。

## 七、验收标准

**引擎与集成：**
- [ ] 不写 `[[banner]]` 时，现有 `[[pool]]` 行为完全不变（向后兼容）
- [ ] Step 链：3个 pool 的阶梯池按 `pool_draws` 阈值自动切换
- [ ] 送抽插入：main 池30抽后自动切换到 free_10pull 池；free_10pull 耗尽后自动切回 main
- [ ] 保底旁路：`excludes_all_pity` 的 pool 不触发 `before_draw`/`after_draw`，不影响保底计数器
- [ ] 新手池：`max_draws` 达到后 exhaust
- [ ] 一次性 pool：`one_shot=true` 的 pool 在一次 batch（batch_size 抽）完成后标记 exhausted，不可再抽；批次中途不因 one_shot 耗尽切换/终止（REVIEW-R1-FIX: ISSUE-002）
- [ ] 批次内每抽对当前活跃池单独扣费：lifecycle 中途 switch_to 改变成本后，剩余抽数按新池成本逐抽检查，不可负担即终止本批次——旗舰 free_10pull 场景仅持 free_ticket 时不静默消耗 orundum，免费十连实际出满 10 抽（REVIEW-R1-FIX: ISSUE-002）
- [ ] Pool `max_draws` 自动耗尽：引擎自动监控 `_pool_draws[id] >= max_draws` → 标记 exhausted——无需在 lifecycle 中手写 `pool_draws → exhaust_pool` 规则
- [ ] Banner `max_draws` 自动耗尽：引擎自动监控 `_total_draws >= max_draws` → 自动 `_exhaust()`——新手池 `max_draws = 20` 配置即生效，无需手写 `banner_draws → exhaust_banner` lifecycle 规则（§3.6 新手池示例已移除冗余规则，ISSUE-303）
- [ ] Pool `max_draws` 非 batch_size 倍数的批次中途耗尽：max_draws=15 / batch_size=10 时第 15 抽落在第 2 批次中途，本抽完成后 batch 循环 break 终止剩余抽数，总抽数恒为 15——硬上限不被批次惯性突破（REVIEW-R1-FIX: ISSUE-302）
- [ ] `card_obtained`（card_id 匹配）与 `time_window` 条件在引擎层可求值——after_draw 订阅 handler 将本抽 `card_id` 与 `state.real_time` 透传进 `_check_transitions(card_id, real_time)`，新手池 `on = { card_obtained = "ssr_1" }` 提前关闭与 `on = { time_window = 21 }` 阶段切换均生效（REVIEW-R1-FIX: ISSUE-001）
- [ ] `card_obtained` 稀有度匹配（`match = "rarity"`，如 `rarity = "ssr"`）用于终末地新手池「出任意 6★ 即关闭」——`_check_transitions` 经本抽 `DrawOutcome.reward.extra_info['rarity']` 判定（Ph1c 交付，REVIEW-R1-FIX: ISSUE-306）；UI 侧 §3.10.5 二级匹配控件（`card_id` / `rarity` 切换）对应
- [ ] `banner.pending_transitions` 正确暴露「还差X抽触发Y」——事件型条件（card_obtained / pool_exhausted）remaining=-1（不可预估）、阈值型（pool_draws/banner_draws/time_window）为剩余抽数/向上取整剩余天数；策略示例带 `pt.remaining >= 0` 守卫，事件型规则不被误判为「立刻可触发」，time_window 2.5 天不截断为 2（REVIEW-R1-FIX: ISSUE-305）
- [ ] Notifier 优先级生效：P58（资源注入，priority=0）先于 P61（生命周期检查，priority=1）
- [ ] 生命周期转换单一触发点：`_check_transitions` 仅由 `after_draw` 订阅（P61 priority=1）触发一次，Banner.draw 内部不再评估——每抽至多一次转换，无级联二次触发；Notifier 实例与 P61 订阅装配于 Ph2 的 gacha_service（REVIEW-R1-FIX: ISSUE-001）
- [ ] after_draw 事件按单抽粒度发射——batch_size=10 的池每抽 emit 一次，P58 每抽计数与 collector 逐抽记录与现状等价（REVIEW-R1-FIX: ISSUE-004）
- [ ] after_draw 事件契约三处统一（§3.3 / §3.5 / §5.4 键名与 pool_id 取值源一致：`banner_id` + `card_id` + `pool_id`=全限定键 + `pity_triggered` + `state` + `collector`），P58 按 §5.4 契约实现即可消费（REVIEW-R1-FIX: ISSUE-005）
- [ ] collector 逐抽记录与现状等价——compact `draw_pity_names` 由 `DrawOutcome.triggered_pity_name` 供给、非恒为 None（含触发保底名称，与 gacha_service.py:310-316 现状一致）（REVIEW-R1-FIX: ISSUE-003）
- [ ] `random` 推导公式按两种 rewards 表示分别实现（tuple：`rewards[0][1] < 1.0`；dict：`rewards[0]['probability'] < 100.0`），无 `rewards[0].prob` 属性访问（REVIEW-R1-FIX: ISSUE-008）
- [ ] `time_window` 生命周期阈值支持浮点天数书写（TOML/UI 层 `at` / `at_value` 为 float），解析边界 `* DAY` 换算为秒后与 `real_time`（秒）比较——21.5 天等非整数值不截断提前触发，与 `available_from`/`available_until` 精度一致（REVIEW-R1-FIX: ISSUE-009/001）
- [ ] P55 槽位概率聚合（featured/standard + scale_factors 还原）在 Banner.draw 内正确迁移——featured 卡保底概率与现状一致（AUDIT-BREAK-8 回归）；`aggregate_probs_by_rarity`/`infer_rarity_from_spec` 已下沉为 core 层模块级函数，core 层与 service 层调用结果一致（REVIEW-R1-FIX: ISSUE-004/005）
- [ ] 含 exchange / batch_size≠1 / P56 定轨 / `enabled=False` 禁用池 的旧 `[[pool]]` 自动包装后行为与现状等价——enabled 判定与 featured 保底重置判定（featured_ids 由 rewards featured 聚合）不退化（REVIEW-R1-FIX: ISSUE-006/007）
- [ ] banner 池的保底重置判定与现状等价——PoolPitySpec.featured_ids 从 banner rewards 聚合（REVIEW-R1-FIX: ISSUE-009）
- [ ] `StrategyContext` 同时提供 `banners` 和 `current_pools`（后者由 `active_banners[*].active_pool` 推导填充）；8 个内置策略经 Ph1a 迁移后，banner 模式与旧 `[[pool]]` 模式运行结果等价（策略迁移是强制项——「无需修改」验收取消）（REVIEW-R1-FIX: ISSUE-001）
- [ ] fixed_count / target_hunting 已随 Ph1a 迁移到 `ctx.banners` 双字段——target_hunting 的 `target_pool_ids` 匹配 `banner_id`，`[[pool]]` 兼容模式下旧池 id（如 `'genshin_limited'`）命中 Banner id，不再恒空；fixed_count 的 `DrawAction` 带 `banner_id`，不依赖裸 `'main'` 反查（REVIEW-R1-FIX: ISSUE-003）
- [ ] `GachaState.get_available_pools()` 已删除；`tests/core/test_state.py::test_get_available_pools` 已随 Ph1b（原子单元）同步删除/改写，不再引用 `get_available_pools`，首提交后 pytest 全量通过（REVIEW-R1-FIX: ISSUE-002 / GATE-6_测试策略）
- [ ] `GachaService.__init__` 构造桥生效——`_run_single`（batch_simulator.py:228）与现有测试直接构造 `GachaService([pool],...)` 后 `self._banners` 非空、`run_simulation` 正常路由；`from_config_store`（batch_simulator.py:547-559）不再以已删字段（`available_from`/`available_until`/`pool_type`/`is_exchange`）构造 `Pool(...)`（REVIEW-R1-FIX: GATE-3_依赖顺序，Ph1a + Ph2）
- [ ] 池结束快照机制已迁移：`on_banner_end` 写 `CompactResult.banner_end_resources`/`banner_end_pity_states`，P62 可达过滤 / per_pool_analysis / `core/vulnerability.py` 逐池分箱消费端一致——脆弱性分析字段改名后不静默返回空结果（REVIEW-R1-FIX: ISSUE-003/005）
- [ ] `result.pool_types` 由 output/random 推导填充（值来源变化）且键格式改为全限定 `{banner_id}.{pool_id}`（键迁移），gdr 白名单 / process_trace 分类 / main_window / data_manager 消费结果与旧 pool_type 等价（REVIEW-R1-FIX: ISSUE-004/002）
- [ ] `build_strategy_context()` 新增 `banners`/`all_banners` 参数并透传——banner 模式模拟运行不再 TypeError（REVIEW-R1-FIX: ISSUE-005）
- [ ] `DrawAction.banner_id` 生效；`pool_id` 改 `Optional`（默认 None，省略时服务层按 `banner.active_pool` 路由——§3.7 示例 `DrawAction(banner_id=banner.id)` 不再 TypeError，ISSUE-004）；定轨（NonDrawAction switch/cancel）在 banner 模式经 `{banner_id}.{pool_id}` 全限定键正确派发到 TargetedBehavior（REVIEW-R1-FIX: ISSUE-006/004）
- [ ] `filter_target_specs_by_obtainable` 读 `store.banner`——banner 模式下 `_obtainable` GDR 分母与 `[[pool]]` 模式语义一致（REVIEW-R1-FIX: ISSUE-009）
- [ ] PityEngine 键统一为 `{banner_id}.{pool_id}`——多 Banner 各含同名 `main` 时保底不串池（REVIEW-R1-FIX: ISSUE-010）
- [ ] 逐池统计键（stats / collector / `pool_types`）同步统一为 `{banner_id}.{pool_id}`——多 Banner 各含同名 `main` 时 `pool_draw_counts`/`pool_card_counts`/`pool_pity_counts`/`draw_pool_ids` 不串池，gdr 白名单 / process_trace 分类 / main_window / data_manager 消费键已迁移（REVIEW-R1-FIX: ISSUE-002）
- [ ] 全量历史模式 `InfoVector.pool_id` 与紧凑模式键语义一致（均全限定 `{banner_id}.{pool_id}`）——同一模拟循环两模式 `draw_pool_ids`/`pool_card_counts` 键不分裂，混用两模式结果不聚合错配（REVIEW-R1-FIX: ISSUE-006）
- [ ] `SimulationEnv.banner_defs` 带默认值——旧 worker 反序列化不破坏（跨进程 pickle 兼容）（REVIEW-R1-FIX: ISSUE-011）
- [ ] 里程碑抽数计数含 free_10pull/一次性池抽数；`excludes_all_pity` 不阻断计数（REVIEW-R1-FIX: ISSUE-014）
- [ ] P58 经 Notifier 订阅后，里程碑结算以订阅函数形式落地，gacha_service 其余代码零改动（P58 当前未实施——本条为契约验收，待 P58 落地后验证）（REVIEW-R1-FIX: ISSUE-001）

**ConfigStore：**
- [ ] `BannerEntry` / `BannerPoolEntry` / `LifecycleRuleEntry` / `BannerConfig` dataclass 正确定义
- [ ] `ConfigStore.banner` 字段可用，`ConfigStore.clear()` 重置 `self.banner = BannerConfig()`
- [ ] `flattened_pools` 只读视图 + 写侧 dual-write：banner 模式下 `store.pools` 字段本身被 `_build_banners()` 展平回填（非空），`pool_id` 为全限定 `{banner_id}.{pool_id}`；旧字段读者不拿空列表（REVIEW-R1-FIX: ISSUE-007/006）
- [ ] `_wrap_pools_as_banners` 的 rewards 元素统一为 dict（正常分支 PoolDistEntry→dict 转换；exchange 分支 100% 单卡 dict）——`rewards[0]['probability']` 推导与 featured 聚合 `r['card_id']` 对两种分支均不抛 TypeError（REVIEW-R1-FIX: ISSUE-304）

**TOML：**
- [ ] `[[banner]]` / `[[banner.pool]]` / `[[banner.pool.reward]]` / `[[banner.lifecycle]]` TOML 段解析正确
- [ ] `[[pool]]` 自动包装为单 pool Banner（无 `[[banner]]` 段时）
- [ ] Banner TOML round-trip 保真——GUI 编辑 → 保存 → 重载后字段不丢失
- [ ] 保存侧双路径：banner 配置保存写回 `[[banner]]`；无 `[[banner]]` 时仍写 `[[pool]]` 且旧 `[[pool]]` 行为完全不变（REVIEW-R1-FIX: ISSUE-012）
- [ ] 永久 Banner（`available_until=None`）不抛 TypeError——逐 Banner 有效结束时间 `eff_end = until if until is not None else from + 21 * DAY`、`end_time = max(eff_end)`（单位秒，与 `banner_end_times_sorted` 的 `available_until`、`real_time` 一致），`AllPoolsEndCondition` / 资源收益日程不退化，与现状 `(start_day + 21) * DAY` 秒兜底语义逐池等价（REVIEW-R1-FIX: ISSUE-007/001）

**UI（ConfigPanel「卡池管理」Tab）：**
- [ ] 左侧 Banner 列表 + 右侧顶部基础字段（QFormLayout，4个字段：name/id/max_draws/时间窗口）
- [ ] `id` 为 `QLineEdit`（可编辑），变更时级联更新生命周期和保底中的引用
- [ ] 右侧两子标签页：池 / 生命周期
- [ ] 「池」子标签页上半——5 列表格（ID/成本/批次/一次性/不计保底），内联编辑
- [ ] 「池」子标签页下半——5 列奖励表（卡ID QComboBox 仅可选已注册卡牌/概率% QDoubleSpinBox/稀有度 QLabel 自动解析/Featured QCheckBox/资源获取 QLineEdit），选中上半行自动切换
- [ ] 按钮 `[添加]` `[移除选中]` `[缩放至100%]`——添加空行/仅删除选中行/按比例缩放所有行至合计100%
- [ ] 「生命周期」子标签页——5 列表格（关联池/条件/阈值/动作/目标），QComboBox 委托正确填充
- [ ] 左栏底部按钮 `[添加] [移除] [复制] [批量创建...]`
- [ ] 「批量创建...」对话框：模板Banner选择 / 数量 / ID前缀 / 名称前缀 / 起始时间 / 间隔 → 预览 → 批量生成
- [ ] **移除**「池子模板」表格及相关控件
- [ ] 无「启用 Banner 模式」总闸
- [ ] `apply_to_store()` 将 Banner UI 数据写回 `store.banner.banners`
- [ ] `set_config()` 从 `store.banner.banners` 回填 Banner UI
- [ ] `get_config()` 返回字典含 `'banner'` 键
- [ ] Tab 在 `_setup_ui()` 中正确注册（替代旧「卡池配置」Tab 的位置）

**UI（ConfigPanel「保底机制」Tab 增强）：**
- [ ] **删除**旧的 `pools` 手写 fnmatch 文本框
- [ ] 「绑定池」勾选表格（Banner / Pool / 说明 三列 + QCheckBox）——直接勾选要绑定的 Banner.Pool 对
- [ ] `excludes_all_pity=True` 的 pool 在「说明」列标注「(不计保底)」
- [ ] 加载时：`pools` fnmatch pattern → 自动勾选匹配行；保存时：勾选行 → 自动生成紧凑 fnmatch pattern
- [ ] `[全选]` `[全不选]` 按钮
- [ ] 匹配逻辑三路兼容：对每个 `{banner_id}.{pool_id}` 依次做全限定 / `banner_id` 段 / 裸 `pool_id` 段 fnmatch——旧 `[[pool]]` + 旧 `pools = ["genshin_limited"]`（命中 banner_id 段）与旧 `pools = ["main"]`（命中裸 pool_id 段）均不失绑（REVIEW-R1-FIX: ISSUE-004）
- [ ] 保留现有左列表+右动态表单结构（BEHAVIOR_REGISTRY 驱动）不变

**DataManager / 指纹：**
- [ ] 可比性指纹按 banner 维度（pool_ids 指纹改 banner 标识或新增 banner_ids 字段，旧数据集兼容）；`config_hash` 纳入 Banner 级配置（lifecycle / 时间窗口 / 开关属性）——仅 Banner 配置不同的数据集不被判「配置相同」（REVIEW-R1-FIX: ISSUE-013）

**测试：**
- [ ] `test_banner.py` 覆盖全部 lifecycle 规则 + 集成 + 向后兼容 + 8 策略迁移回归（banner 模式跑通）
- [ ] `tests/core/test_state.py::test_get_available_pools` 已随 Ph1b 删除/改写，不再引用 `get_available_pools`
- [ ] `tests/service/test_gacha_service.py::test_env_builder_from_config_store_smoke` 已随 Ph1b 改写——不再断言已删 `pool_type` 字段，改断言推导属性（`pool.output`/`pool.random` 或 §3.13.1 `derive_type`）；`_make_pool`（:14-21）与 `test_initial_count_multiple_cards`（:68-69）不再以 `available_from`/`available_until` 构造 `Pool`（AUDIT-BREAK-7）
- [ ] `tests/core/test_pool.py` 的 `is_available_at` 用例已删除/改写——不再直测退役 API、不以将删字段构造 `Pool`（AUDIT-BREAK-7）；`tests/core/test_epitomizable_cards.py:189/202-205`、`tests/core/test_pity_integration.py:97/150` 不再以 `pool_type`/`available_from`/`available_until` 构造 `Pool`（AUDIT-BREAK-7）；`tests/core/test_batch_draw.py:24`、`tests/service/test_gacha_service.py:142` 不再以 `pool_type` 构造 `PoolEntry`（随 Ph4 删字段，AUDIT-BREAK-4/7）
- [ ] 原子提交态 pity 键一致——`_build_pity_engine_from_gui`/`from_config_store` 的 pool_specs 键为全限定 `{pool.id}.main` 且与 gacha_service 查询键同口径，原子提交后 soft pity 不静默失效（旧 `[[pool]]` + 旧 `PityDef.pools` 绑定等价，AUDIT-BREAK-3 / §3.5 要点 12）
- [ ] pytest 全量通过（成立时点：原子提交 {Ph1, Ph1a, Ph1b, Ph1c, Ph2, Ph5} + 上述测试改动（含 AUDIT-BREAK-7 全部既有测试破坏点）同步落地后；Ph9 `test_banner.py` 新增用例不在首提交通过判据内——REVIEW-R1-FIX: GATE-6_测试策略）

## ⚠ 自动化审查阻塞项

未解决问题：**0 个**，详情：`[]`。

> **标注原因**：6 轮对抗循环未收敛。Finder→Fixer→Verifier 对抗验证流水线（计划审查工作流 P38 阶段 2）在 6 轮后仍未达到收敛判据（每轮仍产生新的 ISSUE 修正），按工作流标记为自动化审查阻塞项；审查结束时最终存活未解决问题为 0 个。

## 自动化审查记录

<details>
<summary>第 1 次审查（2026-06-11）——P38 工作流自动化</summary>

- 复杂度: complex | 变更性质: breaking
- 阶段 1 影响面: 56 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 57 个

</details>
