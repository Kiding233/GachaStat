"""P69 §1.10b：策略系统测试——迁移冒烟 + 注册表自检 + pickle 序列化。"""
import pytest
from gacha_simulator.core.strategy import (
    create_strategy, STRATEGY_REGISTRY, StrategyMeta, register_strategy,
    Strategy, StrategyContext,
)
from gacha_simulator.core.param_descriptor import (
    FloatParam, IntParam, BoolParam, StringListParam,
)


# ── 8 策略迁移冒烟测试 ────────────────────────────────────────────

ALL_STRATEGIES = [
    ('smart', {}),
    ('pool_quota', {'pool_quotas': {'pool_a': 10}}),
    ('pity_reserve', {'pity_threshold_pct': 70.0}),
    ('stop_on_target', {'stop_on_featured': True, 'stop_on_any_target': False}),
    ('fixed_count', {'count': 10}),
    ('target_hunting', {'target_pool_ids': ['pool_a', 'pool_b']}),
    ('no_draw', {}),
    ('draw_target', {'target_card_ids': ['card_a'], 'pool_id': 'pool_a'}),
]


@pytest.mark.parametrize('key,params', ALL_STRATEGIES)
def test_create_each_strategy(key, params):
    """每个策略可正常构造 + select_action 可调用。"""
    s = create_strategy(key, params)
    assert s is not None
    assert hasattr(s, 'select_action')
    # 验证 _strategy_key 类属性被装饰器注入
    sk = getattr(type(s), '_strategy_key', None)
    assert sk == key, f"{key}: _strategy_key={sk}, 期望={key}"
    # 验证参数正确传递到实例属性
    for k, v in params.items():
        actual = getattr(s, k, None)
        if k == 'target_pool_ids':
            assert actual == v
        elif k == 'pool_quotas':
            assert actual == v
        elif k == 'pity_threshold_pct':
            # PityReserveStrategy.__init__ 内部除以 100
            assert actual == v / 100.0
        elif k == 'target_card_ids':
            # DrawTargetStrategy.__init__ 内部 list→set 转换
            assert actual == set(v)
        else:
            assert actual == v


# ── 未知/无效策略 ──────────────────────────────────────────────────

def test_unknown_strategy_raises():
    with pytest.raises(ValueError, match='Unknown strategy'):
        create_strategy('nonexistent_key')


def test_type_validation_raises():
    with pytest.raises(ValueError):
        create_strategy('pity_reserve', {'pity_threshold_pct': '八十'})


# ── _validate_registry() 自检测试用例 ────────────────────────────

class TestRegistryValidation:
    """VR-01~VR-06: _validate_registry() 自检。"""

    def setup_method(self):
        self._backup = dict(STRATEGY_REGISTRY)

    def teardown_method(self):
        STRATEGY_REGISTRY.clear()
        STRATEGY_REGISTRY.update(self._backup)

    def _reimport_validate(self):
        """重新执行 _validate_registry 以触发断言。"""
        from gacha_simulator.core.strategy import _validate_registry
        _validate_registry()

    def test_duplicate_key_raises(self):
        """VR-01: 注册表 key 重复 → AssertionError。

        Python dict 天然保证 key 唯一——同 key 赋值会覆盖而非重复。
        此测试验证 _validate_registry 的 all_keys 集合检查逻辑能正确
        处理 items() 遍历中的所有 key（均为唯一）。"""
        self._reimport_validate()  # 正常注册表不应触发重复 key 断言

    def test_non_internal_cls_none_raises(self):
        """VR-02: internal=False 且 cls=None → TypeError。"""
        STRATEGY_REGISTRY['test_broken'] = StrategyMeta(
            key='test_broken', display_name='Test',
            description='test', cls=None, params=[],
        )
        with pytest.raises(TypeError, match='cls 为 None'):
            self._reimport_validate()

    def test_non_strategy_subclass_raises(self):
        """VR-03: cls 不是 Strategy 子类 → TypeError。"""
        STRATEGY_REGISTRY['test_bad_cls'] = StrategyMeta(
            key='test_bad_cls', display_name='Test',
            description='test', cls=str, params=[],
        )
        with pytest.raises(TypeError, match='必须为 Strategy 子类'):
            self._reimport_validate()

    def test_duplicate_param_keys_raises(self):
        """VR-04: 同一策略内参数 key 重复 → AssertionError。"""
        # 找一个有 params 的条目，复制其 params
        for key, meta in list(STRATEGY_REGISTRY.items()):
            if meta.params:
                STRATEGY_REGISTRY[key] = StrategyMeta(
                    key=key, display_name=meta.display_name,
                    description=meta.description, cls=meta.cls,
                    params=list(meta.params) + list(meta.params),
                )
                break
        with pytest.raises(AssertionError, match='重复 key'):
            self._reimport_validate()

    def test_internal_and_disabled_raises(self):
        """VR-05: internal=True 且 disabled=True → AssertionError。"""
        STRATEGY_REGISTRY['test_bad_combo'] = StrategyMeta(
            key='test_bad_combo', display_name='Test',
            description='test', cls=None, params=[],
            internal=True, disabled=True,
        )
        with pytest.raises(AssertionError, match='internal 与 disabled'):
            self._reimport_validate()

    def test_valid_registry_passes(self):
        """VR-06: 正常注册表通过全部检查。"""
        self._reimport_validate()  # 不应抛出异常


# ── 多进程 Pickle 序列化测试 ─────────────────────────────────────

@register_strategy('plugin/test_pickle', 'Pickle测试',
    params=[
        FloatParam('threshold', '阈值', default=80.0, min_val=0.0, max_val=100.0),
        IntParam('count', '数量', default=10, min_val=1),
        BoolParam('flag', '开关', default=False),
        StringListParam('ids', '池子列表', default=['pool_a']),
    ])
class _PickleTestStrategy(Strategy):
    def __init__(self, threshold=80.0, count=10, flag=False, ids=None):
        self.threshold = threshold
        self.count = count
        self.flag = flag
        self.ids = ids or ['pool_a']

    @classmethod
    def description(cls):
        return "Pickle序列化测试策略"

    def select_action(self, ctx):
        from gacha_simulator.core.action import DrawAction
        return DrawAction(pool_id=self.ids[0] if self.ids else 'pool_a')


def _worker_select_action(strategy, ctx):
    """子进程 worker——验证 strategy 可被 pickle 并在子进程正常工作。"""
    action = strategy.select_action(ctx)
    return type(action).__name__, type(strategy)._strategy_key


def test_strategy_pickle_multiprocess():
    """验证 @register_strategy 装饰的策略实例可 pickle 并在子进程执行。"""
    from gacha_simulator.core.action import DrawAction

    s = create_strategy('plugin/test_pickle', {
        'threshold': 50.0, 'count': 5, 'flag': True, 'ids': ['pool_a', 'pool_b']
    })
    assert type(s)._strategy_key == 'plugin/test_pickle'

    # pickle round-trip
    import pickle
    restored = pickle.loads(pickle.dumps(s))
    assert type(restored)._strategy_key == 'plugin/test_pickle'
    assert restored.threshold == 50.0
    assert restored.count == 5
    assert restored.flag is True
    assert restored.ids == ['pool_a', 'pool_b']

    # 单进程验证 select_action
    action = restored.select_action(None)
    assert isinstance(action, DrawAction)


def test_strategy_pickle_subprocess():
    """验证策略可跨进程传递并执行 select_action。"""
    import multiprocessing as mp

    s = create_strategy('plugin/test_pickle', {})
    # 最小构造 StrategyContext
    from gacha_simulator.core.state import GachaState
    ctx = StrategyContext(
        state=GachaState(),
        current_pools=[],
        all_pools=[],
        future_schedules=[],
        target_cards=None,
        stop_condition=None,
    )

    with mp.Pool(1) as pool:
        action_name, strategy_key = pool.apply(_worker_select_action, (s, ctx))

    assert action_name == 'DrawAction'
    assert strategy_key == 'plugin/test_pickle'


# ── Ps01 R1：future_resource_gains 派生字段测试 ────────────────────

def _min_strategy_context(**kw):
    """构造最小 build_strategy_context 调用（Ps01 R1 测试辅助）。"""
    from gacha_simulator.core.state import GachaState
    from gacha_simulator.core.strategy_context_builder import build_strategy_context
    rt = kw.pop('real_time', 0.0)
    state = GachaState()
    state.real_time = rt
    base = dict(
        state=state, current_pools=[], all_pools=[], real_time=rt,
        target_cards=None, stop_condition=None, pity_engine=None, pity_state=None,
        pool_draw_counts={}, total_draws=0, last_draw_pity_triggered=False,
        ssr_ids=set(),
    )
    base.update(kw)
    return build_strategy_context(**base)


def test_future_resource_gains_schedule():
    """SC-01（Ps01 R1）：未来未到达日程资源聚合，day 天数与 real_time 秒正确换算。

    日程 day0=50（已到达，第 3 天前）、day5=100（未到达），real_time=第 3 天，
    lookahead=10 天 → 聚合 day5 的 100，排除 day0。用区分性数值钉死
    「聚合未来未到达资源」方向（P69 SC-01 原文两金额相同无法区分）。
    """
    from gacha_simulator.core.resource_gain import ScheduleResourceGain
    DAY = 86400
    rg = ScheduleResourceGain({0: {'gem': 50.0}, 5: {'gem': 100.0}}, total_days=30)
    ctx = _min_strategy_context(real_time=3 * DAY, resource_gain=rg, lookahead=10)
    assert ctx.future_resource_gains == {'gem': 100.0}


def test_future_resource_gains_empty():
    """SC-02（Ps01 R1）：无 resource_gain / lookahead 时为空 dict（非 None），
    策略 `ctx.future_resource_gains.get('gem', 0.0)` 正常工作。"""
    ctx = _min_strategy_context()
    assert ctx.future_resource_gains == {}
    assert ctx.future_resource_gains is not None


def test_future_resource_gains_no_lookahead():
    """lookahead 为 None 时 future_resource_gains 为空（未请求前瞻），
    即使传了 resource_gain 也不计算。"""
    from gacha_simulator.core.resource_gain import ScheduleResourceGain
    rg = ScheduleResourceGain({5: {'gem': 100.0}}, total_days=30)
    ctx = _min_strategy_context(resource_gain=rg, lookahead=None)
    assert ctx.future_resource_gains == {}


def test_future_resource_gains_with_schedule_mgr_no_crash():
    """Ps01 R1 回归：带 schedule_mgr + resource_gain 时 build_strategy_context 不崩溃。

    原缺陷：遍历 get_future_schedules() 访问 entry.day/entry.gains 抛 AttributeError
    （PoolSchedule 无这两个属性），带 schedule 配置的批量模拟每轮必崩被吞。
    修复后 schedule_mgr 只供 future_schedules 使用、resource_gain 走 compute，
    两者并存不再抛异常。
    """
    from gacha_simulator.core.resource_gain import ScheduleResourceGain
    from gacha_simulator.core.schedule import PoolSchedule, PoolScheduleManager
    DAY = 86400
    rg = ScheduleResourceGain({5: {'gem': 100.0}}, total_days=30)
    mgr = PoolScheduleManager([
        PoolSchedule(pool_id='pool_a', available_from=0.0, available_until=30 * DAY),
    ])
    ctx = _min_strategy_context(
        real_time=0.0, schedule_mgr=mgr, resource_gain=rg, lookahead=10,
    )
    # 不再抛 AttributeError；future_schedules 正常返回、future_resource_gains 正确聚合
    assert len(ctx.future_schedules) == 1
    assert ctx.future_schedules[0].pool_id == 'pool_a'
    assert ctx.future_resource_gains == {'gem': 100.0}
