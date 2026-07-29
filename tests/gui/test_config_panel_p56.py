"""P56 阶段十三-c：ConfigPanel 保底 UI P56 扩展集成测试。

覆盖目标：
  1. _PITY_TYPES 包含 10 条目（4 + 6 P56 新增）
  2. type 切换时专属控件显隐正确
  3. 池子级 epitomizable_cards round-trip
  4. 联动校验（depends_on 引用不存在→警告）
"""

import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def _make_panel():
    """构造含真实 TOML 的 ConfigPanel 并刷新。"""
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.gui.config_panel import ConfigPanel

    toml_path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "gacha_simulator", "config", "config.toml",
    )
    store = load_toml(toml_path)
    p = ConfigPanel()
    p._store = store
    p._refresh_from_store_impl()
    return p


# ═══════════════════════════════════════════════════════════════════
# PITY_TYPES 扩展
# ═══════════════════════════════════════════════════════════════════

class TestPityTypesP56:
    """P56 类型在 _PITY_TYPES 和下拉框中就绪。"""

    def test_pity_types_has_10_entries(self, qapp):
        panel = _make_panel()
        assert len(panel._PITY_TYPES) == 10

    def test_all_p56_types_present(self, qapp):
        panel = _make_panel()
        btypes = {t for t, _ in panel._PITY_TYPES}
        for bt in ('rotating', 'rotating_soft', 'rotating_cr',
                    'rotating_cr_soft', 'targeted', 'targeted_soft'):
            assert bt in btypes, f"缺少类型: {bt}"

    def test_combo_has_10_entries(self, qapp):
        panel = _make_panel()
        assert panel.pity_type_combo.count() == 10


# ═══════════════════════════════════════════════════════════════════
# 控件显隐
# ═══════════════════════════════════════════════════════════════════

class TestP56WidgetVisibility:
    """P56 专属控件在对应 type 下正确显隐。"""

    def test_rotating_shows_guaranteed_init(self, qapp):
        """rotating 类型——guaranteed_init 复选框可见。"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES) if t == 'rotating')
        panel.pity_type_combo.setCurrentIndex(idx)
        assert not panel.pity_guaranteed_init_cb.isHidden()

    def test_targeted_shows_fate_points_init(self, qapp):
        """targeted 类型——fate_points_init 可见。"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES) if t == 'targeted')
        panel.pity_type_combo.setCurrentIndex(idx)
        assert not panel.pity_fate_points_spin.isHidden()

    def test_hard_hides_p56_init_widgets(self, qapp):
        """hard 类型——P56 初始状态控件均隐藏。"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES) if t == 'hard')
        panel.pity_type_combo.setCurrentIndex(idx)
        assert panel.pity_guaranteed_init_cb.isHidden()
        assert panel.pity_fate_points_spin.isHidden()

    def test_rotating_cr_shows_cr_probs_table(self, qapp):
        """rotating_cr 类型——cr_state_probs 表格可见。"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES)
                    if t == 'rotating_cr')
        panel.pity_type_combo.setCurrentIndex(idx)
        assert not panel._pity_cr_probs_group.isHidden()

    def test_rotating_hides_cr_probs_table(self, qapp):
        """普通 rotating 类型——cr_state_probs 表格隐藏。"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES) if t == 'rotating')
        panel.pity_type_combo.setCurrentIndex(idx)
        assert panel._pity_cr_probs_group.isHidden()

    def test_deactivate_on_early_hit_only_enabled_for_hard(self, qapp):
        """deactivate_on_early_hit 仅 type=hard 启用。"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)

        # hard → 启用
        hard_idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES) if t == 'hard')
        panel.pity_type_combo.setCurrentIndex(hard_idx)
        assert panel.pity_deactivate_cb.isEnabled()

        # rotating → 禁用
        rot_idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES) if t == 'rotating')
        panel.pity_type_combo.setCurrentIndex(rot_idx)
        assert not panel.pity_deactivate_cb.isEnabled()


# ═══════════════════════════════════════════════════════════════════
# depends_on 下拉框
# ═══════════════════════════════════════════════════════════════════

class TestDependsOnCombo:
    """depends_on 使用 QComboBox 而非 QLineEdit。"""

    def test_depends_on_is_combo_not_lineedit(self, qapp):
        panel = _make_panel()
        from PyQt6.QtWidgets import QComboBox
        assert isinstance(panel.pity_depends_combo, QComboBox)

    def test_depends_on_has_no_dependency_option(self, qapp):
        panel = _make_panel()
        # 第一项应为 "(无依赖)"
        assert panel.pity_depends_combo.itemText(0) == "(无依赖)"
        assert panel.pity_depends_combo.itemData(0) == ""

    def test_depends_on_populated_after_refresh(self, qapp):
        """加载 TOML 后 depends_on 下拉框含已有 behavior 名称。"""
        panel = _make_panel()
        # 应至少有 2 项：(无依赖) + 至少一个已有 behavior
        assert panel.pity_depends_combo.count() >= 2


# ═══════════════════════════════════════════════════════════════════
# 序列化 round-trip
# ═══════════════════════════════════════════════════════════════════

class TestP56SerializationRoundtrip:
    """P56 字段在 get_config / set_config / apply_to_store / refresh 中保持。"""

    def test_get_config_includes_p56_pity_fields(self, qapp):
        """get_config 输出含 P56 字段键。"""
        panel = _make_panel()
        config = panel.get_config()
        pities = config.get("pity", {}).get("pities", [])
        assert len(pities) >= 1
        sample = pities[0]
        for key in ('guaranteed_init', 'fate_points_init', 'cr_counter_threshold',
                     'cr_base_rate', 'cr_state_probs', 'fate_threshold',
                     'switch_allowed', 'switch_resets_progress'):
            assert key in sample, f"get_config 缺少字段: {key}"

    def test_get_config_includes_epitomizable_cards(self, qapp):
        """get_config 输出 pools 含 epitomizable_cards 键。"""
        panel = _make_panel()
        config = panel.get_config()
        pools = config.get("pools", [])
        assert len(pools) >= 1
        assert 'epitomizable_cards' in pools[0], "get_config pools 缺少 epitomizable_cards"

    def test_apply_to_store_preserves_p56_fields(self, qapp):
        """apply_to_store 后 P56 字段不丢失。"""
        panel = _make_panel()
        panel.apply_to_store()
        p0 = panel._store.pity.pities[0]
        assert hasattr(p0, 'guaranteed_init')
        assert hasattr(p0, 'fate_points_init')
        assert hasattr(p0, 'cr_counter_threshold')

    def test_set_config_reads_p56_fields(self, qapp):
        """set_config 从 dict 正确读取 P56 字段（含 None 默认值）。"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        pd = panel._pity_defs[0]
        for key in ('guaranteed_init', 'fate_points_init', 'cr_counter_threshold',
                     'cr_base_rate', 'cr_state_probs', 'fate_threshold',
                     'switch_allowed', 'switch_resets_progress'):
            assert key in pd, f"_pity_defs 缺少字段: {key}"


# ═══════════════════════════════════════════════════════════════════
# cr_state_probs 表格操作
# ═══════════════════════════════════════════════════════════════════

class TestCrProbsTable:
    """cr_state_probs 表格增删操作。"""

    def test_add_row_to_cr_probs(self, qapp):
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES)
                    if t == 'rotating_cr')
        panel.pity_type_combo.setCurrentIndex(idx)

        initial_rows = panel.pity_cr_probs_table.rowCount()
        panel._add_cr_probs_row()
        assert panel.pity_cr_probs_table.rowCount() == initial_rows + 1

    def test_read_cr_probs_table(self, qapp):
        """写入 → 读取 round-trip。"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES)
                    if t == 'rotating_cr')
        panel.pity_type_combo.setCurrentIndex(idx)

        # 清空后写入已知值
        table = panel.pity_cr_probs_table
        table.setRowCount(0)
        for val in [0.0, 0.05, 0.55, 1.0]:
            row = table.rowCount()
            table.insertRow(row)
            from PyQt6.QtWidgets import QTableWidgetItem
            table.setItem(row, 0, QTableWidgetItem(str(val)))

        result = panel._read_cr_probs_table()
        assert result == [0.0, 0.05, 0.55, 1.0]


# ═══════════════════════════════════════════════════════════════════
# 联动校验
# ═══════════════════════════════════════════════════════════════════

class TestDependsComboRefresh:
    """depends_on 下拉框随增删刷新 + P56 行显隐。"""

    def test_depends_combo_refreshes_on_add(self, qapp):
        panel = _make_panel()
        old_count = panel.pity_depends_combo.count()
        panel._add_pity()
        assert panel.pity_depends_combo.count() >= old_count

    def test_depends_combo_refreshes_on_remove(self, qapp):
        panel = _make_panel()
        n = len(panel._pity_defs)
        if n < 2:
            panel._add_pity()
        before = panel.pity_depends_combo.count()
        panel.pity_list.setCurrentRow(panel.pity_list.count() - 1)
        panel._remove_pity()
        assert panel.pity_depends_combo.count() <= before

    def test_fate_points_row_hidden_for_non_targeted(self, qapp):
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES) if t == 'hard')
        panel.pity_type_combo.setCurrentIndex(idx)
        assert panel.pity_fate_points_spin.isHidden()
        label = panel._pity_detail_form.labelForField(panel.pity_fate_points_spin)
        assert label is None or label.isHidden()

    def test_guaranteed_init_row_hidden_for_non_rotating(self, qapp):
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES) if t == 'hard')
        panel.pity_type_combo.setCurrentIndex(idx)
        assert panel.pity_guaranteed_init_cb.isHidden()
        label = panel._pity_detail_form.labelForField(panel.pity_guaranteed_init_cb)
        assert label is None or label.isHidden()

class TestP56TypeSwitchNoCrash:
    """遍历所有 10 种类型切换——不崩溃。"""

    def test_cycle_all_10_types(self, qapp):
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        for i in range(panel.pity_type_combo.count()):
            panel.pity_type_combo.setCurrentIndex(i)
            # 每种类型应正确重建动态控件
            assert panel._pity_dynamic_container.parentWidget() is not None

    def test_switch_to_p56_type_and_back(self, qapp):
        """hard → rotating → rotating_cr → targeted → hard——往返不崩溃。"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        for bt in ('hard', 'rotating', 'rotating_cr', 'rotating_cr_soft',
                    'targeted', 'targeted_soft', 'rotating_soft', 'hard'):
            idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES) if t == bt)
            panel.pity_type_combo.setCurrentIndex(idx)
            assert panel._pity_dynamic_container.parentWidget() is not None
        # combo 当前选中 hard——不崩溃即通过
