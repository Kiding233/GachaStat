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

## 启动测量（`subject='startup'`，`3f-1` 的适配器侧）

`subject='startup'` 走**另一条驱动**：拉一个**全新冷子进程**
`python -X importtime -m gacha_simulator.main`（规则 9），在**父进程**里用外部观测
取时间线，然后按 §3.11 的八段词汇表归一。**不复制 `main.py` 的初始化序列**
（§3.2 约束 A）——那个子进程就是产品本身。

**平台分工（§3.11 定死）：** 该子进程跑**真实 `windows` 平台**，不从
`subject='simulation'` 的 `offscreen` 继承——第 6 段「窗口可见」的采集方式是
`EnumWindows` 轮询，而 offscreen 下窗口没有原生 HWND，`EnumWindows` 不可能枚举到
被测窗口（2026-09-21 实测：`P83PROBE present: False`），第 6 段随之不可得。

| 段 | 谁采 | 本文件里的落点 |
|---|---|---|
| 1 解释器启动 | 父进程 spawn 打点 + 子进程打点首行 | `_observe_startup`（父）/ `3f-2` 的 JSON（子） |
| 2 Qt 栈 import | 父进程解析子进程 stderr 的 `-X importtime` | `parse_importtime` |
| 3 `QApplication` 构造 | 子进程打点 | `3f-2` 的 JSON |
| 4 主模块 import | 同 2 | `parse_importtime` |
| 5 主窗口构造 | 子进程打点 | `3f-2` 的 JSON |
| 6 窗口可见 | 父进程 `EnumWindows` 轮询 | `_observe_startup` |
| 7 启动工作完成 | 父进程整棵进程树 CPU 采样 | `_observe_startup` |
| 8 图表可用 | 子进程轮询 `MainWindow.charts_ready()` | `3f-2` 的 JSON |

**第 8 段的观察为什么落在子进程**（与 §3.11 表格里「落点：适配器」不同，2026-09-22
实施时判定并记录）：就绪状态是**另一个进程内的对象状态**，父进程无法对它做方法调用。
§3.11 同时要求「必须经新增的只读聚合入口 `MainWindow.charts_ready()`、不得读私有
`_loaded`」与「规则 9 要求冷进程」——两条都成立时，**调用 `charts_ready()` 的只能是
被测进程自己**。故本文件的角色是**消费者**：读子进程回传的 JSON（`3f-2` 生产）。
1 / 3 / 5 段同理（§3.11 的采集方式表本就写明这三段「无法纯外部观测」）。

**钩子缺席时软降级**（§3.8 D7 同源）：未设置打点环境变量、或产品侧尚未落地该钩子时，
1 / 3 / 5 / 6 / 8 段在报告里逐段标注「不可得」并写明成因，**不假装它们被采到了**；
2 / 4 / 7 段照常产出。`6` 段在本表里也依赖钩子（它需要「主窗口构造结束」这个锚点
才能算成耗时），故钩子缺席时同样标注——**理由是口径一致性，不是采集不到**：该时刻
本身可由父进程直接读出（作为「自进程创建起 2.3s」这样的累计时刻），但把累计时刻混进
一份全是耗时的 `stages` 会让报告的占比失去意义（见 `stage.STARTUP_STAGES` 的注释）。
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from benchmarks.perf.adapters.base import (
    Adapter,
    AdapterError,
    SingleRun,
    kill_process_tree,
    new_run_id,
    register_adapter,
)
from benchmarks.perf.plan import Plan
from benchmarks.perf.profilers.stage import (
    STARTUP_STAGES,
    normalize_resources,
    normalize_stages,
)

logger = logging.getLogger(__name__)

__all__ = ['GuiQtAdapter', 'pyqt_available', 'qt_argv', 'parse_importtime',
           'STARTUP_JSON_ENV']

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

# ── 启动测量（`3f-1`）─────────────────────────────────────

STARTUP_JSON_ENV = 'GACHASTAT_STARTUP_TIMELINE'
"""启动打点回传文件的环境变量名。**`3f-2` 是它的生产者，本文件是消费者。**

**契约是一个字符串，两侧各写一份字面量**：产品代码（`gacha_simulator/main.py`）
不得 import `benchmarks/`（后者是开发侧资产、不进发布产物，见 §四「不进发布产物」），
故该名在两侧各存一份，**改动须同时改两处**。此约束同 §3.8 D1 的四字段：跨
dev / 产品边界的东西只能靠契约名对齐，不能靠 import。

「为何这里可以用环境变量」的理由见 §3.11：启动打点是**一次性冷子进程**，子进程即用
即灭、不污染适配器进程，且产物是文件而非进程内状态，故不受 §3.8 D1 的约束。
"""

#: 启动冷子进程的平台。§3.11 定死：**真实平台**，不从 `simulation` 的 `offscreen`
#: 继承（offscreen 下窗口无原生 HWND，第 6 段不可观测）。非 Windows 主机上不设该
#: 变量、交给 Qt 选原生平台，此时 `EnvFingerprint` 记「未记录」（不可比）而非猜一个值。
STARTUP_PLATFORM: Optional[str] = 'windows' if os.name == 'nt' else None

#: 启动测量的硬超时（秒）。单次启动实测约 10s（§3.11 的实测数据：图表可用 8.22s），
#: 60s 给足余量；超时即判失败并回收进程树（§3.10 第 3 条），绝不无超时等待。
_STARTUP_MIN_TIMEOUT = 60.0

#: 记到第 7 段之后，再等第 8 段的宽限（秒）。超过即按「不可得」收口，
#: **不为一个可能永远不来的段把整次测量拖到硬超时**。
_STARTUP_CHARTS_GRACE_SECONDS = 20.0

#: 整棵进程树 CPU 低于该百分比即视为「启动工作完成」（第 7 段）。
#:
#: **2026-09-22 实测标定**（本机 `python -m gacha_simulator.main`，0.5s 窗口）：
#: 0.5s 109% → 1.0-2.6s 3-9% → 3.1-4.1s 42-48% → 4.7s 156%（Chromium 开始起）
#: → 5.7s **窗口可见** → 6.2-7.3s 615-999%（渲染 + 图表）→ **7.8s 起 0.0%** 并
#: 保持，期间 8.8s 有一个 6% 的短促回升。故取 5% 作阈值：高于空闲毛刺、远低于
#: 任何一段真实工作。**数值是初始值**（同 §3.4 的口径），证伪则记录后修订。
_STARTUP_CPU_IDLE_PERCENT = 5.0

#: 第 7 段要求**连续**多少次采样都低于阈值才算完成。单次采样会被调度抖动骗过。
_STARTUP_CPU_IDLE_SAMPLES = 2

#: 进程树 CPU 的采样窗口（秒）。**0.5s 是实测标定的取值**：0.2s 时单次窗口的百分比
#: 抖动足以让「连续两次低于 5%」在真实工作期间偶然成立，0.5s 则把「持续安静」
#: 与「恰好赶上两个空档」分开（连上 `_STARTUP_CPU_IDLE_SAMPLES=2` 即要求约 1s 安静）。
_STARTUP_CPU_WINDOW_SECONDS = 0.5

WARN_STARTUP_NOT_A_PARTITION = (
    '启动八段不是一份划分：Qt 栈 import（第 2 段）与主模块 import（第 4 段）是 '
    '-X importtime 的独立测量，时间窗与第 1 / 3 / 5 段重叠，故八段之和不等于总'
    '启动时间、「阶段占比」对本次记录无「占时间线百分比」的解释（逐段比值不受影响）。'
)
"""每次启动测量都随记录带出——**该口径不写在报告里，读的人会把八段相加当总时长**。"""


def qt_argv() -> List[str]:
    """构造 `QApplication` 用的 argv。**规则 6 的第一条：必须非空。**

    从测试或脚本里调起时 `sys.argv` 可能是 `[]`（pytest 有 argv，但 `python -c` 的
    调用方常传空列表），而**空 argv 下 QtWebEngine 初始化失败、进程以 `0xC0000409`
    终止**——2026-09-17 之前八次探针全部失败都是这一个原因，不是环境限制。
    故这里补一个占位，保证永不交空列表出去。

    独立成函数是为了**可测**：空 argv 的复现要能把 `sys.argv` 清空后再构造
    `QApplication`，而 Qt 的 `QApplication` 在同一进程里只允许一个实例（第二次构造
    会拿到既有实例），故「行为级」断言会退化成空断言——这条规则必须有一条直接的、
    不依赖 Qt 单例语义的断言。
    """
    return list(sys.argv) or ['benchmarks.perf']


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
        if plan.subject == 'startup':
            return self._run_startup(plan)
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
        """设定本进程的 `QT_QPA_PLATFORM`（**只对 `simulation` 有效**）。

        §3.10：`simulation` 下采 `offscreen`——反复跑模拟，不打扰使用者；它会向 stderr
        输出 GPU 错误（`Failed to make current since context is marked as lost`），
        属噪声、不影响功能，报告时须过滤。

        `subject='startup'` **不走这里**：它驱动的是独立冷子进程，平台由父进程经
        `Popen(env=...)` 交给子进程（`_startup_child_env`）——顺手改父进程的环境变量
        既无必要，又会让「父进程此刻的平台」与「被测进程的平台」两件事混成一件。
        """
        if plan.subject != 'simulation':
            return
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'

    @staticmethod
    def _make_application():
        """构造 `QApplication`。**规则 6 的两条都在这里**。"""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication

        # 必须在 QApplication 之前——QtWebEngine 要求共享 OpenGL 上下文
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app = QApplication.instance() or QApplication(qt_argv())
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
        """§3.11：记录本次 `QT_QPA_PLATFORM` 取值，供基线比对照出平台口径。

        `simulation` 取本进程环境变量（适配器自己在 `_prepare_environment` 里设的
        `offscreen`）；`startup` 的平台由父进程交给冷子进程，**不在本进程环境里**，
        故 `_run_startup` 经 `SingleRun.qt_qpa_platform` 显式报出，本方法对它不生效。
        """
        return os.environ.get('QT_QPA_PLATFORM')

    # ── 启动测量（`3f-1`：§3.11 的 1-8 段） ───────────────

    def _run_startup(self, plan: Plan) -> SingleRun:
        """启动测量：预热一次丢弃（规则 10），再测一次并记录（规则 9）。

        每次都是一条**全新冷子进程**。需要进程内观察的段（1 / 3 / 5 / 8）由子进程
        经 `STARTUP_JSON_ENV` 指向的 JSON 回传（生产者是 `3f-2`），其余由父进程外部
        观测（2 / 4 解析 `-X importtime`，6 `EnumWindows`，7 整棵进程树 CPU）。
        """
        warnings: List[str] = []

        # 规则 10：先跑一次同条件预热并丢弃。**冷启动（清空文件缓存）显式不在覆盖
        # 范围**——无管理员权限下无法可靠清空 Windows 文件缓存（§3.11 规则 10）。
        # 预热那次的告警整份丢弃（读数本就不记录），但异常不吞：两次拉不起来同样是
        # 拉不起来，第二次照样抛。
        self._launch_startup_child(plan)

        observed, hook = self._launch_startup_child(plan)
        wall = observed['wall']

        if hook is None:
            warnings.append(
                '冷子进程未回传启动打点（未设置 ' + STARTUP_JSON_ENV + '、或产品侧尚未'
                '落地 main.py 的打点钩子，见 §3.11「分段采集方式」）——1 / 3 / 5 / 8 段'
                '与依赖锚点的 6 段本次不可得。成因是**回传通道未启用**，不是采集点故障。'
            )

        if observed.get('charts_ready_error'):
            warnings.append(
                '第 8 段「图表可用」不可得：被测进程轮询 MainWindow.charts_ready() 时抛错'
                f'（{observed["charts_ready_error"]}）——八处只读访问器链条有断点，'
                '不是「图表一直没就绪」。'
            )

        raw = self._startup_segments(observed, hook, warnings)
        stages, stage_warnings = normalize_stages(
            raw,
            absent_by_design=self._startup_absent(hook),
            vocabulary=STARTUP_STAGES,
        )
        warnings.extend(w for w in stage_warnings if w not in warnings)

        resources, resource_warnings = normalize_resources(
            subject=plan.subject, rss_peak_mb=observed.get('rss_peak_mb'),
        )
        warnings.extend(w for w in resource_warnings if w not in warnings)

        return SingleRun(
            wall=wall,
            stages=stages,
            resources=resources,
            # 启动期不产出函数级统计：§3.8 D1 的四字段注入通道落在
            # `run_batch_parallel` 的 worker 路径上，冷启动子进程根本不经过它。
            functions=None,
            samples_meta=None,
            # 启动测量不跑模拟、不产 `CompactResult`。`return_compact` 的语义是「本次
            # 运行是否构建了完整 CompactResult」，故为 False；它对每条 startup 记录
            # 恒相同（startup 之间可比，与 simulation 侧不可比）。
            return_compact=False,
            qt_qpa_platform=STARTUP_PLATFORM,
            run_id=new_run_id(),
            warnings=warnings,
        )

    def _launch_startup_child(self, plan: Plan) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """拉一条冷子进程、观测到收口，返回（父进程侧读数, 子进程回传的 JSON）。

        **预热与测量共用本方法**——规则 10 要求两次同条件，两条不同的代码路径迟早会
        漂移成不同条件。超时取固定的 `_STARTUP_MIN_TIMEOUT`：启动的代价与 `plan.n`
        无关（`n` 在 `startup` 下被忽略，见 `plan.STARTUP_IGNORED_FIELDS`），故不套用
        §3.10 那条按 `n` 线性给额度的公式。
        """
        hook_dir = tempfile.mkdtemp(prefix='p83-startup-')
        hook_path = os.path.join(hook_dir, 'timeline.json')
        stderr_path = os.path.join(hook_dir, 'stderr.txt')
        observed: Dict[str, Any] = {'spawn_at': None, 'rss_peak_mb': None, 'stderr': ''}
        proc = None
        try:
            spawn_at = time.perf_counter()
            # ⚠ **stderr 必须重定向到文件，不能用 PIPE**：`-X importtime` 会给每个被导入
            # 的模块打一行，GUI 栈有上千个模块，远超管道缓冲区；不读走就会**把子进程
            # 堵死在 write 上**——症状是窗口永不出现、测量到硬超时才失败（实测踩到：
            # 一个 60s 超时的空跑，而同一命令不带 `-X importtime` 时 14s 就出窗口）。
            # 用文件则写侧永不阻塞，且父进程在观测期间一行都不用读。
            with open(stderr_path, 'w', encoding='utf-8', errors='replace') as stderr_file:
                proc = subprocess.Popen(
                    [sys.executable, '-X', 'importtime', '-m', 'gacha_simulator.main'],
                    cwd=_project_root(),
                    env=self._startup_child_env(hook_path),
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_file,
                )
                observed = self._observe_startup(proc, spawn_at, _STARTUP_MIN_TIMEOUT,
                                                 hook_path)
        except AdapterError as exc:
            # 启动失败的第一现场是子进程自己的 stderr（导入错误、Qt 报错、
            # 0xC0000409 之类都在那里）。不带出来，读报告的人只看到一个「超时」，
            # 还得自己去复现一遍才能查因。
            raise AdapterError(f'{exc}；子进程 stderr 末尾：{_tail(stderr_path)}') from exc
        finally:
            if proc is not None:
                kill_process_tree(proc.pid)             # 规则 3：整棵进程树
                self._kill_children(None)               # 规则 7：Chromium 子进程
            observed['stderr'] = _read_text_file(stderr_path)
        return observed, _read_startup_json(hook_path, proc.pid if proc is not None else None)

    @staticmethod
    def _startup_child_env(hook_path: str) -> Dict[str, str]:
        """冷子进程的环境：显式给平台（§3.11），显式给打点回传路径（`3f-2` 消费）。

        **不继承本进程的 `QT_QPA_PLATFORM`**：本进程可能刚跑过一次
        `subject='simulation'`（`offscreen`），继承下去会让第 6 段不可观测——
        这正是 §3.11「不得从 `3a` 继承 offscreen」要挡的事。
        """
        env = dict(os.environ)
        if STARTUP_PLATFORM is None:
            env.pop('QT_QPA_PLATFORM', None)
        else:
            env['QT_QPA_PLATFORM'] = STARTUP_PLATFORM
        env[STARTUP_JSON_ENV] = hook_path
        return env

    def _observe_startup(self, proc: Any, spawn_at: float, timeout: float,
                         hook_path: str) -> Dict[str, Any]:
        """外部观测循环：窗口可见（第 6 段）、整棵进程树 CPU 归零（第 7 段）、RSS 峰值。

        三个出口：**两个关键时刻都取到** → 正常收口；**子进程提前退出** → 抛错
        （启动测量没有「部分成功」这种读数）；**硬超时** → 杀掉进程树并抛错
        （§3.10 第 3 条：绝不无超时等待）。
        """
        observed: Dict[str, Any] = {'spawn_at': spawn_at, 'rss_peak_mb': None, 'stderr': ''}
        idle_streak = 0
        deadline = spawn_at + timeout

        while True:
            now = time.perf_counter()
            if proc.poll() is not None:
                raise AdapterError(
                    f'启动冷子进程在测量完成前退出（退出码 {proc.returncode}）——'
                    '启动测量的读数只有「完整的一次启动」这一种，没有部分成功'
                )
            if time.perf_counter() >= deadline:
                raise AdapterError(
                    f'启动测量超过硬超时 {timeout:.0f}s（§3.10 第 3 条：绝不无超时等待）；'
                    f'已取到的时刻：{sorted(observed)}，已按规则 3 回收进程树'
                )

            # ── 阶段一：等窗口可见。**这一段不去采 CPU** ──
            # 两个理由：① 采一次要占 0.2s 的采样窗口，会拖慢「窗口何时可见」的判定；
            # ② 第 7 段是「启动工作完成」，在窗口出现之前它无从谈起，而观测者自己
            # 的采样动作会给被测进程抢 CPU，把读数推向更晚——观测不该成为被观测的因。
            if 'window_visible' not in observed:
                if _child_has_visible_window(proc.pid):
                    observed['window_visible'] = now - spawn_at
                else:
                    time.sleep(_POLL_INTERVAL)
                continue

            # ── 阶段二：窗口已可见，开始按整棵进程树判「启动工作完成」──
            busy = _tree_cpu_percent(proc.pid, _STARTUP_CPU_WINDOW_SECONDS)
            if busy is not None:
                idle_streak = idle_streak + 1 if busy < _STARTUP_CPU_IDLE_PERCENT else 0
                if idle_streak >= _STARTUP_CPU_IDLE_SAMPLES and 'work_complete' not in observed:
                    observed['work_complete'] = time.perf_counter() - spawn_at
                    # 规则 11：RSS 固定在此刻采样（启动完成时刻的峰值）
                    observed['rss_peak_mb'] = _process_rss_mb(proc.pid)

            if 'work_complete' in observed:
                payload = _read_startup_json(hook_path, proc.pid)
                charts = (payload or {}).get('charts_ready')
                if charts is not None:
                    # 子进程的 `perf_counter()` 与父进程同源（Windows 上为 QPC，
                    # 系统级），故这里存绝对值、拼段时再与父进程的时刻相减。
                    observed['charts_ready_abs'] = float(charts)
                    break
                error = (payload or {}).get('charts_ready_error')
                if error:
                    # 「一直不就绪」与「访问器坏了」是两件事。被测进程已停表并报出
                    # 成因，父进程就别再等——八处只读访问器的失败不该伪装成超时。
                    observed['charts_ready_error'] = str(error)
                    break
                # 钩子不在（产品侧未落地或未启用）就别等——第 8 段不可能来。有钩子但
                # 还没就绪时给一段宽限，**不为一个可能永远不来的段把整次测量拖到硬超时**。
                grace = _STARTUP_CHARTS_GRACE_SECONDS if payload is not None else 0.0
                if time.perf_counter() >= spawn_at + observed['work_complete'] + grace:
                    break

        # `wall` 取**「启动工作完成」这一刻**（自进程创建起算），不是观测循环的
        # 时长：循环可能在等第 8 段的宽限里多跑一段，把那段算进总墙钟会让
        # 「本次启动用了多久」随「有没有等到图表就绪」漂移，而后者是另一件事
        # （第 8 段）。它也是 §3.11 实测数据里「启动完成 6.5s」的那个量。
        observed['wall'] = observed['work_complete']
        return observed

    def _startup_segments(self, observed: Mapping[str, Any], hook: Optional[Mapping[str, Any]],
                          warnings: List[str]) -> Dict[str, float]:
        """把「父进程侧时刻」与「子进程回传标记」拼成八段**耗时**。

        词汇表见 `stage.STARTUP_STAGES`：值一律是相邻时刻之差（理由见该常量注释），
        时刻由前缀和还原。

        子进程的 `perf_counter()` 与父进程**是同一个时钟**（Windows 上为 QPC，
        系统级、非进程级），故父进程可以直接与子进程回传的绝对值相减。仍做**合理性
        检查**（`_positive`）：结果不落在 (0, 段上限] 内即判该段不可得并记成因——
        若哪天换了平台导致两进程时钟不同源，这里是第一个报错的地方，而不是产出一个
        荒谬数字的地方。
        """
        raw: Dict[str, float] = {}

        # 第 2 / 4 段：解析子进程 stderr 里的 `-X importtime`
        raw.update(parse_importtime(observed.get('stderr') or ''))

        hook = hook or {}
        spawn_at = observed.get('spawn_at')
        origin = _as_float(hook.get('origin'))

        # 第 1 段：打点首行的 `perf_counter` 减去父进程 spawn 时刻。这是**近似**——
        # 父进程的 spawn 时刻早于子进程真正被创建（含 fork / exec 的延迟），故本值
        # 会略小于「进程创建 → 脚本首行」的真值（§3.11 第 1 段的取法 ①）。
        if origin is not None and spawn_at is not None:
            raw['interpreter_start'] = _positive(origin - spawn_at, warnings,
                                                 'interpreter_start')

        # 第 3 / 5 段：子进程自己量的一对时刻
        construct_end: Dict[str, Optional[float]] = {}
        for key, start_key, end_key in (
            ('app_construct', 'app_construct_start', 'app_construct_end'),
            ('window_construct', 'window_construct_start', 'window_construct_end'),
        ):
            start, end = _as_float(hook.get(start_key)), _as_float(hook.get(end_key))
            construct_end[key] = end
            if start is not None and end is not None:
                value = _positive(end - start, warnings, key)
                if value is not None:
                    raw[key] = value

        # ── 第 6 / 7 / 8 段：三个「时刻」按**观测到的先后**切分 ──
        #
        # 三者的名义顺序是「可见 → 启动工作完成 → 图表可用」（§3.11 的 1-8 排列），
        # 但**实测会出现顺序颠倒**：2026-09-22 本机实测，图表在 2.29s 就绪，而整棵
        # 进程树到 3.14s 才安静下来——「图表能看了」与「后台不再忙了」本来是两条
        # 独立的线，没有固定先后（同机 2026-09-18 的读数则是先完成、后就绪）。
        #
        # 故按观测顺序相减、把每个时长记在**较晚那个时刻**的段上，并在顺序颠倒时记
        # 一条告警。若按名义顺序硬减，颠倒时得到的是负值、只能整段丢弃——那会把一个
        # 真实存在且可测的时刻变成「永远不可得」，而读的人还以为那段有问题。
        #
        # 各时刻先换算到**同一根轴**（父进程的 `perf_counter`）：父进程侧的量是相对
        # spawn 的时长，子进程侧的量是绝对时钟值，两者相差一个 `spawn_at`。
        charts = _as_float(observed.get('charts_ready_abs'))
        visible = observed.get('window_visible')
        window_end = construct_end.get('window_construct')
        marks: List[Tuple[str, float]] = []
        if window_end is not None:
            # 锚点：第 6 段的起点是「主窗口构造结束」，它本身不是一段。
            marks.append(('_window_construct_end', window_end))
        if visible is not None and spawn_at is not None:
            marks.append(('window_visible', spawn_at + visible))
        if 'work_complete' in observed and spawn_at is not None:
            marks.append(('work_complete', spawn_at + observed['work_complete']))
        if charts is not None:
            marks.append(('charts_ready', charts))
        marks.sort(key=lambda item: item[1])

        for (_, prev_at), (name, at) in zip(marks, marks[1:]):
            if name.startswith('_'):
                continue
            value = _positive(at - prev_at, warnings, name)
            if value is not None:
                raw[name] = value

        observed_order = [name for name, _ in marks if not name.startswith('_')]
        nominal_order = [name for name in ('window_visible', 'work_complete', 'charts_ready')
                         if name in observed_order]
        if observed_order != nominal_order:
            warnings.append(
                '启动段的观测顺序与 §3.11 的名义顺序不同：观测到 '
                f'{" → ".join(observed_order)}，名义为 {" → ".join(nominal_order)}。'
                '段值因此按**观测顺序**相减（每个时长记在较晚那个时刻的段上）——'
                '「窗口可见」「启动工作完成」「图表可用」三件事没有固定先后，'
                '把其中两件当成有前后关系会算出负值并整段丢弃。'
            )

        # 口径注记随记录带出——**不写进报告的话，读的人会把八段相加当总启动时间**。
        warnings.append(WARN_STARTUP_NOT_A_PARTITION)
        return {key: value for key, value in raw.items() if value is not None}

    @staticmethod
    def _startup_absent(hook: Optional[Mapping[str, Any]]) -> Tuple[str, ...]:
        """本路径**不产出**的启动段：缺 `main.py` 打点时，进程内观察的那几段无从取得。

        与「应收未收」区分开（`normalize_stages` 的两条告警文案不同）：这里是
        「冷子进程的回传通道未启用」，不是「采集点坏了」。`6` 段一并列入——它需要
        「主窗口构造结束」这个锚点才能算成耗时，理由见模块 docstring 末段。
        """
        if hook:
            return ()
        return ('interpreter_start', 'app_construct', 'window_construct',
                'window_visible', 'charts_ready')


# ── 启动测量的模块级辅助 ─────────────────────────────────
#
# 全部是纯函数（除两个采样器要读进程），故可单测——启动测量本身要起真实窗口、
# 进不了默认 `pytest -q`（§3.9 T6），但**解析与拼段**这两件最容易写错的事
# 不该跟着一起被门控掉。

#: `-X importtime` 的输出行。三个字段：self(µs) | cumulative(µs) | 模块名。
#: 格式由 CPython 定死（`import time: %9ld | %10ld | %*s%s`），自 3.7 未变。
_IMPORTTIME_RE = re.compile(r'^import time:\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\S+)\s*$')

#: 第 4 段「主模块 import」认的模块名。`main.py` 的 `__main__` 护卫里做的是
#: `from gacha_simulator.gui import MainWindow`，它触发的正是这个模块的导入。
_MAIN_MODULE = 'gacha_simulator.gui.main_window'


def parse_importtime(text: str) -> Dict[str, float]:
    """从 `-X importtime` 的输出里取第 2 段（Qt 栈 import）与第 4 段（主模块 import）。

    - **第 2 段 = 所有 `PyQt6*` 模块的 self 时间之和**。用 self 而非 cumulative：
      `PyQt6.QtWidgets` 与 `PyQt6.QtWebEngineWidgets` 在导入树里是**并列的顶层**，
      各自 cumulative 都包含 `PyQt6.QtCore` 等公共部分，相加会重复计入（实测同一
      进程里 `PyQt6.QtCore` 只被真正导入一次，故 self 之和无重复）。每个模块在
      importtime 里只出现一行，取和即可。
    - **第 4 段 = `gacha_simulator.gui.main_window` 那一行的 cumulative**——这一个
      要的是「导入它一共花了多久」，含它拖进来的全部面板与依赖，故用 cumulative。

    解析不到的段**不返回**（调用方按「未采集」逐段告警），不返回 0——0 是一个
    合法读数（快得不计），与「没测到」必须分开。
    """
    qt_self_us = 0.0
    qt_seen = False
    main_import_us: Optional[float] = None

    for line in (text or '').splitlines():
        match = _IMPORTTIME_RE.match(line.strip())
        if match is None:
            continue
        self_us, cumulative_us, name = match.groups()
        if name.startswith('PyQt6'):
            qt_self_us += float(self_us)
            qt_seen = True
        if name == _MAIN_MODULE:
            main_import_us = float(cumulative_us)

    result: Dict[str, float] = {}
    if qt_seen:
        result['qt_import'] = qt_self_us / 1e6
    if main_import_us is not None:
        result['main_import'] = main_import_us / 1e6
    return result


def _project_root() -> str:
    """仓库根（含 `gacha_simulator/` 包的目录）。

    `-m gacha_simulator.main` 需要 cwd 在 `sys.path` 上；产品是 editable 安装时
    其实随处可跑，但把 cwd 定死在仓库根可让「未安装也能跑」这条路径同时成立。
    `<root>/benchmarks/perf/adapters/gui_qt.py` 往上四级即根。
    """
    return str(Path(__file__).resolve().parents[3])


def _as_float(value: Any) -> Optional[float]:
    """宽松取浮点：`None` / 缺失 / 非数一律 `None`（**不猜 0**）。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive(value: Optional[float], warnings: List[str], name: str) -> Optional[float]:
    """合理性检查：段的耗时必须落在 (0, `_STARTUP_MIN_TIMEOUT`] 内。

    落在外面的两种情形都要点名，而不是「结果有点怪但先写进去」：

    - **非正值**：多半是两进程时钟不同源（父进程的 `perf_counter` 与子进程的不是
      同一根轴）。Windows 上两者同为 QPC、系统级，故正常情况下不会发生；但这是
      「换了平台就静默产出荒谬数字」的那类风险，检查放在这里最省。
    - **超上限**：多半是子进程回传的是另一种量纲（如毫秒），或本次测量本身异常。
    """
    if value is None:
        return None
    if value <= 0:
        warnings.append(
            f'启动段 {name}（{name}）算出非正值 {value:.6f}s——两进程的 perf_counter '
            '不同源时会出现这种结果（父进程与子进程不在同一根时钟轴上），'
            '该段按不可得处理，不写入荒谬数字。'
        )
        return None
    if value > _STARTUP_MIN_TIMEOUT:
        warnings.append(
            f'启动段 {name} 算出 {value:.3f}s，超过启动测量的硬超时 '
            f'{_STARTUP_MIN_TIMEOUT:.0f}s——量纲或回传值有误，该段按不可得处理。'
        )
        return None
    return value


def _read_startup_json(path: str, pid: Optional[int]) -> Optional[Dict[str, Any]]:
    """读冷子进程回传的启动打点 JSON（生产者是 `3f-2` 的 `main.py` 钩子）。

    四种情形分得开，**`None` 只表示「还没有/不是这次 run 的」**：

    - 文件不存在 → `None`（钩子未启用，或本次启动还没写到那一步）
    - 不是合法 JSON → `None`（可能读到了半截写入——钩子的落盘纪律是
      「先写临时文件再替换」，见 §3.11；此处不因此报错，下次轮询会重读）
    - `pid` 与本次 spawn 的子进程不符 → `None`（**防止读到另一次 run 的残留**；
      并行或重复测量时同一路径可能被上一条冷进程写过）
    - 其余 → 原样返回
    """
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding='utf-8') as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if pid is not None and payload.get('pid') not in (None, pid):
        return None
    return payload


def _read_text_file(path: str) -> str:
    """读一个可能不存在的文本文件（子进程 stderr 的落点）。

    读不到返回空串：该段随之走「未采集」告警，**不抛**——观测的收尾动作不该让
    整次测量失败（同 §3.8 D7 的方向）。
    """
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            return handle.read()
    except OSError:  # pragma: no cover - 文件由本方法自己创建
        return ''


def _tail(path: str, lines: int = 8) -> str:
    """子进程 stderr 的末尾若干行，用于把失败成因带进错误信息。"""
    text = _read_text_file(path).strip()
    if not text:
        return '（空）'
    return ' | '.join(text.splitlines()[-lines:])


def _child_has_visible_window(pid: int) -> bool:
    """本进程之外、属于 `pid` 的**可见且有标题**的顶层窗口是否已出现（第 6 段）。

    用 `EnumWindows` 而不是进程内信号：第 6 段的定义就是「用户能看见窗口了」，
    进程内信号（如 `show()` 返回）在窗口真正映射到屏幕之前就会返回。

    **必须按 pid 过滤**：`EnumWindows` 会枚举本机所有顶层窗口，不过滤就会把
    适配器自己或用户已经开着的 GachaStat 实例当成本次被测窗口（标题是通用的
    「GachaStat」，靠标题判更不可靠）。判据取「可见 + 有标题」而非比对标题字符串：
    标题可被产品改动，而「有标题的可见顶层窗口」正是「用户看得见一个窗口」。
    """
    if os.name != 'nt':  # pragma: no cover - 本项目只在 Windows 上跑
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd, _lparam):  # pragma: no cover - 回调由系统调用
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                found.append(hwnd)
                return False        # 找到一个就够了，停止枚举
        return True

    user32.EnumWindows(_callback, 0)
    return bool(found)


def _tree_cpu_seconds(pid: int) -> float:
    """整棵进程树的累计 CPU 秒数（user + system，**跨核求和**）。

    每次调用**重新枚举子进程**：Chromium 子进程是启动过程中陆续创建的，只在开头
    枚举一次会让后面创建的进程完全不计入，读数偏低；子进程中途退出则其累计时间
    随之消失，故调用方须把负的差值钳到 0。
    """
    import psutil

    try:
        root = psutil.Process(pid)
        tree = [root, *root.children(recursive=True)]
    except psutil.Error:
        return 0.0
    total = 0.0
    for item in tree:
        try:
            times = item.cpu_times()
        except psutil.Error:            # 采样间隙里退出的进程
            continue
        total += times.user + times.system
    return total


def _tree_cpu_percent(pid: int, window: float) -> Optional[float]:
    """`window` 秒内整棵进程树的 CPU 占用百分比（跨核求和）。

    与 §3.11 实测数据的口径一致（峰值 115%、空闲 1%）：**不除以核数**，故单核满载
    即 100%。缺 `psutil` 时返回 `None`——调用方跳过本次判定（第 7 段随之不可得），
    **不因此判完成**。
    """
    try:
        import psutil  # noqa: F401
    except ImportError:  # pragma: no cover - [dev] 里有
        return None
    before = _tree_cpu_seconds(pid)
    time.sleep(window)
    after = _tree_cpu_seconds(pid)
    return max(0.0, after - before) / window * 100.0


def _process_rss_mb(pid: int) -> Optional[float]:
    """**被测主进程自身**的常驻内存（MB）。读不到返回 `None`（不记 0）。

    口径取「主进程自身」而非「整棵进程树」，是为了与 §3.11 的实测数据可比——
    那条曲线记的是 368 MB / 367 MB / 412 MB，皆为**父进程**的读数；同一次运行的
    整棵树另有约 890 MB（10 个 Chromium 子进程，2026-09-22 本机实测），两者相差
    2.4 倍，混用会让新旧读数不可比而看不出成因。

    Chromium 那一份并非被忽略：它由 §3.4 规则 5 的 `gui-qt` 特例（另加 0.5 GB
    预算）覆盖。本字段若要改记整棵树，须同时改基线口径并作废旧读数（同 §3.5 对
    `return_compact` 的口径纪律），不得静默切换。
    """
    import psutil

    try:
        return psutil.Process(pid).memory_info().rss / 1024 / 1024
    except psutil.Error:
        return None

