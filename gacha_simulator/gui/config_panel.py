#!/usr/bin/env python3
"""配置面板"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QLabel, QCheckBox, QScrollArea, QSplitter,
    QListWidget, QDialog, QDialogButtonBox, QMessageBox, QAbstractItemView,
    QDateEdit, QCalendarWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QTimer
from PyQt6.QtGui import QFont, QColor

from ..core.config_store import (
    CardDefEntry, PoolEntry, PoolDistEntry,
    PityDef, PityConfig, GainRule, DayOverride, TargetCardEntry, CardWeightEntry,
)
from ..core.overflow import OverflowBand
from ..core.pity import BEHAVIOR_REGISTRY


class PoolDistributionDialog(QDialog):
    def __init__(self, pool_id, distribution_data, parent=None):
        super().__init__(parent)
        self.pool_id = pool_id
        self.setWindowTitle(f"编辑池子分布 - {pool_id}")
        self.setMinimumSize(900, 400)

        layout = QVBoxLayout(self)

        self.dist_table = QTableWidget()
        self.dist_table.setColumnCount(5)
        self.dist_table.setHorizontalHeaderLabels(["卡ID", "概率(%)", "稀有度", "Featured", "资源获取"])
        self.dist_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.dist_table.verticalHeader().setVisible(False)
        self.dist_table.setAlternatingRowColors(True)
        self.dist_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.dist_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.dist_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.dist_table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加")
        add_btn.clicked.connect(self._add_row)
        remove_btn = QPushButton("移除选中")
        remove_btn.clicked.connect(self._remove_row)
        no_card_btn = QPushButton("添加空抽(仅资源)")
        no_card_btn.clicked.connect(self._add_no_card_row)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addWidget(no_card_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        bottom_layout = QHBoxLayout()
        self.total_label = QLabel("概率合计: 0.000%")
        bottom_layout.addWidget(self.total_label)

        default_btn = QPushButton("默认3卡")
        default_btn.clicked.connect(self._set_default)
        bottom_layout.addWidget(default_btn)
        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._try_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._populate(distribution_data)

    def _populate(self, data):
        self.dist_table.setRowCount(len(data))
        for i, d in enumerate(data):
            card_id = d.get('card_id', '')
            card_id_item = QTableWidgetItem(card_id)
            if card_id == '_no_card':
                card_id_item.setFlags(card_id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                card_id_item.setBackground(QColor(220, 220, 220))
            self.dist_table.setItem(i, 0, card_id_item)

            prob_spin = QDoubleSpinBox()
            prob_spin.setRange(0.000, 100.000)
            prob_spin.setDecimals(3)
            prob_spin.setValue(d.get('probability', 0.0))
            prob_spin.valueChanged.connect(self._update_total)
            self.dist_table.setCellWidget(i, 1, prob_spin)

            rarity_combo = QComboBox()
            rarity_combo.addItems(["SSR", "SR", "R", "无"])
            rarity = d.get('rarity', 'R').lower()
            rarity_map = {o.lower(): i for i, o in enumerate(["SSR", "SR", "R", "无"])}
            idx = rarity_map.get(rarity, 2)
            rarity_combo.setCurrentIndex(idx)
            self.dist_table.setCellWidget(i, 2, rarity_combo)

            featured_cb = QCheckBox()
            featured_cb.setChecked(d.get('featured', False))
            if d.get('card_id', '') == '_no_card':
                featured_cb.setChecked(False)
                featured_cb.setEnabled(False)
            self.dist_table.setCellWidget(i, 3, featured_cb)

            resources_gained = d.get('resources_gained', {})
            res_text = ','.join(f'{k}:{v}' for k, v in resources_gained.items()) if resources_gained else ''
            res_edit = QLineEdit(res_text)
            res_edit.setPlaceholderText("resource_id:amount,...")
            self.dist_table.setCellWidget(i, 4, res_edit)

        self._update_total()

    def _add_row(self):
        row = self.dist_table.rowCount()
        self.dist_table.insertRow(row)
        self.dist_table.setItem(row, 0, QTableWidgetItem(f"{self.pool_id}_new"))

        prob_spin = QDoubleSpinBox()
        prob_spin.setRange(0.000, 100.000)
        prob_spin.setDecimals(3)
        prob_spin.setValue(0.0)
        prob_spin.valueChanged.connect(self._update_total)
        self.dist_table.setCellWidget(row, 1, prob_spin)

        rarity_combo = QComboBox()
        rarity_combo.addItems(["SSR", "SR", "R", "无"])
        self.dist_table.setCellWidget(row, 2, rarity_combo)

        featured_cb = QCheckBox()
        self.dist_table.setCellWidget(row, 3, featured_cb)

        res_edit = QLineEdit()
        res_edit.setPlaceholderText("resource_id:amount,...")
        self.dist_table.setCellWidget(row, 4, res_edit)

        self._update_total()

    def _add_no_card_row(self):
        row = self.dist_table.rowCount()
        self.dist_table.insertRow(row)
        card_id_item = QTableWidgetItem("_no_card")
        card_id_item.setFlags(card_id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        card_id_item.setBackground(QColor(220, 220, 220))
        self.dist_table.setItem(row, 0, card_id_item)

        prob_spin = QDoubleSpinBox()
        prob_spin.setRange(0.000, 100.000)
        prob_spin.setDecimals(3)
        prob_spin.setValue(0.0)
        prob_spin.valueChanged.connect(self._update_total)
        self.dist_table.setCellWidget(row, 1, prob_spin)

        rarity_combo = QComboBox()
        rarity_combo.addItems(["SSR", "SR", "R", "无"])
        rarity_combo.setCurrentIndex(3)
        self.dist_table.setCellWidget(row, 2, rarity_combo)

        featured_cb = QCheckBox()
        featured_cb.setChecked(False)
        featured_cb.setEnabled(False)
        self.dist_table.setCellWidget(row, 3, featured_cb)

        res_edit = QLineEdit()
        res_edit.setPlaceholderText("resource_id:amount,...")
        self.dist_table.setCellWidget(row, 4, res_edit)

        self._update_total()

    def _remove_row(self):
        rows = sorted([r.row() for r in self.dist_table.selectionModel().selectedRows()], reverse=True)
        for row in rows:
            self.dist_table.removeRow(row)
        self._update_total()

    def _update_total(self):
        total = 0.0
        for i in range(self.dist_table.rowCount()):
            spin = self.dist_table.cellWidget(i, 1)
            if spin:
                total += spin.value()

        if abs(total - 100.0) < 0.1:
            self.total_label.setText(f"概率合计: {total:.3f}%")
            self.total_label.setStyleSheet("")
        else:
            self.total_label.setText(f"概率合计: {total:.3f}%")
            self.total_label.setStyleSheet("color: red;")

    def _set_default(self):
        data = [
            {'card_id': f'{self.pool_id}_ssr', 'probability': 0.6, 'rarity': 'SSR', 'featured': True, 'resources_gained': {'exchange_currency': 5}},
            {'card_id': f'{self.pool_id}_sr', 'probability': 5.1, 'rarity': 'SR', 'featured': False},
            {'card_id': f'{self.pool_id}_r', 'probability': 94.3, 'rarity': 'R', 'featured': False},
        ]
        self._populate(data)

    def _try_accept(self):
        total = 0.0
        for i in range(self.dist_table.rowCount()):
            spin = self.dist_table.cellWidget(i, 1)
            if spin:
                total += spin.value()

        if total < 99.9 or total > 100.1:
            QMessageBox.warning(self, "概率错误", f"概率合计为 {total:.3f}%，必须接近100%")
            return

        self.accept()

    def get_distribution(self):
        result = []
        for i in range(self.dist_table.rowCount()):
            card_id_item = self.dist_table.item(i, 0)
            prob_spin = self.dist_table.cellWidget(i, 1)
            rarity_combo = self.dist_table.cellWidget(i, 2)
            featured_cb = self.dist_table.cellWidget(i, 3)
            res_edit = self.dist_table.cellWidget(i, 4)

            card_id = card_id_item.text().strip() if card_id_item else ''

            resources_gained = {}
            if res_edit:
                res_text = res_edit.text().strip()
                if res_text:
                    for part in res_text.split(','):
                        part = part.strip()
                        if ':' in part:
                            rid, amt = part.split(':', 1)
                            try:
                                resources_gained[rid.strip()] = float(amt.strip())
                            except ValueError:
                                pass

            rarity = rarity_combo.currentText() if rarity_combo else 'R'
            featured = featured_cb.isChecked() if featured_cb else False
            if card_id == '_no_card':
                rarity = '无'
                featured = False

            result.append({
                'card_id': card_id,
                'probability': prob_spin.value() if prob_spin else 0.0,
                'rarity': rarity,
                'featured': featured,
                'resources_gained': resources_gained,
            })
        return result


class ConfigPanel(QWidget):

    config_changed = pyqtSignal(dict)

    @staticmethod
    def _infer_pool_type(pool_id, pool_type, note=''):
        if pool_type and pool_type not in ('角色', ''):
            return pool_type
        pid = pool_id.lower()
        if pid.startswith('pool_w') or '武器' in pid or 'weapon' in pid:
            return '武器'
        if pid.startswith('pool_e') or '兑换' in pid or 'exchange' in pid:
            return '兑换'
        if '复刻' in note:
            return '复刻'
        return pool_type or '角色'

    @staticmethod
    def _pool_row_bg(pool_type, note=''):
        if pool_type == '兑换':
            return QColor(255, 245, 220)
        if pool_type == '武器':
            return QColor(220, 240, 255)
        if pool_type == '复刻' or '复刻' in note:
            return QColor(240, 255, 240)
        return None

    def __init__(self):
        super().__init__()
        self._store = None
        self._refreshing = False
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(500)
        self._preview_timer.timeout.connect(self._do_update_preview)
        self._setup_ui()
        self._set_defaults()

    def set_store(self, store):
        self._store = store

    def get_store(self):
        return self._store

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        self.left_tabs = QTabWidget()

        card_def_tab = QWidget()
        self._setup_card_def_tab(card_def_tab)
        self.left_tabs.addTab(card_def_tab, "卡牌定义")

        resource_tab_scroll = QScrollArea()
        resource_tab_scroll.verticalScrollBar().setSingleStep(15)
        resource_tab_scroll.setWidgetResizable(True)
        resource_tab_content = QWidget()
        resource_tab_layout = QVBoxLayout(resource_tab_content)
        self._setup_resource_tab(resource_tab_layout)
        resource_tab_scroll.setWidget(resource_tab_content)
        self.left_tabs.addTab(resource_tab_scroll, "资源管理")

        pool_tab_scroll = QScrollArea()
        pool_tab_scroll.verticalScrollBar().setSingleStep(15)
        pool_tab_scroll.setWidgetResizable(True)
        pool_tab_content = QWidget()
        pool_tab_layout = QVBoxLayout(pool_tab_content)
        self._setup_pool_config(pool_tab_layout)
        pool_tab_layout.addStretch()
        pool_tab_scroll.setWidget(pool_tab_content)
        self.left_tabs.addTab(pool_tab_scroll, "卡池配置")

        pity_tab_scroll = QScrollArea()
        pity_tab_scroll.verticalScrollBar().setSingleStep(15)
        pity_tab_scroll.setWidgetResizable(True)
        pity_tab_content = QWidget()
        pity_tab_layout = QVBoxLayout(pity_tab_content)
        self._setup_pity_config(pity_tab_layout)
        pity_tab_layout.addStretch()
        pity_tab_scroll.setWidget(pity_tab_content)
        self.left_tabs.addTab(pity_tab_scroll, "保底机制")

        strategy_tab_scroll = QScrollArea()
        strategy_tab_scroll.verticalScrollBar().setSingleStep(15)
        strategy_tab_scroll.setWidgetResizable(True)
        strategy_tab_content = QWidget()
        strategy_tab_layout = QVBoxLayout(strategy_tab_content)
        self._setup_strategy_tab(strategy_tab_layout)
        strategy_tab_layout.addStretch()
        strategy_tab_scroll.setWidget(strategy_tab_content)
        self.left_tabs.addTab(strategy_tab_scroll, "抽卡策略")

        target_tab_scroll = QScrollArea()
        target_tab_scroll.verticalScrollBar().setSingleStep(15)
        target_tab_scroll.setWidgetResizable(True)
        target_tab_content = QWidget()
        target_tab_layout = QVBoxLayout(target_tab_content)
        self._setup_target_tab(target_tab_layout)
        target_tab_layout.addStretch()
        target_tab_scroll.setWidget(target_tab_content)
        self.left_tabs.addTab(target_tab_scroll, "目标卡")

        weight_tab_scroll = QScrollArea()
        weight_tab_scroll.verticalScrollBar().setSingleStep(15)
        weight_tab_scroll.setWidgetResizable(True)
        weight_tab_content = QWidget()
        weight_tab_layout = QVBoxLayout(weight_tab_content)
        self._setup_weight_config(weight_tab_layout)
        weight_tab_layout.addStretch()
        weight_tab_scroll.setWidget(weight_tab_content)
        self.left_tabs.addTab(weight_tab_scroll, "权重配置")

        # P63：满突溢出标签页
        overflow_tab_scroll = QScrollArea()
        overflow_tab_scroll.verticalScrollBar().setSingleStep(15)
        overflow_tab_scroll.setWidgetResizable(True)
        overflow_tab_content = QWidget()
        overflow_tab_layout = QVBoxLayout(overflow_tab_content)
        self._setup_overflow_tab(overflow_tab_layout)
        overflow_tab_layout.addStretch()
        overflow_tab_scroll.setWidget(overflow_tab_content)
        self.left_tabs.addTab(overflow_tab_scroll, "满突溢出")

        splitter.addWidget(self.left_tabs)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        self._setup_preview(right_layout)
        splitter.addWidget(right_widget)

        splitter.setSizes([800, 400])

    def _setup_pool_config(self, parent):
        template_group = QGroupBox("池子模板")
        template_layout = QVBoxLayout(template_group)

        self.pool_template_table = QTableWidget()
        self.pool_template_table.setColumnCount(6)
        self.pool_template_table.setHorizontalHeaderLabels(["模板ID", "类型", "持续(天)", "单抽消耗", "分布", "分布编辑"])
        t_header = self.pool_template_table.horizontalHeader()
        t_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        t_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        t_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        t_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        t_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.pool_template_table.setColumnWidth(1, 70)
        self.pool_template_table.setColumnWidth(2, 70)
        self.pool_template_table.setColumnWidth(3, 160)
        self.pool_template_table.setColumnWidth(5, 80)
        self.pool_template_table.verticalHeader().setVisible(False)
        self.pool_template_table.setAlternatingRowColors(True)
        self.pool_template_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.pool_template_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.pool_template_table.setMinimumHeight(120)
        self.pool_template_table.cellDoubleClicked.connect(self._edit_template_distribution)
        template_layout.addWidget(self.pool_template_table)

        tmpl_btn_layout = QHBoxLayout()
        add_tmpl_btn = QPushButton("添加模板")
        add_tmpl_btn.clicked.connect(self._add_pool_template)
        remove_tmpl_btn = QPushButton("移除选中")
        remove_tmpl_btn.clicked.connect(self._remove_pool_template)
        tmpl_btn_layout.addWidget(add_tmpl_btn)
        tmpl_btn_layout.addWidget(remove_tmpl_btn)
        tmpl_btn_layout.addStretch()
        template_layout.addLayout(tmpl_btn_layout)

        add_from_tmpl_layout = QHBoxLayout()
        add_from_tmpl_layout.addWidget(QLabel("从模板批量添加:"))
        self.tmpl_count_spin = QSpinBox()
        self.tmpl_count_spin.setRange(1, 50)
        self.tmpl_count_spin.setValue(8)
        add_from_tmpl_layout.addWidget(QLabel("数量:"))
        add_from_tmpl_layout.addWidget(self.tmpl_count_spin)
        self.tmpl_id_prefix = QLineEdit()
        self.tmpl_id_prefix.setPlaceholderText("ID前缀(如pool_c)")
        add_from_tmpl_layout.addWidget(self.tmpl_id_prefix)
        self.tmpl_name_prefix = QLineEdit()
        self.tmpl_name_prefix.setPlaceholderText("名称前缀(如角色池)")
        add_from_tmpl_layout.addWidget(self.tmpl_name_prefix)
        self.tmpl_start_day = QSpinBox()
        self.tmpl_start_day.setRange(0, 9999)
        self.tmpl_start_day.setValue(0)
        add_from_tmpl_layout.addWidget(QLabel("起始天:"))
        add_from_tmpl_layout.addWidget(self.tmpl_start_day)
        self.tmpl_interval = QSpinBox()
        self.tmpl_interval.setRange(0, 9999)
        self.tmpl_interval.setValue(21)
        add_from_tmpl_layout.addWidget(QLabel("间隔天:"))
        add_from_tmpl_layout.addWidget(self.tmpl_interval)
        add_from_tmpl_btn = QPushButton("添加")
        add_from_tmpl_btn.clicked.connect(self._add_pools_from_template)
        add_from_tmpl_layout.addWidget(add_from_tmpl_btn)
        add_from_tmpl_layout.addStretch()
        template_layout.addLayout(add_from_tmpl_layout)

        parent.addWidget(template_group)

        group = QGroupBox("卡池配置")
        layout = QVBoxLayout(group)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("筛选:"))

        self.pool_filter = QComboBox()
        self.pool_filter.addItems(["全部", "角色池", "武器池", "兑换池", "复刻池", "普通池"])
        self.pool_filter.currentIndexChanged.connect(self._filter_pools)
        filter_layout.addWidget(self.pool_filter)

        self.pool_search = QLineEdit()
        self.pool_search.setPlaceholderText("搜索池子ID或名称...")
        self.pool_search.textChanged.connect(self._search_pools)
        filter_layout.addWidget(self.pool_search)

        layout.addLayout(filter_layout)

        self.pool_table = QTableWidget()
        self.pool_table.setColumnCount(10)
        self.pool_table.setHorizontalHeaderLabels([
            "启用", "ID", "名称", "类型", "开始(天)", "持续(天)", "单抽消耗", "批次大小", "备注", "分布编辑"
        ])
        header = self.pool_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)
        self.pool_table.setColumnWidth(0, 40)
        self.pool_table.setColumnWidth(3, 70)
        self.pool_table.setColumnWidth(4, 70)
        self.pool_table.setColumnWidth(5, 70)
        self.pool_table.setColumnWidth(6, 160)
        self.pool_table.setColumnWidth(7, 60)
        self.pool_table.setColumnWidth(9, 80)
        self.pool_table.verticalHeader().setVisible(False)
        self.pool_table.setAlternatingRowColors(True)
        self.pool_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.pool_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.pool_table.setMinimumHeight(250)
        self.pool_table.cellDoubleClicked.connect(self._edit_pool_distribution)
        self.pool_table.cellChanged.connect(self._on_pool_cell_changed)
        layout.addWidget(self.pool_table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加")
        add_btn.clicked.connect(self._add_pool)
        remove_btn = QPushButton("移除选中")
        remove_btn.clicked.connect(self._remove_pool)
        duplicate_btn = QPushButton("复制选中")
        duplicate_btn.clicked.connect(self._duplicate_pool)
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear_pools)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addWidget(duplicate_btn)
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        hint_label = QLabel("提示：类型列只有「角色」「武器」「兑换」「资源」四种类型会被后续分析识别。批次大小设 10 即一次抽卡行动只能十连。")
        hint_label.setStyleSheet("color: #888; font-size: 11px; padding: 2px;")
        layout.addWidget(hint_label)

        parent.addWidget(group)
        self._all_pool_rows = []
        self._pool_distributions = {}
        self._pool_templates = {}
        self._set_default_templates()

    def _set_default_templates(self):
        default_templates = {
            '角色池': {
                'type': '角色',
                'duration': 21,
                'cost': 'draw_resource:160',
                'distribution': [
                    {'card_id': '{id}_ssr', 'probability': 0.6, 'rarity': 'SSR', 'featured': True},
                    {'card_id': '{id}_sr', 'probability': 5.1, 'rarity': 'SR', 'featured': False},
                    {'card_id': '{id}_r', 'probability': 94.3, 'rarity': 'R', 'featured': False},
                ],
            },
            '武器池': {
                'type': '武器',
                'duration': 21,
                'cost': 'draw_resource:160',
                'distribution': [
                    {'card_id': '{id}_ssr', 'probability': 0.7, 'rarity': 'SSR', 'featured': True},
                    {'card_id': '{id}_sr', 'probability': 6.3, 'rarity': 'SR', 'featured': False},
                    {'card_id': '{id}_r', 'probability': 93.0, 'rarity': 'R', 'featured': False},
                ],
            },
            '兑换池': {
                'type': '兑换',
                'duration': 21,
                'cost': 'exchange_currency:5',
                'distribution': [
                    {'card_id': '{id}_ssr', 'probability': 0.6, 'rarity': 'SSR', 'featured': True},
                    {'card_id': '{id}_sr', 'probability': 5.1, 'rarity': 'SR', 'featured': False},
                    {'card_id': '{id}_r', 'probability': 94.3, 'rarity': 'R', 'featured': False},
                ],
            },
        }
        self._pool_templates = default_templates
        self._refresh_template_table()

    def _refresh_template_table(self):
        self.pool_template_table.blockSignals(True)
        self.pool_template_table.setRowCount(len(self._pool_templates))
        for i, (tid, tmpl) in enumerate(self._pool_templates.items()):
            self.pool_template_table.setItem(i, 0, QTableWidgetItem(tid))
            self.pool_template_table.setItem(i, 1, QTableWidgetItem(tmpl.get('type', '角色')))
            self.pool_template_table.setItem(i, 2, QTableWidgetItem(str(tmpl.get('duration', 21))))
            self.pool_template_table.setItem(i, 3, QTableWidgetItem(tmpl.get('cost', 'draw_resource:160')))
            dist = tmpl.get('distribution', [])
            dist_str = ', '.join(f"{d['card_id']}({d['probability']}%)" for d in dist) if dist else '(空)'
            self.pool_template_table.setItem(i, 4, QTableWidgetItem(dist_str))
            edit_item = QTableWidgetItem("...双击编辑")
            edit_item.setFlags(edit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.pool_template_table.setItem(i, 5, edit_item)
        self.pool_template_table.blockSignals(False)

    def _add_pool_template(self):
        row = self.pool_template_table.rowCount()
        tid = f'模板{row+1}'
        while tid in self._pool_templates:
            row += 1
            tid = f'模板{row+1}'
        self._pool_templates[tid] = {
            'type': '角色',
            'duration': 21,
            'cost': 'draw_resource:160',
            'distribution': [
                {'card_id': '{id}_ssr', 'probability': 0.6, 'rarity': 'SSR', 'featured': True},
                {'card_id': '{id}_sr', 'probability': 5.1, 'rarity': 'SR', 'featured': False},
                {'card_id': '{id}_r', 'probability': 94.3, 'rarity': 'R', 'featured': False},
            ],
        }
        self._refresh_template_table()

    def _remove_pool_template(self):
        rows = sorted([r.row() for r in self.pool_template_table.selectionModel().selectedRows()], reverse=True)
        tids = []
        for row in rows:
            tid_item = self.pool_template_table.item(row, 0)
            if tid_item:
                tids.append(tid_item.text())
        for tid in tids:
            self._pool_templates.pop(tid, None)
        self._refresh_template_table()

    def _edit_template_distribution(self, row, col):
        if col != 5:
            return
        tid_item = self.pool_template_table.item(row, 0)
        if not tid_item:
            return
        tid = tid_item.text()
        tmpl = self._pool_templates.get(tid)
        if not tmpl:
            return
        dist = tmpl.get('distribution', [])
        dialog = PoolDistributionDialog(tid, dist, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_distribution()
            tmpl['distribution'] = result
            for item in result:
                rg = item.get('resources_gained', {})
                if isinstance(rg, dict):
                    for rid in rg.keys():
                        self._ensure_resource_registered(rid)
            self._refresh_template_table()

    def _add_pools_from_template(self):
        rows = self.pool_template_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "提示", "请先在模板表中选择一个模板")
            return
        row = rows[0].row()
        tid_item = self.pool_template_table.item(row, 0)
        if not tid_item:
            return
        tid = tid_item.text()
        tmpl = self._pool_templates.get(tid)
        if not tmpl:
            return

        count = self.tmpl_count_spin.value()
        id_prefix = self.tmpl_id_prefix.text().strip() or tid
        name_prefix = self.tmpl_name_prefix.text().strip() or tid
        start_day = self.tmpl_start_day.value()
        interval = self.tmpl_interval.value()

        pools = []
        for i in range(count):
            pid = f'{id_prefix}{i+1}'
            dist = []
            for d in tmpl.get('distribution', []):
                item = dict(d)
                item['card_id'] = item['card_id'].replace('{id}', pid)
                dist.append(item)
            pool = {
                'enabled': True,
                'id': pid,
                'name': f'{name_prefix}{i+1}',
                'type': tmpl.get('type', '角色'),
                'start_day': start_day + i * interval,
                'duration': tmpl.get('duration', 21),
                'cost': tmpl.get('cost', 'draw_resource:160'),
                'note': '复刻池' if i > 0 and interval > 0 else '',
                'distribution': dist,
                'batch_size': 1,
            }
            pools.append(pool)

        existing_count = self.pool_table.rowCount()
        self.pool_table.blockSignals(True)
        self.pool_table.setRowCount(existing_count + count)
        for i, p in enumerate(pools):
            r = existing_count + i
            enabled_cb = QCheckBox()
            enabled_cb.setChecked(p['enabled'])
            self.pool_table.setCellWidget(r, 0, enabled_cb)
            self.pool_table.setItem(r, 1, QTableWidgetItem(p['id']))
            self.pool_table.setItem(r, 2, QTableWidgetItem(p['name']))
            self.pool_table.setItem(r, 3, QTableWidgetItem(p['type']))
            self.pool_table.setItem(r, 4, QTableWidgetItem(str(p['start_day'])))
            self.pool_table.setItem(r, 5, QTableWidgetItem(str(p['duration'])))
            self.pool_table.setItem(r, 6, QTableWidgetItem(p['cost']))
            self.pool_table.setItem(r, 7, QTableWidgetItem(str(p.get('batch_size', 1))))
            self.pool_table.setItem(r, 8, QTableWidgetItem(p.get('note', '')))
            edit_item = QTableWidgetItem("...双击编辑")
            edit_item.setFlags(edit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.pool_table.setItem(r, 9, edit_item)
            self._pool_distributions[p['id']] = p['distribution']

            inferred = self._infer_pool_type(p['id'], p['type'], p.get('note', ''))
            row_bg = self._pool_row_bg(inferred, p.get('note', ''))
            if row_bg:
                for col in range(10):
                    item = self.pool_table.item(r, col)
                    if item:
                        item.setBackground(row_bg)

        self.pool_table.blockSignals(False)
        self._sync_card_defs_from_pools()
        self._register_resources_from_pools(pools)
        self._update_preview()

    def _set_pool_table(self, pools):
        self.pool_table.blockSignals(True)
        self.pool_table.setRowCount(len(pools))
        self._all_pool_rows = list(range(len(pools)))
        self._pool_distributions = {}

        for i, p in enumerate(pools):
            enabled_cb = QCheckBox()
            enabled_cb.setChecked(p.get('enabled', True))
            self.pool_table.setCellWidget(i, 0, enabled_cb)

            pool_id = p.get('id', '')
            self.pool_table.setItem(i, 1, QTableWidgetItem(pool_id))
            self.pool_table.setItem(i, 2, QTableWidgetItem(p.get('name', '')))
            self.pool_table.setItem(i, 3, QTableWidgetItem(p.get('type', '角色')))
            self.pool_table.setItem(i, 4, QTableWidgetItem(str(p.get('start_day', 0))))
            self.pool_table.setItem(i, 5, QTableWidgetItem(str(p.get('duration', 21))))

            cost = p.get('cost', 160)
            if isinstance(cost, int):
                cost_text = f'draw_resource:{cost}'
            else:
                cost_text = str(cost)
            self.pool_table.setItem(i, 6, QTableWidgetItem(cost_text))

            dist = p.get('distribution')
            if dist is not None:
                self._pool_distributions[pool_id] = dist
                note = f"{len(dist)}卡"
            else:
                note = p.get('note', '')
            batch_size = p.get('batch_size', 1)
            self.pool_table.setItem(i, 7, QTableWidgetItem(str(batch_size)))
            self.pool_table.setItem(i, 8, QTableWidgetItem(note))
            edit_item = QTableWidgetItem("...双击编辑")
            edit_item.setFlags(edit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.pool_table.setItem(i, 9, edit_item)

            inferred = self._infer_pool_type(pool_id, p.get('type', ''), note)
            row_bg = self._pool_row_bg(inferred, note)
            if row_bg:
                for col in range(10):
                    item = self.pool_table.item(i, col)
                    if item:
                        item.setBackground(row_bg)

        self._sync_card_defs_from_pools()
        self._register_resources_from_pools(pools)
        self.pool_table.blockSignals(False)
        self._update_preview()

    def _filter_pools(self):
        filter_type = self.pool_filter.currentText()
        for i in range(self.pool_table.rowCount()):
            if filter_type == "全部":
                self.pool_table.setRowHidden(i, False)
            else:
                type_col = self.pool_table.item(i, 3)
                hidden = type_col.text() != filter_type if type_col else True
                self.pool_table.setRowHidden(i, hidden)

    def _search_pools(self, text):
        text = text.lower()
        for i in range(self.pool_table.rowCount()):
            if not text:
                self.pool_table.setRowHidden(i, False)
                continue
            id_item = self.pool_table.item(i, 1)
            name_item = self.pool_table.item(i, 2)
            id_match = id_item.text().lower().find(text) >= 0 if id_item else False
            name_match = name_item.text().lower().find(text) >= 0 if name_item else False
            self.pool_table.setRowHidden(i, not (id_match or name_match))

    def _add_pool(self):
        row = self.pool_table.rowCount()
        self.pool_table.insertRow(row)
        enabled_cb = QCheckBox()
        enabled_cb.setChecked(True)
        self.pool_table.setCellWidget(row, 0, enabled_cb)
        self.pool_table.setItem(row, 1, QTableWidgetItem(f"pool_{row+1}"))
        self.pool_table.setItem(row, 2, QTableWidgetItem(f"池子{row+1}"))
        self.pool_table.setItem(row, 3, QTableWidgetItem("角色"))
        self.pool_table.setItem(row, 4, QTableWidgetItem("0"))
        self.pool_table.setItem(row, 5, QTableWidgetItem("21"))
        self.pool_table.setItem(row, 6, QTableWidgetItem("draw_resource:160"))
        self.pool_table.setItem(row, 7, QTableWidgetItem("1"))
        self.pool_table.setItem(row, 8, QTableWidgetItem(""))
        edit_item = QTableWidgetItem("...双击编辑")
        edit_item.setFlags(edit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.pool_table.setItem(row, 9, edit_item)
        self._all_pool_rows.append(row)
        self._ensure_resource_registered('draw_resource', '抽卡资源')
        self._sync_card_defs_from_pools()
        self._update_preview()

    def _remove_pool(self):
        rows = sorted([r.row() for r in self.pool_table.selectionModel().selectedRows()], reverse=True)
        for row in rows:
            id_item = self.pool_table.item(row, 1)
            if id_item:
                self._pool_distributions.pop(id_item.text().strip(), None)
            self.pool_table.removeRow(row)
        self._sync_card_defs_from_pools()
        self._update_preview()

    def _duplicate_pool(self):
        rows = [r.row() for r in self.pool_table.selectionModel().selectedRows()]
        for row in rows:
            new_row = self.pool_table.rowCount()
            self.pool_table.insertRow(new_row)
            for col in range(10):
                if col == 0:
                    enabled_cb = QCheckBox()
                    enabled_cb.setChecked(True)
                    self.pool_table.setCellWidget(new_row, 0, enabled_cb)
                else:
                    src_item = self.pool_table.item(row, col)
                    if src_item:
                        new_item = QTableWidgetItem(src_item.text())
                        new_item.setBackground(src_item.background())
                        self.pool_table.setItem(new_row, col, new_item)
            edit_item = QTableWidgetItem("...双击编辑")
            edit_item.setFlags(edit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.pool_table.setItem(new_row, 9, edit_item)
            id_item = self.pool_table.item(new_row, 1)
            if id_item:
                id_item.setText(f"{id_item.text()}_copy")
        self._update_preview()

    def _clear_pools(self):
        self.pool_table.setRowCount(0)
        self._all_pool_rows = []
        self._pool_distributions = {}
        self._sync_card_defs_from_pools()
        self._update_preview()

    def _edit_pool_distribution(self, row, col):
        if col != 8:
            return
        pool_id_item = self.pool_table.item(row, 1)
        if not pool_id_item:
            return
        pool_id = pool_id_item.text()

        distribution = self._pool_distributions.get(pool_id)
        if distribution is None:
            distribution = [
                {'card_id': f'{pool_id}_ssr', 'probability': 0.6, 'rarity': 'SSR', 'featured': True},
                {'card_id': f'{pool_id}_sr', 'probability': 5.1, 'rarity': 'SR', 'featured': False},
                {'card_id': f'{pool_id}_r', 'probability': 94.3, 'rarity': 'R', 'featured': False},
            ]

        dialog = PoolDistributionDialog(pool_id, distribution, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_distribution()
            self._pool_distributions[pool_id] = result
            for item in result:
                rg = item.get('resources_gained', {})
                if isinstance(rg, dict):
                    for rid in rg.keys():
                        self._ensure_resource_registered(rid)
            note_item = self.pool_table.item(row, 8)
            if note_item:
                note_item.setText(f"{len(result)}卡")
            self._sync_card_defs_from_pools()

    # ══════════════════════════════════════════════════════════════════
    # P55 阶段十一：保底配置 UI——BEHAVIOR_REGISTRY 元数据驱动
    # ══════════════════════════════════════════════════════════════════

    # 可选的保底类型（仅已实现的 counter 驱动型）
    _PITY_TYPES = [
        ('soft_interval', '区间软保底'),
        ('soft_additive', '累加软保底'),
        ('soft_step', '分段软保底'),
        ('hard', '硬保底'),
        # P56 新增
        ('rotating', '轮换保底'),
        ('rotating_soft', '轮换+软保底'),
        ('rotating_cr', '轮换+捕获明光'),
        ('rotating_cr_soft', '轮换+捕获明光+软保底'),
        ('targeted', '定轨保底'),
        ('targeted_soft', '定轨+软保底'),
    ]

    # 动态控件工厂——参数类型 → (widget_class, widget_kwargs)
    _WIDGET_FACTORY = {
        'int': (QSpinBox, {'range': (1, 999), 'value': 80}),
        'float': (QDoubleSpinBox, {'range': (0.1, 1000.0), 'value': 6.0, 'decimals': 2, 'singleStep': 0.5}),
        'bool': (QCheckBox, {}),
        'str': (QLineEdit, {}),
        'deltas': (None, {}),  # 特殊处理——deltas 表格
    }

    def _setup_pity_config(self, parent):
        self._pity_defs = []
        self._current_pity_row: int = -1  # 当前选中索引（用于切换前 flush）
        self._pity_dynamic_widgets = {}  # pname → widget
        self._pity_dynamic_labels = {}   # pname → label

        self.pity_enabled = QCheckBox("启用保底")
        self.pity_enabled.setChecked(True)
        parent.addWidget(self.pity_enabled)

        main_layout = QHBoxLayout()
        left_layout = QVBoxLayout()
        self.pity_list = QListWidget()
        self.pity_list.currentRowChanged.connect(self._on_pity_selected)
        left_layout.addWidget(self.pity_list)

        pity_btn_layout = QHBoxLayout()
        add_pity_btn = QPushButton("添加保底")
        add_pity_btn.clicked.connect(self._add_pity)
        remove_pity_btn = QPushButton("移除保底")
        remove_pity_btn.clicked.connect(self._remove_pity)
        apply_pity_btn = QPushButton("应用修改")
        apply_pity_btn.clicked.connect(self._apply_pity_edit)
        pity_btn_layout.addWidget(add_pity_btn)
        pity_btn_layout.addWidget(remove_pity_btn)
        pity_btn_layout.addWidget(apply_pity_btn)
        left_layout.addLayout(pity_btn_layout)
        main_layout.addLayout(left_layout, 1)

        # ── 详情面板（右侧） ──
        detail_group = QGroupBox("保底详情")
        detail_group.setEnabled(False)
        self._pity_detail_group = detail_group
        detail_form = QFormLayout(detail_group)
        self._pity_detail_form = detail_form  # P56：供 _on_pity_type_changed 整行显隐

        # 名称
        self.pity_name_edit = QLineEdit()
        detail_form.addRow("名称:", self.pity_name_edit)

        # 类型
        self.pity_type_combo = QComboBox()
        self.pity_type_combo.addItems([d for _, d in self._PITY_TYPES])
        self.pity_type_combo.currentIndexChanged.connect(self._on_pity_type_changed)
        detail_form.addRow("类型:", self.pity_type_combo)

        # scope
        self.pity_scope_combo = QComboBox()
        self.pity_scope_combo.addItems(["ssr", "sr", "r"])
        detail_form.addRow("稀有度:", self.pity_scope_combo)

        # target_featured
        self.pity_target_featured_cb = QCheckBox("仅限Featured卡")
        detail_form.addRow("目标:", self.pity_target_featured_cb)

        # ── 动态参数区（由 BEHAVIOR_REGISTRY 元数据生成） ──
        self._pity_dynamic_area = QFormLayout()
        self._pity_dynamic_area.setContentsMargins(0, 0, 0, 0)
        self._pity_dynamic_container = QWidget()
        self._pity_dynamic_container.setLayout(self._pity_dynamic_area)
        detail_form.addRow(QLabel("参数:"), self._pity_dynamic_container)

        # ── deltas 表格（仅 soft_step 可见） ──
        self._pity_deltas_group = QGroupBox("deltas 分段表")
        deltas_layout = QVBoxLayout(self._pity_deltas_group)
        self.pity_deltas_table = QTableWidget()
        self.pity_deltas_table.setColumnCount(2)
        self.pity_deltas_table.setHorizontalHeaderLabels(["抽数段", "增量(%)"])
        dt_header = self.pity_deltas_table.horizontalHeader()
        dt_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        dt_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.pity_deltas_table.setMaximumHeight(150)
        deltas_layout.addWidget(self.pity_deltas_table)
        deltas_btn_layout = QHBoxLayout()
        add_delta_btn = QPushButton("添加段")
        add_delta_btn.clicked.connect(self._add_deltas_row)
        remove_delta_btn = QPushButton("移除段")
        remove_delta_btn.clicked.connect(self._remove_deltas_row)
        deltas_btn_layout.addWidget(add_delta_btn)
        deltas_btn_layout.addWidget(remove_delta_btn)
        deltas_btn_layout.addStretch()
        deltas_layout.addLayout(deltas_btn_layout)
        detail_form.addRow(self._pity_deltas_group)
        self._pity_deltas_group.setVisible(False)

        # ── P56：cr_state_probs 表格（仅 rotating_cr / rotating_cr_soft 可见） ──
        self._pity_cr_probs_group = QGroupBox("捕获明光——每状态拦截概率")
        cr_probs_layout = QVBoxLayout(self._pity_cr_probs_group)
        self.pity_cr_probs_table = QTableWidget()
        self.pity_cr_probs_table.setColumnCount(1)
        self.pity_cr_probs_table.setHorizontalHeaderLabels(["拦截概率"])
        cr_header = self.pity_cr_probs_table.horizontalHeader()
        cr_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.pity_cr_probs_table.setMaximumHeight(150)
        cr_probs_layout.addWidget(self.pity_cr_probs_table)
        cr_probs_btn_layout = QHBoxLayout()
        add_cr_btn = QPushButton("添加行")
        add_cr_btn.clicked.connect(self._add_cr_probs_row)
        remove_cr_btn = QPushButton("移除行")
        remove_cr_btn.clicked.connect(self._remove_cr_probs_row)
        cr_probs_btn_layout.addWidget(add_cr_btn)
        cr_probs_btn_layout.addWidget(remove_cr_btn)
        cr_probs_btn_layout.addStretch()
        cr_probs_layout.addLayout(cr_probs_btn_layout)
        detail_form.addRow(self._pity_cr_probs_group)
        self._pity_cr_probs_group.setVisible(False)

        # ── 池子 + 初始值 ──
        self.pity_pools_edit = QLineEdit()
        self.pity_pools_edit.setPlaceholderText("* (全部池子)")
        detail_form.addRow("适用池子:", self.pity_pools_edit)

        self.pity_init_spin = QSpinBox()
        self.pity_init_spin.setRange(0, 200)
        self.pity_init_spin.setValue(0)
        detail_form.addRow("初始水位:", self.pity_init_spin)

        # ── P56：初始状态（rotating / targeted 家族） ──
        self.pity_guaranteed_init_cb = QCheckBox("初始处于大保底状态")
        self.pity_guaranteed_init_cb.setVisible(False)
        detail_form.addRow("", self.pity_guaranteed_init_cb)

        self.pity_fate_points_spin = QSpinBox()
        self.pity_fate_points_spin.setRange(0, 10)
        self.pity_fate_points_spin.setValue(0)
        self.pity_fate_points_spin.setVisible(False)
        detail_form.addRow("初始命定值:", self.pity_fate_points_spin)

        # P56：初始定轨卡片（targeted 家族可见，从池子 epitomizable_cards 填充）
        self.pity_selected_card_combo = QComboBox()
        self.pity_selected_card_combo.setVisible(False)
        self.pity_selected_card_combo.setToolTip("模拟开始时的定轨目标——留空 = 不定轨")
        detail_form.addRow("初始定轨:", self.pity_selected_card_combo)

        # ── 生命周期 ──
        self.pity_deactivate_cb = QCheckBox("提前出货后停用")
        detail_form.addRow("", self.pity_deactivate_cb)

        self.pity_depends_combo = QComboBox()
        self.pity_depends_combo.addItem("(无依赖)", "")
        self.pity_depends_combo.setToolTip("依赖的 behavior——该 behavior 首次触发后本保底才激活")
        detail_form.addRow("依赖:", self.pity_depends_combo)

        main_layout.addWidget(detail_group, 2)
        parent.addLayout(main_layout)

        # 信号连接——控件变更 → 实时写回数据 → 触发预览
        self.pity_enabled.stateChanged.connect(self._flush_pity_current_detail)
        self.pity_name_edit.textChanged.connect(self._flush_pity_current_detail)
        self.pity_type_combo.currentIndexChanged.connect(self._flush_pity_current_detail)
        self.pity_scope_combo.currentIndexChanged.connect(self._flush_pity_current_detail)
        self.pity_target_featured_cb.stateChanged.connect(self._flush_pity_current_detail)
        self.pity_pools_edit.textChanged.connect(self._flush_pity_current_detail)
        self.pity_init_spin.valueChanged.connect(self._flush_pity_current_detail)
        self.pity_deactivate_cb.stateChanged.connect(self._flush_pity_current_detail)
        self.pity_guaranteed_init_cb.stateChanged.connect(self._flush_pity_current_detail)
        self.pity_fate_points_spin.valueChanged.connect(self._flush_pity_current_detail)
        self.pity_selected_card_combo.currentIndexChanged.connect(self._flush_pity_current_detail)
        self.pity_depends_combo.currentIndexChanged.connect(self._flush_pity_current_detail)

    # ── 动态控件构建 ──

    def _build_param_widgets(self, btype: str) -> dict:
        """根据 BEHAVIOR_REGISTRY 中 btype 的 params 元数据生成控件。
        返回 {param_name: widget} dict。
        """
        widgets = {}
        # 清除旧控件
        self._clear_dynamic_widgets()

        entry = BEHAVIOR_REGISTRY.get(btype, {})
        params_meta = entry.get('params', {})

        for pname, pmeta in params_meta.items():
            ptype = pmeta.get('type', 'str')
            if ptype == 'deltas':
                continue  # deltas 由专用表格处理

            factory = self._WIDGET_FACTORY.get(ptype)
            if factory is None:
                continue

            widget_cls, kwargs = factory
            if widget_cls is None:
                continue

            # registry 声明了 options → 使用 QComboBox（覆盖类型默认控件）
            if "options" in pmeta:
                w = QComboBox()
                options = pmeta["options"]
                for opt in options:
                    w.addItem(str(opt))
                default = pmeta.get('default', options[0])
                idx = w.findText(str(default))
                if idx >= 0:
                    w.setCurrentIndex(idx)
            elif widget_cls is QSpinBox:
                w = QSpinBox()
                w.setRange(*kwargs.get('range', (1, 999)))
                default = pmeta.get('default', kwargs.get('value', 0))
                w.setValue(int(default) if default else 0)
            elif widget_cls is QDoubleSpinBox:
                w = QDoubleSpinBox()
                w.setRange(*kwargs.get('range', (0.1, 1000.0)))
                w.setDecimals(kwargs.get('decimals', 2))
                w.setSingleStep(kwargs.get('singleStep', 1.0))
                default = pmeta.get('default', kwargs.get('value', 1.0))
                w.setValue(float(default) if default else 0.0)
            elif widget_cls is QCheckBox:
                w = QCheckBox()
                w.setChecked(pmeta.get('default', False))
            elif widget_cls is QLineEdit:
                w = QLineEdit()
                default = pmeta.get('default', '')
                w.setText(str(default) if default else '')
            else:
                continue

            display = pmeta.get('display_name', pname)
            label = QLabel(f"{display}:")
            self._pity_dynamic_area.addRow(label, w)
            # 连接预览信号
            if hasattr(w, 'valueChanged'):
                w.valueChanged.connect(self._flush_pity_current_detail)
            elif hasattr(w, 'currentIndexChanged'):
                w.currentIndexChanged.connect(self._flush_pity_current_detail)
            elif hasattr(w, 'textChanged'):
                w.textChanged.connect(self._flush_pity_current_detail)
            elif hasattr(w, 'stateChanged'):
                w.stateChanged.connect(self._flush_pity_current_detail)

            widgets[pname] = w
            self._pity_dynamic_labels[pname] = label

        self._pity_dynamic_widgets = widgets
        return widgets

    def _clear_dynamic_widgets(self):
        """清除旧的动态控件。"""
        area = self._pity_dynamic_area
        # 从后往前移除所有行
        for i in range(area.rowCount() - 1, -1, -1):
            row = area.takeRow(i)
            # PyQt6: takeRow() 返回 TakeRowResult (namedtuple-like)；
            # 可通过 .labelItem / .fieldItem 属性安全访问
            if row is not None:
                label_item = row.labelItem
                field_item = row.fieldItem
                if label_item and label_item.widget():
                    label_item.widget().setParent(None)
                if field_item and field_item.widget():
                    field_item.widget().setParent(None)
        self._pity_dynamic_widgets = {}
        self._pity_dynamic_labels = {}

    # ── deltas 表格 ──

    def _show_deltas_table(self, visible: bool):
        self._pity_deltas_group.setVisible(visible)

    def _populate_deltas_table(self, deltas):
        """deltas: ((n, inc), ...) 或 None"""
        table = self.pity_deltas_table
        table.setRowCount(0)
        if not deltas:
            return
        table.setRowCount(len(deltas))
        for i, (n, inc) in enumerate(deltas):
            n_item = QTableWidgetItem(str(n))
            inc_item = QTableWidgetItem(str(inc))
            table.setItem(i, 0, n_item)
            table.setItem(i, 1, inc_item)

    def _read_deltas_table(self):
        """读取 deltas 表格 → tuple[tuple[int, float], ...]"""
        table = self.pity_deltas_table
        result = []
        for i in range(table.rowCount()):
            n_item = table.item(i, 0)
            inc_item = table.item(i, 1)
            if n_item and inc_item:
                try:
                    n = int(n_item.text())
                    inc = float(inc_item.text())
                    result.append((n, inc))
                except ValueError:
                    continue
        return tuple(result) if result else None

    def _add_deltas_row(self):
        table = self.pity_deltas_table
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem("10"))
        table.setItem(row, 1, QTableWidgetItem("5.0"))

    def _remove_deltas_row(self):
        table = self.pity_deltas_table
        rows = sorted([r.row() for r in table.selectionModel().selectedRows()], reverse=True)
        for row in rows:
            table.removeRow(row)

    # ── P56：cr_state_probs 表格操作 ──

    def _populate_cr_probs_table(self, cr_state_probs):
        """cr_state_probs: [float, ...] 或 None"""
        table = self.pity_cr_probs_table
        table.setRowCount(0)
        if not cr_state_probs:
            return
        table.setRowCount(len(cr_state_probs))
        for i, val in enumerate(cr_state_probs):
            table.setItem(i, 0, QTableWidgetItem(str(val)))

    def _read_cr_probs_table(self):
        """读取 cr_state_probs 表格 → list[float]"""
        table = self.pity_cr_probs_table
        result = []
        for i in range(table.rowCount()):
            item = table.item(i, 0)
            if item:
                try:
                    result.append(float(item.text()))
                except ValueError:
                    continue
        return result if result else None

    def _add_cr_probs_row(self):
        table = self.pity_cr_probs_table
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem("0.0"))

    def _remove_cr_probs_row(self):
        table = self.pity_cr_probs_table
        rows = sorted([r.row() for r in table.selectionModel().selectedRows()], reverse=True)
        for row in rows:
            table.removeRow(row)

    # ── P56：depends_on 下拉框刷新 ──

    def _refresh_depends_combo(self):
        """用当前 _pity_defs 中的 behavior 名称填充 depends_on 下拉框。"""
        combo = self.pity_depends_combo
        current_data = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("(无依赖)", "")
        for pd in self._pity_defs:
            name = pd.get('name', '')
            if name:
                combo.addItem(name, name)
        idx = combo.findData(current_data)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    # ── P56：QFormLayout 整行显隐 + selected_card 下拉填充 ──

    def _set_form_row_visible(self, widget, visible: bool):
        """隐藏/显示 QFormLayout 中一整行（标签 + 控件）。"""
        widget.setVisible(visible)
        label = self._pity_detail_form.labelForField(widget)
        if label:
            label.setVisible(visible)

    def _populate_selected_card_combo(self):
        """从池子 epitomizable_cards 填充初始定轨下拉框。无配置时仅显示「不定轨」。"""
        combo = self.pity_selected_card_combo
        current_data = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("(不定轨)", "")
        if self._store:
            for pool in self._store.pools:
                for cid in getattr(pool, 'epitomizable_cards', []):
                    combo.addItem(cid, cid)
        idx = combo.findData(current_data)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    # ── CRUD 操作 ──

    def _add_pity(self):
        idx = len(self._pity_defs) + 1
        name = f"pity_{idx}"
        while any(pd.get('name') == name for pd in self._pity_defs):
            idx += 1
            name = f"pity_{idx}"
        # P55 新格式
        new_def = {
            'name': name,
            'btype': 'soft_interval',
            'scope': 'ssr',
            'target_featured': False,
            'deltas': None,
            'threshold': None,
            'counter_init': 0,
            'guaranteed_init': False,
            'fate_points_init': 0,
            'selected_card_init': None,
            'soft_start': 80,
            'soft_end': 90,
            'soft_increment': None,
            'reset': '',
            'pools': '*',
            'deactivate_on_early_hit': False,
            'depends_on': None,
        }
        self._pity_defs.append(new_def)
        self.pity_list.addItem(name)
        self.pity_list.setCurrentRow(self.pity_list.count() - 1)
        self._refresh_depends_combo()  # P56：新增后刷新引用列表
        self._update_preview()

    def _remove_pity(self):
        row = self.pity_list.currentRow()
        if row < 0:
            return
        self._pity_defs.pop(row)
        self.pity_list.takeItem(row)
        self._pity_detail_group.setEnabled(False)
        self._refresh_depends_combo()  # P56：删除后刷新引用列表
        if self._pity_defs and self.pity_list.count() > 0:
            self.pity_list.setCurrentRow(min(row, self.pity_list.count() - 1))
        self._update_preview()

    def _on_pity_selected(self, row):
        # 切换前先保存当前编辑（仿照 _on_card_selected 模式）
        self._flush_pity_current_detail()
        if row < 0 or row >= len(self._pity_defs):
            self._current_pity_row = -1
            self._pity_detail_group.setEnabled(False)
            return
        self._current_pity_row = row
        self._pity_detail_group.setEnabled(True)
        pd = self._pity_defs[row]

        # 阻断信号避免级联触发
        self.pity_name_edit.blockSignals(True)
        self.pity_type_combo.blockSignals(True)
        self.pity_scope_combo.blockSignals(True)

        self.pity_name_edit.setText(pd.get('name', ''))

        # 类型
        btype = pd.get('btype', 'soft_interval')
        type_idx = next((i for i, (t, _) in enumerate(self._PITY_TYPES) if t == btype), 0)
        self.pity_type_combo.setCurrentIndex(type_idx)

        # scope
        scope = pd.get('scope', 'ssr')
        scope_idx = self.pity_scope_combo.findText(scope)
        if scope_idx >= 0:
            self.pity_scope_combo.setCurrentIndex(scope_idx)

        # target_featured
        self.pity_target_featured_cb.setChecked(pd.get('target_featured', False))

        # 动态参数
        self._build_param_widgets(btype)
        self._populate_dynamic_values(pd, btype)

        # deltas 表格（仅 soft_step 显示并填充）
        is_soft_step = (btype == 'soft_step')
        self._show_deltas_table(is_soft_step)
        if is_soft_step:
            self._populate_deltas_table(pd.get('deltas'))

        # 池子 / 初始值
        pools = pd.get('pools', '*')
        if isinstance(pools, (tuple, list)):
            pools = ','.join(pools)
        self.pity_pools_edit.setText(pools if pools != '*' else '')
        self.pity_init_spin.setValue(pd.get('counter_init', 0))

        # 生命周期
        self.pity_deactivate_cb.setChecked(pd.get('deactivate_on_early_hit', False))
        self._refresh_depends_combo()
        depends_val = pd.get('depends_on') or ''
        idx = self.pity_depends_combo.findData(depends_val)
        if idx >= 0:
            self.pity_depends_combo.setCurrentIndex(idx)

        # ── P56：初始状态 ──
        self.pity_guaranteed_init_cb.setChecked(pd.get('guaranteed_init', False))
        self.pity_fate_points_spin.setValue(pd.get('fate_points_init', 0))
        sc = pd.get('selected_card_init') or ''
        idx = self.pity_selected_card_combo.findData(sc)
        if idx >= 0:
            self.pity_selected_card_combo.setCurrentIndex(idx)

        self.pity_name_edit.blockSignals(False)
        self.pity_type_combo.blockSignals(False)
        self.pity_scope_combo.blockSignals(False)

        self._on_pity_type_changed(type_idx)

    # Registry 参数名 → PityDef 标准字段名映射
    _PARAM_TO_FIELD = {'start': 'soft_start', 'end': 'soft_end', 'increment': 'soft_increment'}

    def _populate_dynamic_values(self, pd: dict, btype: str):
        """将 pd 的字段值填入动态控件。"""
        entry = BEHAVIOR_REGISTRY.get(btype, {})
        params_meta = entry.get('params', {})
        for pname, w in self._pity_dynamic_widgets.items():
            pmeta = params_meta.get(pname, {})
            ptype = pmeta.get('type', 'str')
            val = pd.get(pname)
            # 若 registry 参数名不存在，尝试标准 PityDef 字段名
            if val is None:
                canonical = self._PARAM_TO_FIELD.get(pname)
                if canonical:
                    val = pd.get(canonical)
            if val is None:
                val = pmeta.get('default', 0 if ptype in ('int', 'float') else '')
            if isinstance(w, QSpinBox):
                w.setValue(int(val) if val else 0)
            elif isinstance(w, QDoubleSpinBox):
                w.setValue(float(val) if val else 0)
            elif isinstance(w, QComboBox):
                idx = w.findText(str(val)) if val else -1
                if idx >= 0:
                    w.setCurrentIndex(idx)
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(val))
            elif isinstance(w, QLineEdit):
                w.setText(str(val) if val else '')

    def _flush_pity_current_detail(self):
        """从右侧控件读取当前值 → 实时写回 self._pity_defs[idx]"""
        row = self._current_pity_row
        if row < 0 or row >= len(self._pity_defs):
            return
        pd = self._pity_defs[row]
        pd['name'] = self.pity_name_edit.text().strip() or f"pity_{row+1}"

        # btype
        bt_idx = self.pity_type_combo.currentIndex()
        pd['btype'] = self._PITY_TYPES[bt_idx][0] if 0 <= bt_idx < len(self._PITY_TYPES) else 'soft_interval'

        # scope
        pd['scope'] = self.pity_scope_combo.currentText()

        # target_featured
        pd['target_featured'] = self.pity_target_featured_cb.isChecked()

        # 动态参数 → pd 字段
        btype = pd['btype']
        entry = BEHAVIOR_REGISTRY.get(btype, {})
        params_meta = entry.get('params', {})
        for pname, w in self._pity_dynamic_widgets.items():
            pmeta = params_meta.get(pname, {})
            ptype = pmeta.get('type', 'str')
            try:
                if isinstance(w, QComboBox):
                    pd[pname] = w.currentText()
                elif ptype == 'int':
                    raw = w.value() if hasattr(w, 'value') else w.text()
                    pd[pname] = int(raw) if str(raw).strip() else 0
                elif ptype == 'float':
                    raw = w.value() if hasattr(w, 'value') else w.text()
                    pd[pname] = float(raw) if str(raw).strip() else 0.0
                elif ptype == 'bool':
                    pd[pname] = w.isChecked() if hasattr(w, 'isChecked') else False
                else:
                    pd[pname] = w.text() if hasattr(w, 'text') else str(w.value())
            except (ValueError, TypeError):
                pd[pname] = pmeta.get('default', 0 if ptype in ('int', 'float') else '')

        # deltas（仅 soft_step 类型保存）
        if btype == 'soft_step':
            deltas = self._read_deltas_table()
            if deltas:
                pd['deltas'] = deltas
            else:
                pd['deltas'] = None

        # 语法糖参数映射（registry 控件名 → PityDef 标准字段）
        if btype in ('soft_interval',):
            pd['soft_start'] = pd.get('start')
            pd['soft_end'] = pd.get('end')
        elif btype in ('soft_additive', 'rotating_soft',
                        'rotating_cr_soft', 'targeted_soft'):
            pd['soft_start'] = pd.get('start')
            pd['soft_increment'] = pd.get('increment')

        # 池子 / 初始值
        pools_text = self.pity_pools_edit.text().strip()
        pd['pools'] = tuple(pools_text.split(',')) if pools_text else ('*',)
        pd['counter_init'] = self.pity_init_spin.value()

        # 生命周期
        pd['deactivate_on_early_hit'] = self.pity_deactivate_cb.isChecked()
        depends = self.pity_depends_combo.currentData()
        pd['depends_on'] = depends if depends else None

        # ── P56：初始状态 ──
        pd['guaranteed_init'] = self.pity_guaranteed_init_cb.isChecked()
        pd['fate_points_init'] = self.pity_fate_points_spin.value()
        sc = self.pity_selected_card_combo.currentData()
        pd['selected_card_init'] = sc if sc else None

        # ── P56：cr_state_probs 表格（仅 rotating_cr 家族保存） ──
        if btype in ('rotating_cr', 'rotating_cr_soft'):
            cr_probs = self._read_cr_probs_table()
            pd['cr_state_probs'] = cr_probs if cr_probs else None

        self.pity_list.item(row).setText(pd['name'])
        self._update_preview()

    def _apply_pity_edit(self):
        row = self.pity_list.currentRow()
        if row < 0 or row >= len(self._pity_defs):
            return
        pd = self._pity_defs[row]
        pd['name'] = self.pity_name_edit.text().strip() or f"pity_{row+1}"

        # btype
        bt_idx = self.pity_type_combo.currentIndex()
        pd['btype'] = self._PITY_TYPES[bt_idx][0] if 0 <= bt_idx < len(self._PITY_TYPES) else 'soft_interval'

        # scope
        pd['scope'] = self.pity_scope_combo.currentText()

        # target_featured
        pd['target_featured'] = self.pity_target_featured_cb.isChecked()

        # 动态参数 → pd 字段
        btype = pd['btype']
        entry = BEHAVIOR_REGISTRY.get(btype, {})
        params_meta = entry.get('params', {})
        for pname, w in self._pity_dynamic_widgets.items():
            pmeta = params_meta.get(pname, {})
            ptype = pmeta.get('type', 'str')
            try:
                if isinstance(w, QComboBox):
                    pd[pname] = w.currentText()
                elif ptype == 'int':
                    raw = w.value() if hasattr(w, 'value') else w.text()
                    pd[pname] = int(raw) if str(raw).strip() else 0
                elif ptype == 'float':
                    raw = w.value() if hasattr(w, 'value') else w.text()
                    pd[pname] = float(raw) if str(raw).strip() else 0.0
                elif ptype == 'bool':
                    pd[pname] = w.isChecked() if hasattr(w, 'isChecked') else False
                else:
                    pd[pname] = w.text() if hasattr(w, 'text') else str(w.value())
            except (ValueError, TypeError):
                pd[pname] = pmeta.get('default', 0 if ptype in ('int', 'float') else '')

        # deltas（仅 soft_step 类型保存）
        if btype == 'soft_step':
            deltas = self._read_deltas_table()
            if deltas:
                pd['deltas'] = deltas
            else:
                pd['deltas'] = None

        # 语法糖参数映射（registry 控件名 → PityDef 标准字段）
        # soft_interval               → start + end       (interval 模式)
        # soft_additive + P56 _soft   → start + increment (additive 模式)
        if btype in ('soft_interval',):
            pd['soft_start'] = pd.get('start')
            pd['soft_end'] = pd.get('end')
        elif btype in ('soft_additive', 'rotating_soft',
                        'rotating_cr_soft', 'targeted_soft'):
            pd['soft_start'] = pd.get('start')
            pd['soft_increment'] = pd.get('increment')

        # 池子 / 初始值
        pools_text = self.pity_pools_edit.text().strip()
        pd['pools'] = tuple(pools_text.split(',')) if pools_text else ('*',)
        pd['counter_init'] = self.pity_init_spin.value()

        # 生命周期
        pd['deactivate_on_early_hit'] = self.pity_deactivate_cb.isChecked()
        depends = self.pity_depends_combo.currentData()
        pd['depends_on'] = depends if depends else None

        # ── P56：初始状态 ──
        pd['guaranteed_init'] = self.pity_guaranteed_init_cb.isChecked()
        pd['fate_points_init'] = self.pity_fate_points_spin.value()
        sc = self.pity_selected_card_combo.currentData()
        pd['selected_card_init'] = sc if sc else None

        # ── P56：cr_state_probs 表格（仅 rotating_cr 家族保存） ──
        if btype in ('rotating_cr', 'rotating_cr_soft'):
            cr_probs = self._read_cr_probs_table()
            pd['cr_state_probs'] = cr_probs if cr_probs else None

        self.pity_list.item(row).setText(pd['name'])
        self._update_preview()

    def _on_pity_type_changed(self, idx):
        if idx < 0 or idx >= len(self._PITY_TYPES):
            return
        btype = self._PITY_TYPES[idx][0]
        is_soft_step = (btype == 'soft_step')
        is_counter = btype in ('soft_interval', 'soft_additive', 'soft_step', 'hard')
        is_cr = btype in ('rotating_cr', 'rotating_cr_soft')

        # deltas 表格显隐
        self._show_deltas_table(is_soft_step)

        # P56：cr_state_probs 表格显隐
        self._pity_cr_probs_group.setVisible(is_cr)

        # 动态参数重建——先 flush 保存当前值，再销毁旧控件
        self._flush_pity_current_detail()
        self._build_param_widgets(btype)
        # 重建后重新填充当前选中条目的值（否则只剩默认值）
        row = self.pity_list.currentRow()
        if 0 <= row < len(self._pity_defs):
            self._populate_dynamic_values(self._pity_defs[row], btype)
            # 填充 cr_state_probs 表格
            if is_cr:
                self._populate_cr_probs_table(self._pity_defs[row].get('cr_state_probs'))

        # 联动校验：hard+非ssr 禁用 target_featured
        is_hard = (btype == 'hard')
        is_ssr_scope = self.pity_scope_combo.currentText() == 'ssr'
        self.pity_target_featured_cb.setEnabled(not (is_hard and not is_ssr_scope))

        # deactivate_on_early_hit 对 counter 驱动型均可用（soft/hard 均可）
        self.pity_deactivate_cb.setEnabled(is_counter)

        # ── P56：初始状态控件整行显隐（标签 + 控件） ──
        is_rotating = btype in ('rotating', 'rotating_soft', 'rotating_cr', 'rotating_cr_soft')
        is_targeted = btype in ('targeted', 'targeted_soft')
        self._set_form_row_visible(self.pity_guaranteed_init_cb, is_rotating)
        self._set_form_row_visible(self.pity_fate_points_spin, is_targeted)
        self._set_form_row_visible(self.pity_selected_card_combo, is_targeted)
        if is_targeted:
            self._populate_selected_card_combo()

    def _setup_strategy_tab(self, parent):
        from gacha_simulator.core.strategy import STRATEGY_REGISTRY
        from gacha_simulator.core.stop_condition import STOP_CONDITION_REGISTRY

        group = QGroupBox("抽卡策略")
        layout = QVBoxLayout(group)

        strategy_layout = QFormLayout()
        self.strategy_type = QComboBox()
        self._strategy_display_names = [
            entry.display_name for entry in STRATEGY_REGISTRY.values()
            if not entry.internal and not entry.disabled
        ]
        self.strategy_type.addItems(self._strategy_display_names)
        strategy_layout.addRow("策略类型:", self.strategy_type)

        self.stop_condition_type = QComboBox()
        self._stop_condition_display_names = [
            entry['display_name'] for entry in STOP_CONDITION_REGISTRY.values()
        ]
        self.stop_condition_type.addItems(self._stop_condition_display_names)
        strategy_layout.addRow("停止条件:", self.stop_condition_type)

        self.auto_wait = QCheckBox("无池可抽时自动等待")
        self.auto_wait.setChecked(True)
        strategy_layout.addRow("", self.auto_wait)
        layout.addLayout(strategy_layout)

        self._strategy_params_group = QGroupBox("策略参数")
        self._strategy_params_layout = QFormLayout(self._strategy_params_group)
        layout.addWidget(self._strategy_params_group)
        self._strategy_param_widgets = {}

        self.strategy_type.currentIndexChanged.connect(self._on_strategy_type_changed)
        self._on_strategy_type_changed(0)

        parent.addWidget(group)

    def _setup_target_tab(self, parent):
        """目标卡编辑标签页。"""
        group = QGroupBox("目标卡")
        layout = QVBoxLayout(group)

        target_label = QLabel("目标卡（卡ID + 需求数量）:")
        layout.addWidget(target_label)

        self.target_table = QTableWidget()
        self.target_table.setColumnCount(3)
        self.target_table.setHorizontalHeaderLabels(["卡ID", "需求数量", "所属池子"])
        header = self.target_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.target_table.setColumnWidth(1, 70)
        self.target_table.verticalHeader().setVisible(False)
        self.target_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.target_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.target_table.setMinimumHeight(150)
        layout.addWidget(self.target_table)

        target_btn_layout = QHBoxLayout()
        add_target_btn = QPushButton("添加目标卡")
        add_target_btn.clicked.connect(self._add_target_card)
        remove_target_btn = QPushButton("移除选中")
        remove_target_btn.clicked.connect(self._remove_target_card)
        target_btn_layout.addWidget(add_target_btn)
        target_btn_layout.addWidget(remove_target_btn)
        target_btn_layout.addStretch()
        layout.addLayout(target_btn_layout)

        hint_label = QLabel(
            "提示：「需求数量」表示还需从抽卡中获得的额外数量。"
            "例如：初始持有 1 张，想再抽 2 张，则需求数量应设为 2。"
        )
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: #888; padding: 4px 0; font-size: 12px;")
        layout.addWidget(hint_label)

        card_ref_label = QLabel("可用卡ID参考（双击可添加到目标卡）:")
        layout.addWidget(card_ref_label)

        self.card_id_list = QListWidget()
        self.card_id_list.setMinimumHeight(120)
        self.card_id_list.itemDoubleClicked.connect(self._on_card_id_double_clicked)
        layout.addWidget(self.card_id_list)

        self.target_table.cellChanged.connect(self._update_preview)

        parent.addWidget(group)

    def _rebuild_strategy_dropdown(self):
        """公开方法——重建策略下拉框（供插件管理面板启用/禁用后调用）。"""
        from gacha_simulator.core.strategy import STRATEGY_REGISTRY as _sr
        current_key = None
        if self.strategy_type.currentIndex() >= 0:
            from gacha_simulator.core.strategy import strategy_type_to_key
            current_key = strategy_type_to_key(self.strategy_type.currentText())

        self._strategy_display_names = [
            entry.display_name for entry in _sr.values()
            if not entry.internal and not entry.disabled
        ]
        self.strategy_type.blockSignals(True)
        self.strategy_type.clear()
        self.strategy_type.addItems(self._strategy_display_names)
        if current_key:
            from gacha_simulator.core.strategy import STRATEGY_REGISTRY
            meta = STRATEGY_REGISTRY.get(current_key)
            if meta and not meta.disabled and meta.display_name in self._strategy_display_names:
                self.strategy_type.setCurrentIndex(
                    self._strategy_display_names.index(meta.display_name))
            else:
                self.strategy_type.setCurrentIndex(0)
        self.strategy_type.blockSignals(False)

    def _on_strategy_type_changed(self, idx):
        from gacha_simulator.core.strategy import STRATEGY_REGISTRY, strategy_type_to_key
        from gacha_simulator.gui.param_renderer import render_param_widgets

        while self._strategy_params_layout.rowCount() > 0:
            self._strategy_params_layout.removeRow(0)
        self._strategy_param_widgets = {}

        display_name = self.strategy_type.currentText()
        key = strategy_type_to_key(display_name)
        entry = STRATEGY_REGISTRY.get(key)
        if not entry or not entry.params:
            self._strategy_params_group.setVisible(False)
            if hasattr(self, 'preview_text'):
                self._update_preview()
            return

        self._strategy_params_group.setVisible(True)
        render_param_widgets(
            entry.params, self._strategy_params_layout,
            self._strategy_param_widgets, parent=self,
        )

        if hasattr(self, 'preview_text'):
            self._update_preview()

    def _get_strategy_params_from_widgets(self):
        from gacha_simulator.gui.param_renderer import collect_params_from_widgets
        return collect_params_from_widgets(self._strategy_param_widgets)

    def _set_strategy_params_to_widgets(self, params):
        from gacha_simulator.core.strategy import STRATEGY_REGISTRY, strategy_type_to_key
        from gacha_simulator.gui.param_renderer import set_params_to_widgets

        display_name = self.strategy_type.currentText()
        key = strategy_type_to_key(display_name)
        entry = STRATEGY_REGISTRY.get(key)
        if entry:
            set_params_to_widgets(entry.params, self._strategy_param_widgets, params)

    def _setup_weight_config(self, parent):
        info_label = QLabel("配置每张卡的权重，用于加权满意度和总出卡价值等广义出率的计算。\n"
                            "抽取意愿权重：成功抽出该卡时获得的满意度权重\n"
                            "错失代价权重：未能抽出该卡时的遗憾代价权重\n"
                            "单卡价值：每张卡的价值，用于总出卡价值计算")
        info_label.setWordWrap(True)
        parent.addWidget(info_label)

        self.weight_table = QTableWidget()
        self.weight_table.setColumnCount(5)
        self.weight_table.setHorizontalHeaderLabels(["卡ID", "名称", "抽取意愿权重", "错失代价权重", "单卡价值"])
        header = self.weight_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.weight_table.setColumnWidth(2, 110)
        self.weight_table.setColumnWidth(3, 110)
        self.weight_table.setColumnWidth(4, 110)
        self.weight_table.verticalHeader().setVisible(False)
        self.weight_table.setAlternatingRowColors(True)
        self.weight_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.weight_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.weight_table.setMinimumHeight(200)
        parent.addWidget(self.weight_table)

        btn_layout = QHBoxLayout()
        remove_weight_btn = QPushButton("移除选中")
        remove_weight_btn.clicked.connect(self._remove_weight_row)
        reset_weight_btn = QPushButton("重置为默认(1.0)")
        reset_weight_btn.clicked.connect(self._reset_weights_default)
        btn_layout.addWidget(remove_weight_btn)
        btn_layout.addWidget(reset_weight_btn)
        btn_layout.addStretch()
        parent.addLayout(btn_layout)

        self._weight_data = {}

    # ═══════════════════════════════════════════════════════════════
    # P63：满突溢出标签页
    # ═══════════════════════════════════════════════════════════════

    def _setup_overflow_tab(self, parent):
        info_label = QLabel(
            "配置稀有度级别的卡片溢出规则。\n"
            "卡片获得时根据累计持有次数匹配分段表，命中区间即产出资源。\n"
            "优先级：卡片显式配置 > 稀有度默认。键名大小写不敏感。\n"
            "产出格式：资源名:数值，多个用逗号分隔（如 exchange_currency:10,starglitter:5）"
        )
        info_label.setWordWrap(True)
        parent.addWidget(info_label)

        self.overflow_table = QTableWidget()
        self.overflow_table.setColumnCount(5)
        self.overflow_table.setHorizontalHeaderLabels([
            "稀有度", "首次获得产出", "满突张数", "满突前每次产出", "满突后每次产出"
        ])
        header = self.overflow_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for col in range(1, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self.overflow_table.verticalHeader().setVisible(False)
        self.overflow_table.setAlternatingRowColors(True)
        self.overflow_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.overflow_table.setMinimumHeight(150)
        parent.addWidget(self.overflow_table)

        # 变更即写回 store（P56 自动应用模式）
        self.overflow_table.cellChanged.connect(self._on_overflow_cell_changed)

        parent.addStretch()

        # 初始化时填充表格
        self._refresh_overflow_tab()

    def _get_rarity_list(self):
        """从 [rarities].ranks 动态解析稀有度列表；无配置时回退默认三级。"""
        store = getattr(self, '_store', None)
        if store and store.rarity_rank:
            # rarities.ranks 如 [["SSR"], ["SR"], ["R"]] → 展平按 rank 排序
            buckets = {}
            for name, rank_idx in store.rarity_rank.items():
                buckets.setdefault(rank_idx, []).append(name.upper())
            result = []
            for r in sorted(buckets):
                result.extend(buckets[r])
            return result
        return ["SSR", "SR", "R"]

    def _refresh_overflow_tab(self):
        """从 ConfigStore.rarity_defaults 填充溢出表格。"""
        store = getattr(self, '_store', None)
        rarities = self._get_rarity_list()

        # 阻断信号避免刷新期间的 cellChanged 触发写入
        self.overflow_table.blockSignals(True)

        self.overflow_table.setRowCount(len(rarities))
        for i, rarity_name in enumerate(rarities):
            # 稀有度列（只读）
            rarity_item = QTableWidgetItem(rarity_name)
            rarity_item.setFlags(rarity_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.overflow_table.setItem(i, 0, rarity_item)

            # 从 store 读取该稀有度的溢出规则（键名 .lower()）
            rarity_key = rarity_name.lower()
            rd = {}
            if store and hasattr(store, 'rarity_defaults'):
                rd = store.rarity_defaults.get(rarity_key, {})

            bands = rd.get('overflow_bands', [])
            # 将分段表反推为三字段
            first, threshold, pre_excess, post_excess = self._bands_to_fields(bands)

            # 首次获得产出
            first_text = ','.join(f'{k}:{v}' for k, v in sorted(first.items())) if first else ''
            first_item = QTableWidgetItem(first_text)
            self.overflow_table.setItem(i, 1, first_item)

            # 满突张数（阈值）
            threshold_item = QTableWidgetItem(str(threshold) if threshold else '')
            self.overflow_table.setItem(i, 2, threshold_item)

            # 满突前每次产出
            pre_text = ','.join(f'{k}:{v}' for k, v in sorted(pre_excess.items())) if pre_excess else ''
            pre_item = QTableWidgetItem(pre_text)
            self.overflow_table.setItem(i, 3, pre_item)

            # 满突后每次产出
            post_text = ','.join(f'{k}:{v}' for k, v in sorted(post_excess.items())) if post_excess else ''
            post_item = QTableWidgetItem(post_text)
            self.overflow_table.setItem(i, 4, post_item)

        self.overflow_table.blockSignals(False)

    def _bands_to_fields(self, bands):
        """将 OverflowBand 列表反推为三字段（首次/阈值/满突前/满突后）。

        Returns:
            (first, threshold, pre_excess, post_excess)
        """
        first = {}
        threshold = 7
        pre_excess = {}
        post_excess = {}

        for band in bands:
            if band.min == 1 and band.max == 1:
                first = dict(band.resources)
            elif band.max is None:
                # [N, ∞) → 满突后
                post_excess = dict(band.resources)
                threshold = band.min
            elif band.min == 2 and band.max is not None:
                # [2, N] → 满突前（假设首次=1, 满突后=N+1）
                pre_excess = dict(band.resources)
                if threshold is None:
                    threshold = band.max + 1
            elif band.min > 1 and band.max is None:
                post_excess = dict(band.resources)
                threshold = band.min
            elif band.min == 1 and band.max is not None and band.max > 1:
                # [1, N] 恒真单段——无首次、无满突后
                pre_excess = dict(band.resources)

        return first, threshold, pre_excess, post_excess

    def _on_overflow_cell_changed(self, row, col):
        """溢出表格单元格变更 → 实时展开为分段表并写回 store.rarity_defaults。"""
        store = getattr(self, '_store', None)
        if store is None:
            return

        rarity_name = self._get_rarity_list()[row]
        rarity_key = rarity_name.lower()

        # 读取四组字段
        def _parse_resources(item):
            if item is None:
                return {}
            text = item.text().strip()
            if not text:
                return {}
            result = {}
            for part in text.split(','):
                part = part.strip()
                if not part:
                    continue
                if ':' in part:
                    k, v = part.split(':', 1)
                    try:
                        val = float(v.strip())
                        if val < 0:
                            continue  # GUI-3：负数拒绝写入
                        result[k.strip()] = val
                    except ValueError:
                        continue  # GUI-4：非数值拒绝写入，保持旧值
            return result

        first = _parse_resources(self.overflow_table.item(row, 1))
        threshold_text = (self.overflow_table.item(row, 2).text().strip()
                          if self.overflow_table.item(row, 2) else '')
        try:
            threshold = int(threshold_text) if threshold_text else None
        except ValueError:
            threshold = None
        pre_excess = _parse_resources(self.overflow_table.item(row, 3))
        post_excess = _parse_resources(self.overflow_table.item(row, 4))

        # 展开为分段表（四种组合映射）
        bands = self._expand_fields_to_bands(first, threshold, pre_excess, post_excess)

        # 写回 store.rarity_defaults（键名 .lower()）
        if not hasattr(store, 'rarity_defaults'):
            store.rarity_defaults = {}
        if bands:
            store.rarity_defaults[rarity_key] = {'overflow_bands': bands}
        elif rarity_key in store.rarity_defaults:
            del store.rarity_defaults[rarity_key]

        # 重新构建 card_overflow_map
        from ..core.config_toml import _build_card_overflow_map
        _build_card_overflow_map(store)

    def _expand_fields_to_bands(self, first, threshold, pre_excess, post_excess):
        """将三字段展开为 OverflowBand 列表（四种组合映射）。

        组合：
          首次 + 满突张数N + 满突前 + 满突后 → [1,1]→首次 + [2,N]→满突前 + [N+1,∞)→满突后
          满突张数N + 满突前 + 满突后（无首次）→ [1,N]→满突前 + [N+1,∞)→满突后
          仅有满突前（无张数）→ [1,∞)→满突前（恒真单段）
          全空 → 无溢出规则
        """
        bands = []

        if first:
            bands.append(OverflowBand(min=1, max=1, resources=first))

        if threshold is not None and threshold > 0:
            if post_excess:
                bands.append(OverflowBand(min=threshold, max=None, resources=post_excess))
            if pre_excess:
                # 满突前区间取决于是否有首次
                pre_start = 2 if first else 1
                pre_end = threshold - 1
                if pre_start <= pre_end:
                    bands.append(OverflowBand(min=pre_start, max=pre_end, resources=pre_excess))
        elif pre_excess and not post_excess:
            # 仅有满突前、无张数、无满突后 → 恒真单段 [1,∞)
            pre_start = 2 if first else 1
            bands.append(OverflowBand(min=pre_start, max=None, resources=pre_excess))

        bands.sort(key=lambda b: b.min)
        return bands if bands else None

    def _sync_weight_cards(self):
        card_defs = self.get_card_defs()
        existing_weights = self._get_weight_data()
        new_weights = {}
        for cd in card_defs:
            cid = cd.get('card_id', '')
            if not cid or cid == '_no_card':
                continue
            if cid in existing_weights:
                new_weights[cid] = existing_weights[cid]
                new_weights[cid]['name'] = cd.get('name', cid)
            else:
                new_weights[cid] = {
                    'name': cd.get('name', cid),
                    'desire_weight': 1.0,
                    'miss_cost_weight': 1.0,
                    'card_value': 1.0,
                }
        self._set_weight_data(new_weights)

    def _remove_weight_row(self):
        rows = sorted([r.row() for r in self.weight_table.selectionModel().selectedRows()], reverse=True)
        for row in rows:
            self.weight_table.removeRow(row)
        self._weight_data = self._get_weight_data()
        self._update_preview()

    def _reset_weights_default(self):
        for i in range(self.weight_table.rowCount()):
            desire_spin = self.weight_table.cellWidget(i, 2)
            miss_spin = self.weight_table.cellWidget(i, 3)
            value_spin = self.weight_table.cellWidget(i, 4)
            if desire_spin:
                desire_spin.setValue(1.0)
            if miss_spin:
                miss_spin.setValue(1.0)
            if value_spin:
                value_spin.setValue(1.0)

    def _get_weight_data(self):
        data = {}
        for i in range(self.weight_table.rowCount()):
            id_item = self.weight_table.item(i, 0)
            name_item = self.weight_table.item(i, 1)
            desire_spin = self.weight_table.cellWidget(i, 2)
            miss_spin = self.weight_table.cellWidget(i, 3)
            value_spin = self.weight_table.cellWidget(i, 4)
            cid = id_item.text().strip() if id_item else ''
            if not cid:
                continue
            data[cid] = {
                'name': name_item.text().strip() if name_item else cid,
                'desire_weight': desire_spin.value() if desire_spin else 1.0,
                'miss_cost_weight': miss_spin.value() if miss_spin else 1.0,
                'card_value': value_spin.value() if value_spin else 1.0,
            }
        return data

    def _set_weight_data(self, data):
        self._weight_data = dict(data)
        self.weight_table.blockSignals(True)
        self.weight_table.setRowCount(len(data))
        for i, (cid, w) in enumerate(data.items()):
            self.weight_table.setItem(i, 0, QTableWidgetItem(cid))
            self.weight_table.setItem(i, 1, QTableWidgetItem(w.get('name', cid)))
            desire_spin = QDoubleSpinBox()
            desire_spin.setRange(0.0, 100.0)
            desire_spin.setDecimals(2)
            desire_spin.setValue(w.get('desire_weight', 1.0))
            desire_spin.setSingleStep(0.1)
            self.weight_table.setCellWidget(i, 2, desire_spin)
            miss_spin = QDoubleSpinBox()
            miss_spin.setRange(0.0, 100.0)
            miss_spin.setDecimals(2)
            miss_spin.setValue(w.get('miss_cost_weight', 1.0))
            miss_spin.setSingleStep(0.1)
            self.weight_table.setCellWidget(i, 3, miss_spin)
            value_spin = QDoubleSpinBox()
            value_spin.setRange(0.0, 100.0)
            value_spin.setDecimals(2)
            value_spin.setValue(w.get('card_value', 1.0))
            value_spin.setSingleStep(0.1)
            self.weight_table.setCellWidget(i, 4, value_spin)
        self.weight_table.blockSignals(False)

    def _setup_resource_tab(self, parent):
        defs_group = QGroupBox("资源定义")
        defs_layout = QVBoxLayout(defs_group)

        self.resource_defs_table = QTableWidget()
        self.resource_defs_table.setColumnCount(3)
        self.resource_defs_table.setHorizontalHeaderLabels(["资源ID", "显示名称", "初始数量"])
        header = self.resource_defs_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.resource_defs_table.setColumnWidth(2, 120)
        self.resource_defs_table.verticalHeader().setVisible(False)
        self.resource_defs_table.setAlternatingRowColors(True)
        self.resource_defs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.resource_defs_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.resource_defs_table.setMinimumHeight(100)
        defs_layout.addWidget(self.resource_defs_table)

        defs_btn_layout = QHBoxLayout()
        auto_gen_btn = QPushButton("自动生成")
        auto_gen_btn.clicked.connect(self._auto_generate_resource_defs)
        add_def_btn = QPushButton("添加")
        add_def_btn.clicked.connect(self._add_resource_def)
        remove_def_btn = QPushButton("移除选中")
        remove_def_btn.clicked.connect(self._remove_resource_def)
        defs_btn_layout.addWidget(auto_gen_btn)
        defs_btn_layout.addWidget(add_def_btn)
        defs_btn_layout.addWidget(remove_def_btn)
        defs_btn_layout.addStretch()
        defs_layout.addLayout(defs_btn_layout)

        parent.addWidget(defs_group)

        gain_group = QGroupBox("资源获取规则")
        gain_layout = QVBoxLayout(gain_group)

        self.gain_rules_table = QTableWidget()
        self.gain_rules_table.setColumnCount(4)
        self.gain_rules_table.setHorizontalHeaderLabels(["规则类型", "参数", "资源ID", "数量"])
        self.gain_rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.gain_rules_table.verticalHeader().setVisible(False)
        self.gain_rules_table.setAlternatingRowColors(True)
        self.gain_rules_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.gain_rules_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.gain_rules_table.setMinimumHeight(80)
        gain_layout.addWidget(self.gain_rules_table)

        gain_btn_layout = QHBoxLayout()
        add_gain_btn = QPushButton("添加")
        add_gain_btn.clicked.connect(self._add_gain_rule)
        remove_gain_btn = QPushButton("移除选中")
        remove_gain_btn.clicked.connect(self._remove_gain_rule)
        gain_btn_layout.addWidget(add_gain_btn)
        gain_btn_layout.addWidget(remove_gain_btn)
        gain_btn_layout.addStretch()
        gain_layout.addLayout(gain_btn_layout)

        # Phase 2: 模拟起始日期选择器
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("模拟起始日期（day=0 对应）:"))
        self.sim_start_date_edit = QDateEdit()
        self.sim_start_date_edit.setCalendarPopup(True)
        self.sim_start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.sim_start_date_edit.setDate(QDate.currentDate())
        self.sim_start_date_edit.dateChanged.connect(self._on_sim_start_date_changed)
        date_layout.addWidget(self.sim_start_date_edit)
        date_layout.addStretch()
        gain_layout.addLayout(date_layout)

        parent.addWidget(gain_group)

        override_group = QGroupBox("指定日期资源获取")
        override_layout = QVBoxLayout(override_group)

        self.day_overrides_table = QTableWidget()
        self.day_overrides_table.setColumnCount(3)
        self.day_overrides_table.setHorizontalHeaderLabels(["天数", "资源ID", "数量"])
        self.day_overrides_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.day_overrides_table.verticalHeader().setVisible(False)
        self.day_overrides_table.setAlternatingRowColors(True)
        self.day_overrides_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.day_overrides_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.day_overrides_table.setMinimumHeight(80)
        override_layout.addWidget(self.day_overrides_table)

        override_btn_layout = QHBoxLayout()
        add_override_btn = QPushButton("添加")
        add_override_btn.clicked.connect(self._add_day_override)
        remove_override_btn = QPushButton("移除选中")
        remove_override_btn.clicked.connect(self._remove_day_override)
        override_btn_layout.addWidget(add_override_btn)
        override_btn_layout.addWidget(remove_override_btn)
        override_btn_layout.addStretch()
        override_layout.addLayout(override_btn_layout)

        parent.addWidget(override_group)

        # Phase 3: 日历预览（可折叠）
        self.calendar_group = QGroupBox("📅 日历预览")
        self.calendar_group.setCheckable(True)
        self.calendar_group.setChecked(True)
        calendar_layout = QVBoxLayout(self.calendar_group)
        self.calendar_widget = QCalendarWidget()
        self.calendar_widget.setMinimumHeight(200)
        self.calendar_widget.setMaximumHeight(280)
        self.calendar_widget.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.calendar_widget.clicked.connect(self._on_calendar_date_clicked)
        calendar_layout.addWidget(self.calendar_widget)
        self.calendar_detail_label = QLabel("（勾选标题复选框展开日历预览）")
        self.calendar_detail_label.setWordWrap(True)
        self.calendar_detail_label.setStyleSheet("color: #666; padding: 4px;")
        calendar_layout.addWidget(self.calendar_detail_label)
        self.calendar_group.toggled.connect(self._on_calendar_toggled)
        parent.addWidget(self.calendar_group)

        parent.addStretch()

        self.resource_defs = []
        self.resource_gain_rules = []
        self.resource_day_overrides = []

        # Phase 3: 日历预览缓存
        self._cached_schedule = None
        self._cached_schedule_key = None
        self._cached_start_date = None  # 用于清除旧高亮

        self.resource_defs_table.cellChanged.connect(self._on_resource_def_changed)
        self.gain_rules_table.cellChanged.connect(self._update_preview)
        self.day_overrides_table.cellChanged.connect(self._update_preview)

    def _setup_card_def_tab(self, parent):
        # ── 实例变量 ──
        self._card_defs: list = []           # List[dict] —— 内部数据
        self._current_card_idx: int = -1     # 当前选中索引
        self._card_id_counter: int = 0       # P65：_add_card() 递增计数器——在 set_card_defs 中初始化

        outer = QVBoxLayout(parent)

        # ═══ 筛选栏 ═══
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("筛选:"))

        self.card_rarity_filter = QComboBox()
        self.card_rarity_filter.addItem("全部")
        self.card_rarity_filter.currentIndexChanged.connect(self._filter_card_list)
        filter_layout.addWidget(self.card_rarity_filter)

        self.card_search = QLineEdit()
        self.card_search.setPlaceholderText("搜索卡ID、名称或标签...")
        self.card_search.textChanged.connect(self._filter_card_list)
        filter_layout.addWidget(self.card_search)

        outer.addLayout(filter_layout)

        # ═══ 水平两栏 ═══
        main_layout = QHBoxLayout()

        # ── 左栏：卡片列表 ──
        left_layout = QVBoxLayout()
        self._card_list = QListWidget()
        self._card_list.currentRowChanged.connect(self._on_card_selected)
        left_layout.addWidget(self._card_list)

        card_btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加")
        add_btn.clicked.connect(self._add_card)
        remove_btn = QPushButton("移除选中")
        remove_btn.clicked.connect(self._remove_card)
        auto_btn = QPushButton("自动生成")
        auto_btn.clicked.connect(self._auto_generate_card_defs)
        card_btn_layout.addWidget(add_btn)
        card_btn_layout.addWidget(remove_btn)
        card_btn_layout.addWidget(auto_btn)
        card_btn_layout.addStretch()
        left_layout.addLayout(card_btn_layout)

        main_layout.addLayout(left_layout, 1)

        # ── 右栏：详情面板 ──
        self._card_detail_group = QGroupBox("卡片详情")
        self._card_detail_group.setEnabled(False)
        detail_form = QFormLayout(self._card_detail_group)

        self._card_id_edit = QLineEdit()
        self._card_id_edit.textChanged.connect(lambda: self._on_detail_changed())
        detail_form.addRow("card_id:", self._card_id_edit)

        self._card_name_edit = QLineEdit()
        self._card_name_edit.textChanged.connect(lambda: self._on_detail_changed())
        detail_form.addRow("名称:", self._card_name_edit)

        self._card_rarity_combo = QComboBox()
        self._card_rarity_combo.currentIndexChanged.connect(lambda: self._on_detail_changed())
        detail_form.addRow("稀有度:", self._card_rarity_combo)

        self._card_init_spin = QSpinBox()
        self._card_init_spin.setRange(0, 9999)
        self._card_init_spin.valueChanged.connect(lambda: self._on_detail_changed())
        detail_form.addRow("初始持有:", self._card_init_spin)

        # ── 单值标签表 ──
        tags_group = QGroupBox("标签")
        tags_layout = QVBoxLayout(tags_group)
        self._card_tags_table = QTableWidget()
        self._card_tags_table.setColumnCount(2)
        self._card_tags_table.setHorizontalHeaderLabels(["Key", "Value"])
        t_header = self._card_tags_table.horizontalHeader()
        t_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        t_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._card_tags_table.verticalHeader().setVisible(False)
        self._card_tags_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._card_tags_table.cellChanged.connect(self._on_tag_cell_changed)
        tags_layout.addWidget(self._card_tags_table)

        tags_btn = QHBoxLayout()
        tags_btn.addWidget(QPushButton("添加", clicked=self._add_tag_row))
        tags_btn.addWidget(QPushButton("移除选中", clicked=self._remove_tag_row))
        tags_btn.addStretch()
        tags_layout.addLayout(tags_btn)

        detail_form.addRow(tags_group)

        # ── 多值标签表 ──
        lt_group = QGroupBox("多值标签")
        lt_layout = QVBoxLayout(lt_group)
        self._card_list_tags_table = QTableWidget()
        self._card_list_tags_table.setColumnCount(2)
        self._card_list_tags_table.setHorizontalHeaderLabels(["Key", "Value"])
        lt_header = self._card_list_tags_table.horizontalHeader()
        lt_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lt_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._card_list_tags_table.verticalHeader().setVisible(False)
        self._card_list_tags_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        lt_layout.addWidget(self._card_list_tags_table)

        lt_btn = QHBoxLayout()
        lt_btn.addWidget(QPushButton("添加", clicked=self._add_list_tag_row))
        lt_btn.addWidget(QPushButton("移除选中", clicked=self._remove_list_tag_row))
        lt_btn.addStretch()
        lt_layout.addLayout(lt_btn)

        detail_form.addRow(lt_group)

        # ── 所属池子（只读） ──
        self._card_pools_label = QLabel("(自动推导)")
        self._card_pools_label.setWordWrap(True)
        detail_form.addRow("所属池子:", self._card_pools_label)

        main_layout.addWidget(self._card_detail_group, 2)
        outer.addLayout(main_layout)

    def _on_detail_changed(self):
        """详情面板控件变动 → 实时回写当前卡片"""
        if self._current_card_idx >= 0:
            self._flush_current_detail()
            self._update_preview()

    # ══════════════════════════════════════════════════════════════════
    # 卡片列表操作方法
    # ══════════════════════════════════════════════════════════════════

    def _add_card(self):
        """创建空卡片 → 追加到列表 → 自动选中"""
        self._card_id_counter += 1
        new_card = {
            'card_id': f'card_{self._card_id_counter}',
            'name': '',
            'rarity': 'R',
            'pools': [],
            'initial_count': 0,
            'tags': {},
            'list_tags': {},
        }
        self._card_defs.append(new_card)
        self._card_list.addItem(f"{new_card['card_id']}")
        self._card_list.setCurrentRow(self._card_list.count() - 1)
        self._update_preview()

    def _remove_card(self):
        """移除选中卡片"""
        row = self._card_list.currentRow()
        if row < 0:
            return
        self._card_defs.pop(row)
        self._card_list.takeItem(row)
        self._card_detail_group.setEnabled(False)
        self._current_card_idx = -1
        if self._card_defs and self._card_list.count() > 0:
            self._card_list.setCurrentRow(min(row, self._card_list.count() - 1))
        self._update_preview()

    # ══════════════════════════════════════════════════════════════════
    # 详情面板数据交换
    # ══════════════════════════════════════════════════════════════════

    def _on_card_selected(self, row: int):
        """左侧列表切换 → 保存当前编辑 → 填充新卡片"""
        self._flush_current_detail()
        if row < 0 or row >= len(self._card_defs):
            self._card_detail_group.setEnabled(False)
            self._current_card_idx = -1
            return
        self._current_card_idx = row
        self._card_detail_group.setEnabled(True)
        self._populate_card_detail(self._card_defs[row])

    def _flush_current_detail(self):
        """从右侧控件读取当前值 → 写回 self._card_defs[idx]"""
        if self._current_card_idx < 0 or self._current_card_idx >= len(self._card_defs):
            return
        card = self._card_defs[self._current_card_idx]
        card.setdefault('tags', {})
        card.setdefault('list_tags', {})
        card['card_id'] = self._card_id_edit.text().strip()
        card['name'] = self._card_name_edit.text().strip()
        card['rarity'] = self._card_rarity_combo.currentText()
        card['initial_count'] = self._card_init_spin.value()
        card['tags'] = self._read_tags_from_table()
        card['list_tags'] = self._read_list_tags_from_table()
        # P65：跨表冲突检测
        self._validate_cross_table_keys(card['tags'], card['list_tags'])
        # 更新左侧列表显示
        new_label = f"{card['card_id']} ({card['name']})" if card['name'] else card['card_id']
        self._card_list.item(self._current_card_idx).setText(new_label)

    def _validate_cross_table_keys(self, tags: dict, list_tags: dict) -> bool:
        """检查单值标签表和多值标签表是否有同名 Key。返回是否有冲突"""
        overlap = set(tags.keys()) & set(list_tags.keys())
        overlap.discard('')
        if overlap:
            QMessageBox.warning(self, "标签冲突",
                f"以下 Key 同时出现在单值标签和多值标签表中：{', '.join(sorted(overlap))}\n"
                f"将以单值标签表为准，多值表中对应的 Key 将被忽略。")
            for k in overlap:
                list_tags.pop(k, None)
            return True
        return False

    def _populate_card_detail(self, card: dict):
        """将单张卡的数据填入右侧控件（阻断信号——避免逐字段触发 _flush_current_detail 串扰）"""
        widgets = [self._card_id_edit, self._card_name_edit,
                    self._card_rarity_combo, self._card_init_spin]
        for w in widgets:
            w.blockSignals(True)

        self._card_id_edit.setText(card.get('card_id', ''))
        self._card_name_edit.setText(card.get('name', ''))
        rarity_val = card.get('rarity', 'R')
        idx = self._card_rarity_combo.findText(rarity_val, Qt.MatchFlag.MatchFixedString)
        if idx < 0:
            idx = self._card_rarity_combo.findText(rarity_val.upper(), Qt.MatchFlag.MatchFixedString)
        self._card_rarity_combo.setCurrentIndex(idx if idx >= 0 else 2)
        self._card_init_spin.setValue(card.get('initial_count', 0))

        for w in widgets:
            w.blockSignals(False)

        self._populate_tags_table(card.get('tags', {}))
        self._populate_list_tags_table(card.get('list_tags', {}))
        pools_map = self._compute_pools_map()
        pools = pools_map.get(card.get('card_id', ''), [])
        self._card_pools_label.setText(','.join(pools) if pools else '(未关联任何池子)')

    # ══════════════════════════════════════════════════════════════════
    # 标签表操作
    # ══════════════════════════════════════════════════════════════════

    def _populate_tags_table(self, tags: dict):
        """填充单值标签表——card_type 首行（QComboBox）+ 其余行"""
        self._card_tags_table.blockSignals(True)
        self._card_tags_table.setRowCount(0)
        row = 0

        # card_type 系统行
        self._card_tags_table.insertRow(0)
        key_item = QTableWidgetItem("card_type")
        key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._card_tags_table.setItem(0, 0, key_item)
        ct_combo = QComboBox()
        ct_combo.setEditable(True)
        ct_combo.addItems(['', 'character', 'weapon'])
        ct_combo.setCurrentText(tags.get('card_type', ''))
        self._card_tags_table.setCellWidget(0, 1, ct_combo)
        row = 1

        # 其余自定义标签
        for k, v in tags.items():
            if k == 'card_type':
                continue
            self._card_tags_table.insertRow(row)
            self._card_tags_table.setItem(row, 0, QTableWidgetItem(k))
            self._card_tags_table.setItem(row, 1, QTableWidgetItem(v))
            row += 1

        self._card_tags_table.blockSignals(False)

    def _populate_list_tags_table(self, list_tags: dict):
        """展开 Dict[str, List[str]] → 每值一行"""
        self._card_list_tags_table.blockSignals(True)
        self._card_list_tags_table.setRowCount(0)
        row = 0
        for k, values in list_tags.items():
            for v in values:
                self._card_list_tags_table.insertRow(row)
                self._card_list_tags_table.setItem(row, 0, QTableWidgetItem(k))
                self._card_list_tags_table.setItem(row, 1, QTableWidgetItem(v))
                row += 1
        self._card_list_tags_table.blockSignals(False)

    def _read_tags_from_table(self) -> dict:
        """遍历单值表 → Dict[str, str]"""
        result = {}
        for i in range(self._card_tags_table.rowCount()):
            key_item = self._card_tags_table.item(i, 0)
            if not key_item:
                continue
            key = key_item.text().strip()
            if not key:
                continue
            widget = self._card_tags_table.cellWidget(i, 1)
            if isinstance(widget, QComboBox):
                value = widget.currentText().strip()
            else:
                val_item = self._card_tags_table.item(i, 1)
                value = val_item.text().strip() if val_item else ''
            if value:
                result[key] = value
        return result

    def _read_list_tags_from_table(self) -> dict:
        """遍历多值表 → Dict[str, List[str]]"""
        result: dict = {}
        for i in range(self._card_list_tags_table.rowCount()):
            key_item = self._card_list_tags_table.item(i, 0)
            val_item = self._card_list_tags_table.item(i, 1)
            if not key_item or not val_item:
                continue
            key = key_item.text().strip()
            val = val_item.text().strip()
            if not key or not val:
                continue
            result.setdefault(key, []).append(val)
        return result

    def _add_tag_row(self):
        """单值标签表：添加空行"""
        row = self._card_tags_table.rowCount()
        self._card_tags_table.insertRow(row)
        self._card_tags_table.setItem(row, 0, QTableWidgetItem(''))
        self._card_tags_table.setItem(row, 1, QTableWidgetItem(''))

    def _remove_tag_row(self):
        """单值标签表：移除选中行——跳过 card_type 行"""
        rows = sorted([r.row() for r in self._card_tags_table.selectionModel().selectedRows()], reverse=True)
        for row in rows:
            key_item = self._card_tags_table.item(row, 0)
            if key_item and key_item.text().strip() == 'card_type':
                continue
            self._card_tags_table.removeRow(row)

    def _add_list_tag_row(self):
        """多值标签表：添加空行"""
        row = self._card_list_tags_table.rowCount()
        self._card_list_tags_table.insertRow(row)
        self._card_list_tags_table.setItem(row, 0, QTableWidgetItem(''))
        self._card_list_tags_table.setItem(row, 1, QTableWidgetItem(''))

    def _remove_list_tag_row(self):
        """多值标签表：移除选中行"""
        rows = sorted([r.row() for r in self._card_list_tags_table.selectionModel().selectedRows()], reverse=True)
        for row in rows:
            self._card_list_tags_table.removeRow(row)

    def _on_tag_cell_changed(self, row: int, col: int):
        """单值标签表 Key 列编辑完成 → 校验唯一性"""
        if col != 0:
            return
        item = self._card_tags_table.item(row, 0)
        if not item:
            return
        key = item.text().strip()
        if not key:
            return
        if key == 'card_type':
            QMessageBox.warning(self, "系统保留",
                f"'{key}' 是系统标签，不可自定义。")
            item.setText('')
            return
        for i in range(self._card_tags_table.rowCount()):
            if i != row:
                other = self._card_tags_table.item(i, 0)
                if other and other.text().strip() == key:
                    QMessageBox.warning(self, "重复标签",
                        f"标签 Key '{key}' 已存在。如需修改，请直接编辑现有行。")
                    item.setText('')
                    return

    # ══════════════════════════════════════════════════════════════════
    # 筛选与搜索
    # ══════════════════════════════════════════════════════════════════

    def _filter_card_list(self):
        """稀有度筛选 + 文本搜索 → clear + rebuild 列表"""
        filter_rarity = self.card_rarity_filter.currentText()
        search_text = self.card_search.text().strip().lower()

        saved_idx = self._current_card_idx
        self._card_list.blockSignals(True)
        self._card_list.clear()

        for card in self._card_defs:
            cid = card.get('card_id', '')
            # 过滤 _no_card 内部占位条目
            if cid == '_no_card':
                continue
            # 稀有度筛选（大小写不敏感——rarity_rank 大写，卡片数据小写）
            if filter_rarity != "全部":
                if card.get('rarity', '').upper() != filter_rarity.upper():
                    continue
            # 文本搜索
            if search_text:
                name = card.get('name', '').lower()
                tags_match = any(search_text in str(v).lower() for v in card.get('tags', {}).values())
                lt_match = any(
                    search_text in str(v).lower()
                    for vs in card.get('list_tags', {}).values()
                    for v in vs
                )
                if not (search_text in cid.lower() or search_text in name or tags_match or lt_match):
                    continue
            # 通过筛选
            label = f"{cid} ({card.get('name', '')})" if card.get('name') else cid
            self._card_list.addItem(label)

        self._card_list.blockSignals(False)

        # 恢复选中
        if saved_idx >= 0 and saved_idx < len(self._card_defs):
            # 在可见列表中定位原卡片
            for i in range(self._card_list.count()):
                item_text = self._card_list.item(i).text()
                cid = self._card_defs[saved_idx].get('card_id', '')
                if item_text.startswith(cid):
                    self._card_list.setCurrentRow(i)
                    break

    # ══════════════════════════════════════════════════════════════════
    # 兼容旧 API：get_card_defs / set_card_defs
    # ══════════════════════════════════════════════════════════════════

    def get_card_defs(self):
        """读取所有卡片定义（先刷新当前编辑）"""
        self._flush_current_detail()
        return [dict(c) for c in self._card_defs]

    def set_card_defs(self, defs):
        """批量设置卡片定义 → 重建列表"""
        self._card_defs = [dict(d) for d in defs]
        # 确保每条有 tags/list_tags 键
        for c in self._card_defs:
            c.setdefault('tags', {})
            c.setdefault('list_tags', {})
        # P65：从已有 card_N ID 初始化计数器，避免冲突
        max_n = 0
        for c in self._card_defs:
            cid = c.get('card_id', '')
            if cid.startswith('card_') and cid.split('_')[-1].isdigit():
                max_n = max(max_n, int(cid.split('_')[-1]))
        self._card_id_counter = max_n
        self._rebuild_card_list()

    def _rebuild_card_list(self):
        """根据 self._card_defs 重建 QListWidget"""
        self._card_list.clear()
        for c in self._card_defs:
            cid = c.get('card_id', '')
            name = c.get('name', '')
            label = f"{cid} ({name})" if name else cid
            self._card_list.addItem(label)
        self._filter_card_list()

    def _populate_card_rarity_filter(self):
        """从 rarity_rank 动态填充稀有度下拉（筛选栏 + 详情面板共用）。

        store 未就绪或 rarity_rank 为空时回退到默认 SSR/SR/R/无。
        """
        ranks = self._store.rarity_rank if self._store else {}
        rarities = sorted(ranks.keys(), key=lambda r: ranks.get(r, 99)) if ranks else ["SSR", "SR", "R", "无"]
        for combo in [self.card_rarity_filter, self._card_rarity_combo]:
            if combo is None:
                continue
            combo.blockSignals(True)
            combo.clear()
            if combo is self.card_rarity_filter:
                combo.addItem("全部")
            combo.addItems(rarities)
            combo.blockSignals(False)

    def _auto_generate_card_defs(self):
        """从池子分布补充缺失的卡牌——合并模式，不覆盖已有卡片。

        1. 扫描所有池子的分布，收集 (card_id, rarity, pool_id) 三元组
        2. 已有卡片：仅更新 pools 列表
        3. 新卡片：追加到末尾，只填 card_id + rarity + pools，名称和 tag 留空
        4. 排序：已有卡片保持原位，新卡片追加在末尾
        """
        # 阻断串位：松开当前选中，详情面板灰掉
        self._current_card_idx = -1
        self._card_detail_group.setEnabled(False)

        # ── 从池子分布收集卡片 ──
        pool_cards: dict[str, dict] = {}  # card_id → {rarity, pools}
        for i in range(self.pool_table.rowCount()):
            pool_id_item = self.pool_table.item(i, 1)
            if not pool_id_item or not pool_id_item.text():
                continue
            pid = pool_id_item.text()
            dist = self._pool_distributions.get(pid)
            if not dist:
                continue
            for d in dist:
                cid = d.get('card_id', '')
                if not cid or cid == '_no_card':
                    continue
                if cid not in pool_cards:
                    pool_cards[cid] = {
                        'rarity': d.get('rarity', 'R'),
                        'pools': [pid],
                    }
                else:
                    if pid not in pool_cards[cid]['pools']:
                        pool_cards[cid]['pools'].append(pid)

        # ── 合并：已有卡片保留数据和位置 ──
        merged = []
        for c in self._card_defs:
            cid = c.get('card_id', '')
            if cid in pool_cards:
                # 已有卡片：更新 pools
                c['pools'] = pool_cards[cid]['pools']
                del pool_cards[cid]
            merged.append(c)

        # ── 追加：池子中新增的卡片 ──
        for cid, info in pool_cards.items():
            merged.append({
                'card_id': cid,
                'name': '',
                'rarity': info['rarity'],
                'pools': info['pools'],
                'initial_count': 0,
                'tags': {},
                'list_tags': {},
            })

        self.set_card_defs(merged)
        self._update_preview()

    def _compute_pools_map(self):
        """从池子分布实时推导每张卡的池子归属。"""
        result = {}
        for pid, dist_list in self._pool_distributions.items():
            for d in dist_list:
                cid = d.get('card_id', '')
                if cid and cid != '_no_card':
                    result.setdefault(cid, []).append(pid)
        return result

    def _setup_preview(self, parent):
        group = QGroupBox("配置预览")
        layout = QVBoxLayout(group)

        self.preview_text = QLabel()
        self.preview_text.setWordWrap(True)
        self.preview_text.setFont(QFont("Monospace", 9))
        self.preview_text.setStyleSheet("background-color: #f5f5f5; padding: 10px;")
        layout.addWidget(self.preview_text)

        parent.addWidget(group)
        self._update_preview()

    def _add_target_card(self):
        row = self.target_table.rowCount()
        self.target_table.insertRow(row)
        self.target_table.setItem(row, 0, QTableWidgetItem(""))
        qty_item = QTableWidgetItem()
        qty_item.setData(Qt.ItemDataRole.EditRole, 1)
        self.target_table.setItem(row, 1, qty_item)
        pools_item = QTableWidgetItem("")
        pools_item.setFlags(pools_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        pools_item.setBackground(QColor(240, 240, 240))
        self.target_table.setItem(row, 2, pools_item)
        self._update_preview()

    def _remove_target_card(self):
        current_row = self.target_table.currentRow()
        if current_row >= 0:
            self.target_table.removeRow(current_row)
            self._update_preview()

    def _on_card_id_double_clicked(self, item):
        card_id = item.text().split(' | ')[0] if ' | ' in item.text() else item.text()
        for i in range(self.target_table.rowCount()):
            existing = self.target_table.item(i, 0)
            if existing and existing.text().strip() == card_id:
                return
        row = self.target_table.rowCount()
        self.target_table.insertRow(row)
        self.target_table.setItem(row, 0, QTableWidgetItem(card_id))
        qty_item = QTableWidgetItem()
        qty_item.setData(Qt.ItemDataRole.EditRole, 1)
        self.target_table.setItem(row, 1, qty_item)
        pools_item = QTableWidgetItem("")
        pools_item.setFlags(pools_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        pools_item.setBackground(QColor(240, 240, 240))
        self.target_table.setItem(row, 2, pools_item)
        self._update_preview()

    def _update_card_id_list(self):
        self.card_id_list.clear()
        card_defs = self.get_card_defs()
        card_pools_map = {}
        for cd in card_defs:
            cid = cd.get('card_id', '')
            if cid:
                card_pools_map[cid] = cd.get('pools', [])
        for pid, dist in self._pool_distributions.items():
            for d in dist:
                cid = d.get('card_id', '')
                if cid and cid not in card_pools_map:
                    card_pools_map[cid] = [pid]
                elif cid and pid not in card_pools_map[cid]:
                    card_pools_map[cid].append(pid)
        for cd in card_defs:
            card_id = cd['card_id']
            name = cd.get('name', '')
            pools = cd.get('pools', [])
            pools_str = ','.join(pools)
            if name and pools_str:
                display = f"{card_id} | {name} | {pools_str}"
            elif name:
                display = f"{card_id} | {name}"
            elif pools_str:
                display = f"{card_id} | {pools_str}"
            else:
                display = card_id
            self.card_id_list.addItem(display)

    def _get_target_cards(self):
        targets = []
        for i in range(self.target_table.rowCount()):
            id_item = self.target_table.item(i, 0)
            qty_item = self.target_table.item(i, 1)
            pools_item = self.target_table.item(i, 2)
            if id_item and id_item.text().strip():
                card_id = id_item.text().strip()
                try:
                    qty = int(qty_item.text()) if qty_item else 1
                except (ValueError, AttributeError):
                    qty = 1
                pools_text = pools_item.text().strip() if pools_item else ''
                pools = [p.strip() for p in pools_text.split(',') if p.strip()] if pools_text else []
                targets.append({'card_id': card_id, 'quantity': qty, 'pools': pools})
        return targets

    def _set_target_cards(self, targets):
        self.target_table.setRowCount(len(targets))
        for i, t in enumerate(targets):
            self.target_table.setItem(i, 0, QTableWidgetItem(t.get('card_id', '')))
            qty_item = QTableWidgetItem()
            qty_item.setData(Qt.ItemDataRole.EditRole, t.get('quantity', 1))
            self.target_table.setItem(i, 1, qty_item)
            pools_text = ','.join(t.get('pools', []))
            pools_item = QTableWidgetItem(pools_text)
            pools_item.setFlags(pools_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            pools_item.setBackground(QColor(240, 240, 240))
            self.target_table.setItem(i, 2, pools_item)

    def _update_target_pools(self):
        card_defs = self.get_card_defs()
        card_pools_map = {}
        for cd in card_defs:
            cid = cd.get('card_id', '')
            if cid:
                card_pools_map[cid] = cd.get('pools', [])
        for pid, dist in self._pool_distributions.items():
            for d in dist:
                cid = d.get('card_id', '')
                if cid and cid not in card_pools_map:
                    card_pools_map[cid] = [pid]
                elif cid and pid not in card_pools_map[cid]:
                    card_pools_map[cid].append(pid)
        for i in range(self.target_table.rowCount()):
            id_item = self.target_table.item(i, 0)
            if not id_item or not id_item.text().strip():
                continue
            card_id = id_item.text().strip()
            pools = card_pools_map.get(card_id, [])
            pools_text = ','.join(pools)
            pools_item = self.target_table.item(i, 2)
            if pools_item:
                pools_item.setText(pools_text)
            else:
                pools_item = QTableWidgetItem(pools_text)
                pools_item.setFlags(pools_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                pools_item.setBackground(QColor(240, 240, 240))
                self.target_table.setItem(i, 2, pools_item)

    def _update_calendar_highlights(self, start_date, total_days,
                                     old_schedule=None, old_start_date=None):
        """根据缓存的 schedule 设置日历高亮。线程安全：必须在 GUI 主线程调用。

        Args:
            start_date: 当前模拟起始日期。
            total_days: 模拟总天数。
            old_schedule: 上一次展开的 schedule（用于精准清除旧高亮）。
            old_start_date: 上一次使用的起始日期（与 old_schedule 配对）。
        """
        from PyQt6.QtGui import QTextCharFormat, QColor
        import datetime as _dt

        default_fmt = QTextCharFormat()

        # 精准清除上一次设置的高亮日期（解决删除规则后旧日期仍标绿的问题）
        if old_schedule and old_start_date:
            for day_offset in old_schedule:
                d = old_start_date + _dt.timedelta(days=day_offset)
                self.calendar_widget.setDateTextFormat(d, default_fmt)

        if not self._cached_schedule:
            return

        has_fmt = QTextCharFormat()
        has_fmt.setBackground(QColor(180, 230, 180))  # 浅绿色高亮

        try:
            for day_offset, day_gains in self._cached_schedule.items():
                d = start_date + _dt.timedelta(days=day_offset)
                self.calendar_widget.setDateTextFormat(d, has_fmt)
                # Qt 6.8+ setDateToolTip；低版本降级为点击查看
                if hasattr(self.calendar_widget, 'setDateToolTip'):
                    lines = [f"day={day_offset}"]
                    for rid, amt in sorted(day_gains.items()):
                        lines.append(f"{rid}: +{amt}")
                    self.calendar_widget.setDateToolTip(d, '\n'.join(lines))
        except Exception:
            pass

    def _on_calendar_date_clicked(self, qdate):
        """点击日历日期时显示当日资源明细。"""
        if self._cached_schedule is None:
            self.calendar_detail_label.setText("日历预览未展开，请勾选标题复选框启用")
            return

        import datetime as _dt
        start_date_str = getattr(self._store, 'sim_start_date', None) or _dt.date.today().isoformat()
        try:
            start_date = _dt.date.fromisoformat(start_date_str)
        except (ValueError, TypeError):
            start_date = _dt.date(2013, 6, 2)

        py_date = _dt.date(qdate.year(), qdate.month(), qdate.day())
        day_offset = (py_date - start_date).days

        # 检查是否在模拟时间线内
        pools_list = getattr(self._store, 'pools', [])
        if pools_list:
            max_day = max((p.start_day + (p.end_day - p.start_day)) for p in pools_list)
        else:
            max_day = 365

        if day_offset < 0 or day_offset >= max_day:
            self.calendar_detail_label.setText(
                f"📅 {py_date.isoformat()} (day={day_offset}) — 该日期不在模拟时间线内")
            return

        day_gains = self._cached_schedule.get(day_offset, {})
        if day_gains:
            lines = [f"📅 {py_date.isoformat()} (day={day_offset})"]
            for rid, amt in sorted(day_gains.items()):
                lines.append(f"  {rid}: +{amt}")
            self.calendar_detail_label.setText('\n'.join(lines))
        else:
            self.calendar_detail_label.setText(
                f"📅 {py_date.isoformat()} (day={day_offset}) — 当日无资源获取")

    def _on_calendar_toggled(self, checked):
        """日历预览展开/折叠时触发。"""
        if checked:
            import datetime as _dt
            # 展开时跳转到模拟起始日期所在月份
            start_date_str = getattr(self._store, 'sim_start_date', None) or _dt.date.today().isoformat()
            try:
                sd = _dt.date.fromisoformat(start_date_str)
                self.calendar_widget.setCurrentPage(sd.year, sd.month)
            except (ValueError, TypeError):
                pass
            self._cached_schedule_key = None  # 强制重新计算
            self._update_preview()

    def _on_sim_start_date_changed(self, qdate):
        """模拟起始日期变更时触发预览更新。"""
        if self._refreshing or self._store is None:
            return
        self._store.sim_start_date = qdate.toString("yyyy-MM-dd")
        self._update_preview()

    def _update_preview(self):
        """请求更新预览（500ms 去抖）"""
        if self._refreshing or self._store is None:
            return
        self._preview_timer.start()

    def _do_update_preview(self):
        """实际执行预览更新"""
        if self._refreshing:
            return
        if self._store is None:
            self.preview_text.setText("配置预览:\n\n（等待配置加载...）")
            return

        config = self.get_config()
        if not config:
            self.preview_text.setText("配置预览:\n\n（无配置）")
            return

        self._sync_weight_cards()

        pool_info = f"卡池数量: {len(config['pools'])}"

        enabled_count = sum(1 for p in config['pools'] if p.get('enabled', True))
        type_counts = {}
        for p in config['pools']:
            pt = p.get('type', '未知')
            type_counts[pt] = type_counts.get(pt, 0) + 1
        type_lines = '\n'.join(f'  - {t}: {c}' for t, c in sorted(type_counts.items()))

        # P55：pity 预览——遍历 pities 列表
        pity_lines = []
        for pdef in config['pity'].get('pities', []):
            btype = pdef.get('type', '?')
            scope = pdef.get('scope', '?')
            line = f"  {pdef['name']}: {btype}({scope})"
            if pdef.get('deltas'):
                total_n = sum(n for n, _ in pdef['deltas'])
                line += f" deltas={total_n}抽"
            if pdef.get('threshold'):
                line += f" threshold={pdef['threshold']}"
            if pdef.get('target_featured'):
                line += " featured"
            if pdef.get('counter_init'):
                line += f" init={pdef['counter_init']}"
            pity_lines.append(line)
        pity_str = '\n'.join(pity_lines) if pity_lines else '  无'

        resource_defs = config.get('resource_defs', [])
        gain_rules = config.get('resource_gain_rules', [])
        day_overrides = config.get('resource_day_overrides', [])

        init_res_parts = []
        for rd in resource_defs:
            amt = rd.get('initial_amount', 0)
            if amt > 0:
                init_res_parts.append(f"{rd['resource_id']}:{amt}")
        init_res_str = ', '.join(init_res_parts) if init_res_parts else '无'

        preview = f"""配置预览:

模拟次数: {config['simulation_count']}
并行进程: {config['max_workers']}
随机种子: {config['seed']}

{pool_info}
启用: {enabled_count} 个
{type_lines}

卡牌定义: {len(config.get('card_defs', []))} 张

总时长: {max((p['start_day'] + p['duration']) for p in config['pools']) if config['pools'] else 0} 天

保底 ({len(config['pity'].get('pities', []))} 条):
{pity_str}

资源类型: {len(resource_defs)} 种
初始资源: {init_res_str}
获取规则: {len(gain_rules)} 条
指定日期: {len(day_overrides)} 条

目标卡: {len(config.get('target_cards', []))} 张"""

        self.preview_text.setText(preview)
        self._update_card_id_list()
        self._update_target_pools()

        # Phase 3: 日历预览（带缓存，仅当展开时计算）
        # 线程安全：此函数必须在 GUI 主线程执行，若迁移至 QThread 需通过
        # 信号槽或 QMetaObject.invokeMethod 回主线程调用 setDateTextFormat/setDateToolTip。
        if self.calendar_group.isChecked() and self._store is not None:
            from gacha_simulator.core.resource_gain import expand_gain_rules_to_schedule
            import datetime as _dt

            gain_rules = list(getattr(self._store, 'gain_rules', []))
            day_overrides = list(getattr(self._store, 'day_overrides', []))
            start_date_str = getattr(self._store, 'sim_start_date', None) or _dt.date.today().isoformat()
            try:
                start_date = _dt.date.fromisoformat(start_date_str)
            except (ValueError, TypeError):
                start_date = _dt.date(2013, 6, 2)

            # total_days 从池配置推导
            pools_list = getattr(self._store, 'pools', [])
            if pools_list:
                total_days = max(
                    (p.start_day + (p.end_day - p.start_day)) for p in pools_list
                )
            else:
                total_days = 365

            # 缓存 key（避免每次按键都重算日历）
            key_parts = []
            for r in gain_rules:
                rt = getattr(r, 'rule_type', '')
                rp = getattr(r, 'param', '')
                rg = tuple(sorted(
                    (k, round(float(v), 6)) for k, v in (getattr(r, 'gains', {}) or {}).items()
                ))
                key_parts.append((rt, rp, rg))
            for do in day_overrides:
                dg = tuple(sorted(
                    (k, round(float(v), 6)) for k, v in (getattr(do, 'gains', {}) or {}).items()
                ))
                key_parts.append((getattr(do, 'day', 0), dg))
            cache_key = (start_date_str, total_days, tuple(key_parts))

            if self._cached_schedule_key != cache_key:
                # 保存旧缓存以便精准清除上一次的高亮日期
                old_schedule = self._cached_schedule
                old_start_date = self._cached_start_date
                self._cached_schedule = expand_gain_rules_to_schedule(
                    gain_rules=gain_rules,
                    day_overrides=day_overrides,
                    total_days=total_days,
                    start_date=start_date,
                )
                self._cached_schedule_key = cache_key
                self._cached_start_date = start_date
                self._update_calendar_highlights(
                    start_date, total_days, old_schedule, old_start_date)

        self.config_changed.emit(config)

    def _set_defaults(self):
        self._auto_generate_resource_defs()

    def _register_resources_from_pools(self, pools):
        for p in pools:
            cost = p.get('cost', 160)
            if isinstance(cost, int):
                self._ensure_resource_registered('draw_resource', '抽卡资源')
            else:
                cost_text = str(cost)
                for part in cost_text.split('&'):
                    part = part.strip()
                    if ':' in part:
                        rid = part.split(':')[0].strip()
                        self._ensure_resource_registered(rid)
            dist = p.get('distribution')
            if dist:
                for item in dist:
                    rg = item.get('resources_gained', {})
                    if isinstance(rg, dict):
                        for rid in rg.keys():
                            self._ensure_resource_registered(rid)

    def _ensure_resource_registered(self, resource_id, display_name=''):
        if not resource_id:
            return
        existing = self._get_resource_ids()
        if resource_id in existing:
            return
        row = self.resource_defs_table.rowCount()
        self.resource_defs_table.blockSignals(True)
        self.resource_defs_table.insertRow(row)
        self.resource_defs_table.setItem(row, 0, QTableWidgetItem(resource_id))
        self.resource_defs_table.setItem(row, 1, QTableWidgetItem(display_name or resource_id))
        spin = QSpinBox()
        spin.setRange(0, 9999999)
        spin.setValue(0)
        spin.setSingleStep(100)
        self.resource_defs_table.setCellWidget(row, 2, spin)
        self.resource_defs_table.blockSignals(False)
        self._refresh_resource_combos()

    def get_config(self):
        self.apply_to_store()
        store = self._store
        if store is None:
            return {}

        pools = []
        for p in store.pools:
            pools.append({
                'enabled': p.enabled,
                'id': p.pool_id,
                'name': p.name,
                'type': p.pool_type or (p.bindings.get('type', '角色') if p.bindings else '角色'),
                'start_day': p.start_day,
                'duration': p.end_day - p.start_day,
                'cost': p.cost,
                'note': '',
                'batch_size': getattr(p, 'batch_size', 1),
                'epitomizable_cards': getattr(p, 'epitomizable_cards', []),
                'distribution': [{'card_id': d.card_id, 'probability': d.probability,
                                  'rarity': d.rarity, 'featured': d.featured,
                                  'resources_gained': d.resources_gained,}
                                 for d in p.distribution] if p.distribution else None,
            })

        # P55：pity 输出扁平化格式
        pity_summary = {}
        if store.pity.pities:
            first = store.pity.pities[0]
            pity_summary['type'] = first.btype
            if first.deltas is not None:
                total_n = sum(n for n, _ in first.deltas)
                pity_summary['deltas_total'] = total_n
            elif first.threshold is not None:
                pity_summary['threshold'] = first.threshold

        [{'resource_id': rid, 'amount': amt}
                             for rid, amt in store.initial_resources.items() if amt > 0]

        gain_rules = []
        for rule in store.gain_rules:
            for rid, amt in rule.gains.items():
                gain_rules.append({
                    'type': _gain_rule_type_to_gui(rule.rule_type, rule.param),
                    'param': _gain_rule_param_to_gui(rule.rule_type, rule.param),
                    'resource_id': rid,
                    'amount': amt,
                })

        day_overrides = [{'day': do.day, 'resource_id': rid, 'amount': amt}
                         for do in store.day_overrides for rid, amt in do.gains.items()]

        target_cards = [{'card_id': tc.card_id, 'quantity': tc.quantity, 'pools': tc.pool_ids}
                        for tc in store.target_cards]

        card_defs = [{'card_id': cd.card_id, 'name': cd.name, 'rarity': cd.rarity, 'pools': cd.pools,
                      'initial_count': getattr(cd, 'initial_count', 0),
                      'tags': getattr(cd, 'tags', {}),
                      'list_tags': getattr(cd, 'list_tags', {})}
                     for cd in store.card_defs]

        resource_defs = [{'resource_id': rid, 'display_name': name,
                          'initial_amount': store.initial_resources.get(rid, 0)}
                         for rid, name in store.resource_defs.items()]

        sim_count, max_workers, seed = self._get_sim_params()

        return {
            'simulation_count': sim_count,
            'max_workers': max_workers,
            'seed': seed,
            'pools': pools,
            'pity': {
                'enabled': store.pity.enabled,
                'pities': [{
                    'name': pd.get('name', ''),
                    'type': pd.get('btype', 'soft_interval'),
                    'scope': pd.get('scope', 'ssr'),
                    'target_featured': pd.get('target_featured', False),
                    'deltas': pd.get('deltas'),
                    'threshold': pd.get('threshold'),
                    'counter_init': pd.get('counter_init', 0),
                    'start': pd.get('soft_start'),
                    'end': pd.get('soft_end'),
                    'increment': pd.get('soft_increment'),
                    'reset': pd.get('reset', ''),
                    'pools': pd.get('pools', '*'),
                    'guaranteed_init': pd.get('guaranteed_init', False),
                    'fate_points_init': pd.get('fate_points_init', 0),
                    'selected_card_init': pd.get('selected_card_init'),
                    'soft_deltas': pd.get('soft_deltas'),
                    'cr_counter_threshold': pd.get('cr_counter_threshold'),
                    'cr_base_rate': pd.get('cr_base_rate'),
                    'cr_state_probs': pd.get('cr_state_probs'),
                    'fate_threshold': pd.get('fate_threshold'),
                    'switch_allowed': pd.get('switch_allowed'),
                    'switch_resets_progress': pd.get('switch_resets_progress'),
                    'lifecycle': {
                        'deactivate_on_early_hit': pd.get('deactivate_on_early_hit', False),
                        'depends_on': pd.get('depends_on'),
                    } if (pd.get('deactivate_on_early_hit') or pd.get('depends_on')) else {},
                } for pd in self._pity_defs],
            },
            'auto_wait': store.auto_wait,
            'strategy': {
                'key': store.strategy_key,
                'params': dict(store.strategy_params),
            },
            'stop_condition': {
                'type': store.stop_condition_type,
                'params': dict(store.stop_condition_params),
            },
            'target_cards': target_cards,
            'card_defs': card_defs,
            'resource_defs': resource_defs,
            'initial_resources': [{'resource_id': rid, 'amount': amt}
                                  for rid, amt in store.initial_resources.items() if amt > 0],
            'resource_gain_rules': gain_rules,
            'resource_day_overrides': day_overrides,
            'daily_income': _daily_income(store),
            'sim_start_date': store.sim_start_date,
            'card_weights': {cid: {'desire_weight': cw.desire_weight, 'miss_cost_weight': cw.miss_cost_weight, 'card_value': cw.card_value}
                             for cid, cw in store.card_weights.items()},
        }

    def _get_sim_params(self):
        if self._store is not None:
            return self._store.simulation_count, self._store.max_workers, self._store.seed
        return 1000, 4, 42

    def set_config(self, config):
        if self._store is None:
            return

        store = self._store
        store.clear()

        pools_data = config.get('pools', [])
        for p in pools_data:
            from ..core.config_store import PoolEntry, PoolDistEntry
            pid = p.get('id', '')
            dist_data = p.get('distribution')
            distribution = []
            if dist_data:
                for d in dist_data:
                    distribution.append(PoolDistEntry(
                        card_id=d.get('card_id', ''),
                        probability=d.get('probability', 0),
                        rarity=d.get('rarity', 'R'),
                        featured=d.get('featured', False),
                        resources_gained=d.get('resources_gained', {}),
                    ))
            pool_type = p.get('type', '角色')
            bindings = {}
            if pool_type:
                bindings['type'] = pool_type
            store.pools.append(PoolEntry(
                enabled=p.get('enabled', True),
                pool_id=pid,
                name=p.get('name', ''),
                pool_type=pool_type,
                start_day=p.get('start_day', 0),
                end_day=p.get('start_day', 0) + p.get('duration', 21),
                cost=p.get('cost', 'draw_resource:160'),
                distribution_template="",
                bindings=bindings,
                distribution=distribution,
                batch_size=p.get('batch_size', 1),
                epitomizable_cards=p.get('epitomizable_cards', []),
            ))

        pity = config.get('pity', {})
        pities_data = pity.get('pities', [])
        if not pities_data:
            pities_data = [{'name': 'ssr_soft', 'type': 'soft',
                            'params': {'start': str(pity.get('start', 74)),
                                       'end': str(pity.get('end', 90))},
                            'reset': 'any_ssr', 'pools': '*'}]
        pities = []
        self._pity_defs = []
        for pd in pities_data:
            pities.append(PityDef(
                name=pd.get('name', 'pity'),
                btype=pd.get('type', 'soft_interval'),
                scope=pd.get('scope', 'ssr'),
                target_featured=pd.get('target_featured', False),
                deltas=pd.get('deltas'),
                threshold=pd.get('threshold'),
                counter_init=pd.get('counter_init', 0),
                guaranteed_init=pd.get('guaranteed_init', False),
                fate_points_init=pd.get('fate_points_init', 0),
                soft_start=pd.get('start'),
                soft_end=pd.get('end'),
                soft_increment=pd.get('increment'),
                soft_deltas=pd.get('soft_deltas'),
                cr_counter_threshold=pd.get('cr_counter_threshold'),
                cr_base_rate=pd.get('cr_base_rate'),
                cr_state_probs=pd.get('cr_state_probs'),
                fate_threshold=pd.get('fate_threshold'),
                switch_allowed=pd.get('switch_allowed'),
                switch_resets_progress=pd.get('switch_resets_progress'),
                reset=pd.get('reset', ''),
                pools=tuple(pd.get('pools', ('*',))) if isinstance(pd.get('pools'), (list, tuple)) else (pd.get('pools', '*'),),
                deactivate_on_early_hit=(pd.get('lifecycle') or {}).get('deactivate_on_early_hit', False),
                depends_on=(pd.get('lifecycle') or {}).get('depends_on'),
            ))
            # 同步到 _pity_defs UI 内部格式
            self._pity_defs.append({
                'name': pd.get('name', 'pity'),
                'btype': pd.get('type', 'soft_interval'),
                'scope': pd.get('scope', 'ssr'),
                'target_featured': pd.get('target_featured', False),
                'deltas': pd.get('deltas'),
                'threshold': pd.get('threshold'),
                'counter_init': pd.get('counter_init', 0),
                'soft_start': pd.get('start'),
                'soft_end': pd.get('end'),
                'soft_increment': pd.get('increment'),
                'reset': pd.get('reset', ''),
                'pools': pd.get('pools', '*'),
                'guaranteed_init': pd.get('guaranteed_init', False),
                'fate_points_init': pd.get('fate_points_init', 0),
                'selected_card_init': pd.get('selected_card_init'),
                'soft_deltas': pd.get('soft_deltas'),
                'cr_counter_threshold': pd.get('cr_counter_threshold'),
                'cr_base_rate': pd.get('cr_base_rate'),
                'cr_state_probs': pd.get('cr_state_probs'),
                'fate_threshold': pd.get('fate_threshold'),
                'switch_allowed': pd.get('switch_allowed'),
                'switch_resets_progress': pd.get('switch_resets_progress'),
                'deactivate_on_early_hit': (pd.get('lifecycle') or {}).get('deactivate_on_early_hit', False),
                'depends_on': (pd.get('lifecycle') or {}).get('depends_on'),
            })
        store.pity = PityConfig(
            enabled=pity.get('enabled', True),
            pities=pities,
        )

        strategy = config.get('strategy', {})
        # P69：新格式 {key, params}，兼容旧格式 {type, name, params}
        if 'key' in strategy:
            store.strategy_key = str(strategy['key'])
        elif 'name' in strategy:
            store.strategy_key = str(strategy['name'])
        else:
            store.strategy_key = 'smart'
        store.strategy_params = strategy.get('params', {})
        # auto_wait：优先从顶层读取（P69 新位置），回退到旧 strategy 子 dict
        store.auto_wait = config.get('auto_wait', strategy.get('auto_wait', True))

        stop_cond = config.get('stop_condition', {})
        stop_type_raw = stop_cond.get('type', '所有池结束')
        from gacha_simulator.core.stop_condition import STOP_CONDITION_REGISTRY, stop_condition_key_to_type
        if stop_type_raw in STOP_CONDITION_REGISTRY:
            stop_type_resolved = stop_condition_key_to_type(stop_type_raw)
        else:
            stop_type_resolved = stop_type_raw
        store.stop_condition_type = stop_type_resolved
        store.stop_condition_params = stop_cond.get('params', {})

        for tc in config.get('target_cards', []):
            from ..core.config_store import TargetCardEntry
            store.target_cards.append(TargetCardEntry(
                card_id=tc.get('card_id', ''),
                quantity=tc.get('quantity', 1),
                pool_ids=tc.get('pools', []),
            ))

        for cd in config.get('card_defs', []):
            from ..core.config_store import CardDefEntry
            store.card_defs.append(CardDefEntry(
                card_id=cd.get('card_id', ''),
                name=cd.get('name', ''),
                rarity=cd.get('rarity', 'R'),
                pools=cd.get('pools', []),
                initial_count=cd.get('initial_count', 0),
                tags=cd.get('tags', {}),
                list_tags=cd.get('list_tags', {}),
            ))

        for rd in config.get('resource_defs', []):
            rid = rd.get('resource_id', '')
            store.resource_defs[rid] = rd.get('display_name', '')
            init_amt = rd.get('initial_amount', 0)
            if init_amt > 0:
                store.initial_resources[rid] = init_amt

        for ir in config.get('initial_resources', []):
            rid = ir.get('resource_id', '')
            amt = ir.get('amount', 0)
            if amt > 0:
                store.initial_resources[rid] = amt

        from ..core.config_store import GainRule, DayOverride
        for gr in config.get('resource_gain_rules', []):
            store.gain_rules.append(GainRule(
                rule_type=_gui_gain_type_to_store(gr.get('type', '每天')),
                param=str(gr.get('param', '')),
                gains={gr.get('resource_id', ''): gr.get('amount', 0)},
            ))

        for dor in config.get('resource_day_overrides', []):
            store.day_overrides.append(DayOverride(
                day=dor.get('day', 0),
                gains={dor.get('resource_id', ''): dor.get('amount', 0)},
            ))

        for cid, cw in config.get('card_weights', {}).items():
            store.card_weights[cid] = CardWeightEntry(
                desire_weight=cw.get('desire_weight', 1.0),
                miss_cost_weight=cw.get('miss_cost_weight', 1.0),
                card_value=cw.get('card_value', 1.0),
            )

        # Phase 2: 恢复模拟起始日期
        import datetime as _dt
        store.sim_start_date = config.get('sim_start_date') or _dt.date.today().isoformat()

        # P60：统一填充 featured_card_ids
        for pool in store.pools:
            pool.featured_card_ids = [d.card_id for d in pool.distribution if d.featured]

        self.refresh_from_store()

    def _sync_card_defs_from_pools(self):
        existing_defs = self.get_card_defs()
        existing_map = {d['card_id']: d for d in existing_defs}

        for i in range(self.pool_table.rowCount()):
            id_item = self.pool_table.item(i, 1)
            if not id_item or not id_item.text().strip():
                continue
            pid = id_item.text().strip()
            dist = self._pool_distributions.get(pid)

            if dist:
                for d in dist:
                    cid = d.get('card_id', '')
                    if not cid:
                        continue
                    if cid in existing_map:
                        pools = existing_map[cid].get('pools', [])
                        if pid not in pools:
                            pools.append(pid)
                        existing_map[cid]['pools'] = pools
                    else:
                        base = {'tags': {}, 'list_tags': {}, 'initial_count': 0}
                        if cid == '_no_card':
                            existing_map[cid] = {
                                'card_id': '_no_card',
                                'name': '空抽(仅资源)',
                                'rarity': '无',
                                'pools': [pid],
                                **base,
                            }
                        else:
                            existing_map[cid] = {
                                'card_id': cid,
                                'name': cid,
                                'rarity': d.get('rarity', 'R'),
                                'pools': [pid],
                                **base,
                            }
            else:
                for suffix, rarity in [('_ssr', 'SSR'), ('_sr', 'SR'), ('_r', 'R')]:
                    cid = f"{pid}{suffix}"
                    if cid in existing_map:
                        pools = existing_map[cid].get('pools', [])
                        if pid not in pools:
                            pools.append(pid)
                        existing_map[cid]['pools'] = pools
                    else:
                        existing_map[cid] = {
                            'card_id': cid,
                            'name': cid,
                            'rarity': rarity,
                            'pools': [pid],
                            'tags': {},
                            'list_tags': {},
                            'initial_count': 0,
                        }

        merged = list(existing_map.values())
        self.set_card_defs(merged)

    def _on_pool_cell_changed(self, row, col):
        if col == 6:
            cost_item = self.pool_table.item(row, 6)
            if cost_item:
                cost_text = cost_item.text().strip()
                for part in cost_text.split('&'):
                    part = part.strip()
                    if ':' in part:
                        rid = part.split(':')[0].strip()
                        self._ensure_resource_registered(rid)
        self._update_preview()
        if col == 3:
            self._sync_card_defs_from_pools()

    # _filter_card_defs / _search_card_defs / _on_card_def_changed 已由
    # P65 的 _filter_card_list 替代——见 _setup_card_def_tab 区域

    def _on_resource_def_changed(self, row, col):
        self._refresh_resource_combos()
        self._update_preview()

    def _get_resource_ids(self):
        ids = []
        for i in range(self.resource_defs_table.rowCount()):
            id_item = self.resource_defs_table.item(i, 0)
            if id_item and id_item.text().strip():
                ids.append(id_item.text().strip())
        return ids

    def _update_param_placeholder(self, row: int, gui_type: str):
        """更新指定行参数列的 placeholder 提示文本。"""
        widget = self.gain_rules_table.cellWidget(row, 1)
        if isinstance(widget, QLineEdit):
            widget.setPlaceholderText(_gain_rule_param_placeholder(gui_type))

    def _refresh_resource_combos(self):
        resource_ids = self._get_resource_ids()
        # gain_rules_table: 仅第 2 列（资源ID）是资源下拉框，跳过第 0 列（规则类型）
        for i in range(self.gain_rules_table.rowCount()):
            widget = self.gain_rules_table.cellWidget(i, 2)
            if isinstance(widget, QComboBox):
                current = widget.currentText()
                widget.blockSignals(True)
                widget.clear()
                widget.addItems(resource_ids)
                idx = widget.findText(current)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
                widget.blockSignals(False)
        # day_overrides_table: 仅第 1 列（资源ID）是资源下拉框
        for i in range(self.day_overrides_table.rowCount()):
            widget = self.day_overrides_table.cellWidget(i, 1)
            if isinstance(widget, QComboBox):
                current = widget.currentText()
                widget.blockSignals(True)
                widget.clear()
                widget.addItems(resource_ids)
                idx = widget.findText(current)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
                widget.blockSignals(False)

    def get_resource_defs(self):
        defs = []
        for i in range(self.resource_defs_table.rowCount()):
            id_item = self.resource_defs_table.item(i, 0)
            name_item = self.resource_defs_table.item(i, 1)
            amt_widget = self.resource_defs_table.cellWidget(i, 2)
            rid = id_item.text().strip() if id_item else ''
            name = name_item.text().strip() if name_item else ''
            amt = amt_widget.value() if amt_widget else 0
            if rid:
                defs.append({'resource_id': rid, 'display_name': name, 'initial_amount': amt})
        return defs

    def set_resource_defs(self, defs):
        self.resource_defs = list(defs)
        self.resource_defs_table.blockSignals(True)
        self.resource_defs_table.setRowCount(len(defs))
        for i, d in enumerate(defs):
            self.resource_defs_table.setItem(i, 0, QTableWidgetItem(d.get('resource_id', '')))
            self.resource_defs_table.setItem(i, 1, QTableWidgetItem(d.get('display_name', '')))
            spin = QSpinBox()
            spin.setRange(0, 9999999)
            spin.setValue(int(d.get('initial_amount', 0)))
            spin.setSingleStep(100)
            self.resource_defs_table.setCellWidget(i, 2, spin)
        self.resource_defs_table.blockSignals(False)
        self._refresh_resource_combos()

    def get_resource_gain_rules(self):
        rules = []
        for i in range(self.gain_rules_table.rowCount()):
            type_widget = self.gain_rules_table.cellWidget(i, 0)
            param_widget = self.gain_rules_table.cellWidget(i, 1)
            rid_widget = self.gain_rules_table.cellWidget(i, 2)
            amt_widget = self.gain_rules_table.cellWidget(i, 3)
            rtype = type_widget.currentText() if type_widget else '每天'
            param = param_widget.text().strip() if param_widget else ''
            rid = rid_widget.currentText() if rid_widget else ''
            amt = amt_widget.value() if amt_widget else 0
            if rid:
                rules.append({'type': rtype, 'param': param, 'resource_id': rid, 'amount': amt})
        return rules

    def set_resource_gain_rules(self, rules):
        self.resource_gain_rules = list(rules)
        resource_ids = self._get_resource_ids()
        rule_types = ["每天", "每N天", "每周几", "每月第几天", "每月第几周几", "指定日期"]
        self.gain_rules_table.blockSignals(True)
        self.gain_rules_table.setRowCount(len(rules))
        for i, r in enumerate(rules):
            type_combo = QComboBox()
            type_combo.addItems(rule_types)
            rtype = r.get('type', '每天')
            idx = type_combo.findText(rtype)
            if idx >= 0:
                type_combo.setCurrentIndex(idx)
            self.gain_rules_table.setCellWidget(i, 0, type_combo)

            param_edit = QLineEdit(str(r.get('param', '')))
            param_edit.setPlaceholderText(_gain_rule_param_placeholder(rtype))
            self.gain_rules_table.setCellWidget(i, 1, param_edit)
            type_combo.currentTextChanged.connect(lambda text, r=i: self._update_param_placeholder(r, text))

            rid_combo = QComboBox()
            rid_combo.addItems(resource_ids)
            rid = r.get('resource_id', '')
            idx = rid_combo.findText(rid)
            if idx >= 0:
                rid_combo.setCurrentIndex(idx)
            self.gain_rules_table.setCellWidget(i, 2, rid_combo)

            amt_spin = QSpinBox()
            amt_spin.setRange(0, 99999)
            amt_spin.setValue(int(r.get('amount', 0)))
            self.gain_rules_table.setCellWidget(i, 3, amt_spin)
        self.gain_rules_table.blockSignals(False)

    def get_resource_day_overrides(self):
        overrides = []
        for i in range(self.day_overrides_table.rowCount()):
            day_item = self.day_overrides_table.item(i, 0)
            rid_widget = self.day_overrides_table.cellWidget(i, 1)
            amt_widget = self.day_overrides_table.cellWidget(i, 2)
            try:
                day = int(day_item.text().strip()) if day_item else 0
            except (ValueError, AttributeError):
                day = 0
            rid = rid_widget.currentText() if rid_widget else ''
            amt = amt_widget.value() if amt_widget else 0
            if rid:
                overrides.append({'day': day, 'resource_id': rid, 'amount': amt})
        return overrides

    def set_resource_day_overrides(self, overrides):
        self.resource_day_overrides = list(overrides)
        resource_ids = self._get_resource_ids()
        self.day_overrides_table.blockSignals(True)
        self.day_overrides_table.setRowCount(len(overrides))
        for i, o in enumerate(overrides):
            self.day_overrides_table.setItem(i, 0, QTableWidgetItem(str(o.get('day', 0))))

            rid_combo = QComboBox()
            rid_combo.addItems(resource_ids)
            rid = o.get('resource_id', '')
            idx = rid_combo.findText(rid)
            if idx >= 0:
                rid_combo.setCurrentIndex(idx)
            self.day_overrides_table.setCellWidget(i, 1, rid_combo)

            amt_spin = QSpinBox()
            amt_spin.setRange(0, 99999)
            amt_spin.setValue(int(o.get('amount', 0)))
            self.day_overrides_table.setCellWidget(i, 2, amt_spin)
        self.day_overrides_table.blockSignals(False)

    def _auto_generate_resource_defs(self):
        defs = [
            {'resource_id': 'draw_resource', 'display_name': '抽卡资源'},
            {'resource_id': 'exchange_currency', 'display_name': '兑换货币'},
        ]
        self.set_resource_defs(defs)

    def _add_resource_def(self):
        row = self.resource_defs_table.rowCount()
        self.resource_defs_table.blockSignals(True)
        self.resource_defs_table.insertRow(row)
        self.resource_defs_table.setItem(row, 0, QTableWidgetItem(""))
        self.resource_defs_table.setItem(row, 1, QTableWidgetItem(""))
        spin = QSpinBox()
        spin.setRange(0, 9999999)
        spin.setValue(0)
        spin.setSingleStep(100)
        self.resource_defs_table.setCellWidget(row, 2, spin)
        self.resource_defs_table.blockSignals(False)

    def _remove_resource_def(self):
        rows = sorted([r.row() for r in self.resource_defs_table.selectionModel().selectedRows()], reverse=True)
        for row in rows:
            self.resource_defs_table.removeRow(row)
        self._refresh_resource_combos()
        self._update_preview()

    def _add_gain_rule(self):
        resource_ids = self._get_resource_ids()
        if not resource_ids:
            QMessageBox.warning(self, "提示", "请先在资源类型定义中注册资源ID")
            return
        row = self.gain_rules_table.rowCount()
        self.gain_rules_table.insertRow(row)
        rule_types = ["每天", "每N天", "每周几", "每月第几天", "每月第几周几", "指定日期"]
        type_combo = QComboBox()
        type_combo.addItems(rule_types)
        self.gain_rules_table.setCellWidget(row, 0, type_combo)
        param_edit = QLineEdit()
        param_edit.setPlaceholderText(_gain_rule_param_placeholder("每天"))
        self.gain_rules_table.setCellWidget(row, 1, param_edit)
        type_combo.currentTextChanged.connect(lambda text, r=row: self._update_param_placeholder(r, text))
        rid_combo = QComboBox()
        rid_combo.addItems(resource_ids)
        self.gain_rules_table.setCellWidget(row, 2, rid_combo)
        amt_spin = QSpinBox()
        amt_spin.setRange(0, 99999)
        amt_spin.setValue(0)
        self.gain_rules_table.setCellWidget(row, 3, amt_spin)

    def _remove_gain_rule(self):
        rows = sorted([r.row() for r in self.gain_rules_table.selectionModel().selectedRows()], reverse=True)
        for row in rows:
            self.gain_rules_table.removeRow(row)
        self._update_preview()

    def _add_day_override(self):
        resource_ids = self._get_resource_ids()
        if not resource_ids:
            QMessageBox.warning(self, "提示", "请先在资源类型定义中注册资源ID")
            return
        row = self.day_overrides_table.rowCount()
        self.day_overrides_table.insertRow(row)
        self.day_overrides_table.setItem(row, 0, QTableWidgetItem("0"))
        rid_combo = QComboBox()
        rid_combo.addItems(resource_ids)
        self.day_overrides_table.setCellWidget(row, 1, rid_combo)
        amt_spin = QSpinBox()
        amt_spin.setRange(0, 99999)
        amt_spin.setValue(0)
        self.day_overrides_table.setCellWidget(row, 2, amt_spin)

    def _remove_day_override(self):
        rows = sorted([r.row() for r in self.day_overrides_table.selectionModel().selectedRows()], reverse=True)
        for row in rows:
            self.day_overrides_table.removeRow(row)
        self._update_preview()

    def apply_to_store(self):
        if self._store is None or self._refreshing:
            return
        from gacha_simulator.core.strategy import strategy_type_to_key
        store = self._store

        # P56：保存旧池子的 epitomizable_cards 映射，避免 apply_to_store 中失丢
        _old_epitomizable = {p.pool_id: getattr(p, 'epitomizable_cards', [])
                             for p in store.pools}

        store.pools = []
        for i in range(self.pool_table.rowCount()):
            cb = self.pool_table.cellWidget(i, 0)
            def _item(col, default=''):
                it = self.pool_table.item(i, col)
                return it.text() if it else default
            pid = _item(1)
            pool_type = _item(3, '角色')
            cost_text = _item(6, 'draw_resource:160').strip()
            if ':' not in cost_text:
                try:
                    cost_text = f"draw_resource:{int(cost_text or 160)}"
                except ValueError:
                    cost_text = "draw_resource:160"

            start_day = int(_item(4, '0') or 0)
            duration = int(_item(5, '21') or 21)

            batch_size = 1
            batch_text = _item(7, '1').strip()
            if batch_text:
                try:
                    batch_size = int(batch_text)
                    if batch_size < 1:
                        batch_size = 1
                    elif batch_size > 1000:
                        batch_size = 1000
                except ValueError:
                    batch_size = 1

            dist_data = self._pool_distributions.get(pid)
            distribution = []
            if dist_data:
                for d in dist_data:
                    distribution.append(PoolDistEntry(
                        card_id=d.get('card_id', ''),
                        probability=d.get('probability', 0),
                        rarity=d.get('rarity', 'R'),
                        featured=d.get('featured', False),
                        resources_gained=d.get('resources_gained', {}),
                    ))

            bindings = {}
            if pool_type:
                bindings['type'] = pool_type

            store.pools.append(PoolEntry(
                enabled=cb.isChecked() if cb else True,
                pool_id=pid,
                name=_item(2),
                pool_type=pool_type,
                start_day=start_day,
                end_day=start_day + duration,
                cost=cost_text,
                distribution_template="",
                bindings=bindings,
                distribution=distribution,
                batch_size=batch_size,
                epitomizable_cards=_old_epitomizable.get(pid, []),
            ))

        store.pity.enabled = self.pity_enabled.isChecked()
        pities = []
        for pd in self._pity_defs:
            pities.append(PityDef(
                name=pd.get('name', ''),
                btype=pd.get('btype', 'soft_interval'),
                scope=pd.get('scope', 'ssr'),
                target_featured=pd.get('target_featured', False),
                deltas=pd.get('deltas'),
                threshold=pd.get('threshold'),
                counter_init=pd.get('counter_init', 0),
                guaranteed_init=pd.get('guaranteed_init', False),
                fate_points_init=pd.get('fate_points_init', 0),
                selected_card_init=pd.get('selected_card_init'),
                soft_start=pd.get('soft_start'),
                soft_end=pd.get('soft_end'),
                soft_increment=pd.get('soft_increment'),
                soft_deltas=pd.get('deltas') if pd.get('btype') == 'soft_step' else None,
                cr_counter_threshold=pd.get('cr_counter_threshold'),
                cr_base_rate=pd.get('cr_base_rate'),
                cr_state_probs=pd.get('cr_state_probs'),
                fate_threshold=pd.get('fate_threshold'),
                switch_allowed=pd.get('switch_allowed'),
                switch_resets_progress=pd.get('switch_resets_progress'),
                reset=pd.get('reset', ''),
                pools=tuple(pd.get('pools', ('*',))) if isinstance(pd.get('pools'), list) else (pd.get('pools', '*'),) if isinstance(pd.get('pools'), str) else pd.get('pools', ('*',)),
                deactivate_on_early_hit=pd.get('deactivate_on_early_hit', False),
                depends_on=pd.get('depends_on'),
            ))
        store.pity.pities = pities

        display_name = self.strategy_type.currentText()
        store.strategy_key = strategy_type_to_key(display_name)
        store.strategy_params = self._get_strategy_params_from_widgets()
        store.stop_condition_type = self.stop_condition_type.currentText()
        store.stop_condition_params = {}
        store.auto_wait = self.auto_wait.isChecked()

        store.target_cards = []
        for tc in self._get_target_cards():
            store.target_cards.append(TargetCardEntry(
                card_id=tc.get('card_id', ''),
                quantity=tc.get('quantity', 1),
                pool_ids=tc.get('pools', []),
            ))

        store.card_defs = []
        for cd in self.get_card_defs():
            store.card_defs.append(CardDefEntry(
                card_id=cd.get('card_id', ''),
                name=cd.get('name', ''),
                rarity=cd.get('rarity', 'R'),
                pools=cd.get('pools', []),
                initial_count=cd.get('initial_count', 0),
                tags=cd.get('tags', {}),
                list_tags=cd.get('list_tags', {}),
            ))

        store.resource_defs = {}
        store.initial_resources = {}
        for rd in self.get_resource_defs():
            rid = rd.get('resource_id', '')
            store.resource_defs[rid] = rd.get('display_name', '')
            init_amt = rd.get('initial_amount', 0)
            if init_amt > 0:
                store.initial_resources[rid] = init_amt

        store.gain_rules = []
        for gr in self.get_resource_gain_rules():
            store.gain_rules.append(GainRule(
                rule_type=_gui_gain_type_to_store(gr.get('type', '每天')),
                param=str(gr.get('param', '')),
                gains={gr.get('resource_id', ''): gr.get('amount', 0)},
            ))

        store.day_overrides = []
        for dor in self.get_resource_day_overrides():
            store.day_overrides.append(DayOverride(
                day=dor.get('day', 0),
                gains={dor.get('resource_id', ''): dor.get('amount', 0)},
            ))

        store.card_weights = {}
        weight_data = self._get_weight_data()
        for cid, w in weight_data.items():
            store.card_weights[cid] = CardWeightEntry(
                desire_weight=w.get('desire_weight', 1.0),
                miss_cost_weight=w.get('miss_cost_weight', 1.0),
                card_value=w.get('card_value', 1.0),
            )

        # P60：统一填充 featured_card_ids
        for pool in store.pools:
            pool.featured_card_ids = [d.card_id for d in pool.distribution if d.featured]

    def refresh_from_store(self):
        if self._store is None:
            return
        self._refreshing = True
        try:
            self._refresh_from_store_impl()
        finally:
            self._refreshing = False
        self._update_preview()  # 刷新完成后启动去抖预览（_refreshing=True 期间被跳过）

    def _refresh_from_store_impl(self):
        store = self._store

        pools_data = []
        self._pool_distributions = {}
        for p in store.pools:
            dist_list = None
            if p.distribution:
                dist_list = [{'card_id': d.card_id, 'probability': d.probability,
                              'rarity': d.rarity, 'featured': d.featured,
                              'resources_gained': d.resources_gained,}
                             for d in p.distribution]
                self._pool_distributions[p.pool_id] = dist_list

            pool_type = p.pool_type or (p.bindings.get('type', '角色') if p.bindings else '角色')
            pools_data.append({
                'enabled': p.enabled,
                'id': p.pool_id,
                'name': p.name,
                'type': pool_type,
                'start_day': p.start_day,
                'duration': p.end_day - p.start_day,
                'cost': p.cost,
                'note': '',
                'distribution': dist_list,
                'batch_size': getattr(p, 'batch_size', 1),
            })
        self._set_pool_table(pools_data)

        self.pity_enabled.setChecked(store.pity.enabled)
        self._pity_defs = []
        for p in store.pity.pities:
            # P55：扁平化字段
            pools_val = getattr(p, 'pools', ('*',))
            if isinstance(pools_val, tuple):
                pools_val = ','.join(pools_val) if pools_val != ('*',) else '*'
            self._pity_defs.append({
                'name': p.name,
                'btype': p.btype,
                'scope': getattr(p, 'scope', 'ssr'),
                'target_featured': getattr(p, 'target_featured', False),
                'deltas': getattr(p, 'deltas', None),
                'threshold': getattr(p, 'threshold', None),
                'counter_init': getattr(p, 'counter_init', 0),
                'soft_start': getattr(p, 'soft_start', None),
                'soft_end': getattr(p, 'soft_end', None),
                'soft_increment': getattr(p, 'soft_increment', None),
                'reset': getattr(p, 'reset', ''),
                'pools': pools_val,
                'guaranteed_init': getattr(p, 'guaranteed_init', False),
                'fate_points_init': getattr(p, 'fate_points_init', 0),
                'selected_card_init': getattr(p, 'selected_card_init', None),
                'soft_deltas': getattr(p, 'soft_deltas', None),
                'cr_counter_threshold': getattr(p, 'cr_counter_threshold', None),
                'cr_base_rate': getattr(p, 'cr_base_rate', None),
                'cr_state_probs': getattr(p, 'cr_state_probs', None),
                'fate_threshold': getattr(p, 'fate_threshold', None),
                'switch_allowed': getattr(p, 'switch_allowed', None),
                'switch_resets_progress': getattr(p, 'switch_resets_progress', None),
                'deactivate_on_early_hit': getattr(p, 'deactivate_on_early_hit', False),
                'depends_on': getattr(p, 'depends_on', None),
            })
        self.pity_list.clear()
        for pd in self._pity_defs:
            self.pity_list.addItem(pd['name'])
        if self._pity_defs:
            self.pity_list.setCurrentRow(0)

        # P69：通过 strategy_key 反向查找 display_name + _invalid_state 守卫
        from gacha_simulator.core.strategy import STRATEGY_REGISTRY as _sr
        meta = _sr.get(store.strategy_key)
        if meta is not None and meta._invalid_state is not None:
            # 插件加载失败——弹出警告并回退为 'smart'
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "策略插件加载失败",
                f"策略 '{store.strategy_key}' 的插件加载失败：\n{meta._invalid_state}\n\n"
                f"已自动回退为 'smart'。原始参数已保留，修复插件后可手动恢复。"
            )
            store._unknown_strategy_raw = {
                'key': store.strategy_key,
                'params': dict(store.strategy_params),
            }
            store.strategy_key = 'smart'
            store.strategy_params = {}
            # 持久化回退结果，避免每次启动都弹警告
            from gacha_simulator.paths import get_config_dir
            import os
            config_path = os.path.join(get_config_dir(), 'config.toml')
            from gacha_simulator.core.config_toml import save_toml
            save_toml(store, config_path)

        display_name = _sr[store.strategy_key].display_name if store.strategy_key in _sr else '按需追卡'
        strategy_idx = self._strategy_display_names.index(display_name) if display_name in self._strategy_display_names else 0
        self.strategy_type.setCurrentIndex(strategy_idx)
        self._set_strategy_params_to_widgets(store.strategy_params)
        stop_idx = self._stop_condition_display_names.index(store.stop_condition_type) if store.stop_condition_type in self._stop_condition_display_names else 0
        self.stop_condition_type.setCurrentIndex(stop_idx)
        self.auto_wait.setChecked(store.auto_wait)

        target_data = [{'card_id': tc.card_id, 'quantity': tc.quantity, 'pools': tc.pool_ids}
                       for tc in store.target_cards]
        self._set_target_cards(target_data)

        card_data = [{'card_id': cd.card_id, 'name': cd.name, 'rarity': cd.rarity, 'pools': cd.pools,
                      'initial_count': getattr(cd, 'initial_count', 0),
                      'tags': getattr(cd, 'tags', {}),
                      'list_tags': getattr(cd, 'list_tags', {})}
                     for cd in store.card_defs]
        self.set_card_defs(card_data)
        # P65：store 就绪后从 rarity_rank 动态填充稀有度下拉
        self._populate_card_rarity_filter()

        res_defs = [{'resource_id': rid, 'display_name': name,
                     'initial_amount': store.initial_resources.get(rid, 0)}
                    for rid, name in store.resource_defs.items()]
        if res_defs:
            self.set_resource_defs(res_defs)
        else:
            self._auto_generate_resource_defs()

        daily = _daily_income(store)

        gain_data = []
        for rule in store.gain_rules:
            for rid, amt in rule.gains.items():
                gain_data.append({
                    'type': _gain_rule_type_to_gui(rule.rule_type, rule.param),
                    'param': _gain_rule_param_to_gui(rule.rule_type, rule.param),
                    'resource_id': rid,
                    'amount': amt,
                })
        if gain_data:
            self.set_resource_gain_rules(gain_data)
        elif daily > 0:
            self.set_resource_gain_rules([{'type': '每天', 'param': '', 'resource_id': 'draw_resource', 'amount': daily}])

        override_data = []
        for do in store.day_overrides:
            for rid, amt in do.gains.items():
                override_data.append({'day': do.day, 'resource_id': rid, 'amount': amt})
        self.set_resource_day_overrides(override_data)

        weight_data = {}
        card_name_map = {cd.card_id: cd.name for cd in store.card_defs}
        for cid, cw in store.card_weights.items():
            weight_data[cid] = {
                'name': card_name_map.get(cid, cid),
                'desire_weight': cw.desire_weight,
                'miss_cost_weight': cw.miss_cost_weight,
                'card_value': cw.card_value,
            }
        if weight_data:
            self._set_weight_data(weight_data)

        # Phase 2: 同步模拟起始日期
        start_date_str = getattr(store, 'sim_start_date', None) or QDate.currentDate().toString('yyyy-MM-dd')
        try:
            qd = QDate.fromString(start_date_str, "yyyy-MM-dd")
            if qd.isValid():
                self.sim_start_date_edit.blockSignals(True)
                self.sim_start_date_edit.setDate(qd)
                self.sim_start_date_edit.blockSignals(False)
        except Exception:
            pass

        # P63：刷新溢出表格
        try:
            self._refresh_overflow_tab()
        except Exception:
            pass

        self._update_preview()


def _gain_rule_type_to_gui(rule_type: str, param: str = '') -> str:
    """将归一化后的 rule_type + param 转为 GUI 显示的类型标签。

    归一化后 rule_type 不再含冒号/参数后缀，类型判定完全依赖 rule_type + param。
    """
    if rule_type == 'every_n_days':
        if param in ('1', ''):
            return '每天'
        return '每N天'
    if rule_type == 'weekly':
        return '每周几'
    if rule_type == 'monthly_day':
        # 参数含逗号（月,日格式）→ "指定日期"；纯数字或空 → "每月第几天"
        if ',' in param:
            return '指定日期'
        return '每月第几天'
    if rule_type == 'monthly_week':
        return '每月第几周几'

    # 兼容旧格式（rule_type 中仍含冒号+参数，未归一化数据）
    if rule_type.startswith('every_n_days:'):
        n = rule_type.split(':')[1].strip()
        return '每天' if n == '1' else '每N天'
    if rule_type.startswith('monthly_day:'):
        param_str = rule_type.split(':', 1)[1].strip()
        return '指定日期' if ',' in param_str else '每月第几天'
    if rule_type.startswith('weekly:'):
        return '每周几'
    if rule_type.startswith('monthly_week:'):
        return '每月第几周几'

    return '每天'


def _gain_rule_param_to_gui(rule_type: str, param: str = '') -> str:
    """将归一化后的 rule_type + param 转为 GUI 显示的参数字符串。

    归一化后 param 独立承载参数值，不再从 rule_type 字符串中提取。
    """
    if rule_type == 'every_n_days':
        return param if param not in ('1', '') else ''
    if rule_type in ('weekly', 'monthly_day', 'monthly_week'):
        return param

    # 兼容旧格式（rule_type 中仍含冒号+参数）
    if ':' in rule_type:
        if rule_type.startswith('every_n_days:'):
            n = rule_type.split(':')[1].strip()
            return n if n != '1' else ''
        return rule_type.split(':', 1)[1].strip()

    return param if param else ''


def _gui_gain_type_to_store(gui_type: str) -> str:
    mapping = {
        '每天': 'every_n_days',
        '每N天': 'every_n_days',
        '每周几': 'weekly',
        '每月第几天': 'monthly_day',
        '每月第几周几': 'monthly_week',
        '指定日期': 'monthly_day',
    }
    return mapping.get(gui_type, 'every_n_days')


def _gain_rule_param_placeholder(gui_type: str) -> str:
    """返回规则类型对应的参数列 placeholder 提示文本。"""
    hints = {
        '每天': '无需参数',
        '每N天': '间隔天数，例：3',
        '每周几': '1–7（周一至周日），例：1',
        '每月第几天': '1–31，例：1',
        '每月第几周几': '周,日（1–5, 1–7），例：1,1',
        '指定日期': '月,日（1–12, 1–31），例：6,15',
    }
    return hints.get(gui_type, '请输入参数')


def _pity_start(pity):
    for p in pity.pities:
        if 'start' in p.params:
            try:
                return int(p.params['start'])
            except ValueError:
                pass
        if 'threshold' in p.params:
            try:
                return int(p.params['threshold'])
            except ValueError:
                pass
    return 80


def _pity_end(pity):
    for p in pity.pities:
        if 'end' in p.params:
            try:
                return int(p.params['end'])
            except ValueError:
                pass
    return 90


def _pity_counter_group(pity):
    counter_names = set(p.name for p in pity.pities)
    if len(counter_names) <= 1:
        return 0
    has_type_counters = any('_pity' in cn and cn != 'draw' for cn in counter_names)
    has_pool_counters = any(cn.startswith('draw_') and cn != 'draw' for cn in counter_names)
    if has_pool_counters:
        return 2
    if has_type_counters:
        return 1
    return 0


def _daily_income(store):
    for rule in store.gain_rules:
        if rule.rule_type == 'every_n_days' and (rule.param == '1' or rule.param == ''):
            amt = rule.gains.get('draw_resource', 0)
            if amt > 0:
                return int(amt)
    return 0
