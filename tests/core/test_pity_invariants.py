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

## 归一性的口径随里程碑切换（ISSUE-903，后手改造者必读）

本文件按 **M1 槽位级管道** 的 **scope 感知式**实现：
`Σp = 1 + Σp(被 F 豁免的更高稀有度槽位)`，无 F 参与时退化为 `Σp = 1`
（判据出处：§3.12.1 的归一性行 + §3.13 的分布层行；实测形态见 §3.12.1 的
`hard(scope='sr')` 例，输出 `{ssr: 0.006, ssr_featured: 0.003, sr: 1.0, r: 0.0}`、
Σ = 1.009，即「目标集绝对赋值到 1.0 + 更高稀有度槽位原值保留」）。

**自 S8 起** `_apply_delta`（§3.9.2）无条件归一化，且转移族恒有 `Σδ = 0` 使其
退化为恒等，故 S8 起恒有 `Σp ≡ 1`（§3.9.5 的 `Σ(p + δ) ≠ 1` 行）。届时本文件
**三处**断言须按 `Σp = 1` 改写（改写点登记在 M2 的 S8-6 ⑤）：

1. `TestNormalizationInvariant.test_step_total_scope_aware_for_f_part`
2. `TestNormalizationInvariant.test_pipeline_total_equals_last_f_step_exemption`
3. `TestNormalizationInvariant.test_hard_below_top_rarity_scope_aware_shape`

（`test_transfer_step_preserves_total` 与 `test_pipeline_total_is_one_without_f_part`
在 S8 后仍然成立，不需改写。）

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
   边界），组合面会退化成「装了零件但从不生效」；空目标集这一边界本身仍由
   `seed101` 那类组合覆盖。该纪律只改池形，不改零件参数。

**该「δ 恒零」是实测而非推断**（2026-10-13）：先按 §3.12.1 的字面式实现，随机
组合跑红后定位到 `FlagTracker(guaranteed) + RotatingModifier + SelectedModifier`
单抽场景（第二步 `dist_out == dist_in`、δ 全域为 0）；定位过程与处置见
`TestConcentratingPairDegeneracy` 的 docstring。

## Σ 式对「豁免被整体去掉」不敏感（本块的实测发现）

§3.12.1 的 `Σp = 1 + Σp(被 F 豁免的更高稀有度槽位)` 的右侧取自**输出**分布，故把
F 步的豁免整个删掉（豁免槽位归零）会让两侧同时减到 1、该式照样成立。实测
（2026-10-13）：删掉 `HardModifier.apply` 的豁免循环后，该式在含 `hard(scope='sr')`
的随机组合上仍全绿。故本文件在该式之外并列一条
`test_f_step_exemption_keeps_original_values`（豁免槽位逐位保留原值，即 §3.12.1
所引 §3.1.5.2 的「更高稀有度槽位还原原值」），两条合起来才对 F 语义有判别力。
该结构式在 S8 后依然成立（§3.9.5：增量形式下「U 外的卡逐位不变」），故它**不在**
上面那三处待改写点内。


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

from gacha_simulator.core.pity import Pity
from gacha_simulator.core.pity_modifier import (
    HardModifier,
    NonFeaturedModifier,
    NotOwnedModifier,
    RotatingModifier,
    SelectedModifier,
    SoftModifier,
    _higher_rarity_keys,
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
    """一个池子的槽位映射 + 基础分布（`DrawInfo` 的全部映射齐备）。

    `slot_to_card` 是本文件新增的**抽样反查表**：驱动层从调整后的分布抽一个槽位，
    再反查代表卡作为本次奖励（与「先定分布、再抽奖励」的引擎同形）。
    """

    label: str
    rarity_rank: Dict[str, int]
    scope_cards: Dict[str, tuple]
    featured_cards: Dict[str, tuple]
    scope_slots: Dict[str, tuple]
    featured_slots: Dict[str, tuple]
    card_to_slot: Dict[str, str]
    slot_to_card: Dict[str, str]
    base: Dict[str, float]


#: 标准池形（与 `tests/core/test_pity_modifier.py` 的夹具同形，即
#: `compute_scope_mappings` 对「只有 ssr 有 featured 卡」的池子的真实产出：
#: 无 featured 卡的稀有度其 `featured_slots[r] == (r,)`）。
STANDARD_SHAPE = _Shape(
    label='std',
    rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
    scope_cards={'ssr': ('ssr_up', 'ssr_std'), 'sr': ('sr_std',), 'r': ('r_std',)},
    featured_cards={'ssr': ('ssr_up',)},
    scope_slots={'ssr': ('ssr', 'ssr_featured'), 'sr': ('sr',), 'r': ('r',)},
    featured_slots={'ssr': ('ssr_featured',), 'sr': ('sr',), 'r': ('r',)},
    card_to_slot={'ssr_up': 'ssr_featured', 'ssr_std': 'ssr',
                  'sr_std': 'sr', 'r_std': 'r'},
    slot_to_card={'ssr_featured': 'ssr_up', 'ssr': 'ssr_std',
                  'sr': 'sr_std', 'r': 'r_std'},
    base={'ssr_featured': 0.006, 'ssr': 0.004, 'sr': 0.05, 'r': 0.94},
)

#: 宽池形：`sr` 也有 featured 卡（`compute_scope_mappings` 对「两级都有 UP」的池子
#: 的产出）。它使 `sr` 上的三个目标集语义 Modifier 与 `hard(target='featured')`
#: 从「恒不触发」变为可触发，是组合面覆盖的必要一支。
WIDE_SHAPE = _Shape(
    label='wide',
    rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
    scope_cards={'ssr': ('ssr_up', 'ssr_std'), 'sr': ('sr_up', 'sr_std'),
                 'r': ('r_std',)},
    featured_cards={'ssr': ('ssr_up',), 'sr': ('sr_up',)},
    scope_slots={'ssr': ('ssr', 'ssr_featured'), 'sr': ('sr', 'sr_featured'),
                 'r': ('r',)},
    featured_slots={'ssr': ('ssr_featured',), 'sr': ('sr_featured',), 'r': ('r',)},
    card_to_slot={'ssr_up': 'ssr_featured', 'ssr_std': 'ssr',
                  'sr_up': 'sr_featured', 'sr_std': 'sr', 'r_std': 'r'},
    slot_to_card={'ssr_featured': 'ssr_up', 'ssr': 'ssr_std',
                  'sr_featured': 'sr_up', 'sr': 'sr_std', 'r': 'r_std'},
    base={'ssr_featured': 0.006, 'ssr': 0.004, 'sr_featured': 0.01, 'sr': 0.04,
          'r': 0.94},
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
    """一次 Modifier 应用的观测记录（δ 与归一性的观测面）。"""

    draw_index: int
    part_key: str
    kind: str                 # 'f'（绝对赋值 + 豁免）/ 'transfer'（转移族）
    scope: str
    dist_in: Dict[str, float]
    dist_out: Optional[Dict[str, float]]   # None = 本次未触发（`apply` 返回 None）
    exempted: Tuple[str, ...]              # F 型豁免的更高稀有度槽位（仅 'f' 步非空）

    @property
    def fired(self) -> bool:
        return self.dist_out is not None

    def delta(self) -> Dict[str, float]:
        """δ = 输出 − 输入（未触发的步须先查 `fired` 再调用）。"""
        out = self.dist_out or {}
        return {k: out.get(k, 0.0) - self.dist_in.get(k, 0.0)
                for k in set(self.dist_in) | set(out)}


class _StepLog:
    """逐步观测的载体（`_Recorder` 写入，驱动层按抽切分）。"""

    def __init__(self):
        self.draw_index = -1
        self.steps: List[_Step] = []


class _Recorder:
    """Modifier 的 1:1 委派包装，唯一作用是记录每步的输入 / 输出分布。

    **不改行为**：`Pity` 消费的四个成员（`apply` / `rebind` / `state_keys` /
    `namespace`）一律直转发，`inner` 供断言取真实零件。故 `Pity._declared_keys` /
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

    def apply(self, ctx, view, dist, readonly):
        out = self.inner.apply(ctx, view, dist, readonly)
        self._log.steps.append(_Step(
            draw_index=self._log.draw_index,
            part_key=self._part.key,
            kind=self._part.kind,
            scope=self._part.scope,
            dist_in=dict(dist),
            dist_out=None if out is None else dict(out),
            exempted=(_higher_rarity_keys(ctx, self._part.scope)
                      if self._part.kind == 'f' else ()),
        ))
        return out


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
    #    宽池形。空目标集这一边界本身仍由 `seed101` 那类组合覆盖（`hard` 不在此列：
    #    它的 `target='scope'` 形态目标集是 scope 全卡集，与本纪律无关）。
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
        scope_slots=shape.scope_slots, featured_slots=shape.featured_slots,
        card_to_slot=shape.card_to_slot,
        base_probabilities=dict(shape.base) if step is None else {},
        rarity_rank=shape.rarity_rank,
    )
    ctx = PityContext(
        draw=draw, current=dict(shape.base) if step is None else {}, state=state)
    ctx.sim = sim
    return ctx


def _step_of(shape: _Shape, slot: str) -> _DrawStep:
    """槽位 → 奖励事实（稀有度取槽位名前缀，featured 由槽位名后缀判定）。"""
    return _DrawStep(
        card=shape.slot_to_card[slot],
        rarity=slot.split('_')[0],
        is_featured=slot.endswith('_featured'),
    )


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
    `selected_card` 白名单内（本文件的组合无 lifecycle 声明键，故并集的另一半恒空）。

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

def _total(dist: Dict[str, float]) -> float:
    return sum(dist.values())


def _exempted_mass(dist: Dict[str, float], exempted) -> float:
    """被 F 豁免的更高稀有度槽位上的概率和（scope 感知式的加项）。"""
    return sum(dist.get(k, 0.0) for k in exempted)


def _assert_scope_aware_total(dist: Dict[str, float], exempted, where: str) -> None:
    """§3.12.1 归一性：`Σp = 1 + Σp(被 F 豁免的更高稀有度槽位)`（容差 1e-12）。"""
    expected = 1.0 + _exempted_mass(dist, exempted)
    assert abs(_total(dist) - expected) <= TOL, (
        f'{where}：Σp = {_total(dist)!r}，期望 {expected!r}'
        f'（1 + 豁免槽位 {list(exempted)} 上的 {_exempted_mass(dist, exempted)!r}）')


def _assert_total_is_one(dist: Dict[str, float], where: str) -> None:
    """无 F 参与时的退化式：`Σp = 1`（容差 1e-12）。"""
    assert abs(_total(dist) - 1.0) <= TOL, (
        f'{where}：Σp = {_total(dist)!r}，期望 1.0（无 F 型参与，退化式）')


def _declared_allowed(run: _Run) -> set:
    """三族声明集的并集 + `_active`（生命周期层的键，见状态键用例的 docstring）。"""
    declared = run.pity._declared_keys
    return (set(declared['trackers']) | set(declared['modifiers'])
            | set(declared['lifecycle']) | {'_active'})


# ══════════════════════════════════════════════════════════════════
# 八、① 归一性
# ══════════════════════════════════════════════════════════════════

class TestNormalizationInvariant:
    """§3.12.1 归一性行 + §3.13 分布层行的 scope 感知式（M1 口径，见模块 docstring）。"""

    @pytest.mark.parametrize('combo', _COMBOS_WITH_F, ids=_IDS_WITH_F)
    def test_step_total_scope_aware_for_f_part(self, combo):
        """F 型（hard / not_owned）步：`Σp = 1 + Σp(豁免槽位)`。

        §3.12.1 的例外条即此处：F 语义是「全池置零 + 更高稀有度槽位还原原值」，
        故 scope 低于最高稀有度时输出 Σ > 1。
        """
        run = _trace(combo)
        for step in [s for s in run.fired_steps() if s.kind == 'f']:
            _assert_scope_aware_total(
                step.dist_out, step.exempted,
                f'[{combo.label}] 第 {step.draw_index} 抽的 {step.part_key} 步')

    @pytest.mark.parametrize('combo', _COMBOS, ids=_IDS_ALL)
    def test_transfer_step_preserves_total(self, combo):
        """转移族步：`Σδ = 0`（总量守恒）。

        §3.9.2 的「因转移族恒有 `Σδ = 0`」是本式的出处；它也是 scope 感知式能从
        F 步传播到管道末端的载体（soft / rotating / non_featured / selected 四类
        只在 scope 内重分配，scope 外原值保留）。
        """
        run = _trace(combo)
        for step in run.fired_steps():
            if step.kind == 'f':
                continue
            before, after = _total(step.dist_in), _total(step.dist_out)
            assert abs(after - before) <= TOL, (
                f'[{combo.label}] 第 {step.draw_index} 抽的 {step.part_key} 步：'
                f'Σ 由 {before!r} 变为 {after!r}（转移族须守恒）')

    @pytest.mark.parametrize('combo', _COMBOS_WITH_F, ids=_IDS_WITH_F)
    def test_f_step_exemption_keeps_original_values(self, combo):
        """F 步的豁免槽位**逐位保留原值**（§3.12.1 的「更高稀有度槽位还原原值」）。

        **为什么该式必须与 Σ 式并存**：Σ 式的右侧 `Σp(豁免槽位)` 取自**输出**分布，
        故「豁免被整体去掉」（豁免槽位归零）会让两侧同时减到 1、Σ 式照样成立。实测
        （2026-10-13）：删掉 `HardModifier.apply` 的豁免循环后，Σ 式在含
        `hard(scope='sr')` 的随机组合上**仍全绿**，只有本条与
        `test_hard_below_top_rarity_scope_aware_shape` 变红。判别该破坏的是本式。
        """
        run = _trace(combo)
        for step in [s for s in run.fired_steps() if s.kind == 'f']:
            for key in step.exempted:
                assert step.dist_out[key] == step.dist_in[key], (
                    f'[{combo.label}] 第 {step.draw_index} 抽的 {step.part_key} 步：'
                    f'豁免槽位 {key!r} 须保留原值 {step.dist_in[key]!r}，'
                    f'实测 {step.dist_out[key]!r}')

    @pytest.mark.parametrize('combo', _COMBOS_WITHOUT_F, ids=_IDS_WITHOUT_F)
    def test_pipeline_total_is_one_without_f_part(self, combo):
        """无 F 型参与时退化为 `Σp = 1`（§3.12.1 的「无 F 参与时退化为」半句）。"""
        run = _trace(combo)
        for index, dist in enumerate(run.probs):
            _assert_total_is_one(dist, f'[{combo.label}] 第 {index} 抽的管道输出')

    @pytest.mark.parametrize('combo', _COMBOS_WITH_F, ids=_IDS_WITH_F)
    def test_pipeline_total_equals_last_f_step_exemption(self, combo):
        """含 F 型时的管道口径：`Σ(管道输出) = 1 + Σ(最后一次 F 步的豁免槽位值)`。

        依据：F 步把非豁免侧归一到 1.0、豁免槽位原值保留，此后每一步转移都守恒
        （上一条），故管道输出 Σ 等于「最后一次 F 步那一刻」的 `1 + Σp(豁免槽位)`。
        **适用边界**：F 步之后若再有转移改写豁免槽位的值，最终分布本身不再满足
        scope 感知式（§3.12.1 的实测例是单个 `hard(scope='sr')`），故本式以「F 步
        那一刻的分布」为基准，而不是以最终分布为基准。
        """
        run = _trace(combo)
        for index, dist in enumerate(run.probs):
            fired_f = [s for s in run.steps_by_draw[index]
                       if s.kind == 'f' and s.fired]
            if not fired_f:
                _assert_total_is_one(dist, f'[{combo.label}] 第 {index} 抽（F 未触发）')
                continue
            last = fired_f[-1]
            expected = 1.0 + _exempted_mass(last.dist_out, last.exempted)
            assert abs(_total(dist) - expected) <= TOL, (
                f'[{combo.label}] 第 {index} 抽：管道 Σ = {_total(dist)!r}，'
                f'期望 {expected!r}（最后一次 F 步为 {last.part_key}，'
                f'豁免槽位 {list(last.exempted)}）')

    def test_hard_below_top_rarity_scope_aware_shape(self):
        """§3.12.1 实测形态的定点用例：`hard(scope='sr')` 输出 Σ = 1 + p(ssr 槽位) > 1。

        与 §3.12.1 的实测例同形（该例给 `{ssr: 0.006, ssr_featured: 0.003, sr: 1.0,
        r: 0.0}`、Σ = 1.009），本用例的池形与基础分布取 `STANDARD_SHAPE`，故具体
        数值不同、**结构相同**：目标集（sr）绝对赋值到 1.0、更低稀有度（r）归零、
        更高稀有度（ssr 两槽）原值保留。
        """
        combo = _FIXED_COMBOS['hard_below_top']
        run = _trace(combo)
        fired = [s for s in run.fired_steps() if s.kind == 'f']
        assert fired, 'hard(scope=sr) 须在本序列内触发（否则本用例无观测对象）'
        step = fired[0]
        dist = step.dist_out
        exempted = set(step.exempted)
        assert exempted == {'ssr', 'ssr_featured'}, (
            f'豁免槽位须为 ssr 的两槽，实测 {sorted(exempted)}')
        _assert_scope_aware_total(dist, step.exempted, '[hard_below_top]')
        assert _total(dist) > 1.0, 'scope 低于最高稀有度时 Σ 必大于 1'
        # 本组合只有 hard 一个 Modifier，故该步输出即**管道输出**：scope 感知式在
        # 「无后续转移改写豁免槽位」这一域内对管道输出本身成立。
        _assert_scope_aware_total(run.probs[step.draw_index], step.exempted,
                                  '[hard_below_top] 管道输出')
        for key in exempted:
            assert dist[key] == combo.shape.base[key], (
                f'豁免槽位 {key} 须保留原值 {combo.shape.base[key]!r}，'
                f'实测 {dist[key]!r}')
        assert dist['sr'] == pytest.approx(1.0, abs=TOL), 'sr 目标集绝对赋值到 1.0'
        assert dist['r'] == pytest.approx(0.0, abs=TOL), '更低稀有度须被搬空'


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
            delta = step.delta()
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
            delta = step.delta()
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
        泄漏」这一缺陷型的唯一观测面（零件对象在 worker 内复用）。
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
        sequence = tuple(_step_of(combo.shape, slot) for slot in (
            'r', 'r', 'r', 'ssr_featured', 'r', 'r', 'ssr', 'r',
            'r', 'sr', 'r', 'r', 'r', 'ssr_featured', 'r', 'r'))

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
            '须有「F 型 scope 低于最高稀有度」的组合（scope 感知式的判别面）')
        assert any(s.kind == 'f' and s.fired and s.exempted
                   for c in _COMBOS for s in _trace(c).steps()), (
            '须有「F 步实际触发且豁免集非空」的步，否则 scope 感知式的加项恒为 0、'
            '与退化式 Σp = 1 无判别差异')

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
        在该组合上恒真（例如目标集恒空的 `not_owned`）。零件在单个组合里可以因
        边界条件（空目标集 / 阈值未达 / 全部已拥有）不触发，但不得在整个组合面上
        一次都不触发，否则那条不变式对该零件无判别力。
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
        assert first.fired and second.fired, '两步都须触发（否则无观测对象）'
        assert second.dist_out == first.dist_out, (
            f'[{combo.label}] 集中型串联的第二步须与第一步同分布（实测 '
            f'第一步 {first.dist_out}、第二步 {second.dist_out}）')
        support = [k for k, v in second.dist_in.items() if v > 0.0]
        assert all(second.delta().get(k, 0.0) == 0.0 for k in support), (
            '第二步的 δ 在支撑上恒为 0（这正是生成纪律 2 的实测依据）')

    def test_second_step_delta_is_zero_everywhere(self):
        """δ 恒零是**全域**的（不只支撑上）：该步确为恒等映射。"""
        combo = _FIXED_COMBOS['concentrating_pair']
        run = _trace(combo)
        pairs = [s for s in run.steps() if s.part_key in ('rotating', 'selected')]
        second = pairs[1]
        assert all(v == 0.0 for v in second.delta().values()), (
            f'[{combo.label}] 第二步的 δ 须全域为 0，实测 {second.delta()}')


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
