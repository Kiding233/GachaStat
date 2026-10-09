from gacha_simulator.core.worst_impact import (
    ConditionalResourceDistribution,
    WorstImpactResult,
)


def _check_success_from_counts(obtained, target_specs):
    if not target_specs:
        return True
    for card_id, needed in target_specs.items():
        if obtained.get(card_id, 0) < needed:
            return False
    return True


def test_check_success_from_counts_all_obtained():
    assert _check_success_from_counts(
        {'char_a': 1, 'char_b': 2}, {'char_a': 1, 'char_b': 2}
    ) is True


def test_check_success_from_counts_partial():
    assert _check_success_from_counts(
        {'char_a': 1, 'char_b': 0}, {'char_a': 1, 'char_b': 1}
    ) is False


def test_check_success_from_counts_empty_targets():
    assert _check_success_from_counts({'char_a': 1}, {}) is True


def test_check_success_from_counts_missing_card():
    assert _check_success_from_counts(
        {'char_a': 1}, {'char_b': 1}
    ) is False


def test_conditional_resource_distribution():
    simulation_results = [
        {
            'card_counts': {'char_a': 1, 'char_b': 1},
            'final_resources': {'draw_resource': 1000},
        },
        {
            'card_counts': {'char_a': 0, 'char_b': 1},
            'final_resources': {'draw_resource': 200},
        },
        {
            'card_counts': {'char_a': 1, 'char_b': 1},
            'final_resources': {'draw_resource': 800},
        },
    ]
    target_specs = {'char_a': 1, 'char_b': 1}

    def checker(r):
        return _check_success_from_counts(r.get('card_counts', {}), target_specs)

    dist = ConditionalResourceDistribution(simulation_results, checker)

    assert len(dist.success_resources) == 2
    assert len(dist.failure_resources) == 1
    assert dist.success_resources == [1000, 800]
    assert dist.failure_resources == [200]


def test_conditional_distribution_all_condition():
    simulation_results = [
        {'card_counts': {'a': 1}, 'final_resources': {'draw_resource': 1000}},
        {'card_counts': {'a': 0}, 'final_resources': {'draw_resource': 200}},
    ]
    target_specs = {'a': 1}

    def checker(r):
        return _check_success_from_counts(r.get('card_counts', {}), target_specs)

    dist = ConditionalResourceDistribution(simulation_results, checker)

    all_dist = dist.get_conditional_distribution('all')
    assert all_dist.n == 2
    assert all_dist.mean() == 600.0


def test_worst_case_resource_failure():
    simulation_results = [
        {'card_counts': {'a': 1}, 'final_resources': {'draw_resource': 1000}},
        {'card_counts': {'a': 0}, 'final_resources': {'draw_resource': 200}},
        {'card_counts': {'a': 0}, 'final_resources': {'draw_resource': 100}},
    ]
    target_specs = {'a': 1}

    def checker(r):
        return _check_success_from_counts(r.get('card_counts', {}), target_specs)

    dist = ConditionalResourceDistribution(simulation_results, checker)
    worst = dist.get_worst_case_resource('failure', 0.5)
    assert worst == 150.0


def test_worst_impact_result_dataclass():
    result = WorstImpactResult(
        worst_resource=500.0,
        pity_coverage=0.35,
        pool_distribution={0: 0.3, 1: 0.5, 2: 0.2},
        expected_pools=0.9,
    )
    assert result.worst_resource == 500.0
    assert result.pity_coverage == 0.35
    assert result.expected_pools == 0.9


def test_worst_impact_result_get_p_ge():
    result = WorstImpactResult(
        worst_resource=500.0,
        pity_coverage=0.35,
        pool_distribution={0: 0.1, 1: 0.35, 2: 0.4, 3: 0.15},
        expected_pools=1.6,
    )
    assert abs(result.get_p_ge(0) - 1.0) < 1e-9
    assert abs(result.get_p_ge(1) - 0.9) < 1e-9
    assert abs(result.get_p_ge(2) - 0.55) < 1e-9
    assert abs(result.get_p_ge(3) - 0.15) < 1e-9
    assert abs(result.get_p_ge(4) - 0.0) < 1e-9


def test_worst_impact_result_max_consecutive_at_threshold():
    result = WorstImpactResult(
        worst_resource=500.0,
        pity_coverage=0.35,
        pool_distribution={0: 0.1, 1: 0.35, 2: 0.4, 3: 0.15},
        expected_pools=1.6,
    )
    assert result.get_max_consecutive_at_threshold(1.0) == 0
    assert result.get_max_consecutive_at_threshold(0.9) == 1
    assert result.get_max_consecutive_at_threshold(0.5) == 2
    assert result.get_max_consecutive_at_threshold(0.1) == 3


def test_worst_impact_result_empty_distribution():
    result = WorstImpactResult(
        worst_resource=0.0,
        pity_coverage=0.0,
    )
    assert result.get_p_ge(0) == 0.0
    assert result.get_p_ge(1) == 0.0
    assert result.get_max_consecutive_at_threshold(0.5) == 0


# ════════════════════════════════════════════════════════
# 虚拟池的卡集合对齐（原 ISSUE-006 / P17 补完）
# ════════════════════════════════════════════════════════

def _wi_config():
    """用真实 config.toml 构造最差影响分析的配置。"""
    from pathlib import Path
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.core.worst_impact import WorstImpactAnalyzer
    cfg_path = (Path(__file__).resolve().parents[2]
                / 'gacha_simulator' / 'config' / 'config.toml')
    store = load_toml(str(cfg_path))
    return WorstImpactAnalyzer([], {}, store).prepare_simulation_config(50000.0)


def test_synthetic_pool_aggregate_conserves_probability():
    """虚拟池的槽位级聚合不得静默丢卡。

    `_build_pity_engine` 曾用**原始**卡 id 建 `scope_cards` / `featured_cards`
    （`limited_ssr_2`），而合成池里是重命名后的 `_wi_featured_{i}`。于是
    `aggregate_probs_by_rarity` 认不出池内绝大多数卡属于哪个槽位，把它们丢弃，
    只剩 `{'ssr': 0.004}`（池内 99.6% 的概率凭空消失）。
    """
    from gacha_simulator.core.pool import aggregate_probs_by_rarity
    cfg = _wi_config()
    banner, engine = cfg['pools'][0], cfg['pity_engine']
    pool = banner.pools['main']
    spec = engine.get_spec(f'{banner.id}.main')

    pool_total = sum(p for _, p in pool.rewards)
    agg = aggregate_probs_by_rarity(pool, spec)
    assert abs(sum(agg.values()) - pool_total) < 1e-12, \
        f'聚合丢了概率：聚合和 {sum(agg.values())} vs 池内 {pool_total}；agg={agg}'


def test_synthetic_pool_pity_actually_fires():
    """虚拟池的保底必须真的改动分布。

    P17（最差影响保底匹配修复，已完成）的记录称「修复后保底正确触发」，但实测
    200 抽里 `before_draw` 改动分布的次数为 0：保底绑上了池，却因为目标槽位的卡
    集合对不上（聚合把 UP 卡算进了普通槽），`target_total <= 0` 每次早退。
    """
    from gacha_simulator.core.pity import PityState
    from gacha_simulator.core.state import GachaState

    cfg = _wi_config()
    banner, engine = cfg['pools'][0], cfg['pity_engine']
    pool = banner.pools['main']
    spec = engine.get_spec(f'{banner.id}.main')
    assert spec.pity_names, '本配置应有绑到虚拟池的保底'

    fired = []
    orig = engine.before_draw

    def spy(key, st, dist):
        out = orig(key, st, dist)
        if out != dist:
            fired.append(key)
        return out

    engine.before_draw = spy
    try:
        st = PityState.from_dict(cfg['pity_state_init'])
        st.set(spec.pity_names[0], 'counter', 85)   # 软保底爬升中段，必触发
        banner._use_adjusted = False
        pool._use_adjusted = False
        banner.draw(GachaState(), engine, st, pool)
    finally:
        engine.before_draw = orig

    assert fired, '保底未改动分布——虚拟池的保底没生效'


def test_synthetic_pool_card_level_sum_is_one_when_pity_fires():
    """保底生效时，喂给抽卡的卡级字典必须归一（Σ = 1）。

    虚拟池此前从不触发保底，故那段 `scale_factors` 还原路径在它身上从未跑过；
    表修对之后它第一次跑起来，这条断言即为其验收面。
    """
    from gacha_simulator.core import pool as pool_mod
    from gacha_simulator.core.pity import PityState
    from gacha_simulator.core.state import GachaState

    cfg = _wi_config()
    banner, engine = cfg['pools'][0], cfg['pity_engine']
    pool = banner.pools['main']
    spec = engine.get_spec(f'{banner.id}.main')

    captured = {}
    orig_apply = pool_mod.Pool._apply_probabilities

    def spy_apply(self, probs):
        captured['card'] = dict(probs)
        return orig_apply(self, probs)

    pool_mod.Pool._apply_probabilities = spy_apply
    try:
        st = PityState.from_dict(cfg['pity_state_init'])
        st.set(spec.pity_names[0], 'counter', 85)
        banner._use_adjusted = False
        pool._use_adjusted = False
        banner.draw(GachaState(), engine, st, pool)
    finally:
        pool_mod.Pool._apply_probabilities = orig_apply

    card = captured['card']
    assert abs(sum(card.values()) - 1.0) < 1e-12, \
        f'Σ = {sum(card.values())}（保底调整未逐卡落实）'


def test_synthetic_pool_specs_satisfy_alignment_invariants():
    """每个虚拟池的 spec 都必须满足两条不变量（构造期保证的根因守卫）。

    不变量成立时，两份「卡 id → 稀有度」实现对池内每张卡必然同答（见
    `test_pity_integration.TestRarityInferenceConsistency`）；反过来说，这两条
    不变量被破坏就是本类缺陷的根因。
    """
    from gacha_simulator.core.pool import infer_rarity_from_spec
    cfg = _wi_config()
    engine = cfg['pity_engine']
    checked = 0
    for banner in cfg['pools']:
        spec = engine.get_spec(f'{banner.id}.main')
        assert spec is not None
        # ① ssr_ids 与 scope_cards['ssr'] 是同一集合（大小写归一后）
        sc_ssr = {c.lower() for c in spec.scope_cards.get('ssr', ())}
        assert {c.lower() for c in spec.ssr_ids} == sc_ssr, \
            f'{banner.id}: ssr_ids != scope_cards["ssr"]'
        # ② featured_ids ⊆ scope_cards
        all_sc = {c.lower() for cs in spec.scope_cards.values() for c in cs}
        assert {c.lower() for c in spec.featured_ids} <= all_sc, \
            f'{banner.id}: featured_ids 不在 scope_cards 内'
        # ③ 池内每张卡都查得到，且与它的真实稀有度一致
        pool = banner.pools['main']
        for rwd, _ in pool.rewards:
            real = (rwd.extra_info.get('rarity') or '').lower() or None
            assert infer_rarity_from_spec(rwd.id, spec) == real, \
                f'{rwd.id} @ {banner.id}: 推断 {infer_rarity_from_spec(rwd.id, spec)!r} vs 真实 {real!r}'
            checked += 1
    assert checked > 0, '未扫到任何卡——本测试无验收面'


def test_synthetic_pool_pity_moves_mass_into_featured_slot():
    """保底生效后，质量必须是从普通槽搬进限定槽（证明方向，不只是「有变化」）。"""
    from gacha_simulator.core.pity import PityState
    from gacha_simulator.core.state import GachaState

    cfg = _wi_config()
    banner, engine = cfg['pools'][0], cfg['pity_engine']
    pool = banner.pools['main']
    spec = engine.get_spec(f'{banner.id}.main')
    featured_slot = spec.featured_slots['ssr'][0]      # 'ssr_featured'

    seen = []
    orig = engine.before_draw

    def spy(key, st, dist):
        out = orig(key, st, dist)
        if out != dist:
            seen.append((dict(dist), dict(out)))
        return out

    engine.before_draw = spy
    try:
        st = PityState.from_dict(cfg['pity_state_init'])
        st.set(spec.pity_names[0], 'counter', 85)
        banner._use_adjusted = False
        pool._use_adjusted = False
        banner.draw(GachaState(), engine, st, pool)
    finally:
        engine.before_draw = orig

    assert seen, '保底未生效——无验收面'
    before, after = seen[0]
    assert after[featured_slot] > before.get(featured_slot, 0.0), \
        f'保底未把质量搬进 {featured_slot}：{before} → {after}'
    assert after['ssr'] < before['ssr'], \
        f'保底未从普通槽取质量：{before} → {after}'
