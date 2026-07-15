<!-- META: P56 | module:保底系统 | status:designing | last:2026-06-20 | depends:P60✅ -->

# P56 事件驱动保底——rotating / rotating_soft / rotating_cr / rotating_cr_soft / targeted / targeted_soft 完整实现 + LifecycleConfig 扩展

> 日期：2026-06-15 | 更新：2026-06-20 | 状态：设计中
> **2026-06-20 修正案 #1：** 捕获明光方案已决策——独立 `type="rotating_cr"`，`RotatingCRBehavior(RotatingBehavior)` 子类继承。`cr_state_probs` 为数组预留。详见 §3.3。
> **2026-06-20 修正案 #2：** 移除 `initial_win_rate` 参数——小保底 featured 占比由**基础概率分布**唯一确定。
> **2026-06-20 修正案 #3：** 新增集成 type——`_soft` 后缀 = 自带软保底。纯 type（`rotating`/`rotating_cr`/`targeted`）保留，集成 type（`rotating_soft`/`rotating_cr_soft`/`targeted_soft`）= 一个条目搞定 90% 场景。命名：rotating 家族统一前缀 + 后缀机制。`rotating_cr` 的 `cr` 缩写来自英文社区 Capturing Radiance 通用简称（Reddit/Fandom/ResetEra）。
> 依赖：[P60](../../../02-待办/P60%20基础平台——依赖消除与下游并行化.md)（提供 PityState / DrawInfo / PityContext / Counter / Flag / CounterBasedBehavior / BEHAVIOR_REGISTRY / PityEngine 调度器）。与 P58（独立 MilestoneEngine——`[[milestone]]` 独立配置段）可并行于P60 之上。
> 触发：调研 15 款主流抽卡游戏——事件驱动型保底机制 + behavior 间生命周期依赖 + 定轨统一建模

## 一、问题

P55 提供了三种 counter 驱动的基础保底（`soft_interval` / `soft_additive` / `hard`）+ 两种事件驱动保底的 stub（`rotating` / `targeted`）。本计划交付两者的完整实现及 `CounterBasedBehavior` 的生命周期扩展。

**rotating 和 targeted 的共性与差异：**

| | rotating | targeted |
|---|---------|---------|
| 驱动方式 | SSR 事件 | SSR 事件 |
| 概率操作 | 重分配 featured/offrate 内部比例 | 同 rotating——共享 `_redistribute_scope()` |
| 目标锁定 | 无——featured 全体 | 有——锁定单张 selected_card |
| 状态机制 | guaranteed flag（纯净二态） | guaranteed flag + losses counter + fate_points + selected_card |
| 切换支持 | 不适用 | switch_allowed / switch_resets_progress |
| 跨期继承 | 由 `pools` 字段控制作用域 | 同——`pools` 就是继承边界，无需额外参数 |

两者平级继承 `PityBehavior`，不互为父子。概率重分配算法提取为模块级 `_redistribute_scope()` 供两者共用。

| 机制 | 本质 | 本计划交付方式 |
|------|------|--------------|
| 纯净轮换 | SSR 事件 → 二态 flag 翻转 | `RotatingBehavior`（零参数） |
| 轮换+软保底 | counter 爬升 + SSR 事件翻转 | `RotatingSoftBehavior(RotatingBehavior)`——~25 行增量 |
| 轮换+捕获明光 | 连歪计数器——0→1→2→3→拦截 | `RotatingCRBehavior(RotatingBehavior)`——~40 行增量 |
| 轮换+CR+软保底 | 以上两者叠加 | `RotatingCRSoftBehavior(RotatingCRBehavior)`——~25 行增量 |
| 定轨（原神式） | 命中特定卡片才重置 + 命定值 | `TargetedBehavior`——`fate_threshold=1` |
| 定轨（绝区零式） | 同上 + 切换不清零 | `TargetedBehavior`——`fate_threshold=1` + `switch_resets_progress=false` |
| 常驻自选（鸣潮式） | 100% 不歪 | `TargetedBehavior`——`fate_threshold=0` |
| 定轨+软保底 | 定轨 + 软保底爬升 | `TargetedSoftBehavior(TargetedBehavior)`——~25 行增量 |
| 提前命中永久失效 | 阈值前命中即关闭 | `LifecycleConfig.deactivate_on_early_hit` |
| 依赖激活 | 另一 behavior 首次命中后激活 | `LifecycleConfig.depends_on` + 引擎声明式传播 |

**`fate_threshold=0` 的语义：** 没有「累积→触发」的过程——命定值始终 ≥ 阈值，`before_draw` 始终将 scope 内概率全部分配给 `selected_card` 对应的槽位。等价于「出金即目标」。切换目标行为由 `switch_allowed` / `switch_resets_progress` 控制——因为无进度可清，切换代价为零。

## 二、目标

| # | 交付 | 说明 |
|---|------|------|
| 1 | `RotatingBehavior` 完整实现 | 纯净大小保底——事件驱动，零参数。`type="rotating"`。 |
| 2 | `RotatingSoftBehavior` 完整实现 | `RotatingBehavior` 子类——追加软保底计数器。~25 行增量。`type="rotating_soft"`。 |
| 3 | `RotatingCRBehavior` 完整实现 | `RotatingBehavior` 子类——追加 CR 状态机 + `cr_state_probs` + `cr_base_rate`。~40 行增量。`type="rotating_cr"`。 |
| 4 | `RotatingCRSoftBehavior` 完整实现 | `RotatingCRBehavior` 子类——追加软保底计数器。~25 行增量。`type="rotating_cr_soft"`。 |
| 5 | `TargetedBehavior` 完整实现 | 定轨——`_is_hit()` 锁定 selected_card + 命定值 + 切换规则。`type="targeted"`。 |
| 6 | `TargetedSoftBehavior` 完整实现 | `TargetedBehavior` 子类——追加软保底计数器。~25 行增量。`type="targeted_soft"`。 |
| 7 | `_redistribute_scope()` 工具函数 | 模块级函数——在所有 rotating/targeted 家族间共用。软保底由 P55 `SoftStepBehavior` deltas 引擎统一消费 |
| 8 | `LifecycleConfig` 扩展 | 新增 `deactivate_on_early_hit` + `depends_on` |
| 9 | 引擎声明式依赖传播 | `_build_activation_graph()` + `after_draw` 中自动激活依赖方 |
| 10 | `[[pool]].epitomizable_cards` | 池子级配置——显式声明定轨可选卡 |

## 三、方案

### 3.1 RotatingBehavior——纯净 50/50 轮换保底

不继承 `CounterBasedBehavior`——无计数器。SSR 事件触发状态转移。不改变 SSR 总出率，只重分配 featured/非featured 的内部概率权重。**仅维护 `guaranteed` flag（大保底/小保底）。小保底不修改概率——featured 占比由基础分布决定。连歪计数器归入子类 `RotatingCRBehavior`。**

```python
class RotatingBehavior(PityBehavior):
    """事件驱动的纯净轮换保底。

    内部状态：
      - guaranteed flag：当前是否处于大保底

    小保底（guaranteed=False）：沿用基础分布的 featured/非featured 比例——不修改概率。
    大保底（guaranteed=True）：featured 100%。
    无需 initial_win_rate——featured 占比由基础概率分布唯一确定。
    """

    def __init__(self, name, state, scope="ssr"):
        self._name = name
        self._scope = scope
        self._guaranteed = Flag(state, name, "guaranteed")

    def before_draw(self, ctx):
        """重分配 scope 内部 featured/非featured 比例。"""
        total = self._scope_total_prob(ctx)
        if total <= 0:
            return ctx.current.copy()

        featured_slots = self._featured_slots(ctx)
        if not featured_slots:
            return ctx.current.copy()

        if self._guaranteed.is_set():
            featured_ratio = 1.0    # 大保底：featured 100%
        else:
            # 小保底：featured 占比由基础分布决定，不做修改
            featured_total = sum(ctx.current.get(s, 0.0) for s in featured_slots)
            featured_ratio = featured_total / total

        return _redistribute_scope(ctx, featured_ratio, total, featured_slots, self._scope)

    def after_draw(self, ctx):
        if not self._is_trigger_rarity(ctx.draw.reward_rarity, ctx):
            return
        if self._is_hit(ctx):
            self._guaranteed.clear()
        else:
            self._guaranteed.set()

    def _is_hit(self, ctx):
        """子类可覆写——默认：出了 featured 就算命中。"""
        return ctx.draw.is_featured

    def _is_trigger_rarity(self, rarity, ctx):
        return rarity == self._scope

    def _scope_total_prob(self, ctx):
        slots = ctx.draw.scope_slots.get(self._scope, ())
        return sum(ctx.current.get(s, 0.0) for s in slots)

    def _featured_slots(self, ctx):
        return ctx.draw.featured_slots.get(self._scope, ())

    def did_fire(self, ctx):
        return self._is_hit(ctx)
```

~55 行。零参数——**不需要 `initial_win_rate`**：小保底 featured 占比由基础概率分布（`featured` 槽总概率 / SSR 总概率）自动计算；大保底恒为 100% featured。**不含 `losses` counter、`loss_increment`、`lost_flag`——捕获明光所需状态归入子类。**

```toml
# rotating——纯净大小保底
# featured 占比由基础分布决定——无需 initial_win_rate
[[pity]]
type = "rotating"
scope = "ssr"
```

### 3.2 TargetedBehavior（定向保底/定轨）——独立事件驱动

与 `RotatingBehavior` 平级继承 `PityBehavior`，共享 `_redistribute_scope()` 工具函数。不继承 `RotatingBehavior`——两者的共同点仅在于概率重分配算法。

**与 RotatingBehavior 的差异点：**

| | RotatingBehavior | TargetedBehavior |
|---|---|---|
| `_is_hit()` | `ctx.draw.is_featured` | `reward_id == selected_card` |
| 状态 | guaranteed flag（纯净二态） | guaranteed + losses + fate_points + selected_card |
| 切换 | 不适用 | switch_allowed / switch_resets_progress |
| 不定轨 | 不适用 | selected_card=None → 不累积、不翻转 |
| 小保底规则 | 沿用基础分布 | 沿用基础分布（对齐 rotating） |

```python
class TargetedBehavior(PityBehavior):
    """事件驱动的定向保底（定轨）。

    内部状态：
      - selected_card：目标卡牌 ID（由策略 NonDrawAction 设定，可从 PityState 读取）
      - guaranteed flag：命定值满后的大保底
      - losses counter：累计歪次数（仅追踪——不影响概率，小保底 featured 占比由基础分布决定）
      - lost_flag：上轮是否歪了（仅追踪）
      - fate_points counter：命定值累积
    """

    def __init__(self, name, state, scope="ssr",
                 fate_threshold=1, switch_allowed=True,
                 switch_resets_progress=True):
        self._name = name
        self._state = state
        self._scope = scope
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
            return _redistribute_scope(ctx, featured_ratio, total, targeted_slots, self._scope)
        else:
            # 小保底：featured 占比由基础分布决定（对齐 rotating）
            featured_total = sum(ctx.current.get(s, 0.0) for s in featured_slots)
            featured_ratio = featured_total / total if total > 0 else 0.0
            return _redistribute_scope(ctx, featured_ratio, total, featured_slots, self._scope)

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


def _redistribute_scope(ctx, featured_ratio, total, featured_slots, scope):
    """在 featured/非featured 之间重分配 scope 总概率。
    供 RotatingBehavior 和 TargetedBehavior 共用。"""
    result = ctx.current.copy()
    featured_total = total * featured_ratio
    non_featured_total = total - featured_total

    for s in featured_slots:
        result[s] = featured_total / len(featured_slots)

    non_featured_slots = [
        s for s in ctx.draw.scope_slots.get(scope, ())
        if s not in featured_slots
    ]
    if non_featured_slots:
        for s in non_featured_slots:
            result[s] = non_featured_total / len(non_featured_slots)

    return result
```

~65 行（移除 `initial_win_rate` / `loss_increment` 后缩减 ~15 行）。小保底 featured 占比由基础概率分布决定（对齐 rotating）。`switch_allowed` / `switch_resets_progress` 在 `NonDrawAction` 分发时由 `gacha_service` 读取本 behavior 配置执行；behavior 本身不处理切换逻辑——切换由策略驱动、模拟循环执行。

### 3.3 RotatingCRBehavior —— 捕获明光（修正案）

> **2026-06-20 修正案（替代 2026-06-17 更正）：** 方案已决策——独立 `type="rotating_cr"`，`RotatingBehavior` 的子类。英文社区 Capturing Radiance 通用缩写 CR（Reddit / Fandom / ResetEra / GameFAQs）。

**设计逻辑：**

捕获明光不能独立存在——它依附于 50/50 轮换。但没有 rotating 就没有「小保底」概念。因此：**同一份 rotating 逻辑，子类追加 CR 状态机。** 不与 `type="rotating"` 并存——一个池子只配一种。

**机制概要：**

```
出 SSR 时：
  ├─ 大保底（上次歪了）→ 100% featured → CR 无事可做
  └─ 小保底 → 50/50 判定
       ├─ 直接赢 → cr_counter = 0
       ├─ 歪了但 CR 拦截 → 转败为胜，cr_counter 重置
       └─ 歪了且 CR 未拦截 → cr_counter++

cr_counter ≥ cr_counter_threshold → 下次小保底 100% 拦截
```

```python
class RotatingCRBehavior(RotatingBehavior):
    """轮换保底 + 捕获明光。

    继承纯净 RotatingBehavior 的全部 50/50 逻辑，追加：
      - cr_counter：连歪次数追踪
      - cr_state_probs：每个 counter 状态的拦截概率（数组预留）
      - cr_base_rate：每次祈愿的基础触发概率
    """

    def __init__(self, name, state, scope="ssr",
                 cr_counter_threshold=3,
                 cr_base_rate=0.0,
                 cr_state_probs=None):
        super().__init__(name, state, scope)
        self._cr_max = cr_counter_threshold
        self._cr_base_rate = cr_base_rate
        # 默认：仅 counter≥threshold 时拦截
        self._cr_state_probs = cr_state_probs or [0.0] * cr_counter_threshold + [1.0]
        self._cr_counter = Counter(state, name, "cr_counter")

    # ── before_draw：小保底时检查 CR 拦截 ──

    def before_draw(self, ctx):
        if self._guaranteed.is_set():
            return super().before_draw(ctx)   # 大保底——CR 不干预

        # 基础概率自然触发（每次祈愿独立判定）
        if self._cr_base_rate > 0 and random.random() < self._cr_base_rate:
            return self._force_featured(ctx)

        # Counter 状态拦截
        idx = min(self._cr_counter.value(), len(self._cr_state_probs) - 1)
        state_prob = self._cr_state_probs[idx]
        if state_prob >= 1.0:
            return self._force_featured(ctx)
        if state_prob > 0 and random.random() < state_prob:
            return self._force_featured(ctx)

        return super().before_draw(ctx)       # 正常 50/50

    def _force_featured(self, ctx):
        """将 scope 内概率全部导向 featured。"""
        total = self._scope_total_prob(ctx)
        featured_slots = self._featured_slots(ctx)
        return _redistribute_scope(ctx, 1.0, total, featured_slots, self._scope)

    # ── after_draw：更新连歪计数器 ──

    def after_draw(self, ctx):
        # 在 super() 之前保存——super().after_draw() 会翻转 guaranteed
        was_guaranteed = self._guaranteed.is_set()
        super().after_draw(ctx)

        if not self._is_trigger_rarity(ctx.draw.reward_rarity, ctx):
            return

        if was_guaranteed:
            return   # 大保底出金——CR 无关

        # 小保底
        if ctx.draw.is_featured:
            self._cr_counter.reset()           # 赢了——连歪中断
        else:
            self._cr_counter.incr()            # 歪了——连歪+1

    def did_fire(self, ctx):
        """CR 拦截 = 命中 featured。"""
        return ctx.draw.is_featured
```

~40 行增量。所有 rotating 核心逻辑继承自父类，CR 只追加拦截判定 + counter 维护。

```toml
# rotating_cr —— 轮换保底 + 捕获明光（原神 5.0+）
[[pity]]
type = "rotating_cr"
scope = "ssr"
cr_counter_threshold = 3          # 连歪 N 次后 100% 拦截
cr_base_rate = 0.00018            # 每次祈愿基础触发（0=禁用）
cr_state_probs = [0.0, 0.0, 0.0, 1.0]  # 每个 counter 状态的拦截概率（数组预留）
# 无 initial_win_rate——小保底 featured 占比由基础分布决定
```

**`cr_state_probs` 预留说明：**

| 索引 | counter 值 | 当前默认 | 含义 |
|:---:|:---:|:---:|------|
| 0 | 0 | 0.0 | 上次赢了——不拦截 |
| 1 | 1 | 0.0 | 歪 1 次——精确概率待定 |
| 2 | 2 | 0.0 | 两连歪——精确概率待定 |
| 3 | 3 | 1.0 | 三连歪——100% 拦截 ✅ |

> 等社区数据明确后，用户可更新为 `[0.0, 0.05, 0.55, 1.0]` 等。数组自动扩展——`cr_state_probs[i]` 超出数组长度时复用最后一项。

### 3.4 RotatingSoftBehavior——轮换 + 软保底

`type="rotating_soft"`。`RotatingBehavior` 子类——继承纯净轮换，追加软保底计数器。~25 行增量。

软保底概率统一由 P55 `SoftStepBehavior` 的 deltas 引擎计算——`_soft_engine._compute_probabilities()`。与 `SoftIntervalBehavior` 走同一引擎——纯重构，不改行为。

**继承链：** `PityBehavior` → `RotatingBehavior` → `RotatingSoftBehavior`

**内部状态：** `counter`（软保底抽数）+ `guaranteed` flag（轮换，来自父类）

> **2026-06-20 修正案 #4：** `_compute_soft_progress()` / `_apply_soft_pity_boost()` 已移除——`_soft` 后缀 type 统一通过 P55 的 `SoftStepBehavior` deltas 引擎消费软保底概率。三态语法糖（`soft_start`/`soft_end` / `soft_start`/`soft_increment` / `soft_deltas`）在构造时由 `_expand_soft_to_deltas()` 展开为 deltas，传入内部 `_soft_engine`（`SoftStepBehavior` 实例）。消除两套平行代码。



class RotatingSoftBehavior(RotatingBehavior):
    """轮换保底 + 软保底。

    继承 RotatingBehavior 的全部 50/50 逻辑，追加：
      - counter：软保底抽数计数器
      - _soft_engine：SoftStepBehavior 实例——deltas 引擎统一消费三态语法糖（interval/additive/step）

    before_draw：
      1. 递增 counter → 委托 _soft_engine（SoftStepBehavior 实例）按 deltas 计算概率
      2. super().before_draw() 做 rotating 重分配
    deltas 引擎支持三态语法糖（interval/additive/step），统一由 _expand_soft_to_deltas() 展开

    after_draw：
      1. SSR 时 reset counter
      2. super().after_draw() 翻转 guaranteed
    """

    def __init__(self, name, state, scope="ssr",
                 soft_start=74, soft_end=90, soft_increment=None, soft_deltas=None):
        super().__init__(name, state, scope)
        # 三态语法糖 → deltas（由 _expand_soft_to_deltas() 展开）
        deltas = _expand_soft_to_deltas({
            'type': 'soft_interval' if soft_increment is None and soft_deltas is None
                    else 'soft_additive' if soft_increment is not None
                    else 'soft_step',
            'start': soft_start, 'end': soft_end,
            'increment': soft_increment, 'deltas': soft_deltas,
        })
        self._soft_engine = SoftStepBehavior(name + '_soft', state, scope, deltas)
        self._counter = Counter(state, name, "counter")

    def before_draw(self, ctx):
        self._counter.incr()
        # 委托 SoftStepBehavior 的 deltas 引擎计算软保底概率
        # _deltas 由 _expand_soft_to_deltas() 在构造时展开（支持 interval/additive/step 三态）
        modified = self._soft_engine._compute_probabilities(ctx, self._counter)

        # fork ctx 传入修改后的概率给父类做 rotating 重分配
        forked = PityContext(draw=ctx.draw, current=modified, state=ctx.state)
        return super().before_draw(forked)

    def after_draw(self, ctx):
        if ctx.draw.reward_rarity == self._scope:
            self._counter.reset()
        super().after_draw(ctx)

    def did_fire(self, ctx):
        return self._is_hit(ctx)
```

~25 行增量。不再重复实现 `_is_hit` / `_is_trigger_rarity` / `_scope_total_prob` / `_featured_slots`——全部从 `RotatingBehavior` 继承。

```toml
# rotating_soft——软保底 + 大小保底（原神 4.x 角色池）
[[pity]]
type = "rotating_soft"
scope = "ssr"
soft_start = 74
soft_end = 90

# 星铁光锥池——75/25 + 提前软保底
[[pity]]
type = "rotating_soft"
scope = "ssr"
soft_start = 63
soft_end = 80
```

> **与分别配置 `soft_interval` + `rotating` 的区别：** 效果等价，但 `rotating_soft` 是一个语义单元。将来自定义扩展（如大保底时抽数阈值不同）在类内实现，不污染配置。

### 3.5 RotatingCRSoftBehavior——轮换 + 捕获明光 + 软保底

`type="rotating_cr_soft"`。`RotatingCRBehavior` 子类——追加软保底计数器。~25 行增量。

```python
class RotatingCRSoftBehavior(RotatingCRBehavior):
    """轮换 + CR + 软保底。继承 RotatingCRBehavior 的全部 CR 逻辑，追加软保底。"""

    def __init__(self, name, state, scope="ssr",
                 soft_start=74, soft_end=90, soft_increment=None, soft_deltas=None,
                 cr_counter_threshold=3, cr_base_rate=0.0,
                 cr_state_probs=None):
        super().__init__(name, state, scope,
                        cr_counter_threshold, cr_base_rate, cr_state_probs)
        # 三态语法糖 → deltas → SoftStepBehavior（对齐 RotatingSoftBehavior）
        deltas = _expand_soft_to_deltas({
            'type': 'soft_interval' if soft_increment is None and soft_deltas is None
                    else 'soft_additive' if soft_increment is not None
                    else 'soft_step',
            'start': soft_start, 'end': soft_end,
            'increment': soft_increment, 'deltas': soft_deltas,
        })
        self._soft_engine = SoftStepBehavior(name + '_soft', state, scope, deltas)
        self._counter = Counter(state, name, "counter")

    def before_draw(self, ctx):
        self._counter.incr()
        modified = self._soft_engine._compute_probabilities(ctx, self._counter)
        forked = PityContext(draw=ctx.draw, current=modified, state=ctx.state)
        return super().before_draw(forked)

    def after_draw(self, ctx):
        if ctx.draw.reward_rarity == self._scope:
            self._counter.reset()
        super().after_draw(ctx)
```

~25 行增量。`rotating_cr_soft` 与 `rotating_cr` 的关系 = `rotating_soft` 与 `rotating` 的关系——同一 `_soft` 后缀模式。

```toml
# rotating_cr_soft——软保底 + 大小保底 + 捕获明光
[[pity]]
type = "rotating_cr_soft"
scope = "ssr"
soft_start = 74
soft_end = 90
cr_counter_threshold = 3
cr_base_rate = 0.00018
cr_state_probs = [0.0, 0.0, 0.0, 1.0]
```

### 3.6 TargetedSoftBehavior——定轨 + 软保底

`type="targeted_soft"`。`TargetedBehavior` 子类——追加软保底计数器。~25 行增量。

```python
class TargetedSoftBehavior(TargetedBehavior):
    """定轨 + 软保底。继承 TargetedBehavior 的全部定轨逻辑，追加软保底。"""

    def __init__(self, name, state, scope="ssr",
                 soft_start=74, soft_end=90, soft_increment=None, soft_deltas=None,
                 fate_threshold=1, switch_allowed=True,
                 switch_resets_progress=True):
        super().__init__(name, state, scope,
                        fate_threshold, switch_allowed, switch_resets_progress)
        # 三态语法糖 → deltas → SoftStepBehavior（对齐 RotatingSoftBehavior）
        deltas = _expand_soft_to_deltas({
            'type': 'soft_interval' if soft_increment is None and soft_deltas is None
                    else 'soft_additive' if soft_increment is not None
                    else 'soft_step',
            'start': soft_start, 'end': soft_end,
            'increment': soft_increment, 'deltas': soft_deltas,
        })
        self._soft_engine = SoftStepBehavior(name + '_soft', state, scope, deltas)
        self._counter = Counter(state, name, "counter")

    def before_draw(self, ctx):
        self._counter.incr()
        modified = self._soft_engine._compute_probabilities(ctx, self._counter)
        forked = PityContext(draw=ctx.draw, current=modified, state=ctx.state)
        return super().before_draw(forked)

    def after_draw(self, ctx):
        if ctx.draw.reward_rarity == self._scope:
            self._counter.reset()
        super().after_draw(ctx)
```

~25 行增量。与 `targeted` 的区别：一个条目自带软保底。

```toml
# targeted_soft——定轨 + 软保底
[[pity]]
type = "targeted_soft"
scope = "ssr"
pools = ["limited_weapon"]
soft_start = 63
soft_end = 80
fate_threshold = 1
switch_allowed = true
switch_resets_progress = true
```

### 3.7 LifecycleConfig 扩展 + 引擎声明式依赖传播

#### 3.7.1 LifecycleConfig 扩展

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

#### 3.7.2 引擎声明式依赖传播

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

#### 3.7.3 配置示例

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

### 3.8 配置语法

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

# 纯净 rotating——仅轮换，无软保底（组合 soft_interval 使用）
# featured 占比由基础分布决定——无需 initial_win_rate
[[pity]]
name = "rotating_5050"
type = "rotating"
scope = "ssr"
pools = ["limited_character"]

# ── rotating_soft ——轮换 + 软保底 ──

# 原神 4.x 角色池——74→90 软保底 + 50/50
[[pity]]
name = "rotating_soft_char"
type = "rotating_soft"
scope = "ssr"
pools = ["limited_character"]
soft_start = 74
soft_end = 90

# 星铁光锥池——63→80 软保底
[[pity]]
name = "rotating_soft_lc"
type = "rotating_soft"
scope = "ssr"
pools = ["limited_lightcone"]
soft_start = 63
soft_end = 80

# ── rotating_cr ——轮换 + 捕获明光 ──

# 原神 5.0+ 角色池
[[pity]]
name = "rotating_cr_char"
type = "rotating_cr"
scope = "ssr"
pools = ["limited_character"]
cr_counter_threshold = 3
cr_base_rate = 0.00018
cr_state_probs = [0.0, 0.0, 0.0, 1.0]

# ── rotating_cr_soft ——轮换 + CR + 软保底 ──

[[pity]]
name = "rotating_cr_soft_char"
type = "rotating_cr_soft"
scope = "ssr"
pools = ["limited_character"]
soft_start = 74
soft_end = 90
cr_counter_threshold = 3
cr_base_rate = 0.00018
cr_state_probs = [0.0, 0.0, 0.0, 1.0]

# ── targeted（定向保底/定轨）——独立 type ──

# 原神武器池定轨（5.0 改版后——1 命定值）
[[pity]]
name = "epitomized_weapon"
type = "targeted"
scope = "ssr"
pools = ["limited_weapon"]
fate_threshold = 1                # 几个命定值触发保证
switch_allowed = true             # 允许中途切换目标
switch_resets_progress = true     # 切换后命定值清零（原神=true，绝区零=false）
# 小保底 featured 占比由基础概率分布决定（对齐 rotating）
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

# ── targeted_soft ——定轨 + 软保底 ──

# 武器池定轨 + 63→80 软保底
[[pity]]
name = "targeted_soft_weapon"
type = "targeted_soft"
scope = "ssr"
pools = ["limited_weapon"]
soft_start = 63
soft_end = 80
fate_threshold = 1
switch_allowed = true
switch_resets_progress = true

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

### 3.9 `selected_card` 的建模方式——决议

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

### 3.10 实施阶段

| 阶段 | 内容 |
|------|------|
| **阶段一** | `_redistribute_scope()` 模块级工具函数（~30 行）。软保底概率由 P55 `SoftStepBehavior` 统一消费 |
| **阶段二** | `RotatingBehavior` 纯净实现（~55 行）——事件驱动，仅维护 `guaranteed` flag |
| **阶段三** | `RotatingSoftBehavior(RotatingBehavior)`（~25 行增量）——追加软保底 |
| **阶段四** | `RotatingCRBehavior(RotatingBehavior)`（~40 行增量）——追加 CR 状态机 |
| **阶段五** | `RotatingCRSoftBehavior(RotatingCRBehavior)`（~25 行增量）——追加软保底 |
| **阶段六** | `TargetedBehavior` 完整实现（~80 行）——定轨 |
| **阶段七** | `TargetedSoftBehavior(TargetedBehavior)`（~25 行增量）——追加软保底 |
| **阶段八** | `NonDrawAction` + `NON_DRAW_ACTION_REGISTRY`（~30 行）+ `gacha_service._apply_non_draw()`（~25 行） |
| **阶段九** | `[[pool]].epitomizable_cards` 字段——解析 + 校验 |
| **阶段十** | `LifecycleConfig` 扩展——`deactivate_on_early_hit` + `depends_on` + `did_fire()` |
| **阶段十一** | `PityEngine` 声明式依赖传播——`_build_activation_graph()` + `after_draw` 自动激活 |
| **阶段十二** | 配置面板 UI 更新——各 type 新字段控件 |
| **阶段十三** | 测试 + 文档 |

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
        ├── P56（本计划）
        │     ├── _redistribute_scope()（共用工具函数）
        │     ├── RotatingBehavior（纯净，~55 行，零参数）
        │     ├── RotatingSoftBehavior（RotatingBehavior 子类，~25 行）
        │     ├── RotatingCRBehavior（RotatingBehavior 子类，~40 行）
        │     ├── RotatingCRSoftBehavior（RotatingCRBehavior 子类，~25 行）
        │     ├── TargetedBehavior（定轨，~80 行）
        │     ├── TargetedSoftBehavior（TargetedBehavior 子类，~25 行）
        │     ├── NonDrawAction + gacha_service 分发（~55 行）
        │     ├── [[pool]].epitomizable_cards（~20 行解析）
        │     ├── LifecycleConfig 扩展（+deactivate_on_early_hit / +depends_on）
        │     └── PityEngine 声明式依赖传播（+_activation_graph）
        │
        └── P58（MilestoneEngine）—— 独立于保底体系，与本计划并行
              ├── 不依赖 P55/PityState/CounterBasedBehavior/BEHAVIOR_REGISTRY
              ├── 独立 `[[milestone]]` TOML 段 + `core/milestone.py`
              ├── 互不依赖——milestone 是计数器驱动（抽数→达阈值→注入），rotating/targeted 是事件驱动
              └── 与 P56 完全并行——改不同文件、不同 TOML 段、不同 UI Tab
```

**关键识别：P56 与 P58 互不依赖。** P56 的 rotating/targeted 是事件驱动（SSR 出货→状态转移），P58 的 milestone 是独立的计数器驱动机制（抽数→达阈值→注入）——两者不共享代码路径、不共享配置段、不共享 UI Tab。P60（`state.add_card` / `state.gain`）交付后两者可完全并行推进。

## 五、波及范围

| 文件 | 改动 |
|------|------|
| `core/pity.py` | 新增 `_redistribute_scope()` + `RotatingBehavior` + `RotatingSoftBehavior` + `RotatingCRBehavior` + `RotatingCRSoftBehavior` + `TargetedBehavior` + `TargetedSoftBehavior` + `LifecycleConfig` 扩展 + `PityEngine._activation_graph` + `did_fire()` |
| `core/action.py` | 新增 `NonDrawAction` + `NON_DRAW_ACTION_REGISTRY`（2 条目——switch_epitomized_target / cancel_epitomized_path） |
| `service/gacha_service.py` | 新增 `_apply_non_draw()` 分发函数 + `NonDrawAction` 分支 |
| `service/batch_simulator.py` | 同上（或共用） |
| `core/config_store.py` | `LifecycleConfig` 扩展 `deactivate_on_early_hit` / `depends_on`；`PoolDef` 新增 `epitomizable_cards: list[str]` |
| `core/config_toml.py` | `[[pool]]` 解析 `epitomizable_cards` + 校验 `card_id` 在池子中存在 |
| `gui/config_panel.py` | 新字段 UI——见 §5.1 |

### 5.1 UI 适配

所有新增控件均在 P55 §4.4 的动态显隐框架下追加——type 切换时自动显示/隐藏对应专属控件。

#### 5.1.1 池子级配置

| 控件 | 类型 | 说明 |
|------|:---:|------|
| `epitomizable_cards` | 多选列表 | 从池子内卡牌中选择——复制 card_id 列表。默认空 |

> `epitomizable_cards` 放在 `[[pool]]` 面板而非 `[[pity]]` 面板——池子属性，不属于单个保底条目。

#### 5.1.2 rotating_cr / rotating_cr_soft 专属

| 控件 | 类型 | 默认 | 说明 |
|------|:---:|:---:|------|
| `cr_counter_threshold` | QSpinBox | 3 | 连歪 N 次后 100% 拦截 |
| `cr_base_rate` | QDoubleSpinBox | 0.0 | 每次祈愿基础触发率（0=禁用）。小数，6 位精度 |
| `cr_state_probs` | 数组表格 | `[0,0,0,1]` | 每 counter 状态的拦截概率。行数 = threshold+1，可编辑 |

#### 5.1.3 targeted / targeted_soft 专属

| 控件 | 类型 | 默认 | 说明 |
|------|:---:|:---:|------|
| `fate_threshold` | QSpinBox | 1 | 命定值触发阈值。0 = 始终保证。小保底 featured 占比由基础分布决定 |
| `switch_allowed` | 复选框 | True | 允许中途切换目标 |
| `switch_resets_progress` | 复选框 | True | 切换后命定值清零 |

`switch_resets_progress` 仅在 `switch_allowed = True` 时启用。

不设 `selected_card` 控件——由策略 NonDrawAction 运行时设定。

#### 5.1.4 所有 _soft 后缀 type 专属

| 控件 | 类型 | 默认 | 说明 |
|------|:---:|:---:|------|
| `soft_start` | QSpinBox | 74 | 软保底起始抽数。与 `soft_end` / `soft_increment` / `soft_deltas` 三态互斥——按需显示 |
| `soft_end` | QSpinBox | 90 | 区间结束抽数（interval 糖）。与 `soft_increment` / `soft_deltas` 互斥 |
| `soft_increment` | QDoubleSpinBox | — | 每抽固定增量 %（additive 糖）。与 `soft_end` / `soft_deltas` 互斥 |
| `soft_deltas` | 表格 | — | RLE 数组（底层）。与 `soft_end` / `soft_increment` 互斥 |
| — | — | — | 三态均走 `_expand_soft_to_deltas()` → 统一由 P55 `SoftStepBehavior` 消费 |

#### 5.1.5 LifecycleConfig 专属

| 控件 | 类型 | 默认 | 说明 |
|------|:---:|:---:|------|
| `deactivate_on_early_hit` | 复选框 | False | 提前命中永久关闭。**仅 type=hard 时启用** |
| `depends_on` | 下拉框 | 空 | 可选其他 behavior 名称。空 = 不依赖 |

#### 5.1.6 联动校验

| 条件 | 行为 |
|------|------|
| `depends_on` 引用的名称不存在 | 红色边框 + 保存拒绝 |
| `deactivate_on_early_hit` = True + type ≠ hard | ConfigError |
| `cr_state_probs` 长度 ≠ cr_counter_threshold + 1 | 黄色警告 |
| `soft_start` ≥ `soft_end` | 红色边框 + 保存拒绝 |

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
| 大小保底轮换 | `RotatingBehavior` — 事件驱动，SSR 时状态转移。零参数 | `pity.py` 新增类 | `type="rotating"`。大保底=100% featured；小保底=沿用基础分布 |
| 轮换+软保底 | `RotatingSoftBehavior(RotatingBehavior)` — 追加软保底计数器 | `pity.py` 新增类 | `type="rotating_soft"`。~25 行增量 |
| 轮换+捕获明光 | `RotatingCRBehavior(RotatingBehavior)` — 追加 CR 状态机 | `pity.py` 新增类 | `type="rotating_cr"`。~40 行增量 |
| 轮换+CR+软保底 | `RotatingCRSoftBehavior(RotatingCRBehavior)` — 追加软保底计数器 | `pity.py` 新增类 | `type="rotating_cr_soft"`。~25 行增量 |
| 捕获明光 | `RotatingCRBehavior(RotatingBehavior)` — 子类追加 CR 状态机 | `pity.py` 新增类 | `cr_counter` + `cr_state_probs` + `cr_base_rate`。小保底时才介入，大保底透传 |
| 定向保底（定轨） | `TargetedBehavior(PityBehavior)` — 独立类，覆写 `_is_hit()` + `after_draw()` | `pity.py` 新增类 | **不要继承 RotatingBehavior**——两者平级，共享 `_redistribute_scope()` |
| 切换目标 + 取消定轨 | `NonDrawAction` + `NON_DRAW_ACTION_REGISTRY` | `action.py` 新增 | **不要将 `selected_card` 放入 `[[pity]]` 静态配置**——由策略运行时设定 |
| 定轨可选卡 | `[[pool]].epitomizable_cards` — 池子级配置字段 | `config_store.py` + `config_toml.py` | **不要从 featured 推导**——不稳定、不灵活、不必然 |
| 依赖激活传播 | `LifecycleConfig.depends_on` + `PityEngine._activation_graph` | 字段 + Engine 方法 | **不要在 behavior 内部硬编码依赖方名称**——关系只在 TOML 中声明 |
| 提前命中停用 | `LifecycleConfig.deactivate_on_early_hit` + `HardPityBehavior.after_draw` 覆写 | 字段 + 子类覆写 | **不要将阈值检查放入 `CounterBasedBehavior` 基类** |
| `did_fire()` 声明式传播 | 引擎检查 `did_fire()` → 激活依赖方 | `PityEngine.after_draw` | **不要追加事件类型枚举**——`bool` 对 `depends_on` 激活已够用 |
| 跨期继承 | 由 `[[pity]].pools` 控制作用域——行为绑定到哪些池子，状态就在哪些池子间共享 | 已有机制 | **不要加 `carry_over` 参数**——`pools` 就是继承边界 |

## 七、验收标准

- [ ] 纯净 rotating：歪后下一次必中 featured；中 featured 后回归 50/50
- [ ] 捕获明光：三连歪后 100% 拦截；拦截后 cr_counter 重置；小保底赢了 cr_counter 归零
- [ ] 捕获明光—base_rate：`cr_base_rate=0.00018` 时每次祈愿有独立判定
- [ ] 捕获明光—state_probs：`cr_state_probs=[0.0, 0.05, 0.55, 1.0]` 按状态分段判定
- [ ] 定轨—小保底 featured 占比由基础分布决定（对齐 rotating，无 `initial_win_rate` / `loss_increment`）
- [ ] 定轨—命中（fate_threshold=1）：出非选择 SSR → +1 命定值；命定值满 → 下次必出选中卡
- [ ] 定轨—切换：`switch_allowed=true` + `switch_resets_progress=true` → 切目标清零；`false` → 保留
- [ ] 定轨—取消：`cancel_epitomized_path` → `selected_card=None`，之后不累积命定值、不翻转状态
- [ ] 定轨—不定轨抽：`selected_card=None` 且 `switch_epitomized_target` 可设初始目标
- [ ] 定轨—零阈值（fate_threshold=0）：始终处于保证状态，scope 内概率全部分配给 selected_card；切换目标无代价
- [ ] `epitomizable_cards` 正确校验——`card_id` 不在列表中 → 拒绝
- [ ] 终末地 120：`hard` + `max_triggers=1` + `deactivate_on_early_hit=true`——120 抽前已出 featured → 永久关闭
- [ ] 终末地 240：`hard` + `depends_on="featured_hard_120"`——120 保底首次命中后激活；激活前不计数、不调概率
- [ ] `selected_card` 建模方式已有明确决议（§3.9 已收敛）
- [ ] `_soft` 后缀 type（rotating_soft / rotating_cr_soft / targeted_soft）构造时创建内部 `SoftStepBehavior` 实例，软保底概率由 deltas 引擎统一计算——无独立 `_compute_soft_progress` / `_apply_soft_pity_boost` 函数
- [ ] 三态语法糖（`soft_start`/`soft_end` / `soft_start`/`soft_increment` / `soft_deltas`）正确由 `_expand_soft_to_deltas()` 展开
- [ ] 所有机制均不依赖 P55 之外的任何新基础设施
