"""P69 §1.10b：ParamDescriptor 边界条件测试（PD-01~PD-09）。"""
import pytest
from gacha_simulator.core.param_descriptor import (
    FloatParam, IntParam, BoolParam, StrParam,
    StringListParam, PoolIntMapParam,
    ListParam, DictParam, PARAM_TYPE_MAP,
)


class TestFloatParam:
    def test_min_equals_max_valid_value_passes(self):
        """PD-01: min=max=0 且值为唯一合法值时应通过。"""
        p = FloatParam('t', '阈值', default=0.0, min_val=0.0, max_val=0.0)
        assert p.validate(0.0) == 0.0

    def test_min_equals_max_invalid_value_raises(self):
        """PD-02: min=max=0 且值超出边界时应拒绝。"""
        p = FloatParam('t', '阈值', default=0.0, min_val=0.0, max_val=0.0)
        with pytest.raises(ValueError):
            p.validate(0.1)

    def test_validate_converts_int_to_float(self):
        p = FloatParam('t', '阈值', default=0.0)
        assert p.validate(42) == 42.0

    def test_validate_rejects_non_numeric(self):
        p = FloatParam('t', '阈值')
        with pytest.raises(ValueError):
            p.validate('abc')


class TestIntParam:
    def test_negative_default_valid(self):
        """PD-03: min_val 为负是合法用例（如 -1 表示「无限制」）。"""
        p = IntParam('c', '数量', default=-1, min_val=-1)
        assert p.validate(-1) == -1

    def test_negative_below_min_raises(self):
        """PD-04: 负数值超出 min_val 范围应拒绝。"""
        p = IntParam('c', '数量', default=-1, min_val=-1)
        with pytest.raises(ValueError):
            p.validate(-5)

    def test_validate_rejects_float_with_fraction(self):
        p = IntParam('c', '数量')
        with pytest.raises(ValueError):
            p.validate(3.5)

    def test_validate_accepts_float_whole_number(self):
        p = IntParam('c', '数量')
        assert p.validate(10.0) == 10


class TestBoolParam:
    def test_validate_accepts_bool(self):
        p = BoolParam('b', '开关')
        assert p.validate(True) is True
        assert p.validate(False) is False

    def test_validate_accepts_string_true(self):
        p = BoolParam('b', '开关')
        for s in ('true', 'True', 'TRUE', '1', 'yes', 'on'):
            assert p.validate(s) is True

    def test_validate_accepts_string_false(self):
        p = BoolParam('b', '开关')
        for s in ('false', 'False', 'FALSE', '0', 'no', 'off', ''):
            assert p.validate(s) is False


class TestStrParam:
    def test_validate_accepts_string(self):
        p = StrParam('s', '文本')
        assert p.validate('hello') == 'hello'

    def test_validate_rejects_non_string(self):
        p = StrParam('s', '文本')
        with pytest.raises(ValueError):
            p.validate(42)


class TestStringListParam:
    def test_validate_empty_list_passes(self):
        """PD-05: 空列表是合法输入。"""
        p = StringListParam('ids', 'ID列表', default=[])
        assert p.validate([]) == []

    def test_validate_parses_comma_string(self):
        p = StringListParam('ids', 'ID列表')
        assert p.validate('a, b, c') == ['a', 'b', 'c']

    def test_validate_parses_space_string(self):
        p = StringListParam('ids', 'ID列表')
        assert p.validate('a b c') == ['a', 'b', 'c']

    def test_validate_accepts_list(self):
        p = StringListParam('ids', 'ID列表')
        assert p.validate(['a', 'b']) == ['a', 'b']

    def test_validate_empty_list_roundtrip(self):
        """PD-06: 空列表在序列化往返中保持为空列表（str 表示 → 解析）。"""
        p = StringListParam('ids', 'ID列表')
        # 模拟 TOML/JSON 序列化往返——str 表示再解析回 list
        empty_cases = ['', ' ', ',', ' , ']
        for case in empty_cases:
            result = p.validate(case)
            assert result == [], f"输入 {case!r} 应返回 []，实际: {result}"
        # 直接传空列表也应保持空列表
        assert p.validate([]) == []


class TestPoolIntMapParam:
    def test_validate_empty_dict_passes(self):
        """PD-07: 空字典——「不设配额」的合法表示。"""
        p = PoolIntMapParam('q', '配额', default={})
        assert p.validate({}) == {}

    def test_validate_negative_value_raises(self):
        """PD-08: 负值条目应抛出 ValueError（严格校验）。"""
        p = PoolIntMapParam('q', '配额')
        with pytest.raises(ValueError):
            p.validate({'pool_a': -5})

    def test_validate_parses_json_string(self):
        p = PoolIntMapParam('q', '配额')
        result = p.validate('{"pool_a": 10, "pool_b": 20}')
        assert result == {'pool_a': 10, 'pool_b': 20}

    def test_validate_accepts_valid_dict(self):
        p = PoolIntMapParam('q', '配额')
        assert p.validate({'pool_a': 10}) == {'pool_a': 10}


class TestListParam:
    """P79 4b1：通用列表描述符（承载 consecutive_pool_target 的 pool_schedules）。"""

    def test_default_is_empty_list(self):
        assert ListParam('s', '调度表').validate([]) == []

    def test_accepts_list_tuple_set(self):
        p = ListParam('s', '调度表')
        assert p.validate([1, 2]) == [1, 2]
        assert p.validate((1, 2)) == [1, 2]
        assert sorted(p.validate({1, 2})) == [1, 2]

    def test_parses_json_string(self):
        p = ListParam('s', '调度表')
        assert p.validate('[1, 2]') == [1, 2]

    def test_rejects_non_list(self):
        with pytest.raises(ValueError):
            ListParam('s', '调度表').validate({'a': 1})

    def test_rejects_unparsable_string(self):
        with pytest.raises(ValueError):
            ListParam('s', '调度表').validate('not json')

    def test_element_type_checked_when_declared(self):
        p = ListParam('s', '调度表', element_type=str)
        assert p.validate(['a']) == ['a']
        with pytest.raises(ValueError):
            p.validate([1])

    def test_element_type_not_checked_when_absent(self):
        # 元素为任意结构（如 pool_schedules 的 [pool_id, start, end] 三元组）
        p = ListParam('s', '调度表')
        assert p.validate([['pool_a', 0, 10]]) == [['pool_a', 0, 10]]


class TestDictParam:
    """P79 4b1：通用字典描述符（承载 consecutive_pool_target 的 pool_targets）。"""

    def test_default_is_empty_dict(self):
        assert DictParam('t', '目标表').validate({}) == {}

    def test_accepts_dict_and_parses_json_string(self):
        p = DictParam('t', '目标表')
        assert p.validate({'a': 'b'}) == {'a': 'b'}
        assert p.validate('{"a": "b"}') == {'a': 'b'}

    def test_rejects_non_dict(self):
        with pytest.raises(ValueError):
            DictParam('t', '目标表').validate([1])

    def test_rejects_non_string_key(self):
        with pytest.raises(ValueError):
            DictParam('t', '目标表').validate({1: 'b'})

    def test_value_type_checked_when_declared(self):
        p = DictParam('t', '目标表', value_type=str)
        assert p.validate({'a': 'b'}) == {'a': 'b'}
        with pytest.raises(ValueError):
            p.validate({'a': 1})


class TestParamTypeMap:
    """P79 4b1：两个新描述符必须进入 PARAM_TYPE_MAP，否则渲染分派取不到类。"""

    def test_list_and_dict_registered(self):
        assert PARAM_TYPE_MAP['list'] is ListParam
        assert PARAM_TYPE_MAP['dict'] is DictParam
