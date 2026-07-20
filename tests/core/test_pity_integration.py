"""P56 集成测试——多 behavior 协同 + depends_on 激活传播 + card_to_slot。

覆盖目标：
  1. _resolve_selected_slots O(1) card_to_slot 路径
  2. depends_on：被依赖方 did_fire → 依赖方 _active 从 False → True
  3. 多保底协同：rotating + hard 同时作用于一个池子
"""

import pytest
from gacha_simulator.core.pity import (
    PityState, PityEngine, DrawInfo, PityContext,
    TargetedBehavior, RotatingBehavior, HardPityBehavior,
    _redistribute_scope, compute_scope_mappings,
    PoolPitySpec, BEHAVIOR_REGISTRY,
)
from gacha_simulator.core.config_store import PityDef
from gacha_simulator.core.pool import Pool, Reward


# ══════════════════════════════════════════════════════════════════
# _resolve_selected_slots O(1) 路径
# ══════════════════════════════════════════════════════════════════

class TestResolveSelectedSlots:
    """TargetedBehavior._resolve_selected_slots 的 card_to_slot 主路径。"""

    def test_o1_lookup_via_card_to_slot(self):
        """selected 在 card_to_slot 中 → O(1) 返回对应槽位。"""
        state = PityState()
        bh = TargetedBehavior('tgt', state, scope='ssr', fate_threshold=1)
        state.set('tgt', 'selected_card', 'f1')

        draw = DrawInfo(
            pool_id='p1', pool_instance_id='p1_0',
            reward_id='', reward_rarity='', is_featured=False,
            scope_cards={'ssr': ('f1', 'f2', 's1')},
            featured_cards={'ssr': ('f1', 'f2')},
            scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
            featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured', 'f2': 'ssr_featured', 's1': 'ssr_standard'},
            base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
            rarity_rank={'ssr': 3},
        )
        ctx = PityContext(draw=draw, current={}, state=state)

        result = bh._resolve_selected_slots('f1', ('ssr_featured',), ctx)
        assert result == ('ssr_featured',)

    def test_fallback_when_not_in_card_to_slot(self):
        """selected 不在 card_to_slot → 降级遍历 featured_slots → scope_cards。"""
        state = PityState()
        bh = TargetedBehavior('tgt', state, scope='ssr', fate_threshold=1)

        draw = DrawInfo(
            pool_id='p1', pool_instance_id='p1_0',
            reward_id='', reward_rarity='', is_featured=False,
            scope_cards={'ssr': ('f1', 'f2', 's1')},
            featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
            featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={},  # 空——走降级路径
            base_probabilities={},
            rarity_rank={'ssr': 3},
        )
        ctx = PityContext(draw=draw, current={}, state=state)

        result = bh._resolve_selected_slots('f1', ('ssr_featured',), ctx)
        assert result == ('ssr_featured',)

    def test_selected_none_returns_all_featured(self):
        """selected=None → 返回全部 featured_slots。"""
        state = PityState()
        bh = TargetedBehavior('tgt', state, scope='ssr', fate_threshold=1)
        draw = DrawInfo(
            pool_id='p1', pool_instance_id='p1_0',
            reward_id='', reward_rarity='', is_featured=False,
            scope_cards={}, featured_cards={}, scope_slots={},
            featured_slots={'ssr': ('ssr_featured', 'ssr_featured2')},
            card_to_slot={}, base_probabilities={}, rarity_rank={},
        )
        ctx = PityContext(draw=draw, current={}, state=state)
        result = bh._resolve_selected_slots(None, ('ssr_featured', 'ssr_featured2'), ctx)
        assert result == ('ssr_featured', 'ssr_featured2')


# ══════════════════════════════════════════════════════════════════
# depends_on 激活传播
# ══════════════════════════════════════════════════════════════════

class TestDependsOnIntegration:
    """PityEngine + depends_on 端到端——did_fire 激活依赖方。"""

    def test_dependent_activated_after_source_fires(self):
        """被依赖方 did_fire → 依赖方 _active 变为 True。"""
        state = PityState()

        pool = Pool(
            id='test_pool', name='测试池', pool_type='角色',
            cost={'gem': 1},
            rewards=[
                (Reward(id='f1', name='F1', extra_info={'rarity': 'SSR', 'featured': True}), 0.005),
                (Reward(id='s1', name='S1', extra_info={'rarity': 'SSR', 'featured': False}), 0.005),
            ],
        )

        scope_cards, featured_cards, scope_slots, featured_slots, card_to_slot = \
            compute_scope_mappings(pool)

        source_def = PityDef(name='source', btype='rotating', scope='ssr')
        dep_def = PityDef(name='dependent', btype='hard', scope='ssr',
                           threshold=100, depends_on='source')

        pool_spec = PoolPitySpec(
            scope_cards=scope_cards, featured_cards=featured_cards,
            scope_slots=scope_slots, featured_slots=featured_slots,
            pity_names=('source', 'dependent'),
            ssr_ids={'f1', 's1'}, featured_ids={'f1'},
            card_to_slot=card_to_slot,
        )

        engine = PityEngine(
            pool_specs={'test_pool': pool_spec},
            pity_defs=[source_def, dep_def],
            state=state,
            rarity_rank={'ssr': 3, 'sr': 2, 'r': 1},
        )

        # 依赖方初始 inactive（depends_on → _active 未 set → Flag 默认 False）
        assert state.get('dependent', '_active', False) is False

        # 模拟抽中 featured SSR —— source.did_fire → True
        engine.before_draw('test_pool', state, {'ssr_featured': 0.005, 'ssr_standard': 0.005})
        engine.after_draw('test_pool', state, 'f1')

        # 依赖方被激活
        assert state.get('dependent', '_active', False) is True


# ══════════════════════════════════════════════════════════════════
# 多保底协同
# ══════════════════════════════════════════════════════════════════

class TestMultiPityCoordination:
    """rotating + hard 同时作用——概率叠加 + 状态独立。"""

    def test_rotating_and_hard_on_same_pool(self):
        """rotating 和 hard 概率叠加：先 rotating 调整比例，再 hard 100% featured。"""
        state = PityState()

        pool = Pool(
            id='test_pool', name='测试池', pool_type='角色',
            cost={'gem': 1},
            rewards=[
                (Reward(id='f1', name='F1', extra_info={'rarity': 'SSR', 'featured': True}), 0.005),
                (Reward(id='s1', name='S1', extra_info={'rarity': 'SSR', 'featured': False}), 0.005),
            ],
        )

        scope_cards, featured_cards, scope_slots, featured_slots, card_to_slot = \
            compute_scope_mappings(pool)

        rot_def = PityDef(name='rot', btype='rotating', scope='ssr')
        hard_def = PityDef(name='hard90', btype='hard', scope='ssr', threshold=90)

        pool_spec = PoolPitySpec(
            scope_cards=scope_cards, featured_cards=featured_cards,
            scope_slots=scope_slots, featured_slots=featured_slots,
            pity_names=('rot', 'hard90'),
            ssr_ids={'f1', 's1'}, featured_ids={'f1'},
            card_to_slot=card_to_slot,
        )

        engine = PityEngine(
            pool_specs={'test_pool': pool_spec},
            pity_defs=[rot_def, hard_def],
            state=state,
            rarity_rank={'ssr': 3, 'sr': 2, 'r': 1},
        )

        # 初始——小保底，未到硬保底阈值
        probs = engine.before_draw('test_pool', state,
                                    {'ssr_featured': 0.005, 'ssr_standard': 0.005})
        # rotating 小保底维持基础比例
        assert probs['ssr_featured'] == pytest.approx(0.005)
        assert probs['ssr_standard'] == pytest.approx(0.005)

        # 设 counter 到 90——hard 保底触发 + rotating 大保底
        state.set('hard90', 'counter', 89)
        state.set('rot', 'guaranteed', True)
        probs2 = engine.before_draw('test_pool', state,
                                     {'ssr_featured': 0.005, 'ssr_standard': 0.005})
        # 两条保底叠加后 standard 槽位归零（全部导向 featured）
        assert probs2['ssr_standard'] == pytest.approx(0.0)
        assert probs2['ssr_featured'] >= 0.005  # featured 至少保持基础概率
