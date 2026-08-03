"""插件管理面板——QDialog，管理策略插件的启用/禁用/重新扫描。

P69 阶段 4a：从「工具 → 插件管理」菜单触发。
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QMessageBox, QTextEdit, QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal


class PluginManagerDialog(QDialog):
    """插件管理对话框——模态窗口。

    构造函数接收 MainWindow 作为 parent，通过 parent.config_panel
    获取配置面板引用以刷新下拉框。
    """

    # 关闭时发出，携带是否有变更的标志
    finished = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_window = parent
        self._has_changes = False
        self._setup_ui()
        self._refresh_table()

    def _setup_ui(self):
        self.setWindowTitle("插件管理")
        self.setMinimumSize(700, 500)
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        # ── 顶部说明 ──
        hint = QLabel(
            "策略插件放在 strategies/ 目录下即可被自动发现。\n"
            "禁用插件后需重新扫描才能恢复。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── 表格 ──
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["插件名称", "Key", "状态", "文件路径"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        # ── 错误详情（底部可折叠区域） ──
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._table)

        error_widget = QVBoxLayout()
        error_label = QLabel("错误详情:")
        self._error_text = QTextEdit()
        self._error_text.setReadOnly(True)
        self._error_text.setMaximumHeight(120)
        self._error_text.setPlaceholderText("选择加载失败的插件以查看错误详情...")
        error_widget.addWidget(error_label)
        error_widget.addWidget(self._error_text)

        from PyQt6.QtWidgets import QWidget
        error_container = QWidget()
        error_container.setLayout(error_widget)
        splitter.addWidget(error_container)
        splitter.setSizes([350, 150])
        layout.addWidget(splitter)

        # ── 按钮行 ──
        btn_layout = QHBoxLayout()

        self._enable_btn = QPushButton("启用")
        self._enable_btn.clicked.connect(self._on_enable)
        self._enable_btn.setEnabled(False)

        self._disable_btn = QPushButton("禁用")
        self._disable_btn.clicked.connect(self._on_disable)
        self._disable_btn.setEnabled(False)

        rescan_btn = QPushButton("重新扫描")
        rescan_btn.clicked.connect(self._on_rescan)
        rescan_btn.setToolTip(
            "重新扫描 strategies/ 目录。已运行的模拟持有旧策略实例，不受影响。"
        )

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self._on_close)

        btn_layout.addWidget(self._enable_btn)
        btn_layout.addWidget(self._disable_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(rescan_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _refresh_table(self):
        """从 STRATEGY_REGISTRY 刷新表格——仅展示非 internal 的条目。"""
        from gacha_simulator.core.strategy import STRATEGY_REGISTRY

        self._table.setRowCount(0)
        self._meta_order = []  # 行索引 → StrategyMeta

        for key, meta in sorted(STRATEGY_REGISTRY.items()):
            if meta.internal:
                continue

            row = self._table.rowCount()
            self._table.insertRow(row)
            self._meta_order.append(meta)

            # 插件名称
            self._table.setItem(row, 0, QTableWidgetItem(meta.display_name))
            # Key
            self._table.setItem(row, 1, QTableWidgetItem(key))

            # 状态
            if meta._invalid_state:
                status = "加载失败"
            elif meta.disabled:
                status = "已禁用"
            else:
                status = "启用"
            self._table.setItem(row, 2, QTableWidgetItem(status))

            # 文件路径
            path = meta.plugin_path or "内置策略"
            self._table.setItem(row, 3, QTableWidgetItem(path))

        self._update_button_states()

    def _on_selection_changed(self):
        """选择变更时更新按钮状态和错误详情。"""
        self._update_button_states()
        self._update_error_detail()

    def _update_button_states(self):
        """根据当前选中行更新启用/禁用按钮。"""
        selected = self._table.currentRow()
        if selected < 0 or selected >= len(self._meta_order):
            self._enable_btn.setEnabled(False)
            self._disable_btn.setEnabled(False)
            return

        meta = self._meta_order[selected]
        is_error = meta._invalid_state is not None
        is_builtin = meta.plugin_path is None

        self._enable_btn.setEnabled(meta.disabled and not is_error)
        self._disable_btn.setEnabled(not meta.disabled and not is_error and not is_builtin)

    def _update_error_detail(self):
        """更新错误详情文本框。"""
        selected = self._table.currentRow()
        if selected < 0 or selected >= len(self._meta_order):
            self._error_text.clear()
            return

        meta = self._meta_order[selected]
        if meta._invalid_state:
            self._error_text.setPlainText(meta._invalid_state)
        else:
            self._error_text.clear()

    def _on_enable(self):
        """启用选中的插件。"""
        selected = self._table.currentRow()
        if selected < 0 or selected >= len(self._meta_order):
            return

        meta = self._meta_order[selected]
        meta.disabled = False
        self._has_changes = True
        self._refresh_table()
        self._table.selectRow(selected)
        self._rebuild_config_dropdown()

    def _on_disable(self):
        """禁用选中的插件。"""
        selected = self._table.currentRow()
        if selected < 0 or selected >= len(self._meta_order):
            return

        meta = self._meta_order[selected]
        if meta.plugin_path is None:
            return  # 不能禁用内置策略

        meta.disabled = True
        self._has_changes = True
        self._refresh_table()
        self._table.selectRow(selected)
        self._rebuild_config_dropdown()

    def _on_rescan(self):
        """重新扫描 strategies/ 目录。"""
        from gacha_simulator.core.strategy_loader import load_plugin_strategies

        count = load_plugin_strategies()
        self._has_changes = True
        self._refresh_table()

        if count == 0:
            QMessageBox.information(self, "扫描完成", "未发现新的插件文件。")
        else:
            QMessageBox.information(self, "扫描完成", f"成功加载 {count} 个插件。")

    def _rebuild_config_dropdown(self):
        """通知主窗口的配置面板刷新策略下拉框。"""
        if self._main_window and hasattr(self._main_window, 'config_panel'):
            self._main_window.config_panel._rebuild_strategy_dropdown()

    def _on_close(self):
        """关闭对话框。"""
        self.finished.emit(self._has_changes)
        self.accept()
