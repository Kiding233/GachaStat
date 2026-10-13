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


def test_synthetic_pool_card_level_pipe_neither_drops_nor_invents_cards():
    """虚拟池的卡级管道不得静默丢卡、也不得引入槽位键。

    **S8-4 改写（ISSUE-504 / §3.9.3）**：原用例 `test_synthetic_pool_aggregate_
    conserves_probability` 断言的是**槽位级聚合**的守恒——`_build_pity_engine` 曾用
    **原始**卡 id 建 `scope_cards` / `featured_cards`（`limited_ssr_2`），而合成池里
    是重命名后的 `_wi_featured_{i}`，于是 `aggregate_probs_by_rarity` 认不出池内绝大
    多数卡属于哪个槽位、把它们丢弃（只剩 `{'ssr': 0.004}`，池内 99.6% 的概率凭空
    消失）。**S8-2 起「卡级 → 槽位级聚合」这一步在生产上不存在**（`banner.draw`
    卡级直传），故本用例改钉同一风险的**卡级形态**，断言内容不变（不得丢卡）：
    管道输出的键集必须与池内 reward id 逐一相同，且归一化后 Σ = 1。

    这同时是「对齐不变量」在管道侧的同源守卫：卡集合若与池内 id 对不上，
    `transfer_linear` 的 `sum(dist[c] for c in Q)` 会直接抛 `KeyError`（而不是像
    聚合那样静默丢卡），故本用例失败时的症状是异常而非断言——两者都由本行覆盖。

    **counter 预置 85（同 `test_synthetic_pool_pity_actually_fires`）**：不预置则
    `ssr_soft` 在爬升起点不触发、`before_draw` 恒等返回，本条的三项断言全部空转
    （恒等输入必然键集相同、Σ 恒为 1）。末条的「非空转守卫」正是为此。
    """
    from gacha_simulator.core.pity import PityState

    cfg = _wi_config()
    banner, engine = cfg['pools'][0], cfg['pity_engine']
    pool = banner.pools['main']
    key = f'{banner.id}.main'
    spec = engine.get_spec(key)
    assert spec is not None, '本配置应把保底绑到虚拟池'

    probs = {r.id: p for r, p in pool.rewards}
    state = PityState.from_dict(cfg['pity_state_init'])
    state.set(spec.pity_names[0], 'counter', 85)   # 软保底爬升中段，必触发
    out = engine.before_draw(key, state, probs)

    assert set(out) == set(probs), (
        f'卡级管道改了键集：多出 {sorted(set(out) - set(probs))}、'
        f'丢掉 {sorted(set(probs) - set(out))}'
    )
    assert abs(sum(out.values()) - 1.0) < 1e-12, \
        f'Σ = {sum(out.values())}（卡级管道未归一）'
    assert out != probs, '保底未改动分布（本用例的键集 / 归一断言随之空转）'


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

    不变量成立时，「卡 id → 稀有度」的推断（S8 起唯一实现是
    `PityEngine._infer_rarity`，喂状态路径）对池内每张卡必然答对；反过来说，
    这两条不变量被破坏就是本类缺陷的根因。

    **S8-2 改写（ISSUE-504）**：原第 ③ 条用 `pool.infer_rarity_from_spec`（A 实现）
    逐卡比对，该函数已随其最后一批消费者删除（`banner.draw` 的 `scale_factors`
    还原段与 `aggregate_probs_by_rarity` 的内部调用），故第 ③ 条改为**直接查
    `scope_cards` 的反查表**：这正是被删函数当年的唯一判据来源，断言内容
    （池内每张卡都查得到、且与它声明的稀有度一致）不变。
    """
    cfg = _wi_config()
    engine = cfg['pity_engine']
    checked = 0
    for banner in cfg['pools']:
        spec = engine.get_spec(f'{banner.id}.main')
        assert spec is not None
        # ① ssr_ids ⊆ scope_cards['ssr']（大小写归一后）
        #    用包含而非相等：`batch_simulator` 建 ssr_ids 时排除 `_no_card`
        #    （:1091 的 `cid != '_no_card'`），而 `compute_scope_mappings` 会把它计入
        #    scope_cards，故 SSR 稀有度的 `_no_card` 会让等号在**合法配置**上误红。
        #    这里需要的是「查得到」，即包含。
        sc_ssr = {c.lower() for c in spec.scope_cards.get('ssr', ())}
        assert {c.lower() for c in spec.ssr_ids} <= sc_ssr, \
            f'{banner.id}: ssr_ids 未被 scope_cards["ssr"] 覆盖'
        # ② featured_ids ⊆ scope_cards
        all_sc = {c.lower() for cs in spec.scope_cards.values() for c in cs}
        assert {c.lower() for c in spec.featured_ids} <= all_sc, \
            f'{banner.id}: featured_ids 不在 scope_cards 内'
        # ③ 池内每张卡都查得到，且与它的真实稀有度一致
        card_rarity = {c.lower(): r.lower()
                       for r, cs in spec.scope_cards.items() for c in cs}
        pool = banner.pools['main']
        for rwd, _ in pool.rewards:
            real = (rwd.extra_info.get('rarity') or '').lower() or None
            got = card_rarity.get(rwd.id.lower())
            assert got == real, \
                f'{rwd.id} @ {banner.id}: 查得 {got!r} vs 真实 {real!r}'
            checked += 1
    assert checked > 0, '未扫到任何卡——本测试无验收面'


def test_synthetic_pool_pity_moves_mass_into_featured_slot():
    """保底生效后，质量必须是从低稀有度槽搬进 scope 槽（证明方向，不只是「有变化」）。

    **目标集口径（2026-10-10，S4-2 随裁决 7B 改写；S8-2 迁到卡级）**：本用例原断言
    「搬进 `ssr_featured`（限定槽）、从 `ssr`（普通槽）取」，那是样例配置
    `config.toml` 的 `ssr_soft` 带 `target_featured = true` 时的形态。裁决 7B
    （2026-10-05）把 `soft_*` + `target_featured = true` 定为 `ConfigError`
    （soft 的目标集恒为 scope 全集，该形态可等价分解为「稀有度级 + 卡级」两步
    转移），样例配置随之删去该行，故本用例改断言**方向**：质量自低稀有度卡搬入
    **SSR 卡集**（`spec.scope_cards['ssr']`），低稀有度侧一律下降。
    **S8-2 起管道是卡级**（§3.9.1），故断言面由槽位名换成卡 id（原写 `scope_slots`
    的槽名，卡级管道下 `dist` 的键里根本没有它们）。断言目的（「方向而非仅
    『有变化』」）不变，变的只是目标集口径与键空间。
    """
    from gacha_simulator.core.pity import PityState
    from gacha_simulator.core.state import GachaState

    cfg = _wi_config()
    banner, engine = cfg['pools'][0], cfg['pity_engine']
    pool = banner.pools['main']
    spec = engine.get_spec(f'{banner.id}.main')
    ssr_cards = tuple(spec.scope_cards['ssr'])

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
    lower = [c for c in before if c not in ssr_cards]
    assert lower, '本用例需要 scope 之外的低稀有度卡作取源面'
    assert sum(after[c] for c in ssr_cards) > sum(before[c] for c in ssr_cards), \
        f'保底未把质量搬进 SSR 卡集：{before} → {after}'
    for c in lower:
        assert after[c] < before[c], \
            f'保底未从低稀有度卡 {c} 取质量：{before} → {after}'
