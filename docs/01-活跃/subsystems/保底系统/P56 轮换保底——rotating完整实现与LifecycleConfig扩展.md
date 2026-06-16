<!-- META: P56 | module:保底系统 | status:designing | last:2026-06-17 -->

# P56 事件驱动保底——rotating + targeted 完整实现 + LifecycleConfig 扩展

> 日期：2026-06-15 | 状态：设计中（2026-06-17 更正——捕获明光 ≠ rotating 软变体；移除 §3.3 错误归类；loss_streak 独立 type 归入后续计划）
> 依赖：P55 保底体系重构（基础设施——DrawInfo / PityContext / PityState / Counter / Flag / CounterBasedBehavior）
> 触发：调研 15 款主流抽卡游戏——事件驱动型保底机制 + behavior 间生命周期依赖 + 定轨统一建模

## 一、问题

P55 提供了三种 counter 驱动的基础保底（`soft_interval` / `soft_additive` / `hard`）+ 两种事件驱动保底的 stub（`rotating` / `targeted`）。本计划交付两者的完整实现及 `CounterBasedBehavior` 的生命周期扩展。

**rotating 和 targeted 的共性与差异：**

| | rotating | targeted |
|---|---------|---------|
| 驱动方式 | SSR 事件 | SSR 事件 |
| 概率操作 | 重分配 featured/offrate 内部比例 | 同 rotating——共享 `_redistribute_scope()` |
| 目标锁定 | 无——featured 全体 | 有——锁定单张 selected_card |
| 状态机制 | guaranteed flag + losses counter | guaranteed flag + losses counter + fate_points + selected_card |
| 切换支持 | 不适用 | switch_allowed / switch_resets_progress |
| 跨期继承 | 由 `pools` 字段控制作用域 | 同——`pools` 就是继承边界，无需额外参数 |

两者平级继承 `PityBehavior`，不互为父子。概率重分配算法提取为模块级 `_redistribute_scope()` 供两者共用。

| 机制 | 本质 | 本计划交付方式 |
|------|------|--------------|
| 大小保底轮换 | SSR 事件 → 二态 flag 翻转 | `RotatingBehavior`（`loss_increment=50`） |
| 捕获明光 | ~~SSR 事件 → 多态渐进爬升~~ → **见更正 §3.3**：连歪计数器，非 rotating 变体 | ❌ 本计划**不实现**——需 `loss_streak` type（手册 G17） |
| 定轨（原神式） | SSR 事件 → 命中特定卡片才重置 + 命定值累积 | `TargetedBehavior`——`fate_threshold=1` |
| 定轨（绝区零式） | 同上 + 切换目标不清零 | `TargetedBehavior`——`fate_threshold=1` + `switch_resets_progress=false` |
| 常驻自选（鸣潮式） | 100% 不歪——scope 全部分配给选中卡 | `TargetedBehavior`——`fate_threshold=0`（无累积过程，始终保证） |
| 提前命中永久失效 | 阈值前命中即关闭——终末地 120 | `LifecycleConfig.deactivate_on_early_hit` |
| 依赖激活 | 另一 behavior 首次命中后激活——终末地 240 | `LifecycleConfig.depends_on` + 引擎声明式传播 |

**`fate_threshold=0` 的语义：** 没有「累积→触发」的过程——命定值始终 ≥ 阈值，`before_draw` 始终将 scope 内概率全部分配给 `selected_card` 对应的槽位。等价于「出金即目标」。切换目标行为由 `switch_allowed` / `switch_resets_progress` 控制——因为无进度可清，切换代价为零。

## 二、目标

| # | 交付 | 说明 |
|---|------|------|
| 1 | `RotatingBehavior` 完整实现 | 事件驱动——SSR 时状态转移。`loss_increment` 控制单次歪后 featured 提升幅度：50=一次跳满到 100%（二态跳变）。**注：捕获明光不在此列——见 §3.3 更正** |
| 2 | `TargetedBehavior` 完整实现 | 定轨——独立于 rotating，覆写 `_is_hit()` 判定 `selected_card` + 命定值计数器 + 切换规则。`selected_card` 由策略通过 `NonDrawAction` 运行时设定 |
| 3 | `_redistribute_scope()` 工具函数 | 模块级函数——供 rotating 和 targeted 共用 featured/offrate 概率重分配 |
| 4 | `LifecycleConfig` 扩展 | 新增 `deactivate_on_early_hit`（提前命中永久关闭） + `depends_on`（依赖另一 behavior 首次命中后激活）——用于 `CounterBasedBehavior` 子类 |
| 5 | 引擎声明式依赖传播 | `PityEngine` 构造时解析 `depends_on` 关系 → `_activation_graph`；`after_draw` 中自动激活依赖方——消除反向耦合 |
| 6 | `[[pool]].epitomizable_cards` | 池子级配置——显式声明哪些卡可被定轨，默认为空。不从 featured 推导 |

## 三、方案

### 3.1 RotatingBehavior——事件驱动的轮换保底

不继承 `CounterBasedBehavior`——无计数器。SSR 事件触发状态转移。不改变 SSR 总出率，只重分配 featured/非featured 的内部概率权重。

```python
class RotatingBehavior(PityBehavior):
    """事件驱动的轮换保底。

    内部状态：
      - guaranteed flag：当前是否处于大保底
      - losses counter：累计歪次数（供外部 `loss_streak` behavior 读取——本计划不实现 capture radiance）
      - lost_5050 flag：供外部读取（P55 跨 behavior 读取基础设施）
    """

    def __init__(self, name, state, scope="ssr",
                 initial_win_rate=50.0, loss_increment=50.0):
        self._name = name
        self._scope = scope              # 稀有度层级（如 "ssr"）——不再是 "featured"
        self._win_rate = initial_win_rate / 100.0
        self._increment = loss_increment / 100.0
        self._guaranteed = Flag(state, name, "guaranteed")
        self._losses = Counter(state, name, "losses")
        self._lost_flag = Flag(state, name, "lost_5050")

    def before_draw(self, ctx):
        """重分配 scope 内部 featured/非featured 比例，不改变 scope 总概率。"""
        total = self._scope_total_prob(ctx)
        if total <= 0:
            return ctx.current.copy()

        featured_slots = self._featured_slots(ctx)
        if not featured_slots:
            return ctx.current.copy()

        if self._guaranteed.is_set():
            # 大保底：featured 占 100%
            featured_ratio = 1.0
        else:
            # 小保底：根据累计歪次数计算 featured 占比
            featured_ratio = min(
                self._win_rate + self._increment * self._losses.value(),
                1.0
            )

        return self._redistribute_scope(ctx, featured_ratio, total, featured_slots)

    def after_draw(self, ctx):
        if not self._is_trigger_rarity(ctx.draw.reward_rarity, ctx):
            return
        if self._is_hit(ctx):
            self._guaranteed.clear()
            self._lost_flag.clear()
            self._losses.reset()          # ← 命中时清零歪计数器，回归初始 featured 占比
        else:
            self._guaranteed.set()
            self._lost_flag.set()
            self._losses.incr()

    def _is_hit(self, ctx):
        """子类可覆写——默认：出了 featured 就算命中。"""
        return ctx.draw.is_featured

    def _is_trigger_rarity(self, rarity, ctx):
        """rotating 由 scope 对应稀有度的事件触发。
        如 scope='ssr' → SSR 出货时触发状态转移；scope='sr' → SR 出货时触发。
        不再硬编码 rank==0——触发稀有度与 scope 一致。子类可覆写。"""
        return rarity == self._scope

    def _scope_total_prob(self, ctx):
        """scope 在当前概率分布中的总概率。"""
        slots = ctx.draw.scope_slots.get(self._scope, ())
        return sum(ctx.current.get(s, 0.0) for s in slots)

    def _featured_slots(self, ctx):
        """scope 内部标记为 featured 的槽位。"""
        return ctx.draw.featured_slots.get(self._scope, ())

    def _redistribute_scope(self, ctx, featured_ratio, total, featured_slots):
        """在 featured/非featured 之间重分配 scope 总概率。"""
        result = ctx.current.copy()
        featured_total = total * featured_ratio
        non_featured_total = total - featured_total

        for s in featured_slots:
            result[s] = featured_total / len(featured_slots)

        non_featured_slots = [
            s for s in ctx.draw.scope_slots.get(self._scope, ())
            if s not in featured_slots
        ]
        if non_featured_slots:
            for s in non_featured_slots:
                result[s] = non_featured_total / len(non_featured_slots)

        return result
```

~60 行。`loss_increment=50` = 歪一次后 featured 跳满到 100%（二态跳变）。

> ⚠️ 初版在此处放置了 `loss_increment=5` 的「软 rotating」示例并标注为捕获明光——**错误**。捕获明光不是 rotating 变体（见 §3.3 更正）。`loss_increment` 仅控制单次歪后的 featured 增幅，不建模连歪计数逻辑。

```toml
# rotating——大小保底（原神式角色池）
[[pity]]
type = "rotating"
scope = "ssr"
initial_win_rate = 50.0
loss_increment = 50.0          # 歪一次 → featured 跳满到 100%

# rotating——光锥池（星铁式 75/25）
[[pity]]
type = "rotating"
scope = "ssr"
initial_win_rate = 75.0
loss_increment = 50.0          # 歪一次 → featured 跳满到 100%
```

### 3.2 TargetedBehavior（定向保底/定轨）——独立事件驱动

与 `RotatingBehavior` 平级继承 `PityBehavior`，共享 `_redistribute_scope()` 工具函数。不继承 `RotatingBehavior`——两者的共同点仅在于概率重分配算法。

**与 RotatingBehavior 的差异点：**

| | RotatingBehavior | TargetedBehavior |
|---|---|---|
| `_is_hit()` | `ctx.draw.is_featured` | `reward_id == selected_card` |
| 状态 | guaranteed flag + losses | guaranteed + losses + fate_points + selected_card |
| 切换 | 不适用 | switch_allowed / switch_resets_progress |
| 不定轨 | 不适用 | selected_card=None → 不累积、不翻转 |

```python
class TargetedBehavior(PityBehavior):
    """事件驱动的定向保底（定轨）。

    内部状态：
      - selected_card：目标卡牌 ID（由策略 NonDrawAction 设定，可从 PityState 读取）
      - guaranteed flag：命定值满后的大保底
      - losses counter：累计歪次数
      - fate_points counter：命定值累积
    """

    def __init__(self, name, state, scope="ssr",
                 initial_win_rate=50.0, loss_increment=50.0,
                 fate_threshold=1, switch_allowed=True,
                 switch_resets_progress=True):
        self._name = name
        self._state = state
        self._scope = scope
        self._win_rate = initial_win_rate / 100.0
        self._increment = loss_increment / 100.0
        self._fate_threshold = fate_threshold
        self._switch_allowed = switch_allowed
        self._switch_resets_progress = switch_resets_progress
        self._guaranteed = Flag(state, name, "guaranteed")
        self._losses = Counter(state, name, "losses")
        self._lost_flag = Flag(state, name, "lost_5050")
        self._fate_points = Counter(state, name, "fate_points")
        # selected_card 不从构造参数传入——策略通过 NonDrawAction 设定
        # PityState[name]["selected_card"] 初始为 None（不定轨状态）

    def before_draw(self, ctx):
        """重分配 scope 内部 featured/非featured 比例 + 命定值保证检查。"""
        total = self._scope_total_prob(ctx)
        if total <= 0:
            return ctx.current.copy()

        featured_slots = self._featured_slots(ctx)
        if not featured_slots:
            return ctx.current.copy()

        selected = ctx.state.get(self._name, "selected_card")
        if self._guaranteed.is_set() or (
            selected and self._fate_points.value() >= self._fate_threshold
        ):
            # 大保底状态——featured 占 100%，且进一步收窄至 selected_card
            featured_ratio = 1.0
            # 若命定值触发，将 featured 槽位收窄到 selected_card 对应的槽位
            targeted_slots = self._resolve_selected_slots(selected, featured_slots, ctx)
            return _redistribute_scope(ctx, featured_ratio, total, targeted_slots)
        else:
            featured_ratio = min(
                self._win_rate + self._increment * self._losses.value(),
                1.0
            )
            return _redistribute_scope(ctx, featured_ratio, total, featured_slots)

    def after_draw(self, ctx):
        if not self._is_trigger_rarity(ctx.draw.reward_rarity, ctx):
            return

        selected = ctx.state.get(self._name, "selected_card")
        if selected is None:
            return   # 不定轨 → 不累积、不翻转状态

        if self._is_hit(ctx):
            self._fate_points.reset()
            self._guaranteed.clear()
            self._lost_flag.clear()
            self._losses.reset()
            return

        # 出 SSR 但不是目标 → 累积命定值 + 维护 losses
        self._fate_points.incr()
        self._guaranteed.set()
        self._lost_flag.set()
        self._losses.incr()

    def _is_hit(self, ctx):
        selected = ctx.state.get(self._name, "selected_card")
        if selected is None:
            return False
        return ctx.draw.reward_id == selected

    def _resolve_selected_slots(self, selected, featured_slots, ctx):
        """将 featured 槽位收窄为仅包含 selected_card 对应的槽位。"""
        if selected is None:
            return featured_slots
        for slot in featured_slots:
            if slot in ctx.draw.scope_cards.get(self._scope, ()):
                if selected == slot:  # 简化：假设 slot ID = card ID（对齐当前 base_probabilities key 语义）
                    return (slot,)
        return featured_slots  # 回退——selected 不在 featured 中

    def _is_trigger_rarity(self, rarity, ctx):
        return rarity == self._scope

    def _scope_total_prob(self, ctx):
        slots = ctx.draw.scope_slots.get(self._scope, ())
        return sum(ctx.current.get(s, 0.0) for s in slots)

    def _featured_slots(self, ctx):
        return ctx.draw.featured_slots.get(self._scope, ())


def _redistribute_scope(ctx, featured_ratio, total, featured_slots):
    """在 featured/非featured 之间重分配 scope 总概率。
    供 RotatingBehavior 和 TargetedBehavior 共用。"""
    result = ctx.current.copy()
    featured_total = total * featured_ratio
    non_featured_total = total - featured_total

    for s in featured_slots:
        result[s] = featured_total / len(featured_slots)

    non_featured_slots = [
        s for s in ctx.draw.scope_slots.get(ctx.draw.reward_rarity, ())
        if s not in featured_slots
    ]
    if non_featured_slots:
        for s in non_featured_slots:
            result[s] = non_featured_total / len(non_featured_slots)

    return result
```

~80 行。`switch_allowed` / `switch_resets_progress` 在 `NonDrawAction` 分发时由 `gacha_service` 读取本 behavior 配置执行；behavior 本身不处理切换逻辑——切换由策略驱动、模拟循环执行。

### 3.3 捕获明光 ≠ rotating —— 更正

> ⚠️ **2026-06-17 更正：** 初版错误地将捕获明光归类为 `RotatingBehavior` 的「软」变体。经手册审核交叉验证后确认——**捕获明光不能用 rotating 建模。**

**错误根源：** rotating 是 2 状态机（只记忆上一次 SSR 是歪还是胜），捕获明光是 4 状态连歪计数器（连续歪 0→1→2→3 次→触发）。

```
rotating 状态空间:         捕获明光状态空间:
  [normal] ←→ [guaranteed]    0_loss → 1_loss → 2_loss → 3_loss → trigger
  (2 状态，一阶马尔可夫)         (4 状态，三阶马尔可夫)
```

`loss_increment=5` 产生的是 50%→55%→60%→65%→… 的**概率梯度**——每次歪后 win_rate 略增，分布平滑。但捕获明光的实际行为是**离散阈值**——极低基础触发率 (0.018%) + 三次连歪后 100% 触发。两者分布形状根本不同，一阶系统无法等价三阶系统。

**正确建模方向：** 需要新的 `loss_streak` type——独立于 rotating，追踪 rotating 的连续失败事件数，到阈值后强制转胜。这不是 rotating 的「软模式」，而是与 rotating **并行运作**的独立保底行为。

```toml
# rotating：承担 50/50 → guaranteed 的基础大小保底（不变）
[[pity]]
type = "rotating"
name = "char_5050"
initial_win_rate = 50.0
loss_increment = 50.0

# loss_streak：叠加在 rotating 之上——计数 rotating 的连续失败次数
[[pity]]
type = "loss_streak"          # ← 新 type
name = "capturing_radiance"
track = "char_5050"           # 追踪哪个 rotating 的失败事件
threshold = 3                 # 连续失败 3 次 → 触发
base_rate = 0.018             # 基础随机触发率（极低）
```

**本计划不实现 `loss_streak`——但标记为应实现、待讨论方案。** 实现方向（待定）：
- 方案 A：独立 `LossStreakBehavior`——追踪 rotating 的连续失败事件，threshold=3 时 force_win
- 方案 B：内嵌到 `RotatingBehavior`——增加 `loss_streak_threshold` 参数
- 方案 C：事件回调——`on_n_consecutive_losses(3)` → 注入 force_win

本计划仅实现 `RotatingBehavior`（大小保底）和 `TargetedBehavior`（定轨）。

### 3.4 LifecycleConfig 扩展 + 引擎声明式依赖传播

#### 3.4.1 LifecycleConfig 扩展

P55 定义了 `LifecycleConfig(max_triggers=0)`。P56 扩展两个参数：

```python
@dataclass
class LifecycleConfig:
    """跨 type 共享的生命周期参数。P55 定义，P56 扩展 deactivate_on_early_hit / depends_on。"""
    max_triggers: int = 0                         # 最多触发几次（0 = 无限）。耗尽后 _active 置 False（P55 已实现）
    deactivate_on_early_hit: bool = False         # 提前命中后永久关闭（仅 hard type，由 HardPityBehavior 覆写实现）
    depends_on: Optional[str] = None              # 依赖另一 behavior 首次命中后激活（引擎校验引用完整性）
```

**`deactivate_on_early_hit`——终末地 120 大保底（仅 `type="hard"` 有效）：**

`deactivate_on_early_hit` 依赖 `self._threshold` 判定「提前」——该属性仅在 `HardPityBehavior` 中定义。逻辑下沉到子类覆写 `after_draw` 中，而非放在基类：

```python
# HardPityBehavior 覆写 after_draw——加入提前命中停用
class HardPityBehavior(CounterBasedBehavior):
    def after_draw(self, ctx):
        if not self._active.is_set():
            return
        if self._should_reset(ctx):
            c = self._counter()
            if self._lifecycle.deactivate_on_early_hit and c.value() < self._threshold:
                self._active.clear()       # 提前命中 → 永久关闭
                return
            # 正常重置逻辑（max_triggers → 基类已处理，此处覆写需重复）
            if self._lifecycle.max_triggers and self._triggers.value() >= self._lifecycle.max_triggers:
                self._active.clear()
                return
            c.reset()
            self._triggers.incr()
```

**配置层校验：** `deactivate_on_early_hit = true` 仅允许配合 `type = "hard"`——soft_interval / soft_additive 使用此参数 → ConfigError。

**`depends_on`——终末地 240 信物保底：**

依赖方（120 保底）首次命中 featured 后才激活。`_active` flag 已由 P55 `CounterBasedBehavior.__init__` 初始化：`depends_on is None` → `_active.set()`；有依赖 → 初始 False，由引擎激活。

`CounterBasedBehavior.before_draw` 开头检查 `_active.is_set()`——尚未激活时不调概率、不递增计数器（已在 P55 实现）。

#### 3.4.2 引擎声明式依赖传播

**不再由依赖方硬编码激活逻辑。** 引擎构造时解析 `depends_on` 关系，`after_draw` 中自动传播：

```python
class PityEngine:
    def __init__(self, behaviors):
        self._behaviors = _resolve_order(behaviors)
        self._activation_graph = self._build_activation_graph(behaviors)
        _validate_behaviors(self._behaviors)

    def _build_activation_graph(self, behaviors):
        """解析 depends_on → {source_name: [dependent_name, ...]}。校验引用完整性。"""
        all_names = {bh.name for bh in behaviors}
        graph = {}
        for bh in behaviors:
            dep = getattr(bh, '_lifecycle', None)
            if dep and dep.depends_on:
                if dep.depends_on not in all_names:
                    raise ConfigError(
                        f"「{bh.name}」的 depends_on 引用了不存在的 behavior "
                        f"「{dep.depends_on}」——请检查名称拼写或确保目标 behavior 已定义。"
                    )
                graph.setdefault(dep.depends_on, []).append(bh.name)
        return graph

    def after_draw(self, pool_id, state, draw_info):
        ctx = PityContext(draw=draw_info, current={}, state=state)
        for bh in self._behaviors:
            bh.after_draw(ctx)
            # 引擎自动传播激活事件
            if bh.did_fire(ctx):        # behavior 暴露语义方法
                for dep_name in self._activation_graph.get(bh.name, []):
                    state.set(dep_name, "_active", True)
```

每个 behavior 暴露 `did_fire(ctx) → bool`：

- `CounterBasedBehavior`：`_should_reset(ctx)` 为真时返回 True（计数器驱动保底「触发」= 命中 scope 目标）
- `RotatingBehavior`：`_is_hit(ctx)` 为真时返回 True（首次命中 featured/selected_card）

> **⚠️ 命名提醒：** `did_fire` 的字面意思是「保底触发了吗」，但实际语义是「目标被获取了吗」。前者暗示 hard 保底达到阈值时返回 True，后者是每次命中目标稀有度都返回 True。两种理解在当前 `depends_on` 场景下**功能等价**（都是 `_active.set(True)`，幂等），但**不要在 `did_fire` 上追加「区分触发类型」的返回值设计**——当前 `bool` 已满足 `depends_on` 激活的全部需求，引入枚举或事件类型属于过度设计。

**收益：** 依赖方不需要知道谁依赖它——`RotatingBehavior` 和 `HardPityBehavior` 内部零硬编码引用。依赖关系只在 TOML 的 `depends_on` 字段中声明。

#### 3.4.3 配置示例

```toml
# 终末地 120 大保底——提前命中永久关闭
[[pity]]
type = "hard"
scope = "ssr"
threshold = 120
max_triggers = 1
deactivate_on_early_hit = true     # 120抽前已出→永久关闭

# 终末地 240 信物保底——依赖 120 保底首次命中后激活
[[pity]]
type = "hard"
scope = "ssr"
target_featured = true
threshold = 240
depends_on = "featured_hard_120"   # 120 保底命中 featured 后才开始计数
```

### 3.5 配置语法

```toml
# ── 池子级：声明哪些卡可被定轨 ──
[[pool]]
id = "limited_weapon"
name = "神铸赋形"
epitomizable_cards = [            # 默认 []——空 = 不支持定轨
    "wolfs_gravestone",
    "primordial_jade_cutter",
]
# 显式配置，不从 featured 推导——确保稳定性和灵活性

# ── rotating ──

# 硬 rotating——基础二态轮换（原神角色池 50/50、星铁光锥池 75/25）
[[pity]]
name = "rotating_5050"
type = "rotating"
scope = "ssr"                    # 稀有度层级——SSR 事件触发状态转移
pools = ["limited_character"]
initial_win_rate = 50.0
loss_increment = 50.0             # 歪一次跳满到 100%

# ⚠️ 捕获明光不在此处建模——见 §3.3 更正 + 手册 G17（需 loss_streak type）

# ── targeted（定向保底/定轨）——独立 type ──

# 原神武器池定轨（5.0 改版后——1 命定值）
[[pity]]
name = "epitomized_weapon"
type = "targeted"
scope = "ssr"
pools = ["limited_weapon"]
initial_win_rate = 50.0
loss_increment = 50.0
fate_threshold = 1                # 几个命定值触发保证
switch_allowed = true             # 允许中途切换目标
switch_resets_progress = true     # 切换后命定值清零（原神=true，绝区零=false）
# selected_card 不在此配置——由策略通过 NonDrawAction 运行时设定
# 可选卡范围 → 见 [[pool]].epitomizable_cards

# 绝区零音擎回响（切换不清零）
[[pity]]
name = "wengine_targeted"
type = "targeted"
scope = "ssr"
pools = ["wengine_resonance"]
fate_threshold = 1
switch_allowed = true
switch_resets_progress = false    # ← 绝区零：切换后进度保留

# 鸣潮常驻武器池（100% 不歪——阈值 0，出金即目标）
[[pity]]
name = "standard_weapon_select"
type = "targeted"
scope = "ssr"
pools = ["standard_weapon"]
fate_threshold = 0                # ← 无累积过程，始终保证
switch_allowed = true
switch_resets_progress = false    # ← 无进度可清，切换无代价
# selected_card 由策略在模拟开始时通过 NonDrawAction 设定

# ── LifecycleConfig 扩展 ──

# 终末地 120 大保底——提前命中永久关闭
[[pity]]
name = "featured_hard_120"
type = "hard"
scope = "ssr"
threshold = 120
max_triggers = 1
deactivate_on_early_hit = true

# 终末地 240 信物保底——依赖 120 保底首次命中后激活
[[pity]]
name = "dupe_240"
type = "hard"
scope = "ssr"
target_featured = true
threshold = 240
depends_on = "featured_hard_120"   # 120 保底命中 featured 后激活
```

### 3.6 `selected_card` 的建模方式——决议

> **决议日期：2026-06-16 | 结论：策略运行时设定 + 池子声明可选范围 + `NonDrawAction` 作为切换载体**

#### 三层分工

| 层 | 内容 | 决定者 |
|----|------|--------|
| 池子配置 | `epitomizable_cards`——哪些卡可被定轨 | 设计者（TOML `[[pool]]`） |
| 保底配置 | `fate_threshold` / `switch_allowed` / `switch_resets_progress`——定轨规则 | 设计者（TOML `[[pity]]`） |
| 运行时状态 | `selected_card`——当前选哪张 | 策略（`NonDrawAction`） |

#### 策略通过 `NonDrawAction` 控制

```python
# 设初始目标
NonDrawAction("switch_epitomized_target", {
    "pool_id": "limited_weapon",
    "card_id": "wolfs_gravestone",
})

# 中途切换
NonDrawAction("switch_epitomized_target", {
    "pool_id": "limited_weapon",
    "card_id": "primordial_jade_cutter",
})

# 取消定轨（不定轨抽）
NonDrawAction("cancel_epitomized_path", {
    "pool_id": "limited_weapon",
})
```

`gacha_service._apply_non_draw()` 分发时：
1. 校验 `card_id ∈ pool.epitomizable_cards`
2. 校验 `pity_def.switch_allowed == true`（拒绝切 → 静默忽略或 InvalidActionError）
3. 写 `PityState[name]["selected_card"]`
4. 若 `switch_resets_progress` → `PityState[name]["fate_points"] = 0`

#### 不定轨是合法状态

`selected_card = None`（初始默认值）。此时 `TargetedBehavior`：
- `_is_hit()` 返回 `False` → 命定值不累积
- `before_draw()` 正常调整概率（50/50 或 75/25 照常）——不定轨也能抽
- `after_draw()` 看到 `selected_card is None` → 直接 return，不累积不翻转

对应现实：原神取消定轨后照样抽武器池，出金随机。

#### 为何不在 `[[pity]]` 中静态配置 `selected_card`

- 方案搜索（P26）需要遍历「初始选哪张」「歪了之后是否换目标」——静态配置无法覆盖
- `NonDrawAction` 将选择权交给策略——搜索空间自然包含定轨决策节点
- 简单模拟（策略不返回 NonDrawAction）→ 默认 `selected_card = None`（不定轨），用户可通过 GUI 设初始选择

#### 与 P55 `[[pity]].pools` 的关系

`pools` 控制 behavior 的作用域——`targeted` 的 `fate_points` 和 `guaranteed` 在 `pools` 声明的池子间共享。跨期继承由 `pools` 的作用范围自然推导——不需要额外的 `carry_over` 参数。

### 3.7 实施阶段

| 阶段 | 内容 |
|------|------|
| **阶段一** | `_redistribute_scope()` 模块级工具函数——featured/非featured 概率重分配（~25 行） |
| **阶段二** | `RotatingBehavior` 完整实现（~60 行）——事件驱动 + `loss_increment` 软/硬参数 |
| **阶段三** | `TargetedBehavior` 完整实现（~80 行）——独立于 rotating + `_is_hit()` 覆写 + 命定值 + 不定轨守卫 |
| **阶段四** | `NonDrawAction` + `NON_DRAW_ACTION_REGISTRY`（~30 行 `action.py`）+ `gacha_service._apply_non_draw()` 分发（~25 行） |
| **阶段五** | `[[pool]].epitomizable_cards` 字段——`config_store.py` + `config_toml.py` 解析 + 校验 `card_id` 合法性 |
| **阶段六** | `LifecycleConfig` 扩展——`deactivate_on_early_hit` + `depends_on` + `did_fire()` |
| **阶段七** | `PityEngine` 声明式依赖传播——`_build_activation_graph()` + `after_draw` 中自动激活 |
| **阶段八** | 配置面板 UI 更新——`epitomizable_cards` 列表 + 各 type 新字段控件 |
| **阶段九** | 测试 + 文档 |

## 四、依赖关系

```
P55（基础设施）
  ├── PityContext / DrawInfo
  ├── PityState（Counter / Flag）
  ├── PityBehavior（独立化接口）
  ├── CounterBasedBehavior + LifecycleConfig(max_triggers)
  ├── BEHAVIOR_REGISTRY（含参数元数据，对齐 STRATEGY_REGISTRY）
  ├── 执行顺序自动推导（soft → rotating/targeted → hard）
        │
        └── P56（本计划）
              ├── _redistribute_scope()（模块级工具——rotating + targeted 共用）
              ├── RotatingBehavior（stub → 完整，~60 行）
              ├── TargetedBehavior（独立于 rotating，~80 行）
              ├── NonDrawAction + gacha_service 分发（~55 行）
              ├── [[pool]].epitomizable_cards（~20 行解析）
              ├── LifecycleConfig 扩展（+deactivate_on_early_hit / +depends_on）
              └── PityEngine 声明式依赖传播（+_activation_graph）
```

## 五、波及范围

| 文件 | 改动 |
|------|------|
| `core/pity.py` | 新增 `_redistribute_scope()` + `RotatingBehavior` + `TargetedBehavior` + `LifecycleConfig` 扩展 + `PityEngine._activation_graph` + `did_fire()` |
| `core/action.py` | 新增 `NonDrawAction` + `NON_DRAW_ACTION_REGISTRY`（2 条目——switch_epitomized_target / cancel_epitomized_path） |
| `service/gacha_service.py` | 新增 `_apply_non_draw()` 分发函数 + `NonDrawAction` 分支 |
| `service/batch_simulator.py` | 同上（或共用） |
| `core/config_store.py` | `LifecycleConfig` 扩展 `deactivate_on_early_hit` / `depends_on`；`PoolDef` 新增 `epitomizable_cards: list[str]` |
| `core/config_toml.py` | `[[pool]]` 解析 `epitomizable_cards` + 校验 `card_id` 在池子中存在 |
| `gui/config_panel.py` | 新字段 UI——`epitomizable_cards` 列表 + `targeted` type 专属参数 |

## 六、设计边界提醒

### 已有基础（来自 P55，不要推倒或绕过）

| 能力 | P55 机制 | P56 如何使用 |
|------|---------|-------------|
| behavior 独立生命周期 | `PityBehavior.before_draw()` / `after_draw()` | `RotatingBehavior` 覆写这两个方法，不碰 Engine |
| 状态存储 | `PityState` namespace + `Counter` / `Flag` | `RotatingBehavior` 用 `Flag` 存 `guaranteed` / `lost_5050`，用 `Counter` 存 `losses` |
| 不可变上下文 | `DrawInfo`（`frozen`） | rotating 通过 `featured_slots` / `scope_slots` 获取槽位信息 |
| 停用/激活 | `_active` flag + `CounterBasedBehavior.before_draw` 检查 | 终末地 240 的 `depends_on` 依赖此机制——初始 `_active=False`，引擎激活 |
| 触发上限 | `max_triggers` → `_active.clear()` | 终末地 120 复用此机制 |
| 策略读接口 | `PityEngine.is_guaranteed()` 等 | 策略层通过此接口判断大保底状态 |

### P56 新建能力（只建一次）

| 新建能力 | 机制 | 归属 | 不要做的事 |
|---------|------|------|-----------|
| 概率重分配工具 | `_redistribute_scope()` — 模块级函数 | `pity.py` | **不要在 RotatingBehavior 和 TargetedBehavior 中各自复制**——共用此函数 |
| 大小保底轮换 | `RotatingBehavior` — 事件驱动，SSR 时状态转移 | `pity.py` 新增类 | `loss_increment` 控制单次歪后 featured 跳变幅度（50=一次跳满）。捕获明光**不在此列**——需独立 `loss_streak` type（手册 G17） |
| 定向保底（定轨） | `TargetedBehavior(PityBehavior)` — 独立类，覆写 `_is_hit()` + `after_draw()` | `pity.py` 新增类 | **不要继承 RotatingBehavior**——两者平级，共享 `_redistribute_scope()` |
| 切换目标 + 取消定轨 | `NonDrawAction` + `NON_DRAW_ACTION_REGISTRY` | `action.py` 新增 | **不要将 `selected_card` 放入 `[[pity]]` 静态配置**——由策略运行时设定 |
| 定轨可选卡 | `[[pool]].epitomizable_cards` — 池子级配置字段 | `config_store.py` + `config_toml.py` | **不要从 featured 推导**——不稳定、不灵活、不必然 |
| 依赖激活传播 | `LifecycleConfig.depends_on` + `PityEngine._activation_graph` | 字段 + Engine 方法 | **不要在 behavior 内部硬编码依赖方名称**——关系只在 TOML 中声明 |
| 提前命中停用 | `LifecycleConfig.deactivate_on_early_hit` + `HardPityBehavior.after_draw` 覆写 | 字段 + 子类覆写 | **不要将阈值检查放入 `CounterBasedBehavior` 基类** |
| `did_fire()` 声明式传播 | 引擎检查 `did_fire()` → 激活依赖方 | `PityEngine.after_draw` | **不要追加事件类型枚举**——`bool` 对 `depends_on` 激活已够用 |
| 跨期继承 | 由 `[[pity]].pools` 控制作用域——行为绑定到哪些池子，状态就在哪些池子间共享 | 已有机制 | **不要加 `carry_over` 参数**——`pools` 就是继承边界 |

## 七、验收标准

- [ ] 大小保底：歪后下一次必中 featured；中 featured 后回归 50/50
- [ ] ~~捕获明光（软 rotating）~~ → **已移除**。捕获明光不是 rotating 变体——见 §3.3 更正。需 `loss_streak` type（手册 G17），归入后续计划
- [ ] 定轨—命中（fate_threshold=1）：出非选择 SSR → +1 命定值；命定值满 → 下次必出选中卡
- [ ] 定轨—切换：`switch_allowed=true` + `switch_resets_progress=true` → 切目标清零；`false` → 保留
- [ ] 定轨—取消：`cancel_epitomized_path` → `selected_card=None`，之后不累积命定值、不翻转状态
- [ ] 定轨—不定轨抽：`selected_card=None` 且 `switch_epitomized_target` 可设初始目标
- [ ] 定轨—零阈值（fate_threshold=0）：始终处于保证状态，scope 内概率全部分配给 selected_card；切换目标无代价
- [ ] `epitomizable_cards` 正确校验——`card_id` 不在列表中 → 拒绝
- [ ] 终末地 120：`hard` + `max_triggers=1` + `deactivate_on_early_hit=true`——120 抽前已出 featured → 永久关闭
- [ ] 终末地 240：`hard` + `depends_on="featured_hard_120"`——120 保底首次命中后激活；激活前不计数、不调概率
- [ ] `selected_card` 建模方式已有明确决议（§3.6 已收敛）
- [ ] 所有机制均不依赖 P55 之外的任何新基础设施
