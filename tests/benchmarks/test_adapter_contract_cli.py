"""T3（`cli` 部分）：适配器契约测试 + G1 闭环。

对应 §3.9 T3 与 `1i` 行：`name` 互不重复 / `is_user_path` 符合约定 / 返回 `RunResult`
且 `path` 与 `name` 一致 / `available()` 与实际可运行性一致 / **`Plan.collector` 申报值
与驱动代码的实际驱动方式相符**。

两条分界：

- **不起进程的部分**（契约属性、argv 组装、申报值的源码级核对）默认就跑
- **需真实运行的部分**（真实子进程、G1 闭环）由 `P83_PERF_TESTS` 开关门控（§3.9）
"""

import json
import os
import re
from pathlib import Path

import pytest

from benchmarks.perf import __main__ as entry
from benchmarks.perf.adapters.base import get_adapter, load_adapters
from benchmarks.perf.plan import Plan
from benchmarks.perf import report
from gacha_simulator.paths import get_config_dir
from tests.benchmarks.conftest import requires_real_run

REPO_ROOT = Path(__file__).resolve().parents[2]
#: 真实配置的位置由 paths.get_config_dir() 决定——**不是**仓库里的 config/ 目录
#: （那里没有 config.toml，实测：仓库 `config/` 下只有 .py 与模板）。
DEFAULT_CONFIG = os.path.join(get_config_dir(), 'config.toml')
#: T3 的规模参数（§3.9）——秒级。
T3_PARAMS = dict(n=10, workers=2, seed=42, repeats=1, grain='batch', collector=False)
#: G1 闭环用——**建基线须 repeats >= 3**，故不能沿用 T3 的 repeats=1。
G1_PARAMS = dict(n=10, workers=2, seed=42, repeats=3, grain='batch', collector=False)


def _call_arguments(source: str, callee: str) -> str:
    """取出 `callee(...)` 的实参文本（按括号配平）。"""
    match = re.search(re.escape(callee) + r'\s*\(', source)
    if match is None:
        raise AssertionError(f'源码中找不到 {callee}( 的调用')
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        if source[index] == '(':
            depth += 1
        elif source[index] == ')':
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f'{callee}( 的括号未配平')


class TestContractSurface:
    """契约属性——不需要起进程。"""

    def test_name(self):
        assert get_adapter('cli').name == 'cli'

    def test_is_user_path(self):
        """`cli` 是用户真实走的路径（只有 `inline` 为 False）。"""
        assert get_adapter('cli').is_user_path is True

    def test_registered_in_registry(self):
        assert 'cli' in load_adapters()

    def test_declares_absent_stage(self):
        """`cli` 没有分发器——该段缺失属事实，故声明为结构性缺失。"""
        assert get_adapter('cli').absent_stages == ('dispatch',)

    def test_timeout_is_finite(self):
        """§3.10：**绝不无超时等待**。"""
        assert 0 < get_adapter('cli').timeout_seconds < float('inf')


class TestCollectorDeclarationMatchesDriver:
    """§3.9 T3 的专条：声明的 `collector` 必须与驱动代码的实际驱动方式相符。

    `cli` 的驱动是被测的 `python -m gacha_simulator.cli`，故核对对象是**产品侧那个
    文件**里对 `run_batch_parallel` 的调用——适配器自己不起池、也不传 `on_result`。
    """

    def test_adapter_declares_false(self):
        assert get_adapter('cli').collector is False

    def test_driver_does_not_pass_on_result(self):
        source = (REPO_ROOT / 'gacha_simulator' / 'cli.py').read_text(encoding='utf-8')
        arguments = _call_arguments(source, 'run_batch_parallel')
        assert 'on_result' not in arguments, (
            'cli 的驱动未传 on_result，故适配器的 collector 申报值必须是 False；'
            '若这里改传了，须同步把适配器的申报值改为 True'
        )

    def test_driver_passes_collect_perf(self):
        """`--perf-json` 的开启者会下传 `collect_perf`——这一条与申报值是两件事。"""
        source = (REPO_ROOT / 'gacha_simulator' / 'cli.py').read_text(encoding='utf-8')
        assert 'collect_perf=bool(args.perf_json)' in _call_arguments(source, 'run_batch_parallel')

    def test_checker_actually_works(self):
        """反向自检：核对器对一段「传了 on_result」的源码必须报出问题。"""
        fake = 'x = run_batch_parallel(\n    env=env,\n    on_result=collector.on_result,\n)\n'
        assert 'on_result' in _call_arguments(fake, 'run_batch_parallel')


class TestArgvAssembly:
    """argv 组装——不需要起进程。"""

    def test_maps_plan_fields(self, make_plan):
        plan = make_plan(n=7, workers=3, seed=99, strategy_key='no_draw')
        argv = get_adapter('cli').build_argv(plan, perf_json='P.json', output='O.json')
        assert argv[:3] == [__import__('sys').executable, '-m', 'gacha_simulator.cli']
        for flag, value in (('-n', '7'), ('-w', '3'), ('-s', '99'),
                            ('--strategy', 'no_draw'), ('--perf-json', 'P.json'),
                            ('-o', 'O.json')):
            assert argv[argv.index(flag) + 1] == value

    def test_strategy_params_serialized_as_json(self, make_plan):
        plan = make_plan(strategy_params={'desired': {'A': 1}})
        argv = get_adapter('cli').build_argv(plan, perf_json='P', output='O')
        assert json.loads(argv[argv.index('--strategy-params') + 1]) == {'desired': {'A': 1}}

    def test_empty_params_omitted(self, make_plan):
        argv = get_adapter('cli').build_argv(make_plan(strategy_params={}),
                                             perf_json='P', output='O')
        assert '--strategy-params' not in argv

    def test_progress_disabled(self, make_plan):
        """适配器要的是机器可读的输出，不能让进度条刷屏。"""
        argv = get_adapter('cli').build_argv(make_plan(), perf_json='P', output='O')
        assert '--no-progress' in argv


class TestUnavailablePathIsSkippedNotFatal:
    """`available()` 为 False 时平台**跳过**该适配器而非报错（§二 G2）。"""

    def test_entry_reports_skip_and_returns_three(self, tmp_path, monkeypatch, capsys):
        class Dead:
            name = 'cli'
            def available(self):
                return False

        monkeypatch.setattr(entry, 'get_adapter', lambda path: Dead())
        plan_file = tmp_path / 'plan.json'
        plan_file.write_text(json.dumps(
            {'config_path': 'c.toml', 'strategy_key': 'smart', 'strategy_params': {},
             'n': 10, 'workers': 1, 'seed': 1}), encoding='utf-8')
        assert entry.main(['run', '--plan', str(plan_file)]) == entry.EXIT_UNAVAILABLE
        assert '不可用' in capsys.readouterr().err


@requires_real_run
class TestRealRunContract:
    """需真实子进程——受 `P83_PERF_TESTS` 门控。"""

    def _plan(self, **overrides):
        params = dict(T3_PARAMS)
        params.update(overrides)
        return Plan(config_path=DEFAULT_CONFIG,
                    strategy_key='smart', strategy_params={}, **params)

    def test_available_matches_runnability(self):
        adapter = get_adapter('cli')
        assert adapter.available() is True

    def test_result_path_matches_name(self):
        adapter = get_adapter('cli')
        result = adapter.run(self._plan())
        assert result.path == adapter.name
        assert result.is_user_path is True
        assert result.repeats == 1
        assert result.wall_median and result.wall_median > 0

    def test_stages_collected(self):
        result = get_adapter('cli').run(self._plan())
        assert result.stages.get('simulate', 0) > 0
        assert 'dispatch' not in result.stages
        assert any('本路径不产出该段' in w for w in result.warnings)

    def test_bytes_collected(self):
        result = get_adapter('cli').run(self._plan())
        assert result.resources.bytes and result.resources.bytes > 0
        assert result.resources.rss_peak_mb is None
        assert any('本期不采集' in w for w in result.warnings)


@requires_real_run
class TestG1Closure:
    """G1 的闭环：**用 `1k` 的命令**跑「建首条基线 → 再跑一次 → 出比值」。

    不得靠手工多步操作凑出（§3.1 / `1i` 行）——故本用例两次都调 `entry.main`，
    即 README 里写的那条命令。
    """

    @pytest.fixture
    def tmp_baselines(self, tmp_path, monkeypatch):
        """把基线根指向临时目录——用例不得写入仓库的 `benchmarks/baselines/`。"""
        root = tmp_path / 'baselines'
        monkeypatch.setattr(report, 'baselines_root', lambda root=None: root or tmp_path / 'baselines')
        return root

    @pytest.fixture
    def plan_file(self, tmp_path):
        path = tmp_path / 'plan.json'
        payload = dict(config_path=DEFAULT_CONFIG,
                       strategy_key='smart', strategy_params={}, **G1_PARAMS)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        return str(path)

    def test_build_then_compare(self, plan_file, tmp_baselines, capsys):
        assert entry.main(['run', '--plan', plan_file, '--baseline', 'g1-closure',
                           '--register']) == entry.EXIT_OK
        registered = capsys.readouterr().out
        assert '已登记基线' in registered
        assert list(tmp_baselines.rglob('*.json')), '基线文件应已落盘'

        capsys.readouterr()
        assert entry.main(['run', '--plan', plan_file, '--baseline', 'g1-closure']) == entry.EXIT_OK
        output = capsys.readouterr().out
        assert '总墙钟比值' in output
        assert '结论' in output
        match = re.search(r'总墙钟比值（本次 / 基线）：([0-9.]+)', output)
        assert match is not None, output
        # 同一配置连跑两次，比值应贴近 1（本用例只要求它落在合理区间，不断言精确值）
        assert 0.5 < float(match.group(1)) < 2.0
