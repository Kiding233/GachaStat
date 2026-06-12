"""CompactResult 序列化往返测试"""
import numpy as np
from gacha_simulator.core.result_types import CompactResult


class TestCompactResultRoundtrip:
    """to_dict() → from_dict() 往返一致性"""

    def test_basic_roundtrip(self):
        original = CompactResult(
            total_draws=10,
            total_waits=2,
            total_consumed={'draw_resource': 1600.0},
            card_counts={'card_a': 1, 'card_b': 0},
            strategy_name='smart',
            final_time=86400.0,
        )
        d = original.to_dict()
        restored = CompactResult.from_dict(d)
        assert restored.total_draws == 10
        assert restored.total_waits == 2
        assert restored.total_consumed == {'draw_resource': 1600.0}
        assert restored.card_counts == {'card_a': 1, 'card_b': 0}
        assert restored.strategy_name == 'smart'

    def test_empty_result(self):
        original = CompactResult()
        d = original.to_dict()
        restored = CompactResult.from_dict(d)
        assert restored.total_draws == 0
        assert restored.total_consumed == {}
        assert restored.card_counts == {}
        assert restored.draw_card_ids == []

    def test_numpy_int64_conversion(self):
        """numpy int64 → Python int（通过 to_dict/from_dict 链）"""
        original = CompactResult(
            total_draws=100,
            card_counts={'card_a': np.int64(5), 'card_b': np.int64(0)},
            total_consumed={'draw_resource': np.float64(16000.0)},
        )
        d = original.to_dict()
        restored = CompactResult.from_dict(d)
        assert isinstance(restored.total_draws, int)
        assert restored.card_counts['card_a'] == 5
        assert restored.card_counts['card_b'] == 0

    def test_pool_draw_counts_roundtrip(self):
        original = CompactResult(
            pool_draw_counts={'pool_a': 50, 'pool_b': 30},
            pool_card_counts={'pool_a': {'card_x': 2}, 'pool_b': {}},
            pool_end_resources={'pool_a': {'draw': 100.0}},
        )
        d = original.to_dict()
        restored = CompactResult.from_dict(d)
        assert restored.pool_draw_counts == {'pool_a': 50, 'pool_b': 30}
        assert restored.pool_card_counts['pool_a'] == {'card_x': 2}

    def test_extra_keys_ignored(self):
        """from_dict 忽略未知 key——向前兼容"""
        d = {
            'total_draws': 42,
            'future_field': 'should_be_ignored',
            'another_unknown': [1, 2, 3],
        }
        restored = CompactResult.from_dict(d)
        assert restored.total_draws == 42
        # 不应有 future_field 属性

    def test_version_field_present(self):
        original = CompactResult()
        d = original.to_dict()
        assert 'result_version' in d
        assert d['result_version'] == 1


class TestCompactResultAccess:
    """get / __getitem__ / __contains__ 接口"""

    def test_get_existing(self):
        r = CompactResult(total_draws=10)
        assert r.get('total_draws') == 10

    def test_get_missing_default(self):
        r = CompactResult()
        assert r.get('nonexistent', 'fallback') == 'fallback'

    def test_getitem(self):
        r = CompactResult(total_draws=10)
        assert r['total_draws'] == 10

    def test_contains(self):
        r = CompactResult()
        assert 'total_draws' in r
        assert '_private' not in r
