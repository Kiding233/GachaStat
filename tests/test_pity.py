"""保底引擎测试：SoftPityBehavior / HardPityBehavior / PityState / PityEngine"""
import pytest
from gacha_simulator.core.pity import (
    SoftPityBehavior, HardPityBehavior,
    PityDefParsed, PoolPitySpec, PityState, PityEngine,
)


# ═══════════════════════════════════════════════════════════════════
# Task 13(a1): 保底引擎核心——软/硬保底 + 3 种重置语义
# ═══════════════════════════════════════════════════════════════════

class TestSoftPityBehavior:
    """软保底概率爬升曲线"""

    def test_inactive_below_start(self):
        soft = SoftPityBehavior(start_at=73, end_at=90, func_type='linear')
        assert soft.is_active(72) is False
        assert soft.is_active(73) is True

    def test_linear_interpolation_key_points(self):
        """线性插值：start→end→100% 三个关键点"""
        soft = SoftPityBehavior(start_at=73, end_at=90, func_type='linear')
        probs = {'ssr': 0.006, 'sr': 0.051, 'r': 0.943}

        # 未触发：概率不变
        result_before = soft.apply(72, probs)
        assert result_before == pytest.approx(probs)

        # 起始点（counter=73）：progress=0.0 → 概率不变
        result_start = soft.apply(73, probs)
        assert result_start['ssr'] == pytest.approx(0.006, abs=1e-6)

        # 终点（counter=90）：progress=1.0 → SSR=100%
        result_end = soft.apply(90, probs)
        assert result_end['ssr'] == pytest.approx(1.0)
        assert result_end['sr'] == pytest.approx(0.0)

    def test_apply_preserves_total_probability(self):
        """概率总和始终为 1.0"""
        soft = SoftPityBehavior(start_at=74, end_at=90, func_type='linear')
        probs = {'card_a': 0.01, 'card_b': 0.99}
        for c in range(73, 91):
            result = soft.apply(c, probs)
            assert sum(result.values()) == pytest.approx(1.0)

    def test_target_distribution_resolved(self):
        """指定 target_distribution 时概率倾向目标卡"""
        soft = SoftPityBehavior(
            start_at=74, end_at=90,
            target_distribution={'target_ssr': 1.0},
        )
        probs = {'target_ssr': 0.006, 'other_ssr': 0.006, 'r': 0.988}
        # 使用 extra 传入 resolved_targets
        result = soft.apply(90, probs, extra={
            'resolved_targets': {'target_ssr': 1.0},
        })
        assert result['target_ssr'] > 0.9

    def test_empty_probabilities(self):
        """空概率字典——不变"""
        soft = SoftPityBehavior(start_at=74, end_at=90)
        result = soft.apply(80, {})
        assert result == {}


class TestHardPityBehavior:
    """硬保底 100% 触发"""

    def test_below_threshold_inactive(self):
        hard = HardPityBehavior(threshold=90)
        assert hard.is_active(89) is False
        assert hard.is_active(90) is True

    def test_at_threshold_guarantees_ssr(self):
        hard = HardPityBehavior(threshold=90)
        probs = {'ssr': 0.006, 'sr': 0.051, 'r': 0.943}
        result = hard.apply(90, probs)
        assert result['ssr'] == pytest.approx(1.0)
        assert result['sr'] == pytest.approx(0.0)

    def test_below_threshold_unchanged(self):
        hard = HardPityBehavior(threshold=90)
        probs = {'ssr': 0.006, 'sr': 0.994}
        result = hard.apply(89, probs)
        assert result == pytest.approx(probs)

    def test_target_distribution_guaranteed(self):
        hard = HardPityBehavior(
            threshold=90,
            target_distribution={'featured': 1.0},
        )
        probs = {'featured': 0.003, 'standard': 0.003, 'r': 0.994}
        result = hard.apply(90, probs, extra={
            'resolved_targets': {'featured': 1.0},
        })
        assert result['featured'] == pytest.approx(1.0)
        assert result['standard'] == pytest.approx(0.0)


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
    """PityEngine after_draw 三种重置语义"""

    @staticmethod
    def _make_engine(reset_condition='any_ssr'):
        pity_def = PityDefParsed(
            name='test_pity',
            btype='soft',
            params={'start': '73', 'end': '90', 'func': 'linear'},
            target_distribution={},
            reset_condition=reset_condition,
            pools='*',
        )
        spec = PoolPitySpec(
            pity_names=['test_pity'],
            ssr_ids={'ssr_card'},
            featured_ids={'featured_card'},
        )
        behavior = SoftPityBehavior(start_at=73, end_at=90)
        engine = PityEngine(
            pool_specs={'test_pool': spec},
            pity_defs={'test_pity': pity_def},
            behaviors={'test_pity': behavior},
        )
        return engine

    def test_any_ssr_reset_on_ssr(self):
        engine = self._make_engine('any_ssr')
        state = PityState()
        state.incr('test_pity', 'counter')
        state.incr('test_pity', 'counter')
        assert state.get('test_pity', 'counter', 0) == 2
        engine.after_draw('test_pool', state, 'ssr_card')
        assert state.get('test_pity', 'counter', 0) == 0  # any SSR → reset

    def test_any_ssr_no_reset_on_sr(self):
        engine = self._make_engine('any_ssr')
        state = PityState()
        state.incr('test_pity', 'counter')
        engine.after_draw('test_pool', state, 'sr_card')
        assert state.get('test_pity', 'counter', 0) == 1  # not SSR → no reset

    def test_featured_ssr_reset_only_on_featured(self):
        engine = self._make_engine('featured_ssr')
        state = PityState()
        state.incr('test_pity', 'counter')
        engine.after_draw('test_pool', state, 'ssr_card')  # SSR but not featured
        assert state.get('test_pity', 'counter', 0) == 1  # no reset

    def test_featured_ssr_reset_on_featured(self):
        engine = self._make_engine('featured_ssr')
        state = PityState()
        state.incr('test_pity', 'counter')
        engine.after_draw('test_pool', state, 'featured_card')
        assert state.get('test_pity', 'counter', 0) == 0

    def test_never_no_reset(self):
        engine = self._make_engine('never')
        state = PityState()
        state.incr('test_pity', 'counter')
        engine.after_draw('test_pool', state, 'ssr_card')
        assert state.get('test_pity', 'counter', 0) == 1  # never → no reset ever


class TestPityEngineBeforeDraw:
    """PityEngine before_draw 计数器递增 + 概率调整"""

    def test_before_draw_increments_counter(self):
        pity_def = PityDefParsed('test_pity', 'soft', {}, {}, 'any_ssr', '*')
        spec = PoolPitySpec(pity_names=['test_pity'])
        behavior = SoftPityBehavior(start_at=74, end_at=90)
        engine = PityEngine(
            pool_specs={'pool': spec},
            pity_defs={'test_pity': pity_def},
            behaviors={'test_pity': behavior},
        )
        state = PityState()
        probs = engine.before_draw('pool', state, {'ssr': 0.006, 'r': 0.994})
        assert state.get('test_pity', 'counter', 0) == 1
        assert 'ssr' in probs

    def test_before_draw_unknown_pool(self):
        engine = PityEngine(pool_specs={}, pity_defs={}, behaviors={})
        state = PityState()
        probs = engine.before_draw('nonexistent', state, {'a': 1.0})
        assert probs == {'a': 1.0}

    def test_get_probabilities_with_pity_active(self):
        pity_def = PityDefParsed('test_pity', 'soft', {}, {}, 'any_ssr', '*')
        spec = PoolPitySpec(pity_names=['test_pity'])
        behavior = SoftPityBehavior(start_at=74, end_at=90)
        engine = PityEngine(
            pool_specs={'pool': spec},
            pity_defs={'test_pity': pity_def},
            behaviors={'test_pity': behavior},
        )
        state = PityState()
        state.data.setdefault('test_pity', {})['counter'] = 90  # at pity cap
        probs = engine.get_probabilities('pool', state, {'ssr': 0.006, 'r': 0.994})
        assert probs['ssr'] == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════════════════
# Task 13(a2): 多保底叠加 + 计数器边界
# ═══════════════════════════════════════════════════════════════════

class TestMultiPityStacking:
    """多保底叠加顺序"""

    def test_two_pities_stack(self):
        """软保底+硬保底叠加：软保底先提升、硬保底再覆盖"""
        soft_def = PityDefParsed('soft', 'soft',
                                 {'start': '73', 'end': '90'}, {}, 'any_ssr', '*')
        hard_def = PityDefParsed('hard', 'hard',
                                 {'threshold': '90'}, {}, 'any_ssr', '*')
        spec = PoolPitySpec(pity_names=['soft', 'hard'])
        soft = SoftPityBehavior(start_at=73, end_at=90)
        hard = HardPityBehavior(threshold=90)
        engine = PityEngine(
            pool_specs={'pool': spec},
            pity_defs={'soft': soft_def, 'hard': hard_def},
            behaviors={'soft': soft, 'hard': hard},
        )
        # counter=82: 软保底生效但未达100%（progress≈0.56），硬保底未触发
        state = PityState()
        state.data = {'soft': {'counter': 82}, 'hard': {'counter': 82}}
        probs = engine.get_probabilities('pool', state, {'ssr': 0.006, 'r': 0.994})
        assert 0.3 < probs['ssr'] < 0.99  # soft pity active, not 100%

        # counter=90: 硬保底覆盖 → SSR=100%
        state.data = {'soft': {'counter': 90}, 'hard': {'counter': 90}}
        probs = engine.get_probabilities('pool', state, {'ssr': 0.006, 'r': 0.994})
        assert probs['ssr'] == pytest.approx(1.0)

    def test_pity_order_matters(self):
        """pity_names 列表中后一个保底的行为会覆盖前一个"""
        soft_def = PityDefParsed('s', 'soft',
                                 {'start': '73', 'end': '90'}, {}, 'any_ssr', '*')
        hard_def = PityDefParsed('h', 'hard',
                                 {'threshold': '90'}, {}, 'any_ssr', '*')
        spec = PoolPitySpec(pity_names=['s', 'h'])
        soft = SoftPityBehavior(start_at=73, end_at=90)
        hard = HardPityBehavior(threshold=90)
        engine = PityEngine(
            pool_specs={'pool': spec},
            pity_defs={'s': soft_def, 'h': hard_def},
            behaviors={'s': soft, 'h': hard},
        )
        state = PityState()
        state.data = {'s': {'counter': 82}, 'h': {'counter': 82}}
        # 软保底先提升概率，硬保底尚未触发——SSR 概率在中间范围
        probs = engine.get_probabilities('pool', state, {'ssr': 0.006, 'r': 0.994})
        assert 0.3 < probs['ssr'] < 0.99


class TestCounterBoundaries:
    """保底计数器边界：0 / threshold-1 / threshold"""

    def test_counter_zero(self):
        hard = HardPityBehavior(threshold=90)
        probs = {'ssr': 0.006, 'r': 0.994}
        result = hard.apply(0, probs)
        assert result == pytest.approx(probs)  # 未触发

    def test_counter_threshold_minus_one(self):
        hard = HardPityBehavior(threshold=90)
        probs = {'ssr': 0.006, 'r': 0.994}
        result = hard.apply(89, probs)
        assert result == pytest.approx(probs)  # 尚未触发

    def test_counter_at_threshold(self):
        hard = HardPityBehavior(threshold=90)
        probs = {'ssr': 0.006, 'r': 0.994}
        result = hard.apply(90, probs)
        assert result['ssr'] == pytest.approx(1.0)  # 触发

    def test_soft_boundary_start_at(self):
        soft = SoftPityBehavior(start_at=73, end_at=90)
        probs = {'ssr': 0.006, 'r': 0.994}
        result_before = soft.apply(72, probs)
        result_at = soft.apply(73, probs)
        assert result_before['ssr'] == pytest.approx(0.006)  # identical at boundary
        assert result_at['ssr'] >= 0.006

    def test_soft_boundary_end_at(self):
        soft = SoftPityBehavior(start_at=73, end_at=90)
        probs = {'ssr': 0.006, 'r': 0.994}
        result = soft.apply(90, probs)
        assert result['ssr'] == pytest.approx(1.0)  # full upgrade at end
