"""P77 资源生命周期：GUI 数据流 round-trip 测试（§3.8 6d）。

覆盖：默认配置零生命周期规则、GUI 编辑后 apply_to_store 汇总、
get_config / set_config 顶层键往返、全局开关往返、永久池不进对齐下拉。
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


def _select_resource(panel, resource_id):
    """选中左列表中指定资源 id 的行，返回是否命中。"""
    for i, d in enumerate(panel.resource_defs):
        if d.get('resource_id') == resource_id:
            panel._resource_list.setCurrentRow(i)
            return True
    return False


# ══════════════════════════════════════════════════════════════════
# 默认配置零影响
# ══════════════════════════════════════════════════════════════════

class TestDefaults:
    def test_default_config_no_lifecycle_rules(self, qapp):
        """示例配置未启用生命周期段，规则为空且总闸默认勾选。"""
        panel = _make_panel()
        assert panel._store.resource_lifecycle.rules == []
        assert panel._lifecycle_enabled_cb.isChecked() is True

    def test_lifecycle_widgets_exist(self, qapp):
        """生命周期区域控件就绪（到期时刻/行为/比例/开关）。"""
        panel = _make_panel()
        assert panel._lifecycle_expire_mode.count() == 3
        assert panel._lifecycle_action_combo.count() == 3
        assert panel._lifecycle_from_spin.value() >= 1
        assert panel._lifecycle_to_spin.value() >= 1


# ══════════════════════════════════════════════════════════════════
# GUI 编辑 → apply_to_store 汇总
# ══════════════════════════════════════════════════════════════════

class TestApplyToStore:
    def test_banner_aligned_convert(self, qapp):
        """对齐卡池 + 非等额转换：apply_to_store 汇总为规则，天与比例正确。"""
        panel = _make_panel()
        assert _select_resource(panel, 'draw_resource')

        panel._lifecycle_expire_mode.setCurrentIndex(1)      # 对齐卡池
        assert panel._lifecycle_banner_combo.count() > 0
        panel._lifecycle_banner_combo.setCurrentIndex(0)
        banner_id = panel._lifecycle_banner_combo.currentText()

        panel._lifecycle_action_combo.setCurrentIndex(1)     # 转换到
        idx = panel._lifecycle_target_combo.findText('exchange_currency')
        assert idx >= 0
        panel._lifecycle_target_combo.setCurrentIndex(idx)
        panel._lifecycle_from_spin.setValue(3)
        panel._lifecycle_to_spin.setValue(2)
        panel.apply_to_store()

        rules = panel._store.resource_lifecycle.rules
        assert len(rules) == 1
        rule = rules[0]
        assert rule.resource_id == 'draw_resource'
        assert rule.expire_with_banner == banner_id
        assert rule.on_expire == {'convert_to': 'exchange_currency', 'from': 3, 'to': 2}

    def test_absolute_days_convert(self, qapp):
        """绝对时间：GUI 天 → store 秒换算正确。"""
        from gacha_simulator.core.config_store import DAY

        panel = _make_panel()
        assert _select_resource(panel, 'draw_resource')
        panel._lifecycle_expire_mode.setCurrentIndex(2)      # 绝对时间
        panel._lifecycle_days_spin.setValue(12.0)
        panel._lifecycle_action_combo.setCurrentIndex(2)     # 清零
        panel.apply_to_store()

        rule = panel._store.resource_lifecycle.rules[0]
        assert rule.expire_at == 12 * DAY
        assert rule.on_expire == {'clear': True}

    def test_no_rule_when_expire_mode_none(self, qapp):
        """到期时刻保持「永不过期」时不产生规则。"""
        panel = _make_panel()
        assert _select_resource(panel, 'draw_resource')
        panel._lifecycle_action_combo.setCurrentIndex(2)     # 仅设行为，未设到期时刻
        panel.apply_to_store()
        assert panel._store.resource_lifecycle.rules == []

    def test_disabled_flag_written(self, qapp):
        """总闸取消勾选：enabled=False 写入 store（规则保留）。"""
        panel = _make_panel()
        assert _select_resource(panel, 'draw_resource')
        panel._lifecycle_expire_mode.setCurrentIndex(2)
        panel._lifecycle_days_spin.setValue(5.0)
        panel._lifecycle_action_combo.setCurrentIndex(2)
        panel._lifecycle_enabled_cb.setChecked(False)
        panel.apply_to_store()

        assert panel._store.resource_lifecycle.enabled is False
        assert len(panel._store.resource_lifecycle.rules) == 1


# ══════════════════════════════════════════════════════════════════
# get_config / set_config 顶层键往返
# ══════════════════════════════════════════════════════════════════

class TestConfigDictRoundTrip:
    def test_get_config_carries_lifecycle(self, qapp):
        """get_config 输出顶层 resource_lifecycle 键（含 enabled 与规则）。"""
        panel = _make_panel()
        assert _select_resource(panel, 'draw_resource')
        panel._lifecycle_expire_mode.setCurrentIndex(2)
        panel._lifecycle_days_spin.setValue(7.0)
        panel._lifecycle_action_combo.setCurrentIndex(2)
        cfg = panel.get_config()

        assert 'resource_lifecycle' in cfg
        lc = cfg['resource_lifecycle']
        assert lc['enabled'] is True
        assert len(lc['rules']) == 1
        assert lc['rules'][0]['expire_at'] == 7.0            # 天书写
        assert lc['rules'][0]['on_expire'] == {'clear': True}

    def test_set_config_restores_lifecycle(self, qapp):
        """set_config 恢复：写回 store 并刷新 GUI（天 → 秒）。"""
        from gacha_simulator.core.config_store import DAY

        panel = _make_panel()
        cfg = panel.get_config()
        cfg['resource_lifecycle'] = {
            'enabled': True,
            'rules': [{
                'resource_id': 'draw_resource',
                'expire_at': 9.0,
                'on_expire': {'convert_to': 'exchange_currency', 'from': 1, 'to': 1},
            }],
        }
        panel.set_config(cfg)

        rules = panel._store.resource_lifecycle.rules
        assert len(rules) == 1
        assert rules[0].resource_id == 'draw_resource'
        assert rules[0].expire_at == 9 * DAY
        assert rules[0].on_expire == {'convert_to': 'exchange_currency', 'from': 1, 'to': 1}

        # GUI 回填：选中该资源后控件反映恢复值
        assert _select_resource(panel, 'draw_resource')
        assert panel._lifecycle_expire_mode.currentIndex() == 2
        assert panel._lifecycle_days_spin.value() == 9.0

    def test_set_config_disabled(self, qapp):
        """set_config 恢复 enabled=False：总闸取消勾选。"""
        panel = _make_panel()
        cfg = panel.get_config()
        cfg['resource_lifecycle'] = {'enabled': False, 'rules': []}
        panel.set_config(cfg)
        assert panel._store.resource_lifecycle.enabled is False
        assert panel._lifecycle_enabled_cb.isChecked() is False

    def test_roundtrip_stable(self, qapp):
        """get_config → set_config → get_config：生命周期部分稳定。"""
        panel = _make_panel()
        assert _select_resource(panel, 'draw_resource')
        panel._lifecycle_expire_mode.setCurrentIndex(2)
        panel._lifecycle_days_spin.setValue(3.5)
        panel._lifecycle_action_combo.setCurrentIndex(1)
        idx = panel._lifecycle_target_combo.findText('exchange_currency')
        panel._lifecycle_target_combo.setCurrentIndex(idx)
        panel._lifecycle_from_spin.setValue(4)
        panel._lifecycle_to_spin.setValue(1)

        cfg1 = panel.get_config()
        panel.set_config(cfg1)
        cfg2 = panel.get_config()
        assert cfg1['resource_lifecycle'] == cfg2['resource_lifecycle']


# ══════════════════════════════════════════════════════════════════
# 下拉数据源口径
# ══════════════════════════════════════════════════════════════════

class TestComboSources:
    def test_banner_combo_excludes_permanent(self, qapp):
        """对齐卡池下拉含有限池、不含永久池（与解析期校验同口径）。

        注入显式的永久池与有限池，使断言非空集（默认配置无永久池，空集相交恒真）。
        """
        panel = _make_panel()
        panel._banner_defs.append({
            'id': 'zz_perm_banner', 'name': '永久池', 'enabled': True,
            'max_draws': None, 'available_from': 0.0, 'available_until': 10.0,
            'is_permanent': True, 'pools': [], 'lifecycle': [],
        })
        panel._banner_defs.append({
            'id': 'zz_finite_banner', 'name': '限时池', 'enabled': True,
            'max_draws': None, 'available_from': 0.0, 'available_until': 10.0,
            'is_permanent': False, 'pools': [], 'lifecycle': [],
        })
        panel._refresh_lifecycle_banner_combo()

        options = {panel._lifecycle_banner_combo.itemText(i)
                   for i in range(panel._lifecycle_banner_combo.count())}
        assert 'zz_finite_banner' in options, "有限池应可选"
        assert 'zz_perm_banner' not in options, "永久池不得出现在到期对齐下拉"

    def test_target_combo_lists_resources(self, qapp):
        """转换目标下拉列出全部已注册资源。"""
        panel = _make_panel()
        options = {panel._lifecycle_target_combo.itemText(i)
                   for i in range(panel._lifecycle_target_combo.count())}
        assert set(panel._get_resource_ids()) == options

    def test_target_combo_refreshes_on_resource_add(self, qapp):
        """资源新增后转换目标下拉同步刷新。"""
        panel = _make_panel()
        before = panel._lifecycle_target_combo.count()
        panel.resource_defs.append({'resource_id': 'new_coin', 'display_name': '新币',
                                    'initial_amount': 0})
        panel._rebuild_resource_list()
        assert panel._lifecycle_target_combo.count() == before + 1
        options = {panel._lifecycle_target_combo.itemText(i)
                   for i in range(panel._lifecycle_target_combo.count())}
        assert 'new_coin' in options


# ══════════════════════════════════════════════════════════════════
# set_config 恢复路径的校验强度（与解析期同强度）
# ══════════════════════════════════════════════════════════════════

class TestSetConfigValidation:
    def _cfg_with_rule(self, panel, rule):
        cfg = panel.get_config()
        cfg['resource_lifecycle'] = {'enabled': True, 'rules': [rule]}
        return cfg

    def test_rejects_zero_from(self, qapp):
        """from=0 被拒（否则模拟期 divmod 除零崩溃）。"""
        from gacha_simulator.core.config_store import ConfigError

        panel = _make_panel()
        cfg = self._cfg_with_rule(panel, {
            'resource_id': 'draw_resource', 'expire_at': 10.0,
            'on_expire': {'convert_to': 'exchange_currency', 'from': 0, 'to': 1}})
        with pytest.raises(ConfigError):
            panel.set_config(cfg)

    def test_rejects_self_loop(self, qapp):
        """自环转换被拒。"""
        from gacha_simulator.core.config_store import ConfigError

        panel = _make_panel()
        cfg = self._cfg_with_rule(panel, {
            'resource_id': 'draw_resource', 'expire_at': 10.0,
            'on_expire': {'convert_to': 'draw_resource', 'from': 1, 'to': 1}})
        with pytest.raises(ConfigError):
            panel.set_config(cfg)

    def test_rejects_dangling_target(self, qapp):
        """转换目标未声明被拒（防 GUI 回填静默改写目标）。"""
        from gacha_simulator.core.config_store import ConfigError

        panel = _make_panel()
        cfg = self._cfg_with_rule(panel, {
            'resource_id': 'draw_resource', 'expire_at': 10.0,
            'on_expire': {'convert_to': 'ghost_target', 'from': 1, 'to': 1}})
        with pytest.raises(ConfigError):
            panel.set_config(cfg)

    def test_rejects_expire_mutex(self, qapp):
        """expire_at 与 expire_with_banner 同时给出被拒。"""
        from gacha_simulator.core.config_store import ConfigError

        panel = _make_panel()
        cfg = self._cfg_with_rule(panel, {
            'resource_id': 'draw_resource', 'expire_at': 10.0,
            'expire_with_banner': 'pool_c1',
            'on_expire': {'clear': True}})
        with pytest.raises(ConfigError):
            panel.set_config(cfg)


# ══════════════════════════════════════════════════════════════════
# 详情刷写与级联
# ══════════════════════════════════════════════════════════════════

class TestDetailFlushAndCascade:
    def test_row_switch_preserves_edit(self, qapp):
        """切换资源行再切回，生命周期编辑不丢失。"""
        panel = _make_panel()
        assert len(panel.resource_defs) >= 2
        panel._resource_list.setCurrentRow(0)
        panel._lifecycle_expire_mode.setCurrentIndex(2)
        panel._lifecycle_days_spin.setValue(6.0)
        panel._lifecycle_action_combo.setCurrentIndex(2)      # 清零

        panel._resource_list.setCurrentRow(1)
        panel._resource_list.setCurrentRow(0)

        assert panel._lifecycle_expire_mode.currentIndex() == 2
        assert panel._lifecycle_days_spin.value() == 6.0
        assert panel._lifecycle_action_combo.currentIndex() == 2

    def test_cascade_drops_rule_on_target_delete(self, qapp, monkeypatch):
        """转换目标资源被删除后，规则被静默级联过滤（不写出悬垂引用）。"""
        from PyQt6.QtWidgets import QMessageBox
        # 删除资源后 apply_to_store 会对 gain_rules/initial 里的悬垂引用弹模态警告，
        # 测试环境需屏蔽（否则阻塞等待用户点击）
        monkeypatch.setattr(QMessageBox, 'warning',
                            staticmethod(lambda *a, **k: None))

        panel = _make_panel()
        panel._resource_list.setCurrentRow(0)
        rid0 = panel.resource_defs[0]['resource_id']
        panel._lifecycle_expire_mode.setCurrentIndex(2)
        panel._lifecycle_days_spin.setValue(5.0)
        panel._lifecycle_action_combo.setCurrentIndex(1)      # 转换到
        idx = panel._lifecycle_target_combo.findText('exchange_currency')
        assert idx >= 0
        panel._lifecycle_target_combo.setCurrentIndex(idx)
        panel.apply_to_store()
        assert len(panel._store.resource_lifecycle.rules) == 1
        assert panel._store.resource_lifecycle.rules[0].resource_id == rid0

        # 删除目标资源后重新汇总：规则因悬垂目标被过滤
        panel.resource_defs = [d for d in panel.resource_defs
                               if d['resource_id'] != 'exchange_currency']
        panel._rebuild_resource_list()
        panel.apply_to_store()
        assert panel._store.resource_lifecycle.rules == []

    def test_cascade_drops_rule_on_source_delete(self, qapp, monkeypatch):
        """源资源被删除后，其生命周期规则一并消失。"""
        from PyQt6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, 'warning',
                            staticmethod(lambda *a, **k: None))

        panel = _make_panel()
        panel._resource_list.setCurrentRow(0)
        rid0 = panel.resource_defs[0]['resource_id']
        panel._lifecycle_expire_mode.setCurrentIndex(2)
        panel._lifecycle_days_spin.setValue(4.0)
        panel._lifecycle_action_combo.setCurrentIndex(2)
        panel.apply_to_store()
        assert len(panel._store.resource_lifecycle.rules) == 1

        panel.resource_defs = [d for d in panel.resource_defs
                               if d['resource_id'] != rid0]
        panel._rebuild_resource_list()
        panel.apply_to_store()
        assert panel._store.resource_lifecycle.rules == []

    def test_rename_target_rewrites_referencing_rule(self, qapp, monkeypatch):
        """重命名被引用资源后，引用方的转换目标同步改写（规则不因悬垂丢失）。

        计划 §3.6 要求重命名时「同步改写旧 id」；若只做删除语义的静默过滤，
        用户重命名一个被引用的资源会连带丢掉别的资源的转换规则。
        """
        from PyQt6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, 'warning',
                            staticmethod(lambda *a, **k: None))

        panel = _make_panel()
        panel._resource_list.setCurrentRow(0)
        panel._lifecycle_expire_mode.setCurrentIndex(2)
        panel._lifecycle_days_spin.setValue(5.0)
        panel._lifecycle_action_combo.setCurrentIndex(1)      # 转换到
        idx = panel._lifecycle_target_combo.findText('exchange_currency')
        assert idx >= 0
        panel._lifecycle_target_combo.setCurrentIndex(idx)
        panel.apply_to_store()
        assert (panel._store.resource_lifecycle.rules[0].on_expire['convert_to']
                == 'exchange_currency')

        # 重命名被引用的资源
        target_row = next(i for i, d in enumerate(panel.resource_defs)
                          if d['resource_id'] == 'exchange_currency')
        panel._resource_list.setCurrentRow(target_row)
        panel._resource_id_edit.setText('renamed_currency')
        panel._flush_resource_detail()
        panel.apply_to_store()

        rules = panel._store.resource_lifecycle.rules
        assert len(rules) == 1, "重命名不应丢失引用方的规则"
        assert rules[0].on_expire['convert_to'] == 'renamed_currency'


# ══════════════════════════════════════════════════════════════════
# 键空间互通：顶层（config dict）与嵌套（TOML 段）
# ══════════════════════════════════════════════════════════════════
class TestKeySpaceInterop:
    def test_nested_and_top_key_roundtrip(self, qapp, tmp_path):
        """同一规则经顶层键与嵌套键两条路径往返一致。

        顶层路径：get_config/set_config 用 `resource_lifecycle` 键；
        嵌套路径：save_toml/load_toml 用 `data['resources']['lifecycle']`。
        计划 §3.8 6b 要求两路径均一致且互通。
        """
        import os

        from gacha_simulator.core.config_toml import load_toml, save_toml

        panel = _make_panel()

        # 顶层键写入
        cfg = panel.get_config()
        cfg['resource_lifecycle'] = {
            'enabled': True,
            'rules': [{'resource_id': 'draw_resource', 'expire_at': 3.0,
                       'on_expire': {'convert_to': 'exchange_currency',
                                     'from': 2, 'to': 1}}],
        }
        panel.set_config(cfg)
        assert len(panel._store.resource_lifecycle.rules) == 1

        # 顶层键读回
        top_rules = panel.get_config()['resource_lifecycle']['rules']
        assert top_rules[0]['resource_id'] == 'draw_resource'
        assert top_rules[0]['on_expire'] == {'convert_to': 'exchange_currency',
                                             'from': 2, 'to': 1}

        # 嵌套键写盘并读回
        path = os.path.join(str(tmp_path), 'interop.toml')
        save_toml(panel._store, path)
        with open(path, encoding='utf-8') as f:
            text = f.read()
        assert '[resources.lifecycle]' in text, "应写出嵌套段"

        store2 = load_toml(path)
        r0 = panel._store.resource_lifecycle.rules[0]
        r1 = store2.resource_lifecycle.rules[0]
        assert (r1.resource_id, r1.expire_at, r1.on_expire) == \
            (r0.resource_id, r0.expire_at, r0.on_expire)
        assert r1.expire_at == 3 * 86400, "天到秒换算在两路径间应一致"


class TestBannerRenameCascade:
    def test_rename_banner_rewrites_alignment_reference(self, qapp, monkeypatch):
        """重命名被对齐的 banner 后，生命周期规则的到期对齐目标同步改写。

        banner id 可编辑（banner_id_edit），不改写则该规则因 banner 悬垂在
        apply_to_store 重建时被静默过滤（重命名 banner 即丢失引用它的规则）。
        """
        from PyQt6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, 'warning',
                            staticmethod(lambda *a, **k: None))

        panel = _make_panel()
        panel._resource_list.setCurrentRow(0)
        panel._lifecycle_expire_mode.setCurrentIndex(1)          # 随卡池下架
        assert panel._lifecycle_banner_combo.count() > 0, "默认配置应有可对齐的 banner"
        target_bid = panel._lifecycle_banner_combo.itemText(0)
        panel._lifecycle_banner_combo.setCurrentIndex(0)
        panel._lifecycle_action_combo.setCurrentIndex(2)         # 清零
        panel.apply_to_store()
        assert (panel._store.resource_lifecycle.rules[0].expire_with_banner
                == target_bid)

        # 在 banner 列表选中该 banner 并重命名
        brow = next(i for i, b in enumerate(panel._banner_defs)
                    if b.get('id') == target_bid)
        panel._on_banner_selected(brow)
        panel.banner_id_edit.setText('renamed_banner_x')
        panel._flush_banner_current_detail()
        panel.apply_to_store()

        rules = panel._store.resource_lifecycle.rules
        assert len(rules) == 1, "重命名 banner 不应丢失引用它的规则"
        assert rules[0].expire_with_banner == 'renamed_banner_x'
