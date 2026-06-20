from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
import logging

logger = logging.getLogger(__name__)


# ── P60 新增：DrawInfo (frozen) + PityContext (可变载体) ──

@dataclass(frozen=True)
class DrawInfo:
    """抽卡上下文中不可变的部分——本次抽卡的静态事实。"""
    pool_id: str
    pool_instance_id: str
    reward_id: str
    reward_rarity: str
    is_featured: bool
    scope_cards: Mapping[str, tuple] = field(default_factory=dict)
    scope_slots: Mapping[str, tuple] = field(default_factory=dict)
    featured_slots: Mapping[str, tuple] = field(default_factory=dict)
    base_probabilities: Mapping[str, float] = field(default_factory=dict)
    rarity_rank: Mapping[str, int] = field(default_factory=dict)


@dataclass
class PityContext:
    """管道中流转的可变载体。"""
    draw: DrawInfo
    current: Dict[str, float]
    state: 'PityState'


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
    max_triggers: int = 0                         # 最多触发次数（0=无限）
    deactivate_on_early_hit: bool = False         # P56 扩展
    depends_on: Optional[str] = None              # P56 扩展


class PityBehavior(ABC):
    @abstractmethod
    def apply(self, counter_value: int, probabilities: Dict[str, float],
              extra: Dict[str, Any] = None) -> Dict[str, float]:
        pass

    def is_active(self, counter_value: int) -> bool:
        """该保底在给定计数器值下是否影响概率。子类应覆写此方法。"""
        return False


class SoftPityBehavior(PityBehavior):
    def __init__(self, start_at: int, end_at: int,
                 func_type: str = 'linear',
                 target_distribution: Dict[str, float] = None):
        self.start_at = start_at
        self.end_at = end_at
        self.func_type = func_type
        self.target_distribution = target_distribution or {}

    def is_active(self, counter_value: int) -> bool:
        return counter_value >= self.start_at

    def _progress(self, counter_value: int) -> float:
        if counter_value < self.start_at:
            return 0.0
        raw = (counter_value - self.start_at) / max(self.end_at - self.start_at, 1)
        raw = min(raw, 1.0)
        if self.func_type == 'exp':
            return raw * raw
        elif self.func_type == 'step':
            if raw < 0.33:
                return 0.0
            elif raw < 0.66:
                return 0.5
            else:
                return 1.0
        return raw

    def apply(self, counter_value: int, probabilities: Dict[str, float],
              extra: Dict[str, Any] = None) -> Dict[str, float]:
        progress = self._progress(counter_value)
        if progress <= 0:
            return probabilities.copy()

        resolved = self.target_distribution
        if extra and 'resolved_targets' in extra:
            resolved = extra['resolved_targets']

        if resolved:
            return self._apply_targeted(progress, probabilities, resolved)
        return self._apply_first(progress, probabilities)

    def _apply_targeted(self, progress: float,
                        probabilities: Dict[str, float],
                        resolved: Dict[str, float]) -> Dict[str, float]:
        present = {tid: w for tid, w in resolved.items() if tid in probabilities}
        if not present:
            return probabilities.copy()
        total_target_weight = sum(present.values())
        if total_target_weight <= 0:
            return probabilities.copy()

        current_target_prob = sum(
            probabilities.get(tid, 0.0)
            for tid in present
        )
        other_prob = 1.0 - current_target_prob
        new_target_prob = min(current_target_prob + progress * other_prob, 1.0)
        new_other_prob = 1.0 - new_target_prob
        scale = new_other_prob / other_prob if other_prob > 0 else 0

        result = {}
        for rid, prob in probabilities.items():
            if rid in present:
                w = present[rid] / total_target_weight
                result[rid] = new_target_prob * w
            else:
                result[rid] = prob * scale
        return result

    def _apply_first(self, progress: float,
                     probabilities: Dict[str, float]) -> Dict[str, float]:
        items = list(probabilities.items())
        if not items:
            return probabilities.copy()

        first_id, first_prob = items[0]
        other_prob = 1.0 - first_prob
        new_first_prob = min(first_prob + progress * other_prob, 1.0)
        new_other_prob = 1.0 - new_first_prob
        scale = new_other_prob / other_prob if other_prob > 0 else 0

        result = {}
        for rid, prob in probabilities.items():
            if rid == first_id:
                result[rid] = new_first_prob
            else:
                result[rid] = prob * scale
        return result


class HardPityBehavior(PityBehavior):
    def __init__(self, threshold: int,
                 target_distribution: Dict[str, float] = None):
        self.threshold = threshold
        self.target_distribution = target_distribution or {}

    def is_active(self, counter_value: int) -> bool:
        return counter_value >= self.threshold

    def apply(self, counter_value: int, probabilities: Dict[str, float],
              extra: Dict[str, Any] = None) -> Dict[str, float]:
        if counter_value < self.threshold:
            return probabilities.copy()

        resolved = self.target_distribution
        if extra and 'resolved_targets' in extra:
            resolved = extra['resolved_targets']

        if resolved:
            present = {tid: w for tid, w in resolved.items() if tid in probabilities}
            if not present:
                return probabilities.copy()
            total = sum(present.values())
            if total <= 0:
                return probabilities.copy()
            result = {k: 0.0 for k in probabilities}
            for tid, w in present.items():
                result[tid] = w / total
            return result

        result = {k: 0.0 for k in probabilities}
        if probabilities:
            result[list(probabilities.keys())[0]] = 1.0
        return result


# ── P60 新增：计数器驱动型保底基类 ──

class CounterBasedBehavior(PityBehavior, ABC):
    """计数器驱动型保底的通用生命周期。

    子类只需覆写 _compute_probabilities(ctx, counter) → Dict[str, float]。
    计数器管理（增/查/重置/触发上限/停用）由基类统一处理。
    """

    def __init__(self, name: str, state: 'PityState', scope: str,
                 reset: str = None, target_featured: bool = False,
                 lifecycle: 'LifecycleConfig' = None):
        self._name = name
        self._state = state
        self._scope = scope                      # 稀有度层级
        self._target_featured = target_featured
        self._reset = reset if reset is not None else scope
        # sentinel 模式——避免可变默认参数共享
        self._lifecycle = lifecycle if lifecycle is not None else LifecycleConfig()
        self._triggers = Counter(state, name, "triggers")
        self._active = Flag(state, name, "_active")
        if self._lifecycle.depends_on is None:
            self._active.set()

    @abstractmethod
    def _compute_probabilities(self, ctx: 'PityContext', counter: int) -> Dict[str, float]:
        """子类实现——给定上下文和当前计数器值，返回调整后概率分布。"""
        ...

    def _counter(self) -> 'Counter':
        return Counter(self._state, self._name, "counter")

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
        if self._lifecycle.max_triggers and self._triggers.value() >= self._lifecycle.max_triggers:
            self._active.clear()
            return
        self._counter().reset()
        self._triggers.incr()

    def _should_reset(self, ctx: 'PityContext') -> bool:
        if self._reset == "featured":
            return ctx.draw.is_featured
        return ctx.draw.reward_rarity == self._reset

    def did_fire(self, ctx: 'PityContext') -> bool:
        return self._should_reset(ctx)


# ── P60 新增：保底类型注册表（对齐 STRATEGY_REGISTRY） ──

BEHAVIOR_REGISTRY: Dict[str, dict] = {
    "soft_interval": {
        "class": None,                          # P55 剩余实现——占位
        "display_name": "区间软保底",
        "default_scope": "SSR",
        "params": {
            "start": {"type": "int", "display_name": "起始抽数", "default": 80, "min": 1},
            "end":   {"type": "int", "display_name": "结束抽数", "default": 90, "min": 1},
            "func":  {"type": "str", "display_name": "爬升函数", "default": "linear",
                       "options": ["linear", "exp", "step"]},
        },
    },
    "soft_additive": {
        "class": None,                          # P55 剩余实现——占位
        "display_name": "累加软保底",
        "default_scope": "SSR",
        "params": {
            "start":     {"type": "int",   "display_name": "起始抽数",   "default": 74,  "min": 1},
            "increment": {"type": "float", "display_name": "每抽增量(%)", "default": 6.0, "min": 0.1},
        },
    },
    "hard": {
        "class": None,                          # P55 剩余实现——占位
        "display_name": "硬保底",
        "default_scope": "SSR",
        "params": {
            "threshold": {"type": "int", "display_name": "保底抽数", "default": 90, "min": 1},
        },
    },
    "rotating": {
        "class": None,                          # P56 实现——stub
        "display_name": "轮换保底",
        "default_scope": "SSR",
        "params": {
            "initial_win_rate": {"type": "float", "display_name": "初始胜率(%)",  "default": 50.0, "min": 0.0, "max": 100.0},
            "loss_increment":   {"type": "float", "display_name": "歪后增量(%)",  "default": 50.0, "min": 0.0, "max": 100.0},
        },
    },
    "targeted": {
        "class": None,                          # P56 实现——stub
        "display_name": "定向保底（定轨）",
        "default_scope": "SSR",
        "params": {
            "initial_win_rate":       {"type": "float", "display_name": "初始胜率(%)",    "default": 50.0, "min": 0.0, "max": 100.0},
            "loss_increment":         {"type": "float", "display_name": "歪后增量(%)",    "default": 50.0, "min": 0.0, "max": 100.0},
            "fate_threshold":         {"type": "int",   "display_name": "命定值阈值",     "default": 1,    "min": 0},
            "switch_allowed":         {"type": "bool",  "display_name": "允许中途切换",   "default": True},
            "switch_resets_progress": {"type": "bool",  "display_name": "切换后清零进度", "default": True},
        },
    },
}


def create_behavior(pdef: 'PityDefParsed', state: 'PityState', **extra) -> 'PityBehavior':
    """工厂函数——从 PityDefParsed + BEHAVIOR_REGISTRY 构造 behavior 实例。

    scope 从 BEHAVIOR_REGISTRY 条目的 default_scope 读取（非 PityDefParsed，scope 是行为类型固有属性）。
    参数类型根据 registry 声明的 type 强制转换。
    """
    entry = BEHAVIOR_REGISTRY[pdef.btype]
    cls = entry["class"]
    if cls is None:
        raise ValueError(f"Behavior type '{pdef.btype}' 在 P60 中仅为 stub——"
                         f"完整实现由 P55 剩余/P56 交付。")

    # scope 从 registry 条目读取
    scope = entry.get("default_scope", "SSR")

    # 参数类型强制转换——将 pdef.params 的字符串值转为 registry 声明的类型
    typed_params = {}
    for pname, pvalue in pdef.params.items():
        param_meta = entry.get("params", {}).get(pname, {})
        ptype = param_meta.get("type", "str")
        if ptype == "int":
            typed_params[pname] = int(pvalue)
        elif ptype == "float":
            typed_params[pname] = float(pvalue)
        elif ptype == "bool":
            typed_params[pname] = pvalue.lower() in ("true", "1", "yes")
        else:
            typed_params[pname] = pvalue  # str —— 原样传递

    return cls(name=pdef.name, state=state, scope=scope, **typed_params)


@dataclass
class PityDefParsed:
    name: str
    btype: str
    params: Dict[str, str]
    target_distribution: Dict[str, float]
    reset_condition: str
    pools: str


@dataclass
class PoolPitySpec:
    pity_names: List[str]
    featured_ids: Set[str] = field(default_factory=set)
    ssr_ids: Set[str] = field(default_factory=set)
    resolved_targets: Dict[str, Dict[str, float]] = field(default_factory=dict)


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
        elif "counters" in d:
            # ── P60：旧格式自动升级 ──
            for name, val in d["counters"].items():
                ps.data[name] = {"counter": val}
        return ps


class PityEngine:
    """保底引擎——P60 退化为纯调度器。所有业务逻辑由 behavior 自行管理。"""

    def __init__(self, pool_specs: Dict[str, PoolPitySpec],
                 pity_defs: Dict[str, PityDefParsed],
                 behaviors: Dict[str, PityBehavior],
                 rarity_rank: Dict[str, int] = None):
        self.pool_specs = pool_specs
        self.pity_defs = pity_defs
        self.behaviors = behaviors                    # 保留旧接口兼容
        self._state = None                            # 由 before_draw/after_draw 注入
        self._rarity_rank = rarity_rank or {}

        # _behavior_list 仅作为注册表，调度时按池过滤
        self._behavior_list: List[PityBehavior] = list(behaviors.values())

    # ── 辅助：按池过滤 behavior ──

    def _behaviors_for_pool(self, pool_id: str):
        """返回当前池关联的 behavior 实例列表——防止跨池计数器污染。"""
        spec = self.pool_specs.get(pool_id)
        if spec is None:
            return []
        result = []
        for pname in spec.pity_names:
            bh = self.behaviors.get(pname)
            if bh is not None:
                result.append((pname, bh))
        return result

    # ── 策略层查询接口（保留旧方法签名兼容） ──

    def get_probabilities(self, pool_id: str, state: PityState,
                          base_probabilities: Dict[str, float]) -> Dict[str, float]:
        """查询保底调整后的概率分布，不修改保底计数器。"""
        spec = self.pool_specs.get(pool_id)
        if spec is None:
            return base_probabilities.copy()

        draw_info = DrawInfo(
            pool_id=pool_id,
            pool_instance_id=pool_id,
            reward_id="",
            reward_rarity="",
            is_featured=False,
            scope_cards={},
            scope_slots={},
            featured_slots={},
            base_probabilities=base_probabilities,
            rarity_rank=self._rarity_rank,
        )
        ctx = PityContext(draw=draw_info, current=base_probabilities.copy(), state=state)

        # 只读查询——对每个池关联 behavior 调度，跳过计数器递增
        for pname, bh in self._behaviors_for_pool(pool_id):
            try:
                new_probs = bh.before_draw(ctx, readonly=True)
                if new_probs is not None:
                    ctx.current = new_probs
            except AttributeError:
                # 🔴 P55 迁移后删除：旧 behavior（SoftPityBehavior/HardPityBehavior）仅有 apply()，
                # 无 before_draw()。P55 阶段五/六将其改为 CounterBasedBehavior 子类后，此桥接不再触发。
                cv = state.get(pname, "counter", 0)
                extra = {}
                resolved = spec.resolved_targets.get(pname)
                if resolved:
                    extra['resolved_targets'] = resolved
                ctx.current = bh.apply(cv, ctx.current, extra if extra else None)

        return ctx.current

    def before_draw(self, pool_id: str, state: PityState,
                    base_probabilities: Dict[str, float]) -> Dict[str, float]:
        """抽前调度：仅对当前池关联的 behavior 执行 before_draw。"""
        self._state = state
        spec = self.pool_specs.get(pool_id)
        if spec is None:
            return base_probabilities.copy()

        draw_info = DrawInfo(
            pool_id=pool_id,
            pool_instance_id=pool_id,
            reward_id="",
            reward_rarity="",
            is_featured=False,
            scope_cards={},
            scope_slots={},
            featured_slots={},
            base_probabilities=base_probabilities,
            rarity_rank=self._rarity_rank,
        )
        ctx = PityContext(draw=draw_info, current=base_probabilities.copy(), state=state)

        # 按池过滤调度 + 旧接口桥接
        for pname, bh in self._behaviors_for_pool(pool_id):
            try:
                new_probs = bh.before_draw(ctx)
                if new_probs is not None:
                    ctx.current = new_probs
            except AttributeError:
                # 🔴 P55 迁移后删除：旧 behavior 仅有 apply()——P55 阶段五/六改为 CounterBasedBehavior 子类后不再触发
                cv = state.get(pname, "counter", 0)
                state.incr(pname, "counter")
                extra = {}
                resolved = spec.resolved_targets.get(pname)
                if resolved:
                    extra['resolved_targets'] = resolved
                ctx.current = bh.apply(cv + 1, ctx.current, extra if extra else None)

        return ctx.current

    def after_draw(self, pool_id: str, state: PityState, reward_id: str):
        """抽后调度：仅对当前池关联的 behavior 执行 after_draw。"""
        spec = self.pool_specs.get(pool_id)
        if spec is None:
            return

        is_featured = reward_id in spec.featured_ids
        reward_rarity = self._infer_rarity(reward_id, spec)

        draw_info = DrawInfo(
            pool_id=pool_id,
            pool_instance_id=pool_id,
            reward_id=reward_id,
            reward_rarity=reward_rarity,
            is_featured=is_featured,
            scope_cards={},
            scope_slots={},
            featured_slots={},
            base_probabilities={},
            rarity_rank=self._rarity_rank,
        )
        ctx = PityContext(draw=draw_info, current={}, state=state)

        # 按池过滤调度 + 旧接口桥接
        for pname, bh in self._behaviors_for_pool(pool_id):
            try:
                bh.after_draw(ctx)
            except AttributeError:
                # 🔴 P55 迁移后删除：旧 behavior 无 after_draw()——P55 阶段五/六改为 CounterBasedBehavior 子类后不再触发
                pdef = self.pity_defs.get(pname)
                if pdef is None:
                    continue
                is_ssr = reward_id in spec.ssr_ids
                if pdef.reset_condition == 'any_ssr' and is_ssr:
                    state.set(pname, "counter", 0)
                elif pdef.reset_condition == 'featured_ssr' and is_featured:
                    state.set(pname, "counter", 0)
                # 'never' → 无操作

    def _infer_rarity(self, reward_id: str, spec: PoolPitySpec) -> str:
        """从 reward_id 推断稀有度。"""
        if reward_id in spec.ssr_ids:
            return "SSR"
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
        return self._state.get(name, "_active", True) if self._state else True

    def get_state_summary(self) -> Dict[str, Dict[str, Any]]:
        if self._state is None:
            return {}
        return {name: dict(ns) for name, ns in self._state.data.items()}


def _parse_target_distribution(text: str) -> Dict[str, float]:
    result = {}
    if not text:
        return result
    for part in text.split(','):
        part = part.strip()
        if ':' in part:
            cid, w = part.rsplit(':', 1)
            try:
                result[cid.strip()] = float(w.strip())
            except ValueError:
                result[cid.strip()] = 1.0
        else:
            result[part.strip()] = 1.0
    return result


