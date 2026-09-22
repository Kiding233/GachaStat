"""T1：`Plan` 的因子展开与 `plan.json` 输入契约。

对应 §3.1 的输入契约三条与 §3.9 T1 的「Plan 因子展开」「plan.json 缺字段取默认、
未知键与非法值报错」。
"""

import json

import pytest

from benchmarks.perf.plan import PLAN_FIELD_NAMES, Plan, PlanGrid


class TestFactorExpansion:
    def test_cartesian_product(self, make_plan):
        plans = PlanGrid(base=make_plan(), factors={'n': [100, 1000], 'workers': [2, 4]}).expand()
        assert sorted((p.n, p.workers) for p in plans) == [(100, 2), (100, 4), (1000, 2), (1000, 4)]

    def test_dedup(self, make_plan):
        """重复取值去重——`n: [100, 1000, 100]` 的 3x2 应得 4 条而非 6 条。"""
        plans = PlanGrid(base=make_plan(), factors={'n': [100, 1000, 100], 'workers': [2, 4]}).expand()
        assert len(plans) == 4

    def test_order_follows_declaration(self, make_plan):
        plans = PlanGrid(base=make_plan(), factors={'n': [100, 1000]}).expand()
        assert [p.n for p in plans] == [100, 1000]

    def test_empty_factors_yields_base(self, make_plan):
        base = make_plan()
        assert [p.canonical() for p in PlanGrid(base=base, factors={}).expand()] == [base.canonical()]

    def test_unknown_factor_field_rejected(self, make_plan):
        with pytest.raises(ValueError, match='未知字段'):
            PlanGrid(base=make_plan(), factors={'nope': [1]}).expand()

    def test_empty_factor_values_rejected(self, make_plan):
        with pytest.raises(ValueError, match='为空'):
            PlanGrid(base=make_plan(), factors={'n': []}).expand()

    def test_non_sequence_factor_rejected(self, make_plan):
        with pytest.raises(ValueError, match='必须是序列'):
            PlanGrid(base=make_plan(), factors={'n': 1}).expand()

    def test_each_cell_is_validated(self, make_plan):
        """因子把 `n` 推出安全协议上限时，该格就地拒绝而非被静默纳入扫描。"""
        with pytest.raises(ValueError, match='规则 1'):
            PlanGrid(base=make_plan(n=100), factors={'n': [100, 5000]}).expand()

    def test_plan_is_hashable(self, make_plan):
        assert len({make_plan(), make_plan()}) == 1


class TestPlanJsonContract:
    def test_round_trip(self, make_plan):
        plan = make_plan(collector=True, profile_enabled=True, profile_dir='/tmp/p',
                         profile_skip=0, profile_count=500, note='hi')
        assert Plan.from_dict(plan.to_dict()).canonical() == plan.canonical()

    def test_round_trip_through_json_text(self, make_plan):
        plan = make_plan()
        text = json.dumps(plan.to_dict(), ensure_ascii=False)
        assert Plan.from_dict(json.loads(text)).canonical() == plan.canonical()

    def test_strategy_params_is_nested_object(self, make_plan):
        payload = make_plan(strategy_params={'a': 1, 'b': {'c': 2}}).to_dict()
        assert isinstance(payload['strategy_params'], dict)
        assert Plan.from_dict(payload).strategy_params == {'a': 1, 'b': {'c': 2}}

    def test_field_names_cover_all_keys(self, make_plan):
        assert set(make_plan().to_dict()) == set(PLAN_FIELD_NAMES)

    def test_missing_keys_take_defaults(self):
        plan = Plan.from_dict({'config_path': 'c.toml', 'strategy_key': 'smart',
                               'strategy_params': {}, 'n': 10, 'workers': 2, 'seed': 1})
        assert plan.grain == 'stage'
        assert plan.repeats == 3
        assert plan.collector is False
        assert plan.profile_count == 50

    def test_missing_required_key_rejected(self):
        with pytest.raises(ValueError, match="缺必填键 'seed'"):
            Plan.from_dict({'config_path': 'c.toml', 'strategy_key': 'smart',
                            'strategy_params': {}, 'n': 10, 'workers': 2})

    def test_unknown_key_rejected(self, make_plan):
        with pytest.raises(ValueError, match='未知键'):
            Plan.from_dict({**make_plan().to_dict(), 'nope': 1})

    @pytest.mark.parametrize('field,value', [
        ('grain', 'turbo'),
        ('subject', 'startup2'),
        ('path', 'wasm'),
        ('n', '100'),
        ('n', 1.5),
        ('collector', 1),
    ])
    def test_invalid_values_rejected(self, make_plan, field, value):
        with pytest.raises(ValueError):
            Plan.from_dict({**make_plan().to_dict(), field: value})

    def test_none_only_allowed_on_optional_fields(self, make_plan):
        payload = make_plan().to_dict()
        assert Plan.from_dict({**payload, 'chunksize': None}).chunksize is None
        with pytest.raises(ValueError, match='不接受 None'):
            Plan.from_dict({**payload, 'grain': None})

    def test_non_object_rejected(self):
        with pytest.raises(ValueError, match='必须是对象'):
            Plan.from_dict(['nope'])

    def test_bool_not_accepted_as_int(self, make_plan):
        """`isinstance(True, int)` 为真——不特判就会放行 1/0 冒充整数。"""
        with pytest.raises(ValueError, match='必须是整数'):
            Plan.from_dict({**make_plan().to_dict(), 'n': True})

    def test_optional_int_type_is_checked(self, make_plan):
        """`Optional[int]` 未解包时类型判定会全部落空（既非 int 也非 bool）。"""
        with pytest.raises(ValueError, match='必须是整数'):
            Plan.from_dict({**make_plan().to_dict(), 'chunksize': 'x'})
