"""P79 表达式子系统用例：tests/core/test_stop_condition_expr.py。

按计划 8.5 的落点，本文件承载：
- 4d2a：8.2「表达式解析器（合法）」「表达式解析器（非法）」两类用例，
  以及「树 ↔ 表达式互转」（往返部分）
- 4d3：8.2「引用完整性」的 core 纯函数部分
"""

import pytest

from gacha_simulator.core.stop_condition_expr import (
    StopConditionExprError,
    parse_stop_condition_expr,
    expr_ast_to_text,
    tree_to_conditions_and_expr,
    expr_to_tree,
)


# ── 表达式解析器（合法）────────────────────────────────────────────

def test_precedence_not_gt_and_gt_or():
    """not > and > or：`a or b and c` 等价 `a or (b and c)`。"""
    assert parse_stop_condition_expr('a or b and c') == \
        parse_stop_condition_expr('a or (b and c)')
    assert parse_stop_condition_expr('a and b or c') == \
        parse_stop_condition_expr('(a and b) or c')


def test_parentheses_override_precedence():
    assert parse_stop_condition_expr('(a or b) and c') == \
        ('and', ('or', ('id', 'a'), ('id', 'b')), ('id', 'c'))


def test_not_chains_and_nesting():
    assert parse_stop_condition_expr('not a') == ('not', ('id', 'a'))
    assert parse_stop_condition_expr('not not a') == \
        ('not', ('not', ('id', 'a')))
    assert parse_stop_condition_expr('not (a or b) and c') == \
        ('and', ('not', ('or', ('id', 'a'), ('id', 'b'))), ('id', 'c'))


def test_single_identifier_and_extra_whitespace():
    assert parse_stop_condition_expr('a') == ('id', 'a')
    assert parse_stop_condition_expr('  a   or\n b  ') == \
        ('or', ('id', 'a'), ('id', 'b'))


def test_known_ids_validation():
    assert parse_stop_condition_expr('a or b', known_ids={'a', 'b'}) == \
        ('or', ('id', 'a'), ('id', 'b'))
    with pytest.raises(StopConditionExprError):
        parse_stop_condition_expr('a or zz', known_ids={'a', 'b'})


# ── 表达式解析器（非法）：均须给出可读报错而非异常栈 ──────────────

@pytest.mark.parametrize('text', [
    '', '   ',              # 空表达式
    'a and', 'a and not',   # 运算符缺右操作数
    'and a', 'or a',        # 运算符缺左操作数
    '(a or b',              # 未闭合括号
    'a or b)',              # 多出右括号
    'a b',                  # 相邻标识符
    'a & b',                # 非法字符
])
def test_illegal_expressions_raise_readable_error(text):
    with pytest.raises(StopConditionExprError) as excinfo:
        parse_stop_condition_expr(text)
    message = str(excinfo.value)
    assert message, '错误消息不得为空'
    # 消息面向用户，不得含异常栈痕迹
    assert 'Traceback' not in message and 'line ' not in message


# ── 树 ↔ 表达式互转 ──────────────────────────────────────────────

_NESTED_TREE = {
    'mode': 'any',
    'conditions': [
        {'type': 'target_acquired', 'target_id': 'c1', 'quantity': 1},
        {'mode': 'all', 'conditions': [
            {'type': 'resource_threshold', 'resource': 'draw_resource',
             'operator': '<=', 'threshold': 0},
            {'mode': 'not', 'conditions': [
                {'type': 'target_acquired', 'target_id': 'c2', 'quantity': 1}]},
        ]},
    ],
}


def test_tree_to_conditions_and_expr_nested():
    conditions, expr = tree_to_conditions_and_expr(_NESTED_TREE)
    assert [c['id'] for c in conditions] == ['a', 'b', 'c']
    # and 优先级高于 or，故无需括号
    assert expr == 'a or b and not c'
    assert conditions[0]['type'] == 'target_acquired'


def test_round_trip_is_lossless():
    """树 → 表达式 → 树 无损（同运算符链被拉平，结合律等价）。"""
    conditions, expr = tree_to_conditions_and_expr(_NESTED_TREE)
    assert expr_to_tree(expr, conditions) == _NESTED_TREE


def test_flat_same_operator_tree_yields_or_chain():
    """「单层 + 全同运算符」→ a or b or c / a and b and c，供单选识别。"""
    flat_any = {'mode': 'any', 'conditions': [
        {'type': 'time_limit', 'max_time': 1.0},
        {'type': 'time_limit', 'max_time': 2.0},
        {'type': 'time_limit', 'max_time': 3.0},
    ]}
    conditions, expr = tree_to_conditions_and_expr(flat_any)
    assert expr == 'a or b or c'
    assert expr_to_tree(expr, conditions) == flat_any

    flat_all = {'mode': 'all', 'conditions': [
        {'type': 'time_limit', 'max_time': 1.0},
        {'type': 'time_limit', 'max_time': 2.0},
    ]}
    conditions, expr = tree_to_conditions_and_expr(flat_all)
    assert expr == 'a and b'
    assert expr_to_tree(expr, conditions) == flat_all


def test_not_node_maps_to_mode_not_single_child():
    """`not c` 映射为 mode='not' 的单子节点（非 type='not' 叶子）。"""
    tree = {'mode': 'not', 'conditions': [
        {'type': 'target_acquired', 'target_id': 'c1', 'quantity': 1}]}
    conditions, expr = tree_to_conditions_and_expr(tree)
    assert expr == 'not a'
    assert expr_to_tree(expr, conditions) == tree

    leaf = expr_to_tree('not a', conditions)
    assert leaf['mode'] == 'not'
    assert len(leaf['conditions']) == 1
    assert 'type' not in leaf


def test_empty_tree_and_empty_expression():
    assert tree_to_conditions_and_expr(None) == ([], '')
    assert expr_to_tree('', []) is None
    assert expr_to_tree('   ', []) is None


def test_expr_to_tree_rejects_dangling_id():
    conditions = [{'id': 'a', 'type': 'time_limit', 'max_time': 1.0}]
    with pytest.raises(StopConditionExprError):
        expr_to_tree('a or zz', conditions)


def test_ast_to_text_adds_only_necessary_parentheses():
    assert expr_ast_to_text(parse_stop_condition_expr('a or (b and c)')) == \
        'a or b and c'
    assert expr_ast_to_text(parse_stop_condition_expr('(a or b) and c')) == \
        '(a or b) and c'
    assert expr_ast_to_text(parse_stop_condition_expr('not (a or b)')) == \
        'not (a or b)'


# ── 4d3：引用完整性纯函数（8.2「引用完整性」core 部分）──────────────

def test_validate_config_expr_side():
    from gacha_simulator.core.stop_condition_expr import (
        validate_stop_condition_config as V,
    )

    conds = [{'id': 'a', 'type': 'time_limit', 'max_time': 1.0},
             {'id': 'b', 'type': 'time_limit', 'max_time': 2.0}]
    assert V(expr='a or not b', conditions=conds) == []
    assert V(expr='', conditions=conds) == []

    syntax = V(expr='a and (', conditions=conds)
    assert len(syntax) == 1 and '括号' in syntax[0]

    dangling = V(expr='a or zz', conditions=conds)
    assert len(dangling) == 1 and "'zz'" in dangling[0] and '已被删除' in dangling[0]


@pytest.mark.parametrize('tree,frag', [
    ({'type': 'no_such_type'}, '未知的停止条件类型'),
    ({'foo': 1}, '缺少 type 键'),
    ({'mode': 'not', 'conditions': [
        {'type': 'time_limit'}, {'type': 'time_limit'}]}, '恰带一个子节点'),
    ({'mode': 'any', 'conditions': []}, '不得为空'),
    ({'mode': 'xor', 'conditions': [{'type': 'time_limit'}]}, "mode 须为"),
    ({'mode': 'any', 'conditions': {'a': 1}}, '必须是数组'),
])
def test_validate_config_tree_side_rejects(tree, frag):
    from gacha_simulator.core.stop_condition_expr import (
        validate_stop_condition_config as V,
    )

    errors = V(tree=tree)
    assert errors and any(frag in e for e in errors)


def test_validate_config_tree_side_reports_shape_issues():
    """保存闸门（tree 分支）并入形态问题，且对 mode 缺 conditions 只报贴题的那条。

    该形态原先只报「叶子节点缺少 type 键」，指向错误的方向（真正缺的是
    conditions）；两条并报则冗余，故此时抑制泛化讯息。
    """
    from gacha_simulator.core.stop_condition_expr import (
        validate_stop_condition_config as V,
    )

    errors = V(tree={'mode': 'any'})
    assert len(errors) == 1, errors
    assert 'conditions' in errors[0]
    assert not any('缺少 type 键' in e for e in errors), '泛化讯息未抑制'

    unknown = V(tree={'type': 'fixed_action_count', 'count': 500})
    assert len(unknown) == 1, unknown
    assert 'count' in unknown[0] and 'max_actions' in unknown[0]


def test_validate_config_tree_side_accepts_nested():
    from gacha_simulator.core.stop_condition_expr import (
        validate_stop_condition_config as V,
    )

    tree = {'mode': 'any', 'conditions': [
        {'type': 'time_limit', 'max_time': 1.0},
        {'mode': 'not', 'conditions': [
            {'type': 'target_acquired', 'target_id': 'x', 'quantity': 1}]},
    ]}
    assert V(tree=tree) == []
    assert V(tree=None) == []


def test_validate_config_is_total():
    """全函数：任何输入都返回错误列表，不抛异常。"""
    from gacha_simulator.core.stop_condition_expr import (
        validate_stop_condition_config as V,
    )

    for bad in ('not a dict', 123, [], [1, 2]):
        assert isinstance(V(tree=bad), list)
    assert isinstance(V(expr=None, conditions=None), list)
