"""P64 实现层——Modifier 家族（§3.1.2 机制表 / §3.9.2 接口）。

Modifier 是 **pure 函数**：`(State, BaseDistribution) -> Distribution`。**一机制一类**
（「六个类、七个机制形态」，`HardModifier` 按 `target` 分两行，§3.1.2 机制表），
每类只写一个方法，**触发条件与 A/Q 一律内联在方法体内**（§3.1.2「条件内联」裁决）
——不写外置条件类族（S12 已取消）、不写目标解析器族（原 S2b 已并入本族）。

**两期分工（§3.9.2 / §3.14.3）**：M1（S2 起至 S7）方法名为
`apply(ctx, view, dist, readonly) -> 分布`，各 Modifier 自实现；S8 起改实现
`compute_delta(view, dist, ctx) -> 增量向量`，`apply` 收敛为基类的唯一默认实现
（本步的基类 `apply` 按 AUDIT-BREAK-3 取 **M1 期占位形态**：`raise NotImplementedError`
——正式默认实现体依赖 S8-1 的 `_apply_delta` 与 S8 起才存在的 `compute_delta`，
照抄即 `NameError`，且 M1 期无任何消费者）。

**分布空间（§3.9 过渡期纪律）**：M1 期 `dist` 是**槽位级**（旧管线
`aggregate_probs_by_rarity` 的产物），Modifier 内部沿用**槽位法**、与旧类位级一致
（§六 S1–S5 口径）；§3.1.2 的 A/Q 两列是**卡集合**，故经 `card_to_slot` 投影到
分布键空间后使用。S8 的卡级管道（D20）把本族改写为增量法，该投影随之消失。

**依赖方向（§3.1.6，强制）**：本模块**单向**依赖 `pity_primitives`，
**不 import `pity.py`**——`pity.py` 反向依赖本模块（preset 工厂、`Pity` 骨架），
双向模块级 import 会构成循环导入。
"""

from typing import Dict, Optional

from .pity_primitives import PityContext, PityState

__all__ = [
    'Modifier', 'HardModifier', 'SoftModifier',
    'RotatingModifier', 'NonFeaturedModifier', 'SelectedModifier', 'NotOwnedModifier',
]


# ══════════════════════════════════════════════════════════════════
# A/Q 的内联解析面（原 S2b 的解析器族已并入本族，§七 S2a）
# ══════════════════════════════════════════════════════════════════

def _lower_rarities(ctx: PityContext, scope: str) -> tuple:
    """§3.1.2 的「更低稀有度」——`rarity_rank` 中 `rank > rank(scope)` 的稀有度下的**全部卡**。

    `HardModifier` / `SoftModifier` / `NotOwnedModifier`（S2a-2）共用本助手，
    **定义只此一处**（§七 S2a-1）。住本模块而不下沉叶子层：只本族消费。

    `scope` 缺键时取 `rarity_rank.get(scope, 99)`（对齐旧实现
    `ctx.draw.rarity_rank.get(self._scope, 99)` 的兜底）——此时无 rank 更大的稀有度，
    返回空元组。卡集合一律经 `scope_cards.get(rarity, ())` 取、**禁止下标**：
    未在池中出现的稀有度没有键（§3.9.5 的「scope 键缺失」行）。
    """
    scope_rank = ctx.draw.rarity_rank.get(scope, 99)
    out = []
    for rarity, rank in ctx.draw.rarity_rank.items():
        if rank > scope_rank:
            out.extend(ctx.draw.scope_cards.get(rarity, ()))
    return tuple(out)


def _higher_rarity_keys(ctx: PityContext, scope: str) -> tuple:
    """`_lower_rarities` 的**对偶**——`rank < rank(scope)` 的稀有度下的全部卡，投影后返回。

    M1 期「更高稀有度**豁免**」（原值保留）的实现面：`HardModifier`（S2a-1）与
    `NotOwnedModifier`（S2a-2）共用，**定义只此一处**（与 `_lower_rarities` 同址、同理由）。
    S2a-1 曾把它写成 `HardModifier` 的私有方法；S2a-2 交付第二个消费方时下沉到模块级
    （`NotOwnedModifier` 的 M1 形态同为「绝对赋值 + 更高稀有度豁免」，见 §3.1.2 边界二），
    `HardModifier` 的调用点与行为不变。

    `scope` 缺键时取 `rarity_rank.get(scope, 99)`（对齐旧实现的兜底）——此时无 rank
    更小的稀有度，返回空元组。卡集合一律经 `scope_cards.get(rarity, ())` 取、**禁止下标**。
    """
    scope_rank = ctx.draw.rarity_rank.get(scope, 99)
    out = []
    for rarity, rank in ctx.draw.rarity_rank.items():
        if rank < scope_rank:
            out.extend(ctx.draw.scope_cards.get(rarity, ()))
    return _to_dist_keys(ctx, out)


def _to_dist_keys(ctx: PityContext, cards) -> tuple:
    """把卡集合投影到**分布键空间**（保序去重）——A/Q 两列与 `dist` 对键的唯一通道。

    M1 期分布是槽位级（§3.9 过渡期纪律「Modifier 内部沿用槽位法」），故 §3.1.2
    的卡集合须经 `card_to_slot` 映射为槽位名。该映射与旧实现的槽位集合**逐项同源**：
    `compute_scope_mappings` 的 `card_to_slot` 用的就是 `scope_slots` / `featured_slots`
    的同一命名规则（`{rarity}_featured` / `rarity`）。

    卡本身无槽位映射时退回卡 id——使本助手在卡级分布（S8 的 D20 形态）下亦不致
    静默返回空集。
    """
    out = []
    for c in cards:
        key = ctx.draw.card_to_slot.get(c, c)
        if key not in out:
            out.append(key)
    return tuple(out)


# ══════════════════════════════════════════════════════════════════
# 基类（§3.9.2 / §3.14.3）
# ══════════════════════════════════════════════════════════════════

class Modifier:
    """Modifier 协议——`rebind` / `apply` 两个默认实现 + `state_keys()` + `namespace`。

    默认实现即协议对「无状态零件」的定义；子类只覆写自己真正承担的方法。
    """

    #: 命名空间声明面（ISSUE-407）：None = 不做命名空间切换，`Pity` 传默认 view；
    #: `'<ns>'` = 本零件声明独立命名空间，`Pity` 传 `StateView(state, part.namespace)`。
    namespace: Optional[str] = None

    def rebind(self, state: PityState, name: str) -> None:
        """P75 纪律：把本 Modifier 内部的 `Counter` / `Flag` 重绑到 per-call `state`。

        **纯重定向、不复制旧值**；`Pity._rebind_state` 对其**无条件**调用，故方法
        必须存在、不得省略（无状态零件继承本空实现）。当前七个机制均只经 `view`
        读状态，无自持遥控器。
        """
        pass

    def state_keys(self) -> tuple:
        """声明键集（ISSUE-501）——本 Modifier 读或写的 `PityState` 键名。

        只读常量、由构造形参决定、不依赖 state。基类默认 `()`（不碰状态的 Modifier
        不覆写）；**读状态的 Modifier 覆写为本类的键集**（§3.9.2）。它是 §3.12.2
        判据第 2 条「Modifier 引用了不存在的状态键」的唯一输入，比对基准为
        `Pity._declared_keys` 的 `trackers` 与 `lifecycle` 并集。条件内联后无需转发。
        """
        return ()

    def apply(self, ctx: PityContext, view, dist: Dict[str, float], readonly: bool):
        """M1 期**占位实现**（AUDIT-BREAK-3，§3.9.2 / §3.14.3 的两期形态）。

        M1（S2 起至 S7）各具体 Modifier 一律自实现
        `apply(ctx, view, dist, readonly) -> 分布`，本占位**无消费者、故无可执行语义**；
        S8-1 把这一处替换为正式默认实现
        `_apply_delta(dist, self.compute_delta(view, dist, ctx) or {})`，此后内层零件
        只写 `compute_delta`。照抄 S8 期的式子即 `NameError`（`_apply_delta` 归 S8-1、
        `compute_delta` 是 S8 起的方法名）。
        """
        raise NotImplementedError(
            f'{type(self).__name__} 未实现 apply：M1 期各 Modifier 自实现 '
            f'apply(ctx, view, dist, readonly)（基类占位实现无消费者，S8-1 才替换）'
        )


# ══════════════════════════════════════════════════════════════════
# 转移量语义族（§3.1.2 机制表第 1/2/3 行）
# ══════════════════════════════════════════════════════════════════

class HardModifier(Modifier):
    """硬保底（F 语义）——`counter >= threshold` 时把源组概率整组搬给目标集。

    §3.1.2 机制表的**两行**由 `target` 承载（`target_featured` 的选择子，取值由
    `_target_of(pdef)` 产出，§3.1.4 ISSUE-403）：

    | `target` | A（加组） | Q（减组） | 转移量 | A 侧形状 |
    |----------|-----------|-----------|--------|---------|
    | `'scope'`（默认） | `scope_cards[scope]` | 更低稀有度 | `p(Q)` | `current` |
    | `'featured'` | `featured_cards[scope]`（**空集回退 scope 全集**） | 更低稀有度 ∪ scope 去掉 A | `p(Q)` | `declared` |

    **转移量口径是「夺取型」`amount = p(Q)`（源组整组搬空）**，不是 soft 的
    `boost/100`——两者在 §3.1.5.2.2 是并列的两种取法，写混即机制错位。

    **M1 形态（§3.9 过渡期纪律 / §3.9.5 的 `Σ(p + δ) ≠ 1` 行）**：M1 **沿用旧实现**
    ——目标集**绝对赋值**（按声明权重分配 100%）、更高稀有度**豁免**（原值保留），
    故存在更高稀有度时输出 `Σ > 1`。S8 的增量法改为「A 加 Q 减」配平
    （`Σδ = 0`，更高稀有度不写增量即精确保留），两者差 1e-4 ~ 3.5e-3
    （§3.1.2 边界二，属 §3.9.5 已登记的差异类）。§六 S1–S5 的「与旧类逐场一致」
    口径以本形态为前提。

    **`readonly` 不参与判定**：新架构下计数由 `CounterTracker.advance` 推进，本类
    只经 `view` 读 `counter`，是 pure 读者（§3.9.6）。
    """

    def __init__(self, scope: str, threshold: int = 90, target: str = 'scope'):
        self._scope = scope
        # 缺省 90：对齐旧 HardPityBehavior 的 threshold 默认值与 ui_params 默认值
        # （§3.2 取值来源表「HardModifier 的阈值 τ」行）
        self._threshold = threshold
        self._target = target

    def state_keys(self) -> tuple:
        return ('counter',)

    def apply(self, ctx: PityContext, view, dist: Dict[str, float], readonly: bool):
        # ── 条件内联：counter >= τ（§3.1.2 机制表第 1 列）──
        if view.get('counter', 0) < self._threshold:
            return None

        # ── A / Q 就地解析（原 S2b 的解析器族已并入本族）──
        A = self._target_keys(ctx)
        if not A:
            return None
        Q = _to_dist_keys(ctx, _lower_rarities(ctx, self._scope))
        if self._target == 'featured':
            # tf=true 的 Q 还含 scope 去掉 A 的剩余（§3.1.2 表第 2 行的「∪」）
            Q = tuple(k for k in _to_dist_keys(
                ctx, ctx.draw.scope_cards.get(self._scope, ())) if k not in A)

        # ── M1 形态：目标集绝对赋值（按声明权重）+ 更高稀有度豁免 ──
        result = {k: 0.0 for k in dist}
        weights = [ctx.draw.base_probabilities.get(k, 0.0) for k in A]
        total_w = sum(weights)
        if total_w > 0:
            for k, w in zip(A, weights):
                result[k] = w / total_w
        else:
            # 兜底：目标集声明权重全为 0 → 均分（对齐旧实现的兜底分支）
            per = 1.0 / len(A)
            for k in A:
                result[k] = per
        # 更高稀有度豁免——原值保留（M1 形态，S8 改为「不写增量」）
        for k in _higher_rarity_keys(ctx, self._scope):
            result[k] = dist.get(k, 0.0)
        # Q 侧整组搬空（夺取型 amount = p(Q)；更高稀有度不在此列，故不与之冲突）
        for k in Q:
            result[k] = 0.0
        return result

    # ── 内部 ──

    def _target_keys(self, ctx: PityContext) -> tuple:
        """A 列：`target='featured'` 取 `featured_cards[scope]`（**空集回退 scope 全集**，
        对齐旧 `featured_slots.get(scope, scope_slots)`），`'scope'` 取 `scope_cards[scope]`。"""
        if self._target == 'featured':
            cards = ctx.draw.featured_cards.get(self._scope) \
                or ctx.draw.scope_cards.get(self._scope, ())
        elif self._target == 'scope':
            cards = ctx.draw.scope_cards.get(self._scope, ())
        else:
            raise ValueError(
                f"未知的 target={self._target!r}（可用：('scope', 'featured')）")
        return _to_dist_keys(ctx, cards)

class SoftModifier(Modifier):
    """软保底（B 语义）——`boost > 0` 时把源组的 `boost` 个百分点搬给 scope。

    | 项 | 取值（§3.1.2 机制表第 3 行） |
    |----|------------------------------|
    | 条件 | `boost > 0`（`boost%` 由 `deltas` 经 `_cumulative_boost` 从 counter 得出） |
    | A | `scope_cards[scope]` |
    | Q | 更低稀有度 |
    | 转移量 | `t = boost%(counter) / 100` |

    **`t` 是百分点绝对量，不得再乘 `p(Q)`**（§3.4.1 修正 ①，2026-10-06 已落地于旧
    `SoftStepBehavior`）：`t = boost/100` 是「目标组概率**增加** boost 个百分点」，
    而 `t = boost/100 * p(Q)` 是「取源组的百分之几」——两者差一个因子 `p(Q) ≈ 1`，
    前期几乎不可见、爬升后段才拉开（第 89 抽 0.966 vs 0.9009）。

    **不消费 `target_featured`**（裁决 7B，2026-10-05）：`soft_*` 配
    `target_featured = true` 由 `create_behavior` 抛 `ConfigError`，故本类构造形参
    只有 `(scope, deltas)`，preset 侧不写 `target=`（§3.2 取值来源表）。

    `deltas` 的展开归 preset 工厂（`_soft_deltas_of(pdef)`，M6 / ISSUE-001）——
    本类只消费已展开的 RLE 段表。
    """

    def __init__(self, scope: str, deltas: tuple):
        self._scope = scope
        self._deltas = tuple(deltas or ())

    def state_keys(self) -> tuple:
        return ('counter',)

    def apply(self, ctx: PityContext, view, dist: Dict[str, float], readonly: bool):
        # ── 条件内联：boost > 0 ──
        boost_pct = self._cumulative_boost(view.get('counter', 0))
        if boost_pct <= 0:
            return None

        A = _to_dist_keys(ctx, ctx.draw.scope_cards.get(self._scope, ()))
        if not A:
            return None
        Q = _to_dist_keys(ctx, _lower_rarities(ctx, self._scope))

        pool = sum(dist.get(k, 0.0) for k in Q)
        if pool <= 0:
            return None
        target_total = sum(dist.get(k, 0.0) for k in A)
        if target_total <= 0:
            # 目标组当前无概率 → u_A 未定义，不转移（§3.9.5 的 p(A) == 0 行）
            return None

        # ── 转移量：t 为百分点绝对量（§3.4.1 修正 ①），封顶 p(Q) 以免 Q 侧产出负概率 ──
        t = min(boost_pct / 100.0, pool)
        result = dist.copy()
        k_t = (target_total + t) / target_total
        k_q = (pool - t) / pool
        for k in A:
            result[k] = dist.get(k, 0.0) * k_t
        for k in Q:
            result[k] = dist.get(k, 0.0) * k_q
        return result

    # ── 内部 ──

    def _cumulative_boost(self, counter: int) -> float:
        """遍历 `deltas` RLE，按 counter 定位当前段并累计 `boost%`（0 ~ 100）。

        逐行同源于旧 `SoftStepBehavior._cumulative_boost`（位级一致的前提）：
        防御性跳过 `n <= 0` 的无效段（防 counter 不减反增、boost 翻倍）；counter
        超出所有段时延续最后一档的增量率；结果封顶 100。
        """
        if counter <= 0:
            return 0.0
        boost = 0.0
        remaining = counter
        for n, inc in self._deltas:
            if n <= 0:
                continue  # 防御：跳过无效段
            if remaining <= n:
                boost += remaining * inc
                return min(boost, 100.0)
            boost += n * inc
            remaining -= n
        # counter 超出所有段 → 最后一档延续
        if self._deltas:
            boost += remaining * self._deltas[-1][1]
        return min(boost, 100.0)

# ══════════════════════════════════════════════════════════════════
# 目标集语义族（§3.1.2 机制表第 4/5/6/7 行）
# ══════════════════════════════════════════════════════════════════

def _scope_keys(ctx: PityContext, scope: str) -> tuple:
    """`scope` 的**槽位键集**（`scope_slots[scope]`）——M1 期 A ∪ Q 的边界。

    与 `_to_dist_keys` 的分工：本助手给的是「scope 的分布键全集」，即旧
    `_redistribute_scope` 的写入面与旧 `_scope_total_prob` 的求和面；A 侧（目标集）
    仍按 §3.1.2 由**卡集合**投影得出（`_to_dist_keys`）。两者在
    `compute_scope_mappings` 的产出上同集合（`(rarity, f'{rarity}_featured')`），
    顺序不同、对「按值写入」的绝对赋值无影响。

    一律 `.get(scope, ())`、**禁止下标**：未在池中出现的稀有度没有键（§3.9.5 的
    scope 键缺失行）。
    """
    return tuple(ctx.draw.scope_slots.get(scope, ()))


def _scope_total(dist: Dict[str, float], scope_keys: tuple) -> float:
    """scope 的总概率——逐行同源于旧 `_scope_total_prob`（`ctx.current` → `dist`）。

    M1 期 `dist` 与 `ctx.current` 同值（§3.9 过渡期纪律：Modifier 自实现 `apply`，
    在管道内的输入即当前分布）。
    """
    return sum(dist.get(k, 0.0) for k in scope_keys)


def _redistribute_in_scope(dist: Dict[str, float], A: tuple, Q: tuple,
                           total: float, weights) -> Dict[str, float]:
    r"""M1 期 `_redistribute_scope` 的**等价复刻**——scope 内按声明权重的绝对赋值。

    `RotatingModifier` / `NonFeaturedModifier` / `SelectedModifier` 三者共用：都是
    「scope 总量 `total` 在 A / Q 之间重分配」的同一算子，差别只在 A/Q 怎么取。
    本模块**不得 import `pity.py`**（§3.1.6 的单向依赖），故就地复刻而非调用旧函数；
    复刻面只有**构造**（A 侧按 `weights` 分配、Q 侧归零），**目标集解析仍在各类方法体内**。

    与旧 `_redistribute_scope(ctx, ratio, total, featured_slots, scope)` 的对应：
    `featured_slots` ↔ A、`scope_slots\featured_slots` ↔ Q；`ratio = 1.0`（A 收下
    全部 `total`）与 `ratio = 0.0`（A 收下全部 `total`、Q 归零）在旧函数里是同一段
    代码的两支，故本助手只表达「A 收下 `total`」这一支。

    `Σw(A) == 0`（池子未声明该组权重）时退化为**均分**——对齐旧实现的兜底分支
    （`elif featured_slots: per_target = featured_total / len(featured_slots)`）。
    """
    result = dist.copy()
    ws = [weights.get(k, 0.0) for k in A]
    sw = sum(ws)
    if sw > 0:
        for k, w in zip(A, ws):
            result[k] = total * w / sw
    else:
        per = total / len(A)
        for k in A:
            result[k] = per
    for k in Q:
        result[k] = 0.0
    return result


class RotatingModifier(Modifier):
    r"""轮换保底（rotating）——`guaranteed` 时把 scope 内**非** featured 的概率整组搬给 featured。

    | 项 | 取值（§3.1.2 机制表第 4 行） |
    |----|------------------------------|
    | 条件 | `guaranteed` ∨（`extra_flag` ∧ `view.get(extra_flag)`） |
    | A（加组） | `featured_cards[scope]` |
    | Q（减组） | `scope\featured` |
    | 转移量 | `p(Q)` |
    | A 侧形状 | `current`（M1 期一律按声明权重，见下） |

    语义即「大小保底」：歪过一次后，出金必是 UP。

    **`extra_flag` 形参（§3.2 的 `rotating_cr` 行，2026-10-06 补）**：`rotating_cr` 与
    `rotating` 的效果完全相同（「出金必是 UP」），差别只在条件多一个 `cr_intercepted`
    （由 `StreakTracker.prepare` 掷骰后写入，裁决 6B′）。这是「条件内联」的代价之一：
    **条件若有变体，用构造形参表达，而不是新写一个类**（§3.2 同条）；该形参**只影响
    条件**，不影响 A/Q/转移量/形状。

    **`readonly` 抑制 `extra_flag`（§3.9.6 的 M1 期专项，强制）**：6B′ 把 CR 掷骰移回
    `before_draw` 的 `prepare` 相位，只读查询会走到 `prepare` 的 `readonly` 早退分支，
    于是 `cr_intercepted` 读到的是**上一次非只读调用**留下的 flag（差一抽）。M1 期由本类
    依 `readonly` 抑制该标志，**复刻旧查询语义**（查询不体现拦截）；M2 期 `readonly` 从
    Modifier 签名废除后，改按 §3.1.2「新机制需要新静态事实时加字段、不改签名」给 `ctx`
    加查询标记字段。`guaranteed` 不受 `readonly` 影响（旧类同样无条件读它）。

    **M1 形态（§3.9 过渡期纪律）**：scope 内**绝对赋值** + scope 外**原值保留**，
    逐行复刻旧 `RotatingBehavior.before_draw` 的 guaranteed 分支
    `_redistribute_scope(ctx, 1.0, total, featured_slots, scope)`。故 scope 总量不变
    （`Σ` 仍为 1），A 侧按**声明权重**分配（`current` 形状是 S8 的目标形态）。
    """

    def __init__(self, scope: str, extra_flag: Optional[str] = None):
        self._scope = scope
        self._extra_flag = extra_flag

    def state_keys(self) -> tuple:
        if self._extra_flag:
            return ('guaranteed', self._extra_flag)
        return ('guaranteed',)

    def apply(self, ctx: PityContext, view, dist: Dict[str, float], readonly: bool):
        # ── 条件内联：guaranteed ∨（extra_flag ∧ ¬readonly）（§3.1.2 / §3.9.6）──
        if not (view.get('guaranteed')
                or (self._extra_flag and not readonly
                    and view.get(self._extra_flag))):
            return None

        # ── A / Q 就地解析（原 S2b 的解析器族已并入本族）──
        A = _to_dist_keys(ctx, ctx.draw.featured_cards.get(self._scope, ()))
        if not A:
            # 空目标集 → 恒等（§3.9.5；旧实现同为空集早退：`if not featured_slots: return copy`）
            return None
        scope_keys = _scope_keys(ctx, self._scope)
        Q = tuple(k for k in scope_keys if k not in A)
        total = _scope_total(dist, scope_keys)
        if total <= 0:
            return None
        return _redistribute_in_scope(dist, A, Q, total, ctx.draw.base_probabilities)


class NonFeaturedModifier(Modifier):
    r"""反向轮换保底（G1，`rotating_inverse`）——`forced_loss` 时把 featured 的概率整组搬给非 featured。

    | 项 | 取值（§3.1.2 机制表第 5 行） |
    |----|------------------------------|
    | 条件 | `forced_loss`（由 `FlagTracker(judge="featured", hit="set", miss="clear")` 写） |
    | A（加组） | `scope\featured` |
    | Q（减组） | `featured_cards[scope]` |
    | 转移量 | `p(Q)` |
    | A 侧形状 | `declared` |

    与 `RotatingModifier` 是**同一算子的反向调用**（§3.3 定稿语：「`NonFeaturedModifier`
    复用 `_redistribute_scope` 反向调用」）：A / Q 互换，其余（scope 总量不变、scope 外
    不动）完全相同。手册场景为幻塔「连中必歪」——出 UP 后下一次 SSR 必非 UP。

    **无 `flag` 形参**：条件内联后触发标志恒为 `forced_loss`（§3.3 末段明写
    「`NonFeaturedModifier` 本身**无 `flag` 形参**」）。`forced_loss` 是 preset 内部标志，
    `PityDef` 无对应初始值字段，初值恒 `False`（§3.3 的 preset 代码注释）。

    **M1 形态（§3.9 过渡期纪律）**：同 `RotatingModifier`——scope 内绝对赋值、scope 外
    原值保留，逐行复刻 `_redistribute_scope(ctx, 0.0, total, featured_slots, scope)`。
    """

    def __init__(self, scope: str):
        self._scope = scope

    def state_keys(self) -> tuple:
        return ('forced_loss',)

    def apply(self, ctx: PityContext, view, dist: Dict[str, float], readonly: bool):
        # ── 条件内联：forced_loss（§3.1.2 机制表第 5 行）──
        if not view.get('forced_loss'):
            return None

        # ── A / Q 就地解析：A = scope\featured，Q = featured（与 rotating 互换）──
        scope_keys = _scope_keys(ctx, self._scope)
        featured = _to_dist_keys(ctx, ctx.draw.featured_cards.get(self._scope, ()))
        A = tuple(k for k in scope_keys if k not in featured)
        if not A:
            return None
        total = _scope_total(dist, scope_keys)
        if total <= 0:
            return None
        return _redistribute_in_scope(dist, A, featured, total,
                                      ctx.draw.base_probabilities)


class SelectedModifier(Modifier):
    r"""定轨保底（targeted）——`guaranteed` 或定轨就绪时把 scope 的概率整组搬给**定轨选中卡**。

    | 项 | 取值（§3.1.2 机制表第 6 行 / §3.9.2 的 `SelectedModifier` 示例） |
    |----|-------------------------------------------------------------|
    | 条件 | `guaranteed` ∨（已定轨 ∧ `fate_points >= tau`） |
    | A（加组） | `(selected,)` |
    | Q（减组） | `scope\selected` |
    | 转移量 | `p(Q)` |
    | A 侧形状 | `declared` |

    **`tau` 是构造形参**（§3.9.2 的 `self._tau`）：机制表的条件列写 `fate_ready`，其定义
    即 `fate_points >= tau`（对齐旧 `TargetedBehavior` 的
    `self._fate_points.value() >= self._fate_threshold`）。缺省 **1**，与旧类的
    `fate_threshold if fate_threshold is not None else 1` 同源；`tau = 0` 即「定轨后必出」
    （G19 尘白禁区不歪池的 `targeted(fate_threshold=0)` 形态）。

    **`selected_card` 经 `view` 读**：它不由 `FateTracker` 声明（写入者是策略层
    `NonDrawAction`，§3.1.1 L4 例外 2），本类仍把它写进 `state_keys()`——**读键就申报**
    是 §3.12.2 判据 2 的唯一输入，该键的白名单由 §3.1.1 同条要求提供（否则合法配置会被
    误判为「引用不存在的键」）。

    **两处 M1 沿用旧实现的形态（逐字对齐旧 `TargetedBehavior.before_draw`，非 §3.9.2
    示例的 S8 形态）**：

    1. **「已定轨」是 fate 分支的合取项**：旧实现的第二析取项是
       `(selected and self._fate_points.value() >= self._fate_threshold)`，`selected`
       为假时整个析取项为假。故 `tau = 0` 且未定轨时**不触发**（若省掉该合取项，
       `fate_points >= 0` 恒真，会把「未定轨」当成「定轨就绪」）。
    2. **未定轨时目标集退化为全部 featured 槽**：旧 `_resolve_selected_slots(None, …)`
       首行即 `if selected is None: return featured_slots`。**这不是死分支**：手册明写
       「不填卡 ID 时可改用 `guaranteed_init = true` 等效」，该组合（`guaranteed_init=True`
       且未配 `selected_card_init`）正是「出金必是 UP、UP 内按声明权重分配」的既定配置
       形态。§3.1.2 机制表的 `A = (selected,)` 描述的是**定轨已设置**的常规分支；旧
       `_resolve_selected_slots` 中「按槽位名反查 featured 槽」的那一段回退则是
       `card_to_slot` 缺失时的历史兜底，新形态以 `card_to_slot` 为唯一投影通道
       （`_to_dist_keys`），不再复刻。

    **M1 形态（§3.9 过渡期纪律）**：同 `RotatingModifier`——scope 内绝对赋值、scope 外
    原值保留，逐行复刻 `_redistribute_scope(ctx, 1.0, total, targeted_slots, scope)`。
    """

    def __init__(self, scope: str, tau: int = 1):
        self._scope = scope
        self._tau = tau

    def state_keys(self) -> tuple:
        return ('guaranteed', 'fate_points', 'selected_card')

    def apply(self, ctx: PityContext, view, dist: Dict[str, float], readonly: bool):
        sel = view.get('selected_card')
        # ── 条件内联：guaranteed ∨（已定轨 ∧ fate_points >= tau）（§3.1.2 第 6 行）──
        if not (view.get('guaranteed')
                or (sel is not None and view.get('fate_points', 0) >= self._tau)):
            return None

        # ── A / Q 就地解析：A = 定轨选中卡（投影到槽位）；未定轨时退化为全部 featured ──
        featured = _to_dist_keys(ctx, ctx.draw.featured_cards.get(self._scope, ()))
        if sel is None:
            selected_keys = ()
        else:
            selected_keys = tuple(k for k in _to_dist_keys(ctx, (sel,))
                                  if k in featured)
        A = selected_keys or featured
        if not A:
            return None
        scope_keys = _scope_keys(ctx, self._scope)
        Q = tuple(k for k in scope_keys if k not in A)
        total = _scope_total(dist, scope_keys)
        if total <= 0:
            return None
        return _redistribute_in_scope(dist, A, Q, total, ctx.draw.base_probabilities)


class NotOwnedModifier(Modifier):
    r"""G3 硬保底·排除已获得（崩坏3 精准补给）——`counter >= tau` 时把「未拥有」的 featured 卡
    之外的概率整组搬给它们。

    | 项 | 取值（§3.1.2 机制表第 7 行 / §3.10.4） |
    |----|--------------------------------------|
    | 条件 | `counter >= tau` |
    | A（加组） | `featured_cards[scope]` 中**未拥有**者（**动态目标**） |
    | Q（减组） | 更低稀有度 ∪ `scope\A` |
    | 转移量 | `p(Q)` |
    | A 侧形状 | `current` |

    **Q 含已拥有的 UP（§3.10.4 的 2026-10-07 用户裁决）**：A = featured 中未拥有者，故
    `scope\A` = (featured 中已拥有者) ∪ `scope\featured`。**已拥有的 UP 落在 Q 内、本抽
    被搬空**，从而「τ 抽必出**未获得的** UP」成立；若按 `scope\featured` 取 Q，已拥有的
    UP 保留原概率、本抽仍可被抽到，与手册「已获得的装备从 UP 组中排除」冲突。

    **`ctx.sim` 是唯一的状态来源（§3.10.2）**：`ctx.sim.owns(card_id)` 返回该卡持有张数
    （`total_holding` 口径、**含初始持有**），0 即未拥有。该节明令**直接读、无 `None`
    兜底**（`sim` 非 Optional、永远填充；ISSUE-013 的兜底要求已随该节改判取消）。
    **时序说明**：`PityContext.sim` 字段由 **S9-2（M2）** 落在 `pity_primitives.py`，
    本类（S2a-2，M1）先交付读取方；M1 期本类**无消费者**（G3 的两个 type 与 preset 工厂
    归 S9-3），其单测自行提供 `sim` 替身（先例：S2a-1 对尚未存在的 `StateView` 用 `_View`
    替身）。

    **「全部已拥有」的退化分支取形态 a**（§3.10.4）：A 为空 → `return None`（该次保底
    不触发、恒等）。形态 b（目标集退化为全部 featured、仍给出一件）由 **S9-3** 以
    `on_all_owned` 构造形参承载（该形参列在 §七 S9-3 的目标文件清单内，本步不提前落）。
    该分支是 §3.10.4 登记的**待确认项**（零直接信源、两形态并列，谁也不是已确认等价），
    本步只交付形态 a 的行为。

    **M1 形态取 hard 家族的绝对赋值**（§3.9 过渡期纪律）：本类注册在 `_HARD_TYPES`
    （§3.10.4 配套第 1 条的四类集合分类），机制语义是「τ 抽**必出**未获得的 UP」，故 A 侧
    取**绝对 1.0**（同 `HardModifier`），Q 整组搬空、更高稀有度豁免。**与其余三类的差别
    有据**：那三类的 `Q ⊆ scope`，A 收下 scope 总量即可守恒；本类的 Q **含更低稀有度**，
    若同样只收 scope 总量则 `Σ` 会塌到 `p(scope)`，故必须收下 `1.0`（等价于
    「scope 总量 + 更低稀有度总量」，即 scope 为最高稀有度时的 `1 - p(更高稀有度)`）。
    **边界**：scope 非最高稀有度时本形态输出 `Σ > 1`（同 §3.1.2 边界二的已登记差异类）；
    真实配置的 G3 scope 为 `ssr`（rank 0），此时 `Σ = 1`。
    """

    def __init__(self, scope: str, threshold: int = 50):
        self._scope = scope
        # 缺省 50：§3.10.4 配套第 1 条的 `tau = pdef.threshold if pdef.threshold is not
        # None else 50`（`hard` 为 90，本机制为 50 抽）
        self._threshold = threshold

    def state_keys(self) -> tuple:
        return ('counter',)

    def apply(self, ctx: PityContext, view, dist: Dict[str, float], readonly: bool):
        # ── 条件内联：counter >= τ（§3.1.2 第 7 行；条件极性见 §3.10.4 的修正段——
        #    必须是「τ 抽触发」而**不是**恒真，恒真即退化为本节开头否定的 pool 层近似）──
        if view.get('counter', 0) < self._threshold:
            return None

        # ── A / Q 就地解析 ──
        featured = ctx.draw.featured_cards.get(self._scope, ())
        A = _to_dist_keys(ctx, tuple(c for c in featured if ctx.sim.owns(c) == 0))
        if not A:
            # 空目标集（含「全部已拥有」形态 a）→ 恒等（§3.9.5 / §3.10.4）
            return None
        scope_keys = _scope_keys(ctx, self._scope)
        Q = []
        for k in scope_keys:
            if k not in A:
                Q.append(k)
        for k in _to_dist_keys(ctx, _lower_rarities(ctx, self._scope)):
            if k not in A and k not in Q:
                Q.append(k)

        # ── M1 形态：目标集绝对赋值（按声明权重）+ 更高稀有度豁免（同 HardModifier）──
        result = {k: 0.0 for k in dist}
        weights = [ctx.draw.base_probabilities.get(k, 0.0) for k in A]
        total_w = sum(weights)
        if total_w > 0:
            for k, w in zip(A, weights):
                result[k] = w / total_w
        else:
            # 兜底：目标集声明权重全为 0 → 均分（对齐旧实现的兜底分支）
            per = 1.0 / len(A)
            for k in A:
                result[k] = per
        for k in _higher_rarity_keys(ctx, self._scope):
            result[k] = dist.get(k, 0.0)
        for k in Q:
            result[k] = 0.0
        return result
