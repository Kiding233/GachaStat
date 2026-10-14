"""P64 S5a：等价性测试骨架（旧类 vs 新统一骨架，固定种子逐场对比）。

本文件是 §七 S5a / S5b / S5c 三块的共同落点。S5a 只交付**装置**与自检；
逐类型等价性批次（S5b）与三条强制约束的专项断言（S5c）在此文件上叠加。
S5b 分两批接入（§七 S5b 的分批纪律）：批次一 = counter 驱动 4 型
（`TestS5bCounterDrivenBatch`），批次二 = 事件驱动 6 型
（`TestS5bEventDrivenBatch`）。

## 装置形状（三层）

1. **池事实**（`PoolShape` + `make_pool_shape`）：`DrawInfo` 的静态输入，
   池的槽位映射与基础概率，抽卡序列之外唯一的外部输入。
2. **侧驱动**（`run_old` / `run_new` / `run_new_via_engine`，产物 `SideTrace`）：
   在固定种子上把一侧（旧类实例或新骨架实例）逐抽驱动一遍，记录每抽的
   概率分布、只读查询结果、`did_fire`、抽后状态快照，并统计随机数消费次数。
3. **比对**（`compare_traces` / `compare_runs`，产物 `EquivalenceReport`）：
   把两份 `SideTrace` 按**显式参数**的容差与白名单比对，产出结构化差异清单；
   `assert_equivalent` 把清单翻译成断言消息。

## 驱动纪律（两条，均源于近期审查）

- **两侧都必须先 `_rebind_state(state)` 再驱动**。S4-2 删除了
  `PityEngine._rebind_state` 的 `state is self._state` 早退后，`create_behavior`
  返回的 `Pity` 在未经一次 rebind 前，三族零件均未绑定账本；旧类中
  `RotatingBehavior` / `TargetedBehavior` 一族同样不在构造期绑定（只有
  `CounterBasedBehavior` 一族在构造期建 `Counter`）。本装置**直驱 behavior**，
  故两侧各补一次 rebind。走 `PityEngine` 全管道时引擎自身会 rebind，见
  `run_new_via_engine`（装置用它做「直驱是否忠实于生产调度」的自检）。
- **新旧两侧用同一条抽卡序列与同一个种子**（`random.seed(seed)`），故两侧的
  随机流起点相同；`rotating_cr` 族的掷骰在两侧都走模块级 `random`（旧
  `RotatingCRBehavior.before_draw` / 新 `StreakTracker.prepare`），消费次数由
  `_counting_rng()` 统计，供 H4 断言使用。

## 已登记差异（不掩盖，逐项落在用例上）

本装置**不为求绿而放宽任何断言**。下列差异是近期实施与审查的实测产物，
一律以「精确集合的白名单」「显式参数的容差」「断定差异存在的登记用例」表达，
不用魔数把差异盖过去：

| 差异 | 实测 | 表达方式 | 登记用例 |
|------|------|---------|---------|
| 六个事件驱动型的**非条件分支**有 1 ULP 位级差 | 九种池形状扫描上界 1.11e-16（`rotating` 在本装置形状下恰 1 ULP；`_soft` 三型在 0.1/0.3 形状下达 1.11e-16） | `Tolerance` 显式参数（`EXACT` / `FLOAT_ORDER`） | `test_registered_ulp_in_event_driven_non_trigger_branch` |
| 事件驱动型快照多 `_active` 键（ISSUE-202） | 六型全中 | `SnapshotPolicy` 白名单（精确集合，多退少补都报错） | `test_registered_extra_state_keys_are_exactly_whitelisted` |
| `rotating_cr` / `rotating_cr_soft` 快照多 `cr_intercepted` 键 | 两型 | 同上 | 同上 |
| 三个 `_soft` 复合类型的 `did_fire` 放宽为「出 scope」（ISSUE-102） | 非 featured 的 SSR 抽上 旧 False / 新 True | `SideTrace.did_fire` + 差异抽索引 | `test_m4_registered_did_fire_relaxation_for_soft_suffix_types` |
| 三个 `_soft` 后缀类型的 deltas 取值源分叉（新读 `pdef.deltas`，旧只读 `pdef.soft_deltas`） | `deltas` 直构时两侧分叉 | fixture 规则（`soft_fixture()`）+ 登记用例 | `test_registered_soft_deltas_source_divergence` |
| `counter_soft` 的 deltas 与语法糖全缺省时两侧不同处置（旧构造失败、新按 74/90 缺省生效） | 旧 `SoftStepBehavior.__init__` 抛 `ValueError` | 登记用例（不断言等价，只断言两侧各自事实） | `test_registered_counter_soft_deltas_default_divergence` |
| **无 featured 卡的池 + 必然拦截**时旧侧把 scope 清零、新侧恒等（§六 F2） | 旧侧 Σ_scope = 0 / 新侧保持基础总量 | 登记用例（断言差异形状，**不断言等价**） | `test_f2_registered_no_featured_pool_with_forced_interception` |

**容差已裁决（S5b 批次一开工时落地，§六 2026-10-11 同步后的措辞）**：§六 主线
把口径拆成两列：「**概率分布 = 容差 1e-12 内逐场一致**」+「**状态快照 =
位级一致**」，并注明该 1 ULP 是旧侧 `_redistribute_scope` 的「除再乘」往返
产物、不含语义内容（§3.1.5.6 的「位级一致」行与 §3.1.5 定理 1 的效力说明）。
故本装置按机制族分派容差：**counter 驱动 4 型取 `EXACT`**（两侧同为绝对赋值、
实测 `max_prob_diff == 0.0`，位级一致字面成立）；**事件驱动 6 型取
`FLOAT_ORDER`（1e-12）**，覆盖非条件分支的 1 ULP。两族都在调用点写理由
（`Tolerance.rationale` 为空即抛 `ValueError`，禁止匿名魔数）。状态机部分
（counter 整数相位、flag 布尔翻转、随机流消费次数）在两种口径下都是**精确
比较**，放宽的只是浮点分布一列。

## 收集守卫（GATE-6）

S5c 的验收命令是 `pytest -q tests/core/test_pity_equivalence.py -k "n1 or m4 or h4"`。
本文件为 S5a 新建，过滤词零命中时 pytest 以 exit code 5（no tests ran）结束、
会被误读为通过。**S5c 落地后的命中情况（2026-10-11 实测）**：`n1` 4 条 /
`m4` 19 条 / `h4` 10 条，合计 **33 条**（三类各自 ≥1 条，exit code 0）。其中
**S5c 新增 29 条**（`TestS5cN1Phase` 4 + `TestS5cM4DidFire` 16 +
`TestS5cH4RandomConsumption` 9），余 4 条为既有命中（`TestRegisteredDifferences`
的 `_soft` 放宽登记 3 条 + `TestH4RandomConsumption` 的中间值用例 1 条）。
`n1` / `m4` / `h4` 三个过滤词均落在新增用例名内。

## 本装置测不出来的形态（S5a 已知边界，如实列出）

**S5c 落地后的边界（2026-10-11）**：10 个类型的逐类型等价性已按两批接入
（`TestS5bCounterDrivenBatch` / `TestS5bEventDrivenBatch`），N1 / M4 / H4 三条
强制约束已由 `TestS5cN1Phase` / `TestS5cM4DidFire` / `TestS5cH4RandomConsumption`
三节覆盖。装置的自检面之外仍**未覆盖**下列形态：多保底叠加（`hard` + `rotating`
同 scope）、`depends_on` 激活传播、池过滤与池内排序、跨场 `rebind`（worker 内
连跑第 2..N 场）、退役维（`max_triggers`）。这批分归 S6 / S7d / S10，不属
S5b / S5c 的验收面。

**S5c 实测出的一条覆盖边界（2026-10-11，牙齿验证产物）**：三个 `_soft` 复合
类型的 `FlagTracker.did_reset` 若退化（例如恒返回 False），**在 `did_fire` 层面
不可观测**——该族 preset 的 CounterTracker 恰在「出 scope」的那些抽上给出 True，
`any(...)` 被它占满，故 `did_fire` 列逐位不变（实测：把 `FlagTracker.did_reset`
改成恒 False 后，三个 `_soft` 型的 M4 两列断言与 S5b 批次**全绿**，而只由
`FlagTracker` 提供 `did_reset` 的 `rotating` / `rotating_cr` /
`rotating_guaranteed_init` 在 S5b 批次与该型的两列断言上同时变红）。这是
ISSUE-102 的放宽本身带来的语义冗余，不是本装置的漏测：要覆盖它须下沉到「逐个
Tracker 的 `did_reset`」的自洽断言，超出等价性装置的对拍面。**该面已有专属单测**
（`tests/core/test_pity_tracker.py` 的 `TestFlagTrackerDidReset` / `TestFateTrackerDidReset`
等），且 preset 组合面若被破坏会由快照列的 `missing_new_keys` 抓到，故此处只登记为
**本装置的边界**，不另派后续块（S5c 审查 low 4 订正：原写「登记给 S10 / S11」，而计划
的 S10-1 / S10-2 / S11 三条块条目里并无对应项，属无处落地的登记）。

1. **不走 `PityEngine` 的池过滤 / 池内排序 / 激活传播**。旧类在 registry 上已无
   入口（10 条 `registry` 条目全部 preset 化、`class` 置 None），旧侧无法经引擎
   构造，故两侧对称的唯一驱动方式是直驱 behavior。`run_new_via_engine` 只用来
   自检「直驱 vs 引擎调度对同一 pdef 同结果」，不承担等价性覆盖。
2. **单条保底的组合面**。本装置一次只驱动一个 `PityDef`，多保底叠加（`hard` +
   `rotating` 同 scope）、`depends_on` 激活传播、生命周期退役均不在覆盖内。
3. **`readonly` 只读路径的分布差异**只作为附加观测（`SideTrace.readonly_probs`），
   其等价性口径与主路径分开判断。
4. **随机流位置差**只能被「消费次数相同 + 逐抽结果相同」间接约束，不能直接断言
   「消费了同一个数」。
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import math
import os
import random
import tempfile
import textwrap
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import pytest

from gacha_simulator.core.config_store import ConfigError, PityDef
from gacha_simulator.core.config_toml import load_toml
from gacha_simulator.core.invariants import InvariantChecker, InvariantError
from gacha_simulator.core.pity_modifier import Modifier
from gacha_simulator.core.pity import (
    AlwaysActive,
    CounterTracker,
    DrawInfo,
    HardModifier,
    HardPityBehavior,
    Pity,
    PityContext,
    PityEngine,
    PityState,
    PoolPitySpec,
    RotatingBehavior,
    RotatingCRBehavior,
    RotatingCRSoftBehavior,
    RotatingSoftBehavior,
    SoftStepBehavior,
    TargetedBehavior,
    TargetedSoftBehavior,
    _apply_delta,
    _build_pity_state_init,
    create_behavior,
    transfer_linear,
)

# ══════════════════════════════════════════════════════════════════
# 一、池事实与抽卡序列
# ══════════════════════════════════════════════════════════════════

#: 稀有度层级表：**rank 值小 = 稀有度更高**（`config_store._parse_rarities` 的
#: 「rank 0 = 最高」，经 `batch_simulator` 的 `{k.lower(): v}` 小写化后传入引擎；
#: `_resolve_order` 亦以「rank 值小 → 优先级高」排序）。
#:
#: **不得写成 `{'ssr': 3, 'sr': 2, 'r': 1}`**（既有若干单测的写法）：那样
#: `_lower_rarities()` 的 `rank > rank(scope)` 判据返回空集，`SoftModifier` 的
#: `pool <= 0` 提前恒等，软保底在两侧同为恒等、装置全绿而零覆盖。
#: 本方向由 `test_device_shape_makes_soft_transfer_live` 钉住。
RARITY_RANK: Dict[str, int] = {'ssr': 0, 'sr': 1, 'r': 2}

#: 池的默认形状：SSR 双槽（featured / standard）+ SR + R。
#:
#: SSR 侧取 `0.2` / `0.2`（与 `gacha_simulator/config/config.toml` 的
#: 「SSR 总量 0.4、featured 与 standard 各半」同比例），因为它是实测能触发
#: 非条件分支 1 ULP 差的形状之一。**槽位概率取整不影响本装置的判别力**：
#: 1 ULP 差由「除再乘的往返」产生，与取值是否「整齐」无关，只与具体位模式有关
#: （实测 `0.006`/`0.004` 与 `0.005`/`0.005` 两组为零差、`0.2`/`0.2` 组为 1 ULP）。
DEFAULT_CARDS: Tuple[Tuple[str, str, bool, float], ...] = (
    ('f1', 'ssr', True, 0.2),
    ('s1', 'ssr', False, 0.2),
    ('sr1', 'sr', False, 0.051),
    ('r1', 'r', False, 0.549),
)


@dataclass(frozen=True)
class PoolShape:
    """一个池的静态事实：`DrawInfo` 的槽位映射与基础概率。"""

    scope_cards: Dict[str, tuple]
    featured_cards: Dict[str, tuple]
    scope_slots: Dict[str, tuple]
    featured_slots: Dict[str, tuple]
    card_to_slot: Dict[str, str]
    base_probabilities: Dict[str, float]
    rarity_rank: Dict[str, int]
    #: **卡级**基础分布（S8 起新侧的分布键空间，D20 / §3.9.1）。`base_probabilities`
    #: 是槽位级、供旧类使用；两者由同一张四元组表产出，故是同一份质量的两种聚合。
    card_probabilities: Dict[str, float]

    @property
    def scope(self) -> str:
        """本形状的默认 scope（SSR）。装置只覆盖单 scope 保底。"""
        return 'ssr'

    def featured_ids(self) -> frozenset:
        return frozenset(c for cards in self.featured_cards.values() for c in cards)


def make_pool_shape(
    cards: Sequence[Tuple[str, str, bool, float]],
    rarity_rank: Optional[Dict[str, int]] = None,
) -> PoolShape:
    """从 `(card_id, rarity, featured, probability)` 四元组表构造池事实。

    槽位映射的生成规则与 `core/pity.py::compute_scope_mappings()` 同形
    （featured 卡拆出 `{rarity}_featured` 独立槽位，`scope_slots` 内 standard 在前），
    但**不复用该函数**：它要求一个 `Pool` 对象，而本装置只需要静态事实；
    且它的产出在 S8 会被改造（§六 AUDIT-BREAK-5 的 A 项）。本构造器是测试侧设施，
    改动面只在测试内。
    """
    scope_cards: Dict[str, List[str]] = {}
    featured_cards: Dict[str, List[str]] = {}
    card_to_slot: Dict[str, str] = {}
    base: Dict[str, float] = {}
    for card_id, rarity, featured, prob in cards:
        rarity = rarity.lower()
        scope_cards.setdefault(rarity, []).append(card_id)
        slot = f'{rarity}_featured' if featured else rarity
        card_to_slot[card_id] = slot
        base[slot] = base.get(slot, 0.0) + prob
        if featured:
            featured_cards.setdefault(rarity, []).append(card_id)

    scope_slots: Dict[str, tuple] = {}
    featured_slots: Dict[str, tuple] = {}
    for rarity in scope_cards:
        if rarity in featured_cards:
            scope_slots[rarity] = (rarity, f'{rarity}_featured')
            featured_slots[rarity] = (f'{rarity}_featured',)
        else:
            scope_slots[rarity] = (rarity,)
            featured_slots[rarity] = (rarity,)

    return PoolShape(
        scope_cards={r: tuple(c) for r, c in scope_cards.items()},
        featured_cards={r: tuple(c) for r, c in featured_cards.items()},
        scope_slots=scope_slots,
        featured_slots=featured_slots,
        card_to_slot=card_to_slot,
        base_probabilities=base,
        rarity_rank=dict(rarity_rank or RARITY_RANK),
        card_probabilities={cid: prob for cid, _r, _f, prob in cards},
    )


@dataclass(frozen=True)
class DrawStep:
    """一次抽卡的静态事实（奖励卡、稀有度、是否 featured）。"""

    reward_id: str
    rarity: str
    is_featured: bool


FEATURED_SSR = DrawStep('f1', 'ssr', True)
STANDARD_SSR = DrawStep('s1', 'ssr', False)
SR_DRAW = DrawStep('sr1', 'sr', False)
R_DRAW = DrawStep('r1', 'r', False)

#: 默认抽卡序列：覆盖 featured SSR / 非 featured SSR / SR / R 四类，且含两段足够长的
#: 「无 SSR」连抽（8 抽 / 10 抽），使 counter 能越过 `hard` 的阈值与 soft 的 boost 起点。
#:
#: **非 featured SSR 出现两次**（下标 19 / 25），它是三个 `_soft` 复合类型 M4 放宽
#: （ISSUE-102）的唯一显形面（旧 `did_fire` 为 False、新为 True）。
DRAW_SEQUENCE: Tuple[DrawStep, ...] = (
    (R_DRAW,) * 8            # 0-7  ：counter 爬到 8，越过 soft boost 起点与 hard 阈值
    + (FEATURED_SSR,)        # 8    ：命中 featured，counter 归零、guaranteed 清位
    + (R_DRAW,) * 10         # 9-18 ：再爬一轮
    + (STANDARD_SSR,)        # 19   ：出 scope 未命中（M4 放宽的显形点）
    + (R_DRAW,) * 2          # 20-21
    + (FEATURED_SSR,)        # 22
    + (R_DRAW,) * 2          # 23-24
    + (STANDARD_SSR,)        # 25   ：第二个显形点
    + (SR_DRAW,) * 2         # 26-27
)


def make_draw_sequence(
    length: int,
    *,
    seed: int = 20261011,
    ssr_featured_rate: float = 0.02,
    ssr_standard_rate: float = 0.02,
    sr_rate: float = 0.11,
) -> Tuple[DrawStep, ...]:
    """按给定比例随机生成抽卡序列（S5b / S5c 的长序列入口）。"""
    rng = random.Random(seed)
    steps: List[DrawStep] = []
    for _ in range(length):
        roll = rng.random()
        if roll < ssr_featured_rate:
            steps.append(DrawStep('f1', 'ssr', True))
        elif roll < ssr_featured_rate + ssr_standard_rate:
            steps.append(DrawStep('s1', 'ssr', False))
        elif roll < ssr_featured_rate + ssr_standard_rate + sr_rate:
            steps.append(DrawStep('sr1', 'sr', False))
        else:
            steps.append(DrawStep('r1', 'r', False))
    return tuple(steps)


# ══════════════════════════════════════════════════════════════════
# 二、比对口径（容差与白名单的显式载体）
# ══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Tolerance:
    """概率比对的容差。**显式参数，且必须自述理由**。

    `rationale` 为空即抛 `ValueError`：本项目禁止用一个「恰好能过」的匿名魔数
    把已知差异盖住（§六 的差异登记纪律）。选 `EXACT` 还是 `FLOAT_ORDER` 是
    一个**待裁决的决策点**，不是实现细节，故理由必须写进调用点。
    """

    kind: str                      # 'exact' | 'absolute'
    atol: float
    rationale: str

    def __post_init__(self) -> None:
        if self.kind not in ('exact', 'absolute'):
            raise ValueError(f'未知的 Tolerance.kind={self.kind!r}')
        if not self.rationale.strip():
            raise ValueError(
                'Tolerance 必须自述理由（rationale 不得为空）：'
                '容差取值是决策点，不是实现细节'
            )

    def holds(self, old: float, new: float) -> bool:
        if self.kind == 'exact':
            return old == new
        return abs(old - new) <= self.atol

    def describe(self) -> str:
        if self.kind == 'exact':
            return f'位级一致（==）：{self.rationale}'
        return f'绝对容差 {self.atol:g}：{self.rationale}'


#: §六 主线字面口径（「与旧类逐场完全一致」「位级一致」）。
EXACT = Tolerance('exact', 0.0, '§六 主线 S1–S5 口径的字面要求：位级一致')

#: 浮点运算顺序容差。1e-12 是 §六 S8 口径已采用的同一数值（S8 与 S5 产物对比
#: 的容差），非为本装置新造的魔数。
FLOAT_ORDER = Tolerance(
    'absolute', 1e-12,
    '§六 S8 口径已采用的浮点求和顺序容差；覆盖非条件分支 1 ULP 差（九形状扫描上界 1.11e-16）',
)


@dataclass(frozen=True)
class SnapshotPolicy:
    """状态快照比对的白名单。**精确集合**，多退少补都报错。

    `allowed_new_only_keys` 是「新侧允许多出」的 `(命名空间, 键)` 集合。
    `compare_traces` 会把实际上多出的键与之**逐项对账**：

    - 实际多出但未登记 -> `unlisted_extra_keys`（判为失败）
    - 登记了但实际没出现 -> `stale_allowed_keys`（判为失败）

    故白名单不是「一律放过」的口子：它必须与实际差异集合精确相等。新侧**少**
    键（`missing_new_keys`）永不允许。
    """

    allowed_new_only_keys: frozenset
    rationale: str

    def __post_init__(self) -> None:
        if not self.rationale.strip():
            raise ValueError('SnapshotPolicy 必须自述理由（rationale 不得为空）')


NO_EXTRA_KEYS = SnapshotPolicy(
    frozenset(), 'counter 驱动的四个类型两侧写同一批键（实测无多出、无缺失）',
)


def registered_snapshot_policy(pdef: PityDef) -> SnapshotPolicy:
    """按 btype 取已登记的快照白名单（S5b 逐类型批次直接复用）。

    - 六个事件驱动型：多 `_active`（ISSUE-202，`Lifecycle.initialize` 的统一写入，
      旧 `RotatingBehavior` / `TargetedBehavior` 一族不写）
    - `rotating_cr` / `rotating_cr_soft`：再多 `cr_intercepted`
      （`StreakTracker` 的拦截标记，§3.1.1 的 `state_keys()` 声明产物）
    """
    keys = frozenset()
    if pdef.btype in _EVENT_DRIVEN_BTYPES:
        keys |= {(pdef.name, '_active')}
    if pdef.btype in ('rotating_cr', 'rotating_cr_soft'):
        keys |= {(pdef.name, 'cr_intercepted')}
    if keys:
        return SnapshotPolicy(keys, f'{pdef.btype} 的已登记多出键（ISSUE-202 / CR 拦截标记）')
    return SnapshotPolicy(
        frozenset(), f'{pdef.btype} 属 counter 驱动族，两侧写同一批键',
    )


_EVENT_DRIVEN_BTYPES = frozenset({
    'rotating', 'rotating_soft', 'rotating_cr', 'rotating_cr_soft',
    'targeted', 'targeted_soft',
})

_SOFT_SUFFIX_BTYPES = frozenset({'rotating_soft', 'rotating_cr_soft', 'targeted_soft'})


# ══════════════════════════════════════════════════════════════════
# 三、两侧装配（旧类工厂 / 新骨架工厂）
# ══════════════════════════════════════════════════════════════════


@contextmanager
def _counting_rng(seed: int):
    """固定种子 + 统计 `random.random()` 的消费次数（H4 的观测面）。

    两侧的掷骰都走模块级 `random`（`import random` 后属性查找发生在调用时），
    故替换模块属性即可同时覆盖旧类与 `StreakTracker`。退出时无条件还原。
    """
    random.seed(seed)
    calls = {'n': 0}
    original = random.random

    def _counted() -> float:
        calls['n'] += 1
        return original()

    random.random = _counted
    try:
        yield calls
    finally:
        random.random = original


def _old_soft_kwargs(pdef: PityDef) -> dict:
    """三个 `_soft` 后缀类型交给旧 mixin 的关键字参数。

    **这是新旧分叉的落点**（`test_registered_soft_deltas_source_divergence`）：
    旧 `SoftPityMixin._init_soft_pity` 只读 `soft_deltas` / `soft_start` /
    `soft_end` / `soft_increment`，**不读 `pdef.deltas`**；新 `_soft_deltas_of(pdef)`
    首选 `pdef.deltas`。TOML 直载路径把两字段写成同源（`config_toml._build_pity`
    的 `deltas` 键同时填 `PityDef.deltas` 与 `PityDef.soft_deltas`），故
    **fixture 必须按 TOML 形态同时写两个字段**（见 `soft_fixture()`），
    否则 S5b 的 `_soft` 批次会踩空。
    """
    # **`None` 项不入参**（S5a 审查 minor 4）：真实旧类分支是
    # `if v is not None: params[attr] = v`（`core/pity.py` 的 `params` 组装段），
    # 故缺省字段**根本不会出现在 kwargs 里**，`SoftPityMixin._init_soft_pity` 的
    # `kwargs.get('soft_start', 74)` 才会回退到 74 / 90。此前本函数传的是显式
    # `None`，覆盖了那些 default 值，旧侧展开成 `((0, 0.0), (91, 1.098901))`
    # 而非真实的 `((73, 0.0), (17, 5.882353))`，与「旧 mixin 落到缺省 74 / 90」
    # 的说明自相矛盾。改为与真实分支同形。
    return {k: v for k, v in dict(
        soft_deltas=pdef.soft_deltas,
        soft_start=pdef.soft_start,
        soft_end=pdef.soft_end,
        soft_increment=pdef.soft_increment,
    ).items() if v is not None}


def _old_counter_soft_deltas(pdef: PityDef) -> tuple:
    """counter 驱动三软类型的 deltas，按旧 `create_behavior` 分支的取法。

    旧分支顺序：`pdef.deltas` 非空则直取；否则由 `soft_start` 走语法糖展开
    （`soft_step` 不参与展开，故其 `deltas` 为 None 时旧 `SoftStepBehavior`
    构造期抛 `ValueError`）。
    """
    if pdef.deltas is not None:
        return pdef.deltas
    if pdef.soft_start is None:
        return None
    from gacha_simulator.core.config_toml import _expand_soft_to_deltas
    return _expand_soft_to_deltas(
        pdef.btype, pdef.soft_start, pdef.soft_end, pdef.soft_increment)


#: 旧类装配表：btype -> `(pdef, state) -> 旧类实例`。
#: 10 条与 `BEHAVIOR_REGISTRY` 的 btype 一一对应；工厂**逐条直构**旧类，
#: 不经 `create_behavior`（该函数已全部走 preset 分支）。
OLD_BEHAVIOR_FACTORY: Dict[str, Callable[[PityDef, PityState], Any]] = {
    'hard': lambda pd, st: HardPityBehavior(
        pd.name, st, scope=pd.scope, btype='hard',
        threshold=pd.threshold, target_featured=pd.target_featured,
        reset=pd.reset or None,
    ),
    'soft_step': lambda pd, st: SoftStepBehavior(
        pd.name, st, scope=pd.scope, btype=pd.btype,
        deltas=_old_counter_soft_deltas(pd), reset=pd.reset or None,
    ),
    'soft_interval': lambda pd, st: SoftStepBehavior(
        pd.name, st, scope=pd.scope, btype=pd.btype,
        deltas=_old_counter_soft_deltas(pd), reset=pd.reset or None,
    ),
    'soft_additive': lambda pd, st: SoftStepBehavior(
        pd.name, st, scope=pd.scope, btype=pd.btype,
        deltas=_old_counter_soft_deltas(pd), reset=pd.reset or None,
    ),
    'rotating': lambda pd, st: RotatingBehavior(
        pd.name, st, scope=pd.scope, guaranteed_init=pd.guaranteed_init,
    ),
    'rotating_cr': lambda pd, st: RotatingCRBehavior(
        pd.name, st, scope=pd.scope,
        cr_counter_threshold=pd.cr_counter_threshold,
        cr_base_rate=pd.cr_base_rate, cr_state_probs=pd.cr_state_probs,
        guaranteed_init=pd.guaranteed_init,
    ),
    'rotating_soft': lambda pd, st: RotatingSoftBehavior(
        pd.name, st, scope=pd.scope, guaranteed_init=pd.guaranteed_init,
        **_old_soft_kwargs(pd),
    ),
    'rotating_cr_soft': lambda pd, st: RotatingCRSoftBehavior(
        pd.name, st, scope=pd.scope,
        cr_counter_threshold=pd.cr_counter_threshold,
        cr_base_rate=pd.cr_base_rate, cr_state_probs=pd.cr_state_probs,
        guaranteed_init=pd.guaranteed_init,
        **_old_soft_kwargs(pd),
    ),
    'targeted': lambda pd, st: TargetedBehavior(
        pd.name, st, scope=pd.scope, fate_threshold=pd.fate_threshold,
        guaranteed_init=pd.guaranteed_init, fate_points_init=pd.fate_points_init,
    ),
    'targeted_soft': lambda pd, st: TargetedSoftBehavior(
        pd.name, st, scope=pd.scope, fate_threshold=pd.fate_threshold,
        guaranteed_init=pd.guaranteed_init, fate_points_init=pd.fate_points_init,
        **_old_soft_kwargs(pd),
    ),
}


def build_old(pdef: PityDef, state: PityState):
    """构造旧类实例（未 rebind，由 `run_trace` 统一补一次）。"""
    factory = OLD_BEHAVIOR_FACTORY.get(pdef.btype)
    if factory is None:
        raise KeyError(f'OLD_BEHAVIOR_FACTORY 缺 btype={pdef.btype!r} 的装配条目')
    return factory(pdef, state)


def build_new(pdef: PityDef, state: PityState):
    """构造新统一骨架（`create_behavior` 的 preset 分支）。"""
    return create_behavior(pdef, state)


#: targeted 族的定轨卡（`selected_card` 由策略层写入，装置固定取 featured 卡）。
TARGETED_CARD = 'f1'


def initial_state(pdef: PityDef) -> PityState:
    """与引擎阶段 3 同源的初始状态：`_build_pity_state_init` + `selected_card`。"""
    state = _build_pity_state_init([pdef])
    if pdef.btype in ('targeted', 'targeted_soft'):
        state.set(pdef.name, 'selected_card', TARGETED_CARD)
    return state


# ══════════════════════════════════════════════════════════════════
# 四、侧驱动与轨迹记录
# ══════════════════════════════════════════════════════════════════


@dataclass
class SideTrace:
    """一侧在一场模拟中的逐抽记录。"""

    name: str
    base_probabilities: Dict[str, float]
    init_snapshot: Dict[str, Any]
    #: 本侧分布所在的**键空间**（'slot' = 旧类 / M1 管道；'card' = S8 起的新骨架）。
    space: str = 'slot'
    #: 卡 → 槽位的投影表（`space == 'card'` 时用于把本侧结果聚合到槽位级对照）。
    slot_of: Dict[str, str] = field(default_factory=dict)
    probs: List[Dict[str, float]] = field(default_factory=list)
    readonly_probs: List[Dict[str, float]] = field(default_factory=list)
    snapshots: List[Dict[str, Any]] = field(default_factory=list)
    did_fire: List[bool] = field(default_factory=list)
    readonly_mutations: List[int] = field(default_factory=list)
    rng_calls: int = 0

    @property
    def changed_from_base(self) -> bool:
        """本侧是否至少有一抽的分布不等于基础分布。

        旧类侧必须为真（§六 AUDIT-BREAK-D 的验收：旧侧若退化为恒等，说明槽位
        字段已提前消失，等价性对照失去意义）。
        """
        return any(p != self.base_probabilities for p in self.probs)

    @property
    def changed_beyond_ulp(self) -> bool:
        """是否有至少一抽的分布变化**超出浮点噪声**（4 ULP）。

        `changed_from_base` 取严格不等，而六个事件驱动型的旧类在**非触发分支**
        也走一遍 `_redistribute_scope()`（数学等值、位模式不同），故旧侧与该基础
        分布恒有 1 ULP 量级差、`changed_from_base` 恒真，挡不住「机制从未触发」
        的空转（S5b 审查 important 1：全 R 序列下 `rotating` 的 guaranteed 分支
        永不触发，而闸门放过）。空转闸门取本属性。
        """
        eps = 4 * math.ulp(1.0)
        for p in self.probs:
            for k, v in p.items():
                if abs(v - self.base_probabilities.get(k, 0.0)) > eps:
                    return True
        return False


def _ctx(shape: PoolShape, state: PityState, step: Optional[DrawStep] = None,
         space: str = 'slot') -> PityContext:
    """构造一次抽卡的 `PityContext`。

    `step is None` 时是抽前上下文（reward 字段取空串、`current` 取基础分布）。

    **`space` 是本装置在 S8 新增的显式参数**：`'slot'` 给旧类（槽位级分布 +
    槽位级 `base_probabilities`），`'card'` 给 S8 起的新骨架（卡级分布 + 卡级
    `base_probabilities`）。`DrawInfo` 的卡集合 / 槽位映射两份事实两边都给全
    （旧类读槽位、新骨架读卡集合），差别只在**分布与声明权重**的键空间。
    """
    draw = DrawInfo(
        pool_id='rig_pool',
        pool_instance_id='rig_pool_0',
        reward_id=step.reward_id if step else '',
        reward_rarity=step.rarity if step else '',
        is_featured=step.is_featured if step else False,
        scope_cards=shape.scope_cards,
        featured_cards=shape.featured_cards,
        scope_slots=shape.scope_slots,
        featured_slots=shape.featured_slots,
        card_to_slot=shape.card_to_slot,
        base_probabilities=shape.base_probabilities,
        rarity_rank=shape.rarity_rank,
    )
    base = shape.base_probabilities if space == 'slot' else shape.card_probabilities
    draw = dataclasses.replace(draw, base_probabilities=base)
    return PityContext(
        draw=draw,
        current=dict(base) if step is None else {},
        state=state,
    )


def run_trace(
    builder: Callable[[PityDef, PityState], Any],
    pdef: PityDef,
    steps: Sequence[DrawStep],
    *,
    shape: PoolShape,
    seed: int = 20261011,
    probe_readonly: bool = True,
    name: str = '',
) -> SideTrace:
    """用 `builder` 构造一侧并逐抽驱动，返回 `SideTrace`。

    每抽的顺序（两侧一致，与引擎的调度顺序同形）：

    1. 只读查询 `before_draw(ctx, readonly=True)`（可选），并记录状态是否被改动；
    2. 正式 `before_draw(ctx)` -> 分布；
    3. `after_draw(ctx_with_reward)`；
    4. `did_fire(ctx_with_reward)`；
    5. 记录抽后状态快照。
    """
    # 键空间按侧分派：新骨架（`build_new`）是卡级管道（S8），旧类是槽位级。
    # 判据用**构造器身份**而不是「有没有某个属性」，避免「新侧被换成别的构造器」
    # 时静默按错的空间驱动（那会让两侧各自恒等、装置假绿）。
    space = 'card' if builder is build_new else 'slot'
    base = shape.base_probabilities if space == 'slot' else shape.card_probabilities
    state = initial_state(pdef)
    layer = builder(pdef, state)
    # 驱动纪律：两侧都必须补一次 rebind（见模块 docstring）。
    layer._rebind_state(state)
    trace = SideTrace(
        name=name or pdef.name,
        base_probabilities=dict(base),
        init_snapshot=state.to_dict()['data'],
        space=space,
        slot_of=dict(shape.card_to_slot),
    )

    with _counting_rng(seed) as calls:
        for index, step in enumerate(steps):
            if probe_readonly:
                before = state.to_dict()['data']
                trace.readonly_probs.append(dict(layer.before_draw(
                    _ctx(shape, state, space=space), readonly=True)))
                if state.to_dict()['data'] != before:
                    trace.readonly_mutations.append(index)
            trace.probs.append(dict(layer.before_draw(_ctx(shape, state, space=space))))
            after_ctx = _ctx(shape, state, step, space=space)
            layer.after_draw(after_ctx)
            trace.did_fire.append(bool(layer.did_fire(after_ctx)))
            trace.snapshots.append(state.to_dict()['data'])
        trace.rng_calls = calls['n']
    return trace


def run_old(pdef: PityDef, steps: Sequence[DrawStep], *, shape: PoolShape,
            seed: int = 20261011, probe_readonly: bool = True) -> SideTrace:
    return run_trace(build_old, pdef, steps, shape=shape, seed=seed,
                     probe_readonly=probe_readonly, name=f'old:{pdef.name}')


def run_new(pdef: PityDef, steps: Sequence[DrawStep], *, shape: PoolShape,
            seed: int = 20261011, probe_readonly: bool = True) -> SideTrace:
    return run_trace(build_new, pdef, steps, shape=shape, seed=seed,
                     probe_readonly=probe_readonly, name=f'new:{pdef.name}')


def _engine_pool_spec(pdef: PityDef, shape: PoolShape) -> PoolPitySpec:
    return PoolPitySpec(
        pity_names=(pdef.name,),
        featured_ids=set(shape.featured_ids()),
        ssr_ids=set(shape.scope_cards.get(shape.scope, ())),
        scope_cards=shape.scope_cards,
        featured_cards=shape.featured_cards,
        scope_slots=shape.scope_slots,
        featured_slots=shape.featured_slots,
        card_to_slot=shape.card_to_slot,
    )


def run_new_via_engine(pdef: PityDef, steps: Sequence[DrawStep], *,
                       shape: PoolShape, seed: int = 20261011) -> SideTrace:
    """新侧的另一条驱动路径：`PityEngine` 全管道（装置自检用）。

    引擎自身在三个调度入口首行 rebind，故这里不需要外部补 rebind。稀有度由
    `PityEngine._infer_rarity` 从 `spec.scope_cards` 反查，与 `DrawStep.rarity`
    应当同答（本装置不额外断言该一致性，它属 `test_pity_integration` 的守卫面）。
    """
    state = initial_state(pdef)
    engine = PityEngine(
        pool_specs={'rig_pool': _engine_pool_spec(pdef, shape)},
        pity_defs=[pdef],
        rarity_rank=shape.rarity_rank,
        state=state,
    )
    trace = SideTrace(
        name=f'new-engine:{pdef.name}',
        base_probabilities=dict(shape.card_probabilities),
        init_snapshot=state.to_dict()['data'],
        space='card',
        slot_of=dict(shape.card_to_slot),
    )
    with _counting_rng(seed) as calls:
        for step in steps:
            trace.probs.append(dict(engine.before_draw(
                'rig_pool', state, shape.card_probabilities)))
            engine.after_draw('rig_pool', state, step.reward_id)
            trace.snapshots.append(state.to_dict()['data'])
        trace.rng_calls = calls['n']
    return trace


# ══════════════════════════════════════════════════════════════════
# 五、比对与报告
# ══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProbMismatch:
    draw: int
    key: str
    old: float
    new: float
    diff: float
    tolerance: Tolerance

    def __str__(self) -> str:
        return (f'第 {self.draw} 抽 键 {self.key}: old={self.old!r} '
                f'new={self.new!r} 差={self.diff:.3e}')


@dataclass
class EquivalenceReport:
    """一次旧 vs 新比对的**结构化**结果。所有字段都是原始事实，不做取舍。

    **`did_fire_divergent_draws` 不进 `failure_messages()`**：三个 `_soft` 复合类型的
    `did_fire` 放宽是 §3.1.1 的 ISSUE-102 裁定项（「出 scope」），按「不在等价性
    范围内」单独验收，故它是**观测面**而非失败条件。差异必须由
    `TestRegisteredDifferences` 的登记用例逐条断定其形状，不得以「反正不判失败」
    放过（登记用例断言差异面与「出 scope 但未命中」逐项重合）。
    """

    old: SideTrace
    new: SideTrace
    tolerance: Tolerance
    snapshot_policy: SnapshotPolicy
    prob_mismatches: List[ProbMismatch] = field(default_factory=list)
    readonly_mismatches: List[ProbMismatch] = field(default_factory=list)
    max_prob_diff: float = 0.0
    bit_exact: bool = True
    snapshot_mismatches: List[str] = field(default_factory=list)
    extra_new_keys: frozenset = frozenset()
    missing_new_keys: frozenset = frozenset()
    unlisted_extra_keys: frozenset = frozenset()
    stale_allowed_keys: frozenset = frozenset()
    did_fire_divergent_draws: List[int] = field(default_factory=list)

    @property
    def rng_calls_equal(self) -> bool:
        """两侧随机数消费次数是否相同（H4 的观测面）。"""
        return self.old.rng_calls == self.new.rng_calls

    def failure_messages(self) -> List[str]:
        """未通过项的人话描述（空列表 = 通过）。"""
        out: List[str] = []
        if self.prob_mismatches:
            out.append(
                f'概率超容差 {len(self.prob_mismatches)} 处'
                f'（口径：{self.tolerance.describe()}）: '
                + '; '.join(str(m) for m in self.prob_mismatches[:5])
            )
        if self.readonly_mismatches:
            out.append(
                f'只读查询超容差 {len(self.readonly_mismatches)} 处: '
                + '; '.join(str(m) for m in self.readonly_mismatches[:5])
            )
        if self.old.readonly_mutations or self.new.readonly_mutations:
            out.append(
                f'只读查询改动了状态: old={self.old.readonly_mutations} '
                f'new={self.new.readonly_mutations}'
            )
        if self.snapshot_mismatches:
            out.append(
                f'状态快照不等 {len(self.snapshot_mismatches)} 处: '
                + '; '.join(self.snapshot_mismatches[:5]))
        if self.missing_new_keys:
            out.append(f'新侧缺少旧侧存在的键: {sorted(self.missing_new_keys)}')
        if self.unlisted_extra_keys:
            out.append(
                f'新侧多出未登记的键: {sorted(self.unlisted_extra_keys)}'
                '（新增差异必须显式登记进 SnapshotPolicy，不得静默放过）')
        if self.stale_allowed_keys:
            out.append(
                f'白名单登记了实际不存在的键: {sorted(self.stale_allowed_keys)}'
                '（陈旧白名单会把未来的真实差异盖住，故同样判失败）')
        if not self.rng_calls_equal:
            out.append(
                f'随机数消费次数不同: old={self.old.rng_calls} new={self.new.rng_calls}')
        return out

    def is_equivalent(self) -> bool:
        return not self.failure_messages()


def _to_slot_space(dist: Dict[str, float], slot_of: Dict[str, str]) -> Dict[str, float]:
    """把**卡级**分布聚合到槽位级（比对口径的投影）。

    S8 起两侧的分布键空间不同（旧类槽位级 / 新骨架卡级），故比对前把新侧投影到
    旧侧的键空间。投影是**求和**（不是按声明权重展开）：它不引入任何假设，代价是
    组内结构在槽位分辨率下不可见：本装置的两个池形**每个槽位恰含一张卡**（投影
    即双射），故该代价为零；组内结构（如 S8 的单卡定向）由 S8-6 的卡级对比组覆盖。
    """
    out: Dict[str, float] = {}
    for card, value in dist.items():
        slot = slot_of.get(card, card)
        out[slot] = out.get(slot, 0.0) + value
    return out


def to_slots(dist: Dict[str, float], shape: PoolShape, *, space: str) -> Dict[str, float]:
    """把一份分布投影到**槽位级**（测试体对照 `shape.base_probabilities` 与槽位集用）。

    `space='slot'` 时原样返回（旧类侧的分布本就是槽位级）；`space='card'` 时按
    `card_to_slot` 求和聚合。**测试体一律用它**，不要在测试里手写 `shape.*` 的键
    去索引卡级分布（S8 前两者同键、S8 后不同，混用会 KeyError 或静默错值）。
    """
    return dist if space == 'slot' else _to_slot_space(dist, shape.card_to_slot)


def _align_sides(old: SideTrace, new: SideTrace):
    """把两侧对齐到同一键空间（旧侧空间）：返回 `(old, new)`。

    仅当新侧是卡级、旧侧是槽位级时投影新侧；两侧同空间时原样返回。
    """
    if old.space == new.space or not new.slot_of:
        return old, new
    return old, dataclasses.replace(
        new,
        probs=[_to_slot_space(d, new.slot_of) for d in new.probs],
        readonly_probs=[_to_slot_space(d, new.slot_of) for d in new.readonly_probs],
    )


def _diff_probs(old: Dict[str, float], new: Dict[str, float],
                tolerance: Tolerance) -> Tuple[List[ProbMismatch], float, bool]:
    mismatches: List[ProbMismatch] = []
    worst = 0.0
    bit = True
    for index, (a, b) in enumerate(zip(old, new)):
        for key in sorted(set(a) | set(b)):
            va, vb = a.get(key, 0.0), b.get(key, 0.0)
            diff = abs(va - vb)
            worst = max(worst, diff)
            if va != vb:
                bit = False
            if not tolerance.holds(va, vb):
                mismatches.append(ProbMismatch(index, key, va, vb, diff, tolerance))
    return mismatches, worst, bit


def _snapshot_facts(old_snaps, new_snaps, init_old, init_new):
    """逐场比对快照，产出（不匹配描述, 多出键集合, 缺失键集合）。"""
    extra: set = set()
    missing: set = set()
    problems: List[str] = []

    def _pairs(data: Dict[str, Any]):
        return {(ns, key): value for ns, kv in data.items() for key, value in kv.items()}

    frames = [(init_old, init_new)] + list(zip(old_snaps, new_snaps))
    labels = ['初始'] + [f'第 {i} 抽' for i in range(len(old_snaps))]
    for label, (a, b) in zip(labels, frames):
        pa, pb = _pairs(a), _pairs(b)
        extra |= set(pb) - set(pa)
        missing |= set(pa) - set(pb)
        for key in sorted(set(pa) & set(pb)):
            if pa[key] != pb[key]:
                problems.append(f'{label} 键 {key[0]}.{key[1]}: '
                                f'old={pa[key]!r} new={pb[key]!r}')
    return problems, frozenset(extra), frozenset(missing)


def compare_traces(old: SideTrace, new: SideTrace, *,
                   tolerance: Tolerance,
                   snapshot_policy: SnapshotPolicy) -> EquivalenceReport:
    """按显式口径比对两份轨迹，返回结构化报告（不做取舍）。"""
    # 长度守卫（S5a 审查 minor 2）：`_diff_probs` / `_snapshot_facts` 用 `zip`，
    # 两侧长度不等时会被静默截断到较短一侧、「等价」就此成立。经 `run_trace`
    # 产生的两侧必然同长，故当前不可达；但本装置是 S5b / S5c 的验收入口，将来
    # 一旦出现单侧截断（引擎路径、池过滤、异常吞掉）就是静默绿色，故前移到此处。
    if not (len(old.probs) == len(new.probs)
            and len(old.snapshots) == len(new.snapshots)):
        raise AssertionError(
            f'两侧轨迹长度不等（probs {len(old.probs)} vs {len(new.probs)}；'
            f'snapshots {len(old.snapshots)} vs {len(new.snapshots)}）：'
            f'比对会被静默截断，拒绝执行')
    report = EquivalenceReport(
        old=old, new=new, tolerance=tolerance, snapshot_policy=snapshot_policy)
    cmp_old, cmp_new = _align_sides(old, new)
    report.prob_mismatches, report.max_prob_diff, report.bit_exact = _diff_probs(
        cmp_old.probs, cmp_new.probs, tolerance)
    if old.readonly_probs and new.readonly_probs:
        report.readonly_mismatches, _, _ = _diff_probs(
            cmp_old.readonly_probs, cmp_new.readonly_probs, tolerance)
    problems, extra, missing = _snapshot_facts(
        old.snapshots, new.snapshots, old.init_snapshot, new.init_snapshot)
    report.snapshot_mismatches = problems
    report.extra_new_keys = extra
    report.missing_new_keys = missing
    report.unlisted_extra_keys = extra - snapshot_policy.allowed_new_only_keys
    report.stale_allowed_keys = snapshot_policy.allowed_new_only_keys - extra
    report.did_fire_divergent_draws = [
        i for i, (a, b) in enumerate(zip(old.did_fire, new.did_fire)) if a != b]
    return report


def compare_runs(
    pdef: PityDef,
    steps: Sequence[DrawStep],
    *,
    shape: PoolShape,
    seed: int = 20261011,
    tolerance: Tolerance,
    snapshot_policy: Optional[SnapshotPolicy] = None,
    probe_readonly: bool = True,
    allow_vacuous: bool = False,
) -> EquivalenceReport:
    """`run_old` + `run_new` + `compare_traces` 的一步式入口（S5b 的批次主入口）。"""
    policy = snapshot_policy or registered_snapshot_policy(pdef)
    old = run_old(pdef, steps, shape=shape, seed=seed, probe_readonly=probe_readonly)
    new = run_new(pdef, steps, shape=shape, seed=seed, probe_readonly=probe_readonly)
    # 非空转闸门（S5a 审查 important 1）：旧侧轨迹与基础分布逐抽相同，说明该
    # fixture 下这条机制**从未触发**，此时「两侧一致」是空断言（`hard` 的阈值
    # 超出序列长度、`soft` 的保底起点够不着、`targeted` 的定子不可达等都会落到
    # 这一格）。S5b 要在此装置上叠十个批次，任一批次的 fixture 写错即「零覆盖
    # 全绿」，故把它前移到装置属性而非靠个别用例手写自检。
    if not old.changed_beyond_ulp and not allow_vacuous:
        raise AssertionError(
            f'装置空转（S5a 审查 important 1；判据按 S5b 审查 important 1 收严为'
            f'「超出 4 ULP 噪声」）：{pdef.name}（{pdef.btype}）的旧侧轨迹与基础分布'
            f'没有超出浮点噪声的差别，即该 config 下机制从未触发，「两侧一致」不构成'
            f'等价性证据。请让 fixture 真的触发机制（阈值/起点落在序列内等）；'
            f'若确要比一个不触发的形态，传 allow_vacuous=True 并自述理由。'
            f'（注：事件驱动型的旧类在非触发分支也重算一遍，故严格不等判据对它恒真）')
    return compare_traces(old, new, tolerance=tolerance, snapshot_policy=policy)


def assert_equivalent(
    pdef: PityDef,
    steps: Sequence[DrawStep],
    *,
    shape: PoolShape,
    seed: int = 20261011,
    tolerance: Tolerance,
    snapshot_policy: Optional[SnapshotPolicy] = None,
    probe_readonly: bool = True,
    allow_vacuous: bool = False,
) -> EquivalenceReport:
    """比对并断言等价；不等价时抛出带全部差异项的 `AssertionError`。"""
    report = compare_runs(
        pdef, steps, shape=shape, seed=seed, tolerance=tolerance,
        snapshot_policy=snapshot_policy, probe_readonly=probe_readonly,
        allow_vacuous=allow_vacuous)
    messages = report.failure_messages()
    if messages:
        raise AssertionError(
            f"保底 '{pdef.name}'（type={pdef.btype}）旧/新不等价：\n  "
            + '\n  '.join(messages))
    return report


# ══════════════════════════════════════════════════════════════════
# 六、fixture 构造（显式处理已知的两处取值分叉）
# ══════════════════════════════════════════════════════════════════

#: 判据用的 soft RLE 段表（counter 4 起每抽 +6 个百分点）。
SOFT_DELTAS = ((3, 0.0), (4, 6.0))


def counter_fixture(**kwargs) -> PityDef:
    """counter 驱动型 fixture：`deltas` 与语法糖都由调用方显式给出。"""
    return PityDef(**kwargs)


def soft_fixture(name: str, btype: str, **kwargs) -> PityDef:
    """三个 `_soft` 后缀类型的 fixture：**按 TOML 形态同时写两个 deltas 字段**。

    `config_toml._build_pity` 对 `deltas` 键的处理是「同一份解析结果同时填
    `PityDef.deltas` 与 `PityDef.soft_deltas`」，故 TOML 直载路径下这两个字段同源，
    新旧两侧的取值差异被掩盖。而本装置**直构 `PityDef`**，若只写 `deltas`，
    两侧会分别取到不同来源（新读 `deltas`、旧只读 `soft_deltas`）而分叉。
    本 fixture 强制两个字段同源，使 `_soft` 批次的等价性主张成立；
    该分叉本身由 `test_registered_soft_deltas_source_divergence` 显式登记。

    `kwargs` 里显式给出的 `deltas` / `soft_deltas` 优先，便于构造「只写一侧」的
    登记用例。
    """
    deltas = kwargs.pop('deltas', SOFT_DELTAS)
    soft_deltas = kwargs.pop('soft_deltas', deltas)
    return PityDef(name=name, btype=btype, deltas=deltas,
                   soft_deltas=soft_deltas, **kwargs)


def _default_shape() -> PoolShape:
    return make_pool_shape(DEFAULT_CARDS)


# ══════════════════════════════════════════════════════════════════
# 七、S5a 装置自检
# ══════════════════════════════════════════════════════════════════


class TestDeviceSelfCheck:
    """装置自检：只验证「装置能跑、能比、能报、能红」，不承担逐类型覆盖。

    逐类型的等价性批次归 S5b，三条强制约束的专项断言归 S5c。
    """

    @pytest.mark.parametrize(
        'steps',
        [DRAW_SEQUENCE, make_draw_sequence(120)],
        ids=['脚本序列', '生成序列120'],
    )
    def test_hard_single_type_bit_exact(self, steps):
        """S5a 验收：1 个类型（counter 驱动的 `hard`）在位级口径下逐场一致。

        选 `hard` 作装置自检的理由：它是两侧**共用同一套绝对赋值公式**的类型
        （`HardModifier` 与旧 `HardPityBehavior` 的 `w / Σw` 同序），实测位级
        一致、快照键集也一致，故能同时给「分布位级一致」与「快照无白名单」
        两条装置能力作正例。两条序列（手写脚本 / `make_draw_sequence()` 长序列）
        同时跑，顺带证明装置对抽卡序列形态不敏感。
        """
        pdef = counter_fixture(name='rig_hard', btype='hard', scope='ssr', threshold=6)
        report = assert_equivalent(
            pdef, steps, shape=_default_shape(), tolerance=EXACT,
            snapshot_policy=NO_EXTRA_KEYS)
        assert report.bit_exact
        assert report.extra_new_keys == frozenset()
        assert report.missing_new_keys == frozenset()
        assert report.did_fire_divergent_draws == []
        assert report.rng_calls_equal
        # 旧侧必须跑出非恒等分布（AUDIT-BREAK-D 的装置侧守卫）
        assert report.old.changed_from_base
        assert report.new.changed_from_base

    def test_device_reports_inequivalence_for_mismatched_configs(self):
        """负控：装置对不同配置必须**报不等价**。

        没有这条，整套装置的「通过」可能来自「恒绿」。这里故意把旧侧配
        `threshold=7`、新侧配 `threshold=6`，断言报告非空且指向阈值触发的那几抽。
        """
        shape = _default_shape()
        old_pdef = counter_fixture(name='rig_hard', btype='hard', scope='ssr', threshold=7)
        new_pdef = counter_fixture(name='rig_hard', btype='hard', scope='ssr', threshold=6)
        report = compare_traces(
            run_old(old_pdef, DRAW_SEQUENCE, shape=shape),
            run_new(new_pdef, DRAW_SEQUENCE, shape=shape),
            tolerance=EXACT, snapshot_policy=NO_EXTRA_KEYS)
        assert not report.is_equivalent()
        assert report.prob_mismatches
        assert report.max_prob_diff > 1e-3

    def test_direct_drive_is_faithful_to_engine_schedule(self):
        """装置自检：直驱新骨架与走 `PityEngine` 全管道的产物同结果。

        装置为了与旧类对称而直驱 behavior（旧类在 registry 上已无入口），故必须
        自证「直驱没有绕过引擎的调度语义」（引擎会 rebind、会把计数器初值经
        `env.pity_state_init` 送进来）。本用例对 `rotating` 比对两条路径的分布与
        快照；不一致即说明直驱漏了生产路径的某一环。

        **另含 CR 型**（S5a 审查 minor 7）：`rotating` 不掷骰、两侧 `rng_calls`
        恒 0/0，只测它时那条随机数断言是空的；`rotating_cr` 的掷骰在 `prepare`，
        故补一条把随机数消费纳入判别面。
        """
        shape = _default_shape()
        seen_rng = 0
        for pdef in (
            counter_fixture(name='rig_rot', btype='rotating', scope='ssr'),
            counter_fixture(name='rig_cr', btype='rotating_cr', scope='ssr',
                            cr_counter_threshold=3, cr_base_rate=0.018,
                            cr_state_probs=(0.0, 0.0, 0.75, 1.0)),
        ):
            direct = run_new(pdef, DRAW_SEQUENCE, shape=shape)
            via_engine = run_new_via_engine(pdef, DRAW_SEQUENCE, shape=shape)
            assert direct.probs == via_engine.probs, pdef.name
            assert direct.snapshots == via_engine.snapshots, pdef.name
            assert direct.rng_calls == via_engine.rng_calls, pdef.name
            seen_rng = max(seen_rng, direct.rng_calls)
        assert seen_rng > 0, '两条路径的随机数消费断言均无判别力（rng_calls 恒 0）'


    def test_gate_rejects_semantically_inert_event_driven_fixture(self):
        """负控：事件驱动型的 fixture 未触发机制时，空转闸门必须拒绝。

        S5b 审查 important 1：旧类在非触发分支也走 `_redistribute_scope()` 重算，
        与基础分布恒有 1 ULP 量级差，故旧的严格不等判据对它恒真、挡不住空转。
        本条用「全 R 序列」（无任何 SSR，`rotating` 的 guaranteed 分支永不触发）
        钉住收严后的语义判据。
        """
        steps = tuple(R_DRAW for _ in range(40))
        pdef = counter_fixture(name='vac_rot', btype='rotating', scope='ssr')
        with pytest.raises(AssertionError, match='装置空转'):
            compare_runs(pdef, steps, shape=_default_shape(), tolerance=FLOAT_ORDER)

    def test_length_guard_rejects_mismatched_traces(self):
        """负控：两侧轨迹长度不等时 `compare_traces` 必须拒绝（S5a 审查 minor 2）。

        无此守卫时 `zip` 会把比对静默截断到较短一侧、「等价」就此成立。
        """
        shape = _default_shape()
        pdef = counter_fixture(name='len_guard', btype='hard', scope='ssr', threshold=6)
        old = run_old(pdef, DRAW_SEQUENCE, shape=shape)
        new = run_new(pdef, DRAW_SEQUENCE[:5], shape=shape)
        with pytest.raises(AssertionError, match='长度不等'):
            compare_traces(old, new, tolerance=EXACT,
                           snapshot_policy=registered_snapshot_policy(pdef))

    def test_device_shape_makes_soft_transfer_live(self):
        """装置形状自检：软保底的转移**必须真的发生**，否则装置在空转。

        守的是 `PoolShape.rarity_rank` 的语义方向（见 `RARITY_RANK` 的注释）：
        写成倒序时 `SoftModifier` 的 `pool <= 0` 提前恒等，两侧同为恒等，
        「等价」变成空断言。断言取全程最大 SSR 总量（`DRAW_SEQUENCE` 的 counter
        在第 18 抽爬到 10，boost 累计 42 个百分点），不写死抽次索引。
        """
        shape = _default_shape()
        base_ssr = sum(v for k, v in shape.base_probabilities.items() if k.startswith('ssr'))
        pdef = counter_fixture(name='rig_soft', btype='soft_step', scope='ssr',
                               deltas=SOFT_DELTAS)
        trace = run_new(pdef, DRAW_SEQUENCE, shape=shape)
        peak = max(sum(v for k, v in to_slots(probs, shape, space=trace.space).items()
                       if k.startswith('ssr'))
                   for probs in trace.probs)
        assert peak > base_ssr + 0.3, (
            f'全程最大 SSR 总量 {peak:.4f} 未显著高于基础 {base_ssr:.4f}：'
            '软保底未生效（多半是 rarity_rank 方向写反）')

    def test_tolerance_requires_rationale(self):
        """装置纪律：容差是决策点，必须自述理由（禁止匿名魔数）。"""
        with pytest.raises(ValueError):
            Tolerance('absolute', 1e-9, '   ')

    def test_snapshot_policy_requires_rationale(self):
        """装置纪律：白名单同样必须自述理由。"""
        with pytest.raises(ValueError):
            SnapshotPolicy(frozenset({('a', 'b')}), '')


# ══════════════════════════════════════════════════════════════════
# 八、已登记差异（不掩盖，逐条断定差异存在）
# ══════════════════════════════════════════════════════════════════


class TestRegisteredDifferences:
    """已登记差异的显式载体。

    本类的用例**不断言等价**，而是断言「差异以已知的形状存在」。它们的作用有三：

    1. 把差异写进可执行的代码，而不是只写在计划文档里；
    2. 差异消失时（例如 `Modifier` 改为复刻旧 `_redistribute_scope` 的重算式）
       用例立刻变红，逼出「按 §六 字面口径收严为 EXACT」的裁决动作；
    3. 差异扩大时同样变红（幅值有上界断言），防止把真实回归当成「已知差异」放行。
    """

    def test_registered_ulp_in_event_driven_non_trigger_branch(self):
        """六个事件驱动型的**非条件分支**存在 1 ULP 位级差（§六 字面「位级一致」的冲突点）。

        来源：条件不成立时新 `RotatingModifier` / `SelectedModifier` 直接返回恒等
        （`return None`），旧类走 `_redistribute_scope()` 重算一遍
        （`featured_total = total * ratio` 后再 `* w / Σw`），浮点往返引入 1 ULP 差。
        """
        shape = _default_shape()
        pdef = counter_fixture(name='rig_rot', btype='rotating', scope='ssr')

        strict = compare_runs(pdef, DRAW_SEQUENCE, shape=shape, tolerance=EXACT)
        assert not strict.is_equivalent(), (
            '非条件分支的 1 ULP 差已消失：请按 §六 主线字面口径把本类型的容差'
            '收严为 EXACT，并删除本登记用例与模块 docstring 的对应行')
        assert strict.prob_mismatches
        assert not strict.bit_exact

        relaxed = compare_runs(pdef, DRAW_SEQUENCE, shape=shape, tolerance=FLOAT_ORDER)
        assert relaxed.is_equivalent(), relaxed.failure_messages()

        # 幅值上界：差异必须停留在「几个 ULP」量级，超出即回归而非已知差异。
        # 上界由**发生差异的那些槽位自身的取值**推出（不写死常数）。
        affected = max(max(abs(m.old), abs(m.new)) for m in strict.prob_mismatches)
        assert 0.0 < relaxed.max_prob_diff <= 4 * math.ulp(affected)
        assert strict.max_prob_diff == relaxed.max_prob_diff

    def test_registered_extra_state_keys_are_exactly_whitelisted(self):
        """快照白名单是**精确集合**：多出键须逐项登记，未登记与陈旧项都判失败。

        覆盖两类已登记多出键：

        - `_active`：`Lifecycle.initialize` 的统一写入（ISSUE-202），六个事件驱动
          型全中，旧 `RotatingBehavior` / `TargetedBehavior` 一族不写；
        - `cr_intercepted`：`StreakTracker` 的拦截标记，`rotating_cr` /
          `rotating_cr_soft` 两型独有。
        """
        shape = _default_shape()
        pdef = counter_fixture(
            name='rig_cr', btype='rotating_cr', scope='ssr',
            cr_counter_threshold=3, cr_base_rate=0.018,
            cr_state_probs=(0.0, 0.4, 0.75, 1.0))

        registered = registered_snapshot_policy(pdef)
        assert registered.allowed_new_only_keys == frozenset({
            ('rig_cr', '_active'), ('rig_cr', 'cr_intercepted')})

        report = compare_runs(pdef, DRAW_SEQUENCE, shape=shape, tolerance=FLOAT_ORDER)
        assert report.extra_new_keys == registered.allowed_new_only_keys
        assert report.missing_new_keys == frozenset()
        assert report.unlisted_extra_keys == frozenset()
        assert report.stale_allowed_keys == frozenset()
        assert report.is_equivalent(), report.failure_messages()

        # 空白名单下，多出的键必须全部落到「未登记」里（证明白名单不是一律放过）
        strict = compare_traces(
            report.old, report.new, tolerance=FLOAT_ORDER,
            snapshot_policy=SnapshotPolicy(frozenset(), '负控：故意不登记任何多出键'))
        assert strict.unlisted_extra_keys == registered.allowed_new_only_keys
        assert not strict.is_equivalent()

        # 陈旧白名单：登记一个实际不存在的键必须判失败
        stale = compare_traces(
            report.old, report.new, tolerance=FLOAT_ORDER,
            snapshot_policy=SnapshotPolicy(
                registered.allowed_new_only_keys | {('rig_cr', 'never_written')},
                '负控：白名单含陈旧项'))
        assert stale.stale_allowed_keys == frozenset({('rig_cr', 'never_written')})
        assert not stale.is_equivalent()

    @pytest.mark.parametrize('btype', sorted(_SOFT_SUFFIX_BTYPES))
    def test_m4_registered_did_fire_relaxation_for_soft_suffix_types(self, btype):
        """M4 登记的放宽（ISSUE-102）：三个 `_soft` 复合类型的 `did_fire` 由
        「出 scope ∧ 命中」放宽为「出 scope」。

        骨架的 `Pity.did_fire = any(tr.did_reset(...))` 取**任一** Tracker 的重置，
        而这三个类型的 preset 同时含「事件驱动 Tracker（命中才翻转）」与「触发
        稀有度 counter Tracker（出 scope 即重置）」，旧实现只有前者参与
        `did_fire`（后者在 mixin 里，mixin 不定义 `did_fire`）。

        断言形态取**语义**而非抽次索引：差异面恰为「出 scope 稀有度且未命中」的
        那些抽，方向恒为旧 False / 新 True。抽卡序列改动时本用例自动跟随。
        """
        shape = _default_shape()
        steps = DRAW_SEQUENCE
        pdef = soft_fixture(name='rig_soft', btype=btype, scope='ssr',
                            fate_threshold=2, counter_init=0)
        report = compare_runs(pdef, steps, shape=shape, tolerance=FLOAT_ORDER)

        expected = {i for i, s in enumerate(steps)
                    if s.rarity == 'ssr' and not s.is_featured}
        assert set(report.did_fire_divergent_draws) == expected, (
            'M4 放宽的差异面与「出 scope 但未命中」不再重合：'
            '要么放宽被撤销（须按 §六 的 ISSUE-102 条目改回并更新登记），'
            '要么 scope 门控被破坏（回归）')
        for i in sorted(expected):
            assert report.old.did_fire[i] is False
            assert report.new.did_fire[i] is True
        # 差异只落在 did_fire 上：分布与快照仍按 FLOAT_ORDER 口径等价
        assert not report.prob_mismatches
        assert report.is_equivalent(), report.failure_messages()

    def test_registered_soft_deltas_source_divergence(self):
        """三个 `_soft` 后缀类型的 deltas 取值源分叉（新读 `pdef.deltas`，旧只读
        `pdef.soft_deltas`）。

        直构 `PityDef(deltas=...)`（`soft_deltas` 缺省）时两侧不同源：新按
        `pdef.deltas` 生效，旧 mixin 落到 `soft_start` 缺省 74 / `soft_end` 缺省 90
        的语法糖展开。TOML 直载路径把两字段写成同源，故真实配置不踩；本用例把
        「只写 `deltas`」的直构形态显式登记，并给出 fixture 规则
        （`soft_fixture()` 同时写两个字段），使 S5b 的 `_soft` 批次有据可依。
        """
        shape = _default_shape()
        pdef_split = PityDef(name='rig_soft', btype='rotating_soft', scope='ssr',
                             deltas=SOFT_DELTAS, soft_deltas=None)
        report_split = compare_runs(
            pdef_split, DRAW_SEQUENCE, shape=shape, tolerance=FLOAT_ORDER)
        assert not report_split.is_equivalent(), (
            'deltas 取值源的两侧分叉已消失（旧 mixin 也开始读 pdef.deltas？）：'
            '请删除本登记并更新 soft_fixture() 的说明')
        assert report_split.max_prob_diff > 1e-3, (
            '两侧差异应远大于浮点量级（旧侧软保底在第 74 抽才起效）')

        pdef_same = soft_fixture(name='rig_soft', btype='rotating_soft', scope='ssr')
        report_same = compare_runs(
            pdef_same, DRAW_SEQUENCE, shape=shape, tolerance=FLOAT_ORDER)
        assert report_same.is_equivalent(), report_same.failure_messages()


# ══════════════════════════════════════════════════════════════════
# 九、H4：短路条件下的随机数消费（S5c 的完整断言在此叠加）
# ══════════════════════════════════════════════════════════════════


class TestH4RandomConsumption:
    """H4 的骨架面：`rotating_cr` 族在「拦截掷骰」路径上的随机数消费。

    S5a 只交付骨架与 `cr_state_probs` 中间值用例。**S5c 仍须在此文件补**：
    `cr_base_rate == 0` 与 `cr_state_probs` 含 `0` 两条「不消耗」路径的逐位断言，
    以及「只读查询不消耗随机数」「掷骰失败后 flag 必须为假」两条负例。
    """

    def test_h4_cr_state_probs_intermediate_value(self):
        """`cr_state_probs` 含 `(0, 1)` 开区间中间值时，两侧随机数消费逐位相同。

        `(0.0, 0.4, 0.75, 1.0)` 让三档分别落在「不掷」「掷」「掷」「确定性触发」
        四条分支上；两侧的掷骰都在抽前相位（旧 `RotatingCRBehavior.before_draw` /
        新 `StreakTracker.prepare`），故消费次数与次序应当一致。
        """
        shape = _default_shape()
        pdef = counter_fixture(
            name='rig_cr', btype='rotating_cr', scope='ssr',
            cr_counter_threshold=3, cr_base_rate=0.018,
            cr_state_probs=(0.0, 0.4, 0.75, 1.0))
        report = compare_runs(pdef, DRAW_SEQUENCE, shape=shape, tolerance=FLOAT_ORDER)
        assert report.rng_calls_equal, (
            f'随机数消费次数不同: old={report.old.rng_calls} new={report.new.rng_calls}')
        assert report.is_equivalent(), report.failure_messages()

        # 「中间值确实消耗了随机数」的显形：把中间档压成 0（只剩确定性与
        # base_rate 两处掷骰点），同序列同种子下的消费次数必然更少。
        zeroed = counter_fixture(
            name='rig_cr', btype='rotating_cr', scope='ssr',
            cr_counter_threshold=3, cr_base_rate=0.018,
            cr_state_probs=(0.0, 0.0, 0.0, 1.0))
        zero_report = compare_runs(
            zeroed, DRAW_SEQUENCE, shape=shape, tolerance=FLOAT_ORDER)
        assert zero_report.rng_calls_equal
        assert report.old.rng_calls > zero_report.old.rng_calls


# ══════════════════════════════════════════════════════════════════
# 十、S5b 批次一：counter 驱动 4 类（hard / soft_step / soft_interval / soft_additive）
# ══════════════════════════════════════════════════════════════════
#
# 本批覆盖 `BEHAVIOR_REGISTRY` 的 counter 驱动四型，并落地 §七 S5b 的两条强制追加：
# `ISSUE-403`（`target_featured` 的两条 `hard` 用例 + 三条 soft 硬拒）与
# `_soft_deltas_of` 分支 ③ 的行为差异登记。
#
# **容差取 `EXACT` 的理由（§六 主线口径）**：counter 驱动的四型两侧共用同一套
# 绝对赋值公式（`HardModifier` / `SoftModifier` 与旧 `HardPityBehavior` /
# `SoftStepBehavior` 同为 `w / Σw` 且同序），实测逐抽 `max_prob_diff == 0.0`、
# 快照无多出键、无缺失键。故 §六 主线字面的「概率分布 = 容差 1e-12 内」在本批
# **以位级一致满足**，无须动用任何容差（1e-12 是事件驱动六型才需要的放宽）。

#: counter 驱动批次的 fixture 表。逐条取**非默认**值（§六 ISSUE-030：「非默认
#: threshold / scope / counter_init 下 preset 与旧类逐场一致」）：`hard` 走非默认
#: threshold + counter_init 与 `reset='featured'` 两条，软保底三型各取一种 deltas
#: 来路（直写 `deltas` / `soft_interval` 语法糖 / `soft_additive` 语法糖），
#: 并含 `scope='sr'` 一条横向变体。
COUNTER_BATCH: Tuple[Tuple[str, Callable[[], PityDef]], ...] = (
    ('hard_threshold+counter_init', lambda: counter_fixture(
        name='b1_hard', btype='hard', scope='ssr', threshold=6, counter_init=2)),
    ('hard_reset=featured', lambda: counter_fixture(
        name='b1_hard_rf', btype='hard', scope='ssr', threshold=6, reset='featured')),
    ('soft_step', lambda: counter_fixture(
        name='b1_soft_step', btype='soft_step', scope='ssr', deltas=SOFT_DELTAS)),
    ('soft_step_scope=sr', lambda: counter_fixture(
        name='b1_soft_step_sr', btype='soft_step', scope='sr', deltas=SOFT_DELTAS)),
    ('soft_interval_sugar', lambda: counter_fixture(
        name='b1_soft_interval', btype='soft_interval', scope='ssr',
        soft_start=5, soft_end=40)),
    ('soft_additive_sugar', lambda: counter_fixture(
        name='b1_soft_additive', btype='soft_additive', scope='ssr',
        soft_start=5, soft_end=40, soft_increment=8.0)),
)


class TestS5bCounterDrivenBatch:
    """S5b 批次一：counter 驱动 4 类的等价性 + §七 S5b 的两条强制追加。"""

    @pytest.mark.parametrize('make', [c[1] for c in COUNTER_BATCH],
                             ids=[c[0] for c in COUNTER_BATCH])
    def test_batch_equivalence_within_s8_tolerance(self, make):
        """counter 驱动 4 型的等价性：**容差取 §六 的 S8 口径 1e-12**。

        S8 前本用例取 `EXACT`（位级一致），理由是「两侧同为绝对赋值、算式逐字同源」；
        S8 起新侧改为**卡级增量**（A 加 `p(Q)`、Q 减 `p(Q)`），与旧侧的槽位级
        「除再乘往返」不再逐位同源，故按 §六 的 S8 口径取 `FLOAT_ORDER`（1e-12）：
        该数值即 S8 与 S5 产物对比所用，非本用例新造。**状态快照仍按位级比对**
        （`SnapshotPolicy`，不随本改动放宽）。
        """
        pdef = make()
        report = assert_equivalent(
            pdef, DRAW_SEQUENCE, shape=_default_shape(), tolerance=FLOAT_ORDER)
        assert report.extra_new_keys == frozenset()
        assert report.missing_new_keys == frozenset()
        assert report.did_fire_divergent_draws == []
        assert report.rng_calls_equal, (
            f'{pdef.name}: 随机数消费次数不同 '
            f'old={report.old.rng_calls} new={report.new.rng_calls}')
        # 非空转（装置已对旧侧设闸，此处对两侧同时断言：任一侧恒等都说明该 config
        # 下机制从未触发，「两侧一致」不构成证据）
        assert report.old.changed_from_base and report.new.changed_from_base

    def test_issue403_hard_target_featured_narrows_target_set(self):
        """ISSUE-403 ①：`target_featured=True` 的 `hard` 目标集**收窄为 featured 卡集**。

        判别面用同一阈值下的 `target_featured=False` 变体作对照：两条配置在触发抽上
        的分布必须不同（`tf=True` → featured 槽 1.0 / standard 槽 0.0；`tf=False` →
        两槽各 0.5）。preset 漏写 `target=` 时 `HardModifier` 的 `target` 落到缺省
        `'scope'`，两种配置的分布**合并为一**，本断言即红：`_target_of(pdef)` 在
        该批次里别无第二个捕获面（静默放宽、不报错）。
        """
        shape = _default_shape()
        pdef_tf = counter_fixture(name='b1_hard_tf', btype='hard', scope='ssr',
                                  threshold=6, target_featured=True)
        pdef_scope = counter_fixture(name='b1_hard_tf', btype='hard', scope='ssr',
                                     threshold=6, target_featured=False)

        report = assert_equivalent(pdef_tf, DRAW_SEQUENCE, shape=shape,
                                   tolerance=FLOAT_ORDER)
        scoped = compare_runs(pdef_scope, DRAW_SEQUENCE, shape=shape,
                              tolerance=FLOAT_ORDER)

        trigger = next(i for i, p in enumerate(report.new.probs)
                       if p != report.new.base_probabilities)
        tf_draw = to_slots(report.new.probs[trigger], shape, space=report.new.space)
        scoped_draw = to_slots(scoped.new.probs[trigger], shape, space=scoped.new.space)
        assert tf_draw['ssr_featured'] == 1.0 and tf_draw['ssr'] == 0.0, (
            f'第 {trigger} 抽 target_featured=True 的目标集未收窄到 featured：{tf_draw}')
        assert scoped_draw['ssr_featured'] == 0.5 and scoped_draw['ssr'] == 0.5, (
            f'第 {trigger} 抽 target_featured=False 的目标集非 scope 全集：{scoped_draw}')
        assert tf_draw != scoped_draw

    def test_issue403_hard_target_featured_empty_featured_falls_back_to_scope(self):
        """ISSUE-403 ②：该 scope **无 featured 卡**时目标集回退 scope 全集。

        取 `sr` 作 scope（`DEFAULT_CARDS` 里 `sr` 只有非 featured 的 `sr1`）。断言面是
        「回退**真的发生**」：同 scope 上 `tf=True` 与 `tf=False` 的两侧分布逐位相同
        （目标集都等于 scope 全集）。缺回退时 `HardModifier._target_cards()` 给空集、
        `compute_delta` 走 `if not A: return None` 恒等，而另一侧照常转移，该断言即红。

        **S8-2 起本用例不再断言「与旧类逐场一致」**：`hard(scope='sr')` 正是 §六 差异
        归因清单 (a) 登记的配置（`scope` 低于最高稀有度）：M1 的 F 型是「绝对赋值 +
        更高稀有度豁免」（实测 `{ssr_featured: 0.2, ssr: 0.2, sr: 1.0, r: 0.0}`、
        Σ = 1.4），S8 是「A 收下 p(Q)、更高稀有度不写增量」（`{f1: 0.2, s1: 0.2,
        sr1: 0.6, r1: 0.0}`、Σ = 1.0），两侧**本就不等价**（最大差 0.4，非回归）。
        跨侧等价性对本配置不成立，故本用例只做**同侧**自比（两条配置的分布相同 +
        两侧各自的回退事实）。

        另覆盖旧实现回退分支的**缺键形态**：`featured_slots` 连该 scope 的键都没有
        （走 `.get(scope, scope_slots)` 的缺省参数），结果同为 scope 全集。
        """
        shape = _default_shape()
        pdef_tf = counter_fixture(name='b1_hard_sr_tf', btype='hard', scope='sr',
                                  threshold=3, target_featured=True)
        pdef_scope = counter_fixture(name='b1_hard_sr_tf', btype='hard', scope='sr',
                                     threshold=3, target_featured=False)

        report = compare_runs(pdef_tf, DRAW_SEQUENCE, shape=shape,
                              tolerance=FLOAT_ORDER)
        scoped = compare_runs(pdef_scope, DRAW_SEQUENCE, shape=shape,
                              tolerance=FLOAT_ORDER)
        assert report.new.probs == scoped.new.probs
        assert report.old.probs == scoped.old.probs
        assert report.new.changed_from_base, '空集回退若退化为恒等，本用例失去判别力'

        # 缺键形态：`featured_slots` 删去 `sr` 键（旧 `.get(scope, scope_slots)` 的
        # 缺省分支）。本装置可手工构造；生产 `compute_scope_mappings` 不会产出该形状
        # （无 featured 卡时它填 scope 槽本身），故它是防御性覆盖而非生产路径。
        keyless_shape = dataclasses.replace(
            shape,
            featured_slots={k: v for k, v in shape.featured_slots.items() if k != 'sr'})
        keyless = compare_runs(pdef_tf, DRAW_SEQUENCE, shape=keyless_shape,
                               tolerance=FLOAT_ORDER)
        assert keyless.new.probs == report.new.probs

    @pytest.mark.parametrize('btype', ('soft_interval', 'soft_additive', 'soft_step'))
    def test_issue403_soft_counter_types_reject_target_featured(self, btype):
        """7B 硬拒（§3.2.1 落地面 ①）：counter 驱动三软类型配 `target_featured=True`
        时 `create_behavior` 抛 `ConfigError`。

        校验点必须是 `create_behavior`（而非 `_build_pity`）：本文件的等价性装置与
        任何直构 `PityDef` 的路径都绕过 TOML 层，防线须盖住构造入口。同用例内以
        `hard` 作正对照，防止本断言靠「一律拒绝」通过。
        """
        pdef = counter_fixture(name='b1_reject', btype=btype, scope='ssr',
                               soft_start=5, soft_end=40, target_featured=True)
        with pytest.raises(ConfigError):
            create_behavior(pdef, initial_state(pdef))

        ok = counter_fixture(name='b1_reject_ok', btype='hard', scope='ssr',
                             threshold=6, target_featured=True)
        create_behavior(ok, initial_state(ok))   # `hard` 侧不得被牵连

    @pytest.mark.parametrize('btype', ('soft_interval', 'soft_additive'))
    def test_registered_counter_soft_deltas_default_divergence(self, btype):
        """登记的差异：counter 驱动软类型的 `deltas` 与语法糖**全缺省**时，旧路径
        构造即失败（`SoftStepBehavior.__init__` 的 `deltas=None` 检查；生产路径上该
        保底被引擎吞成 warning 后整条消失），新 `_soft_deltas_of` 分支 ③ 按 74 / 90
        缺省展开、软保底**真的生效**。

        本用例**不断言等价**，只断言两侧各自的事实：方向是「从静默消失变为按缺省
        生效」（`_soft_deltas_of` 的 docstring 登记「须由 S5b 的 counter 驱动批次或
        §六 口径一并覆盖」），属修复方向。新侧的生效面取全 `R` 长序列把 counter 推过
        `soft_end=90`，此时 boost 封顶 100 → 转移量 `t = min(1.0, p(Q))` → scope 总
        概率恰为 1.0（不是「大于基础值」这类带余量的弱断言）。
        `soft_step` 不在本用例内：它无语法糖可回退（旧分支对 `soft_step` 不展开），
        行为面与另两型不同。
        """
        shape = _default_shape()
        pdef = counter_fixture(name='b1_soft_default', btype=btype, scope='ssr')
        with pytest.raises(ValueError):
            build_old(pdef, initial_state(pdef))

        trace = run_new(pdef, (R_DRAW,) * 200, shape=shape)
        assert trace.changed_from_base
        peak = max(sum(v for k, v in to_slots(probs, shape, space=trace.space).items()
                       if k.startswith('ssr'))
                   for probs in trace.probs)
        assert peak == 1.0, f'{btype} 的 74/90 缺省展开未生效（峰值 SSR 总量 {peak!r}）'


# ══════════════════════════════════════════════════════════════════
# 十·五、S8 的**跨块断言**（§七 S8 的 ⚠ 原子单元段）
# ══════════════════════════════════════════════════════════════════


class TestS8CardLevelCrossBlock:
    """S8 三块（S8-1 接口 / S8-2 管道换卡级 / S8-3 助手）的**跨块断言**。

    §七 的 ⚠ 段要求三块同一个 commit 落地，理由是**任一中间态都是键空间错位窗口**：
    `_apply_delta` 的 `d.get(c, 0.0)` 把「未在增量向量里出现的键」当作恒等 0.0，
    于是增量键与 `dist` 键不匹配时**不报错**，只让全部保底静默退化为恒等。该段同时
    要求补一条跨块断言，使该形态在 CI 期即暴露：本类即该断言。

    判据三条（缺一即可能假绿）：

    1. **两侧都真的改了分布**（`changed_beyond_ulp`）：任一侧恒等时「一致」是空断言；
    2. **逐元素一致且容差为 §六 的 S8 口径 1e-12**（`max_prob_diff` 打出来，
       不写「恰好能过」的匿名魔数）；
    3. 比对面是**同一键空间**（本装置把卡级侧按 `card_to_slot` 投影到槽位级；两个
       池形每槽恰含一张卡，故投影是双射、逐元素对照成立）。

    覆盖 4 个 counter 驱动型（S8-1 的 `compute_delta` 与 S8-3 的 `transfer_linear`
    在这四型上都被走到）与 2 个事件驱动型（`rotating` / `targeted`，覆盖条件内联与
    单卡定向两条路径）。
    """

    #: 跨块比对的配置（名称 → fixture 工厂）。
    @staticmethod
    def _cross_block_cases():
        return (
            ('hard', lambda: counter_fixture(name='s8_hard', btype='hard',
                                             scope='ssr', threshold=6)),
            ('soft_step', lambda: counter_fixture(name='s8_soft', btype='soft_step',
                                                  scope='ssr', deltas=SOFT_DELTAS)),
            ('soft_interval', lambda: soft_fixture(name='s8_soft_i',
                                                   btype='soft_interval', scope='ssr',
                                                   soft_start=5, soft_end=40)),
            ('soft_additive', lambda: soft_fixture(name='s8_soft_a',
                                                   btype='soft_additive', scope='ssr',
                                                   soft_start=5, soft_end=40,
                                                   soft_increment=8.0)),
            ('rotating', lambda: counter_fixture(name='s8_rot', btype='rotating',
                                                 scope='ssr')),
            ('targeted', lambda: soft_fixture(name='s8_tgt', btype='targeted',
                                              scope='ssr', fate_threshold=2,
                                              fate_points_init=0)),
        )

    @pytest.mark.parametrize('label,make', _cross_block_cases(),
                             ids=[c[0] for c in _cross_block_cases()])
    def test_card_level_pipeline_matches_m1_products_within_1e_12(self, label, make):
        pdef = make()
        report = compare_runs(pdef, DRAW_SEQUENCE, shape=_default_shape(),
                              tolerance=FLOAT_ORDER)
        assert report.is_equivalent(), report.failure_messages()
        assert report.old.changed_beyond_ulp and report.new.changed_beyond_ulp, (
            f'{label}：两侧都须真的改动分布，否则「一致」是空断言'
            f'（old={report.old.changed_beyond_ulp} new={report.new.changed_beyond_ulp}）')
        assert report.max_prob_diff <= FLOAT_ORDER.atol, (
            f'{label}：卡级管道与 M1 产物的最大逐元素差 {report.max_prob_diff!r} '
            f'超出 §六 的 S8 容差 {FLOAT_ORDER.atol!r}')
        assert report.did_fire_divergent_draws == [], (
            f'{label}：did_fire 出现差异（S8 不改变 did_fire 语义）')

    def test_cross_block_assertion_is_not_vacuous(self):
        """非空转守卫：上面那条参数化在**两侧都非恒等**的前提下才成立。

        构造一个「新侧恒等」的对照（把阈值抬到序列长度之外）：跨块断言此时应当
        自己报出「空转」，而不是静默通过：这正是 S8 的静默退化（增量键错位 →
        全部保底恒等）在 CI 期要暴露的形态。
        """
        shape = _default_shape()
        pdef = counter_fixture(name='s8_vacuous', btype='hard', scope='ssr',
                               threshold=999)
        report = compare_runs(pdef, DRAW_SEQUENCE, shape=shape,
                              tolerance=FLOAT_ORDER, allow_vacuous=True)
        assert not report.new.changed_beyond_ulp, (
            '本对照的前提是「新侧恒等」（阈值超出序列长度）')
        assert report.is_equivalent(), (
            '两侧同为恒等时分布仍逐元素一致：「一致」不构成等价性证据，'
            '故上面那条断言必须并列 `changed_beyond_ulp` 守卫')


# ══════════════════════════════════════════════════════════════════
# 十一、S5b 批次二：事件驱动 6 型
# ══════════════════════════════════════════════════════════════════
#
# 本批覆盖 `BEHAVIOR_REGISTRY` 的六个事件驱动型，并落地 §七 S5b 的 ISSUE-001 追加
# （两条语法糖分支的等价性用例）与 §六 F2 的显形用例。
#
# **容差取 `FLOAT_ORDER`（1e-12）的理由（§六 2026-10-11 同步后的口径）**：六个
# 事件驱动型的**非条件分支**实测有 1 ULP 差（条件不成立时新侧 `return None` 恒等，
# 旧侧走 `_redistribute_scope` 的「除再乘」往返）。§六 主线把口径拆成两列，浮点
# 分布一列取 1e-12（该数值即 §六 S8 与 S5 产物对比所用，非本装置新造），
# 状态快照一列仍为**位级一致**；状态机的部分（flag 布尔翻转、随机流消费次数）
# 在两种口径下都是精确比较。差异幅值的上界逐型断言为「受影响槽位取值的 4 ULP」。

#: 事件驱动批次的 fixture 表（§3.2 preset 映射表的六个事件驱动型全覆盖，
#: 另加 `guaranteed_init=True` 一条横向变体）。
EVENT_BATCH: Tuple[Tuple[str, Callable[[], PityDef]], ...] = (
    ('rotating', lambda: counter_fixture(
        name='b2_rotating', btype='rotating', scope='ssr')),
    ('rotating_guaranteed_init', lambda: counter_fixture(
        name='b2_rotating_gi', btype='rotating', scope='ssr', guaranteed_init=True)),
    ('rotating_cr', lambda: counter_fixture(
        name='b2_rotating_cr', btype='rotating_cr', scope='ssr',
        cr_counter_threshold=3, cr_base_rate=0.018,
        cr_state_probs=(0.0, 0.4, 0.75, 1.0))),
    ('rotating_soft', lambda: soft_fixture(
        name='b2_rotating_soft', btype='rotating_soft', scope='ssr')),
    ('rotating_cr_soft', lambda: soft_fixture(
        name='b2_rotating_cr_soft', btype='rotating_cr_soft', scope='ssr',
        cr_counter_threshold=3, cr_base_rate=0.018,
        cr_state_probs=(0.0, 0.4, 0.75, 1.0))),
    ('targeted', lambda: counter_fixture(
        name='b2_targeted', btype='targeted', scope='ssr',
        fate_threshold=2, fate_points_init=0)),
    ('targeted_soft', lambda: soft_fixture(
        name='b2_targeted_soft', btype='targeted_soft', scope='ssr',
        fate_threshold=2, fate_points_init=0)),
    # 命定分支（`fate_points >= τ`）的**唯一可达形态**：默认序列下 fate_points 与
    # `guaranteed` 同时置位，故命定分支只有经 `fate_points_init` 才能单独成立，
    # 见 `test_fate_branch_is_reachable_and_tau_is_consumed`。
    ('targeted_fate_points_init', lambda: counter_fixture(
        name='b2_targeted_fi', btype='targeted', scope='ssr',
        fate_threshold=1, fate_points_init=1)),
    ('targeted_soft_fate_points_init', lambda: soft_fixture(
        name='b2_targeted_soft_fi', btype='targeted_soft', scope='ssr',
        fate_threshold=1, fate_points_init=1)),
)


def _ulp_bound(report: EquivalenceReport) -> float:
    """从**超容差**报告推出差异幅值上界：受影响槽位取值的 4 ULP。

    上界由**发生差异的那些槽位自身的取值**推出（`math.ulp`），不写死常数，
    与 S5a 的 `test_registered_ulp_in_event_driven_non_trigger_branch` 同法。
    """
    if not report.prob_mismatches:
        return 0.0
    affected = max(max(abs(m.old), abs(m.new)) for m in report.prob_mismatches)
    return 4 * math.ulp(affected)


class TestS5bEventDrivenBatch:
    """S5b 批次二：事件驱动 6 型的等价性 + ISSUE-001 追加 + §六 F2 显形。"""

    @pytest.mark.parametrize('make', [c[1] for c in EVENT_BATCH],
                             ids=[c[0] for c in EVENT_BATCH])
    def test_batch_equivalence_float_order(self, make):
        pdef = make()
        report = assert_equivalent(
            pdef, DRAW_SEQUENCE, shape=_default_shape(), tolerance=FLOAT_ORDER)

        # 快照一列仍是位级：多出的键必须**恰为**登记集合，且无缺失键
        registered = registered_snapshot_policy(pdef)
        assert report.extra_new_keys == registered.allowed_new_only_keys
        assert report.missing_new_keys == frozenset()
        assert report.snapshot_mismatches == []
        assert report.rng_calls_equal, (
            f'{pdef.name}: 随机数消费次数不同 '
            f'old={report.old.rng_calls} new={report.new.rng_calls}')
        assert report.old.changed_from_base and report.new.changed_from_base

        # `did_fire` 的差异（ISSUE-102）：仅三个 `_soft` 后缀型放宽为「出 scope」，
        # 差异面必须恰为「出 scope 稀有度且未命中」的那些抽（语义式，不写抽次索引）
        expected = {i for i, s in enumerate(DRAW_SEQUENCE)
                    if s.rarity == 'ssr' and not s.is_featured}
        if pdef.btype in _SOFT_SUFFIX_BTYPES:
            assert set(report.did_fire_divergent_draws) == expected
        else:
            assert report.did_fire_divergent_draws == []

    @pytest.mark.parametrize('bid', ['rotating_soft', 'rotating_cr_soft',
                                     'targeted_soft'])
    def test_soft_suffix_order_contract_is_unobservable_in_m1(self, bid):
        """三个 `_soft` 型的 Modifier 顺序契约在 **M1 形态下不可观测**（登记项）。

        契约（该族 preset 的纪律 ③）：`SoftModifier` 在前、母类型 Modifier 在后。
        S5b 审查 important 2 称「把两者逆序在 400 抽长序列下三个种子都能分辨」，
        **该测量未能复现**：三个 `_soft` 型 × 序列长度 {400, 1200} × 种子 1..24
        共 144 组，逆序与正序的分布差异恒为 0（`compare_runs` 全部 `is_equivalent`）。

        原因是 M1 的这两个 Modifier 都是**绝对赋值**而非增量（`RotatingModifier`
        令 featured := scope 总量、`SelectedModifier` 令 selected := scope 总量），
        故「先 Soft 后母类型」与「先母类型后 Soft」塌到同一末态：Soft 的增量最终
        同样只落在 featured（或 selected）上。顺序要到 S8 的**增量形态**
        （`compute_delta` 的 `Σδ = 0` 逐步应用）才成为可观测项。

        本用例因此**不构成该契约的守卫**，只作为「长序列下三个 `_soft` 型仍等价」
        的覆盖；顺序契约的守卫须在 S8 落地时随增量形态一并补。逆序不报错的现状是
        登记在案的形态，不是漏测（写错的代价为零，因为不可观测）。
        """
        make = dict(EVENT_BATCH)[bid]
        pdef = make()
        report = assert_equivalent(pdef, make_draw_sequence(400),
                                   shape=_default_shape(), tolerance=FLOAT_ORDER)
        assert report.old.changed_beyond_ulp and report.new.changed_beyond_ulp
        assert report.max_prob_diff <= 1e-12, report.max_prob_diff

    @pytest.mark.parametrize('make', [c[1] for c in EVENT_BATCH],
                             ids=[c[0] for c in EVENT_BATCH])
    def test_registered_one_ulp_in_non_conditional_branch(self, make):
        """登记的差异（§六 2026-10-11 同步的「概率分布 1e-12 / 快照位级」两列口径）：
        六个事件驱动型的**非条件分支**存在 1 ULP 位级差。

        来源：条件不成立时新 `RotatingModifier` / `SelectedModifier` / `SoftModifier`
        直接返回恒等，旧类走 `_redistribute_scope()` 重算一遍（`total * ratio` 后再
        `* w / Σw`），浮点往返引入 1 ULP。本用例逐型钉住两件事：① `EXACT` 口径下
        该差异**确实存在**（差异消失即须按 §六 字面口径收严并删本用例）；② 幅值
        停留在 4 ULP 以内（超出即回归，不得当作「已知差异」放行）。
        """
        pdef = make()
        shape = _default_shape()
        strict = compare_runs(pdef, DRAW_SEQUENCE, shape=shape, tolerance=EXACT)
        assert not strict.bit_exact, (
            f'{pdef.name}: 非条件分支的 1 ULP 差已消失，请按 §六 字面口径把本型'
            f'的容差收严为 EXACT，并删除本用例与模块 docstring 的对应行')
        assert strict.prob_mismatches
        bound = _ulp_bound(strict)
        assert 0.0 < strict.max_prob_diff <= bound, (
            f'{pdef.name}: 位级差 {strict.max_prob_diff:.3e} 超出 4 ULP 上界 '
            f'{bound:.3e}（回归而非已知差异）')

        relaxed = compare_runs(pdef, DRAW_SEQUENCE, shape=shape, tolerance=FLOAT_ORDER)
        assert relaxed.max_prob_diff == strict.max_prob_diff
        assert relaxed.is_equivalent(), relaxed.failure_messages()

    def test_issue001_soft_sugar_interval_only(self):
        """ISSUE-001 分支 ③ 的**唯一显形面**：`rotating_soft` **只写 `soft_start` /
        `soft_end`**（`deltas` 与 `soft_deltas` 都缺省）。

        该形态走 `_soft_deltas_of(pdef)` 的分支 ③（先归一为 `soft_interval`，再交
        `_expand_soft_to_deltas`）。若 preset 按 `pdef.btype` 直喂
        `_expand_soft_to_deltas`（后缀型不在该函数的白名单内），展开结果为空元组 →
        `SoftModifier` 的 boost 恒 0 → 软保底静默消失，而**本批次的其余用例
        （写 `deltas` 或写 `soft_increment`）测不出来**。

        判别面两条：① 与旧类逐场一致（旧 `SoftPityMixin._init_soft_pity` 亦先归一
        btype 再展开）；② 新侧该 sugar 配置与「显式写展开结果」的配置**逐抽位级
        相同**，把「展开真的发生」钉在语义上（不靠「分布变了」这类带余量的弱断言）。
        """
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        shape = _default_shape()
        expanded = _expand_soft_to_deltas('soft_interval', 4, 90, None)
        sugar = PityDef(name='b2_rotating_soft_sugar', btype='rotating_soft',
                        scope='ssr', soft_start=4, soft_end=90)
        explicit = PityDef(name='b2_rotating_soft_sugar', btype='rotating_soft',
                           scope='ssr', deltas=expanded, soft_deltas=expanded)

        report = assert_equivalent(sugar, DRAW_SEQUENCE, shape=shape,
                                   tolerance=FLOAT_ORDER)
        assert report.new.probs == run_new(explicit, DRAW_SEQUENCE, shape=shape).probs
        assert report.new.changed_from_base

    def test_issue001_soft_sugar_increment_only(self):
        """ISSUE-001 分支 ②：`rotating_cr_soft` **只写 `soft_increment`**（`deltas` /
        `soft_deltas` / `soft_end` 都缺省）。

        该形态走 `_soft_deltas_of(pdef)` 的分支 ②（先归一为 `soft_additive`，再用
        `soft_end` 缺省 90 展开）。判别面与分支 ③ 用例同形，另含 CR 掷骰的随机数
        消费次数断言（`FLOAT_ORDER` 外唯一在两种口径下都精确的量）。
        """
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        shape = _default_shape()
        expanded = _expand_soft_to_deltas('soft_additive', 4, 90, 6.0)
        cr_kwargs = dict(cr_counter_threshold=3, cr_base_rate=0.018,
                         cr_state_probs=(0.0, 0.4, 0.75, 1.0))
        sugar = PityDef(name='b2_rotating_cr_soft_sugar', btype='rotating_cr_soft',
                        scope='ssr', soft_start=4, soft_increment=6.0, **cr_kwargs)
        explicit = PityDef(name='b2_rotating_cr_soft_sugar', btype='rotating_cr_soft',
                           scope='ssr', deltas=expanded, soft_deltas=expanded,
                           **cr_kwargs)

        report = assert_equivalent(sugar, DRAW_SEQUENCE, shape=shape,
                                   tolerance=FLOAT_ORDER)
        assert report.new.probs == run_new(explicit, DRAW_SEQUENCE, shape=shape).probs
        assert report.new.changed_from_base
        assert report.rng_calls_equal and report.old.rng_calls > 0

    @pytest.mark.parametrize('btype', ('targeted', 'targeted_soft'))
    def test_fate_branch_is_reachable_and_tau_is_consumed(self, btype):
        """`targeted` 族的**命定分支**（`fate_points >= τ`）与 τ 的消费面。

        默认序列（`fate_points_init=0`）下 counter 最多被推到 1，而两侧实现都在
        「命定值 +1」的同一次 `after_draw` 里置 `guaranteed`，故 `fate_points >= 1`
        恒与 `guaranteed` 同时成立，命定分支**永不单独成立**（实测把
        `fate_threshold` 由 2 改成 3 时整批不变红，即 τ 在该形态下没有观测面）。
        可达路径只有 `fate_points_init`：`guaranteed_init=False` + 初值 >= τ 时，
        命定分支在首抽即成立。本用例即钉住该路径与 τ 的消费。

        ① `fate_threshold=1` 时首抽目标组即定轨卡（featured 槽 1.0 / standard 槽 0）；
        ② 同配置把 τ 抬到 2 时首抽恒等，即 `pdef.fate_threshold` 真的进了
           `SelectedModifier` 的 `tau`（preset 写死缺省 1、或漏写 `tau=` 都让 ② 变红）。
        """
        shape = _default_shape()
        maker = counter_fixture if btype == 'targeted' else soft_fixture
        kwargs = dict(name='b2_fate_tau', btype=btype, scope='ssr',
                      fate_points_init=1)
        fired = maker(fate_threshold=1, **kwargs)
        not_yet = maker(fate_threshold=2, **kwargs)

        report = assert_equivalent(fired, DRAW_SEQUENCE, shape=shape,
                                   tolerance=FLOAT_ORDER)
        first = to_slots(report.new.probs[0], shape, space=report.new.space)
        base_slots = to_slots(report.new.base_probabilities, shape,
                              space=report.new.space)
        scope_keys = shape.scope_slots[shape.scope]
        scope_total = sum(base_slots[k] for k in scope_keys)
        selected_slot = shape.card_to_slot[TARGETED_CARD]
        others = [k for k in scope_keys if k != selected_slot]
        assert sum(first[k] for k in others) == 0.0, (
            f'首抽未走命定分支（fate_points_init=1 >= τ=1），scope 其余槽未清零：{first}')
        assert FLOAT_ORDER.holds(first[selected_slot], scope_total), (
            f'定轨槽未拿走 scope 全量：{first[selected_slot]!r} vs {scope_total!r}')

        gated = compare_runs(not_yet, DRAW_SEQUENCE, shape=shape,
                             tolerance=FLOAT_ORDER)
        assert gated.is_equivalent(), gated.failure_messages()
        assert gated.new.probs[0] == gated.new.base_probabilities, (
            'fate_threshold 未被消费：τ=2 时首抽应当恒等（命定值 1 < τ）')
        assert gated.new.probs[0] != first

    def test_f2_registered_no_featured_pool_with_forced_interception(self):
        """§六 F2（2026-10-10 补登记，强制）：无 featured 卡的池 + **必然拦截**时，
        旧 `RotatingCRBehavior._force_featured` 把整个 scope 的概率清零（Σ_scope = 0；
         scope 外槽位不受影响），
        新 `RotatingModifier` 在空目标集上 `return None`（恒等）。两者**不等价**。

        本用例把它**显形**并按缺口登记，**不断言等价**。判为「旧实现的行为本身是
        缺陷」的两条依据：① 旧侧输出 scope 小计为 0 的分布（`_redistribute_scope` 在
        `featured_slots` 为空时既无 A 侧可写、又把 Q 侧整体乘 0），任何配置都不以
        「整池不可出」为目的；② 新侧的恒等是 §六「S8 空目标集断言」的**显式裁定**
        （`A` 为空 → 恒等，不得把空集传给 `transfer_linear`），且与旧实现**非强制
        路径**（`RotatingBehavior.before_draw` 的空集早退）同形，即旧实现两条路径
        自相矛盾、强制路径是离群的那一支。

        **形状可达性**：生产 `compute_scope_mappings` 在「该稀有度无 featured 卡」时
        填 `featured_slots[rarity] = (rarity,)`（非空），故 F2 只能在手工构造的
        `featured_slots={}` 上显形，与 §六 自述的「当前不可达」一致。
        """
        no_featured = make_pool_shape((
            ('s1', 'ssr', False, 0.4),
            ('sr1', 'sr', False, 0.051),
            ('r1', 'r', False, 0.549),
        ))
        shape = dataclasses.replace(no_featured, featured_cards={}, featured_slots={})
        pdef = counter_fixture(name='b2_cr_no_featured', btype='rotating_cr',
                               scope='ssr', cr_counter_threshold=3,
                               cr_base_rate=1.0,
                               cr_state_probs=(0.0, 0.0, 0.0, 1.0))
        old = run_old(pdef, DRAW_SEQUENCE, shape=shape)
        new = run_new(pdef, DRAW_SEQUENCE, shape=shape)
        report = compare_traces(old, new, tolerance=FLOAT_ORDER,
                                snapshot_policy=registered_snapshot_policy(pdef))

        scope_keys = shape.scope_slots[shape.scope]
        base_total = sum(shape.base_probabilities[k] for k in scope_keys)
        assert base_total == 0.4, '本形状的 scope 基础总量变了，下面的对照须重取'
        assert old.changed_from_base, '旧侧若也恒等，本用例就不是在显形差异'
        assert not new.changed_from_base, '新侧的空目标集恒等是 §六 的显式裁定'
        old_totals = [sum(probs[k] for k in scope_keys) for probs in old.probs]
        new_totals = [sum(to_slots(probs, shape, space=new.space)[k] for k in scope_keys)
                      for probs in new.probs]
        assert set(new_totals) == {base_total}, (
            f'新侧出现了既非恒等又非基础总量的取值：{sorted(set(new_totals))}')
        forced = [i for i, t in enumerate(old_totals) if t == 0.0]
        identity = [i for i, t in enumerate(old_totals) if t == base_total]
        assert len(forced) + len(identity) == len(DRAW_SEQUENCE), (
            f'旧侧出现了第三类取值：{sorted(set(old_totals))}')
        assert forced, '旧侧的强制拦截一次都没走到，本用例失去判别力'
        assert identity, (
            '旧侧的非强制路径（guaranteed 命中后的空集早退）应恒等；若它也已清零，'
            '说明旧实现改了行为，本登记须重新核对')

        assert not report.is_equivalent()
        assert {m.key for m in report.prob_mismatches} == set(scope_keys)
        assert report.max_prob_diff == base_total
        assert report.rng_calls_equal, (
            f'拦截掷骰的消费次数在两侧应当一致：'
            f'old={report.old.rng_calls} new={report.new.rng_calls}')


# ══════════════════════════════════════════════════════════════════
# 十二、S5c 三条强制约束专项断言（N1 触发抽数 / M4 did_fire 六类语义 / H4 随机数消费）
# ══════════════════════════════════════════════════════════════════
#
# §七 S5c 的三族断言各自钉住一条**实施约束**（三条都在 §3.1 列为强制）：
#
# - **N1（触发抽数相位）**：计数型 Tracker 在 `Pity.before_draw` 的 `advance` 段先
#   自增、Modifier 再读自增后的值，故 `hard(threshold=90)` 的首次 100% 落在**第 90
#   抽**、软保底的 boost 起始抽数同源（§3.1.1 的 N1 相位表）。把递增挪到
#   `after_draw` 时两者各晚一抽（总次数不变，差的是读相位）。
# - **M4（`did_fire` 六类语义）**：`Pity.did_fire = any(tr.did_reset(...))` 必须与
#   各 Tracker `commit` 的重置分支**严格同条件**（§3.1.1 M4 表六行）。
# - **H4（短路条件下的随机数消费）**：`StreakTracker.prepare` 的六条不消耗路径
#   （`readonly` / `guard_flag` / `state_prob >= 1.0` / `state_prob <= 0` / 空表 /
#   `base_rate == 0`）与旧实现同相位、同次数（§3.1.2 的 CR 随机数消耗协议）。
#
# **M4 为何取两类断言**（S5a 审查结论）：三个 `_soft` 复合类型的 preset 同时含
# 「事件驱动 Tracker（命中才翻转）」与「触发稀有度 counter Tracker（出 scope 即重置）」，
# 而 `did_fire` 取 `any(...)`，故那个 CounterTracker 会在 featured SSR 抽上同样报
# `did_reset`，把同型 FlagTracker 的回归**完全掩盖**。掩盖面**限于该族的三个类型**：
# `rotating` / `rotating_cr` / `rotating_guaranteed_init` 没有 CounterTracker，其
# `did_fire` 只由 FlagTracker 提供，实测会被 S5b 批次抓到（S5c 审查 minor 1 订正：
# 原写「S5b 的十个批次覆盖贡献为零、本节是唯一防线」，与本 commit 自己的实测相反）。
# 本文件对 `did_fire` 的防线是「S5b 批次 + 本节」之和，本节补的是三个 `_soft` 型那一面。
# 两类断言的分工：
# ① 与**状态转移**自洽（flag 翻转 / counter 归零是独立观测面，能抓到
# `FlagTracker.did_reset` 恒 False 一类变异）；② 与**统一语义表**逐抽相等
# （钉住不可由状态转移分辨的那些抽）。只做 ① 会在三个 `_soft` 型上漏掉命中抽，
# 只做 ② 则等于把 `did_reset` 的判据重抄一遍、抓不到「两个方法各写一套」。

#: M4 每个类型的**重置可观测量**表：`btype -> ((键名, 键类别, 初值), ...)`。
#:
#: 只列**参与 `did_fire` 的 Tracker 所写的键**。`StreakTracker.did_reset` 恒 False
#: （§3.1.1：`cr_counter` 的归零是 rotating 族的内部子状态，不构成「本保底回到初始
#: 状态」），故 `rotating_cr` / `rotating_cr_soft` 都不列 `cr_counter`。
#: `rotating` / `targeted` 族的相关键初值均为 False / 0（`guaranteed_init` 与
#: `fate_points_init` 不写时即此值），表内的 `0` 是「旗标未置位」的等价写法。
M4_OBSERVABLES: Dict[str, Tuple[Tuple[str, str, int], ...]] = {
    'hard': (('counter', 'counter', 0),),
    'soft_step': (('counter', 'counter', 0),),
    'rotating': (('guaranteed', 'flag', 0),),
    'rotating_cr': (('guaranteed', 'flag', 0),),
    'targeted': (('fate_points', 'counter', 0),),
    'rotating_soft': (('guaranteed', 'flag', 0), ('counter', 'counter', 0)),
    'rotating_cr_soft': (('guaranteed', 'flag', 0), ('counter', 'counter', 0)),
    'targeted_soft': (('fate_points', 'counter', 0), ('counter', 'counter', 0)),
}


def _pity_scope(pdef: PityDef) -> str:
    """`PityDef.scope` 的归一化取值（缺省回退 `'ssr'`，与 `_norm_scope` 同形）。"""
    return (pdef.scope or 'ssr').lower()


def _key_reset_observation(kind: str, key: str, init: int, pre: dict, post: dict):
    """单个状态键的三值观测：该键所属 Tracker 的 `did_reset` 必然真 / 必然假 / 不可分辨。

    三值而非二值的原因：「状态回到初值」与「重置分支真的跑了」只在部分转移上可分辨。

    - **计数型**（单调 +1 直到重置回初值）：`post != 初值` 蕴含重置未发生（判 False）；
      `post == 初值` 且 `pre != 初值` 蕴含重置发生（判 True）；两侧都在初值则不可分辨
      （整段没动与重置到初值同形）。
    - **标记型**（两支分别写 False / True，初值 False）：`pre is True` 时转移已定
      （`post` 非 True 即 clear 跑过，判 True；`post is True` 即 clear 没跑，判 False）；
      `pre` 非 True 时 `post is True` 说明 set 跑过（判 False），否则不可分辨。
    """
    pre_v, post_v = pre.get(key), post.get(key)
    if kind == 'flag':
        if pre_v is True:
            return post_v is not True
        if post_v is True:
            return False
        return None
    if post_v not in (None, init):
        return False
    if pre_v not in (None, init):
        return True
    return None


def _reset_observations(pdef: PityDef, snaps: Sequence[dict], init_snapshot: dict):
    """逐抽给出「重置分支是否发生」的三值观测（`True` / `False` / `None`）。

    聚合口径与 `Pity.did_fire` 的 `any(...)` 同构：任一键判 True 则整体 True；全部键
    都判 False 才整体 False；含 `None` 且无 True 时整体 `None`。
    """
    name = pdef.name
    out = []
    for index in range(len(snaps)):
        pre_all = snaps[index - 1] if index else init_snapshot
        pre = pre_all.get(name, {})
        post = snaps[index].get(name, {})
        per_key = [_key_reset_observation(kind, key, init, pre, post)
                   for key, kind, init in M4_OBSERVABLES[pdef.btype]]
        if any(x is True for x in per_key):
            out.append(True)
        elif all(x is False for x in per_key):
            out.append(False)
        else:
            out.append(None)
    return out


def _unified_did_fire(pdef: PityDef, step: DrawStep,
                      selected_card: str = TARGETED_CARD) -> bool:
    """§3.1.1 M4 表六行的**统一语义**：本次抽卡是否让本保底回到初始状态。

    逐行转录自该表（不读任何运行时状态，只看本次抽卡的静态事实与配置）：

    - counter 驱动四型：`_should_reset` 按 `reset` 配置（`scope` 出该稀有度 /
      `featured` 仅 featured（**无 scope 门控**，该不对称是既有语义）/ `never` 恒假）；
    - `rotating` / `rotating_cr`：出 scope ∧ is_featured（scope 门控是 2026-09-16 的收严）；
    - `targeted`：出 scope ∧ `reward_id == selected_card`；
    - 三个 `_soft` 复合类型：**出 scope**（ISSUE-102 的放宽，方向与上一行相反）。
    """
    scope = _pity_scope(pdef)
    if pdef.btype in ('hard', 'soft_step', 'soft_interval', 'soft_additive'):
        reset_on = pdef.reset or scope
        if reset_on == 'featured':
            return bool(step.is_featured)
        if reset_on == 'never':
            return False
        return step.rarity == reset_on
    if pdef.btype in ('rotating', 'rotating_cr'):
        return step.rarity == scope and step.is_featured
    if pdef.btype == 'targeted':
        return step.rarity == scope and step.reward_id == selected_card
    return step.rarity == scope


#: M4 批量表（§七 S5c 的「counter 驱动 ×1 + rotating + targeted + 三个 `_soft`
#: 复合类型」六类，另加 `rotating_cr` 一条横向邻接）。逐条取**非默认**形态：
#: `hard` 走小阈值（默认 90 在 28 抽序列内够不着，机制不触发即被非空转闸门拦下），
#: `rotating_cr` 把 `cr_base_rate` 置 0 使掷骰路径不干扰状态观测。
M4_BATCH: Tuple[Tuple[str, Callable[[], PityDef]], ...] = (
    ('hard', lambda: counter_fixture(
        name='m4_hard', btype='hard', scope='ssr', threshold=6, counter_init=0)),
    ('rotating', lambda: counter_fixture(
        name='m4_rotating', btype='rotating', scope='ssr')),
    ('rotating_cr', lambda: counter_fixture(
        name='m4_rotating_cr', btype='rotating_cr', scope='ssr',
        cr_counter_threshold=3, cr_base_rate=0.0,
        cr_state_probs=(0.0, 0.0, 1.0))),
    ('targeted', lambda: counter_fixture(
        name='m4_targeted', btype='targeted', scope='ssr',
        fate_threshold=2, fate_points_init=0)),
    ('rotating_soft', lambda: soft_fixture(
        name='m4_rotating_soft', btype='rotating_soft', scope='ssr')),
    ('rotating_cr_soft', lambda: soft_fixture(
        name='m4_rotating_cr_soft', btype='rotating_cr_soft', scope='ssr',
        cr_counter_threshold=3, cr_base_rate=0.0,
        cr_state_probs=(0.0, 0.0, 1.0))),
    ('targeted_soft', lambda: soft_fixture(
        name='m4_targeted_soft', btype='targeted_soft', scope='ssr',
        fate_threshold=2, fate_points_init=0)),
)


def _family_tolerance(pdef: PityDef) -> Tolerance:
    """按机制族取容差。

    **S8 起两族统一取 `FLOAT_ORDER`（1e-12）**：S8 前 counter 驱动 4 型取 `EXACT`
    （位级一致）的理由是「新侧沿用旧实现的绝对赋值、算式逐字同源」；S8 起新侧改为
    **卡级增量**（`Σδ = 0` 的配平转移），与旧侧槽位级的「除再乘往返」不再逐位同源，
    故按 §六 的 S8 口径取 1e-12（该数值即 S8 与 S5 产物对比所用）。参数保留（族名
    仍决定调用点如何自述理由），但两个分支现同值。
    """
    return FLOAT_ORDER if pdef.btype in _EVENT_DRIVEN_BTYPES else FLOAT_ORDER


def _m4_report(pdef: PityDef, steps: Sequence[DrawStep], shape: PoolShape):
    """跑一次 S5c 的 M4 对拍（复用装置的一步式入口与按类型登记的容差）。"""
    return compare_runs(pdef, steps, shape=shape,
                        tolerance=_family_tolerance(pdef))


def _drive_selected(pdef: PityDef, steps: Sequence[DrawStep], *, shape: PoolShape,
                    selected_card: Optional[str], builder) -> Tuple[List[bool], List[dict]]:
    """S5c 增量门控用例的局部驱动：可指定 `selected_card`。

    装置自带的 `run_trace` 把 `selected_card` 固定为 `TARGETED_CARD`（featured SSR），
    而增量门控要测的正是「命中定轨卡但**出非 scope 稀有度**」，需要 selected 落在
    非 scope 卡上（见 `test_m4_increment_scope_gate_targeted`）。步骤顺序与
    `run_trace` 逐条相同（只省去只读探针，本节不消费该观测面），**两侧都必须先
    `_rebind_state` 再驱动**的纪律同 `run_trace`。
    """
    # 键空间同 `run_trace`：新骨架卡级、旧类槽位级（判据取构造器身份）
    space = 'card' if builder is build_new else 'slot'
    state = _build_pity_state_init([pdef])
    if selected_card is not None:
        state.set(pdef.name, 'selected_card', selected_card)
    layer = builder(pdef, state)
    layer._rebind_state(state)
    did_fire: List[bool] = []
    snaps: List[dict] = []
    for step in steps:
        layer.before_draw(_ctx(shape, state, space=space))
        after_ctx = _ctx(shape, state, step, space=space)
        layer.after_draw(after_ctx)
        did_fire.append(bool(layer.did_fire(after_ctx)))
        snaps.append(state.to_dict()['data'])
    return did_fire, snaps


class TestS5cN1Phase:
    """N1（§3.1.1 计数器相位表）：计数型先自增、Modifier 再读自增后的值。"""

    @staticmethod
    def _full_scope(probs: Dict[str, float], shape: PoolShape, *, space: str) -> bool:
        """该抽是否「scope 概率 100%」（硬保底触发的判别式）。

        判据在**槽位级**表述（`shape.scope_slots` 是槽位名），故先按该侧的键空间投影
        （S8 起新侧是卡级）。
        """
        slots = to_slots(probs, shape, space=space)
        keys = shape.scope_slots[shape.scope]
        others = [k for k in slots if k not in keys]
        return (abs(sum(slots.get(k, 0.0) for k in keys) - 1.0) <= 1e-12
                and all(slots.get(k, 0.0) == 0.0 for k in others))

    def test_n1_hard_first_hundred_percent_at_draw_90(self):
        """`hard(threshold=90)` 的首次 100% 落在**第 90 抽**（下标 89），两侧同答。

        判据分两层，把「相位」而非「总次数」钉住：

        1. **两侧**的 100% 抽次集合都恰为 `[89, 100)`：第 90 抽是首次，此前抽抽不是
           （序列全为 R 抽，出非 scope 不重置计数，故此后抽抽都是）；
        2. 第 90 抽的**抽前** `counter` 为 89，即 Modifier 读到的值是 `pre + 1 = 90`
           （这正是 N1 的读相位：`advance` 在 `before_draw` 的 Modifier 链之前）。

        **本用例哪条断言抓相位**（S5c 审查 minor 2 订正）：是 `firsts` 那条分布列断言。
        实测把递增挪到 `commit` 相位后，new 侧的首次 100% 下标由 89 前移到 90，而
        `pre_counter` 两侧都仍是 89（递增相位不改变「抽后计数 = 已抽次数」这一不变量，
        快照列对相位不敏感）。原 docstring 写「两条同时变红」不成立：下面的
        `pre_counter` 断言另有用处（钉住抽后不变量的初值偏移与 readonly 误推），
        **不构成相位判据**。
        """
        shape = _default_shape()
        pdef = counter_fixture(name='n1_hard90', btype='hard', scope='ssr',
                               threshold=90, counter_init=0)
        steps = tuple(R_DRAW for _ in range(100))
        report = compare_runs(pdef, steps, shape=shape, tolerance=FLOAT_ORDER)
        for side in (report.old, report.new):
            firsts = [i for i, p in enumerate(side.probs)
                      if self._full_scope(p, shape, space=side.space)]
            assert firsts == list(range(89, len(steps))), (
                f'{side.name}: 100% 的抽次集合为 {firsts}，'
                f'期望 {list(range(89, len(steps)))}。'
                f'序列全为 R 抽（出非 scope 不重置计数），故第 90 抽起应当抽抽 100%；'
                f'首个下标落在 90 即计数型 Tracker 的递增相位被挪到了 after_draw')
        # 钉的是**抽后不变量**（第 90 抽抽后计数 == 已抽次数），不是相位（见 docstring）
        pre_counter = report.new.snapshots[88][pdef.name]['counter']
        assert pre_counter == 89, (
            f'第 90 抽抽后 counter 为 {pre_counter}，期望 89'
            f'（不等即初值偏移或只读查询误推进了计数）')
        assert report.is_equivalent(), report.failure_messages()

    @pytest.mark.parametrize('counter_init, expected_index', [(0, 3), (2, 1)])
    def test_n1_soft_boost_start_draw_matches_old(self, counter_init, expected_index):
        """软保底的 boost **起始抽数**与旧实现相同，且随 `counter_init` 整体平移。

        `SOFT_DELTAS = ((3, 0.0), (4, 6.0))` 的累计 boost 在 counter ≥ 4 时为 6 个
        百分点、counter ≤ 3 时恒 0；配合 N1 相位（第 N 抽读到 counter = N）得起始抽数
        为第 4 抽（下标 3）。`counter_init=2` 时同一段表整体前移两抽（下标 1），
        该变体把「起始抽数由 counter 的**读值**决定」与「由抽次序号决定」区分开，
        后者在两种初值下都会答 3。
        """
        shape = _default_shape()
        pdef = counter_fixture(name='n1_soft', btype='soft_step', scope='ssr',
                               deltas=SOFT_DELTAS, counter_init=counter_init)
        report = compare_runs(pdef, DRAW_SEQUENCE, shape=shape,
                              tolerance=FLOAT_ORDER)
        for side in (report.old, report.new):
            changed = [i for i, p in enumerate(side.probs)
                       if p != side.base_probabilities]
            assert changed and changed[0] == expected_index, (
                f'{side.name}: boost 起始下标为 '
                f'{changed[0] if changed else None}，期望 {expected_index}'
                f'（counter_init={counter_init}）')
        assert report.is_equivalent(), report.failure_messages()

    def test_n1_readonly_query_does_not_advance_counter(self):
        """§3.1.1 的 N1 测试断言第三条：`readonly=True` 的查询**不推进计数**。

        判据取「带只读探针与不带探针的两次驱动逐抽全等」（分布列 + 快照列）。
        `CounterTracker.advance` 的 `readonly` 早退若失效，计数会每抽多推一次，
        `hard` 的阈值边界随之整体前移，两列同时不等；这是该早退分支在本文件里的
        显形面（`readonly_mutations` 只能证明「没写状态」，证不了「没推进」）。
        """
        shape = _default_shape()
        pdef = counter_fixture(name='n1_ro', btype='hard', scope='ssr',
                               threshold=6, counter_init=0)
        probe = run_new(pdef, DRAW_SEQUENCE, shape=shape, probe_readonly=True)
        plain = run_new(pdef, DRAW_SEQUENCE, shape=shape, probe_readonly=False)
        assert probe.readonly_mutations == [], (
            f'只读查询改动了状态：{probe.readonly_mutations}')
        assert probe.snapshots == plain.snapshots, (
            '带只读探针的轨迹与不带探针的轨迹在快照列上不同：'
            '`advance` 的 readonly 早退失效（计数被每抽多推一次）')
        assert probe.probs == plain.probs, (
            '带只读探针的轨迹与不带探针的轨迹在分布列上不同：只读查询产生了副作用')



class TestS5cM4DidFire:
    """M4（§3.1.1 M4 表）：`did_fire` 的六类统一语义。

    两类断言分工见本节的模块级说明。逐类一条「语义断言」会被三个 `_soft` 复合类型的
    CounterTracker 掩盖（S5a 审查实测：`FlagTracker.did_reset` 恒返回 False 的变异下
    全文件曾经 14 passed 全绿），故本节按「状态转移自洽 + 统一语义表」两列落。
    """

    @pytest.mark.parametrize('make', [entry[1] for entry in M4_BATCH],
                             ids=[entry[0] for entry in M4_BATCH])
    def test_m4_self_consistency_with_state_reset_transition(self, make):
        """`did_fire` 与**状态转移**自洽：重置分支真的跑过当且仅当 `did_fire` 为真。

        观测面取该族「回到初始状态」的键（`M4_OBSERVABLES`），逐抽判三值：

        - `True`（必然发生重置）：例如 `rotating` 的 `guaranteed` 由 True 转 False
          （`clear` 支跑过）、`hard` 的 `counter` 由非初值回到初值；
        - `False`（必然未发生重置）：例如 `guaranteed` 由 False 转 True（`set` 支跑过）、
          `counter` 未回到初值；
        - `None`（不可分辨）：两侧都在初值，整段没动与重置到初值同形。

        断言只压在 `True` / `False` 两格上（`None` 格交第二条用例的统一语义表覆盖）。
        这是本文件里**唯一**能抓到「`did_reset` 与 `commit` 各写一套判据」的断言：
        三个 `_soft` 型在「出 scope 未命中」当抽会掩盖同型 FlagTracker 的回归，
        而状态转移列不看 `did_fire` 自己、只看状态。
        """
        shape = _default_shape()
        pdef = make()
        report = _m4_report(pdef, DRAW_SEQUENCE, shape)
        assert report.is_equivalent(), report.failure_messages()

        observations = _reset_observations(
            pdef, report.new.snapshots, report.new.init_snapshot)
        reset_draws = [i for i, o in enumerate(observations) if o is True]
        quiet_draws = [i for i, o in enumerate(observations) if o is False]
        assert reset_draws, (
            f'{pdef.name}（{pdef.btype}）：默认序列下观测不到任何一次「重置分支确实跑过」，'
            f'本用例失去判别力，须换 fixture 或换序列')
        assert quiet_draws, (
            f'{pdef.name}（{pdef.btype}）：默认序列下观测不到任何一次「重置分支确实没跑」，'
            f'本用例的否证面是空的')

        for index in reset_draws:
            assert report.new.did_fire[index] is True, (
                f'{pdef.name}（{pdef.btype}）第 {index} 抽：状态转移显示重置分支跑过'
                f'（{M4_OBSERVABLES[pdef.btype]}），而 did_fire 为假。'
                f'`did_reset` 与 `commit` 的重置判据不同源')
        for index in quiet_draws:
            assert report.new.did_fire[index] is False, (
                f'{pdef.name}（{pdef.btype}）第 {index} 抽：状态转移显示重置分支没跑'
                f'（{M4_OBSERVABLES[pdef.btype]}），而 did_fire 为真。'
                f'`did_reset` 比 `commit` 的重置条件更宽')

    @pytest.mark.parametrize('make', [entry[1] for entry in M4_BATCH],
                             ids=[entry[0] for entry in M4_BATCH])
    def test_m4_unified_spec_semantics(self, make):
        """`did_fire` 与 §3.1.1 M4 表的**统一语义**逐抽相等（六类全覆盖）。

        期望值由 `_unified_did_fire()` 从**配置与本次抽卡事实**独立算出，不读
        `did_reset`。三个 `_soft` 复合类型按 ISSUE-102 的放宽取「出 scope」，
        其余四类按表内各自的收严口径；两个方向相反的语义在同一参数化里并列，
        任一侧写反都会变红。

        `did_fire` 的**差异面**同时被钉住：非 `_soft` 型两侧必须与统一语义表全等
        （差异列为空）；`_soft` 型的差异面恰为「出 scope 但未命中」的那些抽。
        """
        shape = _default_shape()
        pdef = make()
        report = _m4_report(pdef, DRAW_SEQUENCE, shape)
        assert report.is_equivalent(), report.failure_messages()

        expected = [_unified_did_fire(pdef, step) for step in DRAW_SEQUENCE]
        assert report.new.did_fire == expected, (
            f'{pdef.name}（{pdef.btype}）的 did_fire 与 §3.1.1 M4 表不符：\n'
            f'  实际 {[int(x) for x in report.new.did_fire]}\n'
            f'  期望 {[int(x) for x in expected]}')

        relaxed = {i for i, step in enumerate(DRAW_SEQUENCE)
                   if step.rarity == shape.scope and not step.is_featured}
        if pdef.btype in _SOFT_SUFFIX_BTYPES:
            assert set(report.did_fire_divergent_draws) == relaxed, (
                f'{pdef.name}: ISSUE-102 的放宽差异面不再等于「出 scope 但未命中」')
        else:
            assert report.old.did_fire == expected, (
                f'{pdef.name}: 本类型的旧类 did_fire 与统一语义表不符'
                f'（该四类的收严已于 2026-09-16 在旧类落地）')
            assert report.did_fire_divergent_draws == [], (
                f'{pdef.name}: 本类型两侧的 did_fire 不应有差异')

    def test_m4_increment_scope_gate_rotating(self):
        """`rotating` 的 scope 门控（M4 表第二行的收严，属增量能力）：

        「出**非 scope 稀有度**的 UP」不得清 `guaranteed`、不得报 `did_fire`。

        构造：池里加一张 featured 的 SR 卡，序列为「无 → 出金未中（置位）→ 出 featured
        SR（**非 scope**）→ 出 scope 的 featured（清位）」。收严前的判据只看
        `is_featured`，第 3 抽会清位并报 `did_fire`；收严后 `guaranteed` 在这一抽
        **必须保持置位**（这是本用例的判别式，`did_fire` 列只是它的伴生观测）。

        该门控已于 2026-09-16 在旧类一并落地，故两侧同答，`compare_runs` 的两列
        可同时断言。
        """
        # `DEFAULT_CARDS` 的 sr 槽只有 `sr1`（0.051）；加一张 featured 的 SR 卡时
        # **必须从同一份质量里拆**（`sr1` 0.001 + `sr_feat` 0.05 = 0.051），否则池的
        # 基础分布 Σ = 1.05：S8 起 `_apply_delta` 对**整份分布**归一化，会把未被任何
        # 算子触碰的卡也整体缩放（实测差 1.9e-2），两侧因此不等价。生产路径不受此
        # 影响：真实 config.toml 的每个池 `Σ p = 1`（已实测）。
        gate_shape = make_pool_shape(
            DEFAULT_CARDS[:-2] + (('sr1', 'sr', False, 0.001),
                                  ('sr_feat', 'sr', True, 0.05),
                                  ('r1', 'r', False, 0.549)))
        featured_sr = DrawStep('sr_feat', 'sr', True)
        steps = (R_DRAW, STANDARD_SSR, featured_sr, FEATURED_SSR)
        assert featured_sr.is_featured and featured_sr.rarity != gate_shape.scope, (
            '本用例的判别力来自「第 3 抽是 featured 且非 scope」，该前提不成立即用例空转')

        pdef = counter_fixture(name='m4_gate_rotating', btype='rotating', scope='ssr')
        report = compare_runs(pdef, steps, shape=gate_shape, tolerance=FLOAT_ORDER)
        assert report.is_equivalent(), report.failure_messages()
        for side in (report.old, report.new):
            assert side.did_fire == [False, False, False, True], (
                f'{side.name}: did_fire 列应为 [F, F, F, T]（出金未中 / 出 featured SR / '
                f'出 scope featured），实际 {side.did_fire}。第 3 抽为真即 scope 门控缺失')
            flags = [snap.get(pdef.name, {}).get('guaranteed')
                     for snap in side.snapshots]
            assert flags == [None, True, True, False], (
                f'{side.name}: guaranteed 列应为 [未写, True, True, False]，实际 {flags}。'
                f'第 3 抽之后不再是 True 即「出非 scope 的 UP」被误当成门控内命中')

    def test_m4_increment_scope_gate_targeted(self):
        """`targeted` 的 scope 门控（M4 表第三行的收严，属增量能力）：

        **命中定轨卡但出非 scope 稀有度**不得清零 `fate_points`、不得报 `did_fire`。

        构造：`selected_card` 取池内一张 SR 卡（`sr1`），序列为「出金未中（fate_points
        1 + guaranteed 置位）→ 出 `sr1`」。`selected_card` 通常由策略层写入 featured
        SSR，装置自带的 `run_trace` 把它写死为 `TARGETED_CARD`，故本用例用局部驱动
        `_drive_selected()` 覆写它。门控缺失时第 2 抽 `reward_id == selected` 成立，
        `fate_points` 归零、`guaranteed` 清位、`did_fire` 为真，三条断言同时变红。
        """
        shape = _default_shape()
        sr_card = 'sr1'
        steps = (STANDARD_SSR, SR_DRAW)
        assert steps[1].reward_id == sr_card and steps[1].rarity != shape.scope, (
            '本用例的判别力来自「命中 selected 且非 scope」，该前提不成立即用例空转')

        pdef = counter_fixture(name='m4_gate_targeted', btype='targeted', scope='ssr',
                               fate_threshold=2, fate_points_init=0)
        for label, builder in (('old', build_old), ('new', build_new)):
            did_fire, snaps = _drive_selected(
                pdef, steps, shape=shape, selected_card=sr_card, builder=builder)
            assert did_fire == [False, False], (
                f'{label}: did_fire 列应为 [F, F]，实际 {did_fire}。'
                f'第 2 抽为真即「命中定轨卡」未受 scope 门控约束')
            fate = [snap[pdef.name].get('fate_points') for snap in snaps]
            assert fate == [1, 1], (
                f'{label}: fate_points 列应为 [1, 1]，实际 {fate}。'
                f'第 2 抽归零即定轨命中把非 scope 抽也算作命中')
            flags = [snap[pdef.name].get('guaranteed') for snap in snaps]
            assert flags == [True, True], (
                f'{label}: guaranteed 列应为 [True, True]，实际 {flags}。'
                f'第 2 抽被清位即门控缺失')


#: CR 族的消费模型批量表：`(id, 配置, 总消费是否应为 0)`。
#: 逐条对应 §3.1.2 协议的一条（或一组）路径：「中间值」与「含 0」两档验掷骰，
#: 「空表」「恒 0 档」与「确定性档」验三条不消耗路径，`base_rate` 两值验 `> 0` 前置。
H4_MODEL_BATCH: Tuple[Tuple[str, Dict[str, Any], bool], ...] = (
    ('base_rate0+mid', dict(cr_counter_threshold=3, cr_base_rate=0.0,
                            cr_state_probs=(0.0, 0.4, 0.75, 1.0)), False),
    ('base_rate0+zeroed', dict(cr_counter_threshold=3, cr_base_rate=0.0,
                               cr_state_probs=(0.0, 0.0, 0.0, 1.0)), True),
    ('base_rate0+empty', dict(cr_counter_threshold=3, cr_base_rate=0.0,
                              cr_state_probs=()), True),
    ('base_rate0+deterministic', dict(cr_counter_threshold=1, cr_base_rate=0.0,
                                      cr_state_probs=(0.0, 1.0)), True),
    ('base_rate0.018+mid', dict(cr_counter_threshold=3, cr_base_rate=0.018,
                                cr_state_probs=(0.0, 0.4, 0.75, 1.0)), False),
    ('base_rate0.018+empty', dict(cr_counter_threshold=3, cr_base_rate=0.018,
                                  cr_state_probs=()), False),
)


@contextmanager
def _scripted_rng(values: Sequence[float]):
    """把模块级 `random.random` 换成**脚本化序列**（H4 负例的确定性掷骰面）。

    与 `_counting_rng` 同法替换模块属性，故新旧两侧消费的是**同一条脚本**（两侧的
    掷骰都走 `random.random` 的属性查找，与 `_counting_rng` 的替换可叠加：
    `run_trace` 内的计数器包住本函数装的脚本函数）。序列耗尽即抛 `AssertionError`，
    比静默回退到真实随机源更能暴露「多消费了一次」。退出时无条件还原。
    """
    pending = list(values)
    consumed: List[float] = []
    original = random.random

    def _scripted() -> float:
        if not pending:
            raise AssertionError(
                '脚本化随机数序列已耗尽：本次运行的消费次数超出用例预期')
        value = pending.pop(0)
        consumed.append(value)
        return value

    random.random = _scripted
    try:
        yield consumed
    finally:
        random.random = original


def _expected_cr_rolls(pdef: PityDef, steps: Sequence[DrawStep],
                       init_snapshot: dict, snaps: Sequence[dict]) -> List[int]:
    """H4 的**独立消费模型**：逐抽期望掷骰枚数（§3.1.2 协议的六条路径逐条写出）。

    只看**配置**与**该侧自己的状态快照**（抽前的 `guaranteed` / `cr_counter`），
    不读 `StreakTracker` 内部的任何东西：

    1. `readonly=True`：本模型只描述主路径（只读路径由
       `test_h4_readonly_query_consumes_no_random` 单独覆盖）；
    2. `guard_flag`（`guaranteed`）已置位：`prepare` 首段早退，**不掷骰**；
    3. `self._cr_base_rate > 0 and random.random() < ...`：`> 0` 是 `and` 的左操作数，
       配 0 时右侧整个不求值。写成 `if random.random() < rate`（省去 `> 0`）会在
       `base_rate == 0` 的每抽多消费一枚，本模型的 `1 if base_rate > 0 else 0` 即该守卫；
    4. 下标裁剪 `idx = min(cr_counter, len(cr_state_probs) - 1)`；
    5. `state_prob >= 1.0`：确定性触发，**不掷骰**；
    6. `state_prob > 0` 才掷骰（`state_prob == 0` 与**空表**（`idx == -1`）都不掷）。
    """
    threshold = (pdef.cr_counter_threshold
                 if pdef.cr_counter_threshold is not None else 3)
    base_rate = pdef.cr_base_rate if pdef.cr_base_rate is not None else 0.0
    state_probs = (list(pdef.cr_state_probs) if pdef.cr_state_probs is not None
                   else [0.0] * threshold + [1.0])

    out: List[int] = []
    for index in range(len(steps)):
        pre_all = snaps[index - 1] if index else init_snapshot
        pre = pre_all.get(pdef.name, {})
        if pre.get('guaranteed') is True:
            out.append(0)
            continue
        rolls = 1 if base_rate > 0 else 0
        idx = min(pre.get('cr_counter') or 0, len(state_probs) - 1)
        if idx >= 0:
            state_prob = state_probs[idx]
            if state_prob >= 1.0:
                pass
            elif state_prob > 0:
                rolls += 1
        out.append(rolls)
    return out


def _drive_cr_per_draw(pdef: PityDef, steps: Sequence[DrawStep], *, shape: PoolShape,
                       builder, seed: int = 20261011,
                       probe_readonly: bool = False) -> Tuple[List[int], List[dict], dict]:
    """H4 的局部驱动：逐抽记录**该抽消耗的随机数枚数**（`run_trace` 只给总数）。

    返回 `(逐抽消费数, 逐抽快照, 初始快照)`。步骤顺序与 `run_trace` 同形
    （`probe_readonly=True` 时在每抽的正式调用前补一次只读查询），rebind 纪律同
    `run_trace`（两侧都必须补一次）。
    """
    # 键空间同 `run_trace`：新骨架卡级、旧类槽位级（判据取构造器身份）
    space = 'card' if builder is build_new else 'slot'
    state = initial_state(pdef)
    layer = builder(pdef, state)
    layer._rebind_state(state)
    init_snapshot = state.to_dict()['data']
    consumed: List[int] = []
    snaps: List[dict] = []
    with _counting_rng(seed) as calls:
        for step in steps:
            if probe_readonly:
                layer.before_draw(_ctx(shape, state, space=space), readonly=True)
            before = calls['n']
            layer.before_draw(_ctx(shape, state, space=space))
            layer.after_draw(_ctx(shape, state, step, space=space))
            consumed.append(calls['n'] - before)
            snaps.append(state.to_dict()['data'])
    return consumed, snaps, init_snapshot


class TestS5cH4RandomConsumption:
    """H4（§3.1.2 的 CR 随机数消耗协议）：短路条件下的消费次数。

    本节把消费从「两侧总数相等」推进到**逐抽、逐侧、对独立模型**三层相等：
    `run_trace` 的 `rng_calls` 只有一个总数，够不着「消费相位错了但总数凑巧相同」
    的形态（例如把 `base_rate == 0` 那次多消费与某次少消费对消）。
    """

    @pytest.mark.parametrize('cfg, expect_zero', [(e[1], e[2]) for e in H4_MODEL_BATCH],
                             ids=[e[0] for e in H4_MODEL_BATCH])
    def test_h4_consumption_matches_short_circuit_model(self, cfg, expect_zero):
        """逐抽消费枚数同时等于：独立模型 / 旧类 / 新骨架。

        模型（`_expected_cr_rolls`）把六条路径逐条写出，只吃配置与各侧自己的状态
        快照；任一条守卫写错都会让某一抽的期望与实际相差一枚：

        - 省去 `base_rate > 0`：`base_rate == 0` 的每抽各多一枚（第 2/3/4 行配置）；
        - 省去 `state_prob > 0`：`state_prob == 0` 的档位每抽各多一枚；
        - 省去 `state_prob >= 1.0` 的确定性早退：确定性档每抽各多一枚；
        - 省去空表早退（`idx == -1`）：空表配置每抽各多一枚；
        - 省去 `guard_flag` 早退：守卫抽各多一枚。

        「逐抽」而非「总数」是关键：总数相等可能由多消费与少消费对消，逐抽列不会。
        `expect_zero` 一条则钉住「三条不消耗路径之和为 0」这一字面主张。
        """
        shape = _default_shape()
        pdef = counter_fixture(name='s5c_h4_model', btype='rotating_cr',
                               scope='ssr', **cfg)
        report = compare_runs(pdef, DRAW_SEQUENCE, shape=shape, tolerance=FLOAT_ORDER)
        assert report.is_equivalent(), report.failure_messages()

        profiles = {}
        for label, builder in (('old', build_old), ('new', build_new)):
            consumed, snaps, init_snapshot = _drive_cr_per_draw(
                pdef, DRAW_SEQUENCE, shape=shape, builder=builder)
            expected = _expected_cr_rolls(
                pdef, DRAW_SEQUENCE, init_snapshot, snaps)
            assert consumed == expected, (
                f'{label} 侧逐抽消费枚数与协议模型不符：\n'
                f'  实际 {consumed}\n  期望 {expected}')
            profiles[label] = consumed
        assert profiles['old'] == profiles['new'], (
            f'两侧逐抽消费枚数不同：\n  old={profiles["old"]}\n  new={profiles["new"]}')

        total = sum(profiles['new'])
        assert (total == 0) is expect_zero, (
            f'本配置的总消费为 {total}，与用例登记的期望'
            f'（{"0" if expect_zero else "> 0"}）不符')
        # 局部驱动与装置的一步式入口同源（同一序列、同一种子、同一 rebind 纪律）
        assert total == report.new.rng_calls, (
            f'局部驱动的消费总数 {total} 与装置记录的 {report.new.rng_calls} 不同，'
            f'说明两者驱动出的不是同一条轨迹')

    def test_h4_short_circuit_paths_consume_no_random(self):
        """三条「不消耗」路径的**正面控制**：同一 fixture 把 `base_rate` 抬到 1.0 后
        每抽恰多消费一枚，证明「0 不消耗」不是模型把消费数算漏了。

        第 1 段的配置（`base_rate == 0` + 空表）总消费恒为 0；第 2 段只改
        `cr_base_rate`（1.0），于是每一张**非守卫抽**都在 `base_rate` 处掷骰一次
        （`random.random() < 1.0` 恒真，仍不触发 state 档），逐抽消费列恰为
        「非守卫抽 1 枚、守卫抽 0 枚」。两段之差即 base_rate 那一处的真实贡献。
        """
        shape = _default_shape()
        quiet = counter_fixture(name='s5c_h4_quiet', btype='rotating_cr', scope='ssr',
                               cr_counter_threshold=3, cr_base_rate=0.0,
                               cr_state_probs=())
        loud = counter_fixture(name='s5c_h4_loud', btype='rotating_cr', scope='ssr',
                              cr_counter_threshold=3, cr_base_rate=1.0,
                              cr_state_probs=())

        quiet_consumed, quiet_snaps, quiet_init = _drive_cr_per_draw(
            quiet, DRAW_SEQUENCE, shape=shape, builder=build_new)
        loud_consumed, loud_snaps, loud_init = _drive_cr_per_draw(
            loud, DRAW_SEQUENCE, shape=shape, builder=build_new)

        assert set(quiet_consumed) == {0}, (
            f'空表 + base_rate=0 时应当一枚都不消费，实际逐抽消费 {quiet_consumed}')
        assert quiet_consumed == _expected_cr_rolls(
            quiet, DRAW_SEQUENCE, quiet_init, quiet_snaps)

        # 守卫抽由状态列给出（`guaranteed` 在抽前为真即 `prepare` 首段早退）
        guarded = [(quiet_snaps[index - 1] if index else quiet_init)
                   .get(quiet.name, {}).get('guaranteed') is True
                   for index in range(len(DRAW_SEQUENCE))]
        assert any(guarded) and not all(guarded), (
            f'本配置下「有守卫抽也有非守卫抽」才使下面的逐抽对照有判别力：{guarded}')
        assert loud_consumed == [0 if g else 1 for g in guarded], (
            f'base_rate=1.0 时每张非守卫抽应在 base_rate 处掷骰恰好一枚'
            f'（守卫抽早退不掷），实际逐抽消费 {loud_consumed}')
        assert loud_consumed == _expected_cr_rolls(
            loud, DRAW_SEQUENCE, loud_init, loud_snaps)

    def test_h4_readonly_query_consumes_no_random(self):
        """H4 负例一（2026-10-10 上调）：**只读查询不消耗随机数**。

        §3.1.2 协议第 3 条：`StreakTracker.prepare` 必须在 `readonly=True` 时早退，
        「漏掉即策略层每次概率查询都掷骰、全局随机流整体错位」。

        **本用例实际生效的判据是快照列（状态副作用）**（S5c 审查 minor 3 订正）：
        `_drive_cr_per_draw` 的消费计数窗口取在只读探针**之后**，故探针自身的消费不在
        窗口内，`probe_consumed == plain_consumed` 是**构造上恒等**的，抓不住「探针掷了
        骰」；真正变红的是 `probe_snaps == plain_snaps`（只读查询产生了状态副作用）。
        窗口如此取是为了让消费列能与 `_expected_cr_rolls` 的非探针模型对齐。若要直接
        钉消费，须把窗口前移到探针之前并同时换掉那个模型的期望值。
        """
        shape = _default_shape()
        pdef = counter_fixture(name='s5c_h4_ro', btype='rotating_cr', scope='ssr',
                               cr_counter_threshold=3, cr_base_rate=0.018,
                               cr_state_probs=(0.0, 0.4, 0.75, 1.0))
        probe_consumed, probe_snaps, probe_init = _drive_cr_per_draw(
            pdef, DRAW_SEQUENCE, shape=shape, builder=build_new, probe_readonly=True)
        plain_consumed, plain_snaps, plain_init = _drive_cr_per_draw(
            pdef, DRAW_SEQUENCE, shape=shape, builder=build_new, probe_readonly=False)

        assert probe_snaps == plain_snaps, (
            '带只读探针的轨迹与不带探针的轨迹在快照列上不同：只读查询产生了副作用')
        assert probe_consumed == plain_consumed, (
            f'只读查询消耗了随机数：\n  带探针 {probe_consumed}\n  不带 {plain_consumed}')
        assert probe_consumed == _expected_cr_rolls(
            pdef, DRAW_SEQUENCE, probe_init, probe_snaps)
        assert sum(plain_consumed) > 0, (
            '本配置一次都没掷骰，本用例失去判别力（改配置使 state 档落在 (0,1) 内）')

    def test_h4_failed_roll_leaves_flag_false(self):
        """H4 负例二（2026-10-10 上调）：**掷骰失败后 `cr_intercepted` 必须为假**。

        §3.1.1 等价性依据第 5 条：旧 `RotatingCRBehavior.before_draw` 只在命中分支
        `return`，照搬会让「上次掷中」的标记残留到下一抽，`RotatingModifier` 因而误
        拦截、拦截率被静默抬高。新实现在掷骰路径上**成功置位、失败清位**。

        构造：`cr_base_rate = 0.5` 配 `cr_state_probs = (0.0,)`（唯一档位概率为 0，
        故只有 `base_rate` 一处掷骰点，每抽恰消费一枚），用**脚本化随机源**把首抽压成
        命中（0.1 < 0.5）、其后全部压成失败（0.9 >= 0.5）。判别面三条：
        ① 逐抽标记列 `[True, False, False, False, False, False]`，即失败抽清位；
        ② 首抽命中把它逼成 featured 全量分布、第二抽失败即回到基础分布（拦截的
           **当抽**效果与标记同源，不留到下一抽）；
        ③ 脚本的消费序列与预期逐项相等（每抽恰一枚，序列耗尽即报错）。
        """
        shape = _default_shape()
        pdef = counter_fixture(name='s5c_h4_flag', btype='rotating_cr', scope='ssr',
                               cr_counter_threshold=3, cr_base_rate=0.5,
                               cr_state_probs=(0.0,))
        steps = tuple(R_DRAW for _ in range(6))
        script = [0.1] + [0.9] * (len(steps) - 1)
        with _scripted_rng(script) as consumed:
            trace = run_new(pdef, steps, shape=shape)

        assert consumed == script, (
            f'脚本化随机源的消费序列与预期不符：{consumed}，期望 {script}'
            f'（每抽恰一枚；多消费一枚即某条守卫缺失）')
        marked = [snap[pdef.name].get('cr_intercepted') for snap in trace.snapshots]
        assert marked == [True] + [False] * (len(steps) - 1), (
            f'掷骰失败后 cr_intercepted 未清位（脏残留）：{marked}')

        # 判据在**槽位级**表述（`shape.scope_slots` 是槽位名），故两侧都先投影
        base = to_slots(trace.base_probabilities, shape, space=trace.space)
        first = to_slots(trace.probs[0], shape, space=trace.space)
        featured_slot = shape.card_to_slot[TARGETED_CARD]
        non_featured = [k for k in shape.scope_slots[shape.scope]
                        if k != featured_slot]
        assert trace.probs[0] != trace.base_probabilities \
            and trace.probs[1] == trace.base_probabilities, (
            '命中抽的分布应当被拦截改写、失败抽应当恒等；'
            f'实际 首抽={trace.probs[0]} 次抽={trace.probs[1]}')
        scope_total = sum(base[k] for k in shape.scope_slots[shape.scope])
        assert FLOAT_ORDER.holds(first[featured_slot], scope_total), (
            f'命中抽未把 scope 全量搬给 featured 槽：'
            f'{first[featured_slot]!r} vs {scope_total!r}'
            f'（容差取 FLOAT_ORDER：S8 起新侧是卡级增量，与旧侧槽位级的'
            f'「除再乘往返」不再逐位同源）')
        assert all(first[k] == 0.0 for k in non_featured), (
            f'命中抽的 scope 非 featured 槽未清零：{first}')


# ══════════════════════════════════════════════════════════════════
# 十四、S8-6 验收块（§七 S8-6 的 ① 至 ⑦ 条 + 承接的 ⑨ 条）
# ══════════════════════════════════════════════════════════════════
#
# 本节的用例名一律含 `s8`（GATE-6 的收集守卫：本文件为 S5a 新建，过滤词零命中时
# pytest 以 exit code 5 结束、会被误读为通过）。逐条对应：
#
# | 计划条 | 用例组 |
# |--------|--------|
# | ① S8 口径（对 S5 产物容差 1e-12） | `TestS8CaliberAgainstS5Products` |
# | ② 单卡定向（双 UP 池定轨） | `TestS8SingleCardTargeting` |
# | ③ (a) 已登记允许差异（`⟨m,p⟩ ≠ 1`） | `TestS8RegisteredDifferenceNonUnitSum` |
# | ③ (g) / ⑦ `priority` 覆盖下 `hard` 的 A 侧形状 | `TestS8RegisteredDifferencePriorityShape` |
# | ④ 遍历点命名空间（ISSUE-505） | `TestS8NamespaceViewDispatch` |
# | ⑤ ISSUE-903 反转的复核 | **不在本节**：判据已随 S8-1/2/3 提前执行，本步只复核 |
# | ⑥ 六场景逐卡对照 | `TestS8SixScenarioCardLevel` |
# | ⑨ 「Σ 偏离 1」形态（S8-5 审查转来） | `TestS8NonUnitSumCoverage` |
#
# **本节的断言对象层级**：① 走既有等价性装置（旧类 vs 新骨架逐场对拍）；② 与 ⑦ 走
# **引擎全管道**（`PityEngine.before_draw`，含排序、Tracker、preset）；⑥ 走**机制级**
# （`HardModifier.compute_delta` + `_apply_delta`，与旧类的单次 `before_draw` 对称）；
# ④ 走**骨架级**（`Pity` + 自定义 Modifier）；③ 走**槽位投影级**（旧类槽位输出 vs
# 新侧投影）。四层各有捕获面，不重复。

#: §3.14.3.1 实测所用的池：**刻意让 featured 组含两张卡**，使「A 组内如何分配」这一
#: 层真正起作用（单卡 A 下 `current` 与 `declared` 同值、分辨不出形状错误）。
S8_SIX_CARDS: Tuple[Tuple[str, str, bool, float], ...] = (
    ('f1', 'ssr', True, 0.004),
    ('f2', 'ssr', True, 0.002),
    ('s1', 'ssr', False, 0.005),
    ('sr1', 'sr', False, 0.05),
    ('r1', 'r', False, 0.939),
)

#: 双 UP 池（§六 的「S8 单卡定向」/ §3.7 的槽位粒度约束）：两张 UP 卡同处一个
#: `ssr_featured` 槽位、一张非 featured 的 SSR 标准卡、一张 scope 外的 SR 卡。
S8_DUAL_UP_CARDS: Tuple[Tuple[str, str, bool, float], ...] = (
    ('up_a', 'ssr', True, 0.25),
    ('up_b', 'ssr', True, 0.25),
    ('std', 'ssr', False, 0.25),
    ('low', 'sr', False, 0.25),
)


def _s8_six_shape() -> PoolShape:
    return make_pool_shape(S8_SIX_CARDS)


def _s8_dual_up_shape() -> PoolShape:
    return make_pool_shape(S8_DUAL_UP_CARDS)


def _s8_lower_cards(scope: str, shape: PoolShape) -> tuple:
    """`rarity_rank` 中 rank 大于 `rank(scope)` 的稀有度下的**全部卡**（§3.1.2 的 Q）。

    本助手是**独立重述**（不复用 `pity_modifier._lower_rarities`）：被测对象的 Q 若
    取错集合（§3.1.5.2.4 的错误 ② 形态），逐卡期望值必须能与它分开。
    """
    rank = shape.rarity_rank.get(scope, 99)
    out: List[str] = []
    for rarity, r in shape.rarity_rank.items():
        if r > rank:
            out.extend(shape.scope_cards.get(rarity, ()))
    return tuple(out)


def _s8_dedup(*groups) -> tuple:
    """保序去重（独立重述 `pity_modifier._cards` 的规范化口径）。"""
    seen: List[str] = []
    for group in groups:
        for c in group:
            if c not in seen:
                seen.append(c)
    return tuple(seen)


def _s8_expected_card_level(scope: str, tf: bool,
                            shape: PoolShape) -> Dict[str, float]:
    """**独立重述** §3.1.2 机制表第 1/2 行的逐卡期望（不调用 `transfer_linear`）。

    A 内每卡 `+ amount * u_A(c)`、Q 内每卡 `- amount * p_c / p(Q)`、其余不写；
    `u_A` 由 A 侧形状定（`current` = `p_c / p(A)`，`declared` = `w_c / w(A)`，
    `w` = 卡级声明权重）。末尾按框架口径归一化（转移族下 `Σδ = 0`，归一化退化为
    恒等，但这里仍写出来，以便「配平被破坏」也能显形）。

    与 `pity_modifier._lower_rarities` / `_cards` 是两份独立实现，故「A 侧形状取错」
    与「Q 取错集合」两类机制错误会被逐卡比出来。
    """
    base = shape.card_probabilities
    scope_cards = tuple(shape.scope_cards.get(scope, ()))
    featured = tuple(shape.featured_cards.get(scope, ()))
    if tf:
        A = _s8_dedup(featured or scope_cards)
        Q = _s8_dedup(_s8_lower_cards(scope, shape),
                      tuple(c for c in scope_cards if c not in set(A)))
    else:
        A = _s8_dedup(scope_cards)
        Q = _s8_lower_cards(scope, shape)
    p_q = sum(base[c] for c in Q)
    if not A or p_q <= 0:
        return dict(base)                       # 恒等（空目标集 / 无货可取）
    if tf:
        w_a = sum(base[c] for c in A)           # `declared`：w 即卡级声明权重
        if w_a <= 0:
            return dict(base)
        u_a = {c: base[c] / w_a for c in A}
    else:
        p_a = sum(base[c] for c in A)
        if p_a <= 0:
            return dict(base)
        u_a = {c: base[c] / p_a for c in A}
    out = dict(base)
    for c in A:
        out[c] += p_q * u_a[c]
    for c in Q:
        out[c] -= base[c]
    total = sum(out.values())
    return {c: v / total for c, v in out.items()}


def _s8_old_hard_slots(scope: str, tf: bool, shape: PoolShape) -> Dict[str, float]:
    """跑一次旧 `HardPityBehavior`（**槽位级**），返回其槽位级输出。

    `threshold=1` 使首次 `before_draw` 即触发（`CounterBasedBehavior.before_draw` 在
    非只读路径先 `incr()`）；`_rebind_state` 是装置纪律（旧类不在构造期绑定 Counter）。
    """
    pdef = counter_fixture(name='s8_old', btype='hard', scope=scope,
                           threshold=1, target_featured=tf)
    state = initial_state(pdef)
    bh = build_old(pdef, state)
    bh._rebind_state(state)
    return bh.before_draw(_ctx(shape, state, space='slot'))


def _s8_old_hard_card_level(scope: str, tf: bool, shape: PoolShape) -> Dict[str, float]:
    """旧实现到**卡级**的还原（`banner.py` 的 `scale_factors` 段口径，§3.14.3.1）。

    `scale = new_slot / old_slot`，每张卡乘其所在槽位的 scale，即「整槽同乘」、
    组内比例不变。**基槽概率为 0 的槽不参与**（scale 无定义），故调用方须先确认
    该池的每个槽基础概率都大于 0（`S8_SIX_CARDS` 满足）。
    """
    slots = _s8_old_hard_slots(scope, tf, shape)
    out: Dict[str, float] = {}
    for card, p in shape.card_probabilities.items():
        slot = shape.card_to_slot[card]
        old_slot = shape.base_probabilities[slot]
        assert old_slot > 0, f'槽 {slot!r} 的基础概率为 0，scale 因子无定义'
        out[card] = p * (slots.get(slot, 0.0) / old_slot)
    return out


def _s8_new_hard_card_level(scope: str, tf: bool, shape: PoolShape) -> Dict[str, float]:
    """S8 卡级管道的**机制级**产物：`HardModifier.compute_delta` + `_apply_delta`。

    与被测生产路径同一组合（`Pity.before_draw` 的内循环就是这两步），但不经 Tracker
    与引擎，以便与旧类的单次 `before_draw` 对称对照。
    """
    mod = HardModifier(scope, threshold=1, target='featured' if tf else 'scope')
    base = dict(shape.card_probabilities)
    ctx = _ctx(shape, PityState(), space='card')
    d = mod.compute_delta({'counter': 1}, dict(base), ctx)
    return _apply_delta(dict(base), d or {})


# ══════════════════════════════════════════════════════════════════
# ① S8 口径：卡级管道产物 vs **S5 产物**（容差 1e-12 + 快照完全一致）
# ══════════════════════════════════════════════════════════════════


class TestS8CaliberAgainstS5Products:
    """§六「S8 口径」：卡级管道产物与 **S5 产物**逐场对比。

    **三条口径的显式登记（S8-6 落盘，待回写计划 §六）**：

    1. **比对口径是「原始值逐元素」，不是「归一化后分布」**。§六 的 (a) 项原文写
       「对比口径为归一化后分布」，而本装置（S5a 交付）实际按原始值逐元素比：两者
       在 `Σ = 1` 的形状上同值，`Σ ≠ 1` 时装置**更严**（归一化会把 Σ 偏离先抹掉）。
       该不一致已由 S8 收口在 (a) 项内登记，本节把它钉在用例上（见
       `test_s8_harness_caliber_is_raw_per_element`）。
    2. **比对面的键空间投影**：旧类是槽位级、新骨架是卡级，故装置把**新侧**按
       `card_to_slot` **求和**投影到槽位级（`_to_slot_space`）。投影是求和而非按
       声明权重展开，它不引入任何假设；代价是组内结构在槽位分辨率下不可见，而
       本装置的两个池形**每槽恰含一张卡**（投影即双射），故该代价为零。组内结构
       （如 S8 的单卡定向）由 `TestS8SingleCardTargeting` 的卡级对比组覆盖。
    3. **「S5 产物」= S5a 装置现跑旧类产出**（ISSUE-502 口径）：旧保底类与
       `_redistribute_scope` 本体均保留至发布前，故本条不需要固化的 golden 快照。
       若将来改为读快照，须同步在 S5a 登记快照文件与重生成命令。

    状态快照一列取**位级一致**（`SnapshotPolicy` 的精确集合白名单，多退少补都报错）。
    """

    def test_s8_harness_caliber_is_raw_per_element(self):
        """口径 1 的**判别性**断言：装置按原始值比对，而非先归一化。

        构造两份「归一化后相同、原始值不同」的分布（`0.5/0.5` 对 `0.4/0.4`）：
        原始口径必须报出 2 处超容差；若谁把装置改成「先归一化再比」，本用例即红。
        后半段是**反证**：手工归一化后两份分布确实相等，故上面的差异只能来自口径。
        """
        a = {'x': 0.5, 'y': 0.5}
        b = {'x': 0.4, 'y': 0.4}
        mismatches, worst, bit = _diff_probs([a], [b], FLOAT_ORDER)
        assert len(mismatches) == 2, (
            f'原始值逐元素口径须报出 2 处差异，实测 {len(mismatches)}')
        assert worst == pytest.approx(0.1), f'最大差应为 0.1，实测 {worst!r}'
        assert bit is False
        norm_a = {k: v / sum(a.values()) for k, v in a.items()}
        norm_b = {k: v / sum(b.values()) for k, v in b.items()}
        assert norm_a == norm_b == {'x': 0.5, 'y': 0.5}, (
            '归一化后两份分布必须相等，否则本用例没有把「口径」与「数值」分开')

    def test_s8_projection_is_bijective_on_the_harness_shape(self):
        """口径 2 的前提守卫：装置池形**每槽恰含一张卡**（投影即双射）。

        该前提一旦被破坏（有人往 `DEFAULT_CARDS` 加第二张同槽卡），投影就会把组内
        结构压掉、「逐元素一致」随之失去意义，故显式钉住。
        """
        shape = _default_shape()
        slots = [shape.card_to_slot[c] for c in shape.card_probabilities]
        assert len(slots) == len(set(slots)), (
            f'装置池形必须每槽恰含一张卡（投影是双射），实测 {shape.card_to_slot}')
        assert len(shape.card_to_slot) == len(shape.card_probabilities)

    def test_s8_card_level_matches_s5_products_within_1e_12(self):
        """① 的主断言：卡级管道与 **S5 产物**（现跑旧类）容差 1e-12 一致、快照位级一致。

        取 `hard(scope='ssr')`（`m = 0`，§六 差异类 (a) 不适用）作代表配置：它是
        两侧**同口径可比**的一档，故本条是「重构未退化」的正面证据。非空转两侧守卫
        一并断言（任一侧恒等时「一致」不构成证据）。
        """
        shape = _default_shape()
        pdef = counter_fixture(name='s8_caliber', btype='hard', scope='ssr',
                               threshold=6)
        report = compare_runs(pdef, DRAW_SEQUENCE, shape=shape,
                              tolerance=FLOAT_ORDER)
        assert report.is_equivalent(), report.failure_messages()
        # 口径 3：对照基准是**现跑旧类**，不是固化快照
        assert report.old.name.startswith('old:'), (
            f'「S5 产物」须为现跑旧类产出（ISSUE-502 口径），实测 {report.old.name!r}')
        # 非空转：两侧都真的改了分布
        assert report.old.changed_beyond_ulp and report.new.changed_beyond_ulp, (
            f'两侧都须真的改动分布（old={report.old.changed_beyond_ulp} '
            f'new={report.new.changed_beyond_ulp}）')
        # 状态快照一列：位级一致（精确集合白名单，无多出、无缺失）
        assert report.snapshot_mismatches == []
        assert report.extra_new_keys == frozenset()
        assert report.missing_new_keys == frozenset()
        assert report.max_prob_diff <= FLOAT_ORDER.atol, (
            f'最大逐元素差 {report.max_prob_diff!r} 超出 §六 的 S8 容差'
            f'{FLOAT_ORDER.atol!r}')


# ══════════════════════════════════════════════════════════════════
# ② 单卡定向（§六「S8 单卡定向」/ §3.7 的槽位粒度约束）
# ══════════════════════════════════════════════════════════════════


class TestS8SingleCardTargeting:
    """双 UP 池定轨：`targeted` 锁定其中一张，必中触发时该卡拿到**整个 scope**。

    **已有用例面的核实（S8-6）**：本条的 Modifier 级面与骨架级面已随 S8-1/2/3 提前
    落地（`tests/core/test_pity_modifier.py::TestSelectedModifier::test_targets_single_card_not_the_whole_featured_group`
    断言 Modifier 输出、`tests/core/test_pity_targeted.py::TestTargetedState::test_guaranteed_targets_selected_card_slot`
    断言骨架输出）。本节补的是**引擎全管道**这一层（含 preset 装配、排序、
    `selected_card` 经 `_build_pity_state_init` 注入），并同时钉住旧类的 50/50 事实
    （§3.7 登记的槽位粒度约束），故与既有两条不同层级、无重复。
    """

    def test_s8_dual_up_targeted_reaches_full_scope_share(self):
        """必中触发时定轨卡收下**整个 scope**，兄弟 UP 卡归零；旧类侧是同槽平摊。

        池形 `S8_DUAL_UP_CARDS` 下 scope 总量 0.75（两张 UP 各 0.25、标准卡 0.25），
        scope 外的 `low`（0.25）不参与（`targeted` 只在 scope 内重分配，新旧两侧
        一致）。旧类的槽位粒度约束（§3.7）使 `ssr_featured` 槽内按基础权重平摊，
        实测 `up_a = up_b = 0.375`（即槽内 50/50）；S8 的卡级管道使 `up_a` 独得
        0.75（槽内 100%）。
        """
        shape = _s8_dual_up_shape()
        pdef = counter_fixture(name='s8_dual_up', btype='targeted', scope='ssr',
                               fate_threshold=1, guaranteed_init=True,
                               selected_card_init='up_a')
        state = _build_pity_state_init([pdef])
        engine = PityEngine({'s8_up_pool': _engine_pool_spec(pdef, shape)}, [pdef],
                            rarity_rank=shape.rarity_rank, state=state)
        probs = engine.before_draw('s8_up_pool', state, dict(shape.card_probabilities))

        scope_total = sum(shape.card_probabilities[c]
                          for c in shape.scope_cards['ssr'])
        assert scope_total == pytest.approx(0.75), '夹具前提：scope 总量 0.75'
        assert probs['up_a'] == pytest.approx(scope_total), (
            f'定轨卡须收下整个 scope（{scope_total}），实测 {probs["up_a"]!r}')
        assert probs['up_b'] == pytest.approx(0.0), (
            f'同 scope 的兄弟 UP 卡须归零，实测 {probs["up_b"]!r}')
        assert probs['std'] == pytest.approx(0.0)
        assert probs['low'] == pytest.approx(0.25), 'scope 外的卡不参与重分配'

        # 旧类的对照：槽位级 + 整槽同乘还原到卡级 → 两张 UP 各得槽内 50%
        old_state = initial_state(pdef)
        old = build_old(pdef, old_state)
        old._rebind_state(old_state)
        old_slots = old.before_draw(_ctx(shape, old_state, space='slot'))
        slot = shape.card_to_slot['up_a']
        assert shape.card_to_slot['up_b'] == slot, '夹具前提：两张 UP 同处一个槽位'
        scale = old_slots[slot] / shape.base_probabilities[slot]
        old_up_a = shape.card_probabilities['up_a'] * scale
        old_up_b = shape.card_probabilities['up_b'] * scale
        assert old_up_a == pytest.approx(old_up_b), (
            f'旧类侧须是槽内平摊（§3.7 的槽位粒度约束），实测 {old_up_a!r} / {old_up_b!r}')
        assert old_up_a == pytest.approx(0.375), (
            f'旧类侧实测值应为 0.375（槽内 50%），实测 {old_up_a!r}')
        assert probs['up_a'] != pytest.approx(old_up_a), (
            '两侧同值说明本用例没有钉住 S8 的语义提升')


# ══════════════════════════════════════════════════════════════════
# ③ (a) 已登记允许差异：`⟨m,p⟩ ≠ 1`（`hard` 的 scope 低于最高稀有度）
# ══════════════════════════════════════════════════════════════════

#: 差异类 (a) 的两个退化形状（`m` = 高于 scope 的稀有度质量 = 0.4）。
#: 前者是「Σ > 1 的归一化」（(a)(i)），后者是「目标组当前无概率」（(a)(ii) 的
#: `p(A) = 0` 支）。两者都刻意取 `m = 0.4`：§六 (a) 的订正段即以该量级给出上界。
S8_NON_UNIT_SUM_CARDS: Tuple[Tuple[str, str, bool, float], ...] = (
    ('f1', 'ssr', True, 0.2),
    ('s1', 'ssr', False, 0.2),
    ('sr1', 'sr', False, 0.1),
    ('r1', 'r', False, 0.5),
)

S8_ZERO_TARGET_CARDS: Tuple[Tuple[str, str, bool, float], ...] = (
    ('f1', 'ssr', True, 0.2),
    ('s1', 'ssr', False, 0.2),
    ('sr1', 'sr', False, 0.0),
    ('r1', 'r', False, 0.6),
)


def _s8_slot_diff(old_slots: Dict[str, float], new_cards: Dict[str, float],
                  shape: PoolShape) -> Tuple[float, Dict[str, float]]:
    """旧槽位级输出（归一化后）与**新侧投影到槽位级**的逐槽差。

    两侧键空间不同（旧槽位 / 新卡级），故新侧按 `card_to_slot` 求和投影；本节的池形
    每槽恰含一张卡，投影是双射。返回 `(最大绝对差, 逐槽差)`。
    """
    total = sum(old_slots.values())
    old_norm = {k: v / total for k, v in old_slots.items()}
    new_slots = _to_slot_space(new_cards, shape.card_to_slot)
    diffs = {k: old_norm.get(k, 0.0) - new_slots.get(k, 0.0)
             for k in set(old_norm) | set(new_slots)}
    return max(abs(v) for v in diffs.values()), diffs


class TestS8RegisteredDifferenceNonUnitSum:
    """§六 差异归因清单 (a)：`hard` 的 scope 低于最高稀有度时的**已登记允许差异**。

    **这不是回归**（S8 收口已登记，量级由该条的订正段给出两条上界）：

    | 子机制 | 形态 | 归一化后逐元素差的上界 |
    |--------|------|----------------------|
    | (i) `Σ > 1` 的归一化 | 旧实现的「目标集绝对赋值 + 更高稀有度豁免」造出 `Σ = 1 + m`，新实现 `Σδ = 0` | `m²/(1+m)`（在目标卡上取到） |
    | (ii) `p(A) = 0`（或 `p(Q) = 0`） | 新实现按 §3.9.5 拒绝转移、旧实现仍绝对赋值**造质量** | `1/(1+m)`（在目标槽上取到） |

    `m` = **高于 scope 的稀有度质量**。本节取 `m = 0.4`（与 (a) 订正段的量级一致）：
    `m²/(1+m) = 0.114286`、`1/(1+m) = 0.714286`。

    **(a)(ii) 的 `p(Q) = 0` 支**不在本节：`hard(scope='r')`（最低稀有度，Q 为空）在
    `TestS8SixScenarioCardLevel` 的 `scope='r'` 两档上以逐卡闭式覆盖（其实测差同样是
    `m²/(1+m)`，`m = 0.061`）。
    """

    def test_s8_registered_difference_a_i_sum_above_one_is_normalized(self):
        """(a)(i)：旧侧 `Σ = 1 + m`、新侧 `Σ = 1`，归一化后最大差恰为 `m²/(1+m)`。"""
        shape = make_pool_shape(S8_NON_UNIT_SUM_CARDS)
        m = 0.4
        old_slots = _s8_old_hard_slots('sr', False, shape)
        new = _s8_new_hard_card_level('sr', False, shape)

        assert sum(old_slots.values()) == pytest.approx(1.0 + m, abs=1e-12), (
            f'旧侧须造出 Σ = 1 + m（这是 (a) 的成因），实测 {sum(old_slots.values())!r}')
        assert sum(new.values()) == pytest.approx(1.0, abs=FLOAT_ORDER.atol)
        assert new['sr1'] == pytest.approx(0.6), (
            f'新侧 A（sr 卡）须收下 p(Q) = 0.5，实测 {new["sr1"]!r}')

        worst, diffs = _s8_slot_diff(old_slots, new, shape)
        bound = m ** 2 / (1 + m)
        assert worst == pytest.approx(bound, rel=1e-9), (
            f'归一化后最大差应为 m²/(1+m) = {bound!r}，实测 {worst!r}（逐槽 {diffs}）')
        assert diffs['sr'] == pytest.approx(bound, rel=1e-9), (
            f'上界须在目标槽上取到，实测 {diffs["sr"]!r}')

    def test_s8_registered_difference_a_ii_zero_target_group_is_refused(self):
        """(a)(ii)：目标组当前无概率时新侧**拒绝转移**（恒等），旧侧仍绝对赋值。

        旧侧在该形状上走 `HardPityBehavior` 的「兜底：均分」分支（目标槽的声明权重
        和为 0），把整个 scope 赋给目标槽；新侧 `transfer_linear` 的 `shape='current'`
        在 `p(A) = 0` 时返回 `None`（§3.9.5 第 1 行的「来源一」处置）。两侧差在目标槽
        上取到 `1/(1+m)`。
        """
        shape = make_pool_shape(S8_ZERO_TARGET_CARDS)
        m = 0.4
        assert shape.card_probabilities['sr1'] == 0.0, '夹具前提：目标组当前无概率'
        old_slots = _s8_old_hard_slots('sr', False, shape)
        new = _s8_new_hard_card_level('sr', False, shape)

        assert new == shape.card_probabilities, (
            f'新侧须恒等（p(A) = 0 → 不转移），实测 {new}')
        worst, diffs = _s8_slot_diff(old_slots, new, shape)
        bound = 1.0 / (1 + m)
        assert worst == pytest.approx(bound, rel=1e-9), (
            f'归一化后最大差应为 1/(1+m) = {bound!r}，实测 {worst!r}（逐槽 {diffs}）')
        assert diffs['sr'] == pytest.approx(bound, rel=1e-9), (
            f'上界须在目标槽上取到，实测 {diffs["sr"]!r}')


# ══════════════════════════════════════════════════════════════════
# ③ (g) / ⑦ `priority` 覆盖下 `hard` 的 A 侧形状
# ══════════════════════════════════════════════════════════════════


def _s8_pool_spec(names, shape: PoolShape) -> PoolPitySpec:
    """多保底池的 `PoolPitySpec`（`_engine_pool_spec` 是单保底版本）。"""
    return PoolPitySpec(
        pity_names=list(names),
        featured_ids=set(shape.featured_ids()),
        ssr_ids=set(shape.scope_cards.get(shape.scope, ())),
        scope_cards=shape.scope_cards,
        featured_cards=shape.featured_cards,
        scope_slots=shape.scope_slots,
        featured_slots=shape.featured_slots,
        card_to_slot=shape.card_to_slot,
    )


class TestS8RegisteredDifferencePriorityShape:
    """§六 差异归因清单 (g) / S8-6 第 ⑦ 条验收面：`hard` 的 A 侧形状语义取向。

    **形态**：形状改变型算子（`rotating` / `targeted`）经 `priority` 排在 `hard`
    **之前**、且同 scope 时，`hard` 的 A 侧取 `current`（§3.1.2 机制表的「A 侧形状」
    列）即**保留前序算子已造成的形状**；旧实现在槽级按 `w_s / Σw`（声明权重）赋值，
    故会把前序形状**重置**为声明比例。两侧实测差 **0.5**（S8 收口登记）。

    **性质**：实现忠于 §3.1.2 的机制表，是**机制表与旧实现分岔**，故不改实现、只登记。
    **可达性**：真实 `config.toml` 无 `hard`，且 `_BTYPE_ORDER` 下 `hard` 默认排在
    `rotating` / `targeted` 之前，故须**显式写 `priority`** 才可达；本用例同时断言
    排序结果（缺该守卫时「`priority` 未生效」会让本用例**假绿**：两种顺序的终态
    恰好相同，见下）。
    """

    def test_s8_priority_ordered_rotating_then_hard_keeps_current_shape(self):
        """`rotating`（`priority=1`）先跑出 featured 独占，`hard` 保留该形状。

        终态与「`hard` 先跑」恰好相同（两种顺序都得到 `{f1: 1.0}`），故**排序断言是
        本用例的牙齿所在**：少了它，`priority` 失效也照样通过。而 A 侧形状的判别力
        在 `current` 与 `declared` 之间：若 `hard` 取 `declared`（旧口径），终态会是
        `{f1: 0.7, s1: 0.3}`。
        """
        shape = _default_shape()
        rot = counter_fixture(name='s8_g_rot', btype='rotating', scope='ssr',
                              guaranteed_init=True, priority=1)
        hard = counter_fixture(name='s8_g_hard', btype='hard', scope='ssr',
                               threshold=1, priority=0)
        state = _build_pity_state_init([rot, hard])
        engine = PityEngine({'s8_g_pool': _s8_pool_spec((rot.name, hard.name), shape)},
                            [rot, hard], rarity_rank=shape.rarity_rank, state=state)

        order = [pname for pname, _bh in engine.get_behaviors_for_pool('s8_g_pool')]
        assert order == [rot.name, hard.name], (
            f'本用例的前提是「rotating 经 priority 排在 hard 之前」，实测顺序 {order}')

        probs = engine.before_draw('s8_g_pool', state, dict(shape.card_probabilities))
        assert probs['f1'] == pytest.approx(1.0), (
            f'hard 的 A 侧须取当前形状（保留 rotating 造成的 f1 独占），实测 {probs}')
        assert probs['s1'] == pytest.approx(0.0), (
            f'取 declared 会把 A 侧重置为声明比例（f1 = 0.7 / s1 = 0.3），实测 {probs}')
        assert probs['sr1'] == pytest.approx(0.0)
        assert probs['r1'] == pytest.approx(0.0)

        # 旧类侧：同样的顺序（槽位级），整槽同乘还原到卡级 → A 侧被重置为声明比例
        old_state = PityState()
        rot_old = RotatingBehavior('s8_g_rot', old_state, scope='ssr',
                                   guaranteed_init=True)
        rot_old._rebind_state(old_state)
        hard_old = HardPityBehavior('s8_g_hard', old_state, scope='ssr',
                                    btype='hard', threshold=1)
        hard_old._rebind_state(old_state)
        ctx = _ctx(shape, old_state, space='slot')
        after_rot = rot_old.before_draw(ctx)
        ctx2 = PityContext(draw=ctx.draw, current=after_rot, state=old_state)
        old_slots = hard_old.before_draw(ctx2)
        assert old_slots['ssr_featured'] == pytest.approx(0.5), (
            f'旧类侧须把 A 侧重置为声明比例（0.5 / 0.5），实测 {old_slots}')

        old_cards = {c: shape.card_probabilities[c]
                     * (old_slots.get(shape.card_to_slot[c], 0.0)
                        / shape.base_probabilities[shape.card_to_slot[c]])
                     for c in shape.card_probabilities}
        old_norm = {c: v / sum(old_cards.values()) for c, v in old_cards.items()}
        assert old_norm['f1'] == pytest.approx(0.5) and old_norm['s1'] == pytest.approx(0.5)
        worst = max(abs(old_norm[c] - probs[c]) for c in probs)
        assert worst == pytest.approx(0.5, rel=1e-9), (
            f'(g) 项登记的实测差为 0.5，实测 {worst!r}（旧 {old_norm} 新 {probs}）')


# ══════════════════════════════════════════════════════════════════
# ④ 遍历点命名空间（ISSUE-505）
# ══════════════════════════════════════════════════════════════════


class TestS8NamespaceViewDispatch:
    """S8 骨架的 Modifier 遍历点一律经 `self._view_for(mod)` 取 view（ISSUE-505）。

    **已有用例面的核实（S8-6）**：`tests/core/test_pity_modifier.py::TestNamespaceViewDispatch`
    的两条已随 S8-1 提前落地（单零件行为面 + `before_draw` 源码的 AST 面）。本节补两
    处不同面：① **链中位置**（namespaced 零件排在**第二个**、前面还有一个默认命名空间
    的零件，断言两者各自读对）；② **AST 判据的扫描面从 `before_draw` 扩大到整个 `Pity`
    类**（将来在别处新增调用点时也拦得住）。
    """

    def test_s8_namespaced_modifier_in_a_chain_reads_its_own_namespace(self):
        """链中第二个零件（声明了命名空间）读自己的命名空间，第一个读默认命名空间。

        两个零件的 `compute_delta` 都记录收到的 view 名与探针键值。判别力三条：
        ① 两个 view 名分别为 `'p'` 与 `'s8_ns'`（写死 `self._view` 时第二条即红）；
        ② 探针值各自来自对应命名空间（同名键在两处放不同值）；
        ③ 命名空间零件的增量**真的作用到了输出**（不是被静默跳过的空操作）。
        """
        seen: Dict[str, Any] = {}

        class _DefaultNsProbe(Modifier):
            def compute_delta(self, view, dist, ctx):
                seen['default'] = (view._name, view.get('probe'))
                return None

        class _NamespacedProbe(Modifier):
            namespace = 's8_ns'

            def compute_delta(self, view, dist, ctx):
                seen['ns'] = (view._name, view.get('probe'))
                if view.get('probe') != 'part-ns':
                    return None
                return {'f1': 0.1}

        state = PityState()
        state.set('p', 'probe', 'default-ns')
        state.set('s8_ns', 'probe', 'part-ns')
        pity = Pity(name='p', state=state, scope='ssr', btype='hard',
                    trackers=[], modifiers=[_DefaultNsProbe(), _NamespacedProbe()],
                    lifecycle=AlwaysActive())
        shape = _default_shape()
        base = dict(shape.card_probabilities)
        out = pity.before_draw(_ctx(shape, state, space='card'))

        assert seen['default'] == ('p', 'default-ns'), (
            f'默认命名空间的零件须拿到 `Pity` 的 view，实测 {seen.get("default")}')
        assert seen['ns'] == ('s8_ns', 'part-ns'), (
            f'声明了命名空间的零件须拿到自己的 view，实测 {seen.get("ns")}')
        assert out != base, (
            '命名空间零件的增量须真的作用到输出（否则本用例只证明「没崩」）')
        assert out['f1'] == pytest.approx((base['f1'] + 0.1) / 1.1), (
            f'不配平增量经 `_apply_delta` 归一化，实测 {out["f1"]!r}')

    def test_s8_skeleton_has_no_direct_self_view_compute_delta_call(self):
        """AST 判据：整个 `Pity` 类内**无** `mod.compute_delta(ctx, self._view, ...)` 直写形态。

        扫描面取**整个类**（不是只 `before_draw`）：`compute_delta` 的调用点若将来
        挪到别的方法里，写死默认 view 同样让声明命名空间的零件静默失效。
        """
        src = textwrap.dedent(inspect.getsource(Pity))
        tree = ast.parse(src)
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and node.func.attr == 'compute_delta']
        assert calls, '骨架内须有 compute_delta 调用点（否则本判据无对象）'
        for node in calls:
            assert len(node.args) == 3, (
                f'`compute_delta` 是**三参**（`view, dist, ctx`，2026-10-08 裁决），'
                f'实测 {ast.dump(node)}')
            first = ast.dump(node.args[0])
            assert 'self' in first and '_view_for' in first, (
                f'首个实参须为 `self._view_for(mod)`，实测 {first}')
            for arg in node.args:
                dumped = ast.dump(arg)
                assert '_view' not in dumped.replace('_view_for', ''), (
                    f'不得写死 `self._view`：{dumped}')


# ══════════════════════════════════════════════════════════════════
# ⑥ `transfer_linear` 六场景逐卡对照（§3.14.3.1 的 `scope` × `tf` 全组合）
# ══════════════════════════════════════════════════════════════════

#: 「浮点噪声」判据（4 ULP），与 `SideTrace.changed_beyond_ulp` 同源。
S8_FLOAT_NOISE = 4 * math.ulp(1.0)


def _s8_scenarios() -> Tuple[Tuple[str, bool], ...]:
    return tuple((scope, tf)
                 for scope in ('ssr', 'sr', 'r') for tf in (False, True))


def _s8_scenario_id(scenario) -> str:
    scope, tf = scenario
    return f'{scope}-tf{int(tf)}'


def _s8_higher_mass(scope: str, shape: PoolShape) -> float:
    """`m` = **高于 scope 的稀有度**的全部卡的概率和（§六 (a) 的 `m`）。"""
    rank = shape.rarity_rank[scope]
    return sum(shape.card_probabilities[c]
               for rarity, r in shape.rarity_rank.items() if r < rank
               for c in shape.scope_cards.get(rarity, ()))


def _s8_a_cards(scope: str, tf: bool, shape: PoolShape) -> tuple:
    scope_cards = tuple(shape.scope_cards.get(scope, ()))
    featured = tuple(shape.featured_cards.get(scope, ()))
    return _s8_dedup(featured or scope_cards) if tf else _s8_dedup(scope_cards)


def _s8_card_rank(card: str, shape: PoolShape) -> int:
    """卡所属稀有度的 rank（由 `scope_cards` 反查，`scope_cards` 是卡集合的真相源）。"""
    for rarity, cards in shape.scope_cards.items():
        if card in cards:
            return shape.rarity_rank[rarity]
    raise KeyError(f'卡 {card!r} 不在任何稀有度的 scope_cards 内')


class TestS8SixScenarioCardLevel:
    """§六「S8 口径 3 的回归断言」/ S8-6 第 ⑥ 条：六场景**逐卡**对照（强制）。

    **两条断言，牙齿各在不同方向**：

    1. `test_s8_six_scenarios_match_mechanism_table_per_card`：新侧逐卡 == **独立重述**
       的机制表期望（不调用 `transfer_linear`）。这是对「A 侧形状取错」（§3.1.5.2.4
       的错误 ① 形态）与「Q 取错集合」（错误 ② 形态）的捕获面：**只断言目标组总量
       = 1.0 对两者恒通过**，故本节一律逐卡。
    2. `test_s8_six_scenarios_against_old_hard_per_card`：与旧 `HardPityBehavior`
       **逐卡**对照。

    **与计划原文的一处不符（S8-6 实测登记，已回写报告）**：计划第 ⑥ 条要求「断言
    **逐卡**结果与旧 `HardPityBehavior` 一致」，而该一致性**只对 `m = 0` 的两档成立**
    （`scope = 'ssr'`）。`m > 0` 的四档（`scope` 为 `sr` / `r`）正是 §六 差异类 (a)
    登记的配置（旧实现「绝对赋值 + 更高稀有度豁免」造出 `Σ = 1 + m`，新实现配平转移
    得 `Σ = 1`），**两侧本就不等价**，其逐卡差有闭式：目标卡 `+m²/(1+m)`、更高稀有度
    的卡 `-p_c·m/(1+m)`、Q 内的卡 `0`。故本组对 `m > 0` 的四档断言的是**该闭式**
    （即差异类 (a) 的已知差异断言），不是「一致」。原句写在 2026-10-09，早于 S8 的
    增量实现落地（当时两侧都是「绝对赋值 + 豁免」的 M1 形态，故 6/6 逐位一致）。
    """

    @pytest.mark.parametrize('scope,tf', _s8_scenarios(),
                             ids=[_s8_scenario_id(s) for s in _s8_scenarios()])
    def test_s8_six_scenarios_match_mechanism_table_per_card(self, scope, tf):
        """逐卡 == 独立重述的机制表期望；并断言「真的改了分布」或「该档本就恒等」。"""
        shape = _s8_six_shape()
        new = _s8_new_hard_card_level(scope, tf, shape)
        expected = _s8_expected_card_level(scope, tf, shape)
        for card in shape.card_probabilities:
            assert new[card] == pytest.approx(expected[card], rel=1e-12, abs=1e-15), (
                f'{scope}/tf={tf} 的卡 {card!r}：实测 {new[card]!r}，'
                f'机制表期望 {expected[card]!r}（全量 新 {new} / 期望 {expected}）')
        assert sum(new.values()) == pytest.approx(1.0, abs=FLOAT_ORDER.atol)
        if scope == 'r':
            assert new == shape.card_probabilities, (
                '最低稀有度 scope 的 Q 为空 → S8 恒等（§3.9.5 的 p(Q) = 0 行）：'
                f'实测 {new}')
        else:
            assert new != shape.card_probabilities, (
                f'{scope}/tf={tf} 的机制须真的触发，否则本参数无判别力')

    @pytest.mark.parametrize('scope,tf', _s8_scenarios(),
                             ids=[_s8_scenario_id(s) for s in _s8_scenarios()])
    def test_s8_six_scenarios_against_old_hard_per_card(self, scope, tf):
        """逐卡与旧 `HardPityBehavior` 对照（`m = 0` 一致、`m > 0` 按 (a) 的闭式分岔）。"""
        shape = _s8_six_shape()
        new = _s8_new_hard_card_level(scope, tf, shape)
        old_cards = _s8_old_hard_card_level(scope, tf, shape)
        total = sum(old_cards.values())
        old_norm = {c: v / total for c, v in old_cards.items()}
        m = _s8_higher_mass(scope, shape)

        assert total == pytest.approx(1.0 + m, abs=1e-12), (
            f'旧侧原始总量须为 1 + m（m = {m}），实测 {total!r}')
        assert sum(new.values()) == pytest.approx(1.0, abs=FLOAT_ORDER.atol)

        rank = shape.rarity_rank[scope]
        a_cards = _s8_a_cards(scope, tf, shape)
        for card in shape.card_probabilities:
            diff = old_norm[card] - new[card]
            if m == 0.0:
                assert abs(diff) <= S8_FLOAT_NOISE, (
                    f'{scope}/tf={tf}（m = 0）的卡 {card!r} 须在浮点噪声内一致，'
                    f'实测差 {diff!r}（旧 {old_norm[card]!r} / 新 {new[card]!r}）')
                continue
            if card in a_cards:
                # 目标卡：旧侧绝对赋值 1.0（归一化后 1/(1+m)）对新侧 1 - m
                want = m ** 2 / (1 + m)
            elif _s8_card_rank(card, shape) < rank:
                # 更高稀有度：旧侧被归一化缩放，新侧不写增量即保留
                want = -shape.card_probabilities[card] * m / (1 + m)
            else:
                want = 0.0
            assert diff == pytest.approx(want, rel=1e-9, abs=1e-15), (
                f'{scope}/tf={tf} 的卡 {card!r}：与旧侧的差应为 {want!r}（差异类 (a) 的'
                f'闭式），实测 {diff!r}')
        worst = max(abs(old_norm[c] - new[c]) for c in new)
        assert worst == pytest.approx(m ** 2 / (1 + m), rel=1e-9), (
            f'最大差应为 m²/(1+m)（(a)(i) 的上界，在目标卡上取到），实测 {worst!r}')


# ══════════════════════════════════════════════════════════════════
# ⑨ 「Σ 偏离 1」形态的覆盖（S8-5 审查转来的责任）
# ══════════════════════════════════════════════════════════════════


class TestS8NonUnitSumCoverage:
    """「输入分布 `Σ ≠ 1`」这一形态的**判别性**覆盖（S8-5 审查转来）。

    **背景（S8-5 审查的实测结论）**：S8-5 的 6 条 `abs(Σout - 1) < 1e-12` 断言
    **零判别力**（`_apply_delta` 的无条件归一化使其成为**结构保证**），且该形态
    **由输入产生**（如池内重复 id，实测 `Σ = 0.8`）而非由算子产生（转移族恒有
    `Σδ = 0`）。故「Σ 偏离」不可能由任何转移族算子造出，本节给出它**唯一可能**的
    三条观测面与各自的口径：

    | 面 | 口径 | 用例 |
    |----|------|------|
    | 有增量作用时 | 输入偏离被归一化**吸收**（`Σout = 1`） | `test_s8_apply_delta_absorbs_non_unit_input` |
    | 无增量作用时 | 输入偏离**原样穿过**（`Σout = Σin`），即 `Σ = 1` 的保证是**有条件的** | `test_s8_pipeline_passes_non_unit_input_through` |
    | 由谁保证 | 分布层判据 `Σp = 1`（`InvariantChecker`），在无增量的那一格上抛 `InvariantError` | `test_s8_non_unit_input_is_caught_by_the_invariant_layer` |

    **如实自报的强度上限**：「增量作用后 `Σ == 1`」一条**只是结构保证**（无条件归一
    化），单看它没有判别力；本节的第一条用例之所以有牙齿，是因为它同时断言**吸收后
    的具体取值**（`0.5/0.8` 与 `0.3/0.8`），故「删掉归一化」（S8-4 变异 8 未被杀死的
    形态）会红。
    """

    def test_s8_apply_delta_absorbs_non_unit_input(self):
        """有增量作用时：`Σ = 0.8` 的输入被归一化吸收为 `Σ = 1`，且取值按总和对齐。

        判别性：不做归一化时 `Σout = 0.8`（**这正是 S8-4 变异 8「去掉归一化」未被
        杀死的形态**），故本条同时断言吸收后的逐卡取值而非只断言 `Σ == 1`。
        """
        dist = {'a': 0.4, 'b': 0.4}
        delta = {'a': 0.1, 'b': -0.1}
        assert sum(dist.values()) == pytest.approx(0.8)
        naive = {c: dist[c] + delta.get(c, 0.0) for c in dist}
        assert sum(naive.values()) == pytest.approx(0.8), (
            '夹具前提：未归一化的裸相加仍偏离 1（否则本用例无判别力）')

        out = _apply_delta(dist, delta)
        assert sum(out.values()) == pytest.approx(1.0, abs=FLOAT_ORDER.atol)
        assert out['a'] == pytest.approx(0.5 / 0.8) and out['b'] == pytest.approx(0.3 / 0.8), (
            f'吸收后的逐卡取值须按输入总和对齐，实测 {out}')

    def test_s8_pipeline_passes_non_unit_input_through(self):
        """无增量作用时：骨架把输入分布**原样返回**（`Σ = 1` 不是无条件保证）。

        这一格是「Σ 偏离」唯一能活着走出管道的形态，也是分布层判据的捕获对象。
        判别性：若谁在骨架出口补一次无条件归一化（把「兜底」变成「恒等化」），本
        用例即红。
        """
        shape = _default_shape()
        base = dict(shape.card_probabilities)
        scaled = {c: 0.8 * v for c, v in base.items()}

        class _Noop(Modifier):
            def compute_delta(self, view, dist, ctx):
                return None

        state = PityState()
        pity = Pity(name='s8_sigma_noop', state=state, scope='ssr', btype='hard',
                    trackers=[], modifiers=[_Noop()], lifecycle=AlwaysActive())
        ctx = dataclasses.replace(_ctx(shape, state, space='card'), current=dict(scaled))
        out = pity.before_draw(ctx)
        assert out == scaled, (
            f'无增量作用时骨架须原样返回输入（含 Σ 偏离），实测 {out}')
        assert sum(out.values()) == pytest.approx(0.8), (
            '输出总量须与输入同（0.8），即 Σ = 1 的保证是有条件的')

    def test_s8_non_unit_input_passes_the_engine_silently_when_checker_off(self):
        """生产默认（`invariants=None`）下：偏离**不报错、原样到达下游**。

        与上一条互为反面，合起来才是完整口径：`Σ = 1` 在「无增量」那一格上**没有
        无条件兜底**，唯一的守卫是可选的不变式校验器（生产默认关闭）。这不是缺陷，
        而是 §六 (a) 登记的「Σ 偏离由输入产生」这一前提：`pool.draw` 的
        `_adjusted_total_weight` 隐含归一化，故偏离只影响绝对量、不影响抽样比。
        **判别性**：若谁在骨架出口补一次无条件归一化，本用例即红。
        """
        shape = _default_shape()
        pdef = counter_fixture(name='s8_sigma_off', btype='hard', scope='sr',
                               threshold=99)
        state = initial_state(pdef)
        engine = PityEngine({'s8_sigma_off_pool': _engine_pool_spec(pdef, shape)},
                            [pdef], rarity_rank=shape.rarity_rank, state=state,
                            invariants=None)
        scaled = {c: 0.8 * v for c, v in shape.card_probabilities.items()}
        out = engine.before_draw('s8_sigma_off_pool', state, dict(scaled))
        assert out == scaled, (
            f'校验器关闭时偏离须原样穿过（不报错、不归一化），实测 {out}')

    def test_s8_non_unit_input_is_caught_by_the_invariant_layer(self):
        """由谁保证：分布层判据 `Σp = 1` 在「无增量」的那一格上抛 `InvariantError`。

        构造：`hard(scope='sr', threshold=99)` 全程不触发（故无增量作用、输入偏离
        原样穿过），输入分布取 `0.8 × 基础`（S8-5 实测的「池内重复 id」形态）。
        判别性：把分布层判据退回 M1 的取值集形态（或删掉该判据）时本用例即红。
        """
        shape = _default_shape()
        pdef = counter_fixture(name='s8_sigma', btype='hard', scope='sr', threshold=99)
        state = initial_state(pdef)
        checker = InvariantChecker(enabled=True)
        engine = PityEngine({'s8_sigma_pool': _engine_pool_spec(pdef, shape)}, [pdef],
                            rarity_rank=shape.rarity_rank, state=state,
                            invariants=checker)
        scaled = {c: 0.8 * v for c, v in shape.card_probabilities.items()}
        with pytest.raises(InvariantError) as excinfo:
            engine.before_draw('s8_sigma_pool', state, dict(scaled))
        message = str(excinfo.value)
        assert "'Σp'" in message and '期望 1.0' in message, (
            f'须由分布层的归一性判据拦下，实测 {message}')


# ══════════════════════════════════════════════════════════════════
# ⑥（续）空目标集 / `declared` 形状的「来源一 / 来源二」/ scope 白名单
# ══════════════════════════════════════════════════════════════════
#
# S8-6 第 ⑥ 条的「另两条」与「`declared` 分支须至少一条正例与一条负例」在本节。
# **层级选择**：逐机制的空目标集断言与 Modifier 级的 `declared` 正负例已随
# S8-1/2/3 提前落地（`tests/core/test_pity_modifier.py::test_empty_target_set_returns_none`
# 的 7 条参数化、`test_declared_shape_transfers_when_pA_is_zero` /
# `test_declared_shape_returns_none_when_wA_is_zero`），故本节改在**组合面**与
# **助手面**覆盖，与既有两条不同层级、无重复。

#: scope 白名单用例的 TOML（`[rarities].ranks` 只有 SSR / SR / R）。
_S8_SCOPE_TOML = """[meta]
version = "2.3.0"

[rarities]
ranks = [
    ["SSR"],
    ["SR"],
    ["R"],
]

[[banner]]
id = "test_pool"
name = "测试池"
start_day = 0
end_day = 21

[[banner.pool]]
id = "main"
cost = "draw_resource:160"

[[banner.pool.reward]]
card_id = "c1"
probability = 1.0
rarity = "SSR"
featured = true

[[pity]]
name = "p_scope"
type = "hard"
scope = "{scope}"
threshold = 90
"""


def _s8_load_toml(toml_str):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False,
                                     encoding='utf-8') as f:
        f.write(toml_str)
        path = f.name
    try:
        return load_toml(path)
    finally:
        os.unlink(path)


class TestS8EmptyTargetSetAndDeclaredShape:
    """空目标集（恒等）与 `declared` 形状的两个来源（§3.9.5 / §3.1.5.6.1）。"""

    def test_s8_empty_target_set_yields_identity_pipeline_output(self):
        """空目标集 → `compute_delta` 返 `None` → **管道输出 = 输入**（恒等）。

        `assert mod.compute_delta(...) is None` 那一面的逐机制覆盖已随 S8-1/2/3 落地
        （`test_empty_target_set_returns_none` 的 7 条参数化）；本节补**组合面**：
        `None` 经 `Pity.before_draw` 的内循环确实不写分布（`if d is not None` 守卫），
        故「机制触发但目标集为空」与「机制未触发」在输出上同值。判别力：把该守卫
        写成无条件 `_apply_delta(out, d or {})` 时，`d = None` 会被当成空增量并**归一化**
        输入分布，本用例即红。
        """
        shape = make_pool_shape((('sr1', 'sr', False, 0.5), ('r1', 'r', False, 0.5)))
        base_dist = dict(shape.card_probabilities)
        for tf in (False, True):
            state = PityState()
            mod = HardModifier('ssr', threshold=1,
                               target='featured' if tf else 'scope')
            pity = Pity(name=f's8_empty_{tf}', state=state, scope='ssr', btype='hard',
                        trackers=[CounterTracker(scope='ssr', reset_on='ssr')],
                        modifiers=[mod], lifecycle=AlwaysActive())
            pity._rebind_state(state)          # 装置纪律：直驱前须补一次 rebind
            out = pity.before_draw(_ctx(shape, state, space='card'))
            assert out == base_dist, (
                f'tf={tf}：该 scope 无卡（空目标集）时管道须恒等，实测 {out}')

    def test_s8_declared_shape_source_two_transfers_when_pA_zero(self):
        """**来源二**（§3.1.5.6.1）：`p(A) = 0` 但 `w(A) > 0` 时 `declared` 仍能转移。

        助手级：`shape='declared'` 的 `u_A` 取 `w_c / w(A)`，与当前分布无关，故目标组
        当前无概率时照常分配（这是 `declared` 唯一的用武之地）。**对照**：同输入下
        `shape='current'` 返 `None`（来源一的处置），两条并置才算钉住了分支差异。
        """
        dist = {'a': 0.0, 'b': 0.5, 'q': 0.5}
        weights = {'a': 0.3, 'b': 0.7, 'q': 1.0}
        d_declared = transfer_linear(dist, ('a',), ('q',), 0.5,
                                     shape='declared', weights=weights)
        assert d_declared is not None, '来源二：p(A) = 0 且 w(A) > 0 时须照常转移'
        assert d_declared['a'] == pytest.approx(0.5), (
            f'A 侧按 w 分配（u_A = 1.0 因单卡），实测 {d_declared}')
        assert d_declared['q'] == pytest.approx(-0.5)
        assert transfer_linear(dist, ('a',), ('q',), 0.5,
                               shape='current') is None, (
            '对照：`current` 在 p(A) = 0 时须返 None（§3.9.5 第 1 行）')

    def test_s8_declared_shape_source_one_returns_none_when_wA_zero(self):
        """**来源一**（池子声明该组不可获得）：`w(A) = 0` → `declared` 返 `None`。

        正对照（把 `w(a)` 抬起来即照常转移）一并给，防「一律返 None」通过。
        """
        dist = {'a': 0.5, 'q': 0.5}
        assert transfer_linear(dist, ('a',), ('q',), 0.5, shape='declared',
                               weights={'a': 0.0, 'q': 1.0}) is None, (
            '来源一：w(A) = 0 时须返 None（不转移）')
        d = transfer_linear(dist, ('a',), ('q',), 0.5, shape='declared',
                            weights={'a': 1.0, 'q': 1.0})
        assert d is not None and d['a'] == pytest.approx(0.5), (
            f'正对照：w(A) > 0 时须照常转移，实测 {d}')

    def test_s8_scope_outside_rarity_ranks_raises_config_error(self):
        """`scope` 不在 `[rarities].ranks` 内时 TOML 层抛 `ConfigError`（白名单硬拒）。

        **本步新增的覆盖**：该白名单（`config_toml._build_pity` 的 scope 校验）此前
        零测试消费者（全库 grep 该异常文案无命中），而 S8-6 的第 ⑥ 条把它列为必覆盖项。
        正对照：同结构下 `scope = "ssr"` 载入成功，防「一律拒绝」通过。
        """
        with pytest.raises(ConfigError) as excinfo:
            _s8_load_toml(_S8_SCOPE_TOML.format(scope='ur'))
        message = str(excinfo.value)
        assert "'ur'" in message and '未在 [rarities] 中注册' in message, (
            f'异常信息须点名出错取值与该白名单，实测 {message}')

        store = _s8_load_toml(_S8_SCOPE_TOML.format(scope='ssr'))
        assert store.pity.pities[0].scope == 'ssr', '正对照：合法 scope 须正常载入'
