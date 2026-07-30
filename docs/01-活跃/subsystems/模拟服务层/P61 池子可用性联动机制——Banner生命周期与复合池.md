<!-- META: P61 | module:模拟服务层 | status:designing | last:2026-07-30 -->

# P61 池子可用性联动机制——Banner生命周期与复合池

> 日期：2026-07-30 | 状态：设计中（原方案重写，UI/配置设计已补全）
> 触发：step池拆分建模（每步抽N次后解锁下一步）与终末地30抽取送抽池（强制插入、一次性、不计保底）需要池间可用性联动，当前仅支持基于时间窗口的单池独立可用性。
> 原方案归档：[P61 池子可用性联动机制——step链与送抽插入（规则引擎版）](../../../03-归档/P61 池子可用性联动机制——step链与送抽插入（规则引擎版）.md)（2026-06-20，已归档）

## 一、问题

### 1.1 功能缺口

当前池子可用性仅基于 `available_from` / `available_until` 时间窗口判断（`Pool.is_available_at()` → `GachaService.run_simulation` 的 `current_pools` 列表推导）。存在三个无法建模的场景：

| 场景 | 机制 | 缺失能力 |
|------|------|---------|
| **Step 池链** | 拆分 N 个阶梯，step N 抽满 M 次后解锁 step N+1，step N 不可用 | 池内阶段切换 + 抽数阈值触发 |
| **送抽插入** | 主池累计 30 抽 → 强制弹出独立送抽池 → 必须先抽送抽才回主池 → 送抽不计主池保底 | 强制插入 + 主源阻塞 + 一次性消耗 + 保底旁路 |
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

1. **Banner（逻辑卡池）** — 用户配置和统计的一等单位。内部包含多个 Pool（抽取源），Pool 对用户透明。Banner 自动管理 Pool 之间的切换、阻塞、耗尽。
2. **Lifecycle（声明式生命周期）** — `on 条件 → action` 规则驱动阶段转换，替代规则引擎的每迭代重算。
3. **Notifier（轻量通知机制）** — `core/notifier.py`（~30行），P61和P58通过订阅同一事件总线协作，互不 import 对方模块。
4. **TransitionPreview（策略可见进度）** — 策略可查询「还差多少抽触发下一阶段」。

覆盖场景（与原方案一致）：

- [x] Step 池链：step1→step2→step3 按抽数阈值自动切换
- [x] 送抽插入：主池30抽后触发，主源被阻塞，送抽源消耗完毕后恢复
- [x] 新手池关闭：`max_draws` 硬上限 + 可选 `card_obtained` 提前退出
- [x] 一次性池：`one_shot` source 抽后永久不可用
- [x] 保底排除：`excludes_all_pity` source 完全旁路保底引擎
- [x] 向后兼容：不写 `[[banner]]` 时现有 `[[pool]]` 自动包装为单 source 的 banner

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

```python
# ── 数据结构 ──

@dataclass
class Pool:
    """Banner 内部的独立抽取单元——自包含，不引用外部"""
    id: str                          # pool 标识符，如 "main"、"free_10pull"、"step2"
    cost: PoolCost                   # 抽取成本（必填——每个 Pool 独立确定）
    rewards: List[Tuple[Reward, float]]  # 奖励表（必填——内联，非引用）
    batch_size: int = 1              # 每次抽取连数
    one_shot: bool = False           # 一次性消耗——抽取1次后即标记 exhausted
    excludes_all_pity: bool = False  # 完全旁路保底引擎
    blocks_parent: bool = False      # 激活时阻塞 id="main" 的池
    max_draws: Optional[int] = None  # 该 pool 的最大抽取次数


@dataclass
class TransitionRule:
    """声明式转换规则：on 条件 → action"""
    condition: str                   # "pool_draws" | "banner_draws" | "card_obtained"
                                     # | "pool_exhausted" | "time_window"
    pool: Optional[str] = None       # 条件关联的 pool id
    at_value: int = 0                # 阈值
    action: str                      # "activate_pool" | "deactivate_pool"
                                     # | "block_pool" | "unblock_pool"
                                     # | "exhaust_banner" | "advance_step"
    target: Optional[str] = None     # action 的目标 pool id


@dataclass
class TransitionPreview:
    """策略可读的进度信息——「还差多少触发什么」"""
    trigger: str                     # 触发条件类型
    remaining: int                   # 还差多少
    at_value: int                    # 阈值
    current_value: int               # 当前进度
    action: str                      # 触发后执行的动作
    description: str                 # 人类可读描述
    target_pool: Optional[str] = None
    blocks_current: bool = False     # 触发后是否阻塞当前活跃池


@dataclass
class Banner:
    """卡池——用户配置的一等单位"""
    id: str
    name: str
    pool_type: str = ""                             # "角色" | "武器" | "常驻" | "新手" | "混池" | "阶梯"
    pools: Dict[str, Pool]                          # pool_id → Pool
    lifecycle: Dict[str, List[TransitionRule]]      # phase → rules
    max_draws: Optional[int] = None                 # Banner 级总抽数硬上限
    available_from: Optional[float] = None          # 时间窗口起点
    available_until: Optional[float] = None         # 时间窗口终点

    # 运行时状态
    _phase: str = "normal"
    _active_pool_id: str = "main"
    _blocked_pools: Set[str] = field(default_factory=set)
    _exhausted_pools: Set[str] = field(default_factory=set)
    _pool_draws: Dict[str, int] = field(default_factory=dict)
    _total_draws: int = 0
    _phase_history: List[Tuple[int, str, str]] = field(default_factory=list)

    # ── 策略可见属性 ──
    @property
    def is_available(self) -> bool: ...
    @property
    def is_exhausted(self) -> bool: ...
    @property
    def phase(self) -> str: ...
    @property
    def active_pool(self) -> Pool: ...
    @property
    def total_draws(self) -> int: ...
    @property
    def pending_transitions(self) -> List[TransitionPreview]: ...

    # ── 核心方法 ──
    def draw(self, state, pity_engine, pity_state) -> Reward:
        """自动路由到活跃 pool，处理保底旁路"""

    def _check_transitions(self):
        """检查当前 phase 的转换规则，触发条件满足时执行 action"""

    def _activate_pool(self, pool_id: str): ...
    def _block_pool(self, pool_id: str): ...
    def _exhaust(self): ...
```

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
# P61 侧 —— 发射事实
notifier.emit("after_draw", banner_id=banner.id, draw_count=banner.total_draws,
              card=reward.id, pity_triggered=triggered)

# P58 侧 —— 订阅事实（P58 模块内部，P61 不知晓）
notifier.subscribe("after_draw", milestone_engine.on_draw, priority=0)
```

**关键约束：**
- Notifier 不存储事件历史——它不是事件溯源，只是分发机制
- 所有订阅者是同步调用的——emit() 返回时所有 handler 已执行完毕
- 优先级保证顺序：P58（资源注入，priority=0）→ P61（生命周期检查，priority=1），避免「P61检查时资源还没注入」的竞态
- P61 不 import P58 的任何符号，反之亦然

### 3.4 旧 Pool 与 Banner 的关系

Banner 内的 `Pool`（`core/banner.py`）和旧 `Pool`（`core/pool.py`）是**两个不同的类**，共享同样的名字但处于不同层级：

- 旧 `Pool`：顶层物理池，存于 `ConfigStore.pools`，`core/pool.py` 不动
- 新 `Pool`：Banner 内部的自包含抽取单元，所有字段内联

迁移路径：

```python
# 向后兼容：现有 [[pool]] 自动包装为 Banner
def _wrap_pools_as_banners(pools: List[Pool]) -> List[Banner]:
    """每个旧 Pool 包装为一个 Banner（内有一个 main pool）"""
    banners = []
    for old_pool in pools:
        new_pool = Pool(
            id="main",
            cost=old_pool.cost,
            rewards=old_pool.rewards,
            batch_size=old_pool.batch_size,
        )
        banner = Banner(
            id=old_pool.id, name=old_pool.name,
            pools={"main": new_pool},
            available_from=old_pool.available_from,
            available_until=old_pool.available_until,
        )
        banners.append(banner)
    return banners
```

**不修改 `core/pool.py`。** 旧 Pool 类继续存在，Banner 内的 Pool 是独立定义。

### 3.5 GachaService 集成

```python
# gacha_service.py 的变更：current_pools → current_banners

def run_simulation(self, ...):
    banners = self._banners  # List[Banner]
    notifier = self._notifier

    for iteration in range(max_iterations):
        if _check(state, [], stats):
            break

        # 可用性过滤——Banner 级别，O(B) 而非 O(P)
        active_banners = [b for b in banners if b.is_available]

        ctx = build_strategy_context(
            state=state,
            banners=active_banners,       # ← 替代 current_pools
            all_banners=banners,          # ← 替代 all_pools（策略可查看被阻塞的 banner）
            ...
        )

        action = _strategy.select_action(ctx)

        if isinstance(action, DrawAction):
            banner = self._banners.get(action.banner_id)
            # Banner.draw() 内部自动路由到活跃 source + 处理保底旁路
            reward = banner.draw(state, _pity_engine, pity_state)

            # 抽后通知——P58 和 P61 的生命周期规则各自订阅
            notifier.emit("after_draw",
                          banner_id=banner.id,
                          draw_count=banner.total_draws,
                          card=reward.id,
                          pity_triggered=triggered)
```

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
pool_type = "新手"
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

[[banner.lifecycle]]
on = { banner_draws = 20 }
action = "exhaust_banner"
```

> **已记录、待实现**：终末地新手池「抽出任意 6★ 即关闭」需要 `card_obtained` 条件支持稀有度匹配（如 `rarity = "ssr"`），参见手册 §16。当前 `card_obtained` 仅匹配特定 card_id。

**终末地送抽插入 + 60抽档案：**

```toml
[[banner]]
id = "endfield_limited"
name = "终末地限定寻访"
pool_type = "角色"

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
blocks_parent = true

[[banner.pool.reward]]
card_id = "endfield_ssr_1"
probability = 0.6
rarity = "ssr"
featured = true
# ... 奖励表（通常与 main 相同）...

[[banner.lifecycle]]
# main 抽满30次 → 激活送抽 + 阻塞 main
on = { pool_draws = "main", at = 30 }
action = "activate_pool"
target = "free_10pull"

[[banner.lifecycle]]
# 送抽耗尽 → 解除 main 阻塞
on = { pool_exhausted = "free_10pull" }
action = "unblock_pool"
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
pool_type = "阶梯"

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
action = "activate_pool"
target = "step2"

[[banner.lifecycle]]
on = { pool_exhausted = "step1" }
action = "deactivate_pool"
target = "step1"

[[banner.lifecycle]]
on = { pool_draws = "step2", at = 10 }
action = "activate_pool"
target = "step3"
```

### 3.7 策略层接口

策略通过 `StrategyContext.banners` 获取 Banner 列表，每个 Banner 暴露：

```python
# ── 可用性 ──
banner.is_available       # bool: 当前是否可以抽
banner.is_exhausted       # bool: 是否已永久关闭

# ── 当前状态 ──
banner.phase              # str: "normal" | "free_pull_interrupted" | ...
banner.active_pool_id   # str: 当前活跃的 pool

# ── 进度 ──
banner.total_draws        # int: 该 Banner 的总抽数（跨 pool 聚合）
banner.pool_draws       # Dict[str, int]: 每个 pool 的抽数

# ── 待处理转换（策略决策核心）──
banner.pending_transitions  # List[TransitionPreview]: 按 remaining 升序排列
```

策略使用示例（SmartStrategy）：

```python
for banner in ctx.banners:
    for pt in banner.pending_transitions:
        # 送抽即将触发 → 垫刀
        if pt.remaining <= 5 and pt.blocks_current:
            return DrawAction(banner_id=banner.id)

        # 送抽已激活 → 优先消耗免费抽
        if banner.phase == "free_pull_interrupted":
            return DrawAction(banner_id=banner.id)

        # 离阈值远 → 不优先
        if pt.remaining > 20:
            continue
```

### 3.8 统计聚合

Banner 是统计的天然聚合边界：

```python
class BannerStats:
    banner_id: str
    total_draws: int              # 跨 source 自动聚合
    total_cost: Dict[str, float]
    cards_obtained: Dict[str, int]
    pity_triggers: int            # 仅统计非 excludes_all_pity 的 source
    pool_breakdown: Dict[str, PoolStats]  # 按需下钻
```

GDR 计算以 Banner 为单位——`banner_id` 替代 `pool_id` 作为统计维度。

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
    blocks_parent: bool = False
    max_draws: Optional[int] = None
    rewards: List[dict] = field(default_factory=list)  # [[banner.pool.reward]] 解析


@dataclass
class LifecycleRuleEntry:
    """声明式转换规则——从 TOML [[banner.lifecycle]] 解析"""
    condition: str                       # "pool_draws" | "banner_draws"
                                         # | "card_obtained" | "pool_exhausted"
    pool: Optional[str] = None           # 条件关联的 pool id
    at: int = 0                          # 阈值
    action: str                          # "activate_pool" | "deactivate_pool"
                                         # | "block_pool" | "unblock_pool"
                                         # | "exhaust_banner"
    target: Optional[str] = None         # action 的目标 pool id


@dataclass
class BannerEntry:
    """单个 Banner 定义——从 TOML [[banner]] 解析"""
    id: str
    name: str
    pool_type: str = ""
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
│ │   新手寻访     │ │ 类型: [限定 ▼]  最大抽数: [     ]      │  │
│ │   标准寻访     │ │ 时间窗口: [0.0] ~ [21.0]                │  │
│ │   阶梯寻访     │ │                                         │  │
│ │               │ │ ── [池] [生命周期] ──────────────────    │  │
│ │               │ │                                         │  │
│ │               │ │ ┌─ 上半：Pool 列表 ────────────────┐    │  │
│ │               │ │ │ID  │成本      │批│一│不│阻        │    │  │
│ │               │ │ │main│orundum:..│10│☐│☐│—         │    │  │
│ │               │ │ │free│ticket:1  │10│☑│☑│☑         │    │  │
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
│ │               │ │ │main  │pool_draws│30 │activ..▼│free│    │  │
│ │               │ │ │free  │pool_exh. │ — │unblo..▼│main│    │  │
│ │               │ │ └──────────────────────────────────┘    │  │
│ │               │ │        [添加] [移除选中]                  │  │
│ └───────────────┘ └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.10.2 布局结构

- **左栏**（QListWidget，~180px）：Banner 列表，`currentRowChanged` 驱动右侧
- **右栏顶部**（QFormLayout，始终可见）：Banner 基础字段（5个）
- **右栏中部**（QTabWidget，**2个子标签页**）：池 / 生命周期
- **左栏底部**：`[添加] [移除] [复制] [批量创建...]`

#### 3.10.3 Banner 基础字段（QFormLayout，始终可见）

Banner 自身不抽卡——成本/批次/奖励都在 Pool 层级各自配置。

| 字段 | 控件 | 说明 |
|------|------|------|
| `name` | `QLineEdit` | 显示名称 |
| `id` | `QLineEdit` | 唯一标识符（可编辑——变更时级联更新生命周期/保底中的引用） |
| `pool_type` | `QComboBox` | `角色` / `武器` / `常驻` / `新手` / `混池` / `阶梯`——用于分析分类和 UI 筛选 |
| `max_draws` | `QSpinBox` | Banner 级硬上限，0=无限制 |
| `available_from` / `available_until` | `QDoubleSpinBox` | 模拟内相对天数（float） |

#### 3.10.4 子标签页：「池」——上半 Pool 列表

6 列（删除了卡牌摘要列——奖励表在下半内联显示）：

| # | 列名 | 控件 | 说明 |
|---|------|------|------|
| 1 | ID | `QTableWidgetItem`（文本） | pool 标识符，内联编辑。变更时级联更新生命周期引用 |
| 2 | 成本 | `QLineEdit` 委托 | TOML 格式，如 `orundum:600`。必填 |
| 3 | 批次 | `QSpinBox` 委托 | 1–100，默认 1 |
| 4 | 一次性 | `QCheckBox` 委托 | `one_shot` |
| 5 | 不计保底 | `QCheckBox` 委托 | `excludes_all_pity` |
| 6 | 阻塞主池 | `QCheckBox` 委托 | `blocks_parent`——仅当此行 ID ≠ `"main"` 时可用 |

**交互细节**：
- 选中行变更 → 下半奖励表自动切换到该 Pool 的 rewards
- 「阻塞主池」列：ID == "main" 时禁用
- 按钮：`[添加] [移除选中]`

#### 3.10.5 子标签页：「池」——下半奖励表

内联编辑，5 列。卡ID 来自「卡牌定义」Tab 已注册的卡牌池——不可自由输入，必须从下拉列表选择。稀有度自动解析。

| # | 列名 | 控件 | 说明 |
|---|------|------|------|
| 1 | 卡ID | `QComboBox`（`setEditable(True)` + `QCompleter` 前缀搜索） | 下拉选项 = 已注册卡牌列表；新增行时为空，强制选择一张卡 |
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
| 1 | 关联池 | `QComboBox` 委托 | 从已有 pool ID 列表动态填充 |
| 2 | 条件 | `QComboBox` 委托 | `pool_draws` / `pool_exhausted` / `card_obtained` / `banner_draws` |
| 3 | 阈值 | `QSpinBox` 委托 | 条件为 `pool_exhausted` 时禁用（置灰） |
| 4 | 动作 | `QComboBox` 委托 | `activate_pool` / `deactivate_pool` / `block_pool` / `unblock_pool` / `exhaust_banner` |
| 5 | 目标 | `QComboBox` 委托 | 从已有 pool ID 列表动态填充；动作为 `exhaust_banner` 时禁用 |

按钮：`[添加] [移除选中]`

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

### 3.11 「保底机制」Tab 增强

**保留**现有「保底机制」Tab 的整体结构（左保底列表 + 右 QFormLayout 动态详情）。BEHAVIOR_REGISTRY 驱动的动态表单体系继续工作。

**核心变更**：删除旧的 `pools` 手写 fnmatch 文本框——改用一个内联的「绑定池」勾选表格。用户不再需要手写 pattern，直接勾选 Banner.Pool 即可。TOML 存储仍用 `pools` fnmatch pattern（由 UI 自动生成/解析），引擎匹配逻辑不变。

#### 3.11.1 变更总览

| 旧 | 新 | 说明 | 参见 |
|----|----|------|------|
| `pools` QLineEdit（手写 fnmatch） | 「绑定池」QTableWidget（勾选表格） | 删除手写 pattern，直接勾选 | §3.11.2 |
| 生效范围 QGroupBox（只读预览） | 删除——勾选表格本身就是生效范围 | 无需两份UI表达同一信息 | §3.11.2 |
| 快速绑定 QDialog（弹窗） | 删除——勾选表格直接在详情面板中 | 无需弹窗 | §3.11.2 |

#### 3.11.2 「绑定池」勾选表格

在保底详情 `QFormLayout` 底部——替代原来的「适用池子」文本框和「生效范围」面板：

```
┌─ 保底详情 ────────────────────────────────────────────┐
│ 名称: [ssr_soft         ]   类型: [soft_step ▼]       │
│ 稀有度: [ssr ▼]   目标: [☑ Featured]                  │
│ ... (BEHAVIOR_REGISTRY 动态参数) ...                   │
│                                                       │
│ ── 绑定池 ───────────────────────────────────────     │
│ ┌──┬──────────────────┬──────┬──────────┬────────────────────┐  │
│ │☑│ Banner            │ 类型  │ Pool     │ 说明                │  │
│ ├──┼──────────────────┼──────┼──────────┼────────────────────┤  │
│ │☑│ endfield_limited  │ 角色  │ main     │                    │  │
│ │☐│ endfield_limited  │ 角色  │ free     │ 不计保底, 一次性    │  │
│ │☑│ standard_banner   │ 常驻  │ main     │                    │  │
│ │☐│ step_up           │ 阶梯  │ step1    │                    │  │
│ │☐│ step_up           │ 阶梯  │ step2    │                    │  │
│ └──┴──────────────────┴──────┴──────────┴────────────────────┘  │
│              [全选] [全不选]                            │
└──────────────────────────────────────────────────────┘
```

| # | 列名 | 控件 | 说明 |
|---|------|------|------|
| 1 | ☑ | `QCheckBox`（`setCellWidget`） | 勾选 = 该保底规则绑定到此 Banner.Pool |
| 2 | Banner | `QTableWidgetItem`（只读） | Banner 名称 |
| 3 | 类型 | `QTableWidgetItem`（只读） | Banner 的 `pool_type`——辅助按类别筛选（如仅看角色池） |
| 4 | Pool | `QTableWidgetItem`（只读） | Pool ID |
| 5 | 说明 | `QTableWidgetItem`（只读） | 合并显示标签：`excludes_all_pity` →「不计保底」/ `one_shot` →「一次性」/ `blocks_parent` →「阻塞主池」；正常池留空 |

**交互细节**：
- 数据来源：遍历 `store.banner.banners` → 展开每个 Banner 的所有 Pool → 每行一个 `{banner_id}.{pool_id}`
- 「类型」列从 Banner 的 `pool_type` 读取（角色/武器/常驻/新手/混池/阶梯），辅助用户按类别筛选绑定范围
- 「说明」列自动聚合 Pool 的特殊属性标签——用户无需逐列查看 `one_shot`/`excludes_all_pity`/`blocks_parent`
- 加载时：读取 `pools` fnmatch pattern → 对每个 `{banner_id}.{pool_id}` 做 `fnmatch` → 勾选匹配的行
- 保存时：从所有勾选行反向生成紧凑的 fnmatch pattern（共享前缀自动缩写为 `*`，精确 ID 用逗号分隔）→ 写回 `pools`
- 「全选」勾选所有行（生成 `*` = 匹配全部）；「全不选」取消所有勾选
- `excludes_all_pity=True` 的 Pool 仍然可以勾选（绑定是声明性的），但引擎不应用保底

#### 3.11.3 引擎匹配逻辑（不变）

TOML `pools` 字段仍存储 fnmatch pattern。引擎匹配流程不变——遍历所有 Banner 的所有 Pool，用 `{banner_id}.{pool_id}` 与 pattern 做 `fnmatch`。同时保留对裸 Pool ID 的匹配（向后兼容未迁移的 `[[pool]]`）。

### 3.12 实施阶段

| 阶段 | 内容 | 文件 | 预估 |
|------|------|------|:---:|
| Ph0 | `core/notifier.py` —— subscribe / emit / priority。**P61 + P58 共享基础设施**——Ph0 交付后两个计划可完全并行 | 新建 | ~30行 |
| Ph1 | `core/banner.py` —— Banner + Pool + TransitionRule + TransitionPreview + Lifecycle 引擎 | 新建 | ~250行 |
| Ph2 | `service/gacha_service.py` —— `current_pools` → `current_banners`，集成 Banner.draw() + Notifier | 修改 | ~40行变更 |
| Ph3 | `core/config_store.py` —— `BannerEntry` / `BannerPoolEntry` / `LifecycleRuleEntry` / `BannerConfig` dataclass + `ConfigStore` 新增 `banner` 字段 | 修改 | ~50行 |
| Ph4 | `config/config_toml.py` —— `_build_banners()` 解析 `[[banner]]` + `[[banner.pool]]` + `[[banner.lifecycle]]` 段 + `_wrap_pools_as_banners()` 自动包装 | 修改 | ~70行 |
| Ph5 | `core/strategy.py` —— `StrategyContext` 新增 `banners` 字段（保留 `current_pools` 向后兼容）| 修改 | ~5行 |
| Ph6 | `service/batch_simulator.py` —— `SimulationEnv` 新增 `banner_defs` 字段 + `SimulationEnvBuilder` 构建 Banner | 修改 | ~25行 |
| Ph7 | 统计层适配 —— GDR / 过程分析 / 流式分析以 Banner 为聚合单位 | 修改 | ~30行 |
| Ph8 | `gui/config_panel.py` ——「卡池管理」Tab：左Banner列表 + 右基础字段(4个) + 两子标签页（池/生命周期）+ PoolDistributionDialog 适配 BannerPoolEntry（~220行） | 修改 | ~220行 |
| Ph8b | `gui/config_panel.py` ——「保底机制」Tab 增强：删除手写 `pools` 文本框 → 改为「绑定池」勾选表格（~60行） | 修改 | ~60行 |
| Ph8c | `gui/config_panel.py` —— `apply_to_store()`/`set_config()`/`get_config()` Banner 适配 + 移除池子模板 + `_setup_ui()` 注册 Tab | 修改 | ~50行 |
| Ph9 | `tests/test_banner.py` —— 覆盖 lifecycle 全部规则 + 送抽 + step + 新手池 + 向后兼容 | 新建 | ~200行 |

## 四、波及范围

| 文件 | 变更性质 | 量级 |
|------|---------|:---:|
| `core/notifier.py` | **新建** | ~30行 |
| `core/banner.py` | **新建** | ~250行 |
| `core/config_store.py` | 新增 `BannerEntry` / `BannerPoolEntry` / `LifecycleRuleEntry` / `BannerConfig` + `ConfigStore.banner` 字段 | ~50行 |
| `core/pool.py` | **不改** | 0 |
| `core/strategy.py` | `StrategyContext` 新增 `banners` + `all_banners` 字段 | +5行 |
| `service/gacha_service.py` | `current_pools` → `current_banners` + Notifier 集成 | ~40行变更 |
| `service/batch_simulator.py` | `SimulationEnv` 新增 `banner_defs` + `SimulationEnvBuilder` 构建 Banner | ~25行 |
| `config/config_toml.py` | `_build_banners()` + `_wrap_pools_as_banners()` + `[[banner]]` / `[[banner.pool]]` / `[[banner.lifecycle]]` 解析 | ~70行 |
| `gui/config_panel.py` | 「卡池管理」Tab：左列表右详情 + 两子标签页（池/生命周期）+ PoolDistributionDialog 适配 +「保底机制」Tab 增强（绑定池勾选表格替代手写pattern）+ `apply_to_store`/`set_config`/`get_config` 适配 + 移除池子模板 + Tab 注册 | ~350行 |
| `core/gdr.py` | `compute_gdr_from_compact` → 以 banner 为聚合单位 | ~15行 |
| `core/streaming.py` | 聚合提取器支持 banner 维度 | ~15行 |
| `tests/test_banner.py` | **新建** | ~200行 |

**不触及：** `core/pity.py`、`core/state.py`、`core/overflow.py`。现有策略文件（`strategies/builtin/*.py`）仅 `StrategyContext` 字段新增，策略无需修改。

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
         │      订阅 "after_draw" → banner._check_transitions()
         │
         └── P58 M1-8: Milestone 全套
                订阅 "after_draw" → milestone_engine.after_draw()
                （原来的 inline 代码移入订阅函数，逻辑不变）
```

**Ph0 之后，P61 和 P58 完全并行**——各自只改自己的文件（`banner.py` / `milestone.py`），`gacha_service.py` 不再需要改动。

### 5.3 实施顺序

```
第一步：Ph0（core/notifier.py + gacha_service emit）—— ~30 行，半天
    │
    ├── P61 Ph1-9（Banner 全套）
    │       依赖：无。Ph0 交付后即可启。
    │
    └── P58 M1-8（Milestone 全套）
            依赖：无。Ph0 交付后即可启。
```

**不提取独立 P 编号。** Notifier 太小（30 行），不值得单独成计划。P61 Ph0 交付，P58 的 M4 节声明 `depends: P61-Ph0` 即可。

### 5.4 P58 接入 Notifier 的改动

P58 当前在 `gacha_service.py` 的模拟循环中直接 inline 调用（M4，第 422-453 行）：

```python
# P58 当前写法
if _milestone_engine:
    for entry in _milestone_engine.after_draw(pool.id):
        # ... 消费 bonus ...
```

引入 Notifier 后，P58 只需将同一段逻辑**原封不动**移入一个订阅函数：

```python
# P58 模块中 —— 逻辑完全不变
def _on_after_draw(banner_id, pool_id, reward_id, state, collector, ...):
    if _milestone_engine:
        for entry in _milestone_engine.after_draw(pool_id):
            # ... 消费 bonus（与 M4 代码完全相同）...

# gacha_service.py 中 —— 原来的 inline 代码块替换为一行 emit
notifier.emit("after_draw", banner_id=banner.id, pool_id=source.id, ...)
```

**P58 改动量：约 15 行**（把 inline 代码块包进一个订阅函数 + 一行 `subscribe`）。P58 审计完成后的其余全部代码不受影响。

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
| `current_pools` → `banners` 导致现有 8 种策略全部需要适配 | `StrategyContext` 同时保留 `current_pools` 和 `banners` 字段两个版本；策略迁移可选 |
| Banner 内部 source 切换逻辑与 PityEngine 的交互复杂（送抽source排除保底时，保底计数器跨source是否继承） | Banner.draw() 内部显式分两路：`excludes_all_pity` 的 source 完全旁路 `before_draw/after_draw`，不触碰 `pity_state`；正常 source 走完整保底管线 |
| 生命周期规则遗漏边界条件（如送抽source激活时主source恰好也被时间窗口过期关闭） | 规则评估顺序：时间窗口（最先，直接 exhaust banner）→ 转换条件 → 可用性汇总。时间过期的 banner 不进入 `active_banners` |
| `[[banner]]` TOML 解析复杂度——source / lifecycle 嵌套段与现有 `[[pool]]` 格式差异大 | `config_toml.py` 中检测到 `[[banner]]` 段时走新解析路径，`[[pool]]` 段保持现有解析路径不变。两者可共存于同一 TOML |
| 现有 `Pool` 对象缓存和共享引用（schedule_generator 等）与新 Banner 包装层的兼容 | `_wrap_pools_as_banners()` 包装而非替换——原始 Pool 对象保留在 `self._pools` dict 中，Banner 引用 Pool 而非复制 |

## 七、验收标准

**引擎与集成：**
- [ ] 不写 `[[banner]]` 时，现有 `[[pool]]` 行为完全不变（向后兼容）
- [ ] Step 链：3个 pool 的阶梯池按 `pool_draws` 阈值自动切换
- [ ] 送抽插入：main 池30抽后自动激活 free_10pull 池 + 阻塞 main 池；free_10pull 耗尽后自动恢复
- [ ] 保底旁路：`excludes_all_pity` 的 pool 不触发 `before_draw`/`after_draw`，不影响保底计数器
- [ ] 新手池：`max_draws` 达到后 exhaust
- [ ] 一次性 pool：`one_shot=true` 的 pool 消耗后标记 exhausted，不可再抽
- [ ] **已记录、待实现**：`card_obtained` 条件支持稀有度匹配（如 `rarity = "ssr"`），用于终末地新手池「出任意6★即关闭」机制
- [ ] `banner.pending_transitions` 正确暴露「还差X抽触发Y」
- [ ] Notifier 优先级生效：P58（资源注入，priority=0）先于 P61（生命周期检查，priority=1）
- [ ] `StrategyContext` 同时提供 `banners` 和 `current_pools`，现有策略不作任何修改即可运行
- [ ] P58 经 Notifier 订阅后，原 inline 调用逻辑移至订阅函数，其余代码零改动

**ConfigStore：**
- [ ] `BannerEntry` / `BannerPoolEntry` / `LifecycleRuleEntry` / `BannerConfig` dataclass 正确定义
- [ ] `ConfigStore.banner` 字段可用，`ConfigStore.clear()` 重置 `self.banner = BannerConfig()`

**TOML：**
- [ ] `[[banner]]` / `[[banner.pool]]` / `[[banner.pool.reward]]` / `[[banner.lifecycle]]` TOML 段解析正确
- [ ] `[[pool]]` 自动包装为单 pool Banner（无 `[[banner]]` 段时）
- [ ] Banner TOML round-trip 保真——GUI 编辑 → 保存 → 重载后字段不丢失

**UI（ConfigPanel「卡池管理」Tab）：**
- [ ] 左侧 Banner 列表 + 右侧顶部基础字段（QFormLayout，5个字段：name/id/pool_type/max_draws/时间窗口）
- [ ] `id` 为 `QLineEdit`（可编辑），变更时级联更新生命周期和保底中的引用
- [ ] `pool_type` 为 `QComboBox`（角色/武器/常驻/新手/混池/阶梯）
- [ ] 右侧两子标签页：池 / 生命周期
- [ ] 「池」子标签页上半——6 列表格（ID/成本/批次/一次性/不计保底/阻塞主池），内联编辑
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
- [ ] 匹配逻辑同时支持 `{banner_id}.{pool_id}` 格式和旧 `{pool_id}` 格式（向后兼容）
- [ ] 保留现有左列表+右动态表单结构（BEHAVIOR_REGISTRY 驱动）不变

**测试：**
- [ ] `test_banner.py` 覆盖全部 lifecycle 规则 + 集成 + 向后兼容
- [ ] pytest 全量通过
