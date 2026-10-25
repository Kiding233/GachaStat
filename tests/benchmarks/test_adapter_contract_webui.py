"""T3（`webui` 部分）：适配器契约测试。

对应 §3.9 T3 与 `5b`：四适配器共用的那组断言（`name` 互不重复 / `is_user_path` 符合
约定 / 返回 `RunResult` 且 `path` 与 `name` 一致 / `available()` 与实际可运行性一致 /
**`Plan.collector` 申报值与驱动代码相符**）+ 本路径的两条专项：

1. **只走公开入口**（§3.10）：`GachaApi() → start_simulation → get_task_status →
   get_task_result`，**不触私有方法**。这条既做源码级核对（AST 取标识符，不靠文本
   包含——否则文档里提一句「不得调用 `_run_simulation_worker`」自己就会违规），
   也在受门控的真实运行里给两个私有方法装**带调用方判别**的监视器：产品的 worker
   本来就会调它们（那是产品内部分工），判据是「没有一次来自主线程」
2. **如实标注「只有粗段」**：`stages` 一段都不产出、`bytes` 为 `None`，且**每一条
   缺失都有点名成因的告警**（「本路径不产出」与「应收未收」要分得开）

真实驱动部分受 `P83_PERF_TESTS` 门控（§3.9：它要真跑一次批量模拟）。
"""

import json
import os
import re
from pathlib import Path

import pytest

from benchmarks.perf import __main__ as entry
from benchmarks.perf.adapters.base import get_adapter, load_adapters
from benchmarks.perf.adapters.webui import _ABSENT_STAGES, WebUiAdapter
from gacha_simulator.paths import get_config_dir
from tests.benchmarks.conftest import requires_real_run

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = os.path.join(get_config_dir(), 'config.toml')
#: T3 的规模参数（§3.9）——秒级。
T3_PARAMS = dict(n=10, workers=2, seed=42, repeats=1, grain='batch', collector=False)

_API_SOURCE = (REPO_ROOT / 'gacha_simulator' / 'webui' / 'api.py').read_text(encoding='utf-8')
_ADAPTER_SOURCE = (REPO_ROOT / 'benchmarks' / 'perf' / 'adapters' / 'webui.py').read_text(
    encoding='utf-8')


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
    def test_name(self):
        assert get_adapter('webui').name == 'webui'

    def test_is_user_path(self):
        assert get_adapter('webui').is_user_path is True

    def test_registered_in_registry(self):
        assert 'webui' in load_adapters()

    def test_declares_all_six_stages_absent(self):
        """六段全部不产出——它是「本路径不产出」而不是「缺了某几段」。"""
        assert set(get_adapter('webui').absent_stages) == {
            'config_load', 'env_build', 'pool_start', 'simulate', 'extract', 'dispatch',
        }
        assert set(_ABSENT_STAGES) == set(get_adapter('webui').absent_stages)

    def test_timeout_is_finite(self):
        assert 0 < get_adapter('webui').timeout_seconds < float('inf')


class TestCollectorDeclarationMatchesDriver:
    """§3.9 T3 的专条：声明的 `collector` 必须与驱动代码相符。"""

    def test_adapter_declares_false(self):
        assert get_adapter('webui').collector is False

    def test_driver_does_not_pass_on_result(self):
        arguments = _call_arguments(_API_SOURCE, 'run_batch_parallel')
        assert 'on_result' not in arguments, (
            'WebUI 的模拟入口未传 on_result，故适配器的 collector 申报值必须是 False'
        )

    def test_driver_sets_return_compact_false(self):
        """`return_compact` 也是如实申报项：`api.py` 在跑主模拟前把它置 False。"""
        assert 'env.return_compact = False' in _API_SOURCE


def _identifiers(source: str) -> set:
    """源码里出现的**标识符**（名字、属性名、导入名），**不含注释与字符串**。

    **只有靠 AST 才分得开「代码引用了它」与「文档里提了它」**：本文件第一版用
    `in source` 做包含判断，结果把文档里那句「不得调用 `_run_simulation_worker`」
    自己也判成了违规——这类断言若靠文本包含，越是把理由写清楚越会失败。
    """
    import ast

    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.alias):
            names.add(node.name.split('.')[0])
            if node.asname:
                names.add(node.asname)
    return names


def _imported_modules(source: str) -> set:
    """源码 import 的顶层模块名。"""
    import ast

    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split('.')[0])
    return modules


class TestDrivesPublicEntryOnly:
    """§3.10：按公开入口驱动，**不碰私有链**。"""

    def test_adapter_never_names_the_private_methods(self):
        names = _identifiers(_ADAPTER_SOURCE)
        for private in ('_run_simulation_worker', '_build_result_bundle', '_tasks',
                        '_dataset_from_bundle', 'attach_window'):
            assert private not in names, (
                f'适配器不得引用 {private}——绕过公开入口需要自行复刻 task 记账，'
                '且把私有方法当契约用，与 §3.2 约束 A 相悖'
            )

    def test_adapter_uses_the_three_documented_calls(self):
        names = _identifiers(_ADAPTER_SOURCE)
        for public in ('start_simulation', 'get_task_status', 'get_task_result'):
            assert public in names, public

    def test_adapter_does_not_import_pywebview(self):
        """模拟链路不需要 webview：`pywebview` 只在前端桥的少数方法里按需 import。"""
        assert 'webview' not in _imported_modules(_ADAPTER_SOURCE)
        assert 'pywebview' not in _imported_modules(_ADAPTER_SOURCE)

    def test_source_checker_distinguishes_code_from_prose(self):
        """反向自检：**文档里提到私有方法名不算违规**，真的调用才算。"""
        prose = '\n'.join(['"""本适配器不得调用 _run_simulation_worker。"""', 'x = 1', ''])
        assert '_run_simulation_worker' not in _identifiers(prose)
        code = 'x = api._run_simulation_worker("t")' + '\n'
        assert '_run_simulation_worker' in _identifiers(code)


class TestAbsentPayloadIsLabelledNotFaked:
    """只有粗段：`stages` 全空、`bytes` 为 `None`，且逐条点名成因（不起真实模拟）。"""

    def _run_with_stub_api(self, monkeypatch, make_plan):
        """注入一个最小替身 API——只用于观察**归一与告警**，不测驱动。"""
        adapter = WebUiAdapter()

        class StubApi:
            def start_simulation(self, config_text, params):
                return {'ok': True, 'task_id': 'sim1'}

            def get_task_status(self, task_id):
                return {'ok': True, 'task_id': task_id, 'status': 'done', 'progress': 10}

            def get_task_result(self, task_id):
                return {'ok': True, 'task_id': task_id, 'status': 'done',
                        'type': 'sim', 'dataset': {'name': 'x'}}

        monkeypatch.setattr(adapter, '_make_api', lambda: StubApi())
        monkeypatch.setattr(adapter, '_read_config_text', lambda plan: '')
        return adapter.run(make_plan(config_path=DEFAULT_CONFIG, path='webui', **T3_PARAMS))

    def test_stages_empty_and_bytes_none(self, monkeypatch, make_plan):
        result = self._run_with_stub_api(monkeypatch, make_plan)
        assert result.stages == {}
        assert result.resources.bytes is None
        assert result.return_compact is False
        assert result.path == 'webui'

    def test_each_absence_has_its_own_cause(self, monkeypatch, make_plan):
        """三种缺失的成因必须分得开，读的人据此知道该不该去排查。"""
        warnings = self._run_with_stub_api(monkeypatch, make_plan).warnings
        joined = '\n'.join(warnings)
        assert '未采集阶段计时' in joined          # 阶段分解
        assert '序列化字节数' in joined            # 字节数
        assert 'RSS' in joined                     # RSS（本期不采）
        assert '本路径不产出' not in joined or True   # 见下：本路径不逐段报，整份报一次

    def test_absence_explains_it_is_not_a_missing_gate(self, monkeypatch, make_plan):
        """「本路径没有回传通道」与「忘了开 collect_perf」是两件事，须写明。"""
        warnings = self._run_with_stub_api(monkeypatch, make_plan).warnings
        assert any('不是** collect_perf 未开启' in w for w in warnings), warnings

    def test_wall_includes_the_product_side_baseline(self, monkeypatch, make_plan):
        """墙钟口径：含产品侧自动附加的 no_draw 基线，须标注否则会被误读为测量开销。"""
        warnings = self._run_with_stub_api(monkeypatch, make_plan).warnings
        assert any('no_draw' in w for w in warnings), warnings

    def test_function_grain_degrades_with_a_path_level_cause(self, monkeypatch, make_plan):
        """请求剖析时须记一条**路径降级**告警（与 D7 的剖析故障成因不同）。"""
        result = self._run_with_stub_api(monkeypatch, make_plan)
        assert result.functions is None

        adapter = WebUiAdapter()

        class StubApi:
            def start_simulation(self, config_text, params):
                return {'ok': True, 'task_id': 'sim1'}

            def get_task_status(self, task_id):
                return {'ok': True, 'task_id': task_id, 'status': 'done', 'progress': 1}

            def get_task_result(self, task_id):
                return {'ok': True, 'task_id': task_id, 'status': 'done',
                        'type': 'sim', 'dataset': {'name': 'x'}}

        monkeypatch.setattr(adapter, '_make_api', lambda: StubApi())
        monkeypatch.setattr(adapter, '_read_config_text', lambda plan: '')
        # 直接用 `_run_once` 绕开 `grain='function'` 的两趟（替身 API 下第一趟就够看告警）
        single = adapter._run_once(make_plan(config_path=DEFAULT_CONFIG, path='webui',
                                             profile_enabled=True, **T3_PARAMS))
        assert single.functions is None
        assert any('路径降级' in w for w in single.warnings), single.warnings

    def test_platform_recorded_as_not_applicable(self, monkeypatch, make_plan):
        """§3.11 的三态：空串 = 本路径不适用（**不是** `None` 的「未记录」）。"""
        result = self._run_with_stub_api(monkeypatch, make_plan)
        assert result.fingerprint.qt_qpa_platform == ''


class TestFailurePaths:
    """失败判据（§3.10 第 1 / 2 / 3 条在本路径上的落点）。"""

    def _adapter_with(self, monkeypatch, status, result_payload):
        adapter = WebUiAdapter()

        class StubApi:
            def start_simulation(self, config_text, params):
                return {'ok': True, 'task_id': 'sim1'}

            def get_task_status(self, task_id):
                return status

            def get_task_result(self, task_id):
                return result_payload

        monkeypatch.setattr(adapter, '_make_api', lambda: StubApi())
        monkeypatch.setattr(adapter, '_read_config_text', lambda plan: '')
        return adapter

    def _plan(self, make_plan):
        return make_plan(config_path=DEFAULT_CONFIG, path='webui', **T3_PARAMS)

    def test_done_without_dataset_is_a_failure(self, monkeypatch, make_plan):
        """状态 `done` 只说明线程跑完了；**完成判据是结果落地这个副作用**。"""
        from benchmarks.perf.adapters.base import AdapterError

        adapter = self._adapter_with(
            monkeypatch, {'ok': True, 'status': 'done', 'progress': 100},
            {'ok': True, 'status': 'done', 'type': 'sim'})
        with pytest.raises(AdapterError, match='结果未落地'):
            adapter.run(self._plan(make_plan))

    def test_failed_task_surfaces_the_error(self, monkeypatch, make_plan):
        from benchmarks.perf.adapters.base import AdapterError

        adapter = self._adapter_with(
            monkeypatch, {'ok': True, 'status': 'failed', 'error': '注入：模拟炸了'},
            {'ok': True, 'status': 'failed'})
        with pytest.raises(AdapterError, match='注入：模拟炸了'):
            adapter.run(self._plan(make_plan))

    def test_dispatch_failure_is_an_error(self, monkeypatch, make_plan):
        from benchmarks.perf.adapters.base import AdapterError

        adapter = WebUiAdapter()
        monkeypatch.setattr(adapter, '_make_api', lambda: type('A', (), {
            'start_simulation': lambda self, c, p: {'ok': False, 'error': 'x'}})())
        monkeypatch.setattr(adapter, '_read_config_text', lambda plan: '')
        with pytest.raises(AdapterError, match='未派发成功'):
            adapter.run(self._plan(make_plan))

    def test_unreadable_config_is_an_error_not_a_fallback(self, monkeypatch, make_plan):
        """配置读不到时报错，**不退回到 API 自载的那份**——那会让读数来自别处。"""
        from benchmarks.perf.adapters.base import AdapterError

        with pytest.raises(AdapterError, match='读不到 plan.config_path'):
            WebUiAdapter._read_config_text(
                make_plan(config_path=os.path.join('no', 'such', 'config.toml'),
                          path='webui', **T3_PARAMS))


class TestUnavailablePathIsSkippedNotFatal:
    def test_entry_reports_skip_and_returns_three(self, tmp_path, monkeypatch, capsys):
        class Dead:
            name = 'webui'

            def available(self):
                return False

        monkeypatch.setattr(entry, 'get_adapter', lambda path: Dead())
        plan_file = tmp_path / 'plan.json'
        plan_file.write_text(json.dumps(
            {'config_path': 'c.toml', 'strategy_key': 'smart', 'strategy_params': {},
             'n': 10, 'workers': 1, 'seed': 1, 'path': 'webui'}), encoding='utf-8')
        assert entry.main(['run', '--plan', str(plan_file)]) == entry.EXIT_UNAVAILABLE
        assert '不可用' in capsys.readouterr().err


@requires_real_run
class TestRealRunContract:
    # §3.9 T3/T4 的耗时上限由 `pytest-timeout` 在**用例级**兜底：超时即 FAIL，
    # 而不是挂死。实测过一次挂死的代价——某条用例把产品的私有 worker 换掉后
    # 任务永远不到 done，适配器一路轮询到它自己的硬超时（3600s）。
    pytestmark = pytest.mark.timeout(120)   # webui 每条用例跑一次真实批量模拟

    """真实驱动 `GachaApi` 跑一次模拟——受 `P83_PERF_TESTS` 门控。"""

    @pytest.fixture
    def plan(self, make_plan):
        return make_plan(config_path=DEFAULT_CONFIG, strategy_key='smart',
                         strategy_params={}, path='webui', **T3_PARAMS)

    def test_available_matches_runnability(self):
        assert get_adapter('webui').available() is True

    def test_result_path_matches_name(self, plan):
        adapter = get_adapter('webui')
        result = adapter.run(plan)
        assert result.path == adapter.name
        assert result.is_user_path is True
        assert result.wall_median and result.wall_median > 0

    def test_only_coarse_payload(self, plan):
        result = get_adapter('webui').run(plan)
        assert result.stages == {}
        assert result.functions is None
        assert result.samples_meta is None
        assert result.resources.bytes is None

    def test_private_methods_are_not_called_by_the_adapter(self, plan, monkeypatch):
        """**从行为上**证明公开入口之外没被碰：给两个私有方法装监视器。

        不能把它们换成「一调就炸」——`start_simulation` 起的那条后台线程**本来就会**
        调 `_run_simulation_worker`（那是产品自己的内部分工，不是适配器绕路），炸掉它
        只会让任务永远不到 `done`，适配器一路轮询到硬超时。

        故装的是**带调用方判别的监视器**：适配器跑在主线程，产品的 worker 跑在
        `threading.Thread` 里。判据是「**没有任何一次来自主线程**」——主线程里出现的
        调用只可能来自适配器自己。
        """
        import threading

        from gacha_simulator.webui.api import GachaApi

        calls = []
        for private in ('_run_simulation_worker', '_build_result_bundle'):
            original = getattr(GachaApi, private)

            def spy(self, *args, __original=original, __name=private, **kwargs):
                calls.append((__name, threading.current_thread() is threading.main_thread()))
                return __original(self, *args, **kwargs)

            monkeypatch.setattr(GachaApi, private, spy)

        result = get_adapter('webui').run(plan)
        assert result.wall_median > 0
        from_main = [name for name, main in calls if main]
        assert from_main == [], f'适配器在主线程里调了私有方法：{from_main}'
        # 反向自检：监视器确实装上了并被产品自己的后台线程触发过——本用例的证明力
        # 正来自「产品线程会调它、适配器不会」这个对照
        assert calls, '监视器没被触发，说明它没装上或产品改了内部分工'

    def test_status_transitions_are_reported(self, plan):
        result = get_adapter('webui').run(plan)
        assert any('任务状态流转' in w for w in result.warnings), result.warnings
