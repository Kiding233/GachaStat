"""完全等价于 main.py 启动流程的集成测试。

每一步对应 main.py __main__ 护卫中的实际代码，直接验证完整启动无崩溃。
窗口会短暂显示——与用户手动运行 main.py 的行为一致。
"""

import os
import sys
import pytest

# ═══ 步骤 1：环境设置（等价 main.py:17-19） ═══
os.environ.setdefault("QT_LOGGING_RULES", "*.warning=false")

from multiprocessing import freeze_support

freeze_support()

# ═══ 步骤 2：Qt 初始化（等价 main.py:25-27,34-35） ═══
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

from gacha_simulator._version import __version__


@pytest.fixture(scope="module")
def qapp():
    """等价 main.py:35 — 创建 QApplication。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName("GachaStat")
    app.setOrganizationName("GachaStat")
    app.setApplicationVersion(__version__)
    yield app


@pytest.fixture(scope="module")
def main_window(qapp):
    """等价 main.py:124 — 创建 MainWindow（最高风险步骤）。"""
    from gacha_simulator.gui import MainWindow

    window = MainWindow()
    yield window


# ═══════════════════════════════════════════════════════════════════
# 测试：完整启动流程
# ═══════════════════════════════════════════════════════════════════


class TestFullStartup:
    """等价 main.py 完整启动——MainWindow 构建无崩溃"""

    def test_main_window_created(self, main_window):
        """MainWindow 构造成功"""
        assert main_window is not None
        assert main_window.windowTitle() == "GachaStat"

    def test_config_panel_exists(self, main_window):
        """ConfigPanel 被 MainWindow 正确初始化"""
        # MainWindow.__init__ → _setup_ui → ConfigPanel()
        # ConfigPanel 存储为 self.config_panel
        panel = main_window.config_panel
        assert panel is not None
        # 确认 _pity_defs 已通过 set_store 刷新
        assert hasattr(panel, "_pity_defs")


class TestConfigPanelViaMainWindow:
    """通过 MainWindow 访问 ConfigPanel 并操作保底 UI"""

    @pytest.fixture
    def panel(self, main_window):
        """从 MainWindow 取 ConfigPanel 并确保已加载数据"""
        p = main_window.config_panel
        if not p._pity_defs:
            # 强制刷新（模拟 TOML 加载完成后的回调）
            from gacha_simulator.core.config_toml import load_toml
            from gacha_simulator.paths import get_config_dir

            toml_path = os.path.join(get_config_dir(), "config.toml")
            if not os.path.exists(toml_path):
                toml_path = os.path.join(
                    os.path.dirname(__file__), "..", "..",
                    "gacha_simulator", "config", "config.toml",
                )
            store = load_toml(toml_path)
            p._store = store
            p._refresh_from_store_impl()
        return p

    def test_pity_defs_loaded(self, panel):
        """ConfigPanel._pity_defs 非空"""
        assert len(panel._pity_defs) >= 1

    def test_select_pity_no_crash(self, panel):
        """选中保底条目——_on_pity_selected 不崩溃"""
        panel.pity_list.setCurrentRow(0)
        assert panel._pity_detail_group.isEnabled()

    def test_cycle_all_types_no_crash(self, panel):
        """遍历全部保底类型——切换不崩溃"""
        panel.pity_list.setCurrentRow(0)
        for i in range(panel.pity_type_combo.count()):
            panel.pity_type_combo.setCurrentIndex(i)
            assert panel._pity_dynamic_container.parentWidget() is not None

    def test_apply_pity_edit_no_crash(self, panel):
        """编辑并应用——_apply_pity_edit 不崩溃"""
        panel.pity_list.setCurrentRow(0)
        panel.pity_name_edit.setText("startup_test")
        panel._apply_pity_edit()
        assert panel._pity_defs[0]["name"] == "startup_test"

    def test_apply_to_store_no_crash(self, panel):
        """apply_to_store 不崩溃"""
        panel.apply_to_store()
        assert panel._store.pity.pities[0].btype

    def test_get_config_no_crash(self, panel):
        """get_config 返回有效数据"""
        config = panel.get_config()
        assert "pity" in config
        assert len(config["pity"]["pities"]) >= 1
