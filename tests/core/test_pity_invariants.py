"""P64 S10-1：组合正确性验收的不变式性质测试（§3.12.1）。

**被测对象**：`Pity` 骨架（§3.1.4）的槽位级概率管道，零件为**随机组合**的
Tracker / Modifier / Lifecycle 三族实例。组合不经 registry、不走 `create_behavior`，
故组合空间不受 10 个 preset 限制（§3.12 的问题陈述：preset 等价性只证明「旧能力
未退化」，本文件证明「新能力自洽」）。每个组合以固定种子跑一段抽卡序列，逐抽记录
每一步 Modifier 的输入 / 输出分布与抽后状态，再对五条不变式断言。

**五条不变式与 §六「S10 组合正确性」条一一对应**（判据原文见 §3.12.1 的表）：

| # | 不变式 | 本文件的断言面 |
|---|--------|----------------|
| ① | 归一性 | 每步（F 步按 scope 感知式 / 转移步守恒）+ 每次抽卡的管道输出 |
| ② | 非负性 | 每步输出 + 每次抽卡的管道输出 |
| ③ | 增量合法性 | 每步 δ（`p + δ >= 0`；在 p 的支撑上不全为 0） |
| ④ | 状态键合法 | 构造期声明集汇总 + 运行期写入集 |
| ⑤ | 确定性 | 同种子两跑逐位相同（复用同一 Pity / 各自新建两条路径） |

## 归一性的口径已完成里程碑切换（ISSUE-903 的反转，S8-2 落地）

**本文件的判据现为恒等断言 `Σp = 1`**（每个触发的步、每次抽卡的管道输出都如此）。
M1 期的 **scope 感知式**（`Σp = 1 + Σp(被 F 豁免的更高稀有度槽位)`，出处 §3.12.1
的归一性行 + §3.13 的分布层行；实测形态见 §3.12.1 的 `hard(scope='sr')` 例，
输出 `{ssr: 0.006, ssr_featured: 0.003, sr: 1.0, r: 0.0}`、Σ = 1.009）**已随 S8
整块消失**：`_apply_delta`（§3.9.2）无条件归一化，且转移族恒有 `Σδ = 0` 使其
退化为恒等（§3.9.5 的「`Σ(p + δ) ≠ 1`」行已记该条消失），故 S8 起恒有 `Σp ≡ 1`。

**改写面（S8-2，S8-6 ⑤ 的一部分提前执行）**：原登记的三处断言（`..._scope_aware_
for_f_part` / `..._equals_last_f_step_exemption` / `..._hard_below_top_rarity_scope_
aware_shape`）按新语义重写，`_exempted_mass` / `_assert_scope_aware_total` 两个
助手同批删除。**这不是放宽**：`Σ ≠ 1` 从「有合法例外值」变成「一律是缺陷」，
判据面更严（且原式对**输出**分布取豁免量，本就有「豁免被整体去掉时两侧同时减到
1」的盲区，见下）。

## 组合面的三条生成纪律

这不是对被测代码的假设，而是本文件**生成器自身**的约束，三条都附理由：

1. **只生成满足 §3.12.2 合法组合判据的组合**（判据 1：同一键不被两个 Tracker
   声明；判据 2：Modifier 声明的读键在 Tracker 声明集内，另加 `selected_card`
   白名单）。镜像谓词见 `_criteria_violations()`，由
   `test_generated_combos_satisfy_combination_criteria` 断言恒空，并由
   `test_criteria_mirror_rejects_conflicting_parts` 自检「非恒真」。**判据的
   构造期拒收（抛 `ConfigError`）归 S10-2**（本块不改生产代码），其三条负例的
   用例名已在 §七 S10-2 写死（`test_illegal_*` / `test_cycle_*`），本文件不得
   抢先占用这三个名字，也不得让 `-k "illegal or cycle"` 命中本块的其他用例
   （**实测注意**：`-k cycle` 是子串匹配，任何名字里含 `lifecycle` 的用例都会被
   它命中，本文件已因此避开该词）。
2. **同一组合至多一个「目标集集中型」Modifier**（`rotating` / `rotating_cr` /
   `selected` / `not_owned` / `hard(target='featured')`）。理由：同 scope 的这类
   零件目标集重合（featured 槽集；本文件两种池形每稀有度都只有一张 featured 卡），
   串联时后者的输出恒等于输入，其 δ 在 p 的支撑上恒为 0，会让 §3.12.1 的
   「δ 在 p 的支撑上不全为 0」抛**假警报**（该组合合法但退化：第二个零件的语义
   已被第一个零件实现）。该退化组合由 `TestConcentratingPairDegeneracy` 以**更强**
   的断言单独覆盖（「两步串联的输出 == 第一步的输出」），而不是让不变式去判它。
3. **集中型零件须落在有 featured 卡的 (池形, scope) 上**（`scope='sr'` 且池形为
   `std` 时换用 `wide`）。理由：目标集恒空的零件整场不触发（§3.9.5 的空目标集
   边界），组合面会退化成「装了零件但从不生效」。**该边界不在本文件的组合面内**：
   全组合面扫描（2026-10-13）显示 `rotating` / `rotating_cr` / `selected` /
   `not_owned` 在两种池形两种 scope 下静态目标集均非空，本纪律的换池形恰好排除了
   唯一可能为空的 `(std, sr)` 情形（`seed101` 那类组合的未触发步全部来自 counter
   阈值未达，不是空目标集路径）；该边界由
   `tests/core/test_pity_modifier.py::TestRotatingModifier::test_rotating_modifier_empty_featured_returns_none`
   覆盖。该纪律只改池形，不改零件参数。

**该「δ 恒零」是实测而非推断**（2026-10-13）：先按 §3.12.1 的字面式实现，随机
组合跑红后定位到 `FlagTracker(guaranteed) + RotatingModifier + SelectedModifier`
单抽场景（第二步 `dist_out == dist_in`、δ 全域为 0）；定位过程与处置见
`TestConcentratingPairDegeneracy` 的 docstring。

## S8 的对应结构式：更高稀有度**不写增量**（逐位保留）

M1 的「豁免」在增量形式下的对应物是 §3.9.5 的「U 外的卡逐位不变」：`hard(scope='sr')`
的 A = sr 卡、Q = 更低稀有度卡，**更高稀有度的卡既不进 A 也不进 Q**，故其 δ 为 0、
取值逐位保留。本文件保留一条并列断言（`test_f_step_leaves_higher_rarity_unwritten`）
把该结构钉住：Σ 式（现为恒等 `Σp = 1`）对「豁免/保留被整体破坏」不敏感：把更高
稀有度的质量搬走再重新归一化，Σ 仍是 1，只有该结构式能拦下它。


## 与 S11 的分工

`tests/core/test_pity_invariant_checker.py` 是 S11 的专属文件，被测对象是
`InvariantChecker`（运行时校验器）；本文件的被测对象是**管道本身**（§七 S10-1
明写「两者被测对象不同，不得混用」）。
"""

import random
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import pytest

from gacha_simulator.core.config_store import ConfigError, PityDef
from gacha_simulator.core.pity import (
    Pity, PityEngine, _apply_delta, _EXTERNAL_STATE_KEYS,
)
from gacha_simulator.core.pity_modifier import (
    HardModifier,
    Modifier,
    NonFeaturedModifier,
    NotOwnedModifier,
    RotatingModifier,
    SelectedModifier,
    SoftModifier,
)
from gacha_simulator.core.pity_primitives import DrawInfo, PityContext, PityState
from gacha_simulator.core.pity_tracker import (
    AlwaysActive,
    CounterTracker,
    DependentActive,
    DependentFiniteActive,
    FateTracker,
    FiniteActive,
    FlagTracker,
    NamespaceTracker,
    StreakTracker,
)

# ── 常量 ──

#: 概率断言容差（§3.12.1 归一性行的「容差 1e-12」）。
TOL = 1e-12

#: 每个组合的抽数。须长到让计数型阈值（本文件取 2..5）与软保底爬升段都被越过。
DRAWS = 40

#: 组合的固定种子表。**逐个写死**，不用真随机：失败时 `combo.label` 带种子，
#: 可直接 `python -m pytest tests/core/test_pity_invariants.py -k seed<种子>` 复现。
COMBO_SEEDS: Tuple[int, ...] = (101, 102, 103, 104, 105, 106, 107, 108,
                                109, 110, 111, 112, 113, 114, 115, 116,
                                117, 118, 119, 120)

_POOL_ID = 's10_pool'
_PITY_NAME = 's10_combo'


# ══════════════════════════════════════════════════════════════════
# 一、池形（槽位映射与基础分布）
# ══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class _Shape:
    """一个池子的卡集合映射 + 基础分布（`DrawInfo` 的卡级映射齐备）。

    **S8-2 起 `base` 是卡级分布**（键即卡 id）：驱动层从调整后的分布抽一张卡、
    该卡即本次奖励（与「先定分布、再抽奖励」的引擎同形）。**S8-7 起不再携带槽位
    三字段**：它们只服务保留到发布前的旧保底类与等价性装置（ISSUE-901），本文件
    测的是卡级零件组合，三个字段零读者。
    """

    label: str
    rarity_rank: Dict[str, int]
    scope_cards: Dict[str, tuple]
    featured_cards: Dict[str, tuple]
    base: Dict[str, float]


#: 标准池形（与 `tests/core/test_pity_modifier.py` 的夹具同形，即
#: `compute_scope_mappings` 对「只有 ssr 有 featured 卡」的池子的真实卡集合产出）。
STANDARD_SHAPE = _Shape(
    label='std',
    rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
    scope_cards={'ssr': ('ssr_up', 'ssr_std'), 'sr': ('sr_std',), 'r': ('r_std',)},
    featured_cards={'ssr': ('ssr_up',)},
    base={'ssr_up': 0.006, 'ssr_std': 0.004, 'sr_std': 0.05, 'r_std': 0.94},
)

#: 宽池形：`sr` 也有 featured 卡（`compute_scope_mappings` 对「两级都有 UP」的池子
#: 的产出）。它使 `sr` 上的四个目标集语义 Modifier（`rotating` / `rotating_cr` /
#: `selected` / `not_owned`）从「恒不触发」变为可触发（实测 2026-10-13：这四者在
#: `(std, sr)` 下 `apply` 恒返回 `None`），是组合面覆盖 `sr` 触发面的必要一支。
#: `hard(target='featured')` 不在此列：其 A 在 featured 为空时回退 scope 全集
#: （§3.1.2 机制表第 2 行），在 `(std, sr)` 下照常触发。
WIDE_SHAPE = _Shape(
    label='wide',
    rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
    scope_cards={'ssr': ('ssr_up', 'ssr_std'), 'sr': ('sr_up', 'sr_std'),
                 'r': ('r_std',)},
    featured_cards={'ssr': ('ssr_up',), 'sr': ('sr_up',)},
    base={'ssr_up': 0.006, 'ssr_std': 0.004, 'sr_up': 0.01, 'sr_std': 0.04,
          'r_std': 0.94},
)

SHAPES: Tuple[_Shape, ...] = (STANDARD_SHAPE, WIDE_SHAPE)


# ══════════════════════════════════════════════════════════════════
# 二、观测装置（记录状态写入 / 逐步分布 / 抽样奖励）
# ══════════════════════════════════════════════════════════════════

class _Sim:
    """`ctx.sim` 的最小替身（`NotOwnedModifier` 只经 `ctx.sim.owns(card_id)` 读持有张数）。

    `PityContext.sim` 字段由 S9-2（M2）落为正式字段；先例：S2a-1 / S2a-2 的单测
    对尚未存在的成员自行提供替身。
    """

    def __init__(self, owned=()):
        self._owned = set(owned)

    def owns(self, card_id: str) -> int:
        return 1 if card_id in self._owned else 0


class _RecordingState(PityState):
    """记录**写入点**的 `PityState`：`set()` 是唯一写漏斗（`incr()` 亦经它），故只覆写它。

    记录集 `written` 是状态键合法不变式「运行期写入集」的观测面。
    """

    def __init__(self):
        super().__init__()
        self.written: set = set()

    def set(self, name, key, value):
        self.written.add((name, key))
        super().set(name, key, value)


@dataclass(frozen=True)
class _DrawStep:
    """一次抽卡的奖励事实（与 `DrawInfo` 的 reward 三字段对应）。"""

    card: str
    rarity: str
    is_featured: bool


@dataclass
class _Step:
    """一次 Modifier 应用的观测记录（δ 与归一性的观测面）。

    **S8-1 起记录的是增量本身**（`compute_delta` 的返回值），不再是「输出分布」：
    M1 的 Modifier 自算输出，S8 起输出由框架的 `_apply_delta` 统一算（§3.9.2），
    故 `dist_out` 改由本类**按同一式子重算**（与骨架的内循环同式，见其 property）。
    """

    draw_index: int
    part_key: str
    kind: str                 # 'f'（hard 族：`HardModifier` / `NotOwnedModifier`）/ 'transfer'
    scope: str
    dist_in: Dict[str, float]
    delta: Optional[Dict[str, float]]      # None = 本次未触发（`compute_delta` 返回 None）

    @property
    def fired(self) -> bool:
        return self.delta is not None

    @property
    def dist_out(self) -> Dict[str, float]:
        """该步的输出分布 = `_apply_delta(dist_in, delta)`（未触发即恒等）。

        与 `Pity.before_draw` 内循环的式子**同源同式**（同一函数、同一实参），
        故它是生产输出的忠实重建，而不是另写一份近似。
        """
        return _apply_delta(self.dist_in, self.delta or {})


class _StepLog:
    """逐步观测的载体（`_Recorder` 写入，驱动层按抽切分）。"""

    def __init__(self):
        self.draw_index = -1
        self.steps: List[_Step] = []


class _Recorder:
    """Modifier 的 1:1 委派包装，唯一作用是记录每步的输入 / 输出分布。

    **不改行为**：`Pity` 消费的四个成员（`compute_delta` / `rebind` / `state_keys` /
    `namespace`）一律直转发（S8-1 起骨架调 `compute_delta`，M1 期的 `apply` 已收敛为
    基类默认实现），`inner` 供断言取真实零件。故 `Pity._declared_keys` /
    `_namespaces` / `_view_for` 在包装下与未包装时同值。
    """

    def __init__(self, part: '_Part', log: _StepLog):
        self.inner = part.instance
        self.namespace = getattr(part.instance, 'namespace', None)
        self._part = part
        self._log = log

    def rebind(self, state, name):
        return self.inner.rebind(state, name)

    def state_keys(self):
        return self.inner.state_keys()

    def compute_delta(self, view, dist, ctx):
        delta = self.inner.compute_delta(view, dist, ctx)
        self._log.steps.append(_Step(
            draw_index=self._log.draw_index,
            part_key=self._part.key,
            kind=self._part.kind,
            scope=self._part.scope,
            dist_in=dict(dist),
            delta=None if delta is None else dict(delta),
        ))
        return delta


@dataclass
class _Run:
    """一次「组合 × 种子 × 抽数」的完整观测结果。"""

    combo: '_Combo'
    pity: Pity
    probs: List[Dict[str, float]]
    steps_by_draw: List[List[_Step]]
    snapshot: Dict            # 构造后（含 flags/counters/initialize 写入）的初始快照
    final_state: Dict
    written: set

    def steps(self) -> List[_Step]:
        return [s for draw in self.steps_by_draw for s in draw]

    def fired_steps(self) -> List[_Step]:
        return [s for s in self.steps() if s.fired]


# ══════════════════════════════════════════════════════════════════
# 三、零件目录（三族候选 + 声明集 / 读键 / 形态元数据）
# ══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class _Part:
    """组合里的一个零件实例 + 其元数据。"""

    key: str                   # 目录键（报错点名用）
    instance: object
    kind: str                  # 'f' / 'transfer'（仅 Modifier 有语义）
    declares: Tuple[str, ...]  # 期望的 `state_keys()`（由自检用例钉住）
    reads: Tuple[str, ...]     # Modifier 的读键（判据 2 的输入）
    scope: str = ''
    concentrating: bool = False  # 目标集集中型（生成纪律 2 的判据）


@dataclass(frozen=True)
class _TrackerSpec:
    declares: Tuple[str, ...]
    factory: Callable          # (rng, scope, name) -> Tracker


@dataclass(frozen=True)
class _ModifierSpec:
    declares: Tuple[str, ...]
    reads: Tuple[str, ...]
    factory: Callable          # (rng, scope) -> (instance, kind, concentrating)


@dataclass(frozen=True)
class _LifecycleSpec:
    declares: Tuple[str, ...]
    factory: Callable


#: Tracker 目录。`declares` 即各类的 `state_keys()`（§3.1.1）。
_TRACKER_SPECS: Dict[str, _TrackerSpec] = {
    'counter': _TrackerSpec(('counter',), lambda rng, scope, name: CounterTracker(
        scope=scope, reset_on=rng.choice((scope, 'featured', 'never')), init=0)),
    'flag_guaranteed': _TrackerSpec(
        ('guaranteed',), lambda rng, scope, name: FlagTracker(
            scope, 'featured', 'clear', 'set', 'guaranteed')),
    'flag_forced_loss': _TrackerSpec(
        ('forced_loss',), lambda rng, scope, name: FlagTracker(
            scope, 'featured', 'set', 'clear', 'forced_loss')),
    # `base_rate > 0` 使 `prepare` 真的消费全局随机源（确定性用例与 H4 的观测面）；
    # `state_probs` 末档 1.0 保留「确定性触发」路径（该路径不消费随机数）。
    'streak': _TrackerSpec(
        ('cr_counter', 'cr_intercepted'), lambda rng, scope, name: StreakTracker(
            scope=scope, judge='featured', threshold=3, base_rate=0.05,
            state_probs=[0.0, 0.0, 0.5, 1.0],
            flag='cr_intercepted', guard_flag='guaranteed')),
    'fate': _TrackerSpec(
        ('fate_points', 'losses', 'guaranteed', 'lost_rotating'),
        lambda rng, scope, name: FateTracker(
            scope=scope, judge='selected', hit='clear', miss='accumulate',
            keys=('fate_points', 'losses', 'guaranteed', 'lost_rotating'))),
    'namespace': _TrackerSpec(
        (), lambda rng, scope, name: NamespaceTracker(namespace=f'{name}_soft')),
}

#: Modifier 目录（六类七形态）。`declares` 即各类的 `state_keys()`（§3.1.2：读键
#: 一律在 Modifier 自己这里申报，条件内联后无需转发）；本文件的组合里 Modifier
#: 只读不写，故 `reads` 与 `declares` 同集。
_MODIFIER_SPECS: Dict[str, _ModifierSpec] = {
    'soft': _ModifierSpec(
        ('counter',), ('counter',),
        lambda rng, scope: (SoftModifier(scope, deltas=((2, 0.0), (3, 30.0))),
                            'transfer', False)),
    'hard': _ModifierSpec(
        ('counter',), ('counter',),
        lambda rng, scope: _hard_part(rng, scope)),
    'rotating': _ModifierSpec(
        ('guaranteed',), ('guaranteed',),
        lambda rng, scope: (RotatingModifier(scope), 'transfer', True)),
    'rotating_cr': _ModifierSpec(
        ('guaranteed', 'cr_intercepted'), ('guaranteed', 'cr_intercepted'),
        lambda rng, scope: (RotatingModifier(scope, extra_flag='cr_intercepted'),
                            'transfer', True)),
    'non_featured': _ModifierSpec(
        ('forced_loss',), ('forced_loss',),
        lambda rng, scope: (NonFeaturedModifier(scope), 'transfer', False)),
    'selected': _ModifierSpec(
        ('guaranteed', 'fate_points', 'selected_card'),
        ('guaranteed', 'fate_points', 'selected_card'),
        lambda rng, scope: (SelectedModifier(scope, tau=rng.choice((1, 2))),
                            'transfer', True)),
    'not_owned': _ModifierSpec(
        ('counter',), ('counter',),
        lambda rng, scope: (NotOwnedModifier(scope, threshold=rng.randint(2, 5)),
                            'f', True)),
}


def _hard_part(rng, scope):
    """`HardModifier` 的两形态（§3.1.2 机制表的两行由 `target` 承载）。"""
    target = rng.choice(('scope', 'featured'))
    return (HardModifier(scope, threshold=rng.randint(2, 5), target=target),
            'f', target == 'featured')


#: Lifecycle 目录（§3.1.3 四类）。`declares` 即 `state_keys()`：`Finite*` 在
#: `max_triggers > 0` 时声明 `triggers`。
_LIFECYCLE_SPECS: Dict[str, _LifecycleSpec] = {
    'always': _LifecycleSpec((), AlwaysActive),
    'finite': _LifecycleSpec(('triggers',), lambda: FiniteActive(max_triggers=2)),
    'dependent': _LifecycleSpec((), DependentActive),
    'dependent_finite': _LifecycleSpec(
        ('triggers',), lambda: DependentFiniteActive(max_triggers=2)),
}

#: 「读键 → 供键的 Tracker 目录键」表（判据 2 的供给面）。
#: `selected_card` 不在表内：它由策略层 `NonDrawAction` 写入、**无任何零件声明它**，
#: 是 §3.12.2 明列的**白名单**键（`_SELECTED_CARD_WHITELIST`）。
_READ_KEY_SUPPLIERS: Dict[str, Tuple[str, ...]] = {
    'counter': ('counter',),
    'guaranteed': ('flag_guaranteed', 'fate'),
    'forced_loss': ('flag_forced_loss',),
    'cr_intercepted': ('streak',),
    'fate_points': ('fate',),
}

_SELECTED_CARD_WHITELIST = ('selected_card',)


def _declares(part: _Part) -> Tuple[str, ...]:
    """零件实例的真实 `state_keys()`（目录元数据由自检用例与它对齐）。"""
    return tuple(part.instance.state_keys())


def _concat_declares(parts) -> Tuple[str, ...]:
    return tuple(k for p in parts for k in _declares(p))


# ══════════════════════════════════════════════════════════════════
# 四、随机组合（固定种子可复现）
# ══════════════════════════════════════════════════════════════════

@dataclass(eq=False)
class _Combo:
    """一个组合的完整描述（零件实例 + 初值 + 标签）。

    `eq=False`：组合含 dict 字段（`flags` / `counters`），默认 `__eq__` / `__hash__`
    会在 pytest 的参数比对与去重上踩到不可哈希字段；本文件的组合按 `label` 索引。
    """

    seed: int
    shape: _Shape
    scope: str
    trackers: Tuple[_Part, ...]
    modifiers: Tuple[_Part, ...]
    lifecycle_key: str
    lifecycle: object
    flags: Dict
    counters: Dict
    selected_card: Optional[str]
    owned: Tuple[str, ...]
    btype: str
    label: str

    @property
    def needs_activation(self) -> bool:
        """`Dependent*` 维的 `initialize` 为空实现，`_active` 由引擎激活传播写入。

        本文件在构造后手工写 `_active=True` 模拟该传播（否则 `before_draw` /
        `after_draw` 首行双双早退、整个组合恒等，不变式退化为恒真）。
        """
        return self.lifecycle_key.startswith('dependent')

    @property
    def namespace(self) -> str:
        return _PITY_NAME

    def has_f_part(self) -> bool:
        return any(p.kind == 'f' for p in self.modifiers)


def _random_combo(seed: int) -> _Combo:
    """按固定种子生成一个组合（**只生成合法且非退化的组合**，见模块 docstring）。"""
    rng = random.Random(seed)
    shape = rng.choice(SHAPES)
    scope = rng.choice(('ssr', 'sr'))

    # ── Modifier 子集：目录键洗牌后取前 n 个（链序 = 洗牌序，故链序也随机）──
    mod_keys = list(_MODIFIER_SPECS)
    rng.shuffle(mod_keys)
    modifiers: List[_Part] = []
    took_concentrating = False
    for key in mod_keys[:rng.randint(0, 3)]:
        spec = _MODIFIER_SPECS[key]
        inst, kind, concentrating = spec.factory(rng, scope)
        if concentrating and took_concentrating:
            continue                      # 生成纪律 2（同组合至多一个集中型）
        took_concentrating = took_concentrating or concentrating
        modifiers.append(_Part(key, inst, kind, spec.declares, spec.reads, scope,
                               concentrating))

    # ── 生成纪律 3：集中型零件的目标集是 scope 的 featured 卡集，若该 (池形, scope)
    #    无 featured 卡则目标集恒空、该零件结构性不触发（§3.9.5 的空目标集边界），
    #    组合面会退化成「装了个零件但从不生效」。故此处把池形换成有 featured 卡的
    #    宽池形。该边界因此**不在本文件的组合面内**（扫描结果与覆盖它的用例见
    #    模块 docstring 的生成纪律 3）。`hard(target='featured')` 同属集中型
    #    （`_hard_part` 的 `concentrating` 判据），但它的 A 取「空 featured 回退
    #    scope 全集」（§3.1.2 机制表第 2 行），故不存在目标集为空的情形。
    if scope == 'sr' and not shape.featured_cards.get('sr') \
            and any(p.concentrating for p in modifiers):
        shape = WIDE_SHAPE

    # ── Tracker：先满足 Modifier 的读键（判据 2），再随机加 0..2 个键集不相交的 ──
    needed = {k for p in modifiers for k in p.reads}
    covered: set = set()
    chosen: List[str] = []
    for key in sorted(needed):
        if key in covered or key in _SELECTED_CARD_WHITELIST:
            continue
        suppliers = _READ_KEY_SUPPLIERS[key]
        if 'fate_points' in needed and 'fate' in suppliers:
            pick = 'fate'                 # 一次供两键（guaranteed + fate_points）
        else:
            pick = rng.choice(suppliers)
        if pick in chosen:
            continue
        chosen.append(pick)
        covered.update(_TRACKER_SPECS[pick].declares)

    declared_now = {k for key in chosen for k in _TRACKER_SPECS[key].declares}
    extras = [k for k in _TRACKER_SPECS
              if k not in chosen
              and not (set(_TRACKER_SPECS[k].declares) & declared_now)]
    for pick in rng.sample(extras, rng.randint(0, min(2, len(extras)))):
        chosen.append(pick)
        declared_now.update(_TRACKER_SPECS[pick].declares)
    if not chosen:                        # 每个组合至少一个 Tracker（避免空组合）
        chosen.append(rng.choice(list(_TRACKER_SPECS)))

    trackers = [_Part(k, _TRACKER_SPECS[k].factory(rng, scope, _PITY_NAME),
                      'tracker', _TRACKER_SPECS[k].declares, ())
                for k in chosen]

    # ── Lifecycle ──
    lc_key = rng.choice(tuple(_LIFECYCLE_SPECS))

    # ── 初值（一律取已声明键；`selected_card` 走白名单）──
    flags: Dict = {}
    counters: Dict = {}
    if any(p.key in ('rotating', 'rotating_cr', 'selected') for p in modifiers):
        flags['guaranteed'] = rng.choice((True, False))
    if 'fate' in chosen:
        counters['fate_points'] = rng.choice((0, 2))
    selected_card = None
    featured_cards = [c for cards in shape.featured_cards.values() for c in cards]
    if any(p.key == 'selected' for p in modifiers) or 'fate' in chosen:
        selected_card = rng.choice([None] + featured_cards)
    owned = tuple(rng.sample(featured_cards,
                             rng.randint(0, len(shape.featured_cards))))

    label = (f'seed{seed}|{shape.label}|scope={scope}'
             f'|T[{"+".join(chosen)}]'
             f'|M[{"+".join(p.key for p in modifiers)}]|L[{lc_key}]')
    return _Combo(
        seed=seed, shape=shape, scope=scope, trackers=tuple(trackers),
        modifiers=tuple(modifiers), lifecycle_key=lc_key,
        lifecycle=_LIFECYCLE_SPECS[lc_key].factory(),
        flags=flags, counters=counters, selected_card=selected_card,
        owned=owned,
        btype='hard' if any(p.kind == 'f' for p in modifiers) else 'soft_step',
        label=label,
    )


#: 组合面（模块导入期生成一次：纯 Python、无副作用、可复现）。
_COMBOS: Tuple[_Combo, ...] = tuple(_random_combo(s) for s in COMBO_SEEDS)

#: 含 / 不含 F 型零件的两个子面（归一性的两条口径各自的作用域）。
_COMBOS_WITH_F: Tuple[_Combo, ...] = tuple(c for c in _COMBOS if c.has_f_part())
_COMBOS_WITHOUT_F: Tuple[_Combo, ...] = tuple(c for c in _COMBOS
                                              if not c.has_f_part())

_IDS_ALL = [c.label for c in _COMBOS]
_IDS_WITH_F = [c.label for c in _COMBOS_WITH_F]
_IDS_WITHOUT_F = [c.label for c in _COMBOS_WITHOUT_F]


# ══════════════════════════════════════════════════════════════════
# 五、驱动（与 `PityEngine.before_draw` / `after_draw` 的调度同形）
# ══════════════════════════════════════════════════════════════════

def _ctx(shape: _Shape, state: PityState, *, sim: _Sim,
         step: Optional[_DrawStep] = None) -> PityContext:
    """构造一次抽卡的 `PityContext`（抽前 `step=None`；抽后带奖励事实）。

    与 `PityEngine.before_draw` / `after_draw` 两处的 `DrawInfo` 构造同形（抽后
    上下文的 `base_probabilities` / `current` 均为空表）。
    """
    draw = DrawInfo(
        pool_id=_POOL_ID, pool_instance_id=f'{_POOL_ID}_0',
        reward_id=step.card if step else '',
        reward_rarity=step.rarity if step else '',
        is_featured=step.is_featured if step else False,
        scope_cards=shape.scope_cards, featured_cards=shape.featured_cards,
        base_probabilities=dict(shape.base) if step is None else {},
        rarity_rank=shape.rarity_rank,
    )
    ctx = PityContext(
        draw=draw, current=dict(shape.base) if step is None else {}, state=state)
    ctx.sim = sim
    return ctx


def _step_of(shape: _Shape, card: str) -> _DrawStep:
    """**卡 id** → 奖励事实（稀有度由 `scope_cards` 反查，featured 由 `featured_cards` 判定）。

    S8-2 起分布是卡级的，故抽样得到的键就是卡 id、无需再经槽位反查（M1 期的
    `slot_to_card` 随之删除）。
    """
    rarity = next((r for r, cs in shape.scope_cards.items() if card in cs), '')
    featured = any(card in cs for cs in shape.featured_cards.values())
    return _DrawStep(card=card, rarity=rarity, is_featured=featured)


def _build_pity(combo: _Combo, state: PityState, log: _StepLog) -> Pity:
    """构造骨架。Modifier 一律经 `_Recorder` 包装（仅记录，不改行为）。"""
    return Pity(
        name=_PITY_NAME, state=state, scope=combo.scope, btype=combo.btype,
        trackers=[p.instance for p in combo.trackers],
        modifiers=[_Recorder(p, log) for p in combo.modifiers],
        lifecycle=combo.lifecycle,
        flags=dict(combo.flags), counters=dict(combo.counters),
    )


def _snapshot_copy(snapshot: Dict) -> _RecordingState:
    """从初始快照派生一个新账本（worker 内第 2..N 场的开工态，§3.1.4 / P75）。"""
    state = _RecordingState()
    state.data = {ns: dict(kv) for ns, kv in snapshot['data'].items()}
    return state


@contextmanager
def _seeded_rng(seed: int):
    """固定全局种子 + 统计 `random.random()` 消费次数，退出时无条件还原。

    形状同 `tests/core/test_pity_equivalence.py` 的 `_counting_rng`；额外还原
    `random.getstate()`，使本文件的播种不外溢到其他测试。
    """
    saved = random.getstate()
    random.seed(seed)
    calls = {'n': 0}
    original = random.random

    def _counted():
        calls['n'] += 1
        return original()

    random.random = _counted
    try:
        yield calls
    finally:
        random.random = original
        random.setstate(saved)


def _drive(pity: Pity, state: PityState, combo: _Combo, log: _StepLog, *,
           draws: int, snapshot: Dict,
           sequence: Optional[Tuple[_DrawStep, ...]] = None) -> _Run:
    """逐抽驱动：`before_draw` → 抽奖励 → `after_draw`（每抽的 `current` 取基础分布）。

    `sequence` 给定时按固定序列发奖励（RNG 计数用例用）；否则从**调整后的分布**
    抽样（与引擎「先定分布、再抽奖励」同形）。
    """
    shape = combo.shape
    sim = _Sim(combo.owned)
    probs: List[Dict[str, float]] = []
    steps_by_draw: List[List[_Step]] = []
    for index in range(draws):
        log.draw_index = index
        start = len(log.steps)
        out = pity.before_draw(_ctx(shape, state, sim=sim))
        probs.append(dict(out))
        steps_by_draw.append(log.steps[start:])
        if sequence is not None:
            step = sequence[index % len(sequence)]
        else:
            slot = random.choices(list(out), weights=[out[k] for k in out], k=1)[0]
            step = _step_of(shape, slot)
        pity.after_draw(_ctx(shape, state, sim=sim, step=step))
    return _Run(
        combo=combo, pity=pity, probs=probs, steps_by_draw=steps_by_draw,
        snapshot=snapshot, final_state=state.to_dict(),
        written=set(getattr(state, 'written', set())),
    )


def _open_pity(combo: _Combo, log: _StepLog):
    """构造 Pity + 账本并完成开工准备（含 `_active` 补写与首次 rebind）。

    返回 `(pity, state, snapshot)`。**驱动纪律**：骨架不在构造期绑定零件
    Counter / Flag（§3.1.4），故驱动前必须 `_rebind_state`（引擎在三个调度入口
    首行做同一件事）。
    """
    state = _RecordingState()
    pity = _build_pity(combo, state, log)
    if combo.needs_activation:
        state.set(_PITY_NAME, '_active', True)
    pity._rebind_state(state)
    return pity, state, state.to_dict()


def _run_combo(combo: _Combo, *, draws: int = DRAWS) -> _Run:
    """构造 + 驱动（新 Pity、新账本）。"""
    log = _StepLog()
    pity, state, snapshot = _open_pity(combo, log)
    with _seeded_rng(combo.seed):
        return _drive(pity, state, combo, log, draws=draws, snapshot=snapshot)


def _run_combo_twice_reusing_pity(combo: _Combo, *,
                                  draws: int = DRAWS) -> Tuple[_Run, _Run]:
    """同种子、同 Pity 对象、两场各自新账本（worker 内连跑 N 场的形态）。

    第二场的开工态取自第一场的初始快照（`env.pity_state_init` 口径），零件经
    `Pity._rebind_state` 纯重定向到新账本。
    """
    log = _StepLog()
    pity, state, snapshot = _open_pity(combo, log)
    with _seeded_rng(combo.seed):
        first = _drive(pity, state, combo, log, draws=draws, snapshot=snapshot)
    log2 = _StepLog()
    state2 = _snapshot_copy(snapshot)
    pity._rebind_state(state2)
    with _seeded_rng(combo.seed):
        second = _drive(pity, state2, combo, log2, draws=draws, snapshot=snapshot)
    return first, second


_TRACE_CACHE: Dict[str, _Run] = {}


def _trace(combo: _Combo) -> _Run:
    """组合的观测结果（每个组合跑一次，全文件复用同一条轨迹）。"""
    run = _TRACE_CACHE.get(combo.label)
    if run is None:
        run = _run_combo(combo)
        _TRACE_CACHE[combo.label] = run
    return run


# ══════════════════════════════════════════════════════════════════
# 六、§3.12.2 合法组合判据的镜像谓词（生成器守卫）
# ══════════════════════════════════════════════════════════════════

def _criteria_violations(trackers, modifiers) -> List[str]:
    """§3.12.2 判据 1 / 2 的**镜像**（本文件自用；构造期拒收归 S10-2）。

    判据 1：同一键被两个 Tracker 声明（比对 `trackers` 声明集的重复）。
    判据 2：Modifier 声明的读键不在 `trackers` 的声明集内，且不在
    `selected_card` 白名单内。

    **本镜像不建模判据 2 并集的 lifecycle 半边**（形参面无 Lifecycle）。该半边在
    **当前组合面上与生产判据零差异**，理由是实测而非推断：`_LIFECYCLE_SPECS` 的
    `finite` / `dependent_finite` **确实声明** `('triggers',)`（且两者都已纳入
    组合面），但组合面内**无任何 Modifier 读 `triggers`**（Modifier 的 `state_keys()`
    只有 counter / guaranteed / forced_loss / cr_intercepted / fate_points /
    selected_card 六个键），故「Tracker 声明集」与「Tracker ∪ Lifecycle 声明集」
    对 Modifier 的可读键给出同一答案。生产侧该半边由 S10-2 的
    `test_finite_activation_declared_key_accepted` 两方向覆盖。

    **不含** Tracker 自身的读键：判据 2 的文本只约束 Modifier（§3.12.2），
    `StreakTracker` 对 `guaranteed` 的守卫读带默认值、缺键无害，不在两条判据内。
    """
    problems: List[str] = []
    seen: set = set()
    for part in trackers:
        for key in _declares(part):
            if key in seen:
                problems.append(f'判据 1：Tracker 重复声明键 {key!r}')
            seen.add(key)
    for part in modifiers:
        for key in _declares(part):
            if key not in seen and key not in _SELECTED_CARD_WHITELIST:
                problems.append(
                    f'判据 2：Modifier {part.key!r} 引用不存在的键 {key!r}')
    return problems


# ══════════════════════════════════════════════════════════════════
# 七、断言助手
# ══════════════════════════════════════════════════════════════════

def _higher_rarity_cards(shape: _Shape, scope: str) -> Tuple[str, ...]:
    """比 `scope` 更高的稀有度下的**全部卡**（由池事实独立算出，不读生产助手）。

    判据同 §3.1.2 的「更低稀有度」的对偶：`rarity_rank` 中 `rank < rank(scope)` 的
    稀有度之全部卡。**本文件自算**（不复用 `pity_modifier._lower_rarities` 或其对偶），
    理由是 S10-1 的方法学纪律：期望值与生产值同源时，生产侧坏掉会让两侧同向偏移、
    断言双双失明。
    """
    scope_rank = shape.rarity_rank.get(scope, 99)
    out: List[str] = []
    for rarity, rank in shape.rarity_rank.items():
        if rank < scope_rank:
            out.extend(shape.scope_cards.get(rarity, ()))
    return tuple(out)


def _total(dist: Dict[str, float]) -> float:
    return sum(dist.values())


def _assert_total_is_one(dist: Dict[str, float], where: str) -> None:
    """§3.12.1 归一性（**S8 起的唯一口径**）：`Σp = 1`（容差 1e-12）。

    M1 期的 scope 感知式（`1 + Σp(豁免槽位)`）与其助手 `_exempted_mass` /
    `_assert_scope_aware_total` 已随 S8 删除，理由见模块 docstring 的
    「归一性的口径已完成里程碑切换」段。
    """
    assert abs(_total(dist) - 1.0) <= TOL, (
        f'{where}：Σp = {_total(dist)!r}，期望 1.0（S8 起 `_apply_delta` 无条件归一化）')


def _declared_allowed(run: _Run) -> set:
    """三族声明集的并集 + `_active`（生命周期层的键，见状态键用例的 docstring）。"""
    declared = run.pity._declared_keys
    return (set(declared['trackers']) | set(declared['modifiers'])
            | set(declared['lifecycle']) | {'_active'})


# ══════════════════════════════════════════════════════════════════
# 八、① 归一性
# ══════════════════════════════════════════════════════════════════

class TestNormalizationInvariant:
    """§3.12.1 归一性行：**S8 起的恒等口径**（每个触发的步、每次抽卡的管道输出
    都 `Σp = 1`（改写记录见模块 docstring 的「归一性的口径已完成里程碑切换」段）。"""

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_every_fired_step_total_is_one(self, combo):
        """**每个**触发的步（含 hard 族的 F 步）输出 `Σp = 1`。

        M1 期的 scope 感知式对 F 步另取 `1 + Σp(豁免槽位)`；S8 起 F 步是配平转移
        （A 加 `p(Q)`、Q 减 `p(Q)`，`Σδ = 0`），框架归一化退化为恒等，故本式对
        **全部**机制同形：「F 步是个例外」这件事在 M2 不复存在。
        """
        run = _trace(combo)
        for step in run.fired_steps():
            _assert_total_is_one(
                step.dist_out,
                f'[{combo.label}] 第 {step.draw_index} 抽的 {step.part_key} 步')

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_transfer_step_preserves_total(self, combo):
        """转移族步：`Σδ = 0`（总量守恒）。

        §3.1.5.2.1 的「转移族恒有 `Σδ = 0`」是本式的出处；它是 S8 管道「`Σp ≡ 1`
        从第一步传播到末端」的载体（每个机制都只在 A / Q 之间搬质量，其余卡不写增量）。
        """
        run = _trace(combo)
        for step in run.fired_steps():
            if step.kind == 'f':
                continue
            before, after = _total(step.dist_in), _total(step.dist_out)
            assert abs(after - before) <= TOL, (
                f'[{combo.label}] 第 {step.draw_index} 抽的 {step.part_key} 步：'
                f'Σ 由 {before!r} 变为 {after!r}（转移族须守恒）')

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_delta_is_balanced_for_every_fired_step(self, combo):
        """`Σδ = 0` 对**全部**机制成立（含 hard 族的 F 步）。

        这是 S8 相对 M1 的结构性变化：M1 的 F 型是「绝对赋值 + 更高稀有度豁免」，
        其 δ 在输出侧不配平（`Σ(out + δ) = 1 + m`）；S8 起 F 型同为配平转移，
        故本式覆盖六个机制、无例外。
        """
        run = _trace(combo)
        for step in run.fired_steps():
            total_delta = sum((step.delta or {}).values())
            assert abs(total_delta) <= TOL, (
                f'[{combo.label}] 第 {step.draw_index} 抽的 {step.part_key} 步：'
                f'Σδ = {total_delta!r}（S8 起全部机制配平）')

    #: 本用例的判据域 = 「有更高稀有度可比」的 F 型组合（scope 已是最高稀有度时
    #: 「更高稀有度卡集」为空、断言无判别对象）。**在参数化处筛掉**而不是在用例内
    #: `skip`：跳过会让「域为空」与「域内全过」长得一样，而域非空这一事实由
    #: `TestCombinationSpaceCoverage` 的覆盖守卫单独断言。
    @pytest.mark.parametrize(
        'combo', [c for c in _COMBOS_WITH_F if _higher_rarity_cards(c.shape, c.scope)],
        ids=[c.label for c in _COMBOS_WITH_F if _higher_rarity_cards(c.shape, c.scope)])
    def test_f_step_leaves_higher_rarity_unwritten(self, combo):
        """F 步（hard 族）**不写更高稀有度卡的增量** → 其取值逐位保留。

        这是 M1 的「豁免」在增量形式下的对应物（§3.9.5 的「U 外的卡逐位不变」）：
        A = scope 卡集、Q = 更低稀有度卡集，更高稀有度的卡**既不在 A 也不在 Q**，
        故其 δ 为 0、输出逐位等于输入。**为什么该结构式必须与 Σ 式并存**：Σ 式
        （现为恒等 `Σp = 1`）对「把更高稀有度的质量搬走再重新归一化」不敏感：
        那仍然归一，只有本式能拦下它。**豁免集写死为「比 scope 高的稀有度卡」**
        （由 `combo.shape.rarity_rank` 与 `scope_cards` 独立算出，不读生产助手：
        读助手会让期望值与生产值同向偏移，故障时双双失明）。
        """
        run = _trace(combo)
        higher = _higher_rarity_cards(combo.shape, combo.scope)
        assert higher, '本用例的参数化域须保证有更高稀有度卡（否则断言无判别对象）'
        for step in [s for s in run.fired_steps() if s.kind == 'f']:
            for key in higher:
                assert step.delta.get(key, 0.0) == 0.0, (
                    f'[{combo.label}] 第 {step.draw_index} 抽的 {step.part_key} 步：'
                    f'更高稀有度卡 {key!r} 不得写增量，实测 '
                    f'δ = {step.delta.get(key, 0.0)!r}')
                # 结构式（δ 恰为 0）精确；**取值**只到 §六 的 S8 容差 1e-12：
                # 框架的归一化 `(p + δ) / Σ(p + δ)` 在 `Σ(out)` 与 1.0 差 1 ULP 时
                # 会把**每一张卡**（含未被触碰的）整体缩放 1 ULP（实测 seed118 的
                # `ssr_up` 由 0.006 变 0.006000000000000001）。「逐位保留」在
                # 归一化管道的字面意义到此为止，故判据拆成两半：结构上 δ ≡ 0
                # （精确）、数值上保留（1e-12）。
                assert abs(step.dist_out[key] - step.dist_in[key]) <= TOL, (
                    f'[{combo.label}] 第 {step.draw_index} 抽的 {step.part_key} 步：'
                    f'更高稀有度卡 {key!r} 须保留 {step.dist_in[key]!r}，'
                    f'实测 {step.dist_out[key]!r}')

    @pytest.mark.parametrize('combo', _COMBOS_WITHOUT_F, ids=_IDS_WITHOUT_F)
    def test_pipeline_total_is_one_without_f_part(self, combo):
        """无 F 型参与时 `Σp = 1`（S8 起该式对**全部**组合成立，本子面是它的非空转
        对照组：无 F 时连 M1 的例外条都不适用）。"""
        run = _trace(combo)
        for index, dist in enumerate(run.probs):
            _assert_total_is_one(dist, f'[{combo.label}] 第 {index} 抽的管道输出')

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_pipeline_total_is_one_for_every_combo(self, combo):
        """**全部**组合的管道输出 `Σp = 1`（含 F 型组合：M1 期这一支取
        `1 + Σp(最后一次 F 步的豁免槽位)`，S8 起两支持平）。"""
        run = _trace(combo)
        for index, dist in enumerate(run.probs):
            _assert_total_is_one(dist, f'[{combo.label}] 第 {index} 抽的管道输出')

    def test_hard_below_top_rarity_leaves_higher_rarity_untouched(self):
        """定点用例：`hard(scope='sr')` 的输出 `Σ = 1`，且 ssr 两张卡逐位保留。

        M1 期的对应形态是「Σ = 1 + p(ssr 槽位) > 1」（§3.12.1 的实测例
        `{ssr: 0.006, ssr_featured: 0.003, sr: 1.0, r: 0.0}`、Σ = 1.009）；S8 起
        目标集（sr 卡）收下 `p(Q)`（Q = 更低稀有度 r 卡）、更高稀有度不写增量，
        故 Σ = 1、ssr 卡逐位保留。

        **定点断言的角色**：`higher` 集由 `scope_cards` / `rarity_rank` **独立算出**
        （写死为「ssr 的两张卡」这一事实），不读任何生产助手：助手自身坏掉时期望值
        会与生产值同向偏移，只有独立算出的字面集能钉住它。
        """
        combo = _FIXED_COMBOS['hard_below_top']
        run = _trace(combo)
        fired = [s for s in run.fired_steps() if s.kind == 'f']
        assert fired, 'hard(scope=sr) 须在本序列内触发（否则本用例无观测对象）'
        step = fired[0]
        dist = step.dist_out
        higher = _higher_rarity_cards(combo.shape, 'sr')
        assert set(higher) == {'ssr_up', 'ssr_std'}, (
            f'更高稀有度卡集须为 ssr 的两张卡，实测 {sorted(higher)}')
        _assert_total_is_one(dist, '[hard_below_top] 该步输出')
        assert _total(dist) == pytest.approx(1.0, abs=TOL), 'S8 起 Σp ≡ 1（M1 为 1.009）'
        # 本组合只有 hard 一个 Modifier，故该步输出即**管道输出**
        _assert_total_is_one(run.probs[step.draw_index], '[hard_below_top] 管道输出')
        for key in higher:
            assert abs(dist[key] - combo.shape.base[key]) <= TOL, (
                f'更高稀有度卡 {key} 须保留 {combo.shape.base[key]!r}，'
                f'实测 {dist[key]!r}（容差 1e-12：归一化在 Σ 差 1 ULP 时整体缩放）')
        # A = sr 卡收下 p(Q) = p(r 卡) = 0.94 → 0.99；Q 归零
        assert dist['sr_std'] == pytest.approx(0.99, abs=TOL), 'sr 卡收下 p(Q)'
        assert dist['r_std'] == pytest.approx(0.0, abs=TOL), '更低稀有度须被搬空'


# ══════════════════════════════════════════════════════════════════
# 九、② 非负性
# ══════════════════════════════════════════════════════════════════

class TestNonNegativityInvariant:
    """§3.12.1 非负性行：「所有卡的概率 ≥ 0」。"""

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_all_step_outputs_and_pipeline_dist_non_negative(self, combo):
        run = _trace(combo)
        for step in run.fired_steps():
            for key, value in step.dist_out.items():
                assert value >= 0.0, (
                    f'[{combo.label}] 第 {step.draw_index} 抽的 {step.part_key} 步：'
                    f'槽位 {key!r} 的概率为 {value!r}（须 ≥ 0；NaN 亦在此判据下失败）')
        for index, dist in enumerate(run.probs):
            for key, value in dist.items():
                assert value >= 0.0, (
                    f'[{combo.label}] 第 {index} 抽的管道输出：槽位 {key!r} 的概率为 '
                    f'{value!r}（须 ≥ 0）')


# ══════════════════════════════════════════════════════════════════
# 十、③ 增量合法性
# ══════════════════════════════════════════════════════════════════

class TestDeltaLegalityInvariant:
    """§3.12.1 增量合法性行：「`p + δ ≥ 0`；δ 在 p 的支撑上不全为 0」。

    **δ 的来源**：M1 槽位级管道没有增量表示（§3.13 的增量层行明写「M1 槽位级管道
    没有增量表示，仅凭 `dist` 取不到该步的 δ」，该层的运行时校验随 S8-6 落地），
    故本文件按 `δ = 输出 − 输入` 逐步构造（每步由 `_Recorder` 记录）。
    """

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_delta_keeps_probabilities_non_negative(self, combo):
        """`p + δ ≥ 0`（按 `p` 与 `δ` 逐位相加判，不预先约简成 `out ≥ 0`）。"""
        run = _trace(combo)
        for step in run.fired_steps():
            delta = step.delta or {}
            for key, p in step.dist_in.items():
                combined = p + delta.get(key, 0.0)
                assert combined >= 0.0, (
                    f'[{combo.label}] 第 {step.draw_index} 抽的 {step.part_key} 步：'
                    f'p({key!r}) + δ = {p!r} + {delta.get(key, 0.0)!r} = {combined!r} < 0')

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_fired_delta_nonzero_on_support(self, combo):
        """δ 在 p 的支撑上不全为 0（触发的步不得是静默空操作）。

        **判据域**：只对 `apply` 返回了分布的步（未触发的步 δ 恒零是设计语义，
        非本式所指）。**生成纪律 2**（模块 docstring）已排除「两个集中型 Modifier
        串联、后者语义被前者实现」这一合法但退化的组合，其 δ 恒零由
        `TestConcentratingPairDegeneracy` 以更强的断言覆盖。
        """
        run = _trace(combo)
        for step in run.fired_steps():
            support = [k for k, v in step.dist_in.items() if v > 0.0]
            assert support, (
                f'[{combo.label}] 第 {step.draw_index} 抽的 {step.part_key} 步：'
                f'输入分布无支撑（p 恒为 0），本不变式无判别力')
            delta = step.delta or {}
            assert any(delta.get(k, 0.0) != 0.0 for k in support), (
                f'[{combo.label}] 第 {step.draw_index} 抽的 {step.part_key} 步：'
                f'δ 在支撑 {support} 上恒为 0（该步触发了却未改动任何有概率的槽位）')


# ══════════════════════════════════════════════════════════════════
# 十一、④ 状态键合法
# ══════════════════════════════════════════════════════════════════

class TestDeclaredStateKeysInvariant:
    """§3.12.1 状态键合法行：「Tracker 写入的键在其自己声明的键集内」。

    比对集 = `Pity._declared_keys`（三族 `state_keys()` 的汇总，§3.1.4；S10-2 /
    S11 的唯一输入）。§六 明写「断言须先证该汇总非空」，故本组先钉汇总的聚合恒等
    与非空，再查运行期写入集，最后钉「内联条件读键须出现在 `modifiers` 声明集内」。
    """

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_declared_keys_aggregation_matches_parts(self, combo):
        """汇总恒等：`_declared_keys` 三个元组 == 三族各自 `state_keys()` 的拼接。"""
        run = _trace(combo)
        declared = run.pity._declared_keys
        assert set(declared) == {'trackers', 'modifiers', 'lifecycle'}
        families = (
            ('trackers', combo.trackers),
            ('modifiers', combo.modifiers),
            ('lifecycle', ()),
        )
        for family, parts in families:
            if family == 'lifecycle':
                expected = _LIFECYCLE_SPECS[combo.lifecycle_key].declares
            else:
                expected = _concat_declares(parts)
            assert tuple(declared[family]) == tuple(expected), (
                f'[{combo.label}] {family} 汇总集 {declared[family]} 与零件声明集 '
                f'{expected} 不符')
            if expected:
                assert len(declared[family]) > 0, (
                    f'[{combo.label}] {family} 的零件声明了键，汇总集却为空')

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_runtime_writes_within_declared_keys(self, combo):
        """运行期写入集 ⊆ 三族声明集（`_active` 除外，理由见下）。

        `_active` 属**生命周期层**：由 `Lifecycle.initialize` 的构造期初始写入与
        `deactivate` 的退役动作写入，而 `Lifecycle.state_keys()` 只声明 `triggers`
        （§3.1.3）；§3.13 的「生命周期」行给该键另设白名单（构造期初始写入 / 引擎
        激活传播 / 本保底退役动作），不在 S10-1 状态键行的覆盖范围内，故显式排除。

        **已登记的覆盖盲区**（2026-10-13）：排除 `_active` 后，**默认命名空间**下的
        `_active` 写入不再受任何限制性断言约束（零件命名空间下的由
        `test_part_namespace_writes_are_only_active` 管）。排除该键本身是必要的
        （`AlwaysActive` / `FiniteActive` 的 `initialize` 会往两个命名空间写
        `_active`，而 `state_keys()` 只声明 `triggers`），代价是「往默认命名空间写
        `_active`」这一形态不被本组断言拦截，此处登记备查。
        """
        run = _trace(combo)
        allowed = _declared_allowed(run)
        written = {key for ns, key in run.written if ns == combo.namespace}
        undeclared = sorted(written - allowed)
        assert not undeclared, (
            f'[{combo.label}] 运行期写入了未声明的状态键 {undeclared}；'
            f'声明集 {run.pity._declared_keys}')

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_part_namespace_writes_are_only_active(self, combo):
        """零件命名空间（`X_soft`）内只有生命周期层的 `_active`。

        `NamespaceTracker` 声明空键集（`state_keys()` 为 `()`，§3.1.1），该命名空间
        的 `_active` 由 `Lifecycle.initialize` 的推广作用域写入（ISSUE-407）；故
        除 `_active` 外的任何写入都属「写进未声明键」。
        """
        run = _trace(combo)
        foreign = {ns: sorted({k for n, k in run.written if n == ns} - {'_active'})
                   for ns in {n for n, _k in run.written} - {combo.namespace}}
        bad = {ns: keys for ns, keys in foreign.items() if keys}
        assert not bad, (
            f'[{combo.label}] 零件命名空间内出现非生命周期写入 {bad}')

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_inline_condition_read_keys_are_declared(self, combo):
        """内联条件的读键须出现在 `_declared_keys['modifiers']` 内（§六 的强制面）。

        条件内联后读键一律落在 Modifier 自己的 `state_keys()` 里（§3.14.2，一处
        声明），否则「条件只在 `apply()` 内读、不申报」的实现会让本不变式对条件
        全盲。`not_owned` / `soft` / `hard` 三类内联读 `counter`，本用例钉住它。
        """
        run = _trace(combo)
        declared_mods = set(run.pity._declared_keys['modifiers'])
        for part in combo.modifiers:
            expected = set(_MODIFIER_SPECS[part.key].declares)
            assert expected <= declared_mods, (
                f'[{combo.label}] Modifier {part.key!r} 的声明集 {sorted(expected)} '
                f'未全部出现在 _declared_keys["modifiers"] = {sorted(declared_mods)} 内')
        if any(p.key in ('soft', 'hard', 'not_owned') for p in combo.modifiers):
            assert 'counter' in declared_mods, (
                f'[{combo.label}] 内联读 counter 的 Modifier 未申报该键')

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_generated_combos_satisfy_combination_criteria(self, combo):
        """生成器守卫：随机组合须满足 §3.12.2 判据 1 / 2 的镜像（恒空）。

        非法组合的**构造期拒收**（抛 `ConfigError`）归 S10-2；本块只保证自己不把
        非法组合喂给不变式（否则「Modifier 引用不存在的键」会被当成不变式失败，
        归因方向完全相反）。
        """
        problems = _criteria_violations(combo.trackers, combo.modifiers)
        assert not problems, f'[{combo.label}] 生成了非法组合：{problems}'

    def test_criteria_mirror_rejects_conflicting_parts(self):
        """镜像谓词的非恒真自检（防「守卫恒真」）。

        三组各造一次：① 两个 `CounterTracker` 同写 `counter`；② `SoftModifier`
        读 `counter` 而无任何 Tracker 声明它；③ 白名单正例（`selected_card` 无零件
        声明，但不得被判为「引用不存在的键」）。
        """
        dup = [_Part('counter', CounterTracker(scope='ssr'), 'tracker',
                     ('counter',), ()),
               _Part('counter', CounterTracker(scope='ssr'), 'tracker',
                     ('counter',), ())]
        assert any('判据 1' in p for p in _criteria_violations(dup, [])), (
            '同键双 Tracker 未被镜像谓词拒收')

        orphan = [_Part('soft', SoftModifier('ssr', deltas=((1, 10.0),)),
                        'transfer', ('counter',), ('counter',), 'ssr')]
        assert any('判据 2' in p for p in _criteria_violations([], orphan)), (
            '读键无供给方的 Modifier 未被镜像谓词拒收')

        fate = [_Part('fate', FateTracker(scope='ssr', judge='selected',
                                          hit='clear', miss='accumulate',
                                          keys=('fate_points', 'losses',
                                                'guaranteed', 'lost_rotating')),
                    'tracker',
                    ('fate_points', 'losses', 'guaranteed', 'lost_rotating'), ())]
        selected = [_Part('selected', SelectedModifier('ssr'), 'transfer',
                          ('guaranteed', 'fate_points', 'selected_card'),
                          ('guaranteed', 'fate_points', 'selected_card'), 'ssr')]
        assert not _criteria_violations(fate, selected), (
            'selected_card 白名单失效：合法配置被判为非法')


# ══════════════════════════════════════════════════════════════════
# 十二、⑤ 确定性
# ══════════════════════════════════════════════════════════════════

class TestDeterminismInvariant:
    """§3.12.1 确定性行：「同种子 + 同配置 → 逐位相同」。"""

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_same_seed_same_pity_bit_identical(self, combo):
        """同 Pity 对象连跑两场（各带新账本、开工态取自初始快照）→ 逐位相同。

        这是 worker 内「同一 engine 连跑 N 场」的真实形态，也是「对象内计数跨模拟
        泄漏」这一缺陷型的观测面（零件对象在 worker 内复用）。**它不是该缺陷型的
        唯一观测面**：`_COMBOS` 在模块导入期生成一次、`_Part.instance` 被全文件
        共享，故 `test_same_seed_fresh_pity_bit_identical` 的「各自新建 Pity」同样
        复用同一批 Tracker 对象。实测（2026-10-13）：令 `CounterTracker.rebind`
        缓存一个跨场递增的计数后，本条 8 例失败、那条 7 例失败，两处一起变红。
        """
        first, second = _run_combo_twice_reusing_pity(combo)
        _assert_runs_identical(first, second, f'[{combo.label}] 同对象两场')

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_same_seed_fresh_pity_bit_identical(self, combo):
        """同种子、各自新建 Pity → 逐位相同（覆盖「同 type 两条保底不共享实例」面）。"""
        first = _run_combo(combo)
        second = _run_combo(combo)
        _assert_runs_identical(first, second, f'[{combo.label}] 新建两场')

    def test_streak_rng_consumed_and_seed_reproducible(self):
        """含随机源零件：固定奖励序列下同种子逐位相同，且确实消费了随机数。

        第二段断言使第一段非空转：`StreakTracker.prepare` 的掷骰走模块级
        `random.random()`（§3.1.1 的 H4 随机数消耗协议），若某次改造让它不再消费
        随机源，「同种子相同」会退化成恒真（本用例随之失败）。
        """
        combo = _FIXED_COMBOS['streak_rng']
        sequence = tuple(_step_of(combo.shape, card) for card in (
            'r_std', 'r_std', 'r_std', 'ssr_up', 'r_std', 'r_std', 'ssr_std', 'r_std',
            'r_std', 'sr_std', 'r_std', 'r_std', 'r_std', 'ssr_up', 'r_std', 'r_std'))

        def _run_with_count():
            log = _StepLog()
            pity, state, snapshot = _open_pity(combo, log)
            with _seeded_rng(combo.seed) as counted:
                run = _drive(pity, state, combo, log, draws=len(sequence),
                             snapshot=snapshot, sequence=sequence)
            return run, counted['n']

        first, first_calls = _run_with_count()
        second, second_calls = _run_with_count()
        assert first_calls > 0, (
            f'[{combo.label}] 本序列未消费任何随机数，「同种子相同」为空转')
        assert first_calls == second_calls, (
            f'[{combo.label}] 两次同种子运行的随机数消费次数不同：'
            f'{first_calls} vs {second_calls}')
        _assert_runs_identical(first, second, f'[{combo.label}] 固定序列两跑')


def _assert_runs_identical(first: _Run, second: _Run, where: str) -> None:
    """逐位比对两次运行的分布与抽后状态（不用 `approx`：同种子须逐位相同）。"""
    assert len(first.probs) == len(second.probs)
    for index, (a, b) in enumerate(zip(first.probs, second.probs)):
        assert a == b, (
            f'{where}：第 {index} 抽的分布不逐位相同\n  第一次 {a}\n  第二次 {b}')
    assert first.final_state == second.final_state, (
        f'{where}：抽后状态不逐位相同\n  第一次 {first.final_state}\n'
        f'  第二次 {second.final_state}')


# ══════════════════════════════════════════════════════════════════
# 十三、组合面覆盖 + 目录自检 + 退化组合（生成纪律 2 的正面覆盖）
# ══════════════════════════════════════════════════════════════════

class TestCombinationSpaceCoverage:
    """生成器守卫：组合面须真的覆盖三族与两种池形（防「不变式恒真」）。"""

    def test_space_covers_three_families_and_both_shapes(self):
        tracker_keys = {p.key for c in _COMBOS for p in c.trackers}
        modifier_keys = {p.key for c in _COMBOS for p in c.modifiers}
        lifecycle_keys = {c.lifecycle_key for c in _COMBOS}
        assert tracker_keys == set(_TRACKER_SPECS), (
            f'Tracker 目录未被组合面覆盖：缺 {set(_TRACKER_SPECS) - tracker_keys}')
        assert modifier_keys == set(_MODIFIER_SPECS), (
            f'Modifier 目录未被组合面覆盖：缺 {set(_MODIFIER_SPECS) - modifier_keys}')
        assert lifecycle_keys == set(_LIFECYCLE_SPECS), (
            f'Lifecycle 目录未被组合面覆盖：缺 {set(_LIFECYCLE_SPECS) - lifecycle_keys}')
        assert {c.shape.label for c in _COMBOS} == {s.label for s in SHAPES}, (
            '两种池形须都被覆盖')
        assert {c.scope for c in _COMBOS} == {'ssr', 'sr'}, (
            '触发稀有度须覆盖最高与次高')
        assert _COMBOS_WITH_F and _COMBOS_WITHOUT_F, 'F / 非 F 两个子面都须非空'
        assert any(c.has_f_part() and c.scope != 'ssr' for c in _COMBOS), (
            '须有「F 型 scope 低于最高稀有度」的组合（「更高稀有度逐位保留」的判别面）')
        assert any(s.kind == 'f' and s.fired
                   and _higher_rarity_cards(c.shape, c.scope)
                   for c in _COMBOS for s in _trace(c).steps()), (
            '须有「F 步实际触发且存在更高稀有度卡」的步，否则「更高稀有度逐位保留」'
            '的断言在组合面上无判别对象（该集合为空时它退化为恒真）')

    def test_declared_keys_aggregation_non_empty_across_space(self):
        """三族汇总在组合面上各自非空（§六：「断言须先证该汇总非空」）。"""
        for family, getter in (
            ('trackers', lambda c: _concat_declares(c.trackers)),
            ('modifiers', lambda c: _concat_declares(c.modifiers)),
            ('lifecycle', lambda c: _LIFECYCLE_SPECS[c.lifecycle_key].declares),
        ):
            hits = [c.label for c in _COMBOS
                    if getter(c) and _trace(c).pity._declared_keys[family]]
            assert hits, f'{family} 的声明集在组合面上恒空，状态键不变式恒真通过'

    def test_every_catalog_part_is_exercised_across_space(self):
        """每个目录零件在组合面上都**实际触发过**至少一步（防「装而不生效」）。

        这是五条不变式的**非空转守卫**：某个零件整场不触发时，它对应的不变式断言
        在该组合上恒真（例如 `seed111` 的 `selected`：条件未成立，整场未触发）。
        零件在单个组合里可以因边界条件（条件未成立 / 计数档位未达阈值）不触发，
        但不得在整个组合面上一次都不触发，否则那条不变式对该零件无判别力。
        **「目标集恒空」与「全部已拥有」不构成本文件的未触发原因**：全组合面扫描
        （2026-10-13）显示无零件因这两条路径不触发（组合面里唯一的 `not_owned`
        组合其 `owned` 为空集），详见模块 docstring 的生成纪律 3。
        """
        fired_keys = {s.part_key for c in _COMBOS for s in _trace(c).fired_steps()}
        missing = set(_MODIFIER_SPECS) - fired_keys
        assert not missing, (
            f'下列 Modifier 在整个组合面上从未触发，其不变式断言为空转：{sorted(missing)}')
        kinds = {s.kind for c in _COMBOS for s in _trace(c).fired_steps()}
        assert kinds == {'f', 'transfer'}, (
            f'F 型与转移族都须有触发的步，实测只有 {sorted(kinds)}')

    def test_catalog_metadata_matches_production_parts(self):
        """目录元数据自检：`declares` / `kind` 与生产类的真实成员同源。

        `kind == 'f'` 必须恰是 `HardModifier` / `NotOwnedModifier`（§3.1.2 的
        「绝对赋值 + 更高稀有度豁免」形态），否则归一性的分支选择会错。
        """
        rng = random.Random(0)
        for key, spec in _MODIFIER_SPECS.items():
            inst, kind, _concentrating = spec.factory(rng, 'ssr')
            assert tuple(inst.state_keys()) == spec.declares, (
                f'{key} 的 declares 元数据与 state_keys() 不符')
            if kind == 'f':
                assert isinstance(inst, (HardModifier, NotOwnedModifier)), (
                    f'{key} 标为 f 型却不是绝对赋值族')
            else:
                assert not isinstance(inst, (HardModifier, NotOwnedModifier)), (
                    f'{key} 标为转移族却是绝对赋值族')
        for key, spec in _TRACKER_SPECS.items():
            inst = spec.factory(rng, 'ssr', _PITY_NAME)
            assert tuple(inst.state_keys()) == spec.declares, (
                f'{key} 的 declares 元数据与 state_keys() 不符')
        for key, spec in _LIFECYCLE_SPECS.items():
            assert tuple(spec.factory().state_keys()) == spec.declares, (
                f'{key} 的 declares 元数据与 state_keys() 不符')


class TestConcentratingPairDegeneracy:
    """生成纪律 2 的正面覆盖：两个集中型 Modifier 串联时的**幂等**（更强断言）。

    **这不是推断，是本块实测到的现象**（2026-10-13：先按 §3.12.1 的字面式实现，
    随机组合跑红后定位到 `FlagTracker(guaranteed) + RotatingModifier +
    SelectedModifier` 单抽场景：第二步的 `dist_out == dist_in`、δ 全域为 0）。
    成因：两者目标集相同（同 scope 的 featured 槽集），第一步已把 scope 总量全部
    放到该槽集，第二步的「按声明权重重分配」于是成为恒等。

    故本类把该组合单独钉住（断言「串联输出 == 第一步输出」这一更强的等价性），
    不变式的字面式只在其非退化域内断言（生成纪律 2）。
    """

    def test_second_concentrating_step_is_idempotent(self):
        combo = _FIXED_COMBOS['concentrating_pair']
        run = _trace(combo)
        pairs = [s for s in run.steps() if s.part_key in ('rotating', 'selected')]
        assert len(pairs) >= 2, '本组合须含两个集中型 Modifier 的步'
        first, second = pairs[0], pairs[1]
        assert first.fired, '第一步须触发（否则无观测对象）'
        # **S8 起第二步是「不触发」**：第一步已把 scope 总量全部搬进目标集，第二步的
        # 源组（scope 内非目标卡）已归零 → `transfer_linear` 的 `p(Q) <= 0` 守卫命中、
        # 返回 `None`（恒等）。M1 期它算出的是一个**恒零的 δ**（「按声明权重重分配」
        # 在目标集已满时退化为恒等）：两者行为等价（都是恒等映射），S8 的形态更强：
        # 它不再需要「第二个零件的 δ 恰好恒零」这一额外解释（§3.9.5 的 `p(Q) == 0`
        # 行就是它的依据）。
        assert second.delta is None or all(v == 0.0 for v in second.delta.values()), (
            f'[{combo.label}] 第二步须为恒等（不触发或恒零 δ），实测 δ = {second.delta}')
        assert second.dist_out == first.dist_out, (
            f'[{combo.label}] 集中型串联的第二步须与第一步同分布（实测 '
            f'第一步 {first.dist_out}、第二步 {second.dist_out}）')

    def test_second_step_is_identity_everywhere(self):
        """第二步的恒等是**全域**的（不只支撑上）：δ 不触发或恒零，且输出 == 输入。"""
        combo = _FIXED_COMBOS['concentrating_pair']
        run = _trace(combo)
        pairs = [s for s in run.steps() if s.part_key in ('rotating', 'selected')]
        second = pairs[1]
        assert second.delta is None or all(v == 0.0 for v in second.delta.values()), (
            f'[{combo.label}] 第二步的 δ 须不触发或全域为 0，实测 {second.delta}')
        assert second.dist_out == second.dist_in, (
            f'[{combo.label}] 第二步须是恒等映射，实测 {second.dist_in} → {second.dist_out}')


# ══════════════════════════════════════════════════════════════════
# 十四、定点组合（非随机，供上面几条用例指名使用）
# ══════════════════════════════════════════════════════════════════

def _stable_seed(label: str) -> int:
    """标签 → 构造种子。**不得用内置 `hash()`**（字符串哈希逐进程随机化）。"""
    return sum(ord(ch) for ch in label) * 7919


def _fixed_combo(label: str, *, shape: _Shape, scope: str,
                 trackers, modifiers, lifecycle_key: str = 'always',
                 flags=None, counters=None, selected_card=None,
                 owned=()) -> _Combo:
    """按显式零件拼一个定点组合（种子表之外，供定点用例使用）。

    `trackers` / `modifiers` 为 `(目录键, 零件实例)` 二元组的序列，故定点组合的
    构造形参（如 `HardModifier` 的 `target`）不受目录工厂的随机取值影响。
    """
    tracker_parts = tuple(
        _Part(key, inst, 'tracker', _TRACKER_SPECS[key].declares, ())
        for key, inst in trackers)
    modifier_parts = []
    for key, inst in modifiers:
        spec = _MODIFIER_SPECS[key]
        kind = 'f' if isinstance(inst, (HardModifier, NotOwnedModifier)) else 'transfer'
        modifier_parts.append(
            _Part(key, inst, kind, spec.declares, spec.reads, scope))
    return _Combo(
        seed=-1, shape=shape, scope=scope, trackers=tracker_parts,
        modifiers=tuple(modifier_parts), lifecycle_key=lifecycle_key,
        lifecycle=_LIFECYCLE_SPECS[lifecycle_key].factory(),
        flags=dict(flags or {}), counters=dict(counters or {}),
        selected_card=selected_card, owned=tuple(owned),
        btype='hard' if any(p.kind == 'f' for p in modifier_parts) else 'soft_step',
        label=label,
    )


_FIXED_COMBOS: Dict[str, _Combo] = {
    # §3.12.1 实测形态的定点组合：hard 的 scope 低于最高稀有度（sr < ssr），
    # 且 `target='scope'`（`target='featured'` 在标准池形下 sr 无 featured 卡、
    # 目标集为空即恒不触发，观测不到 scope 感知式）。
    'hard_below_top': _fixed_combo(
        'hard_below_top', shape=STANDARD_SHAPE, scope='sr',
        trackers=[('counter', CounterTracker(scope='sr', reset_on='sr'))],
        modifiers=[('hard', HardModifier('sr', threshold=3, target='scope'))]),
    # 随机源零件的定点组合（含 rotating_cr 与 streak，供 RNG 计数用例）。
    'streak_rng': _fixed_combo(
        'streak_rng', shape=STANDARD_SHAPE, scope='ssr',
        trackers=[('streak', StreakTracker(scope='ssr', judge='featured',
                                           threshold=3, base_rate=0.05,
                                           state_probs=[0.0, 0.0, 0.5, 1.0],
                                           flag='cr_intercepted',
                                           guard_flag='guaranteed')),
                  ('flag_guaranteed', FlagTracker('ssr', 'featured', 'clear',
                                                  'set', 'guaranteed')),
                  ('counter', CounterTracker(scope='ssr', reset_on='ssr'))],
        modifiers=[('rotating_cr', RotatingModifier('ssr',
                                                    extra_flag='cr_intercepted'))]),
    # 集中型串联（生成纪律 2 的正面覆盖）：guaranteed 初始置位，两步同抽触发。
    # Tracker 取 `fate` 一者：它同时声明 `guaranteed` 与 `fate_points`，故与
    # `selected` 的读键集相容（再加 `flag_guaranteed` 会与它重复声明 `guaranteed`）。
    'concentrating_pair': _fixed_combo(
        'concentrating_pair', shape=STANDARD_SHAPE, scope='ssr',
        trackers=[('fate', FateTracker(scope='ssr', judge='selected', hit='clear',
                                       miss='accumulate',
                                       keys=('fate_points', 'losses',
                                             'guaranteed', 'lost_rotating')))],
        modifiers=[('rotating', RotatingModifier('ssr')),
                   ('selected', SelectedModifier('ssr', tau=1))],
        flags={'guaranteed': True}, counters={'fate_points': 0},
        selected_card='ssr_up'),
}


# ══════════════════════════════════════════════════════════════════
# 十四、S10-2：三条合法组合判据的构造期拒收（§3.12.2）
# ══════════════════════════════════════════════════════════════════
#
# 本段是 S10-2 的用例面（与 S10-1 同文件、按 `-k "illegal or cycle"` 过滤）。
# 三条判据的**检查本体**落在生产代码：判据 1 / 判据 2 在 `Pity.__init__`
# （`_check_declared_keys`，输入是 `Pity._declared_keys`，ISSUE-501），判据 3
# （`depends_on` 成环）在 `PityEngine._build_activation_graph`。三者一律抛
# `ConfigError`（配置错误），**不是** `ValueError`。
#
# **命名约束（GATE-6 测试策略）**：验收命令的过滤词 `illegal` / `cycle` 必须落在
# 用例名内，且命中项**恰好三条**。故承载本段的类名与同文件其他类名一律不含
# 这两个词（`-k` 是子串匹配、且匹配面含类名与模块名），否则会连带命中无关用例。
# S10-2 收口补入的用例同样避开这两个词（命名时另须避开 `lifecycle`，它是 `cycle`
# 的子串），使过滤词命中数仍为三条。
#
# **「不可写」的理由只适用判据 1 / 2（S10-2 审查 F5 收窄）**：`PityEngine.__init__`
# 只收 `PityDef` 并经 `create_behavior` 的 preset 分支造零件，零件键集由 btype 固定、
# 不受用例摆布（实测 11 个 btype 的默认 `PityDef` 全数产出合法组合：无重复 Tracker
# 键、无未知 Modifier 键），故判据 1 / 2 的**引擎层负例写不出**，只能直构 `Pity`。
# 判据 3 的引擎层负例**可写**（两个 `PityDef` 的 `depends_on` 互指即在引擎路径抛
# `ConfigError`），见本类的 `test_cycle_depends_on`。

class _TypoKeyModifier(Modifier):
    """键名拼错的 Modifier：`state_keys()` 申报一个不存在的键 `'countr'`。

    生产零件的键集由构造形参固定，拼错只在**新写的** Modifier 里出现，故本用例
    以桩件复现该形态（§3.13 的状态层判据正是为「把 `'counter'` 拼成 `'countr'`」
    这类静默失效设的）。
    """

    def state_keys(self):
        return ('countr',)


class _TriggersKeyModifier(Modifier):
    """读 Lifecycle 声明键 `triggers` 的 Modifier 桩件（判据 2 并集的 lifecycle 半边）。

    生产 Modifier 无一读该键（全库仅 `Finite*` 生命周期声明它），故这一半边只能
    以桩件复现。桩件只申报声明集、不参与 `apply`（本用例只走构造期）。
    """

    def state_keys(self):
        return ('triggers',)


class TestCombinationCriteriaConstruction:
    """§3.12.2 三条判据各一条负例，均在**构造期**抛 `ConfigError`。"""

    def test_illegal_duplicate_key_across_trackers(self):
        """判据 1：同一键被两个 Tracker 声明（§3.12.2 第 1 条）。

        两个 `CounterTracker` 都写 `counter`：后写者覆盖先写者的计数，而读取侧
        只看到一个值、**不报错**。检查点是 `Pity.__init__`（数据是 per-Pity 的）。
        """
        with pytest.raises(ConfigError, match='重复键'):
            Pity(
                name=_PITY_NAME, state=PityState(), scope='ssr',
                btype='soft_step',
                trackers=[CounterTracker(scope='ssr', init=0),
                          CounterTracker(scope='ssr', init=0)],
                modifiers=[SoftModifier('ssr', deltas=((2, 0.0), (3, 30.0)))],
            )

    def test_illegal_unknown_key_in_modifier(self):
        """判据 2：Modifier 引用不存在的状态键（§3.12.2 第 2 条）。

        「存在」的口径 = Tracker ∪ Lifecycle 的 `state_keys()` 并集（另加
        `selected_card` 白名单）。比对集是 Modifier **自己**的声明集，故两形态
        都在此被拦下：① 生产零件的读键无供给方；② 键名拼错（`'countr'`）。
        """
        # ① 生产零件：`SoftModifier` 读 `counter`，而本保底无任何 Tracker 声明它
        with pytest.raises(ConfigError, match='不存在的状态键'):
            Pity(
                name=_PITY_NAME, state=PityState(), scope='ssr',
                btype='soft_step',
                trackers=[],
                modifiers=[SoftModifier('ssr', deltas=((2, 0.0), (3, 30.0)))],
            )

        # ② 键名拼错：`counter` 有供给方，仅申报名错一格（`'countr'`）
        with pytest.raises(ConfigError, match='不存在的状态键'):
            Pity(
                name=_PITY_NAME, state=PityState(), scope='ssr',
                btype='soft_step',
                trackers=[CounterTracker(scope='ssr', init=0)],
                modifiers=[_TypoKeyModifier()],
            )

    def test_cycle_depends_on(self):
        """判据 3：`depends_on` 成环（§3.12.2 第 3 条，**新增能力**）。

        本块之前 `_build_activation_graph` 只校验「指向的名字存在」，不做环检测，
        故互依配置被静默接受。两个 `PityDef` 的 `btype` 取不同值，使
        `_validate_behaviors` 的规则 4（同 scope 同 btype 双 soft）不先抛错，
        从而把抛错归因钉死在成环检测上。
        """
        def _engine(defs):
            return PityEngine(pool_specs={}, pity_defs=defs, state=PityState(),
                              rarity_rank={'ssr': 0})

        with pytest.raises(ConfigError, match='成环'):
            _engine([
                PityDef(name='cyc_a', btype='soft_interval', scope='ssr',
                        soft_start=73, soft_end=90, depends_on='cyc_b'),
                PityDef(name='cyc_b', btype='soft_additive', scope='ssr',
                        soft_start=70, soft_increment=6, depends_on='cyc_a'),
            ])

        # 自环（`A depends_on A`）同属此列
        with pytest.raises(ConfigError, match='成环'):
            _engine([PityDef(name='cyc_self', btype='soft_interval', scope='ssr',
                             soft_start=73, soft_end=90, depends_on='cyc_self')])

        # 非恒真守卫：无环的依赖链**不得**被判为成环（否则「检出成环」这一半
        # 无法与「一律拒收 depends_on」区分）
        engine = _engine([
            PityDef(name='cyc_src', btype='soft_interval', scope='ssr',
                    soft_start=73, soft_end=90),
            PityDef(name='cyc_dst', btype='soft_additive', scope='ssr',
                    soft_start=70, soft_increment=6, depends_on='cyc_src'),
        ])
        assert engine._activation_graph == {'cyc_src': ['cyc_dst']}

    def test_rejected_combination_leaves_state_untouched(self):
        """检查点次序：判据抛错时 state 必须**一位未写**（S10-2 审查 F2 护栏）。

        判据 1 / 2 在 `Pity.__init__` 里的位置须在 `self._lifecycle.initialize`
        **之前**：`initialize` 会往 `state` 写初始 `_active`，次序颠倒则非法组合
        留下半写的 state（后续复用同一 state 的路径会读到一条已被拒的保底的残留）。
        故本用例对**拒收后的 state** 逐位断言为空，并把合法组合的对照一并写出
        （证明「空」是次序之功，而非 `initialize` 根本不写）。
        """
        state = PityState()
        with pytest.raises(ConfigError, match='重复键'):
            Pity(
                name=_PITY_NAME, state=state, scope='ssr',
                btype='soft_step',
                trackers=[CounterTracker(scope='ssr', init=0),
                          CounterTracker(scope='ssr', init=0)],
                modifiers=[SoftModifier('ssr', deltas=((2, 0.0), (3, 30.0)))],
            )
        assert state.to_dict()['data'] == {}, (
            f'判据 1 拒收后 state 仍被写入：{state.to_dict()}')

        state2 = PityState()
        with pytest.raises(ConfigError, match='不存在的状态键'):
            Pity(
                name=_PITY_NAME, state=state2, scope='ssr',
                btype='soft_step',
                trackers=[],
                modifiers=[SoftModifier('ssr', deltas=((2, 0.0), (3, 30.0)))],
            )
        assert state2.to_dict()['data'] == {}, (
            f'判据 2 拒收后 state 仍被写入：{state2.to_dict()}')

        # 对照：同一形态去掉非法项后，`initialize` 必写 `_active`
        legal = PityState()
        Pity(
            name=_PITY_NAME, state=legal, scope='ssr', btype='soft_step',
            trackers=[CounterTracker(scope='ssr', init=0)],
            modifiers=[SoftModifier('ssr', deltas=((2, 0.0), (3, 30.0)))],
        )
        assert legal.to_dict()['data'] == {_PITY_NAME: {'_active': True}}, (
            f'合法组合的初始 state 形状变了：{legal.to_dict()}')

    def test_finite_activation_declared_key_accepted(self):
        """判据 2 的「存在」口径含 Lifecycle 半边（§3.12.2 原文，S10-2 审查 F3）。

        `FiniteActive(max_triggers=2)` 声明 `('triggers',)`，而**无任何 Tracker**
        声明它，故读它的 Modifier 仅在「Tracker ∪ Lifecycle」口径下合法；把并集里
        的 `set(declared_keys['lifecycle'])` 换成 `set()` 则本用例的正例必红。
        `AlwaysActive`（不声明）一侧作为反向对照，证明上面的通过不是「判据 2 不查」。
        """
        def _build(lifecycle):
            return Pity(
                name=_PITY_NAME, state=PityState(), scope='ssr',
                btype='soft_step',
                trackers=[CounterTracker(scope='ssr', init=0)],
                modifiers=[SoftModifier('ssr', deltas=((2, 0.0), (3, 30.0))),
                           _TriggersKeyModifier()],
                lifecycle=lifecycle,
            )

        assert _build(FiniteActive(max_triggers=2)) is not None, (
            '声明 `triggers` 的生命周期未能供给 Modifier 的读键')

        with pytest.raises(ConfigError, match='不存在的状态键'):
            _build(AlwaysActive())

    def test_criteria_whitelist_content(self):
        """判据 2 的白名单内容等值断言（S10-2 审查 F4）。

        白名单是判据 2 的**放行面**：多一个键即多一条「无声明方的读键被放行」的
        缝隙（审查探针 K1：塞入 `bogus_unused` 后声明该键的 Modifier 被静默
        ACCEPT，属非法形态漏过）；反之清空则 `targeted` / `targeted_soft` 的全部
        合法配置被误杀。故内容与「非空」一并钉住，将来误加键即红。
        """
        assert _EXTERNAL_STATE_KEYS == frozenset({'selected_card'}), (
            f'判据 2 的白名单内容已变：{sorted(_EXTERNAL_STATE_KEYS)}')
