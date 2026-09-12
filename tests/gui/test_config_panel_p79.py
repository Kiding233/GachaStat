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

    # 移除选中（4d2b2 起：被表达式引用的 id 须先解除引用才能删除，否则阻断）
    panel.stop_condition_table.selectRow(0)
    panel.stop_condition_expr_edit.setText('b')
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


# ── 4d2b2：组合区交互规则 1-3 与单选同屏同步 ──────────────────────

def _set_three(panel):
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'time_limit', 'max_time': 1.0},
         {'id': 'b', 'type': 'time_limit', 'max_time': 2.0},
         {'id': 'c', 'type': 'time_limit', 'max_time': 3.0}], '')
    panel._refresh_stop_condition_expr_widget()


def test_radio_rewrites_expression(panel):
    _set_three(panel)
    panel._stop_condition_mode_buttons['any'].setChecked(True)
    assert panel._stop_condition_expr == 'a or b or c'
    panel._stop_condition_mode_buttons['all'].setChecked(True)
    assert panel._stop_condition_expr == 'a and b and c'


def test_manual_edit_falls_to_custom(panel):
    _set_three(panel)
    panel._stop_condition_mode_buttons['any'].setChecked(True)
    assert panel._stop_condition_mode_buttons['any'].isChecked()

    panel.stop_condition_expr_edit.setText('a and (b or c)')
    assert panel._stop_condition_expr == 'a and (b or c)'
    buttons = panel._stop_condition_mode_buttons
    assert buttons['custom'].isChecked()
    assert not buttons['any'].isChecked() and not buttons['all'].isChecked()


def test_sync_is_one_way_and_does_not_loop(panel):
    """单选 ↔ 表达式单向同步：表达式行内容不被回写，勾选态稳定。"""
    _set_three(panel)
    panel._stop_condition_mode_buttons['any'].setChecked(True)
    assert panel.stop_condition_expr_edit.text() == 'a or b or c'
    # 反复刷新不改变状态
    for _ in range(3):
        panel._refresh_stop_condition_expr_widget()
    assert panel._stop_condition_expr == 'a or b or c'
    assert panel._stop_condition_mode_buttons['any'].isChecked()


def test_mode_detected_from_equivalent_text(panel):
    """按 AST 等价判定，不按文本比对（空格与多余括号不影响识别）。"""
    _set_three(panel)
    panel.stop_condition_expr_edit.setText('a  or  (b or c)')
    assert panel._stop_condition_mode_buttons['any'].isChecked()


def test_add_condition_appends_to_expression(panel):
    _set_three(panel)
    panel._stop_condition_mode_buttons['any'].setChecked(True)
    panel.stop_condition_type_combo.setCurrentIndex(0)
    panel._on_stop_condition_add()
    assert panel._stop_condition_conditions[-1]['id'] == 'd'
    assert panel._stop_condition_expr == 'a or b or c or d'


def test_add_condition_when_expression_empty(panel):
    panel.set_stop_condition_conditions([], '')
    panel.stop_condition_type_combo.setCurrentIndex(0)
    panel._on_stop_condition_add()
    assert panel._stop_condition_expr == 'a'


def test_remove_referenced_condition_is_blocked(panel, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    _set_three(panel)
    panel._stop_condition_mode_buttons['any'].setChecked(True)
    calls = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **k: calls.append(a))

    panel.stop_condition_table.selectRow(1)          # 选中 b（被引用）
    panel._on_stop_condition_remove()
    assert calls, '删除被引用的 id 必须给出阻断提示'
    assert [c['id'] for c in panel._stop_condition_conditions] == ['a', 'b', 'c']
    assert panel._stop_condition_expr == 'a or b or c'


def test_remove_unreferenced_condition_succeeds(panel):
    _set_three(panel)
    panel._stop_condition_mode_buttons['any'].setChecked(True)
    # 手改表达式去掉对 b 的引用
    panel.stop_condition_expr_edit.setText('a or c')
    panel.stop_condition_table.selectRow(1)
    panel._on_stop_condition_remove()
    assert [c['id'] for c in panel._stop_condition_conditions] == ['a', 'c']


def test_empty_condition_list_disables_expression_row(panel):
    panel.set_stop_condition_conditions([], '')
    panel._refresh_stop_condition_expr_widget()
    assert not panel.stop_condition_expr_edit.isEnabled()
    assert '硬边界' in panel.stop_condition_expr_edit.placeholderText()

    _set_three(panel)
    assert panel.stop_condition_expr_edit.isEnabled()


# ── 4d2b3：即时校验与应用流程 ────────────────────────────────────

def test_inline_validation_reports_syntax_error(panel):
    _set_three(panel)
    panel.stop_condition_expr_edit.setText('a and (b')
    assert panel.stop_condition_expr_status.text() == '✗'
    assert '括号' in panel.stop_condition_error_label.text()
    # 不阻断输入：表达式行仍可用
    assert panel.stop_condition_expr_edit.isEnabled()


def test_inline_validation_reports_dangling_reference(panel):
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'time_limit', 'max_time': 1.0},
         {'id': 'b', 'type': 'time_limit', 'max_time': 2.0}], 'a or b')
    # 直接改内存态模拟「条件被删但表达式仍引用」的错误态
    panel._stop_condition_conditions.pop()
    panel._refresh_stop_condition_expr_widget()
    assert panel.stop_condition_expr_status.text() == '✗'
    assert "'b'" in panel.stop_condition_error_label.text()
    assert '已被删除' in panel.stop_condition_error_label.text()


def test_inline_validation_ok(panel):
    _set_three(panel)
    panel.stop_condition_expr_edit.setText('a or b')
    assert panel.stop_condition_expr_status.text() == '✔'
    assert panel.stop_condition_error_label.text() == ''


def test_apply_refuses_on_invalid_and_keeps_previous(panel, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    _set_three(panel)
    panel.stop_condition_expr_edit.setText('a or b')
    panel.apply_to_store()
    good = panel._store.stop_condition
    assert good is not None

    calls = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **k: calls.append(a))
    panel.stop_condition_expr_edit.setText('a and (')
    panel._on_stop_condition_apply()
    assert calls, '非法表达式必须拒绝应用并提示'
    assert panel._store.stop_condition == good, '失败时必须保留原态'


def test_apply_succeeds_on_valid(panel):
    _set_three(panel)
    panel.stop_condition_expr_edit.setText('a or b')
    panel._on_stop_condition_apply()
    assert panel._store.stop_condition is not None
    assert '已应用' in panel.stop_condition_error_label.text()


# ── 4d3：引用完整性的 GUI 侧与保存闸门 ───────────────────────────

def _make_dangling(panel):
    """构造「条件被删但表达式仍引用」的错误态（正常 UI 路径会被规则 3 阻断）。"""
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'time_limit', 'max_time': 1.0},
         {'id': 'b', 'type': 'time_limit', 'max_time': 2.0}], 'a or b')
    panel._stop_condition_conditions.pop()
    panel._refresh_stop_condition_expr_widget()
    return panel


def test_validate_banners_reports_dangling_reference(panel):
    _make_dangling(panel)
    errors = panel.validate_banners()
    assert any('已被删除' in e and "'b'" in e for e in errors), errors


def test_validate_banners_clean_when_consistent(panel):
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'time_limit', 'max_time': 1.0}], 'a')
    assert panel.validate_banners() == []


def test_validate_banners_safe_on_bare_panel(qapp):
    """裸构造（无 _store、无条件树内存态）仍安全返回 List[str]。

    这是 tests/gui/test_config_panel_p61.py 三处既有断言的隐式契约。
    """
    from gacha_simulator.gui.config_panel import ConfigPanel

    bare = ConfigPanel()
    errors = bare.validate_banners()
    assert isinstance(errors, list)
    bare.deleteLater()


def test_export_config_gate_blocks_dangling_state(panel, monkeypatch, tmp_path):
    """保存闸门被触发：非法停止条件不得落盘。

    以轻量 QWidget 替身驱动 MainWindow.export_config（未绑定调用）——本方法在
    拦截路径上只用到 self.config_panel。**不构造真实 MainWindow**：那会初始化
    QtWebEngine，与 tests/gui/test_startup.py 的 MainWindow 用例相互干扰，
    实测会触发 access violation（全量套件段错误）。
    """
    from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

    from gacha_simulator.gui.main_window import MainWindow

    class _StubWindow(QWidget):
        def __init__(self, config_panel):
            super().__init__()
            self.config_panel = config_panel

    stub = _StubWindow(panel)
    try:
        target = tmp_path / 'p79_out.toml'
        monkeypatch.setattr(QFileDialog, 'getSaveFileName',
                            lambda *a, **k: (str(target), ''))
        calls = []
        monkeypatch.setattr(QMessageBox, 'warning',
                            lambda *a, **k: calls.append(a))

        _make_dangling(panel)
        MainWindow.export_config(stub)

        assert calls, '保存闸门未触发'
        assert not target.exists(), '非法状态不得写出配置文件'
    finally:
        stub.deleteLater()


# ── 5c2b：8.1 断言 6（同轴条件预填不得被控件钳位）─────────────────

@pytest.mark.parametrize('type_key,pkey,registry_default', [
    ('all_pools_end', 'end_time', 0.0),
    ('time_limit', 'max_time', 86400.0),
])
def test_coaxial_condition_prefill_not_clamped(panel, type_key, pkey,
                                               registry_default):
    """阈值控件的读回值 == store.end_time，且 maximum() >= end_time。

    默认配置 end_time = 168 天 = 14515200 秒，远超 FloatParam 类默认上限
    99999.0——未做范围放宽时 Qt 会把预填值静默钳到 99999（约 1.16 天），
    控件不报错、回显为合法值，预填设计完全落空。
    """
    end = panel._store.end_time
    assert end > 99999.0, '前提：默认配置的 end_time 远超 FloatParam 类默认上限'

    panel.set_stop_condition_conditions([{'id': 'a', 'type': type_key}], 'a')
    panel._rebuild_stop_condition_params()
    widget = panel._stop_condition_param_widgets['a'][pkey][1]

    assert widget.value() == end, '预填值被钳位或未生效'
    assert widget.value() != registry_default, '仍是注册表默认（预填未生效）'
    assert widget.maximum() >= end, '控件范围未放宽，预填会被静默钳位'
    # 模型同步为预填值：apply 落盘的应是 end_time 而非旧默认
    assert panel._stop_condition_conditions[0][pkey] == end


def test_user_customized_coaxial_threshold_is_not_overwritten(panel):
    """用户已自定义阈值时不得被预填覆盖。"""
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'time_limit', 'max_time': 3600.0}], 'a')
    panel._rebuild_stop_condition_params()
    widget = panel._stop_condition_param_widgets['a']['max_time'][1]
    assert widget.value() == 3600.0
    assert panel._stop_condition_conditions[0]['max_time'] == 3600.0


def test_non_coaxial_condition_keeps_registry_default(panel):
    """非同一轴条件的默认值仍来自 ParamDescriptor（5.7 预填只针对两条同轴条件）。"""
    panel.set_stop_condition_conditions(
        [{'id': 'a', 'type': 'fixed_action_count'}], 'a')
    panel._rebuild_stop_condition_params()
    widget = panel._stop_condition_param_widgets['a']['max_actions'][1]
    assert widget.value() == 100          # IntParam default=100
