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


_CONFIG_TOML = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "gacha_simulator", "config", "config.toml",
)


def _make_panel():
    """构造含真实 TOML 的 ConfigPanel 并刷新。"""
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.gui.config_panel import ConfigPanel

    store = load_toml(_CONFIG_TOML)
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

def _reset_whitelist() -> set:
    """G16-1 的 reset 白名单——取自 config_toml 的**同一份**实现。

    原实现把常量复制了一份（``{'', 'featured', 'never', 'ssr', 'sr', 'r'}``），
    而 config_toml 不导出该白名单，白名单改动只能靠第 5 条用例（load_toml
    往返）间接兜住，故改为直接调用 ``legal_reset_values()``。

    `[rarities]` 从磁盘上的 config.toml **现读**（不取 `panel._store`）：
    `set_config` 会先 `store.clear()` 清掉 `rarity_rank`（config_store.py 的
    清空清单含它），取面板的 store 会得到收缩后的白名单、丢掉稀有度名一项。
    `config_store._parse_rarities()` 产的键是大写，故按 `_build_pity` 的形态
    小写归一后传入。
    """
    from gacha_simulator.core.config_toml import legal_reset_values, load_toml

    store = load_toml(_CONFIG_TOML)
    return legal_reset_values({k.lower(): v for k, v in store.rarity_rank.items()})


def _engine_from_store(store):
    """按 GUI 的构造口径把 store 的保底定义喂给 PityEngine（pool_specs 留空）。

    S4-5 起 `PityEngine.__init__` 的构造失败一律抛 `ConfigError`，故「不抛异常」
    已构成证据；此处仍断言到 `engine.behaviors` 有该条目，钉的是「该条目确实被
    构造出来」，而不是「恰好没踩到失败」。
    """
    from gacha_simulator.core.pity import PityEngine, PityState

    return PityEngine(
        pool_specs={},
        pity_defs=list(store.pity.pities),
        rarity_rank={k.lower(): v for k, v in store.rarity_rank.items()},
        state=PityState(),
    )


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
        assert entry['reset'] in _reset_whitelist(), (
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
        """兜底条目可进 **PityEngine** 构造（原 type='soft' 在 create_behavior 首行 KeyError）。

        断言对象按 §3.8「方案 a 下再断言 `PityEngine` 构造成功」取引擎而非
        `create_behavior`：后者只覆盖单 behavior 工厂，而 GUI 路径的实际消费点是
        `PityEngine.__init__`。S4-5 之前它的构造兜底是**吞异常后跳过**（`pity.py`
        的 `try / except Exception → logger.warning`），那时「不抛异常」不构成证据；
        S4-5 起改为抛 `ConfigError`，但断言仍落在「该条目真的进了
        `engine.behaviors`」上，因为它钉的是构造成功本身而非未抛错。
        """
        panel = _make_panel()
        panel.set_config({'pity': {'pities': []}})
        pdefs = [p for p in panel._store.pity.pities if p.name == 'ssr_soft']
        assert len(pdefs) == 1, "兜底条目 name='ssr_soft' 未落进 store.pity.pities"

        engine = _engine_from_store(panel._store)
        assert 'ssr_soft' in engine.behaviors, (
            "兜底条目未构造出 behavior——被 PityEngine 的构造兜底静默跳过")

    def test_set_config_get_config_load_toml_no_config_error(self, qapp, tmp_path):
        """set_config（无保底段）→ get_config → load_toml 全程不抛 ConfigError。

        **载入侧断言不可省**（2026-10-10 独立审查）：只断言「名字还在」不足以证明
        条目可用。`_pitydef_to_toml` 曾对 `deltas is None` 的 soft_interval 不写
        start/end（GUI 内部态的 `deltas` 恒为 None），往返后阈值全丢、
        `_build_pity` 展开不出 deltas、`create_behavior` 抛 TypeError，而
        `PityEngine` 把它静默跳过（`behaviors` 为空表；S4-5 起改为抛
        `ConfigError`）——`load_toml` 本身却不报错，测试照样绿。故此处补齐两条载入侧断言：阈值活过往返 +
        引擎确实构造出该 behavior。
        """
        from gacha_simulator.core.config_toml import load_toml, save_toml

        panel = _make_panel()
        panel.set_config({'pity': {'pities': []}})
        panel.get_config()
        out = tmp_path / "no_pity.toml"
        save_toml(panel._store, str(out))
        store2 = load_toml(str(out))

        assert [p.name for p in store2.pity.pities] == ['ssr_soft']
        reloaded = store2.pity.pities[0]
        assert (reloaded.soft_start, reloaded.soft_end) == (74, 90), (
            "兜底条目的阈值未活过 TOML 往返（写回侧漏写 start/end）")
        assert 'ssr_soft' in _engine_from_store(store2).behaviors, (
            "载入后的 ssr_soft 未构造出 behavior（构造失败被跳过或抛错）")
# ══════════════════════════════════════════════════════════════════
# P64 G16-2：reset 控件的 round-trip（含「永不重置」与未列出取值）
# ══════════════════════════════════════════════════════════════════
# 与上方 TestPityFallbackEntry 分节不重叠：那一段的被测对象是 set_config 合成
# 的兜底条目，本段的被测对象是 reset 下拉自身的取值表与写回路径。

class TestPityResetCombo:
    """reset 下拉（G16-1 新建控件）的取值面与 round-trip。"""

    def test_reset_combo_lists_never_option(self, qapp):
        """下拉含「永不重置」项，取值为 `never`。"""
        panel = _make_panel()
        combo = panel.pity_reset_combo
        idx = combo.findData('never')
        assert idx >= 0, 'reset 下拉缺「永不重置」项'
        assert combo.itemText(idx) == '永不重置'

    def test_reset_combo_never_roundtrip(self, qapp, tmp_path):
        """选中「永不重置」→ 应用 → store → TOML 往返，`reset='never'` 保值。"""
        from gacha_simulator.core.config_toml import load_toml, save_toml

        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        idx = panel.pity_reset_combo.findData('never')
        assert idx >= 0
        panel.pity_reset_combo.setCurrentIndex(idx)
        panel._apply_pity_edit()
        panel.apply_to_store()

        assert panel._store.pity.pities[0].reset == 'never'
        out = tmp_path / "reset_never.toml"
        save_toml(panel._store, str(out))
        assert load_toml(str(out)).pity.pities[0].reset == 'never'

    def test_reset_combo_adds_store_rarity_names(self, qapp):
        """`[rarities].ranks` 里基础表未列出的稀有度按白名单同源补入下拉。"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        panel._store.rarity_rank['UR'] = 3
        panel._populate_reset_combo('ur')

        combo = panel.pity_reset_combo
        assert combo.currentData() == 'ur'
        assert combo.currentText() == 'ur 出金'
        assert panel._pity_defs[0]['reset'] == 'ur'

    def test_reset_combo_preserves_unlisted_value(self, qapp):
        """取值表外的取值补「原样保留」项，不被静默改写为空串。

        旧实现把未知取值一律落成下标 0（「跟随稀有度」），此后任一次编辑触发的
        flush（`_flush_pity_current_detail` / `_apply_pity_edit`）都会把它静默
        改写为空串，是无提示的数据丢失。样本取 `set_config` 的 `store.clear()`
        之后的形态（`rarity_rank` 已清空），此时取值表收缩为六项基础表。
        """
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        panel._store.rarity_rank.clear()
        panel._populate_reset_combo('ur')

        combo = panel.pity_reset_combo
        assert combo.currentData() == 'ur'
        assert '原样保留' in combo.currentText()
        panel._flush_pity_current_detail()
        assert panel._pity_defs[0]['reset'] == 'ur', \
            '取值表外的 reset 被静默改写（旧实现落回下标 0 即空串）'

    def test_reset_combo_excludes_values_rejected_by_loader(self, qapp, tmp_path):
        """`[rarities].ranks` 不含 sr / r 时，下拉不得提供被 loader 硬拒的取值。

        基础表把 ssr / sr / r 硬编码在内；不按白名单过滤时它是白名单的**超集**。
        实测（2026-10-10 独立审查端到端复现）：ranks 改为 {SSR, UR} 后下拉仍给出
        「SR 出金」，选中即写出 `reset = "sr"`，重载抛 `ConfigError: reset='sr'
        不是合法取值`——配置保存后无法再打开，与 AUDIT-BREAK-1 同一失效形态。
        """
        from gacha_simulator.core.config_toml import load_toml, save_toml

        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        panel._store.rarity_rank = {'SSR': 0, 'UR': 1}
        panel._populate_reset_combo('')

        combo = panel.pity_reset_combo
        offered = {combo.itemData(i) for i in range(combo.count())}
        assert 'sr' not in offered and 'r' not in offered, (
            f'ranks 不含 sr / r 时下拉仍提供被 loader 硬拒的取值：{sorted(offered)}'
        )
        assert {'', 'featured', 'never', 'ssr', 'ur'} <= offered, (
            f'白名单放行的取值被漏掉：{sorted(offered)}'
        )

        # 端到端：下拉里任一取值写回并保存后，都必须能重新载入
        for val in sorted(offered):
            combo.setCurrentIndex(combo.findData(val))
            panel._apply_pity_edit()
            panel.apply_to_store()
            out = tmp_path / f"reset_{val or 'empty'}.toml"
            save_toml(panel._store, str(out))
            reloaded = load_toml(str(out))
            assert reloaded.pity.pities[0].reset == val


# ═══════════════════════════════════════════════════════════════════
# P64 S4-5 审查：`target_featured` 勾选框只对 hard 族可用
# ═══════════════════════════════════════════════════════════════════
# 裁决 7B（2026-10-05）把 `soft_*` + `target_featured = true` 定为类型级硬拒，而
# GUI 的联动式原为 `not (is_hard and not is_ssr_scope)`，等价于「对全部非 hard 类型
# 启用」：勾选它、或先在 hard 上勾选再把类型切到 soft，都能就地造出「保存能过、
# 运行抛 ConfigError」的配置（S4-5 之前该失败被构造兜底吞掉，故长期不可见）。


class TestTargetFeaturedCheckboxScope:
    """`target_featured` 控件的作用域与残留清除。"""

    def _set_type(self, panel, key):
        for i in range(panel.pity_type_combo.count()):
            if panel._PITY_TYPES[i][0] == key:
                panel.pity_type_combo.setCurrentIndex(i)
                return
        raise AssertionError(f'类型 {key} 不在下拉')

    def test_enabled_only_for_hard_family(self, qapp):
        """`hard` 且 ssr scope 才启用；其余类型一律禁用（逐条遍历 `_PITY_TYPES`，
        故类型数增长时本表述无需跟着改）。"""
        panel = _make_panel()
        for key, _label in panel._PITY_TYPES:
            self._set_type(panel, key)
            want = (key == 'hard')
            assert panel.pity_target_featured_cb.isEnabled() is want, (
                f'{key} 的「仅限Featured卡」启用态应为 {want}')

    def test_switching_off_hard_clears_the_check(self, qapp):
        """先在 hard 上勾选、再切到 soft 时，勾选被清除且落盘为 False。

        这是审查实测的触达路径：切换类型不清勾选，等于把违规状态顺带带过去。
        """
        panel = _make_panel()
        self._set_type(panel, 'hard')
        panel.pity_target_featured_cb.setChecked(True)
        assert panel._pity_defs[0].get('target_featured') is True

        self._set_type(panel, 'soft_interval')
        assert panel.pity_target_featured_cb.isChecked() is False, '切到 soft 后勾选未清除'
        assert not panel._pity_defs[0].get('target_featured'), (
            '勾选残留被写进 _pity_defs，保存即产出 7B 违规配置')
        pity0 = panel.get_config()['pity']['pities'][0]
        assert not pity0.get('target_featured'), 'get_config 仍带 target_featured'
