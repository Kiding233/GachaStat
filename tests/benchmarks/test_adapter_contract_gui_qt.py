"""T3（`gui-qt` 部分）：适配器契约测试。

对应 §3.9 T3 与 `3c`：`name` 互不重复 / `is_user_path` 符合约定 / 返回 `RunResult` 且
`path` 与 `name` 一致 / `available()` 与实际可运行性一致 / **`Plan.collector` 申报值
与驱动代码相符** / **用例内断言 `QT_QPA_PLATFORM=offscreen` 已生效** / **非空 argv
（规则 6）** / 收尾走 `_restarting` 不弹确认框。

三层分界：

- **不起 Qt 的部分**（契约属性、申报值的源码级核对、缺依赖时的跳过）默认就跑
- **起 Qt 但不起 Chromium 的部分**（`qt_argv`、offscreen 平台生效、收尾不弹框）与
  PyQt6 绑定，缺依赖时 `skipif` 跳过
- **真实驱动 `MainWindow` 跑一次模拟的部分**（含 Chromium 子进程）由
  `P83_PERF_TESTS` 门控（§3.9：否则会把 H9 的 120s push 门控变成随机红灯）

§3.9 T3 还要求「记录字段缺失的降级断言」（`repeats` / `return_compact` /
`qt_qpa_platform` 为 `None` 时按不可比处理且不抛 `TypeError`）——那组断言测的是
**比对侧**（`1f` 的 `compare`），已在 `test_report.py` 内逐条覆盖，本文件不重复。
"""

import os
import re
import sys
from pathlib import Path

import pytest

from benchmarks.perf import __main__ as entry
from benchmarks.perf.adapters.base import get_adapter, load_adapters
from benchmarks.perf.adapters.gui_qt import (
    GuiQtAdapter,
    pyqt_available,
    qt_argv,
)
from benchmarks.perf.plan import Plan
from gacha_simulator.paths import get_config_dir
from tests.benchmarks.conftest import requires_real_run

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = os.path.join(get_config_dir(), 'config.toml')
#: T3 的规模参数（§3.9）——秒级。
T3_PARAMS = dict(n=10, workers=2, seed=42, repeats=1, grain='batch', collector=False)

_PYQT_AVAILABLE = pyqt_available()
requires_pyqt = pytest.mark.skipif(
    not _PYQT_AVAILABLE,
    reason='本环境无 PyQt6——该路径的契约由 available() 报「不可用」，不是错误（§二 G2）',
)


def _call_arguments(source: str, callee: str) -> str:
    """取出 `callee(...)` 的实参文本（按括号配平）。"""
    match = re.search(re.escape(callee) + r'\s*\(', source)
    if match is None:
        raise AssertionError(f'源码中找不到 {callee}( 的调用')
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        if source[index] == '(':
            depth += 1
        elif source[index] == ')':
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f'{callee}( 的括号未配平')


class TestContractSurface:
    """契约属性——不需要 Qt（`get_adapter` 只做类注册表查询）。"""

    def test_name(self):
        assert get_adapter('gui-qt').name == 'gui-qt'

    def test_is_user_path(self):
        assert get_adapter('gui-qt').is_user_path is True

    def test_registered_in_registry(self):
        assert 'gui-qt' in load_adapters()

    def test_declares_absent_stages(self):
        """产品侧没有回传通道，这四段在 GUI 进程内发生但不外流——属事实而非缺口。"""
        assert set(get_adapter('gui-qt').absent_stages) == {
            'config_load', 'env_build', 'pool_start', 'extract',
        }

    def test_timeout_is_finite(self):
        assert 0 < get_adapter('gui-qt').timeout_seconds < float('inf')

    def test_names_are_unique_across_adapters(self):
        """四适配器共用断言的「`name` 互不重复」——按注册表本身断言。"""
        registry = load_adapters()
        assert len(registry) == len(set(registry))


class TestCollectorDeclarationMatchesDriver:
    """§3.9 T3 的专条：声明的 `collector` 必须与驱动代码相符。

    `gui-qt` 的驱动是产品侧的 `gacha_panel.py`——它调 `run_batch_parallel` 时不传
    `on_result`，故适配器的申报值必须是 `False`（填错不会让路径真的带上收集器，
    只会让报告说谎，见 README §一 的 `Plan.collector` 一条）。
    """

    def test_adapter_declares_false(self):
        assert get_adapter('gui-qt').collector is False

    def test_driver_does_not_pass_on_result(self):
        source = (REPO_ROOT / 'gacha_simulator' / 'gui' / 'gacha_panel.py').read_text(
            encoding='utf-8')
        arguments = _call_arguments(source, 'run_batch_parallel')
        assert 'on_result' not in arguments, (
            '抽卡面板的驱动未传 on_result，故适配器的 collector 申报值必须是 False；'
            '若这里改传了，须同步改为 True'
        )


class TestUnavailablePathIsSkippedNotFatal:
    """缺 PyQt6 时 `available()` 静默返回 False，平台跳过而非报错（§二 G2）。"""

    def test_available_is_false_when_pyqt_missing(self, monkeypatch):
        import benchmarks.perf.adapters.gui_qt as module

        monkeypatch.setattr(module, 'pyqt_available', lambda: False)
        assert module.GuiQtAdapter().available() is False

    def test_entry_reports_skip_and_returns_three(self, tmp_path, monkeypatch, capsys):
        import json as _json

        class Dead:
            name = 'gui-qt'

            def available(self):
                return False

        monkeypatch.setattr(entry, 'get_adapter', lambda path: Dead())
        plan_file = tmp_path / 'plan.json'
        plan_file.write_text(_json.dumps(
            {'config_path': 'c.toml', 'strategy_key': 'smart', 'strategy_params': {},
             'n': 10, 'workers': 1, 'seed': 1, 'path': 'gui-qt'}), encoding='utf-8')
        assert entry.main(['run', '--plan', str(plan_file)]) == entry.EXIT_UNAVAILABLE
        assert '不可用' in capsys.readouterr().err

    def test_run_raises_unavailable_rather_than_running(self, monkeypatch):
        """`available()` 为假时 `run()` 必须拒绝执行，不得硬跑。"""
        from benchmarks.perf.adapters.base import AdapterUnavailable

        adapter = GuiQtAdapter()
        monkeypatch.setattr(adapter, 'available', lambda: False)
        with pytest.raises(AdapterUnavailable):
            adapter.run(Plan(config_path=DEFAULT_CONFIG, strategy_key='smart',
                             strategy_params={}, **T3_PARAMS))


@requires_pyqt
class TestRule6NonEmptyArgv:
    """规则 6：`QApplication` 的 argv **必须非空**，且平台须在构造前设定。

    这正是 2026-09-17 之前八次探针全部失败的原因（空 argv → QtWebEngine 初始化失败
    → 进程以 `0xC0000409` 终止），故它值得一条常驻断言而不是一次性的排查记录。
    """

    def test_argv_never_empty_when_sys_argv_is(self, monkeypatch):
        monkeypatch.setattr(sys, 'argv', [])
        assert qt_argv(), 'sys.argv 为空时必须补占位，不得把空列表交给 QApplication'

    def test_argv_preserved_when_present(self, monkeypatch):
        monkeypatch.setattr(sys, 'argv', ['prog', '--flag'])
        assert qt_argv() == ['prog', '--flag']

    def test_argv_is_a_copy(self, monkeypatch):
        """交出去的是副本——Qt 会改它，不得因此改写调用方的 `sys.argv`。"""
        monkeypatch.setattr(sys, 'argv', ['prog'])
        argv = qt_argv()
        argv.append('mutated')
        assert sys.argv == ['prog']

    def test_make_application_survives_empty_sys_argv(self, monkeypatch, qapp):
        monkeypatch.setattr(sys, 'argv', [])
        app = GuiQtAdapter._make_application()
        assert app is not None and app.arguments()


@pytest.fixture(scope='module')
def qapp():
    """本模块共用一个 `QApplication`——Qt 全进程只允许一个实例。"""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(qt_argv())
    yield app


@requires_pyqt
class TestOffscreenPlatformTakesEffect:
    """`QT_QPA_PLATFORM=offscreen` **已生效**（§3.9 T3 的 gui-qt 专条）。

    **Qt 只在 `QApplication` 构造那一刻读这个变量**，此后再设无效。故「已生效」不能
    靠在已有 app 的进程里改环境变量再问 `platformName()`——那个断言恒为假（实测：
    pytest 进程里先构造过 app 之后，`QGuiApplication.platformName()` 报 `windows`，
    与 `os.environ` 的值无关）。

    因此分三层断言，各自守一个具体的失效方式：

    1. **顺序**（源码级）：`_run_once` 必须在构造 `QApplication` **之前**设平台。
       这是最实际的回归——把两行的次序颠倒，平台就白设了，而任何行为级断言都会
       因为「进程里已经有 app」而看不见它
    2. **取值**：`simulation` 设为 `offscreen`；`startup` **不动本进程**（它的平台
       由父进程交给冷子进程，见 §3.11）
    3. **真生效**（子进程）：在一条**全新**进程里设 `offscreen` 再构造 app，
       断言 `QGuiApplication.platformName()` 报 `offscreen`。受 `P83_PERF_TESTS`
       门控（§3.9 把 gui-qt 的 T3 部分整体划入需真实子进程的一档）
    """

    def test_platform_is_set_before_application_construction(self):
        """源码级顺序断言——它守的正是「把两行颠倒」这个失效方式。"""
        source = (REPO_ROOT / 'benchmarks' / 'perf' / 'adapters' / 'gui_qt.py').read_text(
            encoding='utf-8')
        run_once = source[source.index('def _run_once'):]
        run_once = run_once[:run_once.index('def _prepare_environment')]
        assert run_once.index('self._prepare_environment(plan)') < run_once.index(
            'self._make_application()'), (
            '`_prepare_environment` 必须在 `_make_application` 之前调用——Qt 只在 '
            'QApplication 构造那一刻读 QT_QPA_PLATFORM'
        )

    def test_simulation_sets_offscreen(self, make_plan):
        GuiQtAdapter._prepare_environment(make_plan(path='gui-qt', subject='simulation'))
        assert os.environ['QT_QPA_PLATFORM'] == 'offscreen'

    def test_startup_does_not_touch_this_processs_platform(self, make_plan):
        """`subject='startup'` 的平台由父进程交给冷子进程，**不设在本进程上**。

        本进程可能刚跑过 `simulation`，顺手改环境变量会让「父进程此刻的平台」与
        「被测进程的平台」两件事混成一件（§3.11）。
        """
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        GuiQtAdapter._prepare_environment(make_plan(subject='startup', path='gui-qt'))
        assert os.environ['QT_QPA_PLATFORM'] == 'offscreen'


@requires_pyqt
@requires_real_run
class TestPlatformReallyTakesEffect:
    """在**全新进程**里验证 `offscreen` 真的换掉了平台插件。

    必须新起进程：本 pytest 进程里 app 早已构造，`platformName()` 不反映后来设的
    环境变量（原因见上一个类的 docstring）。
    """

    #: 在全新进程里跑的最小脚本。**用行列表拼**而非内嵌换行转义——后者在多层
    #: 转义里极易被折成真换行（写这段时就踩过一次）。
    _SCRIPT_LINES = [
        'import os, sys',
        'os.environ["QT_QPA_PLATFORM"] = "offscreen"',
        'from PyQt6.QtGui import QGuiApplication',
        'from PyQt6.QtWidgets import QApplication',
        'from benchmarks.perf.adapters.gui_qt import qt_argv',
        'app = QApplication(qt_argv())',
        'print(QGuiApplication.platformName())',
    ]

    def test_platform_name_in_a_fresh_process(self):
        import subprocess

        proc = subprocess.run([sys.executable, '-c', '\n'.join(self._SCRIPT_LINES)],
                              cwd=str(REPO_ROOT), capture_output=True,
                              text=True, encoding='utf-8', timeout=120)
        assert proc.returncode == 0, proc.stderr[-800:]
        assert proc.stdout.strip().splitlines()[-1] == 'offscreen', proc.stdout


@requires_pyqt
@requires_real_run
class TestRealRunContract:
    """真实驱动 `MainWindow` 跑一次模拟——含 Chromium 子进程，受 `P83_PERF_TESTS` 门控。"""

    @pytest.fixture
    def plan(self, make_plan):
        return make_plan(config_path=DEFAULT_CONFIG, strategy_key='smart',
                         strategy_params={}, path='gui-qt', **T3_PARAMS)

    def test_available_matches_runnability(self):
        adapter = get_adapter('gui-qt')
        assert adapter.available() is True

    def test_result_path_matches_name(self, plan):
        adapter = get_adapter('gui-qt')
        result = adapter.run(plan)
        assert result.path == adapter.name
        assert result.is_user_path is True
        assert result.wall_median and result.wall_median > 0

    def test_platform_recorded_as_offscreen(self, plan):
        result = get_adapter('gui-qt').run(plan)
        assert result.fingerprint.qt_qpa_platform == 'offscreen'

    def test_stages_and_absent_stages_are_labelled(self, plan):
        result = get_adapter('gui-qt').run(plan)
        assert result.stages.get('simulate', 0) > 0
        assert result.stages.get('dispatch', 0) > 0
        for absent in ('config_load', 'env_build', 'pool_start', 'extract'):
            assert absent not in result.stages
        assert any('本路径不产出该段' in w for w in result.warnings)
        assert any('本路径不可得' in w for w in result.warnings)

    def test_no_gui_side_effects_after_teardown(self, plan):
        """规则 7：收尾必须回收 Chromium 子进程，否则每跑一次残留 10 个。

        给一点时间：`psutil.kill()` 是异步的（`TerminateProcess` 返回不等于进程已消失），
        立刻断言会把「正在死」误判成「不死」。等它真的消失才作数，**上限内不消失即失败**。
        """
        import time

        import psutil

        get_adapter('gui-qt').run(plan)

        def leftovers():
            return [c.name() for c in psutil.Process().children(recursive=True)
                    if 'QtWebEngineProcess' in (c.name() or '')]

        deadline = time.perf_counter() + 10.0
        while leftovers() and time.perf_counter() < deadline:
            time.sleep(0.2)
        assert leftovers() == [], f'收尾 10s 后仍有 Chromium 子进程残留：{leftovers()}'

    def test_teardown_goes_through_restarting_flag(self, plan):
        """规则 8：关闭 `MainWindow` 必须先置 `_restarting`，否则弹确认框阻塞。

        **本用例直接断言那个标志**——确认框一旦弹出，用例会挂死而不是失败，
        那样连花在哪都看不出来（§3.11 的实测教训）。
        """
        GuiQtAdapter._prepare_environment(plan)
        app = GuiQtAdapter._make_application()
        adapter = GuiQtAdapter()
        window, _ = adapter._build_window(plan)
        try:
            assert adapter._teardown(app, window) is None
            assert window._restarting is True
        finally:
            adapter._teardown(app, window)
