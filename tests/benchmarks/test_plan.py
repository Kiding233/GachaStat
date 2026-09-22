"""T1：`Plan` 的因子展开与 `plan.json` 输入契约。

对应 §3.1 的输入契约三条与 §3.9 T1 的「Plan 因子展开」「plan.json 缺字段取默认、
未知键与非法值报错」。
"""

import json

import pytest

from benchmarks.perf.plan import (
    MEM_BASE_GB,
    MEM_GUI_QT_EXTRA_GB,
    MEM_PER_WORKER_GB,
    PLAN_FIELD_NAMES,
    STARTUP_IGNORED_FIELDS,
    STARTUP_PATHS,
    Plan,
    PlanGrid,
    injected_memory_query,
)


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


class TestStartupSemantics:
    """`3e`：`subject='startup'` 的语义与落点边界（P83 §3.11）。

    本项只定语义与分支，不改适配器——`3f-1` 是它的消费者。
    """

    def test_ignored_fields_are_exactly_the_five(self, make_plan):
        """被忽略的字段是**恰好这五个**：多一个会静默吞掉有效因子，少一个会让
        「被忽略却仍参与校验」的字段留下（例如 `n` 若不在列，规则 1 就会在
        startup 下重新适用）。"""
        assert STARTUP_IGNORED_FIELDS == ('n', 'workers', 'chunksize',
                                          'strategy_key', 'seed')
        assert make_plan(subject='startup', path='gui-qt').ignored_fields() \
            == STARTUP_IGNORED_FIELDS

    def test_simulation_ignores_nothing(self, make_plan):
        assert make_plan(subject='simulation').ignored_fields() == ()

    def test_n_and_workers_do_not_affect_the_reading(self, make_plan):
        """五个字段的取值**不进 `canonical()` 之外的任何计算**：两个只在这五项上
        不同的 startup plan，其内存下限相同（其余语义不依赖它们）。"""
        a = make_plan(subject='startup', path='gui-qt', n=1, workers=1, seed=1,
                      strategy_key='no_draw')
        b = make_plan(subject='startup', path='gui-qt', n=99_999, workers=64, seed=7,
                      strategy_key='smart')
        assert a.memory_requirement_gb() == b.memory_requirement_gb()
        assert a.ignored_fields() == b.ignored_fields()


class TestStartupLandingBoundary:
    """「被忽略」不等于「可以声明」——本期只在 `gui-qt` 上有落点（`3f-1`）。

    口径与 `grain='single'` 同型（§3.3）：**声明了平台不实现的组合即调用方
    编程错误**。放行的实际后果不是「少测一段」，而是入口薄壳按 `plan.path` 派发
    到该路径适配器、照常产出一条带 `subject='startup'` 的记录——报告会把一次普通
    模拟说成启动测量。
    """

    def test_only_gui_qt_is_landed(self):
        assert STARTUP_PATHS == ('gui-qt',)

    @pytest.mark.parametrize('path', ['cli', 'webui', 'inline'])
    def test_unlanded_paths_rejected(self, make_plan, path):
        with pytest.raises(ValueError, match='落点'):
            make_plan(subject='startup', path=path)

    def test_message_names_the_landed_path(self, make_plan):
        with pytest.raises(ValueError, match="'gui-qt'"):
            make_plan(subject='startup', path='cli')

    def test_function_grain_rejected(self, make_plan):
        """`function` 档的落点是围绕单次 `_run_single` 的开闭窗口（§3.8 D2），
        冷启动进程内既无 worker 池也无该调用点。"""
        with pytest.raises(ValueError, match='grain'):
            make_plan(subject='startup', path='gui-qt', grain='function', workers=4)

    def test_profile_enabled_rejected(self, make_plan):
        with pytest.raises(ValueError, match='profile_enabled'):
            make_plan(subject='startup', path='gui-qt', grain='stage',
                      profile_enabled=True)

    def test_stage_and_batch_grains_survive(self, make_plan):
        for grain in ('stage', 'batch'):
            assert make_plan(subject='startup', path='gui-qt', grain=grain).grain == grain

    def test_simulation_paths_are_unaffected(self, make_plan):
        """本条只收 `startup`——四条路径在 `simulation` 下的可构造性不变。"""
        for path in ('cli', 'webui', 'inline', 'gui-qt'):
            assert make_plan(subject='simulation', path=path).path == path

    def test_scanning_an_ignored_factor_is_rejected(self, make_plan):
        """`startup` 下扫被忽略的字段：各格读数必然相同，但每格要真起一次冷进程
        （真实窗口 + 8 秒），扫描看起来生效、实际只是重复同一次测量。"""
        base = make_plan(subject='startup', path='gui-qt')
        with pytest.raises(ValueError, match='被忽略'):
            PlanGrid(base=base, factors={'n': [100, 1000]}).expand()

    def test_scanning_a_live_factor_still_works(self, make_plan):
        base = make_plan(subject='startup', path='gui-qt')
        plans = PlanGrid(base=base, factors={'repeats': [1, 3]}).expand()
        assert [p.repeats for p in plans] == [1, 3]


class TestStartupMemoryStillApplies:
    """决策 34：规则 5 与 D8 在 `startup` 下**仍然适用**（豁免它们等于在唯一需要
    该防线的场景关掉防线）。`3e` 补的是「特例按 `gui-qt` 计」这一半。"""

    def test_extra_half_gigabyte_is_charged(self, make_plan):
        """`startup` 的内存下限 = gui-qt 特例（`workers=1` + 0.5 GB），与 plan 里
        填的 `workers` 无关（那五项被忽略）。"""
        expected = max(MEM_BASE_GB, MEM_PER_WORKER_GB) + MEM_GUI_QT_EXTRA_GB
        for workers in (1, 4, 64):
            plan = make_plan(subject='startup', path='gui-qt', workers=workers)
            assert plan.memory_requirement_gb() == expected

    def test_boundary_is_enforced(self, make_plan):
        required = max(MEM_BASE_GB, MEM_PER_WORKER_GB) + MEM_GUI_QT_EXTRA_GB
        with injected_memory_query(lambda: required - 0.01):
            with pytest.raises(ValueError, match='规则 5'):
                make_plan(subject='startup', path='gui-qt')
        with injected_memory_query(lambda: required):
            assert make_plan(subject='startup', path='gui-qt').subject == 'startup'
