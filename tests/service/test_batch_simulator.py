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
import dataclasses
import functools
import os
import pickle
import types

import pytest

from gacha_simulator.core.config_store import ConfigError, PityDef
from gacha_simulator.core.config_toml import load_toml
from gacha_simulator.core.state import GachaState
from gacha_simulator.core.stop_condition import (
    AllPoolsEndCondition, CompositeStopCondition, FixedActionCountCondition,
    NotCondition, ResourceThresholdCondition, TargetAcquiredCondition,
)
from gacha_simulator.service.batch_simulator import (
    SimulationEnvBuilder, _build_pity_cfg_dict, _pity_dict_to_pitydef,
    _pitydef_to_pity_dict, run_batch_parallel,
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
    assert cond.check(state, _stats()) is True
    assert cond.check(state, _stats()) is True
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


# ══════════════════════════════════════════════════════════════════
# P79 4a5：from_config_store 的条件树接线（缺陷 A 的闭合点）
#
# 依赖 4a1 的字段 / 4a3 的解析 / 4b2b2 的树分派三者，故排在它们之后交付。
# ══════════════════════════════════════════════════════════════════

# 顶层取 all 而非 any：any(fixed_action_count, not target_acquired) 中「未持有 →
# not 为真」会让条件在 iteration 0 即成立（0 抽），夹具失去意义。all 下由
# fixed_action_count(20) 作真实闸门，not 节点仍参与求值。
_STOP_SECTION = """
[stop_condition]
mode = "all"

[[stop_condition.conditions]]
type = "fixed_action_count"
max_actions = 20

[[stop_condition.conditions]]
mode = "not"

[[stop_condition.conditions.conditions]]
type = "target_acquired"
target_id = "no_such_card"
quantity = 1
"""


def test_from_config_store_wires_stop_condition_tree():
    """条件树 → create_stop_condition → env.stop_condition（等价对象）。"""
    store = load_toml(CONFIG)
    store.stop_condition = {
        'mode': 'any',
        'conditions': [
            {'type': 'fixed_action_count', 'max_actions': 20},
            {'mode': 'not', 'conditions': [
                {'type': 'target_acquired', 'target_id': 'x', 'quantity': 1}]},
        ],
    }
    env = SimulationEnvBuilder.from_config_store(store)

    cond = env.stop_condition
    assert isinstance(cond, CompositeStopCondition)
    assert cond.mode == 'any'
    assert isinstance(cond.conditions[0], FixedActionCountCondition)
    assert cond.conditions[0].max_actions == 20
    assert isinstance(cond.conditions[1], NotCondition)


def test_from_config_store_empty_tree_yields_none():
    """空树（None / 空字典）→ env.stop_condition 为 None（= 仅硬边界）。"""
    for empty in (None, {}):
        store = load_toml(CONFIG)
        store.stop_condition = empty
        assert SimulationEnvBuilder.from_config_store(store).stop_condition is None


def test_from_config_store_tolerates_missing_field(monkeypatch):
    """对不含 stop_condition 字段的 ConfigStore 变体不抛 AttributeError。

    2b 的接线以 getattr(store, 'stop_condition', None) 读字段，正是为容忍本形态
    ——字段由 4a1 才引入，硬取属性会使接线落地即对旧 ConfigStore 抛错。
    """
    from gacha_simulator.core.config_store import ConfigStore

    store = load_toml(CONFIG)
    monkeypatch.delattr(ConfigStore, 'stop_condition')
    env = SimulationEnvBuilder.from_config_store(store)
    assert env.stop_condition is None


def test_toml_stop_condition_end_to_end(tmp_path):
    """TOML [stop_condition] 段 → store → env → 用户条件真实生效。

    这是缺陷 A 的端到端闭合验证：改造前即便手写该段也无人解析，模拟固定使用
    AllPoolsEndCondition(env.end_time)。
    """
    base = open(CONFIG, encoding='utf-8').read()
    path = os.path.join(str(tmp_path), 'p79.toml')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(base + _STOP_SECTION)

    store = load_toml(path)
    assert store.stop_condition is not None
    env = SimulationEnvBuilder.from_config_store(store)
    assert isinstance(env.stop_condition, CompositeStopCondition)

    specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    r = run_batch_parallel(
        env=env, target_specs=specs, initial_resources=env.initial_resources,
        num_simulations=1, max_workers=1, seed=42, strategy_key='smart').results[0]

    # 用户条件 fixed_action_count(20) 先于硬边界收口
    assert r.total_draws == 20
    assert r.final_time < env.end_time


def _stats(**kw):
    """P81 §4.1-4：停止条件 check() 的 stats 形参改为必填，测试统一由此构造。"""
    from gacha_simulator.service.gacha_service import SimulationStats
    s = SimulationStats()
    for k, v in kw.items():
        setattr(s, k, v)
    return s


# ══════════════════════════════════════════════════════════════════
# P64 S4b / §3.6 AUDIT-BREAK-1：PityDef 字段级透传守卫
# ══════════════════════════════════════════════════════════════════
# 三处透传点（`pentry` 写端 / `_PityDef` 读端 / `retreat_config` 浅拷贝）原为
# 枚举式逐字段列举：新增字段漏写即静默落回默认值，配置层与测试都看不出异常。
# 本组把「键集相等」与「逐字段等值」两条钉死，使「第 N+1 个字段漏透传」在 CI
# 期即失败（§六「PityDef 字段枚举透传守卫」条）。


def _all_fields_non_default() -> dict:
    """一条**全部字段均为非默认值**的 `PityDef` kwargs（字段集由 dataclasses 现取）。

    取值本身不参与语义断言，唯一作用是让下面每条用例对**每个字段**都有检测力
    （全默认构造时用例恒绿、检测力归零）。
    """
    return {
        'name': 'p1',
        'btype': 'soft_interval',
        'scope': 'sr',
        'target_featured': True,
        'deltas': ((74, 0.0), (16, 6.25)),
        'threshold': 90,
        'counter_init': 3,
        'guaranteed_init': True,
        'fate_points_init': 2,
        'selected_card_init': 'up_a',
        'soft_start': 74,
        'soft_end': 90,
        'soft_increment': 6.25,
        'soft_deltas': ((74, 0.0), (16, 6.25)),
        'cr_counter_threshold': 3,
        'cr_base_rate': 0.018,
        'cr_state_probs': (0.0, 0.0, 0.0, 1.0),
        'fate_threshold': 1,
        'switch_allowed': False,
        'switch_resets_progress': False,
        'pools': ('b1.main',),
        'deactivate_on_early_hit': True,
        'depends_on': 'other',
        'max_triggers': 2,
        'reset': 'featured',
        'priority': 5,
    }


class TestPityDefFieldPassthrough:
    """`PityDef` → `pentry` → `PityDef` 的字段全量保真（S4b 改造的守卫）。"""

    def test_non_default_table_covers_every_field(self):
        """取值表必须覆盖 `PityDef` 全部字段——否则本组用例对该字段零检测力。"""
        names = {f.name for f in dataclasses.fields(PityDef)}
        assert set(_all_fields_non_default()) == names, (
            f"字段集不匹配：仅取值表有 {sorted(set(_all_fields_non_default()) - names)}，"
            f"仅 PityDef 有 {sorted(names - set(_all_fields_non_default()))}")

    def test_non_default_table_values_are_actually_non_default(self):
        """逐字段确认取值 != 字段默认值——防「表里写了，但恰好写的就是默认值」。"""
        pd = PityDef(**_all_fields_non_default())
        bad = [f.name for f in dataclasses.fields(PityDef)
               if f.default is not dataclasses.MISSING
               and getattr(pd, f.name) == f.default]
        assert bad == [], f"这些字段取的是默认值，本组用例对它们零检测力：{bad}"

    def test_pentry_keyset_equals_pitydef_fields(self):
        """键集相等（防漏**亦防多**）——AUDIT-BREAK-1 的强制断言。"""
        pentry = _pitydef_to_pity_dict(PityDef(**_all_fields_non_default()))
        assert set(pentry) == {f.name for f in dataclasses.fields(PityDef)}

    def test_production_pentry_keyset_equals_pitydef_fields(self):
        """同一断言落在**生产路径实际产出的那份 `pentry`** 上。

        上一条断言的是辅助函数的输出；本条的取值来自 `from_config_store` 实际调用的
        `_build_pity_cfg_dict`。

        **注意覆盖面**（S4b 审查 minor）：本断言只保证「该函数本身不漏字段」，对
        「把**调用点**改回内联枚举式 dict」无检测力（实测该回退下本文件全绿，而生产
        链路的 `priority` 真的丢了）。后者由
        `test_from_config_store_carries_priority_end_to_end` 末尾对 `engine.pity_defs`
        的断言钉住。
        """
        store = load_toml(CONFIG)
        store.pity.pities = [PityDef(**_all_fields_non_default())]
        cfg = _build_pity_cfg_dict(store)
        assert len(cfg['pities']) == 1
        pentry = cfg['pities'][0]
        assert set(pentry) == {f.name for f in dataclasses.fields(PityDef)}
        assert pentry['priority'] == 5
        assert cfg['counter_init'] == {'p1': 3}

    def test_pentry_carries_no_alias_keys(self):
        """四个别名键已弃用，写端不得再产出（ISSUE-910 的改名前提）。"""
        pd = PityDef(**_all_fields_non_default())
        pentry = _pitydef_to_pity_dict(pd)
        assert {'type', 'start', 'end', 'increment'} & set(pentry) == set()
        # 四者的字段名口径必须真实携带值（防「删了别名键又忘了加字段名键」）
        assert pentry['btype'] == 'soft_interval'
        assert pentry['soft_start'] == 74
        assert pentry['soft_end'] == 90
        assert pentry['soft_increment'] == 6.25

    def test_field_driven_roundtrip_preserves_every_field(self):
        """字段驱动往返：`PityDef` → `pentry` → `PityDef` 逐字段等值。"""
        pd = PityDef(**_all_fields_non_default())
        restored = _pity_dict_to_pitydef(_pitydef_to_pity_dict(pd))
        for f in dataclasses.fields(PityDef):
            assert getattr(restored, f.name) == getattr(pd, f.name), (
                f"字段 '{f.name}' 在字段驱动往返中失真："
                f"{getattr(pd, f.name)!r} → {getattr(restored, f.name)!r}")
        assert restored == pd

    def test_missing_key_falls_back_to_field_default(self):
        """键缺失落回 dataclass 字段默认值。

        **不与旧口径完全一致**（S4b 审查 low）：旧读端 `p.get(k, default)` 对 `btype`
        缺键落 `'soft_interval'`（合法），新读端落字段默认 `'soft'`（不在
        `BEHAVIOR_REGISTRY`，该保底会被引擎跳过、只留一条 warning）。生产路径不可达
        （写端恒发全字段），故只登记不改。
        """
        pd = _pity_dict_to_pitydef({'name': 'x'})
        assert pd == PityDef(name='x')

    def test_pools_normalized_to_tuple_from_list_and_str(self):
        """`pools` 归一为 tuple：list（TOML 读入形态）与裸字符串均收。"""
        assert _pity_dict_to_pitydef({'name': 'x', 'pools': ['b1.main']}).pools == ('b1.main',)
        assert _pity_dict_to_pitydef({'name': 'x', 'pools': 'b1.main'}).pools == ('b1.main',)
        assert _pity_dict_to_pitydef({'name': 'x'}).pools == ('*',)

    def test_missing_required_name_raises(self):
        """`name` 是唯一无默认值的字段，缺失必须显式报错而非静默合成。"""
        with pytest.raises(ConfigError, match='name'):
            _pity_dict_to_pitydef({'btype': 'hard'})

    @pytest.mark.parametrize('alias', ['type', 'start', 'end', 'increment'])
    def test_legacy_alias_keys_rejected(self, alias):
        """别名键已不属契约——放行即静默错值，故硬拒（AUDIT-BREAK-1 的失效形态）。"""
        with pytest.raises(ConfigError, match='别名键'):
            _pity_dict_to_pitydef({'name': 'x', alias: 'anything'})

    def test_priority_survives_both_passthrough_sites(self):
        """§六 ISSUE-007：`priority=5` 经 `pentry` 与 `_PityDef` 两处后仍为 5。"""
        pd = PityDef(name='pf', btype='soft_interval', scope='ssr', priority=5)
        pentry = _pitydef_to_pity_dict(pd)
        assert pentry['priority'] == 5
        assert _pity_dict_to_pitydef(pentry).priority == 5

    def test_priority_default_zero_is_carried_as_zero(self):
        """默认 0 亦须显式携带（读端不依赖「缺键」这一隐式默认）。"""
        pentry = _pitydef_to_pity_dict(PityDef(name='x'))
        assert pentry['priority'] == 0
        assert _pity_dict_to_pitydef(pentry).priority == 0

    def test_from_config_store_carries_priority_end_to_end(self):
        """端到端：`ConfigStore` 携带 `priority=5` 的配置能走通 `from_config_store`。

        本步只做透传（消费方是紧随其后的 S4-2 构造形参与 S6b 排序键），故断言落点
        在「写端 `pentry` 与读端重建出的 `PityDef` 仍带 priority」；`from_config_store`
        一侧断言引擎可正常构造（改造后读端不再认别名键，若两处口径不一致则此处
        保底的 btype 会落回默认而抛 `KeyError`→被吞成 warning，`pity_engine` 仍在
        但保底列表为空）。故一并断言 `_behavior_list` 非空以钉住「保底确实建出来了」。
        """
        store = load_toml(CONFIG)
        store.pity.pities = [PityDef(name='pf', btype='soft_interval', scope='ssr',
                                     soft_start=74, soft_end=90, priority=5)]
        env = SimulationEnvBuilder.from_config_store(store)
        assert env.pity_engine is not None
        assert len(env.pity_engine._behavior_list) == 1
        # 写端 → 读端两处的优先级保真
        pentry = _pitydef_to_pity_dict(store.pity.pities[0])
        assert pentry['priority'] == 5
        assert _pity_dict_to_pitydef(pentry).priority == 5
        # **生产对象上的断言**（S4b 审查 minor）：上面两条断言的是辅助函数，把
        # `from_config_store` 的**调用点**改回内联枚举式 dict（漏 priority）时它们
        # 仍全绿，而生产链路的 priority 已静默丢失。此处直接观察引擎最终收到的
        # `PityDef`：实测该突变下本行是唯一变红的断言。
        assert env.pity_engine.pity_defs['pf'].priority == 5


# ══════════════════════════════════════════════════════════════════
# P64 S7b / §四 跨进程 pickle 约束：四族对象的 round-trip + 并行度未退化
# ══════════════════════════════════════════════════════════════════
# 依据：计划 §四「跨进程 pickle 约束」段。`run_batch_parallel` 用
# `MPPool(initializer=_wk_init, initargs=(env, target_specs))` 把**整个 env**
# 序列化给每个 worker，故 P64 的四族新对象（`Pity` / `Tracker` / `Modifier` /
# `Lifecycle`）全部进这条 pickle 图。禁 lambda / 闭包 / 局部函数 / 不可 pickle 的
# 第三方对象；违反时并行度**静默归零**（故障形态见下方冒烟用例的说明）。
#
# `InvariantChecker` 的 round-trip **不在本步**：该类由排在 S7b 之后的 S11 产出，
# 此刻引用即 `ImportError`（pytest 收集期即红），该用例归 S11 的专属文件
# `tests/core/test_pity_invariant_checker.py`。
#
# 上方 `pentry` / `_pity_dict_to_pitydef` 透传用例（S4b）与本节无关，未改动。

#: 五条保底定义，拼出四族对象的**齐全覆盖**（覆盖集由
#: `test_pickle_family_fixture_covers_every_family` 钉住）。
#: scope 的分配受 `_validate_behaviors` 约束（每个稀有度最多一个事件驱动型）：
#: SSR / SR 各一条 counter 驱动型与一条事件驱动型，R 留给 `rotating_soft`。
_FAMILY_PITY_DEFS = (
    # counter 驱动型 + AlwaysActive
    dict(name='p_soft', btype='soft_interval', scope='ssr',
         soft_start=74, soft_end=90, soft_increment=6.25, counter_init=2),
    # counter 驱动型 + FiniteActive（`max_triggers` > 0）+ target_featured
    dict(name='p_hard', btype='hard', scope='sr', threshold=10, counter_init=3,
         max_triggers=2, target_featured=True),
    # 事件驱动型（FlagTracker）+ deactivate_on_early_hit
    dict(name='p_rot', btype='rotating', scope='ssr', guaranteed_init=True,
         deactivate_on_early_hit=True),
    # 事件驱动型（FateTracker）+ 初始定轨目标
    dict(name='p_tgt', btype='targeted', scope='sr', fate_threshold=2,
         selected_card_init='up_a', fate_points_init=1),
    # `_soft` 复合型：NamespaceTracker（独立命名空间）+ 双 Modifier + DependentActive
    dict(name='p_rotsoft', btype='rotating_soft', scope='r', soft_start=4,
         soft_end=6, soft_increment=3.0, counter_init=1, depends_on='p_soft'),
)

#: 四族的覆盖集：夹具必须产出这些类。零件被改动后静默消失时，本组用例对该族的
#: 检测力会归零（构造成功、断言恒真），故覆盖集本身是一条断言。
_FAMILY_COVERAGE = {
    'pity': {'Pity'},
    'tracker': {'CounterTracker', 'FlagTracker', 'FateTracker', 'NamespaceTracker'},
    'modifier': {'SoftModifier', 'HardModifier', 'RotatingModifier', 'SelectedModifier'},
    'lifecycle': {'AlwaysActive', 'FiniteActive', 'DependentActive'},
}

_SCALAR_TYPES = (str, bytes, int, float, bool, type(None))
_MISSING = object()


def _family_env():
    """构造一条四族对象齐全的 env（默认配置的池子 + 五条补上的保底定义）。

    构造后调 `_bind_counter_to_pickle_graph`：`Counter` 在刚构造完的对象图里
    **不存在**（`CounterTracker._counter` 为 `None`），须显式绑一次才进 round-trip 图。
    """
    store = load_toml(CONFIG)
    store.pity.pities = [PityDef(**d) for d in _FAMILY_PITY_DEFS]
    env = SimulationEnvBuilder.from_config_store(store)
    _bind_counter_to_pickle_graph(env.pity_engine.behaviors.values())
    specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    return env, specs


def _family_objects(env):
    """从 env 的引擎里取出四族对象，按 `Pity` → 零件 的从属关系分组。"""
    pities = list(env.pity_engine.behaviors.values())
    return {
        'pity': pities,
        'tracker': [t for bh in pities for t in bh._trackers],
        'modifier': [m for bh in pities for m in bh._modifiers],
        'lifecycle': [bh._lifecycle for bh in pities],
    }


def _bind_counter_to_pickle_graph(pities):
    """把 `CounterTracker` 的 `Counter` 显式绑进对象图，返回绑定的 `Counter` 个数。

    **补的是一处实质覆盖缺口**（2026-10-13 独立审查实测）：`CounterTracker._counter`
    与 `FlagTracker._flag_ctl` 在**构造期均为 `None`**，只有抽卡入口的
    `Pity._rebind_state` 才会调 `rebind` 绑定它们，故刚构造完的对象图里**只有 `Flag`**
    （`Lifecycle._ns_active` 直接持有 `Flag`）、**`Counter` 一个都没有**（实测两套夹具
    均为 `Counter=0`）。于是「`Counter` / `Flag` 是 dataclass，自动生成的 `__eq__` 会拿
    `_state` 比同一性、故不能用 `==`」这条理由里，`Counter` 那一半**从未被行使**：
    `Counter` 自身若获得不可 pickle 的成员，round-trip 与禁令扫描都测不出来。

    此处显式调一次 `rebind`，调用形态与引擎 `_rebind_state` 对 Tracker 的调用一致
    （`rebind(state, self._name)`，见 `core/pity.py`）。绑定用的 `PityState()` 是
    **独立新实例**、不接 env 的 `pity_state_init`：本函数只负责让 `Counter` 出现在图里，
    而 `Counter._state` 本身可 pickle 且指纹可折算，用哪一份 state 都不影响检测力。
    **不得**删除本调用（缺口回归）或改绑 `None`（`Counter` 又消失）。
    """
    from gacha_simulator.core.pity_tracker import CounterTracker
    from gacha_simulator.core.pity_primitives import PityState

    bound = 0
    for bh in pities:
        for tr in bh._trackers:
            if isinstance(tr, CounterTracker):
                tr.rebind(PityState(), bh._name)
                bound += 1
    return bound


def _fingerprint(obj):
    """把对象图折算成「结构指纹」（嵌套 tuple + 标量），逐字段相等的实现基础。

    **不直接比 `==`**：四族的零件（`Counter` / `Flag`）是 dataclass，自动生成的
    `__eq__` 会拿 `_state` 比**对象同一性**，而 round-trip 后两侧必是不同对象，故
    `orig == back` 恒假（假红）；`Pity` / `Tracker` / `Modifier` / `Lifecycle` 未定义
    `__eq__`，退化为同一性比较同样恒假。故按类型分派折算：

    | 类型 | 折算 |
    |------|------|
    | 标量 / None | 原值 |
    | dataclass（`Counter` / `Flag` / `LifecycleConfig`） | 类名 + 逐字段递归 |
    | dict | 类名 + 逐项递归，**保插入序**（pickle 保留插入序，故保序比对同时钉住「键集与顺序都不变」） |
    | list / tuple / set / frozenset | 容器类名 + 逐元素递归（set 无插入序，按 `repr` 排序后再比） |
    | 其余带 `__dict__` 的对象（`Pity` / 零件 / `StateView` / `PityState`） | 类名 + 逐 `vars()` 项递归 |

    未知类型**抛 `TypeError`**：新成员类型出现时必须显式补一条折算规则，否则
    「逐字段相等」会悄悄失去检测力（退化成恒假的同一性比较，或恒真的 `repr` 比较）。
    """
    if isinstance(obj, _SCALAR_TYPES):
        return obj
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return (type(obj).__qualname__,
                tuple((f.name, _fingerprint(getattr(obj, f.name)))
                      for f in dataclasses.fields(obj)))
    if isinstance(obj, dict):
        return ('dict', tuple((_fingerprint(k), _fingerprint(v)) for k, v in obj.items()))
    if isinstance(obj, (list, tuple)):
        return (type(obj).__name__, tuple(_fingerprint(v) for v in obj))
    if isinstance(obj, (set, frozenset)):
        return (type(obj).__name__, tuple(sorted((_fingerprint(v) for v in obj), key=repr)))
    if hasattr(obj, '__dict__'):
        return (type(obj).__qualname__,
                tuple((k, _fingerprint(v)) for k, v in vars(obj).items()))
    raise TypeError(
        f'_fingerprint 不认识 {type(obj).__name__}：请补一条折算规则，'
        f'不得退化为 == 或 repr，否则比对失去检测力'
    )


def _field_diffs(orig, back):
    """回报逐字段指纹不同的字段名（只比一层），失败信息用它指出差异落在哪里。

    全量比对由 `_fingerprint` 的递归负责报「有差异」，本函数负责报「差异在哪个字段」。
    """
    if dataclasses.is_dataclass(orig) and not isinstance(orig, type):
        pairs = [(f.name, getattr(orig, f.name), getattr(back, f.name))
                 for f in dataclasses.fields(orig)]
    else:
        pairs = [(k, v, getattr(back, k, _MISSING)) for k, v in vars(orig).items()]
    return [name for name, a, b in pairs
            if b is _MISSING or _fingerprint(a) != _fingerprint(b)]


#: §四 禁令中**可由类型直接判定**的成员形态。第三方的不可 pickle 对象无法枚举，
#: 由 round-trip 本体（pickle 是权威判据）兜住；本表负责给出可读的定位信息。
#:
#: **本表是 §四 禁令的保守超集：命中不等于违规**，须由 round-trip 复核。下列形态
#: 实测**可 pickle**（`pickle.dumps` 均成功）却会在此假红：模块级 `def`（按引用
#: 序列化）、可 pickle 的绑定方法（如 `'abc'.upper`）、内建函数（如 `len`）、
#: `functools.partial`（其函数与参数都可按引用序列化时，如 `partial(int, base=2)`）。
#: 真正无条件不可 pickle 的只有模块对象 / 代码对象 / 生成器 / **嵌套 def 与闭包**。
#:
#: **不为此改扫描逻辑**（如「先试 `pickle.dumps` 再剔除」）的理由：本扫描的价值在
#: **定位层**。pickle 的报错只有一句 `Can't pickle local object`、**不含路径**，而本
#: 扫描能给出如 `behaviors['p_soft']._trackers[0]._f` 的路径。两者不是冗余关系：
#: 扫描认不出第三方的不可 pickle 对象，round-trip 给不出路径。
_FORBIDDEN_TYPES = (
    types.FunctionType,          # lambda / 闭包 / 局部函数（模块级 def 可 pickle，假红）
    types.MethodType,            # 绑定方法（`__self__` 不可 pickle 时才真违规）
    types.BuiltinFunctionType,   # 内建函数（按引用 pickle，实测可 pickle）
    types.ModuleType,            # 模块对象不可 pickle
    types.CodeType,              # 代码对象不可 pickle
    types.GeneratorType,         # 生成器不可 pickle
    functools.partial,           # 函数与参数都可序列化时可 pickle（假红）
)


def _forbidden_members(obj, path, seen, out):
    """深度优先遍历对象图，把命中 §四 禁令的成员记进 `out`（路径 + 类型名）。"""
    if isinstance(obj, _SCALAR_TYPES) or id(obj) in seen:
        return
    seen.add(id(obj))
    if isinstance(obj, _FORBIDDEN_TYPES):
        out.append((path, type(obj).__name__))
        return
    if isinstance(obj, type):
        return                       # 类对象按引用 pickle，其成员不随实例进 pickle 图
    if dataclasses.is_dataclass(obj):
        for f in dataclasses.fields(obj):
            _forbidden_members(getattr(obj, f.name), f'{path}.{f.name}', seen, out)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            _forbidden_members(v, f'{path}[{k!r}]', seen, out)
        return
    if isinstance(obj, (list, tuple, set, frozenset)):
        for i, v in enumerate(obj):
            _forbidden_members(v, f'{path}[{i}]', seen, out)
        return
    if hasattr(obj, '__dict__'):
        for k, v in vars(obj).items():
            _forbidden_members(v, f'{path}.{k}', seen, out)


class TestFourFamilyPickleRoundtrip:
    """四族对象各一条 `dumps` → `loads` → 逐字段相等（§四 的验收面）。"""

    def test_pickle_family_fixture_covers_every_family(self):
        """夹具的覆盖集守卫：零件静默消失时本组用例对该族的检测力归零。"""
        env, _ = _family_env()
        fam_objs = _family_objects(env)
        got_trackers = fam_objs['tracker']
        got = {fam: {type(o).__name__ for o in objs} for fam, objs in fam_objs.items()}
        for fam, expected in _FAMILY_COVERAGE.items():
            assert got[fam] == expected, (
                f'{fam} 族的覆盖集变了（少即夹具退化、多即需补进 _FAMILY_COVERAGE）：'
                f'{sorted(got[fam])} != {sorted(expected)}')
        # 判据：`Counter` 必须真的在 pickle 图里。`CounterTracker._counter` 构造期为
        # `None`，靠 `_bind_counter_to_pickle_graph` 的 rebind 才出现，故本行同时是那个
        # 绑定的存在性守卫：删掉绑定即红，`Counter` 与 `Flag` 并列的那条理由会重新只剩
        # `Flag` 一半被行使。
        assert [t for t in got_trackers if getattr(t, '_counter', None) is not None], (
            '夹具图里没有已绑定的 Counter：`Counter` 与 `Flag` 并列作为「不能用 ==」的'
            '理由时，Counter 那一半会重新变成未被行使')

    @pytest.mark.parametrize('family', ['pity', 'tracker', 'modifier', 'lifecycle'])
    def test_pickle_roundtrip_family(self, family):
        """该族每个对象经 `env` 的 round-trip 后**逐字段相等**。

        比对面是**同族的第 i 个对象**（`env.pity_engine.behaviors` 的顺序在 round-trip
        后不变，故 `zip` 逐位对应），逐字段由 `_fingerprint` 递归折算后比对。
        """
        env, _ = _family_env()
        restored = pickle.loads(pickle.dumps(env))
        before = _family_objects(env)[family]
        after = _family_objects(restored)[family]
        assert len(before) == len(after) > 0, (
            f'{family} 族的对象数在 round-trip 后变了：{len(before)} → {len(after)}')
        for orig, back in zip(before, after):
            assert type(orig) is type(back), (
                f'{family} 族的对象类型在 round-trip 后变了：'
                f'{type(orig).__name__} → {type(back).__name__}')
            if _fingerprint(orig) != _fingerprint(back):
                raise AssertionError(
                    f'{family} 族的 {type(orig).__name__} 在 round-trip 后字段失真：'
                    f'字段 {_field_diffs(orig, back)} 的指纹不同')

    def test_pickle_family_has_no_lambda_or_closure_member(self):
        """§四 专项：四族对象的成员里不得有 lambda / 闭包 / 局部函数 / partial / 模块。

        **与 round-trip 的分工**：round-trip 是权威判据（pickle 说了算），本扫描是
        定位层：pickle 的报错只有一句 `Can't pickle local object`，看不出挂在哪个
        保底的哪个零件的哪个字段，本扫描直接给出路径。两者都不可省：扫描只认类型表
        （第三方的不可 pickle 对象它认不出），round-trip 只认能否序列化（不给路径）。

        **本扫描是保守超集：命中不等于违规**，对若干**可 pickle** 的形态会假红
        （模块级 `def` / 可 pickle 的绑定方法 / 内建函数 / 可序列化的 `partial`），
        详见 `_FORBIDDEN_TYPES` 上方注释；真伪由 round-trip 复核。
        """
        env, _ = _family_env()
        offenders = []
        for name, bh in env.pity_engine.behaviors.items():
            _forbidden_members(bh, f'behaviors[{name!r}]', set(), offenders)
        assert offenders == [], f'四族对象里挂了不可 pickle 的成员：{offenders}'

    def test_pickle_worker_initializer_env_is_usable_and_parallelism_not_degraded(self):
        """worker initializer 实际收到可用的 env：判据是**并行度未退化**，不是「没报错」。

        **为什么「跑完了没报错」零检测力**：`run_batch_parallel` 对 MPPool 异常有三次
        逐级降并发重试（N → N/2 → N/4），而 env 不可 pickle 时异常发生在**父进程**
        （`initargs=(env, target_specs)` 由父进程 pickle 后才进 `Process.start()`），
        三次全败即落到**单进程兜底**：模拟照常跑完、结果照常返回，`warnings` 里
        **没有**任何一条能说明并行度已归零（唯一与降级相关的告警只在
        `profile_enabled` 为真时才记）。

        判据取 `BatchResult.parallel_metrics`（`collect_perf=True` 才采）：
        `worker_count` **只在 MPPool 路径**被赋值（兜底路径保持空 dict），且取自
        `Pool._processes` 即**最终成功那次**的进程数，`== max_workers` 同时排除
        「落到单进程兜底」与「降并发重试后成功」两种退化；`worker_task_counts` 的键
        是**子进程 pid**（worker 侧按 pid 落的计数文件），非空即证明 initializer 真的
        在子进程里跑完并注入了 env，而不只是池建起来了。
        """
        env, specs = _family_env()
        result = run_batch_parallel(
            env=env, target_specs=specs, initial_resources=env.initial_resources,
            num_simulations=4, max_workers=2, seed=2026, strategy_key='smart',
            collect_perf=True)
        metrics = result.parallel_metrics
        assert metrics.get('worker_count') == 2, (
            f'并行度退化：期望 workers=2 的 MPPool 路径，实得 worker_count='
            f'{metrics.get("worker_count")!r}（None = 落到单进程兜底；1 = 降并发重试成功）')
        child_pids = set(metrics.get('worker_task_counts') or {})
        assert child_pids and str(os.getpid()) not in child_pids, (
            f'worker 侧一个任务计数都没有（或计数落在父进程 pid 上）：{child_pids}')
        assert len(result) == 4, f'模拟未全部产出结果：{len(result)}/4'
        assert not [w for w in result.warnings if '次模拟失败' in w], result.warnings


#: 注册表**全量**零件类：另用 `create_behavior` 直构覆盖。
#:
#: **为何需要本组（2026-10-13 独立审查实测订正）**：原表述称「env 夹具受『每稀有度
#: 最多一个事件驱动型』约束装不下全部 10 个类型」，该前提**已被实测证伪**，真实理由
#: 是下面两条：
#:
#: ① **夹具选型的结果，不是结构限制**：默认配置只有 SSR / SR / R 三个 scope，而
#:    `_validate_behaviors` 限「每个稀有度最多一个事件驱动型」，11 个 btype 在三 scope
#:    下确实装不下。但这条约束**不是结构性的**：夹具本就绕过 TOML 白名单校验（直接
#:    `store.pity.pities = [...]`，不经 `config_toml._build_pity`），而
#:    `SimulationEnvBuilder.from_config_store` **不校验 scope 是否在 `[rarities].ranks`
#:    内**，实测以 `ssr/sr/r/x1/x2/x3/x4` 七个 scope 直设 11 个 btype 即构造成功、11 个
#:    `Pity`、四族皆产出对象、且该 env 可 pickle（**非**「覆盖集被满足」：该 env 的
#:    lifecycle 只到 `AlwaysActive`，modifier 缺 `NotOwnedModifier`）。即「不是装不下，
#:    是没这么装」。故 ① 只解释
#:    下面三个**可达但未纳入夹具**的类：`StreakTracker`（`rotating_cr` 族）、
#:    `NonFeaturedModifier`（`rotating_inverse`，产出方 `_preset_rotating_inverse`）、
#:    `DependentFiniteActive`（同一 `PityDef` 上同时给 `max_triggers` 与 `depends_on`）。
#: ② **`NotOwnedModifier` 自 S9-3 起有产出方**（2026-10-14 订正）：S9-3 之前该类在 M1
#:    无 preset 产出方（`core/pity.py` 未 import 它），旧表述据此称它「任何 env 都不可
#:    达」；**该前提已不成立**：`core/pity.py` 现已 import 该类，两条 G3 preset
#:    （`_preset_hard_exclude_owned_skip` / `_preset_hard_exclude_owned_any`）各产出一例，
#:    故该类**可达**，只是 env 夹具（`_FAMILY_PITY_DEFS` 五条保底）不含 G3 类型，
#:    env 的 pickle 图里仍不会出现它。
#:
#: **`NonFeaturedModifier` 与 `NotOwnedModifier` 的覆盖理由相同**：前者的产出方是
#: `_preset_rotating_inverse`，后者是上面两条 G3 preset，即**都有**产出方、都不在 env
#: 夹具里；本组（注册表全量直构）对二者的覆盖理由一致：补 env 夹具未纳入的零件类。
#:
#: 覆盖的 btype 数为 `len(BEHAVIOR_REGISTRY)`（不写死条数：该集合随注册表增长）。
_REGISTRY_FAMILY_COVERAGE = {
    'pity': {'Pity'},
    'tracker': {'CounterTracker', 'FlagTracker', 'StreakTracker', 'FateTracker',
                'NamespaceTracker'},
    'modifier': {'HardModifier', 'SoftModifier', 'RotatingModifier',
                 'NonFeaturedModifier', 'SelectedModifier', 'NotOwnedModifier'},
    'lifecycle': {'AlwaysActive', 'FiniteActive', 'DependentActive',
                  'DependentFiniteActive'},
}

#: 生命周期两个维度的四个取值组合（激活维 Always / Dependent × 退役维 Never / AfterN）。
_LIFECYCLE_VARIANTS = ({}, {'max_triggers': 2}, {'depends_on': 'x'},
                       {'max_triggers': 2, 'depends_on': 'x'})


def _registry_family_objects():
    """直构**注册表全量**的四族对象（`BEHAVIOR_REGISTRY` 全量 btype + 4 个生命周期
    组合 + 另直构的一例 `NotOwnedModifier`）。

    `NotOwnedModifier`（S2a-2 交付）自 **S9-3**（2026-10-14）起**有产出方**：`core/pity.py`
    import 该类，两条 G3 preset（`_preset_hard_exclude_owned_skip` / `_any`）各产出一例，
    故上面的 `pities` 遍历 `BEHAVIOR_REGISTRY` 时**已含**它（`threshold=50`、两形态各一，
    实测 2 例），该类的**类型出现性**由那一趟遍历承担、不再依赖本行。此处另直构一例
    （`threshold=5`、`on_all_owned` 取默认 `'skip'`），多覆盖一组构造参数下的 round-trip。
    另三个（`StreakTracker` / `NonFeaturedModifier` / `DependentFiniteActive`）属
    **夹具选型**所致、并非不可达，理由见 `_REGISTRY_FAMILY_COVERAGE` 上方注释。

    构造后调 `_bind_counter_to_pickle_graph`：同 env 夹具，`Counter` 不显式绑一次就
    不在图里（`CounterTracker._counter` 构造期为 `None`）。
    """
    from gacha_simulator.core.pity import BEHAVIOR_REGISTRY, create_behavior
    from gacha_simulator.core.pity_modifier import NotOwnedModifier
    from gacha_simulator.core.pity_primitives import PityState

    pities = [create_behavior(PityDef(name=f'x_{btype}', btype=btype), PityState())
              for btype in BEHAVIOR_REGISTRY]
    pities += [create_behavior(PityDef(name=f'x_lc{i}', btype='hard', **variant),
                               PityState())
               for i, variant in enumerate(_LIFECYCLE_VARIANTS)]
    _bind_counter_to_pickle_graph(pities)
    return {
        'pity': pities,
        'tracker': [t for bh in pities for t in bh._trackers],
        'modifier': ([m for bh in pities for m in bh._modifiers]
                     + [NotOwnedModifier('ssr', threshold=5)]),
        'lifecycle': [bh._lifecycle for bh in pities],
    }


class TestRegistryWidePickleCoverage:
    """§四 禁令与 round-trip 的**全量**覆盖面（补 env 夹具未纳入的零件类）。"""

    def test_pickle_registry_types_roundtrip_without_forbidden_member(self):
        """注册表全量零件：无禁令成员 + round-trip 逐字段相等。

        与 `TestFourFamilyPickleRoundtrip` 的分工：那一组走**真实 env 的 pickle 图**
        （计划 S7b 的验收形态），本组走**注册表全量直构**，把 env 夹具未纳入的类
        （`StreakTracker` / `NonFeaturedModifier` / `DependentFiniteActive`，夹具选型
        所致）与同为「env 夹具未纳入」的 `NotOwnedModifier`（产出方为两条 G3 preset）
        一并纳入「无 lambda / 闭包 / 不可 pickle 成员」的确认面。
        """
        fams = _registry_family_objects()
        got = {fam: {type(o).__name__ for o in objs} for fam, objs in fams.items()}
        for fam, expected in _REGISTRY_FAMILY_COVERAGE.items():
            assert got[fam] == expected, (
                f'{fam} 族的全量覆盖集变了：{sorted(got[fam])} != {sorted(expected)}')
        # 同 env 夹具的守卫：`Counter` 必须在图里（靠 `_bind_counter_to_pickle_graph`）。
        assert [t for t in fams['tracker'] if getattr(t, '_counter', None) is not None], (
            '全量组图里没有已绑定的 Counter：Counter 那一半的理由会重新未被行使')

        offenders = []
        for fam, objs in fams.items():
            for i, obj in enumerate(objs):
                _forbidden_members(obj, f'{fam}[{i}]', set(), offenders)
        assert offenders == [], f'四族对象里挂了不可 pickle 的成员：{offenders}'

        for fam, objs in fams.items():
            for orig in objs:
                back = pickle.loads(pickle.dumps(orig))
                assert type(orig) is type(back), (
                    f'{fam} 族的对象类型在 round-trip 后变了：'
                    f'{type(orig).__name__} → {type(back).__name__}')
                if _fingerprint(orig) != _fingerprint(back):
                    raise AssertionError(
                        f'{fam} 族的 {type(orig).__name__} 在 round-trip 后字段失真：'
                        f'字段 {_field_diffs(orig, back)} 的指纹不同')
