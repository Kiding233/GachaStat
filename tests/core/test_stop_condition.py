import pytest

from gacha_simulator.core.stop_condition import (
    FixedActionCountCondition, ResourceThresholdCondition,
    TargetAcquiredCondition, CompositeStopCondition, AllPoolsEndCondition,
    NotCondition, create_stop_condition,
)
from gacha_simulator.core.state import GachaState


def test_fixed_action_count():
    cond = FixedActionCountCondition(max_actions=10)
    state = GachaState()
    assert cond.check(state, []) is False
    assert cond.check(state, [None] * 10) is True


def test_resource_threshold():
    cond = ResourceThresholdCondition('draw_resource', 100, '<=')
    state = GachaState(resources={'draw_resource': 50})
    assert cond.check(state, []) is True
    state.resources['draw_resource'] = 200
    assert cond.check(state, []) is False


def test_target_acquired():
    cond = TargetAcquiredCondition('character_a', quantity=2)
    state = GachaState()
    from gacha_simulator.core.info_vector import InfoVector
    history = [
        InfoVector('draw', 'character_a', 'p1', action_index=0, session_id='s1'),
        InfoVector('draw', 'character_b', 'p1', action_index=1, session_id='s1'),
    ]
    assert cond.check(state, history) is False
    history.append(InfoVector('draw', 'character_a', 'p1', action_index=2, session_id='s1'))
    assert cond.check(state, history) is True


def test_composite_any():
    cond1 = FixedActionCountCondition(5)
    cond2 = ResourceThresholdCondition('draw_resource', 0, '<=')
    composite = CompositeStopCondition([cond1, cond2], mode='any')
    state = GachaState(resources={'draw_resource': 0})
    assert composite.check(state, []) is True


# ── P79 4b2b2：递归条件树求值（8.2「递归条件树求值」整行）────────────

def test_not_condition_negates_child():
    state = GachaState(resources={'draw_resource': 0})
    inner = ResourceThresholdCondition('draw_resource', 0, '<=')
    assert inner.check(state, []) is True
    assert NotCondition(inner).check(state, []) is False
    # description 必须实现——CompositeStopCondition.description 会逐个调用子节点
    assert '非(' in NotCondition(inner).description()


def test_create_stop_condition_empty_tree_returns_none():
    """空树规范化：None / 空字典 → None（= 仅引擎硬边界收口）。"""
    assert create_stop_condition(None) is None
    assert create_stop_condition({}) is None


def test_create_stop_condition_leaf_filters_type_key():
    """叶子表带 type 键时构造不抛 TypeError（4b2b2 的键白名单过滤）。"""
    cond = create_stop_condition({'type': 'fixed_action_count', 'max_actions': 3})
    assert isinstance(cond, FixedActionCountCondition)
    assert cond.max_actions == 3

    # TOML 往返可能残留 mode——一并剔除
    cond2 = create_stop_condition(
        {'type': 'all_pools_end', 'end_time': 123.0, 'mode': 'any'})
    assert isinstance(cond2, AllPoolsEndCondition)
    assert cond2.end_time == 123.0


def test_create_stop_condition_leaf_defaults_from_descriptors():
    """叶子缺省参数由 List[ParamDescriptor] 的 default 补齐。"""
    cond = create_stop_condition({'type': 'fixed_action_count'})
    assert cond.max_actions == 100
    cond2 = create_stop_condition({'type': 'consecutive_pool_target'})
    assert cond2.pool_schedules == [] and cond2.pool_targets == {}


def test_create_stop_condition_recursive_tree_and_evaluation():
    """任意深度嵌套：树构造 + check 结果正确。"""
    state = GachaState(resources={'draw_resource': 10})
    tree = {
        'mode': 'any',
        'conditions': [
            {'type': 'target_acquired', 'target_id': 'x', 'quantity': 1},
            {'mode': 'all', 'conditions': [
                {'type': 'resource_threshold', 'resource': 'draw_resource',
                 'operator': '<=', 'threshold': 100},
                {'mode': 'not', 'conditions': [
                    {'type': 'target_acquired', 'target_id': 'y', 'quantity': 1}]},
            ]},
        ],
    }
    cond = create_stop_condition(tree)
    assert isinstance(cond, CompositeStopCondition) and cond.mode == 'any'
    inner = cond.conditions[1]
    assert isinstance(inner, CompositeStopCondition) and inner.mode == 'all'
    assert isinstance(inner.conditions[1], NotCondition)
    # A 未达成；Y 成立（10 <= 100）；not B 成立（y 未持有）→ any 为真
    assert cond.check(state, []) is True


def test_create_stop_condition_conditions_present_skips_registry():
    """判别键：conditions 在场即不查 registry——该节点自带的 type 被忽略。"""
    cond = create_stop_condition({
        'mode': 'any',
        'type': 'no_such_condition_type',
        'conditions': [{'type': 'fixed_action_count', 'max_actions': 1}],
    })
    assert isinstance(cond, CompositeStopCondition)


def test_create_stop_condition_unknown_type_raises():
    """叶子形态下未知 type 仍抛 ValueError。"""
    with pytest.raises(ValueError):
        create_stop_condition({'type': 'no_such_condition_type'})


def test_create_stop_condition_not_requires_exactly_one_child():
    """否定节点恰带一个子节点——多子节点不得静默取首个。"""
    with pytest.raises(ValueError):
        create_stop_condition({'mode': 'not', 'conditions': [
            {'type': 'fixed_action_count'}, {'type': 'time_limit'}]})
    ok = create_stop_condition({'mode': 'not', 'conditions': [
        {'type': 'fixed_action_count', 'max_actions': 1}]})
    assert isinstance(ok, NotCondition)


def test_create_stop_condition_rejects_malformed_nodes():
    with pytest.raises(ValueError):
        create_stop_condition({'mode': 'xor', 'conditions': []})
    with pytest.raises(ValueError):
        create_stop_condition({'foo': 1})            # 非空但既无 conditions 也无 type
    with pytest.raises(ValueError):
        create_stop_condition({'mode': 'any', 'conditions': {'a': 1}})
