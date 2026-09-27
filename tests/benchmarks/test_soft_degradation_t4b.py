"""T4b（`6f`）：D7 四条软降级路径的单测。

§3.8 D7 的四条：`profile_dir` 不可写 / `cProfile` 不可用 / worker 被 `terminate()`
致文件缺失 / `pstats` 解析失败。

**注入 + fixture 形态，不跑真实进程池**——故不受 `P83_PERF_TESTS` 门控，进默认
`pytest -q`（§3.9 T4b）。

**同时断言「测量工具不得伤及被测对象」**：这四条路径下模拟结果必须与**不带 profile
的同种子对照组**逐字段一致。这是硬规则，硬规则没有测试就只是文档。
（worker 路径上的逐字段一致由 T4/`6g` 用真实进程池承担——那一段非跑池不可；
本文件覆盖的是不跑池即可注入的那些形态。）

每条路径还须**成因可辨**：D7 的四种成因不得共用一句话，否则读的人不知道该查什么。
"""

import os
import tempfile
from pathlib import Path

import pytest

import gacha_simulator.service.batch_simulator as bs
from benchmarks.perf.profilers import cprofile as cprofile_mod
from benchmarks.perf.profilers.cprofile import PROFILE_FILE_SUFFIX, WorkerProfiler, merge_profiles
from gacha_simulator.core.config_toml import load_toml
from gacha_simulator.paths import get_config_dir
from gacha_simulator.service.batch_simulator import SimulationEnvBuilder

N = 2
SEED = 11


@pytest.fixture
def env_and_targets():
    store = load_toml(os.path.join(get_config_dir(), 'config.toml'))
    env = SimulationEnvBuilder.from_config_store(store)
    targets = {tc.card_id: getattr(tc, 'quantity', 1) for tc in store.target_cards}
    return env, targets


def _run(env, targets, *, profile_dir, enabled):
    env.profile_enabled = enabled
    env.profile_dir = profile_dir
    # 单进程路径：不起池，故本文件可进默认 pytest -q；且它足以断言
    # 「请求剖析这条记账不影响模拟结果」。
    return bs.run_batch_parallel(
        env=env, target_specs=targets, initial_resources=env.initial_resources,
        num_simulations=N, max_workers=1, seed=SEED, strategy_key='smart',
    )


#: 逐字段比对时排除的易变字段——`generated_at` 是采集时刻，同种子也不会相同；
#: 它与「模拟结果」无关，排除它是为了让「逐字段一致」这条断言真正检验模拟行为。
_VOLATILE = ('generated_at',)


def _fingerprint(result):
    """把一组 `CompactResult` 归一为可逐字段比对的形式。"""
    return [
        {k: v for k, v in r.to_dict().items() if k not in _VOLATILE}
        for r in result
    ]


class TestPath1ProfileDirNotWritable:
    def test_dump_failure_is_soft(self, tmp_path):
        blocker = tmp_path / 'a_file'
        blocker.write_text('x', encoding='utf-8')
        profiler = WorkerProfiler(profile_dir=str(blocker / 'sub'), skip=0, count=5)
        with profiler.window():
            sum(range(1000))
        assert profiler.disabled_reason and '落盘失败' in profiler.disabled_reason
        assert profiler.dumped == 0
        # 停用之后不再采样——不反复撞同一堵墙
        assert profiler.should_sample() is False

    def test_merge_reports_directory_missing(self, tmp_path):
        _, warnings = merge_profiles(str(tmp_path / 'nope'))
        assert warnings and '目录不存在' in warnings[0]

    def test_simulation_unaffected(self, env_and_targets, tmp_path):
        env_a, targets_a = env_and_targets
        control = _fingerprint(_run(env_a, targets_a, profile_dir='', enabled=False))

        blocker = tmp_path / 'a_file'
        blocker.write_text('x', encoding='utf-8')
        env_b, targets_b = env_and_targets
        with_profile = _fingerprint(_run(env_b, targets_b,
                                        profile_dir=str(blocker / 'sub'), enabled=True))
        assert with_profile == control, '不可写的 profile 目录不得改变模拟结果'


class TestPath2CProfileUnavailable:
    def test_enable_failure_is_soft(self, monkeypatch):
        monkeypatch.setattr(cprofile_mod.cProfile, 'Profile', _ExplodingProfile)
        profiler = WorkerProfiler(profile_dir=tempfile.mkdtemp(), skip=0, count=2)
        with profiler.window():          # 不抛即通过
            sum(range(1000))
        assert profiler.disabled_reason and 'cProfile 不可用' in profiler.disabled_reason
        assert profiler.dumped == 0

    def test_simulation_unaffected(self, env_and_targets, monkeypatch, tmp_path):
        env_a, targets_a = env_and_targets
        control = _fingerprint(_run(env_a, targets_a, profile_dir='', enabled=False))

        monkeypatch.setattr(cprofile_mod.cProfile, 'Profile', _ExplodingProfile)
        env_b, targets_b = env_and_targets
        with_profile = _fingerprint(_run(env_b, targets_b,
                                        profile_dir=str(tmp_path / 'p'), enabled=True))
        assert with_profile == control, 'cProfile 不可用不得改变模拟结果'


class TestPath3WorkerTerminatedFilesMissing:
    """worker 被 `Pool.__exit__` 的 `terminate()` 强杀 → 文件没落盘。

    §3.8 D2 的实证依据就是这件事：`multiprocessing.pool.Pool.__exit__` 走
    `self.terminate()`，故「攒到窗口结束再落盘」的方案在这个失效面前毫无保障——
    这也是 `6b` 改成逐次落盘的原因之一。
    """

    def test_simulation_unaffected(self, env_and_targets, tmp_path):
        """**本条是独立审查补出来的**（§七 要求四条降级路径**各自**断言「模拟结果与不带
        profile 的同种子对照组逐字段一致」，而路径 3 此前只有「成因可辨」两条断言）。

        **自然触发**：单进程路径（`max_workers=1`）不经过 `_wk_run_single`，故即使请求了
        剖析也一个文件都不会落——正好就是「worker 被 terminate 致文件缺失」那一形态
        （§3.8 D2 的实证依据：`Pool.__exit__` 走 `self.terminate()`）。不需要注入替身。
        """
        env_a, targets_a = env_and_targets
        control = _fingerprint(_run(env_a, targets_a, profile_dir='', enabled=False))

        env_b, targets_b = env_and_targets
        profile_dir = tmp_path / 'prof'
        os.makedirs(profile_dir, exist_ok=True)
        affected = _fingerprint(_run(env_b, targets_b, profile_dir=str(profile_dir),
                                     enabled=True))
        assert affected == control, '文件缺失这一形态不得改变模拟结果'
        # 先确认本用例真的落在了路径 3 的形态上（否则这条断言是空转）
        assert list(profile_dir.rglob(f'*{PROFILE_FILE_SUFFIX}')) == []
        assert '没有任何' in merge_profiles(str(profile_dir))[1][0]

    def test_missing_files_have_their_own_cause(self, tmp_path):
        functions, warnings = merge_profiles(str(tmp_path))
        assert functions is None
        assert warnings and '没有任何' in warnings[0]
        assert 'terminate' in warnings[0], '成因须点名 terminate()，与「目录不存在」区分'

    def test_causes_differ_from_path1(self, tmp_path):
        _, missing_dir = merge_profiles(str(tmp_path / 'nope'))
        _, empty_dir = merge_profiles(str(tmp_path))
        assert missing_dir[0] != empty_dir[0]


class TestPath4PstatsParseFailure:
    def test_corrupt_file_is_skipped_not_fatal(self, tmp_path):
        (tmp_path / f'worker-1-0{PROFILE_FILE_SUFFIX}').write_text('not a profile', encoding='utf-8')
        functions, warnings = merge_profiles(str(tmp_path))
        assert functions is None
        assert warnings and '解析或合并失败' in warnings[0]

    def test_one_bad_file_does_not_lose_the_good_ones(self, tmp_path):
        profiler = WorkerProfiler(profile_dir=str(tmp_path), skip=0, count=1, label='good')
        with profiler.window():
            sum(range(5000))
        assert profiler.dumped == 1
        (tmp_path / f'broken-1-0{PROFILE_FILE_SUFFIX}').write_text('junk', encoding='utf-8')

        functions, warnings = merge_profiles(str(tmp_path))
        assert functions, '一个坏文件不该让好文件的结果一起丢掉'
        assert any('解析或合并失败' in w for w in warnings)
        assert len(warnings) == 1

    def test_simulation_unaffected(self, env_and_targets, tmp_path):
        env_a, targets_a = env_and_targets
        control = _fingerprint(_run(env_a, targets_a, profile_dir='', enabled=False))

        (tmp_path / f'broken-1-0{PROFILE_FILE_SUFFIX}').write_text('junk', encoding='utf-8')
        env_b, targets_b = env_and_targets
        with_profile = _fingerprint(_run(env_b, targets_b, profile_dir=str(tmp_path), enabled=True))
        assert with_profile == control


class TestAllFourCausesAreDistinct:
    """D7 的四种成因**不得共用一句话**——读的人据此决定该查什么。"""

    def _collect(self, tmp_path):
        blocker = tmp_path / 'a_file'
        blocker.write_text('x', encoding='utf-8')
        bad_dir = str(blocker / 'sub')

        profiler = WorkerProfiler(profile_dir=bad_dir, skip=0, count=1)
        with profiler.window():
            sum(range(100))
        unwritable = profiler.disabled_reason

        _, missing = merge_profiles(str(tmp_path / 'nope'))       # 目录不存在
        _, empty = merge_profiles(str(tmp_path / 'emptydir'))      # 无文件（terminate）
        os.makedirs(str(tmp_path / 'emptydir'), exist_ok=True)
        _, empty = merge_profiles(str(tmp_path / 'emptydir'))
        (tmp_path / 'emptydir' / f'x-1-0{PROFILE_FILE_SUFFIX}').write_text('junk', encoding='utf-8')
        _, broken = merge_profiles(str(tmp_path / 'emptydir'))
        return {
            '不可写': unwritable,
            '目录不存在': missing[0],
            '无文件': empty[0],
            '解析失败': broken[0],
        }

    def test_all_present(self, tmp_path):
        causes = self._collect(tmp_path)
        for name, text in causes.items():
            assert text, f'{name} 应有成因文案'

    def test_all_different(self, tmp_path):
        causes = self._collect(tmp_path)
        texts = list(causes.values())
        assert len(set(texts)) == len(texts), f'成因文案重复：{causes}'


class _ExplodingProfile:
    """替身：`enable()` 即抛，模拟 cProfile 不可用。"""

    def enable(self):
        raise RuntimeError('注入：cProfile 不可用（T4b）')

    def disable(self):  # pragma: no cover - 不会走到
        pass

    def dump_stats(self, path):  # pragma: no cover - 不会走到
        Path(path).write_bytes(b'')
