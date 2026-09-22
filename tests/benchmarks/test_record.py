"""T1：`RunResult` / `EnvFingerprint` 的序列化往返与环境指纹稳定性。

对应 §3.5「`RunResult` / `EnvFingerprint` 的字段表以 `1c` 为唯一真值源」与
AUDIT-BREAK-2 的「容忍 `None` 字段与浮点」。
"""

import json

import pytest

from benchmarks.perf.record import (
    EnvFingerprint,
    FuncStat,
    RunResult,
    SamplesMeta,
    SingleStats,
)

#: §3.5 真值源表列的 18 个字段——少一个即为 AUDIT-BREAK-2 的复发。
TRUTH_SOURCE_FIELDS = {
    'run_id', 'timestamp', 'path', 'is_user_path', 'fingerprint', 'plan',
    'repeats', 'wall_median', 'wall_samples', 'repeats_downgraded',
    'stages', 'single', 'functions', 'resources', 'return_compact',
    'samples_meta', 'not_comparable', 'warnings',
}


class TestFieldTable:
    def test_run_result_has_all_truth_source_fields(self, make_result):
        assert set(make_result().to_dict()) == TRUTH_SOURCE_FIELDS

    def test_env_fingerprint_has_all_truth_source_fields(self, fingerprint):
        assert set(fingerprint.to_dict()) == {
            'cpu', 'cores', 'os', 'python', 'code_version', 'qt_qpa_platform'}

    def test_repeats_and_comparability_fields_are_optional(self, make_result, record_without_repeats):
        """四字段必须可表达「未记录」——否则 §3.5 要求的降级无从落地。"""
        assert record_without_repeats().repeats is None
        payload = make_result().to_dict()
        assert RunResult.from_dict({**payload, 'wall_median': None}).wall_median is None
        assert RunResult.from_dict({**payload, 'return_compact': None}).return_compact is None
        no_qpa = RunResult.from_dict(
            {**payload, 'fingerprint': {**payload['fingerprint'], 'qt_qpa_platform': None}})
        assert no_qpa.fingerprint.qt_qpa_platform is None

    def test_single_is_reserved_and_none(self, make_result):
        """`grain='single'` 本期未实现，故 `single` 恒为 None（字段保留不删）。"""
        assert make_result().single is None
        assert SingleStats(min=1.0, median=2.0, max=3.0).median == 2.0


class TestSerialization:
    def test_round_trip_with_all_nested_types(self, make_result):
        result = make_result(
            functions=[FuncStat('core/pool.py:160(output)', 16600, 0.12, 0.13)],
            samples_meta=SamplesMeta(duration=8.0, samples=3193, errors=[]),
        )
        payload = json.loads(json.dumps(result.to_dict(), ensure_ascii=False))
        assert RunResult.from_dict(payload).to_dict() == result.to_dict()

    def test_nested_plan_survives(self, make_result):
        result = make_result()
        assert RunResult.from_dict(result.to_dict()).plan.canonical() == result.plan.canonical()

    def test_floats_accept_ints(self, make_result):
        """JSON 里整数是常见写法，浮点字段应归一而非报错。"""
        payload = make_result().to_dict()
        payload['wall_samples'] = [1, 2.5]
        payload['stages'] = {'simulate': 100}
        payload['resources'] = {'bytes': 1688000, 'rss_peak_mb': 368}
        back = RunResult.from_dict(payload)
        assert back.wall_samples == [1.0, 2.5]
        assert back.stages == {'simulate': 100.0}
        assert back.resources.rss_peak_mb == 368.0

    def test_missing_keys_take_defaults(self, make_result):
        payload = make_result().to_dict()
        minimal = {k: v for k, v in payload.items()
                   if k in ('run_id', 'timestamp', 'path', 'is_user_path', 'fingerprint', 'plan')}
        back = RunResult.from_dict(minimal)
        assert back.repeats is None
        assert back.wall_samples == []
        assert back.stages == {}
        assert back.functions is None
        assert back.not_comparable is False

    def test_unknown_key_rejected(self, make_result):
        """版本不一致时必须早失败——此时任何比值都在比不可比的东西。"""
        with pytest.raises(ValueError, match='未知键'):
            RunResult.from_dict({**make_result().to_dict(), 'nope': 1})

    def test_nested_unknown_key_rejected(self, make_result):
        payload = make_result().to_dict()
        with pytest.raises(ValueError, match='未知键'):
            RunResult.from_dict({**payload, 'resources': {**payload['resources'], 'zzz': 1}})

    @pytest.mark.parametrize('field,value', [
        ('repeats', '3'),
        ('repeats', True),
        ('repeats', 3.5),
        ('wall_median', 'x'),
        ('return_compact', 1),
    ])
    def test_type_mismatch_rejected(self, make_result, field, value):
        with pytest.raises(ValueError):
            RunResult.from_dict({**make_result().to_dict(), field: value})

    def test_none_on_non_optional_rejected(self, make_result):
        with pytest.raises(ValueError, match='不接受 None'):
            RunResult.from_dict({**make_result().to_dict(), 'path': None})

    def test_non_object_rejected(self):
        with pytest.raises(ValueError, match='必须是对象'):
            RunResult.from_dict([1, 2])


class TestFingerprint:
    def test_capture_reads_real_environment(self):
        fp = EnvFingerprint.capture(qt_qpa_platform='offscreen')
        assert fp.python and fp.os and fp.cores > 0
        assert fp.code_version, '代码版本不得为空（取自 gacha_simulator/_version.py）'
        assert fp.qt_qpa_platform == 'offscreen'

    def test_capture_is_stable(self):
        """同一环境两次捕获的关键字段一致——否则基线无法按机器类别分组。"""
        a, b = EnvFingerprint.capture('offscreen'), EnvFingerprint.capture('offscreen')
        assert a.machine_class == b.machine_class
        assert (a.python, a.cores, a.os) == (b.python, b.cores, b.os)

    @pytest.mark.parametrize('cores,band', [(2, '1-4'), (4, '1-4'), (8, '5-8'),
                                            (16, '9-16'), (22, '17+')])
    def test_machine_class_buckets(self, cores, band):
        fp = EnvFingerprint(cores=cores, os='Windows 11')
        assert fp.machine_class == f'{band}cores_Windows 11'

    def test_qt_qpa_platform_is_recorded(self, fingerprint):
        """§3.11 要求记录本次 QT_QPA_PLATFORM 取值——它是可比性维度。"""
        assert fingerprint.qt_qpa_platform == 'offscreen'
        assert EnvFingerprint(cpu='x', cores=1, os='y', python='3.12',
                              code_version='1').qt_qpa_platform is None
