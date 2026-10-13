"""P64 实现层——Modifier 家族（§3.1.2 机制表 / §3.9.2 接口）。

Modifier 是 **pure 函数**：`(State, BaseDistribution) -> Distribution`。**一机制一类**
（「六个类、七个机制形态」，`HardModifier` 按 `target` 分两行，§3.1.2 机制表），
每类只写一个方法，**触发条件与 A/Q 一律内联在方法体内**（§3.1.2「条件内联」裁决）
——不写外置条件类族（S12 已取消）、不写目标解析器族（原 S2b 已并入本族）。

**两期分工（§3.9.2 / §3.14.3）；S8-1 已切到第二期**：M1（S2 起至 S7）方法名为
`apply(ctx, view, dist, readonly) -> 分布`，各 Modifier 自实现；**S8 起**各 Modifier
实现 `compute_delta(view, dist, ctx) -> 增量向量`，`apply` 收敛为基类的唯一默认实现
（`_apply_delta(dist, self.compute_delta(...) or {})`），骨架逐项调用 `compute_delta`。
**`compute_delta` 的三参是定稿**（2026-10-08 用户裁决），`readonly` 随「Modifier 是
pure 函数」从本族签名废除：查询标记改由 `PityContext.readonly` 字段承载（§3.9.6 的
「处置（两期）②」按 §3.1.2 的「加字段、不改签名」落地）。

**分布空间（D20，S8 已切换）**：`dist` 是**卡级**（池内 `{card_id: p}`），A / Q 两列
直接是**卡集合**（§3.1.2 的 A/Q 列即卡集合，S8 前那条 `card_to_slot` 投影通道已随
M1 槽位法一并消失）。**键空间错位不会静默**：`transfer_linear` 对 A / Q 内的卡直接
`dist[c]` 取值，错位即 `KeyError`（若改用 `.get(c, 0.0)` 兜底，全部保底会无声退化为
恒等：正是 §七 S8-1/S8-2/S8-3 原子单元警告所针对的形态）。

**依赖方向（§3.1.6，强制）**：本模块**单向**依赖 `pity_primitives`，
**不 import `pity.py`**——`pity.py` 反向依赖本模块（preset 工厂、`Pity` 骨架），
双向模块级 import 会构成循环导入。`_apply_delta` 与 `transfer_linear` 住叶子层
（§3.1.6），本模块与编排层共用同一对象。
"""

from typing import Dict, Optional

from .pity_primitives import PityContext, PityState, _apply_delta, transfer_linear

__all__ = [
    'Modifier', 'HardModifier', 'SoftModifier',
    'RotatingModifier', 'NonFeaturedModifier', 'SelectedModifier', 'NotOwnedModifier',
]


# ══════════════════════════════════════════════════════════════════
# A/Q 的内联解析面（原 S2b 的解析器族已并入本族，§七 S2a）
# ══════════════════════════════════════════════════════════════════

def _lower_rarities(ctx: PityContext, scope: str) -> tuple:
    """§3.1.2 的「更低稀有度」——`rarity_rank` 中 `rank > rank(scope)` 的稀有度下的**全部卡**。

    `HardModifier` / `SoftModifier` / `NotOwnedModifier` 共用本助手，
    **定义只此一处**（§七 S2a-1）。住本模块而不下沉叶子层：只本族消费。

    `scope` 缺键时取 `rarity_rank.get(scope, 99)`（对齐旧实现
    `ctx.draw.rarity_rank.get(self._scope, 99)` 的兜底）——此时无 rank 更大的稀有度，
    返回空元组。卡集合一律经 `scope_cards.get(rarity, ())` 取、**禁止下标**：
    未在池中出现的稀有度没有键（§3.9.5 的「scope 键缺失」行）。

    **卡级（S8 起）**：返回值即卡 id，直接被 `transfer_linear` 当 Q 使用，
    无需再经投影（M1 的 `_to_dist_keys` 通道已随槽位法删除）。
    """
    scope_rank = ctx.draw.rarity_rank.get(scope, 99)
    out = []
    for rarity, rank in ctx.draw.rarity_rank.items():
        if rank > scope_rank:
            out.extend(ctx.draw.scope_cards.get(rarity, ()))
    return tuple(out)


def _cards(*groups) -> tuple:
    """把若干卡集合串成一个**保序去重**的元组：A / Q 两列的规范化入口。

    去重不是形式主义：一张卡在 Q 内出现两次会让 `transfer_linear` 对它扣两次
    减量（产出负概率），在 A 内出现两次会让它拿到双份增量（`Σδ ≠ 0`）。正常
    配置下 `scope_cards` / `featured_cards` 各自不含重复项，故本助手是**防御**：
    「`scope\\featured`」这类由两列拼出来的集合最容易在构造上重叠。
    """
    seen = []
    for group in groups:
        for c in group:
            if c not in seen:
                seen.append(c)
    return tuple(seen)


# ══════════════════════════════════════════════════════════════════
# 基类（§3.9.2 / §3.14.3）
# ══════════════════════════════════════════════════════════════════

class Modifier:
    """Modifier 协议：`compute_delta` 是本族唯一必写的方法，`apply` / `rebind` 由本基类提供。

    默认实现即协议对「无状态零件」的定义；子类只覆写自己真正承担的方法。
    """

    #: 命名空间声明面（ISSUE-407）：None = 不做命名空间切换，`Pity` 传默认 view；
    #: `'<ns>'` = 本零件声明独立命名空间，`Pity` 传 `StateView(state, part.namespace)`。
    namespace: Optional[str] = None

    def compute_delta(self, view, dist: Dict[str, float],
                      ctx: PityContext) -> Optional[Dict[str, float]]:
        r"""返回增量向量 `{card_id: δ}`；未列出的卡默认 `δ = 0`；`None` 表示恒等。

        **三参数是定稿（2026-10-06 用户裁决），不得再增形参**（§3.1.2）。

        - `view`：状态视图。当前是 `PityState` 的薄包装（可读全部命名空间），
          S9 后收紧为「只含自身命名空间」的 StateView（§3.10.3）。
        - `dist`：当前分布 `{card_id: p}`（卡级，D20）。
        - `ctx` ：本次抽卡的静态事实（`scope_cards` / `featured_cards` /
          `rarity_rank` / `base_probabilities` / `sim`，以及只读查询标记
          `readonly`）。**需要新的事实时加字段，不改签名**。

        本实现**抛 `NotImplementedError`**而不是返回 `None`：§3.9.2 的基类代码块把
        本方法写成只有 docstring 的接口声明（等价于返回 `None`），但「漏写
        `compute_delta` 的子类」在那种形态下会**静默变成恒等零件**（机制不生效、
        不报错），与本计划在别处一律按阻塞级处理的失效模式同类（§六 ISSUE-204 条
        的「配置里写了保底、运行时该保底不存在且无可见报错」）。本族六个机制全部
        覆写本方法，故该选择对生产路径零影响。
        """
        raise NotImplementedError(
            f'{type(self).__name__} 未实现 compute_delta：S8 起各 Modifier 一律实现 '
            f'compute_delta(view, dist, ctx) -> Optional[增量向量]（§3.9.2）'
        )

    def rebind(self, state: PityState, name: str) -> None:
        """P75 纪律：把本 Modifier 内部的 `Counter` / `Flag` 重绑到 per-call `state`。

        **纯重定向、不复制旧值**；`Pity._rebind_state` 对其**无条件**调用，故方法
        必须存在、不得省略（无状态零件继承本空实现）。当前六个机制均只经 `view`
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

    def apply(self, ctx: PityContext, view, dist: Dict[str, float],
              readonly: bool) -> Dict[str, float]:
        r"""**S8 起的正式默认实现**（§3.9.2 / §3.14.3）：把本 Modifier 的增量向量
        作用到分布并归一化：`_apply_delta(dist, self.compute_delta(view, dist, ctx) or {})`。

        **`apply` 自此不是每个 Modifier 的必写方法**：各 Modifier 覆写的是
        `compute_delta()`，本方法是全族唯一的 `apply` 定义（M1 期的占位实现
        `raise NotImplementedError` 已由 S8-1 按 AUDIT-BREAK-3 的两期形态替换）。

        **参数面故意保持四参**：`apply` 收 `readonly`（M1 骨架的调用形态），内部调用
        `compute_delta` 时**只传三参**（2026-10-08 裁决：`readonly` 随「Modifier 是
        pure 函数」一并废除）。S8 起的骨架改调 `compute_delta`，故本方法在生产路径
        上无消费者，它保留为「`apply()` 保留为默认实现」这条契约的承载处（§3.14.3）。
        """
        return _apply_delta(dist, self.compute_delta(view, dist, ctx) or {})


# ══════════════════════════════════════════════════════════════════
# 转移量语义族（§3.1.2 机制表第 1/2/3 行）
# ══════════════════════════════════════════════════════════════════

class HardModifier(Modifier):
    r"""硬保底（F 语义）：`counter >= threshold` 时把源组概率整组搬给目标集。

    §3.1.2 机制表的**两行**由 `target` 承载（`target_featured` 的选择子，取值由
    `_target_of(pdef)` 产出，§3.1.4 ISSUE-403）：

    | `target` | A（加组） | Q（减组） | 转移量 | A 侧形状 |
    |----------|-----------|-----------|--------|---------|
    | `'scope'`（默认） | `scope_cards[scope]` | 更低稀有度 | `p(Q)` | `current` |
    | `'featured'` | `featured_cards[scope]`（**空集回退 scope 全集**） | 更低稀有度 ∪ `scope\A` | `p(Q)` | `declared` |

    **转移量口径是「夺取型」`amount = p(Q)`（源组整组搬空）**，不是 soft 的
    `boost/100`——两者在 §3.1.5.2.2 是并列的两种取法，写混即机制错位。

    **S8 形态（增量法）**：A 加 `p(Q)`、Q 减 `p(Q)` 的配平转移（`Σδ = 0`），
    **更高稀有度不写增量即精确保留**。M1 的「目标集绝对赋值 + 更高稀有度豁免」
    形态（输出 `Σ > 1`）已随 S8-1 废除：它与框架的无条件归一化互斥
    （§3.9.5 的 `Σ(p + δ) ≠ 1` 行 / §3.1.2 边界二）。

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

    def compute_delta(self, view, dist: Dict[str, float],
                      ctx: PityContext) -> Optional[Dict[str, float]]:
        # ── 条件内联：counter >= τ（§3.1.2 机制表第 1 列）──
        if view.get('counter', 0) < self._threshold:
            return None

        # ── A / Q 就地解析（卡级；原 S2b 的解析器族已并入本族）──
        A = self._target_cards(ctx)
        if not A:
            return None                      # 空目标集 → 恒等（§3.9.5）
        scope = ctx.draw.scope_cards.get(self._scope, ())
        if self._target == 'featured':
            # tf=true 的 Q = 更低稀有度 ∪（scope 去掉 A）（§3.1.2 表第 2 行的「∪」）
            Q = _cards(_lower_rarities(ctx, self._scope),
                       tuple(c for c in scope if c not in set(A)))
            # A 侧 `declared`：A 是 featured 的真子集，会被同 scope 的 counter 驱动算子
            # 清空，`p(A) = 0` 时只有按声明权重分配才仍能转移（§3.1.2 的「A 侧形状」段）
            return transfer_linear(dist, A, Q, sum(dist[c] for c in Q),
                                   shape='declared',
                                   weights=ctx.draw.base_probabilities)
        Q = _lower_rarities(ctx, self._scope)
        return transfer_linear(dist, A, Q, sum(dist[c] for c in Q))

    # ── 内部 ──

    def _target_cards(self, ctx: PityContext) -> tuple:
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
        return _cards(cards)


class SoftModifier(Modifier):
    r"""软保底（B 语义）：`boost > 0` 时把源组的 `boost` 个百分点搬给 scope。

    | 项 | 取值（§3.1.2 机制表第 3 行） |
    |----|------------------------------|
    | 条件 | `boost > 0`（`boost%` 由 `deltas` 经 `_cumulative_boost` 从 counter 得出） |
    | A | `scope_cards[scope]` |
    | Q | 更低稀有度 |
    | 转移量 | `t = boost%(counter) / 100`（**封顶 `p(Q)`**，见下） |
    | A 侧形状 | `current` |

    **`t` 是百分点绝对量，不得再乘 `p(Q)`**（§3.4.1 修正 ①，2026-10-06 已落地于旧
    `SoftStepBehavior`）：`t = boost/100` 是「目标组概率**增加** boost 个百分点」，
    而 `t = boost/100 * p(Q)` 是「取源组的百分之几」——两者差一个因子 `p(Q) ≈ 1`，
    前期几乎不可见、爬升后段才拉开（第 89 抽 0.966 vs 0.9009）。

    **`t` 仍须封顶 `p(Q)`**（`t = min(boost/100, p(Q))`，与 M1 形态逐字同源）：
    §3.9.4 的前置条件表要求 `amount <= p(Q)`，否则 Q 侧增量为负、产出负概率。
    §3.9.4 的三个调用示例把 soft 写成 `transfer_linear(dist, A, Q, boost / 100.0)`、
    不带封顶，那是**示例的简化**（它的论证前提是「boost% 封顶 100，故 amount <= 1」，
    只在 Q 为全池时成立）；卡级下 `Q = 更低稀有度` 的小计可远小于 `boost/100`
    （真实配置 `ssr_soft` 第 90 抽 boost = 100、`p(低稀有度)` ≈ 0.11），漏封顶即
    负概率。

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

    def compute_delta(self, view, dist: Dict[str, float],
                      ctx: PityContext) -> Optional[Dict[str, float]]:
        # ── 条件内联：boost > 0 ──
        boost_pct = self._cumulative_boost(view.get('counter', 0))
        if boost_pct <= 0:
            return None

        A = _cards(ctx.draw.scope_cards.get(self._scope, ()))
        if not A:
            return None
        Q = _lower_rarities(ctx, self._scope)
        p_q = sum(dist[c] for c in Q)
        # 转移量为百分点绝对量，封顶 p(Q)（§3.9.4 前置条件表；M1 形态同式）
        return transfer_linear(dist, A, Q, min(boost_pct / 100.0, p_q))

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

class RotatingModifier(Modifier):
    r"""轮换保底（rotating）——`guaranteed` 时把 scope 内**非** featured 的概率整组搬给 featured。

    | 项 | 取值（§3.1.2 机制表第 4 行） |
    |----|------------------------------|
    | 条件 | `guaranteed` ∨（`extra_flag` ∧ ¬只读查询 ∧ `view.get(extra_flag)`） |
    | A（加组） | `featured_cards[scope]` |
    | Q（减组） | `scope\featured` |
    | 转移量 | `p(Q)` |
    | A 侧形状 | `current` |

    语义即「大小保底」：歪过一次后，出金必是 UP。

    **`extra_flag` 形参（§3.2 的 `rotating_cr` 行，2026-10-06 补）**：`rotating_cr` 与
    `rotating` 的效果完全相同（「出金必是 UP」），差别只在条件多一个 `cr_intercepted`
    （由 `StreakTracker.prepare` 掷骰后写入，裁决 6B′）。这是「条件内联」的代价之一：
    **条件若有变体，用构造形参表达，而不是新写一个类**（§3.2 同条）；该形参**只影响
    条件**，不影响 A/Q/转移量/形状。

    **只读查询抑制 `extra_flag`（§3.9.6 的「处置（两期）②」，M2 形态）**：6B′ 把 CR
    掷骰移回 `before_draw` 的 `prepare` 相位，只读查询会走到 `prepare` 的 `readonly`
    早退分支，于是 `cr_intercepted` 读到的是**上一次非只读调用**留下的 flag（差一抽）。
    M2 起 `readonly` 从 Modifier 签名废除，抑制依据改读 `ctx.readonly`（查询标记字段，
    `Pity.before_draw` 首行按其实参写入）：语义与 M1 的 `readonly` 形参逐条相同：
    **查询不体现拦截**（复刻旧 `RotatingCRBehavior` 的只读语义）。`guaranteed` 不受
    只读标记影响（旧类同样无条件读它）。
    """

    def __init__(self, scope: str, extra_flag: Optional[str] = None):
        self._scope = scope
        self._extra_flag = extra_flag

    def state_keys(self) -> tuple:
        if self._extra_flag:
            return ('guaranteed', self._extra_flag)
        return ('guaranteed',)

    def compute_delta(self, view, dist: Dict[str, float],
                      ctx: PityContext) -> Optional[Dict[str, float]]:
        # ── 条件内联：guaranteed ∨（extra_flag ∧ ¬只读查询）（§3.1.2 / §3.9.6）──
        if not (view.get('guaranteed')
                or (self._extra_flag and not ctx.readonly
                    and view.get(self._extra_flag))):
            return None

        # ── A / Q 就地解析（卡级；原 S2b 的解析器族已并入本族）──
        A = _cards(ctx.draw.featured_cards.get(self._scope, ()))
        if not A:
            # 空目标集 → 恒等（§3.9.5；旧实现同为空集早退：`if not featured_slots: return copy`）
            return None
        scope = ctx.draw.scope_cards.get(self._scope, ())
        Q = _cards(tuple(c for c in scope if c not in set(A)))
        if not Q:
            return None                      # 无源可搬（`p(Q) = 0` 的显式形态）
        return transfer_linear(dist, A, Q, sum(dist[c] for c in Q))


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
    复用 `_redistribute_scope` 反向调用」）：A / Q 互换，其余（scope 内重分配、scope 外
    不动）完全相同。手册场景为幻塔「连中必歪」——出 UP 后下一次 SSR 必非 UP。

    **A 侧取 `declared`（§3.1.2 表的「A 侧形状」列）**：A 是 featured 的补集，会被同
    scope 的夺 UP 算子清空，`p(A) = 0` 时只有按声明权重分配才仍能转移。

    **无 `flag` 形参**：条件内联后触发标志恒为 `forced_loss`（§3.3 末段明写
    「`NonFeaturedModifier` 本身**无 `flag` 形参**」）。`forced_loss` 是 preset 内部标志，
    `PityDef` 无对应初始值字段，初值恒 `False`（§3.3 的 preset 代码注释）。
    """

    def __init__(self, scope: str):
        self._scope = scope

    def state_keys(self) -> tuple:
        return ('forced_loss',)

    def compute_delta(self, view, dist: Dict[str, float],
                      ctx: PityContext) -> Optional[Dict[str, float]]:
        # ── 条件内联：forced_loss（§3.1.2 机制表第 5 行）──
        if not view.get('forced_loss'):
            return None

        # ── A / Q 就地解析：A = scope\featured，Q = featured（与 rotating 互换）──
        scope = ctx.draw.scope_cards.get(self._scope, ())
        Q = _cards(ctx.draw.featured_cards.get(self._scope, ()))
        A = _cards(tuple(c for c in scope if c not in set(Q)))
        if not A:
            return None
        return transfer_linear(dist, A, Q, sum(dist[c] for c in Q),
                               shape='declared',
                               weights=ctx.draw.base_probabilities)


class SelectedModifier(Modifier):
    r"""定轨保底（targeted）——`guaranteed` 或定轨就绪时把 scope 的概率整组搬给**定轨选中卡**。

    | 项 | 取值（§3.1.2 机制表第 6 行 / §3.9.2 的 `SelectedModifier` 示例） |
    |----|-------------------------------------------------------------|
    | 条件 | `guaranteed` ∨（已定轨 ∧ `fate_points >= tau`） |
    | A（加组） | `(selected,)`（未定轨时退化为全部 featured，见下） |
    | Q（减组） | `scope\A` |
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

    **两处 M1 沿用旧实现的形态被保留（逐字对齐旧 `TargetedBehavior.before_draw`，
    §3.9.2 的 S8 示例省略了它们）**：

    1. **「已定轨」是 fate 分支的合取项**：旧实现的第二析取项是
       `(selected and self._fate_points.value() >= self._fate_threshold)`，`selected`
       为假时整个析取项为假。故 `tau = 0` 且未定轨时**不触发**（若省掉该合取项，
       `fate_points >= 0` 恒真，会把「未定轨」当成「定轨就绪」）。
    2. **未定轨时目标集退化为全部 featured 卡**：旧 `_resolve_selected_slots(None, …)`
       首行即 `if selected is None: return featured_slots`。**这不是死分支**：手册明写
       「不填卡 ID 时可改用 `guaranteed_init = true` 等效」，该组合（`guaranteed_init=True`
       且未配 `selected_card_init`）正是「出金必是 UP、UP 内按声明权重分配」的既定配置
       形态。§3.1.2 机制表的 `A = (selected,)` 描述的是**定轨已设置**的常规分支。
       判据是「选中卡落在 **featured 集**内」（不是「落在 scope 内」）：旧
       `_resolve_selected_slots` 只在 featured 槽里认目标：选中一张 scope 内的
       非 featured 卡时，它会返回**第一个 featured 槽**（按槽位名反查稀有度、
       命中即返回该槽），而不是把该标准卡当目标。故本类的 `A` 取
       `(sel,) if sel in featured else featured`，与旧实现逐条对齐。
    """

    def __init__(self, scope: str, tau: int = 1):
        self._scope = scope
        self._tau = tau

    def state_keys(self) -> tuple:
        return ('guaranteed', 'fate_points', 'selected_card')

    def compute_delta(self, view, dist: Dict[str, float],
                      ctx: PityContext) -> Optional[Dict[str, float]]:
        sel = view.get('selected_card')
        # ── 条件内联：guaranteed ∨（已定轨 ∧ fate_points >= tau）（§3.1.2 第 6 行）──
        if not (view.get('guaranteed')
                or (sel is not None and view.get('fate_points', 0) >= self._tau)):
            return None

        # ── A / Q 就地解析：A = 定轨选中卡（**须落在 featured 集内**，对齐旧
        #    `_resolve_selected_slots` 的判据）；未定轨或选中卡不在 featured 内时
        #    退化为全部 featured ──
        scope = ctx.draw.scope_cards.get(self._scope, ())
        featured = _cards(ctx.draw.featured_cards.get(self._scope, ()))
        A = (sel,) if sel in set(featured) else featured
        if not A:
            return None
        Q = _cards(tuple(c for c in scope if c not in set(A)))
        if not Q:
            return None
        return transfer_linear(dist, A, Q, sum(dist[c] for c in Q),
                               shape='declared',
                               weights=ctx.draw.base_probabilities)


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
    UP 保留原概率、本抽仍可被抽到，与手册「已获得的装备从 UP 组中排除」冲突。S8 的
    增量形态下该裁决**可断言**（Q 的构成决定减量落点，不再被绝对赋值吸收）。

    **`ctx.sim` 是唯一的状态来源（§3.10.2）**：`ctx.sim.owns(card_id)` 返回该卡持有张数
    （`total_holding` 口径、**含初始持有**），0 即未拥有。该节明令**直接读、无 `None`
    兜底**（`sim` 非 Optional、永远填充；ISSUE-013 的兜底要求已随该节改判取消）。
    **时序说明**：`PityContext.sim` 字段由 **S9-2（M2）** 落在 `pity_primitives.py`，
    本类（S2a-2，M1）先交付读取方；M1 期本类**无消费者**（G3 的两个 type 与 preset 工厂
    归 S9-3），其单测自行提供 `sim` 替身。

    **「全部已拥有」的退化分支取形态 a**（§3.10.4）：A 为空 → `return None`（该次保底
    不触发、恒等）。形态 b（目标集退化为全部 featured、仍给出一件）由 **S9-3** 以
    `on_all_owned` 构造形参承载（该形参列在 §七 S9-3 的目标文件清单内，本步不提前落）。
    该分支是 §3.10.4 登记的**待确认项**（零直接信源、两形态并列，谁也不是已确认等价），
    本步只交付形态 a 的行为。

    **S8 形态（增量法）**：A 加 `p(Q)`、Q 减 `p(Q)`（`Σδ = 0`），**更高稀有度不写增量
    即精确保留**。M1 的「A 取绝对 1.0 + 更高稀有度豁免」形态（scope 非最高稀有度时
    输出 `Σ > 1`，同 §3.1.2 边界二的已登记差异类）已随 S8-1 废除；真实配置的 G3
    scope 为 `ssr`（rank 0），此时 `p(Q) = 1 − p(A)`，A 收下全部可用质量。
    """

    def __init__(self, scope: str, threshold: int = 50):
        self._scope = scope
        # 缺省 50：§3.10.4 配套第 1 条的 `tau = pdef.threshold if pdef.threshold is not
        # None else 50`（`hard` 为 90，本机制为 50 抽）
        self._threshold = threshold

    def state_keys(self) -> tuple:
        return ('counter',)

    def compute_delta(self, view, dist: Dict[str, float],
                      ctx: PityContext) -> Optional[Dict[str, float]]:
        # ── 条件内联：counter >= τ（§3.1.2 第 7 行；条件极性见 §3.10.4 的修正段——
        #    必须是「τ 抽触发」而**不是**恒真，恒真即退化为本节开头否定的 pool 层近似）──
        if view.get('counter', 0) < self._threshold:
            return None

        # ── A / Q 就地解析（卡级）──
        scope = ctx.draw.scope_cards.get(self._scope, ())
        featured = ctx.draw.featured_cards.get(self._scope, ())
        A = _cards(c for c in featured if ctx.sim.owns(c) == 0)
        if not A:
            # 空目标集（含「全部已拥有」形态 a）→ 恒等（§3.9.5 / §3.10.4）
            return None
        Q = _cards(tuple(c for c in scope if c not in set(A)),
                   _lower_rarities(ctx, self._scope))
        if not Q:
            return None
        return transfer_linear(dist, A, Q, sum(dist[c] for c in Q))
