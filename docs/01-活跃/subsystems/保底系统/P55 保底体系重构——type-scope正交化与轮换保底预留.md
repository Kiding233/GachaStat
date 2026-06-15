<!-- META: P55 | module:保底系统 | status:designing | last:2026-06-15 -->

# P55 保底体系重构——type/scope 正交化、状态抽象化、行为独立化

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
- **四种 type**：`soft_interval` / `soft_additive` / `hard` / `rotating_guarantee`
- **统一 `scope` 参数**：作用于稀有度级别（`ssr` / `sr` / `r` / `featured`），同时适用于软保底和硬保底
- **行为独立化**：每个 `PityBehavior` 自管完整生命周期（概率调整 + 状态更新），引擎退化为纯调度器，对齐策略系统的 Context 注入模式
- **状态抽象化**：`PityState` 不预设字段类型——每个 behavior 以自身 `name` 为 namespace 存取任意类型数据
- **DrawInfo 拆分**：`PityContext` 拆为两层——`DrawInfo`（不可变静态事实，`frozen=True`）+ 可变载体（`current` / `state`），类型系统强制执行可变/不可变边界
- **Registry 模式**：`BEHAVIOR_REGISTRY` + `PARAM_REGISTRY` 两张表消除 if-else，新增保底类型 = 写类 + 注册一行 + 配 TOML
- **参数 dataclass 化**：每种 type 配一个强类型参数 dataclass（`IntervalParams` / `AdditiveParams` / `HardParams`），TOML 解析时即校验，消除 `Dict[str, str]` 的类型丢失
- **Counter / Flag 微抽象**：`Counter`（遥控器模式——封装 `state.incr(name, key)` 为 `counter.incr()`）+ `Flag`（布尔标志遥控器），消除字符串 key 散落
- **CounterBasedBehavior**：计数器驱动型保底的可选基类——统一计数器生命周期（增/查/重置/触发上限）、子类只实现 `_compute_probabilities(ctx, counter)`
- **六大支柱**：`type × scope 正交` + `行为独立化` + `状态抽象化` + `DrawInfo 拆分` + `Registry` + `CounterBasedBehavior` → 新增计数器型保底只需实现一个方法
- **轮换保底**：本次预留接口（`PityState` 抽象存储天然支持），完整实现作为后续计划
- **扩展覆盖**：A2（多计数器继承控制）、C1（计数器加速）、C2（提前出货不重置）、C3（保底触发上限）

## 二、目标

### 2.1 核心交付

| # | 交付 | 说明 |
|---|------|------|
| 1 | **行为独立化** | `PityBehavior` 自管完整生命周期；`PityEngine` 退化为调度器 |
| 2 | **`PityContext` + `DrawInfo`** | `DrawInfo`（`frozen=True`，静态事实）+ `PityContext`（可变载体：`current` / `state`），类型系统强制执行可变/不可变边界 |
| 3 | **`BEHAVIOR_REGISTRY` + `PARAM_REGISTRY`** | 两张注册表消除 if-else；新增保底类型 = 写类 + 注册一行 |
| 4 | **参数 dataclass 化** | `IntervalParams` / `AdditiveParams` / `HardParams`，TOML 解析时即校验，消除 `Dict[str, str]` |
| 5 | **`Counter` / `Flag` 微抽象** | 遥控器模式——`Counter(state, name)` 封装 `incr()`/`value()`/`reset()`/`reached()`；`Flag` 同理 |
| 6 | **`CounterBasedBehavior`** | 计数器驱动型保底可选基类——统一计数器生命周期，子类只实现 `_compute_probabilities()` |
| 7 | `type = "soft_additive"` | 每抽固定百分点累加，`scope` 决定加给谁 |
| 8 | `type = "soft_interval"` | 区间比例爬升，进度驱动概率从「非目标」向目标转移 |
| 9 | `scope` 参数 | 四 type 共享：`featured` / `ssr` / `sr` / `r` |
| 10 | **`PityState` 抽象化** | 三层嵌套 namespace：`{behavior_name: {key: value}}`；`get()`/`set()`/`incr()` 接口 |
| 11 | 轻量扩展 | `increment_step`（C1）/ `reset_min_counter`（C2）/ `max_triggers`（C3）/ `persistence`（A2） |
| 12 | 优先级机制 | 显式 `priority` 字段（数值排序）+ 引擎层冲突检测（scope 重叠 warning） |

### 2.2 非目标

- `rotating_guarantee` 完整实现（仅预留接口 + `PityState` 支持）
- `scope` 扩展为自定义卡组（`card_group` 定义）——当前稀有度级别足够
- Box 制 / 阶梯池 / 天井 / 不重复保底 —— 不属于保底引擎职责范围
- 捕获明光式后处理（A3）—— 需后处理管道，本次不纳入

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
    scope_cards: Mapping[str, tuple[str, ...]]    # rarity → 该稀有度的具体卡牌 ID
    scope_slots: Mapping[str, tuple[str, ...]]    # rarity → 该稀有度的分布模板槽位 ID
    base_probabilities: Mapping[str, float]       # 槽位 ID → 基础概率（如 "ssr"→0.2, "ssr_alt"→0.2）

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
- `base_probabilities["ssr"]` = `0.2`——模板槽位的基础概率
- 两者分开是因为一个稀有度对应多个槽位（如 SSR = featured slot + offrate slot），概率计算需要按槽位求和，而非按具体卡牌

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
- behavior 之间可通过 `state.get("other_name", "key")` 读取对方状态（如捕获明光读取轮换保底的 `lost_5050` flag）

### 3.2 新 type 体系

| `type` | 累加方式 | 关键参数 | 状态维度 |
|--------|---------|---------|---------|
| `soft_interval` | 区间比例爬升：`new_target = target + progress × other` | `start` / `end` / `func` | 计数器 |
| `soft_additive` | 每抽固定累加：`new_scope_prob = base + increment × Δn` | `start` / `increment` | 计数器 |
| `hard` | 达到阈值后 scope 范围内 100% | `threshold` | 计数器 |
| `rotating_guarantee` | SSR 事件触发状态转移（后续计划） | `initial_win_rate` | 布尔标志 |

### 3.3 统一参数：`scope`

`scope` 取值 `"ssr"` / `"sr"` / `"r"` / `"featured"`，所有 type 共享。

- **增量分配**：`scope = "ssr"` → 增量按池子中所有 SSR 卡的基础概率权重等比分配；`scope = "featured"` → 仅分配给 featured 卡
- **重置判定**：不再硬编码 `is_ssr`，由 behavior 基于 `PityContext.reward_rarity` 和 `is_featured` 自行判定
- **`reset` 默认值**：默认 = `scope`（如 `scope = "ssr"` → `reset = "ssr"`），可显式覆盖

### 3.4 轻量扩展参数（所有 type 可选）

| 参数 | 默认值 | 含义 | 覆盖 |
|------|--------|------|------|
| `increment_step` | 1 | 每次抽卡计数器加几 | C1 计数器加速 |
| `reset_min_counter` | 0 | 计数器低于此值时不触发重置 | C2 提前出货不消耗保底 |
| `max_triggers` | 0（无限制） | 该保底最多触发几次 | C3 保底触发上限 |
| `persistence` | `"inherit"` | `"inherit"`（跨池继承）/ `"per_banner"`（每池独立） | A2 多计数器继承控制 |

### 3.5 参数 Dataclass 化

每种 `type` 配一个强类型参数 dataclass，在 TOML 解析时即完成类型校验，消除 `Dict[str, str]` 的类型丢失：

```python
@dataclass
class IntervalParams:
    start: int
    end: int
    func: str = 'linear'       # "linear" | "exp" | "step"

@dataclass
class AdditiveParams:
    start: int
    increment: float

@dataclass
class HardParams:
    threshold: int

@dataclass
class RotatingParams:
    initial_win_rate: float = 50.0
```

配置解析时：

```python
# core/config_toml.py
PARAM_REGISTRY = {
    "soft_interval": IntervalParams,
    "soft_additive": AdditiveParams,
    "hard": HardParams,
}

def _build_pity(data, store):
    for p in data.get('pity', []):
        btype = p['type']                    # 必填，无默认值——不向后兼容旧格式
        param_cls = PARAM_REGISTRY[btype]    # KeyError = 未知 type，立即报错
        params = param_cls(**p)              # TOML dict → 强类型 dataclass
        pities.append(PityDef(
            name=p['name'], btype=btype,
            params=params,                   # 强类型 dataclass
            scope=p.get('scope', 'featured'),
            ...
        ))
```

Behavior 构造时直接接收强类型参数：

```python
class AdditiveBehavior(PityBehavior):
    def __init__(self, name: str, params: AdditiveParams, scope: str, ...):
        self._start = params.start          # int，无需转换
        self._increment = params.increment  # float，无需转换
```

**收益：** `int('abc')` → dataclass 构造时立即报错 · 拼写错误 → `TypeError: unexpected keyword` · IDE 自动补全。

### 3.6 Registry 模式

对齐策略系统的 `STRATEGY_REGISTRY`，两张注册表消除 if-else：

```python
# core/pity.py

BEHAVIOR_REGISTRY: Dict[str, Type[PityBehavior]] = {
    "soft_interval": SoftIntervalBehavior,
    "soft_additive": AdditiveBehavior,
    "hard": HardPityBehavior,
    "rotating_guarantee": RotatingGuaranteeBehavior,
}

def create_behavior(pdef: PityDef, scope_cards: dict, featured_ids: set, ...) -> PityBehavior:
    """工厂函数——一行查找、一行构造。"""
    cls = BEHAVIOR_REGISTRY[pdef.btype]
    return cls(name=pdef.name, params=pdef.params, scope=pdef.scope, ...)
```

`PityEngine.__init__()` 退化为：

```python
for pdef in self.pity_defs:
    bh = create_behavior(pdef, spec.scope_cards, spec.featured_ids, ...)
    self._behaviors.append(bh)
```

**新增保底类型 = 写类 + `BEHAVIOR_REGISTRY` 加一行 + `PARAM_REGISTRY` 加一行 + 配 TOML。** 引擎零改动。

### 3.7 类结构（全景）

```
DrawInfo (frozen dataclass)                    # 不可变静态事实
  pool_id / pool_instance_id
  reward_id / reward_rarity / is_featured
  scope_cards: Mapping[str, tuple[str, ...]]    # rarity → 具体卡牌 ID
  scope_slots: Mapping[str, tuple[str, ...]]    # rarity → 模板槽位 ID
  base_probabilities: Mapping[str, float]       # 槽位 ID → 基础概率

PityContext                                     # 管道可变载体
  draw: DrawInfo                                # 只读
  current: Dict[str, float]                     # 管道概率
  state: PityState                              # 可读写

PityBehavior (ABC)                              # 独立化接口
  ├── before_draw(ctx: PityContext) -> Dict[str, float]
  ├── after_draw(ctx: PityContext) -> None
  └── is_active(ctx: PityContext) -> bool

├── CounterBasedBehavior (ABC)                   # 可选基类——计数器驱动型通用生命周期
│   ├── SoftIntervalBehavior (params: IntervalParams)
│   ├── AdditiveBehavior (params: AdditiveParams)
│   └── HardPityBehavior (params: HardParams)
└── RotatingGuaranteeBehavior (params: RotatingParams, stub)  # 不走 CounterBased

Counter / Flag                                  # 微抽象——PityState 的语法糖

PityState:                                      # 抽象 namespace 容器
  _data: Dict[str, Dict[str, Any]]
  get(name, key, default) / set(name, key, val) / incr(name, key, delta)

PityEngine:                                     # 退化为调度器
  _behaviors: List[PityBehavior]                # 外部注入
  before_draw(pool_id, state, draw_info) → adjusted_probs
  after_draw(pool_id, state, reward) → None

BEHAVIOR_REGISTRY: Dict[str, Type[PityBehavior]]    # type → 类
PARAM_REGISTRY: Dict[str, type]                     # type → 参数 dataclass
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

**设计哲学：** 三种计数器驱动型 behavior 共享同一个生命周期模式——提取共性到可选基类，子类只写概率调整逻辑。不影响非计数器型保底（`RotatingGuaranteeBehavior` 直接继承 `PityBehavior`）。

```python
class CounterBasedBehavior(PityBehavior, ABC):
    """计数器驱动型保底的通用生命周期。
    
    子类只需实现 _compute_probabilities(ctx, counter) → Dict[str, float]。
    计数器管理（增/查/重置/触发上限）统一处理。
    """

    def __init__(self, name: str, state: PityState, scope: str,
                 increment_step: int = 1, reset_min_counter: int = 0,
                 max_triggers: int = 0, persistence: str = "inherit"):
        self._name = name
        self._state = state
        self._scope = scope
        self._step = increment_step
        self._reset_min = reset_min_counter
        self._max_triggers = max_triggers
        self._persistence = persistence
        self._triggers = Counter(state, name, "triggers")  # 触发次数 key 始终固定

    # ── 子类只需实现这一个方法 ──
    @abstractmethod
    def _compute_probabilities(self, ctx: PityContext, counter: int) -> Dict[str, float]:
        """给定上下文和当前计数器值，返回调整后概率分布。"""
        ...

    # ── 计数器遥控器：每次调用根据 ctx 动态确定 key ──
    def _counter(self, ctx: PityContext) -> Counter:
        """返回当前上下文对应的计数器遥控器。
        
        persistence="inherit"  → key = "counter"
        persistence="per_banner" → key = "counter_pool_c1_b7"
        
        每次调用都新建遥控器——确保增与查始终操作同一 key。
        """
        key = f"counter_{ctx.draw.pool_instance_id}" if self._persistence == "per_banner" else "counter"
        return Counter(self._state, self._name, key)

    # ── 生命周期由基类统一管理 ──
    def before_draw(self, ctx: PityContext) -> Dict[str, float]:
        c = self._counter(ctx)
        v = c.incr(self._step)
        return self._compute_probabilities(ctx, v)

    def after_draw(self, ctx: PityContext) -> None:
        if not self._should_reset(ctx):
            return
        if self._max_triggers and self._triggers.value() >= self._max_triggers:
            return
        c = self._counter(ctx)                     # 与 before_draw 同一 key
        if c.value() < self._reset_min:
            return
        c.reset()
        self._triggers.incr()

    def _should_reset(self, ctx: PityContext) -> bool:
        """子类可覆写——默认：出了 scope 对应的稀有度就重置。"""
        if self._scope == "featured":
            return ctx.draw.is_featured
        return ctx.draw.reward_rarity == self._scope
```

**三个具体 behavior 瘦身后的对比：**

| | 当前每个类 | 使用 CounterBasedBehavior 后 |
|---|---|---|
| 行数 | ~80-100 行 | ~25-40 行（只写 `_compute_probabilities`） |
| 计数器管理 | 每个类重复一次 | 基类统一 |
| 轻量扩展参数 | 每个类重复 4 个字段 | 基类统一接收 |
| per-banner 隔离 | 每个类重复 key 逻辑 | 基类 `_counter_key()` |

`AdditiveBehavior` 瘦身示例：

```python
class AdditiveBehavior(CounterBasedBehavior):
    def __init__(self, name, state, params: AdditiveParams, scope, **kwargs):
        super().__init__(name, state, scope, **kwargs)
        self._start = params.start
        self._increment = params.increment

    def _compute_probabilities(self, ctx, counter):
        if counter < self._start:
            return ctx.current.copy()
        slots = ctx.draw.scope_slots.get(self._scope, ())
        base = sum(ctx.draw.base_probabilities.get(s, 0.0) for s in slots)
        new_prob = min(base + self._increment * (counter - self._start + 1), 1.0)
        return self._redistribute(ctx, new_prob, slots)
```

**层级关系不会混乱：** `CounterBasedBehavior` 是可选快捷方式——完全匹配计数器模式就用它，不完全匹配（如轮换保底）直接继承 `PityBehavior`。没有强制层级。

### 3.10 优先级机制

独立化后，优先级问题可在保底模块内部完全解决，无需外部介入：

**方式一：显式 `priority` 字段（主要）**

```toml
[[pity]]
name = "sr_hard"
type = "hard"
scope = "sr"
threshold = 10
priority = 10          # 数值越小越先执行

[[pity]]
name = "ssr_soft"
type = "soft_additive"
scope = "ssr"
start = 74
increment = 6.0
priority = 20          # sr_hard 调整后，ssr_soft 在其结果上继续
```

`PityEngine.__init__()` 按 `priority` 排序，不依赖 `[[pity]]` 数组的书写顺序。

**方式二：引擎内冲突检测（防御性）**

`PityEngine.__init__()` 遍历同池的所有 behavior：
- 若两个 behavior 的 `scope` 有重叠（如 `ssr` 和 `featured`）→ `warnings.warn("scope overlap")`
- 提醒配置者注意后执行的行为可能覆盖前者的概率调整

**设计决策：** 不介入冲突解决——仅提醒。管道顺序语义是有意为之的设计，后覆盖前是预期行为。配置者通过 `priority` 显式控制顺序。这与缺陷 11 的理论立场一致。

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
# 1. 不歪型区间软保底
[[pity]]
type = "soft_interval"
scope = "featured"
start = 80
end = 90
func = "linear"
reset = "featured"               # 可省略——默认 = scope

# 2. 会歪型固定累加软保底（新增主目标）
[[pity]]
type = "soft_additive"
scope = "ssr"
start = 74
increment = 6.0
# reset 默认 = "ssr"，可省略

# 3. 不歪型硬保底
[[pity]]
type = "hard"
scope = "featured"
threshold = 180

# 4. SR 保底（每 10 抽保底 SR）
[[pity]]
type = "hard"
scope = "sr"
threshold = 10

# 5. 会歪型硬保底 + 每池独立 + 仅触发一次（终末地式 120 大保底）
[[pity]]
type = "hard"
scope = "ssr"
threshold = 120
persistence = "per_banner"
max_triggers = 1

# 6. 计数器加速 + 前 N 抽不重置（示例）
[[pity]]
type = "soft_additive"
scope = "ssr"
start = 74
increment = 6.0
increment_step = 1               # 默认值，可省略
reset_min_counter = 20           # 前 20 抽出 SSR 不消耗保底

# 7. 未来：轮换保底（本次预留，暂不可用）
[[pity]]
type = "rotating_guarantee"
scope = "featured"
initial_win_rate = 50.0
```

### 3.13 实施阶段

| 阶段 | 内容 | 文件 |
|------|------|------|
| **阶段一** | `PityState` 抽象化（namespace 容器 + `get`/`set`/`incr`）+ `Counter` / `Flag` 微抽象 | `pity.py` |
| **阶段二** | `DrawInfo`（`frozen` 静态事实）+ `PityContext`（可变载体：`draw` / `current` / `state`） | `pity.py` |
| **阶段三** | `PityBehavior` 接口独立化 + `CounterBasedBehavior` 基类（含轻量扩展参数贯通） | `pity.py` |
| **阶段四** | 参数 dataclass 化（`IntervalParams` / `AdditiveParams` / `HardParams`） | `pity.py` |
| **阶段五** | `SoftIntervalBehavior` 独立化改造——继承 `CounterBasedBehavior`，接收 `IntervalParams`，只写 `_compute_probabilities()` | `pity.py` |
| **阶段六** | `HardPityBehavior` scope 化——继承 `CounterBasedBehavior`，接收 `HardParams` | `pity.py` |
| **阶段七** | `AdditiveBehavior` 实现——继承 `CounterBasedBehavior`，接收 `AdditiveParams`，只写 `_compute_probabilities()` | `pity.py` |
| **阶段八** | `BEHAVIOR_REGISTRY` + `PARAM_REGISTRY` + `create_behavior()` 工厂函数 | `pity.py` |
| **阶段九** | `PityEngine` 退化为调度器——注入 `_behaviors` 列表 + 遍历 + `priority` 排序 | `pity.py` |
| **阶段十** | `PityDef` 字段扩展 + 配置解析更新（含 `_build_pity()` 适配新字段） | `config_store.py` / `config_toml.py` |
| **阶段十一** | 配置面板 UI 更新——新增 `type`/`scope`/`increment`/轻量扩展控件 | `config_panel.py` |
| **阶段十二** | 波及文件适配——`worst_impact.py` / `batch_simulator.py` / `gacha_service.py` 等 | 多个文件 |
| **阶段十三** | 测试更新 + 文档更新 | `tests/` / `docs/` |

## 四、波及范围

### 4.1 核心改动

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/pity.py` | **重构** | DrawInfo + PityContext + PityState 抽象化 + PityBehavior 接口独立化 + 四种 behavior + BEHAVIOR_REGISTRY + Engine 退化 |
| `core/config_store.py` | **修改** | `PityDef` 字段扩展：`type`/`scope`/`increment`/`increment_step`/`reset_min_counter`/`max_triggers`/`persistence`/`priority`/`params`（dataclass 而非 dict） |
| `core/config_toml.py` | **修改** | `_build_pity()` 解析新字段 + PARAM_REGISTRY 反序列化 |
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
| `gui/config_panel.py` | **修改** | `_setup_pity_config()` UI 重构 |
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

## 五、风险

| 风险 | 缓解 |
|------|------|
| `worst_impact.py` 直接实例化原类名（`SoftPityBehavior` / `HardPityBehavior`） | 全量替换为新类名，不保留旧别名 |
| 独立化后 behavior 间状态竞争（多 behavior 同时修改 `ctx.state`） | namespace 隔离——各 behavior 操作独立 key，冲突由配置者通过 `priority` 控制 |
| `PityState` 抽象化后序列化兼容 | `to_dict()`/`from_dict()`通用——三层嵌套结构，namespace 隔离天然保证兼容 |
| `CounterBasedBehavior` 中 `_counter(ctx)` 每次动态构造——per-banner 场景下增/查 key 不一致 | `_counter(ctx)` 方法保证增与查使用同一 key 的 Counter 实例；per-banner 单元测试覆盖 counter 隔离 |
| `base_probabilities` key 语义不明确（槽位 vs 卡牌 id） | DrawInfo 显式区分 `scope_cards`（卡牌 ID）与 `scope_slots`（槽位 ID）；AdditiveBehavior 累加使用 slots |
| 配置面板 UI 改动过大 | 渐进式——先加新字段，确保必填校验 |

## 六、验收标准

- [ ] `DrawInfo` 不可变性：`frozen=True` 生效，误写编译报错
- [ ] `PityContext` 完整性：behavior 仅通过 `ctx.draw` / `ctx.current` / `ctx.state` 获取信息，不访问外部全局状态
- [ ] `PityEngine` 无保底业务逻辑——`after_draw()` 仅为 `foreach behavior: behavior.after_draw(ctx)`
- [ ] `PityState` 抽象化：behavior 通过 `get()`/`set()`/`incr()` 操作自身 namespace，引擎不预设字段类型
- [ ] `PityState` 序列化往返无损（`to_dict()` → `from_dict()`）
- [ ] `Counter` 封装正确：`incr()`/`value()`/`reset()`/`reached()` 等价直接操作 `PityState`
- [ ] `CounterBasedBehavior` 生命周期统一：三个子类（Soft/Additive/Hard）只实现 `_compute_probabilities()`，`before_draw`/`after_draw` 由基类统一
- [ ] `BEHAVIOR_REGISTRY` + `PARAM_REGISTRY` + `create_behavior()` 工厂函数正确路由所有 type
- [ ] 参数 dataclass 校验：非法类型/缺少必填字段在 TOML 解析时即报错
- [ ] `type = "soft_additive"` + `scope = "ssr"` 产出概率分布与公式一致（≥3 个抽样点校验）
- [ ] `scope = "sr"` 硬保底正确工作——第 N 抽出 SR 时重置，累加至 100% 后必出 SR
- [ ] `persistence = "per_banner"` + `max_triggers = 1` 正确限制触发次数且池间隔离
- [ ] `reset` 默认值 = `scope` 正确生效（如 `scope="ssr"` 未设 `reset` → 出 SSR 即重置）
- [ ] 同 pool 上两个不同 `name` 的同 type 保底（如 `soft1`、`soft2`），计数器完全独立不互相影响
- [ ] `priority` 字段正确控制 behavior 执行顺序（≥2 个 behavior 同池时排序验证）
- [ ] 配置面板可完整编辑所有新字段
- [ ] 现有 7 种策略在保底重构后行为无退化（集成测试）
- [ ] `worst_impact.py` / `batch_simulator.py` / `gacha_service.py` 无 import 错误
- [ ] pytest 全量通过（含新增 pity 专项测试 ≥20 用例，覆盖所有新 type/scope/轻量扩展组合）
