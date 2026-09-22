import sys
import os

this_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(this_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 关键修复：PyQt6 和 GUI 导入必须放在 __main__ 护卫内。
# Windows 上 multiprocessing 使用 spawn 模式，每个 worker 子进程都会
# 重新执行此模块的顶层代码。若 PyQt6 在顶层导入，18 个 worker 各自加载
# 整个 GUI 栈（PyQt6 C 扩展 + 所有面板 + matplotlib），浪费 3-8 秒。
# 移入 __main__ 护卫后，worker 进程 __name__ 为 'gacha_simulator.main'，
# 不会触发这些导入，仅加载轻量的 sys/os 路径配置。

# ── 启动打点（opt-in，P83 `3f-2`）────────────────────────────────────────
#
# 供性能平台的启动测量取「进程内才能观察」的那几段（§3.11 的 1 / 3 / 5 / 8）。
# **默认关闭**：只有环境变量指向一个路径时才打点，未设置时本节的每个调用点都只
# 是一次 `is not None` 判断——零文件 I/O、零 Qt 调用、零行为变化（§8.2 的成立前提）。
#
# 环境变量名与 `benchmarks/perf/adapters/gui_qt.py` 的 `STARTUP_JSON_ENV` **同名**，
# 两侧各写一份字面量：产品代码不得 import `benchmarks/`（那是开发侧资产、不进发布
# 产物），跨这条边界的东西只能靠契约名对齐。**改一处必须同时改另一处。**
#
# 为何这里可以用环境变量（§3.8 D1 否决过环境变量）：D1 针对的是**长期存活的适配器
# 进程**——在它进程内设环境变量会泄漏影响后续用例。启动打点是**一次性冷子进程**，
# 子进程即用即灭、不污染任何人，且产物是文件而非进程内状态。
_STARTUP_TIMELINE_ENV = 'GACHASTAT_STARTUP_TIMELINE'


def _probe_now():
    """打点用的时钟。

    与父进程**同源**：Windows 上 `perf_counter()` 走 QPC（系统级、非进程级），
    故父进程可以直接把它与自己记下的时刻相减。换平台后该前提须重新验证——
    消费侧有一条合理性检查会在不同源时判该段不可得，而不是写进一个荒谬数字。
    """
    import time

    return time.perf_counter()


def _probe_write(path, payload):
    """把打点写成 JSON。

    **先写临时文件再原子替换**：读方（父进程）在轮询同一个路径，直接覆写会让它
    有机会读到半截文件。

    **落盘时机是硬要求**（§3.11）：本函数在段 5 记录完成后**立即**被调用，flush 与
    `fsync` 都做掉。**不得**推迟到事件循环退出、窗口关闭或收尾清理阶段——本文件
    的收尾是 `os._exit()`，它绕过缓冲区刷新与 `atexit`，推迟就等于永远写不出来。

    **任何异常一律吞掉**：打点失败不得改变退出码、不得让产品行为发生变化；后果只是
    没有 JSON，父进程按软降级口径逐段标注「本段不可得」。
    """
    try:
        import json
        import os

        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        pass


def _probe_install_charts_ready(window, payload, path):
    """段 8「图表可用」：轮询 `MainWindow.charts_ready()`，就绪后回写打点文件。

    **判据是连续 3 次（间隔 200ms）都就绪**，不是「某次取到 True」——`ChartWebView`
    的 `closeEvent` 会把就绪状态置回 `False`，单次取值不足以当完成（§3.11 第 8 段
    的第 3 条）。

    观察只能落在被测进程自己身上：就绪状态是**本进程内的对象状态**，父进程无法对它
    做方法调用，而规则 9 又要求冷进程——故父进程是消费者、本函数是生产者。

    读取异常时**记下成因并停表**（不重试）：八处只读访问器是本平台最新、最脆的一环，
    「一直不就绪」与「访问器坏了」是两件事，父进程据此区分。
    """
    try:
        from PyQt6.QtCore import QTimer
    except Exception:  # pragma: no cover - PyQt6 已在本文件上方导入成功才会走到这
        return

    state = {'streak': 0, 'timer': None}

    def _tick():
        try:
            ready = bool(window.charts_ready())
        except Exception as exc:
            payload['charts_ready_error'] = f'{type(exc).__name__}: {exc}'
            if state['timer'] is not None:
                state['timer'].stop()
            _probe_write(path, payload)
            return
        state['streak'] = state['streak'] + 1 if ready else 0
        if state['streak'] < 3:
            return
        if state['timer'] is not None:
            state['timer'].stop()
        payload['charts_ready'] = _probe_now()
        _probe_write(path, payload)

    # **必须给 parent**（`QTimer(window)`），不能只把引用存进局部/闭包：定时器与
    # 回调之间只有一条「state ← _tick 的闭包 ← 信号连接 ← timer ← state」的**环**，
    # 没有外部根可达，Python 的 gc 可以整个回收掉它——回收了就不再有 tick，而**表
    # 面上没有任何错误**（实测踩到：段 8 永不出现、父进程等满宽限后报「该段未采集」）。
    # 交给 Qt 持有（parent = 窗口）后生命周期与窗口一致。
    timer = QTimer(window)
    timer.timeout.connect(_tick)
    timer.start(200)
    state['timer'] = timer


if __name__ == '__main__':
    # 段 1 的锚点：这一行就是「脚本首行」，与父进程的 spawn 时刻相减即解释器启动耗时。
    # 未设置打点环境变量时 `_probe` 恒为 None，下面每个打点都是一次布尔判断。
    _probe_path = os.environ.get(_STARTUP_TIMELINE_ENV) or ''
    _probe = {'pid': os.getpid(), 'origin': _probe_now()} if _probe_path else None

    # os._exit 绕过 C++ 析构会触发 Qt 内部清理警告
    # （QDxgiVSyncService / QThreadStorage），抑制之。
    os.environ.setdefault('QT_LOGGING_RULES', '*.warning=false')

    # Windows spawn 模式 + PyInstaller 打包的必要调用
    from multiprocessing import freeze_support
    freeze_support()

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QIcon
    from gacha_simulator.gui import MainWindow
    from gacha_simulator._version import __version__

    from gacha_simulator.paths import get_resource
    _ICON_PATH = get_resource('app_icon.png')

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    if _probe is not None:
        _probe['app_construct_start'] = _probe_now()          # 段 3 起
    app = QApplication(sys.argv)
    if _probe is not None:
        _probe['app_construct_end'] = _probe_now()            # 段 3 止
    from gacha_simulator.gui.wheel_blocker import GlobalWheelBlocker
    app.installEventFilter(GlobalWheelBlocker(app))
    app.setApplicationName("GachaStat")
    app.setOrganizationName("GachaStat")
    app.setApplicationVersion(__version__)
    app.setStyleSheet("""
        QTableWidget::item:selected {
            background-color: #308cc6;
            color: white;
        }
    """)

    # 替代 QSS :hover —— QProxyStyle 覆写 Fusion 的 hover 绘制色，
    # 用淡蓝 #d6e8f5 替代默认的深蓝（与选中同色），且不触发 Qt 6.11 的
    # hover→FocusIn bug（QSS :hover 伪类才会触发，纯 Style 绘制不触发）。
    from PyQt6.QtWidgets import QProxyStyle, QStyle, QStyleOptionViewItem
    from PyQt6.QtGui import QColor as _QColor, QPalette as _QPalette

    class _HoverColorStyle(QProxyStyle):
        def drawControl(self, element, option, painter, widget):
            if (element == QStyle.ControlElement.CE_ItemViewItem
                    and option.state & QStyle.StateFlag.State_MouseOver
                    and not option.state & QStyle.StateFlag.State_Selected):
                try:
                    opt = QStyleOptionViewItem(option)
                    opt.palette.setColor(_QPalette.ColorRole.Highlight,
                                         _QColor("#d6e8f5"))
                    super().drawControl(element, opt, painter, widget)
                except Exception:
                    super().drawControl(element, option, painter, widget)
            else:
                super().drawControl(element, option, painter, widget)

    _base_style = app.style()
    _hover_style = _HoverColorStyle(_base_style)
    app.setStyle(_hover_style)

    if os.path.exists(_ICON_PATH):
        app.setWindowIcon(QIcon(_ICON_PATH))

    # ── 启动时清理上一次运行的残留（孤儿子进程 + 临时文件）──
    # 必须在 MainWindow() 创建之前执行——ChartWebView._preload() 会在构造期
    # 写入临时 HTML 文件，若清理在此之后执行会误删当次会话的文件，导致
    # 所有图表 WebEngine 加载失败（loadFinished ok=False）。
    import subprocess as _subprocess
    _my_pid = os.getpid()

    # 清理 os._exit 绕过 atexit 导致的残留临时目录
    try:
        import shutil as _shutil
        import tempfile as _tempfile
        _tmp_root = _tempfile.gettempdir()
        for _name in os.listdir(_tmp_root):
            if _name.startswith('gachastat_charts_'):
                _path = os.path.join(_tmp_root, _name)
                if os.path.isdir(_path):
                    _shutil.rmtree(_path, ignore_errors=True)
    except Exception:
        pass

    try:
        # 查找所有 python.exe / QtWebEngineProcess.exe 中可能残留的孤儿
        _orphans = _subprocess.run(
            ["wmic", "process", "where",
             "Name='QtWebEngineProcess.exe' or Name='python.exe'",
             "get", "ProcessId,ParentProcessId"],
            capture_output=True, text=True, timeout=5,
        )
        import signal as _signal
        for line in _orphans.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                try:
                    pid, ppid = int(parts[-1]), int(parts[-2])
                except ValueError:
                    continue
                # 父进程是当前进程、或父进程已不存在(PPID=1)、或父进程是
                # 非当前终端进程 — 都视为孤儿子进程
                if pid == _my_pid:
                    continue
                if ppid == _my_pid or ppid == 1:
                    try:
                        os.kill(pid, _signal.SIGTERM)
                    except OSError:
                        pass
    except Exception:
        pass

    if _probe is not None:
        _probe['window_construct_start'] = _probe_now()       # 段 5 起
    window = MainWindow()
    if _probe is not None:
        _probe['window_construct_end'] = _probe_now()         # 段 5 止
        # **立即落盘**（§3.11 的 flush 纪律）：本文件收尾是 os._exit()，它绕过缓冲区
        # 刷新与 atexit——推迟到事件循环退出或窗口关闭就等于永远写不出来。
        _probe_write(_probe_path, _probe)
        # 段 8 起表：就绪状态只能在本进程内观察，故轮询装在这里而非父进程。
        _probe_install_charts_ready(window, _probe, _probe_path)
    window.show()

    # ── Ps03：Ctrl+R 重启快捷键（开发调试用）──
    restart_pid = None

    def _on_restart_requested():
        """重启：保存配置 → 启动新进程 → 探测 → 记录 pid → 关闭旧进程。

        新进程作为本进程子进程启动，退出清理（下方）需跳过 restart_pid，否则误杀。
        任一失败路径都 cancel_restart() 复位防抖并保持旧进程，避免「改错一行应用就没了」。
        """
        global restart_pid
        from PyQt6.QtWidgets import QMessageBox
        try:
            # 保存序列复用 export_config（main_window.py L266-290）：校验 → 应用 → 写盘
            errors = window.config_panel.validate_banners()
            if errors:
                QMessageBox.warning(
                    window, "配置校验失败",
                    "以下问题需修正后才能重启：\n\n" + '\n'.join(f"  · {e}" for e in errors))
                window.cancel_restart()
                return
            window.config_panel.apply_to_store()
            from gacha_simulator.core.config_toml import save_toml
            from gacha_simulator.paths import get_config_dir
            save_toml(window._store, os.path.join(get_config_dir(), 'config.toml'))
        except Exception:
            window.cancel_restart()
            return

        # 启动新进程（cwd 必须是含 gacha_simulator 包的目录，否则 -m 失败）
        try:
            if getattr(sys, 'frozen', False):
                proc = _subprocess.Popen([sys.executable])
            else:
                proc = _subprocess.Popen(
                    [sys.executable, '-m', 'gacha_simulator.main'], cwd=parent_dir)
        except Exception as e:
            QMessageBox.warning(window, "重启失败", f"无法启动新进程：{e}")
            window.cancel_restart()
            return

        # 启动探测：语法/导入错误通常在导入早期秒崩，poll() 判定后取消重启
        import time as _time
        _time.sleep(0.8)
        if proc.poll() is not None:
            QMessageBox.warning(
                window, "重启失败",
                "新进程启动即退出，可能代码存在语法/导入错误（检查终端报错）。已保留当前窗口。")
            window.cancel_restart()
            return

        restart_pid = proc.pid
        window.close()

    window.restart_requested.connect(_on_restart_requested)

    _exit_code = app.exec()

    # 退出前杀掉所有子进程，然后 os._exit 绕过 C++ 析构阶段。
    # C++ 析构时 widget 树清理可能将事件派发至 GlobalWheelBlocker，
    # 此时 obj.parent() 链已部分析构，触发 Qt 内部非零退出码。
    try:
        result = _subprocess.run(
            ["wmic", "process", "where",
             f"ParentProcessId={_my_pid}",
             "get", "ProcessId"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit() and int(line) != _my_pid:
                # Ps03：跳过重启启动的新进程，否则误杀刚启动的实例
                if int(line) == restart_pid:
                    continue
                try:
                    os.kill(int(line), _signal.SIGTERM)
                except OSError:
                    pass
    except Exception:
        pass

    os._exit(_exit_code)
