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
        # P64 S7a（ISSUE-918）：别名键 `type` 已废弃，输出改用字段名 `btype`。
        assert "btype" in pdef
        assert "type" not in pdef, "别名键 type 仍在输出中（改名未完成）"
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
        assert entry['btype'] in BEHAVIOR_REGISTRY, (
            f"兜底条目 btype='{entry['btype']}' 不在 BEHAVIOR_REGISTRY 内")
        assert entry['reset'] in _reset_whitelist(), (
            f"兜底条目 reset='{entry['reset']}' 不在 G16 白名单内")

    def test_fallback_entry_start_end_from_pity_section(self, qapp):
        """soft_start / soft_end 取自 pity.start / pity.end（不再走嵌套 params）。

        **注**：`pity.start` / `pity.end`（**段级**键）与保底**条目级**的四个别名键
        `type` / `start` / `end` / `increment`（S7a 已改名为字段名）是两回事：段级
        键没有任何写出方（`get_config` 的 pity 段只输出 `enabled` / `pities`），只
        作兜底条目的阈值来源，故不在 S7a 的改名面内。条目级键已全部改为字段名，
        断言随之取 `soft_start` / `soft_end`。
        """
        panel = _make_panel()
        panel.set_config({'pity': {'pities': [], 'start': 62, 'end': 88}})
        entry = panel.get_config()['pity']['pities'][0]
        assert (entry['soft_start'], entry['soft_end']) == (62, 88)

    def test_fallback_entry_start_end_platform_default(self, qapp):
        """pity 段未给 start/end 时落平台默认 74 / 90（原嵌套 params 下两者都丢）。"""
        panel = _make_panel()
        panel.set_config({'pity': {'pities': []}})
        entry = panel.get_config()['pity']['pities'][0]
        assert (entry['soft_start'], entry['soft_end']) == (74, 90)

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


# ═══════════════════════════════════════════════════════════════════
# P64 S6b（G5）：`priority` 的 GUI 往返（§六 G5 验收第三项）
# ═══════════════════════════════════════════════════════════════════

class TestPriorityRoundTrip:
    """TOML 写非默认 `priority` → GUI 加载 → 直接保存 → 重读 TOML 仍为原值。

    本用例是 GUI 逐字段键表（`_refresh_from_store_impl` 读侧 / `apply_to_store`
    写侧 / `set_config` 字典侧 / `get_config` 输出侧）漏改 `priority` 的**唯一
    显形面**：漏改不报错、保存时静默落回默认 0（手写的 priority 被抹掉）。
    链路上任一环缺该键，本用例即红。
    """

    def _panel_from_toml(self, path):
        from gacha_simulator.core.config_toml import load_toml
        from gacha_simulator.gui.config_panel import ConfigPanel

        store = load_toml(str(path))
        panel = ConfigPanel()
        panel._store = store
        panel._refresh_from_store_impl()
        return panel

    def test_priority_survives_gui_round_trip(self, qapp, tmp_path):
        from gacha_simulator.core.config_toml import load_toml, save_toml

        # 1) 造一份带非默认 priority 的 TOML（真实写盘路径产出）
        seeded = load_toml(_CONFIG_TOML)
        seeded.pity.pities[0].priority = 7
        toml_in = tmp_path / 'in.toml'
        save_toml(seeded, str(toml_in))
        assert 'priority = 7' in toml_in.read_text(encoding='utf-8'), (
            '前置条件不成立：输入 TOML 未带非默认 priority')

        # 2) GUI 加载：内存态与控件都必须拿到 7
        panel = self._panel_from_toml(toml_in)
        assert panel._pity_defs[0]['priority'] == 7, (
            '读侧字段表（_refresh_from_store_impl）未透传 priority')
        panel.pity_list.setCurrentRow(0)
        assert panel.pity_priority_spin.value() == 7, (
            '控件未回填 priority，用户看到的是 0，保存即抹掉原值')

        # 3) 不做任何编辑，直接保存
        panel.apply_to_store()
        assert panel._store.pity.pities[0].priority == 7, (
            '写侧字段表（apply_to_store）未透传 priority')
        toml_out = tmp_path / 'out.toml'
        save_toml(panel._store, str(toml_out))

        # 4) 重读 TOML：键仍为原值
        reloaded = load_toml(str(toml_out))
        assert reloaded.pity.pities[0].priority == 7

    def test_set_config_get_config_carry_priority(self, qapp):
        """字典侧往返（`set_config` → `get_config`）：同样不得丢 priority。

        钉住两处独立于上一条（读 / 写侧字段表）的接线：
        ① `set_config` 的 `PityDef(...)` 构造（config dict → store）；② `get_config`
        的输出 dict（导出 / 预览面）。
        **注意**：`set_config` 的 `_pity_defs` 字段表**不在**本用例的判别面上——
        `set_config` 结尾调用 `refresh_from_store()`，`_pity_defs` 随即被
        `_refresh_from_store_impl` 按 store 重建（实测：删掉该表里的 `priority`
        本用例仍绿，判别力只来自上面两处）。该表照样补键，是为与 S7a 的
        dataclass 驱动改造同形、且防将来去掉那次 refresh。
        """
        panel = _make_panel()
        config = panel.get_config()
        config['pity']['pities'][0]['priority'] = 9
        panel.set_config(config)
        assert panel._pity_defs[0]['priority'] == 9, (
            'set_config 的字段表未透传 priority')
        assert panel.get_config()['pity']['pities'][0]['priority'] == 9, (
            'get_config 的输出未带 priority')

    def test_edited_priority_is_saved(self, qapp, tmp_path):
        """编辑控件 → 保存 → 重读 TOML 为新值（S6b 审查 F3）。

        **为什么必须单独一条**：本类其余用例全是「加载后**不编辑**直接保存」，
        故 `_flush_pity_current_detail` 的写回、`_apply_pity_edit` 的写回、
        `pity_priority_spin.valueChanged` 的连线**任一被删都无人报警**（审查实测：
        三处各删一次，59 条用例全绿）。而这三处恰是 S7a 结构性改造要动的面，
        缺本断言则改造致坏时无信号。

        取值用 **-4**：同时覆盖「负值经编辑路径不被夹」这一面（与
        `test_negative_priority_not_clamped_by_spinbox` 的加载路径互补）。
        """
        from gacha_simulator.core.config_toml import load_toml, save_toml

        seeded = load_toml(_CONFIG_TOML)
        toml_in = tmp_path / 'in.toml'
        save_toml(seeded, str(toml_in))

        panel = self._panel_from_toml(toml_in)
        panel.pity_list.setCurrentRow(0)
        assert panel.pity_priority_spin.value() == 0, '前置：示例配置首条为默认值'

        # 走真实用户路径：setValue 触发 valueChanged → _flush_pity_current_detail
        panel.pity_priority_spin.setValue(-4)
        assert panel._pity_defs[0]['priority'] == -4, (
            '控件 valueChanged 未连到 flush，或该 flush 未写回 priority')

        panel.apply_to_store()
        assert panel._store.pity.pities[0].priority == -4, (
            'apply_to_store 未透传 priority')
        toml_out = tmp_path / 'out.toml'
        save_toml(panel._store, str(toml_out))
        assert load_toml(str(toml_out)).pity.pities[0].priority == -4, (
            '编辑值未落盘')

    def test_negative_priority_not_clamped_by_spinbox(self, qapp, tmp_path):
        """控件量程须容纳负值：否则 TOML 里的负 priority 经「加载 → 保存」被夹到 0。

        `setValue` 对超量程值是**静默夹取**（不报错），故这是一条无报错的数据损坏路径：
        量程收成 0..N 即必红。
        """
        from gacha_simulator.core.config_toml import load_toml, save_toml

        seeded = load_toml(_CONFIG_TOML)
        seeded.pity.pities[0].priority = -3
        toml_in = tmp_path / 'in.toml'
        save_toml(seeded, str(toml_in))
        panel = self._panel_from_toml(toml_in)
        panel.pity_list.setCurrentRow(0)
        assert panel.pity_priority_spin.value() == -3, '负 priority 被控件夹住'
        panel.apply_to_store()
        toml_out = tmp_path / 'out.toml'
        save_toml(panel._store, str(toml_out))
        assert load_toml(str(toml_out)).pity.pities[0].priority == -3

    def test_row_switch_does_not_clobber_priority(self, qapp, tmp_path):
        """切换条目不得把本条目的 `priority` 写成上一条的残留值。

        机制：`_on_pity_selected` 中任一后续控件的 `setValue` / `setChecked` 都会触发
        `_flush_pity_current_detail`，而该 flush 从**全部**控件读值写回本条目；
        priority 控件若尚未回填，本条目的值即被上一条的残留值覆盖，保存即固化。
        故回填须排在其他控件之前（本用例是该排布的**唯一显形面**：
        排到后面时无任何报错，只是静默改写两条保底的配置）。
        """
        import copy

        from gacha_simulator.core.config_toml import load_toml, save_toml

        seeded = load_toml(_CONFIG_TOML)
        first = seeded.pity.pities[0]
        first.priority = 7
        second = copy.deepcopy(first)
        second.name = 'second_pity'
        second.priority = 0
        # 让 counter_init 两行取值不同：它保证切换时确有控件发出变更信号，
        # 即真正走到「flush 从全部控件读值」这一步（否则本用例无判别力）
        second.counter_init = 5
        seeded.pity.pities.append(second)

        toml_in = tmp_path / 'two_pities.toml'
        save_toml(seeded, str(toml_in))
        panel = self._panel_from_toml(toml_in)
        assert panel.pity_list.count() == 2

        panel.pity_list.setCurrentRow(0)
        assert panel.pity_priority_spin.value() == 7
        panel.pity_list.setCurrentRow(1)
        assert panel._pity_defs[1]['priority'] == 0, (
            '切到第 2 条时其 priority 被上一条的 7 覆盖（控件回填排在了其他控件之后）')
        assert panel.pity_priority_spin.value() == 0
        panel.pity_list.setCurrentRow(0)
        assert panel._pity_defs[0]['priority'] == 7

        panel.apply_to_store()
        toml_out = tmp_path / 'two_pities_out.toml'
        save_toml(panel._store, str(toml_out))
        reloaded = load_toml(str(toml_out))
        assert [p.priority for p in reloaded.pity.pities] == [7, 0]


# ═══════════════════════════════════════════════════════════════════
# P64 S7a：五处字段键表改造的验收面
# ═══════════════════════════════════════════════════════════════════

class TestS7aFieldKeyTables:
    """`dataclasses.fields(PityDef)` 驱动的键表：下拉验收 + 预览不打印 `?`。"""

    def test_pity_type_dropdown_offers_registry_types(self, qapp):
        """新 type 自动出现在保底 type 下拉（S6a 生成式改造的验收）。

        与 `tests/gui/test_config_panel_p56.py::test_s6a_rotating_inverse_auto_appears`
        同源（那一条是 S6a 的落地面），此处按 §七 S7a 的验收命令再钉一次：断言取
        下拉的**实际条目文本集合**，故「registry 有、下拉没 addItems」也红。
        """
        from gacha_simulator.core.pity import BEHAVIOR_REGISTRY

        panel = _make_panel()
        items = {panel.pity_type_combo.itemText(i)
                 for i in range(panel.pity_type_combo.count())}
        assert items == {v['display_name'] for v in BEHAVIOR_REGISTRY.values()}

    def test_preview_shows_pity_type_not_question_mark(self, qapp):
        """`_do_update_preview` 的保底段须打印真实类型（P64 S7a / ISSUE-918）。

        `get_config` 的输出自 S7a 起用字段名 `btype`（原别名 `type`）。同文件的
        `_do_update_preview` 若仍读 `pdef.get('type', '?')`，**不报错**，只是每条
        保底都打印 `?`；而 `preview_text` 全库无断言，属静默失真。
        """
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        panel._do_update_preview()

        text = panel.preview_text.text()
        btype = panel._pity_defs[0]['btype']
        assert f": {btype}(" in text, (
            f"预览未打印保底类型（预期 {btype}）。实际预览：\n{text}")
        assert ": ?(" not in text, f"预览把保底类型打印成了 ?：\n{text}"


class TestMaxTriggersRoundTrip:
    """`max_triggers`（ISSUE-032，S7a 新建控件）的 GUI 往返。

    与 `TestPriorityRoundTrip` 同形：TOML 写非默认值 → GUI 加载 → 直接保存 →
    重读 TOML 仍为原值。该用例是五处字段表漏改 `max_triggers` 的唯一显形面
    （漏改不报错，保存时静默落回默认 0）。
    """

    def _panel_from_toml(self, path):
        from gacha_simulator.core.config_toml import load_toml
        from gacha_simulator.gui.config_panel import ConfigPanel

        store = load_toml(str(path))
        panel = ConfigPanel()
        panel._store = store
        panel._refresh_from_store_impl()
        return panel

    def test_max_triggers_survives_gui_round_trip(self, qapp, tmp_path):
        from gacha_simulator.core.config_toml import load_toml, save_toml

        seeded = load_toml(_CONFIG_TOML)
        seeded.pity.pities[0].max_triggers = 3
        toml_in = tmp_path / 'in.toml'
        save_toml(seeded, str(toml_in))
        assert 'max_triggers = 3' in toml_in.read_text(encoding='utf-8'), (
            '前置条件不成立：输入 TOML 未带非默认 max_triggers')

        panel = self._panel_from_toml(toml_in)
        assert panel._pity_defs[0]['max_triggers'] == 3, (
            '读侧字段表（_refresh_from_store_impl）未透传 max_triggers')
        panel.pity_list.setCurrentRow(0)
        assert panel.pity_max_triggers_spin.value() == 3, (
            '控件未回填 max_triggers，用户看到的是 0，保存即抹掉原值')

        panel.apply_to_store()
        assert panel._store.pity.pities[0].max_triggers == 3, (
            '写侧字段表（apply_to_store）未透传 max_triggers')
        toml_out = tmp_path / 'out.toml'
        save_toml(panel._store, str(toml_out))
        assert load_toml(str(toml_out)).pity.pities[0].max_triggers == 3

    def test_set_config_get_config_carry_max_triggers(self, qapp):
        """字典侧往返（`set_config` → `get_config`）不得丢 `max_triggers`。"""
        panel = _make_panel()
        config = panel.get_config()
        config['pity']['pities'][0]['max_triggers'] = 5
        panel.set_config(config)
        assert panel._pity_defs[0]['max_triggers'] == 5, (
            'set_config 的字段表未透传 max_triggers')
        assert panel.get_config()['pity']['pities'][0]['max_triggers'] == 5, (
            'get_config 的输出未带 max_triggers')

    def test_edited_max_triggers_is_saved(self, qapp, tmp_path):
        """编辑控件 → 保存 → 重读 TOML 为新值。

        本类其余用例都是「加载后不编辑直接保存」，故
        `pity_max_triggers_spin.valueChanged` 的连线与
        `_flush_pity_current_detail` 的写回**任一被删都无人报警**，须单独钉一条。
        """
        from gacha_simulator.core.config_toml import load_toml, save_toml

        seeded = load_toml(_CONFIG_TOML)
        toml_in = tmp_path / 'in.toml'
        save_toml(seeded, str(toml_in))

        panel = self._panel_from_toml(toml_in)
        panel.pity_list.setCurrentRow(0)
        assert panel.pity_max_triggers_spin.value() == 0, '前置：示例配置首条为默认值'

        panel.pity_max_triggers_spin.setValue(4)
        assert panel._pity_defs[0]['max_triggers'] == 4, (
            '控件 valueChanged 未连到 flush，或该 flush 未写回 max_triggers')

        panel.apply_to_store()
        assert panel._store.pity.pities[0].max_triggers == 4, (
            'apply_to_store 未透传 max_triggers')
        toml_out = tmp_path / 'out.toml'
        save_toml(panel._store, str(toml_out))
        assert load_toml(str(toml_out)).pity.pities[0].max_triggers == 4, (
            '编辑值未落盘')

    def test_max_triggers_spin_excludes_negative(self, qapp):
        """控件量程不含负值：负值被 `_build_pity` 硬拒，控件给出即「保存能过、重载报错」。"""
        panel = _make_panel()
        assert panel.pity_max_triggers_spin.minimum() == 0


class TestPityDetailBackfillIsolation:
    """条目切换（含首次加载）不得把上一条的初始状态字段写进当前条（P64 S7a）。

    缺陷（S6b 独立审查复现，S7a 结构性修复）：`_on_pity_selected` 的回填途中任一
    控件的 setText / setValue / setChecked 都会触发 `_flush_pity_current_detail`，
    该 flush 从**全部**控件读值写回**本条**，而本条正是回填此刻正在读取的那个
    dict。于是尚未回填的控件把**上一条的残留值**写进当前条，当前条后续的回填再从
    **已被污染**的 dict 取值（取到的值与控件现值相同，故不再发信号），污染就此
    固化并落盘，全程无任何报错。

    被污染的字段实测为 counter_init / guaranteed_init / fate_points_init /
    deactivate_on_early_hit 四个初始状态字段。本类是该修复的唯一显形面：去掉
    `_pity_detail_backfilling` 标志位（即回填期不阻断信号）两条用例即红。
    """

    _FIELDS = ('counter_init', 'guaranteed_init', 'fate_points_init',
               'deactivate_on_early_hit')

    def _two_pities_panel(self, tmp_path):
        """两条保底、四个初始状态字段取互不相同的非默认值，返回面板与输入 TOML。"""
        import copy

        from gacha_simulator.core.config_toml import load_toml, save_toml
        from gacha_simulator.gui.config_panel import ConfigPanel

        seeded = load_toml(_CONFIG_TOML)
        first = seeded.pity.pities[0]
        first.counter_init = 7
        first.guaranteed_init = True
        first.fate_points_init = 4
        first.deactivate_on_early_hit = True
        second = copy.deepcopy(first)
        second.name = 'second_pity'
        second.counter_init = 2
        second.guaranteed_init = False
        second.fate_points_init = 1
        second.deactivate_on_early_hit = False
        seeded.pity.pities.append(second)
        toml_in = tmp_path / 'two_pities.toml'
        save_toml(seeded, str(toml_in))

        store = load_toml(str(toml_in))
        panel = ConfigPanel()
        panel._store = store
        panel._refresh_from_store_impl()
        return panel, toml_in

    @classmethod
    def _snapshot(cls, pd):
        return {k: pd[k] for k in cls._FIELDS}

    def test_first_load_keeps_selected_row_init_fields(self, qapp, tmp_path):
        """首次加载（`_refresh_from_store_impl` 内部选中第 0 条）即不得污染。"""
        panel, _ = self._two_pities_panel(tmp_path)
        assert self._snapshot(panel._pity_defs[0]) == {
            'counter_init': 7, 'guaranteed_init': True,
            'fate_points_init': 4, 'deactivate_on_early_hit': True}

    def test_row_switch_keeps_current_row_init_fields(self, qapp, tmp_path):
        """切到第 2 条后其四个字段仍是自身取值，并活过保存与重读 TOML。"""
        from gacha_simulator.core.config_toml import load_toml, save_toml

        panel, _ = self._two_pities_panel(tmp_path)
        assert panel.pity_list.count() == 2
        panel.pity_list.setCurrentRow(0)
        panel.pity_list.setCurrentRow(1)

        assert self._snapshot(panel._pity_defs[1]) == {
            'counter_init': 2, 'guaranteed_init': False,
            'fate_points_init': 1, 'deactivate_on_early_hit': False}

        panel.apply_to_store()
        saved = panel._store.pity.pities[1]
        assert (saved.counter_init, saved.guaranteed_init,
                saved.fate_points_init, saved.deactivate_on_early_hit) == (
                    2, False, 1, False)
        toml_out = tmp_path / 'two_pities_out.toml'
        save_toml(panel._store, str(toml_out))
        reloaded = load_toml(str(toml_out)).pity.pities[1]
        assert (reloaded.counter_init, reloaded.guaranteed_init,
                reloaded.fate_points_init, reloaded.deactivate_on_early_hit) == (
                    2, False, 1, False)


# ═══════════════════════════════════════════════════════════════════
# P64 S7a 审查收口（F1 / F2 / F3 / F5）
# ═══════════════════════════════════════════════════════════════════

# F1 的两种 btype 参数面互不相同，故两条用例都按 btype 参数化：
#   targeted：fate_threshold(int) / switch_allowed(bool) / switch_resets_progress(bool)
#   rotating_cr：cr_counter_threshold(int) / cr_base_rate(float)
# 每个参数的注册表默认值都与用例取值不同，保证回填途中确有控件发出变更信号
# （若首个控件不发信号，flush 由后续控件触发，丢失面后移，用例仍应有判别力）。
_S7A_DYN_CASES = [
    ('targeted', {'fate_threshold': 2, 'switch_allowed': False,
                  'switch_resets_progress': False}),
    ('rotating_cr', {'cr_counter_threshold': 4, 'cr_base_rate': 12.0}),
]


def _two_pities_of_type(tmp_path, btype, row0_params, row1_params, tag):
    """两条同类型保底（第 1 条取 row0_params，第 2 条取 row1_params）→ 加载面板。"""
    from gacha_simulator.core.config_store import PityDef
    from gacha_simulator.core.config_toml import load_toml, save_toml
    from gacha_simulator.gui.config_panel import ConfigPanel

    seeded = load_toml(_CONFIG_TOML)
    seeded.pity.pities = [
        PityDef(name='dyn_a', btype=btype, scope='ssr', reset='', **row0_params),
        PityDef(name='dyn_b', btype=btype, scope='ssr', reset='', **row1_params),
    ]
    toml_in = tmp_path / f'{tag}.toml'
    save_toml(seeded, str(toml_in))

    store = load_toml(str(toml_in))
    panel = ConfigPanel()
    panel._store = store
    panel._refresh_from_store_impl()
    return panel, toml_in


class TestS7aTypeChangeBackfillIsolation:
    """F1：`_on_pity_type_changed` 的重建 + 回填也须落在标志位窗口内。

    缺陷（S7a 独立审查实测）：`_on_pity_selected` 只把 `_backfill_pity_detail`
    包进 `_pity_detail_backfilling` 窗口，紧随其后的 `_on_pity_type_changed` 末尾
    还会再 `_build_param_widgets()` 重建一次动态控件并从条目回填，而这段运行在
    标志位**已复位**之后。于是回填途中第一个控件发出的信号跑 flush，该 flush 从
    全部控件读值，尚未回填的控件把刚建的 registry 默认值写进条目，后续回填再从
    被改写的条目取值（值相同故不再发信号），默认值就此固化并落盘，全程无报错。
    实测丢失面：`targeted` 的 switch_allowed / switch_resets_progress 由 False 变
    True；`rotating_cr` 的 cr_base_rate 由 12.0 变 5.0。

    与 `TestPityDetailBackfillIsolation` 的分工：那一条管 `_backfill_pity_detail`
    读取的四个人工字段，本类管 `_on_pity_type_changed` 的 registry 动态参数面。
    """

    @pytest.mark.parametrize('btype,params', _S7A_DYN_CASES)
    def test_first_load_keeps_selected_row_dynamic_params(
            self, qapp, tmp_path, btype, params):
        """首次加载（`_refresh_from_store_impl` 内部选中第 0 条）即不得被默认值覆盖。"""
        panel, _ = _two_pities_of_type(tmp_path, btype, params, {}, f'first_{btype}')
        got = {k: panel._pity_defs[0][k] for k in params}
        assert got == params, (
            f'首次加载后第 1 条的 {btype} 动态参数被 registry 默认值覆盖：{got}')

    @pytest.mark.parametrize('btype,params', _S7A_DYN_CASES)
    def test_row_switch_keeps_current_row_dynamic_params(
            self, qapp, tmp_path, btype, params):
        """切到第 2 条后其动态参数仍是自身取值，并活过保存与重读 TOML。"""
        from gacha_simulator.core.config_toml import load_toml, save_toml

        panel, _ = _two_pities_of_type(tmp_path, btype, {}, params, f'switch_{btype}')
        assert panel.pity_list.count() == 2
        panel.pity_list.setCurrentRow(0)
        panel.pity_list.setCurrentRow(1)

        got = {k: panel._pity_defs[1][k] for k in params}
        assert got == params, (
            f'切到第 2 条后其 {btype} 动态参数被 registry 默认值覆盖：{got}')

        panel.apply_to_store()
        saved = {k: getattr(panel._store.pity.pities[1], k) for k in params}
        assert saved == params, f'默认值已写进 store：{saved}'
        toml_out = tmp_path / f'switch_{btype}_out.toml'
        save_toml(panel._store, str(toml_out))
        reloaded = {k: getattr(load_toml(str(toml_out)).pity.pities[1], k)
                    for k in params}
        assert reloaded == params, f'默认值已落盘：{reloaded}'


class TestS7aSelectedCardInitBackfill:
    """F2：`selected_card_init` 的回填须排在 combo 填充之后。

    缺陷（S7a 独立审查实测）：`_backfill_pity_detail` 对 `pity_selected_card_combo`
    的 `findData` 早于 `_populate_selected_card_combo()`（后者只在
    `_on_pity_type_changed` 末尾被调用）。combo 尚未填充时 `findData` 返回 -1，
    回填不改选，随后统一 flush 把 `currentData() or None`（即空）写进条目，
    `selected_card_init` 静默丢成 None 并落盘。同类的 `pity_depends_combo` /
    `pity_reset_combo` 都在 findData 前先填充，本处是唯一顺序颠倒的一处。
    """

    def _panel(self, tmp_path):
        from gacha_simulator.core.config_store import PityDef
        from gacha_simulator.core.config_toml import load_toml, save_toml
        from gacha_simulator.gui.config_panel import ConfigPanel

        seeded = load_toml(_CONFIG_TOML)
        seeded.banner.banners[0].pools[0].epitomizable_cards = [
            'limited_ssr_1', 'standard_ssr_1']
        seeded.pity.pities = [
            PityDef(name='tgt_a', btype='targeted', scope='ssr', reset='',
                    selected_card_init='limited_ssr_1', fate_points_init=1),
            PityDef(name='tgt_b', btype='targeted', scope='ssr', reset='',
                    selected_card_init='standard_ssr_1', fate_points_init=2),
        ]
        toml_in = tmp_path / 'two_targeted.toml'
        save_toml(seeded, str(toml_in))

        store = load_toml(str(toml_in))
        panel = ConfigPanel()
        panel._store = store
        panel._refresh_from_store_impl()
        return panel

    def test_selected_card_init_survives_load_save_reload(self, qapp, tmp_path):
        """两条 targeted 的 `selected_card_init` 经「加载 → 直接保存 → 重读」不丢。"""
        from gacha_simulator.core.config_toml import load_toml, save_toml

        panel = self._panel(tmp_path)
        assert [d['selected_card_init'] for d in panel._pity_defs] == [
            'limited_ssr_1', 'standard_ssr_1'], (
            '首个被选中的 targeted 条目把 selected_card_init 丢成了 None'
            '（combo 尚未填充时 findData 返回 -1，回填未改选）')

        panel.apply_to_store()
        assert [p.selected_card_init for p in panel._store.pity.pities] == [
            'limited_ssr_1', 'standard_ssr_1'], 'apply_to_store 未透传'
        toml_out = tmp_path / 'two_targeted_out.toml'
        save_toml(panel._store, str(toml_out))
        assert [p.selected_card_init
                for p in load_toml(str(toml_out)).pity.pities] == [
            'limited_ssr_1', 'standard_ssr_1'], 'selected_card_init 未落盘'


class TestS7aMaxTriggersRange:
    """F3：`max_triggers` 控件量程须与解析侧同口径（只设下界，无小上界）。

    解析侧（`config_toml._build_pity`）只拒 bool / 非 int / 负值，**无上界**。
    控件若收成 0..9999，TOML 里的大值经「加载 → 保存」被 `setValue` 静默夹取
    （不报错），与 priority 控件同一失效形态。
    """

    def test_large_max_triggers_not_clamped(self, qapp, tmp_path):
        from gacha_simulator.core.config_toml import load_toml, save_toml
        from gacha_simulator.gui.config_panel import ConfigPanel

        seeded = load_toml(_CONFIG_TOML)
        seeded.pity.pities[0].max_triggers = 50000
        toml_in = tmp_path / 'big_max_triggers.toml'
        save_toml(seeded, str(toml_in))
        assert 'max_triggers = 50000' in toml_in.read_text(encoding='utf-8'), (
            '前置条件不成立：输入 TOML 未带大值 max_triggers')

        store = load_toml(str(toml_in))
        panel = ConfigPanel()
        panel._store = store
        panel._refresh_from_store_impl()
        panel.pity_list.setCurrentRow(0)
        assert panel.pity_max_triggers_spin.value() == 50000, (
            '控件量程夹住了大值（setValue 静默夹取）')

        panel.apply_to_store()
        toml_out = tmp_path / 'big_max_triggers_out.toml'
        save_toml(panel._store, str(toml_out))
        assert load_toml(str(toml_out)).pity.pities[0].max_triggers == 50000, (
            '大值未落盘（被夹成控件上界）')


class TestS7aNestedLifecycleFieldPaths:
    """F5：`_PITY_NESTED_FIELD_PATHS`（`lifecycle` 嵌套两字段）的覆盖。

    该表把 config dict 的 `lifecycle.{deactivate_on_early_hit, depends_on}` 映回
    `PityDef` 的顶层字段。审查实测：置空该表后 tests/gui 全绿，即此前零覆盖
    （表本身工作正常，只是无断言）。
    """

    def test_set_config_reads_nested_lifecycle_fields(self, qapp):
        panel = _make_panel()
        config = panel.get_config()
        config['pity']['pities'][0]['lifecycle'] = {
            'deactivate_on_early_hit': True, 'depends_on': 'x'}
        panel.set_config(config)

        assert panel._pity_defs[0]['deactivate_on_early_hit'] is True, (
            'set_config 未从 lifecycle.deactivate_on_early_hit 读入 PityDef')
        assert panel._pity_defs[0]['depends_on'] == 'x', (
            'set_config 未从 lifecycle.depends_on 读入 PityDef')
        assert panel._store.pity.pities[0].depends_on == 'x'
