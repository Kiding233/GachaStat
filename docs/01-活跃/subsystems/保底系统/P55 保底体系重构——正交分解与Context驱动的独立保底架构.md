<!-- META: P55 | module:保底系统 | status:designing | last:2026-06-20 | depends:P60✅ -->

# P55 保底体系重构——behavior 实现与配置集成

> 日期：2026-06-19 | 状态：设计中
> 触发：用户请求「会歪型软保底」（全体 SSR 每抽固定增量）+ 讨论中自然延伸至保底体系整体重构
> **原 Phase 1-4（平台层——PityState/DrawInfo/CounterBasedBehavior/BEHAVIOR_REGISTRY）+ 引擎调度 已提取至 [P60](../../../02-待办/P60%20基础平台——依赖消除与下游并行化.md)。本计划保留具体 behavior 实现（SoftInterval/Additive/Hard）+ 配置/UI/波及适配。**
> 依赖：[P60](../../../02-待办/P60%20基础平台——依赖消除与下游并行化.md)（提供 PityState / DrawInfo / PityContext / Counter / Flag / CounterBasedBehavior / BEHAVIOR_REGISTRY / PityEngine 调度器）

## 一、问题

### 1.1 当前局限

当前保底体系（`core/pity.py`）存在五个结构性问题：

| # | 问题 | 影响 |
|---|------|------|
| 1 | `type = "soft"` 硬编码累加公式（`new = target + progress × other` 比例重分配），不支持替换为其他累加方式 | 无法表达「每抽固定＋6%」等增量型保底 |
| 2 | `progress` 计算和 `_apply_targeted()` 绑死在 `SoftPityBehavior.apply()` 中——方式与类一对一 | 新增累加方式必须写新类，且与旧公式耦合在同一 type 下 |
| 3 | `PityEngine.after_draw()` 硬编码 `is_ssr` 判定，生命周期逻辑外泄在引擎层 | 每加一个新保底类型就要改引擎；无法表达 SR/R 保底 |
| 4 | `PityState` 预设字段类型（仅 `counters: Dict[str, int]`），每加一种状态维度就要改数据结构 | 无法存储布尔标志、触发次数、per-banner 隔离计数——新增保底类型需要同时改 `PityState` 定义 |
| 5 | 保底行为的生命周期被 `PityEngine` 和 `PityBehavior` 割裂——`apply()` 在 behavior，`after_draw()` 在引擎 | 新增保底类型的改动散落两处，违背开闭原则 |

### 1.2 讨论结论（本次会话）

- **两个正交维度**：累加方式（怎么加）× 作用范围（加给谁）→ `type` × `scope`
- **十种 TOML type**：四种 counter 驱动（`soft_interval` / `soft_additive` / `soft_step` / `hard`）+ 六种事件驱动（`rotating` / `rotating_soft` / `rotating_cr` / `rotating_cr_soft` / `targeted` / `targeted_soft`）。`soft_interval` 和 `soft_additive` 是语法糖——TOML 解析时展开为 `deltas`，统一由 `SoftStepBehavior` 执行。`_soft` 后缀 = 自带软保底，`_cr` 后缀 = 带捕获明光（CR = Capturing Radiance，英文社区通用缩写）
- **统一 `scope` 参数**：作用于稀有度级别（`ssr` / `sr` / `r` 等，必须已在 `[rarities]` 注册），`target_featured` 布尔字段同时控制两个维度——概率调整范围（仅 featured 子集 / 全体）和计数器重置条件（仅 featured 出货 / 任意出货）。`_should_reset(ctx)` = 命中 scope 稀有度 且（`target_featured` → `is_featured` 为真；否则 → 直接通过）
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
- **保留参数**：`pools`（适用池子）· `counter_init`（初始水位，模拟开始前已垫抽数）——不动链路，`batch_simulator` 直接写 `PityState`。**`reset` 已移除**——计数器重置条件由 `target_featured` 自动推导（`true` → 仅 featured 出货重置；`false` → 任意 scope 出货重置），`reset` 的三个枚举值中 `any_ssr` 与 `scope` 语义重叠，`featured_ssr` 与 `target_featured` 语义重叠，`never` 属于里程碑系统职责
- **rotating（轮换保底/大小保底）**：事件驱动——`RotatingBehavior`，纯净 50/50 轮换，零参数
- **rotating_soft（轮换+软保底）**：`RotatingSoftBehavior(RotatingBehavior)` 子类——~25 行增量
- **rotating_cr（轮换+捕获明光）**：`RotatingCRBehavior(RotatingBehavior)` 子类——CR 状态机。**不与 rotating 并存。**
- **rotating_cr_soft（轮换+CR+软保底）**：`RotatingCRSoftBehavior(RotatingCRBehavior)` 子类——~25 行增量
- **targeted（定向保底/定轨）**：事件驱动——`TargetedBehavior`，selected_card + 命定值 + 切换规则
- **targeted_soft（定轨+软保底）**：`TargetedSoftBehavior(TargetedBehavior)` 子类——~25 行增量

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
| 7 | `type = "soft_interval"` | 语法糖——TOML 解析时展开为 deltas，统一由 `SoftStepBehavior` 执行 |
| 8 | `type = "soft_additive"` | 语法糖——同上。每抽固定百分点累加，`scope` 决定加给谁 |
| 9 | `type = "soft_step"` | 底层——RLE 压缩的逐抽增量数列 `deltas = [[n, inc], ...]`，任意形状 |
| 10 | `SoftStepBehavior` | 唯一的 counter 驱动软保底类——替代 `SoftIntervalBehavior` + `SoftAdditiveBehavior` |
| 11 | `scope` 参数 | 四 type 共享：`featured` / `ssr` / `sr` / `r` |
| 12 | **`PityState` 抽象化** | 三层嵌套 namespace：`{behavior_name: {key: value}}`；`get()`/`set()`/`incr()` 接口 |
| 13 | **`LifecycleConfig`** | 跨 type 共享的生命周期参数 dataclass：`max_triggers`（C3）+ P56 扩展 `deactivate_on_early_hit` / `depends_on` |
| 14 | **执行顺序自动推导** | 基于 type 分类（概率增加/强制出卡）+ scope 层级关系自动排序；校验分级（ConfigError / warn / 通过） |

### 2.2 非目标

- `rotating` 事件驱动行为的完整实现（P56）——P55 仅确保基础设施（`PityState` / `Flag` / 跨 behavior 读取）支持
- `scope` 扩展为自定义卡组（`card_group` 定义）——当前稀有度级别足够
- Box 制 / 阶梯池 / 天井 / 不重复保底 —— 不属于保底引擎职责范围
- **捕获明光 —— 已决策（2026-06-20）：** 独立 `type="rotating_cr"`，`RotatingBehavior` 的子类。`cr_state_probs` 为数组预留。详见 P56 §3.3。

## 三、方案

> **原 §3.1-3.9（平台层——PityState / DrawInfo / PityContext / Counter / Flag / CounterBasedBehavior / BEHAVIOR_REGISTRY / 类结构全景 / PityEngine 调度器）已提取至 [P60](../../../02-待办/P60%20基础平台——依赖消除与下游并行化.md) 块 2-4。** 下文直接从执行顺序开始——此为 P55 保留的专属内容（执行顺序推导依赖具体 behavior 的 type 分类，属于 P55 而非平台层）。

### 3.1 执行顺序——矩阵规则自动推导（来源：原 §3.10）

**设计决策：不再使用 `priority` 数字字段。** 执行顺序由 behavior 的 type 分类 + scope 层级关系自动推导。配置者无需手写排序数字。

#### 3.1.1 矩阵分析

两个 behavior 的交互由两个维度决定：**驱动方式**（counter vs 事件）× **scope 关系**（无关 / 重叠）。

| A \ B | 概率增加（soft_*、rotating_soft） | 重分配（rotating/targeted/rotating_cr） | 强制出卡（hard） |
|-------|-------------------|-------------------------|-----------------|
| **soft_* / rotating_soft** | 叠加——后执行者继续调整 | soft 先——先增加总出率，再分配内部比例 | soft 先——hard 设 100% 覆盖 soft |
| **rotating/targeted/rotating_cr** | rotating 后（同上） | 同 scope → 无意义，校验时 warn | rotating 先——分配完再 hard 覆盖 |
| **hard** | hard 后（同上） | hard 后（同上） | 同 scope → **ConfigError** |

**排序规则：soft / rotating_soft → rotating/targeted/rotating_cr → hard。** 先增加 scope 总出率，再分配内部比例，最后强制覆盖。每个 type 内部按稀有度降序。`rotating` / `targeted` / `rotating_cr` 为同一优先级，其中同 scope 两个以上 → ConfigError。

| scope 关系 | 处理 |
|-----------|------|
| **无关**（如 `ssr` ∪ `sr`，互不重叠） | 低稀有度保底只从 ≤ 自身稀有度取概率——不会碰高稀有度。顺序无关 |
| **包含**（如 `featured` ⊂ `ssr`） | 自动：高稀有度在前，同层 soft→rotating→hard |
| **相同** | 按 type 规则（见上表） |

#### 3.1.2 自动推导规则

引擎在构造时自动排序，不依赖配置者手写数字：

```python
def _resolve_order(behaviors: List[PityBehavior]) -> List[PityBehavior]:
    """基于 type 分类 + scope 层级自动推导执行顺序。"""
    return sorted(behaviors, key=lambda bh: (
        _rarity_rank(bh.scope),      # 高稀有度排前；featured → rank 0
        _type_order(bh),              # soft / rotating_soft(0) < rotating / rotating_cr / targeted(1) < hard(2)
    ))

def _rarity_rank(scope: str) -> int:
    return rarity_rank_map[scope]   # KeyError = 校验层 bug

def _type_order(bh: PityBehavior) -> int:
    if bh.is_soft:     return 0
    if bh.is_event_driven: return 1   # rotating / rotating_soft / rotating_cr / targeted
    if bh.is_hard:     return 2
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

#### 3.1.3 校验分级

```python
def _validate_behaviors(behaviors: List[PityBehavior]) -> None:
    for a, b in itertools.combinations(behaviors, 2):
        if not _scope_overlap(a.scope, b.scope):
            continue
        if a.is_hard and b.is_hard and a.scope == b.scope:
            raise ConfigError(...)
        if a.is_event_driven and b.is_event_driven and a.scope == b.scope:
            raise ConfigError(...)
        if a.is_soft and b.is_soft and a.type == b.type and a.scope == b.scope:
            raise ConfigError(...)
        if a.is_soft and b.is_soft and a.type != b.type and a.scope == b.scope:
            warnings.warn(...)
```

| 场景 | 行为 |
|------|------|
| scope 无关 | 通过——自动排序，低稀有度不碰高稀有度 |
| scope 重叠 + 有 hard | 通过——自动排序（soft 前 hard 后） |
| 同 scope 两个 hard | **ConfigError**——无意义 |
| 同 scope 两个事件驱动型（rotating/rotating_soft/rotating_cr/targeted） | **ConfigError**——后者覆盖前者 |
| 同 scope 同 type 两个 soft | **ConfigError**——管道叠加导致后者覆盖前者 |
| 同 scope 不同 type 两个 soft | **warn**——允许但提醒可能非有意 |

### 3.2 `AdditiveBehavior` 数学公式（来源：原 §3.11）

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

### 3.3 配置语法

```toml
# ── 稀有度层级注册（P60 已交付 [rarities] 段 —— 见 P60 块5） ──
[rarities]
ranks = [
    ["UR", "SSR"],   # rank 0 — 最高，平级
    ["SR"],           # rank 1
    ["R"],            # rank 2
]

# ── 保底配置 ──

# 1. 区间软保底（语法糖——解析层展开为 deltas）
#    start=74, end=90 → deltas = [[73, 0.0], [17, 5.88]]
[[pity]]
type = "soft_interval"
scope = "ssr"
target_featured = true
start = 74
end = 90
counter_init = 0                  # 可选，默认 0——模拟开始前已垫抽数

# 2. 累加软保底（语法糖——解析层展开为 deltas）
[[pity]]
type = "soft_additive"
scope = "ssr"
start = 74
increment = 6.0

# 3. 自定义逐抽增量——RLE 压缩描述任意形状（底层）
[[pity]]
type = "soft_step"
scope = "ssr"
deltas = [
    [73, 0.0],     # 抽数 1-73：不增
    [5, 1.5],      # 抽数 74-78：每抽 +1.5%
    [6, 3.0],      # 抽数 79-84：每抽 +3.0%
    [5, 6.0],      # 抽数 85-89：每抽 +6.0%
    [1, 50.0],     # 抽数 90：+50%（总计跳到 100%）
]

# 5. 不歪型硬保底（仅 featured）
[[pity]]
type = "hard"
scope = "ssr"
target_featured = true
threshold = 180

# 6. SR 保底（每 10 抽保底 SR）
[[pity]]
type = "hard"
scope = "sr"
threshold = 10

# 7. 硬保底 + 仅触发一次（终末地 120 大保底）
[[pity]]
type = "hard"
scope = "ssr"
threshold = 120
max_triggers = 1

# 8. 轮换保底——基础二态轮换（纯净，无捕获明光）
# featured 占比由基础概率分布决定——无需 initial_win_rate
[[pity]]
type = "rotating"
scope = "ssr"

# 9. 轮换+软保底——RotatingSoftBehavior（74→90 + 50/50）
[[pity]]
type = "rotating_soft"
scope = "ssr"
soft_start = 74
soft_end = 90

# 10. 轮换+捕获明光——RotatingCRBehavior（原神 5.0+）
[[pity]]
type = "rotating_cr"
scope = "ssr"
cr_counter_threshold = 3
cr_base_rate = 0.00018
cr_state_probs = [0.0, 0.0, 0.0, 1.0]

# 11. 轮换+CR+软保底——RotatingCRSoftBehavior
[[pity]]
type = "rotating_cr_soft"
scope = "ssr"
soft_start = 74
soft_end = 90
cr_counter_threshold = 3
cr_base_rate = 0.00018
cr_state_probs = [0.0, 0.0, 0.0, 1.0]

# 12. 定向保底（定轨）——小保底 featured 占比由基础分布决定
[[pity]]
type = "targeted"
scope = "ssr"
fate_threshold = 1
switch_allowed = true
switch_resets_progress = true

# 13. 定轨+软保底——TargetedSoftBehavior
[[pity]]
type = "targeted_soft"
scope = "ssr"
soft_start = 63
soft_end = 80
fate_threshold = 1
switch_allowed = true
switch_resets_progress = true
```

#### 3.3.1 TOML → PityDef 解析

```python
SOFT_TYPES = {'soft_interval', 'soft_additive', 'soft_step'}

def _expand_soft_to_deltas(raw):
    """语法糖展开：interval/additive → deltas"""
    if raw['type'] == 'soft_interval':
        n = raw['end'] - raw['start'] + 1
        return [[raw['start'] - 1, 0.0], [n, 100.0 / n]]
    if raw['type'] == 'soft_additive':
        # 每抽固定 +increment%，累加到 ≥100% 自然封顶
        # 例：start=74, increment=6.0 → ceil(100/6)=17 抽 → 74-90 每抽+6%
        n_additive = math.ceil(100.0 / raw['increment'])
        return [[raw['start'] - 1, 0.0], [n_additive, raw['increment']]]
    if raw['type'] == 'soft_step':
        return raw['deltas']


def _build_pity_def(raw):
    """单条 [[pity]] → PityDef。"""

    btype = raw['type']
    scope = raw.get('scope', 'ssr')

    # —— 保留参数，不做语义变换 ——
    pools     = raw.get('pools', [])              # 适用池子
    cinit     = raw.get('counter_init', 0)        # 初始水位
    # reset 已移除——计数器重置条件由 target_featured 自动推导

    # —— counter 驱动 ——
    target_featured = raw.get('target_featured', False)
    deltas  = _expand_soft_to_deltas(raw) if btype in SOFT_TYPES else None
    threshold = raw.get('threshold', 0)           # hard 保底抽数

    # —— 事件驱动 ——
    soft_start = raw.get('soft_start')            # rotating_soft 等
    soft_end   = raw.get('soft_end')
    cr_counter_threshold = raw.get('cr_counter_threshold', 3)
    cr_base_rate         = raw.get('cr_base_rate', 0.0)
    cr_state_probs       = raw.get('cr_state_probs')
    # targeted 参数由 P56 定义

    return PityDef(
        name=raw.get('name', ''),
        btype=btype, scope=scope,
        target_featured=target_featured,
        pools=pools, counter_init=cinit,
        deltas=deltas, threshold=threshold,
        soft_start=soft_start, soft_end=soft_end,
        cr_counter_threshold=cr_counter_threshold,
        cr_base_rate=cr_base_rate, cr_state_probs=cr_state_probs,
    )
```

两个保留参数语义不变：
- `pools`：字符串数组 → `PityDef.pools`
- `counter_init`：int → `PityDef.counter_init`，`batch_simulator` 写 `PityState`

`reset` 已移除——计数器重置条件由 `target_featured` 自动推导：`_should_reset(ctx)` = 命中 scope 稀有度 且（`target_featured=true` → `is_featured` 为真；`false` → 直接通过）

目标分布（`target_distribution`）→ 替换为 `scope` + `target_featured`。

### 3.4 实施阶段

> 原 Phase 1-4（平台层）和微型任务已提取至 [P60](../../../02-待办/P60%20基础平台——依赖消除与下游并行化.md)。以下为 P55 保留的实施阶段。

| 阶段 | 内容 | 文件 |
|------|------|------|
| **阶段五** | `SoftStepBehavior(CounterBasedBehavior)` 实现——唯一的 counter 驱动软保底类，RLE deltas 驱动（~50 行） | `pity.py` |
| **阶段六** | TOML 糖展开 `_expand_soft_to_deltas()`——`soft_interval`（start/end → deltas）/ `soft_additive`（start/increment → deltas）（~15 行） | `config_toml.py` |
| **阶段七** | `HardPityBehavior` scope 化——继承 `CounterBasedBehavior` | `pity.py` |
| **阶段八** | BEHAVIOR_REGISTRY 条目更新——`soft_interval` / `soft_additive` / `soft_step` / `hard` + 事件驱动 6 种参数元数据完整化（事件驱动类 = `None` stub——P56 交付） | `pity.py` |
| **阶段九** | `_resolve_order()` 自动排序 + `_validate_behaviors()` 校验 | `pity.py` |
| **阶段十** | `PityDef` 字段扩展 + 配置解析更新（`[rarities]` 解析 + `_build_pity()` 适配 + scope 注册校验 + `counter_init` 解析） | `config_store.py` / `config_toml.py` |
| **阶段十一** | 配置面板 UI 更新——新增 `type`/`scope`/`deltas`/轻量扩展控件 | `config_panel.py` |
| **阶段十二** | 波及文件适配——`worst_impact.py` / `batch_simulator.py` / `gacha_service.py` 等 | 多个文件 |
| **阶段十三** | 测试更新 + 文档更新 | `tests/` / `docs/` |

## 四、波及范围

### 4.1 核心改动

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/pity.py` | **重构** | 两种 counter behavior（`SoftStepBehavior` / `HardPityBehavior`）+ BEHAVIOR_REGISTRY 条目更新（4 种 counter + 6 种事件驱动）+ `_resolve_order()` + `_validate_behaviors()` |
| `core/config_store.py` | **修改** | `PityDef` 字段扩展：`type`/`scope`/`max_triggers`/`params`（`Dict[str, Any]`）+ `LifecycleConfig` |
| `core/config_toml.py` | **修改** | `[rarities]` 解析 + `_build_pity()` 适配新字段（`type`/`scope` 等）+ scope 注册校验 + `counter_init` 透传 |
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

### 4.4 UI 适配

#### 4.4.1 通用控件（所有 type）

| 控件 | 类型 | 来源 | 说明 |
|------|:---:|------|------|
| `type` | 下拉框 | `BEHAVIOR_REGISTRY` 所有条目 | 选项：10 种 type。切换时动态显隐下方专属控件 |
| `scope` | 下拉框 | `ConfigStore.rarity_ranks` | 仅稀有度名（`ssr`/`sr`/`r`），无 `featured` |
| `target_featured` | 复选框 | — | 默认不勾选。rotating 家族禁用并强制勾选 |
| `pools` | 文本编辑 | — | 池子名，逗号分隔 |
| `counter_init` | QSpinBox | — | 0–200，默认 0。仅 counter 驱动型（soft_*/hard）启用 |
| — | — | — | `reset` 已移除——计数器重置由 `target_featured` 控制：勾选 → 仅 featured 出货重置；不勾选 → 任意 scope 出货重置 |

#### 4.4.2 type 切换——动态显隐

```
选中 type                 显示                               隐藏
──────────────────────────────────────────────────────────────────
soft_interval          start / end                         deltas
soft_additive          start / increment                   deltas
soft_step              deltas 编辑器                       start/end/increment
hard                   threshold                            —
rotating               （无——零参数）                       —
rotating_soft          soft_start / soft_end                —
rotating_cr            cr_counter_threshold / cr_base_rate
                       / cr_state_probs                     —
rotating_cr_soft       soft_start / soft_end
                       + cr_counter_threshold / cr_base_rate
                       / cr_state_probs                     —
targeted               fate_threshold / switch_allowed
                       / switch_resets_progress              —
targeted_soft          soft_*（三态——见 P56  §3.4 soft 参数）
                       + targeted 全部字段                    —
```

#### 4.4.3 deltas 编辑器（soft_step）

RLE 数组 `[[n, inc], ...]` 用表格控件：

| 抽数段 | 每抽增量(%) |
|:---:|:---:|
| `73` | `0.0` |
| `5` | `1.5` |
| `6` | `3.0` |
| … | … |

两列 QTableWidget，行可增删。保存时序列化为 `deltas` 数组。

#### 4.4.4 联动校验

| 条件 | 行为 |
|------|------|
| `type` = rotating 家族 | `target_featured` 禁用 + 强制勾选 |
| `type` = hard + scope = sr/r | `target_featured` 禁用（低稀有度无 featured 概念） |
| `type` = soft_interval + start ≥ end | 红色边框 + 保存时拒绝 |
| `scope` = sr/r + target_featured = True | 黄色警告「低稀有度通常无 featured 子集」 |
| `counter_init` > 0 且 type 无计数器 | 禁用控件 |

#### 4.4.5 向后兼容

旧 `scope = "featured"` → 解析时自动迁移：`scope` = 池子最高稀有度，`target_featured = True`，记录 warning。
旧 `reset_condition` → 丢弃——`_should_reset()` 由 `target_featured` 自动推导，无需手动配置。

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
| `PityEngine.after_draw()` — `is_ssr` 判定 + 三级 `reset_condition` | `pity.py:246-264` | **重构**。P55 移除 `reset_condition`（`_should_reset()` 由 `target_featured` 自动推导），`after_draw()` 退化为 `foreach behavior: bh.after_draw(ctx)` |
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
| 计数器重置条件 | `_should_reset(ctx)` = 命中 scope 稀有度 且（`target_featured=true` → `is_featured` 为真），无需独立 `reset` 参数 | 不要加 inter-behavior 重置传播协议 |
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
- [ ] `_should_reset()` 由 `target_featured` 控制：`target_featured=true` → 仅 featured 出货重置；`false` → 任意 scope 出货重置
- [ ] 同 pool 上两个不同 `name` 的同 type 保底（如 `soft1`、`soft2`），计数器完全独立不互相影响
- [ ] `[rarities]` 解析正确——`rarity_rank` 映射生成、平级同 rank、未注册 scope → ConfigError
- [ ] 自动推导：`_resolve_order()` 正确排序——高稀有度先执行、同稀有度 soft 在 hard 前
- [ ] 校验分级：同 scope 两个 hard → ConfigError；同 scope 两个事件驱动型（rotating/rotating_soft/rotating_cr/targeted）→ ConfigError；同 scope 同 type 两个 soft → ConfigError；同 scope 不同 type 两个 soft → warn
- [ ] 稀有度层级保护：`scope="SR"` 的增量不着色 `rank < SR_rank` 的稀有度（如 UR/SSR）
- [ ] 配置面板可完整编辑所有新字段
- [ ] 现有 7 种策略在保底重构后行为无退化（集成测试）
- [ ] `worst_impact.py` / `batch_simulator.py` / `gacha_service.py` 无 import 错误
- [ ] pytest 全量通过（含新增 pity 专项测试 ≥20 用例，覆盖所有新 type/scope/轻量扩展组合）
