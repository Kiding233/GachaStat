"""诊断脚本：逐步添加组件，隔离 QApplication.exec() 返回退出码 1 的来源。

用法：python scripts/diagnose_exit_code.py [test_number]
  - 不带参数：运行所有测试
  - 带数字 N：只运行测试 N

每个测试写入临时 .py 文件后通过 subprocess 执行，避免嵌套引号转义问题。
"""

import subprocess
import sys
import os
import tempfile
import time
import textwrap

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TESTS = []


def test(name: str, code: str, timeout: int = 15):
    """注册一个测试。code 是完整的 Python 脚本代码。"""
    # 自动添加项目路径
    full_code = f"""\
import sys, os
sys.path.insert(0, {PROJECT_ROOT!r})
{textwrap.dedent(code)}
"""
    TESTS.append((name, full_code, timeout))


def run_test_script(code: str, timeout: int) -> tuple[int, str, str]:
    """将代码写入临时文件，subprocess 执行，返回 (returncode, stdout, stderr)。"""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False,
                                      encoding="utf-8", dir=PROJECT_ROOT)
    try:
        tmp.write(code)
        tmp.close()
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, tmp.name],
            capture_output=True, text=True,
            timeout=timeout,
            cwd=PROJECT_ROOT,
            env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -999, "", f"TIMEOUT after {timeout}s"
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# 测试定义
# ═══════════════════════════════════════════════════════════════════════════

test(
    "T1: 裸 QApplication（无窗口，自动 quit）",
    """
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
app = QApplication(sys.argv)
QTimer.singleShot(500, app.quit)
exit_code = app.exec()
print(f"EXIT_CODE={exit_code}", flush=True)
""",
    timeout=10,
)

test(
    "T2: QApplication + Fusion 样式",
    """
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
app = QApplication(sys.argv)
app.setStyle('Fusion')
QTimer.singleShot(500, app.quit)
exit_code = app.exec()
print(f"EXIT_CODE={exit_code}", flush=True)
""",
    timeout=10,
)

test(
    "T3: Fusion + QProxyStyle (HoverColorStyle)",
    """
from PyQt6.QtWidgets import QApplication, QProxyStyle, QStyle, QStyleOptionViewItem
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtCore import QTimer

app = QApplication(sys.argv)
app.setStyle('Fusion')

class _HoverColorStyle(QProxyStyle):
    def drawControl(self, element, option, painter, widget):
        if (element == QStyle.ControlElement.CE_ItemViewItem
                and option.state & QStyle.StateFlag.State_MouseOver
                and not option.state & QStyle.StateFlag.State_Selected):
            try:
                opt = QStyleOptionViewItem(option)
                opt.palette.setColor(QPalette.ColorRole.Highlight, QColor("#d6e8f5"))
                super().drawControl(element, opt, painter, widget)
            except Exception:
                super().drawControl(element, option, painter, widget)
        else:
            super().drawControl(element, option, painter, widget)

app.setStyle(_HoverColorStyle(app.style()))
QTimer.singleShot(500, app.quit)
exit_code = app.exec()
print(f"EXIT_CODE={exit_code}", flush=True)
""",
    timeout=10,
)

test(
    "T4: Fusion + GlobalWheelBlocker（无窗口）",
    """
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
app = QApplication(sys.argv)
app.setStyle('Fusion')
from gacha_simulator.gui.wheel_blocker import GlobalWheelBlocker
app.installEventFilter(GlobalWheelBlocker(app))
QTimer.singleShot(500, app.quit)
exit_code = app.exec()
print(f"EXIT_CODE={exit_code}", flush=True)
""",
    timeout=10,
)

test(
    "T5: Fusion + MainWindow（仅创建显示 + 自动 close）",
    """
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
app = QApplication(sys.argv)
app.setStyle('Fusion')
from gacha_simulator.gui.wheel_blocker import GlobalWheelBlocker
app.installEventFilter(GlobalWheelBlocker(app))
from gacha_simulator.gui.main_window import MainWindow
window = MainWindow()
window.show()
QTimer.singleShot(2000, window.close)
exit_code = app.exec()
print(f"EXIT_CODE={exit_code}", flush=True)
""",
    timeout=25,
)

test(
    "T6: QTableWidget + setCellWidget + QSS hover（无 MainWindow）",
    """
from PyQt6.QtWidgets import (QApplication, QTableWidget, QSpinBox,
                              QDoubleSpinBox, QComboBox, QMainWindow)
from PyQt6.QtCore import QTimer
app = QApplication(sys.argv)
app.setStyle('Fusion')

class Win(QMainWindow):
    def __init__(self):
        super().__init__()
        self.table = QTableWidget(3, 2, self)
        self.setCentralWidget(self.table)
        self.table.setHorizontalHeaderLabels(["Param", "Value"])
        sb = QSpinBox()
        sb.setRange(0, 100)
        sb.setValue(50)
        self.table.setCellWidget(0, 1, sb)
        dsb = QDoubleSpinBox()
        dsb.setRange(0.0, 1.0)
        dsb.setValue(0.5)
        self.table.setCellWidget(1, 1, dsb)
        cb = QComboBox()
        cb.addItems(["A", "B", "C"])
        self.table.setCellWidget(2, 1, cb)
        self.table.setStyleSheet(
            "QTableWidget::item:hover:!selected { background-color: #d6e8f5; }"
        )
        self.resize(400, 200)

window = Win()
window.show()
QTimer.singleShot(2000, window.close)
exit_code = app.exec()
print(f"EXIT_CODE={exit_code}", flush=True)
""",
    timeout=20,
)

test(
    "T7: Fusion + ChartWebView (QtWebEngine)",
    """
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtCore import QTimer
app = QApplication(sys.argv)
app.setStyle('Fusion')

from gacha_simulator.gui.chart_webview import ChartWebView
from gacha_simulator.visualization.chart_spec import ChartSpec

window = QMainWindow()
container = QWidget()
layout = QVBoxLayout(container)
chart_view = ChartWebView()
layout.addWidget(chart_view)
window.setCentralWidget(container)
window.resize(800, 600)
window.show()

specs = [
    ChartSpec(key="test", title="Test Chart",
              figure_json='{"data":[{"y":[1,2,3],"type":"bar"}],"layout":{"title":"Test"}}')
]
QTimer.singleShot(1000, lambda: chart_view.set_charts(specs, use_tabs=False))
QTimer.singleShot(4000, window.close)
exit_code = app.exec()
print(f"EXIT_CODE={exit_code}", flush=True)
""",
    timeout=30,
)

test(
    "T8: 完整 main.py 初始化流程（自动 close，无 QMessageBox）",
    """
from multiprocessing import freeze_support
freeze_support()

from PyQt6.QtCore import Qt, QTimer
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
_QSS = (
    "QTableWidget::item:selected {"
    " background-color: #308cc6;"
    " color: white;"
    "}"
)
app.setStyleSheet(_QSS)

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
QTimer.singleShot(3000, window.close)
exit_code = app.exec()
print(f"EXIT_CODE={exit_code}", flush=True)
""",
    timeout=30,
)

test(
    "T9: 完整 main.py + closeEvent accept（模拟用户点 Yes）",
    """
from multiprocessing import freeze_support
freeze_support()

from PyQt6.QtCore import Qt, QTimer
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
_QSS = (
    "QTableWidget::item:selected {"
    " background-color: #308cc6;"
    " color: white;"
    "}"
)
app.setStyleSheet(_QSS)

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

# 覆盖 closeEvent 跳过 QMessageBox，直接 accept
def _patched_close(event):
    event.accept()
window.closeEvent = _patched_close

QTimer.singleShot(3000, window.close)
exit_code = app.exec()
print(f"EXIT_CODE={exit_code}", flush=True)
""",
    timeout=30,
)

test(
    "T10: 最小 MainWindow + ChartWebView（无 config 面板，无 wheel_blocker）",
    """
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtCore import QTimer
app = QApplication(sys.argv)
app.setStyle('Fusion')

from gacha_simulator.gui.chart_webview import ChartWebView
from gacha_simulator.visualization.chart_spec import ChartSpec

window = QMainWindow()
container = QWidget()
layout = QVBoxLayout(container)
chart_view = ChartWebView()
layout.addWidget(chart_view)
window.setCentralWidget(container)
window.resize(800, 600)
window.show()

specs = [
    ChartSpec(key="test", title="Test",
              figure_json='{"data":[{"y":[1,2,3],"type":"bar"}],"layout":{"title":"Test"}}')
]
QTimer.singleShot(1500, lambda: chart_view.set_charts(specs, use_tabs=False))
QTimer.singleShot(4000, app.quit)
exit_code = app.exec()
print(f"EXIT_CODE={exit_code}", flush=True)
""",
    timeout=30,
)

test(
    "T11: 最小 MainWindow + ChartWebView + GlobalWheelBlocker",
    """
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtCore import QTimer
app = QApplication(sys.argv)
app.setStyle('Fusion')

from gacha_simulator.gui.wheel_blocker import GlobalWheelBlocker
app.installEventFilter(GlobalWheelBlocker(app))

from gacha_simulator.gui.chart_webview import ChartWebView
from gacha_simulator.visualization.chart_spec import ChartSpec

window = QMainWindow()
container = QWidget()
layout = QVBoxLayout(container)
chart_view = ChartWebView()
layout.addWidget(chart_view)
window.setCentralWidget(container)
window.resize(800, 600)
window.show()

specs = [
    ChartSpec(key="test", title="Test",
              figure_json='{"data":[{"y":[1,2,3],"type":"bar"}],"layout":{"title":"Test"}}')
]
QTimer.singleShot(1500, lambda: chart_view.set_charts(specs, use_tabs=False))
QTimer.singleShot(4000, app.quit)
exit_code = app.exec()
print(f"EXIT_CODE={exit_code}", flush=True)
""",
    timeout=30,
)


# ═══════════════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) > 1:
        try:
            idx = int(sys.argv[1]) - 1
            name, code, timeout = TESTS[idx]
            print(f"\n{'='*60}")
            print(f"运行: {name}")
            print(f"{'='*60}")
            rc, stdout, stderr = run_test_script(code, timeout)
            print(f"\n退出码: {rc}")
            if stdout:
                print(f"stdout:\n{stdout}")
            if stderr:
                print(f"stderr:\n{stderr}")
            if rc == -999:
                print("(超时)")
        except (ValueError, IndexError):
            print(f"无效的测试编号。可用: 1-{len(TESTS)}")
            sys.exit(1)
        return

    print(f"\n{'='*60}")
    print(f"退出码诊断工具 —— 共 {len(TESTS)} 个测试")
    print(f"{'='*60}\n")

    results = []
    for i, (name, code, timeout) in enumerate(TESTS, 1):
        print(f"[{i}/{len(TESTS)}] {name} ... ", end="", flush=True)
        rc, stdout, stderr = run_test_script(code, timeout)
        results.append((name, rc, stdout, stderr))
        if rc == 0:
            print(f"✅ exit={rc}")
        elif rc == -999:
            print(f"⏰ TIMEOUT")
        else:
            print(f"❌ exit={rc}")
        if stderr:
            short_err = stderr.strip()[:400]
            if len(stderr.strip()) > 400:
                short_err += f"\n... (截断，共 {len(stderr)} 字符)"
            for line in short_err.splitlines():
                print(f"    | {line}")
        time.sleep(0.3)

    # ── 汇总 ──
    print(f"\n{'='*60}")
    print("汇总")
    print(f"{'='*60}")
    fail_count = 0
    for name, rc, stdout, stderr in results:
        if rc == 0:
            status = "✅ PASS"
        elif rc == -999:
            status = "⏰ TIMEOUT"
        else:
            status = f"❌ FAIL (exit={rc})"
            fail_count += 1
        print(f"  {status}: {name}")

    if fail_count == 0:
        print("\n🎉 所有测试通过，未发现退出码 1 来源。")
    else:
        print(f"\n⚠️  {fail_count} 个测试返回非零退出码。")


if __name__ == '__main__':
    main()
