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

if __name__ == '__main__':
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
    app = QApplication(sys.argv)
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
    window = MainWindow()
    window.show()

    # ── 启动时清理上一次运行的残留（孤儿子进程 + 临时文件）──
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
                try:
                    os.kill(int(line), _signal.SIGTERM)
                except OSError:
                    pass
    except Exception:
        pass

    os._exit(_exit_code)
