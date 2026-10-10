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
import os
import pickle

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
