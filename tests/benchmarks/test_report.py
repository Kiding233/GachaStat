"""T1：基线登记门禁与比值比对判据——**用手工构造的 `RunResult` 测，不依赖真实计时**。

对应 §3.9 T1「基线比对判据」、§3.5 的 repeats 政策与 AUDIT-BREAK-2 / AUDIT-BREAK-4。
"""

import json

import pytest

from benchmarks.perf.record import EnvFingerprint
from benchmarks.perf.report import (
    BASELINE_MIN_REPEATS,
    BaselineGateError,
    baseline_path,
    compare,
    find_baseline,
    format_comparison,
    load_baseline,
    register_baseline,
)


class TestBaselineGate:
    def test_registers_when_repeats_sufficient(self, tmp_path, make_result, fingerprint):
        path = register_baseline('smoke', make_result(), root=tmp_path)
        assert path.parent.name == fingerprint.machine_class
        assert path.name == 'smoke.json'

    def test_rejects_missing_repeats(self, tmp_path, record_without_repeats):
        """`repeats=None` 与 `3` 比较会抛 `TypeError`——必须**先判 None 再判大小**。"""
        with pytest.raises(BaselineGateError, match='字段缺失'):
            register_baseline('smoke', record_without_repeats(), root=tmp_path)

    def test_rejects_insufficient_repeats(self, tmp_path, make_result):
        with pytest.raises(BaselineGateError, match=str(BASELINE_MIN_REPEATS)):
            register_baseline('smoke', make_result(repeats=BASELINE_MIN_REPEATS - 1), root=tmp_path)

    def test_missing_and_insufficient_are_different_messages(self, tmp_path,
                                                            make_result, record_without_repeats):
        with pytest.raises(BaselineGateError) as missing:
            register_baseline('a', record_without_repeats(), root=tmp_path)
        with pytest.raises(BaselineGateError) as insufficient:
            register_baseline('b', make_result(repeats=2), root=tmp_path)
        assert str(missing.value) != str(insufficient.value)

    def test_downgraded_record_names_the_cause(self, tmp_path, make_result):
        with pytest.raises(BaselineGateError, match='repeats_downgraded'):
            register_baseline('d', make_result(repeats=1, repeats_downgraded=True), root=tmp_path)

    def test_nothing_written_on_rejection(self, tmp_path, make_result):
        with pytest.raises(BaselineGateError):
            register_baseline('never', make_result(repeats=1), root=tmp_path)
        assert not list(tmp_path.rglob('*.json'))

    def test_file_carries_scope_note(self, tmp_path, make_result, fingerprint):
        register_baseline('scoped', make_result(), root=tmp_path)
        payload = json.loads(baseline_path('scoped', fingerprint.machine_class, tmp_path)
                             .read_text(encoding='utf-8'))
        assert payload['machine_class'] == fingerprint.machine_class
        assert 'scope_note' in payload and fingerprint.cpu in payload['scope_note']


class TestLoadBaseline:
    def test_round_trip(self, tmp_path, make_result, fingerprint):
        original = make_result()
        register_baseline('rt', original, root=tmp_path)
        loaded = load_baseline('rt', fingerprint, root=tmp_path)
        assert loaded.to_dict() == original.to_dict()

    def test_missing_raises_with_expected_path(self, tmp_path, fingerprint):
        with pytest.raises(FileNotFoundError, match='nope'):
            load_baseline('nope', fingerprint, root=tmp_path)

    def test_find_returns_none_when_absent(self, tmp_path, fingerprint):
        assert find_baseline('nope', fingerprint, root=tmp_path) is None


class TestComparabilityGate:
    def test_same_dimensions_produce_ratios(self, make_result):
        comparison = compare(make_result(wall=1200.0), make_result(wall=1000.0))
        assert comparison.comparable
        assert comparison.wall_ratio == pytest.approx(1.2)
        assert comparison.byte_ratio == pytest.approx(1.0)
        assert set(comparison.stage_ratios) == {'config_load', 'simulate', 'extract'}

    def test_different_path_produces_no_ratios(self, make_result):
        comparison = compare(make_result(path='gui-qt'), make_result(path='cli'))
        assert not comparison.comparable
        assert comparison.wall_ratio is None
        assert comparison.byte_ratio is None
        assert comparison.stage_ratios == {}

    def test_different_subject_produces_no_ratios(self, make_result):
        comparison = compare(make_result(subject='startup'), make_result(subject='simulation'))
        assert not comparison.comparable and comparison.wall_ratio is None

    def test_unrecorded_dimension_is_not_reported_as_difference(self, make_result):
        """「未记录」不是「不同」——静默判不等会让读报告的人去查不存在的差异。"""
        comparison = compare(make_result(qt_qpa_platform='offscreen'),
                             make_result(qt_qpa_platform=None))
        assert any('未记录' in r for r in comparison.reasons)
        assert not any('取值不同' in r for r in comparison.reasons)

    def test_unrecorded_return_compact_same_treatment(self, make_result):
        comparison = compare(make_result(return_compact=None), make_result(return_compact=True))
        assert any('未记录' in r and 'return_compact' in r for r in comparison.reasons)

    def test_different_machine_class_only_shares(self, make_result):
        other = EnvFingerprint(cpu='Other', cores=4, os='Windows 11', python='3.12.5',
                               code_version='2.4.0', qt_qpa_platform='offscreen')
        comparison = compare(make_result(wall=1200.0), make_result(fp=other, wall=1000.0))
        assert not comparison.comparable
        assert comparison.wall_ratio is None
        assert comparison.current_stage_shares and comparison.baseline_stage_shares
        assert sum(comparison.current_stage_shares.values()) == pytest.approx(1.0)

    def test_stage_shares_available_even_when_incomparable(self, make_result):
        comparison = compare(make_result(path='gui-qt'), make_result(path='cli'))
        assert comparison.current_stage_shares


class TestRatioExclusions:
    def test_not_comparable_record_excluded(self, make_result):
        comparison = compare(make_result(wall=1200.0, not_comparable=True), make_result())
        assert comparison.wall_ratio is None
        assert any('not_comparable' in item for item in comparison.excluded)

    def test_missing_median_excluded(self, make_result):
        payload = make_result().to_dict()
        payload['wall_median'] = None
        from benchmarks.perf.record import RunResult
        comparison = compare(RunResult.from_dict(payload), make_result())
        assert comparison.wall_ratio is None
        assert any('wall_median' in item for item in comparison.excluded)

    def test_missing_bytes_excluded_not_treated_as_zero(self, make_result):
        comparison = compare(make_result(bytes_=1_688_000), make_result(bytes_=None))
        assert comparison.byte_ratio is None
        assert any('bytes' in item for item in comparison.excluded)

    def test_zero_baseline_excluded(self, make_result):
        comparison = compare(make_result(wall=1000.0), make_result(wall=0.0))
        assert comparison.wall_ratio is None
        assert any('比值无定义' in item for item in comparison.excluded)

    def test_stage_set_mismatch_warns(self, make_result):
        comparison = compare(make_result(stages={'simulate': 900.0}),
                             make_result(stages={'simulate': 900.0, 'dispatch': 5.0}))
        assert any('dispatch' in w for w in comparison.warnings)


class TestMissingRepeatsDegradation:
    """AUDIT-BREAK-2 的核心断言：缺字段按不可比处理并记 `warnings`，**不抛 TypeError**。"""

    def test_compare_does_not_raise(self, make_result, record_without_repeats):
        comparison = compare(record_without_repeats(wall=1200.0), make_result(wall=1000.0))
        assert comparison.wall_ratio == pytest.approx(1.2)

    def test_warning_recorded(self, make_result, record_without_repeats):
        comparison = compare(record_without_repeats(), make_result())
        assert any('repeats 缺失' in w for w in comparison.warnings)

    def test_gate_still_rejects_it(self, tmp_path, record_without_repeats):
        with pytest.raises(BaselineGateError):
            register_baseline('x', record_without_repeats(), root=tmp_path)


class TestReportText:
    def test_contains_ratio(self, make_result):
        current, baseline = make_result(wall=1200.0), make_result(wall=1000.0)
        text = format_comparison(compare(current, baseline), current=current,
                                 baseline=baseline, baseline_label='b1')
        assert '1.200' in text and 'b1' in text

    def test_states_incomparability(self, make_result):
        current, baseline = make_result(path='gui-qt'), make_result(path='cli')
        text = format_comparison(compare(current, baseline), current=current,
                                 baseline=baseline)
        assert '不可比' in text and 'path' in text

    def test_mentions_bytes_is_a_proxy(self, make_result):
        current, baseline = make_result(wall=1200.0), make_result(wall=1000.0)
        text = format_comparison(compare(current, baseline), current=current,
                                 baseline=baseline)
        assert '代理指标' in text


class TestRepeatsDowngradedPropagation:
    """`repeats_downgraded` 的传播（§3.9 T1）——它既要在比对侧可见，也要挡住基线登记。"""

    def test_visible_on_the_record(self, make_result):
        assert make_result(repeats=1, repeats_downgraded=True).repeats_downgraded is True
        assert make_result().repeats_downgraded is False

    def test_survives_serialization(self, make_result):
        from benchmarks.perf.record import RunResult
        record = make_result(repeats=1, repeats_downgraded=True)
        assert RunResult.from_dict(record.to_dict()).repeats_downgraded is True

    def test_blocks_baseline_registration(self, tmp_path, make_result):
        with pytest.raises(BaselineGateError, match='repeats_downgraded'):
            register_baseline('d', make_result(repeats=1, repeats_downgraded=True), root=tmp_path)

    def test_comparison_still_works(self, make_result):
        """降级记录不是「不可比」——它只是不能当基线。比值照出。"""
        comparison = compare(make_result(repeats=1, repeats_downgraded=True, wall=1200.0),
                             make_result(wall=1000.0))
        assert comparison.wall_ratio == pytest.approx(1.2)


class TestReturnCompactIsAComparabilityDimension:
    """§3.5：`return_compact` 不同则字节数不可比——**不得把两个取值直接作比值**。

    `return_compact=False` 时三元组首分量为 `None`（GUI 抽卡面板与 WebUI 在跑主模拟前
    置 `False`），`packet_bytes` 因而不含 `compact`，故 `gui-qt` / `webui` 的字节数
    **天然小于** `cli`。
    """

    def test_different_values_are_incomparable(self, make_result):
        comparison = compare(make_result(return_compact=True), make_result(return_compact=False))
        assert not comparison.comparable
        assert comparison.byte_ratio is None and comparison.wall_ratio is None
        assert any('return_compact' in r for r in comparison.reasons)

    def test_same_value_is_comparable(self, make_result):
        comparison = compare(make_result(return_compact=False, wall=1200.0),
                             make_result(return_compact=False, wall=1000.0))
        assert comparison.comparable and comparison.wall_ratio == pytest.approx(1.2)
