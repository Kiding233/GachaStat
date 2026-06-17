<!-- META: P58 | module:模拟服务层 | status:designing | last:2026-06-17 -->

# P58 G20 赠送资源机制——acquired 迁移 + 保底追加语义

> 日期：2026-06-17 | 状态：设计中
> 触发：G20 跨游戏核心功能缺口——8 个场景、6 款游戏均需「在正常抽卡产出之上额外注入卡/资源，不吞正常产出」
> 依赖：**不依赖 P55/P56**——基于当前保底架构实施

## 一、问题

### 1.1 G20 缺口全景

手册基建补丁优先级 #1——当前所有 pity type 默认「替换」语义（保底触发时**覆盖**概率分布，吞掉正常抽卡产出），大量游戏需要「追加」语义（在正常产出之上**额外注入**，不吞正常产出）：

| # | 游戏 | 场景 | 触发方式 | 赠送内容 | 当前近似 |
|---|------|------|---------|---------|---------|
| 1 | 火影忍者 | 每 10 抽保底碎片 | `every=10` | 1 片 S/A 碎片 | `hard` 替换语义——**吞卡** |
| 2 | 火影忍者 | 50 抽大保底碎片 | `every=50` | 5 片 S 碎片 | `hard` 替换语义——**吞卡** |
| 3 | 火影忍者 | 首付返利 | `at=100`(S忍) / `at=50`(A忍) | 25-38 片碎片 | 未实现 |
| 4 | 阴阳师 | 40 抽赠送随机 SSR/SP | `at=40` | 随机 SSR/SP，不计入保底 | 未实现 |
| 5 | 明日方舟 | 300 抽赠送当期限定 | `at=300` | 当期限定干员，不计井币 | 未实现 |
| 6 | 终末地 | 30 抽取送十连 | `at=30` | 1 次十连，不计保底 | 附属池 workaround |
| 7 | 终末地 | 60 抽寻访档案 | `at=60` | 10 张下期限定券 | 附属池 workaround |

~~场景 8「异环保底双黄」已于 2026-06-17 交叉验证排除——三测特征，公测移除，见手册 §20.1 更正。~~

**触发方式分类：**
- `at=N`（单次触发）：场景 3/4/5/6/7 —— 5 个
- `every=N`（周期触发）：场景 1/2 —— 2 个

**覆盖策略：** 本计划覆盖全部 7 个场景（均为计数器驱动）。

### 1.2 两个层面的缺失

G20 的阻塞不在一个地方，而在**两层**：

| 层 | 缺失 | 为什么阻塞 |
|----|------|-----------|
| **状态层** | `acquired_counts` 是 `SimulationStats` 局部变量，不是 `GachaState` 的一等公民 | 赠卡无处落地——不知道往哪写、写了无法序列化 |
| **机制层** | 保底只有「替换」语义，没有「追加」语义 | 赠卡无触发入口——`hard` 触发时覆盖概率分布而非旁路注入 |

两层都修好，赠送才是完整可用的。只修一层不够。

---

## 二、目标

### 阶段 A：状态完整性（基础设施）

- `GachaState.acquired: Dict[str, int]` —— 卡牌持有成为一等公民
- `state.add_card()` / `get_card_count()` / `total_holding()` —— 封装操作
- 策略层通过 `ctx.state.acquired` 直接访问
- 序列化包含 `acquired`，快照完整恢复

### 阶段 B：保底追加语义（机制实现）

- 新增 `type = "milestone"` 保底类型——独立的 `MilestoneBehavior(PityBehavior)`，与 `hard` 平级
- 计数器正常递增，`before_draw` 永远透传（不修改概率管道），达阈值后 `after_draw` 返回 bonus 信号
- 引擎层消费 bonus 信号 → `state.add_card()` / `state.gain()`，不触发保底重置、不产生副产物
- TOML 配置支持 `threshold` / `repeat` / `max_triggers` / `bonus_reward` 等字段
- 覆盖 `at=N` + `every=N` 全部 7 个计数器驱动场景

### 非目标

- 事件驱动型赠送（异环保底双黄、幻塔歪后铸金）——依赖 P56 `RotatingBehavior` + `did_fire()` 声明式依赖传播
- 赠送走 `Pool.draw()` 管线——不走。bonus 是直入库存，不触发保底、不产生副产物
- 合并 `resources` 和 `acquired` 为统一 inventory——已决议不合并（操作语义不同）

---

## 三、方案

### 3.1 阶段 A —— GachaState 状态完整性

#### 3.1.1 核心设计

```python
@dataclass
class GachaState:
    resources: Dict[str, float] = field(default_factory=dict)
    acquired: Dict[str, int] = field(default_factory=dict)    # ← 新增——卡牌持有
    pity_counters: Dict[str, int] = field(default_factory=dict)
    real_time: float = 0.0
    total_actions: int = 0
    extra_state: Dict[str, Any] = field(default_factory=dict)

    # ── 现有方法不变 ──
    def can_afford(self, cost) -> bool: ...
    def spend(self, cost) -> Optional[CostOption]: ...
    def gain(self, gains: Dict[str, float]): ...
    def can_afford_batch(self, cost, batch_size: int) -> bool: ...
    def clone(self) -> 'GachaState': ...

    # ── 新增：卡牌持有操作 ──
    def add_card(self, card_id: str) -> int:
        """抽到/赠送一张卡。返回新增后的持有数量。"""
        self.acquired[card_id] = self.acquired.get(card_id, 0) + 1
        return self.acquired[card_id]

    def get_card_count(self, card_id: str) -> int:
        """模拟中获得的该卡数量（不含初始持有）。"""
        return self.acquired.get(card_id, 0)

    def total_holding(self, card_id: str, initial_counts: Dict[str, int]) -> int:
        """含初始持有的总数量。"""
        return initial_counts.get(card_id, 0) + self.acquired.get(card_id, 0)
```

**字段语义：** `acquired` 只记录模拟过程中获得的卡。`CardDefEntry.initial_count` 是配置常量，不写入——由 `total_holding()` 做加法。

#### 3.1.2 gacha_service 适配

**stats.on_draw → state.add_card：**

```python
# 统计维度（保持在 stats）
stats.on_draw(reward.id, pool.id, pity_triggered)
# 状态维度（新增——写入 state）
if reward.id != _NO_CARD_ID:
    state.add_card(reward.id)
```

`SimulationStats.on_draw` 中移除 `acquired_counts` 更新逻辑，只保留 `card_counts` / `pool_draw_counts` / `total_draws`。

**bonus 计算简化：**

```python
# 时序：先算 bonus，再 add_card（因为 total_after 需要预判）
if reward.id != _NO_CARD_ID:
    total_before = state.total_holding(reward.id, _initial_counts)
    total_after = total_before + 1
    bonus = compute_bonus_resources(reward, total_before, total_after)
    state.add_card(reward.id)
```

**StrategyContext 向后兼容：**

```python
@dataclass
class StrategyContext:
    state: 'GachaState'
    ...
    @property
    def acquired(self) -> Dict[str, int]:
        return self.state.acquired
```

#### 3.1.3 波及适配

| 文件 | 改动 |
|------|------|
| `core/state.py` | `acquired` 字段 + 3 方法 + `to_dict`/`from_dict`/`clone` |
| `service/gacha_service.py` | `state.add_card()` 替代 `stats.acquired_counts`；bonus 计算简化；`_initial_counts` 仅保留配置提取 |
| `core/strategy.py` | `StrategyContext.acquired` → property 代理 |
| `core/stop_condition.py` | `TargetAcquiredCondition` → `state.acquired` |
| `core/collector.py` | `card_counts` 保持不变（统计维度 ≠ 状态维度） |

### 3.2 阶段 B —— 新增 `milestone` 保底类型

**设计决策：独立 type，不给 `hard` 打补丁。** `hard` 的职责是「强制出卡」（覆盖概率分布），`milestone` 的职责是「达阈值后额外注入」（不碰概率）。两者行为完全不同——用一个 `mode` 参数切换违反 P55 的「行为独立化」原则。

**实施前提：P55 基础设施就绪后，继承 `CounterBasedBehavior`。** 当前阶段 A 不依赖 P55，阶段 B 等待 P55 完成后实施——届时 `MilestoneBehavior` 只需覆写 `_compute_probabilities()`（透传）和 `after_draw()`（达阈值注入），计数器生命周期由基类统一管理。

#### 3.2.1 `scope` 和 `pools` 语义

| 参数 | milestone 的语义 | 与 `hard`/`soft` 的差异 |
|------|------|------|
| `pools` | **完全相同**——计数器只在绑定池子的抽卡中递增。`pools = ["limited_pool"]` 则仅统计该池抽数 | 无差异 |
| `scope` | **仅用于执行顺序排序**，不操作概率分布。必须为 `[rarities]` 中注册的稀有度名，默认取绑定池子的最高稀有度。计数器统计**所有抽卡**（不限稀有度）——`scope="ssr"` 不代表「只计 SSR 出货」，只代表「排序时和 SSR 级保底同组」 | `hard`/`soft` 用 scope 决定操作哪个稀有度的概率槽位；milestone 不操作概率，scope 退化为排序标记 |

**为什么 scope 不控制「统计哪些抽卡」：** milestone 的计数器是纯粹的池子抽数——抽第 1 抽 +1，抽第 40 抽触发，不问中间出了什么。如果 scope 控制统计范围（如「只计 SSR 出货」），那它就不是里程碑奖励而是稀有度事件计数器，属于另一个 type 的职责。

**scope 校验依赖 `[rarities]`：** milestone 的 `scope` 必须在 `[rarities]` 中注册——这是 P55 Phase 10 提取的微型任务可提前交付的动机之一。`[rarities]` 提早实施后，milestone 的 scope 校验即可使用统一的稀有度名称注册表。详见 P55 §3.13「可提前提取的微型任务」。

#### 3.2.2 `MilestoneBehavior(CounterBasedBehavior)` —— P55 之后的实现

```python
# core/pity.py —— P55 基础设施就绪后

class MilestoneBehavior(CounterBasedBehavior):
    """计数器驱动的里程碑赠送保底。
    
    继承 CounterBasedBehavior——计数器递增/上限停用由基类统一管理。
    子类只写两件事：概率永远透传 + 达阈值后注入 bonus。
    
    与 hard 的核心区别：
      - hard:  _compute_probabilities 覆盖概率 → pool.draw() 必出目标卡
      - milestone: _compute_probabilities 透传 → pool.draw() 正常随机
                   → after_draw 达阈值 → 返回 bonus 信号
    """

    def __init__(self, name, state, scope,
                 threshold: int,
                 bonus_reward: dict,
                 repeat: bool = False,              # False=at=N / True=every=N
                 **kwargs):                          # LifecycleConfig 等透传基类
        super().__init__(name, state, scope, reset="never", **kwargs)
        self._threshold = threshold
        self._bonus_reward = bonus_reward
        self._repeat = repeat
        # bonus_reward 结构:
        #   {"type": "card", "card_id": "xxx"}
        #   {"type": "resource", "resource_id": "y", "amount": 10}
        #   {"type": "random_card", "candidates": [...], "weights": [...]}

    # ── 概率：永远透传 ──
    def _compute_probabilities(self, ctx, counter):
        return ctx.current.copy()

    # ── 生命周期：基类 before_draw 已处理计数器递增 + _active 检查 ──
    # ── 只需覆写 after_draw：达阈值 → 发射 bonus → 管理计数器状态 ──
    def after_draw(self, ctx):
        if not self._active.is_set():
            return None
        if self._counter.value() < self._threshold:
            return None

        # 基类 after_draw 处理 max_triggers（_should_reset 返回 False 所以不会走基类重置路径）
        bonus = self._resolve_bonus()

        if self._repeat:
            self._counter.reset()          # every=N：重置继续
        else:
            self._active.clear()           # at=N：永久停用

        # 基类的 max_triggers 检查在 after_draw 中——此处触发了，基类 trunc 计数器归它管
        super().after_draw(ctx)            # 处理 max_triggers 耗尽停用
        return bonus                       # 引擎层消费

    def _resolve_bonus(self):
        """根据 bonus_reward 类型解析具体奖励。"""
        br = self._bonus_reward
        if br["type"] == "card":
            return {"card_id": br["card_id"]}
        elif br["type"] == "resource":
            return {"resources": {br["resource_id"]: br.get("amount", 1)}}
        elif br["type"] == "random_card":
            import random
            chosen = random.choices(
                br["candidates"],
                weights=br.get("weights", [1.0] * len(br["candidates"])),
                k=1
            )[0]
            return {"card_id": chosen}
        return None
```

**~35 行。** 对比直接继承 `PityBehavior` 的版本（~60 行），计数器管理（`Counter`/`Flag`/`_active`/`max_triggers`）全部由 `CounterBasedBehavior` 基类处理，子类只写业务逻辑。**这是 P55 平台层（Phase 1-4）最直接的简化乘数效应——25 行计数器样板代码被继承替代。**

**与 P56 的并行关系：** MilestoneBehavior（计数器驱动）与 RotatingBehavior/TargetedBehavior（事件驱动）互不依赖——两者共享 P55 平台层但可并行开发。P55 Phase 1-4 完成后即可同时启动 P56 和 P58B。

**继承来的能力（零代码）：**

| 能力 | 来源 |
|------|------|
| 计数器递增 + 查询 | `CounterBasedBehavior.before_draw` → `self._counter.incr()` |
| `_active` 停用后跳过 | `CounterBasedBehavior.before_draw` 开头检查 |
| `max_triggers` 耗尽停用 | `CounterBasedBehavior.after_draw` → `self._active.clear()` |
| 序列化（计数器/triggers/_active） | `PityState` namespace 自动兼容 |
| 执行顺序自动推导 | `_resolve_order()` 按 scope 稀有度 rank 排序 |

#### 3.2.2 和 `hard` 的对比

| | `hard` | `milestone` |
|---|---|---|
| `before_draw` | 达阈值 → 概率 100% 强制出卡 | **透传**——不修改概率 |
| `after_draw` | 出目标稀有度 → 重置计数器 | 达阈值 → 注入 bonus → 重置或停用 |
| 正常抽卡结果 | 被覆盖 | **照常产出** |
| 保底计数器 | 不受 bonus 影响 | **不影响**其他保底 |
| 副产物（星辉等） | 照常计算 | **不产生** |
| `repeat` | 不适用 | `false`=at=N 一次性 / `true`=every=N 周期 |

#### 3.2.3 配置语法

```toml
# ── at=N —— 40 抽赠送随机 SSR，仅一次 ──
[[pity]]
type = "milestone"
name = "onmyoji_40_gift"
threshold = 40
repeat = false
max_triggers = 1
bonus_reward = { type = "random_card", candidates = [
    "ssr_ibaraki", "ssr_shuten", "ssr_oomoji", "ssr_kaguya",
], weights = [1.0, 1.0, 1.0, 1.0] }

# ── every=N —— 每 10 抽保底碎片，无限重复 ──
[[pity]]
type = "milestone"
name = "naruto_fragment"
threshold = 10
repeat = true
bonus_reward = { type = "resource", resource_id = "fragment_s", amount = 1 }

# ── at=N —— 300 抽赠送指定卡 ──
[[pity]]
type = "milestone"
name = "ak_300_gift"
threshold = 300
repeat = false
max_triggers = 1
bonus_reward = { type = "card", card_id = "limited_operator" }

# ── at=N —— 60 抽送跨期券 ──
[[pity]]
type = "milestone"
name = "endfield_archive"
threshold = 60
repeat = false
max_triggers = 1
bonus_reward = { type = "resource", resource_id = "endfield_next_voucher", amount = 10 }
```

#### 3.2.4 gacha_service bonus 注入分支

在 `after_draw` 之后、资源结算之前插入。`MilestoneBehavior` 自己管理计数器生命周期（递增/重置/停用），引擎只负责消费它返回的 bonus 信号：

```python
# gacha_service.py —— 在 after_draw 和资源结算之间
# ── 【新增】milestone 注入 ──
if _pity_engine:
    spec = _pity_engine.get_spec(pool.id)
    if spec:
        for pname in spec.pity_names:
            behavior = _pity_engine.behaviors.get(pname)
            if not isinstance(behavior, MilestoneBehavior):
                continue
            bonus = behavior.after_draw_behavior(ctx)
            if bonus is None:
                continue
            # ── 消费 bonus 信号 ──
            bonus_card_id = None
            bonus_resources = {}
            if 'card_id' in bonus:
                bonus_card_id = bonus['card_id']
                state.add_card(bonus_card_id)
            if 'resources' in bonus:
                bonus_resources = bonus['resources']
                for k, v in bonus_resources.items():
                    resources[k] = resources.get(k, 0) + v
            # ── 记录为赠送（非抽得）──
            collector.on_bonus(
                pname, bonus_card_id, bonus_resources,
                real_time=real_time,
            )
```

**关键时序：**

```
before_draw → MilestoneBehavior.before_draw_behavior (计数器+1)
  → pool.draw() → 正常出卡
  → after_draw → 常规保底重置（hard/soft 等，不涉及 milestone）
  → [新增] MilestoneBehavior.after_draw_behavior → 达阈值 → 返回 bonus
  → state.add_card() / state.gain() ← 注入，不碰保底
  → 资源结算（正常 reward.resources_gained + compute_bonus_resources）
  → collector
```

#### 3.2.5 collector 新增 `on_bonus` 事件

```python
# collector.py
class SimulationCollector(ABC):
    def on_bonus(self, pity_name: str, card_id: Optional[str],
                 resources: Dict[str, float], real_time: float):
        """milestone 注入事件——区分「抽得」和「赠得」."""

# CompactCollector
def on_bonus(self, ...):
    r = self._result
    r.bonus_events.append({...})   # 新增字段
```

分析面板据此区分两类来源——赠送的卡不出现在出率计算中。

#### 3.2.6 TOML 解析适配

`config_toml.py._build_pity()` 解析 `type = "milestone"` 的专属字段：

```toml
[[pity]]
type = "milestone"
name = "..."
threshold = 40
repeat = false                     # false=at=N, true=every=N
max_triggers = 1                   # 0=无限
bonus_reward = { type = "...", ... }
```

`PityDefParsed` 增加对应字段。`BEHAVIOR_REGISTRY` 注册 `milestone` 条目（对齐 P55 的 Registry 模式，当前可先在 `create_behavior` 工厂中硬编码路由，P55 后迁移至 Registry）。

### 3.3 实施阶段

| 阶段 | 内容 | 文件 | 预估行数 |
|:---:|------|------|:---:|
| A1 | `GachaState` 新增 `acquired` + 3 方法 + `to_dict`/`from_dict`/`clone` | `core/state.py` | ~40 |
| A2 | `gacha_service`——`state.add_card()` 替代 `stats.acquired_counts`；bonus 计算简化 | `service/gacha_service.py` | ~20 |
| A3 | `SimulationStats` 移除 `acquired_counts`；`StrategyContext.acquired` → property | `gacha_service.py` + `strategy.py` | ~10 |
| A4 | `TargetAcquiredCondition` → `state.acquired` | `stop_condition.py` | ~5 |
| A5 | 阶段 A 测试（序列化往返 + `add_card`/`total_holding` 单元） | `tests/` | ~30 |
| **A 合计** | | | **~105** |
| B1 | `MilestoneBehavior(CounterBasedBehavior)` 实现——覆写 `_compute_probabilities`（透传）+ `after_draw`（达阈值注入） | `core/pity.py` | ~35 |
| B2 | `PityEngine` 管道适配——`after_draw` 中消费 milestone 返回的 bonus 信号 | `core/pity.py` | ~10 |
| B3 | `PityDefParsed` + `config_toml.py._build_pity()` 解析 `type="milestone"` 专属字段 | `config_store.py` + `config_toml.py` | ~15 |
| B4 | `gacha_service` bonus 注入分支——检测 → 选卡/资源 → `state.add_card()` / `state.gain()` → `collector.on_bonus()` | `gacha_service.py` | ~35 |
| B5 | `collector` 新增 `on_bonus` 事件 + `CompactResult.bonus_events` 字段 | `collector.py` + `result_types.py` | ~15 |
| B6 | TOML 解析也修复阶段 A 中发现的 `resources_gained`/bonus 字段遗漏（顺带） | `config_toml.py` | ~10 |
| B7 | 阶段 B 集成测试（7 个 G20 场景的 TOML 配置 → 模拟 → 验证产出） | `tests/` | ~50 |
| **B 合计** | | | **~150** |
| **总计** | | | **~255** |

### 3.4 配置面板 UI（后续）

`config_panel.py` 在保底配置区域增加：
- `type` 下拉新增「里程碑赠送」选项
- `bonus_reward` 子面板（类型选择 + 参数编辑）
- `repeat` 复选框（一次性 / 周期重复）

此部分可与 B 阶段并行或后置，不影响核心管线。

---

## 四、依赖关系

### 4.1 本计划的依赖

```
本计划（P58）
│
├─ 阶段 A (P58a): acquired 迁移
│   依赖: 无
│   交付: state.add_card() / state.total_holding() / 序列化
│
├─ 阶段 B (P58b): type="milestone" + bonus 注入
│   依赖: 阶段 A（需要 state.add_card() 落脚点）
│         P55 Phase 1-4（PityState + CounterBasedBehavior + BEHAVIOR_REGISTRY）
│         不依赖 P56（milestone 与 rotating/targeted 互不依赖）
│   覆盖: 全部 7 个 G20 场景（均为计数器驱动）
│
└─ 无需事件驱动型赠送: ~~异环保底双黄已排除~~（公测移除）
```

### 4.2 本计划对其他计划的简化效应（乘数效应）

P58 阶段 A 是**最高杠杆的基础设施**——改动量小（~105 行），但为多个后续计划提供关键简化：

| 被简化方 | 简化点 | 效应 | 量级 |
|---------|------|------|:---:|
| **P41** | `instance_index` 推导——`state.acquired.get(card_id, 0)` 替代局部 `instance_counter` 递减维护 | 消灭两本账（`card_counts` ↔ `instance_counter`），一份数据两种读法 | ~15行 |
| **P41** | `WeightEvalContext.acquired` 来源统一——事后 GDR 和运行时流式分析都读 `state.acquired`，而非分别从 `compact.card_counts` 和 `SimulationStats.acquired_counts` 取 | 单一真相源——消除两处数据源潜在的不一致 bug | ~10行 |
| **P58B** | `state.add_card()` 为 milestone bonus 卡提供落脚点——无此方法则 bonus 注入无处可写（`SimulationStats` 在错误层） | 架构必须——无 P58A 则 P58B 不可实现 | 架构级 |
| **stop conditions** | `TargetAcquiredCondition` 从 `state.acquired` 直读——不需要间接查 `SimulationStats` | 依赖方向正确（条件→状态，而非条件→统计） | ~5行 |
| **策略层** | `StrategyContext.acquired` 退化为 property 代理——`return self.state.acquired` | 消除策略层对统计层的耦合 | ~5行 |

**核心原则：** `acquired` 是模拟状态（玩家持有），不是统计数据（汇总报表）。迁入 `GachaState` 后，所有消费者（策略、停止条件、GDR、bonus 注入）共享同一真相源。

### 4.3 为何 P58B 不等 P56

全部 7 个 G20 场景都是计数器驱动的——不需要 P56 的事件驱动机制。P56 解决的是轮换保底和定轨（歪→大保底），而 G20 的里程碑赠送是「抽到第 N 抽给东西」——纯计数器逻辑，P55 的 `CounterBasedBehavior` 完全覆盖。

---

## 五、波及范围

| 文件 | 阶段 | 改动类型 | 说明 |
|------|:---:|---------|------|
| `core/state.py` | A | **修改** | `acquired` 字段 + 3 方法 + 序列化 |
| `service/gacha_service.py` | A+B | **修改** | A: `state.add_card()` 替代 `stats.acquired_counts`；B: bonus 注入分支 |
| `core/strategy.py` | A | **小改** | `StrategyContext.acquired` → property |
| `core/stop_condition.py` | A | **小改** | `TargetAcquiredCondition` → `state.acquired` |
| `core/pity.py` | B | **修改** | 新增 `MilestoneBehavior` 类；`PityEngine` 管道调度适配 |
| `core/config_store.py` | B | **小改** | `PityDefParsed` 新增 milestone 专属字段 |
| `core/config_toml.py` | B | **修改** | `_build_pity()` 解析 `type="milestone"` 和 `bonus_reward`；顺带修 `resources_gained` 解析遗漏 |
| `core/collector.py` | B | **修改** | 新增 `on_bonus` 事件 |
| `core/result_types.py` | B | **小改** | `CompactResult` 新增 `bonus_events` 字段 |
| `tests/` | A+B | **新增** | ~80 行测试 |
| `gui/config_panel.py` | 后置 | **修改** | `mode`/`bonus_reward` UI 控件 |
| `service/batch_simulator.py` | — | 检查 | 确认无 break |

**不受影响：** `core/pool.py`（池子抽卡不感知 mode）、`gui/` 分析面板（通过 collector 隔离赠送事件）

---

## 六、风险

| 风险 | 缓解 |
|------|------|
| `SimulationStats.acquired_counts` 移除后外部引用遗漏 | 全局 grep `acquired_counts` 确认无残留 |
| 旧序列化快照（无 `acquired`）反序列化失败 | `from_dict` 中 `d.get('acquired', {})` |
| `card_counts`（含 `_no_card`）与 `acquired`（不含）语义混淆 | 文档注释 + `total_holding()` 统一入口 |
| 策略子类中 `ctx.acquired` 引用 | property 代理保留向后兼容 |
| `milestone` 计数器生命周期（`repeat`=true 重置继续 vs false 停用）与常规保底不同 | `MilestoneBehavior` 自管——`after_draw_behavior` 中根据 `repeat` 决定重置或停用 |
| bonus 注入时序不当（早于/晚于保底重置导致状态不一致） | 时序固定：`after_draw` → bonus 注入 → 资源结算 → collector |
| TOML 中 `resources_gained`/bonus 字段从未被解析——历史遗漏可能引发其他 bug | B6 步骤顺带修复 |

---

## 七、验收标准

### 阶段 A

- [ ] `GachaState.acquired` 序列化往返无损（`to_dict()` → `from_dict()`）
- [ ] `state.add_card("diluc")` 正确递增；`state.get_card_count("diluc")` 返回正确值
- [ ] `state.total_holding("diluc", {"diluc": 3})` = `3 + acquired`
- [ ] `state.clone()` 含 `acquired` 副本，修改克隆不影响原对象
- [ ] bonus 计算（`first_time` / `nth_time` / `excess`）结果与迁移前一致
- [ ] `StrategyContext` 中 `acquired` 可通过 `ctx.acquired` 或 `ctx.state.acquired` 访问
- [ ] `TargetAcquiredCondition` 正确基于 `state.acquired` 判定
- [ ] 旧序列化快照（无 `acquired` 字段）反序列化不报错
- [ ] `SimulationStats` 中 `acquired_counts` 已完全移除

### 阶段 B

- [ ] `type="milestone"` + `bonus_reward.type="card"`——计数器达阈值后 `state.acquired[card_id] += 1`，不修改概率分布
- [ ] `type="milestone"` + `bonus_reward.type="resource"`——计数器达阈值后 `state.resources[rid] += amount`
- [ ] `type="milestone"` + `bonus_reward.type="random_card"`——计数器达阈值后从候选集加权随机选卡，直入 `state.acquired`
- [ ] `repeat=false`（at=N）：触发一次后永久停用，计数器不复位
- [ ] `repeat=true`（every=N）：触发后计数器归零继续计数，下一轮继续触发
- [ ] bonus 注入不触发常规保底重置（`hard`/`soft` 计数器不受 milestone 影响）
- [ ] bonus 注入不产生副产物（不走 `compute_bonus_resources`）
- [ ] `collector.on_bonus()` 正确记录——赠送卡不出现在 `card_counts` 的抽卡统计中
- [ ] `max_triggers` 正确限制触发次数——达上限后 `_active.clear()` 永久停用
- [ ] `config_toml._build_pools()` 正确解析 `resources_gained` / `first_time_bonus` / `nth_time_bonus` / `excess_bonus`（顺带修复）
- [ ] 7 个 G20 场景的 TOML 配置 → 模拟 → 产出验证通过
- [ ] pytest 全量通过
