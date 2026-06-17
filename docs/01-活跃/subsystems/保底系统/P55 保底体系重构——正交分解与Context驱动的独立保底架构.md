<!-- META: P55 | module:保底系统 | status:designing | last:2026-06-17 -->

# P55 保底体系重构——正交分解与 Context 驱动的独立保底架构

> 日期：2026-06-15 | 状态：设计中
> 触发：用户请求「会歪型软保底」（全体 SSR 每抽固定增量）+ 讨论中自然延伸至保底体系整体重构

## 一、问题

### 1.1 当前局限

当前保底体系（`core/pity.py`）存在五个结构性问题：

| # | 问题 | 影响 |
|---|------|------|
| 1 | `type = "soft"` 硬编码「增量只给 featured、比例爬升」——两种正交维度被耦合 | 无法表达「增量给全体 SSR」的保底 |
| 2 | 增量逻辑单一（仅比例再分配 `new = target + progress × other`），不支持固定百分点累加 | 无法模拟每抽固定增量型软保底 |
| 3 | `PityEngine.after_draw()` 硬编码 `is_ssr` 判定，生命周期逻辑外泄在引擎层 | 每加一个新保底类型就要改引擎；无法表达 SR/R 保底 |
| 4 | `PityState` 预设字段类型（仅 `counters: Dict[str, int]`），每加一种状态维度就要改数据结构 | 无法存储布尔标志、触发次数、per-banner 隔离计数——新增保底类型需要同时改 `PityState` 定义 |
| 5 | 保底行为的生命周期被 `PityEngine` 和 `PityBehavior` 割裂——`apply()` 在 behavior，`after_draw()` 在引擎 | 新增保底类型的改动散落两处，违背开闭原则 |

### 1.2 讨论结论（本次会话）

- **两个正交维度**：累加方式（怎么加）× 作用范围（加给谁）→ `type` × `scope`
- **五种基础 type**：三种 counter 驱动（`soft_interval` / `soft_additive` / `hard`）+ 两种事件驱动（`rotating` / `targeted`）——事件驱动型不改变 SSR 总出率，只重分配 featured/非featured 内部比例；`rotating` 无锁定目标，`targeted` 有 selected_card + 命定值累积
- **统一 `scope` 参数**：作用于稀有度级别（`ssr` / `sr` / `r` 等，必须已在 `[rarities]` 注册），`target_featured` 布尔字段独立控制是否限定 featured 子集
- **行为独立化**：每个 `PityBehavior` 自管完整生命周期（概率调整 + 状态更新），引擎退化为纯调度器，对齐策略系统的 Context 注入模式
- **状态抽象化**：`PityState` 不预设字段类型——每个 behavior 以自身 `name` 为 namespace 存取任意类型数据
- **DrawInfo 拆分**：`PityContext` 拆为两层——`DrawInfo`（不可变静态事实，`frozen=True`）+ 可变载体（`current` / `state`），类型系统强制执行可变/不可变边界
- **Registry 模式**：`BEHAVIOR_REGISTRY` 一张表消除 if-else——含每个 type 的参数元数据（对齐策略 `STRATEGY_REGISTRY.params`），新增保底类型 = 写类 + 注册一行 + 写元数据 + 配 TOML
- **参数元数据驱动**：对齐策略系统的 `STRATEGY_REGISTRY.params` 模式——`BEHAVIOR_REGISTRY` 中声明每个 type 的参数元数据（`type` / `display_name` / `default` / `min` / `max`），config panel 据此渲染 UI 控件 + 就地校验。不需 params dataclass——TOML 解析后类型已是正确的（`int`/`float`/`str`），无类型转换需求
- **Counter / Flag 微抽象**：`Counter`（遥控器模式）+ `Flag`（布尔标志遥控器），消除字符串 key 散落
- **CounterBasedBehavior**：计数器驱动型保底的可选基类——统一计数器生命周期、子类只实现 `_compute_probabilities(ctx, counter)`
- **LifecycleConfig**：跨 type 共享的生命周期参数 dataclass——`max_triggers`（触发上限）+ P56 扩展 `deactivate_on_early_hit` / `depends_on`
- **执行顺序自动推导**：不再使用 `priority` 数字——基于 type 分类（概率增加/强制出卡）+ scope 层级（稀有度高低 + 重叠关系）自动推导执行顺序；校验分级（ConfigError / warn / 通过）
- **稀有度层级保护**：低稀有度保底绝不降低高稀有度概率——`scope=sr` 只从 R 取概率，不动 SSR
- **七大支柱**：`type × scope 正交` + `行为独立化` + `状态抽象化` + `DrawInfo 拆分` + `Registry` + `CounterBasedBehavior` + `执行顺序自动推导` → 配置者无需手写排序数字
- **YAGNI 移除**：`increment_step`（计数器加速）· `reset_min_counter`（前 N 抽不重置）· `persistence`（计数器跨池继承——由 `pools` 配置推导，无需独立参数）——调研 12 款游戏无实际用例
- **rotating（轮换保底）**：事件驱动的基础 type——P55 注册 stub + 执行顺序支持，P56 完整实现
- **targeted（定向保底/定轨）**：事件驱动的基础 type——独立于 rotating，P55 注册 stub + 执行顺序支持，P56 完整实现（含 selected_card 运行时设定 + 命定值累积 + 切换规则）

## 二、目标

### 2.1 核心交付

| # | 交付 | 说明 |
|---|------|------|
| 1 | **行为独立化** | `PityBehavior` 自管完整生命周期；`PityEngine` 退化为调度器 |
| 2 | **`PityContext` + `DrawInfo`** | `DrawInfo`（`frozen=True`，静态事实）+ `PityContext`（可变载体：`current` / `state`），类型系统强制执行可变/不可变边界 |
| 3 | **`BEHAVIOR_REGISTRY`** | 消除 if-else——含 type→类 + 参数元数据（对齐 `STRATEGY_REGISTRY`）；新增保底类型 = 写类 + 注册一段元数据 |
| 4 | **参数元数据驱动** | `BEHAVIOR_REGISTRY` 中含各 type 的参数元数据（`type` / `display_name` / `default`），对齐策略系统——config panel 据此渲染 UI + 校验，不引入 params dataclass |
| 5 | **`Counter` / `Flag` 微抽象** | 遥控器模式——`Counter(state, name)` 封装 `incr()`/`value()`/`reset()`/`reached()`；`Flag` 同理 |
| 6 | **`CounterBasedBehavior`** | 计数器驱动型保底可选基类——统一计数器生命周期，子类只实现 `_compute_probabilities()` |
| 7 | `type = "soft_additive"` | 每抽固定百分点累加，`scope` 决定加给谁 |
| 8 | `type = "soft_interval"` | 区间比例爬升，进度驱动概率从「非目标」向目标转移 |
| 9 | `scope` 参数 | 三 type 共享：`featured` / `ssr` / `sr` / `r` |
| 10 | **`PityState` 抽象化** | 三层嵌套 namespace：`{behavior_name: {key: value}}`；`get()`/`set()`/`incr()` 接口 |
| 11 | **`LifecycleConfig`** | 跨 type 共享的生命周期参数 dataclass：`max_triggers`（C3）+ P56 扩展 `deactivate_on_early_hit` / `depends_on` |
| 12 | **执行顺序自动推导** | 基于 type 分类（概率增加/强制出卡）+ scope 层级关系自动排序；校验分级（ConfigError / warn / 通过） |

### 2.2 非目标

- `rotating` 事件驱动行为的完整实现（P56）——P55 仅确保基础设施（`PityState` / `Flag` / 跨 behavior 读取）支持
- `scope` 扩展为自定义卡组（`card_group` 定义）——当前稀有度级别足够
- Box 制 / 阶梯池 / 天井 / 不重复保底 —— 不属于保底引擎职责范围
- **捕获明光 —— `loss_streak` type（应实现、待讨论方案）。** 2026-06-17 更正：初版错误归类为 rotating 软变体。实际是 4 状态连歪计数器（0→1→2→3→触发），rotating 是 2 状态机，无法互相建模。实现方向：独立 `loss_streak` behavior——追踪 rotating 的连续失败事件，threshold=3 时 force_win。具体方案待讨论（是否内嵌到 rotating / 独立 type / 事件回调）。手册 G17

## 三、方案

### 3.1 架构核心：行为独立化

**设计哲学：** 对齐策略系统——`PityEngine` 只负责调度，每个 `PityBehavior` 拿到 `PityContext` 后自己决定一切。

```
当前（割裂）：
  PityEngine.before_draw() → increment → get_probabilities() → behavior.apply()
  PityEngine.after_draw()  → [引擎层硬编码] 检查 rarity → reset

重构后（独立化）：
  PityEngine.before_draw() → 构建 PityContext → foreach behavior: behavior.before_draw(ctx)
  PityEngine.after_draw()  → 构建 PityContext → foreach behavior: behavior.after_draw(ctx)
```

#### PityContext 设计：DrawInfo 拆分

**设计哲学：** 将「不变的静态事实」与「管道中流转的可变状态」拆为两层，类型系统强制执行可变/不可变边界。

```
@dataclass(frozen=True)                    # ← frozen：不可变
class DrawInfo:
    """抽卡上下文中不变的部分——本次抽卡的静态事实。"""
    pool_id: str
    pool_instance_id: str                  # per-banner 计数器隔离（A2）
    reward_id: str
    reward_rarity: str                     # "ssr" | "sr" | "r"
    is_featured: bool
    scope_cards: Mapping[str, tuple[str, ...]]    # rarity → 具体卡牌 ID
    scope_slots: Mapping[str, tuple[str, ...]]    # rarity → 模板槽位 ID
    featured_slots: Mapping[str, tuple[str, ...]] # rarity → 标记 featured=true 的槽位 ID
    base_probabilities: Mapping[str, float]       # 槽位 ID → 基础概率
    rarity_rank: Mapping[str, int]                # rarity → 层级（0=最高），由 [rarities] 生成

@dataclass
class PityContext:
    """管道中流转的可变载体。"""
    draw: DrawInfo                         # 不可变——只读
    current: Dict[str, float]              # 当前管道概率——随 behavior 依次修改
    state: PityState                       # 状态引用——behavior 通过 set/incr 写入
```

**key 语义说明：**
- `scope_cards["ssr"]` = `("limited_ssr_1", "standard_ssr_1", ...)`——具体卡牌，用于判断 reward 属于哪个稀有度
- `scope_slots["ssr"]` = `("ssr", "ssr_alt")`——模板槽位，用于从 `base_probabilities` 中累加概率
- `featured_slots["ssr"]` = `("ssr",)`——其中标记了 `featured=true` 的槽位，用于 rotating 重分配 featured/非featured 内部比例
- `base_probabilities["ssr"]` = `0.2`——模板槽位的基础概率
- `rarity_rank["ssr"]` = `0`——由 `[rarities]` 生成，用于稀有度层级保护（低 rank 不从高 rank 取概率）

**收益：**
- `ctx.draw.base_probabilities` 是 `Mapping`，不可写——误写编译报错
- `ctx.draw` 是 `frozen`——不可整体重新赋值
- 测试中 `DrawInfo` 可独立构造 + 跨用例复用
- 接口即文档：`before_draw(self, ctx)` → 只能读 `ctx.draw`、写 `ctx.current`

#### PityState 抽象化

**设计哲学：** 不预设字段类型——`PityState` 是一个以 `{behavior_name: {key: value}}` 为内部结构的三层嵌套 namespace 容器。behavior 自己决定存取什么、怎么解释，引擎不知道内部结构。

```
class PityState:
    """每个 behavior 通过自身 name 作为顶级 namespace 存取任意键值对。"""

    def get(self, name: str, key: str, default=None):
        return self._data.get(name, {}).get(key, default)

    def set(self, name: str, key: str, value):
        self._data.setdefault(name, {})[key] = value

    def incr(self, name: str, key: str, delta=1) -> int:
        v = self.get(name, key, 0) + delta
        self.set(name, key, v)
        return v

    def to_dict(self) -> dict:
        return {"data": self._data}

    @classmethod
    def from_dict(cls, d: dict) -> "PityState":
        ps = cls()
        ps._data = d.get("data", {})
        return ps
```

**对比：**

| | 旧 PityState（预设字段） | 新 PityState（抽象 namespace） |
|---|---|---|
| 结构 | `counters: Dict[str, int]` | `_data: Dict[str, Dict[str, Any]]` |
| 加新状态维度 | 修改 `PityState` 定义 → 改引擎 → 改序列化 | behavior 内部 `state.set(name, "新key", val)` |
| 扩展现有 behavior | 可能影响其他 behavior 的序列化 | 无影响——namespace 隔离 |
| 示例 | `state.counters["ssr_soft"] = 5` | `state.incr("ssr_soft", "counter")` |
| 轮换保底 | 需加 `flags: Dict[str, bool]` | `state.set("rotating", "guaranteed", True)` |
| 定轨 | 需加 `fate_points: Dict[str, int]` | `state.incr("epitomized", "fate_points")` |
| 终末地 per-banner | 需加 `scoped_counters: Dict[str, Dict[str, int]]` | `state.incr("ssr_hard", f"counter_{pool_instance_id}")` |

#### 完整数据流

```
                         ┌──────────────────────────────────────────────┐
                         │              PityEngine（调度器）              │
                         │                                              │
  pool_id ──────────────→│  1. 构建 PityContext                         │
  state (PityState) ────→│     · base_probabilities（从分布模板来）      │
  base_probabilities ───→│     · scope_cards（从 PoolPitySpec 来）       │
  reward (出卡结果) ────→│     · reward_id / reward_rarity / is_featured │
                         │     · pool_instance_id（per-banner 隔离用）   │
                         │     · state 引用（behavior 可读写）            │
                         │                                              │
                         │  2. before_draw():                            │
                         │     for bh in sorted_behaviors:               │
                         │       prob = bh.before_draw(ctx)              │──→ adjusted_probabilities
                         │       ctx.current = prob                      │    （用于最终抽卡）
                         │                                              │
                         │  3. after_draw():                             │
                         │     for bh in behaviors:                      │
                         │       bh.after_draw(ctx)                      │──→ ctx.state._data 被修改
                         │       # bh 自己通过 state.set/incr 操作        │    （计数器、flag等）
                         │       # 引擎完全不知道 bh 做了什么              │
                         └──────────────────────────────────────────────┘
```

**关键约束：**
- `PityContext` 携带的 `base_probabilities` 是配置层产出的**原始**分布，behavior 不修改它
- `ctx.current` 在管道中传递——每个 behavior 在前一个调整后的概率上继续调整
- `state` 的写入是 behavior 通过自己的 namespace 隔离的，管道顺序不影响状态一致性
- behavior 之间可通过 `state.get("other_name", "key")` 读取对方状态（如未来的 `loss_streak` behavior 读取 rotating 的 `lost_5050` flag——见手册 G17）

#### 策略层读接口

重构后保底状态散落在 `PityState._data["behavior_name"]["..."]` 中。策略系统（`StrategyContext.get_pity_probabilities()` / `select_action()`）需要**不耦合 `PityState` 内部结构**的查询接口。`PityEngine` 暴露以下方法供策略层消费：

```python
class PityEngine:
    # ── 策略层查询接口（不暴露 PityState 内部 key） ──

    def get_counter(self, name: str) -> int:
        """返回指定 behavior 的当前计数器值。不存在 → 0。"""
        return self._state.get(name, "counter", 0)

    def get_trigger_count(self, name: str) -> int:
        """返回指定 behavior 已触发的次数。"""
        return self._state.get(name, "triggers", 0)

    def is_guaranteed(self, name: str) -> bool:
        """返回指定 rotating behavior 是否处于大保底状态。非 rotating → False。"""
        return self._state.get(name, "guaranteed", False)

    def is_active(self, name: str) -> bool:
        """返回指定 behavior 当前是否活跃。"""
        return self._state.get(name, "_active", True)

    def get_state_summary(self) -> Dict[str, Dict[str, Any]]:
        """返回所有 behavior 的状态摘要（嵌套 dict 浅拷贝）。
        策略层可一次性获取全量状态，避免多次跨层调用。"""
        return {name: dict(ns) for name, ns in self._state._data.items()}
```

**设计原则：**
- 策略层通过 `PityEngine` 的方法查询，**不直接访问 `PityState._data`**——内部 key 名（`"counter"` / `"triggers"` / `"guaranteed"`）对策略层透明
- `get_state_summary()` 提供逃生舱——策略层可获取全量快照用于复杂决策，但常规查询应使用语义方法
- 这些方法是 **只读** 的——策略层不能通过此接口修改保底状态

### 3.2 基础 type 体系

三种 counter 驱动 + 两种事件驱动：

| `type` | 驱动方式 | 累加方式 | 关键参数 | 状态维度 |
|--------|---------|---------|---------|---------|
| `soft_interval` | counter（每抽 +1） | 区间比例爬升：`new_target = target + progress × other` | `start` / `end` / `func` | 计数器 |
| `soft_additive` | counter（每抽 +1） | 每抽固定累加：`new_scope_prob = base + increment × Δn` | `start` / `increment` | 计数器 |
| `hard` | counter（每抽 +1） | 达到阈值后 scope 范围内 100% | `threshold` | 计数器 |
| `rotating` | 事件（SSR 时转移） | featured/offrate 占比重分配——不改变 SSR 总出率，无锁定目标 | `initial_win_rate` / `loss_increment` | 布尔标志 + 累歪计数器 |
| `targeted` | 事件（SSR 时转移） | 同 rotating 的重分配算法 + 目标锁定 + 命定值累积 | `initial_win_rate` / `loss_increment` / `fate_threshold` / `switch_allowed` / `switch_resets_progress` | 布尔标志 + 累歪计数器 + 命定值 + selected_card |

**`targeted` 与 `rotating` 的关系：** 两者共享 scope 内 featured/offrate 概率重分配算法（提取为模块级 `_redistribute_scope()` 函数），但语义和状态独立——`rotating` 无锁定目标，`targeted` 有 `selected_card` + `fate_points`。两者平级继承 `PityBehavior`，不存在父子关系。


**rotating 的跳变幅度由 `loss_increment` 参数控制：**

| | 硬 rotating（50/50 → 100） | rotating（75/25 → 100） |
|---|---|---|
| `initial_win_rate` | 50% | 75% |
| `loss_increment` | 50%（一次跳满） | 50%（一次跳满） |
| 行为 | 歪 → 100% featured（二态） | 歪 → 100% featured（二态） |

> ⚠️ **2026-06-17 更正：** 原表第三列「软 rotating（捕获明光）」已移除。捕获明光不是 rotating 的 `loss_increment` 变体——它是连歪计数器（4 状态），rotating 是 2 状态机。见手册 G17。

**rotating 在单卡概率体系下的工作方式：**

系统中无两阶段稀有度判定——所有卡片在同一概率空间中竞争。rotating 的 `before_draw` 直接调整 featured 卡片与非 featured 卡片的内部概率权重：

```
小保底状态（50:50）：
  featured_slot: 0.3%  ─┐
  offrate_slot:  0.3%  ─┴─ SSR 总概率 = 0.6%

大保底状态（100:0）：
  featured_slot: 0.6%  ─┐
  offrate_slot:  0.0%  ─┴─ SSR 总概率 = 0.6%（不变）
```

rotating 不改变 SSR 总出率，只重新分配 featured/offrate 内部比例。SSR 总出率由 `soft_interval` 或 `hard`（scope=ssr）控制。

### 3.3 统一参数：`scope`（稀有度层级） + `target_featured`（是否限定 featured 子集）

**两个正交字段：**

| 字段 | 类型 | 含义 |
|------|------|------|
| `scope` | `str` | 作用于哪个稀有度层级——**必须是 `[rarities]` 中注册的稀有度名**（如 `"ssr"` / `"sr"` / `"r"`）。不再接受 `"featured"` 值 |
| `target_featured` | `bool` | 是否仅作用于该稀有度中的 **featured 子集**。默认 `false`——作用于该稀有度全体卡片 |

**为什么拆分：** `"featured"` 不是稀有度名——它是跨稀有度的标记属性。将其作为 `scope` 值导致 `rarity_rank` / `_should_reset` / 排序函数中散落 `if scope == "featured"` 特殊分支。拆为两个正交字段后，`scope` 永远是合法稀有度名，所有特殊分支消失。

**稀有度层级注册（新增配置段）：**

```toml
# ── 稀有度层级注册 ──
[rarities]
ranks = [
    ["UR", "SSR"],   # rank 0 — 最高，平级
    ["SR"],           # rank 1
    ["R"],            # rank 2
]
```

- 同一数组内为平级——`UR` 和 `SSR` 互不碰对方概率
- 框架据此生成 `rarity_rank: {"UR": 0, "SSR": 0, "SR": 1, "R": 2}`（0 = 最高）
- `scope` 值必须在此注册——未注册的 scope → ConfigError

**增量分配：**
- `target_featured = false` → 增量按 scope 稀有度中**所有**槽位的基础概率权重等比分配
- `target_featured = true` → 增量仅分配给 scope 稀有度中标记 `featured=True` 的槽位

**稀有度层级保护（核心规则）：**
- `scope` 的稀有度 rank 决定了它能从哪些稀有度取概率
- **只从 rank ≥ 自身 rank 的稀有度取。** `scope="SR"`（rank=1）→ 从 SR(1) + R(2) 取，不动 UR/SSR(0)
- **平级不互取。** `UR` 和 `SSR` 均为 rank=0，`scope="SSR"` 不能动 `UR`

**重分配算法（`_redistribute_with_rank_protection`）：**

当 behavior 需要将 scope 的总概率调整为 `target_prob` 时：

1. 计算 scope 槽位在当前分布中的总概率 `scope_total`
2. 若 `target_prob == scope_total`：返回 `ctx.current.copy()`
3. 若 `target_prob > scope_total`（增量）：
   - 按 `base_probabilities` 中 scope 各槽位的占比**等比放大** scope 槽位
   - 差额从 **rank ≥ scope_rank 的非 scope 稀有度**中等比扣除（平级跳过 scope 自身 rank 中的其他稀有度）
4. 若 `target_prob < scope_total`（缩减）：
   - 按 scope 各槽位当前占比**等比缩小** scope 槽位
   - 释放的概率按**原始 base_probabilities 权重**等比分配给**所有非 scope 槽位**

极端情况：当可扣除稀有度的总概率为 0 时 → scope 概率封顶于当前可达最大值 + 记录 warning。

**重置判定：**
- 由 behavior 基于 `ctx.draw.reward_rarity` 和 `is_featured` 自行判定
- **低稀有度 hard 保底不被高稀有度出货触发重置。** 如 SR 硬保底——抽到 SSR 不重置 SR 计数器

**`reset` 默认值：** 若 `target_featured = true` → 默认 `reset = scope`（出该稀有度即重置，不要求 featured）；若 `target_featured = false` → 默认 `reset = scope`。均可显式覆盖。

### 3.4 LifecycleConfig——跨 type 共享的生命周期参数

控制行为**何时触发 / 何时停止**的参数，与概率公式无关。聚合为 dataclass 避免 `__init__` 参数膨胀。

**`_active` Flag 集成：** `CounterBasedBehavior.__init__` 中创建 `_active = Flag(state, name, "_active")`。`before_draw` / `after_draw` 开头检查 `_active.is_set()`——非活跃时不调概率、不递增计数器。`_active` 初始值：`depends_on` 为 None → `True`；有依赖 → `False`（由引擎在依赖方首次命中后激活）。`max_triggers` 耗尽时 `_active.clear()` 永久停用。

**计数器作用域由 `pools` 配置推导——** 保底配置作用于哪些池子，计数器就在哪些池子间共享。不设独立的 `persistence` 参数（重复声明且可能矛盾）。

> **非常规组合提醒：** `type=soft_interval` 或 `type=soft_additive` 配合 `scope=sr` 或 `scope=r` 在实际游戏中无先例（调研 12 款游戏，低稀有度保底均为 hard）。框架层面不禁止——允许反事实模拟——但配置时标注为非常规。

### 3.5 参数元数据驱动——对齐策略系统

不引入 params dataclass。TOML 解析后类型已是正确的（`start: int`、`increment: float`），不需类型转换。参数校验由 `BEHAVIOR_REGISTRY` 中的元数据声明支撑——config panel 据此渲染 UI 控件、就地校验必填/范围/类型。模式对齐 `STRATEGY_REGISTRY.params`：

```python
BEHAVIOR_REGISTRY = {
    # ═══ 通用参数（所有 type 共享，不在 params 中重复声明） ═══
    #   scope:     str   — 稀有度层级（必须已在 [rarities] 注册）
    #   target_featured: bool — 是否仅作用于 featured 子集（默认 false）
    #   reset:     str   — 重置条件稀有度（默认 = scope，可覆盖）
    #   LifecycleConfig  — max_triggers / deactivate_on_early_hit / depends_on

    "soft_interval": {
        "class": SoftIntervalBehavior,
        "display_name": "区间软保底",
        "params": {
            "start":      {"type": "int",   "display_name": "起始抽数",   "default": 80,  "min": 1},
            "end":        {"type": "int",   "display_name": "结束抽数",   "default": 90,  "min": 1},
            "func":       {"type": "str",   "display_name": "爬升函数",   "default": "linear",
                            "options": ["linear", "exp", "step"]},
        },
    },
    "soft_additive": {
        "class": AdditiveBehavior,
        "display_name": "累加软保底",
        "params": {
            "start":      {"type": "int",   "display_name": "起始抽数",   "default": 74,  "min": 1},
            "increment":  {"type": "float", "display_name": "每抽增量(%)", "default": 6.0, "min": 0.1},
        },
    },
    "hard": {
        "class": HardPityBehavior,
        "display_name": "硬保底",
        "params": {
            "threshold":  {"type": "int",   "display_name": "保底抽数",   "default": 90,  "min": 1},
        },
    },
    "rotating": {
        "class": RotatingBehavior,
        "display_name": "轮换保底",
        "params": {
            "initial_win_rate": {"type": "float", "display_name": "初始胜率(%)",  "default": 50.0, "min": 0.0, "max": 100.0},
            "loss_increment":   {"type": "float", "display_name": "歪后增量(%)",  "default": 50.0, "min": 0.0, "max": 100.0},
        },
    },
    "targeted": {
        "class": TargetedBehavior,
        "display_name": "定向保底（定轨）",
        "params": {
            "initial_win_rate":       {"type": "float", "display_name": "初始胜率(%)",    "default": 50.0, "min": 0.0, "max": 100.0},
            "loss_increment":         {"type": "float", "display_name": "歪后增量(%)",    "default": 50.0, "min": 0.0, "max": 100.0},
            "fate_threshold":         {"type": "int",   "display_name": "命定值阈值",     "default": 1,    "min": 0},
            "switch_allowed":         {"type": "bool",  "display_name": "允许中途切换",   "default": true},
            "switch_resets_progress": {"type": "bool",  "display_name": "切换后清零进度", "default": true},
        },
    },
}
```

**收益：** 零新类型 · TOML 类型保真（`int`/`float`/`str`） · config panel 元数据驱动渲染 · 与策略系统一致 · 新增 type 只需在注册表中加一段元数据声明。

### 3.6 Registry 模式

对齐策略系统的 `STRATEGY_REGISTRY`——`BEHAVIOR_REGISTRY` 的元数据结构见 §3.5。工厂函数：

```python
# core/pity.py

def create_behavior(pdef: PityDef, state: PityState, scope_cards: dict, ...) -> PityBehavior:
    """工厂函数——一行查找、一行解包构造。"""
    entry = BEHAVIOR_REGISTRY[pdef.btype]
    cls = entry["class"]
    return cls(name=pdef.name, state=state, scope=pdef.scope, **pdef.params)
```

`PityEngine.__init__()` 退化为：

```python
for pdef in self.pity_defs:
    bh = create_behavior(pdef, spec.scope_cards, spec.featured_ids, ...)
    self._behaviors.append(bh)
```

**新增保底类型 = 写类 + `BEHAVIOR_REGISTRY` 加一段元数据 + 配 TOML。** 引擎零改动。

### 3.7 类结构（全景）

```
LifecycleConfig                                 # 跨 type 生命周期参数
  max_triggers: int = 0                         # P56 扩展 deactivate_on_early_hit / depends_on

DrawInfo (frozen dataclass)                    # 不可变静态事实
  pool_id / pool_instance_id
  reward_id / reward_rarity / is_featured
  scope_cards: Mapping[str, tuple[str, ...]]    # rarity → 具体卡牌 ID
  scope_slots: Mapping[str, tuple[str, ...]]    # rarity → 模板槽位 ID
  featured_slots: Mapping[str, tuple[str, ...]]  # rarity → featured=true 的槽位 ID
  base_probabilities: Mapping[str, float]       # 槽位 ID → 基础概率
  rarity_rank: Mapping[str, int]                # 0=最高，由 [rarities] 生成

PityContext                                     # 管道可变载体
  draw: DrawInfo                                # 只读
  current: Dict[str, float]                     # 管道概率
  state: PityState                              # 可读写

PityBehavior (ABC)                              # 独立化接口
  ├── before_draw(ctx: PityContext) -> Dict[str, float]
  ├── after_draw(ctx: PityContext) -> None
  ├── did_fire(ctx: PityContext) -> bool         # P56 声明式依赖传播
  └── is_active(ctx: PityContext) -> bool

├── CounterBasedBehavior (ABC)                   # 可选基类——计数器驱动型通用生命周期
│   │   _active: Flag                             # P56 声明式依赖激活 + max_triggers 耗尽停用
│   │   _reset: str                                # 默认 = scope，可显式覆盖
│   ├── SoftIntervalBehavior
│   ├── AdditiveBehavior
│   └── HardPityBehavior                           # P56 覆写 after_draw 实现 deactivate_on_early_hit
├── RotatingBehavior (PityBehavior)               # P56 实现——事件驱动，无锁定目标
└── TargetedBehavior (PityBehavior)               # P56 实现——事件驱动 + 目标锁定 + 命定值
                                                    # 与 RotatingBehavior 平级，共享 _redistribute_scope()

Counter / Flag                                  # 微抽象——PityState 的语法糖

PityState:                                      # 抽象 namespace 容器
  _data: Dict[str, Dict[str, Any]]
  get(name, key, default) / set(name, key, val) / incr(name, key, delta)

PityEngine:                                     # 调度器 + 策略读接口
  _behaviors: List[PityBehavior]                # 外部注入
  _activation_graph: Dict[str, List[str]]       # P56：声明式依赖传播
  before_draw(pool_id, state, draw_info) → adjusted_probs
  after_draw(pool_id, state, reward) → None
  # ── 策略层读接口 ──
  get_counter(name) → int                       # 计数器值
  get_trigger_count(name) → int                 # 触发次数
  is_guaranteed(name) → bool                    # rotating 大保底状态
  is_active(name) → bool                        # 是否活跃
  get_state_summary() → Dict[str, Dict]         # 全量状态快照

BEHAVIOR_REGISTRY: Dict[str, dict]                    # type → {class, display_name, params元数据}（对齐 STRATEGY_REGISTRY）
```

### 3.8 Counter / Flag 微抽象

**设计哲学：** `PityState` 是公寓楼（`{name: {key: value}}`），`Counter` / `Flag` 是遥控器——记住地址，不需要每次念楼层和抽屉号。

```python
@dataclass
class Counter:
    """封装 PityState 中单个保底的计数器操作。不持有状态——纯语法糖、只记住地址。"""
    _state: PityState
    _name: str
    _key: str = "counter"

    def incr(self, delta: int = 1) -> int:
        return self._state.incr(self._name, self._key, delta)

    def reset(self):
        self._state.set(self._name, self._key, 0)

    def value(self) -> int:
        return self._state.get(self._name, self._key, 0)

    def reached(self, threshold: int) -> bool:
        return self.value() >= threshold

@dataclass
class Flag:
    """封装 PityState 中单个保底的布尔标志操作。"""
    _state: PityState
    _name: str
    _key: str

    def set(self):
        self._state.set(self._name, self._key, True)

    def clear(self):
        self._state.set(self._name, self._key, False)

    def is_set(self) -> bool:
        return self._state.get(self._name, self._key, False)
```

**对比：**

| | 直接用 PityState | 用 Counter 遥控器 |
|---|---|---|
| 计数器 +1 | `state.incr(name, "counter", step)` | `self._counter.incr(step)` |
| 查询值 | `state.get(name, "counter")` | `self._counter.value()` |
| 归零 | `state.set(name, "counter", 0)` | `self._counter.reset()` |
| 达阈值？ | `state.get(name, "counter") >= 90` | `self._counter.reached(90)` |
| 拼写错误 | `"counetr"` → 返回 0，安静 bug | `self._counter` → AttributeError，立即发现 |

**零成本：** 不影响序列化、不改变 `PityState` 接口、不引入新概念。只是 `PityState` 的语法糖。

### 3.9 CounterBasedBehavior 基类

**设计哲学：** 三种计数器驱动型 behavior 共享同一个生命周期模式——提取共性到可选基类，子类只写概率调整逻辑。不影响非计数器型保底（`RotatingBehavior` 直接继承 `PityBehavior`）。

```python
class CounterBasedBehavior(PityBehavior, ABC):
    """计数器驱动型保底的通用生命周期。
    
    子类只需实现 _compute_probabilities(ctx, counter) → Dict[str, float]。
    计数器管理（增/查/重置/触发上限）统一处理。
    """

    def __init__(self, name: str, state: PityState, scope: str, reset: str = None,
                 target_featured: bool = False,
                 lifecycle: LifecycleConfig = LifecycleConfig()):
        self._name = name
        self._state = state
        self._scope = scope              # 稀有度层级——永远是合法 rarity 名
        self._target_featured = target_featured
        self._reset = reset if reset is not None else scope  # 默认 = scope，可显式覆盖
        self._lifecycle = lifecycle
        self._triggers = Counter(state, name, "triggers")  # 触发次数 key 始终固定
        self._active = Flag(state, name, "_active")         # 活跃标志——depends_on 初始 False
        if lifecycle.depends_on is None:
            self._active.set()                               # 无依赖 → 始终活跃
        # 有依赖 → 初始 False，由引擎在依赖方首次命中后激活

    # ── 子类只需实现这一个方法 ──
    @abstractmethod
    def _compute_probabilities(self, ctx: PityContext, counter: int) -> Dict[str, float]:
        """给定上下文和当前计数器值，返回调整后概率分布。"""
        ...

    # ── 计数器遥控器：计数器作用域由 pools 配置推导，无需 persistence 参数 ──
    def _counter(self) -> Counter:
        """返回计数器遥控器。key 始终为 "counter"——pools 配置决定作用域。"""
        return Counter(self._state, self._name, "counter")

    # ── 生命周期由基类统一管理 ──
    def before_draw(self, ctx: PityContext) -> Dict[str, float]:
        if not self._active.is_set():
            return ctx.current.copy()   # 已停用——不调概率、不递增计数器
        c = self._counter()
        v = c.incr()
        return self._compute_probabilities(ctx, v)

    def after_draw(self, ctx: PityContext) -> None:
        if not self._active.is_set():
            return
        if not self._should_reset(ctx):
            return
        if self._lifecycle.max_triggers and self._triggers.value() >= self._lifecycle.max_triggers:
            self._active.clear()         # 触发上限耗尽 → 永久停用（不再调概率、不再递增计数器）
            return
        c = self._counter()
        c.reset()
        self._triggers.incr()

    def _should_reset(self, ctx: PityContext) -> bool:
        """子类可覆写——默认：出了 reset 对应的稀有度就重置。
        target_featured 不影响 reset 判定（reset 始终基于稀有度，不强制 featured）。
        如需「仅 featured 命中才重置」，显式设置 reset="featured"（但通常不推荐）。"""
        if self._reset == "featured":
            return ctx.draw.is_featured
        return ctx.draw.reward_rarity == self._reset
```

**三个具体 behavior 瘦身后的对比：**

| | 当前每个类 | 使用 CounterBasedBehavior 后 |
|---|---|---|
| 行数 | ~80-100 行 | ~25-40 行（只写 `_compute_probabilities`） |
| 计数器管理 | 每个类重复一次 | 基类统一 |
| 生命周期参数 | 每个类重复 | 基类统一接收 `LifecycleConfig` |

`AdditiveBehavior` 瘦身示例：

```python
class AdditiveBehavior(CounterBasedBehavior):
    def __init__(self, name, state, scope, start=74, increment=6.0, **kwargs):
        super().__init__(name, state, scope, **kwargs)
        self._start = start
        self._increment = increment

    def _compute_probabilities(self, ctx, counter):
        if counter < self._start:
            return ctx.current.copy()
        slots = ctx.draw.scope_slots.get(self._scope, ())
        base = sum(ctx.draw.base_probabilities.get(s, 0.0) for s in slots)
        new_prob = min(base + self._increment * (counter - self._start + 1), 1.0)
        return self._redistribute(ctx, new_prob, slots)
```

**层级关系不会混乱：** `CounterBasedBehavior` 是可选快捷方式——counter 驱动的三种 type 用它。`rotating` 是事件驱动的，直接继承 `PityBehavior`，不走 `CounterBasedBehavior`。没有强制层级。

### 3.10 执行顺序——矩阵规则自动推导

**设计决策：不再使用 `priority` 数字字段。** 执行顺序由 behavior 的 type 分类 + scope 层级关系自动推导。配置者无需手写排序数字。

#### 3.10.1 矩阵分析

两个 behavior 的交互由两个维度决定：**驱动方式**（counter vs 事件）× **scope 关系**（无关 / 重叠）。

| A \ B | 概率增加（soft_*） | 重分配（rotating/targeted） | 强制出卡（hard） |
|-------|-------------------|-------------------------|-----------------|
| **soft_*** | 叠加——后执行者继续调整 | soft 先——先增加总出率，再分配内部比例 | soft 先——hard 设 100% 覆盖 soft |
| **rotating/targeted** | rotating 后（同上） | 同 scope → 无意义，校验时 warn | rotating 先——分配完再 hard 覆盖 |
| **hard** | hard 后（同上） | hard 后（同上） | 同 scope → **ConfigError** |

**排序规则：soft → rotating/targeted → hard。** 先增加 scope 总出率，再分配内部比例，最后强制覆盖。每个 type 内部按稀有度降序。`rotating` 和 `targeted` 为同一优先级，两者作用于同 scope → ConfigError。

| scope 关系 | 处理 |
|-----------|------|
| **无关**（如 `ssr` ∪ `sr`，互不重叠） | 低稀有度保底只从 ≤ 自身稀有度取概率——不会碰高稀有度。顺序无关 |
| **包含**（如 `featured` ⊂ `ssr`） | 自动：高稀有度在前，同层 soft→rotating→hard |
| **相同** | 按 type 规则（见上表） |

#### 3.10.2 自动推导规则

引擎在构造时自动排序，不依赖配置者手写数字：

```python
def _resolve_order(behaviors: List[PityBehavior]) -> List[PityBehavior]:
    """基于 type 分类 + scope 层级自动推导执行顺序。

    规则：
      1. scope 无关（互不重叠）→ 顺序不影响结果，保持注册顺序
      2. scope 重叠 → soft → rotating → hard（先增量、再分配、最后强制）
      3. 低稀有度只在 ≤ 自身稀有度的概率段操作——不影响高稀有度
    """
    return sorted(behaviors, key=lambda bh: (
        _rarity_rank(bh.scope),      # 高稀有度排前；featured → rank 0
        _type_order(bh),              # soft(0) < rotating(1) < hard(2)
    ))

def _rarity_rank(scope: str) -> int:
    """scope → 稀有度数值 rank。scope 永远是合法稀有度名——校验层已保证。"""
    return rarity_rank_map[scope]   # KeyError = 校验层 bug，不应静默吞掉

def _type_order(bh: PityBehavior) -> int:
    if bh.is_soft:     return 0   # soft_* 最先
    if bh.is_rotating: return 1   # rotating 中间——重分配
    if bh.is_hard:     return 2   # hard 最后——强制覆盖
```

**举例：**

```
输入: [sr_hard(scope=sr), ssr_soft(scope=ssr)]

解析:
  ssr_soft  稀有度=高, type=soft → 排序靠前（先执行）
  sr_hard   稀有度=低, type=hard → 排序靠后（后执行）

执行:
  Step 1: ssr_soft: SSR 从 1%→10%, SR+R 等比缩小
  Step 2: sr_hard:  R→0, SR 涨到 90%, SSR 保持 10%  ← 不动 SSR
```

#### 3.10.3 校验分级

```python
def _validate_behaviors(behaviors: List[PityBehavior]) -> None:
    for a, b in itertools.combinations(behaviors, 2):
        if not _scope_overlap(a.scope, b.scope):
            continue

        # ── 同 scope 两个 hard → 报错 ──
        if a.is_hard and b.is_hard and a.scope == b.scope:
            raise ConfigError(
                f"「{a.name}」和「{b.name}」都是强制出卡型且 scope 相同——"
                f"后者覆盖前者，没有意义。删除其一或改为不同 scope。"
            )

        # ── 同 scope 两个 rotating → 报错 ──
        if a.is_rotating and b.is_rotating and a.scope == b.scope:
            raise ConfigError(
                f"「{a.name}」和「{b.name}」都是轮换保底且 scope={a.scope}——"
                f"第二个的效果覆盖第一个，没有意义。删除其一。"
            )

        # ── 同 scope 两个同 type 的 soft → 报错 ──
        if a.is_soft and b.is_soft and a.type == b.type and a.scope == b.scope:
            raise ConfigError(
                f"「{a.name}」和「{b.name}」type 和 scope 完全相同——"
                f"管道效果叠加，第二个的效果完全覆盖第一个。改为不同 scope 或删除其一。"
            )

        # ── 同 scope 两个不同 type 的 soft → 警告 ──
        if a.is_soft and b.is_soft and a.type != b.type and a.scope == b.scope:
            warnings.warn(
                f"「{a.name}」和「{b.name}」同时调整 scope={a.scope}——"
                f"效果叠加，后执行者在前者基础上继续。若非有意，请检查。"
            )
```

| 场景 | 行为 |
|------|------|
| scope 无关 | 通过——自动排序，低稀有度不碰高稀有度 |
| scope 重叠 + 有 hard | 通过——自动排序（soft 前 hard 后） |
| 同 scope 两个 hard | **ConfigError**——无意义 |
| 同 scope 两个 rotating | **ConfigError**——后者覆盖前者 |
| 同 scope 同 type 两个 soft | **ConfigError**——管道叠加导致后者覆盖前者，等同于前者无效 |
| 同 scope 不同 type 两个 soft | **warn**——允许（如 `soft_interval` + `soft_additive` 同时作用于 ssr），但提醒可能非有意 |

### 3.11 `AdditiveBehavior` 数学公式

```
给定 scope = "ssr", increment = 6.0, start = 74, counter = n：

  base_ssr_prob = Σ_{s ∈ scope_slots["ssr"]} prob(s)    # 按槽位求和：如 s∈{"ssr","ssr_alt"}
  raw = base_ssr_prob + increment × max(n - start + 1, 0)
  new_ssr_prob = min(raw, 1.0)

  各 SSR 卡按基础概率在 SSR 中的占比分配 new_ssr_prob
  非 SSR 卡等比缩放至 (1 - new_ssr_prob)，保持内部比例不变
```

### 3.12 配置语法

```toml
# ── 稀有度层级注册（新增配置段，全文件仅一处） ──
[rarities]
ranks = [
    ["UR", "SSR"],   # rank 0 — 最高，平级
    ["SR"],           # rank 1
    ["R"],            # rank 2
]

# ── 保底配置 ──

# 1. 不歪型区间软保底（仅作用于 featured 子集）
[[pity]]
type = "soft_interval"
scope = "ssr"
target_featured = true
start = 80
end = 90
func = "linear"
# reset 默认 = "ssr"（出 SSR 即重置，不要求 featured）

# 2. 会歪型固定累加软保底（作用于全体 SSR）
[[pity]]
type = "soft_additive"
scope = "ssr"
start = 74
increment = 6.0
# target_featured 默认 = false → 增量分配给所有 SSR 槽位
# reset 默认 = "ssr"，可省略

# 3. 不歪型硬保底（仅 featured）
[[pity]]
type = "hard"
scope = "ssr"
target_featured = true
threshold = 180

# 4. SR 保底（每 10 抽保底 SR）
[[pity]]
type = "hard"
scope = "sr"
threshold = 10

# 5. 硬保底 + 仅触发一次（终末地 120 大保底）
[[pity]]
type = "hard"
scope = "ssr"
threshold = 120
max_triggers = 1
# deactivate_on_early_hit = true   # P56：提前命中永久关闭

# 6. 轮换保底——基础二态轮换（rotating 内部 target_featured 恒为 true）
[[pity]]
type = "rotating"
scope = "ssr"
initial_win_rate = 50.0
loss_increment = 50.0            # 歪一次后 featured 跳满到 100%（二态跳变）。注：捕获明光不在此类——见手册 G17

# 7. 定向保底（定轨）——三种变体覆盖所有已知游戏
# 7a. 原神式：fate_threshold=1 + 切换清零
[[pity]]
type = "targeted"
scope = "ssr"
initial_win_rate = 50.0
loss_increment = 50.0
fate_threshold = 1
switch_allowed = true
switch_resets_progress = true

# 7b. 绝区零音擎回响式：fate_threshold=1 + 切换不清零
[[pity]]
type = "targeted"
scope = "ssr"
fate_threshold = 1
switch_allowed = true
switch_resets_progress = false

# 7c. 鸣潮常驻武器池式：fate_threshold=0——无累积，100%分配到选定卡
[[pity]]
type = "targeted"
scope = "ssr"
fate_threshold = 0
switch_allowed = true
switch_resets_progress = false
# 可选卡范围 → 由 [[pool]].epitomizable_cards 显式配置，不从 featured 推导
```

### 3.13 实施阶段

**关键识别：阶段一至四构成「平台层」——是 P56（rotating/targeted）和 P58B（milestone）的共同基础设施。平台层完成后，P56、P58B、P55 后续阶段可并行推进。**

**可提前提取的微型任务（不依赖 P55 任何其他阶段）：**

| 微型任务 | 归属 | 行数 | 受益方 |
|---------|------|:---:|--------|
| `ConfigStore.is_limited(card_id)` | 独立——利用现有 `PoolPitySpec.featured_ids` | ~5 | P57（替代 `card_id.startswith('limited')`） |
| `[rarities]` 配置段解析 | P55 Phase 10 中提取 | ~15 | P55（scope 校验）、P57（scope 参数校验）、P58B（milestone scope 默认值推导） |

这两个微型任务可在 P58A 之后、P55 平台层之前以一次提交完成——低成本、零风险、高收益（统一稀有度名称校验、消除 P57 命名约定依赖）。

**平台层（Phase 1-4）对其他计划的简化效应：**

| 被简化方 | 简化点 | 效应 |
|---------|------|------|
| **P58B** | `MilestoneBehavior(CounterBasedBehavior)` —— 计数器生命周期（增/查/重置/停用）全部继承 | 60→35行 |
| **P56** | `RotatingBehavior` / `TargetedBehavior` 状态存储——`PityState` namespace + `Counter`/`Flag` | 每个 behavior 的状态管理零新代码 |
| **P55 自身** | `SoftInterval`/`Additive`/`HardPity` 只写 `_compute_probabilities()` | 各 ~80→~30行 |
| **任何未来 type** | `BEHAVIOR_REGISTRY` 一行注册 + 写类 | 引擎零改动 |

| 阶段 | 内容 | 文件 |
|------|------|------|
| **阶段一** | `PityState` 抽象化（namespace 容器 + `get`/`set`/`incr`）+ `Counter` / `Flag` 微抽象 | `pity.py` |
| **阶段二** | `DrawInfo`（`frozen` 静态事实）+ `PityContext`（可变载体：`draw` / `current` / `state`） | `pity.py` |
| **阶段三** | `PityBehavior` 接口独立化 + `CounterBasedBehavior` 基类（含 `LifecycleConfig` 贯通） | `pity.py` |
| **阶段四** | `BEHAVIOR_REGISTRY` 参数元数据——对齐 `STRATEGY_REGISTRY.params` 模式 | `pity.py` |
| **阶段五** | `SoftIntervalBehavior` 独立化改造——继承 `CounterBasedBehavior`，只写 `_compute_probabilities()` | `pity.py` |
| **阶段六** | `HardPityBehavior` scope 化——继承 `CounterBasedBehavior` | `pity.py` |
| **阶段七** | `AdditiveBehavior` 实现——继承 `CounterBasedBehavior`，只写 `_compute_probabilities()` | `pity.py` |
| **阶段八** | `BEHAVIOR_REGISTRY`（含参数元数据）+ `create_behavior()` 工厂函数 + `RotatingBehavior` stub（继承 `PityBehavior`，`before_draw` 返回 `ctx.current.copy()`，`after_draw` 空实现） | `pity.py` |
| **阶段九** | `PityEngine` 退化为调度器——注入 `_behaviors` 列表 + `_resolve_order()` 自动排序（含 rotating） + `_validate_behaviors()` 校验 | `pity.py` |
| **阶段十** | `PityDef` 字段扩展 + 配置解析更新（含 `[rarities]` 解析 + `_build_pity()` 适配 + scope 注册校验） | `config_store.py` / `config_toml.py` |
| **阶段十一** | 配置面板 UI 更新——新增 `type`/`scope`/`increment`/轻量扩展控件 | `config_panel.py` |
| **阶段十二** | 波及文件适配——`worst_impact.py` / `batch_simulator.py` / `gacha_service.py` 等 | 多个文件 |
| **阶段十三** | 测试更新 + 文档更新 | `tests/` / `docs/` |

## 四、波及范围

### 4.1 核心改动

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/pity.py` | **重构** | DrawInfo + PityContext + PityState 抽象化 + PityBehavior 接口独立化 + 三种 counter behavior + rotating stub + BEHAVIOR_REGISTRY + Engine 退化 |
| `core/config_store.py` | **修改** | `PityDef` 字段扩展：`type`/`scope`/`max_triggers`/`params`（`Dict[str, Any]`）+ `LifecycleConfig` |
| `core/config_toml.py` | **修改** | `[rarities]` 解析 + `_build_pity()` 适配新字段（`type`/`scope` 等）+ scope 注册校验 |
| `core/__init__.py` | **修改** | 更新导出符号 |

### 4.2 波及适配

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `service/batch_simulator.py` | 适配 | PityEngine 构造参数可能变化 |
| `service/gacha_service.py` | 适配 | 同上 |
| `core/worst_impact.py` | 适配 | 直接实例化 `SoftPityBehavior`/`HardPityBehavior` → 更新类名引用 |
| `core/strategy.py` | 检查 | `StrategyContext` 是否引用 `PityState` |
| `core/process_analysis.py` | 检查 | pity 事件类型是否需要更新 |
| `core/process_trace.py` | 检查 | 同上 |
| `core/streaming.py` | 检查 | 同上 |
| `core/collector.py` | 检查 | 是否引用 pity 相关结构 |
| `gui/config_panel.py` | **修改** | `_setup_pity_config()` UI 重构——见下方 UI 适配说明 |
| `gui/gacha_panel.py` | 检查 | 可能引用 pity 配置 |
| `gui/analysis_panel.py` | 检查 | 可能引用 pity 事件 |
| `gui/process_analysis_panel.py` | 检查 | 同上 |
| `gui/worst_impact_panel.py` | 检查 | 同上 |
| `gui/retreat_search_panel.py` | 检查 | 同上 |
| `cli.py` | 检查 | 是否构造 PityEngine |
| `config/config.toml` | **更新** | `[[pity]]` 节使用新语法 |

### 4.3 文档

| 文件 | 改动 |
|------|------|
| `subsystems/保底系统/01-理论.md` | 更新——加入独立化设计 + 新 type/scope 理论 |
| `subsystems/保底系统/02-实施.md` | 更新——反映新类结构和上下文模型 |
| `subsystems/保底系统/04-问题.md` | 更新——缺陷状态同步 |
| `subsystems/保底系统/05-笔记.md` | H4 自动维护 |

### 4.4 UI 适配：`scope` / `target_featured` 拆分后的控件映射

`config_panel.py` 的 `_setup_pity_config()` 中，每个保底条目当前有 `scope` 下拉框（含 `"featured"` 选项）。拆分后：

| 旧控件 | 新控件 | 说明 |
|--------|--------|------|
| `scope` 下拉框（含 `"ssr"` / `"sr"` / `"r"` / `"featured"`） | `scope` 下拉框（**仅** `[rarities]` 中注册的稀有度名，如 `"ssr"` / `"sr"` / `"r"`） | 选项由 `ConfigStore.rarity_ranks` 动态生成，移除 `"featured"` 选项 |
| （无） | `target_featured` 复选框 | 新增——默认不勾选。勾选 = 「仅作用于 featured 子集」 |
| `type` 下拉框 | 不变 | — |
| 各 type 专属参数 | rotating 的 `scope` 下拉框同样仅显示稀有度名 | rotating 不再特殊——`scope` 与其他 type 共用同一套下拉选项 |

**联动校验：**
- `type = "rotating"` 时 `target_featured` 复选框**禁用并强制显示为勾选**（rotating 天生操作 featured 子集，不提供选择）
- `type = "soft_additive"` + `scope = "sr"` / `"r"` 时显示 **「非常规组合」警告标签**（见 §3.4 提醒）

**向后兼容：** 旧 `config.toml` 中 `scope = "featured"` 的条目——解析时自动迁移：`scope` 改为该池子最高稀有度（如 `"ssr"`），`target_featured` 设为 `true`，并记录 warning 提示用户确认。

## 五、风险

| 风险 | 缓解 |
|------|------|
| `worst_impact.py` 直接实例化原类名（`SoftPityBehavior` / `HardPityBehavior`） | 全量替换为新类名，不保留旧别名 |
| 独立化后 behavior 间状态竞争（多 behavior 同时修改 `ctx.state`） | namespace 隔离——各 behavior 操作独立 key；执行顺序由自动推导规则保证确定性 |
| `PityState` 抽象化后序列化兼容 | `to_dict()`/`from_dict()`通用——三层嵌套结构，namespace 隔离天然保证兼容 |
| `CounterBasedBehavior` 计数器作用域与池子配置的一致性 | 计数器作用域由 `pools` 配置推导——保底作用于哪些池子，计数器就在哪些池子间共享；不引入独立的 `persistence` 参数 |
| `base_probabilities` key 语义不明确（槽位 vs 卡牌 id） | DrawInfo 显式区分 `scope_cards`（卡牌 ID）与 `scope_slots`（槽位 ID）；AdditiveBehavior 累加使用 slots |
| `[rarities]` 中 scope 未注册但被 `[[pity]]` 引用 | 解析时即校验——`scope` 值必须在 `[rarities]` 的某一行中出现过，否则 ConfigError |
| 配置面板 UI 改动过大 | 渐进式——先加新字段，确保必填校验 |
| `ctx.current` 管道缺少历史记录 | **已知局限（搁置）：** behavior 只能看到当前管道状态，无法回溯前一个 behavior 调整前的 `ctx.current`。调试复杂叠加场景时可能不便。低优先级，后续按需在 `PityContext` 增加 `previous: Optional[Dict]` 字段 |

## 六、设计边界提醒

### 现有能力（不要推倒重来）

以下能力当前 `core/pity.py` 已实现，P55 是**重构**而非新建——保留核心逻辑，改的是组织方式：

| 现有能力 | 代码位置 | P55 如何处理 |
|---------|---------|-------------|
| `SoftPityBehavior._apply_targeted()` — 概率增量按 `resolved_targets` 分配 | `pity.py:62-88` | **保留分配算法**。P55 的 `target_featured` 参数是此能力的声明式入口——`PoolPitySpec.resolved_targets` 的构建逻辑改为由 `target_featured` + `scope` 推导 |
| `PityEngine.after_draw()` — 三级 `reset_condition`（`any_ssr` / `featured_ssr` / `never`） | `pity.py:246-264` | **保留判定结构**。P55 泛化 `reset` 为任意稀有度名（如 `"ssr"` / `"sr"`），但仍走同一判定分支 |
| `PityState` — `increment()` / `reset()` / `get()` 基础操作 | `pity.py:165-192` | **保留语义**。P55 扩展为 namespace 容器（`_data: Dict[str, Dict[str, Any]]`），但 `incr` / `set` / `get` 语义不变 |
| `PityEngine.before_draw()` — 先 `increment` 再 `get_probabilities` 的管道顺序 | `pity.py:227-236` | **保留顺序**。P55 改为 `foreach behavior: bh.before_draw(ctx)`，但「先计数、后算概率」不变 |
| `PityEngine.get_probabilities()` — 不修改状态的查询 | `pity.py:203-225` | **保留此方法**。策略层已有只读查询入口，P55 扩充为 5 个语义方法 |
| `PoolPitySpec.featured_ids` / `ssr_ids` — 区分限定/常驻的基础设施 | `pity.py:158-163` | **保留**。P55 的 `DrawInfo.featured_slots` 由此推导 |

### P55 新建能力（只建一次，不要叠层）

以下为 P55 新建——每个需求对应**一个**机制：

| 新建能力 | 机制 | 不要做的事 |
|---------|------|-----------|
| behavior 自管完整生命周期 | `PityBehavior.before_draw()` / `after_draw()` 独立接口 | 不要在 Engine 层写 if-else 分发 |
| 新增保底类型零改动 Engine | `BEHAVIOR_REGISTRY` + `create_behavior()` 工厂 | 不要额外建 plugin 系统或注册中心 |
| 状态字段不预设类型 | `PityState` namespace 化（`_data: Dict[str, Dict]`） | 不要建 typed state schema |
| 计数器操作拼写安全 | `Counter` / `Flag` 微抽象 | 不要引入完整 ORM 或状态管理框架 |
| 跨 behavior 重置协调 | TOML `reset` 参数——各自声明 | 不要加 inter-behavior 重置传播协议 |
| 触发 N 次后停用 | `max_triggers` → `_active.clear()` | 不要额外建「一次性 behavior」子类 |
| 策略查询保底状态 | `PityEngine.get_counter()` / `is_guaranteed()` 等 | 不要让策略直接访问 `PityState._data` |
| 管道概率依次传递 | `ctx.current` → 返回新 dict → engine 赋值 | 不要加概率快照/回滚机制 |

## 七、验收标准

- [ ] `DrawInfo` 不可变性：`frozen=True` 生效，误写编译报错
- [ ] `PityContext` 完整性：behavior 仅通过 `ctx.draw` / `ctx.current` / `ctx.state` 获取信息，不访问外部全局状态
- [ ] `PityEngine` 无保底业务逻辑——`after_draw()` 仅为 `foreach behavior: behavior.after_draw(ctx)`
- [ ] `PityState` 抽象化：behavior 通过 `get()`/`set()`/`incr()` 操作自身 namespace，引擎不预设字段类型
- [ ] `PityState` 序列化往返无损（`to_dict()` → `from_dict()`）
- [ ] `Counter` 封装正确：`incr()`/`value()`/`reset()`/`reached()` 等价直接操作 `PityState`
- [ ] `CounterBasedBehavior` 生命周期统一：三个子类（Soft/Additive/Hard）只实现 `_compute_probabilities()`，`before_draw`/`after_draw` 由基类统一
- [ ] `BEHAVIOR_REGISTRY`（含参数元数据）+ `create_behavior()` 工厂函数正确路由所有 type
- [ ] 参数元数据驱动：config panel 依据元数据渲染 UI 控件，必填/范围/类型校验生效
- [ ] `type = "soft_additive"` + `scope = "ssr"` 产出概率分布与公式一致（≥3 个抽样点校验）
- [ ] `scope = "sr"` 硬保底正确工作——第 N 抽出 SR 时重置，累加至 100% 后必出 SR
- [ ] `max_triggers = 1` 正确限制触发次数——触发一次后不再触发
- [ ] `reset` 默认值 = `scope` 正确生效（如 `scope="ssr"` 未设 `reset` → 出 SSR 即重置）
- [ ] 同 pool 上两个不同 `name` 的同 type 保底（如 `soft1`、`soft2`），计数器完全独立不互相影响
- [ ] `[rarities]` 解析正确——`rarity_rank` 映射生成、平级同 rank、未注册 scope → ConfigError
- [ ] 自动推导：`_resolve_order()` 正确排序——高稀有度先执行、同稀有度 soft 在 hard 前
- [ ] 校验分级：同 scope 两个 hard → ConfigError；同 scope 两个 rotating → ConfigError；同 scope 同 type 两个 soft → ConfigError；同 scope 不同 type 两个 soft → warn
- [ ] 稀有度层级保护：`scope="SR"` 的增量不着色 `rank < SR_rank` 的稀有度（如 UR/SSR）
- [ ] 配置面板可完整编辑所有新字段
- [ ] 现有 7 种策略在保底重构后行为无退化（集成测试）
- [ ] `worst_impact.py` / `batch_simulator.py` / `gacha_service.py` 无 import 错误
- [ ] pytest 全量通过（含新增 pity 专项测试 ≥20 用例，覆盖所有新 type/scope/轻量扩展组合）
