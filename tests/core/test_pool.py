from gacha_simulator.core.pity import compute_scope_mappings
from gacha_simulator.core.pool import (
    Pool, Reward,
    parse_cost_string,
)

# `infer_rarity_from_spec` 的两条用例随函数本体删除（S8-2 / ISSUE-504）：该函数的
# 三类消费者（`banner.draw` 的 `scale_factors` 还原段、`aggregate_probs_by_rarity`
# 的内部调用、导出面）在 S8-2 / S8-4 逐个消失后它零消费者，故定义与用例同批删。
# **覆盖不缩水**：它当年守的两件事各有别的承载面：
# ① 「SR / R 卡必须能认出自己的稀有度」（缺陷 12 的根因）：由下方
#    `test_scope_mappings_put_sr_featured_in_its_own_scope` 覆盖（分组侧归对稀有度），
#    并由 `PityEngine._infer_rarity` 的守卫用例（`test_pity_integration.py` 的
#    稀有度推断守卫类）覆盖状态路径；
# ② 「查不到即 None、不得回退猜测」：该回退已于 2026-10-09 删除，其守卫面是
#    `test_worst_impact.py` 的 `test_synthetic_pool_specs_satisfy_alignment_invariants`
#    第 ③ 条（池内每张卡都必须查得到且与真实稀有度一致）。
#
# `aggregate_probs_by_rarity` 的用例随其函数本体删除（S8-4 / ISSUE-504 / §3.9.3）：
# 卡级管道下「卡级 → 槽位级聚合」这一步在生产上不存在，该函数的断言对象随之消失。
# 它守的「SR 的 UP 卡不得被按 SSR 处理」改由下方用例钉在**存活的那个真相源**上
# （`compute_scope_mappings` 的卡集合产出，即 Modifier 侧 A / Q 的取值来源）。


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


def test_scope_mappings_put_sr_featured_in_its_own_scope():
    """SR 的 UP 卡必须归入 `sr` 组，不得归入 `ssr` 组。

    与缺陷 12 同源（都源于「卡 id → 稀有度」的判定只认 SSR）：聚合侧的 featured
    分支原先写 `infer_rarity_from_spec(...) or 'ssr'`，故 SR 的 UP 卡会被按 SSR
    分组。**S8-4 改写（ISSUE-504 / §3.9.3）**：聚合函数本体已删（卡级管道下没有
    「卡级 → 槽位级」这一步），本用例改钉它的**取值来源**——`compute_scope_mappings`
    的卡集合产出，即 S8 的 Modifier 链取 A / Q 的同一个真相源。断言内容不变
    （SR 的 UP 卡归 `sr`、SSR 的 UP 卡归 `ssr`），只是对象从被删函数的输出换成
    喂给它的那张表。
    """
    pool = Pool(
        id='p', name='P', cost=parse_cost_string('draw_resource:160'),
        rewards=[
            (Reward(id='ssr_up', name='SU', extra_info={'rarity': 'SSR', 'featured': True}), 0.01),
            (Reward(id='sr_up', name='RU', extra_info={'rarity': 'SR', 'featured': True}), 0.04),
            (Reward(id='r_a', name='RA', extra_info={'rarity': 'R'}), 0.95),
        ],
    )
    # S8-7：只消费五元组的卡集合两项，槽位三项以 `_` 前缀显式丢弃。
    # `compute_scope_mappings` 的五元组形态与槽位产出保留至发布前（ISSUE-901）。
    scope_cards, featured_cards, _scope_slots, _featured_slots, _card_to_slot = \
        compute_scope_mappings(pool)
    assert scope_cards == {'ssr': ('ssr_up',), 'sr': ('sr_up',), 'r': ('r_a',)}
    assert featured_cards == {'ssr': ('ssr_up',), 'sr': ('sr_up',)}
    # 判据落到断言上：SR 的 UP 卡不在 `ssr` 组内（缺陷 12 的根因形态）
    assert 'sr_up' not in scope_cards['ssr']
    assert 'sr_up' in scope_cards['sr']
