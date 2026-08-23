"""P78 里程碑序列与自选券扩展测试——引擎断言 + 解析/校验断言。

覆盖（§5.2 阶段 6 子块）：
  6a1 引擎断言域（ISSUE-001/106）——直接构造 MilestoneEngine 实例（不经 TOML 解析，
      与阶段 2 解耦）：G18 节点 100/180/260/340、交替 A/B、offset×at=N、offset×max_triggers、
      repeat 归零 offset 不叠加、旧行为不回归、_resolve_bonus_from。
  6a2 解析/校验/哈希/截断断言域（ISSUE-006/007/112/120/111/119/113/118/108/107/130/
      129/131/503/606/603）——config_toml 解析新字段、校验器同构、条件写键、独立 gate、
      select_voucher 解析/补全/去重、hash 差异、截断透传。
"""
import warnings
import tempfile
import os

import pytest

from gacha_simulator.core.config_store import (
    ConfigStore, ConfigError, CardDefEntry, BannerEntry, BannerPoolEntry,
    MilestoneConfig, MilestoneDef, SelectVoucherDef, DAY,
)
from gacha_simulator.core.config_toml import (
    load_toml, save_toml,
    _validate_milestone_dict, _validate_select_voucher_dict,
)
from gacha_simulator.core.milestone import MilestoneEngine
from gacha_simulator.core.retreat_config import RetreatConfigBuilder
from gacha_simulator.core.result_store import compute_config_hash


# ══════════════════════════════════════════════════════════════════
# 6a1 引擎断言域（ISSUE-001/106——直接构造 MilestoneEngine，不经 TOML）
# ══════════════════════════════════════════════════════════════════

def _run_engine(md, n_draws):
    """跑 n_draws 次 after_draw，返回 [(draw_index, bonus), ...] 触发序列。"""
    eng = MilestoneEngine([md], seed=42)
    triggers = []
    for draw in range(1, n_draws + 1):
        for entry in eng.after_draw('b', 'p'):
            triggers.append((draw, entry['bonus']))
    return triggers


def test_g18_alternating_cycle_nodes_and_rewards():
    """ISSUE-001 + G18：threshold=80 offset=20 repeat=True → 100/180/260/340，A/B 交替。"""
    md = MilestoneDef(name='cyc', threshold=80, offset=20, repeat=True,
                      alternate_rewards=[{'resources': {'voucher': 1}}, {'cards': ['up']}])
    triggers = _run_engine(md, 360)
    expected = [
        (100, {'card_ids': [], 'resources': {'voucher': 1}}),
        (180, {'card_ids': ['up'], 'resources': {}}),
        (260, {'card_ids': [], 'resources': {'voucher': 1}}),
        (340, {'card_ids': ['up'], 'resources': {}}),
    ]
    assert triggers == expected, f"G18 节点/交替错误: {triggers}"


def test_offset_only_applies_to_first_node():
    """ISSUE-001：repeat 归零后 offset 不叠加——节点序列 100/180/260 而非 100/200/300。"""
    md = MilestoneDef(name='cyc', threshold=80, offset=20, repeat=True,
                      alternate_rewards=[{'cards': ['a']}, {'cards': ['b']}])
    nodes = [d for d, _ in _run_engine(md, 300)]
    assert nodes == [100, 180, 260], f"offset 重复叠加导致漂移: {nodes}"


def test_offset_with_at_once():
    """ISSUE-106：offset × at=N（repeat=False）——首触发 threshold+offset 且仅一次。"""
    md = MilestoneDef(name='at', threshold=80, offset=20, repeat=False)
    triggers = _run_engine(md, 200)
    assert [d for d, _ in triggers] == [100], f"at=N 应仅 100 触发一次: {triggers}"


def test_offset_with_max_triggers():
    """ISSUE-106：offset × max_triggers=2——节点 100/180 到上限停，交替正确。"""
    md = MilestoneDef(name='mt', threshold=80, offset=20, repeat=True, max_triggers=2,
                      alternate_rewards=[{'cards': ['A']}, {'cards': ['B']}])
    triggers = _run_engine(md, 400)
    assert [(d, b['card_ids']) for d, b in triggers] == [(100, ['A']), (180, ['B'])], f"max_triggers 错误: {triggers}"


def test_legacy_behavior_no_regression():
    """旧 every=N（无 offset/alternate）行为不变——每 threshold 抽一次。"""
    md = MilestoneDef(name='old', threshold=10, repeat=True, bonus_reward={'cards': ['x']})
    nodes = [d for d, _ in _run_engine(md, 40)]
    assert nodes == [10, 20, 30, 40], f"旧 every=N 回归: {nodes}"


def test_at_once_no_regression():
    """旧 at=N（无 offset/alternate）行为不变。"""
    md = MilestoneDef(name='old', threshold=300, repeat=False, bonus_reward={'cards': ['x']})
    nodes = [d for d, _ in _run_engine(md, 400)]
    assert nodes == [300], f"旧 at=N 回归: {nodes}"


def test_resolve_bonus_from_standalone():
    """_resolve_bonus_from 独立解析——cards/resources/random_cards 组合。"""
    eng = MilestoneEngine([], seed=42)
    r = eng._resolve_bonus_from({'cards': ['a'], 'resources': {'r': 1}})
    assert r == {'card_ids': ['a'], 'resources': {'r': 1}}


def test_resolve_bonus_delegates_to_from():
    """_resolve_bonus 保留委托壳——内部调用 _resolve_bonus_from。"""
    md = MilestoneDef(name='m', threshold=1, bonus_reward={'cards': ['x'], 'resources': {'r': 2}})
    eng = MilestoneEngine([md], seed=42)
    bonus = eng._resolve_bonus(md)
    assert bonus == {'card_ids': ['x'], 'resources': {'r': 2}}


# ══════════════════════════════════════════════════════════════════
# 6a2 解析/校验/哈希/截断断言域
# ══════════════════════════════════════════════════════════════════

def _make_toml(extra=''):
    return f"""
[[card]]
card_id = 'endfield_wp_std_1'
name = '陪跑1'
rarity = 'ssr'
[[card]]
card_id = 'endfield_wp_std_2'
name = '陪跑2'
rarity = 'ssr'
[[card]]
card_id = 'endfield_current_up_wp'
name = '当期UP'
rarity = 'ssr'

[resources.defs]
endfield_supply_voucher = '武库箱券'
[resources.initial]
endfield_supply_voucher = 0
{extra}
"""


def _load(text):
    with tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False, encoding='utf-8') as f:
        f.write(text)
        tmp = f.name
    try:
        return load_toml(tmp)
    finally:
        os.unlink(tmp)


def test_parse_new_fields_and_roundtrip():
    """ISSUE-006/113：解析 alternate_rewards/offset + select_voucher 段 + round-trip。"""
    text = _make_toml("""
[[milestone]]
name = 'cyc'
threshold = 80
offset = 20
repeat = true
alternate_rewards = [
    { resources = { endfield_supply_voucher = 1 } },
    { cards = ['endfield_current_up_wp'] },
]

[[select_voucher]]
voucher = 'endfield_supply_voucher'
cards = ['endfield_wp_std_1', 'endfield_wp_std_2']
""")
    store = _load(text)
    md = store.milestone.milestones[0]
    assert md.offset == 20 and len(md.alternate_rewards) == 2
    assert md.alternate_rewards[0]['resources']['endfield_supply_voucher'] == 1
    assert store.select_vouchers[0].voucher == 'endfield_supply_voucher'
    assert store.select_vouchers[0].cards == ['endfield_wp_std_1', 'endfield_wp_std_2']
    # round-trip
    with tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False, encoding='utf-8') as f:
        tmp = f.name
    try:
        save_toml(store, tmp)
        store2 = load_toml(tmp)
        assert store2.milestone.milestones[0].offset == 20
        assert len(store2.milestone.milestones[0].alternate_rewards) == 2
        assert store2.select_vouchers[0].cards == ['endfield_wp_std_1', 'endfield_wp_std_2']
    finally:
        os.unlink(tmp)


def test_voucher_setdefault_preserves_display_name():
    """ISSUE-119：select_voucher 补全 resource_defs 用 setdefault——既有显示名不被覆盖。"""
    store = _load(_make_toml("""
[[select_voucher]]
voucher = 'endfield_supply_voucher'
cards = ['endfield_wp_std_1']
"""))
    assert store.resource_defs['endfield_supply_voucher'] == '武库箱券'


def test_explicit_empty_alternate_rewards_rejected():
    """ISSUE-112 规则 1：显式 alternate_rewards = [] 抛 ConfigError（键缺失走默认不抛）。"""
    with pytest.raises(ConfigError):
        _load(_make_toml("""
[[milestone]]
name = 'cyc'
threshold = 80
alternate_rewards = []
"""))


def test_empty_alternate_item_rejected():
    """ISSUE-112 规则 2：空 dict 项 {} 抛 ConfigError。"""
    with pytest.raises(ConfigError):
        _load(_make_toml("""
[[milestone]]
name = 'cyc'
threshold = 80
repeat = true
alternate_rewards = [ {} ]
"""))


def test_single_alternate_warning():
    """ISSUE-120：单元素交替列表发 warning（不崩溃）。"""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        _load(_make_toml("""
[[milestone]]
name = 'cyc'
threshold = 80
repeat = true
alternate_rewards = [ { cards = ['endfield_current_up_wp'] } ]
"""))
    assert any('单元素' in str(x.message) for x in w), '单元素交替列表应发 warning'


def test_negative_offset_rejected():
    """ISSUE-007/501：负 offset 显式拒绝。"""
    with pytest.raises(ConfigError):
        _load(_make_toml("""
[[milestone]]
name = 'cyc'
threshold = 80
offset = -1
"""))


def test_offset_bool_rejected():
    """ISSUE-007：offset 拒 bool（isinstance(True, int) 陷阱）。"""
    with pytest.raises(ConfigError):
        _load(_make_toml("""
[[milestone]]
name = 'cyc'
threshold = 80
offset = true
"""))


def test_d6_d7_warning():
    """D6/D7：offset×at=N、alternate×repeat=False 发 warning（不崩溃）。"""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        _load(_make_toml("""
[[milestone]]
name = 'm1'
threshold = 80
offset = 20

[[milestone]]
name = 'm2'
threshold = 80
alternate_rewards = [ { cards = ['endfield_current_up_wp'] }, { cards = ['endfield_wp_std_1'] } ]
"""))
    msgs = [str(x.message) for x in w]
    assert any('repeat=False' in m for m in msgs), f"D6/D7 warning 缺失: {msgs}"


def test_conditional_write_key_omits_empty():
    """ISSUE-113：无交替/零偏移里程碑写出省略键；显式配置写出。"""
    store = ConfigStore()
    store.card_defs = [CardDefEntry(card_id='c1', rarity='ssr')]
    store.milestone.milestones = [MilestoneDef(name='plain', threshold=10, repeat=True)]
    with tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False, encoding='utf-8') as f:
        tmp = f.name
    try:
        save_toml(store, tmp)
        txt = open(tmp, encoding='utf-8').read()
        assert 'alternate_rewards' not in txt and 'offset' not in txt, '空键被写出'
        store2 = load_toml(tmp)
        assert store2.milestone.milestones[0].offset == 0
        assert store2.milestone.milestones[0].alternate_rewards == []
    finally:
        os.unlink(tmp)


def test_select_voucher_independent_gate():
    """ISSUE-118：milestone 禁用但 select_vouchers 非空 → 段存活。"""
    store = ConfigStore()
    store.card_defs = [CardDefEntry(card_id='c1', rarity='ssr')]
    store.milestone = MilestoneConfig(enabled=False, milestones=[])
    store.select_vouchers = [SelectVoucherDef(voucher='v1', cards=['c1'])]
    with tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False, encoding='utf-8') as f:
        tmp = f.name
    try:
        save_toml(store, tmp)
        store2 = load_toml(tmp)
        assert len(store2.select_vouchers) == 1, 'select_voucher 段被 milestone gate 误伤'
    finally:
        os.unlink(tmp)


def test_select_voucher_duplicate_voucher_rejected():
    """ISSUE-111：voucher id 重复抛 ConfigError。"""
    with pytest.raises(ConfigError):
        _load(_make_toml("""
[[select_voucher]]
voucher = 'v1'
cards = ['endfield_wp_std_1']
[[select_voucher]]
voucher = 'v1'
cards = ['endfield_wp_std_2']
"""))


def test_select_voucher_unknown_card_rejected():
    """ISSUE-111：候选卡引用不存在抛 ConfigError。"""
    with pytest.raises(ConfigError):
        _load(_make_toml("""
[[select_voucher]]
voucher = 'v1'
cards = ['no_such_card']
"""))


def test_select_voucher_empty_cards_warning():
    """ISSUE-111：空候选集允许但发 warning。"""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        store = _load(_make_toml("""
[[select_voucher]]
voucher = 'v1'
cards = []
"""))
    assert store.select_vouchers[0].cards == []
    assert any('候选集为空' in str(x.message) for x in w)


def test_voucher_build_position_after_cards():
    """ISSUE-129：_build_select_voucher 在 _build_cards 后执行（候选卡校验需 card_defs 就绪）。"""
    store = _load(_make_toml("""
[[select_voucher]]
voucher = 'v1'
cards = ['endfield_wp_std_1', 'endfield_wp_std_2']
"""))
    assert len(store.select_vouchers) == 1  # 合法卡被正确校验通过


def test_validate_milestone_dict_interface():
    """ISSUE-114/201/606：_validate_milestone_dict 全量同构——非法值被拒。"""
    kc = {'c1', 'c2'}
    mdv = _validate_milestone_dict(
        {'name': 'x', 'threshold': 80, 'offset': 20, 'repeat': True,
         'alternate_rewards': [{'cards': ['c1']}, {'resources': {'r': 1}}]}, kc)
    assert mdv.offset == 20 and len(mdv.alternate_rewards) == 2
    for bad in [{'name': 'x', 'offset': -1}, {'name': 'x', 'alternate_rewards': [{}]},
                {'name': 'x', 'threshold': -5}, {'name': 'x', 'threshold': 'five'}, {'name': ''}]:
        with pytest.raises(ConfigError):
            _validate_milestone_dict(bad, kc)


def test_validate_milestone_dict_preserves_bonus_empty():
    """ISSUE-503：bonus_reward={} 空奖励里程碑合法（allow_empty=True 原样保留空 {}）。"""
    mdv = _validate_milestone_dict({'name': 'x', 'threshold': 10}, {'c1'})
    assert mdv.bonus_reward == {}, f"空 bonus_reward 应原样保留: {mdv.bonus_reward}"


def test_validate_select_voucher_dict_interface():
    """ISSUE-116/201：_validate_select_voucher_dict 同构——重复/不存在卡被拒。"""
    kc = {'c1', 'c2'}
    sv = _validate_select_voucher_dict([{'voucher': 'v', 'cards': ['c1']}], kc)
    assert sv[0].voucher == 'v' and sv[0].cards == ['c1']
    with pytest.raises(ConfigError):
        _validate_select_voucher_dict([{'voucher': 'v', 'cards': ['nope']}], kc)
    with pytest.raises(ConfigError):
        _validate_select_voucher_dict([{'voucher': 'v', 'cards': []}, {'voucher': 'v', 'cards': []}], kc)


def test_validate_milestone_dict_normalizes_string_weights():
    """ISSUE-701：set_config 入口字符串数值权重规范化写回——引擎 rng.choices 不崩。"""
    kc = {'c1', 'c2'}
    mdv = _validate_milestone_dict(
        {'name': 'x', 'threshold': 10,
         'bonus_reward': {'random_cards': [{'candidates': ['c1', 'c2'], 'weights': ['0.1', '0.2']}]}},
        kc)
    rc = mdv.bonus_reward['random_cards'][0]
    assert all(isinstance(w, float) for w in rc['weights']), f"权重未规范化: {rc['weights']}"
    assert rc['count'] == 1


def test_retreat_config_transmits_new_fields():
    """ISSUE-107/130：截断分支透传 alternate_rewards/offset + select_vouchers。"""
    store = ConfigStore()
    store.banner.banners = [
        BannerEntry(id='pool_1', name='池1', available_from=0 * DAY, available_until=21 * DAY,
                    pools=[BannerPoolEntry(id='main', cost='draw_resource:160')]),
        BannerEntry(id='pool_2', name='池2', available_from=21 * DAY, available_until=42 * DAY,
                    pools=[BannerPoolEntry(id='main', cost='draw_resource:160')]),
    ]
    store.card_defs = [CardDefEntry(card_id='c1', name='A', rarity='SSR', pools=['pool_1', 'pool_2'])]
    store.milestone = MilestoneConfig(enabled=True, milestones=[MilestoneDef(
        name='m1', threshold=80, offset=20, repeat=True,
        alternate_rewards=[{'cards': ['c1']}, {'resources': {'r': 1}}])])
    store.select_vouchers = [SelectVoucherDef(voucher='v1', cards=['c1'])]
    t = RetreatConfigBuilder.build(store, 'pool_2', {}, {})
    assert t.milestone.milestones[0].offset == 20, '截断 offset 丢失'
    assert len(t.milestone.milestones[0].alternate_rewards) == 2, '截断交替丢失'
    assert t.select_vouchers[0].voucher == 'v1', '截断 select_vouchers 丢失'


def test_config_hash_reflects_new_fields():
    """ISSUE-108：仅新字段不同 → hash 不同。"""
    h1 = compute_config_hash([], None, [], MilestoneConfig(milestones=[MilestoneDef(name='m', threshold=80)]))
    h2 = compute_config_hash([], None, [], MilestoneConfig(milestones=[MilestoneDef(name='m', threshold=80, offset=20)]))
    h3 = compute_config_hash([], None, [], MilestoneConfig(milestones=[MilestoneDef(
        name='m', threshold=80, offset=20, alternate_rewards=[{'cards': ['a']}])]))
    assert h1 != h2 and h2 != h3 and h1 != h3, 'hash 差异未反映新字段'


# ══════════════════════════════════════════════════════════════════
# 6c 服务层集成（ISSUE-009/103/010/106——经 run_batch_parallel）
# ══════════════════════════════════════════════════════════════════

def _make_integration_store():
    """构造含交替里程碑 + select_voucher 的 store（模拟 G18 武器池）。"""
    store = ConfigStore()
    b = BannerEntry(id='b1', name='武器池', enabled=True,
                    available_from=0.0, available_until=None,
                    pools=[BannerPoolEntry(
                        id='main', cost='draw_resource:160',
                        rewards=[
                            {'card_id': 'up', 'probability': 4.0, 'rarity': 'SSR', 'featured': True},
                            {'card_id': 'std1', 'probability': 4.0, 'rarity': 'SSR'},
                            {'card_id': '_no_card', 'probability': 92.0, 'rarity': 'R'},
                        ])])
    store.banner.banners = [b]
    store.card_defs = [
        CardDefEntry(card_id='up', name='当期UP', rarity='ssr'),
        CardDefEntry(card_id='std1', name='陪跑1', rarity='ssr'),
    ]
    store.resource_defs = {'draw_resource': '抽卡资源', 'voucher1': '武库箱券'}
    store.initial_resources = {'draw_resource': 1000000}
    store.milestone = MilestoneConfig(enabled=True, milestones=[
        MilestoneDef(name='wp_cycle', threshold=80, offset=20, repeat=True,
                     alternate_rewards=[
                         {'resources': {'voucher1': 1}},
                         {'cards': ['up']},
                     ]),
    ])
    store.select_vouchers = [SelectVoucherDef(voucher='voucher1', cards=['std1'])]
    store.strategy_key = 'smart'
    return store


def test_integration_node_rhythm_and_voucher_flow():
    """ISSUE-009/103/010/106：固定种子模拟——节点节奏 100/180/260/340、券进 total_gained、
    候选卡不进 acquired（只记券不落卡）。"""
    from gacha_simulator.core.stop_condition import FixedActionCountCondition
    from gacha_simulator.service.batch_simulator import (
        SimulationEnvBuilder, run_batch_parallel,
    )

    store = _make_integration_store()
    env = SimulationEnvBuilder.from_config_store(store)
    env.stop_condition = FixedActionCountCondition(max_actions=340)
    batch = run_batch_parallel(
        env=env, target_specs={}, initial_resources=env.initial_resources,
        num_simulations=1, max_workers=1, seed=42,
        strategy_key='fixed_count', strategy_params={'count': 340},
    )
    result = batch.results[0]

    # 节点节奏：固定抽数 340 → 抽满 340，交替里程碑触发 4 次（100/180/260/340）
    # 每次触发发 1 券 或 1 卡——验证 total_gained 含 voucher1 且 final_resources 保留券
    assert result.total_gained.get('voucher1', 0) == 2, \
        f"武库箱券应进 total_gained（100/260 触发）: {result.total_gained}"
    # 只记券不落卡：券保留在 final_resources（未被消耗兑换），候选卡 std1 未落地
    assert result.final_resources.get('voucher1', 0) == 2, \
        f"武库箱券应保留在 final_resources（只记券不落卡）: {result.final_resources}"

