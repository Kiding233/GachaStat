"""P56 阶段十三-a：RotatingBehavior / RotatingCRBehavior / _soft 变体单元测试。

覆盖目标：
  1. 纯净 rotating 大小保底翻转正确性——歪后 guaranteed=True、中 featured 后 guaranteed=False
  2. 小保底 featured 占比由基础分布决定（非硬编码 50%）
  3. CR 连歪计数器递增/重置/逻辑边界
  4. _soft 后缀 counter 递增 + SSR 重置
  5. readonly=True 时不修改状态
"""

import pytest
from gacha_simulator.core.pity import (
    PityState, DrawInfo, PityContext,
    RotatingBehavior, RotatingCRBehavior,
    RotatingSoftBehavior, RotatingCRSoftBehavior,
    _redistribute_scope,
)


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════

@pytest.fixture
def state():
    return PityState()


@pytest.fixture
def base_ctx(state):
    """构造一个标准 SSR 小保底 PityContext。
    基础分布：featured 槽 0.005 (50%), standard 槽 0.005 (50%)。
    """
    draw = DrawInfo(
        pool_id='test_pool',
        pool_instance_id='test_pool_0',
        reward_id='',
        reward_rarity='',
        is_featured=False,
        scope_cards={'ssr': ('f1', 'f2', 's1', 's2')},
        featured_cards={'ssr': ('f1', 'f2')},
        scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
        featured_slots={'ssr': ('ssr_featured',)},
        card_to_slot={'f1': 'ssr_featured', 'f2': 'ssr_featured',
                       's1': 'ssr_standard', 's2': 'ssr_standard'},
        base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
        rarity_rank={'ssr': 3, 'sr': 2, 'r': 1},
    )
    return PityContext(
        draw=draw,
        current={'ssr_featured': 0.005, 'ssr_standard': 0.005},
        state=state,
    )


# ══════════════════════════════════════════════════════════════════
# RotatingBehavior —— 纯净轮换保底
# ══════════════════════════════════════════════════════════════════

class TestRotatingBehavior:
    """纯净大小保底——零参数事件驱动。"""

    def test_small_pity_uses_base_distribution(self, state, base_ctx):
        """小保底：featured 占比由基础分布决定——不修改概率。"""
        bh = RotatingBehavior('test_rot', state, scope='ssr')
        result = bh.before_draw(base_ctx)
        # 小保底 featured 占比 = 0.005/(0.005+0.005) = 50%
        assert result['ssr_featured'] == pytest.approx(0.005)
        assert result['ssr_standard'] == pytest.approx(0.005)

    def test_guaranteed_pity_gives_100_percent_featured(self, state, base_ctx):
        """大保底：featured 100%。"""
        bh = RotatingBehavior('test_rot', state, scope='ssr')
        # 先模拟歪一次 → guaranteed=True
        draw_miss = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
            featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured', 's1': 'ssr_standard'},
            base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
            rarity_rank={'ssr': 3},
        )
        miss_ctx = PityContext(draw=draw_miss, current={'ssr_featured': 0.005, 'ssr_standard': 0.005}, state=state)
        bh.after_draw(miss_ctx)
        assert state.get('test_rot', 'guaranteed', False) is True

        # 大保底：featured 100%
        result = bh.before_draw(base_ctx)
        assert result['ssr_featured'] == pytest.approx(0.01)
        assert result['ssr_standard'] == pytest.approx(0.0)

    def test_hit_featured_clears_guaranteed(self, state, base_ctx):
        """中 featured 后 guaranteed=False——回到小保底。"""
        bh = RotatingBehavior('test_rot', state, scope='ssr')
        # 先歪一次
        draw_miss = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
            featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured', 's1': 'ssr_standard'},
            base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
            rarity_rank={'ssr': 3},
        )
        miss_ctx = PityContext(draw=draw_miss, current={}, state=state)
        bh.after_draw(miss_ctx)
        assert state.get('test_rot', 'guaranteed', False) is True

        # 再中 featured
        draw_hit = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='f1', reward_rarity='ssr', is_featured=True,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
            featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured', 's1': 'ssr_standard'},
            base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
            rarity_rank={'ssr': 3},
        )
        hit_ctx = PityContext(draw=draw_hit, current={}, state=state)
        bh.after_draw(hit_ctx)
        assert state.get('test_rot', 'guaranteed', False) is False

    def test_non_ssr_does_not_trigger(self, state):
        """非 scope 稀有度不触发状态转移。"""
        bh = RotatingBehavior('test_rot', state, scope='ssr')
        draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='r1', reward_rarity='sr', is_featured=False,
            scope_cards={}, featured_cards={}, scope_slots={}, featured_slots={},
            card_to_slot={}, base_probabilities={}, rarity_rank={'ssr': 3, 'sr': 2},
        )
        ctx = PityContext(draw=draw, current={}, state=state)
        bh.after_draw(ctx)
        # guaranteed 未被设置（保持默认 False）
        assert state.get('test_rot', 'guaranteed', False) is False

    def test_did_fire_returns_is_hit(self, state):
        """did_fire() = _is_hit() → is_featured 为 True 时返回 True。"""
        bh = RotatingBehavior('test_rot', state, scope='ssr')
        draw_hit = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='f1', reward_rarity='ssr', is_featured=True,
            scope_cards={'ssr': ('f1',)}, featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured',)}, featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured'},
            base_probabilities={'ssr_featured': 0.01}, rarity_rank={'ssr': 3},
        )
        ctx_hit = PityContext(draw=draw_hit, current={}, state=state)
        assert bh.did_fire(ctx_hit) is True

        draw_miss = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('s1',)}, featured_cards={'ssr': ()},
            scope_slots={'ssr': ('ssr_standard',)}, featured_slots={'ssr': ()},
            card_to_slot={'s1': 'ssr_standard'},
            base_probabilities={'ssr_standard': 0.01}, rarity_rank={'ssr': 3},
        )
        ctx_miss = PityContext(draw=draw_miss, current={}, state=state)
        assert bh.did_fire(ctx_miss) is False


# ══════════════════════════════════════════════════════════════════
# RotatingCRBehavior —— 捕获明光
# ══════════════════════════════════════════════════════════════════

class TestRotatingCRBehavior:
    """轮换 + 捕获明光——CR 状态机。"""

    def test_cr_counter_increments_on_loss(self, state, base_ctx):
        """小保底歪了 → cr_counter++。"""
        bh = RotatingCRBehavior('test_cr', state, scope='ssr', cr_counter_threshold=3)
        draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
            featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured', 's1': 'ssr_standard'},
            base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
            rarity_rank={'ssr': 3},
        )
        ctx = PityContext(draw=draw, current={}, state=state)
        bh.after_draw(ctx)
        assert state.get('test_cr', 'cr_counter', 0) == 1

    def test_cr_counter_resets_on_win(self, state):
        """小保底赢了 → cr_counter 归零。（需先经过 guaranteed→hit 回到小保底状态）"""
        bh = RotatingCRBehavior('test_cr', state, scope='ssr', cr_counter_threshold=3)

        # 第1抽：小保底歪 → cr_counter=1, guaranteed=True
        miss_draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
            featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured', 's1': 'ssr_standard'},
            base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
            rarity_rank={'ssr': 3},
        )
        bh.after_draw(PityContext(draw=miss_draw, current={}, state=state))
        assert state.get('test_cr', 'cr_counter', 0) == 1
        assert state.get('test_cr', 'guaranteed', False) is True

        # 第2抽：大保底命中 → guaranteed 清除，cr_counter 不变（CR 不介入大保底）
        hit_draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='f1', reward_rarity='ssr', is_featured=True,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
            featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured', 's1': 'ssr_standard'},
            base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
            rarity_rank={'ssr': 3},
        )
        bh.after_draw(PityContext(draw=hit_draw, current={}, state=state))
        assert state.get('test_cr', 'guaranteed', False) is False  # 大保底清除
        assert state.get('test_cr', 'cr_counter', 0) == 1  # CR 不介入大保底

        # 第3抽：小保底赢 → cr_counter 归零
        bh.after_draw(PityContext(draw=hit_draw, current={}, state=state))
        assert state.get('test_cr', 'cr_counter', 0) == 0

    def test_cr_100_percent_intercept_at_threshold(self, state, base_ctx):
        """cr_counter >= threshold → 100% 拦截——featured_ratio=1.0。"""
        bh = RotatingCRBehavior('test_cr', state, scope='ssr', cr_counter_threshold=2)
        # 设 cr_counter = 2（达到阈值）
        state.set('test_cr', 'cr_counter', 2)
        # 设 guaranteed = False（小保底状态）
        state.set('test_cr', 'guaranteed', False)

        result = bh.before_draw(base_ctx)
        # 100% featured
        assert result['ssr_featured'] == pytest.approx(0.01)
        assert result['ssr_standard'] == pytest.approx(0.0)

    def test_cr_not_intercept_when_guaranteed(self, state, base_ctx):
        """大保底时 CR 不介入——透传给父类。"""
        bh = RotatingCRBehavior('test_cr', state, scope='ssr', cr_counter_threshold=3)
        # 设 guaranteed = True（大保底状态）
        state.set('test_cr', 'guaranteed', True)

        result = bh.before_draw(base_ctx)
        # 大保底：100% featured（由父类 RotatingBehavior 处理）
        assert result['ssr_featured'] == pytest.approx(0.01)

    def test_readonly_mode_no_random_change(self, state, base_ctx):
        """readonly=True 时不执行随机判定——确定性返回。"""
        bh = RotatingCRBehavior('test_cr', state, scope='ssr', cr_counter_threshold=3)
        state.set('test_cr', 'guaranteed', False)
        state.set('test_cr', 'cr_counter', 0)
        result = bh.before_draw(base_ctx, readonly=True)
        # 小保底——featured 占比由基础分布决定
        assert result['ssr_featured'] == pytest.approx(0.005)


# ══════════════════════════════════════════════════════════════════
# RotatingSoftBehavior —— 轮换 + 软保底（mixin）
# ══════════════════════════════════════════════════════════════════


    def test_cr_base_rate_deterministic(self, state, base_ctx):
        """cr_base_rate=1.0 forces 100% intercept; cr_base_rate=0 never intercepts."""
        bh_full = RotatingCRBehavior('test_cr_full', state, scope='ssr',
                                      cr_counter_threshold=3, cr_base_rate=1.0)
        state.set('test_cr_full', 'guaranteed', False)
        state.set('test_cr_full', 'cr_counter', 0)
        result = bh_full.before_draw(base_ctx)
        assert result['ssr_featured'] == pytest.approx(0.01)

        bh_none = RotatingCRBehavior('test_cr_none', state, scope='ssr',
                                      cr_counter_threshold=3, cr_base_rate=0.0)
        state.set('test_cr_none', 'guaranteed', False)
        state.set('test_cr_none', 'cr_counter', 0)
        result2 = bh_none.before_draw(base_ctx)
        assert result2['ssr_featured'] == pytest.approx(0.005)

    def test_cr_state_probs_boundary(self, state, base_ctx):
        """cr_state_probs[idx]=1.0 triggers intercept at that state."""
        bh = RotatingCRBehavior('test_cr_sp', state, scope='ssr',
                                 cr_counter_threshold=2,
                                 cr_state_probs=[1.0, 0.0, 0.0])
        state.set('test_cr_sp', 'guaranteed', False)
        state.set('test_cr_sp', 'cr_counter', 0)
        result = bh.before_draw(base_ctx)
        assert result['ssr_featured'] == pytest.approx(0.01)

        bh2 = RotatingCRBehavior('test_cr_sp2', state, scope='ssr',
                                  cr_counter_threshold=2,
                                  cr_state_probs=[0.0, 1.0, 0.0])
        state.set('test_cr_sp2', 'guaranteed', False)
        state.set('test_cr_sp2', 'cr_counter', 1)
        result2 = bh2.before_draw(base_ctx)
        assert result2['ssr_featured'] == pytest.approx(0.01)

class TestRotatingSoftBehavior:
    """mixin 提供 counter 管理 + deltas 引擎委托。"""

    def test_counter_increments_on_before_draw(self, state, base_ctx):
        """before_draw 递增 counter。"""
        bh = RotatingSoftBehavior('test_rs', state, scope='ssr',
                                   soft_start=74, soft_end=90)
        bh.before_draw(base_ctx)
        assert state.get('test_rs', 'counter', 0) == 1

    def test_ssr_resets_counter(self, state, base_ctx):
        """SSR 出货 → counter 重置。"""
        bh = RotatingSoftBehavior('test_rs', state, scope='ssr',
                                   soft_start=74, soft_end=90)
        # 递增几次 counter
        for _ in range(10):
            bh.before_draw(base_ctx)
        assert state.get('test_rs', 'counter', 0) == 10

        # SSR 出货
        hit_draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='f1', reward_rarity='ssr', is_featured=True,
            scope_cards={'ssr': ('f1',)}, featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured',)}, featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured'},
            base_probabilities={'ssr_featured': 0.01}, rarity_rank={'ssr': 3},
        )
        hit_ctx = PityContext(draw=hit_draw, current={}, state=state)
        bh.after_draw(hit_ctx)
        assert state.get('test_rs', 'counter', 0) == 0

    def test_readonly_no_counter_increment(self, state, base_ctx):
        """readonly=True 不递增 counter。"""
        bh = RotatingSoftBehavior('test_rs', state, scope='ssr',
                                   soft_start=74, soft_end=90)
        bh.before_draw(base_ctx, readonly=True)
        assert state.get('test_rs', 'counter', 0) == 0

    def test_guaranteed_flag_works_with_mixin(self, state, base_ctx):
        """mixin 不破坏 rotating 的大小保底翻转。"""
        bh = RotatingSoftBehavior('test_rs', state, scope='ssr',
                                   soft_start=74, soft_end=90)
        # 歪一次
        miss_draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
            featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured', 's1': 'ssr_standard'},
            base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
            rarity_rank={'ssr': 3},
        )
        bh.after_draw(PityContext(draw=miss_draw, current={}, state=state))
        assert state.get('test_rs', 'guaranteed', False) is True


# ══════════════════════════════════════════════════════════════════
# RotatingCRSoftBehavior —— CR + 软保底（mixin）
# ══════════════════════════════════════════════════════════════════

class TestRotatingCRSoftBehavior:
    """CR + 软保底组合——mixin 提供 counter 管理。"""

    def test_combined_cr_and_soft_counter(self, state, base_ctx):
        """CR counter 和 soft counter 独立运作。"""
        bh = RotatingCRSoftBehavior('test_crs', state, scope='ssr',
                                     cr_counter_threshold=3,
                                     soft_start=74, soft_end=90)
        # 递增 soft counter
        bh.before_draw(base_ctx)
        assert state.get('test_crs', 'counter', 0) == 1

        # 歪一次 → cr_counter++
        miss_draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
            featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured', 's1': 'ssr_standard'},
            base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
            rarity_rank={'ssr': 3},
        )
        bh.after_draw(PityContext(draw=miss_draw, current={}, state=state))
        assert state.get('test_crs', 'cr_counter', 0) == 1
        # SSR 出货后 soft counter 重置
        assert state.get('test_crs', 'counter', 0) == 0


# ══════════════════════════════════════════════════════════════════
# _redistribute_scope —— 概率重分配工具函数
# ══════════════════════════════════════════════════════════════════

class TestRedistributeScope:
    """模块级概率重分配函数。"""

    def test_full_featured_ratio(self, base_ctx):
        """featured_ratio=1.0 → 全部概率归入 featured 槽。"""
        result = _redistribute_scope(
            base_ctx, featured_ratio=1.0, total=0.01,
            featured_slots=('ssr_featured',), scope='ssr',
        )
        assert result['ssr_featured'] == pytest.approx(0.01)
        assert result['ssr_standard'] == pytest.approx(0.0)

    def test_half_featured_ratio_preserves_proportions(self, base_ctx):
        """featured_ratio=0.5 → featured/standard 各占 50%，内部按权重比例分配。"""
        result = _redistribute_scope(
            base_ctx, featured_ratio=0.5, total=0.01,
            featured_slots=('ssr_featured',), scope='ssr',
        )
        assert result['ssr_featured'] == pytest.approx(0.005)
        assert result['ssr_standard'] == pytest.approx(0.005)

    def test_zero_total_ratio_math(self, base_ctx):
        """total=0 时重分配算出全零——由调用方负责前置守卫（RotatingBehavior 已有）。"""
        result = _redistribute_scope(
            base_ctx, featured_ratio=0.5, total=0.0,
            featured_slots=('ssr_featured',), scope='ssr',
        )
        # total=0 → 所有槽位概率归零——调用方应在调用前检查 total<=0
        assert result['ssr_featured'] == pytest.approx(0.0)
        assert result['ssr_standard'] == pytest.approx(0.0)
