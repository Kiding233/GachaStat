"""P79 §8.5 落点：`ctx.stop_condition` 为含硬边界的复合对象。

计划 §5.3 的「策略侧可见性变更」：装配后 `StrategyContext.stop_condition` 由
「用户条件或其 `None`」变为「含硬边界的 `CompositeStopCondition` 包装」——这是
**插件作者可见**的语义变更（策略可能读该字段），故须有独立断言固化。

断言取的是策略**实际看到的**那个对象，而非 `build_strategy_context` 的回声
（后者只会证实参数被透传，证不了装配层的包装行为）。
"""

import pytest

from gacha_simulator.core.action import WaitAction
from gacha_simulator.core.stop_condition import (
    AllPoolsEndCondition, CompositeStopCondition, FixedActionCountCondition,
)
from gacha_simulator.core.strategy import Strategy

CONFIG = 'gacha_simulator/config/config.toml'
SEED = 42


class _RecordingStrategy(Strategy):
    """记录每一轮实际看到的 ctx.stop_condition。"""

    def __init__(self):
        self.seen = []

    @classmethod
    def description(cls) -> str:
        return '记录策略实际看到的 ctx（P79 审计用例）'

    def select_action(self, ctx):
        self.seen.append(ctx.stop_condition)
        return WaitAction(duration=86400)


@pytest.fixture
def env_and_targets():
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.service.batch_simulator import (
        SimulationEnvBuilder, _build_target_set,
    )

    store = load_toml(CONFIG)
    env = SimulationEnvBuilder.from_config_store(store)
    specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    return env, _build_target_set(env.card_defs, specs)


def _run_with_recorder(monkeypatch, env, target_set):
    from gacha_simulator.service.batch_simulator import _run_single
    import gacha_simulator.service.batch_simulator as bs

    recorder = _RecordingStrategy()
    monkeypatch.setattr(bs, 'create_strategy', lambda key, params=None: recorder)
    _run_single(env, target_set, SEED, env.initial_resources)
    assert recorder.seen, '策略一次都没被调用'
    return recorder


def test_ctx_stop_condition_wraps_user_condition_with_hard_boundary(
        monkeypatch, env_and_targets):
    """用户条件在位时：策略看到的是 any(用户条件, 硬边界)。"""
    env, target_set = env_and_targets
    env.stop_condition = FixedActionCountCondition(3)
    recorder = _run_with_recorder(monkeypatch, env, target_set)

    seen = recorder.seen[0]
    assert isinstance(seen, CompositeStopCondition), (
        f'策略看到的是 {type(seen).__name__}，应为含硬边界的复合对象')
    assert seen.mode == 'any'
    kinds = [type(c) for c in seen.conditions]
    assert FixedActionCountCondition in kinds, '用户条件不在复合对象内'
    boundaries = [c for c in seen.conditions if isinstance(c, AllPoolsEndCondition)]
    assert boundaries and boundaries[0].end_time == env.end_time


def test_ctx_stop_condition_degrades_to_bare_boundary_when_no_user_condition(
        monkeypatch, env_and_targets):
    """用户条件为 None 时（默认配置）：策略看到的是单一硬边界。"""
    env, target_set = env_and_targets
    env.stop_condition = None
    recorder = _run_with_recorder(monkeypatch, env, target_set)

    seen = recorder.seen[0]
    assert isinstance(seen, AllPoolsEndCondition), type(seen).__name__
    assert not isinstance(seen, CompositeStopCondition)
    assert seen.end_time == env.end_time


def test_ctx_stop_condition_is_stable_across_rounds(monkeypatch, env_and_targets):
    """同一模拟内多轮的 ctx.stop_condition 是同一对象（每轮重建 ctx，不重建条件）。"""
    env, target_set = env_and_targets
    env.stop_condition = FixedActionCountCondition(3)
    recorder = _run_with_recorder(monkeypatch, env, target_set)

    assert len(recorder.seen) > 1, '用例前提：应为多轮模拟'
    assert all(c is recorder.seen[0] for c in recorder.seen)
