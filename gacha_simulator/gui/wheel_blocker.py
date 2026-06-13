"""全局滚轮过滤器——QComboBox/QAbstractSpinBox 不响应滚轮，
将事件转发给外层 ScrollArea 保持页面正常滚动。

覆盖：QComboBox / QSpinBox / QDoubleSpinBox / QDateEdit / QTimeEdit / QDateTimeEdit
"""

from PyQt6.QtCore import QObject, QEvent, QCoreApplication
from PyQt6.QtWidgets import (
    QComboBox, QAbstractSpinBox, QAbstractScrollArea,
)


class GlobalWheelBlocker(QObject):
    """安装于 QApplication，阻止目标控件响应滚轮并转发至 ScrollArea。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = True
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._deactivate)

    def _deactivate(self):
        """aboutToQuit 时停用——防止关闭阶段事件访问半销毁对象导致退出码 1。"""
        self._active = False

    def eventFilter(self, obj, event):
        # 关闭阶段：aboutToQuit 已触发或 closingDown，跳过所有事件处理
        if not self._active or QCoreApplication.closingDown():
            return False

        try:
            if event.type() != QEvent.Type.Wheel:
                return super().eventFilter(obj, event)
            if not isinstance(obj, (QComboBox, QAbstractSpinBox)):
                return super().eventFilter(obj, event)

            # 查找最近的可滚动祖先，转发事件
            parent = obj.parent()
            while parent is not None:
                if isinstance(parent, QAbstractScrollArea):
                    vp = parent.viewport()
                    if vp is not None:
                        QCoreApplication.sendEvent(vp, event)
                    break
                parent = parent.parent()

            return True  # 阻止目标控件自己处理
        except RuntimeError:
            # C++ 对象已被析构（关闭阶段极端时序）
            return False
