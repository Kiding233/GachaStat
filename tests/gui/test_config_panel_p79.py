"""P79 GUI 用例：配置面板「停止条件」子标签页。

按计划 8.5 的落点，本文件承载：
- 4c1a：子标签页外壳、祖先链含 QAbstractScrollArea（wheel_blocker 转发前提）、
  顶部只读提示读 store.end_time
- 5c2b：8.1 断言 6（同轴条件预填的控件读回值）
- 4d2b2：8.2「组合区同屏同步」
- 4d3：8.2「引用完整性」的 GUI 侧
"""

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

import pytest  # noqa: E402

CONFIG = 'gacha_simulator/config/config.toml'


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture
def panel(qapp):
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.gui.config_panel import ConfigPanel

    p = ConfigPanel()
    p.set_store(load_toml(CONFIG))
    yield p
    p.deleteLater()


def _tab_index(panel, title):
    return next(i for i in range(panel.left_tabs.count())
                if panel.left_tabs.tabText(i) == title)


def test_stop_condition_tab_exists(panel):
    idx = _tab_index(panel, '停止条件')
    assert panel.left_tabs.widget(idx) is not None


def test_stop_condition_tab_inside_scroll_area(panel):
    """祖先链须含 QAbstractScrollArea。

    gui/wheel_blocker.py 的全局事件过滤器在找不到该祖先时仍 return True，
    吞掉 QComboBox / QAbstractSpinBox 的滚轮而不转发——这是硬约束。
    """
    from PyQt6.QtWidgets import QAbstractScrollArea

    widget = panel.left_tabs.widget(_tab_index(panel, '停止条件'))
    node, found = widget, False
    while node is not None:
        if isinstance(node, QAbstractScrollArea):
            found = True
            break
        node = node.parentWidget()
    assert found, '停止条件子标签页不在 QScrollArea 内'


def test_hint_reads_store_end_time(panel):
    """顶部只读提示读 self._store.end_time（单一实现点），面板内不重算。"""
    from gacha_simulator.core.config_toml import load_toml

    store = load_toml(CONFIG)
    panel.set_store(store)
    text = panel.stop_condition_hint.text()
    assert f"{store.end_time / 86400:.1f}" in text
    assert '强制结束' in text


def test_hint_without_store_shows_placeholder(qapp):
    from gacha_simulator.gui.config_panel import ConfigPanel

    p = ConfigPanel()          # 未 set_store → _store 为 None
    assert '—' in p.stop_condition_hint.text()
    p.deleteLater()


# ── 4c1b：条件列表 ───────────────────────────────────────────────

def test_condition_table_columns_and_buttons(panel):
    from PyQt6.QtWidgets import QPushButton

    assert panel.stop_condition_table.columnCount() == 3
    labels = [panel.stop_condition_table.horizontalHeaderItem(i).text()
              for i in range(3)]
    assert labels == ['id', '类型', '摘要']
    texts = {b.text() for b in panel.findChildren(QPushButton)}
    assert {'添加', '移除选中', '上移', '下移'} <= texts


def test_type_combo_filters_internal(panel):
    """类型下拉须按 internal 标志过滤——consecutive_pool_target 不得暴露给用户。"""
    keys = [k for k, _ in panel._stop_condition_type_choices]
    assert 'consecutive_pool_target' not in keys
    assert 'all_pools_end' in keys and 'resource_threshold' in keys


def test_add_remove_move_conditions(panel):
    panel.stop_condition_type_combo.setCurrentIndex(0)
    panel._on_stop_condition_add()
    panel._on_stop_condition_add()

    conds = panel._stop_condition_conditions
    assert [c['id'] for c in conds] == ['a', 'b']
    assert panel.stop_condition_table.rowCount() == 2
    # 默认值来自注册表描述符
    assert 'type' in conds[0]

    # 摘要列取自条件对象的 description()
    summary = panel.stop_condition_table.item(0, 2).text()
    assert summary

    # 上移 / 下移
    panel.stop_condition_table.selectRow(1)
    panel._move_stop_condition(-1)
    assert [c['id'] for c in panel._stop_condition_conditions] == ['b', 'a']
    panel._move_stop_condition(1)
    assert [c['id'] for c in panel._stop_condition_conditions] == ['a', 'b']

    # 移除选中
    panel.stop_condition_table.selectRow(0)
    panel._on_stop_condition_remove()
    assert [c['id'] for c in panel._stop_condition_conditions] == ['b']
    assert panel.stop_condition_table.rowCount() == 1


def test_selection_syncs_selected_id(panel):
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'fixed_action_count', 'max_actions': 1},
         {'id': 'b', 'type': 'time_limit', 'max_time': 10.0}], 'a or b')
    assert panel._stop_condition_selected_id == 'a'
    panel.stop_condition_table.selectRow(1)
    assert panel._stop_condition_selected_id == 'b'
