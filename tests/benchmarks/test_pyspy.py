"""T5（`py-spy` 层）：解析测试与软降级断言。

§3.9 T5 的边界：**`py-spy` 是外部工具，其采样质量不属本平台**。本文件只测两件事：

1. 录制的 speedscope fixture 能否被正确解析为 `SamplesMeta` 与热点列表
2. `4a` 的「`py-spy` 不存在」软降级：注入不存在的可执行路径后，`record` / `dump`
   的封装返回降级结果并记 `warnings`，**不抛异常、不使测量失败**

**默认门控内不在测试里真的 attach 进程**：attach 需要真实长跑进程，会造成 flaky 与内存风险
（违反 §3.4 规则 4）。故本文件的**默认**部分（解析与软降级）进 `pytest -q`；「真的 attach」
 那一条落在 `TestLiveAttach` 里、**受 `P83_PERF_TESTS` 门控**（2026-09-28 补——§七 要求
 「可 attach 到运行中的真实进程」有可重复证据，而手工记录不算）。

fixture 的来源：`py-spy record --format speedscope --rate 200 -- python <工作负载>`
——录制**新起的**进程，不是 attach 已有进程。
"""

import json
import subprocess
from pathlib import Path

import pytest

from benchmarks.perf.record import SamplesMeta
from tests.benchmarks.conftest import requires_real_run
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
        assert argv[argv.index('--duration') + 1] == '8'

    def test_duration_is_sent_as_an_integer(self, captured):
        """`--duration` **必须取整**——`py-spy` 用 `ParseIntError` 解析它。

        传 `8.0` 会让 py-spy **panic 退出（码 101）**，即 `record()` 对任何非整数时长
        从来不工作。**本文件原来那条断言写的是 `== '8.0'`**，把缺陷当成正确行为钉住了，
        所以 T5 全绿、缺陷活着——而「不真的 attach」是 T5 的明确设计，只有手工实测
        能发现它（2026-09-28 attach 时撞到）。
        """
        record(1, duration=8.0)
        assert captured[-1][captured[-1].index('--duration') + 1] == '8'
        record(1, duration=7.4)
        assert captured[-1][captured[-1].index('--duration') + 1] == '7'

    def test_duration_rounding_is_announced(self, captured):
        """取整改变了读数口径（采样时长），不该静默发生。"""
        assert record(1, duration=8.0).warnings == []
        assert any('只接受整数秒' in w for w in record(1, duration=7.4).warnings)

    def test_sub_second_duration_floors_at_one(self, captured):
        """`--duration 0` 在 py-spy 里意为「一直采」，故下限取 1 秒。"""
        record(1, duration=0.2)
        assert captured[-1][captured[-1].index('--duration') + 1] == '1'

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


@requires_real_run
class TestLiveAttach:
    """G4 的**可重复**证据（2026-09-28 补——独立审查指出此前仓内只有一次性手工记录）。

    §七 要求「`py-spy` 采集可 attach 到运行中的真实进程并覆盖子进程」，而本文件开头
    明写「**不在测试里真的 attach**」。两者不矛盾但需要分清：T5 管的是**默认门控**——
    attach 要真实长跑进程，会造成 flaky 与内存风险，不能进 `pytest -q`；本类受
    `P83_PERF_TESTS` 门控、由人工触发，正好落在 T5 划出的那条线之外。

    判「覆盖子进程」的依据：`cli` 路径的父进程此刻阻塞在 `imap_unordered` 上，真正
    干活的是 **worker 子进程**，故样本里出现**只在 worker 侧执行**的函数名即证明覆盖
    到了。只看「有没有采到样本」不够——那只能证明 attach 成功。
    """

    pytestmark = pytest.mark.timeout(180)

    def test_attach_covers_worker_subprocesses(self, tmp_path):
        """**本用例直接起 cli 子进程，绕过 `Plan.validate()`**，故规则 5 的内存门禁在这里
        不生效（n=600 时父进程保留约 600 × 1996 KB ≈ 1.2 GB）。受 `P83_PERF_TESTS` 门控、
        由人工触发，故不构成默认路径上的风险；但若将来把它挪进默认套件，须先过一遍 `Plan`
        的校验口径。
        """
        import os
        import sys
        import time

        from benchmarks.perf.profilers.pyspy import parse_speedscope, record, resolve_binary

        if resolve_binary() is None:
            pytest.skip('本环境没有 py-spy 可执行文件')

        target = tmp_path / 'attach.speedscope.json'
        root = Path(__file__).resolve().parents[2]
        # **stderr 落文件，不要接 PIPE 而无人读**：日志一多就会把子进程堵死在 write 上
        # （64KB 管道），表现为「采样期间子进程莫名不动」——同一个坑在 `gui_qt.py` 的启动
        # 测量里踩过一次（见 `benchmarks/README.md` 的启动测量纪律），别在这里复现。
        stderr_path = tmp_path / 'child_stderr.txt'
        with open(stderr_path, 'w', encoding='utf-8', errors='replace') as err:
            proc = subprocess.Popen(
                [sys.executable, '-m', 'gacha_simulator.cli', '-n', '600', '-w', '2',
                 '-s', '42', '--no-progress', '-o', str(tmp_path / 'out.json')],
                cwd=str(root), stdout=subprocess.DEVNULL, stderr=err,
            )
        try:
            time.sleep(3.0)          # 等进程池起起来、进入模拟循环
            result = record(proc.pid, duration=6, output=str(target), subprocesses=True,
                            rate=200)
            assert result, f'采样失败：ok={result.ok} warnings={result.warnings}'
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:      # pragma: no cover
                proc.kill()
        assert os.path.isfile(target), '未产出 speedscope 文件'

        summary = parse_speedscope(str(target))
        assert not summary.meta.errors, summary.meta.errors
        names = [hot.name for hot in summary.hotspots]

        # **判据必须是能区分的那一条。** 独立审查做过对照实验：把 `--subprocesses` 关掉，
        # `profile_count` 仍是 2-3——**speedscope 按「进程 × 线程」出份数**，只采父进程也有
        # 好几份（`Thread-1 (_handle_workers)` 等）。故「份数 >= 2」在「完全没覆盖子进程」
        # 时**照样通过**，与我刚在 `gui_qt` 里修掉的 `dispatch > 0` 是同一类无鉴别力断言。
        # 真判据是：**剖面名里出现别的 pid**，以及下面的 worker 侧帧。
        import json as _json

        with open(target, encoding='utf-8') as handle:
            payload = _json.load(handle)
        profile_names = [item.get('name', '') for item in payload.get('profiles', [])]
        # **判据的形态是实测定的，不是推的**：`py-spy` 只在采**多个进程**时才给剖面名加
        # `Process <pid> ` 前缀；关掉 `--subprocesses` 时名字是裸的 `Thread <tid> "..."`。
        # 故「名字里不含被测 pid」这种写法会把「无前缀」误判成「别的进程」而照样通过
        # （我第一版就是这么写的，反向对照实测抓到）。**要判「覆盖了子进程」，必须要求
        # 前缀存在且 pid 不同**。
        foreign = [name for name in profile_names
                   if name.startswith('Process ') and f'Process {proc.pid} ' not in name]
        assert foreign, (
            '没有采到任何**别的进程**的剖面——attach 成功但未覆盖子进程。'
            '注意：`py-spy` 只在采多进程时才加 `Process <pid> ` 前缀，故空列表也可能是'
            f'「根本没开 --subprocesses」。全部剖面名：{profile_names}'
        )
        worker_frames = [name for name in names
                         if '_run_single' in name or 'run_simulation_compact' in name]
        assert worker_frames, (
            'attach 成功但**未覆盖子进程**：样本里没有任何只在 worker 侧执行的函数。'
            f'前十个热点：{names[:10]}'
        )
