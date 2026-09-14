import pytest
from gacha_simulator.core.config_store import (
    ConfigStore, PityConfig, PityDef, GainRule, DayOverride,
    TargetCardEntry, CardDefEntry, BannerEntry, BannerPoolEntry,
    LifecycleRuleEntry, DAY,
)
from gacha_simulator.core.retreat_config import RetreatConfigBuilder


def _make_store_with_3_pools():
    store = ConfigStore()
    # P61（§3.9）：写入侧为 store.banner.banners，每个旧池 → 一个 Banner（内层 pool id="main"）
    store.banner.banners = [
        BannerEntry(id='pool_1', name='池1',
                    available_from=0 * DAY, available_until=21 * DAY,
                    pools=[BannerPoolEntry(id='main', cost='draw_resource:160')]),
        BannerEntry(id='pool_2', name='池2',
                    available_from=21 * DAY, available_until=42 * DAY,
                    pools=[BannerPoolEntry(id='main', cost='draw_resource:160')]),
        BannerEntry(id='pool_3', name='池3',
                    available_from=42 * DAY, available_until=63 * DAY,
                    pools=[BannerPoolEntry(id='main', cost='draw_resource:160')]),
    ]
    store.pity = PityConfig(enabled=True, pities=[
        PityDef(name='soft_pity', btype='soft_interval', scope='ssr',
                soft_start=74, soft_end=90, counter_init=0,
                deltas=((74, 0.0), (16, 6.25))),
    ])
    store.gain_rules = [
        GainRule(rule_type='every_n_days', param='1', gains={'draw_resource': 100}),
    ]
    store.day_overrides = [
        DayOverride(day=5, gains={'draw_resource': 500}),
        DayOverride(day=30, gains={'draw_resource': 1000}),
        DayOverride(day=50, gains={'draw_resource': 2000}),
        DayOverride(day=70, gains={'draw_resource': 3000}),
    ]
    store.initial_resources = {'draw_resource': 30000}
    store.target_cards = [
        TargetCardEntry(card_id='card_a', quantity=1),
        TargetCardEntry(card_id='card_b', quantity=1),
    ]
    store.card_defs = [
        CardDefEntry(card_id='card_a', name='A', rarity='SSR', pools=['pool_1', 'pool_2']),
        CardDefEntry(card_id='card_b', name='B', rarity='SSR', pools=['pool_3']),
    ]
    return store


def test_truncate_removes_earlier_pools():
    store = _make_store_with_3_pools()
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='pool_2',
        initial_resources={'draw_resource': 5000},
        pity_counter_init={'soft_pity': 30},
    )
    pool_ids = [p.pool_id for p in truncated.pools]
    # P61：展平视图 pool_id 为全限定键 {banner_id}.main
    assert 'pool_1.main' not in pool_ids
    assert 'pool_2.main' not in pool_ids
    assert 'pool_3.main' in pool_ids
    assert len(truncated.pools) == 1


def test_truncate_offsets_pool_days():
    store = _make_store_with_3_pools()
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='pool_2',
        initial_resources={'draw_resource': 5000},
        pity_counter_init={'soft_pity': 30},
    )
    pool_3 = truncated.pools[0]
    assert pool_3.start_day == 0
    assert pool_3.end_day == 21


def test_truncate_sets_initial_resources():
    store = _make_store_with_3_pools()
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='pool_2',
        initial_resources={'draw_resource': 5000},
        pity_counter_init={'soft_pity': 30},
    )
    assert truncated.initial_resources == {'draw_resource': 5000}


def test_truncate_sets_pity_counter_init():
    store = _make_store_with_3_pools()
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='pool_2',
        initial_resources={'draw_resource': 5000},
        pity_counter_init={'soft_pity': 30},
    )
    # P55：counter_init 已从 PityConfig 移至每个 PityDef
    counter_inits = {p.name: p.counter_init for p in truncated.pity.pities}
    assert counter_inits['soft_pity'] == 30


def test_truncate_offsets_day_overrides():
    store = _make_store_with_3_pools()
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='pool_2',
        initial_resources={'draw_resource': 5000},
        pity_counter_init={'soft_pity': 30},
    )
    override_days = [o.day for o in truncated.day_overrides]
    assert 5 not in override_days
    assert 8 in override_days
    assert 28 in override_days


def test_truncate_preserves_gain_rules():
    store = _make_store_with_3_pools()
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='pool_2',
        initial_resources={'draw_resource': 5000},
        pity_counter_init={'soft_pity': 30},
    )
    assert len(truncated.gain_rules) == 1
    assert truncated.gain_rules[0].rule_type == 'every_n_days'


def test_truncate_preserves_target_cards():
    store = _make_store_with_3_pools()
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='pool_2',
        initial_resources={'draw_resource': 5000},
        pity_counter_init={'soft_pity': 30},
    )
    tc_ids = [tc.card_id for tc in truncated.target_cards]
    assert 'card_a' in tc_ids
    assert 'card_b' in tc_ids


def test_truncate_preserves_card_defs():
    store = _make_store_with_3_pools()
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='pool_2',
        initial_resources={'draw_resource': 5000},
        pity_counter_init={'soft_pity': 30},
    )
    cd_ids = [cd.card_id for cd in truncated.card_defs]
    assert 'card_a' in cd_ids
    assert 'card_b' in cd_ids


def test_truncate_invalid_pool_raises():
    store = _make_store_with_3_pools()
    with pytest.raises(ValueError):
        RetreatConfigBuilder.build(
            original_store=store,
            from_pool_id='nonexistent',
            initial_resources={'draw_resource': 5000},
            pity_counter_init={},
        )


def test_truncate_permanent_banner_offset():
    """退避点为永久 Banner（end_day=None）时 offset_day 不抛 TypeError（ISSUE-002）。

    offset_day 兜底 start_day+21；永久 Banner 在退避点之前被截断，之后池保留。
    """
    store = ConfigStore()
    store.banner.banners = [
        BannerEntry(id='perm', name='永久',
                    available_from=0 * DAY, available_until=None,  # 永久池
                    pools=[BannerPoolEntry(id='main', cost='draw_resource:160')]),
        BannerEntry(id='after', name='之后',
                    available_from=21 * DAY, available_until=42 * DAY,
                    pools=[BannerPoolEntry(id='main', cost='draw_resource:160')]),
    ]
    store.pity = PityConfig(enabled=False)
    store.gain_rules = []
    store.initial_resources = {'draw_resource': 5000}
    # 从永久池退避——offset_day 兜底 start_day+21=21，不抛 TypeError
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='perm.main',
        initial_resources={'draw_resource': 5000},
        pity_counter_init={},
    )
    # 永久池在退避点之前被截断；之后池保留
    assert [b.id for b in truncated.banner.banners] == ['after']


def test_truncate_permanent_pool_preserved_none():
    """永久 Banner 在退避点之后保留时，重建写侧 end_day 保持 None（ISSUE-002 写侧分支）。"""
    store = ConfigStore()
    store.banner.banners = [
        BannerEntry(id='early', name='早池',
                    available_from=0 * DAY, available_until=21 * DAY,
                    pools=[BannerPoolEntry(id='main', cost='draw_resource:160')]),
        BannerEntry(id='perm', name='永久',
                    available_from=21 * DAY, available_until=None,  # 永久池，在退避点之后
                    pools=[BannerPoolEntry(id='main', cost='draw_resource:160')]),
    ]
    store.pity = PityConfig(enabled=False)
    store.gain_rules = []
    store.initial_resources = {'draw_resource': 5000}
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='early.main',
        initial_resources={'draw_resource': 5000},
        pity_counter_init={},
    )
    # 永久池保留（from=21 >= offset=21）且写侧 available_until 保持 None（不抛 TypeError）
    perm = [b for b in truncated.banner.banners if b.id == 'perm']
    assert perm and perm[0].available_until is None


def test_truncate_multi_pool_banner_preserved():
    """多池 Banner 退避不丢池 + lifecycle 规则复制（D3/D4 修复）。"""
    store = ConfigStore()
    store.banner.banners = [
        BannerEntry(id='early', name='早池',
                    available_from=0 * DAY, available_until=30 * DAY,
                    pools=[BannerPoolEntry(id='main', cost='draw_resource:160')]),
        BannerEntry(id='multi', name='多池',
                    available_from=30 * DAY, available_until=60 * DAY,
                    max_draws=20,  # banner 级抽数上限（新手池自动 exhaust）
                    pools=[
                        BannerPoolEntry(id='main', cost='draw_resource:160'),
                        BannerPoolEntry(id='free', cost='ticket:1'),
                    ],
                    lifecycle=[LifecycleRuleEntry(condition='pool_draws', pool='main',
                                                  at=30, action='switch_to', target='free')]),
    ]
    store.pity = PityConfig(enabled=False)
    store.gain_rules = []
    store.initial_resources = {'draw_resource': 5000}
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='early.main',
        initial_resources={'draw_resource': 5000},
        pity_counter_init={},
    )
    multi = [b for b in truncated.banner.banners if b.id == 'multi']
    assert len(multi) == 1, '多池 Banner 不应拆成重复 id（构造桥收纳丢池）'
    assert [p.id for p in multi[0].pools] == ['main', 'free'], '多池不丢'
    assert len(multi[0].lifecycle) == 1, 'lifecycle 规则应复制'
    assert multi[0].max_draws == 20, 'banner 级 max_draws 应透传（复审查修复）'


def test_truncate_after_normalized_permanent():
    """生产路径（load_toml 归一后）从「原永久」池退避：offset_day 用归一后的 end_day，不崩。"""
    store = ConfigStore()
    # 模拟归一后：原永久池 available_until 已是具体值（最后一个有结束时间的池）
    store.banner.banners = [
        BannerEntry(id='perm', name='永久',
                    available_from=0 * DAY, available_until=42 * DAY,
                    pools=[BannerPoolEntry(id='main', cost='draw_resource:160')]),
        BannerEntry(id='after', name='之后',
                    available_from=42 * DAY, available_until=63 * DAY,
                    pools=[BannerPoolEntry(id='main', cost='draw_resource:160')]),
    ]
    store.pity = PityConfig(enabled=False)
    store.gain_rules = []
    store.initial_resources = {'draw_resource': 5000}
    # 从归一后的「永久」池退避（offset_day = 42）
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='perm.main',
        initial_resources={'draw_resource': 5000},
        pity_counter_init={},
    )
    # perm 在退避点前截断；after 保留
    assert [b.id for b in truncated.banner.banners] == ['after']


def _make_store_with_multi_pool_banner():
    """多 pool banner（b1 含 main/step1）+ 单池 banner（b2）。"""
    store = ConfigStore()
    store.banner.banners = [
        BannerEntry(id='b1', name='周年庆',
                    available_from=0 * DAY, available_until=42 * DAY,
                    pools=[
                        BannerPoolEntry(id='main', cost='draw_resource:160'),
                        BannerPoolEntry(id='step1', cost='draw_resource:160'),
                    ]),
        BannerEntry(id='b2', name='武器特选',
                    available_from=42 * DAY, available_until=63 * DAY,
                    pools=[BannerPoolEntry(id='main', cost='draw_resource:160')]),
    ]
    store.pity = PityConfig(enabled=True, pities=[])
    store.gain_rules = []
    store.day_overrides = []
    store.initial_resources = {'draw_resource': 30000}
    store.target_cards = []
    store.card_defs = []
    return store


def test_empty_from_pool_id_raises_value_error():
    """ISSUE-129 falsy 守卫：from_pool_id=None/''/空白串统一 ValueError，
    消息含「Pool ... not found in config」（与既有错误路径统一），不裸抛 TypeError。"""
    store = _make_store_with_3_pools()
    for bad in (None, '', '  '):
        with pytest.raises(ValueError, match="not found in config"):
            RetreatConfigBuilder.build(
                original_store=store, from_pool_id=bad,
                initial_resources={}, pity_counter_init={})


def test_multi_pool_banner_fallback_hits_banner_start():
    """ISSUE-109 兜底语义（路线 A 接受项）：多 pool banner 下 build('b1') 不崩溃。

    兜底命中遍历序首个池（b1.main），offset_day 取 b1 结束日（42）→ 截断保留
    available_from >= 42 的 banner（b2）；与精确 build('b1.main') 结果一致，
    验证「起始粒度 = banner、命中首个池 = 活动起点」的接受项语义。
    """
    store = _make_store_with_multi_pool_banner()
    truncated = RetreatConfigBuilder.build(
        original_store=store, from_pool_id='b1',
        initial_resources={'draw_resource': 5000}, pity_counter_init={})
    pool_ids = [p.pool_id for p in truncated.pools]
    # offset_day = b1.main.end_day(42) → 截断保留 available_from >= 42 的 banner（b2）
    assert pool_ids == ['b2.main'], f'got {pool_ids}'
    # 与精确命中 b1.main 结果一致（兜底取遍历序首个池 = 活动起点语义）
    exact = RetreatConfigBuilder.build(
        original_store=store, from_pool_id='b1.main',
        initial_resources={'draw_resource': 5000}, pity_counter_init={})
    assert [p.pool_id for p in exact.pools] == pool_ids


def test_min_resource_build_env_banner_fallback_equiv():
    """ISSUE-110：min_resource 模式共用 _build_env 截断路径（RetreatConfigBuilder.build）。

    路线 A 兜底（from_pool_id='b1' 命中首个池 b1.main）与精确（'b1.main'）经 _build_env
    产出的模拟环境截断一致——min_resource 搜索在两种入口下环境等价（不可逆语义变化的
    等价性基线）。
    """
    from gacha_simulator.core.retreat_search import PlanSearchEngine

    store = _make_store_with_multi_pool_banner()
    env1 = PlanSearchEngine(store, from_pool_id='b1')._build_env(5000.0)
    env2 = PlanSearchEngine(store, from_pool_id='b1.main')._build_env(5000.0)
    ids1 = sorted(b.id for b in env1.pools)
    ids2 = sorted(b.id for b in env2.pools)
    assert ids1 == ids2, f'env1={ids1} env2={ids2}'
    assert ids1 == ['b2']  # offset_day=b1.end_day(42) → 截断保留 b2
    assert env1.pool_end_times == env2.pool_end_times
