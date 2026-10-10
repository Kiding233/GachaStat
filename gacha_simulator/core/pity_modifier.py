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

__all__ = ['Modifier', 'HardModifier', 'SoftModifier']


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
        for k in self._higher_rarity_keys(ctx):
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

    def _higher_rarity_keys(self, ctx: PityContext) -> tuple:
        """`_lower_rarities` 的对偶——`rank < rank(scope)` 的稀有度下的全部卡，投影后返回。"""
        scope_rank = ctx.draw.rarity_rank.get(self._scope, 99)
        out = []
        for rarity, rank in ctx.draw.rarity_rank.items():
            if rank < scope_rank:
                out.extend(ctx.draw.scope_cards.get(rarity, ()))
        return _to_dist_keys(ctx, out)


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
