"""T4（`6g`）：`function` 档的真实并行集成测试。

**唯一需要真实进程池的一段**，故 `@pytest.mark.skipif` 门控（`P83_PERF_TESTS=1` 才跑），
默认 `pytest -q` 不执行、不撞 H9 的 120s（§3.9）。

机制本身已于 2026-09-18 用真实 `_wk_init` / `_wk_run_single` 预验证通过（§3.8 的验证
记录），故本项是「真实集成的回归测试」而非「可行性探针」。

规模参数按 §3.9 T4：`n=20, workers=2, profile_skip=0, profile_count=4`。
"""

import json
import os
from pathlib import Path

import pytest

import gacha_simulator.service.batch_simulator as bs
from benchmarks.perf.adapters.base import get_adapter
from benchmarks.perf.profilers.cprofile import (
    PROFILE_FILE_SUFFIX,
    WORKER_MARKER_PREFIX,
    WORKER_MARKER_SUFFIX,
)
from gacha_simulator.core.config_toml import load_toml
from gacha_simulator.core.result_types import _RESULT_VERSION
from gacha_simulator.paths import get_config_dir
from gacha_simulator.service.batch_simulator import SimulationEnvBuilder
from tests.benchmarks.conftest import requires_real_run

N = 20
WORKERS = 2
SKIP = 0
COUNT = 4
SEED = 42
CONFIG = os.path.join(get_config_dir(), 'config.toml')
#: 逐字段比对时排除的易变字段（采集时刻，同种子也不会相同）。
_VOLATILE = ('generated_at',)


def _fingerprint(result):
    """把一组 `CompactResult` 归一为可逐字段比对的形式。

    **按内容排序后再比**：MPPool 路径用 `imap_unordered`，同种子下每次模拟的内容是
    确定的，但**返回顺序不确定**（谁先算完谁先出）。故「逐字段一致」必须按多重集读，
    否则会把顺序差异误报成内容差异。排序键用规范化 JSON，保证与顺序无关、与内容有关。
    """
    rows = [{k: v for k, v in r.to_dict().items() if k not in _VOLATILE} for r in result]
    return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False))


@requires_real_run
class TestFunctionGrainIntegration:
    # §3.9 T3/T4 的耗时上限由 `pytest-timeout` 在**用例级**兜底：超时即 FAIL，
    # 而不是挂死。实测过一次挂死的代价——某条用例把产品的私有 worker 换掉后
    # 任务永远不到 done，适配器一路轮询到它自己的硬超时（3600s）。
    pytestmark = pytest.mark.timeout(60)   # T4 的唯一真实并行的部分（§3.9 定的上限 60s）

    @pytest.fixture
    def plan(self, make_plan, tmp_path):
        return make_plan(config_path=CONFIG, n=N, workers=WORKERS, seed=SEED,
                         repeats=1, grain='function', collector=True,
                         profile_enabled=True, profile_dir=str(tmp_path / 'prof'),
                         profile_skip=SKIP, profile_count=COUNT)

    def test_profile_files_produced(self, plan):
        get_adapter('inline').run(plan)
        run_dirs = list(Path(plan.profile_dir).glob('*'))
        assert run_dirs, '应落一个 run 级子目录'
        files = [f for d in run_dirs for f in d.glob(f'*{PROFILE_FILE_SUFFIX}')]
        assert files, '真实并行下应产出至少一个剖面文件'

    def test_worker_marker_proves_fields_reached_the_worker(self, plan):
        """**worker 侧**的断言（AUDIT-BREAK-8①）。

        只断言父进程侧的 `env.profile_enabled` 覆盖不到「四字段未随 pickle 到达
        worker」这一断裂。Windows spawn 下父进程对模块做的 monkeypatch 到不了 worker，
        故由 worker 自己写一份自报标记——**该文件存在即证明本 worker 进程按收到的字段
        构造出了采样器**，且 skip / count 与 plan 一致。
        """
        get_adapter('inline').run(plan)
        markers = list(Path(plan.profile_dir).rglob(f'{WORKER_MARKER_PREFIX}*{WORKER_MARKER_SUFFIX}'))
        assert markers, '每个真正参与了采样的 worker 都应留下一份自报标记'
        payloads = [json.loads(m.read_text(encoding='utf-8')) for m in markers]
        pids = {p['pid'] for p in payloads}
        assert len(pids) == len(payloads), '每个 worker 进程一份'
        for payload in payloads:
            assert payload['skip'] == SKIP and payload['count'] == COUNT, payload
        assert len(pids) <= WORKERS

    def test_merged_functions_contain_the_call_chain(self, plan):
        result = get_adapter('inline').run(plan)
        assert result.functions, 'function 档应产出函数级统计'
        names = ' '.join(f.name for f in result.functions)
        assert '_run_single' in names or 'run_simulation' in names, names[:300]

    def test_not_comparable_is_set(self, plan):
        """§3.8 D6：function 档的耗时被插桩放大，不得进基线比值。"""
        result = get_adapter('inline').run(plan)
        assert result.not_comparable is True


@requires_real_run
class TestZeroSideEffectsWhenOff:
    """关闭剖析时**零副作用**——这条是 §8.2/§8.3「默认路径零行为变化」的依据。"""

    def _run(self, *, enabled, tmp_path):
        store = load_toml(CONFIG)
        env = SimulationEnvBuilder.from_config_store(store)
        env.profile_enabled = enabled
        env.profile_dir = str(tmp_path / 'prof') if enabled else ''
        targets = {tc.card_id: getattr(tc, 'quantity', 1) for tc in store.target_cards}
        result = bs.run_batch_parallel(
            env=env, target_specs=targets, initial_resources=env.initial_resources,
            num_simulations=N, max_workers=WORKERS, seed=SEED, strategy_key='smart',
        )
        return result, tmp_path / 'prof'

    def test_no_files_when_disabled(self, tmp_path):
        _, profile_dir = self._run(enabled=False, tmp_path=tmp_path)
        assert not profile_dir.exists(), '关闭剖析时不该创建任何目录'

    def test_results_identical_to_control(self, tmp_path):
        """**同种子逐字段一致**——测量工具不得伤及被测对象。

        比对是**多重集**意义下的（见 `_fingerprint` 的说明）：`imap_unordered` 的
        返回顺序不确定，而内容由种子决定。
        """
        off, _ = self._run(enabled=False, tmp_path=tmp_path / 'a')
        on, _ = self._run(enabled=True, tmp_path=tmp_path / 'b')
        assert _fingerprint(off) == _fingerprint(on)

    def test_result_version_unchanged(self, tmp_path):
        """§3.8 D3 的副产品：`CompactResult` 与 `_RESULT_VERSION` 完全不动。"""
        on, _ = self._run(enabled=True, tmp_path=tmp_path)
        assert _RESULT_VERSION == 3
        assert all(r.to_dict()['result_version'] == 3 for r in on)

    def test_no_marker_when_disabled(self, tmp_path):
        _, profile_dir = self._run(enabled=False, tmp_path=tmp_path)
        assert not list(profile_dir.rglob(f'{WORKER_MARKER_PREFIX}*')) if profile_dir.exists() else True


@requires_real_run
class TestTripleArityContract:
    def test_worker_returns_stay_triples(self, tmp_path):
        """真跑一次并行，父进程的 `len(result) == 3` 守卫不会落进 else 分支。

        落进 else 分支的症状是 `compact` 与 `warnings` 双丢且无告警——故额外用
        `collect_perf=True` 取到的字节数条数来佐证每个返回值都被正确解包。
        """
        store = load_toml(CONFIG)
        env = SimulationEnvBuilder.from_config_store(store)
        targets = {tc.card_id: getattr(tc, 'quantity', 1) for tc in store.target_cards}
        result = bs.run_batch_parallel(
            env=env, target_specs=targets, initial_resources=env.initial_resources,
            num_simulations=N, max_workers=WORKERS, seed=SEED, strategy_key='smart',
            collect_perf=True,
        )
        assert len(result.packet_bytes) == N
        assert all(b > 0 for b in result.packet_bytes)


@requires_real_run
class TestCliFunctionGrainClosure:
    """§3.9 T4 明写要求而此前**缺失**的那条断言（AUDIT-BREAK-3）。

    原文：「`cli` 路径的 `function` 档闭合链：断言 `cli` 适配器产出的
    `RunResult.functions` **非 `None`**（即 `--perf-json` 的 `run_id` / `functions`
    两字段确实回传到了适配器进程）——`cli` 是 §3.8 D1 指定的 `function` 档主路径，
    而它是子进程驱动，**不测这一条则该链「在两端各自成立、中间断开」时无人发现**」。

    2026-09-23 实测发现该断裂**确实存在**：`CliAdapter.build_argv` 从不传
    `--profile-*`，故被测 CLI 的剖析从未启动、`functions` 恒为 `None`，而报告里只有
    一条把读者指向 stderr 的告警。本类即原文要求的那道断言，现已补上并随之修好。
    """

    pytestmark = pytest.mark.timeout(60)   # §3.9：T4 ≤ 60s

    @pytest.fixture
    def plan(self, make_plan, tmp_path):
        return make_plan(config_path=CONFIG, n=20, workers=2, seed=SEED,
                         repeats=1, grain='function', collector=False,
                         profile_enabled=True, profile_dir=str(tmp_path / 'prof'),
                         profile_skip=0, profile_count=4)

    def test_functions_come_back_through_perf_json(self, plan):
        result = get_adapter('cli').run(plan)
        assert result.functions, (
            'cli 的 function 档闭合链断了：适配器未取到函数级统计。'
            f'告警：{result.warnings}'
        )
        names = ' '.join(f.name for f in result.functions)
        assert '_run_single' in names or 'output' in names, names[:300]

    def test_no_chain_when_no_directory(self, plan):
        """对照组：请求了剖析但**没有可写目录**时，`functions` 如实为 `None`。

        **注意不能用 `grain='function'` 造这个对照**：`grain='function'` 走两趟
        （§3.8 D6），第二趟**总会**自己配一个临时目录，故它必然有剖面。要测的是
        「请求了剖析、但没人给它落盘的地方」——对应 `stage` 档 + `profile_dir` 为空。

        同时断言告警**点名真实成因**：「没传 `--profile-dir`，剖析实际没启动」与
        D7 的「剖析故障，成因在 stderr 里」是两件事，混成一句会把读者指向一个
        空无一物的地方（这正是修好之前那条告警的问题）。
        """
        from dataclasses import replace

        quiet = replace(plan, grain='stage', profile_dir='', profile_enabled=True)
        result = get_adapter('cli').run(quiet)
        assert result.functions is None
        assert any('profile_dir 为空' in w for w in result.warnings), result.warnings
        assert not any('stderr 里有具体成因' in w for w in result.warnings), result.warnings
