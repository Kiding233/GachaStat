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


# ══════════════════════════════════════════════════════════════════
# 5d：断言 2（按策略 max_step）+ 非默认 end_time 行 + 断言 4
# ══════════════════════════════════════════════════════════════════

# 断言 2 的容差按**策略分别取值**，不得一刀切：
# - helper 系（next_event_wait 的 86400 硬上限）与 no_draw 的固定 86400
# - target_hunting 是固定 3600 的粗粒度等待，不纳入 helper 化
MAX_STEP_BY_STRATEGY = {
    'smart': 86400.0, 'pool_quota': 86400.0, 'pity_reserve': 86400.0,
    'stop_on_target': 86400.0, 'fixed_count': 86400.0, 'no_draw': 86400.0,
    'draw_target': 86400.0, 'plugin/example_phased': 86400.0,
    'target_hunting': 3600.0,
}


@pytest.mark.parametrize('strategy_key', STRATEGY_KEYS)
def test_matrix_final_time_within_one_step(env_and_targets, strategy_key):
    """断言 2：`final_time` 必须抵达时间线终点，且上溢不超过一个动作步长。

    主循环对等待不做端点夹取（`real_time += action.duration`），越界后由下一轮循环
    顶部的硬边界收口，故可上溢至多一个步长。
    """
    assert set(MAX_STEP_BY_STRATEGY) == set(STRATEGY_KEYS)
    env, _ = env_and_targets
    # 不可达条件 → 只能由硬边界收口
    condition = TargetAcquiredCondition(_MISSING_CARD, quantity=1)
    result = run_matrix_case(env_and_targets, strategy_key, condition)

    step = MAX_STEP_BY_STRATEGY[strategy_key]
    assert result.final_time >= env.end_time, '未抵达时间线终点（硬边界未收口）'
    assert result.final_time <= env.end_time + step, (
        f'{strategy_key}: final_time={result.final_time} 上溢超过一个步长 {step}')


def test_matrix_non_default_end_time_bounds(env_and_targets):
    """非默认 end_time 的矩阵行（断言 2 的容差口径必须在此验证）。

    默认配置 168 天 = 14515200 秒**同时被 86400 与 3600 整除**，于是
    `final_time == env.end_time` 恰好成立——这个巧合会掩盖步长取值错误。故在
    非整除的 end_time 上复验：helper 系仍恰好落在终点（其步长自适应到最近关闭
    时刻），target_hunting 则会真实上溢（固定 3600 步长）。
    """
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.service.batch_simulator import (
        SimulationEnvBuilder, _build_target_set, _run_single,
    )

    store = load_toml(CONFIG)
    finite = [b for b in store.banner.banners if b.available_until is not None]
    latest = max(finite, key=lambda b: b.available_until)
    base = float(latest.available_until)
    latest.available_until = base + 12345.0        # 不被 86400 / 3600 整除

    env = SimulationEnvBuilder.from_config_store(store)
    assert env.end_time == base + 12345.0
    specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    target_set = _build_target_set(env.card_defs, specs)

    for strategy_key in ('smart', 'target_hunting'):
        env.strategy_key = strategy_key
        env.strategy_params = {}
        env.stop_condition = None                  # 仅硬边界
        result = _run_single(env, target_set, SEED, env.initial_resources)
        step = MAX_STEP_BY_STRATEGY[strategy_key]
        assert env.end_time <= result.final_time <= env.end_time + step, \
            f'{strategy_key}: final_time={result.final_time} end_time={env.end_time}'

    # target_hunting 用固定 3600 步长，非整除时确实会越过终点（容差被真实用到）
    env.strategy_key = 'target_hunting'
    env.strategy_params = {}
    env.stop_condition = None
    hunting = _run_single(env, target_set, SEED, env.initial_resources)
    assert hunting.final_time > env.end_time


def test_matrix_warning_expectations(env_and_targets):
    """断言 4：正常组合不产生告警；零进度组合命中且告警含策略 key 与动作类型。"""
    from gacha_simulator.service.batch_simulator import _run_single

    env, target_set = env_and_targets

    # 正常组合：不应命中
    env.strategy_key = 'smart'
    env.strategy_params = {}
    env.stop_condition = AllPoolsEndCondition(env.end_time)
    normal = _run_single(env, target_set, SEED, env.initial_resources)
    assert normal.warnings == [], normal.warnings

    # 零进度组合（资源耗尽后空转）：应命中，且文案含策略 key 与最后动作类型
    env.strategy_key = 'fixed_count'
    env.strategy_params = {'count': 50000}
    env.stop_condition = AllPoolsEndCondition(env.end_time)
    stalled = _run_single(env, target_set, SEED, env.initial_resources)
    assert stalled.warnings, '零进度组合未被兜住'
    assert 'fixed_count' in stalled.warnings[0]
    assert 'DrawAction' in stalled.warnings[0]
    assert stalled.iterations < COARSE_ITERATION_CAP


# ══════════════════════════════════════════════════════════════════
# 5e：8.4 性能闸门
# ══════════════════════════════════════════════════════════════════

PERF_UNIVERSAL_CAP = 1000       # 通用「失控」判据
PERF_WALL_CLOCK_SECONDS = 0.5   # 单次模拟耗时阈值（修复前 1.04s / 1.78s；修复后约 0.02s）


def _hunting_cap(end_time, step=3600.0, slack=10):
    """粗粒度等待策略的单列上界：ceil(end_time / 步长) + 常数。"""
    import math
    return int(math.ceil(end_time / step)) + slack


@pytest.mark.parametrize('strategy_key,params', [
    ('fixed_count', {'count': 100}),
    ('stop_on_target', {'stop_on_featured': True}),
])
def test_perf_within_universal_cap(env_and_targets, strategy_key, params):
    """断言：迭代数不超过 1000 且耗时不超过阈值。

    这是防止 10 万轮空转复现的直接闸门——修复前两者均为 100000 轮、
    耗时 1.04s / 1.78s；修复后约 100 量级、约 0.02s。
    """
    import time

    from gacha_simulator.service.batch_simulator import _run_single

    env, target_set = env_and_targets
    env.strategy_key = strategy_key
    env.strategy_params = dict(params)
    env.stop_condition = None

    started = time.time()
    result = _run_single(env, target_set, SEED, env.initial_resources)
    elapsed = time.time() - started

    assert result.iterations <= PERF_UNIVERSAL_CAP, (
        f'{strategy_key}: iterations={result.iterations} 超过通用上界')
    assert elapsed < PERF_WALL_CLOCK_SECONDS, (
        f'{strategy_key}: 耗时 {elapsed:.2f}s 超过阈值 {PERF_WALL_CLOCK_SECONDS}s')


def test_perf_target_hunting_single_column_cap(env_and_targets):
    """粗粒度等待策略单列上界——不能用 1000 一把尺子量它。

    target_hunting 在全部目标池不可负担时固定返回 WaitAction(duration=3600)，
    跨越默认 168 天需 4032 轮，是**合法的多轮**而非失控。
    """
    from gacha_simulator.service.batch_simulator import _run_single

    env, target_set = env_and_targets
    env.strategy_key = 'target_hunting'
    env.strategy_params = {}
    env.stop_condition = None
    result = _run_single(env, target_set, SEED, env.initial_resources)

    cap = _hunting_cap(env.end_time)
    assert result.iterations <= cap, f'iterations={result.iterations} 超过单列上界 {cap}'
    # 该值由 §2.1 的原始实测固化（4032 轮）
    assert result.iterations == 4032


def test_perf_criterion_distinguishes_legit_multiround_from_spin(env_and_targets):
    """判据须能区分「粒度导致的合法多轮」与「10 万轮空转」。

    同一份配置下：
    - target_hunting 的 4032 轮**超过**通用上界 1000，但合法（步长 3600）
    - fixed_count(50000) 的资源耗尽空转被兜底截断，远低于 100000，且带告警
    故闸门必须按策略分别设界 + 用告警区分「兜底收口」与「正常结束」。
    """
    from gacha_simulator.service.batch_simulator import _run_single

    env, target_set = env_and_targets

    env.strategy_key = 'target_hunting'
    env.strategy_params = {}
    env.stop_condition = None
    hunting = _run_single(env, target_set, SEED, env.initial_resources)
    assert hunting.iterations > PERF_UNIVERSAL_CAP          # 合法的多轮
    assert hunting.warnings == []                           # 且不是靠兜底收口的

    env.strategy_key = 'fixed_count'
    env.strategy_params = {'count': 50000}
    env.stop_condition = None
    spin = _run_single(env, target_set, SEED, env.initial_resources)
    assert spin.iterations < 100000                         # 不再烧满预算
    assert spin.warnings and '零进度兜底' in spin.warnings[0]  # 由兜底收口
