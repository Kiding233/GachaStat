"""P79 2e：引擎硬边界的组装与停止条件对象的约束。

组装点在 _run_single（service/batch_simulator.py）：

- env.stop_condition 为 None → 退化为单一 AllPoolsEndCondition(env.end_time)
- 非 None → CompositeStopCondition([用户条件, 硬边界], mode='any')

故「any 语义」的两条分支由本文件的两条对照用例固化：用户条件可满足时按其
收口（早于硬边界），不可满足时仍由硬边界在 env.end_time 收口。

from_config_store 的接线用例（含 getattr 容忍断言）不在此处，依赖 4a1 字段 /
4a3 解析 / 4b2b2 树分派三者，落子任务 4a5、同为该文件。
"""
import copy
import pickle

from gacha_simulator.core.config_toml import load_toml
from gacha_simulator.core.state import GachaState
from gacha_simulator.core.stop_condition import (
    AllPoolsEndCondition, CompositeStopCondition, FixedActionCountCondition,
    ResourceThresholdCondition, TargetAcquiredCondition,
)
from gacha_simulator.service.batch_simulator import (
    SimulationEnvBuilder, run_batch_parallel,
)

CONFIG = 'gacha_simulator/config/config.toml'
# 主循环对等待不做端点夹取（real_time += action.duration），越界后由下一轮循环
# 顶部的硬边界收口，故 final_time 可上溢至多一个动作步长。矩阵内最大步长为
# next_event_wait 的 86400 硬上限（默认配置 168 天恰被其整除，故实际恰好相等；
# 该整除是巧合，断言仍按容差口径写）。
MAX_STEP = 86400.0


def _run(stop_condition, strategy_key='smart', seed=42):
    store = load_toml(CONFIG)
    env = SimulationEnvBuilder.from_config_store(store)
    specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    env.stop_condition = stop_condition
    batch = run_batch_parallel(
        env=env, target_specs=specs, initial_resources=env.initial_resources,
        num_simulations=1, max_workers=1, seed=seed, strategy_key=strategy_key,
    )
    return env, batch.results[0]


def test_hard_boundary_when_no_user_condition():
    """env.stop_condition 为 None → 单一硬边界，在 env.end_time 收口。"""
    env, r = _run(None)
    # 必须抵达时间线终点（缺硬边界时 final_time 会冻结在 0），且上溢不超过一步
    assert env.end_time <= r.final_time <= env.end_time + MAX_STEP


def test_unreachable_user_condition_still_closes_at_hard_boundary():
    """any 语义之一：用户条件不可满足时，由硬边界在 env.end_time 收口。

    改造前该组合（smart + 不可达条件）会冲到 99605 天并污染 _obtainable 系列
    GDR 的分母（计划 2.2 / 2.4 实测）。
    """
    env, ref = _run(None)
    env2, r = _run(TargetAcquiredCondition('不存在的卡', quantity=1))
    assert r.final_time <= env2.end_time + MAX_STEP
    assert r.final_time >= env2.end_time
    # 不可达条件不改变任何结果——与「仅硬边界」逐字段一致
    assert r.total_draws == ref.total_draws
    assert r.total_waits == ref.total_waits


def test_satisfiable_user_condition_closes_before_hard_boundary():
    """any 语义之二：用户条件可满足时按其收口，早于硬边界。"""
    env, r = _run(FixedActionCountCondition(20))
    assert r.total_draws == 20
    assert r.final_time < env.end_time


def test_stop_condition_objects_are_picklable():
    """条件对象须可 pickle——env 经 MPPool initializer pickle 到子进程。

    max_workers > 1 时若不可 pickle，异常会被 _wk_run_single 的
    traceback.print_exc() 吞掉，只体现为 n_failed 上涨。
    """
    nested = CompositeStopCondition(
        [AllPoolsEndCondition(1000.0), TargetAcquiredCondition('c', quantity=2)],
        mode='all')
    cond = CompositeStopCondition([FixedActionCountCondition(200), nested], mode='any')

    env = SimulationEnvBuilder.from_config_store(load_toml(CONFIG))
    env.stop_condition = cond
    restored = pickle.loads(pickle.dumps(env))

    assert isinstance(restored.stop_condition, CompositeStopCondition)
    assert restored.stop_condition.conditions[0].max_actions == 200
    assert isinstance(restored.stop_condition.conditions[1], CompositeStopCondition)
    assert restored.stop_condition.conditions[1].mode == 'all'


def test_stop_condition_has_no_cross_round_state():
    """同一条件对象连续两次 check 不改变内部状态。

    这是 _run_single 对 env.stop_condition「直接引用不深拷贝」的交换条件：新增
    条件类型不得携带跨轮累积状态（复合节点与现有叶子条件均为无状态判据）。
    """
    state = GachaState(resources={'draw_resource': 0})
    cond = CompositeStopCondition(
        [ResourceThresholdCondition('draw_resource', 0, '<='),
         FixedActionCountCondition(5)],
        mode='any')

    snapshot = pickle.dumps(cond)
    assert cond.check(state, []) is True
    assert cond.check(state, []) is True
    assert pickle.dumps(cond) == snapshot


def test_pickled_condition_survives_deepcopy_of_env():
    """基线/搜索模式用 copy.deepcopy(env) 置空条件——副本不影响原对象。"""
    env = SimulationEnvBuilder.from_config_store(load_toml(CONFIG))
    env.stop_condition = FixedActionCountCondition(20)

    clone = copy.deepcopy(env)
    clone.stop_condition = None

    assert env.stop_condition is not None
    assert isinstance(env.stop_condition, FixedActionCountCondition)
    assert clone.stop_condition is None
