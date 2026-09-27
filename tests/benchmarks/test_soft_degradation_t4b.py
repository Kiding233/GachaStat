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

import json
import os
import tempfile
from pathlib import Path

import pytest

import gacha_simulator.service.batch_simulator as bs
from benchmarks.perf.profilers import cprofile as cprofile_mod
from benchmarks.perf.profilers.cprofile import (
    PROFILE_FILE_SUFFIX,
    WORKER_MARKER_PREFIX,
    WorkerProfiler,
    merge_profiles,
)
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


def _run(env, targets, *, profile_dir, enabled, workers=1, skip=None, count=None):
    env.profile_enabled = enabled
    env.profile_dir = profile_dir
    # 默认走单进程路径（不起池）——本文件大多数用例只需断言「请求剖析这条记账不影响
    # 模拟结果」，单进程即可，且因此能进默认 `pytest -q`。
    #
    # **但路径 3 必须起池**：`_make_worker_profiler` 只被 `_wk_init` 调用，单进程分支
    # 根本不读 `profile_enabled` / `profile_dir`——在单进程上断言「结果不受影响」是
    # **近乎构造性成立**的（独立审查 2026-09-28 指出）。
    if skip is not None:
        env.profile_skip = skip
    if count is not None:
        env.profile_count = count
    return bs.run_batch_parallel(
        env=env, target_specs=targets, initial_resources=env.initial_resources,
        num_simulations=N, max_workers=workers, seed=SEED, strategy_key='smart',
    )


#: 逐字段比对时排除的易变字段——`generated_at` 是采集时刻，同种子也不会相同；
#: 它与「模拟结果」无关，排除它是为了让「逐字段一致」这条断言真正检验模拟行为。
_VOLATILE = ('generated_at',)


def _fingerprint(result):
    """把一组 `CompactResult` 归一为可逐字段比对的形式。

    **按内容排序后再比**（2026-09-28 订正，独立审查指出）：MPPool 路径用
    `imap_unordered` 边收边 `append`（`batch_simulator.py:650`），同种子下每次模拟的
    **内容**是确定的、但**返回顺序不确定**（谁先算完谁先出）。不排序就是在比顺序，
    会把顺序差异误报成内容差异。**实测**：空载时 27/27 通过；加载 8 个满载 CPU 进程后
    16 对里 7 对失败，而每次失配都是纯排列、逐条内容完全相等。

    同一条 worker 路径的 `test_function_grain_t4.py` 早就按多重集读（那里的注释写的就是
    这个理由），本处此前漏了——**同一个仓里两处同型断言写法不一致，是漏抄而非有意**。
    """
    rows = [{k: v for k, v in r.to_dict().items() if k not in _VOLATILE} for r in result]
    return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False))


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
        """**独立审查指出本条此前是错的**（2026-09-28），已重写。

        §七 要求四条降级路径**各自**断言「模拟结果与不带 profile 的同种子对照组逐字段
        一致」，路径 3 此前只有「成因可辨」两条断言，我补的第一版**用了单进程路径**——
        而 `_make_worker_profiler` 只被 `_wk_init` 调用，单进程分支**根本不读**
        `profile_enabled` / `profile_dir`，于是「结果不受影响」**近乎构造性成立**：它证明
        的是「两个没人读的字段不改结果」，不是路径 3。

        **本版的触发方式照 §3.9 T4b 自己定的**（「令本 run 子目录为空 / 删除落盘文件」）：

        1. 起池（`workers=2`）并让采样窗口真的打开 → 字段到达 worker、采样器被构造、
           剖面真的落盘（三步都有断言先证明「确实发生了」，否则后面的断言是空转）；
        2. **把落下的 `.prof` 删掉**——对应现实中 worker 被 `Pool.__exit__` 的
           `terminate()` 强杀以致文件缺失（§3.8 D2 的实证依据）；
        3. 再断言合并侧报「没有任何文件」这个**路径 3 专属成因**，且模拟结果与对照组一致。

        **我第一版曾想用「`profile_skip` 大到窗口永不打开」来造文件缺失，那是错的**：
        `_write_marker()` 就在窗口内（`cprofile.py:138`），窗口不开则连自报标记都没有，
        「字段到了 worker」这一步就无从证明——同一次批评里被独立审查一并指出。
        """
        env_a, targets_a = env_and_targets
        env_b, targets_b = env_and_targets
        profile_dir = tmp_path / 'prof'
        profile_dir.mkdir(parents=True, exist_ok=True)
        # **对照与实验组同用 `workers=2`**：换并发度会连带换掉「哪个种子落在哪个 worker」，
        # 结果本就会变，那就不是一个受控对照了。
        control = _fingerprint(_run(env_a, targets_a, profile_dir='', enabled=False,
                                    workers=2))
        affected = _fingerprint(_run(env_b, targets_b, profile_dir=str(profile_dir),
                                     enabled=True, workers=2, skip=0, count=2))

        # **先证明本用例真的落在路径 3 的形态上**，否则下面的断言是空转：
        # ① worker 自报标记存在 → 四字段确实到了 worker、采样器确实被构造、窗口真的开了
        markers = list(profile_dir.rglob(f'{WORKER_MARKER_PREFIX}*'))
        assert markers, ('worker 未落自报标记——四字段没到 worker，那本条就退化成'
                         '「没人读这两个字段」的构造性断言了（独立审查的批评正是这一条）')
        # ② 剖面文件确实落过（证明采样真的发生）
        assert list(profile_dir.rglob(f'*{PROFILE_FILE_SUFFIX}')), '采样窗口没打开'
        # ③ 把它们删掉——**这就是 §3.9 T4b 定的路径 3 触发方式**（「令本 run 子目录为空 /
        #    删除落盘文件」），对应现实中 worker 被 `Pool.__exit__` 的 `terminate()` 强杀
        #    以致文件缺失。删的是本用例 tmp_path 下的产物，不涉仓库文件。
        for stale in profile_dir.rglob(f'*{PROFILE_FILE_SUFFIX}'):
            stale.unlink()
        functions, causes = merge_profiles(str(profile_dir))
        assert functions is None and '没有任何' in causes[0]

        assert affected == control, '文件缺失这一形态不得改变模拟结果'

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
