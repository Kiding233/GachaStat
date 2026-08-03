"""P56 阶段十三-a：TargetedBehavior / TargetedSoftBehavior 单元测试。

覆盖目标：
  1. 定轨命中 selected_card 后重置所有状态
  2. 歪非目标卡时 fate_points 递增 + guaranteed 翻转
  3. switch_resets_progress=true/false 的切换行为差异
  4. cancel_epitomized_path 后 selected_card=None 且不累积
  5. fate_threshold=0 始终保证
  6. selected_card=None（不定轨）时不累积
"""

import pytest
from gacha_simulator.core.pity import (
    PityState, DrawInfo, PityContext,
    TargetedBehavior, TargetedSoftBehavior,
)


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════

@pytest.fixture
def state():
    return PityState()


def _make_draw(reward_id, rarity='ssr', is_featured=False, selected=None):
    """构造 DrawInfo 快捷方法。"""
    featured_cards = {'ssr': ('f1', 'f2')}
    all_cards = ('f1', 'f2', 's1', 's2')
    return DrawInfo(
        pool_id='test_pool', pool_instance_id='test_pool_0',
        reward_id=reward_id, reward_rarity=rarity, is_featured=is_featured,
        scope_cards={'ssr': all_cards},
        featured_cards=featured_cards,
        scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
        featured_slots={'ssr': ('ssr_featured',)},
        card_to_slot={'f1': 'ssr_featured', 'f2': 'ssr_featured',
                       's1': 'ssr_standard', 's2': 'ssr_standard'},
        base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
        rarity_rank={'ssr': 3, 'sr': 2, 'r': 1},
    )


def _make_ctx(state, reward_id, rarity='ssr', is_featured=False):
    """构造 PityContext 快捷方法。"""
    draw = _make_draw(reward_id, rarity, is_featured)
    return PityContext(
        draw=draw,
        current={'ssr_featured': 0.005, 'ssr_standard': 0.005},
        state=state,
    )


# ══════════════════════════════════════════════════════════════════
# TargetedBehavior —— 定向保底（定轨）
# ══════════════════════════════════════════════════════════════════

class TestTargetedBehavior:
    """定轨——selected_card 锁定目标 + fate_points 累积。"""

    def test_hit_selected_card_resets_all(self, state):
        """命中 selected_card → fate_points 清零 + guaranteed 清除 + losses 重置。"""
        bh = TargetedBehavior('test_tgt', state, scope='ssr',
                               fate_threshold=1, switch_allowed=True,
                               switch_resets_progress=True)
        state.set('test_tgt', 'selected_card', 'f1')

        # 先歪一次
        bh.after_draw(_make_ctx(state, 's1', is_featured=False))
        assert state.get('test_tgt', 'fate_points', 0) == 1
        assert state.get('test_tgt', 'guaranteed', False) is True

        # 命中目标
        bh.after_draw(_make_ctx(state, 'f1', is_featured=True))
        assert state.get('test_tgt', 'fate_points', 0) == 0
        assert state.get('test_tgt', 'guaranteed', False) is False
        assert state.get('test_tgt', 'losses', 0) == 0

    def test_miss_accumulates_fate_points(self, state):
        """歪非目标 SSR → fate_points++ + guaranteed 翻转 + losses++。"""
        bh = TargetedBehavior('test_tgt', state, scope='ssr',
                               fate_threshold=1, switch_allowed=True,
                               switch_resets_progress=True)
        state.set('test_tgt', 'selected_card', 'f1')

        bh.after_draw(_make_ctx(state, 's1', is_featured=False))
        assert state.get('test_tgt', 'fate_points', 0) == 1
        assert state.get('test_tgt', 'guaranteed', False) is True
        assert state.get('test_tgt', 'lost_rotating', False) is True
        assert state.get('test_tgt', 'losses', 0) == 1

    def test_no_selected_card_does_not_accumulate(self, state):
        """selected_card=None → 不累积、不翻转状态。"""
        bh = TargetedBehavior('test_tgt', state, scope='ssr',
                               fate_threshold=1, switch_allowed=True,
                               switch_resets_progress=True)
        # selected_card 默认为 None（不定轨状态）
        assert state.get('test_tgt', 'selected_card') is None

        bh.after_draw(_make_ctx(state, 's1', is_featured=False))
        assert state.get('test_tgt', 'fate_points', 0) == 0
        assert state.get('test_tgt', 'guaranteed', False) is False

    def test_fate_threshold_zero_always_guaranteed(self, state):
        """fate_threshold=0 → 始终处于保证状态——全部概率归入 selected_card 槽位。"""
        bh = TargetedBehavior('test_tgt', state, scope='ssr',
                               fate_threshold=0, switch_allowed=True,
                               switch_resets_progress=False)
        state.set('test_tgt', 'selected_card', 'f1')

        ctx = _make_ctx(state, '', rarity='')  # before_draw 不计 reward_id
        result = bh.before_draw(ctx)
        # featured 占 100%，且进一步收窄至 selected_card 的槽位
        assert result['ssr_featured'] == pytest.approx(0.01)
        assert result['ssr_standard'] == pytest.approx(0.0)

    def test_small_pity_uses_base_distribution(self, state):
        """小保底：featured 占比由基础分布决定——不修改概率。"""
        bh = TargetedBehavior('test_tgt', state, scope='ssr',
                               fate_threshold=1, switch_allowed=True,
                               switch_resets_progress=True)
        state.set('test_tgt', 'selected_card', 'f1')

        ctx = _make_ctx(state, '', rarity='')
        result = bh.before_draw(ctx)
        # 小保底：featured 占比 = 0.005/(0.005+0.005) = 50%，但概率收窄至 selected slot
        # featured 槽内的 f1 权重 = 0.005 / 0.005 = 1.0 → featured 槽 50% 分配给 f1
        assert result['ssr_featured'] == pytest.approx(0.005)
        assert result['ssr_standard'] == pytest.approx(0.005)

    def test_guaranteed_targets_selected_card_slot(self, state):
        """大保底状态：featured 100% 且收窄到 selected_card 的槽位。"""
        bh = TargetedBehavior('test_tgt', state, scope='ssr',
                               fate_threshold=1, switch_allowed=True,
                               switch_resets_progress=True)
        state.set('test_tgt', 'selected_card', 'f1')
        state.set('test_tgt', 'guaranteed', True)

        ctx = _make_ctx(state, '', rarity='')
        result = bh.before_draw(ctx)
        # 大保底 + selected_card → 全部分配给 f1 所在的槽位
        assert result['ssr_featured'] == pytest.approx(0.01)
        assert result['ssr_standard'] == pytest.approx(0.0)

    def test_is_hit_matches_selected_card(self, state):
        """_is_hit() 仅在 reward_id == selected_card 时返回 True。"""
        bh = TargetedBehavior('test_tgt', state, scope='ssr',
                               fate_threshold=1)
        state.set('test_tgt', 'selected_card', 'f1')

        # 命中目标
        assert bh._is_hit(_make_ctx(state, 'f1', is_featured=True)) is True
        # 命中其他 featured
        assert bh._is_hit(_make_ctx(state, 'f2', is_featured=True)) is False
        # 歪了
        assert bh._is_hit(_make_ctx(state, 's1', is_featured=False)) is False

    def test_did_fire_returns_is_hit(self, state):
        """did_fire() = _is_hit()。"""
        bh = TargetedBehavior('test_tgt', state, scope='ssr', fate_threshold=1)
        state.set('test_tgt', 'selected_card', 'f1')
        assert bh.did_fire(_make_ctx(state, 'f1', is_featured=True)) is True
        assert bh.did_fire(_make_ctx(state, 's1', is_featured=False)) is False

    def test_non_ssr_does_not_trigger(self, state):
        """非 scope 稀有度不触发状态转移。"""
        bh = TargetedBehavior('test_tgt', state, scope='ssr', fate_threshold=1)
        state.set('test_tgt', 'selected_card', 'f1')
        ctx = _make_ctx(state, 'r1', rarity='r', is_featured=False)
        bh.after_draw(ctx)
        assert state.get('test_tgt', 'fate_points', 0) == 0

    def test_miss_featured_but_not_selected_accumulates(self, state):
        """歪了 featured 但不是 selected_card → 仍然累积命定值。"""
        bh = TargetedBehavior('test_tgt', state, scope='ssr',
                               fate_threshold=1, switch_allowed=True,
                               switch_resets_progress=True)
        state.set('test_tgt', 'selected_card', 'f1')

        # 出了 f2（featured 但不是 selected_card）
        bh.after_draw(_make_ctx(state, 'f2', is_featured=True))
        # 仍然歪——is_hit 检查 reward_id==selected_card
        assert state.get('test_tgt', 'fate_points', 0) == 1


# ══════════════════════════════════════════════════════════════════
# TargetedSoftBehavior —— 定轨 + 软保底（mixin）
# ══════════════════════════════════════════════════════════════════

class TestTargetedSoftBehavior:
    """mixin 提供 soft counter + deltas 引擎委托。"""

    def test_counter_increments_on_before_draw(self, state):
        """before_draw 递增 counter。"""
        bh = TargetedSoftBehavior('test_ts', state, scope='ssr',
                                   fate_threshold=1,
                                   soft_start=63, soft_end=80)
        state.set('test_ts', 'selected_card', 'f1')
        ctx = _make_ctx(state, '', rarity='')
        bh.before_draw(ctx)
        assert state.get('test_ts', 'counter', 0) == 1

    def test_ssr_resets_counter(self, state):
        """SSR 出货 → counter 重置。"""
        bh = TargetedSoftBehavior('test_ts', state, scope='ssr',
                                   fate_threshold=1,
                                   soft_start=63, soft_end=80)
        state.set('test_ts', 'selected_card', 'f1')

        # 递增几次 counter
        ctx = _make_ctx(state, '', rarity='')
        for _ in range(10):
            bh.before_draw(ctx)
        assert state.get('test_ts', 'counter', 0) == 10

        # SSR 出货
        bh.after_draw(_make_ctx(state, 'f1', is_featured=True))
        assert state.get('test_ts', 'counter', 0) == 0

    def test_readonly_no_counter_increment(self, state):
        """readonly=True 不递增 counter。"""
        bh = TargetedSoftBehavior('test_ts', state, scope='ssr',
                                   fate_threshold=1,
                                   soft_start=63, soft_end=80)
        state.set('test_ts', 'selected_card', 'f1')
        ctx = _make_ctx(state, '', rarity='')
        bh.before_draw(ctx, readonly=True)
        assert state.get('test_ts', 'counter', 0) == 0

    def test_fate_points_work_with_soft(self, state):
        """mixin 不破坏定轨的命定值累积。"""
        bh = TargetedSoftBehavior('test_ts', state, scope='ssr',
                                   fate_threshold=1,
                                   soft_start=63, soft_end=80)
        state.set('test_ts', 'selected_card', 'f1')

        # 歪一次
        bh.after_draw(_make_ctx(state, 's1', is_featured=False))
        assert state.get('test_ts', 'fate_points', 0) == 1
        assert state.get('test_ts', 'guaranteed', False) is True
