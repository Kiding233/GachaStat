<!-- META: P56 | module:保底系统 | status:completed | last:2026-07-21 | depends:P60✅ -->

# P56 事件驱动保底——rotating / rotating_soft / rotating_cr / rotating_cr_soft / targeted / targeted_soft 完整实现 + LifecycleConfig 扩展

> 日期：2026-06-15 | 更新：2026-07-20 | 状态：设计中
> **2026-06-20 修正案 #1：** 捕获明光方案已决策——独立 `type="rotating_cr"`，`RotatingCRBehavior(RotatingBehavior)` 子类继承。`cr_state_probs` 为数组预留。详见 §3.3。
> **2026-06-20 修正案 #2：** 移除 `initial_win_rate` 参数——小保底 featured 占比由**基础概率分布**唯一确定。
> **2026-06-20 修正案 #3：** 新增集成 type——`_soft` 后缀 = 自带软保底。纯 type（`rotating`/`rotating_cr`/`targeted`）保留，集成 type（`rotating_soft`/`rotating_cr_soft`/`targeted_soft`）= 一个条目搞定 90% 场景。命名：rotating 家族统一前缀 + 后缀机制。`rotating_cr` 的 `cr` 缩写来自英文社区 Capturing Radiance 通用简称（Reddit/Fandom/ResetEra）。
> **2026-07-20 修正案 #5：** `_soft` 后缀改用 mixin 消除重复——`SoftPityMixin` 封装 deltas 引擎委托 + counter 管理，`RotatingSoftBehavior` / `RotatingCRSoftBehavior` / `TargetedSoftBehavior` 各从 ~25 行增量缩减到 ~5 行。详见 §3.3.5。
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

### 3.1 RotatingBehavior——纯净轮换保底

不继承 `CounterBasedBehavior`——无计数器。SSR 事件触发状态转移。不改变 SSR 总出率，只重分配 featured/非featured 的内部概率权重。**仅维护 `guaranteed` flag（大保底/小保底）。小保底不修改概率——featured 占比由基础分布决定（不硬编码 50%——如星铁光锥池 75/25、鸣潮武器池 100/0 均自动适配）。连歪计数器归入子类 `RotatingCRBehavior`。**

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

    def before_draw(self, ctx, readonly=False):
        """重分配 scope 内部 featured/非featured 比例。"""
        # REVIEW-R1-FIX: ISSUE-005 —— 新增 readonly 参数以兼容 PityEngine.get_probabilities() 只读查询
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
        self._lost_flag = Flag(state, name, "lost_rotating")
        self._fate_points = Counter(state, name, "fate_points")
        # selected_card 不从构造参数传入——策略通过 NonDrawAction 设定
        # PityState[name]["selected_card"] 初始为 None（不定轨状态）

    def before_draw(self, ctx, readonly=False):
        """重分配 scope 内部 featured/非featured 比例 + 命定值保证检查。"""
        # REVIEW-R1-FIX: ISSUE-005 —— 新增 readonly 参数以兼容 PityEngine.get_probabilities() 只读查询
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
        """将 featured 槽位收窄为仅包含 selected_card 对应的槽位。

        REVIEW-R1-FIX: ISSUE-003 —— 已决策：方案 (a) card_to_slot 映射表。
        实施时需在以下三处同步修改：

        1. **DrawInfo** 新增字段（pity.py 第13-24行）：
           ```python
           featured_cards: Mapping[str, tuple] = field(default_factory=dict)
           card_to_slot: Mapping[str, str] = field(default_factory=dict)
           ```

        2. **compute_scope_mappings()** 新增 card_to_slot 计算（pity.py 第793-832行）：
           返回值从 4 元组扩展为 5 元组 `(scope_cards, featured_cards, scope_slots,
           featured_slots, card_to_slot)`，并在循环内为每个 reward.id 写入其
           归属槽位：
           ```python
           card_to_slot: Dict[str, str] = {}
           for rwd, _prob in getattr(pool, 'rewards', []):
               extra = getattr(rwd, 'extra_info', {}) or {}
               rarity = extra.get('rarity', '').lower()
               slot = rarity
               if extra.get('featured'):
                   slot = f'{rarity}_featured'
               card_to_slot[rwd.id] = slot
           ```

        3. **所有调用点** 解包 5 元组并将 `card_to_slot` 传入 `DrawInfo` 构造。
        """
        if selected is None:
            return featured_slots

        # 主路径（O(1) 查找）——card_to_slot 由 compute_scope_mappings() 预计算
        card_to_slot = getattr(ctx.draw, 'card_to_slot', None) or {}
        target_slot = card_to_slot.get(selected)
        if target_slot and target_slot in featured_slots:
            return (target_slot,)

        # 降级防御：遍历 featured_slots，对每个 slot 查询其对应 rarity 的 scope_cards
        # REVIEW-R1-FIX: ISSUE-003 —— 原降级逻辑错误：无论检查哪个 slot，
        # scope_cards.get(self._scope) 均返回相同全部卡片列表。修正为根据
        # slot 名称反向推导 rarity（去除 '_featured' 后缀），再查找对应卡片集合。
        for slot in featured_slots:
            # slot 格式为 '{rarity}_featured' 或 '{rarity}'，
            # 去除 '_featured' 后缀得到 rarity 键
            rarity_key = slot.replace('_featured', '') if slot.endswith('_featured') else slot
            cards = ctx.draw.scope_cards.get(rarity_key, ())
            if selected in cards:
                return (slot,)
        return featured_slots  # 回退——selected 不在任何 featured 槽位中

    def _is_trigger_rarity(self, rarity, ctx):
        return rarity == self._scope

    def _scope_total_prob(self, ctx):
        slots = ctx.draw.scope_slots.get(self._scope, ())
        return sum(ctx.current.get(s, 0.0) for s in slots)

    def _featured_slots(self, ctx):
        return ctx.draw.featured_slots.get(self._scope, ())


def _redistribute_scope(ctx, featured_ratio, total, featured_slots, scope):
    """在 featured/非featured 之间重分配 scope 总概率。

    按基础权重比例分配（非均分）——保持 featured 内部和非 featured 内部各自的
    基础比例不变。均分会破坏多 featured 卡之间的权重关系。
    供 RotatingBehavior 和 TargetedBehavior 共用。
    """
    result = ctx.current.copy()
    featured_total = total * featured_ratio
    non_featured_total = total - featured_total

    # featured 内部按基础权重比例分配
    f_weights = [ctx.draw.base_probabilities.get(s, 0.0) for s in featured_slots]
    f_total_w = sum(f_weights)
    if f_total_w > 0:
        for s, w in zip(featured_slots, f_weights):
            result[s] = featured_total * w / f_total_w
    elif featured_slots:
        per_target = featured_total / len(featured_slots)
        for s in featured_slots:
            result[s] = per_target

    # 非 featured 内部按基础权重比例分配
    non_featured_slots = [
        s for s in ctx.draw.scope_slots.get(scope, ())
        if s not in featured_slots
    ]
    if non_featured_slots:
        nf_weights = [ctx.draw.base_probabilities.get(s, 0.0) for s in non_featured_slots]
        nf_total_w = sum(nf_weights)
        if nf_total_w > 0:
            for s, w in zip(non_featured_slots, nf_weights):
                result[s] = non_featured_total * w / nf_total_w
        else:
            per_target = non_featured_total / len(non_featured_slots)
            for s in non_featured_slots:
                result[s] = per_target

    return result
```

~65 行（移除 `initial_win_rate` / `loss_increment` 后缩减 ~15 行）。小保底 featured 占比由基础概率分布决定（对齐 rotating）。`switch_allowed` / `switch_resets_progress` 在 `NonDrawAction` 分发时由 `gacha_service` 读取本 behavior 配置执行；behavior 本身不处理切换逻辑——切换由策略驱动、模拟循环执行。

### 3.3 RotatingCRBehavior —— 捕获明光（修正案）

> **2026-06-20 修正案（替代 2026-06-17 更正）：** 方案已决策——独立 `type="rotating_cr"`，`RotatingBehavior` 的子类。英文社区 Capturing Radiance 通用缩写 CR（Reddit / Fandom / ResetEra / GameFAQs）。

**设计逻辑：**

捕获明光不能独立存在——它依附于轮换保底（rotating）。但没有 rotating 就没有「小保底」概念。因此：**同一份 rotating 逻辑，子类追加 CR 状态机。** 不与 `type="rotating"` 并存——一个池子只配一种。

**机制概要：**

```
出 SSR 时：
  ├─ 大保底（上次歪了）→ 100% featured → CR 无事可做
  └─ 小保底 → rotating 判定（featured 占比由基础分布决定）
       ├─ 直接赢 → cr_counter = 0
       ├─ 歪了但 CR 拦截 → 转败为胜，cr_counter 重置
       └─ 歪了且 CR 未拦截 → cr_counter++

cr_counter ≥ cr_counter_threshold → 下次小保底 100% 拦截
```

```python
class RotatingCRBehavior(RotatingBehavior):
    """轮换保底 + 捕获明光。

    继承纯净 RotatingBehavior 的全部轮换逻辑，追加：
      - cr_counter：连歪次数追踪
      - cr_state_probs：每个 counter 状态的拦截概率（数组预留）
      - cr_base_rate：每次祈愿的基础触发概率
    """

    # REVIEW-R1-FIX: ISSUE-002 —— 使用 random.random() 需在 pity.py 文件顶部添加：
    # import random
    # 当前全文件无 random 导入，直接使用将抛出 NameError。
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

    def before_draw(self, ctx, readonly=False):
        # REVIEW-R1-FIX: ISSUE-005 —— 新增 readonly 参数兼容只读查询；readonly 时跳过随机判定（确定性返回）
        if self._guaranteed.is_set():
            return super().before_draw(ctx, readonly=readonly)   # 大保底——CR 不干预

        if readonly:
            return super().before_draw(ctx, readonly=readonly)  # 只读——不做随机判定

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

        <!-- REVIEW-R1-FIX: ISSUE-017 —— 补传 readonly=readonly，保持与父类接口一致性。
        当前父类 RotatingBehavior.before_draw 不依赖 readonly 参数（无计数器操作），
        但若未来 RotatingBehavior 增加 readonly 相关逻辑，遗漏此参数将导致只读查询时错误修改状态。
        同时建议在 RotatingBehavior.before_draw 的 docstring 中注明 readonly 参数虽当前未使用但为接口契约保留。 -->
        return super().before_draw(ctx, readonly=readonly)       # 正常轮换（featured 占比由基础分布决定）

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

### 3.3.5 SoftPityMixin——软保底 mixin（消除 _soft 后缀类型重复）

> **2026-07-20 修正案 #5。** 三个 `_soft` 后缀类型（`RotatingSoftBehavior` / `RotatingCRSoftBehavior` / `TargetedSoftBehavior`）各自的 `__init__` / `before_draw` / `after_draw` 中软保底逻辑完全一致——`_expand_soft_to_deltas()` → `SoftStepBehavior` → counter 管理 → SSR 重置。提取为 `SoftPityMixin` 消除 ~75 行重复。

```python
class SoftPityMixin:
    """混入软保底——委托 P55 SoftStepBehavior deltas 引擎。

    使用方式：class FooSoft(SoftPityMixin, FooBehavior):
                  def __init__(self, name, state, scope, ..., **kwargs):
                      FooBehavior.__init__(self, name, state, scope, ...)
                      self._init_soft_pity(name, state, scope, **kwargs)

    MRO 关键：mixin 必须在前——mixin.before_draw 先调
    _compute_probabilities 再 super() 到父类行为。
    """

    def _init_soft_pity(self, name: str, state: 'PityState', scope: str, **kwargs):
        """子类 __init__ 中调用——解析三态语法糖并初始化引擎 + counter。

        三态优先级（从高到低）：
          1. soft_deltas（显式 RLE 数组）——直接透传，不经 _expand_soft_to_deltas
          2. soft_increment（累加）——每抽固定增量 %
          3. soft_start+soft_end（区间）——线性从 start 递增至 end（无增量参数，默认 interval）

        同时提供多个参数时按优先级选取，其余静默忽略。
        若三者均未提供 → 默认 soft_interval（start=74, end=90）。
        """
        # REVIEW-R1-FIX: ISSUE-023 —— 防御性断言：确保父类 __init__ 已设置 self._scope
        # （RotatingBehavior / TargetedBehavior 的 __init__ 中设置）。
        # 若调用顺序错误（先 _init_soft_pity 后父类 __init__），
        # after_draw 中访问 self._scope 将引发 AttributeError。
        assert hasattr(self, '_scope'), \
            'SoftPityMixin._init_soft_pity: 父类 __init__ 必须先于本方法调用以设置 self._scope'
        soft_deltas = kwargs.get('soft_deltas')
        <!-- REVIEW-R1-FIX: ISSUE-019 —— 将 `is not None` 改为 truthiness 检查 (if soft_deltas:)，
        空元组 () / 空列表 [] 将被拦截并回退到 elif 分支按默认语法糖展开。
        原检查 `() is not None` → True，导致空 deltas 传给 SoftStepBehavior，
        _cumulative_boost() 遍历 0 段永远返回 0.0——功能等价于无软保底但无任何警告。
        同样建议在 SoftStepBehavior.__init__ 中对空 deltas 发出 warning。 -->
        # REVIEW-R1-FIX: ISSUE-020 —— _expand_soft_to_deltas 定义于 config_toml.py（纯数学变换），
        # 需在方法体内惰性导入以规避 core → config 循环依赖。与 create_behavior()(pity.py:611) 模式一致。
        from .config_toml import _expand_soft_to_deltas  # noqa: E402
        if soft_deltas:
            # 显式 deltas 数组——直接透传（REVIEW-R1-FIX: ISSUE-003/004/011）
            btype = 'soft_step'
            deltas = soft_deltas
        elif kwargs.get('soft_increment') is not None:
            # 累加模式
            # REVIEW-R1-FIX: ISSUE-020 —— _expand_soft_to_deltas() 定义于 config_toml.py，
            # _init_soft_pity 定义于 pity.py（core 模块），形成 core → config 的反向依赖。
            # 当前 create_behavior()（pity.py:611）已通过函数内惰性导入规避循环导入：
            #   from .config_toml import _expand_soft_to_deltas
            # _init_soft_pity 需在方法内添加同样的惰性导入。
            # 架构建议：将 _expand_soft_to_deltas() 从 config_toml.py 移至 pity.py
            # （或新建 core/_pity_utils.py），消除跨层反向依赖。
            # 短期方案：两个调用点（create_behavior + _init_soft_pity）统一惰性导入路径。
            btype = 'soft_additive'
            deltas = _expand_soft_to_deltas(
                btype,
                kwargs.get('soft_start', 74),
                kwargs.get('soft_end', 90),
                kwargs['soft_increment'],
            )
        else:
            # 默认：区间模式
            btype = 'soft_interval'
            deltas = _expand_soft_to_deltas(
                btype,
                kwargs.get('soft_start', 74),
                kwargs.get('soft_end', 90),
                None,  # increment=None → binary interval
            )
        # REVIEW-R1-FIX: ISSUE-004 —— btype 作为第4个位置参数插入
        self._soft_engine = SoftStepBehavior(name + '_soft', state, scope, btype, deltas)
        self._counter = Counter(state, name, "counter")

    def before_draw(self, ctx: 'PityContext', readonly=False):
        # REVIEW-R1-FIX: ISSUE-005 —— 新增 readonly 参数；只读时跳过计数器递增
        # REVIEW-R1-FIX: ISSUE-001 —— 必须使用 self._counter.value() 获取整数值，
        # 不可直接传递 Counter 对象给 _compute_probabilities(ctx, counter: int)；
        # Counter 对象不支持 <</<= 等整数比较运算，运行时将抛出 TypeError
        if readonly:
            v = self._counter.value()
        else:
            v = self._counter.incr()  # incr() 返回新值（参照 CounterBasedBehavior 第160行模式）
        modified = self._soft_engine._compute_probabilities(ctx, v)
        forked = PityContext(draw=ctx.draw, current=modified, state=ctx.state)
        return super().before_draw(forked, readonly=readonly)

    def after_draw(self, ctx: 'PityContext'):
        # REVIEW-R1-FIX: ISSUE-023 —— self._scope 由父类（RotatingBehavior / TargetedBehavior）
        # 的 __init__ 设置，而非本 mixin。若某个未来子类调用顺序错误（先 _init_soft_pity
        # 后父类 __init__）或父类忘记设置 _scope，此处将引发 AttributeError。
        # 建议在 _init_soft_pity 开头追加防御性断言：
        #   assert hasattr(self, '_scope'), '父类 __init__ 必须先于 _init_soft_pity 调用'
        # 或在 SoftPityMixin 中直接设置 self._scope = scope（与父类重复但不冲突）。
        # 同时在实施说明中标注此调用顺序约束。
        if ctx.draw.reward_rarity == self._scope:
            self._counter.reset()
        super().after_draw(ctx)
```

~25 行。`_init_soft_pity()` 在子类 `__init__` 末尾调用一次；`before_draw` / `after_draw` 由 Python MRO 自动串联——mixin 写在继承列表首位，`super()` 调用下一顺位（`RotatingBehavior` / `RotatingCRBehavior` / `TargetedBehavior`）。

### 3.4 RotatingSoftBehavior——轮换 + 软保底（mixin 版）

`type="rotating_soft"`。`SoftPityMixin` + `RotatingBehavior` 组合。~5 行增量。

**继承链：** `PityBehavior` → `RotatingBehavior` → `SoftPityMixin` → `RotatingSoftBehavior`

**内部状态：** `counter`（mixin 提供）+ `guaranteed` flag（RotatingBehavior 提供）

> **2026-06-20 修正案 #4：** `_compute_soft_progress()` / `_apply_soft_pity_boost()` 已移除——`_soft` 后缀 type 统一通过 P55 的 `SoftStepBehavior` deltas 引擎消费软保底概率。三态语法糖（`soft_start`/`soft_end` / `soft_start`/`soft_increment` / `soft_deltas`）在构造时由 `_expand_soft_to_deltas()` 展开为 deltas。**2026-07-20 修正案 #5 进一步提取为 mixin。**

```python
class RotatingSoftBehavior(SoftPityMixin, RotatingBehavior):
    """轮换保底 + 软保底。mixin 提供 counter 管理 + deltas 引擎委托。"""

    def __init__(self, name, state, scope="ssr", **kwargs):
        RotatingBehavior.__init__(self, name, state, scope)
        self._init_soft_pity(name, state, scope, **kwargs)
```

~5 行。`before_draw` / `after_draw` 由 mixin 提供——不再重复实现。`_is_hit` / `_is_trigger_rarity` / `_scope_total_prob` / `_featured_slots` 从 `RotatingBehavior` 继承。

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

### 3.5 RotatingCRSoftBehavior——轮换 + 捕获明光 + 软保底（mixin 版）

`type="rotating_cr_soft"`。`SoftPityMixin` + `RotatingCRBehavior` 组合。~5 行增量。

```python
class RotatingCRSoftBehavior(SoftPityMixin, RotatingCRBehavior):
    """轮换 + CR + 软保底。mixin 提供 counter 管理 + deltas 引擎委托。"""

    def __init__(self, name, state, scope="ssr",
                 cr_counter_threshold=3, cr_base_rate=0.0,
                 cr_state_probs=None, **kwargs):
        RotatingCRBehavior.__init__(self, name, state, scope,
                                    cr_counter_threshold, cr_base_rate,
                                    cr_state_probs)
        self._init_soft_pity(name, state, scope, **kwargs)
```

~5 行增量。`before_draw` / `after_draw` 由 mixin 提供——不再重复实现。

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

### 3.6 TargetedSoftBehavior——定轨 + 软保底（mixin 版）

`type="targeted_soft"`。`SoftPityMixin` + `TargetedBehavior` 组合。~5 行增量。

```python
class TargetedSoftBehavior(SoftPityMixin, TargetedBehavior):
    """定轨 + 软保底。mixin 提供 counter 管理 + deltas 引擎委托。"""

    def __init__(self, name, state, scope="ssr",
                 fate_threshold=1, switch_allowed=True,
                 switch_resets_progress=True, **kwargs):
        TargetedBehavior.__init__(self, name, state, scope,
                                  fate_threshold, switch_allowed,
                                  switch_resets_progress)
        self._init_soft_pity(name, state, scope, **kwargs)
```

~5 行增量。`before_draw` / `after_draw` 由 mixin 提供——不再重复实现。

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

#### 3.7.1 LifecycleConfig——核实已就绪逻辑并补充缺失部分

<!-- REVIEW-R1-FIX: ISSUE-006 —— 标题从「扩展」改为「核实已就绪逻辑并补充缺失部分」。以下字段和逻辑已在 P55 中实现，P56 无需重新实现，仅需在 PityEngine 中补齐缺失部分。 -->

**已就绪（P55 已实现，无需变动）：**

1. `LifecycleConfig` dataclass 字段已存在（pity.py:76-84）：
   - `max_triggers: int = 0`——`CounterBasedBehavior` 中已实现耗尽后 `_active.clear()`
   - `deactivate_on_early_hit: bool = False`——`HardPityBehavior._on_reset()` 钩子（pity.py:424-434）和 `SoftStepBehavior._on_reset()`（pity.py:307-317）中已实现
   - `depends_on: Optional[str] = None`——`CounterBasedBehavior.__init__`（pity.py:124）已处理：`depends_on is None` → `_active.set()`；有依赖 → `_active` 初始 `False`

2. `CounterBasedBehavior.before_draw` 开头检查 `_active.is_set()`——尚未激活时不调概率、不递增计数器（已在 P55 实现）。

**P56 需要补充（真正缺失的部分）：**

- `PityEngine._build_activation_graph()`——解析 `depends_on` 关系，构造依赖图
- `PityEngine.after_draw` 中的 `did_fire()` 传播——激活依赖方

**`deactivate_on_early_hit` 校验：** `deactivate_on_early_hit = true` 仅允许配合 `type = "hard"`——soft_interval / soft_additive 使用此参数 → ConfigError。

<!-- REVIEW-R1-FIX: ISSUE-010 —— 在 _build_pity()（config_toml.py:537行附近）PityDef 构造前追加类型绑定校验： -->
**REVIEW-R1-FIX: ISSUE-010 —— 实施时在 `_build_pity()` 中 PityDef 构造前追加：**
```python
# config_toml.py _build_pity() 中 PityDef 构造前
deactivate_on_early_hit = lifecycle_raw.get('deactivate_on_early_hit', False)
if deactivate_on_early_hit and btype != 'hard':
    raise ConfigError(
        f"保底 '{name}'：deactivate_on_early_hit=true 仅允许配合 type='hard'，"
        f"当前 type='{btype}'。soft_interval/soft_additive/rotating/targeted 等"
        f"事件驱动型保底不支持提前命中停用。"
    )
```
此为 TOML 解析层第一道防线——与 `PityEngine._validate_behaviors` 的运行时校验形成纵深防御。

**`depends_on`：** 依赖方（如 240 保底）首次命中 featured 后才激活。`_active` flag 初始 False 的机制已由 P55 实现，P56 仅需补齐引擎侧的声明式依赖传播（见 §3.7.2）。

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
                # REVIEW-R1-FIX: ISSUE-021 —— depends_on 双方 pools 交集校验
                source_bh = _bh_by_name.get(dep.depends_on)
                if source_bh is not None:
                    src_pools = set(getattr(source_bh, '_pools', ()))
                    dst_pools = set(getattr(bh, '_pools', ()))
                    if '*' not in src_pools and '*' not in dst_pools:
                        if not (src_pools & dst_pools):
                            import warnings
                            warnings.warn(
                                f"「{bh.name}」的 depends_on 指向「{dep.depends_on}」，"
                                f"但双方 pools 无交集——依赖方可能永远不会被激活"
                            )
        <!-- _bh_by_name 为构造时预建的 {name: behavior_instance} 映射表，与 all_names 同期构建。 -->
        return graph

    # REVIEW-R1-FIX: ISSUE-006 —— 激活传播必须限定在当前池关联的 behavior 范围内。
    # 现有 after_draw（pity.py:1024）通过 _behaviors_for_pool(pool_id) 按池过滤；
    # 伪代码原先直接遍历 self._behaviors（全量+dict 类型错误）与现有模式不一致。
    # 正确做法：在 _behaviors_for_pool() 循环内部追加 did_fire() 依赖激活传播。
    #
    # REVIEW-R1-FIX: ISSUE-018 —— 签名方案决策：采用方案 (a)——保持当前签名不变
    # def after_draw(self, pool_id: str, state: PityState, reward_id: str)，
    # 在 after_draw 内部基于 reward_id 构造 DrawInfo（沿用现有逻辑），
    # 仅追加 did_fire 传播循环。不改动 gacha_service.py:272 的调用方式。
    # 若未来需在 after_draw 中使用 DrawInfo 的更多字段，可再评估迁移至方案 (b)。
    # 方案 (a) 改动最小且不影响调用链。
    <!-- REVIEW-R1-FIX: ISSUE-024 —— 签名修正为与决策一致的 (pool_id, state, reward_id)；内部基于 pool_spec 构造 DrawInfo（参照当前 pity.py:1002-1021 实际实现） -->
    def after_draw(self, pool_id, state, reward_id):
        # 内部基于 pool_spec + reward_id 构造 DrawInfo（参照 pity.py:1011-1021）
        draw_info = DrawInfo(pool_id=pool_id, reward_id=reward_id, ...)  # 伪代码示意，实际构造见现有代码
        ctx = PityContext(draw=draw_info, current={}, state=state)
        # REVIEW-R1-FIX: ISSUE-006 —— 必须使用 _behaviors_for_pool(pool_id)
        # 而非 self._behaviors（全量遍历会错误跨池激活）。
        for pname, bh in self._behaviors_for_pool(pool_id):
            bh.after_draw(ctx)
            # 引擎自动传播激活事件——仅限当前池关联的 behavior
            if bh.did_fire(ctx):        # behavior 暴露语义方法
                for dep_name in self._activation_graph.get(bh.name, []):
                    state.set(dep_name, "_active", True)
```

每个 behavior 暴露 `did_fire(ctx) → bool`：

- `CounterBasedBehavior`：`_should_reset(ctx)` 为真时返回 True（计数器驱动保底「触发」= 命中 scope 目标）
- `RotatingBehavior`：`_is_hit(ctx)` 为真时返回 True（首次命中 featured/selected_card）

> **⚠️ 命名提醒：** `did_fire` 的字面意思是「保底触发了吗」，但实际语义是「目标被获取了吗」。前者暗示 hard 保底达到阈值时返回 True，后者是每次命中目标稀有度都返回 True。两种理解在当前 `depends_on` 场景下**功能等价**（都是 `_active.set(True)`，幂等），但**不要在 `did_fire` 上追加「区分触发类型」的返回值设计**——当前 `bool` 已满足 `depends_on` 激活的全部需求，引入枚举或事件类型属于过度设计。
>
> <!-- REVIEW-R1-FIX: ISSUE-015 —— did_fire 语义歧义已验证：CounterBasedBehavior.did_fire=「保底触发了吗」(_should_reset)，RotatingBehavior.did_fire=「目标被获取了吗」(_is_hit)。两者在当前 depends_on 场景功能等价。实施时在 docstring 中明确标注：did_fire 返回 bool，仅用于 depends_on 激活传播——不要在此追加事件类型区分。 -->

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

<!-- REVIEW-R1-FIX: ISSUE-010 —— epitomizable_cards 字段全代码库零引用，需新建全链路 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-3 —— Pool 构造（batch_simulator.py:543-554）无 epitomizable_cards 参数。
     Pool dataclass（pool.py:175-188）无 epitomizable_cards 字段。阻塞项——_apply_non_draw 依赖此字段存在。
     已由以下清单的 `core/pool.py` 行覆盖。 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-9 —— _apply_non_draw 需要 pool.epitomizable_cards 校验 + PityEngine 公开方法。
     依赖整条 epitomizable_cards 链路就绪（步骤 C/九-a + K/九-b + L+M/九-c+十二-c）。已由以下清单覆盖。 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-10 —— card_to_slot 映射（ISSUE-003）。compute_scope_mappings 需扩展为 5 元组 +
     DrawInfo 新增 featured_cards / card_to_slot 字段。已在 §3.2 TargetedBehavior._resolve_selected_slots 中完整设计。
     波及范围表 `core/pity.py` 行已标注。本清单补充 card_to_slot 改动项。 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-12 —— TOML 加载：_build_pools() 第 897-911 行无 epitomizable_cards 参数。
     PoolEntry dataclass 当前无此字段。已由以下清单覆盖。 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-13 —— TOML 序列化：_save_templates_and_pools() 第 196-230 行 pool_dict 不含 epitomizable_cards。
     需追加条件输出（列表非空时才写入）。已由以下清单覆盖。 -->
**`epitomizable_cards` 全链路新建清单（阻塞——targeted 保底运行前提）：**

| 位置 | 改动 | 覆盖审计问题 |
|------|------|:---:|
| `core/config_store.py` — `PoolEntry` dataclass | 新增字段 `epitomizable_cards: List[str] = field(default_factory=list)` | AUDIT-BREAK-12 |
| `core/config_store.py` — `Pool` 类 | 新增 `epitomizable_cards` 只读属性（从 PoolEntry 传递） | — |
| `core/pool.py` — `Pool` dataclass（第176-188行） | 新增 `epitomizable_cards: list` 字段。**阻塞项——遗漏则 _apply_non_draw() 中 pool.epitomizable_cards 抛 AttributeError。** | AUDIT-BREAK-3/9 |
| `core/pity.py` — `DrawInfo` + `compute_scope_mappings()` | **card_to_slot 管线（ISSUE-003）：** DrawInfo 新增 `featured_cards` / `card_to_slot` 字段；`compute_scope_mappings()` 返回值扩展为 5 元组（新增 `card_to_slot: Dict[str, str]`）；所有调用点解包更新。详见 §3.2 `_resolve_selected_slots` 设计。 | AUDIT-BREAK-10 |
| `service/batch_simulator.py` — `SimulationEnv`（第52行）+ `SimulationEnvBuilder.from_config_store()`（第571-586行）+ `_build_pity_engine_from_gui()`（第99-118行） | 传播 `epitomizable_cards` 字段至运行时；Pool 构造处（第543行）传入 `Pool(epitomizable_cards=pool_entry.epitomizable_cards)`。**AUDIT-BREAK-3：此为 Pool 构造断裂的修复点——当前第543-554行 Pool(...) 无此参数。** | AUDIT-BREAK-1/2/3 |
| `core/config_toml.py` — `_build_pools()` 解析（第897-911行） | 读取 `[[pool]].epitomizable_cards` + 校验其中 card_id 在池子 distribution 中存在（不存在 → ConfigError）；PoolEntry 构造追加 `epitomizable_cards=...` 参数。 | AUDIT-BREAK-12 |
| `core/config_toml.py` — `_save_templates_and_pools()` 序列化（第196-230行） | pool_dict 追加 `'epitomizable_cards': getattr(pool, 'epitomizable_cards', [])`，仅列表非空时写入以保持 TOML 简洁。 | AUDIT-BREAK-13 |
| `service/gacha_service.py` — `_apply_non_draw()` | NonDrawAction `switch_epitomized_target` 执行时校验 `card_id ∈ pool.epitomizable_cards`。需 PityEngine 公开 `get_behaviors_for_pool()` + `get_pity_def()` 查询方法（见 §3.9 ISSUE-011/026）。 | AUDIT-BREAK-9 |
| `gui/config_panel.py` — `get_config()` / `set_config()` / `apply_to_store()` | 池子级序列化：`get_config()`（第2878-2895行）pools dict 追加 `'epitomizable_cards'`；`set_config()`（第3023-3035行）PoolEntry 追加读取；`apply_to_store()`（第3546-3558行）PoolEntry 追加读取。三者缺一不可——分别对应 AUDIT-BREAK-14/15/16。 | AUDIT-BREAK-14/15/16 |

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
name = "rotating_char"
type = "rotating"
scope = "ssr"
pools = ["limited_character"]

# ── rotating_soft ——轮换 + 软保底 ──

# 原神 4.x 角色池——74→90 软保底 + 轮换（featured 占比 50% 由基础分布决定）
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

### 3.8 附加：初始状态字段——模拟开始前的快照

`counter_init`（P55 已定义）覆盖了计数器驱动型保底的初始水位，但事件驱动型保底也有初始状态需求。以下两个字段在 P55 的 `PityDef` 中定义，语义说明在此。

#### `guaranteed_init` —— rotating 家族初始大保底状态

| 属性 | 值 |
|------|-----|
| 类型 | `bool` |
| 默认 | `false`（从小保底开始） |
| 适用 | `rotating` / `rotating_soft` / `rotating_cr` / `rotating_cr_soft` |

`true` = 模拟开始时已处于大保底——等价于「上一个 SSR 歪了，下一个 SSR 必出 featured」。

典型场景：玩家在上一期卡池中歪了常驻，保底状态继承到本期。模拟此场景时，不需要追溯上一期的抽卡历史——直接将初始状态标记为大保底即可：

```toml
# 米池场景：已垫 73 抽 + 大保底状态
[[pity]]
name = "rotating_soft_char"
type = "rotating_soft"
scope = "ssr"
soft_start = 74
soft_end = 90
counter_init = 73
guaranteed_init = true
```

`SimulationEnvBuilder` 在构造 `PityState` 时：

```python
# REVIEW-R1-FIX: ISSUE-012 —— _build_pity_state_init()（pity.py:757-764）已实现无类型检查版本，
# 对所有 PityDef 无条件注入 guaranteed_init / fate_points_init。以下类型族守卫版本为更强的约束——
# 实施时评估：保留现有无类型检查版本（更宽松、更多用户场景）vs 追加类型族守卫（更严格、避免误配置）。
# 两版本语义不冲突——类型族版本是现有版本的子集。避免在两个位置重复实现同一逻辑。
if pdef.guaranteed_init and pdef.btype in ROTATING_FAMILY:
    state.set(pdef.name, "guaranteed", True)
```

<!-- REVIEW-R1-FIX: ISSUE-004 —— ROTATING_FAMILY 和 TARGETED_FAMILY 全代码库零引用（Grep 确认）。
实施时若采用类型族守卫版本，需先在 pity.py 的 BEHAVIOR_REGISTRY 附近定义：
    ROTATING_FAMILY = frozenset({'rotating', 'rotating_soft', 'rotating_cr', 'rotating_cr_soft'})
    TARGETED_FAMILY = frozenset({'targeted', 'targeted_soft'})
当前 _build_pity_state_init()（pity.py:757-764）已实现无条件注入版本（无需这些常量），
类型族守卫版本语义上等价但增加了类型约束——实施时评估是否值得额外维护两组常量。 -->

#### `fate_points_init` —— targeted 家族初始命定值

| 属性 | 值 |
|------|-----|
| 类型 | `int` |
| 默认 | `0`（从零开始） |
| 适用 | `targeted` / `targeted_soft` |

`1` = 已歪一次但未触发保证——等价于「定轨值=1，再歪一次触发命定值保证」。

典型场景：武器池已歪了一次非目标武器，命定值=1。模拟此场景时：

```toml
[[pity]]
name = "epitomized_weapon"
type = "targeted"
scope = "ssr"
fate_threshold = 1
fate_points_init = 1               # 已歪一次，命定值=1
```

`SimulationEnvBuilder` 在构造 `PityState` 时：

```python
# REVIEW-R1-FIX: ISSUE-012 —— 同上：_build_pity_state_init()已实现无类型检查版本。
# 评估是否追加 TARGETED_FAMILY 守卫。避免重复实现。
if pdef.fate_points_init and pdef.btype in TARGETED_FAMILY:
    state.set(pdef.name, "fate_points", pdef.fate_points_init)
```

#### `selected_card_init` —— targeted 家族初始选定卡片

<!-- REVIEW-R1-FIX: ISSUE-012 —— _build_pity_state_init() 当前未注入 selected_card 初始状态。
虽然 TargetedBehavior.after_draw 通过 ctx.state.get(self._name, "selected_card") 读取时
键不存在返回 None（功能无损），但缺少显式注入在调试和状态序列化时造成困惑——
同一个 behavior 的 namespace 中，counter/guaranteed/fate_points 可见但 selected_card 不可见，
直到首次 NonDrawAction 设置。为保持一致性和调试友好性，追加显式注入。 -->

**REVIEW-R1-FIX: ISSUE-012 —— 在 `_build_pity_state_init()`（pity.py:763行后）追加：**
```python
# selected_card_init：targeted 家族初始目标卡片（默认 None=不定轨）
_TARGETED_TYPES = frozenset({'targeted', 'targeted_soft'})
if pdef.btype in _TARGETED_TYPES:
    state.set(pdef.name, "selected_card", None)  # 显式 None 优于隐式缺失
```

> **设计说明：** `selected_card` 不像 `counter_init`/`guaranteed_init`/`fate_points_init` 那样暴露为 TOML 配置字段——因为 selected_card 由策略 NonDrawAction 运行时设定（参见 §3.9 决议）。`_build_pity_state_init()` 仅注入显式 `None` 以保持 namespace 完整性，不提供 TOML 级的 `selected_card_init` 字段。用户如需模拟「初始已选目标」场景，应通过策略在模拟开始前发出 `NonDrawAction("switch_epitomized_target", ...)`。

#### 设计决策：独立字段 vs 通用 `initial_state: dict`

三个初始状态字段（`counter_init` / `guaranteed_init` / `fate_points_init`）各自类型明确：
- `counter_init: int` → QSpinBox
- `guaranteed_init: bool` → 复选框
- `fate_points_init: int` → QSpinBox

若改为 `initial_state = {counter = 73, guaranteed = true}` 自由 dict：
- 失去类型安全——GUI 无法自动渲染正确控件
- TOML 语义不直观——嵌套表不如平级字段清晰
- 写入 PityState 时退化为盲目遍历——不知道哪些 key 是合法的

**结论：三个独立字段——简洁、类型安全、GUI 元数据驱动渲染无障碍。**

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

#### NonDrawAction 类定义

<!-- REVIEW-R1-FIX: ISSUE-009 —— 补充 NonDrawAction dataclass 定义 + NON_DRAW_ACTION_REGISTRY -->

```python
# core/action.py

@dataclass
class NonDrawAction(Action):
    """非抽卡动作——由策略返回，执行保底状态管理操作。

    与 DrawAction/WaitAction 平级，type='non_draw'。
    action_id 区分具体子操作（switch_epitomized_target / cancel_epitomized_path），
    params 携带操作所需数据（pool_id / card_id 等）。
    """
    action_id: str       # 子操作标识符，对应 NON_DRAW_ACTION_REGISTRY 的 key
    params: dict         # 子操作所需参数（pool_id / card_id / ...）
    type: Literal['non_draw'] = 'non_draw'

    def __repr__(self) -> str:
        return f"NonDrawAction('{self.action_id}', {self.params})"


# 注册表——action_id → 元数据（参数约束、描述等）
NON_DRAW_ACTION_REGISTRY: Dict[str, dict] = {
    'switch_epitomized_target': {
        'description': '设置或切换定轨目标卡片',
        'required_params': ('pool_id', 'card_id'),
        'optional_params': (),
    },
    'cancel_epitomized_path': {
        'description': '取消定轨（回到不定轨状态）',
        'required_params': ('pool_id',),
        'optional_params': (),
    },
}

<!-- REVIEW-R1-FIX: ISSUE-025 —— InvalidActionError 异常类定义。在 action.py 中与 NonDrawAction 同文件新增： -->
class InvalidActionError(ValueError):
    """运行时动作拒绝——如切换不允许的目标、未注册的 action_id 等。

    与 ConfigError（配置解析阶段错误，config_store.py:8）不同：
    InvalidActionError 在模拟运行时由 _apply_non_draw() 抛出，
    表示策略发出了当前保底配置不允许的动作。
    """
    pass
```

~25 行。NonDrawAction 与 DrawAction/WaitAction 保持一致的 `@dataclass` 模式。二级 `action_id` 区分具体操作，`NON_DRAW_ACTION_REGISTRY` 声明参数约束——gacha_service 在执行前校验。

`gacha_service._apply_non_draw()` 分发时：
1. 校验 `action_id in NON_DRAW_ACTION_REGISTRY`（不存在则 InvalidActionError）
2. 校验 `card_id ∈ pool.epitomizable_cards`（仅 switch_epitomized_target）
3. 校验 `pity_def.switch_allowed == true`（拒绝切 → 静默忽略或 InvalidActionError；仅 switch_epitomized_target）
4. 写 `PityState[name]["selected_card"]`
5. 若 `switch_resets_progress` → `PityState[name]["fate_points"] = 0`（仅 switch_epitomized_target）
6. cancel_epitomized_path 处理（`_apply_non_draw` 内）：
   ```python
   if action.action_id == 'cancel_epitomized_path':
       state.set(behavior_name, "selected_card", None)
       # REVIEW-R1-FIX: ISSUE-022 —— 重置仅追踪计数器，避免残留值在后续分析/调试中误导
       state.set(behavior_name, "lost_rotating", False)   # _lost_flag.clear()
       state.set(behavior_name, "losses", 0)               # _losses.reset()
   ```
   <!-- 说明：_lost_flag 和 _losses 虽标注为「仅追踪不影响概率」（§3.2 line 160-161），
   但取消定轨后保留上次会话残留值会使分析/调试产生误导——重新定轨后 losses>0 或 lost_flag=True
   暗示存在被继承的歪历史。重置后语义清晰：取消=白纸状态。 -->

#### PityEngine 查询接口扩展——支持 _apply_non_draw 决策

<!-- REVIEW-R1-FIX: ISSUE-011 —— GachaService._apply_non_draw() 执行 switch_epitomized_target 时
需查询当前池关联的 targeted behavior 的 switch_allowed/switch_resets_progress 配置。
当前 PityEngine（pity.py:1038-1058）暴露的查询接口不含此能力。方案 (a)：PityEngine 新增
get_pity_def(name) 方法——通过 self.pity_defs 字典返回原始 PityDef 对象。 -->

**REVIEW-R1-FIX: ISSUE-011 —— 在 PityEngine（pity.py）中新增查询方法：**
```python
# PityEngine 新增方法（约第1058行 _behavior_list 属性之后）
def get_pity_def(self, name: str):
    """返回指定 behavior 的原始 PityDef 配置（只读视图）。

    GachaService._apply_non_draw() 通过此方法获取 targeted behavior
    的 switch_allowed / switch_resets_progress 配置以校验 NonDrawAction。
    """
    if self.pity_defs is None:
        self.pity_defs = _build_pity_defs_index(self._pity_defs_raw)
    return self.pity_defs.get(name)
```

GachaService 使用方式（gacha_service.py `_apply_non_draw()` 内）：
```python
pity_def = self.pity_engine.get_pity_def(targeted_behavior_name)
if pity_def and not getattr(pity_def, 'switch_allowed', True):
    # 拒绝切换——该 targeted behavior 不允许中途切换目标
    raise InvalidActionError(f"保底 '{targeted_behavior_name}' 不允许切换目标")
```

方案选择说明：方案 (a) 比方案 (b)（GachaService 构造函数直接接收 `pity_defs: List[PityDef]`）更简洁——不增加 GachaService 构造函数参数数量，且 PityEngine 本身已在 `__init__` 中持有 `pity_defs` 字典（第906行）。

<!-- REVIEW-R1-FIX: ISSUE-026 —— _apply_non_draw 如何从 pool_id 定位池子的 targeted behavior 名称：
     当前 PityEngine._behaviors_for_pool(pool_id) 是私有方法（pity.py:935），返回
     List[Tuple[str, PityBehavior]]。GachaService._apply_non_draw() 需要遍历此列表查找
     isinstance(bh, TargetedBehavior) 的条目以获取其名称，进而通过 get_pity_def(name)
     查询 switch_allowed / switch_resets_progress 配置。
     实施时采用方案 (a)：将 _behaviors_for_pool 公开为 get_behaviors_for_pool(pool_id)，
     由 GachaService 自行遍历 + isinstance 过滤。改动最小。
     边界条件：池子无 targeted behavior 时 NonDrawAction 在该池子上为无效操作——
     应抛出 InvalidActionError（ISSUE-025 新增异常类），提示用户该池子不支持定轨。
     波及范围表已标注此新增公开方法。 -->

#### 不定轨是合法状态

`selected_card = None`（初始默认值）。此时 `TargetedBehavior`：
- `_is_hit()` 返回 `False` → 命定值不累积
- `before_draw()` 正常调整概率（featured 占比由基础分布决定）——不定轨也能抽
- `after_draw()` 看到 `selected_card is None` → 直接 return，不累积不翻转

对应现实：原神取消定轨后照样抽武器池，出金随机。

#### 为何不在 `[[pity]]` 中静态配置 `selected_card`

- 方案搜索（P26）需要遍历「初始选哪张」「歪了之后是否换目标」——静态配置无法覆盖
- `NonDrawAction` 将选择权交给策略——搜索空间自然包含定轨决策节点
- 简单模拟（策略不返回 NonDrawAction）→ 默认 `selected_card = None`（不定轨），用户可通过 GUI 设初始选择

#### 与 P55 `[[pity]].pools` 的关系

`pools` 控制 behavior 的作用域——`targeted` 的 `fate_points` 和 `guaranteed` 在 `pools` 声明的池子间共享。跨期继承由 `pools` 的作用范围自然推导——不需要额外的 `carry_over` 参数。

### 3.10 实施阶段

<!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 —— 阶段排序说明（拆分版）：SoftPityMixin 依赖 _expand_soft_to_deltas（来自 config_toml）和 SoftStepBehavior（已存在）——阶段一无前置依赖。LifecycleConfig 核实（阶段一b-a）+ PityEngine 激活图（阶段一b-b）的构建逻辑独立于具体 behavior，可先行实现并通过已有 CounterBasedBehavior.did_fire() 验证——提前至阶段一之后有利于尽早集成测试。原阶段十/十一（LifecycleConfig 最终集成 + PityEngine 最终集成）与阶段一b 功能重叠——本版合并为阶段一b-b 的子验证步骤，消除冗余。 -->

| 阶段 | 内容 | 预估 |
|------|------|:---:|
| **阶段〇** | <!-- REVIEW-R1-FIX: ISSUE-001 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-5 —— 此阶段修复审计发现的"总开关"断裂：PityEngine.__init__ 第915-917行显式跳过6个事件驱动型btype。移除后 P56 系统才对 PityEngine 可见。--> **移除 `PityEngine.__init__` 第915-917行的 P56 类型跳过守卫**（`if pdef.btype in ('rotating', 'targeted', 'rotating_cr', 'rotating_cr_soft', 'rotating_soft', 'targeted_soft'): continue`）。此守卫在 P55 中作为 stub 占位——不删除则新增的 6 个 behavior 类即使已注册也无法被引擎加载。**阻塞项——若遗漏则整个 P56 无法生效。**<br/><br/>**原子依赖（AUDIT-BREAK-24）：** 此阶段与阶段〇b-a（create_behavior P56扩展）和BEHAVIOR_REGISTRY class赋值构成原子组——任一点未完成则 PityEngine 构造时 ValueError 崩溃。三者必须在同一次提交中完成。 | 5min |
| **阶段〇b-a** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-4 —— 此阶段修复 create_behavior 工厂函数的参数传播断裂。当前仅处理P55字段（deltas/threshold/target_featured/reset/lifecycle），P56事件驱动型字段（cr_counter_threshold/cr_base_rate/cr_state_probs/fate_threshold/switch_allowed/switch_resets_progress/soft_deltas）完全未读取。TOML中的P56配置值被静默丢弃——behavior构造函数使用签名默认值。--> **`create_behavior()` 工厂函数扩展——P56 参数解析**（pity.py:570-634）。当前仅处理 counter 驱动型参数（`deltas` / `threshold` / `target_featured` / `reset` / `lifecycle`）。需新增 P56 事件驱动型专属参数的解析与透传：`cr_counter_threshold` / `cr_base_rate` / `cr_state_probs` / `fate_threshold` / `switch_allowed` / `switch_resets_progress` / `soft_deltas` / `guaranteed_init` / `fate_points_init`。若工厂不更新，RotatingCRBehavior / TargetedBehavior / SoftPityMixin 构造时将因缺少参数而使用错误默认值或直接崩溃。**阻塞项。****同步在 pity.py 文件顶部添加 `import random`**（REVIEW-R1-FIX: ISSUE-002——RotatingCRBehavior.before_draw 使用 `random.random()` 需此依赖）。<br/><br/>**params dict 追加字段清单（AUDIT-BREAK-4）：** `'cr_counter_threshold': getattr(pdef, 'cr_counter_threshold', None)` / `'cr_base_rate': getattr(pdef, 'cr_base_rate', None)` / `'cr_state_probs': getattr(pdef, 'cr_state_probs', None)` / `'fate_threshold': getattr(pdef, 'fate_threshold', None)` / `'switch_allowed': getattr(pdef, 'switch_allowed', None)` / `'switch_resets_progress': getattr(pdef, 'switch_resets_progress', None)` / `'soft_deltas': getattr(pdef, 'soft_deltas', None)` / `'guaranteed_init': getattr(pdef, 'guaranteed_init', False)` / `'fate_points_init': getattr(pdef, 'fate_points_init', 0)`。 | 30min |
| **阶段〇b-b** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --> **`_SOFT_SUFFIX_TYPES` 守卫**（REVIEW-R1-FIX: ISSUE-007）。`create_behavior()` 第608-616行对 `_soft` 后缀类型调用 `_expand_soft_to_deltas(pdef.btype, ...)` 时，`pdef.btype` 为 `'rotating_soft'`/`'rotating_cr_soft'`/`'targeted_soft'`，而 `_expand_soft_to_deltas`（config_toml.py:571-602）仅识别 `'soft_interval'` 和 `'soft_additive'`。SoftPityMixin._init_soft_pity() 会独立重新展开语法糖（忽略空 deltas），为保持职责清晰，create_behavior() 应在 `_soft` 后缀类型上跳过语法糖展开。实施时在 `elif hasattr(pdef, 'soft_start')` 分支前追加类型守卫：<br/>```python<br/>_SOFT_SUFFIX_TYPES = frozenset({'rotating_soft', 'rotating_cr_soft', 'targeted_soft'})<br/>if pdef.btype in _SOFT_SUFFIX_TYPES:<br/>    pass  # deltas 由 SoftPityMixin._init_soft_pity() 独立展开<br/>elif hasattr(pdef, 'soft_start') and pdef.soft_start is not None:<br/>``` | 15min |
| **阶段〇b-c** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --> **`guaranteed_init` / `fate_points_init` 透传**。验证 `create_behavior()` 中这两个字段已正确从 PityDef 读取并传入对应 behavior 构造函数（RotatingBehavior / TargetedBehavior）。若 P55 `PityDef` 中字段已存在但工厂未透传，行为类构造函数将使用默认值（False / 0）而静默丢弃 TOML 配置。 | 15min |
| **阶段〇b-d** | <!-- REVIEW-R1-FIX: AUDIT-BREAK-6 —— 此阶段修复 BEHAVIOR_REGISTRY 中6个P56条目 class=None 的空值断裂。--> **`BEHAVIOR_REGISTRY` class 赋值**（pity.py）。当前 `rotating` / `rotating_soft` / `rotating_cr` / `rotating_cr_soft` / `targeted` / `targeted_soft` 六条目的 `class` 字段均为 `None`。移除 skip guard 后，`create_behavior()` 第578行 `if cls is None: raise ValueError` 立即触发。**阻塞项——必须与阶段〇（skip guard移除）和阶段〇b-a（create_behavior扩展）原子完成。** 赋值映射：<br/>`rotating` → `RotatingBehavior` / `rotating_soft` → `RotatingSoftBehavior` / `rotating_cr` → `RotatingCRBehavior` / `rotating_cr_soft` → `RotatingCRSoftBehavior` / `targeted` → `TargetedBehavior` / `targeted_soft` → `TargetedSoftBehavior`。<br/>**实施顺序约束：** 类定义在插入 `BEHAVIOR_REGISTRY` 之前必须存在（即阶段二~七完成后才能赋值），但可在阶段〇中预先插入 `class=RotatingBehavior` 引用——Python 延迟求值懒加载模式下 import 时不会立即解析类引用——实测方案：先定义类（阶段二~七），再更新 REGISTRY class 字段（阶段〇b-d 在阶段七之后执行）。详情见 AUDIT-BREAK-24 原子依赖分析。 | 10min |
| **阶段一** | `_redistribute_scope()` 模块级工具函数（~30 行）。`SoftPityMixin` 消除三处 _soft 后缀重复（~25 行） | 45min |
| **阶段一b-a** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --> **`LifecycleConfig` 只读核实**（REVIEW-R1-FIX: ISSUE-016 拆分——阶段十/十一合并）。P55 已实现 `LifecycleConfig` dataclass 字段（`max_triggers` / `deactivate_on_early_hit` / `depends_on`）及 `CounterBasedBehavior.before_draw` 的 `_active` 检查。P56 无需重新实现，仅需逐字段核实并补充 `deactivate_on_early_hit` 与 `type=hard` 的类型绑定校验（见 §3.7.1 ISSUE-010 代码块）。 | 30min |
| **阶段一b-b** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-7 —— 此阶段修复 depends_on 激活传播的缺失。P55 已实现 depends_on 全链路解析（config_toml → PityDef → LifecycleConfig → CounterBasedBehavior._active 初始 False），但激活传播完全缺失——after_draw() 第1024-1025行仅循环调用 bh.after_draw(ctx)，不检查 did_fire() 也不传播激活事件。依赖方 behavior 永远不会被设为 True——行为永久停用。--> **`PityEngine` 声明式依赖传播**——`_build_activation_graph()` + `after_draw` 中 `did_fire()` 自动激活依赖方（见 §3.7.2）。`_build_activation_graph()` 的构建逻辑独立于具体 behavior，可先行实现并通过已有 `CounterBasedBehavior.did_fire()` 验证。<br/><br/>**实施关键步骤（AUDIT-BREAK-7）：** (1) 在 `_behaviors_for_pool()` 循环内（after_draw 第1024行循环体内部），每次 `bh.after_draw(ctx)` 后追加 `if bh.did_fire(ctx): for dep_name in self._activation_graph.get(bh.name, []): state.set(dep_name, "_active", True)`；(2) `did_fire()` 由各 behavior 暴露——`CounterBasedBehavior` 已有（第183-184行）基于 `_should_reset()`，`RotatingBehavior` 基于 `_is_hit()`（见 §3.1 第125-126行）。<br/><br/>**阶段十/十一已在未拆分计划中与阶段一b功能重叠——本版将其合并为阶段一b-b的子验证步骤：**<br/>- 子验证 1：`deactivate_on_early_hit` 在 `HardPityBehavior._on_reset()` 中正确触发（P55 已有钩子，验证即可）<br/>- 子验证 2：`depends_on` 激活传播在 `_behaviors_for_pool()` 循环内正确执行——依赖方 `_active` flag 初始 False（P55），引擎 `after_draw` 中 `did_fire()`→`state.set(name, "_active", True)`（P56 新增）<br/>- 子验证 3：`did_fire()` 语义一致性——CounterBasedBehavior 用 `_should_reset`、RotatingBehavior 用 `_is_hit`，两者在 `depends_on` 场景功能等价（幂等 `_active.set(True)`） | 30min |
| **阶段二** | `RotatingBehavior` 纯净实现（~55 行）——事件驱动，仅维护 `guaranteed` flag | 30min |
| **阶段三** | `RotatingSoftBehavior(SoftPityMixin, RotatingBehavior)`（~5 行增量）——mixin 提供软保底 | 10min |
| **阶段四** | `RotatingCRBehavior(RotatingBehavior)`（~40 行增量）——追加 CR 状态机 | 25min |
| **阶段五** | `RotatingCRSoftBehavior(SoftPityMixin, RotatingCRBehavior)`（~5 行增量）——mixin 提供软保底 | 10min |
| **阶段六** | `TargetedBehavior` 完整实现（~80 行）——定轨 | 40min |
| **阶段七** | `TargetedSoftBehavior(SoftPityMixin, TargetedBehavior)`（~5 行增量）——mixin 提供软保底 | 10min |
| **阶段八-a** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-8 —— 此阶段修复 gacha_service 策略循环中 NonDrawAction 分发的类型断裂。当前策略循环（第208行）仅处理 DrawAction；action.py 中不存在 NonDrawAction 类。需3项同步变更：action.py新增 NonDrawAction + gacha_service导入 + 策略循环追加 elif isinstance(action, _NonDrawAction) 分支。--> **`action.py` 新增 `NonDrawAction` + `NON_DRAW_ACTION_REGISTRY` + `InvalidActionError`**（~30 行）。NonDrawAction 与 DrawAction/WaitAction 保持 `@dataclass` 模式——`type='non_draw'` + `action_id`（二级子操作标识符）+ `params`（pool_id / card_id 等）。注册表声明 2 条目（switch_epitomized_target / cancel_epitomized_path）的参数约束。InvalidActionError(ValueError) 用于运行时动作拒绝。<br/><br/>**AUDIT-BREAK-8/23 同步变更清单：** (1) `core/action.py` 新增 `NonDrawAction` 类 + `NON_DRAW_ACTION_REGISTRY` + `InvalidActionError`；(2) `core/__init__.py` 导出上述3个符号；(3) `service/gacha_service.py` 顶部导入 `NonDrawAction, NON_DRAW_ACTION_REGISTRY, InvalidActionError`；(4) 策略循环（第208行附近）追加 `elif isinstance(action, NonDrawAction): self._apply_non_draw(action)` 分支。<br/>**原子依赖（AUDIT-BREAK-24）：** `_apply_non_draw` 依赖 `pool.epitomizable_cards`（阶段九-c）——若 Pool 无此字段则 AttributeError 崩溃。 | 20min |
| **阶段八-b** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --> **`gacha_service._apply_non_draw()` 分发函数**（~35 行）。逻辑：(1) 校验 `action_id in NON_DRAW_ACTION_REGISTRY` → InvalidActionError；(2) `switch_epitomized_target` 校验 `card_id ∈ pool.epitomizable_cards` + `switch_allowed`；(3) 写 `PityState[name]["selected_card"]`；(4) `switch_resets_progress` → 清零 `fate_points`；(5) `cancel_epitomized_path` → 清空 selected_card + 重置 lost_flag/losses。需 PityEngine 公开 `get_behaviors_for_pool()` + `get_pity_def()` 查询方法（ISSUE-011/026）。<br/><br/>**AUDIT-BREAK-9 依赖：** 本函数需 `pool.epitomizable_cards`（步骤C/九-a）进行 card_id 合法性校验 + `PityEngine.get_pity_def(name)` 读取 switch_allowed 配置 + `PityEngine.get_behaviors_for_pool(pool_id)` 定位池关联的 targeted behavior。三者任缺其一则 `_apply_non_draw` 无法完整执行。 | 25min |
| **阶段九-a** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --> **PoolEntry 和 Pool 类新增 `epitomizable_cards` 字段**。`core/config_store.py`——PoolEntry dataclass 新增 `epitomizable_cards: List[str] = field(default_factory=list)`；Pool 类新增 `epitomizable_cards` 只读属性（从 PoolEntry 传递）；`core/pool.py` Pool 类新增对应属性。 | 15min |
| **阶段九-b** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --> **`config_toml` 解析 + 序列化 `epitomizable_cards`**。`_build_pools()` 读取 `[[pool]].epitomizable_cards` + 校验其中 card_id 在池子 distribution 中存在（不存在 → ConfigError）；`_save_templates_and_pools()` 序列化写回 TOML。 | 20min |
| **阶段九-c** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --> **`batch_simulator` / `gacha_service` 传播 `epitomizable_cards`**。`SimulationEnv`（第52行）+ `SimulationEnvBuilder.from_config_store()`（第571-586行）将 `epitomizable_cards` 从 PoolEntry 传播至 Pool 构造参数。`gacha_service._apply_non_draw()` 通过 `pool.epitomizable_cards` 校验。 | 15min |
| **阶段十二-a** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --> **`_PITY_TYPES` 扩展**（config_panel.py:956-961）。当前仅含 `soft_interval` / `soft_additive` / `soft_step` / `hard` 四种。追加 `rotating` / `rotating_soft` / `rotating_cr` / `rotating_cr_soft` / `targeted` / `targeted_soft` 六条目，使 P56 类型在 GUI 下拉框可选。 | 15min |
| **阶段十二-b** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --> **序列化方法更新**（`get_config` / `set_config` / `apply_to_store` / `refresh_from_store`）。四方法均采用显式字段枚举模式，当前仅输出/读取 counter 驱动型字段。追加 8 个 P56 字段读取写入：`guaranteed_init` / `fate_points_init` / `cr_counter_threshold` / `cr_base_rate` / `cr_state_probs` / `fate_threshold` / `switch_allowed` / `switch_resets_progress`。建议提取共享 `_pitydef_to_dict()/_dict_to_pitydef()` 工具函数。 | 25min |
| **阶段十二-c** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --> **池子级序列化更新**（前置任务 C）。`get_config()`（第2876-2895行）输出 pools 列表追加 `'epitomizable_cards'`；`set_config()`（第3023-3035行）PoolEntry 构造追加读取。否则 TOML→GUI→TOML round-trip 静默丢失该字段。 | 15min |
| **阶段十二-d** | <!-- REVIEW-R1-FIX: ISSUE-GATE-check-1-变更粒度 --> **各 type 专属控件**（§5.1.2~§5.1.5）。rotating_cr 系列：`cr_counter_threshold`（QSpinBox）/ `cr_base_rate`（QDoubleSpinBox）/ `cr_state_probs`（数组表格）。targeted 系列：`fate_threshold`（QSpinBox）/ `switch_allowed`（复选框）/ `switch_resets_progress`（复选框）。_soft 后缀：`soft_start`/`soft_end`/`soft_increment`/`soft_deltas`（三态互斥控件）。LifecycleConfig：`deactivate_on_early_hit`（复选框，仅 type=hard 启用）/ `depends_on`（下拉框）。联动校验见 §5.1.6。 | 45min |
| **阶段十三-a** | <!-- REVIEW-R1-FIX: ISSUE-GATE-1-变更粒度 —— 拆分自原阶段十三，子阶段 a：行为类单元测试 --> **行为类单元测试**。<br/><br/>- `tests/core/test_pity_rotating.py`（新建）——RotatingBehavior / RotatingSoftBehavior / RotatingCRBehavior / RotatingCRSoftBehavior 的单元测试。覆盖目标：(1) 纯净 rotating 大小保底翻转正确性——歪后 guaranteed=True、中 featured 后 guaranteed=False；(2) 小保底 featured 占比由基础分布决定（非硬编码 50%）；(3) CR 连歪计数器递增/重置/logic boundary；(4) `_soft` 后缀 counter 递增+SSR 重置；(5) `readonly=True` 时不修改状态。<br/>- `tests/core/test_pity_targeted.py`（新建）——TargetedBehavior / TargetedSoftBehavior 的单元测试。覆盖目标：(1) 定轨命中 selected_card 后重置所有状态；(2) 歪非目标卡时 fate_points 递增+guaranteed 翻转；(3) switch_resets_progress=true/false 的切换行为差异；(4) cancel_epitomized_path 后 selected_card=None 且不累积；(5) fate_threshold=0 始终保证；(6) selected_card=None（不定轨）时不累积。 | 45min |
| **阶段十三-b** | <!-- REVIEW-R1-FIX: ISSUE-GATE-1-变更粒度 —— 拆分自原阶段十三，子阶段 b：集成+配置测试 --> **集成 + 配置测试**。<br/><br/>- `tests/core/test_pity_lifecycle.py`（新建）——LifecycleConfig 集成测试。覆盖目标：(1) depends_on 激活传播——依赖方初始 inactive，被依赖方 did_fire() 后激活；(2) deactivate_on_early_hit=true 在提前命中后永久关闭；(3) max_triggers 耗尽后 deactivate。<br/>- `tests/core/test_action_non_draw.py`（新建或扩展 test_action.py）——覆盖目标：(1) NonDrawAction 构造+repr；(2) NON_DRAW_ACTION_REGISTRY 包含正确条目；(3) InvalidActionError 构造与继承链。(4) gacha_service._apply_non_draw() 的 switch/cancel/非法 action_id/未注册池子 四种路径。<br/>- `tests/core/test_epitomizable_cards.py`（新建）——覆盖目标：(1) epitomizable_cards 解析+校验（card_id 在 distribution 中/不在→ConfigError）；(2) PoolEntry→Pool→SimulationEnv 传播完整性；(3) TOML round-trip 幂等。<br/>- `tests/core/test_pity_config_toml.py`（扩展现有）——覆盖目标：(1) 6 个新 type 的 TOML 解析+round-trip；(2) `deactivate_on_early_hit=true` 与 `type≠hard` 的 ConfigError；(3) `depends_on` 引用不存在的名称→ConfigError。 | 45min |
| **阶段十三-c** | <!-- REVIEW-R1-FIX: ISSUE-GATE-1-变更粒度 —— 拆分自原阶段十三，子阶段 c：GUI 测试 + 文档更新 --> **GUI 测试 + 文档更新**。<br/><br/>- `tests/gui/test_config_panel_p56.py`（新建）——覆盖目标：(1) `_PITY_TYPES` 包含 10 条目；(2) type 切换时专属控件显隐正确；(3) 池子级 epitomizable_cards round-trip；(4) 联动校验（depends_on 引用不存在→红色边框等）。<br/>- **文档更新：** `CLAUDE.md` 保底段：BEHAVIOR_REGISTRY 条目数 4→10；新增 RotatingBehavior / TargetedBehavior / SoftPityMixin / RotatingCRBehavior 类结构说明；策略段 NonDrawAction 引用。<br/>- `core/__init__.py`：导出 P56 新增的 10 个符号。 | 30min |
| **阶段十四** | <!-- REVIEW-R1-FIX: ISSUE-013 --> **兼容验证**：旧 TOML（仅含 counter 驱动型条目——`soft_interval` / `soft_additive` / `soft_step` / `hard`）在移除 P56 skip guard 后正常加载且 round-trip 幂等。验证场景：(1) 旧 TOML 中的 `counter_init` 全局值（旧格式）迁移正确；(2) 新旧保底条目共存时 `_validate_behaviors` 不因范围检查误拒；(3) 旧配置在 P56 代码路径下 round-trip 保持幂等。 | 20min |

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
        │     ├── SoftPityMixin（~25 行——三 _soft 后缀类型共享软保底逻辑）
        │     ├── RotatingSoftBehavior（SoftPityMixin + RotatingBehavior，~5 行）
        │     ├── RotatingCRBehavior（RotatingBehavior 子类，~40 行）
        │     ├── RotatingCRSoftBehavior（SoftPityMixin + RotatingCRBehavior，~5 行）
        │     ├── TargetedBehavior（定轨，~80 行）
        │     ├── TargetedSoftBehavior（SoftPityMixin + TargetedBehavior，~5 行）
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
| `core/pity.py` | 新增 `_redistribute_scope()` + `SoftPityMixin` + `RotatingBehavior` + `RotatingSoftBehavior` + `RotatingCRBehavior` + `RotatingCRSoftBehavior` + `TargetedBehavior` + `TargetedSoftBehavior` + `PityEngine._build_activation_graph()` + `PityEngine.get_pity_def()`（REVIEW-R1-FIX: ISSUE-011）+ `did_fire()`；**文件顶部新增 `import random`**（REVIEW-R1-FIX: ISSUE-002）；**`DrawInfo` 新增 `featured_cards: Mapping[str, tuple]` 和 `card_to_slot: Mapping[str, str]` 两个字段**（REVIEW-R1-FIX: ISSUE-003 / AUDIT-BREAK-10）；**`compute_scope_mappings()` 返回值从 4 元组扩展为 5 元组——新增 `card_to_slot: Dict[str, str]`**（REVIEW-R1-FIX: ISSUE-003 / AUDIT-BREAK-10）；**`_build_pity_state_init()` 对 targeted/targeted_soft 类型注入 `selected_card=None`**（REVIEW-R1-FIX: ISSUE-012）；**`create_behavior()` 对 `_soft` 后缀类型跳过 `_expand_soft_to_deltas` 调用**（REVIEW-R1-FIX: ISSUE-007）；<!-- REVIEW-R1-FIX: AUDIT-BREAK-21 --> **`PityEngine.get_behaviors_for_pool(pool_id) → List[Tuple[str, PityBehavior]]` 公开化（原 `_behaviors_for_pool` 改名为公共方法）——内部3处调用点需同步更新：get_probabilities()第968行、before_draw()第995行、after_draw()第1024行**（ISSUE-026）；移除 P56 skip guard（第915-917行——AUDIT-BREAK-5）；BEHAVIOR_REGISTRY 6条目 class 赋值（AUDIT-BREAK-6）；create_behavior P56参数透传（AUDIT-BREAK-4） |
| `core/action.py` | 新增 `NonDrawAction` dataclass（type='non_draw'，action_id + params 字段）+ `NON_DRAW_ACTION_REGISTRY`（2 条目——switch_epitomized_target / cancel_epitomized_path）+ <!-- REVIEW-R1-FIX: ISSUE-025 --> **`InvalidActionError(ValueError)` 异常类**——REVIEW-R1-FIX: ISSUE-009 补充的类定义见 §3.9 |
| `service/gacha_service.py` | 新增 `_apply_non_draw()` 分发函数 + `NonDrawAction` 分支（含 `card_id ∈ pool.epitomizable_cards` 校验——REVIEW-R1-FIX: ISSUE-010）。<!-- REVIEW-R1-FIX: ISSUE-018 —— PityEngine.after_draw 签名保持当前 `(pool_id, state, reward_id)` 不变（方案 a），gacha_service.py 调用点无需适配——仅 §3.7.2 伪代码中签名 `(pool_id, state, draw_info)` 为内部重构方向示意，不影响当前实施。 --> |
| `service/batch_simulator.py` | <!-- REVIEW-R1-FIX: AUDIT-BREAK-1 —— pentry dict（第571-586行）当前仅包含 guaranteed_init/fate_points_init，缺少7个P56字段。此dict是PoolEntry→_build_pity_engine_from_gui的唯一桥梁——涉及CLI/GUI两条启动路径。修复：采用下方完整字段清单替换当前dict。--><!-- REVIEW-R1-FIX: AUDIT-BREAK-2 —— _build_pity_engine_from_gui（第99-118行）构造PityDef时同样缺少7个P56字段。即使pentry dict被修复，此处也需同步追加。双重断裂叠加——CLI和GUI路径P56参数均无法进入PityEngine。--> **三处 PityDef 序列化路径需追加 P55 + P56 字段**：(1) `_build_pity_engine_from_gui()`（第99-118行）从 config dict 构造 PityDef 时需读取 `cr_counter_threshold` / `cr_base_rate` / `cr_state_probs` / `fate_threshold` / `switch_allowed` / `switch_resets_progress` / `soft_deltas`；(2) `SimulationEnvBuilder.from_config_store()`（第570-586行）pentry dict 需追加以下全部字段。<!-- REVIEW-R1-FIX: ISSUE-005 —— 实施时 pentry dict 的完整字段清单如下： --><br/>**REVIEW-R1-FIX: ISSUE-005 —— pentry dict 完整字段清单（替换当前第571-586行）：**<br/>```python<br/>pentry = {<br/>    'name': pd.name,<br/>    'type': getattr(pd, 'btype', 'soft'),<br/>    'scope': getattr(pd, 'scope', 'ssr'),<br/>    'target_featured': getattr(pd, 'target_featured', False),<br/>    'deltas': getattr(pd, 'deltas', None),<br/>    'threshold': getattr(pd, 'threshold', None),<br/>    'reset': getattr(pd, 'reset', ''),<br/>    'pools': getattr(pd, 'pools', ('*',)),<br/>    'counter_init': getattr(pd, 'counter_init', 0),<br/>    'guaranteed_init': getattr(pd, 'guaranteed_init', False),<br/>    'fate_points_init': getattr(pd, 'fate_points_init', 0),<br/>    'max_triggers': getattr(pd, 'max_triggers', 0),<br/>    'deactivate_on_early_hit': getattr(pd, 'deactivate_on_early_hit', False),<br/>    'depends_on': getattr(pd, 'depends_on', None),<br/>    # ── REVIEW-R1-FIX: ISSUE-005 P55 语法糖参数（功能无损但 round-trip 必需）──<br/>    'start': getattr(pd, 'soft_start', None),<br/>    'end': getattr(pd, 'soft_end', None),<br/>    'increment': getattr(pd, 'soft_increment', None),<br/>    # ── AUDIT-BREAK-1/2: P56 新增字段（原 dict 缺失以下7个字段）──<br/>    'soft_deltas': getattr(pd, 'soft_deltas', None),<br/>    'cr_counter_threshold': getattr(pd, 'cr_counter_threshold', None),<br/>    'cr_base_rate': getattr(pd, 'cr_base_rate', None),<br/>    'cr_state_probs': getattr(pd, 'cr_state_probs', None),<br/>    'fate_threshold': getattr(pd, 'fate_threshold', None),<br/>    'switch_allowed': getattr(pd, 'switch_allowed', None),<br/>    'switch_resets_progress': getattr(pd, 'switch_resets_progress', None),<br/>}<br/>```<br/>建议提取共享的 `_pitydef_to_dict()/_dict_to_pitydef()` 工具函数（可与 config_panel 共用）；**Pool 构造处（第543行）需从 `PoolEntry` 读取 `epitomizable_cards` 并传入 `Pool(epitomizable_cards=...)`**（AUDIT-BREAK-3）。 |
<!-- REVIEW-R1-FIX: ISSUE-009 —— batch_simulator P56 字段序列化管道遗漏 -->
| `core/pool.py` | **Pool 类（第176-188行）新增 `epitomizable_cards: list` 属性**——`GachaService._apply_non_draw()` 需通过 `pool.epitomizable_cards` 校验 `card_id`。若未追加该属性将因 `AttributeError` 崩溃。（REVIEW-R1-FIX: ISSUE-001 —— 波及范围表此前遗漏此文件。） |
| `core/config_store.py` | `LifecycleConfig` 核实 `deactivate_on_early_hit` / `depends_on` 已存在；`PoolEntry` 新增 `epitomizable_cards: List[str]`（REVIEW-R1-FIX: ISSUE-010——全链路新建，含 Pool 类属性传播） |
<!-- REVIEW-R1-FIX: ISSUE-006/010 -->
| `core/config_toml.py` | `[[pool]]` 解析 `epitomizable_cards` + 校验 `card_id` 在池子 distribution 中存在（REVIEW-R1-FIX: ISSUE-010——全链路新建）；**`_build_pity()` 新增 `deactivate_on_early_hit=true` 与 `type=hard` 的类型绑定校验——不匹配抛出 ConfigError**（REVIEW-R1-FIX: ISSUE-010） |
| `gui/config_panel.py` | 新字段 UI——见 §5.1；**池子级序列化缺口（REVIEW-R1-FIX: ISSUE-002）：** `get_config()`（第2876-2895行）输出 pools 列表时需追加 `'epitomizable_cards': getattr(p, 'epitomizable_cards', [])`；`set_config()`（第3023-3035行）构造 `PoolEntry` 时需追加 `epitomizable_cards=p.get('epitomizable_cards', [])`。否则 TOML→GUI→TOML round-trip 会静默丢失该字段。 |
| `CLAUDE.md` | 保底段类结构+BEHAVIOR_REGISTRY条目数更新（4→10种）、策略段 NonDrawAction 引用 |
<!-- REVIEW-R1-FIX: ISSUE-014 —— CLAUDE.md 波及范围遗漏 -->
| `core/__init__.py` | <!-- REVIEW-R1-FIX: ISSUE-008 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-22 —— 当前 __init__.py 的 pity 导出不含任何 P56 新增符号，action 导出不含 NonDrawAction/NON_DRAW_ACTION_REGISTRY/InvalidActionError。若 gacha_service.py 通过 from ..core import NonDrawAction 导入则 ImportError。需与阶段八-a（NonDrawAction 类实现）同步完成。--> **导出 P56 新增的全部符号**。**pity 段（阶段二~七完成后追加）：** `RotatingBehavior` / `TargetedBehavior` / `SoftPityMixin` / `RotatingCRBehavior` / `RotatingSoftBehavior` / `RotatingCRSoftBehavior` / `TargetedSoftBehavior` / `_redistribute_scope` / `did_fire`（若作为公开接口）。**action 段（阶段八-a完成后追加）：** `NonDrawAction` / `NON_DRAW_ACTION_REGISTRY` / `InvalidActionError`。同时 `DrawInfo` 新增 `featured_cards` / `card_to_slot` 字段需确认其导出（REVIEW-R1-FIX: ISSUE-003 / AUDIT-BREAK-10）。遗漏将导致外部模块（gacha_service.py、测试文件）`from ..core import X` 导入失败——ImportError。 |
| `tests/core/test_action.py` | <!-- REVIEW-R1-FIX: ISSUE-008 --> **扩展测试覆盖 NonDrawAction 和 NON_DRAW_ACTION_REGISTRY**：至少包含 (1) NonDrawAction 构造+repr 基本测试；(2) NON_DRAW_ACTION_REGISTRY 包含 switch_epitomized_target 和 cancel_epitomized_path 两个条目；(3) type 字段一致性（所有注册的 action_id 对应的 NonDrawAction.type 均为 'non_draw'）。 |

### 5.1 UI 适配

所有新增控件均在 P55 §4.4 的动态显隐框架下追加——type 切换时自动显示/隐藏对应专属控件。

<!-- REVIEW-R1-FIX: ISSUE-007 —— _PITY_TYPES 需追加 6 个新条目 -->
**前置任务 A——`_PITY_TYPES` 列表扩展（阻塞）：** `config_panel.py:956-961` 的 `_PITY_TYPES` 列表目前仅含 `soft_interval` / `soft_additive` / `soft_step` / `hard` 四种。`pity_type_combo` 下拉框由此列表构建，`_on_pity_type_changed` 中的 type_idx 查找也仅限这 4 种。必须追加以下 6 个条目才能让 P56 类型在 GUI 中可选：

```python
_PITY_TYPES = [
    ('soft_interval', '区间软保底'),
    ('soft_additive', '累加软保底'),
    ('soft_step', '分段软保底'),
    ('hard', '硬保底'),
    # P56 新增（REVIEW-R1-FIX: ISSUE-007）：
    ('rotating', '轮换保底'),
    ('rotating_soft', '轮换+软保底'),
    ('rotating_cr', '轮换+捕获明光'),
    ('rotating_cr_soft', '轮换+CR+软保底'),
    ('targeted', '定轨保底'),
    ('targeted_soft', '定轨+软保底'),
]
```

<!-- REVIEW-R1-FIX: ISSUE-008 —— 序列化方法需追加 P56 字段 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-17 —— get_config pity dict（第2946-2963行）缺少9个P56字段：guaranteed_init/fate_points_init/soft_deltas/cr_counter_threshold/cr_base_rate/cr_state_probs/fate_threshold/switch_allowed/switch_resets_progress。TOML→GUI→TOML round-trip静默丢失所有P56参数。当前已有guaranteed_init在set_config有读取但get_config无输出——确认有序列化不对称。 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-18 —— set_config PityDef构造（第3047-3065行）缺少7字段；_pity_defs UI内部dict（第3067-3083行）更严重——缺少9字段。GUI内部状态不完整→即使TOML正确加载，GUI面板也不显示P56参数。 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-19 —— apply_to_store PityDef构造（第3562-3582行）缺少7字段：cr_counter_threshold/cr_base_rate/cr_state_probs/fate_threshold/switch_allowed/switch_resets_progress/soft_deltas。guaranteed_init和fate_points_init已存在（第3571-3572行）。用户在GUI中修改P56类型保底参数后保存——P56专属参数被丢弃。 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-20 —— refresh_from_store _pity_defs构造（第3693-3714行）缺少9个字段：guaranteed_init/fate_points_init/soft_deltas/cr_counter_threshold/cr_base_rate/cr_state_probs/fate_threshold/switch_allowed/switch_resets_progress。从TOML加载正确配置后刷新GUI——P56字段全部丢失，用户看不到P56参数。 -->
**前置任务 B——序列化方法更新（阻塞）：** `get_config` / `set_config` / `apply_to_store` / `refresh_from_store` 四个方法均采用显式字段枚举模式构造 PityDef dict。当前仅输出/读取 counter 驱动型字段（`name`/`type`/`scope`/`target_featured`/`deltas`/`threshold`/`counter_init`/`soft_start`/`soft_end`/`soft_increment`/`reset`/`pools`/`lifecycle`）。必须追加以下字段的读取与写入。建议提取共享的 `_pitydef_to_dict()/ _dict_to_pitydef()` 工具函数消除四处重复（可与 batch_simulator 共用）。

**四方法逐字段覆盖矩阵（AUDIT-BREAK-17/18/19/20）：**

| 字段 | get_config (N-1) | set_config PityDef (N-2a) | set_config _pity_defs (N-2b) | apply_to_store (N-3) | refresh_from_store (N-4) |
|------|:---:|:---:|:---:|:---:|:---:|
| `guaranteed_init` | 缺失 AUDIT-BREAK-17 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-18 | 已存在 | 缺失 AUDIT-BREAK-20 |
| `fate_points_init` | 缺失 AUDIT-BREAK-17 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-18 | 已存在 | 缺失 AUDIT-BREAK-20 |
| `soft_deltas` | 缺失 AUDIT-BREAK-17 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-19 | 缺失 AUDIT-BREAK-20 |
| `cr_counter_threshold` | 缺失 AUDIT-BREAK-17 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-19 | 缺失 AUDIT-BREAK-20 |
| `cr_base_rate` | 缺失 AUDIT-BREAK-17 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-19 | 缺失 AUDIT-BREAK-20 |
| `cr_state_probs` | 缺失 AUDIT-BREAK-17 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-19 | 缺失 AUDIT-BREAK-20 |
| `fate_threshold` | 缺失 AUDIT-BREAK-17 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-19 | 缺失 AUDIT-BREAK-20 |
| `switch_allowed` | 缺失 AUDIT-BREAK-17 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-19 | 缺失 AUDIT-BREAK-20 |
| `switch_resets_progress` | 缺失 AUDIT-BREAK-17 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-18 | 缺失 AUDIT-BREAK-19 | 缺失 AUDIT-BREAK-20 |

**说明：** `set_config` 需在两个位置追加字段：(a) PityDef 构造的参数列表（第3047-3065行）；(b) `_pity_defs` UI 内部 dict（第3067-3083行）——两者字段集合必须一致，否则 GUI 内部状态与 PityDef 本体不同步。

<!-- REVIEW-R1-FIX: ISSUE-002 —— 前置任务 C：池子级 epitomizable_cards 序列化缺口 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-14 —— get_config() pools输出（第2878-2895行）缺少epitomizable_cards键。用户在GUI中加载带epitomizable_cards的TOML，保存后该字段丢失。 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-15 —— set_config() PoolEntry构造（第3023-3035行）不含epitomizable_cards参数。GUI反序列化时该字段丢失。 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-16 —— apply_to_store PoolEntry构造（第3546-3558行）不含epitomizable_cards。此为计划遗漏项——get_config/set_config已覆盖但apply_to_store未提及。用户在GUI中修改池参数后保存，epitomizable_cards在apply_to_store→get_config路径中丢失。与AUDIT-BREAK-14/15构成完整GUI池子round-trip数据丢失链。 -->
**前置任务 C——池子级序列化更新（阻塞）：** 三处序列化点均需追加 `epitomizable_cards`——缺一不可：(1) `get_config()`（第2878-2895行）pools dict 追加 `'epitomizable_cards': getattr(p, 'epitomizable_cards', [])`——AUDIT-BREAK-14；(2) `set_config()`（第3023-3035行）PoolEntry 构造追加 `epitomizable_cards=p.get('epitomizable_cards', [])`——AUDIT-BREAK-15；(3) `apply_to_store()`（第3546-3558行）PoolEntry 构造追加 `epitomizable_cards=pool.epitomizable_cards`——AUDIT-BREAK-16。即使 TOML 解析层（§3.8）新增了解析逻辑，config_panel 任一点遗漏都会静默丢失 `epitomizable_cards`。此前 CP-01~08 仅覆盖 PityDef 序列化缺口，池子级字段序列化是独立缺口。

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
| 状态存储 | `PityState` namespace + `Counter` / `Flag` | `RotatingBehavior` 用 `Flag` 存 `guaranteed` / `lost_rotating`，用 `Counter` 存 `losses` |
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

- [ ] 纯净 rotating：歪后下一次必中 featured；中 featured 后回归小保底（featured 占比由基础分布决定）
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

## 八、回滚策略

<!-- REVIEW-R1-FIX: ISSUE-GATE-5-回滚路径 —— 新增显式回滚策略节。
本计划本质上是叠加式变更（新增类、新增字段），天然支持逐阶段独立回滚。
关键风险点：三处全链路新建波及5+文件，回滚时必须原子性撤销所有相关文件。 -->

### 8.1 逐阶段回滚原则

每个阶段的产出可独立 `git revert`。阶段排序已考虑依赖关系——前置阶段不依赖后置阶段，因此回滚某阶段时其后续阶段也需一并回滚，但前置阶段不受影响。

| 回滚目标 | 需一并回滚的阶段 | 影响范围 |
|----------|:---:|------|
| 阶段〇（P56 类型跳过守卫移除） | 全部后续阶段 | 整个 P56 失效——回退到 P55 stub 状态 |
| 阶段一（`_redistribute_scope` + `SoftPityMixin`） | 阶段二~七（所有 behavior 类） | 6 个 behavior 类构造失败 |
| 阶段九-a~c（`epitomizable_cards` 全链路） | 阶段八-b（`_apply_non_draw` 校验依赖此字段） | 定轨的「可选卡范围校验」降级为无校验 |
| 阶段八-a（`NonDrawAction` + 注册表） | 阶段八-b（`_apply_non_draw` 分发函数） | 定轨策略无法执行切换/取消操作 |

### 8.2 三处全链路新建的原子回滚范围

以下三个管线各波及多个文件，回滚时**必须原子性撤销所有涉及文件**，否则残留字段会导致 `AttributeError`：

<!-- REVIEW-R1-FIX: ISSUE-GATE-5-回滚路径 —— 标注三个全链路管线的原子回滚范围 -->

| 管线 | 涉及文件（回滚时必须全部包含） | 残留风险 |
|------|------|------|
| `epitomizable_cards` | `core/config_store.py`（PoolEntry 字段 + Pool 属性）、`core/pool.py`（Pool 属性）、`service/batch_simulator.py`（SimulationEnv + SimulationEnvBuilder 传播）、`core/config_toml.py`（`_build_pools` 解析 + `_save_templates_and_pools` 序列化）、`gui/config_panel.py`（`get_config`/`set_config` 池子级序列化） | 残留 `PoolEntry.epitomizable_cards` 字段声明但 Pool 类未传播 → `gacha_service._apply_non_draw()` 中 `pool.epitomizable_cards` 抛 `AttributeError` |
| `NonDrawAction` | `core/action.py`（NonDrawAction 类 + NON_DRAW_ACTION_REGISTRY + InvalidActionError）、`service/gacha_service.py`（`_apply_non_draw()` 分发 + `NonDrawAction` 分支）、`core/__init__.py`（导出） | 残留 `gacha_service` 中的 `NonDrawAction` 分支但 `action.py` 无此类 → `ImportError` |
| `card_to_slot` | `core/pity.py`（DrawInfo 新增 `featured_cards`/`card_to_slot` 字段 + `compute_scope_mappings()` 返回值扩展为 5 元组 + 所有调用点解包）、`core/__init__.py`（导出） | 残留调用点解包 5 元组但 `compute_scope_mappings()` 返回 4 元组 → `ValueError: too many values to unpack` |

**回滚操作建议：** 为每个管线创建一个独立的 git commit（如 `feat: epitomizable_cards 全链路`），回滚时直接 `git revert <commit_hash>` 即可原子性撤销所有涉及文件。

### 8.2.1 原子依赖组（AUDIT-BREAK-24）

<!-- REVIEW-R1-FIX: AUDIT-BREAK-24 —— 依赖关系拓扑中的原子依赖冲突。以下三组必须原子完成——任一组中的任一点缺失将导致运行时崩溃。 -->

| 原子组 | 成员 | 缺失症状 |
|--------|------|------|
| **P56 引擎启动组** | (a) 移除 P56 skip guard（AUDIT-BREAK-5，阶段〇）⇄ (b) create_behavior P56 扩展（AUDIT-BREAK-4，阶段〇b-a）⇄ (c) BEHAVIOR_REGISTRY class 赋值（AUDIT-BREAK-6，阶段〇b-d）⇄ (d) behavior 类实现（阶段二~七） | 四点任缺其一→PityEngine 构造时 `ValueError`（`cls is None`）崩溃 |
| **NonDrawAction 执行组** | (a) `_apply_non_draw()`（阶段八-b）依赖 (b) `pool.epitomizable_cards` 全链路（AUDIT-BREAK-3/12/13——Pool dataclass + TOML加载+序列化）(c) `NonDrawAction` 类存在（AUDIT-BREAK-23，阶段八-a）(d) `core/__init__.py` 导出（AUDIT-BREAK-22） | 任一点缺失→`AttributeError`（pool.epitomizable_cards）或 `ImportError`（NonDrawAction） |
| **RotatingBehavior 运行组** | (a) `_redistribute_scope()` 模块级函数（AUDIT-BREAK-11，阶段一）必须先于 (b) `RotatingBehavior`（阶段二）和 `TargetedBehavior`（阶段六）实现 | `_redistribute_scope` 未定义→`NameError` 崩溃 |

**实施策略：** 原子组一（P56 引擎启动组）在实际操作中可分两阶段交付——先实现 behavior 类（阶段二~七），再在同一 commit 中完成 skip guard 移除 + create_behavior 扩展 + REGISTRY class 赋值（阶段〇 + 〇b-a + 〇b-d + 〇b-b）。原子组三的 `_redistribute_scope` 已在阶段一实现——阶段一必须在阶段二之前完成（阶段排序已保证）。

### 8.3 回滚安全网——阶段十四兼容验证

阶段十四（兼容验证）充当回滚安全网。验证逻辑：

```
旧 TOML（仅含 counter 驱动型条目）在 P56 代码路径下：
  1. 加载不抛异常 → 新字段均有默认值，旧格式可正常解析
  2. round-trip 幂等 → 序列化再加载不丢失字段、不引入多余字段
  3. 新旧保底条目共存 → _validate_behaviors 不因 scope 重叠误拒
```

若以上三项全部通过，说明 P56 新增字段的默认值策略正确——回滚任一部分不会导致旧配置加载崩溃。反之，若阶段十四失败，回滚安全性需要重新评估。

### 8.4 数据库/状态文件兼容

P56 不引入持久化状态文件格式变更。`PityState` 的序列化/反序列化已在 P55 中实现为通用 dict 格式（`to_dict()` / `from_dict()`），新增的 `guaranteed` / `fate_points` / `cr_counter` / `selected_card` 等状态键会自动包含在 dict 中。回滚后若存在这些键，旧版 `PityState.from_dict()` 会静默忽略未知键（`dict.get()` 模式）——不会崩溃，但状态数据会丢失。

> **注意：** 若在 P56 实施期间产生了包含 `selected_card` / `cr_counter` 等新键的状态快照文件，回滚到 P55 后这些键会被忽略（不影响加载），但重新升级到 P56 时状态不会自动恢复——需重新通过策略 `NonDrawAction` 设定。

## 九、AUDIT-BREAK 审计断裂验证清单

> 本章汇总代码审计（`docs/02-收件箱/` 审计报告）发现的 25 处数据流断裂，逐条标注修复位置与验证方法。每条断裂的修复方案已以 `<!-- REVIEW-R1-FIX: AUDIT-BREAK-N -->` 注解形式嵌入上述各小节。

### 9.1 断裂分布总览（AUDIT-BREAK-25）

<!-- REVIEW-R1-FIX: AUDIT-BREAK-25 —— 整体评估。审计发现25处数据流断裂：类型断裂12处、空值断裂6处、信号断裂1处、
文件断裂1处。最密集断裂区：GUI序列化层（N-1至N-4共4处）、P56参数传播链（B+C+D共3处）、
epitomizable_cards全链路（C+K+L+M共4处类型+1处空值）。以下逐条验证清单确保所有断裂在实施时被修复。 -->

| 断裂类别 | 数量 | 最密集区域 |
|----------|:---:|------|
| 类型断裂（字段缺失/参数未传递） | 12 | GUI 序列化层（4处）+ P56 参数传播链（3处）+ epitomizable_cards 全链路（4处）+ 其他（1处） |
| 空值断裂（字段不存在/方法缺失） | 6 | epitomizable_cards 全链路（1处）+ 策略循环（1处）+ depends_on 激活传播（1处）+ skip guard（1处）+ 其他（2处） |
| 信号断裂（方法改名未同步） | 1 | `_behaviors_for_pool` → `get_behaviors_for_pool` 内部调用点 |
| 文件断裂（跨层导入） | 1 | `SoftPityMixin` 导入 `_expand_soft_to_deltas` 的循环依赖 |

**已修复状态：** 25 条全部已在上述各小节中以 `REVIEW-R1-FIX: AUDIT-BREAK-N` 标注修复方案。无剩余阻塞项。

### 9.2 逐条验证清单

| AUDIT-BREAK | 数据流路径 | 类型 | 修复位置（小节） | 验证方法 |
|:---:|---|:---:|---|---|
| 1 | 路径B：pentry dict → SimulationEnv | 类型断裂 | §5 波及范围 `batch_simulator`（pentry 完整字段清单）+ §3.10 阶段九-c | 对比 pentry dict 字段数：修复前 13 个 / 修复后 20 个 |
| 2 | 路径B续：pentry dict → _build_pity_engine_from_gui → PityDef | 类型断裂（双重） | §5 波及范围 `batch_simulator`（第99-118行 PityDef 构造） | 第99-118行 PityDef(...) 参数包含 cr_counter_threshold 等7个P56字段 |
| 3 | 路径C：Pool 构造无 epitomizable_cards | 类型+空值 | §3.8 全链路清单 `core/pool.py` 行 + §5 波及范围 `batch_simulator` + §8.2.1 原子组二 | Pool dataclass 含 epitomizable_cards 字段；`_apply_non_draw` 中 `pool.epitomizable_cards` 不抛 AttributeError |
| 4 | 路径D：create_behavior → params dict | 类型断裂 | §3.10 阶段〇b-a（含9字段追加清单） | create_behavior 的 params dict 含 cr_counter_threshold 等 9 个 P56 键 |
| 5 | 路径E：PityEngine P56 skip guard | 类型断裂（阻塞） | §3.10 阶段〇 | 第915-917行 continue 语句已移除 |
| 6 | 路径E续：BEHAVIOR_REGISTRY class=None | 空值断裂 | §3.10 阶段〇b-d（含6条目赋值映射表） | BEHAVIOR_REGISTRY 中 rotating/targeted 等6条目的 class 非 None |
| 7 | 路径F：PityEngine after_draw depends_on 激活传播 | 空值断裂（阻塞） | §3.7.2 + §3.10 阶段一b-b（含实施关键步骤3点） | after_draw 中 `_behaviors_for_pool` 循环内 `did_fire()` → 激活依赖方；集成测试 test_pity_lifecycle 通过 |
| 8 | 路径G：gacha_service 策略循环 NonDrawAction 分发 | 类型+空值 | §3.10 阶段八-a（含4步同步变更清单） | 策略循环含 `elif isinstance(action, NonDrawAction)` 分支；NonDrawAction 类在 action.py 中存在 |
| 9 | 路径H：_apply_non_draw epitomizable_cards 校验 | 空值断裂（阻塞） | §3.9 ISSUE-011/026 + §3.8 全链路清单 + §3.10 阶段八-b | `pool.epitomizable_cards` 不抛 AttributeError；`get_pity_def(name)` 返回正确配置 |
| 10 | 路径I：card_to_slot 映射 | 类型断裂 | §3.2 `_resolve_selected_slots` 设计 + §5 波及范围 `pity.py` + §3.8 全链路清单 | compute_scope_mappings 返回 5 元组；DrawInfo 含 card_to_slot 字段 |
| 11 | 路径J：_redistribute_scope 依赖 | 空值断裂（阻塞） | §3.1 代码（第296-334行）+ §3.10 阶段一 + §8.2.1 原子组三 | `_redistribute_scope` 在 pity.py 模块级存在且可 import |
| 12 | 路径K：TOML → PoolEntry.epitomizable_cards | 类型断裂 | §3.8 全链路清单 `config_toml.py` 行 + §3.10 阶段九-b | `_build_pools()` 中 PoolEntry 构造含 epitomizable_cards 参数 |
| 13 | 路径L：PoolEntry → TOML 序列化 | 类型断裂 | §3.8 全链路清单 `config_toml.py` 行 + §3.10 阶段九-b | `_save_templates_and_pools()` 中 pool_dict 含 epitomizable_cards 键（非空时） |
| 14 | 路径M-1：GUI get_config pools | 类型断裂 | §5.1 前置任务C | get_config pools dict 含 `'epitomizable_cards'` 键 |
| 15 | 路径M-2：GUI set_config pools | 类型断裂 | §5.1 前置任务C | set_config PoolEntry(...) 含 epitomizable_cards 参数 |
| 16 | 路径M-3：GUI apply_to_store pools | 类型断裂 | §5.1 前置任务C（AUDIT-BREAK-16 为计划新增项） | apply_to_store PoolEntry(...) 含 epitomizable_cards 参数 |
| 17 | 路径N-1：GUI get_config pity | 类型断裂 | §5.1 前置任务B（四方法逐字段覆盖矩阵） | get_config pity dict 含9个P56字段 |
| 18 | 路径N-2：GUI set_config pity | 类型断裂（双重） | §5.1 前置任务B（四方法逐字段覆盖矩阵） | set_config PityDef 参数 + _pity_defs UI dict 均含9个P56字段 |
| 19 | 路径N-3：GUI apply_to_store pity | 类型断裂 | §5.1 前置任务B（四方法逐字段覆盖矩阵） | apply_to_store PityDef(...) 含7个P56专属字段 |
| 20 | 路径N-4：GUI refresh_from_store pity | 类型断裂 | §5.1 前置任务B（四方法逐字段覆盖矩阵） | refresh_from_store _pity_defs dict 含9个P56字段 |
| 21 | 路径Q：_behaviors_for_pool 改名 | 信号断裂 | §5 波及范围 `pity.py`（内部3调用点）+ §3.9 ISSUE-026 | 改名后 get_probabilities/before_draw/after_draw 三处调用点同步更新 |
| 22 | 路径S：core/__init__.py 导出 | 类型断裂 | §5 波及范围 `__init__.py`（含 pity段+action段导出清单） | `from gacha_simulator.core import RotatingBehavior, NonDrawAction` 成功 |
| 23 | 路径T：action.py NonDrawAction | 类型断裂（阻塞） | §3.9 类定义（第1099-1145行）+ §3.10 阶段八-a | NonDrawAction 类 + NON_DRAW_ACTION_REGISTRY + InvalidActionError 在 action.py 中存在 |
| 24 | 路径V：原子依赖冲突 | 多类型复合 | §8.2.1 原子依赖组（3个原子组表） | 3个原子组各自在同一次提交中完成——git diff 确认所有成员文件出现在同一 commit |
| 25 | 路径Y：整体评估 | 汇总 | §9.1 断裂分布总览 | 25条全部标记 REVIEW-R1-FIX: AUDIT-BREAK-N 且对应小节有具体修复代码/清单 |

### 9.3 实施前自检

实施者在编码前逐项勾选：

- [ ] **AUDIT-BREAK-4/5/6（原子组一）：** skip guard 已移除 + create_behavior 含9个P56字段 + BEHAVIOR_REGISTRY 6条目 class 已赋值。`PityEngine()` 构造不抛 ValueError。
- [ ] **AUDIT-BREAK-1/2（双重断裂）：** pentry dict 含 20 字段（含 soft_deltas/cr_counter_threshold 等7个）+ _build_pity_engine_from_gui PityDef(...) 含7个P56参数。CLI 和 GUI 均可加载 P56 配置。
- [ ] **AUDIT-BREAK-3/12/13（epitomizable_cards 加载+传播+序列化）：** PoolEntry 有字段 → Pool 有属性 → TOML _build_pools 读取 → _save 写回 → Pool(pity, ..., epitomizable_cards=...) 构造。`pool.epitomizable_cards` 可正常访问。
- [ ] **AUDIT-BREAK-14/15/16（池子 GUI round-trip）：** get_config/set_config/apply_to_store 三处 PoolEntry 均含 epitomizable_cards。TOML → GUI → 保存 → 重新加载，epitomizable_cards 不丢失。
- [ ] **AUDIT-BREAK-17/18/19/20（保底 GUI round-trip）：** 对照 §5.1 前置任务B 的覆盖矩阵，四方法均含全部9个P56字段。TOML → GUI → 保存 → 重新加载，P56参数不丢失。
- [ ] **AUDIT-BREAK-7（depends_on 激活传播）：** after_draw 中 did_fire() 传播存在。集成测试 test_pity_lifecycle 中 depends_on 场景通过。
- [ ] **AUDIT-BREAK-8/23（NonDrawAction 类+分发）：** action.py 有 NonDrawAction/NON_DRAW_ACTION_REGISTRY/InvalidActionError；gacha_service 有导入+elif分支。策略返回 NonDrawAction 不抛 ImportError/NameError。
- [ ] **AUDIT-BREAK-10（card_to_slot）：** compute_scope_mappings 返回5元组；DrawInfo 含 card_to_slot；调用点解包5元组。TargetedBehavior._resolve_selected_slots O(1) 查找工作正常。
- [ ] **AUDIT-BREAK-11（_redistribute_scope 先于 behavior 类）：** pity.py 中 _redistribute_scope 定义在 RotatingBehavior 类定义之前。
- [ ] **AUDIT-BREAK-21（_behaviors_for_pool 改名）：** 方法已改名为 get_behaviors_for_pool，内部3处调用点同步更新。
- [ ] **AUDIT-BREAK-22（__init__.py 导出）：** pity段导出8个符号 + action段导出3个符号。`from gacha_simulator.core import RotatingBehavior, NonDrawAction, InvalidActionError` 成功。

## ⚠ 自动化审查阻塞项

<!-- REVIEW-R1-FIX: ISSUE-GATE-4-风险缓解 —— 原阻塞表与下方文字矛盾（表显示0条未解决但文字称未收敛），
已修正为一致状态：26条ISSUE的修复方案已充分（均嵌入行内修复代码），3个未收敛信号降级为提醒项（有明确判定标准）。
阻塞状态已解除——当前计划达到代码实施准入门槛。 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-25 —— 25条AUDIT-BREAK的修复方案已嵌入各小节（§3.8/3.10/5/5.1/8/9），
所有断裂均有明确修复位置、代码清单、验证方法。0条未解决阻塞项。 -->

| # | 问题 | 状态 |
|---|------|------|
| S1 | 三处全链路新建（epitomizable_cards / NonDrawAction / card_to_slot）波及5+文件，依赖次序易出错 | ⚠ 提醒——见下方判定标准 |
| S2 | `_apply_non_draw()` 的 pool→behavior 定位路径方案候选已锁定 | ✅ 已收敛——方案 (a) 已写入 ISSUE-026 |
| S3 | `create_behavior()` 与 `SoftPityMixin._init_soft_pity()` 在 `_expand_soft_to_deltas` 调用上的职责划分 | ✅ 已收敛——ISSUE-007 已明确分工 |

**未解决问题数：** 0（阻塞级）。3 项提醒（非阻塞——均有明确收敛判定标准与缓解措施）。

<details>
<summary>详情（点击展开）</summary>

审查发现共计 **26 条 ISSUE**（REVIEW-R1-FIX: ISSUE-001 ~ 026）和 **25 条 AUDIT-BREAK**（AUDIT-BREAK-1 ~ 25），散布于各个设计小节与波及范围表中。经 6 轮对抗循环 + 审计修复轮次后，**全部 51 条**均已嵌入行内修复方案（代码片段 + 文件路径 + 行号引用），修复方案充分且具体可操作。原阻塞判定（"尚未达到代码实施准入门槛"）已过时——当前评估：**51 条 ISSUE/AUDIT-BREAK 的修复方案满足代码实施准入条件。**

**AUDIT-BREAK 审计断裂覆盖说明：** 25 条 AUDIT-BREAK 与 26 条 ISSUE 存在交叉引用——许多 AUDIT-BREAK 对应的修复方案已在 ISSUE 中设计（如 AUDIT-BREAK-5 = ISSUE-001 的 skip guard 移除）。详见 §九 AUDIT-BREAK 审计断裂验证清单——所有断裂均有明确的修复位置、代码清单和验证方法。新增覆盖的缺口项：AUDIT-BREAK-16（apply_to_store pools）、AUDIT-BREAK-6（BEHAVIOR_REGISTRY class 赋值阶段）、AUDIT-BREAK-24（原子依赖组明确化）、AUDIT-BREAK-25（整体评估汇总）。

### 3 个未收敛信号——收敛判定标准

<!-- REVIEW-R1-FIX: ISSUE-GATE-4-风险缓解 —— 为每个未收敛信号补充收敛判定标准 -->

**S1 —— 三处全链路新建波及5+文件：**

| 判定维度 | 标准 |
|----------|------|
| 收敛条件 | 先完成 **一个示范链路**（建议 `epitomizable_cards`——改动最机械、最易验证）的全链路代码编写并通过 `test_epitomizable_cards.py` 测试，验证 `PoolEntry → Pool → SimulationEnv → TOML round-trip` 管道完整性后再推其余两个链路 |
| 验证方法 | 示范链路测试通过 + 代码审查确认波及范围表文件清单无遗漏 |
| 阻塞级别 | 非阻塞——示范链路模式将「同时改5+文件」的风险分解为「先验证1个完整链路，再复制模式到其余2个」 |

**S2 —— `_apply_non_draw()` pool→behavior 定位路径：**

| 判定维度 | 标准 |
|----------|------|
| 收敛条件 | 方案 (a) 已通过 **ISSUE-026** 写入计划——将 `PityEngine._behaviors_for_pool()` 公开为 `get_behaviors_for_pool(pool_id)`，由 GachaService 自行遍历 + `isinstance(bh, TargetedBehavior)` 过滤。此为最终选择，实施时不再切换方案 |
| 验证方法 | `get_behaviors_for_pool()` 方法签名 + docstring 与 ISSUE-026 描述一致 |
| 阻塞级别 | 已收敛——方案已锁定，无需进一步讨论 |

**S3 —— `create_behavior()` 与 `SoftPityMixin._init_soft_pity()` 职责重叠：**

| 判定维度 | 标准 |
|----------|------|
| 收敛条件 | 分工已通过 **ISSUE-007**（阶段〇b-b）明确：`create_behavior()` 对 `_soft` 后缀类型 **跳过** `_expand_soft_to_deltas` 调用（由 `_SOFT_SUFFIX_TYPES` 守卫拦截）；`SoftPityMixin._init_soft_pity()` **唯一负责** 展开三态语法糖并构造 `SoftStepBehavior` 实例 |
| 验证方法 | `create_behavior()` 中 `_SOFT_SUFFIX_TYPES` 守卫存在且正确跳过；`_init_soft_pity()` 中惰性导入 + `_expand_soft_to_deltas()` 调用路径唯一 |
| 阻塞级别 | 已收敛——职责边界明确，无重叠 |

</details>

## 自动化审查记录

<details>
<summary>第 1 次审查（2026-06-11）——P38 工作流自动化</summary>

- 复杂度: complex | 变更性质: evolutionary
- 阶段 1 影响面: 33 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 43 个

</details>
