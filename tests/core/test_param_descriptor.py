"""P69 §1.10b：ParamDescriptor 边界条件测试（PD-01~PD-09）。"""
import pytest
from gacha_simulator.core.param_descriptor import (
    FloatParam, IntParam, BoolParam, StrParam,
    StringListParam, PoolIntMapParam,
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
