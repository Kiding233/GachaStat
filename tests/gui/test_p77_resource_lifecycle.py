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
        """对齐卡池下拉不含永久池（与解析期校验同口径）。"""
        panel = _make_panel()
        permanent = {b.get('id') for b in panel._banner_defs if b.get('is_permanent')}
        options = {panel._lifecycle_banner_combo.itemText(i)
                   for i in range(panel._lifecycle_banner_combo.count())}
        assert not (permanent & options), "永久池不得出现在到期对齐下拉"

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
