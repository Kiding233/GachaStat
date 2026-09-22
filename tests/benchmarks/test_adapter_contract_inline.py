"""T3（`inline` 部分）：适配器契约测试。

对应 §3.9 T3 与 `2e` 行：`name` 互不重复 / `is_user_path` 符合约定 / 返回 `RunResult`
且 `path` 与 `name` 一致 / `available()` 与实际可运行性一致 / **`Plan.collector` 申报值
与驱动代码的实际驱动方式相符**。

§3.9 的专条：**`inline` 适配器专项断言 `is_user_path is False`**——「这不是用户路径」
这一标签若不成立，它在报告里会被读成真实用户体验。

`collector` 的断言点落在本项与 `2d`：`inline` 的驱动是 `2d` 吸收的 `profile_sim.py`
驱动逻辑，故**两处都核对**。
"""

import os
import re
from pathlib import Path

import pytest

from benchmarks.perf.adapters.base import get_adapter, load_adapters
from benchmarks.perf.plan import Plan
from gacha_simulator.paths import get_config_dir
from tests.benchmarks.conftest import call_arguments, requires_real_run

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = os.path.join(get_config_dir(), 'config.toml')
T3_PARAMS = dict(n=10, workers=2, seed=42, repeats=1, grain='batch', collector=True)


class TestContractSurface:
    def test_name(self):
        assert get_adapter('inline').name == 'inline'

    def test_is_user_path_is_false(self):
        """§3.9 的专项断言：`inline` **不是**用户路径。"""
        assert get_adapter('inline').is_user_path is False

    def test_registered_alongside_cli(self):
        registry = load_adapters()
        assert 'inline' in registry and 'cli' in registry

    def test_names_are_unique(self):
        names = [cls.name for cls in load_adapters().values()]
        assert len(names) == len(set(names))

    def test_declares_absent_stage(self):
        assert get_adapter('inline').absent_stages == ('dispatch',)

    def test_does_not_claim_function_grain_for_single_worker(self, make_plan):
        """§3.8 D2.1 由 `Plan.validate()` 拦截，故 `workers=1` 的 function plan 建不出来。"""
        with pytest.raises(ValueError, match='D2.1'):
            make_plan(grain='function', workers=1)


class TestCollectorDeclarationMatchesDriver:
    """§3.9 T3 专条：`inline` 申报 `True`，驱动代码必须**真的**传 `on_result`。"""

    def test_adapter_declares_true(self):
        assert get_adapter('inline').collector is True

    def test_adapter_source_passes_on_result(self):
        source = (REPO_ROOT / 'benchmarks' / 'perf' / 'adapters' / 'inline.py').read_text(encoding='utf-8')
        assert 'on_result' in call_arguments(source, 'run_batch_parallel')

    def test_absorbed_driver_source_passes_on_result(self):
        """驱动逻辑的来源（`2a` 修复后的 `profile_sim.py`）同样传 `on_result`。"""
        source = (REPO_ROOT / 'scripts' / 'profile_sim.py').read_text(encoding='utf-8')
        assert 'on_result' in call_arguments(source, 'run_batch_parallel')

    def test_contrast_with_cli(self):
        """反向对照：`cli` 的驱动**不**传 `on_result`，故其申报值为 `False`。"""
        source = (REPO_ROOT / 'gacha_simulator' / 'cli.py').read_text(encoding='utf-8')
        assert 'on_result' not in call_arguments(source, 'run_batch_parallel')
        assert get_adapter('cli').collector is False

    def test_declaration_is_not_a_runtime_switch(self):
        """平台不因 `collector` 改变驱动方式——它是申报值（§3.4）。"""
        source = (REPO_ROOT / 'benchmarks' / 'perf' / 'adapters' / 'inline.py').read_text(encoding='utf-8')
        call = call_arguments(source, 'run_batch_parallel')
        assert re.search(r'on_result\s*=', call), 'on_result 应无条件传入，而非由 plan.collector 条件控制'


@requires_real_run
class TestRealRunContract:
    """需真实运行——受 `P83_PERF_TESTS` 门控。"""

    def _plan(self, **overrides):
        params = dict(T3_PARAMS)
        params.update(overrides)
        return Plan(config_path=DEFAULT_CONFIG, strategy_key='smart',
                    strategy_params={}, **params)

    def test_result_path_matches_name(self):
        adapter = get_adapter('inline')
        result = adapter.run(self._plan())
        assert result.path == adapter.name
        assert result.is_user_path is False, 'inline 的每条 RunResult 都必须自带非用户路径标签'
        assert result.wall_median and result.wall_median > 0

    def test_stages_collected(self):
        result = get_adapter('inline').run(self._plan())
        assert result.stages.get('simulate', 0) > 0
        assert result.stages.get('config_load', 0) > 0
        assert 'dispatch' not in result.stages
        assert any('本路径不产出该段' in w for w in result.warnings)

    def test_resources_collected(self):
        """本路径在进程内、有回传通道，故字节数可得（与 `gui-qt` / `webui` 相反）。"""
        result = get_adapter('inline').run(self._plan())
        assert result.resources.bytes and result.resources.bytes > 0
        assert result.resources.rss_peak_mb is None
        assert any('本期不采集' in w for w in result.warnings)

    def test_available_matches_runnability(self):
        assert get_adapter('inline').available() is True
