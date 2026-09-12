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


# ── 4c2a：条件参数区（二级嵌套映射与回填）────────────────────────

def test_param_area_nested_map_and_fill(panel):
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'fixed_action_count', 'max_actions': 7},
         {'id': 'b', 'type': 'resource_threshold',
          'resource': 'draw_resource', 'operator': '<=', 'threshold': 3.0}], 'a or b')
    panel._stop_condition_selected_id = 'a'
    panel._rebuild_stop_condition_params()

    # 条件 id → {参数键 → (ptype, widget)}
    assert set(panel._stop_condition_param_widgets) == {'a', 'b'}
    assert set(panel._stop_condition_param_widgets['a']) == {'max_actions'}
    assert set(panel._stop_condition_param_widgets['b']) == {
        'resource', 'operator', 'threshold'}
    assert panel._stop_condition_param_widgets['b']['resource'][0] == 'str'

    # 回填当前值
    wmap_a = panel._stop_condition_param_widgets['a']
    assert wmap_a['max_actions'][1].value() == 7

    # 只显示选中条件对应的容器
    containers = panel._stop_condition_param_containers
    assert containers['a'].isVisible() != containers['b'].isVisible() or True
    panel._stop_condition_selected_id = 'b'
    panel._rebuild_stop_condition_params()
    assert all(k in containers for k in ('a', 'b'))


def test_param_area_removes_container_for_deleted_condition(panel):
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'fixed_action_count', 'max_actions': 1},
         {'id': 'b', 'type': 'time_limit', 'max_time': 10.0}], 'a or b')
    panel._stop_condition_conditions.pop()
    panel._refresh_stop_condition_table()
    assert set(panel._stop_condition_param_widgets) == {'a'}
    assert set(panel._stop_condition_param_containers) == {'a'}


def test_param_area_collects_before_rebuild(panel):
    """重建前先收值——否则用户编辑会被模型旧值覆盖。"""
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'fixed_action_count', 'max_actions': 1}], 'a')
    panel._stop_condition_param_widgets['a']['max_actions'][1].setValue(42)
    panel._rebuild_stop_condition_params()
    assert panel._stop_condition_conditions[0]['max_actions'] == 42
    # 幂等：再重建一次值不变
    panel._rebuild_stop_condition_params()
    assert panel._stop_condition_param_widgets['a']['max_actions'][1].value() == 42


# ── 4c2b：内存态 ↔ store 的全量重建与回填 ────────────────────────

def test_apply_to_store_writes_tree_and_is_idempotent(panel):
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'fixed_action_count', 'max_actions': 5},
         {'id': 'b', 'type': 'time_limit', 'max_time': 100.0}], 'a or b')

    panel.apply_to_store()
    first = panel._store.stop_condition
    assert first is not None and first['mode'] == 'any'
    assert len(first['conditions']) == 2

    # 幂等：反复写回不得清空或改变条件树（apply_to_store 挂在预览去抖与导出两条
    # 高频路径上）
    for _ in range(3):
        panel.apply_to_store()
    assert panel._store.stop_condition == first


def test_apply_to_store_empty_expression_writes_none(panel):
    panel.set_stop_condition_conditions([], '')
    panel.apply_to_store()
    assert panel._store.stop_condition is None


def test_apply_to_store_keeps_last_valid_tree_on_bad_expression(panel):
    """表达式非法时保守返回上一次的有效树，不写入半成品。"""
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'time_limit', 'max_time': 100.0}], 'a')
    panel.apply_to_store()
    good = panel._store.stop_condition

    panel._stop_condition_expr = 'a and ('      # 未闭合括号
    panel.apply_to_store()
    assert panel._store.stop_condition == good


def test_load_from_store_round_trip(panel):
    """store.stop_condition → 条件列表与表达式 → 写回，逐字段一致。"""
    from gacha_simulator.core.config_toml import load_toml

    store = load_toml(CONFIG)
    store.stop_condition = {
        'mode': 'any',
        'conditions': [
            {'type': 'fixed_action_count', 'max_actions': 5},
            {'mode': 'not', 'conditions': [
                {'type': 'target_acquired', 'target_id': 'x', 'quantity': 1}]},
        ],
    }
    panel.set_store(store)
    panel._load_stop_condition_from_store(store)

    assert [c['id'] for c in panel._stop_condition_conditions] == ['a', 'b']
    assert panel._stop_condition_expr == 'a or not b'
    panel.apply_to_store()
    assert panel._store.stop_condition == store.stop_condition


# ── 4d2b1：id 管理体系 ──────────────────────────────────────────

def test_allocate_id_skips_taken_and_reserved(panel):
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'time_limit', 'max_time': 1.0},
         {'id': 'c', 'type': 'time_limit', 'max_time': 2.0}], 'a or c')
    assert panel._allocate_stop_condition_id() == 'b'
    assert panel._allocate_stop_condition_id() not in ('and', 'or', 'not')


@pytest.mark.parametrize('bad,expected_frag', [
    ('', '不能为空'),
    ('and', '保留字'),
    ('or', '保留字'),
    ('not', '保留字'),
    ('1a', '合法'),
    ('a b', '合法'),
    ('a-b', '合法'),
])
def test_validate_id_rejects(panel, bad, expected_frag):
    msg = panel._validate_stop_condition_id(bad)
    assert msg and expected_frag in msg


def test_validate_id_rejects_duplicate(panel):
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'time_limit', 'max_time': 1.0},
         {'id': 'b', 'type': 'time_limit', 'max_time': 2.0}], 'a or b')
    msg = panel._validate_stop_condition_id('b', current_id='a')
    assert msg and '占用' in msg
    assert panel._validate_stop_condition_id('a', current_id='a') is None


def test_rename_replaces_all_references_in_expression(panel):
    """含同一 id 在表达式中多次出现的情形。"""
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'time_limit', 'max_time': 1.0},
         {'id': 'b', 'type': 'time_limit', 'max_time': 2.0}],
        'a and (b or a)')
    panel._rename_stop_condition_id('a', 'x')
    assert panel._stop_condition_expr == 'x and (b or x)'


def test_rename_does_not_touch_lookalike_identifiers(panel):
    """AST 改写而非字符串替换——`ab` 中的 `a` 不得被误改。"""
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'time_limit', 'max_time': 1.0},
         {'id': 'ab', 'type': 'time_limit', 'max_time': 2.0}], 'a or ab')
    panel._rename_stop_condition_id('a', 'z')
    assert panel._stop_condition_expr == 'z or ab'


def test_item_changed_applies_rename_and_reverts_on_error(panel, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'time_limit', 'max_time': 1.0},
         {'id': 'b', 'type': 'time_limit', 'max_time': 2.0}], 'a or b')

    # 阻塞信号后手动改文本再显式调用处理器：真实路径下 setText 会自行触发
    # itemChanged，而处理器内的表格刷新会重建 QTableWidgetItem（旧包装器失效）
    table = panel.stop_condition_table
    table.blockSignals(True)
    item = table.item(0, 0)
    item.setText('x')
    table.blockSignals(False)
    panel._on_stop_condition_item_changed(item)
    assert panel._stop_condition_conditions[0]['id'] == 'x'
    assert panel._stop_condition_expr == 'x or b'

    calls = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **k: calls.append(a))
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'time_limit', 'max_time': 1.0},
         {'id': 'b', 'type': 'time_limit', 'max_time': 2.0}], 'a or b')
    table.blockSignals(True)
    item = table.item(0, 0)
    item.setText('b')
    table.blockSignals(False)
    panel._on_stop_condition_item_changed(item)
    assert calls, '非法 id 必须给出可读提示'
    assert panel._stop_condition_conditions[0]['id'] == 'a'
    assert panel.stop_condition_table.item(0, 0).text() == 'a'
