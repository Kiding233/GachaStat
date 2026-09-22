"""`3f-1`：启动时间线（§3.11 的八段）的解析、拼装与受门控的真实测量。

**分两层**：

- **不跑真实启动的部分**（解析 `-X importtime`、拼段、回传契约、子进程环境）——
  纯函数与注入形态，进默认 `pytest -q`。这几件事最容易写错（时钟同源、量纲、
  缺段与 0 的区分），**不该跟着真实测量一起被门控掉**。
- **真实冷启动**（`TestRealStartupMeasurement`）——要起一条真实 `windows` 平台的
  子进程、弹一次窗口、约 10s ×2（预热 + 测量），故受 `P83_PERF_TESTS` 门控、**由
  人工触发**（§3.9 T6：`subject='startup'` 的冷启动测量不进 H9 的 `pytest -q`）。
"""

import json
import os

import pytest

from benchmarks.perf.adapters.gui_qt import (
    STARTUP_JSON_ENV,
    STARTUP_PLATFORM,
    WARN_STARTUP_NOT_A_PARTITION,
    GuiQtAdapter,
    _as_float,
    _positive,
    _read_startup_json,
    parse_importtime,
)
from benchmarks.perf.profilers.stage import (
    STAGES,
    STARTUP_STAGE_LABELS,
    STARTUP_STAGES,
    WARN_STAGE_ABSENT,
    WARN_STAGE_MISSING,
    normalize_stages,
    stage_label,
)
from benchmarks.perf.adapters.base import Adapter, SingleRun
from tests.benchmarks.conftest import requires_real_run

#: 一条 `-X importtime` 的真实输出片段（取自本机 `import gacha_simulator.gui`）。
_IMPORTTIME_SAMPLE = """\
import time:      4585 |      26182 |   PyQt6
import time:       893 |        961 |   PyQt6.sip
import time:      3718 |       3718 |   PyQt6.QtCore
import time:     22628 |      28823 | PyQt6.QtWebEngineWidgets
import time:      1084 |     430248 | gacha_simulator.gui.main_window
some unrelated stderr noise
"""


class TestStartupVocabulary:
    """启动八段与模拟六段是**两张不可互认的表**（§3.11 与 §3.3 不是同一组分段）。"""

    def test_eight_segments_in_timeline_order(self):
        assert STARTUP_STAGES == (
            'interpreter_start', 'qt_import', 'app_construct', 'main_import',
            'window_construct', 'window_visible', 'work_complete', 'charts_ready',
        )

    def test_disjoint_from_simulation_vocabulary(self):
        assert not set(STARTUP_STAGES) & set(STAGES)

    def test_every_segment_has_a_label(self):
        for stage in STARTUP_STAGES:
            assert STARTUP_STAGE_LABELS.get(stage), stage

    def test_stage_label_resolves_both_tables(self):
        assert stage_label('charts_ready') == '图表可用'
        assert stage_label('simulate') == '模拟'
        assert stage_label('unknown_segment') == 'unknown_segment'

    def test_simulation_key_is_rejected_under_startup_vocabulary(self):
        """`simulate` 落进启动表必是键名写错——报错而非静默丢弃。"""
        with pytest.raises(ValueError, match='未知段名'):
            normalize_stages({'simulate': 1.0}, vocabulary=STARTUP_STAGES)

    def test_startup_key_is_rejected_under_simulation_vocabulary(self):
        with pytest.raises(ValueError, match='未知段名'):
            normalize_stages({'charts_ready': 1.0})

    def test_absent_and_missing_have_different_words(self):
        """两种缺失成因不得共用一句话——读的人据此决定该不该排查。"""
        _, missing = normalize_stages({'qt_import': 1.0}, vocabulary=STARTUP_STAGES)
        _, absent = normalize_stages(
            {'qt_import': 1.0}, vocabulary=STARTUP_STAGES,
            absent_by_design=('charts_ready',),
        )
        assert any('未采集' in w for w in missing)
        assert any('不产出' in w for w in absent)

        charts_missing = [w for w in missing if '图表可用' in w][0]
        charts_absent = [w for w in absent if '图表可用' in w][0]
        assert charts_missing != charts_absent
        assert charts_absent == WARN_STAGE_ABSENT.format(stage='charts_ready（图表可用）')
        assert charts_missing == WARN_STAGE_MISSING.format(stage='charts_ready（图表可用）')

    def test_no_collection_yields_one_warning_not_eight(self):
        stages, warnings = normalize_stages(None, vocabulary=STARTUP_STAGES)
        assert stages == {} and len(warnings) == 1


class TestParseImporttime:
    """第 2 / 4 段的取法：Qt 栈用**self 之和**、主模块用 **cumulative**。"""

    def test_qt_import_sums_self_times(self):
        # 4585 + 893 + 3718 + 22628 = 31824 µs
        assert parse_importtime(_IMPORTTIME_SAMPLE)['qt_import'] == pytest.approx(0.031824)

    def test_main_import_uses_cumulative(self):
        assert parse_importtime(_IMPORTTIME_SAMPLE)['main_import'] == pytest.approx(0.430248)

    def test_qt_self_sum_avoids_double_counting(self):
        """同一个模块只出现一行——若改成 cumulative 相加，`PyQt6.QtCore` 会被
        `PyQt6` 与 `PyQt6.QtWidgets` 两条各算一次（实测 QtWebEngine 那棵树如此）。"""
        text = ('import time:      100 |      500 |   PyQt6\n'
                'import time:      200 |      200 | PyQt6.QtWidgets\n')
        assert parse_importtime(text)['qt_import'] == pytest.approx(300 / 1e6)

    def test_absent_segment_is_omitted_not_zero(self):
        """0 是合法读数（快得不计），与「没测到」必须分开。"""
        parsed = parse_importtime('import time: 100 | 100 | numpy\n')
        assert 'qt_import' not in parsed and 'main_import' not in parsed

    def test_blank_and_garbage_yield_nothing(self):
        assert parse_importtime('') == {}
        assert parse_importtime('Traceback (most recent call last):\n  File "x"\n') == {}

    def test_leading_whitespace_is_tolerated(self):
        """importtime 的模块名带缩进（嵌套深度），不 strip 就一个都匹配不上。"""
        text = 'import time:      100 |      100 |     PyQt6.QtCore\n'
        assert parse_importtime(text)['qt_import'] == pytest.approx(100 / 1e6)


class TestHookContract:
    """`3f-2` 的回传 JSON：**契约在两侧各写一份字面量**（产品侧不得 import
    `benchmarks/`），故这里把消费侧的容忍面钉死。"""

    def test_missing_file_is_not_an_error(self, tmp_path):
        assert _read_startup_json(str(tmp_path / 'nope.json'), 1234) is None

    def test_half_written_json_is_not_an_error(self, tmp_path):
        """落盘纪律是「先写临时文件再替换」，但读到半截时**不得抛**——下次轮询会重读。"""
        path = tmp_path / 'timeline.json'
        path.write_text('{"origin": 1.0, "pid"', encoding='utf-8')
        assert _read_startup_json(str(path), 1234) is None

    def test_other_runs_leftovers_are_rejected(self, tmp_path):
        """按 pid 过滤：同一路径可能被上一条冷进程写过，不然会读到另一次 run 的读数。"""
        path = tmp_path / 'timeline.json'
        path.write_text(json.dumps({'pid': 999, 'origin': 1.0}), encoding='utf-8')
        assert _read_startup_json(str(path), 1234) is None
        assert _read_startup_json(str(path), 999) is not None

    def test_pid_absent_is_accepted(self, tmp_path):
        """回传里没有 pid 时不据此拒绝（契约里 pid 是可选的自证字段）。"""
        path = tmp_path / 'timeline.json'
        path.write_text(json.dumps({'origin': 1.0}), encoding='utf-8')
        assert _read_startup_json(str(path), 1234) == {'origin': 1.0}

    def test_non_object_payload_rejected(self, tmp_path):
        path = tmp_path / 'timeline.json'
        path.write_text('[1, 2]', encoding='utf-8')
        assert _read_startup_json(str(path), 1234) is None

    def test_empty_path_is_not_an_error(self):
        assert _read_startup_json('', 1234) is None


class TestSanityChecks:
    """`_positive` / `_as_float`：宁可判该段不可得，也不写进一个荒谬数字。"""

    def test_valid_value_passes_through(self):
        warnings = []
        assert _positive(1.5, warnings, 'qt_import') == 1.5
        assert warnings == []

    def test_non_positive_means_clocks_disagree(self):
        warnings = []
        assert _positive(-2.0, warnings, 'interpreter_start') is None
        assert warnings and '不同源' in warnings[0]

    def test_zero_is_rejected_too(self):
        """0 对「段耗时」不是合法值——它意味着两个时刻完全相同，多半是取值取错了。"""
        warnings = []
        assert _positive(0.0, warnings, 'qt_import') is None
        assert warnings

    def test_over_ceiling_is_rejected(self):
        warnings = []
        assert _positive(999.0, warnings, 'qt_import') is None
        assert warnings and '超时' in warnings[0]

    def test_as_float_rejects_bool_and_junk(self):
        assert _as_float(True) is None
        assert _as_float('abc') is None
        assert _as_float(None) is None
        assert _as_float('1.5') == 1.5


class TestSegmentAssembly:
    """把「父进程侧时刻」与「子进程回传标记」拼成八段耗时（§3.11）。"""

    SPAWN = 100.0
    ORIGIN = 100.3          # 段 1 = 0.3s

    def _observed(self, **overrides):
        observed = {
            'spawn_at': self.SPAWN,
            'stderr': _IMPORTTIME_SAMPLE,
            'window_visible': 2.3,       # 自 spawn 起 2.3s
            'work_complete': 8.0,
            # 子进程回传的绝对时钟值——`_observe_startup` 从钩子 JSON 抄进这里，
            # 因为「何时停」的判定在观察循环里、而拼段在另一个方法里。
            'charts_ready_abs': 108.5,
            'rss_peak_mb': 368.0,
            'wall': 8.4,
        }
        observed.update(overrides)
        return observed

    def _hook(self, **overrides):
        # 段 3 = 0.4s，段 5 = 0.9s；窗口构造结束于 1.5s 绝对时钟 → 段 6 = 2.3 - 1.5
        hook = {
            'pid': os.getpid(),
            'origin': self.ORIGIN,
            'app_construct_start': 100.6, 'app_construct_end': 101.0,
            'window_construct_start': 101.0, 'window_construct_end': 101.5,
            'charts_ready': 108.5,
        }
        hook.update(overrides)
        return hook

    def test_all_eight_segments_present(self):
        segments = GuiQtAdapter()._startup_segments(self._observed(), self._hook(), [])
        assert set(segments) == set(STARTUP_STAGES), segments

    def test_each_segment_is_a_positive_duration(self):
        segments = GuiQtAdapter()._startup_segments(self._observed(), self._hook(), [])
        assert all(value > 0 for value in segments.values()), segments

    def test_known_values(self):
        """逐段核数——拼错一段不会报错，只会让报告里的时间线整体错位。"""
        segments = GuiQtAdapter()._startup_segments(self._observed(), self._hook(), [])
        assert segments['interpreter_start'] == pytest.approx(0.3)
        assert segments['app_construct'] == pytest.approx(0.4)
        assert segments['window_construct'] == pytest.approx(0.5)
        assert segments['window_visible'] == pytest.approx(2.3 - 1.5)
        assert segments['work_complete'] == pytest.approx(8.0 - 2.3)
        assert segments['charts_ready'] == pytest.approx(108.5 - 108.0)
        assert segments['qt_import'] == pytest.approx(0.031824)
        assert segments['main_import'] == pytest.approx(0.430248)

    def test_the_eight_segments_are_not_a_partition(self):
        """第 2 / 4 段是 `-X importtime` 的独立测量，时间窗与第 1 / 3 / 5 段重叠——
        **八段之和不是总启动时间**。这条口径必须随记录带出：不写进报告的话，读的人
        会把八段相加当总时长，而那个数没有意义。"""
        warnings = []
        GuiQtAdapter()._startup_segments(self._observed(), self._hook(), warnings)
        assert WARN_STARTUP_NOT_A_PARTITION in warnings

    def test_without_hook_only_the_external_segments_remain(self):
        """钩子缺席：**不假装**进程内那几段采到了（§3.8 D7 同源）。"""
        # `charts_ready_abs` 只可能由钩子回传而来，无钩子时它必然缺席
        observed = self._observed(charts_ready_abs=None)
        segments = GuiQtAdapter()._startup_segments(observed, None, [])
        assert set(segments) == {'qt_import', 'main_import', 'work_complete'}

    def test_without_hook_the_absent_segments_are_declared(self):
        adapter = GuiQtAdapter()
        assert adapter._startup_absent(None) == (
            'interpreter_start', 'app_construct', 'window_construct',
            'window_visible', 'charts_ready',
        )
        assert adapter._startup_absent(self._hook()) == ()

    def test_clock_mismatch_degrades_instead_of_writing_garbage(self):
        """两进程时钟不同源时，段 1 会是负数——判该段不可得并记成因。"""
        warnings = []
        hook = self._hook(origin=99.0)          # 早于 spawn
        segments = GuiQtAdapter()._startup_segments(self._observed(), hook, warnings)
        assert 'interpreter_start' not in segments
        assert any('interpreter_start' in w for w in warnings)

    def test_charts_ready_before_work_complete_is_degraded(self):
        """第 7 段（整棵进程树 CPU 归零）实测可能**晚于**第 8 段——那时段 8 会算出
        非正值。此处只保证不写荒谬数字；该观测顺序问题记在 `04-问题.md`。"""
        warnings = []
        # 早于 work_complete 的绝对时刻（100 + 8.0 = 108.0）
        observed = self._observed(charts_ready_abs=107.0)
        segments = GuiQtAdapter()._startup_segments(observed, self._hook(), warnings)
        assert 'charts_ready' not in segments
        assert any('charts_ready' in w for w in warnings)


class TestChildEnvironment:
    """冷子进程的环境（§3.11 定死：**不从 `simulation` 的 offscreen 继承**）。"""

    def test_hook_path_is_exported(self):
        env = GuiQtAdapter._startup_child_env('C:/tmp/x.json')
        assert env[STARTUP_JSON_ENV] == 'C:/tmp/x.json'

    def test_platform_is_forced_not_inherited(self, monkeypatch):
        monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
        env = GuiQtAdapter._startup_child_env('C:/tmp/x.json')
        if STARTUP_PLATFORM is None:
            assert 'QT_QPA_PLATFORM' not in env
        else:
            assert env['QT_QPA_PLATFORM'] == STARTUP_PLATFORM
            assert env['QT_QPA_PLATFORM'] != 'offscreen'

    def test_other_environment_variables_are_preserved(self, monkeypatch):
        monkeypatch.setenv('P83_STARTUP_SENTINEL', 'kept')
        assert GuiQtAdapter._startup_child_env('x').get('P83_STARTUP_SENTINEL') == 'kept'

    def test_does_not_mutate_the_parent_environment(self, monkeypatch):
        monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
        GuiQtAdapter._startup_child_env('x')
        assert os.environ['QT_QPA_PLATFORM'] == 'offscreen'


@requires_real_run
class TestRealStartupMeasurement:
    """真实冷启动测量：起一条真实平台的子进程、弹一次窗口，约 10s ×2。

    **由人工触发**（§3.9 T6）：它要弹真实窗口，不进 H9 的 `pytest -q` 门控。
    运行方式：`P83_PERF_TESTS=1 pytest tests/benchmarks/test_startup_timeline.py -q`
    """

    @pytest.fixture
    def plan(self, make_plan):
        # `repeats=1`：预热 + 一次记录 = 两条冷进程（规则 10 不因 repeats 而省）
        return make_plan(subject='startup', path='gui-qt', grain='stage',
                         repeats=1, n=10, workers=1)

    def test_produces_a_real_timeline(self, plan):
        from benchmarks.perf.adapters.base import get_adapter

        result = get_adapter('gui-qt').run(plan)
        assert result.path == 'gui-qt' and result.is_user_path
        assert result.plan.subject == 'startup'
        assert result.wall_median > 0

        # 平台口径必须记下来（§3.11：启动跑真实平台，与 offscreen 的基线不可混比）
        assert result.fingerprint.qt_qpa_platform == STARTUP_PLATFORM

        # 外部观测的三段随适配器一并落地
        assert result.stages.get('work_complete', 0) > 0
        assert result.resources.rss_peak_mb is not None

        # 钩子段要么在，要么有一条点名成因的告警——**不得静默缺失**
        hook_segments = {'interpreter_start', 'app_construct', 'window_construct',
                         'window_visible', 'charts_ready'}
        if not hook_segments <= set(result.stages):
            assert any(STARTUP_JSON_ENV in w for w in result.warnings), result.warnings

    def test_startup_key_never_leaks_into_simulation_records(self, plan):
        assert plan.ignored_fields() != ()
        assert STARTUP_STAGES[0] not in STAGES

class _StubAdapter(Adapter):
    """替身：单次驱动返回一个给定的墙钟，不碰任何真实路径。"""

    name = 'stub'
    is_user_path = False

    def __init__(self, wall: float):
        self._wall = wall
        self.calls = 0

    def available(self) -> bool:
        return True

    def _run_once(self, plan):
        self.calls += 1
        return SingleRun(wall=self._wall)


class TestStartupIsExemptFromAutoDowngrade:
    """`subject='startup'` 不参与 §3.5 的自动降级（2026-09-22 定）。

    理由三条，缺一条都不足以豁免：**单次代价是固定成本**（冷进程 + 10 个 Chromium
    子进程，实测 8-10s，`repeats` 缩不了它）；**该启发式防的是「`n` 填大了」**
    而 `startup` 下 `n` / `workers` 本就**被忽略**；**一旦降级，`register_baseline`
    的 `repeats >= 3` 会拒绝入库**——启动测量将永远无法建立基线，而「启动有没有
    变慢」正是 G6 要回答的问题。本组测试守的正是最后这条后果。
    """

    def _plan(self, make_plan, subject, repeats):
        return make_plan(subject=subject,
                         path='gui-qt' if subject == 'startup' else 'cli',
                         repeats=repeats, n=10, workers=2)

    def test_startup_keeps_its_repeats(self, make_plan):
        adapter = _StubAdapter(wall=20.0)          # 20 x 3 = 60s，远超 30s 阈值
        result = adapter.run(self._plan(make_plan, 'startup', 3))
        assert adapter.calls == 3
        assert result.repeats == 3
        assert result.repeats_downgraded is False

    def test_simulation_still_downgrades(self, make_plan):
        """对照组：同一条启发式对 `simulation` 照常生效，豁免只限 `startup`。"""
        adapter = _StubAdapter(wall=20.0)
        result = adapter.run(self._plan(make_plan, 'simulation', 3))
        assert adapter.calls == 1
        assert result.repeats == 1 and result.repeats_downgraded is True

    def test_downgraded_record_cannot_be_a_baseline(self, make_plan, tmp_path):
        """豁免的**目的**：不加这条，启动测量永远建不了基线。"""
        from benchmarks.perf.report import BaselineGateError, register_baseline

        startup = _StubAdapter(wall=20.0).run(self._plan(make_plan, 'startup', 3))
        register_baseline('startup-baseline', startup, root=tmp_path)   # 不抛即通过

        simulation = _StubAdapter(wall=20.0).run(self._plan(make_plan, 'simulation', 3))
        with pytest.raises(BaselineGateError):
            register_baseline('sim-down', simulation, root=tmp_path)

