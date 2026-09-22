"""T5（`py-spy` 层）：解析测试与软降级断言。

§3.9 T5 的边界：**`py-spy` 是外部工具，其采样质量不属本平台**。本文件只测两件事：

1. 录制的 speedscope fixture 能否被正确解析为 `SamplesMeta` 与热点列表
2. `4a` 的「`py-spy` 不存在」软降级：注入不存在的可执行路径后，`record` / `dump`
   的封装返回降级结果并记 `warnings`，**不抛异常、不使测量失败**

**不在测试里真的 attach 进程**：attach 需要真实长跑进程，会造成 flaky 与内存风险
（违反 §3.4 规则 4）。扣掉这一点，本文件可进默认 `pytest -q`、不受 `P83_PERF_TESTS` 门控。

fixture 的来源：`py-spy record --format speedscope --rate 200 -- python <工作负载>`
——录制**新起的**进程，不是 attach 已有进程。
"""

import json
import subprocess
from pathlib import Path

import pytest

from benchmarks.perf.record import SamplesMeta
from benchmarks.perf.profilers.pyspy import (
    DEFAULT_RATE_HZ,
    Hotspot,
    PySpyResult,
    SpeedscopeSummary,
    dump,
    parse_speedscope,
    record,
    resolve_binary,
    self_test,
)

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'speedscope_pyspy_0.4.2.json'
#: 录制时的采样时长（秒）——fixture 的 endValue，容忍 py-spy 的收口偏差。
FIXTURE_DURATION = 2.72
MISSING = 'this-binary-does-not-exist-p83'


@pytest.fixture(scope='module')
def summary():
    return parse_speedscope(FIXTURE)


class TestRealFixtureParsing:
    def test_meta(self, summary):
        assert summary.meta.profiles == 1
        assert summary.meta.samples and summary.meta.samples > 100
        assert summary.meta.duration == pytest.approx(FIXTURE_DURATION, abs=0.2)
        assert summary.meta.errors == []

    def test_no_parse_errors(self, summary):
        """解析真实 fixture 不该产生任何告警——有的话说明解析器对合法输入也在猜。"""
        assert summary.meta.errors == []

    def test_hotspots_sorted_by_self_time(self, summary):
        times = [h.self_time for h in summary.hotspots]
        assert times == sorted(times, reverse=True)

    def test_hotspots_aggregated_by_function_name(self, summary):
        """py-spy 为同一函数的每个行号各建一帧——按帧索引统计会把函数拆成多条。"""
        names = [h.name for h in summary.hotspots]
        assert len(names) == len(set(names)), f'同名函数被拆开：{names}'

    def test_top_hotspot_is_the_workload(self, summary):
        """fixture 的工作负载把时间全花在 inner_loop 上，热点第一必须是它。"""
        assert summary.hotspots[0].name == 'inner_loop'
        assert summary.hotspots[0].self_share > 0.5

    def test_top_hotspot_has_a_location(self, summary):
        top = summary.hotspots[0]
        assert top.file.endswith('workload.py')
        assert isinstance(top.line, int)

    def test_self_time_never_exceeds_total(self, summary):
        for hotspot in summary.hotspots:
            assert hotspot.self_time <= hotspot.total_time + 1e-9

    def test_shares_are_a_fraction(self, summary):
        assert 0 < sum(h.self_share for h in summary.hotspots) <= 1.0 + 1e-9

    def test_top_helper(self, summary):
        assert len(summary.top(1)) == 1

    def test_accepts_dict_and_text(self):
        payload = json.loads(FIXTURE.read_text(encoding='utf-8'))
        assert parse_speedscope(payload).meta.samples == parse_speedscope(FIXTURE).meta.samples
        assert parse_speedscope(json.dumps(payload)).meta.samples is not None


class TestDegradation:
    """解析失败一律软降级——一份读不了的剖面不该让整个排查中断。"""

    def test_missing_path_reports_a_file_cause(self):
        result = parse_speedscope('no-such-file-p83.json')
        assert result.meta.samples is None and result.meta.profiles == 0
        assert '读不到或解析不了' in result.meta.errors[0]

    def test_invalid_json_text_reports_a_text_cause(self):
        """路径与 JSON 文本的成因不得互换——否则读的人会去查不存在的东西。"""
        result = parse_speedscope('{"a": ')
        assert 'JSON' in result.meta.errors[0]
        assert '读不到' not in result.meta.errors[0]

    def test_non_object_top_level(self):
        result = parse_speedscope([1, 2])
        assert result.meta.profiles == 0 and '顶层必须是对象' in result.meta.errors[0]

    def test_no_sampled_profile(self):
        result = parse_speedscope({'shared': {'frames': []}, 'profiles': [{'type': 'evented'}]})
        assert result.meta.profiles == 0
        assert any("非 'sampled'" in e for e in result.meta.errors)

    def test_length_mismatch_is_aligned_not_fatal(self):
        result = parse_speedscope({
            'shared': {'frames': [{'name': 'f'}]},
            'profiles': [{'type': 'sampled', 'endValue': 1.0,
                          'samples': [[0], [0]], 'weights': [0.5]}],
        })
        assert result.meta.samples == 1
        assert any('长度不一致' in e for e in result.meta.errors)

    def test_missing_weights_falls_back_to_equal_weight(self):
        result = parse_speedscope({
            'shared': {'frames': [{'name': 'f'}]},
            'profiles': [{'type': 'sampled', 'endValue': 4.0, 'samples': [[0], [0], [0]]}],
        })
        assert result.meta.samples == 3
        assert result.hotspots[0].self_time == pytest.approx(3.0)
        assert any('无 weights' in e for e in result.meta.errors)

    def test_bad_frames_and_profiles_types(self):
        result = parse_speedscope({'shared': {'frames': 1}, 'profiles': {}})
        assert '必须是数组' in result.meta.errors[0]

    def test_nothing_raises(self):
        for payload in ('', 'x', [], {}, {'profiles': None}, {'shared': None, 'profiles': []}):
            parse_speedscope(payload)  # 不抛即通过


class TestMissingBinaryDegrades:
    """`4a` 的「`py-spy` 不存在时软降级」（§3.9 T5 明写随 `4c` 交付）。"""

    def test_resolve_returns_none(self):
        assert resolve_binary(MISSING) is None

    def test_record_degrades(self):
        result = record(1234, duration=1.0, binary=MISSING)
        assert result.available is False and result.ok is False and bool(result) is False
        assert result.warnings and '未找到' in result.warnings[0]

    def test_dump_degrades(self):
        result = dump(1234, binary=MISSING)
        assert result.available is False and '未找到' in result.warnings[0]

    def test_self_test_degrades(self):
        assert self_test(binary=MISSING).available is False

    def test_monkeypatched_which_also_degrades(self, monkeypatch):
        """另一种注入方式（§3.9 T5 给的备选）：把 `which` 打断。"""
        monkeypatch.setattr('benchmarks.perf.profilers.pyspy.shutil.which', lambda name: None)
        result = record(1234, duration=1.0)
        assert result.available is False and not result.warnings == []

    def test_never_raises(self):
        for call in (lambda: record(1, duration=0.1, binary=MISSING),
                     lambda: dump(1, binary=MISSING),
                     lambda: self_test(binary=MISSING)):
            call()  # 不抛即通过


class TestCommandAssembly:
    """argv 组装——不真的执行 `py-spy`。"""

    @pytest.fixture
    def captured(self, monkeypatch):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, stdout='', stderr='')

        monkeypatch.setattr('benchmarks.perf.profilers.pyspy.subprocess.run', fake_run)
        monkeypatch.setattr('benchmarks.perf.profilers.pyspy.resolve_binary',
                            lambda explicit=None: 'py-spy')
        return calls

    def test_record_flags(self, captured):
        record(4321, duration=8.0, output='out.json', rate=200)
        argv = captured[-1]
        assert argv[0] == 'py-spy' and argv[1] == 'record'
        assert argv[argv.index('--pid') + 1] == '4321'
        assert argv[argv.index('--format') + 1] == 'speedscope'
        assert argv[argv.index('--output') + 1] == 'out.json'
        assert argv[argv.index('--rate') + 1] == '200'
        assert argv[argv.index('--duration') + 1] == '8.0'

    def test_record_covers_subprocesses_by_default(self, captured):
        """不覆盖子进程就只能采到父进程主线程的空等（实测父进程空等在 pool.py:861）。"""
        record(1, duration=1.0)
        assert '--subprocesses' in captured[-1]

    def test_record_can_disable_subprocesses(self, captured):
        record(1, duration=1.0, subprocesses=False)
        assert '--subprocesses' not in captured[-1]

    def test_default_rate_not_forced(self, captured):
        """不传 `rate` 就不加 `--rate`——把默认值交给 py-spy 自己，避免两处默认漂移。"""
        record(1, duration=1.0)
        assert '--rate' not in captured[-1]
        assert DEFAULT_RATE_HZ == 100

    def test_dump_flags(self, captured):
        dump(99)
        argv = captured[-1]
        assert argv[1] == 'dump' and argv[argv.index('--pid') + 1] == '99'

    def test_nonzero_exit_is_recorded_not_raised(self, monkeypatch):
        monkeypatch.setattr('benchmarks.perf.profilers.pyspy.resolve_binary',
                            lambda explicit=None: 'py-spy')

        def failing(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 3, stdout='', stderr='boom')

        monkeypatch.setattr('benchmarks.perf.profilers.pyspy.subprocess.run', failing)
        result = record(1, duration=1.0)
        assert result.available is True and result.ok is False
        assert any('退出码 3' in w for w in result.warnings)

    def test_timeout_is_soft(self, monkeypatch):
        monkeypatch.setattr('benchmarks.perf.profilers.pyspy.resolve_binary',
                            lambda explicit=None: 'py-spy')

        def timing_out(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 1)

        monkeypatch.setattr('benchmarks.perf.profilers.pyspy.subprocess.run', timing_out)
        result = record(1, duration=1.0)
        assert result.ok is False and any('超时' in w for w in result.warnings)


class TestPublicSurface:
    def test_types_are_exported(self):
        assert Hotspot(name='f', self_time=1.0, total_time=1.0, self_share=1.0,
                       samples=1).name == 'f'
        assert PySpyResult(available=True, ok=True)
        assert SpeedscopeSummary(meta=SamplesMeta(), profile_count=0, frame_count=0)
