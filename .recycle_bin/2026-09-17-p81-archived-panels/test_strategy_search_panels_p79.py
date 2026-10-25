"""P79 8.2「搜索面板 env 不继承条件」的 GUI 侧落点。

覆盖 `gui/strategy_panel.py` 与 `gui/resource_search_panel.py` 各自自建的
`_build_simulation_env()`——**两个面板都不经 `retreat_search._build_env`**，
只改那里对它们零作用（5 阶段的影响面复核结论）。搜索由硬边界收口。

退避搜索 `_build_env` 两分支的同类断言落 `tests/core/test_retreat_search.py`。
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


def _store_with_condition():
    """带用户停止条件的 ConfigStore——否则「不继承」无从体现。"""
    from gacha_simulator.core.config_toml import load_toml

    store = load_toml(CONFIG)
    store.stop_condition = {
        'mode': 'any',
        'conditions': [{'type': 'fixed_action_count', 'max_actions': 20}],
    }
    return store


def test_condition_is_actually_wired_into_env():
    """前提断言：同一 store 经 from_config_store 会带上用户条件。

    否则下面的「为 None」可能只是接线失效导致的假通过。
    """
    from gacha_simulator.service.batch_simulator import SimulationEnvBuilder

    env = SimulationEnvBuilder.from_config_store(_store_with_condition())
    assert env.stop_condition is not None


def test_strategy_panel_env_does_not_inherit_condition(qapp):
    from gacha_simulator.gui.strategy_panel import StrategyWorker

    worker = StrategyWorker(
        method='forward', all_target_ids=[], desire_weights={},
        miss_cost_weights={}, card_value_weights={}, success_threshold=0.95,
        target_qty=1, num_simulations=1, gdr_key='all_targets',
        gdr_threshold=1.0, config_store=_store_with_condition(),
    )
    worker._build_simulation_env()
    assert worker._sim_env is not None
    assert worker._sim_env.stop_condition is None


def test_resource_search_panel_env_does_not_inherit_condition(qapp):
    from gacha_simulator.gui.resource_search_panel import ResourceSearchWorker

    worker = ResourceSearchWorker(
        target_specs={}, success_threshold=0.95, num_simulations=1,
        initial_resource_hint=1000.0, resource_lo=0.0, max_iterations=10,
        precision_draws=1, gdr_key='all_targets', gdr_threshold=1.0,
        config_store=_store_with_condition(),
    )
    worker._build_simulation_env()
    assert worker._sim_env is not None
    assert worker._sim_env.stop_condition is None
