from gacha_simulator.core.pity import PoolPitySpec
from gacha_simulator.core.pool import (
    Pool, Reward, aggregate_probs_by_rarity, infer_rarity_from_spec,
    parse_cost_string,
)


def test_pool_draw_returns_reward():
    r1 = Reward(id='r1', name='Reward 1')
    r2 = Reward(id='r2', name='Reward 2')
    pool = Pool(
        id='test_pool',
        name='Test Pool',
        cost=parse_cost_string('draw_resource:160'),
        rewards=[(r1, 0.6), (r2, 0.4)],
    )
    result = pool.draw()
    assert result in [r1, r2]


def test_exchange_pool_returns_first_reward():
    r = Reward(id='exchange', name='Exchange')
    pool = Pool(
        id='exchange_pool',
        name='Exchange Pool',
        cost=parse_cost_string('stardust:75'),
        rewards=[(r, 1.0)],
    )
    result = pool.draw()
    assert result == r


def test_infer_rarity_recognizes_non_ssr_cards():
    """scope_cards 含全部稀有度，SR / R 卡必须能认出自己的稀有度。

    缺陷 12 的根因：本函数原先只认 SSR（判 ssr_ids / featured_ids 两个集合），
    SR / R 一律返回 None，使 banner.draw 的 scale_factors 还原段跳过它们的缩放，
    喂给 pool.draw 的卡级字典 Σ > 1、保底效果被稀释。
    """
    spec = PoolPitySpec(
        pity_names=['p'],
        scope_cards={'ssr': ('ssr_a',), 'sr': ('sr_a',), 'r': ('r_a',)},
    )
    assert infer_rarity_from_spec('sr_a', spec) == 'sr'
    assert infer_rarity_from_spec('r_a', spec) == 'r'


def test_infer_rarity_falls_back_to_renamed_ssr_ids():
    """scope_cards 覆盖不到 id 时，仍须经 ssr_ids / featured_ids 认出 SSR。

    worst_impact 路径的 scope_cards / card_to_slot 按**原始** card id 建，而池内
    是重命名后的 `_wi_featured_{i}`（ISSUE-006），故该路径只能靠这两个集合命中。
    缺失回退即「最差影响分析的保底缩放被静默跳过」。
    """
    spec = PoolPitySpec(
        pity_names=['p'],
        ssr_ids={'_wi_featured_0'},
        featured_ids={'_wi_featured_0'},
        scope_cards={'ssr': ('ssr_a',)},
        card_to_slot={'ssr_a': 'ssr_featured'},
    )
    assert infer_rarity_from_spec('_wi_featured_0', spec) == 'ssr'
    assert infer_rarity_from_spec('not_in_spec', spec) is None


def test_aggregate_puts_sr_featured_in_its_own_slot():
    """SR 的 UP 卡必须落 `sr_featured`，不得落 `ssr_featured`。

    与缺陷 12 同源（都源于本函数原先只认 SSR）：聚合侧的 featured 分支写
    `infer_rarity_from_spec(...) or 'ssr'`，故 SR 的 UP 卡会被按 SSR 限定槽聚合。
    """
    pool = Pool(
        id='p', name='P', cost=parse_cost_string('draw_resource:160'),
        rewards=[
            (Reward(id='ssr_up', name='SU', extra_info={'rarity': 'SSR', 'featured': True}), 0.01),
            (Reward(id='sr_up', name='RU', extra_info={'rarity': 'SR', 'featured': True}), 0.04),
            (Reward(id='r_a', name='RA', extra_info={'rarity': 'R'}), 0.95),
        ],
    )
    spec = PoolPitySpec(
        pity_names=['p'],
        scope_cards={'ssr': ('ssr_up',), 'sr': ('sr_up',), 'r': ('r_a',)},
        featured_cards={'ssr': ('ssr_up',), 'sr': ('sr_up',)},
    )
    result = aggregate_probs_by_rarity(pool, spec)
    assert result == {'ssr_featured': 0.01, 'sr_featured': 0.04, 'r': 0.95}
