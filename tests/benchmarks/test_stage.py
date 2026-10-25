"""T1：`stage.py` 的解析与归一——**用手工构造的 `stage_times` 与 `packet_bytes` 输入**。

对应 §3.9 T1「`stage.py` 解析与归一」与 §3.5 / §3.3 的采集面口径。
"""

import pytest

from benchmarks.perf.profilers.stage import (
    STAGES,
    WARN_BYTES_UNAVAILABLE,
    WARN_RSS_NOT_COLLECTED,
    WARN_RSS_UNAVAILABLE,
    WARN_STAGE_ABSENT,
    WARN_STAGE_MISSING,
    WARN_STAGES_NOT_COLLECTED,
    map_product_stage_times,
    normalize_resources,
    normalize_stages,
    stage_label,
)


class TestStageVocabulary:
    def test_six_stages(self):
        assert len(STAGES) == 6
        assert STAGES == ('config_load', 'env_build', 'pool_start', 'simulate',
                          'extract', 'dispatch')

    def test_labels_cover_all(self):
        assert set(STAGES) <= set(__import__(
            'benchmarks.perf.profilers.stage', fromlist=['STAGE_LABELS']).STAGE_LABELS)
        assert stage_label('dispatch') == '分发'
        assert stage_label('unknown') == 'unknown'


class TestProductStageTimes:
    def test_maps_three_keys(self):
        assert map_product_stage_times({'pool_start': 1.0, 'simulate': 2.0, 'extract': 3.0}) == {
            'pool_start': 1.0, 'simulate': 2.0, 'extract': 3.0}

    def test_empty_is_not_collected(self):
        """空 dict（`collect_perf=False` 时槽保持空）视同**未采集**，不是「三个 0」。"""
        assert map_product_stage_times({}) is None
        assert map_product_stage_times(None) is None

    def test_unknown_key_rejected(self):
        with pytest.raises(ValueError, match='未知键'):
            map_product_stage_times({'nope': 1.0})


class TestNormalizeStages:
    def test_full_set(self):
        raw = {'config_load': 0.3, 'env_build': 0.15, 'pool_start': 0.8,
               'simulate': 12.5, 'extract': 1.2, 'dispatch': 0.05}
        stages, warnings = normalize_stages(raw)
        assert stages == raw
        assert warnings == []

    def test_structural_absence_is_distinct_from_missing(self):
        """两种缺失成因可区分——读数据的人才知道该不该去排查。"""
        stages, warnings = normalize_stages({'simulate': 1.0}, absent_by_design=('dispatch',))
        assert stages == {'simulate': 1.0}
        absent = [w for w in warnings if w.startswith('本路径不产出')]
        missing = [w for w in warnings if w.startswith('该段未采集')]
        assert len(absent) == 1 and 'dispatch' in absent[0]
        assert len(missing) == 4

    def test_absent_declaration_is_inert_when_present(self):
        """声明了不产出、但实际上采到了——不报「不产出」，也不报「未采集」。"""
        _, warnings = normalize_stages({s: 1.0 for s in STAGES}, absent_by_design=('dispatch',))
        assert warnings == []

    def test_not_collected_returns_empty_and_one_warning(self):
        stages, warnings = normalize_stages(None)
        assert stages == {}
        assert warnings == [WARN_STAGES_NOT_COLLECTED]

    def test_order_follows_vocabulary(self):
        stages, _ = normalize_stages({'dispatch': 1.0, 'config_load': 2.0})
        assert list(stages) == ['config_load', 'dispatch']

    def test_unknown_stage_rejected(self):
        with pytest.raises(ValueError, match='未知段名'):
            normalize_stages({'bogus': 1.0})

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match='负值'):
            normalize_stages({'simulate': -1.0})

    def test_warning_constants_are_the_ones_emitted(self):
        _, warnings = normalize_stages({'simulate': 1.0}, absent_by_design=('dispatch',))
        assert any(w.startswith(WARN_STAGE_ABSENT.split('{')[0]) for w in warnings)
        assert any(w.startswith(WARN_STAGE_MISSING.split('{')[0]) for w in warnings)


class TestNormalizeResources:
    def test_bytes_is_per_simulation_median(self):
        """取 per-simulation 中位数而非总和——总和随 `n` 增长，而 `n` 本身是被测因子。"""
        result, _ = normalize_resources(packet_bytes=[1000, 3000, 2000])
        assert result.bytes == 2000

    def test_bytes_independent_of_n(self):
        one, _ = normalize_resources(packet_bytes=[1_688_000])
        many, _ = normalize_resources(packet_bytes=[1_688_000] * 1000)
        assert one.bytes == many.bytes == 1_688_000

    def test_missing_bytes_marks_unavailable(self):
        result, warnings = normalize_resources(subject='simulation')
        assert result.bytes is None
        assert WARN_BYTES_UNAVAILABLE in warnings

    def test_simulation_rss_never_collected(self):
        """`subject='simulation'` 下 RSS 恒为 None 属**定义如此**，不是缺失。"""
        result, warnings = normalize_resources(packet_bytes=[1], subject='simulation',
                                               rss_peak_mb=368.0)
        assert result.rss_peak_mb is None
        assert WARN_RSS_NOT_COLLECTED in warnings

    def test_startup_rss_collected(self):
        result, warnings = normalize_resources(subject='startup', rss_peak_mb=368.0)
        assert result.rss_peak_mb == 368.0
        assert WARN_RSS_NOT_COLLECTED not in warnings

    def test_startup_rss_unavailable_is_a_different_cause(self):
        """两种 None 的成因不得共用一句文案。"""
        _, warnings = normalize_resources(subject='startup', rss_peak_mb=None)
        assert WARN_RSS_UNAVAILABLE in warnings
        assert WARN_RSS_NOT_COLLECTED not in warnings
        assert WARN_RSS_UNAVAILABLE != WARN_RSS_NOT_COLLECTED

    def test_negative_bytes_rejected(self):
        with pytest.raises(ValueError, match='负值'):
            normalize_resources(packet_bytes=[-1])
