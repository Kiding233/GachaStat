from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set
import random

# ── P64 S1a：叶子原语层迁出至 pity_primitives（§3.1.6）──
# 下方 re-export 使既有导入路径不变；三个类型集合常量在本模块内**裸名**可用
# （`Pity` 骨架不继承 CounterBasedBehavior，S3-1 起需要）。
from .pity_primitives import (  # noqa: F401
    Counter, Flag, DrawInfo, PityContext, LifecycleConfig, PityState,
    _SOFT_TYPES, _HARD_TYPES, _EVENT_DRIVEN_TYPES, _EXTERNAL_STATE_KEYS,
    # P64 S8-1 / S8-3：卡级增量管道的两个本原函数。**定义**住叶子层
    # （`pity_primitives.py`），此处 re-export 使其在编排层可见：
    # `_apply_delta` 的另一个消费方是**实现层**的 `Modifier.apply` 默认实现，
    # 而实现层不得 import 本模块（§3.1.6 单向依赖），故它不能定义在本模块内
    # （§3.9.2 称之为「框架级」函数，指可见面而非存放文件）。
    transfer_linear, _apply_delta,
)
from .pity_tracker import (  # noqa: F401
    AlwaysActive, CounterTracker, DependentActive, DependentFiniteActive,
    FateTracker, FiniteActive, FlagTracker, Lifecycle, NamespaceTracker,
    StreakTracker, Tracker,
)
from .pity_modifier import (  # noqa: F401
    KNOWN_SIM_SOURCES, HardModifier, Modifier, NonFeaturedModifier, RotatingModifier,
    SelectedModifier, SoftModifier,
)
# P64 S11（ISSUE-003）：校验层由编排层**单向**引用——本模块 import 它，它不 import
# 本模块（checker 的 `engine` 一律经实参传入），故不成环。类的定义归 `core/invariants.py`。
from .invariants import InvariantChecker
# P64 S9-2：`sim` 形参的类型注记用字符串前向引用 `'SimView'`（`SimView` 住
# `core/state.py`，本模块不 import 它：只为类型检查而引用，运行期不需要该对象）。
if TYPE_CHECKING:  # pragma: no cover - 仅类型检查
    from .state import SimView



# ── P64 S1d：生命周期字段 → Lifecycle 对象的唯一转换点（ISSUE-301）──

def build_lifecycle(pdef) -> Lifecycle:
    """把 `PityDef` 的两个生命周期字段转成 Lifecycle 对象——全库唯一转换点。

    两个维度**独立取值**（2026-09-28 修正：非「`depends_on` 优先」）：
    激活维 = `depends_on` 非空 ? `Dependent` : `Always`；退役维 =
    `max_triggers > 0` ? `AfterN(n)` : `Never`。四组合全部合法（§3.1.3 的四行表）。

    **注意退役维取 `max_triggers`，不是 `deactivate_on_early_hit`**——后者是与两维
    正交的**第三个开关**（布尔，命中即退役），四组合下均由 `should_deactivate`
    一并判定；`cfg` 里两个字段都带入。

    旧 `create_behavior` 的 `lifecycle_kwargs` 段（`LifecycleConfig(**kwargs)`）
    是这两个字段此前的转换点，已随 S4-4 删除：同一转换不得留两处。
    """
    cfg = LifecycleConfig(
        deactivate_on_early_hit=bool(getattr(pdef, 'deactivate_on_early_hit', False)),
        depends_on=getattr(pdef, 'depends_on', None),
    )
    _dep = cfg.depends_on
    _n = getattr(pdef, 'max_triggers', 0) or 0
    if _dep and _n > 0:
        return DependentFiniteActive(cfg, max_triggers=_n)
    if _dep:
        return DependentActive(cfg)
    if _n > 0:
        return FiniteActive(cfg, max_triggers=_n)
    return AlwaysActive(cfg)


# ── P64 S4-2：preset 工厂的三个取值 helper（§3.2 取值来源表）──
# 三者与 `build_lifecycle` 同为「PityDef 字段 → 零件实参」的唯一转换点，故同居本模块。

def _norm_scope(pdef, default: str = 'ssr') -> str:
    """scope 的**唯一归一化点**（ISSUE-503），`create_behavior` 与全部 preset 工厂共用。

    与 `create_behavior` 的 `scope = (getattr(pdef,'scope',None) or _default_scope).lower()`
    同式同源：`create_behavior` 侧把 registry 条目的 `default_scope` 传进来（10 条目
    全为 `'ssr'`），preset 侧用默认值（§3.2 取值来源表）。

    **不归一化的后果**：`Pity._scope` 是小写、而各 Tracker / Modifier 的 `_scope` 是
    `pdef` 原值，任何绕开 TOML 层 `.lower()`（`config_toml.py:645`）的直构路径
    （`PityDef(scope='SSR', …)`）会让 `ctx.draw.scope_cards.get('SSR', ())` 取空 →
    增量为 `None` → **该保底静默恒等、不报错**。
    """
    return (getattr(pdef, 'scope', None) or default).lower()


def _target_of(pdef) -> str:
    """`pdef.target_featured` 决定目标集（ISSUE-403），全库唯一的取值点。

    `True`  → 目标集 = scope 内的 featured 卡集（旧 `target_slots = featured_slots`）
    `False` → 目标集 = scope 内全部卡（旧 `target_slots = scope_slots`）
    缺省同 `False`（`PityDef.target_featured` 默认 `False`）。

    **空 featured 集必须回退 scope 全集**（对齐旧的 `.get(scope, scope_slots)`），
    该回退由消费方 `HardModifier._target_keys()` 承担（`featured_cards.get(scope)
    or scope_cards.get(scope, ())`）。缺这条回退，无 featured 卡的池在
    `target_featured=True` 下会退化为恒等（旧实现回退全部 scope 槽）。

    **消费面只有 `hard` 一族**（裁决 7B，2026-10-05）：`soft_*` + `target_featured
    = true` 由 `create_behavior` 抛 `ConfigError`，`_preset_soft_step` 不写 `target=`；
    `rotating` 族旧实现忽略该字段，故六个事件驱动 preset 亦不加 `target=`
    （照抄到事件驱动族即语义漂移）。
    """
    return 'featured' if getattr(pdef, 'target_featured', False) else 'scope'


def _soft_deltas_of(pdef) -> tuple:
    """`deltas` 的**唯一展开点**（ISSUE-001 / M6），四个 soft 系类型共用。

    旧 `SoftPityMixin._init_soft_pity`（`CounterBasedBehavior` 侧的对应物是
    `create_behavior` 的 deltas 组装段）三分支归一的 preset 侧替代：

      ① `pdef.deltas` / `pdef.soft_deltas` 非空 → 直接用它（`soft_step` 形态）；
      ② 否则 `soft_increment is not None` → 归一为 `soft_additive` 后展开；
      ③ 否则归一为 `soft_interval` 后展开（`soft_start` 缺省 74、`soft_end`
         缺省 90，与 `_init_soft_pity` 的默认值同值）。

    对 counter 驱动三类型，`_build_pity` 已在 `pdef.deltas` 里放好展开结果
    （`config_toml.py:927-934`），故 ① 是常态路径；分支 ②③ 是「后缀型只写语法糖」
    的路径，旧路径由 `_init_soft_pity` 承担，preset 化后由本函数承担。

    **分支 ③ 相对旧路径改变了行为（S4-2 审查 minor，登记）**：纯 `soft_interval` /
    `soft_additive` 在 `deltas` 与语法糖都缺省时，旧路径 `SoftStepBehavior.__init__`
    抛 `ValueError`（被引擎吞成 warning、该保底整条消失），而本函数的 74/90 缺省会
    让它**真的生效**（counter=85 时 `ssr` 0.02 对 0.78）。方向是「从静默消失变为按
    缺省生效」，属修复方向；但旧路径并无此缺省（缺省值原本只服务三个 `_soft` 复合
    类型），故该形态的行为差异须由 S5b 的 counter 驱动批次或 §六 口径一并覆盖。

    **`pdef.btype` 一律不得直喂 `_expand_soft_to_deltas`**：该函数
    （`config_toml.py:1838`）只认 `soft_interval` / `soft_additive` 两个字面量，其余
    一律落到函数末尾的 `return ()`；后缀型（`rotating_soft` / `rotating_cr_soft` /
    `targeted_soft`）的 btype 恰在「其余」之内，直喂的后果是「只写 soft_start /
    soft_end（或只写 soft_increment）」的合法配置展开出空元组 → `SoftModifier` 的
    boost 恒 0、该步增量恒 `None`（恒等）→ **软保底静默消失、且不报错**。
    旧路径不踩这一条：`_init_soft_pity` 先归一 btype 再展开。
    """
    if getattr(pdef, 'deltas', None) is not None:
        return pdef.deltas
    if getattr(pdef, 'soft_deltas', None):
        return pdef.soft_deltas
    from .config_toml import _expand_soft_to_deltas
    _s = pdef.soft_start if getattr(pdef, 'soft_start', None) is not None else 74
    _e = pdef.soft_end if getattr(pdef, 'soft_end', None) is not None else 90
    if getattr(pdef, 'soft_increment', None) is not None:
        return _expand_soft_to_deltas('soft_additive', _s, _e, pdef.soft_increment)
    return _expand_soft_to_deltas('soft_interval', _s, _e, None)


class PityBehavior(ABC):
    def _rebind_state(self, state: 'PityState') -> None:
        """P75：将本 behavior 的 Counter/Flag 重绑到新的 PityState 实例。

        纯重定向、不复制旧值——初始状态完全由 per-call state（阶段 3 完整快照）承载。
        子类覆写此方法重绑自身特有的 Counter/Flag（无特有字段则继承默认空实现）。
        """
        pass


# ── P60 新增：计数器驱动型保底基类 ──

class CounterBasedBehavior(PityBehavior, ABC):
    """计数器驱动型保底的通用生命周期。

    子类只需覆写 _compute_probabilities(ctx, counter) → Dict[str, float]。
    计数器管理（增/查/重置/触发上限/停用）由基类统一处理。

    P55 变更：新增 btype 参数（推导 is_soft/is_hard/is_event_driven）
    与 _on_reset() 钩子（子类可覆写以绕过默认重置流程）。
    """

    # ── btype → 分类属性映射 ──
    # P64 S1a：内容升为 `pity_primitives` 的模块级常量（§3.1.6），此处保留为
    # **同对象别名**——既有读法（本类的 is_soft/is_hard/is_event_driven、下方
    # create_behavior 的局部常量、config_toml 的防漂移断言）一律不变，且不存在
    # 第二份真相源。`_SOFT_SUFFIX_TYPES` 不在迁移面内（两侧内容本已相同）。
    _SOFT_TYPES = _SOFT_TYPES
    _HARD_TYPES = _HARD_TYPES
    _EVENT_DRIVEN_TYPES = _EVENT_DRIVEN_TYPES
    # 软保底后缀型：deltas 由 SoftPityMixin 独立展开，不经 PityDef.deltas。
    # config_toml._SOFT_SUFFIX_TYPES 是同内容的另一份拷贝（写回侧用），
    # 两者由 tests/core/test_pity_config_toml.py::TestDuplicatedConstants 钉住相等。
    # （本组常量位于 CounterBasedBehavior，与 _SOFT_TYPES / _HARD_TYPES 同处。）
    _SOFT_SUFFIX_TYPES = frozenset({'rotating_soft', 'rotating_cr_soft', 'targeted_soft'})

    def __init__(self, name: str, state: 'PityState', scope: str, btype: str,
                 reset: str = None, target_featured: bool = False,
                 lifecycle: 'LifecycleConfig' = None):
        self._name = name
        self._state = state
        self._scope = scope                      # 稀有度层级
        self._btype = btype                      # P55：行为类型标识
        self._target_featured = target_featured
        self._reset = reset if reset is not None else scope
        # sentinel 模式——避免可变默认参数共享
        self._lifecycle = lifecycle if lifecycle is not None else LifecycleConfig()
        self._active = Flag(state, name, "_active")
        if self._lifecycle.depends_on is None:
            self._active.set()

        # P55：从 btype 推导分类属性
        self.is_soft = btype in self._SOFT_TYPES
        self.is_hard = btype in self._HARD_TYPES
        self.is_event_driven = btype in self._EVENT_DRIVEN_TYPES

    @abstractmethod
    def _compute_probabilities(self, ctx: 'PityContext', counter: int) -> Dict[str, float]:
        """子类实现——给定上下文和当前计数器值，返回调整后概率分布。"""
        ...

    def _counter(self) -> 'Counter':
        return Counter(self._state, self._name, "counter")

    # ── P75：_rebind_state——重绑 Counter/Flag 到 per-call state ──

    def _rebind_state(self, state: 'PityState') -> None:
        """重绑本 behavior 的 Counter/Flag 到新 PityState（纯重定向，不复制旧值）。

        P55 蓝图（归档文档 line 1914-1925）设计——构造时绑定 + per-call 调度重绑，
        保证计数写入调度层实际使用的 state 对象。初始值由阶段 3 完整快照承载。
        """
        self._state = state
        self._active = Flag(state, self._name, "_active")
        self._on_rebind_state(state)

    def _on_rebind_state(self, state: 'PityState') -> None:
        """子类覆写点——重绑子类特有的 Counter/Flag。默认空实现。

        当前 10 种 behavior 均无覆写需求（特有字段已由各自 _rebind_state 或
        PityBehavior 子类显式处理），该钩子仅为未来新增带特有 Counter/Flag 的
        behavior 预留扩展点。实现时不得因「无覆写者」删除该调用。
        """
        pass

    # ── P55：_on_reset() 钩子 ──

    def _on_reset(self, ctx: 'PityContext') -> bool:
        """子类可覆写——在 _should_reset() 后、默认重置前调用。

        Returns:
            True  → 子类已完全处理重置逻辑，跳过默认 reset+incr 流程。
            False → 继续执行默认重置（counter 归零 + triggers 累加）。
        """
        return False

    # ── 生命周期由基类统一管理 ──

    def before_draw(self, ctx: 'PityContext', readonly: bool = False) -> Dict[str, float]:
        if not self._active.is_set():
            return ctx.current.copy()
        if readonly:
            # 只读查询——仅基于当前值计算概率，不修改状态
            v = self._counter().value()
        else:
            v = self._counter().incr()
        return self._compute_probabilities(ctx, v)

    def after_draw(self, ctx: 'PityContext') -> None:
        if not self._active.is_set():
            return
        if not self._should_reset(ctx):
            return
        # ── P55 新增：_on_reset() 钩子 ──
        if self._on_reset(ctx):
            return  # 子类已完全处理——跳过默认 reset+incr 流程
        # ── 默认重置流程 ──
        self._counter().reset()

    def _should_reset(self, ctx: 'PityContext') -> bool:
        if self._reset == "featured":
            return ctx.draw.is_featured
        if self._reset == "never":
            # G16（P64 独立先行）：永不重置，即幻塔「出金不重置」。
            # P64 主线落地后本分支由 CounterTracker(reset_on="never") 自然承载。
            return False
        return ctx.draw.reward_rarity == self._reset

    def did_fire(self, ctx: 'PityContext') -> bool:
        return self._should_reset(ctx)


# ── P55：SoftStepBehavior —— 唯一的 counter 驱动软保底类 ──

class SoftStepBehavior(CounterBasedBehavior):
    """RLE deltas 驱动的通用软保底——唯一的 counter 驱动型软保底。

    deltas 格式：((抽数段, 每抽增量%), ...)
    例：((73, 0.0), (17, 5.88)) → 前 73 抽不增，后 17 抽每抽 +5.88%

    soft_interval / soft_additive 在 TOML 解析时通过 _expand_soft_to_deltas()
    展开为 deltas，统一由此类消费。
    """

    def __init__(self, name: str, state: 'PityState', scope: str, btype: str,
                 deltas: tuple, target_featured: bool = False,
                 lifecycle: 'LifecycleConfig' = None, reset: str = None):
        if deltas is None:
            raise ValueError(
                f"SoftStepBehavior '{name}' 的 deltas 为 None——"
                f"soft_interval/soft_additive 语法糖必须在构造前通过 "
                f"_expand_soft_to_deltas() 展开。"
            )
        super().__init__(name, state, scope, btype,
                         reset=reset, target_featured=target_featured,
                         lifecycle=lifecycle)
        self._deltas = deltas  # tuple[tuple[int, float], ...]

    # ── 核心：counter → 累计 boost% ──

    def _cumulative_boost(self, counter: int) -> float:
        """遍历 deltas RLE，按 counter 定位当前段并计算累计 boost%。

        防御：跳过 n <= 0 的无效段（防止 counter 不减反增、boost 翻倍）。
        counter 超出所有段时延续最后一档的增量率。
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

    # ── 概率调整 ──

    def _compute_probabilities(self, ctx: 'PityContext', counter: int) -> Dict[str, float]:
        """按 counter 计算 boost，跨稀有度重分配概率。

        算法：
          1. 累计 deltas → boost_pct（0–100）
          2. 定位 scope 槽位 + target_featured 收窄目标
          3. 从非目标槽位（含低稀有度，排除高稀有度）取概率 → 转给目标槽位
          4. 目标槽位内部按基础权重比例分配（不改变 featured/standard 比例）
        """
        # 1. 累计 boost
        boost_pct = self._cumulative_boost(counter)
        if boost_pct <= 0:
            return ctx.current.copy()

        # 2. 槽位分组
        scope_slots = ctx.draw.scope_slots.get(self._scope, ())
        if not scope_slots:
            return ctx.current.copy()

        if self._target_featured:
            target_slots = ctx.draw.featured_slots.get(self._scope, scope_slots)
        else:
            target_slots = scope_slots

        # 3. 确定可抽取的概率池——排除目标槽位 + 更高稀有度槽位（层级保护）
        result = ctx.current.copy()
        scope_rank = ctx.draw.rarity_rank.get(self._scope, 99)

        higher_slots = set()
        for rarity, rank in ctx.draw.rarity_rank.items():
            if rank < scope_rank:
                higher_slots.update(ctx.draw.scope_slots.get(rarity, ()))

        non_target = [s for s in result
                      if s not in target_slots
                      and s not in higher_slots]

        if not non_target:
            return result

        pool = sum(result.get(s, 0.0) for s in non_target)
        if pool <= 0:
            return result

        # 4. 重分配：从 non_target 取 t 给 target（t 为百分点绝对量，§3.4.1 修正 ①）
        t = min(boost_pct / 100.0, pool)
        target_total = sum(result.get(s, 0.0) for s in target_slots)
        if target_total <= 0:
            return result          # 目标组当前无概率，不转移
        k_t = (target_total + t) / target_total
        k_q = (pool - t) / pool
        for s in target_slots:
            result[s] = result.get(s, 0.0) * k_t
        for s in non_target:
            result[s] = result.get(s, 0.0) * k_q

        return result

    # ── P55：硬保底接力 _on_reset() ──

    def _on_reset(self, ctx: 'PityContext') -> bool:
        """soft 保底触发后——若配置了 deactivate_on_early_hit，停用自身。

        任意一次 SSR 命中 → 退役。与 HardPityBehavior 语义一致。
        """
        if self._lifecycle.deactivate_on_early_hit:
            self._active.clear()
            return True
        return False


# ── P55：HardPityBehavior —— CounterBasedBehavior 子类，scope 化 ──

class HardPityBehavior(CounterBasedBehavior):
    """计数器驱动硬保底——counter 达到 threshold 时 scope 概率强制 100%。

    P55 变更：从 PityBehavior 直接子类改为 CounterBasedBehavior 子类，
    通过 scope 槽位定位目标。
    """

    def __init__(self, name: str, state: 'PityState',
                 scope: str = 'ssr', btype: str = 'hard',
                 threshold: int = 90, target_featured: bool = False,
                 lifecycle: 'LifecycleConfig' = None, reset: str = None):
        super().__init__(name, state, scope, btype,
                         reset=reset, target_featured=target_featured,
                         lifecycle=lifecycle)
        self._threshold = threshold

    # ── 新架构接口 ──

    def _compute_probabilities(self, ctx: 'PityContext', counter: int) -> Dict[str, float]:
        """counter 达到 threshold 时 scope 概率强制 100%。

        算法：
          1. 未达 threshold → 原样返回
          2. 定位 scope 槽位 + target_featured 收窄目标
          3. 目标槽位概率 = 100%（按基础权重比例分配），其余 = 0%
        """
        if counter < self._threshold:
            return ctx.current.copy()

        # 槽位分组
        scope_slots = ctx.draw.scope_slots.get(self._scope, ())
        if not scope_slots:
            return ctx.current.copy()

        if self._target_featured:
            target_slots = ctx.draw.featured_slots.get(self._scope, scope_slots)
        else:
            target_slots = scope_slots

        # 目标槽位强制 100%（按基础权重比例分配）
        result = {k: 0.0 for k in ctx.current}
        target_weights = [ctx.draw.base_probabilities.get(s, 0.0) for s in target_slots]
        total_weight = sum(target_weights)
        if total_weight > 0:
            for s, w in zip(target_slots, target_weights):
                result[s] = w / total_weight
        elif target_slots:
            # 兜底：均分
            per = 1.0 / len(target_slots)
            for s in target_slots:
                result[s] = per

        # 保留非目标槽位的稀有度层级保护——更高稀有度不变
        scope_rank = ctx.draw.rarity_rank.get(self._scope, 99)
        for rarity, rank in ctx.draw.rarity_rank.items():
            if rank < scope_rank:
                for s in ctx.draw.scope_slots.get(rarity, ()):
                    result[s] = ctx.current.get(s, 0.0)

        return result

    # ── P55：_on_reset() 钩子 —— deactivate_on_early_hit ──

    def _on_reset(self, ctx: 'PityContext') -> bool:
        """硬保底触发后——若配置了 deactivate_on_early_hit，停用自身。

        任意一次 SSR 命中（无论 counter 是否达到 threshold）→ 退役。
        """
        if self._lifecycle.deactivate_on_early_hit:
            self._active.clear()
            return True
        return False


# ── P56：_redistribute_scope() —— rotating/targeted 家族共用的概率重分配工具 ──
#
# **S8 处置（ISSUE-502，强制）**：本函数**本体保留**，与叶子层的卡级助手
# `transfer_linear`（`pity_primitives.py`，§3.9.4）并存。理由：本模块内仍有 4 处
# 调用点，全部位于**按 GATE-5 要保留到发布前的旧类体内**（`RotatingBehavior` /
# `RotatingCRBehavior._force_featured` / `TargetedBehavior` 两处）：删函数本体即
# `NameError`（模块级名字在**调用时**解析，导入期与 ruff 都不报错），而 S5a 等价性
# 装置与 S8-6 的「对 S5 产物容差 1e-12」正是拿这些旧类当基准。
# 故 S8 只**新增**卡级 `transfer_linear` 并让新骨架改用它（`Pity.before_draw` 经
# Modifier 链消费）；本函数与其 4 处调用点、10 个旧保底类、`PoolPitySpec` /
# `DrawInfo` 的槽位三字段、`compute_scope_mappings` 的槽位产出，一律并入 GATE-5
# 末条「发布前一次性移除旧保底类」的同一个 commit（ISSUE-901）。

def _redistribute_scope(ctx, featured_ratio, total, featured_slots, scope):
    """在 featured/非featured 之间按基础权重比例重分配 scope 总概率。"""
    result = ctx.current.copy()
    featured_total = total * featured_ratio
    non_featured_total = total - featured_total
    f_weights = [ctx.draw.base_probabilities.get(s, 0.0) for s in featured_slots]
    f_total_w = sum(f_weights)
    if f_total_w > 0:
        for s, w in zip(featured_slots, f_weights):
            result[s] = featured_total * w / f_total_w
    elif featured_slots:
        per_target = featured_total / len(featured_slots)
        for s in featured_slots:
            result[s] = per_target
    non_featured_slots = [s for s in ctx.draw.scope_slots.get(scope, ()) if s not in featured_slots]
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


# ── P56：RotatingBehavior —— 事件驱动的纯净轮换保底 ──

class RotatingBehavior(PityBehavior):
    """事件驱动的纯净轮换保底。小保底沿用基础分布比例，大保底 featured 100%。"""
    def __init__(self, name, state, scope="ssr", guaranteed_init=False, **kwargs):
        self._name = name
        self._scope = scope
        self._btype = 'rotating'
        self.is_soft = False
        self.is_hard = False
        self.is_event_driven = True
        self._guaranteed = Flag(state, name, "guaranteed")
        if guaranteed_init:
            self._guaranteed.set()

    def _rebind_state(self, state):
        self._state = state
        self._guaranteed = Flag(state, self._name, "guaranteed")

    def before_draw(self, ctx, readonly=False):
        total = self._scope_total_prob(ctx)
        if total <= 0:
            return ctx.current.copy()
        featured_slots = self._featured_slots(ctx)
        if not featured_slots:
            return ctx.current.copy()
        if self._guaranteed.is_set():
            featured_ratio = 1.0
        else:
            featured_total = sum(ctx.current.get(s, 0.0) for s in featured_slots)
            featured_ratio = featured_total / total if total > 0 else 0.0
        return _redistribute_scope(ctx, featured_ratio, total, featured_slots, self._scope)

    def after_draw(self, ctx):
        if not self._is_trigger_rarity(ctx.draw.reward_rarity, ctx):
            return
        if self._is_hit(ctx):
            self._guaranteed.clear()
        else:
            self._guaranteed.set()

    def _is_hit(self, ctx):
        return ctx.draw.is_featured

    def _is_trigger_rarity(self, rarity, ctx):
        return rarity == self._scope

    def _scope_total_prob(self, ctx):
        slots = ctx.draw.scope_slots.get(self._scope, ())
        return sum(ctx.current.get(s, 0.0) for s in slots)

    def _featured_slots(self, ctx):
        return ctx.draw.featured_slots.get(self._scope, ())

    def did_fire(self, ctx):
        # M4（2026-09-16 统一）：did_fire ≡ 本次抽卡是否让本保底回到初始状态。
        # 旧实现只判 is_featured、不含 scope 门控，会在「出非 scope 稀有度的 UP」时
        # 为真而状态并未翻转，导致 depends_on 依赖方被提前激活。
        return self._is_trigger_rarity(ctx.draw.reward_rarity, ctx) and self._is_hit(ctx)


# ── P56：SoftPityMixin —— 消除 _soft 后缀类型重复的软保底 mixin ──

class SoftPityMixin:
    """混入软保底——委托 P55 SoftStepBehavior deltas 引擎。MRO 关键：mixin 必须在继承列表首位。"""
    def _init_soft_pity(self, name, state, scope, **kwargs):
        assert hasattr(self, '_scope'), 'SoftPityMixin._init_soft_pity: 父类 __init__ 必须先于本方法调用'
        from .config_toml import _expand_soft_to_deltas  # noqa: E402
        soft_deltas = kwargs.get('soft_deltas')
        if soft_deltas:
            btype = 'soft_step'
            deltas = soft_deltas
            if isinstance(deltas, (list, tuple)) and len(deltas) == 0:
                btype = 'soft_interval'
                deltas = ((0, 0.0),)
        elif kwargs.get('soft_increment') is not None:
            btype = 'soft_additive'
            deltas = _expand_soft_to_deltas(btype, kwargs.get('soft_start', 74), kwargs.get('soft_end', 90), kwargs['soft_increment'])
        else:
            btype = 'soft_interval'
            deltas = _expand_soft_to_deltas(btype, kwargs.get('soft_start', 74), kwargs.get('soft_end', 90), None)
        self._soft_engine = SoftStepBehavior(name + '_soft', state, scope, btype, deltas)
        self._counter = Counter(state, name, "counter")
    def before_draw(self, ctx, readonly=False):
        v = self._counter.value() if readonly else self._counter.incr()
        modified = self._soft_engine._compute_probabilities(ctx, v)
        # P64 S9-2：`sim` 是 `PityContext` 的必填字段，fork 必须原样透传
        # （缺参即 TypeError；`sim` 与 `state` 同源，都是「本次调用」的载体）。
        forked = PityContext(draw=ctx.draw, current=modified, state=ctx.state,
                             sim=ctx.sim)
        return super().before_draw(forked, readonly=readonly)
    def after_draw(self, ctx):
        if ctx.draw.reward_rarity == self._scope:
                self._counter.reset()
        super().after_draw(ctx)

    def _rebind_state(self, state):
        """重绑 mixin 自身 + 委托软保底引擎（MRO 链：本 mixin 须在继承列表首位）。"""
        self._counter = Counter(state, self._name, "counter")
        self._soft_engine._rebind_state(state)
        super()._rebind_state(state)


# ── P56：RotatingSoftBehavior —— 轮换 + 软保底（mixin 版） ──

class RotatingSoftBehavior(SoftPityMixin, RotatingBehavior):
    def __init__(self, name, state, scope="ssr", **kwargs):
        RotatingBehavior.__init__(self, name, state, scope, **kwargs)
        self._init_soft_pity(name, state, scope, **kwargs)


# ── P56：RotatingCRBehavior —— 轮换保底 + 捕获明光 ──

class RotatingCRBehavior(RotatingBehavior):
    """轮换保底 + 捕获明光（Capturing Radiance）。"""
    def __init__(self, name, state, scope="ssr", cr_counter_threshold=None, cr_base_rate=None, cr_state_probs=None, **kwargs):
        super().__init__(name, state, scope, **kwargs)
        self._btype = 'rotating_cr'
        self._cr_max = cr_counter_threshold if cr_counter_threshold is not None else 3
        self._cr_base_rate = cr_base_rate if cr_base_rate is not None else 0.0
        if cr_state_probs is not None:
            self._cr_state_probs = list(cr_state_probs) if isinstance(cr_state_probs, (list, tuple)) else [0.0] * self._cr_max + [1.0]
        else:
            self._cr_state_probs = [0.0] * self._cr_max + [1.0]
        self._cr_counter = Counter(state, name, "cr_counter")
    def _rebind_state(self, state):
        self._cr_counter = Counter(state, self._name, "cr_counter")
        super()._rebind_state(state)
    def before_draw(self, ctx, readonly=False):
        if self._guaranteed.is_set():
                return super().before_draw(ctx, readonly=readonly)
        if readonly:
                return super().before_draw(ctx, readonly=readonly)
        if self._cr_base_rate > 0 and random.random() < self._cr_base_rate:
                return self._force_featured(ctx)
        idx = min(self._cr_counter.value(), len(self._cr_state_probs) - 1)
        if idx >= 0:
            state_prob = self._cr_state_probs[idx]
            if state_prob >= 1.0:
                    return self._force_featured(ctx)
            if state_prob > 0 and random.random() < state_prob:
                    return self._force_featured(ctx)
        return super().before_draw(ctx, readonly=readonly)
    def _force_featured(self, ctx):
        total = self._scope_total_prob(ctx)
        featured_slots = self._featured_slots(ctx)
        return _redistribute_scope(ctx, 1.0, total, featured_slots, self._scope)
    def after_draw(self, ctx):
        was_guaranteed = self._guaranteed.is_set()
        super().after_draw(ctx)
        if not self._is_trigger_rarity(ctx.draw.reward_rarity, ctx):
                return
        if was_guaranteed:
                return
        if ctx.draw.is_featured:
                self._cr_counter.reset()
        else:
            self._cr_counter.incr()
    # M4（2026-09-16）：did_fire 继承 RotatingBehavior 的统一实现（出 scope ∧ is_featured）。
    # 原覆写 `return ctx.draw.is_featured` 缺 scope 门控，且与父类 _is_hit 完全相同，故删除。


# ── P56：RotatingCRSoftBehavior —— 轮换 + CR + 软保底（mixin 版） ──

class RotatingCRSoftBehavior(SoftPityMixin, RotatingCRBehavior):
    def __init__(self, name, state, scope="ssr", cr_counter_threshold=None, cr_base_rate=None, cr_state_probs=None, **kwargs):
        RotatingCRBehavior.__init__(self, name, state, scope, cr_counter_threshold, cr_base_rate, cr_state_probs, **kwargs)
        self._init_soft_pity(name, state, scope, **kwargs)


# ── P56：TargetedBehavior —— 事件驱动的定向保底（定轨） ──

class TargetedBehavior(PityBehavior):
    """事件驱动的定向保底（定轨）。"""
    def __init__(self, name, state, scope="ssr", fate_threshold=None, switch_allowed=None, switch_resets_progress=None, guaranteed_init=False, fate_points_init=0, **kwargs):
        self._name = name
        self._state = state
        self._scope = scope
        self._btype = 'targeted'
        self.is_soft = False
        self.is_hard = False
        self.is_event_driven = True
        self._fate_threshold = fate_threshold if fate_threshold is not None else 1
        self._switch_allowed = switch_allowed if switch_allowed is not None else True
        self._switch_resets_progress = switch_resets_progress if switch_resets_progress is not None else True
        self._guaranteed = Flag(state, name, "guaranteed")
        self._losses = Counter(state, name, "losses")
        self._lost_flag = Flag(state, name, "lost_rotating")
        self._fate_points = Counter(state, name, "fate_points")
        if guaranteed_init:
                self._guaranteed.set()
        if fate_points_init:
                self._fate_points._state.set(name, "fate_points", fate_points_init)

    def _rebind_state(self, state):
        self._state = state
        self._guaranteed = Flag(state, self._name, "guaranteed")
        self._losses = Counter(state, self._name, "losses")
        self._lost_flag = Flag(state, self._name, "lost_rotating")
        self._fate_points = Counter(state, self._name, "fate_points")

    def _selected_card(self, ctx):
        """`selected_card` 经 `StateView` 读（P64 S9-1 / ISSUE-103，§3.10.3）。

        §3.10.3 的「三处存量迁移」：原三处 `ctx.state.get(self._name,
        "selected_card")` 改为 `StateView(ctx.state, self._name).get("selected_card")`。
        两式**逐字等价**（同名同键、缺省同为 `None`；`StateView.get` 就是
        `state.data.get(name, {}).get(key, default)`），故 S1–S5 的「逐场一致」口径
        不受影响。本迁移的唯一目的是让 `pity.py` 内的「`ctx.state` 状态键读取点」
        归零（余下 `SoftPityMixin.before_draw` 的 fork 是**构造透传**而非读取，计划
        显式豁免，§3.10.3），使「Modifier / 行为类只经 view 读状态」这条纪律可被
        静态核对。本类保留至 ISSUE-502 的「发布前一次性移除旧类」commit，本迁移
        随该 commit 一并消失。
        """
        return StateView(ctx.state, self._name).get("selected_card")

    def before_draw(self, ctx, readonly=False):
        total = self._scope_total_prob(ctx)
        if total <= 0:
                return ctx.current.copy()
        featured_slots = self._featured_slots(ctx)
        if not featured_slots:
                return ctx.current.copy()
        selected = self._selected_card(ctx)
        if self._guaranteed.is_set() or (selected and self._fate_points.value() >= self._fate_threshold):
            featured_ratio = 1.0
            targeted_slots = self._resolve_selected_slots(selected, featured_slots, ctx)
            return _redistribute_scope(ctx, featured_ratio, total, targeted_slots, self._scope)
        else:
            featured_total = sum(ctx.current.get(s, 0.0) for s in featured_slots)
            featured_ratio = featured_total / total if total > 0 else 0.0
            return _redistribute_scope(ctx, featured_ratio, total, featured_slots, self._scope)
    def after_draw(self, ctx):
        if not self._is_trigger_rarity(ctx.draw.reward_rarity, ctx):
                return
        selected = self._selected_card(ctx)
        if selected is None:
                return
        if self._is_hit(ctx):
            self._fate_points.reset()
            self._guaranteed.clear()
            self._lost_flag.clear()
            self._losses.reset()
            return
        self._fate_points.incr()
        self._guaranteed.set()
        self._lost_flag.set()
        self._losses.incr()
    def _is_hit(self, ctx):
        selected = self._selected_card(ctx)
        if selected is None:
                return False
        return ctx.draw.reward_id == selected
    def _resolve_selected_slots(self, selected, featured_slots, ctx):
        if selected is None:
                return featured_slots
        card_to_slot = getattr(ctx.draw, 'card_to_slot', None) or {}
        target_slot = card_to_slot.get(selected)
        if target_slot and target_slot in featured_slots:
                return (target_slot,)
        for slot in featured_slots:
            rarity_key = slot.replace('_featured', '') if slot.endswith('_featured') else slot
            cards = ctx.draw.scope_cards.get(rarity_key, ())
            if selected in cards:
                    return (slot,)
        return featured_slots
    def _is_trigger_rarity(self, rarity, ctx): return rarity == self._scope
    def _scope_total_prob(self, ctx):
        slots = ctx.draw.scope_slots.get(self._scope, ())
        return sum(ctx.current.get(s, 0.0) for s in slots)
    def _featured_slots(self, ctx): return ctx.draw.featured_slots.get(self._scope, ())
    def did_fire(self, ctx):
        # M4（2026-09-16 统一）：同 RotatingBehavior，需出 scope 稀有度且命中定轨卡。
        return self._is_trigger_rarity(ctx.draw.reward_rarity, ctx) and self._is_hit(ctx)


# ── P56：TargetedSoftBehavior —— 定轨 + 软保底（mixin 版） ──

class TargetedSoftBehavior(SoftPityMixin, TargetedBehavior):
    def __init__(self, name, state, scope="ssr", fate_threshold=None, switch_allowed=None, switch_resets_progress=None, **kwargs):
        TargetedBehavior.__init__(self, name, state, scope, fate_threshold, switch_allowed, switch_resets_progress, **kwargs)
        self._init_soft_pity(name, state, scope, **kwargs)


# ══════════════════════════════════════════════════════════════════
# P64 S4-2 / S4-3：preset 工厂（§3.2）
#   `preset(pdef) -> dict`（ISSUE-030 签名定稿），键集恰为
#   `trackers` / `modifiers` / `lifecycle`（必需）+ `flags` / `counters`（可选），
#   消费者是 `create_behavior` 的 preset 分支与 `Pity.__init__` 的
#   `flags` / `counters` 形参（AUDIT-BREAK-3）。
#
#   **必须是工厂函数、不是模块级常量实例（ISSUE-005）**：模块级赋值会把
#   Tracker / Modifier 实例化在模块命名空间里，`create_behavior` 每次拿回的是
#   同一批对象，同进程内所有用该 preset 的保底共享同一批 Counter/Flag 遥控器，
#   `_rebind_state` 会把它们重绑到最后调度的保底，串扰既跨保底又跨模拟。
#
#   逐条可配字段一律取自 `pdef`（取值来源表见 §3.2），**不得写成常量**：
#   否则 M1 的「与旧类逐场一致」只在默认配置下成立，任何非默认
#   `threshold` / `scope` / `counter_init` / `guaranteed_init` / `deltas`
#   都会静默退回常量值。
#
#   四个取值 helper（`build_lifecycle` / `_norm_scope` / `_target_of` /
#   `_soft_deltas_of`）已随 S1d / S4-2 定义于本模块上方，**10 个工厂共用**，
#   不得另起第二份取值逻辑。
# ══════════════════════════════════════════════════════════════════

def _preset_soft_step(pdef):
    """counter 驱动三软类型（`soft_step` / `soft_interval` / `soft_additive`）共用的 preset。

    三者的差异**只在 deltas 的来路**（`soft_step` 直写 `deltas`，`soft_interval` /
    `soft_additive` 写语法糖），由 `_soft_deltas_of(pdef)` 三分支归一（ISSUE-001），
    故 §3.2 的 preset 映射表把三行并作一行、共用本工厂。
    """
    deltas = _soft_deltas_of(pdef)                                     # M6（ISSUE-001）
    return dict(
        lifecycle=build_lifecycle(pdef),                               # ISSUE-301
        trackers=[CounterTracker(scope=_norm_scope(pdef),
                                 reset_on=pdef.reset or _norm_scope(pdef),
                                 init=pdef.counter_init)],
        modifiers=[
            # 裁决 7B：soft 不消费 target_featured（该形态经 create_behavior 抛
            # ConfigError），故本工厂**不写 `target=`**；Q 若写成 scope 内部，soft
            # 整体不生效（§3.1.5.2.4 错误 ②）。
            SoftModifier(_norm_scope(pdef), deltas=deltas),            # deltas 经 _soft_deltas_of(pdef)
        ],
        counters={"counter": pdef.counter_init},
    )


def _preset_hard(pdef):
    """硬保底 preset，`counter >= τ` 时目标集概率强制 100%（F 语义）。"""
    _scope = _norm_scope(pdef)
    tau = pdef.threshold if pdef.threshold is not None else 90
    return dict(
        lifecycle=build_lifecycle(pdef),                               # ISSUE-301
        trackers=[CounterTracker(scope=_scope, reset_on=pdef.reset or _scope,
                                 init=pdef.counter_init)],
        modifiers=[
            # ISSUE-403：target_featured 由本类自己的 apply() 消费；本类型是它的
            # 唯一合法消费者（soft 侧已按裁决 7B 移出）。漏写 `target=` 不报错，
            # `HardModifier` 的 `target` 默认 `'scope'`，`target_featured=True` 的
            # 配置会把目标集由 featured 卡集静默放宽为 scope 全集。
            HardModifier(_scope, threshold=tau, target=_target_of(pdef)),
        ],
        counters={"counter": pdef.counter_init},
    )


# ── P64 S4-3：事件驱动 preset 工厂（6 类，§3.2 映射表 / §3.10.3 配套 1）──
#
# 六类共用三条纪律，缺一则语义漂移或静默失效：
#
# ① **一律不写 `target=`**（ISSUE-403 / 裁决 7B）：旧实现忽略本族的
#    `target_featured`（`RotatingBehavior.__init__` 收进 `**kwargs` 后丢弃；
#    三个 `_soft` 变体内层也未传该值），故把 `_preset_hard` 的 `_target_of(pdef)`
#    照抄到本族即为语义漂移。
# ② **三个 `_soft` 类型的命名空间载体（ISSUE-407，强制）**：`rotating_soft` /
#    `rotating_cr_soft` / `targeted_soft` 的 preset **必须**含
#    `NamespaceTracker(namespace=f'{pdef.name}_soft')`。缺它则 `X_soft` 命名空间
#    不存在、`Lifecycle.initialize` 的推广写入无处落，且 `PityState.to_dict()`
#    与旧实现的快照口径不再一致（旧内层 `SoftStepBehavior(name + '_soft', …)`
#    在该空间留下 `{_active: True}`，ISSUE-023）。
# ③ **Modifier 顺序 = 旧 mixin 的相位顺序**：`SoftPityMixin.before_draw` 先把
#    soft 结果算成 `modified` 再交给父类，故三个 `_soft` 类型的 `modifiers` 一律
#    `SoftModifier` 在前、母类型 Modifier 在后。

def _preset_rotating(pdef):
    """轮换保底（大小保底）preset——`guaranteed` 时把 scope 内非 featured 的概率整组搬给 featured。

    对齐旧 `RotatingBehavior`：出 scope 稀有度且 featured → 清 `guaranteed`（大保底
    已用掉），未命中 → 置位（下一次必出 UP）。标记初值走状态声明（H2），不加
    Tracker 形参（同 `_preset_hard` 的 `counters` 口径）。
    """
    _scope = _norm_scope(pdef)
    return dict(
        lifecycle=build_lifecycle(pdef),                               # ISSUE-301
        trackers=[FlagTracker(scope=_scope, judge="featured",
                              hit="clear", miss="set", flag="guaranteed")],
        modifiers=[RotatingModifier(_scope)],
        flags={"guaranteed": pdef.guaranteed_init},
    )


def _preset_rotating_cr(pdef):
    """轮换保底 + 捕获明光——`rotating` 之上加「连续未命中 → 抽前随机拦截」。

    **Tracker 顺序是契约（强制，RULING-6B′）**：`StreakTracker` 必须排在
    `FlagTracker` **之前**，`commit` 列表顺序即语义的一部分。`StreakTracker.commit`
    的归零条件含「抽前 `guaranteed` 未置位」一项，而该值由同抽 `FlagTracker.commit`
    尚未翻转的状态给出；顺序对调则两处读点取到同一个（抽后的）值，守卫语义反转、
    **`cr_counter` 恒为 0**（§3.1.1「Tracker 顺序是契约」条，`_preset_rotating_cr`
    的 docstring 记有实测轨迹）。
    """
    _scope = _norm_scope(pdef)
    return dict(
        lifecycle=build_lifecycle(pdef),                               # ISSUE-301
        trackers=[
            # ← 顺序是契约：必须在 FlagTracker 之前（RULING-6B′ / §3.2 该行）
            StreakTracker(scope=_scope, judge="featured",
                          threshold=pdef.cr_counter_threshold,
                          base_rate=pdef.cr_base_rate,
                          state_probs=pdef.cr_state_probs,
                          flag="cr_intercepted",
                          guard_flag="guaranteed"),
            FlagTracker(scope=_scope, judge="featured",
                        hit="clear", miss="set", flag="guaranteed"),
        ],
        # `extra_flag` 表达「条件多一个 `cr_intercepted`」（§3.2 的构造形参口径）：
        # `rotating_cr` 与 `rotating` 的效果相同，差别只在触发条件。
        modifiers=[RotatingModifier(_scope, extra_flag="cr_intercepted")],
        flags={"guaranteed": pdef.guaranteed_init},
    )


def _preset_rotating_soft(pdef):
    """轮换保底 + 软保底——`rotating` 的 Tracker 加软计数与 `X_soft` 命名空间载体。

    | 项 | 依 §3.10.3 配套 1 的定稿 |
    |----|--------------------------|
    | 软计数落点 | **默认 view（`X` 命名空间）**，对齐旧 mixin 的 `X.counter` |
    | `X_soft` 命名空间 | 只含 `_active`，产出者是 `NamespaceTracker`；`_active` 由 `Lifecycle.initialize` 的推广作用域写入 |
    | Tracker 顺序 | `FlagTracker` → `CounterTracker` → `NamespaceTracker`（三者写不同键，无顺序契约） |
    """
    _scope = _norm_scope(pdef)
    deltas = _soft_deltas_of(pdef)                                     # M6（ISSUE-001）
    return dict(
        lifecycle=build_lifecycle(pdef),                               # ISSUE-301
        trackers=[
            FlagTracker(scope=_scope, judge="featured",
                        hit="clear", miss="set", flag="guaranteed"),
            CounterTracker(scope=_scope, reset_on=_scope,
                           init=pdef.counter_init),
            # ISSUE-407：`X_soft` 命名空间的**唯一产出者**（缺它则 `Lifecycle.
            # initialize` 的推广写入无处落）
            NamespaceTracker(namespace=f'{pdef.name}_soft'),
        ],
        # 顺序同旧 mixin：soft 先算，母类型 Modifier 接收 soft 后的分布
        modifiers=[SoftModifier(_scope, deltas=deltas),                # deltas 经 _soft_deltas_of(pdef)
                   RotatingModifier(_scope)],
        flags={"guaranteed": pdef.guaranteed_init},
        counters={"counter": pdef.counter_init},
    )


def _preset_rotating_cr_soft(pdef):
    """轮换保底 + 捕获明光 + 软保底——`_preset_rotating_cr` 的 Tracker 加软计数与载体。

    `StreakTracker` 仍排在 `FlagTracker` 之前（顺序契约同 `_preset_rotating_cr`）；
    软计数与命名空间载体写的是另一批键（`counter` / `X_soft._active`），排在两者
    之后不影响该契约。`modifiers` 顺序同 `_preset_rotating_soft`。
    """
    _scope = _norm_scope(pdef)
    deltas = _soft_deltas_of(pdef)                                     # M6（ISSUE-001）
    return dict(
        lifecycle=build_lifecycle(pdef),                               # ISSUE-301
        trackers=[
            # ← 顺序是契约：必须在 FlagTracker 之前（RULING-6B′ / §3.2 该行）
            StreakTracker(scope=_scope, judge="featured",
                          threshold=pdef.cr_counter_threshold,
                          base_rate=pdef.cr_base_rate,
                          state_probs=pdef.cr_state_probs,
                          flag="cr_intercepted",
                          guard_flag="guaranteed"),
            FlagTracker(scope=_scope, judge="featured",
                        hit="clear", miss="set", flag="guaranteed"),
            CounterTracker(scope=_scope, reset_on=_scope,
                           init=pdef.counter_init),
            NamespaceTracker(namespace=f'{pdef.name}_soft'),           # ISSUE-407
        ],
        modifiers=[SoftModifier(_scope, deltas=deltas),
                   RotatingModifier(_scope, extra_flag="cr_intercepted")],
        flags={"guaranteed": pdef.guaranteed_init},
        counters={"counter": pdef.counter_init},
    )


def _preset_targeted(pdef):
    """定向保底（定轨）preset——`guaranteed` 或「已定轨 ∧ 命定值达阈值」时必出定轨卡。

    | 形参 | 取值来源（§3.2 取值来源表） |
    |------|------------------------------|
    | `FateTracker` 的 `keys` | 机制语义固定（四个键的写面：`fate_points` / `losses` / `guaranteed` / `lost_rotating`） |
    | `SelectedModifier` 的 `tau` | `pdef.fate_threshold`，`None` 回退 **1**（对齐旧 `TargetedBehavior.__init__` 的 `fate_threshold if fate_threshold is not None else 1`，S2a-2 补登行） |

    `switch_allowed` / `switch_resets_progress` **不进本 preset**：它们是 GachaService
    策略层（`NonDrawAction`）的判定输入，由 `pity_engine.get_pity_def()` 直读
    `PityDef`，旧类只是把它们存下后从未消费（§3.7 范围边界条）。
    """
    _scope = _norm_scope(pdef)
    tau = pdef.fate_threshold if pdef.fate_threshold is not None else 1
    return dict(
        lifecycle=build_lifecycle(pdef),                               # ISSUE-301
        trackers=[FateTracker(scope=_scope, judge="selected",
                              hit="clear", miss="accumulate",
                              keys=("fate_points", "losses",
                                    "guaranteed", "lost_rotating"))],
        modifiers=[SelectedModifier(_scope, tau=tau)],
        # 两个初值各按 truthy 规则写（对齐 `_build_pity_state_init` 的 `if v:`）：
        # `guaranteed_init` 走 flags、`fate_points_init` 走 counters，与旧
        # `TargetedBehavior.__init__` 的两处条件写入同源。
        flags={"guaranteed": pdef.guaranteed_init},
        counters={"fate_points": pdef.fate_points_init},
    )


def _preset_targeted_soft(pdef):
    """定向保底（定轨）+ 软保底——`_preset_targeted` 的 Tracker 加软计数与载体。

    两个计数同命名空间但不同键：软计数是 `counter`（旧 mixin 的 `X.counter`），
    命定值是 `fate_points`。`modifiers` 顺序同其余两个 `_soft` 类型。
    """
    _scope = _norm_scope(pdef)
    tau = pdef.fate_threshold if pdef.fate_threshold is not None else 1
    deltas = _soft_deltas_of(pdef)                                     # M6（ISSUE-001）
    return dict(
        lifecycle=build_lifecycle(pdef),                               # ISSUE-301
        trackers=[
            FateTracker(scope=_scope, judge="selected",
                        hit="clear", miss="accumulate",
                        keys=("fate_points", "losses",
                              "guaranteed", "lost_rotating")),
            CounterTracker(scope=_scope, reset_on=_scope,
                           init=pdef.counter_init),
            NamespaceTracker(namespace=f'{pdef.name}_soft'),           # ISSUE-407
        ],
        modifiers=[SoftModifier(_scope, deltas=deltas),
                   SelectedModifier(_scope, tau=tau)],
        flags={"guaranteed": pdef.guaranteed_init},
        counters={"counter": pdef.counter_init,
                  "fate_points": pdef.fate_points_init},
    )



# ── P64 S6a：G1 反向轮换 preset（1 类，§3.3）──
#
# 本类是**新增机制**（旧实现无对应类），故不进等价性装置的比对面（§3.3 首段：
# G1 为独立 type，无旧类可对拍）；其验收面是 §六 的语义断言
# 「出 UP → 下一次 SSR 必非 UP；出非 UP → 恢复基础比例」与三条类型注册断言。

def _preset_rotating_inverse(pdef):
    """反向轮换保底（G1，幻塔「连中必歪」）——出 UP 后下一次 SSR 必非 UP。

    与 `_preset_rotating` 是**对偶**：`RotatingModifier` 把非 featured 的概率搬给
    featured，本类经 `NonFeaturedModifier` 反向搬运（A / Q 互换，见 §3.1.2 机制表
    第 5 行）。条件同样内联在 Modifier 的 `apply` 开头，标志为 `forced_loss`。

    三条与母类型一致的纪律（同 §3.2 事件驱动族）：

    ① **不写 `target=`**（ISSUE-403 / 裁决 7B）：本族一律不消费 `PityDef.target_featured`。
    ② **`flags` 的 `forced_loss` 初值恒 `False`，且该行按 truthy 规则是 no-op**
       （AUDIT-BREAK-3：`Pity.__init__` 仅写入 truthy 值）。保留它是为了记明
       「本键的初值不由任何 `PityDef` 字段供给」，与 `_preset_rotating` 的
       `guaranteed_init` 形成对照；缺键与 `False` 在读取侧同值（`view.get` 落 None）。
    ③ **无 `NamespaceTracker`**：本类不是 `_soft` 后缀型，不声明 `X_soft` 命名空间。
    """
    _scope = _norm_scope(pdef)
    return dict(
        lifecycle=build_lifecycle(pdef),                               # ISSUE-301
        trackers=[FlagTracker(scope=_scope, judge="featured",
                              hit="set", miss="clear", flag="forced_loss")],
        modifiers=[NonFeaturedModifier(_scope)],
        flags={"forced_loss": False},
    )

# ── P60 新增 → P55 更新：保底类型注册表（对齐 STRATEGY_REGISTRY） ──

BEHAVIOR_REGISTRY: Dict[str, dict] = {
    # ══ P55：counter 驱动型（4 种） ══
    # ── P64 S4-2：本组四条已 preset 化 ──
    # `class` 置 `None` 与 `preset` 赋值**按条目原子地**完成（GATE-3 定稿）：
    # 条目既无 `preset` 又无 `class` 时导入期的 `_validate_registry()` 即失败，
    # 故两者不得跨 commit 拆开（§3.2 首段 / §七 S4-1 的落地时序）。
    # `params` / `ui_params` 保留，它们是 GUI 控件声明面，与本键集契约无关
    # （`_PITY_TYPE_KEYS` 才是 TOML 键契约，S4c）。
    "soft_interval": {
        "class": None,
        "preset": _preset_soft_step,
        "display_name": "区间软保底",
        "default_scope": "ssr",
        "params": {
            "start": {"type": "int", "display_name": "起始抽数", "default": 80, "min": 1},
            "end":   {"type": "int", "display_name": "结束抽数", "default": 90, "min": 1},
            "func":  {"type": "str", "display_name": "爬升函数", "default": "linear",
                       "options": ["linear"]},
        },
        "ui_params": ["start", "end"],
    },
    "soft_additive": {
        "class": None,
        "preset": _preset_soft_step,
        "display_name": "累加软保底",
        "default_scope": "ssr",
        "params": {
            "start":     {"type": "int",   "display_name": "起始抽数",   "default": 74,  "min": 1},
            "increment": {"type": "float", "display_name": "每抽增量(%)", "default": 6.0, "min": 0.1},
        },
        "ui_params": ["start", "increment"],
    },
    "soft_step": {
        "class": None,
        "preset": _preset_soft_step,
        "display_name": "分段软保底",
        "default_scope": "ssr",
        "params": {
            "deltas": {"type": "deltas", "display_name": "RLE 分段表", "default": ((73, 0.0), (17, 5.88))},
        },
        "ui_params": ["deltas"],
    },
    "hard": {
        "class": None,
        "preset": _preset_hard,
        "display_name": "硬保底",
        "default_scope": "ssr",
        "params": {
            "threshold": {"type": "int", "display_name": "保底抽数", "default": 90, "min": 1},
        },
        "ui_params": ["threshold"],
    },
    # ══ P56：事件驱动型（6 种）+ P64 S6a 的 G1（1 种） ══
    # ── P64 S4-3：P56 六条已 preset 化（与 S4-2 的四条同形态、同原子性纪律：
    #    `class` 置 `None` 与 `preset` 赋值必须同一条目内同时成立）──
    #
    # **书写顺序 = GUI 下拉顺序（S6a，ISSUE-929）**：本字典是字面量（Python 3.7+
    # 保序），GUI 的 `_PITY_TYPES` 自 S6a 起由它生成，故顺序在此处即用户可见顺序。
    # 顺序本身**无引擎语义**（`_resolve_order` 走 `_BTYPE_ORDER`，与字典序无关），
    # 仅 `_validate_registry` 自检与 `create_behavior` 按键查表消费本字典。
    "rotating": {
        "class": None,
        "preset": _preset_rotating,
        "display_name": "轮换保底",
        "default_scope": "ssr",
        "params": {},
    },
    # ── P64 S6a：G1 反向轮换（§3.3）──
    # `params` 为空：本类型无类型专用 `PityDef` 字段（`forced_loss` 是 preset 内部
    # 标志，无对应初值字段）。故 `_PITY_TYPE_KEYS` 的键集同 `rotating`（仅通用键）。
    "rotating_inverse": {
        "class": None,
        "preset": _preset_rotating_inverse,
        "display_name": "反向轮换保底（连中必歪）",
        "default_scope": "ssr",
        "params": {},
    },
    "rotating_soft": {
        "class": None,
        "preset": _preset_rotating_soft,
        "display_name": "轮换+软保底",
        "default_scope": "ssr",
        "params": {
            "start":     {"type": "int",   "display_name": "起始抽数",   "default": 74,  "min": 1},
            "increment": {"type": "float", "display_name": "每抽增量(%)", "default": 6.0, "min": 0.1},
        },
    },
    "rotating_cr": {
        "class": None,
        "preset": _preset_rotating_cr,
        "display_name": "轮换+捕获明光",
        "default_scope": "ssr",
        "params": {
            "cr_counter_threshold": {"type": "int",   "display_name": "CR 计数器阈值", "default": 3,  "min": 1},
            "cr_base_rate":         {"type": "float", "display_name": "基础递增率(%)",  "default": 5.0, "min": 0.0},
        },
    },
    "rotating_cr_soft": {
        "class": None,
        "preset": _preset_rotating_cr_soft,
        "display_name": "轮换+捕获明光+软保底",
        "default_scope": "ssr",
        "params": {
            "cr_counter_threshold": {"type": "int",   "display_name": "CR 计数器阈值", "default": 3,  "min": 1},
            "cr_base_rate":         {"type": "float", "display_name": "基础递增率(%)",  "default": 5.0, "min": 0.0},
            "start":                {"type": "int",   "display_name": "起始抽数",      "default": 50, "min": 1},
            "increment":            {"type": "float", "display_name": "每抽增量(%)",    "default": 5.0, "min": 0.1},
        },
    },
    "targeted": {
        "class": None,
        "preset": _preset_targeted,
        "display_name": "定轨保底",
        "default_scope": "ssr",
        "params": {
            "fate_threshold":         {"type": "int",   "display_name": "命定值阈值",     "default": 1,    "min": 0},
            "switch_allowed":         {"type": "bool",  "display_name": "允许中途切换",   "default": True},
            "switch_resets_progress": {"type": "bool",  "display_name": "切换后清零进度", "default": True},
        },
    },
    "targeted_soft": {
        "class": None,
        "preset": _preset_targeted_soft,
        "display_name": "定轨+软保底",
        "default_scope": "ssr",
        "params": {
            "fate_threshold":         {"type": "int",   "display_name": "命定值阈值",     "default": 2,    "min": 0},
            "switch_allowed":         {"type": "bool",  "display_name": "允许中途切换",   "default": True},
            "switch_resets_progress": {"type": "bool",  "display_name": "切换后清零进度", "default": True},
            "start":                  {"type": "int",   "display_name": "起始抽数",      "default": 50, "min": 1},
            "increment":              {"type": "float", "display_name": "每抽增量(%)",    "default": 5.0, "min": 0.1},
        },
    },
}


def _validate_registry():
    """BEHAVIOR_REGISTRY 自检：**每条目一律判 `preset` 可调用**（GATE-3 收口定稿）。

    **P64 S4-3 收口（GATE-3）**：S4-1 的过渡判据（「条目含 `preset` 键则判其可调用；
    无 `preset` 键则沿用旧判据 `PityBehavior` 子类」）已删除——S4-2 / S4-3 落地后
    10 条目一律为 `class: None` + 可调用 `preset`，旧判据的对象已不存在。
    `ISSUE-015` 的「`class` 一律置 `None`」在本步终局达成（其断言在
    `tests/core/test_pity_registry_schema.py` 的 S4-3 段）。

    导入期仍**只做 `callable()` 判定**，**既不调用 preset、也不校验其返回键集**
    （ISSUE-405）：① 本函数形参表为空，手上**没有 `PityDef` 实例**可传给
    `preset(pdef)`；② 导入期真调用会把 preset 体内的运行期错误（Modifier 构造签名
    不符致 `TypeError`）从「`PityEngine` 构造期可见」升级为**整包
    `import gacha_simulator.core` 失败**。preset 返回 dict 的键集校验（未知键查多 /
    `lifecycle` 必需键查漏）一律在**运行期**由 `create_behavior` 承担
    （§3.2 AUDIT-BREAK-3）。

    **缺 `preset` 键**（或值不可调用）即抛——`.get()` 而非 `[]`：手工构造的畸形条目
    （无该键）与显式置 `None` 的条目在本判据下等价，报错形态唯一。

    在模块导入时自动执行一次——类型错误在导入阶段立即暴露。
    """
    for btype, entry in BEHAVIOR_REGISTRY.items():
        preset = entry.get("preset")
        if not callable(preset):
            raise TypeError(
                f"BEHAVIOR_REGISTRY['{btype}'].preset={preset!r}: "
                f"必须为可调用的 preset 工厂函数"
            )


_validate_registry()


# ══════════════════════════════════════════════════════════════════
# P64 S3-1：StateView 薄版（§3.10.3）+ 统一 Pity 骨架（§3.1.4）
# ══════════════════════════════════════════════════════════════════

class StateView:
    """限定在单个保底命名空间内的只读视图（§3.10.3；**S3 落薄版 / S9 收紧**）。

    **不得在构造期缓存命名空间 dict**（ISSUE-004）：`PityState.data` 是惰性创建的
    ——构造期 `data.get(name, {})` 若该命名空间尚不存在（`depends_on` 依赖方在构造
    期不写 `_active`），会拿到一个与 state 脱联的空 dict，此后引擎 `state.set` 新建
    的命名空间与该 view 无关，所有读取恒返回 default 且不报错。故 `get()` 每次现取；
    配合 `Pity._rebind_state` 重建 view（§3.1.4），worker 内同一 engine 连跑 N 场
    模拟时每场读到的都是当场的账本。

    **S9-1（2026-10-14）事实确认**：本薄版**已是 S9 定稿的可读面**——`get` 只取
    `data[self._name]`，读他人命名空间的键自始返回 `default`（跨保底读在架构上
    关闭）。故原稿「S9 才切断 `name` 之外的读取、收紧只改可读面、不改签名」与代码
    事实不符：本类本体在 S9-1 **无代码增量**，S9-1 的实质是「`view` 形参确为本类」
    的接线确认、`ctx.state` 通道的存量读取迁移（§3.10.3 的三处）与验收面。
    """

    def __init__(self, state: 'PityState', name: str):
        self._state = state
        self._name = name

    def get(self, key, default=None):
        return self._state.data.get(self._name, {}).get(key, default)


class Pity(PityBehavior):
    """统一保底骨架（§3.1.4）——Tracker + Modifier + Lifecycle 三元组。

    **不继承 `CounterBasedBehavior`**：三个分类标志由 `btype` 自行推导（ISSUE-001），
    故 `_SOFT_TYPES` / `_HARD_TYPES` / `_EVENT_DRIVEN_TYPES` 走 `pity_primitives`
    的模块级常量裸名引用（ISSUE-024）。写死 `is_event_driven` 会让
    `_validate_behaviors` 的规则 2/3/4 全部落到「事件驱动型」分支——soft 组合由
    「通过」变 `ConfigError`、`rotating` + `hard` 同 scope 被拒、规则 2 静默失效。

    构造期顺序（**不可颠倒**，ISSUE-202 / ISSUE-407）：

    1. 收集零件声明的命名空间（`trackers` / `modifiers` / `lifecycle` 的 `namespace`
       属性去 `None`）；
    2. 汇总三族声明键集 `_declared_keys`（S10-2 / S11 的唯一输入）并跑 S10-2 的
       两条构造期判据（§3.12.2，非法组合抛 `ConfigError`，先于任何 state 写入）；
    3. `Lifecycle.initialize(state, name, namespaces)`——写初始 `_active`。**须先于
       `_view` 创建**：`initialize` 只写 state、不依赖 view；
    4. 建默认 view（`self._name`）与零件命名空间 view（`self._ns_views`）；
    5. 按 truthy 规则消费 `flags` / `counters`（AUDIT-BREAK-3）；写入点须在
       `initialize` 之后——`_active` 归 Lifecycle，不在此列。

    本块（S3-1）只要求骨架**可独立构造并验收**；接入 `PityEngine` / preset 是 S4 的事。
    """

    def __init__(self, *, name, state, scope, btype,
                 trackers: List[Tracker],
                 modifiers: List[Modifier],
                 lifecycle: Lifecycle = AlwaysActive(),
                 priority: int = 0,
                 pools: tuple = ('*',),
                 flags: Optional[dict] = None,
                 counters: Optional[dict] = None):
        self._name = name
        self._state = state
        # `scope` 必须是**已归一化的小写值**（ISSUE-503）——归一化由 `create_behavior`
        # / preset 侧完成，本骨架**不做二次归一化**（否则 `Pity._scope` 与零件
        # `_scope` 会再次分叉）。
        self._scope = scope
        self._btype = btype
        self._priority = priority
        # ISSUE-019：`_pools` 由 `PityDef.pools` 注入，`PityEngine._build_activation_graph`
        # 的池交集校验据此恢复语义（§3.12.2）——S1a 至 S2a-2 期间该警告对每条
        # `depends_on` 恒真触发，属已登记的过渡态。
        self._pools = pools
        self._trackers = trackers
        self._modifiers = modifiers
        self._lifecycle = lifecycle

        # ISSUE-001：三个分类标志由 btype 推导，与 CounterBasedBehavior.__init__ 同源。
        self.is_soft = btype in _SOFT_TYPES
        self.is_hard = btype in _HARD_TYPES
        self.is_event_driven = btype in _EVENT_DRIVEN_TYPES

        # ISSUE-407：先收集零件声明的命名空间（去 None），再调 initialize——
        # Lifecycle 需要知道「本保底声明了哪些命名空间」才能把 `_active` 写进 `X_soft`。
        self._namespaces = tuple(sorted(
            {getattr(_p, 'namespace', None)
             for _p in (*trackers, *modifiers, lifecycle)} - {None}))

        # ISSUE-501：三族声明键集的**汇总点**（S10-2 的两条构造期判据与 S11 状态层
        # checker 的唯一输入）。三族一律暴露只读成员 `state_keys()`（由构造形参决定、
        # 不依赖 state），故此处无守卫直调；缺该方法即首次构造 `AttributeError`。
        # 三者分开存，因为判据口径不同：判据 1 查 `'trackers'` 内的重复，判据 2 以
        # `trackers ∪ lifecycle` 为「存在」的并集（`'modifiers'` 只作被查方）。
        self._declared_keys = {
            'trackers': tuple(k for _p in trackers for k in _p.state_keys()),
            'modifiers': tuple(k for _p in modifiers for k in _p.state_keys()),
            'lifecycle': tuple(lifecycle.state_keys()),
        }

        # S10-2（§3.12.2）：两条合法组合判据的**检查点**。数据是 per-Pity 的
        # （`_declared_keys` 由本保底三族给出），无需引擎上下文，故落在本构造器。
        # 位置须在 `Lifecycle.initialize` **之前**：非法组合在此抛 `ConfigError`，
        # 不留半写的 state（`initialize` 与 `flags` / `counters` 消费都会写 state）。
        _check_declared_keys(self._declared_keys, name)

        # P64 S9-2（§3.10.2）：`uses_sim` 注解的构造期校验：与上一条同层、同在
        # 任何 state 写入之前。注解不参与门控，故这里只查名字是否在已知源集合内。
        _check_uses_sim(modifiers, name)

        # ISSUE-202 / ISSUE-407：构造期写入初始 `_active` 的**唯一归属方法**。漏掉即
        # 非 `depends_on` 保底 `_active` 恒 False、`before_draw` / `after_draw` 首行
        # 双双早退，全部计数型保底静默失效。
        self._lifecycle.initialize(state, name, self._namespaces)

        # ISSUE-004：默认 view——随 state 重建，见 `_rebind_state`。
        self._view = StateView(state, name)
        # ISSUE-407：零件命名空间 view（keyed by namespace）。调用零件时经
        # `self._view_for(part)` 取值，**不得写死 `self._view`**，否则 `X_soft` 的
        # 读取全落默认命名空间。
        self._ns_views = {_ns: StateView(state, _ns) for _ns in self._namespaces}

        # AUDIT-BREAK-3：preset 返回 dict 的 `flags` / `counters` 两键的消费者。
        # 写入规则与 §3.1.1 的 L4 键集语义一致——**仅 truthy 才预建键**（对齐
        # `_build_pity_state_init` 的 `if cv:`），故与引擎侧的 `env.pity_state_init`
        # 快照幂等同值，不引入第二套初值口径。
        for _k, _v in (flags or {}).items():
            if _v:
                state.set(name, _k, _v)
        for _k, _v in (counters or {}).items():
            if _v:
                state.set(name, _k, _v)

    # ── P75：`_rebind_state`——三族统一实现 ──

    def _rebind_state(self, state: 'PityState') -> None:
        """把三族的 Counter / Flag / view 全部重绑到 per-call `state`（纯重定向）。

        `PityEngine._rebind_state` 经 `hasattr(bh, '_rebind_state')` 对其**无守卫**
        调用（P75 纪律），故本方法必须存在且覆盖三族：Tracker / Modifier 两族
        `rebind(state, name)` 两实参；Lifecycle `rebind(state, name, namespaces)`
        **三实参**（ISSUE-917：与 `initialize` 实参面对称，漏传即 `X_soft` 的
        `_active` Flag 跨场不重绑、仍指上一场 state）。
        """
        self._state = state
        for tr in self._trackers:
            tr.rebind(state, self._name)
        for mod in self._modifiers:
            mod.rebind(state, self._name)
        self._lifecycle.rebind(state, self._name, self._namespaces)
        # ISSUE-004：view 必须随 state 重建。worker 内同一 engine 被 N 次模拟复用，
        # 跨模拟隔离唯一靠 rebind；view 若只在构造期建一次，第 2..N 场读的仍是旧账本。
        self._view = StateView(state, self._name)
        # ISSUE-407：零件命名空间 view **同批重建**（否则与 ISSUE-004 同一失效模式）。
        self._ns_views = {_ns: StateView(state, _ns) for _ns in self._namespaces}

    def _view_for(self, part):
        """零件级 view 取值（ISSUE-407）：声明了 `namespace` 的零件拿它自己的 view，
        其余拿默认 view。**遍历 `trackers` / `modifiers` 时一律经本方法，不得写死
        `self._view`。**

        注意：Tracker 的 `advance` / `prepare` / `commit` / `did_reset` 形参是**原始
        `state`**（§3.1.1 协议表），故本方法只用于 Modifier 的 `view` 形参。
        """
        return self._ns_views.get(getattr(part, 'namespace', None)) or self._view

    # ── N1 相位：before_draw ──

    def before_draw(self, ctx: 'PityContext', readonly: bool = False) -> Dict[str, float]:
        """`is_active` 早退 → `advance` 循环 → **`prepare` 循环** → Modifier 链。

        `prepare` 相位（2026-10-10，裁决 6B′）位于 `advance` 之后、本保底 Modifier
        链**之前**，**并透传 `readonly`**：`StreakTracker` 在此掷骰，`readonly=True`
        时早退不掷——策略层每次概率查询都会经 `PityEngine.before_draw` 走到本相位，
        漏透传即每次查询都掷骰、全局随机流整体错位（§3.1.1 的 N1 相位表）。

        **Modifier 链是卡级增量管道（S8，D20 + §3.9.2）**：`ctx.current` 与各
        `compute_delta()` 的 A / Q 两列同为卡级键空间；每个 Modifier 在前一个的输出上
        操作，非短路，`_apply_delta` 逐项归一化。

        **只读查询标记（§3.9.6 的「处置（两期）②」，M2 落实）**：本方法是 `readonly`
        实参的唯一入口，故在首行把它写进 `ctx.readonly`（**先于 `is_active` 早退**：
        早退路径不跑 Modifier，但把标记写全可免去「有的分支写了、有的没写」两套
        语义）。`PityEngine.get_probabilities` 以 `readonly=True` 走本方法，Modifier
        据此复刻「查询不体现 CR 拦截」的旧语义（消费方当前一处：`RotatingModifier`
        的 `extra_flag` 抑制）。

        **增量层校验的调用点（S8-6 接线，§3.13 增量行）**：`ctx.invariants` 非 `None`
        时，每个 Modifier 的增量在**作用到分布之前**经 `check_delta(pool_id, out, d)`
        判一遍（`p + δ ≥ 0`；δ 在 `p` 的支撑上不全为 0）。**三条候选的裁决（S8-6）**：
        计划 §3.13 与 S8-6 原写「调用点在 `_apply_delta()` 内部」，而该函数已随 S8-1
        迁到叶子层、签名收为 `(dist, d)`，**取不到 `pool_id` 与校验器**，故不可执行。
        候选 ②（把 checker 作为形参传入 `_apply_delta`）要让这个框架级函数多收一个
        `pool_id` 形参（判据的异常信息要它）；候选 ③（在骨架内循环里包一层）与候选 ①
        同源但需另立一个只此一处消费的包装函数。**取候选 ①**：调用点落在骨架内循环
        （`p` 与 `δ` 同时在手、`pool_id` 由 `ctx.draw.pool_id` 可得），校验器经
        `PityContext.invariants` 进骨架。

        **候选 ① 的取舍理由（S8-6 审查收口订正）**：原稿两条论证有误，订正如后。
        其一「唯一通道」不成立：另有两条替代，(i) `Pity` 自持校验器引用、由引擎装配后
        注入；(ii) 给 `Pity.before_draw` 加 keyword-only 形参、由引擎按
        `isinstance(bh, Pity)` 分派。真正的取舍理由是候选 ① **无需分派**：旧类与新骨架
        同在一个 `_behaviors_for_pool` 序列里，按类型分派会把这条分歧写进引擎的调度
        循环；它同时**让校验器随调用走**（不必在装配期回填到每个骨架实例）、**不给
        叶子层加形参**。其二「候选 ② 与 §3.1.6 相抵」是对 §3.1.6 的误引：该节约束的是
        **import 方向**（叶子层不 import 编排层），把鸭子类型对象当形参传入**不产生
        模块依赖**，叶子层的红线仍是「不 import 编排层」这一条，候选 ② 的实际代价只在
        签名多一个 `pool_id`。

        **边界登记（S8-6 审查收口）**：`ctx.invariants` 是**未登记的新耦合面**，零件
        当前零消费（`core/pity_tracker.py` / `core/pity_modifier.py` 中无任何读取），
        **约定零件不得消费它**（零件要判据只能用各自已有的相位钩子）。
        **零开销**：生产传 `invariants=None`，引擎不建实例、`ctx.invariants` 为 `None`
        （每抽一次属性读，不逐 Modifier 重复读）。
        """
        ctx.readonly = readonly
        if not self._lifecycle.is_active(self._state, self._name):
            return ctx.current.copy()
        for tr in self._trackers:            # N1 首段：计数型先在 before 侧推进
            tr.advance(ctx, self._state, self._name, readonly=readonly)
        for tr in self._trackers:            # N1 中段：抽前需读 state 并消费随机源的零件
            tr.prepare(ctx, self._state, self._name, readonly=readonly)
        out = ctx.current.copy()
        checker = ctx.invariants               # 增量层校验器（None = 未接线，生产默认）
        for mod in self._modifiers:
            # ISSUE-407 / ISSUE-505：按零件命名空间取 view，**不得写死 `self._view`**
            # （声明了 `namespace` 的零件必须读到自己的命名空间）。
            d = mod.compute_delta(self._view_for(mod), out, ctx)
            if d is not None:
                if checker is not None:
                    # 增量层：判在「p 与 δ 同时在手、尚未归一化」处（§3.13）。
                    checker.check_delta(ctx.draw.pool_id, out, d)
                out = _apply_delta(out, d)   # (out + d) / Σ(out + d)
        return out

    # ── M4 / 退役：after_draw ──

    def after_draw(self, ctx: 'PityContext') -> None:
        """`is_active` 早退 → `did_fire` → 退役判定（**四实参**）→ 退役 → `commit`。

        `fired = self.did_fire(ctx)` 必须在退役判定**之前**取值（ISSUE-402）：
        `should_deactivate` 的第四实参是「本次抽卡是否让本保底回到初始状态」，由
        `any(tr.did_reset(...))` 给出——Lifecycle 自身拿不到该判据（`LifecycleConfig`
        只有 `deactivate_on_early_hit` / `depends_on`，无 `scope` / `reset`，而「命中」
        的定义依赖后者）。三实参调用有两种失败形态：① 按四参协议实现 → 每次抽卡
        `TypeError`；② 迁就三参 → `triggers` 退化为「激活后的**抽数**」，
        `max_triggers=2` 在第 2 抽即退役，与「触发 N 次后退役」相反。

        **退役先于 `commit`**（ISSUE-018）：旧实现在 `_on_reset()` 返回 True 时提前
        return、跳过 `counter().reset()`。若写成「先 commit 后 deactivate」，counter
        会被无条件归零，与 N1 例外断言相悖。`did_reset` 只看本次 `ctx.draw`
        （§3.1.1 M4 统一语义），与 `commit` 的先后无关，故先取值是安全的。
        """
        if not self._lifecycle.is_active(self._state, self._name):
            return
        fired = self.did_fire(ctx)
        retire = self._lifecycle.should_deactivate(
            ctx, self._state, self._name, fired)
        if retire:
            self._lifecycle.deactivate(self._state, self._name)
        # 仅 `deactivate_on_early_hit` 触发的退役跳过重置；其余退役动作（如触发次数
        # 用尽）不改变 commit 语义，counter 照常归零。
        skip_reset = retire and self._lifecycle.deactivate_on_early_hit
        for tr in self._trackers:            # N1 末段：此处只落重置/翻转/累积
            tr.commit(ctx, self._state, self._name, skip_reset=skip_reset)

    def did_fire(self, ctx: 'PityContext') -> bool:
        """M4：统一为「本次抽卡是否让本保底回到初始状态」（§3.1.1 M4 表）。"""
        return any(tr.did_reset(ctx, self._state, self._name)
                   for tr in self._trackers)


def create_behavior(pdef, state: 'PityState', **extra) -> 'PityBehavior':
    """工厂函数——从 PityDef（P55 扁平化字段）构造 behavior 实例。

    **P64 S4-1 双路径**：registry 条目含 `preset` 键则走 **preset 分支**（按名取键
    构造统一骨架 `Pity`，§3.2）；否则走**旧类兼容分支**（保留到发布前，见 GATE-5）。

    参数直接从 dataclass 字段读取；软保底语法糖（soft_start/soft_end/soft_increment）
    经 _expand_soft_to_deltas() 展开为 deltas（仅旧类分支）。
    """
    entry = BEHAVIOR_REGISTRY[pdef.btype]

    # scope：优先取 PityDef.scope（用户配置），回退 registry 的 default_scope。
    # 2026-09-16 修正：此前只读 registry，PityDef.scope 被静默忽略，
    # 导致跨稀有度保底无法配置。P55 前的旧格式无 scope 字段，
    # getattr 返回 None 时自然回退。
    # P64 S4-2：本式与 preset 侧取同一个归一化点 `_norm_scope`（ISSUE-503），
    # 两处各写一份 `.lower()` 时，任何一处漏改都会让 `Pity._scope`（小写）与
    # 零件 `_scope`（原值）分叉，`ctx.draw.scope_cards.get('SSR', ())` 取空、
    # 该保底静默恒等且不报错。
    _default_scope = entry.get("default_scope", "ssr")
    scope = _norm_scope(pdef, _default_scope)

    # ══ 裁决 7B（2026-10-05）：`soft_*` + `target_featured = true` 类型级硬拒 ══
    # 校验点定稿为**本函数**（§3.2.1 落地面 ①，preset 构造前即抛）：等价性 harness
    # 与直构 `PityDef` 的路径**绕过 TOML 层**，防线须盖住构造入口，故不放在
    # `_build_pity`。判据来源：手册 10 处 `target_featured = true` 全部落在
    # `type = "hard"`，`soft_*` 一次都没有；soft 侧该形态可等价分解为
    # 「稀有度级 + 卡级」两步转移，能力不丢，故从配置面移除（详 §3.2.1）。
    # **本拒止与落地面 ②（`config.toml` 的 `ssr_soft` 删去该行）是同一条裁决的两面**：
    # 只落拒止而不改样例配置时，本 `ConfigError` 会在 `PityEngine` 构造期上抛、样例
    # 配置直接构造失败（S4-5 之前它被 `__init__` 的 `try/except` 吞成 `logger.warning`
    # 并跳过该保底，样例配置的保底**静默消失**；该兜底已随 S4-5 删除）。
    if getattr(pdef, 'target_featured', False) and pdef.btype in _SOFT_TYPES:
        from .config_store import ConfigError
        raise ConfigError(
            f"保底 '{pdef.name}'（type='{pdef.btype}'）不支持 target_featured=true："
            f"该字段仅对 hard 族生效（裁决 7B，2026-10-05）；soft 保底的目标集恒为 "
            f"scope 全集（可等价分解为「稀有度级 + 卡级」两步转移表达同形配置）。"
        )

    # ══ P64 preset 分支（§3.2 AUDIT-BREAK-3；preset 本体随 S4-2 / S4-3 逐条落地）══
    preset = entry.get("preset")
    if preset is not None:
        from .config_store import ConfigError
        built = preset(pdef)
        # 两道**互补**校验，**不得合并成一道**：前者查多（未知键）、后者查漏
        # （必需键缺），合并后两类问题互相掩盖。二者都是**运行期**校验：导入期的
        # `_validate_registry()` 只判 `preset` 可调用、不碰键集（ISSUE-405）。
        _unknown = set(built) - {'trackers', 'modifiers', 'lifecycle', 'flags', 'counters'}
        if _unknown:
            raise ConfigError(
                f"preset '{pdef.btype}' 返回未声明键 {sorted(_unknown)}")
        if 'lifecycle' not in built:
            raise ConfigError(
                f"preset '{pdef.btype}' 缺少必需键 'lifecycle'")
        # **按名取键，禁止 `**built` 直展开**：直展开会让未知键在 `Pity(...)` 处抛
        # `TypeError`（键多余）或静默落成死代码（键无人读）。亦**不得传旧类分支的
        # `params` dict**（其中 `target_featured` / `reset` 在骨架无对应形参，见
        # §3.1.4 AUDIT-BREAK-2）。
        # `priority` 走**构造形参**（§3.6 M3 / ISSUE-203）：S4b 已把该字段定义在
        # `PityDef` 上，故此处直取字段，不再用 `getattr` 兜底（S4-2 审查结转项）。
        return Pity(
            name=pdef.name, state=state, scope=scope, btype=pdef.btype,
            priority=pdef.priority,
            pools=tuple(getattr(pdef, 'pools', ('*',))),
            trackers=built['trackers'], modifiers=built['modifiers'],
            lifecycle=built['lifecycle'],
            flags=built.get('flags'), counters=built.get('counters'),
        )

    # ══ 旧类兼容分支（**仅旧类分支**；保留到发布前，见 GATE-5）══
    # 下面 `cls(**params)` 的 `params` 组装段随「发布前一次性移除旧类」一并删除，
    # 勿按此形态复制到 preset 分支（GATE-5 末条）。
    # `entry["class"]` 改取 `entry.get("class")`（S4-1 审查 low）：仅影响「运行期注入
    # 无 `class` 键的畸形条目」这一不可达场景（该类条目在导入期已被
    # `_validate_registry()` 以 `TypeError` 拦下），报错由 `KeyError` 变为下面的
    # `ValueError`；60 组真实类型的探针输出逐字段未变，故「零运行时行为变更」成立。
    cls = entry.get("class")
    if cls is None:
        raise ValueError(
            f"Behavior type '{pdef.btype}' 尚未实现——"
            f"P56 将交付事件驱动型保底。"
        )

    # btype 传递给 behavior——基类据此推导 is_soft/is_hard/is_event_driven
    params: Dict[str, Any] = {"btype": pdef.btype}

    _SOFT_SUFFIX_TYPES = CounterBasedBehavior._SOFT_SUFFIX_TYPES
    _P56_TYPES = frozenset({'rotating', 'rotating_soft', 'rotating_cr', 'rotating_cr_soft', 'targeted', 'targeted_soft'})

    if getattr(pdef, 'deltas', None) is not None:
        params['deltas'] = pdef.deltas
    elif pdef.btype in _SOFT_SUFFIX_TYPES:
        pass  # deltas 由 SoftPityMixin._init_soft_pity() 独立展开
    elif hasattr(pdef, 'soft_start') and pdef.soft_start is not None:
        from .config_toml import _expand_soft_to_deltas
        params['deltas'] = _expand_soft_to_deltas(
            pdef.btype, pdef.soft_start,
            getattr(pdef, 'soft_end', None),
            getattr(pdef, 'soft_increment', None),
        )
    if getattr(pdef, 'threshold', None) is not None:
        params['threshold'] = pdef.threshold
    # 以下两处注入是**旧类分支专属**（AUDIT-BREAK-2）：骨架 `Pity.__init__` 无这两个
    # 形参，接回 preset 分支即 `TypeError: unexpected keyword argument`。勿复制。
    if getattr(pdef, 'target_featured', False):
        params['target_featured'] = True
    if getattr(pdef, 'reset', None):
        params['reset'] = pdef.reset
    # ── P56：事件驱动型参数透传（仅 P56 type） ──
    if pdef.btype in _P56_TYPES:
        for attr in ('cr_counter_threshold', 'cr_base_rate', 'cr_state_probs',
                     'fate_threshold', 'switch_allowed', 'switch_resets_progress',
                     'soft_deltas', 'soft_start', 'soft_end', 'soft_increment'):
            v = getattr(pdef, attr, None)
            if v is not None:
                    params[attr] = v
        if getattr(pdef, 'guaranteed_init', False):
                params['guaranteed_init'] = True
        if getattr(pdef, 'fate_points_init', 0):
                params['fate_points_init'] = pdef.fate_points_init
    # ── P64 S4-4：旧 `lifecycle_kwargs` 段已删除（§3.1.3 / ISSUE-301）──
    # `pdef.deactivate_on_early_hit` / `pdef.depends_on`（连同退役维的
    # `pdef.max_triggers`）到 Lifecycle 对象的转换**只有一处**：模块级
    # `build_lifecycle(pdef)`，由各 preset 工厂的 `lifecycle=` 键消费。
    # 删除时机：S4-2 / S4-3 之后 10 条 registry 条目已全部 preset 化，旧类兼容
    # 分支在 registry 上已无入口（只剩测试注入的合成条目），故此处不再注入
    # `LifecycleConfig`。留着即「同一转换两处」，而两处各留一半时的失效模式
    # 没有对照实现可发现。本分支的 `params` 组装段整体随「发布前一次性移除旧类」删除。
    #
    # **代价：本分支对三个生命周期字段静默丢弃**（S4-4 审查 minor）。分支在生产上
    # 结构性不可达（导入期 `_validate_registry()` 要求每条目 `preset` 可调用，且全库
    # 无第二处 registry 注入点），但「不可达」是易失前提，故对任一字段非默认即显式
    # 拒绝，把静默丢弃变成响亮的失败（与 ISSUE-301 消除「配置静默失效」同取向）。
    # `False` / `None` / `0` 即默认，不触发。
    _lc_fields = [f for f in ('deactivate_on_early_hit', 'depends_on', 'max_triggers')
                  if getattr(pdef, f, None)]
    if _lc_fields:
        from .config_store import ConfigError as _ConfigError
        raise _ConfigError(
            f"旧类兼容分支（btype='{pdef.btype}'）不支持生命周期字段 {_lc_fields}："
            f"它们的唯一转换点是 `build_lifecycle(pdef)`，由 preset 工厂消费（§3.1.3）。"
            f"本分支只服务未 preset 化的测试合成条目。")

    return cls(name=pdef.name, state=state, scope=scope, **params)


# ── P55：behavior 排序与校验 ──

# 排序优先级：counter_soft → counter_hard → event_driven_soft → event_driven_hard
_BTYPE_ORDER = {
    'soft_interval': 0, 'soft_additive': 0, 'soft_step': 0,
    'hard': 1,
    'rotating_soft': 2, 'rotating_cr': 2, 'rotating_cr_soft': 2,
    'rotating': 3, 'targeted': 3, 'targeted_soft': 3,
    'rotating_inverse': 3,   # G1 幻塔连中后必歪（ISSUE-105，随 S1a 的集合内容同批）
}


def _resolve_order(behaviors, rarity_rank=None):
    """按稀有度层级→priority→type 优先级→name 排序 behavior 列表。

    P55 §3.3：高稀有度先执行（rank 值小→优先级高），同稀有度内
    counter_soft → counter_hard → event_driven_soft → event_driven_hard。
    同优先级按 name 字母序（确定性）。

    **P64 S6b（G5，§1.5 排序键规格）**：`priority` 插在稀有度 rank 之后、
    `_BTYPE_ORDER` 之前，即排序键为 `(rank, -priority, order, name)`。
    方向取「**数值大者先执行**」（故对 priority 取负后交给 sorted 升序），
    依据两条：
      ① 字段名直译即「优先级」，手册 3.4 节把该需求写作「福利保底和常规保底的
         优先级交互」，期望 `hard` 先于 `targeted`，即优先级高者先执行；
      ② 全部 priority 为 0 时 `-0 == 0`，排序结果与接线后的默认序逐位相同，
         故取此方向不引入回归（方向本身不影响「全 0 退化为默认序」这一要求）。
    `getattr(bh, '_priority', 0)` 兜底：`create_behavior` 保留着旧类兼容分支
    （见 GATE-5），旧类实例没有该属性，缺属性即按默认 0 参与排序。
    """
    if rarity_rank is None:
        rarity_rank = {}
    def _sort_key(bh):
        scope = getattr(bh, '_scope', '')
        rank = rarity_rank.get(scope, 99)
        priority = -getattr(bh, '_priority', 0)
        order = _BTYPE_ORDER.get(getattr(bh, '_btype', ''), 99)
        return (rank, priority, order, getattr(bh, '_name', ''))
    return sorted(behaviors, key=_sort_key)


def _validate_behaviors(behaviors):
    """PityEngine 层校验——第二道防线（TOML 解析层为第一道）。

    校验规则：
      1. name 重名 → ValueError
      2. 同 scope 两个 hard → ConfigError（互斥）
      3. 同 scope 两个事件驱动型 → ConfigError（互斥）
      4. 同 scope 同 btype 两个 soft → ConfigError（重复配置）
    """
    from .config_store import ConfigError
    seen_names = {}
    scope_hard = set()
    scope_event = set()
    scope_soft = {}

    for bh in behaviors:
        name = getattr(bh, '_name', id(bh))
        scope = getattr(bh, '_scope', '')
        btype = getattr(bh, '_btype', '')

        # 规则 1：name 重名
        if name in seen_names:
            raise ValueError(
                f"PityEngine._validate_behaviors: 重复的 behavior name '{name}'——"
                f"已由 '{seen_names[name].__class__.__name__}' 注册。"
                f"每个 behavior 必须有唯一的 name。"
            )
        seen_names[name] = bh

        # 规则 2-4：scope 重叠校验
        if getattr(bh, 'is_hard', False):
            if scope in scope_hard:
                raise ConfigError(
                    f"同 scope '{scope}' 存在两个硬保底："
                    f"'{next(n for n, b in seen_names.items() if getattr(b,'_scope','')==scope and getattr(b,'is_hard',False))}'"
                    f" 与 '{name}'——每个稀有度最多一个硬保底"
                )
            scope_hard.add(scope)
        elif getattr(bh, 'is_event_driven', False):
            if scope in scope_event:
                raise ConfigError(
                    f"同 scope '{scope}' 存在两个事件驱动型保底——每个稀有度最多一个事件驱动型"
                )
            scope_event.add(scope)
        elif getattr(bh, 'is_soft', False):
            key = (scope, btype)
            if key in scope_soft:
                raise ConfigError(
                    f"同 scope '{scope}' 同 type '{btype}' 存在两个软保底："
                    f"'{scope_soft[key]}' 与 '{name}'——请合并或使用不同 type"
                )
            scope_soft[key] = name


#: 判据 2 的**白名单**（§3.12.2）：由零件之外的层写入、**无任何零件声明它**的键。
#: 不留白名单则 `targeted` 族全部合法配置在构造期被判为「引用不存在的键」。
#:
#: **声明与理由都在叶子层**（`core/pity_primitives.py`，S11 审查收口 F3 的下沉）：
#: 本模块与 `core/invariants.py` 都从那里取**同一对象**，故「两处声明 + 逐元素守卫」
#: 的镜像面不复存在；本文件顶部对该常量的 import 即 re-export，既有导入路径
#: （`from gacha_simulator.core.pity import _EXTERNAL_STATE_KEYS`）不变。
#: 白名单的键来历与理由（写入方 / 读取方 / §3.1.1 的 L4 例外 2）见叶子层该常量的段。


def _check_declared_keys(declared_keys, name):
    """S10-2 的两条构造期判据（§3.12.2 第 1 / 第 2 条），与 `_validate_behaviors` 同层。

    **输入是 `Pity._declared_keys`（ISSUE-501）**，即三族 `state_keys()` 的汇总，
    由 §3.1.4 骨架写入。本函数**不自行推断声明集**（那会让 §3.12.1 / §3.12.2 /
    §3.13 三处各有一套口径），只做两条判据的检查本体。

    判据 1（同一状态键被重复声明）：比对 `declared_keys['trackers']` 内的重复。
    两种形态都落在这一条：**两个 Tracker** 声明同一个键（后写者覆盖先写者，
    计数器的归属不再唯一），或**单个 Tracker 的键集内**同一键出现两次
    （声明集与「一个键一个写入方」不再对应）。两者读取侧都只看到一个值、
    **不报错**，故一律在构造期拒收。

    判据 2（Modifier 引用不存在的键）：「存在」的口径 = 该键在 **Tracker ∪
    Lifecycle** 的 `state_keys()` 并集内，另加 `_EXTERNAL_STATE_KEYS` 白名单。
    比对集 = `declared_keys['modifiers']`（各 Modifier **自己**的声明集，§3.14 条件
    内联后读键一律落在这一处，故键名拼错在此处被构造期拦下）。

    **不含 Tracker 自身的读键**：判据 2 的文本只约束 Modifier（§3.12.2），
    而 `FateTracker` 对 `selected_card` 的读取属 §3.1.1 的 L4 例外 2
    （Tracker 允许读「不由自己声明的键」）。

    两处均抛 `ConfigError`（配置错误，与 `_validate_behaviors` 的规则 2/3/4 同类；
    不用 `ValueError`，后者在本库专用于「编程错误」面的重名判定）。
    """
    from .config_store import ConfigError

    # ── 判据 1：同一键被两个 Tracker 声明（§3.12.2 第 1 条）──
    seen: set = set()
    duplicated: List[str] = []
    for key in declared_keys['trackers']:
        if key in seen and key not in duplicated:
            duplicated.append(key)
        seen.add(key)
    if duplicated:
        raise ConfigError(
            f"保底 '{name}' 的 Tracker 声明集存在重复键 "
            f"{sorted(duplicated)}：同一状态键被重复声明"
            f"（两个 Tracker 之间，或单个 Tracker 内）（§3.12.2 判据 1）："
            f"「一个键一个写入方」不再成立，后写者覆盖先写者，且不报错"
        )

    # ── 判据 2：Modifier 引用不存在的状态键（§3.12.2 第 2 条）──
    available = (set(declared_keys['trackers'])
                 | set(declared_keys['lifecycle'])
                 | _EXTERNAL_STATE_KEYS)
    unknown = sorted({k for k in declared_keys['modifiers'] if k not in available})
    if unknown:
        raise ConfigError(
            f"保底 '{name}' 的 Modifier 引用了不存在的状态键 {unknown}"
            f"（§3.12.2 判据 2）：「存在」的口径是 Tracker ∪ Lifecycle 的声明集"
            f"（另加白名单 {sorted(_EXTERNAL_STATE_KEYS)}）；"
            f"当前可用的键为 {sorted(available)}"
        )


def _check_uses_sim(modifiers, name):
    """`uses_sim` 注解的构造期校验（P64 S9-2 第 ③ 件，§3.10.2）。

    **只校验名字是否在已知源集合内**（`KNOWN_SIM_SOURCES`，当前只有 `owns`），
    **不参与门控**：`ctx.sim` 对所有保底一律可读（非 Optional、永远填充），注解写与
    不写都不改变行为。校验的唯一对象是「注解腐烂」：名字拼错、或引用了已删除的源
    （`balance()` 于 2026-10-06 删除）时，注解会静默地指向一个不存在的源，检查器
    据此报告出的「哪些保底读了 sim 的什么」随之失真。与 §3.12.2 两条判据同层、
    同在 `Pity` 构造期（`create_behavior` 的 preset 分支失败即抛 `ConfigError`）。

    **为什么不在 `_validate_registry()` 的导入期自检里做**：那里只有 preset 工厂
    可调用性可判（`class: None`），`Modifier` 实例要到 `preset(pdef)` 被调用时才
    存在；注解住在零件类上、由 preset 实例化，故唯一能看到全部实例的时点是构造期。
    """
    from .config_store import ConfigError
    for mod in modifiers:
        for src in getattr(mod, 'uses_sim', ()) or ():
            if src not in KNOWN_SIM_SOURCES:
                raise ConfigError(
                    f"保底 '{name}' 的 Modifier {type(mod).__name__} 声明了未知的 "
                    f"`uses_sim` 源 {src!r}（§3.10.2）：已知源集合为 "
                    f"{list(KNOWN_SIM_SOURCES)}。注解不参与门控，但它会被检查器读作"
                    f"「本保底读了 sim 的什么」，指向不存在的源即注解腐烂"
                )


def _build_pity_state_init(pity_defs, counter_init_overrides=None):
    """从 PityDef 列表构造初始 PityState。

    P55 变更：counter_init 从每个 PityDef.counter_init 读取（而非全局 PityConfig）。
    同时注入 guaranteed_init / fate_points_init 初始标志。

    Args:
        pity_defs: List[PityDef]（扁平化后的 17 字段版本）。
        counter_init_overrides: 可选——per-name counter 覆盖值（GUI 面板传入）。
    """
    state = PityState()
    for pdef in pity_defs:
        # counter_init：优先使用覆盖值，否则用 PityDef 自身值
        cv = 0
        if counter_init_overrides and pdef.name in counter_init_overrides:
            cv = counter_init_overrides[pdef.name]
        elif hasattr(pdef, 'counter_init') and pdef.counter_init:
            cv = pdef.counter_init
        if cv:
            state.set(pdef.name, "counter", cv)

        # guaranteed_init（rotating 家族初始大保底状态）
        if getattr(pdef, 'guaranteed_init', False):
            state.set(pdef.name, "guaranteed", True)

        # fate_points_init（targeted 家族初始命定值）
        fp = getattr(pdef, 'fate_points_init', 0)
        if fp:
            state.set(pdef.name, "fate_points", fp)

        # P56：targeted 家族显式注入 selected_card（初始定轨卡片）
        _TARGETED_TYPES = frozenset({'targeted', 'targeted_soft'})
        if getattr(pdef, 'btype', '') in _TARGETED_TYPES:
            sc = getattr(pdef, 'selected_card_init', None)
            state.set(pdef.name, "selected_card", sc)

    return state


@dataclass
class PoolPitySpec:
    pity_names: List[str]
    featured_ids: Set[str] = field(default_factory=set)
    ssr_ids: Set[str] = field(default_factory=set)
    # ── P55 新增：槽位映射（供 DrawInfo 构造） ──
    scope_cards: Dict[str, tuple] = field(default_factory=dict)
    featured_cards: Dict[str, tuple] = field(default_factory=dict)
    scope_slots: Dict[str, tuple] = field(default_factory=dict)
    featured_slots: Dict[str, tuple] = field(default_factory=dict)
    # P56: card_id -> slot name mapping
    card_to_slot: Dict[str, str] = field(default_factory=dict)


def compute_scope_mappings(pool) -> tuple:
    """从池子的 Reward 列表预计算 scope_cards/featured_cards/scope_slots/featured_slots/card_to_slot。

    P55 ISSUE-032：Reward.extra_info 含 'rarity'/'featured' 键，
    据此分组生成 DrawInfo 所需的槽位映射。

    P56：返回值新增 card_to_slot（card_id → 槽位名），供 TargetedBehavior O(1) 查找。

    Returns:
        (scope_cards, featured_cards, scope_slots, featured_slots, card_to_slot) 五元组 dict。
    """
    cards_by_rarity: Dict[str, list] = {}
    featured_by_rarity: Dict[str, list] = {}
    card_to_slot: Dict[str, str] = {}

    for rwd, _prob in getattr(pool, 'rewards', []):
        extra = getattr(rwd, 'extra_info', {}) or {}
        rarity = extra.get('rarity', '').lower()
        if not rarity:
            continue
        cards_by_rarity.setdefault(rarity, []).append(rwd.id)
        if extra.get('featured'):
            featured_by_rarity.setdefault(rarity, []).append(rwd.id)
            card_to_slot[rwd.id] = f'{rarity}_featured'
        else:
            card_to_slot[rwd.id] = rarity

    scope_cards = {r: tuple(cards) for r, cards in cards_by_rarity.items()}
    featured_cards = {r: tuple(cards) for r, cards in featured_by_rarity.items()}

    # 槽位映射——featured 拆分为独立槽位名（如 'ssr_featured'）
    scope_slots = {}
    featured_slots = {}
    for rarity in cards_by_rarity:
        if rarity in featured_by_rarity:
            featured_slot = f'{rarity}_featured'
            scope_slots[rarity] = (rarity, featured_slot)
            featured_slots[rarity] = (featured_slot,)
        else:
            scope_slots[rarity] = (rarity,)
            featured_slots[rarity] = (rarity,)

    return scope_cards, featured_cards, scope_slots, featured_slots, card_to_slot


class PityEngine:
    """保底引擎——P55 重构：自行管理 behavior 生命周期。

    PityEngine(pool_specs, pity_defs: List[PityDef], state, rarity_rank)

    新引擎在构造时通过 create_behavior() 从 PityDef 构造 behavior 实例，
    经过 _resolve_order() 排序 + _validate_behaviors() 校验后存入内部 registry。
    """

    def __init__(self, pool_specs: Dict[str, PoolPitySpec],
                 pity_defs,  # List[PityDef]（P55 扁平化定义列表）
                 rarity_rank: Dict[str, int] = None,
                 state: 'PityState' = None,
                 invariants: 'Optional[InvariantChecker]' = None):
        self.pool_specs = pool_specs
        self._rarity_rank = rarity_rank or {}

        # ── P64 S11（ISSUE-003 / ISSUE-945）：不变式校验器的挂载层 ──
        # 挂在引擎上（不是模块级全局、不是 `Pity`、不是 `env` 的新字段）的理由是它
        # 随 `env.pity_engine` 进每条并行路径的 pickle 图，spawn worker 自动继承该
        # 设置。`invariants=None`（默认）即**生产关闭态**：连实例都不建，两处调用点
        # 的首行守卫 `is not None` 直接短路，零开销、零行为变更。`enabled=True` 只能
        # 由测试夹具产出。
        self._invariants = invariants

        self.pity_defs = {p.name: p for p in pity_defs} if pity_defs else {}
        self._state = state

        # 从 PityDef 构造 behavior 实例
        self.behaviors: Dict[str, PityBehavior] = {}
        from .config_store import ConfigError, PityDef as _PityDef

        # 重名校验（2026-09-16 修正）：此前重名会被下面的 dict 赋值静默覆盖、
        # 只留后者，用户无从察觉，`_validate_behaviors` 的规则 1 因此永不可达。
        _seen_names: set = set()
        for pdef in (pity_defs or []):
            if not isinstance(pdef, _PityDef):
                continue
            if pdef.name in _seen_names:
                raise ValueError(
                    f"PityEngine: 重复的保底 name '{pdef.name}'——"
                    f"每条保底必须有唯一的 PityDef.name"
                )
            _seen_names.add(pdef.name)

        for pdef in (pity_defs or []):
            if not isinstance(pdef, _PityDef):
                continue
            # P56：移除 skip guard——所有 10 种 type 均由 create_behavior() 处理
            # ── P64 S4-5（ISSUE-204）：构造兜底由「logger.warning 后跳过」改为硬失败 ──
            # 原 `except Exception → logger.warning` 会把构造失败的那条保底从
            # `self.behaviors` 里悄悄删掉。后果不止「少一条保底」：紧随其后的
            # `_resolve_order` / `_validate_behaviors` 于是跑在**截断后**的列表上，
            # 同 scope 互斥校验（规则 2/3/4）失去语义，形成「配置里写了保底、运行时
            # 该保底不存在且无可见报错」。分类为配置错误（与 `_validate_behaviors` 的
            # 校验失败同层，§四 `core/pity.py` 行），故两级处理：
            #   ① `create_behavior` 自己抛的 `ConfigError` 原样上抛（消息里带保底名与
            #      成因，如 7B 的 target_featured 硬拒），不二次包装；
            #   ② 其余异常（未知 btype 的 `KeyError`、preset 体内的 `TypeError` 等）
            #      一并归为 `ConfigError`——ISSUE-204 的措辞是「**任一** preset 构造
            #      失败抛 `ConfigError`」，只放行 `ConfigError` 会让其余失败形态以
            #      非配置错误的类型逃逸；`from exc` 保留原始调用链。
            try:
                bh = create_behavior(pdef, self._state)
            except ConfigError:
                raise
            except Exception as exc:
                raise ConfigError(
                    f"PityEngine: 保底 '{pdef.name}'（type='{pdef.btype}'）构造失败："
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            self.behaviors[pdef.name] = bh

        # 排序 + 校验
        ordered = _resolve_order(list(self.behaviors.values()), self._rarity_rank)
        _validate_behaviors(ordered)
        self._pity_defs_list = pity_defs  # P56
        self._behavior_list: List[PityBehavior] = ordered

        # ── P82-1：独立排序视图（§1.5「接线实施方案」）──
        # 让 `_resolve_order()` 的排序结果成为池内保底的实际执行顺序：三个调度入口
        # （get_probabilities / before_draw / after_draw）共用 `get_behaviors_for_pool()`，
        # 排序生效即概率管道生效。
        # 视图与 `PoolPitySpec.pity_names` 分离：后者保留 TOML 定义顺序，
        # 兼有第二职责（`banner.draw_pity_names` 用 `','.join(pity_names)` 生成
        # 输出串，字面顺序会进 golden 快照），故不动它；本视图只承载「谁先执行」。
        # 池内序 = 全局排序（ordered）在池成员上的子序：排序键（稀有度 rank
        # → priority → _BTYPE_ORDER → name）只依赖 behavior 自身属性、与池无关，
        # 故子序即该池按同一排序键的结果。
        _order_index: Dict[str, int] = {
            getattr(bh, '_name', ''): _i for _i, bh in enumerate(ordered)
        }
        self._pool_order: Dict[str, List[str]] = {}
        for _pool_id, _spec in self.pool_specs.items():
            # S4-5 起构造失败即在构造处抛错，不存在「构造失败但仍进了
            # self.behaviors」的条目；此处的成员过滤保留为 `pity_names` 与
            # `self.behaviors` 键集的对齐守卫（与 get_behaviors_for_pool 的
            # `bh is None` 守卫等价）。
            self._pool_order[_pool_id] = sorted(
                (_n for _n in _spec.pity_names if _n in self.behaviors),
                key=lambda _n: _order_index.get(_n, len(ordered)),
            )

        # ── P56：构建 depends_on 激活传播图 ──
        self._activation_graph: Dict[str, List[str]] = self._build_activation_graph(
            list(self.behaviors.values()))

    # ── 辅助：按池过滤 behavior ──

    def _behaviors_for_pool(self, pool_id: str):
        return self.get_behaviors_for_pool(pool_id)

    def get_behaviors_for_pool(self, pool_id: str):
        """公开方法——返回当前池关联的 behavior 实例列表。

        P82-1：顺序取自 `self._pool_order`（`__init__` 预计算的独立排序视图）——
        池内保底的执行顺序由排序键决定而非 TOML 书写顺序；
        `PoolPitySpec.pity_names` 保持 TOML 顺序不动（`banner.draw_pity_names` 依赖它）。
        """
        order = self._pool_order.get(pool_id)
        if order is None:
            return []
        result = []
        for pname in order:
            bh = self.behaviors.get(pname)
            if bh is not None:
                result.append((pname, bh))
        return result

    def get_pity_def(self, name: str):
        """返回指定 behavior 的原始 PityDef 配置（只读视图）。"""
        return self.pity_defs.get(name)

    def _build_activation_graph(self, behaviors):
        """解析 depends_on 关系 -> {source_name: [dependent_name, ...]}。

        **S10-2（§3.12.2 第 3 条）：成环检测为新增能力。** 本函数此前只校验
        `depends_on` 指向的名字存在（`dep not in all_names` 那一支），**不做环检测**，
        故 `A depends_on B` + `B depends_on A` 会被静默接受：激活传播在
        `PityEngine.after_draw` 里沿环反复置位，`DependentActive` 的保底互相激活、
        退役计数（`triggers`）随传播次数漂移，且**不报错**。自环
        （`A depends_on A`）同属此列。故在图建好后立即查环，成环抛 `ConfigError`。

        图的方向是「被依赖方 -> 依赖它的保底」（激活传播方向），与 `depends_on`
        的指向相反；有向图成环与边的整体反向无关，故在本图上查环与在
        `depends_on` 关系上查环等价。

        环检测用**三色迭代 DFS**（`None` = 未访问 / `_GRAY` = 在栈上 / `_BLACK` =
        已出栈）：再次遇到灰节点即成环，此时栈上的那一段就是环路径（取其自该
        灰节点起的后缀，再补上灰节点本身闭合）。用迭代而非递归：依赖链长度由
        配置决定，递归版在深链上有 `RecursionError` 风险，而该异常会被
        `PityEngine.__init__` 的构造兜底归类为 `ConfigError`（S4-5），错误信息失真。
        """
        import warnings
        all_names = {bh._name for bh in behaviors if hasattr(bh, '_name')}
        _bh_by_name = {bh._name: bh for bh in behaviors if hasattr(bh, '_name')}
        graph: Dict[str, List[str]] = {}
        for bh in behaviors:
            name = getattr(bh, '_name', None)
            if name is None:
                    continue
            lc = getattr(bh, '_lifecycle', None)
            if lc and lc.depends_on:
                dep = lc.depends_on
                if dep not in all_names:
                    from .config_store import ConfigError
                    raise ConfigError(f"「{name}」的 depends_on 引用了不存在的 behavior 「{dep}」")
                graph.setdefault(dep, []).append(name)
                source_bh = _bh_by_name.get(dep)
                if source_bh is not None:
                    src_pools = set(getattr(source_bh, '_pools', ()))
                    dst_pools = set(getattr(bh, '_pools', ()))
                    if '*' not in src_pools and '*' not in dst_pools:
                        if not (src_pools & dst_pools):
                            warnings.warn(f"「{name}」的 depends_on 指向「{dep}」，但双方 pools 无交集")

        # ── S10-2：depends_on 成环检测（§3.12.2 第 3 条，新增能力）──
        _GRAY = 1
        _BLACK = 2
        color: Dict[str, int] = {}
        for start in graph:
            if start in color:
                continue
            color[start] = _GRAY
            # 栈元素 = (节点, 未展开的子节点列表)；`pop()` 即按逆序展开
            stack: List[tuple] = [(start, list(graph.get(start, ())))]
            while stack:
                node, children = stack[-1]
                if not children:
                    color[node] = _BLACK
                    stack.pop()
                    continue
                child = children.pop()
                state = color.get(child)
                if state == _GRAY:
                    from .config_store import ConfigError
                    path = [n for n, _ in stack]
                    # 栈序是「激活传播」方向，反转后即 `depends_on` 的指向
                    # （图边 u -> v 的语义是「v 依赖 u」），故报错串读作
                    # 「前者依赖后者」，与用户配置里的写法同向。
                    cycle = list(reversed(path[path.index(child):] + [child]))
                    raise ConfigError(
                        f"depends_on 成环：{' -> '.join(cycle)}"
                        f"（读作「前者依赖后者」）：互相依赖的保底无法确定"
                        f"激活顺序，激活传播会沿环反复置位（§3.12.2 判据 3）"
                    )
                if state is None:
                    color[child] = _GRAY
                    stack.append((child, list(graph.get(child, ()))))
        return graph

    # ── 策略层查询接口（保留旧方法签名兼容） ──

    def _rebind_state(self, state: 'PityState') -> None:
        """P75：将所有 behavior 的 Counter/Flag 重绑到 per-call state。

        在 before_draw()/after_draw()/get_probabilities() 入口调用——确保
        behavior 内部 Counter/Flag 遥控器指向调度层实际使用的 state 对象，
        否则计数器递增写入错误对象（P55 文档 line 1785-1789 预见的 A/B 分裂）。

        纯重定向不复制旧值；rebind 发生在每轮模拟第一次调度，此时旧绑定是
        上一轮模拟的账本，复制旧值会重新引入跨模拟残留。初始值完全由
        阶段 3 完整快照（env.pity_state_init）承载。

        **`state is self._state` 早退已删除（S4-2 处置，2026-10-10）**。原缺陷
        （S3-1 独立审查 → S4-1 登记 → S4-1 审查订正）：该早退对**旧类**成立（旧类
        在构造期即 `Counter(state, ...)` 绑定），对统一骨架 `Pity` **不成立**，
        `Pity` 照 §3.1.4 骨架**不在构造期绑定**零件 Counter/Flag，绑定只发生在
        `Pity._rebind_state`；故早退路径下零件永不绑定，`Tracker.advance` 读
        `self._counter.incr()` 即抛 `AttributeError`（`PityEngine.__init__` 把
        `self._state` 设为构造态却不 rebind，**传 `engine._state` 的派发必抛**）。
        触发条件是「派发的 state 恰为构造期那个对象」而非「早退本身」；实测
        `python -m gacha_simulator.cli -n 3 -w 1 -s 42` 在早退处插桩得
        hits=2379 / misses=3，一场模拟的 `pity_state` 对象整场复用，首调绑定后
        其余每次派发都走早退，**早退是常态路径而非死分支**。构造态 `self._state`
        是唯一未绑定的那一格，故本处置是**修复**而非「顺手清死代码」。

        **取「删早退」而非「在 `Pity.__init__` 绑定零件」**（两者都能修掉构造态
        那一格）：① 本方法全程是纯重定向（不复制旧值），重跑幂等，删掉后语义收敛
        为「把三族重定向到本调用的 `state`」，不新增分支；② 骨架的构造期职责由
        §3.1.4 写死（收集命名空间 → 汇总声明键集 → `Lifecycle.initialize` → 建 view
        → 消费 `flags` / `counters`），**不含**零件绑定，加一处构造期绑定会让「谁
        负责绑定零件」出现两个答案（构造期 + 每次派发），与 P75 纪律「初始值完全由
        per-call state 承载」的口径相抵；③ 按对象同一性短路使「构造态」成为唯一
        例外格，删掉后无例外格，新建克隆 / 快照派生 / 构造态三条路径走同一条重定向。
        **代价如实登记**：每轮模拟的每次派发都重建三族遥控器。隔离 A/B（同配置、
        各 4 次交错、与「只在 `PityEngine._rebind_state` 加回早退」的补丁树对照，
        2026-10-10 S4-2 审查实测）：median 15.92s 对 15.26s（约 +4.4%）、
        min 14.96s 对 14.80s（约 +1.1%）。用例
        `tests/core/test_pity_rebind.py::TestEngineRebind::test_rebind_same_state_still_rebinds`
        钉住本处置（原 `test_rebind_same_state_short_circuit` 守的是已删除的短路）。
        """
        self._state = state
        for bh in self._behavior_list:
            if hasattr(bh, '_rebind_state'):
                bh._rebind_state(state)

    def get_probabilities(self, pool_id: str, state: PityState,
                          base_probabilities: Dict[str, float],
                          sim: 'SimView') -> Dict[str, float]:
        """查询保底调整后的概率分布。

        P75（ISSUE-122）：首行 rebind state 至传入参数（带重绑副作用），随后以只读
        语义查询——「查询不写计数」仍成立，但不再是 P55 归档定义的无副作用纯查询。

        **P64 S9-2：`sim` 是必填参**（§3.10.2）：`PityContext.sim` 非 Optional，
        缺参在构造 `ctx` 时即 `TypeError`（构造期失败），不是运行期读到 `None` 的
        静默恒等。填充点是**通道 B**：`core/strategy.py` 的
        `StrategyContext.get_pity_probabilities`（本入口的全库唯一外部调用点）。
        """
        self._rebind_state(state)  # 必须先于 spec=None 早退（ISSUE-123）
        spec = self.pool_specs.get(pool_id)
        if spec is None:
            return base_probabilities.copy()

        draw_info = DrawInfo(
            pool_id=pool_id, pool_instance_id=pool_id,
            reward_id="", reward_rarity="", is_featured=False,
            scope_cards=spec.scope_cards,
            featured_cards=spec.featured_cards,
            scope_slots=spec.scope_slots,
            featured_slots=spec.featured_slots,
            card_to_slot=spec.card_to_slot,
            base_probabilities=base_probabilities,
            rarity_rank=self._rarity_rank,
        )
        ctx = PityContext(draw=draw_info, current=base_probabilities.copy(), state=state,
                          sim=sim)

        # 只读查询——对每个池关联 behavior 调度
        for pname, bh in self._behaviors_for_pool(pool_id):
            new_probs = bh.before_draw(ctx, readonly=True)
            if new_probs is not None:
                ctx.current = new_probs

        return ctx.current

    def before_draw(self, pool_id: str, state: PityState,
                    base_probabilities: Dict[str, float],
                    sim: 'SimView') -> Dict[str, float]:
        """抽前调度：仅对当前池关联的 behavior 执行 before_draw。

        **P64 S9-2：`sim` 是必填参**（§3.10.2）：理由与
        `get_probabilities` 同（缺参在构造 `ctx` 时即 `TypeError`）。填充点是
        **通道 A**：`core/banner.py` 的 `Banner.draw`。
        """
        self._rebind_state(state)  # P75：重绑 behaviors 到 per-call state（ISSUE-123 先于早退）
        spec = self.pool_specs.get(pool_id)
        if spec is None:
            return base_probabilities.copy()

        draw_info = DrawInfo(
            pool_id=pool_id, pool_instance_id=pool_id,
            reward_id="", reward_rarity="", is_featured=False,
            scope_cards=spec.scope_cards,
            featured_cards=spec.featured_cards,
            scope_slots=spec.scope_slots,
            featured_slots=spec.featured_slots,
            card_to_slot=spec.card_to_slot,
            base_probabilities=base_probabilities,
            rarity_rank=self._rarity_rank,
        )
        ctx = PityContext(draw=draw_info, current=base_probabilities.copy(), state=state,
                          sim=sim)

        # ── P64 S8-6：增量层校验器的 per-call 引用。**只在本入口写**：
        #    `get_probabilities` 按 §3.13 已登记的「四层覆盖边界」不在判据面内
        #    （该入口不调任何一层），故不得同批写入。`None` = 生产默认（零开销）。 ──
        ctx.invariants = self._invariants

        # 按池过滤调度
        for pname, bh in self._behaviors_for_pool(pool_id):
            new_probs = bh.before_draw(ctx)
            if new_probs is not None:
                ctx.current = new_probs

        # ── P64 S11（ISSUE-003）：分布层的唯一调用点——「该池的全部保底跑完、
        #    返回值之前」（§3.13 的「调用点与构造源」段固定此位置）──
        if self._invariants is not None:
            self._invariants.check_after_before_draw(pool_id, ctx.current, self)

        return ctx.current

    def after_draw(self, pool_id: str, state: PityState, reward_id: str,
                   sim: 'SimView'):
        """抽后调度：仅对当前池关联的 behavior 执行 after_draw。

        **P64 S9-2：`sim` 也是必填参**：本入口同样构造 `PityContext`，而该字段
        非 Optional、永远填充（§3.10.2）。它不是「送达通道」（Modifier 不在本相位
        运行），但**字段的完备性要求本入口一并填充**：漏填会让 `after_draw` 相位的
        ctx 带一个 `None`，任何在 `after_draw` 读 `ctx.sim` 的零件（Tracker 亦可读）
        会拿到 `AttributeError` 而非「视图」。§六 的「PityEngine 调度层既有调用形式
        不变（before_draw / after_draw / get_probabilities …；S9 新增必填参数 sim）」
        即本口径。
        """
        self._rebind_state(state)  # P75：重绑 behaviors 到 per-call state
        spec = self.pool_specs.get(pool_id)
        if spec is None:
            return

        is_featured = reward_id in spec.featured_ids
        reward_rarity = self._infer_rarity(reward_id, spec)

        draw_info = DrawInfo(
            pool_id=pool_id, pool_instance_id=pool_id,
            reward_id=reward_id, reward_rarity=reward_rarity,
            is_featured=is_featured,
            scope_cards=spec.scope_cards,
            featured_cards=spec.featured_cards,
            scope_slots=spec.scope_slots,
            featured_slots=spec.featured_slots,
            card_to_slot=spec.card_to_slot,
            base_probabilities={},
            rarity_rank=self._rarity_rank,
        )
        ctx = PityContext(draw=draw_info, current={}, state=state, sim=sim)

        # 按池过滤调度 + P56 声明式依赖传播
        for pname, bh in self._behaviors_for_pool(pool_id):
            bh.after_draw(ctx)
            if bh.did_fire(ctx):
                for dep_name in self._activation_graph.get(bh._name, []):
                    state.set(dep_name, "_active", True)

        # ── P64 S11（ISSUE-003）：状态层 + 生命周期层的唯一调用点——「该池的全部
        #    保底跑完、返回值之前」（§3.13 的「调用点与构造源」段固定此位置）──
        if self._invariants is not None:
            self._invariants.check_after_after_draw(pool_id, state, self)

    def _infer_rarity(self, reward_id: str, spec: PoolPitySpec) -> str:
        """从 reward_id 推断稀有度（大小写归一化）。

        **S8-2 起本方法是「卡 id → 稀有度」这条规则的唯一实现**：原先 `pool.py` 里
        还有一份（喂**概率**路径：`banner.draw` 的 `scale_factors` 还原段与
        `aggregate_probs_by_rarity`），两者的判定顺序曾不同（本方法先查 `ssr_ids`、
        那份先查 `scope_cards`），并因此漂移出缺陷 12。S8-2 把概率路径改为卡级直传
        后那份零消费者、随 ISSUE-504 删除，故「两处实现必须同答」这一守卫形态
        **在结构上不再存在**（守卫随之改写为「本方法的答案 == 池内真实稀有度」，
        见 `tests/core/test_pity_integration.py::TestRarityInferenceGuards`）。

        判定只用 `scope_cards`（唯一真相源；`spec.ssr_ids` 那一级与另一份的两级回退
        已于 2026-10-09 删除，它们都是为绕开 worst_impact 那张写错名字的表而存在的）。
        """
        rid_lower = reward_id.lower()
        for rarity, cards in spec.scope_cards.items():
            if rid_lower in {c.lower() for c in cards}:
                return rarity.lower()
        return ""

    def get_spec(self, pool_id: str) -> Optional[PoolPitySpec]:
        return self.pool_specs.get(pool_id)

    # ── P60 新增：策略层只读查询 ──

    def get_counter(self, name: str) -> int:
        return self._state.get(name, "counter", 0) if self._state else 0

    def get_trigger_count(self, name: str) -> int:
        return self._state.get(name, "triggers", 0) if self._state else 0

    def is_guaranteed(self, name: str) -> bool:
        return self._state.get(name, "guaranteed", False) if self._state else False

    def is_active(self, name: str) -> bool:
        # ISSUE-120：默认 False——depends_on 依赖方初始 inactive（构造期不 set），
        # 与 Flag.is_set() 默认 False 一致；正常 behavior 的 _active=True 由构造期 set + 阶段 3 快照承载。
        # 已无运行时调用方，保留仅供策略层未来使用。
        return self._state.get(name, "_active", False) if self._state else False

    def get_state_summary(self) -> Dict[str, Dict[str, Any]]:
        if self._state is None:
            return {}
        return {name: dict(ns) for name, ns in self._state.data.items()}


