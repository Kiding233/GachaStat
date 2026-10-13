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


# ══════════════════════════════════════════════════════════════════
# P64 S4b / §3.6 AUDIT-BREAK-1：retreat_config 浅拷贝的字段全量保真
# ══════════════════════════════════════════════════════════════════
# 第三处透传点。原为 24 个字段的显式列举（曾漏拷 selected_card_init，即 ISSUE-132），
# 现由 `dataclasses.fields(PityDef)` 驱动——漏字段的失败形态是**静默落回默认值**。

def _all_fields_non_default() -> dict:
    """一条全部字段均为非默认值的 `PityDef` kwargs（取值同 S4b 的字段往返守卫）。"""
    return {
        'name': 'pity_full',
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
        'pools': ('pool_3.main',),
        'deactivate_on_early_hit': True,
        'depends_on': 'other',
        'max_triggers': 2,
        'reset': 'featured',
        'priority': 5,
    }


def _truncated_pity(pity_counter_init=None):
    store = _make_store_with_3_pools()
    store.pity.pities = [PityDef(**_all_fields_non_default())]
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='pool_2',
        initial_resources={'draw_resource': 5000},
        pity_counter_init=pity_counter_init or {},
    )
    assert len(truncated.pity.pities) == 1
    return truncated.pity.pities[0]


def test_truncate_preserves_every_pitydef_field():
    """截断浅拷贝逐字段等值——漏字段即静默落回默认值（AUDIT-BREAK-1）。"""
    import dataclasses

    store = _make_store_with_3_pools()
    store.pity.pities = [PityDef(**_all_fields_non_default())]
    src = store.pity.pities[0]
    truncated = RetreatConfigBuilder.build(
        original_store=store,
        from_pool_id='pool_2',
        initial_resources={'draw_resource': 5000},
        pity_counter_init={},
    )
    got = truncated.pity.pities[0]
    for f in dataclasses.fields(PityDef):
        assert getattr(got, f.name) == getattr(src, f.name), (
            f"字段 '{f.name}' 在截断浅拷贝中失真："
            f"{getattr(src, f.name)!r} → {getattr(got, f.name)!r}")
    assert got == src


def test_truncate_shallow_copy_carries_priority():
    """`priority` 是 S4b 新增字段——浅拷贝必须带上（第三处透传点，ISSUE-007）。"""
    assert _truncated_pity().priority == 5


def test_truncate_counter_init_override_still_wins():
    """counter_init 覆盖语义不受字段驱动改造影响（唯一改写点）。"""
    got = _truncated_pity({'pity_full': 30})
    assert got.counter_init == 30


# ══════════════════════════════════════════════════════════════════
# P64 S4-2 审查 important：截断 store 必须带上 `rarity_rank`
# ══════════════════════════════════════════════════════════════════
# 截断路径**不过 TOML 往返**（`PlanSearchEngine._build_env` 把 `RetreatConfigBuilder`
# 的产物直接喂 `SimulationEnvBuilder`），故 `ConfigStore()` 的空表会一路带到引擎。
# 旧 `SoftStepBehavior` 从 dist 键推导量来源 Q、不依赖本表；新 `SoftModifier` 的
# `_lower_rarities` 依赖它，空表下 `pool == 0` 即 `apply` 返回恒等，软保底**静默
# 失效**（退避点 / 最少资源搜索会低估保底效果、高估资源需求，且不报错）。

def test_truncate_copies_rarity_rank():
    """`rarity_rank` 与其余十余个字段同等对待，必须浅拷贝（S4-2 审查 important）。"""
    store = _make_store_with_3_pools()
    store.rarity_rank = {'SSR': 0, 'SR': 1, 'R': 2}
    truncated = RetreatConfigBuilder.build(
        original_store=store, from_pool_id='pool_2',
        initial_resources={'draw_resource': 5000}, pity_counter_init={})
    assert truncated.rarity_rank == {'SSR': 0, 'SR': 1, 'R': 2}


def test_truncated_env_soft_pity_is_not_identity():
    """截断 env 的软保底必须真的改动分布（漏拷 `rarity_rank` 时恒等）。

    **S8-2 起管道是卡级**（§3.9.1）：基础分布改由池内**卡 id** 构造——原写
    `base={'ssr': 0.02, 'r': 0.98}` 是槽位级键，卡级管道下 `transfer_linear`
    取 `dist[c]`（c 为卡 id）会直接 `KeyError`（**不是静默恒等**，这是 S8 键空间
    纪律的显形面）。实测（真实 config.toml、`from_pool_id='pool_c1'`、counter=90、
    按池内声明概率建基础分布）：空表下分布原样返回；补齐后 SSR 卡集的小计由
    池内声明值抬到 1.0（ssr 是最高稀有度，软保底的 Q = 更低稀有度卡，
    `amount` 封顶 `p(Q)`）。
    """
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.service.batch_simulator import SimulationEnvBuilder

    # 用真实配置（合成 store 的池 id 与保底 pool_specs 的键空间对不上，`spec=None`
    # 会在 `before_draw` 首行早退，测不到本缺陷）。
    store = load_toml('gacha_simulator/config/config.toml')
    truncated = RetreatConfigBuilder.build(
        original_store=store, from_pool_id='pool_c1',
        initial_resources={'draw_resource': 0.0},
        pity_counter_init={'ssr_soft': 90})
    assert truncated.rarity_rank, '截断 copy 丢了 rarity_rank'
    env = SimulationEnvBuilder.from_config_store(truncated)
    eng = env.pity_engine
    pool_id = truncated.pools[0].pool_id
    spec = eng.get_spec(pool_id)
    assert spec is not None, '截断后的池必须在 pool_specs 内（否则测不到本缺陷）'
    ssr_cards = tuple(spec.scope_cards['ssr'])
    base = {r.id: p for r, p in env.pools[0].active_pool.rewards}
    assert ssr_cards and len(base) > len(ssr_cards), \
        '本用例需要 SSR 与更低稀有度两类卡（Q 非空才谈得上搬质量）'

    out = eng.before_draw(pool_id, eng._state, dict(base))
    ssr_before = sum(base[c] for c in ssr_cards)
    ssr_after = sum(out[c] for c in ssr_cards)
    assert ssr_after > ssr_before, (
        f"截断路径的软保底恒等（SSR 卡集小计仍为 {ssr_after}）——"
        f"`rarity_rank` 未随截断复制")
