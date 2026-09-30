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
from types import SimpleNamespace

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


class TestEmptyProfileDirWritesNothing:
    """`profile_enabled=True` + `profile_dir=''` 时**不得落盘**（契约「空则不落盘」）。

    **回归用途：** 该组合是合法状态（`cli` 路径的 `test_no_chain_when_no_directory` 就是
    这么用的），而 `os.path.join('', run_id)` 会退化成裸 `run_id`（相对路径）——守卫缺失
    时 run 目录被建到**调用方的当前工作目录**：2026-09-30 在仓库根查出 70 个 12 位十六
    进制空目录，每次 `pytest` 掉一个（含 H9 在 `git push` 时跑的全量）。

    **不受 `P83_PERF_TESTS` 门控：** 本用例护的正是默认 `pytest -q` 会踩到的那条路，
    放进受门控的类里等于没测。
    """

    def test_no_directory_created_in_cwd(self, make_plan, tmp_path, monkeypatch):
        """空 `profile_dir` 时工作目录必须一个条目都不多出来。"""
        monkeypatch.chdir(tmp_path)
        plan = make_plan(config_path=DEFAULT_CONFIG, path='inline', n=2, workers=1,
                         seed=42, repeats=1, grain='stage', collector=True,
                         profile_enabled=True, profile_dir='')
        result = get_adapter('inline').run(plan)
        leftover = sorted(entry.name for entry in tmp_path.iterdir())
        assert leftover == [], f'profile_dir 为空时不该在工作目录建任何东西，实得 {leftover}'
        assert result.functions is None
        assert any('未指定 profile 目录' in w for w in result.warnings), result.warnings

    def test_directory_is_created_when_profile_dir_given(self, make_plan, tmp_path):
        """反向对照：守卫只挡空值。给了 `profile_dir` 时四字段照常置位、目录照常建。

        **没有这一条，上面那条断言对「守卫被写成无差别 return」没有鉴别力**——那种写法
        会让剖析彻底失效，而上面一条仍会通过。
        """
        run_id = 'abcdef012345'
        plan = make_plan(config_path=DEFAULT_CONFIG, path='inline', n=2, workers=1,
                         seed=42, repeats=1, grain='stage', collector=True,
                         profile_enabled=True, profile_dir=str(tmp_path),
                         profile_skip=0, profile_count=4)
        env = SimpleNamespace(profile_enabled=False, profile_dir='',
                              profile_skip=0, profile_count=0)
        warnings: list = []
        get_adapter('inline')._apply_profile_fields(env, plan, run_id, warnings)
        assert warnings == []
        assert env.profile_enabled is True
        assert env.profile_dir == str(tmp_path / run_id)
        assert env.profile_skip == 0 and env.profile_count == 4
        assert (tmp_path / run_id).is_dir(), '给了 profile_dir 就该落 run 级子目录'


@requires_real_run
class TestRealRunContract:
    # §3.9 T3/T4 的耗时上限由 `pytest-timeout` 在**用例级**兜底：超时即 FAIL，
    # 而不是挂死。实测过一次挂死的代价——某条用例把产品的私有 worker 换掉后
    # 任务永远不到 done，适配器一路轮询到它自己的硬超时（3600s）。
    pytestmark = pytest.mark.timeout(60)   # T3 的 inline 部分（§3.9 定的上限 60s）

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
