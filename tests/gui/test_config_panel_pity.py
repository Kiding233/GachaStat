"""P55 阶段十一：ConfigPanel 保底 UI 端到端集成测试。

覆盖完整启动流程：加载 TOML → _refresh_from_store_impl → _on_pity_selected
→ _apply_pity_edit → apply_to_store → get_config。
窗口会短暂显示——用户明确不介意。
"""

import os
import sys

# ⚠️ 必须在任何 Qt import 之前设置，否则 QtWebEngineWidgets 导入会崩溃
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    """模块级 QApplication——所有测试共享。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # 不调用 quit()——后续模块可能还需要 QApplication


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
# 核心集成测试
# ═══════════════════════════════════════════════════════════════════


class TestPityPanelStartup:
    """模拟启动流程——完整路径无崩溃"""

    def test_refresh_populates_pity_defs(self, qapp):
        """加载 TOML 后 _pity_defs 非空且格式正确"""
        panel = _make_panel()
        assert len(panel._pity_defs) >= 1
        pd = panel._pity_defs[0]
        assert pd["name"]
        assert pd["btype"] in ("soft_interval", "soft_additive", "soft_step", "hard")
        assert pd["scope"] in ("ssr", "sr", "r")
        for key in ["name", "btype", "scope", "target_featured", "deltas",
                     "threshold", "counter_init", "soft_start", "soft_end",
                     "reset", "pools", "deactivate_on_early_hit"]:
            assert key in pd, f"缺少字段: {key}"

    def test_select_first_pity_no_crash(self, qapp):
        """选中第一个保底 → _on_pity_selected 不崩溃"""
        panel = _make_panel()
        assert panel.pity_list.count() >= 1
        panel.pity_list.setCurrentRow(0)
        assert panel._pity_detail_group.isEnabled()

    def test_select_all_pities_no_crash(self, qapp):
        """遍历所有保底条目——逐个选中不崩溃"""
        panel = _make_panel()
        for i in range(panel.pity_list.count()):
            panel.pity_list.setCurrentRow(i)
            assert panel._pity_detail_group.isEnabled()
            assert panel._pity_dynamic_container is not None

    def test_select_none_disables_detail(self, qapp):
        """无选中时详情面板禁用"""
        panel = _make_panel()
        panel.pity_list.clearSelection()
        panel.pity_list.setCurrentRow(-1)
        # _on_pity_selected(-1) 会禁用
        # 手动触发一下
        panel._on_pity_selected(-1)
        assert not panel._pity_detail_group.isEnabled()


class TestPityTypeSwitching:
    """切换保底类型——动态控件重建不崩溃"""

    def test_cycle_all_types(self, qapp):
        """遍历全部 4 种类型——每次切换调 _on_pity_type_changed"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        for i in range(panel.pity_type_combo.count()):
            panel.pity_type_combo.setCurrentIndex(i)
            assert panel._pity_dynamic_container.parentWidget() is not None

    def test_switch_type_and_back(self, qapp):
        """soft_interval → hard → soft_interval——往返切换正常"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        hard_idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES)
                        if t == "hard")
        panel.pity_type_combo.setCurrentIndex(hard_idx)
        assert panel._pity_dynamic_container.parentWidget() is not None

        si_idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES)
                      if t == "soft_interval")
        panel.pity_type_combo.setCurrentIndex(si_idx)
        assert panel._pity_dynamic_container.parentWidget() is not None
        # 应有 start/end 两个动态控件
        assert panel._pity_dynamic_area.rowCount() >= 2


class TestPityEditApply:
    """编辑并应用修改——_apply_pity_edit 不崩溃"""

    def test_apply_without_changes(self, qapp):
        """选中保底后直接点应用——不修改任何值"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        panel._apply_pity_edit()
        assert panel._pity_defs[0]["name"]

    def test_edit_name_and_apply(self, qapp):
        """修改名称后应用——列表同步"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        panel.pity_name_edit.setText("test_pity_edited")
        panel._apply_pity_edit()
        assert panel._pity_defs[0]["name"] == "test_pity_edited"
        assert panel.pity_list.item(0).text() == "test_pity_edited"

    def test_switch_to_hard_and_apply(self, qapp):
        """切换类型为 hard → 设置 threshold → 应用保存"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        hard_idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES)
                        if t == "hard")
        panel.pity_type_combo.setCurrentIndex(hard_idx)
        # 设置 threshold
        tw = panel._pity_dynamic_widgets.get("threshold")
        if tw and hasattr(tw, "setValue"):
            tw.setValue(180)
        panel._apply_pity_edit()
        pd = panel._pity_defs[0]
        assert pd["btype"] == "hard"
        assert pd.get("threshold") == 180

    def test_soft_interval_params_roundtrip(self, qapp):
        """编辑 start/end → 应用 → 重新选中 → 控件值保持"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        si_idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES)
                      if t == "soft_interval")
        panel.pity_type_combo.setCurrentIndex(si_idx)

        sw = panel._pity_dynamic_widgets.get("start")
        ew = panel._pity_dynamic_widgets.get("end")
        if sw and hasattr(sw, "setValue"):
            sw.setValue(50)
        if ew and hasattr(ew, "setValue"):
            ew.setValue(60)
        panel._apply_pity_edit()

        # 重新选中同一行——控件应显示新值
        panel.pity_list.setCurrentRow(-1)
        panel.pity_list.setCurrentRow(0)
        sw2 = panel._pity_dynamic_widgets.get("start")
        if sw2 and hasattr(sw2, "value"):
            assert sw2.value() == 50


class TestApplyToStore:
    """apply_to_store —— 写入 ConfigStore 正确"""

    def test_store_has_new_pity_format(self, qapp):
        """apply_to_store 后 Store 使用新 PityDef 格式"""
        panel = _make_panel()
        panel.apply_to_store()
        p0 = panel._store.pity.pities[0]
        assert hasattr(p0, "scope")
        assert hasattr(p0, "deltas")
        assert hasattr(p0, "counter_init")
        assert not hasattr(p0, "params")

    def test_round_trip_preserves_data(self, qapp):
        """数据往返一致"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        orig_name = panel._pity_defs[0]["name"]
        orig_btype = panel._pity_defs[0]["btype"]
        panel.apply_to_store()
        panel._refresh_from_store_impl()
        assert panel._pity_defs[0]["name"] == orig_name
        assert panel._pity_defs[0]["btype"] == orig_btype


class TestGetConfig:
    """get_config —— 输出新格式"""

    def test_pities_list_format(self, qapp):
        """输出含 pities 列表"""
        panel = _make_panel()
        config = panel.get_config()
        pity = config.get("pity", {})
        assert "pities" in pity
        assert len(pity["pities"]) >= 1

    def test_no_old_fields_in_output(self, qapp):
        """旧字段不出现在输出中"""
        panel = _make_panel()
        config = panel.get_config()
        pdef = config["pity"]["pities"][0]
        assert "type" in pdef
        assert "scope" in pdef
        assert "params" not in pdef
        assert "target_distribution" not in pdef


class TestAddRemovePity:
    """增删保底条目"""

    def test_add_then_remove(self, qapp):
        """添加 → 选中 → 移除"""
        panel = _make_panel()
        n = len(panel._pity_defs)
        panel._add_pity()
        assert len(panel._pity_defs) == n + 1
        panel.pity_list.setCurrentRow(panel.pity_list.count() - 1)
        panel._remove_pity()
        assert len(panel._pity_defs) == n


class TestDeltasTable:
    """soft_step 的 deltas 表格显隐"""

    def test_soft_step_shows_deltas(self, qapp):
        """切到 soft_step → deltas 表格可见"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        ss_idx = next((i for i, (t, _) in enumerate(panel._PITY_TYPES)
                       if t == "soft_step"), None)
        assert ss_idx is not None, "soft_step 不在 _PITY_TYPES 中（类型表变更致本测试前提失效）"
        panel.pity_type_combo.setCurrentIndex(ss_idx)
        # 使用 isHidden() 而非 isVisible()：面板未显示时后者总是 False
        assert not panel._pity_deltas_group.isHidden()

    def test_soft_interval_hides_deltas(self, qapp):
        """非 soft_step 时 deltas 隐藏"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        si_idx = next(i for i, (t, _) in enumerate(panel._PITY_TYPES)
                      if t == "soft_interval")
        panel.pity_type_combo.setCurrentIndex(si_idx)
        assert panel._pity_deltas_group.isHidden()
# ══════════════════════════════════════════════════════════════════
# P64 G16-1 / AUDIT-BREAK-1：无保底段时兜底条目的合法性
# ══════════════════════════════════════════════════════════════════

# G16-1 的 reset 白名单：空串（回退 scope 兜底分支）/ featured / 稀有度名 / never。
# 稀有度名取自本模块加载的 config.toml 的 [rarities]（ssr / sr / r）。
_RESET_WHITELIST = {'', 'featured', 'never', 'ssr', 'sr', 'r'}


class TestPityFallbackEntry:
    """`set_config` 在 `pities` 为空时就地合成的兜底条目须全合法（AUDIT-BREAK-1）。

    原兜底的三个取值恰好都落在 P64 新增的硬拒面上：`type='soft'` 不在
    BEHAVIOR_REGISTRY（create_behavior 首行 KeyError）、`reset='any_ssr'` 不在
    G16 的 reset 白名单、嵌套 `params` 使 start/end 读不到（平台默认阈值丢失）。
    处置取方案 a（2026-10-10 用户裁决）：改写为全合法形态。
    """

    def test_fallback_entry_type_in_registry_reset_in_whitelist(self, qapp):
        """type 在 BEHAVIOR_REGISTRY 内、reset 在 G16 白名单内。"""
        from gacha_simulator.core.pity import BEHAVIOR_REGISTRY

        panel = _make_panel()
        panel.set_config({'pity': {'pities': []}})
        entry = panel.get_config()['pity']['pities'][0]

        assert entry['name'] == 'ssr_soft'
        assert entry['type'] in BEHAVIOR_REGISTRY, (
            f"兜底条目 type='{entry['type']}' 不在 BEHAVIOR_REGISTRY 内")
        assert entry['reset'] in _RESET_WHITELIST, (
            f"兜底条目 reset='{entry['reset']}' 不在 G16 白名单内")

    def test_fallback_entry_start_end_from_pity_section(self, qapp):
        """soft_start / soft_end 取自 pity.start / pity.end（不再走嵌套 params）。"""
        panel = _make_panel()
        panel.set_config({'pity': {'pities': [], 'start': 62, 'end': 88}})
        entry = panel.get_config()['pity']['pities'][0]
        assert (entry['start'], entry['end']) == (62, 88)

    def test_fallback_entry_start_end_platform_default(self, qapp):
        """pity 段未给 start/end 时落平台默认 74 / 90（原嵌套 params 下两者都丢）。"""
        panel = _make_panel()
        panel.set_config({'pity': {'pities': []}})
        entry = panel.get_config()['pity']['pities'][0]
        assert (entry['start'], entry['end']) == (74, 90)

    def test_fallback_entry_engine_constructs(self, qapp):
        """兜底条目可进引擎构造（原 type='soft' 在 create_behavior 首行 KeyError）。"""
        from gacha_simulator.core.pity import PityState, create_behavior

        panel = _make_panel()
        panel.set_config({'pity': {'pities': []}})
        pdefs = [p for p in panel._store.pity.pities if p.name == 'ssr_soft']
        assert len(pdefs) == 1, "兜底条目 name='ssr_soft' 未落进 store.pity.pities"
        assert create_behavior(pdefs[0], PityState()) is not None

    def test_set_config_get_config_load_toml_no_config_error(self, qapp, tmp_path):
        """set_config（无保底段）→ get_config → load_toml 全程不抛 ConfigError。"""
        from gacha_simulator.core.config_toml import load_toml, save_toml

        panel = _make_panel()
        panel.set_config({'pity': {'pities': []}})
        panel.get_config()
        out = tmp_path / "no_pity.toml"
        save_toml(panel._store, str(out))
        store2 = load_toml(str(out))
        assert [p.name for p in store2.pity.pities] == ['ssr_soft']
