"""P64 叶子原语层（§3.1.6）——保底引擎的最底层构件，仅依赖标准库。

本模块由 S1a 自 `core/pity.py` 迁出，`pity.py` 保留 re-export，故既有导入路径
（`from gacha_simulator.core.pity import PityState` 等）与 `core/__init__.py` 的导出
一律不变——**语义与接口完全保留，仅换存放文件**。

依赖方向（§3.1.6，强制）：本模块只依赖标准库；实现层
（`pity_tracker.py` / `pity_modifier.py`）单向依赖本模块、不 import `pity.py`；
编排层 `pity.py` 依赖本模块 + 两个实现层模块。三个 `_*_TYPES` 集合常量放在本层，
是因为 §3.1.4 骨架的 `Pity` 不继承 `CounterBasedBehavior`，裸名引用它们否则
`NameError`。
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ── P60 新增：DrawInfo (frozen) + PityContext (可变载体) ──

@dataclass(frozen=True)
class DrawInfo:
    """抽卡上下文中不可变的部分——本次抽卡的静态事实。

    **`base_probabilities` 的口径是卡级 `{card_id: p}`（P64 S8，§3.9.3）**：S8 前
    该字段按调用路径两种口径并存（`banner.draw` 传槽位级聚合结果、`strategy.py`
    传卡级），S8-2 起两个填充点（`core/banner.py` 的 `draw` 与 `core/strategy.py`
    的 `get_pity_probabilities`）一律传卡级，与 Modifier 链的 A / Q（卡集合）同
    键空间。**该口径是声明式的**：本字段无类型级约束，其唯一消费面是
    `transfer_linear(..., shape='declared', weights=...)`（`shape='current'` 分支
    完全不读它，填错无任何影响；空表 / `None` 会被 `not weights` 守卫报
    `ValueError`，**非空而键错位**的表不触发该守卫）。键空间错位的失效形态是
    **静默恒等**而非报错：`weights.get(c, 0.0)` 对 A 内每卡取 0 → `w(A) <= 0`
    → 助手返回 `None` → 生产骨架跳过 `_apply_delta`，分布原样输出、无任何提示
    （正是本项目反复登记要消除的形态）。`KeyError` 只在 **`dist`** 的键空间错位
    时触发（`transfer_linear` 首行的 `sum(dist[c] for c in Q)`），与本字段无关。

    `scope_slots` / `featured_slots` / `card_to_slot` 仍是槽位级，只服务保留到
    发布前的旧保底类与等价性装置（ISSUE-901），新卡级管道不读它们。
    """
    pool_id: str
    pool_instance_id: str
    reward_id: str
    reward_rarity: str
    is_featured: bool
    scope_cards: Mapping[str, tuple] = field(default_factory=dict)
    featured_cards: Mapping[str, tuple] = field(default_factory=dict)
    scope_slots: Mapping[str, tuple] = field(default_factory=dict)
    featured_slots: Mapping[str, tuple] = field(default_factory=dict)
    card_to_slot: Mapping[str, str] = field(default_factory=dict)
    base_probabilities: Mapping[str, float] = field(default_factory=dict)
    rarity_rank: Mapping[str, int] = field(default_factory=dict)


@dataclass
class PityContext:
    """管道中流转的可变载体。

    **`readonly` 是 S8 / M2 的查询标记**（§3.9.6 的「处置（两期）②」）：`True` 表示
    本次调度是只读查询（`PityEngine.get_probabilities` → `Pity.before_draw(readonly=True)`），
    不是真实抽卡。它是 `readonly` 形参从 Modifier 面废除后的落点：按 §3.1.2 的
    「新机制需要新的静态事实时**加字段、不改签名**」，而不是给 `compute_delta()` 加形参。
    写入者是 `Pity.before_draw` 的首行（唯一的 readonly 入口透传点），消费面当前一处：
    `RotatingModifier` 据此抑制 `extra_flag`（复刻旧 `RotatingCRBehavior` 的只读查询
    语义：查询不体现 CR 拦截）。**Trackers 侧的 `readonly`（`advance` / `prepare` 形参）
    是另一条通路**，不经本字段、不受本条影响。

    **`invariants` 是增量层校验器的 per-call 引用（P64 S8-6 接线，§3.13 增量行）**：
    计划 §3.13 原写「增量层由 `_apply_delta()` 内部调用」，而 S8-1 把 `_apply_delta`
    迁到本叶子层、签名收为 `(dist, d)`，**取不到 `pool_id` 与校验器**，故该写法不可
    执行。三条候选的裁决与理由见 `Pity.before_draw` 的内循环注记：取「调用点移到骨架
    内循环」，本字段即校验器进入骨架的**唯一通道**（行为层与引擎之间现无其他通道，
    而给 `before_draw` 加形参会同时打到保留到发布前的 10 个旧类，它们不接受该形参）。
    **类型写作 `Any` 而非 `InvariantChecker`**：本层只依赖标准库（§3.1.6），
    `invariants.py` 反向 import 本层，故此处不得 import 它；消费面只要求
    `check_delta(pool_id, dist, delta)` 这一个鸭子类型方法。
    写入者是 `PityEngine.before_draw`（**只在该入口**：`get_probabilities` 按
    `core/invariants.py` 已登记的「四层覆盖边界」不在判据面内）；`None` = 未接线
    （生产默认，连实例都不建）。
    """

    draw: DrawInfo
    current: Dict[str, float]
    state: 'PityState'
    readonly: bool = False
    invariants: Optional[Any] = None


# ── P60 新增：Counter / Flag 微抽象 ──

@dataclass
class Counter:
    """PityState 计数器遥控器——记住地址，封装操作。"""
    _state: 'PityState'
    _name: str
    _key: str = "counter"

    def incr(self, delta: int = 1) -> int:
        return self._state.incr(self._name, self._key, delta)

    def reset(self) -> None:
        self._state.set(self._name, self._key, 0)

    def value(self) -> int:
        return self._state.get(self._name, self._key, 0)

    def reached(self, threshold: int) -> bool:
        return self.value() >= threshold


@dataclass
class Flag:
    """PityState 布尔标志遥控器。"""
    _state: 'PityState'
    _name: str
    _key: str

    def set(self) -> None:
        self._state.set(self._name, self._key, True)

    def clear(self) -> None:
        self._state.set(self._name, self._key, False)

    def is_set(self) -> bool:
        return self._state.get(self._name, self._key, False)


# ── P60 新增：跨 type 生命周期参数 ──

@dataclass(frozen=True)
class LifecycleConfig:
    """跨 type 共享的生命周期参数。P56 扩展 deactivate_on_early_hit / depends_on。

    frozen=True：纵深防御——阻止运行时意外修改。
    """
    deactivate_on_early_hit: bool = False         # P56 扩展
    depends_on: Optional[str] = None              # P56 扩展


class PityState:
    """三层嵌套 namespace 容器——每个 behavior 通过自身 name 存取任意类型数据。"""

    def __init__(self):
        self.data: Dict[str, Dict[str, Any]] = {}

    def get(self, name: str, key: str, default=None):
        """读取 behavior name 下 key 的值。"""
        return self.data.get(name, {}).get(key, default)

    def set(self, name: str, key: str, value):
        """写入 behavior name 下 key 的值。"""
        self.data.setdefault(name, {})[key] = value

    def incr(self, name: str, key: str, delta=1) -> int:
        """递增 behavior name 下 key 的计数器值。"""
        v = self.get(name, key, 0) + delta
        self.set(name, key, v)
        return v

    def clone(self) -> 'PityState':
        ps = PityState()
        ps.data = {name: dict(ns) for name, ns in self.data.items()}
        return ps

    def to_dict(self) -> Dict[str, Any]:
        return {"data": {name: dict(ns) for name, ns in self.data.items()}}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'PityState':
        ps = cls()
        if "data" in d:
            # 防御性复制——确保 from_dict() 返回的 PityState 与输入 dict 完全解耦
            ps.data = {name: dict(ns) for name, ns in d["data"].items()}
        # P81 B9：P60 之前的 {"counters": {...}} 旧序列化格式的自动升级分支已删除
        # （其生产者只有测试；真实数据均为 to_dict() 产出的 {"data": {...}} 新格式）。
        return ps

# ── btype 分类集合（P64 S1a：自 CounterBasedBehavior 的类属性升为模块级常量）──
# 消费面：`Pity` 骨架（§3.1.4，不继承 CounterBasedBehavior 故须裸名可取）、
# `CounterBasedBehavior`（保留为同对象别名）、`config_toml` 的同名拷贝
# （由 tests/core/test_pity_config_toml.py::TestDuplicatedConstants 钉住相等）。
_SOFT_TYPES = frozenset({'soft_interval', 'soft_additive', 'soft_step'})
_HARD_TYPES = frozenset({'hard'})
# ISSUE-105：`rotating_inverse`（G1 幻塔连中后必歪）是**事件驱动型**，故本集合的
# 内容须追加它，不是原样迁移。落地先于该类型的注册（S6a），提前列出无副作用。
_EVENT_DRIVEN_TYPES = frozenset({'rotating', 'targeted', 'targeted_soft',
                                 'rotating_cr', 'rotating_cr_soft', 'rotating_soft',
                                 'rotating_inverse'})

# ── 外部写入键白名单（S11 审查收口 F3：自编排层下沉，一处声明）──
#: 三族声明集之外的**外部写入键**白名单。消费面两处：`Pity._check_declared_keys`
#: 的判据 2（§3.12.2 构造期）与 `InvariantChecker._check_declared_state` 的状态层
#: （§3.13 运行期）。
#:
#: 键的来历：`selected_card` 由**零件之外的层**写入（策略层的 `NonDrawAction`
#: （`service/gacha_service.py` 的 `switch_epitomized_target` / `cancel_epitomized_path`
#: 两条路径）与 `_build_pity_state_init`；**无任何零件声明它**，而 `FateTracker`
#: 与 `SelectedModifier` 都会读它，且该键的初始化路径独立于零件声明（§3.1.1 的
#: L4 例外 2：无条件注入，`sc` 为 `None` 也写）。不留白名单则 `targeted` 族的
#: 全部合法配置在**构造期**被判为「引用不存在的键」、在**运行期**被状态层判为
#: 「未声明键」。
#:
#: **放在叶子层的理由**：`core/pity.py` 与 `core/invariants.py` 两个消费模块
#: **都已 import 本层**，故两处取到的是**同一对象**：不需要镜像副本、不需要
#: 逐元素漂移守卫、也不需要函数内惰性 import（§3.14.2 的「一处声明」纪律）。
#: 本模块只依赖标准库（§3.1.6），不因此引入任何依赖方向问题。
_EXTERNAL_STATE_KEYS = frozenset({'selected_card'})

# ── 概率代数（P64 S8：卡级增量管道的两个本原函数，§3.9.2 / §3.9.4）──
#
# 两者都是**纯函数、只依赖标准库**，故住叶子层（§3.1.6）：
# - `_apply_delta` 的消费面有两处且分居两层：编排层的 `Pity.before_draw` 内循环
#   （§3.1.4 骨架）与**实现层** `pity_modifier.Modifier.apply` 的默认实现（§3.14.3）。
#   实现层**不得 import `pity.py`**（§3.1.6 的单向依赖，双向 import 即循环），故它
#   只能住叶子层：放 `pity.py` 会让基类只能走函数内惰性 import（本项目已把
#   「函数内 import 漏改不报错」列为缺陷形态，见 §3.9.3 的 banner 局部 import 处置）。
#   `pity.py` 以 `from .pity_primitives import _apply_delta` 再导出，故
#   `from gacha_simulator.core.pity import _apply_delta` 亦可用（§3.9.2 称其为
#   「框架级」函数，该名在编排层可见）。
# - `transfer_linear` 的消费面在 `pity_modifier.py`（六个机制）与 preset 工厂，
#   同一条理由（§3.9.4 的「模块归属」段）。

def _apply_delta(dist: Dict[str, float], d: Dict[str, float]) -> Dict[str, float]:
    """把增量向量 `d` 作用到分布 `dist` 上并**归一化**（§3.9.2 的框架级归一化）。

    `out = {c: dist[c] + d.get(c, 0.0) for c in dist}`：只遍历 `dist` 的键，故
    **`d` 里多出来的键不参与输出**（增量向量按稀疏给出：未列出的卡 δ = 0）；
    归一化 `Σ(out) <= 0` 时返回原 `dist`（该行是退化保护，§3.9.5 的「归一化后
    总量 ≤ 0」行）。

    **转移族下本函数退化为恒等**（§3.1.5.2.1：转移族恒有 `Σδ = 0`，故
    `Σ(p + δ) ≡ 1`），但它**不因此可删**：接口本身允许不配平的自定义 Modifier
    （§3.9.2 的「为什么归一化放引擎层」段），归一化是对该接口的兜底。
    """
    out = {c: dist[c] + d.get(c, 0.0) for c in dist}
    total = sum(out.values())
    return dist if total <= 0 else {c: v / total for c, v in out.items()}


def transfer_linear(dist: Dict[str, float], A, Q, amount: float,
                    shape: str = 'current', weights=None) -> Optional[Dict[str, float]]:
    r"""把 `amount` 的概率质量从 Q 搬到 A，返回**增量向量**（§3.9.4）。

    ```
    A 内每卡 + amount · u_A(c)        u_A 由 shape 定：
                                        'current'  → p_c / p(A)
                                        'declared' → w_c / w(A)，w 由 weights 传入
    Q 内每卡 − amount · p_c / p(Q)    （Q 侧恒为当前形状，不可指定）
    其余不写（= 0）
    ```

    配平：`Σδ = amount − amount = 0`，故 `Σ(p + δ) = 1`、框架归一化退化为恒等
    （§3.1.5.2.1）。

    **定位是助手、不是接口**（§3.9.4 首段）：Modifier 的接口是
    `compute_delta(view, dist, ctx)`，返回任意增量向量；当前七个机制恰好都落在
    「A 加 Q 减」这一族，故提供本函数供其复用。**不属于该族的新机制直接实现
    `compute_delta()`，不经过本函数。**

    **A 与 Q 必须不交**（§3.9.4 的前置条件表）：相交时同一张卡既加又减，结果由
    字典写法次序决定、语义无定义。本助手**不做该校验**（调用方按 §3.1.2 机制表
    构造 A/Q，两者天然不交）。

    边缘返回 `None` 的三处（恒等；均为**防御性**返回，调用方仍应在
    `compute_delta()` 开头自行早退，以免把行为依赖在助手的内部实现上）：
    `p(Q) <= 0`（无货可取）/ `amount <= 0`（不转移）/ `shape='current'` 时
    `p(A) <= 0`（`u_A` 未定义）。`shape='declared'` 时改判 `w(A) <= 0`
    （池子声明该组不可获得）：**该分支在 `p(A) = 0` 时仍可分配**，这正是
    `declared` 唯一的用武之地（§3.1.2 的「A 侧形状」段 / §3.1.5.6.1 的
    「来源二」在冲突配置下由此生效）。

    `dist` 与 `A` / `Q` 的键空间必须一致（S8 起都是**卡级**，D20）；键不一致时
    此处直接 `KeyError` 而非静默恒等：静默恒等会让全部保底无声失效，而报错能
    在首次抽卡就暴露键空间错位。
    """
    pQ = sum(dist[c] for c in Q)
    if pQ <= 0 or amount <= 0:
        return None                      # 无货可取 / 不转移 → 恒等
    if shape == 'current':
        pA = sum(dist[c] for c in A)
        if pA <= 0:
            return None                  # 目标组当前无概率 → u_A 未定义（不转移）
        uA = {c: dist[c] / pA for c in A}
    elif shape == 'declared':
        if not weights:
            raise ValueError("shape='declared' 必须同时传 weights"
                             "（声明权重，即 ctx.base_probabilities）")
        wA = sum(weights.get(c, 0.0) for c in A)
        if wA <= 0:
            return None                  # 池子声明该组不可获得 → 不转移
        uA = {c: weights.get(c, 0.0) / wA for c in A}
    else:
        raise ValueError("未知的 shape: %r" % (shape,))

    d = {c: amount * uA[c] for c in A}
    for c in Q:
        # **先除后乘**（`amount * (dist[c] / pQ)`，不是 `amount * dist[c] / pQ`）：
        # 夺取型机制的 `amount` 与 `pQ` 由**同一表达式**算出（调用方传
        # `sum(dist[c] for c in Q)`，本函数内同式同序），故两者**位级相等**；
        # 此时「源组归零」（§3.9.5 的 `p(Q) == amount` 行）要求 Q 侧增量的量值与
        # `dist[c]` 精确抵消，而先乘后除的写法会留下 1 ULP 的**负**残值
        # （实测 `dist[c] = pQ = amount = 0.4` 得 `-5.55e-17`）：它会被 §3.12.1 的
        # 非负性判据判为违规（`not (v >= 0)`），也会让 `pool.draw` 的累积权重
        # 出现极小的非单调段。先除后乘在该形态下给出精确 0.0。
        d[c] = d.get(c, 0.0) - amount * (dist[c] / pQ)
    return d


__all__ = [
    'Counter', 'Flag', 'DrawInfo', 'PityContext', 'LifecycleConfig', 'PityState',
    '_SOFT_TYPES', '_HARD_TYPES', '_EVENT_DRIVEN_TYPES', '_EXTERNAL_STATE_KEYS',
    'transfer_linear', '_apply_delta',
]
