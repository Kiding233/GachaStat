"""保底引擎测试：SoftStepBehavior / HardPityBehavior / PityState / PityEngine"""
import pytest
from gacha_simulator.core.pity import (
    HardPityBehavior,
    PityDefParsed, PoolPitySpec, PityState, PityEngine,
    Counter, Flag, DrawInfo, PityContext,
    CounterBasedBehavior, SoftStepBehavior, LifecycleConfig,
    create_behavior, BEHAVIOR_REGISTRY, compute_scope_mappings,
)


# ═══════════════════════════════════════════════════════════════════
# Task 13(a1): 保底引擎核心——软/硬保底 + 3 种重置语义
# ═══════════════════════════════════════════════════════════════════

class TestSoftStepProgress:
    """SoftStepBehavior 概率爬升——_cumulative_boost 与旧 _progress 等价"""

    @staticmethod
    def _make_soft_behavior(start=73, end=90):
        """构造等价于旧 SoftPityBehavior(start_at=73, end_at=90) 的 SoftStepBehavior。"""
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        deltas = _expand_soft_to_deltas('soft_interval', start, end, None)
        return SoftStepBehavior(
            name='test', state=PityState(), scope='ssr', btype='soft_interval',
            deltas=deltas, reset='ssr',
        )

    def test_boost_zero_below_start(self):
        """counter < start → boost=0"""
        bh = self._make_soft_behavior(73, 90)
        assert bh._cumulative_boost(72) == 0.0
        assert bh._cumulative_boost(73) == 0.0  # first step is (73, 0.0)

    def test_boost_increases_after_start(self):
        """counter 进入增量段后 boost 递增"""
        bh = self._make_soft_behavior(73, 90)
        # deltas = ((73, 0.0), (17, 5.88235...)) → counter=74: boost=5.88%
        assert bh._cumulative_boost(74) > 0
        assert bh._cumulative_boost(80) > bh._cumulative_boost(74)

    def test_boost_reaches_100_at_end(self):
        """counter=end 时 boost=100%"""
        bh = self._make_soft_behavior(73, 90)
        assert bh._cumulative_boost(90) == pytest.approx(100.0)

    def test_boost_clamped_at_100(self):
        """counter 超出范围后 boost 封顶 100%"""
        bh = self._make_soft_behavior(73, 90)
        assert bh._cumulative_boost(100) == pytest.approx(100.0)
        assert bh._cumulative_boost(200) == pytest.approx(100.0)

    def test_target_featured_preserves_total(self):
        """feature_slot 分离后概率和保持"""
        bh = SoftStepBehavior(
            name='test', state=PityState(), scope='ssr', btype='soft_interval',
            deltas=((80, 0.0), (10, 10.0)), target_featured=True, reset='featured',
        )
        probs = {'ssr': 0.002, 'ssr_featured': 0.002, 'sr': 0.051, 'r': 0.945}
        draw = DrawInfo(
            pool_id='t', pool_instance_id='t', reward_id='', reward_rarity='',
            is_featured=False, scope_cards={}, rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
            scope_slots={'ssr': ('ssr', 'ssr_featured'), 'sr': ('sr',), 'r': ('r',)},
            featured_slots={'ssr': ('ssr_featured',), 'sr': ('sr',), 'r': ('r',)},
            base_probabilities=probs,
        )
        ctx = PityContext(draw=draw, current=probs.copy(), state=PityState())
        for c in [0, 40, 80, 85, 90, 100]:
            result = bh._compute_probabilities(ctx, c)
            assert sum(result.values()) == pytest.approx(1.0)


class TestHardPityNewArchitecture:
    """硬保底——CounterBasedBehavior 子类"""

    def _make_hard(self, threshold=90, target_featured=False):
        return HardPityBehavior(
            name='test', state=PityState(), scope='ssr', btype='hard',
            threshold=threshold, target_featured=target_featured, reset='ssr',
        )

    def _make_ctx(self, probs=None):
        if probs is None:
            probs = {'ssr': 0.006, 'sr': 0.051, 'r': 0.943}
        draw = DrawInfo(
            pool_id='t', pool_instance_id='t', reward_id='', reward_rarity='',
            is_featured=False, scope_cards={}, rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
            scope_slots={'ssr': ('ssr',), 'sr': ('sr',), 'r': ('r',)},
            featured_slots={'ssr': ('ssr',), 'sr': ('sr',), 'r': ('r',)},
            base_probabilities=probs,
        )
        return PityContext(draw=draw, current=probs.copy(), state=PityState())

    def test_below_threshold_unchanged(self):
        bh = self._make_hard(90)
        ctx = self._make_ctx()
        result = bh._compute_probabilities(ctx, 89)
        assert result == pytest.approx(ctx.current)

    def test_at_threshold_ssr_100_pct(self):
        bh = self._make_hard(90)
        ctx = self._make_ctx()
        result = bh._compute_probabilities(ctx, 90)
        assert result['ssr'] == pytest.approx(1.0)
        assert result['sr'] == pytest.approx(0.0)

    def test_threshold_early_reached(self):
        bh = self._make_hard(50)
        ctx = self._make_ctx()
        result = bh._compute_probabilities(ctx, 50)
        assert result['ssr'] == pytest.approx(1.0)

    def test_hard_preserves_sum(self):
        bh = self._make_hard(90)
        ctx = self._make_ctx()
        for c in [0, 50, 89, 90, 100]:
            result = bh._compute_probabilities(ctx, c)
            assert sum(result.values()) == pytest.approx(1.0)


class TestPityState:
    """保底计数器状态"""

    def test_increment_new_counter(self):
        state = PityState()
        state.incr('soft_ssr', 'counter')
        assert state.get('soft_ssr', 'counter', 0) == 1

    def test_increment_existing(self):
        state = PityState()
        state.data.setdefault('soft_ssr', {})['counter'] = 5
        state.incr('soft_ssr', 'counter')
        assert state.get('soft_ssr', 'counter', 0) == 6

    def test_reset(self):
        state = PityState()
        state.data.setdefault('soft_ssr', {})['counter'] = 10
        state.set('soft_ssr', 'counter', 0)
        assert state.get('soft_ssr', 'counter', 0) == 0

    def test_get_nonexistent(self):
        state = PityState()
        assert state.get('nonexistent', 'counter', 0) == 0

    def test_clone_independent(self):
        state = PityState()
        state.incr('soft_ssr', 'counter')
        cloned = state.clone()
        cloned.incr('soft_ssr', 'counter')
        assert state.get('soft_ssr', 'counter', 0) == 1
        assert cloned.get('soft_ssr', 'counter', 0) == 2

    def test_to_from_dict_roundtrip(self):
        state = PityState()
        state.data = {'soft_ssr': {'counter': 5}, 'hard_ssr': {'counter': 2}}
        d = state.to_dict()
        restored = PityState.from_dict(d)
        assert restored.get('soft_ssr', 'counter', 0) == 5
        assert restored.get('hard_ssr', 'counter', 0) == 2


class TestPityEngineReset:
    """PityEngine after_draw 三种重置语义（新 API）"""

    @staticmethod
    def _make_engine(reset='any_ssr'):
        from gacha_simulator.core.config_store import PityDef as _PityDef
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        deltas = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        pdef = _PityDef(
            name='test_pity', btype='soft_interval', scope='ssr',
            deltas=deltas, reset=reset, pools=('*',),
        )
        state = PityState()
        bh = create_behavior(pdef, state)
        spec = PoolPitySpec(
            pity_names=['test_pity'],
            ssr_ids={'ssr_card', 'featured_card'},
            featured_ids={'featured_card'},
            scope_cards={'ssr': ('ssr_card', 'featured_card')},
            scope_slots={'ssr': ('ssr',)},
            featured_slots={'ssr': ('ssr',)},
        )
        engine = PityEngine(
            pool_specs={'test_pool': spec},
            pity_defs=[pdef],
            state=state,
            rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
        )
        return engine, state

    def test_ssr_reset_on_ssr(self):
        """_reset='ssr' → 抽到任何 SSR 都重置"""
        engine, state = self._make_engine('ssr')
        state.incr('test_pity', 'counter')
        state.incr('test_pity', 'counter')
        assert state.get('test_pity', 'counter', 0) == 2
        engine.after_draw('test_pool', state, 'ssr_card')
        assert state.get('test_pity', 'counter', 0) == 0

    def test_ssr_no_reset_on_sr(self):
        """_reset='ssr' → 非 SSR 不重置"""
        engine, state = self._make_engine('ssr')
        state.incr('test_pity', 'counter')
        engine.after_draw('test_pool', state, 'sr_card')
        assert state.get('test_pity', 'counter', 0) == 1

    def test_featured_reset_only_on_featured(self):
        """_reset='featured' → 标准 SSR 不重置"""
        engine, state = self._make_engine('featured')
        state.incr('test_pity', 'counter')
        engine.after_draw('test_pool', state, 'ssr_card')
        assert state.get('test_pity', 'counter', 0) == 1

    def test_featured_reset_on_featured(self):
        """_reset='featured' → featured SSR 触发重置"""
        engine, state = self._make_engine('featured')
        state.incr('test_pity', 'counter')
        engine.after_draw('test_pool', state, 'featured_card')
        assert state.get('test_pity', 'counter', 0) == 0

    def test_deactivate_on_early_hit(self):
        """deactivate_on_early_hit=True → 触发后停用，计数器保持（由 _on_reset 接管）"""
        from gacha_simulator.core.config_store import PityDef as _PityDef
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        deltas = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        pdef = _PityDef(
            name='test_once', btype='soft_interval', scope='ssr',
            deltas=deltas, reset='ssr',
            max_triggers=1, deactivate_on_early_hit=True,
            pools=('*',),
        )
        state2 = PityState()
        create_behavior(pdef, state2)
        spec2 = PoolPitySpec(
            pity_names=['test_once'],
            ssr_ids={'ssr_card'},
            featured_ids=set(),
            scope_cards={'ssr': ('ssr_card',)},
            scope_slots={'ssr': ('ssr',)},
            featured_slots={'ssr': ('ssr',)},
        )
        eng2 = PityEngine(
            pool_specs={'test_pool': spec2},
            pity_defs=[pdef],
            state=state2,
            rarity_rank={'ssr': 0},
        )
        state2.incr('test_once', 'counter')
        assert state2.get('test_once', 'counter', 0) == 1
        eng2.after_draw('test_pool', state2, 'ssr_card')
        # deactivate_on_early_hit=True → _on_reset 返回 True，
        # 跳过默认 counter reset，behavior 被停用
        assert state2.get('test_once', 'counter', 0) == 1  # counter 保持
        assert state2.get('test_once', '_active', True) is False  # 已停用


class TestPityEngineBeforeDraw:
    """PityEngine before_draw / get_probabilities（新 API）"""

    @staticmethod
    def _make_engine():
        from gacha_simulator.core.config_store import PityDef as _PityDef
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        deltas = _expand_soft_to_deltas('soft_interval', 74, 90, None)
        pdef = _PityDef(
            name='test_pity', btype='soft_interval', scope='ssr',
            deltas=deltas, reset='ssr', pools=('*',),
        )
        state = PityState()
        create_behavior(pdef, state)
        spec = PoolPitySpec(
            pity_names=['test_pity'],
            ssr_ids={'ssr_card'},
            scope_cards={'ssr': ('ssr_card',)},
            scope_slots={'ssr': ('ssr',)},
            featured_slots={'ssr': ('ssr',)},
        )
        engine = PityEngine(
            pool_specs={'pool': spec},
            pity_defs=[pdef],
            state=state,
            rarity_rank={'ssr': 0, 'r': 1},
        )
        return engine, state

    def test_before_draw_increments_counter(self):
        engine, state = self._make_engine()
        probs = engine.before_draw('pool', state, {'ssr': 0.006, 'r': 0.994})
        assert state.get('test_pity', 'counter', 0) == 1
        assert 'ssr' in probs

    def test_before_draw_unknown_pool(self):
        engine = PityEngine(pool_specs={}, pity_defs=[], state=PityState(), rarity_rank={})
        state = PityState()
        probs = engine.before_draw('nonexistent', state, {'a': 1.0})
        assert probs == {'a': 1.0}

    def test_get_probabilities_at_pity_cap(self):
        engine, state = self._make_engine()
        state.data.setdefault('test_pity', {})['counter'] = 90
        probs = engine.get_probabilities('pool', state, {'ssr': 0.006, 'r': 0.994})
        assert probs['ssr'] == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════════════════
# Task 13(a2): 多保底叠加 + 计数器边界
# ═══════════════════════════════════════════════════════════════════

class TestMultiPityStacking:
    """多保底叠加顺序（新 API）"""

    @staticmethod
    def _make_two_pity_engine():
        from gacha_simulator.core.config_store import PityDef as _PityDef
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        deltas = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        soft_pdef = _PityDef(
            name='soft', btype='soft_interval', scope='ssr',
            deltas=deltas, reset='ssr', pools=('*',),
        )
        hard_pdef = _PityDef(
            name='hard', btype='hard', scope='ssr',
            threshold=90, reset='ssr', pools=('*',),
        )
        state = PityState()
        create_behavior(soft_pdef, state)
        create_behavior(hard_pdef, state)
        spec = PoolPitySpec(
            pity_names=['soft', 'hard'],
            ssr_ids={'ssr_card'},
            scope_cards={'ssr': ('ssr_card',)},
            scope_slots={'ssr': ('ssr',)},
            featured_slots={'ssr': ('ssr',)},
        )
        engine = PityEngine(
            pool_specs={'pool': spec},
            pity_defs=[soft_pdef, hard_pdef],
            state=state,
            rarity_rank={'ssr': 0, 'r': 1},
        )
        return engine, state

    def test_two_pities_stack(self):
        """软保底+硬保底叠加"""
        engine, state = self._make_two_pity_engine()
        # counter=82: 软保底生效但未达100%，硬保底未触发
        state.data = {'soft': {'counter': 82, '_active': True},
                      'hard': {'counter': 82, '_active': True}}
        probs = engine.get_probabilities('pool', state, {'ssr': 0.006, 'r': 0.994})
        assert 0.3 < probs['ssr'] < 0.99  # soft pity active, not 100%

        # counter=90: 硬保底覆盖 → SSR=100%
        state.data = {'soft': {'counter': 90, '_active': True},
                      'hard': {'counter': 90, '_active': True}}
        probs = engine.get_probabilities('pool', state, {'ssr': 0.006, 'r': 0.994})
        assert probs['ssr'] == pytest.approx(1.0)

    def test_pity_order_matters(self):
        """软保底(soft_interval)先于硬保底(hard)执行——概率叠加正确"""
        from gacha_simulator.core.config_store import PityDef as _PityDef
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        deltas = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        spdef = _PityDef(name='s', btype='soft_interval', scope='ssr',
                         deltas=deltas, reset='ssr', pools=('*',))
        hpdef = _PityDef(name='h', btype='hard', scope='ssr',
                         threshold=90, reset='ssr', pools=('*',))
        state3 = PityState()
        create_behavior(spdef, state3)
        create_behavior(hpdef, state3)
        spec3 = PoolPitySpec(
            pity_names=['s', 'h'],
            ssr_ids={'ssr_card'},
            scope_cards={'ssr': ('ssr_card',)},
            scope_slots={'ssr': ('ssr',)},
            featured_slots={'ssr': ('ssr',)},
        )
        eng3 = PityEngine(
            pool_specs={'pool': spec3}, pity_defs=[spdef, hpdef],
            state=state3, rarity_rank={'ssr': 0, 'r': 1},
        )
        state3.data = {'s': {'counter': 82, '_active': True},
                       'h': {'counter': 82, '_active': True}}
        probs = eng3.get_probabilities('pool', state3, {'ssr': 0.006, 'r': 0.994})
        assert 0.3 < probs['ssr'] < 0.99


class TestCounterBoundaries:
    """保底计数器边界——HardPityBehavior._compute_probabilities"""

    def _make_hard_ctx(self, probs=None):
        if probs is None:
            probs = {'ssr': 0.006, 'r': 0.994}
        draw = DrawInfo(
            pool_id='t', pool_instance_id='t', reward_id='', reward_rarity='',
            is_featured=False, scope_cards={}, rarity_rank={'ssr': 0, 'r': 1},
            scope_slots={'ssr': ('ssr',)}, featured_slots={'ssr': ('ssr',)},
            base_probabilities=probs,
        )
        return PityContext(draw=draw, current=probs.copy(), state=PityState())

    def test_counter_zero(self):
        bh = HardPityBehavior(name='t', state=PityState(), scope='ssr',
                              btype='hard', threshold=90, reset='ssr')
        ctx = self._make_hard_ctx()
        result = bh._compute_probabilities(ctx, 0)
        assert result == pytest.approx(ctx.current)

    def test_counter_threshold_minus_one(self):
        bh = HardPityBehavior(name='t', state=PityState(), scope='ssr',
                              btype='hard', threshold=90, reset='ssr')
        ctx = self._make_hard_ctx()
        result = bh._compute_probabilities(ctx, 89)
        assert result == pytest.approx(ctx.current)  # 尚未触发

    def test_counter_at_threshold(self):
        bh = HardPityBehavior(name='t', state=PityState(), scope='ssr',
                              btype='hard', threshold=90, reset='ssr')
        ctx = self._make_hard_ctx()
        result = bh._compute_probabilities(ctx, 90)
        assert result['ssr'] == pytest.approx(1.0)  # 触发

    def test_soft_boundary_start(self):
        """counter=start 时 boost=0，概率不变"""
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        deltas = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        bh = SoftStepBehavior(name='t', state=PityState(), scope='ssr',
                              btype='soft_interval', deltas=deltas, reset='ssr')
        ctx = self._make_hard_ctx({'ssr': 0.006, 'r': 0.994})
        result = bh._compute_probabilities(ctx, 72)
        assert result['ssr'] == pytest.approx(0.006)
        result73 = bh._compute_probabilities(ctx, 73)
        assert result73['ssr'] >= 0.006  # at start, first step has 0% boost

    def test_soft_boundary_end(self):
        """counter=end 时 boost=100%，SSR=100%"""
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        deltas = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        bh = SoftStepBehavior(name='t', state=PityState(), scope='ssr',
                              btype='soft_interval', deltas=deltas, reset='ssr')
        ctx = self._make_hard_ctx({'ssr': 0.006, 'r': 0.994})
        result = bh._compute_probabilities(ctx, 90)
        assert result['ssr'] == pytest.approx(1.0)
