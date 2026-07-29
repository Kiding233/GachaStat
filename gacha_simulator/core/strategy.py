from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional, Dict, Set, TYPE_CHECKING
import logging

from .action import Action
from .schedule import PoolSchedule
from .target_card import TargetCardSet

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .state import GachaState
    from .pool import Pool
    from .stop_condition import StopCondition
    from .pity import PityEngine, PityState
    from .param_descriptor import ParamDescriptor


# ── 策略注册表元数据 ──────────────────────────────────────────────


@dataclass
class StrategyMeta:
    """策略注册表条目——类定义即注册，消除分离维护。"""

    key: str
    display_name: str
    description: str
    cls: Optional[type] = None
    params: List['ParamDescriptor'] = field(default_factory=list)
    internal: bool = False          # 内置隐藏策略——不出现于任何 GUI 列表
    disabled: bool = False          # 用户手动禁用的插件
    plugin_path: Optional[str] = None
    _invalid_state: Optional[str] = None  # 加载失败的插件占位


# 全局策略注册表——模块级别，装饰器副作用填充
STRATEGY_REGISTRY: Dict[str, StrategyMeta] = {}


def register_strategy(
    key: str,
    display_name: str,
    *,
    params: Optional[List['ParamDescriptor']] = None,
    internal: bool = False,
):
    """装饰器——将策略类注册到 STRATEGY_REGISTRY。

    副作用：
    1. 向 STRATEGY_REGISTRY 写入 StrategyMeta
    2. 向被装饰类注入 _strategy_key 类属性

    用法:
        @register_strategy('smart', '按需追卡')
        class SmartStrategy(Strategy): ...

        @register_strategy('pity_reserve', '保底预留',
            params=[FloatParam('pity_threshold_pct', '保底概率阈值(%)', default=80.0)])
        class PityReserveStrategy(Strategy): ...
    """
    def decorator(cls):
        meta = StrategyMeta(
            key=key,
            display_name=display_name,
            description=cls.description(),
            cls=cls,
            params=params or [],
            internal=internal,
        )
        STRATEGY_REGISTRY[key] = meta
        cls._strategy_key = key
        return cls

    return decorator


@dataclass
class StrategyContext:
    state: 'GachaState'
    current_pools: List['Pool']
    all_pools: List['Pool']
    future_schedules: List[PoolSchedule]
    target_cards: TargetCardSet
    stop_condition: 'StopCondition'
    _pity_engine: Optional['PityEngine'] = field(default=None, repr=False)
    _pity_state: Optional['PityState'] = field(default=None, repr=False)
    pool_draw_counts: Dict[str, int] = field(default_factory=dict)
    total_draws: int = 0

    @property                                                          # P60：从 state 实时读取
    def acquired(self) -> Dict[str, int]:
        """卡牌持有量单一真相源。"""
        return self.state.acquired
    # P69 阶段 2：上下文契约完善——所有新字段提供默认值，现有策略不经修改即可运行
    future_resource_gains: Dict[str, float] = field(default_factory=dict)
    """未来资源收入聚合——按资源ID聚合 schedule 中尚未到达的条目（day > real_time）。"""
    inter_pool_pity_links: Dict[str, List[str]] = field(default_factory=dict)
    """跨池保底继承关系——key=池子ID, value=与该池共享保底计数器的池子ID列表。"""
    time_discount: float = 1.0
    """时间偏好因子——1.0=无折扣，<1.0=偏好早期收益，>1.0=偏好后期收益。"""
    last_draw_pity_triggered: bool = False
    ssr_ids: Set[str] = field(default_factory=set)
    _pity_cache: Dict[str, Dict[str, float]] = field(default_factory=dict, repr=False)

    def get_pity_probabilities(self, pool_id: str) -> Dict[str, float]:
        if self._pity_engine is None:
            return {}
        cached = self._pity_cache.get(pool_id)
        if cached is not None:
            return cached
        pool = next((p for p in self.current_pools if p.id == pool_id), None)
        if pool is None or pool.is_exchange:
            return {}
        probs = {r.id: p for r, p in pool.rewards}
        result = self._pity_engine.get_probabilities(pool_id, self._pity_state, probs)
        self._pity_cache[pool_id] = result
        return result


class Strategy(ABC):
    lookahead: Optional[float] = None

    @classmethod
    def name(cls) -> str:
        return cls.__name__

    @classmethod
    @abstractmethod
    def description(cls) -> str:
        return ""

    @abstractmethod
    def select_action(self, ctx: StrategyContext) -> Action:
        pass


# ── 内置策略——通过 import 触发 @register_strategy 装饰器副作用 ──
# 策略类定义拆分至 strategies/builtin/*.py，与插件策略统一目录结构。
# 框架核心（Strategy / StrategyContext / register_strategy / create_strategy）保留在本文件。

from gacha_simulator.strategies.builtin.smart import SmartStrategy  # noqa: E402, F401
from gacha_simulator.strategies.builtin.pool_quota import PoolQuotaStrategy  # noqa: E402, F401
from gacha_simulator.strategies.builtin.pity_reserve import PityReserveStrategy  # noqa: E402, F401
from gacha_simulator.strategies.builtin.stop_on_target import StopOnTargetStrategy  # noqa: E402, F401
from gacha_simulator.strategies.builtin.fixed_count import FixedCountStrategy  # noqa: E402, F401
from gacha_simulator.strategies.builtin.target_hunting import TargetHuntingStrategy  # noqa: E402, F401
from gacha_simulator.strategies.builtin.no_draw import NoDrawStrategy  # noqa: E402, F401
from gacha_simulator.strategies.builtin.draw_target import DrawTargetStrategy  # noqa: E402, F401


class CompositeStrategy(Strategy):
    """[DEPRECATED] 请使用 PriorityChainStrategy 替代。

    P69 阶段 3：CompositeStrategy 保留但内部委托给 PriorityChainStrategy，
    并在实例化时发出 DeprecationWarning。
    """

    def __init__(self, strategies: List[Strategy], mode: str = 'first_valid'):
        import warnings
        warnings.warn(
            "CompositeStrategy 已废弃，请使用 PriorityChainStrategy 替代",
            DeprecationWarning, stacklevel=2,
        )
        if mode not in ('first_valid',):
            raise ValueError(
                f"CompositeStrategy mode must be 'first_valid', got '{mode}'"
            )
        self.strategies = strategies
        self.mode = mode

    @classmethod
    def description(cls) -> str:
        return "组合多个策略"

    def select_action(self, ctx: StrategyContext) -> Action:
        for strategy in self.strategies:
            action = strategy.select_action(ctx)
            if self.mode == 'first_valid' and action is not None:
                return action
        from .action import WaitAction
        return WaitAction(duration=0)


# ── 复合策略 Building Block（P69 阶段 3） ─────────────────────────
# 纯 Python API——不进入 TOML 序列化，不进入 GUI。
# 供 coding agent 在插件策略中作为子策略组合使用。


class DrawSegmentStrategy(Strategy):
    """按累计抽数分段委托——不同抽数区间使用不同策略。

    segments: List[tuple[int, Optional[int], Strategy]]
        三元组 (start, end, strategy):
        - start: 起始抽数（含）
        - end: 结束抽数（不含），None 表示到模拟结束
        - strategy: 该区间使用的策略实例
    """

    _strategy_key = None  # 哨兵——非注册策略，无 key

    def __init__(self, segments: List[tuple]):
        self.segments = segments

    @classmethod
    def description(cls) -> str:
        return f"分段策略（{0}段）"

    def select_action(self, ctx: StrategyContext) -> Action:
        for start, end, strategy in self.segments:
            if ctx.total_draws >= start and (end is None or ctx.total_draws < end):
                return strategy.select_action(ctx)
        from .action import WaitAction
        return WaitAction(duration=0)


class PriorityChainStrategy(Strategy):
    """优先级降级链——依次尝试子策略，返回第一个有效 Action。

    strategies: List[Strategy]
        按优先级排列的策略列表。每个策略依次调用 select_action()，
        第一个返回非 None 且非 WaitAction(duration=0) 的结果被采纳。
        若全部返回 WaitAction(0)，则返回最后一个。
    """

    _strategy_key = None  # 哨兵——非注册策略，无 key

    def __init__(self, strategies: List[Strategy]):
        self.strategies = strategies

    @classmethod
    def description(cls) -> str:
        return f"优先级降级链（{0}个子策略）"

    def select_action(self, ctx: StrategyContext) -> Action:
        for strategy in self.strategies:
            action = strategy.select_action(ctx)
            if action is not None:
                return action
        from .action import WaitAction
        return WaitAction(duration=0)


class ConditionalStrategy(Strategy):
    """条件分支策略——根据 lambda 选择子策略。

    condition: Callable[[StrategyContext], bool]
        条件函数，接收 ctx 返回 True/False。
    true_s: Strategy
        条件为 True 时使用的策略。
    false_s: Strategy
        条件为 False 时使用的策略。
    """

    _strategy_key = None  # 哨兵——非注册策略，无 key

    def __init__(self, condition, true_s: Strategy, false_s: Strategy):
        self.condition = condition
        self.true_s = true_s
        self.false_s = false_s

    @classmethod
    def description(cls) -> str:
        return "条件分支策略"

    def select_action(self, ctx: StrategyContext) -> Action:
        if self.condition(ctx):
            return self.true_s.select_action(ctx)
        return self.false_s.select_action(ctx)


# ── 策略工厂（数据驱动） ──────────────────────────────────────────


def create_strategy(key: str, params: Optional[Dict[str, Any]] = None) -> Strategy:
    """数据驱动工厂——查 StrategyMeta → 守卫 → 合并默认值 → 校验 → 实例化。

    Args:
        key: 策略 key（如 'smart'、'pity_reserve'、'plugin/my_adaptive'）。
        params: 用户传入的参数 dict，覆盖 ParamDescriptor.default。

    Returns:
        策略实例。

    Raises:
        ValueError: key 不存在、插件加载失败、参数校验失败。
    """
    # 1. 查注册表
    meta = STRATEGY_REGISTRY.get(key)
    if meta is None:
        raise ValueError(f"Unknown strategy: {key}")

    # 2. _invalid_state 守卫——插件加载失败
    if meta._invalid_state is not None:
        raise ValueError(
            f"Cannot create strategy '{key}': plugin failed to load — "
            f"{meta._invalid_state}"
        )

    # 3. internal + cls=None 守卫
    if meta.internal and meta.cls is None:
        raise ValueError(
            f"Cannot create internal strategy '{key}': no instantiable class"
        )

    cls = meta.cls
    if cls is None:
        raise ValueError(
            f"STRATEGY_REGISTRY['{key}'].cls is None — "
            f"strategy cannot be instantiated"
        )

    user_params = params or {}

    # 4. 合并默认值 + 校验
    resolved: Dict[str, Any] = {}
    for pdesc in meta.params:
        raw = user_params.get(pdesc.key, pdesc.default)
        resolved[pdesc.key] = pdesc.validate(raw)

    # 5. 实例化
    return cls(**resolved)


def strategy_type_to_key(display_name: str) -> str:
    """显示名 → key：遍历注册表反向查找 StrategyMeta.display_name。"""
    for key, entry in STRATEGY_REGISTRY.items():
        if entry.display_name == display_name:
            return key
    logger.warning(
        "Unknown strategy display_name '%s', falling back to 'smart'",
        display_name,
    )
    return 'smart'


def strategy_key_to_type(key: str) -> str:
    """key → 显示名：查 StrategyMeta.display_name。"""
    entry = STRATEGY_REGISTRY.get(key)
    return entry.display_name if entry else '按需追卡'


# ── 注册表自检 ────────────────────────────────────────────────────


def _validate_registry() -> None:
    """STRATEGY_REGISTRY 自检——模块导入时自动执行。

    验证内容：
    (a) 每个非 internal、_invalid_state 为空的 entry，cls 非 None。
    (b) 每个非 internal、_invalid_state 为空的 entry，cls 为 Strategy 子类。
    (c) 每个 entry.params 中所有 ParamDescriptor.key 无重复。
    (d) 所有 entry.key 唯一。
    (e) internal 与 disabled 正交——不存在同时为 True 的条目。

    失败行为：
    - (a)/(b) 违反 → TypeError（cls 类型不满足约束）。
    - (c)/(d)/(e) 违反 → AssertionError（注册表数据不一致）。
    - 抛出异常会阻止模块导入，在应用启动阶段立即暴露问题。
    """
    all_keys: set = set()
    for key, meta in STRATEGY_REGISTRY.items():
        # (d) key 唯一性
        assert key not in all_keys, f"STRATEGY_REGISTRY key 重复: {key!r}"
        all_keys.add(key)

        # (e) internal 与 disabled 正交
        assert not (meta.internal and meta.disabled), (
            f"STRATEGY_REGISTRY['{key}']: internal 与 disabled 不能同时为 True——"
            f"internal 策略永不对外暴露，disabled 语义不适用"
        )

        # (a) cls 非 None 检查
        if meta.cls is None:
            if not meta.internal and meta._invalid_state is None:
                raise TypeError(
                    f"STRATEGY_REGISTRY['{key}'].cls 为 None——"
                    f"非 internal 且无 _invalid_state 的策略必须提供可实例化的类"
                )
            continue  # cls=None 且合法，跳过后续 cls 检查

        # (b) cls 类型检查
        if not isinstance(meta.cls, type):
            raise TypeError(
                f"STRATEGY_REGISTRY['{key}'].cls={meta.cls!r}——必须为类（type）"
            )
        if not meta.internal and meta._invalid_state is None:
            if not issubclass(meta.cls, Strategy):
                raise TypeError(
                    f"STRATEGY_REGISTRY['{key}'].cls={meta.cls.__name__}——"
                    f"必须为 Strategy 子类"
                )

        # (c) params 参数名无重复
        if meta.params:
            param_keys = [p.key for p in meta.params]
            if len(param_keys) != len(set(param_keys)):
                from collections import Counter
                dupes = [k for k, v in Counter(param_keys).items() if v > 1]
                raise AssertionError(
                    f"STRATEGY_REGISTRY['{key}'].params 存在重复 key: {dupes}"
                )


_validate_registry()
