"""GUI 模块冒烟导入测试——确保所有面板可正常加载，不存在 NameError / ImportError。
不实例化 QApplication（headless 环境友好），仅验证模块级导入路径。
"""
import pytest


# 需要 QApplication 才能构造 QWidget 的模块——只验证导入，不构造实例
GUI_MODULES = [
    'gacha_simulator.gui.main_window',
    'gacha_simulator.gui.analysis_panel',
    'gacha_simulator.gui.gacha_panel',
    'gacha_simulator.gui.retreat_panel',
    'gacha_simulator.gui.worst_impact_panel',
    'gacha_simulator.gui.strategy_panel',
    'gacha_simulator.gui.config_panel',
    'gacha_simulator.gui.chart_webview',
    'gacha_simulator.gui.data_manager_panel',
    'gacha_simulator.gui.plan_search_panel',
    'gacha_simulator.gui.process_analysis_panel',
    'gacha_simulator.gui.comparison_analysis_panel',
]


@pytest.mark.parametrize('module_name', GUI_MODULES)
def test_gui_module_imports(module_name):
    """每个 GUI 模块至少能成功导入——防止 NameError / ImportError"""
    try:
        __import__(module_name)
    except Exception as e:
        pytest.fail(f"导入 {module_name} 失败: {type(e).__name__}: {e}")
