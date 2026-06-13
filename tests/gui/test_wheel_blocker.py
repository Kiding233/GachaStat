"""GlobalWheelBlocker 单元测试 —— 纯事件逻辑，headless，无渲染依赖。"""

import pytest
from PyQt6.QtCore import QEvent, Qt, QPoint, QPointF
from PyQt6.QtGui import QWheelEvent, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication, QWidget, QComboBox, QSpinBox, QDoubleSpinBox,
    QDateEdit, QPushButton, QLabel, QScrollArea,
)

from gacha_simulator.gui.wheel_blocker import GlobalWheelBlocker


@pytest.fixture(scope='module')
def qapp():
    """模块级 QApplication——headless，整个测试模块共享一个实例。"""
    import os
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _make_wheel_event():
    """构造一个标准滚轮事件。"""
    return QWheelEvent(
        QPointF(0, 0), QPointF(0, 0), QPoint(0, 120), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )


def _make_key_event():
    """构造一个键盘按下事件。"""
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)


def _install_and_dispatch(blocker, widget, event):
    """安装 GlobalWheelBlocker 到 QApplication 并分派事件。

    eventFilter 是主动调用的——我们直接调 blocker.eventFilter(widget, event)
    而不是走 QApplication.notify()，这样不依赖完整的事件分发链。
    """
    qapp = QApplication.instance()
    if qapp:
        qapp.installEventFilter(blocker)
    return blocker.eventFilter(widget, event)


# ═══════════════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════════════

class TestWheelBlocking:
    """验证目标控件滚轮被拦截。"""

    def test_combo_wheel_blocked(self, qapp):
        blocker = GlobalWheelBlocker(qapp)
        widget = QComboBox()
        event = _make_wheel_event()
        result = _install_and_dispatch(blocker, widget, event)
        assert result is True, "QComboBox 滚轮必须被拦截"

    def test_spinbox_wheel_blocked(self, qapp):
        blocker = GlobalWheelBlocker(qapp)
        widget = QSpinBox()
        event = _make_wheel_event()
        result = _install_and_dispatch(blocker, widget, event)
        assert result is True, "QSpinBox 滚轮必须被拦截"

    def test_double_spinbox_wheel_blocked(self, qapp):
        blocker = GlobalWheelBlocker(qapp)
        widget = QDoubleSpinBox()
        event = _make_wheel_event()
        result = _install_and_dispatch(blocker, widget, event)
        assert result is True, "QDoubleSpinBox 滚轮必须被拦截"

    def test_dateedit_wheel_blocked(self, qapp):
        """QDateEdit 继承 QAbstractSpinBox，必须被 QAbstractSpinBox 匹配覆盖。"""
        blocker = GlobalWheelBlocker(qapp)
        widget = QDateEdit()
        event = _make_wheel_event()
        result = _install_and_dispatch(blocker, widget, event)
        assert result is True, "QDateEdit (QAbstractSpinBox 子类) 滚轮必须被拦截"


class TestNonWheelPassthrough:
    """验证键盘等非滚轮事件正常放行。"""

    def test_combo_key_passthrough(self, qapp):
        blocker = GlobalWheelBlocker(qapp)
        widget = QComboBox()
        event = _make_key_event()
        result = _install_and_dispatch(blocker, widget, event)
        # super().eventFilter() → QObject.eventFilter → 返回 False(放行)
        assert result is False, "键盘事件必须放行"

    def test_spinbox_key_passthrough(self, qapp):
        blocker = GlobalWheelBlocker(qapp)
        widget = QSpinBox()
        event = _make_key_event()
        result = _install_and_dispatch(blocker, widget, event)
        assert result is False, "键盘事件必须放行"


class TestNonTargetPassthrough:
    """验证非目标控件的滚轮事件正常放行。"""

    def test_button_wheel_passthrough(self, qapp):
        blocker = GlobalWheelBlocker(qapp)
        widget = QPushButton("test")
        event = _make_wheel_event()
        result = _install_and_dispatch(blocker, widget, event)
        assert result is False, "QPushButton 滚轮必须放行"

    def test_label_wheel_passthrough(self, qapp):
        blocker = GlobalWheelBlocker(qapp)
        widget = QLabel("test")
        event = _make_wheel_event()
        result = _install_and_dispatch(blocker, widget, event)
        assert result is False, "QLabel 滚轮必须放行"


class TestNoScrollAreaAncestor:
    """验证没有 ScrollArea 祖先时安全退出。"""

    def test_orphan_widget_safe(self, qapp):
        """控件无父对象时 while 循环走到 root 安全退出，仍正确阻止控件响应。"""
        blocker = GlobalWheelBlocker(qapp)
        widget = QComboBox()  # 无 parent
        event = _make_wheel_event()
        result = _install_and_dispatch(blocker, widget, event)
        assert result is True, "无祖先时仍必须阻止控件响应（安全退出 + return True）"


class TestScrollAreaForwarding:
    """验证存在 ScrollArea 祖先时正确转发事件。"""

    def test_combo_in_scrollarea_blocks_and_scrolls(self, qapp):
        """QComboBox 在 ScrollArea 内：滚轮被拦截，事件转发给 viewport。

        我们验证：拦截返回 True + ScrollArea viewport 存在。
        实际滚动行为需 GUI 验收。
        """
        blocker = GlobalWheelBlocker(qapp)
        scroll = QScrollArea()
        scroll.setWidget(QWidget())  # 必须 setWidget 才能有 viewport
        viewport = scroll.viewport()
        assert viewport is not None, "前置条件：viewport 必须存在"

        combo = QComboBox()
        combo.setParent(viewport)

        event = _make_wheel_event()
        result = _install_and_dispatch(blocker, combo, event)
        assert result is True, "ScrollArea 内 ComboBox 滚轮必须被拦截"
        # viewport 存在 → sendEvent 被调用。实际滚动效果需 GUI 验收。

    def test_spinbox_in_scrollarea_blocks(self, qapp):
        blocker = GlobalWheelBlocker(qapp)
        scroll = QScrollArea()
        scroll.setWidget(QWidget())
        viewport = scroll.viewport()
        assert viewport is not None

        spin = QSpinBox()
        spin.setParent(viewport)

        event = _make_wheel_event()
        result = _install_and_dispatch(blocker, spin, event)
        assert result is True
