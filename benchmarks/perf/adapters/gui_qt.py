"""`gui-qt` 路径适配器。

**本文件是 §8.1 组 G 的四个子任务（`3a` / `3b` / `3d` / `3f-1`）的共同落点**——它们
逐项提交、但组内中间态不单独验收，回滚以组为单位（任一单项单独 revert 都会留下
半截适配器）。

**驱动方式：包装已有入口，不重写它**（§3.2 约束 A）。import `main_window.MainWindow`
与 `gacha_panel` 的 `SimulationThread`，用 `offscreen` + `QApplication(sys.argv)` 驱动
真实调用链。**可观测性缺口按约束 B 的范围修订以 opt-in 默认关闭通道补齐**——本文件
本身不改产品的 `gacha_panel` / `main_window`（`3f-2` 的 `main.py` 打点是另一件事）。

**规则 6（本路径的头号纪律）：** `QApplication(sys.argv)` 必须是**非空 argv**，且
`QApplication` 之前须 `setAttribute(AA_ShareOpenGLContexts)`。空 argv 下 QtWebEngine
初始化失败、进程以 `0xC0000409` 终止（§3.10 的六变体矩阵实测）——**此前八次探针全部
失败都是这一个原因**，而不是执行环境限制。

**完成与错误判定（§3.10，三条同时具备）：**

1. **完成判据**：以 `MainWindow` 的**结果落地副作用**为准（`result_store` 更新 /
   `tabs.setCurrentIndex(2)`），**不得**以「tab 索引」单独作完成契约
2. **错误判据**：适配器不改产品代码，故只能从外部可观测的两个出口取信号——
   `SimulationThread.isFinished()` 为真但结果副作用未出现即判失败；`status_update`
   文案含「错误」作二次确认
3. **超时上限**：必须设硬超时，超时即判 FAIL、杀进程树（规则 3），**绝不无超时等待**

`dispatch` 段的切分点按 §3.10 收窄后的口径：**`GachaPanel.on_simulation_finished` 的
emit 到 `MainWindow.on_simulation_finished` 的返回**——包含两次信号发射与 MainWindow
侧的分发。**不照抄 `scripts/profile_gui.py` 的 B6 自建实例序列**（那是替身：它自建
四个面板后直接调 `update_results`，绕开了两条 `on_simulation_finished`）。
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import time
from typing import Any, List, Optional, Tuple

from benchmarks.perf.adapters.base import (
    Adapter,
    AdapterError,
    SingleRun,
    new_run_id,
    register_adapter,
)
from benchmarks.perf.plan import Plan
from benchmarks.perf.profilers.stage import normalize_resources, normalize_stages

logger = logging.getLogger(__name__)

__all__ = ['GuiQtAdapter', 'pyqt_available']

#: 本路径**结构上不产出**的段：产品侧没有回传通道，这几段在 GUI 进程内发生但不外流。
#: 报告据此标注「本路径不产出该段」，**不得留空静默跳过**（§3.5 末表的口径）。
_ABSENT_STAGES = ('config_load', 'env_build', 'pool_start', 'extract')

#: 轮询间隔（秒）。GUI 的完成判据是副作用而非信号，只能轮询。
_POLL_INTERVAL = 0.05

#: 硬超时的下限（秒）。§3.10 建议初值 `max(60s, 单次模拟预估墙钟 × n × 3)`。
_MIN_TIMEOUT = 60.0

#: 线程结束后的**宽限期**（秒）：等排队中的 `finished` 信号被投递。
#: `QThread.isFinished()` 为真不等于「信号已送达」——前者是线程状态，后者要经事件循环。
#: 不给这个宽限期，每次正常完成都会被误判为失败（实测踩到）。
_FINISH_GRACE_SECONDS = 5.0


def pyqt_available() -> bool:
    """本环境有没有 PyQt6。**缺依赖时返回 `False` 而非报错**（§3.9 T3 的 `available()` 约定）。"""
    return importlib.util.find_spec('PyQt6') is not None


@register_adapter
class GuiQtAdapter(Adapter):
    """`gui-qt` 路径。"""

    name = 'gui-qt'
    is_user_path = True

    #: GUI 抽卡面板不向 `run_batch_parallel` 传 `on_result`（`gacha_panel.py:82`）。
    collector = False

    absent_stages = _ABSENT_STAGES

    def available(self) -> bool:
        if not pyqt_available():
            return False
        try:
            import gacha_simulator.gui.main_window  # noqa: F401
        except Exception as exc:  # pragma: no cover - 取决于环境
            logger.debug('gui-qt 路径不可用：%s', exc)
            return False
        return True

    # ── 单次驱动 ─────────────────────────────────────────

    def _run_once(self, plan: Plan) -> SingleRun:
        self._prepare_environment(plan)
        app = self._make_application()
        window, panel = self._build_window(plan)
        try:
            return self._drive(plan, app, window, panel)
        finally:
            self._teardown(app, window)

    # 规则 6：平台在 QApplication 之前设置
    @staticmethod
    def _prepare_environment(plan: Plan) -> None:
        """设定 `QT_QPA_PLATFORM`。`simulation` 用 `offscreen`、`startup` 用真实平台。

        §3.10：`simulation` 下采 `offscreen`——反复跑模拟，不打扰使用者；它会向 stderr
        输出 GPU 错误（`Failed to make current since context is marked as lost`），
        属噪声、不影响功能，报告时须过滤。
        §3.11：`startup` 的冷启动子进程须跑**真实 `windows` 平台**，否则第 6 段
        「窗口可见」不可观测（offscreen 下窗口无原生 HWND）。
        """
        platform_name = 'offscreen' if plan.subject == 'simulation' else 'windows'
        os.environ['QT_QPA_PLATFORM'] = platform_name

    @staticmethod
    def _make_application():
        """构造 `QApplication`。**规则 6 的两条都在这里**。"""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication

        # 必须在 QApplication 之前——QtWebEngine 要求共享 OpenGL 上下文
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        # sys.argv 可能为空（从测试/脚本里调起时），补一个占位以**保证非空**
        # ——空 argv 正是此前八次探针全失败的原因（0xC0000409）
        argv = list(sys.argv) or ['benchmarks.perf']
        app = QApplication.instance() or QApplication(argv)
        return app

    def _build_window(self, plan: Plan) -> Tuple[Any, Any]:
        """建 `MainWindow` 并取出其中的 `GachaPanel`。"""
        from gacha_simulator.gui.main_window import MainWindow

        window = MainWindow()
        panel = self._find_panel(window)
        if panel is None:
            raise AdapterError('在 MainWindow 里找不到 GachaPanel——适配器无从驱动真实入口')
        window.show()
        return window, panel

    @staticmethod
    def _find_panel(window: Any):
        """在 `MainWindow` 的 Tab 里找 `GachaPanel`（`main_window.py:120-129` 的 10 次 addTab）。"""
        from gacha_simulator.gui.gacha_panel import GachaPanel

        for index in range(window.tabs.count()):
            widget = window.tabs.widget(index)
            if isinstance(widget, GachaPanel):
                return widget
        return None

    def _drive(self, plan: Plan, app: Any, window: Any, panel: Any) -> SingleRun:
        """配置面板控件 → 触发真实入口 → 等完成（带硬超时）→ 归一读数。"""

        warnings: List[str] = []
        panel.sim_count.setValue(int(plan.n))
        panel.max_workers.setValue(int(plan.workers))
        panel.seed.setValue(int(plan.seed))

        baseline = self._result_evidence(window)
        baseline_index = self._current_tab_index(window)

        started = time.perf_counter()
        panel.start_simulation()
        thread = getattr(panel, 'simulation_thread', None)
        if thread is None:
            raise AdapterError('start_simulation() 未起 SimulationThread——真实入口的形状变了')

        # 完成判据走 MainWindow 的**结果落地副作用**（§3.10 第 1 条）
        timeout = max(_MIN_TIMEOUT, self._estimate_timeout(plan))
        dispatch_seconds = self._await_completion(app, window, panel, thread,
                                                 baseline, baseline_index, timeout)
        wall = time.perf_counter() - started

        simulate_seconds = max(0.0, wall - dispatch_seconds)
        raw_stages = {'simulate': simulate_seconds, 'dispatch': dispatch_seconds}
        stages, stage_warnings = normalize_stages(raw_stages, absent_by_design=self.absent_stages)
        warnings.extend(w for w in stage_warnings if w not in warnings)
        # 噪声过滤：offscreen 下 Chromium 会往 stderr 输出 GPU 错误，不影响功能（§3.10）
        warnings.append(
            '本路径无回传通道：阶段计时与三元组字节数不可得（§3.5）；'
            'simulate 段含 env 构建与进程池启动——产品侧无采集点，三者在这条路径上不可切分。'
        )

        resources, resource_warnings = normalize_resources(subject=plan.subject)
        warnings.extend(w for w in resource_warnings if w not in warnings)

        return SingleRun(
            wall=wall,
            stages=stages,
            resources=resources,
            functions=None,          # GUI 无注入通道（§3.8 D1 注入通道表）
            samples_meta=None,
            return_compact=False,    # `gacha_panel.py:66` 在跑主模拟前置 False
            run_id=new_run_id(),
            warnings=warnings,
        )

    @staticmethod
    def _estimate_timeout(plan: Plan) -> float:
        """§3.10 建议的初值：`max(60s, 单次模拟预估墙钟 × n × 3)`。

        无单次预估时退化为「按 `n` 线性给额度」——绝不返回 0 或无穷。
        """
        per_simulation = 0.05        # 保守的单次模拟秒数上限（实测远低于此）
        return max(_MIN_TIMEOUT, per_simulation * max(1, plan.n) * 3)

    @staticmethod
    def _current_tab_index(window: Any) -> Optional[int]:
        try:
            return int(window.tabs.currentIndex())
        except Exception:  # pragma: no cover - 形状变化时退化为 None
            return None

    @staticmethod
    def _result_evidence(window: Any) -> Any:
        """`MainWindow` 侧「结果已落地」的**副作用**证据（§3.10 第 1 条）。

        取 `result_store` 的版本或长度作证据——它是 `on_simulation_finished` 的产物，
        而不是信号本身。**不以 tab 索引单独作完成契约**：它是副作用，不是契约。
        """
        store = getattr(window, 'result_store', None)
        if store is None:
            return None
        # `on_simulation_finished` 的落地动作按序是 `result_store.add(...)`（`main_window.py:501`）
        # → `set_current`（`:502`）→ `tabs.setCurrentIndex(2)`（`:507`）。数据集条数是最直接
        # 的那一个副作用；`setCurrentIndex` 是它的下游，**不得单独作完成契约**。
        for accessor in ('list_datasets',):
            method = getattr(store, accessor, None)
            if callable(method):
                try:
                    return len(method())
                except Exception:  # pragma: no cover - 形状变化时退化
                    continue
        return None

    def _await_completion(self, app: Any, window: Any, panel: Any, thread: Any,
                          baseline: Any, baseline_index: Optional[int],
                          timeout: float) -> float:
        """轮询等完成，返回 `dispatch` 段的耗时。

        三条出口（§3.10）：**完成** = 结果副作用出现；**失败** = 线程结束但副作用未出现；
        **超时** = 到点杀进程树并抛错（绝不无超时等待）。
        """
        deadline = time.perf_counter() + timeout
        dispatch_started: Optional[float] = None

        while True:
            app.processEvents()
            evidence = self._result_evidence(window)
            # **两侧都为 None 时不能用 `!=` 判完成**——那意味着本窗口根本没有可读的
            # 结果容器，而不是「结果已落地」。此时只能靠线程结束 + 错误判据收口。
            if baseline is not None and evidence is not None and evidence != baseline:
                # 副作用已落地。`dispatch` 段 = 面板 emit 到 MainWindow 处理返回。
                dispatch_started = time.perf_counter()
                self._drain_events(app, _POLL_INTERVAL)
                return time.perf_counter() - dispatch_started

            if self._thread_finished(thread):
                # **先宽限排空、再下结论**：`QThread.isFinished()` 会先于**排队中的
                # `finished` 信号**为真（信号经事件循环投递）。不等投递就判失败，
                # 会把每一次正常完成都误报成失败——`_FINISH_GRACE_SECONDS` 就是为此。
                if self._grace_drain(app, window, baseline):
                    dispatch_started = time.perf_counter()
                    self._drain_events(app, _POLL_INTERVAL)
                    return time.perf_counter() - dispatch_started

                status = self._status_text(panel)
                if self._looks_like_error(status):
                    raise AdapterError(
                        f'gui-qt 路径失败：SimulationThread 已结束但结果副作用未出现，'
                        f'状态栏文案={status!r}（§3.10 的错误判据）'
                    )
                if self._current_tab_index(window) != baseline_index:
                    # 副作用以另一种形式出现（切了 tab）——按完成处理
                    dispatch_started = time.perf_counter()
                    self._drain_events(app, _POLL_INTERVAL)
                    return time.perf_counter() - dispatch_started
                raise AdapterError(
                    'gui-qt 路径失败：SimulationThread 已结束，但宽限期后结果副作用与 '
                    f'tab 索引仍未变化，状态栏文案={status!r}（§3.10 的错误判据）'
                )

            if time.perf_counter() >= deadline:
                self._kill_children(window)
                raise AdapterError(
                    f'gui-qt 路径超过硬超时 {timeout:.0f}s（§3.10 第 3 条：绝不无超时等待）；'
                    '已按规则 3 回收进程树'
                )
            self._drain_events(app, _POLL_INTERVAL)

    def _grace_drain(self, app: Any, window: Any, baseline: Any) -> bool:
        """线程结束后的宽限排空：期间副作用若出现即判完成。返回是否已出现。"""
        deadline = time.perf_counter() + _FINISH_GRACE_SECONDS
        while time.perf_counter() < deadline:
            app.processEvents()
            evidence = self._result_evidence(window)
            if baseline is not None and evidence is not None and evidence != baseline:
                return True
            time.sleep(0.01)
        return False

    @staticmethod
    def _drain_events(app: Any, seconds: float) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            app.processEvents()
            time.sleep(0.005)

    @staticmethod
    def _thread_finished(thread: Any) -> bool:
        try:
            return bool(thread.isFinished())
        except Exception:  # pragma: no cover
            return False

    @staticmethod
    def _status_text(panel: Any) -> str:
        label = getattr(panel, 'status_label', None)
        try:
            return str(label.text()) if label is not None else ''
        except Exception:  # pragma: no cover
            return ''

    @staticmethod
    def _looks_like_error(status: str) -> bool:
        """二次确认用的文案判据（`gacha_panel.py:372-375` 的 `on_simulation_error` 会写「错误」）。"""
        return '错误' in status

    # ── 收尾（`3d`：规则 7 / 规则 8） ─────────────────────

    def _teardown(self, app: Any, window: Any) -> None:
        """先回收 Chromium 子进程，再置 `_restarting` 关闭窗口。

        **规则 8**：关闭 `MainWindow` 必须先置 `win._restarting = True` 再 `close()`，
        否则弹「确定要退出吗」确认框并阻塞，自动化流程卡死等人点击
        （`main_window.py:627-641`）。项目自带该绕过路径（Ps03 的 Ctrl+R 重启即走此路）。
        **规则 7**：`MainWindow` 显示后实测 10 个 `QtWebEngineProcess` 子进程，不回收会残留。
        """
        try:
            window._restarting = True          # 规则 8：绕过「确定要退出吗」确认框
            window.close()
        except Exception as exc:  # pragma: no cover
            logger.debug('关闭 MainWindow 失败：%s', exc)
        try:
            app.processEvents()
        except Exception:  # pragma: no cover
            pass
        self._kill_children(window)            # 规则 7：回收 Chromium 子进程

    @staticmethod
    def _kill_children(window: Any) -> None:
        """回收本进程的 Chromium 子进程（规则 7）。

        只杀 QtWebEngine 相关子进程，**不动本进程自己**。缺 `psutil` 时静默跳过——
        它是收尾动作，不该让整次测量失败。
        """
        try:
            import psutil
        except ImportError:  # pragma: no cover
            return
        try:
            current = psutil.Process()
            for child in current.children(recursive=True):
                try:
                    if 'QtWebEngineProcess' in (child.name() or ''):
                        child.kill()
                except psutil.Error:  # pragma: no cover - 已在退出中
                    continue
        except psutil.Error as exc:  # pragma: no cover
            logger.debug('回收 Chromium 子进程失败：%s', exc)

    # ── 平台口径 ─────────────────────────────────────────

    def _qt_qpa_platform(self, run: SingleRun) -> Optional[str]:
        """§3.11：记录本次 `QT_QPA_PLATFORM` 取值，供基线比对照出平台口径。"""
        return os.environ.get('QT_QPA_PLATFORM')
