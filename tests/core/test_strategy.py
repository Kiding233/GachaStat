import pytest

from gacha_simulator.core.strategy import (
    FixedCountStrategy, TargetHuntingStrategy, StrategyContext,
    DrawSegmentStrategy, PriorityChainStrategy, NoDrawStrategy, Strategy,
    STRATEGY_REGISTRY, create_strategy, next_event_wait,
)
from gacha_simulator.core.action import DrawAction, WaitAction
from gacha_simulator.core.state import GachaState
from gacha_simulator.core.stop_condition import FixedActionCountCondition
from gacha_simulator.core.target_card import TargetCardSet
from gacha_simulator.core.banner import Banner


def _make_ctx(state, pools, total_draws=0, stop_condition=None):
    # P61（Ph1a）：策略消费 ctx.banners——裸 Pool 经单池包装为 Banner 传入
    banners = [Banner(id=p.id, name=p.name, pools={'main': p}) for p in pools]
    return StrategyContext(
        state=state,
        current_pools=pools,
        all_pools=pools,
        future_schedules=[],
        target_cards=TargetCardSet([]),
        stop_condition=stop_condition or FixedActionCountCondition(100),
        total_draws=total_draws,
        banners=banners,
        all_banners=banners,
    )


def test_fixed_count_strategy():
    state = GachaState(resources={'draw_resource': 1000})
    strategy = FixedCountStrategy(count=10)
    pools = []

    ctx = _make_ctx(state, pools, total_draws=0)
    action = strategy.select_action(ctx)
    assert isinstance(action, WaitAction)

    # P79 1e：枯竭态不得返回零等待（WaitAction(0) 会让 real_time 冻结，
    # 时间型停止条件永远够不着）。无可用 banner 时取 86400。
    ctx2 = _make_ctx(state, pools, total_draws=10)
    action2 = strategy.select_action(ctx2)
    assert isinstance(action2, WaitAction)
    assert action2.duration > 0


def test_target_hunting_strategy():
    state = GachaState(resources={'draw_resource': 160})
    strategy = TargetHuntingStrategy(target_pool_ids=['standard'])
    from gacha_simulator.core.pool import Pool, Reward
    pools = [Pool('standard', 'Standard', {'draw_resource': 160}, [(Reward('r1', 'R1'), 1.0)])]

    ctx = _make_ctx(state, pools)
    action = strategy.select_action(ctx)
    assert isinstance(action, DrawAction)
    # P61（Ph1a）：策略返回 DrawAction(banner_id=...)，pool_id 仅供反查
    assert action.banner_id == 'standard'


# ── P79 阶段 1：策略枯竭态契约与 next_event_wait ──────────────────────

_BUILTIN_KEYS = [
    'smart', 'pool_quota', 'pity_reserve', 'stop_on_target',
    'fixed_count', 'target_hunting', 'no_draw', 'draw_target',
]
# 插件策略由 load_plugin_strategies 注册并参与默认运行；其内部组合
# PityReserveStrategy + DrawSegmentStrategy 横跨策略层与 building block 层
_PLUGIN_KEY = 'plugin/example_phased'


def _state(real_time=0.0, resources=None):
    st = GachaState(resources=resources if resources is not None else {'draw_resource': 0})
    st.real_time = real_time
    return st


def _ctx(banners=(), real_time=0.0, total_draws=0, resources=None):
    return StrategyContext(
        state=_state(real_time=real_time, resources=resources),
        current_pools=[], all_pools=[], future_schedules=[],
        target_cards=TargetCardSet([]),
        stop_condition=FixedActionCountCondition(100),
        total_draws=total_draws,
        banners=list(banners), all_banners=list(banners),
    )


def _exhausted_ctx(total_draws=10 ** 6):
    """枯竭态：无可用 banner（抽不动）+ 抽数远超任何 count 阈值。"""
    return _ctx(total_draws=total_draws)


def _dummy_pool():
    from gacha_simulator.core.pool import Pool, Reward
    return Pool('main', 'Main', {'draw_resource': 160}, [(Reward('r1', 'R1'), 1.0)])


def test_next_event_wait_returns_float_and_respects_cap():
    """8.2 next_event_wait：契约是 min(86400, 最近关闭时刻 - real_time)。"""
    # 无可用 banner → 上限
    assert next_event_wait(_exhausted_ctx()) == 86400.0
    # available_until 为 None → 上限
    assert next_event_wait(_ctx([Banner(id='b', name='b', pools={'main': _dummy_pool()})])) == 86400.0
    # 最近关闭时刻早于一天 → 取该差值
    b1 = Banner(id='b1', name='b1', pools={'main': _dummy_pool()}, available_until=7200.0)
    b2 = Banner(id='b2', name='b2', pools={'main': _dummy_pool()}, available_until=3600.0)
    assert next_event_wait(_ctx([b1, b2])) == 3600.0
    # 最近关闭时刻晚于一天 → 上限（86400 是硬上限，不得返回更大的值）
    b3 = Banner(id='b3', name='b3', pools={'main': _dummy_pool()}, available_until=200000.0)
    assert next_event_wait(_ctx([b3])) == 86400.0
    # 已过期 → 上限
    b4 = Banner(id='b4', name='b4', pools={'main': _dummy_pool()}, available_until=-100.0)
    assert next_event_wait(_ctx([b4])) == 86400.0
    # 返回类型必须是 float（不是 Action）——调用点负责包 WaitAction
    assert isinstance(next_event_wait(_exhausted_ctx()), float)


@pytest.mark.parametrize('key', _BUILTIN_KEYS + [_PLUGIN_KEY])
def test_strategy_exhausted_returns_time_advancing_wait(key):
    """8.2 策略契约：9 组策略（8 内置 + 插件）在枯竭态均返回 duration > 0。"""
    if key == _PLUGIN_KEY:
        from gacha_simulator.core.strategy_loader import load_plugin_strategies
        load_plugin_strategies()
    assert key in STRATEGY_REGISTRY, f'{key} 未注册'
    action = create_strategy(key, {}).select_action(_exhausted_ctx())
    # 先过 isinstance 再断言 duration：只断言 duration 属性会让「直接返回 float」
    # 的写法在 AttributeError 与断言失败之间表现不一致（运行期实为 ValueError）
    assert isinstance(action, WaitAction), f'{key} 枯竭态返回了 {type(action).__name__}'
    assert action.duration > 0, f'{key} 枯竭态返回零等待，real_time 会冻结'


def test_draw_segment_strategy_exhausted_fallback():
    """building block 兜底：全有界 segments 且抽数超出最后一档。"""
    seg = DrawSegmentStrategy([(0, 10, NoDrawStrategy())])
    action = seg.select_action(_exhausted_ctx(total_draws=100))
    assert isinstance(action, WaitAction)
    assert action.duration > 0


def test_priority_chain_strategy_exhausted_fallback():
    """building block 兜底：全部子策略返回 None。"""

    class _NoneStrategy(Strategy):
        _strategy_key = None

        @classmethod
        def description(cls) -> str:
            return '始终返回 None'

        def select_action(self, ctx):
            return None

    chain = PriorityChainStrategy([_NoneStrategy(), _NoneStrategy()])
    action = chain.select_action(_exhausted_ctx())
    assert isinstance(action, WaitAction)
    assert action.duration > 0
