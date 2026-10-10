from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
import logging
import random

# ── P64 S1a：叶子原语层迁出至 pity_primitives（§3.1.6）──
# 下方 re-export 使既有导入路径不变；三个类型集合常量在本模块内**裸名**可用
# （`Pity` 骨架不继承 CounterBasedBehavior，S3-1 起需要）。
from .pity_primitives import (  # noqa: F401
    Counter, Flag, DrawInfo, PityContext, LifecycleConfig, PityState,
    _SOFT_TYPES, _HARD_TYPES, _EVENT_DRIVEN_TYPES,
)

logger = logging.getLogger(__name__)


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
        forked = PityContext(draw=ctx.draw, current=modified, state=ctx.state)
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

    def before_draw(self, ctx, readonly=False):
        total = self._scope_total_prob(ctx)
        if total <= 0:
                return ctx.current.copy()
        featured_slots = self._featured_slots(ctx)
        if not featured_slots:
                return ctx.current.copy()
        selected = ctx.state.get(self._name, "selected_card")
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
        selected = ctx.state.get(self._name, "selected_card")
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
        selected = ctx.state.get(self._name, "selected_card")
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


# ── P60 新增 → P55 更新：保底类型注册表（对齐 STRATEGY_REGISTRY） ──

BEHAVIOR_REGISTRY: Dict[str, dict] = {
    # ══ P55：counter 驱动型（4 种） ══
    "soft_interval": {
        "class": SoftStepBehavior,
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
        "class": SoftStepBehavior,
        "display_name": "累加软保底",
        "default_scope": "ssr",
        "params": {
            "start":     {"type": "int",   "display_name": "起始抽数",   "default": 74,  "min": 1},
            "increment": {"type": "float", "display_name": "每抽增量(%)", "default": 6.0, "min": 0.1},
        },
        "ui_params": ["start", "increment"],
    },
    "soft_step": {
        "class": SoftStepBehavior,
        "display_name": "分段软保底",
        "default_scope": "ssr",
        "params": {
            "deltas": {"type": "deltas", "display_name": "RLE 分段表", "default": ((73, 0.0), (17, 5.88))},
        },
        "ui_params": ["deltas"],
    },
    "hard": {
        "class": HardPityBehavior,
        "display_name": "硬保底",
        "default_scope": "ssr",
        "params": {
            "threshold": {"type": "int", "display_name": "保底抽数", "default": 90, "min": 1},
        },
        "ui_params": ["threshold"],
    },
    # ══ P56：事件驱动型（6 种——已实现） ══
    "rotating": {
        "class": RotatingBehavior,
        "display_name": "轮换保底",
        "default_scope": "ssr",
        "params": {},
    },
    "rotating_soft": {
        "class": RotatingSoftBehavior,
        "display_name": "轮换保底（带软保底）",
        "default_scope": "ssr",
        "params": {
            "start":     {"type": "int",   "display_name": "起始抽数",   "default": 74,  "min": 1},
            "increment": {"type": "float", "display_name": "每抽增量(%)", "default": 6.0, "min": 0.1},
        },
    },
    "targeted": {
        "class": TargetedBehavior,
        "display_name": "定向保底（定轨）",
        "default_scope": "ssr",
        "params": {
            "fate_threshold":         {"type": "int",   "display_name": "命定值阈值",     "default": 1,    "min": 0},
            "switch_allowed":         {"type": "bool",  "display_name": "允许中途切换",   "default": True},
            "switch_resets_progress": {"type": "bool",  "display_name": "切换后清零进度", "default": True},
        },
    },
    "rotating_cr": {
        "class": RotatingCRBehavior,
        "display_name": "轮换保底（递增概率）",
        "default_scope": "ssr",
        "params": {
            "cr_counter_threshold": {"type": "int",   "display_name": "CR 计数器阈值", "default": 3,  "min": 1},
            "cr_base_rate":         {"type": "float", "display_name": "基础递增率(%)",  "default": 5.0, "min": 0.0},
        },
    },
    "rotating_cr_soft": {
        "class": RotatingCRSoftBehavior,
        "display_name": "轮换保底·递增概率（带软保底）",
        "default_scope": "ssr",
        "params": {
            "cr_counter_threshold": {"type": "int",   "display_name": "CR 计数器阈值", "default": 3,  "min": 1},
            "cr_base_rate":         {"type": "float", "display_name": "基础递增率(%)",  "default": 5.0, "min": 0.0},
            "start":                {"type": "int",   "display_name": "起始抽数",      "default": 50, "min": 1},
            "increment":            {"type": "float", "display_name": "每抽增量(%)",    "default": 5.0, "min": 0.1},
        },
    },
    "targeted_soft": {
        "class": TargetedSoftBehavior,
        "display_name": "定向保底·定轨（带软保底）",
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
    """BEHAVIOR_REGISTRY 自检——验证所有条目 class 字段可导入。

    P55 阶段八集成：遍历注册表中所有条目，确认 counter 驱动型的 class 字段
    非 None 且确为 PityBehavior 子类。事件驱动型（P56 stub）跳过。
    在模块导入时自动执行一次——类型错误在导入阶段立即暴露。
    """
    for btype, entry in BEHAVIOR_REGISTRY.items():
        cls = entry.get("class")
        if cls is not None:
            if not isinstance(cls, type) or not issubclass(cls, PityBehavior):
                raise TypeError(
                    f"BEHAVIOR_REGISTRY['{btype}'].class={cls!r}——"
                    f"必须为 PityBehavior 子类"
                )


_validate_registry()


def create_behavior(pdef, state: 'PityState', **extra) -> 'PityBehavior':
    """工厂函数——从 PityDef（P55 扁平化字段）构造 behavior 实例。

    参数直接从 dataclass 字段读取；软保底语法糖（soft_start/soft_end/soft_increment）
    经 _expand_soft_to_deltas() 展开为 deltas。
    """
    entry = BEHAVIOR_REGISTRY[pdef.btype]
    cls = entry["class"]
    if cls is None:
        raise ValueError(
            f"Behavior type '{pdef.btype}' 尚未实现——"
            f"P56 将交付事件驱动型保底。"
        )

    # scope：优先取 PityDef.scope（用户配置），回退 registry 的 default_scope。
    # 2026-09-16 修正：此前只读 registry，PityDef.scope 被静默忽略，
    # 导致跨稀有度保底无法配置。P55 前的旧格式无 scope 字段，
    # getattr 返回 None 时自然回退。
    _default_scope = entry.get("default_scope", "ssr")
    scope = (getattr(pdef, 'scope', None) or _default_scope).lower()

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
    # 生命周期参数——LifecycleConfig 跨 type 共享
    lifecycle_kwargs = {}
    if getattr(pdef, 'deactivate_on_early_hit', False):
        lifecycle_kwargs['deactivate_on_early_hit'] = True
    if getattr(pdef, 'depends_on', None):
        lifecycle_kwargs['depends_on'] = pdef.depends_on
    if lifecycle_kwargs:
        params['lifecycle'] = LifecycleConfig(**lifecycle_kwargs)

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
    """按稀有度层级→type 优先级排序 behavior 列表。

    P55 §3.3：高稀有度先执行（rank 值小→优先级高），同稀有度内
    counter_soft → counter_hard → event_driven_soft → event_driven_hard。
    同优先级按 name 字母序（确定性）。
    """
    if rarity_rank is None:
        rarity_rank = {}
    def _sort_key(bh):
        scope = getattr(bh, '_scope', '')
        rank = rarity_rank.get(scope, 99)
        order = _BTYPE_ORDER.get(getattr(bh, '_btype', ''), 99)
        return (rank, order, getattr(bh, '_name', ''))
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
                 state: 'PityState' = None):
        self.pool_specs = pool_specs
        self._rarity_rank = rarity_rank or {}

        self.pity_defs = {p.name: p for p in pity_defs} if pity_defs else {}
        self._state = state

        # 从 PityDef 构造 behavior 实例
        self.behaviors: Dict[str, PityBehavior] = {}
        from .config_store import PityDef as _PityDef

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
            try:
                bh = create_behavior(pdef, self._state)
                self.behaviors[pdef.name] = bh
            except Exception:
                logger.warning(
                    f"PityEngine: 跳过 behavior '{pdef.name}' (type={pdef.btype})——"
                    f"构造失败",
                    exc_info=True,
                )

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
        # → _BTYPE_ORDER → name）只依赖 behavior 自身属性、与池无关，
        # 故子序即该池按同一排序键的结果。
        _order_index: Dict[str, int] = {
            getattr(bh, '_name', ''): _i for _i, bh in enumerate(ordered)
        }
        self._pool_order: Dict[str, List[str]] = {}
        for _pool_id, _spec in self.pool_specs.items():
            # 构造失败的 behavior 已在上方跳过、不进 self.behaviors，
            # 此处同样剔除（与 get_behaviors_for_pool 的 `bh is None` 守卫等价）。
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
        """解析 depends_on 关系 -> {source_name: [dependent_name, ...]}。"""
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
        """
        if state is self._state:
            return  # 同一对象——无需重绑定
        self._state = state
        for bh in self._behavior_list:
            if hasattr(bh, '_rebind_state'):
                bh._rebind_state(state)

    def get_probabilities(self, pool_id: str, state: PityState,
                          base_probabilities: Dict[str, float]) -> Dict[str, float]:
        """查询保底调整后的概率分布。

        P75（ISSUE-122）：首行 rebind state 至传入参数（带重绑副作用），随后以只读
        语义查询——「查询不写计数」仍成立，但不再是 P55 归档定义的无副作用纯查询。
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
        ctx = PityContext(draw=draw_info, current=base_probabilities.copy(), state=state)

        # 只读查询——对每个池关联 behavior 调度
        for pname, bh in self._behaviors_for_pool(pool_id):
            new_probs = bh.before_draw(ctx, readonly=True)
            if new_probs is not None:
                ctx.current = new_probs

        return ctx.current

    def before_draw(self, pool_id: str, state: PityState,
                    base_probabilities: Dict[str, float]) -> Dict[str, float]:
        """抽前调度：仅对当前池关联的 behavior 执行 before_draw。"""
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
        ctx = PityContext(draw=draw_info, current=base_probabilities.copy(), state=state)

        # 按池过滤调度
        for pname, bh in self._behaviors_for_pool(pool_id):
            new_probs = bh.before_draw(ctx)
            if new_probs is not None:
                ctx.current = new_probs

        return ctx.current

    def after_draw(self, pool_id: str, state: PityState, reward_id: str):
        """抽后调度：仅对当前池关联的 behavior 执行 after_draw。"""
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
        ctx = PityContext(draw=draw_info, current={}, state=state)

        # 按池过滤调度 + P56 声明式依赖传播
        for pname, bh in self._behaviors_for_pool(pool_id):
            bh.after_draw(ctx)
            if bh.did_fire(ctx):
                for dep_name in self._activation_graph.get(bh._name, []):
                    state.set(dep_name, "_active", True)

    def _infer_rarity(self, reward_id: str, spec: PoolPitySpec) -> str:
        """从 reward_id 推断稀有度（大小写归一化）。

        与 `pool.infer_rarity_from_spec` 是同一条规则的两处实现（本方法喂**状态**
        路径：`DrawInfo.reward_rarity` → `_should_reset` / `_is_trigger_rarity`；
        那份喂**概率**路径）。2026-10-09 起两者都退化为「扫 scope_cards」——原先
        本方法特有的「先查 ssr_ids」那一级与那份特有的两级回退一并删除，它们都是
        为绕开 worst_impact 那张写错名字的表而存在的。

        **两者必须保持同答**，守卫见
        `tests/core/test_pity_integration.py::TestRarityInferenceConsistency`；
        P64 的 S8 会删除 pool.py 那份（其概率路径消费者消失），届时只剩本方法。
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


