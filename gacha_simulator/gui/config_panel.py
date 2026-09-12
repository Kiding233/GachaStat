#!/usr/bin/env python3
"""配置面板"""

from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QLabel, QCheckBox, QScrollArea, QSplitter,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox, QMessageBox, QAbstractItemView,
    QDateEdit, QCalendarWidget, QInputDialog, QCompleter, QRadioButton,
)
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QTimer
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import QSizePolicy

from ..core.config_store import (
    CardDefEntry,
    PityDef, PityConfig, GainRule, DayOverride, TargetCardEntry, CardWeightEntry,
    BannerEntry, BannerPoolEntry, LifecycleRuleEntry, DAY, derive_pool_type_from_distribution,
    MilestoneDef,   # ← P58 里程碑奖励（apply_to_store 写回）
    SelectVoucherDef,   # ← P78 自选券候选集（apply_to_store 写回）
)
from ..core.overflow import OverflowBand
from ..core.pity import BEHAVIOR_REGISTRY
from ..core.resource_lifecycle import ResourceLifecycle, ResourceLifecycleConfig   # P77


# P79 4d2b1：表达式保留字——条件 id 不得与运算符同名，否则表达式无法解析
_EXPR_RESERVED_WORDS = ('and', 'or', 'not')


def _expr_flat_operands(node, op: str):
    """把同运算符的链拉平为操作数列表（结合律等价）；顶层不是该运算符时返回 None。

    `a or (b or c)` 与 `a or b or c` 的 AST 分别是右嵌套与左嵌套——按结构比对会被
    结合律打败，故单选识别必须按「拉平后的操作数集合」判定。
    """
    if node[0] != op:
        return None
    out = []

    def collect(n):
        if n[0] == op:
            collect(n[1])
            collect(n[2])
        else:
            out.append(n)

    collect(node)
    return out


def _collect_expr_ids(expr: str):
    """收集表达式引用的全部条件 id（去重、保序）。表达式非法时抛出."""
    from gacha_simulator.core.stop_condition_expr import parse_stop_condition_expr

    found = []

    def walk(node):
        if node[0] == 'id':
            if node[1] not in found:
                found.append(node[1])
        elif node[0] == 'not':
            walk(node[1])
        else:
            walk(node[1])
            walk(node[2])

    walk(parse_stop_condition_expr(expr))
    return found


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


class RandomCardPoolDialog(QDialog):
    """P58 随机卡池编辑弹窗（§3.8.3）——四列勾选/卡/稀有度/权重表格 + 抽取张数。

    result() 返回 {candidates, weights, count}——仅勾选的卡进入 candidates，
    对应权重进入 weights（未勾选卡权重忽略，但回填时保留以支持重复编辑往返）。
    """

    def __init__(self, store, pool_data, parent=None):
        super().__init__(parent)
        self._store = store
        self.setWindowTitle("编辑随机卡池")
        self.setMinimumSize(700, 500)

        layout = QVBoxLayout(self)

        self.pool_table = QTableWidget()
        self.pool_table.setColumnCount(4)
        self.pool_table.setHorizontalHeaderLabels(["勾选", "卡", "稀有度", "权重"])
        self.pool_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.pool_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.pool_table.setMaximumHeight(360)
        layout.addWidget(self.pool_table)

        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("抽取张数:"))
        self.count_spin = QSpinBox()
        # REVIEW-R1-FIX: ISSUE-301 —— 抽取张数下限 1：与 §3.7 解析期 _build_milestone 的
        #   count >= 1 校验一致（count=0 时 _resolve_bonus 静默无效、无提示），杜绝 round-trip 断裂。
        self.count_spin.setMinimum(1)
        self.count_spin.setRange(1, 999)
        self.count_spin.setValue(1)
        count_row.addWidget(self.count_spin)
        count_row.addStretch()
        layout.addLayout(count_row)

        hint = QLabel("提示: 仅勾选的卡参与抽取，权重越大中选概率越高")
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._populate(pool_data)

    def _populate(self, pool_data):
        pool_data = pool_data or {}
        candidates = set(pool_data.get('candidates', []) or [])
        weights = pool_data.get('weights', []) or []
        self._weights = dict(zip(candidates, weights))  # cid → float（保持既有权重供回填）
        try:
            self.count_spin.setValue(int(pool_data.get('count', 1)))
        except (TypeError, ValueError):
            self.count_spin.setValue(1)

        cards = []
        if self._store is not None:
            cards = list(self._store.card_defs)
        self.pool_table.setRowCount(len(cards))
        for i, entry in enumerate(cards):
            cid = entry.card_id
            rarity = (entry.rarity or '?').upper()

            cb = QCheckBox()
            cb.setChecked(cid in candidates)
            self.pool_table.setCellWidget(i, 0, cb)

            name_item = QTableWidgetItem(f"{entry.name} ({cid})")
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.pool_table.setItem(i, 1, name_item)

            rarity_item = QTableWidgetItem(rarity)
            rarity_item.setFlags(rarity_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.pool_table.setItem(i, 2, rarity_item)

            weight_spin = QDoubleSpinBox()
            weight_spin.setRange(0.0, 100000.0)
            weight_spin.setDecimals(2)
            weight_spin.setValue(float(self._weights.get(cid, 1.0)))
            self.pool_table.setCellWidget(i, 3, weight_spin)

    def result(self):
        """返回 {candidates, weights, count}——仅勾选卡进 candidates/weights。"""
        candidates = []
        weights = []
        for i in range(self.pool_table.rowCount()):
            name_item = self.pool_table.item(i, 1)
            cb = self.pool_table.cellWidget(i, 0)
            if name_item is None or cb is None:
                continue
            cid = name_item.text().rsplit('(', 1)[-1].rstrip(')')
            if cb.isChecked():
                candidates.append(cid)
                spin = self.pool_table.cellWidget(i, 3)
                weights.append(float(spin.value()) if spin is not None else 1.0)
        return {
            'candidates': candidates,
            'weights': weights,
            'count': int(self.count_spin.value()),
        }


class MilestoneAlternateDialog(QDialog):
    """P78 交替奖励项编辑对话框（ISSUE-110）——编辑单个交替项 dict。

    交替项与 bonus_reward 同为 cards/resources/random_cards 三字段，编辑逻辑
    （固定卡多选 / 资源表 / 随机池）与 bonus_reward 区同构。ISSUE-706：交替项
    random_cards 编辑状态由本对话框自持（打开从 item['random_cards'] 载入、
    Accept 整体写回）——不引入 name 级平行存储；未 Accept 编辑关闭即丢弃。
    ISSUE-605：打开时从 store.resource_defs 实时填充资源选项（不缓存旧快照）。

    result() 返回编辑后的 reward dict（{'cards','resources','random_cards'}）。
    """

    def __init__(self, store, item_data, parent=None):
        super().__init__(parent)
        self._store = store
        self.setWindowTitle("编辑交替奖励项")
        self.setMinimumSize(520, 420)

        layout = QVBoxLayout(self)

        # ── 固定卡牌（多选）──
        layout.addWidget(QLabel("固定赠送卡牌:"))
        self.cards_list = QListWidget()
        self.cards_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.cards_list.setMaximumHeight(110)
        layout.addWidget(self.cards_list)
        card_ids = set((item_data or {}).get('cards', []))
        if store is not None:
            for entry in store.card_defs:
                cid = entry.card_id
                display = f"{cid} ({entry.name})" if entry.name else cid
                it = QListWidgetItem(display)
                it.setData(Qt.ItemDataRole.UserRole, cid)
                self.cards_list.addItem(it)          # 先 addItem 再 setSelected（未入列表的 item 选中态不生效）
                it.setSelected(cid in card_ids)

        # ── 资源（可编辑下拉 + 数量）──
        layout.addWidget(QLabel("赠送资源:"))
        self.resources_table = QTableWidget()
        self.resources_table.setColumnCount(2)
        self.resources_table.setHorizontalHeaderLabels(["资源", "数量"])
        self.resources_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.resources_table.setMaximumHeight(120)
        layout.addWidget(self.resources_table)

        res_btn = QHBoxLayout()
        add_r = QPushButton("添加")
        add_r.clicked.connect(self._add_resource_row)
        rem_r = QPushButton("移除选中")
        rem_r.clicked.connect(self._remove_resource_row)
        res_btn.addWidget(add_r)
        res_btn.addWidget(rem_r)
        res_btn.addStretch()
        layout.addLayout(res_btn)

        # 回填既有资源
        resources = (item_data or {}).get('resources', {}) or {}
        for rid, amt in resources.items():
            self._append_resource_row(rid, amt)

        # ── 随机卡池（复用 RandomCardPoolDialog，ISSUE-706 自持）──
        layout.addWidget(QLabel("随机卡池:"))
        self.rand_pool_list = QListWidget()
        self.rand_pool_list.setMaximumHeight(90)
        layout.addWidget(self.rand_pool_list)

        rand_btn = QHBoxLayout()
        edit_rp = QPushButton("编辑")
        edit_rp.clicked.connect(self._edit_random_pool)
        add_rp = QPushButton("添加")
        add_rp.clicked.connect(self._add_random_pool)
        rem_rp = QPushButton("移除选中")
        rem_rp.clicked.connect(self._remove_random_pool)
        rand_btn.addWidget(edit_rp)
        rand_btn.addWidget(add_rp)
        rand_btn.addWidget(rem_rp)
        rand_btn.addStretch()
        layout.addLayout(rand_btn)

        self._random_pools = [dict(p) for p in ((item_data or {}).get('random_cards', []) or [])]
        self._selected_pool_idx = 0
        self._refresh_random_pool_summary()

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    # ── 资源行操作 ──
    def _append_resource_row(self, rid='', amount=0):
        row = self.resources_table.rowCount()
        self.resources_table.insertRow(row)
        combo = QComboBox()
        known = list(self._store.resource_defs.keys()) if self._store else []
        combo.addItems(known)
        combo.setEditable(True)
        if rid:
            combo.setEditText(rid)      # ISSUE-605：打开时实时填充（可编辑兜底手输）
        self.resources_table.setCellWidget(row, 0, combo)
        amt_item = QTableWidgetItem()
        amt_item.setData(Qt.ItemDataRole.EditRole, float(amount))
        self.resources_table.setItem(row, 1, amt_item)

    def _add_resource_row(self):
        self._append_resource_row()

    def _remove_resource_row(self):
        row = self.resources_table.currentRow()
        if row >= 0:
            self.resources_table.removeRow(row)

    # ── 随机池操作（ISSUE-706 自持）──
    def _refresh_random_pool_summary(self):
        self.rand_pool_list.clear()
        for i, pool in enumerate(self._random_pools):
            names = [c[:6] for c in pool.get('candidates', [])]
            self.rand_pool_list.addItem(f"池{i+1}: {', '.join(names[:3])}{'...' if len(names)>3 else ''}, 抽{pool.get('count',1)}张")

    def _add_random_pool(self):
        self._random_pools.append({'candidates': [], 'weights': [], 'count': 1})
        self._refresh_random_pool_summary()

    def _remove_random_pool(self):
        idx = self.rand_pool_list.currentRow()
        if 0 <= idx < len(self._random_pools):
            self._random_pools.pop(idx)
            self._refresh_random_pool_summary()

    def _edit_random_pool(self):
        idx = self.rand_pool_list.currentRow()
        if idx < 0 and self._random_pools:
            idx = 0
        if idx < 0 or idx >= len(self._random_pools):
            self._add_random_pool()
            idx = len(self._random_pools) - 1
        dialog = RandomCardPoolDialog(self._store, self._random_pools[idx], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._random_pools[idx] = dialog.result()
            self._refresh_random_pool_summary()

    def result(self):
        """返回编辑后的 reward dict。"""
        cards = []
        for i in range(self.cards_list.count()):
            it = self.cards_list.item(i)
            if it.isSelected():
                cid = it.data(Qt.ItemDataRole.UserRole)
                if cid:
                    cards.append(cid)
        resources = {}
        for i in range(self.resources_table.rowCount()):
            combo = self.resources_table.cellWidget(i, 0)
            amt_item = self.resources_table.item(i, 1)
            rid = ''
            if combo is not None and hasattr(combo, 'currentText'):
                rid = combo.currentText().strip()
            if rid and amt_item:
                try:
                    amount = float(amt_item.data(Qt.ItemDataRole.EditRole) or 0)
                except (TypeError, ValueError):
                    amount = 0.0
                if amount != 0:
                    resources[rid] = amount
        return {
            'cards': cards,
            'resources': resources,
            'random_cards': [dict(p) for p in self._random_pools],
        }


class ConfigPanel(QWidget):

    config_changed = pyqtSignal(dict)

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
        # P79 4c1a：顶部只读提示读 self._store.end_time（单一实现点），store 变更后刷新
        self._refresh_stop_condition_hint()

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

        # P78（方案 X）：资源定义独立 Tab——左列表 + 右详情，与卡牌定义/保底/累抽格式统一。
        # 数据层 resource_defs: Dict[str, str] 一字不动（11 个分析面板零改动）。
        resource_def_tab = QWidget()
        self._setup_resource_def_tab(resource_def_tab)
        self.left_tabs.addTab(resource_def_tab, "资源定义")

        resource_tab_scroll = QScrollArea()
        resource_tab_scroll.verticalScrollBar().setSingleStep(15)
        resource_tab_scroll.setWidgetResizable(True)
        resource_tab_content = QWidget()
        resource_tab_layout = QVBoxLayout(resource_tab_content)
        self._setup_resource_tab(resource_tab_layout)
        resource_tab_scroll.setWidget(resource_tab_content)
        self.left_tabs.addTab(resource_tab_scroll, "资源获取")

        pool_tab_scroll = QScrollArea()
        pool_tab_scroll.verticalScrollBar().setSingleStep(15)
        pool_tab_scroll.setWidgetResizable(True)
        pool_tab_content = QWidget()
        pool_tab_layout = QVBoxLayout(pool_tab_content)
        self._setup_pool_config(pool_tab_layout)
        pool_tab_layout.addStretch()
        pool_tab_scroll.setWidget(pool_tab_content)
        self.left_tabs.addTab(pool_tab_scroll, "卡池管理")

        pity_tab_scroll = QScrollArea()
        pity_tab_scroll.verticalScrollBar().setSingleStep(15)
        pity_tab_scroll.setWidgetResizable(True)
        pity_tab_content = QWidget()
        pity_tab_layout = QVBoxLayout(pity_tab_content)
        self._setup_pity_config(pity_tab_layout)
        pity_tab_layout.addStretch()
        pity_tab_scroll.setWidget(pity_tab_content)
        self.left_tabs.addTab(pity_tab_scroll, "保底机制")

        # P58：累抽奖励 Tab——位于「保底机制」Tab 之后（§3.8.5a）
        milestone_tab_scroll = QScrollArea()
        milestone_tab_scroll.verticalScrollBar().setSingleStep(15)
        milestone_tab_scroll.setWidgetResizable(True)
        milestone_tab_content = QWidget()
        milestone_tab_layout = QVBoxLayout(milestone_tab_content)
        self._setup_milestone_config(milestone_tab_layout)
        milestone_tab_layout.addStretch()
        milestone_tab_scroll.setWidget(milestone_tab_content)
        self.left_tabs.addTab(milestone_tab_scroll, "累抽奖励")

        strategy_tab_scroll = QScrollArea()
        strategy_tab_scroll.verticalScrollBar().setSingleStep(15)
        strategy_tab_scroll.setWidgetResizable(True)
        strategy_tab_content = QWidget()
        strategy_tab_layout = QVBoxLayout(strategy_tab_content)
        self._setup_strategy_tab(strategy_tab_layout)
        strategy_tab_layout.addStretch()
        strategy_tab_scroll.setWidget(strategy_tab_content)
        self.left_tabs.addTab(strategy_tab_scroll, "抽卡策略")

        # P79 5.7：停止条件子标签页——必须处于 QScrollArea 内，否则
        # gui/wheel_blocker.py 的全局事件过滤器在找不到 QAbstractScrollArea 祖先时
        # 仍 return True，吞掉 QComboBox / QAbstractSpinBox 的滚轮而不转发。
        stop_condition_tab_scroll = QScrollArea()
        stop_condition_tab_scroll.verticalScrollBar().setSingleStep(15)
        stop_condition_tab_scroll.setWidgetResizable(True)
        stop_condition_tab_content = QWidget()
        stop_condition_tab_layout = QVBoxLayout(stop_condition_tab_content)
        self._setup_stop_condition_tab(stop_condition_tab_layout)
        stop_condition_tab_layout.addStretch()
        stop_condition_tab_scroll.setWidget(stop_condition_tab_content)
        self.left_tabs.addTab(stop_condition_tab_scroll, "停止条件")

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

        splitter.setSizes([880, 320])

    def _setup_pool_config(self, parent):
        """「卡池管理」Tab——P61 Ph8 重写（§3.10）。

        替换旧「卡池配置」Tab（扁平池表格 + 池子模板）。新结构：
        左栏 Banner 列表（筛选 + 添加/移除/复制/批量创建）；
        右栏 Banner 详情（基础字段 4 个 + 两子标签页「池」/「生命周期」）。
        Banner 是用户配置的一等单位——内含若干 Pool（cost/batch/rewards 内联），
        Pool 之间经 Lifecycle 规则自动切换。池子模板系统移除（§3.10.6），
        由「复制 Banner」与「批量创建」替代。
        """
        self._banner_defs = []
        self._current_banner_row: int = -1

        main_layout = QHBoxLayout()

        # ── 左栏：Banner 列表 ──
        left_layout = QVBoxLayout()
        self.banner_filter = QLineEdit()
        self.banner_filter.setPlaceholderText("筛选 Banner 名或 ID...")
        self.banner_filter.textChanged.connect(self._filter_banners)
        left_layout.addWidget(self.banner_filter)

        self.banner_list = QListWidget()
        self.banner_list.currentRowChanged.connect(self._on_banner_selected)
        self.banner_list.itemChanged.connect(self._on_banner_item_changed)
        left_layout.addWidget(self.banner_list, 1)

        banner_btn_layout = QHBoxLayout()
        add_banner_btn = QPushButton("添加")
        add_banner_btn.clicked.connect(self._add_banner)
        remove_banner_btn = QPushButton("移除")
        remove_banner_btn.clicked.connect(self._remove_banner)
        duplicate_banner_btn = QPushButton("复制")
        duplicate_banner_btn.clicked.connect(self._duplicate_banner)
        batch_banner_btn = QPushButton("批量创建...")
        batch_banner_btn.clicked.connect(self._batch_create_banners)
        banner_btn_layout.addWidget(add_banner_btn)
        banner_btn_layout.addWidget(remove_banner_btn)
        banner_btn_layout.addWidget(duplicate_banner_btn)
        banner_btn_layout.addWidget(batch_banner_btn)
        left_layout.addLayout(banner_btn_layout)
        main_layout.addLayout(left_layout, 1)

        # ── 右栏：Banner 详情 ──
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        detail_group = QGroupBox("Banner 详情")
        detail_group.setEnabled(False)
        self._banner_detail_group = detail_group
        detail_form = QFormLayout(detail_group)

        self.banner_name_edit = QLineEdit()
        self.banner_name_edit.setPlaceholderText("显示名称")
        self.banner_name_edit.textChanged.connect(self._flush_banner_current_detail)
        detail_form.addRow("名称:", self.banner_name_edit)

        self.banner_id_edit = QLineEdit()
        self.banner_id_edit.setPlaceholderText("唯一标识符")
        self.banner_id_edit.textChanged.connect(self._flush_banner_current_detail)
        detail_form.addRow("ID:", self.banner_id_edit)

        self.banner_max_draws_spin = QSpinBox()
        self.banner_max_draws_spin.setRange(0, 1000000)
        self.banner_max_draws_spin.setValue(0)
        self.banner_max_draws_spin.setSpecialValueText("无限制")
        self.banner_max_draws_spin.setToolTip("Banner 级硬上限抽数；0 = 无限制")
        self.banner_max_draws_spin.valueChanged.connect(self._flush_banner_current_detail)
        detail_form.addRow("最大抽数:", self.banner_max_draws_spin)

        window_layout = QHBoxLayout()
        window_layout.addWidget(QLabel("从"))
        self.banner_from_spin = QDoubleSpinBox()
        self.banner_from_spin.setRange(0.0, 99999.0)
        self.banner_from_spin.setDecimals(1)
        self.banner_from_spin.setValue(0.0)
        self.banner_from_spin.valueChanged.connect(self._flush_banner_current_detail)
        window_layout.addWidget(self.banner_from_spin)
        window_layout.addWidget(QLabel("到"))
        self.banner_until_spin = QDoubleSpinBox()
        self.banner_until_spin.setRange(0.0, 99999.0)
        self.banner_until_spin.setDecimals(1)
        self.banner_until_spin.setValue(21.0)
        self.banner_until_spin.valueChanged.connect(self._flush_banner_current_detail)
        window_layout.addWidget(self.banner_until_spin)
        self.banner_permanent_cb = QCheckBox("永久")
        self.banner_permanent_cb.setToolTip("勾选 = available_until=None（永久开放）")
        self.banner_permanent_cb.stateChanged.connect(self._on_banner_permanent_toggled)
        window_layout.addWidget(self.banner_permanent_cb)
        detail_form.addRow("时间窗口(天):", window_layout)
        right_layout.addWidget(detail_group)

        # ── 两子标签页：池 / 生命周期 ──
        self.pool_sub_tabs = QTabWidget()

        pool_tab = QWidget()
        pool_layout = QVBoxLayout(pool_tab)
        pool_layout.setContentsMargins(0, 0, 0, 0)

        # 上半：Pool 列表（5 列，删除卡牌摘要——奖励表下半内联）
        pool_list_group = QGroupBox("池子列表")
        pool_list_layout = QVBoxLayout(pool_list_group)
        self.banner_pool_table = QTableWidget()
        self.banner_pool_table.setColumnCount(6)
        self.banner_pool_table.setHorizontalHeaderLabels(["ID", "成本", "批次", "最大抽数", "一次性", "不计保底"])
        pool_header = self.banner_pool_table.horizontalHeader()
        pool_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        pool_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        pool_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        pool_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        pool_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        pool_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        # P61（2026-08-04）：成本列 Stretch 自适应（占固定列后的剩余空间，
        # 不挤压批次/最大抽数等 Fixed 列）；ID 缩 1/2、批次/最大抽数加宽
        self.banner_pool_table.setColumnWidth(0, 55)
        self.banner_pool_table.setColumnWidth(2, 80)
        self.banner_pool_table.setColumnWidth(3, 115)
        self.banner_pool_table.setColumnWidth(4, 55)
        self.banner_pool_table.setColumnWidth(5, 75)
        self.banner_pool_table.verticalHeader().setVisible(False)
        self.banner_pool_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.banner_pool_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.banner_pool_table.setMinimumHeight(110)
        self.banner_pool_table.itemChanged.connect(self._on_pool_table_item_changed)
        self.banner_pool_table.itemSelectionChanged.connect(self._on_pool_selected)
        pool_list_layout.addWidget(self.banner_pool_table)
        pool_btn_layout = QHBoxLayout()
        add_pool_btn = QPushButton("添加")
        add_pool_btn.clicked.connect(self._add_pool_to_banner)
        remove_pool_btn = QPushButton("移除选中")
        remove_pool_btn.clicked.connect(self._remove_pool_from_banner)
        pool_btn_layout.addWidget(add_pool_btn)
        pool_btn_layout.addWidget(remove_pool_btn)
        pool_btn_layout.addStretch()
        pool_list_layout.addLayout(pool_btn_layout)
        pool_layout.addWidget(pool_list_group)

        # 下半：选中池 rewards 表（5 列）
        reward_group = QGroupBox("选中池分布")
        reward_layout = QVBoxLayout(reward_group)
        self.reward_table = QTableWidget()
        self.reward_table.setColumnCount(5)
        self.reward_table.setHorizontalHeaderLabels(["卡ID", "概率(%)", "稀有度", "Featured", "资源获取"])
        reward_header = self.reward_table.horizontalHeader()
        reward_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        reward_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        reward_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        reward_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        reward_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.reward_table.setColumnWidth(1, 90)
        self.reward_table.setColumnWidth(2, 60)
        self.reward_table.setColumnWidth(3, 60)
        self.reward_table.verticalHeader().setVisible(False)
        self.reward_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.reward_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.reward_table.setMinimumHeight(130)
        reward_layout.addWidget(self.reward_table)
        reward_btn_layout = QHBoxLayout()
        add_reward_btn = QPushButton("添加")
        add_reward_btn.clicked.connect(self._add_reward_row)
        remove_reward_btn = QPushButton("移除选中")
        remove_reward_btn.clicked.connect(self._remove_reward_rows)
        scale_reward_btn = QPushButton("缩放至100%")
        scale_reward_btn.clicked.connect(self._scale_rewards_to_100)
        import_reward_btn = QPushButton("从其他池导入...")
        import_reward_btn.clicked.connect(self._import_rewards_from_pool)
        self._reward_total_label = QLabel("合计: 0%")
        self._reward_total_label.setStyleSheet("color: #888;")
        reward_btn_layout.addWidget(add_reward_btn)
        reward_btn_layout.addWidget(remove_reward_btn)
        reward_btn_layout.addWidget(scale_reward_btn)
        reward_btn_layout.addWidget(import_reward_btn)
        reward_btn_layout.addStretch()
        reward_btn_layout.addWidget(self._reward_total_label)
        reward_layout.addLayout(reward_btn_layout)
        pool_layout.addWidget(reward_group)
        self.pool_sub_tabs.addTab(pool_tab, "池")

        # 生命周期子标签页（5 列）
        lifecycle_tab = QWidget()
        lifecycle_layout = QVBoxLayout(lifecycle_tab)
        lifecycle_layout.setContentsMargins(0, 0, 0, 0)
        self.lifecycle_table = QTableWidget()
        self.lifecycle_table.setColumnCount(5)
        self.lifecycle_table.setHorizontalHeaderLabels(["关联池", "条件", "阈值", "动作", "目标"])
        lc_header = self.lifecycle_table.horizontalHeader()
        for ci in range(5):
            lc_header.setSectionResizeMode(ci, QHeaderView.ResizeMode.Stretch)
        self.lifecycle_table.verticalHeader().setVisible(False)
        self.lifecycle_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.lifecycle_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lifecycle_table.itemChanged.connect(self._on_lifecycle_item_changed)
        lifecycle_layout.addWidget(self.lifecycle_table)
        lc_btn_layout = QHBoxLayout()
        add_lc_btn = QPushButton("添加")
        add_lc_btn.clicked.connect(self._add_lifecycle_row)
        remove_lc_btn = QPushButton("移除选中")
        remove_lc_btn.clicked.connect(self._remove_lifecycle_rows)
        lc_btn_layout.addWidget(add_lc_btn)
        lc_btn_layout.addWidget(remove_lc_btn)
        lc_btn_layout.addStretch()
        lifecycle_layout.addLayout(lc_btn_layout)
        self.pool_sub_tabs.addTab(lifecycle_tab, "生命周期")

        right_layout.addWidget(self.pool_sub_tabs, 1)
        main_layout.addWidget(right_widget, 2)

        parent.addLayout(main_layout)

    # ══════════════════════════════════════════════════════════════════
    # P61 Ph8：卡池管理 Tab —— Banner / Pool / Rewards / Lifecycle 操作
    # （替换旧「卡池配置」扁平池表格 + 池子模板系统，§3.10）
    # ══════════════════════════════════════════════════════════════════

    def _iter_pool_rewards(self):
        """遍历所有 Banner 的所有 Pool 的所有 rewards（§3.10.7 正向同步统一入口）。

        返回 (full_key, reward) 生成器——full_key = {banner_id}.{pool_id} 全限定键
        （与逐池统计键/`card_defs[].pools` 键空间同口径，Ph3 展平视图）。
        替代旧 pool_table 行遍历，供 _sync_card_defs_from_pools /
        _register_resources_from_pools / _compute_pools_map 等消费。
        """
        for b in self._banner_defs:
            bid = b.get('id', '')
            for p in b.get('pools', []):
                full_key = f"{bid}.{p.get('id', '')}"
                for r in p.get('rewards', []) or []:
                    yield full_key, r

    def _selected_banner_idx(self):
        """当前选中 Banner 在 _banner_defs 的下标；无选中返回 -1。"""
        row = self.banner_list.currentRow()
        if row < 0 or row >= self.banner_list.count():
            return -1
        item = self.banner_list.item(row)
        if item is None:
            return -1
        return item.data(Qt.ItemDataRole.UserRole)

    def _refresh_banner_list(self, select_idx=-1):
        self.banner_list.blockSignals(True)
        self.banner_list.clear()
        for i, b in enumerate(self._banner_defs):
            item = QListWidgetItem(b.get('name', '') or b.get('id', ''))
            item.setData(Qt.ItemDataRole.UserRole, i)
            # §3.10.1 列表行 enabled 勾选开关（不勾选 = 该 Banner 不参与模拟）
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if b.get('enabled', True)
                               else Qt.CheckState.Unchecked)
            self.banner_list.addItem(item)
        if select_idx >= 0 and select_idx < len(self._banner_defs):
            self.banner_list.setCurrentRow(select_idx)
        self.banner_list.blockSignals(False)
        # P77：Banner 增删后刷新生命周期「对齐卡池」下拉（数据源为 _banner_defs）
        self._refresh_lifecycle_combos()

    def _on_banner_item_changed(self, item):
        """Banner 列表行勾选状态 → 写回 _banner_defs[idx]['enabled']。"""
        bidx = item.data(Qt.ItemDataRole.UserRole)
        if 0 <= bidx < len(self._banner_defs):
            self._banner_defs[bidx]['enabled'] = \
                item.checkState() == Qt.CheckState.Checked

    def _filter_banners(self, text):
        text = text.lower()
        for i in range(self.banner_list.count()):
            item = self.banner_list.item(i)
            bidx = item.data(Qt.ItemDataRole.UserRole)
            b = self._banner_defs[bidx] if 0 <= bidx < len(self._banner_defs) else {}
            match = (text in b.get('id', '').lower()) or (text in b.get('name', '').lower())
            item.setHidden(not match)

    def _add_banner(self):
        self._flush_banner_current_detail()
        existing_ids = {b['id'] for b in self._banner_defs}
        idx = 1
        while f'banner_{idx}' in existing_ids:
            idx += 1
        banner = {
            'id': f'banner_{idx}',
            'name': f'Banner {idx}',
            'enabled': True,
            'max_draws': None,
            'available_from': 0.0,
            'available_until': 21.0,
            'pools': [{
                'id': 'main',
                'cost': 'draw_resource:160',
                'batch_size': 1,
                'excludes_all_pity': False,
                'max_draws': None,
                'exchange_card_id': None,
                'epitomizable_cards': [],
                # P61（2026-08-04 用户决策）：无默认3卡——奖励表为空，每池独立配置
                'rewards': [],
            }],
            'lifecycle': [],
        }
        self._banner_defs.append(banner)
        self._refresh_banner_list(len(self._banner_defs) - 1)
        self._on_banner_selected(len(self._banner_defs) - 1)
        # §3.10.7：新增 Banner 的默认奖励卡注册进「卡牌定义」Tab
        self._sync_card_defs_from_pools()
        self._update_preview()

    def _remove_banner(self):
        bidx = self._selected_banner_idx()
        if bidx < 0:
            QMessageBox.information(self, "提示", "请先选择一个 Banner")
            return
        # §3.10.2 移除安全检查：检查保底绑定引用
        refs = self._collect_banner_references(bidx)
        if refs:
            resp = QMessageBox.question(
                self, "Banner 被引用",
                "该 Banner 的 Pool 被以下保底规则绑定，删除后将自动解除绑定：\n\n"
                + '\n'.join(f"  · {r}" for r in refs[:10])
                + ("\n  ..." if len(refs) > 10 else "") + "\n\n确认删除？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
        banner_id = self._banner_defs[bidx].get('id', '')
        self._unbind_pity_pools_for_banner(banner_id)
        del self._banner_defs[bidx]
        self._refresh_banner_list()
        self._clear_banner_detail()
        self._update_preview()

    def _duplicate_banner(self):
        bidx = self._selected_banner_idx()
        if bidx < 0:
            QMessageBox.information(self, "提示", "请先选择一个 Banner")
            return
        import copy
        src = self._banner_defs[bidx]
        new_banner = copy.deepcopy(src)
        # P61（2026-08-04 用户决策）：复制 id 去重——连续复制不产出重复 id（B2）
        base = f"{src['id']}_copy"
        existing = {b['id'] for b in self._banner_defs}
        new_id = base
        n = 2
        while new_id in existing:
            new_id = f"{base}_{n}"
            n += 1
        new_banner['id'] = new_id
        new_banner['name'] = f"{src['name']} 副本"
        self._banner_defs.append(new_banner)
        self._refresh_banner_list(len(self._banner_defs) - 1)
        self._on_banner_selected(len(self._banner_defs) - 1)
        self._sync_card_defs_from_pools()
        self._update_preview()

    def _batch_create_banners(self):
        """§3.10.6 批量创建对话框：模板 Banner / 数量 / ID前缀 / 名称前缀 / 起始/间隔。"""
        if not self._banner_defs:
            QMessageBox.information(self, "提示", "请先创建一个 Banner 作为模板")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("批量创建 Banner")
        form = QFormLayout(dialog)

        tmpl_combo = QComboBox()
        for b in self._banner_defs:
            tmpl_combo.addItem(f"{b.get('name', '')} ({b.get('id', '')})")
        form.addRow("模板 Banner:", tmpl_combo)

        count_spin = QSpinBox()
        count_spin.setRange(1, 50)
        count_spin.setValue(8)
        form.addRow("数量:", count_spin)

        id_prefix = QLineEdit('banner_')
        form.addRow("ID前缀:", id_prefix)
        name_prefix = QLineEdit('角色池')
        form.addRow("名称前缀:", name_prefix)
        start_spin = QDoubleSpinBox()
        start_spin.setRange(0.0, 99999.0)
        start_spin.setDecimals(1)
        start_spin.setValue(0.0)
        form.addRow("起始时间(天):", start_spin)
        interval_spin = QDoubleSpinBox()
        interval_spin.setRange(0.0, 9999.0)
        interval_spin.setDecimals(1)
        interval_spin.setValue(21.0)
        form.addRow("间隔(天):", interval_spin)

        # P61（2026-08-04 用户决策）：批量创建加预览（A3 / §3.10.6）
        preview_list = QListWidget()
        preview_list.setMaximumHeight(140)
        form.addRow("预览:", preview_list)

        def _update_batch_preview():
            preview_list.clear()
            pfx = id_prefix.text().strip() or 'banner_'
            npfx = name_prefix.text().strip() or '池'
            n = count_spin.value()
            start = start_spin.value()
            interval = interval_spin.value()
            # D-2（2026-08-04）：预览反映 id 去重——与生成逻辑一致的跳号
            existing = {b['id'] for b in self._banner_defs}
            for i in range(n):
                bid = f"{pfx}{i+1}"
                while bid in existing:
                    i += 1
                    bid = f"{pfx}{i+1}"
                existing.add(bid)
                preview_list.addItem(
                    f"{bid}  {npfx}{i+1}  "
                    f"[{round(start + i * interval, 1)}, {round(start + (i + 1) * interval, 1)}]")

        count_spin.valueChanged.connect(lambda *_: _update_batch_preview())
        id_prefix.textChanged.connect(lambda *_: _update_batch_preview())
        name_prefix.textChanged.connect(lambda *_: _update_batch_preview())
        start_spin.valueChanged.connect(lambda *_: _update_batch_preview())
        interval_spin.valueChanged.connect(lambda *_: _update_batch_preview())
        _update_batch_preview()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        import copy
        src = copy.deepcopy(self._banner_defs[tmpl_combo.currentIndex()])
        existing_ids = {b['id'] for b in self._banner_defs}
        n = count_spin.value()
        start = start_spin.value()
        interval = interval_spin.value()
        pfx = id_prefix.text().strip() or 'banner_'
        npfx = name_prefix.text().strip() or '池'
        for i in range(n):
            bid = f"{pfx}{i+1}"
            while bid in existing_ids:
                i += 1
                bid = f"{pfx}{i+1}"
            existing_ids.add(bid)
            b = copy.deepcopy(src)
            b['id'] = bid
            b['name'] = f"{npfx}{i+1}"
            b['available_from'] = round(start + i * interval, 1)
            b['available_until'] = round(start + (i + 1) * interval, 1)
            for pool in b.get('pools', []):
                for r in pool.get('rewards', []):
                    cid = r.get('card_id', '')
                    if '{id}' in cid:
                        r['card_id'] = cid.replace('{id}', bid)
            self._banner_defs.append(b)
        self._refresh_banner_list(len(self._banner_defs) - 1)
        self._sync_card_defs_from_pools()
        self._update_preview()

    def _collect_banner_references(self, bidx):
        """收集引用该 Banner Pool 的保底规则（§3.10.2 移除安全检查）。"""
        banner = self._banner_defs[bidx]
        banner_id = banner.get('id', '')
        pool_ids = [p.get('id', '') for p in banner.get('pools', [])]
        full_keys = {f"{banner_id}.{pid}" for pid in pool_ids}
        refs = []
        for pd in getattr(self, '_pity_defs', []):
            pools = pd.get('pools', ('*',))
            if not pools or pools == ('*',):
                continue
            import fnmatch as _fn
            for key in full_keys:
                if any(_fn.fnmatch(key, ptn) for ptn in pools):
                    refs.append(f"保底「{pd.get('name', '')}」")
                    break
        return refs

    def _unbind_pity_pools_for_banner(self, banner_id):
        """删除 Banner 前解除其 Pool 上的精确保底绑定（§3.10.2；* 通配绑定保留）。"""
        for pd in getattr(self, '_pity_defs', []):
            pools = list(pd.get('pools', ('*',)))
            if pools == ['*'] or not pools:
                continue
            kept = [p for p in pools if not p.startswith(banner_id + '.')]
            if kept != pools:
                pd['pools'] = tuple(kept) if kept else []

    def _clear_banner_detail(self):
        self._current_banner_row = -1
        self._banner_detail_group.setEnabled(False)
        self.banner_name_edit.setText('')
        self.banner_id_edit.setText('')
        self.banner_max_draws_spin.setValue(0)
        self.banner_from_spin.setValue(0.0)
        self.banner_until_spin.setValue(0.0)
        self.banner_permanent_cb.setChecked(True)
        self.banner_pool_table.setRowCount(0)
        self.reward_table.setRowCount(0)
        self.lifecycle_table.setRowCount(0)

    def _on_banner_selected(self, row):
        self._flush_banner_current_detail()
        bidx = self._selected_banner_idx()
        if bidx < 0:
            self._clear_banner_detail()
            return
        self._current_banner_row = bidx
        self._banner_detail_group.setEnabled(True)
        b = self._banner_defs[bidx]

        self.banner_name_edit.blockSignals(True)
        self.banner_id_edit.blockSignals(True)
        self.banner_max_draws_spin.blockSignals(True)
        self.banner_from_spin.blockSignals(True)
        self.banner_until_spin.blockSignals(True)
        self.banner_permanent_cb.blockSignals(True)
        self.banner_name_edit.setText(b.get('name', ''))
        self.banner_id_edit.setText(b.get('id', ''))
        self.banner_max_draws_spin.setValue(int(b.get('max_draws') or 0))
        self.banner_from_spin.setValue(float(b.get('available_from') or 0.0))
        until = b.get('available_until')
        permanent = until is None
        self.banner_permanent_cb.setChecked(permanent)
        self.banner_until_spin.setValue(float(until) if not permanent else 0.0)
        self.banner_until_spin.setEnabled(not permanent)
        self.banner_name_edit.blockSignals(False)
        self.banner_id_edit.blockSignals(False)
        self.banner_max_draws_spin.blockSignals(False)
        self.banner_from_spin.blockSignals(False)
        self.banner_until_spin.blockSignals(False)
        self.banner_permanent_cb.blockSignals(False)

        self._refresh_pool_table()

    def _on_banner_permanent_toggled(self, checked):
        self.banner_until_spin.setEnabled(not checked)
        self._flush_banner_current_detail()

    def _flush_banner_current_detail(self):
        """从右栏基础字段读取 → 写回 _banner_defs[current]（仿 _flush_pity_current_detail）。"""
        bidx = self._current_banner_row
        if bidx < 0 or bidx >= len(self._banner_defs):
            return
        b = self._banner_defs[bidx]
        b['name'] = self.banner_name_edit.text().strip()
        new_id = self.banner_id_edit.text().strip() or b.get('id', '')
        _prev_bid = b.get('id', '')
        if new_id != _prev_bid:
            # §3.10.3 id 变更 → 级联更新保底绑定/卡牌归属中的全限定键
            # （P77：同时改写生命周期规则的 expire_banner 引用）
            self._rename_banner_references(_prev_bid, new_id)
        b['id'] = new_id
        if _prev_bid and new_id != _prev_bid and hasattr(self, '_lifecycle_banner_combo'):
            # P77：下拉候选随 _banner_defs 变更重建；控件原值若指向被重命名的 banner，
            # 须同步指向新 id，否则保留逻辑会把旧 id 当悬垂项留下、写回时覆盖已改写的值
            _was = self._lifecycle_banner_combo.currentText()
            self._refresh_lifecycle_banner_combo(preserve_current=False)
            _tgt = new_id if _was == _prev_bid else _was
            _bi = self._lifecycle_banner_combo.findText(_tgt)
            if _bi >= 0:
                self._lifecycle_banner_combo.setCurrentIndex(_bi)
        md = self.banner_max_draws_spin.value()
        b['max_draws'] = int(md) if md > 0 else None
        b['available_from'] = self.banner_from_spin.value()
        b['available_until'] = None if self.banner_permanent_cb.isChecked() \
            else self.banner_until_spin.value()
        # 更新列表项文本：按 bidx 的 UserRole 定位，不用 currentItem()——切换选中时
        # currentItem 已是用户新点击的项而 bidx 仍是旧选中值，会把旧 banner 名写到
        # 新点击项上（点击 banner 名字随机变化的 bug）
        for i in range(self.banner_list.count()):
            it = self.banner_list.item(i)
            if it is not None and it.data(Qt.ItemDataRole.UserRole) == bidx:
                it.setText(b.get('name', '') or b.get('id', ''))
                break
        self._update_preview()

    def _rename_banner_references(self, old_id, new_id):
        """Banner id 变更 → 级联更新 _pity_defs 绑定与 card_defs 归属中的全限定键。

        §3.10.3：id 可编辑，变更时更新引用，避免保底绑定/目标归属指向旧 id 静默失配。
        """
        if not old_id or old_id == new_id:
            return
        for pd in getattr(self, '_pity_defs', []):
            pools = list(pd.get('pools', ('*',)))
            if pools == ['*'] or not pools:
                continue
            pools = [f"{new_id}.{p.split('.', 1)[1]}" if p.startswith(old_id + '.') else p
                     for p in pools]
            pd['pools'] = tuple(pools)
        # card_defs pools 全限定键同步（Ph3 展平视图口径）
        existing = self.get_card_defs()
        changed = False
        for cd in existing:
            pools = cd.get('pools', [])
            pools = [f"{new_id}.{p.split('.', 1)[1]}" if p.startswith(old_id + '.') else p
                     for p in pools]
            if pools != cd.get('pools', []):
                cd['pools'] = pools
                changed = True
        if changed:
            self.set_card_defs(existing)
        # P77：资源生命周期规则的到期对齐目标同步改写。不改写则该规则因 banner
        # 悬垂在 apply_to_store 重建时被静默过滤（重命名 banner 即丢失引用它的规则）
        for d in self.resource_defs:
            if d.get('expire_banner') == old_id:
                d['expire_banner'] = new_id

    # ── Pool 操作 ──

    def _selected_pool_idx(self):
        """当前选中 Pool 在 _banner_defs[bidx]['pools'] 的下标；无选中返回 -1。"""
        bidx = self._current_banner_row
        if bidx < 0 or bidx >= len(self._banner_defs):
            return -1
        rows = self.banner_pool_table.selectionModel().selectedRows()
        if not rows:
            return -1
        row = rows[0].row()
        pools = self._banner_defs[bidx].get('pools', [])
        if row < 0 or row >= len(pools):
            return -1
        return row

    def _refresh_pool_table(self):
        bidx = self._current_banner_row
        self.banner_pool_table.blockSignals(True)
        self.banner_pool_table.setRowCount(0)
        if bidx < 0 or bidx >= len(self._banner_defs):
            self.banner_pool_table.blockSignals(False)
            self.reward_table.setRowCount(0)
            self.lifecycle_table.setRowCount(0)
            return
        pools = self._banner_defs[bidx].get('pools', [])
        self.banner_pool_table.setRowCount(len(pools))
        for i, p in enumerate(pools):
            self.banner_pool_table.setItem(i, 0, QTableWidgetItem(p.get('id', '')))
            self.banner_pool_table.setItem(i, 1, QTableWidgetItem(p.get('cost', 'draw_resource:160')))
            batch_spin = QSpinBox()
            batch_spin.setRange(1, 100)
            batch_spin.setValue(int(p.get('batch_size', 1)))
            batch_spin.valueChanged.connect(
                lambda val, r=i: self._on_pool_batch_changed(r, val))
            self.banner_pool_table.setCellWidget(i, 2, batch_spin)
            # 最大抽数（列 3）：0 = 无限制；一次性时禁用（max_draws 由 batch_size 决定）
            md = p.get('max_draws')
            is_once = md is not None and md == p.get('batch_size', 1)
            md_spin = QSpinBox()
            md_spin.setRange(0, 1000000)
            md_spin.setSpecialValueText("无限制")
            md_spin.setValue(int(md) if md is not None else 0)
            md_spin.setEnabled(not is_once)
            md_spin.setToolTip("池级硬上限抽数，抽满自动关闭；0 = 无限制")
            md_spin.valueChanged.connect(
                lambda val, r=i: self._on_pool_max_draws_changed(r, val))
            self.banner_pool_table.setCellWidget(i, 3, md_spin)
            once_cb = QCheckBox()
            once_cb.setChecked(is_once)
            once_cb.setToolTip("一次性池（max_draws=batch_size，DECISION-1）")
            once_cb.stateChanged.connect(
                lambda ch, r=i: self._on_pool_once_toggled(r, ch))
            self.banner_pool_table.setCellWidget(i, 4, once_cb)
            excl_cb = QCheckBox()
            excl_cb.setChecked(p.get('excludes_all_pity', False))
            excl_cb.setToolTip("excludes_all_pity——不计保底")
            excl_cb.stateChanged.connect(
                lambda ch, r=i: self._on_pool_excl_toggled(r, ch))
            self.banner_pool_table.setCellWidget(i, 5, excl_cb)
        self.banner_pool_table.blockSignals(False)
        # P61（2026-08-04 用户决策）：默认不选中任何池——分布表不显示（选中后经
        # _on_pool_selected 显示）；lifecycle 表为 Banner 级规则、保持显示。
        self.reward_table.setRowCount(0)
        self._refresh_lifecycle_table()

    def _on_pool_table_item_changed(self, item):
        """Pool ID / 成本内联编辑 → 写回（§3.10.4）。"""
        bidx = self._current_banner_row
        if bidx < 0:
            return
        row = item.row()
        pools = self._banner_defs[bidx].get('pools', [])
        if row < 0 or row >= len(pools):
            return
        if item.column() == 0:
            old_id = pools[row].get('id', '')
            new_id = item.text().strip()
            if new_id != old_id:
                # §3.10.4 id 变更 → 级联更新 lifecycle 规则引用与保底绑定全限定键
                self._rename_pool_references(bidx, old_id, new_id)
            pools[row]['id'] = new_id
            self._refresh_lifecycle_table()  # 关联池/目标下拉同步
        elif item.column() == 1:
            pools[row]['cost'] = item.text().strip()
            # §3.10.7 正向同步：成本资源注册
            for part in item.text().strip().split('&'):
                part = part.strip()
                if ':' in part:
                    self._ensure_resource_registered(part.split(':')[0].strip())

    def _rename_pool_references(self, bidx, old_id, new_id):
        """Pool id 变更 → 级联更新 lifecycle 规则（pool/target）与保底绑定。

        §3.10.4：id 内联编辑，变更时更新引用，杜绝悬空 pool_draws 规则 / switch_to 指向旧 id。
        """
        if not old_id or old_id == new_id or bidx < 0 or bidx >= len(self._banner_defs):
            return
        b = self._banner_defs[bidx]
        for rule in b.get('lifecycle', []):
            if rule.get('pool') == old_id:
                rule['pool'] = new_id
            if rule.get('target') == old_id:
                rule['target'] = new_id
        # 保底绑定全限定键 {banner}.{old_id} → {banner}.{new_id}
        bid = b.get('id', '')
        for pd in getattr(self, '_pity_defs', []):
            pools = list(pd.get('pools', ('*',)))
            if pools == ['*'] or not pools:
                continue
            pools = [f"{bid}.{new_id}" if p == f"{bid}.{old_id}" else p for p in pools]
            pd['pools'] = tuple(pools)

    def _on_pool_batch_changed(self, row, val):
        bidx = self._current_banner_row
        if bidx < 0:
            return
        pools = self._banner_defs[bidx].get('pools', [])
        if row < 0 or row >= len(pools):
            return
        pools[row]['batch_size'] = int(val)
        # 一次性池语义联动：max_draws 随 batch_size 同步（DECISION-1），最大抽数 spin 跟随
        if pools[row].get('max_draws') is not None:
            pools[row]['max_draws'] = int(val)
            md_spin = self.banner_pool_table.cellWidget(row, 3)
            if md_spin is not None:
                md_spin.blockSignals(True)
                md_spin.setValue(int(val))
                md_spin.blockSignals(False)
        # D-1（2026-08-04）：同步一次性勾选显示——max_draws == batch_size 时勾选，
        # 避免改批次使 max_draws 恰好等于 batch_size 时勾选状态陈旧
        once_cb = self.banner_pool_table.cellWidget(row, 4)
        if once_cb is not None:
            once_cb.blockSignals(True)
            once_cb.setChecked(pools[row].get('max_draws') is not None
                               and pools[row].get('max_draws') == pools[row].get('batch_size', 1))
            once_cb.blockSignals(False)

    def _on_pool_max_draws_changed(self, row, val):
        """最大抽数（列 3）变更 → 写回 max_draws（0=无限制），联动一次性勾选。"""
        bidx = self._current_banner_row
        if bidx < 0:
            return
        pools = self._banner_defs[bidx].get('pools', [])
        if row < 0 or row >= len(pools):
            return
        pools[row]['max_draws'] = None if int(val) == 0 else int(val)
        # 联动一次性勾选：max_draws == batch_size → 勾选；否则不勾选
        once_cb = self.banner_pool_table.cellWidget(row, 4)
        if once_cb is not None:
            once_cb.blockSignals(True)
            once_cb.setChecked(pools[row]['max_draws'] is not None
                               and pools[row]['max_draws'] == pools[row].get('batch_size', 1))
            once_cb.blockSignals(False)

    def _on_pool_once_toggled(self, row, checked):
        bidx = self._current_banner_row
        if bidx < 0:
            return
        pools = self._banner_defs[bidx].get('pools', [])
        if row < 0 or row >= len(pools):
            return
        if checked:
            pools[row]['max_draws'] = int(pools[row].get('batch_size', 1))
        else:
            pools[row]['max_draws'] = None
        # 最大抽数 spin 联动：一次性时禁用并显示 batch_size
        md_spin = self.banner_pool_table.cellWidget(row, 3)
        if md_spin is not None:
            md_spin.blockSignals(True)
            md_spin.setValue(int(pools[row]['max_draws'])
                             if pools[row]['max_draws'] is not None else 0)
            md_spin.setEnabled(not checked)
            md_spin.blockSignals(False)

    def _on_pool_excl_toggled(self, row, checked):
        bidx = self._current_banner_row
        if bidx < 0:
            return
        pools = self._banner_defs[bidx].get('pools', [])
        if row < 0 or row >= len(pools):
            return
        pools[row]['excludes_all_pity'] = bool(checked)

    def _on_pool_selected(self):
        self._refresh_reward_table()

    def _add_pool_to_banner(self):
        bidx = self._current_banner_row
        if bidx < 0:
            QMessageBox.information(self, "提示", "请先选择一个 Banner")
            return
        pools = self._banner_defs[bidx].get('pools', [])
        used = {p.get('id', '') for p in pools}
        n = 1
        new_id = 'pool_1'
        while new_id in used:
            n += 1
            new_id = f'pool_{n}'
        pools.append({
            'id': new_id,
            'cost': 'draw_resource:160',
            'batch_size': 1,
            'excludes_all_pity': False,
            'max_draws': None,
            'exchange_card_id': None,
            'epitomizable_cards': [],
            # P61（2026-08-04 用户决策）：无默认3卡——奖励表为空，每池独立配置
            'rewards': [],
        })
        self._refresh_pool_table()
        # P61（2026-08-04 用户决策）：默认不选中新池
        self._sync_card_defs_from_pools()
        self._update_preview()

    def _remove_pool_from_banner(self):
        bidx = self._current_banner_row
        if bidx < 0:
            return
        pools = self._banner_defs[bidx].get('pools', [])
        rows = self.banner_pool_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "提示", "请先选择要移除的 Pool")
            return
        row = rows[0].row()
        if row < 0 or row >= len(pools):
            return
        del pools[row]
        self._refresh_pool_table()
        self._update_preview()

    # ── Rewards 操作（§3.10.5） ──

    def _current_reward_pool(self):
        """返回 (bidx, pool dict) 或 (None, None)。"""
        bidx = self._current_banner_row
        pidx = self._selected_pool_idx()
        if bidx < 0 or pidx < 0:
            return None, None
        pools = self._banner_defs[bidx].get('pools', [])
        if pidx >= len(pools):
            return None, None
        return bidx, pools[pidx]

    def _refresh_reward_table(self):
        self.reward_table.blockSignals(True)
        self.reward_table.setRowCount(0)
        bidx, pool = self._current_reward_pool()
        if pool is None:
            self.reward_table.blockSignals(False)
            self._reward_total_label.setText("合计: 0%")
            return
        rewards = pool.get('rewards', [])
        self.reward_table.setRowCount(len(rewards))
        for i, r in enumerate(rewards):
            self._set_reward_row(i, r)
        self.reward_table.blockSignals(False)
        self._update_reward_total()

    def _set_reward_row(self, row, r):
        card_combo = QComboBox()
        card_combo.setEditable(True)
        card_combo.addItems(self._registered_card_labels())
        # P61（2026-08-04 用户决策）：QCompleter 前缀搜索（§3.10.5 / A2）
        completer = QCompleter(self._registered_card_labels(), card_combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        card_combo.setCompleter(completer)
        card_combo.setCurrentText(r.get('card_id', ''))
        card_combo.currentTextChanged.connect(
            lambda text, rr=row: self._on_reward_card_changed(rr, text))
        self.reward_table.setCellWidget(row, 0, card_combo)

        prob_spin = QDoubleSpinBox()
        prob_spin.setRange(0.0, 100.0)
        prob_spin.setDecimals(3)
        prob_spin.setSingleStep(0.1)
        prob_spin.setValue(float(r.get('probability', 0.0)))
        prob_spin.valueChanged.connect(
            lambda val, rr=row: self._on_reward_prob_changed(rr, val))
        self.reward_table.setCellWidget(row, 1, prob_spin)

        rarity_label = QLabel(r.get('rarity', ''))
        rarity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rarity_label.setStyleSheet("color: #888; background: #f0f0f0;")
        self.reward_table.setCellWidget(row, 2, rarity_label)

        featured_cb = QCheckBox()
        featured_cb.setChecked(bool(r.get('featured', False)))
        featured_cb.stateChanged.connect(
            lambda ch, rr=row: self._on_reward_featured_toggled(rr, ch))
        self.reward_table.setCellWidget(row, 3, featured_cb)

        res_edit = QLineEdit()
        # P61（2026-08-04 用户决策）：补回灰字提示（旧分布表有，新奖励表丢失）
        res_edit.setPlaceholderText("resource_id:amount,...")
        rg = r.get('resources_gained', {}) or {}
        res_edit.setText(','.join(f"{k}:{v}" for k, v in rg.items()))
        res_edit.textChanged.connect(
            lambda text, rr=row: self._on_reward_resources_changed(rr, text))
        self.reward_table.setCellWidget(row, 4, res_edit)

    def _registered_card_labels(self):
        """「卡牌定义」Tab 已注册卡牌 → 显示格式 card_id（名称）。"""
        labels = []
        for d in self.get_card_defs():
            cid = d.get('card_id', '')
            name = d.get('name', '')
            labels.append(f"{cid}（{name}）" if name and name != cid else cid)
        return labels

    def _registered_rarities(self) -> List[str]:
        """「卡牌定义」Tab 已使用的稀有度列表（去重，大写；SSR/SR/R 优先排序）。

        P61（2026-08-04 用户决策）：card_obtained rarity 取值控件动态填充（A4）。
        """
        seen: List[str] = []
        for d in self.get_card_defs():
            r = str(d.get('rarity', '')).upper()
            if r and r not in seen:
                seen.append(r)
        for r in ['SSR', 'SR', 'R']:
            if r in seen:
                seen.remove(r)
                seen.insert(0, r)
        return seen or ['SSR', 'SR', 'R']

    @staticmethod
    def _card_id_from_label(text):
        return text.split('（')[0].strip()

    def _current_reward(self, rr):
        bidx, pool = self._current_reward_pool()
        if pool is None:
            return None
        rewards = pool.get('rewards', [])
        if rr < 0 or rr >= len(rewards):
            return None
        return rewards[rr]

    def _on_reward_card_changed(self, row, text):
        r = self._current_reward(row)
        if r is None:
            return
        cid = self._card_id_from_label(text)
        r['card_id'] = cid
        # 稀有度自动解析：从卡牌定义查找（§3.10.5）
        for d in self.get_card_defs():
            if d.get('card_id') == cid:
                r['rarity'] = d.get('rarity', '')
                break
        widget = self.reward_table.cellWidget(row, 2)
        if widget is not None:
            widget.setText(r.get('rarity', ''))

    def _on_reward_prob_changed(self, row, val):
        r = self._current_reward(row)
        if r is not None:
            r['probability'] = float(val)
        self._update_reward_total()

    def _on_reward_featured_toggled(self, row, checked):
        r = self._current_reward(row)
        if r is not None:
            r['featured'] = bool(checked)

    def _on_reward_resources_changed(self, row, text):
        r = self._current_reward(row)
        if r is None:
            return
        rg = {}
        for part in text.split(','):
            part = part.strip()
            if ':' in part:
                rid, _, amt = part.partition(':')
                try:
                    rg[rid.strip()] = float(amt)
                except ValueError:
                    continue
                self._ensure_resource_registered(rid.strip())
        r['resources_gained'] = rg

    def _update_reward_total(self):
        total = 0.0
        for i in range(self.reward_table.rowCount()):
            spin = self.reward_table.cellWidget(i, 1)
            if spin is not None and hasattr(spin, 'value'):
                total += spin.value()
        total = round(total, 3)
        color = "#2e7d32" if 99.9 <= total <= 100.1 else "#c62828"
        self._reward_total_label.setText(f"合计: {total}%")
        self._reward_total_label.setStyleSheet(f"color: {color};")

    def _add_reward_row(self):
        bidx, pool = self._current_reward_pool()
        if pool is None:
            QMessageBox.information(self, "提示", "请先选择一个 Pool")
            return
        pool.setdefault('rewards', []).append({
            'card_id': '',
            'probability': 0.0,
            'rarity': '',
            'featured': False,
            'resources_gained': {},
        })
        row = len(pool['rewards']) - 1
        self.reward_table.setRowCount(len(pool['rewards']))
        self._set_reward_row(row, pool['rewards'][row])
        self._update_reward_total()

    def _remove_reward_rows(self):
        bidx, pool = self._current_reward_pool()
        if pool is None:
            return
        rows = sorted([r.row() for r in self.reward_table.selectionModel().selectedRows()],
                      reverse=True)
        if not rows:
            QMessageBox.information(self, "提示", "请先选择要移除的奖励行")
            return
        rewards = pool.get('rewards', [])
        for row in rows:
            if 0 <= row < len(rewards):
                del rewards[row]
        self._refresh_reward_table()

    def _scale_rewards_to_100(self):
        """§3.10.5 缩放至 100%：按比例调整所有行概率。"""
        bidx, pool = self._current_reward_pool()
        if pool is None:
            return
        rewards = pool.get('rewards', [])
        total = sum(r.get('probability', 0.0) for r in rewards)
        if total <= 0:
            return
        for r in rewards:
            r['probability'] = round(r.get('probability', 0.0) / total * 100.0, 3)
        self._refresh_reward_table()

    def _import_rewards_from_pool(self):
        """§3.10.6 从其他池导入 rewards：一键填入当前池。"""
        bidx, pool = self._current_reward_pool()
        if pool is None:
            QMessageBox.information(self, "提示", "请先选择一个 Pool")
            return
        candidates = []
        for bi, b in enumerate(self._banner_defs):
            for pi, p in enumerate(b.get('pools', [])):
                key = f"{b.get('id', '')}.{p.get('id', '')}"
                if (bi, pi) == (bidx, self._selected_pool_idx()):
                    continue
                candidates.append((key, bi, pi))
        if not candidates:
            QMessageBox.information(self, "提示", "没有其他可导入的池")
            return
        keys = [c[0] for c in candidates]
        choice, ok = QInputDialog.getItem(self, "从其他池导入", "选择来源池:", keys, 0, False)
        if not ok:
            return
        src = next(c for c in candidates if c[0] == choice)
        src_pool = self._banner_defs[src[1]]['pools'][src[2]]
        pool['rewards'] = [dict(r) for r in src_pool.get('rewards', [])]
        self._refresh_reward_table()
        self._sync_card_defs_from_pools()
        self._update_preview()

    # ── Lifecycle 操作（§3.10.5） ──

    def _current_banner_pool_ids(self):
        """当前 Banner 的 Pool ID 列表（供关联池/目标下拉动态填充）。"""
        bidx = self._current_banner_row
        if bidx < 0 or bidx >= len(self._banner_defs):
            return []
        return [p.get('id', '') for p in self._banner_defs[bidx].get('pools', [])]

    def _refresh_lifecycle_table(self):
        self.lifecycle_table.blockSignals(True)
        self.lifecycle_table.setRowCount(0)
        bidx = self._current_banner_row
        if bidx < 0 or bidx >= len(self._banner_defs):
            self.lifecycle_table.blockSignals(False)
            return
        rules = self._banner_defs[bidx].get('lifecycle', [])
        pool_ids = self._current_banner_pool_ids()
        self.lifecycle_table.setRowCount(len(rules))
        for i, rule in enumerate(rules):
            self._set_lifecycle_row(i, rule, pool_ids)
        self.lifecycle_table.blockSignals(False)

    def _set_lifecycle_row(self, row, rule, pool_ids):
        cond = rule.get('condition', 'pool_draws')
        # 关联池列：card_obtained / time_window 时禁用（匹配目标/时间条件是 Banner 级）；
        # 空项「(未选择)」data='' 保持显示与数据一致（新规则 pool='' 不误显第一池）
        pool_combo = QComboBox()
        pool_combo.addItem("(未选择)", "")
        for pid in pool_ids:
            pool_combo.addItem(pid, pid)
        cur_pool = rule.get('pool', '') if cond in ('pool_draws', 'pool_exhausted') else ''
        pidx = pool_combo.findData(cur_pool)
        pool_combo.setCurrentIndex(pidx if pidx >= 0 else 0)
        pool_combo.setEnabled(cond in ('pool_draws', 'pool_exhausted'))
        pool_combo.currentTextChanged.connect(
            lambda text, rr=row: self._on_lifecycle_pool_changed(rr, text))
        self.lifecycle_table.setCellWidget(row, 0, pool_combo)

        cond_combo = QComboBox()
        cond_combo.addItems(['pool_draws', 'banner_draws', 'card_obtained',
                             'pool_exhausted', 'time_window'])
        cond_combo.setCurrentText(cond)
        cond_combo.currentTextChanged.connect(
            lambda text, rr=row: self._on_lifecycle_condition_changed(rr, text))
        self.lifecycle_table.setCellWidget(row, 1, cond_combo)

        at_widget = self._build_lifecycle_at_widget(row, rule, cond)
        self.lifecycle_table.setCellWidget(row, 2, at_widget)

        action_combo = QComboBox()
        action_combo.addItems(['switch_to', 'exhaust_banner'])
        action_combo.setCurrentText(rule.get('action', 'switch_to'))
        action_combo.currentTextChanged.connect(
            lambda text, rr=row: self._on_lifecycle_action_changed(rr, text))
        self.lifecycle_table.setCellWidget(row, 3, action_combo)

        target_combo = QComboBox()
        target_combo.addItem("(未选择)", "")
        for pid in pool_ids:
            target_combo.addItem(pid, pid)
        tidx = target_combo.findData(rule.get('target', ''))
        target_combo.setCurrentIndex(tidx if tidx >= 0 else 0)
        target_combo.currentTextChanged.connect(
            lambda text, rr=row: self._on_lifecycle_target_changed(rr, text))
        self.lifecycle_table.setCellWidget(row, 4, target_combo)
        target_combo.setEnabled(rule.get('action', 'switch_to') == 'switch_to')

    def _build_lifecycle_at_widget(self, row, rule, cond):
        """§3.10.5 阈值列控件。
        pool_draws/banner_draws → 整数抽数；time_window → QDoubleSpinBox（天，UI/存储层
        天数、保存 *DAY 转秒，ISSUE-001）；card_obtained → 二级匹配控件（match + 取值，
        取值写 rule['pool']——引擎字段：card_obtained 匹配目标存在 pool，见 banner.py:29）；
        pool_exhausted → 禁用。"""
        if cond in ('pool_draws', 'banner_draws'):
            spin = QSpinBox()
            spin.setRange(0, 1000000)
            spin.setValue(int(rule.get('at', 0)))
            spin.valueChanged.connect(
                lambda val, rr=row: self._on_lifecycle_at_changed(rr, val))
            return spin
        if cond == 'time_window':
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 99999.0)
            spin.setDecimals(2)
            spin.setValue(float(rule.get('at', 0.0)) / DAY)  # 秒 → 天（显示）
            spin.valueChanged.connect(
                lambda val, rr=row: self._on_lifecycle_at_changed(rr, val * DAY))
            return spin
        if cond == 'card_obtained':
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            match_combo = QComboBox()
            match_combo.addItems(['card_id', 'rarity'])
            match_combo.setCurrentText(rule.get('match', 'card_id'))
            lay.addWidget(match_combo)
            val_combo = QComboBox()
            val_combo.setEditable(True)
            match_mode = rule.get('match', 'card_id')
            if match_mode == 'card_id':
                val_combo.addItems(self._registered_card_labels())
                cur = rule.get('pool', '')
                val_combo.setCurrentText(
                    next((lab for lab in self._registered_card_labels()
                          if self._card_id_from_label(lab) == cur), cur))
            else:
                # P61（2026-08-04 用户决策）：rarity 从已注册稀有度动态填充（A4）
                val_combo.addItems(self._registered_rarities())
                val_combo.setCurrentText(rule.get('pool', '') or 'SSR')
            lay.addWidget(val_combo, 1)

            def _on_match(idx, mc=match_combo, vc=val_combo, rr=row):
                mode = mc.currentText()
                self._set_lifecycle_rule(rr, 'match', mode)
                vc.blockSignals(True)
                vc.clear()
                if mode == 'card_id':
                    vc.addItems(self._registered_card_labels())
                else:
                    vc.addItems(self._registered_rarities())
                    vc.setCurrentText('SSR')
                vc.blockSignals(False)

            def _on_val(text, rr=row):
                # card_obtained 匹配值存 rule['pool']（引擎字段语义，banner.py:29）
                cid = self._card_id_from_label(text)
                self._set_lifecycle_rule(rr, 'pool', cid)

            match_combo.currentIndexChanged.connect(_on_match)
            val_combo.currentTextChanged.connect(_on_val)
            return w
        # pool_exhausted：阈值禁用
        label = QLabel("—")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #aaa;")
        return label

    def _on_lifecycle_pool_changed(self, row, text):
        # 空项「(未选择)」data=''——取 currentData 而非显示文本
        bidx = self._current_banner_row
        if bidx < 0:
            return
        rules = self._banner_defs[bidx].get('lifecycle', [])
        if row < 0 or row >= len(rules):
            return
        combo = self.lifecycle_table.cellWidget(row, 0)
        data = combo.currentData() if combo is not None else ''
        rules[row]['pool'] = data

    def _on_lifecycle_condition_changed(self, row, text):
        bidx = self._current_banner_row
        if bidx < 0:
            return
        rules = self._banner_defs[bidx].get('lifecycle', [])
        if row < 0 or row >= len(rules):
            return
        rules[row]['condition'] = text
        pool_ids = self._current_banner_pool_ids()
        self.lifecycle_table.blockSignals(True)
        self._set_lifecycle_row(row, rules[row], pool_ids)
        self.lifecycle_table.blockSignals(False)

    def _on_lifecycle_at_changed(self, row, val):
        self._set_lifecycle_rule(row, 'at', float(val))

    def _on_lifecycle_action_changed(self, row, text):
        self._set_lifecycle_rule(row, 'action', text)
        tgt = self.lifecycle_table.cellWidget(row, 4)
        if tgt is not None:
            tgt.setEnabled(text == 'switch_to')

    def _on_lifecycle_target_changed(self, row, text):
        # 空项「(未选择)」data=''——取 currentData 而非显示文本
        bidx = self._current_banner_row
        if bidx < 0:
            return
        rules = self._banner_defs[bidx].get('lifecycle', [])
        if row < 0 or row >= len(rules):
            return
        combo = self.lifecycle_table.cellWidget(row, 4)
        data = combo.currentData() if combo is not None else ''
        rules[row]['target'] = data

    def _set_lifecycle_rule(self, row, key, value):
        bidx = self._current_banner_row
        if bidx < 0:
            return
        rules = self._banner_defs[bidx].get('lifecycle', [])
        if row < 0 or row >= len(rules):
            return
        rules[row][key] = value

    def _on_lifecycle_item_changed(self, item):
        # 生命周期表为 cellWidget 驱动，无文本 item——此回调保留占位
        pass

    def _add_lifecycle_row(self):
        bidx = self._current_banner_row
        if bidx < 0:
            QMessageBox.information(self, "提示", "请先选择一个 Banner")
            return
        self._banner_defs[bidx].setdefault('lifecycle', []).append({
            'condition': 'pool_draws',
            'pool': '',
            'at': 0.0,
            'match': 'card_id',
            'action': 'switch_to',
            'target': '',
        })
        self._refresh_lifecycle_table()
        self.lifecycle_table.selectRow(len(self._banner_defs[bidx]['lifecycle']) - 1)

    def _remove_lifecycle_rows(self):
        bidx = self._current_banner_row
        if bidx < 0:
            return
        rules = self._banner_defs[bidx].get('lifecycle', [])
        rows = sorted([r.row() for r in self.lifecycle_table.selectionModel().selectedRows()],
                      reverse=True)
        if not rows:
            QMessageBox.information(self, "提示", "请先选择要移除的规则")
            return
        for row in rows:
            if 0 <= row < len(rules):
                del rules[row]
        self._refresh_lifecycle_table()

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

        # ── 绑定池（P61 Ph8b，§3.11.2）：替代手写 fnmatch 文本框 ──
        bind_group = QGroupBox("绑定池")
        bind_layout = QVBoxLayout(bind_group)
        bind_filter_row = QHBoxLayout()
        self.pity_bind_filter = QLineEdit()
        self.pity_bind_filter.setPlaceholderText("筛选 Banner 名或 Pool ID...")
        self.pity_bind_filter.textChanged.connect(self._filter_pity_bind_rows)
        bind_filter_row.addWidget(self.pity_bind_filter, 1)
        sel_all_btn = QPushButton("全选")
        sel_all_btn.clicked.connect(lambda: self._set_pity_bind_all(True))
        sel_none_btn = QPushButton("全不选")
        sel_none_btn.clicked.connect(lambda: self._set_pity_bind_all(False))
        bind_filter_row.addWidget(sel_all_btn)
        bind_filter_row.addWidget(sel_none_btn)
        bind_layout.addLayout(bind_filter_row)

        self.pity_bind_table = QTableWidget()
        self.pity_bind_table.setColumnCount(4)
        # P61（2026-08-04 用户决策）：第一列头 ☑ 删除（勾选列保留空列头）
        self.pity_bind_table.setHorizontalHeaderLabels(["", "Banner", "Pool", "说明"])
        bind_header = self.pity_bind_table.horizontalHeader()
        bind_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        bind_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        bind_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        bind_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.pity_bind_table.setColumnWidth(0, 30)
        self.pity_bind_table.setColumnWidth(2, 90)
        self.pity_bind_table.verticalHeader().setVisible(False)
        self.pity_bind_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.pity_bind_table.setMinimumHeight(120)
        bind_layout.addWidget(self.pity_bind_table)
        # P61（2026-08-04 用户决策）：绑定池移至表单最底部（依赖之后）——
        # 保持「定义规则 → 配置参数 → 指定作用范围」逻辑流，绑定池为最后一段。
        self._pity_bind_group = bind_group

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

        # P61（2026-08-04 用户决策）：绑定池在表单最底部（初始水位/依赖之后）
        detail_form.addRow(self._pity_bind_group)

        main_layout.addWidget(detail_group, 2)
        parent.addLayout(main_layout)

        # 信号连接——控件变更 → 实时写回数据 → 触发预览
        self.pity_enabled.stateChanged.connect(self._flush_pity_current_detail)
        self.pity_name_edit.textChanged.connect(self._flush_pity_current_detail)
        self.pity_type_combo.currentIndexChanged.connect(self._flush_pity_current_detail)
        self.pity_scope_combo.currentIndexChanged.connect(self._flush_pity_current_detail)
        self.pity_target_featured_cb.stateChanged.connect(self._flush_pity_current_detail)
        self.pity_init_spin.valueChanged.connect(self._flush_pity_current_detail)
        self.pity_deactivate_cb.stateChanged.connect(self._flush_pity_current_detail)
        self.pity_guaranteed_init_cb.stateChanged.connect(self._flush_pity_current_detail)
        self.pity_fate_points_spin.valueChanged.connect(self._flush_pity_current_detail)
        self.pity_selected_card_combo.currentIndexChanged.connect(self._flush_pity_current_detail)
        self.pity_depends_combo.currentIndexChanged.connect(self._flush_pity_current_detail)

    # ── P58：累抽奖励配置 ──

    def _setup_milestone_config(self, parent):
        """[[milestone]] 配置 UI——与 _setup_pity_config() 统一模式（§3.8.5）"""
        self._milestone_defs = []
        self._select_vouchers: list = []     # P78：自选券候选集（List[SelectVoucherDef] 同构 dict）
        self._selected_alternate_idx = 0     # P78：当前选中编辑的交替项索引
        self._milestone_random_pools = {}   # milestone_name → [{candidates, weights, count}]
        self._selected_random_pool_idx = 0  # 当前选中编辑的候选池索引（由池列表行选中维护，REVIEW-R1-FIX: ISSUE-003）
        self._current_milestone_row = -1    # REVIEW-R1-FIX: ISSUE-001 —— 追踪当前编辑行（仿 _current_pity_row 模式）
        self._warned_milestone_resource_ids = set()  # REVIEW-R1-FIX: ISSUE-311 —— 未定义资源 ID 一次性警告去重集合

        # ── 全局总闸 ──
        self.milestone_enabled = QCheckBox("启用累抽奖励")
        self.milestone_enabled.setChecked(True)
        parent.addWidget(self.milestone_enabled)

        # ── 主布局：左列表 + 右详情 ──
        main_layout = QHBoxLayout()

        # 左侧——累抽列表 + 按钮
        left_layout = QVBoxLayout()
        self.milestone_list = QListWidget()
        self.milestone_list.currentRowChanged.connect(self._on_milestone_selected)
        left_layout.addWidget(self.milestone_list)

        btn_layout = QHBoxLayout()
        for text, slot in [("添加", self._add_milestone),
                           ("移除选中", self._remove_milestone)]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn_layout.addWidget(btn)
        left_layout.addLayout(btn_layout)
        main_layout.addLayout(left_layout, 1)

        # 右侧——详情面板
        detail_group = QGroupBox("累抽详情")
        detail_group.setEnabled(False)
        self._milestone_detail_group = detail_group
        detail_form = QFormLayout(detail_group)

        # 基础字段——所有信号实时写回数据（_flush_milestone_current_detail），无需"应用修改"按钮
        self.ml_name_edit = QLineEdit()
        detail_form.addRow("名称:", self.ml_name_edit)

        # P78（ISSUE-110/128）：threshold/offset 编辑入口改为用户心智模型的「首次触发 / 循环周期」
        # 双输入框。ml_threshold_spin 改名为「循环周期」spin（语义 = threshold，既有 L2149 回填/
        # L2203 写回/信号连接天然成立）；新增「首次触发」spin 承载 offset 分支。
        # 换算：写回 threshold=循环周期、offset=首次触发-循环周期；回填 首次触发=threshold+offset。
        # at=N（repeat 未勾选）：循环周期禁用不参与写回，写回 threshold=首次触发、offset 省略（ISSUE-502）。
        self.ml_first_trigger_spin = QSpinBox()
        self.ml_first_trigger_spin.setRange(1, 9999)
        self.ml_first_trigger_spin.setValue(40)
        detail_form.addRow("首次触发(抽):", self.ml_first_trigger_spin)

        self.ml_threshold_spin = QSpinBox()   # 现代表「循环周期」
        self.ml_threshold_spin.setRange(1, 9999)
        self.ml_threshold_spin.setValue(40)
        detail_form.addRow("循环周期(抽):", self.ml_threshold_spin)
        self.ml_threshold_spin.setToolTip("可重复触发时生效——每 N 抽循环一次；单次触发(at=N)时禁用，只填首次触发。")

        self.ml_repeat_check = QCheckBox("可重复触发")
        detail_form.addRow("触发模式:", self.ml_repeat_check)

        self.ml_max_triggers_spin = QSpinBox()
        self.ml_max_triggers_spin.setRange(0, 999)
        self.ml_max_triggers_spin.setValue(0)
        self.ml_max_triggers_spin.setToolTip("0 = 无限触发")
        detail_form.addRow("最大触发次数:", self.ml_max_triggers_spin)

        self.ml_banner_edit = QLineEdit()
        self.ml_banner_edit.setPlaceholderText("留空 = 全部 Banner")
        detail_form.addRow("适用 Banner:", self.ml_banner_edit)

        # ── 奖励配置（三区域并行） ──
        detail_form.addRow(QLabel(""))  # 分隔
        detail_form.addRow("── 奖励配置（可同时填写多区域） ──", QLabel(""))

        # 固定卡牌
        self.ml_cards_list = QListWidget()
        self.ml_cards_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.ml_cards_list.setMaximumHeight(100)
        detail_form.addRow("固定赠送卡牌:", self.ml_cards_list)

        # 资源
        self.ml_resources_table = QTableWidget()
        self.ml_resources_table.setColumnCount(2)
        self.ml_resources_table.setHorizontalHeaderLabels(["资源", "数量"])
        self.ml_resources_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.ml_resources_table.setMaximumHeight(120)
        detail_form.addRow("赠送资源:", self.ml_resources_table)

        res_btn_layout = QHBoxLayout()
        add_res_btn = QPushButton("添加")
        add_res_btn.clicked.connect(self._add_milestone_resource)
        remove_res_btn = QPushButton("移除选中")
        remove_res_btn.clicked.connect(self._remove_milestone_resource)
        res_btn_layout.addWidget(add_res_btn)
        res_btn_layout.addWidget(remove_res_btn)
        res_btn_layout.addStretch()
        detail_form.addRow(res_btn_layout)

        # 随机卡——池列表（可点击选中）+ 弹窗编辑
        # REVIEW-R1-FIX: ISSUE-003 —— 随机池摘要从纯文本 QLabel 换为可点击 QListWidget：
        #   currentRowChanged 实时维护 _selected_random_pool_idx，否则多池时「编辑」恒作用于池 0。
        self.ml_random_pool_list = QListWidget()
        self.ml_random_pool_list.setMaximumHeight(100)
        self.ml_random_pool_list.currentRowChanged.connect(self._on_random_pool_selected)
        detail_form.addRow("随机卡:", self.ml_random_pool_list)

        rand_btn_layout = QHBoxLayout()
        edit_rand_btn = QPushButton("编辑")
        edit_rand_btn.clicked.connect(self._edit_milestone_random_pool)
        add_rand_btn = QPushButton("添加")
        add_rand_btn.clicked.connect(self._add_milestone_random_pool)
        remove_rand_btn = QPushButton("移除选中")
        remove_rand_btn.clicked.connect(self._remove_milestone_random_pool)
        rand_btn_layout.addWidget(edit_rand_btn)
        rand_btn_layout.addWidget(add_rand_btn)
        rand_btn_layout.addWidget(remove_rand_btn)
        rand_btn_layout.addStretch()
        detail_form.addRow(rand_btn_layout)

        # ── P78（ISSUE-110 对话框部分）：交替奖励分组 ──
        # 交替序列——每次触发取下一项、索引模长度循环。摘要 QListWidget + 添加/编辑/移除。
        detail_form.addRow("── 交替奖励（可选，周期触发时按序循环） ──", QLabel(""))
        self.ml_alternate_list = QListWidget()
        self.ml_alternate_list.setMaximumHeight(100)
        self.ml_alternate_list.currentRowChanged.connect(self._on_alternate_selected)
        detail_form.addRow("交替项:", self.ml_alternate_list)

        alt_btn_layout = QHBoxLayout()
        add_alt_btn = QPushButton("添加")
        add_alt_btn.clicked.connect(self._add_milestone_alternate)
        edit_alt_btn = QPushButton("编辑")
        edit_alt_btn.clicked.connect(self._edit_milestone_alternate)
        remove_alt_btn = QPushButton("移除选中")
        remove_alt_btn.clicked.connect(self._remove_milestone_alternate)
        alt_btn_layout.addWidget(add_alt_btn)
        alt_btn_layout.addWidget(edit_alt_btn)
        alt_btn_layout.addWidget(remove_alt_btn)
        alt_btn_layout.addStretch()
        detail_form.addRow(alt_btn_layout)

        main_layout.addWidget(detail_group, 2)
        parent.addLayout(main_layout)

        # ── 自动写入 + 预览信号（仿 _flush_pity_current_detail 模式） ──
        # REVIEW-R1-FIX: ISSUE-001 —— 行追踪机制：_on_milestone_selected 先 flush 到旧行再切换；
        #   _flush_milestone_current_detail 读 _current_milestone_row 而非 currentRow()。
        for w in [self.ml_name_edit, self.ml_banner_edit]:
            w.textChanged.connect(self._flush_milestone_current_detail)
        for w in [self.ml_first_trigger_spin, self.ml_threshold_spin, self.ml_max_triggers_spin]:
            w.valueChanged.connect(self._flush_milestone_current_detail)
        self.ml_repeat_check.stateChanged.connect(self._on_milestone_repeat_changed)
        self.milestone_enabled.stateChanged.connect(self._update_preview)

    def _on_milestone_repeat_changed(self):
        """repeat 勾选状态变化——at=N（未勾选）时循环周期 spin 禁用（ISSUE-502）。"""
        repeat = self.ml_repeat_check.isChecked()
        self.ml_threshold_spin.setEnabled(repeat)
        self._flush_milestone_current_detail()
        self._update_preview()

    # REVIEW-R1-FIX: ISSUE-010 —— 调用点见 §3.8.5a 回填段（_refresh_from_store_impl 内 store 就绪后）
    def _populate_milestone_cards_list(self):
        """从 store.card_defs 填充固定卡牌 QListWidget——每行 [稀有度] 名称 (card_id)。"""
        self.ml_cards_list.clear()
        if not self._store:
            return
        # REVIEW-R1-FIX: ISSUE-301 —— store.card_defs 是 List[CardDefEntry]，无 .items()，
        #   原 `.items()` 迭代会抛 AttributeError。改为列表迭代 + entry.card_id。
        for entry in self._store.card_defs:
            cid = entry.card_id
            rarity = (entry.rarity or '?').upper()
            display = f"[{rarity}] {entry.name} ({cid})"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, cid)
            self.ml_cards_list.addItem(item)

    def _on_milestone_selected(self, row):
        """选中左侧累抽条目 → 刷新右侧详情面板。"""
        # REVIEW-R1-FIX: ISSUE-001 —— 先 flush 到【上一行】（_current_milestone_row 追踪）
        self._flush_milestone_current_detail()
        # 再切换到新行
        self._current_milestone_row = row
        if row < 0 or row >= len(self._milestone_defs):
            self._milestone_detail_group.setEnabled(False)
            return
        md = self._milestone_defs[row]
        self._milestone_detail_group.setEnabled(True)

        # REVIEW-R1-FIX: ISSUE-310 —— 回填段 blockSignals：阻断级联 flush
        #   （否则未更新的控件残留上一行值被写入新行 bonus_reward）
        # P78（ISSUE-127）：_bs_widgets 扩展——纳入首次触发 spin（循环周期=ml_threshold_spin 保留）
        _bs_widgets = [self.ml_name_edit, self.ml_first_trigger_spin, self.ml_threshold_spin,
                       self.ml_repeat_check, self.ml_max_triggers_spin, self.ml_banner_edit]
        for w in _bs_widgets:
            w.blockSignals(True)
        try:
            # 基础字段
            self.ml_name_edit.setText(md.get('name', ''))
            # P78（ISSUE-110/502）回填换算：首次触发 = threshold + offset；
            # 循环周期 = threshold（at=N 时禁用、回填 threshold 值展示「单次触发」）
            _threshold = md.get('threshold', 40)
            _offset = md.get('offset', 0)
            self.ml_first_trigger_spin.setValue(_threshold + _offset)
            self.ml_threshold_spin.setValue(_threshold)
            self.ml_repeat_check.setChecked(md.get('repeat', False))
            self.ml_threshold_spin.setEnabled(md.get('repeat', False))   # ISSUE-502：at=N 循环周期禁用
            self.ml_max_triggers_spin.setValue(md.get('max_triggers', 0))
            self.ml_banner_edit.setText(md.get('banner', ''))

            # 奖励：固定卡牌
            card_ids = set(md.get('bonus_reward', {}).get('cards', []))
            for i in range(self.ml_cards_list.count()):
                item = self.ml_cards_list.item(i)
                cid = item.data(Qt.ItemDataRole.UserRole)
                item.setSelected(cid in card_ids)

            # 奖励：资源
            resources = md.get('bonus_reward', {}).get('resources', {})
            self.ml_resources_table.setRowCount(len(resources))
            for i, (res_id, amount) in enumerate(resources.items()):
                self.ml_resources_table.setItem(i, 0, QTableWidgetItem(res_id))
                amt_item = QTableWidgetItem()
                amt_item.setData(Qt.ItemDataRole.EditRole, amount)
                self.ml_resources_table.setItem(i, 1, amt_item)

            # 奖励：随机卡摘要
            self._milestone_random_pools[md['name']] = md.get('bonus_reward', {}).get('random_cards', [])
            self._selected_random_pool_idx = 0   # REVIEW-R1-FIX: ISSUE-003 —— 切换里程碑时重置池选中
            self._update_milestone_random_summary()
            # P78（ISSUE-115）：交替项摘要刷新——回填后立即刷新（防行切换残留旧行数据）
            self._selected_alternate_idx = 0
            self._refresh_milestone_alternate_summary(row)
        finally:
            for w in _bs_widgets:
                w.blockSignals(False)
        # 回填完成后主动 flush 一次（REVIEW-R2-FIX: ISSUE-310）
        self._flush_milestone_current_detail()

    def _flush_milestone_current_detail(self):
        """从右侧控件读取当前值 → 实时写回 self._milestone_defs[row]。"""
        # REVIEW-R1-FIX: ISSUE-001 —— 读 _current_milestone_row（追踪的旧行）而非 currentRow()
        row = self._current_milestone_row
        if row < 0 or row >= len(self._milestone_defs):
            return
        md = self._milestone_defs[row]

        # REVIEW-R1-FIX: ISSUE-314 —— 空名回退复用 _add_milestone 查重循环（排除当前行）
        _raw_name = self.ml_name_edit.text().strip()
        if _raw_name:
            new_name = _raw_name
        else:
            _existing = {d['name'] for i, d in enumerate(self._milestone_defs) if i != row}
            _n = 1
            while f'milestone_{_n}' in _existing:
                _n += 1
            new_name = f'milestone_{_n}'
        md['name'] = new_name
        # 更名时迁移 _milestone_random_pools 键——防止随机卡池静默丢失
        old_name = self.milestone_list.item(row).text()
        if old_name != new_name and old_name in self._milestone_random_pools:
            self._milestone_random_pools[new_name] = self._milestone_random_pools.pop(old_name)
        # P78（ISSUE-110/502）写回换算：
        #   every：threshold = 循环周期、offset = 首次触发 - 循环周期
        #   at=N（repeat 未勾选）：threshold = 首次触发、offset 省略（0）——循环周期 spin 禁用残留值不得参与换算
        _repeat = self.ml_repeat_check.isChecked()
        _first = self.ml_first_trigger_spin.value()
        if _repeat:
            _cycle = self.ml_threshold_spin.value()
            md['threshold'] = _cycle
            md['offset'] = _first - _cycle
            # P78（ISSUE-501）：首次触发 ≥ 循环周期（换算后 offset ≥ 0）——仅 every 场景；
            # 负 offset 由解析期 ISSUE-007 显式拒绝（offset ≥ 0），GUI 侧一次性警告（ISSUE-104 通道）
            if _first < _cycle:
                QMessageBox.warning(self, "偏移冲突",
                                    f"首次触发({_first}) 不得小于循环周期({_cycle})——"
                                    f"否则换算后 offset 为负（首节点早于周期），请调整数值。")
                # 不写回非法换算——恢复控件为合法组合（首次触发 = 循环周期）
                self.ml_first_trigger_spin.blockSignals(True)
                self.ml_first_trigger_spin.setValue(_cycle)
                self.ml_first_trigger_spin.blockSignals(False)
                md['offset'] = 0
        else:
            md['threshold'] = _first
            md['offset'] = 0
        md['repeat'] = _repeat
        md['max_triggers'] = self.ml_max_triggers_spin.value()
        md['banner'] = self.ml_banner_edit.text().strip()

        # 固定卡牌
        cards = []
        for i in range(self.ml_cards_list.count()):
            item = self.ml_cards_list.item(i)
            if item.isSelected():
                cards.append(item.data(Qt.ItemDataRole.UserRole))
        md.setdefault('bonus_reward', {})['cards'] = cards

        # 资源
        resources = {}
        for i in range(self.ml_resources_table.rowCount()):
            # REVIEW-R1-FIX: ISSUE-104 —— 兼容两种行形态：新增行（列0 = QComboBox）取 currentText；
            #   回填的既有行（列0 = QTableWidgetItem 直填）取 item 文本
            res_widget = self.ml_resources_table.cellWidget(i, 0)
            res_item = self.ml_resources_table.item(i, 0)
            amt_item = self.ml_resources_table.item(i, 1)
            rid = ''
            if res_widget is not None and hasattr(res_widget, 'currentText'):
                rid = res_widget.currentText().strip()
            elif res_item:
                rid = res_item.text().strip()
            if rid and amt_item:
                # REVIEW-R1-FIX: ISSUE-004 —— 金额读取防异常 + 过滤 0 值行
                try:
                    amount = float(amt_item.data(Qt.ItemDataRole.EditRole) or 0)
                except (TypeError, ValueError):
                    amount = 0.0
                if amount != 0:
                    resources[rid] = amount
        md.setdefault('bonus_reward', {})['resources'] = resources

        # 随机卡——从 _milestone_random_pools 回写
        pools = self._milestone_random_pools.get(md['name'], [])
        md.setdefault('bonus_reward', {})['random_cards'] = list(pools)

        # P78（ISSUE-115）：编辑实时刷新交替摘要（行切换后由 _on_milestone_selected 刷新）
        self._refresh_milestone_alternate_summary(row)

        self.milestone_list.item(row).setText(md['name'])
        self._update_preview()

    def _add_milestone(self):
        """添加新累抽条目——默认占位，选中后编辑。"""
        existing = {d['name'] for d in self._milestone_defs}
        n = 1
        while f'milestone_{n}' in existing:
            n += 1
        md = {'name': f'milestone_{n}', 'threshold': 40,
              'repeat': False, 'max_triggers': 0, 'banner': '',
              'bonus_reward': {'cards': [], 'resources': {}, 'random_cards': []},
              # P78（ISSUE-110）：默认 offset 0 / 交替空列表
              'offset': 0, 'alternate_rewards': []}
        self._milestone_defs.append(md)
        self.milestone_list.addItem(md['name'])
        self.milestone_list.setCurrentRow(len(self._milestone_defs) - 1)

    def _remove_milestone(self):
        """移除选中的累抽条目。"""
        row = self.milestone_list.currentRow()
        if row < 0:
            return
        name = self._milestone_defs[row]['name']
        del self._milestone_defs[row]
        self._milestone_random_pools.pop(name, None)
        self.milestone_list.takeItem(row)
        if row < len(self._milestone_defs):
            self.milestone_list.setCurrentRow(row)
        self._update_preview()

    # ── 资源子表操作 ──

    def _add_milestone_resource(self):
        row = self.ml_resources_table.rowCount()
        self.ml_resources_table.insertRow(row)
        # REVIEW-R1-FIX: ISSUE-104 —— 资源列改为可编辑 QComboBox（从 store.resource_defs 填充）
        combo = QComboBox()
        known = list(self._store.resource_defs.keys()) if self._store else []
        combo.addItems(known)
        combo.setEditable(True)
        self.ml_resources_table.setCellWidget(row, 0, combo)
        amt_item = QTableWidgetItem()
        amt_item.setData(Qt.ItemDataRole.EditRole, 0)   # REVIEW-R1-FIX: ISSUE-004 —— 0 金额行被 flush 过滤
        self.ml_resources_table.setItem(row, 1, amt_item)
        self._flush_milestone_current_detail()

    def _remove_milestone_resource(self):
        row = self.ml_resources_table.currentRow()
        if row >= 0:
            self.ml_resources_table.removeRow(row)
            self._flush_milestone_current_detail()

    # ── 随机卡池操作 ──

    def _add_milestone_random_pool(self):
        """追加一个空候选池。"""
        row = self._current_milestone_row   # REVIEW-R1-FIX: ISSUE-001 —— 作用于当前编辑行
        if row < 0:
            return
        md = self._milestone_defs[row]
        pools = self._milestone_random_pools.setdefault(md['name'], [])
        # REVIEW-R1-FIX: ISSUE-305 —— 空候选池是合法编辑中间态，保存时由 apply_to_store 过滤
        pools.append({'candidates': [], 'weights': [], 'count': 1})
        self._update_milestone_random_summary()
        self._flush_milestone_current_detail()

    def _remove_milestone_random_pool(self):
        """移除当前选中的候选池（基于 _selected_random_pool_idx，由池列表行选中维护）。"""
        row = self._current_milestone_row   # REVIEW-R1-FIX: ISSUE-001
        if row < 0:
            return
        md = self._milestone_defs[row]
        pools = self._milestone_random_pools.get(md['name'], [])
        idx = getattr(self, '_selected_random_pool_idx', -1)
        if 0 <= idx < len(pools):
            pools.pop(idx)
            self._selected_random_pool_idx = max(0, idx - 1)
            self._update_milestone_random_summary()
            self._flush_milestone_current_detail()

    def _edit_milestone_random_pool(self):
        """打开 RandomCardPoolDialog 编辑当前候选池。"""
        row = self._current_milestone_row   # REVIEW-R1-FIX: ISSUE-001
        if row < 0:
            return
        md = self._milestone_defs[row]
        pools = self._milestone_random_pools.setdefault(md['name'], [])
        # REVIEW-R1-FIX: ISSUE-308 —— 空池守卫：pools 为空时先追加一个空池再进入弹窗
        if not pools:
            self._add_milestone_random_pool()
            pools = self._milestone_random_pools[md['name']]
        idx = getattr(self, '_selected_random_pool_idx', 0)
        if idx >= len(pools):
            idx = 0
        dialog = RandomCardPoolDialog(self._store, pools[idx], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            pools[idx] = dialog.result()
            self._update_milestone_random_summary()
            self._flush_milestone_current_detail()

    def _on_random_pool_selected(self, row):
        """随机池列表行选中 → 记录当前编辑目标池索引（供 编辑/移除 使用）。"""
        # REVIEW-R1-FIX: ISSUE-003 —— 用户点击池行即更新 _selected_random_pool_idx
        self._selected_random_pool_idx = row if row >= 0 else 0

    def _update_milestone_random_summary(self):
        """刷新随机卡池列表——每个候选池一行摘要（可点击选中）。"""
        row = self._current_milestone_row   # REVIEW-R1-FIX: ISSUE-001
        self.ml_random_pool_list.clear()
        if row < 0:
            return
        md = self._milestone_defs[row]
        pools = self._milestone_random_pools.get(md['name'], [])
        if not pools:
            return
        lines = []
        for i, pool in enumerate(pools):
            names = [c[:6] for c in pool.get('candidates', [])]
            w_hint = ''
            weights = pool.get('weights', [])
            if weights and not all(w == 1.0 for w in weights):
                varied = [f"{c[:6]}={w}" for c, w in zip(names, weights) if w != 1.0]
                w_hint = f" ({', '.join(varied)})" if varied else ''
            lines.append(f"池{i+1}: {', '.join(names[:3])}{'...' if len(names)>3 else ''}, 抽{pool.get('count',1)}张{w_hint}")
        self.ml_random_pool_list.addItems(lines)
        # REVIEW-R1-FIX: ISSUE-003 —— 恢复选中到当前池（clamp 到有效范围）
        idx = min(self._selected_random_pool_idx, len(pools) - 1)
        self.ml_random_pool_list.setCurrentRow(idx)

    # ── P78（ISSUE-110 交替奖励操作）──

    def _add_milestone_alternate(self):
        """追加一个空交替项（默认空奖励，弹窗编辑）。"""
        row = self._current_milestone_row
        if row < 0:
            return
        md = self._milestone_defs[row]
        md.setdefault('alternate_rewards', []).append({'cards': [], 'resources': {}, 'random_cards': []})
        # 编辑新项
        self._selected_alternate_idx = len(md['alternate_rewards']) - 1
        self._edit_milestone_alternate()

    def _edit_milestone_alternate(self):
        """打开 MilestoneAlternateDialog 编辑当前选中的交替项（ISSUE-706 对话框自持状态）。"""
        row = self._current_milestone_row
        if row < 0:
            return
        md = self._milestone_defs[row]
        alt = md.setdefault('alternate_rewards', [])
        if not alt:
            return
        idx = getattr(self, '_selected_alternate_idx', 0)
        if idx >= len(alt):
            idx = 0
        dialog = MilestoneAlternateDialog(self._store, alt[idx], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            alt[idx] = dialog.result()      # ISSUE-706：Accept 整体写回第 idx 项
            self._refresh_milestone_alternate_summary(row)
            self._flush_milestone_current_detail()

    def _remove_milestone_alternate(self):
        """移除当前选中的交替项。"""
        row = self._current_milestone_row
        if row < 0:
            return
        md = self._milestone_defs[row]
        alt = md.get('alternate_rewards', [])
        idx = getattr(self, '_selected_alternate_idx', -1)
        if 0 <= idx < len(alt):
            alt.pop(idx)
            self._selected_alternate_idx = max(0, idx - 1)
            self._refresh_milestone_alternate_summary(row)
            self._flush_milestone_current_detail()

    def _refresh_milestone_alternate_summary(self, row: int = None):
        """刷新交替奖励列表摘要（ISSUE-115——行切换后也调用，防显示旧行数据）。"""
        if row is None:
            row = self._current_milestone_row
        self.ml_alternate_list.clear()
        if row < 0 or row >= len(self._milestone_defs):
            return
        md = self._milestone_defs[row]
        alt = md.get('alternate_rewards', [])
        for i, item in enumerate(alt):
            cards = len(item.get('cards', []))
            res = len(item.get('resources', {}))
            rnd = len(item.get('random_cards', []))
            self.ml_alternate_list.addItem(f"项{i+1}: {cards}卡 + {res}资源 + {rnd}随机池")
        # 恢复选中（若仍在范围内）
        idx = getattr(self, '_selected_alternate_idx', 0)
        if 0 <= idx < len(alt):
            self.ml_alternate_list.setCurrentRow(idx)

    def _on_alternate_selected(self, row):
        """交替项列表行选中 → 记录当前编辑目标索引。"""
        self._selected_alternate_idx = row if row >= 0 else 0

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

        # P61 Ph8b：先填充绑定池勾选表格——后续 detail 控件 setText/setChecked 触发
        # flush 时 _read_pity_bind_patterns 读到的是本规则的新勾选状态，而非旧/空表格
        pools = pd.get('pools', ('*',))
        if isinstance(pools, str):
            pools = (pools,) if pools else ()
        self._refresh_pity_bind_table(pools)

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

    # ── P61 Ph8b：绑定池勾选表格（§3.11.2，替代手写 fnmatch 文本框） ──

    def _refresh_pity_bind_table(self, patterns=None):
        """填充绑定池勾选表格。数据源 = _banner_defs（兜底 store.banner.banners）。

        patterns 语义（ISSUE-328）：('*',) → 全选；空/[] → 全不选（不绑定任何池）；
        其余 → 对每个全限定键 fnmatch 命中即勾选（D4 一次性迁移后 PityDef.pools
        均为全限定键，无三路兼容）。
        """
        import fnmatch as _fn
        if patterns is None:
            row = self._current_pity_row
            patterns = self._pity_defs[row].get('pools', ('*',)) \
                if 0 <= row < len(self._pity_defs) else ('*',)
        banners = getattr(self, '_banner_defs', None) or []
        if not banners and self._store is not None:
            # 兜底：store.banner.banners → _banner_defs 等价 dict
            banners = [{
                'id': b.id, 'name': b.name,
                'pools': [{'id': p.id, 'excludes_all_pity': p.excludes_all_pity,
                           'max_draws': p.max_draws, 'batch_size': p.batch_size}
                          for p in b.pools],
            } for b in self._store.banner.banners]
        if isinstance(patterns, str):
            patterns = (patterns,) if patterns else ()

        self.pity_bind_table.blockSignals(True)
        self.pity_bind_table.setRowCount(0)
        rows_data = []
        for b in banners:
            for p in b.get('pools', []):
                full_key = f"{b.get('id', '')}.{p.get('id', '')}"
                note = []
                if p.get('excludes_all_pity'):
                    note.append('不计保底')
                md = p.get('max_draws')
                if md is not None and md == p.get('batch_size', 1):
                    note.append('一次性')
                rows_data.append((full_key, b.get('name', ''), p.get('id', ''), '、'.join(note)))
        self._pity_bind_keys = [r[0] for r in rows_data]
        self.pity_bind_table.setRowCount(len(rows_data))
        is_all = patterns == ('*',)
        for i, (full_key, bname, pid, note) in enumerate(rows_data):
            cb = QCheckBox()
            checked = is_all or any(_fn.fnmatch(full_key, ptn) for ptn in patterns)
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
            cb.stateChanged.connect(lambda ch, rr=i: self._on_pity_bind_toggled(rr, ch))
            self.pity_bind_table.setCellWidget(i, 0, cb)
            self.pity_bind_table.setItem(i, 1, QTableWidgetItem(bname))
            self.pity_bind_table.setItem(i, 2, QTableWidgetItem(pid))
            self.pity_bind_table.setItem(i, 3, QTableWidgetItem(note))
        self.pity_bind_table.blockSignals(False)
        self._update_preview()

    def _read_pity_bind_patterns(self):
        """从勾选表格生成 pools pattern（§3.11.2 / ISSUE-328）。

        全选 → ('*',)；全不选 → ()（不绑定任何池，区别于旧空文本 → ('*',)）；
        部分勾选 → 紧凑 fnmatch pattern（B3）：同一 Banner 的勾选池缩写为
        {banner}.*（引擎对全限定键 fnmatch 命中）；跨 Banner 保留精确键。
        """
        checked = []
        for i in range(self.pity_bind_table.rowCount()):
            cb = self.pity_bind_table.cellWidget(i, 0)
            if cb is not None and cb.isChecked():
                keys = getattr(self, '_pity_bind_keys', [])
                if i < len(keys):
                    checked.append(keys[i])
        total = self.pity_bind_table.rowCount()
        if total > 0 and len(checked) == total:
            return ('*',)
        if not checked:
            return ()
        # B3：仅当某 banner 的【全部】池都被勾选时才缩写为 {banner}.*——
        # 部分勾选缩写会让引擎 fnmatch 误绑该 banner 未勾选的池（复审查发现）
        banners = {k.split('.', 1)[0] for k in checked}
        if len(banners) == 1:
            banner_id = next(iter(banners))
            all_keys = getattr(self, '_pity_bind_keys', [])
            banner_pool_total = sum(1 for k in all_keys
                                    if k.split('.', 1)[0] == banner_id)
            if banner_pool_total == len(checked):
                return (f"{banner_id}.*",)
        return tuple(checked)

    def _on_pity_bind_toggled(self, row, checked):
        """勾选变化 → 实时写回 _pity_defs[current]['pools']。"""
        self._flush_pity_current_detail()

    def _filter_pity_bind_rows(self, text):
        text = text.lower()
        for i in range(self.pity_bind_table.rowCount()):
            bname = self.pity_bind_table.item(i, 1)
            pid = self.pity_bind_table.item(i, 2)
            bname_text = bname.text() if bname else ''
            pid_text = pid.text() if pid else ''
            match = (text in bname_text.lower()) or (text in pid_text.lower()) if text else True
            self.pity_bind_table.setRowHidden(i, not match)

    def _set_pity_bind_all(self, checked):
        for i in range(self.pity_bind_table.rowCount()):
            cb = self.pity_bind_table.cellWidget(i, 0)
            if cb is not None:
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)
        self._flush_pity_current_detail()

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

        # 绑定池（P61 Ph8b：勾选表格 → patterns）
        pd['pools'] = self._read_pity_bind_patterns()
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

        # 绑定池（P61 Ph8b：勾选表格 → patterns）
        pd['pools'] = self._read_pity_bind_patterns()
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

    def _setup_stop_condition_tab(self, parent):
        """「停止条件」子标签页外壳（P79 5.7）。

        竖直三块 + 顶部只读提示。三个 GroupBox 的**内容**由后续子任务填充：
        组合方式与条件列表（4c1b / 4d2b*）、条件参数（4c2a / 4c2b）；本项只落外壳
        与顶部提示。

        条件树走「面板内存态 + apply_to_store 全量重建」的既有模式——面板持
        ``self._stop_condition_tree`` 作为编辑期真相源。
        """
        # 编辑期真相源。5.7 定死：**表达式是组合的唯一真相源**，
        # 条件列表持各条件的 id 与叶子节点；树是由二者派生的落盘形态。
        self._stop_condition_conditions: List[dict] = []   # [{'id': 'a', 'type': ..., ...参数}]
        self._stop_condition_expr: str = ''
        self._stop_condition_tree = None                   # 派生结果（apply 时重建）
        self._stop_condition_selected_id = None

        # ── 顶部只读提示（5.5 校验项 1：显式化「模拟将在 X 天后强制结束」）──
        self.stop_condition_hint = QLabel()
        self.stop_condition_hint.setWordWrap(True)
        parent.addWidget(self.stop_condition_hint)
        self._refresh_stop_condition_hint()

        # ── 组合方式（4d2b2）──
        self._stop_condition_compose_group = QGroupBox("组合方式")
        self._stop_condition_compose_layout = QVBoxLayout(self._stop_condition_compose_group)
        self._setup_stop_condition_compose()
        parent.addWidget(self._stop_condition_compose_group)

        # ── 条件列表（4c1b）──
        self._stop_condition_list_group = QGroupBox("条件列表")
        self._stop_condition_list_layout = QVBoxLayout(self._stop_condition_list_group)
        self._setup_stop_condition_list()
        parent.addWidget(self._stop_condition_list_group)

        # ── 条件参数（4c2a / 4c2b）──
        # 二级嵌套映射：{条件 id → {参数键 → (ptype, widget)}}。
        # render_param_widgets 三函数是**单条件粒度** API，而本区是「多条件 × 多参数」，
        # 故调用侧必须自建该嵌套映射与容器管理（5.7「R1 工作量更正」）。
        self._stop_condition_param_widgets: dict = {}
        self._stop_condition_param_containers: dict = {}
        self._stop_condition_params_group = QGroupBox("条件参数")
        self._stop_condition_params_layout = QFormLayout(self._stop_condition_params_group)
        parent.addWidget(self._stop_condition_params_group)
        self._rebuild_stop_condition_params()

    # ── 停止条件：条件列表（4c1b）────────────────────────────────

    def _setup_stop_condition_list(self):
        """条件列表块：类型下拉 + 添加 + 3 列表格 + 移除/上移/下移。

        类型下拉**按 `internal` 标志过滤**——原「抽卡策略」Tab 的下拉未过滤，
        把仅供内部使用的 consecutive_pool_target 暴露给了用户。
        """
        from gacha_simulator.core.stop_condition import STOP_CONDITION_REGISTRY

        self._stop_condition_type_choices = [
            (key, entry['display_name'])
            for key, entry in STOP_CONDITION_REGISTRY.items()
            if not entry.get('internal', False)
        ]

        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("条件类型:"))
        self.stop_condition_type_combo = QComboBox()
        self.stop_condition_type_combo.addItems(
            [d for _, d in self._stop_condition_type_choices])
        add_row.addWidget(self.stop_condition_type_combo, 1)
        self.stop_condition_add_btn = QPushButton("添加")
        self.stop_condition_add_btn.clicked.connect(self._on_stop_condition_add)
        add_row.addWidget(self.stop_condition_add_btn)
        self._stop_condition_list_layout.addLayout(add_row)

        self.stop_condition_table = QTableWidget()
        self.stop_condition_table.setColumnCount(3)
        self.stop_condition_table.setHorizontalHeaderLabels(["id", "类型", "摘要"])
        header = self.stop_condition_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.stop_condition_table.setColumnWidth(0, 60)
        self.stop_condition_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.stop_condition_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        # id 列可编辑（4d2b1 的 id 管理体系）；其余两列是渲染结果，不可编辑
        self.stop_condition_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.stop_condition_table.itemSelectionChanged.connect(
            self._on_stop_condition_selection_changed)
        self.stop_condition_table.itemChanged.connect(
            self._on_stop_condition_item_changed)
        self._stop_condition_list_layout.addWidget(self.stop_condition_table)

        btn_row = QHBoxLayout()
        for text, slot in (
            ("移除选中", self._on_stop_condition_remove),
            ("上移", lambda: self._move_stop_condition(-1)),
            ("下移", lambda: self._move_stop_condition(1)),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        self._stop_condition_list_layout.addLayout(btn_row)

        self._refresh_stop_condition_table()

    # ── 停止条件：id 管理体系（4d2b1）────────────────────────────

    def _validate_stop_condition_id(self, new_id: str,
                                    current_id: Optional[str] = None) -> Optional[str]:
        """校验条件 id；合法返回 None，非法返回面向用户的可读消息。"""
        import re as _re

        if not new_id:
            return "条件 id 不能为空"
        if new_id in _EXPR_RESERVED_WORDS:
            return (f"id '{new_id}' 是表达式保留字"
                    f"（{' / '.join(_EXPR_RESERVED_WORDS)}），请换一个")
        if not _re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', new_id):
            return (f"id '{new_id}' 不是合法的标识符——"
                    f"只能由字母、数字、下划线组成，且不以数字开头")
        taken = {c['id'] for c in self._stop_condition_conditions}
        if new_id != current_id and new_id in taken:
            return f"id '{new_id}' 已被占用，条件 id 必须唯一"
        return None

    def _rename_stop_condition_id(self, old_id: str, new_id: str) -> None:
        """重命名条件 id 并**同步替换表达式内的全部引用**（含同一 id 多次出现）。

        走 AST 改写而非字符串替换：字符串替换会把 `ab` 中的 `a` 一并改掉，且无法
        区分运算符名。表达式本身非法时退化为按标识符边界替换，尽力保持一致。
        """
        import re as _re

        from gacha_simulator.core.stop_condition_expr import (
            StopConditionExprError, expr_ast_to_text, parse_stop_condition_expr,
        )

        expr = self._stop_condition_expr
        if not expr or not expr.strip():
            return
        try:
            ast = parse_stop_condition_expr(expr)
        except StopConditionExprError:
            self._stop_condition_expr = _re.sub(
                rf'\b{_re.escape(old_id)}\b', new_id, expr)
            return

        def subst(node):
            if node[0] == 'id':
                return ('id', new_id if node[1] == old_id else node[1])
            if node[0] == 'not':
                return ('not', subst(node[1]))
            return (node[0], subst(node[1]), subst(node[2]))

        self._stop_condition_expr = expr_ast_to_text(subst(ast))
        refresh = getattr(self, '_refresh_stop_condition_expr_widget', None)
        if refresh is not None:
            refresh()

    def _on_stop_condition_item_changed(self, item):
        """id 列编辑：校验通过则重命名并同步替换表达式引用，否则回退并提示。

        「重名 / 空 id / 与保留字冲突」一律给出可读提示，**不静默改名**。
        """
        if item is None or item.column() != 0:
            return
        row = item.row()
        if not (0 <= row < len(self._stop_condition_conditions)):
            return
        old_id = self._stop_condition_conditions[row]['id']
        new_id = item.text().strip()
        if new_id == old_id:
            return

        error = self._validate_stop_condition_id(new_id, current_id=old_id)
        if error is not None:
            QMessageBox.warning(self, "条件 id 非法", error)
            self.stop_condition_table.blockSignals(True)
            item.setText(old_id)
            self.stop_condition_table.blockSignals(False)
            return

        self._stop_condition_conditions[row]['id'] = new_id
        self._rename_stop_condition_id(old_id, new_id)
        if self._stop_condition_selected_id == old_id:
            self._stop_condition_selected_id = new_id
        # ⚠ 此处**不得**整表刷新：本方法是 QTableWidget.itemChanged 的槽，而
        # setRowCount()/setItem() 会删除正在发信的那个 QTableWidgetItem——
        # 在信号处理中删除发信项是隐患（实测会拿到已析构的包装器）。
        # 重命名只改模型与表达式，id 单元格已由用户输入，其余两列与 id 无关，
        # 无需刷新。

    def _allocate_stop_condition_id(self) -> str:
        """分配未占用的条件 id（a/b/c…，用尽后退化为 c1/c2…）。

        避开既有 id 与表达式保留字（and / or / not）。
        """
        used = {c['id'] for c in self._stop_condition_conditions} | set(_EXPR_RESERVED_WORDS)
        for i in range(26):
            cid = chr(ord('a') + i)
            if cid not in used:
                return cid
        n = 1
        while f'c{n}' in used:
            n += 1
        return f'c{n}'

    @staticmethod
    def _stop_condition_default_node(type_key: str) -> dict:
        """按注册表默认值构造叶子节点。"""
        from gacha_simulator.core.stop_condition import STOP_CONDITION_REGISTRY

        node: dict = {'type': type_key}
        for pdesc in STOP_CONDITION_REGISTRY[type_key].get('params', []):
            node[pdesc.key] = pdesc.default
        return node

    @staticmethod
    def _stop_condition_summary(node: dict) -> str:
        """摘要列——由条件对象自身的 description() 渲染。

        节点暂时非法（编辑中途）时不抛错，退化为原始字段展示。
        """
        from gacha_simulator.core.stop_condition import create_stop_condition

        try:
            cond = create_stop_condition(dict(node))
            return cond.description() if cond is not None else ''
        except Exception:
            return ' / '.join(f'{k}={v}' for k, v in node.items() if k != 'type')

    def _refresh_stop_condition_table(self):
        """按 self._stop_condition_conditions 重建表格（幂等）。"""
        table = getattr(self, 'stop_condition_table', None)
        if table is None:
            return
        from gacha_simulator.core.stop_condition import STOP_CONDITION_REGISTRY

        table.blockSignals(True)
        table.setRowCount(len(self._stop_condition_conditions))
        for row, cond in enumerate(self._stop_condition_conditions):
            node = {k: v for k, v in cond.items() if k != 'id'}
            entry = STOP_CONDITION_REGISTRY.get(node.get('type'))
            type_name = entry['display_name'] if entry else str(node.get('type'))
            for col, text in enumerate((cond['id'], type_name,
                                        self._stop_condition_summary(node))):
                table.setItem(row, col, QTableWidgetItem(text))
        table.blockSignals(False)

        # 选中态回落：优先保持原选中 id，否则选首行
        ids = [c['id'] for c in self._stop_condition_conditions]
        if self._stop_condition_selected_id in ids:
            table.selectRow(ids.index(self._stop_condition_selected_id))
        elif ids:
            table.selectRow(0)
            self._stop_condition_selected_id = ids[0]
        else:
            self._stop_condition_selected_id = None
        self._on_stop_condition_selection_changed()

    def set_stop_condition_conditions(self, conditions, expr):
        """载入路径的入口：设置条件列表与表达式并刷新表格。"""
        self._stop_condition_conditions = [dict(c) for c in (conditions or [])]
        self._stop_condition_expr = expr or ''
        self._refresh_stop_condition_table()

    def _on_stop_condition_selection_changed(self):
        """同步选中条件——条件参数区（4c2a/4c2b）以它为渲染依据。"""
        table = getattr(self, 'stop_condition_table', None)
        if table is None:
            return
        row = table.currentRow()
        if 0 <= row < len(self._stop_condition_conditions):
            self._stop_condition_selected_id =                 self._stop_condition_conditions[row]['id']
        else:
            self._stop_condition_selected_id = None
        rebuild = getattr(self, '_rebuild_stop_condition_params', None)
        if rebuild is not None:
            rebuild()

    def _on_stop_condition_add(self):
        """添加条件：按当前下拉的类型与注册表默认值新建条目。

        表达式侧的「新增条件自动追加到表达式末尾」（5.7 交互规则 2）归 4d2b2。
        """
        idx = self.stop_condition_type_combo.currentIndex()
        if idx < 0 or idx >= len(self._stop_condition_type_choices):
            return
        type_key = self._stop_condition_type_choices[idx][0]
        node = self._stop_condition_default_node(type_key)
        node_id = self._allocate_stop_condition_id()
        self._stop_condition_conditions.append({'id': node_id, **node})
        self._stop_condition_selected_id = node_id
        self._refresh_stop_condition_table()
        self._on_stop_condition_added(node_id)

    def _on_stop_condition_added(self, node_id: str):
        """新增钩子——表达式追加（4d2b2）覆写本方法。"""
        return None

    def _on_stop_condition_remove(self):
        """移除选中条件。

        「删除仍被表达式引用的 id → 错误态 + 保存阻断」（5.7 交互规则 3）归 4d2b2；
        本项只做列表侧的增删。
        """
        table = getattr(self, 'stop_condition_table', None)
        if table is None:
            return
        row = table.currentRow()
        if not (0 <= row < len(self._stop_condition_conditions)):
            return
        cond_id = self._stop_condition_conditions[row]['id']
        # 规则 3：删除仍被表达式引用的 id → 阻断提示。不做自动摘除——
        # `a and b` 中删掉 `b` 会自动变成 `a`，语义已变却不报错。
        if self._expr_references_id(cond_id):
            QMessageBox.warning(
                self, "条件仍被表达式引用",
                f"条件 '{cond_id}' 仍被表达式引用：\n    {self._stop_condition_expr}\n\n"
                f"请先在表达式中去掉对它的引用，再删除该条件。")
            return
        self._stop_condition_conditions.pop(row)
        self._refresh_stop_condition_table()
        self._refresh_stop_condition_expr_widget()
        self._refresh_stop_condition_error_hint()

    def _move_stop_condition(self, delta: int):
        """上移 / 下移选中条件（列表顺序即表达式追加顺序）。"""
        table = getattr(self, 'stop_condition_table', None)
        if table is None:
            return
        row = table.currentRow()
        target = row + delta
        conds = self._stop_condition_conditions
        if not (0 <= row < len(conds)) or not (0 <= target < len(conds)):
            return
        conds[row], conds[target] = conds[target], conds[row]
        self._stop_condition_selected_id = conds[target]['id']
        self._refresh_stop_condition_table()

    # ── 停止条件：条件参数区（4c2a）──────────────────────────────

    def _prefill_coaxial_threshold(self, cond, params, widget_map):
        """与硬边界同轴条件（all_pools_end / time_limit）的阈值预填（P79 5.7）。

        注册表默认值 0.0 / 86400.0（= 0 天 / 1 天）远早于 env.end_time（默认 168 天），
        用户添加后不改即让模拟在第 0 轮结束（`any(用户条件, 硬边界)` 恒真），
        `final_time = 0` 还会把 `_obtainable` 系列 GDR 的分母收窄。以 env.end_time
        预填后，用户不改即为与硬边界同值、条件退化为冗余而不再截断模拟。

        ⚠ **必须先放宽控件范围再 setValue**：Qt 对超范围 setValue 不报错、不回显真实
        值，直接钳到上限并显示为合法值（FloatParam 类默认 max_val=99999.0 ≈ 1.16 天），
        预填会静默变成「1.16 天收口」。静态范围（4b2a 的 MAX_SIM_TIME）与这里的
        动态放宽**二者须同时满足**。
        """
        from gacha_simulator.core.stop_condition import COAXIAL_THRESHOLD_KEYS

        pkey = COAXIAL_THRESHOLD_KEYS.get(cond.get('type'))
        if pkey is None:
            return
        entry = widget_map.get(pkey)
        pdesc = next((p for p in params if p.key == pkey), None)
        if entry is None or pdesc is None:
            return
        _ptype, widget = entry

        # 用户已自定义则不动它（判据：与注册表默认值不同）
        current = cond.get(pkey)
        if current is not None and current != pdesc.default:
            return

        # 本处保留 getattr 容忍：预填是「能读到终点就预填」的便利项，不构成硬依赖；
        # 且它不在 §11.1 声明的跨文件对（4a2 ↔ 4a4 / 4c1a）内，硬取属性会引入一个
        # 计划未声明的失效形态。
        store = getattr(self, '_store', None)
        end_time = getattr(store, 'end_time', None) if store is not None else None
        if not end_time:
            return

        widget.setRange(float(getattr(pdesc, 'min_val', 0.0)),
                        max(float(widget.maximum()), float(end_time)))
        widget.setValue(float(end_time))
        # 同步模型：apply 落盘的应是预填值（否则界面显示 end_time、落盘仍是旧默认）
        cond[pkey] = float(end_time)

    def _sync_stop_condition_params(self):
        """把参数区控件的当前值收回模型。

        **每次重建前必须先收**——否则 set_params_to_widgets 会用模型里的旧值覆盖
        用户刚做的编辑（这是「重建」幂等性的前提）。
        """
        from gacha_simulator.gui.param_renderer import collect_params_from_widgets

        for cond in self._stop_condition_conditions:
            wmap = self._stop_condition_param_widgets.get(cond['id'])
            if not wmap:
                continue
            cond.update(collect_params_from_widgets(wmap))

    def _rebuild_stop_condition_params(self):
        """按条件列表（重）建参数区容器，回填当前值，并只显示选中条件。

        幂等：先收值再回填，故反复调用不改变模型与控件的内容。
        """
        from gacha_simulator.core.stop_condition import STOP_CONDITION_REGISTRY
        from gacha_simulator.gui.param_renderer import (
            render_param_widgets, set_params_to_widgets,
        )

        layout = getattr(self, '_stop_condition_params_layout', None)
        if layout is None:
            return
        # 顺序不可颠倒：先收值（控件还在）→ 再整表清空（removeRow(int) 会删除控件）
        # → 再重建。若用 removeRow(QWidget*) 逐行移除，其对控件的析构语义不确定，
        # 事后触碰 Python 包装器会直接崩溃（实测）。
        self._sync_stop_condition_params()
        self._stop_condition_param_widgets = {}
        self._stop_condition_param_containers = {}
        while layout.rowCount():
            layout.removeRow(0)

        conds = self._stop_condition_conditions
        for cond in conds:
            cid = cond['id']
            entry = STOP_CONDITION_REGISTRY.get(cond.get('type'))
            params = entry.get('params', []) if entry else []

            container = QWidget()
            form = QFormLayout(container)
            form.setContentsMargins(0, 0, 0, 0)
            widget_map: dict = {}
            skipped = render_param_widgets(
                params, form, widget_map, parent=container)
            if skipped:
                form.addRow(QLabel(
                    "以下参数无可用控件，本界面不支持配置："
                    + "、".join(p.display_name for p in skipped)))
            layout.addRow(container)
            self._stop_condition_param_containers[cid] = container
            self._stop_condition_param_widgets[cid] = widget_map

            node = {k: v for k, v in cond.items() if k != 'id'}
            set_params_to_widgets(params, widget_map, node)
            self._prefill_coaxial_threshold(cond, params, widget_map)

        selected = self._stop_condition_selected_id
        for cid, container in self._stop_condition_param_containers.items():
            container.setVisible(cid == selected)

        group = getattr(self, '_stop_condition_params_group', None)
        if group is not None:
            group.setVisible(bool(conds))

    # ── 停止条件：内存态 ↔ store（4c2b）──────────────────────────

    def _build_stop_condition_tree(self):
        """由编辑期内存态（条件列表 + 表达式）重建条件树。

        **表达式是组合的唯一真相源**（5.7 交互规则 1）。表达式为空 → ``None``
        （空树 = 仅引擎硬边界收口）。

        表达式非法或引用了不存在的 id 时**保守返回上一次的有效树**，不写入半成品：
        本方法经 apply_to_store 挂在预览去抖与导出两条高频路径上，写入中间态会把
        用户正在编辑的条件树写坏。语法错误本身由即时校验（4d2b3）行内提示、
        由 validate_banners（4d3）阻断保存，不在此静默吞掉。
        """
        from gacha_simulator.core.stop_condition_expr import (
            StopConditionExprError, expr_to_tree,
        )

        try:
            tree = expr_to_tree(self._stop_condition_expr,
                                self._stop_condition_conditions)
        except StopConditionExprError:
            return self._stop_condition_tree
        self._stop_condition_tree = tree
        return self._stop_condition_tree

    def _load_stop_condition_from_store(self, store):
        """从 ``store.stop_condition`` 回填条件列表与表达式。

        走 4d2a 的「树 → (条件列表, 表达式)」方向；空树得到 ``([], '')``。
        """
        from gacha_simulator.core.stop_condition_expr import (
            tree_to_conditions_and_expr,
        )

        tree = getattr(store, 'stop_condition', None)
        self._stop_condition_tree = tree
        conditions, expr = tree_to_conditions_and_expr(tree)
        self.set_stop_condition_conditions(conditions, expr)

    # ── 停止条件：组合区（4d2b2）────────────────────────────────

    def _setup_stop_condition_compose(self):
        """组合方式单选 + 表达式行（同屏、单向同步，5.7 交互规则 1 与 ⑨）。"""
        row = QHBoxLayout()
        self._stop_condition_mode_buttons = {}
        for mode, label in (('any', '任一满足'), ('all', '全部满足'),
                            ('custom', '自定义')):
            button = QRadioButton(label)
            button.toggled.connect(
                lambda checked, m=mode: self._on_stop_condition_mode_toggled(m, checked))
            self._stop_condition_mode_buttons[mode] = button
            row.addWidget(button)
        row.addStretch()
        self._stop_condition_compose_layout.addLayout(row)

        expr_row = QHBoxLayout()
        expr_row.addWidget(QLabel("表达式:"))
        self.stop_condition_expr_edit = QLineEdit()
        self.stop_condition_expr_edit.setPlaceholderText("例：a or (b and not c)")
        self.stop_condition_expr_edit.textChanged.connect(
            self._on_stop_condition_expr_edited)
        expr_row.addWidget(self.stop_condition_expr_edit, 1)
        # 行尾校验图标（5.7 布局）：即时反馈，不阻断输入
        self.stop_condition_expr_status = QLabel()
        expr_row.addWidget(self.stop_condition_expr_status)
        self.stop_condition_apply_btn = QPushButton("应用")
        self.stop_condition_apply_btn.clicked.connect(self._on_stop_condition_apply)
        expr_row.addWidget(self.stop_condition_apply_btn)
        self._stop_condition_compose_layout.addLayout(expr_row)

        # 错误行：红字反馈。**不阻断输入**——用户可继续敲到合法为止
        self.stop_condition_error_label = QLabel()
        self.stop_condition_error_label.setWordWrap(True)
        self.stop_condition_error_label.setStyleSheet("color: #c0392b;")
        self._stop_condition_compose_layout.addWidget(self.stop_condition_error_label)

        self._refresh_stop_condition_expr_widget()

    def _detect_stop_condition_mode(self) -> str:
        """按当前表达式判定单选项：'any' / 'all' / 'custom'。

        判据是「表达式 AST 与 a or b or c（或 a and b and c）等价」——按文本比对
        会被空格与括号写法差异打败。
        """
        from gacha_simulator.core.stop_condition_expr import (
            StopConditionExprError, parse_stop_condition_expr,
        )

        ids = [c['id'] for c in self._stop_condition_conditions]
        expr = (self._stop_condition_expr or '').strip()
        if not ids or not expr:
            return 'custom'
        try:
            current = parse_stop_condition_expr(expr)
        except StopConditionExprError:
            return 'custom'
        for mode, op in (('any', 'or'), ('all', 'and')):
            operands = _expr_flat_operands(current, op)
            if operands is None or len(operands) != len(ids):
                continue
            # 全部操作数须是裸 id 且正好覆盖条件列表（顺序无关——a or b 与 b or a
            # 同属「任一满足」）
            names = [n[1] for n in operands if n[0] == 'id']
            if len(names) != len(operands):
                continue
            if sorted(names) == sorted(ids):
                return mode
        return 'custom'

    def _refresh_stop_condition_expr_widget(self):
        """表达式行与单选从内存态刷新（阻塞信号，保证单向流动不成环）。"""
        edit = getattr(self, 'stop_condition_expr_edit', None)
        if edit is None:
            return
        edit.blockSignals(True)
        edit.setText(self._stop_condition_expr)
        edit.blockSignals(False)

        mode = self._detect_stop_condition_mode()
        buttons = getattr(self, '_stop_condition_mode_buttons', {})
        for key, button in buttons.items():
            button.blockSignals(True)
            button.setChecked(key == mode)
            button.blockSignals(False)

        # 条件列表为空：表达式行禁用并提示由硬边界收口（5.7「选项为空时的表现」）
        empty = not self._stop_condition_conditions
        edit.setEnabled(not empty)
        if empty:
            edit.setPlaceholderText("未配置停止条件，模拟将由硬边界收口")
        else:
            edit.setPlaceholderText("例：a or (b and not c)")

        self._refresh_stop_condition_error_hint()

    def _on_stop_condition_mode_toggled(self, mode: str, checked: bool):
        """单选 → 表达式重写（规则 1）。「自定义」不重写，它只标记手改后的状态。"""
        if not checked or mode == 'custom':
            return
        ids = [c['id'] for c in self._stop_condition_conditions]
        op = 'or' if mode == 'any' else 'and'
        self._stop_condition_expr = f' {op} '.join(ids) if ids else ''
        self._refresh_stop_condition_expr_widget()

    def _on_stop_condition_expr_edited(self, text: str):
        """表达式手改 → 更新内存态 + 单选自动落到「自定义」（规则 1 / ⑨）。

        单向流动：本回调只更新内存态与单选外观，**不回写表达式行**，故不成环。
        """
        self._stop_condition_expr = text
        mode = self._detect_stop_condition_mode()
        buttons = getattr(self, '_stop_condition_mode_buttons', {})
        for key, button in buttons.items():
            button.blockSignals(True)
            button.setChecked(key == mode)
            button.blockSignals(False)
        refresh = getattr(self, '_refresh_stop_condition_error_hint', None)
        if refresh is not None:
            refresh()

    def _expr_references_id(self, cond_id: str) -> bool:
        """表达式是否引用了该 id（AST 判定；表达式非法时按标识符边界退让）。"""
        import re as _re

        from gacha_simulator.core.stop_condition_expr import StopConditionExprError

        expr = self._stop_condition_expr or ''
        if not expr.strip():
            return False
        try:
            return cond_id in _collect_expr_ids(expr)
        except StopConditionExprError:
            return bool(_re.search(rf'\b{_re.escape(cond_id)}\b', expr))

    def _on_stop_condition_added(self, node_id: str):
        """新增条件自动追加到表达式末尾（规则 2，覆写 4c1b 的空钩子）。

        「保持既有结构」：追加 `or <id>` 时既有部分作为一个整体参与（如
        `a and b` + `or c` 解析为 `(a and b) or c`）。
        """
        expr = (self._stop_condition_expr or '').strip()
        self._stop_condition_expr = f'{expr} or {node_id}' if expr else node_id
        self._refresh_stop_condition_expr_widget()

    # ── 停止条件：即时校验与应用（4d2b3）────────────────────────

    def _stop_condition_expr_error(self) -> Optional[str]:
        """校验当前表达式；合法返回 None，非法返回面向用户的可读消息。

        两类问题：语法非法；引用了已被删除的条件 id。
        """
        from gacha_simulator.core.stop_condition_expr import (
            StopConditionExprError, parse_stop_condition_expr,
        )

        expr = (self._stop_condition_expr or '').strip()
        if not expr:
            return None
        ids = {c['id'] for c in self._stop_condition_conditions}
        try:
            parse_stop_condition_expr(expr)
        except StopConditionExprError as exc:
            return str(exc)

        dangling = [rid for rid in _collect_expr_ids(expr) if rid not in ids]
        if dangling:
            return ("以下条件已被删除，但仍被表达式引用："
                    + '、'.join(f"'{d}'" for d in dangling))
        return None

    def _refresh_stop_condition_error_hint(self):
        """刷新行尾图标与错误行（即时校验，不阻断输入）。"""
        status = getattr(self, 'stop_condition_expr_status', None)
        label = getattr(self, 'stop_condition_error_label', None)
        if status is None or label is None:
            return
        error = self._stop_condition_expr_error()
        if error:
            status.setText('✗')
            status.setStyleSheet("color: #c0392b;")
            label.setText(error)
        else:
            status.setText('✔' if (self._stop_condition_expr or '').strip() else '')
            status.setStyleSheet("color: #27ae60;")
            label.setText('')

    def _on_stop_condition_apply(self):
        """应用：把面板内存态提交到条件树并落 store（5.7 交互规则 5）。

        校验不通过则**拒绝应用并保留原态**——表达式 → 条件树 → 写 store 的链路
        不写入半成品；错误另有行内红字反馈与保存阻断（validate_banners）。
        """
        error = self._stop_condition_expr_error()
        if error:
            QMessageBox.warning(
                self, "停止条件表达式非法",
                f"{error}\n\n已保留上一次的有效配置，本次未应用。")
            return
        self.apply_to_store()
        self.stop_condition_error_label.setText('已应用到配置')

    def _refresh_stop_condition_hint(self):
        """顶部只读提示：模拟将在 end_time（所有卡池关闭时刻）后强制结束。

        读 ``self._store.end_time``（5.5 的单一实现点），面板内不重算；``_store``
        未就绪或 end_time 为 0 时显示「—」。
        """
        label = getattr(self, 'stop_condition_hint', None)
        if label is None:
            return
        # 直读 self._store.end_time（5.5 的单一实现点），**不用 getattr 兜属性缺失**：
        # 计划 §11.1 把「单独 revert 4a2 后 4c1a 抛 AttributeError」列为该跨文件对
        # （4a2 ↔ 4a4 / 4c1a）的失效形态，而 getattr 会把显式失败降级为静默显示「—」，
        # 使该回滚保护失效。这里只需容忍 `_store` 未就绪（面板构造期）。
        store = getattr(self, '_store', None)
        end_time = store.end_time if store is not None else None
        if not end_time:
            label.setText("ℹ 模拟终点：—（配置载入后显示）")
        else:
            label.setText(
                f"ℹ 模拟将在 {end_time / 86400:.1f} 天后强制结束（所有卡池关闭时刻）"
                f"——用户停止条件与之取「任一满足」，不可满足的条件不会让模拟越界")

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
        skipped = render_param_widgets(
            entry.params, self._strategy_params_layout,
            self._strategy_param_widgets, parent=self,
        )
        # P79 4b3：未能渲染的参数不得静默消失（原实现静默 continue）——在参数区显式提示
        if skipped:
            self._strategy_params_layout.addRow(QLabel(
                "以下参数无可用控件，本界面不支持配置："
                + "、".join(p.display_name for p in skipped)))

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

    def _setup_resource_def_tab(self, parent):
        """「资源定义」独立 Tab（P78 方案 X）——左列表 + 右详情表单。

        数据层 resource_defs: Dict[str, str] 一字不动（11 个分析面板零改动）——
        本 Tab 是 ConfigStore.resource_defs 的编辑视图：左 QListWidget 列资源 id，
        右详情表单编辑 display_name / initial_amount。自选券候选集区域（select_voucher）
        在 5b 挂接。
        """
        # ── 实例变量 ──
        self.resource_defs: list = []          # List[dict] —— 内部数据（同 _card_defs 模式）
        self._current_resource_idx: int = -1   # 当前选中索引
        self._resource_lifecycle_enabled: bool = True   # P77：生命周期全局开关（总闸）

        outer = QVBoxLayout(parent)

        # ═══ 水平两栏 ═══
        main_layout = QHBoxLayout()

        # ── 左栏：资源列表 ──
        left_layout = QVBoxLayout()
        self._resource_list = QListWidget()
        self._resource_list.currentRowChanged.connect(self._on_resource_selected)
        left_layout.addWidget(self._resource_list)

        res_btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加")
        add_btn.clicked.connect(self._add_resource_def)
        remove_btn = QPushButton("移除选中")
        remove_btn.clicked.connect(self._remove_resource_def)
        auto_btn = QPushButton("自动生成")
        auto_btn.clicked.connect(self._auto_generate_resource_defs)
        res_btn_layout.addWidget(add_btn)
        res_btn_layout.addWidget(remove_btn)
        res_btn_layout.addWidget(auto_btn)
        res_btn_layout.addStretch()
        left_layout.addLayout(res_btn_layout)

        main_layout.addLayout(left_layout, 1)

        # ── 右栏：详情面板 ──
        self._resource_detail_group = QGroupBox("资源详情")
        self._resource_detail_group.setEnabled(False)
        detail_form = QFormLayout(self._resource_detail_group)

        self._resource_id_edit = QLineEdit()
        self._resource_id_edit.textChanged.connect(self._on_resource_def_changed)
        detail_form.addRow("资源ID:", self._resource_id_edit)

        self._resource_name_edit = QLineEdit()
        self._resource_name_edit.textChanged.connect(self._on_resource_def_changed)
        detail_form.addRow("显示名称:", self._resource_name_edit)

        self._resource_init_spin = QSpinBox()
        self._resource_init_spin.setRange(0, 9999999)
        self._resource_init_spin.setSingleStep(100)
        self._resource_init_spin.valueChanged.connect(self._on_resource_def_changed)
        detail_form.addRow("初始数量:", self._resource_init_spin)

        # P78：自选券候选集区域（ISSUE-004——详情面板按资源 id 关联编辑候选集）
        self._voucher_group = QGroupBox("自选券候选集")
        voucher_layout = QVBoxLayout(self._voucher_group)
        self._voucher_hint_label = QLabel("勾选该资源可兑换的候选卡（未勾选 = 非自选券/无候选）。")
        self._voucher_hint_label.setWordWrap(True)
        voucher_layout.addWidget(self._voucher_hint_label)
        self._voucher_cards_list = QListWidget()
        self._voucher_cards_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        # P78 布局修复：不再固定 150 上限（否则 group 内下方大片空白）——改为
        # Expanding 让列表铺满 group 剩余空间；最小高度 80 保证可用性。P77 交接：
        # 详情面板后续加 lifecycle 占位区时，Expanding 让本列表与 P77 区域动态分配高度。
        self._voucher_cards_list.setMinimumHeight(80)
        self._voucher_cards_list.setSizePolicy(QSizePolicy.Policy.Expanding,
                                               QSizePolicy.Policy.Expanding)
        # 变更实时写回 self._select_vouchers（ISSUE-004 数据流）
        self._voucher_cards_list.itemSelectionChanged.connect(self._on_voucher_selection_changed)
        voucher_layout.addWidget(self._voucher_cards_list)
        detail_form.addRow(self._voucher_group)

        # P77：资源生命周期区域（到期时刻 + 到期行为，按资源 id 关联编辑）
        self._setup_resource_lifecycle_group(detail_form)

        main_layout.addWidget(self._resource_detail_group, 2)

        outer.addLayout(main_layout)

        # P78：资源获取规则 / 指定日期等仍在「资源获取」Tab——本 Tab 仅资源定义

    # ── P77：资源生命周期区域（UI + 读写 + 下拉数据源）──────────────────

    def _setup_resource_lifecycle_group(self, detail_form):
        """资源生命周期区域：到期时刻（三态）+ 到期行为（三态）+ 转换比例。

        挂载于资源详情表单下（P78 预留的 lifecycle 占位区），按资源 id 关联编辑：
        字段写回 self.resource_defs[idx]，apply_to_store 时汇总为
        store.resource_lifecycle.rules。三态与从属控件的联动见 _sync_lifecycle_controls。
        """
        self._lifecycle_group = QGroupBox("资源生命周期")
        lc_outer = QVBoxLayout(self._lifecycle_group)

        self._lifecycle_enabled_cb = QCheckBox("启用资源生命周期")
        self._lifecycle_enabled_cb.setChecked(True)
        self._lifecycle_enabled_cb.setToolTip(
            "全局开关。关闭时已配置的规则仍保留，但模拟不执行到期结算（往返不丢配置）")
        self._lifecycle_enabled_cb.toggled.connect(self._on_lifecycle_enabled_toggled)
        lc_outer.addWidget(self._lifecycle_enabled_cb)

        lc_form = QFormLayout()

        self._lifecycle_expire_mode = QComboBox()
        self._lifecycle_expire_mode.addItems(["永不过期", "随卡池下架", "指定天数"])
        self._lifecycle_expire_mode.setToolTip(
            "到期时刻。随卡池下架 = 取所选卡池的结束时间（卡池下架时刻资源失效）；"
            "指定天数 = 模拟开始后第 N 天失效")
        self._lifecycle_expire_mode.currentIndexChanged.connect(
            self._on_lifecycle_expire_mode_changed)
        lc_form.addRow("到期时刻:", self._lifecycle_expire_mode)

        self._lifecycle_banner_combo = QComboBox()
        self._lifecycle_banner_combo.currentIndexChanged.connect(
            self._on_resource_lifecycle_changed)
        lc_form.addRow("下架卡池:", self._lifecycle_banner_combo)

        self._lifecycle_days_spin = QDoubleSpinBox()
        self._lifecycle_days_spin.setRange(0.0, 9999.0)
        self._lifecycle_days_spin.setDecimals(1)
        self._lifecycle_days_spin.setSingleStep(1.0)
        self._lifecycle_days_spin.valueChanged.connect(self._on_resource_lifecycle_changed)
        lc_form.addRow("到期天数:", self._lifecycle_days_spin)

        self._lifecycle_action_combo = QComboBox()
        self._lifecycle_action_combo.addItems(["（未设置）", "转换到", "清零"])
        self._lifecycle_action_combo.currentIndexChanged.connect(
            self._on_lifecycle_action_changed)
        lc_form.addRow("到期行为:", self._lifecycle_action_combo)

        self._lifecycle_target_combo = QComboBox()
        self._lifecycle_target_combo.currentIndexChanged.connect(
            self._on_resource_lifecycle_changed)
        lc_form.addRow("转换目标:", self._lifecycle_target_combo)

        ratio_row = QHBoxLayout()
        self._lifecycle_from_spin = QSpinBox()
        self._lifecycle_from_spin.setRange(1, 99999)
        self._lifecycle_from_spin.valueChanged.connect(self._on_resource_lifecycle_changed)
        self._lifecycle_to_spin = QSpinBox()
        self._lifecycle_to_spin.setRange(1, 99999)
        self._lifecycle_to_spin.valueChanged.connect(self._on_resource_lifecycle_changed)
        ratio_row.addWidget(QLabel("每"))
        ratio_row.addWidget(self._lifecycle_from_spin)
        ratio_row.addWidget(QLabel("个 换"))
        ratio_row.addWidget(self._lifecycle_to_spin)
        ratio_row.addWidget(QLabel("个"))
        ratio_row.addStretch()
        lc_form.addRow("转换比例:", ratio_row)

        lc_outer.addLayout(lc_form)
        detail_form.addRow(self._lifecycle_group)
        self._sync_lifecycle_controls()

    def _on_lifecycle_enabled_toggled(self, checked):
        """总闸切换：从属控件置灰但值保留（总闸自身始终可点），并刷新预览。"""
        self._resource_lifecycle_enabled = bool(checked)
        self._sync_lifecycle_controls()
        self._update_preview()

    def _on_lifecycle_expire_mode_changed(self):
        self._sync_lifecycle_controls()
        self._on_resource_lifecycle_changed()

    def _on_lifecycle_action_changed(self):
        self._sync_lifecycle_controls()
        self._on_resource_lifecycle_changed()

    def _sync_lifecycle_controls(self):
        """三态联动：按当前选择启用从属控件（未选中的保留值但不写入规则）。"""
        enabled = getattr(self, '_resource_lifecycle_enabled', True)
        mode = self._lifecycle_expire_mode.currentIndex()
        self._lifecycle_expire_mode.setEnabled(enabled)
        self._lifecycle_banner_combo.setEnabled(enabled and mode == 1)
        self._lifecycle_days_spin.setEnabled(enabled and mode == 2)
        self._lifecycle_action_combo.setEnabled(enabled)

        is_convert = (self._lifecycle_action_combo.currentIndex() == 1)
        self._lifecycle_target_combo.setEnabled(enabled and is_convert)
        self._lifecycle_from_spin.setEnabled(enabled and is_convert)
        self._lifecycle_to_spin.setEnabled(enabled and is_convert)

    def _on_resource_lifecycle_changed(self):
        """生命周期控件变更：实时写回当前资源详情并刷新预览。"""
        self._flush_resource_detail()
        self._update_preview()

    def _refresh_lifecycle_banner_combo(self, preserve_current=True):
        """到期对齐下拉数据源：仅列「有结束时间且非永久池」的 banner id。

        与解析期校验同口径（_is_permanent 原始标记），避免下拉可选但保存后
        重载报 ConfigError 的口径分叉（P77 ISSUE-302）。

        blockSignals 用保存/恢复而非固定 False：本方法可能被调用于外层
        blockSignals(True) 区间内（_populate_resource_detail），Qt 的
        blockSignals 非嵌套计数，固定 False 会提前解除外层屏蔽导致回填中途触发写回。
        """
        current = self._lifecycle_banner_combo.currentText()
        _prev = self._lifecycle_banner_combo.blockSignals(True)
        self._lifecycle_banner_combo.clear()
        for b in getattr(self, '_banner_defs', []) or []:
            bid = b.get('id', '')
            if not bid or b.get('is_permanent'):
                continue
            if b.get('available_until') is None:
                continue
            self._lifecycle_banner_combo.addItem(bid)
        if preserve_current and current:
            if self._lifecycle_banner_combo.findText(current) < 0:
                # 原值不在候选中（悬垂引用）：临时补入，避免 findText 失败后
                # 静默落到 index 0 并在写回时改写用户的到期对齐目标
                self._lifecycle_banner_combo.addItem(current)
            idx = self._lifecycle_banner_combo.findText(current)
            if idx >= 0:
                self._lifecycle_banner_combo.setCurrentIndex(idx)
        self._lifecycle_banner_combo.blockSignals(_prev)

    def _refresh_lifecycle_target_combo(self, preserve_current=True):
        """转换目标下拉数据源：全部已注册资源 id（含原值兜底，见上）。"""
        current = self._lifecycle_target_combo.currentText()
        _prev = self._lifecycle_target_combo.blockSignals(True)
        self._lifecycle_target_combo.clear()
        for rid in self._get_resource_ids():
            self._lifecycle_target_combo.addItem(rid)
        if preserve_current and current:
            if self._lifecycle_target_combo.findText(current) < 0:
                self._lifecycle_target_combo.addItem(current)
            idx = self._lifecycle_target_combo.findText(current)
            if idx >= 0:
                self._lifecycle_target_combo.setCurrentIndex(idx)
        self._lifecycle_target_combo.blockSignals(_prev)

    def _refresh_lifecycle_combos(self, preserve_current=True):
        """两个下拉数据源一并刷新（资源/Banner 增删后调用）。

        preserve_current=False 用于详情回填场景：此时控件值即将被回填覆盖，
        保留旧值会把上一行的残留项带入新列表。
        """
        if not hasattr(self, '_lifecycle_banner_combo'):
            return
        self._refresh_lifecycle_banner_combo(preserve_current=preserve_current)
        self._refresh_lifecycle_target_combo(preserve_current=preserve_current)

    def _lifecycle_rule_from_detail(self, res: dict):
        """资源详情 dict → 生命周期规则 dict；无有效规则返回 None。

        有效性判定：到期时刻已选（banner 或天数）且到期行为已选
        （转换含目标与比例，或清零）。resource_id 为空亦视为无效。
        """
        rid = res.get('resource_id', '')
        if not rid:
            return None

        mode = res.get('expire_mode', 'none')
        if mode == 'banner':
            banner_id = res.get('expire_banner', '')
            if not banner_id:
                return None
            rule = {'resource_id': rid, 'expire_with_banner': banner_id}
        elif mode == 'at':
            rule = {'resource_id': rid, 'expire_at': float(res.get('expire_at') or 0.0)}
        else:
            return None

        on_expire = res.get('on_expire')
        if not on_expire:
            return None
        rule['on_expire'] = dict(on_expire)
        return rule

    def _on_resource_selected(self, row: int):
        """左列表切换 → 保存当前编辑 → 填充新资源详情。"""
        self._flush_resource_detail()
        if row < 0 or row >= len(self.resource_defs):
            self._resource_detail_group.setEnabled(False)
            self._current_resource_idx = -1
            return
        self._current_resource_idx = row
        self._resource_detail_group.setEnabled(True)
        self._populate_resource_detail(self.resource_defs[row])

    def _rename_lifecycle_references(self, old_id: str, new_id: str):
        """资源重命名时同步改写生命周期规则中的转换目标（P77 §3.6 外键级联）。

        仅改写引用方的 on_expire.convert_to；被重命名资源自身的 resource_id 由
        _flush_resource_detail 直接写入，不在此处理。当前行的转换目标下拉若指向
        旧 id 需一并更新，否则随后读控件写回时会用旧值覆盖改写结果。

        范围不含 select_vouchers（P78 自选券的资源引用），那属 P78 的外键语义。
        """
        if hasattr(self, '_lifecycle_target_combo'):
            if self._lifecycle_target_combo.currentText() == old_id:
                self._refresh_lifecycle_target_combo(preserve_current=False)
                _idx = self._lifecycle_target_combo.findText(new_id)
                if _idx >= 0:
                    self._lifecycle_target_combo.setCurrentIndex(_idx)
        for d in self.resource_defs:
            on_expire = d.get('on_expire') or {}
            if on_expire.get('convert_to') == old_id:
                d['on_expire'] = dict(on_expire, convert_to=new_id)

    def _flush_resource_detail(self):
        """从右侧控件读取当前值 → 写回 self.resource_defs[idx]。"""
        if self._current_resource_idx < 0 or self._current_resource_idx >= len(self.resource_defs):
            return
        res = self.resource_defs[self._current_resource_idx]
        _old_id = res.get('resource_id', '')
        _new_id = self._resource_id_edit.text().strip()
        res['resource_id'] = _new_id
        # P77（§3.6 外键级联）：资源重命名时同步改写引用方的转换目标。放在写入自身
        # resource_id 之后，使下拉候选已含新 id；不改写则引用方规则会因目标悬垂
        # 在 apply_to_store 重建时被静默过滤（重命名资源即丢失别的资源的转换规则）。
        if _old_id and _new_id and _old_id != _new_id:
            self._rename_lifecycle_references(_old_id, _new_id)
        res['display_name'] = self._resource_name_edit.text().strip()
        res['initial_amount'] = self._resource_init_spin.value()
        # P77：生命周期字段写回（三态 → 归一化存储，供 _lifecycle_rule_from_detail 汇总）
        if hasattr(self, '_lifecycle_expire_mode'):
            mode = self._lifecycle_expire_mode.currentIndex()
            res['expire_mode'] = ('none', 'banner', 'at')[mode]
            res['expire_banner'] = (self._lifecycle_banner_combo.currentText()
                                    if mode == 1 else '')
            res['expire_at'] = (float(self._lifecycle_days_spin.value())
                                if mode == 2 else None)
            action = self._lifecycle_action_combo.currentIndex()
            if action == 1:
                res['on_expire'] = {
                    'convert_to': self._lifecycle_target_combo.currentText(),
                    'from': int(self._lifecycle_from_spin.value()),
                    'to': int(self._lifecycle_to_spin.value()),
                }
            elif action == 2:
                res['on_expire'] = {'clear': True}
            else:
                res['on_expire'] = None
        # 更新左列表显示
        label = f"{res['resource_id']} ({res['display_name']})" if res['display_name'] else res['resource_id']
        self._resource_list.item(self._current_resource_idx).setText(label)

    def _populate_resource_detail(self, res: dict):
        """将单条资源数据填入右侧控件（阻断信号——防逐字段触发 _flush 串扰）。"""
        # P77：生命周期控件一并纳入同一阻断区间（回填中途态不得被判为脏而触发写回链）
        widgets = [self._resource_id_edit, self._resource_name_edit, self._resource_init_spin]
        if hasattr(self, '_lifecycle_expire_mode'):
            widgets += [self._lifecycle_expire_mode, self._lifecycle_banner_combo,
                        self._lifecycle_days_spin, self._lifecycle_action_combo,
                        self._lifecycle_target_combo, self._lifecycle_from_spin,
                        self._lifecycle_to_spin]
        for w in widgets:
            w.blockSignals(True)
        self._resource_id_edit.setText(res.get('resource_id', ''))
        self._resource_name_edit.setText(res.get('display_name', ''))
        self._resource_init_spin.setValue(int(res.get('initial_amount', 0)))
        # P77：生命周期字段回填（先刷新下拉数据源，再选值）
        if hasattr(self, '_lifecycle_expire_mode'):
            self._refresh_lifecycle_combos(preserve_current=False)
            mode = res.get('expire_mode', 'none')
            self._lifecycle_expire_mode.setCurrentIndex({'none': 0, 'banner': 1, 'at': 2}.get(mode, 0))
            if res.get('expire_banner'):
                _bid = res['expire_banner']
                # 悬垂引用（banner 已删或不可对齐）原样保留为列表项，避免 findText
                # 失败后静默落到 index 0、写回时改写用户的到期对齐目标
                if self._lifecycle_banner_combo.findText(_bid) < 0:
                    self._lifecycle_banner_combo.addItem(_bid)
                idx = self._lifecycle_banner_combo.findText(_bid)
                if idx >= 0:
                    self._lifecycle_banner_combo.setCurrentIndex(idx)
            self._lifecycle_days_spin.setValue(float(res.get('expire_at') or 0.0))
            on_expire = res.get('on_expire') or {}
            if 'convert_to' in on_expire:
                self._lifecycle_action_combo.setCurrentIndex(1)
                _tgt = on_expire['convert_to']
                if self._lifecycle_target_combo.findText(_tgt) < 0:
                    self._lifecycle_target_combo.addItem(_tgt)
                idx = self._lifecycle_target_combo.findText(_tgt)
                if idx >= 0:
                    self._lifecycle_target_combo.setCurrentIndex(idx)
                self._lifecycle_from_spin.setValue(int(on_expire.get('from', 1)))
                self._lifecycle_to_spin.setValue(int(on_expire.get('to', 1)))
            elif on_expire.get('clear'):
                self._lifecycle_action_combo.setCurrentIndex(2)
            else:
                self._lifecycle_action_combo.setCurrentIndex(0)
        for w in widgets:
            w.blockSignals(False)
        if hasattr(self, '_lifecycle_expire_mode'):
            self._sync_lifecycle_controls()
        # P78（ISSUE-004）：候选集回填——填充全部卡 id + 勾选当前资源的候选集
        self._populate_voucher_candidates(res.get('resource_id', ''))

    def _populate_voucher_candidates(self, resource_id: str):
        """填充自选券候选卡列表——全部 card_defs 可勾选，勾选态 = 该资源的候选集。

        数据源 store.card_defs（全部卡 id）；当前资源的候选集优先读 GUI 内部
        self._select_vouchers（实时——GUI 编辑期间 store 仅 apply_to_store/load 时
        同步，读 store 会回填滞后），fallback store.get_select_voucher_candidates。
        """
        self._voucher_cards_list.blockSignals(True)
        self._voucher_cards_list.clear()
        cards = list(self._store.card_defs) if self._store else []
        selected = set()
        if resource_id:
            for sv in self._select_vouchers:
                if sv['voucher'] == resource_id:
                    selected = set(sv['cards'])
                    break
            else:
                selected = set(self._store.get_select_voucher_candidates(resource_id)) if self._store else set()
        for entry in cards:
            cid = entry.card_id
            item = QListWidgetItem(f"{cid} ({entry.name})" if entry.name else cid)
            item.setData(Qt.ItemDataRole.UserRole, cid)
            self._voucher_cards_list.addItem(item)   # 先 addItem 再 setSelected（未入列表的 item 选中态不生效）
            item.setSelected(cid in selected)
        self._voucher_cards_list.blockSignals(False)

    def _on_voucher_selection_changed(self):
        """候选卡勾选变化 → 实时写回 self._select_vouchers（ISSUE-004 数据流）。

        当前资源 id = _resource_id_edit 文本；勾选集作为候选集。空候选集 = 移除
        select_voucher 条目（该资源非自选券）——经 store.get_select_voucher_candidates
        与 apply_to_store 重建保持单一真相（GUI 编辑期间 store 未同步，此处只维护
        self._select_vouchers，apply_to_store 时以 store 重建为准，ISSUE-117/702）。
        """
        rid = self._resource_id_edit.text().strip()
        if not rid:
            return
        selected = []
        for i in range(self._voucher_cards_list.count()):
            item = self._voucher_cards_list.item(i)
            if item.isSelected():
                cid = item.data(Qt.ItemDataRole.UserRole)
                if cid:
                    selected.append(cid)
        # 更新或移除 self._select_vouchers 中该资源条目
        for sv in self._select_vouchers:
            if sv['voucher'] == rid:
                if selected:
                    sv['cards'] = selected
                else:
                    self._select_vouchers.remove(sv)
                break
        else:
            if selected:
                self._select_vouchers.append({'voucher': rid, 'cards': selected})
        self._update_preview()

    def _setup_resource_tab(self, parent):
        """「资源获取」Tab——资源获取规则 / 指定日期资源获取 / 日历预览。

        P78（方案 X）：资源定义已拆为独立「资源定义」Tab（_setup_resource_def_tab）——
        本 Tab 仅保留资源获取规则、指定日期资源获取、日历预览三块。
        """
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

        self.resource_gain_rules = []
        self.resource_day_overrides = []

        # Phase 3: 日历预览缓存
        self._cached_schedule = None
        self._cached_schedule_key = None
        self._cached_start_date = None  # 用于清除旧高亮

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

        # ── 从池子分布收集卡片（P61 Ph8：读 banner 视图）──
        pool_cards: dict[str, dict] = {}  # card_id → {rarity, pools}
        for full_key, d in self._iter_pool_rewards():
            cid = d.get('card_id', '')
            if not cid or cid == '_no_card':
                continue
            if cid not in pool_cards:
                pool_cards[cid] = {
                    'rarity': d.get('rarity', 'R'),
                    'pools': [full_key],
                }
            else:
                if full_key not in pool_cards[cid]['pools']:
                    pool_cards[cid]['pools'].append(full_key)

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
        """从池子分布实时推导每张卡的池子归属（P61 Ph8：读 banner 视图）。"""
        result = {}
        for full_key, d in self._iter_pool_rewards():
            cid = d.get('card_id', '')
            if cid and cid != '_no_card':
                result.setdefault(cid, []).append(full_key)
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
        for full_key, d in self._iter_pool_rewards():
            cid = d.get('card_id', '')
            if cid and cid not in card_pools_map:
                card_pools_map[cid] = [full_key]
            elif cid and full_key not in card_pools_map[cid]:
                card_pools_map[cid].append(full_key)
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
        for full_key, d in self._iter_pool_rewards():
            cid = d.get('card_id', '')
            if cid and cid not in card_pools_map:
                card_pools_map[cid] = [full_key]
            elif cid and full_key not in card_pools_map[cid]:
                card_pools_map[cid].append(full_key)
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
            max_day = max((p.start_day + (p.end_day - p.start_day if p.end_day is not None else 0))
                          for p in pools_list)
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

        # P58（§3.8.4）：累抽奖励摘要段
        ml_cfg = config.get('milestone', {})
        if ml_cfg.get('enabled', True) and ml_cfg.get('milestones'):
            lines = []
            for md in ml_cfg['milestones']:
                mode = f"every={md['threshold']}" if md.get('repeat') else f"at={md['threshold']}"
                # P78（ISSUE-101）：交替里程碑——交替项优先，offset 首节点用用户心智模型表述
                alt = md.get('alternate_rewards', [])
                if alt:
                    parts = []
                    # 交替项奖励类型统计（items 可能是 cards/resources/random_cards 组合）
                    card_n = sum(len(a.get('cards', [])) for a in alt)
                    res_n = sum(len(a.get('resources', {})) for a in alt)
                    rnd_n = sum(len(a.get('random_cards', [])) for a in alt)
                    if card_n:
                        parts.append(f"{card_n}张固定卡")
                    if res_n:
                        parts.append(f"{res_n}项资源")
                    if rnd_n:
                        parts.append(f"{rnd_n}个随机池")
                    offset = md.get('offset', 0)
                    threshold = md.get('threshold', 0)
                    first = threshold + offset
                    if md.get('repeat'):
                        lines.append(f"  {md['name']}: {len(alt)}项交替 → {', '.join(parts) or '无奖励'} · 首次触发 {first} · 每 {threshold} 抽循环")
                    else:
                        lines.append(f"  {md['name']}: at={first} → {', '.join(parts) or '无奖励'}（交替仅首项生效）")
                    continue
                br = md.get('bonus_reward', {})
                parts = []
                if br.get('cards'):
                    parts.append(f"{len(br['cards'])}张固定卡")
                if br.get('resources'):
                    parts.append(f"{len(br['resources'])}项资源")
                if br.get('random_cards'):
                    parts.append(f"{len(br['random_cards'])}个随机池")
                lines.append(f"  {md['name']}: {mode} → {', '.join(parts) or '无奖励'}")
            preview += "\n累抽奖励:\n" + '\n'.join(lines)

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
                    (p.start_day + (p.end_day - p.start_day if p.end_day is not None else 0))
                    for p in pools_list
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

    def _register_resources_from_pools(self):
        """从 Banner 视图注册资源（§3.10.7 正向同步）：Pool cost + rewards resources_gained。

        P61 Ph8 改写：原遍历 pool_table 行（pools 参数），现遍历 _banner_defs
        （banner → pools[*]）自动补全「资源获取」Tab 的资源定义。
        P77（ISSUE-205）：追加扫描资源生命周期的转换目标（convert_to）——该目标可能
        仅通过转换获得（不出现于任何池成本或奖励），未登记则转换目标下拉缺选项。
        """
        for b in self._banner_defs:
            for p in b.get('pools', []):
                cost_text = str(p.get('cost', 'draw_resource:160'))
                for part in cost_text.split('&'):
                    part = part.strip()
                    if ':' in part:
                        self._ensure_resource_registered(part.split(':')[0].strip())
                for r in p.get('rewards', []) or []:
                    rg = r.get('resources_gained', {}) or {}
                    for rid in rg:
                        self._ensure_resource_registered(rid)
        # P77：资源生命周期转换目标登记（详情 dict 携带 on_expire）
        for d in getattr(self, 'resource_defs', []) or []:
            on_expire = d.get('on_expire') or {}
            tgt = on_expire.get('convert_to')
            if tgt:
                self._ensure_resource_registered(tgt)

    def _ensure_resource_registered(self, resource_id, display_name=''):
        if not resource_id:
            return
        existing = self._get_resource_ids()
        if resource_id in existing:
            return
        self.resource_defs.append({
            'resource_id': resource_id,
            'display_name': display_name or resource_id,
            'initial_amount': 0,
        })
        self._rebuild_resource_list()
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
                'type': derive_pool_type_from_distribution(p.distribution),
                'start_day': p.start_day,
                'duration': (p.end_day - p.start_day) if p.end_day is not None else 0,
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
            # P61（Ph8c）：追加完整 Banner 结构（秒），供预览面板合成 Banner 摘要（§3.10.7）。
            # pools 展平视图保留供旧消费方（预览/导出摘要）兼容。
            'banner': [{
                'id': b.id,
                'name': b.name,
                'enabled': b.enabled,
                'max_draws': b.max_draws,
                'available_from': b.available_from,
                'available_until': b.available_until,
                # P77：归一前永久池标记随 config 透传，否则往返后永久池混入
                # 「对齐卡池」下拉（set_config 重建 BannerEntry 时标记丢失）
                'is_permanent': getattr(b, '_is_permanent', False),
                'pools': [{
                    'id': p.id, 'cost': p.cost, 'batch_size': p.batch_size,
                    'excludes_all_pity': p.excludes_all_pity, 'max_draws': p.max_draws,
                    'exchange_card_id': p.exchange_card_id,
                    'epitomizable_cards': list(p.epitomizable_cards),
                    'rewards': [dict(r) for r in p.rewards],
                } for p in b.pools],
                'lifecycle': [{
                    'condition': lc.condition, 'pool': lc.pool, 'at': lc.at,
                    'match': lc.match, 'action': lc.action, 'target': lc.target,
                } for lc in b.lifecycle],
            } for b in store.banner.banners],
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
            # P58（§3.8.5a，REVIEW-FIX-PREV: ISSUE-003）：追加里程碑键——供 _do_update_preview 累抽摘要段读取
            'milestone': {
                'enabled': store.milestone.enabled,
                'milestones': [self._milestone_to_dict(m) for m in store.milestone.milestones],
            },
            # P78（ISSUE-703 契约）：select_vouchers 键名 + 条目格式与 TOML [[select_voucher]] 段同构
            'select_vouchers': [
                {'voucher': sv.voucher, 'cards': list(sv.cards)}
                for sv in store.select_vouchers
            ],
            # P77：resource_lifecycle 顶层键（与 Store 字段同名；TOML 层落点为嵌套
            # data['resources']['lifecycle']，两层由 config_toml/config_panel 显式适配）
            'resource_lifecycle': {
                'enabled': store.resource_lifecycle.enabled,
                'rules': [self._lifecycle_rule_to_config(r)
                          for r in store.resource_lifecycle.rules],
            },
        }

    def _lifecycle_rule_to_config(self, rule) -> dict:
        """ResourceLifecycle → config dict（expire_at 以天书写，与 TOML 段同构）。"""
        entry = {'resource_id': rule.resource_id}
        if rule.expire_at is not None:
            entry['expire_at'] = float(rule.expire_at) / DAY
        elif rule.expire_with_banner:
            entry['expire_with_banner'] = rule.expire_with_banner
        entry['on_expire'] = dict(rule.on_expire) if rule.on_expire else {}
        return entry

    def _lifecycle_config_from_dict(self, cfg: dict):
        """config dict 转 ResourceLifecycleConfig（复用解析期校验，两入口同强度）。

        与 config_toml.validate_resource_lifecycle_rules 共用实现：非法条目抛
        ConfigError 而非静默跳过（同 P78 的 _validate_milestone_dict 纪律）。
        上下文（资源 id 集合 / banner 映射 / 永久池标记）取自 self._store。
        """
        from ..core.config_toml import validate_resource_lifecycle_rules

        store = self._store
        resource_ids = set(store.resource_defs.keys()) if store is not None else set()
        banners = list(store.banner.banners) if store is not None else []
        raw_rules = cfg.get('rules', [])
        return validate_resource_lifecycle_rules(
            raw_rules if isinstance(raw_rules, list) else [],
            resource_ids,
            {b.id: b.available_until for b in banners},
            {b.id for b in banners if getattr(b, '_is_permanent', False)},
            bool(cfg.get('enabled', True)),
        )

    def _milestone_to_dict(self, m) -> dict:
        """MilestoneDef → config dict（P78 ISSUE-121：条件省略键）。

        与 save_toml 写盘侧同规则——无交替/零偏移里程碑省略 alternate_rewards/offset 键
        （set_config 恢复过 _validate_milestone_dict 时无法区分「用户显式空」与「程序默认空」，
        省略键走默认值路径不抛 ConfigError；含交替/非零偏移里程碑键存在、round-trip 存活）。
        """
        entry = {'name': m.name, 'threshold': m.threshold, 'repeat': m.repeat,
                 'max_triggers': m.max_triggers, 'banner': m.banner, 'bonus_reward': m.bonus_reward}
        if m.alternate_rewards:
            entry['alternate_rewards'] = m.alternate_rewards
        if m.offset:
            entry['offset'] = m.offset
        return entry

    def _get_sim_params(self):
        if self._store is not None:
            return self._store.simulation_count, self._store.max_workers, self._store.seed
        return 1000, 4, 42

    def set_config(self, config):
        if self._store is None:
            return

        store = self._store
        store.clear()

        # P61（Ph8c）：优先从 config['banner']（完整 Banner 结构，秒）加载；
        # 旧 config['pools'] 展平视图（一池一 banner）回退保留。
        banners = []
        banner_cfg = config.get('banner')
        if banner_cfg:
            for b in banner_cfg:
                pools = []
                for p in b.get('pools', []):
                    pools.append(BannerPoolEntry(
                        id=p.get('id', 'main'),
                        cost=p.get('cost', 'draw_resource:160'),
                        batch_size=p.get('batch_size', 1),
                        excludes_all_pity=p.get('excludes_all_pity', False),
                        max_draws=p.get('max_draws'),
                        exchange_card_id=p.get('exchange_card_id'),
                        epitomizable_cards=p.get('epitomizable_cards', []) or [],
                        rewards=[dict(r) for r in p.get('rewards', []) or []],
                    ))
                lifecycle = []
                for lc in b.get('lifecycle', []) or []:
                    condition = lc.get('condition', 'pool_draws')
                    at = lc.get('at', 0)
                    # P61 Ph8c：get_config 输出的 banner.at 已是秒（apply_to_store 后
                    # store.banner 的 lc.at 为秒）——透传，不再 * DAY（避免 86400 倍二次换算）。
                    lifecycle.append(LifecycleRuleEntry(
                        condition=condition,
                        pool=lc.get('pool'),
                        at=float(at),
                        match=lc.get('match', 'card_id'),
                        action=lc.get('action', 'switch_to'),
                        target=lc.get('target'),
                    ))
                banners.append(BannerEntry(
                    id=b.get('id', ''),
                    name=b.get('name', ''),
                    enabled=b.get('enabled', True),
                    max_draws=b.get('max_draws'),
                    available_from=b.get('available_from'),
                    available_until=b.get('available_until'),
                    pools=pools,
                    lifecycle=lifecycle,
                    # P77：永久池标记随 config 恢复（否则往返后永久池混入到期对齐下拉）
                    _is_permanent=bool(b.get('is_permanent', False)),
                ))
        else:
            pools_data = config.get('pools', [])
            for p in pools_data:
                # 旧格式：get_config 输出的 pools id 为全限定展平键，拆出 banner 段。
                pid_raw = p.get('id', '')
                pid = pid_raw.rsplit('.', 1)[0] if '.' in pid_raw else pid_raw
                dist_data = p.get('distribution')
                rewards = []
                if dist_data:
                    for d in dist_data:
                        rewards.append({
                            'card_id': d.get('card_id', ''),
                            'probability': d.get('probability', 0),
                            'rarity': d.get('rarity', 'R'),
                            'featured': d.get('featured', False),
                            **({'resources_gained': d.get('resources_gained', {})}
                               if d.get('resources_gained') else {}),
                        })
                banners.append(BannerEntry(
                    enabled=p.get('enabled', True),
                    id=pid,
                    name=p.get('name', ''),
                    available_from=p.get('start_day', 0) * DAY,
                    available_until=(p.get('start_day', 0) + p.get('duration', 21)) * DAY,
                    pools=[BannerPoolEntry(
                        id='main',
                        cost=p.get('cost', 'draw_resource:160'),
                        batch_size=p.get('batch_size', 1),
                        epitomizable_cards=p.get('epitomizable_cards', []),
                        rewards=rewards,
                    )],
                ))
        store.banner.banners = banners
        # P61（2026-08-04 用户决策）：GUI 编辑路径同样归一永久 Banner（无 None）
        from ..core.config_toml import _normalize_permanent_banners
        _normalize_permanent_banners(store.banner.banners)

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

        # ── P78（ISSUE-202/102/114/116/602）：里程碑 + 自选券恢复块 ──
        # 置于 store.card_defs 填充（L5085-5095）之后、refresh_from_store（L5139）之前——
        # 两校验器 _validate_milestone_dict/_validate_select_voucher_dict 均需 known_card_ids
        # （从刚填充的 card_defs 派生），card_defs 为空时合法候选卡全被误拒。
        from ..core.config_toml import (
            _validate_milestone_dict,
            _validate_select_voucher_dict,
        )
        from ..core.config_store import ConfigError
        known_card_ids = {c.card_id for c in store.card_defs}
        # milestone 恢复（ISSUE-102：get_config→set_config round-trip 里程碑整段存活）
        ml_cfg = config.get('milestone', {})
        store.milestone.enabled = ml_cfg.get('enabled', True)
        # ISSUE-606：set_config 入口与 _build_milestone 同构——列表级 name 去重（TOML 路径
        # 有 seen_names ConfigError；set_config 注入重复 name 静默通过会致引擎后覆盖前，
        # 「两入口校验强度一致」对 name 去重不成立）
        _seen_ml_names: set = set()
        for md_dict in ml_cfg.get('milestones', []) or []:
            # 与 _build_milestone 同构：去重用 strip 后 name（原始含空格 name 在不同字符串
            # 下不判重复，strip 后 'dup' 与 ' dup ' 均为 'dup'——两入口完全同构）
            _name = md_dict.get('name', '').strip() if isinstance(md_dict, dict) else ''
            if _name in _seen_ml_names:
                raise ConfigError(f"里程碑名称重复: '{_name}'")
            if _name:
                _seen_ml_names.add(_name)
            store.milestone.milestones.append(
                _validate_milestone_dict(md_dict, known_card_ids))
        # select_vouchers 恢复（ISSUE-102/116/602：同构校验 + resource_defs 补全）
        sv_list = config.get('select_vouchers') or []
        if sv_list:
            store.select_vouchers = _validate_select_voucher_dict(sv_list, known_card_ids)
            # ISSUE-602：恢复 select_vouchers 时同步补全 resource_defs（setdefault——既有显示名保留）
            for item in sv_list:
                store.resource_defs.setdefault(item.get('voucher', ''), item.get('voucher', ''))

        # P77：resource_lifecycle 恢复（新键优先，兼容一次性旧 lifecycle 键；天 → 秒换算）
        lc_cfg = config.get('resource_lifecycle', config.get('lifecycle'))
        if isinstance(lc_cfg, dict):
            store.resource_lifecycle = self._lifecycle_config_from_dict(lc_cfg)

        # P60：统一填充 featured_card_ids
        for pool in store.pools:
            pool.featured_card_ids = [d.card_id for d in pool.distribution if d.featured]

        self.refresh_from_store()

    def _sync_card_defs_from_pools(self):
        """池 rewards → 「卡牌定义」Tab pools 字段正向同步（§3.10.7 / ISSUE-016）。

        P61 Ph8 改写：原遍历 pool_table 行，现遍历 _banner_defs（banner → pools[*]），
        pools 键用全限定 {banner_id}.{pool_id}（与 Ph3 展平视图 card_defs[].pools
        同口径，ISSUE-310）。新 UI 下每个 Pool 必带 rewards（内联），不再有
        「无分布 → 默认 _ssr/_sr/_r」分支。
        """
        existing_defs = self.get_card_defs()
        existing_map = {d['card_id']: d for d in existing_defs}

        for full_key, d in self._iter_pool_rewards():
            cid = d.get('card_id', '')
            if not cid:
                continue
            if cid in existing_map:
                pools = existing_map[cid].get('pools', [])
                if full_key not in pools:
                    pools.append(full_key)
                existing_map[cid]['pools'] = pools
            else:
                base = {'tags': {}, 'list_tags': {}, 'initial_count': 0}
                if cid == '_no_card':
                    existing_map[cid] = {
                        'card_id': '_no_card',
                        'name': '空抽(仅资源)',
                        'rarity': '无',
                        'pools': [full_key],
                        **base,
                    }
                else:
                    existing_map[cid] = {
                        'card_id': cid,
                        'name': cid,
                        'rarity': d.get('rarity', 'R'),
                        'pools': [full_key],
                        **base,
                    }

        merged = list(existing_map.values())
        self.set_card_defs(merged)

    # _filter_card_defs / _search_card_defs / _on_card_def_changed 已由
    # P65 的 _filter_card_list 替代——见 _setup_card_def_tab 区域

    def _on_resource_def_changed(self, *_args):
        self._flush_resource_detail()
        self._refresh_resource_combos()
        self._update_preview()

    def _get_resource_ids(self):
        return [d.get('resource_id', '') for d in self.resource_defs if d.get('resource_id', '').strip()]

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
        # P78 ISSUE-122：ml_resources_table（里程碑赠送资源）第 0 列同样是资源下拉——
        # 资源定义增删后刷新既有行选项（可编辑 combo，保留当前文本）
        for i in range(self.ml_resources_table.rowCount()):
            widget = self.ml_resources_table.cellWidget(i, 0)
            if isinstance(widget, QComboBox):
                current = widget.currentText()
                widget.blockSignals(True)
                widget.clear()
                widget.addItems(resource_ids)
                idx = widget.findText(current)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
                else:
                    # 可编辑 combo——当前值不在新列表中时保留手输文本
                    widget.setEditText(current)
                widget.blockSignals(False)

    def get_resource_defs(self):
        return [dict(d) for d in self.resource_defs]

    def set_resource_defs(self, defs):
        self.resource_defs = [dict(d) for d in defs]
        self._rebuild_resource_list()
        self._refresh_resource_combos()

    def _rebuild_resource_list(self):
        """重建左列表——清空后逐条追加 resource_id (display_name)。"""
        self._resource_list.blockSignals(True)
        self._resource_list.clear()
        for d in self.resource_defs:
            rid = d.get('resource_id', '')
            name = d.get('display_name', '')
            label = f"{rid} ({name})" if name else rid
            self._resource_list.addItem(label)
        self._resource_list.blockSignals(False)
        # P77：资源增删后刷新生命周期「转换目标」下拉（数据源为资源 id 集合）
        self._refresh_lifecycle_combos()
        self._current_resource_idx = -1
        self._resource_detail_group.setEnabled(False)

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
        """从全配置汇总缺失资源，只补不覆盖（替代原硬编码覆盖式）。

        两个用途兼容：
          ① 兜底（_set_defaults / 空 store 加载）——全空时给 2 个默认资源（ISSUE-124）
          ② 按钮点击——扫描卡池 cost/rewards + 里程碑奖励 + 自选券 voucher id，
             只补不覆盖，堵死原「点击覆盖成 2 个固定款」误操作陷阱。

        兜底后不 return：加默认后继续扫描（缺陷 B）——空 resource_defs 时也能补全
        milestone/select_voucher 引入的其它资源，完全吻合「汇总扫描」目标。
        """
        # 兜底：全空时也给两个默认（保持 ISSUE-124 文档验收项），但不 return——
        # 加默认后继续扫描，让「汇总扫描」真正覆盖所有配置源。
        if not self.resource_defs:
            defs = [
                {'resource_id': 'draw_resource', 'display_name': '抽卡资源', 'initial_amount': 0},
                {'resource_id': 'exchange_currency', 'display_name': '兑换货币', 'initial_amount': 0},
            ]
            self.set_resource_defs(defs)

        # 汇总扫描：卡池 cost/rewards（复用 _register_resources_from_pools）
        # 守卫用 getattr——若 _banner_defs 从未初始化，直接访问会抛 AttributeError。
        if getattr(self, '_banner_defs', []):
            self._register_resources_from_pools()
        # 里程碑奖励（bonus_reward + alternate_rewards 同构）
        for md in getattr(self, '_milestone_defs', []):
            for rid in md.get('bonus_reward', {}).get('resources', {}):
                self._ensure_resource_registered(rid)
            for alt in md.get('alternate_rewards', []) or []:
                if isinstance(alt, dict):
                    for rid in alt.get('resources', {}):
                        self._ensure_resource_registered(rid)
        # 自选券 voucher id
        for sv in getattr(self, '_select_vouchers', []):
            self._ensure_resource_registered(sv.get('voucher', ''))

    def _add_resource_def(self):
        self.resource_defs.append({'resource_id': '', 'display_name': '', 'initial_amount': 0})
        self._rebuild_resource_list()
        # 选中新行并聚焦详情编辑
        row = len(self.resource_defs) - 1
        self._resource_list.setCurrentRow(row)

    def _remove_resource_def(self):
        row = self._resource_list.currentRow()
        if row < 0 or row >= len(self.resource_defs):
            return
        # P78 ISSUE-123：先弹确认、确认后才删——取消=整体回滚（资源行与 select_voucher 条目均保留）
        rid = self.resource_defs[row].get('resource_id', '')
        msg = f"确定删除资源「{rid}」？" if rid else "确定删除该资源？"
        if rid:
            msg += "\n该资源的自选券候选集条目将一并移除。"
        ret = QMessageBox.question(self, "删除资源", msg,
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                   QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes:
            return
        del self.resource_defs[row]
        # P78（ISSUE-117）：级联删除该资源的 select_voucher 条目（GUI 内部列表——
        # apply_to_store 重建时再以 store.resource_defs 为准过滤，ISSUE-702 静默级联）
        self._select_vouchers = [sv for sv in self._select_vouchers if sv['voucher'] != rid]
        self._rebuild_resource_list()
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

    def validate_banners(self) -> List[str]:
        """§3.10.2 保存校验：Banner id 全局唯一 / Pool id 唯一 / Pool cost 必填 / 非全永久。

        返回错误列表（空 = 通过）。由保存入口（main_window.export_config）与模拟启动
        （gacha_panel.start_simulation）在 apply_to_store 前调用——校验失败时拦截并提示。
        """
        errors: List[str] = []
        seen_banner_ids = set()
        has_finite_end = False
        for b in self._banner_defs:
            bid = b.get('id', '')
            if not bid:
                errors.append("存在空 Banner id")
            elif bid in seen_banner_ids:
                errors.append(f"Banner id 重复: {bid}")
            seen_banner_ids.add(bid)
            if b.get('available_until') is not None:
                has_finite_end = True
            seen_pool_ids = set()
            for p in b.get('pools', []):
                pid = p.get('id', '')
                if not pid:
                    errors.append(f"Banner「{bid or '?'}」存在空 Pool id")
                elif pid in seen_pool_ids:
                    errors.append(f"Banner「{bid}」Pool id 重复: {pid}")
                seen_pool_ids.add(pid)
                cost = str(p.get('cost', '')).strip()
                if not cost:
                    errors.append(f"Banner「{bid}」Pool「{pid or '?'}」缺少成本(cost)")
        # 全永久组合（2026-08-04 用户决策：禁止）——apply_to_store 归一时会抛
        # ConfigError，此处提前拦截给出明确提示（复审查发现）
        if self._banner_defs and not has_finite_end:
            errors.append("所有 Banner 均为永久（无结束时间），至少需要一个有结束时间的 Banner")

        # P79：停止条件引用完整性。调用 core 层纯函数（与 WebUI 的 _validate_store
        # 同源，不得各自复刻）；返回体仍是 List[str]，且对裸构造（无条件树内存态）
        # 安全——getattr 给出缺省。新增该类目会一并阻断「开始模拟」与「重启并保存」
        # 两条路径，这是期望行为（带非法表达式不应能启动模拟）。
        from ..core.stop_condition_expr import validate_stop_condition_config
        errors.extend(validate_stop_condition_config(
            expr=getattr(self, '_stop_condition_expr', '') or '',
            conditions=getattr(self, '_stop_condition_conditions', None) or [],
        ))
        return errors

    def apply_to_store(self):
        if self._store is None or self._refreshing:
            return
        from gacha_simulator.core.strategy import strategy_type_to_key
        store = self._store

        # P61（Ph8）：写入侧遍历 _banner_defs → store.banner.banners。
        # BannerEntry 全字段（id/name/enabled/max_draws/available_from/until/pools/lifecycle）；
        # 时间窗口经 *DAY 换算为秒（ISSUE-001，UI/存储层为天）；max_draws 0→None 归一化
        # （ISSUE-331）；card_obtained 的匹配值存 pool 字段（引擎语义，banner.py:29）。
        banners = []
        for b in self._banner_defs:
            pools = []
            for p in b.get('pools', []):
                batch_size = int(p.get('batch_size', 1) or 1)
                md = p.get('max_draws')
                pools.append(BannerPoolEntry(
                    id=p.get('id', ''),
                    cost=str(p.get('cost', 'draw_resource:160')),
                    batch_size=batch_size,
                    excludes_all_pity=bool(p.get('excludes_all_pity', False)),
                    max_draws=None if md is None else int(md),
                    exchange_card_id=p.get('exchange_card_id'),
                    epitomizable_cards=list(p.get('epitomizable_cards', []) or []),
                    rewards=[{
                        'card_id': r.get('card_id', ''),
                        'probability': float(r.get('probability', 0)),
                        'rarity': r.get('rarity', 'R'),
                        'featured': bool(r.get('featured', False)),
                        **({'resources_gained': r.get('resources_gained', {})}
                           if r.get('resources_gained') else {}),
                    } for r in p.get('rewards', []) or []],
                ))
            lifecycle = []
            for lc in b.get('lifecycle', []) or []:
                condition = lc.get('condition', 'pool_draws')
                at = lc.get('at', 0.0)
                lifecycle.append(LifecycleRuleEntry(
                    condition=condition,
                    pool=lc.get('pool') or None,
                    at=float(at) * DAY if condition == 'time_window' else float(at),
                    match=lc.get('match', 'card_id'),
                    action=lc.get('action', 'switch_to'),
                    target=lc.get('target') or None,
                ))
            b_from = b.get('available_from')
            b_until = b.get('available_until')
            b_md = b.get('max_draws')
            banners.append(BannerEntry(
                id=b.get('id', ''),
                name=b.get('name', ''),
                enabled=bool(b.get('enabled', True)),
                max_draws=None if not b_md else int(b_md),
                available_from=float(b_from) * DAY if b_from is not None else None,
                available_until=float(b_until) * DAY if b_until is not None else None,
                pools=pools,
                lifecycle=lifecycle,
            ))

        store.banner.banners = banners
        # P61（2026-08-04 用户决策）：GUI 编辑写回同样归一永久 Banner（无 None）
        from ..core.config_toml import _normalize_permanent_banners
        _normalize_permanent_banners(store.banner.banners)

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
        store.auto_wait = self.auto_wait.isChecked()

        # P79：停止条件条件树全量重建（5.7「条件树存放位置」）。面板持内存态、
        # apply_to_store 从内存态重建；重建幂等，反复写回不会清空条件树——
        # 本方法被 get_config() 无条件调用，而 get_config 又被 500ms 去抖预览
        # 与 main_window 导出高频触发，非幂等会直接毁掉用户正在编辑的条件。
        store.stop_condition = self._build_stop_condition_tree()

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

        # ── P58：累抽奖励 milestone 写回（§3.8.5a）──
        store.milestone.enabled = self.milestone_enabled.isChecked()
        store.milestone.milestones = []
        for md in self._milestone_defs:
            # REVIEW-R1-FIX: ISSUE-104 —— 保存前校验资源 ID 合法性：未在 resource_defs 定义的给出一次性警告
            #   （不阻塞保存——幽灵资源键由用户修正）
            # REVIEW-R1-FIX: ISSUE-311 —— 警告不得挂在高频路径：apply_to_store 被 get_config() 无条件调用，
            #   而 get_config 又被 500ms 去抖 _update_preview → _do_update_preview 触发，任何 Tab 任意 UI 交互
            #   都会经过本循环。改为一次性语义：同一 rid 仅首次提示（加入集合），后续预览/模拟启动链路静默。
            for rid in md.get('bonus_reward', {}).get('resources', {}):
                if rid and rid not in store.resource_defs and rid not in self._warned_milestone_resource_ids:
                    self._warned_milestone_resource_ids.add(rid)
                    QMessageBox.warning(self, "未定义资源",
                                        f"资源 ID '{rid}' 未在资源获取 Tab 定义，模拟时可能无法识别")
            # P78（ISSUE-005/109）：交替奖励项内资源同样纳入一次性警告（与 bonus_reward 同构）
            for alt_item in md.get('alternate_rewards', []) or []:
                if not isinstance(alt_item, dict):
                    continue
                for rid in alt_item.get('resources', {}):
                    if rid and rid not in store.resource_defs and rid not in self._warned_milestone_resource_ids:
                        self._warned_milestone_resource_ids.add(rid)
                        QMessageBox.warning(self, "未定义资源",
                                            f"资源 ID '{rid}' 未在资源获取 Tab 定义，模拟时可能无法识别")
            # REVIEW-R1-FIX: ISSUE-305 —— 写出前过滤空候选随机池（_build_milestone 对空 candidates 抛 ConfigError）
            # REVIEW-R1-FIX: ISSUE-304 —— 过滤条件扩展为「candidates 为空 或 weights 全零」
            #   （UI 允许权重全 0，直接保存会触发 _build_milestone 全零权重校验抛 ConfigError）
            _br = dict(md.get('bonus_reward', {'cards': [], 'resources': {}, 'random_cards': []}))
            _br['random_cards'] = [
                rc for rc in _br.get('random_cards', [])
                if rc.get('candidates') and not (rc.get('weights') and all(float(w) == 0.0 for w in rc.get('weights')))
            ]
            store.milestone.milestones.append(MilestoneDef(
                name=md.get('name', ''),
                threshold=md.get('threshold', 40),
                repeat=md.get('repeat', False),
                max_triggers=md.get('max_triggers', 0),
                banner=md.get('banner', ''),
                bonus_reward=_br,
                # ── P78 透传（ISSUE-002/101 round-trip 纪律）──
                offset=md.get('offset', 0),
                alternate_rewards=self._filter_alternate_rewards(md.get('alternate_rewards', [])),
            ))

        # P78：select_vouchers 写回 + 级联删除孤儿条目（ISSUE-117/702）
        # 以重建后的 resource_defs 为准——不在其中的 voucher id 级联删除（静默、不弹框，
        # 防 500ms 去抖预览链弹框风暴；确认框唯一弹出点为 _remove_resource_def，ISSUE-702）
        store.select_vouchers = [
            SelectVoucherDef(voucher=sv['voucher'], cards=list(sv['cards']))
            for sv in self._select_vouchers
            if sv['voucher'] in store.resource_defs
        ]

        # P77：资源生命周期写回（扫描资源详情汇总；外键级联过滤见 _collect_lifecycle_rules）
        store.resource_lifecycle = ResourceLifecycleConfig(
            enabled=getattr(self, '_resource_lifecycle_enabled', True),
            rules=self._collect_lifecycle_rules(set(store.resource_defs.keys())),
        )

    def _collect_lifecycle_rules(self, valid_resource_ids):
        """扫描资源详情汇总生命周期规则；外键失效或自环的规则静默过滤。

        过滤强度与 select_vouchers 级联（ISSUE-702）一致：
        资源已删除或重命名、banner 不再可对齐（被删或为永久池）、转换目标
        不在当前资源集合内，均丢弃该条目而非写出悬垂引用。
        """
        self._flush_resource_detail()   # 当前编辑行可能未失焦，先落盘再扫描
        valid_banners = {b.get('id', '') for b in getattr(self, '_banner_defs', []) or []
                         if b.get('id') and not b.get('is_permanent')
                         and b.get('available_until') is not None}
        rules = []
        seen = set()
        for d in self.resource_defs:
            rule = self._lifecycle_rule_from_detail(d)
            if rule is None:
                continue
            rid = rule['resource_id']
            if rid not in valid_resource_ids or rid in seen:
                continue
            if 'expire_with_banner' in rule and rule['expire_with_banner'] not in valid_banners:
                continue
            on_expire = rule.get('on_expire') or {}
            target = on_expire.get('convert_to')
            if target is not None and (target not in valid_resource_ids or target == rid):
                continue    # 悬垂目标或自环（解析期亦拒绝自环）
            seen.add(rid)
            rules.append(ResourceLifecycle(
                resource_id=rid,
                expire_at=(rule['expire_at'] * DAY if 'expire_at' in rule else None),
                expire_with_banner=rule.get('expire_with_banner'),
                on_expire=dict(on_expire),
            ))
        return rules

    def _filter_alternate_rewards(self, alt_rewards):
        """P78 ISSUE-601：保存侧防线——过滤 alternate_rewards 空 dict 项与空 candidates/全零权重随机卡。

        与 bonus_reward 的 _filter_random_cards 同构（防两处过滤逻辑复制漂移）——
        空项丢弃、空 candidates/全零权重 random_cards 过滤。过滤后全空 → 调用方
        经条件写键自动省略 alternate_rewards 键（ISSUE-113）。
        """
        result = []
        for item in alt_rewards or []:
            if not item or not isinstance(item, dict):
                continue                     # 空 dict 项 / 非 dict → 丢弃（ISSUE-601）
            if not any(item.get(k) for k in ('cards', 'resources', 'random_cards')):
                continue                     # 无任何有效字段 → 丢弃
            rc = item.get('random_cards', [])
            if rc:
                item['random_cards'] = [
                    r for r in rc
                    if r.get('candidates') and not (r.get('weights') and all(float(w) == 0.0 for w in r.get('weights')))
                ]
            result.append(item)
        return result

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

        # P61（Ph8）：从 store.banner.banners 填充 _banner_defs（读侧 Banner 适配）。
        # 时间窗口秒 → 天（// DAY，ISSUE-001）；max_draws None → 0（UI 无限制语义）；
        # lifecycle at 秒 → 天（time_window）；card_obtained 匹配值取自 pool 字段。
        self._banner_defs = []
        for b in store.banner.banners:
            pools = []
            for p in b.pools:
                pools.append({
                    'id': p.id,
                    'cost': p.cost,
                    'batch_size': getattr(p, 'batch_size', 1),
                    'excludes_all_pity': getattr(p, 'excludes_all_pity', False),
                    'max_draws': getattr(p, 'max_draws', None),
                    'exchange_card_id': getattr(p, 'exchange_card_id', None),
                    'epitomizable_cards': list(getattr(p, 'epitomizable_cards', []) or []),
                    'rewards': [dict(r) for r in (p.rewards or [])],
                })
            lifecycle = []
            for lc in b.lifecycle or []:
                lifecycle.append({
                    'condition': lc.condition,
                    'pool': lc.pool,
                    'at': lc.at / DAY if lc.condition == 'time_window' else lc.at,
                    'match': getattr(lc, 'match', 'card_id'),
                    'action': lc.action,
                    'target': lc.target,
                })
            self._banner_defs.append({
                'id': b.id,
                'name': b.name,
                'enabled': getattr(b, 'enabled', True),
                'max_draws': getattr(b, 'max_draws', None),
                'available_from': b.available_from / DAY if b.available_from is not None else None,
                'available_until': b.available_until / DAY if b.available_until is not None else None,
                # P77：归一前永久池标记（供生命周期「对齐卡池」下拉过滤，与解析期校验同口径）
                'is_permanent': getattr(b, '_is_permanent', False),
                'pools': pools,
                'lifecycle': lifecycle,
            })
        self._refresh_banner_list(0 if self._banner_defs else -1)
        self._register_resources_from_pools()

        self.pity_enabled.setChecked(store.pity.enabled)
        self._pity_defs = []
        for p in store.pity.pities:
            # P55：扁平化字段
            pools_val = getattr(p, 'pools', ('*',))
            # P61 Ph8b（ISSUE-328）：保留 tuple 原形——多 pattern（如 ('b1.main','b2.main')）
            # 逗号拼接成字符串后勾选表格对单 pattern fnmatch 恒失配、绑定静默清空。
            # 绑定勾选表格直接消费 tuple（逐 pattern fnmatch）。
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

        display_name = _sr[store.strategy_key].display_name if store.strategy_key in _sr else '按需追卡'
        strategy_idx = self._strategy_display_names.index(display_name) if display_name in self._strategy_display_names else 0
        self.strategy_type.setCurrentIndex(strategy_idx)
        self._set_strategy_params_to_widgets(store.strategy_params)
        self._load_stop_condition_from_store(store)
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

        # ---- 里程碑（P58，§3.8.5a）----
        # REVIEW-R1-FIX: ISSUE-003 —— 回填挂载到 _refresh_from_store_impl（实际加载路径）而非 set_config
        self._milestone_defs = []
        self.milestone_list.clear()
        self._current_milestone_row = -1   # REVIEW-R1-FIX: ISSUE-001 —— 回填不选中任何行，重置行追踪
        # 代码审查 F4（2026-08-05）：跨配置加载清空随机池状态——防同名里程碑经 setdefault 继承上一配置陈旧随机池
        self._milestone_random_pools = {}
        self._selected_random_pool_idx = 0
        self.milestone_enabled.setChecked(store.milestone.enabled)
        for md in store.milestone.milestones:
            self._milestone_defs.append({
                'name': md.name,
                'threshold': md.threshold,
                'repeat': md.repeat,
                'max_triggers': md.max_triggers,
                'banner': md.banner,
                'bonus_reward': {
                    'cards': list(md.bonus_reward.get('cards', [])),
                    'resources': dict(md.bonus_reward.get('resources', {})),
                    'random_cards': list(md.bonus_reward.get('random_cards', [])),
                },
                # P78：回填复制新字段（ISSUE-002/101 round-trip 纪律——_flush 原地改写保留未知键，
                # load/save 两处补键；否则 apply_to_store 时 get('offset',0) 恒 0、交替恒空）
                'offset': md.offset,
                'alternate_rewards': [dict(a) for a in md.alternate_rewards],
            })
            self.milestone_list.addItem(md.name)
        # P78：select_vouchers 回填（ISSUE-004 数据流挂接）——复制到 GUI 内部列表，
        # 详情面板按资源 id 关联编辑候选集（5b 挂接）
        self._select_vouchers = [
            {'voucher': sv.voucher, 'cards': list(sv.cards)}
            for sv in store.select_vouchers
        ]
        # P77：资源生命周期回填——全局开关 + 按 resource_id 索引写回各资源详情 dict
        self._resource_lifecycle_enabled = store.resource_lifecycle.enabled
        if hasattr(self, '_lifecycle_enabled_cb'):
            self._lifecycle_enabled_cb.blockSignals(True)
            self._lifecycle_enabled_cb.setChecked(self._resource_lifecycle_enabled)
            self._lifecycle_enabled_cb.blockSignals(False)
        _lc_by_res = {r.resource_id: r for r in store.resource_lifecycle.rules}
        for _d in self.resource_defs:
            _rule = _lc_by_res.get(_d.get('resource_id', ''))
            if _rule is None:
                _d['expire_mode'] = 'none'
                _d['expire_banner'] = ''
                _d['expire_at'] = None
                _d['on_expire'] = None
                continue
            if _rule.expire_with_banner:
                _d['expire_mode'] = 'banner'
                _d['expire_banner'] = _rule.expire_with_banner
                _d['expire_at'] = None
            else:
                _d['expire_mode'] = 'at'
                _d['expire_banner'] = ''
                _d['expire_at'] = ((_rule.expire_at / DAY)
                                   if _rule.expire_at is not None else 0.0)
            _d['on_expire'] = dict(_rule.on_expire) if _rule.on_expire else None
        self._refresh_lifecycle_combos()
        # REVIEW-R1-FIX: ISSUE-010 —— _populate_milestone_cards_list 调用时机：store 就绪后立即填充
        #   固定卡多选区域（否则 ml_cards_list 恒空，bonus_reward.cards 固定卡多选无法 GUI 编辑）
        self._populate_milestone_cards_list()

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
