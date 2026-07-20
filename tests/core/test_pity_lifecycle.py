"""P56 阶段十三-b：LifecycleConfig 集成测试。

覆盖目标：
  1. depends_on 激活传播——依赖方初始 inactive，被依赖方 did_fire() 后激活
  2. deactivate_on_early_hit=true 在提前命中后永久关闭

"""

import pytest
from gacha_simulator.core.pity import (
    PityState, DrawInfo, PityContext,
    HardPityBehavior,
)
from gacha_simulator.core.pity import LifecycleConfig


class TestDeactivateOnEarlyHit:
    """deactivate_on_early_hit——提前命中永久关闭。"""

    def test_hard_pity_early_hit_deactivates(self):
        """HardPityBehavior + deactivate_on_early_hit：提前命中 featured 后 _active 被清除。"""
        state = PityState()
        lifecycle = LifecycleConfig(
            deactivate_on_early_hit=True,
        )
        bh = HardPityBehavior('early_hard', state, 'ssr', threshold=120,
                               lifecycle=lifecycle,
                               target_featured=True)

        # 激活状态
        state.set('early_hard', '_active', True)

        # 模拟提前命中 featured（counter < threshold）
        draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='f1', reward_rarity='ssr', is_featured=True,
            scope_cards={'ssr': ('f1',)}, featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured',)}, featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured'},
            base_probabilities={'ssr_featured': 0.01}, rarity_rank={'ssr': 3},
        )
        ctx = PityContext(draw=draw, current={}, state=state)
        # counter 低于 threshold
        state.set('early_hard', 'counter', 50)

        bh.after_draw(ctx)
        # deactivate_on_early_hit → _active 被清除
        assert state.get('early_hard', '_active', True) is False
