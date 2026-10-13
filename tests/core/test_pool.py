from gacha_simulator.core.pity import PoolPitySpec
from gacha_simulator.core.pool import (
    Pool, Reward, aggregate_probs_by_rarity,
    parse_cost_string,
)

# `infer_rarity_from_spec` 的两条用例随函数本体删除（S8-2 / ISSUE-504）：该函数的
# 三类消费者（`banner.draw` 的 `scale_factors` 还原段、`aggregate_probs_by_rarity`
# 的内部调用、导出面）在 S8-2 / S8-4 逐个消失后它零消费者，故定义与用例同批删。
# **覆盖不缩水**：它当年守的两件事各有别的承载面——
# ① 「SR / R 卡必须能认出自己的稀有度」（缺陷 12 的根因）：由下方
#    `test_aggregate_puts_sr_featured_in_its_own_slot` 覆盖（聚合侧写对槽位），
#    并由 `PityEngine._infer_rarity` 的守卫用例（`test_pity_integration.py` 的
#    稀有度推断一致性类）覆盖状态路径；
# ② 「查不到即 None、不得回退猜测」：该回退已于 2026-10-09 删除，其守卫面是
#    `test_worst_impact.py` 的 `test_synthetic_pool_specs_satisfy_alignment_invariants`
#    第 ③ 条（池内每张卡都必须查得到且与真实稀有度一致）。


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


def test_aggregate_puts_sr_featured_in_its_own_slot():
    """SR 的 UP 卡必须落 `sr_featured`，不得落 `ssr_featured`。

    与缺陷 12 同源（都源于「卡 id → 稀有度」的判定只认 SSR）：聚合侧的 featured
    分支原先写 `infer_rarity_from_spec(...) or 'ssr'`，故 SR 的 UP 卡会被按 SSR
    限定槽聚合。S8-2 起该分支改查本函数内部构建的 `rarity_of`（`scope_cards` 的
    小写反查表），**判据与旧函数逐条相同**（唯一来源是 `scope_cards`、大小写归一、
    查不到即不写槽），故本条断言不变、仍是本函数在该形态上的验收面。
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
