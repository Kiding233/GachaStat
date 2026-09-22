"""T4c（`6e`）：D9 路径降级告警的注入测试。

**注入形态强制落到 `mp_failed`，不起真实进程池**——故不受 `P83_PERF_TESTS` 门控，
进默认 `pytest -q`（§3.9 T4c）。

§3.8 D9 的可读性价值**全建立在「两种降级成因可区分」上**：

| 成因 | 归属 | 例 |
|---|---|---|
| 剖析故障 | D7 | 目录不可写 / `cProfile` 不可用 / 文件缺失 / `pstats` 解析失败 |
| **路径降级** | **D9** | plan 声明 `function` 档，运行却落到 `mp_failed` 兜底 |

两者都软降级、都记 `warnings`，但读的人需要知道该去查什么。**无验收则可能静默退化
为同一句文案**——本文件就是那道验收。
"""

import os
import tempfile

import pytest

import gacha_simulator.service.batch_simulator as bs
from benchmarks.perf.profilers import cprofile as cprofile_mod
from gacha_simulator.core.config_toml import load_toml
from gacha_simulator.paths import get_config_dir
from gacha_simulator.service.batch_simulator import SimulationEnvBuilder

N = 2
SEED = 7
#: D9 文案的判别片段——必须是 D7 的四条文案里不会出现的词。
D9_MARKER = '路径降级'
D7_MARKERS = ('目录不可写', 'cProfile 不可用', '落盘失败', '解析或合并失败',
              '没有任何', '未指定 profile 目录')


@pytest.fixture
def env_and_targets():
    store = load_toml(os.path.join(get_config_dir(), 'config.toml'))
    env = SimulationEnvBuilder.from_config_store(store)
    targets = {tc.card_id: getattr(tc, 'quantity', 1) for tc in store.target_cards}
    return env, targets


@pytest.fixture
def force_mp_failed(monkeypatch):
    """把 `MPPool` 换成必失败的替身 → 三次重试后落到 `mp_failed` 兜底路径。

    走到 `workers=1` 仍失败即置 `mp_failed`，故**不会真的起进程池**。
    """
    class ExplodingPool:
        def __init__(self, *args, **kwargs):
            raise OSError('注入：进程池起不来（T4c）')

    monkeypatch.setattr(bs, 'MPPool', ExplodingPool)


def _run(env, targets, *, profile_enabled):
    env.profile_enabled = profile_enabled
    env.profile_dir = ''
    return bs.run_batch_parallel(
        env=env, target_specs=targets, initial_resources=env.initial_resources,
        num_simulations=N, max_workers=2, seed=SEED,
        strategy_key='smart', collect_perf=True,
    )


class TestD9Annotation:
    def test_warning_emitted_on_path_degradation(self, env_and_targets, force_mp_failed):
        env, targets = env_and_targets
        result = _run(env, targets, profile_enabled=True)
        matching = [w for w in result.warnings if D9_MARKER in w]
        assert matching, f'mp_failed + profile_enabled 应记一条路径降级告警；实得 {result.warnings}'
        assert 'mp_failed' in matching[0]

    def test_no_warning_when_profiling_not_requested(self, env_and_targets, force_mp_failed):
        """没请求剖析就谈不上「function 档不适用」——不该平白多一条告警。"""
        env, targets = env_and_targets
        result = _run(env, targets, profile_enabled=False)
        assert not [w for w in result.warnings if D9_MARKER in w]

    def test_no_files_written_anyway(self, env_and_targets, force_mp_failed, tmp_path):
        """兜底路径不经过 `_wk_run_single`，故一个剖面文件也不产——告警说的就是这件事。"""
        env, targets = env_and_targets
        env.profile_dir = str(tmp_path)
        bs.run_batch_parallel(
            env=env, target_specs=targets, initial_resources=env.initial_resources,
            num_simulations=N, max_workers=2, seed=SEED,
            strategy_key='smart', collect_perf=True,
        )
        assert list(tmp_path.glob('*.prof')) == []

    def test_simulation_still_completes(self, env_and_targets, force_mp_failed):
        """**模拟本身照常跑完**——路径降级只影响剖面，不影响被测对象。"""
        env, targets = env_and_targets
        result = _run(env, targets, profile_enabled=True)
        assert len(result) > 0
        assert all(r.get('total_draws') is not None for r in result)


class TestWordingIsDistinguishable:
    """告警的价值在于可区分——本条是它不退化的保证。"""

    def test_d9_differs_from_every_d7_wording(self):
        d9 = '路径降级：plan 声明了 function 档（profile_enabled 为真）'
        for marker in D7_MARKERS:
            assert marker not in d9, f'D9 文案不该含 D7 的判别词 {marker!r}'

    def test_d7_wordings_do_not_contain_d9_marker(self):
        """反向也要成立：D7 的各条不出现「路径降级」字样。"""
        merge_dir_missing = cprofile_mod.merge_profiles('/no/such/dir-p83')[1]
        empty = cprofile_mod.merge_profiles(tempfile.mkdtemp())[1]
        unspecified = cprofile_mod.merge_profiles('')[1]
        for warnings in (merge_dir_missing, empty, unspecified):
            for warning in warnings:
                assert D9_MARKER not in warning, warning

    def test_both_are_warnings_not_exceptions(self, env_and_targets, force_mp_failed, tmp_path):
        """两种降级都绝不抛异常（同 §3.8 D7 的方向）。"""
        env, targets = env_and_targets
        env.profile_dir = str(tmp_path / 'a_file')          # 制造 D7 的「落盘失败」
        (tmp_path / 'a_file').write_text('x', encoding='utf-8')
        result = bs.run_batch_parallel(
            env=env, target_specs=targets, initial_resources=env.initial_resources,
            num_simulations=N, max_workers=2, seed=SEED,
            strategy_key='smart', collect_perf=True,
        )
        assert isinstance(result.warnings, list)


class TestD9FlowsIntoRunResult:
    """`BatchResult.warnings` → `RunResult.warnings` 的传递（§3.8 D9 的通道）。"""

    def test_adapter_surfaces_it(self, env_and_targets, force_mp_failed, make_plan):
        """经 `inline` 适配器跑一次，D9 告警应出现在 `RunResult.warnings` 里。

        `MPPool` 已被替换成必失败的替身，故适配器内部的 `run_batch_parallel` 落到
        `mp_failed` 兜底路径，D9 告警经 `BatchResult.warnings` 进入 `SingleRun.warnings`。
        """
        from benchmarks.perf.adapters.base import get_adapter

        adapter = get_adapter('inline')
        plan = make_plan(config_path=os.path.join(get_config_dir(), 'config.toml'),
                         n=N, workers=2, seed=SEED, repeats=1, grain='stage',
                         collector=True, profile_enabled=True)
        result = adapter.run(plan)
        assert any(D9_MARKER in w for w in result.warnings), result.warnings
        assert result.functions is None, '路径降级时 functions 必然为 None'
