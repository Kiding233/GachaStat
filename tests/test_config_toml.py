"""P55 阶段六+十B：TOML 糖展开 + 旧格式迁移测试"""
import pytest
from gacha_simulator.core.config_toml import (
    _expand_soft_to_deltas,
    _is_legacy_format,
    _migrate_legacy_pity,
    _deltas_to_soft_interval,
    _parse_deltas_value,
    load_toml,
)
from gacha_simulator.core.config_store import ConfigError
import tempfile
import os


# ═══════════════════════════════════════════════════════════════════
# 阶段六：_expand_soft_to_deltas
# ═══════════════════════════════════════════════════════════════════

class TestExpandSoftToDeltas:
    """soft_interval / soft_additive 语法糖 → deltas"""

    def test_soft_interval_linear(self):
        """start=73, end=90 → ((73, 0.0), (17, 5.882353...))"""
        result = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        assert len(result) == 2
        assert result[0] == (73, 0.0)
        assert result[1][0] == 17  # 17 抽
        assert pytest.approx(result[1][1], abs=1e-4) == 100.0 / 17

    def test_soft_interval_start_zero(self):
        """start=0, end=10 → ((0, 0.0), (10, 10.0))"""
        result = _expand_soft_to_deltas('soft_interval', 0, 10, None)
        assert result[0] == (0, 0.0)
        assert result[1][0] == 10

    def test_soft_interval_end_equals_start(self):
        """end <= start → 防御性修正为 start+1"""
        result = _expand_soft_to_deltas('soft_interval', 90, 90, None)
        assert result[0] == (90, 0.0)
        assert result[1][0] == 1  # 修正为 1

    def test_soft_additive(self):
        """start=74, increment=6.0 → ((74, 0.0), (N, 6.0))"""
        result = _expand_soft_to_deltas('soft_additive', 74, None, 6.0)
        assert result[0] == (74, 0.0)
        assert result[1][1] == 6.0
        # 达到 100% 需要的抽数 = ceil(100/6) + 1 = 17
        assert result[1][0] > 0

    def test_soft_additive_zero_increment(self):
        """increment=0.0 → 退化为 1 段（无增长）"""
        result = _expand_soft_to_deltas('soft_additive', 10, None, 0.0)
        assert result[0] == (10, 0.0)
        # increment=0.0 → 不计增长段
        assert result[1][1] == 0.0

    def test_unknown_btype_returns_empty(self):
        """非 soft_interval/soft_additive → 空 tuple"""
        result = _expand_soft_to_deltas('hard', 0, 0, None)
        assert result == ()


# ═══════════════════════════════════════════════════════════════════
# 阶段十B：旧格式迁移
# ═══════════════════════════════════════════════════════════════════

class TestIsLegacyFormat:
    """_is_legacy_format 检测"""

    def test_new_format_not_legacy(self):
        assert _is_legacy_format([
            {'name': 'p1', 'type': 'soft_interval', 'scope': 'ssr', 'start': 74, 'end': 90}
        ]) is False

    def test_old_format_with_start_detected(self):
        assert _is_legacy_format([
            {'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90}
        ]) is True

    def test_old_format_with_func_detected(self):
        assert _is_legacy_format([
            {'name': 'p1', 'type': 'soft', 'func': 'exp'}
        ]) is True

    def test_empty_list_not_legacy(self):
        assert _is_legacy_format([]) is False


class TestMigrateLegacyPity:
    """_migrate_legacy_pity 迁移规则"""

    def test_soft_interval_migration(self):
        """旧 soft → 新 soft_interval"""
        old = [{'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90}]
        new = _migrate_legacy_pity(old)
        assert new[0]['type'] == 'soft_interval'
        assert new[0]['scope'] == 'ssr'
        assert new[0]['start'] == 74
        assert new[0]['end'] == 90

    def test_hard_migration(self):
        """旧 hard → 新 hard"""
        old = [{'name': 'h1', 'type': 'hard', 'threshold': 180}]
        new = _migrate_legacy_pity(old)
        assert new[0]['type'] == 'hard'
        assert new[0]['threshold'] == 180

    def test_target_distribution_to_featured(self):
        """旧 target → 新 target_featured=true"""
        old = [{'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90,
                'target': {'limited_ssr': 100}}]
        new = _migrate_legacy_pity(old)
        assert new[0]['target_featured'] is True

    def test_reset_preserved(self):
        """reset 条件保留"""
        old = [{'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90,
                'reset': 'featured_ssr'}]
        new = _migrate_legacy_pity(old)
        assert new[0]['reset'] == 'featured_ssr'

    def test_counter_init_migrated(self):
        """旧 counter_init → 新 counter_init"""
        old = [{'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90,
                'counter_init': 30}]
        new = _migrate_legacy_pity(old)
        assert new[0]['counter_init'] == 30

    def test_func_exp_raises_config_error(self):
        """func='exp' → ConfigError"""
        old = [{'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90,
                'func': 'exp'}]
        with pytest.raises(ConfigError, match='exp'):
            _migrate_legacy_pity(old)

    def test_func_step_raises_config_error(self):
        """func='step' → ConfigError"""
        old = [{'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90,
                'func': 'step'}]
        with pytest.raises(ConfigError, match='step'):
            _migrate_legacy_pity(old)


class TestDeltasRoundTrip:
    """deltas ↔ soft_interval 往返可逆"""

    def test_round_trip(self):
        """deltas → soft_interval → 展开 → 等价"""
        deltas = ((73, 0.0), (17, 5.882353))
        result = _deltas_to_soft_interval(deltas)
        assert result is not None
        start, end = result
        expanded = _expand_soft_to_deltas('soft_interval', start, end, None)
        assert expanded[0] == deltas[0]
        assert expanded[1][0] == deltas[1][0]

    def test_non_soft_interval_returns_none(self):
        """首段增量非零 → 无法还原"""
        deltas = ((10, 5.0), (20, 10.0))
        assert _deltas_to_soft_interval(deltas) is None

    def test_single_segment_returns_none(self):
        """非标准双段 → 无法还原"""
        assert _deltas_to_soft_interval(((10, 1.0),)) is None


class TestMigrationRoundTrip:
    """旧格式 → 迁移 → 新格式 → 写回 → 再读 等价性"""

    def test_migration_preserves_semantics(self):
        """迁移后字段语义等价"""
        old = [
            {'name': 'ssr_soft', 'type': 'soft', 'start': 74, 'end': 90,
             'reset': 'any_ssr', 'counter_init': 0},
            {'name': 'ssr_hard', 'type': 'hard', 'threshold': 180},
        ]
        migrated = _migrate_legacy_pity(old)
        # 迁移后条目数一致
        assert len(migrated) == 2
        # soft → soft_interval
        assert migrated[0]['type'] == 'soft_interval'
        assert migrated[0]['scope'] == 'ssr'
        assert migrated[0]['start'] == 74
        assert migrated[0]['end'] == 90
        # hard → hard
        assert migrated[1]['type'] == 'hard'
        assert migrated[1]['threshold'] == 180


class TestParseDeltasValue:
    """_parse_deltas_value 解析"""

    def test_none_returns_none(self):
        assert _parse_deltas_value(None) is None

    def test_tuple_preserved(self):
        result = _parse_deltas_value(((10, 5.0), (20, 10.0)))
        assert result == ((10, 5.0), (20, 10.0))

    def test_list_converted(self):
        result = _parse_deltas_value([[10, 5.0], [20, 10.0]])
        assert result == ((10, 5.0), (20, 10.0))


class TestMigrationMarkRoundTrip:
    """migrated_from_legacy 标记往返测试"""

    def test_flag_set_on_migration(self):
        """旧格式加载后 migrated_from_legacy=True"""
        content = """[rarities]
ranks = [["SSR"], ["SR"], ["R"]]

[[pity]]
name = "s1"
type = "soft"
start = 74
end = 90
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml',
                                         delete=False, encoding='utf-8') as f:
            f.write(content)
            f.flush()
            path = f.name

        try:
            store = load_toml(path)
            assert store.migrated_from_legacy is True
            assert len(store.pity.pities) == 1
            assert store.pity.pities[0].btype == 'soft_interval'
        finally:
            os.unlink(path)

    def test_flag_false_on_new_format(self):
        """新格式加载后 migrated_from_legacy=False"""
        content = """[rarities]
ranks = [["SSR"], ["SR"], ["R"]]

[[pity]]
name = "s1"
type = "soft_interval"
scope = "ssr"
start = 74
end = 90
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml',
                                         delete=False, encoding='utf-8') as f:
            f.write(content)
            f.flush()
            path = f.name

        try:
            store = load_toml(path)
            assert store.migrated_from_legacy is False
        finally:
            os.unlink(path)
