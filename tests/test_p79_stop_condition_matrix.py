"""P79 §8.1 参数化回归矩阵（策略 × 停止条件）。

把诊断所用的手工矩阵固化为参数化测试，使「哪些组合会失控」成为永久闸门而非
一次性排查。**本文件是全计划核心论点的唯一永久闸门**。

按计划 8.1 的落点分工：

- ``5c1``（本项）：矩阵骨架 + 参数化 + 断言 1 / 3
- ``5d``：断言 2 的按策略 ``max_step`` 分设 + 非默认 ``end_time`` 矩阵行 + 断言 4
- ``5e``：8.4 性能闸门（1000 通用上界 + ``target_hunting`` 约 4100 单列）
- ``5c2a`` / ``5c2b``：断言 5 落 tests/test_config_toml.py、断言 6 落
  tests/gui/test_config_panel_p79.py（**不在本文件**）

断言 1 的上界在本项取**粗上界**（10000，足以拦住 10 万轮级失控），
按策略的精确校准归 ``5d``。
"""

import pytest

from gacha_simulator.core.state import GachaState
from gacha_simulator.core.stop_condition import (
    AllPoolsEndCondition, CompositeStopCondition, FixedActionCountCondition,
    LastDrawCardCondition, NotCondition, ResourceThresholdCondition,
    TargetAcquiredCondition,
)

CONFIG = 'gacha_simulator/config/config.toml'
SEED = 42
# 粗上界：足以拦住「烧满 max_iterations = 100000」这一类失控；
# 按策略的精确上界（1000 通用 / target_hunting 约 4100）由 5d / 5e 固化
COARSE_ITERATION_CAP = 10000

STRATEGY_KEYS = [
    'smart', 'pool_quota', 'pity_reserve', 'stop_on_target',
    'fixed_count', 'target_hunting', 'no_draw', 'draw_target',
    'plugin/example_phased',
]

_MISSING_CARD = '不存在的卡'


def build_stop_conditions(end_time):
    """8.1 维度表的 10 类停止条件（含空/复合/嵌套/纯否定）。"""
    return {
        'none': None,
        'all_pools_end_zero': AllPoolsEndCondition(0.0),
        'all_pools_end_default': AllPoolsEndCondition(end_time),
        'fixed_action_count': FixedActionCountCondition(200),
        'target_unreachable': TargetAcquiredCondition(_MISSING_CARD, quantity=1),
        'last_draw_unreachable': LastDrawCardCondition(_MISSING_CARD),
        'resource_unreachable': ResourceThresholdCondition(
            'draw_resource', -1e9, '<='),
        # all 复合：抽满 5000 次与资源耗尽同时成立（实际由硬边界收口）
        'composite_all': CompositeStopCondition([
            FixedActionCountCondition(5000),
            ResourceThresholdCondition('draw_resource', 0, '<=')], mode='all'),
        # 嵌套 any(A, all(Y, not B))：A 在 20 次动作后成立，Y 永不成立、not B 恒真，
        # 故 all(Y, not B) 恒假——只有 A 这条支路能收口
        'nested': CompositeStopCondition([
            FixedActionCountCondition(20),
            CompositeStopCondition([
                ResourceThresholdCondition('draw_resource', 1e12, '>='),
                NotCondition(TargetAcquiredCondition(_MISSING_CARD, quantity=1))],
                mode='all')], mode='any'),
        # 纯否定：not target_acquired(不可得卡) 恒真 → 第 0 轮即收口
        'pure_not': NotCondition(TargetAcquiredCondition(_MISSING_CARD, quantity=1)),
    }


@pytest.fixture(scope='module')
def env_and_targets():
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.core.strategy_loader import load_plugin_strategies
    from gacha_simulator.service.batch_simulator import (
        SimulationEnvBuilder, _build_target_set,
    )

    load_plugin_strategies()
    store = load_toml(CONFIG)
    env = SimulationEnvBuilder.from_config_store(store)
    specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    return env, _build_target_set(env.card_defs, specs)


def run_matrix_case(env_and_targets, strategy_key, condition):
    """同一 env 上跑一个组合（_run_single 每次深拷贝 banner 隔离状态）。"""
    from gacha_simulator.service.batch_simulator import _run_single

    env, target_set = env_and_targets
    env.strategy_key = strategy_key
    env.strategy_params = {}
    env.stop_condition = condition
    return _run_single(env, target_set, SEED, env.initial_resources)


@pytest.mark.parametrize('strategy_key', STRATEGY_KEYS)
@pytest.mark.parametrize('condition_key', list(build_stop_conditions(0.0).keys()))
def test_matrix_iterations_bounded(env_and_targets, strategy_key, condition_key):
    """断言 1：迭代数不超过上界（以 CompactResult.iterations 为准）。

    现状下 total_draws / total_waits 对类型 3 完全不增长，不能替代本字段。
    """
    env, _ = env_and_targets
    condition = build_stop_conditions(env.end_time)[condition_key]
    result = run_matrix_case(env_and_targets, strategy_key, condition)

    assert result is not None, f'{strategy_key} × {condition_key} 模拟失败'
    assert result.iterations <= COARSE_ITERATION_CAP, (
        f'{strategy_key} × {condition_key}: iterations={result.iterations} '
        f'超过粗上界 {COARSE_ITERATION_CAP}')
    assert result.warnings == [] or result.iterations < COARSE_ITERATION_CAP


@pytest.mark.parametrize('strategy_key', STRATEGY_KEYS)
@pytest.mark.parametrize('condition_key', list(build_stop_conditions(0.0).keys()))
def test_matrix_waits_and_draws_scale(env_and_targets, strategy_key, condition_key):
    """断言 3：`total_waits` 与 `total_draws` 量级合理。"""
    env, _ = env_and_targets
    condition = build_stop_conditions(env.end_time)[condition_key]
    result = run_matrix_case(env_and_targets, strategy_key, condition)

    # 一次都没抽却攒出五位数等待 → 只可能是空转（每轮都在原地打转）
    assert not (result.total_draws == 0 and result.total_waits >= 10000), (
        f'{strategy_key} × {condition_key}: total_draws=0 但 '
        f'total_waits={result.total_waits}')
    assert result.total_waits <= result.iterations
    assert result.total_draws <= result.iterations


def test_matrix_covers_all_dimensions(env_and_targets):
    """矩阵两维度的取值个数与 8.1 表一致（防漏组合的元断言）。"""
    env, _ = env_and_targets
    assert len(STRATEGY_KEYS) == 9          # 8 内置 + plugin/example_phased
    assert len(build_stop_conditions(env.end_time)) == 10
    state = GachaState(resources={'draw_resource': 0})
    # 纯否定条件在「不可得卡 + 空历史」下恒真，是 8.1 表里的边界形态
    assert build_stop_conditions(env.end_time)['pure_not'].check(state, []) is True
