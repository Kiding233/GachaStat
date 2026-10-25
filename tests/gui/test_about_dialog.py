"""P64 S9-3：「关于」页两处文本与 `BEHAVIOR_REGISTRY` 同源（§3.10.4 配套第 4 条）。

**被测面**：`gui/about_dialog.py` 的「关于」页「保底机制」条目与「配置文件指南」页
`[[pity]]` 示例的 `type = "..."` 注释行。两处**改前是硬编码**（前者只列 4 种、后者只列
6 种，P56 交付的 6 种事件驱动型与 S6a 的 G1 至今未登记），**改后由 registry 生成**：
新增 type 随 `display_name` / 键自动进入本页，单一真相源（硬编码列表已漂移过一次，
而「声明与承接分居两处」是本计划审查中出现频率最高的缺陷形态）。

**两处同源不同形**：关于页用 `display_name`（供人阅读），配置指南用 registry **键**
（该行是给用户抄写的合法 `type` 取值，显示名不是合法取值）。

**版式不在被测面内**：本步只改文本来源，不改页面结构（§3.10.4 配套第 4 条）。
"""


import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

import pytest  # noqa: E402

_TAB_ABOUT = 0
_TAB_CONFIG_GUIDE = 2


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def _dialog_texts(qapp):
    """构造一次 `AboutDialog`，返回 `{tab 下标: 纯文本}`（`toPlainText` 抗 HTML 重排）。

    用纯文本而非 `toHtml()`：后者经 Qt 的 HTML 规范化（重排、实体化），对「子串是否
    原样出现」的断言不稳定；本步要验的是文本内容而非标记。
    """
    from PyQt6.QtWidgets import QTabWidget, QTextBrowser

    from gacha_simulator.gui.about_dialog import AboutDialog

    dialog = AboutDialog()
    tabs = dialog.findChild(QTabWidget)
    assert tabs is not None, 'AboutDialog 内未找到 QTabWidget（页面结构变了？）'
    out = {}
    for i in range(tabs.count()):
        browser = tabs.widget(i).findChild(QTextBrowser)
        out[i] = browser.toPlainText() if browser is not None else ''
    dialog.deleteLater()
    return out


class TestAboutPageRegistrySource:
    """「关于」页「保底机制」条目由 `BEHAVIOR_REGISTRY` 的 `display_name` 生成。"""

    def test_about_tab_lists_all_registry_display_names(self, qapp):
        """全部 `display_name` **按 registry 顺序**出现（含 G3 的两个形态）。

        判别性：改前该条目硬编码 4 种，`rotating` / `targeted` 等 9 条的显示名一条
        都不在其中，故「退回硬编码」本用例必红。断言**拼接串**而非逐名包含：
        显示名互为子串（「硬保底」是「硬保底·排除已获得（…）」的前缀），逐名包含
        在硬编码形态下也可能假通过。
        """
        from gacha_simulator.core.pity import BEHAVIOR_REGISTRY

        want = ' / '.join(v['display_name'] for v in BEHAVIOR_REGISTRY.values())
        assert want in _dialog_texts(qapp)[_TAB_ABOUT]

    def test_both_g3_forms_annotated_in_about_tab(self, qapp):
        """G3 两个形态的**括注均须出现**（§3.10.4 的命名口径，两条不得同名）。

        这是「形态写进 `display_name`」在用户可见面上的唯一承载点：两条只差一个字的
        短名会让用户读不出自己选的是哪一种退化行为。
        """
        text = _dialog_texts(qapp)[_TAB_ABOUT]
        assert '全拥有时保底不触发' in text
        assert '全拥有时仍给一件 UP' in text

    def test_no_placeholder_left_in_about_tab(self, qapp):
        """占位符已被替换（防「忘了调 `_fill_registry_slots`」）。"""
        from gacha_simulator.gui.about_dialog import _PITY_NAMES_SLOT

        assert _PITY_NAMES_SLOT not in _dialog_texts(qapp)[_TAB_ABOUT]


class TestConfigGuideRegistrySource:
    """配置指南的 `type = "..."` 注释行由 `BEHAVIOR_REGISTRY` 的**键**生成。"""

    def test_config_guide_lists_all_registry_keys(self, qapp):
        """全部 btype **按 registry 顺序**出现在合法取值清单里。

        **用键而非 `display_name`**：该行是给用户抄写的 `type` 取值，显示名不是合法
        取值。判别性同上一组：改前只列 6 种（`hard_exclude_owned_*` / `rotating_inverse`
        等 7 条不在其中），退回硬编码即必红。
        """
        from gacha_simulator.core.pity import BEHAVIOR_REGISTRY

        want = ' | '.join(BEHAVIOR_REGISTRY)
        assert want in _dialog_texts(qapp)[_TAB_CONFIG_GUIDE]

    def test_no_placeholder_left_in_config_guide(self, qapp):
        """占位符已被替换。"""
        from gacha_simulator.gui.about_dialog import _PITY_KEYS_SLOT

        assert _PITY_KEYS_SLOT not in _dialog_texts(qapp)[_TAB_CONFIG_GUIDE]


class TestRegistryTextHelpers:
    """两个生成函数的本体（不经 Qt 的直调面）。"""

    def test_display_names_join_all_entries_in_order(self):
        from gacha_simulator.core.pity import BEHAVIOR_REGISTRY
        from gacha_simulator.gui.about_dialog import _pity_display_names

        assert _pity_display_names() == \
            ' / '.join(v['display_name'] for v in BEHAVIOR_REGISTRY.values())

    def test_type_keys_join_all_entries_in_order(self):
        from gacha_simulator.core.pity import BEHAVIOR_REGISTRY
        from gacha_simulator.gui.about_dialog import _pity_type_keys

        assert _pity_type_keys() == ' | '.join(BEHAVIOR_REGISTRY)

    def test_fill_slots_replaces_both_and_leaves_rest_untouched(self):
        """替换只动两个占位符，其余内容**逐字保留**（含 TOML 示例里的花括号）。

        花括号是本步**没有**改用 f-string 的原因：配置指南的字面量里有
        `gains = { draw_resource = 100 }` 与 `{banner_id}.{pool_id}`，改 f-string 需
        逐个双写，写漏即静默改掉页面文字。占位符替换把该风险面压到零。
        """
        from gacha_simulator.gui.about_dialog import (
            _PITY_KEYS_SLOT, _PITY_NAMES_SLOT, _fill_registry_slots,
            _pity_display_names, _pity_type_keys,
        )

        html = (f'<pre>gains = {{ draw_resource = 100 }}</pre>'
                f'[{_PITY_NAMES_SLOT}][{_PITY_KEYS_SLOT}]')
        out = _fill_registry_slots(html)
        assert out == ('<pre>gains = { draw_resource = 100 }</pre>'
                       f'[{_pity_display_names()}][{_pity_type_keys()}]')
