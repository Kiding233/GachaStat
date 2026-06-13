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

    def eventFilter(self, obj, event):
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
